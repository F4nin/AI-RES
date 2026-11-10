# AI RES — Learning & Experience Lifecycle

**Версия:** 1.0 | **Статус:** BASELINED.

## 1. Цель

Отделить улучшение продукта/процесса от изменения параметров модели. Успешный Run, feedback или накопленная память не дают агенту новых полномочий.

## 2. Три контура

1. **Operational memory:** факты и результаты конкретного проекта/Epic/Run.
2. **Curated experience:** одобренные exemplars, patterns, playbooks и reusable checklists.
3. **Parametric model training:** SFT/DPO/RFT/RLVR; исключён из MVP.

## 3. MVP improvement loop

Signal (feedback, QA defect, incident, reviewer correction) → triage/classification → privacy/provenance review → Improvement Proposal → hypothesis and expected outcome → evaluation set update or prompt/rule/playbook proposal → independent review → human approval → versioned release → post-release measurement → keep/revise/rollback decision.

Никакой production feedback не меняет prompt, rules, model, tool permissions или memory automatically.

## 4. Governance

Improvement Proposal version immutable; evidence and affected capability/task class explicit. Security/policy changes require security owner approval. Business requirement/baseline decisions remain human. Evaluation manifest and rollback plan required. Cross-tenant reuse requires explicit rights/consent and de-identification; prohibited by default.

## 5. Autonomy

MVP: A0 Observe, A1 Recommend, A2 Prepare. A3 Controlled execution and A4 Bounded autonomy are disabled by default and not part of MVP. Future enablement requires capability/action/environment scoped Autonomy Grant, time bound, budget, allowlist, monitoring, independent evaluation, human approval and emergency revoke. Grant is checked per action; no inheritance widening or self-escalation.

## 6. Fine-tuning decision

No fine-tuning in MVP. Reconsider only when repeated measurable failure persists after prompt/context/tool/workflow improvements; sufficient rights-cleared high-quality data exists; offline eval demonstrates improvement without guardrail regression; security/privacy review and rollback are ready. A training run is a governed release, not background self-learning.

## 7. Metrics

Measure task quality, human correction/rework, recurrence of known defects, regression, drift, privacy/security incidents, cost and latency by task class and segment. A single aggregate score cannot justify autonomy promotion.
