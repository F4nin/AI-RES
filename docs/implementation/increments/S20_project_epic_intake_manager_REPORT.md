# S20 — Project/Epic intake и Manager interaction

**Статус на 2026-11-24:** VERIFIED / DONE в техническом объёме.
[PR #36](https://github.com/F4nin/AI-RES/pull/36) влит в `main`.
Linux CI, G-107, защита данных, история Temporal и PostgreSQL-механика
подтверждены. Качество вывода реальной модели остаётся вне этого evidence.
Для штатного `MANAGER_INTAKE` нужен отдельный допуск и G-145.
[Общая матрица gates](../groups/G02_WORK.md).

## Целевой запуск сверки G-107 · 2026-11-24

В выделенном dev/test Compose на SHA
`8c0c2ebbc6d4618eec3e5e9946bd1acde7d6996f` запущен штатный
`python -m ai_res.api.serve` из Backend-образа
`sha256:fb0b06cc56754a1a26eb383dbd114f25c0cb3d2b02bb31a0fcc3eebe5014d511`.
Использован `compose.g02.yaml` с временным PostgreSQL, изолированными
сетями и синтетическими credentials. Bind манифеста передал явный
allowlist `MANAGER_MESSAGE` и `PLAN_EXECUTION` с post-ACK. Процесс прошёл
healthcheck. Его планировщик установил mTLS с native Temporal и открыл
PostgreSQL-сессию `ai_res_api`. Проверка не создавала Operation и дополняет
ранее проверенные потерю ответа Start, карантин, Cancel и сверку после ACK
на точных назначениях. Штатный producer выключен.

Команды на Darwin arm64 с Python 3.13.5, Docker Engine 29.2.0 linux/arm64
и Compose 5.0.2: `docker --context desktop-linux build --pull=false -t
ai-res/g02-api-admission:8c0c2eb backend`, затем одноразовый Python probe
`/tmp/aires-g02-runtime-api-probe.VcOj2u` с установленным OpenSSL 3.
Build и probe вернули exit 0, три проверки PASS, пропусков 0.
Логи `/tmp/aires-g02-runtime-api.r2Ro0V` и
`/tmp/aires-g02-runtime-api-result.SqUDp6`. Временный Compose остановлен с
сохранением обычного окружения. Платных вызовов 0.

## Актуальность полномочий при записи · 2026-11-24

В `backend/src/ai_res/api/write_api.py` Manager получает сообщение с
техническим дедлайном чтения и прежним настраиваемым лимитом размера.
После чтения Backend фиксирует блокировки сессии и полномочий, заново
проверяет проект, команду и точные ссылки на источники. Доступ должен
действовать до атомарной записи Operation, Interaction, Assignment,
Outbox и аудита. Для черновика Plan и решений Proposal и Plan тот же
порядок применяется перед idempotency и исполнением. Результат решения
опирается на текущие Policy и MFA. Повтор уже завершённой команды
снова проверяет доступ и возвращает прежний результат.

`make backend-check` вернул exit 0, Ruff, mypy 285 файлов и 15 import
contracts. PostgreSQL/Temporal: `test_manager_http.py`,
`test_planning_http.py` и `test_write_api.py` вернули exit 0,
66 passed за 65.73 с, лог `/tmp/aires-g02-api-final.PoGCA5`.
Проверены отзыв роли и сессии во время загрузки, дедлайн чтения,
отзыв сессии после первого Policy перед черновиком и утверждением
Plan, отказ без доменных эффектов и штатные идемпотентные повторы.
Review подтвердило блокировки и фактические решения. LOW остаётся по
консервативному сроку Principal, если параллельный запрос продлит
idle-сессию после первого чтения. Возможен отказ с последующим
повтором. Новых публичных контрактов и миграций в этом проходе нет.

На Linux arm64 пересобран Backend образ
`sha256:48885d1d0878078a316b655d5a586626d9dd8d24a1302801311f4a0feaedb683`.
`backend/.venv/bin/python -B -m infra.temporal_auth_poc.protected_candidate`
вернул exit 0, 1 passed за 15.91 с. Скан этого же образа вернул exit 0,
176 записей в SBOM и 0 исправляемых HIGH/CRITICAL в Trivy.
Логи `/tmp/aires-g02-protected-final-api.8gubGs` и
`/tmp/aires-g02-final-api-supply.VMb2KO`.

Итоговый `make pre-pr` на Ubuntu для HEAD
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочего diff прошёл, exit 0.
Contracts 51, Renovate 10, Backend 3419 passed за 788.00 с,
4 выделенных native-варианта и 540 предупреждений, infra 393 за 178.40 с,
отдельный runtime 148 за 153.75 с, Bifrost 19. Ошибок нет. Runtime входит
в общий infra-набор и отдельно повторяется как обязательная проверка.
Все четыре варианта, пропущенные в обычном Backend, прошли отдельно.
Финальный Compose tag дал 1 passed за 22.17 с. Логи
`/tmp/aires-g02-prepr-gate-final.UCox8O` и
`/tmp/aires-g02-tagged-final-api.1FrTSB`.

Первый полный локальный проход перед последним исправлением авторизации
также вернул exit 0. Лог `/tmp/aires-g02-prepr-after-infra.P85kzf`.
GitHub Actions на SHA доставки остаётся этапом приёмки. Платных вызовов 0.

## Безопасность сборки native Temporal · 2026-11-24

Первый скан образа Go 1.25.11 дал 23 HIGH при общем списке исключений.
Запись для Caddy скрыла дополнительную находку x/net в native образе.
Строгий native проход без исключений выявил
24 исправляемые находки и 139 связанных Go-пакетов, exit 1. Syft записал
140 записей SBOM. Логи `/tmp/aires-g02-native-supply.ZnXkQq` и
`/tmp/aires-g02-native-scan-gate-red.zAhTpv`.

ADR-185 закрепляет Go 1.27.4 и проверяемый `security-locks.patch` для
Temporal 1.29.7. Оригинальные locks проверяются отдельно. Альтернативные
locks применяются только через `-modfile` и также проверяются по SHA-256.
В образ входят хеши источника расширения, patch и locks, а также
`go version -m`. Независимое review сверило 14 хешей исправленных модулей
с Go checksum database. Сканер CI проверяет фактическую Go-инвентаризацию
исполняемого файла, отсутствие fixable HIGH/CRITICAL и успешный exit code.
Изменения не вводят миграций данных или API.

На проверяемом рабочем срезе собраны `native-runtime` и `postgres-test`.
Обычная сборка и варианты с `temporal_runtime` и `temporal_postgres_probe`
прошли offline tests и проверку lock-хешей.
Лог `/tmp/aires-g02-security-final.0HSOjA`. В Ubuntu запущено
`infra/scripts/supply_chain.sh --g02-native-only` для
`sha256:b0a8be0a665f49c3c9ccd35dc3c7a7c2ae43a2a2cb7ff922a06f4973d21b1459`
(Linux arm64). Exit 0, 139 связанных Go-пакетов, 0 исправляемых
HIGH/CRITICAL, Syft SBOM содержит 140 записей. В связанных версиях
подтверждены Go 1.27.4 и все семь повышенных модулей, включая косвенные
x/crypto 0.58.0 и x/text 0.43.0. Лог `/tmp/aires-g02-native-scan-gate-fixed.uQtfhM`.

Прогоны на тех же обновлённых артефактах на Ubuntu вернули exit 0:

| Команда из backend venv | Результат |
|---|---|
| `python -B -m infra.temporal_auth_poc.protected_candidate` | 1 passed за 16.08 с, точный Manager input, Proposal, Plan и сверка после ACK. Лог `/tmp/aires-g02-native-accept-fixed.atpvDU`. |
| `python -B -m infra.temporal_auth_poc.compose_cutover` и `compose_candidate --network --native-runtime` | Три фазы переключения и пять проверок транспорта и рестарта. Лог `/tmp/aires-g02-cutover-fixed.8lUKjs`. |
| `python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | 1 passed за 21.67 с. Лог `/tmp/aires-g02-native-recovery-fixed.1Qh7AC`. |
| `python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` и отдельный запуск с `--lose-start-response --paginate-history --manager-timeout` | По 1 passed за 14.25 и 44.87 с. Лог `/tmp/aires-g02-recovery-fixed.cVd3wS`. |
| `test_native_manager_workflow_with_platform_receipts[sqlite]` и `[postgres]` на Darwin arm64 | 2 passed за 25.71 с на итоговом Python diff. Обе native цели собраны Go 1.27.4 с проверенными оригинальными и альтернативными locks. Лог `/tmp/aires-g02-direct-final.6GNDz9`. |

Ubuntu и исходное рабочее дерево совпадают по манифесту 1225 файлов
без `docs/implementation/` с SHA-256
`45f926e55a62ad0a89e8c73eeb8daa1cf520014bb149c7215c1f496fa397a449`.
`make infra-verify-digests` с Buildx 0.30.1 подтвердил 21 pin,
0 расхождений. ShellCheck, actionlint, Hadolint и secret scan прошли.
Общий скан `AI_RES_SCAN_LLM_POC=1 infra/scripts/supply_chain.sh` вернул
exit 0 на срезе перед последним изменением авторизации. Собственные
образы прошли блокирующую проверку, сторонние отчёты сохранены в
`infra/releases/scan` тестовой VM по ADR-043. Первый запуск
завершился exit 137 из-за OOM Syft, повтор в тестовой VM с 3 GiB swap прошёл.
Логи `/tmp/aires-g02-stack-supply.JjQ5t9` и
`/tmp/aires-g02-stack-supply-final.lw3BAr`.

## Переход Temporal и защищённая сборка Manager · 2026-11-24

Ветка `feat/g02-tool-registry-manager`, HEAD `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
ADR-184 добавляет `runtime/assigned_manager.py`, ограниченную сборку signed
Platform-клиента, негативные проверки и `infra/temporal_auth_poc/compose_cutover.py`
с отдельным Compose probe. CI запускает эту репетицию рядом с protected acceptance.
У runtime нет DB credentials. Temporal использует выделенную Manager identity,
а Platform — HTTPS с проверкой имени и Ed25519 ar2. Доверенная композиция
передаёт построитель текущего входа и управляемый `LLMGatewayPort`. Guard
проверяет точное совпадение текста Platform и отсутствие внеполосных данных
в ответе построителя. Снимок v0.5 выдаёт только Platform, Proposal связан с его
версией. Попытки добавить источник или подменить сообщение прекращаются
до обращения к model transport.

Репетиция закреплённых stock и native Temporal 1.29.7 использует один свежий
PostgreSQL 16.15. На stock SDK завершает уже работающую legacy Activity;
две закрытые истории неизменны по SHA-256, namespace, retention и visibility
сохранились и replay проходит. Native отвергает plaintext, старый Start,
широкое чтение History и попытку получить legacy задачу без assignment.
Перед откатом проверяются точный таймаут выданной задачи и сохранённая
версия исполнения, подтверждающая постановку задачи в очередь. При откате
stock закрывает тот же отложенный Run. Проверка visibility ждёт
ровно один Run исходного Workflow ID. Это репетиция переключения после drain и
отката до допуска новых назначенных Run. Внешних вызовов модели 0.

В `notification_delivery.py` область продолжения ленты разделена на остаток
текущей сводки и строго более ранние доставки. Оба пути используют отдельные
граничные условия B-tree. Курсор, порядок, точные исходные проверки и FORCE RLS
получателя сохранены. Исторический поиск недоставленных событий планировщиком
остаётся отдельным MEDIUM. Публичные контракты, миграции, нормативные документы
и модель полномочий этим проходом не расширялись.

| Проверка | Результат |
|---|---|
| `make backend-check infra-scan-secrets` на Darwin arm64 | Exit 0. Ruff, mypy 285 файлов, 15 import contracts и 0 находок сканера. |
| `pytest -q -p no:cacheprovider tests/unit/test_assigned_manager_runtime.py tests/unit/test_manager_reasoning.py tests/integration/temporal/test_manager_workflows.py --tb=short` из `backend` | Exit 0, 26 passed за 3.76 с. Неполная конфигурация отклоняется до подключения. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.protected_candidate` с OpenSSL 3 в PATH | Exit 0, 1 passed за 38.95 с. Закреплённый Manager Worker с синтетическим входом. Подмена текущего сообщения и добавление источника проверены для точных Run с безопасной причиной отказа, без Proposal и без второй отправки модели. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_cutover` с OpenSSL 3 в PATH | Exit 0, три завершённые фазы stock/native/stock, без пропусков. Docker 29.2.0 linux/arm64, Compose 5.0.2, PostgreSQL 16.15, Temporal 1.29.7 и Python 3.13.5. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` | Exit 0, 1 passed за 12.43 с. В дополнение к Start проверен Cancel Plan. Один моделируемый таймаут доводит заданный тестовый budget доставки до исчерпания. Реальный CLI отклоняет вызов без `--confirm`, возвращает точное событие из карантина с `--confirm` и отклоняет повтор до повторного карантина. Защищённый маршрут доставляет один сигнал тому же Run, сохраняет Task и записывает один audit отмены. |
| `pytest -q -p no:cacheprovider tests/integration/postgres/test_proactive_notifications.py -rs` из `backend` | Exit 0, 7 passed на PostgreSQL 16.15 за 16.43 с. `EXPLAIN` проверяет обе индексные границы в generic plan при действующей tenant/recipient роли. Это проверка структуры, задержка на больших объёмах не измерялась. |
| `actionlint -color`, `git diff --check` | Exit 0. |
| `make backend-test` на Darwin arm64 | Exit 0, 3414 passed, 4 skipped, 540 предупреждений, 1256.78 с. Четыре native варианта включаются отдельно. Лог `/tmp/aires-g02-backend-final.1eWnSp`. |
| `test_native_manager_workflow_with_platform_receipts[sqlite]` и `[postgres]` с указанными native binary и schema refs | Exit 0, 2 passed за 23.11 с на исходной сборке Go 1.25.11. Лог `/tmp/aires-g02-direct.od2M3r`. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.protected_candidate` на Ubuntu VM | Exit 0, 1 passed за 22.27 с. Лог `/tmp/aires-g02-native-host-accept.EODMoj`. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_cutover` на Ubuntu VM | Exit 0, все три фазы. Первый запуск на Ubuntu исчерпал отведённое время при откате. Устранена гонка между сменой сервера и фиксацией повторной доставки legacy задачи. Повтор использовал тот же лимит времени и отдельный SQL statement timeout. Логи `/tmp/aires-g02-native-host-accept.EODMoj` и `/tmp/aires-g02-native-cutover-final.Xg0XqQ`. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` на Ubuntu VM | Exit 0, 1 passed за 52.91 с. Лог `/tmp/aires-g02-native-cancel.rkrMCL`. |
| `make backend-audit` на Ubuntu VM | Exit 0, pip-audit 2.10.1 не обнаружил известных уязвимостей в закреплённых runtime зависимостях. Лог `/tmp/aires-g02-audit.GlCvE7`. |

Общая приёмка выполняется в отдельной Ubuntu 24.04 arm64 VM (Lima 2.3.0,
Docker Engine 29.1.3, Compose 2.40.3, Python 3.13.5, uv 0.11.31,
Node 22.23.5, SOPS 3.13.3 и age 1.3.2). VM использует локальный диск и
свежий age-ключ временного стека. Работающий relay G156 остаётся в исходном
Engine. Предыдущая среда Docker Sandboxes выявила ограничения FUSE для
fsync каталогов и сборочных bind mounts. Её результат не используется
для приёмки. G02 остаётся **IN_PROGRESS** до общей приёмки.

Первый полный Backend на Ubuntu с `umask 0002` дал 3402 passed, 12 failed,
4 skipped. Trust gate корректно отвергал созданные с записью для группы
артефакты. Повтор трёх вариантов fixture с `umask 022` дал 3 passed,
19.56 с. Полный Backend с `umask 022` получил 3414 passed, 4 skipped,
540 предупреждений за 975.33 с. `make up` начал работу со свежими dev
credentials и применил Alembic head `95ce548ce5b0`.
Логи `/tmp/aires-g02-prepr-native.AjmllU`,
`/tmp/aires-g02-vm-umask.tH1VWx` и `/tmp/aires-g02-prepr-linux-final.GcwAsf`.

При сборе `infra-test` прежний parser ожидал аннотации на переменных
ревизий; обновлённый проверяет оба поддерживаемых формата. Следующий
прогон дал 392 passed и один отказ проверки длины нового signing seed.
Исправленный тест проверяет 32 декодированных байта у ключей, сохраняет
проверку длины и уникальности паролей и исключает значения из диагностики.
Два целевых runtime-теста вернули 2 passed за 0.86 с. Два синтетических
негативных теста подтвердили отсутствие значений в диагностике дубликата.
После исправлений общее `make infra-test` дало 393 passed.
Логи `/tmp/aires-g02-infra-final.1iGmBc` и
`/tmp/aires-g02-infra-evidence.0YpCkD`.

Для повторной доставки уже есть разграничение. Назначенный Start требует
human approval по ADR-174. Назначенный Cancel с сохранённым namespace
использует штатное подтверждение точного event ID операторским CLI.
Первая оценка независимого review о недоступности повтора была снята после
сверки предиката поиска, прав роли, триггеров и позитивного G-107 теста.

## Защищённая композиция и персональная лента · 2026-11-23–24

**G02/S20 IN_PROGRESS.** Ветка `feat/g02-tool-registry-manager` от
`7f0c29f9519217dba722ad1f5b6396d8a02216da` с сохранённым рабочим diff.
ADR-183 добавляет `infra/compose.g02.yaml`, приватный network bind,
namespace job с mTLS, привязку метрик к observability, защищённый запуск
Platform, Delivery и Dispatcher, а также opt-in `init-g02`. Тем же CLI
сохраняются базовые значения SOPS, копии для Compose и существующие отзывы.
Backend reconciliation получает scope из доверенного manifest.

Инфраструктурный diff включает `infra/compose.g02.yaml`, оба entrypoint в
`infra/config/temporal/`, `infra/scripts/{g02_credentials,secrets_dev}.py`,
`infra/temporal_auth_poc/{protected_candidate.py,compose.protected-test.yaml}`
и CI. Protected Platform startup проверяется в `api/serve_platform_v2.py`.
Сетевые, credential и lifecycle тесты добавлены в соответствующие существующие
наборы backend/infra. Изменения работы с секретами проверялись на временных
файлах.

ADR-182 реализован в `application/notification_delivery.py` и
`api/notification_api.py`. `GET /projects/{projectId}/notifications` и
`GET`/`PUT /projects/{projectId}/notification-preferences` описаны WORKING
OpenAPI. Доступ связывается с сессией, получателем и точными авторизованными
объектами. Курсор скрывает позицию. Настройки частоты требуют CSRF, Origin
и `If-Match`. Миграция `0055` добавляет персональную RLS-проекцию и
поддерживает переход с предыдущей схемы. Отдельные политики и snapshot
проверяются вместе с миграцией. Для v0.4 сохраняется ADR-161.
Контракт уведомлений хранится в `contracts/openapi/extensions/proactive_notifications.yaml`.
Обновлены ADR, статус и handoff, паспорт G02, KNOWN_GAPS, ECC_USAGE и обе
карты трассировки. Публичные маршруты доставки ограничены персональным
контуром уведомлений.

Проверенный runtime — Linux arm64 в Docker 29.2.0, Compose 5.0.2,
PostgreSQL 16.15, Temporal 1.29.7, Go 1.25.11. Хост Darwin с Python 3.13.5,
OpenSSL 3.6.3, SOPS 3.13.3 и age 1.3.2. Все групповые сценарии выполнены
на временных данных и сетях. Provider calls 0.

| Команда | Результат |
|---|---|
| `docker build --target native-runtime -t ai-res/temporal-native:g02-local infra/temporal_auth_poc` и `docker build -t ai-res/g02-protected-backend:test backend` | Exit 0. Pinned Go и Python образы. Локальные image IDs `sha256:02daf39eded37db7c86505aeda752082e6eea73316c2c6c8dd08394c110ed228` и `sha256:9a45178bb56ffd228a1f3917666c5c0fa48ca37c55d7fd01ef67b79661adffd6`. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.protected_candidate` с OpenSSL 3 в PATH | Exit 0, 1 passed за 20.39 с на HEAD с working diff. Реальные схемы, namespace job, Platform ar2, Dispatcher, Delivery и native Temporal в отдельных процессах. Fixture использует синтетическую модель и session/API в процессе теста. Manager → Proposal с snapshot и receipts. Backend consumer подбирает человеческое решение и создаёт одну назначенную Plan Operation. Сценарий проверяет ожидание Plan после создания Task, защищённую отмену Manager и Plan, сохранение Task и replay. Ровно одна инъекция отказа для точного Plan Run после реального ACK и до создания Task даёт FAILED в Temporal. Reconciler переводит Plan Operation в FAILED, фиксирует один audit и сохраняет историю, пригодную к replay. Метрики доступны только на observability и проверены на отсутствие canary/UUID. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network` с флагами `--paginate-history`, `--lose-start-response --paginate-history --manager-timeout`, `--replay-exhausted-start --paginate-history` и `--native-runtime` по отдельности | Все четыре exit 0. Три PostgreSQL/Temporal сценария дали по 1 passed за 29.52, 49.28 и 25.32 с. Standalone smoke подтвердил 5 проверок, включая отзыв на открытом соединении и сохранение namespace при рестарте. |
| `pytest -q -p no:cacheprovider -c backend/pyproject.toml` для `test_native_manager_workflow_with_platform_receipts[sqlite]` и `[postgres]` с `G02_NATIVE_PROBE_BINARY`, `G02_NATIVE_POSTGRES_PROBE_BINARY`, `G02_TEMPORAL_SQL_TOOL` и `G02_TEMPORAL_POSTGRES_SCHEMA_ROOT` | Exit 0, 2 passed за 20.26 с. Оба Darwin arm64 бинарника собраны текущими Go-файлами на сверенном snapshot Temporal 1.29.7 с Go 1.25.11, offline `go mod verify` exit 0. SQLite применён только для проверки native transport, PostgreSQL проверен отдельно. |
| `backend/.venv/bin/python -B -m pytest -q -c backend/pyproject.toml backend/tests/integration/test_platform_control_tls.py --tb=short` | Exit 0, 3 passed. Включая fail-closed startup защищённого Platform без native key. |
| `pytest -q -p no:cacheprovider tests/integration/postgres/test_proactive_notifications.py tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py::test_persist_001_upgrade_from_empty_reaches_head -rs` из `backend` | Exit 0, 9 passed за 20.46 с на PostgreSQL 16. Включая upgrade предыдущей ревизии с сохранением данных, RLS получателя, отзыв роли при чтении тела PUT, пережившее сбой digest обязательное уведомление с аудитом и bounded cursor. |
| `pytest -q -p no:cacheprovider` из `backend`, scoped файлы `test_native_auth_control.py`, `test_assigned_delivery_api.py`, `test_platform_manager_commands.py`, `test_plan_execution.py`, `test_platform_control_tls.py` | Exit 0, 24 passed за 22.66 с. |
| `pytest -q -p no:cacheprovider` из `backend` для `test_events_are_append_only_for_everyone_including_the_owner_path`, `test_matrix_covers_every_action_of_the_packaged_policy` и `test_write_actions_follow_the_role_matrix_and_are_human_only[notification.preference.manage]` | Exit 0, 3 passed за 7.63 с после обновления тестов. Первые два теста до обновления выявили FK-проверку перед trigger и пропущенный action в матрице. |
| `infra/.venv/bin/python -B -m pytest -q -p no:cacheprovider infra/tests/test_g02_credentials.py infra/tests/test_secrets_dev_identity.py` с OpenSSL 3 в PATH | Exit 0, 28 passed. Изолированные материалы, стабильный повтор, exact leaf/EKU, защита файлов и fail-closed recovery. Дополнительно изолированный реальный SOPS/age roundtrip подтвердил совпадение базового пакета и сохранение отзыва, после восстановления активных pins 0. |
| `infra/.venv/bin/python -B -m pytest -q -p no:cacheprovider infra/tests --ignore=infra/tests/runtime` с OpenSSL 3 в PATH | Exit 0, 245 passed. Runtime этого набора проверялся отдельным защищённым Compose. |
| `make infra-check infra-scan-secrets` | Exit 0, 4 модели с 0 нарушений, 0 находок сканера. |
| `make contracts-check contracts-test` | Exit 0, 6 gates и 51 passed. |
| `make backend-check` | Exit 0 после последних изменений. Ruff, mypy 284 исходных файла, 15 контрактов импортов выполнены. |
| `make backend-test` | Полный прогон первоначальной версии двух тестов завершился exit 2 у Make (pytest exit 1). 3402 passed, 2 failed, 4 skipped, 540 предупреждений за 1255.86 с. Четыре пропущенных варианта native runtime прошли в отдельных конфигурациях выше. Два падения воспроизведены и исправлены в тестовом коде. Повтор затронутых проверок дал 3 passed. Полного прогона после этих двух исправлений нет. |
| `make backend-audit` | Exit 0, known vulnerabilities 0 в locked runtime set. |
| `make infra-verify-digests` и `make renovate-check` | Exit 0. 21 registry pin с 0 расхождений. Renovate 10 passed, 0 failed, 0 skipped. |
| `actionlint -color` и `hadolint --failure-threshold error backend/Dockerfile infra/images/caddy/Dockerfile infra/images/minio/Dockerfile` | Exit 0 локально. Hadolint показал одно предупреждение и одну справочную строку в существующем MinIO Dockerfile. |

Независимое ревью ADR-182 подтвердило 0 открытых CRITICAL/HIGH после
ограничения объёма запросов, шифрования курсора, повторной авторизации PUT
и разделения транзакций обязательной доставки и сводок. Остаётся MEDIUM
по скорости поиска недоставленных событий в длинной истории получателя.
[Материалы ревью](../reviews/G02_S17_S20_REVIEWS.md).

Срез использует новый WORKING контракт уведомлений и существующие private
ar2/Temporal контракты. Canonical документы в текущем проходе не правились.
Compose Linux job включает сборку полных backend/native образов и отдельный
запуск сценария. Публичный app и штатный Manager остаются отдельными от
синтетической фикстуры. Проверки `G-107`, `make pre-pr` и Linux CI на итоговом
SHA нужны для общего статуса. Общий локальный проект содержит запущенный
relay G156 и занимает фиксированную app сеть. В этом проходе использованы
отдельные проекты и база. Git-доставка остаётся общей задачей группы.

## Native runtime, private Platform bind и решения S20 · 2026-11-23

**Статус:** отдельный транспортный срез TESTED. S20/S21 и G02 **IN_PROGRESS**.
Проверен рабочий diff на `feat/g02-tool-registry-manager`,
HEAD `7f0c29f9519217dba722ad1f5b6396d8a02216da`. `git ls-remote --heads origin main`
вернул тот же SHA. Исходные локальные правки и новые файлы G02 сохранены.

- `infra/temporal_auth_poc/`: выделены `probe_main.go` и `runtime_main.go`,
  общий native authorizer, tagged tests, Docker target, smoke Compose и запуск.
- Platform использует `AI_RES_PLATFORM_LISTENER_BIND_HOST` из проверенного
  Settings. Тесты проверяют не только валидатор, но и фактический адрес
  listening socket в сетевом сценарии. Go runtime предъявляет отдельную
  identity к приватному Backend auth-control.
- `.github/workflows/ci.yml` собирает новую цель и содержит отдельный smoke.
  Изменения API, contract schemas, миграций, ролей и пользовательских данных
  в данном срезе отсутствуют. `active` сохраняется с прежними четырьмя shards.
  Temporal может обновить адрес RPC `active` на `temporal-workflow:7233` при
  штатном переключении. История существующих инсталляций в этом срезе не
  переносилась и не воспроизводилась.
- ADR-182 фиксирует внутренний канал уведомлений и условие допуска истории.
  Группировка уже проверена. Серверная доставка требует приватной персональной
  проекции и предпочтений. История v0.4 проверена на точном подписанном Run с
  записями неклассифицированных ответов, без данных об исключённых записях.

Среда: Darwin arm64 и Docker 29.2.0 linux/arm64, Compose 5.0.2, PostgreSQL
16.15, Temporal 1.29.7, Go 1.25.11, Python 3.13.5. Native image digest
`sha256:6bd63208c7502206ce06595376cfccefd8a561c64c5ded51b7918f4de5107e8d`.

| Команда | Результат |
|---|---|
| `docker build --target native-runtime -t ai-res/temporal-native:g02-local infra/temporal_auth_poc` | Exit 0. Исходник и locks проверены, Linux ARM64 binary собран без сети на build step и без ELF interpreter. |
| `docker build --target postgres-test -t ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Tagged test image собран из того же pinned source. |
| `go test -p 4 -json -count=1 -tags temporal_runtime ./cmd/aires-auth-poc`, то же с `-tags temporal_postgres_probe` в проверенном upstream source tree с расширением | Exit 0. 21 PASS runtime. 20 PASS и 1 fixture skip в отдельном tagged-прогоне. Fixture исполнен в Compose ниже. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --native-runtime` | Exit 0, 5 групп assertions. Создание `ai-res`, frontend mTLS, deny неактивной и fixture identity, отказ Worker в namespace RPC, привязка сети, отзыв в живом соединении и ID namespace после restart. |
| `python3 -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0, 1 PASS. Real PostgreSQL/Temporal, ar2 Manager/Plan, утверждённый Plan → Task и пагинация/replay. Сетевой Platform listener проверен на одном фактическом private socket. |
| Та же команда с `--lose-start-response --paginate-history --manager-timeout` и `--replay-exhausted-start --paginate-history` | Exit 0 в обоих случаях, 1 PASS на вариант. Потеря ответа и дедупликация Start, post-ACK timeout, карантин и подтверждённый replay с MFA. |
| `make pre-push-fast` | Exit 0, Ruff PASS, mypy 281 файл, import-linter 15 kept, 1977 PASS, 0 fail/skip. |
| `make contracts-check contracts-test` | Exit 0, все 6 валидаторов, 51 PASS, 0 fail/skip. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_platform_manager_commands.py backend/tests/unit/test_proactive_messages.py --tb=short` | Exit 0, 11 PASS, 0 fail/skip. |
| `infra/.venv/bin/ruff check infra/temporal_auth_poc`, `python3 -B infra/scripts/scan_secrets.py`, `git diff --check` | Exit 0, 0 находок сканера. |
| `python3 -B docs/implementation/tools/check_prompts.py` | Exit 1, 41 prompt, 14 замечаний к SLICE-01, идентичных чистому HEAD. Исправлены 3 ссылки на старые canonical версии из рабочего diff G02. |

Review: отдельные code и security проходы, повторная проверка замечаний об
отзыве в полёте, форме probe-history отрицательного теста и таймауте подключения
к БД. Нет открытых CRITICAL/HIGH в этом срезе. Bind проверен теми же ролями
отдельно. [Ревью](../reviews/G02_S17_S20_REVIEWS.md).

Обновлены паспорт, статус, handoff, ADR, решения, gaps, ECC и requirements
traceability. Штатное подключение Backend auth-control к standalone image,
переход с уже записанной историей, G-107 в штатном стеке и приёмка доставки
уведомлений открыты. `make pre-pr`, публикация и обязательный Linux CI относятся
к общему итоговому diff после их реализации. Платные вызовы отсутствуют.

## Явный allowlist reconciliation · ADR-180 · 2026-11-21

`BoundStartSchedule` содержит `admitted_operation_types`: уникальный
непустой список, ограниченный типами назначенных workflow. Планировщик
передаёт один и тот же набор в pre-ACK и post-ACK reconciliation;
`include_post_ack` включает дополнительную фазу проверки и не расширяет
множество типов. Plan Execution перечисляется явно. Legacy-конфигурация
без поля сохраняет только `MANAGER_MESSAGE`. Loader отвергает повторные
JSON object keys, чтобы дублирующийся allowlist нельзя было интерпретировать
по-разному.

Изменены `backend/src/ai_res/application/reconcile_scheduler.py`,
`backend/tests/unit/test_reconciliation_scheduler.py` и сценарии в
`backend/tests/integration/postgres/test_manager_http.py` и
`test_native_assigned_workflow.py`. API, публичные/внутренние контракты,
миграции и данные не менялись.

### Проверки

| Команда | Результат |
|---|---|
| `backend/.venv/bin/ruff check backend/src/ai_res/application/reconcile_scheduler.py backend/tests/unit/test_reconciliation_scheduler.py backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_native_assigned_workflow.py` | Exit 0, все проверки прошли. |
| `backend/.venv/bin/mypy --follow-imports=silent backend/src/ai_res/application/reconcile_scheduler.py` | Exit 0, no issues. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -q backend/tests/unit/test_reconciliation_scheduler.py --tb=short` | Exit 0, 17 passed. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -q backend/tests/integration/postgres/test_manager_http.py::test_reconcile_real_terminated_plan_after_ack --tb=short` | Exit 0, 1 passed; PostgreSQL + Temporal test fixture. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --manager-timeout --paginate-history` | Exit 0, 1 passed, 42.49 с; изолированный PostgreSQL/native Temporal, Plan post-ACK и Manager timeout в одной композиции. |
| `backend/.venv/bin/python -B infra/scripts/scan_secrets.py` | Exit 0, 0 findings. |
| `git diff --check` | Exit 0. |

Blind-first code и security review выявили и закрыли: переиспользование Plan
allowlist в Manager leg, связанность unit-тестов со старым поведением и
недостаточно валидный duplicate-key fixture. Оба финальных review — APPROVE.
`make pre-pr` и Linux CI не запускались; этот локальный срез не VERIFIED и
не закрывает G-107 или G02.

## Следующий блок: native Temporal target для Compose

Сегодняшняя сверка pinned PoC и штатного Compose установила:
`infra/temporal_auth_poc/Dockerfile` собирает default `sqlite-probe` с
`validateProbeConfig`, требующим SQLite; PostgreSQL entrypoint находится
в `postgres_probe_test.go` за Go test build tag. Штатный `infra/compose.yaml`
использует pinned `temporalio/server:1.29.7` без frontend client-auth и
native authorization configuration. Fixed namespace/queue/SPIFFE names в
PoC относятся к `auth-poc` и не являются target-конфигурацией AI RES.
Production binary, штатные secret mounts и network topology этим срезом не
добавлялись и не проверялись. Следующий шаг — выделить non-test native server
entrypoint с PostgreSQL plugin и production identity profile; покрыть его
конфигурационную валидацию, затем проверить целевую Compose топологию до её
включения. G-104/G-106/G-107/G-111 и общие gates остаются открытыми.

## Изоляция ключа назначенной доставки · ADR-179 · 2026-11-21

### Реализация

Для NCP-19 добавлена отдельная пара Ed25519 для Outbox-to-Backend:
`outbox_delivery_signing_key` предназначается для отдельного secret mount Dispatcher,
а производный `assigned_delivery_public_keys` содержит allowlist только
`OUTBOX_DISPATCHER`. Listener использует новый типизированный setting и при
старте отвергает смешанный issuer registry. Общий `service_public_keys`
не меняется. Dev-secret migration сохраняет непустые прежние значения,
добавляет согласованную пару при upgrade и отказывает до записи при registry
без seed или несовпадающем keypair. Отсутствующий public registry
восстанавливается из имеющегося seed; whitespace сравнивается как токены,
оригинальные строки реестра не переписываются.

### Изменённые файлы

`backend/src/ai_res/platform/config.py`,
`backend/src/ai_res/api/serve_assigned_delivery.py`,
`backend/tests/integration/postgres/test_native_assigned_workflow.py`,
`backend/tests/unit/test_assigned_dispatch.py`,
`infra/scripts/secrets_dev.py`, `infra/tests/test_secrets_dev_identity.py`,
`docs/implementation/ARCHITECTURE_DECISION_LOG.md` (ADR-179),
`docs/implementation/KNOWN_GAPS.md`,
`docs/implementation/ECC_USAGE.md`, `docs/implementation/IMPLEMENTATION_STATUS.md`,
`docs/implementation/CONTEXT_HANDOFF.md`, `docs/implementation/groups/G02_WORK.md`,
`docs/implementation/reviews/G02_S17_S20_REVIEWS.md` и этот отчёт.

API/contract и persistence schema не менялись; migration не требуется.

### Проверки и review

| Команда / review | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_assigned_dispatch.py` | Exit 0, 11 passed. Покрыты mixed issuer deny и rotation того же issuer. |
| `infra/.venv/bin/python -B -m pytest -q infra/tests/test_secrets_dev_identity.py` с OpenSSL 3 в PATH | Exit 0, 12 passed. Проверены legacy upgrade, preservation, partial/mismatch fail-closed и совместимая whitespace нормализация. |
| Backend Ruff + mypy | Exit 0; 281 source files, no issues. Import-linter: 15 kept, 0 broken. |
| Infra Ruff + `infra/scripts/scan_secrets.py` | Exit 0; 0 secret findings. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` с OpenSSL 3 | Exit 0; 1 networked native PostgreSQL/Temporal scenario passed, 21.49 s. Compose проект и сети удалены cleanup-ом. |
| Независимые blind-first `epic_review`, `epic_security` | APPROVE/APPROVE после исправления findings; review запись ниже. |

Полный `make pre-pr` и Linux CI для общего G02 diff не запускались. Compose
secret mounts и native Temporal wiring штатного стека остаются следующим
срезом. Этот результат — локально TESTED компонент ADR-179, не VERIFIED G02.

## Межпроцессная доставка по активному lease · NCP-19 / ADR-178

DOC-087, DOC-068 v1.7, Registry и manifest v1.9 описывают защищённый
POST `/internal/assigned-delivery/v1`. Отдельный Backend listener
`api.serve_assigned_delivery` принимает запрос от `OUTBOX_DISPATCHER`.
Штатный `cli.dispatcher` в защищённом режиме отправляет ar2 подпись
точного lease. Namespace определяется доверенной конфигурацией.
Команда использует только row ID, владельца, попытку и поколение.
Backend получает событие из базы и сам вызывает Temporal.

Миграция 0054 `28a56a9341ce` добавляет узкий SQL EXECUTE Backend,
nonce для нового audience и audit допуска. Функция блокирует строку
lease до commit и повторно сверяет сроки после ожидания. Лишние поля,
чужое назначение, повтор подписи, смена и истечение lease дают отказ.
Неверный namespace не приводит к Temporal RPC. Транзакция закрывается
до вызова Temporal. Legacy wire и публичный API сохранены.

| Команда | Результат |
|---|---|
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_{assigned_delivery_api,native_auth_control,migrations,schema_drift,audit_platform_schema}.py --tb=short` | Exit 0, 42 passed, 0 failed/skipped, 43,20 с. Реальные SQL роли, rollback и гонка lease, grants/RLS, empty/previous upgrade и drift. Одно прежнее предупреждение `xid8`. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0, 1 passed, 20,24 с. Два процесса, потеря 204 после Start, lease следующей попытки, тот же Run, отказ позднего mark и один Cancel. |
| Та же команда с `--replay-exhausted-start` | Exit 0, 1 passed, 10,46 с. Регрессия существующего подтверждения повтора из карантина. |
| `make -j1 pre-push-fast contracts-check contracts-test` | Exit 0 по этим targets, 1966 быстрых, 51 контрактный, 6 валидаторов, mypy 281 файл и 15 import contracts. Три прежних предупреждения OTel. |
| `make -j1 backend-check infra-scan-secrets` | Exit 0 после разделения извлечения Bearer-схемы и токена, 0 findings. |
| `make -j1 infra-check` | Exit 0, во всех четырёх вариантах Compose 0 violations. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff.
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7,
Docker 29.2.0. Make использовал
`UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1`.
Повторные code и security review дали APPROVE.
[Ревью](../reviews/G02_S17_S20_REVIEWS.md).

Проверка двух процессов выполняется в одном изолированном probe-контейнере
с разными SQL roles и настройками. Для целевого стека остаются проверка
раздельных secret mounts, сетей и активации producer. Linux CI
обновлён для проверки нового сценария на итоговом SHA.
Полный `make pre-pr` и Linux CI остаются общими gates G02.

## Backend-композиция назначенной доставки · ADR-177

`application/assigned_dispatch.py` соединяет существующие Backend
prepare/bind с native Start и Cancel. Run берётся из ответа
защищённого frontend. Код Backend принимает запись от доверенного
claim и сверяет `dispatch_namespace` перед любым I/O. Outbox role
обрабатывает lease и публикацию, Backend role проверяет и обновляет
назначение. Отдельные mTLS-клиенты должны указывать на тот же доверенный
endpoint, CA и namespace. Bearer-credentials отклоняются. SAN и RPC
проверяются native frontend.

`outbox_repository.py` возвращает внутренний namespace вместе с
арендованной записью. Сетевой тест заменяет ручные callbacks на новый
Backend-компонент для Start и Cancel. Подтверждены один Run после
потери ответа, отказ чужого namespace, replay из карантина, повтор
завершённой отмены без RPC и допуск отмены Plan. Миграций в этом срезе
нет, event wire и публичные контракты сохранены.

| Команда | Результат |
|---|---|
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history` | Exit 0, 1 passed, 11,78 с. Повтор того же Run и Cancel без повторного сигнала после settlement. |
| Та же команда с `--replay-exhausted-start` вместо `--lose-start-response` | Exit 0, 1 passed, 11,64 с. Повтор из карантина с точной привязкой Run. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_{event_delivery,orchestration_e2e,schema_drift}.py --tb=short` | Exit 0, 33 passed, 0 failed/skipped, 24,36 с. Outbox, оркестрация и отсутствие schema drift. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` | Exit 0, 1966 быстрых, 50 контрактных, 6 валидаторов, mypy 275 файлов, 15 import contracts, 0 findings. Три существующих предупреждения OTel. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff.
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7,
Docker 29.2.0. Make использовал
`UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1`.
Независимые code и security review дали APPROVE после исправлений.
[Ревью](../reviews/G02_S17_S20_REVIEWS.md).

Стенд вызывает Backend внутри процесса и использует отдельные DB
роли. Для штатного запуска в разных процессах требуется утверждение
узкого доступа по активному lease и private ar2-контракта.
`make pre-pr` и Linux CI остаются общей приёмкой. G02 **IN_PROGRESS**.
[NCP-19](../decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-19--передача-защищённой-записи-outbox-в-backend).

## Namespace назначенного Outbox · ADR-176

Миграция 0053 `7c4cb218720a` добавляет внутренние
`dispatch_assignment_id` и `dispatch_namespace` к Outbox. Отложенный
составной FK сверяет tenant, Operation и точное назначение. Manager,
Plan и Cancellation заполняют поля в транзакции записи события.
`DispatcherConfig` обеспечивает одну область для захвата lease и
карантина после истечения попыток. Обычный диспетчер исключает
назначенные Start и Cancel. Event wire и публичные API не затронуты.

Backfill восстанавливает namespace только при точной единственной
ссылке. Историческая незавершённая запись без маршрута попадает в
карантин с `OUTBOX_ROUTE_UNRESOLVED`. Новая активная запись обязана
иметь маршрут. Replay проверяет сохранённую связку и оставляет
недоказанные записи в карантине. Проверены обычный режим, две области
защищённых Start/Cancel, истёкшие lease, отказ неверного namespace,
поздняя запись прежнего producer и запрет менять поле под Outbox role.

| Команда | Результат |
|---|---|
| Из `backend` `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q tests/integration/postgres/test_{orchestration_e2e,event_delivery,migrations,schema_drift,audit_platform_schema,platform_manager_commands}.py --tb=short` | Exit 0, 72 passed, 0 failed/skipped, 57,03 с до финального ограничения записей без маршрута. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_{migrations,schema_drift,audit_platform_schema}.py --tb=short` | Exit 0, 40 passed, 0 failed/skipped, 44,62 с после исправления. Empty/previous upgrade, точный backfill, RLS/grants и drift. Одно существующее предупреждение `xid8`. |
| Та же команда с `UPDATE_SCHEMA_SNAPSHOT=1` и одним тестом `test_schema_drift.py::test_migrated_schema_matches_committed_snapshot` | Exit 0, ожидаемый 1 skip при генерации, 6,97 с. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` | Exit 0, 1 passed, 12,01 с, штатное разрешение replay и точный повтор в выбранном namespace изолированного native Temporal. |
| Та же команда с `--lose-start-response` вместо `--replay-exhausted-start` | Exit 0, 1 passed, 10,24 с, повтор после потери ответа, проверка назначенного Cancel и replay History. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` | Exit 0, 1957 быстрых, 50 контрактных, 6 валидаторов, mypy 274 файла, 15 import contracts и 0 findings. Три существующих предупреждения OTel. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff.
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7,
Docker 29.2.0. Make использовал `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1`.
Независимые code и security review дали APPROVE после исправлений.
[Ревью](../reviews/G02_S17_S20_REVIEWS.md).

Для активации защищённого штатного dispatcher требуется совместное
подключение producers с 0053, клиента нужного namespace и доверенного
Backend prepare/bind. `make pre-pr` и Linux CI относятся к приёмке
всего G02. S20/S21 **IN_PROGRESS**.

## Private v5 и неизменяемый снимок для Proposal · ADR-175 · 2026-11-21

DOC-086 v0.5, DOC-068 v1.6, Registry и manifest v1.8 закрепляют
версионные private маршруты и минимальные SQL-права. Изменены
`api/platform_v2.py`, `application/platform_control.py`,
`application/platform_manager.py`, ar2 credential/client и Manager
Activity. `orchestration/manager_context.py` проверяет закрытую форму
ответа. Если открыт первичный вопрос, Activity не записывает второй.
Снимок и его идентификатор остаются внутри Activity и Backend.

Миграция 0052 `4dd4da8ee5c2` после 0051 добавляет таблицу с FORCE RLS,
две узкие SQL-функции и nullable FK Proposal. Функция выдачи блокирует
точные назначение и Operation, сохраняет первый снимок и аудит
атомарно. Повторы того же Run возвращают первоначальный снимок.
`manager_proposal_versions.context_version_id` входит в SHA-256 v5.
Существующие Proposal сохраняют данные и хеши. Роль Platform имеет
только EXECUTE функций и INSERT ссылки. Попытка legacy записи после
выдачи, чужое или отозванное назначение, неверный Run и срок действия
подтверждены негативными тестами. Публичный API и AsyncAPI сохранены.

| Команда | Результат |
|---|---|
| Из `backend` `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q tests/integration/postgres/{test_platform_manager_commands,test_manager_intake,test_migrations,test_schema_drift,test_audit_platform_schema}.py tests/integration/test_platform_control_tls.py --tb=short` | Exit 0, 46 passed, 0 failed/skipped, 40,61 с. Empty/previous upgrade, digest v3/v5, RLS/grants и drift. Одно существующее предупреждение `xid8` в scratch schema. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" UPDATE_SCHEMA_SNAPSHOT=1 PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_schema_drift.py::test_migrated_schema_matches_committed_snapshot -rs` | Exit 0, ожидаемый 1 skip при генерации. Проверка без флага прошла в предыдущем наборе. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0, 1 passed, 8,38 с. Обязательная запись ссылки точного Run и проверка отсутствия снимка в History. |
| Та же команда с `--replay-exhausted-start` | Exit 0, 1 passed, 8,20 с. Replay с проверкой v5. |
| Та же команда с `--lose-start-response` | Exit 0, 1 passed, 10,04 с. Точный Start, отмена и replay с v5. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --manager-timeout` | Exit 0, 1 passed, 41,99 с. Таймаут Activity после ACK и сверка точного Run. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` | Exit 0, 1957 быстрых тестов, 50 контрактных, 6 валидаторов, Ruff чист, mypy 273 файла, 15 import contracts, 0 findings. Три существующих предупреждения OTel. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff,
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7,
Docker 29.2.0. Make использовал `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1`.
Два независимых повторных review дали APPROVE после исправления SQL-пути.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

v5 работает в изолированном защищённом контуре. Штатная композиция
ADR-129/G-107, отдельный допуск содержания v0.4, доставка уведомлений,
`make pre-pr` и Linux CI остаются открытыми. S20 и G02 **IN_PROGRESS**.
Штатный dispatcher забирает только обычные Start/Cancel. Для назначения
в сетевом стенде операции prepare/bind выполняет доверенный Backend,
а отдельная Outbox identity доставляет intent. При штатном подключении
этим операциям нужна Backend-граница с подтверждением точного Run.

## Минимальная PostgreSQL-проекция назначенного Epic · ADR-175 · 2026-11-21

`modules/readmodel/manager_epic.py` формирует отдельный SQL-снимок Epic
из разрешённых метаданных. Общие связи intake, вопросов, плана и задач
используются двумя проекциями. Узкий запрос читает версию и состояние
указанной Operation, статусы, признак открытого вопроса и счётчики.
Интеграционный тест проверяет изменение версии снимка после перехода
именно этой Operation, стабильность версии соседней Operation и изоляцию
организаций и проектов. В той же одноразовой БД чтение работает после
отзыва широких SELECT на Epic и Proposal и выдачи SELECT на пять
колонок Epic.

| Команда | Результат |
|---|---|
| `cd backend && PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q tests/integration/postgres/test_manager_intake.py tests/unit/test_proactive_messages.py` | Exit 0, 12 passed, 0 failed/skipped, 7,13 с после уточнения теста по review. |
| `make -j1 backend-check backend-test-unit` | Оба target exit 0, Ruff чист, mypy 271 файл, 15 import contracts, 1956 passed, 0 failed/skipped, 3 существующих предупреждения OTel. |
| `make -j1 contracts-check contracts-test infra-scan-secrets` | Exit 0, 6 валидаторов, 48 passed, 0 failed/skipped, 0 findings. |
| `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0, 1 passed, 0 failed/skipped, 8,28 с. Regression существующего Manager/Plan пути и replay в изолированном PostgreSQL/Temporal. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff.
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7,
Docker 29.2.0. Команды Make выполнялись с
`UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1`.
Code и security review выполнены независимо и read-only. Замечание
по различению двух Operation покрыто дополнительным сценарием.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

В NCP-18 описаны совместимые DOC-086 v0.5 и DOC-068 v1.6. Для выпуска
в `docs/architecture/` ожидается явное указание по AGENTS.md §8.
Private wire, сохранение версии выдачи и её связь с Proposal
остаются открытыми. Этот срез ограничен внутренней проекцией:
runtime API, миграций и штатных grants в нём нет. Общий `make pre-pr`
и Linux CI относятся к итоговой приёмке группы. G02 остаётся
**IN_PROGRESS**. [NCP-18](../decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-18--версия-состояния-epic-для-manager).

## Решения по replay и контексту Epic · ADR-174/175 · 2026-11-21

По делегированию владельца назначенный Start из карантина подтверждает
действующий `PROJECT_ADMIN` своего проекта с MFA. WORKING OpenAPI
добавляет проверку точной записи и `If-Match` для утверждения поколения.
Миграция 0051 (`a47ca6b2015f`) блокирует прямой выход из карантина под
ролью диспетчера. Узкая функция блокирует и заново проверяет полномочия,
MFA-сессию, назначение, операцию и Outbox. Срок сессии проверяется после
захвата Outbox. Аудит подтверждения сохраняется вместе с изменением очереди.

Backend строит `AssignedEpicMetadata` для указанной Operation и Epic.
Версия зависит от разрешённых статусов, счётчиков и двух refs. Повторное
чтение в PostgreSQL воспроизводит версию. При появлении нового intake
старое назначение получает метаданные собственной Operation. Private
выдача и привязка точного снимка к Proposal входят в оставшийся ADR-175.

| Команда | Результат |
|---|---|
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` | Exit 0, 1 passed, 11.38 с. Отклонены прямой UPDATE диспетчера, Analyst, администратор без MFA, отозванная сессия и неверный event ID. Точное утверждение дало одну audit-запись и один Temporal Run. Повтор с тем же ключом идемпотентен. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_manager_intake,test_platform_manager_commands}.py --tb=short` | Exit 0, 4 passed, 12.23 с. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_policy_engine.py -k 'approve_start_replay or matrix_covers_every_action' --tb=short` | Exit 0, 2 passed, 183 deselected, 11.02 с. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_migrations,test_schema_drift,test_audit_platform_schema}.py --tb=short` | Exit 0, 38 passed, 52.09 с. Empty/previous upgrade, grants и schema drift после 0051. Одно существующее предупреждение scratch `xid8`. |
| `make -j1 pre-push-fast contracts-check contracts-test` | Exit 0, 1956 быстрых и 48 контрактных тестов, 271 source files mypy и 15 import contracts. Прогон до финального уточнения блокировок и typed Epic metadata. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff, Darwin
arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7.
Два read-only review закрыли замечания по policy matrix, Session/MFA,
проверке срока после ожидания, аудиту GET и формам API.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

## Отмена до ACK, версия Epic и группировка · ADR-171–173 · 2026-11-21

Сверка точного `CANCELLED` до ACK проверяет назначение и версию Operation
под блокировками, требует сохранённый запрос и подтверждает отсутствие
активного WorkerRun. Manager и Plan используют прежнее доменное подтверждение
отмены. Транзакция сохраняет переход, событие, Outbox и аудит. Два read-only
review дали APPROVE.

Backend строит версию проекции Epic из одного снимка PostgreSQL. Версия
воспроизводится после чтения в новой транзакции и учитывает изменившиеся
вопросы, Plan и Task при том же `epic_version`. Передача Manager ожидает
NCP-18. Отдельный планировщик сгруппировал заранее допущенные ссылки для
одного получателя и проекта. Проверены дубли, интервал после предыдущей
доставки, обязательные события, смешение scope и переход летнего времени.
Канал и журнал доставки относятся к штатному подключению.

| Команда | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_operation_execution_assignments,test_native_auth_control,test_orchestration_e2e}.py backend/tests/unit/{test_operation_reconciliation,test_reconciliation_scheduler}.py --tb=short` | Exit 0, 41 passed, 17.83 с. PostgreSQL и типизированный двойник observer для terminal CANCELLED. До правки два новых сценария Manager/Plan показали отсутствие коррекции. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_manager_intake,test_platform_manager_commands}.py --tb=short` | Exit 0, 4 passed, 8.08 с. PostgreSQL rebuild, версия и tenant scope. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/unit/test_proactive_messages.py --tb=short` | Exit 0, 9 passed, 0.03 с после нормализации UTC и обработки будущих событий. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history` | Exit 0, 1 passed, 10.73 с. Реальные native Temporal, PostgreSQL, повтор Start, Manager/Plan отмена и History replay. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` с `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1` | Exit 0, 1954 быстрых и 48 контрактных тестов, 269 файлов mypy, 15 import contracts, 0 findings. Два дополнительных теста UTC и будущих событий проверены отдельно. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_operation_execution_assignments.py -k confirmed_cancellation_before_ack --tb=short` | Exit 0, 6 passed, 13 deselected, 9.68 с. Проверены отзыв назначения во время наблюдения и отсутствие cancel action. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history --manager-timeout` | Exit 0, 1 passed, 43.99 с. Сценарий для Linux CI проверен локально на изолированном native Temporal с реальным timeout. |
| `make -j1 infra-check infra-test infra-scan-secrets` с OpenSSL 3.6.3 в `PATH`, локальными uv-флагами и `PYTEST_ADDOPTS=--tb=short` | Exit 0, 224 passed, 148 runtime skipped, 10.16 с, 0 findings и 0 нарушений Compose. Первый прогон с LibreSSL 3.3.6 дал один отказ на Ed25519. |
| `actionlint .github/workflows/ci.yml`, `git diff --check`, Compose `config --images` для двух candidate-файлов | Exit 0. Обе native проверки добавлены в Linux job `backend`. Два внешних образа указаны по digest. Linux CI по итоговому SHA остаётся этапом общей доставки. |
| Повтор `make -j1 pre-push-fast contracts-check contracts-test` после UTC и дополнительных сценариев authority | Exit 0, 1956 быстрых и 48 контрактных тестов, 269 файлов mypy, 15 import contracts. Три существующих предупреждения OTel. |
| `make backend-test` с теми же uv-флагами | Прерван после остановки вывода на сборке тестового образа Bifrost, exit 2 после SIGINT. До прерывания 1351 passed, 3 skipped, 537 warnings, 877.06 с. Отдельно dev Temporal suite дал 4 и 12 passed, private TLS suite — 17 passed. |
| `PYTHONUNBUFFERED=1 backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/test_*.py --tb=short -o faulthandler_timeout=90` | Exit 0, 97 passed, 340.90 с. Отдельный прогон подтвердил текущий Bifrost fixture и остальные верхнеуровневые интеграции. Локальный label тестового образа совпал с digest входов. |

База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff.
Darwin arm64, Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7.
Изменены `application/reconcile_operations.py`,
`modules/operations/orchestration_service.py`,
`modules/readmodel/manager_epic.py`, добавлен
`application/proactive_messages.py`, расширены соответствующие тесты.
В `infra/scripts/secrets_dev.py` проверен формат SPKI Ed25519 и
сокрытие вывода дочернего процесса при ошибке. В `.github/workflows/ci.yml`
добавлены изолированные native проверки потери Start, истечения Manager
Activity и replay из карантина. Продуктовые схемы и миграции на этом шаге
не обновлялись. Полный `pre-pr` требует завершающего среза группы.
Локальную повторную сборку двух native-образов остановили на ожидании
метаданных registries. Контейнерные сценарии выполнены с ранее собранными
локальными образами. Чистая сборка текущего workflow относится к Linux CI.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

## Сверка до ACK и граница контекста v0.4 · 2026-11-21

Сверка подбирает привязанное назначение в `CANCEL_REQUESTED` до ACK.
Подтверждённый сбой exact Run переводит Operation в `FAILED` с одним
событием и аудитом по существующему правилу ADR-149. Повторное чтение
binding и версии остаётся обязательным. Неоднозначные наблюдения
сохраняют статус.

Негативный тест v0.4 записал разрешёнными командами проекта вопрос,
резолюцию и сообщение с неклассифицированным ответом. Private Activity
получила только назначенное сообщение. Предыдущая запись отсутствует
в массиве и признаке усечения. Передача версии проекции Epic в Manager
описана в [NCP-18](../decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-18--версия-состояния-epic-для-manager).

`backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_platform_manager_commands,test_manager_intake,test_operation_execution_assignments}.py backend/tests/unit/{test_operation_reconciliation,test_reconciliation_scheduler}.py --tb=short`
— exit 0, 39 passed, 0 failed/skipped, 14.46 с. PostgreSQL 16.15, Darwin
arm64, Python 3.13.5, база `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
Проверка pager и доменной транзакции использует типизированное наблюдение
Temporal в тесте. Реальный native cancel и точная авторизация статуса
проверены сценариями ADR-168/170.

## Точечный replay исчерпанного Start · G-107 · 2026-11-21

На PostgreSQL/Temporal проверен сценарий отказа между допуском в Backend и
отправкой RPC. Диспетчер исчерпал тестовый бюджет доставки и перевёл точную
запись в `QUARANTINED`. После `OutboxRepository.replay` по одному event ID
прежнее назначение получило один подтверждённый Run. Outbox перешёл в
`PUBLISHED` с `replay_count=1`, исходная Operation завершилась и её
Temporal history воспроизвелась. Вызов оператора в стенде выполнен под
реальной Outbox role. Продуктовое разрешение replay остаётся WORKING.

`env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --replay-exhausted-start --paginate-history`
— exit 0, 1 passed, 0 failed/skipped, 11.03 с. База
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff. Darwin arm64,
Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7, Docker 29.2.0.
Флаг доступен только в изолированном тестовом launcher.

Если повтор снова исчерпан и Run остаётся недоказанным, Operation
сохраняет прежний доменный статус. Политика подтверждения оператором
перед штатным replay и общий G-107 остаются OPEN.
[Решения владельца](../DECISIONS_PENDING.md).

## Ранняя отмена назначенного Start · ADR-170 · 2026-11-21

Доверенный Backend фиксирует `start_admitted` под блокировкой точного
назначения перед RPC. Native auth-control проверяет признак и старый
Outbox intent только на чтение. Миграция 0050 (`de184e3c4a21`) добавляет
однонаправленный флаг и право обновить эту колонку у tenant Backend.
Ранее существовавшие назначения учитываются как потенциально допущенные.
Новых прав у Temporal, Manager и Outbox роли нет.

Если выигрывает отмена, операция после HTTP 202 становится `CANCELLED`,
а точный Start intent обрабатывается без RPC. После допуска до Run binding
API возвращает стандартный `409 OPERATION_NOT_READY` без записи отмены.
Повтор тем же ключом после binding проходит через `QUEUED` в
`CANCEL_REQUESTED` и доставляет точный сигнал. Публичная схема сохранена.

**Evidence.** Ветка `feat/g02-tool-registry-manager`, база
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff. Darwin arm64,
Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7, Docker 29.2.0.

| Команда | Результат |
|---|---|
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history` | Exit 0, 1 passed, 0 failed/skipped, 17.12 с. Реальный Start до binding, 409, повтор exact Start, 202 с тем же idempotency key, точный сигнал и replay. При отмене до допуска проверены отказ native RPC, отсутствие Run и завершение обработчика Outbox без RPC. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_native_auth_control,test_migrations,test_schema_drift,test_orchestration_e2e,test_manager_http,test_operation_execution_assignments}.py --tb=short` | Exit 0, 44 passed, 0 failed/skipped, 72.18 с. Empty и previous upgrade, snapshot, grants/RLS и native admission. Одно прежнее предупреждение про `xid8` в scratch schema. Прогон предшествовал точечному изменению SELECT полей Operation, покрытому native fixture выше. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/{test_native_auth_control,test_schema_drift,test_audit_platform_schema}.py --tb=short` | Exit 0, 19 passed, 0 failed/skipped, 15.32 с после изменения SELECT. Alembic head `de184e3c4a21`. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` с `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1` | Exit 0, 1947 быстрых и 48 контрактных тестов, шесть валидаторов, 15 import contracts, 268 файлов в mypy, 0 findings. Три прежних предупреждения OTel. |

Code и security review дали APPROVE после переноса записи допуска в Backend
и проверки cancel-wins. Открыт сценарий отсутствия доказанного Run после
исчерпания доставки. [Review](../reviews/G02_S17_S20_REVIEWS.md).

## Подтверждение первого Run через Start · ADR-169 · 2026-11-21

Защищённый frontend сверяет первое появление точного Workflow и Run,
включая при повторном Start. Проверены тип, очередь, original/first Run и
хэш compact input. Backend повторно сверяет назначение перед binding.
Dispatcher identity получает отказ на внешний History RPC. Auth-control
outage для Start возвращает UNAVAILABLE. Публичные контракты, миграции и
grants в ADR-169 сохранены.

**Evidence.** Ветка `feat/g02-tool-registry-manager`, база
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff. Darwin arm64,
Python 3.13.5, PostgreSQL 16.15, Temporal 1.29.7, Docker 29.2.0.

| Команда | Результат |
|---|---|
| `docker build --progress=plain --target postgres-test --tag ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0, pinned Go 1.25.11, обе Go suites и locks прошли. Manifest `sha256:8aa5c23f986d92bd6925bec4be75bab7fc173dfd10ebc17f808842c1718e0e11`. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history` | Exit 0, 1 passed, 0 failed/skipped, 12.54 с. Первый ответ потерян до binding, retry подтвердил тот же Run. Проверены отрицание History для диспетчера, многостраничная выдача, повтор Outbox и отмена после ACK. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_operation_execution_assignments.py backend/tests/integration/postgres/test_manager_http.py --tb=short` | Exit 0, 17 passed, 0 failed/skipped, 33.47 с. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` с `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1` | Exit 0, 1947 быстрых и 48 контрактных тестов, шесть валидаторов, 15 import contracts, 267 source files mypy, 0 findings. Три существующих предупреждения OTel. Прогон предшествовал сверке Workflow ID и deadline, покрытым native сборкой и сценарием выше. |

Два независимых read-only review дали APPROVE после исправления обработки
outage и сокращения ответа. Штатный Compose и Linux CI ожидают общей
приёмки. [Review](../reviews/G02_S17_S20_REVIEWS.md).

## Точная отмена привязанного Run · ADR-168 · 2026-11-21

Штатная публичная команда отмены записывает доменный `CANCEL_REQUESTED` и
Outbox. Для назначенного Run Outbox использует существующий ref назначения
с точным Run. Legacy consumer оставляет эту запись защищённому маршруту.
Отдельный native mTLS caller может доставить только `request_cancel` без
payload. Auth-control v1.2 проверяет существующие assignment, развёрнутый
namespace, очередь, контракт, Run и статус. Ревизия 0049 (`798e2a4f3d60`)
расширяет допуск записи audit, без новых DB grants. Публичный HTTP 202
по-прежнему означает приём запроса.

**Evidence.** Рабочая ветка `feat/g02-tool-registry-manager`, база
`7f0c29f9519217dba722ad1f5b6396d8a02216da`. Darwin arm64, Python 3.13.5,
PostgreSQL 16.15, temporalio Python 1.36.0, Docker 29.2.0, Compose 5.0.2.

| Команда | Результат |
|---|---|
| `docker build --progress=plain --target postgres-test --tag ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Обе Go suites прошли. Pinned Temporal 1.29.7, Go 1.25.11; locks совпали. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history` | Exit 0, 1 passed, 0 skipped/failed, 11.68 с на срезе отмены. HTTP → Outbox → mTLS native → `CANCELLED` → replay. До intent, для чужого Run и manager identity получен отказ. Два успешных RPC с одним `requestId` дали один сигнал. Повтор Outbox после терминации подтвердил delivery без нового сигнала. |
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_auth_control.py backend/tests/integration/postgres/test_migrations.py backend/tests/integration/postgres/test_schema_drift.py backend/tests/integration/postgres/test_orchestration_e2e.py backend/tests/integration/postgres/test_manager_http.py --tb=short` | Exit 0, 31 passed, 0 skipped/failed, 57.59 с. Одно существующее предупреждение `xid8` в scratch schema. Проверены миграции empty/previous, snapshot, grants/RLS, durable nonce и denied scope. |

Два независимых [review](../reviews/G02_S17_S20_REVIEWS.md) дали APPROVE
на post-ACK. Они выделили HIGH в прежней ветви ранней отмены, когда Start
принят до записи binding. Она блокирует реальную активацию G02. Runtime
и evidence ADR-168 относятся к изолированному Compose и привязанному Run.

## Proposal approval и назначенный START · ADR-166/167 · 2026-11-21

Владелец делегировал роль принимающего решение. Активный `ANALYST` того же
проекта, отличный от автора сообщения, подтверждает exact Proposal с ETag
и SHA-256. GET/POST Proposal добавлены в WORKING overlay. Операция выдаёт
Proposal `resultRef` после проверки ACL на точную версию и связь с Operation.
Plan draft с опциональным `proposalVersionId` проверяет независимое решение,
тот же Epic и совпадение цели и scope. Решение по PlanVersion остаётся
отдельной командой. См. [S21](S21_plan_task_orchestration_REPORT.md).

`modules/events/outbox_repository.py`, `dispatcher.py` и штатный CLI
разграничивают выборку назначенных и неназначенных START по существующему
маркеру. Для claim и lease-expiry quarantine применяется один фильтр.
Существующий event envelope, destination и обязательные проверки assigned
Run сохраняются. Новых миграций, DB grants или изменений canonical нет.

**Evidence.** База `7f0c29f9519217dba722ad1f5b6396d8a02216da`, рабочий diff
`feat/g02-tool-registry-manager`. Darwin arm64, Python 3.13.5, uv 0.11.31,
PostgreSQL 16.15, Docker 29.2.0, Compose 5.0.2 и native Temporal 1.29.7.

| Команда | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_manager_intake.py backend/tests/integration/postgres/test_planning_http.py backend/tests/integration/postgres/test_policy_engine.py backend/tests/integration/postgres/test_orchestration_e2e.py --tb=short` | Exit 0. 198 passed, 0 failed/skipped, 82.83 с. Проверены точное утверждение, автор, Viewer, чужой проект, другой Epic, stale hash, повтор, граница тела, привязка плана, отдельный Plan approval и выдача Tasks. Обе выборки Outbox сохраняют чужие строки и их lease. |
| `env PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response --paginate-history` | Exit 0. 1 passed, 0 failed/skipped, 13.07 с. Изолированный runtime подтвердил assigned claim через новый фильтр, повтор после потери ответа Start и точный Run с многостраничной History. Временный Compose очищен. |
| `make -j1 pre-push-fast contracts-check contracts-test infra-scan-secrets` с `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1` | Exit 0. 1947 быстрых и 47 контрактных тестов, 15 import contracts, шесть валидаторов, 0 findings, 0 failed/skipped. В быстрой проверке три OTel deprecation warnings. |

Два независимых read-only review дали APPROVE после исправлений по размеру и
сроку чтения и сокрытию недоступного `resultRef`. [Review](../reviews/G02_S17_S20_REVIEWS.md).
S20/G02 **IN_PROGRESS**. Остаются штатный защищённый запуск и отмена,
потребление версии проекции, доказательство допуска истории v0.4,
проактивная группировка и общая приёмка. Полные `make pre-pr` и Linux CI
относятся к финальному diff группы. Штатный Compose другого worktree продолжал работу.

## Восстановление состояния Epic · ADR-165 · 2026-11-21

`modules/readmodel/manager_epic.py` собирает текущую проекцию в одном снимке
PostgreSQL. Она содержит версию Epic, ссылки на последнее принятое сообщение
и его Operation, последнюю версию Proposal с исходным interaction и точным
решением, checkpoint вопросов, текущую версию плана и счётчики Task по
существующим статусам. Тексты сообщений, вопросов и комментарии не читаются.

Интеграционный сценарий сравнил состояние до событий, во время открытого
вопроса и после rebuild из новой транзакции. Подтверждены проектная изоляция
внутри организации, межорганизационная изоляция и default deny без tenant
context. Рабочий diff на `7f0c29f9519217dba722ad1f5b6396d8a02216da`, ветка
`feat/g02-tool-registry-manager`. Решение и проверки S20/S21 описаны в
[отчёте S21](S21_plan_task_orchestration_REPORT.md) и [review](../reviews/G02_S17_S20_REVIEWS.md).

Проекция доступна доверенному Backend и пока не передаётся в Manager Runtime.
Нормативная привязка существенных решений Manager к версии состояния,
выдача допустимой истории v0.4 и проактивные сообщения остаются открытыми.
Публичная роль для решения по exact Proposal ожидает ответа владельца.
Миграции и контракт ar2 на этом шаге не менялись. S20 **IN_PROGRESS**.

## Native Workflow Task с многостраничной History · ADR-164

Защищённый frontend дочитывает курсор Matching внутри выдачи Workflow Task.
Точный namespace/Workflow/Run берётся из ответа Temporal. События должны
идти подряд до `WorkflowTaskStarted` этой задачи. После сборки frontend
повторно проверяет ту же запись о выдаче и использует полную историю для
доказательства отказа Activity по ADR-163. Сборка ограничена 64 страницами,
3 MiB и 3 секундами. Неполная или просроченная выдача закрывается.

Изменения в `infra/temporal_auth_poc/assigned_poll.go`, настройке native
кандидата и тестах Go/Compose/pytest. Прямой RPC History остаётся закрытым
для Manager и наблюдателя. Изменений API, миграций, SQL grants и формата
доменных данных нет. На `feat/g02-tool-registry-manager` проверен рабочий
diff от `7f0c29f9519217dba722ad1f5b6396d8a02216da` в Docker Engine 29.2.0,
Temporal 1.29.7, PostgreSQL 16.15 и Python SDK 1.36. Linux test image
`sha256:90e56f17ea9d7c598bd5b3c0661ae9f4327b421cb190dc13a0dc1fb8dde4afcf`.

| Команда | Результат |
|---|---|
| `docker build --target postgres-test -t ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Pinned Go 1.25.11, обычный и PostgreSQL-tagged `go test` прошли. |
| `docker run --rm --network none --entrypoint /temporal-postgres-test ai-res/temporal-auth-poc-postgres:test -test.v` | Exit 0. 17 верхнеуровневых тестов прошли, 0 failed. Один вход PostgreSQL fixture пропущен в этом режиме и исполнен ниже. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history --manager-timeout --lose-start-response` | Exit 0. 1 passed, 0 failed/skipped, 42,29 с. Тест потребовал успешных register/check/context одной записи после фактического чтения продолжения. Проверены потеря Start, Manager timeout после ACK, отказ Plan, сверка и replay. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --paginate-history` | Exit 0. 1 passed, 0 failed/skipped, 9,28 с. Проверены пагинация, повторная доставка Outbox, Manager success и failure/replay Plan. |
| `make backend-check infra-check contracts-check contracts-test infra-scan-secrets` | Exit 0. 265 исходников mypy, 15 import contracts, 6 проверок контрактов, 47 тестов без пропусков, 0 нарушений Compose и 0 находок сканера секретов. |
| Повтор тех же `docker build` и `docker run` с тегом `ai-res/temporal-auth-poc-postgres:pagination-check`, `make infra-scan-secrets`, `git diff --check` | Exit 0. После уточнения Go fixture 17 passed, 0 failed, тот же 1 fixture skip вне Compose. 0 находок сканера. Runtime-код соответствует обоим Compose-прогонам. |

Независимые code и security review завершены с **APPROVE**. Исправлено
замечание MEDIUM к принудительной пагинации в fixture. Локальный срез
проверен. S20 и G02 остаются **IN_PROGRESS** и поставлены на паузу по
поручению владельца. Штатное подключение, полный `make pre-pr` и Linux CI
предстоят при возобновлении. [Review](../reviews/G02_S17_S20_REVIEWS.md).

## Native Manager Activity timeout после ACK · 2026-11-20

Изолированный сетевой стенд с opt-in `--manager-timeout` использует настоящий
`ACTIVITY_TIMEOUT` 30 с. Manager получает ACK, читает вход через private ar2
и останавливается в fixture до обращения к модели. Temporal закрывает точный
Workflow Run с `FAILED`. В сохранённой History exact Activity имеет
`START_TO_CLOSE`, а Workflow ссылается на ту же пару scheduled/started event ID.
Текст запроса, исключение fixture и stack traces исключены из persisted History.
SDK Replayer воспроизводит историю. Backend оставляет Operation в `RUNNING` и
сохраняет единственный `DOMAIN_OUTCOME_REQUIRED` для `FAILED`. Тест проверяет,
что второй вызов модели не произошёл.

Файлы `infra/temporal_auth_poc/compose_candidate.py`, `compose.network.yaml` и
`backend/tests/integration/postgres/test_native_assigned_workflow.py`. Флаг
допускается только с `--network`. Рабочий diff поверх
`7f0c29f9519217dba722ad1f5b6396d8a02216da`, ветка
`feat/g02-tool-registry-manager`. PostgreSQL 16.15, Temporal 1.29.7,
Python SDK 1.36, Linux candidate image
`sha256:8e462c34a0c77e29b680fe707736511a7ff8fb04e21302c0de4969ad9f00dafa`.

| Команда | Результат |
|---|---|
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --manager-timeout` | Exit 0, 1 passed, 0 failed/skipped, 41.04 с. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --manager-timeout --lose-start-response` | Exit 0, 1 passed, 0 failed/skipped, 41.03 с. Итоговый diff. Повтор Start и timeout в одном прогоне. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --manager-timeout` | Ожидаемый exit 2 до создания стенда. |
| `make backend-check infra-check infra-scan-secrets` и `git diff --check` | Exit 0. Ruff, 265 исходников mypy, 15 import contracts, 0 нарушений Compose и 0 секретов по сканеру. |

Test-only срез прошёл независимое review. Контракты, миграции, grants и
параметры runtime сохранены. Закрыто evidence `START_TO_CLOSE` до модели.
Другие типы таймаутов, начатый внешний вызов и многостраничная History
остаются отдельным scope. G02 **IN_PROGRESS**, общая приёмка и Linux CI
предстоят. [Review](../reviews/G02_S17_S20_REVIEWS.md).

## Защищённая доставка отказа Activity и Workflow · 2026-11-20

Причина застревания после ACK установлена на native-кандидате. Allowlist
ранее пропускал только успешные завершения. Первая правка разрешила новый
RPC, но реальный SDK 1.36.0 отправлял поле 10 `cause=3`, неизвестное
закреплённому серверу и поэтому отклоняемое проверкой wire shape. Источники
проверены в локальных Rust `worker/activities.rs` и `worker/client.rs`,
vendored protobuf SDK и Go descriptors Temporal API.

`assigned_failure.go`, `assigned_completion.go`, `assigned_poll.go` и
`main.go` ограничивают Activity reply отдельной mTLS identity Manager,
точным namespace, действующей выдачей Activity Task, Run и закрытым
набором типов ошибок. Ровно одно значение `cause=3` снимается для
закреплённого сервера. При выдаче Workflow Task с последним отказом
Activity frontend регистрирует отдельное HMAC-доказательство доверенного
события. `FAIL_WORKFLOW_EXECUTION` требует его дополнительно к обычной
записи о выдаче. History получает очищенную структуру без stack trace,
исходного ответа Platform, произвольных details или encoded payload.
Существующие auth-control API и receipts переиспользованы. Миграций,
новых grants, изменений публичного API и бизнес-полномочий нет. [ADR-163](../ARCHITECTURE_DECISION_LOG.md#adr-163--s20s21-защищённая-доставка-ошибки-activity-и-workflow).

Проверки на HEAD `7f0c29f9519217dba722ad1f5b6396d8a02216da` с рабочим diff,
Darwin arm64, Go 1.25.11 в Linux-образе, Temporal 1.29.7 и PostgreSQL 16.15.

| Команда | Результат |
|---|---|
| `docker build --target postgres-test -t ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Закреплённые стандартный и PostgreSQL Go-наборы прошли. Docker digest `sha256:8e462c34a0c77e29b680fe707736511a7ff8fb04e21302c0de4969ad9f00dafa`. Служебный Go launch fixture запускается последующим Compose. |
| В закреплённом upstream checkout с копией Go-файлов `GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local CGO_ENABLED=0 go test -mod=readonly -tags temporal_postgres_probe -count=1 ./...` и `go vet -mod=readonly -tags temporal_postgres_probe ./...` с тем же env | Exit 0, Darwin arm64 и Go 1.26.3. Pytest Compose отдельно запустил служебный launch fixture. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response` | Exit 0, 1 passed, 0 failed/skipped, 10.96 с. Тест сохранил регрессию потери Start и проверил принудительный отказ Plan Activity после ACK. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network` | Exit 0, 1 passed, 0 failed/skipped, 8.70 с. Регрессия потери отметки Outbox, native `FAILED`, точная история из SQL и replay. |
| `backend/.venv/bin/python -B -m pytest -q -c backend/pyproject.toml backend/tests/integration/temporal/test_manager_workflows.py backend/tests/integration/postgres/test_native_auth_control.py backend/tests/unit/test_reconciliation_scheduler.py --tb=short` | Exit 0, 14 passed, 0 failed/skipped, 11.99 с. Контрольные Workflow и auth-control regressions. |
| `make -j1 pre-push-fast infra-check infra-scan-secrets`, финальный `make backend-check`, `git diff --check` и `gofmt -l` | Exit 0, 1947 passed, 0 failed/skipped, 3 известных OTel warning. Mypy 265 source files, 15 import contracts, 0 нарушений Compose и 0 findings scanner. |

В networked Compose 422 на Plan materialization привёл к `FAILED` у точного
native Run после ACK, нулю задач и одной коррекции/аудиту ADR-162 в БД.
Фактическая persisted History проверена по exact Run tree ID. Ни текст 422,
ни stack traces не сохранились. Python SDK Replayer воспроизвёл историю.
Go и security review одобрили срез. Отдельная проверка native timeout,
исчерпания transient retries и многостраничной History не входит в это
evidence. При получении частичной страницы failure proof отсутствует.
Срез **TESTED**, S20/G02 **IN_PROGRESS**. Остались штатная композиция,
полный `make pre-pr`, Linux CI и приёмка группы.
[Review](../reviews/G02_S17_S20_REVIEWS.md), [паспорт](../groups/G02_WORK.md).

## Сверка доменного эффекта после ACK · 2026-11-20

ADR-162 подключает существующий планировщик Backend к post-ACK эффектам
по явному `include_post_ack: true` в `AI_RES_RECONCILIATION_CONFIG_FILE`.
`reconcile_operations.py` отбирает точные назначения в настроенных проектах.
Признак ACK берётся из `started_at` и повторно проверяется перед записью.
`observe_operations.py` делает один Describe с deadline вне транзакции.
`reconcile_effects.py` после RPC блокирует assignment и Operation,
повторяет проверки версии и scope и сверяет факт результата.

- Manager. Подтверждённый черновик выигрывает гонку с terminal observation.
  Если черновик отсутствует, сведения о возможном внешнем вызове сохраняются
  для расследования. Сверка не повторяет вызов модели.
- Plan. Проверяются immutable approval, completion snapshot, связи задач,
  WorkerRuns и дочерние Operation. `FAILED` или подтверждённый `CANCELLED`
  применяются только когда нет локальных эффектов и соблюдены условия
  доменного перехода. При наличии задач состояние сохраняется.
- `SqlAuditWriter.write_once` использует существующий insert-only RLS и
  сохраняет расследуемое наблюдение один раз для идентичного Run и версии.
  Любая коррекция фиксирует переход, event, Outbox и аудит атомарно.

Миграций, grant-изменений, публичных API или новых типов доменных событий
в этой дельте нет. Старый конфигурационный файл оставляет pre-ACK режим.
Code review и security review подтвердили точный binding, порядок
блокировок, защиту повторного `QUEUED`, атомарность и аудит. [Review](../reviews/G02_S17_S20_REVIEWS.md).

Сквозная проверка на обычном Temporal dev server завершила exact Plan Run
после сохранённого ACK. Backend scheduler установил `FAILED` с
`WORKFLOW_TERMINATED` только после проверки отсутствия задач. Тестовый
оператор завершил Run внутри изолированной fixture. Отдельный networked
native Compose подтвердил существующие статусы после ACK и регрессию
потерянного Start. Попытка довести нативный отрицательный сценарий до
terminal выявила запрет `RespondActivityTaskFailed` для текущего Manager
allowlist. Это ограничение штатного защищённого контура остаётся открытым.

Проверки на `feat/g02-tool-registry-manager`, HEAD
`7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочем diff. Darwin arm64,
Python 3.13.5, PostgreSQL 16.15 и изолированный Temporal 1.29.7 для native.

| Команда | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -q -c backend/pyproject.toml backend/tests/integration/postgres/test_plan_execution.py backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_manager_intake.py backend/tests/integration/postgres/test_operation_execution_assignments.py backend/tests/integration/postgres/test_iam_audit_writer.py backend/tests/unit/test_reconciliation_scheduler.py backend/tests/unit/test_operation_reconciliation.py --tb=short` | Exit 0, 66 passed, 0 failed/skipped, 31.74 с, 1 прежний OTel warning. PostgreSQL проверил отдельный tenant, отзыв, stale/requeue, гонку с Task и draft, два обработчика, failure vs cancel, rollback при сбое аудита и отсутствие дублей. |
| `backend/.venv/bin/python -B -m pytest -q -c backend/pyproject.toml backend/tests/unit/test_reconciliation_scheduler.py backend/tests/unit/test_operation_reconciliation.py --tb=short` | Exit 0, после правки unknown ACK и RPC count 22 passed, 0 failed/skipped, 0.33 с. |
| `make -j1 pre-push-fast infra-check infra-scan-secrets` и `git diff --check` | Exit 0, 1947 passed, 0 failed/skipped, 14.97 с, 3 прежних OTel warning. 265 source files mypy, 15 import contracts, 0 нарушений Compose и 0 findings scanner. |
| `make contracts-check contracts-test` | Exit 0, 6 валидаторов, 47 passed, 0 failed/skipped, 8.45 с. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response` | Финальная регрессия exit 0, 1 passed, 0 failed/skipped, 6.86 с. Отрицательная попытка с 422 на Plan materialization отдельно завершилась exit 1 из-за отказа native failure reply. |

Срез **TESTED**, G02 остаётся **IN_PROGRESS**. Полный `make pre-pr`, Linux CI
и merge относятся к приёмке группы. Штатный стек родительской рабочей копии
использует прежнюю композицию.

## Статус точного активного Run после ACK · 2026-11-20

Владелец делегировал решения по G-107 и истории Manager. ADR-160 выбирает
наблюдение статуса активного exact Manager или Plan Run через выделенную
mTLS identity. ADR-161 требует доказанной привязки текста истории к явно
классифицированной неизменяемой версии источника и текущих Policy/ACL.
При отсутствии такой привязки v0.4 выдаёт пустой срез истории. Полномочия
на бизнес-утверждения сохраняются у человека.

`contracts/internal/platform-native-auth-control.v1.yaml` v1.1 добавляет
подписанный `authorize-bound-status`. `platform_auth_control.py`,
`native_auth_control.py` и `platform_credentials.py` проверяют путь, тело,
срок и nonce. Старое действие ADR-151 сохраняет допуск Manager до ACK.
Миграция 0048 предоставляет существующей роли Platform EXECUTE на одну
булеву проверку exact active Run и добавляет action аудита. Данные Operation
и предыдущие audit rows сохраняются, backfill отсутствует. Native frontend
в `infra/temporal_auth_poc` фильтрует Describe до Run identity, status, type
и queue. Проверка запуска исключает глобальный namespace и redirection.
Публичный API и AsyncAPI сохранены. При rollout новый Backend и 0048 должны
предшествовать запуску обновлённого native frontend.

Проверки на базе `7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочем diff,
Darwin arm64, PostgreSQL 16.15, Temporal 1.29.7, Go 1.25.11 в Linux-образе.

| Команда | Результат |
|---|---|
| `make contracts-check contracts-test backend-check` | Exit 0. 6 валидаторов, 47 passed, 0 failed/skipped, Ruff, mypy 264 source files, 15 import contracts. |
| `backend/.venv/bin/python -B -m pytest -q -c backend/pyproject.toml backend/tests/integration/postgres/test_migrations.py backend/tests/integration/postgres/test_schema_drift.py backend/tests/integration/postgres/test_native_auth_control.py backend/tests/integration/postgres/test_operation_execution_assignments.py backend/tests/unit/test_platform_credentials.py --tb=short` | Exit 0, 39 passed, 0 failed/skipped, 46.21 с. Upgrade с empty/0047, grants/RLS, drift и audit preservation. Известный SQLAlchemy warning `xid8` на scratch schema. |
| Та же команда с `test_native_auth_control.py` и `test_platform_credentials.py` после уточнения expiry rollback | Exit 0, 4 passed, 0 failed/skipped, 12.52 с. Истечение credential после выдачи receipt откатывает receipt и фиксирует отказ. |
| `make -j1 pre-push-fast infra-check infra-scan-secrets` | Exit 0, 1943 passed, 0 failed/skipped, 18.48 с, 3 прежних OTel warning. 0 нарушений Compose и 0 findings scanner. Offline SQL gate проверяет точные три замены CHECK. |
| `docker build --target postgres-test -t ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Изолированный Linux-образ включает успешные Go tests с обычным и PostgreSQL build tag. digest списка `sha256:abd6da6d7cad21e5d52f36e15b2cab8a410d4b22d76e874bee8c0fa6718830d4`. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response` | Exit 0, 1 passed, 0 failed/skipped, 15.69 с. Проверен Manager после ACK и отказ History/List/Cancel. Plan стартовал через реальный native Temporal и прочитан mTLS наблюдателем до и после ar2 ACK от тестовой fixture. |

Независимые code/security review подтвердили scope. Найденные проблемы
redirection и аудита исправлены. DOC-068 v1.5, DOC-082 v1.7 и Registry
обновлены, проверены SHA-256 и размер 76 canonical файлов. Наблюдение не
даёт перехода доменной Operation. Полный G-107 требует доказательств эффекта
и штатного включения. Plan fixture подтверждает статус, материализация
его задач проверяется отдельным сценарным тестом S21. S20/G02 сохраняют
**IN_PROGRESS**. Общий `make pre-pr` и Linux CI относятся к финальному
инкременту группы, штатный Compose в `../AI-RES` сохранён.
[Review](../reviews/G02_S17_S20_REVIEWS.md), [паспорт](../groups/G02_WORK.md).

## Подписанный Manager input v0.4 и проверки утверждения · 2026-11-20

Локальные срезы **TESTED**, S20/G02 **IN_PROGRESS**. Ветка
`feat/g02-tool-registry-manager`, HEAD `7f0c29f9519217dba722ad1f5b6396d8a02216da`
и рабочий diff. `platform_credentials.py`, `api/platform_v2.py` и
`runtime/platform_control_client.py` реализуют принятую форму DOC-086 v0.4.
Приватный обработчик использует существующие подпись, nonce, допуск
точного assignment и Run, аудит и `Cache-Control: no-store`. При отсутствии
доказательства на каждую запись он возвращает `recentQuestions: []`,
`historyTruncated: false`. Клиент проверяет границы ответа, порядок вопросов,
точную Operation и проверенный тип записи. Публичный API, события,
миграции, grants и compatibility baseline сохранены.

На Darwin arm64 и PostgreSQL 16.15 команда
`backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_platform_manager_commands.py backend/tests/integration/test_platform_control_tls.py backend/tests/unit/test_platform_credentials.py backend/tests/unit/test_manager_reasoning.py --tb=short`
вернула exit 0, 20 passed, 0 failed/skipped, 7.88 с. Проверены раздельные
v0.3/v0.4 подписи, неправильный Run, вход до RUNNING, аудит, приватный TLS,
ограничение размера и разбор корректной и некорректной истории fixture.
Opt-in сетевой сценарий с native Temporal через ar2 v0.4, команда из
следующего раздела, exit 0, 1 passed, 0 failed/skipped, 14.41 с на финальном
рабочем diff.

ADR-159 связывает `platform/human_approval.py` с репозиториями Proposal и
PlanVersion. PostgreSQL тесты проверяют отказ сервиса, истёкшей сессии,
`APPROVAL_REQUIRED`, чужого хэша и автора Proposal при включённом SoD.
Команда `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_manager_intake.py backend/tests/integration/postgres/test_plan_execution.py backend/tests/integration/postgres/test_planning_http.py backend/tests/integration/postgres/test_manager_http.py --tb=short`
вернула exit 0, 8 passed, 0 failed/skipped, 29.26 с. Отдельная продуктивная
команда Proposal с точной Policy остаётся открытой. Пройдены code и security
review обоих срезов. [Результаты](../reviews/G02_S17_S20_REVIEWS.md).

Открыты G-107 после ACK и production wiring, допуск истории, расширенная
проекция Epic, проактивные сообщения и общая приёмка. Вопросы владельца
записаны в [DECISIONS_PENDING](../DECISIONS_PENDING.md).

## Потеря ответа Start до привязки Run · 2026-11-20

На базе `7f0c29f9519217dba722ad1f5b6396d8a02216da` расширен сетевой сценарий
ADR-157. `compose.network.yaml`, `compose_candidate.py` и
`test_native_assigned_workflow.py` добавляют opt-in `--lose-start-response`.
Потеря ответа имитируется после реального успешного Start, до вызова bind.
Первая доставка оставила запись `PENDING` и assignment без Run.
Fixture observer прочитал первый history event без изменения assignment.
После перевода `available_at` в текущее время реальный Dispatcher повторил
тот же Start. Native вернул исходный Run. Обработчик сохранил его и отметил
исходную строку `PUBLISHED` на второй попытке. Один Run и один draft
подтверждены по visibility, history и доменной БД.

Команда `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network --lose-start-response`
вернула exit 0, 1 passed, 0 failed/skipped, 10.91 с. Darwin arm64,
Docker Engine 29.2.0, Compose 5.0.2, PostgreSQL 16.15, Temporal 1.29.7.
Ревью сценария пройдено. Внешний сетевой обрыв и остановка процесса
не моделировались. Штатный диспетчер, post-ACK, v0.4 и приёмка S20 открыты.
[Review](../reviews/G02_S17_S20_REVIEWS.md).

## Сети Compose и повтор Outbox · 2026-11-20

Локальный срез **TESTED**. S20/G02 **IN_PROGRESS**. Рабочая ветка `feat/g02-tool-registry-manager`,
HEAD `7f0c29f9519217dba722ad1f5b6396d8a02216da`. Родительская копия
`~/AI-RES-Workspace/AI-RES` на `47468cde88d66014110f0aa4b36c78377d16c454`
содержит исходные Compose и диспетчер S11. В её backend и основном Compose
нет локального diff. Protected publisher и сверка уже были реализованы
в G02 и переиспользованы. Родительская копия проверена в режиме чтения.

| Файлы | Scope |
|---|---|
| `infra/temporal_auth_poc/compose.network.yaml`, `compose_candidate.py` | Opt-in `--network`, отдельные internal сети `data`, `workflow`, `platform`, без опубликованных портов. Rendered preflight проверяет карту сетей и сохранение границ mounts. |
| `infra/temporal_auth_poc/main.go`, `assigned_start.go`, `assigned_start_test.go`, `postgres_probe_test.go`, `check.py` | Сетевой tagged fixture привязывает frontend к workflow-адресу, оставляет History/Matching на loopback через статический membership и допускает только точный HTTPS origin Platform. Обычные профили продолжают использовать loopback. |
| `backend/tests/integration/postgres/test_native_assigned_workflow.py` | Повтор на реальном PostgreSQL под `ai_res_outbox_dispatcher` с существующими Dispatcher, assigned publisher, binding/reconciliation и контрактным validator. |
| Implementation-документы | ADR-157, handoff, status, gaps, G02, requirements traceability, ECC, review. |

API, контракты, Alembic-ревизии и данные штатной среды не изменились.
Штатные provisioning/schema/migrate применены к одноразовому PostgreSQL.
Обычная Compose-конфигурация и текущие сервисы продолжают использовать
штатный Temporal и S11 dispatcher.

| Команда | Результат |
|---|---|
| `docker build --progress=plain --target postgres-test --tag ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Linux arm64, Go 1.25.11. Offline compile, Go tests и проверка locks прошли. Native image ID `sha256:d0047bc2f86ec554ccf8e087bb674a2405c0a20a514091d0fe6198eb9ea7fdf9`, runner `sha256:751a149c3b5302c2f994081749eaf5f01e2b551a230b53ea56a483b7c8b7027e`. |
| В закреплённом upstream checkout Temporal с копией Go-файлов `GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local CGO_ENABLED=0 go test -mod=readonly -tags temporal_postgres_probe -v .`, затем `go vet -mod=readonly -tags temporal_postgres_probe .` | Exit 0 на Darwin arm64, Go 1.26.3. Шесть подслучаев exact origin и запрет redirects; серверный launch-test пропущен без env и выполнялся в Compose. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate --network` | Exit 0, 1 passed, 0 failed/skipped, 14.12 с. PostgreSQL 16.15, Temporal 1.29.7, Docker Engine 29.2.0, Compose 5.0.2. Сети и контейнеры удалены после проверки. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate` | Exit 0, 1 passed, 0 failed/skipped, 12.04 с. Регрессия отдельного loopback-проекта. |
| Команда регрессии ADR-154 с обоими бинарниками и `-k 'not compose'` | Exit 0, 3 passed, 0 failed/skipped, 1 deselected, 39.02 с. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1943 passed, 0 failed/skipped, 3 OTel deprecation warnings, mypy 261 файл, 15 import contracts. |
| `make infra-check infra-scan-secrets` с теми же UV env, Ruff, `gofmt -l`, `git diff --check` | Exit 0, 0 violations/secret findings. |

Первая доставка выполнила native Start и привязала Run. Тест вернул false
только для отметки `mark_published`. Запись осталась `IN_FLIGHT` с
attempt 1. После перевода времени аренды в прошлое реальный Dispatcher
забрал запись со второй попытки и записал `PUBLISHED`. Счётчик ручного
replay остался 0. Не вызван второй Start, совпадает история точного Run,
в visibility один `COMPLETED` Run, в доменной БД один draft. Первое
сравнение сырых идентификаторов visibility выявило пробелы формата
`CHAR(64)`. Запрос проверки теперь обрезает padding.

Реальный ar2 использует private HTTPS и отдельные подписывающие ключи.
Проверены frontend mTLS и ACL, отказ подключения к History/Matching с
workflow-интерфейса, SQL TLS для native, Platform и диспетчера.
Во время регрессии SDK оборачивал отказ TLS без клиентского сертификата в
`BrokenPipe`/`CANCELLED`. Теперь тест требует точный отказ при TLS-handshake
и успешный handshake с сертификатом оператора. Проверки RPC ACL остались
на реальном SDK. Независимые
code/security review пройдены. [Результаты review](../reviews/G02_S17_S20_REVIEWS.md).

Тест моделирует один сбой отметки доставки после привязки Run и ускоряет
истечение lease. Проверки естественного истечения и реального падения
процесса, конкурирующих диспетчеров, потери Start до binding на штатной
identity и сверки после ACK остаются открытыми. Статический membership и
runner с несколькими ролями ограничены стендом. Для полного S20 остаются
переключение штатных сервисов, `pre-pr` и Linux CI.

## Private ar2 и PostgreSQL verify-full · 2026-11-20

Локальный срез **TESTED**. S20/G02 **IN_PROGRESS**. Ветка `feat/g02-tool-registry-manager`, рабочий
diff на `7f0c29f9519217dba722ad1f5b6396d8a02216da`. Darwin arm64,
Docker Engine 29.2.0, Compose 5.0.2, Linux arm64, PostgreSQL 16.15,
Temporal v1.29.7 из `1f74f0c8e9935980d92a39069185671bbbba7c7e`,
Go 1.25.11, Python 3.13.18 и Temporal SDK 1.36.0 в runner.

| Scope | Результат |
|---|---|
| `infra/temporal_auth_poc/compose.candidate.yaml`, `compose_candidate.py`, `Dockerfile.candidate` | Изолированный проект переиспользует штатные PostgreSQL, provision, temporal-schema и migrate. Preflight проверяет список сервисов, отсутствие сети/портов, точные mounts native и происхождение секретов. Native и pytest запускаются в разных контейнерах. |
| `infra/temporal_auth_poc/postgres_probe_test.go`, `postgres_probe.py`, `check.py` | Tagged native profile ждёт ограниченный по времени ready marker. Для SQL допускает только точные history/visibility, роль `temporal`, `postgres:5432` с IPv4 loopback и TLS verify-full под заданной CA. |
| `backend/tests/integration/postgres/test_native_assigned_workflow.py`, `conftest.py` | Compose-вариант поднимает штатный private listener `create_listener` и использует отдельные ключи Manager и Temporal. Подтверждает exact Workflow/Run, авторизацию, receipts и SQL TLS. Существующие SQLite/PostgreSQL профили остаются доступны. |
| `infra/scripts/secrets_dev.py`, `infra/tests/test_secrets_dev_identity.py` | CA, CSR и серверный сертификат получают явный SHA-256. Regression test подтверждает алгоритм свежих TLS сертификатов. Существующие секреты не ротировались. |
| Implementation-документы | ADR-156, handoff, status, gaps, G02, requirements traceability, ECC и review. |

Изменения касаются dev-генерации сертификатов и тестового стенда. API,
контракты и Alembic-ревизии не изменились. Штатные миграции и temporal-schema
применялись только к одноразовой базе. В штатном Compose продолжает
работать stock Temporal. Перезапуск штатного Compose не требовался.

| Команда | Результат |
|---|---|
| `docker build --progress=plain --target postgres-test --tag ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0. Tagged Go tests, шесть новых отрицательных подслучаев и офлайн-проверка locks прошли. Server test на этом шаге пропускается без явной fixture и запускается в Compose. |
| `docker build --progress=plain -t ai-res/s20-compose-probe:local -f infra/temporal_auth_poc/Dockerfile.candidate backend` | Exit 0. Runner установлен по текущему lock. |
| `backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_candidate` | Три последовательных финальных запуска exit 0. В каждом provision, temporal-schema и Alembic завершились успешно, сценарий Manager 1 passed, 0 failed/skipped (10.38, 13.09 и 10.44 с). Тестовые контейнеры удалены. |
| Команда регрессии ADR-154 с обоими бинарниками и `-k 'not compose'` | Exit 0, 3 passed, 0 failed/skipped, 1 deselected, 48.55 с. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1943 passed, 0 failed/skipped, 3 OTel deprecation warnings, mypy 261 файл, 15 import contracts. |
| `make infra-check` с теми же UV env | Exit 0, по профилям 22/22/22/24 сервисов, 0 violations. |
| Из `infra/` `uv run --locked pytest -q --tb=short -m 'not runtime'` с локальным OpenSSL 3.6.3 в PATH и теми же UV env | Exit 0, 222 passed, 18 skipped, 130 deselected, 17.60 с. Первый прогон с системным LibreSSL 3.3.6 завершился ошибкой прежнего Ed25519-теста, повтор сделан с совместимой CLI по tooling/README. |
| Из `infra/` `uv run --locked pytest -q --tb=short tests/test_secrets_dev_identity.py -k postgres_certificates` с LibreSSL 3.3.6 | Exit 0, 1 passed, 4 deselected, 0.09 с. |
| Ruff, Hadolint, `gofmt -l`, `make infra-scan-secrets`, `git diff --check` | Exit 0, 0 secret findings. |

Локальные image IDs по `docker image inspect`:
native `sha256:537e745d9f754c3b788ff0de0a476e4982e4719c44261a983d4ed293b48af6cb`,
runner `sha256:751a149c3b5302c2f994081749eaf5f01e2b551a230b53ea56a483b7c8b7027e`.

Применены реальные native RPC, ar2 receipts и dedicated PostgreSQL roles.
`pg_stat_ssl` показал TLS у `temporal` в history и visibility, а также у
`ai_res_platform_api` в доменной БД. Plaintext и несовпадение hostname
отклонены, ar2 отказал при недоступном authority, доступ к History ограничен.
LLM transport детерминирован в fixture. Code и security review одобрили
разделение mounts и версию проверки. [Review](../reviews/G02_S17_S20_REVIEWS.md).

Первый контейнер с новым сертификатом не запустился из-за подписи SHA-1
от системного LibreSSL. После явного выбора SHA-256 штатные шаги прошли.
Один промежуточный прогон кандидата вернул exit 1. Полная причина этого
сбоя не зафиксирована, три последующих запуска прошли без изменений кода.
Тест использует общий loopback изолированного Compose и синтетические
сертификаты. Остаются штатная топология сервисов и реальных identities,
ar2 на restart/restore, полный G-107, общий `pre-pr` и Linux CI.

## Восстановление Run в тестовом Compose · 2026-11-20

Локальный срез **TESTED**. S20 и G02 **IN_PROGRESS**. Ветка
`feat/g02-tool-registry-manager`, рабочий diff на
`7f0c29f9519217dba722ad1f5b6396d8a02216da`. Хост Darwin arm64 с UID 501,
сервисы теста Linux arm64 с UID 1000. Docker Engine 29.2.0,
Compose 5.0.2, Go 1.25.11 в Linux builder, Python 3.13.5 на хосте,
PostgreSQL 16.15, Temporal v1.29.7 из `1f74f0c8e9935980d92a39069185671bbbba7c7e`.

| Файлы | Scope |
|---|---|
| `infra/temporal_auth_poc/Dockerfile`, `main.go` | Добавлен отдельный тестовый Linux target `postgres-test` с offline-компиляцией. Обычная цель Dockerfile использует SQLite. Уточнено описание PoC. |
| `infra/temporal_auth_poc/compose.restart.yaml`, `compose_restart.py`, `postgres_probe.py` | Временный Compose-проект без опубликованных портов. Отдельные роли/файлы fixture, restore в PostgreSQL tmpfs, проверка exact History, visibility и mTLS до и после перезапуска только Temporal. |
| `backend/tests/integration/postgres/test_native_assigned_workflow.py` | Opt-in экспорт только двух синтетических баз Temporal и хэша истории точного Run в приватный каталог того же запуска. |
| Implementation-документы | ADR-155, handoff, status, gaps, G02, traceability, ECC и review. |

Целевой Compose и его данные не менялись. API, контракты и Alembic-ревизии
не изменились. Дамп с синтетическими данными Temporal импортируется только
в одноразовые базы history и visibility под `temporal_probe`. Runtime
verifier получает отдельный mount без ключа frontend и ключа подписи.

| Команда | Результат |
|---|---|
| `docker build --progress=plain --target postgres-test --tag ai-res/temporal-auth-poc-postgres:test infra/temporal_auth_poc` | Exit 0, tagged Go tests и проверка lock-файлов в offline compile прошли. Тестовый server запускается с fixture env, при unit run без env пропускается. |
| `docker build --progress=plain --tag ai-res/temporal-auth-poc:restart-check infra/temporal_auth_poc` | Exit 0 для обычной SQLite цели. |
| `env PYTHONDONTWRITEBYTECODE=1 G02_NATIVE_POSTGRES_PROBE_BINARY="$pg_probe" G02_TEMPORAL_SQL_TOOL="$sql_tool" G02_TEMPORAL_POSTGRES_SCHEMA_ROOT="$temporal_src/schema/postgresql/v12" backend/.venv/bin/python -B infra/temporal_auth_poc/compose_restart.py` | Exit 0. Исходный native интеграционный тест 1 passed, 0 failed/skipped, 24.48 с. History хэш совпал с источником до и после рестарта, PostgreSQL сохранил `StartedAt`, `StartedAt` Temporal изменился. Тестовый проект удалён. Входные инструменты собраны по ADR-154. |
| Команда регрессии ADR-154 с обоими бинарниками и двумя файлами pytest ниже, без экспорта | Exit 0, 3 passed, 0 failed/skipped, 31.46 с. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1943 passed, 0 failed/skipped, 3 OTel deprecation warnings, mypy 261 файл, 15 import contracts. |
| `backend/.venv/bin/ruff check --no-cache infra/temporal_auth_poc/compose_restart.py infra/temporal_auth_poc/postgres_probe.py backend/tests/integration/postgres/test_native_assigned_workflow.py`, `hadolint infra/temporal_auth_poc/Dockerfile`, `make infra-scan-secrets`, `git diff --check` | Exit 0, 0 secret findings. |

В финальном прогоне SHA-256 истории
`313e50cce38c163b5b2098ccfbbcc4494e12c91b6e4e4effd261fc68a49aaa47`.
Локальные image IDs по `docker image inspect`:
Temporal PostgreSQL `sha256:fac3baa83f0eb1772d5170dd4475e705d5827d930e88225db4acc9ab29c899e8`,
verifier `sha256:10ebf34da9ae133d6795e5a13a94b38be1128adc1bccfccb2117bf84da008690`,
обычная SQLite цель `sha256:ffb2366199a9140762ea29266a58d1ee671daa0dadcab83ed64458ce8291b027`.

Обе проверки в Compose прочитали `COMPLETED` для точного Workflow/Run
в visibility. Fixture operator прочитал History, Manager получил
`PERMISSION_DENIED`. History и Matching приняли internode сертификат
и отклонили отсутствие сертификата и сертификат от frontend CA.
Ревью подтвердили привязку UID/GID, обязательный cleanup, ограниченную роль
импорта и отдельные mounts. [Review](../reviews/G02_S17_S20_REVIEWS.md).

Восстанавливались только базы Temporal. PostgreSQL оставался запущенным
при перезапуске Temporal, ar2 в восстановленном проекте недоступен.
Проверка проведена на Docker Desktop, rootless/remapped/remote Docker
не проверялись. Стенд использует синтетические сертификаты, loopback TCP к
PostgreSQL и локальный образ verifier. Для G-107 остаются целевая композиция
с работающим ar2 и TLS к PostgreSQL, потерянный Start, повтор Outbox и сверка
после ACK. Полный `pre-pr`, supply-chain gates и Linux CI открыты.

## Native Temporal на PostgreSQL с internode mTLS · 2026-11-20

Локальный срез **TESTED**, S20 и G02 **IN_PROGRESS**. Ветка
`feat/g02-tool-registry-manager`, рабочий diff на
`7f0c29f9519217dba722ad1f5b6396d8a02216da`. Darwin arm64, Go 1.26.3,
Python 3.13.5, Docker Engine 29.2.0, PostgreSQL 16.15, Temporal v1.29.7
из коммита `1f74f0c8e9935980d92a39069185671bbbba7c7e`.

| Scope | Результат |
|---|---|
| `infra/temporal_auth_poc/main.go`, `postgres_probe_test.go` | Test binary делит native authorizer с основным PoC, требует loopback и frontend/internode mTLS, точные роль и базы fixture и отвергает DSN overrides. PostgreSQL launcher включается только в Go tests с build tag и явным путём fixture. |
| `infra/temporal_auth_poc/check.py`, `postgres_probe.py` | Для PostgreSQL резервируются loopback-порты до 32767. Fixture поднимает отдельные history и visibility базы, применяет закреплённые upstream схемы и создаёт отдельную internode CA с проверкой hostname. |
| `backend/tests/integration/postgres/test_native_assigned_workflow.py` | Сценарий работает в SQLite и в opt-in PostgreSQL. В PostgreSQL использован отдельный одноразовый контейнер, проверена публикация только на loopback. History содержит события после остановки Temporal, visibility фиксирует `COMPLETED` для точных Workflow ID и Run ID. |
| Implementation-документы | ADR-154, handoff, status, gaps, паспорт G02, traceability, ECC и независимые review. |

Изменения касаются тестового запуска. API, контракты и Alembic-ревизии
в этом срезе не менялись. Upstream SQL tool применял схемы только в двух
временных базах. Штатный Compose продолжил работать со stock Temporal.

| Команда | Результат |
|---|---|
| В checkout Temporal `GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local CGO_ENABLED=0 go build -mod=readonly -trimpath -o "$sql_tool" ./cmd/tools/sql` | Exit 0, инструмент для upstream PostgreSQL схем. |
| В копии Go-файлов probe в checkout Temporal, те же Go env, `go test -mod=readonly -tags temporal_postgres_probe -v .`, `go vet -mod=readonly -tags temporal_postgres_probe .`, `go test -mod=readonly -tags temporal_postgres_probe -trimpath -c -o "$pg_probe" .`, `go build -mod=readonly -trimpath -o "$sqlite_probe" .` | Exit 0, 23 passed с учётом подслучаев, 0 failed. Один server test пропущен без fixture env при unit run и запущен в pytest. |
| `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/infra/temporal_auth_poc" G02_NATIVE_PROBE_BINARY="$sqlite_probe" G02_NATIVE_POSTGRES_PROBE_BINARY="$pg_probe" G02_TEMPORAL_SQL_TOOL="$sql_tool" G02_TEMPORAL_POSTGRES_SCHEMA_ROOT="$temporal_src/schema/postgresql/v12" backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_assigned_workflow.py backend/tests/integration/postgres/test_native_auth_control.py --tb=short` | Exit 0, 3 passed, 0 failed/skipped, финальный прогон 29.03 с. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1943 passed, 0 failed/skipped, 3 OTel deprecation warnings, mypy 261 файл, 15 import contracts. |
| `backend/.venv/bin/ruff check --no-cache infra/temporal_auth_poc/check.py infra/temporal_auth_poc/postgres_probe.py backend/tests/integration/postgres/test_native_assigned_workflow.py`, `gofmt -l infra/temporal_auth_poc/*.go`, `git diff --check` | Exit 0, замечаний нет. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make infra-scan-secrets` | Exit 0, 0 findings. |

History и Matching приняли сертификат internode CA и отклонили подключения
без сертификата и с сертификатом Manager от CA фронтенда. Сквозной сценарий
проверил допуск по exact Run, отказ при 503, Backend scheduler до ACK,
границы доступа к History, отсутствие тестового исходного текста в history
и отсутствие WorkerRun. Два независимых review подтвердили исправления
изоляции, DSN и диапазона портов. [Review](../reviews/G02_S17_S20_REVIEWS.md).

Ранние прогоны выявили порты за пределами PostgreSQL `SMALLINT` и отсутствие
AKI у тестового сертификата. Исправлены диапазон и метаданные сертификата.
Тест использует общую identity для двух проверенных internode listeners
и локальное подключение к временной БД без TLS. Для целевого стека остаются
интеграция native build и реальных identities, membership и другие внутренние
сервисы, TLS к PostgreSQL, restart/restore, supply-chain gates и остальные
G-107 проверки. Полный `pre-pr` и Linux CI для этого diff открыты.

## Linux-сборка native Temporal PoC · 2026-11-20

**Локальный срез TESTED.** S20 и G02 **IN_PROGRESS**. Evidence относится к
`feat/g02-tool-registry-manager` и рабочему diff на базе `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
Docker Engine 29.2.0, linux/arm64, Go 1.25.11 builder. Контейнеры проверки
использовали временные данные. Штатный Compose остался на stock Temporal.

| Файлы | Результат |
|---|---|
| `infra/temporal_auth_poc/Dockerfile`, `.dockerignore` | Commit Temporal `1f74f0c8e9935980d92a39069185671bbbba7c7e`, SHA-256 архива, Go image digest и Go locks. Модули загружаются и проверяются до копирования расширения, Go tests/compile выполняются без сети. `scratch` использует UID/GID 1000, `/scratch` и статический ELF с provenance. |
| `infra/temporal_auth_poc/main.go`, `main_test.go` | Проверка до запуска требует loopback, активный frontend TLS с ключом/сертификатом, явную CA и клиентские сертификаты. HTTP, diagnostics, TLS host overrides и альтернативные хранилища запрещены. Позитивный и отрицательные варианты покрыты Go-тестом. |
| `infra/temporal_auth_poc/check.py` | `--transport-only` переиспользует реальные mTLS проверки в Linux-контейнере без PostgreSQL fixture. Полный режим сохраняет PostgreSQL receipt, тестовый Start повторяет transient RPC с прежним request ID в пределах deadline. |
| Implementation-документы | ADR-153, handoff, status, gaps, G02, traceability, ECC и review. |

Новые входы относятся к сборке и тестовому launcher. Изменений API, схем,
Alembic-ревизий и данных целевого стека в этом срезе нет. Для запуска образа
нужен временный writable каталог `/scratch` под UID 1000. Проверка запуска
предназначена для `--network none`, read-only rootfs, `--cap-drop ALL` и
`--security-opt no-new-privileges`. Упаковка содержит `passwd/group` для
определения текущего UID через Go `os/user` без CGO.

| Проверка | Результат |
|---|---|
| `docker build --progress=plain --iidfile /private/tmp/aires-temporal-auth-linux-153.iid --tag ai-res/temporal-auth-poc:1.29.7 infra/temporal_auth_poc` | Exit 0. Linux Go tests, `go mod verify`, lock hashes и отсутствие ELF `INTERP` прошли. Локальный image ID `sha256:b655581b09201ad48f02ea05c7440c1a993df82146f01a8407c47443b1941664`. |
| `docker create`, `docker cp` `/temporal-auth-poc`, `/etc/passwd` и `/provenance`, затем `shasum`, `cmp` и сравнение входов | Exit 0, 11 exact input hashes. Две отдельные компиляции с одинаковыми Go inputs дали байт-в-байт ELF `9c8283b4c527aa4728e5eeee4cb01e77fcd157e120601a30f9a849a7dbddfc10`. Сравнение относится к бинарнику. |
| `docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /scratch:rw,uid=1000,gid=1000,mode=0700` с final image без аргументов | Ожидаемый exit 1, требуется отдельный конфиг. |
| В Linux runner `ai-res/api:dev` с `--network none --read-only --user 1000:1000` и RO mounts бинарника/`passwd` из образа `python /repo-probe/check.py --transport-only /bundle/temporal-auth-poc` | Exit 0. mTLS и namespace RPC работают, роль без права, неизвестный SAN и отсутствующий клиентский сертификат отклонены. |
| Тот же Linux ELF с 8 изменениями fixture config по одному | Exit 0 для harness. Каждая попытка запуска вернула exit 1 для pprof, metrics, TLS override, отсутствующего TLS key, сертификата или client CA, non-loopback и PostgreSQL. |
| В upstream source копии `go test -mod=readonly -trimpath -count=1 .` и `go vet -mod=readonly .` | Exit 0 на Darwin/arm64, Go 1.26.3. Go-файлы совпадают с входами Linux build. |
| `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/infra/temporal_auth_poc" G02_NATIVE_PROBE_BINARY="$probe_binary" backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_assigned_workflow.py backend/tests/integration/postgres/test_native_auth_control.py --tb=short` | Exit 0, 2 passed. Native authorizer, exact Describe, Backend scheduler и PostgreSQL. |
| `backend/.venv/bin/python -B infra/temporal_auth_poc/check.py "$probe_binary"` | После bounded retry тестового Start exit 0. mTLS, queue ACL, PostgreSQL receipt, отказ при недоступности и bounded completion прошли. |
| `hadolint infra/temporal_auth_poc/Dockerfile`, `backend/.venv/bin/ruff check --no-cache infra/temporal_auth_poc/check.py`, `make infra-scan-secrets`, `git diff --check` | Exit 0, включая 0 secret findings. |

Первый Linux smoke выявил зависимость OTel resource detector от `os/user.Current`.
Добавлена запись фактического UID в финальный образ. После cold offline попытки
со скачиванием зависимостей в compile-шаге загрузка вынесена в отдельный слой
до копирования кода. Финальный compile-шаг прошёл с `RUN --network=none`.
Независимые code/build и security review одобрили изменения. Startup findings
закрыты проверками и Linux smoke. [Review](../reviews/G02_S17_S20_REVIEWS.md).

Целевой Temporal build с PostgreSQL, полным составом внутренних identities и
проверками restart/restore ещё требуется. Целевые SBOM, dependency audit,
`pre-pr`, Linux CI и оставшийся G-107 входят в следующие проверки.

## Планировщик сверки до ACK · 2026-11-20

Локальный срез **TESTED**, S20 и G02 **IN_PROGRESS**. Worktree `AI-RES-G02`,
ветка `feat/g02-tool-registry-manager`, рабочий diff на
`7f0c29f9519217dba722ad1f5b6396d8a02216da`. Darwin arm64, Python 3.13.5,
PostgreSQL 16.15, Temporal SDK 1.36.0, Temporal dev server из CLI 1.5.1 и
изолированный native Temporal 1.29.7.

| Файлы | Результат |
|---|---|
| `application/reconcile_scheduler.py`, `api/app.py`, `platform/config.py`, `orchestration/client.py` | Backend lifespan запускает ограниченную периодическую сверку при явной конфигурации. Отдельный mTLS-клиент переподключается после временного сбоя старта. Завершение lifespan ожидает отмену задачи. |
| `application/reconcile_operations.py`, `application/observe_operations.py` | Сверка Manager Run до ACK обрабатывает одну страницу на проект. После тайм-аута кандидата курсор продвигается и отложенный Run проверяется на следующем обходе. Typed Describe использует метаданные исполнения и сводит неизвестный статус к `SCOPE_MISMATCH`. |
| `backend/tests/unit/test_reconciliation_scheduler.py` и integration тесты Manager, execution assignments и native workflow | Конфигурация, независимые курсоры, повтор, отмена, exact mTLS, прогресс после тайм-аута, подтверждённый TERMINATED и однократная коррекция аудита. |
| Implementation-документы | ADR-152, handoff, status, gap, паспорт G02, traceability, ECC и review. |

`AI_RES_RECONCILIATION_CONFIG_FILE` указывает доверенный JSON-файл Backend.
В нём обязательны `scopes` с `organization_id` и `project_id`, `page_size`,
`interval_seconds`, `page_timeout_seconds`, `rpc_timeout_seconds`, `server_name`,
`ca_file`, `certificate_file` и `private_key_file`. Адрес и namespace используют
`AI_RES_TEMPORAL_ADDRESS` и `AI_RES_TEMPORAL_NAMESPACE`. TLS использует CA и
проверенное имя сервера. Все настройки планировщика задаются явно. Изменение
файла требует перезапуска процесса. Технические тестовые бюджеты ограничены
изолированным стендом. Новых ревизий PostgreSQL и внешних контрактов срез не
требует. Наблюдение проходит за пределами DB-транзакции. CAS и текущая проверка
назначения по ADR-149 защищают запись при повторе. Спаны и счётчики используют
фиксированные метки исхода, детали DB/SDK ошибок ограничены именем класса.

| Команда | Результат |
|---|---|
| В `backend` `.venv/bin/python -B -m pytest -q tests/unit/test_reconciliation_scheduler.py --tb=short` | RED exit 1, 6 failed из-за отсутствующей команды. После реализации и развития тестов проходят в целевом и быстром наборах. |
| Из корня `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/infra/temporal_auth_poc" G02_NATIVE_PROBE_BINARY="$probe_binary" backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_assigned_workflow.py backend/tests/integration/postgres/test_manager_http.py backend/tests/integration/postgres/test_operation_execution_assignments.py backend/tests/integration/temporal backend/tests/unit/test_reconciliation_scheduler.py --tb=short` | Exit 0, 41 passed, 0 failed/skipped, 31.20 с. Включены native lifespan, PostgreSQL/Temporal, обычный клиент и regression tests. Совпадение Go-файлов с исходниками бинарника ADR-151 проверено `cmp`. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0. 1943 passed, 3 OTel deprecation warnings, Ruff, mypy 261 файла, 15 import contracts. |
| `make infra-scan-secrets` и `git diff --check` | Exit 0, 0 findings и 0 ошибок whitespace. |

Два независимых reviewer одобрили срез после исправлений. Связанные MEDIUM
касались потери прогресса страницы при тайм-ауте и SDK-декодирования
неизвестного статуса. Оба закрыты с regression tests. Native-тест ожидает
законченный page span с фактическим наблюдением RUNNING и запись audit.
[Review](../reviews/G02_S17_S20_REVIEWS.md), [ECC](../ECC_USAGE.md).

Целевой Compose использует стандартный Temporal 1.29.7. Подключение
планировщика в целевом окружении ждёт native сборку, проверенный mTLS
и доверенную конфигурацию проектов. G-107 сохраняет восстановление unbound
Start, повтор Outbox и сверку эффектов после ACK. Общие pre-pr/Linux CI и
доставка относятся к приёмке G02.

## Native Describe до ACK · 2026-11-20

Локальный срез **TESTED**. S20 и G02 **IN_PROGRESS**. Evidence относится к
`feat/g02-tool-registry-manager` и рабочему diff на базе `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
Среда Darwin arm64, Python 3.13.5, Go 1.26.3, PostgreSQL 16.15,
изолированный Temporal 1.29.7 и Temporal SDK 1.36.0.

| Файлы | Изменение |
|---|---|
| `infra/temporal_auth_poc/{main.go,reconciliation_describe.go,check.py}` | Отдельный SAN наблюдателя и проверка exact Describe до core handler. Подписанная проверка идёт по существующему private TLS bridge. Недоступность проверки возвращается как безопасный UNAVAILABLE. |
| `backend/src/ai_res/{api/platform_auth_control.py,application/native_auth_control.py,modules/iam/platform_credentials.py}` | Узкий ar2 endpoint для подтверждения текущей привязки, durable nonce и security audit. |
| `backend/src/ai_res/db/migrations/versions/0047_native_reconciliation_describe.py`, `backend/ops/postgres/{grants_audit,schema_snapshot}.sql` | Ревизия `13f3c5d9b7a2` после `382befc90d62` добавляет boolean metadata-функцию и разрешённое audit action. Грант EXECUTE только существующей `ai_res_platform_api_group` и владельцу объекта. Сохранность audit rows и отсутствие drift проверены. |
| `contracts/internal/platform-native-auth-control.v1.yaml` | Аддитивный WORKING маршрут и signed action. Изменения контрактов ограничены внутренним overlay. |
| `backend/tests/integration/postgres/{test_native_auth_control,test_native_assigned_workflow,test_migrations}.py`, `backend/tests/unit/test_migration_graph.py`, `contracts/tests/test_platform_native_auth_control.py` | Conformance, exact authority, отказ после ACK и отзыва, временная недоступность, прежний и новый migration head. |

Владелец разрешил purpose-bound read/describe по ADR-129 и проверку назначений
через существующий metadata-only auth-control. ADR-151 ограничивает этот срез
MANAGER_MESSAGE до ACK, действующим assignment, точным Run, namespace, типом,
очередью и версией. Отдельную authority для восстановления ещё не связанного
Run надо проверить на целевом транспорте. В PoC History доступна только прежней
идентичности тестовой фикстуры. Для наблюдателя History запрещена.

| Команда | Результат |
|---|---|
| В временной копии cmd при исходниках Temporal 1.29.7 `GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go test -mod=readonly .` и `go build -mod=readonly -o "$probe_dir/auth-poc" .` | Exit 0, Go package tests и сборка прошли. Код взят из `infra/temporal_auth_poc/*.go`. |
| В `backend` `env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/integration/postgres/test_native_auth_control.py --tb=short` | RED exit 1 для отсутствующего signed action. Итог после добавления отзыва exit 0, 1 passed. |
| Из корня с `PYTHONPATH="$PWD/infra/temporal_auth_poc"` и `G02_NATIVE_PROBE_BINARY` на собранный бинарник `backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_assigned_workflow.py backend/tests/integration/postgres/test_native_auth_control.py backend/tests/integration/postgres/test_migrations.py backend/tests/integration/postgres/test_schema_drift.py --tb=short` | Exit 0, 23 passed за 42.56 с, один SQLAlchemy warning `xid8`. Повтор native test с отдельной проверкой raw 503 → RPC UNAVAILABLE: exit 0, 1 passed, 15.80 с. |
| `make db-snapshot` | Exit 0, 1 пропуск штатной генерации. Ручная проверка дельты к исходному snapshot показала новый definer/ACL и расширение audit CHECK/RLS. Повтор schema drift без флага прошёл в наборе выше. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1935 passed, 3 OTel deprecation warnings, Ruff, mypy 260 файлов, 15 import contracts. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make contracts-check contracts-test` | Exit 0, шесть валидаторов и 47 passed. RED теста parity до enum дал 1 failed, после исправления целевой набор 2 passed. |
| `make infra-scan-secrets` и `git diff --check` | Exit 0, 0 findings и 0 ошибок whitespace. |

Независимые blind-first review одобрили локальный срез. Несовпадение signed
action в OpenAPI и отсутствие отдельного сценария отзыва исправлены тестами.
Действие допуска проверяется в момент DB-запроса. Уже допущенный read может
завершиться после конкурентного ACK или отзыва. Корректирующая запись делает
свою повторную проверку назначения и CAS. Гонка in-flight Describe не моделировалась
в native тесте. [Review](../reviews/G02_S17_S20_REVIEWS.md), [ECC](../ECC_USAGE.md).

Целевые TLS/identity, планировщик, восстановление Outbox, сверка после ACK и
общий pre-pr/Linux CI остаются этапами приёмки G02. Тесты использовали
временные сервисы и детерминированный LLMGatewayPort. Миграция проверена на
временном PostgreSQL. Штатный Compose продолжил работу.

## Пакетная сверка до ACK · 2026-11-20

**Статус:** локальный срез TESTED, S20 IN_PROGRESS. Ветка
`feat/g02-tool-registry-manager`, HEAD и подтверждённый `origin/main`
`7f0c29f9519217dba722ad1f5b6396d8a02216da`. Evidence относится к рабочему diff.

| Файл | Изменение |
|---|---|
| `backend/src/ai_res/application/reconcile_operations.py` | Backend-команда `reconcile_bound_start_page` обходит записи одного проекта с разрешёнными типами, активным assignment и точным Run. Курсор по UUID ограничивает объём работы за вызов. Для каждого кандидата используется коррекция ADR-149 с повторной проверкой состояния. |
| `backend/tests/integration/postgres/test_operation_execution_assignments.py` | Две страницы, повтор, transient observer, ACCEPTED/QUEUED, соседний проект, чужая организация, исключённый тип, отзыв и отсутствие привязки. |
| `backend/tests/integration/postgres/test_manager_http.py` | Проверка страницы на реальном Temporal. Сначала Run активен, затем `TERMINATED`. PostgreSQL фиксирует один атомарный переход и по одной записи аудита и Outbox. |
| Implementation-документы | ADR-150, handoff, status, gaps, requirements traceability, паспорт G02, ECC и review. |

Вызов использует существующие Backend DML и FORCE RLS. Новых миграций, ролей,
event schemas и изменений API в этом срезе нет. ADR-150 оформляет выбор UUID
курсора и повторную сверку каждого кандидата. Точные Run наблюдаются после
закрытия транзакции. Недоступность наблюдения оставляет Operation для следующего
обхода. Тесты исходной команды покрывают stale ACK/отзыв, неверный assignment и
неоднозначное наблюдение. Код аудита коррекции и correlation сохраняются.

Среда Darwin 25.6.0 arm64, Python 3.13.5, uv 0.11.31, PostgreSQL 16.15
и изолированный Temporal dev server через CLI 1.5.1, SDK 1.36.0.

| Команда | Результат |
|---|---|
| В `backend` `env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/integration/postgres/test_operation_execution_assignments.py::test_reconcile_bound_start_page_is_bounded_and_tenant_scoped --tb=short` | RED до реализации exit 1, отсутствующая команда. GREEN exit 0, 1 passed. |
| В `backend` `env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/integration/postgres/test_operation_execution_assignments.py tests/integration/postgres/test_manager_http.py tests/unit/test_operation_reconciliation.py --tb=short` | Итоговый запуск exit 0, 25 passed, 0 failed/skipped, 16.47 с. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Exit 0, 1935 passed, 0 failed/skipped, 3 OTel deprecation warnings. Ruff, mypy 259 файлов, 15 import contracts. После дополнения PostgreSQL test fixtures повторён точечный Ruff, exit 0. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make infra-scan-secrets` | Exit 0, 0 findings. |
| `git diff --check` | Exit 0. |

Независимые blind-first general/Python и security review одобрили внутренний
срез. Уровни CRITICAL/HIGH/MEDIUM без findings. Для production-планировщика
остаются доверенный источник scope и верхняя граница размера страницы.
[Review](../reviews/G02_S17_S20_REVIEWS.md), [ECC](../ECC_USAGE.md).

Общие pre-pr и Linux CI открыты до объединённой приёмки G02. Штатный Compose
оставался активным, для тестов использованы отдельные контейнеры. Модельные
вызовы отсутствовали. G-107 остаётся OPEN до допуска наблюдателя, подключения
планировщика, повторной доставки Outbox и сверки эффектов после ACK. Следующий
шаг S20 — проверить отдельную authority наблюдателя ADR-129 на точный Run.

## Продолжение от 2026-11-19

В worktree `AI-RES-G02` принят выбор владельца по NCP-14. Канонический
DOC-086, DOC-068 v1.4 и manifest v1.6, зеркало и schema-тесты определяют
ответ v0.4. `runtime/manager_reasoning.py` принимает до восьми разных
вопросов. Состояния OPEN, ANSWERED и UNKNOWN не смешиваются. Сведения идут
в недоверенную JSON-часть запроса через LLMGatewayPort. Human approval и
реплеи Temporal по-прежнему используют действующие границы.

`application/reconcile_operations.py` читает сохранённое назначение и Run,
закрывает транзакцию до наблюдения и проверяет версию и отзыв перед
`FAILED`. `test_operation_execution_assignments.py` проверяет отсутствие
побочных изменений для недоступного наблюдения, чужого назначения, stale
ACK/отзыва и чужого tenant. `test_manager_http.py` подтверждает точный Run в
изолированном Temporal dev server и фиксирует один audit и один Outbox.

Новых миграций в этом продолжении нет. Сохраняется текущая Alembic revision
`382befc90d62`. Общее состояние группы IN_PROGRESS. Требуются handler v0.4,
проверенный источник admissible history, production reconciliation и
целевой runtime. Model provider не вызывался, исходный Compose не менялся.

Manager Activity повторяет идемпотентную проверку ar2 после защищённого
чтения и перед reasoning. При уже записанном `CANCEL_REQUESTED` возвращает
состояние в Workflow без inference и без черновика. Тест с real Temporal
проверяет этот переход, успешный inference с контрольной строкой ответа,
отсутствие строки в Temporal history и replay. Проверка после чтения уменьшает
окно гонки. Перед включением v0.4 остаются текущие ACL, egress policy,
классификация каждого источника, проверка допуска близко к provider send
и политика для производного черновика.

**Evidence.** База `7f0c29f9519217dba722ad1f5b6396d8a02216da` и рабочий diff
`feat/g02-tool-registry-manager`, Darwin arm64, Python 3.13.5, Docker 29.2.0,
uv 0.11.31, PostgreSQL 16.15 и Temporal SDK 1.36.0.

| Проверка | Результат |
|---|---|
| `make pre-push-fast` до повторного ar2 ACK | exit 0. 1935 passed, 3 предупреждения, 15 import contracts. |
| `make backend-check` после повторного ar2 ACK | exit 0. Ruff, mypy 259 файлов, 15 import contracts. |
| `make contracts-check contracts-test` | exit 0. Шесть проверок валидаторов, 45 passed. |
| Из `backend`: `uv run --locked pytest -q tests/integration/postgres/test_operation_execution_assignments.py tests/integration/postgres/test_manager_http.py tests/integration/temporal/test_manager_workflows.py tests/unit/test_operation_reconciliation.py tests/unit/test_manager_reasoning.py --tb=short` | exit 0. 41 passed до добавления повторного ar2 ACK. |
| Из `backend`: `uv run --locked pytest -q tests/integration/temporal/test_manager_workflows.py tests/integration/postgres/test_manager_http.py --tb=short` | exit 0. 7 passed на актуальном Activity, включая новый case отмены. Тот case до исправления exit 1 и переходил в SUCCEEDED. |
| Из корня: `env PYTHONPATH="$PWD/infra/temporal_auth_poc" G02_NATIVE_PROBE_BINARY=/tmp/aires-temporal-auth.v53lrm/auth-poc backend/.venv/bin/python -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_native_assigned_workflow.py --tb=short` | exit 0. 1 passed за 8.17 с на ранее собранном изолированном PoC. Семь Go source inputs совпали с worktree. |
| `make infra-scan-secrets`, `git diff --check`, `uv run --locked alembic heads` (из `backend`) | exit 0. 0 findings, 0 ошибок whitespace в tracked diff, один head `382befc90d62`. |
| `python3 -B docs/implementation/tools/check_prompts.py` | exit 1. 14 замечаний относятся к структуре прежнего мини-этапа SLICE-01, который скрипт включает по шаблону S*.md. Все canonical ссылки Sxx разрешены после обновления S01/S04/S32. |
| Полные pre-pr и Linux CI G02 | Открыты. Оба локальных Docker context указывают на один daemon с работающим исходным Compose `ai-res`. Групповой runtime требует отдельной среды. |

Независимые ECC code/Python и security reviewers нашли 0 CRITICAL и 0 HIGH
в этом локальном scope. Исправлены строгая проверка DTO, синхронизация
согласования и описание уникальности. Security review повторного ACK
подтвердил локальное устранение вызова после зафиксированной отмены.
[Review](../reviews/G02_S17_S20_REVIEWS.md), [ECC](../ECC_USAGE.md).


**Дата:** 2026-11-18 · **Промпт:** [S20](prompts/S20_project_epic_intake_manager.md)
· **Статус:** IN_PROGRESS, IMPLEMENTATION NOT VERIFIED.
**Evidence:** `7f0c29f9519217dba722ad1f5b6396d8a02216da` + рабочий diff
ветки `feat/g02-tool-registry-manager`.

## 1. Текущий результат

- Проекция вопросов сохраняет один основной вопрос, отвечает на exact
  question ID, сохраняет UNKNOWN и воспроизводится без side effects.
- ar2 связывает подпись, метод, raw path, отсутствие query, digest, nonce,
  срок и точный assignment. Отдельная DB-роль потребляет nonce в своей
  транзакции. Platform controller проверяет назначение и Workflow Run,
  затем использует существующие Operation transitions с атомарным аудитом.
- Изолированный native PoC Temporal 1.29.7 проверил mTLS, SAN, queue ACL и
  receipt в PostgreSQL до доставки задания. Совместный тест запустил настоящий
  Manager Worker с детерминированным gateway и подтвердил `SUCCEEDED` в
  нативной истории и PostgreSQL. История не содержит входного и итогового текста.
- Детерминированная часть G-107 различает временную недоступность,
  подтверждённый terminal fault, закрытый Workflow, cancel и повторную
  доставку. Действия строятся по текущей Operation и exact assignment.

Принятые владельцем команды v0.3 читают только назначенное сообщение, сохраняют
неизменяемый черновик и материализуют задачи из утверждённого плана. Запись
черновика завершает текущий MANAGER_MESSAGE, а решение по черновику остаётся
у человека. Handoff Task идёт в PROPOSED и ждёт Readiness Gate. По
терминальному повтору сверяется SHA-256 без записи. Выдача текста аудируется
перед ответом, история Temporal содержит только ссылки и безопасные коды.

## 2. Нормативные источники

DOC-002 §§4–5, 17, 20, DOC-004 Manager Panel, DOC-006 §7.2, DOC-050
`sendManagerMessage`, DOC-008 Manager events, DOC-075 §§6, 9,
ADR-129 и G-107. По отдельному подтверждению владельца актуализированы
DOC-068 v1.3, DOC-084 v0.2, DOC-085 v0.3, Registry и DOC-082 v1.5.

## 3. Область файлов

`modules/epics/manager_questions.py`, `modules/iam/platform_credentials.py`,
`platform_nonces.py`, `modules/operations/execution_authority.py`,
`reconciliation.py`, `application/platform_control.py`,
`api/platform_v2.py`, `infra/temporal_auth_poc/`, PostgreSQL revisions и
провижининг. Точные файлы доступны в рабочем diff паспорта группы.

## 4. API и контракты

Защищённые внутренние OpenAPI v0.2 и v0.3 добавлены в canonical и зеркало.
Public API v1.3 и старый внутренний контракт сохранены. v2 проверяется в
изолированном ASGI-контуре. Первого `MANAGER_MESSAGE` producer в составе
текущего checkpoint нет.

## 5. Миграции

После S17 0027 добавлены 0028 (durable nonces), 0029 (assignments), 0030
(narrow Platform grants и pretenant audit), 0031–0032 (точные metadata
SELECT для существующих deferred invariant triggers). Проверочный PostgreSQL
16.15 disposable. 0033–0039 выполняют intake, связи, immutable proposals,
граф и журнал вопросов. 0040–0041 добавляют scoped grants и проверку approved
PlanItem mapping при вставке Task. 0042–0046 хранят digest выдачи, проверяют
назначение и точную привязку команды с доменным статусом, аудируют действие.
Миграции применялись в тестовых базах.

## 6. Технические решения

ADR-129 технический механизм. ADR-143 контракт ar2. Reconciliation отделяет
снимок Operation/Outbox от наблюдения Temporal и не создаёт бизнес-успех
из факта завершения workflow. Финальный apply должен сверить версию/assignment.

## 7. Нормативные изменения

Scoped owner approval от 2026-11-18 зафиксирован в NCP-14 и Registry §9.
Изменение общей семантики QUEUED вне принятого scope.

## 8. ECC

[Журнал](../ECC_USAGE.md) и [review](../reviews/G02_S17_S20_REVIEWS.md).
TDD agent добавил контрактные проверки с отдельным locked прогоном.

## 9. Проверки checkpoint

- `make contracts-check contracts-test` — exit 0, шесть проверок
  инструментария OK, 37 passed, включая v0.3.
- `cd backend && uv run --locked pytest -q tests/unit/test_operation_reconciliation.py`
  — 10 passed. Кодек ar2 отдельным прогоном — 3 passed.
- `backend/.venv/bin/python -B infra/temporal_auth_poc/check.py <binary>` —
  exit 0, три составных сценария PASS. Сборка `go build -p 4 -mod=readonly -trimpath`
  из upstream commit `1f74f0c8e9935980d92a39069185671bbbba7c7e` с помещёнными
  в отдельный пакет исходниками PoC. Darwin arm64, Go 1.26.3, Python
  3.13.5, Temporal SDK 1.36.0, PostgreSQL 16.15, Docker 29.2.0.
- `cd backend && uv run --locked pytest -q tests/integration/postgres/test_operation_execution_assignments.py`
  — exit 0, 2 passed после предоставления минимальных metadata grants.
- `cd infra && uv run --locked pytest -q tests/test_check_compose.py`
  — exit 0, 56 passed.

- Последний объединённый целевой backend-прогон PostgreSQL, Temporal, private
  TLS, old/new internal API, миграции и публичный Manager HTTP — 56 passed,
  1 предупреждение, exit 0. Полный backend на предыдущем проверенном срезе
  3289 passed, 540 предупреждений, exit 0. Тестовый gateway разрешён ADR-022.
- Изолированный `go test -p 4 -mod=readonly ./cmd/aires-auth-poc` — exit 0.
  Проверены exact Start, Ed25519/TLS, подмена tenant reference, доменный
  исход и строгое удаление поддерживаемого SDK transport field.
- `cd backend && env PYTHONPATH=../infra/temporal_auth_poc G02_NATIVE_PROBE_BINARY=<binary> uv run --locked pytest -q tests/integration/postgres/test_native_assigned_workflow.py --tb=short`
  — 1 passed в 6.70 с, exit 0. Публичный 202 → native Start → восстановление
  Run по первому событию → receipt → private TLS/ar2 → draft + завершение.
  Одно обращение в тестовый gateway.
- `cd backend && uv run --locked pytest -q tests/integration/postgres/test_native_auth_control.py tests/integration/postgres/test_task_issuance.py tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py --tb=short`
  — 22 passed, 1 предупреждение, exit 0 на migration head `382befc90d62`.
- При раннем полном infra-test общая метка Compose позволила тесту изменить
  мониторинг исходного checkout. Сервисы восстановлены, исходная ревизия
  PostgreSQL c97e3bf386f1 проверена. Добавлена проверка working_dir перед
  runtime-операциями. Повтор infra-test — 221 passed, 148 runtime skipped.

## 10. Проверенные security cases

Несовпадение ар2 path, action, body, key, expiry, query. Отказ чужому
assignment/Run, недоступность receipt store, запрет Manager/Worker чужой
очереди и неподписанному клиенту. Durable nonce одноразов в конкурирующих
транзакциях. Семантический повтор с новым nonce оставляет одно доменное
событие на переход, один audit и прежнее состояние Operation.

## 11. Независимое review

S17 и проекция S20 reviewed. Отдельные findings по ar2 и PoC решены
к моменту текущего checkout. Развёрнутый private TLS listener, production
Temporal authorizer, reconcile worker и объединённый diff требуют review.

## 12. Ограничения

PoC исчерпывающе подтверждает только перечисленные синтетические сценарии.
Открыты production native failure/cancel/recovery, связанность полного G-107,
адаптивные вопросы и проактивная выдача, запуск на целевом стеке. Публичный intake
прошёл в тестовом приложении с явно заданным допуском и лимитом тела. Изолированные проверки
покрывают private TLS, ar2 v0.3, запись и восстановление вопросов, отдельное
решение человека, атомарные assignment/Outbox и реальный Temporal replay.
Полный backend во время разработки выполнился с ошибками устаревшего
снимка и изменяющихся файлов. Затронутые тесты перепроверяются после фиксации.
Модельные вызовы в этой работе не выполнялись. Общий pre-pr/Linux CI
запускаются после состава группы.

## 13. Документация

Паспорт G02, handoff, status, ADR, ECC, NCP-14, Registry и traceability.

## 14. DoD

Частичное evidence локальной и изолированной механики. Deployed Manager
intake и оба проверенных product gate ADR-129/G-107 ещё требуются.

## 15. Продолжение

Доработка привязки полномочий к production transport и полного reconciliation
перед первым producer. После реализации internal intake и approval — S21.
