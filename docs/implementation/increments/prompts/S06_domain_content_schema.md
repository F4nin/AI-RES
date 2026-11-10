# S06 — Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules

**Фаза:** B. Persistence & Identity · **Соответствие Spec:** — (DOC-005; ADR-016) · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

> **СТАТУС ПРОМПТА: PENDING_DEPS.** Исполнять только после перевода всех зависимостей в DONE.

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Физическая модель контентных bounded contexts с immutable versions, provenance и RLS.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` — §6 Требования, §7 Источники и знания, §8 Решения и неопределённость, §9 Артефакты и governance, §10 Трассируемость, §11 Агентное исполнение и контекст, §12, §15–§19
- `docs/architecture/AI_RES_Requirements_Lifecycle_v2.7.md` — §13–§16
- `docs/architecture/AI_RES_Source_and_Context_Lifecycle_v1.3.md` — §3, §6
- `docs/architecture/AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md` — §3, §6, §10
- `docs/architecture/AI_RES_Traceability_Dependencies_Impact_Analysis_v1.0.md` — §3–§5
- `docs/architecture/AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md` — типизированные объекты
- `docs/architecture/AI_RES_Agent_Architecture_Concept_v4.6.md` — §15 (Rules Registry)
- `docs/architecture/AI_RES_MVP_Capability_Matrix_v3.3.md` — Дополнение v0.8 (RULE-MVP)
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S05 (Core tenant и execution schema + RLS)
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

- requirements: requirements, requirement_versions (immutable, статусы DOC-003, type registry + UNKNOWN).
- sources: sources, uploads, source_versions (immutable, checksum, MinIO key), extraction_records.
- artifacts: artifacts, artifact_versions (immutable), validation_reports, reviews, approvals, publications (раздельные факты).
- context: context_packages, context_package_versions (immutable, refs).
- decisions: decisions, assumptions, risks, issues, unknowns, hypotheses, conflicts — отдельные таблицы (DOC-051).
- traceability: traceability_links (type registry), link-type registry; специализированные таблицы Task–Requirement, ArtifactVersion–ValidationReport.
- governance: baselines, baseline_items (immutable), change_requests (структура; lifecycle — S31).
- rules: rules, rule_versions (RULE-MVP-02 поля).
- Current-version pointers с транзакционным переключением; RLS FORCE; repositories.
- Append-only event history для агрегатов с AsyncAPI-событиями (основа SSE, ADR-033).
- Расширение reference-таблицы aggregate_type.

**Не входит:**
- Бизнес-процессы над этими данными (S09, S26–S31).

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-014 — Имена PostgreSQL schemas
- ADR-016 — Проектирование отсутствующих физических таблиц
- ADR-018 — Rules Registry и Rules Engine — отдельные интерфейсы в модульном монолите
- ADR-034 — Rework после terminal Operation и RLS/grants для event-таблиц

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Физическое представление каждого объекта DOC-005 §6–§12 (ADR этапа).

## 7. Результаты реализации

- Alembic revisions
- repositories
- integration tests
- S06 report

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

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- Immutable versions: UPDATE содержимого утверждённой версии → отклонение.
- Неизвестный requirement type → UNKNOWN, не ближайший тип.
- object_type/link_type вне registry → отклонение.
- RLS isolation для всех новых tenant tables.
- Baseline items не изменяются после создания.
- Upgrade from previous revision без потери данных.

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
- `docs/implementation/increments/S06_domain_content_schema_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S06_*.md`.
- CONTRACT_TRACEABILITY_MAP.md
- REQUIREMENTS_TRACEABILITY.md

## 13. Definition of Done

- Все тесты зелёные; RLS coverage 100%; drift = 0.
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

Создать `docs/implementation/increments/S06_domain_content_schema_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

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
- UX-REQ/UX-SRC/UX-ART (данные)
- RULE-MVP-02
