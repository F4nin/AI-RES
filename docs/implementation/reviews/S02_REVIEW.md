# S02 — независимые review (2026-11-11)

Ревьюеры (ECC, read-only, ИИ той же модели): `fastapi-reviewer`, `security-reviewer`, `type-design-analyzer`. Повторный review после исправлений **не проводился** (см. ограничения).

| Замечание | Sev | Решение |
|---|---|---|
| 500-ответ без `requestId`/`X-Request-ID`/`traceparent` (handler вне middleware) | HIGH | ИСПРАВЛЕНО: `ErrorBoundaryMiddleware` внутри стека; тест `test_500_carries_correlation…` |
| Exception message и stacktrace в spans (`record_exception`) | HIGH | ИСПРАВЛЕНО: `record_exception=False`, статус ERROR без описания; тест проверяет `events` |
| `traceparent` не связан со span | HIGH/MED | ИСПРАВЛЕНО: extract через W3C propagator, ответ — traceparent собственного span; тест на trace_id/parent |
| uvicorn.error/access логи без redaction; query string в access | HIGH | ИСПРАВЛЕНО: тот же formatter для uvicorn-логгеров, query отбрасывается; тест |
| `KeyRing`: секреты в repr, изменяемый dict, сообщения | HIGH | ИСПРАВЛЕНО: MappingProxyType, custom repr, проверки по key id |
| `PolicyDecision` допускал невалидные состояния; ProblemError из порта переименовывался в outage; нет timeout | HIGH/MED | ИСПРАВЛЕНО: валидация, `ProblemError` пробрасывается, обязательный `timeout_seconds`, malformed → 503 |
| `IdempotencyStorePort` без replay/in-progress/complete | HIGH | ИСПРАВЛЕНО: `IdempotencyRequest/Result`, 4 исхода, `complete` |
| Auth-порты `str|None`; `AuditRecord` слабый | HIGH/MED | ИСПРАВЛЕНО: `Principal`, `ServiceIdentity`, `AuditOutcome`, расширенные поля, kw_only/slots |
| Курсор: не привязан к endpoint, без срока, без лимита размера, без domain separation | MED | ИСПРАВЛЕНО: `aud`, `exp` (TTL обязателен), 2048 символов, префикс MAC |
| Extras перезаписывали `level/ts/logger/msg`; пробелы в redaction | MED | ИСПРАВЛЕНО: extras под `ctx`; новые ключи и паттерны (Basic, URL с credentials, PEM, sk-/ghp_/AKIA), bytes |
| Request id regex допускал `\n` | MED | ИСПРАВЛЕНО: `fullmatch` |
| HTTPException headers терялись; 503 → INTERNAL_ERROR; нет instance/no-store | MED | ИСПРАВЛЕНО |
| Конфиг не подключён к запуску; регистр префикса; otlp_endpoint с credentials; key id | MED | ИСПРАВЛЕНО: `create_app_from_env`, case-sensitive отказ, валидаторы |
| If-Match: `v0`, ведущие нули, `W/`, Unicode-цифры; `Versioned` protocol | MED | ИСПРАВЛЕНО |
| Тестовый клиент скрывал исключения и не закрывался | MED | ИСПРАВЛЕНО (yield fixture, `raise_app_exceptions=True`) |
| ErrorCode↔status рассинхрон; ProblemError.status любой int | MED | ИСПРАВЛЕНО: import-time assert, диапазон 4xx/5xx |
| Starlette не объявлен; SimpleSpanProcessor синхронный; нет pip-audit | LOW | starlette объявлен; processor/audit — S03/S13 (G-22) |
| 403 при object-scoped denial раскрывает существование | MED | Принято: маппинг на controlled 404 — на call site в S07/S08 (документировано в docstring) |
| Идемпотентный порт принимает plaintext-ключ | MED | Принято: HMAC внутри реализации S07 (ADR-024) |
| Переименование `row_version` ошибки 400 vs 422 для курсора | LOW | Решено ADR-041: 400 для курсора, 422 для остального |

## Повторное review (2026-11-11): `security-reviewer`, `python-reviewer`
Оба подтвердили исправление первичных HIGH (error boundary, spans, trace context, курсоры, секреты конфигурации, порты). Новые замечания и решения:

| Замечание | Sev | Решение |
|---|---|---|
| ReDoS в паттернах redaction (4 с на 40 КБ) | MED-HIGH | ИСПРАВЛЕНО: ограничены квантификаторы, текст усечён до 8192 до матчинга; тест времени < 0.5 с на 5 враждебных входах |
| Имена секретов с префиксом (`access_token=`, `DB_PASSWORD=`) не маскировались | MED | ИСПРАВЛЕНО: паттерн допускает префикс/суффикс имени; тест |
| `configure_logging` не вызывался в запуске | MED | ИСПРАВЛЕНО: `create_app_from_env` настраивает ai_res и uvicorn логгеры; тест. Запуск uvicorn с `log_config=None` — в Dockerfile S03 |
| Ключевой regex по подстроке (`resource_id` → REDACTED) | LOW | ИСПРАВЛЕНО: токенный матч; тест |
| Тесты меняли глобальное состояние логгеров | LOW | ИСПРАВЛЕНО: autouse-фикстура восстанавливает handlers/level/propagate/filters |
| Вакуозные тесты (trailing newline; cursor 5000×"A") | LOW | ИСПРАВЛЕНО: реальные запрос/подписанный токен >2048 |
| `timeout_seconds=None` отключал fail-closed; `audit_or_abort` без timeout | LOW | ИСПРАВЛЕНО: валидация и обязательный timeout для обоих |
| ClientDisconnect логировался как 500; репр объекта мог сломать лог; span OK при сбое после начала ответа; naive `expires_at`; мёртвый код/noqa | LOW | ИСПРАВЛЕНО (тесты) |
| `otlp_endpoint` не используется, exporter не подключён | LOW | ПРИНЯТО: S13, G-22; docstring уточнён |
| Лоссовое отображение HTTP-статусов framework-ошибок в коды | LOW | ПРИНЯТО и задокументировано (problems.py, ADR-041): клиент смотрит на `status` |
| Порт, поднявший `ProblemError`, маскирует outage | LOW | ПРИНЯТО: fail-closed, документировано |

Итог: открытых HIGH/MEDIUM нет. Третий проход review не проводился; исправления проверены тестами (56) и прогоном на чистой копии.
