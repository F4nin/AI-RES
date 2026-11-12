# S11 — независимое review (2026-11-12)

Основание: `.claude/rules/ecc-precedence.md` («Когда запускать агентов-ревьюеров», п. 2) и промпт S11 («минимум `code-reviewer` + профильный агент»): этап вносит границу безопасности (service-аутентификация внутреннего API, изоляция Runtime от БД) и fail-closed доставку. Temporal/LangGraph-специалиста в ECC нет — компенсация `architect` + `silent-failure-hunter` (ECC_USAGE §1).
Порядок: blind-first (агенты не читали отчёт этапа и этот файл), read-only, параллельно. Состав: `security-reviewer`, `silent-failure-hunter`, `architect`, `code-reviewer`. Выводы агентов статические (тесты они не запускали; `code-reviewer` прогнал ruff/mypy). Не запускались: `database-reviewer` (SQL-изменение — один параметризованный фильтр destination, покрыт PostgreSQL-тестом), `planner`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer` (основание — «малые изменения без новых рисков» для этих областей; причина записана и в отчёте).

**Итог:** CRITICAL — 0. HIGH (после объединения дублей) — 4 группы: застревание Operation при исчерпании retry и скрытый `ALREADY_FINISHED` (3 агента), зависание процесса воркера, healthcheck'и «зелёные при бесполезном процессе», отсутствие аутентификации Temporal (confused deputy; 2 агента). Две группы исправлены, две сведены в открытые пробелы с решением владельца (OD-19) — S11 **не** заявляет, что Worker технически не может стартовать workflow: гарантия держится на сетевой/кодовой изоляции.

## 1. Исправлено в рамках этапа

| # | Источник | Находка | Исправление / проверка |
|---|---|---|---|
| R1 | silent H1, arch H1, code M1 | 6 попыток (~30 с) — после них workflow падал и Operation оставалась ACCEPTED/RUNNING; docstring утверждал обратное | Retry ограничен временем (`ACTIVITY_BUDGET` 15 мин, WORKING), docstring честно описывает остаточное (G-107); тесты workflow зелёные |
| R2 | silent H2, arch H1 | Повторная доставка после закрытия workflow молча считалась успехом | `ALREADY_FINISHED` → warning + метрика `start_already_finished` (восстановление — G-107) |
| R3 | silent H3 | Процесс воркера ждал сигнала даже после падения воркера | `run_worker_until_stopped`: ждёт воркер ИЛИ сигнал, неожиданное завершение → ошибка/выход ≠0; стек пересобран, health и сквозной прогон проходят |
| R4 | silent M1 | Любой `RPCError` считался transient | Классификация по статусу: UNAVAILABLE/DEADLINE_EXCEEDED/… — transient, INVALID_ARGUMENT/NOT_FOUND/PERMISSION_DENIED — permanent (карантин), статус в логе |
| R5 | silent M2, code L2 | `connect()` бросал ValueError | `ConfigError` (чистое сообщение, exit 1) |
| R6 | silent M5, code L1 | «Невозможный» статус давал 404 | `INTERNAL_ERROR` (5xx, fail closed) |
| R7 | code M3/M4, arch M2, silent M3 | 409 (гонка CAS — transient) и 412 (ошибка состояния — permanent) не были зафиксированы тестами | `test_concurrent_acknowledgements…` (6 параллельных ack на реальном PostgreSQL: ровно по одному queued/started), `test_state_error_is_permanent_412…`, комментарии |
| R8 | code L4, L8 | Мёртвый реэкспорт; импорты workflow без passthrough | Удалено; `workflow.unsafe.imports_passed_through()` |
| R9 | code (тесты), silent M6 | Вакуозная проверка исходов старта; scan истории проходил бы при пустой выборке | `outcomes[0] is ENSURED`, `len(payloads) >= 4` |

## 2. Не исправлено — зафиксировано (владелец/следующие этапы)

| # | Источник | Находка | Где зафиксировано |
|---|---|---|---|
| O1 | security H1, arch H2 | Temporal без authN/authZ/TLS: компрометированный Worker Runtime может стартовать workflow и опросить очередь Manager (confused deputy) | **G-104, OD-19** (решение владельца/security owner; до S23) |
| O2 | silent H1/H2, arch H1/M4 | Нет reconciler'а Operation↔Temporal, нет allowlist типов Operation и производителя маршрута | **G-107** — обязательное условие до первого производителя; сейчас безопасно, т.к. производителя нет (dispatcher простаивает; `closes G-98` смягчено до PARTIAL) |
| O3 | silent H4, arch L4 | Healthcheck'и — только достижимость Temporal/любой HTTP-ответ; нет OTel-интерсептора | G-108 (S13) |
| O4 | security M1–M4, L1–L5, arch L5/L6 | Capability на идентичность, нет jti-кэша, общий audience, HTTP без TLS в `app`, общая DB-роль, нет аудита отказов 401/403, нет лимита тела | G-106, G-111 |
| O5 | arch M1, M5, M4 | QUEUED не наблюдаем; fixture skeleton v1 тянет patching; код ошибки не в реестре | G-110, NCP-14 |
| O6 | arch M3 | Worker build id не записывается, порядок §9.5 (Worker Versioning основной) не соблюдён | G-105 (PoC) |
| O7 | silent L1, L2 | Причина отказа платформы теряется в ApplicationError; 401 не логируется | G-106 |
| O8 | code L3, L5–L7, L9, тесты | Мелочи: порядок connect/engine в dispatcher, `InvalidURL` вне `HTTPError`, нет проверки `operationId` ответа, `ed25519_public_b64` без проверки длины DER, тест «redirect» неявный, хрупкий разбор имён событий в e2e | Не исправлено; не влияет на безопасность этапа |
| O9 | silent M6 | Нет тестов: исчерпание retry оставляет Operation застрявшей, смерть воркера в процессе, ack vs cancel | Привязаны к G-107/G-108 (reconciler/метрики) и S12 (cancel) |
| O10 | arch L1 | `modules/events/temporal_start.py` зависит от Temporal SDK (import-linter разрешает) | Принято; перенос при росте числа адаптеров |
| O11 | silent M2 | Нет `restart:`-политики Compose для новых сервисов (падение процесса не перезапускается) | Не исправлено; общая политика restart для долгоживущих сервисов S03 не вводилась (OPEN, S13) |

## 3. Что агенты проверили и признали корректным
Проверка service-токена (Ed25519 с доменным префиксом, точный набор claims, TTL на выдаче и проверке, audience, любая ошибка → None) и порядок 401→403→404; единообразный 404 для чужой/отсутствующей Operation; отсутствие SSRF в HTTP-клиенте (путь из канонических UUID, без редиректов, без логирования тел); детерминизм workflow; компактность входов (`assert_compact` + scan истории); легальность и непропускаемость переходов §2.4, неперезапись терминального; запись transition+event+outbox+audit в одной транзакции; параметризованный фильтр destination и его применение к lease-карантину; Compose: у Manager нет DB env/секрета/сети data, у Worker нет секретов, Caddy проксирует только `api:8000`.

## 4. Ограничения review
Агенты не запускали тесты и Compose; `architect` не запускал import-linter. Дельта исправлений R1–R9 отдельным агентом не пересматривалась (проверена тестами: temporal 8, internal API 8, e2e 2, unit 42, runtime-набор стека).
