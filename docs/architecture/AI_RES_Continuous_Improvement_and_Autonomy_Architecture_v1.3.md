# AI RES — Архитектура непрерывного улучшения и управляемой автономности

**Версия:** 1.3  
**Статус:** BASELINED — MVP governance and A0–A2; post-MVP A3/A4 and organizational governance remain WORKING
**Блок:** 16A — Continuous Improvement & Autonomy Governance

## 1. Назначение

Документ определяет, как AI RES выявляет возможности улучшения, формирует предложения, проверяет их на данных и тестах, получает необходимые approvals, выпускает изменения и измеряет эффект. Он также задаёт управление автономностью отдельных capability/action class.

Архитектура не предполагает самопроизвольного самообучения production-модели на пользовательских диалогах. Накопление данных, формирование кандидатов улучшения, изменение поведения и расширение полномочий — разные процессы.

## 2. Архитектурные принципы

1. Evidence before change: улучшение должно ссылаться на проверяемые сигналы и примеры.
2. Version everything: datasets, rubrics, prompts, workflows, tools, glossary, model profiles and policies имеют версии.
3. Separate observe from mutate: сбор сигналов не должен менять production поведение.
4. No self-authorization: агент не может сам утверждать изменение или расширять собственные права.
5. Capability-scoped autonomy: автономность задаётся по capability + action class + environment + scope.
6. Safety and quality guardrails override aggregate efficiency metrics.
7. Human approval remains mandatory for reserved decisions and high-impact changes.
8. Reproducibility: каждый evaluation/release связывается с manifest версий.
9. Reversible rollout: изменение должно иметь rollback/containment strategy, если оно технически обратимо.
10. Learning is not permission: накопленный опыт не является основанием для автоматического расширения полномочий.

## 3. Компоненты

### 3.1. Improvement Signal Collector
Получает сигналы из:
- Agent/Worker Run outcomes;
- independent QA и verification;
- human corrections, returned-for-rework, approvals/rejections;
- user feedback;
- incidents, alerts, operational runbooks;
- evaluation/regression results;
- cost, latency, retry, tool and provider metrics;
- drift and retrieval quality indicators.

Collector принимает только разрешённые метаданные/содержимое с учётом privacy, retention, tenant/project ACL and consent/policy. Raw prompts, responses and source payloads не становятся автоматически training data.

### 3.2. Evidence Store
Хранит ссылки на первичные evidence, sanitized examples, source versions, evaluation records, QA findings and feedback records. Сохраняет provenance, rights, data classification, retention and access policy. Raw evidence остаётся в исходном доменном хранилище; Improvement subsystem использует ссылки/санитизированные копии согласно правилам.

### 3.3. Pattern & Opportunity Analyzer
Выявляет повторяющиеся дефекты, rework clusters, retrieval misses, prompt/tool failures, drift, high-cost patterns and opportunities. Может использовать статистику и AI analysis, но выводит гипотезы, а не автоматически меняет production.

### 3.4. Improvement Proposal Registry
Хранит `ImprovementProposal` и версии:
- proposal_id/version/status;
- affected capability/action class/components;
- problem statement and evidence refs;
- hypothesis and expected measurable outcome;
- baseline and target;
- risk/impact and data classification;
- proposed change artifact refs;
- evaluation plan and guardrails;
- approval requirements/decisions;
- release and rollback plan;
- owner, timestamps and audit trail.

Статусы: `DRAFT`, `SUBMITTED`, `TRIAGE`, `EVALUATION_PENDING`, `EVALUATION_FAILED`, `READY_FOR_APPROVAL`, `APPROVED`, `REJECTED`, `SCHEDULED`, `SHADOW`, `CANARY`, `ACTIVE`, `ROLLED_BACK`, `CLOSED`.

### 3.5. Evaluation Orchestrator
Запускает versioned evaluation/regression suites, security/prompt-injection tests, policy compliance tests, quality rubrics and performance/cost comparisons. Для оценки использует изолированное окружение и фиксированный manifest. Изменение evaluator/rubric/dataset само является контролируемым изменением.

### 3.6. Approval & Governance
Определяет обязательных reviewers/approvers по типу изменения, риску, scope and action class. Проверяет наличие evidence, независимой QA, security review, budget and rollback plan. Approval записывается как отдельное неизменяемое решение.

### 3.7. Release Controller
Выпускает только approved version. Поддерживает shadow/staged/canary rollout where applicable, monitoring gates, pause, rollback and version pinning. Не имеет права обходить Policy & Permission Engine.

### 3.8. Outcome Measurement
Сравнивает post-release показатели с baseline в заданном measurement window. Проверяет primary metric, guardrails, сегменты и статистическую достаточность. Закрытие Proposal требует решения сохранить, скорректировать или откатить.

## 4. Канонический цикл

`Observe → Identify → Propose → Evaluate → Approve → Release → Measure`

- Observe: собрать signals, не меняя production.
- Identify: сформулировать pattern, severity, affected scope.
- Propose: создать версионируемую гипотезу изменения.
- Evaluate: воспроизвести проблему и сравнить candidate vs baseline.
- Approve: получить решения требуемых владельцев.
- Release: controlled deployment and version pinning.
- Measure: подтвердить эффект и отсутствие неприемлемой регрессии.

Если evidence недостаточно, proposal остаётся `TRIAGE` или `DRAFT`; система не должна искусственно повышать уверенность.

## 5. Типы улучшений и обязательные gates

| Тип изменения | Пример | Минимальные проверки | Approval |
|---|---|---|---|
| Knowledge content | Добавить проверенное правило/справку | Provenance, rights, conflict, freshness, QA | Владелец знаний/проекта |
| Retrieval/index | Изменить chunking/ranking/index | Retrieval benchmark, ACL isolation, regression | Capability Owner |
| Prompt/template | Изменить инструкции Worker | Eval set, prompt injection, regression, output schema | Capability Owner + QA; Security при риске |
| Workflow/planning | Изменить декомпозицию/переходы | Workflow regression, idempotency, failure/recovery | Workflow Owner + QA |
| Tool/connector | Новая операция или изменение адаптера | Contract, sandbox, permission, side-effect, security tests | Tool Owner + Security |
| Evaluation rubric/dataset | Изменить критерии/выборку | Version diff, bias/coverage review, independent approval | Evaluation Owner + Approver |
| Model/provider profile | Сменить модель/параметры/provider | Quality, privacy, cost, latency, security comparison | Model Owner + Security/Policy |
| Glossary | Изменить канонический термин | Terminology review, downstream impact, schema validation | Glossary Owner |
| UI/onboarding | Изменить подсказки/UX | Usability/accessibility and task outcome tests | Product Owner |

Низкорисковое изменение может иметь упрощённый workflow только если его action class предварительно разрешён. Нельзя переносить approval одного типа изменения на другой.

## 6. Модель автономности

### 6.1. Уровни (предлагаемая шкала)
- A0 Observe — сбор/анализ сигналов, без изменения.
- A1 Recommend — рекомендации с evidence.
- A2 Prepare — черновики изменений, тесты и rollout plan; активация запрещена.
- A3 Controlled execution — выполнение заранее разрешённого низкорискового действия в ограниченном scope с обязательным audit/rollback.
- A4 Bounded autonomy — самостоятельный выбор и выполнение действий в утверждённом action class, бюджете и среде; мониторинг и выборочный аудит обязательны.

### 6.2. Объект назначения
Уровень задаётся кортежем:
`(capability_id, action_class, environment, scope, autonomy_level, policy_version, effective_period)`.

Глобального «уровня автономности AI RES» нет. Один Worker может иметь разные уровни для разных action classes.

### 6.3. Autonomy Grant
Каждое разрешение должно включать:
- grant_id/version, subject/capability/action class;
- project/organization/environment scope;
- allowed operations and explicit denials;
- limits: count, cost, tokens, duration, concurrency;
- required preconditions and evidence;
- human escalation conditions;
- approval reference and expiry/review date;
- rollback/compensation procedure;
- telemetry/audit requirements.

Policy & Permission Engine проверяет grant на каждом действии. Grant не наследуется автоматически новым Worker Run и не может расширяться агентом.

### 6.4. Пример профиля
- Черновой re-index поискового индекса в test environment: может быть кандидатом на A3/A4 после проверок.
- Prompt update: A2 по умолчанию; активировать только через evaluation/approval/release.
- Изменение security policy, утверждение бизнес-требования или baseline: A0/A1; решение остаётся человеку.

Это примеры проектной рекомендации, не утверждённые полномочия.

## 7. Критерии допуска и повышения автономности

Обязательные evidence dimensions:
- representative versioned evaluation set and sample sufficiency;
- task outcome and first-pass acceptance;
- independent QA and critical defect rate;
- human correction/rework;
- robustness across project types, source formats and languages;
- prompt-injection/adversarial resilience;
- policy compliance and unauthorized action attempts;
- evidence/provenance completeness;
- tool side effects and reconciliation;
- cost/latency/resource envelope;
- recovery/rollback success;
- escalation correctness and uncertainty calibration.

Нельзя агрегировать всё в один success score, скрывающий критические дефекты. Hard safety gates имеют право вето независимо от среднего качества.

## 8. Метрики и guardrails

Primary metrics выбираются под тип Proposal. Общие группы:
- quality: defect, critical defect, QA pass, unsupported assertions;
- rework: human correction, return-for-rework;
- effectiveness: accepted outcome, completion by task class;
- autonomy: eligible actions, intervention, escalation;
- safety: policy violations, unauthorized attempts, unsafe side effects;
- provenance: evidence coverage, traceability completeness;
- efficiency: time, tokens, cost, tool calls;
- reliability: retries, timeouts, recovery, rollback;
- experience: user satisfaction, adoption, stakeholder decision time.

Guardrails: security/privacy violations, critical defect, data leakage, unauthorized side effect, broken ACL, loss of provenance, corrupted baseline. Нарушение hard guardrail блокирует rollout или вызывает rollback независимо от улучшения primary metric.

## 9. Интеграция с AI RES

- Observability emits allowed signals.
- Evaluation framework provides versioned suites and rubrics.
- Artifact Registry stores immutable candidate/approved versions.
- Glossary provides canonical terminology and schema validation.
- Rules Registry stores approved improvement policies and gates.
- Policy & Permission Engine enforces action grants.
- Temporal orchestrates long-running evaluation, approval, release and measurement workflows.
- Manager may identify and propose improvement, but cannot approve reserved changes or grant itself permissions.
- Human Workspace provides review/approval and diff/provenance views.

## 10. Security, privacy and data governance

- Tenant/project ACL applies to signal collection, evidence retrieval, evaluation datasets and reports.
- Data minimization and redaction occur before content is copied into evaluation/evidence stores.
- Source rights/licensing and retention are checked before reusing source material.
- No raw user content is used for model training by default.
- Secrets, credentials, private prompts and confidential payloads are excluded unless an explicit reviewed policy permits a narrowly scoped sanitized use.
- Evaluation datasets are access-controlled, versioned and deletion-aware.
- Logs/telemetry do not become an alternate ungoverned knowledge base.

## 11. Failure and rollback

- Evaluation failure returns Proposal to `EVALUATION_FAILED`; no release.
- Approval rejection returns to `REJECTED`; no activation.
- Release controller failure stops rollout and restores last approved version where safe.
- Guardrail breach during canary triggers pause/rollback and incident record.
- Rollback of schema/data changes may require forward-fix or restore; not every change is reversible.
- Uncertain external side effects require reconciliation, not blind rollback.
- Every state transition and human override is audited.

## 12. Open decisions

- Exact statistical methods/sample-size policy by task class.
- Numeric guardrail thresholds and measurement windows.
- Formal owner/approver mapping by organization.
- Dataset retention/deletion and source-rights policy details.
- A0–A4 adoption and terminology approval.
- Whether any A3/A4 capability is allowed in initial production.
- Release automation integration and canary granularity.

## 13. Связанные документы

- `AI_RES_Continuous_Improvement_Requirements_v1.1.md`
- `AI_RES_Continuous_Improvement_Contracts_v1.0.md`
- `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json`
- `AI_RES_Glossary_v1.0.md` / `AI_RES_Glossary_v1.0.json`
- `AI_RES_Glossary_Entry_Schema_v1.1.json`
- `AI_RES_Glossary_Document_Schema_v1.0.json`
- `AI_RES_Post_Implementation_Productization_Plan_v1.2.md`
- `AI_RES_Agent_Observability_and_Evaluation_v1.0.md`
- `AI_RES_Observability_Architecture_v1.0.md`
- `AI_RES_Tool_Registry_and_Tool_Management_MVP_v0.3.md`
- `AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md`

## 14. Контракты и доменные состояния (дополнение v1.1)

Детальные DTO и API-операции вынесены в `AI_RES_Continuous_Improvement_Contracts_v1.0.md`, машинно-читаемые схемы — в `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json`. Они являются проектными контрактами и до реализации должны быть согласованы с основными Domain Model, API Contracts и AsyncAPI. Не создавать параллельные сущности, если соответствующая сущность уже существует в основной доменной модели.

Канонические агрегаты блока:
- `ImprovementProposal` с immutable versions и append-only governance decisions;
- `EvaluationManifest` и `EvaluationResult`, связанные с точной версией Proposal и версиями всех влияющих компонентов;
- `AutonomyGrant`, активируемый только после отдельного approval и проверяемый Policy & Permission Engine на каждом защищённом действии;
- `GlossaryEntry` / `GlossaryVersion` как логические записи; при реализации повторно использовать Artifact/ArtifactVersion и Artifact Registry, если это покрывает lifecycle, вместо создания дублирующего хранилища.

События проходят через Transactional Outbox. Событийные payloads содержат идентификаторы, версии и ссылки, но не полные prompts, исходные документы, секреты или приватные evaluation payloads. Полные AsyncAPI message schemas должны быть добавлены в основной AsyncAPI до реализации consumers.

Статусная модель Proposal из контракта является нормативной для проектирования; переход в `APPROVED` невозможен без применимых evaluation и approvals, а в `ACTIVE` — без pinned versions и release gates. `INCONCLUSIVE` не эквивалентен успешной оценке.

## 15. Решения, которые остаются открытыми

- Утверждение шкалы A0–A4 и допустимых action classes по каждому уровню.
- Конкретные owner/reviewer/approver роли и делегирование по организациям.
- Статистическая достаточность, confidence policy, численные thresholds и окна измерений.
- Evidence retention, deletion, source rights and consent.
- Решение, какие части Continuous Improvement входят в MVP, а какие остаются post-MVP.
- Интеграция новых DTO/endpoints/events в основные OpenAPI/AsyncAPI и Domain Model.

До закрытия этих решений A3/A4 не включать; проектные контракты не означают наличие runtime capability.



---

# Дополнение v1.2 — MVP learning/autonomy baseline

Статус: BASELINED. MVP использует non-parametric curated experience only. Fine-tuning, automatic prompt/rule updates and cross-tenant learning are excluded. A0 Observe, A1 Recommend, A2 Prepare are the only permitted autonomy levels in MVP; A3/A4 disabled pending separate evidence-backed approval. Improvement signal never changes runtime behavior without versioned proposal, evaluation, review, approval and release. Permissions are checked per action and never learned/inferred.


---

# Дополнение v1.3 — статус и границы baseline

**Статус:** BASELINED — MVP governance and autonomy boundary; post-MVP A3/A4 and organization-specific governance details remain WORKING.

Для MVP утверждены: Observe → Identify → Propose → Evaluate → Approve → Release → Measure; evidence-backed, immutable/versioned proposals; separation of knowledge updates, behavior changes and permission changes; no self-approval; A0 Observe, A1 Recommend, A2 Prepare only. A3/A4 disabled. Fine-tuning, automatic prompt/rule updates, cross-tenant learning and self-modification are excluded. Любое изменение production behavior требует versioned proposal, evaluation, independent review where required, approval, pinned release and post-release measurement. Permissions are checked per action and are never inferred from learned experience.

**Остаётся WORKING:** детальная организационная approval matrix, статистические thresholds/sample sizes, retention/legal rights, A3/A4 policy, post-MVP rollout and autonomy grants. До отдельного решения эти возможности не реализуются и не активируются.

**Актуальные нормативные зависимости:** `AI_RES_Document_Registry_v4.1.md`, `AI_RES_Continuous_Improvement_Requirements_v1.3.md`, `AI_RES_Continuous_Improvement_Contracts_v1.1.md`, `AI_RES_Evaluation_and_Release_Gates_v1.0.md`, `AI_RES_Glossary_v1.1.md`, `AI_RES_Security_Controls_and_Requirements_v1.2.md`, `AI_RES_Claude_Code_Implementation_Spec_v1.22.md`.

Исторические предложения A0–A4 в основном тексте читаются с учётом этого дополнения; A3/A4 не входят в MVP baseline.
