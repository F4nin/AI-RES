# ARCHITECTURE_DECISION_LOG

Единый журнал архитектурных и технических решений реализации AI RES (ненормативный). Статусы: PROPOSED, ACCEPTED, REJECTED, SUPERSEDED. Решения в пределах полномочий Implementation Lead регистрируются как ACCEPTED. Решения, меняющие нормативные документы, оформляются как NCP в `decisions/NORMATIVE_CHANGE_PROPOSALS.md` и не считаются утверждёнными до решения владельца. Подробные материалы крупных решений — `decisions/`. `docs/adr/` не используется (`.claude/rules/ecc-precedence.md`).

Сводка: 73 записей; все ACCEPTED.

| ID | Решение | Статус |
|---|---|---|
| ADR-001 | Python 3.13 как целевая версия | ACCEPTED |
| ADR-002 | uv + `uv.lock` как менеджер зависимостей | ACCEPTED |
| ADR-003 | Testcontainers для PostgreSQL integration tests | ACCEPTED |
| ADR-004 | Contract toolchain | ACCEPTED |
| ADR-005 | Раскладка репозитория | ACCEPTED |
| ADR-006 | Система управления реализацией в `docs/implementation/` | ACCEPTED |
| ADR-007 | ECC как dev-time инструментарий | ACCEPTED |
| ADR-008 | Web-стек Backend: FastAPI + полностью async | ACCEPTED |
| ADR-009 | `contracts/` — проверяемое зеркало canonical контрактов | ACCEPTED |
| ADR-010 | Единая последовательность этапов S00–S39 и устранение циклических зависимостей | ACCEPTED |
| ADR-011 | Greenfield-профиль persistence | ACCEPTED |
| ADR-012 | Владеющая Operation для Task, созданной `createTask` | ACCEPTED |
| ADR-013 | Реестр `operation_type` | ACCEPTED |
| ADR-014 | Имена PostgreSQL schemas | ACCEPTED |
| ADR-015 | Набор PostgreSQL ролей по нормативным документам | ACCEPTED |
| ADR-016 | Проектирование отсутствующих физических таблиц | ACCEPTED |
| ADR-017 | Policy & Permission Engine — in-process модуль | ACCEPTED |
| ADR-018 | Rules Registry и Rules Engine — отдельные интерфейсы в модульном монолите | ACCEPTED |
| ADR-019 | Frontend: React + TypeScript + Vite SPA | ACCEPTED |
| ADR-020 | Reverse Proxy: Caddy | ACCEPTED |
| ADR-021 | Работа с WORKING Worker Contracts v1.1 | ACCEPTED |
| ADR-022 | Deterministic LLM test double только в test-профиле | ACCEPTED |
| ADR-023 | `gateResultId` ↔ ReadinessEvaluation | ACCEPTED |
| ADR-024 | Idempotency HMAC keys с key-id | ACCEPTED |
| ADR-025 | Поэтапная observability | ACCEPTED |
| ADR-026 | Инструменты тестирования и статического анализа | ACCEPTED |
| ADR-027 | UUIDv7 | ACCEPTED |
| ADR-028 | Temporal self-hosted | ACCEPTED |
| ADR-029 | Безопасный default для risk-tier эскалации | ACCEPTED |
| ADR-030 | Retention: без автоматического удаления | ACCEPTED |
| ADR-031 | Провайдер-нейтральный LLMGatewayPort до решения по провайдеру | ACCEPTED |
| ADR-032 | Статусы этапов и определение DONE | ACCEPTED |
| ADR-033 | Источник SSE и event history API | ACCEPTED |
| ADR-034 | Rework после terminal Operation и RLS/grants для event-таблиц | ACCEPTED |
| ADR-035 | Контуры тестирования и evidence для P0-этапов | ACCEPTED |
| ADR-036 | LangGraph checkpointer через checkpoint-broker | ACCEPTED |
| ADR-037 | Независимая проверка P0-этапов (замена per-stage human sign-off) | ACCEPTED |
| ADR-038 | План проектирования недостающих endpoint и событий | ACCEPTED |
| ADR-039 | Breaking-change detection: собственный diff вместо oasdiff на S01 | ACCEPTED |
| ADR-040 | Инструменты сохранения контекста: session-brief hook, CONTEXT_HANDOFF, Context7, Serena | ACCEPTED |
| ADR-041 | Platform primitives S02: курсоры, ошибки, корреляция, error boundary, порты | ACCEPTED |
| ADR-042 | MinIO и mc собираются из закреплённых исходников (официальный образ недоступен) | ACCEPTED |
| ADR-043 | Supply chain S03: SBOM, скан образов, политика исключений | ACCEPTED |
| ADR-044 | Состав и жёсткость локального стека S03 (образы, сети, healthchecks, секреты в процессах) | ACCEPTED |
| ADR-045 | Схема dev-секретов: SOPS+age, случайные значения, идемпотентная материализация | ACCEPTED |
| ADR-046 | Роли PostgreSQL S04: provisioning под суперпользователем, ревизия PDB-0001 только проверяет, drift-коррекция | ACCEPTED |
| ADR-047 | Миграционная среда S04: Alembic env, SET ROLE owner, advisory lock, одноразовая служба `migrate`, WORKING-таймауты | ACCEPTED |
| ADR-048 | Контроль дрейфа и аудит: reviewed snapshot (pg_dump + каталог), audit SQL как release gate, positive controls | ACCEPTED |
| ADR-049 | Runtime-слой persistence: engine, Unit of Work, tenant context (один раз на транзакцию), конфигурация db_* | ACCEPTED |
| ADR-050 | S05 срез A: физический дизайн iam / organization / project, общие row guards, справочник ролей | ACCEPTED |
| ADR-051 | S05 срез B: operations, operation_events и work — целостность на уровне БД, append-only события, закрытые Operation | ACCEPTED |
| ADR-052 | S05 срез C: agents и execution — инварианты Readiness Gate на уровне БД, insert-only история и результаты | ACCEPTED |
| ADR-053 | S05 срез D: outbox, inbox, audit_events, idempotency_records и reference aggregate_types — права и RLS по ADR-034 | ACCEPTED |
| ADR-054 | S05: CloudEvents-envelope Operation/WorkerRun событий строго по каноническим сообщениям AsyncAPI v1.6 (G-56, вариант A) | ACCEPTED |
| ADR-055 | S05: migration-политики owner под FORCE RLS (ADR-034 п.5, вариант 1) и hardening по независимым review | ACCEPTED |
| ADR-056 | S06: шаблон «идентичность + неизменяемые версии», требования и нумерация | ACCEPTED |
| ADR-057 | S06: sources, uploads, source_versions, extraction_records | ACCEPTED |
| ADR-058 | S06: traceability, rules, context, decisions | ACCEPTED |
| ADR-059 | S06: append-only история событий агрегатов и расширение aggregate_types | ACCEPTED |
| ADR-060 | S06: артефакты, review/approval/publication, baseline; hardening по независимому review | ACCEPTED |
| ADR-061 | S07: Argon2id и политика паролей | ACCEPTED |
| ADR-062 | S07: pre-auth поиск (закрывает G-48), токен сессии и CSRF | ACCEPTED |
| ADR-063 | S07: маршруты auth в overlay; cookie, Origin и CORS | ACCEPTED |
| ADR-064 | S07: прогрессивная задержка входа и определение IP клиента | ACCEPTED |
| ADR-065 | S07: TOTP MFA, recovery codes и шифрование seed | ACCEPTED |
| ADR-066 | S07: bootstrap первого администратора | ACCEPTED |
| ADR-067 | S07: Policy Engine — конфигурация, решения, enforcer, аудит | ACCEPTED |
| ADR-068 | S07: сервис идемпотентности (HMAC + key_id) | ACCEPTED |
| ADR-069 | S07: идентичности сервисов — короткоживущие токены Ed25519 | ACCEPTED |
| ADR-070 | S07: аудит аутентификации и отзыв сессий при изменении аккаунта | ACCEPTED |
| ADR-071 | S07: счётчики ip и global — сигнал, а не отказ; фиксированная подсеть app | ACCEPTED |
| ADR-072 | S07: повторное подтверждение пароля и код ответа | ACCEPTED |
| ADR-073 | S07: иерархия организационных ролей при действиях над пользователями | ACCEPTED |
| ADR-074 | S08: слой чтения (read model), DTO, cursor-пагинация, ETag | ACCEPTED |
| ADR-075 | S08: разрешение проекта для GET по id, видимость списков, отсутствие вложенных соединений | ACCEPTED |
| ADR-076 | S08: матрица Policy Engine для чтения проектных объектов (OD-15, WORKING) | ACCEPTED |
| ADR-077 | S08: поля DTO без источника в БД и отличия от OAS | ACCEPTED |
| ADR-078 | S09: конвейер команд записи и двухфазный createProject | ACCEPTED |
| ADR-079 | S09: события PROJECT/EPIC/REQUIREMENT, история и расширение outbox-триггера | ACCEPTED |
| ADR-080 | S09: отображение createEpic/registerRequirementCandidate/proposeRequirementVersion на схему | ACCEPTED |
| ADR-081 | S09: SigV4-пресайнер и конфигурация объектного хранилища | ACCEPTED |
| ADR-082 | S09: семантика createUploadIntent | ACCEPTED |
| ADR-083 | S09: матрица политик записи (WORKING) и первый администратор проекта | ACCEPTED |
| ADR-084 | S10: OD-13 — фиксация форм `dataschema` и `source` CloudEvents | ACCEPTED |
| ADR-085 | S10: dispatcher, классификация ошибок доставки и WORKING-конфигурация | ACCEPTED |
| ADR-086 | S10: durable consumer — checkpoint, режимы порядка, контрактная валидация | ACCEPTED |
| ADR-087 | S11: пакет оркестрации без БД, компактные контракты, стратегия версионирования workflow | ACCEPTED |
| ADR-088 | S11: внутренний Platform API для Runtime (транспорт, аутентификация, capability) | ACCEPTED |
| ADR-089 | S11: маршрут запуска Operation в Temporal — destination, фильтр dispatcher'а, skeleton fail-closed | ACCEPTED |
| ADR-090 | S11: топология Compose для оркестрации — сеть `workflow`, секреты, изоляция Runtime | ACCEPTED |
| ADR-091 | S12: типизированные переходы Operation и отмена с reconciliation | ACCEPTED |
| ADR-092 | S12: SSE проекта из event history — курсор, ACL на каждом опросе, retention gap | ACCEPTED |
| ADR-093 | S12: completeUpload — проверка объекта хранилищем, Operation SOURCE_INGESTION, роли политики | ACCEPTED |
| ADR-094 | S12 review follow-up: FAILED побеждает отложенную отмену; истёкший курсор SSE — gap; reconciler до S23 | ACCEPTED |
| ADR-095 | S13: стек наблюдаемости — единый путь OTLP → Collector (allowlist-redaction) → Prometheus/Loki/Tempo/Grafana | ACCEPTED |
| ADR-096 | S13: алерты как код — пороги без значений, `for` как WORKING, без получателей | ACCEPTED |
| ADR-097 | S13: экспорт telemetry из процессов — fail-open, ограниченные очереди, измеряемая потеря, санитизация логов | ACCEPTED |
| ADR-098 | S13: трассировка и метрики Temporal; контекст через Platform API, но не через Outbox | ACCEPTED |
| ADR-099 | S13: PostgreSQL — application-side метрики пула; серверные метрики ждут monitoring-роли (NCP-15) | ACCEPTED |
| ADR-100 | S13: решения владельца по OD-02 — стартовые пороги алертов, retention 30/7/30 дней, получатели и owner | ACCEPTED |

---

## ADR-001 — Python 3.13 как целевая версия

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Нормативные документы задают Python-ориентированный стек (DOC-068 §1), но не версию интерпретатора. |
| Связанные требования | INF-MVP (воспроизводимость), Blueprint §2 |
| Документы и разделы | DOC-068 §1; DOC-072 §2 |
| Альтернативы | 3.12; 3.13 |
| Решение | Python 3.13; точный patch в `.python-version` и base image digest. |
| Обоснование | Доступен локально (3.13.5). Совместимость SQLAlchemy 2.x, psycopg 3, Alembic, temporalio, LangGraph с 3.13 проверяется при pin зависимостей (S02/S04); при несовместимости — новая запись SUPERSEDED → 3.12. |
| Влияние на компоненты/контракты | backend, CI images |
| Риски и компромиссы | Отставание поддержки 3.13 у части библиотек |
| Затронутые тесты | CI matrix на одной версии; import + smoke integration tests в S02 |

## ADR-002 — uv + `uv.lock` как менеджер зависимостей

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Blueprint §2: версии фиксируются lock-файлом; плавающие версии запрещены. |
| Связанные требования | INF-MVP; Spec §4 Inc.1 (pinned tools) |
| Документы и разделы | DOC-072 §2; DOC-015 §12 |
| Альтернативы | Poetry; pip-tools |
| Решение | uv; `uv.lock` в git; CI — `uv sync --locked`. |
| Обоснование | Воспроизводимый lock, скорость, установлен локально. |
| Влияние на компоненты/контракты | backend, CI |
| Риски и компромиссы | — |
| Затронутые тесты | CI падает при рассинхроне lock |

## ADR-003 — Testcontainers для PostgreSQL integration tests

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Blueprint §2 требует выбрать один из pytest-postgresql/Testcontainers; SQLite не является доказательством. |
| Связанные требования | PERSIST-001..024 |
| Документы и разделы | DOC-072 §2, §12 |
| Альтернативы | pytest-postgresql; локальный Homebrew PostgreSQL |
| Решение | Testcontainers, образ `postgres:16.x` по digest; тот же образ в Compose. **[PREP review]** Образ PostgreSQL закрепляется конкретным digest в `infra/images.lock` (тег `16.x` не является pin). RLS/grants/tenant-тесты выполняются только под login-ролями, не под суперпользователем контейнера (DBM-008). [DB-7] |
| Обоснование | Одинаковое поведение локально и в CI; чистый кластер для ролей/RLS. |
| Влияние на компоненты/контракты | tests, CI (нужен Docker) |
| Риски и компромиссы | Время прогона |
| Затронутые тесты | Все integration/RLS/concurrency тесты; тесты RLS/grants падают при запуске под суперпользователем |

## ADR-004 — Contract toolchain

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Spec §4 Inc.1, §7: pinned validators, lint, breaking-change detection. |
| Связанные требования | API-MVP-001 |
| Документы и разделы | Spec v1.22 §4 Inc.1, §7; DOC-006 §17 |
| Альтернативы | Только Spectral; AsyncAPI CLI; Redocly |
| Решение | OpenAPI: openapi-spec-validator + Spectral (pinned) + oasdiff (breaking). AsyncAPI: JSON Schema официальной спецификации 3.1.0 из `@asyncapi/specs` + проверка `$ref`; `@asyncapi/parser` — после закрепления Node 22 LTS (G-03). JSON Schema: jsonschema Draft 2020-12 с локальным registry по `$id`. AsyncAPI/JSON Schema breaking-check — собственный скрипт сравнения с предыдущей версией. |
| Обоснование | Инструменты подтверждены на текущих контрактах (S00 §3). |
| Влияние на компоненты/контракты | contracts/, CI |
| Риски и компромиссы | AsyncAPI parser недоступен на Node 26 |
| Затронутые тесты | S01: негативные фикстуры для каждого валидатора |

## ADR-005 — Раскладка репозитория

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Blueprint §3 (BASELINED) задаёт `backend/`; Spec Inc.1 — `contracts/`; DOC-015 §11.2 — `infra/`. |
| Связанные требования | — |
| Документы и разделы | DOC-072 §3; DOC-015 §11.2; Spec §4 Inc.1 |
| Альтернативы | Корневые src/tests |
| Решение | `backend/` (Python), `frontend/` (UI, ADR-019), `contracts/`, `infra/` (compose.yaml, config, secrets/encrypted, runbooks→`docs/runbooks/`), `docs/implementation/`. Пустые корневые `src/`, `tests/`, `scripts/` не используются и удаляются в S01 (пустые, не отслеживаются git). |
| Обоснование | Следование BASELINED структуре. |
| Влияние на компоненты/контракты | Все компоненты |
| Риски и компромиссы | — |
| Затронутые тесты | — |

## ADR-006 — Система управления реализацией в `docs/implementation/`

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Master Implementation Initialization §5. Ранее трекеры были в `docs/development/`. |
| Связанные требования | — |
| Документы и разделы | CLAUDE.md §9; documentation-and-versioning.md |
| Альтернативы | Оставить docs/development |
| Решение | Все трекеры перенесены в `docs/implementation/` (без дублей); `docs/development/` удалён; ссылка в CLAUDE.md обновлена. `docs/adr/` не создаётся (ecc-precedence.md). |
| Обоснование | Единая точка входа. |
| Влияние на компоненты/контракты | Документация |
| Риски и компромиссы | — |
| Затронутые тесты | — |

## ADR-007 — ECC как dev-time инструментарий

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Владелец проекта (прямое указание) + Implementation Lead |
| Проблема и контекст | Spec Addendum v1.3 §4 откладывал выбор Claude Code расширений до решения пользователя; пользователь поручил обязательное использование ECC. |
| Связанные требования | — |
| Документы и разделы | Spec v1.22 Add. v1.3 §4; `.claude/rules/ecc-precedence.md` |
| Альтернативы | Не использовать ECC |
| Решение | ECC 2.2.3 (manual project-local install, commit d2ef268) используется как dev-time инструментарий. Hooks, MCP, continuous learning, auto-update не включаются. ECC agents не являются Runtime Workers и не заменяют QA Worker/human approval. Trust assessment: `reviews/ECC_TRUST_ASSESSMENT.md`. |
| Обоснование | Указание пользователя; правила AI RES сохраняют приоритет. |
| Влияние на компоненты/контракты | Процесс разработки |
| Риски и компромиссы | Supply-chain риск dev-инструментов (см. assessment) |
| Затронутые тесты | — |

## ADR-008 — Web-стек Backend: FastAPI + полностью async

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Web-фреймворк имел статус WORKING (`coding-standards.md`); DP-01. Master Implementation Initialization делегировала выбор библиотек и инструментов Implementation Lead. Решение явно задокументировано (не «молча»). |
| Связанные требования | API-MVP-003; INF-MVP-002 |
| Документы и разделы | DOC-072 §2 (async psycopg только при полностью async стеке); DOC-006 §3–§5; DOC-015 §3 |
| Альтернативы | Litestar; Starlette; sync Flask/Django |
| Решение | FastAPI + Pydantic v2 (DTO), SQLAlchemy 2.x asyncio + psycopg 3 async, uvicorn. OpenAPI — contract-first: нормативен `contracts/openapi`, сгенерированная FastAPI схема используется только для diff-проверки соответствия (schemathesis + сравнение). **[PREP review]** Выбор FastAPI подтверждён владельцем 2026-11-11 (OD-10), как и правки CLAUDE.md и `.claude/rules/database-and-migrations.md` (ADR-006, ADR-015). |
| Обоснование | temporalio и LangGraph — asyncio; SSE требует неблокирующих соединений; зрелая экосистема. |
| Влияние на компоненты/контракты | backend API, тесты; ECC `fastapi-reviewer` становится применим |
| Риски и компромиссы | Соблазн code-first схем — запрещён ADR-009/ADR-004 |
| Затронутые тесты | Contract tests (schemathesis) против contracts/openapi |

## ADR-009 — `contracts/` — проверяемое зеркало canonical контрактов

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Spec §4 Inc.1 требует `contracts/`; Registry v4.1 §2 фиксирует canonical пути в `docs/architecture/`. |
| Связанные требования | API-MVP-001 |
| Документы и разделы | Registry v4.1 §2; DOC-082 |
| Альтернативы | Валидация прямо в docs/architecture; независимая копия |
| Решение | Файлы в `contracts/` — побайтные копии canonical; CI сверяет SHA-256 с `AI_RES_Architecture_Baseline_Manifest_v1.2.json`. Изменение контракта — только через новую canonical версию по решению владельца (NCP) + Registry/manifest, затем пересинхронизация. Производные артефакты (examples, lint config, changelog) — только в `contracts/`. **[PREP review]** ДОПОЛНЕНИЕ (OD-09, решение владельца 2026-11-11): endpoint и события, отсутствующие в OAS v1.3/AsyncAPI v1.6, проектирует Implementation Lead по документам проекта. Они живут в `contracts/openapi/extensions/` и `contracts/asyncapi/extensions/` как overlay со статусом WORKING (поле `x-status: WORKING`, `x-source` — ссылки на разделы нормативных документов). Базовые зеркальные файлы не изменяются; CI собирает base+overlay, валидирует и проверяет, что overlay только additive (breaking-check против v1.3/v1.6). Формализация в нормативных версиях — NCP-06 (OAS v1.4) после этапа; `docs/architecture/` не меняется без указания владельца. |
| Обоснование | Нет второго источника истины. |
| Влияние на компоненты/контракты | contracts/, CI |
| Риски и компромиссы | — |
| Затронутые тесты | CI: рассинхрон → fail |

## ADR-010 — Единая последовательность этапов S00–S39 и устранение циклических зависимостей

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Нумерация Spec (Inc. 0–9, 10–18, 20–28) содержит прямые и обратные зависимости: Operation API (Inc.5) требует Temporal (Inc.7) и Outbox dispatcher (Inc.8); Readiness Gate (Inc.13) требует ContextPackageVersion (Inc.22) и Tool Registry (Inc.23); Worker lifecycle (Inc.14) требует LLMGatewayPort (Inc.20); Inc.3 читает таблицы, создаваемые только в Inc.5–6; нет этапов для Local Auth/Policy Engine, Rules Registry (RULE-MVP), построения UI (WS-MVP/UX-*), Requirements approvals (DOC-003). |
| Связанные требования | Все MVP-семейства (REQUIREMENTS_TRACEABILITY.md) |
| Документы и разделы | Spec v1.22 §4, Add. v1.1 §3, v1.19, v1.20; Blueprint §5, §14; Process Design §22 |
| Альтернативы | (а) Строго следовать нумерации Spec с заглушками; (б) Перестроить порядок, сохранив все работы и инварианты |
| Решение | (б). Единая последовательность S00–S39 (IMPLEMENTATION_ROADMAP.md) с колонкой соответствия Spec. Разделения: Inc.7 → S11 (Temporal foundation) + S23 (LangGraph/WorkerRun); Inc.8 → S10 (Outbox) + S29 (connectors); Inc.20 → S15 (port) + S16 (Bifrost/provider); Inc.22 → S19 (ContextPackage) + S28 (retrieval). Добавлены S07 (Identity/Policy), S18 (Rules), S26 (Requirements approvals/decisions), S35–S36 (UI). |
| Обоснование | Ни одна работа Spec не удалена; порядок исключает заглушки, выдаваемые за реализацию, и обход Gate (WorkerRun невозможен до S22). |
| Влияние на компоненты/контракты | Весь план |
| Риски и компромиссы | Длиннее путь до первого end-to-end сценария |
| Затронутые тесты | Каждый этап — собственный DoD; проверка в reviews/S-PREP |

## ADR-011 — Greenfield-профиль persistence

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DR-01: DDL v1.0 и Blueprint §5–§6 предполагают существующие `work.tasks` и legacy backfill (PDB-0003 nullable → PDB-0008 backfill → PDB-0009 NOT NULL). В репозитории нет данных и таблиц. |
| Связанные требования | PERSIST-001..024; DBM-* |
| Документы и разделы | DOC-072 §5, §6; DOC-064 §5.2, §11; DOC-068 §5 |
| Альтернативы | (а) Формально пройти expand/backfill на пустых таблицах; (б) Greenfield: создать `work.tasks` сразу с `operation_id NOT NULL` + `UNIQUE(operation_id,id)` |
| Решение | (б). PDB-0003/0008/0009 для `work.tasks.operation_id` сводятся к созданию таблицы с конечными ограничениями; PDB-0008 = N/A с обоснованием «legacy Task отсутствуют» (проверяемо: upgrade from empty). Expand → backfill → validate → contract обязателен для всех изменений после первой применённой ревизии. **[PREP review]** Статус решения: отклонение от порядка Blueprint §5/§14 принято как рабочее; формально PDB-0003/0008/0009 = «N/A pending owner» до решения по NCP-03. PERSIST-017..020 доказываются синтетической test-only expand/backfill/validate ревизией на служебной таблице (не production-схема). [ARC-13, DB-5] |
| Обоснование | Инвариант DOC-005/DOC-064 соблюдается с первого дня; фиктивный backfill не создаёт evidence. |
| Влияние на компоненты/контракты | Alembic revisions S04–S05 |
| Риски и компромиссы | Расхождение с текстом Blueprint §5 → NCP-03 |
| Затронутые тесты | PERSIST-001; тест: вставка Task без operation_id отклоняется; синтетическая ревизия: остановка и перезапуск backfill; NOT VALID→VALIDATE находит orphan |

## ADR-012 — Владеющая Operation для Task, созданной `createTask`

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | OAS: `POST /epics/{epicId}/tasks` → 201 Task; DOC-005/DOC-064: `operation_id NOT NULL`; DOC-064 §8: создание Task требует non-terminal Operation; Spec Add. v1.15 п.2: одна root Operation на принятую команду; terminal Operation не переоткрывается. |
| Связанные требования | PROC-MVP; API-MVP |
| Документы и разделы | DOC-055 §2, Add. v1.2; DOC-064 §8; DOC-005 Add. v1.4; OAS v1.3 createTask |
| Альтернативы | (а) Синхронно завершённая Operation (SUCCEEDED) — блокирует будущие WorkerRun Task (operation terminal, WorkerRun.operation_id = Task.operation_id); (б) Привязка к «текущей» Operation Epic — нарушает «одна Operation на команду» и создаёт неявные агрегаты; (в) Новая root Operation типа `TASK_EXECUTION` в статусе ACCEPTED в той же транзакции, что и Task, + Outbox command |
| Решение | (в). Ответ остаётся 201 Task (контракт не меняется); Operation доступна через Task (additive поле `operationId` — NCP-06). Operation проходит обычный lifecycle и агрегирует результат по Task. Если caller не имеет права на исполнение — Task регистрируется как proposal (OAS: «registered as a proposal according to caller authority») без старта исполнения; Operation остаётся в ожидании решения человека (WAITING_FOR_HUMAN). **[PREP review]** ПЕРЕСМОТР. Публичная команда `createTask` не создаёт собственную Operation и не пишет Outbox-команду старта. Task создаётся только внутри активной non-terminal Operation (`PLAN_EXECUTION`, создаётся при approval PlanVersion, S21) и после включения в одобренный PlanVersion (TX-03; Spec §9). При отсутствии активной Operation команда отклоняется Problem Details с кодом из каталога DOC-006 §16 (код выбирается в S09/S21, не изобретается здесь). Реализация `createTask` переносится из S09 в S21; в S09 остаются остальные записи. Семантика публичной команды (201 vs 202+Location, поле `Task.operationId`) — NCP-08, решение владельца. Прежний вариант «новая root Operation TASK_EXECUTION в ACCEPTED» отозван: переход ACCEPTED→WAITING_FOR_HUMAN запрещён (DOC-055 §2.4), команда с Operation обязана отвечать 202+Location (DOC-055 §2.5), Outbox-старт возникал бы раньше dispatcher/workflow. [ARC-2, DB-1] |
| Обоснование | Сохраняет все BASELINED инварианты без изменения публичного контракта. |
| Влияние на компоненты/контракты | S09, S12, S21 |
| Риски и компромиссы | Рост числа Operation; UX отображает их через Task |
| Затронутые тесты | S09: createTask создаёт ровно одну Operation; retry с тем же Idempotency-Key — та же Task/Operation; Task без Operation невозможна; createTask вне активной Operation → отклонение; Task не включена в PlanVersion → не исполняется; повторный Idempotency-Key — та же Task |

## ADR-013 — Реестр `operation_type`

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | OQ-3 (WORKING): точный enum не определён. Запрещено принимать произвольные строки. |
| Связанные требования | API-MVP; PROC-MVP |
| Документы и разделы | DOC-055 §6; DOC-057 |
| Альтернативы | PostgreSQL enum; CHECK; reference table + code registry |
| Решение | Code registry (Python enum) + reference table `operations.operation_types` (FK), значения добавляются ревизией и ADR на этапе, который вводит команду. Начальные значения: `MANAGER_MESSAGE` (S20), `TASK_EXECUTION` (S09/ADR-012), `SOURCE_INGESTION` (S12/completeUpload), `PLAN_EXECUTION` (S21). |
| Обоснование | Расширяемо без ALTER TYPE; валидация по registry. |
| Влияние на компоненты/контракты | operations schema |
| Риски и компромиссы | Значения — implementation-уровень; синхронизация с DOC-055 через NCP-01 |
| Затронутые тесты | Неизвестный тип → отклонение |

## ADR-014 — Имена PostgreSQL schemas

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | OQ-2 (WORKING). |
| Связанные требования | DATA-MVP |
| Документы и разделы | DOC-005 §14; DOC-064 §3; DOC-065 |
| Альтернативы | Переименование |
| Решение | Использовать имена DOC-005 §14 / DOC-064 §3 / `coding-standards.md`: iam, organization, project, work, requirements, sources, knowledge, decisions, artifacts, traceability, governance, agents, context, integrations, audit, platform, operations, execution; LangGraph — отдельная schema `langgraph` вне Alembic allowlist. |
| Обоснование | Согласовано во всех документах. |
| Влияние на компоненты/контракты | Миграции |
| Риски и компромиссы | — |
| Затронутые тесты | Allowlist test |

## ADR-015 — Набор PostgreSQL ролей по нормативным документам

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DR-10: `.claude/rules/database-and-migrations.md` перечислял `ai_res_manager`/`ai_res_worker`; нормативные DOC-064 §10, DOC-005, DOC-019, DOC-069 — иной набор, Manager/Worker без DB credentials. |
| Связанные требования | SEC P0; DBM-* |
| Документы и разделы | DOC-064 §10; DOC-068 §2; DOC-069; DOC-019 §4 |
| Альтернативы | Следовать правилу проекта |
| Решение | Роли: `ai_res_owner` (NOLOGIN), `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor`, backup identity; login-роли входят в `*_group` роли по DOC-069. `ai_res_manager`/`ai_res_worker` не создаются. Правило проекта исправлено в рамках этого решения (иерархия: нормативные документы выше `.claude/rules`). **[PREP review]** Терминология: `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` — LOGIN-роли, входящие в `ai_res_api_group`, `ai_res_outbox_group`, `ai_res_consumer_group`, `ai_res_auditor_group` (DOC-069). Роль для LangGraph checkpointer не задаётся этим ADR: конфликт BASELINED-документов решён ADR-036. [DB-16, SEC-1] **[PREP review]** ДОПОЛНЕНИЕ (OD-08 закрыт ADR-036): добавляется LOGIN-роль `ai_res_checkpointer`, входящая в `ai_res_checkpointer_group`, права только на schema `langgraph`; пароль держит только процесс API. |
| Обоснование | Иерархия источников истины. |
| Влияние на компоненты/контракты | S04–S05, `.claude/rules/database-and-migrations.md` |
| Риски и компромиссы | — |
| Затронутые тесты | Grants audit; forbidden attributes |

## ADR-016 — Проектирование отсутствующих физических таблиц

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DR-02/DR-09: DDL v1.0 (WORKING) покрывает только execution slice; DOC-064 §1/§3 требует `agents.worker_results`, `audit.audit_events`, `work.task_dependencies`; Roles SQL ссылается на `audit.audit_events`. |
| Связанные требования | DATA-MVP; PERSIST-* |
| Документы и разделы | DOC-005 §5–§16; DOC-064 §3–§7; DOC-065; DOC-069 |
| Альтернативы | Ждать новой версии DDL |
| Решение | Implementation Lead проектирует физические таблицы из логической модели DOC-005 и DOC-064 (UUIDv7 PK, `organization_id`/`project_id`, `row_version`, `timestamptz`, named constraints, RLS FORCE). DDL v1.0 — входной design snapshot, не нормативный DDL. Каждое отклонение от DDL v1.0 фиксируется в ADR этапа. Обновление DOC-065 — NCP-02. **[PREP review]** Drift-snapshot `schema_snapshot.sql` ведётся вручную и ревьюится независимо (не генерируется из миграций) + сверка пересекающихся таблиц с DOC-065, каждое отклонение — ADR этапа. Допустимые `aggregate_type` outbox/events задаются reference-таблицей, а не фиксированным CHECK ('OPERATION','WORKER_RUN'); расширяется ревизиями S06/S10. [DB-10] |
| Обоснование | Без этого невозможны S05–S08; решение в пределах логической модели. |
| Влияние на компоненты/контракты | S05, S06 |
| Риски и компромиссы | Расхождение с будущим DDL владельца |
| Затронутые тесты | Schema drift check против собственного design snapshot `backend/.../schema_snapshot.sql`; drift check падает на намеренном расхождении |

## ADR-017 — Policy & Permission Engine — in-process модуль

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-018 §2, §7 требует независимого Policy Engine; реализация не выбрана. Добавление сервисов в топологию требует владельца. |
| Связанные требования | SEC-001, SEC-002; AUTH-* |
| Документы и разделы | DOC-018 §2, §6, §7; DOC-016 §2; architecture-constraints.md (топология) |
| Альтернативы | OPA sidecar; Cedar; Casbin; in-process |
| Решение | Модуль `ai_res.policy` за `PolicyDecisionPort` (allow/deny/approval-required + reason codes), deny-by-default, версионированная policy-конфигурация, вызывается в каждом enforcement point. Ошибка/недоступность → deny (fail-closed). Внешний engine возможен позже через тот же port. **[PREP review]** Policy-конфигурация версионирована в репозитории, проверяется checksum при старте; невалидная конфигурация или отсутствие версии → deny-all + alert. Изменение — через review и security owner. Каждое решение аудируется с версией policy. Manager/Worker Runtime не вызывают policy in-process: доступ к защищённым действиям — только через API Application Service / Tool Gateway (S17), где PolicyDecisionPort вызывается на каждый tool call. [SEC-7] |
| Обоснование | Не меняет топологию; тестируемо; соответствует модульному монолиту. |
| Влияние на компоненты/контракты | S07 и все последующие |
| Риски и компромиссы | Логика policy в коде — требует review security-reviewer |
| Затронутые тесты | Policy matrix tests; outage → deny; невалидный конфиг → deny; отсутствие версии → deny; решение содержит policy version |

## ADR-018 — Rules Registry и Rules Engine — отдельные интерфейсы в модульном монолите

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | RULE-MVP-01..14 (MVP Matrix Add. v0.7–v0.8) обязательны; в Spec нет этапа; Architecture Concept §15 рекомендует вариант C (гибрид). |
| Связанные требования | RULE-MVP-01..14 |
| Документы и разделы | DOC-001 §15; DOC-009 Add. v0.7, v0.8 |
| Альтернативы | Отдельный сервис; встроить в Policy Engine |
| Решение | Модули `ai_res.rules.registry` и `ai_res.rules.engine` с отдельными интерфейсами от Policy Engine (RULE-MVP-01), совместное развёртывание в API-процессе. Системные правила не переопределяются. Этап S18. |
| Обоснование | Вариант C Architecture Concept; топология не меняется. |
| Влияние на компоненты/контракты | S18, S22 |
| Риски и компромиссы | — |
| Затронутые тесты | RULE-MVP критерии приёмки |

## ADR-019 — Frontend: React + TypeScript + Vite SPA

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Web Project Workspace — основной канал MVP (DOC-004 §18; WS-MVP); frontend-стек нигде не выбран. |
| Связанные требования | WS-MVP; UX-* |
| Документы и разделы | DOC-004; DOC-015 §3, §9; DOC-016 §2 (User Ingress) |
| Альтернативы | Server-rendered templates; Vue; Next.js (SSR-сервер добавил бы процесс) |
| Решение | React + TypeScript (strict) + Vite, статическая сборка, отдаётся Reverse Proxy same-origin с API; cookie session + CSRF; npm + package-lock; Node 22 LTS pinned. Генерация TS-типов из contracts/openapi. |
| Обоснование | Не добавляет runtime-процесс; contract-first типы; ECC имеет react/typescript reviewers. |
| Влияние на компоненты/контракты | S35–S36, S39 |
| Риски и компромиссы | — |
| Затронутые тесты | Vitest + Playwright E2E; axe accessibility |

## ADR-020 — Reverse Proxy: Caddy

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-015 §9: Reverse Proxy — единственная публичная точка; продукт не выбран. |
| Связанные требования | INF-MVP; SEC |
| Документы и разделы | DOC-015 §3, §9; DOC-016 §2 |
| Альтернативы | nginx; Traefik |
| Решение | Caddy (pinned digest), TLS termination, security headers, rate limiting на login (DOC-023 §4) — в приложении, proxy — дополнительный слой. **[PREP review]** Rate limit по client IP: приложение доверяет `X-Forwarded-For` только от Caddy (trusted proxy), Caddy перезаписывает заголовок; вместо hard lockout — progressive delay (иначе DoS учётной записи). Security headers (HSTS, CSP, X-Content-Type-Options) проверяются тестом. [SEC-5] |
| Обоснование | Простая конфигурация TLS для on-prem/local. |
| Влияние на компоненты/контракты | infra |
| Риски и компромиссы | — |
| Затронутые тесты | S03: только proxy опубликован на host; S03: заголовки безопасности; S07: подделанный XFF не обходит лимит |

## ADR-021 — Работа с WORKING Worker Contracts v1.1

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-007 WORKING; S14 требует typed контрактов. |
| Связанные требования | API-MVP; PROC-MVP |
| Документы и разделы | DOC-007; DOC-006 §8; api-and-contracts.md |
| Альтернативы | Ждать BASELINED |
| Решение | Реализовать по v1.1 с явной маркировкой WORKING в коде/тестах; `contractVersion` major проверяется во всех 4 точках, unknown major → fail closed. Изменения полей фиксируются как NCP-04; перевод в BASELINED — владелец. |
| Обоснование | Rules разрешают работу с WORKING при явной маркировке. |
| Влияние на компоненты/контракты | S14, S23 |
| Риски и компромиссы | Rework при изменении контракта |
| Затронутые тесты | Unknown major → reject в 4 точках |

## ADR-022 — Deterministic LLM test double только в test-профиле

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Lifecycle WorkerRun/Manager необходимо тестировать до подключения провайдера (S16 BLOCKED). |
| Связанные требования | API-MVP; INF-MVP |
| Документы и разделы | DOC-076 §2, §8; DOC-006 §11 |
| Альтернативы | Ждать провайдера |
| Решение | `DeterministicLLMGateway` реализует `LLMGatewayPort` для тестов; конфигурационная валидация запрещает его в профилях кроме `test`; отчёты этапов явно указывают, что качество агентного вывода не проверялось. **[PREP review]** Профиль по умолчанию — `prod`. `DeterministicLLMGateway` лежит в отдельном пакете, исключённом из prod-образа; тест: prod-образ не содержит test-модуля. Конфигурационная валидация — дополнительный, не единственный барьер. Embeddings (S27) и E2E-прогоны с double допустимы только в явном test-профиле. [SEC-6, ARC-8] |
| Обоснование | Честное тестирование механики без выдачи заглушки за функциональность. |
| Влияние на компоненты/контракты | S15, S20–S25 |
| Риски и компромиссы | Ложное ощущение готовности — снимается явной маркировкой |
| Затронутые тесты | Профиль local/prod с test double → ошибка запуска; образ без test-модуля; import test-модуля в prod → ошибка |

## ADR-023 — `gateResultId` ↔ ReadinessEvaluation

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DR-04: AsyncAPI v1.6 использует `gateResultId`; DOC-055 §3.2 — переименовать в следующей breaking-safe версии. |
| Связанные требования | — |
| Документы и разделы | DOC-055 §3.2; DOC-008 |
| Альтернативы | Две таблицы |
| Решение | Одна таблица `execution.readiness_evaluations`; event adapter заполняет `gateResultId` = evaluation id; переименование — новая major версия события (NCP-05). |
| Обоснование | Запрет двух таблиц. |
| Влияние на компоненты/контракты | S22 |
| Риски и компромиссы | — |
| Затронутые тесты | Contract test события |

## ADR-024 — Idempotency HMAC keys с key-id

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | HMAC digest обязателен; rotation policy WORKING. |
| Связанные требования | DBM-*; API idempotency |
| Документы и разделы | DOC-064 §8; DOC-006 Add. v1.7; DOC-019 §5 |
| Альтернативы | Без key-id |
| Решение | Хранить `key_id` рядом с digest; активный ключ из Compose secret; проверка по всем незаархивированным key_id. Конкретный период ротации — не задаётся (WORKING), runbook в S37. **[PREP review]** Ротация двухфазная (accepted → active); digest проверяется по всем неархивным key_id в одной транзакции; advisory xact lock по scope+отсортированным digest предотвращает дубль на границе ротации. Runbook компрометации ключа — S37. [DB-11, SEC-11] |
| Обоснование | Ротация без потери идемпотентности. |
| Влияние на компоненты/контракты | S07 |
| Риски и компромиссы | — |
| Затронутые тесты | Rotation test: старый ключ продолжает дедуплицировать; конкурентный запрос на границе ротации не создаёт дубль |

## ADR-025 — Поэтапная observability

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Spec: инкремент без observability не завершён; стек OTel → Prometheus/Loki/Tempo/Grafana. |
| Связанные требования | OBS-* |
| Документы и разделы | DOC-024 §4, §7; DOC-026 |
| Альтернативы | Всё в конце |
| Решение | OTel SDK + structured logging с redaction — с S02; OTel Collector в Compose — S03; Prometheus/Loki/Tempo/Grafana + alerts — S13; Langfuse выключен (content capture off). |
| Обоснование | Каждый этап имеет telemetry с первого кода. |
| Влияние на компоненты/контракты | Все |
| Риски и компромиссы | — |
| Затронутые тесты | Redaction tests с S02 |

## ADR-026 — Инструменты тестирования и статического анализа

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Нужны воспроизводимые проверки уровня Spec §8. |
| Связанные требования | Spec §8 |
| Документы и разделы | Spec v1.22 §8; testing-and-verification.md |
| Альтернативы | — |
| Решение | pytest, pytest-asyncio, hypothesis (stateful tests state machines), Testcontainers, schemathesis (contract), temporalio testing env + replayer, Playwright + axe (UI), ruff, mypy --strict, bandit/pip-audit (security), Vitest. Покрытие — дополнительная метрика, не DoD. |
| Обоснование | Покрывает типы тестов TEST_STRATEGY.md. |
| Влияние на компоненты/контракты | Все |
| Риски и компромиссы | — |
| Затронутые тесты | — |

## ADR-027 — UUIDv7

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | coding-standards: UUIDv7 рекомендован, самодельный генератор запрещён; stdlib 3.13 не имеет uuid7. |
| Связанные требования | DATA-MVP |
| Документы и разделы | DOC-005 §15; coding-standards.md |
| Альтернативы | UUIDv4 |
| Решение | Библиотека `uuid-utils` (RFC 9562); при неподтверждённой надёжности в S02 — UUIDv4 с новой записью ADR. |
| Обоснование | Сортируемость индексов. |
| Влияние на компоненты/контракты | Все таблицы |
| Риски и компромиссы | — |
| Затронутые тесты | Монотонность/формат в S02 |

## ADR-028 — Temporal self-hosted

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | OQ-11; DOC-015 §4: версия/namespace уточняются при сборке Compose. |
| Связанные требования | INF-MVP |
| Документы и разделы | DOC-015 §4, §6 |
| Альтернативы | temporalio/auto-setup (не для production) |
| Решение | `temporalio/server` pinned digest, отдельная БД `temporal_db` в том же PostgreSQL-кластере под отдельной ролью, schema setup — отдельный one-shot job (`temporal-sql-tool`); namespace `ai-res`; Web UI только в admin-сети. Точная версия фиксируется в S03. |
| Обоснование | Соответствие DOC-015, нет auto-setup в release. |
| Влияние на компоненты/контракты | S03, S11 |
| Риски и компромиссы | — |
| Затронутые тесты | S03 health; S11 replay |

## ADR-029 — Безопасный default для risk-tier эскалации

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-051: quantitative risk calibration и authority matrix — WORKING; Spec Add. v1.2 п.9 требует risk-tier adjudication. |
| Связанные требования | PROC-MVP |
| Документы и разделы | DOC-051; Spec Add. v1.2 §9 |
| Альтернативы | Придумать пороги |
| Решение | До решения владельца (OD-05) Manager самостоятельно адъюдицирует только риск `LOW`, определённый детерминированными правилами; всё остальное — human escalation. Пороги не изобретаются, конфигурация пустая = максимальная эскалация. **[PREP review]** До появления правил Rules Registry (S18) класс `LOW` никому не присваивается; LLM-оценка и self-assessment Worker не влияют на класс риска. [SEC-12] |
| Обоснование | Не изобретает WORKING-значения, fail-safe. |
| Влияние на компоненты/контракты | S24, S25 |
| Риски и компромиссы | Больше ручной работы |
| Затронутые тесты | Неопределённый риск → эскалация; LLM/self-assessment не меняет класс риска |

## ADR-030 — Retention: без автоматического удаления

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Retention/legal hold — WORKING (OQ-8); Spec Add. v1.16 п.16. |
| Связанные требования | REL-* |
| Документы и разделы | Spec Add. v1.16 §16; DOC-005 §18 |
| Альтернативы | Придумать сроки |
| Решение | Retention policy — конфигурируемый механизм; до утверждения владельцем (OD-02) автоматическое удаление выключено. **[PREP review]** Исключения из «без автоудаления»: истечение сессий, TTL idempotency, lease — переходы состояния, не удаление данных. Physical purge outbox/inbox выключен до OD-02; алерт на рост объёма (S13). [DB-14] |
| Обоснование | Прямое требование Spec. |
| Влияние на компоненты/контракты | S10, S12, S32 |
| Риски и компромиссы | Рост объёма |
| Затронутые тесты | Политика без значений → удаление не выполняется |

## ADR-031 — Провайдер-нейтральный LLMGatewayPort до решения по провайдеру

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Bifrost — кандидат pending PoC; провайдер/модель первого среза (OQ-1) и разрешение на передачу данных проекта внешнему провайдеру — решение владельца (OD-01). |
| Связанные требования | — |
| Документы и разделы | DOC-076 §2, §7, §8; architecture-constraints.md (LLM доступ) |
| Альтернативы | Выбрать провайдера самостоятельно |
| Решение | S15 реализует port, Model Registry и test double; S16 (Bifrost PoC + provider adapter) BLOCKED до OD-01. Никаких прямых вызовов provider API. |
| Обоснование | Внешний egress проектных данных — решение владельца/security. |
| Влияние на компоненты/контракты | S15, S16, S33, S37, S39 |
| Риски и компромиссы | Задержка end-to-end качества |
| Затронутые тесты | Architecture test: нет импорта provider SDK вне adapter |

## ADR-032 — Статусы этапов и определение DONE

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Master Initialization §8: различать NOT_STARTED…DEFERRED. |
| Связанные требования | — |
| Документы и разделы | testing-and-verification.md |
| Альтернативы | — |
| Решение | Этап считается DONE только в статусе VERIFIED (все применимые DoD подтверждены воспроизводимыми командами из отчёта) либо IMPLEMENTED (static evidence) для чисто документационных этапов. Зависимый этап стартует только после DONE предшественников. Для промптов: READY / PENDING_DEPS / BLOCKED / DONE. |
| Обоснование | Исключает «готово» без evidence. |
| Влияние на компоненты/контракты | Все |
| Риски и компромиссы | — |
| Затронутые тесты | — |

## ADR-033 — Источник SSE и event history API

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Ревью S00: outbox — очередь доставки; API не имеет USAGE на `audit` (DOC-069). |
| Связанные требования | API-MVP |
| Документы и разделы | DOC-061 §9, §12; DOC-006 §4; api-and-contracts.md |
| Альтернативы | Читать outbox |
| Решение | SSE строится из event history (`operations.operation_events`, `agents.worker_run_events`, доменные event history) с ACL-фильтром на каждое событие; Last-Event-ID = (aggregate, sequence) cursor; при выходе за retention — явный gap-сигнал. Outbox никогда не читается API. **[PREP review]** Last-Event-ID — opaque HMAC-подписанный курсор (карта aggregate→sequence), привязанный к сессии и фильтру; подделка/чужой aggregate → отклонение. Поток закрывается при отзыве сессии или прав во время соединения. Для агрегатов S06 (requirements, artifacts и др.) создаётся append-only event history. [SEC-9, DB-12] |
| Обоснование | DOC-061 §12: Outbox не экспонируется пользователям. |
| Влияние на компоненты/контракты | S12 |
| Риски и компромиссы | — |
| Затронутые тесты | SSE replay ACL; gap signalling; revoke сессии/прав закрывает SSE; подделка курсора на чужой aggregate отклоняется |

## ADR-034 — Rework после terminal Operation и RLS/grants для event-таблиц

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-055 §116: повтор после terminal — новая Operation (или дочерняя); composite FK WorkerRun→Task(operation_id,id) BASELINED. Review: DB-1, DB-2, DB-3, DB-4, DB-8 (адаптация WORKING DOC-069). |
| Связанные требования | PERSIST-*; PROC-MVP; SEC P0 |
| Документы и разделы | DOC-055 §116, §353; DOC-064 §10; DOC-069 (WORKING); DOC-065 (WORKING) |
| Альтернативы | Менять composite FK (BASELINED); сменять operation_id у Task |
| Решение | (1) Rework после terminal Operation = новая root Operation + новая Task с additive `derived_from_task_id` + WorkerRun с `derived_from_worker_run_id`; composite FK и immutability сохраняются. (2) `ai_res_api_group`: USAGE на schema `audit`, INSERT-only на `audit.outbox_events` и `audit.audit_events` (без SELECT/UPDATE/DELETE) — иначе невозможны транзакция projection+event+outbox и fail-closed audit. (3) REVOKE UPDATE/DELETE на immutable таблицах (`readiness_evaluations`, `readiness_check_results`, `worker_results`, event history) + trigger; расхождение с DOC-069 фиксируется как discrepancy. (4) Политики для `ai_res_outbox_group`/`ai_res_consumer_group` на outbox/inbox: cross-tenant без GUC, UPDATE только delivery-колонок. (5) Для migrator/owner при FORCE RLS — явные migration-политики; backfill под ними проверяется тестом. |
| Обоснование | Сохраняет все BASELINED инварианты; DOC-069 имеет статус WORKING и требует адаптации. |
| Влияние на компоненты/контракты | S05, S09, S10, S21 |
| Риски и компромиссы | Отклонение от DOC-069 — NCP-02 |
| Затронутые тесты | Grants audit под реальной ролью ai_res_api; атомарность projection+event+outbox+audit; rework после terminal Operation; dispatcher видит события всех tenants; UPDATE immutable → denied |

## ADR-035 — Контуры тестирования и evidence для P0-этапов

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | SEC-10: security-reviewer ECC — та же модель, что и автор; не независимое review. PERSIST-001..024 недостижимы все в S05 (ARC-5, DB-6). |
| Связанные требования | SEC P0; PERSIST-* |
| Документы и разделы | testing-and-verification.md; Blueprint §12 |
| Альтернативы | Считать ECC review достаточным |
| Решение | (1) ECC security-reviewer — обязательный, но не единственный gate; для S03, S05, S07, S37 применяется независимая проверка по ADR-037. (2) PERSIST-тесты распределены по этапам: 001–014 → S05; 003/004 (single head, offline `--sql`) → S04; 015/016 → S10; 023 → S03/S23 (Compose-сеть); 021 → S32; 022 → S37. Отложенные тесты фиксируются явно, не считаются пройденными. |
| Обоснование | Честный evidence без самооценки. |
| Влияние на компоненты/контракты | S03–S07, S10, S32, S37 |
| Риски и компромиссы | Задержка закрытия S05 |
| Затронутые тесты | Матрица PERSIST→этап в TEST_STRATEGY.md |

## ADR-036 — LangGraph checkpointer через checkpoint-broker

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Конфликт BASELINED: DOC-006 §351 и INF-MVP-005 требуют checkpointer в PostgreSQL с доступом «соответствующему Runtime/service role»; Spec Add. v1.18 п.4 и PERSIST-023: у Manager/Worker нет ни DB credentials, ни сетевого пути к БД. Владелец делегировал разрешение противоречий Implementation Lead (Master Implementation Initialization). |
| Связанные требования | INF-MVP-005; PERSIST-023; SEC P0 |
| Документы и разделы | DOC-006 §351; DOC-064 §10; Spec v1.22 Add. v1.18; INF v1.7 §4 |
| Альтернативы | (а) Отдельная роль `langgraph` у Worker Runtime — нарушает PERSIST-023; (б) checkpoint-broker в Application Service; (в) хранить checkpoint в MinIO/файлах — нарушает INF-MVP-005 |
| Решение | (б). Worker/Manager используют собственную реализацию `BaseCheckpointSaver`, которая вызывает внутренний authenticated endpoint Application Service (service identity, audience-scoped, scope = один WorkerRun/thread). Брокер работает в процессе API и пишет в PostgreSQL schema `langgraph` под отдельной LOGIN-ролью `ai_res_checkpointer` (права только на эту schema, без доступа к доменным schemas). Schema создаёт provisioning-ревизия/job под migrator, не runtime (`setup()` DDL не вызывается). Состояние хранится в PostgreSQL и отделено от доменных таблиц — требования DOC-006 и INF-MVP-005 выполнены, DB credentials у Worker нет. Брокер проверяет, что thread принадлежит WorkerRun вызывающего Worker Run grant. |
| Обоснование | Единственный вариант, одновременно удовлетворяющий обоим BASELINED требованиям. |
| Влияние на компоненты/контракты | S03, S04, S23 |
| Риски и компромиссы | Задержка вызова брокера; размер checkpoint — лимиты в S23 |
| Затронутые тесты | Чужой thread → отказ; обращение брокера к доменным schemas → denied под ролью; у Worker нет сетевого пути к PostgreSQL; autogenerate Alembic не видит schema langgraph |

## ADR-037 — Независимая проверка P0-этапов (замена per-stage human sign-off)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Review: ИИ-ревью той же модели не независимо (SEC-10). Владелец поручил выбрать лучшее решение (OD-07). |
| Связанные требования | SEC P0; Spec §8 |
| Документы и разделы | testing-and-verification.md; security.md (P0 release blockers) |
| Альтернативы | Подпись человека на каждом P0-этапе (S03, S05, S07, S37) — тормозит последовательность; только ИИ-ревью — не независимо |
| Решение | Для S03, S05, S07, S37 обязательны четыре слоя: (1) детерминированные проверки без LLM в CI (grants/forbidden attributes audit, RLS coverage, bandit, pip-audit, секрет-скан, negative authorization suite); (2) ECC `security-reviewer` в свежем контексте по принципу blind-first (без чтения отчёта автора) и отдельно `database-reviewer`/`architect` по своей области; (3) Hypothesis/property и adversarial тесты на каждый P0-инвариант; (4) человеческий security owner подписывает чек-лист один раз перед релизным baseline (S37), а не на каждом этапе. Этап не получает VERIFIED при открытом HIGH или непройденных слоях 1–3; без слоя 4 релиз не выпускается. |
| Обоснование | Независимость обеспечивается детерминированными проверками и человеком на релизе, не тормозя последовательность этапов. |
| Влияние на компоненты/контракты | S03, S05, S07, S37 |
| Риски и компромиссы | Человеческая проверка откладывается до релиза |
| Затронутые тесты | CI-джобы слоя 1 падают на намеренных нарушениях |

## ADR-038 — План проектирования недостающих endpoint и событий

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | OD-09 решён владельцем: проектировать недостающие endpoint по документам проекта. OAS v1.3 содержит 26 operations; для этапов S07, S21, S26, S28–S31, S36 нужны дополнительные. |
| Связанные требования | API-MVP; AUTH-*; UX-* |
| Документы и разделы | DOC-023 (Auth); DOC-006 §3–§16; DOC-003; DOC-051; DOC-009 (UX); ADR-009 |
| Альтернативы | Ждать OAS v1.4 от владельца |
| Решение | Каждый этап проектирует свои endpoint в overlay (ADR-009) до написания handler: auth (login/logout/csrf/MFA/recovery) — S07 по DOC-023; approve/reject плана и PlanVersion — S21; approvals требований, decisions/assumptions/risks/unknowns — S26; retrieval/search — S28; connectors/sync — S29; impact/ChangeSet — S30; review/publish артефактов, ChangeRequest, Baseline — S31. Правила: base path `/api/v1`, camelCase, cursor pagination, RFC 9457, If-Match/ETag, Idempotency-Key, 202+Location для долгих команд; события — CloudEvents, additive; имена `operationId` по существующему стилю OAS. Каждый overlay сопровождается ADR этапа, contract tests (schemathesis) и записью в `CONTRACT_TRACEABILITY_MAP.md` со статусом WORKING. |
| Обоснование | Следует всем правилам контрактов; не меняет базовые зеркала. |
| Влияние на компоненты/контракты | S07, S21, S26, S28–S31, S36 |
| Риски и компромиссы | Расхождение с будущей OAS v1.4 — закрывается NCP-06 |
| Затронутые тесты | CI: overlay additive; handler соответствует overlay; schemathesis |

## ADR-039 — Breaking-change detection: собственный diff вместо oasdiff на S01

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | ADR-004 предполагал oasdiff. На момент S01 бинарь oasdiff отсутствует, Docker daemon не запущен, установка через brew меняет глобальное окружение (запрещено без разрешения). |
| Связанные требования | API-MVP-001; Spec §7 |
| Документы и разделы | ADR-004; DOC-006 §15; api-and-contracts.md |
| Альтернативы | brew install oasdiff; docker image по digest; собственный diff |
| Решение | Единый Python-diff (`contracts/tools/contracts_lib.py`: breaking_openapi/asyncapi/jsonschema) с негативными тестами сравнения против снимка `contracts/baseline/`. oasdiff остаётся целевым дополнительным cross-check в CI (pinned image по digest) — подключается в S03 при наличии Docker; расхождение результатов двух инструментов — fail. |
| Обоснование | Воспроизводимо локально без изменения глобального окружения; одна реализация для всех трёх форматов. |
| Влияние на компоненты/контракты | S01, S03 |
| Риски и компромиссы | Собственный diff покрывает не все случаи oasdiff (см. KNOWN_GAPS G-20) |
| Затронутые тесты | test_breaking_*: удаление endpoint/message/поля — breaking; additive optional — нет |

## ADR-040 — Инструменты сохранения контекста: session-brief hook, CONTEXT_HANDOFF, Context7, Serena

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Владелец проекта (выбор 2026-11-11) + Implementation Lead |
| Проблема и контекст | Потеря контекста между сессиями и compaction. Владелец поручил установить ECC-совместимые инструменты. ECC `ck` пишет в глобальные `~/.claude/ck` и в нативную память проекта (нарушает «не менять глобальную конфигурацию»); `suggest-compact.js` в проекте не установлен. |
| Связанные требования | — |
| Документы и разделы | ecc-precedence.md; CLAUDE.md §11 |
| Альтернативы | ECC ck + hooks профиль minimal; сторонние memory-MCP; только ручные заметки |
| Решение | (1) Проектный read-only SessionStart hook `.claude/hooks/session-brief.mjs` (startup|resume|clear|compact) подставляет сводку STATUS + первые 60 строк `CONTEXT_HANDOFF.md` + git status; без сети и записи. (2) `CONTEXT_HANDOFF.md` обновляется в конце этапа/сессии. (3) Context7 MCP `@upstash/context7-mcp@4.6.0` через `.mcp.json` — только имена библиотек и общие вопросы, через ECC `docs-lookup`. (4) Serena MCP `v2.1.0` через `.mcp.json` (uvx из GitHub) — локальная навигация по коду, с S02. Промпты — `docs/implementation/tooling/`. ECC `ck`, memory-MCP третьих сторон не используются. |
| Обоснование | Всё сохранение контекста в репозитории и проверяемо; внешний трафик ограничен именами библиотек. |
| Влияние на компоненты/контракты | Процесс разработки |
| Риски и компромиссы | Serena запускается из GitHub-тега без проверки хэша; запуск вне MCP заблокирован классификатором, работоспособность проверяется владельцем через `/mcp`. Context7 — сторонний сервис (Upstash) |
| Затронутые тесты | Hook выдаёт валидный JSON и не пишет файлы; `/mcp` показывает серверы |

## ADR-041 — Platform primitives S02: курсоры, ошибки, корреляция, error boundary, порты

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-10 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | S02 реализует примитивы без БД; DOC-006 §16 задаёт таксономию ошибок, но не форму курсора, не источник request id и не форму портов S07. Review S02 (fastapi/security/type-design) выявил 500-ответ без корреляции, утечки в spans/логах, слабые порты. |
| Связанные требования | API-MVP (общие HTTP правила); SEC-MVP; OBS |
| Документы и разделы | DOC-006 §5, §16; ADR-008, ADR-024, ADR-025, ADR-027; security.md |
| Альтернативы | Starlette exception handler для 500; ck-подобные библиотеки пагинации; структурное логирование через structlog |
| Решение | (1) Курсор: `base64url(payload).base64url(HMAC-SHA256)`, MAC с префиксом домена `ai-res.cursor.v1`, payload = версия, key id, subject, audience (endpoint+сортировка), digest фильтров (организация/проект передаются в фильтрах), `exp`, keyset; TTL обязателен (значение задаёт контракт endpoint — WORKING); невалидный курсор → 400 `VALIDATION_ERROR` (остальные ошибки валидации — 422). (2) Error boundary — innermost middleware: 500 формируется внутри стека, поэтому request id, traceparent и span применяются; в spans нет exception message/stacktrace (только статус ERROR), в логах только тип исключения. (3) Request id: валидный клиентский принимается (fullmatch), иначе генерируется; traceparent — дочерний span от валидного входящего контекста, в ответе traceparent собственного span. (4) Логи: extras под `ctx`, redaction по ключам и значениям, uvicorn.error/access через тот же formatter, query string отбрасывается. (5) Порты S07: `Principal`, `ServiceIdentity`, `PolicyDecision` (валидируется), `AuditRecord` (enum outcome), `IdempotencyStorePort` с `begin/complete` и состояниями NEW/REPLAY/IN_PROGRESS/CONFLICT; `decide_fail_closed` требует timeout, возвращает только ALLOW. (6) Конфиг: unknown/регистр/секрет в env — отказ запуска; `create_app_from_env` требует cursor key file. (7) 412 `VERSION_CONFLICT` для устаревшего ETag; 409 `AGGREGATE_VERSION_CONFLICT` — на уровне хранилища. |
| Обоснование | Закрывает fail-open пути и утечки, найденные тремя независимыми ревью; формы портов фиксируются до S07. |
| Влияние на компоненты/контракты | S07, S08–S12, S13 |
| Риски и компромиссы | Формат курсора и TTL — WORKING; идемпотентность port принимает plaintext-ключ (HMAC внутри реализации S07) |
| Затронутые тесты | backend/tests/unit/test_platform.py (56 тестов), tests/architecture/test_import_rules.py |

## ADR-042 — MinIO и mc собираются из закреплённых исходников (официальный образ недоступен)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-015 §5.3/§12.2 требуют MinIO и образ по digest; `minio/minio` и `quay.io/minio/minio` публично недоступны (pull denied), сообщество публикует архивные или сторонние образы. |
| Связанные требования | INF-MVP (MinIO), THR-017 |
| Документы и разделы | DOC-015 §5.3, §12.2, §14 |
| Альтернативы | `bitnamilegacy/minio` (архив без патчей); `ghcr.io/coollabsio/minio` (неизвестная модель доверия); отложить MinIO (запрет пустых сервисов). Выбор владельца в сессии S03: сборка из исходников. |
| Решение | `infra/images/minio/Dockerfile`: multi-stage, `golang:1.27.4-bookworm@digest`; `git clone --branch <tag>` + проверка commit SHA (minio `RELEASE.2025-10-15T17-29-55Z` 9e49d5e…, mc `RELEASE.2025-08-13T08-35-41Z` 7394ce0…); `go get` минимальных исправленных версий уязвимых транзитивных зависимостей (x/net, x/crypto, compress, grpc, amqp091-go, thrift, jsonparser, go-jose, otel sdk — списки по деревьям); рантайм `debian:bookworm-slim@digest`, non-root uid 10002, `/data` принадлежит рантайм-пользователю. Не исправленные prometheus CVE — в `vulnerability-exceptions.yaml`. |
| Обоснование | Воспроизводимый источник под контролем проекта; находки сканера сокращены с 44/27 до 2/2 HIGH/CRITICAL; сборка и runtime-набор проходят. |
| Влияние на компоненты/контракты | S03, S27, S28, S32 |
| Риски и компромиссы | Мы отвечаем за патчинг MinIO (поддержка community-ветки неясна); AGPL-3.0 — license review перед релизом; изменённый граф зависимостей не проверялся апстримом (смягчение: runtime-набор bucket/versioning). |
| Затронутые тесты | runtime: MinIO healthy, бакеты и versioning через новый mc; скан собственных образов 0 HIGH/CRITICAL с исключениями |

## ADR-043 — Supply chain S03: SBOM, скан образов, политика исключений

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-015 §14 требует SBOM, vulnerability scan, управление исключениями; первый скан дал десятки HIGH/CRITICAL во всех собственных образах и сотни в сторонних. |
| Связанные требования | THR-017, THR-013, DOC-015 §14 |
| Документы и разделы | DOC-015 §12.2, §14.1–14.7 |
| Альтернативы | Блокировать все образы (стек не собрать до апстрим-патчей); не блокировать ничего; cosign на всё (нет подписей у большинства вендоров). |
| Решение | Syft (SPDX JSON) и Trivy запускаются из образов, закреплённых по digest, над архивами `docker save` (docker.sock не монтируется). Собственные образы `ai-res/*` — блокирующий gate (exit 1 при HIGH/CRITICAL с доступным исправлением); сторонние закреплённые образы — report-only в `infra/releases/scan/` и в KNOWN_GAPS. Исключения: `infra/security/vulnerability-exceptions.yaml` (cve, component, rationale, compensating_controls, owner, expires); просроченная или неполная запись падает. Даты expires — предложения Implementation Lead. Backend: pip-audit по locked runtime-зависимостям. Образ api без pip/setuptools (вендоренные библиотеки давали HIGH). |
| Обоснование | Gate достижим и честен: блокирует то, что мы можем исправить, и не скрывает остальное. |
| Влияние на компоненты/контракты | S03, S37 |
| Риски и компромиссы | Сторонние образы остаются с известными HIGH/CRITICAL (Temporal server 146, UI 117, admin-tools 291, otel 61, Postgres 26 на момент S03); подписи cosign не проверяются; Trivy 0.58.1 — устаревший сканер, обновляется Renovate. |
| Затронутые тесты | tests/test_vuln_exceptions.py; supply_chain.sh на живых образах (exit 0) |

## ADR-044 — Состав и жёсткость локального стека S03 (образы, сети, healthchecks, секреты в процессах)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Нужен воспроизводимый локальный стек, удовлетворяющий DOC-015 §9 и промпту S03, при конкретных ограничениях образов и отсутствии health-эндпоинта в контракте. |
| Связанные требования | INF-MVP-001..041, THR-005, THR-013, PERSIST-023 (сетевая часть), ADR-020, ADR-028, ADR-036 |
| Документы и разделы | DOC-015 §4.4, §5, §6, §9; DOC-019 §3–4 |
| Альтернативы | Один сетевой сегмент; publish admin-портов на loopback; `temporalio/auto-setup`; стандартный entrypoint Postgres с POSTGRES_PASSWORD_FILE. |
| Решение | (1) Образы по tag+digest: Caddy 2.11.9, Postgres 16.15, Temporal server 1.29.7 / admin-tools 1.29.7 / UI 2.49.1, otel-collector 0.116.1, python 3.13.18; (2) сети ingress (единственная не-internal, только Caddy), app/data/admin — `internal: true` (egress deny-by-default, нет шлюза), egress — без участников до S15/S16/S28; наружу `127.0.0.1:8443`; Temporal UI и MinIO console — только admin, недоступны с хоста; Manager/Worker никогда не в data; (3) Caddy пересобран без file capability (`setcap -r`), иначе exec падает при cap_drop ALL; (4) Postgres: собственный entrypoint (`initdb --pwfile`, SCRAM-only, TLS с локальным CA, `pg_hba.conf` по ролям/БД с финальным `reject`, перезаписывается при старте), потому что штатный экспортирует POSTGRES_PASSWORD в окружение процесса; Temporal/provisioning подключаются по TLS с проверкой хоста; (5) Temporal: пароль читается из secret-файла в окружение только процесса `temporal-server`/`temporal-sql-tool` (шаблон конфига принимает пароль лишь из env) — вне `docker inspect`, исключение явно описано; отдельная `temporal_visibility_db` под ролью `temporal` (visibility-схема Temporal конфликтует по `schema_version` с основной) — деталь реализации Temporal, не доменная БД; namespace `ai-res`, retention 72h — WORKING dev default (OD-02); (6) api healthcheck — liveness (любой HTTP-ответ), т.к. health-эндпоинт без контракта запрещён; otel-collector без healthcheck (distroless) — исключение в check_compose; (7) лимиты памяти/pids — WORKING dev значения; (8) schema `langgraph` и роль `ai_res_checkpointer` создаются provisioning-job (ADR-036), доменные роли — S05. |
| Обоснование | Соответствие baseline при проверяемых отклонениях, каждое зафиксировано. |
| Влияние на компоненты/контракты | S03, S04, S05, S11, S13, S23 |
| Риски и компромиссы | Третья БД Temporal; пароль Temporal виден в /proc процесса; liveness ≠ readiness; Manager/Worker → Temporal сеть не решена (G-38). |
| Затронутые тесты | runtime: 77 тестов (сегментация, egress, hardening, секреты, роли); tests/test_check_compose.py: 27 |

## ADR-045 — Схема dev-секретов: SOPS+age, случайные значения, идемпотентная материализация

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DOC-019 §3 / DOC-015 §11.4: секреты в Git только зашифрованными; default credentials запрещены; локальный запуск из чистого клона. |
| Связанные требования | SEC-MVP (secrets), DOC-019 §3, §8 |
| Документы и разделы | DOC-019 §3–4, §8; DOC-015 §9.3, §11.4 |
| Альтернативы | Секреты в `.env`; фиксированные dev-пароли; генерация при каждом запуске. |
| Решение | `make secrets-dev` (`infra/scripts/secrets_dev.py`): age-ключ создаётся вне репозитория (`~/.config/ai-res/age/keys.txt`, 0600, отказ при широких правах), секреты — `secrets.token_urlsafe(48)`, шифруются SOPS в `infra/secrets/encrypted/local.enc.yaml`, расшифровка в `infra/secrets/runtime/` (git-ignored, 0600/0700). Существующие секреты не перегенерируются; материализация идемпотентна и пишет файлы на месте (замена файлов ломает bind mount запущенных контейнеров — найдено тестом). В CI (`AI_RES_SECRETS_WORLD_READABLE=1`) файлы 0644/0755 из-за Linux bind mount с разными uid контейнеров. Сканер репозитория (`scan_secrets.py`) ищет ключи, литеральные присвоения, URL с учётными данными, текущие значения секретов и незашифрованные файлы в `encrypted/`. Зашифрованный файл per-machine (age-ключ разработчика), не коммитится; DOC-015 §17.17 («секреты в Git зашифрованы SOPS») относится к общим секретам поставки, которых в S03 нет. Локальный TLS CA/сертификат Postgres генерируются вместе с секретами. |
| Обоснование | Нет default credentials и plaintext в Git; воспроизводимо; ключ вне репозитория. |
| Влияние на компоненты/контракты | S03, S07 |
| Риски и компромиссы | Файл `local.enc.yaml` per-machine и не коммитится (git-ignored): шифрован под ключ конкретной машины, на чужой машине и в CI секреты генерируются заново, при отсутствии ключа и наличии файла — явная ошибка; ротация и аудит доступа не реализованы (runbook DOC-019 §5 — позже); sops/age ставятся brew (локально) и из закреплённых релизов (CI), хэш age закреплён по первому проверенному скачиванию (апстрим не публикует checksums). |
| Затронутые тесты | runtime: секреты отсутствуют в inspect/env/логах/слоях образов; tests/test_scan_secrets.py: 8 |

## ADR-046 — Роли PostgreSQL S04: provisioning под суперпользователем, ревизия PDB-0001 только проверяет, drift-коррекция

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Промпт S04 требует «PDB-0001: создание schemas, ролей». Но `ai_res_migrator` по Strategy §1.5/§2 не имеет CREATEROLE, а пароли не задаются SQL-миграцией (Strategy §2, DOC-069 §3): роли и пароли миграция создать не может. DOC-069 (WORKING) — шаблон, не исполнимая история. |
| Связанные требования | PERSIST-005..007, DBM-006, DBM-012, DBM-016; SEC P0 |
| Документы и разделы | DOC-068 §1.5–§1.9, §2; DOC-072 §9; DOC-069 (WORKING); ADR-015, ADR-034, ADR-036 |
| Альтернативы | (а) Выдать migrator CREATEROLE (нарушает DOC-068 §1.8); (б) создавать роли в ревизии под суперпользователем (migrator не суперпользователь); (в) provisioning вне Alembic + проверка в ревизии |
| Решение | (в). `infra/config/postgres/provision_roles.sql` (psql, суперпользователь, часть one-shot `postgres-provision`; тот же файл использует тестовый harness) создаёт группы `*_group` (NOLOGIN) и LOGIN-роли `ai_res_migrator/api/outbox_dispatcher/event_consumer/auditor/backup` (+ `ai_res_checkpointer_group`, членство `ai_res_checkpointer`), задаёт SCRAM-пароли из Compose secrets, атрибуты (NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS), владельца БД, `GRANT CONNECT`, role-level `search_path=pg_catalog`, `statement_timeout 15s`, `lock_timeout 2s`, `idle_in_transaction_session_timeout 30s` (значения шаблона DOC-069 §8, WORKING). Скрипт **идемпотентен и возвращает к эталону**: снимает любые членства вне ожидаемого набора (`REVOKE … GRANTED BY`), сбрасывает ADMIN OPTION и явно задаёт опции (`WITH ADMIN FALSE, INHERIT, SET`), `RESET ALL` для role-wide и role-in-database настроек, отзывает лишние `CONNECT`, возвращает владельца БД. Группы — `INHERIT TRUE, SET FALSE`; migrator→owner — `INHERIT FALSE, SET TRUE`. Ревизия PDB-0001 выполняет fail-fast preflight (роли существуют, атрибуты, NOLOGIN у групп, нет членства в owner, search_path зафиксирован, `platform` принадлежит owner) и **ничего не чинит**; затем создаёт 17 схем (`CREATE SCHEMA … AUTHORIZATION ai_res_owner`, строго, без IF NOT EXISTS), `REVOKE ALL … FROM PUBLIC`, `GRANT USAGE` группам (api: все 18 схем; outbox: operations, agents, audit; consumer: operations, agents, execution, audit; auditor: audit — по ADR-034), `ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE … FROM PUBLIC` (содержательно — для функций и типов). `public`: у PUBLIC отозваны все права (в т.ч. USAGE); расширениям в `public` (pgvector, S27) потребуется отдельное явное решение. `ai_res_backup`: роль без прав на данные и без строки в `pg_hba`; профиль привилегий — S32. `postgres` в `pg_hba` не ограничен по адресу (наследие S03, G-44). |
| Обоснование | Соблюдает DOC-068 (migrator без CREATEROLE, пароли вне миграций) и даёт проверяемую базовую линию: слабая настройка ролей останавливает миграцию целиком (транзакционный DDL откатывает схемы). Drift-коррекция закрывает класс «ручная выдача прав переживает повторный provisioning» — найден тестами. |
| Влияние на компоненты/контракты | S03 (provision.sh, hba, secrets), S05+ (грантовые ревизии наследуют роли) |
| Риски и компромиссы | Отклонение от формулировки промпта («ревизия создаёт роли») обосновано DOC-068; миграция не может быть «самодостаточной» на пустом кластере — нужен provisioning (так же, как для БД и `langgraph` в S03). Редактирование уже применённой ревизии: PDB-0001 правилась до первого общего применения, только локальный dev и тестовые контейнеры. |
| Затронутые тесты | test_migrations (sabotage ×5, drift-коррекция), test_roles_and_grants (атрибуты, SCRAM, DDL-отказы, матрица USAGE), SABOTAGE ×37, runtime test_persistence |

## ADR-047 — Миграционная среда S04: Alembic env, SET ROLE owner, advisory lock, одноразовая служба `migrate`, WORKING-таймауты

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Blueprint §4.2/§10 задают требования к env.py и отдельному migration job, но не конкретику: как создать schema `platform` для `alembic_version`, как сериализовать запуски, как запускать job в образе, какие таймауты. |
| Связанные требования | PERSIST-001, -003, -004, -020; DBM-001..003 |
| Документы и разделы | DOC-072 §4, §8, §10; DOC-068 §4; DOC-064 §11; ADR-003, ADR-011, ADR-035 |
| Альтернативы | Запуск миграции при старте API (запрещён); отдельный образ migrate; `Base.metadata.create_all` (запрещён) |
| Решение | (1) `alembic.ini` без DSN, `script_location = ai_res.db:migrations` (работает и из установленного пакета в образе). (2) `env.py`: настройки только из `AI_RES_DB_*` (пароль — файл), отказ под SUPERUSER/BYPASSRLS, `pg_advisory_lock(hashtextextended('ai_res.alembic.migrations',0))` (ожидание ограничено `lock_timeout`), `SET ROLE ai_res_owner`, bootstrap-исключение `CREATE SCHEMA IF NOT EXISTS platform` (Alembic создаёт version table до первой ревизии), `version_table_schema=platform`, allowlist 18 схем через `include_name` (нет `public`, `temporal`, `langgraph`), `compare_type=True`, `compare_server_default=False` до первого drift review; вложенный cleanup в `finally` (rollback → RESET ROLE → unlock с проверкой результата). (3) Одноразовая Compose-служба `migrate`: тот же образ `ai-res/api:dev`, команда `alembic upgrade head`, TLS verify-full, секреты — только `migrator_db_password` и CA; `api` ждёт её завершения (порядок, не запуск). (4) Таймауты миграционного профиля — WORKING: statement 60 с, lock 5 с, idle-in-transaction 60 с (технические значения, не SLO; OD-02). (5) Формат revision: filename `NNNN_intent.py`, id — hex; downgrade PDB-0001 — `NotImplementedError` (forward-fix). (6) Alembic присутствует в образе API (один образ с `migrate`); API-процесс его не импортирует (AST-тест). (7) PERSIST-002 (previous revision): до второй реальной ревизии тривиален; тест — в S05. PERSIST-004 доказан синтетической test-only ревизией с `autocommit_block` + `CREATE INDEX CONCURRENTLY` (ADR-011). |
| Обоснование | Единственный путь DDL, сериализован, не требует суперпользователя, воспроизводим из образа. |
| Влияние на компоненты/контракты | S05+ (ревизии), infra (Compose), CI |
| Риски и компромиссы | Alembic в runtime-образе API — лишняя поверхность (решение: допустимо, отдельный stage — позже, G-45); значения таймаутов WORKING; `long_transaction` в preflight best-effort без `pg_read_all_stats` (G-41). |
| Затронутые тесты | test_migration_graph, test_no_startup_migration, test_migrations (lock, superuser refusal, autocommit), runtime (migrate exit 0, idempotent rerun) |

## ADR-048 — Контроль дрейфа и аудит: reviewed snapshot (pg_dump + каталог), audit SQL как release gate, positive controls

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Промпт требует «Design snapshot schema_snapshot.sql + drift check» и «Grants audit автоматизирован в CI»; формат не задан. Независимое review показало, что проверки без positive control проходят вакуозно. |
| Связанные требования | PERSIST-024, DBM-006, DBM-012, DBM-017; Blueprint §9–§10, §12 |
| Документы и разделы | DOC-072 §9, §10, §12; DOC-068 §8 |
| Альтернативы | Сравнение с design DDL DOC-065 (WORKING, не соответствует принятым решениям ADR-011/034); `alembic check` (не видит роли/гранты/RLS) |
| Решение | (1) Snapshot `backend/ops/postgres/schema_snapshot.sql` = нормализованный `pg_dump --schema-only` (тот же major внутри контейнера; схемы, владельцы, ACL, default privileges, политики; без комментариев/`\\restrict`) + каталожная секция (атрибуты ролей, членства с опциями, role settings, ACL БД; без паролей). Drift = неравенство после `upgrade head`; обновление — `make db-snapshot` и ручной разбор diff; в CI установка `UPDATE_SCHEMA_SNAPSHOT` запрещена. (2) Audit SQL в `backend/ops/postgres/` (`preflight`, `postflight`, `grants_audit`, `rls_coverage`) возвращают строки-нарушения; пусто = пройдено; `audit.sh` — release gate (exit 1 при нарушении, exit 2 при ошибке/пустом файле). RLS-gate default-fail: любая таблица доменных схем без ENABLE+FORCE RLS и политики должна быть в явном `exempt` (сейчас только `platform.alembic_version`). (3) Каждая проверка имеет positive control: параметризованный тест портит состояние и ожидает конкретное имя нарушения (37 случаев), проверки отсутствующих ролей не проходят вакуозно, gate на живом стеке падает на реально испорченном состоянии. (4) Ложное срабатывание (автоматические array-типы строк таблиц) исключено явно. |
| Обоснование | Дрейф и ослабление прав обнаруживаются автоматически и воспроизводимо; пустой результат имеет смысл только вместе с контролем. |
| Влияние на компоненты/контракты | S05+ (каждая таблица: RLS, exempt, snapshot), CI |
| Риски и компромиссы | Snapshot привязан к PG 16.15 (minor — осознанная перегенерация); `rls_coverage` не доказывает корректность выражения политики (это тесты S05); матрица USAGE — только snapshot и тест. |
| Затронутые тесты | test_schema_drift (3), SABOTAGE (37), test_audits_report_missing_roles, runtime audit gate ×3 |

## ADR-049 — Runtime-слой persistence: engine, Unit of Work, tenant context (один раз на транзакцию), конфигурация db_*

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | Blueprint §7–§8 требуют явные транзакции, transaction-local контекст и pool-политику; выбор конкретных механизмов (async, сброс контекста, ошибки begin) оставлен реализации. |
| Связанные требования | PERSIST-008..010, DBM-008..010, DBM-014; INF-MVP |
| Документы и разделы | DOC-072 §7, §8; DOC-068 §3, §7; ADR-008 |
| Альтернативы | Session-level `SET`; middleware, ставящий контекст на соединение; `autobegin` сессии |
| Решение | (1) `db/engine.py`: async engine psycopg 3, `pool_pre_ping`, `pool_recycle` из настроек, `pool_reset_on_return=rollback`; libpq `options` задают `search_path=pg_catalog`, `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`; `application_name`; TLS `verify-full` (отключение допустимо только в environment local/test); пароль только из файла, URL не логируется. (2) `db/tenant_context.py`: `set_config(:name,:value,true)` с bind-параметрами, принимает только `UUID`, пустой project → `''`; политики используют `NULLIF(current_setting(…, true), '')::uuid`. (3) `db/session.py`: `UnitOfWork` — BEGIN при входе, COMMIT только при чистом выходе, ROLLBACK при любом исключении, `autobegin=False`, закрытие сессии при сбое BEGIN; `with_tenant` допускается **один раз** за транзакцию (смена tenant внутри транзакции — `RuntimeError`). (4) Поля `db_*` добавлены в строгий `Settings` (секреты — только `*_file`). (5) Import-linter: `ai_res.db` не зависит от `api`, `modules`, `llm`. |
| Обоснование | Контекст не может пережить транзакцию или смениться внутри неё; ошибка конфигурации — отказ запуска. |
| Влияние на компоненты/контракты | S05–S10 (репозитории, Application Services), S07 (Policy Engine ставит контекст после авторизации) |
| Риски и компромиссы | S04 не содержит доменных таблиц: поведение RLS проверено на test-only probe-таблице с политикой формы DOC-069; реальные политики и негативные тесты — S05. GUC-контекст не защищает от произвольного SQL под API-идентичностью (Strategy §1.12) — документированное ограничение. |
| Затронутые тесты | test_tenant_context (11), test_db_layer (unit), мутация session-level SET обнаружена |

## ADR-050 — S05 срез A: физический дизайн iam / organization / project, общие row guards, справочник ролей

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DDL v1.0 не содержит iam/organization/project; ADR-016 поручает спроектировать таблицы из DOC-005. Словарь ролей DOC-069 / Identity Access Control v1.5 §4 — «стартовый, не окончательная матрица» (WORKING). |
| Связанные требования | DATA-MVP, PERSIST-005..011; DOC-005 §5, §15, §16 |
| Документы и разделы | DOC-005 §5.1–5.3, §15, §16; Identity Access Control v1.5 §4; Blueprint §7, §9; Roles_RLS_v1.0.sql |
| Альтернативы | (а) глобальные iam.users без organization_id и RLS через членство — INSERT пользователя невозможен до членства, вход по e-mail до выбора tenant неразрешим; (б) CHECK-словарь ролей — расширяется только пересозданием ограничения; (в) триггеры вместо composite FK |
| Решение | (1) Все iam-таблицы (users, credentials, sessions, mfa_factors, mfa_recovery_codes, service_identities) несут `organization_id NOT NULL` (домашняя организация, MVP: одна организация на пользователя; многооргановость — через organization.memberships); связь с пользователем — composite FK `(organization_id,user_id)`, межорганизационные связи невозможны на уровне БД. (2) RLS FORCE + политика `organization_id = NULLIF(current_setting('app.organization_id', true),'')::uuid` (organizations — по `id`), `FOR ALL TO ai_res_api_group`, USING = WITH CHECK; grants SELECT/INSERT/UPDATE, без DELETE. Контекст проекта на этих таблицах не требуется (org-level доступ; проектная изоляция — на work/operations/agents/execution). (3) Роли — справочник `iam.roles(code, org_level, project_level)` с семью значениями из IAM v1.5 §4 (WORKING); memberships/project_memberships ссылаются composite FK `(role_code, org_level|project_level)`, поэтому проектная роль не назначается на уровне организации и наоборот. Справочник не tenant-данные: исключён из RLS в `rls_coverage.sql` с причиной, а новая проверка `exempt_table_writable_by_runtime` требует, чтобы runtime не мог писать в исключения. (4) Секреты: credentials принимают только `$argon2id$…`; sessions хранят только 32-байтовые digest токена и CSRF (сырой токен не хранится); TOTP-секрет — `secret_ciphertext` (шифрование и ключи — S07/Secrets). (5) Общие guards в `platform`: `touch_row()` (row_version обязан расти ровно на 1, иначе 23000; выставляет updated_at), `keep_columns_immutable(cols…)` (идентификаторы и scope-колонки), `reject_modification()` (для immutable-таблиц следующих срезов). Функции не SECURITY DEFINER. (6) Минимальные словари статусов (organizations/projects ACTIVE|ARCHIVED, users/service_identities ACTIVE|DISABLED, memberships ACTIVE|SUSPENDED|REVOKED) и service_kind — предложение Implementation Lead, WORKING, расширяются ревизией. |
| Обоснование | Единообразный tenant-контур, невозможность cross-org связей без доверия к приложению, отсутствие секретов в БД, обязательная оптимистичная блокировка на уровне БД. |
| Влияние на компоненты/контракты | S05 срезы B–E, S06, S07 (auth), S08–S09 (repositories) |
| Риски и компромиссы | Вход по e-mail до установки tenant-контекста при FORCE RLS даёт ноль строк: механизм pre-auth lookup (организация по slug/хосту, узкая функция из allowlist SECURITY DEFINER в grants_audit) — решение S07, фиксируется в KNOWN_GAPS. Словари статусов и ролей WORKING. |
| Затронутые тесты | test_identity_org_project_schema (26): default-deny ×9, A/B isolation, WITH CHECK, composite FK ×3, role FK, argon2id CHECK, digests, row_version CAS, immutable scope, no DELETE/TRUNCATE/DDL, auditor/dispatcher denied; rls_coverage/grants_audit/postflight clean |

## ADR-051 — S05 срез B: operations, operation_events и work — целостность на уровне БД, append-only события, закрытые Operation

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DDL v1.0 §1–§3 задаёт Operation, события и связь Task↔Operation, но не задаёт work.epics/tasks/task_dependencies; OAS Task требует `epicId`, но не задаёт словари статуса/приоритета/типа. |
| Связанные требования | PERSIST-005..012, TX-01..TX-03; ADR-011, ADR-012, ADR-013, ADR-034 |
| Документы и разделы | DOC-065 (DDL v1.0) §1–§3; DOC-064 §5.1–5.4, §6; Domain Model v1.9 §5.4–5.5, §10.2, §25–26; State Machine v1.2 |
| Альтернативы | (а) последовательность событий только контрактом репозитория (риск молчаливого разрыва); (б) обновляемые события с audit; (в) Task без Epic; (г) выдумать enum статусов Task |
| Решение | (1) Greenfield: `work.tasks.operation_id NOT NULL`, `UNIQUE(operation_id,id)`, составной FK `(organization_id,project_id,operation_id)` на operations — Task невозможно привязать к Operation другого проекта. `epic_id NOT NULL` (OAS). Parent Operation и lineage `derived_from_task_id` (ADR-034) — тоже составные FK внутри проекта. (2) `operation_type` — справочник `operations.operation_types` (4 значения ADR-013), runtime только SELECT, исключён из RLS с причиной. (3) Целостность последовательности событий проверяется БД при COMMIT (deferred constraint trigger на событиях и на `operations.last_event_sequence`): число событий = max(sequence) = last_event_sequence; контракт репозитория — UPDATE … `last_event_sequence+1` RETURNING под row lock, затем INSERT этой последовательности (MAX()+1 не используется). (4) События append-only для всех: нет UPDATE/DELETE/TRUNCATE у API и триггеры `reject_modification` (включая суперпользователя). RLS событий — через родительскую Operation (шаблон DOC-069 §7). (5) Terminal Operation замораживается полностью (`freeze_when_status_in`): статус не переоткрывается и ничего не меняется; терминальное событие добавляется в той же транзакции, что и переход. (6) Task создаётся только в открытой Operation (`require_open_operation`, ADR-012); rework = новая Operation + Task с `derived_from_task_id`. (7) Статус/приоритет/тип Epic и Task — только формат `^[A-Z][A-Z_]*$` (словарь не задан нормативно, G-49); `task_dependencies` — `dependency_type='BLOCKS'` (WORKING), SELECT/INSERT, циклы — детерминированная проверка домена до активации плана. (8) Отклонение от DOC-069 §5: `ai_res_outbox_group`/`ai_res_consumer_group` не получают SELECT на таблицы событий (без политики FORCE RLS даёт 0 строк; G-50). |
| Обоснование | Инварианты TX-01..03 и PERSIST-012 держатся независимо от дисциплины приложения; нет молчаливого разрыва последовательности, переоткрытия terminal и cross-project связей. |
| Влияние на компоненты/контракты | S05 срезы C–E, S08–S11, S21 |
| Риски и компромиссы | Deferred trigger добавляет два запроса на commit на событие (измерить в S38); terminal-заморозка запрещает поздние обновления progress — проверить с Temporal-интеграцией (S11); словари Task WORKING. |
| Затронутые тесты | test_operations_work_schema (23): default-deny ×5 (+ org-only context), изоляция A/B и sibling project, NOT NULL operation_id, Task в чужой/terminal Operation, rework chain, immutability, dependencies (self/cross/dup), append-only (api и superuser), contiguity/gap/duplicate, PERSIST-012 (8×5 потоков), rollback-атомарность, no access для outbox/consumer/auditor |

## ADR-052 — S05 срез C: agents и execution — инварианты Readiness Gate на уровне БД, insert-only история и результаты

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DDL v1.0 §4–§6 и State Machine v1.2 расходятся: DDL допускает evaluation_status IN_PROGRESS и 5 derivation_reason, JSON v1.2 (новее) — только COMPLETED/EVALUATOR_ERROR и 6 причин (+SPECIALIST_HANDOFF). Таблицы worker_results в DDL нет (ADR-016). |
| Связанные требования | PERSIST-005..012, ADR-016, ADR-023, ADR-034; Readiness Gate invariants (State Machine v1.2) |
| Документы и разделы | DOC-065 §4–§6; DOC-064 §5.3–5.4, §6 (п.1, 7, 11, 12); State Machine v1.2; Operation & Readiness Gate Decision v1.6 §3; Domain Model v1.9 §11.2 |
| Альтернативы | (а) следовать DDL с IN_PROGRESS и UPDATE оценки до завершения; (б) проверять инварианты старта только в приложении; (в) FK worker_runs→tasks только по (operation_id,id) |
| Решение | (1) Расхождение DDL↔JSON решено в пользу JSON v1.2 (последняя BASELINED версия): `evaluation_status ∈ {COMPLETED, EVALUATOR_ERROR}`, `COMPLETED ⇔ gate_outcome и evaluated_at заданы` (EVALUATOR_ERROR не может нести READY — fail-closed), поэтому оценка вставляется один раз и не обновляется; derivation_reason ∈ 6 значений. Согласование — NCP-02. (2) `worker_runs → tasks` составным FK `(organization_id, project_id, operation_id, task_id)` (добавлен `UNIQUE(org,project,operation_id,id)` на tasks): WorkerRun не может ссылаться на Task из другой Operation/проекта; WorkerRun не создаётся в terminal Operation (тот же guard, что для Task). (3) Старт: CHECK — статусы, достижимые только после старта (STARTING … UNVERIFIED), и `started_at` требуют `started_with_readiness_evaluation_id`; trigger `guard_worker_run_start` допускает установку только на COMPLETED READY/READY_WITH_LIMITATIONS (BLOCKED, STALE, EVALUATOR_ERROR отклоняются), отсутствие или чужая оценка отсекается deferred composite FK `(id, started_with…) → evaluations(worker_run_id,id)`; после установки ссылка неизменна. `latest_readiness_evaluation_id` меняется до и после старта. (4) readiness_evaluations, readiness_check_results, worker_run_events, worker_results — INSERT-only: нет UPDATE/DELETE у API и trigger `reject_modification` для всех, включая суперпользователя; TRUNCATE закрыт триггером либо самим PostgreSQL (таблица под FK). Check results допускаются только в транзакции, создавшей оценку (`created_at = now()`), иначе завершённая оценка «пополнялась» бы задним числом. (5) worker_results: один результат на run (rework = новый run, ADR-016), `payload` — объект (jsonb), `contract_version`, SHA-256 payload; scoped-unique `(org, project, worker_run_id)`, чтобы чужой tenant получал FK-ошибку, а не unique-оракул (G-52). Поля контракта DOC-007 — WORKING: структура payload валидируется контрактом в приложении. (6) Terminal WorkerRun заморожен целиком; `finished_at ⇔ terminal`; lineage: `derived_from` ⇔ `derivation_reason`, внутри проекта. (7) События WorkerRun — контроль последовательности при COMMIT тем же deferred trigger, что у Operation (ADR-051). RLS детей — через родительский WorkerRun (шаблон DOC-069). (8) Статус CANCEL_REQUESTED добавлен в словарь WorkerRun (есть в transitions JSON, нет в DDL CHECK). |
| Обоснование | Gate нельзя обойти даже ошибкой приложения: невозможно записать запуск без валидной неизменяемой оценки, переписать историю или результат. |
| Влияние на компоненты/контракты | S05 срезы D–E, S13 (Gate), S14–S15 (Worker), S11 (Temporal activities) |
| Риски и компромиссы | FK на WorkerDefinitionVersion/ContextPackageVersion отложены (G-51); переходы не в БД (G-53); same-transaction guard требует, чтобы evaluator писал оценку и проверки одной транзакцией (это и есть проектный контракт, проверить в S13). |
| Затронутые тесты | test_agents_execution_schema (23): default-deny ×5, изоляция, scope/operation FK, terminal Operation, started⇒evaluation, BLOCKED/STALE/ERROR/чужая оценка, immutability started_with, shape оценки, insert-only (api + superuser), same-transaction check results, worker_results (unique/object/immutable/foreign FK), freeze terminal, lineage, events sequence/append-only, no access outbox/consumer/auditor |

## ADR-053 — S05 срез D: outbox, inbox, audit_events, idempotency_records и reference aggregate_types — права и RLS по ADR-034

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия, Master Implementation Initialization) |
| Проблема и контекст | DDL v1.0 §7–§9 не содержит tenant-колонок у outbox/idempotency и таблицы audit_events; DOC-069 даёт API UPDATE на idempotency и outbox-группе SELECT/INSERT/UPDATE; ADR-034 требует INSERT-only для API и cross-tenant политики сервисных групп. |
| Связанные требования | PERSIST-012..014, TX-01, ADR-016, ADR-024, ADR-034 (2)(4), THR-015 |
| Документы и разделы | DOC-065 §7–§9; DOC-064 §5.5–5.7, §6; DOC-069 §5, §7; Domain Model v1.9 §13 |
| Альтернативы | (а) политика `USING (true)` для outbox без allowlist (ломает default-fail rls_coverage); (б) tenant GUC для dispatcher/consumer (они обслуживают все tenants); (в) outbox через EXISTS по агрегату (полиморфный aggregate_type) |
| Решение | (1) `audit.outbox_events` и `audit.audit_events` получили `organization_id`/`project_id` (outbox: NOT NULL, audit: project NULL для org-level действий), составные FK на projects — иначе RLS строится только полиморфным EXISTS. (2) API: INSERT-only на outbox и audit_events (политики FOR INSERT WITH CHECK по scope; без SELECT/UPDATE/DELETE/TRUNCATE) — THR-015. Dispatcher: SELECT + UPDATE только delivery-колонок (status, available_at, attempt_count, last_error_code, lease_owner, lease_until, published_at), политики `USING (true)` только для `ai_res_outbox_group`; SKIP LOCKED работает (UPDATE-привилегия на колонки). Consumer: INSERT + UPDATE(status, processed_at, error_code) на inbox, cross-tenant, без доступа к outbox и доменным таблицам. Auditor: SELECT audit_events по organization context, default-deny без него. Тriggers `keep_columns_immutable` дублируют колонковые гранты для owner-пути. (3) `rls_coverage.sql`: «always true» допустим только для трёх именованных политик (`cross_tenant` allowlist с причиной) и только если роли политики ⊆ {outbox_group, consumer_group}; иначе нарушение (sabotage-тест). `audit.aggregate_types` — reference, исключён из RLS с причиной, без runtime grants (FK проверяет владелец). (4) Состояния: `IN_FLIGHT ⇔ lease_owner и lease_until`, `PUBLISHED ⇔ published_at`, `PROCESSED ⇔ processed_at`. (5) Atomicity: deferred trigger «outbox-строка описывает реальное событие своего агрегата (event_id, aggregate, sequence)» — orphan откатывает транзакцию; обратное направление остаётся в репозитории (G-54). Новый aggregate_type требует расширения функции в той же ревизии (иначе исключение). (6) audit_events иммутабельны для всех (reject_modification, включая owner/суперпользователя). (7) `platform.idempotency_records`: добавлены `organization_id`, `project_id`, `key_id` (ADR-024); ключ хранится только как HMAC-digest; unique `(organization_id, scope_type, scope_id, key_digest)` — scoped, чужой tenant не получает unique-оракул (G-52); fingerprint и ключевые поля иммутабельны, COMPLETED/REJECTED заморожены (replay читает, не переписывает), `completed_at ⇔ status ≠ IN_PROGRESS`; RLS: организация + `project_id IS NOT DISTINCT FROM` контекст проекта; DELETE нет. |
| Обоснование | Минимальные права каждому принципалу; журнал и outbox нельзя переписать; сервисные cross-tenant роли ограничены колонками и явно перечислены. |
| Влияние на компоненты/контракты | S05 срез E, S07 (Audit/Idempotency), S09 (команды), S10 (dispatcher/inbox) |
| Риски и компромиссы | Dispatcher видит envelope всех tenants — envelope не должен содержать секреты и полный контент (правило событий); lease/retry параметры WORKING; значения словарей audit WORKING (G-55). |
| Затронутые тесты | test_audit_platform_schema (14): allowlist cross-tenant + sabotage, API INSERT-only и scope, orphan/чужой outbox, unique/FK, атомарность в обе стороны, dispatcher cross-tenant+колонки+SKIP LOCKED+состояния, inbox дедуп/колонки, audit immutable + auditor per org, idempotency (scope, frozen, fingerprint, нет raw key), PERSIST-013 (10 потоков → 1 запись), reference read-only |

## ADR-054 — S05: CloudEvents-envelope Operation/WorkerRun событий строго по каноническим сообщениям AsyncAPI v1.6 (G-56, вариант A)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Владелец проекта (выбор варианта A по G-56, 2026-11-11); детали реализации — Implementation Lead |
| Проблема и контекст | Envelope из среза E содержал 8 нестандартных атрибутов верхнего уровня (`organizationid`, `aggregatetype`, …), без `dataschema`, `operationId`, `actor`, `transition`, с коротким `type`; AsyncAPI v1.6 для канонических сообщений требует ровно 9 атрибутов (`additionalProperties: false`) и `data` по `OperationWorkerRunEventData`. Колонка `audit.outbox_events.envelope` иммутабельна, поэтому исправлять форму надо до появления данных. |
| Связанные требования | DOC-008 AsyncAPI v1.6; Event Model v1.4 §4–§5; State Machine v1.2 (operationEventTypes/workerRunEventTypes); coding-standards (CloudEvents, controlled registry); ADR-053 |
| Документы и разделы | AsyncAPI v1.6 components.messages (com.aires.operation.*.v1, com.aires.worker_run.*.v1), schemas.OperationWorkerRunEventData; Event Model v1.4 §4; API Contracts v1.10 §Events |
| Альтернативы | (B) оставить extension-атрибуты и менять контракт; (C) хранить внутреннюю запись и собирать wire-форму в dispatcher (S10); (D) гибрид A+C |
| Решение | (1) `modules/events/envelope.py` строит envelope как чистую функцию: ровно specversion/id/source/type/subject/time/datacontenttype/dataschema/data; tenant, aggregate, operationId, actor, correlationId, causationId, reasonCode, transition, refs — в `data`; event-specific поля (`EventSpec.data`) — в `data.details`; необязательные поля опускаются, а не null. (2) `type = com.aires.<короткое имя>.v<schemaVersion>`; реестры коротких имён = State Machine v1.2 (drift-тест); неизвестный тип, актёр вне {SYSTEM,USER,MANAGER,WORKER,SERVICE} или major-версия вне {1} — ValueError до записи (fail-closed); CHECK на `actor_type` в таблицах истории. (3) `source`/`subject` выводятся из вида агрегата (`urn:aires:operations`, `operations/{id}`, `worker-runs/{id}`), а не передаются вызывающим; `append_event` принимает `operation_id` (для WorkerRun — владеющая Operation). (4) Deferred-триггер `audit.assert_outbox_matches_event` сверяет envelope со столбцами строки (id, type, eventId, organizationId, projectId, aggregateType/Id/Sequence): подделанный envelope чужого tenant отклоняется на COMMIT. (5) Контрактный тест (jsonschema+referencing, закреплены в uv.lock) валидирует envelope каждого из 36 канонических типов против настоящих схем AsyncAPI и проверяет, что схема отвергает прежнюю форму. (6) `data.eventType` НЕ включается: Event Model v1.4 §4 требует его, AsyncAPI запрещает — противоречие передано владельцу (NCP-09), следуем AsyncAPI. |
| Обоснование | Один envelope, соответствующий BASELINED контракту, без технического долга в неизменяемых outbox-строках; нарушение формы ловится тестом, а подделка tenant — базой данных. |
| Влияние на компоненты/контракты | S10 (dispatcher/SSE/consumers читают envelope), S08–S09 (команды формируют EventSpec), S11 (Temporal activities), контрактные тесты событий |
| Риски и компромиссы | WORKING и не зафиксированы нормативно: форма `dataschema` (`urn:aires:schemas:<type>`) и `source` WorkerRun-событий (`urn:aires:worker-runs`) — централизованы в envelope.py, смена = правка констант до S10 (иммутабельные строки до этого не появятся в production). `worker_run.created` есть в State Machine v1.2, но не имеет канонического сообщения в AsyncAPI v1.6: событие строится по тому же шаблону и в тесте названо явно как известный пробел (NCP-11), не молчаливое исключение. Утверждение «соответствует AsyncAPI» верно только для 36 смоделированных типов. |
| Затронутые тесты | tests/contract/test_event_envelope.py (11: реестры = State Machine, пробел AsyncAPI ровно `worker_run.created`, 36 типов × минимум/все опции валидны, схема отвергает старую форму/без dataschema/без operationId/актёр WORKER_RUN/eventType, fail-closed идентичность); test_audit_platform_schema (подделка envelope ×6 откатывает транзакцию); test_repositories (канонический envelope, неизвестный тип/актёр/версия отклоняются до записи) |

## ADR-055 — S05: migration-политики owner под FORCE RLS (ADR-034 п.5, вариант 1) и hardening по независимым review

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Владелец проекта (выбор варианта 1 по H1, 2026-11-11); детали — Implementation Lead |
| Проблема и контекст | Независимый architect-review нашёл, что ADR-034 п.5 («для migrator/owner при FORCE RLS — явные migration-политики; backfill проверяется тестом») не реализован, а PERSIST-017 идёт под суперпользователем на таблицах без RLS и ничего не доказывает: backfill тенантных таблиц под `ai_res_owner` увидел бы 0 строк и «успешно» ничего не сделал бы. Четыре review (database, security, silent-failure, architecture) нашли также дыры Gate и слабые тесты. |
| Связанные требования | ADR-034 (5), ADR-052, ADR-035, PERSIST-005..012, PERSIST-017, security.md (P0), testing-and-verification.md (negative tests) |
| Документы и разделы | Persistence Blueprint v1.0 §9; DOC-064 §6; State Machine v1.2 (invariants Gate); security.md |
| Альтернативы | (2) пересмотреть п.5 новым ADR и завести gap (выбрано не было); BYPASSRLS у migrator (запрещено); отключить FORCE для owner (ломает ADR-034 п.1) |
| Решение | (1) Ревизия 0006: для КАЖДОЙ таблицы с ENABLE+FORCE RLS политика `p_<table>_owner_migration FOR ALL TO ai_res_owner`, включённая только при транзакционном флаге `app.migration_mode='on'` (`set_config(..., true)`); без флага owner остаётся default-deny, runtime-роли политику не получают. `rls_coverage.sql` падает (`owner_migration_policy_missing`), если у RLS-таблицы нет такой гейтированной политики — следующие ревизии обязаны её создавать; два sabotage-теста. Тест `test_owner_backfill_on_a_forced_rls_table_*` идёт реальным путём migrator → `SET ROLE ai_res_owner` (контроль: без флага 0 строк; с флагом — обе организации; флаг не переживает транзакцию; API с флагом ничего не видит). Backfill остаётся под `touch_row` (row_version+1 обязателен). (2) Gate: старт требует МАКСИМАЛЬНЫЙ `evaluation_number` run (BEFORE-guard и deferred-проверка на commit); `agents.worker_results` принимается только для run с `started_with_readiness_evaluation_id` и нетерминального (`FOR SHARE` на run); UNIQUE `(organization_id, project_id, task_id, attempt_number)`. (3) Immutable: `iam.sessions.absolute_expires_at` (+ CHECK idle ≤ absolute), `operations.completion_policy_version/snapshot`. (4) Envelope outbox привязан к событию и tenant триггером (ADR-054). (5) Репозитории: guard секретов на всех jsonb-границах (`assert_no_sensitive_keys` в platform.redaction, токены digest/ciphertext/hmac/signature), `ReadinessRepository.record` валидирует до первого SQL, `cas_update` отвергает пустые изменения, outbox `mark_*` — fencing (owner+attempt+срок lease) и лимит попыток `mark_failed`; `hide_parameters=True` у runtime engine. (6) Verification-проход (2026-11-11, по решению владельца блокировки — в рамках S05): триггер `execution.lock_run_for_evaluation` + `FOR NO KEY UPDATE` на run в `guard_worker_run_start` и `require_started_open_run` (оценка, старт и результат сериализуются; двойной submit результата не даёт deadlock); `app.migration_mode` выключается `on_version_apply` после каждой ревизии; триггер outbox привязывает также `operationId`, `source`, `subject`, `dataschema`, `event_type`, `schema_version`; правило аудита сравнивает точное выражение политики; guard секретов различает secret- и content-токены (ключи-ссылки `source_id` допустимы), `refs`, `reason_code`, `error_code` проверяются по формату. |
| Обоснование | Скрытые no-op миграции и обход Gate выбором выгодной оценки — тихие отказы, которые нельзя найти позже; защита должна быть в БД и подтверждена тестами под реальными ролями. |
| Влияние на компоненты/контракты | Все будущие ревизии с tenant-таблицами (обязаны создавать owner-политику), S07 (auth lookup, column grants), S10 (dispatcher: fencing-токен), S13 (Gate: ревалидация, check_code) |
| Риски и компромиссы | Флаг `app.migration_mode` — не граница безопасности против произвольного SQL владельца роли (owner NOLOGIN, достижим только через SET ROLE у migrator, который и так выполняет DDL); удаление тенантных данных миграцией по-прежнему требует решения владельца (политика FOR ALL включает DELETE). Остаточные gap: G-59…G-68. |
| Затронутые тесты | test_migration_safety (owner backfill, PERSIST-002 с owner-политиками), test_roles_and_grants (sabotage owner_migration_policy_missing ×2), test_agents_execution_schema (start requires latest, result needs started open run, unique attempt), test_identity_org_project_schema / test_operations_work_schema (immutable), test_repositories (fencing, bounded retry, idempotency expiry/key_id, secret guards) |

## ADR-056 — S06: шаблон «идентичность + неизменяемые версии», требования и нумерация

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | DOC-005 §6, §16 требуют иммутабельных версий, контролируемого указателя текущей версии и уникальных номеров без MAX()+1; DDL v1.0 — только design snapshot. |
| Связанные требования | DOC-003, DATA-MVP-004, ADR-016, ADR-027, coding-standards (UUIDv7, MAX+1 запрещён) |
| Документы и разделы | Domain Model v1.9 §6, §16; Requirements Lifecycle v2.7 §13–§16; documentation-and-versioning.md |
| Альтернативы | Статус только на агрегате (версия остаётся «чистым» снимком); указатель без FK; нумерация MAX()+1 — отвергнуты. |
| Решение | (1) Агрегат хранит изменяемые указатель/счётчики (`current_version_id`, `last_version_number`, `row_version`); версия — insert-only, кроме именованных lifecycle-колонок, переходы которых проверяет БД (`platform.guard_status_transition`, `forbid_unset`, `require_initial_state` на INSERT). (2) Указатель — DEFERRABLE составной FK `(id, current_version_id) -> versions(parent_id, id)`: может назвать только версию того же агрегата и tenant. (3) Номера версий непрерывны (отложенная проверка при COMMIT). (4) Статусы RequirementVersion = DOC-003; граф переходов минимальный «только вперёд» (WORKING уточнения: IN_BASELINE->SUPERSEDED). CONFIRMED требует человека (`confirmed_by` FK iam.users), APPROVED — факта approval этого человека для ровно этой версии, IN_BASELINE — baseline_item. (5) Неизвестный тип: реестр `requirement_types` (BR…TR + UNKNOWN), тип вне реестра хранится как UNKNOWN с `declared_type_text`, никогда не ближайший. (6) Человекочитаемые номера: `platform.display_number_counters` (строка под блокировкой, +1 только на единицу), UNIQUE(org, project, номер). (7) Связи: requirement_epics, work.task_requirements (опционально закреплённая версия). |
| Обоснование | «Утверждённое» нельзя получить без существующего факта (approval и т.п.) ни UPDATE, ни INSERT; БД проверяет только наличие факта и что утверждающий — пользователь организации, а полномочия актора проверяет Policy Engine (S07); указатель и нумерация не рассинхронизируются. |
| Влияние на компоненты/контракты | S09 (команды требований), S26–S31, репозиторий `modules/requirements` |
| Риски и компромиссы | Расширение реестра типов на уровне организации и provenance как FK-таблица — не в scope (G-74); номера не привязаны к счётчику на уровне БД (G-72). |
| Затронутые тесты | test_domain_content_schema (immutability, UNKNOWN, lifecycle, указатель/нумерация), test_s06_repositories |

## ADR-057 — S06: sources, uploads, source_versions, extraction_records

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Нужны проверка checksum до обработки, идемпотентность финализации и дедупликация без перезаписи версий. |
| Связанные требования | Source and Context Lifecycle §3, §6; security.md (uploads); testing: duplicate ingestion, parser change |
| Документы и разделы | Domain Model §7; Source and Context Lifecycle v1.3 |
| Альтернативы | Версия из любого объекта MinIO без upload — отвергнуто (ревью C5). |
| Решение | `uploads`: PENDING->UPLOADED->VERIFIED|REJECTED|EXPIRED; VERIFIED только при совпадении checksum и размера (CHECK). `source_versions` insert-only, `object_key ⇔ upload_id` (иначе внешняя ссылка `external_ref`), создаётся из VERIFIED upload того же источника с теми же checksum/размером/типом (триггер); UNIQUE(source_id, checksum) и UNIQUE(upload_id) — повтор не создаёт дубль. `knowledge.extraction_records`: смена parser/pipeline version = новая запись, завершённая запись заморожена. Время жизни upload URL — WORKING конфигурация вызывающего. |
| Обоснование | Содержимое источника не принимается на веру: версия возможна только после проверки. |
| Влияние на компоненты/контракты | S08–S09 (upload API), S10–S11 (ingestion), репозиторий `modules/sources` |
| Риски и компромиссы | SourceFragment/SourceAssertion/DerivedFinding вне scope (G-74); object_key уникален только среди uploads. |
| Затронутые тесты | test_domain_content_schema, test_s06_repositories |

## ADR-058 — S06: traceability, rules, context, decisions

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Полиморфные ссылки не имеют FK; правила нужны трёх уровней; контекст должен быть неизменяемым снимком. |
| Связанные требования | DOC-051, RULE-MVP-02..04, ADR-018, DOC-012 (WORKING) |
| Документы и разделы | Domain Model §8, §10, §11.3; Agent Architecture Concept §15; MVP Capability Matrix RULE-MVP |
| Альтернативы | Универсальная таблица заметок для решений (запрещена); произвольные object/link types (запрещены). |
| Решение | (1) Реестры `object_types`, `link_types`, `link_type_rules` (составной FK пары); засеяны только типы из документов (REFINES, DEPENDS_ON, CONFLICTS_WITH, DUPLICATES, SUPERSEDES для REQUIREMENT↔REQUIREMENT — WORKING, расширение ревизией). Концы связи проверяются триггером на существование в том же tenant; неизвестный тип — fail closed. Подтверждение требует субъекта и evidence. (2) Правила в схеме `governance` (отдельной схемы `rules` в ADR-014 нет): SYSTEM-правила без tenant (читают все, пишут только ревизии), ORGANIZATION/PROJECT — по RLS; одна APPROVED версия на правило; неутверждённая версия не «активна»; Registry и Engine — раздельные интерфейсы (ADR-018, Engine вне scope). (3) Контекст: пакет, неизменяемая версия и элементы пишутся одной транзакцией (число элементов проверяется при COMMIT), элементы — типизированные FK, rule-элемент — только APPROVED версия, видимая tenant. (4) Решения: семь отдельных таблиц DOC-051, статусы — regex (WORKING), risk probability/impact по умолчанию UNKNOWN без числовых порогов. |
| Обоснование | Целостность там, где её может дать БД; остальное — явный WORKING. |
| Влияние на компоненты/контракты | S09, S12 (context), S26–S31, Rules Engine |
| Риски и компромиссы | Словари статусов decisions и политики правил WORKING (G-72); FK worker_runs->context_package_versions не добавлен (G-73). |
| Затронутые тесты | test_domain_content_schema (traceability, rules, context, decisions) |

## ADR-059 — S06: append-only история событий агрегатов и расширение aggregate_types

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | ADR-033: SSE строится из event history (в S06 созданы только таблицы истории — ни один продюсер событий не реализован, G-70); ADR-016/053: aggregate_types расширяется ревизиями S06/S10. |
| Связанные требования | ADR-033, ADR-034, ADR-053, PERSIST-012 |
| Документы и разделы | AsyncAPI v1.6 (RequirementVersionCreated, SourceVersionIngested, Artifact*, Baseline*, ChangeRequest*) |
| Альтернативы | Один общий журнал событий — отвергнут (расходится с operation_events/worker_run_events). |
| Решение | Таблицы `{requirement,source,artifact,baseline,change_request}_events` по образцу operation_events: insert-only для всех, RLS через агрегат, непрерывная sequence при COMMIT. `audit.aggregate_types` расширен. `assert_outbox_matches_event` намеренно НЕ расширена: outbox-строка для новых агрегатов отвергается (fail closed) до решения OD-13 (форма dataschema/source, до S10). |
| Обоснование | История готова для SSE, а публикация в outbox не появится раньше решения владельца по форме envelope. |
| Влияние на компоненты/контракты | S10 (расширить функцию и репозиторий событий), S08–S09 |
| Риски и компромиссы | Эмиссия событий этими агрегатами не реализована (G-70). |
| Затронутые тесты | test_domain_content_schema::test_event_history_is_append_only_contiguous_and_outbox_stays_fail_closed |

## ADR-060 — S06: артефакты, review/approval/publication, baseline; hardening по независимому review

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Validation, Review, Approval, Publication — разные факты; Baseline неизменяем; словарь статусов артефакта «начальный предлагаемый». |
| Связанные требования | DOC-005 §9, Artifacts Lifecycle §6, §10; documentation-and-versioning.md; ADR-037 |
| Документы и разделы | Documentation Artifacts Lifecycle v1.0 §3, §6, §10; Domain Model §9, §16 |
| Альтернативы | Единый статус «готов к публикации» — отвергнуто; смешение validation и approval — отвергнуто. |
| Решение | (1) Статусы ArtifactVersion — реестр (FK), засеян словарём §6.1; граф переходов минимальный (WORKING). APPROVED требует approval человека для ровно этой версии, PUBLISHED — publication (создаётся только для APPROVED), содержимое неизменно. (2) Reviews/approvals/publications/validation_reports — insert-only; approvals имеют типизированные FK (requirement_version | artifact_version | baseline), approver — пользователь организации. (3) Baseline и baseline_items insert-only; элементы добавляются только в транзакции создания baseline, только для APPROVED версий; число элементов проверяется при COMMIT; baseline требует APPROVED approval человека в той же транзакции; номер n следует за n-1. (4) Ревью (C1–C5, M1, M4): все lifecycle-guard-ы действуют и на INSERT (ревизия 0011, `require_initial_state`); object_key ⇔ upload; rule-элемент контекста — только APPROVED версия tenant; approver правила — из той же организации; индексы под FK. РАСХОЖДЕНИЕ: documentation-and-versioning.md называет жизненный цикл DRAFT→PROPOSED→UNDER_REVIEW→APPROVED→PUBLISHED→SUPERSEDED, Artifacts Lifecycle §6.1 — другой словарь; выбран §6.1 как профильный документ, решение — владельцу (OD-14). |
| Обоснование | Статус не может утверждать то, чего нет: факты проверяются самой БД, в том числе при INSERT. |
| Влияние на компоненты/контракты | S26–S31 (artifact/baseline/change control), S07 (approvals через Policy) |
| Риски и компромиссы | Открытые пункты review → G-72 (validation как предпосылка approval, xid-запечатывание, привязка номеров к счётчикам, статус CR, разделение обязанностей). |
| Затронутые тесты | test_domain_content_schema (artifact facts, baseline, lifecycle on INSERT, rule item tenant) |

## ADR-061 — S07: Argon2id и политика паролей

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Параметры Argon2id и состав denylist нормативно не заданы; минимум длины 15 — нормативен. |
| Связанные требования | AUTH-003, AUTH-005, AUTH-MVP-003 |
| Документы и разделы | Authentication and Session Management v1.1 §4; Security Controls v1.2 |
| Альтернативы | bcrypt/scrypt — отвергнуто (требование Argon2id); «тяжёлые» параметры без замеров — отвергнуто. |
| Решение | argon2-cffi, Argon2id; по умолчанию t=2, m=19456 KiB, p=1 (минимум OWASP; **WORKING** — до замера на целевом оборудовании, G-75), параметры в Settings. Минимум длины 15 — пол, ниже настроить нельзя; denylist — упакованный seed из 22 строк + файл (**WORKING**, G-75). Для неизвестной учётки проверяется хеш-«приманка» тех же параметров (одна проверка на любой путь). `needs_rehash` при входе. Пароль нигде не логируется и не попадает в аудит. |
| Обоснование | Единый стоимостной профиль входа не даёт отличить существующую учётку; WORKING-значения вынесены в конфигурацию, а не зашиты. |
| Влияние на компоненты/контракты | modules/iam/passwords.py, Settings, bootstrap, login, смена пароля |
| Риски и компромиссы | Параметры могут оказаться слабее/тяжелее нужного (нет benchmark); denylist неполный. |
| Затронутые тесты | test_iam_passwords, test_iam_login (счётчик проверок = 1 на любом пути) |

## ADR-062 — S07: pre-auth поиск (закрывает G-48), токен сессии и CSRF

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Таблицы `iam.users`/`iam.sessions` под FORCE RLS по организации, а поиск по cookie/логину происходит до tenant-контекста (G-48); SECURITY DEFINER и BYPASSRLS запрещены. |
| Связанные требования | AUTH-007, AUTH-008, SEC-001 |
| Документы и разделы | Authentication v1.1 §5–§6; Persistence Blueprint (RLS); database-and-migrations.md |
| Альтернативы | SECURITY DEFINER-функция поиска — отвергнуто (ослабляет модель ролей); отдельная роль с BYPASSRLS — запрещено; глобальный индекс сессий вне RLS — отвергнуто. |
| Решение | Токен сессии `<org-hex>.<random 256 бит>`: организация — только **подсказка для выбора tenant-контекста**, полномочия даёт совпадение SHA-256 дайджеста под RLS (поддельная подсказка даёт 0 строк). Логин принимает `organizationId` (или `default_organization_id` установки). В БД только дайджесты. Idle 30 мин / absolute 12 ч (конфиг.), ротация при login/MFA/смене пароля не продлевает absolute; revoke write-once (триггер). CSRF-токен = HMAC-SHA256(ключ = токен сессии, «ai-res-csrf-v1»), его можно получить заново через `GET /auth/csrf`; сравнение constant-time. Миграция не потребовалась. |
| Обоснование | Не вводит привилегированный путь мимо RLS; утечка БД не раскрывает токены. |
| Влияние на компоненты/контракты | modules/iam/{tokens,sessions}.py, api/identity.py |
| Риски и компромиссы | Утечка токена из памяти/логов даёт сессию — закрыто редактированием логов и тестом golden. |
| Затронутые тесты | test_iam_sessions, test_iam_tokens_and_request_security, test_identity_http |

## ADR-063 — S07: маршруты auth в overlay; cookie, Origin и CORS

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | В Public API v1.3 нет login/logout/MFA/password (кроме getCurrentUser); handler без контракта запрещён. |
| Связанные требования | AUTH-007, API-MVP, ADR-009/ADR-038 |
| Документы и разделы | Public API v1.3; Authentication v1.1 §6; api-and-contracts.md |
| Альтернативы | Handler без overlay — запрещено; изменение canonical v1.3 — только через NCP-06. |
| Решение | Overlay `contracts/openapi/extensions/identity_auth.yaml` (**WORKING**): login, logout, csrf, password, mfa/enrollment, mfa/enrollment/confirm, mfa/verify. Spectral-правило `aires-idempotency-key`: операция может не объявлять `Idempotency-Key` только с письменным `x-idempotency-exempt` (≥20 символов) — для обмена учётными данными повтор не должен возвращать выданную сессию. Cookie `ai_res_session` (OD-03): HttpOnly, Secure, SameSite=Lax, Path=/api/v1, без Domain; все небезопасные запросы (включая login — login-CSRF) проходят allowlist Origin/Referer; CORS не включается (deny-by-default), пустой allowlist отказывает всё. |
| Обоснование | Контракт предшествует коду; исключение из идемпотентности явное и проверяемое. |
| Влияние на компоненты/контракты | contracts/, api/identity.py, api/request_security.py, infra (AI_RES_ALLOWED_ORIGINS) |
| Риски и компромиссы | Overlay WORKING до NCP-06; wire-имена cookie/CSRF ждут security owner (OD-03). |
| Затронутые тесты | contracts tests (3), test_identity_http, infra runtime (origin/CORS через Caddy) |

## ADR-064 — S07: прогрессивная задержка входа и определение IP клиента

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | DOC-023 §4 требует rate limiting без hard lockout; пороги нормативно не заданы. |
| Связанные требования | AUTH-005, AUTH-MVP-004 |
| Документы и разделы | Authentication v1.1 §4.3; Infrastructure (ADR-020: Caddy перезаписывает X-Forwarded-For) |
| Альтернативы | Постоянная блокировка учётки — отвергнуто (DoS по чужой учётке); Redis — не в топологии MVP. |
| Решение | Счётчики по ключам account+ip, ip, account, global; задержка растёт экспоненциально от base до max, решение принимается ДО проверки пароля (верный пароль во время задержки тоже ждёт); состояние процесса, ограниченное по размеру. Все пороги — Settings (**WORKING**). XFF учитывается только от пиров из `trusted_proxy_cidrs`, берётся самый правый недоверенный хоп; пусто = XFF игнорируется. |
| Обоснование | Подделка XFF не обходит лимиты (счётчик account остаётся); нет вектора вечной блокировки. |
| Влияние на компоненты/контракты | modules/iam/throttle.py, api/client_ip.py, Settings |
| Риски и компромиссы | Состояние process-local: при нескольких процессах API лимит ослабляется (G-76); без фиксированной подсети app за Caddy IP клиента не доверяется (G-77). |
| Затронутые тесты | test_iam_throttle_and_client_ip, test_identity_http (forged XFF) |

## ADR-065 — S07: TOTP MFA, recovery codes и шифрование seed

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | MFA обязательна для привилегированных ролей; хранение seed и защита от повтора кода не заданы. |
| Связанные требования | AUTH-006, AUTH-MVP-005 |
| Документы и разделы | Authentication v1.1 §7; Security Architecture v1.2 |
| Альтернативы | Хранить seed открытым — запрещено; SMS/e-mail — вне MVP. |
| Решение | pyotp (SHA1, 6 цифр, 30 с; окно `mfa_window_steps` — **WORKING**). Seed шифруется AES-256-GCM (`SecretBox`, id ключа в blob, AAD = org/user/factor), ключ — Compose-секрет `mfa_encryption_key`. Recovery codes: 120 бит, хранится SHA-256, одноразовые. Повтор TOTP отклоняется compare-and-set по `last_used_step` + монотонный триггер БД (миграция 0012). Подтверждение enrolment и verify ротируют сессию. Сброс MFA — отдельный привилегированный путь с аудитом. |
| Обоснование | Повтор кода и подмена блоба seed между пользователями отсекаются на уровне БД/AAD. |
| Влияние на компоненты/контракты | modules/iam/{totp,secretbox,mfa}.py, миграция 0012, infra secret |
| Риски и компромиссы | Ротация ключа MFA — отдельный runbook (SEC-027, не сделан); факт «MFA обязательна для роли» принуждается Policy на привилегированных действиях, не при входе. |
| Затронутые тесты | test_iam_secretbox_and_totp, test_iam_mfa, test_identity_http (MFA flow) |

## ADR-066 — S07: bootstrap первого администратора

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Default credentials запрещены; нужен одноразовый путь создания первого admin. |
| Связанные требования | AUTH-004, AUTH-MVP-003 |
| Документы и разделы | Authentication v1.1 §3.3; security.md |
| Альтернативы | Admin из миграции/seed — отвергнуто (default credentials); HTTP-endpoint — отвергнуто (публичная поверхность). |
| Решение | CLI `python -m ai_res.cli.bootstrap` (профиль Compose `bootstrap`, `make bootstrap`): секрет и пароль — только через `getpass`, не argv/env/логи; секрет читается из Compose-файла и сравнивается constant-time. Одноразовость — singleton `platform.bootstrap_state` (миграция 0013, append-only, атомарный claim по PK); повтор → отказ, аудит `AUTH_ACCOUNT_INVITED` (SYSTEM). Печатает только идентификаторы. Секрет не монтируется в API. |
| Обоснование | Окно атаки — одна процедура с секретом, а не постоянная поверхность. |
| Влияние на компоненты/контракты | modules/iam/bootstrap.py, cli/bootstrap.py, миграция 0013, compose |
| Риски и компромиссы | Секрет не инвалидируется файлом (одноразовость — в БД); runbook не написан (G-78). |
| Затронутые тесты | test_iam_bootstrap, infra check_compose |

## ADR-067 — S07: Policy Engine — конфигурация, решения, enforcer, аудит

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | ADR-017: in-process, deny-by-default, fail-closed; матрица ролей и действий нормативно не задана. |
| Связанные требования | SEC-001, SEC-002, SEC-MVP-001, AUTH-006, AUTH-012 |
| Документы и разделы | Identity & Access Control v1.5; Security Architecture v1.2 |
| Альтернативы | Решения в коде handler-ов — отвергнуто; RLS как замена Policy — запрещено. |
| Решение | Версионируемый `policy_config.json` с закреплённым SHA-256; недопустимая/без версии/с дубликатами конфигурация = deny-all (`policy_config_invalid`). Решение: неизвестное действие, неверный тип ресурса, нет scope, не-USER актор, автономия > A2, неактивный субъект/членство, нет grant, нет MFA — DENY с reason code; человеко-только действия (`humanOnly`) недоступны сервисам/агентам. `PolicyEnforcer`: ALLOW аудируется в транзакции вызывающего (откат действия откатывает аудит), DENY — в собственной транзакции, затем 403 или одинаковый 404 при `conceal`; недоступность/таймаут/мусор → 503 (fail-closed). Матрица (`iam.*`) — **WORKING** (OD-15). |
| Обоснование | Каждое решение воспроизводимо (policy_version) и аудируется; ослабить матрицу можно только изменением конфигурации с новой контрольной суммой. |
| Влияние на компоненты/контракты | ai_res/policy/*, ports (PolicyRequest.attributes, decide_or_fail), modules/iam/accounts.py |
| Риски и компромиссы | Для `iam.self.read/logout` ALLOW не аудируется (`auditAllow:false`) — отступление от «каждое решение аудируется» (G-79); матрица не утверждена владельцем. |
| Затронутые тесты | test_policy_config (22), test_policy_engine (98), test_iam_accounts |

## ADR-068 — S07: сервис идемпотентности (HMAC + key_id)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | ADR-024; репозиторий S05 принимает готовые дайджесты — нужен слой, который их строит. |
| Связанные требования | API-MVP (Idempotency-Key), ADR-024 |
| Документы и разделы | API and Interaction Contracts v1.10; api-and-contracts.md |
| Альтернативы | Хранить ключ открытым — запрещено; общий хеш без ключа — отвергнуто (перебор). |
| Решение | Ключ 16..128 печатных ASCII. Дайджест = HMAC-SHA256(ключ из key ring, org|тип/id актора|команда|ключ); отпечаток запроса — тоже HMAC (тот же ключ записи) от канонического JSON. Поиск по дайджестам под всеми принятыми ключами кольца (ротация); advisory xact lock по неключевому хешу scope сериализует гонку на границе ротации. Файл кольца: `<id> <base64 32 байта>`, первая строка активна. Повтор → REPLAY, тот же ключ с другим телом → 409 `IDEMPOTENCY_KEY_REUSED`. TTL (`idempotency_ttl_hours`, **WORKING**, G-58). |
| Обоснование | Сырой ключ и тело не попадают в БД; параллельные одинаковые запросы дают одну запись. |
| Влияние на компоненты/контракты | modules/idempotency/service.py, Settings |
| Риски и компромиссы | Кольцо ключей не подключено к compose до первого идемпотентного endpoint (G-80); политика очистки/takeover — G-58. |
| Затронутые тесты | test_idempotency_service (18, включая мутацию: без lock гонка проваливается) |

## ADR-069 — S07: идентичности сервисов — короткоживущие токены Ed25519

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | AUTH-012: человек, сервис и Worker не подменяют друг друга; браузерная сессия не принимается Runtime. |
| Связанные требования | AUTH-012, AUTH-MVP-008, SEC-013 |
| Документы и разделы | Authentication v1.1 §8; Identity & Access Control v1.5 §3 |
| Альтернативы | Общий HMAC-секрет — отвергнуто (любой сервис подделает другого); mTLS — вне scope S07. |
| Решение | Токен `ar1.<payload>.<подпись>`: claims `iss, aud, iat, exp, jti` (без ролей и секретов), подпись Ed25519 с доменным префиксом; у каждого сервиса свой закрытый ключ, верификатор держит только публичные ключи по издателям (две записи при ротации). Срок ограничен при выпуске и при проверке (`service_token_max_ttl_seconds`, **WORKING** 300 с); неизвестная версия/лишние или дублирующиеся claims/чужая аудитория/срок — отказ; верификатор не бросает исключений. Не является Worker Run grant и не даёт прав. |
| Обоснование | Подделать токен другого сервиса можно только его ключом; сессия и сервисный токен имеют разные форматы. |
| Влияние на компоненты/контракты | modules/iam/service_tokens.py, ServiceIdentityPort |
| Риски и компромиссы | Потребителей пока нет (Manager/Worker/dispatcher — S11/S23); ключи не в compose (G-80); защиты от повтора jti нет (токены короткоживущие, аудитория ограничена). |
| Затронутые тесты | test_iam_service_tokens (22) |

## ADR-070 — S07: аудит аутентификации и отзыв сессий при изменении аккаунта

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | AUTH-008/013: события входа, MFA, смены пароля аудируются без секретов; отключение и отзыв роли немедленно закрывают сессии; сбой аудита отказывает действию. |
| Связанные требования | AUTH-008, AUTH-013, SEC-019, SEC-020 |
| Документы и разделы | Authentication v1.1 §6, §9; Security Architecture v1.2 |
| Альтернативы | Аудит «после коммита» — отвергнуто (потеря при сбое); логирование вместо аудита — запрещено. |
| Решение | `SqlAuditWriter` пишет в `audit.audit_events` в транзакции действия; ключи `details` проверяются фильтром чувствительных имён; организация обязательна. Неуспех входа аудируется в закоммиченной транзакции. `AccountService.disable_user_in/revoke_membership_in` меняют статус, отзывают все сессии (USER_DISABLED/ROLE_REVOKED) и пишут аудит одной транзакцией; нельзя отключить себя и последнего активного владельца; чужой/несуществующий пользователь — одинаковый 404. |
| Обоснование | Утверждённое событие и его аудит атомарны; отзыв не зависит от обновления UI. |
| Влияние на компоненты/контракты | modules/audit/writer.py, modules/iam/accounts.py |
| Риски и компромиссы | Расхождение портов: `AuditOutcome.ALLOWED` порта и `SUCCEEDED` в БД сведены маппингом; статусы пользователя Auth §3.1 (INVITED/SUSPENDED/LOCKED) шире `iam.users.status` (ACTIVE/DISABLED) — G-81. |
| Затронутые тесты | test_iam_audit_writer, test_iam_accounts, test_identity_http (golden логов и аудита) |

## ADR-071 — S07: счётчики ip и global — сигнал, а не отказ; фиксированная подсеть app

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Review S07 (R01/SEC-03): за одним адресом прокси лимит по IP превращается в способ отключить вход всем. Auth v1.1 §4 требует rate limit по account, source signal и глобальному порогу, но не фиксирует, что порог отказывает. |
| Связанные требования | AUTH-005 |
| Документы и разделы | Authentication v1.1 §4; Security Architecture v1.2 |
| Альтернативы | Жёсткий отказ по ip/global — отвергнуто (DoS на всех пользователей); убрать счётчики — отвергнуто (нужен сигнал атаки по многим аккаунтам). |
| Решение | Отказывают (progressive delay с потолком) только счётчики (account, ip) и account. Счётчики ip и global при достижении порога один раз пишут AUTH_RATE_LIMITED с исходом FAILED и причиной `ip_threshold_signal`/`global_threshold_signal`; режим переключается `AI_RES_LOGIN_ENFORCE_IP_GLOBAL` (WORKING, по умолчанию false). Сеть `app` получает фиксированную подсеть 172.28.20.0/24, Caddy — адрес 172.28.20.2, API доверяет X-Forwarded-For только от 172.28.20.2/32 (WORKING; подсеть может конфликтовать с сетями хоста). Решение владельца, делегировано 2026-11-12. |
| Обоснование | Задержка по аккаунту остаётся против подбора пароля; атакующий может временно замедлить конкретную жертву (принятый риск, смягчается MFA и потолком задержки). **NCP-12 (PROPOSED):** уточнить в Auth v1.1 §4, что ip/global — сигнал. |
| Влияние на компоненты/контракты | modules/iam/throttle.py, Settings, api/identity.py, infra/compose.yaml |
| Риски и компромиссы | Режим сигнала не защищает от распределённого перебора по одному аккаунту сильнее, чем account-порог; нормативный текст допускает и иное прочтение. |
| Затронутые тесты | test_iam_throttle_and_client_ip (signal mode), test_iam_login (burst), check_compose |

## ADR-072 — S07: повторное подтверждение пароля и код ответа

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Review S07 (R03, SEC-05): неверный текущий пароль при смене отдавал 401 (клиент разлогинивает пользователя); подключение TOTP не требовало свежего доказательства. |
| Связанные требования | AUTH-003, AUTH-007 |
| Документы и разделы | Authentication v1.1 §3.2, §5; NIST SP 800-63B §6.1.2 |
| Альтернативы | Оставить 401 — отвергнуто (путает с истёкшей сессией); не требовать пароль при подключении TOTP — отвергнуто (кража cookie закрепляет чужой фактор). |
| Решение | Неверный текущий пароль — 422 VALIDATION_ERROR с `errors[{field: currentPassword, reason: invalid_current_password}]`, попытка учитывается throttle. `POST /auth/mfa/enrollment` требует `currentPassword` (`AuthService.reauthenticate`: throttle, аудит AUTH_REAUTHENTICATED, 422 при ошибке). Overlay WORKING обновлён. Решение владельца, делегировано 2026-11-12. |
| Обоснование | Клиент не теряет сессию на опечатке; привязка аутентификатора требует свежей аутентификации. |
| Влияние на компоненты/контракты | api/identity.py, modules/iam/auth.py, contracts overlay |
| Риски и компромиссы | Изменение WORKING overlay; потребителей вне репозитория нет. |
| Затронутые тесты | test_identity_http (fresh password proof), test_iam_login |

## ADR-073 — S07: иерархия организационных ролей при действиях над пользователями

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-11 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Review S07 (SEC-06): ORGANIZATION_ADMIN мог отключить, отозвать членство или сбросить MFA владельца (кроме последнего). IAM v1.5 иерархию ролей не описывает. |
| Связанные требования | AUTH-008 |
| Документы и разделы | Identity & Access Control v1.5 (иерархия не определена); принцип наименьших привилегий |
| Альтернативы | Оставить только защиту последнего владельца — отвергнуто; вынести правило в матрицу политик — отвергнуто (это инвариант домена, не конфигурация). |
| Решение | `ensure_may_act_on`: ранг OWNER=2, ADMIN=1, прочие/нет=0; действие допустимо, если ранг актора строго выше ранга субъекта, либо оба OWNER. Применяется в `AccountService` (disable, revoke membership) и `MfaService.reset`; отказ — 403 ACCESS_DENIED, reason `role_hierarchy`. Защита «последнего владельца» и самоблокировки сохраняется. **WORKING**: нормативный документ молчит. Решение владельца, делегировано 2026-11-12. |
| Обоснование | Скомпрометированный администратор не снимает защиту владельцев. |
| Влияние на компоненты/контракты | modules/iam/accounts.py, modules/iam/mfa.py |
| Риски и компромиссы | Ранги вшиты в код, при новых ролях нужно расширять. Отказ иерархии аудируется отдельной транзакцией (POLICY_DECISION, DENIED, reason `role_hierarchy`), как отказы Policy Engine; если запись не удалась — 503, действие не выполняется. |
| Затронутые тесты | test_iam_accounts (role hierarchy, audit trace, 503 при сбое аудита), test_iam_mfa (reset) |

## ADR-074 — S08: слой чтения (read model), DTO, cursor-пагинация, ETag

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | 12 GET Public API v1.3 нужны с ACL, стабильной пагинацией и явным DTO; ORM-сущности наружу не отдаются. |
| Связанные требования | API-MVP-003/007, SEC-001/002 |
| Документы и разделы | Public API v1.3 (GET), API & Interaction Contracts v1.10 §3/§5/§6; api-and-contracts.md (cursor, ETag) |
| Альтернативы | Возвращать ORM-модели напрямую — отвергнуто (правило явного DTO); offset-пагинация — запрещена; count всех объектов — запрещён (утечка). |
| Решение | `modules/readmodel/queries.py` (SQL-запросы, плоские mapping) + `api/read_api.py` (маршруты и DTO-мапперы). Keyset по `(created_at,id)` / `(display_number,id)` / `(version_number,id)`, выборка limit+1 для `hasMore`. Курсор — HMAC-подписанный (S02), привязан к пользователю, операции, организации и области; форма keyset проверяется ДО транзакции (плохой курсор = 400 без обращения к БД и без аудита); пустой `cursor` = первая страница. `limit` 1..100 (OAS), вне диапазона — 422 `VALIDATION_ERROR`. TTL курсора — `cursor_ttl_seconds` (**WORKING**, 900 c). ETag — `format_etag` (вид «v<N>» в кавычках, совместим с `parse_if_match` для S09) на `getProject` и `getTask` (как объявлено в OAS). `Cache-Control: no-store`. |
| Обоснование | Один стиль пагинации и ETag для всех чтений; нет расхождения форматов между чтением и будущими записями. |
| Влияние на компоненты/контракты | api/read_api.py, modules/readmodel/, platform/config.py (`cursor_ttl_seconds`). |
| Риски и компромиссы | `listRequirementVersions`/`listArtifactVersions` в OAS без параметров `limit`/`cursor`; реализация принимает их как аддитивное расширение (G-89). TTL курсора — WORKING. |
| Затронутые тесты | test_read_api (пагинация, ничьи по времени, limit равен размеру, плохие/просроченные курсоры, ETag), test_read_api_schemathesis |

## ADR-075 — S08: разрешение проекта для GET по id, видимость списков, отсутствие вложенных соединений

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | RLS проектных таблиц требует пары (organization, project); по id объекта проект заранее неизвестен. `SECURITY DEFINER` в проекте нет, owner подчиняется FORCE RLS. |
| Связанные требования | SEC-001/002, IAM v1.5 §7/§10 |
| Документы и разделы | security.md (IDOR → 404), database-and-migrations.md (RLS не меняется без решения) |
| Альтернативы | Индекс расположения объектов (новая таблица + триггеры + backfill) — отложено (G-87); `SECURITY DEFINER` — отвергнуто (не обходит FORCE RLS без смены политик); смена GUC внутри SQL — отвергнуто. |
| Решение | GET по id перебирает проекты, которые вызывающий вправе читать (`visible_projects`), по одной короткой транзакции в его tenant-контексте; при находке Policy Engine решает по владеющему проекту, отказ и «нет объекта» дают один и тот же 404. Запросы дополнительно фильтруют `project_id` (defense in depth рядом с RLS). Предел перебора `read_lookup_max_projects` (**WORKING**, 100): сверх предела — 503 с логом, пользователь работает через списки внутри проекта. Список `GET /projects` строится SQL-фильтром, повторяющим `PolicyEngine.decide(project.read)`; **принятое исключение** из «каждый запрос проходит Policy Engine»: равенство закреплено параметризованным тестом по матрице роли × MFA × статус членства, по-объектный путь всегда проходит движок. Чтобы запрос не держал два соединения (пул), для чтений движок вызывается ДО открытия транзакции данных (`PolicyEnforcer.decide` + `record_allow`); запись аудита ALLOW остаётся в транзакции данных (нет записи — нет данных). Отказ `resource_not_visible` (неизвестный/чужой проект) аудируется на уровне организации (иначе FK давал 503 вместо 404 и раскрывал существование); искомый id кладётся в `details.probedProjectId`. |
| Обоснование | Нет изменений схемы/RLS; один ответ на «чужой/несуществующий»; фиксированное число соединений на запрос. |
| Влияние на компоненты/контракты | api/read_api.py, policy/enforcer.py (`decide`, `record_allow`, якорь аудита), policy/engine.py (константа причины). |
| Риски и компромиссы | Стоимость промаха O(P) транзакций (P не больше предела), нет троттлинга запросов (G-88); решение движка и чтение данных не атомарны (RLS и проверка членства повторно действуют на уровне организации/проекта). |
| Затронутые тесты | test_read_api (IDOR, параллельные запросы без исчерпания пула, предел перебора, равенство SQL и движка), test_policy_engine |

## ADR-076 — S08: матрица Policy Engine для чтения проектных объектов (OD-15, WORKING)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | В матрице v2026-11-11.1 не было доменных read-действий. |
| Связанные требования | SEC-001/002 |
| Документы и разделы | IAM v1.5 §4 (матрица — стартовый словарь), DECISIONS_PENDING OD-15 |
| Альтернативы | Дополнительно Org Owner/Admin без членства в проекте — отвергнуто владельцем (2026-11-12): минимальные права. |
| Решение | Версия `2026-11-12.1` (статус WORKING, контрольная сумма перепинована): `project|epic|task|requirement|source|artifact|worker_run.read` — все пять проектных ролей и org `AUDITOR`. `PROJECT_ADMIN` как привилегированная роль требует подтверждённого MFA. Org Owner/Admin доступа к проектным данным без членства в проекте НЕ имеют. Старт API проверяет наличие всех семи действий, их `resourceType` и одинаковые наборы ролей (иначе отказ запуска). Аудит ALLOW чтений оставлен включённым (ADR-017); рост аудита от чтений/отказов — OD-17. |
| Обоснование | Решение владельца (вариант «только члены проекта»); fail-closed. |
| Влияние на компоненты/контракты | policy/policy_config.json + .sha256, api/read_api.py (проверка на старте). |
| Риски и компромиссы | Матрица остаётся WORKING (OD-15 не закрыт). Org Owner/Admin должны быть добавлены в проект, чтобы читать его. |
| Затронутые тесты | test_policy_engine (матрица read × роль × MFA), test_read_api |

## ADR-077 — S08: поля DTO без источника в БД и отличия от OAS

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Часть обязательных полей OAS не имеет источника в схеме S05–S06. |
| Связанные требования | API-MVP-003 |
| Документы и разделы | Public API v1.3 (Project, WorkerRun, Requirement); правило «не изобретать бизнес-поля» |
| Альтернативы | Выдумать значение (`workerRole` из `task_type`) — отвергнуто; опустить обязательное поле — нарушает OAS. |
| Решение | `Project.goal` = null (нет колонки, G-84). `WorkerRun.workerRole` = «UNKNOWN» (нет таблицы определений Worker, `worker_definition_version_id` без FK-цели, G-85). `resultRef` — только строковое `result_ref.id`, `problem` — только `type/title/status/code` с ограничением длины 200, остальное из JSON-ссылок не отдаётся (G-86). `listRequirements` показывает требования с текущей версией (в OAS `currentVersionId` обязателен). `Requirement.displayId` = `REQ-` + 6-значный номер. Статус требования/артефакта — статус текущей версии. |
| Обоснование | Явная пометка вместо выдуманных значений; ничего лишнего из JSONB не утекает. |
| Влияние на компоненты/контракты | api/read_api.py (мапперы). |
| Риски и компромиссы | Клиенты видят `UNKNOWN`/`null` до решения владельца/этапов S14+. |
| Затронутые тесты | test_read_api, test_read_api_schemathesis |

## ADR-78 — S09: конвейер команд записи и двухфазный createProject

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Шесть команд записи должны быть атомарными (проекция + событие + outbox + аудит + идемпотентность), а RLS идемпотентной записи привязана к проекту (`project_id IS NOT DISTINCT FROM app.project_id`), тогда как createProject создаёт сам проект: контекст нового проекта неизвестен до первого запроса, а `UnitOfWork.with_tenant` вызывается ровно один раз. |
| Связанные требования | API-MVP-003; PROC-MVP; SEC (идемпотентность, ACL, audit fail-closed) |
| Документы и разделы | Physical Model v1.2 §8 TX-01/TX-02; API Contracts v1.10 §3, §5; Implementation Spec §4 Inc.4; ADR-012, ADR-024 |
| Альтернативы | (а) Ослабить RLS идемпотентной таблицы (`project_id IS NULL OR …`) — отвергнуто (ослабляет S05); (б) детерминированный UUID проекта из ключа — самодельный генератор идентификаторов запрещён (ADR-027); (в) три транзакции с резервированием id проекта в записи идемпотентности (принято). |
| Решение | Общий конвейер `run()`: решение Policy (до взятия соединения; для проектных команд сначала `project.read` с утаиванием → 404, затем право записи → честный 403) → одна транзакция: контекст → `IdempotencyService.begin` → (REPLAY: перерисовать ресурс из БД, записать ничего; IN_PROGRESS: 409 `OPERATION_NOT_READY`; иной fingerprint: 409 `IDEMPOTENCY_KEY_REUSED`) → `record_allow` → запись домена + событие + outbox + аудит → `complete`. Ответ при replay строится из БД, а не из сохранённого тела (подписанный URL загрузки не хранится); тело ответа в запись идемпотентности не кладётся. createProject: Tx1 (контекст организации) — запись идемпотентности и резервирование id проекта (`reserve_resource`, статус остаётся IN_PROGRESS); Tx2 (контекст организации+проекта) — проект, членство, ProjectCreated, outbox, аудит; повтор после падения находит проект по зарезервированному id, а гонку арбитрирует первичный ключ; Tx3 — завершение записи. `createTask` в S09 не реализуется: ADR-012 (PREP review) и NCP-08 — перенос в S21; тесты createTask из раздела 9 промпта относятся к S21. Технические пределы длины текстов (20 000 символов, 50 evidence refs) — WORKING. |
| Обоснование | Сохраняет все инварианты S05/S07 без изменения RLS; повторы безопасны при падении между фазами. |
| Влияние на компоненты/контракты | api/write_api.py, modules/idempotency (reserve_resource), api/locator.py |
| Риски и компромиссы | createProject — три транзакции: между Tx2 и Tx3 запись остаётся IN_PROGRESS (повтор довершает её); политика истечения записей по-прежнему G-58. |
| Затронутые тесты | test_write_api: replay/параллельные повторы/другой body → 409, откат при сбое outbox, fail-closed без key ring и при сбое Policy Engine |

## ADR-79 — S09: события PROJECT/EPIC/REQUIREMENT, история и расширение outbox-триггера

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | AsyncAPI v1.6 содержит сообщения ProjectCreated, EpicCreated, RequirementVersionCreated (старое семейство `aires.<name>.v1`, без Operation). Таблицы истории и outbox-триггер S05/S06 поддерживали только OPERATION/WORKER_RUN (G-70). |
| Связанные требования | API-MVP; EVT (outbox); PERSIST |
| Документы и разделы | AsyncAPI v1.6 (канал `projectEvents`, схемы ProjectCreated/EpicCreated/RequirementVersionCreated); Physical Model v1.2 TX-01/TX-02; ADR-054 |
| Альтернативы | Выдумать события обновления проекта/создания загрузки — запрещено (нет контракта); не писать события — нарушает атомарность «проекция+событие+outbox». |
| Решение | Ревизия 0014 (expand): `project.projects.goal`, `last_event_sequence` у проектов и эпиков, таблицы `project.project_events`, `work.epic_events` (insert-only, RLS через родителя, контроль непрерывности на COMMIT), типы агрегатов PROJECT/EPIC; `audit.assert_outbox_matches_event` заменена: ветки PROJECT/EPIC/REQUIREMENT проверяют тип `aires.<event>.v1`, отсутствие `operationId`, source/subject/dataschema. Конверт семейства строится в `modules/events/envelope.py` (`DOMAIN_EVENT_TYPES`), идентификаторы лежат прямо в `data`, как требует схема. Назначение outbox — адрес канала AsyncAPI `aires.project.events`. События только там, где есть сообщение: ProjectCreated (createProject), EpicCreated (createEpic), RequirementVersionCreated (register и propose). updateProjectMetadata и createUploadIntent событий не создают — аудит. WORKING (OD-13): `source` (`urn:aires:projects|epics|requirements`) и форма `dataschema`. |
| Обоснование | Минимальное расширение существующей модели; ничего вне контракта. |
| Влияние на компоненты/контракты | migrations 0014, schema_snapshot.sql, modules/events/*, modules/projects, modules/epics, modules/requirements |
| Риски и компромиссы | Два семейства `type` (`com.aires.*` и `aires.*`) в одном AsyncAPI остаются нормативной неоднородностью; оба проверяются триггером; G-84 (Project.goal) закрыт. |
| Затронутые тесты | test_write_api (конверт против схем AsyncAPI), test_audit_platform_schema, schema drift, rls_coverage/grants audits |

## ADR-80 — S09: отображение createEpic / registerRequirementCandidate / proposeRequirementVersion на схему

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | OAS не задаёт начальный статус Epic, смысл `registrationKind`, источник ETag требования и обработку `evidenceRefs`. |
| Связанные требования | PROC-MVP (intake/registration); Requirements Lifecycle v2.7 §13, §14, §16 |
| Документы и разделы | Public API v1.3 (Epic, RegisterRequirementRequest, ProposeRequirementVersionRequest); ADR-056 |
| Альтернативы | Объявлять версию CONFIRMED/APPROVED по `registrationKind` — запрещено; разрешать `evidenceRefs` по несуществующим таблицам — нельзя; двойной шаг `row_version` на версию (CAS репозитория + CAS события). |
| Решение | Epic создаётся в статусе `PROPOSED` (WORKING: словарь не зафиксирован), `owner_user_id` не заполняется (не изобретаем бизнес-поле). Любая регистрация даёт версию `CANDIDATE` с автором USER; `registrationKind` фиксируется в аудите. `evidenceRefs` сохраняются как непроверенные ссылки `{type: EVIDENCE_REF, id, verified: false}` в `provenance_refs` (DOC-007 WORKING: существование не проверяется). Тип не указан → `UNKNOWN` с текстом `UNSPECIFIED`; неизвестный тип хранится как текст, не отображается на ближайший. Новая версия переносит тип предыдущей (смена типа — не часть команды). Предложение новой версии запрещено (409 `STATE_TRANSITION_NOT_ALLOWED`), если текущая версия `IN_BASELINE`, `REJECTED` или `SUPERSEDED` (WORKING, OD-18; изменение базовой версии — только через Change Request). Одна команда = один шаг `row_version` требования: версия, указатель и событие — один UPDATE. ETag требования возвращается заголовком ответов register/propose (аддитивно; OAS не называет источник ETag, G-91). |
| Обоснование | Минимальные предположения; ничего не утверждает. |
| Влияние на компоненты/контракты | modules/requirements (register, propose_version, current_type), modules/epics, api/write_api.py |
| Риски и компромиссы | Клиент получает ETag требования только из ответов register/propose (G-91); статус Epic — условный. |
| Затронутые тесты | test_write_api (register/propose/immutability/конкурентные предложения) |

## ADR-81 — S09: SigV4-пресайнер и конфигурация объектного хранилища

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | createUploadIntent требует короткоживущий URL, привязанный к объекту, типу и размеру. Нужен SigV4 для MinIO; у API нет сервисной учётки MinIO (G-37: root только у init). |
| Связанные требования | UX-SRC; SEC (6.4 upload) |
| Документы и разделы | Source & Context v1.3 §5.1, §13; Security Architecture v1.2; G-37 |
| Альтернативы | SDK (boto3/minio): новая тяжёлая зависимость; использовать root-учётку в API — запрещено; заглушка URL — запрещена. |
| Решение | Чистые функции `modules/sources/presign.py` (stdlib HMAC-SHA256), проверка по опубликованному вектору AWS и привязке заголовков. PUT подписывает `content-length`, `content-type`, `x-amz-checksum-sha256`: размер, тип и контрольную сумму принуждает хранилище. Конфигурация (`upload_public_endpoint`, `upload_bucket`, ключи — только файлы, `upload_max_size_bytes`) обязательна целиком: иначе 503 (fail-closed); значения по умолчанию для максимального размера НЕТ (WORKING, не изобретаем); `upload_url_ttl_seconds=300` и список MIME (PDF/DOCX/MD/TXT/XLSX/CSV) — WORKING. Сервисная учётка MinIO с ограничением по префиксу и публичный маршрут S3 в Compose — за S27 (G-37), см. G-92. |
| Обоснование | Без новых зависимостей и без расширения привилегий; проверяемость векторами. |
| Влияние на компоненты/контракты | modules/sources/presign.py, platform/config.py, api/write_api.py |
| Риски и компромиссы | Подпись проверена по вектору AWS, но не против живого MinIO (нет учётки/маршрута): приём загрузки хранилищем — IMPLEMENTATION NOT VERIFIED. |
| Затронутые тесты | tests/unit/test_presign.py, test_write_api (upload intent) |

## ADR-82 — S09: семантика createUploadIntent

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | OAS: `POST /uploads` принимает projectId, fileName, contentType, sizeBytes, sha256 и возвращает uploadUrl/expiresAt/requiredHeaders; Source и Upload связаны в схеме S06. |
| Связанные требования | UX-SRC; Source & Context v1.3 §5.1 |
| Документы и разделы | Public API v1.3 createUploadIntent; ADR-057 |
| Альтернативы | Хранить подписанный URL для replay — секретоподобное значение в БД; имя файла в ключе объекта — риск path traversal. |
| Решение | Каждый intent создаёт новый Source (FILE, заголовок = очищенное имя файла без путей и управляющих символов) и Upload PENDING; ключ объекта `<org>/<project>/<uploadId>` непрозрачен. Проверки: проект в контексте сессии, право `source.upload_create`, размер ≤ лимита, MIME из allowlist, sha256 — 64 hex. Replay с тем же ключом перерисовывает intent и подписывает URL заново на остаток TTL; для истёкшего или использованного intent — 409 `IDEMPOTENCY_KEY_REUSED` (новый intent — новый ключ). События и outbox не создаются (нет сообщения AsyncAPI), результат — аудит `UPLOAD_INTENT_CREATE`. completeUpload — S12. |
| Обоснование | Нет секретов в БД/аудите/событиях; ключ объекта не зависит от пользовательского ввода. |
| Влияние на компоненты/контракты | api/write_api.py, modules/sources/repository.py (get_intent, upload_id) |
| Риски и компромиссы | Загрузка новой версии существующего Source этим endpoint не выражается (нет sourceId в OAS). |
| Затронутые тесты | test_write_api (лимиты, ACL/IDOR, replay, истечение, fail-closed без конфигурации) |

## ADR-83 — S09: матрица политик записи (WORKING) и первый администратор проекта

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead (делегированные полномочия) |
| Проблема и контекст | Для записей нужны действия в Policy Engine; чтение (S08) доступно только членам проекта и org AUDITOR. Создатель проекта без членства не смог бы прочитать созданное. |
| Связанные требования | SEC (ACL), IAM v1.5 §4 (матрица — «стартовый словарь») |
| Документы и разделы | Identity & Access v1.5 §4–§5; OD-15; ADR-017, ADR-076 |
| Альтернативы | Не создавать членство (проект нечитаем создателем); дать org-админам глобальное чтение — отвергнуто решением S08. |
| Решение | Версия политики `2026-11-12.2` (WORKING, `humanOnly`): `project.create` — ORGANIZATION_OWNER/ADMIN; `project.update` — PROJECT_ADMIN; `epic.create`, `requirement.register`, `requirement.propose_version`, `source.upload_create` — PROJECT_ADMIN, ANALYST. Привилегированные роли требуют MFA (как раньше). Только USER-сессии браузера; сервисы/Manager/Worker получают отказ движка. Создатель проекта получает членство PROJECT_ADMIN в той же транзакции и аудите (`PROJECT_MEMBERSHIP_INITIAL_GRANT`) — единственная выдача роли в S09: человек над собственным проектом; решение владельца — OD-18. Approval-переходов в S09 нет. |
| Обоснование | Минимально необходимый набор, fail-closed; ничего не расширяет молча. |
| Влияние на компоненты/контракты | policy/policy_config.json + .sha256, api/write_api.py (проверка на старте), modules/projects |
| Риски и компромиссы | Матрица остаётся WORKING (OD-15); автоматическое членство создателя — предложение (OD-18). |
| Затронутые тесты | test_write_api (ACL по ролям, MFA, IDOR), test_policy_engine |

## ADR-084 — S10: OD-13 — фиксация форм `dataschema` и `source` CloudEvents

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Владелец проекта (выбор вариантов по OD-13, 2026-11-12) |
| Проблема и контекст | Event Model v1.4 §4 требует «стабильный URI схемы конкретной версии» для `dataschema` и приводит только пример `source` для Operation. Значения WORKING с S05 (ADR-054); S10 (dispatcher, SSE) публикует события наружу. |
| Связанные требования | DOC-008 AsyncAPI v1.6; Event Model v1.4 §4; ADR-054, ADR-079 |
| Документы и разделы | Event Model v1.4 §4; AsyncAPI v1.6 (`dataschema`, `source` — произвольные string) |
| Альтернативы | `dataschema`: https-URL схемы (нужен домен/хостинг схем, вне MVP); путь в `contracts/` (привязка wire-формата к раскладке репозитория). `source`: единый `urn:aires:operations` для Operation и WorkerRun; единый `urn:aires:backend`. |
| Решение | (1) `dataschema = urn:aires:schemas:<CloudEvents type>` (уникален на тип и major-версию). (2) `source` — один URN на вид агрегата: `urn:aires:operations`, `urn:aires:worker-runs`, `urn:aires:projects`, `urn:aires:epics`, `urn:aires:requirements`. (3) NCP-09…11: следовать AsyncAPI v1.6 (без `data.eventType`, без extension-атрибутов `correlationid`/`traceparent`, `worker_run.created` по общему шаблону); правки нормативных документов — NCP, остаются PROPOSED. Значения в `modules/events/envelope.py` не меняются; формы стали DECIDED (не WORKING). |
| Обоснование | Нулевая миграция иммутабельных строк outbox; соответствие Event Model §4; S10 не зависит от правок нормативных документов. |
| Влияние на компоненты/контракты | `modules/events/envelope.py` (комментарий WORKING снят), dispatcher/SSE S10 используют значения без трансформации. |
| Риски и компромиссы | Смена формы после появления production-данных потребует нового major типа события. NCP-09…11 остаются открытыми до правки нормативных документов. |
| Затронутые тесты | tests/contract/test_event_envelope.py (без изменений) |

## ADR-085 — S10: dispatcher, классификация ошибок доставки и WORKING-конфигурация

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Репозиторий S05 даёт claim/lease/fencing, но не процесс доставки: нужны цикл, классификация ошибок, backoff, карантин, controlled replay и метрики. |
| Связанные требования | REL-*, TX-*, API-MVP (events) |
| Документы и разделы | Event Model v1.4 §9.1, §15, §16; Persistence Blueprint PERSIST-015 |
| Альтернативы | Брокер (запрещён в MVP); публикация внутри транзакции claim (держала бы lock над сетевым вызовом); автоматический replay/удаление опубликованных строк (ADR-030). |
| Решение | (1) `Dispatcher.run_once`: claim отдельной транзакцией → проверка контракта → publish БЕЗ открытой транзакции → mark в новой короткой транзакции под fencing (owner, attempt). (2) Ошибки: `TransientDeliveryError` → PENDING с backoff (экспоненциальный, потолок, half-jitter), после `max_attempts` — карантин; `PermanentDeliveryError`/нарушение контракта → карантин сразу; неизвестное исключение publisher — transient `PUBLISH_FAILED`, логируется только класс (сообщение может нести payload). Неизвестный тип/major — карантин + счётчик `unknown_major_event`. (3) Событие в destination без consumer'ов — карантин `NO_CONSUMER`, не молчаливое «доставлено». (4) Controlled replay: `OutboxRepository.replay(event_ids)` только для QUARANTINED, только поимённо, бюджет попыток обнуляется, `replay_count + 1` (миграция 0015); CLI `ai_res.cli.outbox status|replay --confirm`. (5) Метрики — OpenTelemetry API (no-op без провайдера), атрибуты только машинные коды; алерты роста — чистые функции `alerts.py`, удаления нет (у ролей нет DELETE). (6) **WORKING (не утверждены):** batch 8, lease 60 с, publish timeout 5 с (ограничение batch × timeout ≤ 80 % lease), max_attempts 8, backoff 1–60 с, poll 1 с, интервал проверки роста 30 с, пороги алертов (backlog 1000, возраст 300 с, любая карантинная строка, 5 млн строк) — технические значения по умолчанию, меняются конфигурацией; OD-02. (6a) Fencing-токен = (owner, attempt, replay_count): replay обнуляет бюджет попыток, но меняет токен. Строка с истёкшим до очереди lease не публикуется. `observe()`/`run_forever` ведут gauge и счётчик `alert`; ошибка БД при `mark_*` считается и логируется классом, цикл завершается после `max_consecutive_errors` подряд. (7) Runtime-зависимости `jsonschema`, `referencing`, `rfc3339-validator`, `pyyaml` перенесены из dev (+ `types-*` в dev) — для проверки контракта в процессе. |
| Обоснование | Доставка не теряет событие и не блокирует поток из-за одного отравленного; всё неопределённое уходит в карантин с машинным кодом. |
| Влияние на компоненты/контракты | `modules/events/{dispatcher,delivery,alerts,metrics}.py`, `cli/outbox.py`, `outbox_repository.py`, миграция 0015, `pyproject.toml`/`uv.lock` |
| Риски и компромиссы | Compose-сервис dispatcher не добавлен (нет consumer'ов до S12; топология — решение владельца, G-98). Роль утверждения replay и аудит replay не определены (G-100). Метрики не проверены на реальном MeterProvider (S13). |
| Затронутые тесты | test_event_delivery (crash/duplicate/poison/concurrent/backoff/replay/lease lost/CLI), test_event_delivery_units |

## ADR-086 — S10: durable consumer — checkpoint, режимы порядка, контрактная валидация

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Event Model §9.2 требует Inbox + проверку sequence + checkpoint в одной транзакции с локальным эффектом; таблицы checkpoint нет (G-57). |
| Связанные требования | REL-*, TX-*; PERSIST-015/016 |
| Документы и разделы | Event Model v1.4 §9.2, §9.3, §15; AsyncAPI v1.6 |
| Альтернативы | Checkpoint как MAX(sequence) по inbox_messages (нет блокировки, не фиксирует фильтрованные потоки); advisory-lock без таблицы. |
| Решение | (1) Миграция 0015: `audit.inbox_checkpoints (consumer_name, aggregate_type, aggregate_id, last_sequence)`, RLS ENABLE+FORCE, политика только для `ai_res_consumer_group` + owner-политика, UPDATE только `last_sequence/updated_at`, триггеры: идентичность неизменяема, checkpoint строго растёт. (2) `InboxConsumer.deliver`: одна транзакция — advisory lock (consumer, aggregate) → Inbox marker (дубликат = успешный no-op; иной контент при том же id — аномалия) → sequence: CONTIGUOUS требует checkpoint+1 (gap → `SEQUENCE_GAP` transient, событие откладывается, не применяется и не пропускается), `<=` checkpoint с новым event id → `SEQUENCE_REGRESSION` permanent; MONOTONIC (фильтрованный поток, где пропуски законны) требует только рост → handler → PROCESSED → checkpoint → COMMIT. Падение до COMMIT не оставляет следа (PERSIST-016). (3) `EventContract` строится из AsyncAPI v1.6 (`type.const` каждого сообщения) и проверяет envelope целиком (additionalProperties:false), неизвестный major → `UNKNOWN_MAJOR_VERSION`, неизвестный тип → `UNKNOWN_EVENT_TYPE`, чувствительные ключи в `data` → `FORBIDDEN_CONTENT`; пустой контракт — ошибка старта. Dispatcher и consumer проверяют независимо (consumer не доверяет dispatcher'у). |
| Обоснование | Дубликаты и reorder не портят состояние; gap виден как алерт; checkpoint нельзя откатить даже ошибкой кода. |
| Влияние на компоненты/контракты | `consumer.py`, `contract.py`, `inbox_repository.py`, миграция 0015, `contracts/` (читается как файл) |
| Риски и компромиссы | Файл контракта должен быть доступен процессу (упаковка образа — G-99). Gap, вызванный потерянным (не карантинным) событием, откладывает бесконечно — только алерт. Inbox QUARANTINED финален (replay на стороне consumer'а не реализован, G-101). |
| Затронутые тесты | test_event_delivery (gap, regression, monotonic, PERSIST-016, checkpoint role/trigger, contract), test_event_delivery_units |

## ADR-087 — S11: пакет оркестрации без БД, компактные контракты, стратегия версионирования workflow

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Нужны Manager/Worker Runtime без DB credentials, детерминированный workflow и компактная история Temporal (Contracts v1.10 §7.2, §9.1, §9.5). |
| Связанные требования | INF-MVP-002; PROC-MVP (durable execution) |
| Документы и разделы | API Contracts v1.10 §7.2, §9; Spec Inc. 7, Add. v1.13 п.2, 14, 17 |
| Альтернативы | Один пакет с доменными модулями (нарушает изоляцию Runtime); Worker Versioning как основной механизм (требует PoC SDK/локального режима). |
| Решение | (1) Пакет `ai_res/orchestration` (контракты, workflow, activities, порт `OperationPlatform`, HTTP-клиент, воркеры) и `ai_res/runtime` (процессы manager/worker) запрещены к импорту sqlalchemy/psycopg/alembic/`ai_res.db`/`policy`/`api`/`cli`/`modules` контрактом import-linter (одно исключение: подпись service-токена). (2) Вход workflow — `OperationWorkflowInput{contract_version, OperationRef{operation,organization,project}, correlation}`: только канонические UUID и короткие коды, `assert_compact` на границе, повторная валидация внутри workflow; major вне `SUPPORTED_CONTRACT_MAJORS` — fail closed (non-retryable). (3) Workflow ID = `operation-{operationId}`, старт с `USE_EXISTING` + `REJECT_DUPLICATE`. (4) Версионирование: major контракта во входе; изменения последовательности команд — через `workflow.patched`; каждая выпущенная история хранится как replay-fixture (`tests/integration/temporal/histories/`). Worker Versioning — техническая гипотеза (G-105), не применяется; Worker build id в истории пока не записывается. (5) Retry Activity ограничен ВРЕМЕНЕМ (`ACTIVITY_BUDGET` 15 мин, WORKING), не числом попыток; ошибки платформы классифицируются: transient (сеть, 5xx, 408/425/429/409) — retry, permanent (прочее 4xx) — non-retryable. |
| Обоснование | Изоляция проверяется машинно, а не соглашением; история Temporal не может содержать документы/секреты; повторный старт не создаёт второй процесс; ack/fail идемпотентны, поэтому длительный bounded retry безопасен. |
| Влияние на компоненты/контракты | `orchestration/*`, `runtime/*`, `pyproject.toml` (контракт import-linter), `platform/config.py` (temporal_*, platform_api_*) |
| Риски и компромиссы | Порядок §9.5 (Worker Versioning основной) отложен: при долгоживущих workflow до PoC опираемся на patching — зафиксировано как G-105. Исчерпание бюджета оставляет Operation в ACCEPTED/RUNNING до reconciler (G-107). |
| Затронутые тесты | test_operation_workflow (реальный Temporal: старт, дубль, retry, permanent, scan истории, replay + fixture + негатив), test_orchestration_units, test_architecture (import-linter) |

## ADR-088 — S11: внутренний Platform API для Runtime (транспорт, аутентификация, capability)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Activities Manager без DB credentials должны менять Operation через Application Service (Contracts v1.10 §7.2: internal authenticated Platform API, HTTP/JSON допустим). |
| Связанные требования | INF-MVP-002; SEC-*; AUTH-012 |
| Документы и разделы | API Contracts v1.10 §7.2; Auth v1.1 §8; IAM v1.5 §3; Decision v1.6 §2.5 п.5–7 |
| Альтернативы | Тот же listener, что публичный API (общий порт, риск маршрутизации); gRPC/очередь (лишний компонент, расширение топологии); доступ Manager к БД (запрещён). |
| Решение | Отдельное ASGI-приложение `api/internal_api.py` на порту 8001 в сервисе `platform-api` (тот же образ, другой entrypoint `ai_res.api.serve_internal`), не за reverse proxy. Аутентификация — service-токен `ar1.…` (Ed25519, audience API, TTL 60 с ≤ max_ttl), без cookie/CSRF; ключ подписи Manager — отдельный Compose-секрет, реестр публичных ключей — `service_public_keys`. Авторизация — фиксированная таблица `CAPABILITIES` (WORKING): `operation.acknowledge_start`, `operation.record_failure` → только MANAGER_RUNTIME; без токена 401, без capability 403. Две узкие идемпотентные команды `POST /internal/v1/operations/{id}/start-acknowledgement` и `…/failure`. Tenant-scope в теле — ЗАЯВЛЕНИЕ: применяется как transaction-local context и проверяется по строке (RLS + сверка), несовпадение = тот же 404, что и для отсутствующей Operation. Каждая команда = transition (CAS) + OperationEvent + Outbox + audit в одной транзакции (`OperationOrchestrationService`). Контракт — `contracts/internal/AI_RES_Platform_Internal_API_v0.1.yaml` (WORKING overlay, NCP-14). |
| Обоснование | Минимальная поверхность и отдельная идентичность; Temporal-статус не копируется вслепую; повтор не создаёт второй переход. |
| Влияние на компоненты/контракты | `api/internal_api.py`, `serve_internal.py`, `modules/operations/orchestration_service.py`, `orchestration/http_platform.py`, `contracts/internal/`, Compose `platform-api`, `manager-runtime` |
| Риски и компромиссы | Capability привязана к идентичности, а не к конкретной Operation; нет jti-кэша, audience общий с публичным API, HTTP без TLS, DB-роль `ai_res_api` общая с публичным API, нет аудита отказов 401/403 (G-106, G-111). Это принятый WORKING-риск до решения security owner. |
| Затронутые тесты | test_internal_platform_api (реальный PostgreSQL: ack, fail, терминальность, подмена tenant, auth/capability, валидация, гонка, контракт↔маршруты), test_check_compose |

## ADR-089 — S11: маршрут запуска Operation в Temporal — destination, фильтр dispatcher'а, skeleton fail-closed

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | dispatcher S10 клеймит все destination, а consumer'ов нет; нужен идемпотентный старт workflow из Outbox, а исполняемого плана до S21/S23 нет. |
| Связанные требования | INF-MVP-002; PROC-MVP |
| Документы и разделы | Decision v1.6 §2.5 п.2–5, §5; Spec Add. v1.13 п.2, 8, 14; Process v1.9 §13 |
| Альтернативы | Dispatcher без фильтра (чужие события в карантин NO_CONSUMER); переводить QUEUED из dispatcher'а (у роли нет записи в доменные таблицы); оставлять Operation RUNNING/успешной в skeleton (ложь или вечная зависшая Operation). |
| Решение | (1) Destination `orchestration.operation-start`: accepted-событие Operation, которую надо оркестрировать, перечисляет его рядом с доменным. (2) `OutboxRepository.claim(..., destinations=)` и `DispatcherConfig.destinations` ограничивают claim и lease-карантин своими destination (по умолчанию None = все: S10 совместим). (3) `TemporalStartPublisher` берёт из события только идентификаторы, проверяет destination/тип/агрегат (иначе permanent), классифицирует RPC-статусы (UNAVAILABLE/DEADLINE_EXCEEDED/… transient, остальное permanent), ALREADY_FINISHED не молчит (warning + метрика `start_already_finished`). (4) QUEUED→RUNNING подтверждает первая Activity workflow через Platform API (dispatcher доменные таблицы не пишет): принятый Temporal'ом, но не подтверждённый старт остаётся ACCEPTED и виден reconciler'у. (5) Skeleton после подтверждения старта фиксирует терминальный FAILED `ORCHESTRATION_NOT_IMPLEMENTED` (SUCCEEDED ложен, зависшая RUNNING недопустима); WorkerRun не создаётся. |
| Обоснование | Не нарушает §2.4 (все переходы легальны, ничего не пропущено), не требует прав записи у dispatcher'а, не теряет события других destination. |
| Влияние на компоненты/контракты | `outbox_repository.py`, `dispatcher.py`, `modules/events/temporal_start.py`, `cli/dispatcher.py`, `orchestration/workflows.py` |
| Риски и компромиссы | Реального производителя START_DESTINATION пока нет (команды S09 не создают Operation; createTask — S21): dispatcher в стеке простаивает. До S21 нельзя направлять реальные типы Operation на этот маршрут (allowlist типов и reconciler — G-107). FAILED терминален и не переоткрывается; код ORCHESTRATION_NOT_IMPLEMENTED не внесён в реестр кодов ошибок (G-110). |
| Затронутые тесты | test_orchestration_e2e (PostgreSQL+Temporal: дубль доставки, чужой destination остаётся PENDING, WorkerRun=0, claim-фильтр), test_orchestration_units, runtime-тест стека |

## ADR-090 — S11: топология Compose для оркестрации — сеть `workflow`, секреты, изоляция Runtime

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Manager/Worker не должны иметь сетевого пути к PostgreSQL и DB-секретов (PERSIST-023), но обязаны достучаться до Temporal и Platform API. |
| Связанные требования | INF-MVP-002; SEC-* |
| Документы и разделы | Infrastructure v1.7 §3–4; Security v1.2; Secrets v1.1 |
| Альтернативы | Сеть `data` для Temporal+Runtime (нарушает PERSIST-023); Temporal на `app` вместе с proxy. |
| Решение | Сеть `workflow` (internal): temporal, manager-runtime, worker-runtime, outbox-dispatcher. `platform-api` [app, data]; `outbox-dispatcher` [data, workflow] с секретом `outbox_db_password`; `manager-runtime` [app, workflow] с единственным секретом `manager_signing_key`; `worker-runtime` [workflow] без секретов. `check_compose.py`: allowlists секретов/сетей и запрет `AI_RES_DB_*` у Manager/Worker. `secrets_dev.py`: `manager_signing_key` (seed Ed25519) и производный `service_public_keys` (через openssl, совпадение с cryptography проверено). Файл AsyncAPI монтируется Compose-`configs` (закрывает G-99 для dispatcher). Образ один (`ai-res/api:dev`), разные entrypoint; изоляция кода — import-linter, сети/секретов — Compose-проверки. |
| Обоснование | Изоляция проверена статически (check_compose) и в живом стеке (разрешение имени postgres, env, /run/secrets). |
| Влияние на компоненты/контракты | `infra/compose.yaml`, `infra/scripts/{check_compose,secrets_dev,wait_stack}.py`, infra-тесты |
| Риски и компромиссы | Образ Runtime содержит DB-код (не импортируется, но присутствует); healthcheck'и Runtime/dispatcher проверяют только достижимость Temporal (G-108); platform-api делит сеть `app` с reverse proxy (G-106); Temporal без аутентификации (G-104). |
| Затронутые тесты | infra static (check_compose, secrets), runtime: изоляция, секреты по сервисам, health, сквозной прогон |

## ADR-91 — S12: типизированные переходы Operation и отмена с reconciliation

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Переходы Operation проверялись только спецификацией в БД-ограничениях; отмена должна записывать запрос (202), а не результат, и не должна перезаписывать фактический исход. |
| Связанные требования | PROC-MVP; INF-MVP-002 |
| Документы и разделы | Operation State Machine v1.2; Decision v1.6 §2.4–2.5; API Contracts v1.10 §7 |
| Альтернативы | Сразу CANCELLED по запросу (ложь при активных WorkerRun); подтверждать отмену самим Temporal-статусом (статус Temporal не источник истины); отдельная таблица запросов отмены. |
| Решение | (1) `modules/operations/state_machine.py` — таблица переходов, равная baselined JSON (тест), применяется в `OperationRepository.transition`. (2) `POST /operations/{id}/cancel` → 202: ACCEPTED сразу CANCELLED (ничего не запущено, команды оркестратору нет); активная Operation → CANCEL_REQUESTED + Outbox-команда `orchestration.operation-cancel`; терминальная → 409; повтор — no-op. (3) Dispatcher сигналит workflow (`request_cancel`), workflow просит домен выполнить идемпотентную reconciliation `confirm_cancellation`: CANCELLED только если нет активных WorkerRun; уже терминальный статус побеждает; сигнал без опоры в домене ничего не меняет (домен — авторитет, сигнал — подсказка). (4) 409 `STATE_TRANSITION_NOT_ALLOWED` классифицируется как PERMANENT по problem code. |
| Обоснование | Запрос и результат — разные факты; реальный исход не перетирается; закрывает S11 L7 (CANCEL_REQUESTED без исполнителя). |
| Влияние на компоненты/контракты | `state_machine.py`, `cancellation.py`, `orchestration_service.py`, `orchestration/*`, `temporal_start.py`, `cli/dispatcher.py`, `internal_api.py`, `write_api.py`; внутренний контракт v0.1 (путь cancellation-confirmation) |
| Риски и компромиссы | Если workflow закрыт или отсутствует, Operation остаётся CANCEL_REQUESTED до будущего reconciler (G-107). Роли `operation.cancel` (PROJECT_ADMIN/ANALYST, humanOnly) — WORKING (G-113). |
| Затронутые тесты | test_operation_state_machine (hypothesis), test_operation_cancellation, test_write_api (cancel), temporal/test_operation_workflow |

## ADR-92 — S12: SSE проекта из event history — курсор, ACL на каждом опросе, retention gap

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | ADR-033 требует SSE из event history с Last-Event-ID, gap-сигналом и закрытием при потере прав; Outbox — не источник для клиента. |
| Связанные требования | API-MVP; SEC-* |
| Документы и разделы | ADR-033; API Contracts v1.10 §7; Security v1.2 |
| Альтернативы | Читать Outbox (смешивает транспортное и клиентское, нет ACL-проекции); отдавать `data` событий (обход ACL ресурсных эндпоинтов); LISTEN/NOTIFY (не гарантирует replay). |
| Решение | `GET /projects/{id}/events` (policy `project.events_read`; недоступный/отсутствующий проект — 404). Источники — пять append-only таблиц истории (замороженный allowlist). Событие — ACL-нейтральная проекция (идентификатор, тип, порядок, смена статуса), без `data`. `id` — непрозрачный HMAC-курсор `{watermark, {aggregate: sequence}}`, привязанный к сессии, проекту и endpoint; подделка, чужая сессия, чужой проект → 422, не молчаливый рестарт. На каждом опросе заново проверяются сессия и право чтения; сбой → `event: close` (`access_revoked`/`unavailable`, fail closed). Курсор старше retention → `event: gap` (resync из REST). Поток ограничен по времени, клиент переподключается. WORKING (настройки): poll, settle, max duration, retention. |
| Обоснование | Per-aggregate порядок точный (sequence); водяной знак находит только новые агрегаты; settle-окно защищает от поздних коммитов. |
| Влияние на компоненты/контракты | `modules/events/stream.py`, `api/events_api.py`, `platform/config.py` (sse_*), `app.py` |
| Риски и компромиссы | Settle-окно — техническая гипотеза (поздний коммит дольше окна будет пропущен для НОВОГО агрегата, G-114); опрос БД вместо push; курсор ограничен MAX_TRACKED агрегатами (иначе gap); сессия в потоке не продлевается до истечения idle — поток живёт ≤ sse_max_seconds. |
| Затронутые тесты | test_read_api (SSE: проекция, ACL 404/401, подделанный/чужой курсор, resume без повторов, отзыв сессии, retention gap) |

## ADR-93 — S12: completeUpload — проверка объекта хранилищем, Operation SOURCE_INGESTION, роли политики

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Завершение загрузки не должно доверять заявленному клиентом: проверять нужно то, что реально лежит в хранилище, затем создавать Operation (конвейер — S27). |
| Связанные требования | SRC-MVP; SEC-* |
| Документы и разделы | Source and Context Lifecycle v1.3; API Contracts v1.10; Security v1.2 |
| Альтернативы | Принимать sha256 клиента как доказательство; скачивать объект целиком для хеша (дорого, SSRF-поверхность); считать объект без проверенного хранилищем SHA-256 принятым. |
| Решение | `POST /uploads/{id}/complete` (Idempotency-Key, policy `source.upload_complete`). Порт `ObjectStore.stat` (presigned HEAD, `x-amz-checksum-mode`) возвращает размер и SHA-256, вычисленный и проверенный хранилищем при PUT. Несовпадение размера/суммы или отсутствие проверенной суммы → REJECTED (вердикт фиксируется отдельной транзакцией и переживает отказ), истёкший → EXPIRED без обращения к хранилищу, нет объекта → 409 OPERATION_NOT_READY, недоступное хранилище → 503 без изменений. Успех: UPLOADED→VERIFIED, SourceVersion, Operation SOURCE_INGESTION (ACCEPTED, 202, Location). Команда старта оркестратору НЕ ставится (G-107). Роли `source.upload_complete` и `operation.cancel` — PROJECT_ADMIN/ANALYST, humanOnly (WORKING). |
| Обоснование | Доказательство целостности — у хранилища; сетевой вызов вне транзакции; отказ необратим и аудируем. |
| Влияние на компоненты/контракты | `modules/sources/object_store.py`, `sources/repository.py`, `write_api.py`, `policy_config.json` (+sha256), `app.py` |
| Риски и компромиссы | Объект, загруженный без `x-amz-checksum-sha256`, отклоняется (presign требует заголовок); completion policy SOURCE_INGESTION — заглушка `wip-1` до S21/S27; TOCTOU между HEAD и finalize (объект неизменяем по ключу, G-115). |
| Затронутые тесты | test_write_api (completeUpload: успех, несовпадения, истечение, недоступность, идемпотентность, ACL/IDOR) |

## ADR-094 — S12 review follow-up: FAILED побеждает отложенную отмену; истёкший курсор SSE — gap; reconciler до S23

| Поле | Значение |
|---|---|
| Статус | ACCEPTED (решение владельца по рекомендациям `architect`, 2026-11-12) |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Второй раунд review (architect, code-reviewer, fastapi, pr-test-analyzer, type-design) выявил три развилки: реальная ошибка во время ожидающей отмены терялась; истёкший курсор SSE давал 400 вместо gap (ADR-033); Operation в CANCEL_REQUESTED без живого workflow никто не разрешал. |
| Связанные требования | PROC-MVP; API-MVP |
| Документы и разделы | Operation State Machine v1.2 (CANCEL_REQUESTED → FAILED допустим); ADR-033; ADR-091, ADR-092 |
| Альтернативы | Всегда CANCELLED при ожидающей отмене (теряется исход); 400 на истёкший курсор (EventSource не переподключается); удерживать отмену внутри workflow (дублирует reconciler G-107). |
| Решение | (1) `record_failure` из CANCEL_REQUESTED переводит Operation в FAILED с problem_ref; поздняя reconciliation уже не меняет терминальный статус. (2) Срок токена курсора SSE не проверяется; актуальность определяется retention по водяному знаку и даёт `event: gap`. Курсор никогда не выдаётся клиенту, если сам endpoint его отвергнет (>24 агрегатов → `gap` + `close resync` до отправки события). Разбор курсора строгий: запись не отбрасывается молча. (3) Reconciler для CANCEL_REQUESTED без workflow (G-117) вместе с G-107 должен быть выполнен до S23; в S12 не реализуется. |
| Обоснование | Реальный исход не должен теряться; клиент EventSource обязан восстанавливаться без перезагрузки; дублирование сверки в workflow и в reconciler избыточно. |
| Влияние на компоненты/контракты | `orchestration_service.record_failure`, `api/events_api.py`, `modules/events/stream.py`, `modules/sources/completion.py` (новый сервис completeUpload), `modules/sources/object_store.py` (клиент на вызов, составной checksum = непроверяемый объект) |
| Риски и компромиссы | До reconciler зависшая отмена возможна (G-117); `FAILED` при отмене пользователя может удивить — отражено в событии (`from_status=CANCEL_REQUESTED`). |
| Затронутые тесты | test_operation_cancellation, test_read_api (SSE), test_write_api (completeUpload), unit/test_s12_review_units |

## ADR-095 — S13: стек наблюдаемости — единый путь OTLP → Collector (allowlist-redaction) → Prometheus/Loki/Tempo/Grafana

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Скелет Collector (S03) только печатал счётчики; нужно развернуть MVP-стек DOC-024 §4 так, чтобы redaction выполнялась до backend'ов, высококардинальные ID не попадали в labels, а потеря telemetry не влияла на домен. |
| Связанные требования | OBS-MON-001/002/003/010/012/013, OBS-SEC-001..003/005/009, DOC-024 §3–§4, §7–§9; ADR-025 |
| Документы и разделы | Observability Architecture v1.2 §3, §4, §7, §8; Monitoring & Alerting Requirements v1.0; Infrastructure v1.7 §10.1–§10.6 |
| Альтернативы | Collector core-образ (нет `redaction`/`transform`); redaction только в backend'ах; blocklist вместо allowlist; ELK/SigNoz (запрещено DOC-015 §10.8 без потребности); Grafana Alerting вместе с Alertmanager (два пути); публикация Grafana на хост. |
| Решение | `otel/opentelemetry-collector-contrib:0.116.1` (закреплён digest; тот же релиз, что и скелет). Конвейеры: traces `memory_limiter → redaction/traces (allow_all_keys=false + allowed_keys + blocked_values) → transform/traces (exception.message/stacktrace и status.message удаляются, остаётся тип) → batch → Tempo`; logs `memory_limiter → transform/logs (keep_keys + маскирование body и атрибутов) → batch → Loki (OTLP)`; metrics `memory_limiter → filter/metrics (только именованные семейства) → transform/metrics (allowlist меток) → batch → prometheus exporter :8889`, Prometheus скрейпит (также Temporal :9090, MinIO, сами компоненты). Новая internal-сеть `observability`; Prometheus/Loki/Tempo/Alertmanager — только в ней, Grafana — `observability` + `admin` (порта на хосте нет, анонимный доступ и регистрация выключены, пароль — Compose secret `grafana_admin_password` через `__FILE`). Одна точка маршрутизации алертов — Alertmanager. Retention не задаётся: действуют умолчания компонентов (не решение AI RES), удаления данных AI RES нет. `infra/config/otel` перенесён в `infra/observability/otel`. |
| Обоснование | Allowlist безопаснее blocklist (новое поле по умолчанию не уезжает); redaction в Collector — вторая линия после санитайзера процесса; contrib-образ — единственный вариант с нужными процессорами в тот же релиз. |
| Влияние на компоненты/контракты | `infra/compose.yaml` (+5 сервиса, сеть, тома, секрет), `check_compose.py` (политика сети/секретов), `secrets_dev.py`, `wait_stack.py`, `infra/observability/**`. |
| Риски и компромиссы | OTLP-приёмник без аутентификации доступен в сетях `app`/`workflow` (G-123); внутри `observability` нет TLS; обновление версии redaction-процессора (в 0.116.1 нет `blocked_key_patterns`) требует пересмотра allowlist; умолчания retention — не решение (OD-02). |
| Затронутые тесты | test_observability_static, runtime/test_observability (redaction до Loki/Tempo, labels, изоляция, деградация) |

## ADR-096 — S13: алерты как код — пороги без значений, `for` как WORKING, без получателей

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | DOC-025 требует алерты с полным набором метаданных, но числовые SLO/пороги, получатели и дежурные — открытые параметры (OD-02); Spec Add. v1.20 п.8 запрещает их изобретать. |
| Связанные требования | OBS-MON-011, OBS-ALR-001..007; OD-02 |
| Документы и разделы | Monitoring & Alerting Requirements v1.0 §5–§7; Observability Architecture v1.2 §9, §13 |
| Альтернативы | Задать «разумные» числа (изобретение WORKING-значений); не писать числовые алерты вовсе (нет проверяемого механизма включения); Grafana-managed alerts. |
| Решение | Правила Prometheus в `infra/observability/prometheus/rules/alerts.yml`, у каждого: severity, scope, owner, `for`, runbook, user_impact, auto_action=`none`, silence_policy; описание начинается с «Fact:» (факт отделён от гипотезы). Числовые пороги — серии `ai_res:threshold:<name>` в `thresholds.yml`, где **нет ни одного значения**: сравнение с отсутствующей серией не даёт результата, алерт инертен, пока владелец не запишет значение (promtool-тесты показывают оба состояния; значения в тестах — фикстуры). Структурные алерты (TargetDown, quarantine, unknown major, потеря экспорта) порогов не требуют. `for` — WORKING-защита от flapping, не SLO. `owner` — роль-заглушка (`platform-operations`, WORKING). Alertmanager без получателей (`unrouted`); inhibit TargetDown→warning. |
| Обоснование | Механизм включения порога виден и проверен, но решение о значении остаётся у владельца; алерт не может выполнить действие (OBS-ALR-004). |
| Влияние на компоненты/контракты | `alerts.yml`, `thresholds.yml`, `alertmanager.yml`, `prometheus/tests/alerts_test.yml`, runbook `docs/runbooks/observability.md`. |
| Риски и компромиссы | До решения владельца числовые алерты не срабатывают, а страниц/уведомлений нет вообще — виден только Alertmanager/дашборд (OD-02, OBS-ALR-006). |
| Затронутые тесты | test_observability_static (метаданные, runbook-якоря, promtool test + саботаж, пороги пусты), runtime (правила загружены и здоровы) |

## ADR-097 — S13: экспорт telemetry из процессов — fail-open, ограниченные очереди, измеряемая потеря, санитизация логов

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Процессы (API, Platform API, dispatcher, Manager/Worker Runtime) должны отдавать traces/metrics/logs, не рискуя доступностью и не утекая секретами; потеря должна быть видимой. |
| Связанные требования | OBS-MON-014/015/003, OBS-SEC-001..004; G-22 |
| Документы и разделы | Observability Architecture v1.2 §2.5, §7; Infrastructure v1.7 §10.11 |
| Альтернативы | Синхронный `SimpleSpanProcessor` (блокирует запрос); экспорт логов без санитайзера; docker-логи через docker.sock (запрещено); глобальная auto-instrumentation. |
| Решение | `platform/export.py::install_telemetry`: `BatchSpanProcessor`/`PeriodicExportingMetricReader`/`BatchLogRecordProcessor` с ограниченной очередью (`otlp_queue_size`) и коротким таймаутом (`otlp_export_timeout_seconds`), OTLP/HTTP; без `otlp_endpoint` экспорта нет (no-op). Экспортёры-наследники считают неудачные батчи в `ai_res.telemetry.export_failures` и раз в минуту пишут одну строку в stderr; шум SDK-логгера ограничен. `_SanitizingLogHandler` экспортирует копию записи (message/extra через `redact`, исключение — только тип), оригинал для stdout не меняется; логгер `ai_res.telemetry` не экспортируется (нет петли). `TelemetryMiddleware` пишет `http.server.request.duration` (метки: method из белого списка, route-шаблон, класс статуса). Числа (очередь 2048, таймаут 5 с, период метрик 15 с) — WORKING, конфигурация. Audit не использует этот модуль (контракт import-linter + интеграционный тест). |
| Обоснование | Ограниченные фоновые очереди дают «потеряли, а не зависли»; санитизация до экспорта — вторая линия перед Collector. |
| Влияние на компоненты/контракты | `platform/export.py`, `platform/telemetry.py`, `platform/config.py`, `api/app.py`, `api/serve_internal.py`, `cli/dispatcher.py`, `runtime/lifecycle.py`, `pyproject.toml` (+opentelemetry-exporter-otlp-proto-http), контракт import-linter. |
| Риски и компромиссы | Переполнение очереди batch-процессора не считается приложением (G-124); `LoggingHandler` SDK помечен deprecated (G-124); первая неудача экспорта видна только после периода метрик. |
| Затронутые тесты | unit/test_telemetry_export (мёртвый Collector, санитизация, метрики), integration audit-независимость, runtime (остановка всех backend'ов) |

## ADR-098 — S13: трассировка и метрики Temporal; контекст через Platform API, но не через Outbox

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | G-108: нет OTel-интерсептора Temporal, trace linkage workflow и метрик очередей. |
| Связанные требования | OBS-MON-002/004/007; G-108 |
| Документы и разделы | Agent Observability v1.2 §4; Observability Architecture v1.2 §6 |
| Альтернативы | Свой интерсептор; Prometheus-эндпоинт в каждом Runtime (Prometheus в сети `workflow`); propagation через событие Outbox (меняет контракт событий — NCP). |
| Решение | `connect()` подключает `temporalio.contrib.opentelemetry.TracingInterceptor` (spans StartWorkflow/RunWorkflow/RunActivity, контекст — заголовок `_tracer-data` с `traceparent`, без payload) и `Runtime` с OpenTelemetry-метриками ядра SDK по OTLP/gRPC (`temporal_*`, секунды). `HttpOperationPlatform` передаёт `traceparent` (без baggage), Platform API продолжает trace. Серверные метрики Temporal — scrape `:9090` по сети `observability`. |
| Обоснование | Один trace от запуска workflow через Activity до Platform API при нулевом изменении payload'ов; реплей совместим (тест). |
| Влияние на компоненты/контракты | `orchestration/client.py`, `orchestration/http_platform.py`, `api/internal_api.py`, Compose (Temporal: `PROMETHEUS_ENDPOINT`, сеть `observability`). |
| Риски и компромиссы | Контекст запроса API не доходит до dispatcher/workflow (Outbox не несёт `traceparent`): два trace вместо одного (G-126). Имена метрик SDK (schedule-to-start) не проверены реальным workflow в Compose (G-129). |
| Затронутые тесты | integration/temporal (спаны в одном trace, заголовок содержит только trace-контекст, replay с интерсептором и без), runtime (метрики `temporal_*` в Prometheus) |

## ADR-099 — S13: PostgreSQL — application-side метрики пула; серверные метрики ждут monitoring-роли (NCP-15)

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-12 |
| Ответственный | Implementation Lead |
| Проблема и контекст | Дашборд PostgreSQL требует серверных метрик (блокировки, соединения), но baselined набор ролей (DOC-069/Identity v1.5) не содержит monitoring-роли, а postgres-exporter требует учётных данных БД. |
| Связанные требования | OBS-MON-001; database-and-migrations.md (роли BASELINED) |
| Документы и разделы | Identity & Access v1.5; PostgreSQL Migration and Access Strategy v1.1; Infrastructure v1.7 §10.4 |
| Альтернативы | Дать exporter'у `ai_res_auditor`/`ai_res_api` (расширение прав вне baseline); завести `ai_res_monitor` без решения (изменение BASELINED); не делать дашборд. |
| Решение | Дашборд «PostgreSQL (application view)» строится на метриках пула SQLAlchemy (`db.client.connection.count/max`, `ai_res.db.errors` по классу исключения) и на метриках Temporal persistence (`persistence_sql_*`). Серверные метрики PostgreSQL не собираются; предложение — NCP-15 (роль `ai_res_monitor` с `pg_monitor`, отдельный exporter, отдельный секрет, сеть `data`+`observability`). Новая роль не создаётся. |
| Обоснование | Не нарушает baseline ролей и не требует DB credentials у observability-стека. |
| Влияние на компоненты/контракты | `db/metrics.py`, `db/engine.py`, дашборд `postgresql`, алерты DatabasePoolSaturated/DatabaseErrors, `NORMATIVE_CHANGE_PROPOSALS.md`. |
| Риски и компромиссы | Нет видимости блокировок/репликации/места на диске PostgreSQL до решения NCP-15 (G-125). |
| Затронутые тесты | test_observability_static (дашборд), runtime (валидность запросов), unit (пул) |

## ADR-100 — S13: решения владельца по OD-02 — стартовые пороги алертов, retention 30/7/30 дней, получатели и owner

| Поле | Значение |
|---|---|
| Статус | ACCEPTED |
| Дата | 2026-11-13 |
| Ответственный | Владелец проекта (решение дано в сессии 2026-11-13); реализация — Implementation Lead |
| Проблема и контекст | После S13 числовые пороги алертов, сроки хранения telemetry и получатели были открыты (OD-02, OBS-SEC-007, OBS-ALR-006): алерты по порогам инертны, retention — умолчания компонентов, owner алертов — заглушка |
| Связанные требования | OBS-MON-011, OBS-SEC-007, OBS-ALR-001/006; OD-02 |
| Документы и разделы | Monitoring & Alerting Requirements v1.0 §5–§7; Observability Architecture v1.2 §8, §9 |
| Альтернативы | Оставить пороги пустыми до S33 (алерты инертны); задать значения владельцем вручную; email-получатель (внешний сервис, SMTP-секрет); умолчания компонентов для retention |
| Решение | 1) Пороги — **стартовые значения, статус WORKING**, не SLO, записаны в `thresholds.yml`: доля 5xx 0.05; p95 запроса 1 с; schedule-to-start p95 5 с; свободное место MinIO < 0.15; возраст старейшей недоставленной строки outbox 300 с; заполнение очереди Collector 0.9. Пересмотр по измерениям на S33. 2) Retention: метрики 30 дней, трейсы 7 дней, логи 30 дней; явная конфигурация (Prometheus `--storage.tsdb.retention.time=30d`, Tempo `block_retention: 168h`, Loki `retention_period: 720h` + compactor). Относится только к telemetry; Audit Log (PostgreSQL) не затрагивается. 3) Получатели: только Alertmanager и дашборд, внешних получателей нет (PagerDuty вне MVP); `owner` алертов — `project-owner` (роль владельца проекта) вместо заглушки `platform-operations` |
| Обоснование | Включить механизм оповещения сейчас лучше, чем держать его выключенным без измерений; значения консервативны и помечены как подлежащие калибровке; retention соответствует OBS-SEC-007 (явные сроки по классам); внешние сервисы и их секреты не добавляются |
| Влияние на компоненты/контракты | `thresholds.yml`, `compose.yaml` (Prometheus), `loki/tempo` конфиги, `alerts.yml`/тесты (owner), runbook; публичные контракты и `docs/architecture/` не менялись |
| Риски и компромиссы | Стартовые числа могут давать ложные срабатывания или пропуски до калибровки; без получателей алерт виден только в Alertmanager/дашборде (OBS-ALR-006 для production-like запуска остаётся: нужна эскалация человеку); диск Loki/Tempo/Prometheus по-прежнему без алерта (G-127) |
| Затронутые тесты | test_observability_static (пороги записаны и WORKING, retention, owner), promtool `thresholds_test.yml`, runtime-набор |
