# S13 — независимое review (2026-11-12)

Состав (ecc-precedence п. 1: этап чьего промпта требует независимого review; blind-first, read-only): `code-reviewer`, `security-reviewer`, `silent-failure-hunter`, `architect`. Агенты отчёты автора не читали. Статические находки; запусков тестов агенты не делали.

CRITICAL: 1 (исправлен). HIGH: 6 (все исправлены или вынесены владельцу как документированное решение). Итог после исправлений: CRITICAL/HIGH открытых нет.

| № | Агент | Серьёзность | Находка | Решение |
|---|---|---|---|---|
| 1 | silent-failure | CRITICAL | `CollectorBackendExportFailing` складывал серии с разными `exporter` через `+` — пустой результат, алерт не мог сработать; promtool-кейса не было | Исправлено (`or` по `sum by (exporter)`, скобки вокруг `> 0` — первая правка упала на приоритете оператора и поймана promtool-кейсом); добавлен положительный promtool-кейс с контролем «нулевой экспортёр не срабатывает» |
| 2 | silent-failure, code | HIGH | Первое приращение лениво созданного счётчика теряется в `increase()` (DatabaseErrors, UnknownMajorEventVersion, OperationCancelWithoutWorkflow, TelemetryExportFailing) | Исправлено: `increase(...) > 0 or (x unless x offset w) > 0`; promtool-кейс на серию, появившуюся сразу со значением |
| 3 | silent-failure, code | HIGH | Нет сигнала, если процесс приложения замолчал: серии истекают за `metric_expiration`, алерты outbox самоустраняются | Добавлен `ApplicationTelemetryMissing` (+runbook, promtool) |
| 4 | silent-failure, code | HIGH | Переполнение очереди batch-процессора SDK не считается | НЕ исправлено; задокументировано (G-124, ADR-097): метрика потерь best-effort |
| 5 | security | HIGH | OTLP-приёмник без аутентификации/изоляции продюсеров; метрики/логи можно подделать, нет лимита серий | Частично: `label_limit`/`sample_limit` на scrape; остальное — G-123 + явное решение владельца (DOC-015 §9.2 запрещает доверие только сети) вынесено в DECISIONS_PENDING |
| 6 | security | HIGH | Redaction неполная: span name, scope-атрибуты, не-строковое тело лога, четыре из восьми шаблонов для атрибутов логов | Исправлено в `otel/config.yaml` (scope keep_keys, маскирование `name`, не-строковое тело заменяется, все шаблоны для атрибутов, `severity_text` очищен); `spanlink` в OTTL 0.116 не поддерживается — ссылки спанов остаются на allowlist-redaction процессора (проверено только конфигом) |
| 7 | architect | HIGH | Retention-текст неверен: Prometheus/Tempo удаляют по умолчанию | Исправлены runbook и комментарии; явные сроки — владельцу (OD-02, OBS-SEC-007) |
| 8 | architect | HIGH | Сквозной trace (DOC-024 §12 п.1) не выполнен: контекст не идёт через Outbox | Не исправлено (изменение контракта событий → NCP); G-126, статус этапа ограничен |
| 9 | silent-failure | MEDIUM | `error_mode: ignore` в процессорах redaction | Исправлено: `propagate` (+ статический тест) |
| 10 | security, code | MEDIUM | Атрибут `http.request.method` на спане без нормализации | Исправлено |
| 11 | code | MEDIUM | Метрика `db.client.connection.max` без `max_overflow` — ложное насыщение | Исправлено |
| 12 | code | MEDIUM | `Runtime` Temporal создаётся на каждый `connect()` | Исправлено (кэш) |
| 13 | code | MEDIUM | Отмена клиентом считалась 5xx | Исправлено |
| 14 | code | LOW | `_ACTIVE` не очищается; двойной `install_telemetry` дублирует логи | Исправлено |
| 15 | architect | MEDIUM | Нет `release_id`/`service.version` | Исправлено: из настройки `release_id` (значение даёт релизный процесс, не выдумано) |
| 16 | architect | MEDIUM | Захардкожены 0.9 (очередь Collector) и 1 (пул); «max 1h» в silence_policy | Исправлено: порог `collector_queue_fill_ratio` в thresholds, `max 1h` убрано; пул — отношение к реальному максимуму |
| 17 | architect | MEDIUM | Недостающий дашборд Manager & Workers | Добавлен runtime-вид; LLM & Tools, Product Quality — G-128 |
| 18 | security | MEDIUM | Grafana admin может завести datasource на Temporal UI/MinIO (SSRF) | Исправлено: `GF_SECURITY_DATA_SOURCE_PROXY_WHITELIST` |
| 19 | security, code | MEDIUM | MinIO/Temporal метрики доступны всей сети | Принято, задокументировано (G-123), комментарий в Compose исправлен |
| 20 | code | LOW | Идентификаторы Temporal не проходят allowlist | Исправлено |
| 21 | code | MEDIUM | Тест восстановления после остановки backend'ов недоказателен (старые трассы) | Не исправлено в этом проходе — открыто как остаточный риск в отчёте |
| 22 | silent-failure | MEDIUM | Пороговые алерты инертны без видимого признака | Исправлено: панель «Numeric alert thresholds configured» на Platform Overview |
| 23 | architect | LOW | Правило ингибирования не совпадает с метками | Удалено (нет доказанного совпадения) |
| 24 | architect | LOW | `external_labels: environment: local` | Удалено |

Не приняты/отложены: Loki/Tempo лимиты (L3), health-check Collector (G-132), хост-метрики (G-127), разграничение доступа Grafana (G-130), `shutdown()` в api/serve_internal (fail-open допускает потерю последнего батча).
