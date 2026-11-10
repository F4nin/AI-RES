# AI RES — API и контракты взаимодействия

**Версия:** 1.10  
**Дата:** 10.11.2026  
**Статус:** целевая спецификация API для MVP и нормативная основа реализации; точные поля отдельных специализированных DTO уточняются в машинных схемах без изменения принципов.  
**Назначение:** определить внешние и внутренние интерфейсы AI RES, контракты агентного исполнения, событийную модель, правила безопасности, совместимости и проверки.

## 1. Архитектурные решения

### 1.1. Contract-first

1. Контракт проектируется и проходит review до реализации обработчика.
2. OpenAPI/JSON Schema/AsyncAPI являются машиночитаемыми источниками контрактов; Markdown объясняет архитектуру и правила.
3. Backend реализация, frontend-клиенты, SDK и интеграционные тесты должны соответствовать контрактам.
4. Claude Code не должен самостоятельно изобретать DTO, endpoint, event name, enum или статус, если он уже определён в контракте.
5. Изменение контракта проходит review, compatibility checks, обновление спецификаций, тестов и changelog.

### 1.2. Три плоскости взаимодействия

| Плоскость | Потребители | Механизм | Назначение |
|---|---|---|---|
| User/API plane | Frontend, пользовательские интеграции | REST/JSON через Reverse Proxy | Управление проектами, требованиями, задачами, артефактами и действиями аналитика |
| Platform/runtime plane | Manager Runtime, Worker Runtime, Backend-модули, Connector Platform | Типизированные внутренние интерфейсы; Temporal для durable orchestration; HTTP только на границах процессов, где он оправдан | Внутренние операции и выполнение |
| Event/stream plane | Frontend, доменные модули, наблюдаемость | SSE для UI; Transactional Outbox для доменных событий; AsyncAPI для описания событий | Прогресс, уведомления, интеграция и реакция на изменения |

API не превращает модульный Backend в набор микросервисов. Внутри одного процесса доменные модули вызывают друг друга через application service interfaces, а не через HTTP loopback.

### 1.3. Технологические стандарты

| Область | Выбор для MVP | Обоснование / ограничение |
|---|---|---|
| HTTP API | REST + JSON | Простая интеграция с Frontend и внешними клиентами |
| API description | OpenAPI 3.1.1 | Выбран как совместимая базовая версия для JSON Schema 2020-12 и существующего tooling; перед реализацией генераторов выполнить compatibility PoC с OAS 3.2.1 |
| Data schemas | JSON Schema Draft 2020-12 | Единая схема для HTTP payload, Worker DTO и событий; использовать явный `$schema` |
| Error format | RFC 9457 `application/problem+json` | Стандартизированный формат ошибок HTTP |
| Domain events | CloudEvents 1.0 envelope + typed `data` | Общая оболочка события, типизированное содержимое |
| Event contract description | AsyncAPI 3.1.0 | Документирование логических каналов, сообщений и подписчиков |
| UI streaming | Server-Sent Events (SSE) | Однонаправленная передача прогресса/уведомлений; команды остаются REST |
| Long-running orchestration | Temporal | Durable lifecycle, timers, retries, waiting, cancellation, resumption |
| Agent reasoning | LangGraph | Внутренний граф рассуждений Worker/Manager; не внешний API AI RES |
| Internal model access | AI RES LLM Gateway Adapter → Bifrost candidate | Не связывать код агентов с SDK или API конкретного провайдера |

OAS 3.1.1 — осознанный выбор совместимости, а не утверждение, что это самая новая версия: на дату документа опубликована OAS 3.2.1. Перед генерацией SDK/валидаторов проверить фактическую поддержку 3.2.1; переход на неё допускается отдельным совместимым обновлением. Официальные спецификации: OpenAPI, JSON Schema, AsyncAPI и RFC 9457 перечислены в разделе 18.

## 2. Границы API и владение данными

- Domain Services AI RES — единственный владелец доменного состояния Project, Epic, Task, Requirement, Source, Artifact, Decision, Plan, Approval и Baseline.
- Temporal — владелец состояния Workflow execution, а не доменных сущностей.
- LangGraph Checkpointer — владелец состояния внутреннего graph thread/checkpoint, но не Project/Task/Requirement.
- MinIO — хранит бинарные объекты; API выдаёт ограниченные по времени presigned upload/download URLs после ACL checks.
- Bifrost — инфраструктурный провайдер LLM Gateway, но не владелец AI RES policy, project permissions или domain audit.
- Worker Runtime не получает unrestricted SQL-доступ и не меняет доменные таблицы напрямую.
- Frontend не обращается напрямую к Temporal, PostgreSQL, MinIO Console, Bifrost Admin API или Langfuse.

## 3. Публичный REST API

### 3.1. Базовые правила

- Base path: `/api/v1`.
- JSON UTF-8; даты/время — RFC 3339 UTC (`timestamptz` в БД).
- Идентификаторы — UUID; человекочитаемые номера (`REQ-...`, `TASK-...`) только для отображения.
- Именование JSON: `camelCase`; enum — стабильные UPPER_SNAKE_CASE значения.
- Не возвращать ORM/entity напрямую: только версионируемые API DTO.
- Ответ на чтение ресурса — resource representation; коллекция — `{ "data": [...], "page": {...} }`.
- Ошибки — RFC 9457 `application/problem+json` с `code`, `correlationId` и при необходимости `fieldErrors` как extension.
- Не включать stack traces, SQL, secrets, provider raw payload или внутренние пути файлов в API errors.
- Не использовать универсальные endpoint вида `/execute`, `/query`, `/mutate` или произвольный SQL.

### 3.2. Ресурсные группы и endpoint catalog

#### Workspace / organization / projects

| Method | Path | Назначение |
|---|---|---|
| GET | `/me` | Текущий пользователь и доступные контексты |
| GET/POST | `/organizations` | Список доступных организаций / создание при наличии права |
| GET | `/organizations/{organizationId}` | Карточка организации |
| GET/POST | `/projects` | Список проектов / создание проекта |
| GET/PATCH | `/projects/{projectId}` | Чтение / изменение разрешённых метаданных проекта |
| GET | `/projects/{projectId}/members` | Участники проекта |
| POST | `/projects/{projectId}/members` | Назначение участника с проверкой полномочий |
| DELETE | `/projects/{projectId}/members/{membershipId}` | Отзыв членства; audit required |

#### Epics, tasks and plans

| Method | Path | Назначение |
|---|---|---|
| GET/POST | `/projects/{projectId}/epics` | Список / создание Epic |
| GET/PATCH | `/epics/{epicId}` | Чтение / изменение метаданных Epic с optimistic concurrency |
| GET/POST | `/epics/{epicId}/tasks` | Список / создание Task |
| GET/PATCH | `/tasks/{taskId}` | Чтение / изменение Task |
| POST | `/tasks/{taskId}/links` | Создание разрешённой связи Task с Requirement/Artifact и т.п. |
| GET | `/tasks/{taskId}/runs` | История Worker Runs задачи |
| GET/POST | `/epics/{epicId}/plans` | Список / создание Plan proposal |
| GET | `/plans/{planId}` | Текущая карточка Plan |
| GET | `/plans/{planId}/versions` | История PlanVersion |
| GET | `/plan-versions/{planVersionId}` | Неизменяемая версия плана |
| POST | `/plan-versions/{planVersionId}/decision` | Approve/reject/request-changes для версии плана или допустимой части |
| POST | `/epics/{epicId}/manager-messages` | Отправить Manager сообщение/запрос в контексте Epic |

Plan approval не является approval требований или Baseline. Пользователь не запускает произвольный Worker напрямую: он инициирует работу/обращается к Manager, который формирует план и исполняет его через Temporal после обязательного Readiness Gate.

#### Requirements and decisions

| Method | Path | Назначение |
|---|---|---|
| GET/POST | `/projects/{projectId}/requirements` | Поиск/создание кандидатов или требований в пределах разрешённых действий |
| GET | `/requirements/{requirementId}` | Карточка требования |
| GET | `/requirements/{requirementId}/versions` | История версий |
| GET | `/requirement-versions/{versionId}` | Неизменяемая версия |
| POST | `/requirements/{requirementId}/versions` | Предложить новую версию с `If-Match` |
| POST | `/requirements/{requirementId}/decisions` | Действие по candidate/confirmation/approval согласно полномочиям |
| GET/POST | `/projects/{projectId}/decisions` | Реестр Decision |
| GET/POST | `/projects/{projectId}/assumptions` | Реестр Assumption |
| GET/POST | `/projects/{projectId}/risks` | Реестр Risk |
| GET/POST | `/projects/{projectId}/issues` | Реестр Issue |

Статусы и действия не должны быть произвольными строками от LLM. Сервер проверяет переходы lifecycle и authority. Создание версии не равнозначно утверждению.

#### Sources and knowledge

| Method | Path | Назначение |
|---|---|---|
| GET/POST | `/projects/{projectId}/sources` | Каталог / регистрация Source |
| GET | `/sources/{sourceId}` | Карточка Source |
| GET/POST | `/sources/{sourceId}/versions` | История / регистрация версии |
| GET | `/source-versions/{sourceVersionId}` | Метаданные неизменяемой версии |
| GET | `/source-versions/{sourceVersionId}/fragments` | Фрагменты с локаторами и ACL |
| POST | `/uploads` | Создать upload intent и получить краткоживущий presigned URL |
| POST | `/uploads/{uploadId}/complete` | Подтвердить upload, проверить checksum/размер/тип и создать SourceVersion |
| POST | `/sources/{sourceId}/refresh` | Запросить синхронизацию/обновление источника |

Файл не принимается как доверенный только из-за успешного upload. Проверяются размер, тип, malware policy, checksum, ACL и provenance. Presigned URL ограничен по времени, объекту, методу и размеру; MinIO credentials клиенту не выдаются.

#### Artifacts, review and baseline

| Method | Path | Назначение |
|---|---|---|
| GET/POST | `/projects/{projectId}/artifacts` | Каталог / регистрация Artifact |
| GET | `/artifacts/{artifactId}` | Карточка Artifact |
| GET/POST | `/artifacts/{artifactId}/versions` | История / создание новой версии |
| GET | `/artifact-versions/{artifactVersionId}` | Точная версия и provenance |
| GET | `/artifact-versions/{artifactVersionId}/representations` | Представления версии |
| POST | `/artifact-versions/{artifactVersionId}/validate` | Запустить validation job |
| GET | `/validation-reports/{validationReportId}` | Результат проверки |
| POST | `/artifact-versions/{artifactVersionId}/reviews` | Создать Review |
| POST | `/reviews/{reviewId}/comments` | Добавить замечание |
| POST | `/reviews/{reviewId}/decision` | Submit review outcome |
| POST | `/artifact-versions/{artifactVersionId}/approvals` | Approval конкретной версии при наличии полномочий |
| GET/POST | `/projects/{projectId}/baselines` | Список / предложение новой Baseline |
| GET | `/baselines/{baselineId}` | Неизменяемая Baseline и её элементы |
| POST | `/projects/{projectId}/change-requests` | Создать Change Request |
| GET | `/change-requests/{changeRequestId}` | Состояние и Impact Assessment |

#### Traceability, runs and integrations

| Method | Path | Назначение |
|---|---|---|
| GET | `/projects/{projectId}/traceability` | Фильтрованный список связей с ACL |
| POST | `/projects/{projectId}/traceability-links` | Предложить/создать связь с проверкой registry |
| GET | `/projects/{projectId}/impact-assessments/{assessmentId}` | Результат анализа влияния |
| GET | `/worker-runs/{workerRunId}` | Сводка выполнения, статус и ссылки |
| GET | `/worker-runs/{workerRunId}/result` | Структурированный результат с ACL |
| POST | `/worker-runs/{workerRunId}/feedback` | Запросить доработку через Manager, не менять результат Run |
| GET/POST | `/projects/{projectId}/integrations` | Каталог/создание connection при наличии права |
| GET | `/integrations/{integrationId}` | Состояние подключения |
| POST | `/integrations/{integrationId}/sync` | Запустить синхронизацию |
| GET | `/sync-runs/{syncRunId}` | Результат синхронизации |

Endpoint catalog — целевой MVP-контур. Не все группы обязаны быть реализованы в первом инкременте, но их контракты должны быть согласованы и реализовываться по приоритетам Capability Matrix.

## 4. Асинхронные операции и прогресс

### 4.1. HTTP 202 и Operation Resource

Долгие операции (создание плана, анализ источника, генерация артефакта, Impact Analysis, sync, запуск Epic orchestration) не удерживают HTTP request до завершения.

- API принимает и валидирует команду.
- Создаёт `operation_id` и доменную запись/команду в одной транзакции с Outbox либо иным надёжным механизмом передачи.
- Возвращает `202 Accepted`, `Location: /api/v1/operations/{operationId}` и `Retry-After` при необходимости.
- Клиент читает `GET /operations/{operationId}` или подписывается на SSE.
- Operation resource содержит `status`, `submittedAt`, `startedAt`, `completedAt`, `resultRef`, `problem`, `correlationId`.
- Не использовать фиктивные проценты; progress — только подтверждённые этапы/события.

Канонические состояния Operation: `ACCEPTED`, `QUEUED`, `RUNNING`, `WAITING_FOR_HUMAN`, `WAITING_FOR_DEPENDENCY`, `RETRYING`, `CANCEL_REQUESTED`, `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `CANCELLED`. Это объединяет состояния, описанные в API-представлении и процессной модели. `CANCEL_REQUESTED` — нетерминальное состояние; `WAITING_FOR_DEPENDENCY` и `RETRYING` — нетерминальные состояния; `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `CANCELLED` — терминальные. Технический статус Temporal и доменный статус Task/Epic не сливаются. Переходы должны быть реализованы как явная state machine и покрыты тестами; произвольная смена статуса запрещена.

### 4.2. Endpoints операций

- `GET /api/v1/operations/{operationId}` — состояние.
- `POST /api/v1/operations/{operationId}/cancel` — запрос отмены; ответ подтверждает приём запроса, а не завершение отмены.
- `GET /api/v1/projects/{projectId}/events` — SSE поток событий проекта, доступных текущему субъекту.

SSE использует `text/event-stream`, `id` для replay cursor, `Last-Event-ID` для переподключения и heartbeat. События не должны содержать полный prompt, secret, скрытые документы или данные, не разрешённые ACL. При пропуске retention клиент получает `resync_required` и перечитывает snapshot через REST.

## 5. Общие HTTP правила

### 5.1. Pagination and filtering

- Cursor-based pagination по умолчанию: `limit` (серверный max), `cursor` opaque.
- Стабильная сортировка с уникальным tie-breaker (обычно `createdAt,id`).
- Фильтры только явно объявленные endpoint-ом; произвольный SQL/filter DSL запрещён.
- Ответ страницы: `data`, `page.nextCursor`, `page.hasMore`.
- Список не должен раскрывать количество/наличие недоступных объектов.

### 5.2. Concurrency and versioning

- Для изменяемых ресурсов возвращать `ETag`.
- Для update/version/approval commands требовать `If-Match` либо явно определённый expected version; stale request получает `412 Precondition Failed`.
- Создание новой версии не перезаписывает предыдущую.
- `409 Conflict` — бизнес-конфликт перехода/уникальности; `412` — устаревшая версия; `428 Precondition Required` — обязательный If-Match отсутствует.

### 5.3. Idempotency

- Для POST, создающих операцию, запускающих workflow/sync, upload finalization, approval/decision и иных side effects, клиент обязан передать `Idempotency-Key`.
- Ключ ограничен authenticated subject + operation scope; сервер сохраняет request hash, итоговый response reference и expiry.
- Повтор с тем же ключом и тем же payload возвращает тот же результат; тот же ключ с другим payload — `409 IDEMPOTENCY_KEY_REUSED`.
- Idempotency не заменяет проверку прав и доменные unique constraints.
- Для внешних provider calls и Activities используются отдельные deterministic idempotency keys, связанные с operation/run/action.

### 5.4. HTTP status semantics

Использовать стандартные коды: `200`, `201`, `202`, `204`, `400`, `401`, `403`, `404`, `409`, `412`, `413`, `415`, `422`, `428`, `429`, `500`, `502`, `503`, `504`. Не возвращать `200` с `success:false` вместо HTTP ошибки.

## 6. Аутентификация и авторизация

- Browser User API в MVP: Local Authentication + opaque server-side session cookie согласно `AI_RES_Authentication_and_Session_Management_v1.0.md`. Backend извлекает session ID из cookie, проверяет серверную сессию, её expiry/revocation и состояние пользователя; далее каждый запрос проходит независимую object-level authorization через Policy & Permission Engine. Пользовательский browser API не требует OIDC/JWT Bearer.
- Для cookie-authenticated state-changing requests обязательны CSRF token validation и проверка Origin/Referer по принятой security policy; SameSite cookie — дополнительный, не единственный CSRF control.
- Future external federation: OIDC Authorization Code + PKCE через `IdentityProvider` adapter; проверка issuer/audience/signature/expiry/nonce/state/PKCE применяется к OIDC callback/token flow, но не подменяет внутреннюю browser session.
- Service-to-service: отдельные service identities и короткоживущие audience-scoped credentials/mTLS по мере зрелости; если используется JWT, его проверка относится только к соответствующему service token profile. Не использовать пользовательскую browser session или пользовательский bearer token как универсальную идентичность Worker.
- RBAC определяет базовые действия роли; ABAC/Policy Engine проверяет organization/project/object scope, ownership, sensitivity, operation risk и временные grants.
- Авторизация выполняется на сервере при каждом запросе и каждом инструментальном действии; UI скрытие не является защитой.
- Worker permissions не наследуются автоматически от инициатора; Manager запрашивает scoped grant, Policy Engine независимо разрешает/запрещает.
- Критические операции fail-closed. При недоступности Policy Engine нельзя выполнять write/approval/external side effects.
- Не раскрывать existence объекта через 403/404 вразрез с политикой anti-enumeration; для объектов вне scope предпочтителен контролируемый 404.
- Все изменения прав и административные операции аудируются.

## 7. Внутренние контракты платформы

### 7.1. Modular Backend — без HTTP между модулями

Внутри Backend использовать application service interfaces и typed commands/queries. Каждый доменный модуль владеет своими таблицами и инвариантами. Прямой доступ к таблицам другого модуля запрещён, кроме миграций/административных процедур. Межмодульные изменения — через публичный application service или domain event.

### 7.2. Межпроцессные границы

- Frontend ↔ Backend: Public REST + SSE.
- Manager Runtime ↔ Temporal: Temporal SDK через разрешённый orchestration client/Activities; Manager не обращается к Temporal UI/API напрямую.
- Worker Runtime ↔ Temporal: Worker SDK poll-ит только разрешённые task queues; Worker получает typed Run envelope через Activity input.
- Manager/Worker Runtime ↔ Domain Services: внутренний authenticated Platform API/SDK с узкими операциями. Для MVP допустим internal HTTP/JSON на границе процессов; интерфейс должен быть provider/runtime independent.
- Connector Platform ↔ внешние системы: только через connector adapters и egress policy.
- LLM: только через AI RES LLM Gateway Adapter → Bifrost candidate; прямые SDK провайдеров в Manager/Workers запрещены.
- MinIO: upload/download через short-lived presigned URLs, генерируемые File Service после ACL.

Внутренний Platform API не публикуется через внешний Reverse Proxy и не доступен пользователю напрямую. Он использует отдельную service authentication, rate limits, audit и network policy.

### 7.3. Основные application service interfaces

Рекомендуемые логические интерфейсы (не обязательно отдельные сетевые сервисы):

- `ProjectApplicationService`: create/read/update project, membership checks.
- `WorkApplicationService`: Epic/Task/Plan commands, state transitions.
- `RequirementApplicationService`: candidate registration, version proposal, lifecycle decisions.
- `SourceApplicationService`: upload finalization, source version registration, fragments and provenance.
- `ContextApplicationService`: build/retrieve immutable ContextPackageVersion.
- `ArtifactApplicationService`: artifact/version/generation/representation lifecycle.
- `TraceabilityApplicationService`: typed links, impact assessment.
- `GovernanceApplicationService`: review, approval, baseline and CR transitions.
- `PolicyDecisionService`: authorization decision and scoped grants.
- `AuditApplicationService`: append-only audit recording.
- `AgentExecutionApplicationService`: create WorkerRun, persist WorkerResult/proposals and retrieve status.
- `IntegrationApplicationService`: connections, mappings, sync runs.

## 8. Manager–Worker contract

### 8.1. WorkerRunEnvelope (input)

Каждый запуск получает immutable, schema-versioned envelope, содержащий:

- `contractVersion`, `workerRunId`, `taskId`, `epicId`, `projectId`, `organizationId`;
- `workerDefinitionId`, `workerRole`, `runtimeProfileVersion`;
- `planVersionId`, если применимо;
- `contextPackageVersionId` и checksum;
- цель, scope, ограничения, допущения и зависимости;
- expected output schema/version и acceptance criteria;
- разрешённые tool IDs/versions и opaque scoped grant reference (не сами секреты);
- execution budgets/timeout class, если заданы политикой;
- `correlationId`, `traceparent`, attempt number и `idempotencyKey`.

Envelope не должен содержать большие документы, полные репозитории, API keys или секреты. Большие данные передаются ссылками на Context Package/Artifact/SourceVersion с ACL и checksum.

### 8.2. WorkerResult (output)

Результат — структурированный объект, не свободный текст и не прямой write в доменные таблицы. Обязательные группы:

- `contractVersion`, `workerRunId`, `taskId`, `workerRole`, `resultStatus`;
- `summary` и `outcome`;
- `findings[]` с типом утверждения (FACT/SOURCE_ASSERTION/CONCLUSION/HYPOTHESIS/ASSUMPTION/UNKNOWN), evidence references, rationale и uncertainty;
- `proposedChanges[]` с target object/version, change type, proposed payload/reference, rationale и impact hints;
- `artifactRefs[]` с Artifact/ArtifactVersion IDs или generation proposal;
- `questions[]`, `blockers[]`, `risks[]`, `limitations[]`;
- `validation` и self-assessment (не подменяет independent QA/Manager acceptance/human approval);
- `toolExecutionRefs[]` (только безопасные ссылки/метаданные);
- `metrics` (latency/token usage/cost only where provider reports it, no secrets).

`resultStatus`: `COMPLETED`, `PARTIAL`, `BLOCKED`, `FAILED`, `CANCELLED`. Worker не может выставить доменному требованию `APPROVED`, опубликовать Artifact или создать Baseline по одному своему результату.

### 8.3. Worker messages / handoff

- Worker сообщает о blocker, missing information, conflict, risk, need for clarification через типизированный `WorkerNotice`.
- Worker может предложить handoff другому Worker; Manager/Workflow Engine подтверждает и создаёт новый WorkerRun.
- Handoff не передаёт автоматически permissions, secrets, tool grants или право менять scope.
- Worker-to-Worker обмен допустим только в рамках зарегистрированной задачи и контролируется Manager.

### 8.4. Manager result acceptance

Платформа различает: Worker self-assessment → independent QA review (когда требуется) → Manager orchestration acceptance → human approval. Эти состояния нельзя свести к одному `approved`.

## 9. Temporal contracts

### 9.1. Ответственность

Temporal — durable orchestration; LangGraph — внутреннее reasoning. Workflow code детерминирован. Все LLM вызовы, БД, HTTP, файловые операции и прочие side effects выполняются в Activities. Workflow History хранит компактные параметры и ссылки/ID, не полные документы, prompts или secrets.

### 9.2. Workflow/Activity inputs

- `EpicOrchestrationWorkflow` — epic ID, request ID, plan version reference и compact execution options.
- `ManagerActivity` — цель, scoped context refs, permissions references, expected decision/output schema.
- `WorkerExecutionActivity` — WorkerRunEnvelope и ContextPackageVersion reference.
- `ReadinessGateActivity` — task/worker/context/permission/acceptance references; результат `READY`, `READY_WITH_LIMITATIONS`, `BLOCKED` с checks и reasons.
- `PersistWorkerResultActivity` — validated WorkerResult reference/payload and run version.
- `PublishDomainEventActivity` / outbox dispatcher — event ID only/reference, idempotent delivery.

### 9.3. Signals, Updates, Queries

- **Update:** пользовательская/сервисная команда, требующая синхронной валидации и подтверждения приёма в состояние Workflow (например, принять решение по ожидающему review, если workflow должен проверить допустимость). До Update выполняется обычная Backend authz; Update handler повторно проверяет workflow preconditions.
- **Signal:** асинхронное событие без немедленного результата (например, уведомление о завершении внешней sync или поступлении source change). Дедупликация обязательна.
- **Query:** read-only диагностика runtime состояния. UI и доменные экраны читают canonical domain state из Backend API, а не делают Temporal Query как источник истины.
- Не экспонировать Temporal Workflow IDs как публичные управляющие ресурсы и не открывать Temporal Web UI пользователям.

### 9.4. Идентификаторы и идемпотентность

Связать `operationId`, `projectId`, `epicId`, `planVersionId`, `taskId`, `workerRunId`, `contextPackageVersionId`, `temporalWorkflowId`, `langgraphThreadId`, `traceId`. Workflow ID строится детерминированно в пределах namespace/типизированного scope; повторный start не должен создавать дублирующий бизнес-процесс. Activities, создающие внешние side effects, используют idempotency key и reconciliation.

### 9.5. Versioning

Workflow contract version и Worker build/version фиксируются при запуске. Для долгоживущих Workflow применять Temporal Worker Versioning как основной механизм после проверки SDK/локального режима; patching — совместимый fallback. Изменение Activity/Workflow command sequence должно пройти Temporal replay/compatibility tests. Ссылки на текущие Temporal рекомендации приведены в разделе 18.

## 10. LangGraph contracts

- Каждый WorkerDefinition имеет зарегистрированный graph implementation и graph contract version.
- `thread_id` связывается с `workerRunId` (или детерминированным thread ID, scoped на WorkerRun); не использовать один общий thread на весь Project.
- Checkpointer — отдельная схема/таблицы PostgreSQL, доступ только соответствующему Runtime/service role.
- Graph state содержит минимальные raw typed facts/refs, необходимые для исполнения; не копирует всю доменную БД.
- `interrupt()` применяется для внутренних пауз графа; основной долгоживущий Epic lifecycle и ожидание пользователя контролируются Temporal.
- При resume использовать тот же `thread_id` и validated resume payload. Повторно выполняемые узлы должны быть идемпотентны или не содержать side effects до подтверждённой точки.
- LangGraph events/stream не являются доменными событиями и не заменяют Audit/Outbox.

## 11. LLM Gateway Adapter contract

Manager и Workers обращаются только к внутреннему `LLMGatewayPort`, не к Bifrost API напрямую.

Минимальный normalized request: `requestId`, `modelProfileId`, `purpose`, `messages/input`, `responseSchemaRef`, `toolDefinitionsRef`, `stream`, `limits`, `dataClassification`, `traceContext`. Ответ: `provider/model identity`, `output`, `toolCalls`, `finishReason`, `usage`, `latency`, `providerRequestRef`, normalized error. Потоковые chunks типизированы.

- Model profile разрешается через AI RES configuration/policy; модель не выбирается произвольно Worker-ом вне разрешённого списка.
- Adapter нормализует несовпадения провайдеров, но не скрывает несовместимые возможности (например, structured output/tool calling support).
- Fallback разрешён только на policy-approved модель с совместимыми capabilities и классификацией данных.
- Secrets остаются на стороне Gateway/provider adapter; не возвращаются в Runtime и не попадают в контекст.
- Логируются безопасные метаданные и usage; prompts/responses не сохраняются по умолчанию.
- Bifrost остаётся основным кандидатом, pending PoC и security review.

## 12. Connector Platform contract

- Все provider-specific API/webhooks инкапсулированы в Connector Adapter.
- Общая операция описывает `provider`, `connectionId`, `operation`, `objectType`, `externalId`, `cursor/versionMarker`, `idempotencyKey`, `requestedScope`.
- Provider response преобразуется в normalized Source/ExternalObject/ChangeSet input; provider raw payload хранится только по разрешённой retention/policy.
- Webhook: validate signature → replay protection → deduplicate → fetch authoritative current object → compare version → ingest → emit event.
- MVP GitHub/GitLab read-only; write/bidirectional sync не открывать только потому, что provider API это позволяет.
- Rate limit, pagination, cursor, retry, partial sync, reconciliation и schema drift — обязательная часть Adapter contract.

## 13. Domain event contract

### 13.1. Envelope

Использовать CloudEvents 1.0 JSON envelope. Обязательные атрибуты: `specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, `dataschema`, `correlationid` (extension), `traceparent` (extension), `data`.

`data` содержит только typed domain payload и ссылки/IDs, не секреты и не полные чувствительные документы. Event version фиксируется в `type` или `dataschema`, не в произвольном поле.

### 13.2. Примеры event types

- `aires.project.created.v1`
- `aires.epic.plan.proposed.v1`
- `aires.plan.version.approved.v1`
- `aires.task.created.v1`
- `aires.task.state.changed.v1`
- `aires.requirement.candidate.registered.v1`
- `aires.requirement.version.created.v1`
- `aires.source.version.ingested.v1`
- `aires.source.change.detected.v1`
- `aires.impact.assessment.completed.v1`
- `aires.artifact.version.created.v1`
- `aires.artifact.validation.completed.v1`
- `aires.review.decision.recorded.v1`
- `aires.approval.recorded.v1`
- `aires.baseline.created.v1`
- `aires.worker.run.started.v1`
- `aires.worker.run.completed.v1`
- `aires.worker.run.blocked.v1`
- `aires.integration.sync.completed.v1`

### 13.3. Delivery guarantees

- Outbox transaction atomically records domain change and event.
- Delivery is at-least-once; exactly-once across DB/Temporal/external provider is not assumed.
- Consumers deduplicate by `event.id`, store processed event/inbox marker and are idempotent.
- Out-of-order events handled via aggregate ID + aggregate version/sequence; stale event cannot overwrite newer state.
- Failed delivery uses bounded retries and DLQ/quarantine with alert and controlled replay.
- No RabbitMQ/Kafka is introduced for MVP; Postgres Outbox + dispatcher is sufficient. Temporal handles durable workflow control, not general event bus replacement.

## 14. Audit, trace and correlation

Every API/command/event/run propagates `traceparent` (W3C Trace Context), `correlationId`, `causationId` where applicable, and domain IDs. AuditEvent is written by trusted application services for material actions. Telemetry loss must not cause domain action failure except when audit persistence is a mandatory transaction invariant for a critical action. Do not use high-cardinality domain IDs as Prometheus labels.

## 15. Contract compatibility and versioning

- Public REST major version in path (`/api/v1`); backward-compatible additive changes within v1.
- Breaking change requires `/api/v2` or explicit migration/deprecation policy.
- JSON schema has `$id`, `$schema`, `title`, `description`, strict required fields and controlled `additionalProperties` policy. For core envelopes, reject unknown fields unless an extension object is explicitly provided; for extensible metadata use namespaced `extensions`.
- Event type and schema version immutable once published; new incompatible shape gets `.v2` type.
- WorkerRunEnvelope/WorkerResult `contractVersion` explicit; Runtime must reject unsupported major version before execution/persistence.
- Deprecation includes `Deprecation` and `Sunset` headers where applicable, migration guide, telemetry and removal release.
- Generated clients are generated from committed contracts; generated code is not edited manually.

## 16. Error taxonomy

Machine-readable `code` is stable; `title/detail` may be localized and must not be parsed by clients. Minimum categories:

- `VALIDATION_ERROR` (422)
- `AUTHENTICATION_REQUIRED` (401)
- `ACCESS_DENIED` (403/controlled 404)
- `RESOURCE_NOT_FOUND` (404)
- `STATE_TRANSITION_NOT_ALLOWED` (409)
- `VERSION_CONFLICT` (412)
- `PRECONDITION_REQUIRED` (428)
- `IDEMPOTENCY_KEY_REUSED` (409)
- `RATE_LIMITED` (429; include Retry-After)
- `DEPENDENCY_UNAVAILABLE` (503/502)
- `OPERATION_NOT_READY` (409/422 per defined condition)
- `POLICY_ENGINE_UNAVAILABLE` (503; critical writes fail closed)
- `INTERNAL_ERROR` (500)

Do not reveal whether a protected resource exists if anti-enumeration policy requires 404.

## 17. Contract testing and quality gates

1. OpenAPI lint and validation in CI.
2. JSON Schema validation for WorkerRunEnvelope, WorkerResult, WorkerNotice, domain events and command payloads.
3. Consumer-driven contract tests for Frontend↔Backend and Runtime↔Platform API.
4. Provider tests verify real handler matches OpenAPI examples/schemas.
5. Negative tests for unknown enum, missing scope, stale ETag, duplicate idempotency key, wrong project, invalid transition, unsupported contract major.
6. Temporal workflow replay/compatibility tests and Activity idempotency tests.
7. Outbox duplicate, delay, reorder and poison-message tests.
8. SSE reconnect, Last-Event-ID, ACL filtering and retention-gap tests.
9. LLM Gateway Adapter contract tests against a mock and selected Bifrost PoC; no production provider key in CI.
10. Connector adapter contract tests with provider sandbox/fixtures, signature replay and rate limit cases.
11. Security tests: object-level authorization, cross-project IDOR, service identity misuse, secret leakage, prompt injection payload isolation.
12. Breaking change detection against last released contract.

## 18. Machine-readable companion contracts

- `AI_RES_Public_API_v1.0.yaml` — initial normative OpenAPI vertical slice; full MVP endpoint catalog and semantics are defined in this document and must be progressively represented in OpenAPI before implementation of each endpoint.
- `AI_RES_Domain_Events_AsyncAPI_v1.2.yaml` — logical event catalogue for the MVP event envelope.
- `AI_RES_Worker_Contracts_v1.1.schema.json` — JSON Schema 2020-12 definitions for WorkerRunEnvelope, WorkerResult, WorkerNotice and shared evidence references.
- The local `$id` base URI in the starter schema is a placeholder for the project's controlled schema registry/documentation URI; it is not an instruction to expose a public service at that host.

## 19. Official technical references

- OpenAPI 3.1.1 and 3.2.1: https://spec.openapis.org/oas/ (3.2.1 was published 10.09.2026; 3.1.1 selected as MVP compatibility baseline).
- JSON Schema 2020-12: https://json-schema.org/specification
- AsyncAPI 3.1.0: https://www.asyncapi.com/docs/reference/specification/v3.0.0 and https://github.com/asyncapi/spec/releases
- RFC 9457 Problem Details: https://www.rfc-editor.org/rfc/rfc9457.html
- Temporal message passing: https://docs.temporal.io/encyclopedia/workflow-message-passing
- Temporal Workflow determinism and versioning: https://docs.temporal.io/workflow-definition
- Temporal worker versioning: https://docs.temporal.io/best-practices/worker
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts

External references inform implementation details. AI RES domain semantics, permissions, worker contracts and workflow boundaries are project-specific design decisions.

## 20. Open parameters (not blockers for contract architecture)

1. Identity Provider product and exact OIDC claims/scopes.
2. Backend language/framework and generated SDK language.
3. Whether internal Runtime API uses HTTP/JSON or gRPC after PoC; MVP default is internal HTTP/JSON for inspectability and ease of local Compose debugging.
4. Exact SSE event catalog and UI replay retention.
5. Final list of public endpoint operations per screen and permission matrix.
6. Concrete schema for each specialized Requirement/Artifact subtype.
7. Numerical API rate limits, payload sizes and timeout budgets.
8. Final choice of OpenAPI 3.1.1 vs 3.2.1 after codegen compatibility test.

These choices must not lead to ad hoc or incompatible contracts. They are recorded as explicit implementation decisions before the corresponding component is built.


---

# Дополнение v1.1. Процессные события и их семантика

Процессы AI RES детализированы в `AI_RES_Process_Design_and_Algorithms_v1.0.md`. Для основных новых переходов расширен AsyncAPI контракт до `AI_RES_Domain_Events_AsyncAPI_v1.2.yaml`.

Дополнительные типизированные события:

| Event | Смысл |
|---|---|
| `aires.plan.version.proposed.v1` | Manager сформировал предложение PlanVersion |
| `aires.readiness_gate.completed.v1` | Gate завершился с результатом READY/BLOCKED/READY_WITH_LIMITATIONS/STALE |
| `aires.worker.result.submitted.v1` | WorkerResult передан на платформенную валидацию/приёмку |
| `aires.qa.review.completed.v1` | Независимая QA завершена с конкретным outcome |
| `aires.impact.assessment.completed.v1` | Impact Assessment завершён с I0–I4 категорией |
| `aires.change_request.approved.v1` | Change Request утверждён уполномоченным субъектом |
| `aires.baseline.created.v1` | Создана новая immutable Baseline |

События являются фактами, а не командами. Публикация — через Transactional Outbox; доставка at-least-once; consumers дедуплицируют event ID и защищаются aggregate version/sequence. Payload содержит минимальные typed refs и не содержит секретов, полного текста документов или chain-of-thought.

Точный полный каталог lifecycle событий расширяется по мере появления подтверждённых доменных переходов. Нельзя публиковать событие только потому, что LLM предложила соответствующее действие: сначала должна успешно завершиться доменная транзакция.


---

# Дополнение v1.2. Worker Coordination Contract

## 1. Семантика

Worker-to-Worker — контролируемая логическая координация, не прямой
сетевой вызов между Runtime. Worker создаёт `WorkerCoordinationRequest`;
Manager принимает содержательное решение; Policy Engine независимо
проверяет права; Temporal исполняет согласованный Run.

## 2. Типы запросов

- `CONSULTATION`: короткий ограниченный запрос информации/экспертного
  уточнения; исходный Worker остаётся владельцем основной задачи.
- `DELEGATED_SUBTASK`: Manager создаёт отдельную Task/PlanItem либо
  ограниченную подзадачу, если требуется самостоятельный результат.
- `HANDOFF`: Manager передаёт дальнейшее выполнение или выделенную часть
  работы другому Worker и явно определяет судьбу исходного Run.
- `INDEPENDENT_QA`: не является Worker-initiated coordination request;
  создаётся Manager/Review workflow как отдельный независимый Review Run.

## 3. WorkerCoordinationRequest

Минимальные поля:
- `coordinationRequestId`, `contractVersion`;
- `sourceWorkerRunId`, `taskId`, `epicId`, `projectId`;
- `requestType`, `purpose`, `rationale`;
- `targetCapability` (предпочтительная компетенция, не обязательное
  назначение конкретного Worker);
- `inputRefs` (только typed refs, доступность которых проверяется ACL);
- `expectedOutputSchema` и `acceptanceCriteria`;
- `proposedDependency`;
- `requestedAt`, `correlationId`, `idempotencyKey`.

Lifecycle:
`REQUESTED → MANAGER_REVIEW → POLICY_CHECK → APPROVED → SCHEDULED →
COMPLETED`, с альтернативами `REJECTED`, `NEEDS_CLARIFICATION`,
`BLOCKED`, `CANCELLED`, `EXPIRED`.

Manager decision и Policy decision — независимые поля/записи:
- Manager: approve/reject/clarify/convert-to-task, rationale, target role;
- Policy: allow/deny, allowed resources/operations, grant refs, expiry.

## 4. Новый WorkerRun

Envelope для дополнительного запуска должен включать:
- `runPurpose`: `PRIMARY`, `CONSULTATION`, `DELEGATED_SUBTASK`,
  `INDEPENDENT_QA`;
- `parentWorkerRunId` (если запуск производный);
- `coordinationRequestId` (для consultation/delegated subtask/handoff);
- `reviewId` (для independent QA).

`runPurpose`: `PRIMARY`, `CONSULTATION`, `DELEGATED_SUBTASK`, `HANDOFF`,
`INDEPENDENT_QA`. Для CONSULTATION/DELEGATED_SUBTASK/HANDOFF обязательны
`parentWorkerRunId` и `coordinationRequestId`; для INDEPENDENT_QA обязательны
`parentWorkerRunId` и `reviewId`. Для PRIMARY производные refs не требуются.

Каждый дополнительный Run получает собственные:
WorkerDefinition, ContextPackageVersion, scoped grants, budgets,
output contract и GateResult. Grants/секреты исходного Run не
наследуются. Передаваемые документы/данные доступны только через
разрешённые refs.

## 5. Ограничения

- Worker не вызывает Worker Runtime напрямую и не управляет Temporal.
- Worker не создаёт доменные Task/PlanItem и не меняет global Plan.
- Manager не может одобрить доступ, который Policy Engine запретил.
- Policy Engine не решает, нужна ли содержательно консультация или
  передача работы; это решение Manager.
- Temporal не выбирает целевую специализацию; он исполняет одобренную
  orchestration command.
- Нет свободного group chat/роя в MVP.
- Все coordination requests ограничиваются max depth, max outstanding
  requests, time, token/cost budgets и anti-cycle checks.

## 6. Manager acceptance и verification status

`ACCEPTED_FOR_ORCHESTRATION` — разрешение использовать результат в
следующем шаге; не означает `VERIFIED`.
Verification: `VERIFIED`, `VERIFIED_WITH_LIMITATIONS`, `DISPUTED`,
`UNVERIFIED`. QA outcome хранится отдельно. Human Approval — отдельная
запись с approver identity и exact object/version refs.

Manager уровня B может adjudicate low-risk disagreement с rationale и
evidence. При обязательной high/critical QA unresolved disagreement
блокирует fully verified и соответствующий downstream gate. Ограниченное
orchestration продолжение возможно только если policy явно допускает и
оно не нарушает критический gate.

## 7. Readiness Gate responsibilities

Manager предоставляет semantic Readiness Request и оценивает, что задача
достаточно хорошо определена. Platform Gate Evaluator проверяет
машинно-проверяемые условия: registered WorkerDefinition/capability
metadata, supported contract version, Task/Plan/dependencies,
ContextPackageVersion, grants, tool allowlist, output schema, budgets и
policy. Gate не должен подменять семантическую оценку LLM-решением и
наоборот.



## Дополнение v1.3 — согласование аутентификации и Operation lifecycle

1. Для MVP browser API использует непрозрачную серверную сессию в cookie `ai_res_session`; локальный login/logout и session lifecycle определены в `AI_RES_Authentication_and_Session_Management_v1.0.md`. OIDC/JWT не является обязательной схемой browser API MVP.
2. CSRF-защита обязательна для cookie-authenticated state-changing requests. Конкретные login/logout/MFA HTTP endpoints и их request/response schemas должны быть включены в OpenAPI до реализации соответствующего UI/auth flow; текущий Public API contract описывает защищённый API slice и не является полным auth endpoint catalogue.
3. Канонический Operation status set: `ACCEPTED`, `QUEUED`, `RUNNING`, `WAITING_FOR_HUMAN`, `WAITING_FOR_DEPENDENCY`, `RETRYING`, `CANCEL_REQUESTED`, `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `CANCELLED`. Терминальность и допустимые переходы определяются процессной state machine. OpenAPI и Process Design должны использовать один и тот же набор.
4. Доменная модель пока не описывает Operation и ReadinessGate/GateResult как явные persistence entities. До реализации persistence необходимо принять решение об их владельце, хранении, retention и отношении к Temporal Workflow. См. Cross-Document Audit.


---

## Дополнение v1.4 — Operation и ReadinessEvaluation API semantics

### 21.1. Канонический Operation resource

`Operation` — persisted domain resource в `ai_res_db`; Temporal Workflow ID/Run ID являются техническими ссылками. API читает Operation из domain store. Любая команда, запускающая длительное действие, возвращает `202 Accepted` и ссылку на Operation после атомарного сохранения Operation + Outbox command.

Operation read model включает:
`id`, `organizationId`, optional `projectId`/`epicId`, `operationType`, `status`, `initiator`, `subjectRef`, `submittedAt`, optional `acceptedAt`/`startedAt`/`completedAt`, `lastProgressAt`, `resultRef`, safe `problem`, `correlationId`, `rowVersion`.
Не раскрывать idempotency internals, secrets, prompt, hidden source content или внутренние policy details.

Operation transition validation выполняется application service. OperationEvent — append-only; `sequence` монотонен в пределах Operation. Повторная команда с тем же idempotency key и fingerprint возвращает ту же Operation; тот же key с другим fingerprint — `IDEMPOTENCY_KEY_REUSED`.

### 21.2. Readiness Evaluation read model

`ReadinessEvaluation` — неизменяемая запись результата Gate; `ReadinessCheckResult[]` — детальные проверки. `GateResult` — термин/DTO представления, не отдельная таблица.

Безопасный read model для UI должен включать:
`id`, `workerRunId`, `evaluationNumber`, `outcome`, `evaluationStatus`, `evaluatedAt`, `summary`, `blockers[]`, `limitations[]`, безопасные `checkSummaries[]`, `isCurrent`, `supersededBy`.
Подробные evidence refs возвращаются только при наличии ACL на исходные объекты. Внутренние правила policy и секреты не раскрываются.

### 21.3. Рекомендуемые endpoint semantics

- `GET /api/v1/operations/{operationId}` — текущая Operation projection.
- `POST /api/v1/operations/{operationId}/cancel` — идемпотентный запрос отмены; 202 означает, что запрос принят, а не что Operation уже отменена.
- `GET /api/v1/worker-runs/{workerRunId}/readiness-evaluations` — история evaluations (MVP read-only, если включена в UI/API scope); доступ по project/object ACL.
- `GET /api/v1/readiness-evaluations/{evaluationId}` — опциональный detail endpoint; не обязателен для первого вертикального среза.
- Никакого публичного `POST /readiness-evaluations` для пользователя: evaluation инициируется application/workflow service. UI не может самостоятельно выставить READY.

### 21.4. Ошибки и concurrency

- Недопустимый Operation transition — `409 STATE_TRANSITION_NOT_ALLOWED`.
- Stale row version/ETag — `412 VERSION_CONFLICT`.
- Повтор ключа с иным payload — `409 IDEMPOTENCY_KEY_REUSED`.
- Operation за пределами ACL — controlled `404` либо `403` согласно anti-enumeration policy.
- Gate не готов — доменный результат `BLOCKED`, а не инфраструктурная ошибка HTTP; инициирующая Operation может оставаться `WAITING_FOR_DEPENDENCY`/`WAITING_FOR_HUMAN` либо завершиться по policy.
- Evaluator/Policy Engine unavailable — запуск запрещён; причина отображается безопасным кодом, техническая диагностика остаётся в audit/telemetry.


---

## Дополнение v1.5 — Operation/WorkerRun lifecycle contracts

Нормативные lifecycle definitions: Architecture Decision v1.2, Process Design v1.4, state machine JSON v1.1, Public OpenAPI v1.3, AsyncAPI v1.4.

### Operation resource
Operation API представляет корневую/дочернюю команду и безопасную агрегированную проекцию. Поля дополнительно включают `parentOperationId`, `rootOperationId`, `completionPolicyVersion`, `aggregateVersion`, `progress` (structured counts/phase, без псевдоточной процентовки), `resultRef`, `partialResultReasons`, `childOperationRefs`. API не раскрывает скрытые Task/WorkerRun/evidence при отсутствии ACL.

### WorkerRun resource
WorkerRun read model включает `operationId`, `taskId`, `status`, `rowVersion`, `workerDefinitionVersionId`, `contextPackageVersionId`, `latestReadinessEvaluationId`, `startedWithReadinessEvaluationId`, `derivedFromWorkerRunId`, `derivationReason`, `attemptNumber`, timestamps, safe `problem`, `resultRef`, `reviewRefs`, `qaReviewRef`. `startedWithReadinessEvaluationId` обязателен после старта; не выдавать internal prompt/tool secrets.

Status mutation не предоставляется как произвольный PATCH. Переходы вызываются доменными командами/внутренними application services. Публичные действия ограничиваются явно разрешёнными user intents (например, отмена Operation/WorkerRun, human response/approval через отдельные endpoints). Все команды требуют idempotency key, authorization, expected version where applicable, CSRF for browser session and audit.

### Semantics
`WorkerRun.COMPLETED` не означает human approval, QA pass, Artifact approval/publication или baseline. `REWORK_REQUIRED` создаёт новый WorkerRun по Manager decision; прежний Run остаётся terminal. `BLOCKED` — текущая Gate disposition, `STALE` — Gate outcome, не WorkerRun status. `CANCEL_REQUESTED` не равен `CANCELLED`.

### Events
WorkerRun/Operation domain events публикуются из transactional outbox только после commit. Consumer должен быть idempotent по event ID; порядок обеспечивается aggregate sequence, не глобальным порядком доставки. Payload содержит IDs, versions, safe refs, transition, reasonCode, correlationId, causationId, aggregateVersion. Никаких секретов, prompt или полного документа.

### Error model
`INVALID_STATE_TRANSITION`, `VERSION_CONFLICT`, `IDEMPOTENCY_KEY_REUSED`, `READINESS_NOT_SATISFIED`, `READINESS_STALE`, `CANCELLATION_OUTCOME_PENDING`, `OPERATION_TERMINAL`, `WORKER_RUN_TERMINAL`, `ACL_SCOPE_MISMATCH` — типизированные machine-readable errors. Не раскрывать существование недоступных ресурсов.


## Дополнение v1.6 — Operation/WorkerRun event contracts

Нормативный документ: `AI_RES_Operation_WorkerRun_Event_Model_v1.0.md`; AsyncAPI: `AI_RES_Domain_Events_AsyncAPI_v1.5.yaml`.

### 19.1 Event identity and envelope
Все доменные события Operation/WorkerRun публикуются как CloudEvents 1.0. Event `id` стабилен при redelivery; `type` содержит major version; `data.schemaVersion` — версия payload. Обязательны aggregate type/id/sequence/version, organization/project/operation IDs, actor type/id, correlationId, causationId, occurredAt и typed refs. Не включать секреты, prompts, chain-of-thought, full result/source body или provider raw payload.

### 19.2 Ordering and delivery
At-least-once; dedupe по event ID; строгий порядок только внутри aggregate. Глобальный порядок между Operation и WorkerRun не обещается. Consumers используют Inbox и sequence checkpoint; gap откладывается, не пропускается. SSE выдаёт только ACL-filtered projection и не является прямой подпиской на Outbox.

### 19.3 Command idempotency
Команды создания Operation/WorkerRun и cancel используют idempotency key с scope `(organizationId, actorScope, operationName, key)` и canonical request fingerprint. Same key + same fingerprint возвращает тот же resource/result; same key + different fingerprint — HTTP 409 `IDEMPOTENCY_KEY_REUSED`. Для optimistic concurrency применять `If-Match`/expected version; mismatch — HTTP 409 `AGGREGATE_VERSION_CONFLICT`.

### 19.4 Event history API
При реализации endpoint чтения истории возвращать пагинируемый ACL-filtered список событий с `eventId`, `eventType`, `schemaVersion`, `aggregateSequence`, `aggregateVersion`, `occurredAt`, actor summary, reasonCode, transition и safe refs. Не отдавать raw Outbox payload, hidden fields или evidence content без отдельного ACL-protected resource request. События immutable; API не предоставляет update/delete.

### 19.5 Canonical event names
`worker_run.accepted` deprecated; использовать `worker_run.completed`. `worker_run.gate_evaluation_completed` — связь WorkerRun с ReadinessEvaluation; полный evaluation lifecycle публикуется как `readiness_evaluation.*`. `operation.progress_updated` informational/coalescible и не является source of truth. Подробный каталог и compatibility policy — в `AI_RES_Operation_WorkerRun_Event_Model_v1.4.md` и `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml`.

---

## Дополнение v1.7 — API idempotency и persistence guarantees

**Статус:** нормативное дополнение, согласованное с PostgreSQL Physical Model v1.0.

### Persistence semantics exposed through API

- Create Operation и другие idempotent command endpoints выполняют authentication/authorization до доменной транзакции.
- `Idempotency-Key` имеет scope по actor/organization/project и command endpoint согласно API operation policy; сервер хранит только HMAC digest, не raw key.
- Совпадающий key + fingerprint возвращает исходный resource/response; несовпадающий fingerprint возвращает `409 IDEMPOTENCY_KEY_REUSED`.
- Ответ `202 Accepted` означает, что Operation committed в `ai_res_db` вместе с `operation.accepted` Event History и Outbox; это не подтверждает старт Temporal Workflow.
- Ошибка dispatcher после commit не превращает принятый запрос в API failure: Operation остаётся принятой, доставка восстанавливается Outbox.
- Cancel API означает принятие запроса на отмену, а не гарантированное завершение отмены. Терминальный результат доступен через Operation read model после reconciliation.
- API не раскрывает внутренние Outbox lease, Inbox payload, raw event transport или Temporal internals. Event history выдаётся только через ACL-filtered read projection.
- Доменная DB transaction не охватывает Temporal RPC, LLM, tool/HTTP call или human wait.

Физические ограничения и TX-01..TX-09 определены в `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.0.md`. Wire schema OpenAPI v1.3 не меняется этим дополнением; новые endpoint/field contracts не вводятся.


---

## Дополнение 1.8 — PostgreSQL access boundaries

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.

Application Services — единственная доменная DB write boundary. Worker/Manager взаимодействуют через внутренние API/Temporal Activities и scoped grants; прямой SQL доступ Runtime запрещён. DB role permissions не заменяют API-level BOLA/IDOR, ACL и Policy Engine checks. API transaction scope устанавливает tenant context локально для конкретной транзакции; session-level tenant GUC запрещён из-за connection pooling.


## Дополнение v1.9 — Persistence boundary contract

Внешний API и Runtime не получают SQL connection или DB credentials. API/Application Services выполняют серверную аутентификацию, Policy Engine authorization, установку transaction-local tenant context и вызов Domain Services. Manager/Worker Runtime взаимодействуют через внутренние сервисные контракты и не читают/пишут PostgreSQL напрямую.

Для каждой доменной команды Application Service задаёт единую транзакционную границу: idempotency reservation, aggregate lock/CAS, domain validation, projection update, event history, Outbox и commit. Внешний side effect после commit выполняется dispatcher/consumer с Inbox/Outbox semantics. Технические детали и тесты — `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`.


---

## Дополнение v1.10 — актуализация нормативных ссылок

**Статус:** BASELINED contract design; реализация endpoints не заявляется.

Текущие нормативные источники: Architecture Concept v4.6; Domain Model v1.9; Process Design v1.9; Public OpenAPI v1.3 (начальный public vertical slice); AsyncAPI v1.6; Operation/WorkerRun Event Model v1.4; Persistence Implementation Blueprint v1.0; Identity & Access Control v1.5; Authentication & Session Management v1.1. Полный список актуальных файлов определяется Registry v4.0.

Исторические ссылки на API Contracts v1.2–v1.9, AsyncAPI v1.0–v1.5 и ранние OpenAPI версии внутри предыдущих дополнений не являются текущими зависимостями. Wire contract OpenAPI v1.3 остаётся ограниченным vertical slice и не объявляется полным покрытием всего API.
