# S01 — Contract toolchain и CI-валидация контрактов

**Фаза:** A. Foundation · **Соответствие Spec:** Spec Inc. 1 · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

> **СТАТУС: DONE.** Промпт сохранён для истории; повторно не исполнять.

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Воспроизводимая в репозитории валидация OpenAPI/AsyncAPI/JSON Schema, lint, breaking-change detection и SHA-256 контроль зеркала контрактов; минимальный CI.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §4 Increment 1; §7; §8 (Contracts)
- `docs/architecture/AI_RES_API_and_Interaction_Contracts_v1.10.md` — §15 Contract compatibility and versioning; §17 Contract testing and quality gates; §18
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (DOC-006/007/008/050/056/057), §5
- `docs/architecture/AI_RES_Architecture_Baseline_Manifest_v1.2.json` — files[].sha256
- `.claude/rules/api-and-contracts.md` — «OpenAPI/AsyncAPI toolchain»
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S00 (Repository reconnaissance и baseline manifest)
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

- Каталог `contracts/` (openapi, asyncapi, json-schema/{common,worker,events,commands}, examples) — зеркало canonical файлов (ADR-009).
- Pinned toolchain: Python (uv: openapi-spec-validator, jsonschema, pyyaml) и Node 22 LTS (`.nvmrc`/`engines`; Spectral, @asyncapi/specs, @asyncapi/parser — повторная проверка G-03; oasdiff — pinned binary или docker image по digest).
- Скрипты `contracts/tools/`: verify-mirror (SHA-256 против manifest), validate-openapi, validate-asyncapi, validate-jsonschema (локальный `$id` registry), check-refs, breaking-change (oasdiff + собственный diff для AsyncAPI/JSON Schema).
- Spectral ruleset: `spectral:oas` + правила AI RES (cursor pagination, Problem Details, Idempotency-Key на side-effecting POST, If-Match на version-sensitive writes); baseline 24 существующих warning (G-04) — новые запрещены.
- Минимальный CI workflow (`.github/workflows/contracts.yml` или эквивалент, без публикации куда-либо) и `Makefile` цели `contracts-check`.
- Examples: валидные и невалидные фикстуры для каждого контракта.
- `contracts/CHANGELOG.md` и `contracts/COMPATIBILITY.md` (политика совместимости).
- Удалить пустые корневые `src/`, `tests/`, `scripts/` (ADR-005).
- Структура overlay `contracts/openapi/extensions/`, `contracts/asyncapi/extensions/`; CI собирает base+overlay, валидирует и проверяет additive-only (ADR-009).

**Не входит:**
- Генерация application code (до S02).
- Изменение содержимого canonical контрактов.

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-004 — Contract toolchain
- ADR-005 — Раскладка репозитория
- ADR-009 — `contracts/` — проверяемое зеркало canonical контрактов

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Точные версии инструментов и способ поставки oasdiff.
- Структура CI (провайдер CI в репозитории не определён — использовать формат, исполнимый локально через `make`; CI-файл — тонкая обёртка).

## 7. Результаты реализации

- `contracts/**`
- `Makefile`
- CI workflow
- `contracts/tools/*`
- S01 report

## 8. ECC: обязательные agents, skills, commands

| Тип | Имя (установлено в `.claude/`) | Назначение на этапе |
|---|---|---|
| agent | `planner` | декомпозиция этапа на вертикальные срезы перед реализацией |
| agent | `architect` | архитектурное соответствие плана и результата нормативной архитектуре (read-only review) |
| agent | `code-reviewer` | независимое общее code review |
| agent | `silent-failure-hunter` | поиск проглоченных ошибок, небезопасных fallback и fail-open путей |
| agent | `type-design-analyzer` | проверка инвариантов в типах DTO/доменных моделей |
| skill | `contract-first` | contract-first координация, сгенерированные типы |
| skill | `api-design` | только в части ресурсов/статусов; пагинация — cursor, ошибки — RFC 9457 (ecc-precedence) |
| skill | `verification-loop` | финальная верификация этапа |
| command | `/plan` | план этапа до кода |
| command | `/code-review` | локальный review изменений (без PR-режима) |
| command | `/quality-gate` | проверка quality gates |

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- Каждый валидатор падает на соответствующей негативной фикстуре (broken $ref, неверный тип, неизвестное поле, отсутствующий required).
- verify-mirror падает при изменении одного байта зеркала.
- breaking-change: удаление обязательного поля/endpoint детектируется; additive optional поле — нет.
- Spectral AI RES rules: offset-пагинация и не-RFC9457 error в фикстуре → error.
- Полный `make contracts-check` на текущих контрактах — зелёный.

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
- `docs/implementation/increments/S01_contract_toolchain_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S01_*.md`.
- CONTRACT_TRACEABILITY_MAP.md (пути `contracts/`)
- LOCAL_DEVELOPMENT.md (команды)
- KNOWN_GAPS.md (G-03, G-04)

## 13. Definition of Done

- `make contracts-check` воспроизводимо проходит из чистого клона.
- Все негативные фикстуры падают ожидаемо.
- Lock-файлы (uv.lock, package-lock.json) закоммичены в рабочее дерево (commit — только по разрешению).
- Воспроизводимость проверяется на чистой копии рабочего дерева (commit — только по OD-06).
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

Создать `docs/implementation/increments/S01_contract_toolchain_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

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

- API-MVP-001
- API-MVP-0xx (contract compatibility)
