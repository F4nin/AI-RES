# AI RES — Архитектурное решение: Operation и Readiness Gate

**Версия:** 1.6  
**Дата:** 2026-11-10  
**Статус:** BASELINED — архитектурная основа подтверждена владельцем проекта 2026-11-10  
**Область:** доменная модель, durable orchestration, API, события, безопасность, восстановление.

## 1. Цель решения

Зафиксировать каноническое представление длительных действий AI RES и обязательного допуска WorkerRun к исполнению. Решение закрывает архитектурные вопросы PRE-009 и PRE-011 из Cross-Document Consistency Audit на уровне выбранной модели владения, хранения и lifecycle. Контрактная синхронизация и детализация реализации продолжаются отдельно; закрытие архитектурного решения не означает runtime-реализацию или прохождение эксплуатационных тестов.

## 2. Решение по Operation

### 2.1. Назначение и источник истины

`Operation` — доменная сущность, представляющая инициированное пользователем или системой длительное действие, за которым клиент может наблюдать независимо от HTTP-запроса и состояния конкретного процесса Runtime.

**Каноническое доменное состояние Operation хранится в PostgreSQL `ai_res_db`, schema `operations`.** Temporal является источником истины для технического состояния и истории исполнения Workflow, но не заменяет доменную Operation и не является публичным API read model.

Следствия:
- API читает Operation из AI RES domain store, а не опрашивает Temporal для каждого запроса.
- Temporal Workflow ID/Run ID — внешние correlation references, не PK Operation.
- Operation сохраняется после завершения/удаления Temporal execution history в соответствии с retention.
- Task/Epic/Artifact/WorkerRun сохраняют собственные lifecycle; Operation не заменяет их.
- Operation может охватывать несколько Task/WorkerRun, но не должна дублировать их статусы.
- Workflow может обслуживать Operation, но технические retry/continue-as-new не создают новую Operation.
- Одна Operation может иметь несколько Workflow Execution attempts, но одновременно только один активный управляющий execution chain, если явно не определён fan-out contract.

### 2.2. Область ответственности

Operation отвечает за:
- принятие и отслеживание длительной команды;
- связь инициатора, области доступа, целевого объекта и корреляции;
- отображаемый lifecycle состояния;
- подтверждённые progress milestones;
- ссылку на результат или Problem Details;
- запрос и подтверждение отмены;
- связь с Temporal execution и причинно-следственными событиями;
- идемпотентное принятие повторных команд.

Operation НЕ отвечает за:
- бизнес-статус Task/Epic/Requirement/Artifact;
- детальное состояние каждого WorkerRun;
- хранение полного вывода модели, документов или prompt;
- исполнение workflow;
- выдачу разрешений;
- подтверждение человеческого решения.

### 2.3. Рекомендуемая модель хранения

PostgreSQL schema `operations`:

**`operations.operations`**
- `id UUID PK`;
- `organization_id`, nullable `project_id`, nullable `epic_id`;
- `operation_type` — controlled enum;
- `status` — controlled enum;
- `initiator_type` (`HUMAN`, `SYSTEM`, `MANAGER`, `SCHEDULED`);
- `initiator_id` — nullable для system actor, обязательно для HUMAN/MANAGER;
- `subject_type`, `subject_id` — типизированная ссылка на основной объект/команду;
- `correlation_id`, `causation_id`;
- `idempotency_scope`, `idempotency_key`, `request_fingerprint`;
- `submitted_at`, `accepted_at`, `started_at`, `completed_at`;
- `last_progress_at`, `last_event_sequence`;
- `result_ref` — typed reference, nullable;
- `problem` — RFC 9457-compatible safe summary, nullable;
- `cancel_requested_at`, `cancel_requested_by`, `cancellation_reason`;
- `temporal_workflow_id`, `temporal_run_id`, `temporal_first_execution_run_id`;
- `row_version`, `created_at`, `updated_at`.

**`operations.operation_events`**
- append-only доменная история переходов и подтверждённых milestones;
- `id`, `operation_id`, `sequence`, `event_type`, `from_status`, `to_status`;
- `occurred_at`, `actor_type`, `actor_id`, `reason_code`;
- `correlation_id`, `causation_id`, `payload_ref`/ограниченный typed payload;
- unique `(operation_id, sequence)`;
- не содержит prompt, secret, полного документа или произвольного LLM-текста.

**`operations.operation_workflow_links`** (если у Operation более одной Workflow Execution)
- `operation_id`, `workflow_id`, `run_id`, `execution_role`, `started_at`, `closed_at`, `status_snapshot`, `attempt_number`;
- уникальность по `(workflow_id, run_id)`;
- один активный `execution_role=PRIMARY` на Operation.

**`operations.operation_idempotency`** может быть отдельной таблицей либо уникальным индексом в operations. Уникальность — в scope authenticated actor/service + operation type + idempotency key. Повтор с тем же fingerprint возвращает ту же Operation; тот же key с другим fingerprint даёт `IDEMPOTENCY_KEY_REUSED`.

Нормативно обязательны Operation и append-only OperationEvent. Таблица workflow links отдельна только если реально поддерживаются множественные Workflow Executions; иначе ссылки могут быть полями Operation с возможностью расширения.

### 2.4. Канонические статусы и переходы

Статусы:
- `ACCEPTED` — команда прошла синтаксическую/авторизационную проверку и Operation записана;
- `QUEUED` — команда надёжно поставлена на запуск/ожидает workflow scheduling;
- `RUNNING` — подтверждено начало исполняемого workflow этапа;
- `WAITING_FOR_HUMAN` — требуется конкретное человеческое решение/действие;
- `WAITING_FOR_DEPENDENCY` — ожидается внешняя или внутренняя зависимость;
- `RETRYING` — система выполняет разрешённую повторную попытку;
- `CANCEL_REQUESTED` — запрос отмены принят, отмена ещё не подтверждена;
- `SUCCEEDED` — целевой результат достигнут;
- `PARTIALLY_SUCCEEDED` — достигнут частичный результат, остаток явно описан;
- `FAILED` — операция завершилась неуспешно после исчерпания/запрета восстановления;
- `CANCELLED` — подтверждённая отмена и завершение контролируемого cleanup/reconciliation.

Терминальные: `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `CANCELLED`.

Допустимые переходы:
- `ACCEPTED → QUEUED | FAILED | CANCELLED`
- `QUEUED → RUNNING | WAITING_FOR_DEPENDENCY | FAILED | CANCEL_REQUESTED | CANCELLED`
- `RUNNING → WAITING_FOR_HUMAN | WAITING_FOR_DEPENDENCY | RETRYING | CANCEL_REQUESTED | SUCCEEDED | PARTIALLY_SUCCEEDED | FAILED`
- `WAITING_FOR_HUMAN → QUEUED | RUNNING | CANCEL_REQUESTED | FAILED | CANCELLED`
- `WAITING_FOR_DEPENDENCY → QUEUED | RUNNING | RETRYING | CANCEL_REQUESTED | FAILED | CANCELLED`
- `RETRYING → QUEUED | RUNNING | WAITING_FOR_DEPENDENCY | FAILED | CANCEL_REQUESTED | CANCELLED`
- `CANCEL_REQUESTED → CANCELLED | SUCCEEDED | PARTIALLY_SUCCEEDED | FAILED`

Последняя строка намеренная: гонка отмены с уже завершившимся внешним действием может привести к фактическому success/partial success. Система обязана сообщить фактический результат, а не ложно объявить CANCELLED. Запрос отмены не гарантирует компенсацию уже выполненного внешнего действия.

Повторное открытие terminal Operation запрещено. Новый запуск/rework создаёт новую Operation или отдельную дочернюю Operation, связанную `parent_operation_id`; конкретная политика определяется типом команды. Исправление/повтор WorkerRun внутри одной ещё активной Operation допускается, если это одна исходная команда и lifecycle не завершён.

### 2.5. Создание и связь с Temporal

1. API/application service выполняет authentication, authorization, validation, idempotency check.
2. В одной транзакции `ai_res_db` создаёт Operation со статусом `ACCEPTED` и Outbox command/event.
3. Ответ API — `202 Accepted`, `Location` на Operation. Внутренний dispatcher читает Outbox и запускает Temporal Workflow с детерминированным Workflow ID, основанным на Operation ID.
4. Повторная доставка Outbox безопасна: старт Workflow идемпотентен; существующий Workflow ID проверяется и связывается с Operation.
5. После подтверждения scheduling Operation переводится в `QUEUED`; после подтверждённого старта — в `RUNNING`.
6. Workflow/Activities сообщают domain outcomes через доверенные application services. Только они меняют Operation и пишут OperationEvent/Outbox в одной доменной транзакции.
7. Temporal status не копируется вслепую: перевод статуса требует сопоставления с доменным событием/результатом и проверки версии Operation.
8. Reconciliation job сравнивает активные Operation с Temporal executions и Outbox. Расхождения исправляются идемпотентно, неоднозначные внешние side effects — через human escalation.

Запрещено делать dual-write «сначала Temporal, затем PostgreSQL» без outbox/reconciliation. PostgreSQL Operation + Outbox — точка надёжного принятия команды.

### 2.6. API и безопасность

Публичные операции:
- `GET /api/v1/operations/{operationId}` — read model;
- `POST /api/v1/operations/{operationId}/cancel` — request cancellation; не обещает немедленное завершение;
- команды, запускающие длительный процесс, возвращают `202` и `operationId`.

Опционально `GET /operations/{id}/events` не включать в MVP без подтверждённой потребности; проектный SSE канал может использоваться для уведомлений, а REST snapshot остаётся источником истины.

Каждый запрос проверяет ACL по organization/project/subject. Нельзя раскрывать существование чужой Operation; применяется controlled 404 согласно IAM policy. Системные/Manager операции используют service identity, а не подменяют инициатора человеком. Cancel требует отдельного permission и аудита. Operation не предоставляет клиенту прямое управление Temporal.

### 2.7. Retention

- Активные Operation не удаляются.
- Terminal Operation и OperationEvent сохраняются по политике audit/operational retention.
- Рекомендуемая исходная политика MVP: хранить доменную запись и историю переходов бессрочно в пределах жизненного цикла проекта, пока не утверждена отдельная retention policy; большие payload/result хранятся отдельно и по своим правилам.
- Temporal Workflow history retention независим от Operation retention.
- Удаление/анонимизация персональных данных не должно разрушать audit invariants; применяется отдельная legal/privacy procedure.

## 3. Решение по Readiness Gate

### 3.1. Назначение

Readiness Gate — платформенная контрольная точка допуска одного конкретного WorkerRun к запуску. Она не является LLM-оценкой «в целом задача готова» и не является только Activity в Temporal.

Каждая попытка запуска WorkerRun должна ссылаться на сохранённую успешную оценку допуска, которая проверяет точные версии и разрешения.

### 3.2. Канонические сущности

Рекомендуемая схема PostgreSQL `execution` (логический модуль Backend; физическое размещение допускается в `agents`/`governance`, но ownership должен быть единым):

**`execution.readiness_evaluations`** — immutable evaluation record:
- `id`, `organization_id`, `project_id`, `epic_id`, `task_id`, `worker_run_id`;
- `evaluation_number` (монотонный в пределах WorkerRun);
- `outcome`: `READY`, `READY_WITH_LIMITATIONS`, `BLOCKED`, `STALE`;
- `evaluation_status`: `COMPLETED`, `EVALUATOR_ERROR`;
- `evaluated_at`, `evaluator_version`, `policy_engine_version`;
- `task_id + task_row_version` / relevant task version;
- `plan_version_id`, `plan_item_id`, `plan_version_hash`;
- `worker_definition_id`, `worker_definition_version`;
- `context_package_version_id`, `context_manifest_hash`;
- `ruleset_version`, `policy_snapshot_ref`;
- `grant_set_version/hash`, `tool_registry_version/hash`, `tool_allowlist_hash`;
- `output_contract_version/hash`;
- `budget_profile_version/hash`;
- `dependency_snapshot_hash`;
- `manager_assessment_ref` (если semantic assessment required);
- `checks_summary`, `limitations`, `blockers`, `evidence_refs`;
- `snapshot_hash`, `row_version` (immutable record version = 1).

**`execution.readiness_check_results`** — детальные результаты отдельных обязательных/условных проверок:
- `id`, `readiness_evaluation_id`, `check_code`, `check_category`;
- `result` (`PASS`, `FAIL`, `WARN`, `NOT_APPLICABLE`);
- `severity` (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`);
- `reason_code`, safe `message`, `evidence_refs`, `evaluated_at`;
- `required` boolean, `check_version`.

Оценка и её check results неизменяемы. Если состояние изменилось, создаётся новая evaluation, а предыдущая помечается логически устаревшей только через отдельное событие/ссылку supersession; содержимое старой записи не обновляется.

`GateResult` — термин из контрактов/процессов, не отдельная конкурирующая сущность: это API/domain projection над `ReadinessEvaluation` + `ReadinessCheckResult[]`. Стабильное имя сущности хранения — `ReadinessEvaluation`; `gateResultId` в текущих событиях следует трактовать как ID этой записи и затем переименовать в `readinessEvaluationId` при следующей breaking-safe версии event schema. Не создавать две таблицы `gate_results` и `readiness_evaluations`.

### 3.3. Обязательные проверки

Группы:
1. Task/goal: Task существует, активна, scope достаточен для роли; нет запрещающего статуса.
2. Plan: применимая PlanVersion существует; PlanItem разрешён/утверждён; predecessor dependencies выполнены.
3. Worker capability: WorkerDefinition активна; capability и contract version совместимы.
4. Context: ContextPackageVersion существует, immutable, относится к правильному проекту/задаче; все refs разрешены ACL; обязательные источники доступны и версии совпадают.
5. Governance/rules: system/org/project rules разрешены и версии зафиксированы; нет запрещающего конфликта.
6. Permissions: grant активен, scope соответствует project/task/run, срок не истёк; tool allowlist разрешён; секреты не наследуются.
7. Output contract: схема результата зарегистрирована и поддерживается.
8. Budget: time/token/cost/tool/concurrency budgets определены и не превышают policy limits.
9. Dependencies: обязательные predecessor/approval/review/source readiness условия выполнены.
10. Semantic readiness: Manager assessment требуется по классу задачи; если требуется, assessment должен быть явным, привязанным к evidence и иметь outcome `READY`/`NEEDS_CLARIFICATION`/`NOT_READY`. LLM не может override deterministic/security/policy failure.
11. Runtime capability: допустимая модель/провайдер и необходимые инструменты доступны по разрешённой конфигурации.

### 3.4. Объединение результатов

- Любой обязательный `FAIL` с severity HIGH/CRITICAL → `BLOCKED`.
- Любой недоступный Policy Engine / неизвестный статус grant / невозможность подтвердить ACL → `BLOCKED` (fail-closed).
- `READY_WITH_LIMITATIONS` допустим только при отсутствии обязательных FAIL и при наличии явного списка ограничений, которые могут быть технически enforced в WorkerRun envelope/grants/budgets.
- `WARN` сам по себе не разрешает обход policy; результат зависит от check.required и severity.
- `STALE` — не оценка качества и не «почти готово»: фиксирует, что snapshot больше не соответствует актуальному состоянию. Перед запуском требуется новая evaluation.
- Ошибка evaluator не равна READY; `evaluation_status=EVALUATOR_ERROR`, WorkerRun не стартует.
- `READY` и `READY_WITH_LIMITATIONS` — единственные outcomes, разрешающие переход к финальной pre-start revalidation; не дают безусловного права на запуск.

### 3.5. TOCTOU и финальная revalidation

Критический риск — изменение прав/контекста между Gate и фактическим запуском.

Перед dispatch WorkerRun выполняется короткая финальная revalidation:
- проверяются текущие row/version counters для Task/Plan/WorkerDefinition;
- ContextPackageVersion и manifest hash не изменились;
- grant не отозван/не истёк; Policy Engine доступен;
- tool allowlist, ruleset и output contract совместимы;
- dependencies/approvals не изменились.

Если что-либо изменилось — текущая evaluation получает отдельное superseded/stale event, создаётся новая evaluation. Старый GateResult не используется. Revalidation и запуск связываются с защищённой командой/lease; lease ограничен коротким сроком и не заменяет per-tool-call authorization. Каждый tool call повторно проверяется Policy Engine.

Не обещать абсолютную атомарность между PostgreSQL, Policy Engine, Temporal и внешним провайдером. Гарантия: не запускать Worker при известном stale/denied gate; при гонке после dispatch права повторно проверяются на каждом действии, а Run может быть остановлен/заблокирован.

### 3.6. Связь с WorkerRun и Temporal

- WorkerRun создаётся как доменная запись до исполнения (или как подготовленная запись с состоянием `PENDING_GATE`).
- Каждая попытка запуска получает новую ReadinessEvaluation.
- WorkerRun хранит `latest_readiness_evaluation_id` как удобный pointer и `started_with_readiness_evaluation_id` как immutable reference.
- Run может иметь несколько Gate evaluations (blocked → fixed → ready; stale → reevaluated).
- Temporal Workflow не должен стартовать до успешной финальной revalidation.
- Gate Evaluation может выполняться как Activity/Backend application service, но результат и checks сохраняются в `ai_res_db`.
- Temporal history содержит только IDs, compact decisions и references; не копирует все evidence/payload.
- Gate result is not human approval. Если требуется human approval, Gate проверяет наличие действующей Approval на точную версию.

### 3.7. Инвалидация и supersession

Создание новой evaluation требуется при изменении любого влияющего фактора:
- Task scope/status/row_version;
- PlanVersion/PlanItem/approval;
- WorkerDefinition/capabilities;
- ContextPackageVersion/manifest;
- rules/policy/grants/tool registry/allowlist;
- output contract;
- budgets;
- dependencies и обязательные upstream outcomes;
- semantic assessment, если он required.

Изменение Source не инвалидирует пакет автоматически, если текущий WorkerRun использует immutable ContextPackageVersion. Оно может инициировать новую ContextPackageVersion и новый Gate только когда Manager/impact process решил, что текущая работа должна учитывать изменение.

### 3.8. Retention и ACL

- ReadinessEvaluation и CheckResults сохраняются как audit evidence не менее срока жизни связанного WorkerRun/Task; рекомендуемое MVP правило — сохранять вместе с историей WorkerRun.
- Evidence refs подчиняются ACL исходных объектов; gate summary не должен раскрывать скрытый контент.
- Worker не может читать чужие gate details, менять outcome или создавать grant.
- API пользователя показывает безопасную причину блокировки и доступные действия, не раскрывая секреты, внутренние policy rules и скрытые source content.
- Gate evaluation records immutable; retention cleanup не удаляет записи, на которые ссылаются WorkerRun/AuditEvent.

## 4. Разделение ответственности

| Компонент | Operation | Readiness Gate |
|---|---|---|
| API/Application Services | создаёт и читает Operation, принимает cancel | принимает запрос/отдаёт безопасный статус, не решает policy |
| Manager | инициирует цель и выбирает workflow | semantic assessment и достаточность задачи |
| Context Builder | не владеет Operation | собирает immutable ContextPackageVersion |
| Policy & Permission Engine | authorizes command/cancel | independently validates grants/ACL/tools |
| Gate Evaluator | не управляет Operation lifecycle | выполняет deterministic checks и сохраняет evaluation |
| Temporal | durable execution и signals | запускает workflow только после successful Gate |
| Worker Runtime | исполняет связанный Run | не может менять Gate outcome или обходить Gate |
| PostgreSQL `ai_res_db` | canonical Operation state/history | canonical immutable evaluation/check results |
| Outbox/dispatcher | надёжная публикация команд/событий | публикация gate completed/stale/blocked facts |

## 5. Набор обязательных инвариантов

1. Нельзя запустить WorkerRun без `started_with_readiness_evaluation_id`.
2. Evaluation outcome должен быть `READY` или `READY_WITH_LIMITATIONS`, evaluation_status `COMPLETED`.
3. Нельзя использовать Gate Evaluation с несовпадающими version/hash refs.
4. Нельзя трактовать `READY_WITH_LIMITATIONS` как READY без применения ограничений.
5. Нельзя изменить сохранённую evaluation; только создать новую.
6. Нельзя выдать Gate разрешение на действие, запрещённое Policy Engine.
7. Нельзя считать Temporal Workflow status источником доменного Operation status.
8. Нельзя менять Operation status без валидного transition, actor и audit/event.
9. Cancel request не равен confirmed cancellation.
10. Результат внешнего side effect при cancel/retry должен reconciliation-иться; exactly-once не обещается.
11. Operation и Gate не содержат full prompt/secrets/raw source payload.
12. Доступ к Operation/Gate проверяется по project/organization ACL.

## 6. Открытые решения, которые остаются PROPOSED

- Утвердить физическое имя schema: `operations` и `execution` либо поместить evaluation в `agents`; рекомендация — `operations` + `execution`.
- Утвердить срок retention по юридическим/организационным правилам; до этого не вводить автоматическое удаление.
- Утвердить точные `operation_type` enum и `check_code` registry при подготовке API/implementation slices.
- Утвердить короткий dispatch lease duration и concrete revalidation transaction strategy при выборе Backend stack.
- Утвердить, нужен ли отдельный public endpoint для списка evaluations, или MVP ограничивается безопасным read model внутри WorkerRun detail.
- Утвердить semantic assessment schema и task-class policy.
- Утвердить точные статусы WorkerRun и связь с Operation в едином lifecycle catalogue.

## 7. Связанные документы

- `AI_RES_Domain_Model_and_Data_Architecture_v1.3.md`
- `AI_RES_Process_Design_and_Algorithms_v1.3.md`
- `AI_RES_API_and_Interaction_Contracts_v1.4.md`
- `AI_RES_Public_API_v1.2.yaml`
- `AI_RES_Domain_Events_AsyncAPI_v1.3.yaml`
- `AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json`
- `AI_RES_Claude_Code_Implementation_Spec_v1.13.md`
- `AI_RES_Document_Registry_v3.0.md`


## 13. Подтверждение архитектурного решения — 2026-11-10

Владелец проекта подтвердил предложенную архитектуру Operation и Readiness Gate. Статус документа изменён с `PROPOSED` на `BASELINED`. Подтверждены архитектурные принципы и обязательные инварианты, изложенные в разделах 2–12, включая доменное владение Operation, разделение Operation/Temporal, атомарный Outbox, append-only OperationEvent, неизменяемые ReadinessEvaluation, обязательную проверку перед WorkerRun, final pre-start revalidation и fail-closed поведение при критичной неопределённости.

**Границы утверждения:** подтверждение относится к архитектурной основе. Оно не утверждает как окончательно определённые все поля физической БД, полный реестр `operation_type` и `check_code`, точные индексы/миграции, lease/revalidation алгоритм, полный WorkerRun state machine, retention/legal hold, API UX-детали или эксплуатационные SLO. Эти элементы подлежат последующей детализации в рамках утверждённых принципов.

**Статус реализации:** не реализовано и не проверено в runtime на основании этого архитектурного подтверждения. Статическая проверка контрактов остаётся отдельным evidence и не является доказательством работоспособности Temporal, PostgreSQL concurrency, Policy Engine или recovery.


---

## Дополнение v1.2 — утверждённые Operation Lifecycle и WorkerRun Lifecycle

**Статус дополнения:** BASELINED — пользователь принял предложенный подход 2026-11-10 и делегировал выбор конкретных проектных решений. Это дополнение является нормативным продолжением архитектурного решения v1.1.

### A. Operation как корневая команда

1. Одна пользовательская/системная команда создаёт одну корневую Operation. Operation может охватывать множество Tasks и WorkerRuns, включая fan-out/fan-in, итерации, rework и независимый QA.
2. Fan-out внутри одной команды моделируется Plan/PlanVersion/PlanItem/Task/WorkerRun и связями зависимостей. Не создавать дочернюю Operation на каждый Task, WorkerRun, retry, consultation или QA.
3. `parent_operation_id` допускается только для самостоятельной длительной подкоманды с отдельным результатом/статусом, независимой отменой или продолжением, отдельным инициатором/permission scope либо самостоятельным audit-контекстом. Дочерняя Operation имеет собственный idempotency scope, lifecycle и OperationEvents; связь parent-child не означает автоматического наследования прав.
4. WorkerRun обязан принадлежать ровно одной Task. Operation связывается с Task через область исполнения/subject/operation-task association, а с WorkerRun — через Task и явную `operation_id` для однозначной корреляции и безопасной агрегации. `operation_id` не заменяет `task_id`.
5. Для MVP каждая Task в рамках операции имеет один обязательный owning Operation. Если позднее потребуется Task, разделяемая несколькими операциями, это будет отдельное архитектурное изменение; не моделировать это неявно.

### B. Operation aggregation

Operation status — доменная агрегированная проекция хода команды, а не копия статуса Temporal, Task или WorkerRun. Агрегатор использует критерии завершения Operation, обязательность/необязательность PlanItems/Tasks, зависимости, допустимость partial result, результаты и unresolved blockers. Количество успешных WorkerRuns само по себе не является критерием.

- `RUNNING`: есть активный прогресс, включая параллельные ветви; локальное ожидание одного WorkerRun не переводит Operation в ожидание, если другая ветвь может продвигаться.
- `WAITING_FOR_HUMAN`: необходимое человеческое действие блокирует все допустимые пути продолжения Operation.
- `WAITING_FOR_DEPENDENCY`: обязательная зависимость блокирует все допустимые пути продолжения Operation.
- `RETRYING`: выполняется согласованное восстановление/повтор, и это является текущим доминирующим состоянием операции.
- `SUCCEEDED`: выполнены все обязательные критерии, необязательные ветви либо завершены, либо допустимо исключены контрактом; итоговый результат соответствует контракту.
- `PARTIALLY_SUCCEEDED`: достигнут явно разрешённый частичный результат, обязательная часть результата определена, невыполненные части и ограничения раскрыты.
- `FAILED`: обязательный результат недостижим и стратегия восстановления исчерпана/запрещена.
- `CANCELLED`: отмена подтверждена, активные исполнения reconciled, обязательный cleanup завершён; если side effect уже завершился, фактический итог может быть `SUCCEEDED`, `PARTIALLY_SUCCEEDED` или `FAILED` согласно исходу.

Operation aggregation должна быть детерминированной и версионируемой. Все входные факты имеют event refs/sequence и причины. Переход в terminal state выполняется только после проверки criteria и reconciliation. Terminal Operation не открывается повторно; новое пользовательское намерение создаёт новую Operation.

### C. WorkerRun lifecycle — отдельная доменная попытка исполнения

Канонические статусы WorkerRun:
`CREATED`, `PREPARING`, `WAITING_FOR_GATE`, `BLOCKED`, `QUEUED`, `STARTING`, `RUNNING`, `WAITING_FOR_HUMAN`, `WAITING_FOR_DEPENDENCY`, `RESULT_SUBMITTED`, `VALIDATING`, `REVIEW_PENDING`, `QA_PENDING`, `CANCEL_REQUESTED`, `COMPLETED`, `REWORK_REQUIRED`, `REJECTED`, `UNVERIFIED`, `FAILED`, `TIMED_OUT`, `CANCELLED`.

Terminal: `COMPLETED`, `REWORK_REQUIRED`, `REJECTED`, `UNVERIFIED`, `FAILED`, `TIMED_OUT`, `CANCELLED`. `BLOCKED` — non-terminal operational state: после устранения блокера создаётся новая ReadinessEvaluation и WorkerRun возвращается в `WAITING_FOR_GATE`. `CANCEL_REQUESTED` — non-terminal.

Семантика:
- `CREATED`: доменная попытка создана, ещё не подготовлена.
- `PREPARING`: фиксируются envelope, context, budgets, grants refs, output contract и execution metadata.
- `WAITING_FOR_GATE`: ожидается persisted ReadinessEvaluation и финальная revalidation.
- `BLOCKED`: текущий запуск не допускается; Runtime не стартует. После изменения условий возможна новая evaluation для того же WorkerRun, если не меняется его смысл/Task contract; существенное изменение scope/контекста/плана создаёт производный WorkerRun.
- `QUEUED`: допуск подтверждён, запуск ожидает scheduler/dispatcher.
- `STARTING`: workflow/run стартует; ещё нет подтверждённого начала Worker execution.
- `RUNNING`: Worker execution начат.
- `WAITING_FOR_HUMAN` / `WAITING_FOR_DEPENDENCY`: durable pause; возобновление через авторизованный backend command/signal, не прямое воздействие UI на Temporal.
- `RESULT_SUBMITTED`: Worker передал неизменяемый result reference/manifest; это ещё не принятие.
- `VALIDATING`: deterministic validation output schema, provenance, references, policy and integrity.
- `REVIEW_PENDING`: ожидается Manager/Reviewer semantic assessment.
- `QA_PENDING`: отдельный Review/QA WorkerRun обязателен по task-class policy или принятому решению Manager; QA оформляется отдельным Review и WorkerRun, не продолжением того же Run.
- `COMPLETED`: результат этого WorkerRun принят в пределах его execution/output contract. Это не human approval, Artifact approval, publication или baseline.
- `REWORK_REQUIRED`: результат требует исправления; данный WorkerRun терминален, создаётся производный WorkerRun.
- `REJECTED`: результат отклонён и не допускается к downstream use; если исправление возможно, решение должно быть `REWORK_REQUIRED`.
- `UNVERIFIED`: достаточного подтверждения нет; не допускается к критичным downstream decisions.
- `FAILED`: execution/processing failure после применимых retry/recovery policy либо невосстановимая ошибка.
- `TIMED_OUT`: достигнут hard deadline; состояние фиксируется после reconciliation фактического исполнения/side effects.
- `CANCEL_REQUESTED`: запрошена отмена, исход ещё не подтверждён.
- `CANCELLED`: отмена подтверждена после stop/cleanup/reconciliation. Если результат фактически завершился до cancellation, фиксируется соответствующий фактический исход, а не ложная отмена.

### D. Readiness Gate и WorkerRun

Gate outcome не является WorkerRun status. `READY` и `READY_WITH_LIMITATIONS` с `COMPLETED` evaluation допускают final pre-start revalidation; `BLOCKED` переводит WorkerRun в `BLOCKED`; `STALE` требует новой evaluation и оставляет WorkerRun в `WAITING_FOR_GATE`; `EVALUATOR_ERROR` fail-closed и не допускает dispatch. Gate evaluation immutable. Каждая новая попытка/производный WorkerRun получает собственную evaluation. Повторная оценка того же WorkerRun разрешена только если его execution intent и контракт не изменились; иначе нужен новый WorkerRun.

### E. Производные WorkerRun

Каждый WorkerRun имеет ровно один `task_id`, `operation_id`, `worker_definition_version_id`, ContextPackageVersion и точную ReadinessEvaluation для каждого допуска/старта. `derived_from_worker_run_id` nullable self-reference. `derivation_reason` enum: `RETRY`, `REWORK`, `NEW_CONTEXT`, `INDEPENDENT_REVIEW`, `REEXECUTION`, `SPECIALIST_HANDOFF`. Не все derivations являются retry.

- Повтор содержательной работы всегда создаёт новый WorkerRun; terminal Run не reopen.
- `RETRY` допустим только для повторного выполнения того же intent после transient failure/timeout с соблюдением retry budget/idempotency и side-effect reconciliation.
- `REWORK` следует за `REWORK_REQUIRED` и содержит ссылки на замечания/acceptance gaps.
- `NEW_CONTEXT` означает новое содержательное основание/версию контекста.
- `INDEPENDENT_REVIEW` — независимая оценка; создаётся отдельная Review и WorkerRun.
- `SPECIALIST_HANDOFF` выполняется только через Manager; новый Run проходит Gate.
- Temporal Activity retry/replay внутри одной доменной попытки не создаёт новый WorkerRun. Новый WorkerRun создаётся при новой содержательной попытке, а не при техническом retry Activity.

### F. Границы принятия результата

`WorkerRun.COMPLETED` ≠ `QA PASS` как самостоятельный Review outcome ≠ человеческое `Approval` ≠ `Artifact.APPROVED` ≠ `PUBLISHED` ≠ `Baseline`. Эти факты фиксируются отдельными доменными сущностями/событиями. Manager может принять результат WorkerRun в пределах output contract, но не может подменить бизнес-решение человека там, где требуется human approval.

### G. Отмена и сбои

Отмена Operation инициирует отмену активных WorkerRuns через доверенный application service/Temporal signals. Каждый WorkerRun проходит `CANCEL_REQUESTED` и собственную reconciliation. Operation остаётся `CANCEL_REQUESTED`, пока все обязательные активные ветви reconciled и определён итог. Нельзя считать остановку Temporal Workflow доказательством отсутствия внешнего side effect. Для неоднозначных side effects требуется idempotent reconciliation или human escalation.

### H. Нормативные инварианты

1. Operation, Task, WorkerRun, ReadinessEvaluation, Review, Approval, Artifact и Temporal Workflow имеют разные lifecycle.
2. WorkerRun принадлежит ровно одной Task и одной Operation; Task принадлежит одной owning Operation в рамках MVP.
3. Operation может иметь N Tasks и N WorkerRuns; fan-out не создаёт автоматически child Operations.
4. Child Operation — самостоятельная команда с отдельными idempotency/audit/ACL boundaries.
5. WorkerRun terminal state immutable; новый содержательный запуск — новая запись.
6. Каждый фактический WorkerRun start ссылается на точную успешную ReadinessEvaluation и прошедшую final revalidation.
7. `BLOCKED` и `STALE` не являются успешным допуском; `EVALUATOR_ERROR` fail-closed.
8. WorkerRun не может завершить Operation напрямую; только агрегатор/application service.
9. Operation success требует criteria-based completion, а не подсчёта WorkerRun.
10. QA, business approval, artifact approval/publication и baseline — отдельные решения.
11. Temporal replay/Activity retry не создают новый доменный WorkerRun.
12. Cancellation/timeout/failure требуют side-effect reconciliation прежде чем фиксировать terminal outcome.
13. Все переходы — атомарные, optimistic concurrency controlled, append-only event + outbox; клиент не может произвольно PATCH status.
14. ACL проверяется на Operation, Task, WorkerRun, Review и result/evidence refs; parent-child связи не расширяют доступ автоматически.


## Дополнение v1.3 — Operation/WorkerRun Event Model decision

**Статус:** BASELINED design decision, 10.11.2026.

Утверждены: CloudEvents 1.0 envelope; PostgreSQL append-only event history + Transactional Outbox; consumer-scoped Inbox; at-least-once delivery; stable event ID; monotonic per-aggregate sequence; строгий порядок только внутри aggregate; optimistic concurrency; command idempotency fingerprint; ACL-filtered event access; versioned event schemas; quarantine/replay; no secrets/prompts/full payloads in events. Exactly-once end-to-end не обещается. Outbox не является публичным API и не заменяет AuditEvent. Полный каталог и правила — `AI_RES_Operation_WorkerRun_Event_Model_v1.0.md`.

---

## Дополнение v1.4 — физическая модель PostgreSQL и транзакционные гарантии

**Статус дополнения:** BASELINED design contract; физическая реализация и runtime verification не заявляются.

### Принятые решения по PostgreSQL persistence

- `ai_res_db` остаётся единой доменной БД; `temporal_db` отделена.
- Operation, Task association, WorkerRun, ReadinessEvaluation, Event History, Outbox, Inbox и Idempotency records хранятся в нормализованных доменных схемах PostgreSQL.
- Текущее состояние хранится в проекциях; append-only Event History является историей доменных фактов, но не единственным источником восстановления состояния (не full Event Sourcing).
- Доменная мутация + event history + outbox фиксируются одной транзакцией.
- Delivery at-least-once; обработчики идемпотентны через Inbox.
- Sequence выдаётся транзакционно под блокировкой aggregate row; `MAX(sequence)+1` запрещён.
- Optimistic concurrency через `row_version`; короткие row locks допустимы для сериализации aggregate transitions.
- Operation → Task → WorkerRun — физически защищённые FK; WorkerRun несёт operation_id для запросов, composite FK обеспечивает соответствие Task.
- UUIDv7 генерируется приложением; status хранится как TEXT с CHECK/domain validation, не PostgreSQL ENUM в MVP.
- Внешние вызовы никогда не выполняются внутри открытой DB-транзакции.
- Terminal immutability и Gate/WorkerRun referential invariants контролируются доменным слоем и ограничениями БД.
- Child Operation остаётся редким самостоятельным процессом; fan-out реализуется через Tasks/WorkerRuns.

### Транзакционные контракты

Утверждены design algorithms: TX-01 Create Operation idempotently; TX-02 aggregate transition; TX-03 Task/WorkerRun creation; TX-04 Gate completion and final start revalidation; TX-05 Outbox dispatch; TX-06 Inbox consumer; TX-07 cancellation; TX-08 Operation aggregation; TX-09 recovery/reconciliation.

### Открытые implementation decisions

ORM/query layer, migration tool, HMAC key rotation, retention, lease/retry parameters, event transport и legacy data mapping остаются implementation decisions. Их нельзя угадывать в коде без записи ADR/Implementation Decision.


---

## Дополнение 1.5 — PostgreSQL migration и access decision

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.

Физическая модель остаётся частью `ai_res_db`, Temporal persistence — отдельная `temporal_db`. Migration ownership, DB role ownership и runtime ownership разделены.


## Дополнение v1.6 — Persistence Implementation Blueprint

**Статус:** BASELINED design/implementation contract; live implementation is not claimed.

Для Operation/Task/WorkerRun/ReadinessEvaluation persistence принят `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`. Обязательные решения: Alembic + SQLAlchemy 2.x; единый migration environment для `ai_res_db`; schema allowlist и `platform.alembic_version`; отдельный one-shot migration job; expand/backfill/validate/contract; backfill только по подтверждённому legacy provenance; Unit of Work с атомарной записью projection + event + Outbox; transaction-local tenant context; отдельные DB identities; PostgreSQL integration acceptance PERSIST-001..024.

Claude Code не должен считать blueprint внедрённым до прохождения Definition of Done и предоставления фактических migration/test/restore evidence. Temporal/LangGraph persistence migrations остаются вне AI RES Alembic.
