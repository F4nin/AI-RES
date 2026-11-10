# IMPLEMENTATION_CHARTER — устав реализации AI RES

**Версия:** 1.0 · **Дата:** 2026-11-10 · **Статус:** действующий (ненормативный документ управления реализацией)

## 1. Роль и мандат

Implementation Lead (Principal Architect) отвечает за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации. Мандат получен от владельца проекта: инструкции «Implementation Lead Operating Instructions» и «Master Implementation Initialization» (2026-11-10).

**Принимается самостоятельно (регистрируется как ACCEPTED ADR):** недостающие технические механизмы, подходы, библиотеки и инструменты в пределах согласованного стека, структура модулей и интерфейсов, разрешение технических противоречий и циклических зависимостей, порядок работ, способы тестирования.

**Не меняется без владельца:** BASELINED требования и документы, бизнес-цели, границы MVP, права пользователей, модель полномочий Manager/Workers, критические гарантии безопасности, публичные контракты с нарушением совместимости. Для них готовится Normative Change Proposal (`decisions/NORMATIVE_CHANGE_PROPOSALS.md`) и, при блокировке, запись в `DECISIONS_PENDING.md`.

## 2. Нерушимые гарантии

Модульный Backend; PostgreSQL `ai_res_db` — источник истины; Temporal — durable orchestration; LangGraph — reasoning; раздельные Manager Runtime и Worker Runtime pool; 9 логических Workers; Readiness Gate перед каждым WorkerRun; Workers без прямой записи в БД и без прямого Worker-to-Worker; immutable versions, provenance, audit, traceability; нет автоматического одобрения агентами; Bifrost — кандидат до PoC; Connector Platform — единственный путь к внешним системам; GitHub/GitLab read-only.

## 3. Иерархия источников

1. `docs/architecture/AI_RES_Document_Registry_v4.1.md` §2 и canonical документы (BASELINED — нормативный дизайн, не реализация; WORKING — незавершённое решение).
2. `CLAUDE.md` и `.claude/rules/*.md`.
3. Этот устав и `docs/implementation/*` (решения реализации в пределах п.1–2).
4. ECC (`.claude/agents`, `skills`, `commands`, `rules/ecc`) — инструментарий.

## 4. Система документов

| Документ | Назначение |
|---|---|
| `IMPLEMENTATION_ROADMAP.md` | Единая последовательность S00–S39, зависимости, DoD, тесты |
| `IMPLEMENTATION_STATUS.md` | Текущие статусы этапов и компонентов |
| `ARCHITECTURE_DECISION_LOG.md` | Все решения реализации (ADR-xxx) |
| `decisions/` | Подробные решения; `NORMATIVE_CHANGE_PROPOSALS.md` |
| `DECISIONS_PENDING.md` | Только вопросы владельца / security owner |
| `KNOWN_GAPS.md` | Пробелы и риски реализации |
| `REQUIREMENTS_TRACEABILITY.md` | Требования → этапы → тесты |
| `CONTRACT_TRACEABILITY_MAP.md` | API/события → агрегаты → таблицы → этапы |
| `TEST_STRATEGY.md`, `QUALITY_GATES.md` | Как и чем проверяется работа; gates G1–G9 |
| `ECC_USAGE.md` | Карта компетенций ECC и журнал использования |
| `LOCAL_DEVELOPMENT.md`, `RELEASE_AND_VERSIONING.md` | Разработка и выпуск |
| `INCREMENT_REPORT_TEMPLATE.md` | Шаблон отчёта этапа |
| `increments/prompts/` | Исполнимые промпты этапов + индекс |
| `increments/` | Отчёты этапов |
| `reviews/` | Независимые review и проверки |
| `docs/runbooks/` | Эксплуатационные процедуры (по мере появления компонентов) |

## 5. Цикл этапа

Изучить нормативные требования → проверить зависимости → определить scope → подобрать ECC → план → вертикальные срезы → тесты → независимое review → устранение замечаний → проверки → traceability и документация → статусы → Increment Report. Переход дальше при незакрытых критических дефектах запрещён.

## 6. Статусы

Реализация: NOT_STARTED, IN_PROGRESS, IMPLEMENTED, TESTED, VERIFIED, BLOCKED, DEFERRED. Решения: PROPOSED, ACCEPTED, REJECTED, SUPERSEDED. Готовность промптов: READY, PENDING_DEPS, BLOCKED, DONE (ADR-032).

## 7. Действия, требующие разрешения пользователя

`git commit`/`push`/PR; внешние публикации и отправка кода/документов во внешние сервисы; destructive-операции с данными; изменение глобальных настроек Claude Code; изменение `docs/architecture/`.
