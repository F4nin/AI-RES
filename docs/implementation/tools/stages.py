# Stage data: single source for ROADMAP, STATUS, prompts and index.
# gate: DONE | READY | PENDING_DEPS | BLOCKED
A = "docs/architecture/"
R = lambda doc, sec: f"`{A}{doc}` — {sec}"

SPEC = "AI_RES_Claude_Code_Implementation_Spec_v1.22.md"
REG = "AI_RES_Document_Registry_v4.1.md"
DM = "AI_RES_Domain_Model_and_Data_Architecture_v1.9.md"
API = "AI_RES_API_and_Interaction_Contracts_v1.10.md"
OAS = "AI_RES_Public_API_v1.3.yaml"
ASY = "AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"
WC = "AI_RES_Worker_Contracts_v1.1.schema.json"
ORG = "AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md"
ORGS = "AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json"
SM = "AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json"
EM = "AI_RES_Operation_WorkerRun_Event_Model_v1.4.md"
PM = "AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md"
DDL = "AI_RES_PostgreSQL_Physical_Model_v1.0.sql"
MIG = "AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md"
RLS = "AI_RES_PostgreSQL_Roles_RLS_v1.0.sql"
BP = "AI_RES_Persistence_Implementation_Blueprint_v1.0.md"
INF = "AI_RES_Infrastructure_Deployment_Operations_v1.7.md"
SEC = "AI_RES_Security_Architecture_v1.2.md"
SECR = "AI_RES_Security_Controls_and_Requirements_v1.2.md"
THR = "AI_RES_Threat_Model_v1.1.md"
IAM = "AI_RES_Identity_Access_Control_v1.5.md"
AUTH = "AI_RES_Authentication_and_Session_Management_v1.1.md"
SK = "AI_RES_Secrets_and_Key_Management_v1.1.md"
OBS = "AI_RES_Observability_Architecture_v1.2.md"
MON = "AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md"
AOE = "AI_RES_Agent_Observability_and_Evaluation_v1.2.md"
MG = "AI_RES_Model_Gateway_and_Model_Registry_v1.0.md"
KMR = "AI_RES_Knowledge_Memory_Retrieval_Architecture_v1.0.md"
TR = "AI_RES_Tool_Registry_and_Tool_Management_MVP_v1.0.md"
SC = "AI_RES_Source_and_Context_Lifecycle_v1.3.md"
EXT = "AI_RES_External_Integrations_and_Project_Context_v1.2.md"
EV = "AI_RES_Evaluation_and_Release_Gates_v1.0.md"
LE = "AI_RES_Learning_Experience_Lifecycle_v1.0.md"
PD = "AI_RES_Process_Design_and_Algorithms_v1.9.md"
RL = "AI_RES_Requirements_Lifecycle_v2.7.md"
DAL = "AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md"
TDI = "AI_RES_Traceability_Dependencies_Impact_Analysis_v1.0.md"
UX = "AI_RES_UX_Concept_v1.2.md"
AC = "AI_RES_Agent_Architecture_Concept_v4.6.md"
MVP = "AI_RES_MVP_Capability_Matrix_v3.3.md"
ACB = "AI_RES_Architecture_Completion_and_Baseline_Decisions_v1.0.md"
DAR = "AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md"
PSR = "AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md"
PSA = "AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md"
RR = "AI_RES_Resilience_and_Recovery_Requirements_v1.0.md"
CLT = "AI_RES_Capacity_and_Load_Test_Plan_v1.0.md"
RB = "AI_RES_Operational_Runbooks_v1.0.md"
GL = "AI_RES_Glossary_v1.1.md"
CIA = "AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.3.md"
UDA = "AI_RES_User_Documentation_Information_Architecture_v1.1.md"
PPP = "AI_RES_Post_Implementation_Productization_Plan_v1.3.md"
MAN = "AI_RES_Architecture_Baseline_Manifest_v1.2.json"

# ECC building blocks (actual installed names)
E_ARCH = ("architect", "архитектурное соответствие плана и результата нормативной архитектуре (read-only review)")
E_PLAN = ("planner", "декомпозиция этапа на вертикальные срезы перед реализацией")
E_PY = ("python-reviewer", "review Python-кода")
E_FA = ("fastapi-reviewer", "review FastAPI слоя (ADR-008)")
E_DB = ("database-reviewer", "review миграций, ролей, RLS, запросов (с учётом ecc-precedence: RLS через transaction-local context, не Supabase)")
E_SEC = ("security-reviewer", "независимое security review")
E_CR = ("code-reviewer", "независимое общее code review")
E_SF = ("silent-failure-hunter", "поиск проглоченных ошибок, небезопасных fallback и fail-open путей")
E_TDD = ("tdd-guide", "тесты до реализации (DoD — по testing-and-verification.md, не «80% coverage»)")
E_PRT = ("pr-test-analyzer", "оценка полноты поведенческих и негативных тестов")
E_TYPE = ("type-design-analyzer", "проверка инвариантов в типах DTO/доменных моделей")
E_BUILD = ("build-error-resolver", "устранение ошибок сборки/типов минимальными правками")
E_TS = ("typescript-reviewer", "review TypeScript")
E_RE = ("react-reviewer", "review React-компонентов")
E_A11Y = ("a11y-architect", "WCAG 2.2 доступность")
E_E2E = ("e2e-runner", "Playwright E2E (без внешних сервисов)")
E_RAG = ("rag-pipeline-reviewer", "review ingestion/chunking/retrieval и retrieval-evaluation")
E_MLE = ("mle-reviewer", "review evaluation pipelines, датасетов и воспроизводимости")
E_PERF = ("performance-optimizer", "анализ узких мест по результатам измерений")
E_DOC = ("doc-updater", "обновление docs/implementation (не docs/architecture)")

S_PYP = ("python-patterns", "идиомы и типизация Python")
S_PYT = ("python-testing", "pytest, fixtures, parametrization (без FastAPI-примеров как обоснования стека)")
S_TDD = ("tdd-workflow", "red → green → refactor")
S_PG = ("postgres-patterns", "индексы, запросы (Supabase-RLS паттерны не применять)")
S_MIG = ("database-migrations", "expand/contract, concurrent indexes (только Alembic)")
S_CF = ("contract-first", "contract-first координация, сгенерированные типы")
S_API = ("api-design", "только в части ресурсов/статусов; пагинация — cursor, ошибки — RFC 9457 (ecc-precedence)")
S_ERR = ("error-handling", "типизированные ошибки, bounded retries")
S_VL = ("verification-loop", "финальная верификация этапа")
S_EH = ("eval-harness", "dev-time eval-driven критерии для агентных компонентов")
S_E2E = ("e2e-testing", "Playwright patterns")
S_AIR = ("ai-regression-testing", "регрессия AI-assisted изменений")
S_PA = ("production-audit", "локальный аудит готовности (без внешних сервисов)")

C_PLAN = ("/plan", "план этапа до кода")
C_PYR = ("/python-review", "review Python изменений")
C_FAR = ("/fastapi-review", "review FastAPI")
C_CR = ("/code-review", "локальный review изменений (без PR-режима)")
C_QG = ("/quality-gate", "проверка quality gates")
C_TC = ("/test-coverage", "отчёт покрытия как дополнительная метрика")
C_BF = ("/build-fix", "исправление сборки")
C_RR = ("/react-review", "review React")
C_RT = ("/react-test", "тесты React")
C_SR = ("/security-review", "встроенная команда Claude Code: security review изменений ветки")

BASE_AGENTS = [E_PLAN, E_ARCH, E_CR, E_SF]
BASE_SKILLS = [S_VL]
BASE_CMDS = [C_PLAN, C_CR, C_QG]

def ecc(agents=(), skills=(), cmds=()):
    return dict(agents=list(BASE_AGENTS) + list(agents), skills=list(skills) + BASE_SKILLS, cmds=list(BASE_CMDS) + list(cmds))

PY_ECC = dict(agents=[E_PY, E_TDD, E_PRT], skills=[S_PYP, S_PYT, S_TDD], cmds=[C_PYR, C_TC])

def py(extra_agents=(), extra_skills=(), extra_cmds=()):
    return ecc(PY_ECC["agents"] + list(extra_agents), PY_ECC["skills"] + list(extra_skills), PY_ECC["cmds"] + list(extra_cmds))

STAGES = [
 dict(id="S00", slug="repository_reconnaissance", title="Repository reconnaissance и baseline manifest", spec="Spec Inc. 0", phase="A. Foundation",
  deps=[], gate="DONE", blockers=[], reqs=["—"],
  goal="Разведка репозитория, Implementation Baseline Manifest, discrepancy report, первичный план.",
  refs=[R(SPEC, "§4 Increment 0; Add. v1.3 §1, §5"), R("AI_RES_Pre_Implementation_Readiness_Audit_v2.2.md", "§4")],
  scope=["Выполнено: см. `docs/implementation/increments/S00_repository_reconnaissance_REPORT.md`."], out=[],
  deliverables=["S00 report"], tests=["Static: Registry/manifest SHA-256, валидация контрактов"],
  ecc=ecc(), adrs=[], decide=[], docs=[], dod=["Выполнено (IMPLEMENTED, static evidence); воспроизводимость проверок обеспечивает S01."]),

 dict(id="S01", slug="contract_toolchain", title="Contract toolchain и CI-валидация контрактов", spec="Spec Inc. 1", phase="A. Foundation",
  deps=["S00"], gate="DONE", blockers=[], reqs=["API-MVP-001", "API-MVP-0xx (contract compatibility)"],
  goal="Воспроизводимая в репозитории валидация OpenAPI/AsyncAPI/JSON Schema, lint, breaking-change detection и SHA-256 контроль зеркала контрактов; минимальный CI.",
  refs=[R(SPEC, "§4 Increment 1; §7; §8 (Contracts)"), R(API, "§15 Contract compatibility and versioning; §17 Contract testing and quality gates; §18"), R(REG, "§2 (DOC-006/007/008/050/056/057), §5"), R(MAN, "files[].sha256"), "`.claude/rules/api-and-contracts.md` — «OpenAPI/AsyncAPI toolchain»"],
  scope=["Каталог `contracts/` (openapi, asyncapi, json-schema/{common,worker,events,commands}, examples) — зеркало canonical файлов (ADR-009).",
         "Pinned toolchain: Python (uv: openapi-spec-validator, jsonschema, pyyaml) и Node 22 LTS (`.nvmrc`/`engines`; Spectral, @asyncapi/specs, @asyncapi/parser — повторная проверка G-03; oasdiff — pinned binary или docker image по digest).",
         "Скрипты `contracts/tools/`: verify-mirror (SHA-256 против manifest), validate-openapi, validate-asyncapi, validate-jsonschema (локальный `$id` registry), check-refs, breaking-change (oasdiff + собственный diff для AsyncAPI/JSON Schema).",
         "Spectral ruleset: `spectral:oas` + правила AI RES (cursor pagination, Problem Details, Idempotency-Key на side-effecting POST, If-Match на version-sensitive writes); baseline 24 существующих warning (G-04) — новые запрещены.",
         "Минимальный CI workflow (`.github/workflows/contracts.yml` или эквивалент, без публикации куда-либо) и `Makefile` цели `contracts-check`.",
         "Examples: валидные и невалидные фикстуры для каждого контракта.",
         "`contracts/CHANGELOG.md` и `contracts/COMPATIBILITY.md` (политика совместимости).",
         "Удалить пустые корневые `src/`, `tests/`, `scripts/` (ADR-005)."],
  out=["Генерация application code (до S02).", "Изменение содержимого canonical контрактов."],
  deliverables=["`contracts/**`", "`Makefile`", "CI workflow", "`contracts/tools/*`", "S01 report"],
  tests=["Каждый валидатор падает на соответствующей негативной фикстуре (broken $ref, неверный тип, неизвестное поле, отсутствующий required).",
         "verify-mirror падает при изменении одного байта зеркала.",
         "breaking-change: удаление обязательного поля/endpoint детектируется; additive optional поле — нет.",
         "Spectral AI RES rules: offset-пагинация и не-RFC9457 error в фикстуре → error.",
         "Полный `make contracts-check` на текущих контрактах — зелёный."],
  ecc=ecc([E_TYPE], [S_CF, S_API], []), adrs=["ADR-004", "ADR-005", "ADR-009"],
  decide=["Точные версии инструментов и способ поставки oasdiff.", "Структура CI (провайдер CI в репозитории не определён — использовать формат, исполнимый локально через `make`; CI-файл — тонкая обёртка)."],
  docs=["CONTRACT_TRACEABILITY_MAP.md (пути `contracts/`)", "LOCAL_DEVELOPMENT.md (команды)", "KNOWN_GAPS.md (G-03, G-04)"],
  dod=["`make contracts-check` воспроизводимо проходит из чистого клона.", "Все негативные фикстуры падают ожидаемо.", "Lock-файлы (uv.lock, package-lock.json) закоммичены в рабочее дерево (commit — только по разрешению)."]),

 dict(id="S02", slug="backend_skeleton_platform_primitives", title="Backend skeleton и platform primitives (без БД)", spec="Spec Inc. 2 (п.1–5, 7–9); Process Design §22 п.1 (частично)", phase="A. Foundation",
  deps=["S01"], gate="DONE", blockers=[], reqs=["API-MVP (общие HTTP правила)", "SEC-MVP (error leakage)", "OBS (correlation)"],
  goal="Каркас модульного монолита `backend/` и платформенные примитивы, не требующие БД, с negative/security тестами и telemetry.",
  refs=[R(SPEC, "§4 Increment 2; §5 Required API and DTO behavior; §6"), R(API, "§5 Общие HTTP правила; §6; §14 Audit, trace and correlation; §16 Error taxonomy"), R(BP, "§3 Обязательная структура репозитория"), R(OBS, "§6 Корреляция и taxonomy; §8"), R(IAM, "§2 Слои контроля; §7"), R(INF, "§11.3 Иерархия и правила конфигурации"), "`.claude/rules/coding-standards.md`"],
  scope=["`backend/pyproject.toml` + `uv.lock` (FastAPI, Pydantic v2, uvicorn, uuid-utils, opentelemetry-*, structlog/std logging), `.python-version`.",
         "Пакеты `backend/src/ai_res/` по Blueprint §3 + `platform/` (ids, time, problems, correlation, pagination, concurrency, auth ports, policy port, audit port, config).",
         "UUIDv7 (ADR-027) и UTC RFC3339 сериализация.",
         "RFC 9457 Problem Details: стабильные `code` из DOC-006 §16; никаких stack traces/секретов.",
         "Request/correlation/trace propagation (W3C traceparent, `X-Request-ID`), OTel SDK, структурные логи с redaction (ADR-025).",
         "Cursor pagination codec: opaque, подписанный HMAC, привязан к пользователю/фильтру; stable ordering contract.",
         "ETag/If-Match примитивы и `row_version` контракт (без БД).",
         "Порты: `AuthenticationPort`, `ServiceIdentityPort`, `PolicyDecisionPort` (ADR-017), `AuditWriterPort` (fail-closed семантика), `IdempotencyStorePort` (реализация — S07).",
         "Типизированный каталог конфигурации: неизвестные ключи/неверные типы → ошибка запуска; секреты только из файлов Compose secrets.",
         "Architecture tests (import-linter или эквивалент): запрет импорта ORM в API-слой, provider SDK вне adapter, cross-module internals."],
  out=["Таблицы и миграции (S04+).", "Реальная аутентификация (S07).", "Доменные endpoints (S08+)."],
  deliverables=["`backend/**` skeleton", "unit/security tests", "S02 report"],
  tests=["Problem Details: unknown exception → 500 c generic body без деталей; validation error → 400/422 с `code`.",
         "Cursor: подделка/чужой пользователь/изменённый фильтр → 400 без раскрытия данных.",
         "If-Match: отсутствует → 428/412 по DOC-006; stale → 412.",
         "Redaction: пароль/токен/cookie/`Authorization` не попадают в логи и spans (golden test).",
         "Config: неизвестный ключ, секрет в env вместо secret file, test-профиль LLM double в local → ошибка старта.",
         "Correlation: входящий traceparent сохраняется; без него генерируется; не используется как авторизация.",
         "Architecture tests проходят и падают на намеренном нарушении."],
  ecc=py([E_FA, E_SEC, E_TYPE], [S_ERR, S_API], [C_FAR, C_SR]), adrs=["ADR-001", "ADR-002", "ADR-005", "ADR-008", "ADR-025", "ADR-026", "ADR-027", "ADR-032"],
  decide=["Библиотеки логирования и architecture-test инструмента.", "Точная форма cursor и коды ошибок пагинации (в пределах DOC-006 §16)."],
  docs=["LOCAL_DEVELOPMENT.md", "TEST_STRATEGY.md (если появились новые типы тестов)"],
  dod=["`make backend-check` (ruff, mypy --strict, pytest) зелёный.", "Все перечисленные negative tests присутствуют и проходят.", "Redaction доказана тестом.", "Нет доменной логики-заглушки, выдаваемой за реализацию."]),

 dict(id="S03", slug="local_infrastructure_secrets_ci", title="Local infrastructure (Docker Compose), secrets и CI baseline", spec="— (DOC-015; добавлено ADR-010)", phase="A. Foundation",
  deps=["S02"], gate="READY", blockers=[], reqs=["INF-MVP-001..041", "SEC-MVP (secrets)"],
  goal="Воспроизводимый локальный стек с pinned digests, сетевой сегментацией и Compose secrets; CI, исполняющий backend и contract checks.",
  refs=[R(INF, "§2, §3, §4, §5, §6 Состав Docker Compose, §9 Сетевая архитектура, §11, §12, §14, §17"), R(SK, "§2–§4, §7, §8"), R(SEC, "§2 (сегментация)"), R(OBS, "§4 Стек MVP"), "`.claude/rules/security.md` — «Секреты»"],
  scope=["`infra/compose.yaml` (+ `compose.dev.yaml`, `compose.test.yaml`): reverse proxy Caddy (ADR-020), api, postgres 16 (ai_res_db + temporal_db), temporal server + schema setup job (ADR-028), temporal-ui (admin network), minio (+ init job), otel-collector. Manager/Worker runtime services — заготовки только когда появится код (S11/S23), не пустые контейнеры.",
         "Все образы по digest; запрет `latest` проверяется скриптом.",
         "Сети: ingress/app/data/egress/admin; наружу опубликован только Caddy.",
         "Секреты: SOPS/age в `infra/secrets/encrypted/`, Compose secrets; генерация dev-секретов скриптом без default credentials; `.env.example` без значений-секретов.",
         "Dockerfile backend (non-root, pinned base digest), `.dockerignore`.",
         "CI: lint, types, unit, contracts, Testcontainers integration (Docker), compose config validation, image digest check.",
         "Release Manifest заготовка (DOC-015 §12) — формат."],
  out=["Prometheus/Loki/Tempo/Grafana (S13).", "Backup/pgBackRest (S32/S38).", "Bifrost (S16)."],
  deliverables=["`infra/**`", "Dockerfile", "CI workflow", "`docs/runbooks/local-stack.md`", "S03 report"],
  tests=["`docker compose config` валиден; скрипт падает на `latest`/отсутствии digest.",
         "Только порт Caddy опубликован на host (проверка `docker compose ps`/inspect).",
         "Секрет не присутствует в image layers, env, логах (скан).",
         "Health: postgres, temporal, minio, api достигают healthy; temporal schema job идемпотентен при повторном запуске.",
         "MinIO console и Temporal UI недоступны из ingress-сети."],
  ecc=ecc([E_SEC, E_BUILD], [S_PA], [C_SR]), adrs=["ADR-005", "ADR-020", "ADR-028"],
  decide=["Точные версии/digest всех образов.", "Схема генерации dev-секретов.", "DevOps-агент в ECC отсутствует — дополнительная проверка `security-reviewer` + `architect` (зафиксировать в ECC_USAGE.md)."],
  docs=["LOCAL_DEVELOPMENT.md", "RELEASE_AND_VERSIONING.md", "`docs/runbooks/`"],
  dod=["`make up` поднимает стек из чистого клона; `make down` чистит.", "Негативные проверки сегментации и секретов проходят.", "CI исполняет все проверки S01–S03."]),

 dict(id="S04", slug="persistence_foundation", title="Persistence foundation: Alembic, schemas, роли", spec="Spec Add. v1.18–v1.19; Blueprint §14 шаги 1–3, 5 (частично)", phase="B. Persistence & Identity",
  deps=["S03"], gate="PENDING_DEPS", blockers=[], reqs=["PERSIST-001, -002 и ролевые PERSIST-*", "DBM-*"],
  goal="Alembic environment со schema allowlist, отдельный migration job, PDB-0001 (schemas, owner/migrator/runtime роли, grants), engine/session/tenant context.",
  refs=[R(BP, "§2, §3, §4 Alembic configuration contract, §5 (PDB-0001), §7, §8, §9, §10, §14"), R(MIG, "§1, §2 Ролевая модель, §3, §4, §6"), R(RLS, "весь файл (адаптировать)"), R(PM, "§3, §10"), R(IAM, "Дополнение 1.2, v1.3"), R(SK, "§4"), "`.claude/rules/database-and-migrations.md`"],
  scope=["Pinned SQLAlchemy 2.x, Alembic, psycopg 3 (async), Testcontainers.",
         "`backend/alembic.ini`, `src/ai_res/db/migrations/env.py`: allowlist доменных schemas (ADR-014), `platform.alembic_version`, named constraints convention, statement/lock timeouts.",
         "PDB-0001: создание schemas, ролей по ADR-015 (`ai_res_owner` NOLOGIN, migrator, api, outbox_dispatcher, event_consumer, auditor, backup; `*_group`), default privileges; без DDL/BYPASSRLS/TRUNCATE у runtime.",
         "Migration job — отдельная Compose-служба/команда; запуск из API startup запрещён и проверяется тестом.",
         "`db/engine.py`, `session.py`, `tenant_context.py` (SET LOCAL после авторизации, reset при возврате в pool), Unit of Work.",
         "Design snapshot `schema_snapshot.sql` + drift check."],
  out=["Доменные таблицы (S05–S06)."],
  deliverables=["Alembic env", "PDB-0001 revision", "db infrastructure", "integration tests", "S04 report"],
  tests=["PERSIST-001 upgrade from empty до head.", "Runtime роли: CREATE TABLE/ALTER/DROP/TRUNCATE → permission denied; нет SUPERUSER/BYPASSRLS (catalog query).",
         "Migrator-only DDL.", "Allowlist: Alembic не видит/не трогает `temporal`/`langgraph` schemas.", "API startup не выполняет миграции (тест на отсутствие вызова).",
         "Tenant context: без SET LOCAL контекст пуст; после commit/rollback и возврата соединения в pool контекст отсутствует."],
  ecc=py([E_DB, E_SEC], [S_PG, S_MIG], [C_SR]), adrs=["ADR-003", "ADR-011", "ADR-014", "ADR-015"],
  decide=["Формат snapshot/drift check.", "Конкретные timeouts миграций (технические значения, не SLO)."],
  docs=["LOCAL_DEVELOPMENT.md (migrate)", "`docs/runbooks/migrations.md`"],
  dod=["PERSIST-тесты этапа проходят на PostgreSQL 16 (Testcontainers).", "Grants audit автоматизирован в CI.", "`.claude/rules/database-and-migrations.md` согласован с ADR-015."]),

 dict(id="S05", slug="core_tenant_execution_schema_rls", title="Core tenant и execution schema + RLS", spec="Blueprint §5 PDB-0002…0007, 0009, 0010 (greenfield ADR-011); Spec Add. v1.17", phase="B. Persistence & Identity",
  deps=["S04"], gate="PENDING_DEPS", blockers=[], reqs=["DATA-MVP", "PERSIST-001..024", "TX-01..TX-09 (persistence части)"],
  goal="Таблицы iam/organization/project/work/operations/agents/execution/audit/platform с ограничениями целостности, sequences, outbox/inbox/idempotency, RLS ENABLE+FORCE и полным PERSIST acceptance suite.",
  refs=[R(DM, "§5, §11, §13, §14, §15, §16, §17; Дополнения v1.3–v1.9"), R(PM, "§3–§9, §11, §12"), R(DDL, "весь файл (design snapshot, WORKING)"), R(BP, "§5, §7, §9, §12, §14"), R(ORG, "§2, §3, §5; Дополнения v1.2–v1.6"), R(EM, "§8, §9, §10"), R(RLS, "весь файл"), R(SM, "статусы Operation/WorkerRun/Gate")],
  scope=["iam: users, credentials (Argon2id hash поля), sessions, mfa, service_identities; organization: organizations, memberships; project: projects, project_memberships.",
         "work: epics, tasks (`operation_id NOT NULL`, `UNIQUE(operation_id,id)`, ADR-011/012), task_dependencies (ADR-016).",
         "operations: operation_types (ADR-013), operations, operation_events (append-only, `UNIQUE(aggregate_id,sequence)`).",
         "agents: worker_runs (composite FK на work.tasks, `started_with_readiness_evaluation_id` immutable), worker_run_events, worker_results (immutable, ADR-016).",
         "execution: readiness_evaluations, readiness_check_results (composite FK, immutable).",
         "audit: outbox_events, inbox_messages, audit_events (ADR-016); platform: idempotency_records (HMAC digest + key_id, ADR-024).",
         "Sequence allocation под row lock/CAS (запрет MAX()+1); `row_version` optimistic concurrency.",
         "RLS ENABLE+FORCE на tenant tables, default deny без контекста; grants по ADR-015.",
         "Immutability triggers/constraints для immutable записей.",
         "Repositories для этих агрегатов (без HTTP)."],
  out=["requirements/sources/artifacts/context/decisions/traceability (S06).", "HTTP endpoints."],
  deliverables=["Alembic revisions", "repositories", "PERSIST suite", "S05 report"],
  tests=["PERSIST-001..024 (Blueprint §12) — все Required.", "Tenant A/B isolation под реальными runtime ролями.", "Missing context default-deny; pooled context reset.",
         "Task без operation_id; WorkerRun с task из другой Operation → отклонение.", "Параллельная аллокация sequence без дублей/дыр (concurrency test).",
         "Попытка UPDATE/DELETE immutable worker_results/readiness_evaluations/event history → отклонение.", "Projection+event+outbox атомарность: сбой между шагами → ни одной записи.",
         "Upgrade from previous revision; RLS coverage check (все tenant tables покрыты)."],
  ecc=py([E_DB, E_SEC, E_TYPE], [S_PG, S_MIG], [C_SR]), adrs=["ADR-011", "ADR-012", "ADR-013", "ADR-014", "ADR-015", "ADR-016", "ADR-023", "ADR-024", "ADR-030"],
  decide=["Физические детали таблиц, не заданные DDL v1.0 (ADR этапа на каждое отклонение)."],
  docs=["CONTRACT_TRACEABILITY_MAP.md (таблицы)", "KNOWN_GAPS.md (G-02, G-10)", "decisions/NORMATIVE_CHANGE_PROPOSALS.md (NCP-02 детали)"],
  dod=["PERSIST-001..024 зелёные.", "RLS coverage = 100% tenant tables.", "Schema drift = 0 относительно snapshot."]),

 dict(id="S06", slug="domain_content_schema", title="Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules", spec="— (DOC-005; ADR-016)", phase="B. Persistence & Identity",
  deps=["S05"], gate="PENDING_DEPS", blockers=[], reqs=["DATA-MVP", "UX-REQ/UX-SRC/UX-ART (данные)", "RULE-MVP-02"],
  goal="Физическая модель контентных bounded contexts с immutable versions, provenance и RLS.",
  refs=[R(DM, "§6 Требования, §7 Источники и знания, §8 Решения и неопределённость, §9 Артефакты и governance, §10 Трассируемость, §11 Агентное исполнение и контекст, §12, §15–§19"), R(RL, "§13–§16"), R(SC, "§3, §6"), R(DAL, "§3, §6, §10"), R(TDI, "§3–§5"), R(DAR, "типизированные объекты"), R(AC, "§15 (Rules Registry)"), R(MVP, "Дополнение v0.8 (RULE-MVP)")],
  scope=["requirements: requirements, requirement_versions (immutable, статусы DOC-003, type registry + UNKNOWN).",
         "sources: sources, uploads, source_versions (immutable, checksum, MinIO key), extraction_records.",
         "artifacts: artifacts, artifact_versions (immutable), validation_reports, reviews, approvals, publications (раздельные факты).",
         "context: context_packages, context_package_versions (immutable, refs).",
         "decisions: decisions, assumptions, risks, issues, unknowns, hypotheses, conflicts — отдельные таблицы (DOC-051).",
         "traceability: traceability_links (type registry), link-type registry; специализированные таблицы Task–Requirement, ArtifactVersion–ValidationReport.",
         "governance: baselines, baseline_items (immutable), change_requests (структура; lifecycle — S31).",
         "rules: rules, rule_versions (RULE-MVP-02 поля).",
         "Current-version pointers с транзакционным переключением; RLS FORCE; repositories."],
  out=["Бизнес-процессы над этими данными (S09, S26–S31)."],
  deliverables=["Alembic revisions", "repositories", "integration tests", "S06 report"],
  tests=["Immutable versions: UPDATE содержимого утверждённой версии → отклонение.", "Неизвестный requirement type → UNKNOWN, не ближайший тип.", "object_type/link_type вне registry → отклонение.",
         "RLS isolation для всех новых tenant tables.", "Baseline items не изменяются после создания.", "Upgrade from previous revision без потери данных."],
  ecc=py([E_DB, E_TYPE], [S_PG, S_MIG], []), adrs=["ADR-014", "ADR-016", "ADR-018"],
  decide=["Физическое представление каждого объекта DOC-005 §6–§12 (ADR этапа)."],
  docs=["CONTRACT_TRACEABILITY_MAP.md", "REQUIREMENTS_TRACEABILITY.md"],
  dod=["Все тесты зелёные; RLS coverage 100%; drift = 0."]),

 dict(id="S07", slug="identity_auth_policy_audit_idempotency", title="Identity, Local Auth, Policy Engine, Audit, Idempotency", spec="Spec Inc. 2 п.6–9 (реализация); Add. v1.3 §3.1", phase="B. Persistence & Identity",
  deps=["S05"], gate="PENDING_DEPS", blockers=[], reqs=["AUTH-001..013", "AUTH-MVP-*", "SEC-001..035 (P0 части)", "SEC-MVP-*"],
  goal="Local authentication MVP, opaque server-side sessions, CSRF, privileged TOTP MFA, bootstrap admin, Policy & Permission Engine (deny-by-default), fail-closed audit writer, idempotency service.",
  refs=[R(AUTH, "§1–§6, §8, §9, §10, §11, §12"), R(IAM, "§2–§8, §10"), R(SECR, "§2, §3, Дополнение v1.1 (AUTH-001…013)"), R(SEC, "§2"), R(SK, "§3, §4, §7"), R(THR, "§5 (сценарии для auth/ACL)"), R(API, "§6; Дополнение v1.7"), R(EM, "§10")],
  scope=["Argon2id (параметры конфигурируемы), минимальная длина 15, local denylist; login rate limiting/lockout по DOC-023 §4.",
         "Sessions в PostgreSQL: opaque id, rotation после login/MFA/elevation, idle 30 мин / absolute 12 ч (configurable defaults), revoke; cookie `ai_res_session` (имя конфигурируемо, OD-03), HttpOnly/Secure/SameSite=Lax.",
         "CSRF (`X-CSRF-Token`, конфигурируемо) + Origin check для cookie-аутентифицированных state changes; CORS deny-by-default.",
         "TOTP MFA для Organization Owner/Admin, Project Admin; recovery codes (hash).",
         "Bootstrap admin: одноразовая CLI-процедура, секрет из Compose secret, инвалидируется после использования.",
         "Service identities (api/dispatcher/consumer/manager/worker) — отдельные, короткоживущие credentials; браузерные сессии не передаются.",
         "Policy Engine (ADR-017): RBAC+ABAC/ACL, approval-required, reason codes, fail-closed; autonomy A0–A2 enforcement point.",
         "Audit writer: запись в `audit.audit_events` в той же транзакции, сбой → отказ защищённого действия.",
         "Idempotency service: scope `(organization, actor scope, command, key)`, fingerprint, HMAC+key_id, replay, 409 `IDEMPOTENCY_KEY_REUSED`.",
         "`GET /api/v1/me` (getCurrentUser) как первый endpoint по контракту."],
  out=["OIDC adapter (post-MVP, только interface).", "UI логина (S35)."],
  deliverables=["iam/auth/policy/audit/idempotency модули", "endpoints login/logout/me (по контракту; login/logout отсутствуют в OAS v1.3 → NCP-06 или internal auth router по DOC-023 — решить ADR)", "tests", "S07 report"],
  tests=["Stale/revoked/expired session → 401.", "CSRF отсутствует/неверен/чужой Origin → 403.", "Privileged роль без MFA → доступ к privileged действиям запрещён.",
         "Bootstrap secret повторно → отказ; default credentials отсутствуют.", "Policy outage/exception → deny; неизвестное действие → deny.",
         "Audit write failure → защищённое действие откатывается.", "Idempotency: параллельные одинаковые запросы → одна запись; другой fingerprint → 409.",
         "Логи/трейсы не содержат пароль, cookie, TOTP seed, recovery codes (golden test).", "Brute-force: rate limit срабатывает."],
  ecc=py([E_SEC, E_FA, E_DB], [S_ERR], [C_FAR, C_SR]), adrs=["ADR-015", "ADR-017", "ADR-024", "ADR-032"],
  decide=["Маршруты login/logout/MFA/recovery: проектируются в overlay по DOC-023 (ADR-009/ADR-038); зафиксировать ADR этапа.", "Параметры Argon2id (по OWASP, конфигурируемые)."],
  docs=["DECISIONS_PENDING.md (OD-03 статус)", "decisions/NORMATIVE_CHANGE_PROPOSALS.md (NCP-06)"],
  dod=["Все SEC P0 тесты этапа зелёные.", "security-reviewer review без открытых HIGH.", "Policy matrix покрывает все действия, введённые к этому этапу."]),

 dict(id="S08", slug="read_only_api_slices", title="Read-only API vertical slices", spec="Spec Inc. 3", phase="C. Public API & Events",
  deps=["S06", "S07"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP-0xx (read)", "SEC-001/002", "WS-MVP (данные)"],
  goal="GET-операции Public API v1.3 для Project, Epic, Task, Requirement(+versions), Source, Artifact(+versions), WorkerRun с ACL, cursor pagination, ETag и DTO mapping.",
  refs=[R(SPEC, "§4 Increment 3; §5"), R(OAS, "GET operations: listProjects, getProject, listEpics, getEpic, listTasks, getTask, listRequirements, listRequirementVersions, listSources, listArtifacts, listArtifactVersions, getWorkerRun"), R(API, "§3, §5, §6"), R(IAM, "§7, §10"), R(SECR, "SEC-001, SEC-002")],
  scope=["Handlers + application query services + explicit DTO mappers; ORM-сущности не возвращаются.", "ACL server-side на каждый запрос; cross-project → controlled 404.", "Cursor pagination со stable ordering, без counts недоступных объектов.", "ETag там, где объявлен в OAS.", "Contract tests (schemathesis) против `contracts/openapi`."],
  out=["Записи (S09).", "Operations/SSE (S12)."],
  deliverables=["read endpoints", "contract & authorization tests", "S08 report"],
  tests=["IDOR: доступ к объекту другого проекта/организации → 404 без утечки (тот же ответ, что и несуществующий).", "List не содержит недоступных объектов; cursor другого пользователя отклоняется.",
         "Ответы соответствуют OAS (schemathesis, все GET).", "ETag меняется при изменении row_version.", "Revoked membership → немедленный отказ."],
  ecc=py([E_FA, E_SEC, E_TYPE], [S_CF, S_API], [C_FAR, C_SR]), adrs=["ADR-008", "ADR-033"],
  decide=["Фильтры list-операций в пределах OAS."], docs=["CONTRACT_TRACEABILITY_MAP.md (статусы строк)", "REQUIREMENTS_TRACEABILITY.md"],
  dod=["Все GET из scope соответствуют OAS и проходят ACL-тесты.", "Ни один endpoint вне контракта не создан."]),

 dict(id="S09", slug="controlled_write_commands", title="Controlled write commands", spec="Spec Inc. 4", phase="C. Public API & Events",
  deps=["S08"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP (writes)", "PROC-MVP (intake/regist.)", "UX-SRC (upload)"],
  goal="createProject, updateProjectMetadata, createEpic, createTask (ADR-012), registerRequirementCandidate, proposeRequirementVersion, createUploadIntent с доменными сервисами, транзакциями, If-Match, idempotency, audit и outbox records.",
  refs=[R(SPEC, "§4 Increment 4"), R(OAS, "POST/PATCH операции кроме 202-операций"), R(API, "§3, §5; Дополнение v1.7"), R(PM, "§8 Транзакционные алгоритмы (TX-01, TX-02)"), R(EM, "§8"), R(RL, "§13, §14, §16"), R(SC, "§5, §13 (upload безопасность)"), R(ORG, "Дополнение v1.2")],
  scope=["Domain/application services; транзакция: projection + aggregate event + outbox.", "createTask → Task + root Operation `TASK_EXECUTION` (ACCEPTED) + outbox command (ADR-012); proposal-режим по полномочиям.",
         "RequirementVersion — immutable proposals (CANDIDATE), не approval.", "Upload intent: short-lived, object-scoped presigned URL MinIO, ограничение content-type/size.",
         "Idempotency-Key обязателен на side-effecting POST; If-Match на version-sensitive.", "Audit для всех state changes."],
  out=["completeUpload (202, S12).", "sendManagerMessage (S20).", "Approval переходы (S26)."],
  deliverables=["write endpoints", "domain services", "tests", "S09 report"],
  tests=["Idempotent retry без дублей (параллельно).", "Тот же key, другой body → 409.", "Stale If-Match → 412.", "createTask: ровно одна Operation; Task без Operation невозможна.",
         "Попытка изменить утверждённую версию → отказ.", "CSRF/ACL negative.", "Rollback при сбое outbox insert → нет ни Task, ни события.", "Upload URL: истечение, чужой проект, превышение размера."],
  ecc=py([E_FA, E_SEC, E_DB], [S_CF, S_ERR], [C_FAR, C_SR]), adrs=["ADR-012", "ADR-013", "ADR-024"],
  decide=["Структура domain events payload в пределах AsyncAPI (без контента)."], docs=["CONTRACT_TRACEABILITY_MAP.md", "REQUIREMENTS_TRACEABILITY.md"],
  dod=["Все write операции scope соответствуют OAS и проходят negative suite.", "Outbox записи создаются атомарно (доставка — S10)."]),

 dict(id="S10", slug="outbox_dispatcher_inbox_cloudevents", title="Outbox dispatcher, Inbox и CloudEvents", spec="Spec Inc. 8 (часть: Outbox/CloudEvents/Inbox/DLQ)", phase="C. Public API & Events",
  deps=["S09"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP (events)", "REL-* (delivery)", "TX-* (outbox)"],
  goal="Надёжная at-least-once доставка доменных событий с lease, per-aggregate ordering, bounded retry, quarantine и идемпотентными consumers.",
  refs=[R(EM, "§4, §8, §9 Outbox, Inbox, доставка и порядок, §10, §12, §13, §15, §17"), R(ASY, "envelope, сообщения"), R(PM, "§8, §9"), R(API, "§13 Domain event contract"), R(RR, "§1")],
  scope=["Dispatcher process (identity `ai_res_outbox_dispatcher`): lease без удержания DB lock во время network call, backoff+jitter, quarantine, controlled replay.", "CloudEvents 1.0 envelope; тот же event_id при retry.",
         "Inbox `(consumer_name,event_id)` + sequence checkpoint, gap → defer.", "Unknown major event type → quarantine + alert metric.", "Validation event payload против AsyncAPI schemas; запрет контента в payload."],
  out=["Внешние брокеры (RabbitMQ/Kafka запрещены в MVP).", "Temporal start (S11)."],
  deliverables=["dispatcher", "inbox library", "tests", "S10 report"],
  tests=["Crash after commit-before-publish → доставка после recovery.", "Crash after publish-before-mark → duplicate → consumer no-op.", "Out-of-order/gap → defer, не skip.", "Poison event → quarantine, поток не блокируется.",
         "Concurrent dispatchers не публикуют одно событие одновременно в нарушение порядка.", "Payload privacy: тест на отсутствие запрещённых полей."],
  ecc=py([E_DB], [S_ERR], []), adrs=["ADR-023", "ADR-025", "ADR-030"], decide=["Lease/backoff значения как конфигурация (WORKING; задать технические defaults и отметить WORKING)."],
  docs=["`docs/runbooks/outbox.md`"], dod=["Все тесты доставки зелёные на PostgreSQL.", "Exactly-once нигде не заявлен."]),

 dict(id="S11", slug="temporal_foundation_operation_dispatch", title="Temporal foundation и dispatch Operation", spec="Spec Inc. 7 (часть: Temporal), Inc. 5 (часть: start)", phase="C. Public API & Events",
  deps=["S10"], gate="PENDING_DEPS", blockers=[], reqs=["INF-MVP-002", "PROC-MVP (durable execution)"],
  goal="Manager и Worker Runtime процессы (task queues `ai-res-manager`, `ai-res-workers`), детерминированный Operation workflow skeleton, идемпотентный старт из Outbox, replay-тесты. WorkerRun не исполняется.",
  refs=[R(INF, "§3, §4"), R(API, "§9 Temporal contracts"), R(ORG, "§2, §4, §5"), R(PD, "§2, §13"), R(SPEC, "§4 Increment 7; Add. v1.13 п.2, 14")],
  scope=["Temporal client adapter в API/dispatcher; stable Workflow ID из Operation ID.", "Manager Runtime процесс (без DB credentials) — Activities вызывают Application Services через internal API/service identity.",
         "Worker Runtime процесс — только регистрация, без исполнения WorkerRun до S23.", "Компактные refs в history; запрет документов/промптов/секретов.", "Replay test harness; versioning стратегия workflow."],
  out=["LangGraph и WorkerRun (S23).", "Cancellation (S12)."],
  deliverables=["runtime processes", "workflow skeleton", "Compose services", "tests", "S11 report"],
  tests=["Duplicate outbox delivery → один workflow.", "Activity retry не создаёт новую Operation.", "Replay сохранённых histories без non-determinism.", "History не содержит запрещённых данных (scan).", "Manager/Worker контейнеры не имеют DB secrets и сетевого доступа к PostgreSQL."],
  ecc=py([E_DB, E_SEC], [S_ERR], [C_SR]), adrs=["ADR-028", "ADR-010"], decide=["Internal API между runtime и Application Services (транспорт/аутентификация) — ADR этапа.", "Workflow versioning стратегия.", "Temporal/LangGraph специалиста в ECC нет — компенсировать `architect` + `silent-failure-hunter` (ECC_USAGE.md)."],
  docs=["`docs/runbooks/temporal.md`"], dod=["Replay и идемпотентность доказаны тестами с реальным Temporal (test server или Compose)."]),

 dict(id="S12", slug="operation_api_process_primitives_sse", title="Operation API, process primitives, cancellation, SSE", spec="Spec Inc. 5; Add. v1.1 Inc. 10; Add. v1.13, v1.15", phase="C. Public API & Events",
  deps=["S11"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP (async ops)", "PROC-MVP", "UX-DUR"],
  goal="Operation resource (GET, cancel), state machine с валидацией переходов, детерминированный aggregator, 202+Location, completeUpload, SSE из event history с ACL.",
  refs=[R(SM, "Operation states/transitions, aggregation rules"), R(ORG, "§2; Дополнение v1.2"), R(EM, "§5, §11, §12"), R(API, "§4; Дополнения v1.3–v1.5"), R(OAS, "getOperation, requestOperationCancellation, streamProjectEvents, completeUpload"), R(PD, "§3, §13, §14"), R(SPEC, "Add. v1.15")],
  scope=["Typed transitions Operation (terminal не переоткрывается), aggregator по критериям, не по счётчикам.", "Cancellation: request → stop/cleanup → reconciliation → terminal.", "completeUpload: checksum verify → Operation `SOURCE_INGESTION` (202).",
         "SSE (ADR-033) с Last-Event-ID, retention gap сигнал.", "Operation Events history API не создаётся (DOC-055 §2.6)."],
  out=["WorkerRun lifecycle (S23)."], deliverables=["operation module", "SSE", "tests", "S12 report"],
  tests=["Exhaustive transition tests (hypothesis stateful).", "Cancel race с завершением → reconciliation, не blind CANCELLED.", "SSE reconnect: недоступные события не отдаются; gap сигнализируется.", "Upload checksum mismatch → отказ.", "202 + Location; GET не опрашивает Temporal."],
  ecc=py([E_FA, E_SEC, E_TYPE], [S_CF], [C_FAR, C_SR]), adrs=["ADR-012", "ADR-013", "ADR-033"], decide=["Детали aggregator policy snapshot."],
  docs=["CONTRACT_TRACEABILITY_MAP.md"], dod=["State machine покрыта полностью; SSE ACL доказан."]),

 dict(id="S13", slug="observability_stack", title="Observability stack и мониторинг", spec="— (DOC-024/025/026; ADR-025)", phase="C. Public API & Events",
  deps=["S03", "S10"], gate="PENDING_DEPS", blockers=[], reqs=["OBS-MON-*", "OBS-SEC-*", "OBS-ALR-*"],
  goal="OTel Collector → Prometheus, Loki, Tempo, Grafana; redaction до экспорта; dashboards и alert rules без изобретённых порогов.",
  refs=[R(OBS, "§3–§9, §12"), R(MON, "OBS-MON, OBS-SEC, OBS-ALR"), R(AOE, "§2–§4"), R(INF, "§10")],
  scope=["Compose services (pinned digests), admin-сеть.", "Collector pipelines: redaction/filter до экспорта; high-cardinality IDs не в labels.", "Dashboards: API, outbox, Temporal, PostgreSQL.", "Alert rules как код; числовые пороги — конфигурация с пометкой WORKING (OD-02).", "Потеря telemetry не останавливает домен; audit — отдельный контур."],
  out=["Langfuse (выключен).", "PagerDuty (post-MVP)."], deliverables=["infra/observability/**", "tests", "S13 report"],
  tests=["Redaction в collector: синтетический секрет не доходит до Loki/Tempo.", "Label cardinality lint.", "Отключение observability backend не ломает API.", "Audit не зависит от telemetry."],
  ecc=ecc([E_SEC], [S_PA], [C_SR]), adrs=["ADR-025"], decide=["Набор метрик/дашбордов в пределах DOC-025."], docs=["`docs/runbooks/observability.md`"],
  dod=["Redaction и degradation доказаны тестами."]),

 dict(id="S14", slug="worker_contracts_runtime_validation", title="Worker contracts: Envelope/Result/Notice", spec="Spec Inc. 6", phase="D. Agent execution",
  deps=["S12"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP (internal contracts)", "PROC-MVP"],
  goal="Typed WorkerRunEnvelope/WorkerResult/WorkerNotice с валидацией в 4 точках и fail-closed для unknown major.",
  refs=[R(WC, "весь файл (WORKING)"), R(API, "§7, §8 Manager–Worker contract, §15"), R(SPEC, "§4 Increment 6"), "`.claude/rules/api-and-contracts.md` — WorkerRunEnvelope"],
  scope=["Pydantic модели из JSON Schema (генерация после валидации S01) + runtime JSON Schema validation.", "Точки: enqueue / перед исполнением / при получении результата / перед downstream consumption.", "Персистенция WorkerResult только через Application Service (immutable).", "Маркировка WORKING (ADR-021)."],
  out=["Исполнение WorkerRun (S23)."], deliverables=["worker_contracts module", "tests", "S14 report"],
  tests=["Unknown major → reject во всех 4 точках.", "Лишние/недостающие поля → reject.", "WorkerResult без evidence refs/с секретом → reject.", "Попытка повторно сохранить/изменить WorkerResult → отказ."],
  ecc=py([E_TYPE], [S_CF], []), adrs=["ADR-021"], decide=["Изменения полей → NCP-04."], docs=["decisions/NORMATIVE_CHANGE_PROPOSALS.md (NCP-04)"], dod=["4 точки валидации покрыты тестами."]),

 dict(id="S15", slug="llm_gateway_port_model_registry", title="LLMGatewayPort и Model Registry (провайдер-нейтрально)", spec="Spec Add. v1.20 Inc. 20 (часть)", phase="D. Agent execution",
  deps=["S11"], gate="PENDING_DEPS", blockers=[], reqs=["API-MVP (LLM adapter)", "SEC (LLM)"],
  goal="Единственный путь к LLM: port, Model Registry, routing policy, budgets, failure semantics, deterministic test double.",
  refs=[R(MG, "§1–§6, §8"), R(API, "§11 LLM Gateway Adapter contract"), R(ACB, "§3"), "`.claude/rules/architecture-constraints.md` — «LLM доступ»"],
  scope=["`LLMGatewayPort` (chat/structured/embedding), Model Registry (профили, версии, статус approval), budget enforcement вне модели.", "DeterministicLLMGateway только в `test` профиле (ADR-022).", "Redaction промптов из telemetry; секреты не попадают в контекст.", "Architecture test: provider SDK импортируется только в adapter-пакетах."],
  out=["Реальный провайдер и Bifrost (S16)."], deliverables=["llm_gateway module", "model registry tables (revision)", "tests", "S15 report"],
  tests=["Неутверждённый профиль → отказ.", "Budget exhausted → typed error, без retry.", "Test double в local профиле → ошибка запуска.", "Секрет в prompt input → блок/redaction."],
  ecc=py([E_SEC], [S_ERR], [C_SR]), adrs=["ADR-022", "ADR-031"], decide=["Схема Model Registry записей."], docs=[], dod=["Нет прямых provider вызовов (architecture test)."]),

 dict(id="S16", slug="bifrost_poc_provider_profile", title="Bifrost PoC и первый утверждённый provider profile", spec="Spec Add. v1.20 Inc. 20 (часть)", phase="D. Agent execution",
  deps=["S15", "S13"], gate="BLOCKED", blockers=["OD-01 (провайдер/модель и разрешение на передачу данных проекта внешнему провайдеру)"], reqs=["DOC-076 §7 acceptance"],
  goal="PoC Bifrost за `LLMGatewayPort` по DOC-076 §7, security review, один утверждённый model profile для первого vertical slice.",
  refs=[R(MG, "§2, §5, §6, §7 Bifrost acceptance PoC, §8"), R(INF, "§8 LLM Gateway"), R(SEC, "egress"), R(THR, "§5 (LLM/egress сценарии)")],
  scope=["Bifrost в Compose (pinned), egress allowlist только к утверждённому провайдеру.", "Adapter; streaming/tool-calling совместимость с LangGraph; failure semantics.", "Security review и отчёт PoC; production-like профиль остаётся заблокирован до acceptance."],
  out=["Несколько провайдеров/маршрутизация сверх одного профиля."], deliverables=["PoC report в reviews/", "adapter", "S16 report"],
  tests=["PoC критерии DOC-076 §7.", "Egress к неразрешённому хосту блокируется.", "Admin Bifrost не доступен из ingress."],
  ecc=py([E_SEC], [], [C_SR]), adrs=["ADR-031"], decide=["По итогам PoC — ACCEPT/REJECT Bifrost (решение владельца/security owner)."], docs=["DECISIONS_PENDING.md (OD-01)"], dod=["PoC критерии подтверждены; security review без открытых HIGH; решение владельца зафиксировано."]),

 dict(id="S17", slug="tool_registry_tool_gateway", title="Tool Registry и Tool Gateway", spec="Spec Add. v1.20 Inc. 23", phase="D. Agent execution",
  deps=["S07", "S12"], gate="PENDING_DEPS", blockers=[], reqs=["TR MVP §9", "SEC (tools)"],
  goal="Typed tool contracts, версии, per-call Policy authorization, side-effect классификация, MCP allowlist adapter (выключен по умолчанию).",
  refs=[R(TR, "§3, §4 Обязательный поток вызова, §5, §6, §7, §9, §13, §16"), R(ACB, "§5"), R(IAM, "§6 Worker Run grants")],
  scope=["Tool Registry записи/версии; ролевые наборы инструментов Workers (§13).", "Tool Gateway: валидация входа/выхода, policy per call, audit, timeout, idempotency для side effects.", "MCP только allowlisted adapter; Code Mode/runtime code generation — вне MVP."],
  out=["Конкретные внешние интеграции (S29)."], deliverables=["tools module", "tests", "S17 report"],
  tests=["Tool без grant → deny.", "Схема входа нарушена → reject до вызова.", "Revoked grant между вызовами → deny.", "Неаллоулистный MCP сервер → отказ."],
  ecc=py([E_SEC], [S_ERR], [C_SR]), adrs=["ADR-017"], decide=["MVP tool catalogue из §10 (какие инструменты реализуются в каком этапе)."], docs=[], dod=["Per-call authorization доказана."]),

 dict(id="S18", slug="rules_registry_rules_engine", title="Rules Registry и Rules Engine", spec="— (RULE-MVP; ADR-018)", phase="D. Agent execution",
  deps=["S07", "S06"], gate="PENDING_DEPS", blockers=[], reqs=["RULE-MVP-01..14"],
  goal="Версионируемые системные/организационные/проектные правила с lifecycle и детерминированным вычислением применимых правил.",
  refs=[R(AC, "§15 Архитектура управления правилами"), R(MVP, "Дополнения v0.7, v0.8 (RULE-MVP-01..14)"), R(IAM, "§2")],
  scope=["Registry: ID, версия, уровень, область, условие, действие, статус, автор, утверждающий, сроки.", "Иерархия: нижние уровни не ослабляют системные.", "Неутверждённые правила не применяются; исключения — human approval, ограничены сроком.", "Engine: детерминированный результат со структурой (DOC-009 v0.8 «Структурированный результат»)."],
  out=["UI управления правилами (S36)."], deliverables=["rules module", "tests", "S18 report"],
  tests=["Проектное правило не может ослабить системное.", "DRAFT правило не применяется.", "Истёкшее исключение не действует.", "Детерминизм: одинаковый вход → одинаковый результат."],
  ecc=py([E_TYPE], [], []), adrs=["ADR-018"], decide=["Язык условий правил (безопасный, без eval)."], docs=[], dod=["Критерии RULE-MVP покрыты тестами."]),

 dict(id="S19", slug="context_package_versioning", title="ContextPackageVersion (минимальный Context Builder)", spec="Spec Add. v1.20 Inc. 22 (часть)", phase="D. Agent execution",
  deps=["S06", "S07"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP (immutable context)", "Context Builder критерии DOC-009 v0.4"],
  goal="Immutable ContextPackageVersion из явных versioned refs с ACL-проверкой при сборке; основа для Readiness Gate.",
  refs=[R(KMR, "§5 Context engineering"), R(SC, "§9"), R(DM, "§11"), R(MVP, "Дополнение v0.4 (Context Builder)")],
  scope=["Сборка пакета из explicit refs (Requirement/Source/Artifact versions), хэш, provenance.", "ACL до включения; секреты не включаются.", "Пакет immutable; обновление источника → новый пакет."],
  out=["Retrieval/ranking (S28)."], deliverables=["context module", "tests", "S19 report"],
  tests=["Ref недоступного проекта → отказ сборки.", "Изменение источника не мутирует существующий пакет.", "Хэш стабилен."],
  ecc=py([E_SEC], [], []), adrs=[], decide=["Формат manifest пакета."], docs=[], dod=["Immutability и ACL доказаны."]),

 dict(id="S20", slug="project_epic_intake_manager", title="Project/Epic intake и Manager interaction", spec="Spec Add. v1.1 Inc. 11", phase="D. Agent execution",
  deps=["S12", "S15", "S19"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP", "UX-START-*", "UX-MVP-*"],
  goal="sendManagerMessage (202 + Operation `MANAGER_MESSAGE`), Manager intake workflow, adaptive question state, proposal persistence, human decision boundary.",
  refs=[R(PD, "§4, §5, §17, §20"), R(UX, "«Создание проекта и первое взаимодействие с Manager»; §5, §8"), R(RL, "§4"), R(AC, "Manager (роль и полномочия)"), R(OAS, "sendManagerMessage"), R(ACB, "§6, §9")],
  scope=["Manager как Temporal workflow + LangGraph (через LLMGatewayPort; test double в тестах).", "Proposal объекты — не решения; human decision boundary.", "Proactive сообщения сгруппированы и rate-limited (configurable).", "Manager Epic state — rebuildable projection."],
  out=["Plan (S21).", "Worker execution (S23)."], deliverables=["manager intake", "tests", "S20 report"],
  tests=["Manager не утверждает требования/решения.", "Prompt injection в сообщении/вложении не исполняется как инструкция.", "Projection rebuild из событий совпадает.", "Idempotency sendManagerMessage."],
  ecc=py([E_SEC], [S_EH], [C_SR]), adrs=["ADR-022", "ADR-029"], decide=["Структура adaptive question state."], docs=[], dod=["Тесты механики зелёные; качество вывода модели помечено как не проверенное до S16."]),

 dict(id="S21", slug="plan_task_orchestration", title="Plan & Task orchestration", spec="Spec Add. v1.1 Inc. 12", phase="D. Agent execution",
  deps=["S20"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP", "UX-PLAN-*"],
  goal="Immutable PlanVersion, PlanItem→Task mapping, dependency graph validation, cycle detection, partial approval, Temporal plan workflow.",
  refs=[R(PD, "§6, §15"), R(UX, "Plan (UX-PLAN)"), R(DM, "§5, §11"), R(SPEC, "Add. v1.1 §4 Plan graph tests")],
  scope=["PlanVersion immutable; approve/reject человеком.", "Graph: cycles, unreachable nodes, partial approval constraints, safe parallel branches.", "Operation `PLAN_EXECUTION`."],
  out=["Gate (S22)."], deliverables=["planning module", "tests", "S21 report"],
  tests=["Cycle detection.", "Unreachable PlanItem.", "Partial approval dependency violation.", "Approval только exact version."],
  ecc=py([E_TYPE], [], []), adrs=["ADR-013"], decide=["Completion policy snapshot формат."], docs=[], dod=["Все plan graph tests зелёные."]),

 dict(id="S22", slug="readiness_gate", title="Readiness Gate", spec="Spec Add. v1.1 Inc. 13; Add. v1.13–v1.14", phase="D. Agent execution",
  deps=["S14", "S17", "S18", "S19", "S21"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP (Gate)", "DOC-055 инварианты"],
  goal="Детерминированный check registry, immutable ReadinessEvaluation + check results, staleness, final pre-start revalidation, fail-closed.",
  refs=[R(ORG, "§3 Решение по Readiness Gate, §5"), R(ORGS, "ReadinessEvaluation"), R(SM, "Gate outcomes"), R(PD, "§7"), R(SPEC, "Add. v1.13 п.6–12; Add. v1.2 п.11"), R(API, "§7 Readiness Gate responsibilities")],
  scope=["Check code registry (implementation registry с ADR; WORKING синхронизация через NCP).", "Snapshot точных версий (Task/Plan/WorkerDefinition/ContextPackage/rules/grants/tools/output/budget/deps).", "READY_WITH_LIMITATIONS материализует ограничения в envelope/grants.", "Manager semantic assessment отделён и не переопределяет deterministic checks.", "listWorkerRunReadinessEvaluations endpoint; события (ADR-023)."],
  out=["Исполнение WorkerRun (S23)."], deliverables=["readiness module", "tests", "S22 report"],
  tests=["Revoked permission, stale context, missing dependency, wrong capability, missing acceptance schema → BLOCKED.", "Evaluator error/policy outage → не READY.", "Final revalidation при изменённых версиях → новая evaluation.", "Попытка старта без evaluation → отказ (DB constraint + сервис)."],
  ecc=py([E_SEC, E_TYPE], [], [C_SR]), adrs=["ADR-023"], decide=["Check code registry и dispatch lease (WORKING → ADR с пометкой, NCP-01)."], docs=["decisions/NORMATIVE_CHANGE_PROPOSALS.md"], dod=["Обход Gate невозможен ни одним путём (тесты на все пути старта)."]),

 dict(id="S23", slug="worker_run_lifecycle_langgraph", title="WorkerRun lifecycle и LangGraph runtime", spec="Spec Inc. 7 (LangGraph), Add. v1.1 Inc. 14, Add. v1.15", phase="D. Agent execution",
  deps=["S22", "S15"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP", "INF-MVP-002"],
  goal="WorkerRun state machine, Temporal schedule/start, LangGraph thread per WorkerRun (checkpoint schema изолирована), WorkerNotice/Result, Manager acceptance, девять логических специализаций в одном пуле.",
  refs=[R(SM, "WorkerRun states"), R(ORG, "Дополнение v1.2"), R(PD, "§8, §9"), R(API, "§8, §9, §10 LangGraph contracts"), R(AC, "Workers (9 специализаций)"), R(SPEC, "Add. v1.15; Add. v1.2")],
  scope=["Worker Runtime исполняет WorkerRun только с started_with_readiness_evaluation_id.", "LangGraph checkpointer в schema `langgraph` (вне Alembic), scope = WorkerRun.", "Worker не имеет DB credentials; результат через Application Service.", "Derived runs: attempt/derivation lineage; Activity retry не создаёт новый WorkerRun.", "Worker Run grants: scoped, TTL, budget."],
  out=["Coordination (S24).", "QA (S25)."], deliverables=["worker runtime", "tests", "S23 report"],
  tests=["Exhaustive WorkerRun transitions.", "Worker пытается писать в domain DB / self-grant / вызвать peer → отказ + audit.", "Prompt injection из source content не исполняется.", "Replay Temporal; cancel/timeout race.", "LangGraph state другого WorkerRun недоступен."],
  ecc=py([E_SEC, E_DB], [S_EH, S_ERR], [C_SR]), adrs=["ADR-021", "ADR-022"], decide=["Структура LangGraph графов специализаций (минимальная для MVP)."], docs=[], dod=["Инварианты Worker isolation доказаны тестами."]),

 dict(id="S24", slug="manager_worker_coordination", title="Manager–Worker coordination", spec="Spec Add. v1.2", phase="D. Agent execution",
  deps=["S23"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP (coordination)"],
  goal="CONSULTATION / DELEGATED_SUBTASK / HANDOFF через WorkerCoordinationRequest → Manager → Policy → Temporal → новый Gate; risk-tier adjudication.",
  refs=[R(SPEC, "Add. v1.2 (все пункты и тесты)"), R(API, "Дополнение «WorkerCoordinationRequest» §1–§7"), R(DM, "WorkerCoordinationRequest §1–§3"), R(RL, "§7.4, §7.5")],
  scope=["Typed requests; каждый derivative run — свой ContextPackageVersion, grants, budget, Gate.", "Risk-tier: ADR-029 default.", "Manager state rebuildable."],
  out=["QA (S25)."], deliverables=["coordination module", "tests", "S24 report"],
  tests=["Все 9 обязательных тестов Spec Add. v1.2."], ecc=py([E_SEC], [], [C_SR]), adrs=["ADR-029"], decide=[], docs=[], dod=["Тесты Add. v1.2 зелёные."]),

 dict(id="S25", slug="independent_qa_rework", title="Independent QA и rework", spec="Spec Add. v1.1 Inc. 15", phase="D. Agent execution",
  deps=["S24"], gate="PENDING_DEPS", blockers=[], reqs=["PROC-MVP (QA)", "UX-RESULT-*"],
  goal="Verification modes, independent QA WorkerRun (blind-first), disagreement handling, rework как новый Run, разделение acceptance/verification/QA/approval.",
  refs=[R(PD, "§9"), R(RL, "§7.6"), R(SPEC, "Add. v1.1 §4 QA tests; Add. v1.2 п.8, 10"), "`.claude/rules/testing-and-verification.md` — «Независимый QA Worker»"],
  scope=["QA = Review + отдельный WorkerRun.", "Blind-first где поддерживается; запись причины, если нет.", "High-risk unresolved → unverified/blocked."],
  out=[], deliverables=["qa module", "tests", "S25 report"],
  tests=["Mandatory QA недоступна → результат unverified.", "Self-assessment не засчитывается как QA.", "Disagreement low/high risk.", "Rework создаёт новый WorkerRun/Result, старый неизменен."],
  ecc=py([], [S_EH], []), adrs=["ADR-029"], decide=[], docs=[], dod=["QA tests зелёные."]),

 dict(id="S26", slug="requirements_lifecycle_approvals_decisions", title="Requirements lifecycle, approvals, decisions & uncertainty", spec="— (DOC-003, DOC-051; ADR-010)", phase="E. Knowledge, Change & Governance",
  deps=["S25"], gate="PENDING_DEPS", blockers=[], reqs=["UX-REQ-*", "UX-DUR-*", "LC-DEC-*", "PROC-MVP"],
  goal="Контролируемые переходы CANDIDATE→CONFIRMED→APPROVED, human approval exact version, качество/конфликты требований, typed Decisions/Assumptions/Risks/Issues/Unknowns/Hypotheses/Conflicts.",
  refs=[R(RL, "§3, §5, §6, §12–§19"), R(DAR, "все типы и lifecycle"), R(IAM, "§8 Approval и separation of duties"), R(UX, "UX-REQ, UX-DUR")],
  scope=["Approval commands только с правом и exact version; не через PATCH статуса.", "Separation of duties.", "Конфликты и автономное разрешение только низкого риска (ADR-029)."],
  out=["Baseline (S31)."], deliverables=["requirements/decisions services + endpoints по контракту (новые — через NCP/контракт)", "tests", "S26 report"],
  tests=["Worker/Manager не может APPROVE.", "Approval stale version → 412/409.", "Неизвестный тип требования → UNKNOWN.", "Separation of duties нарушение → отказ."],
  ecc=py([E_SEC, E_FA], [S_CF], [C_FAR, C_SR]), adrs=["ADR-029"], decide=["Endpoints, отсутствующие в OAS v1.3 → контракт до кода (NCP-06)."], docs=["decisions/NORMATIVE_CHANGE_PROPOSALS.md"], dod=["Нет автоматического approval ни одним путём."]),

 dict(id="S27", slug="knowledge_ingestion_indexing", title="Knowledge ingestion и indexing", spec="Spec Add. v1.20 Inc. 21", phase="E. Knowledge, Change & Governance",
  deps=["S12", "S15"], gate="PENDING_DEPS", blockers=[], reqs=["UX-SRC-*", "KMR §3"],
  goal="Ingestion pipeline для SourceVersion: проверка файла, извлечение, chunking, FTS (tsvector/GIN) + pgvector embeddings, provenance, ACL.",
  refs=[R(KMR, "§2, §3, §6, §7"), R(SC, "§4, §5, §6, §13, §15"), R(ACB, "§4")],
  scope=["Проверка типа/размера/целостности/безопасности до обработки.", "Extraction records с parser version; partial failure не заменяет предыдущую валидную версию.", "Embeddings через LLMGatewayPort.", "Content из источников — недоверенный."],
  out=["Retrieval API (S28)."], deliverables=["ingestion module", "tests", "S27 report"],
  tests=["Duplicate ingestion → нет дубля SourceVersion.", "Parser version change → новый ExtractionRecord.", "Partial index failure.", "Вредоносный файл/zip bomb отклоняется."],
  ecc=py([E_RAG, E_SEC, E_DB], [S_PG], [C_SR]), adrs=[], decide=["Chunking/форматы (WORKING лимиты — конфигурация)."], docs=[], dod=["Тесты Source Add. v1.1 §4 зелёные."]),

 dict(id="S28", slug="retrieval_api_context_builder", title="Retrieval API и полный Context Builder", spec="Spec Add. v1.20 Inc. 22", phase="E. Knowledge, Change & Governance",
  deps=["S27", "S19"], gate="PENDING_DEPS", blockers=[], reqs=["KMR §4–§5", "Context Builder критерии"],
  goal="Hybrid retrieval (FTS + pgvector) с ACL до retrieval/rerank/cache/export; Context Builder формирует immutable пакеты.",
  refs=[R(KMR, "§4, §5, §8"), R(MVP, "Дополнение v0.4"), R(SECR, "SEC-002")],
  scope=["ACL filter в запросе, не post-filter.", "Retrieval evaluation harness (метрики без утверждённых порогов)."],
  out=[], deliverables=["retrieval module", "tests", "S28 report"],
  tests=["ACL leakage — hard blocker: ни один фрагмент чужого проекта (включая через cache/rank).", "Prompt injection в retrieved контенте маркируется как данные."],
  ecc=py([E_RAG, E_SEC], [S_PG, S_EH], [C_SR]), adrs=[], decide=[], docs=[], dod=["ACL leakage suite зелёный."]),

 dict(id="S29", slug="connector_mvp_read_only", title="Connector MVP (read-only)", spec="Spec Add. v1.20 Inc. 24; Inc. 8 (connector contracts)", phase="E. Knowledge, Change & Governance",
  deps=["S27", "S17"], gate="PENDING_DEPS", blockers=[], reqs=["INT-MVP-*"],
  goal="Connector Platform: файлы, OpenAPI import, GitHub/GitLab read-only с checkpoint, dedupe, rate-limit, partial sync.",
  refs=[R(EXT, "§2, §3, §5, §7, §8, §11, §13, §15"), R(API, "§12 Connector Platform contract"), R(SC, "Дополнение §2, §3")],
  scope=["Только read; write/bidirectional запрещены.", "Credentials через secrets; egress allowlist.", "Provider-specific scopes — WORKING, конфигурация."],
  out=["Write операции (post-MVP)."], deliverables=["connectors module", "tests", "S29 report"],
  tests=["Попытка write API → отсутствует/запрещено.", "Rate limit/partial sync/resume.", "Webhook signature/replay window (если используется)."],
  ecc=py([E_SEC], [S_ERR], [C_SR]), adrs=[], decide=["Список scopes для GitHub/GitLab (минимальные read)."], docs=[], dod=["Read-only доказано тестами."]),

 dict(id="S30", slug="source_change_traceability_impact", title="Source change, traceability и Impact Assessment", spec="Spec Add. v1.1 Inc. 16", phase="E. Knowledge, Change & Governance",
  deps=["S28", "S29", "S25"], gate="PENDING_DEPS", blockers=[], reqs=["UX-TRC-*", "DOC-012 критерии"],
  goal="ChangeSet → ImpactAssessment → ImpactItem[], deterministic + semantic impact, категории I0–I4, targeted revalidation, TraceabilityLink lifecycle.",
  refs=[R(SC, "§7, §8, §10"), R(TDI, "§2–§9, §12, §15"), R(PD, "§10"), R(DM, "§10")],
  scope=["Deterministic checks до/параллельно semantic.", "Semantic не понижает I0–I4.", "Source ingestion ≠ impact revalidation."],
  out=[], deliverables=["traceability/impact module", "tests", "S30 report"],
  tests=["Critical impact I0 не понижается.", "Source change after run → revalidation.", "Link type вне registry → reject."],
  ecc=py([E_TYPE], [], []), adrs=[], decide=[], docs=[], dod=["Тесты Source/Impact Spec Add. v1.1 §4 зелёные."]),

 dict(id="S31", slug="artifact_cr_baseline_lifecycle", title="Artifact, Change Request и Baseline lifecycle", spec="Spec Add. v1.1 Inc. 17", phase="E. Knowledge, Change & Governance",
  deps=["S30", "S26"], gate="PENDING_DEPS", blockers=[], reqs=["UX-ART-*", "DOC-013 критерии"],
  goal="Generate → validate → review → approve → publish; exact-version Baseline; CR workflow с Impact Assessment и approvals.",
  refs=[R(DAL, "§3–§10, §14"), R(PD, "§11, §12"), R(TDI, "§9"), R(DM, "§9")],
  scope=["Validation/Review/Approval/Publication — разные факты.", "Baseline immutable; изменение только через CR → новая Baseline.", "GenerationJob записи."],
  out=[], deliverables=["artifacts/governance module", "tests", "S31 report"],
  tests=["Baseline только из exact approved versions.", "Попытка изменить Baseline → отказ.", "WorkerResult не делает артефакт APPROVED."],
  ecc=py([E_SEC], [], [C_SR]), adrs=[], decide=[], docs=[], dod=["Тесты Baseline Spec Add. v1.1 §4 зелёные."]),

 dict(id="S32", slug="recovery_reconciliation", title="Recovery и reconciliation", spec="Spec Add. v1.1 Inc. 18 (recovery)", phase="E. Knowledge, Change & Governance",
  deps=["S31"], gate="PENDING_DEPS", blockers=[], reqs=["REL-001..028"],
  goal="Error taxonomy, bounded retries, pause/cancel/resume, reconciliation DB/Temporal/MinIO, backup (pgBackRest) и restore rehearsal.",
  refs=[R(PD, "§13"), R(RR, "§1, §3"), R(INF, "§7"), R(RB, "процедуры"), R(MIG, "§6, §7")],
  scope=["Reconciliation jobs; ambiguous external effects → manual.", "pgBackRest + WAL; MinIO backup; Recovery Manifest.", "Restore drill (RPO/RTO — цели, не гарантии)."],
  out=[], deliverables=["recovery module", "runbooks", "drill report", "S32 report"],
  tests=["Transient bounded retry; permanent no retry.", "Cancel race.", "Pause/resume консистентность.", "Restore rehearsal на тестовом стенде."],
  ecc=py([E_DB, E_SF], [S_ERR], []), adrs=["ADR-030"], decide=[], docs=["`docs/runbooks/`"], dod=["Restore drill выполнен и задокументирован."]),

 dict(id="S33", slug="evaluation_harness_release_gates", title="Evaluation harness и release gates", spec="Spec Add. v1.20 Inc. 25; Add. v1.1 Inc. 18 (evaluation)", phase="F. Quality & Learning",
  deps=["S32", "S16"], gate="BLOCKED", blockers=["OD-01 (через S16)", "OD-02 (пороги, размеры выборок, human calibration)"], reqs=["DOC-078", "DOC-026 §7"],
  goal="Task-class evaluation sets (deterministic + rubric + adversarial), regression manifest, release gates; LLM judge не единственный gate.",
  refs=[R(EV, "§1–§7"), R(AOE, "§5–§7, §13"), R(ACB, "§7")],
  scope=["Наборы: elicitation, extraction, conflict detection, decomposition, artifact generation, recovery.", "Пороги — только утверждённые владельцем."],
  out=[], deliverables=["evaluation harness", "datasets", "S33 report"],
  tests=["Gate блокирует релиз при провале deterministic/security.", "Воспроизводимость manifest."],
  ecc=py([E_MLE], [S_EH, S_AIR], []), adrs=[], decide=[], docs=[], dod=["Harness работает; пороги утверждены владельцем."]),

 dict(id="S34", slug="learning_signals_curated_experience", title="Learning signals и curated experience", spec="Spec Add. v1.20 Inc. 26", phase="F. Quality & Learning",
  deps=["S33"], gate="PENDING_DEPS", blockers=[], reqs=["DOC-079", "CI-001..045 (MVP часть A0–A2)"],
  goal="Сбор сигналов и curated experience без fine-tuning и без автоматического изменения поведения; A0–A2 только.",
  refs=[R(LE, "§2–§7"), R(CIA, "MVP governance A0–A2"), R(SPEC, "Add. v1.4 (CI contracts — не создавать дубли агрегатов)")],
  scope=["Feedback → curated experience → human approval → versioned release.", "Без cross-tenant learning."],
  out=["A3/A4, fine-tuning."], deliverables=["learning module", "tests", "S34 report"],
  tests=["Feedback не меняет поведение без approval.", "Cross-tenant изоляция."], ecc=py([E_MLE, E_SEC], [], []), adrs=[], decide=["Сопоставление CI contracts с существующими агрегатами (discrepancy report до таблиц)."], docs=[], dod=["Нет автоматических изменений поведения."]),

 dict(id="S35", slug="web_workspace_ui_foundation", title="Web Project Workspace UI: foundation", spec="— (WS-MVP, UX; ADR-010, ADR-019)", phase="G. UI",
  deps=["S12"], gate="PENDING_DEPS", blockers=[], reqs=["WS-MVP-*", "UX-MVP-*", "UX-START-*"],
  goal="SPA: login/MFA, проекты, Epics, Tasks, требования, источники, артефакты (read/write по реализованным API), статусы Operation, SSE.",
  refs=[R(UX, "§3, §4, §6, §7, §10, §12, §13"), R(MVP, "Дополнение v1.0 (WS-MVP)"), R(GL, "термины (UI labels)"), R(AUTH, "§6")],
  scope=["Типы из contracts/openapi; cookie+CSRF; без токенов в storage.", "Состояния loading/error/empty/permission.", "Доступность WCAG 2.2 AA."],
  out=["Manager/plan/результаты/трассируемость (S36)."], deliverables=["`frontend/**`", "tests", "S35 report"],
  tests=["Playwright: основные сценарии.", "axe: нет нарушений уровня A/AA.", "UI скрытие ≠ авторизация (API тесты остаются).", "Нет токенов в localStorage."],
  ecc=ecc([E_TS, E_RE, E_A11Y, E_E2E, E_SEC], [S_E2E, S_CF], [C_RR, C_RT, C_SR]), adrs=["ADR-019"], decide=["State management, routing."], docs=["LOCAL_DEVELOPMENT.md"], dod=["E2E и a11y зелёные."]),

 dict(id="S36", slug="web_workspace_ui_manager_results", title="Web Workspace UI: Manager, plan, results, traceability, artifacts", spec="— (UX; ADR-010)", phase="G. UI",
  deps=["S35", "S31"], gate="PENDING_DEPS", blockers=[], reqs=["UX-PLAN-*", "UX-RESULT-*", "UX-TRC-*", "UX-ART-*", "UX-DUR-*", "UX-REQ-*", "UX-SRC-*"],
  goal="Панель Manager (4 режима), plan review/partial approval, результаты и QA статусы, трассируемость и impact, артефакты/Baseline, решения/риски.",
  refs=[R(UX, "§5, §8, §9, §11, §12"), R(TDI, "§10"), R(DAL, "§11"), R(MVP, "UX-* разделы")],
  scope=["Раздельное отображение execution/acceptance/verification/QA/approval.", "Approval UI вызывает approval команды, не PATCH."],
  out=[], deliverables=["frontend features", "tests", "S36 report"],
  tests=["E2E канонического MVP сценария (DOC-075 §2) с test double LLM.", "a11y."], ecc=ecc([E_TS, E_RE, E_A11Y, E_E2E], [S_E2E], [C_RR, C_RT]), adrs=["ADR-019"], decide=[], docs=[], dod=["Канонический сценарий E2E зелёный."]),

 dict(id="S37", slug="contract_security_verification_hardening", title="Contract & security verification, hardening", spec="Spec Inc. 9; Add. v1.20 Inc. 27", phase="H. Verification & Release",
  deps=["S32", "S36", "S16"], gate="PENDING_DEPS", blockers=[], reqs=["SEC-001..035", "AUTH-*", "THR-*", "Spec §8 полностью"],
  goal="Полные suites: contract, integration, replay, idempotency, authorization, isolation, prompt injection, secret leakage, failure-recovery; adversarial acceptance; SBOM, сканирование, подписи.",
  refs=[R(SPEC, "§4 Increment 9; §8; Add. v1.20 Inc. 27"), R(SECR, "§2, §3 Security gates"), R(THR, "§5–§7"), R(INF, "§14")],
  scope=["Матрица THR → тесты.", "pip-audit/npm audit, SBOM, Cosign подписи собственных образов.", "Credential rotation runbook и тест."],
  out=[], deliverables=["verification reports в reviews/", "S37 report"],
  tests=["Все P0 security gates.", "Полный Spec §8 checklist."], ecc=py([E_SEC, E_SF], [S_PA], [C_SR]), adrs=[], decide=[], docs=["QUALITY_GATES.md"], dod=["Security gates P0 пройдены; отчёт с evidence."]),

 dict(id="S38", slug="performance_capacity_resilience_drills", title="Performance, capacity и resilience drills", spec="— (DOC-030..033)", phase="H. Verification & Release",
  deps=["S37"], gate="BLOCKED", blockers=["OD-02 (числовые SLO/capacity)"], reqs=["PERF-001..026", "REL-001..028", "LT-*"],
  goal="Baseline измерения, нагрузочные тесты, resilience drills; утверждение SLO владельцем.",
  refs=[R(PSR, "§1–§3"), R(PSA, "весь документ"), R(CLT, "LT сценарии"), R(RR, "§1–§3")],
  scope=["Измерить baseline без изобретённых порогов; представить владельцу."], out=[], deliverables=["reports", "S38 report"],
  tests=["LT сценарии DOC-033."], ecc=py([E_PERF], [], []), adrs=[], decide=[], docs=[], dod=["SLO утверждены, измерения воспроизводимы."]),

 dict(id="S39", slug="ui_ux_acceptance_runbooks_productization", title="UI/UX acceptance, runbooks и productization", spec="Spec Add. v1.20 Inc. 28; Add. v1.3 §6", phase="H. Verification & Release",
  deps=["S37", "S36"], gate="PENDING_DEPS", blockers=[], reqs=["UX критерии §15", "DOC-029 deliverables"],
  goal="Usability review, accessibility acceptance, operational runbooks, пользовательские guides по фактическому release build.",
  refs=[R(UX, "§13, §15"), R(UDA, "весь документ"), R(PPP, "весь документ"), R(RB, "весь документ"), R(GL, "термины")],
  scope=["Документация только по фактическому поведению build; скриншоты из release build."], out=[], deliverables=["guides", "runbooks", "S39 report"],
  tests=["Проверка скриншотов против build.", "a11y acceptance."], ecc=ecc([E_A11Y, E_E2E, E_DOC], [S_E2E], []), adrs=[], decide=[], docs=["`docs/runbooks/`"], dod=["Acceptance владельцем UI."]),
]


# --- PREP review amendments (reviews/PREP_PHASE_REVIEW.md) ---
_BYS = {s["id"]: s for s in STAGES}


def _st(i, scope=(), tests=(), decide=(), dod=(), adrs=(), out=(), gate=None, blockers=()):
    s = _BYS[i]
    s["scope"] += list(scope)
    s["tests"] += list(tests)
    s["decide"] += list(decide)
    s["dod"] += list(dod)
    s["out"] += list(out)
    for a in adrs:
        if a not in s["adrs"]:
            s["adrs"].append(a)
    if gate:
        s["gate"] = gate
    s["blockers"] += list(blockers)


CONTRACT_GAP = "Недостающие endpoint/events этапа проектируются в overlay `contracts/*/extensions/` (статус WORKING) до handler по ADR-009 и ADR-038 (OD-09 решён владельцем 2026-11-11); contract tests обязательны."

_st("S01", dod=["Воспроизводимость проверяется на чистой копии рабочего дерева (commit — только по OD-06)."])
_st("S02", tests=["Cursor-HMAC секрет не из файла (env) → отказ запуска; ротация ключа cursor: старые курсоры отклоняются, новые валидны."])
_st("S03", scope=["Hardening контейнеров: non-root, нет docker.sock и privileged, `cap_drop: ALL`, `read_only`, `no-new-privileges`; egress deny-by-default (THR-005); SBOM и скан образов; GitHub Actions закреплены по SHA (THR-013, THR-017); provisioning schema `langgraph` вне runtime (ADR-036)."],
    tests=["Security headers Caddy (HSTS, CSP, X-Content-Type-Options).", "Egress: доступ к metadata/внутренним адресам заблокирован.", "Контейнеры без docker.sock/privileged; read_only и cap_drop проверены inspect.", "PERSIST-023 (сеть): у Manager/Worker нет сетевого пути к PostgreSQL."],
    adrs=["ADR-035"], dod=["Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты."])
_st("S04", scope=["PERSIST-003 (single head) и PERSIST-004 (offline `alembic upgrade --sql`, `CREATE INDEX CONCURRENTLY` через autocommit_block)."],
    tests=["Tenant context через `set_config(name, value, true)` с bind-параметрами; пустая строка → 0 строк, не ошибка (политики с NULLIF).", "Alembic autogenerate не видит schema `langgraph`/`temporal`.", "RLS/grants-тесты только под login-ролями."], adrs=["ADR-034", "ADR-035"])
_st("S05", scope=["Гранты ADR-034: INSERT-only для api на outbox/audit; REVOKE UPDATE/DELETE на immutable; политики outbox/consumer; migration-политики; `derived_from_task_id`.", "Reference-таблица aggregate_type; drift operation_type registry↔таблица."],
    tests=["Под ролью `ai_res_api`: атомарность projection+event+outbox+audit; UPDATE immutable → denied; ai_res_api не может UPDATE/DELETE `audit.audit_events` (THR-015).", "Rework после terminal Operation (новая Operation + Task + WorkerRun).", "Drift registry operation_type ↔ таблица.", "Backfill под migrator при FORCE RLS."],
    dod=["PERSIST по матрице ADR-035 для S05 (001–014, 017–020 на синтетической ревизии); остальные явно отложены.", "Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты."], adrs=["ADR-034", "ADR-035"])
_st("S06", scope=["Append-only event history для агрегатов с AsyncAPI-событиями (основа SSE, ADR-033).", "Расширение reference-таблицы aggregate_type."], adrs=["ADR-034"])
_st("S07", scope=["Прогрессивная задержка вместо hard lockout; доверие XFF только Caddy."],
    tests=["AUTH-005: одинаковые ответ и время для существующей/несуществующей учётки; progressive delay.", "AUTH-008: отзыв сессий при смене пароля, отключении, отзыве роли.", "AUTH-012: человек/сервис/Worker не подменяют друг друга.", "AUTH-013: покрытие auth-событий аудитом.", "Смена session ID после login/MFA (fixation); recovery codes одноразовые; повтор TOTP отклонён; login-CSRF.", "Подделанный XFF не обходит rate limit.", "Невалидная/без версии policy-конфигурация → deny."],
    decide=[CONTRACT_GAP + ""],
    dod=["Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты."], adrs=["ADR-035", "ADR-037"])
_st("S09", out=["`createTask` (перенесено в S21, ADR-012/NCP-08)."])
_st("S10", tests=["PERSIST-015/016.", "Dispatcher видит outbox всех tenants (ADR-034).", "Рост outbox/inbox: алерт, без автоудаления."], adrs=["ADR-034", "ADR-035"])
_st("S12", tests=["SSE закрывается при отзыве сессии/прав во время соединения.", "Подделка Last-Event-ID к чужому aggregate отклоняется."],
    out=["Формат completion policy snapshot (S21), агрегатор по PlanItems (S21), pipeline SOURCE_INGESTION (S27) — в S12 только каркас Operation API."])
_st("S14", scope=["Реестр WorkerDefinition (версии, capability, acceptance schema) — владелец FK и теста Gate «wrong capability»."])
_st("S17", scope=["Worker Run grants (project/task/run/tools/model/budget, TTL) — используются тестами S17 и snapshot Gate S22."])
_st("S20", scope=["Общее ядро Approval и separation of duties (нужно для proposal/PlanVersion); S26 добавляет только requirement-специфику."])
_st("S21", scope=["`createTask` (ADR-012): только внутри активной Operation PLAN_EXECUTION и после включения в одобренный PlanVersion."],
    decide=[CONTRACT_GAP + " Семантика createTask — NCP-08."])
_st("S23", scope=["Checkpoint-broker (ADR-036): собственный `BaseCheckpointSaver` через внутренний endpoint API; роль `ai_res_checkpointer` только на schema `langgraph`."], tests=["Thread другого WorkerRun → отказ.", "Брокер не имеет доступа к доменным schemas.", "У Worker нет сетевого пути к PostgreSQL."], adrs=["ADR-036"])
_st("S26", decide=[CONTRACT_GAP])
_st("S27", scope=["Embeddings — только после OD-01; до того — FTS (статус WORKING). Test double не используется вне test-профиля (ADR-022)."], decide=["Embeddings gated OD-01."])
_st("S28", decide=[CONTRACT_GAP])
_st("S29", decide=[CONTRACT_GAP])
_st("S30", decide=[CONTRACT_GAP])
_st("S31", scope=["Валидаторы Mermaid/PlantUML (UX-ART-33); представления Markdown/DOCX/PDF (UX-ART-31/13)."], decide=[CONTRACT_GAP])
_st("S36", decide=[CONTRACT_GAP + " E2E на test double — только в явном test-профиле."])
_st("S16", tests=["Нет fallback на неразрешённого провайдера/регион (THR-009).", "Provider key только у host-side адаптера (THR-018).", "Bifrost не логирует prompts/payload (THR-019).", "Бюджет и таймауты (THR-016); egress deny-by-default для всех, не только «неразрешённый хост» (THR-004)."])
_st("S24", tests=["LLM и self-assessment Worker не влияют на класс риска (ADR-029)."])
_st("S37", scope=["Runbook компрометации HMAC-ключа idempotency; PERSIST-022; integrity-экспорт audit (THR-015)."], dod=["Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты."], adrs=["ADR-035"])
_st("S32", scope=["PERSIST-021 (restore)."], adrs=["ADR-035"])

for _i in ["S03", "S05", "S07"]:
    _st(_i, adrs=["ADR-037"])
_st("S37", scope=["Чек-лист security owner (слой 4 ADR-037): подпись человека один раз перед релизным baseline."], adrs=["ADR-037"])
_st("S03", adrs=["ADR-036"]); _st("S04", adrs=["ADR-036"])
for _i in ["S07", "S21", "S26", "S28", "S29", "S30", "S31", "S36"]:
    _st(_i, adrs=["ADR-038"])
_st("S01", scope=["Структура overlay `contracts/openapi/extensions/`, `contracts/asyncapi/extensions/`; CI собирает base+overlay, валидирует и проверяет additive-only (ADR-009)."], adrs=["ADR-009"])
