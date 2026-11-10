# AI RES — Operation Event Model и WorkerRun Event Model

**Версия:** 1.4  
**Дата:** 10.11.2026  
**Статус:** BASELINED design contract; реализация и runtime-проверки не заявляются.  
**Область:** доменные события Operation и WorkerRun, Transactional Outbox/Inbox, доставка, идемпотентность, порядок, эволюция схем и восстановление.

## 1. Назначение и нормативность

Документ конкретизирует event contracts для двух независимых доменных агрегатов. Историческая карта исходной редакции v1.0: Architecture Decision v1.2, Domain Model v1.4, Process Design v1.4, API Contracts v1.5, State Machine JSON v1.1 и AsyncAPI v1.5. Текущая нормативная карта приведена в дополнении v1.4 и Registry v4.0. При конфликте исторических фрагментов применять актуальные версии этих источников и настоящий документ.

Событие — неизменяемый факт уже совершившегося доменного изменения, а не команда, намерение или технический лог. Команды (`operation.cancel`, `worker_run.cancel`, `worker_run.create`) не публикуются как факты; их приём/отклонение порождает соответствующие доменные события. Temporal Workflow/Activity signals, LLM traces и telemetry не являются доменными событиями.

## 2. Принятые архитектурные решения

1. PostgreSQL в `ai_res_db` — canonical source of truth для Operation, WorkerRun, их текущих проекций и append-only event history.
2. Каждая доменная мутация и соответствующие event records + Outbox records фиксируются одной DB-транзакцией. Внешняя доставка выполняется после commit.
3. Доставка — **at-least-once**. Exactly-once end-to-end не обещается; идемпотентность обеспечивается event identity, aggregate sequence, Inbox и идемпотентными handlers.
4. Строгий порядок гарантируется только в пределах одного aggregate (`operation_id` или `worker_run_id`), не глобально и не между агрегатами.
5. Один aggregate получает монотонный `aggregate_sequence`, выделяемый в той же транзакции под optimistic/pessimistic concurrency control. Для каждой пары `(aggregate_type, aggregate_id, aggregate_sequence)` допускается ровно одно событие.
6. Event payload содержит идентификаторы, версии, коды причин и защищённые ссылки, но не полный prompt, chain-of-thought, секреты, полный документ, необработанный LLM/provider payload или содержимое источника.
7. События immutable. Исправление — новое компенсирующее/корректирующее событие, никогда UPDATE/DELETE старого факта.
8. Публичный SSE/API stream — ACL-filtered projection, не прямой поток Outbox.
9. События Operation и WorkerRun не заменяют AuditEvent. Защищённые административные/пользовательские действия дополнительно аудируются.
10. В MVP PostgreSQL Outbox/Inbox — транспортный механизм; Kafka/RabbitMQ не обязательны.

## 3. Разделение команд, событий и проекций

| Элемент | Назначение | Пример |
|---|---|---|
| Command | Запросить действие, может быть отклонён | `CancelOperation`, `CreateDerivedWorkerRun` |
| Domain event | Факт, который уже произошёл | `operation.cancel_requested`, `worker_run.derived` |
| Current projection | Быстрое чтение актуального состояния | `operations.operations`, `agents.worker_runs` |
| Event history | Полная упорядоченная история фактов | `operations.operation_events`, `agents.worker_run_events` |
| Outbox | Надёжная публикация committed events | `audit.outbox_events` |
| Inbox | Дедупликация и checkpoint потребителя | `audit.inbox_messages` |
| Audit | Кто/что/на каком основании выполнил защищённое действие | `audit.audit_events` |

Event history — доменная история; Outbox — доставка. Они связаны по `event_id`, но не должны быть одной таблицей с разными целями/retention.

## 4. Общая оболочка события

Использовать CloudEvents 1.0 JSON envelope с обязательными атрибутами:

| Атрибут | Тип | Правило |
|---|---|---|
| `specversion` | string | `1.0` |
| `id` | UUID | Глобально уникальный event ID, неизменен при redelivery |
| `source` | URI-reference | Стабильный URI доменного сервиса, например `urn:aires:operations` |
| `type` | string | Полное версионируемое имя, например `com.aires.operation.started.v1` |
| `subject` | string | `operations/{operationId}` или `worker-runs/{workerRunId}` |
| `time` | RFC3339 UTC | Время доменного commit/occurrence, не время dispatch |
| `datacontenttype` | string | `application/json` |
| `dataschema` | URI | Стабильный идентификатор схемы события конкретной версии |
| `traceparent` | string, optional | W3C Trace Context; не использовать как auth context |
| `data` | object | Typed payload по event schema |

Обязательные поля `data` для Operation/WorkerRun event:

- `eventId` — равен CloudEvents `id`;
- `eventType` — короткое имя из реестра;
- `schemaVersion` — integer, первоначально `1`;
- `aggregateType` — `OPERATION` или `WORKER_RUN`;
- `aggregateId`;
- `aggregateSequence` — монотонный sequence внутри aggregate;
- `aggregateVersion` — новая `row_version` проекции после перехода;
- `organizationId`, `projectId`;
- `operationId` — для обоих типов событий; для Operation совпадает с aggregateId, для WorkerRun — owning Operation;
- `occurredAt`;
- `actor` — typed `{type, id}` с `SYSTEM`, `USER`, `MANAGER`, `WORKER`, `SERVICE`; секреты и display names не передавать;
- `correlationId` — сквозной бизнес-контекст;
- `causationId` — непосредственная команда/предыдущее событие, если известно;
- `reasonCode` — стабильный машинный код при наличии;
- `transition` — `{from, to}` для status transition events;
- `refs` — только ACL-protected resource references.

Не включать `actor` token/session, prompt, model hidden reasoning, source text, full result, secret, grant token или сырые provider error messages.

## 5. Каталог Operation events

События публикуются только после соответствующего committed state/record. Прогресс/метрики могут быть coalesced в projection/SSE и не обязаны создавать высокочастотные domain events.

| Event type | Триггер и обязательные поля `data` сверх envelope | Терминальность |
|---|---|---|
| `operation.accepted` | Operation и idempotency record созданы; `operationType`, `idempotencyKeyRef`, `requestFingerprint`, `completionPolicyVersion` | Нет |
| `operation.queued` | Outbox dispatch принят scheduling boundary; `dispatchAttempt`, `workflowId` | Нет |
| `operation.started` | Подтверждён фактический старт workflow; `workflowId`, `workflowRunId` | Нет |
| `operation.waiting_for_human` | Все разрешённые пути прогресса заблокированы human action; `waitId`, `approvalOrDecisionRef`, `blockingScope` | Нет |
| `operation.waiting_for_dependency` | Все разрешённые пути прогресса заблокированы dependency; `dependencyRefs`, `blockingScope` | Нет |
| `operation.resumed` | Глобальный blocker снят; `resumeReason`, `resumedBy` | Нет |
| `operation.retrying` | Агрегатор выбрал recovery path; `recoveryAttempt`, `strategyCode`, `failedBranchRefs` | Нет |
| `operation.cancel_requested` | Отмена принята и каскадирована; `requestedBy`, `cancelScope`, `activeWorkerRunIds` | Нет |
| `operation.succeeded` | Все обязательные критерии завершены; `completionPolicySnapshotRef`, `resultSummaryRef` | Да |
| `operation.partially_succeeded` | Обязательные/допустимые partial-result rules выполнены; `partialResultReasons`, `completionPolicySnapshotRef` | Да |
| `operation.failed` | Нет допустимого recovery path; `failureCode`, `failedBranchRefs`, `problemRef` | Да |
| `operation.cancelled` | Cancel/cleanup/reconciliation завершены; `cancellationOutcome`, `reconciledSideEffectRefs` | Да |
| `operation.child_created` | Создана самостоятельная child Operation; `childOperationId`, `childPurpose`, `independenceCriteria` | Нет |
| `operation.progress_updated` | Существенное изменение агрегированного прогресса; `progressVersion`, `completedRequiredCount`, `totalRequiredCount`, `blockedCount` | Нет |

`operation.progress_updated` — coalescible informational event. Он не является источником истины для переходов и не должен публиковаться при каждом низкоуровневом изменении процента. Числовой процент — UI estimate, а не acceptance criterion.

## 6. Каталог WorkerRun events

| Event type | Триггер и обязательные поля `data` сверх envelope | Терминальность |
|---|---|---|
| `worker_run.created` | Run создан; `taskId`, `workerDefinitionVersionId`, `derivedFromWorkerRunId`, `derivationReason`, `attemptNumber` |
| `worker_run.preparation_started` | Подготовка Envelope/ContextPackage начата; `contextPackageVersionId` если уже создан |
| `worker_run.gate_evaluation_requested` | Создан запрос Gate evaluation; `readinessEvaluationId` |
| `worker_run.gate_evaluation_completed` | Immutable evaluation завершена; `readinessEvaluationId`, `gateOutcome`, `evaluationStatus`, `snapshotHash` |
| `worker_run.blocked` | Gate outcome BLOCKED и запуск не разрешён; `readinessEvaluationId`, `blockingCheckCodes` |
| `worker_run.queued` | Успешная Gate + final revalidation; `readinessEvaluationId`, `dispatchId` |
| `worker_run.started` | Фактический старт; `startedWithReadinessEvaluationId`, `workflowId`, `workflowRunId`, `workerDefinitionVersionId` |
| `worker_run.waiting_for_human` | Worker execution suspended; `waitId`, `requiredActionRef` |
| `worker_run.waiting_for_dependency` | Worker execution suspended; `dependencyRefs` |
| `worker_run.resumed` | Worker execution resumes; `resumeReason`, `resumedBy` |
| `worker_run.result_submitted` | Immutable result ref committed; `resultRef`, `outputContractVersion`, `contentChecksum` |
| `worker_run.validation_completed` | Deterministic output validation done; `validationId`, `validationOutcome`, `issueCodes` |
| `worker_run.review_requested` | Semantic review assigned; `reviewId`, `reviewType`, `reviewerType` |
| `worker_run.qa_requested` | QA policy requires independent review; `reviewId`, `qaWorkerRunId` when created |
| `worker_run.completed` | Execution contract accepted; `resultRef`, `validationRef`, `reviewRef` |
| `worker_run.rework_required` | Review requires rework; `reviewId`, `reworkReasonCodes`, `derivedRunRequired` |
| `worker_run.rejected` | Result rejected under task-class policy; `reviewId`, `rejectionReasonCodes` |
| `worker_run.unverified` | Evidence insufficient; `verificationStatus`, `limitationCodes` |
| `worker_run.cancel_requested` | Cancel accepted; `requestedBy`, `cancelReasonCode` |
| `worker_run.cancelled` | Cancellation reconciled; `cancellationOutcome`, `sideEffectRefs` |
| `worker_run.failed` | Execution/validation failed with no in-place continuation; `failureCode`, `problemRef`, `retryPermitted` |
| `worker_run.timed_out` | Deadline passed and outcome reconciled; `deadlineAt`, `reconciliationOutcome` |
| `worker_run.derived` | New substantive run created from prior run; `sourceWorkerRunId`, `derivedWorkerRunId`, `derivationReason` |

`readiness_evaluation.completed/blocked/stale` остаются отдельными ReadinessEvaluation events; `worker_run.gate_evaluation_completed` — связь evaluation с жизненным циклом конкретного WorkerRun, не дубликат полного evidence payload. Событие `worker_run.accepted` deprecated: не создавать в новых контрактах; использовать `worker_run.completed`.

## 7. События переходов и события фактов

Для status transition event `transition.from` и `transition.to` обязательны. Для создания сущности `from` отсутствует. Для non-status event (например, `result_submitted`, `progress_updated`) transition отсутствует. События не обязаны быть один-к-одному со всеми внутренними изменениями полей: публикуются значимые domain facts, определённые каталогом.

Каждый transition event должен соответствовать разрешённому переходу state machine. Нельзя публиковать `operation.succeeded` или `worker_run.completed` до commit соответствующего terminal status. Consumer не имеет права сам вычислять/исправлять aggregate state по payload: он либо обновляет собственную проекцию, либо вызывает владельца домена.

## 8. Транзакционный алгоритм записи

Для команды, меняющей aggregate:

1. Аутентифицировать caller; выполнить ACL, Policy, scope и idempotency checks.
2. Загрузить aggregate и проверить `expectedRowVersion`/ETag.
3. Валидировать transition, actor authority, Gate references, deadlines, dependency/approval constraints.
4. В одной транзакции PostgreSQL: обновить current projection с optimistic concurrency; выделить `aggregate_sequence`; вставить append-only event history; вставить Outbox envelope; записать AuditEvent, если действие требует аудита; завершить idempotency command record.
5. Commit. До commit событие не может быть доставлено.
6. Outbox dispatcher lease-ит доступные строки и публикует с тем же `event_id`; retry не меняет identity, payload или sequence.
7. Помечать delivered только после подтверждённого приёма транспортной границей. Если dispatcher упал после publish до отметки — повторная доставка ожидаема.

Для Operation/WorkerRun events текущая проекция, event history и Outbox всегда атомарны. Внешние системы/Temporal не входят в DB transaction.

## 9. Outbox, Inbox, доставка и порядок

### 9.1 Outbox

Минимальные поля: `id`, `event_id` unique, `aggregate_type`, `aggregate_id`, `aggregate_sequence`, `event_type`, `schema_version`, `payload_json`, `occurred_at`, `available_at`, `attempt_count`, `lease_owner`, `lease_until`, `delivered_at`, `last_error_code`, `created_at`. Индексы: ready dispatch `(delivered_at, available_at, lease_until)`, unique `(aggregate_type, aggregate_id, aggregate_sequence)`, unique `event_id`. Payload encrypted/ACL controlled at rest per platform policy.

Dispatcher:
- использует короткий lease и `FOR UPDATE SKIP LOCKED` или эквивалентную безопасную конкурентную стратегию;
- не держит DB transaction открытой во время network publish;
- сохраняет порядок внутри aggregate: событие N+1 не dispatch-ится, пока N не подтверждено, либо consumer обязан буферизовать gap; для MVP выбрать строгий per-aggregate dispatch order;
- bounded exponential backoff + jitter; после лимита — quarantine/DLQ с алертом, не silent drop;
- событие в quarantine не считается доставленным и остаётся доступным для controlled replay.

### 9.2 Inbox

Каждый durable consumer имеет отдельную inbox namespace. Минимальные поля: `consumer_name`, `event_id`, `aggregate_type`, `aggregate_id`, `aggregate_sequence`, `received_at`, `processed_at`, `processing_status`, `attempt_count`, `error_code`, `payload_ref` при необходимости. Unique `(consumer_name, event_id)`; unique `(consumer_name, aggregate_type, aggregate_id, aggregate_sequence)` если consumer применяет все события агрегата.

Consumer algorithm:
1. Начать локальную транзакцию.
2. Вставить inbox marker; duplicate event ID — no-op success.
3. Проверить aggregate sequence. Sequence меньше/equal checkpoint — duplicate/stale; gap — defer/retry, не применить out-of-order.
4. Выполнить локальную идемпотентную проекцию/side effect и обновить checkpoint в той же транзакции, насколько это возможно.
5. Commit. Внешний side effect выполняется через собственный outbox, не внутри handler без идемпотентного ключа.

### 9.3 Семантика доставки

- At-least-once, не exactly-once.
- Idempotency key для consumer — `(consumer_name, event_id)`; ordering key — `(aggregate_type, aggregate_id)`.
- `event_id` сохраняется при retry/redelivery.
- События разных aggregate могут приходить в любом порядке.
- Для cross-aggregate causality использовать `correlationId`/`causationId` и explicit references; не обещать глобальную транзакционность.

## 10. Idempotency и concurrency

### 10.1 Команды

Idempotency scope: `(organization_id, actor_scope, operation_name, idempotency_key)`. Сохранять request fingerprint, result resource ID, response status/body ref, created/expiry time. Повтор с тем же ключом и fingerprint возвращает прежний результат; тот же ключ с другим fingerprint — `IDEMPOTENCY_KEY_REUSED` (HTTP 409). TTL не удаляет event history и не позволяет повторно исполнить уже завершённую команду; retention idempotency records должен быть не короче максимального retry/replay horizon, установленного эксплуатационной политикой.

### 10.2 События

Producer создаёт event ID один раз в исходной транзакции. Повторный dispatch использует тот же ID. Consumer deduplicates по ID. Нельзя генерировать новый event ID при retry.

### 10.3 Optimistic concurrency

Каждый aggregate хранит `row_version`; каждое событие — `aggregate_version`. Команды могут передавать `expectedVersion`/`If-Match`. Несовпадение возвращает typed conflict (`AGGREGATE_VERSION_CONFLICT`), без автоматического overwrite. Sequence выделяется атомарно, без `MAX(sequence)+1` race.

## 11. Корреляция, causation и trace

- `correlationId` объединяет одну пользовательскую команду/Operation, дочерние Operation, Tasks и WorkerRuns.
- `causationId` указывает непосредственное событие или command receipt, вызвавшее факт.
- `operationId` всегда присутствует в WorkerRun events.
- `parentOperationId` присутствует только для child Operation; не означает наследование ACL.
- `traceparent` связывает технические spans, но не заменяет business correlation и не даёт права доступа.
- Temporal Workflow ID/Run ID — execution references, не event IDs и не domain IDs.

## 12. ACL и безопасность событий

Outbox не является публичной подпиской. Перед выдачей event history, SSE или integration delivery проверять organization/project/resource ACL и field-level policy. Не допускать утечку через имена каналов, counts, timing, error details, hidden child Operation или ссылки на evidence. Событие хранит opaque resource refs; потребитель получает payload объекта только через ACL-protected API. Consumer service identity имеет минимальный набор scopes. Секреты/токены запрещены в event data и error text.

## 13. Schema evolution

- `type` включает major schema version (`...v1`); `schemaVersion` фиксирует версию data schema.
- Добавление optional поля — backward-compatible minor evolution; изменение смысла/типа/обязательности или удаление поля — новая major event type (`...v2`).
- Не переиспользовать имя удалённого/устаревшего события с другой семантикой.
- Unknown optional fields consumers игнорируют; неизвестный major event type — quarantine/alert, не молчаливое применение.
- Producer contract tests проверяют payload против schema; consumer contract tests проверяют compatibility.
- Retired events остаются в историческом реестре и AsyncAPI с `deprecated: true` до завершения migration window.

## 14. Readiness/Gate event boundary

ReadinessEvaluation имеет собственный immutable lifecycle. События `readiness_evaluation.requested`, `readiness_evaluation.completed`, `readiness_evaluation.blocked`, `readiness_evaluation.stale`, `readiness_evaluation.evaluator_error` относятся к evaluation aggregate. WorkerRun event `worker_run.gate_evaluation_completed` содержит только ID, outcome/status и snapshot hash для связи. Gate event не означает запуск WorkerRun. `worker_run.started` требует exact `startedWithReadinessEvaluationId` и успешной final revalidation.

## 15. Recovery и failure handling

- DB commit succeeded, dispatcher down: Outbox остаётся pending; после восстановления dispatch.
- Publish succeeded, delivery marker not committed: duplicate delivery; Inbox dedupe.
- Consumer committed, ack lost: duplicate; Inbox dedupe.
- Sequence gap: defer later events, alert after threshold; do not skip silently.
- Poison event/schema mismatch: quarantine, preserve payload ref/checksum, alert; corrected consumer or explicit replay.
- Operation terminal but child WorkerRun active: reconciliation command to cancel/terminate according to policy; event only after confirmed domain transition.
- Temporal replay: техническое повторное выполнение не создаёт duplicate domain events/WorkerRuns; Activity side effects use deterministic idempotency keys.
- Ambiguous external side effect: manual/controlled reconciliation, never blind retry.

## 16. Наблюдаемость и эксплуатация

Метрики: outbox pending count/oldest age, dispatch attempts/errors, quarantined count, inbox duplicate count, sequence gap count/age, consumer lag, event processing latency, aggregate transition conflicts, invalid transition count, replay count. Логи — структурированные, без secrets/prompts/full payload. Alert thresholds задаются в observability configuration; значения не фиксируются здесь без нагрузочных данных.

## 17. Обязательные тесты

1. Atomicity projection + history + outbox (rollback всех трёх при failure).
2. Unique event ID и aggregate sequence под параллельной нагрузкой.
3. Concurrent transitions с optimistic locking; ровно один победитель.
4. Duplicate command same fingerprint returns same Operation; different fingerprint conflicts.
5. Dispatcher crash before publish / after publish before mark delivered.
6. Inbox duplicate event no-op; consumer crash before/after commit.
7. Per-aggregate ordering; gap buffering/retry; no global ordering assumption.
8. Poison event quarantine/replay; schema incompatibility handling.
9. Cross-aggregate causation/correlation across Operation, Task and WorkerRun.
10. Cancellation and timeout races with late success/side effect.
11. Temporal replay does not duplicate WorkerRun or domain event.
12. ACL filtering for event history/SSE/child Operation and evidence refs.
13. Payload privacy scan: no prompts, secrets, raw source text or full result bodies.
14. Schema compatibility producer/consumer contract tests.
15. Retention/legal hold does not delete immutable domain history under default policy.

## 18. Открытые эксплуатационные параметры

До production rollout определить и протестировать: Outbox batch size, lease duration, max attempts, backoff/jitter, quarantine replay approval, Inbox retention, event history retention/legal hold, idempotency retention, consumer lag SLO, sequence-gap alert threshold, payload encryption/key rotation. Эти параметры конфигурируемы; не хардкодить в domain code. Пока политика retention не утверждена, автоматическое удаление Operation/WorkerRun event history запрещено.

---

## Дополнение v1.1 — физическое хранение и транзакционные границы

## Дополнение v1.1 — физическая persistence реализация

Нормативные источники актуализированы: Architecture Decision v1.4, Domain Model v1.6, Process Design v1.6, API Contracts v1.6, AsyncAPI v1.5, State Machine JSON v1.2 и PostgreSQL Physical Model v1.0.

Event contracts остаются прежними по семантике. Физическая реализация:
- `operations.operation_events` и `agents.worker_run_events` — append-only history;
- `audit.outbox_events` — отдельная delivery queue, по одной записи на event/destination;
- `audit.inbox_messages` — consumer deduplication;
- aggregate sequence хранится в projection (`last_event_sequence`) и выделяется в одной транзакции под aggregate row lock/CAS;
- событие, projection mutation и Outbox insert атомарны;
- Outbox publish выполняется только после commit;
- Inbox и локальный handler effect атомарны;
- external consumer side effects выполняются через consumer-owned Outbox;
- Event History не является полной Event Sourcing моделью.

DDL, индексы, ограничения, миграционные шаги и TX-01..TX-09 определены в `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.0.md` и `AI_RES_PostgreSQL_Physical_Model_v1.0.sql`.

Изменение event schema по сравнению с v1.0 не вводится. Это дополнение фиксирует storage/delivery mapping и не меняет CloudEvents envelope, типы событий, delivery guarantee или ordering scope.


---

## Дополнение 1.2 — Database role ownership and migration lifecycle

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.


## Дополнение v1.3 — Persistence implementation contract

Operation/WorkerRun event persistence реализуется через SQLAlchemy 2.x repositories и Alembic-managed PostgreSQL schema. Aggregate projection, event history, sequence/version и все destination-specific Outbox rows создаются атомарно. Consumer Inbox dedupe и локальный consumer effect фиксируются одной транзакцией; внешний эффект оформляется новым Outbox command.

Миграционная цепочка, grants/RLS, connection context, tests и deployment gates определены в `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`. Event history остаётся append-only; event delivery — at-least-once; per-aggregate order enforced through aggregate sequence and dispatcher policy.


---

## Дополнение v1.4 — каноническая карта актуальных event/persistence contracts

**Статус:** BASELINED design contract.

Текущие нормативные источники: Architecture Decision v1.6; Domain Model v1.9; Process Design v1.9; API Contracts v1.10; AsyncAPI v1.6; State Machine JSON v1.2; PostgreSQL Physical Model v1.2; PostgreSQL Migration & Access Strategy v1.1; Persistence Implementation Blueprint v1.0; Identity & Access Control v1.5; Implementation Spec v1.21. Точные пути и версии подтверждаются Registry v4.0.

Ранее указанные версии источников в исторических разделах v1.0–v1.3 фиксируют контекст соответствующих изменений и не являются текущей нормативной картой. Event History — append-only domain facts; Outbox — delivery mechanism; Inbox — consumer deduplication. At-least-once delivery и per-aggregate ordering остаются гарантией, exactly-once не заявляется. Runtime acceptance не подразумевается.
