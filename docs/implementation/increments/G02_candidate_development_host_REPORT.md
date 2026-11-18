# G156 / ADR136 — Candidate development host: Increment Report

**2026-11-18 · Итог: локально TESTED для host gate/composition; полная подготовка IN_PROGRESS / IMPLEMENTATION NOT VERIFIED.** [Промпт](prompts/G02_candidate_development_host.md), [ADR136](../decisions/ADR-136-candidate-development-host.md), [review](../reviews/G02_DEVELOPMENT_HOST_REVIEWS.md), [точные10code hashes](../reviews/G02_DEVELOPMENT_HOST_CODE_HASHES.json).

## 1. Что реализовано

Concrete protected host config, immutable manifest/source/config/plan/tariff/runtime bindings, fresh fixed official pricing HTTPS observer без TTL/cache/retry/redirect/environment proxy, bounded readonly Docker inspector. Сравниваются фактический immutable container/image, безопасные launch options и точные reviewed mount mappings/hashes текущих host-source files; повторная local validation после внешних await. Config/tariff не генерируются и не утверждаются автоматически.

Trusted local/test source-checkout composition собирает существующие ledger/accounting/probe/runner/control. Original account/authorization/rates/route/bounds сверяются read-only под API role. Claim повторяет host+DB preflight перед existing onceclaim. Settlement остаётся доступным после revoke/outage. AsyncExitStack закрывает HTTP clients/engine/probe при ошибках/cancel; standalone env-only HTTPS listener accounting-only с lifespan cleanup. Base CLI default DRY_RUN, execute без отдельной factory HOST_UNCONFIGURED.

## 2. Нормативная база и Registry

AGENTS§7/10, CONTEXT_RETENTION, CHARTER, ROADMAP/STATUS/HANDOFF, Registry4.1; Spec1.22/1.22.1, DOC076v1.1§3.1/5/7, canonical security/IAM/secrets/persistence и ADR128/131–135. Registry74canonical paths присутствуют; hashes сверяются отдельно final checks. Новых нормативных решений/параметров/permissions нет. Внешние источники реальных тарифов этим offline срезом не запрашивались: observer проверен на explicit doubles.

## 3. Файлы и исходное состояние

Ветка `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`. До работы108изменённых/new files сохранены; существующий canonical/NCP16/OD19/ledger/SDK diff не присваивается новому срезу. Commit/push/PR/newCI не выполнялись: подготовка как целое ещё не прошла общие gates; чужие исходные изменения автоматически не публикуются.

| Файлы | Изменение |
|---|---|
| `backend/src/ai_res/modules/model_registry/candidate_host.py` | Новый strict config/tariff, concrete observers/gate/claim wrapper |
| `backend/src/ai_res/modules/model_registry/candidate_host_account.py` | Новый read-only exact account preflight |
| `backend/src/ai_res/cli/candidate_composition.py` | Новые explicit runner/control async contexts; no app→CLI import |
| `backend/src/ai_res/cli/flash_candidate.py` | Patch/build input hashing и защищённое Git provenance |
| `backend/src/ai_res/api/serve_candidate.py` | Accounting-only standalone listener, lifespan engine cleanup |
| `backend/tests/unit/test_candidate_host.py`, `test_candidate_composition.py` | Новые behavioral/negative tests |
| `backend/tests/unit/test_flash_candidate_cli.py`, `test_serve_candidate.py` | Delta source/env/standalone tests |
| `backend/tests/integration/postgres/test_candidate_host_account.py` |8новых real PG cases |
| Implementation docs | ADR/prompt/report/review/hashes, context/status/plan/gap/traceability/ECC |

## 4. API / контракты / события

Public/product API/events/JSON schemas не менялись. Новый local closed host config0.1 и tariff descriptor0.1 — технические входы, не public contract/profile approval. Private standalone control wire прежний, но activated env factory теперь всегда отказывает claim: guarded service доступен только отдельной trusted composition. Settlement semantics сохраняются. Existing low-level control unit/TLS fixtures используют explicit service injection, не доказывают runnable live host.

## 5. Миграции и данные

Новых revisions/DDL/grants нет; applied0020–24 и snapshot не менялись. Новая query только SELECT с exact account/RLS/UoW; никаких production/account/profile/tariff seeds. Тесты мигрировали одноразовый PG16 штатной fixture; original main stack/data/secrets не менялись. Existing pending reserve после reader остаётся неизменным.

## 6. Самостоятельные решения

[ADR136](../decisions/ADR-136-candidate-development-host.md): fresh exact-document gate вместо TTL/парсинга автоматически принятых цен; strict current-checkout/local-test host; explicit Docker endpoint; claim gate отдельно от settlement. Original≤10USD/≤8attempt authorization2026-11-17 сохраняется при restart/новой дате. Второго account/budget не создаётся.

## 7. Несогласованности

Source hash прежде не включал candidate SDK/build inputs; RED5fail→GREEN5pass. Env toggle мог открыть ungated claim; теперь standalone accounting-only. Остальные исправленные findings — review. Canonical/NCP не переписывались.

## 8. ECC

`host_plan`: отдельные planner/architect instructions, затем ограниченное авторство host module/tests, прочитанные Python patterns/testing/TDD. Root: composition/integration/test/doc-updater checklists. `host_python_review`: независимые general/Python/database/pr-test-analyzer; `host_security`: независимые security/architect/silent-failure. Blind-first и scope зафиксированы в review; авторы не reviewers себя. Native Claude commands/hooks не запускались. Отсутствующий live runtime evidence не компенсируется self-review.

## 9. Тесты и команды

Среда: Darwin25.6.0 arm64, Python3.13.5, uv0.11.31, Ruff0.17.4; installed lock-based environments, sync/network disabled для fast. HEAD выше; artifact содержит final10file hashes, документация исключена. Fast/PG/affected142 выполнены до последней test-only scanner fixture правки, описанной ниже; production5source hashes с момента этих прогонов не менялись.

| Проверка/команда из корня | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_flash_candidate_cli.py -k candidate_build_inputs --tb=short` | RED5failed; после fix GREEN5passed/29deselected,exit0 |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_candidate_composition.py --tb=short` | RED missing module exit2; final в affected/fast ниже |
| Author `cd backend && .venv/bin/python -B -m pytest -q tests/unit/test_candidate_host.py` |77passed,0failed/skipped,0.33s; scopedRuff/mypy1file0,exit0 |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` |exit0: Ruff0,mypy194sourcefiles0issues,15importcontractsKEPT;1389passed/4deprecationwarnings,0failed/skipped,10.66spytest. Лог `/private/tmp/g156-host-fast.log` временный; этот отчёт — постоянная сводка |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/integration/postgres/test_candidate_host_account.py backend/tests/integration/postgres/test_candidate_runner.py --tb=short` |exit0,22passed/0failed/skipped,9.62s;8new+14runner, realPG16 Testcontainers, synthetic transport double |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_flash_candidate_cli.py backend/tests/unit/test_candidate_composition.py backend/tests/unit/test_serve_candidate.py backend/tests/unit/test_candidate_host.py --tb=short` |final после test-only hooks/signing fix:142passed/0failed/skipped,0.75s,exit0; affectedRuff0 |

Первый sandbox PG вызов:8setup errors, Docker socket EPERM; штатно повторён с escalation, без обхода sandbox. Первый realPG run1passed/7failed из-за отсутствующего explicit begin в новом тесте; исправлено и повторён вместе с runner22PASS. Fast первый запуск остановлен uv cache sandbox, повтор разрешён; следующий lint выявил2bare Git paths в fixture, исправлено. Отдельный new standalone test сначала29pass/1fail (неверная kw-only test identity), исправлен. Эти попытки не скрываются и не считаются PASS.

После fast/affected142 штатный secret scan выявил1false-positive literal assignment в новом synthetic unsafe-env test. Длинное fake значение заменено коротким fixture и соответствующий no-echo assertion обновлён. Scanner/allowlist/production code не менялись. Final test_candidate_host.py SHA256 `bfd9a5612e82feee7107d5c91bc6c24c832bcf8d0b2033a409d0c380f8ded873`; после этих2строк повторно host77passed/0failed/skipped,0.44s и Ruff10files exit0. Security delta APPROVE/open0; повтор всего fast после этой fixture-only правки не заявляется.

## 10. Security / authorization

Strict unknown/version/auth/account/path/manifest inputs; unsafe/symlink/ancestor/hardlink/FIFO/permissions/bounds; missing/changed tariffs, redirect/HTTP errors, bounded/chunked timeout/cancel; root/privilege/hostports/mount/runtime drift; final source recheck; Git redirect refusal; production/privileged host refusal; wrong provider/virtual secret shape without echo; gate→account→onceclaim, settlement после revoke; realPG exact account/plan/tariff/rates, default-deny/reset, zero writes/pending preserved; resource close construction/error/cancel. Existing product/session/IDOR/Worker/Temporal behavior не изменялось и не объявляется проверенным заново этим targeted run.

## 11. Независимое review

[Протокол](../reviews/G02_DEVELOPMENT_HOST_REVIEWS.md): два отдельных reviewers APPROVE/open0 после исправлений; actual runtime только root/author, не reviewers. Security-owner/human acceptance этим не заменена.

## 12. Невыполненное и ограничения

Фактические Docker/HTTPS host topology и live provider не запускались. Inspect связывает launch/mount mappings и hashes текущих host files; bytes внутри уже смонтированного inode после atomic replace не проверяются. Также не проверен mutable rendered `/app/data`/SQLite state/admin changes; это обязательный следующий runtime/config seam до key. Нужен свежий процесс после code edits; hot-reload provenance не гарантируется. Operator-reviewed official snapshot/rates/real account/keys отсутствуют; hash не доказывает их approval. Trusted host composition — explicit context, не готовый deploy/автозапуск. No paid model calls, spend0; фактический provider balance не измерялся.

Полный backend/pre-pr/LinuxCI/dependency audit/digests/SBOM нового объединённого diff ещё не выполнялись: это промежуточный preparatory checkpoint, не VERIFIED/delivery. SDK build/native suite не повторялись без причины, hashes прежнего checkpoint сохраняются. Owner lifecycle/product observed wiring, final security/regression gates, safe SOPS/age→Compose secret setup, live exactvalues/Bifrost/profile human acceptance и SLICE01(data/license/separatebudget) не завершены. До S20 отдельно ADR129/G107.

## 13. Документация

Обновлены implementation ADR136, prompt/index, report/review/hash artifact, HANDOFF/STATUS/G02 passport/plan/G156 gap/ECC/requirements+contract traceability. ROADMAP/Sxx dependencies/owner decisions/canonical/contracts не меняются. До старта G02 требуется новое явное согласие после уведомления о завершении всей подготовки.

## 14. DoD и gates

G1/G2 PASS fast; G3 PASS только scoped PG/query, observers на explicit doubles; G4 public/wire schemas unchanged, relevant contract subset включён fast; G5 negative source/targeted cases и independent review PASS, общий supplychain gate pending; G6 N/A new migration, existing fixture upgrade использован без нового migration evidence; G7 APPROVE/open0; G8/G9 checkpoint docs/evidence. Никакого VERIFIED G156/runtime/profile или готовности всей подготовки.

## 15. Следующий безопасный шаг

Продолжить только подготовку: exact isolated launch/effective config integrity (включая mutable SQLite/admin settings и topology), затем product observed admission/owner lifecycle/wiring и final gates. Реальные account/tariff/key setup — после конкретного reviewable плана и закрытых предпосылок; значение ключа в чате не спрашивать. Реальные metadata/Bifrost/profile требуют отдельной человеческой приёмки. SLICE01 имеет отдельные данные/лицензию/бюджет. G02/S17/S20/S21 NOT_STARTED; готовность всей подготовки ещё не объявлена.

## 16. Финальные deterministic checks и сохранность

`infra/.venv/bin/python -B infra/scripts/scan_secrets.py` — exit0,0findings после описанного false-positive; `infra/.venv/bin/python -B docs/implementation/tools/check_prompts.py` — exit0,40prompts/0issues; `git diff --check` — exit0. Python SHA256/relative-link inspection:74canonical paths present,73manifest hashes/0mismatch,10final host files/0mismatch,9prior SDK/build files/0mismatch;366local Markdown file links/0missing (code fences excluded, anchors не проверялись). Initial108files:94byte-identical+14authorized edits/0unexpected/0missing; все frozen migrations/canonical/SDK bytes сохранены. Временный initial hash snapshot не нужен для продолжения: finalscope закреплён persistent10file artifact и этим отчётом.
