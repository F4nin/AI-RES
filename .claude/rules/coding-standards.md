# coding-standards.md — Стандарты разработки AI RES

**Нормативные источники:** `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` §3,§5 · `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` §15 · `AI_RES_API_and_Interaction_Contracts_v1.10.md`

---

## Технологический стек

### BASELINED
- **ORM и миграции:** Alembic + SQLAlchemy 2.x для `ai_res_db`.
- **СУБД:** PostgreSQL; pgvector для embeddings; `tsvector`/GIN для FTS.
- **Объектное хранилище:** MinIO с S3-compatible API.
- **Workflow Engine:** Temporal.
- **Agent reasoning:** LangGraph (scope — один WorkerRun).
- **Развёртывание MVP:** Docker Compose.
- **Инструментация:** OpenTelemetry SDK — единый стандарт.

### WORKING (не выбрано — не выбирать молча)
- Python Web-фреймворк (FastAPI, Litestar и др. — не утверждено).
- HTTP-библиотека для внутренних вызовов.
- Connection pool параметры, таймауты, backpressure thresholds.

В Increment 0: зафиксировать находки о существующем стеке (если есть) и предложить варианты владельцу. Не выбирать фреймворк без явного решения.

---

## Идентификаторы и типы данных

| Тип данных | Правило |
|---|---|
| PK новых доменных таблиц | UUIDv7 (рекомендован); UUIDv4 допустим если библиотека не поддерживает v7 надёжно. Самодельный генератор запрещён. |
| Human-readable номера | `REQ-000123`, `TASK-000045` — display/business IDs, не PK; уникальны в пределах org/project |
| Timestamps в БД | `timestamptz` UTC |
| Timestamps в API | UTC RFC3339 строка |
| Timezone пользователя | Отдельная настройка; не выводить из timestamp |
| Деньги / стоимость | `decimal`/`numeric` + явная валюта; не `float` |
| Статусы и типы | Controlled enum или reference registry; LLM-output строка не принимается как enum value без валидации |
| Расширяемые metadata | JSONB для typed extensions и versioned payload; не вместо нормализованных FK и key query fields |
| Embeddings | pgvector в PostgreSQL; не отдельный vector DB |

---

## API layer

- Base path: `/api/v1`; JSON `camelCase`; UUID идентификаторы; UTC RFC3339 timestamps.
- Ошибки: **RFC 9457 Problem Details**; стабильный machine-readable `code`; никаких stack traces, secrets, provider payload в ответе.
- Pagination: cursor-based со stable ordering; не возвращать недоступные объекты или их counts клиенту.
- Версионирование ресурсов: ETag / `If-Match` или explicit expected version для version-sensitive writes. Stale write → 412.
- Side-effecting POST: требует `Idempotency-Key`; replay одного `key+fingerprint` → тот же результат; тот же `key` + другой `fingerprint` → 409 `IDEMPOTENCY_KEY_REUSED`.
- Длительные операции: 202 Accepted + `Location` на Operation resource. Никогда не держать HTTP connection открытым на время agent execution.
- Не создавать generic `/execute` endpoint или arbitrary PATCH protected status fields.
- Не проксировать ORM entity как DTO напрямую; только явный DTO mapping.

---

## Слой доменных сервисов

- Domain write — только через Application Service / Domain Service, не из Worker Runtime напрямую.
- Не держать транзакцию открытой во время LLM RPC, Temporal RPC, HTTP/tool call, human wait.
- `MAX(sequence)+1` для monotonic sequences запрещён; использовать aggregate row lock/CAS или PostgreSQL sequences.
- Cross-database FK запрещены (`ai_res_db` ↔ `temporal_db` ↔ LangGraph schema).
- Projection update + aggregate event + Outbox record — **одна транзакция PostgreSQL**; rollback оставляет ни одной из трёх записей.

---

## WorkerRunEnvelope / WorkerResult / WorkerNotice

- Все три схемы versioned и validated.
- Четыре точки валидации: enqueue / перед выполнением Worker / при получении результата / перед downstream consumption.
- Unsupported major contract version → fail closed, не silent downgrade.
- WorkerResult immutable после сохранения; rework = новый WorkerRun с новым WorkerResult.
- **DOC-007 Worker Contracts — статус WORKING.** Поля контракта не финальные до перевода в BASELINED. Явно отражать в коде и тестах.

---

## Events и Outbox

- CloudEvents 1.0 envelope для всех domain events.
- Monotonic per-aggregate sequence: уникальный `(aggregate_id, sequence)`. `MAX(sequence)+1` запрещён.
- Сохранять тот же `event_id` при retry/redelivery.
- Не помещать в события: prompts, secrets, full source content, raw LLM responses, unredacted tool arguments.

---

## Именование

**PostgreSQL schemas** (доменные bounded contexts):
`iam`, `organization`, `project`, `work`, `requirements`, `sources`, `knowledge`, `decisions`, `artifacts`, `traceability`, `governance`, `agents`, `context`, `integrations`, `audit`, `platform`, `operations`, `execution`

**Таблицы:** snake_case, множественное число (`worker_runs`, `readiness_evaluations`, `outbox_events`).

**Alembic revisions:** именованные constraints; diff autogenerate требует manual review перед применением.

**Контракты в репозитории:**
```
contracts/
  openapi/
  asyncapi/
  json-schema/
    common/
    worker/
    events/
    commands/
  examples/
```

---

## Запрещённые паттерны

- Hardcoded credentials или secrets в коде или конфиг-файлах.
- `latest` теги контейнеров в любых deploy-конфигах.
- Произвольный пользовательский ввод как SQL, enum value, `object_type`/`link_type` без валидации по registry.
- Молчаливый fallback на старую версию документа/контракта при отсутствии актуальной.
- Прямой доступ Manager/Worker Runtime к PostgreSQL через credentials.
- SQLite как доказательство корректности PostgreSQL semantics (RLS, sequences, locking).
