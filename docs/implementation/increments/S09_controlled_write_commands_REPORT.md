# S09 — Controlled write commands: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S09_controlled_write_commands.md` · **Итоговый статус:** VERIFIED (локально `make pre-pr` ok; GitHub Actions на Linux зелёный на коммите cc26beb: ci 43203466196 и 43203684744, contracts 43203466171 и 43203684738; приём загрузки хранилищем — IMPLEMENTATION NOT VERIFIED, G-92)

## 1. Что реализовано
Шесть команд записи Public API v1.3: createProject, updateProjectMetadata, createEpic, registerRequirementCandidate, proposeRequirementVersion, createUploadIntent — каждая в одной транзакции (проекция + событие + outbox + аудит + запись идемпотентности), с CSRF/Origin, ACL с утаиванием (404/403), If-Match (428/412) и Idempotency-Key. `createTask` в S09 не реализован: перенос в S21 (ADR-012, NCP-08; ADR-078).

## 2. Нормативная база и проверка Registry
Registry v4.1 и документы из промпта присутствуют в `docs/architecture/`; нормативные документы не менялись. Расхождения: у AsyncAPI v1.6 два семейства `type` (`com.aires.*`, `aires.*`); OAS не называет источник ETag требования (G-91) и не задаёт лимиты текстов (G-95).

## 3. Созданные и изменённые файлы
| Область | Файлы |
|---|---|
| API | `api/write_api.py`, `api/locator.py` (новые); `api/app.py`, `api/identity.py`, `api/read_api.py` |
| Домен | `modules/projects/`, `modules/epics/` (новые); `modules/requirements/repository.py`, `modules/sources/{repository.py,presign.py}`, `modules/idempotency/repository.py`, `modules/events/{aggregate_events.py,envelope.py}`, `modules/readmodel/queries.py`, `db/session.py` |
| Конфигурация и политика | `platform/config.py`, `policy/policy_config.json` + `.sha256` (2026-11-12.2) |
| Миграция | `db/migrations/versions/0014_write_commands_events.py`, `ops/postgres/schema_snapshot.sql` |
| Инфраструктура | `infra/compose.yaml`, `scripts/{check_compose.py,secrets_dev.py}`, секрет `idempotency_keyring`, тесты infra |
| Тесты | `tests/integration/postgres/test_write_api.py` (36), `tests/unit/test_presign.py` (10), правки `test_policy_engine.py`, `test_audit_platform_schema.py`, `test_operations_work_schema.py` |
| Документы | ADR-078…083, G-84 закрыт, G-91…G-97, OD-18, карта трассировки, `reviews/S09_REVIEWS.md` |

## 4. Изменения API / контрактов / событий
Только операции из OAS v1.3. События: ProjectCreated, EpicCreated, RequirementVersionCreated (канал `aires.project.events`, проверены против схем AsyncAPI v1.6 в тестах). Для updateProjectMetadata и createUploadIntent событий нет (нет сообщения; G-93). Аддитивно: заголовок ETag в ответах register/propose требования (G-91). Контракты в `contracts/` не менялись.

## 5. Миграции и совместимость
Ревизия 0014, expand-only: `project.projects.goal`, `last_event_sequence` у проектов и эпиков, таблицы `project.project_events`, `work.epic_events` (RLS ENABLE+FORCE, insert-only, контроль непрерывности), типы агрегатов PROJECT/EPIC, замена `audit.assert_outbox_matches_event` (ветки OPERATION/WORKER_RUN не изменены). Downgrade запрещён. Проверено: upgrade с пустой БД и с предыдущей ревизии, schema drift, rls_coverage, grants_audit, postflight.

## 6. Решения, принятые самостоятельно
ADR-078 (конвейер и двухфазный createProject), ADR-079 (события и триггер), ADR-080 (отображение команд, охрана статуса версии), ADR-081 (SigV4), ADR-082 (семантика intent), ADR-083 (матрица записи WORKING и первый администратор). Все WORKING-значения вынесены в OD-18/G-95.

## 7. Выполненные тесты (`make pre-pr`)
| Набор | Результат |
|---|---|
| contracts | passed (`make contracts-test`) |
| backend (`uv run --locked pytest -q`) | **924 passed**, 881.65 s |
| ruff / mypy / import-linter | чисто / 95 файлов без ошибок / 8 kept, 0 broken |
| infra static (`make infra-test`) | **186 passed** |
| infra runtime (`make infra-test-runtime`) | **99 passed** (стек с миграцией 0014) |
| `infra-scan-secrets` | 0 находок (после замены тестового ключа AWS на разбитый литерал) |
Первый `pre-pr` упал на `infra-scan-secrets` (публичный ключ AWS из документации в `test_presign.py`); исправлено, оставшиеся шаги выполнены отдельным запуском `make up infra-test infra-test-runtime`.

## 8. Проверенные security/authorization кейсы
Без сессии → 401; нет CSRF-токена / чужой или отсутствующий Origin → 403 до любых изменений; IDOR: чужой, невидимый и несуществующий проект неразличимы (404, идентичное тело); viewer/analyst на `project.update`, viewer на создание → 403; привилегированная роль без MFA; организация из тела не доверяется; idempotency: replay, другой fingerprint → 409, параллельные повторы → одна запись; If-Match: отсутствует 428, устаревший/некорректный 412, конкурентные предложения → ровно одна версия; откат всего при сбое outbox; fail-closed при сбое Policy Engine, без key ring и без конфигурации хранилища (503); подписанный URL: нет имени файла в ключе объекта, URL не хранится, лимиты размера/типа; неизменяемость версий через роль API; запрет предложения на `IN_BASELINE`.

## 9. Неразрешённые вопросы и допущения
G-91…G-97, OD-18 (WORKING-матрица, лимиты, статус Epic `PROPOSED`, автоматическое членство создателя, блокирующие статусы версии), A1–A16 в `reviews/S09_REVIEWS.md`. Подпись PUT не проверена против живого MinIO.

## 10. Независимое review
Выполнено (правило ecc-precedence, п. 2): security-reviewer, database-reviewer, silent-failure-hunter, code-reviewer, blind-first. CRITICAL/HIGH — 0; исправлены R1–R4. Дельта правок отдельным проходом не пересматривалась.

## 11. Документы и контракты обновлены
Да: ADL, KNOWN_GAPS, DECISIONS_PENDING, CONTRACT_TRACEABILITY_MAP, STATUS, HANDOFF. Нормативные документы и Registry не менялись.

## 12. Следующий безопасный инкремент
S10 (Outbox dispatcher / Inbox и доставка событий) — после слияния S09; перед ним решить OD-13 (формы `dataschema`/`source`) и учесть G-93.
