# Runbook — Observability stack и мониторинг (S13)

Статус: ненормативный; опирается на DOC-024 §3–§9, DOC-025 (OBS-MON/SEC/ALR), DOC-015 §10. Все числа (окна `for`, пороги, retention, sizing, получатели алертов) — WORKING или открыты (OD-02): не утверждены.

## Что это и чем не является
`API / Manager / Worker / dispatcher → OTLP → OTel Collector (redaction) → Prometheus (scrape) / Loki / Tempo → Grafana`; алерты: правила Prometheus → Alertmanager (один путь). Telemetry — диагностическая проекция: она **не источник истины** и **не Audit Log**. Audit пишется доменными сервисами в PostgreSQL независимо от Collector; потеря telemetry не останавливает домен (fail-open), отказ обязательной audit-записи останавливает защищённое действие (fail-closed).

## Доступ
Grafana доступна только в сети `admin` (порта на хосте нет, как и у Temporal UI). Вход: пользователь `admin`, пароль — Compose secret `grafana_admin_password` (`infra/secrets/runtime/`, случайный на машине; в Git не попадает). Локально: `docker compose -p ai-res -f infra/compose.yaml -f infra/compose.dev.yaml exec grafana …` или временный `docker run --network ai-res_admin` с port-forward — публикация порта требует решения владельца. Prometheus/Loki/Tempo/Alertmanager — только в сети `observability`, без человеческого входа (запросы — через Grafana или `docker compose exec`).

## Что собирается
| Сигнал | Источник | Куда |
|---|---|---|
| Трейсы | `TelemetryMiddleware` (api, platform-api), `TracingInterceptor` Temporal (dispatcher, manager, worker), `traceparent` в вызовах Platform API | Tempo |
| Метрики | HTTP `http.server.request.duration`, пул БД `db.client.connection.*`, outbox/inbox `ai_res.*`, ядро Temporal SDK `temporal_*`, серверные метрики Temporal и MinIO (scrape), собственные метрики компонентов | Prometheus |
| Логи | JSON-логи `ai_res`/`uvicorn.error` (дважды редактируются: в процессе и в Collector) | Loki |

**Не собирается (и почему):** полные prompts/ответы, документы, код, секреты, тела запросов, тексты исключений и stack trace (остаётся только тип). Высококардинальные идентификаторы (`project_id`, `task_id`, `worker_run_id`, `trace_id` …) — только в traces/logs, **не в labels Prometheus**: allowlist меток в `infra/observability/otel/config.yaml` (`transform/metrics`) + линтер в тестах.

## Деградация (OBS-MON-014/015)
Недоступен Collector/Loki/Tempo/Prometheus → API и Workflow работают как обычно; данные отбрасываются после ограниченной очереди и ограниченных повторов (очередь SDK `otlp_queue_size`, очередь и retry Collector — WORKING). Потеря измерима: `ai_res_telemetry_export_failures_total` (приложение → Collector), `otelcol_exporter_send_failed_*` (Collector → бэкенд). Раз в минуту процесс пишет одну строку `telemetry export failing` в stderr.

## Доказательства (как воспроизвести)
`make infra-test` (статика: конфиги, алерты, promtool, линтеры), `make infra-test-runtime` (на живом стеке: redaction до Loki/Tempo, остановка backend'ов не ломает API, audit не зависит от telemetry), `cd backend && uv run pytest tests/unit/test_telemetry_export.py`.

## Алерты
Каждый алерт содержит severity, scope, owner, `for`, runbook, user_impact, auto_action (всегда `none`), silence_policy. Alertmanager **не имеет получателей**: назначение получателей/дежурных — решение владельца (OD-02, OBS-ALR-006); до него алерты видны в Alertmanager и на дашборде Platform Overview. Числовые пороги **не заданы**: алерты по порогам инертны, пока владелец не запишет значение в `infra/observability/prometheus/rules/thresholds.yml` (имена — в комментарии файла).

### TargetDown
Факт: Prometheus не может снять метрики с job. Причину алерт не определяет. Шаги: `docker compose ps`, логи сервиса, сеть `observability`. Для `otel-collector` проверить `otelcol_*` и порт 8888/8889.

### ApiServerErrorRatioHigh
Факт: доля 5xx выше порога (порог не задан по умолчанию — OD-02). Шаги: дашборд API (классы статусов, самые медленные маршруты), логи Loki по `service_name`, трассы с ошибкой в Tempo.

### ApiLatencyP95High
Факт: p95 длительности запроса выше порога. Проверить число запросов (малая выборка — не измерение), затем маршруты и пул БД.

### DatabasePoolSaturated
Факт: заняты все соединения пула с учётом `max_overflow` в течение окна. Шаги: дашборд PostgreSQL (состояния пула), долгие транзакции (`idle_in_transaction_session_timeout` и `statement_timeout` уже заданы), ошибки БД. Серверные метрики PostgreSQL недоступны без monitoring-роли (NCP-15, G-125).

### DatabaseErrors
Факт: приложение получило ошибки БД класса `error_type`. Шаги: логи (тип исключения без текста), состояние PostgreSQL, миграции. Не включать SQL/параметры в тикеты.

### ObjectStorageLowFreeSpace
Факт: доля свободного места MinIO ниже порога (не задан по умолчанию). Данные автоматически не удаляются (ADR-030): решение об освобождении места принимает владелец.

### TelemetryExportFailing
Факт: процесс не может экспортировать сигнал в Collector, данные отброшены. Пользовательского влияния нет; домен и Audit Log не затронуты. Шаги: состояние `otel-collector`, сеть, лимиты памяти.

### CollectorBackendExportFailing
Факт: Collector не доставляет данные в Loki/Tempo. Шаги: здоровье бэкенда (`up`), место на томе, лимиты Loki (`ingestion_rate_mb`, WORKING).

### CollectorQueueNearFull
Факт: очередь экспортёра Collector заполнена не меньше порога `collector_queue_fill_ratio` (не задан, OD-02) в течение окна; следующие данные будут отброшены. Шаги: как выше + нагрузка на бэкенд.

### ApplicationTelemetryMissing
Факт: от job приложения (api, platform-api, outbox-dispatcher, manager-runtime, worker-runtime) 10 минут нет метрик в Prometheus. Алерт не различает «процесс остановлен» и «экспорт сломан». Шаги: `docker compose ps`, логи сервиса, `TelemetryExportFailing`, состояние `otel-collector`. Пока процесс не работает, алерты по его метрикам (outbox, inbox) сами исчезают через `metric_expiration` (5 мин) — этот алерт закрывает именно такой случай.

## Retention
Сроки хранения **не заданы проектом** (OD-02, DOC-024 §8). Применяются умолчания компонентов, не решения AI RES: Prometheus — 15 дней, Tempo — `block_retention` по умолчанию, Loki — удаление выключено. Prometheus и Tempo удаляют данные по этим умолчаниям автоматически (это не решение AI RES); Loki не удаляет ничего. Явные сроки по классам данных — решение владельца (OD-02, OBS-SEC-007). Тома: `prometheus_data`, `loki_data`, `tempo_data`, `grafana_data`, `alertmanager_data` (удаляются только `make reset CONFIRM=yes`).

## Известные ограничения
См. `docs/implementation/KNOWN_GAPS.md` (G-123…): TLS внутри сети `observability`, контекст трассы не передаётся через Outbox (API → dispatcher разрываются на два trace), нет метрик хоста/диска (node-exporter требует монтирования хоста), дашборды Manager&Workers / LLM&Tools / Product Quality ждут компонентов S15+/S23+.
