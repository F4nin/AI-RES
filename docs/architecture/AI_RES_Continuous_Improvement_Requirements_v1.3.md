# AI RES — Требования к непрерывному улучшению и управляемой автономности

**Версия:** 1.3  
**Статус:** BASELINED — normative CI requirements; runtime beyond MVP is not implemented
**Блок:** 16A

## 1. Требования

### CI-001 — Evidence-backed proposal
Каждое Improvement Proposal MUST ссылаться на evidence, проблему, гипотезу, ожидаемый эффект, риски и затрагиваемую область.

### CI-002 — Immutable proposal versions
Изменение существенных полей Proposal MUST создавать новую версию; история оценок, approvals и релизов сохраняется.

### CI-003 — Signal provenance
Каждый сигнал улучшения MUST содержать источник, время, scope, версию затронутого компонента и доступную provenance.

### CI-004 — Data minimization
Signal Collector MUST собирать только данные, необходимые для указанной цели, с учётом ACL, classification, retention and privacy rules.

### CI-005 — No default training
Raw user prompts, responses, documents and source payloads MUST NOT автоматически использоваться для model training/fine-tuning.

### CI-006 — Sanitized evaluation data
Копирование примеров в Evidence Store/Evaluation Set MUST проходить redaction, rights review, ACL check and versioning.

### CI-007 — Separation of knowledge and behavior
Обновление Knowledge Base, изменение prompt/workflow/model behavior и изменение autonomy grants MUST быть разными типами change с разными gates.

### CI-008 — No self-approval
Manager/Worker MUST NOT approve собственные Improvement Proposals, security/policy changes или grants, расширяющие собственные полномочия.

### CI-009 — Versioned evaluation
Каждый evaluation run MUST фиксировать версии dataset, rubric/evaluator, prompt, model/provider profile, tools, workflow and application build.

### CI-010 — Regression evaluation
Кандидатное изменение MUST пройти применимые regression suites до approval/release.

### CI-011 — Independent review
Критические и высокорисковые изменения MUST проходить независимую QA; security/tool/permission changes дополнительно проходят security/policy review.

### CI-012 — Guardrail veto
Нарушение hard safety/security/privacy/ACL/provenance guardrail MUST блокировать release независимо от улучшения aggregate score.

### CI-013 — Approval matrix
Для каждого change class MUST быть определены owner, reviewers, approver and required evidence. Отсутствие владельца/approver блокирует активацию.

### CI-014 — Controlled lifecycle
Proposal MUST следовать управляемым статусам от Draft/Triage через Evaluation/Approval к Release/Measure или Rejected/Rolled Back.

### CI-015 — Release version pinning
Production deployment MUST ссылаться на конкретные approved artifact/config versions; плавающие latest references запрещены для критичных компонентов.

### CI-016 — Shadow mode isolation
Shadow execution MUST NOT создавать реальные внешние side effects или изменять canonical project state.

### CI-017 — Canary and staged release
Для поддерживаемых типов изменений MUST быть возможность ограниченного rollout, pause and rollback; если canary неприменим, это фиксируется в release plan.

### CI-018 — Post-release measurement
Каждый релиз улучшения MUST иметь baseline, measurement window, primary metric and guardrails; результат фиксируется в Proposal.

### CI-019 — Rollback decision
При hard guardrail breach или согласованном regression threshold система MUST остановить rollout и инициировать rollback/containment.

### CI-020 — Rollback limitations
Если изменение необратимо (например, external side effect или data migration), Proposal MUST описывать compensation/forward-fix/reconciliation; нельзя обещать универсальный rollback.

### CI-021 — Capability-scoped autonomy
Autonomy level MUST назначаться по capability, action class, environment and scope, а не глобально для всей системы.

### CI-022 — Explicit autonomy grant
A3/A4 execution MUST require explicit versioned Autonomy Grant with allowed operations, denials, budgets, expiry, approval and escalation conditions.

### CI-023 — Policy enforcement per action
Policy & Permission Engine MUST independently check current grant and permissions for each protected action; agent-provided claims are insufficient.

### CI-024 — No inherited expansion
New Worker Run MUST NOT automatically inherit broader autonomy grants than its validated scope; grants are explicitly bound to scope and expiry.

### CI-025 — No self-escalation
Agent MUST NOT raise its own autonomy level, extend grant scope, increase budgets or remove denials.

### CI-026 — Reserved human decisions
Business requirement approval, baseline approval, critical business decisions and security policy activation MUST remain human-controlled unless a separately approved governance policy explicitly changes a non-reserved action; reserved decisions remain human.

### CI-027 — Autonomy promotion evidence
Promotion MUST require representative evaluation evidence, independent QA, security/policy tests, sample sufficiency, robustness, provenance, side-effect safety and recovery evidence.

### CI-028 — No single-score promotion
Autonomy MUST NOT be promoted solely on aggregate success rate, volume of completed tasks or subjective impression.

### CI-029 — Auditability
Signal access, proposal changes, evaluation runs, approvals, grants, releases, rollbacks and human overrides MUST be auditable.

### CI-030 — Tenant/project isolation
Signal collection, evidence access, evaluation datasets, reports and release scopes MUST enforce organization/project ACL and prevent cross-tenant leakage.

### CI-031 — Glossary governance
Canonical glossary changes MUST be versioned, reviewed and approved by Glossary Owner; agents may propose but MUST NOT activate changes.

### CI-032 — Glossary validation
UI labels, user docs and generated artifacts SHOULD be checked for canonical terminology and deprecated terms, with context-aware exceptions.

### CI-033 — Evaluation integrity
Changes to evaluator, rubric or dataset MUST be reviewed as first-class changes; they MUST NOT silently weaken acceptance criteria or hide regressions.

### CI-034 — Improvement workflow durability
Long-running evaluation, approval, staged release and measurement workflows MUST be orchestrated durably through Temporal or approved Workflow Engine.

### CI-035 — Human-readable rationale
Each proposal, approval, rejection, autonomy grant and rollback MUST include rationale and supporting evidence references.

### CI-036 — Insufficient evidence
If sample size, provenance, rights or evaluation coverage is insufficient, system MUST keep the proposal non-active and request more evidence/review.

### CI-037 — Monitoring after promotion
A3/A4 capabilities MUST have active telemetry, alerts, periodic review and an owner; expiry/review dates MUST be enforced.

### CI-038 — Emergency disable
Authorized operators MUST be able to revoke autonomy grants and disable affected capability/action classes without deleting audit history.

### CI-039 — Improvement outcome segmentation
Metrics MUST be segmented by capability, task class, project type and relevant model/prompt/tool version to avoid misleading aggregate results.

### CI-040 — Learning does not grant permission
Accumulated knowledge, successful task history or improved evaluation scores MUST NOT automatically expand permissions or autonomy.


### CI-041 — Glossary referential integrity
Машиночитаемый Glossary MUST проверяться на уникальность term_id/canonical_term, существование всех related_terms, корректность статусов и соответствие JSON Schema. Ошибки целостности блокируют публикацию новой версии Glossary.

### CI-042 — Documentation release binding
Пользовательская документация MUST быть связана с конкретной версией продукта/release и MUST NOT описывать недоступные или не прошедшие acceptance функции как доступные.

### CI-043 — Documentation evidence
Каждая пошаговая пользовательская инструкция MUST быть подтверждена проверенным пользовательским сценарием на release build; screenshots MUST иметь версию сборки и дату проверки.

### CI-044 — Documentation change impact
Изменение UI, workflow, permission, status, API-visible behavior или пользовательского процесса MUST запускать оценку влияния на соответствующие user guides, onboarding, glossary и FAQ.

### CI-045 — Accessibility and localization review
Перед публикацией пользовательские руководства MUST пройти проверку доступности, понятности терминологии и согласованности локализации для поддерживаемых языков.

## 2. Открытые параметры
- Statistical sample-size and confidence policy.
- Numerical quality/safety thresholds.
- Measurement windows by change class.
- Owner/approver matrix per organization.
- Retention and deletion policy for improvement evidence.
- A0–A4 approval and initial allowed capabilities.
- Release/canary integration details.

## 3. Acceptance criteria
- Improvement Proposal lifecycle and versioning defined.
- Evidence and evaluation manifests reproducible.
- Approval and security gates enforced independently of Manager.
- A0–A4 scope can be assigned per capability/action class.
- No self-approval or self-escalation path.
- Shadow/canary/rollback and post-release measurement supported.
- Glossary governance connected to product artifact lifecycle.
- Tenant/project ACL and data minimization apply end-to-end.
- Glossary document and entries pass schema plus semantic referential-integrity validation.
- User-facing documentation is release-bound, scenario-verified, accessible and localized before publication.


---

# Дополнение v1.2 — scope and release status

CI-001..CI-045 остаются нормативными requirements для governed improvement capability, но Continuous Improvement runtime и autonomy grants beyond A2 не входят в MVP implementation increment. MVP реализует signal capture, curated examples/evaluation case workflow, human approval and versioned prompt/rules release only where explicitly enabled. No automated training or self-modification.


---

# Дополнение v1.3 — нормативный статус требований

**Статус:** BASELINED — CI-001…CI-045 являются нормативными требованиями governed improvement. Это не означает, что весь Continuous Improvement runtime входит в MVP или уже реализован.

MVP включает разрешённый сбор сигналов, curated/sanitized evaluation cases, human-reviewed improvement proposals и versioned prompt/rules release только в явно разрешённых пределах. Fine-tuning, automated self-modification, automatic permission expansion and A3/A4 autonomy запрещены. Post-MVP runtime реализуется отдельными increments после approval matrix, evidence thresholds, privacy/retention rules and release gates.

**Актуальные нормативные зависимости:** `AI_RES_Document_Registry_v4.1.md`, `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.3.md`, `AI_RES_Continuous_Improvement_Contracts_v1.1.md`, `AI_RES_Evaluation_and_Release_Gates_v1.0.md`, `AI_RES_Claude_Code_Implementation_Spec_v1.22.md`.

Все требования остаются обязательными для соответствующей capability, когда она вводится в scope; post-MVP требования не являются разрешением реализовать capability в MVP.
