# AI RES — Evaluation Framework и Release Gates

**Версия:** 1.0 | **Статус:** BASELINED.

## 1. Принцип

Качество AI RES оценивается не одним общим score, а по task class, компоненту, workflow, риску и версии. Evaluation не заменяет Policy Engine, QA, human approval или security controls.

## 2. Наборы оценки

`EvaluationCase`: case_id, task_class, scenario, sanitized input/context fixture, expected assertions/rubric, risk, source/provenance, dataset_version, split, owner, reviewer, last_reviewed_at, limitations. Golden set immutable/versioned; production examples попадают туда только после triage, rights/privacy review, sanitization, deduplication и approval.

Наборы: elicitation, research, requirement extraction/quality, business/system analysis, API/integration, modeling, QA, traceability/impact, retrieval, planning/orchestration, tool use, security/adversarial, end-to-end Epic.

## 3. Evaluation methods

- Deterministic assertions and schema validation.
- Reference/rubric evaluation by trained reviewers.
- LLM-as-judge as secondary signal only; calibrated against human sample, position bias and model version tracked.
- Pairwise comparison for model/prompt/retrieval changes.
- Adversarial and security testing.
- Production trace review after redaction/consent and ACL checks.

## 4. Metrics

Task-specific correctness/completeness, evidence support, requirement quality, traceability coverage, contradiction/ambiguity, tool success, unauthorized action count, retrieval recall/precision, hallucination/unsupported-claim rate, human rework, time/cost, latency, failure/recovery. Every metric has definition, denominator, exclusions, data source, segmentation, owner and window.

## 5. Release gates

- Contract/schema and deterministic domain tests: all mandatory tests pass.
- Security/privacy: zero critical leakage, privilege escalation, unauthorized side effect, or reserved-decision violation.
- Critical workflow: no regression in mandatory acceptance assertions.
- Model-based quality: task-class threshold established from baseline and human calibration; no universal arbitrary threshold.
- Retrieval: zero ACL leakage; quality/latency thresholds established per query class.
- Shadow/canary only with pinned versions, monitoring, rollback and owner approval.
- Evaluation manifest binds model/provider/version, prompts, tools, rules, retrieval/index, context builder, workflow and dataset versions.

## 6. Continuous evaluation

Changes to model, prompt, tool, Worker contract, retrieval, embedding, rules, workflow or artifact renderer trigger impact-based regression selection. Production incidents become regression cases after sanitization and review. Do not use raw production traces as training/evaluation data by default.

## 7. MVP

Deterministic contract/domain tests, curated task-class eval sets, retrieval benchmark, security/adversarial suite, human review sample, release manifest and regression gates. Automated promotion and autonomous rollout are post-MVP.
