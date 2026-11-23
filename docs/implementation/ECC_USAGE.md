# ECC_USAGE — использование Everything Claude Code

## G02 · техническое закрытие · 2026-11-24

Контрольный список `verification-loop` применён к Linux CI точного SHA,
целевому запуску G-107 и сравнению Git-деревьев после merge. Доказательства
подтвердили готовность технического объёма S17/S20/S21.
[Матрица gates и результаты](groups/G02_WORK.md).

## G02 · подготовка к Linux CI · 2026-11-24

`verification-loop` прочитан и применён как контрольный список перед
доставкой. Проверены манифест локального Ubuntu-среза, результаты
`make pre-pr`, текущий diff, canonical Registry и границы runtime evidence.
Штатный допуск профиля и целевой G-107 остаются открытыми.
Повторное независимое review этого технического среза не запускалось:
совпавший манифест сохраняет границы ранее записанного code/security
review. [Паспорт G02](groups/G02_WORK.md),
[Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · security сборки native Temporal · 2026-11-24

`g02_native_security_review` и `g02_native_code_review` независимо сверили
применимость находок, совместимость версий и официальный Go module graph.
`g02_native_security_review` восстановил альтернативные locks из архива,
сверил хеши Go SumDB и потребовал доказать фактический охват бинарника
сканером. Основной исполнитель добавил обязательную проверку инвентаризации,
проверил отказ на исходном артефакте и пересобирает образ с обновлениями.
[Отчёт S20](increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · репетиция перехода и Manager · 2026-11-24

`protected_wiring_plan` применил planner и Python integration testing к
трем фазам stock/native/stock. `protected_wiring_review` независимо проверил
изоляцию и охват. `g02_native_security_review` применил security checklist
к полномочиям model/context и отдельно проверил границу mTLS/ar2 и v0.5.
`proactive_delivery` реализовал раздельные seeks и измеримую проверку
PostgreSQL. `g02_native_code_review` подтвердил их семантику и исследовал
безопасную изоляцию общего тестового стека. Основной исполнитель применил
`verification-loop` к build/trust, Ruff, mypy, runtime tests, secret scan
и рабочему diff. [Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · защищённая композиция и доставка · 2026-11-23

`protected_wiring_plan` применил planner к сети, секретам и последовательности
запуска. Затем реализовал изолированный `init-g02` и проверил режимы файлов.
`proactive_delivery` внедрил ADR-182 и применил `python-testing` к миграции и
авторизации на PostgreSQL. Независимые read-only проверки выявили проблемы
на границах Compose, credential recovery, объёма запросов ленты и интервала
сводки. Исполнитель применил `verification-loop` к pinned builds, сценариям
PostgreSQL/Temporal, secret scan и diff. Фактические результаты и открытые
проверки ведутся в [отчёте S20](increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · native runtime и коммуникация · 2026-11-23

`verification-loop` применён как checklist Linux сборки из pinned source,
проверок Go/Python, PostgreSQL/Temporal regression, secret scan и diff review.
Отдельные blind-first read-only `g02_native_code_review` и
`g02_native_security_review` проверили конфигурацию, build tags, trust/transport,
отзыв в полёте и негативные тесты. Findings устранены и повторно проверены.
Те же роли отдельно применили архитектурный/product анализ уведомлений и
проверку источника доказательств v0.4. Профильное review проверило явный bind
Platform. [Материалы review](reviews/G02_S17_S20_REVIEWS.md).

## G-107 · явный reconciliation allowlist · ADR-180

`python-testing` и `verification-loop` применены к форме trusted config,
legacy compatibility и ограничению post-ACK. Проверены duplicate JSON keys,
orthogonal allowlist/flag cases, PostgreSQL/Temporal Plan и combined native
Manager timeout сценарий. `epic_review` и `epic_security` провели blind-first
read-only review; после исправления трёх замечаний оба дали APPROVE.
[Evidence](increments/S20_project_epic_intake_manager_REPORT.md).

## S20 · раздельный ключ назначенной доставки · ADR-179

`verification-loop` применён к конфигурационной границе и производному
Ed25519-реестру. Изменение ограничено загрузчиком ключа и dev secret
tooling; целевые Compose mounts пока не подключены. Blind-first code и
security review выполнили `epic_review` и `epic_security`; после исправления
keypair upgrade и строгого issuer allowlist оба дали APPROVE.

## S20/S21 · NCP-19 и ADR-178

`verification-loop` применён к SQL-модели, схеме, контрактам
и сетевому сценарию раздельных процессов. Blind-first code и
security review выполнены через `epic_review` и `epic_security`.
Изменения по findings проверены отдельным повторным review.
[Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · доставка ADR-177

`verification-loop` применён к проверке транспорта, быстрому набору,
контрактам и native Temporal. `epic_review` и `epic_security`
выполнили независимые read-only проверки. Повторный Cancel без RPC
и отказ дополнительных credentials покрыты тестами по findings.
[Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · маршрут Outbox ADR-176

`verification-loop` применён к миграции, schema drift, grants/RLS,
совместимости доставки, статической проверке и native Temporal.
`epic_review` и `epic_security` выполнили blind-first code и security
review и подтвердили исправление карантина и replay.
[Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20 · private v5, 2026-11-21

`verification-loop` применён через Ruff, mypy, import-linter, PostgreSQL
upgrade и schema drift, contract validation и native Temporal.
`epic_review` и `epic_security` выполнили blind-first code и security
review и подтвердили исправления SQL-границы. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · узкая проекция ADR-175, 2026-11-21

`python-patterns` применён к общим SQL-связям двух проекций.
`python-testing` применён к проверке неизменности и изоляции снимков
в PostgreSQL. Независимые `epic_review` и `epic_security` выполнили
code/Python и security review. Тест различения Operation усилен по
finding. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · ADR-174/175, 2026-11-21

Code и security review применены через `epic_review` и `epic_security`.
Проверены активная сессия, MFA, границы RLS, audit и конкурентный replay.
Исправлены гонка отзыва и истечение сессии при ожидании Outbox.
`verification-loop` применён к native, миграциям, grants и policy matrix.
[Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · ADR-171–173, 2026-11-21

`python-testing` и `verification-loop` использованы для регрессии
отмены до ACK, версии проекции и границ группировки. `epic_review`
проверил Python, транзакции и интервалы, `epic_security` проверил
границу отмены. Findings по интервалу исправлены. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S21 · отмена Plan Run после создания задачи · 2026-11-21

`verification-loop` применён к изолированному native Compose, точному
сигналу Outbox, подтверждению результата в PostgreSQL и replay. Проверены
регрессии Plan и Manager HTTP. Изменение ограничено тестовым сценарием и
доказательствами. Review механизмов доставки записано в ADR-168–170.
[Evidence](increments/S21_plan_task_orchestration_REPORT.md).

## S20/S21 · replay исчерпанного Start · 2026-11-21

`verification-loop` применён к реальным PostgreSQL, Outbox и pinned
Temporal. Новый режим меняет только test launcher и сценарий.
Использованы существующие проверенные prepare/Start/binding/replay;
профильные review этих путей зафиксированы в ADR-168–170.
[Evidence](increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · ранняя отмена и допуск Start · 2026-11-21

Два read-only review применили code, PostgreSQL/concurrency и security
компетенции. По их findings запись вынесена из native authority в
tenant Backend, отменённый до допуска intent обрабатывается без RPC.
`verification-loop` применён к schema drift, grants/RLS, Idempotency-Key,
native cancel и replay. [Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · подтверждённый старт · 2026-11-21

`verification-loop` применён к pinned Go, повтору Start на PostgreSQL и
Temporal и контрактным проверкам. Code и security компетенции применены
двумя read-only агентами. Отказ при outage исправлен, два APPROVE.
[Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · точный Cancel и ранняя гонка · 2026-11-21

Code/contract/DB и security review выполнены двумя read-only Codex-агентами.
APPROVE относится к привязанному Run после ACK. Обнаружена блокирующая
гонка до binding. `verification-loop` применён к Go native build, real
PostgreSQL, schema drift, grants/RLS, contracts и replay. Claude slash
commands не запускались. [Ревью](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · Proposal approval и START Outbox · 2026-11-21

`python-testing` и `verification-loop` применены для PostgreSQL/Temporal,
bounded ingress, прохода статических и contract checks. Codex-агенты
`epic_review` и `epic_security` независимо применили code/Python,
contract/coverage и security review. Найденные проблемы ограниченного
чтения, ACL `resultRef` и описания lineage исправлены. Повторные review
дали APPROVE в границах ADR-166/167. Claude slash commands не запускались.
[Evidence](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · запрос проекции Epic и создание PlanVersion · 2026-11-21

Чек-листы `python-patterns`, `python-testing` и `verification-loop` применены
к типизации, красным/зелёным интеграционным тестам и контрольным прогонам.
Два Codex-агента read-only, blind-first применили компетенции
`code-reviewer`/`python-reviewer`/`pr-test-analyzer` и `security-reviewer`.
По замечаниям добавлены provenance Proposal, тесты изоляции, CAS `412`,
точные Policy-правила, повторная аутентификация после stream и audit.
Оба повторных review команды дали APPROVE. Проверка касается среза ADR-165.
Claude slash commands в Codex не запускались. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · пагинация native Workflow Task

В проектном verification-loop использованы Go build/test, статические
проверки и отдельный Compose-прогон. Независимые `code-reviewer` и
`security-reviewer` сверили pinned Temporal, закрыли дефект тестовой
настройки и подтвердили границы полномочий. Review было read-only.
[Evidence](reviews/G02_S17_S20_REVIEWS.md).

## S20 · native Manager Activity timeout после ACK

`verification-loop` применён к реальному timeout, точной History и
сверке аудита. Независимое `go-reviewer` проверило изоляцию режима,
реальный ACK, идентификаторы события таймаута и приватность истории.
Уточнения по assertions внесены, scope одобрен. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · защищённая доставка отказа Activity → Workflow

Применены `tdd-workflow` и `verification-loop` к исчезавшему сбою Plan.
Независимые `go-reviewer` и `security-reviewer` в read-only режиме проверили
порядок RPC checks, совместимость закреплённого SDK, исторический receipt,
очистку payload и границы evidence. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · сверка доменного эффекта после ACK · 2026-11-20

`tdd-workflow`, `postgres-patterns` и `verification-loop` применены к
доменным сценариям, блокировкам, аудиту и прогону real Temporal/PG. RED
выявил отсутствие пост-ACK обработки страницы. Независимые code и
security reviewers проверили requeue/ACK, version fencing, audit RLS и
atomicity. [Результаты](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · наблюдение статуса активного Run · 2026-11-20

`tdd-workflow`, `postgres-patterns`, `verification-loop` применены к scope
запроса, fail-closed допуску, миграции 0048 и проверкам upgrade/drift. RED
зафиксировал отсутствие подписанного действия, GREEN подтверждён через
PostgreSQL. Два независимых reviewer проверили Python, Go и SQL. Найденные
redirection/expiry cases закрыты и перепроверены.
[Review](reviews/G02_S17_S20_REVIEWS.md).

## S20/S21 · общий guard утверждения · 2026-11-20

`python-testing` и `verification-loop` применены к PostgreSQL регрессиям
авторизации, срока действия, хэша и SoD. Независимые `code-reviewer` и
`security-reviewer` подтвердили сохранение поведения общего guard и
отметили границы exact Policy и отсутствующего продуктового producer Plan.
[Результаты](reviews/G02_S17_S20_REVIEWS.md).

## S20 · подписанный Manager input v0.4 · 2026-11-20

- Инструкции `python-patterns`, `python-testing` и `verification-loop`
  применены к strict parser, exact Run и существующим real TLS/PG fixtures.
- Независимые `code-reviewer` и `security-reviewer` проверили diff. LOW по
  максимальному Unicode payload и непустому ответу закрыты расширением
  конечного лимита и fixture-тестом. [Review](reviews/G02_S17_S20_REVIEWS.md).

## G02 · S21 consumer и потерянный ответ Start · 2026-11-20

- Инструкции `python-patterns`, `python-testing`, `tdd-workflow` и
  `verification-loop` использованы для consumer, tenant, идемпотентности
  и сбоя Start. RED подтвердил отсутствие обработчика страницы, GREEN
  проверен на целевых сценариях PostgreSQL и Temporal.
- Независимое code review выявило откат целой страницы при deadline и
  недосчёт метрики. Security review выявило смешение допусков Manager/Plan
  и отсутствующий audit подготовки. Все замечания этого среза устранены.
  [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · сети Compose и повтор Outbox · 2026-11-20

- Инструкции `go-reviewer`, `security-reviewer` и `verification-loop`
  применены к конфигурации межсервисного транспорта, отказу отметки доставки
  и сравнению истории Run и результатов.
- Независимые review проверили fencing репозитория, роли DB, выбор
  входящего интерфейса, exact-origin и границы runtime evidence.
  Добавлен отрицательный тест origin. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · private ar2 и PostgreSQL verify-full · 2026-11-20

- Применены инструкции `go-reviewer`, `security-reviewer` и
  `verification-loop` к Compose mounts, проверке CA/hostname, startup guard,
  scoped DB roles и runtime evidence.
- Независимые code и security review выявили риски UID/GID и доступа
  native к данным тестового runner. Исправлены standalone Compose, разделение
  контейнеров и mounts, проверка эффективной конфигурации и права UID.
  [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · восстановление Run в тестовом Compose · 2026-11-20

- Применены `go-reviewer`, `security-reviewer` и `verification-loop`
  к закреплённой Go-сборке, сетевой изоляции, воспроизводимости
  restore/restart и проверке доказательств.
- Независимые code и security review проверили lifecycle, приватные файлы,
  полномочия импорта, доступ проверяющего к ключам и точность evidence.
  Исправления проверены повторным review. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · PostgreSQL и internode mTLS · 2026-11-20

- Локальные инструкции `go-reviewer` и `verification-loop` применены к
  изоляции test binary, отрицательным сценариям и проверкам Go/Python/Temporal.
- Независимое read-only code review проверило очистку fixture, запись visibility
  и диапазон портов. Security review проверило сетевые границы, два CA и
  обнаружило возможность DSN override. Замечания закрыты валидатором,
  изоляцией PostgreSQL и тестами. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 · Linux-сборка native Temporal PoC · 2026-11-20

- Применены `go-reviewer` и `verification-loop` для плана проверки Go build,
  закреплённых входов, статической линковки, transport и отказов запуска.
- Два независимых read-only review проверили build provenance, source/lock
  hashes, UID, loopback, mTLS и диагностику. Уточнены `/scratch`, OCI metadata,
  startup guards, offline-компиляция и `passwd/group` для CGO-free старта.
  [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 / G-107 · планировщик сверки до ACK · 2026-11-20

- Применены `python-patterns`, `python-testing`, `tdd-workflow` и
  `verification-loop` для Backend lifecycle, конфигурации и тестов. RED
  подтвердил отсутствие scheduler, GREEN проверен на целевых тестах и быстром слое.
- `code-reviewer` / `python-reviewer` обнаружил сброс прогресса на timeout.
  Независимый `security-reviewer` выявил остановку scheduler при неизвестном
  SDK status и пробел native evidence. Исправлены курсор, typed Describe и
  ожидание завершённого span. Оба повторных review APPROVE.
- Применены штатные pytest и `make`, без имитации Claude slash-команд.
  [Review](reviews/G02_S17_S20_REVIEWS.md), [тесты](increments/S20_project_epic_intake_manager_REPORT.md).

## S20 / G-107 · native Describe до ACK · 2026-11-20

- Корневой исполнитель применил `python-patterns`, `python-testing`,
  `tdd-workflow` и `verification-loop` для нового signed action, миграции,
  ревизии snapshot и фактической native проверки. DB и contract RED отработали
  по ожидаемой причине, после исправлений зелёные.
- Независимые `code-reviewer` / `python-reviewer` и `security-reviewer` сверили
  Go authorizer, ar2, SQL/ACL и контракт. Оба нашли пропущенный signed action
  уровня MEDIUM. Enum и conformance тест исправлены. В тест добавлен отдельный
  отказ после committed revocation. Открытых CRITICAL/HIGH/MEDIUM в срезе нет.
- Использованы Go, штатные `make` и pytest. Для общей приёмки S20 сохраняется
  полный набор ролей и gates промпта. [Review](reviews/G02_S17_S20_REVIEWS.md).

## S20 / G-107 · пакетная сверка до ACK · 2026-11-20

- Корневой исполнитель применил `python-patterns`, `python-testing`,
  `tdd-workflow` и `verification-loop`. Выбор курсора проверен против поведения
  изменяющейся выборки, тест подтвердил RED и GREEN на PostgreSQL, общий
  быстрый слой и целевые PostgreSQL/Temporal проверки прошли.
- Независимый агент `code-reviewer` / `python-reviewer` проверил keyset,
  границы транзакций, CAS, поведение повтора и тесты. APPROVE, 0 findings.
- В повторном проходе `pr-test-analyzer` проверил отдельный `QUEUED`, соседний
  проект одной организации и интеграцию страницы с Temporal. APPROVE.
- Независимый `security-reviewer` проверил tenant isolation, allowlist,
  точный Run, повторный scope check, audit и обработку неопределённости.
  APPROVE для внутреннего среза. Верхняя граница страницы относится к
  доверенной конфигурации будущего планировщика.
- Использованы репозиторные `make` и pytest. Claude slash-команды не
  вызывались. Полный набор ролей S20 проверяется при общей приёмке.
  [Review](reviews/G02_S17_S20_REVIEWS.md), [evidence](increments/S20_project_epic_intake_manager_REPORT.md).

**G02 S20/S21, 2026-11-18.** ECC planner/architect подготовили порядок
внутренних срезов, DAG и точные границы полномочий. Независимый
code-reviewer/Python/database/test reviewer проверил записи, DDL, grants и
негативные сценарии. Security/silent-failure reviewer проверил ar2, TLS PoC,
seal вложений, историю Activity и отмену. Исправлены привязка к immutable event,
сериализация исключений, контроли запросов и correlation аудита. Python/testing,
TDD и verification применены как прочитанные инструкции к целевым тестам.
Отдельное runtime review после соединения ещё предстоит, Claude slash
commands не выполнялись. [Review](reviews/G02_S17_S20_REVIEWS.md)

## SLICE-01 — 2026-11-18

| Роль | Фактическая работа | Результат и независимость |
|---|---|---|
| Root | Scope/интеграция/host composition/native fixture, реальные tests/model calls; прочитанные planner/python-testing/verification-loop checklists | Успешный V3; исполнял проверки, не выдавал личные approvals |
| slice_budget_transport | Автор ledger/tests; отдельный read-only security/database review чужих host/producer/owner/requirements/MFA | 83 ledger tests; final APPROVE/open0 на чужом source |
| slice_runtime_plan | Автор relay/tests; read-only architecture/Python/requirements/ledger/host review; полное чтение45startupfiles | 62 relay tests; final delta APPROVE, свои файлы не утверждал |
| slice_requirements_design | Автор requirements/prompts/owner/capture/совместимости MFA и tests; read-only review чужих ledger/relay | Auth/PG/capture/JSON/grounding regressions; свои изменения проверены другими |

Review исправил конкретные дефекты: missing freeze/schema/image binding, потерю
диагностики, live-controls race window, runtime drift во время human review,
JSON-escaped secrets до quarantine, неполную схему промпта и line offset.
V3 validators остались строгими; actual response не нормализовался для принятия.
MFA helper больше не читает localizeddetail и не повторяет OTP автоматически.

Root final local evidence: V2scope371PASS/35.52s, V3affected87PASS/22.35s,
fast1896PASS/4warnings/15.12s, explicitmypy10PASS, scanner0, helper28PASS/0.12s.
Полный pre-pr и exact Linux CI PASS; PR34 merged. Реальные SLICEcalls6, известный
консервативный расход0.0032058USD; роли/review не подменяют эти факты.
[Отчёт](increments/SLICE-01_requirements_experiment_REPORT.md), tooling/live evidenceV1–V3.

Ранний preflight147tests+19disabled-relay checks и MFA resume20tests сохранены в
отдельных evidence, это исторические исполнения с прежними hashes. Авторы не
подменяли независимое review. Native Claude agents/slashcommands/hooks, независимый
продуктовый WorkerQA, semantic quality и production certification не имитировались.

## G156 / ADR141 — observed product wiring и полный human approval path

Root восстановил действующее поручение/known draft, применил прочитанные локальные
python-testing и verification-loop как checklists (behavioral RED→GREEN, scope,
evidence), реализовал fixes/CLI/PG tests и интегрировал. `activation_scope` сначала
отдельно read-only planner/architect анализировал минимальное закрытие missing
profile activation, затем написал только profile_approval.py и его unit tests;
свои файлы не ревьюировал. Новых stages/framework/roles/grants не предложено.

`observed_general_review` — отдельный blind-first code/Python/architecture и
silent-failure source review; `observed_security_review` — независимый security/
database/authorization/locks/replay/path/redaction review. Два final APPROVE/open0,
findings и source hashes — [протокол](reviews/G02_OBSERVED_APPROVAL_REVIEWS.md).
Проверяющие не выполняли runtime; root исполнил actual PG10 observed +21 approval,
pure50 observed +32 approval/CLI; fast1538PASS/4warnings. Full final gates/evidence
уточняются в [текущем отчёте](increments/G02_identity_admission_operator_REPORT.md).
Native Claude slash commands/hooks, product QA и человеческое approval не заявлены.

Закрыты reverse SSE durable block, final reauthorization, Settings composition,
second APPROVED, invalid candidate, unsafe getpass fallback и ошибочные reason-code
assertions. Source review не заменяет Linux CI/live timeout/human acceptance.

## G156 / ADR140 и конечная candidate composition,2026-11-18

Root — author identityoperator/DDL/tests/integrator/runtime operator;
python-testing/verification-loop прочитаны как checklists. executor_plan отдельно
planner/architect+general/Python/database review root executor, затем автор только
candidate_launch.py+unit tests; себя не ревьюировал. executor_normative отдельно
normative reconnaissance+security/architect/silent-failure review обеих реализаций;
launch_general отдельно blind-first general/Python/pr-test review launch.
Native commands/hooks/productQA/human approval не имитируются.

MEDIUM inherited EXECUTE/SQLNULLgeneration и LOWFK исправлены до successfulapply;
owner parameterSET отдельно source-reviewed после полного firstattempt rollback.
Оба finalreview executor APPROVE/open0, finaltiny snapshotformat/catalogue delta
sourceAPPROVE; launch два APPROVE/open0. Root actualjointPG306PASS/fast1434PASS,
authorlaunch22purePASS; [executor](increments/G02_identity_admission_operator_REPORT.md),
[review](reviews/G02_IDENTITY_OPERATOR_REVIEWS.md), [launchreview](reviews/G02_CANDIDATE_LAUNCH_REVIEWS.md).
Fullpre-pr/LinuxCI/realprovider не подменяются source verdict. По уточнению владельца
завершается весь MVP-допуск, промежуточный report не конец текущего поручения.


## G156 / ADR139 — authenticated owner identity-review,2026-11-18

Root — единственный author/integrator/runtime operator; python-testing/verification-
loop прочитаны как checklists (TDD/evidence/scope). `owner_plan` — отдельный read-only
planner/architect, затем general/Python/database/pr-test source review;
`owner_normative` — normative reconnaissance, затем independent security/architect/
silent-failure source review. Native Claude commands/hooks/productQA не имитируются.

Два MEDIUM (session expiry during fence wait, factor/session lock inversion) исправлены,
второй воспроизведён actualPG RED locktimeout. Добавлены real waiter/reset interleave,
active subject change, session/policy staleness и lossless full numeric snapshot.
Оба finalsource APPROVE/open0/4hashes; reviewers не запускали tests/runtime и не
читали author report до выводов. Root newPG42PASS/joint187PASS,unit9PASS,
contracts22PASS; fast/final commands — в [отчёте](increments/G02_owner_review_binding_REPORT.md),
[протокол](reviews/G02_OWNER_REVIEW_REVIEWS.md). Материал review не human approval,
G156/pre-pr/LinuxCI/live/SLICE pending. Обязательные роли bounded seam покрыты;
готовность будущего privileged executor не проверяется текущим source verdict.

## G156 / ADR138 — admission lifecycle fence, 2026-11-18

Root — единственный автор/интегратор/runtime operator; прочитанные python-testing
и verification-loop как checklists. Отдельные read-only admission_plan
(planner/architect, затем general/Python/database/pr-test source review),
admission_normative (canonical/current addenda/Registry/ref/manifest reconnaissance),
lifecycle_security (blind-first security/architect/silent-failure review).
Авторы и reviewers различны; native Claude hooks/commands/productQA не имитируются.

Оба actual DDL reviewers APPROVE до first apply; final4hash/source/test/snapshot
APPROVE/open0. Note о пустом old history закрыт populated receipt/audit fixture.
Root исправил test-only rollback teardown, повторил full scoped suite; finalPG111PASS,
fast1419PASS/4warnings,mypy196/15importsKEPT,contracts22PASS.
[Отчёт](increments/G02_admission_lifecycle_fence_REPORT.md), [протокол](reviews/G02_ADMISSION_LIFECYCLE_REVIEWS.md).
Source review не human approval/runtime reviewer execution; fullG156/live/CI pending.

## G156 / ADR137 — configuration integrity2026-11-18

`config_integrity_plan`: отдельные planner/architect actualsource analysis, затем ограниченное авторство только3path Go patch/tests, gofmt; runtime не запускал, не reviewer себя. Root: build/launcher/Python/sourcebinding/native fixtures/integration/docs, прочитанные python-testing/verification-loop как checklists. Два отдельные blind-first read-only `bifrost_audit_review` (general/Go/Python/test) и `bifrost_isolation_security` (security/Go/architect/silentfailure); .claude/agents/go-reviewer instructions применены, native slash commands/hooks/productQA/human approval не имитировались.

Исправлены MEDIUM typed SQLite collision и proxy-health spoof, LOW sticky-restoration evidence; оба finalsource APPROVE/open0/15hash0mismatch, tiny Cmd/env-i-restoration deltas отдельно APPROVE. Reviewers не запускали Go/Docker/tests, execution — root. Normal/raceGo8parents+42subPASS,vet0; staticcheck unavailable; fast1419PASS/4warnings,mypy195/15imports; build/proofPASS/newnative12PASS/final104.20s,legacy65PASSизjointс1testfixturefailure(исправлен/повторnew12). NoSQLexceptions, source-only verdict не заменяет wholeG156/pre-pr/LinuxCI/live/human. [Report](increments/G02_candidate_configuration_integrity_REPORT.md), [review](reviews/G02_CONFIGURATION_INTEGRITY_REVIEWS.md). Владелец просит после документов остановиться, G02 NOT_STARTED.

## G156 / ADR136 — native config/isolation audit2026-11-18

Root: planner/architect scope по existing interfaces/pinned source; явно прочитанные `python-testing` и `verification-loop` как checklists реальных fixtures/regression/evidence. `contract-first` прочитан для оценки применимости: public/wire contract не меняется, новой schema machinery нет. Два отдельных blind-first read-only agents `bifrost_audit_review` (general/Python/test) и `bifrost_isolation_security` (security/architect/silent-failure) проверили чужие4codefiles до авторского отчёта. Исправлены MEDIUM provider envelope/direct-key opt-in; final delta/mount-order reviews APPROVE/open0. Runtime принадлежал root, reviewers не запускали tests/Docker и не подменяли human acceptance.

Native6PASS/final7.18s,host78PASS/RED1 доfix,fast1390PASS/4warnings,mypy194/15importsKEPT. Actual audit подтвердил OPEN effective-config integrity: admin меняет live/SQLite при unchangedfile/inspect; pass reproduction не означает security acceptance. Mounts-order canonicalization устраняет false-refusal с сохранением всех полей. Нативные slash commands/hooks не запускались, live/pre-pr/LinuxCI/весьG156 не объявлены выполненными. [Report](increments/G02_bifrost_effective_isolation_REPORT.md), [review](reviews/G02_BIFROST_ISOLATION_REVIEWS.md).

## G156 / ADR136 — development host,2026-11-18

`host_plan`: отдельное read-only planner/architect исследование actual interfaces/ADR133–135, затем только candidate_host.py/test_candidate_host.py (прочитанные Python patterns/testing/TDD), RED missing module→GREEN77PASS; автор не reviewer. Root применил integration/Python/TDD/doc-updater checklists: source binding RED5→GREEN5, explicit resource/claim composition, read-only account query, accounting-only standalone factory, tests и контекст. Native Claude commands/hooks не запускались.

`host_python_review`: отдельный blind-first read-only general/Python/database/pr-test-analyzer; `host_security`: отдельный blind-first read-only security/architect/silent-failure всех boundaries. Исправлены root/NNPfalse, boundedstdout, local drift during awaits, Git redirects/hooks/signing, provider-shaped virtual key, checkout/Docker-path/prod guards и gaps control lifecycle tests; finalAPPROVE/open0. Авторы не присваивают себе независимое review. Reviewers только source/AST/Ruff/read-only smoke, не DB/runtime. Rootfast1389PASS/4warnings,mypy194/15KEPT; actualPG22PASS;finalaffected142PASS. [Evidence](increments/G02_candidate_development_host_REPORT.md), [review](reviews/G02_DEVELOPMENT_HOST_REVIEWS.md). Непроверенные live topology/mutable effective SQLite/admin config/provider/human gates не закрыты review; G156IN_PROGRESS,G02NOT_STARTED.

## G156 / ADR135 — SDK metadata integrity и candidate build,2026-11-18

ECC go-reviewer/architect/security/test-analysis применены как прочитанные инструкции и отдельные ограниченные задания. g02_prerequisite_plan автор patch/Go tests, pinned Go runtime; g02_python_contract_review независимый Go/code/test reviewer SDK, одновременно автор separate build/fixture (свои файлы исключены из verdict); g02_scope_security_review независимый read-only security/Go SDK/build reviewer. Root architect/integration/doc-updater/checklists + source inspection build. Native Claude commands/hooks/Go agents не подключались. Golang-testing skill файла в `.claude/skills` нет; компенсация доступным go-reviewer/behavioral TDD/race/vet/отдельными reviewers. Staticcheck отсутствует и не устанавливался.

SDK initial HIGH duplicate declarations и MEDIUM metadata-to-wire/mixedfamily bypass исправлены; два final APPROVE/open0 на exact ec453… . Behavioral RED исходного SDK3presence subFAIL; final normal/race11parents+134subPASS,vet2packages exit0,4locks unchanged. Source Git sparse/1452files/snapshot hash проверен; actualbuild/fixture NOT VERIFIED. Security build review выявил3MEDIUM (promisor freshfetch/Git env redirect/actual binary SHA), послеfixes/review CLOSED, два final source APPROVE/open0. Pure14passed, fresh scripted source acquisition PASS. Общий runtime передан от SDK автора build автору после cleanup, cold image build/provenance PASS278.63s. Actual fixture auth/control outcome MEDIUM gaps исправлены, два final source APPROVE/open0; pure14PASS, actual32PASS(24patched+8official,27deselected),35.70s. Временный runtime очищен/освобождён, owncache retained, по просьбе владельца работа остановлена до новой команды. Modelcalls/spend0, mainstack/officialimage не менялись. [Отчёт](increments/G02_bifrost_candidate_patch_REPORT.md), [review](reviews/G02_BIFROST_PATCH_REVIEWS.md). G156/SLICE/G02 не разблокированы.

## G156 / ADR134 — candidate boundary, native compatibility и runner, 2026-11-18

Применены architect/contract-first/TDD/Python/database/testing/security/silent-failure компетенции. `g02_prerequisite_plan` автор control/runner, `g02_python_contract_review` автор codec/probe/actual-Bifrost fixture; root автор client/relay/TLS/shared schema и интегратор. General cross-review только чужих файлов, отдельный `g02_scope_security_review` blind-first read-only по всем boundaries. Авторы не объявляются reviewers своих компонентов. Native slash commands/hooks не запускались. Root повторно прочитал doc-updater/verification-loop как checklists для context/evidence/ссылок/секретов; формальный набор каталога не запускался.

Исправлены contradictory settlement facts, split/interleaved secret export, TLS-file modes, known-VK echo, source discovery/bounds и malformed JSONL fd/flock; final security delta APPROVE/open0. Fast1281passed/4warnings,mypy191files,15importsKEPT; runner43passed с14realPG. Actual official Bifrost/fake upstream8passed **включает отказ на потере terminal fingerprint**: это открытый compatibility blocker, не SSE readiness. Primary-source SDK investigation использует только generic upstream URLs, без project data; SDK patch не применялся. Portable fixture own-image build и21cases PASS; independent security re-review закрыл MEDIUM pre-check ignorefile read, open0. Main stack/секреты/modelcalls не затронуты; Docker/PG по очереди. [Отчёт](increments/G02_candidate_egress_preparation_REPORT.md), [review](reviews/G02_CANDIDATE_EGRESS_REVIEWS.md). Full pre-pr/Linux CI и G156/live/profile acceptance не заявлены, G02 NOT_STARTED.

## G156 / ADR133 — ledger и независимое review, 2026-11-17

Отдельный g02_prerequisite_plan выполнил actual-code план и ограниченное авторство новых0024/poc_budget.py/mainPGtests; TDD RED missing module, затем real PG34passed. Root добавил отдельные process/restore cases, интеграцию/catalogue/snapshot и получил40PGpassed/fast957/actual drift-upgrades6. Mypy182files0issues,15importcontractsKEPT. Backend host/product gateway не подключены, calls/spend0.

Независимые blind-first read-only g02_python_contract_review (database/Python/code/tests) и g02_scope_security_review (security/code) проверили DDL до первого apply, frozen hash, модуль и обе тестовые дельты, final APPROVE/open0. Исправлены MEDIUM balance snapshot race и LOW malformed reason; owner/money authority не расширена. Авторы и reviewers различны, reviewers не запускали runtime и не читали author report до выводов. [Отчёт](increments/G02_flash_paid_ledger_REPORT.md), [review](reviews/G02_PAID_LEDGER_REVIEWS.md). Native Claude commands/hooks не запускались.

Security reviewer отдельно применил architect/silent-failure analysis будущего sole-egress A/privateTLS backendclaim vs B/offline signedpermit. Рекомендован A, выявлен replay reuse bodyhash; до apply добавлен permanent UNIQUE и future synthetic marker inside body. Это [read-only план§6](groups/G02_FLASH_ADMISSION.md#6-следующий-candidate-egress-seam-ограниченный-технический-план), PROPOSED/NOT_IMPLEMENTED/NOT_SECURITY_ACCEPTED, без Docker/modelcalls/внешней передачи projectdata; не заменяет ADR129 product enforcement.

## G156 / ADR132 — persistence, migrations и failure semantics, 2026-11-17

Отдельный `g02_prerequisite_plan`: planner/architect actual registry/IAM/persistence, затем ограниченное авторство0020/admission.py/PG tests. Root: integration, forward0021/22, migration/process/logical restore cases, snapshot и shared legacy gates. Использованы прочитанные database/Python/testing/security ECC instructions; native slash commands/hooks не запускались. Независимые blind-first read-only `g02_python_contract_review` (database/Python/code/tests) и `g02_scope_security_review` (security/code) оба final APPROVE/open0 после исправления pending generation barrier, restore CHECK и уточнения evidence. Reviewers не запускали Docker/runtime и не являются авторами проверяемых файлов.

Реальные targeted PG32passed; backend-check ruff0/mypy178files0issues/import15KEPT; full backend1901passed/3legacy failures, после обновления точных expectations affected+drift/upgrade11passed. Полный backend green, pre-pr/Linux CI не заявлены. [Отчёт](increments/G02_model_admission_persistence_REPORT.md), [протокол](reviews/G02_MODEL_ADMISSION_REVIEWS.md). Последующий0023 получил отдельные pre-apply и final database/Python/security APPROVE/open0; real PG56cases выполнил ограниченный автор, root выполнил fast957/actual drift-upgrades7 и вручную просмотрел snapshot271add/1deletion. Его code/evidence не засчитываются историческим0022review автоматически. Полный G156 и подготовка NOT VERIFIED, G02 NOT_STARTED до нового согласия.

## G02 / ADR131 — делегированный выбор и реализация0.2, 2026-11-17

`g02_prerequisite_plan` отдельно применил planner/architect read-only к концепции AI RES/DOC076§3.1/ADR128: обязательный expected fingerprint VALUE в scope, candidate ABSENT/NULL сохраняются, точные live values/profile не утверждены; поиск consumers подтвердил отсутствие runtime wiring. Root применил прочитанный TDD-workflow как checklist RED→GREEN (без ECC checkpoint commits/coverage-порогов вместо правил AI RES), сам изменил parser/test и создал schema0.2, историческую0.1 сохранил. RED5failed, GREEN121passed; verification-loop/doc-updater — scope, diff, версия, контекст. Нативные Claude commands/hooks не запускались.

Отдельные blind-first read-only `g02_python_contract_review` (Python/code/test/type) и `g02_scope_security_review` (code/security) проверили фактическую дельту до авторского отчёта: оба APPROVE/openfindings0. Security reviewer сам выполнил read-only schema/positive match+7negative smoke,exit0; другому reviewer запуск не приписывается. Planner не подменяет независимые review и human approval. Runtime/PG review не заявлены: в этой дельте их нет. Применимые проверки: fast957passed/4warnings,ruff0,mypy174files0issues,15contractsKEPT; contracts6/6+22passed; prompts40/0,secrets0,diff0,exit0. [Текущий отчёт](increments/G02_flash_admission_preparation_REPORT.md), [протокол](reviews/G02_FLASH_IDENTITY_REVIEWS.md). Полный G156/G02 NOT VERIFIED; живой профиль не включён.

## G02 / G156 — подготовка и первый отключённый срез, 2026-11-17

Отдельный `g02_prerequisite_plan` применил planner/architect read-only к текущим ADR128/129, DAG и фактическим llm seams; затем получил ограниченное авторство новых observed_identity.py/schema0.1/tests. Прочитанные python-patterns/python-testing/tdd-workflow/contract-first использованы как checklists; фактический RED missing-module exit2, затем targeted245passed (108new), scopedruff/mypy0. Он не reviewer своего кода. Root применил doc-updater/verification-loop к источникам, сохранности29initialfiles, paid plan, статическим проверкам и контексту; общие официальные provider docs без передачи проектного содержимого.

Отдельный `g02_scope_security_review`: blind-first/read-only code/security по плану/границам и затем actual3files, APPROVE/findings0; независимый read-only smoke3positive+8negative exit0. Отдельный `g02_python_contract_review`: blind-first/read-only Python/code/test/type разбор parser/schema, обязательный providerRequestRef и semantic-schema note исправлены; finalAPPROVE/openfindings0. Документационный earlyAPPROVE не выдаётся за review кода. Native Claude commands/hooks не запускались; runtime QA Worker/human acceptance не заменены. DB/runtime review не заявлены, их scope пока не реализован; они сохраняются для durable/transport фазы.

Root `make pre-push-fast` exit0: ruff0,mypy174files0issues,15importcontractsKEPT,944passed/4warnings/0failed/skipped; contracts-check6/6,contracts-test22passed. Полный pre-pr/LinuxCI/runtime/DB не выполнялись в промежуточном срезе, G156/G02 NOT VERIFIED. [Отчёт](increments/G02_flash_admission_preparation_REPORT.md), [review](reviews/G02_FLASH_IDENTITY_REVIEWS.md), [паспорт](groups/G02_WORK.md).

## G01 / S19 — 2026-11-17, выполнение

Отдельный `s19_plan`: planner + tdd-guide/pr-test-analyzer для плана; затем ограниченное авторство pure manifest/tests (python-patterns, python-testing, tdd-workflow как прочитанные checklists) и passport/ADR. `g01_architecture`: read-only нормативная разведка/architect, затем ограниченное авторство module-owned metadata readers, platform port, composition и их PG tests. Эти авторы не считаются независимыми reviewers своего кода. Root: TDD service/migration/negative suites, существующие команды Make/CI и verification-loop checklist; нативные Claude slash commands/hooks не запускались.

Отдельные blind-first/read-only `s19_review` (code-reviewer/python-reviewer/architect/pr-test-analyzer/type-design-analyzer), `s19_security` (security-reviewer/silent-failure-hunter), `s19_database` (database-reviewer/silent-failure-hunter, без Supabase). Initial findings: duplicate-ref integrity, failure audit и lock inversion; исправления и финальная дельта рассмотрены, openfindings0, APPROVE. Обязательные компетенции покрыты отдельными заданиями/checklists; команды /plan, /code-review, /python-review, /quality-gate, /test-coverage не объявляются нативно выполненными. Coverage-порог не заменяет DoD; pytest-cov отсутствует в lock, новую зависимость ради метрики не добавляли. [Review](reviews/S19_IMPLEMENTATION_REVIEWS.md), [report](increments/S19_context_package_versioning_REPORT.md).

## История исходного документирования групп ADR124 — 2026-11-17 (до G01/ADR127)

Документирование принятого владельцем подхода, без запуска продуктовых этапов. Отдельный read-only `parallel_plan` применил `planner` к DAG S17–S39, готовности S19/S35 и конфликтам Compose/runtime; результат — зависимости и кандидаты независимой работы. Root прочитал `doc-updater`/`verification-loop` и применил как checklists scope, источников, ссылок, статусов и секретов. Отдельный `group_review` применил `code-reviewer` blind-first/read-only к фактическому diff и новым файлам: APPROVE, findings 0; сценарии одного инкремента/группы/блокера/нескольких окон/остановки пройдены. Evidence, команды и неприменимость продуктовых suites — [DEVELOPMENT_GROUPS.md §7](DEVELOPMENT_GROUPS.md#7-проверка-документирования). Нативные Claude commands/hooks, продуктовый QA Worker и human approval не имитировались; пробелов обязательного набора узкой docs-задачи нет.

## Постоянный процесс Codex — 2026-11-17

Дополнение по отдельному поручению устранить Caddy CI blocker: `verification-loop` применён как checklist точного scope/registry comparison/digests/static/fast-tests/CI. Повторные отдельные blind-first reviewers `process_review` (`code-reviewer`) и `permission_review` (`security-reviewer` + evidence checklist) проверили однострочный index pin и неизменность Linux artifacts; оба APPROVE/0 findings. Тест на конкретное значение digest не добавлялся; существующие validators и новый CI сохраняются. Evidence/команды/counts/неудачная sandbox/LibreSSL попытка — завершающий раздел [отчёта](reviews/CODEX_PROCESS_REVIEW.md).

Окончательный выбор официального release variant `2.11.9-alpine` повторно проверен теми же двумя независимыми read-only reviewers blind-first: все 7 Linux descriptors и 7 attestations прежние, Windows исключены из выбранного индекса, поддержка multiarch и gates сохранены; оба APPROVE/0 findings. Успешный промежуточный CI `b02634f` отделён от обязательного нового CI окончательного FROM.

Документационная задача по семи решениям владельца, без запуска продуктового инкремента. `doc-updater` применён основным исполнителем как checklist сверки существующих документов с Git/кодом; `verification-loop` — явно прочитанный checklist применимых проверок (diff/ссылки/secret scan/быстрый слой, без переноса чужих команд или coverage-порога). Skill `openai-docs` прочитан для оценки механизма подстановки инструкций; вывод об усечении основан на фактически полученном reviewer фрагменте, не на обещании универсального лимита клиента.

Отдельные read-only агенты: `process_review` использовал `code-reviewer` + checklist `doc-updater` для независимой согласованности и dry run; `permission_review` — `security-reviewer` + evidence/severity `code-reviewer` для постоянных полномочий и approval границ. Blind-first: первоначальные выводы до авторского отчёта. Один MEDIUM по видимости §10 в автофрагменте исправлен bootstrap-указанием в начале AGENTS; повторная проверка — открытых findings нет. Runtime/API/DB review неприменимы: эти поверхности не менялись. Tests/CI не заменяются ECC; продуктовые статусы не повышены. Evidence, команды, counts и ограничения — [reviews/CODEX_PROCESS_REVIEW.md](reviews/CODEX_PROCESS_REVIEW.md).

ECC 2.2.3 (manual project-local install) — dev-time инструментарий (ADR-007; оценка — `reviews/ECC_TRUST_ASSESSMENT.md`). Иерархия: Registry/нормативные документы → `CLAUDE.md` и `.claude/rules/*.md` → ECC (`.claude/rules/ecc-precedence.md`). ECC agents — инструменты разработки, не Runtime Workers AI RES; не заменяют QA Worker и human approval.

Инвентарь (проверено 2026-11-10): 71 agents, 59 skills, 98 commands в `.claude/`; `.claude/rules/ecc/` (development-workflow, git-workflow, python-patterns); hooks не включены; MCP не подключены; нативных плагинов нет. Проектные `.claude/agents/` или `skills/` AI RES не создавались — потребности нет (существующие покрывают компетенции; пробелы ниже компенсируются процессом).

## 1. Карта компетенций → фактические имена

| Компетенция | Agents | Skills | Commands | Ограничения AI RES |
|---|---|---|---|---|
| Архитектура и планирование | `architect`, `planner`, `code-architect`, `code-explorer` | — | `/plan` | Нормативные решения — только владелец |
| Python / backend | `python-reviewer`, `fastapi-reviewer` (ADR-008), `type-design-analyzer` | `python-patterns`, `error-handling` | `/python-review`, `/fastapi-review`, `/build-fix` | — |
| PostgreSQL / миграции | `database-reviewer` | `postgres-patterns`, `database-migrations` | — | Только Alembic; RLS — transaction-local context, не Supabase |
| API / контракты | — (нет агента) | `contract-first`, `api-design` | — | Cursor pagination, RFC 9457; review — `code-reviewer` + `type-design-analyzer` |
| Temporal / LangGraph | — (нет агента) | `eval-harness` (агентные критерии) | — | Компенсация: `architect` + `silent-failure-hunter` + `python-reviewer` |
| Безопасность | `security-reviewer` | — | `/security-review` (встроенная), `/security-scan` (только с согласия: npm) | Внешние сервисы — с согласия владельца |
| Docker / CI / DevOps | — (нет агента); `build-error-resolver` для сборки | `production-audit`, `verification-loop` | `/quality-gate` | Компенсация: `security-reviewer` + `architect` |
| Тестирование / QA | `tdd-guide`, `pr-test-analyzer`, `e2e-runner` | `python-testing`, `tdd-workflow`, `e2e-testing`, `ai-regression-testing` | `/test-coverage`, `/react-test` | DoD — testing-and-verification.md, не 80% coverage |
| Независимое review | `code-reviewer`, `silent-failure-hunter`, `comment-analyzer` | — | `/code-review` (локально) | PR-режим — только с разрешения |
| Frontend | `typescript-reviewer`, `react-reviewer`, `a11y-architect` | `e2e-testing` | `/react-review`, `/react-build`, `/react-test` | `browser-qa` требует browser MCP — не используется |
| Retrieval / evaluation | `rag-pipeline-reviewer`, `mle-reviewer` | `eval-harness` | — | Пороги — OD-02 |
| Performance | `performance-optimizer` | — | — | SLO — OD-02 |
| Документация | `doc-updater` | — | — | Не менять `docs/architecture/` |
| Запрещено без решения владельца | — | `architecture-decision-records` (docs/adr), `continuous-learning*`, `ck`, `delivery-gate`, `plankton-code-quality`, `loop` | `/auto-update`, `/loop-start`, `/evolve`, `/learn*`, `/instinct-*` | ecc-precedence.md |

Обязательный набор на каждый этап задан в промпте этапа (раздел 8).

## 2. Журнал использования

S16 owner closeout (2026-11-17, только implementation docs): doc-updater и verification-loop повторно прочитаны и применены root как checklists статусов/evidence/ссылок/секретов/scope. Отдельный s16_security — blind-first read-only оценка уточнённого milestone и границ приёмки до авторской дельты, затем actual14Markdown review и delta recheck: MEDIUM по ROADMAP reasons/color исправлен, финал APPROVE/openfindings0. DONE по owner decision, real provider NOT VERIFIED и NCP-16 PROPOSED согласованы; live/SLICE/release gates не сняты. После verdict добавлены только протокол/точные checks; evidence — S16_IMPLEMENTATION_REVIEWS/report§17. Обязательные роли кодового S16 уже применены в записи ниже; код/config/API/DB не меняются, повтор runtime review/pre-pr для Markdown неприменим. Нативные Claude commands/hooks и новый product approval не заявляются.

S16 implementation (2026-11-17, продолжение того же этапа): planner/architect и официальные pinned-source исследования применены до независимого кода; python-testing/tdd-workflow — прочитанные checklists с RED/GREEN у исполнителей. code-reviewer/python-reviewer/pr-test-analyzer — reciprocal review чужих файлов (`s16_arch` исключил свои relay/gateway, `s16_docs_review` исключил свой adapter); отдельный `s16_security` выполнил security-reviewer/silent-failure-hunter по всему срезу и delta review исправлений. tdd-guide (`s16_plan`) — retrospective test-design review и4/4 isolated mutations, собственный renderer исключён. Thread limit не позволил новый reviewer thread, компенсировано доступными отдельными reviewers без самопроверки вместо независимости. Два MEDIUM (Unicode parsing и порядок no-paid guard) исправлены; открытых findings0 на отключённом срезе. Verification-loop/doc-updater — checklist root: pre-pr exit0, все8 Linux push/PR checks153e3bb success, PR #28 MERGED091b976, tree equality. Evidence-only closeout не меняет code/config/security boundaries: отдельное новое runtime review не требуется; применяются prompts/link/secret/diff checks и contracts CI, post-merge CI фиксируется в отчёте по его SHA. Нативные slash commands не запускались; профиль, immutable exception и production-like Bifrost не утверждены. Полный evidence — [S16_IMPLEMENTATION_REVIEWS](reviews/S16_IMPLEMENTATION_REVIEWS.md), S16 report. Ранний preflight ниже — история до кодовой реализации.

S16 preflight (2026-11-17, документационный checkpoint, не завершение S16): `planner` (`s16_plan`) — отдельное read-only планирование по промпту; `architect` (`s16_arch`) — независимая оценка pinning/identity/egress и повторная сверка local-model scope; `security-reviewer` (`s16_security`) — blind-first проверка immutable guarantee до отчёта автора. Вывод: immutable selection в документированном API не подтверждён, требуется NCP-16; local-model не блокирует первый срез. `doc-updater` и skill `verification-loop` явно прочитаны/применены исполнителем как checklist ссылок, точности статусов и evidence (без Claude slash commands/hooks). Общее review docs-дельты и security delta — [S16_PREFLIGHT_REVIEWS](reviews/S16_PREFLIGHT_REVIEWS.md). Python/TDD/failure/test роли и skills кодовой реализации пока не применялись: нового кода нет, обязательный набор S16 остаётся на продолжение. Context7/Serena не экспонированы в этой сессии; официальные provider docs и локальное чтение компенсируют навигацию. Никаких project content/credentials во внешние docs-сервисы не передавалось. Runtime acceptance и человеческое approval этим не заменяются.

DEP-01 docs-only закрытие (2026-11-17): `verification-loop` повторно прочитан и применён исполнителем как checklist точности evidence, scope/diff, prompts и secrets; runtime/config не меняются, отдельный reviewer не требуется по AGENTS §7. DONE отражает прямое решение владельца; hosted App не объявляется VERIFIED. Ссылки и команды — DEP report §16.

DEP-01 (2026-11-17): `planner` — отдельное read-only исследование до реализации (native pep621/uv.lock, custom pins, source/image связность и ограничения security alerts). `verification-loop` — явно прочитанный checklist исполнителя. `code-reviewer` + `security-reviewer` — два отдельных blind-first read-only review и отдельный проход финальной дельты HADOLINT/actionlint: 0 findings. Реальные методы применения — Codex agents/checklist, нативные Claude slash commands/hooks не запускались. `plugin-management` — прочитанный skill и фактический поиск доступного механизма установки App; неподключённые GitHub/TinyFish не считаются доступными и не подключались. Обязательный набор промпта применён; runtime DB/Temporal review неприменимы. Evidence — [DEP-01 review](reviews/DEP-01_REVIEWS.md) и отчёт.

| Этап | Инструмент | Зачем | Результат |
|---|---|---|---|
| S00 | — (собственная работа) | Сверка Registry/SHA-256 и валидация контрактов — подходящего ECC инструмента нет | S00 report |
| S00 | `architect` | Независимое review пакета S00 | 15 замечаний (3 HIGH), все учтены (S00 report §7) |
| PREP | инвентаризация `.claude/` (agents/skills/commands/settings/install-state) | Проверка фактической доступности и trust assessment | `reviews/ECC_TRUST_ASSESSMENT.md` |
| PREP | `architect` | Независимое review roadmap, ADR и промптов | 14 замечаний (4 HIGH), `reviews/PREP_PHASE_REVIEW.md` |
| PREP | `database-reviewer` | Review persistence-решений (ADR-011…016, ADR-024) и промптов S04–S06 | см. `reviews/PREP_PHASE_REVIEW.md` |
| PREP | `security-reviewer` | Review security-решений (ADR-015, 017, 020, 022, 031) и промптов S03, S07, S16 | см. `reviews/PREP_PHASE_REVIEW.md` |
| S01 | `code-reviewer`, `silent-failure-hunter` | Независимое review contracts toolchain | 5 HIGH + 8 MEDIUM, исправлено; `reviews/S01_REVIEW.md`. `planner`, `architect`, `verification-loop` не использованы (отклонение, S01 report §8) |

## 3. Дополнительные инструменты (ADR-040)
SessionStart hook `session-brief`, `CONTEXT_HANDOFF.md`, Context7 MCP (через ECC `docs-lookup`), Serena MCP (совместно с `code-explorer`, `code-reviewer`). Промпты и ограничения — `tooling/`. ECC `ck` и `strategic-compact` hook не включались (глобальные записи / скрипт не установлен).
| S02 | `fastapi-reviewer`, `security-reviewer`, `type-design-analyzer` | Независимое review platform primitives | HIGH исправлены, `reviews/S02_REVIEW.md`; повторное review не проводилось |
| S03 | `security-reviewer`, `architect`, `silent-failure-hunter`, `code-reviewer` | Независимое blind-first review инфраструктуры (ADR-037 слой 2); DevOps-агента в ECC нет — компенсация: `security-reviewer` + `architect` | результаты и устранение — `reviews/S03_*.md` |
| S03 | `planner`, `verification-loop`, `production-audit` | `planner`/`/plan` заменены планом по срезам, согласованным с владельцем; `verification-loop`, `production-audit` не запускались | отмечено в S03 report |
| S04 | `code-reviewer`, `database-reviewer`, `security-reviewer`, `silent-failure-hunter` | Независимое параллельное read-only review (ADR-035); `database-reviewer` — с учётом ecc-precedence (без Supabase-RLS) | CRITICAL/HIGH — 0; MEDIUM/LOW исправлены или записаны в gaps, `reviews/S04_REVIEWS.md`; повторного прохода агентов после исправлений не было |
| S04 | `planner`, `architect`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`; skills `python-patterns`, `python-testing`, `tdd-workflow`, `postgres-patterns`, `database-migrations`, `verification-loop`; commands `/plan`, `/code-review`, `/quality-gate`, `/python-review`, `/test-coverage`, `/security-review` | **Не запускались** (требовались промптом §8). Компенсация: план по вертикальным срезам согласован внутри сессии; тесты писались вместе с кодом и проверены мутациями; профильные проверки Python — ruff/mypy --strict/import-linter; полнота тестов — `silent-failure-hunter` (вакуозные тесты) вместо `pr-test-analyzer`; соответствие архитектуре — прямая сверка с DOC-068/072 и ADR в review `database-reviewer`; `/security-review` заменён `security-reviewer`. Отклонение от порядка применения промпта фиксируется здесь и в отчёте | отмечено |
| S06 | `database-reviewer`, `silent-failure-hunter`; навыки `postgres-patterns`, `database-migrations` — как ориентир, без запуска skill-инструментов | Независимое read-only review (ADR-035); `database-reviewer` с учётом ecc-precedence (без Supabase-RLS). `planner`, `architect`, `code-reviewer`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, `type-design-analyzer`, `/plan`, `/quality-gate`, `/test-coverage`, `verification-loop` в этой сессии НЕ запускались: компенсация — тесты вместе с кодом, `make pre-pr`; пробел отмечен в reviews/S06_REVIEWS.md §3 | database-reviewer: 1 CRITICAL, 4 HIGH, 6 MEDIUM, 6 LOW — CRITICAL/HIGH устранены или вынесены в G-72/OD-14 (reviews/S06_REVIEWS.md) |
| S07 | Агенты не запускались (по умолчанию проекта — только по просьбе пользователя); навыки как ориентир без запуска инструментов: `python-testing`, `tdd-workflow` (порядок «тест → код»), `postgres-patterns`/`database-migrations` (миграции 0012–0013), `api-design`/`contract-first` (overlay) | Реализация и самопроверка выполнялись inline (TDD, реальный PostgreSQL 16, мутационные проверки на ключевых инвариантах: advisory lock, mfa-pending) | Независимое review слоя 3 ADR-037 (`security-reviewer`, `code-reviewer`, `python-reviewer`, `silent-failure-hunter`) **не проведено** — ждёт согласия пользователя; статус S07 из-за этого не выше TESTED (`reviews/S07_REVIEWS.md`) |
| S08 | `security-reviewer`, `code-reviewer`, `silent-failure-hunter` (blind-first, read-only) | Независимое review слоя 3 ADR-037 (граница безопасности: матрица политик, разрешение проекта) | `reviews/S08_REVIEWS.md`: CRITICAL 0, HIGH 1 (ETag) исправлен; остальное исправлено или в G-87/G-88/OD-17. Не запускались: planner, architect, fastapi/python-reviewer, tdd-guide, pr-test-analyzer — компенсация inline (TDD, мутационные проверки) |
| S10 | `code-reviewer`, `database-reviewer`, `silent-failure-hunter` (blind-first, read-only) | Независимое review (ecc-precedence п. 2: миграция с RLS/ролями/триггерами, fail-closed доставка) | `reviews/S10_REVIEWS.md`: CRITICAL 0, HIGH 0, замечания исправлены или в G-98…G-103; `planner`/`architect`/`tdd-guide`/`python-reviewer`/`pr-test-analyzer` не запускались |
| S11 | `security-reviewer`, `silent-failure-hunter`, `architect`, `code-reviewer` (blind-first, read-only) | Независимое review (ecc-precedence п. 2: граница безопасности — service-аутентификация и изоляция Runtime, fail-closed доставка; Temporal/LangGraph-специалиста в ECC нет — компенсация `architect` + `silent-failure-hunter` по ECC_USAGE §1) | `reviews/S11_REVIEWS.md`: CRITICAL 0; HIGH сведены к 3 группам (застревание Operation, авторизация Temporal, зависание воркера) — исправлено/зафиксировано (G-104, G-107); `planner`, `database-reviewer`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer` не запускались (изменение SQL ограничено одним фильтром, покрытым тестами; причина пропуска — отчёт S11 §11) |
| S12 | `security-reviewer`, `silent-failure-hunter` (blind-first, read-only) | Независимое review (ecc-precedence п. 2: SSE/ACL, проверка загрузки, fail-closed отмена) | `reviews/S12_REVIEWS.md` |
| S13 | `code-reviewer`, `security-reviewer`, `silent-failure-hunter`, `architect` (blind-first, read-only) | Независимое review (промпт этапа; границы redaction/fail-open, алерты) | `reviews/S13_REVIEWS.md` |
| S14 | `database-reviewer`, `silent-failure-hunter`, `code-reviewer` (blind-first, read-only) | Независимое review (ecc-precedence п. 2: миграция с FK/триггерами и RLS-исключениями, fail-closed валидация); `planner`/`architect`/`tdd-guide`/`python-reviewer` из промпта не запускались — план по срезам и тесты до кода выполнены исполнителем | `reviews/S14_REVIEWS.md`: CRITICAL 0, HIGH 2 (исправлен / граница Gate), MEDIUM исправлены, кроме OD-20 |
| S15 | `code-reviewer`, `security-reviewer`, `silent-failure-hunter` (blind-first, read-only) | Независимое review (DoD промпта; граница безопасности: охрана исходящих промптов, egress, fail-closed бюджет) — CRITICAL 0, HIGH 5 исправлены; `planner`/`architect`/`tdd-guide`/`python-reviewer`/`pr-test-analyzer`/`database-reviewer` не запускались — план и TDD самостоятельно, мутационная проверка тестов; БД-часть (одна справочная таблица по образцу 0016) покрыта интеграционными тестами и security-review | `reviews/S15_REVIEWS.md` |
| ARCH-01 | `architect` (отдельный Codex-агент, read-only) | Исследование до реализации: фактический граф импортов, canonical модульные границы, установленный import-linter/grimp, состав слоёв и защита новых модулей | 14 модулей, 17 edges/9 направлений, циклов нет; уточнение ADR-120; `reviews/ARCH-01_REVIEWS.md` |
| ARCH-01 | `code-reviewer`, `pr-test-analyzer` (два отдельных Codex-агента, blind-first/read-only) | Общее review и профильная проверка чувствительности architecture gate; без отчёта автора и результатов друг друга | Оба — 0 findings; test reviewer обнаружил 3/3 мутации (`exhaustive=false`, peer ignore, обратный порядок layers); `reviews/ARCH-01_REVIEWS.md` |
| ARCH-01 | `verification-loop` (явно прочитанный ECC skill/checklist, вручную) | Makefile/CI → lint/types/tests → secret scan → diff → точный SHA/evidence; без Claude slash command/hook | Результаты в отчёте ARCH-01; security/DB review не требуется: runtime boundaries, SQL/RLS, crypto, migrations не меняются. Пробелов обязательного набора нет. |


S19 closeout: тот же независимый s19_review проверил staged docs после завершения source findings:74 local file targets/0missing; duplicate G157 MEDIUM исправлен, pool-pressure и старый runtime snapshot уточнены. Старый lock-order mutant воспроизвёл DeadlockDetected2/2. Full pre-pr и Linux head/post-merge counts/links сохранены в report; docs-only closeout не приписывает старый CI своему SHA. S18 только read-only planner и предварительный architect/security design assessment, без кода/новых production grants до закрытия S19.


## S18 — фактическое применение, 2026-11-17

Planner/TDD/type-design и Pythonpatterns/testing: отдельный bounded author types/DSL+security acceptance, RED→GREEN и strict immutable invariants. Architect: отдельный author pure engine/validation, canonical I0–I4/hierarchy/exceptions assessment; это author self-check, не independent review. Database competency: отдельный author owned storage/migration/RLS/previous-upgrade tests. Root: application composition/current Policy/session, exact refs/audit/idempotency, acceptance integration и verification-loop checklist. Native Claude slash commands/hooks не запускались; `/plan`, `/python-review`, `/code-review`, `/quality-gate` использованы как явно прочитанные процедуры, не как фактически вызванные команды. Numeric coverage не измерялось (pytest-cov вне lock); behavioral positive/negative cases и import constraints — evidence, не substitute всех gates.

Independent blind-first general/code/Python/types/pr-test-analyzer/architect, security/silent-failure и новый database reviewer отделены от авторов. Финальные findings/hashes/команды — [review](reviews/S18_IMPLEMENTATION_REVIEWS.md), [report](increments/S18_rules_registry_rules_engine_REPORT.md). Финальная приёмка:186targeted,pre-pr exit0,all8sourceLinuxchecksSUCCESS;3independentAPPROVE/openfindings0. ECC не заменяет эти gates. ЗакрытиеG01 доставляется в PR33, без отдельного docsPR.


## Уточнение группового цикла ADR127 — 2026-11-17

По прямому текущему поручению владельца root применил прочитанные doc-updater/verification-loop инструкции как checklists согласованности процесса, scope, evidence и ссылок. Native Claude commands/hooks не запускались. Отдельный read-only reviewer проверяет новую редакцию на сохранение внешних DONE/DoD/product security и отсутствие обязательного per-stage full-cycle барьера. Старые записи parallel_plan/group_review выше относятся к исходному документированию ADR124, не к фактическим запускам текущего уточнения. Gates продуктового кода не заменяются docs review; source7dd8475 не меняется.

ADR127 final independent process review: APPROVE/openfindings0,15files/176links0missing; уточнена точка проверки внешних зависимостей перед соответствующим Sxx. [Evidence](reviews/GROUP_PROCESS_ADR127_REVIEW.md). Root check_prompts40/0,8groups23stages compositionunchanged,secret0,diffcheck0. Product tree unchanged; повторный локальный backend для docs-only scope не запускался.

## NCP-16 B — решение владельца, 2026-11-17

Root прочитал doc-updater и verification-loop, применил как checklists источников/версий/evidence/границ. Отдельный g02_dependencies применил architect/planner read-only к normative impact: три v1.1, сохранение bootstrap Registry, новый полный manifest и неизменные шесть machine mirrors. Машинная схема остаётся pending design; runtime guards не ослаблялись. Независимый ncp16_security_review выполнил security/code/docs blind-first review и delta recheck: исправлен1LOW, финал APPROVE/openfindings0;26files/133links/74canonical/73hashes. Протокол reviews/NCP16_EXCEPTION_REVIEW.md. Native Claude commands/hooks и runtime verification не заявляются.

## OD-19 / ADR-129 — 2026-11-17

Root применил прочитанные architect/doc-updater/verification-loop как checklists совместимости, источников и evidence. Отдельный g02_dependencies: planner/architect read-only по existing service tokens/internal API/domain audit/roles/retries; отдельный od19_temporal_feasibility: pinned official Temporal1.29.7/SDK1.36.0 research без project-content egress, выявлены недостаточность defaultAuthorizer/queue-onlyACL и ранний token parse до custom interceptors. Выбраны неизменный task-token format и issuance receipts, а не неподтверждённый MAC-wrapper. Отдельный ncp16_security_review выполнил blind-first security/architecture review ADR129 до отчёта автора: два MEDIUM (вложенные Workflow Commands и Start intent authorization seam) исправлены; final delta APPROVE, open findings0. Протокол reviews/OD19_RUNTIME_AUTH_REVIEW.md. Native Claude commands/hooks и runtime/paid tests не выполнялись.

## G156 — конкретные runtime/CI исправления и реальные наблюдения,2026-11-18

Root — operator/integrator/реальные guarded probes; прежние python-testing/verification-loop
checklists, без native Claude hooks/commands. executor_plan — source diagnosis и автор
minimal candidate idle/routing fixes; его Go-reviewer инструкции применены как author
checklist, Go skill в каталоге отсутствует (компенсация pinnedsource+Go/native checks).
executor_normative — независимые security/Go/DB reviews + metadata-only actualruntime
inspect:18enabledchecks/10DNSdelta; launch_general — независимый general/Go/CI review.
Securityreviews не читали secretvalues/responsecontent и не делали providercalls.

CI896 nativeDockerpath8FAIL corrected; abe cancelled20m, не PASS. Workflow45m+
verbose/faulthandler diagnostics reviewedAPPROVE; 504 LinuxalljobsPASS. No tests
removed/skipped. Root realTEXT/JSON/TOOL/SSE stableidentity+knownusage; CANCELlate
UNKNOWNreserve measured, TIMEOUTnotobserved explicitly. Technicalevidence не human
approval/immutablepin. Runtime15minSQL_DRIFT isolated to unusedroutingregistry
complexity_semantic_generations and distributedlocks; exact3filefix reviewed
APPROVE/open0 by2non-authors, modulepins+fullSQLguard preserved. Root affected
build/Go/native+longidle/newexactCI pending; do not claim verification before results.

Ownercheckpoint: author executor_plan produced14file observedport draft separately,
1495purePASS/Ruff/mypy/importsPASS, butscopeauditfoundHIGHreverseSSEdrift. Perowner
context-update steering no furtherfix/newworkstarted. Root preservedidentical14hashes
inlocalWIPcommit3733825, nointegration/publication. Thisis NOTindependentreview or
VERIFIED. Firstcontinuation mustfixfinding+regression thenuseindependentgeneral/
securityreview. Roottechnical38CI+922.37shealth evidence doesnotcoverthisdraft.

## G02 / S17–S20 · 2026-11-18

- planner: отдельное read-only планирование S17, каталог, точные grants,
  уровень интеграции и тесты, затем источники и порядок PoC Temporal.
- architect: отдельная проверка границы ADR-129 и необходимости owner decision
  для role map/internal contract, определение независимой проекции S20.
- code-reviewer, python-reviewer, database-reviewer, pr-test-analyzer:
  независимое read-only review миграции, lock order, реального PostgreSQL,
  вызовов и идемпотентности. После исправлений срез S17 и проекция S20 APPROVE.
- security-reviewer, silent-failure-hunter: независимое review per-call
  authorization, MCP/scopes, errors и audit. Повторное APPROVE среза S17.
  Отдельный просмотр ar2/DOC-084 и изоляции PoC дал конкретные корректировки.
- tdd-guide: отдельный исполнитель контрактных тестов DOC-084, 7 PASS.
  Корневой исполнитель применил Python patterns/testing, проверку типизированных
  ошибок и verification-loop к локальным conformance и PostgreSQL тестам.
  Claude slash commands не запускались, использованы `make` и locked pytest.

## G02 / S20–S21 · 2026-11-19

- Architect проверил Process/UX/Manager Concept и закрытую схему DOC-085 v0.3.
  Различены серверный журнал, обязательная проактивная выдача и передача
  предыдущих ответов для reasoning. Отдельное изменение контракта в NCP-14
  ожидает владельца.
- Planner прочитал Makefile, Compose runtime fixtures и PoC checks. Полный
  pre-pr использует общий project, порт, подсети и образы, поэтому нужен
  изолированный Docker daemon с локальным loopback.
- Security reviewer двумя read-only проходами проверил native Task issuance,
  смешение scope, SDK metadata и наблюдение terminal. Подмена scope закрыта
  сверкой digest, статус — проверкой текущего доменного исхода. Poll и вложенные
  protobuf fields получили allowlists и отрицательные тесты, совместный native
  прогон exit 0. Финальный security review всего диффа остаётся в DoD.
- Code reviewer подтвердил необходимость отделить `201` решения человека от
  подготовки длительной Operation и обнаружил отказ при повторе после новой
  PlanVersion. Отдельный обработчик события и replay существующей связи прошли
  4 проверками PostgreSQL/Temporal с exit 0.


## S20 · продолжение 2026-11-19

- `tdd-workflow`, `python-testing` использованы как локальные чеклисты для
  PostgreSQL, схем и Temporal. Отдельно воспроизведён вызов после отмены до
  повторной проверки и подтверждён исправленный case.
- `verification-loop` использован как чеклист статических, целевых и
  контрактных проверок, проверки diff и сканера. Целевые Compose и CI gates
  ожидают общего результата G02 и изолированного runtime.
- Отдельные read-only агенты `g02_local_review` (code-reviewer, python-reviewer)
  и `g02_security_review` (security-reviewer) проверили локальный срез blind-first
  и перепроверили исправления. Итог 0 CRITICAL/HIGH локального scope.
  [Review](reviews/G02_S17_S20_REVIEWS.md). Профильное review развёрнутого
  стека остаётся частью общей приёмки. Claude slash commands не запускались.
