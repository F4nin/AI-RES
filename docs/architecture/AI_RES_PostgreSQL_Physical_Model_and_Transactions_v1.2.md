# AI RES — Физическая модель PostgreSQL и транзакционные алгоритмы

**Версия:** 1.2  
**Дата:** 10.11.2026  
**Статус:** BASELINED design contract для доменного persistence slice Operation / Task / WorkerRun / ReadinessEvaluation / Domain Events; DDL является проектной миграционной спецификацией и требует runtime validation.  
**Область:** `ai_res_db`, физические таблицы, связи, индексы, concurrency, idempotency, Outbox/Inbox, транзакционные алгоритмы, миграции и восстановление.

## 1. Назначение и границы

Документ переводит утверждённые Domain Model v1.5, Operation/WorkerRun Lifecycle v1.2, Event Model v1.0 и Process Design v1.5 в конкретную физическую модель PostgreSQL для критического execution slice AI RES.

Решение распространяется на:
- `operations.operations`, `operations.operation_events`;
- `work.tasks` и `work.task_dependencies` как существующие доменные сущности, расширяемые связью с Operation;
- `agents.worker_runs`, `agents.worker_run_events`, `agents.worker_results`;
- `execution.readiness_evaluations`, `execution.readiness_check_results`;
- `audit.outbox_events`, `audit.inbox_messages`, `audit.audit_events`;
- `platform.idempotency_records` (отдельная техническая схема для idempotency; если в реализации принят `audit`, имя должно быть согласовано до первой миграции).

Не является полной схемой всей AI RES БД и не описывает все поля Project, Epic, Artifact, Requirements, IAM и Context. Их существующие таблицы остаются в соответствующих доменных схемах. Temporal persistence остаётся в отдельной `temporal_db`; AI RES не создаёт собственные таблицы внутри Temporal schema.

## 2. Нормативные решения

1. PostgreSQL `ai_res_db` — canonical source of truth для Operation, Task association, WorkerRun, ReadinessEvaluation, event history и delivery records.
2. Доменное состояние не строится исключительно replay-ем событий. Текущие проекции и append-only event history обновляются в одной транзакции.
3. Все изменения состояния и соответствующие доменные события + Outbox записи фиксируются атомарно.
4. `READ COMMITTED` — стандартный уровень изоляции MVP. Корректность обеспечивается row locks / compare-and-swap (`row_version`) и уникальными ограничениями. `SERIALIZABLE` применяется только к конкретным алгоритмам, если доказана необходимость.
5. PK — UUIDv7, генерируемый приложением через проверенную библиотеку; UUIDv4 допускается как fallback. Не использовать самодельный SQL UUIDv7 генератор.
6. Время — `timestamptz` UTC. Суммы/бюджеты — `numeric`, не float.
7. Status — `text` + CHECK constraints / controlled registry, а не PostgreSQL ENUM в MVP: это облегчает expand/contract миграции. Любая строка статуса всё равно проходит domain validation.
8. FK — `ON DELETE RESTRICT` для доменной истории. Физическое удаление Operation/Task/WorkerRun с событиями запрещено; используется archive/soft-delete по отдельной политике.
9. JSONB разрешён для versioned event payload, policy snapshots и typed metadata, но не заменяет FK, ключевые поля и нормализованные связи.
10. Никакие LLM prompts, hidden reasoning, секреты, access tokens, полные документы и необработанные provider payload не хранятся в event/outbox/inbox.
11. Outbox delivery — at-least-once. Exactly-once end-to-end не обещается.
12. Один aggregate sequence выделяется под блокировкой строки агрегата в той же транзакции, что и переход состояния и event insert.
13. Worker Runtime не получает unrestricted SQL write-доступ к доменным таблицам. Все доменные мутации проходят через Application/Domain Service.
14. Cross-schema FK допустимы внутри одной `ai_res_db`; cross-database FK к `temporal_db` запрещены. Temporal IDs хранятся как references без FK.

## 3. Логические схемы и ownership

| Schema | Таблицы этого блока | Владелец записи |
|---|---|---|
| `operations` | `operations`, `operation_events` | Operation Application Service |
| `work` | `tasks`, `task_dependencies` | Work/Planning Service |
| `agents` | `worker_runs`, `worker_run_events`, `worker_results` | WorkerRun Application Service |
| `execution` | `readiness_evaluations`, `readiness_check_results` | Gate Evaluator |
| `audit` | `outbox_events`, `inbox_messages`, `audit_events` | Outbox Dispatcher / Consumers / Audit Service |
| `platform` | `idempotency_records` | Idempotency middleware/Application Service |

Schema ownership — граница полномочий приложения, а не самостоятельный security boundary. Роли PostgreSQL ограничиваются least privilege; приложения не обходят доменные сервисы прямыми UPDATE.

## 4. ER-модель и кардинальности

- Organization 1:N Project.
- Project 1:N Operation.
- Operation 1:N Task в MVP.
- Task 1:N WorkerRun.
- Operation 1:N WorkerRun (денормализованная owning reference для запросов и защиты scope); composite FK гарантирует, что WorkerRun.operation_id соответствует Task.operation_id.
- WorkerRun 1:N ReadinessEvaluation; у каждого запуска может быть несколько evaluations, но ровно одна evaluation привязана как `started_with_readiness_evaluation_id` при фактическом старте.
- Operation 1:N OperationEvent; WorkerRun 1:N WorkerRunEvent.
- Domain event 1:1 Outbox message (для каждого публикуемого события).
- Consumer 1:N Inbox messages; уникальность `(consumer_name, event_id)`.
- WorkerRun lineage: `derived_from_worker_run_id` self-FK в рамках той же Operation/Task либо по явно разрешённой политике cross-task derivation; причина хранится в `derivation_reason`.

Child Operation — самостоятельная сущность с `parent_operation_id`. Fan-out через Tasks/WorkerRuns не создаёт Child Operation автоматически.

## 5. Таблицы и поля

### 5.1 `operations.operations`

Ключевые поля:
- `id UUID PK`;
- `organization_id`, `project_id`, `parent_operation_id`;
- `operation_type`, `status`;
- `initiator_type`, `initiator_id`;
- `idempotency_scope`, `request_fingerprint`;
- `completion_policy_version`, `completion_policy_snapshot JSONB`;
- `correlation_id`, `causation_id`;
- `workflow_id`, `workflow_run_id` nullable references;
- `progress_version`, `progress_snapshot JSONB`;
- `result_ref`, `problem_ref`;
- `cancel_requested_at`, `started_at`, `completed_at`;
- `row_version BIGINT`, `last_event_sequence BIGINT`;
- `created_at`, `updated_at`.

`idempotency_key` в открытом виде в Operation не хранить; хранить в `platform.idempotency_records` в виде HMAC/digest по ключу с tenant scope. `request_fingerprint` — SHA-256 канонизированного нормализованного запроса.

### 5.2 `work.tasks`

Для MVP добавить `operation_id UUID NOT NULL` после backfill. Составной `UNIQUE(operation_id, id)` нужен для FK из WorkerRun. Task остаётся отдельной доменной сущностью и не заменяется Operation.

### 5.3 `agents.worker_runs`

Ключевые поля:
- `id`, `organization_id`, `project_id`, `operation_id`, `task_id`;
- `worker_definition_version_id`;
- `status`;
- `derived_from_worker_run_id`, `derivation_reason`, `attempt_number`;
- `context_package_version_id`;
- `latest_readiness_evaluation_id`;
- `started_with_readiness_evaluation_id`;
- `workflow_id`, `workflow_run_id`;
- `input_contract_version`, `output_contract_version`;
- `execution_envelope_ref`, `result_ref`, `problem_ref`;
- `started_at`, `finished_at`, `deadline_at`;
- `row_version`, `last_event_sequence`;
- audit timestamps/actor.

`started_with_readiness_evaluation_id` immutable after start. `latest_readiness_evaluation_id` может обновляться при повторной Gate evaluation до старта; после старта историческая связь не переписывает `started_with...`.

### 5.4 Event history

`operations.operation_events` и `agents.worker_run_events`:
- `event_id UUID PK`;
- aggregate ID + `aggregate_sequence`;
- `aggregate_version`;
- `event_type`, `schema_version`;
- CloudEvents attributes (`source`, `subject`, `occurred_at`, `correlation_id`, `causation_id`);
- `actor_type`, `actor_id`;
- `reason_code`, `from_status`, `to_status`;
- `data JSONB`;
- `created_at`.

Уникальность `(aggregate_id, aggregate_sequence)`. Событие immutable: UPDATE/DELETE запрещены правами DB role и, дополнительно, trigger policy в production.

### 5.5 Outbox

`audit.outbox_events`:
- `event_id UUID PK` (совпадает с domain event ID);
- `aggregate_type`, `aggregate_id`, `aggregate_sequence`;
- `destination`, `event_type`, `schema_version`;
- `envelope JSONB`;
- `status` (`PENDING`, `IN_FLIGHT`, `PUBLISHED`, `QUARANTINED`);
- `available_at`, `attempt_count`, `last_error_code`;
- `lease_owner`, `lease_until`;
- `created_at`, `published_at`.

Payload сохраняется как envelope, но без секретов/неограниченных содержимых. Публикация в несколько независимых destinations моделируется отдельной строкой на destination с уникальностью `(event_id, destination)`; event history остаётся одна.

### 5.6 Inbox

`audit.inbox_messages`:
- `consumer_name`, `event_id`, `aggregate_type`, `aggregate_id`, `aggregate_sequence`;
- `status` (`PROCESSING`, `PROCESSED`, `QUARANTINED`);
- `received_at`, `processed_at`, `error_code`, `payload_hash`.

Уникальность `(consumer_name, event_id)`. Inbox запись и эффект локального consumer handler фиксируются в одной транзакции. Для внешнего side effect consumer сначала создаёт собственный outbox command, а не вызывает внешний API до commit.

### 5.7 Idempotency

`platform.idempotency_records`:
- `id`, `scope_type`, `scope_id`, `key_digest`, `request_fingerprint`;
- `resource_type`, `resource_id`;
- `status` (`IN_PROGRESS`, `COMPLETED`, `REJECTED`);
- `response_status`, `response_body_ref`;
- `created_at`, `expires_at`, `completed_at`.

Уникальность `(scope_type, scope_id, key_digest)`. Один и тот же ключ + fingerprint возвращает исходный resource/response; тот же ключ с другим fingerprint → `IDEMPOTENCY_KEY_REUSED`. Срок хранения должен покрывать retry horizon и contractual client retry window; истечение не должно приводить к повторному выполнению уже существующей активной операции.

## 6. Ключевые ограничения целостности

1. `worker_runs(operation_id, task_id)` → `work.tasks(operation_id, id)`.
2. `operation_events(operation_id, aggregate_sequence)` unique.
3. `worker_run_events(worker_run_id, aggregate_sequence)` unique.
4. `outbox_events(event_id, destination)` unique.
5. `inbox_messages(consumer_name, event_id)` unique.
6. `idempotency_records(scope_type, scope_id, key_digest)` unique.
7. `worker_runs.derived_from_worker_run_id` не может ссылаться на себя; lineage cycle detection выполняется domain service.
8. Terminal Operation/WorkerRun не возвращаются в non-terminal state; trigger может быть дополнительной защитой, но canonical validation — domain service + conditional update.
9. `row_version` увеличивается ровно на 1 при каждом изменении mutable projection.
10. `last_event_sequence` увеличивается ровно на число event records, вставленных в той же транзакции.
11. Для started WorkerRun `started_with_readiness_evaluation_id` NOT NULL; FK должен вести к evaluation того же WorkerRun, outcome READY/READY_WITH_LIMITATIONS, status COMPLETED.
12. ReadinessEvaluation immutable; check results immutable после completion.

## 7. Индексы

Минимум:
- `operations(project_id, created_at DESC)`;
- partial `operations(status, updated_at)` для non-terminal states;
- `operations(parent_operation_id)`;
- `work.tasks(operation_id, status, priority)`;
- `agents.worker_runs(operation_id, created_at DESC)`;
- `agents.worker_runs(task_id, created_at DESC)`;
- partial queue index `agents.worker_runs(status, created_at)` для schedulable statuses;
- `agents.worker_runs(derived_from_worker_run_id)`;
- events `(aggregate_id, aggregate_sequence)` unique и `(aggregate_id, occurred_at)`;
- outbox partial `(available_at, created_at)` WHERE status IN PENDING/IN_FLIGHT;
- outbox `(aggregate_type, aggregate_id, aggregate_sequence, destination)`;
- inbox `(consumer_name, status, received_at)`;
- idempotency unique scope/key digest и `expires_at` cleanup index;
- ReadinessEvaluation `(worker_run_id, created_at DESC)`.

Не вводить partitioning, sharding и BRIN до измерения фактического объёма/плана запросов. Event tables можно партиционировать позже, но только после проектирования FK/unique constraints и retention.

## 8. Транзакционные алгоритмы

### TX-01 Create Operation (idempotent)

1. API проверяет authentication, organization/project ACL, Policy и command schema.
2. Канонизирует запрос и вычисляет `request_fingerprint`; вычисляет `key_digest` через keyed HMAC, не сохраняет raw idempotency key.
3. Начинает транзакцию.
4. Пытается вставить `idempotency_records` со статусом IN_PROGRESS. При конфликте блокирует существующую запись:
   - fingerprint совпадает и resource существует → вернуть исходную Operation;
   - fingerprint отличается → rollback и `IDEMPOTENCY_KEY_REUSED`;
   - IN_PROGRESS → вернуть безопасный retryable conflict / await policy, не создавать вторую Operation.
5. Создаёт Operation `ACCEPTED`, `row_version=1`, `last_event_sequence=1`.
6. Вставляет `operation.accepted` sequence=1 и Outbox message.
7. Связывает idempotency record с Operation и переводит в COMPLETED.
8. Commit; только после commit API возвращает Operation ID.

Operation и outbox никогда не создаются раздельно.

### TX-02 Transition aggregate

1. Начать короткую транзакцию.
2. `SELECT ... FOR UPDATE` aggregate row либо выполнить compare-and-swap `UPDATE ... WHERE id=:id AND row_version=:expected`.
3. Проверить текущий status, allowed transition, actor, policy, scope и preconditions.
4. При недопустимом переходе вернуть typed domain conflict; не писать событие.
5. Обновить projection, `row_version=row_version+1`, timestamps.
6. Выделить `aggregate_sequence` из `last_event_sequence+1` под той же блокировкой; обновить last sequence.
7. Вставить event history и Outbox envelope с теми же event_id/sequence.
8. Commit.
9. Конкурентный loser перечитывает актуальное состояние; не повторяет мутацию вслепую.

### TX-03 Create Task / WorkerRun

- Создание Task: проверить Operation non-terminal, policy разрешает добавление work item на текущей фазе, dependency graph не образует цикл; вставить Task с operation_id и событие Task (вне scope данного event catalogue).
- Создание WorkerRun: проверить Task.operation_id, Task допускает исполнение, Operation активна, WorkerDefinition version существует, immutable ContextPackageVersion привязан, derivation lineage валиден; создать WorkerRun `CREATED`, `row_version=1`, sequence=1; вставить `worker_run.created` + Outbox в одной транзакции.
- Для каждой содержательной попытки создаётся новый WorkerRun. Temporal Activity retry не создаёт новый WorkerRun.

### TX-04 Gate completion and final start revalidation

1. Gate Evaluator создаёт immutable ReadinessEvaluation и check rows.
2. В транзакции завершения evaluation обновить evaluation status/outcome, worker_run.latest_readiness_evaluation_id, event `worker_run.gate_evaluation_completed` + Outbox.
3. Если outcome BLOCKED/STALE/EVALUATOR_ERROR — запуск не dispatch.
4. Для READY/READY_WITH_LIMITATIONS выполнить отдельную финальную pre-start revalidation непосредственно перед scheduling boundary: row versions, context manifest/hash, grants/revocations/expiry, tool allowlist, policy/ruleset, output contract, budgets, dependencies, approvals.
5. В одной транзакции проверить worker_run still eligible and evaluation still current; создать dispatch intent/Outbox, перевести WorkerRun в QUEUED, зафиксировать `worker_run.queued`.
6. Перед фактическим start Runtime повторно authorizes every tool call; Gate не является permission token.
7. После подтверждения фактического старта в отдельной транзакции зафиксировать STARTING/RUNNING согласно принятой state machine, `started_with_readiness_evaluation_id` и `worker_run.started`.
8. Если условия изменились между revalidation и start, abort dispatch, создать новую evaluation; не использовать stale grant snapshot.

### TX-05 Outbox dispatcher

1. Выбрать доступные строки с `FOR UPDATE SKIP LOCKED`, где `available_at <= now()` и lease отсутствует/истёк.
2. Назначить lease и commit короткую транзакцию.
3. Отправить событие во внешний transport после commit.
4. При подтверждении — отдельной транзакцией пометить PUBLISHED.
5. При ошибке — увеличить attempt_count, вычислить bounded exponential backoff + jitter, записать безопасный error_code.
6. После лимита попыток — QUARANTINED + alert; ручной replay создаёт новую delivery attempt, но не новое доменное событие.
7. Для одного aggregate/destination не отправлять sequence N+1, пока N не опубликовано или не переведено в явно разрешённый quarantine/manual resolution. Соседние aggregates могут публиковаться параллельно.

### TX-06 Inbox consumer

1. Начать транзакцию.
2. Вставить `(consumer_name,event_id)` со статусом PROCESSING `ON CONFLICT DO NOTHING`.
3. Если запись уже PROCESSED — commit no-op.
4. Если event sequence не ожидаемая — сохранить как pending/gap либо quarantine; не применять out-of-order aggregate transition.
5. Выполнить локальный handler effect в той же транзакции; записать checkpoint/processed sequence.
6. Пометить PROCESSED; commit.
7. Внешний side effect оформлять через consumer-owned Outbox.

### TX-07 Cancel Operation / WorkerRun

1. Проверить permission и идемпотентность команды.
2. Перевести aggregate в `CANCEL_REQUESTED` (для Operation) или соответствующее состояние cancellation request по WorkerRun contract; создать event + Outbox.
3. После commit послать Temporal cancellation request через dispatcher/activity.
4. Не маркировать CANCELLED по факту отправки cancel.
5. Дождаться фактического workflow/worker outcome, проверить незавершённые Activities и внешние side effects, выполнить compensation если предусмотрено контрактом.
6. Reconciliation определяет итог `CANCELLED`, `SUCCEEDED`, `PARTIALLY_SUCCEEDED` или `FAILED` согласно фактически совершённым действиям.
7. Terminal state фиксируется отдельной доменной транзакцией и событием.

### TX-08 Operation aggregation

- Aggregator запускается после релевантных Task/WorkerRun/Review/Approval/Dependency events и при recovery sweep.
- Читает согласованный snapshot Tasks, dependencies, completion policy и relevant WorkerRuns.
- Блокирует Operation row / применяет optimistic version.
- Определяет, есть ли executable branch, blocker, recovery path, required task failure, valid partial result.
- Переходы Operation выполняются только через Operation domain service.
- Если остаётся хоть одна обязательная незавершённая работа, Operation не terminal.
- `SUCCEEDED` — все обязательные критерии выполнены и контракт допускает итог.
- `PARTIALLY_SUCCEEDED` — контракт допускает partial и есть завершённый пригодный результат при невыполненных/failed optional или разрешённых partial branches.
- `FAILED` — обязательный критерий не выполнен и допустимого recovery/partial path нет.
- `WAITING_FOR_HUMAN` / `WAITING_FOR_DEPENDENCY` устанавливаются только если blocker глобально блокирует все допустимые пути прогресса.
- Итог фиксируется вместе с Operation event + Outbox.

### TX-09 Recovery / reconciliation

Периодический reconciler находит:
- Operation non-terminal без ожидаемого Outbox/Temporal Workflow;
- WorkerRun QUEUED/STARTING/RUNNING с несогласованными Temporal refs;
- expired Outbox leases;
- Inbox gaps/quarantine;
- Temporal workflow завершён, но доменная проекция не терминальна;
- доменная сущность terminal, но workflow продолжает исполняться.

Reconciler не переписывает историю и не угадывает результат. Он получает authoritative facts из Temporal и внешних систем, сверяет доменные preconditions, создаёт новое корректирующее событие или incident/quarantine. Все recovery actions идемпотентны и аудируются.

## 9. Concurrency и порядок блокировок

1. Не держать DB transaction открытой во время LLM call, Temporal RPC, HTTP/tool call или ожидания человека.
2. Стандартный порядок блокировок для multi-row operations: Operation → Task (по UUID ascending) → WorkerRun (по UUID ascending) → event/outbox rows. Единый порядок снижает deadlock risk.
3. Outbox dispatcher не держит lock во время network publish.
4. `SKIP LOCKED` используется только для queue claiming, не для проверки доменных инвариантов.
5. Sequence нельзя выдавать через `MAX(sequence)+1`; только aggregate row counter под lock/CAS.
6. Для агрегатных мутаций retry выполняется на уровне команды с повторным чтением состояния и проверкой idempotency.
7. DB deadlock/serialization failures повторяются ограниченное число раз с jitter, но только для транзакций без внешних side effects.

## 10. Роли и безопасность PostgreSQL

Рекомендуемые роли:
- `aires_migrator` — DDL/migrations, недоступна runtime;
- `aires_api` — execute domain service procedures / ограниченный DML;
- `aires_manager_runtime` — минимальные операции через backend service; без unrestricted domain writes;
- `aires_worker_runtime` — нет прямого write доступа к Operation/Task/WorkerRun/Event/Outbox;
- `aires_outbox_dispatcher` — select/lease/update delivery status в Outbox;
- `aires_event_consumer` — Inbox + разрешённые consumer-owned writes;
- `aires_audit_writer` — insert-only AuditEvent;
- `aires_readonly_observability` — ограниченные агрегированные метрики, без payload/evidence.

RLS может быть defense-in-depth, но не заменяет application authorization. Сервисные роли не получают `BYPASSRLS`. Secrets не сохраняются в DB payload.

## 11. Миграционная стратегия

- Версионирование миграций — один инструмент для `ai_res_db`; конкретный инструмент фиксируется Infrastructure/Implementation Spec до реализации.
- Миграции expand → backfill → validate → enforce → contract.
- Для `work.tasks.operation_id NOT NULL`: сначала nullable column + backfill для существующих Task; создать/назначить owning Operation по migration mapping; проверить orphan=0; затем NOT NULL и composite unique.
- WorkerRun `operation_id` backfill через Task.operation_id; проверить mismatch=0; добавить composite FK.
- Создать event tables, Outbox/Inbox/idempotency, indexes concurrently там, где это применимо.
- Не создавать FK в `temporal_db`.
- Migration transaction mode выбирать с учётом PostgreSQL операций, требующих вне-транзакционного выполнения (`CREATE INDEX CONCURRENTLY`).
- Destructive migration запрещена без backup, restore test, explicit approval и rollback/forward-fix plan.
- Schema version записывать в migration history и Release Manifest.

## 12. Обязательные тесты

### Unit/domain
- Полная таблица разрешённых/запрещённых переходов Operation и WorkerRun.
- Terminal immutability.
- Operation aggregation для success/partial/failure/wait/cancel.
- Derivation reason и lineage cycle.
- Gate snapshot immutability и `started_with` immutability.

### PostgreSQL integration
- Два параллельных перехода одного aggregate: только один CAS победитель.
- Два параллельных CreateOperation с одинаковым idempotency key/fingerprint: одна Operation.
- Одинаковый ключ, разный fingerprint: `IDEMPOTENCY_KEY_REUSED`.
- Concurrent aggregate event sequence: нет дубликатов/пропусков.
- Crash после DB commit до publish: Outbox доставляет после restart.
- Crash после publish до mark PUBLISHED: consumer дедуплицирует redelivery.
- Inbox consumer crash до commit: handler effect не дублируется.
- WorkerRun FK не допускает Task другой Operation.
- Started WorkerRun без valid readiness evaluation невозможен.
- Outbox sequence N+1 не обгоняет N в пределах aggregate/destination.
- Quarantine и controlled replay.
- Deadlock/lock timeout bounded retry.

### Temporal/recovery
- DB commit до Temporal start; dispatcher crash; restart.
- Temporal workflow started, но API потерял response.
- Temporal завершился, доменный event не записан.
- Cancellation race: workflow success против cancel request.
- Activity retry не создаёт новый WorkerRun.
- Reconciler не создаёт повторные terminal events.

## 13. Нерешённые параметры (не блокируют логическую модель, но обязательны перед production)

1. Конкретный migration tool и ORM/query layer.
2. HMAC key management/rotation для idempotency key digest.
3. Точные retention periods для event history, Outbox, Inbox, idempotency и Audit.
4. Outbox lease duration, retry schedule и quarantine thresholds — определить измерениями и нагрузочными тестами.
5. Конкретный transport для межпроцессной доставки; MVP может использовать PostgreSQL-backed dispatcher.
6. Набор существующих таблиц и миграционный mapping legacy Tasks/WorkerRuns к Operation.
7. Политика partitioning/archival после volume benchmark.
8. Точные DB grants/процедуры и применение RLS после Security Owner review.

## 14. Ограничения доказательности

Документ и SQL DDL описывают целевую конструкцию. Они не доказывают, что миграции уже применимы к фактической БД или что алгоритмы выдерживают реальные concurrency/crash сценарии. До implementation acceptance требуются PostgreSQL integration tests, Temporal integration tests, restore/recovery drills и security review.

## 15. Связанные нормативные документы

- `AI_RES_Domain_Model_and_Data_Architecture_v1.6.md`
- `AI_RES_Process_Design_and_Algorithms_v1.6.md`
- `AI_RES_Operation_WorkerRun_Event_Model_v1.0.md`
- `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.4.md`
- `AI_RES_API_and_Interaction_Contracts_v1.7.md`
- `AI_RES_Domain_Events_AsyncAPI_v1.5.yaml`
- `AI_RES_Claude_Code_Implementation_Spec_v1.17.md`
- `AI_RES_Document_Registry_v3.6.md`


---

## Дополнение 1.1 — Migration strategy и access controls

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.

DDL v1.0 сохраняется как design snapshot, не production migration. Перед эксплуатацией его необходимо разложить на Alembic revisions, учесть существующие схемы и выполнить legacy mapping/backfill для `work.tasks.operation_id`. См. Migration Strategy v1.0 и Roles/RLS SQL reference v1.0.


## Дополнение v1.2 — Persistence Implementation Blueprint

Физическая модель дополняется реализационным Blueprint v1.0: Alembic revision chain PDB-0001..PDB-0010, SQLAlchemy Unit of Work, explicit transaction ownership, schema allowlist, migration job isolation, resumable Task backfill, RLS/grants acceptance и PostgreSQL integration test matrix PERSIST-001..024.

Текущий DDL v1.0 остаётся design reference, а не автоматически применяемой миграцией. Перед генерацией revisions требуется repository/schema reconnaissance, сопоставление существующих таблиц и constraints, проверка owner/privileges и безопасный expand/contract план.
