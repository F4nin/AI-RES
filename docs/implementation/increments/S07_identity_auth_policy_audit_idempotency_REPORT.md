# S07 — Identity, Local Auth, Policy Engine, Audit, Idempotency: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S07_identity_auth_policy_audit_idempotency.md` · **Итоговый статус:** **VERIFIED по решению владельца** (локально: backend 676, contracts 22, infra static 185, runtime 99; два прохода независимого review; GitHub Actions на Linux зелёный (2026-11-11, PR #6, коммит 86328e4: ci 43111752244 и 43111759690, contracts 43111752277 и 43111759762 — backend/infra-static/infra-runtime/contracts success; ранее на c8e9040: ci 43107954898 и 43107964966)).

## 1. Что реализовано
- **Пароли:** Argon2id (WORKING-параметры), минимум 15, denylist-seed, decoy-проверка для неизвестной учётки, rehash.
- **Сессии:** opaque, дайджесты в `iam.sessions`, idle 30 мин / absolute 12 ч, ротация без продления absolute, write-once revoke; cookie `ai_res_session` (HttpOnly/Secure/SameSite=Lax/Path=/api/v1), CSRF (HMAC от токена) + Origin/Referer allowlist, CORS deny-by-default; **G-48 закрыт** без SECURITY DEFINER/BYPASSRLS (ADR-062).
- **Вход/выход/смена пароля:** единый 401, прогрессивная задержка (без блокировки навсегда), XFF только от доверенных прокси, аудит событий.
- **MFA:** TOTP (pyotp) + recovery codes (одноразовые, hash), seed под AES-256-GCM, защита от повтора шага (CAS + триггер БД), ротация сессии, сброс; **сессия без второго фактора пригодна только для verify/logout/csrf** (найдено самопроверкой, S1 в `reviews/S07_REVIEWS.md`).
- **Bootstrap:** CLI/`make bootstrap`, секрет и пароль через prompt, одноразовость в `platform.bootstrap_state`.
- **Policy Engine** (ADR-017): версионируемая конфигурация с SHA-256, deny-by-default, fail-closed, reason codes, enforcer с аудитом (ALLOW атомарен с действием, DENY сохраняется после отката), `conceal` → одинаковый 404; **аккаунты:** disable/revoke membership отзывают сессии, защита от самоблокировки.
- **Audit writer** (одна транзакция, фильтр чувствительных ключей), **Idempotency service** (HMAC + key_id, ротация, advisory lock, 409), **сервисные токены** Ed25519 (короткоживущие, по аудитории, раздельные ключи).
- **HTTP:** `login, logout, getCsrfToken, changePassword, beginMfaEnrollment, confirmMfaEnrollment, verifyMfa` (overlay, WORKING) + `getCurrentUser` (`GET /me`, канон v1.3) через Policy Engine.
- **Инфраструктура:** `api` подключён к БД ролью `ai_res_api` (TLS verify-full), секреты `mfa_encryption_key`/`bootstrap_secret`, профиль Compose `bootstrap`, allowlist `check_compose.py`.
- **Не сделано (по scope/плану):** G-75…G-82 (`KNOWN_GAPS.md`); UI логина (S35); OIDC (post-MVP); подключение кольца идемпотентности и ключей сервисов к Compose (нет потребителей).

## 2. Нормативная база и проверка Registry
Registry v4.1 и canonical-документы §3 промпта присутствуют; `docs/architecture/` и Registry **не изменялись**. Discrepancy: словари статусов пользователя и результата аудита, ссылки на «Registry v4.0» (G-81); матрица Policy не задана нормативно (OD-15).

## 3. Созданные и изменённые файлы
- **Код:** `backend/src/ai_res/modules/iam/{passwords,tokens,sessions,throttle,auth,secretbox,totp,mfa,bootstrap,accounts,profile,service_tokens}.py` (+`denylist.txt`), `modules/audit/writer.py`, `modules/idempotency/service.py`, `policy/{config,engine,enforcer}.py` (+`policy_config.json`, `.sha256`), `api/{identity,request_security,client_ip}.py`, `api/app.py`, `cli/bootstrap.py`, `platform/{config,ports}.py`.
- **Миграции:** `0012_mfa_totp_replay_guard.py`, `0013_bootstrap_state.py`; `ops/postgres/schema_snapshot.sql` перегенерирован и разобран.
- **Контракты:** `contracts/openapi/extensions/identity_auth.yaml`, `spectral-functions/idempotencyKey.js`, `CHANGELOG.md`, тесты.
- **Infra:** `compose.yaml`, `scripts/{secrets_dev,check_compose}.py`, `Makefile` (`bootstrap`), тесты static/runtime.
- **Тесты:** unit — `test_iam_{passwords,tokens_and_request_security,throttle_and_client_ip,secretbox_and_totp,service_tokens}`, `test_policy_config`; integration — `test_iam_{sessions,audit_writer,login,mfa,bootstrap,accounts}`, `test_policy_engine`, `test_idempotency_service`, `test_identity_http`; обновлены `test_platform`, `test_audit_platform_schema`, `conftest` (`IamWorld`).
- **Документы (ненормативные):** `tools/adrs.py` + ADL (ADR-061…070), `KNOWN_GAPS.md` (G-48 закрыт, G-75…G-82), `DECISIONS_PENDING.md` (OD-03, OD-15), `NORMATIVE_CHANGE_PROPOSALS.md` (NCP-06), `REQUIREMENTS_TRACEABILITY.md`, `CONTRACT_TRACEABILITY_MAP.md`, `ECC_USAGE.md`, `reviews/S07_REVIEWS.md`, `docs/runbooks/identity-bootstrap.md`, `CONTEXT_HANDOFF.md`, `IMPLEMENTATION_STATUS.md`.

## 4. Изменения API / контрактов / событий
Добавлены 7 операций overlay (аддитивно, `breaking` = ok, Spectral без новых находок); `getCurrentUser` реализован по каноническому контракту. Событий нет (аудит ≠ domain events). Spectral: `x-idempotency-exempt` с письменной причиной.

## 5. Миграции и совместимость
`0012` (`last_used_step`, монотонный триггер), `0013` (`platform.bootstrap_state`, RLS FORCE, append-only) — аддитивны, greenfield; upgrade from empty и from previous проходят; drift снимка = 0; DROP/TRUNCATE нет.

## 6. Решения, принятые самостоятельно
ADR-061…070 (ACCEPTED, Implementation Lead). WORKING-значения вынесены в конфигурацию и перечислены в G-75/G-76/G-79; матрица политики — OD-15.

## 7. Устранённые несогласованности / NCP
G-48 закрыт (ADR-062). NCP-06 остаётся PROPOSED (auth-маршруты реализованы в overlay). Нормативные документы не менялись.

## 8. ECC: фактически использованные agents, skills, commands
Агенты не запускались (по правилам проекта — только по просьбе пользователя); см. `ECC_USAGE.md`.

## 9. Тесты и проверки
Команда: `make pre-pr` (contracts-check, contracts-test, backend-check, backend-test, infra-check, up, infra-test, infra-test-runtime). Результат ПОСЛЕ правок по независимому review: `make pre-pr` завершился с кодом 0 (2026-11-11): contracts 22 passed, backend 670 passed, infra static 181 passed, runtime 99 passed, ruff/mypy/import-linter (8 контрактов) чисто. Ниже — состав до правок:: contracts-check ok, contracts 22 passed, ruff/mypy/import-linter чисто, backend 655 passed (430 с), infra-check 0 нарушений, `make up` с миграциями, infra-test 181 passed, runtime 99 passed. После правок по review прогон повторяется (см. §11).
Отдельно (до pre-pr): policy-матрица 98 параметризованных кейсов, идемпотентность 18, сервисные токены 22, HTTP 17, `make infra-test-runtime` 99, contracts 22, infra static 82. Мутационные проверки: advisory lock; пропуск MFA (тест падал до исправления).

## 10. Security / authorization cases
Stale/revoked/expired/disabled session → 401 (один ответ); CSRF отсутствует/неверен/чужой Origin → 403; login-CSRF; CORS без заголовков (в т.ч. через Caddy); подделанный XFF не обходит лимит; single-use TOTP и recovery; **пропуск MFA → 403**; смена пароля/disable/revoke отзывают сессии; Policy: неизвестное действие, чужая организация, неактивный субъект/членство, сервис/агент, A3+, невалидная конфигурация → deny; недоступность/таймаут Policy → 503; DENY-аудит переживает откат, ALLOW-аудит откатывается с действием; conceal-404; IDOR между организациями; идемпотентность (параллель, чужой actor/команда/организация, 409, ротация ключа); логи и аудит без пароля/cookie/seed/recovery (golden); сервисные токены: подмена издателя/аудитории, срок, мусор, fuzz.

## 11. Независимое review
Два прохода четырьмя и двумя read-only агентами, blind-first (`reviews/S07_REVIEWS.md` §5 и §6). Первый проход: `database-reviewer`, `code-reviewer`, `silent-failure-hunter`, `security-reviewer`; второй, по дельте правок: `security-reviewer`, `silent-failure-hunter`. CRITICAL — 0, HIGH — 0 после первого прохода (HIGH первого прохода исправлены). Исправлены MEDIUM и разумные LOW с тестами; принятые риски и остаток — ADR-071…073, G-83; NCP-12 PROPOSED. Решения по R01/R03/SEC-05/SEC-06/OD-15 приняты владельцем (делегировано 2026-11-12). Агенты читали код и не запускали тесты; их выводы не заменяют человеческое approval.

## 12. Не выполненные проверки, ограничения, риски
G-75…G-82; интерактивный запуск `make bootstrap` в контейнере не прогонялся (CLI покрыт тестами `main()`, Compose-сервис — статикой); throttle process-local; параметры Argon2 не измерены; Linux CI не запускался.

## 13. Обновлённые документы и статусы
Да: см. §3. Статус S07 в `IMPLEMENTATION_STATUS.md`: TESTED.

## 14. Статус DoD
Выполнено: тесты раздела 9 промпта, миграции, контракты, секреты вне логов, документы, отчёт, независимое review слоя 3 (два прохода, CRITICAL/HIGH нет), Linux CI зелёный. Оговорки: агенты читали код и не запускали тесты; OD-15 (матрица политик) остаётся WORKING; NCP-12 PROPOSED; G-75…G-83 открыты. VERIFIED присвоен по решению владельца.

## 15. Можно ли начинать следующий этап
Да: S08 (проекты/work API) может опираться на `IdentityServices`, Policy Engine и `IdempotencyService`. Перед S08 стоит учесть G-83 и то, что матрица политик (OD-15) проверяется на реальных сценариях S08+.
