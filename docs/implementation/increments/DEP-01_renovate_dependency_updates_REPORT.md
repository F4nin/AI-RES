# DEP-01 — Renovate dependency updates: Increment Report

**Дата:** 2026-11-17 · **Промпт:** [DEP-01](prompts/DEP-01_renovate_dependency_updates.md). **Статус:** IN_PROGRESS. Config **TESTED локально**, полный pre-pr PASS; Linux CI/доставка продолжаются. GitHub App installation **NOT VERIFIED**.

## 1. Реализованный scope

`renovate.json`: weekly Monday 00–06 Europe/Moscow; ordinary updates age 14 days, timestamp-required/internal strict; 3 concurrent normal PR / 2 per hour (WORKING, ADR-121). Security vulnerabilityAlerts обходят ordinary schedule/age/limits, automerge/platformAutomerge выключены. Major/stateful review labels сохранены. Формат dependencyDashboard приведён к версии Renovate 44 (`enabled` object).

Native Docker/Actions/npm/pep621/nvm + custom RE2 для uv values в двух workflow формах, SYFT/TRIVY/validator/HADOLINT/actionlint images, двух MinIO TAG+COMMIT пар и всех MinIO/Caddy own-image references. Own `ai-res/*` не ищутся как remote registry packages. MinIO source+refs объединены по upstream package и groups; acceptance обнаруживает drift.

`make renovate-check`: официальный pinned Renovate **44.249.0**, index `sha256:595b3b1bd60514d1943d84a60c0ec57bbb2663ce1b5a981dccfe206283ca386c`, amd64+arm64, bundled Node **24.22.3**. Strict validator `--no-global --strict`, реальные RE2/extraction/normalization/package rules/update API; replacements только в tmpfs. Контейнер offline/read-only/no caps/no-new-privileges; mount содержит только curated config inputs, без `.git`/tokens/secrets/socket. Target включён в pre-pr и infra-static CI. Registry digest scan охватывает также shell/workflow image pins.

## 2. Источники и исходное состояние

AGENTS с диска включая §10, CONTEXT_RETENTION, CLAUDE, Registry v4.1, действующие implementation документы, Spec v1.22 и его текущие addenda; применимый canonical scope DOC-015 v1.7 §12–14, release/versioning, ADR-043/113. CI-01/ARCH-01 DONE. Начальная база `main` **823decd81833bdffe9b957b95ddf736f82ed6597**, чистое дерево, `git ls-remote origin refs/heads/main` подтвердил совпадение. Ветка `feat/dep-01-renovate-config`; до commit результаты относятся к этой базе + описанному diff.

## 3. Изменённые файлы

| Файлы | Изменение |
|---|---|
| `renovate.json` | Policy и custom managers |
| `infra/scripts/check_renovate.sh`, `infra/tests/renovate/check.mjs` | Isolated pinned validator + 10 real-API acceptance checks / 18 extracted deps |
| `infra/scripts/verify_digests.py` | Shell/workflow tool image pins включены в registry gate |
| Makefile, `.github/workflows/ci.yml` | Renovate check в pre-pr/infra-static, прежние gates сохранены |
| Implementation prompt/index/roadmap, ADR-121, STATUS/HANDOFF, gaps/decisions, traceability/ECC/tooling, review/report | Scope, разрешение установки App, evidence и ограничения |

## 4. API / contracts / events

Не изменены. `contracts/`, compatibility baseline, canonical и Registry не редактировались. Новая конфигурация относится к dev-time dependency PR, не к runtime Tool Registry/MCP продукта.

## 5. Миграции / данные / совместимость

Миграции, schema snapshot, RLS/roles, runtime application code, topology, package manifests/locks и существующие version/digest pins не менялись. Validator — отдельный digest-pinned tool, без глобальной установки/npm dependencies проекта. Full pre-pr использует штатный dev stack/Testcontainers; volumes не удаляются, secret rotation/bootstrap/backup drills не выполняются. Runtime tests могут оставлять synthetic dev data, полная неизменность dev-БД не заявляется.

## 6. Решения

ADR-121 ACCEPTED в пределах ADR-113: WORKING schedule/limits, exact validator, custom/native coverage, MinIO numeric timestamp ordering до секунды. Seconds используют числовой prerelease comparator при ignoreUnstable=false только для полного RELEASE timestamp pattern; chronological boundaries проверены настоящим versioning API. Пользователь затем прямо поручил установку App агенту; этот scope зафиксирован в DECISIONS_PENDING, не требует повторного approval.

## 7. Несогласованности / gaps

G-31 разделён: strict config checks уже выполнены, hosted App/onboarding пока нет. G-24 остаётся OPEN — настройка Renovate не устраняет существующие findings. SOPS/age version+checksum и embedded MinIO Go security overrides остаются контролируемыми ручными updates; checksum verification не ослаблена. Registries без timestamps (в частности GHCR tool image) могут удерживаться timestamp-required; автоматический обход возраста не включён. NCP не требуется, BASELINED не менялся.

## 8. ECC

Отдельный read-only planner до реализации; отдельные blind-first code-reviewer/security-reviewer + review финальной дельты, все 0 findings; verification-loop прочитан и применён как checklist, без Claude commands/hooks. Plugin-management skill прочитан и выполнен поиск доступного способа установки; неподключённые GitHub/TinyFish не подключались и не считаются доступными. Evidence — [DEP-01_REVIEWS](../reviews/DEP-01_REVIEWS.md), ECC_USAGE. DB/Temporal reviewer не требуется: corresponding runtime mechanisms не меняются.

## 9. Проверки

Среда: Darwin 25.6 arm64, Python 3.13.5, uv 0.11.31, Docker dev/test. Для contracts/pre-pr PATH процесса выбирает существующие Node 22.23.5/npm 10.9.9 и OpenSSL 3.6.3; Renovate исполняется на своём bundled Node 24.22.3. Глобальные настройки/зависимости не менялись.

| Команда | Результат |
|---|---|
| `docker buildx imagetools inspect ghcr.io/renovatebot/renovate:44.249.0` | exit 0, index digest и amd64/arm64 manifests проверены; последующий pull по exact digest exit 0 |
| `bash infra/scripts/check_renovate.sh` / `make renovate-check` | exit 0: strict validation **1 config**, **10 acceptance passed / 0 failed / 0 skipped**, **18 extracted dependencies**. Direct internal API harness печатает note об ещё не инициализированном logger; assertions не подавляются. |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | exit 0: ruff/mypy (148 source files), 14 kept/0 broken, **465 passed**, 4 warnings, 0 failed/errors/skipped; pytest 7.15 s |
| `infra/.venv/bin/ruff check infra`, `git diff --check` | exit 0 |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make infra-verify-digests` | Первый run exit 2: 19 OK, Temporal UI registry=None. Отдельный `docker buildx imagetools inspect temporalio/ui:2.49.1` exit 0 вернул ровно закреплённый digest. Полный повтор gate **exit 0: 20 pinned images / 0 mismatches**. Pins/checker semantics не менялись ради PASS. |
| Registry canonical presence/uniqueness (Python -B, read-only) | exit 0: 74 records / 74 unique IDs / 74 unique paths, missing 0 |
| `infra/.venv/bin/python -B docs/implementation/tools/check_prompts.py`, `infra/.venv/bin/python -B infra/scripts/scan_secrets.py` | exit 0: 40 S-промптов / 0 issues (DEP mini prompt дополнительно проверен review вручную); scan 0 findings; существующие exclusions review/ECC prose сохранены, весь diff также просмотрен вручную |
| Полный `make -j1 pre-pr` | **exit 0**: contracts **22 passed** (6.13 s), Renovate strict + **10 acceptance passed**, backend **1301 passed**, 540 warnings (275.85 s), infra **307 passed** (133.65 s), отдельный runtime **148 passed** (128.81 s); 0 failed/errors/skipped, scan 0 findings, ruff/mypy PASS, 14 import contracts kept. Runtime 148 уже входят в infra 307 и затем повторяются; это не сумма уникальных tests. Existing dev secrets: 21 файл / 0 written. |
| Independent reviews | code/security + финальная дельта: 0 findings |
| GitHub `gh api user/installations` (только lookup для разрешённой установки) | exit 1, HTTP **403**: requires access token authorized to a GitHub App; credentials не извлекались/не печатались |

Точная текущая команда полного прогона:

```sh
PATH="/private/tmp/arch-01-tools/node-v22.23.5-darwin-arm64/bin:/opt/homebrew/opt/openssl@3/bin:$PATH" UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-pr > /private/tmp/dep-01-pre-pr.log 2>&1
```

Предварительные неуспешные запуски не считаются PASS: Docker Hub `44.249.0-slim` не существует (выбран официальный GHCR exact version/index); strict validation потребовал миграцию dashboard boolean→object; harness приведён к реальному internal manager ID `regex` и normalizeDepNames, затем actual checks прошли. Не выполнялся hosted write/dry-run над репозиторием до установки App. Raw local logs — вспомогательный system temp; постоянные результаты сохраняются здесь, Linux CI URL добавляются по факту.

## 10. Security / authorization

Запрет automerge, отсутствие глобального/repo credential в validator, curated read-only mount и offline network; malformed SHA не даёт version-only match; atomic replacement сохраняет version/digest/source refs. GitHub vulnerability alerts требуют включённых Dependency graph/Dependabot alerts и permissions установленного App, не покрывают произвольные source/Docker CVE автоматически; существующие audits/scans не отключены. Ни один dependency update PR не сливается автоматически этим этапом. Runtime auth/ACL не менялись; regression проверяется полным набором.

## 11. Независимое review

[Протокол](../reviews/DEP-01_REVIEWS.md): два отдельных blind-first read-only агента; CRITICAL/HIGH/MEDIUM/LOW = 0, повторный delta review обоих = 0. Исправлений по findings не требовалось. Это review config/gates, не hosted App acceptance.

## 12. App installation — отдельный незавершённый результат

Владелец прямо разрешил установку App агенту **только** на AI-RES. Доступный GitHub CLI credential получил 403 на installation API; подключённого браузерного инструмента нет. Plugin discovery проведён; GitHub/TinyFish доступны для отдельного подключения, но сейчас не подключены; cloud browser и передача ему credentials не авторизованы автоматически установкой Renovate. Не создавался App/token, не запускался self-hosted бот как подмена, не менялись другие repositories.

При сохранении ограничения после готового конфига в main нужен интерактивный переход на [официальную установку Renovate](https://github.com/apps/renovate/installations/new), **Only select repositories → AI-RES → Install**. После этого проверить onboarding/dashboard и отсутствие config errors. Нового разрешения на саму установку не нужно; недостаёт механизма аутентифицированного browser consent. Ссылка/403 не доказывают фактическую установку. До этого App **NOT VERIFIED**, полный DEP-01 не DONE.

Локальный Chrome найден; после доставки конфига будет проверена возможность точечного управления официальной installation page стандартным механизмом ОС. Настройки браузера/automation и глобальные permissions автоматически не расширяются. Наличие установленного браузера само по себе не доказывает доступ к аутентифицированному UI или завершённую установку.

## 13. Документы / traceability

Обновлены prompt/index, roadmap-ссылка на выбранный owner scope, ADR-121, STATUS/HANDOFF, KNOWN_GAPS G-31, DECISIONS_PENDING, REQUIREMENTS_TRACEABILITY, ECC_USAGE, tooling README и review/report. Public CONTRACT_TRACEABILITY_MAP не меняется: API/event/persistence mapping прежние. Canonical/Registry, baseline manifest, прочие product statuses сохранены.

## 14. DoD

Config/target acceptance, fast tests и полный локальный pre-pr пройдены, independent review выполнено. Linux CI и доставка config ещё не завершены. App installation/hosted runtime NOT VERIFIED. Разделять эти результаты; конфигурацию не повышать до VERIFIED до Linux gates, весь DEP-01 не считать DONE до установленного App.

## 15. Следующий безопасный шаг

Завершить config gates/доставку DEP-01, затем подтвердить установку и onboarding App доступным разрешённым механизмом либо передать точный интерактивный шаг владельцу. Не начинать PROF-01/S16/SLICE-01/другой продуктовый этап по текущему поручению. Блокировки/бюджеты/approval будущих этапов сохраняются.
