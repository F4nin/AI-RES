# testing-and-verification.md — Тестирование и фактическая верификация

**Нормативные источники:** `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` §8 · `AI_RES_Agent_Observability_and_Evaluation_v1.2.md` · `AI_RES_Evaluation_and_Release_Gates_v1.0.md`

---

## Принцип: статические проверки ≠ runtime evidence

- Успешная генерация кода не подтверждает корректность поведения.
- Прохождение JSON Schema lint не подтверждает runtime semantics.
- Статическая верификация документов не подтверждает реализацию.
- Если PostgreSQL instance или репозиторий недоступны — выполнять только documentation/scaffold и явно указывать `IMPLEMENTATION NOT VERIFIED`. Не имитировать deployment/test results.

---

## Definition of Done для каждого инкремента

Инкремент не считается завершённым, пока не выполнены **все** применимые пункты:

### Contracts
- [ ] OpenAPI/AsyncAPI/JSON Schema валидируются pinned-валидаторами в CI.
- [ ] Handler/provider соответствует OpenAPI schema и примерам.
- [ ] Contract lint и breaking-change detection проходят.
- [ ] API и event changes проходят backward-compatibility check.

### Authorization
- [ ] Аутентифицированный пользователь видит только объекты своей organization/project.
- [ ] Cross-project IDOR попытки отклоняются без раскрытия факта существования ресурса.
- [ ] Stale/revoked session отклоняется (401).
- [ ] Revoked Worker grant блокирует protected operation.
- [ ] Policy Engine outage → fail-closed для критических операций.

### Domain integrity
- [ ] Invalid enum/state transition отклоняется.
- [ ] Unknown major contract version → fail closed.
- [ ] Missing/stale If-Match → 412 для version-sensitive writes.
- [ ] Идемпотентный retry не создаёт дубль task/operation/upload finalization/external action.

### Worker/Gate/Operation
- [ ] Worker не может писать domain data напрямую или self-grant.
- [ ] Readiness Gate блокирует WorkerRun при failing deterministic checks.
- [ ] WorkerRun не стартует без корректной ReadinessEvaluation (outcome READY или READY_WITH_LIMITATIONS).
- [ ] Operation status transitions валидируются; terminal статус не переоткрывается.
- [ ] TOCTOU revalidation: stale evaluation → новая evaluation, не переиспользование старой.

### Temporal/LangGraph
- [ ] Temporal Workflow replay проходит для поддерживаемых версий history.
- [ ] Activities идемпотентны или имеют reconciliation для side effects.
- [ ] Параллельная идемпотентная команда не создаёт два WorkerRun.
- [ ] Activity retry не создаёт новый WorkerRun.

### Events/Outbox
- [ ] Outbox duplicate/out-of-order delivery не корруптит состояние.
- [ ] Consumer Inbox deduplication работает: повторная доставка — successful no-op.
- [ ] Sequence gap не проглатывается молча.
- [ ] Crash after commit-before-publish: после recovery событие доставляется ровно один раз.
- [ ] SSE reconnect/replay соблюдает ACL и retention gaps.

### Security
- [ ] Logs/traces/events/WorkerResult не содержат secrets или unauthorized source content.
- [ ] Prompt injection attempt из source content не выполняется как инструкция.
- [ ] Upload checksum verification работает.
- [ ] Webhook signature validation работает; replay window соблюдается.

---

## Обязательные negative tests по областям

### Gate и WorkerRun
- Revoked permission после Gate — WorkerRun не стартует при финальной revalidation.
- Stale ContextPackageVersion — новая evaluation требуется.
- Missing Worker capability version — BLOCKED.
- Missing required dependency/approval — BLOCKED.
- Evaluator error — WorkerRun не стартует (не READY).

### Plan и Task
- Cycle detection в dependency graph.
- Partial approval dependency violation.
- Unreachable PlanItem.

### Worker isolation
- Worker пытается писать в domain DB — отклоняется и аудируется.
- Worker пытается self-grant permission — отклоняется.
- Worker пытается запустить peer Worker напрямую — отклоняется.
- Prompt injection из source content — не исполняется.

### Source и Impact
- Duplicate source ingestion — не создаёт дубль SourceVersion.
- Parser version change — новый ExtractionRecord, старый не мутируется.
- Partial index failure — не заменяет предыдущую валидную SourceVersion.
- Critical impact category I0 не может быть понижена семантической оценкой.

### Recovery и Outbox
- Transient error → bounded retry, не бесконечный.
- Permanent error (input/business) → нет retry.
- Cancel race с уже завершившимся action → reconciliation, не blind retry.
- Pause/resume — состояние консистентно до и после.

### Baseline и версионирование
- Утверждённая версия требования не перезаписывается in-place.
- Baseline не переписывается; изменение только через Change Request.
- WorkerResult immutable после сохранения.

---

## Независимый QA Worker

- QA Worker выполняет отдельный WorkerRun с собственным ContextPackageVersion, grants и Readiness Gate.
- QA Worker не читает author WorkerResult до формирования собственных выводов (blind-first где workflow поддерживает).
- Disagreement QA vs author: low-risk → Manager adjudicates с evidence; high-risk → BLOCKED до human resolution.
- Self-assessment Worker ≠ независимая проверка.
- Mandatory independent QA недоступен → результат остаётся unverified/blocked; нельзя заменить self-assessment.

---

## Evaluation Framework (BASELINED)

- Evaluation sets — task-class based: elicitation, extraction, conflict detection, decomposition, artifact generation, recovery.
- Три типа тестов: deterministic + human-calibrated rubric + adversarial/security.
- LLM judge не может быть единственным release gate.
- Quality signals раздельны: execution outcome / orchestration acceptance / verification status / independent QA outcome / human approval.
- Feedback и telemetry не запускают автоматическое обучение или изменение поведения в production.

---

## Delivery report по инкременту

Завершение инкремента = предоставить все восемь пунктов из Implementation Spec v1.22 §10:
1. Файлы created/changed.
2. API/contract surface changed.
3. Migrations и compatibility implications.
4. Tests executed — точная команда и результаты.
5. Security/authorization cases tested.
6. Unresolved issues и assumptions.
7. Docs/contracts updated (да/нет + что).
8. Next safe increment.
