# S05 — Core tenant и execution schema + RLS

**Фаза:** B. Persistence & Identity · **Соответствие Spec:** Blueprint §5 PDB-0002…0007, 0009, 0010 (greenfield ADR-011); Spec Add. v1.17 · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

> **СТАТУС ПРОМПТА: PENDING_DEPS.** Исполнять только после перевода всех зависимостей в DONE.

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Таблицы iam/organization/project/work/operations/agents/execution/audit/platform с ограничениями целостности, sequences, outbox/inbox/idempotency, RLS ENABLE+FORCE и полным PERSIST acceptance suite.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` — §5, §11, §13, §14, §15, §16, §17; Дополнения v1.3–v1.9
- `docs/architecture/AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md` — §3–§9, §11, §12
- `docs/architecture/AI_RES_PostgreSQL_Physical_Model_v1.0.sql` — весь файл (design snapshot, WORKING)
- `docs/architecture/AI_RES_Persistence_Implementation_Blueprint_v1.0.md` — §5, §7, §9, §12, §14
- `docs/architecture/AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` — §2, §3, §5; Дополнения v1.2–v1.6
- `docs/architecture/AI_RES_Operation_WorkerRun_Event_Model_v1.4.md` — §8, §9, §10
- `docs/architecture/AI_RES_PostgreSQL_Roles_RLS_v1.0.sql` — весь файл
- `docs/architecture/AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json` — статусы Operation/WorkerRun/Gate
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S04 (Persistence foundation: Alembic, schemas, роли)
- **Решения владельца:**
- Нет блокирующих решений владельца.

Порядок старта:
1. Прочитай `CLAUDE.md`, все `.claude/rules/*.md` (включая `ecc-precedence.md`), `docs/implementation/IMPLEMENTATION_CHARTER.md` и `docs/implementation/CONTEXT_HANDOFF.md`; инструменты контекста — `docs/implementation/tooling/README.md` (Context7 через `docs-lookup`, Serena для навигации по коду).
2. Открой `docs/architecture/AI_RES_Document_Registry_v4.1.md` §2: убедись, что каждый документ из раздела «Нормативные источники» существует и является canonical (версия и статус). Отсутствие или противоречие → discrepancy report в отчёте этапа и остановка затронутой части.
3. Открой `docs/implementation/IMPLEMENTATION_STATUS.md`: все зависимости этапа должны быть в статусе DONE (ADR-032). Иначе — остановись и сообщи.
4. Проверь `docs/implementation/DECISIONS_PENDING.md`: блокирующие решения владельца для этапа должны быть закрыты.
5. Проверь фактическое состояние репозитория (`git status`, существующий код этапа) — не дублируй уже реализованное.
6. Переведи этап в `IN_PROGRESS` в `IMPLEMENTATION_STATUS.md`.

## 5. Scope (входит)

- iam: users, credentials (Argon2id hash поля), sessions, mfa, service_identities; organization: organizations, memberships; project: projects, project_memberships.
- work: epics, tasks (`operation_id NOT NULL`, `UNIQUE(operation_id,id)`, ADR-011/012), task_dependencies (ADR-016).
- operations: operation_types (ADR-013), operations, operation_events (append-only, `UNIQUE(aggregate_id,sequence)`).
- agents: worker_runs (composite FK на work.tasks, `started_with_readiness_evaluation_id` immutable), worker_run_events, worker_results (immutable, ADR-016).
- execution: readiness_evaluations, readiness_check_results (composite FK, immutable).
- audit: outbox_events, inbox_messages, audit_events (ADR-016); platform: idempotency_records (HMAC digest + key_id, ADR-024).
- Sequence allocation под row lock/CAS (запрет MAX()+1); `row_version` optimistic concurrency.
- RLS ENABLE+FORCE на tenant tables, default deny без контекста; grants по ADR-015.
- Immutability triggers/constraints для immutable записей.
- Repositories для этих агрегатов (без HTTP).
- Гранты ADR-034: INSERT-only для api на outbox/audit; REVOKE UPDATE/DELETE на immutable; политики outbox/consumer; migration-политики; `derived_from_task_id`.
- Reference-таблица aggregate_type; drift operation_type registry↔таблица.

**Не входит:**
- requirements/sources/artifacts/context/decisions/traceability (S06).
- HTTP endpoints.

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-011 — Greenfield-профиль persistence
- ADR-012 — Владеющая Operation для Task, созданной `createTask`
- ADR-013 — Реестр `operation_type`
- ADR-014 — Имена PostgreSQL schemas
- ADR-015 — Набор PostgreSQL ролей по нормативным документам
- ADR-016 — Проектирование отсутствующих физических таблиц
- ADR-023 — `gateResultId` ↔ ReadinessEvaluation
- ADR-024 — Idempotency HMAC keys с key-id
- ADR-030 — Retention: без автоматического удаления
- ADR-034 — Rework после terminal Operation и RLS/grants для event-таблиц
- ADR-035 — Контуры тестирования и evidence для P0-этапов
- ADR-037 — Независимая проверка P0-этапов (замена per-stage human sign-off)

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Физические детали таблиц, не заданные DDL v1.0 (ADR этапа на каждое отклонение).

## 7. Результаты реализации

- Alembic revisions
- repositories
- PERSIST suite
- S05 report

## 8. ECC: обязательные agents, skills, commands

| Тип | Имя (установлено в `.claude/`) | Назначение на этапе |
|---|---|---|
| agent | `planner` | декомпозиция этапа на вертикальные срезы перед реализацией |
| agent | `architect` | архитектурное соответствие плана и результата нормативной архитектуре (read-only review) |
| agent | `code-reviewer` | независимое общее code review |
| agent | `silent-failure-hunter` | поиск проглоченных ошибок, небезопасных fallback и fail-open путей |
| agent | `python-reviewer` | review Python-кода |
| agent | `tdd-guide` | тесты до реализации (DoD — по testing-and-verification.md, не «80% coverage») |
| agent | `pr-test-analyzer` | оценка полноты поведенческих и негативных тестов |
| agent | `database-reviewer` | review миграций, ролей, RLS, запросов (с учётом ecc-precedence: RLS через transaction-local context, не Supabase) |
| agent | `security-reviewer` | независимое security review |
| agent | `type-design-analyzer` | проверка инвариантов в типах DTO/доменных моделей |
| skill | `python-patterns` | идиомы и типизация Python |
| skill | `python-testing` | pytest, fixtures, parametrization (без FastAPI-примеров как обоснования стека) |
| skill | `tdd-workflow` | red → green → refactor |
| skill | `postgres-patterns` | индексы, запросы (Supabase-RLS паттерны не применять) |
| skill | `database-migrations` | expand/contract, concurrent indexes (только Alembic) |
| skill | `verification-loop` | финальная верификация этапа |
| command | `/plan` | план этапа до кода |
| command | `/code-review` | локальный review изменений (без PR-режима) |
| command | `/quality-gate` | проверка quality gates |
| command | `/python-review` | review Python изменений |
| command | `/test-coverage` | отчёт покрытия как дополнительная метрика |
| command | `/security-review` | встроенная команда Claude Code: security review изменений ветки |

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- PERSIST-001..024 (Blueprint §12) — все Required.
- Tenant A/B isolation под реальными runtime ролями.
- Missing context default-deny; pooled context reset.
- Task без operation_id; WorkerRun с task из другой Operation → отклонение.
- Параллельная аллокация sequence без дублей/дыр (concurrency test).
- Попытка UPDATE/DELETE immutable worker_results/readiness_evaluations/event history → отклонение.
- Projection+event+outbox атомарность: сбой между шагами → ни одной записи.
- Upgrade from previous revision; RLS coverage check (все tenant tables покрыты).
- Под ролью `ai_res_api`: атомарность projection+event+outbox+audit; UPDATE immutable → denied; ai_res_api не может UPDATE/DELETE `audit.audit_events` (THR-015).
- Rework после terminal Operation (новая Operation + Task + WorkerRun).
- Drift registry operation_type ↔ таблица.
- Backfill под migrator при FORCE RLS.

Типы тестов и инструменты — `docs/implementation/TEST_STRATEGY.md`.

## 10. Quality gates

- `docs/implementation/QUALITY_GATES.md`: G1 Static, G2 Unit, G3 Integration (PostgreSQL/Temporal реальные), G4 Contract, G5 Security/Authorization, G6 Migration, G7 Independent review, G8 Documentation & traceability, G9 Evidence & report — все применимые.
- Этап-специфичные: все тесты раздела 9 зелёные; результаты воспроизводимы командой из отчёта.

## 11. Документирование решений

Каждое нетривиальное самостоятельное техническое/архитектурное решение регистрируется как ADR (`ACCEPTED`, ответственный — Implementation Lead) с полным набором полей. Противоречия не скрываются: discrepancy report в отчёте этапа. Изменения нормативных документов — только как NCP.

## 12. Обновление документов и статусов

- `docs/implementation/CONTEXT_HANDOFF.md` — обновить в конце этапа (где мы, следующий шаг, новые решения).
- `docs/implementation/IMPLEMENTATION_STATUS.md` — статус этапа (NOT_STARTED → IN_PROGRESS → IMPLEMENTED → TESTED → VERIFIED; BLOCKED/DEFERRED с причиной). IMPLEMENTED ≠ TESTED ≠ VERIFIED.
- `docs/implementation/ARCHITECTURE_DECISION_LOG.md` — все самостоятельно принятые нетривиальные решения (ID, дата, проблема/контекст, связанные требования, документы/разделы, альтернативы, решение, обоснование, влияние на компоненты и контракты, риски, затронутые тесты, статус, ответственный). Подробные решения — `docs/implementation/decisions/ADR-xxx-*.md`.
- `docs/implementation/REQUIREMENTS_TRACEABILITY.md` и `CONTRACT_TRACEABILITY_MAP.md` — статусы покрытых требований и контрактов.
- `docs/implementation/KNOWN_GAPS.md` — новые/закрытые пробелы.
- `docs/implementation/DECISIONS_PENDING.md` — только вопросы, действительно требующие владельца/security owner.
- `docs/implementation/ECC_USAGE.md` — фактически использованные ECC agents/skills/commands, цель и результат; недоступные компетенции и компенсация.
- `docs/implementation/increments/S05_core_tenant_execution_schema_rls_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S05_*.md`.
- CONTRACT_TRACEABILITY_MAP.md (таблицы)
- KNOWN_GAPS.md (G-02, G-10)
- decisions/NORMATIVE_CHANGE_PROPOSALS.md (NCP-02 детали)

## 13. Definition of Done

- PERSIST-001..024 зелёные.
- RLS coverage = 100% tenant tables.
- Schema drift = 0 относительно snapshot.
- PERSIST по матрице ADR-035 для S05 (001–014, 017–020 на синтетической ревизии); остальные явно отложены.
- Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты.
- Все пункты «Результаты» созданы; функциональность не замаскирована заглушками (test double допускается только по ADR-022 и с явной маркировкой).
- Все обязательные тесты этапа написаны до/вместе с кодом, проверяют реальное поведение (не импорт и не наличие файлов) и проходят; точные команды и результаты — в отчёте.
- Применимые пункты `.claude/rules/testing-and-verification.md` и `docs/implementation/QUALITY_GATES.md` (G1–G9) выполнены; неприменимые — с обоснованием.
- Миграции (если есть): upgrade from empty и from previous revision; drift = 0.
- Security/authorization negative tests этапа выполнены; секреты отсутствуют в коде, логах, трейсах, событиях, Temporal history.
- Observability: новые компоненты инструментированы (OTel, redaction).
- Независимое review (минимум `code-reviewer` + профильный агент) проведено, CRITICAL/HIGH устранены, отчёт review сохранён.
- Документы и статусы обновлены (раздел «Обновление документов»); Increment Report заполнен.
- Нет критических открытых дефектов; если runtime-проверка невозможна — статус не выше IMPLEMENTED и пометка `IMPLEMENTATION NOT VERIFIED`.

## 14. Increment Report

Создать `docs/implementation/increments/S05_core_tenant_execution_schema_rls_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

## 15. Запреты

- Не изменять файлы `docs/architecture/` и Registry; не выдавать предложение (PROPOSED/NCP) за утверждённое решение.
- Не расширять MVP (fine-tuning, GraphRAG/отдельный vector DB, runtime code generation, A2A brokers, A3/A4, OIDC adapter, write/bidirectional sync, shadow/canary, PagerDuty и др. — `.claude/rules/project-context.md`).
- Не изобретать значения WORKING-параметров (SLO, retention, пороги, lease/backoff как «утверждённые») — задавать как конфигурацию с пометкой WORKING или регистрировать решение с обоснованием.
- Не создавать endpoint/event без контракта; не делать generic `/execute` и PATCH защищённых статусов.
- Не ослаблять ACL, audit, Readiness Gate, fail-closed поведение; не отключать проверки ради зелёного CI.
- Не использовать `latest` теги; не хранить секреты в Git/образах/логах/промптах.
- Не выполнять `git commit`/`push`, PR, внешние публикации, destructive-операции с данными и изменение глобальных настроек без явного разрешения пользователя.
- Не отправлять код/документы/идентификаторы AI RES во внешние сервисы без согласия владельца (`/security-scan` — только с согласием: загружает npm-пакет; `/code-review` — только локальный режим).

## 16. Условия остановки

Остановись и сообщи (с discrepancy report / записью в DECISIONS_PENDING), если: зависимость не DONE; canonical документ отсутствует или противоречит другому BASELINED документу и противоречие нельзя устранить без изменения baseline; реализация требует изменить бизнес-цель, MVP, права пользователя или критические гарантии безопасности; невозможно получить runtime evidence для заявленного статуса.

## 17. Покрываемые требования

- DATA-MVP
- PERSIST-001..024
- TX-01..TX-09 (persistence части)
