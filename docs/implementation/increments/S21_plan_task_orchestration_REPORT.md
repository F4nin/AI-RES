# S21 — Планирование и задачи

**Статус на 2026-11-24:** VERIFIED / DONE. Влит через
[PR #36](https://github.com/F4nin/AI-RES/pull/36) в составе G02.
Точные PlanVersion и решение человека, граф, Task, protected Cancel/replay
и G-107 после ACK покрыты общим локальным pre-pr и Linux CI точного SHA.
[Паспорт G02](../groups/G02_WORK.md).

## Актуальность разрешения Plan · 2026-11-24

В точке записи черновика и решения Plan Backend повторно проверяет
текущие проектные полномочия и сессию под блокировками. Повтор использует
тот же допуск. Новое решение связывает версию с актуальной Policy и MFA.
PostgreSQL проверил отзыв сессии после начального допуска без создания
черновика, решения, Operation или события одобрения. Совместный прогон
HTTP и Temporal вернул 66 passed. [Отчёт S20](S20_project_epic_intake_manager_REPORT.md).

## Повтор защищённого Cancel · 2026-11-24

На отдельной Ubuntu 24.04 arm64 VM проверен Cancel назначенной Plan
Operation. Точный Run остаётся активным после карантина доставки. Операторский
CLI требует подтверждения для точной записи, увеличивает поколение доставки
один раз, а закрытый маршрут адресует сигнал исходному Run. После отмены
утверждённая Task сохраняется, доменный audit записывается единожды.
`compose_candidate --network --replay-exhausted-start --paginate-history`
вернул exit 0, 1 passed за 52.91 с. В том же окружении прошла сохранность
историй и репетиция отката Temporal. Общий runtime G-107 остаётся этапом
приёмки. [Команды и границы evidence](S20_project_epic_intake_manager_REPORT.md).

## Нативная доставка и защищённая отмена · 2026-11-23

ADR-183 соединяет штатные entrypoints защищённой доставки в выделенном
Compose. На PostgreSQL 16 standalone native Runtime получил approved Plan
через Outbox, материализовал Task, сохранил `WAITING_FOR_DEPENDENCY`, отменил
точный Run и оставил ссылку на Task. History прошла replay. Backend consumer
получил Plan approval от человеческого API и создал назначенную Operation.
Во втором сценарии
после реального ACK тест вводит отказ до первой записи Task. Exact observer
видит терминальный Run. Сверка завершает Operation с одиночной записью
аудита и сохраняет детерминированный replay истории отказа. Подробные версии,
команды, review и границы evidence приведены в [S20](S20_project_epic_intake_manager_REPORT.md).
S21 и G02 **IN_PROGRESS** до общей приёмки.

## Общий транспорт S20/S21 · 2026-11-23

Standalone `native-runtime` и private bind Platform проверены на изолированном
PostgreSQL 16. Сетевой tagged кандидат прошёл Manager/Plan, повтор Start и
Manager timeout, а также отдельный replay исчерпанного Start. Штатное
подключение, общий G-107 и итоговая приёмка S21 пока открыты. Точные команды,
версии и независимые review записаны в [отчёте S20](S20_project_epic_intake_manager_REPORT.md).

**Начальный checkpoint:** 2026-11-18 · **Статус на ту дату:** IN_PROGRESS.
[Промпт S21](prompts/S21_plan_task_orchestration.md)

## Общая доставка назначенных Run · ADR-168–170 · 2026-11-21

Plan использует то же подтверждение initial Run, изоляцию START/CANCEL
Outbox и встроенную сверку до ACK, что Manager. Изолированная композиция
прошла Manager Start и Cancel, отказ Plan Run и отмену Plan Run после
создания утверждённой задачи. Публичная команда получила
`202 CANCEL_REQUESTED` из `WAITING_FOR_DEPENDENCY`. Защищённый dispatcher
доставил один сигнал точному Run. PostgreSQL подтвердил `CANCELLED`,
связь PlanItem → Task сохранилась, History прошла replay. Обычный
dispatcher защищённую команду пропускает.

`env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history`
— exit 0, 1 passed, 0 failed/skipped, 13.58 с. Darwin arm64, Python 3.13.5,
PostgreSQL 16.15, Temporal 1.29.7. База
`7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff. Первый прогон
выявил запрет расширенного чтения через SDK. Подтверждение терминала
и replay выполнены по сохранённой History временного стенда. Изменён
тест `test_native_assigned_workflow.py`. Для тестового сценария применены
Ruff и `git diff --check`, review механизмов доставки записано в
ADR-168–170. Штатное подключение и `pre-pr` остаются в приёмке G02.

`backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_plan_execution,test_manager_http}.py --tb=short`
— exit 0, 21 passed, 0 failed/skipped, 28.31 с.
[Сценарии и проверки S20](S20_project_epic_intake_manager_REPORT.md).

## Черновик из утверждённого Proposal · ADR-166/167 · 2026-11-21

`proposePlanVersion` может ссылаться на independently approved Proposal того
же Epic. Поля `goal` и `scope` сверяются с исходной версией. Неизменяемый
snapshot и audit сохраняют точное происхождение. PlanVersion по-прежнему
утверждается отдельным запросом по собственному хэшу. Контракт расширен в
WORKING overlay, прежний standalone draft сохраняет wire, snapshot и хэш.
Сквозной тест начал с результата настоящего Manager Workflow и дошёл до
Task materialization. Назначенный START проверен с новым Outbox filter.
S21 **IN_PROGRESS** до штатного защищённого допуска и групповых gates.
[Команды, ограничения и результаты](S20_project_epic_intake_manager_REPORT.md).

## HTTP-черновик PlanVersion · ADR-165 · 2026-11-21

`POST /api/v1/epics/{epicId}/plans` создаёт неизменяемую PlanVersion по
`expectedVersion` и возвращает её вместе с ETag и SHA-256. Проверка графа
использует существующий PlanGraph. Два запроса с одинаковым ожидаемым номером
не создают две версии. Существующий endpoint решения, приёмка выбранных
пунктов и правила материализации сохраняются. Контракт создания записан в
WORKING `contracts/openapi/extensions/plan_decision.yaml`. Миграций и
изменений canonical или формата событий нет.

Сессия и CSRF проверяются до чтения. Сессия и точный Project/Epic Policy
проверяются снова после ограниченного чтения. Проверены отозванные сессия
и членство во время передачи тела, отсутствие сессии, Origin/CSRF, чужой
проект, отказ Viewer, предел размера и deadline. Разрешающие проверки,
событие и audit фиксируются вместе с записанной версией. Независимые
code/Python и security review после исправлений дали APPROVE для среза.
[Запись review](../reviews/G02_S17_S20_REVIEWS.md).

**Evidence.** Ветка `feat/g02-tool-registry-manager`, `7f0c29f9519217dba722ad1f5b6396d8a02216da`
и рабочий diff. Darwin arm64, Python 3.13.5, uv 0.11.31, Docker 29.2.0,
Compose 5.0.2, PostgreSQL 16.15, Temporal SDK 1.36.0. Native Temporal 1.29.7
запущен в отдельном временном Compose с private сетями.

| Команда | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_manager_intake.py backend/tests/integration/postgres/test_planning_http.py backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_plan_execution.py backend/tests/integration/postgres/test_policy_engine.py --tb=short` | Exit 0. 210 passed, 0 failed/skipped, 86.83 с. Включены HTTP draft → approval → consumer → Temporal dev server → private ar2 → Tasks и проверка CAS/replay. |
| `make -j1 pre-push-fast contracts-check contracts-test` с `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1` | Exit 0. Ruff, mypy 266 файлов, 15 import contracts. Backend 1947 passed, 3 предупреждения, contracts 47 passed, 6 валидаторов, 0 failed/skipped. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0. 1 passed, 0 failed/skipped, 8.91 с. После HTTP-черновика и approval точный native Plan Run прошёл сценарий отказа после ACK и replay History. Тестовый Compose очищен. |
| `make -j1 infra-check infra-scan-secrets` с теми же флагами uv | Exit 0. 4 Compose-конфигурации, 0 нарушений, 0 findings. |

S21 остаётся **IN_PROGRESS**. HTTP-автором черновика выступает аналитик.
Связь одобренного Manager Proposal с PlanVersion, штатный Plan admission,
общие `make pre-pr` и Linux CI по итоговому SHA остаются условиями доставки.

ADR-163 подтвердил восстановление ошибки Plan после ACK в изолированном
native Temporal. Запрет материализации оставил ноль Task, защищённый
failure reply завершил то же исполнение, а Backend зафиксировал один
`FAILED` и аудит ADR-162. Сохранённая история Plan воспроизводится.
[Проверки](S20_project_epic_intake_manager_REPORT.md#защищённая-доставка-отказа-activity-и-workflow--2026-11-20).

После ACK Backend сверяет статус exact Plan Run с утверждённой версией,
связями PlanItem → Task и остальными локальными эффектами. Реальный
Temporal dev server и PostgreSQL подтвердили безопасный `FAILED` без
созданных задач. PostgreSQL также проверил сохранение частичной
материализации, безопасное подтверждение отмены, конкурентный повтор и
откат при недоступном аудите. [Отчёт ADR-162](S20_project_epic_intake_manager_REPORT.md#сверка-доменного-эффекта-после-ack--2026-11-20).

ADR-160 проверен на реальном Plan Run в отдельном networked native Temporal.
Публичное решение человека создало право подготовки, fixture сохранила
assignment, запустила Workflow и выполнила private ar2 ACK. Выделенный mTLS
наблюдатель прочитал точный статус до и после ACK. Штатное включение
consumers и сверка эффектов остаются открытыми.
[Команда и results](S20_project_epic_intake_manager_REPORT.md#статус-точного-активного-run-после-ack--2026-11-20).

## Обработка зафиксированного утверждения · 2026-11-20

Локальный срез **TESTED**, S21/G02 **IN_PROGRESS**. Рабочая ветка
`feat/g02-tool-registry-manager` на `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
ADR-158 добавляет opt-in Backend consumer, подключённый к lifecycle FastAPI.
Потребитель читает события утверждения только в заданном tenant, повторно
проверяет точный PlanVersion, автора и content hash. Каждая транзакция
фиксирует Operation, assignment, START Outbox, marker решения и отдельный
аудит `PLAN_EXECUTION_PREPARED`. После commit записывается метрика.
При остановке уже завершённые транзакции сохраняются.

Код в `application/plan_approval_consumer.py`, `application/plan_execution.py`,
`api/app.py` и `platform/config.py`. Изменения API, контрактов, миграций
и DB privileges отсутствуют. Конфигурация `AI_RES_PLAN_APPROVAL_CONFIG_FILE`
задаёт scopes, интервал, deadline и размер страницы. Backend требует
отдельного Plan admission в composition root. Manager admission его не
заменяет. Штатный entrypoint его ещё не подключает.

На Darwin arm64, Python 3.13.5, PostgreSQL 16.15 и реальном Temporal dev server
выполнена команда `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_plan_execution.py backend/tests/integration/postgres/test_planning_http.py backend/tests/unit/test_reconciliation_scheduler.py --tb=short`.
Exit 0, 15 passed, 0 failed/skipped, 17.29 с. Проверены отказ Manager-only
admission, tenant scope, текущая и отвергнутая версии, commit visibility,
повтор и одновременная обработка, отмена и ошибка аудита. Сценарий от HTTP
201 прошёл через реальный consumer и private ar2. Материализованы две
одобренные PROPOSED Tasks, после команды отмены Operation завершилась
как CANCELLED. WorkerRun не появился.

Ревью code/security подтверждены после исправления transaction scope,
аудита, метрики и separate Plan admission. Штатные Plan-purpose Describe,
protected dispatcher и полная приёмка S21 ещё открыты.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

## 1. Что реализовано

PlanVersion хранит неизменяемый снимок графа и его SHA-256. Аналитик читает версию и принимает решение для конкретного UUID, ETag и хэша. При частичном утверждении каждый выбранный пункт включает свои незавершённые зависимости. Привязка утверждённых PlanItems к Tasks выдерживает повтор, сохраняет зависимости и публикует события. Отдельный Temporal workflow моделирует подготовку плана и обработку отмены на компактных ссылках.

## 2. Нормативная база и Registry

Process v1.9 §§6, 15, UX v1.2 UX-PLAN, Domain Model v1.9 §§5, 11,
API Contracts v1.10 §4.4, public OpenAPI v1.3 и AsyncAPI v1.6, Registry v4.1,
ADR-012/013/038, Spec v1.22 Add. v1.1 §4. Для чтения и решения принят рабочий overlay.

## 3. Файлы

| Файл или модуль | Изменение |
|---|---|
| modules/tasks/plan_graph.py, plan_versions.py | Проверка DAG, сохранение версии и решения |
| application/plan_execution.py | Связь Operation, утверждения и PlanItem → Task |
| api/read_api.py, api/write_api.py, policy/policy_config.json | Чтение snapshot, решение человека, публичный createTask v1.3 |
| orchestration/manager_workflows.py, runtime/manager_activities.py | Отдельный PlanExecutionWorkflow и порт Activity |
| contracts/openapi/extensions/plan_decision.yaml | Рабочие GET и POST, ETag и hash |
| tests/{unit/test_plan_graph.py,integration/postgres/test_plan_execution.py,integration/postgres/test_planning_http.py,integration/temporal/test_manager_workflows.py} | Контракты, PostgreSQL, Temporal, отмена и replay |

Пути backend относительно backend/src/ai_res, тесты относительно backend.

## 4. API, контракты и события

Владелец выбрал сохранить тело запроса и Task response v1.3 с HTTP 201. Сервис сопоставляет все поля кандидата с одобренными пунктами плана в активном PLAN_EXECUTION его Epic. Отсутствие совпадения или неоднозначность возвращают 409. Read/decision overlay добавляет `getPlanVersion` и `decidePlanVersion`. События PlanVersionProposed, PlanVersionApproved, PlanVersionRejected и TaskCreated используют AsyncAPI v1.6.

## 5. Миграции и совместимость

0036 добавляет tenant-снимки, решение, binding Operation и связь с Task.
0037 добавляет неизменяемый журнал PlanVersion и Task. Транзакционная
замена триггеров сохраняет неизменность бизнес-колонок и запрет удаления.
Для runtime API действует RLS, его роли получают узкие права на нужные таблицы.
Хранение существующих Tasks и их wire representation сохранено.

## 6. Технические решения

[ADR-144](../ARCHITECTURE_DECISION_LOG.md#adr-144--s21-точное-утверждение-плана-и-createTask-v13)
фиксирует ETag неизменяемого снимка, зависимости и состав completion snapshot.
ADR-147 фиксирует подготовку в обработчике зафиксированного утверждения.
Operation, assignment и START Outbox записываются атомарно с correlation и
causation от события. Публичный `201` подтверждает решение человека.

## 7. Несогласованности и NCP

NCP-08 описывал расхождение между HTTP 201 и созданием новой Operation.
Владелец подтвердил HTTP 201 внутри существующей PLAN_EXECUTION и точное
однозначное сопоставление в рамках действующего контракта.

## 8. ECC

Planner и architect определили DAG, границу human decision и неизменяемый
контракт. Независимый code/Python/database/test reviewer проверил запросы,
снимки, события и тесты. Security/silent-failure reviewer проверил общий
Temporal/Platform путь. Python/testing/TDD/verification применены из
инструкций ECC. Вызовы Claude slash commands в Codex отсутствуют.
[Журнал ECC](../ECC_USAGE.md)

## 9. Проверки

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочая ветка
`feat/g02-tool-registry-manager`, macOS, Python 3.13, disposable PostgreSQL
16.15, Temporal CLI image из test fixture / SDK 1.36.0.

| Gate | Команда | Результат на срезе |
|---|---|---|
| G1/G2 | make pre-push-fast | 1924 passed, 3 предупреждения, exit 0 до добавления listener/client и журнала вопросов |
| G3/G5 | uv run --locked pytest -q tests/integration/postgres/test_planning_http.py tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py | 20 passed, 1 предупреждение, exit 0 на head 0037 |
| G3 | uv run --locked pytest -q tests/integration/temporal --tb=short | 15 passed, exit 0. Real dev server, synthetic Platform и test-only LLM |
| G4 | make contracts-check contracts-test | 6 проверок, 29 passed, exit 0 |
| G6 | make db-snapshot | SQL snapshot записан, exit 0. Последующий drift запускается отдельной командой |
| G3/G5 | uv run --locked pytest -q tests/integration/postgres/test_manager_http.py tests/integration/postgres/test_plan_execution.py tests/integration/postgres/test_planning_http.py --tb=short | 4 passed, exit 0. Обработчик читает зафиксированное событие, создаёт один START и возвращает прежнюю Operation после появления новой версии |

## 10. Авторизация

Проверены запрет решения Viewer, одинаковый 404 для чужого проекта, 428 при
отсутствии If-Match, 412 для устаревшего ETag/хэша, 409 для отсутствующего или
неоднозначного пункта, связь Task с точной действующей Operation, replay одного
решения и одной Task. SQL читается в tenant-транзакции.

## 11. Независимое review

Независимый reviewer проверил S21 и подтвердил исправление проверки дубликатов предшественников.
Расхождение вокруг ETag снято через публичное чтение той же неизменяемой
версии и фиксацию semantics в overlay. Профильное review итогового
production соединения ещё требуется. [Результаты](../reviews/G02_S17_S20_REVIEWS.md)

## 12. Ограничения доказательства

Публичное утверждение сохраняет решение. Сквозной тест использует opt-in
Backend consumer по ADR-158. PlanExecutionWorkflow получает подготовленный
результат через private TLS/ar2 v0.3 и отдельную PostgreSQL роль.
Штатное включение consumer требует отдельного native Plan admission.
Две одобренные задачи материализованы в PROPOSED и одна исключена. Replay
сохраняет прежний исход, WorkerRun отсутствует. Полный pre-pr и Linux CI
текущего diff ещё требуются.

Общий guard ADR-159 применяется к существующему Plan decision. HTTP путь
сверяет tenant, `plan.decide`, `If-Match` и digest точной версии. Продуктовый
producer Manager draft → PlanVersion открыт. Сквозной тест подготавливает
неизменяемую PlanVersion в fixture, после чего публичный HTTP approval и
consumer выполняются по штатным для тестовой композиции путям.

## 13. Документы и статусы

Обновлены ADR, STATUS, HANDOFF, scope группы, NCP-08, tracing требований и контрактов,
KNOWN_GAPS и ECC_USAGE. Канонический публичный OpenAPI и его зеркало сохранены в v1.3.

## 14. DoD

Граф, точные решения, публичное чтение и создание Task проверены целевыми
тестами. Production Temporal → Platform → Plan и полные gates G1–G9
остаются открыты. Проверки нового journal/миграции учитываются отдельно.

## 15. Продолжение

Подключение типизированного PlanExecutionWorkflow через защищённый запуск и
G-107, затем общая проверка G02. S22 остаётся следующим этапом roadmap после G02.
