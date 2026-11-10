# AI RES — Требования к мониторингу и оповещениям

**Версия:** 1.0 | **Статус:** WORKING | **Дата:** 2026-11-10

## 1. Назначение и приоритеты
Проверяемые требования к сбору, хранению, отображению и использованию эксплуатационной telemetry AI RES.
- `MUST` — обязательное для заявленного MVP.
- `SHOULD` — рекомендуется; отклонение требует rationale.
- `POST-MVP` — последующее расширение.
- `OPEN` — решение не принято, не считать реализованным.

## 2. Функциональные требования

| ID | Приоритет | Требование | Проверка |
|---|---|---|---|
| OBS-MON-001 | MUST | Собирать health/availability и ошибки API, Manager, Worker, Temporal, PostgreSQL, MinIO, LLM Gateway. | Dashboard по каждому компоненту. |
| OBS-MON-002 | MUST | Собирать distributed traces API → Manager → Temporal → Worker → LLM Gateway → Tool. | Сквозной тестовый Run прослеживается. |
| OBS-MON-003 | MUST | Структурированные логи содержат timestamp, severity, service, environment, release_id и correlation IDs при наличии. | Фильтрация и переход к trace. |
| OBS-MON-004 | MUST | Измерять длительность, outcome и error category Task, WorkerRun, Workflow и ключевых Activities. | Counts, duration distributions, failure categories. |
| OBS-MON-005 | MUST | Измерять latency/errors/timeouts/retries/fallback вызовов tools. | Метрики и spans по tool_name/version. |
| OBS-MON-006 | MUST | Собирать provider/model, LLM latency, input/output tokens, rate limits/errors, fallback и estimated cost при наличии pricing. | Dashboard без prompt content. |
| OBS-MON-007 | MUST | Отражать Temporal backlog, schedule-to-start, Activity failures/retries и длительные/stuck workflows. | Тестовые состояния обнаруживаются. |
| OBS-MON-008 | MUST | Отражать Readiness Gate, Manager/Worker outcomes, blockers, rework и independent QA. | Агрегаты и ACL-safe drill-down. |
| OBS-MON-009 | MUST | Коррелировать события с release, WorkerDefinition, prompt, model, tool, ruleset и Context Package versions. | Версии видны в trace/log. |
| OBS-MON-010 | MUST | Предоставить dashboards Platform, Workflow, Agent/Worker, LLM/Tools, Telemetry Pipeline. | Dashboard inventory. |
| OBS-MON-011 | MUST | Для критичных отказов иметь actionable alerts с severity, owner, response и runbook. | Все alert rules содержат поля. |
| OBS-MON-012 | MUST | Логи, metrics и traces используют общую correlation model. | Trace/log lookup работает. |
| OBS-MON-013 | MUST | Обнаруживать деградацию telemetry pipeline. | Collector export errors/dropped signals/backend health. |
| OBS-MON-014 | MUST | Недоступность telemetry backend не блокирует критические API/Workflow операции. | Fault injection; bounded degradation. |
| OBS-MON-015 | MUST | Буферы и retries telemetry ограничены. | Нет бесконечного накопления; лимиты конфигурируются. |
| OBS-MON-016 | MUST | Поддерживать P50/P95/P99 для ключевых latency distributions при достаточной выборке. | Percentile + sample count + window. |
| OBS-MON-017 | SHOULD | Сравнивать поведение по версии приложения, модели, prompt и workflow. | Сопоставимые cohort/filters. |
| OBS-MON-018 | SHOULD | Сохранять sanitized production failures как regression candidates только после review. | Candidate→review→Evaluation Set. |
| OBS-MON-019 | SHOULD | Собирать явную и ограниченный набор неявной обратной связи с привязкой к Task/Run. | Feedback record + trace reference. |
| OBS-MON-020 | POST-MVP | Drift analysis по выбранным признакам и метрикам качества. | Baseline, sample size, method, threshold, owner заданы. |
| OBS-MON-021 | POST-MVP | Shadow comparison новой модели/prompt/workflow. | Shadow не показывает результат и не выполняет side effects. |
| OBS-MON-022 | POST-MVP | Canary rollout только при traffic routing, kill switch и rollback. | Проверены маршрутизация/сравнение/rollback; для local MVP не обязательно. |

## 3. Семантика метрик
| ID | Требование |
|---|---|
| OBS-MON-030 | Для каждой критичной метрики определить смысл, единицу, источник, окно, владельца, baseline и action. |
| OBS-MON-031 | Технический успех должен отличаться от семантического качества и принятия результата. |
| OBS-MON-032 | `ACCEPTED_FOR_ORCHESTRATION`, `VERIFIED`, `VERIFIED_WITH_LIMITATIONS`, `DISPUTED`, `UNVERIFIED`, QA и human approval учитывать раздельно. |
| OBS-MON-033 | Средние значения не использовать без распределения/percentile и sample size там, где важны хвостовые задержки. |
| OBS-MON-034 | `project_id`, `task_id`, `worker_run_id`, `trace_id` и прочие high-cardinality IDs запрещены в Prometheus labels; допустимы в logs/traces при ACL. |
| OBS-MON-035 | LLM cost маркировать `estimated`, если расчёт сделан по локальному pricing, а не provider billing. |
| OBS-MON-036 | Отсутствующая оценка качества не означает нулевое качество или успешность. |

## 4. Security/privacy requirements
| ID | Приоритет | Требование | Проверка |
|---|---|---|---|
| OBS-SEC-001 | MUST | Запретить в telemetry passwords, reset tokens, cookies/session secrets, MFA seeds, recovery codes, API/OAuth tokens, private keys, connection strings. | Canary-secret test. |
| OBS-SEC-002 | MUST | По умолчанию не записывать full prompts/responses, source fragments, documents, source code и confidential payloads. | Canary-content test. |
| OBS-SEC-003 | MUST | Redaction выполнять до telemetry backend; backend не единственная линия защиты. | Export pipeline tests. |
| OBS-SEC-004 | MUST | Scrub stack traces и error messages от secrets/sensitive params. | Synthetic exception tests. |
| OBS-SEC-005 | MUST | Ограничить dashboards/logs/traces/LLM observability по roles и project/tenant ACL. | Negative cross-project tests. |
| OBS-SEC-006 | MUST | Отделить Domain/Security Audit Log от operational telemetry по модели доступа и retention. | Schema/roles/API permissions review. |
| OBS-SEC-007 | MUST | Установить отдельные retention policies metrics/logs/traces/LLM traces/feedback/audit. | Explicit config per class. |
| OBS-SEC-008 | MUST | Ограничить просмотр/экспорт Audit Log; чувствительное чтение может само журналироваться. | Permission + audit-of-audit tests. |
| OBS-SEC-009 | MUST | Temporal Web UI и observability admin interfaces не доступны публично без auth/network restrictions. | Deployment/security test. |
| OBS-SEC-010 | MUST | LLM content capture только по отдельному opt-in с ACL, purpose, redaction и retention. | Default off; opt-in verification. |
| OBS-SEC-011 | MUST | Telemetry не используется для автоматического обучения/изменения модели без reviewed dataset lifecycle. | Data-flow/permission review. |

## 5. Alerting
| ID | Требование |
|---|---|
| OBS-ALR-001 | Alert rule содержит name, severity, scope, condition, evaluation window/for, owner, runbook, user impact, auto_action, silence policy. |
| OBS-ALR-002 | Alerts дедуплицируются и подавляют flapping; paging только для пользовательского impact, integrity или security-critical. |
| OBS-ALR-003 | Alert отделяет обнаруженный факт от гипотезы причины. |
| OBS-ALR-004 | Alert не может автоматически approve requirements, publish artifacts, expand permissions, change model/provider или delete data. |
| OBS-ALR-005 | Автоматическое восстановление только заранее разрешёнными, ограниченными, обратимыми действиями с audit/trace. |
| OBS-ALR-006 | До production-like запуска назначить owner и escalation route каждому критичному alert. |
| OBS-ALR-007 | Низкоуровневые alerts нормализуются для Workspace; не создавать пользователю поток инфраструктурного шума. |

## 6. Минимальный набор SLI и кандидатных SLO
Численные SLO не утверждаются до baseline на прототипе/пилоте. Минимальные SLI:
- service availability/health;
- API request success and latency;
- Task/WorkerRun completion by outcome class;
- workflow queue wait and execution duration;
- tool success/timeout;
- LLM latency/errors/rate limits/tokens/cost per task;
- telemetry export success/drop rate;
- backup job success and recovery verification;
- quality outcomes and rework rate.

Для каждого SLI задать target, measurement window, exclusions, sample size, owner, response и error budget при применимости. Числовые примеры главы 10 не переносить как нормативные пороги.

## 7. Открытые параметры
Численные SLO/thresholds; retention и sizing; alert destinations/on-call; Langfuse enablement/content capture; список implicit feedback; drift features/thresholds; автоматические recovery actions.

## 8. Трассируемость
Связанные документы: `AI_RES_Observability_Architecture_v1.0.md`, `AI_RES_Agent_Observability_and_Evaluation_v1.0.md`, `AI_RES_Infrastructure_Deployment_Operations_v1.4.md`, исходный конспект главы 10.
