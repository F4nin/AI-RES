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
| G-13 | Провайдер CI не определён | S01/S03 | RESOLVED 2026-11-11: GitHub Actions, remote `origin` = `F4nin/AI-RES` (публичный репозиторий); workflows — тонкие обёртки над `make` |
| G-14 | Требования MVP Matrix сопоставлены с этапами на уровне семейств | Точность трассируемости | OPEN — уточняется в каждом этапе (REQUIREMENTS_TRACEABILITY.md) |
| G-15 | Конфликт BASELINED: checkpointer в PostgreSQL vs запрет DB-доступа runtime | S23 | RESOLVED by decision (ADR-036) |
| G-16 | DOC-069 (WORKING): нет грантов API на outbox/audit; UPDATE на immutable; нет политик dispatcher/consumer | S05 | RESOLVED by decision (ADR-034); отклонение — NCP-02 |
| G-17 | PERSIST-015/016/021/022/023 недостижимы в S05 | S05, S10, S32, S37 | MITIGATED — матрица ADR-035 |
| G-18 | Нет этапа/валидаторов Mermaid/PlantUML и содержательных графов 9 специализаций | S23, S24, S31 | OPEN — уточнить в S23/S24; валидаторы добавлены в S31 |
| G-19 | OAS v1.3: 3 list-операции без cursor/limit (`listRequirementVersions`, `listArtifactVersions`, `listWorkerRunReadinessEvaluations`) — нарушение правила AI RES cursor pagination | S08, S12 | OPEN — зафиксировано в `contracts/spectral-baseline.json`; исправление через overlay/NCP-06 |
| G-20 | Собственный breaking-diff уже oasdiff (нет анализа security schemes, headers, discriminator, allOf-композиции глубже deref) | S03 | OPEN — cross-check oasdiff в CI (ADR-039) |
| G-21 | `@asyncapi/parser` не запускается на Node 26; валидация AsyncAPI — JSON Schema `@asyncapi/specs` 6.11.1 (3.1.0) + `$ref` check; проверка на Node 22 LTS не выполнена (локально доступна только Node 26) | S03 | OPEN — CI на Node 22 (`.nvmrc`) |
| G-22 | В S02: SimpleSpanProcessor синхронный, OTLP exporter не подключён, `pip-audit`/`uv audit` не запускались; не проверено на реальном uvicorn/SSE | S03, S13 | OPEN |
| G-23 | У api нет readiness/health endpoint (контракт отсутствует в OAS; endpoint без контракта запрещён): healthcheck стека — liveness (любой HTTP-ответ) | S03, S08, S13 | OPEN — health/readiness как overlay-контракт (ADR-038) в S08 или S13 |
| G-24 | Сторонние закреплённые образы имеют HIGH/CRITICAL с доступным исправлением (на 2026-11-11: Temporal server 146, UI 117, admin-tools 291, otel-collector 61, Postgres 16.15 26); исправить нельзя — только обновить версию | S03, S37, release | OPEN — report-only (ADR-043), Renovate; перед релизом обновить/принять исключения владельцем |
| G-25 | TLS для соединений с PostgreSQL (DOC-015 add.1.6) | S03 | RESOLVED в S03: локальный CA, `hostssl` + SCRAM, `pg_hba` по ролям и БД, Temporal подключён по TLS с проверкой хоста (тест по `pg_stat_ssl`). Остаток: сертификаты dev-only (825 дней — WORKING); ротация и клиентские сертификаты — S32/S37 |
| G-26 | Образы не подписываются и подписи сторонних образов не проверяются (cosign, DOC-015 §14.3); `signature_verified` в Release Manifest всегда false | S03, release | OPEN — release candidate (S37) |
| G-27 | CI workflows на runner GitHub (Linux) | S03 | RESOLVED 2026-11-11: ветка `ci/s03-first-run`, коммит `5272c69`; `ci` (run 42980598813: backend, infra-static, infra-runtime) и `contracts` (run 42980597940) — success. Подтверждено на Linux: права bind-mount секретов, установка sops/age, сборка MinIO, runtime-тесты с `AI_RES_REQUIRE_STACK=1`, скан секретов с реальными значениями, SBOM + скан образов. Остаток: политика approval для workflows от fork-PR (публичный репозиторий) настраивается владельцем в Settings → Actions (M-6); прогон на `main`/PR не выполнялся |
| G-28 | Egress allowlist для LLM Gateway/Connector Platform не реализован: сеть `egress` без участников; deny-by-default обеспечен `internal: true` у app/data/admin, а не прокси-allowlist | S03, S15, S16, S28 | OPEN — S15/S16/S28 добавляют сервисы в `egress` |
| G-29 | PERSIST-023 проверен для существующих сервисов (структурно + inspect); Manager/Worker Runtime ещё не существуют — реальная проверка сетевого пути в S11/S23 | S03, S11, S23 | OPEN — ADR-035 |
| G-30 | MinIO/mc: community-ветка собирается нами из тега с обновлёнными зависимостями; исключения CVE prometheus (CVE-2026-42151/42154, до 2027-01-31); AGPL-3.0 — license review | S03, S27, release | OPEN |
| G-31 | `renovate.json` не проверялся приложением Renovate (нет репозитория на платформе) | S03 | OPEN |
| G-32 | Пароль БД Temporal находится в окружении процесса `temporal-server`/`temporal-sql-tool` (шаблон конфига принимает пароль только из env); вне `docker inspect` и логов | S03 | ACCEPTED risk (ADR-044); пересмотреть при смене способа конфигурации Temporal |
| G-33 | Лимиты памяти/pids/ресурсов, retention namespace Temporal (72h) — WORKING dev defaults, не утверждены | S03, S38 | OPEN — OD-02 |
| G-34 | У Caddy неограниченный исходящий трафик (сеть `ingress` не internal; метаданные облака и LAN не блокируются) | S03, S37 | OPEN — ограничение исходящих (firewall/DOCKER-USER или egress-proxy); текущее поведение зафиксировано тестом |
| G-35 | Исключения уязвимостей применяются глобально по CVE, не по образу/компоненту; скан использует `--ignore-unfixed`; сторонние образы без baseline/regression gate | S03, S37 | OPEN |
| G-36 | Temporal frontend и UI без аутентификации/авторизации (mTLS/authorizer), UI с write-действиями; доверие только по сети (DOC-015 §9.2) | S03, S11, S37 | OPEN — к S11 |
| G-37 | Консоль и S3 API MinIO слушают на всех интерфейсах и доступны участникам `data`/`admin`; init использует root-учётку | S03, S27 | OPEN — отдельные service accounts и ограничение консоли в S27 |
| G-38 | Нет решения о сетевом пути Manager/Worker → Temporal без доступа к `data` (отдельная internal-сеть `workflow`?) | S03, S11 | OPEN — решить в S11; check_compose допускает Manager/Worker только в `app`/`workflow` |
| G-39 | Третья БД `temporal_visibility_db` (деталь Temporal; DOC-015 §5.1 называет `ai_res_db` и `temporal_db`); неатомарная запись секретов, версии uv различаются (Dockerfile 0.11.0 / CI 0.11.31), нет OCI revision label | S03 | OPEN — владелец подтверждает интерпретацию при следующей синхронизации baseline (NCP) |
| G-40 | Остатки re-review S03 (MEDIUM/LOW): `scan_secrets` не знает имён `access_key`/`*_pwd`/`credential`/`hmac_key`, значения <16 символов и исключает `.claude/`, `docs/implementation/reviews/`; хостовая проба портов в `test_stack.py` не отличает чужой процесс от опубликованного порта (transient на 8000 не объяснён); `check_compose` не ловит `healthcheck NONE`, `devices`, `volumes_from`, `sysctls`, unconfined seccomp; тест egress Caddy не может упасть; скан слоёв не читает zstd | S03 | OPEN — `reviews/S03_security_rereview.md`, `S03_silent_failure_rereview.md`; закрыть до S37 |
| G-41 | `preflight.sql` `long_transaction` best-effort: без `pg_read_all_stats` migrator не видит чужие сессии (расширять права migrator не стали) | S04, S32 | OPEN — решить с релизным pipeline |
| G-42 | Пароль login-ролей передаётся серверу литералом в `ALTER ROLE … PASSWORD` (логирование DDL/duration отключено в сессии; виден суперпользователю в `pg_stat_activity` на время выполнения). Предвычисленный SCRAM-verifier на клиенте убрал бы это | S04, S37 | OPEN — ADR-046 |
| G-43 | Testcontainers идут по plain TCP (TLS/`pg_hba` доказаны только на живом стеке); S04 ещё не прогонялся в GitHub Actions на Linux (как G-27 для S03) | S04 | OPEN — закрыть первым CI-прогоном ветки S04 |
| G-44 | `hostssl all postgres all` в `pg_hba` не ограничен адресами, а в сети `data` появится API с DB-credentials (S08+): RCE в API получает сетевой путь к суперпользователю (нужен пароль) | S03, S04, S37 | OPEN — ограничить CIDR или вынести суперпользователя в `admin` |
| G-45 | Alembic и миграции присутствуют в образе API (один образ с `migrate`); отдельный stage/образ уменьшил бы поверхность | S04, S37 | ACCEPTED risk (ADR-047) |
| G-46 | ADR-042…049 добавлены прямо в `ARCHITECTURE_DECISION_LOG.md`, их нет в `tools/adrs.py`: запуск `tools/gen.py` перезапишет журнал; статусы в `prompts/README.md` генерируются и отстают от `IMPLEMENTATION_STATUS.md` | S03, S04 | OPEN — перенести ADR в `adrs.py` или отключить генерацию ADL |
| G-47 | PERSIST-002 («upgrade from previous revision») тривиален: существует одна ревизия; PERSIST-005..014 (полный набор на доменных таблицах) — S05 по ADR-035; профиль привилегий `ai_res_backup` и pgBackRest — S32 | S04, S05, S32 | OPEN — по плану |
