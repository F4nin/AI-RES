# AI RES — План нагрузочного тестирования и capacity assessment

**Версия:** 1.0 | **Статус:** WORKING | **Этап:** 15

## 1. Цель

Определить фактическую производительность и capacity envelope AI RES, найти bottlenecks и подтвердить корректность backpressure, concurrency limits, isolation and recovery under load. План предназначен для исполнения после появления интеграционного стенда и representative data.

## 2. Правила тестирования

- Тестировать версии приложения, инфраструктуры, моделей, prompts, tools и схем БД, фиксируя manifest.
- Использовать синтетические/обезличенные данные, не production secrets или персональные данные.
- Разделять внутреннюю задержку AI RES, Temporal queue wait, LLM provider latency и external tool latency.
- Проверять качество результата наряду с latency/cost: быстрый, но неправильный результат не считается успехом.
- Повторять тесты и фиксировать вариативность; не выводить capacity из одного прогона.
- Указывать hardware, Docker limits, DB settings, provider quota, network and dataset profile.
- Изменения конфигурации между прогонами версионировать.

## 3. Workload profiles

Пока точные величины не определены, использовать параметризуемые профили, а не выдуманные фиксированные числа.

| Профиль | Характер нагрузки | Основные риски |
|---|---|---|
| Interactive baseline | Одновременная работа аналитиков в Workspace, чтение, поиск, комментарии, approvals | API latency, DB connections |
| Planning | Manager анализирует Epic и строит Plan | Manager saturation, LLM cost/latency |
| Worker steady state | Постоянный поток задач разных capability | Queue wait, worker concurrency |
| Worker burst | Короткий всплеск новых Tasks/Worker Runs | Queue growth, provider limits |
| Ingestion | Массовая загрузка PDF/DOCX/XLSX/CSV/Markdown | CPU/RAM, object storage, DB writes |
| Artifact generation | Параллельная генерация Markdown/DOCX/PDF/OpenAPI/diagrams | Memory, rendering, IO |
| Impact analysis | Изменение источника/требования с анализом зависимостей | DB query plans, graph traversal |
| QA/Evaluation | Независимые Reviews и regression batch | Worker pool contention, token cost |
| Mixed realistic | Смешение интерактивных и фоновых сценариев | Cross-component contention |
| Degraded dependency | Provider/Tool/Storage/Temporal degradation | Retry storm, backlog, graceful degradation |

## 4. Обязательные типы тестов

1. **Baseline:** минимальная и типичная нагрузка, фиксация нормального профиля.
2. **Load:** постепенное увеличение до ожидаемого рабочего профиля.
3. **Stress:** превышение ожидаемого профиля до контролируемого saturation point.
4. **Spike:** резкий всплеск и наблюдение queue/backpressure/recovery.
5. **Soak:** длительная нагрузка для выявления memory leaks, queue accumulation, connection leaks and storage growth.
6. **Capacity:** поиск максимальной устойчивой нагрузки при заданных quality/reliability guardrails.
7. **Resilience under load:** отключение/замедление зависимостей при продолжающейся нагрузке.
8. **Recovery:** восстановление после отказа, измерение backlog drain and consistency.

## 5. Representative end-to-end сценарии

### LT-01 — Interactive workspace
Пользователи параллельно открывают проекты, Epic, требования, артефакты, выполняют поиск/фильтрацию и сохраняют комментарии. Измерять API p50/p95/p99, errors, DB latency, connection pool saturation.

### LT-02 — Plan creation
Несколько Epic одновременно запускают Manager planning, создают Plan Versions и задачи. Измерять time-to-first-status, Manager concurrency, LLM calls/tokens/cost, DB writes, plan completion and quality.

### LT-03 — Worker pool mixed capabilities
Одновременно выполняются задачи Elicitation, Research, Business Analysis, Requirements, System Analysis, API & Integration, Modeling, QA and Traceability. Измерять queue wait, schedule-to-start, run duration, resource use, completion/quality, capability fairness.

### LT-04 — Ingestion burst
Пакетно загружаются файлы разного размера и формата; extraction/indexing запускаются асинхронно. Измерять throughput, memory peak, CPU, MinIO I/O, DB writes, failures and user-visible status.

### LT-05 — Artifact generation/export
Параллельно генерируются и экспортируются документы, OpenAPI specs и diagrams. Измерять memory, render duration, file sizes, object store throughput, errors and validation outcome.

### LT-06 — Change impact
Обновляются источники и требования с различной степенью связности. Измерять query count, rows scanned, traversal duration, impact completeness and false-negative review.

### LT-07 — QA and evaluation batch
Запускаются independent QA and regression evaluations. Проверить, что batch не лишает API и Manager ресурсов.

### LT-08 — Provider degradation
LLM provider latency/error/rate limits искусственно повышаются. Проверить timeout, circuit breaker, bounded retries, approved fallback, queue status, token budget and no policy bypass.

### LT-09 — Worker restart
Worker Runtime принудительно завершается во время Run. Проверить Temporal recovery, duplicate Activity delivery, idempotency, result submission and domain consistency.

### LT-10 — Temporal outage/restart
Остановить Temporal service/persistence в тестовом окружении. Проверить, что API не заявляет о durable start при недоступности, workflow state is recovered and reconciliation succeeds.

### LT-11 — PostgreSQL/MinIO pressure
Имитировать DB connection exhaustion, slow queries, object storage latency and disk pressure. Проверить backpressure, safe failure, audit integrity and no dangling object refs.

### LT-12 — Mixed peak + optional component outage
Смешанная нагрузка при отключённом Redis, Langfuse или telemetry backend. Проверить core workflow continuity and observability gap reporting.

## 6. Метрики и артефакты каждого прогона

- Request throughput and latency percentiles by endpoint/class.
- API error rate and saturation.
- CPU, RAM, disk IO, network, container restarts.
- PostgreSQL connections, query latency, locks, cache hit, slow queries.
- Temporal task queue backlog, schedule-to-start, Activity retries/timeouts, workflow completion.
- Worker concurrency, capability distribution, queue fairness, run outcomes.
- LLM provider latency, rate limits, token usage, cost, fallback.
- Tool call latency/error/permission denial and side-effect reconciliation.
- MinIO throughput, latency, object count, storage growth.
- Telemetry ingestion/drop rate and backend resource use.
- Quality/QA outcomes, rework, evidence/provenance coverage.
- Actual recovery duration, data loss window and reconciliation result.

Каждый отчёт включает test run ID, build/release manifest, hardware, configuration, dataset/workload profile, graphs, bottleneck analysis, pass/fail, open issues and recommended capacity.

## 7. Exit criteria

Тестовый профиль считается пройденным, если:
- agreed SLOs выполнены на согласованном workload;
- error rate and quality guardrails не нарушены;
- очереди и retries остаются bounded;
- API/control plane сохраняют доступность при фоновой нагрузке;
- resource use не показывает неконтролируемого роста;
- backpressure/fairness работают согласно политике;
- recovery не создаёт duplicate side effects или inconsistent domain state;
- quality не деградирует из-за model fallback или resource pressure;
- наблюдаемость достаточна для локализации bottleneck.

Численные thresholds должны быть заполнены после baseline и согласования. До этого test report может быть exploratory, но не production capacity certification.

## 8. Итоговые результаты

- Baseline performance report.
- Capacity envelope and limiting component.
- Resource sizing recommendation for Compose MVP.
- Concurrency and queue policy values.
- DB/index/query tuning backlog.
- LLM/provider budgets and fallback evidence.
- Resilience and recovery test report.
- Production On-prem scaling/HA decision inputs.
