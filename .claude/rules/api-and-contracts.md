# api-and-contracts.md — API, контракты и события

**Нормативные источники:** `AI_RES_API_and_Interaction_Contracts_v1.10.md` · `AI_RES_Public_API_v1.3.yaml` · `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml` · `AI_RES_Worker_Contracts_v1.1.schema.json` · `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md`

---

## Общие правила Public API (BASELINED)

- Base path: `/api/v1`.
- Format: JSON, `camelCase` поля.
- Timestamps: UTC RFC3339 строки.
- Идентификаторы: UUID строки.
- Ошибки: RFC 9457 Problem Details; стабильный machine-readable `code`; никаких stack traces, secrets, provider payload.
- Authenticity: только server-side; не доверять client-supplied authorization context.

**Важно:** `AI_RES_Public_API_v1.3.yaml` описывает **начальный вертикальный срез**, не полный endpoint catalogue. Отсутствие endpoint в OpenAPI не запрещает его существование, но реализовывать endpoint без контракта запрещено.

---

## Pagination

- Cursor-based с stable ordering.
- Не возвращать объекты, недоступные текущему пользователю.
- Не включать в ответ aggregate counts недоступных объектов.
- Следующая страница: opaque cursor (не offset).

---

## Версионирование ресурсов и оптимистичная блокировка

- Version-sensitive writes (Requirement, Artifact, Plan, Baseline и др.) требуют `ETag`/`If-Match` или explicit `expected_version`.
- Stale write → **412 Precondition Failed**.
- Не реализовывать last-write-wins для версионируемых ресурсов.
- Нельзя обходить version check для «быстрых» административных операций.

---

## Idempotency

- Side-effecting POST (операции с внешними side effects, создание WorkerRun, upload finalization и др.) требуют `Idempotency-Key` header.
- Replay того же `key + fingerprint` → тот же результат без дублирования action.
- Тот же `key` + другой `fingerprint` → **409 `IDEMPOTENCY_KEY_REUSED`**.
- Idempotency key хранится как HMAC digest с tenant/scope binding; не как plaintext.
- Idempotent retry не создаёт дубль Operation, Task, WorkerRun, approval, upload finalization или external action.

---

## Асинхронные операции (BASELINED)

- Любой долгосрочный процесс (agent execution, source ingestion, batch analysis) → **202 Accepted** + `Location: /api/v1/operations/{id}`.
- Никогда не держать HTTP connection открытым на время agent execution.
- `GET /api/v1/operations/{id}` — read model из PostgreSQL `operations` schema; не через Temporal polling.
- `POST /api/v1/operations/{id}/cancel` — request cancellation; не обещает немедленного завершения.
- SSE (`/api/v1/events` или per-resource stream) — projection авторизованных domain events; источник истины состояния — REST snapshot, не SSE.
- Operation Events history API (`GET /operations/{id}/events`): **не включать в MVP** без подтверждённой продуктовой потребности (из Architecture Decision v1.6 §2.6).

---

## WorkerRunEnvelope / WorkerResult / WorkerNotice

- Все три схемы versioned; major version bump = breaking change.
- Валидация в четырёх точках: enqueue / перед исполнением Worker / при получении результата / перед downstream consumption.
- Unsupported major version → fail closed; никакого silent downgrade.
- WorkerResult содержит: structured output, links к созданным/обновлённым domain objects, evidence refs, ограничения, неопределённость, self-assessment. Не содержит full prompts, secrets, raw provider responses.
- **DOC-007 Worker Contracts — статус WORKING.** До финализации считать поля черновыми.

---

## Domain Events (BASELINED — DOC-008 AsyncAPI v1.6)

- CloudEvents 1.0 envelope для всех domain events.
- Monotonic per-aggregate sequence: уникальный `(aggregate_id, sequence)`; `MAX()+1` запрещён.
- Сохранять тот же `event_id` на retry/redelivery.
- Гарантия: at-least-once; exactly-once не обещается.
- Consumer Inbox: deduplication `(consumer_name, event_id)`; duplicate delivery = successful no-op.
- Sequence gap: defer обработку, не пропускать молча.
- Строгий ordering только per-aggregate; не глобальный.
- Запрещено в event payload: prompts, secrets, full source/document body, raw LLM output, unredacted tool args/results.
- Schema compatibility: additive optional fields within major version = non-breaking; breaking change → новый major event type. Unknown major → quarantine + alert.

**Текущий naming gap (известное расхождение):**
В текущих event schemas используется `gateResultId`; Architecture Decision v1.6 §3.2 указывает переименовать в `readinessEvaluationId` при следующей breaking-safe версии. Не создавать две таблицы `gate_results` и `readiness_evaluations`.

---

## Outbox dispatcher

- Dispatcher читает Outbox из PostgreSQL и публикует в internal/external consumers.
- Lease: не держать DB lock во время network call.
- Per-aggregate ordering: dispatcher публикует события одного aggregate в порядке sequence.
- Bounded retry + backoff/jitter.
- Quarantine для poison events: отдельная очередь + alert; не блокировать нормальный поток.
- Controlled replay: возможность повторной отправки из quarantine после исправления.

---

## Connector Platform (BASELINED — MVP scope)

**MVP:** read-only коннекторы.
- Загрузка файлов (PDF/DOCX/MD/TXT/XLSX/CSV).
- OpenAPI/Swagger import.
- GitHub/GitLab read-only (commits, files, PRs — без write operations).

**Запрещено в MVP:**
- Write operations или bidirectional sync с любой внешней системой.
- Произвольный outbound HTTP из Worker без Connector Platform.

Connector Platform — единственный маршрут к внешним project systems. Worker не вызывает provider API напрямую.

---

## OpenAPI/AsyncAPI toolchain

- Pinned версии валидаторов в lock/config (не `@latest`).
- CI: validate OpenAPI, AsyncAPI, JSON Schema при каждом PR.
- Breaking-change detection: запрещено merge с breaking change без явного versioning решения.
- Генерация application code из схем — только после прохождения schema validation.
- Consumer/provider contract tests обязательны.
- API changelog и compatibility policy: вести в `contracts/` рядом со схемами.
