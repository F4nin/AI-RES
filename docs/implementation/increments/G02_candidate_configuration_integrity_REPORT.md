# G156 — Candidate configuration integrity: Increment Report

**Дата:**2026-11-18. **Промпт:** [scope](prompts/G02_candidate_configuration_integrity.md). **Результат:** механизм ADR137 локально TESTED; полный G156/pre-pr/LinuxCI/live/human acceptance NOT VERIFIED. Подготовка IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED.

**Граница завершения:** после документирования остановиться по прямой команде владельца. Следующие подготовительные этапы — только после новой задачи; контекст для продолжения сохранён.

## 1. Что реализовано

Отдельный hardened candidate поверх того же pinned Bifrost2.5.1/SDK fingerprint patch. До загрузки config требуется свежий `/app/data` с единственным bounded regular0600 config, exact compiled template/catalogues и3mounted64hex credentials. Существующее SQLite/governance auth сохранено. Launcher очищает inherited environment и не удаляет старое состояние.

Внешний compile-time HTTP guard разрешает только exact raw URI/method `GET /health` и `POST /v1/chat/completions`, до CORS/base-path/router. Admin/UI/alternative paths закрыты даже с admin credentials. Перед разрешённым запросом проверяются mounted/rendered/marker bytes, live Client/Providers/Framework и readonly consistent logical SQLite snapshot всех schema objects/tables/visible columns/rows. Storage classes и bytes сохраняются; WAL учитывается; rows/schema/size/time bounds обязательны. **Bookkeeping exceptions нет.** Обнаруженный drift/read failure защёлкивает отказ после восстановления данных.

Host0.2 требует exact reviewed namespace proof, image/source/runtime и StartedAt/Pid/RestartCount; действующий guarded health проверяется под `env -i`. Gate встроен до reserve/probe/onceclaim; settlement после отзыва сохраняется. Old descriptor0.1/missing marker/unknown image/mount mismatch не принимаются автоматически. Это наблюдение в доверенном dev host, не human/model approval.

## 2. Нормативная база и Registry

AGENTS/CONTEXT_RETENTION, CLAUDE, Registry v4.1 и canonical DOC076 v1.1§3.1/5/7, DOC015 v1.7§8/9, security/threat/secrets baseline, существующие charter/roadmap/quality/test rules; ADR134–136 и native audit. Новое техническое решение — [ADR137](../decisions/ADR-137-candidate-configuration-integrity.md). Canonical документы, MVP, публичные permissions, baseline manifest и зеркала не менялись. Registry/manifest presence/hashes проверены при closeout, результаты ниже.

Исходники и dependencies: exact public commit `7cb75fb2f8276ca48d0792c857fecb67b8879e2f`, verified sparse selection и unchanged Go locks из ADR135. Дополнительных библиотек/framework/MCP/global configuration нет. Locked Go dependencies восстановлены в task/local cache; project code/данные не отправлялись во внешние doc/model services.

## 3. Файлы и сохранность

Ветка `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + working diff. До начала125изменённых/new files, включая прежний owner NCP16/OD19/canonical/SDK/persistence/host diff. Baseline byte hashes сохранены до правок. Исходный unrelated diff не присваивается этому срезу и не публикуется автоматически.

| Scope | Файлы |
|---|---|
| Новый hardened build | `infra/llm_poc/bifrost_integrity/{integrity.patch,build.py,manifest.json,Dockerfile,start-candidate.sh,README.md}` |
| Host/source binding | `backend/src/ai_res/modules/model_registry/{candidate_host.py,candidate_integrity.py}`, `cli/flash_candidate.py` |
| Unit tests | `test_candidate_host.py`, `test_candidate_integrity.py`, `test_flash_candidate_cli.py` |
| Native tests/helpers | `test_bifrost_candidate_integrity.py`, `fixtures/{bifrost_integrity_probe.py,candidate_sqlite_mutation.go,flash_candidate_fake_relay.py}` |
| Evidence/context | Этот report, prompt/ADR137/review/hash/build proof, HANDOFF/STATUS/groups/gap/traceability/ECC/ADL/index |

Проверенные [15code hashes](../reviews/G02_CONFIGURATION_INTEGRITY_CODE_HASHES.json) отделены от документации. Original fingerprint.patch/build/manifest, official/main image tags, основной Compose, frozen0020–24/schema snapshot и прежние report/hash artifacts сохранены.

## 4. API / контракты / события

Public AI RES API/events/schema mirrors/private control wire не менялись. Local protected host descriptor —0.2 с обязательным `expectedIntegritySha256`; старый0.1 отказывает. Новый file marker protocol0.1: ровно version/bootNonce/configSha256,0600, без trailing newline/credential values. Несовместимость private development descriptor принята в ADR137; public compatibility baseline не принимался/не заменялся.

Management APIs закрыты только в новом opt-in candidate binary. Прежний Bifrost/SDK/mutable audit сохранён для regression; продуктовая конфигурация не заменялась.

## 5. Миграции и данные

Новых Alembic revisions/DDL/grants/domain seeds нет; applied0020–24 не редактировались. Основные PostgreSQL/Temporal/MinIO данные не использовались и не мигрировались. Новые SQLite находятся в собственных tmpfs тестовых контейнеров; logical snapshot не является доказательством PostgreSQL semantics. Реальные accounts/tariffs/profiles/keys/approvals не создавались.

## 6. Технические решения

ADR137: свежая initial state + hard HTTP deny + sticky file/live/logical DB invariant вместо неполных redacted admin GET snapshots или отключения ConfigStore. Snapshot включает все таблицы/schema и duplicate multiplicity, не physical DB bytes/implicit rowid. Снимок выполняется в readonly transaction, завершённой до HTTP/provider execution. Expected bindings не переучиваются после drift/restart. Settlement отдельно от freshness guard.

Фиксированные bounds — технические ограничения парсинга/ресурсов локального candidate, не product SLO/retention/capacity. Test-only dormant retention/exec/proxy и fault injection не переносятся в product configuration.

## 7. Найденные проблемы и исправления

| Находка | Исправление |
|---|---|
| Go SQLite JSON encoding смешивал INTEGER/REAL и TEXT/BLOB, мог терять invalidUTF8/declared BOOL/DATETIME raw values | Typed framing: typeof + SQL CASE/CAST, INTEGER int64, REAL IEEEbits, TEXT/BLOB hex; raw schema metadata lossless.6collision+duplicate tests |
| Sticky test восстанавливал только rendered file | Все8dependencies реально восстанавливаются; `guard.check()==nil` перед проверкой продолжающегося503 |
| Namespace wget наследовал proxy env, мог увидеть ложный200 при guard503 | Весь Docker observation выполняется под fixed `env -i`; unit argv и native lying-proxy positive control |
| OCI image omits empty Cmd | Provenance `.get("Cmd")` принимает только omitted/null/[], exact baked entrypoint по-прежнему обязателен |
| Native rendered restoration наследовал намеренно вредный APP_DIR | Test-only restore переведён на тот же clean env, затем проверены правильное восстановление и sticky refusal |

Секретные ошибки/DB/raw provider content не экспортируются. Проверки не отключались, skip/xfail/exceptions в DB snapshot не добавлялись.

## 8. ECC / независимость

`config_integrity_plan`: отдельные planner/architect/source analysis, затем ограниченное авторство только integrity.patch/Go tests в temp source. Он не reviewer своего кода и не запускал runtime. Root — build/launcher/Python/fixtures/integration/docs/runtime owner, явно прочитанные python-testing/verification-loop как checklists.

`bifrost_audit_review`: blind-first read-only general/Go/Python/test review; `bifrost_isolation_security`: независимое security/Go/architect/silent-failure review. Первые выводы до авторского отчёта; source-only verdicts APPROVE/open0 после исправлений и final15hash check. Native execution/root checks не приписываются reviewers. Go-reviewer применён через прочитанные инструкции и отдельную роль, не фиктивную Claude команду. Hooks/native slash commands/product QA/human approval не запускались/не имитировались. [Review protocol](../reviews/G02_CONFIGURATION_INTEGRITY_REVIEWS.md).

## 9. Проверки / evidence

Среда: macOS26.6.2 arm64/Python3.13.5, Docker29.2.0; builder Go1.27.4 по digest. Все результаты — HEAD выше +15current code hashes. Установленные lock-based Python environments, final fast без sync/network. Logs/XML в `/tmp/g156-integrity-*` — временные; обязательная сводка здесь и в постоянных artifacts.

| Команда / профиль | Результат |
|---|---|
| Pinned builder: `go test -p 2 -count=1 -v ./bifrost-http/server -run '^TestCandidate'` |8parent+42sub PASS,0failed/skipped,0.105s,exit0 |
| Тот же builder: `go test -p 2 -race -count=1 -v ./bifrost-http/server -run '^TestCandidate'` |8parent+42sub PASS,0race reports,1.262s,exit0 |
| `go vet -p 2 ./bifrost-http/server` |exit0; staticcheck не запускался (host `command -v staticcheck` exit1), компенсация vet/race/independent Go review |
| `backend/.venv/bin/python -B infra/llm_poc/bifrost_integrity/build.py --snapshot /tmp/g02-bifrost-verified-sparse-7cb75fb2.tar` |Build/provenance PASS; actual binary и baked launcher/manifest проверены; old SDK inputs/locks не менялись |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_candidate_host.py backend/tests/unit/test_candidate_integrity.py backend/tests/unit/test_candidate_composition.py backend/tests/unit/test_flash_candidate_cli.py --tb=short` |165passed,0failed/skipped,0.89s,exit0 до последнего argv assertion; последний unit delta включён final fast |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` |Final1419passed/4existing deprecation warnings,0failed/skipped,10.56spytest,exit0; Ruff0,mypy195sourcefiles0issues,15importcontractsKEPT |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/integration/test_bifrost_candidate_integrity.py -k two_real --tb=short -x` |Smoke1passed/11deselected,47.48s,exit0;2successful fake SSE+posthealth и10.2s window. Deselected не является full suite evidence |
| Joint `pytest -q` нового native file + `test_bifrost_effective_isolation.py test_flash_candidate_bifrost.py test_flash_candidate_bifrost_patch.py --tb=short --junitxml=/tmp/g156-integrity-native-joint.xml` |76passed/1test-fixture failure,154.50s,exit1. **Все65legacy cases прошли**:6mutable audit+21official/fixture+38SDK-patched/pure. Новый rendered restore fix ниже |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/integration/test_bifrost_candidate_integrity.py --tb=short --junitxml=/tmp/g156-integrity-native-final.xml` |Final12passed,0failed/errors/skipped,104.20s,exit0 после test-only clean-env restore fix |

Итоговое уникальное покрытие relevant77cases:12new final +65unchanged legacy из joint run. **Не утверждается единый прогон77PASS:** initial joint имел1failure, после исправления повторены только затронутые12. Legacy source/helper с момента их PASS не менялись.

Go tests выполнялись в isolated pinned builder с nonroot current UID/GID, read-only source, cap-dropALL/no-new-privileges, pids512/memory3g, GOTOOLCHAIN=local/GOFLAGS=-mod=readonly/CGO_ENABLED=1/GOMAXPROCS=2. GOMODCACHE task/local, GOCACHE task-local; generated go.work/sum — в writable task dir, не в source/locks. После восстановления packages race/vet выполнялись с `--network none`. Первые3environment attempts не PASS: readonly go.work.sum, GOPATH sumdb path и noexec tmpfs. Исправлена только временная test environment, source/checks не ослаблялись. Затронутые upstream locks проверены неизменными.

Build image `sha256:183fc5ac5b1c5b73ea31ae93a24de0cee7c344e1622a92a6233680d49d76681b`, actual binary `d280f39e88a38711bffd6dfacf96118a1464161ca2d846fdc1f416d861f4ab73`, ELF interpreter отсутствует. [Build proof](../reviews/G02_CONFIGURATION_INTEGRITY_BUILD_PROVENANCE.json). Первоначальный cold build скомпилировал binary, но final proof отказал по omitted Cmd; после validator fix image собран с cache reuse и actual proof PASS. Повторный cold SDK build не заявляется.

Final closeout checks, все применимые команды exit0:

- `infra/.venv/bin/python -B infra/scripts/scan_secrets.py`:0findings.
- `python3 -B docs/implementation/tools/check_prompts.py`:40stage prompts/0issues. Новый preparatory prompt дополнительно рассмотрен independent docs review.
- Inline read-only `python3 -B` Registry/manifest checker:74canonical paths/0missing/0duplicates;73manifest hashes/0mismatch.15current code hashes совпадают; buildManifestSha256/integrityPatchSha256 совпадают с текущими files.
- Local Markdown link checker:282file links в15task docs/0missing. Anchors/external URLs не проверялись.
- Baseline SHA check:125initial files →110byte-identical+15authorized scoped edits/0missing,17new files. Total32task files:15code и17documentation/evidence; среди прежних125изменены только5code и10implementation docs. Existing canonical/contracts/frozen/SDK hashes сохранены.
- `git diff --check`:exit0. Final read-only Docker inspection: все18initial container IDs/StartedAt unchanged, other running containers0. Это контроль запуска, не data checksum всех main-stack stores.
- Ветка/HEAD повторно проверены, остаются указанными выше; commit/push/PR/merge/newCI не выполнялись. После финальной test-only restore строки выполнен scoped Ruff; Go/production code и15hashes неизменны.

## 10. Security / authorization

45actual admin/UI/alternative URI/method combinations с anonymous/admin/VK отказывают; wrong/missing/direct-key inference отказывают при сохранённом positive SSE. Fresh/reused DB/bootstrap, hardlink/symlink/missing/malformed/oversize inputs, marker bytes, SQLite corruption/schema/data/type-collisions/WAL, live config, sticky-after-restore и resource bounds проверены Go tests. Native cases проверяют file/marker/mounted mutation, **actual os.replace**, direct valid SQL client/schema mutation, restart sameCID, claim refusal/settlement after revoke, proxy200-vs-guard503,2successfulSSE+health и configured10s governance ticker window. Выполнение всех возможных фоновых jobs не утверждается.

Стэнд — только own internal network/noports/read-only nonroot containers. Provider — настоящий relay/codec с synthetic MockTransport upstream и test-double accounting; **реальных provider calls0/spend0**, durable paid ledger/control auth этим не проверены заново. Test-only closed SQLite fault injector собран отдельно по existing locks, помещён trusted test host в `/tmp` с `exec`; в candidate image/main Compose/real descriptor его нет. Main18container IDs/StartedAt сохранялись каждым fixture и сверяются при closeout. Known synthetic credential values отсутствуют в tested logs/env; это не доказательство всех возможных telemetry leaks.

## 11. Независимое review

Два separate reviewers, final source verdicts APPROVE/open0,15hashes/0mismatch. MEDIUM typed SQLite и proxy health spoof, LOW sticky-test evidence исправлены; CRITICAL/HIGH нет в reviewed scope. Последние tiny deltas Cmd omission/test restore повторно APPROVE. Reviewers не запускали Docker/Go/tests и не дают human/security-owner approval. Final documentation review выполняется после первичных blind-first выводов.

## 12. Не выполнено / ограничения

Полный backend/pre-pr/LinuxCI/security advisory/audit/digest/SBOM всего накопленного diff не выполнялись этим checkpoint; до VERIFIED/доставки сохраняются. Проверки PostgreSQL/Temporal/RLS/migrations не повторялись: код/DDL этих областей не менялся. Historical CI не переносится на current diff. Runtime target — только local candidate Linux/arm64 внутри Docker на Mac, не production acceptance/новая OS matrix.

Logical snapshot — all configured schema/visible data, не physical pages/implicit rowid/все внутренние caches. Он не предотвращает необнаруженное A→B→A между проверками, RCE или компрометацию trusted Docker host. Check→claim/provider window не объявляется атомарным. HTTP route denial предотвращает прежнюю admin mutation, sticky наблюдения блокируют замеченный drift; это не общая sandbox/SSRF гарантия. Internal/noports/canary checks имеют указанные границы. Hashes/marker не утверждают модель/профиль/тариф.

## 13. Документация

ADR137, prompt/index/README/report/review/hash/proof, HANDOFF/STATUS, G02 passport/Flash plan, G156 gap, ADL, ECC and requirements/contract traceability обновлены. Canonical/contracts/ROADMAP/DECISIONS_PENDING не менялись: нового owner/business решения не появилось. Старые результаты сохранены как история с точной границей новой реализации.

## 14. DoD

G1/G2 PASS fast/Go/unit; G3 PASS scoped native Docker/SQLite/relay, не real provider; G4 public/wire unchanged, private0.2/marker grammar validated; G5 scoped negative suites/proxy/secret review PASS, global supply-chain gate pending; G6 N/A no migration; G7 independent source APPROVE; G8/G9 docs/evidence/checkpoint. **Технический configuration integrity срез локально TESTED. Full G156 NOT VERIFIED, G02 NOT_STARTED.**

## 15. Остановка и продолжение

По последней команде владельца закончить документирование, сообщить и остановиться до обновления контекста/новой задачи. Следующие preparatory seams: product observed-admission/owner lifecycle/wiring, общие final regression/pre-pr/LinuxCI, reviewed tariff/original account/safe key setup, real technical observations + отдельные human Bifrost/profile approvals, SLICE01 с собственными data/license/budget gates. До S20 отдельно ADR129/G107. G02/S17/S20/S21 без нового явного согласия после завершения подготовки не запускать.
