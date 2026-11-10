# AI RES — Operation/WorkerRun Event Model Verification v1.0

**Дата:** 10.11.2026  
**Тип проверки:** статическая документационная/контрактная проверка.

## Результаты

- AsyncAPI YAML parsed: **PASS** (AsyncAPI 3.1.0).
- Local `$ref` count: **360**.
- Missing local `$ref`: **0** — none.
- State Machine JSON parsed: **PASS**.
- Event catalogue in state machine: 14 Operation names and 23 WorkerRun names.
- Canonical AsyncAPI message definitions added: **36**.
- Deprecated legacy `WorkerRunAccepted` marked deprecated: **PASS**.
- Event guarantees explicitly encoded: at-least-once, per-aggregate ordering, Inbox dedupe, no exactly-once.

## Не выполнялось

Не выполнялись PostgreSQL DDL/migrations, конкурентная выдача sequence, transaction rollback tests, Outbox dispatcher/Inbox consumer crash tests, broker/network fault injection, Temporal integration/replay, ACL runtime tests, load tests, retention/legal-hold drills, official AsyncAPI CLI validation. Документация не является доказательством работающей реализации.

## Замечания

Исторические event names из AsyncAPI v1.4 сохранены для совместимости; `worker_run.accepted`/`WorkerRunAccepted` deprecated. Новая реализация должна использовать `worker_run.completed`. Старые сообщения требуют последующей миграции consumers и не должны порождать новую семантику.
