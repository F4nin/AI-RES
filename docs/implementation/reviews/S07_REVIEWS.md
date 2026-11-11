# S07 — проверки (ADR-035/037)

**Дата:** 2026-11-11. **Слой 3 (ADR-037) проведён 2026-11-11, дельта правок пересмотрена 2026-11-12 (§6)** по правилу владельца (`.claude/rules/ecc-precedence.md`): четыре read-only агента, blind-first (`database-reviewer`, `code-reviewer`, `silent-failure-hunter`, `security-reviewer`). Их выводы получены чтением кода, сами они тесты не запускали. Поправки ниже проверены тестами автора; дельта после правок пересмотрена отдельным проходом (§6).

## 1. Слой 1 — статические проверки
`ruff` (строка 160, S-правила), `mypy --strict`, `import-linter` (5 контрактов: api/platform без sqlalchemy, modules без api, db без api/modules), `check_compose.py` (13 сервисов, 0 нарушений; allowlist секретов для `api` и `bootstrap`), контракты (`make contracts-check`: mirror, OpenAPI/AsyncAPI/JSON Schema, Spectral без новых находок, breaking = ok), pinned-зависимости (`uv.lock`).

## 2. Слой 2 — тесты и мутационные проверки (реальный PostgreSQL 16, live-стек)
Список — в отчёте этапа. Мутации, выполненные вручную:
- убран `pg_advisory_xact_lock` в `IdempotencyService.begin` → `test_race_on_the_rotation_boundary…` падает (подтверждено), код восстановлен;
- тест на пропуск второго фактора написан до исправления и **упал** (`GET /me → 200` при `mfaRequired`), после исправления проходит.

## 3. Самопроверка автором (не независимая)

| ID | Серьёзность | Суть | Статус |
|---|---|---|---|
| S1 | HIGH | **Обход MFA:** пользователь с активным фактором после ввода пароля получал полноценную сессию; достаточно было проигнорировать `mfaRequired` (политика закрывала только привилегированные действия `iam.*`). Также позволяло из такой сессии вызвать смену пароля | **Исправлено**: `AuthenticatedSession.second_factor_pending` (активный фактор и нет `mfa_verified_at`); API пускает такую сессию только на `/auth/mfa/verify`, `/auth/logout`, `/auth/csrf`, остальное — 403 `mfa_required`; тест `test_a_session_that_skipped_the_second_factor…` |
| S2 | MEDIUM | `create_app_from_env` строил приложение без БД/ключа MFA — идентичность молча отсутствовала бы | **Исправлено**: без конфигурации БД/MFA API не стартует (fail closed), тесты S02 обновлены |
| S3 | MEDIUM | Устаревший guard S04 «API без DB credentials» противоречил ADR-015 | **Исправлено осознанно**: тест заменён на «только `ai_res_api`, только его пароль, остальные сервисы без DB-переменных» |
| S4 | LOW | Per-request `cookies=` в httpx-тестах (deprecated) | Исправлено |

## 4. Остаются открытыми (не скрыты)
- G-75…G-82 (`KNOWN_GAPS.md`): WORKING-параметры паролей, process-local throttle, доверие XFF без фиксированной подсети, runbook ротации, `auditAllow:false`, проводка ключей идемпотентности/сервисов в Compose, расхождения словарей, нереализованное (admin-тайм-ауты, reset/invite, IdentityProvider, jti-replay).
- OD-15 — матрица Policy Engine утверждена только как WORKING-конфигурация.
- Не проверено вне автора: криптографическая постановка `SecretBox` (AAD, формат blob), сравнение constant-time в местах, где сравниваются дайджесты в SQL, полнота редактирования логов для новых ключей. **Рекомендация владельцу:** запустить слой 3 (минимум `security-reviewer` + `silent-failure-hunter`) до перевода S07 в VERIFIED.


## 5. Слой 3 — независимое review (4 агента), триаж
CRITICAL — 0. Дубликаты между агентами объединены.

| ID | Серьёзность | Суть (кто нашёл) | Решение |
|---|---|---|---|
| L3-1 | HIGH | Гонка «последний владелец»: два владельца отключают друг друга (database, silent-failure, security) | **Исправлено**: `pg_advisory_xact_lock` на организацию в `_guard`; `test_two_owners_cannot_remove_each_other_concurrently` (мутация без блокировки — падает) |
| L3-2 | HIGH | Throttle check-then-act: пачка параллельных попыток проходит шлюз; перебор TOTP (silent-failure, security) | **Исправлено**: `LoginThrottle.reserve/release` (атомарно до проверки, отдаётся при успехе и при инфраструктурной ошибке); `test_a_burst_of_parallel_guesses…` (мутация — падает) |
| L3-3 | HIGH (DoS) | Синхронный Argon2 блокирует event loop, держит транзакцию (silent-failure, security) | **Исправлено**: `asyncio.to_thread` + семафор (по умолчанию 4) |
| L3-4 | HIGH | Отозванное членство не закрывает вход и доступ; project-роли и self-grant работают (security) | **Исправлено**: вход и `authenticate` отклоняют явно отозванное членство (`AuthFailure.MEMBERSHIP_REVOKED`), Policy Engine даёт `membership_inactive` на любые гранты. Project-only пользователь (строки членства нет) не затронут. Тесты в accounts/policy |
| L3-5 | MEDIUM | Блокировки throttle вытесняются флудом уникальных ключей (silent-failure, security) | **Исправлено**: активные `blocked_until` не вытесняются; тест (мутация — падает) |
| L3-6 | MEDIUM | Отзыв предъявленной сессии при логине — отдельная транзакция (code R06, silent-failure M-2) | **Исправлено** для своей организации (та же транзакция); для cookie чужой организации остаётся отдельная |
| L3-7 | MEDIUM | Ложный успех при нуле строк: `disable_user_in`, `revoke_membership_in`, `mfa.reset` | **Исправлено**: 409 / 404 без аудита успеха; тесты |
| L3-8 | MEDIUM | Счётчик throttle менялся до коммита (code R07, silent-failure L-3) | **Исправлено** тем же `reserve/release` |
| L3-9 | MEDIUM | `rotate_in` бросал голый `LookupError` (500) | **Исправлено**: 401 `ProblemError` |
| L3-10 | LOW | Секреты в `repr` (`IssuedSession`, `Enrollment`, `ConfirmedEnrollment`) | **Исправлено**: `field(repr=False)`; тест |
| L3-11 | LOW | CLI bootstrap печатает traceback с параметрами SQL | **Исправлено**: одна строка с именем класса исключения |
| L3-12 | LOW | `touch` сессии не проверял CAS | **Исправлено**: при проигрыше возвращается значение из БД |
| L3-13 | MEDIUM | Нет теста «аудит отказа упал → 503» и «аудит упал → откат» на путях login | **Исправлено** частично: тесты для denial-audit и login; остальные пути (change_password, mfa, bootstrap) — G-83 |
| L3-14 | LOW | Нет import-linter контрактов для `policy`, `cli` | **Исправлено**: +3 контракта (всего 8) |

### Решения владельца (делегировано, 2026-11-12) — внедрены
- **R01/SEC-03 → ADR-071:** отказывают только account и (account, ip); ip/global — сигнал аудита (`AI_RES_LOGIN_ENFORCE_IP_GLOBAL`, WORKING, по умолчанию выкл.); у сети `app` фиксированная подсеть, доверие к XFF только от Caddy (G-77 закрыт). NCP-12 (PROPOSED) — уточнение Auth v1.1 §4.
- **R03 → ADR-072:** неверный текущий пароль — 422, не 401.
- **SEC-05 → ADR-072:** подключение TOTP требует `currentPassword` (`AuthService.reauthenticate`).
- **SEC-06 → ADR-073:** иерархия ролей (WORKING, IAM v1.5 молчит): действовать можно на роль строго ниже своей, OWNER — и на OWNER.
- **OD-15:** матрица остаётся WORKING до проверки на S08+ (OD-16).

### Не исправлено — в KNOWN_GAPS
- **R02** — мёртвый `IdempotencyStorePort` в `platform/ports.py` (код S02, VERIFIED): не удалён, в G-83.
- **G-83** — остаточное: тесты отката при падении аудита на change_password/mfa/bootstrap; аудит отказов аутентификации сессии (R08); bootstrap без лимита попыток и `secret_digest` без соли; TTL идемпотентности по часам приложения; IPv6 /64 и несколько XFF; ротация ключа `SecretBox` не поддержана; `mfa.reset` без HTTP-обработчика — при его появлении обязателен `enforcer.authorize` и контрольный тест; нормализация Origin.


## 6. Ревью дельты (2026-11-12): `security-reviewer` + `silent-failure-hunter`, blind-first, read-only
Дельта = коммиты 1cb3c01 и c8e9040. CRITICAL — 0, HIGH — 0. Находки получены чтением кода (тесты агенты не запускали).

| ID | Серьёзность | Суть | Решение |
|---|---|---|---|
| D-1 | MEDIUM | Отмена запроса освобождала слот семафора Argon2, поток продолжал работать: лимит параллелизма не выполнялся | **Исправлено**: `ThreadPoolExecutor(max_workers=N)` вместо `to_thread`+семафор; тест `test_argon2_work_and_open_credential_transactions_are_bounded…` |
| D-2 | MEDIUM | Соединение пула держалось, пока ждёт семафор и считается Argon2: около 15 параллельных логинов исчерпывали пул | **Исправлено**: слот берётся ДО открытия транзакции (`async with self._slots, UnitOfWork(...)`) в login, change_password, reauthenticate; тот же тест |
| D-3 | MEDIUM | `SecretBoxError` молча превращался в «неверный код» (потеря ключа блокировала бы всех с MFA без следа) | **Исправлено частично**: ERROR-лог без секретов и идентификаторов, клиенту тот же 401; тест. Отдельный `reason_code` в аудите не добавлен (G-83) |
| D-4 | MEDIUM | Сбой отзыва сессии другой организации после коммита давал 500 без cookie | **Исправлено**: best-effort с логом; тест |
| D-5 | MEDIUM | `_bound` — полный проход и сортировка на каждый запрос при заполненной таблице | **Исправлено**: вытеснение пакетом до 90% лимита; тест |
| D-6 | MEDIUM | «Освобождение резервации после успеха стирает сигнал ip/global» | **Отклонено после анализа**: успех возвращает только собственную +1 (чистый ноль), перебор не скрывается. Моя первая правка (не возвращать ip/global) сделала бы сигнал шумным и была откатана; тест `test_a_stream_of_valid_logins_never_raises…` (мутант падает) |
| D-7 | MEDIUM | Любой аноним может держать аккаунт заблокированным, посылая по одной попытке после каждой задержки | **Принятый риск** (ADR-071, Auth v1.1 §4 запрещает только постоянную блокировку; смягчение: потолок задержки, MFA) |
| D-8 | LOW | `mfa.reset` позволял владельцу сбросить собственный фактор | **Исправлено**: `actor == user` отказ; тест |
| D-9 | LOW | Проверка иерархии читала роли до advisory-lock (TOCTOU) | **Исправлено**: блокировка берётся первой, внутри `ensure_may_act_on` |
| D-10 | LOW | `touch` сессии не отличал проигранный CAS от параллельного отзыва | **Исправлено**: при проигрыше перечитывается `revoked_at`, при отзыве — REVOKED. Тест покрывает только «CAS проигран, не отозвана»; ветка «отозвана во время» тестом не воспроизведена (нужна гонка) |
| D-11 | LOW | `AuthenticatedSession.csrf_token/csrf_digest` в repr; max_delay > window; touch ≥ idle; битый хеш пароля без сигнала | **Исправлено**: `repr=False`, валидации в `ThrottlePolicy` и `SessionService`, ERROR-лог на `InvalidHashError`; тесты |
| D-12 | LOW | Гонка begin/confirm enrollment, возможный второй фактор | **Не воспроизводится**: уникальный индекс `ux_mfa_factors_active_per_user` (`status <> 'REVOKED'`) |
| D-13 | LOW | Отдельные бюджеты throttle для login/pwchange/reauth/mfa; рост аудита от уникальных email; `release` не идемпотентен; CLI bootstrap без логов; результат rehash не проверяется; `_audit_hierarchy_denial` ловит `Exception` | Записано в G-83, не исправлено |
