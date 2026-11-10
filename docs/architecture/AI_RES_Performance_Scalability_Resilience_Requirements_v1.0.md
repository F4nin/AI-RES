# AI RES — Требования к производительности и масштабированию

**Версия:** 1.0 | **Статус:** WORKING | **Этап:** 15

## 1. Общие положения

Требования задают измеримые свойства производительности и масштабирования. Численные SLO/capacity limits являются OPEN до baseline и согласования; их нельзя подменять произвольными значениями.

### PERF-001 — Классификация нагрузки
Система MUST измерять нагрузку отдельно для интерактивных API, Manager planning, Worker execution, ingestion, artifact generation, traceability/impact, evaluation/QA и observability.

### PERF-002 — Разделение API и длительных задач
API MUST завершать запрос на постановку длительной работы подтверждением принятия/отклонения и идентификатором операции, не ожидая завершения Worker Run.

### PERF-003 — Изоляция control plane
Worker execution, ingestion и evaluation MUST иметь ограничения ресурсов и concurrency, не позволяющие исчерпать ресурсы API/Manager control plane.

### PERF-004 — Worker concurrency
Platform MUST enforce глобальные и capability/task-class concurrency limits для общего Worker Runtime pool. Manager не может повышать лимиты.

### PERF-005 — Queue backpressure
При достижении capacity limits система MUST ограничивать admission, ставить работу в ограниченную очередь либо отклонять её с явным retryable/non-retryable reason. Неограниченный рост очереди запрещён.

### PERF-006 — Fairness
Система MUST поддерживать настраиваемые quotas/limits на organization/project/task scope и защищать shared pool от monopolization одним проектом.

### PERF-007 — Приоритеты и starvation
Workflow dispatch MUST поддерживать определяемую политикой приоритизацию и механизм предотвращения starvation. Конкретные priority classes/aging thresholds OPEN до workload analysis.

### PERF-008 — Resource budgets
Для Worker Run MUST применяться лимиты wall-clock duration, attempts, LLM tokens/cost, tool calls/concurrency, context size и output size. Превышение приводит к контролируемому завершению/эскалации.

### PERF-009 — API performance telemetry
Для API MUST собираться latency distributions, throughput, error rate, saturation, DB dependency latency и request class. Высококардинальные идентификаторы не должны быть metric labels.

### PERF-010 — Workflow performance telemetry
Для workflow MUST измеряться queue wait, schedule-to-start, execution duration, retries, timeout, blocked/waiting time, completion and cancellation по task class/capability.

### PERF-011 — Database efficiency
DB hot paths MUST иметь bounded pagination, query plans/slow-query visibility, connection pool limits, indexes based on measured access patterns and protection against N+1/unbounded queries.

### PERF-012 — Connection budget
Суммарные connections API, Manager, Worker, Temporal and maintenance jobs MUST be budgeted against PostgreSQL capacity. При необходимости используется connection pooler после отдельного compatibility review.

### PERF-013 — Async bulk processing
Bulk ingestion, reindexing, export, artifact rendering, impact analysis and batch evaluation MUST execute asynchronously and in bounded batches.

### PERF-014 — Object/document processing
Large files and artifacts MUST be processed with bounded memory and size limits; streaming/chunking is preferred where supported.

### PERF-015 — Context efficiency
Context Builder MUST use minimum sufficient context and versioned references; full project/document payload MUST NOT be repeatedly copied into Temporal history or unrelated Worker contexts.

### PERF-016 — LLM efficiency
LLM calls MUST be bounded by provider/model/task-class budgets, timeout and concurrency limits. Model/provider fallback must follow approved policy and be observable.

### PERF-017 — Cache correctness
Any cache MUST define key scope, tenant/project ACL isolation, source/version invalidation and TTL. Cache MUST NOT become canonical domain or workflow state.

### PERF-018 — Capacity envelope
Before production release, supported workload envelope MUST be documented from measured baseline: active users, projects, task rates, concurrent Worker Runs, ingestion, storage growth, provider limits and telemetry volume.

### PERF-019 — SLO definitions
Each critical user journey MUST have SLI definition, measurement source, target, window, owner, alert and error budget. Targets require baseline and stakeholder approval.

### PERF-020 — Percentile reporting
Latency MUST be reported using distributions/percentiles (at minimum p50/p95/p99 where sample size permits), not averages alone. Async workflows are segmented by task class.

### PERF-021 — Capacity headroom
Production sizing MUST include documented headroom for peak load, maintenance, retries and partial dependency degradation. Exact headroom percentage OPEN pending measurements.

### PERF-022 — Scale-out compatibility
Stateless API/Manager/Worker services SHOULD support horizontal replicas without relying on local process memory for durable business/workflow state.

### PERF-023 — State consistency
Scaling MUST preserve idempotency, domain invariants, ACL and event consistency. Concurrent updates to one Epic/Plan/Task MUST use explicit optimistic concurrency/locking/version checks.

### PERF-024 — Resource saturation behavior
At CPU, memory, disk, DB connection, queue or provider saturation, system MUST expose degraded state and apply backpressure rather than uncontrolled retry amplification.

### PERF-025 — Load test coverage
Release validation MUST include baseline, load, stress, spike, soak and capacity-limit tests for critical user journeys and asynchronous workloads.

### PERF-026 — No invented SLO
No absolute latency, throughput, concurrency or storage target may be marked approved without benchmark evidence and explicit product/operations approval.

## 2. Открытые параметры
- API latency targets by request class.
- Throughput and concurrency envelope.
- Maximum active Worker Runs by capability and organization.
- Queue capacity/priority/aging.
- Token and cost budgets.
- File size, ingestion throughput and artifact size limits.
- DB connection pool sizing and query budgets.
- Storage/telemetry growth and retention.
- Headroom factor and production node sizing.

## 3. Acceptance criteria
- Load classes and metrics are implemented and visible.
- Limits/backpressure/fairness are testable.
- API remains responsive during long Worker runs and ingestion.
- DB connections and memory remain bounded under peak workload.
- No unbounded retry/queue growth.
- SLOs are approved only after baseline measurements.
