# Постоянный процесс Codex: проверка и независимое review

**Дата:** 2026-11-17. **Scope:** документирование семи согласованных решений владельца, без реализации следующего инкремента. Исходная версия — `main`, HEAD `ab5e75439f0201bbec3bb0c910ef86d031f58e8a`, чистое рабочее дерево; доставка — ветка `docs/codex-autonomous-process`. Проверки ниже относятся к этому HEAD плюс документационный diff задачи, не к будущим инкрементам.

## Изменения

Изменены `AGENTS.md`, `CONTEXT_HANDOFF.md`, `DECISIONS_PENDING.md`, `tooling/CONTEXT_RETENTION.md`, `tooling/README.md`, журнал `ECC_USAGE.md`; добавлен этот отчёт. Постоянные правила — AGENTS §10; подробности восстановления/сохранения — существующий CONTEXT_RETENTION. Отдельный roadmap, runtime loop, hooks или конфигурация клиента не создавались.

На исходном документационном этапе API/event contracts, миграции, данные, версии пакетов, lock-файлы, продуктовый код, `docs/architecture/`, CLAUDE/.claude/MCP-конфигурации не менялись. Затем владелец отдельно разрешил устранить Caddy CI blocker: однострочное изменение infrastructure index pin описано в завершающем разделе. Статусы S00–S39/мини-этапов не повышаются. Новое owner approval удовлетворяет прежним требованиям отдельных Git/dev/MCP разрешений в том же scope; product/security approval, специальные запреты и sandbox сохранены.

## Выполненные проверки

Среда: локальный macOS arm64; Python 3.13.5 (существующий `infra/.venv`), uv 0.11.31, Codex CLI 0.169.0. В PATH Node v26.12.1/npm 11.20.0; npm/Node установки и тесты локально не запускались, это не повторение исторической приёмки Node 22.

| Команда/способ | Результат | Ограничение |
|---|---|---|
| `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, `git diff --check` | Исходный main/HEAD установлен, исходное дерево чистое; diff check exit 0 | Финальные refs после доставки проверяются отдельно |
| `git ls-remote origin refs/heads/main` | exit 0, remote main совпал с `ab5e75439f0201bbec3bb0c910ef86d031f58e8a` | Снимок на момент проверки, не вечная актуальность |
| Inline read-only Python, `infra/.venv/bin/python -B -` | 74 записи Registry, 74 уникальных ID/пути, 0 отсутствующих canonical; 4 локальные Markdown file-ссылки основного diff и 9 опорных process paths существуют; исходный scope 5/5 ожидаемых файлов | Проверка наличия/ссылок, не семантики всех canonical документов |
| Проверка первых 32768 bytes AGENTS тем же Python | Bootstrap полного чтения AGENTS §10 и CONTEXT_RETENTION виден в начале | Наблюдавшееся усечение автофрагмента; новый клиент/новая сессия целиком не запускались |
| `infra/.venv/bin/python -B infra/scripts/scan_secrets.py` | exit 0, 0 findings | Штатный охват scanner; не повторный скан всей истории |
| Финальная inline Python проверка scope и ссылок; `git diff --exit-code ab5e754 -- CLAUDE.md .claude .codex .serena .mcp.json docs/architecture backend contracts infra frontend Makefile docs/implementation/IMPLEMENTATION_ROADMAP.md docs/implementation/IMPLEMENTATION_STATUS.md docs/implementation/ARCHITECTURE_DECISION_LOG.md` | exit 0; 7/7 ожидаемых документационных файлов, 5 локальных file-ссылок без missing; защищённые поверхности неизменны | Отчёт/review-документ включён в финальный scope; не runtime-проверка |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Разрешённый запуск вне sandbox: exit 0, Ruff PASS, mypy 148 files PASS, import-linter 12 kept/0 broken, pytest 455 passed/0 failed/errors/skipped, 4 warnings, 8.02 s pytest | Первый запуск в sandbox: exit 2 до проверок, uv cache `Operation not permitted`; исправление продукта не требовалось. Быстрый слой не заменяет pre-pr/CI продуктового этапа |

`make pre-pr`, backend/infrastructure runtime, migration/API/security integration suites локально не запускались: это узкий docs scope, соответствующие поверхности не изменены, продуктовый инкремент не закрывается как VERIFIED. Неприменимы G2/G3/G4/G6 и runtime-часть G5; G1/G5 проверены в применимом объёме diff/secret/fast-check, G7 — ниже, G8/G9 — документация и этот отчёт. Применимые CI jobs на опубликованной версии сохраняются. Не выполнялись MCP/OAuth, сборка/остановка стека, миграции, генерация секретов, обновления пакетов или отложенные инфраструктурные сценарии.

## Сценарий новой сессии без реализации

| Сценарий | Наблюдаемое основание и ожидаемое действие |
|---|---|
| Короткая команда в новой сессии | Раннее указание AGENTS требует явно прочитать весь файл с диска и CONTEXT_RETENTION до выбора/Git; по одному автофрагменту не стартовать |
| Незавершённая работа | В ходе проверки текущая работа — документирование/доставка этого процесса; сначала закрыть её. При незавершённом инкременте далее — продолжить его, включая review/CI, без нового выбора |
| Выбор следующего | Продуктовых IN_PROGRESS нет. Первый обоснованный кандидат после этой задачи — ARCH-01: ADR-114 помещает сразу после CI-01 и до S17. Это не реализация ARCH-01 и не новый приоритет вместо ADR |
| Проверка зависимости | CI-01 DONE: STATUS + существующий отчёт + merge PR #20 в локальной истории. Историческая строка ARCH-01 PENDING_DEPS требует сверки фактов; не означает повторный CI-01 |
| Проверка реализации | В pyproject 12 import-linter contracts типа forbidden; согласованные ARCH-01 layers/independence между доменными модулями ещё отсутствуют. Промпт ARCH-01 пишется при старте согласно owner/ADR, отсутствие заранее не заменяется произвольным scope |
| Блокеры/альтернативы | S16 BLOCKED, не начат; не выбирать его только по номеру. Не брать произвольный READY S18/S19/S27/S35. При отсутствии приоритета после проверки всех актуальных решений — представить варианты владельцу |
| Review и доставка | Необходимые отдельные read-only reviewers, blind-first; обязательный reviewer недоступен → не выше TESTED, без merge. Commit/push/PR разрешены; merge только после применимых gates и обязательного Linux CI по точному SHA |
| Пауза/блокировка | Сохранить ветку/HEAD/diff, сделанное, невыполненные gates, вопросы и точный следующий шаг в существующем контексте; не обходить blocker |
| Завершение | Проверить итоговый Git/CI, сохранить evidence, выдать русский отчёт, остановиться до новой команды; следующий инкремент не запускать |

## Независимое review

Выполнено отдельными Codex-агентами, read-only, blind-first: оба формировали первоначальные выводы до создания этого отчёта. Это dev-time роли, не Runtime Workers и не human approval.

- `process_review`: ECC `code-reviewer` + checklist `doc-updater`, весь основной diff/источники и dry run. Выявлен один MEDIUM: §10 первоначально находился за границей фактически подставленного автоматического фрагмента AGENTS. Исправление — bootstrap в первых строках, явно требующий полного чтения с диска. Повторная проверка: APPROVE, открытых CRITICAL/HIGH/MEDIUM нет.
- `permission_review`: ECC `security-reviewer` + evidence/severity `code-reviewer`, границы standing permissions, Git/merge gates, dev/test, secrets, dependencies, MCP/egress и product approval. APPROVE, 0 findings; отдельная проверка bootstrap-дельты — APPROVE, 0 findings.

Оба проверили `git diff --check` (exit 0); security reviewer дополнительно подтвердил отсутствие diff в code/canonical/config surfaces. Наличие постоянных инструкций не доказывает автономное выполнение будущего инкремента: реальный новый runtime-cycle здесь намеренно не запускался. Детерминированные проверки и два review подтверждают документированный порядок в этом scope.

## Доставка и следующий шаг

Git-доставка разрешена прямым решением владельца 2026-11-17; публикация/CI/merge проверяются после формирования коммита, без приписывания результатов исходному SHA. Постоянное evidence публикации — GitHub PR/Actions и итоговый отчёт с точными ссылками. До успешных обязательных checks merge не выполнять.

Создан [PR #21](https://github.com/F4nin/AI-RES/pull/21), исходный опубликованный commit `9c9d7fc517a5a8a6f2f7aafbfbac1c1dea20c35c`. На момент записи стартовали [ci 44047390449](https://github.com/F4nin/AI-RES/actions/runs/44047390449) и [contracts 44047390580](https://github.com/F4nin/AI-RES/actions/runs/44047390580); запуск не считается PASS. Эта запись добавляет только документационные результаты; перед merge проверяются checks финального head PR, их SHA/conclusion/jobs, а не автоматически результаты исходного коммита. Финальные GitHub checks доступны из PR и проверяются также после merge.

**Выявлен blocker CI на исходном опубликованном SHA:** contracts push/PR ([PR run 44047473298](https://github.com/F4nin/AI-RES/actions/runs/44047473298)) — success; infra-static в push и [PR ci 44047473294](https://github.com/F4nin/AI-RES/actions/runs/44047473294) failed на проверке digest `caddy:2.11.9`. Остальные 14 refs совпали. Предшествующие infra-check/static tests/secret scan — success; hadolint/actionlint после failure skipped и не считаются PASS. Backend/runtime на момент диагностики ещё выполнялись. Merge заблокирован независимо от локального PASS.

Закреплённый index `sha256:f971688b2aaf1a26d256de552f17fb13f64fc5ed2dee4cf40c7f9d70cea0e12d`; текущий registry index `sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b`. Read-only `docker buildx imagetools inspect caddy:2.11.9@sha256:<digest> --raw` для обоих — exit 0 вне sandbox. Все 7 Linux descriptors и 7 их attestations идентичны, прежний Windows descriptor сохранён, добавлен Windows `10.0.20348.5873` с digest `sha256:166ed6c94d1b1204a448f1254b7d68284a000cd8aa8a1993fcae364c7e5e426b`. Это не утверждение эквивалентности всех ОС. Локальное evidence: `codex-process-caddy-categbdt/{pinned,registry,comparison}.json` в системном temp; существенные выводы сохранены здесь. Первый sandbox inspect failed на DNS, разрешённое повторение прошло. Job logs прочитаны whitelist-фильтром только строк digest; сырые логи/секреты не выводились.

Владельцу представлен точный вариант исправления: заменить только index digest в `infra/images/caddy/Dockerfile`, сохранив Caddy 2.11.9, записать evidence и повторить CI. Это обновление инфраструктуры вне исходного docs scope, поэтому по AGENTS §10 отдельно запрошено решение. До ответа pin не меняется; его нельзя молча обновить или отключить gate ради merge. Текущее ограничение готовности — доставка через обязательный CI, а не отсутствие постоянных инструкций.

Последующая проверка PR run `44047473294` на том же SHA: backend job — success (включая dependency audit), runtime ещё выполняется; contracts PR run `44047473298` — completed/success. Независимое read-only `permission_review` отдельно сравнило два полученных индексных JSON: прежних descriptors не удалено/изменено, добавлен только указанный Windows descriptor, 0 security findings для предложенного минимального pin diff. Это review предложения, не разрешение владельца и не новый runtime PASS.

После закрытия этой задачи ожидать новой короткой команды. Для ARCH-01 заново проверить текущую реализацию, установленный import-linter, зависимости/ADR, подготовить предусмотренный промпт и выполнить один инкремент. Новые бизнес-/security-решения, внешние расходы и специальные ограничения автоматически не утверждаются.

## Устранение Caddy blocker по поручению владельца — 2026-11-17

Владелец прямо поручил закрыть CI blocker и спросил о фиксированной релизной версии. Рабочая база — ветка `docs/codex-autonomous-process`, HEAD `8f3d487f57347caffd45e6475e3465e9927717ce`, чистое дерево. Scope расширен только на `infra/images/caddy/Dockerfile` (одна строка FROM digest) и связанные implementation evidence/решения/контекст/ECC. Версия `2.11.9`, build-команда `setcap`, digest checker и все gates неизменны. Продуктовые API/БД/данные/lock-файлы/canonical не меняются.

Повторно прочитаны `docker buildx imagetools inspect caddy:2.11.9@sha256:<старый digest> --raw` и `docker buildx imagetools inspect caddy:2.11.9 --raw` (оба exit 0). Отдельное inspect tag подтвердило текущий OCI index `sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b`. Новый локальный протокол `caddy-blocker-fix-o404mtra/{pinned,current}.json`: 7 Linux descriptors и 7 attestations полностью совпадают; все прежние descriptors сохранены, добавлен только Windows `10.0.20348.5873` с digest `sha256:166ed6c94d1b1204a448f1254b7d68284a000cd8aa8a1993fcae364c7e5e426b`. Linux amd64 остаётся `sha256:fc9cbc100585871d18d4e451cca7021785c90a7006087427ae5ceb3e4efe6424`, arm64/v8 — `sha256:9ee998103a2bc0d4392bbe9738b4069da1562d6920b3cd8088cfd098a8270120`.

Фиксированный релизный tag уже используется. Docker допускает обновление tag; digest фиксирует точный артефакт ([официальная документация Docker](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)). DOC-015 §12.2/§13.1 требует version tag + digest и проверку refresh даже без смены версии. Удалять digest, закреплять одну архитектуру вместо существующего index или отключать gate для текущего исправления не требуется. Строгий checker по-прежнему сравнивает pin с текущим tag, поэтому будущий upstream index refresh может снова потребовать контролируемого обновления. Автоматизация updates относится к существующему DEP-01/ADR-113; этот мини-этап не запускался, новая политика supply-chain не вводилась.

Независимое blind-first review фактического diff выполнено повторно до написания этого раздела:

- `process_review` / ECC `code-reviewer`: APPROVE, 0 findings; соответствует DOC-015 §12.2/§13.1, новый тест на конкретный digest не нужен, CI на исправленной версии обязателен.
- `permission_review` / ECC `security-reviewer` + evidence checklist: APPROVE, 0 findings; самостоятельно сравнены повторно полученные JSON, подтвердились 7 Linux/7 attestations и только одно Windows-добавление. Runtime/registry запрос самим reviewer не выполнялся.

Локальные проверки на указанном HEAD + минимальный diff (Python 3.13.5, uv 0.11.31, Darwin arm64):

| Команда | Результат |
|---|---|
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make infra-verify-digests` | exit 0, 15 pinned images, 0 mismatches |
| Те же четыре переменные + `make -j1 pre-push-fast` | exit 0, Ruff PASS, mypy 148 files PASS, 12 import contracts kept, pytest 455 passed/0 failed/errors/skipped, 4 warnings (6.47 s pytest) |
| Те же переменные + `make infra-check` | exit 0, Ruff PASS, три Compose-комбинации по 22 services/0 violations |
| Из `infra/`: `PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests --ignore=tests/runtime --tb=no` | разрешённый запуск вне sandbox: exit 0, 159 passed/0 failed/errors/skipped (3.49 s). PATH только процесса, используется уже установленный OpenSSL 3.6.3; глобальная конфигурация не менялась |
| `infra/.venv/bin/python -B infra/scripts/scan_secrets.py`, `git diff --check` | exit 0, 0 findings; diff check PASS |

Сохранена неудачная первая попытка infra tests в sandbox с системным LibreSSL 3.3.6: 156 passed/3 failed (Docker socket denied в двух promtool tests и неподдерживаемый Ed25519 в LibreSSL). Product/tests не исправлялись и проверки не ослаблялись; повтор теми же тестами с доступом Docker и установленным OpenSSL прошёл. Не использовались действующие секреты для генерации тестовых ключей.

Полный локальный `make pre-pr` повторно не выполнялся: это не новый продуктовый этап; идентичность всех используемых Linux manifests подтверждена сравнением, прежнее runtime evidence сохраняется только для соответствующих артефактов. Новый обязательный Linux CI (build/runtime/static/contracts/audit/digests/supply-chain) на исправленном SHA проверяется до merge и отдельно от старых failed runs. Новые миграции, перезапуск основного стека, генерация его секретов и отложенные backup/drills не выполнялись.

## Окончательный вариант: релизный Linux-тег Caddy

Промежуточный commit `b02634f0cf3fc00f6cc801be7afb539f3ef36695` успешно проверен: [PR ci 44050409094](https://github.com/F4nin/AI-RES/actions/runs/44050409094), [PR contracts 44050409158](https://github.com/F4nin/AI-RES/actions/runs/44050409158), [push ci 44050399799](https://github.com/F4nin/AI-RES/actions/runs/44050399799), [push contracts 44050400016](https://github.com/F4nin/AI-RES/actions/runs/44050400016). Backend 1291 passed (540 warnings), infra-static 159 passed, runtime 148 passed, contracts 22 passed; failed/errors/test skips отсутствуют. Audit, 15 digests/0 mismatches, hadolint/actionlint, secret scans, SBOM/vulnerability scan — success. Failure-only logs и PR-only baseline guard на push неприменимы, не выдаются за выполненные проверки. Обезличенный протокол — `/private/tmp/codex-process-ci-b02634f.json`.

Чтобы убрать причину Windows-only churn, в рамках того же разрешённого исправления дополнительно проверен официальный `caddy:2.11.9-alpine`. [Docker Hub](https://hub.docker.com/_/caddy) различает simple tag `2.11.9-alpine` и shared tag `2.11.9`, объединяющий Alpine/Linux и Windows. Registry `docker buildx imagetools inspect caddy:2.11.9-alpine --raw` и отдельный inspect — exit 0, OCI index `sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0`. Локальные JSON — `caddy-linux-variant-x9i4e9k5/alpine.json` и предыдущее `caddy-blocker-fix-o404mtra/current.json`.

В обоих индексах все 7 Linux descriptors и 7 attestations полностью идентичны. В Alpine index 14 descriptors и нет Windows; общий index содержит ещё два Windows descriptors. Окончательный FROM — `caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0`, добавлен поясняющий комментарий. Версия Caddy, все используемые Linux платформы, capability removal, собственный image tag `ai-res/caddy:2.11.9` и его ссылки в Compose/runtime/supply-chain не меняются. Это не переход на другую Linux-базу: выбранные Linux artifacts уже были Alpine. Отдельное обновление Windows больше не меняет этот simple-tag index; Linux rebuild всё ещё может изменить tag→digest и будет обнаружен прежним checker. Вечная неизменность upstream tag не заявляется.

Фактический FROM diff повторно проверен отдельными `process_review` (`code-reviewer`) и `permission_review` (`security-reviewer` + evidence) read-only, blind-first, до написания этого раздела. Оба самостоятельно сравнили JSON: 7 Linux/7 attestations идентичны, Windows — 0, schema/mediaType совпадают; оба APPROVE/0 findings. Checker/CI/Compose unchanged, дополнительные код/тест на конкретное значение pin не требуются.

Повторные локальные проверки на HEAD `b02634f` плюс окончательный diff: `make -j1 pre-push-fast` с прежними четырьмя offline/no-sync переменными — exit 0, 455 passed/4 warnings (6.89 s pytest), Ruff/mypy/12 import contracts PASS; `make infra-check` — exit 0, 3 × 22 services/0 violations. Infra static tests с установленным OpenSSL 3 только в PATH процесса и вне sandbox — exit 0, 159 passed (3.28 s). Первый registry check окончательного варианта подтвердил Caddy Alpine, но вернул `registry=None` для неизменённых PostgreSQL/admin-tools (exit 2 у make); это отсутствие ответа, а не доказанный сдвиг pin, повторная проверка проводится без изменения этих образов. Новое обязательное CI на окончательном SHA сохраняется перед merge, успех промежуточного SHA не переносится автоматически.

Повтор того же `make infra-verify-digests` завершился exit 0: все 15 pinned images совпали, 0 mismatches; PostgreSQL/admin-tools pins не менялись. Финальные `git diff --check` и штатный secret scan — exit 0, 0 findings.

## Финальная проверка и доставка

Окончательный FROM проверен на commit `6fe0176f2506d0090bb164d931e19a89baecf16e`: [PR ci 44052484683](https://github.com/F4nin/AI-RES/actions/runs/44052484683), [PR contracts 44052484667](https://github.com/F4nin/AI-RES/actions/runs/44052484667), [push ci 44052475850](https://github.com/F4nin/AI-RES/actions/runs/44052475850), [push contracts 44052475820](https://github.com/F4nin/AI-RES/actions/runs/44052475820) — success. Перед merge `gh pr view 21 --json headRefOid,mergeStateStatus,statusCheckRollup` подтвердил точный head, все 8 checks COMPLETED/SUCCESS, mergeStateStatus CLEAN.

Численные summaries PR job logs (получены whitelist-фильтром, сырые логи/secret values не выводились): backend **1291 passed, 540 warnings** (219.31 s); infra-static **159 passed** (5.90 s), **15 pinned images/0 mismatches**, secret scan 0; runtime **148 passed** (144.85 s), secret scan 0; contracts **22 passed** (7.15 s). Failures/errors/test skips отсутствуют. Все дополнительные audit/hadolint/actionlint/SBOM/vulnerability steps — success; failure-only stack logs неприменимы и не считаются тестом. Обезличенный локальный протокол — `/private/tmp/codex-process-ci-6fe0176.json`, постоянное evidence — ссылки выше и эта сводка.

`gh pr merge 21 --merge --match-head-commit 6fe0176f2506d0090bb164d931e19a89baecf16e` — exit 0. [PR #21](https://github.com/F4nin/AI-RES/pull/21) MERGED `2026-11-17T09:19:27Z`, merge SHA `5cd3d17db2e887017ac3a1f89ee552f33d193bb6`. `git fetch origin main`, `git switch main`, `git merge --ff-only origin/main` — exit 0, main обновлён, дерево чистое; `git diff --exit-code 6fe0176 HEAD` — exit 0: merge tree идентичен проверенному head. История не переписывалась.

Post-merge [ci 44054525105](https://github.com/F4nin/AI-RES/actions/runs/44054525105) и [contracts 44054525039](https://github.com/F4nin/AI-RES/actions/runs/44054525039) на SHA `5cd3d17db2e887017ac3a1f89ee552f33d193bb6` — **completed/success**. Числа получены отдельно из job logs whitelist-фильтром: backend **1291 passed, 540 warnings** (273.79 s), infra-static **159 passed** (5.67 s), runtime **148 passed** (146.97 s), contracts **22 passed** (6.67 s). Test failures/errors/skips отсутствуют, 15 digests/0 mismatches, secret scans 0, все audit/hadolint/actionlint/SBOM/vulnerability checks success. Failure-only stack logs и PR-only baseline guard на push неприменимы. Обезличенный протокол — `/private/tmp/codex-process-ci-main-5cd3d17.json`; постоянное evidence — ссылки и эта сводка. Ранее pending статус не объявлялся PASS до этой проверки.

Закрывающий checkpoint в ветке `docs/codex-process-closeout` меняет только два implementation-документа (handoff и этот отчёт), продуктовые/infra/config surfaces сохранены относительно проверенного `5cd3d17`. Он не подменяет своим SHA runtime CI предыдущей версии; приёмка runtime относится к указанному source SHA. Неприменимость повторного runtime для docs-only подтверждена scope diff; contracts CI и применимые diff/link/secret/fast checks сохраняются. После публикации SHA/PR и текущие refs устанавливать по Git. Отдельное read-only delta review итоговой записи `process_review` — APPROVE/0 findings; counts/границы evidence сверены с обезличенным протоколом, `git diff --check` — exit 0.

Следующее действие после доставки итогового документационного checkpoint — остановиться до новой команды владельца. Следующий обоснованный кандидат ARCH-01 по ADR-114 остаётся NOT_STARTED; DEV/MCP/платные вызовы/backup/drills и другие инкременты этим закрытием не запускаются. Постоянные правила находятся в main и позволяют продолжать по короткой команде, сохраняя вопросы владельцу для новых решений/блокеров и ограничения среды.
