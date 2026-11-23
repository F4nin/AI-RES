# G02 — Инструменты и планирование Manager

## Общая приёмка S17/S20/S21 · 2026-11-24

Группа **IN_PROGRESS**, фаза доставки проверенного среза через draft PR.
Ветка `feat/g02-tool-registry-manager`, база `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
Локальная приёмка включает реальный PostgreSQL, Temporal и защищённую
Compose-топологию на синтетических данных. Манифест 1 225 файлов за пределами
`docs/implementation/` совпал с проверенным срезом Ubuntu по SHA-256
`45f926e55a62ad0a89e8c73eeb8daa1cf520014bb149c7215c1f496fa397a449`.

| Этап | Проверенная функциональность | Отчёт |
|---|---|---|
| S17 | Реестр инструментов, per-call Policy, точные Run grants и allowlisted MCP | [S17](../increments/S17_tool_registry_tool_gateway_REPORT.md) |
| S20 | Назначенный Manager Run, точный вход, Proposal, персональная лента и проверка полномочий | [S20](../increments/S20_project_epic_intake_manager_REPORT.md) |
| S21 | Неизменяемая PlanVersion, отдельное утверждение, исполнение Task, отмена и replay | [S21](../increments/S21_plan_task_orchestration_REPORT.md) |

Полный `make pre-pr` в Ubuntu завершился с exit 0. Локальные G1–G9
и ограничения покрытия приведены в отчётах этапов и
[независимом review](../reviews/G02_S17_S20_REVIEWS.md).

Перед доставкой на Darwin arm64 (Python 3.13.5, uv 0.11.31)
`make pre-push-fast` вернул exit 0, 1984 passed, 3 предупреждения OTel,
15 import contracts. `git diff --check`, `actionlint -color` и
`python3 -B infra/scripts/scan_secrets.py` прошли, находок 0. Registry
содержит 78 canonical путей без пропусков и дублей.
Проверка staged diff выявила только 19 Markdown-переносов с двумя
пробелами в заголовках версий стратегии PostgreSQL и отчёте S21.
С `-c core.whitespace=-blank-at-eol` она вернула exit 0.
`python3 -B docs/implementation/tools/check_prompts.py` вернул exit 1
с теми же 14 замечаниями к формату `SLICE-01_requirements_experiment.md`
в рабочем дереве и в чистом архиве базового HEAD. К промптам G02 замечаний нет.

Для завершения доставки нужен Linux CI на SHA PR. Для включения штатного
producer нужны целевая приёмка G-107 с явным allowlist, допуск точного входа
и managed-профиля `MANAGER_INTAKE` через MFA и применение лимита OD-21 через
G-145. Платные вызовы в этой проверке отсутствуют.

## Контрольная точка G02 · ADR-184/185 · 2026-11-24

На временном PostgreSQL репетирован переход stock → native → stock.
Проверяется drain старой Activity, сохранность завершённых историй и откат
до допуска новых назначенных Run. Native защищённо отклоняет старый запуск
без assignment. Программная сборка Manager использует mTLS и ar2, требует
отдельно переданные контекст и управляемый `LLMGatewayPort` и проверяет точный
текст v0.5. Глубокая пагинация уведомлений получила два проверенных B-tree
диапазона. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

Native образ пересобран на Go 1.27.4 с проверяемыми модулями Temporal 1.29.7.
Сборка прошла отдельный блокирующий скан Trivy с подтверждённым инвентарём
139 Go-пакетов и 0 исправляемых HIGH/CRITICAL. Эта проверка включена в CI.

G02 **IN_PROGRESS**. Итоговый общий `make pre-pr` прошёл в Ubuntu VM
с отдельным Docker Engine. Запись Manager/Proposal/Plan повторно проверяет
сессию и Policy под блокировками. Остаются допуск точного входа и
managed-профиля `MANAGER_INTAKE`, применение бюджета через G-145,
приёмка G-107 перед штатным producer и Linux CI точного SHA доставки.

## Защищённый контур и персональная доставка · 2026-11-23

ADR-183 подключает отдельный Compose с native Temporal, защищёнными Platform,
assigned delivery и Dispatcher. Dev credentials переиспользуют нужные
значения базового SOPS-пакета. Сетевой сценарий на временном PostgreSQL
проверил approval consumer, доставку, отмену и сверку Plan после ACK.
Серверная лента ADR-182 использует персональную RLS-проекцию,
точные доменные ссылки и отдельный trusted schedule. Её реализация и
локальное evidence записаны в [S20](../increments/S20_project_epic_intake_manager_REPORT.md).

G02 **IN_PROGRESS** на `feat/g02-tool-registry-manager` от `7f0c29f`. Для общей
приёмки остаются включение штатного Manager и producer после допусков,
проверка перехода с существующей Temporal history, итоговый целевой G-107,
`make pre-pr` в изолированном окружении и точный Linux CI. v0.4 применяет ADR-161.

## Native Temporal и решения S20 · ADR-181/182 · 2026-11-23

Ветка `feat/g02-tool-registry-manager`, база `7f0c29f9519217dba722ad1f5b6396d8a02216da`,
сохранён исходный рабочий diff. Native runtime image, приватный bind Platform и
отдельный Compose smoke локально **TESTED**. Проверены frontend+internode mTLS,
допуск leaf и отзыв на открытом соединении, рестарт с тем же namespace,
regression Manager/Plan и подтверждённый replay исчерпанного Start.
По делегированию владельца MVP канал уведомлений выбран: персональная лента
Workspace. Выдача истории v0.4 ограничена подтверждённым источником по ADR-161.
G02 **IN_PROGRESS**: штатные mounts/identities, сквозная проверка standalone
образа с Platform, защищённый Backend delivery и reconciliation, персональная
доставка, общий pre-pr и Linux CI. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Явный allowlist reconciliation · ADR-180 · 2026-11-21

`BoundStartSchedule` задаёт уникальный набор назначенных типов Operation;
`include_post_ack` включает дополнительную фазу, не меняя этот набор.
Legacy-конфигурация допускает только `MANAGER_MESSAGE`; Plan явно выбирает
`PLAN_EXECUTION`. Loader отклоняет повторяющиеся JSON-ключи. Ruff, mypy,
17 unit tests, PostgreSQL/Temporal Plan post-ACK test, combined native
Plan+Manager-timeout candidate и два независимых APPROVE завершены.
G-107, штатный protected wiring и общие gates остаются открытыми.

## Изоляция ключа назначенной доставки · ADR-179 · 2026-11-21

## Изоляция ключа назначенной доставки · ADR-179 · 2026-11-21

Dev secret tooling производит отдельный seed Dispatcher и отдельный
публичный allowlist, Backend listener читает только этот allowlist.
Общий service-token реестр не расширяется. Upgrade старых dev secrets
сохраняет существующие значения; неполные/несогласованные пары отклоняются.
Backend и infra focused checks прошли, изолированный native candidate прошёл,
два независимых review APPROVE. G02 **IN_PROGRESS**: mounts Compose,
штатный native Temporal wiring, G-107 и общие gates остаются открыты.
[ADR-179](../ARCHITECTURE_DECISION_LOG.md), [отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Межпроцессная доставка · NCP-19

DOC-087, DOC-068 v1.7 и 0054 закрепляют отдельную ar2-границу.
Два отдельных процесса проверяют имя назначения, подпись, nonce,
lease и exact Temporal Run. Тестовые процессы используют разные
DB-роли и конфигурацию. Открыты изоляция secret и сети в целевом
стеке, история v0.4, уведомления и общий цикл приёмки.
G02 **IN_PROGRESS**. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Backend-композиция назначенной доставки · ADR-177

На изолированном PostgreSQL и Temporal Dispatcher использует
`AssignedDeliveryBackend` для допуска Start, привязки Run и Cancel.
Доставочная и Backend DB роли проверены отдельно. Межпроцессное
подключение ожидает NCP-19 по приватной передаче и проверке lease.
G02 **IN_PROGRESS**. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Namespace назначенной доставки · ADR-176

0053 хранит точную привязку Start и Cancel в Outbox. Миграция
разрешает исторические маршруты и изолирует недоказанные в карантине.
Изоляция claim, истёкших lease и replay проверена на PostgreSQL.
G02 **IN_PROGRESS**. Для штатного контура остаётся отдельное
подключение доставки и доверенного Backend prepare/bind.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Привязка Proposal к состоянию Epic · 2026-11-21

ADR-175 локально проверен. Новый private v5 и миграция 0052 сохраняют
неизменяемый контекст точного назначения и Run. Ссылка входит в Proposal
и хеш для человеческого решения. В isolated native Temporal проверены
реальная запись и отсутствие контекста в History. PostgreSQL проверил
повтор выдачи и отказ legacy после выдачи. G02 **IN_PROGRESS**.
Штатный защищённый контур, текстовый допуск v0.4, доставка уведомлений
и общая приёмка открыты. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Минимальный запрос контекста Epic · 2026-11-21

ADR-175 получил узкую PostgreSQL-проекцию с проверенными границами
чтения. В NCP-18 подготовлены условия private v0.5 и минимальных SQL-прав.
После указания на выпуск новых редакций DOC-086 и DOC-068 можно
подключать приватный контур и сохранять provenance Proposal. Статус
**IN_PROGRESS**. [Evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## Решения о повторе и контексте · 2026-11-21

ADR-174 закрепляет подтверждение конкретной записи Start в карантине
действующим администратором её проекта с MFA. ADR-175 ограничивает
состояние Manager метаданными назначенного Epic. Сохраняются отдельные
человеческие решения по Proposal и PlanVersion. Открыты private API
и привязка Proposal, доставка уведомлений, штатные процессы,
`make pre-pr` и Linux CI. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Отмена до ACK, группировка и версия Epic · 2026-11-21

ADR-171 подтверждает точную отмену до ACK в PostgreSQL. ADR-172 проверяет
объединение допущенных событий, срочность и интервалы, ADR-173 добавляет
воспроизводимую внутреннюю версию Epic. Открыты штатный replay, включение
версии Epic в Proposal, доставка сводок, история v0.4, штатное
подключение и общая приёмка. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Начальный Run и отмена назначения · 2026-11-21

ADR-168 добавляет отдельный mTLS-допуск точного сигнала отмены. ADR-169
подтверждает исходный Run после потери Start reply через закреплённую
identity диспетчера. ADR-170 сохраняет порядок отмены до допуска, между
допуском и binding и после привязки Run. PostgreSQL и native Temporal
используются через изолированный Compose-кандидат.

Plan Run проверен после материализации утверждённой задачи. Защищённая
отмена завершает Operation в `CANCELLED`, сохраняет связку утверждённого
пункта с Task и проходит replay. [Отчёт S21](../increments/S21_plan_task_orchestration_REPORT.md).

Группа **IN_PROGRESS**. Открыты G-107 для исчерпанной доставки без
подтверждённого Run, штатные сервисы и identities, использование проекции
Manager, доказанный v0.4 context, проактивность, `make pre-pr` и Linux CI.
[Evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## Человеческое решение Proposal и диспетчеризация · 2026-11-21

ADR-166 закрывает вопрос роли по делегированию владельца. В публичном пути
решение принимает действующий аналитик того же проекта, отличный от автора
сообщения. Точная утверждённая версия становится источником цели и scope
для черновика PlanVersion. Plan approval остаётся последующей командой.
ADR-167 отделяет назначенные START в claim/quarantine. PostgreSQL и Temporal
проверили цепочку от Manager до задач. Независимые code и security review
дали APPROVE после ограниченного чтения тела и отдельного ACL на `resultRef`.

G02 **IN_PROGRESS** на `feat/g02-tool-registry-manager`, база
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff. Открыты target
protected wiring, авторизация отмены exact Run, включение проекции и
история v0.4, проактивность, `make pre-pr` и Linux CI. При подключении
namespace защищённого dispatcher должен совпадать с namespace всех
забираемых им назначений. [Evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## Возобновление · 2026-11-21

Владелец поручил продолжить и завершить группу. Ветка
`feat/g02-tool-registry-manager`, база `7f0c29f9519217dba722ad1f5b6396d8a02216da`,
рабочий diff. S17 сохраняет прежнее локальное evidence. В S20 добавлен
внутренний read model Epic. В S21 черновик PlanVersion доступен через
канонический путь `POST /epics/{epicId}/plans` с WORKING overlay.
Реальный PostgreSQL/Temporal проверил путь от HTTP до Task, native-кандидат
проверил сценарий отказа и replay после создания черновика через HTTP.

Группа **IN_PROGRESS**. В открытом scope остаются целевое подключение ADR-129
и G-107, Manager Proposal → PlanVersion, привязка Manager к версии проекции,
допущенная история v0.4 и проактивная группировка. Для человеческого решения
по Proposal запрошено подтверждение роли approver. Общие `make pre-pr` и
Linux CI относятся к будущему полному diff. Следующая группа не начата.
[S20](../increments/S20_project_epic_intake_manager_REPORT.md),
[S21](../increments/S21_plan_task_orchestration_REPORT.md).

## Предыдущая пауза после проверки ADR-164

По поручению владельца завершён текущий срез и приостановлена реализация
группы. Native frontend собрал многостраничную History точного Run, повторно
проверил выдачу и подтвердил отказ и replay на изолированном PostgreSQL/Temporal.
G02 остаётся **IN_PROGRESS**. При возобновлении в текущей ветке открыты
штатный защищённый контур, Manager Proposal → PlanVersion, история v0.4
с доказанным происхождением, проекция Epic, проактивные сообщения и общая
приёмка. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Native таймаут Manager после ACK · 2026-11-20

Сетевой native сценарий подтвердил `START_TO_CLOSE` на Manager Activity
после ACK, `FAILED` точного Workflow Run, сохранение доменной Operation
в `RUNNING` и одну запись `OPERATION_RECONCILIATION_REQUIRED`. История
воспроизводится. Синтетический таймаут происходит перед вызовом модели.
G02 остаётся **IN_PROGRESS**. Открыты штатный защищённый контур,
многостраничная History, финальные продуктовые сценарии и общая приёмка.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Защищённая доставка отказа · 2026-11-20

ADR-163 устранил `PermissionDenied` при отправке ошибки native Manager
Activity. Реальный отрицательный Plan после ACK достиг `FAILED` в Temporal,
Backend связал статус с отсутствием локальных эффектов и записал коррекцию.
Точная сохранённая история прошла replay. Срез **TESTED**, G02 остаётся
**IN_PROGRESS** до штатного подключения, закрытия оставшегося scope и общих
gates. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Сверка эффектов после ACK · 2026-11-20

ADR-162 связал exact Temporal Describe с PostgreSQL под блокировками.
Изолированный Plan terminates after ACK и корректируется только без
созданных эффектов. Неполный или неоднозначный результат сохраняется в
аудите без дублей и ждёт подтверждения. Режим включается доверенным
`include_post_ack`. G02 **IN_PROGRESS**. Сквозное native failure reply,
штатные процессы и общие gates остаются открытыми.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Делегированные решения · 2026-11-20

ADR-160 и ADR-161 зафиксированы по поручению владельца принимать решения
самостоятельно. Отдельная identity получает минимальный статус точного Run.
Проверка разграничена от полномочий на изменение Operation. Для выдачи
текста истории допускается доказанная связь с явно классифицированной
неизменяемой версией источника и актуальные Policy/ACL. Штатное подключение,
сверка фактического эффекта, выдача допустимых записей и общая приёмка
G02 остаются открытыми. [Решения](../DECISIONS_PENDING.md),
[отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Приёмка группы · 2026-11-20

По поручению владельца проверяется весь состав G02. В S20 подтверждён
повтор Start после потери успешного ответа до binding на сетевом кандидате.
В S21 opt-in Backend consumer готовит `PLAN_EXECUTION` из зафиксированного
утверждения. Проверен HTTP → consumer → Temporal → private ar2 → Tasks
на заранее подготовленной PlanVersion. Общий guard Proposal/PlanVersion
введён ADR-159. Подписанный ar2 v0.4 проверен с пустым журналом.

S17 остаётся проверенным локальным срезом. G02, S20 и S21 остаются
IN_PROGRESS. Открыты штатный protected wiring и G-107 после ACK, допуск
Plan, продуктовая цепочка Proposal → PlanVersion, выдача истории v0.4,
проекция Epic и проактивная группировка. Общие `make pre-pr` и точный
Linux CI выполняются после завершения состава группы. Штатный Compose
на этом checkpoint не перестраивался.
[Отчёт S17](../increments/S17_tool_registry_tool_gateway_REPORT.md),
[отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md),
[отчёт S21](../increments/S21_plan_task_orchestration_REPORT.md),
[решения владельца](../DECISIONS_PENDING.md).

### Проверки рабочего diff

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, ветка
`feat/g02-tool-registry-manager`. Darwin arm64, Python 3.13.5 и Docker
Engine 29.2.0. Целевой PostgreSQL 16.15.

| Команда | Результат |
|---|---|
| `make contracts-check contracts-test` | Exit 0, 6 validators, 47 passed, 0 failed/skipped, 8.58 с. |
| `make -j1 pre-push-fast infra-check infra-scan-secrets` | Exit 0, 1943 passed, 0 failed/skipped, 3 OTel deprecation warnings, 13.90 с для pytest. 15 import contracts, 0 нарушений Compose и 0 секретов по scanner. Выполнено до ADR-159. |
| `make backend-check` и `git diff --check` после ADR-159 | Exit 0, 263 mypy файла, 15 import contracts. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_migrations.py backend/tests/integration/postgres/test_schema_drift.py backend/tests/integration/postgres/test_operation_execution_assignments.py backend/tests/integration/postgres/test_native_auth_control.py backend/tests/integration/postgres/test_platform_manager_commands.py backend/tests/integration/postgres/test_manager_intake.py backend/tests/integration/temporal --tb=short` | Exit 0, 53 passed, 0 failed/skipped, 53.62 с, одно предупреждение SQLAlchemy `xid8` на scratch schema. После этого v0.4 и ADR-159 проверены целевыми командами из отчёта S20. |
| Из `backend`: `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 uv run --locked pytest -q --tb=short` | Exit 0, 3326 passed, 0 failed, 3 skipped, 540 предупреждений, 1207.59 с. Прогон стартовал до итоговых правок v0.4 и ADR-159. Три native варианта требуют отдельной среды. Финальный Compose-вариант и затронутые команды выполнены отдельно. |
| Из `infra`: `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 uv run --locked pytest -q -m 'not runtime' -rs --tb=short` | Exit 0, 222 passed, 0 failed, 18 skipped, 130 deselected, 14.35 с. 18 тестов обнаружили, что запущенный Compose принадлежит родительскому worktree. Первый запуск с LibreSSL 3.3.6 завершился exit 1 на derivation Ed25519, повтор с OpenSSL 3.6.3 прошёл. |
| `make renovate-check` | Exit 0, 10 passed, 0 failed/skipped. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response` | Финальный рабочий diff, exit 0, 1 passed, 0 failed/skipped, 14.41 с. Самостоятельный Compose очищен. |

## Сети Compose и повтор Outbox · 2026-11-20

ADR-157 проверяет раздельные private сети Compose и повтор Outbox реальным
dispatcher после привязки Run. Второй delivery поставил отметку `PUBLISHED`
при одном Start и одном draft. Переключение штатных процессов и оставшийся
G-107 открыты. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Private ar2 и PostgreSQL verify-full · 2026-11-20

ADR-156 подтверждает запуск Manager через native Temporal и реальный ar2
на изолированном Compose. Подготовка схем и Alembic переиспользуют штатные
шаги. Основная Compose-топология и G-107 recovery остаются открыты.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Восстановление Run в тестовом Compose · 2026-11-20

ADR-155 подтверждает логическое восстановление двух баз temporal fixture,
точную историю и visibility Run при перезапуске только Temporal. Доступ
и internode gRPC mTLS подтверждены на изолированном проекте. Целевой
Compose и остальной G-107 открыты. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## PostgreSQL и internode mTLS для native PoC · 2026-11-20

ADR-154 дополняет изолированный PoC одноразовым PostgreSQL и отдельной CA
для gRPC History/Matching. History и visibility подтвердили точный Run.
Развёртывание в целевом Compose и G-107 recovery остаются открытыми.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Linux-сборка native PoC · 2026-11-20

ADR-153 закрепляет отдельный Linux-образ PoC с offline-компиляцией,
provenance и локальными проверками mTLS/изоляции. Целевой Compose сохраняет
stock Temporal до приёмки PostgreSQL, mTLS и остальных G-107.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Планировщик сверки · 2026-11-20

ADR-152 подключает сверку до ACK к Backend lifespan через явную конфигурацию
проектов и mTLS. PostgreSQL/Temporal подтвердили коррекцию, native PoC подтвердил
чтение по отдельной identity. Для целевого Compose нужны native build и проверка
deployment-конфигурации. S20/G02 IN_PROGRESS. [Отчёт](../increments/S20_project_epic_intake_manager_REPORT.md).

## Native observer · 2026-11-20

В S20 ADR-151 и 0047 подключают проверку exact Describe до ACK к изолированному
native Temporal. Пройдены PostgreSQL, TLS/RPC и контрактные сценарии для этого
среза. Целевая композиция, планировщик и оставшиеся G-107 открыты.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Продолжение · 2026-11-20

S20 получил постраничную сверку назначенных Run до ACK в Backend, ADR-150.
Целевые PostgreSQL/Temporal тесты и независимые review подтвердили локальный
срез. Права production observer и подключение планировщика остаются открытыми;
S20, S21 и G02 сохраняют **IN_PROGRESS**. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Продолжение · 2026-11-19

Текущая папка `../AI-RES-G02` и ветка `feat/g02-tool-registry-manager`.
S17 сохранил прежний локальный результат. В S20 выполнена часть G-107
(проверенный сбой exact Run до ACK), оформлен согласованный DOC-086 v0.4
и проверен его вход в LangGraph через детерминированный LLMGatewayPort.
S21 ждёт завершения admission start/cancel и подключения потребителя
зафиксированного утверждения. Группа остаётся **IN_PROGRESS**.
[Новый checkpoint](../CONTEXT_HANDOFF.md), [отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## Рабочий checkpoint · 2026-11-19

Поручение владельца «реализуем следующую имеющуюся у нас группу».
Определена G02 после G01 в PR #33 и SLICE-01 в PR #34–35. Общее свойство
группы — управляемый каталог инструментов и Manager intake → PlanVersion → Task.
База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, worktree `../AI-RES-G02`,
ветка `feat/g02-tool-registry-manager`, рабочий diff. Исходная ветка сохранена
вместе с шестью модифицированными документами/evidence и локальным tariff input.

| Этап | Внешние DONE и внутренний порядок | Фактическая готовность |
|---|---|---|
| S17 | S07, S12, ARCH-01 и SLICE-01 DONE | Каталог и локальный Gateway реализованы, целевые PG и unit проверки, review среза пройдено |
| S20 | S12, S15, S19 DONE, ADR-129/G-107 до producer | IN_PROGRESS. Intake, draft, question journal, ar2 v0.3 и Outbox добавлены. Изолированный native Temporal подтвердил Start, receipt выдачи Workflow Task и Activity, completion и итог в PostgreSQL. G-107, обработка отказов в целевом стеке, подключение журнала вопросов и проактивная группировка остаются в scope. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md) |
| S21 | Внутренние intake и approval S20 | IN_PROGRESS. Граф, immutable version, exact approval, createTask v1.3 и Temporal replay локально проверены. Обработчик зафиксированного события утверждения готовит один запуск. Подключение его потребителя в целевом стеке открыто. [Отчёт](../increments/S21_plan_task_orchestration_REPORT.md) |

Владелец отдельно одобрил scoped role map и внутренний контракт ADR-129.
Публичная семантика QUEUED продолжает действовать. Runtime PoC использует своё
loopback-окружение, временные сертификаты и disposable PostgreSQL. Основной
Compose, пользовательские данные и секреты не использованы в проверке PoC.
Сквозной локальный сценарий проверяет intake, ar2 v0.3, восстановление
Start и отмену PlanExecution. Защищённый runtime Compose и общий G-107
reconciler остаются. Общие G1–G9 и CI на итоговом SHA проводятся после
реализации группы. Для полного `pre-pr` требуется отдельное окружение с
собственным Docker daemon и loopback. Текущие цели и runtime-тесты используют
общие имена проекта, образы, сети и порт 8443.
Текущий результат не является VERIFIED/DONE. См. [handoff](../CONTEXT_HANDOFF.md).

**Final local gates:** contracts22/Renovate10/backend2853/fast1538/PG31/infra369/
runtime148/PoC19PASS; scanner0findings; rebuiltAPI14reviewedfiles/0hashmismatch и
trustedTLS admin login/logout PASS. Pre-pr scanner false positives исправлены,
завершён scoped resume exit0 без повтора полного backend; исходныйpre-pr exit2
не объявляется exit0. Следующий шаг только delivery PR34/exactLinuxCI, затем STOP
для обновления контекста. SLICE-01/G02 не начинать. После CI обновить evidence
ЛОКАЛЬНО без ещё одного docs-only push.

**Актуальное поручение:** закончить все реализации перед SLICE-01, затем остановиться
для обновления контекста; SLICE-01 и G02 не запускать. ADR141 observed product
wiring и полный audited human profile approval CLI реализованы/reviewed; code
locally TESTED. Два independent APPROVE/open0; backend2853PASS/fast1538PASS/PG31PASS,
финальные infra/runtime gates и одна доставка PR34 завершаются. Владелец принял
50USD/month + INTERNAL ordinary/noPII/noTradeSecrets и поручил default admin;
AI RES / Administrator / admin@ai-res.local создан, unique secret только ignored0600,
реальные trustedTLS login/logout PASS. Дальнейшая персональная настройка позднее
по указанию владельца; actual model approval не совершался. G02/S17/S20/S21
NOT_STARTED; fullG156 real admission NOT VERIFIED. Актуальные details —
[handoff](../CONTEXT_HANDOFF.md) и [отчёт](../increments/G02_identity_admission_operator_REPORT.md).

История ниже:

**Последнее уточнение владельца:** лишний documentation push вызвал CI44312593429;
этот повтор отменён, COMPLETED/CANCELLED подтверждено. Runtimecode38 уже имеет
обаCI SUCCESS;1e меняеттолькодокументы. Не запускатьновуюработу/тесты/push/CI
до продолжения после обновленияконтекста. Это уточнение сохранено только локально.

**Перед обновлениемконтекста:** docsHEAD1e971f5, PRCI44312593429 ещёвработе,
contractsPASS, codebyte-identical38. Локальныйdocs-onlydiffуточняетhandoff;
дальше не делатьpushрадиоднихcheckpointслов. Подготовка неDONE; продолжение
послеобновленияконтекста начинаетсясHIGHdraft373, не новойгруппы.

**Checkpoint перед обновлениемконтекста:** CODE38f5955 technicalCIpush+PR alljobsPASS,
Go/race/vet/native12PASS, guardedidle922.37s/182checksPASS. FullG156/modelactivation
ещёНЕзакрыты. Productobservedwiring сохранён отдельно вLOCALbranch
wip/g156-observed-wiring-checkpoint@3733825, неintegrated/published:1495purePASS,
knownHIGHreverseSSEdrift NOT_FIXED, noindependentreview/PG/pre-pr/CI.
[Draftcheckpoint](../reviews/G02_OBSERVED_WIRING_DRAFT_CHECKPOINT.json).
По просьбе владельца после текущихтестов работа остановлена дляобновленияконтекста.


**Актуальный прогон2026-11-18:** localpre-pr PASS(backend2740/infra369/runtime148/poc19/contracts22);
HEAD504ceb0 LinuxPR44300787624/push44300778838 alljobsPASS, backend2740/541warnings/14:31,
locked dependency auditclean. На реальном DeepSeek TEXT/JSON/TOOL/SSE COMPLETE/capabilitytrue,
stablefingerprintbc19ba97cbe016479903222bb1578db6, usage+ledgerKNOWN. CANCEL locally
closed; initialCLI accountingunconfirmed thenauthoritativeSETTLED/UNKNOWN/fullreserve.
TIMEOUTcase returnedCOMPLETE within10s: timeoutNOTOBSERVED. Original6/8attempts,
used+reserved0.6005034USD,remaining9.3994966,pendingfalse/blockedfalse; providerbilling
notverified. [Metadata evidence](../reviews/G02_FLASH_LIVE_EVIDENCE.json). No humanmodelapproval.
Concrete15minhousekeepingSQLdrift found/isolated; minimal3file candidate routingstore
fix source-reviewed twiceAPPROVE/open0, build/native/longidle/newexactCI running.
No newstage/framework, noSQLexceptions/auth weakening. G156 IN_PROGRESS; product
profile/observedgateway/human/SLICE prerequisites remain, G02 NOT_STARTED.


**Текущее завершение2026-11-18:** владелец потребовал закончить допуск как
конечный MVP-результат с необходимыми тестами, затем вернуться к группам.
ADR140 operator локально TESTED306jointPG/1434fastPASS, два independent APPROVE;
[отчёт](../increments/G02_identity_admission_operator_REPORT.md). Launcher existing
contexts готов:22purePASS/два independent APPROVE, [review](../reviews/G02_CANDIDATE_LAUNCH_REVIEWS.md).
Finalpre-pr/LinuxCI и real setup в работе; provider key получен только как локальный
SOPS ciphertext, value не раскрывался, calls/spend0. Не добавлять самостоятельные
подготовительные механизмы без concrete blocker; product gateway/APPROVED не нужны
до первого profileless candidate probe. G02 NOT_STARTED; подготовка ещё IN_PROGRESS.

**Checkpoint2026-11-18 / ADR139:** authenticated owner identity-review preparation
локально TESTED; newPG42PASS, jointPG187PASS, contracts22PASS, два independent
APPROVE/open0. [Отчёт](../increments/G02_owner_review_binding_REPORT.md).
Exact owner/session/MFA/Policy/evidence/full profile/state binding реализован;
нет approval DML/grants/migrations или включения. Следующий seam — отдельный
operator lifecycle executor с exact human decision/global audit, затем observed
gateway. Finalgates/key/live/human/SLICE остаются; G156 IN_PROGRESS/NOT VERIFIED,
G02/S17/S20/S21 NOT_STARTED до нового согласия после подготовки.

**Checkpoint 2026-11-18 / ADR138:** lifecycle fence локально TESTED, forward0025;
PG111PASS, fast1419PASS, contracts22PASS, два independent APPROVE/open0.
[Отчёт](../increments/G02_admission_lifecycle_fence_REPORT.md).
Новая команда продолжения сняла остановку ADR137 только для подготовки.
Owner lifecycle/authenticated evidence binding и observed gateway ещё нужны;
fence не является dispatch authority. Затем finalgates/key/live/human/SLICE.
G156 IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED до нового согласия после подготовки.

**Актуально2026-11-18 / ADR137:** [configuration integrity](../increments/G02_candidate_configuration_integrity_REPORT.md) локально TESTED:Go8+42normal/racePASS,vet0,fast1419PASS/4warnings,newnative12PASS/final104.20s,legacy65PASSизjointс1testfixturefailure(исправлен/повторnew12). Два independent source APPROVE/15hashes0mismatch. Новый отдельный candidate: freshbootstrap,hardroutefreeze,stickyfile/live/readonlylogicalSQLiteguard безexclusions;host0.2actualnamespace+env-ihealth+bootbindingpreclaim,settlementpreserved. Official/SDK/mainstack/frozen/canonical не заменены,realcalls/spend0. **Владелец поручил закончить документирование и остановиться до обновления контекста/новойзадачи.** G156 IN_PROGRESS/G02/S17/S20/S21 NOT_STARTED. Следующий preparatory seam — product admission/owner lifecycle/wiring; потом finalgates/tariff+account/key/live/human/SLICE. Старые ниже configOPEN checkpoints — история до нового механизма, не отмена общего G156 OPEN.

**Актуальный native audit2026-11-18:** [проверка](../increments/G02_bifrost_effective_isolation_REPORT.md) локально TESTED:6nativePASS/final7.18s,host78PASS,fast1390PASS/4warnings,два independent APPROVE/open0. Штатный renderer/selected live+DB settings/auth/network/logs проверены на новом disabled-provider стенде. Admin mutation live/SQLite при unchanged rendered config/image/canonical inspect воспроизведена — effective integrity gate OPEN. Mounts-order false-refusal исправлен без исключения полей из hash. Следующий preparatory seam — actual rendered/effective/admin/SQLite enforcement до reserve/claim; не key/live. Main18containers/frozen0020–24/SDK/canonical/secrets сохранены;calls/spend0. Подготовка IN_PROGRESS,G02/S17/S20/S21 NOT_STARTED. Ниже прежние checkpoints сохраняются как история; финальные live/human/SLICE/CI gates не сняты.

**Актуальное продолжение2026-11-18:** новая команда разрешила следующий preparatory seam. ADR136 host gate/composition локально TESTED:fast1389,PG22,affected142PASS,два independent APPROVE/open0. [Отчёт](../increments/G02_candidate_development_host_REPORT.md), [review](../reviews/G02_DEVELOPMENT_HOST_REVIEWS.md). G02 NOT_STARTED/подготовка IN_PROGRESS. Следующий seam — actual isolated topology/effective mutable Bifrost config integrity, затем оставшиеся admission/lifecycle/final/live/human/SLICE gates. Default env listener accounting-only, реальные accounts/tariffs/keys/calls отсутствуют. Source review не доказывает mutable SQLite/admin state. Предыдущая остановка ниже снята только для подготовки этой командой; group consent не выдано.

**Поручение:** владелец, 2026-11-17: продолжить подготовку и реализацию G02 по DEVELOPMENT_GROUPS, восстановить фактический контекст, сохранить локальные изменения; учесть ADR-128/129, не обходить зависимости, допуск модели и SLICE-01; вопросы обсуждать по одному.

**Уточнение владельца 2026-11-17:** «как выполнишь подготовительные шаги обязательно скажи. G02 без моего согласия не начинай». Продолжается только подготовка внешних предпосылок. Старт S17/S20/S21 требует нового явного согласия владельца после отчёта о готовности; прежнее поручение не использовать как автоматическое разрешение перехода в продуктовую группу.

**Статус группы:** NOT_STARTED, ожидает нового согласия владельца. **Подготовка G156:** IN_PROGRESS. S17/S20/S21 NOT_STARTED, вход в S17 также требует завершённого SLICE-01. Ближайшая работа — [Flash admission](G02_FLASH_ADMISSION.md). Когда подготовительные условия будут действительно выполнены, отдельно уведомить владельца; локально TESTED guard не выдавать за полную готовность подготовки.

**Завершающий preparatory checkpoint ADR135,2026-11-18:** отдельная local patch/build того же Bifrost2.5.1 для actual terminal SSE fingerprint bug. SDK автор g02_prerequisite_plan, build/fixture автор g02_python_contract_review, Go/security reviewers проверяют только чужое. Root shared docs/integration. SDK exactec453… normal/race11parents+134subPASS,vet exit0,два independent APPROVE. Build source/fresh acquisition/image+actualbinary provenance и24patched+8official nativecases PASS, два final source review APPROVE/open0; wholeG156 NOT VERIFIED. Runtime очищен/освобождён, owncaches оставлены. По просьбе владельца остановиться до новой команды; завтра начать с конкретного host composition/gate scope по HANDOFF, SDK не повторять без новой причины. Official image/main stack/strict adapter/required metadata не менять. Modelcalls0, G02 NOT_STARTED.

**Metadata decision принято и реализовано по делегированию владельца:** ADR131, активный внутренний контракт0.2. Fingerprint VALUE обязателен для expectation; ABSENT/NULL остаются candidate facts. Parser/schema/direct construction совпадают, прежний0.1 не принимается активным parser. Повторного вопроса optional/mandatory нет. Live values/evidence/Bifrost/profile approvals остаются до включения. Durable foundation0020–0022 локально TESTED; полный G156 NOT VERIFIED, mode expand0023 локально TESTED.

## Git и сохранность работы

- Worktree: текущий репозиторий AI-RES; исполнитель/координатор — основной Codex. Другие группы не поручены.
- Проверенная база/HEAD: `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, merge PR33. История содержит G01/S18 и S19; G01 не переоткрывается.
- Исходная ветка: `docs/ncp16-flash-identity-exception`; создана `feat/g02-manager-tools-planning` от того же HEAD с сохранением всего исходного diff.
- До начала: 19 изменённых tracked + 10 новых файлов по NCP16/OD19 (ADR128/129), docs/architecture и manifest pointer включены. Это существующая работа владельца; не включать автоматически в commit. Канонические файлы, зеркало и прежние отчёты этой сессией не редактируются. HANDOFF/STATUS/ECC дополняются без удаления исходных записей.
- Общий PR/SHA/новое Linux CI: отсутствуют. Исторические PASS G01/S16 не относятся к новому diff.

## Порядок и зависимости

| Работа | Источники | Проверенные предпосылки / оставшиеся условия | Статус |
|---|---|---|---|
| G-156: технический допуск Flash | ADR128; DOC076 §3.1/7; [план](G02_FLASH_ADMISSION.md) | Контракт0.2 и durable foundation0020–0022 локально проверены;0023 mode expand локально TESTED. Ledger/candidate runner/live evidence и approvals ещё нужны | IN_PROGRESS; полный механизм NOT VERIFIED |
| SLICE-01, внешний мини-этап | ADR115; TEST_DATA_SOURCES | Технический S16 DONE; нужен допущенный Flash, проверенная лицензия выбранного источника и отдельный бюджет SLICE. Общий потолок 10 USD допуска на SLICE не переносится | NOT_STARTED / BLOCKED |
| S17 | [промпт](../increments/prompts/S17_tool_registry_tool_gateway.md) | S07/S12, ARCH-01 DONE; SLICE-01 ещё не выполнен | NOT_STARTED / PENDING_DEPS |
| S20 | [промпт](../increments/prompts/S20_project_epic_intake_manager.md) | S12/S15/S19 DONE; по порядку группы после S17. До первого producer нужны OD19 enforcement и G107 reconciler+allowlist | NOT_STARTED / PENDING_DEPS |
| S21 | [промпт](../increments/prompts/S21_plan_task_orchestration.md) | Внутренний реализованный контракт S20 в общей ветке; replay/versioning/plan gates остаются | NOT_STARTED / PENDING_DEPS |

Внешняя предпосылка требует своего DONE до зависимого Sxx. Реализация → общая отладка → независимое review/исправления → финальные gates и один PR группы по AGENTS §11/ADR127. Отдельный полный pre-pr/CI/PR каждого внутреннего Sxx не требуется. Подготовка G-156 не разрешает пропустить SLICE-01, перейти в другую группу или назвать модель APPROVED.

## Scope и владение

Текущая подготовка включает pure identity contract0.2 и durable admission foundation0020–0022: четыре технические таблицы, immutable evidence, pending barrier, sticky block, security audit, PG/restart/logical restore tests. Следующий0023 добавляет честный observed profile mode/readonly reference без fake pin; локально проверен на PostgreSQL, без product wiring. Product factory/routing/immutable transport guards не включаются, реальные profile/approval/grant/classification seeds не создаются.

Основной исполнитель ведёт shared tests/snapshot и implementation-документы. `g02_prerequisite_plan` получил ограниченное авторство новых persistence/mode компонентов; отдельные read-only database/Python и security reviewers проверяют чужой код blind-first. ADR132 фиксирует durable foundation, не выдаёт human authority и не меняет BASELINED.

Runtime использовался только последовательно в disposable PostgreSQL Testcontainers. Основной Compose stack/volumes/данные/secrets не менялись; платных вызовов0.После scoped0023 tests исполнитель освободил runtime; root последовательно завершил snapshot и actual drift/upgrades, контейнеры тестов завершены. Это владение рабочим runtime, не требование для следующей сессии: перед возобновлением проверить фактически работающие процессы/контейнеры. Сброс volumes и ротация существующих secrets не разрешены. Внешнему исследованию передавались только общие официальные DeepSeek/PostgreSQL вопросы без проектного содержимого.

## Gates и продолжение

Для чистого validator выполнены fast/contracts и независимое review; для0020–0022 добавлены реальные PG32cases и profile/RLS/grants/failure/concurrency/process/logical restore coverage. Initial full backend1901passed/3legacy failures, после точечных test fixes affected+upgrade/drift11passed; полного green повторно нет.0023 отдельно:56PGpassed,fast957passed,actual drift/upgrades7passed,два reviewers APPROVE. Pre-pr/Linux CI итоговой подготовки ещё не выполнены; локальные checkpoints не являются real-provider approval или VERIFIED G156. Все применимые G1–G9 и DoD будущих Sxx сохраняются. Подробная readiness matrix — в плане подготовки.

Первый внешний operational blocker live candidate PoC — безопасный setup provider key после готового плана расходов. Значение ключа не запрашивать в чате. Состав обязательной identity metadata выбран по делегированию владельца (ADR131); точные реальные значения/evidence проходят человеческую приёмку до включения. Список классификаций также нужен перед включением, а не для начала отключённой разработки. Первый ответ не auto-approval. Технические выборы OD19 повторно владельцу не возвращать; PoC ADR129 и G107 остаются обязательными до реального producer S20.

Identity checkpoint — [первый отчёт](../increments/G02_flash_admission_preparation_REPORT.md); persistence/current checks — [durable report](../increments/G02_model_admission_persistence_REPORT.md) и [review](../reviews/G02_MODEL_ADMISSION_REVIEWS.md). При остановке HANDOFF/STATUS обновляются; незакрытые G156/SLICE/OD19 не теряются. При DONE всей G02 — остановка до нового поручения.

**Текущий preparatory checkpoint (ADR133):** ledger локально TESTED,0024 frozen; PG40cases/process+restore,fast957,actual drift/upgrades/security6passed,два independent APPROVE. [Отчёт](../increments/G02_flash_paid_ledger_REPORT.md). Runtime tests завершены; следующие runtime действия предварительно проверить по фактическому состоянию. Новых real accounts/tariffs/keys/calls нет. Ближайшая незавершённая часть — candidate egress/runner; read-only план A/privateTLS backend claim остаётся PROPOSED/NOT_IMPLEMENTED/NOT_SECURITY_ACCEPTED. Подготовка не завершена, о старте G02 вопрос не ставится.

**ADR134, checkpoint2026-11-18:** private backend service/ASGI + codec/client/relay/TLS + native profileless probe + runner реализованы и локально TESTED. Fast1281passed,runner43passed с14realPG, independent security re-review APPROVE/open0. Actual Bifrost8passed включает negative terminal fingerprint loss: SSE compatibility BLOCKED; TEXT/JSON/TOOL fake-upstream проходят. Root владеет relay/client/TLS/tests/docs/contracts; g02_prerequisite_plan автор control/runner, g02_python_contract_review автор codec/probe/Bifrost fixture. General cross-review только чужих файлов, g02_scope_security_review независимый security reviewer всех. Concrete trusted host/freshness/product wiring/owner lifecycle/key/live/SLICE остаются. [Отчёт](../increments/G02_candidate_egress_preparation_REPORT.md), [review](../reviews/G02_CANDIDATE_EGRESS_REVIEWS.md). Main stack не перезапускался, frozen0020–24 неизменны, modelcalls/spend0. Portable fixture own-image build+21cases PASS, security delta APPROVE/open0; временные containers/network удалены, runtime освобождён. При возобновлении проверить фактическое состояние. Подготовка IN_PROGRESS, G02 NOT_STARTED.
