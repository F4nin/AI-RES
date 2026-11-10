# S02 — Backend skeleton и platform primitives (без БД)

**Фаза:** A. Foundation · **Соответствие Spec:** Spec Inc. 2 (п.1–5, 7–9); Process Design §22 п.1 (частично) · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

> **СТАТУС: DONE.** Промпт сохранён для истории; повторно не исполнять.

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Каркас модульного монолита `backend/` и платформенные примитивы, не требующие БД, с negative/security тестами и telemetry.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §4 Increment 2; §5 Required API and DTO behavior; §6
- `docs/architecture/AI_RES_API_and_Interaction_Contracts_v1.10.md` — §5 Общие HTTP правила; §6; §14 Audit, trace and correlation; §16 Error taxonomy
- `docs/architecture/AI_RES_Persistence_Implementation_Blueprint_v1.0.md` — §3 Обязательная структура репозитория
- `docs/architecture/AI_RES_Observability_Architecture_v1.2.md` — §6 Корреляция и taxonomy; §8
- `docs/architecture/AI_RES_Identity_Access_Control_v1.5.md` — §2 Слои контроля; §7
- `docs/architecture/AI_RES_Infrastructure_Deployment_Operations_v1.7.md` — §11.3 Иерархия и правила конфигурации
- `.claude/rules/coding-standards.md`
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S01 (Contract toolchain и CI-валидация контрактов)
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

- `backend/pyproject.toml` + `uv.lock` (FastAPI, Pydantic v2, uvicorn, uuid-utils, opentelemetry-*, structlog/std logging), `.python-version`.
- Пакеты `backend/src/ai_res/` по Blueprint §3 + `platform/` (ids, time, problems, correlation, pagination, concurrency, auth ports, policy port, audit port, config).
- UUIDv7 (ADR-027) и UTC RFC3339 сериализация.
- RFC 9457 Problem Details: стабильные `code` из DOC-006 §16; никаких stack traces/секретов.
- Request/correlation/trace propagation (W3C traceparent, `X-Request-ID`), OTel SDK, структурные логи с redaction (ADR-025).
- Cursor pagination codec: opaque, подписанный HMAC, привязан к пользователю/фильтру; stable ordering contract.
- ETag/If-Match примитивы и `row_version` контракт (без БД).
- Порты: `AuthenticationPort`, `ServiceIdentityPort`, `PolicyDecisionPort` (ADR-017), `AuditWriterPort` (fail-closed семантика), `IdempotencyStorePort` (реализация — S07).
- Типизированный каталог конфигурации: неизвестные ключи/неверные типы → ошибка запуска; секреты только из файлов Compose secrets.
- Architecture tests (import-linter или эквивалент): запрет импорта ORM в API-слой, provider SDK вне adapter, cross-module internals.

**Не входит:**
- Таблицы и миграции (S04+).
- Реальная аутентификация (S07).
- Доменные endpoints (S08+).

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-001 — Python 3.13 как целевая версия
- ADR-002 — uv + `uv.lock` как менеджер зависимостей
- ADR-005 — Раскладка репозитория
- ADR-008 — Web-стек Backend: FastAPI + полностью async
- ADR-025 — Поэтапная observability
- ADR-026 — Инструменты тестирования и статического анализа
- ADR-027 — UUIDv7
- ADR-032 — Статусы этапов и определение DONE

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Библиотеки логирования и architecture-test инструмента.
- Точная форма cursor и коды ошибок пагинации (в пределах DOC-006 §16).

## 7. Результаты реализации

- `backend/**` skeleton
- unit/security tests
- S02 report

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
| agent | `fastapi-reviewer` | review FastAPI слоя (ADR-008) |
| agent | `security-reviewer` | независимое security review |
| agent | `type-design-analyzer` | проверка инвариантов в типах DTO/доменных моделей |
| skill | `python-patterns` | идиомы и типизация Python |
| skill | `python-testing` | pytest, fixtures, parametrization (без FastAPI-примеров как обоснования стека) |
| skill | `tdd-workflow` | red → green → refactor |
| skill | `error-handling` | типизированные ошибки, bounded retries |
| skill | `api-design` | только в части ресурсов/статусов; пагинация — cursor, ошибки — RFC 9457 (ecc-precedence) |
| skill | `verification-loop` | финальная верификация этапа |
| command | `/plan` | план этапа до кода |
| command | `/code-review` | локальный review изменений (без PR-режима) |
| command | `/quality-gate` | проверка quality gates |
| command | `/python-review` | review Python изменений |
| command | `/test-coverage` | отчёт покрытия как дополнительная метрика |
| command | `/fastapi-review` | review FastAPI |
| command | `/security-review` | встроенная команда Claude Code: security review изменений ветки |

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- Problem Details: unknown exception → 500 c generic body без деталей; validation error → 400/422 с `code`.
- Cursor: подделка/чужой пользователь/изменённый фильтр → 400 без раскрытия данных.
- If-Match: отсутствует → 428/412 по DOC-006; stale → 412.
- Redaction: пароль/токен/cookie/`Authorization` не попадают в логи и spans (golden test).
- Config: неизвестный ключ, секрет в env вместо secret file, test-профиль LLM double в local → ошибка старта.
- Correlation: входящий traceparent сохраняется; без него генерируется; не используется как авторизация.
- Architecture tests проходят и падают на намеренном нарушении.
- Cursor-HMAC секрет не из файла (env) → отказ запуска; ротация ключа cursor: старые курсоры отклоняются, новые валидны.

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
- `docs/implementation/increments/S02_backend_skeleton_platform_primitives_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S02_*.md`.
- LOCAL_DEVELOPMENT.md
- TEST_STRATEGY.md (если появились новые типы тестов)

## 13. Definition of Done

- `make backend-check` (ruff, mypy --strict, pytest) зелёный.
- Все перечисленные negative tests присутствуют и проходят.
- Redaction доказана тестом.
- Нет доменной логики-заглушки, выдаваемой за реализацию.
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

Создать `docs/implementation/increments/S02_backend_skeleton_platform_primitives_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

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

- API-MVP (общие HTTP правила)
- SEC-MVP (error leakage)
- OBS (correlation)
