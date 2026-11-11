# ADR data for ARCHITECTURE_DECISION_LOG.md. Each entry: all mandatory fields.
D = "2026-11-10"
IL = "Implementation Lead (делегированные полномочия, Master Implementation Initialization)"

ADRS = [
 dict(id="ADR-001", title="Python 3.13 как целевая версия", status="ACCEPTED", owner=IL,
  context="Нормативные документы задают Python-ориентированный стек (DOC-068 §1), но не версию интерпретатора.",
  reqs="INF-MVP (воспроизводимость), Blueprint §2", docs="DOC-068 §1; DOC-072 §2",
  alts="3.12; 3.13", decision="Python 3.13; точный patch в `.python-version` и base image digest.",
  why="Доступен локально (3.13.5). Совместимость SQLAlchemy 2.x, psycopg 3, Alembic, temporalio, LangGraph с 3.13 проверяется при pin зависимостей (S02/S04); при несовместимости — новая запись SUPERSEDED → 3.12.",
  impact="backend, CI images", risks="Отставание поддержки 3.13 у части библиотек", tests="CI matrix на одной версии; import + smoke integration tests в S02"),
 dict(id="ADR-002", title="uv + `uv.lock` как менеджер зависимостей", status="ACCEPTED", owner=IL,
  context="Blueprint §2: версии фиксируются lock-файлом; плавающие версии запрещены.", reqs="INF-MVP; Spec §4 Inc.1 (pinned tools)", docs="DOC-072 §2; DOC-015 §12",
  alts="Poetry; pip-tools", decision="uv; `uv.lock` в git; CI — `uv sync --locked`.", why="Воспроизводимый lock, скорость, установлен локально.",
  impact="backend, CI", risks="—", tests="CI падает при рассинхроне lock"),
 dict(id="ADR-003", title="Testcontainers для PostgreSQL integration tests", status="ACCEPTED", owner=IL,
  context="Blueprint §2 требует выбрать один из pytest-postgresql/Testcontainers; SQLite не является доказательством.", reqs="PERSIST-001..024", docs="DOC-072 §2, §12",
  alts="pytest-postgresql; локальный Homebrew PostgreSQL", decision="Testcontainers, образ `postgres:16.x` по digest; тот же образ в Compose.",
  why="Одинаковое поведение локально и в CI; чистый кластер для ролей/RLS.", impact="tests, CI (нужен Docker)", risks="Время прогона", tests="Все integration/RLS/concurrency тесты"),
 dict(id="ADR-004", title="Contract toolchain", status="ACCEPTED", owner=IL,
  context="Spec §4 Inc.1, §7: pinned validators, lint, breaking-change detection.", reqs="API-MVP-001", docs="Spec v1.22 §4 Inc.1, §7; DOC-006 §17",
  alts="Только Spectral; AsyncAPI CLI; Redocly", decision="OpenAPI: openapi-spec-validator + Spectral (pinned) + oasdiff (breaking). AsyncAPI: JSON Schema официальной спецификации 3.1.0 из `@asyncapi/specs` + проверка `$ref`; `@asyncapi/parser` — после закрепления Node 22 LTS (G-03). JSON Schema: jsonschema Draft 2020-12 с локальным registry по `$id`. AsyncAPI/JSON Schema breaking-check — собственный скрипт сравнения с предыдущей версией.",
  why="Инструменты подтверждены на текущих контрактах (S00 §3).", impact="contracts/, CI", risks="AsyncAPI parser недоступен на Node 26", tests="S01: негативные фикстуры для каждого валидатора"),
 dict(id="ADR-005", title="Раскладка репозитория", status="ACCEPTED", owner=IL,
  context="Blueprint §3 (BASELINED) задаёт `backend/`; Spec Inc.1 — `contracts/`; DOC-015 §11.2 — `infra/`.", reqs="—", docs="DOC-072 §3; DOC-015 §11.2; Spec §4 Inc.1",
  alts="Корневые src/tests", decision="`backend/` (Python), `frontend/` (UI, ADR-019), `contracts/`, `infra/` (compose.yaml, config, secrets/encrypted, runbooks→`docs/runbooks/`), `docs/implementation/`. Пустые корневые `src/`, `tests/`, `scripts/` не используются и удаляются в S01 (пустые, не отслеживаются git).",
  why="Следование BASELINED структуре.", impact="Все компоненты", risks="—", tests="—"),
 dict(id="ADR-006", title="Система управления реализацией в `docs/implementation/`", status="ACCEPTED", owner=IL,
  context="Master Implementation Initialization §5. Ранее трекеры были в `docs/development/`.", reqs="—", docs="CLAUDE.md §9; documentation-and-versioning.md",
  alts="Оставить docs/development", decision="Все трекеры перенесены в `docs/implementation/` (без дублей); `docs/development/` удалён; ссылка в CLAUDE.md обновлена. `docs/adr/` не создаётся (ecc-precedence.md).",
  why="Единая точка входа.", impact="Документация", risks="—", tests="—"),
 dict(id="ADR-007", title="ECC как dev-time инструментарий", status="ACCEPTED", owner="Владелец проекта (прямое указание) + Implementation Lead",
  context="Spec Addendum v1.3 §4 откладывал выбор Claude Code расширений до решения пользователя; пользователь поручил обязательное использование ECC.", reqs="—", docs="Spec v1.22 Add. v1.3 §4; `.claude/rules/ecc-precedence.md`",
  alts="Не использовать ECC", decision="ECC 2.2.3 (manual project-local install, commit d2ef268) используется как dev-time инструментарий. Hooks, MCP, continuous learning, auto-update не включаются. ECC agents не являются Runtime Workers и не заменяют QA Worker/human approval. Trust assessment: `reviews/ECC_TRUST_ASSESSMENT.md`.",
  why="Указание пользователя; правила AI RES сохраняют приоритет.", impact="Процесс разработки", risks="Supply-chain риск dev-инструментов (см. assessment)", tests="—"),
 dict(id="ADR-008", title="Web-стек Backend: FastAPI + полностью async", status="ACCEPTED", owner=IL,
  context="Web-фреймворк имел статус WORKING (`coding-standards.md`); DP-01. Master Implementation Initialization делегировала выбор библиотек и инструментов Implementation Lead. Решение явно задокументировано (не «молча»).", reqs="API-MVP-003; INF-MVP-002", docs="DOC-072 §2 (async psycopg только при полностью async стеке); DOC-006 §3–§5; DOC-015 §3",
  alts="Litestar; Starlette; sync Flask/Django", decision="FastAPI + Pydantic v2 (DTO), SQLAlchemy 2.x asyncio + psycopg 3 async, uvicorn. OpenAPI — contract-first: нормативен `contracts/openapi`, сгенерированная FastAPI схема используется только для diff-проверки соответствия (schemathesis + сравнение).",
  why="temporalio и LangGraph — asyncio; SSE требует неблокирующих соединений; зрелая экосистема.", impact="backend API, тесты; ECC `fastapi-reviewer` становится применим", risks="Соблазн code-first схем — запрещён ADR-009/ADR-004", tests="Contract tests (schemathesis) против contracts/openapi"),
 dict(id="ADR-009", title="`contracts/` — проверяемое зеркало canonical контрактов", status="ACCEPTED", owner=IL,
  context="Spec §4 Inc.1 требует `contracts/`; Registry v4.1 §2 фиксирует canonical пути в `docs/architecture/`.", reqs="API-MVP-001", docs="Registry v4.1 §2; DOC-082",
  alts="Валидация прямо в docs/architecture; независимая копия", decision="Файлы в `contracts/` — побайтные копии canonical; CI сверяет SHA-256 с `AI_RES_Architecture_Baseline_Manifest_v1.2.json`. Изменение контракта — только через новую canonical версию по решению владельца (NCP) + Registry/manifest, затем пересинхронизация. Производные артефакты (examples, lint config, changelog) — только в `contracts/`.",
  why="Нет второго источника истины.", impact="contracts/, CI", risks="—", tests="CI: рассинхрон → fail"),
 dict(id="ADR-010", title="Единая последовательность этапов S00–S39 и устранение циклических зависимостей", status="ACCEPTED", owner=IL,
  context="Нумерация Spec (Inc. 0–9, 10–18, 20–28) содержит прямые и обратные зависимости: Operation API (Inc.5) требует Temporal (Inc.7) и Outbox dispatcher (Inc.8); Readiness Gate (Inc.13) требует ContextPackageVersion (Inc.22) и Tool Registry (Inc.23); Worker lifecycle (Inc.14) требует LLMGatewayPort (Inc.20); Inc.3 читает таблицы, создаваемые только в Inc.5–6; нет этапов для Local Auth/Policy Engine, Rules Registry (RULE-MVP), построения UI (WS-MVP/UX-*), Requirements approvals (DOC-003).", reqs="Все MVP-семейства (REQUIREMENTS_TRACEABILITY.md)", docs="Spec v1.22 §4, Add. v1.1 §3, v1.19, v1.20; Blueprint §5, §14; Process Design §22",
  alts="(а) Строго следовать нумерации Spec с заглушками; (б) Перестроить порядок, сохранив все работы и инварианты", decision="(б). Единая последовательность S00–S39 (IMPLEMENTATION_ROADMAP.md) с колонкой соответствия Spec. Разделения: Inc.7 → S11 (Temporal foundation) + S23 (LangGraph/WorkerRun); Inc.8 → S10 (Outbox) + S29 (connectors); Inc.20 → S15 (port) + S16 (Bifrost/provider); Inc.22 → S19 (ContextPackage) + S28 (retrieval). Добавлены S07 (Identity/Policy), S18 (Rules), S26 (Requirements approvals/decisions), S35–S36 (UI).",
  why="Ни одна работа Spec не удалена; порядок исключает заглушки, выдаваемые за реализацию, и обход Gate (WorkerRun невозможен до S22).", impact="Весь план", risks="Длиннее путь до первого end-to-end сценария", tests="Каждый этап — собственный DoD; проверка в reviews/S-PREP"),
 dict(id="ADR-011", title="Greenfield-профиль persistence", status="ACCEPTED", owner=IL,
  context="DR-01: DDL v1.0 и Blueprint §5–§6 предполагают существующие `work.tasks` и legacy backfill (PDB-0003 nullable → PDB-0008 backfill → PDB-0009 NOT NULL). В репозитории нет данных и таблиц.", reqs="PERSIST-001..024; DBM-*", docs="DOC-072 §5, §6; DOC-064 §5.2, §11; DOC-068 §5",
  alts="(а) Формально пройти expand/backfill на пустых таблицах; (б) Greenfield: создать `work.tasks` сразу с `operation_id NOT NULL` + `UNIQUE(operation_id,id)`", decision="(б). PDB-0003/0008/0009 для `work.tasks.operation_id` сводятся к созданию таблицы с конечными ограничениями; PDB-0008 = N/A с обоснованием «legacy Task отсутствуют» (проверяемо: upgrade from empty). Expand → backfill → validate → contract обязателен для всех изменений после первой применённой ревизии.",
  why="Инвариант DOC-005/DOC-064 соблюдается с первого дня; фиктивный backfill не создаёт evidence.", impact="Alembic revisions S04–S05", risks="Расхождение с текстом Blueprint §5 → NCP-03", tests="PERSIST-001; тест: вставка Task без operation_id отклоняется"),
 dict(id="ADR-012", title="Владеющая Operation для Task, созданной `createTask`", status="ACCEPTED", owner=IL,
  context="OAS: `POST /epics/{epicId}/tasks` → 201 Task; DOC-005/DOC-064: `operation_id NOT NULL`; DOC-064 §8: создание Task требует non-terminal Operation; Spec Add. v1.15 п.2: одна root Operation на принятую команду; terminal Operation не переоткрывается.", reqs="PROC-MVP; API-MVP", docs="DOC-055 §2, Add. v1.2; DOC-064 §8; DOC-005 Add. v1.4; OAS v1.3 createTask",
  alts="(а) Синхронно завершённая Operation (SUCCEEDED) — блокирует будущие WorkerRun Task (operation terminal, WorkerRun.operation_id = Task.operation_id); (б) Привязка к «текущей» Operation Epic — нарушает «одна Operation на команду» и создаёт неявные агрегаты; (в) Новая root Operation типа `TASK_EXECUTION` в статусе ACCEPTED в той же транзакции, что и Task, + Outbox command", decision="(в). Ответ остаётся 201 Task (контракт не меняется); Operation доступна через Task (additive поле `operationId` — NCP-06). Operation проходит обычный lifecycle и агрегирует результат по Task. Если caller не имеет права на исполнение — Task регистрируется как proposal (OAS: «registered as a proposal according to caller authority») без старта исполнения; Operation остаётся в ожидании решения человека (WAITING_FOR_HUMAN).",
  why="Сохраняет все BASELINED инварианты без изменения публичного контракта.", impact="S09, S12, S21", risks="Рост числа Operation; UX отображает их через Task", tests="S09: createTask создаёт ровно одну Operation; retry с тем же Idempotency-Key — та же Task/Operation; Task без Operation невозможна"),
 dict(id="ADR-013", title="Реестр `operation_type`", status="ACCEPTED", owner=IL,
  context="OQ-3 (WORKING): точный enum не определён. Запрещено принимать произвольные строки.", reqs="API-MVP; PROC-MVP", docs="DOC-055 §6; DOC-057",
  alts="PostgreSQL enum; CHECK; reference table + code registry", decision="Code registry (Python enum) + reference table `operations.operation_types` (FK), значения добавляются ревизией и ADR на этапе, который вводит команду. Начальные значения: `MANAGER_MESSAGE` (S20), `TASK_EXECUTION` (S09/ADR-012), `SOURCE_INGESTION` (S12/completeUpload), `PLAN_EXECUTION` (S21).",
  why="Расширяемо без ALTER TYPE; валидация по registry.", impact="operations schema", risks="Значения — implementation-уровень; синхронизация с DOC-055 через NCP-01", tests="Неизвестный тип → отклонение"),
 dict(id="ADR-014", title="Имена PostgreSQL schemas", status="ACCEPTED", owner=IL,
  context="OQ-2 (WORKING).", reqs="DATA-MVP", docs="DOC-005 §14; DOC-064 §3; DOC-065", alts="Переименование", decision="Использовать имена DOC-005 §14 / DOC-064 §3 / `coding-standards.md`: iam, organization, project, work, requirements, sources, knowledge, decisions, artifacts, traceability, governance, agents, context, integrations, audit, platform, operations, execution; LangGraph — отдельная schema `langgraph` вне Alembic allowlist.",
  why="Согласовано во всех документах.", impact="Миграции", risks="—", tests="Allowlist test"),
 dict(id="ADR-015", title="Набор PostgreSQL ролей по нормативным документам", status="ACCEPTED", owner=IL,
  context="DR-10: `.claude/rules/database-and-migrations.md` перечислял `ai_res_manager`/`ai_res_worker`; нормативные DOC-064 §10, DOC-005, DOC-019, DOC-069 — иной набор, Manager/Worker без DB credentials.", reqs="SEC P0; DBM-*", docs="DOC-064 §10; DOC-068 §2; DOC-069; DOC-019 §4",
  alts="Следовать правилу проекта", decision="Роли: `ai_res_owner` (NOLOGIN), `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor`, backup identity; login-роли входят в `*_group` роли по DOC-069. `ai_res_manager`/`ai_res_worker` не создаются. Правило проекта исправлено в рамках этого решения (иерархия: нормативные документы выше `.claude/rules`).",
  why="Иерархия источников истины.", impact="S04–S05, `.claude/rules/database-and-migrations.md`", risks="—", tests="Grants audit; forbidden attributes"),
 dict(id="ADR-016", title="Проектирование отсутствующих физических таблиц", status="ACCEPTED", owner=IL,
  context="DR-02/DR-09: DDL v1.0 (WORKING) покрывает только execution slice; DOC-064 §1/§3 требует `agents.worker_results`, `audit.audit_events`, `work.task_dependencies`; Roles SQL ссылается на `audit.audit_events`.", reqs="DATA-MVP; PERSIST-*", docs="DOC-005 §5–§16; DOC-064 §3–§7; DOC-065; DOC-069",
  alts="Ждать новой версии DDL", decision="Implementation Lead проектирует физические таблицы из логической модели DOC-005 и DOC-064 (UUIDv7 PK, `organization_id`/`project_id`, `row_version`, `timestamptz`, named constraints, RLS FORCE). DDL v1.0 — входной design snapshot, не нормативный DDL. Каждое отклонение от DDL v1.0 фиксируется в ADR этапа. Обновление DOC-065 — NCP-02.",
  why="Без этого невозможны S05–S08; решение в пределах логической модели.", impact="S05, S06", risks="Расхождение с будущим DDL владельца", tests="Schema drift check против собственного design snapshot `backend/.../schema_snapshot.sql`"),
 dict(id="ADR-017", title="Policy & Permission Engine — in-process модуль", status="ACCEPTED", owner=IL,
  context="DOC-018 §2, §7 требует независимого Policy Engine; реализация не выбрана. Добавление сервисов в топологию требует владельца.", reqs="SEC-001, SEC-002; AUTH-*", docs="DOC-018 §2, §6, §7; DOC-016 §2; architecture-constraints.md (топология)",
  alts="OPA sidecar; Cedar; Casbin; in-process", decision="Модуль `ai_res.policy` за `PolicyDecisionPort` (allow/deny/approval-required + reason codes), deny-by-default, версионированная policy-конфигурация, вызывается в каждом enforcement point. Ошибка/недоступность → deny (fail-closed). Внешний engine возможен позже через тот же port.",
  why="Не меняет топологию; тестируемо; соответствует модульному монолиту.", impact="S07 и все последующие", risks="Логика policy в коде — требует review security-reviewer", tests="Policy matrix tests; outage → deny"),
 dict(id="ADR-018", title="Rules Registry и Rules Engine — отдельные интерфейсы в модульном монолите", status="ACCEPTED", owner=IL,
  context="RULE-MVP-01..14 (MVP Matrix Add. v0.7–v0.8) обязательны; в Spec нет этапа; Architecture Concept §15 рекомендует вариант C (гибрид).", reqs="RULE-MVP-01..14", docs="DOC-001 §15; DOC-009 Add. v0.7, v0.8",
  alts="Отдельный сервис; встроить в Policy Engine", decision="Модули `ai_res.rules.registry` и `ai_res.rules.engine` с отдельными интерфейсами от Policy Engine (RULE-MVP-01), совместное развёртывание в API-процессе. Системные правила не переопределяются. Этап S18.",
  why="Вариант C Architecture Concept; топология не меняется.", impact="S18, S22", risks="—", tests="RULE-MVP критерии приёмки"),
 dict(id="ADR-019", title="Frontend: React + TypeScript + Vite SPA", status="ACCEPTED", owner=IL,
  context="Web Project Workspace — основной канал MVP (DOC-004 §18; WS-MVP); frontend-стек нигде не выбран.", reqs="WS-MVP; UX-*", docs="DOC-004; DOC-015 §3, §9; DOC-016 §2 (User Ingress)",
  alts="Server-rendered templates; Vue; Next.js (SSR-сервер добавил бы процесс)", decision="React + TypeScript (strict) + Vite, статическая сборка, отдаётся Reverse Proxy same-origin с API; cookie session + CSRF; npm + package-lock; Node 22 LTS pinned. Генерация TS-типов из contracts/openapi.",
  why="Не добавляет runtime-процесс; contract-first типы; ECC имеет react/typescript reviewers.", impact="S35–S36, S39", risks="—", tests="Vitest + Playwright E2E; axe accessibility"),
 dict(id="ADR-020", title="Reverse Proxy: Caddy", status="ACCEPTED", owner=IL,
  context="DOC-015 §9: Reverse Proxy — единственная публичная точка; продукт не выбран.", reqs="INF-MVP; SEC", docs="DOC-015 §3, §9; DOC-016 §2",
  alts="nginx; Traefik", decision="Caddy (pinned digest), TLS termination, security headers, rate limiting на login (DOC-023 §4) — в приложении, proxy — дополнительный слой.",
  why="Простая конфигурация TLS для on-prem/local.", impact="infra", risks="—", tests="S03: только proxy опубликован на host"),
 dict(id="ADR-021", title="Работа с WORKING Worker Contracts v1.1", status="ACCEPTED", owner=IL,
  context="DOC-007 WORKING; S14 требует typed контрактов.", reqs="API-MVP; PROC-MVP", docs="DOC-007; DOC-006 §8; api-and-contracts.md",
  alts="Ждать BASELINED", decision="Реализовать по v1.1 с явной маркировкой WORKING в коде/тестах; `contractVersion` major проверяется во всех 4 точках, unknown major → fail closed. Изменения полей фиксируются как NCP-04; перевод в BASELINED — владелец.",
  why="Rules разрешают работу с WORKING при явной маркировке.", impact="S14, S23", risks="Rework при изменении контракта", tests="Unknown major → reject в 4 точках"),
 dict(id="ADR-022", title="Deterministic LLM test double только в test-профиле", status="ACCEPTED", owner=IL,
  context="Lifecycle WorkerRun/Manager необходимо тестировать до подключения провайдера (S16 BLOCKED).", reqs="API-MVP; INF-MVP", docs="DOC-076 §2, §8; DOC-006 §11",
  alts="Ждать провайдера", decision="`DeterministicLLMGateway` реализует `LLMGatewayPort` для тестов; конфигурационная валидация запрещает его в профилях кроме `test`; отчёты этапов явно указывают, что качество агентного вывода не проверялось.",
  why="Честное тестирование механики без выдачи заглушки за функциональность.", impact="S15, S20–S25", risks="Ложное ощущение готовности — снимается явной маркировкой", tests="Профиль local/prod с test double → ошибка запуска"),
 dict(id="ADR-023", title="`gateResultId` ↔ ReadinessEvaluation", status="ACCEPTED", owner=IL,
  context="DR-04: AsyncAPI v1.6 использует `gateResultId`; DOC-055 §3.2 — переименовать в следующей breaking-safe версии.", reqs="—", docs="DOC-055 §3.2; DOC-008",
  alts="Две таблицы", decision="Одна таблица `execution.readiness_evaluations`; event adapter заполняет `gateResultId` = evaluation id; переименование — новая major версия события (NCP-05).",
  why="Запрет двух таблиц.", impact="S22", risks="—", tests="Contract test события"),
 dict(id="ADR-024", title="Idempotency HMAC keys с key-id", status="ACCEPTED", owner=IL,
  context="HMAC digest обязателен; rotation policy WORKING.", reqs="DBM-*; API idempotency", docs="DOC-064 §8; DOC-006 Add. v1.7; DOC-019 §5",
  alts="Без key-id", decision="Хранить `key_id` рядом с digest; активный ключ из Compose secret; проверка по всем незаархивированным key_id. Конкретный период ротации — не задаётся (WORKING), runbook в S37.",
  why="Ротация без потери идемпотентности.", impact="S07", risks="—", tests="Rotation test: старый ключ продолжает дедуплицировать"),
 dict(id="ADR-025", title="Поэтапная observability", status="ACCEPTED", owner=IL,
  context="Spec: инкремент без observability не завершён; стек OTel → Prometheus/Loki/Tempo/Grafana.", reqs="OBS-*", docs="DOC-024 §4, §7; DOC-026",
  alts="Всё в конце", decision="OTel SDK + structured logging с redaction — с S02; OTel Collector в Compose — S03; Prometheus/Loki/Tempo/Grafana + alerts — S13; Langfuse выключен (content capture off).",
  why="Каждый этап имеет telemetry с первого кода.", impact="Все", risks="—", tests="Redaction tests с S02"),
 dict(id="ADR-026", title="Инструменты тестирования и статического анализа", status="ACCEPTED", owner=IL,
  context="Нужны воспроизводимые проверки уровня Spec §8.", reqs="Spec §8", docs="Spec v1.22 §8; testing-and-verification.md",
  alts="—", decision="pytest, pytest-asyncio, hypothesis (stateful tests state machines), Testcontainers, schemathesis (contract), temporalio testing env + replayer, Playwright + axe (UI), ruff, mypy --strict, bandit/pip-audit (security), Vitest. Покрытие — дополнительная метрика, не DoD.",
  why="Покрывает типы тестов TEST_STRATEGY.md.", impact="Все", risks="—", tests="—"),
 dict(id="ADR-027", title="UUIDv7", status="ACCEPTED", owner=IL,
  context="coding-standards: UUIDv7 рекомендован, самодельный генератор запрещён; stdlib 3.13 не имеет uuid7.", reqs="DATA-MVP", docs="DOC-005 §15; coding-standards.md",
  alts="UUIDv4", decision="Библиотека `uuid-utils` (RFC 9562); при неподтверждённой надёжности в S02 — UUIDv4 с новой записью ADR.",
  why="Сортируемость индексов.", impact="Все таблицы", risks="—", tests="Монотонность/формат в S02"),
 dict(id="ADR-028", title="Temporal self-hosted", status="ACCEPTED", owner=IL,
  context="OQ-11; DOC-015 §4: версия/namespace уточняются при сборке Compose.", reqs="INF-MVP", docs="DOC-015 §4, §6",
  alts="temporalio/auto-setup (не для production)", decision="`temporalio/server` pinned digest, отдельная БД `temporal_db` в том же PostgreSQL-кластере под отдельной ролью, schema setup — отдельный one-shot job (`temporal-sql-tool`); namespace `ai-res`; Web UI только в admin-сети. Точная версия фиксируется в S03.",
  why="Соответствие DOC-015, нет auto-setup в release.", impact="S03, S11", risks="—", tests="S03 health; S11 replay"),
 dict(id="ADR-029", title="Безопасный default для risk-tier эскалации", status="ACCEPTED", owner=IL,
  context="DOC-051: quantitative risk calibration и authority matrix — WORKING; Spec Add. v1.2 п.9 требует risk-tier adjudication.", reqs="PROC-MVP", docs="DOC-051; Spec Add. v1.2 §9",
  alts="Придумать пороги", decision="До решения владельца (OD-05) Manager самостоятельно адъюдицирует только риск `LOW`, определённый детерминированными правилами; всё остальное — human escalation. Пороги не изобретаются, конфигурация пустая = максимальная эскалация.",
  why="Не изобретает WORKING-значения, fail-safe.", impact="S24, S25", risks="Больше ручной работы", tests="Неопределённый риск → эскалация"),
 dict(id="ADR-030", title="Retention: без автоматического удаления", status="ACCEPTED", owner=IL,
  context="Retention/legal hold — WORKING (OQ-8); Spec Add. v1.16 п.16.", reqs="REL-*", docs="Spec Add. v1.16 §16; DOC-005 §18",
  alts="Придумать сроки", decision="Retention policy — конфигурируемый механизм; до утверждения владельцем (OD-02) автоматическое удаление выключено.",
  why="Прямое требование Spec.", impact="S10, S12, S32", risks="Рост объёма", tests="Политика без значений → удаление не выполняется"),
 dict(id="ADR-031", title="Провайдер-нейтральный LLMGatewayPort до решения по провайдеру", status="ACCEPTED", owner=IL,
  context="Bifrost — кандидат pending PoC; провайдер/модель первого среза (OQ-1) и разрешение на передачу данных проекта внешнему провайдеру — решение владельца (OD-01).", reqs="—", docs="DOC-076 §2, §7, §8; architecture-constraints.md (LLM доступ)",
  alts="Выбрать провайдера самостоятельно", decision="S15 реализует port, Model Registry и test double; S16 (Bifrost PoC + provider adapter) BLOCKED до OD-01. Никаких прямых вызовов provider API.",
  why="Внешний egress проектных данных — решение владельца/security.", impact="S15, S16, S33, S37, S39", risks="Задержка end-to-end качества", tests="Architecture test: нет импорта provider SDK вне adapter"),
 dict(id="ADR-032", title="Статусы этапов и определение DONE", status="ACCEPTED", owner=IL,
  context="Master Initialization §8: различать NOT_STARTED…DEFERRED.", reqs="—", docs="testing-and-verification.md",
  alts="—", decision="Этап считается DONE только в статусе VERIFIED (все применимые DoD подтверждены воспроизводимыми командами из отчёта) либо IMPLEMENTED (static evidence) для чисто документационных этапов. Зависимый этап стартует только после DONE предшественников. Для промптов: READY / PENDING_DEPS / BLOCKED / DONE.",
  why="Исключает «готово» без evidence.", impact="Все", risks="—", tests="—"),
 dict(id="ADR-033", title="Источник SSE и event history API", status="ACCEPTED", owner=IL,
  context="Ревью S00: outbox — очередь доставки; API не имеет USAGE на `audit` (DOC-069).", reqs="API-MVP", docs="DOC-061 §9, §12; DOC-006 §4; api-and-contracts.md",
  alts="Читать outbox", decision="SSE строится из event history (`operations.operation_events`, `agents.worker_run_events`, доменные event history) с ACL-фильтром на каждое событие; Last-Event-ID = (aggregate, sequence) cursor; при выходе за retention — явный gap-сигнал. Outbox никогда не читается API.",
  why="DOC-061 §12: Outbox не экспонируется пользователям.", impact="S12", risks="—", tests="SSE replay ACL; gap signalling"),
]


# --- PREP review amendments (reviews/PREP_PHASE_REVIEW.md) ---
_BYA = {a["id"]: a for a in ADRS}


def _am(i, decision=None, tests=None, context=None, status=None):
    a = _BYA[i]
    if decision:
        a["decision"] += " **[PREP review]** " + decision
    if tests:
        a["tests"] += "; " + tests
    if context:
        a["context"] += " " + context
    if status:
        a["status"] = status


_am("ADR-003", "Образ PostgreSQL закрепляется конкретным digest в `infra/images.lock` (тег `16.x` не является pin). RLS/grants/tenant-тесты выполняются только под login-ролями, не под суперпользователем контейнера (DBM-008). [DB-7]", "тесты RLS/grants падают при запуске под суперпользователем")
_am("ADR-011", "Статус решения: отклонение от порядка Blueprint §5/§14 принято как рабочее; формально PDB-0003/0008/0009 = «N/A pending owner» до решения по NCP-03. PERSIST-017..020 доказываются синтетической test-only expand/backfill/validate ревизией на служебной таблице (не production-схема). [ARC-13, DB-5]", "синтетическая ревизия: остановка и перезапуск backfill; NOT VALID→VALIDATE находит orphan")
_am("ADR-012", "ПЕРЕСМОТР. Публичная команда `createTask` не создаёт собственную Operation и не пишет Outbox-команду старта. Task создаётся только внутри активной non-terminal Operation (`PLAN_EXECUTION`, создаётся при approval PlanVersion, S21) и после включения в одобренный PlanVersion (TX-03; Spec §9). При отсутствии активной Operation команда отклоняется Problem Details с кодом из каталога DOC-006 §16 (код выбирается в S09/S21, не изобретается здесь). Реализация `createTask` переносится из S09 в S21; в S09 остаются остальные записи. Семантика публичной команды (201 vs 202+Location, поле `Task.operationId`) — NCP-08, решение владельца. Прежний вариант «новая root Operation TASK_EXECUTION в ACCEPTED» отозван: переход ACCEPTED→WAITING_FOR_HUMAN запрещён (DOC-055 §2.4), команда с Operation обязана отвечать 202+Location (DOC-055 §2.5), Outbox-старт возникал бы раньше dispatcher/workflow. [ARC-2, DB-1]", "createTask вне активной Operation → отклонение; Task не включена в PlanVersion → не исполняется; повторный Idempotency-Key — та же Task")
_am("ADR-015", "Терминология: `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` — LOGIN-роли, входящие в `ai_res_api_group`, `ai_res_outbox_group`, `ai_res_consumer_group`, `ai_res_auditor_group` (DOC-069). Роль для LangGraph checkpointer не задаётся этим ADR: конфликт BASELINED-документов решён ADR-036. [DB-16, SEC-1]")
_am("ADR-016", "Drift-snapshot `schema_snapshot.sql` ведётся вручную и ревьюится независимо (не генерируется из миграций) + сверка пересекающихся таблиц с DOC-065, каждое отклонение — ADR этапа. Допустимые `aggregate_type` outbox/events задаются reference-таблицей, а не фиксированным CHECK ('OPERATION','WORKER_RUN'); расширяется ревизиями S06/S10. [DB-10]", "drift check падает на намеренном расхождении")
_am("ADR-017", "Policy-конфигурация версионирована в репозитории, проверяется checksum при старте; невалидная конфигурация или отсутствие версии → deny-all + alert. Изменение — через review и security owner. Каждое решение аудируется с версией policy. Manager/Worker Runtime не вызывают policy in-process: доступ к защищённым действиям — только через API Application Service / Tool Gateway (S17), где PolicyDecisionPort вызывается на каждый tool call. [SEC-7]", "невалидный конфиг → deny; отсутствие версии → deny; решение содержит policy version")
_am("ADR-020", "Rate limit по client IP: приложение доверяет `X-Forwarded-For` только от Caddy (trusted proxy), Caddy перезаписывает заголовок; вместо hard lockout — progressive delay (иначе DoS учётной записи). Security headers (HSTS, CSP, X-Content-Type-Options) проверяются тестом. [SEC-5]", "S03: заголовки безопасности; S07: подделанный XFF не обходит лимит")
_am("ADR-022", "Профиль по умолчанию — `prod`. `DeterministicLLMGateway` лежит в отдельном пакете, исключённом из prod-образа; тест: prod-образ не содержит test-модуля. Конфигурационная валидация — дополнительный, не единственный барьер. Embeddings (S27) и E2E-прогоны с double допустимы только в явном test-профиле. [SEC-6, ARC-8]", "образ без test-модуля; import test-модуля в prod → ошибка")
_am("ADR-024", "Ротация двухфазная (accepted → active); digest проверяется по всем неархивным key_id в одной транзакции; advisory xact lock по scope+отсортированным digest предотвращает дубль на границе ротации. Runbook компрометации ключа — S37. [DB-11, SEC-11]", "конкурентный запрос на границе ротации не создаёт дубль")
_am("ADR-029", "До появления правил Rules Registry (S18) класс `LOW` никому не присваивается; LLM-оценка и self-assessment Worker не влияют на класс риска. [SEC-12]", "LLM/self-assessment не меняет класс риска")
_am("ADR-030", "Исключения из «без автоудаления»: истечение сессий, TTL idempotency, lease — переходы состояния, не удаление данных. Physical purge outbox/inbox выключен до OD-02; алерт на рост объёма (S13). [DB-14]")
_am("ADR-033", "Last-Event-ID — opaque HMAC-подписанный курсор (карта aggregate→sequence), привязанный к сессии и фильтру; подделка/чужой aggregate → отклонение. Поток закрывается при отзыве сессии или прав во время соединения. Для агрегатов S06 (requirements, artifacts и др.) создаётся append-only event history. [SEC-9, DB-12]", "revoke сессии/прав закрывает SSE; подделка курсора на чужой aggregate отклоняется")

ADRS.append(dict(id="ADR-034", title="Rework после terminal Operation и RLS/grants для event-таблиц", status="ACCEPTED", owner=IL,
  context="DOC-055 §116: повтор после terminal — новая Operation (или дочерняя); composite FK WorkerRun→Task(operation_id,id) BASELINED. Review: DB-1, DB-2, DB-3, DB-4, DB-8 (адаптация WORKING DOC-069).", reqs="PERSIST-*; PROC-MVP; SEC P0", docs="DOC-055 §116, §353; DOC-064 §10; DOC-069 (WORKING); DOC-065 (WORKING)",
  alts="Менять composite FK (BASELINED); сменять operation_id у Task", decision="(1) Rework после terminal Operation = новая root Operation + новая Task с additive `derived_from_task_id` + WorkerRun с `derived_from_worker_run_id`; composite FK и immutability сохраняются. (2) `ai_res_api_group`: USAGE на schema `audit`, INSERT-only на `audit.outbox_events` и `audit.audit_events` (без SELECT/UPDATE/DELETE) — иначе невозможны транзакция projection+event+outbox и fail-closed audit. (3) REVOKE UPDATE/DELETE на immutable таблицах (`readiness_evaluations`, `readiness_check_results`, `worker_results`, event history) + trigger; расхождение с DOC-069 фиксируется как discrepancy. (4) Политики для `ai_res_outbox_group`/`ai_res_consumer_group` на outbox/inbox: cross-tenant без GUC, UPDATE только delivery-колонок. (5) Для migrator/owner при FORCE RLS — явные migration-политики; backfill под ними проверяется тестом.",
  why="Сохраняет все BASELINED инварианты; DOC-069 имеет статус WORKING и требует адаптации.", impact="S05, S09, S10, S21", risks="Отклонение от DOC-069 — NCP-02", tests="Grants audit под реальной ролью ai_res_api; атомарность projection+event+outbox+audit; rework после terminal Operation; dispatcher видит события всех tenants; UPDATE immutable → denied"))

ADRS.append(dict(id="ADR-035", title="Контуры тестирования и evidence для P0-этапов", status="ACCEPTED", owner=IL,
  context="SEC-10: security-reviewer ECC — та же модель, что и автор; не независимое review. PERSIST-001..024 недостижимы все в S05 (ARC-5, DB-6).", reqs="SEC P0; PERSIST-*", docs="testing-and-verification.md; Blueprint §12",
  alts="Считать ECC review достаточным", decision="(1) ECC security-reviewer — обязательный, но не единственный gate; для S03, S05, S07, S37 применяется независимая проверка по ADR-037. (2) PERSIST-тесты распределены по этапам: 001–014 → S05; 003/004 (single head, offline `--sql`) → S04; 015/016 → S10; 023 → S03/S23 (Compose-сеть); 021 → S32; 022 → S37. Отложенные тесты фиксируются явно, не считаются пройденными.",
  why="Честный evidence без самооценки.", impact="S03–S07, S10, S32, S37", risks="Задержка закрытия S05", tests="Матрица PERSIST→этап в TEST_STRATEGY.md"))


# --- Owner decisions 2026-11-11: OD-07..OD-10 ---
_am("ADR-008", "Выбор FastAPI подтверждён владельцем 2026-11-11 (OD-10), как и правки CLAUDE.md и `.claude/rules/database-and-migrations.md` (ADR-006, ADR-015).")
_am("ADR-009", "ДОПОЛНЕНИЕ (OD-09, решение владельца 2026-11-11): endpoint и события, отсутствующие в OAS v1.3/AsyncAPI v1.6, проектирует Implementation Lead по документам проекта. Они живут в `contracts/openapi/extensions/` и `contracts/asyncapi/extensions/` как overlay со статусом WORKING (поле `x-status: WORKING`, `x-source` — ссылки на разделы нормативных документов). Базовые зеркальные файлы не изменяются; CI собирает base+overlay, валидирует и проверяет, что overlay только additive (breaking-check против v1.3/v1.6). Формализация в нормативных версиях — NCP-06 (OAS v1.4) после этапа; `docs/architecture/` не меняется без указания владельца.")
_am("ADR-015", "ДОПОЛНЕНИЕ (OD-08 закрыт ADR-036): добавляется LOGIN-роль `ai_res_checkpointer`, входящая в `ai_res_checkpointer_group`, права только на schema `langgraph`; пароль держит только процесс API.")

ADRS.append(dict(id="ADR-036", title="LangGraph checkpointer через checkpoint-broker", status="ACCEPTED", owner=IL,
  context="Конфликт BASELINED: DOC-006 §351 и INF-MVP-005 требуют checkpointer в PostgreSQL с доступом «соответствующему Runtime/service role»; Spec Add. v1.18 п.4 и PERSIST-023: у Manager/Worker нет ни DB credentials, ни сетевого пути к БД. Владелец делегировал разрешение противоречий Implementation Lead (Master Implementation Initialization).", reqs="INF-MVP-005; PERSIST-023; SEC P0", docs="DOC-006 §351; DOC-064 §10; Spec v1.22 Add. v1.18; INF v1.7 §4",
  alts="(а) Отдельная роль `langgraph` у Worker Runtime — нарушает PERSIST-023; (б) checkpoint-broker в Application Service; (в) хранить checkpoint в MinIO/файлах — нарушает INF-MVP-005", decision="(б). Worker/Manager используют собственную реализацию `BaseCheckpointSaver`, которая вызывает внутренний authenticated endpoint Application Service (service identity, audience-scoped, scope = один WorkerRun/thread). Брокер работает в процессе API и пишет в PostgreSQL schema `langgraph` под отдельной LOGIN-ролью `ai_res_checkpointer` (права только на эту schema, без доступа к доменным schemas). Schema создаёт provisioning-ревизия/job под migrator, не runtime (`setup()` DDL не вызывается). Состояние хранится в PostgreSQL и отделено от доменных таблиц — требования DOC-006 и INF-MVP-005 выполнены, DB credentials у Worker нет. Брокер проверяет, что thread принадлежит WorkerRun вызывающего Worker Run grant.",
  why="Единственный вариант, одновременно удовлетворяющий обоим BASELINED требованиям.", impact="S03, S04, S23", risks="Задержка вызова брокера; размер checkpoint — лимиты в S23", tests="Чужой thread → отказ; обращение брокера к доменным schemas → denied под ролью; у Worker нет сетевого пути к PostgreSQL; autogenerate Alembic не видит schema langgraph"))

ADRS.append(dict(id="ADR-037", title="Независимая проверка P0-этапов (замена per-stage human sign-off)", status="ACCEPTED", owner=IL,
  context="Review: ИИ-ревью той же модели не независимо (SEC-10). Владелец поручил выбрать лучшее решение (OD-07).", reqs="SEC P0; Spec §8", docs="testing-and-verification.md; security.md (P0 release blockers)",
  alts="Подпись человека на каждом P0-этапе (S03, S05, S07, S37) — тормозит последовательность; только ИИ-ревью — не независимо", decision="Для S03, S05, S07, S37 обязательны четыре слоя: (1) детерминированные проверки без LLM в CI (grants/forbidden attributes audit, RLS coverage, bandit, pip-audit, секрет-скан, negative authorization suite); (2) ECC `security-reviewer` в свежем контексте по принципу blind-first (без чтения отчёта автора) и отдельно `database-reviewer`/`architect` по своей области; (3) Hypothesis/property и adversarial тесты на каждый P0-инвариант; (4) человеческий security owner подписывает чек-лист один раз перед релизным baseline (S37), а не на каждом этапе. Этап не получает VERIFIED при открытом HIGH или непройденных слоях 1–3; без слоя 4 релиз не выпускается.",
  why="Независимость обеспечивается детерминированными проверками и человеком на релизе, не тормозя последовательность этапов.", impact="S03, S05, S07, S37", risks="Человеческая проверка откладывается до релиза", tests="CI-джобы слоя 1 падают на намеренных нарушениях"))

ADRS.append(dict(id="ADR-038", title="План проектирования недостающих endpoint и событий", status="ACCEPTED", owner=IL,
  context="OD-09 решён владельцем: проектировать недостающие endpoint по документам проекта. OAS v1.3 содержит 26 operations; для этапов S07, S21, S26, S28–S31, S36 нужны дополнительные.", reqs="API-MVP; AUTH-*; UX-*", docs="DOC-023 (Auth); DOC-006 §3–§16; DOC-003; DOC-051; DOC-009 (UX); ADR-009",
  alts="Ждать OAS v1.4 от владельца", decision="Каждый этап проектирует свои endpoint в overlay (ADR-009) до написания handler: auth (login/logout/csrf/MFA/recovery) — S07 по DOC-023; approve/reject плана и PlanVersion — S21; approvals требований, decisions/assumptions/risks/unknowns — S26; retrieval/search — S28; connectors/sync — S29; impact/ChangeSet — S30; review/publish артефактов, ChangeRequest, Baseline — S31. Правила: base path `/api/v1`, camelCase, cursor pagination, RFC 9457, If-Match/ETag, Idempotency-Key, 202+Location для долгих команд; события — CloudEvents, additive; имена `operationId` по существующему стилю OAS. Каждый overlay сопровождается ADR этапа, contract tests (schemathesis) и записью в `CONTRACT_TRACEABILITY_MAP.md` со статусом WORKING.",
  why="Следует всем правилам контрактов; не меняет базовые зеркала.", impact="S07, S21, S26, S28–S31, S36", risks="Расхождение с будущей OAS v1.4 — закрывается NCP-06", tests="CI: overlay additive; handler соответствует overlay; schemathesis"))

ADRS.append(dict(id="ADR-039", title="Breaking-change detection: собственный diff вместо oasdiff на S01", status="ACCEPTED", owner=IL,
  context="ADR-004 предполагал oasdiff. На момент S01 бинарь oasdiff отсутствует, Docker daemon не запущен, установка через brew меняет глобальное окружение (запрещено без разрешения).", reqs="API-MVP-001; Spec §7", docs="ADR-004; DOC-006 §15; api-and-contracts.md",
  alts="brew install oasdiff; docker image по digest; собственный diff", decision="Единый Python-diff (`contracts/tools/contracts_lib.py`: breaking_openapi/asyncapi/jsonschema) с негативными тестами сравнения против снимка `contracts/baseline/`. oasdiff остаётся целевым дополнительным cross-check в CI (pinned image по digest) — подключается в S03 при наличии Docker; расхождение результатов двух инструментов — fail.",
  why="Воспроизводимо локально без изменения глобального окружения; одна реализация для всех трёх форматов.", impact="S01, S03", risks="Собственный diff покрывает не все случаи oasdiff (см. KNOWN_GAPS G-20)", tests="test_breaking_*: удаление endpoint/message/поля — breaking; additive optional — нет"))

ADRS.append(dict(id="ADR-040", title="Инструменты сохранения контекста: session-brief hook, CONTEXT_HANDOFF, Context7, Serena", status="ACCEPTED", owner="Владелец проекта (выбор 2026-11-11) + Implementation Lead",
  context="Потеря контекста между сессиями и compaction. Владелец поручил установить ECC-совместимые инструменты. ECC `ck` пишет в глобальные `~/.claude/ck` и в нативную память проекта (нарушает «не менять глобальную конфигурацию»); `suggest-compact.js` в проекте не установлен.", reqs="—", docs="ecc-precedence.md; CLAUDE.md §11",
  alts="ECC ck + hooks профиль minimal; сторонние memory-MCP; только ручные заметки", decision="(1) Проектный read-only SessionStart hook `.claude/hooks/session-brief.mjs` (startup|resume|clear|compact) подставляет сводку STATUS + первые 60 строк `CONTEXT_HANDOFF.md` + git status; без сети и записи. (2) `CONTEXT_HANDOFF.md` обновляется в конце этапа/сессии. (3) Context7 MCP `@upstash/context7-mcp@4.6.0` через `.mcp.json` — только имена библиотек и общие вопросы, через ECC `docs-lookup`. (4) Serena MCP `v2.1.0` через `.mcp.json` (uvx из GitHub) — локальная навигация по коду, с S02. Промпты — `docs/implementation/tooling/`. ECC `ck`, memory-MCP третьих сторон не используются.",
  why="Всё сохранение контекста в репозитории и проверяемо; внешний трафик ограничен именами библиотек.", impact="Процесс разработки", risks="Serena запускается из GitHub-тега без проверки хэша; запуск вне MCP заблокирован классификатором, работоспособность проверяется владельцем через `/mcp`. Context7 — сторонний сервис (Upstash)", tests="Hook выдаёт валидный JSON и не пишет файлы; `/mcp` показывает серверы"))

ADRS.append(dict(id="ADR-041", title="Platform primitives S02: курсоры, ошибки, корреляция, error boundary, порты", status="ACCEPTED", owner=IL,
  context="S02 реализует примитивы без БД; DOC-006 §16 задаёт таксономию ошибок, но не форму курсора, не источник request id и не форму портов S07. Review S02 (fastapi/security/type-design) выявил 500-ответ без корреляции, утечки в spans/логах, слабые порты.", reqs="API-MVP (общие HTTP правила); SEC-MVP; OBS", docs="DOC-006 §5, §16; ADR-008, ADR-024, ADR-025, ADR-027; security.md",
  alts="Starlette exception handler для 500; ck-подобные библиотеки пагинации; структурное логирование через structlog", decision="(1) Курсор: `base64url(payload).base64url(HMAC-SHA256)`, MAC с префиксом домена `ai-res.cursor.v1`, payload = версия, key id, subject, audience (endpoint+сортировка), digest фильтров (организация/проект передаются в фильтрах), `exp`, keyset; TTL обязателен (значение задаёт контракт endpoint — WORKING); невалидный курсор → 400 `VALIDATION_ERROR` (остальные ошибки валидации — 422). (2) Error boundary — innermost middleware: 500 формируется внутри стека, поэтому request id, traceparent и span применяются; в spans нет exception message/stacktrace (только статус ERROR), в логах только тип исключения. (3) Request id: валидный клиентский принимается (fullmatch), иначе генерируется; traceparent — дочерний span от валидного входящего контекста, в ответе traceparent собственного span. (4) Логи: extras под `ctx`, redaction по ключам и значениям, uvicorn.error/access через тот же formatter, query string отбрасывается. (5) Порты S07: `Principal`, `ServiceIdentity`, `PolicyDecision` (валидируется), `AuditRecord` (enum outcome), `IdempotencyStorePort` с `begin/complete` и состояниями NEW/REPLAY/IN_PROGRESS/CONFLICT; `decide_fail_closed` требует timeout, возвращает только ALLOW. (6) Конфиг: unknown/регистр/секрет в env — отказ запуска; `create_app_from_env` требует cursor key file. (7) 412 `VERSION_CONFLICT` для устаревшего ETag; 409 `AGGREGATE_VERSION_CONFLICT` — на уровне хранилища.",
  why="Закрывает fail-open пути и утечки, найденные тремя независимыми ревью; формы портов фиксируются до S07.", impact="S07, S08–S12, S13", risks="Формат курсора и TTL — WORKING; идемпотентность port принимает plaintext-ключ (HMAC внутри реализации S07)", tests="backend/tests/unit/test_platform.py (56 тестов), tests/architecture/test_import_rules.py"))

# ADR-042…049 were first written directly into the log (S03/S04); `date` overrides D per entry.
ADRS.append(dict(
  id='ADR-042',
  title='MinIO и mc собираются из закреплённых исходников (официальный образ недоступен)',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DOC-015 §5.3/§12.2 требуют MinIO и образ по digest; `minio/minio` и `quay.io/minio/minio` публично недоступны (pull denied), сообщество публикует архивные или сторонние образы.',
  reqs='INF-MVP (MinIO), THR-017',
  docs='DOC-015 §5.3, §12.2, §14',
  alts='`bitnamilegacy/minio` (архив без патчей); `ghcr.io/coollabsio/minio` (неизвестная модель доверия); отложить MinIO (запрет пустых сервисов). Выбор владельца в сессии S03: сборка из исходников.',
  decision='`infra/images/minio/Dockerfile`: multi-stage, `golang:1.27.4-bookworm@digest`; `git clone --branch <tag>` + проверка commit SHA (minio `RELEASE.2025-10-15T17-29-55Z` 9e49d5e…, mc `RELEASE.2025-08-13T08-35-41Z` 7394ce0…); `go get` минимальных исправленных версий уязвимых транзитивных зависимостей (x/net, x/crypto, compress, grpc, amqp091-go, thrift, jsonparser, go-jose, otel sdk — списки по деревьям); рантайм `debian:bookworm-slim@digest`, non-root uid 10002, `/data` принадлежит рантайм-пользователю. Не исправленные prometheus CVE — в `vulnerability-exceptions.yaml`.',
  why='Воспроизводимый источник под контролем проекта; находки сканера сокращены с 44/27 до 2/2 HIGH/CRITICAL; сборка и runtime-набор проходят.',
  impact='S03, S27, S28, S32',
  risks='Мы отвечаем за патчинг MinIO (поддержка community-ветки неясна); AGPL-3.0 — license review перед релизом; изменённый граф зависимостей не проверялся апстримом (смягчение: runtime-набор bucket/versioning).',
  tests='runtime: MinIO healthy, бакеты и versioning через новый mc; скан собственных образов 0 HIGH/CRITICAL с исключениями',
))

ADRS.append(dict(
  id='ADR-043',
  title='Supply chain S03: SBOM, скан образов, политика исключений',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DOC-015 §14 требует SBOM, vulnerability scan, управление исключениями; первый скан дал десятки HIGH/CRITICAL во всех собственных образах и сотни в сторонних.',
  reqs='THR-017, THR-013, DOC-015 §14',
  docs='DOC-015 §12.2, §14.1–14.7',
  alts='Блокировать все образы (стек не собрать до апстрим-патчей); не блокировать ничего; cosign на всё (нет подписей у большинства вендоров).',
  decision='Syft (SPDX JSON) и Trivy запускаются из образов, закреплённых по digest, над архивами `docker save` (docker.sock не монтируется). Собственные образы `ai-res/*` — блокирующий gate (exit 1 при HIGH/CRITICAL с доступным исправлением); сторонние закреплённые образы — report-only в `infra/releases/scan/` и в KNOWN_GAPS. Исключения: `infra/security/vulnerability-exceptions.yaml` (cve, component, rationale, compensating_controls, owner, expires); просроченная или неполная запись падает. Даты expires — предложения Implementation Lead. Backend: pip-audit по locked runtime-зависимостям. Образ api без pip/setuptools (вендоренные библиотеки давали HIGH).',
  why='Gate достижим и честен: блокирует то, что мы можем исправить, и не скрывает остальное.',
  impact='S03, S37',
  risks='Сторонние образы остаются с известными HIGH/CRITICAL (Temporal server 146, UI 117, admin-tools 291, otel 61, Postgres 26 на момент S03); подписи cosign не проверяются; Trivy 0.58.1 — устаревший сканер, обновляется Renovate.',
  tests='tests/test_vuln_exceptions.py; supply_chain.sh на живых образах (exit 0)',
))

ADRS.append(dict(
  id='ADR-044',
  title='Состав и жёсткость локального стека S03 (образы, сети, healthchecks, секреты в процессах)',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='Нужен воспроизводимый локальный стек, удовлетворяющий DOC-015 §9 и промпту S03, при конкретных ограничениях образов и отсутствии health-эндпоинта в контракте.',
  reqs='INF-MVP-001..041, THR-005, THR-013, PERSIST-023 (сетевая часть), ADR-020, ADR-028, ADR-036',
  docs='DOC-015 §4.4, §5, §6, §9; DOC-019 §3–4',
  alts='Один сетевой сегмент; publish admin-портов на loopback; `temporalio/auto-setup`; стандартный entrypoint Postgres с POSTGRES_PASSWORD_FILE.',
  decision='(1) Образы по tag+digest: Caddy 2.11.9, Postgres 16.15, Temporal server 1.29.7 / admin-tools 1.29.7 / UI 2.49.1, otel-collector 0.116.1, python 3.13.18; (2) сети ingress (единственная не-internal, только Caddy), app/data/admin — `internal: true` (egress deny-by-default, нет шлюза), egress — без участников до S15/S16/S28; наружу `127.0.0.1:8443`; Temporal UI и MinIO console — только admin, недоступны с хоста; Manager/Worker никогда не в data; (3) Caddy пересобран без file capability (`setcap -r`), иначе exec падает при cap_drop ALL; (4) Postgres: собственный entrypoint (`initdb --pwfile`, SCRAM-only, TLS с локальным CA, `pg_hba.conf` по ролям/БД с финальным `reject`, перезаписывается при старте), потому что штатный экспортирует POSTGRES_PASSWORD в окружение процесса; Temporal/provisioning подключаются по TLS с проверкой хоста; (5) Temporal: пароль читается из secret-файла в окружение только процесса `temporal-server`/`temporal-sql-tool` (шаблон конфига принимает пароль лишь из env) — вне `docker inspect`, исключение явно описано; отдельная `temporal_visibility_db` под ролью `temporal` (visibility-схема Temporal конфликтует по `schema_version` с основной) — деталь реализации Temporal, не доменная БД; namespace `ai-res`, retention 72h — WORKING dev default (OD-02); (6) api healthcheck — liveness (любой HTTP-ответ), т.к. health-эндпоинт без контракта запрещён; otel-collector без healthcheck (distroless) — исключение в check_compose; (7) лимиты памяти/pids — WORKING dev значения; (8) schema `langgraph` и роль `ai_res_checkpointer` создаются provisioning-job (ADR-036), доменные роли — S05.',
  why='Соответствие baseline при проверяемых отклонениях, каждое зафиксировано.',
  impact='S03, S04, S05, S11, S13, S23',
  risks='Третья БД Temporal; пароль Temporal виден в /proc процесса; liveness ≠ readiness; Manager/Worker → Temporal сеть не решена (G-38).',
  tests='runtime: 77 тестов (сегментация, egress, hardening, секреты, роли); tests/test_check_compose.py: 27',
))

ADRS.append(dict(
  id='ADR-045',
  title='Схема dev-секретов: SOPS+age, случайные значения, идемпотентная материализация',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DOC-019 §3 / DOC-015 §11.4: секреты в Git только зашифрованными; default credentials запрещены; локальный запуск из чистого клона.',
  reqs='SEC-MVP (secrets), DOC-019 §3, §8',
  docs='DOC-019 §3–4, §8; DOC-015 §9.3, §11.4',
  alts='Секреты в `.env`; фиксированные dev-пароли; генерация при каждом запуске.',
  decision='`make secrets-dev` (`infra/scripts/secrets_dev.py`): age-ключ создаётся вне репозитория (`~/.config/ai-res/age/keys.txt`, 0600, отказ при широких правах), секреты — `secrets.token_urlsafe(48)`, шифруются SOPS в `infra/secrets/encrypted/local.enc.yaml`, расшифровка в `infra/secrets/runtime/` (git-ignored, 0600/0700). Существующие секреты не перегенерируются; материализация идемпотентна и пишет файлы на месте (замена файлов ломает bind mount запущенных контейнеров — найдено тестом). В CI (`AI_RES_SECRETS_WORLD_READABLE=1`) файлы 0644/0755 из-за Linux bind mount с разными uid контейнеров. Сканер репозитория (`scan_secrets.py`) ищет ключи, литеральные присвоения, URL с учётными данными, текущие значения секретов и незашифрованные файлы в `encrypted/`. Зашифрованный файл per-machine (age-ключ разработчика), не коммитится; DOC-015 §17.17 («секреты в Git зашифрованы SOPS») относится к общим секретам поставки, которых в S03 нет. Локальный TLS CA/сертификат Postgres генерируются вместе с секретами.',
  why='Нет default credentials и plaintext в Git; воспроизводимо; ключ вне репозитория.',
  impact='S03, S07',
  risks='Файл `local.enc.yaml` per-machine и не коммитится (git-ignored): шифрован под ключ конкретной машины, на чужой машине и в CI секреты генерируются заново, при отсутствии ключа и наличии файла — явная ошибка; ротация и аудит доступа не реализованы (runbook DOC-019 §5 — позже); sops/age ставятся brew (локально) и из закреплённых релизов (CI), хэш age закреплён по первому проверенному скачиванию (апстрим не публикует checksums).',
  tests='runtime: секреты отсутствуют в inspect/env/логах/слоях образов; tests/test_scan_secrets.py: 8',
))

ADRS.append(dict(
  id='ADR-046',
  title='Роли PostgreSQL S04: provisioning под суперпользователем, ревизия PDB-0001 только проверяет, drift-коррекция',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='Промпт S04 требует «PDB-0001: создание schemas, ролей». Но `ai_res_migrator` по Strategy §1.5/§2 не имеет CREATEROLE, а пароли не задаются SQL-миграцией (Strategy §2, DOC-069 §3): роли и пароли миграция создать не может. DOC-069 (WORKING) — шаблон, не исполнимая история.',
  reqs='PERSIST-005..007, DBM-006, DBM-012, DBM-016; SEC P0',
  docs='DOC-068 §1.5–§1.9, §2; DOC-072 §9; DOC-069 (WORKING); ADR-015, ADR-034, ADR-036',
  alts='(а) Выдать migrator CREATEROLE (нарушает DOC-068 §1.8); (б) создавать роли в ревизии под суперпользователем (migrator не суперпользователь); (в) provisioning вне Alembic + проверка в ревизии',
  decision='(в). `infra/config/postgres/provision_roles.sql` (psql, суперпользователь, часть one-shot `postgres-provision`; тот же файл использует тестовый harness) создаёт группы `*_group` (NOLOGIN) и LOGIN-роли `ai_res_migrator/api/outbox_dispatcher/event_consumer/auditor/backup` (+ `ai_res_checkpointer_group`, членство `ai_res_checkpointer`), задаёт SCRAM-пароли из Compose secrets, атрибуты (NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS), владельца БД, `GRANT CONNECT`, role-level `search_path=pg_catalog`, `statement_timeout 15s`, `lock_timeout 2s`, `idle_in_transaction_session_timeout 30s` (значения шаблона DOC-069 §8, WORKING). Скрипт **идемпотентен и возвращает к эталону**: снимает любые членства вне ожидаемого набора (`REVOKE … GRANTED BY`), сбрасывает ADMIN OPTION и явно задаёт опции (`WITH ADMIN FALSE, INHERIT, SET`), `RESET ALL` для role-wide и role-in-database настроек, отзывает лишние `CONNECT`, возвращает владельца БД. Группы — `INHERIT TRUE, SET FALSE`; migrator→owner — `INHERIT FALSE, SET TRUE`. Ревизия PDB-0001 выполняет fail-fast preflight (роли существуют, атрибуты, NOLOGIN у групп, нет членства в owner, search_path зафиксирован, `platform` принадлежит owner) и **ничего не чинит**; затем создаёт 17 схем (`CREATE SCHEMA … AUTHORIZATION ai_res_owner`, строго, без IF NOT EXISTS), `REVOKE ALL … FROM PUBLIC`, `GRANT USAGE` группам (api: все 18 схем; outbox: operations, agents, audit; consumer: operations, agents, execution, audit; auditor: audit — по ADR-034), `ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE … FROM PUBLIC` (содержательно — для функций и типов). `public`: у PUBLIC отозваны все права (в т.ч. USAGE); расширениям в `public` (pgvector, S27) потребуется отдельное явное решение. `ai_res_backup`: роль без прав на данные и без строки в `pg_hba`; профиль привилегий — S32. `postgres` в `pg_hba` не ограничен по адресу (наследие S03, G-44).',
  why='Соблюдает DOC-068 (migrator без CREATEROLE, пароли вне миграций) и даёт проверяемую базовую линию: слабая настройка ролей останавливает миграцию целиком (транзакционный DDL откатывает схемы). Drift-коррекция закрывает класс «ручная выдача прав переживает повторный provisioning» — найден тестами.',
  impact='S03 (provision.sh, hba, secrets), S05+ (грантовые ревизии наследуют роли)',
  risks='Отклонение от формулировки промпта («ревизия создаёт роли») обосновано DOC-068; миграция не может быть «самодостаточной» на пустом кластере — нужен provisioning (так же, как для БД и `langgraph` в S03). Редактирование уже применённой ревизии: PDB-0001 правилась до первого общего применения, только локальный dev и тестовые контейнеры.',
  tests='test_migrations (sabotage ×5, drift-коррекция), test_roles_and_grants (атрибуты, SCRAM, DDL-отказы, матрица USAGE), SABOTAGE ×37, runtime test_persistence',
))

ADRS.append(dict(
  id='ADR-047',
  title='Миграционная среда S04: Alembic env, SET ROLE owner, advisory lock, одноразовая служба `migrate`, WORKING-таймауты',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='Blueprint §4.2/§10 задают требования к env.py и отдельному migration job, но не конкретику: как создать schema `platform` для `alembic_version`, как сериализовать запуски, как запускать job в образе, какие таймауты.',
  reqs='PERSIST-001, -003, -004, -020; DBM-001..003',
  docs='DOC-072 §4, §8, §10; DOC-068 §4; DOC-064 §11; ADR-003, ADR-011, ADR-035',
  alts='Запуск миграции при старте API (запрещён); отдельный образ migrate; `Base.metadata.create_all` (запрещён)',
  decision="(1) `alembic.ini` без DSN, `script_location = ai_res.db:migrations` (работает и из установленного пакета в образе). (2) `env.py`: настройки только из `AI_RES_DB_*` (пароль — файл), отказ под SUPERUSER/BYPASSRLS, `pg_advisory_lock(hashtextextended('ai_res.alembic.migrations',0))` (ожидание ограничено `lock_timeout`), `SET ROLE ai_res_owner`, bootstrap-исключение `CREATE SCHEMA IF NOT EXISTS platform` (Alembic создаёт version table до первой ревизии), `version_table_schema=platform`, allowlist 18 схем через `include_name` (нет `public`, `temporal`, `langgraph`), `compare_type=True`, `compare_server_default=False` до первого drift review; вложенный cleanup в `finally` (rollback → RESET ROLE → unlock с проверкой результата). (3) Одноразовая Compose-служба `migrate`: тот же образ `ai-res/api:dev`, команда `alembic upgrade head`, TLS verify-full, секреты — только `migrator_db_password` и CA; `api` ждёт её завершения (порядок, не запуск). (4) Таймауты миграционного профиля — WORKING: statement 60 с, lock 5 с, idle-in-transaction 60 с (технические значения, не SLO; OD-02). (5) Формат revision: filename `NNNN_intent.py`, id — hex; downgrade PDB-0001 — `NotImplementedError` (forward-fix). (6) Alembic присутствует в образе API (один образ с `migrate`); API-процесс его не импортирует (AST-тест). (7) PERSIST-002 (previous revision): до второй реальной ревизии тривиален; тест — в S05. PERSIST-004 доказан синтетической test-only ревизией с `autocommit_block` + `CREATE INDEX CONCURRENTLY` (ADR-011).",
  why='Единственный путь DDL, сериализован, не требует суперпользователя, воспроизводим из образа.',
  impact='S05+ (ревизии), infra (Compose), CI',
  risks='Alembic в runtime-образе API — лишняя поверхность (решение: допустимо, отдельный stage — позже, G-45); значения таймаутов WORKING; `long_transaction` в preflight best-effort без `pg_read_all_stats` (G-41).',
  tests='test_migration_graph, test_no_startup_migration, test_migrations (lock, superuser refusal, autocommit), runtime (migrate exit 0, idempotent rerun)',
))

ADRS.append(dict(
  id='ADR-048',
  title='Контроль дрейфа и аудит: reviewed snapshot (pg_dump + каталог), audit SQL как release gate, positive controls',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='Промпт требует «Design snapshot schema_snapshot.sql + drift check» и «Grants audit автоматизирован в CI»; формат не задан. Независимое review показало, что проверки без positive control проходят вакуозно.',
  reqs='PERSIST-024, DBM-006, DBM-012, DBM-017; Blueprint §9–§10, §12',
  docs='DOC-072 §9, §10, §12; DOC-068 §8',
  alts='Сравнение с design DDL DOC-065 (WORKING, не соответствует принятым решениям ADR-011/034); `alembic check` (не видит роли/гранты/RLS)',
  decision='(1) Snapshot `backend/ops/postgres/schema_snapshot.sql` = нормализованный `pg_dump --schema-only` (тот же major внутри контейнера; схемы, владельцы, ACL, default privileges, политики; без комментариев/`\\\\restrict`) + каталожная секция (атрибуты ролей, членства с опциями, role settings, ACL БД; без паролей). Drift = неравенство после `upgrade head`; обновление — `make db-snapshot` и ручной разбор diff; в CI установка `UPDATE_SCHEMA_SNAPSHOT` запрещена. (2) Audit SQL в `backend/ops/postgres/` (`preflight`, `postflight`, `grants_audit`, `rls_coverage`) возвращают строки-нарушения; пусто = пройдено; `audit.sh` — release gate (exit 1 при нарушении, exit 2 при ошибке/пустом файле). RLS-gate default-fail: любая таблица доменных схем без ENABLE+FORCE RLS и политики должна быть в явном `exempt` (сейчас только `platform.alembic_version`). (3) Каждая проверка имеет positive control: параметризованный тест портит состояние и ожидает конкретное имя нарушения (37 случаев), проверки отсутствующих ролей не проходят вакуозно, gate на живом стеке падает на реально испорченном состоянии. (4) Ложное срабатывание (автоматические array-типы строк таблиц) исключено явно.',
  why='Дрейф и ослабление прав обнаруживаются автоматически и воспроизводимо; пустой результат имеет смысл только вместе с контролем.',
  impact='S05+ (каждая таблица: RLS, exempt, snapshot), CI',
  risks='Snapshot привязан к PG 16.15 (minor — осознанная перегенерация); `rls_coverage` не доказывает корректность выражения политики (это тесты S05); матрица USAGE — только snapshot и тест.',
  tests='test_schema_drift (3), SABOTAGE (37), test_audits_report_missing_roles, runtime audit gate ×3',
))

ADRS.append(dict(
  id='ADR-049',
  title='Runtime-слой persistence: engine, Unit of Work, tenant context (один раз на транзакцию), конфигурация db_*',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='Blueprint §7–§8 требуют явные транзакции, transaction-local контекст и pool-политику; выбор конкретных механизмов (async, сброс контекста, ошибки begin) оставлен реализации.',
  reqs='PERSIST-008..010, DBM-008..010, DBM-014; INF-MVP',
  docs='DOC-072 §7, §8; DOC-068 §3, §7; ADR-008',
  alts='Session-level `SET`; middleware, ставящий контекст на соединение; `autobegin` сессии',
  decision="(1) `db/engine.py`: async engine psycopg 3, `pool_pre_ping`, `pool_recycle` из настроек, `pool_reset_on_return=rollback`; libpq `options` задают `search_path=pg_catalog`, `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`; `application_name`; TLS `verify-full` (отключение допустимо только в environment local/test); пароль только из файла, URL не логируется. (2) `db/tenant_context.py`: `set_config(:name,:value,true)` с bind-параметрами, принимает только `UUID`, пустой project → `''`; политики используют `NULLIF(current_setting(…, true), '')::uuid`. (3) `db/session.py`: `UnitOfWork` — BEGIN при входе, COMMIT только при чистом выходе, ROLLBACK при любом исключении, `autobegin=False`, закрытие сессии при сбое BEGIN; `with_tenant` допускается **один раз** за транзакцию (смена tenant внутри транзакции — `RuntimeError`). (4) Поля `db_*` добавлены в строгий `Settings` (секреты — только `*_file`). (5) Import-linter: `ai_res.db` не зависит от `api`, `modules`, `llm`.",
  why='Контекст не может пережить транзакцию или смениться внутри неё; ошибка конфигурации — отказ запуска.',
  impact='S05–S10 (репозитории, Application Services), S07 (Policy Engine ставит контекст после авторизации)',
  risks='S04 не содержит доменных таблиц: поведение RLS проверено на test-only probe-таблице с политикой формы DOC-069; реальные политики и негативные тесты — S05. GUC-контекст не защищает от произвольного SQL под API-идентичностью (Strategy §1.12) — документированное ограничение.',
  tests='test_tenant_context (11), test_db_layer (unit), мутация session-level SET обнаружена',
))


ADRS.append(dict(
  id='ADR-050',
  title='S05 срез A: физический дизайн iam / organization / project, общие row guards, справочник ролей',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DDL v1.0 не содержит iam/organization/project; ADR-016 поручает спроектировать таблицы из DOC-005. Словарь ролей DOC-069 / Identity Access Control v1.5 §4 — «стартовый, не окончательная матрица» (WORKING).',
  reqs='DATA-MVP, PERSIST-005..011; DOC-005 §5, §15, §16',
  docs='DOC-005 §5.1–5.3, §15, §16; Identity Access Control v1.5 §4; Blueprint §7, §9; Roles_RLS_v1.0.sql',
  alts='(а) глобальные iam.users без organization_id и RLS через членство — INSERT пользователя невозможен до членства, вход по e-mail до выбора tenant неразрешим; (б) CHECK-словарь ролей — расширяется только пересозданием ограничения; (в) триггеры вместо composite FK',
  decision="(1) Все iam-таблицы (users, credentials, sessions, mfa_factors, mfa_recovery_codes, service_identities) несут `organization_id NOT NULL` (домашняя организация, MVP: одна организация на пользователя; многооргановость — через organization.memberships); связь с пользователем — composite FK `(organization_id,user_id)`, межорганизационные связи невозможны на уровне БД. (2) RLS FORCE + политика `organization_id = NULLIF(current_setting('app.organization_id', true),'')::uuid` (organizations — по `id`), `FOR ALL TO ai_res_api_group`, USING = WITH CHECK; grants SELECT/INSERT/UPDATE, без DELETE. Контекст проекта на этих таблицах не требуется (org-level доступ; проектная изоляция — на work/operations/agents/execution). (3) Роли — справочник `iam.roles(code, org_level, project_level)` с семью значениями из IAM v1.5 §4 (WORKING); memberships/project_memberships ссылаются composite FK `(role_code, org_level|project_level)`, поэтому проектная роль не назначается на уровне организации и наоборот. Справочник не tenant-данные: исключён из RLS в `rls_coverage.sql` с причиной, а новая проверка `exempt_table_writable_by_runtime` требует, чтобы runtime не мог писать в исключения. (4) Секреты: credentials принимают только `$argon2id$…`; sessions хранят только 32-байтовые digest токена и CSRF (сырой токен не хранится); TOTP-секрет — `secret_ciphertext` (шифрование и ключи — S07/Secrets). (5) Общие guards в `platform`: `touch_row()` (row_version обязан расти ровно на 1, иначе 23000; выставляет updated_at), `keep_columns_immutable(cols…)` (идентификаторы и scope-колонки), `reject_modification()` (для immutable-таблиц следующих срезов). Функции не SECURITY DEFINER. (6) Минимальные словари статусов (organizations/projects ACTIVE|ARCHIVED, users/service_identities ACTIVE|DISABLED, memberships ACTIVE|SUSPENDED|REVOKED) и service_kind — предложение Implementation Lead, WORKING, расширяются ревизией.",
  why='Единообразный tenant-контур, невозможность cross-org связей без доверия к приложению, отсутствие секретов в БД, обязательная оптимистичная блокировка на уровне БД.',
  impact='S05 срезы B–E, S06, S07 (auth), S08–S09 (repositories)',
  risks='Вход по e-mail до установки tenant-контекста при FORCE RLS даёт ноль строк: механизм pre-auth lookup (организация по slug/хосту, узкая функция из allowlist SECURITY DEFINER в grants_audit) — решение S07, фиксируется в KNOWN_GAPS. Словари статусов и ролей WORKING.',
  tests='test_identity_org_project_schema (26): default-deny ×9, A/B isolation, WITH CHECK, composite FK ×3, role FK, argon2id CHECK, digests, row_version CAS, immutable scope, no DELETE/TRUNCATE/DDL, auditor/dispatcher denied; rls_coverage/grants_audit/postflight clean',
))

ADRS.append(dict(
  id='ADR-051',
  title='S05 срез B: operations, operation_events и work — целостность на уровне БД, append-only события, закрытые Operation',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DDL v1.0 §1–§3 задаёт Operation, события и связь Task↔Operation, но не задаёт work.epics/tasks/task_dependencies; OAS Task требует `epicId`, но не задаёт словари статуса/приоритета/типа.',
  reqs='PERSIST-005..012, TX-01..TX-03; ADR-011, ADR-012, ADR-013, ADR-034',
  docs='DOC-065 (DDL v1.0) §1–§3; DOC-064 §5.1–5.4, §6; Domain Model v1.9 §5.4–5.5, §10.2, §25–26; State Machine v1.2',
  alts='(а) последовательность событий только контрактом репозитория (риск молчаливого разрыва); (б) обновляемые события с audit; (в) Task без Epic; (г) выдумать enum статусов Task',
  decision="(1) Greenfield: `work.tasks.operation_id NOT NULL`, `UNIQUE(operation_id,id)`, составной FK `(organization_id,project_id,operation_id)` на operations — Task невозможно привязать к Operation другого проекта. `epic_id NOT NULL` (OAS). Parent Operation и lineage `derived_from_task_id` (ADR-034) — тоже составные FK внутри проекта. (2) `operation_type` — справочник `operations.operation_types` (4 значения ADR-013), runtime только SELECT, исключён из RLS с причиной. (3) Целостность последовательности событий проверяется БД при COMMIT (deferred constraint trigger на событиях и на `operations.last_event_sequence`): число событий = max(sequence) = last_event_sequence; контракт репозитория — UPDATE … `last_event_sequence+1` RETURNING под row lock, затем INSERT этой последовательности (MAX()+1 не используется). (4) События append-only для всех: нет UPDATE/DELETE/TRUNCATE у API и триггеры `reject_modification` (включая суперпользователя). RLS событий — через родительскую Operation (шаблон DOC-069 §7). (5) Terminal Operation замораживается полностью (`freeze_when_status_in`): статус не переоткрывается и ничего не меняется; терминальное событие добавляется в той же транзакции, что и переход. (6) Task создаётся только в открытой Operation (`require_open_operation`, ADR-012); rework = новая Operation + Task с `derived_from_task_id`. (7) Статус/приоритет/тип Epic и Task — только формат `^[A-Z][A-Z_]*$` (словарь не задан нормативно, G-49); `task_dependencies` — `dependency_type='BLOCKS'` (WORKING), SELECT/INSERT, циклы — детерминированная проверка домена до активации плана. (8) Отклонение от DOC-069 §5: `ai_res_outbox_group`/`ai_res_consumer_group` не получают SELECT на таблицы событий (без политики FORCE RLS даёт 0 строк; G-50).",
  why='Инварианты TX-01..03 и PERSIST-012 держатся независимо от дисциплины приложения; нет молчаливого разрыва последовательности, переоткрытия terminal и cross-project связей.',
  impact='S05 срезы C–E, S08–S11, S21',
  risks='Deferred trigger добавляет два запроса на commit на событие (измерить в S38); terminal-заморозка запрещает поздние обновления progress — проверить с Temporal-интеграцией (S11); словари Task WORKING.',
  tests='test_operations_work_schema (23): default-deny ×5 (+ org-only context), изоляция A/B и sibling project, NOT NULL operation_id, Task в чужой/terminal Operation, rework chain, immutability, dependencies (self/cross/dup), append-only (api и superuser), contiguity/gap/duplicate, PERSIST-012 (8×5 потоков), rollback-атомарность, no access для outbox/consumer/auditor',
))

ADRS.append(dict(
  id='ADR-052',
  title='S05 срез C: agents и execution — инварианты Readiness Gate на уровне БД, insert-only история и результаты',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DDL v1.0 §4–§6 и State Machine v1.2 расходятся: DDL допускает evaluation_status IN_PROGRESS и 5 derivation_reason, JSON v1.2 (новее) — только COMPLETED/EVALUATOR_ERROR и 6 причин (+SPECIALIST_HANDOFF). Таблицы worker_results в DDL нет (ADR-016).',
  reqs='PERSIST-005..012, ADR-016, ADR-023, ADR-034; Readiness Gate invariants (State Machine v1.2)',
  docs='DOC-065 §4–§6; DOC-064 §5.3–5.4, §6 (п.1, 7, 11, 12); State Machine v1.2; Operation & Readiness Gate Decision v1.6 §3; Domain Model v1.9 §11.2',
  alts='(а) следовать DDL с IN_PROGRESS и UPDATE оценки до завершения; (б) проверять инварианты старта только в приложении; (в) FK worker_runs→tasks только по (operation_id,id)',
  decision="(1) Расхождение DDL↔JSON решено в пользу JSON v1.2 (последняя BASELINED версия): `evaluation_status ∈ {COMPLETED, EVALUATOR_ERROR}`, `COMPLETED ⇔ gate_outcome и evaluated_at заданы` (EVALUATOR_ERROR не может нести READY — fail-closed), поэтому оценка вставляется один раз и не обновляется; derivation_reason ∈ 6 значений. Согласование — NCP-02. (2) `worker_runs → tasks` составным FK `(organization_id, project_id, operation_id, task_id)` (добавлен `UNIQUE(org,project,operation_id,id)` на tasks): WorkerRun не может ссылаться на Task из другой Operation/проекта; WorkerRun не создаётся в terminal Operation (тот же guard, что для Task). (3) Старт: CHECK — статусы, достижимые только после старта (STARTING … UNVERIFIED), и `started_at` требуют `started_with_readiness_evaluation_id`; trigger `guard_worker_run_start` допускает установку только на COMPLETED READY/READY_WITH_LIMITATIONS (BLOCKED, STALE, EVALUATOR_ERROR отклоняются), отсутствие или чужая оценка отсекается deferred composite FK `(id, started_with…) → evaluations(worker_run_id,id)`; после установки ссылка неизменна. `latest_readiness_evaluation_id` меняется до и после старта. (4) readiness_evaluations, readiness_check_results, worker_run_events, worker_results — INSERT-only: нет UPDATE/DELETE у API и trigger `reject_modification` для всех, включая суперпользователя; TRUNCATE закрыт триггером либо самим PostgreSQL (таблица под FK). Check results допускаются только в транзакции, создавшей оценку (`created_at = now()`), иначе завершённая оценка «пополнялась» бы задним числом. (5) worker_results: один результат на run (rework = новый run, ADR-016), `payload` — объект (jsonb), `contract_version`, SHA-256 payload; scoped-unique `(org, project, worker_run_id)`, чтобы чужой tenant получал FK-ошибку, а не unique-оракул (G-52). Поля контракта DOC-007 — WORKING: структура payload валидируется контрактом в приложении. (6) Terminal WorkerRun заморожен целиком; `finished_at ⇔ terminal`; lineage: `derived_from` ⇔ `derivation_reason`, внутри проекта. (7) События WorkerRun — контроль последовательности при COMMIT тем же deferred trigger, что у Operation (ADR-051). RLS детей — через родительский WorkerRun (шаблон DOC-069). (8) Статус CANCEL_REQUESTED добавлен в словарь WorkerRun (есть в transitions JSON, нет в DDL CHECK).",
  why='Gate нельзя обойти даже ошибкой приложения: невозможно записать запуск без валидной неизменяемой оценки, переписать историю или результат.',
  impact='S05 срезы D–E, S13 (Gate), S14–S15 (Worker), S11 (Temporal activities)',
  risks='FK на WorkerDefinitionVersion/ContextPackageVersion отложены (G-51); переходы не в БД (G-53); same-transaction guard требует, чтобы evaluator писал оценку и проверки одной транзакцией (это и есть проектный контракт, проверить в S13).',
  tests='test_agents_execution_schema (23): default-deny ×5, изоляция, scope/operation FK, terminal Operation, started⇒evaluation, BLOCKED/STALE/ERROR/чужая оценка, immutability started_with, shape оценки, insert-only (api + superuser), same-transaction check results, worker_results (unique/object/immutable/foreign FK), freeze terminal, lineage, events sequence/append-only, no access outbox/consumer/auditor',
))

ADRS.append(dict(
  id='ADR-053',
  title='S05 срез D: outbox, inbox, audit_events, idempotency_records и reference aggregate_types — права и RLS по ADR-034',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Implementation Lead (делегированные полномочия, Master Implementation Initialization)',
  context='DDL v1.0 §7–§9 не содержит tenant-колонок у outbox/idempotency и таблицы audit_events; DOC-069 даёт API UPDATE на idempotency и outbox-группе SELECT/INSERT/UPDATE; ADR-034 требует INSERT-only для API и cross-tenant политики сервисных групп.',
  reqs='PERSIST-012..014, TX-01, ADR-016, ADR-024, ADR-034 (2)(4), THR-015',
  docs='DOC-065 §7–§9; DOC-064 §5.5–5.7, §6; DOC-069 §5, §7; Domain Model v1.9 §13',
  alts='(а) политика `USING (true)` для outbox без allowlist (ломает default-fail rls_coverage); (б) tenant GUC для dispatcher/consumer (они обслуживают все tenants); (в) outbox через EXISTS по агрегату (полиморфный aggregate_type)',
  decision="(1) `audit.outbox_events` и `audit.audit_events` получили `organization_id`/`project_id` (outbox: NOT NULL, audit: project NULL для org-level действий), составные FK на projects — иначе RLS строится только полиморфным EXISTS. (2) API: INSERT-only на outbox и audit_events (политики FOR INSERT WITH CHECK по scope; без SELECT/UPDATE/DELETE/TRUNCATE) — THR-015. Dispatcher: SELECT + UPDATE только delivery-колонок (status, available_at, attempt_count, last_error_code, lease_owner, lease_until, published_at), политики `USING (true)` только для `ai_res_outbox_group`; SKIP LOCKED работает (UPDATE-привилегия на колонки). Consumer: INSERT + UPDATE(status, processed_at, error_code) на inbox, cross-tenant, без доступа к outbox и доменным таблицам. Auditor: SELECT audit_events по organization context, default-deny без него. Тriggers `keep_columns_immutable` дублируют колонковые гранты для owner-пути. (3) `rls_coverage.sql`: «always true» допустим только для трёх именованных политик (`cross_tenant` allowlist с причиной) и только если роли политики ⊆ {outbox_group, consumer_group}; иначе нарушение (sabotage-тест). `audit.aggregate_types` — reference, исключён из RLS с причиной, без runtime grants (FK проверяет владелец). (4) Состояния: `IN_FLIGHT ⇔ lease_owner и lease_until`, `PUBLISHED ⇔ published_at`, `PROCESSED ⇔ processed_at`. (5) Atomicity: deferred trigger «outbox-строка описывает реальное событие своего агрегата (event_id, aggregate, sequence)» — orphan откатывает транзакцию; обратное направление остаётся в репозитории (G-54). Новый aggregate_type требует расширения функции в той же ревизии (иначе исключение). (6) audit_events иммутабельны для всех (reject_modification, включая owner/суперпользователя). (7) `platform.idempotency_records`: добавлены `organization_id`, `project_id`, `key_id` (ADR-024); ключ хранится только как HMAC-digest; unique `(organization_id, scope_type, scope_id, key_digest)` — scoped, чужой tenant не получает unique-оракул (G-52); fingerprint и ключевые поля иммутабельны, COMPLETED/REJECTED заморожены (replay читает, не переписывает), `completed_at ⇔ status ≠ IN_PROGRESS`; RLS: организация + `project_id IS NOT DISTINCT FROM` контекст проекта; DELETE нет.",
  why='Минимальные права каждому принципалу; журнал и outbox нельзя переписать; сервисные cross-tenant роли ограничены колонками и явно перечислены.',
  impact='S05 срез E, S07 (Audit/Idempotency), S09 (команды), S10 (dispatcher/inbox)',
  risks='Dispatcher видит envelope всех tenants — envelope не должен содержать секреты и полный контент (правило событий); lease/retry параметры WORKING; значения словарей audit WORKING (G-55).',
  tests='test_audit_platform_schema (14): allowlist cross-tenant + sabotage, API INSERT-only и scope, orphan/чужой outbox, unique/FK, атомарность в обе стороны, dispatcher cross-tenant+колонки+SKIP LOCKED+состояния, inbox дедуп/колонки, audit immutable + auditor per org, idempotency (scope, frozen, fingerprint, нет raw key), PERSIST-013 (10 потоков → 1 запись), reference read-only',
))

ADRS.append(dict(
  id='ADR-054',
  title='S05: CloudEvents-envelope Operation/WorkerRun событий строго по каноническим сообщениям AsyncAPI v1.6 (G-56, вариант A)',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Владелец проекта (выбор варианта A по G-56, 2026-11-11); детали реализации — Implementation Lead',
  context='Envelope из среза E содержал 8 нестандартных атрибутов верхнего уровня (`organizationid`, `aggregatetype`, …), без `dataschema`, `operationId`, `actor`, `transition`, с коротким `type`; AsyncAPI v1.6 для канонических сообщений требует ровно 9 атрибутов (`additionalProperties: false`) и `data` по `OperationWorkerRunEventData`. Колонка `audit.outbox_events.envelope` иммутабельна, поэтому исправлять форму надо до появления данных.',
  reqs='DOC-008 AsyncAPI v1.6; Event Model v1.4 §4–§5; State Machine v1.2 (operationEventTypes/workerRunEventTypes); coding-standards (CloudEvents, controlled registry); ADR-053',
  docs='AsyncAPI v1.6 components.messages (com.aires.operation.*.v1, com.aires.worker_run.*.v1), schemas.OperationWorkerRunEventData; Event Model v1.4 §4; API Contracts v1.10 §Events',
  alts='(B) оставить extension-атрибуты и менять контракт; (C) хранить внутреннюю запись и собирать wire-форму в dispatcher (S10); (D) гибрид A+C',
  decision="(1) `modules/events/envelope.py` строит envelope как чистую функцию: ровно specversion/id/source/type/subject/time/datacontenttype/dataschema/data; tenant, aggregate, operationId, actor, correlationId, causationId, reasonCode, transition, refs — в `data`; event-specific поля (`EventSpec.data`) — в `data.details`; необязательные поля опускаются, а не null. (2) `type = com.aires.<короткое имя>.v<schemaVersion>`; реестры коротких имён = State Machine v1.2 (drift-тест); неизвестный тип, актёр вне {SYSTEM,USER,MANAGER,WORKER,SERVICE} или major-версия вне {1} — ValueError до записи (fail-closed); CHECK на `actor_type` в таблицах истории. (3) `source`/`subject` выводятся из вида агрегата (`urn:aires:operations`, `operations/{id}`, `worker-runs/{id}`), а не передаются вызывающим; `append_event` принимает `operation_id` (для WorkerRun — владеющая Operation). (4) Deferred-триггер `audit.assert_outbox_matches_event` сверяет envelope со столбцами строки (id, type, eventId, organizationId, projectId, aggregateType/Id/Sequence): подделанный envelope чужого tenant отклоняется на COMMIT. (5) Контрактный тест (jsonschema+referencing, закреплены в uv.lock) валидирует envelope каждого из 36 канонических типов против настоящих схем AsyncAPI и проверяет, что схема отвергает прежнюю форму. (6) `data.eventType` НЕ включается: Event Model v1.4 §4 требует его, AsyncAPI запрещает — противоречие передано владельцу (NCP-09), следуем AsyncAPI.",
  why='Один envelope, соответствующий BASELINED контракту, без технического долга в неизменяемых outbox-строках; нарушение формы ловится тестом, а подделка tenant — базой данных.',
  impact='S10 (dispatcher/SSE/consumers читают envelope), S08–S09 (команды формируют EventSpec), S11 (Temporal activities), контрактные тесты событий',
  risks='WORKING и не зафиксированы нормативно: форма `dataschema` (`urn:aires:schemas:<type>`) и `source` WorkerRun-событий (`urn:aires:worker-runs`) — централизованы в envelope.py, смена = правка констант до S10 (иммутабельные строки до этого не появятся в production). `worker_run.created` есть в State Machine v1.2, но не имеет канонического сообщения в AsyncAPI v1.6: событие строится по тому же шаблону и в тесте названо явно как известный пробел (NCP-11), не молчаливое исключение. Утверждение «соответствует AsyncAPI» верно только для 36 смоделированных типов.',
  tests='tests/contract/test_event_envelope.py (11: реестры = State Machine, пробел AsyncAPI ровно `worker_run.created`, 36 типов × минимум/все опции валидны, схема отвергает старую форму/без dataschema/без operationId/актёр WORKER_RUN/eventType, fail-closed идентичность); test_audit_platform_schema (подделка envelope ×6 откатывает транзакцию); test_repositories (канонический envelope, неизвестный тип/актёр/версия отклоняются до записи)',
))

ADRS.append(dict(
  id='ADR-055',
  title='S05: migration-политики owner под FORCE RLS (ADR-034 п.5, вариант 1) и hardening по независимым review',
  status='ACCEPTED',
  date='2026-11-11',
  owner='Владелец проекта (выбор варианта 1 по H1, 2026-11-11); детали — Implementation Lead',
  context='Независимый architect-review нашёл, что ADR-034 п.5 («для migrator/owner при FORCE RLS — явные migration-политики; backfill проверяется тестом») не реализован, а PERSIST-017 идёт под суперпользователем на таблицах без RLS и ничего не доказывает: backfill тенантных таблиц под `ai_res_owner` увидел бы 0 строк и «успешно» ничего не сделал бы. Четыре review (database, security, silent-failure, architecture) нашли также дыры Gate и слабые тесты.',
  reqs='ADR-034 (5), ADR-052, ADR-035, PERSIST-005..012, PERSIST-017, security.md (P0), testing-and-verification.md (negative tests)',
  docs='Persistence Blueprint v1.0 §9; DOC-064 §6; State Machine v1.2 (invariants Gate); security.md',
  alts='(2) пересмотреть п.5 новым ADR и завести gap (выбрано не было); BYPASSRLS у migrator (запрещено); отключить FORCE для owner (ломает ADR-034 п.1)',
  decision="(1) Ревизия 0006: для КАЖДОЙ таблицы с ENABLE+FORCE RLS политика `p_<table>_owner_migration FOR ALL TO ai_res_owner`, включённая только при транзакционном флаге `app.migration_mode='on'` (`set_config(..., true)`); без флага owner остаётся default-deny, runtime-роли политику не получают. `rls_coverage.sql` падает (`owner_migration_policy_missing`), если у RLS-таблицы нет такой гейтированной политики — следующие ревизии обязаны её создавать; два sabotage-теста. Тест `test_owner_backfill_on_a_forced_rls_table_*` идёт реальным путём migrator → `SET ROLE ai_res_owner` (контроль: без флага 0 строк; с флагом — обе организации; флаг не переживает транзакцию; API с флагом ничего не видит). Backfill остаётся под `touch_row` (row_version+1 обязателен). (2) Gate: старт требует МАКСИМАЛЬНЫЙ `evaluation_number` run (BEFORE-guard и deferred-проверка на commit); `agents.worker_results` принимается только для run с `started_with_readiness_evaluation_id` и нетерминального (`FOR SHARE` на run); UNIQUE `(organization_id, project_id, task_id, attempt_number)`. (3) Immutable: `iam.sessions.absolute_expires_at` (+ CHECK idle ≤ absolute), `operations.completion_policy_version/snapshot`. (4) Envelope outbox привязан к событию и tenant триггером (ADR-054). (5) Репозитории: guard секретов на всех jsonb-границах (`assert_no_sensitive_keys` в platform.redaction, токены digest/ciphertext/hmac/signature), `ReadinessRepository.record` валидирует до первого SQL, `cas_update` отвергает пустые изменения, outbox `mark_*` — fencing (owner+attempt+срок lease) и лимит попыток `mark_failed`; `hide_parameters=True` у runtime engine. (6) Verification-проход (2026-11-11, по решению владельца блокировки — в рамках S05): триггер `execution.lock_run_for_evaluation` + `FOR NO KEY UPDATE` на run в `guard_worker_run_start` и `require_started_open_run` (оценка, старт и результат сериализуются; двойной submit результата не даёт deadlock); `app.migration_mode` выключается `on_version_apply` после каждой ревизии; триггер outbox привязывает также `operationId`, `source`, `subject`, `dataschema`, `event_type`, `schema_version`; правило аудита сравнивает точное выражение политики; guard секретов различает secret- и content-токены (ключи-ссылки `source_id` допустимы), `refs`, `reason_code`, `error_code` проверяются по формату.",
  why='Скрытые no-op миграции и обход Gate выбором выгодной оценки — тихие отказы, которые нельзя найти позже; защита должна быть в БД и подтверждена тестами под реальными ролями.',
  impact='Все будущие ревизии с tenant-таблицами (обязаны создавать owner-политику), S07 (auth lookup, column grants), S10 (dispatcher: fencing-токен), S13 (Gate: ревалидация, check_code)',
  risks='Флаг `app.migration_mode` — не граница безопасности против произвольного SQL владельца роли (owner NOLOGIN, достижим только через SET ROLE у migrator, который и так выполняет DDL); удаление тенантных данных миграцией по-прежнему требует решения владельца (политика FOR ALL включает DELETE). Остаточные gap: G-59…G-68.',
  tests='test_migration_safety (owner backfill, PERSIST-002 с owner-политиками), test_roles_and_grants (sabotage owner_migration_policy_missing ×2), test_agents_execution_schema (start requires latest, result needs started open run, unique attempt), test_identity_org_project_schema / test_operations_work_schema (immutable), test_repositories (fencing, bounded retry, idempotency expiry/key_id, secret guards)',
))


def _s06(id_, title, context, reqs, docs, alts, decision, why, impact, risks, tests):
    ADRS.append(dict(id=id_, title=title, status='ACCEPTED', date='2026-11-11', owner='Implementation Lead (делегированные полномочия)', context=context, reqs=reqs,
                     docs=docs, alts=alts, decision=decision, why=why, impact=impact, risks=risks, tests=tests))


_s06('ADR-056', 'S06: шаблон «идентичность + неизменяемые версии», требования и нумерация',
     'DOC-005 §6, §16 требуют иммутабельных версий, контролируемого указателя текущей версии и уникальных номеров без MAX()+1; DDL v1.0 — только design snapshot.',
     'DOC-003, DATA-MVP-004, ADR-016, ADR-027, coding-standards (UUIDv7, MAX+1 запрещён)',
     'Domain Model v1.9 §6, §16; Requirements Lifecycle v2.7 §13–§16; documentation-and-versioning.md',
     'Статус только на агрегате (версия остаётся «чистым» снимком); указатель без FK; нумерация MAX()+1 — отвергнуты.',
     '(1) Агрегат хранит изменяемые указатель/счётчики (`current_version_id`, `last_version_number`, `row_version`); версия — insert-only, кроме именованных lifecycle-колонок, переходы которых проверяет БД (`platform.guard_status_transition`, `forbid_unset`, `require_initial_state` на INSERT). (2) Указатель — DEFERRABLE составной FK `(id, current_version_id) -> versions(parent_id, id)`: может назвать только версию того же агрегата и tenant. (3) Номера версий непрерывны (отложенная проверка при COMMIT). (4) Статусы RequirementVersion = DOC-003; граф переходов минимальный «только вперёд» (WORKING уточнения: IN_BASELINE->SUPERSEDED). CONFIRMED требует человека (`confirmed_by` FK iam.users), APPROVED — факта approval этого человека для ровно этой версии, IN_BASELINE — baseline_item. (5) Неизвестный тип: реестр `requirement_types` (BR…TR + UNKNOWN), тип вне реестра хранится как UNKNOWN с `declared_type_text`, никогда не ближайший. (6) Человекочитаемые номера: `platform.display_number_counters` (строка под блокировкой, +1 только на единицу), UNIQUE(org, project, номер). (7) Связи: requirement_epics, work.task_requirements (опционально закреплённая версия).',
     '«Утверждённое» нельзя получить без существующего факта (approval и т.п.) ни UPDATE, ни INSERT; БД проверяет только наличие факта и что утверждающий — пользователь организации, а полномочия актора проверяет Policy Engine (S07); указатель и нумерация не рассинхронизируются.',
     'S09 (команды требований), S26–S31, репозиторий `modules/requirements`',
     'Расширение реестра типов на уровне организации и provenance как FK-таблица — не в scope (G-74); номера не привязаны к счётчику на уровне БД (G-72).',
     'test_domain_content_schema (immutability, UNKNOWN, lifecycle, указатель/нумерация), test_s06_repositories')

_s06('ADR-057', 'S06: sources, uploads, source_versions, extraction_records',
     'Нужны проверка checksum до обработки, идемпотентность финализации и дедупликация без перезаписи версий.',
     'Source and Context Lifecycle §3, §6; security.md (uploads); testing: duplicate ingestion, parser change',
     'Domain Model §7; Source and Context Lifecycle v1.3',
     'Версия из любого объекта MinIO без upload — отвергнуто (ревью C5).',
     '`uploads`: PENDING->UPLOADED->VERIFIED|REJECTED|EXPIRED; VERIFIED только при совпадении checksum и размера (CHECK). `source_versions` insert-only, `object_key ⇔ upload_id` (иначе внешняя ссылка `external_ref`), создаётся из VERIFIED upload того же источника с теми же checksum/размером/типом (триггер); UNIQUE(source_id, checksum) и UNIQUE(upload_id) — повтор не создаёт дубль. `knowledge.extraction_records`: смена parser/pipeline version = новая запись, завершённая запись заморожена. Время жизни upload URL — WORKING конфигурация вызывающего.',
     'Содержимое источника не принимается на веру: версия возможна только после проверки.',
     'S08–S09 (upload API), S10–S11 (ingestion), репозиторий `modules/sources`',
     'SourceFragment/SourceAssertion/DerivedFinding вне scope (G-74); object_key уникален только среди uploads.',
     'test_domain_content_schema, test_s06_repositories')

_s06('ADR-058', 'S06: traceability, rules, context, decisions',
     'Полиморфные ссылки не имеют FK; правила нужны трёх уровней; контекст должен быть неизменяемым снимком.',
     'DOC-051, RULE-MVP-02..04, ADR-018, DOC-012 (WORKING)',
     'Domain Model §8, §10, §11.3; Agent Architecture Concept §15; MVP Capability Matrix RULE-MVP',
     'Универсальная таблица заметок для решений (запрещена); произвольные object/link types (запрещены).',
     '(1) Реестры `object_types`, `link_types`, `link_type_rules` (составной FK пары); засеяны только типы из документов (REFINES, DEPENDS_ON, CONFLICTS_WITH, DUPLICATES, SUPERSEDES для REQUIREMENT↔REQUIREMENT — WORKING, расширение ревизией). Концы связи проверяются триггером на существование в том же tenant; неизвестный тип — fail closed. Подтверждение требует субъекта и evidence. (2) Правила в схеме `governance` (отдельной схемы `rules` в ADR-014 нет): SYSTEM-правила без tenant (читают все, пишут только ревизии), ORGANIZATION/PROJECT — по RLS; одна APPROVED версия на правило; неутверждённая версия не «активна»; Registry и Engine — раздельные интерфейсы (ADR-018, Engine вне scope). (3) Контекст: пакет, неизменяемая версия и элементы пишутся одной транзакцией (число элементов проверяется при COMMIT), элементы — типизированные FK, rule-элемент — только APPROVED версия, видимая tenant. (4) Решения: семь отдельных таблиц DOC-051, статусы — regex (WORKING), risk probability/impact по умолчанию UNKNOWN без числовых порогов.',
     'Целостность там, где её может дать БД; остальное — явный WORKING.',
     'S09, S12 (context), S26–S31, Rules Engine',
     'Словари статусов decisions и политики правил WORKING (G-72); FK worker_runs->context_package_versions не добавлен (G-73).',
     'test_domain_content_schema (traceability, rules, context, decisions)')

_s06('ADR-059', 'S06: append-only история событий агрегатов и расширение aggregate_types',
     'ADR-033: SSE строится из event history (в S06 созданы только таблицы истории — ни один продюсер событий не реализован, G-70); ADR-016/053: aggregate_types расширяется ревизиями S06/S10.',
     'ADR-033, ADR-034, ADR-053, PERSIST-012',
     'AsyncAPI v1.6 (RequirementVersionCreated, SourceVersionIngested, Artifact*, Baseline*, ChangeRequest*)',
     'Один общий журнал событий — отвергнут (расходится с operation_events/worker_run_events).',
     'Таблицы `{requirement,source,artifact,baseline,change_request}_events` по образцу operation_events: insert-only для всех, RLS через агрегат, непрерывная sequence при COMMIT. `audit.aggregate_types` расширен. `assert_outbox_matches_event` намеренно НЕ расширена: outbox-строка для новых агрегатов отвергается (fail closed) до решения OD-13 (форма dataschema/source, до S10).',
     'История готова для SSE, а публикация в outbox не появится раньше решения владельца по форме envelope.',
     'S10 (расширить функцию и репозиторий событий), S08–S09',
     'Эмиссия событий этими агрегатами не реализована (G-70).',
     'test_domain_content_schema::test_event_history_is_append_only_contiguous_and_outbox_stays_fail_closed')

_s06('ADR-060', 'S06: артефакты, review/approval/publication, baseline; hardening по независимому review',
     'Validation, Review, Approval, Publication — разные факты; Baseline неизменяем; словарь статусов артефакта «начальный предлагаемый».',
     'DOC-005 §9, Artifacts Lifecycle §6, §10; documentation-and-versioning.md; ADR-037',
     'Documentation Artifacts Lifecycle v1.0 §3, §6, §10; Domain Model §9, §16',
     'Единый статус «готов к публикации» — отвергнуто; смешение validation и approval — отвергнуто.',
     '(1) Статусы ArtifactVersion — реестр (FK), засеян словарём §6.1; граф переходов минимальный (WORKING). APPROVED требует approval человека для ровно этой версии, PUBLISHED — publication (создаётся только для APPROVED), содержимое неизменно. (2) Reviews/approvals/publications/validation_reports — insert-only; approvals имеют типизированные FK (requirement_version | artifact_version | baseline), approver — пользователь организации. (3) Baseline и baseline_items insert-only; элементы добавляются только в транзакции создания baseline, только для APPROVED версий; число элементов проверяется при COMMIT; baseline требует APPROVED approval человека в той же транзакции; номер n следует за n-1. (4) Ревью (C1–C5, M1, M4): все lifecycle-guard-ы действуют и на INSERT (ревизия 0011, `require_initial_state`); object_key ⇔ upload; rule-элемент контекста — только APPROVED версия tenant; approver правила — из той же организации; индексы под FK. РАСХОЖДЕНИЕ: documentation-and-versioning.md называет жизненный цикл DRAFT→PROPOSED→UNDER_REVIEW→APPROVED→PUBLISHED→SUPERSEDED, Artifacts Lifecycle §6.1 — другой словарь; выбран §6.1 как профильный документ, решение — владельцу (OD-14).',
     'Статус не может утверждать то, чего нет: факты проверяются самой БД, в том числе при INSERT.',
     'S26–S31 (artifact/baseline/change control), S07 (approvals через Policy)',
     'Открытые пункты review → G-72 (validation как предпосылка approval, xid-запечатывание, привязка номеров к счётчикам, статус CR, разделение обязанностей).',
     'test_domain_content_schema (artifact facts, baseline, lifecycle on INSERT, rule item tenant)')


def _s07(id_, title, context, reqs, docs, alts, decision, why, impact, risks, tests):
    ADRS.append(dict(id=id_, title=title, status='ACCEPTED', date='2026-11-11', owner='Implementation Lead (делегированные полномочия)', context=context, reqs=reqs,
                     docs=docs, alts=alts, decision=decision, why=why, impact=impact, risks=risks, tests=tests))


_s07('ADR-061', 'S07: Argon2id и политика паролей',
     'Параметры Argon2id и состав denylist нормативно не заданы; минимум длины 15 — нормативен.',
     'AUTH-003, AUTH-005, AUTH-MVP-003', 'Authentication and Session Management v1.1 §4; Security Controls v1.2',
     'bcrypt/scrypt — отвергнуто (требование Argon2id); «тяжёлые» параметры без замеров — отвергнуто.',
     'argon2-cffi, Argon2id; по умолчанию t=2, m=19456 KiB, p=1 (минимум OWASP; **WORKING** — до замера на целевом оборудовании, G-75), параметры в Settings. Минимум длины 15 — пол, ниже настроить нельзя; denylist — упакованный seed из 22 строк + файл (**WORKING**, G-75). Для неизвестной учётки проверяется хеш-«приманка» тех же параметров (одна проверка на любой путь). `needs_rehash` при входе. Пароль нигде не логируется и не попадает в аудит.',
     'Единый стоимостной профиль входа не даёт отличить существующую учётку; WORKING-значения вынесены в конфигурацию, а не зашиты.',
     'modules/iam/passwords.py, Settings, bootstrap, login, смена пароля',
     'Параметры могут оказаться слабее/тяжелее нужного (нет benchmark); denylist неполный.',
     'test_iam_passwords, test_iam_login (счётчик проверок = 1 на любом пути)')

_s07('ADR-062', 'S07: pre-auth поиск (закрывает G-48), токен сессии и CSRF',
     'Таблицы `iam.users`/`iam.sessions` под FORCE RLS по организации, а поиск по cookie/логину происходит до tenant-контекста (G-48); SECURITY DEFINER и BYPASSRLS запрещены.',
     'AUTH-007, AUTH-008, SEC-001', 'Authentication v1.1 §5–§6; Persistence Blueprint (RLS); database-and-migrations.md',
     'SECURITY DEFINER-функция поиска — отвергнуто (ослабляет модель ролей); отдельная роль с BYPASSRLS — запрещено; глобальный индекс сессий вне RLS — отвергнуто.',
     'Токен сессии `<org-hex>.<random 256 бит>`: организация — только **подсказка для выбора tenant-контекста**, полномочия даёт совпадение SHA-256 дайджеста под RLS (поддельная подсказка даёт 0 строк). Логин принимает `organizationId` (или `default_organization_id` установки). В БД только дайджесты. Idle 30 мин / absolute 12 ч (конфиг.), ротация при login/MFA/смене пароля не продлевает absolute; revoke write-once (триггер). CSRF-токен = HMAC-SHA256(ключ = токен сессии, «ai-res-csrf-v1»), его можно получить заново через `GET /auth/csrf`; сравнение constant-time. Миграция не потребовалась.',
     'Не вводит привилегированный путь мимо RLS; утечка БД не раскрывает токены.',
     'modules/iam/{tokens,sessions}.py, api/identity.py',
     'Утечка токена из памяти/логов даёт сессию — закрыто редактированием логов и тестом golden.',
     'test_iam_sessions, test_iam_tokens_and_request_security, test_identity_http')

_s07('ADR-063', 'S07: маршруты auth в overlay; cookie, Origin и CORS',
     'В Public API v1.3 нет login/logout/MFA/password (кроме getCurrentUser); handler без контракта запрещён.',
     'AUTH-007, API-MVP, ADR-009/ADR-038', 'Public API v1.3; Authentication v1.1 §6; api-and-contracts.md',
     'Handler без overlay — запрещено; изменение canonical v1.3 — только через NCP-06.',
     'Overlay `contracts/openapi/extensions/identity_auth.yaml` (**WORKING**): login, logout, csrf, password, mfa/enrollment, mfa/enrollment/confirm, mfa/verify. Spectral-правило `aires-idempotency-key`: операция может не объявлять `Idempotency-Key` только с письменным `x-idempotency-exempt` (≥20 символов) — для обмена учётными данными повтор не должен возвращать выданную сессию. Cookie `ai_res_session` (OD-03): HttpOnly, Secure, SameSite=Lax, Path=/api/v1, без Domain; все небезопасные запросы (включая login — login-CSRF) проходят allowlist Origin/Referer; CORS не включается (deny-by-default), пустой allowlist отказывает всё.',
     'Контракт предшествует коду; исключение из идемпотентности явное и проверяемое.',
     'contracts/, api/identity.py, api/request_security.py, infra (AI_RES_ALLOWED_ORIGINS)',
     'Overlay WORKING до NCP-06; wire-имена cookie/CSRF ждут security owner (OD-03).',
     'contracts tests (3), test_identity_http, infra runtime (origin/CORS через Caddy)')

_s07('ADR-064', 'S07: прогрессивная задержка входа и определение IP клиента',
     'DOC-023 §4 требует rate limiting без hard lockout; пороги нормативно не заданы.',
     'AUTH-005, AUTH-MVP-004', 'Authentication v1.1 §4.3; Infrastructure (ADR-020: Caddy перезаписывает X-Forwarded-For)',
     'Постоянная блокировка учётки — отвергнуто (DoS по чужой учётке); Redis — не в топологии MVP.',
     'Счётчики по ключам account+ip, ip, account, global; задержка растёт экспоненциально от base до max, решение принимается ДО проверки пароля (верный пароль во время задержки тоже ждёт); состояние процесса, ограниченное по размеру. Все пороги — Settings (**WORKING**). XFF учитывается только от пиров из `trusted_proxy_cidrs`, берётся самый правый недоверенный хоп; пусто = XFF игнорируется.',
     'Подделка XFF не обходит лимиты (счётчик account остаётся); нет вектора вечной блокировки.',
     'modules/iam/throttle.py, api/client_ip.py, Settings',
     'Состояние process-local: при нескольких процессах API лимит ослабляется (G-76); без фиксированной подсети app за Caddy IP клиента не доверяется (G-77).',
     'test_iam_throttle_and_client_ip, test_identity_http (forged XFF)')

_s07('ADR-065', 'S07: TOTP MFA, recovery codes и шифрование seed',
     'MFA обязательна для привилегированных ролей; хранение seed и защита от повтора кода не заданы.',
     'AUTH-006, AUTH-MVP-005', 'Authentication v1.1 §7; Security Architecture v1.2',
     'Хранить seed открытым — запрещено; SMS/e-mail — вне MVP.',
     'pyotp (SHA1, 6 цифр, 30 с; окно `mfa_window_steps` — **WORKING**). Seed шифруется AES-256-GCM (`SecretBox`, id ключа в blob, AAD = org/user/factor), ключ — Compose-секрет `mfa_encryption_key`. Recovery codes: 120 бит, хранится SHA-256, одноразовые. Повтор TOTP отклоняется compare-and-set по `last_used_step` + монотонный триггер БД (миграция 0012). Подтверждение enrolment и verify ротируют сессию. Сброс MFA — отдельный привилегированный путь с аудитом.',
     'Повтор кода и подмена блоба seed между пользователями отсекаются на уровне БД/AAD.',
     'modules/iam/{totp,secretbox,mfa}.py, миграция 0012, infra secret',
     'Ротация ключа MFA — отдельный runbook (SEC-027, не сделан); факт «MFA обязательна для роли» принуждается Policy на привилегированных действиях, не при входе.',
     'test_iam_secretbox_and_totp, test_iam_mfa, test_identity_http (MFA flow)')

_s07('ADR-066', 'S07: bootstrap первого администратора',
     'Default credentials запрещены; нужен одноразовый путь создания первого admin.',
     'AUTH-004, AUTH-MVP-003', 'Authentication v1.1 §3.3; security.md',
     'Admin из миграции/seed — отвергнуто (default credentials); HTTP-endpoint — отвергнуто (публичная поверхность).',
     'CLI `python -m ai_res.cli.bootstrap` (профиль Compose `bootstrap`, `make bootstrap`): секрет и пароль — только через `getpass`, не argv/env/логи; секрет читается из Compose-файла и сравнивается constant-time. Одноразовость — singleton `platform.bootstrap_state` (миграция 0013, append-only, атомарный claim по PK); повтор → отказ, аудит `AUTH_ACCOUNT_INVITED` (SYSTEM). Печатает только идентификаторы. Секрет не монтируется в API.',
     'Окно атаки — одна процедура с секретом, а не постоянная поверхность.',
     'modules/iam/bootstrap.py, cli/bootstrap.py, миграция 0013, compose',
     'Секрет не инвалидируется файлом (одноразовость — в БД); runbook не написан (G-78).',
     'test_iam_bootstrap, infra check_compose')

_s07('ADR-067', 'S07: Policy Engine — конфигурация, решения, enforcer, аудит',
     'ADR-017: in-process, deny-by-default, fail-closed; матрица ролей и действий нормативно не задана.',
     'SEC-001, SEC-002, SEC-MVP-001, AUTH-006, AUTH-012', 'Identity & Access Control v1.5; Security Architecture v1.2',
     'Решения в коде handler-ов — отвергнуто; RLS как замена Policy — запрещено.',
     'Версионируемый `policy_config.json` с закреплённым SHA-256; недопустимая/без версии/с дубликатами конфигурация = deny-all (`policy_config_invalid`). Решение: неизвестное действие, неверный тип ресурса, нет scope, не-USER актор, автономия > A2, неактивный субъект/членство, нет grant, нет MFA — DENY с reason code; человеко-только действия (`humanOnly`) недоступны сервисам/агентам. `PolicyEnforcer`: ALLOW аудируется в транзакции вызывающего (откат действия откатывает аудит), DENY — в собственной транзакции, затем 403 или одинаковый 404 при `conceal`; недоступность/таймаут/мусор → 503 (fail-closed). Матрица (`iam.*`) — **WORKING** (OD-15).',
     'Каждое решение воспроизводимо (policy_version) и аудируется; ослабить матрицу можно только изменением конфигурации с новой контрольной суммой.',
     'ai_res/policy/*, ports (PolicyRequest.attributes, decide_or_fail), modules/iam/accounts.py',
     'Для `iam.self.read/logout` ALLOW не аудируется (`auditAllow:false`) — отступление от «каждое решение аудируется» (G-79); матрица не утверждена владельцем.',
     'test_policy_config (22), test_policy_engine (98), test_iam_accounts')

_s07('ADR-068', 'S07: сервис идемпотентности (HMAC + key_id)',
     'ADR-024; репозиторий S05 принимает готовые дайджесты — нужен слой, который их строит.',
     'API-MVP (Idempotency-Key), ADR-024', 'API and Interaction Contracts v1.10; api-and-contracts.md',
     'Хранить ключ открытым — запрещено; общий хеш без ключа — отвергнуто (перебор).',
     'Ключ 16..128 печатных ASCII. Дайджест = HMAC-SHA256(ключ из key ring, org|тип/id актора|команда|ключ); отпечаток запроса — тоже HMAC (тот же ключ записи) от канонического JSON. Поиск по дайджестам под всеми принятыми ключами кольца (ротация); advisory xact lock по неключевому хешу scope сериализует гонку на границе ротации. Файл кольца: `<id> <base64 32 байта>`, первая строка активна. Повтор → REPLAY, тот же ключ с другим телом → 409 `IDEMPOTENCY_KEY_REUSED`. TTL (`idempotency_ttl_hours`, **WORKING**, G-58).',
     'Сырой ключ и тело не попадают в БД; параллельные одинаковые запросы дают одну запись.',
     'modules/idempotency/service.py, Settings',
     'Кольцо ключей не подключено к compose до первого идемпотентного endpoint (G-80); политика очистки/takeover — G-58.',
     'test_idempotency_service (18, включая мутацию: без lock гонка проваливается)')

_s07('ADR-069', 'S07: идентичности сервисов — короткоживущие токены Ed25519',
     'AUTH-012: человек, сервис и Worker не подменяют друг друга; браузерная сессия не принимается Runtime.',
     'AUTH-012, AUTH-MVP-008, SEC-013', 'Authentication v1.1 §8; Identity & Access Control v1.5 §3',
     'Общий HMAC-секрет — отвергнуто (любой сервис подделает другого); mTLS — вне scope S07.',
     'Токен `ar1.<payload>.<подпись>`: claims `iss, aud, iat, exp, jti` (без ролей и секретов), подпись Ed25519 с доменным префиксом; у каждого сервиса свой закрытый ключ, верификатор держит только публичные ключи по издателям (две записи при ротации). Срок ограничен при выпуске и при проверке (`service_token_max_ttl_seconds`, **WORKING** 300 с); неизвестная версия/лишние или дублирующиеся claims/чужая аудитория/срок — отказ; верификатор не бросает исключений. Не является Worker Run grant и не даёт прав.',
     'Подделать токен другого сервиса можно только его ключом; сессия и сервисный токен имеют разные форматы.',
     'modules/iam/service_tokens.py, ServiceIdentityPort',
     'Потребителей пока нет (Manager/Worker/dispatcher — S11/S23); ключи не в compose (G-80); защиты от повтора jti нет (токены короткоживущие, аудитория ограничена).',
     'test_iam_service_tokens (22)')

_s07('ADR-070', 'S07: аудит аутентификации и отзыв сессий при изменении аккаунта',
     'AUTH-008/013: события входа, MFA, смены пароля аудируются без секретов; отключение и отзыв роли немедленно закрывают сессии; сбой аудита отказывает действию.',
     'AUTH-008, AUTH-013, SEC-019, SEC-020', 'Authentication v1.1 §6, §9; Security Architecture v1.2',
     'Аудит «после коммита» — отвергнуто (потеря при сбое); логирование вместо аудита — запрещено.',
     '`SqlAuditWriter` пишет в `audit.audit_events` в транзакции действия; ключи `details` проверяются фильтром чувствительных имён; организация обязательна. Неуспех входа аудируется в закоммиченной транзакции. `AccountService.disable_user_in/revoke_membership_in` меняют статус, отзывают все сессии (USER_DISABLED/ROLE_REVOKED) и пишут аудит одной транзакцией; нельзя отключить себя и последнего активного владельца; чужой/несуществующий пользователь — одинаковый 404.',
     'Утверждённое событие и его аудит атомарны; отзыв не зависит от обновления UI.',
     'modules/audit/writer.py, modules/iam/accounts.py',
     'Расхождение портов: `AuditOutcome.ALLOWED` порта и `SUCCEEDED` в БД сведены маппингом; статусы пользователя Auth §3.1 (INVITED/SUSPENDED/LOCKED) шире `iam.users.status` (ACTIVE/DISABLED) — G-81.',
     'test_iam_audit_writer, test_iam_accounts, test_identity_http (golden логов и аудита)')

_s07('ADR-071', 'S07: счётчики ip и global — сигнал, а не отказ; фиксированная подсеть app',
     'Review S07 (R01/SEC-03): за одним адресом прокси лимит по IP превращается в способ отключить вход всем. Auth v1.1 §4 требует rate limit по account, source signal и глобальному порогу, но не фиксирует, что порог отказывает.',
     'AUTH-005', 'Authentication v1.1 §4; Security Architecture v1.2',
     'Жёсткий отказ по ip/global — отвергнуто (DoS на всех пользователей); убрать счётчики — отвергнуто (нужен сигнал атаки по многим аккаунтам).',
     'Отказывают (progressive delay с потолком) только счётчики (account, ip) и account. Счётчики ip и global при достижении порога один раз пишут AUTH_RATE_LIMITED с исходом FAILED и причиной `ip_threshold_signal`/`global_threshold_signal`; режим переключается `AI_RES_LOGIN_ENFORCE_IP_GLOBAL` (WORKING, по умолчанию false). Сеть `app` получает фиксированную подсеть 172.28.20.0/24, Caddy — адрес 172.28.20.2, API доверяет X-Forwarded-For только от 172.28.20.2/32 (WORKING; подсеть может конфликтовать с сетями хоста). Решение владельца, делегировано 2026-11-12.',
     'Задержка по аккаунту остаётся против подбора пароля; атакующий может временно замедлить конкретную жертву (принятый риск, смягчается MFA и потолком задержки). **NCP-12 (PROPOSED):** уточнить в Auth v1.1 §4, что ip/global — сигнал.',
     'modules/iam/throttle.py, Settings, api/identity.py, infra/compose.yaml',
     'Режим сигнала не защищает от распределённого перебора по одному аккаунту сильнее, чем account-порог; нормативный текст допускает и иное прочтение.',
     'test_iam_throttle_and_client_ip (signal mode), test_iam_login (burst), check_compose')

_s07('ADR-072', 'S07: повторное подтверждение пароля и код ответа',
     'Review S07 (R03, SEC-05): неверный текущий пароль при смене отдавал 401 (клиент разлогинивает пользователя); подключение TOTP не требовало свежего доказательства.',
     'AUTH-003, AUTH-007', 'Authentication v1.1 §3.2, §5; NIST SP 800-63B §6.1.2',
     'Оставить 401 — отвергнуто (путает с истёкшей сессией); не требовать пароль при подключении TOTP — отвергнуто (кража cookie закрепляет чужой фактор).',
     'Неверный текущий пароль — 422 VALIDATION_ERROR с `errors[{field: currentPassword, reason: invalid_current_password}]`, попытка учитывается throttle. `POST /auth/mfa/enrollment` требует `currentPassword` (`AuthService.reauthenticate`: throttle, аудит AUTH_REAUTHENTICATED, 422 при ошибке). Overlay WORKING обновлён. Решение владельца, делегировано 2026-11-12.',
     'Клиент не теряет сессию на опечатке; привязка аутентификатора требует свежей аутентификации.',
     'api/identity.py, modules/iam/auth.py, contracts overlay',
     'Изменение WORKING overlay; потребителей вне репозитория нет.',
     'test_identity_http (fresh password proof), test_iam_login')

_s07('ADR-073', 'S07: иерархия организационных ролей при действиях над пользователями',
     'Review S07 (SEC-06): ORGANIZATION_ADMIN мог отключить, отозвать членство или сбросить MFA владельца (кроме последнего). IAM v1.5 иерархию ролей не описывает.',
     'AUTH-008', 'Identity & Access Control v1.5 (иерархия не определена); принцип наименьших привилегий',
     'Оставить только защиту последнего владельца — отвергнуто; вынести правило в матрицу политик — отвергнуто (это инвариант домена, не конфигурация).',
     '`ensure_may_act_on`: ранг OWNER=2, ADMIN=1, прочие/нет=0; действие допустимо, если ранг актора строго выше ранга субъекта, либо оба OWNER. Применяется в `AccountService` (disable, revoke membership) и `MfaService.reset`; отказ — 403 ACCESS_DENIED, reason `role_hierarchy`. Защита «последнего владельца» и самоблокировки сохраняется. **WORKING**: нормативный документ молчит. Решение владельца, делегировано 2026-11-12.',
     'Скомпрометированный администратор не снимает защиту владельцев.',
     'modules/iam/accounts.py, modules/iam/mfa.py',
     'Ранги вшиты в код, при новых ролях нужно расширять. Отказ иерархии аудируется отдельной транзакцией (POLICY_DECISION, DENIED, reason `role_hierarchy`), как отказы Policy Engine; если запись не удалась — 503, действие не выполняется.',
     'test_iam_accounts (role hierarchy, audit trace, 503 при сбое аудита), test_iam_mfa (reset)')
