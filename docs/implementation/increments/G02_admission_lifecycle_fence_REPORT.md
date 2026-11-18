# G156 — Admission lifecycle fence: Increment Report

**Дата:** 2026-11-18. **Промпт:** [scope](prompts/G02_admission_lifecycle_fence.md).
**Результат:** узкий механизм ADR138 локально TESTED. Подготовка G156 IN_PROGRESS;
полный G156 NOT VERIFIED, G02/S17/S20/S21 NOT_STARTED.

## 1. Что реализовано

Закрыта гонка между lifecycle UPDATE профиля и begin/finalize admission. Guard
берёт transaction advisory fence по UUID до control lock и читает lifecycle после
ожидания отдельным statement. Новый invoker BEFORE UPDATE trigger берёт тот же
fence при изменении status/approved_at/approved_by/deprecated_at observed Flash.

Если revoke committed первым, begin не выдаёт ticket, finalize не принимает
результат и сохраняет pending. Если guard первый, его commit упорядочен до
ожидающего owner UPDATE. После commit/rollback lock освобождается. Прежние
generation, single-flight, sticky block, replay и атомарный audit сохраняются.

READ COMMITTED обязателен. Отсутствующий, отключённый, replica-only или неполный
trigger, неверный function binding и session replication mode дают отказ.
Это проверка trusted schema binding, не контроль целостности function body
против DBA. API по-прежнему имеет только SELECT на model_profiles.

## 2. Нормативная база и Registry

Прочитаны AGENTS целиком/CONTEXT_RETENTION, CLAUDE, Registry, Spec, устав/gates/
стратегия/tooling, текущие G02 report/handoff/plan и ADR128/131/132. Canonical
основание: DOC076 v1.1 §3.1/7, DOC068, DOC072, IAM/security/observability. Отдельная
read-only нормативная разведка проверила применимые startup sections/current
addenda: 74canonical/0missing/0duplicates, 73manifest SHA+bytes/0mismatch;
OpenAPI117/AsyncAPI360/Worker10 local refs без missing. Это reconnaissance,
не runtime или pinned validation. Конфликтов выбранного scope не выявлено.

Механизм сверён с official PostgreSQL16 docs, ссылки в [ADR138](../decisions/ADR-138-admission-lifecycle-fence.md).
Canonical документы/Registry/manifest и зеркала этим срезом не менялись.

## 3. Файлы и scope

Ветка `feat/g02-manager-tools-planning`, HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + working diff. На старте142изменённых/
новых файла; initial SHA256/bytes сохранены до edits. Прежняя накопленная работа
не присваивается этому срезу. [Final code hashes](../reviews/G02_ADMISSION_LIFECYCLE_CODE_HASHES.json).

| Файл/область | Изменение |
|---|---|
| `modules/model_registry/admission.py` | Isolation/schema readiness и fence до control |
| `db/migrations/versions/0025_model_admission_lifecycle_fence.py` | Новый invoker function/trigger, PUBLIC EXECUTE revoked |
| `tests/integration/postgres/test_model_admission_lifecycle.py` | 36реальных PG cases |
| `backend/ops/postgres/schema_snapshot.sql` | Explicit regeneration, reviewed +20строк относительно initial bytes |
| Implementation docs/evidence | ADR138, prompt/report/review/hashes, index/status/handoff/passport/plan/gap/traceability/ECC |

## 4. API, контракты и события

Public API/events/Worker DTO/internal wire contracts не меняются. Factory,
pinned ModelProfile/ModelIdentity и Bifrost adapter прежние. Новые внутренние
controlled refusal codes: UNSUPPORTED_ISOLATION/LIFECYCLE_FENCE_UNAVAILABLE.
Нового HTTP endpoint, compatibility baseline или profile routing нет.

## 5. Миграции и данные

Forward0025 `b86d2af275e0` от0024 `a75c0eb164d9`. После первого disposable apply
revision не редактировалась; SHA `e01361de68f4e734f64865f8da7ccb239d40605968998c90d4332b3ce5635a08`.
Добавлены function/trigger, без DML/backfill/новых таблиц/прав runtime. Previous
upgrade сохраняет populated profile/generation/control/terminal receipt/audit;
empty upgrade, one head/offline SQL, drift/grants/RLS проходят. Downgrade
намеренно отказывает, исправления forward. Main dev DB не мигрировалась.

## 6. Технические решения

[ADR138](../decisions/ADR-138-admission-lifecycle-fence.md): advisory fence вместо
FOR SHARE с расширением UPDATE privilege или definer function. Hash collision
может лишь сериализовать чужие профили. Новый epoch не нужен для данной гонки:
monotonic lifecycle и generation fence уже существуют. Future owner commands
должны брать fence перед control; обратный порядок способен вызвать deadlock,
который должен завершаться rollback/fail-closed, без automatic retry.

## 7. Найденные проблемы

RED воспроизвёл обе исходные гонки. Initial GREEN attempt выполнил29cases, затем
выявил fixture-only ошибку rollback внутри explicit psycopg transaction context:
завершение owner thread ожидало удерживаемый test lock. Отменены только запросы
своего disposable PG и собственный pytest (exit143); PASS этому прогону не
приписывается. Исправлено plain autocommit=False/manualrollback +10s threaded
owner SQL timeout, затем весь исправленный scoped набор повторён.

Review note о пустой history в upgrade test закрыт добавлением populated synthetic
receipt/audit под original runtime grants. Checks не ослаблялись; skips/xfail нет.

## 8. ECC и независимость

Root — автор/интегратор/runtime operator; python-testing и verification-loop
прочитаны как checklists. `admission_plan` — read-only planner/architect, затем
general/Python/database/pr-test review; `admission_normative` — source/baseline
reconnaissance; `lifecycle_security` — blind-first security/architect/silentfailure
review. Авторы и reviewers различны. Native Claude commands/hooks, product QA и
human approval не имитировались. [Протокол](../reviews/G02_ADMISSION_LIFECYCLE_REVIEWS.md).

## 9. Проверки

Среда: Darwin arm64, Python3.13.5, uv0.11.31, Docker29.2.0;
PostgreSQL16.15-bookworm по существующему Compose digest, реальные api/migrator
identities/Testcontainers. Все команды — проверенный HEAD +4final code hashes.
Временные logs/XML `/tmp/g156-lifecycle-*` не обязательны для продолжения;
постоянная сводка здесь. Поздняя test-only history delta вошла в final111run.

| Команда | Результат |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q backend/tests/integration/postgres/test_model_admission_lifecycle.py -k guard_first --tb=short --junitxml=/tmp/g156-lifecycle-red.xml` до fix | 2failed/4deselected/0errors/skips,4.62s,exit1: owner UPDATE не ждал |
| Тот же scoped pytest без `-k`, XML `/tmp/g156-lifecycle-final.xml` | 36passed/0failed/errors/skipped,15.55s,exit0 до history-only enhancement |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | 1419passed/4existing deprecation warnings/0failed/skipped,9.69spytest,exit0; Ruff0,mypy196files0issues,15importcontractsKEPT |
| Те же env + `make db-snapshot` | exit0,1intentional generation skip/3.82s; это генерация, не PASS drift |
| Final joint PG regression, точная команда ниже | 111passed/0failed/errors/skipped,1existing xid8 reflection warning,49.87s,exit0 |
| Те же offline env + `make -j1 contracts-check contracts-test` | 6/6validators,22passed/8.20s,exit0 |
| Scoped `backend/.venv/bin/ruff check` трёх Python files после final delta | exit0 |
| `infra/.venv/bin/python -B infra/scripts/scan_secrets.py` | 0findings,exit0 |
| `python3 -B docs/implementation/tools/check_prompts.py` | 40stage prompts/0issues,exit0; preparatory prompt отдельно source-reviewed |
| `git diff --check` | exit0 |

Final joint regression:

```sh
PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q \
  backend/tests/integration/postgres/test_model_admission_lifecycle.py \
  backend/tests/integration/postgres/test_model_admission.py \
  backend/tests/integration/postgres/test_model_admission_migration.py \
  backend/tests/integration/postgres/test_model_admission_restart.py \
  backend/tests/integration/postgres/test_observed_model_profiles.py \
  backend/tests/integration/postgres/test_model_registry.py \
  backend/tests/integration/postgres/test_schema_drift.py \
  backend/tests/integration/postgres/test_migrations.py \
  --tb=short --junitxml=/tmp/g156-lifecycle-regression.xml
```

## 10. Security / authorization

Owner-first begin/finalize refuse после commit revoke, guard-first owner ждёт
commit, изменения каждого lifecycle поля проверены. Timestamp/rollback/другой
профиль/таймаут/audit failure и transaction release; unsupported snapshots;
missing/disabled/replica/wrongfunction/partialcolumns/conditionaltrigger;
replica session; прежние pending/generation/drift/replay/restart/grants/RLS.
API не получает UPDATE/INSERT/trigger-management/function EXECUTE на профиль.
Нет definer escalation, реальных accounts/keys/approvals, provider calls/spend0.

## 11. Independent review

Два independent final source APPROVE/open0; оба сверили4hashes, actual DDL до
первого apply, final test enhancement и snapshot+20lines. Root runtime результаты
не приписываются reviewers. Точный протокол выше. CRITICAL/HIGH нет в scope.

## 12. Ограничения

Этот fence упорядочивает короткие DB UoW, не выдаёт ticket право внешнего вызова.
После begin и до dispatch revoke возможен; product composition/grant revalidation
ещё нужны. DB transaction не удерживается через provider I/O. Наступление
deprecated_at в wall-clock момент commit и защита от trusted DBA не гарантируются.
Реальный deadlock не инжектировался: safe SQLAlchemy failure path проверен actual
lock timeout; потенциальный порядок owner control→profile описан, не объявлен PASS.

Полный backend/pre-pr/Linux CI, global dependency audit/digests/SBOM и paid/human
acceptance не выполнялись в этом промежуточном срезе. Temporal/MinIO/SDK native
повторно не запускались: их код/контракты не менялись. До общей готовности/доставки
G156 эти gates сохраняются. Commit/push/PR/merge нет; исходный накопленный diff
не публикуется автоматически как авторство текущего узкого среза.

## 13. Документация

ADR138/prompt/index/report/review/hashes, HANDOFF/STATUS, G02 passport/Flash plan,
G156 gap, ADL, ECC и обе traceability обновлены. DECISIONS_PENDING/ROADMAP/canonical/
contracts не менялись: нового owner-решения, порядка этапов или wire scope нет.

## 14. DoD

G1/G2 fast PASS; G3/G6 actual scopedPG111PASS, empty/previous/drift/roles/RLS;
G4 unchanged surfaces/pinned validators22PASS; G5 scoped negatives/review,
global supply-chain pending; G7 independent APPROVE; G8/G9 документы/evidence.
Локальный lifecycle mechanism TESTED, полный G156 NOT VERIFIED.

## 15. Продолжение

Текущий технический срез завершён. Следующий разрешённый preparatory seam —
authenticated owner lifecycle/точное human evidence binding и observed gateway
integration, сохраняя disabled defaults. Затем общие final gates, tariff/original
account/safe key setup, live observations+отдельные human approvals, SLICE01 с
data/license/separatebudget. До S20 отдельно ADR129/G107. Всего остаются5крупных
блоков из handoff, этот срез закрывает часть первого, не весь блок. G02/S17/S20/S21
не стартуют без нового явного согласия после готовности всей подготовки.

Final scope/сохранность:142initial files →130byte-identical +12authorized scoped
edits/0missing,+7new files, всего19task files (4code/15docs+evidence).
Четыре final code hashes совпали.296local Markdown file links/0missing;
anchors/external URLs не проверялись. Все18initial Docker IDs/StartedAt unchanged,
new running containers0; это контроль запуска, не checksum основных stores.
Секретные значения/DSN/credential files в evidence не включались.
