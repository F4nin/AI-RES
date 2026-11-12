# CONTRACT_TRACEABILITY_MAP

Связь: публичный API (DOC-050 `AI_RES_Public_API_v1.3.yaml`) ↔ доменные агрегаты (DOC-005) ↔ физические таблицы (DOC-065 DDL / ADR-016) ↔ события (DOC-008 `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml`) ↔ инкремент ↔ тесты.
Статус реализации всех строк: **NOT_STARTED**. Этапы — по `IMPLEMENTATION_ROADMAP.md` (ADR-010). Зеркало контрактов в `contracts/` — ADR-009 (S01). Таблицы с пометкой «ADR-016» не имеют физического DDL в baseline. Статусы источников в Registry: DOC-050 Public API — **WORKING**, DOC-065 DDL — **WORKING**, DOC-008 AsyncAPI — BASELINED.

## Public API v1.3 (26 операций)

| operationId | Метод / путь | Агрегат | Таблица | Заголовки контракта | События | Этап |
|---|---|---|---|---|---|---|
| getCurrentUser | GET /me | User/Session | `iam.*` (ADR-016) | cookie session | — | S07 — IMPLEMENTED/TESTED (`test_identity_http`, live stack) |
| listProjects | GET /projects | Project | `project.projects` (ADR-016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| createProject | POST /projects | Project | `project.projects` | Idempotency-Key; ETag в 201 | ProjectCreated | S09 IMPLEMENTED |
| getProject | GET /projects/{projectId} | Project | `project.projects` | ETag | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| updateProjectMetadata | PATCH /projects/{projectId} | Project | `project.projects` | If-Match | — (нет сообщения AsyncAPI, G-93) | S09 IMPLEMENTED |
| listEpics | GET /projects/{projectId}/epics | Epic | `work.epics` (ADR-016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| createEpic | POST /projects/{projectId}/epics | Epic | `work.epics` | Idempotency-Key | EpicCreated | S09 IMPLEMENTED |
| getEpic | GET /epics/{epicId} | Epic | `work.epics` | — (ETag в OAS не объявлен) | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| sendManagerMessage | POST /epics/{epicId}/manager-messages | Manager interaction → Operation | `operations.operations` | Idempotency-Key, 202 | ManagerInteractionReceived, Operation* | S20 |
| listTasks | GET /epics/{epicId}/tasks | Task | `work.tasks` (ADR-011/016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| createTask | POST /epics/{epicId}/tasks | Task | `work.tasks` (+ владеющая Operation — ADR-012) | Idempotency-Key; 201 | TaskCreated | S21 (перенос из S09: ADR-012, NCP-08; ADR-078) |
| getTask | GET /tasks/{taskId} | Task | `work.tasks` | ETag | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| listRequirements | GET /projects/{projectId}/requirements | Requirement | `requirements.requirements` (ADR-016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| registerRequirementCandidate | POST /projects/{projectId}/requirements | Requirement | `requirements.*` | Idempotency-Key | RequirementVersionCreated | S09 IMPLEMENTED |
| listRequirementVersions | GET /requirements/{id}/versions | RequirementVersion | `requirements.requirement_versions` | — | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| proposeRequirementVersion | POST /requirements/{id}/versions | RequirementVersion | `requirements.requirement_versions` | If-Match, Idempotency-Key | RequirementVersionCreated | S09 IMPLEMENTED |
| listSources | GET /projects/{projectId}/sources | Source | `sources.*` (ADR-016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| createUploadIntent | POST /uploads | Upload | `sources.uploads` (ADR-016) | Idempotency-Key | — | S09 IMPLEMENTED (хранилище не проверено, G-92) |
| completeUpload | POST /uploads/{uploadId}/complete | Upload → Operation → SourceVersion | `operations.operations`, `sources.source_versions` | Idempotency-Key; **202 + Operation** | Operation*, SourceVersionIngested | S12 |
| listArtifacts | GET /projects/{projectId}/artifacts | Artifact | `artifacts.*` (ADR-016) | Limit, Cursor | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| listArtifactVersions | GET /artifacts/{id}/versions | ArtifactVersion | `artifacts.artifact_versions` | — | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| getWorkerRun | GET /worker-runs/{workerRunId} | WorkerRun | `agents.worker_runs` (DDL) | — | — | S08 — IMPLEMENTED/TESTED (`test_read_api`, `test_read_api_schemathesis`) |
| streamProjectEvents | GET /projects/{projectId}/events | SSE projection | event history: `operations.operation_events`, `agents.worker_run_events`, доменные event history (ADR-016); **не** `audit.outbox_events` (очередь доставки; у API нет USAGE на `audit`, DOC-069) | Last-Event-ID | все авторизованные; retention — WORKING | S12 |
| getOperation | GET /operations/{operationId} | Operation | `operations.operations` (DDL) | — | — | S12 |
| requestOperationCancellation | POST /operations/{id}/cancel | Operation | `operations.operations` | Idempotency-Key | OperationCancelRequested | S12 |
| listWorkerRunReadinessEvaluations | GET /worker-runs/{id}/readiness-evaluations | ReadinessEvaluation | `execution.readiness_evaluations` (DDL) | — | ReadinessGate* (`gateResultId` → DR-04) | S22 |

## AsyncAPI v1.6 (78 сообщений) — группы

| Группа | Сообщения | Таблицы-источники | Этапы |
|---|---|---|---|
| Operation (16) | OperationAccepted…OperationWaitingForHuman, OperationFailedV1, OperationStateChanged, OperationChildCreated | `operations.operations`, `operations.operation_events` | S10, S12 |
| WorkerRun (26) | WorkerRunCreated…WorkerRunWaitingForHuman, WorkerRunFailedV1, WorkerResultSubmitted (`WorkerRunAccepted` — deprecated, AsyncAPI info) | `agents.worker_runs`, `agents.worker_run_events`, `agents.worker_results` (DDL отсутствует — DR-09) | S14, S23 |
| Readiness Gate (3) | ReadinessGateBlocked/Completed/Stale | `execution.readiness_evaluations`, `execution.readiness_check_results` | S22 |
| Task / Plan / Epic / Project (14) | TaskCreated…TaskStateChanged, PlanVersion*, PlanReplanned, EpicCreated, EpicGoalUpdated, ProjectCreated | ADR-016 | S09, S21 |
| Requirements / Sources / Impact (5) | RequirementVersionCreated, SourceVersionIngested, SourceChangeDetected, ImpactAssessmentCompleted, ImpactRevalidationRequired | ADR-016 | S09, S27, S30 |
| Artifact / CR / Baseline (7) | ArtifactVersionCreated, ArtifactValidationCompleted, ArtifactApproved, ArtifactPublished, ChangeRequestCreated/Approved, BaselineCreated | ADR-016 | S31 |
| Coordination / QA / Manager (7) | WorkerCoordination*, QAReview*, ManagerQuestionProposed, ManagerInteractionReceived | ADR-016 | S20, S24, S25 |

Транспорт всех событий: `audit.outbox_events` → dispatcher → `audit.inbox_messages` (DDL v1.0).

## Execution slice DDL v1.0 (DOC-065)

Есть в DDL: `operations.operations`, `operations.operation_events`, `agents.worker_runs`, `agents.worker_run_events`, `execution.readiness_evaluations`, `execution.readiness_check_results`, `platform.idempotency_records`, `audit.outbox_events`, `audit.inbox_messages`.
Требуются DOC-064 v1.2, но отсутствуют в DDL (DR-09): `agents.worker_results`, `audit.audit_events`, `work.task_dependencies`; `work.tasks` — только ALTER.

## Overlay S07 — `contracts/openapi/extensions/identity_auth.yaml` (WORKING, ADR-038/063; формализация — NCP-06)

| operationId | Метод / путь | Агрегат | Таблица | Заголовки контракта | События | Этап / тесты |
|---|---|---|---|---|---|---|
| login | POST /auth/login | Session | `iam.sessions`, `iam.credentials` | Origin; `x-idempotency-exempt` | — (аудит `AUTH_LOGIN_*`) | S07 — `test_identity_http`, `test_iam_login` |
| logout | POST /auth/logout | Session | `iam.sessions` | Origin, X-CSRF-Token | — | S07 — `test_identity_http` |
| getCsrfToken | GET /auth/csrf | Session | `iam.sessions` | cookie | — | S07 |
| changePassword | POST /auth/password | Credential | `iam.credentials` | Origin, X-CSRF-Token | — | S07 — `test_identity_http`, `test_iam_login` |
| beginMfaEnrollment | POST /auth/mfa/enrollment | MFA factor | `iam.mfa_factors` | Origin, X-CSRF-Token | — | S07 — `test_iam_mfa` |
| confirmMfaEnrollment | POST /auth/mfa/enrollment/confirm | MFA factor | `iam.mfa_factors`, `iam.mfa_recovery_codes` | Origin, X-CSRF-Token | — | S07 |
| verifyMfa | POST /auth/mfa/verify | Session | `iam.sessions`, `iam.mfa_factors` | Origin, X-CSRF-Token | — | S07 |
