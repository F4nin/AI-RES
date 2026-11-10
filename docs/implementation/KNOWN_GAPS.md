# KNOWN_GAPS

Пробелы реализации, инструментария и рисков. Нормативные расхождения S00 — `increments/S00_repository_reconnaissance_REPORT.md` §4 (DR-xx); предложения по их устранению — `decisions/NORMATIVE_CHANGE_PROPOSALS.md`.

| ID | Пробел | Влияние | Статус / план |
|---|---|---|---|
| G-01 | Нет кода, миграций, тестов, CI, Compose | Весь runtime NOT VERIFIED | OPEN — закрывается S01–S39 |
| G-02 | Физический DDL есть только для execution slice | S05–S06 | RESOLVED by decision (ADR-016); реализация S05–S06; NCP-02 |
| G-03 | `@asyncapi/parser@3.4.0` падает (`Error running Nimma`) на Node 26.12.1 | Нет семантической проверки AsyncAPI parser | OPEN — S01: Node 22 LTS и повтор (ADR-004) |
| G-04 | Spectral: 24 warning `operation-description` в Public API v1.3 | Качество контракта | OPEN — baseline в S01; NCP-06 |
| G-05 | OAS 3.2.1 compatibility не тестировалась | — | DEFERRED |
| G-06 | Temporal локально не установлен | S11 | OPEN — через pinned image (ADR-028) |
| G-07 | Bifrost PoC / провайдер LLM | Качество агентного вывода не проверяемо | BLOCKED — OD-01 |
| G-08 | WORKING числовые параметры (SLO, retention, thresholds, lease/backoff, HMAC rotation period) | Release gates S33, S38 | BLOCKED — OD-02; технические defaults помечаются WORKING |
| G-09 | ECC trust assessment | Dev-time supply-chain | ASSESSED — `reviews/ECC_TRUST_ASSESSMENT.md`; приёмка — OD-03 |
| G-10 | DDL отсутствует для `worker_results`, `audit_events`, `task_dependencies` | S05 | RESOLVED by decision (ADR-016) |
| G-11 | В ECC нет агентов для Temporal/LangGraph, DevOps/Docker/CI и API-контрактов | Ниже экспертиза review | MITIGATED — компенсация `architect` + `silent-failure-hunter` + `security-reviewer`; skill `contract-first` (ECC_USAGE.md) |
| G-12 | В OAS v1.3 нет auth endpoints и ряда команд этапов S07, S21, S26, S28–S31, S36 | Эти этапы | RESOLVED by decision (OD-09 владельца; ADR-009, ADR-038): overlay WORKING; формализация — NCP-06 |
| G-13 | Провайдер CI не определён (нет удалённого репозитория в контексте) | S01/S03 | OPEN — CI исполним локально через `make`; workflow-файл — тонкая обёртка |
| G-14 | Требования MVP Matrix сопоставлены с этапами на уровне семейств | Точность трассируемости | OPEN — уточняется в каждом этапе (REQUIREMENTS_TRACEABILITY.md) |
| G-15 | Конфликт BASELINED: checkpointer в PostgreSQL vs запрет DB-доступа runtime | S23 | RESOLVED by decision (ADR-036) |
| G-16 | DOC-069 (WORKING): нет грантов API на outbox/audit; UPDATE на immutable; нет политик dispatcher/consumer | S05 | RESOLVED by decision (ADR-034); отклонение — NCP-02 |
| G-17 | PERSIST-015/016/021/022/023 недостижимы в S05 | S05, S10, S32, S37 | MITIGATED — матрица ADR-035 |
| G-18 | Нет этапа/валидаторов Mermaid/PlantUML и содержательных графов 9 специализаций | S23, S24, S31 | OPEN — уточнить в S23/S24; валидаторы добавлены в S31 |
| G-19 | OAS v1.3: 3 list-операции без cursor/limit (`listRequirementVersions`, `listArtifactVersions`, `listWorkerRunReadinessEvaluations`) — нарушение правила AI RES cursor pagination | S08, S12 | OPEN — зафиксировано в `contracts/spectral-baseline.json`; исправление через overlay/NCP-06 |
| G-20 | Собственный breaking-diff уже oasdiff (нет анализа security schemes, headers, discriminator, allOf-композиции глубже deref) | S03 | OPEN — cross-check oasdiff в CI (ADR-039) |
| G-21 | `@asyncapi/parser` не запускается на Node 26; валидация AsyncAPI — JSON Schema `@asyncapi/specs` 6.11.1 (3.1.0) + `$ref` check; проверка на Node 22 LTS не выполнена (локально доступна только Node 26) | S03 | OPEN — CI на Node 22 (`.nvmrc`) |
| G-22 | В S02: SimpleSpanProcessor синхронный, OTLP exporter не подключён, `pip-audit`/`uv audit` не запускались; не проверено на реальном uvicorn/SSE | S03, S13 | OPEN |
