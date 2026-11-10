# AI RES — Спецификация реализации API и контрактов для Claude Code

**Версия:** 1.22  
**Дата:** 10.11.2026  
**Статус:** implementation brief; использовать только совместно с актуальным Document Registry и перечисленным ниже baseline. Не является разрешением перепроектировать домен.  
**Основная спецификация:** `AI_RES_API_and_Interaction_Contracts_v1.10.md`.

## 1. Назначение

Документ предназначен для передачи Claude Code как implementation brief. Он задаёт границы реализации, порядок работ, ограничения, ожидаемые файлы, тесты и Definition of Done. Claude Code должен сначала изучить все перечисленные проектные документы и репозиторий, затем реализовывать небольшими вертикальными инкрементами.

## 2. Обязательные документы для изучения перед изменением кода

Claude Code MUST сначала прочитать `AI_RES_Document_Registry_v4.0.md`, затем использовать только canonical current files из его раздела 2. Исторические версии, старые ссылки в предыдущих addenda и ZIP snapshots не являются нормативными источниками. Минимальный набор для старта включает:

### Product, requirements, domain, process and UX
- `AI_RES_Agent_Architecture_Concept_v4.6.md`
- `AI_RES_MVP_Capability_Matrix_v3.3.md`
- `AI_RES_Requirements_Lifecycle_v2.6.md`
- `AI_RES_UX_Concept_v1.2.md`
- `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md`
- `AI_RES_Process_Design_and_Algorithms_v1.9.md`
- `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.1.md`
- `AI_RES_Glossary_v1.1.md` and `AI_RES_Glossary_v1.1.json`

### API, events, execution and persistence
- `AI_RES_API_and_Interaction_Contracts_v1.10.md`
- `AI_RES_Public_API_v1.3.yaml` (initial public vertical slice; not the full API catalogue)
- `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml`
- `AI_RES_Worker_Contracts_v1.1.schema.json`
- `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md`
- `AI_RES_Operation_WorkerRun_Event_Model_v1.4.md`
- `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json`
- `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md`
- `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md`
- `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`

### Knowledge, tools, integrations and model access
- `AI_RES_Source_and_Context_Lifecycle_v1.2.md`
- `AI_RES_Knowledge_Memory_Retrieval_Architecture_v1.0.md`
- `AI_RES_Tool_Registry_and_Tool_Management_MVP_v1.0.md`
- `AI_RES_External_Integrations_and_Project_Context_v1.1.md`
- `AI_RES_Model_Gateway_and_Model_Registry_v1.0.md`
- `AI_RES_Evaluation_and_Release_Gates_v1.0.md`
- `AI_RES_Learning_Experience_Lifecycle_v1.0.md`
- `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.2.md`
- `AI_RES_Continuous_Improvement_Requirements_v1.2.md`
- `AI_RES_Continuous_Improvement_Contracts_v1.1.md`

### Security, identity, infrastructure and operations
- `AI_RES_Security_Architecture_v1.2.md`
- `AI_RES_Threat_Model_v1.1.md`
- `AI_RES_Identity_Access_Control_v1.5.md`
- `AI_RES_Authentication_and_Session_Management_v1.1.md`
- `AI_RES_Secrets_and_Key_Management_v1.1.md`
- `AI_RES_Security_Controls_and_Requirements_v1.2.md`
- `AI_RES_Infrastructure_Deployment_Operations_v1.7.md`
- `AI_RES_Observability_Architecture_v1.1.md`
- `AI_RES_Agent_Observability_and_Evaluation_v1.1.md`
- `AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md`
- `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md`
- `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md`
- `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md`
- `AI_RES_Methodology_and_Source_Traceability_Matrix_v1.2.md`

If any canonical file is absent or its contents contradict the Registry, stop the affected increment and produce a discrepancy report. Do not silently choose an older file or rewrite architecture.

## 3. Non-negotiable architecture constraints

- Modular Backend; no microservice-per-domain decomposition in MVP.
- One `ai_res_db` PostgreSQL domain database; separate `temporal_db`; LangGraph checkpoint tables/schema isolated; MinIO for binaries; Redis optional and non-authoritative.
- Temporal is the durable workflow engine; LangGraph is internal agent reasoning.
- Manager Runtime and shared Worker Runtime pool are separate processes; nine Worker specializations are logical roles, not nine services/containers.
- Manager coordinates; Workers execute specialized tasks; Workflow Engine enforces execution mechanics.
- Readiness Gate is mandatory before every Worker Run.
- Manager/Workers do not access arbitrary SQL, Docker socket, arbitrary internet or raw provider APIs.
- Bifrost is the primary LLM Gateway candidate, pending PoC/security review. All LLM access through AI RES adapter.
- Connector Platform is the only route to external project systems; MVP GitHub/GitLab read-only.
- Project/domain state belongs to AI RES services and PostgreSQL, not Temporal or LangGraph checkpoint.
- All object access is organization/project/object scoped and authorized server-side.
- No automatic human approval, business decision approval, Baseline approval or permission escalation by an agent.
- Immutable versions, provenance, audit and traceability must be preserved.

## 4. Implementation sequence

### Increment 0 — repository reconnaissance and architecture plan

- Inspect current repository structure, language/framework, dependency lockfiles, existing conventions and tests.
- Produce a short implementation plan and identify missing prerequisites.
- Do not replace working stack choices or introduce new infrastructure without approval.
- Confirm OpenAPI 3.1.1 tooling; test OAS 3.2.1 compatibility separately before proposing migration.

### Increment 1 — contract toolchain

Create contract directories (adapt names to repository conventions, but preserve separation):

```text
contracts/
  openapi/
    public-api-v1.yaml
  asyncapi/
    domain-events-v1.yaml
  json-schema/
    common/
    worker/
    events/
    commands/
  examples/
```

- Validate OpenAPI, AsyncAPI and JSON Schema in CI.
- Add a contract lint rule set and breaking-change detection.
- Do not generate application code until schema validation passes.
- Pin tool versions in lock/config.

### Increment 2 — shared platform primitives

Implement, in order:
1. UUID and time serialization rules.
2. API Problem Details error model.
3. request/correlation/trace context propagation.
4. pagination contract.
5. ETag/If-Match and optimistic concurrency primitives.
6. Idempotency-Key storage and replay behavior.
7. authentication/service identity middleware integration points.
8. object-level authorization hooks and policy decision interface.
9. audit writer interface.

All middleware must have tests, including negative/security tests.

### Increment 3 — read-only vertical slices

Implement read paths first for Project, Epic, Task, Requirement, Source, Artifact and WorkerRun. Every query must enforce organization/project ACL. Add pagination, filtering, ETags and DTO mapping. Never return ORM entities directly.

### Increment 4 — controlled write commands

Implement writes with domain services, transaction boundaries, If-Match where version-sensitive, idempotency for side effects, audit and outbox. Start with Project/Epic/Task, then Requirement version proposals, then Source upload lifecycle and Artifact lifecycle. Do not expose generic state mutation endpoints.

### Increment 5 — asynchronous operations and UI events

Implement Operation resource, Temporal start/cancel integration and SSE. Ensure request returns 202 and operation reference for long-running tasks. SSE is a projection of authorized domain events; it is not a replacement for REST resource reads.

### Increment 6 — Manager/Worker runtime contracts

Implement typed WorkerRunEnvelope, WorkerResult and WorkerNotice schemas. Validate before enqueue, before Worker execution, before result persistence and before downstream consumption. Worker cannot write directly to domain DB. Result persistence occurs through trusted platform application services.

### Increment 7 — Temporal and LangGraph integration

Implement deterministic Workflow definitions and Activities for external effects. Keep payloads compact; use immutable refs. Use separate task queues already selected (`ai-res-manager`, `ai-res-workers`). Apply idempotency, bounded retries, timeout, heartbeat, cancellation and reconciliation. Test replay compatibility. Use LangGraph thread/checkpoint scoped to WorkerRun.

### Increment 8 — events and integrations

Implement Transactional Outbox, CloudEvents envelope, idempotent consumer/inbox marker, bounded retries and DLQ/quarantine. Add Connector Platform adapter contracts; GitHub/GitLab remain read-only. Do not add RabbitMQ/Kafka to MVP.

### Increment 9 — contract and security verification

Run full contract, integration, replay, idempotency, authorization, isolation, prompt injection, secret-leakage and failure-recovery suites. Provide evidence and test reports.

## 5. Required API and DTO behavior

- Public API base `/api/v1`; JSON `camelCase`; UUID identifiers; timestamps UTC RFC3339.
- REST endpoints follow `AI_RES_API_and_Interaction_Contracts_v1.2.md` endpoint catalog.
- Long-running work returns `202 Accepted` and an Operation resource; never hold request open for agent execution.
- Errors use RFC 9457; stable machine `code`; no stack traces or secret/provider payload leakage.
- Cursor pagination with stable ordering; do not return inaccessible objects or counts.
- Versioned resource updates require ETag/If-Match or explicit expected version; stale writes fail `412`.
- Side-effecting POST requires Idempotency-Key and stable replay semantics.
- WorkerRunEnvelope and WorkerResult are versioned and validated; unsupported major contract versions fail closed.
- Use typed domain commands and lifecycle transitions; no generic `/execute` or arbitrary PATCH of protected status fields.
- Frontend reads canonical state through REST; SSE delivers authorized progress/events only.

## 6. Security implementation requirements

1. For browser User API in MVP, authenticate with opaque server-side `ai_res_session` cookie; validate session status, expiry, revocation and user status. Apply CSRF validation and Origin/Referer policy to state-changing cookie-authenticated requests. Never require OIDC/JWT Bearer for local browser login. For future OIDC callbacks and service-to-service JWT credentials, validate issuer, audience, signature, expiry and required claims according to the relevant token profile. Never trust client-supplied `userId`, `organizationId`, `projectId` as authorization proof.
2. Resolve object ownership from database, then enforce organization/project/object ACL.
3. Enforce policy on reads, lists, search, graph traversal, exports, uploads/downloads and summaries.
4. Service identities are separate from human identities; worker receives scoped grants only.
5. Policy Engine unavailable => deny critical write, approval, permission grant and external side-effect operations.
6. Do not put secrets in prompts, event payloads, logs, traces, Temporal history or WorkerResult.
7. Do not expose Temporal, PostgreSQL, MinIO console, Bifrost admin or Langfuse admin endpoints through public API.
8. Validate webhook signatures and replay windows; deduplicate event IDs.
9. Upload URLs must be short-lived, object-scoped and constrained by content size/type; verify object checksum after upload.
10. Never trust content embedded in Source documents as system/developer instructions.

## 7. Required contract artifacts

At minimum, commit:

- OpenAPI public API v1.1 (`AI_RES_Public_API_v1.1.yaml`); it defines the initial vertical slice, not the entire endpoint catalogue.
- AsyncAPI domain event catalogue.
- JSON Schema: common identifiers/error/pagination; WorkerRunEnvelope; WorkerResult; WorkerNotice; domain event envelope; key command payloads. Starter schema: `AI_RES_Worker_Contracts_v1.1.schema.json` (move/copy into `contracts/json-schema/worker/` and evolve only with compatibility review).
- Positive and negative example payloads.
- API changelog and compatibility policy.
- Contract validation/lint CI job.
- Consumer/provider contract tests.

## 8. Test matrix / Definition of Done

Implementation increment is not complete until:

- [ ] Contract documents validate with pinned validators.
- [ ] Handler/provider conforms to OpenAPI schema and examples.
- [ ] Authenticated user can access only permitted project objects.
- [ ] Cross-project IDOR attempts fail without leaking resource existence.
- [ ] Invalid enum/state transition/unknown major contract version rejected.
- [ ] Missing/stale If-Match rejected for version-sensitive writes.
- [ ] Idempotent retry does not create duplicate task, operation, approval, upload finalization or external action.
- [ ] Worker cannot write domain data directly or self-grant permissions.
- [ ] Readiness Gate blocks Worker Run when mandatory checks fail.
- [ ] Temporal workflow replay succeeds against supported history versions.
- [ ] Activities are idempotent or have reconciliation for side effects.
- [ ] Outbox duplicate and out-of-order delivery does not corrupt state.
- [ ] SSE reconnect/replay respects ACL and retention gaps.
- [ ] Logs/traces/events/results contain no secrets or unauthorized source content.
- [ ] API and event changes pass backward-compatibility check.
- [ ] Tests and security findings are reported; no unresolved critical/high findings without documented approved exception.

## 9. Prohibited implementation shortcuts

- Do not create a new DB per domain or a graph DB for MVP.
- Do not let agents directly manipulate ORM models or database sessions across domain boundaries.
- Do not let Manager call Docker/Kubernetes APIs.
- Do not call provider LLM APIs directly from LangGraph nodes.
- Do not expose Temporal Workflow/Activity APIs as public endpoints.
- Do not put full document contents or prompts into Temporal histories/events/logs by default.
- Do not assume exactly-once delivery or exactly-once external side effects.
- Do not use `latest` container tags, unpinned schemas or mutable contract refs in a release.
- Do not silently overwrite versions, approved artifacts, Baselines or Worker results.
- Do not automatically approve business decisions, requirements, plans requiring human approval or Baselines.
- Do not invent missing business fields; mark them as unresolved and request design decision.

## 10. Required Claude Code delivery report

At the end of each increment Claude Code reports:
1. files created/changed;
2. contract/API surface changed;
3. migrations and compatibility implications;
4. tests executed and exact results;
5. security/authorization cases tested;
6. unresolved issues and assumptions;
7. whether docs/contracts were updated;
8. next safe increment.

Claude Code must not claim completion based only on code generation or a successful happy-path test.


---

# Дополнение v1.1. Обязательная реализация процессов и алгоритмов (этап 12)

**Нормативная спецификация:** `AI_RES_Process_Design_and_Algorithms_v1.8.md`. Этот документ дополняет API implementation spec и не заменяет его.

## 1. Обязательные документы для изучения

Перед изменением процессов Claude Code обязан изучить актуальные версии:
- `AI_RES_Process_Design_and_Algorithms_v1.8.md`;
- `AI_RES_Requirements_Lifecycle_v2.5.md`;
- `AI_RES_MVP_Capability_Matrix_v2.6.md`;
- `AI_RES_Agent_Architecture_Concept_v3.9.md`;
- `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md`;
- `AI_RES_API_and_Interaction_Contracts_v1.2.md`;
- `AI_RES_UX_Concept_v1.1.md`;
- `AI_RES_Infrastructure_Deployment_Operations_v1.1.md`;
- OpenAPI, AsyncAPI и Worker JSON Schemas.

Если репозиторий расходится с документами, сначала составить discrepancy report; не переписывать архитектуру молча.

## 2. Non-negotiable process invariants

1. Ни один Worker Run без успешного актуального Readiness Gate.
2. Каждый Run привязан к immutable ContextPackageVersion и точным Plan/Worker contract refs.
3. Manager принимает содержательные решения; Temporal управляет durable execution; LangGraph — внутренним reasoning graph.
4. Worker не пишет напрямую в domain DB, не расширяет grants, не утверждает требования/Baseline и не запускает peer Worker напрямую.
5. Handoff проходит Manager → Policy → Temporal → новый Readiness Gate.
6. WorkerResult валидируется и сохраняется immutable; rework — новый Run/Result.
7. Self-check, independent QA, Manager acceptance и human approval раздельны.
8. Critical/high-risk результат без обязательной QA не считается verified.
9. Source ingestion и Project Change Assessment — разные процессы.
10. Semantic impact не может понизить обязательную deterministic severity.
11. PlanVersion, RequirementVersion, ArtifactVersion и Baseline не перезаписываются.
12. Retry bounded и error-classified; pause/cancel/resume требуют reconciliation.
13. Параллелизм только для независимых задач; fan-in имеет явные criteria.
14. Approval всегда относится к exact version/scope и проверяет human authority.
15. Все значимые переходы — audit + outbox + correlation IDs.

## 3. Рекомендуемая реализационная последовательность

### Increment 10 — process primitives

Typed lifecycle transitions, Operation projection, Process/GateResult model, correlation, audit, outbox, idempotency и state transition tests.

### Increment 11 — Project/Epic intake

Project creation, Manager intake, adaptive question state, proposal persistence, human decision boundary.

### Increment 12 — Plan & Task orchestration

Immutable PlanVersion, PlanItem/Task mapping, dependency graph validation, cycle detection, partial approval constraints, Temporal workflow skeleton.

### Increment 13 — Readiness Gate

Deterministic check registry, GateResult, block reasons, staleness invalidation, last-moment grant/cancellation check.

### Increment 14 — Worker Run lifecycle

Envelope validation, Temporal schedule/start, LangGraph thread scope, WorkerNotice/Result, immutable persistence, Manager acceptance.

### Increment 15 — QA and rework

Verification modes, independent QA, disagreement handling, new Run for rework, human approval separation.

### Increment 16 — Source ingestion and Impact Assessment

Immutable SourceVersion, extraction provenance, indexing status, ChangeSet, deterministic + semantic impact, targeted revalidation.

### Increment 17 — Artifact / CR / Baseline lifecycle

Generate, validate, review, approve, publish, exact-version baseline and CR workflow.

### Increment 18 — Recovery and evaluation

Error taxonomy, bounded retries, pause/cancel/resume, reconciliation, process Evaluation Sets, regression and deployment gates.

Не начинать следующий increment, если предыдущий не имеет миграций, contract/process tests, security tests, observability и delivery report.

## 4. Обязательные тесты

- Gate false-ready negative tests: revoked permission, stale context, missing dependency, wrong Worker capability, missing acceptance schema.
- Plan graph: cycle, unreachable node, partial approval dependency violation, safe parallel branch.
- Worker: invalid schema, prompt injection, forbidden tool, attempted self-handoff, direct DB access denied.
- QA: mandatory independent QA, unavailable QA, disagreement, unverified result.
- Source: duplicate ingestion, parser version change, partial index failure, source change after run, critical impact not downgraded.
- Recovery: transient bounded retry, permanent error no retry, cancel race, pause/resume, DB/Temporal/MinIO reconciliation.
- Baseline: exact approved versions only, CR approval, old baseline immutable.
- Events: duplicate/out-of-order delivery, consumer idempotency, audit/outbox atomicity.

## 5. Запрещённые shortcuts

- Нельзя реализовать Readiness Gate как один LLM prompt без deterministic checks.
- Нельзя использовать Worker self-assessment вместо независимой QA.
- Нельзя считать source indexing завершением impact revalidation.
- Нельзя запускать все workers в фиксированной цепочке.
- Нельзя retry permission/input/business failures бесконечно.
- Нельзя обновлять старые ContextPackage/PlanVersion/WorkerResult/Baseline in-place.
- Нельзя делать approval через обычный PATCH статуса.
- Нельзя делать Temporal Workflow единственным хранилищем доменного статуса.

## 6. Обязательный отчёт Claude Code

Для каждого increment указать: implemented process/transition, файлы и миграции, contracts/events updated, тесты и точные результаты, negative/security/recovery cases, evaluation-set impact, telemetry/audit coverage, known gaps и следующий безопасный increment. Не заявлять завершение без воспроизводимых тестов.


---

# Дополнение v1.2. Manager–Worker reconciliation requirements

## Mandatory constraints

1. Implement one Manager + nine logical Worker specializations on the shared
   Worker Runtime pool. Do not create nine mandatory containers/services.
2. Manager owns planning, routing, coordination, result integration and
   Epic-level readiness; it does not perform specialized Worker analysis.
3. Elicitation dialogue is coordinated by Manager; specialized elicitation
   analysis is executed by Elicitation Worker.
4. Worker may perform internal LangGraph decomposition within its assigned
   scope. Any domain Task creation, scope/budget/dependency change or new
   WorkerRun requires Manager decision.
5. Worker-to-Worker collaboration is supported only through typed
   WorkerCoordinationRequest → Manager decision → Policy decision →
   Temporal execution. No Runtime-to-Runtime direct invocation.
6. Implement request types CONSULTATION, DELEGATED_SUBTASK, HANDOFF.
   Independent QA is a separate Review + WorkerRun.
7. Every derivative WorkerRun has a parent/request/review relationship as
   applicable, its own immutable ContextPackageVersion, scoped grants,
   budget, contract and Readiness Gate.
8. Keep Manager orchestration acceptance separate from verification status,
   independent QA outcome and human approval.
9. Implement risk-tier conflict adjudication. Manager may resolve low-risk
   analytical conflicts with evidence/rationale; medium risk requires the
   defined review/confirmation; high/critical or reserved authority is
   escalated.
10. Independent QA uses blind-first/staged review where applicable; record
    why it is not applicable when the author result must be visible.
11. Readiness Gate separates Manager semantic readiness assessment from
    deterministic platform checks against Worker Registry, capabilities,
    versions, dependencies, context, grants, tools, output schema and budget.
12. Manager Epic state is a rebuildable projection of canonical domain
    state/events, not an independent source of truth.

## Required implementation tests

- Worker proposes CONSULTATION; Manager approves; Policy allows; Temporal
  starts a new consultation Run; result returns to source Run.
- Worker proposes a handoff; Manager rejects; no WorkerRun is created.
- Manager approves but Policy denies; no WorkerRun starts.
- Worker attempts direct Runtime invocation or direct task creation; it is
  rejected and audited.
- Derivative Run with revoked grant or stale ContextPackageVersion is
  blocked by a new Readiness Gate.
- Worker local decomposition stays inside assigned scope; request for new
  domain Task is mediated by Manager.
- Low-risk disagreement is Manager-adjudicated with preserved evidence;
  high-risk unresolved QA disagreement remains unverified/blocked.
- Blind-first QA records its independent findings before author result is
  disclosed where the workflow supports it.
- Manager state projection can be rebuilt from domain records/events.


---

# Дополнение v1.3 — актуальный baseline перед реализацией

**Это дополнение имеет приоритет над списками версий в исторических дополнениях v1.0–v1.2.** Упоминания старых версий в предыдущих разделах сохраняются как история и не являются разрешением использовать устаревшие документы.

## 1. Source of truth и порядок разрешения конфликтов

Перед началом любого increment Claude Code MUST:
1. Прочитать `AI_RES_Document_Registry_v1.7.md` и определить текущие authoritative versions.
2. Прочитать актуальные документы из обязательного списка ниже.
3. Проверить наличие файлов и фактические версии в репозитории.
4. Составить `Implementation Baseline Manifest`: файл, версия, статус, checksum, область применимости.
5. Составить discrepancy report между документацией и текущим кодом/репозиторием.
6. Остановить затронутую работу при противоречии; не выбирать трактовку молча и не использовать устаревшую версию как fallback.

Если два нормативных документа противоречат друг другу, Claude Code не должен самостоятельно придумывать приоритет по дате/имени файла. Он обязан указать конфликт и предложить варианты решения. Решение принимает владелец проекта.

## 2. Актуальные обязательные документы

### 2.1. Product/domain/UX/process
- `AI_RES_Agent_Architecture_Concept_v4.3.md`
- `AI_RES_Product_Vision_and_Scope_v0.1.md`
- `AI_RES_MVP_Capability_Matrix_v3.1.md`
- `AI_RES_Requirements_Lifecycle_v2.5.md`
- `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md`
- `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.0.md`
- `AI_RES_UX_Concept_v1.1.md`
- `AI_RES_Process_Design_and_Algorithms_v1.8.md`
- `AI_RES_Manager_Worker_Consistency_Audit_v1.0.md`

### 2.2. Contracts and schemas
- `AI_RES_API_and_Interaction_Contracts_v1.2.md`
- `AI_RES_Public_API_v1.0.yaml`
- `AI_RES_Domain_Events_AsyncAPI_v1.2.yaml`
- `AI_RES_Worker_Contracts_v1.1.schema.json`
- все JSON Schemas, прямо указанные в API/Domain/Process specs и зарегистрированные в Document Registry.

### 2.3. Security, identity and tools
- `AI_RES_Security_Architecture_v1.1.md`
- `AI_RES_Threat_Model_v1.0.md`
- `AI_RES_Identity_Access_Control_v1.3.md`
- `AI_RES_Authentication_and_Session_Management_v1.0.md`
- `AI_RES_Secrets_and_Key_Management_v1.0.md`
- `AI_RES_Security_Controls_and_Requirements_v1.1.md`
- `AI_RES_Tool_Registry_and_Tool_Management_MVP_v0.3.md`
- `AI_RES_External_Integrations_and_Project_Context_v1.0.md`
- `AI_RES_Source_and_Context_Lifecycle_v1.1.md`
- `AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md`
- `AI_RES_Traceability_Dependencies_Impact_Analysis_v1.0.md`

### 2.4. Infrastructure, operations and quality
- `AI_RES_Infrastructure_Deployment_Operations_v1.7.md`
- `AI_RES_Observability_Architecture_v1.0.md`
- `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md`
- `AI_RES_Agent_Observability_and_Evaluation_v1.0.md`
- `AI_RES_Operational_Runbooks_v1.0.md`
- `AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md`
- `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md`
- `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md`
- `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md`

### 2.5. Glossary and improvement governance
- `AI_RES_Glossary_v1.0.md` and `AI_RES_Glossary_v1.0.json` — PROPOSED glossary; not an approved normative standard until owner/domain review.
- `AI_RES_Glossary_Entry_Schema_v1.1.json` and `AI_RES_Glossary_Document_Schema_v1.0.json`.
- `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.1.md`.
- `AI_RES_Continuous_Improvement_Requirements_v1.1.md` (CI-001…CI-045).
- `AI_RES_Continuous_Improvement_Contracts_v1.1.md` and `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json` — proposed contracts; reconcile with core API/Domain Model/AsyncAPI before implementing.
- `AI_RES_User_Documentation_Information_Architecture_v1.0.md` — guide structure and release gates; not a completed user manual.
- `AI_RES_Post_Implementation_Productization_Plan_v1.2.md` — final post-implementation deliverables.

### 2.6. Registry and methodology
- `AI_RES_Document_Registry_v1.7.md`
- `AI_RES_Methodology_and_Source_Traceability_Matrix_v1.1.md`

If a listed file is absent, report it. Do not silently downgrade to an earlier version. A document marked DRAFT/PROPOSED/PLANNED is not an approved implementation requirement unless its status and authority are explicitly clarified.

## 3. Additional non-negotiable constraints from stages 13–16

### 3.1. Security and identity
- Implement local authentication MVP with `IdentityProvider` abstraction; OIDC Authorization Code + PKCE is an extension, not a requirement to enable external IdP in MVP.
- Argon2id password hashing; no default credentials; one-time bootstrap admin flow.
- Privileged production-like roles require TOTP MFA according to IAM requirements.
- Human sessions, service identities and Worker Run scoped grants are distinct.
- OIDC issuer/subject mapping is stable identity; email is not identity key.
- OIDC claims do not automatically grant project roles.
- Authorization is enforced server-side at every protected operation; UI visibility is not authorization.
- Secrets never enter model context or logs.
- Do not claim these controls are implemented until tests demonstrate them.

### 3.2. Observability and evaluation
- OTel, Prometheus, Grafana, Loki and Tempo are the baseline observability design; Langfuse is optional and content capture is off by default.
- Domain/Security Audit Log is separate from ordinary telemetry.
- Redaction occurs before telemetry export; high-cardinality identifiers stay out of metric labels.
- Quality signals distinguish execution outcome, orchestration acceptance, verification, independent QA and human approval.
- Feedback and telemetry do not trigger automatic training or production behavior changes.

### 3.3. Performance and resilience
- API must not block on long-running agent work; Temporal durable workflows handle long-lived execution.
- Worker pool concurrency, provider/tool budgets, backpressure, fairness and resource isolation must be enforced outside the model.
- Retries are bounded and error-classified; Activities are idempotent or reconciled.
- Single-node Compose is not HA; RPO/RTO remain targets until restore drills.
- Numerical SLO/capacity limits are not invented; measure baseline and obtain approval.
- Optional Redis/Langfuse/telemetry backend outage must not silently bypass mandatory audit/security controls.

### 3.4. Glossary and continuous improvement
- Glossary is a versioned canonical product artifact; current v1.0 is PROPOSED and requires owner/domain approval.
- Improvement proposals require evidence, versioned evaluation, approval, release controls and post-release measurement.
- A0–A4 is a proposed autonomy scale, not a user-approved decision.
- Autonomy is capability/action-class/environment/scope-specific.
- No self-approval, self-escalation or permission expansion from accumulated experience.
- Business requirement/Baseline approval and security policy activation remain human-controlled.

## 4. Claude Code plugins and development tooling

The user will decide after the architecture/design package is complete which Claude Code plugins/extensions/MCP servers should be used during implementation.

Until that decision:
- do not install, enable or assume any specific Claude Code plugin, MCP server, hook or marketplace extension;
- do not make project implementation depend on a non-selected third-party extension;
- use standard repository tooling and explicitly declared dependencies;
- distinguish **Claude Code development-time extensions** from **AI RES runtime Tools/Plugins/MCP integrations**. They are separate trust boundaries, permission models and deployment concerns;
- any proposed development extension must be evaluated for publisher/repository trust, source availability, permissions, network access, secrets handling, update policy, telemetry and reproducibility before adoption;
- the AI RES Tool Registry remains the product runtime tool governance mechanism; installing a Claude Code plugin does not automatically register it as an AI RES tool.

## 5. Implementation readiness gate

Before the first code change:
- baseline manifest and repository reconnaissance are complete;
- current registry references resolve;
- OpenAPI/AsyncAPI/JSON Schema files parse and pass appropriate validators;
- database entities and API/event contracts have a traceability map;
- security-sensitive flows have negative tests planned;
- Docker Compose topology and environment/secrets strategy are documented;
- increment plan maps every increment to requirements, contracts, migrations, tests and DoD;
- unresolved decisions are listed with owner and blocking/non-blocking classification.

Do not start broad code generation before this gate. Prefer small vertical slices with migrations, contract tests, authorization tests, observability and reproducible delivery reports.

## 6. Stage 16 delivery boundary

During initial implementation, create only technical foundations that are in MVP scope (for example, glossary schema/storage/validation if explicitly prioritized). Do not present post-implementation user manuals as complete before UI and workflows exist.

After implementation and validation, execute Productization Plan v1.2:
- approve glossary v1.0 and integrate it into actual UI/docs/artifacts;
- produce Analyst and Stakeholder guides, Quick Start, workflow examples and FAQ from actual behavior;
- complete usability review and verify all screenshots against release build;
- enable improvement workflow only with explicit owners, versioned evaluation baseline, approvals, release/rollback and audit;
- evaluate autonomy per capability/action class; do not enable A3/A4 by default.

### 6.1. Stage 16 detailed boundary

- Treat the Continuous Improvement schemas as proposed contracts, not permission to create duplicate domain entities. Reconcile them with existing Improvement/Evaluation/Approval/Policy objects before migrations.
- Do not implement A3/A4 autonomous actions until the autonomy scale, capability/action-class matrix, owners, approvers, budgets, evaluation thresholds and emergency disable procedure are explicitly approved.
- Glossary may be integrated into UI/docs only after Glossary Owner and domain-owner approval. While entries are PROPOSED, use them as review material, not binding product terminology.
- User manuals and screenshots must be generated and validated against the actual release build. The pre-implementation information architecture is not a user guide.
- Continuous Improvement production rollout requires stable telemetry, versioned evaluation datasets, reproducible manifests, approval matrix, audit, release pinning, staged rollout and rollback/reconciliation.

## 7. Required implementation reporting

For each increment, report:
1. baseline manifest and files inspected;
2. requirements and contracts implemented;
3. files/migrations/API/events changed;
4. tests executed, command and exact results;
5. authorization/negative/security tests;
6. performance/reliability implications;
7. observability and audit coverage;
8. unresolved assumptions/decisions;
9. whether runtime behavior was actually exercised;
10. next safe increment.

Completion must be supported by reproducible tests, not code generation or documentation alone.

---

# Дополнение v1.4 — authoritative baseline после детализации блока 16

Это дополнение имеет приоритет над любыми более ранними перечнями версий в этом документе.

Перед реализацией Claude Code MUST использовать `AI_RES_Document_Registry_v1.9.md` как единственный актуальный реестр. Для архитектуры использовать `AI_RES_Agent_Architecture_Concept_v4.4.md`; для MVP scope — `AI_RES_MVP_Capability_Matrix_v3.2.md`; для реализации — настоящую версию спецификации v1.4.

Блок 16 состоит из двух частей:
- **16A — pre-implementation design:** glossary, continuous improvement/autonomy architecture, requirements, contracts and schemas; они являются проектными артефактами, runtime не реализован.
- **16B — post-implementation productization:** user/analyst/stakeholder/admin guides, Quick Start, workflow examples, FAQ, release screenshots, usability validation; публикуются только после проверки фактического поведения release build.

Обязательное ограничение: `AI_RES_Continuous_Improvement_Contracts_v1.1.md` содержит proposed API/event catalogue. До создания новых таблиц, endpoint или events Claude Code MUST сопоставить их с существующими сущностями и контрактами, подготовить discrepancy report и получить согласование изменения основных Domain Model/API/AsyncAPI. Нельзя автоматически трактовать standalone schema как разрешение создать дублирующие агрегаты.

Glossary v1.0 имеет статус PROPOSED. Не превращать его в нормативный набор UI labels или prompt rules до решения Glossary Owner и доменных владельцев. A0–A4 остаётся предложенной шкалой; не активировать A3/A4 без отдельного утверждённого autonomy matrix и тестовых evidence.


---

# Дополнение v1.5 — результаты сквозной сверки и обязательные ограничения

1. Единственный актуальный реестр — `AI_RES_Document_Registry_v2.6.md`. Все более ранние ссылки на Registry v1.7/v1.9 и устаревшие версии Architecture/MVP/Infrastructure/Tool Registry в исторических дополнениях не являются указанием читать эти версии.
2. Browser User API MVP использует opaque server-side session cookie `ai_res_session`; CSRF защита обязательна для state-changing requests. OIDC/JWT применяется только в будущей federation adapter или для явно определённых service-to-service token profiles.
3. Канонический Operation status set и его terminal/non-terminal semantics определены в API Contracts v1.3 и синхронизированы с Public API v1.1. Не добавлять собственные статусы без изменения обоих контрактов и state machine.
4. OpenAPI v1.1 описывает начальный вертикальный срез, а не все endpoint из полного API catalogue. Реализовывать endpoint только по приоритету MVP Matrix и согласованному increment; не считать отсутствие endpoint в OpenAPI доказательством, что он запрещён, и не создавать его без контракта.
5. До реализации persistence для Operation и ReadinessGate/GateResult требуется закрыть PRE-009: определить доменное владение, хранение, lifecycle, retention и отношение к Temporal.
6. До реализации API/event lifecycle для CI/autonomy требуется закрыть PRE-010: согласовать CI contracts с Domain Model, API Contracts и AsyncAPI; не создавать дублирующие агрегаты или события.
7. Security design documents остаются PROPOSED в Registry. Решение по Local Authentication MVP является выбранным; остальные PROPOSED controls должны пройти owner/security approval до соответствующего production-like release gate.


# Дополнение v1.6 — актуализация CI contract reference

Использовать `AI_RES_Continuous_Improvement_Contracts_v1.1.md` как последнюю proposed редакцию. Ссылка на Public API в нём указывает `AI_RES_Public_API_v1.1.yaml`; это не означает, что CI endpoints/event catalogue уже включены или утверждены.


# Дополнение v1.8 — правило выбора актуального реестра

Claude Code MUST открыть `AI_RES_Document_Registry_*.md`, выбрать файл с наибольшей версией SemVer и сверить его дату/историю. На момент выпуска этой версии snapshot реестра — `AI_RES_Document_Registry_v2.7.md`; при наличии более нового файла применяется правило выбора наибольшей SemVer версии. Не использовать зафиксированную в старом дополнении версию реестра, если в репозитории есть более новая.


Примечание: исторические перечни версий в дополнениях v1.1–v1.4 сохранены как журнал решений. Нормативный порядок чтения и актуальные версии задаются разделом 2 и правилом из дополнения v1.8.


# Дополнение v1.9 — синхронизация Operation state machine

Использовать `AI_RES_Process_Design_and_Algorithms_v1.8.md` вместе с API Contracts v1.3 и Public API v1.1. Набор Operation states общий; реализация обязана проверять terminal/non-terminal transitions.


# Дополнение v1.10 — актуальный process reference и registry snapshot

Текущий process design — `AI_RES_Process_Design_and_Algorithms_v1.8.md`. При старте Claude Code должен выбрать файл реестра с наибольшей версией SemVer; на дату этого выпуска snapshot — `AI_RES_Document_Registry_v2.7.md`.


# Дополнение v1.11 — точные wire names как проектные предложения

В Public API v1.1 используются имена cookie `ai_res_session` и CSRF header `X-CSRF-Token`. Это согласованные между API/OpenAPI рабочие имена для контрактного прототипа, но не отдельное пользовательское решение. Security owner должен подтвердить их в рамках AUTH/API security review до релизного baseline.


# Дополнение v1.12 — correction of document header references

Основная спецификация API — `AI_RES_API_and_Interaction_Contracts_v1.9.md`. Текущий реестр выбирается динамически как файл `AI_RES_Document_Registry_v*.md` с наибольшей версией SemVer. CI contract proposal — `AI_RES_Continuous_Improvement_Contracts_v1.1.md`. Более ранние references в исторических дополнениях не нормативны.


---

## Дополнение v1.13 — Operation и Readiness Gate implementation contract

## Дополнение v1.13 — обязательные implementation constraints для Operation и Readiness Gate

Перед реализацией использовать только следующие актуальные проектные контракты:
- `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.0.md`;
- `AI_RES_Domain_Model_and_Data_Architecture_v1.3.md`;
- `AI_RES_Process_Design_and_Algorithms_v1.3.md`;
- `AI_RES_API_and_Interaction_Contracts_v1.4.md`;
- `AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json`;
- `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.0.json`;
- `AI_RES_Public_API_v1.2.yaml`;
- `AI_RES_Domain_Events_AsyncAPI_v1.3.yaml`.

Implementation rules:
1. Implement Operation persistence in AI RES PostgreSQL; do not use Temporal as the public/domain source of truth.
2. Create Operation + Outbox command atomically; start Temporal idempotently using stable Workflow ID derived from Operation ID.
3. Persist append-only OperationEvent and validate all status transitions in application/domain service.
4. Keep Temporal technical status, Operation status, Task status and WorkerRun status separate.
5. Implement idempotency scope/fingerprint; duplicate identical command returns same Operation.
6. Persist immutable ReadinessEvaluation and typed ReadinessCheckResults before dispatch.
7. Store exact Task/Plan/WorkerDefinition/ContextPackage/rules/grants/tool/output/budget/dependency versions or hashes in evaluation snapshot.
8. Perform final pre-start revalidation; stale snapshot means no dispatch and a new evaluation.
9. Every started WorkerRun must reference exact successful evaluation; no bypass route.
10. `READY_WITH_LIMITATIONS` must materialize restrictions into WorkerRun envelope and scoped grants/budgets.
11. Policy/ACL uncertainty, evaluator failure or policy engine outage fails closed.
12. Reauthorize every tool call; Gate is not a permission token.
13. Implement cancellation as request/acknowledgement/reconciliation; do not report CANCELLED before confirmed cleanup/outcome.
14. Add recovery reconciliation for Operation ↔ Outbox ↔ Temporal. Ambiguous external effects require manual reconciliation, not blind retry.
15. Add contract, state-machine, concurrency, duplicate delivery, stale-gate, revoked-grant, crash/recovery, cancellation-race and ACL tests.
16. Do not create parallel `GateResult` and `ReadinessEvaluation` tables; GateResult is the projection over evaluation + checks.
17. Keep evidence and result payloads out of Temporal history; pass IDs/refs and compact typed metadata.
18. Do not claim runtime correctness from schema lint or static validation; report tests actually executed.


---

## Дополнение v1.14 — подтверждённая архитектурная основа Operation и Readiness Gate

Архитектурное решение `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.1.md` имеет статус `BASELINED` и подтверждено владельцем проекта 2026-11-10. Его архитектурные принципы обязательны для реализации. Использовать версию v1.1 решения вместо v1.0.

PRE-009 и PRE-011 считаются закрытыми на уровне архитектурного выбора: определены доменное владение Operation, разделение доменного состояния и Temporal execution state, Outbox delivery, append-only события, persistence ReadinessEvaluation и обязательный Gate перед WorkerRun. Это не отменяет оставшиеся implementation details и проверки.

До начала соответствующего increment необходимо детализировать и согласовать: operation type/check code registries; fan-out и parent/child Operation semantics; WorkerRun lifecycle; физические миграции, ограничения и индексы; retention/legal hold; dispatch lease и транзакционную стратегию final revalidation; semantic assessment schema/task-class policy; recovery/reconciliation алгоритмы; ACL-safe API/UI diagnostics. Не трактовать эти открытые детали как разрешение нарушать BASELINED-инварианты.

Ни статическая валидация JSON/YAML, ни факт наличия контрактов не подтверждают runtime correctness. Для реализации обязательны тесты concurrency, idempotency, duplicate delivery, cancellation races, stale readiness, revoked grants, policy outage, crash/restart, Temporal replay/recovery и ACL isolation.


---

## Дополнение v1.15 — обязательная реализация Operation и WorkerRun Lifecycle

Нормативные источники для этого increment:
- `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.2.md`;
- `AI_RES_Domain_Model_and_Data_Architecture_v1.4.md`;
- `AI_RES_Process_Design_and_Algorithms_v1.4.md`;
- `AI_RES_API_and_Interaction_Contracts_v1.5.md`;
- `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.1.json`;
- `AI_RES_Public_API_v1.3.yaml`;
- `AI_RES_Domain_Events_AsyncAPI_v1.4.yaml`.

Implementation MUST:
1. Implement two independent domain state machines for Operation and WorkerRun, plus separate Task, ReadinessEvaluation, Review, Approval, Artifact and Temporal execution state.
2. Enforce one root Operation per accepted command; fan-out/fan-in remains Tasks/WorkerRuns under the same Operation. Child Operation only for a genuinely independent long-running subcommand per Decision v1.2.
3. In MVP enforce `Task.operation_id` and `WorkerRun.operation_id` equality; WorkerRun has exactly one Task. Do not infer ACL inheritance from parent Operation.
4. Implement criteria-based deterministic Operation aggregator using required/optional PlanItems, dependency graph, completion policy snapshot, WorkerRun/Review outcomes and global blockers. Never derive success from counts alone.
5. Keep Operation `RUNNING` while any allowed branch can progress; use global WAITING statuses only when all allowed progress paths are blocked.
6. Implement WorkerRun status enum/transitions exactly as State Machine v1.1. Gate outcomes are not WorkerRun statuses; STALE is Gate outcome. BLOCKED returns to WAITING_FOR_GATE only after new persisted evaluation; evaluator error fails closed.
7. Implement WorkerRun event append-only sequence, optimistic concurrency, current projection + event + Outbox atomicity.
8. Store `derived_from_worker_run_id`, `derivation_reason`, `attempt_number`; do not mutate/reopen terminal WorkerRun. Activity retry/replay does not create a new WorkerRun.
9. QA is a separate Review and (when performed by agent) a separate WorkerRun. Human Approval, Artifact approval/publication and Baseline remain separate domain records.
10. Implement cancellation/timeout as request → stop/cleanup → reconciliation → terminal outcome. A Temporal cancellation acknowledgement alone is insufficient evidence for WorkerRun/Operation CANCELLED.
11. Every actual start references exact successful ReadinessEvaluation and final pre-start revalidation. Every new derived WorkerRun gets its own Gate evaluation.
12. Implement ACL isolation for Operation, Task, WorkerRun, child Operations, Reviews and result/evidence refs; no parent-child ACL inheritance by assumption.
13. Publish versioned domain events through Outbox; enforce per-aggregate sequence and idempotent consumers; never include prompts, secrets, or full payloads in event history.
14. Tests MUST cover exhaustive transitions, invalid transitions, fan-out/fan-in, required vs optional branches, partial success, child Operation boundaries, task/run cardinality, derived lineage, Gate blocked/stale/error, Activity replay, duplicate delivery, optimistic concurrency, human wait/resume, QA/approval separation, cancellation/timeout side-effect races, ACL isolation and recovery.
15. Do not claim runtime completion until integration tests against PostgreSQL and Temporal, crash/restart/replay tests and policy/ACL tests have actually passed. Static schema checks are not runtime evidence.


## Дополнение v1.16 — обязательная реализация Operation/WorkerRun Event Model

Нормативные источники: `AI_RES_Operation_WorkerRun_Event_Model_v1.0.md`, Domain Model v1.5, Process Design v1.5, API Contracts v1.6, AsyncAPI v1.5, State Machine JSON v1.1.

Implementation MUST:
1. Maintain separate current projections and append-only event histories for Operation and WorkerRun; Outbox and Inbox are separate delivery/deduplication concerns.
2. Persist projection update + aggregate event + Outbox record in one PostgreSQL transaction. Rollback must leave none of these committed.
3. Use CloudEvents 1.0 envelope and registered typed event schemas. Preserve same `event_id` on retries/redelivery.
4. Allocate monotonic per-aggregate sequence atomically; unique `(aggregate_id, sequence)` and event ID constraints are mandatory. Never use `MAX(sequence)+1`.
5. Guarantee strict order only per aggregate. Do not assume global order across Operation/WorkerRun or other aggregates.
6. Implement Outbox dispatcher with lease, bounded retry/backoff+jitter, quarantine, controlled replay, and per-aggregate ordering. Do not hold DB transaction during network calls.
7. Implement consumer-scoped Inbox dedupe `(consumer_name,event_id)` and sequence checkpoint/gap handling. Duplicate delivery is successful no-op; gaps are deferred, not silently skipped.
8. Implement command idempotency scope `(organization, actor scope, command name, key)` plus canonical request fingerprint. Same key/different fingerprint returns `IDEMPOTENCY_KEY_REUSED` (409).
9. Implement `row_version`/expected version concurrency; stale update returns `AGGREGATE_VERSION_CONFLICT` (409), never force-overwrite.
10. Include correlationId, causationId, operationId and explicit aggregate references. Trace context is not authorization.
11. Enforce ACL for event history, SSE and consumers; Outbox is never directly exposed to end users. Resource refs require independent ACL on dereference.
12. Exclude prompts, hidden reasoning, secrets, source bodies, full results and raw provider errors from events/logs. Use typed error/reason codes and protected refs.
13. Use `worker_run.completed`; do not emit new `worker_run.accepted`. Keep ReadinessEvaluation event stream distinct from WorkerRun events.
14. Implement schema compatibility checks: additive optional fields within major version; breaking change creates new major event type/schema. Unknown major type goes to quarantine/alert.
15. Do not claim exactly-once. Guarantee at-least-once delivery with idempotent processing.
16. Implement event history retention/legal hold as configurable policy; until approved, no automatic deletion of Operation/WorkerRun event history.
17. Test transaction atomicity, concurrent sequence allocation, duplicate dispatch, crash after publish, inbox duplicate, sequence gaps, poison events, replay, ACL filtering, schema compatibility, payload privacy and cancellation/timeout races.

---

## Дополнение v1.17 — PostgreSQL persistence и транзакционная реализация

**Обязательное дополнение к реализации.** Реализация этого блока должна следовать `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.0.md` и SQL design migration `AI_RES_PostgreSQL_Physical_Model_v1.0.sql`.

### Non-negotiable constraints

- `ai_res_db` — доменная БД; `temporal_db` — отдельная. Не создавать cross-database FK.
- Domain write выполняется только через Application/Domain Service; Worker Runtime не имеет unrestricted SQL write.
- Projection + Event History + Outbox в одной транзакции.
- At-least-once; Inbox deduplication; exactly-once не заявлять.
- Sequence под aggregate row lock/CAS; запрещён `MAX()+1`.
- Использовать optimistic `row_version`; bounded retry для deadlock/serialization conflict.
- Не держать транзакцию во время LLM, Temporal RPC, HTTP/tool или human wait.
- Idempotency key хранить только как HMAC digest с tenant/scope binding; fingerprint mismatch → `IDEMPOTENCY_KEY_REUSED`.
- `started_with_readiness_evaluation_id` неизменяем; evaluation принадлежит тому же WorkerRun.
- Outbox publish выполняется после commit; lease не держит DB lock во время network call.
- Consumer Inbox и локальный эффект — одна транзакция; внешние side effects через consumer Outbox.
- Cancellation и recovery завершаются только по фактам reconciliation.
- Schema changes — expand/backfill/validate/enforce/contract; destructive migrations запрещены без restore/rollback plan.

### Обязательные acceptance tests

Параллельная идемпотентная команда; fingerprint mismatch; aggregate sequence race; CAS race; crash after commit-before-publish; crash after publish-before-mark; Inbox dedupe; ordering gap; quarantine/replay; Task/Operation composite FK; Gate snapshot and started evaluation immutability; cancellation race; Temporal Activity retry; reconciliation after Workflow completion; restore drill.

### Explicitly unresolved implementation choices

Не выбирать ORM, migration tool, transport, HMAC key rotation, retention и lease/backoff thresholds молча. Зафиксировать их отдельными implementation ADRs до использования в production.


---

## Дополнение v1.18 — PostgreSQL migration и access baseline (обязательное)

**Supersedes** прежний пункт v1.17 об открытом выборе ORM/migration tool: выбран Alembic + SQLAlchemy 2.x для `ai_res_db`.

Перед реализацией изучить:
- `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`
- `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`
- `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.1.md`
- `AI_RES_Identity_Access_Control_v1.2.md`
- `AI_RES_Infrastructure_Deployment_Operations_v1.6.md`

Обязательные ограничения:
1. Создать Alembic migration environment для `ai_res_db` с явным allowlist схем; не мигрировать Temporal/LangGraph schemas.
2. Migration job отдельна от API startup; revisions immutable, именованные constraints, manual review autogenerate.
3. Несовместимые изменения: expand → resumable backfill → validate → contract; большие индексы CONCURRENTLY; FK/CHECK NOT VALID + VALIDATE; lock/statement timeouts.
4. `ai_res_owner` NOLOGIN; отдельный migrator; runtime principals не владельцы и не имеют DDL/BYPASSRLS. Manager/Worker Runtime без DB credentials.
5. RLS ENABLE + FORCE на tenant tables, fail-closed без transaction-local tenant context; тестировать под реальными runtime roles.
6. Policy Engine остаётся authoritative; RLS — defense-in-depth. Не считать custom GUC безопасным против arbitrary SQL под API identity.
7. DB secrets только через Secret Manager; TLS/SCRAM, network allowlist, credential rotation.
8. Добавить CI checks на schema drift, RLS coverage, grants, forbidden role attributes, migration upgrade from empty and previous revision.
9. Production contract migration блокируется без backup/PITR/restore evidence и approval.
10. Не заявлять реализацию до исполнения migration/access acceptance suite.

Acceptance suite включает tenant A/B isolation, missing context default-deny, pooled connection context reset, runtime cannot DDL/DELETE/TRUNCATE/BYPASSRLS, Manager/Worker no DB network/secret, migrator-only DDL, RLS coverage, expand/backfill interruption/resume, upgrade from empty and previous revision, restore rehearsal, credential rotation.


## Дополнение v1.19 — Persistence Implementation Blueprint (обязательный порядок реализации)

Перед реализацией persistence Claude Code MUST изучить `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`, актуальный Registry и перечисленные в Blueprint нормативные документы. Нельзя начинать с прямого применения design DDL. Сначала выполнить repository/schema reconnaissance и зафиксировать существующие metadata, tables, owners, grants, constraints, migration head и legacy Task provenance.

Обязательный порядок: (1) pin dependencies; (2) Alembic env + schema allowlist + `platform.alembic_version`; (3) empty DB upgrade test; (4) additive revisions; (5) role/grant/RLS revisions; (6) resumable backfill dry-run and approved mapping; (7) validation and NOT NULL/FK contract; (8) repositories/Unit of Work/tenant context; (9) PERSIST-001..024 tests; (10) preflight/postflight and recovery runbooks. Не запускать migration из application startup. Не выдавать DB credentials Manager/Worker Runtime. Не использовать SQLite как доказательство PostgreSQL semantics.

Claude Code MUST not claim implementation complete until Blueprint §14 DoD is met and evidence is attached. Если репозиторий или PostgreSQL instance недоступен, выполнить только documentation/scaffold work, явно указав `IMPLEMENTATION NOT VERIFIED`; не имитировать deployment/test results.


---

## Дополнение v1.20 — полный architecture baseline и реализационные gates

Перед реализацией Claude Code MUST прочитать актуальный Registry, Architecture Completion Baseline и следующие нормативные документы: Model Gateway/Model Registry, Knowledge/Memory/Retrieval, Evaluation/Release Gates, Learning/Experience Lifecycle, Security Architecture, Threat Model, Security Controls, Identity/Access, Authentication/Sessions, Secrets, Tool Registry, Source/Context, Integrations, Requirements Lifecycle, UX, Persistence Blueprint, PostgreSQL physical model, Operation/WorkerRun lifecycle/event contracts, API/OpenAPI/AsyncAPI, Observability, Performance/Resilience and MVP Matrix.

### Non-negotiable decisions

1. LLM access only via `LLMGatewayPort`; Bifrost preferred behind adapter and blocked from production-like profile until PoC/security acceptance. One approved model profile for first vertical slice.
2. MVP retrieval uses PostgreSQL FTS + pgvector; MinIO originals; Redis cache only. ACL before retrieval/reranking/context/cache/export. No GraphRAG or separate vector DB.
3. Tools execute only through Tool Gateway and per-call Policy authorization. MCP is allowlisted adapter only. Runtime code generation is out of MVP.
4. MVP integrations: files, OpenAPI import, read-only GitHub/GitLab. No arbitrary outbound writes/bidirectional sync.
5. Evaluation is task-class based; deterministic tests + human-calibrated rubric + adversarial/security tests. LLM judge cannot be sole gate.
6. Learning is non-parametric curated experience. No fine-tuning, self-modifying prompts/rules or cross-tenant learning. Autonomy A0-A2 only; A3/A4 disabled.
7. Security controls SEC P0 are release blockers. Local auth, opaque sessions, CSRF, Argon2id, least-privilege PostgreSQL, RLS defense-in-depth, secrets isolation, no direct DB credentials in Manager/Worker Runtime.
8. Numerical SLO, retention, capacity and retrieval/model quality thresholds require measurement/legal policy; do not fabricate them.

### Implementation sequence after persistence

- Increment 20: LLMGatewayPort + Model Registry + Bifrost PoC adapter; no provider-specific calls from agents.
- Increment 21: Knowledge ingestion/index generation with PostgreSQL FTS/pgvector and MinIO; provenance and ACL tests first.
- Increment 22: Retrieval API + Context Builder immutable package; ACL leakage tests are hard blockers.
- Increment 23: Tool Registry/Gateway, typed tool contracts, per-call policy, MCP allowlist adapter; side-effect tests.
- Increment 24: Connector MVP (file/OpenAPI/GitHub/GitLab read-only) with checkpoint, dedupe, rate-limit and partial sync.
- Increment 25: Evaluation harness, task-class datasets, regression manifest, human calibration and release gates.
- Increment 26: Learning signal/curated experience workflow; no model fine-tuning or autonomous behavior update.
- Increment 27: Security hardening and adversarial acceptance across API, retrieval, tools, files, secrets, RLS and event delivery.
- Increment 28: UI/UX acceptance, accessibility, user guides and operational runbooks based on actual running product.

### Completion rule

A design baseline is not implementation evidence. Every increment must attach code diff, migration revision, automated test report, security evidence, runtime configuration and known limitations. No claim of completion without executable tests in the target stack. If repo/infra is unavailable, produce only plan/scaffold and mark `IMPLEMENTATION NOT VERIFIED`.


---

## Дополнение v1.21 — актуальная нормативная карта после reconciliation

**Обязательное правило:** до любых изменений кода Claude Code MUST прочитать `AI_RES_Document_Registry_v4.0.md` и использовать только актуальные пути из его раздела текущих документов. Любые versioned references в исторических дополнениях настоящей спецификации являются историей, если не подтверждены Registry v4.0.

Обязательный стартовый набор: Architecture Concept v4.6; MVP Capability Matrix v3.3; Requirements Lifecycle v2.6; UX Concept v1.2; Domain Model v1.9; Process Design v1.9; API Contracts v1.10; Public OpenAPI v1.3; AsyncAPI v1.6; Worker Contracts v1.1; Operation/WorkerRun Event Model v1.4; Architecture Decision v1.6; PostgreSQL Physical Model v1.2; Migration & Access Strategy v1.1; Persistence Implementation Blueprint v1.0; Identity & Access Control v1.5; Security Architecture v1.2; Threat Model v1.1; Security Controls v1.2; Secrets v1.1; Authentication v1.1; Infrastructure v1.7; Model Gateway v1.0; Knowledge/Memory/Retrieval v1.0; Tool Registry v1.0; Evaluation/Release Gates v1.0; Learning Lifecycle v1.0; Glossary v1.1; Decisions/Assumptions/Risks v1.1; Methodology Traceability Matrix v1.2.

Before implementation Claude Code MUST verify: registry file paths exist; no duplicate canonical document IDs/paths; referenced contract versions match Registry v4.0; OpenAPI/AsyncAPI local refs resolve; JSON schemas validate; migration scaffold and SQL are reviewed against the actual repository and PostgreSQL major version. If an actual repository contradicts the design, stop the affected increment, report evidence and propose a controlled decision; do not silently rewrite architecture.

This specification is a design/implementation instruction, not evidence that code, migrations, security tests or runtime services exist. Current readiness disposition is `AI_RES_Pre_Implementation_Readiness_Audit_v2.1.md`.


---

# Дополнение v1.22 — статусная карта и актуальные документы

**Единственный актуальный реестр:** `AI_RES_Document_Registry_v4.1.md`. Он имеет приоритет над всеми versioned references в исторических разделах настоящей спецификации. Не использовать старые ссылки, если актуальный файл указан в Registry v4.1.

Актуальные версии затронутых документов: Requirements Lifecycle v2.7; Source & Context Lifecycle v1.3; External Integrations v1.2; Observability Architecture v1.2; Agent Observability & Evaluation v1.2; Continuous Improvement & Autonomy Architecture v1.3; Continuous Improvement Requirements v1.3; Decisions/Assumptions/Risks/Uncertainty v1.2.

Статус `BASELINED` означает нормативный design/requirements baseline, но не подтверждает программную реализацию, PoC, runtime, security, load или production acceptance. Частичные baseline и открытые implementation/deployment gates описаны непосредственно в соответствующих документах и Registry v4.1.

Перед началом каждого implementation increment Claude Code MUST проверить: (1) canonical file/version/status в Registry v4.1; (2) наличие файла; (3) соответствие referenced contract versions; (4) unresolved WORKING items, относящиеся к increment. При конфликте остановить затронутую работу и выпустить discrepancy report; не выбирать статус или версию самостоятельно.


## Дополнение v1.22.1 — финальная статусная синхронизация

Для всех текущих решений использовать Registry v4.1. Статусные addenda следующих документов являются нормативными: Requirements Lifecycle v2.7; Source & Context v1.3; External Integrations v1.2; Observability v1.2; Agent Observability & Evaluation v1.2; Continuous Improvement Architecture v1.3; Continuous Improvement Requirements v1.3; Decisions/Assumptions/Risks v1.2. Старые references в предыдущих разделах являются историческими snapshots.
