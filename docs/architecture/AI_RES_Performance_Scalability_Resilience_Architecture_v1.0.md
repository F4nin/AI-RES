# AI RES — Архитектура производительности, масштабирования и отказоустойчивости

**Версия:** 1.0  
**Статус:** WORKING  
**Этап:** 15 — Performance, Scalability & Resilience Architecture  
**Дата:** 2026-11-10

## 1. Назначение

Документ определяет архитектурные принципы и требования к производительности, масштабированию, устойчивости к отказам и восстановлению AI RES. Он развивает Infrastructure Deployment & Operations v1.4 и Observability Architecture v1.0, не заменяя их.

Цель — обеспечить предсказуемое поведение системы при росте числа проектов, пользователей, источников, задач, Worker Runs и длительных агентных процессов, а также при частичных отказах LLM providers, tools, storage и инфраструктурных компонентов.

## 2. Архитектурные ограничения и исходные решения

Сохраняются ранее принятые проектные решения:
- локальный On-prem MVP на Docker Compose; Kubernetes не входит в MVP;
- Modular Backend + отдельно запускаемые Manager Runtime и Worker Runtime;
- общий пул Worker Runtime, девять специализаций — логические capability, не девять обязательных сервисов;
- Temporal — durable Workflow Engine; LangGraph — внутреннее исполнение агентного графа;
- PostgreSQL: `ai_res_db` и `temporal_db` как отдельные базы; LangGraph checkpoint storage логически отделён;
- MinIO — объектное хранилище источников и артефактов;
- Redis optional, не источник истины и не обязательная зависимость;
- LLM Gateway — контролируемый путь к model providers;
- observability — OTel, Prometheus, Grafana, Loki, Tempo; Langfuse optional;
- backup/restore: pgBackRest + WAL archiving для PostgreSQL, отдельное резервирование MinIO;
- исходные целевые RPO ≤ 1 часа и RTO ≤ 4 часов сохраняются как цели из Infrastructure v1.4, а не подтверждённые гарантии.

Этап 15 не утверждает новые численные capacity/SLO без нагрузочных измерений.

## 3. Модель нагрузки AI RES

Нагрузка неоднородна и не должна измеряться только HTTP requests/sec. Учитывать:
1. Interactive UX/API: открытие Workspace, чтение требований/артефактов, поиск, фильтры, комментарии и approvals.
2. Manager planning: анализ Epic, декомпозиция, создание Plan Versions и выбор Workers.
3. Worker execution: число активных Worker Runs, типы задач, длительность, tool/LLM calls, retries.
4. Context ingestion: загрузка, извлечение, OCR, chunking, indexing, обновление источников.
5. Artifact generation: Markdown/DOCX/PDF/OpenAPI/diagram source and rendering.
6. Traceability & impact: graph traversal, dependency analysis, change assessment.
7. Evaluation/QA: independent review, regression suites, batch evaluation.
8. Observability: telemetry ingestion, query, retention, cardinality.
9. Recovery/backup: backup windows, WAL, MinIO object copies, restore and reconciliation.

Для каждой категории фиксируются arrival rate, concurrency, payload size, CPU/memory profile, I/O, external dependency and priority.

## 4. Производительность: пользовательские и фоновые классы

Разделять интерактивные запросы и длительные агентные процессы:
- API не ожидает завершения долгого Worker Run; возвращает подтверждение/ID и состояние.
- Длительные операции выполняются асинхронно через Temporal.
- UI получает состояние через подходящий механизм обновления (polling/SSE/WebSocket — выбрать в API/UX implementation design; не создавать несколько конкурирующих механизмов).
- Фоновые batch tasks не должны исчерпывать ресурсы, необходимые интерактивному API и control plane.
- При перегрузке система предпочитает контролируемое ожидание/отказ с понятным статусом, а не бесконтрольный рост очередей.

Для интерактивных API устанавливаются latency objectives отдельно по классам (read, write, search, upload initiation, approval). Для agent workflows задаются time-to-start, execution duration distributions, queue wait, completion and quality objectives. LLM/provider latency учитывается отдельно от внутренней задержки AI RES.

## 5. Resource isolation и concurrency control

### 5.1. Пулы и лимиты
- API, Manager Runtime, Worker Runtime, Temporal, PostgreSQL, MinIO и observability имеют отдельные resource requests/limits на уровне deployment configuration.
- Worker Runtime concurrency ограничивается глобально и по capability/task class.
- Вводятся budgets: active runs, LLM concurrency, tool concurrency, tokens/cost, wall-clock time, retries, context size and artifact size.
- Manager не может обойти platform limits; Temporal/dispatch layer enforce concurrency and queue policy.
- High-cost/long-running tasks могут иметь отдельные очереди/лимиты после измерений, но стартовая модель — `ai-res-manager` и `ai-res-workers`.
- Очереди не должны создавать starvation для интерактивно важных задач; предусмотреть приоритеты и aging/anti-starvation policy.

### 5.2. Backpressure
- При достижении лимитов новые задания остаются в контролируемой очереди или отклоняются с retryable status.
- Ограничить максимальную длину очереди, время ожидания и число одновременных запусков.
- Не принимать неограниченный объём загрузок/извлечения/LLM jobs.
- При деградации provider/tool применять circuit breaker или эквивалентный механизм на gateway/adapter boundary.
- Backpressure должен быть виден в UI и telemetry: queued, throttled, deferred, rejected, reason.

### 5.3. Fairness
- Ограничивать потребление ресурсов одним проектом/пользователем/задачей.
- Ввести квоты и лимиты на organization/project scope; точные значения настраиваются после workload sizing.
- Не допускать, чтобы один Epic или массовый ingestion блокировал весь Worker pool.

## 6. Масштабирование по компонентам

| Компонент | Первичная стратегия | Условия масштабирования / ограничения |
|---|---|---|
| Frontend | Stateless web replicas при необходимости | CDN не предполагается для локального On-prem; UI не хранит бизнес-состояние |
| API | Stateless horizontal replicas за reverse proxy | Session/auth state server-side; idempotency и shared domain DB |
| Manager Runtime | Отдельные экземпляры/ограниченная concurrency | Планирование и orchestration; защищать от параллельного конфликта на одном Epic |
| Worker Runtime | Shared pool, horizontal replicas позже | Основной scale-out axis; capability-aware concurrency |
| Temporal | Сначала self-hosted topology, масштабировать по официальным deployment guidance | Worker pollers, task queues, persistence capacity; не масштабировать только количеством контейнеров |
| PostgreSQL | Сначала vertical sizing, индексы, connection pooling и query tuning | Read replicas/partitioning/HA — после измерений; Temporal DB отдельно |
| MinIO | Сначала capacity/IO sizing для single-node MVP | Distributed/object storage topology — отдельное production design |
| LLM Gateway | Stateless gateway replicas при необходимости | Provider quotas, connection pools, circuit breaker, fallback policy |
| OTel Collector | Agent/sidecar or central gateway pattern | Queue/batch sizing, backpressure, no app blocking |
| Prometheus/Loki/Tempo | Retention, compaction, storage sizing | Separate storage/cluster only when metrics justify |
| Redis | Optional cache/rate limiting | Не переносить туда canonical state/workflow |

Horizontal scaling of stateless services must not imply that stateful components can be replicated without their own consistency/HA design.

## 7. Data and database performance

- Все DB access paths имеют измеримые query latency, rows scanned, locks, connection pool saturation and slow-query visibility.
- Индексы создаются под реальные query patterns; избегать чрезмерной индексации write-heavy tables.
- Pagination обязательна для крупных списков; cursor/keyset pagination предпочтительна для больших/изменяющихся выборок.
- Запрещать неограниченную загрузку больших списков и N+1 запросы в hot paths.
- Connection pools ограничиваются с учётом общего числа API/Manager/Worker/Temporal connections и PostgreSQL `max_connections`.
- Длительные операции (bulk import, reindex, impact analysis, export, evaluation) выполняются асинхронно и пакетно.
- Большие документы/контексты не передаются через Temporal history; использовать object references and immutable version IDs.
- Large artifact generation и file parsing выполняются streaming/chunked, где поддерживается.
- Retention/partitioning/archival для audit/telemetry/event tables проектируется по фактическому объёму и требованиям хранения.

## 8. LLM и tool efficiency

- Model selection учитывает задачу, качество, privacy/locality, latency, token/cost budget and availability.
- Контекст формируется по принципу minimum sufficient context; не отправлять повторно полный проект на каждый Worker Run.
- Использовать caching только для данных, где определены key, version, ACL scope, invalidation and TTL; cache не является источником истины.
- Повторный LLM/tool call допустим только с error classification, bounded attempts, timeout, idempotency where needed and budget.
- Provider fallback — только заранее разрешённый профиль; смена модели/provider фиксируется и может требовать quality guardrails.
- Batch API/provider features допускаются как оптимизация после проверки задержки и privacy constraints.
- Не оптимизировать token count ценой потери provenance, обязательных требований, QA или безопасности.

## 9. Resilience patterns

Применять там, где соответствует характеру операции:
- bounded retries with exponential backoff and jitter для transient failures;
- timeout budgets и cancellation propagation;
- circuit breaker для деградирующих внешних providers/connectors;
- bulkheads/resource isolation для независимых пулов;
- idempotency keys и deduplication для повторяемых команд;
- outbox/inbox или эквивалентный transactional event publishing для согласования domain state/events;
- checkpointing для длительных workflow;
- compensation/reconciliation для операций, где exactly-once недостижимо;
- graceful degradation: отключение необязательной аналитики/telemetry enrichment без отказа core workflow;
- fail-closed для security/policy/audit-critical operations.

Exactly-once execution для внешних API не обещается. Используются at-least-once delivery, idempotency and reconciliation.

## 10. Failure domains и поведение при отказах

| Отказ | Ожидаемое поведение |
|---|---|
| LLM provider недоступен | Bounded retry; разрешённый fallback или очередь ожидания; не обходить privacy/model policy |
| Tool/connector недоступен | Retryable/blocked state; альтернативный инструмент только по policy; side-effect reconciliation |
| Worker Runtime потерян | Temporal task остаётся durable; запуск на другом poller после восстановления/timeout; проверить идемпотентность |
| Manager Runtime потерян | Workflow остаётся durable; Manager task повторяется безопасно; domain state не теряется |
| Temporal недоступен | Новые долгие работы не запускаются/не подтверждаются как начатые; API показывает degraded status; не эмулировать workflow в памяти |
| PostgreSQL AI RES недоступен | Защищённые доменные операции fail closed; не принимать изменения без persistence |
| Temporal DB недоступна | Workflow execution pauses/fails safely; восстановить Temporal persistence по процедуре |
| MinIO недоступен | Операции, требующие source/artifact bytes, блокируются; метаданные не должны ссылаться на неподтверждённую запись |
| OTel/Prometheus/Loki/Tempo недоступны | Telemetry fail-open, bounded buffers/drop metrics; audit сохраняется отдельно |
| Langfuse недоступен | Core workflow continues; optional integration disabled |
| Redis недоступен | Core functionality continues; cache/rate limiting degrade to safe fallback |
| Disk full | Backpressure; приоритет защитить PostgreSQL/MinIO/audit; не удалять canonical data |
| Один Worker pool saturated | Queue/backpressure; не истощать API/Manager control plane |
| Частичный сбой deployment | Health-based readiness; не направлять трафик в неполностью готовый экземпляр |

## 11. Consistency, idempotency и side effects

- Каждая mutating Activity определяет idempotency strategy.
- Повторная доставка Task/Activity не создаёт дублирующие Requirements, Artifacts, Reviews или external side effects.
- Перед external write connector использует idempotency key, external stable ID или reconciliation protocol.
- Domain state transition и событие должны публиковаться согласованно (transactional outbox или эквивалент).
- Workflow retries не должны повторно выполнять уже подтверждённые необратимые действия.
- При неопределённом результате внешней операции состояние `OUTCOME_UNKNOWN`/эквивалент требует reconciliation, а не слепого повтора.
- Все recovery действия аудируются.

## 12. Recovery, HA и disaster recovery

Сохраняются текущие target RPO ≤ 1h и RTO ≤ 4h из Infrastructure v1.4 как проектные цели. Для production On-prem необходимо:
- независимое backup storage для PostgreSQL и MinIO;
- шифрование backup и контроль доступа;
- регулярные restore drills;
- Recovery Manifest с версиями DB backup/PITR, MinIO snapshot, configs/rules/secrets references, release manifest и unfinished workflows;
- reconciliation domain DB ↔ Temporal ↔ MinIO ↔ external side effects;
- документированные процедуры failover, restore, reprocessing and operator escalation.

Высокая доступность (HA) не тождественна backup/DR. Single-node Docker Compose MVP не обеспечивает автоматическую отказоустойчивость узла. Production HA topology — отдельное deployment profile/design с redundant compute, DB/object storage, network and failure-domain analysis.

## 13. SLO/SLI и capacity objectives

Не фиксировать абсолютные численные targets без baseline. Для каждого critical user journey определить:
- SLI definition and measurement source;
- target percentile/window;
- error budget;
- exclusions and dependency attribution;
- owner and alert;
- degraded mode and recovery objective.

Минимальные journey:
1. Open Project Workspace.
2. Read/search requirements and artifacts.
3. Save analyst change / approve decision.
4. Upload and ingest source.
5. Start Manager plan and receive first progress state.
6. Start Worker Run and receive first result.
7. Complete independent QA.
8. Generate/export artifact.
9. Execute change impact assessment.
10. Recover workflow after process restart.

Для async workflows задавать distribution objectives (p50/p95/p99 time-to-start and duration) отдельно по task class; длительность LLM provider не смешивать с internal queue wait.

## 14. Capacity model

До production sizing собрать:
- concurrent active users;
- active projects/Epics per organization;
- tasks created/day and peak burst;
- concurrent Worker Runs by capability;
- LLM calls/run, input/output tokens, provider concurrency;
- ingestion volume/day, file count/size/type, OCR rate;
- artifacts generated/day and export sizes;
- traceability graph nodes/edges and query patterns;
- DB rows/GB growth, MinIO GB growth;
- telemetry GB/day and retention;
- backup throughput/window and restore throughput.

Capacity model должна оценивать CPU, RAM, DB connections/IOPS, object storage throughput/capacity, Temporal persistence, network, provider quotas, token cost and telemetry storage. Сначала измерить реальный MVP, затем рассчитывать headroom.

## 15. Открытые решения

- Численные API SLO и workflow duration objectives.
- Baseline workload profile and supported scale envelope.
- Максимальные concurrency/budgets per organization/project/capability.
- Механизм API push updates: polling vs SSE vs WebSocket.
- Connection pooler (например, PgBouncer) и его deployment profile.
- Production HA topology for PostgreSQL/Temporal/MinIO.
- Queue priority and fairness parameters.
- Exact circuit-breaker thresholds and retry budgets.
- Data/telemetry retention, storage growth and partitioning thresholds.
- Provider fallback matrix and model quality constraints.
- Production backup location, encryption and tested restore throughput.

## 16. Критерии архитектурной готовности

1. Нагрузка классифицирована по interactive, orchestration, agent, ingestion, evaluation and operations.
2. API и долгие agent jobs разделены.
3. Worker concurrency, provider/tool budgets and queue backpressure defined.
4. Нет single Worker Run, способного исчерпать весь shared pool без лимитов.
5. Повторные Activities и external side effects идемпотентны или имеют reconciliation.
6. Состояние workflow переживает рестарт Runtime.
7. Отказ optional Redis/Langfuse/telemetry не нарушает core workflow.
8. DB/object store/Temporal failure modes имеют явное поведение.
9. RPO/RTO цели связаны с Recovery Manifest и проверяемыми drills.
10. Есть workload model, load test plan and capacity baseline.
11. SLO targets не выдуманы: они определяются после baseline и stakeholder agreement.
12. HA и DR не смешиваются; ограничения single-node MVP явно раскрыты.

## 17. Связанные документы

- `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md`
- `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md`
- `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md`
- `AI_RES_Infrastructure_Deployment_Operations_v1.5.md`
- `AI_RES_Observability_Architecture_v1.0.md`
- `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md`
- `AI_RES_MVP_Capability_Matrix_v3.0.md`
- `AI_RES_Document_Registry_v1.4.md`
