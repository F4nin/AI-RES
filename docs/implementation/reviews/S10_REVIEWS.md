# S10 — независимое review (2026-11-12)

Основание: `.claude/rules/ecc-precedence.md` («Когда запускать агентов-ревьюеров», п. 2) и промпт S10 («минимум `code-reviewer` + профильный агент»): этап вносит миграцию с RLS/ролями/триггерами, fail-closed поведение доставки и контрактную валидацию. Не P0 по ADR-037.
Порядок: blind-first (агенты не читали отчёт этапа и этот файл), read-only. Состав: `code-reviewer`, `database-reviewer`, `silent-failure-hunter`. Выводы агентов статические (тесты они не запускали); подтверждение исправлений — тесты `test_event_delivery.py`.

**Итог:** CRITICAL — 0, HIGH — 0 по оценке `code-reviewer` и `database-reviewer`; `silent-failure-hunter` назвал два пункта HIGH (R1, R2), оба исправлены (R2 — защита вторым слоем: подмену уже отвергает триггер БД).

## 1. Исправлено в рамках этапа

| # | Источник | Находка | Исправление / проверка |
|---|---|---|---|
| R1 | silent HIGH-1, code L2 | Алерты роста и gauge нигде не вызывались: карантин блокирует агрегат, но сигнала нет, пока оператор не запустит CLI | `Dispatcher.observe()` (stats → gauge → `evaluate_outbox` → счётчик `alert` + error-лог), вызывается из `run_forever` по `stats_interval_seconds`; `InboxConsumer.observe()`; общий `get_event_metrics()` (gauge регистрируются один раз). Тест `test_dispatcher_survives_a_mark_error_and_reports_…` |
| R2 | silent HIGH-2 | Envelope не сверялся с колонками строки | `EventContract.check_row`: id, type, subject = колонки, иначе `ENVELOPE_MISMATCH` (dispatcher и consumer). Тест `test_consumer_paths_…` |
| R3 | silent M3 | Карантин при claim (`LEASE_EXPIRED_MAX_ATTEMPTS`) молчал | `claim_quarantined` → счётчик `quarantined` + error-лог. Тест |
| R4 | silent M4, code L5 | `format: date-time` не проверялся (нет `rfc3339-validator`) | зависимость добавлена и закреплена; тест `test_a_malformed_timestamp_…` |
| R5 | silent M5, code L4 | Ошибка БД при `mark_*` обрывала проход и цикл | per-row перехват (`mark_error`, лог только класса), `run_forever` — счётчик подряд идущих ошибок и громкий выход на `max_consecutive_errors`. Тест |
| R6 | silent M6, code M1 | Строки batch делят один lease и доставляются последовательно | `publish_timeout_seconds` + проверка конфигурации `batch × timeout ≤ 80 % lease`; строка с истёкшим lease не публикуется (`lease_lost:expired_before_publish`). Тесты `test_publish_timeout_…` |
| R7 | database M1 | `replay` обнуляет `attempt_count` → токен (owner, attempt) старого держателя снова совпадает | `replay_count` включён в токен fencing (`mark_*`, `OutboxRow`). Тест `test_same_owner_restart_…` |
| R8 | database M2 | Индексы под claim/quarantine | `ix_outbox_events_claim_pending`, `_claim_lease`, `_quarantined` (0015). План запроса на больших данных не проверялся (G-102) |
| R9 | database L3 | `replay_count` без защиты от произвольной записи | триггер `assert_replay_count_step` (+1 и только QUARANTINED→PENDING). Тест `test_replay_count_moves_only_by_one…` |
| R10 | database L4 | inline CHECK без NOT VALID | `ADD COLUMN` → `ADD CONSTRAINT … NOT VALID` → `VALIDATE CONSTRAINT` |
| R11 | silent M7, database L6, code L3 | `replay` молча принимал частичное совпадение | CLI считает `not_replayed`, код 2, если хоть один id не карантинный; `status` возвращает 3 при алертах. Тест CLI |
| R12 | code L1, silent L9 | Inbox QUARANTINED трактовался как DUPLICATE | отдельное значение `Delivery.QUARANTINED` → permanent `INBOX_QUARANTINED`; тесты STUCK/QUARANTINED |
| R13 | code M2–M4 | Тестовые пробелы: fencing по тому же owner, `lease_lost:failed`, преемник за IN_FLIGHT/backoff, ENVELOPE_MISMATCH, STUCK, contract-check consumer'а, гонка двух доставок (advisory lock), приватность логов | добавлены тесты (раздел «Тесты» отчёта); мусорные assert'ы убраны |

## 2. Принято / не исправлено (в отчёте этапа и KNOWN_GAPS)

| # | Находка | Решение |
|---|---|---|
| A1 | database L5, code L3, silent M7: replay не пишет `audit.audit_events` | G-100: роль dispatcher не пишет аудит; роль утверждающего — WORKING (Event Model §18) |
| A2 | database M2: `stats()` считает PUBLISHED полным сканом; claim EXPLAIN на больших данных | G-102: индексы добавлены, оценка нагрузки — S33 |
| A3 | code L5: `additionalProperties:false` против правила §15 «consumers игнорируют неизвестные опциональные поля» | G-103: AsyncAPI v1.6 закрыта (решение владельца G-56/ADR-054); расхождение Event Model §15 ↔ AsyncAPI оформить в NCP-13 (PROPOSED) |
| A4 | database L7, INFO-8: advisory-lock hash, `updated_at` задаётся клиентом | безвредно (ложная сериализация); один aggregate-lock на транзакцию зафиксирован комментарием/ADR-086 |
| A5 | silent L10: `InternalFanoutPublisher` считает любой возврат consumer'а успехом | защищает контракт библиотеки `InboxConsumer` (исключение при любой ошибке); зафиксировано в ADR-085 |

Дельта после исправлений отдельным агентом не пересматривалась (как в S06/S08).
