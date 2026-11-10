# AI RES — Наблюдаемость и оценка ИИ-агентов

**Версия:** 1.2 | **Статус:** BASELINED — agent telemetry/evaluation design; thresholds and sample sizes require calibration

## 1. Назначение
Описывает наблюдаемость Manager/Workers и использование production signals для контролируемого улучшения. Дополняет Evaluation Framework главы 9, но не заменяет его.

## 2. Модель наблюдения
Единица наблюдения — не только HTTP request или LLM call. Один сценарий может включать Plan Versions, Tasks, WorkerRuns, consultation, delegated subtask, handoff и independent QA. Корреляция:
`Project → Epic → Plan Version → Task → WorkerRun → Temporal Workflow/Run → LangGraph Thread → Context Package Version → Artifact/Review`.

Manager и Workers — логические роли; не предполагать отдельный физический контейнер для каждой специализации.

## 3. Инструментация Manager
Наблюдать:
- создание/изменение Plan Version, декомпозицию и назначение Tasks;
- выбор Worker capability и rationale reference;
- Readiness Gate initiation/result;
- зависимости и параллелизм;
- CONSULTATION / DELEGATED_SUBTASK / HANDOFF / INDEPENDENT_QA;
- разрешение конфликтов, escalation и human decision waits;
- replanning, recovery, cancellation, completion.

Не записывать chain-of-thought или скрытые рассуждения. Хранить структурированные decision records: action, reason code, evidence/artifact references, policy applied, unresolved questions.

## 4. Инструментация Worker и Temporal
Worker: WorkerRun lifecycle/readiness, LangGraph node spans, context retrieval/build, provenance refs, LLM calls, tool calls, validation, WorkerResult submission, notices/coordination, QA outcomes.

Temporal: Workflow/Activity lifecycle, task queue, schedule-to-start, retries, timeouts, heartbeat, cancellation, Signals/Updates, stuck/long-running workflows. Workflow IDs связываются с domain IDs; большие payloads не копировать в telemetry. Temporal Web UI — internal admin only.

## 5. Outcome taxonomy
Разделять:
- **Execution outcome:** `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `BLOCKED`, `RETRIED`, `RECOVERED`.
- **Orchestration acceptance:** `ACCEPTED_FOR_ORCHESTRATION` либо не принят; это не verification/approval.
- **Verification:** `VERIFIED`, `VERIFIED_WITH_LIMITATIONS`, `DISPUTED`, `UNVERIFIED`.
- **Independent QA:** отдельный Review/WorkerRun; исход PASS / PASS_WITH_LIMITATIONS / FAIL / INCONCLUSIVE должен согласовываться с QA contracts.
- **Human decision:** соответствующие lifecycle states `PENDING`, `APPROVED`, `REJECTED`, `CHANGES_REQUESTED`, `DEFERRED`.

Не сводить их к одному success rate. Технически завершённый Run, принятый для ограниченного downstream use, но не прошедший QA, не является VERIFIED.

## 6. Метрики поведения
| Область | Сигналы | Разрезы |
|---|---|---|
| Manager planning | plan duration, tasks proposed/approved/rejected, replans, dependency changes | Epic type, Manager/model/prompt version |
| Readiness | pass/fail, reason, time-to-ready | Worker capability, task class |
| Worker | run duration/outcome, timeout, blocker, retries | capability/version, task type |
| Coordination | requests by type, approved/denied, latency, unresolved | source/target capability, policy |
| Tools | calls, success, timeout, permission denial, fallback | tool/version, operation class |
| Context/retrieval | latency, source count, package failures, freshness/coverage | source type, index version |
| LLM | calls, tokens, latency, rate limit, estimated cost, fallback | provider/model, task class |
| Quality | verification distribution, QA outcomes, rework, defect categories | artifact/requirement type, evaluator version |
| Human oversight | approvals pending, wait duration, escalations | decision class/risk |
| UX | feedback, repeated prompts, abandonment/interruption | workflow stage, task class |

Каждая quality metric сопровождается критерием, источником, evaluator version и sample size.

## 7. Evaluation и production traces
Production telemetry — сигнал и материал расследования, не ground truth. Успешные и сбойные traces могут стать кандидатами в Evaluation Set после sanitization, review, deduplication, labeling и проверки прав.

Evaluation Set версионируется; фиксируются provenance, permitted purpose, evaluator/judge version, rubric version, run/model/prompt version, timestamp, outcome, evidence refs и limitations. LLM-as-a-judge не единственный критерий: сверять с human-labeled sample и измерять agreement/false positives/negatives.

Regression case должен воспроизводить sanitized input/context fixture и expected criteria, а не секретные production payloads. Изменение модели/prompt/tool/workflow требует сравнения с baseline evaluation set.

## 8. Пользовательская обратная связь
Явные сигналы: rating, thumbs up/down, comment, unresolved task, correction request. Неявные кандидаты: повторная формулировка, повторный запуск, cancel, abandonment, длительное ожидание подтверждения. Не трактовать любой повтор как негатив без контекста.

Feedback record: feedback_id, timestamp, category, optional sanitized rating/comment, project/epic/task/run refs under ACL, trace ref, task type/workflow stage, purpose/consent/retention metadata, review status/disposition.

Feedback не запускает автоматическое обучение или изменение модели; он создаёт reviewed candidate для product/QA backlog.

## 9. Drift monitoring
Начинать с baseline distributions и трендов: язык/длина/тип задач, tool usage, retrieval coverage, error/retry/fallback, latency, tokens/cost, quality outcomes.

Методы главы 10:
- KS — непрерывные распределения;
- KL-divergence — вероятностные распределения;
- PSI — доли/бакеты;
- embedding similarity — семантические изменения.

Для каждого метода задать baseline/current windows, feature definition, minimum sample, threshold calibration, multiple-testing handling и owner. Пороговые примеры главы не являются универсальными настройками AI RES.

Реакция: alert → проверить data pipeline → сегментировать по task/source/model/prompt/tool → оценить quality/retrieval/feedback → выбрать корректирующее действие → evaluation/regression → controlled release. Drift не разрешает автономный fine-tuning или изменение policy.

## 10. Shadow / Canary
Shadow: новая версия обрабатывает допустимую копию входа, не показывает результат пользователю и не выполняет side effects. Нужны no-write tools, изолированные budgets, version tags и отдельная корреляция.

Canary возможен только при traffic routing, cohort assignment, privacy basis, kill switch и rollback. Для локального single-node Compose MVP canary не обязателен. Сравнивать outcomes, quality, latency, tokens/cost, tool selection, retries, escalation и safety/permission events. Не расширять rollout при ухудшении критичных quality/safety signals.

## 11. Recovery и автономность
Допустимые примеры: bounded retry/fallback для временного provider failure; безопасный alternate path при tool failure; запрос уточнения при недостатке данных; escalation при риске/противоречии.

Recovery actions должны быть разрешены Policy Engine, ограничены attempts/time/budget/scope, не обходить Readiness Gate/permissions/approvals/QA, логироваться с reason/evidence и проверяться по фактическому результату.

## 12. Ownership
Назначить metric owner, technical owner, responder, reviewer. Рекомендуемое распределение: Product/BA — пользовательские outcomes/rework; AI/ML — model/prompt/retrieval/quality; Platform/SRE — infra/Temporal/telemetry; Security — sensitive telemetry/audit. В небольшой команде роли могут совмещаться, ответственность должна быть явной.

## 13. Критерии приёмки
1. Выбранный Manager–Worker сценарий имеет связанные spans ключевых этапов.
2. Различаются execution outcome, orchestration acceptance, verification, independent QA и human approval.
3. LLM/tool calls имеют latency/outcome/version; tokens/cost — если доступны.
4. Trace связана с task/run/context/artifact refs с соблюдением ACL.
5. Regression candidate проходит sanitization/review.
6. Feedback не запускает обучение автоматически.
7. Drift не меняет автоматически model/policy.
8. Shadow run не выполняет side effects.
9. Recovery ограничен, объясним, аудируем и не обходит permissions/readiness.
10. У метрик есть owner и интерпретация.

## 14. Открытые решения
Evaluation Set governance; разрешённые implicit feedback signals; shadow isolation/budget; drift features/thresholds; фактический RACI; Langfuse vs OTel-only.


---

# Дополнение v1.1 — evaluation baseline

Статус: BASELINED. Apply `AI_RES_Evaluation_and_Release_Gates_v1.0.md`. Every Worker task class has evaluation rubric and versioned fixtures before production enablement. LLM judge is secondary only; deterministic assertions and human calibration required. Model/prompt/tool/retrieval/rules/workflow changes trigger impact-based regression. Production traces require sanitization and ACL review before inclusion in evaluation sets. Zero critical security/privacy regressions is mandatory.


---

# Дополнение v1.2 — статус и нормативная карта

**Статус:** BASELINED — agent telemetry and evaluation integration design. Numerical thresholds, sample sizes and metric calibration remain WORKING until representative evaluation data exists.

Нормативно разделяются execution outcome, orchestration acceptance, verification, independent QA и human decision. Correlation связывает Project/Epic/Plan/Task/WorkerRun/Temporal/LangGraph/ContextPackage/Artifact. Chain-of-thought и скрытые рассуждения не собираются. LLM-as-judge является вторичным сигналом; deterministic assertions и human calibration обязательны. Production traces становятся evaluation evidence только после sanitization, ACL/rights review и versioning. Shadow execution не имеет side effects; recovery bounded и не обходит Gate/Policy/Approval.

**Актуальные нормативные зависимости:** `AI_RES_Document_Registry_v4.1.md`, `AI_RES_Observability_Architecture_v1.2.md`, `AI_RES_Evaluation_and_Release_Gates_v1.0.md`, `AI_RES_Operation_WorkerRun_Event_Model_v1.4.md`, `AI_RES_Continuous_Improvement_Requirements_v1.3.md`, `AI_RES_Security_Controls_and_Requirements_v1.2.md`.

Runtime instrumentation, task-class golden sets, thresholds and sample sufficiency require implementation and calibration; this status does not claim those tests have passed.
