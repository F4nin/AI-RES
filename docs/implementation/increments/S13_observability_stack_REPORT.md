# S13 — Observability stack и мониторинг: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S13_observability_stack.md` · **Итоговый статус:** VERIFIED (Linux CI зелёный (PR #16: ci 43301634548/43301768127, contracts 43301634628/43301768417 — backend, infra-runtime, infra-static, contracts success)).

## 1. Что реализовано
- Конвейер `процессы → OTLP → Collector (redaction, allowlist) → Prometheus / Loki / Tempo → Grafana`; Alertmanager — единственный путь алертов, без получателей (OD-02).
- Экспорт из процессов (API, Platform API, dispatcher, Manager/Worker Runtime): fail-open, ограниченные очереди, счётчик потерь, санитизация логов до экспорта.
- Трассировка Temporal (`TracingInterceptor`), метрики ядра SDK, `traceparent` в вызовах Platform API; метрики пула БД; метрика длительности HTTP.
- 7 дашбордов (Platform, API, Outbox/Events, Temporal, Manager & Workers, PostgreSQL application view, Telemetry Pipeline); 16 алертов как код с полным набором метаданных; числовые пороги отсутствуют (серии `ai_res:threshold:*` пусты — алерты по порогам инертны); promtool-тесты.
- Runbook `docs/runbooks/observability.md`.
- Не сделано: сквозной trace через Outbox (G-126), серверные метрики PostgreSQL (NCP-15), метрики хоста (G-127), дашборды LLM/Quality (G-128), TLS/auth внутренних путей (G-123), разграничение доступа в Grafana (G-130), ретенция и получатели (OD-02).

## 2. Нормативная база и проверка Registry
Registry v4.1 §2; DOC-024 (Observability Architecture v1.2), DOC-025 (Monitoring & Alerting Requirements, WORKING), DOC-015 §10. Файлы на месте. Замечание: ярлыки «S13» у старых gaps (G-53, G-60, G-61, G-107, G-117, G-121) относятся к прежнему «Increment 13» (Gate/переходы), а не к этому этапу. DOC-025 цитирует устаревшие версии Observability v1.0 / Infrastructure v1.4 — расхождение для владельца.

## 3. Созданные и изменённые файлы
Новые: `infra/observability/**` (otel, prometheus + rules + tests, alertmanager, loki, tempo, grafana + generate_dashboards.py и 7 dashboards), `backend/src/ai_res/platform/export.py`, `backend/src/ai_res/db/metrics.py`, `backend/tests/unit/test_telemetry_export.py`, `infra/tests/test_observability_static.py`, `infra/tests/runtime/test_observability.py`, `docs/runbooks/observability.md`, `reviews/S13_REVIEWS.md`.
Изменены: `infra/compose.yaml`, `check_compose.py`, `secrets_dev.py`, `wait_stack.py`, `scan_secrets.py`, тесты infra; `backend` — `api/{app,identity,internal_api,serve_internal}.py`, `cli/dispatcher.py`, `db/engine.py`, `orchestration/{client,http_platform}.py`, `platform/{config,telemetry}.py`, `runtime/{lifecycle,manager,worker}.py`, `pyproject.toml`, `uv.lock`; документы реализации. Удалён `infra/config/otel/config.yaml` (перенесён).

## 4. Изменения API / контрактов / событий
Публичный OAS и AsyncAPI не менялись. Внутренний Platform API принимает `traceparent`. Контракт событий не менялся (контекст трассы через Outbox не передаётся — G-126).

## 5. Миграции и совместимость
Миграций нет. Compose: новая сеть `observability` (internal), 6 сервисов, 5 томов, секрет `grafana_admin_password`; Temporal и MinIO подключены к `observability`. Образы закреплены digest'ами.

## 6. Решения
ADR-095…099 (стек и redaction; алерты без значений; fail-open экспорт; Temporal; PostgreSQL application view). WORKING (не утверждены): окна `for`, размеры очередей, таймауты, label_limit/sample_limit, owner `platform-operations`.

## 7. NCP / расхождения
NCP-15 (monitoring-роль PostgreSQL) — PROPOSED. Новая сеть `observability` расширяет четырёхсетевую модель DOC-015 §9.1 — зафиксировать как отклонение.

## 8. Тесты (точные команды и результаты, 2026-11-12)
- `make contracts-check contracts-test` — ok (contracts 22 passed).
- `make backend-check backend-test` — ruff, mypy, import-linter (10 контрактов kept, включая «audit не зависит от telemetry») ok; `pytest` backend: **1116 passed** (15 мин 36 с). Юниты после правок review: 305 passed.
- `make infra-check` — ruff ok; `check_compose` 22 сервиса, 0 нарушений (3 комбинации).
- `make infra-scan-secrets` — 0 находок (после добавления фиктивного канареечного теста в ALLOW).
- `make up` — стек поднят, все сервисы healthy (otel-collector без healthcheck — G-132).
- `make infra-test` — **305 passed** (включая promtool с положительными и саботажными контролями).
- `make infra-test-runtime` (`AI_RES_REQUIRE_STACK=1`) — **148 passed**, 0 skipped.
Эти прогоны выполнены после исправлений review. `make pre-pr` прошёл за три приёма: первый остановился на сканере секретов (фиктивный JWT-канарейка в тесте), второй — на длине строки ruff в моей правке; оба исправлены, оставшиеся шаги затем выполнены полностью. Единым запуском цепочка не проходила.

### Проверенные security/authorization cases
Redaction: канареечные секреты (Bearer, JWT, key=value, DSN, PRIVATE KEY) не доходят до Loki/Tempo, с положительным контролем и обходом через Loki push API; lint кардинальности меток; остановка Collector/Loki/Tempo/Prometheus/Alertmanager/Grafana не ломает API (401 < 3 с, контейнеры приложения healthy) и стек восстанавливается; Audit не зависит от telemetry (import-linter + интеграционный тест); нет host-портов, секрет Grafana из Compose secret, анонимный доступ выключен.
Не применимо/не проверено: негативные cross-project тесты доступа к telemetry (нет не-админских ролей, G-130); аутентификация OTLP (G-123).

### Независимое review
`reviews/S13_REVIEWS.md`: 4 агента, blind-first. CRITICAL 1 (алерт не мог сработать) и HIGH исправлены или вынесены владельцу; дельта исправлений отдельным проходом не пересматривалась.

## Неразрешённое и допущения
- Имена метрик Temporal schedule-to-start не проверены реальным workflow (G-129). Тест восстановления после остановки backend'ов слабый (проходит и на старых трассах). Переполнение очереди SDK не считается (G-124). Не закрыты `spanlink`-атрибуты на уровне OTTL.
- Решения владельца: пороги, retention, получатели, доверие внутренних путей только по сети, NCP-15, расширение Outbox для `traceparent` (см. DECISIONS_PENDING).

## Документация обновлена
Да: ADL (095–099), NORMATIVE_CHANGE_PROPOSALS (NCP-15), KNOWN_GAPS (G-22/99/101/102/108 обновлены, G-123…G-133), DECISIONS_PENDING, REQUIREMENTS_TRACEABILITY (13 подтверждённых строк), ECC_USAGE, CONTEXT_HANDOFF, runbook. `docs/architecture/` и Registry не менялись.

## Следующий безопасный инкремент
После слияния PR #16 и решения владельца по G-126/OD-02 — S14.

## Дополнение 2026-11-13 — решения владельца по OD-02 (ADR-100)
Пороги алертов (стартовые, WORKING, пересмотр на S33), retention 30/7/30 дней, получатели только Alertmanager/дашборд и owner `project-owner` реализованы в ветке `feat/s13-owner-decisions`. Проверка: infra static 159 passed (включая promtool `thresholds_test.yml`), `make up` + runtime 148 passed (0 skipped); вживую подтверждены 6 порогов в Prometheus, retention 30d и Loki `retention_period: 30d`. Linux CI для этой дельты не запускался. Остаётся открытым (требует NCP/решения владельца): аутентификация внутренних путей (G-123), NCP-15, `traceparent` через Outbox (G-126).
