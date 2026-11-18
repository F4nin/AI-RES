# G156 / ADR135 — Candidate Bifrost: SSE metadata patch

**Дата:**2026-11-18. **Статус:** TESTED локальный SDK/build/native-fixture срез; полный G156 IMPLEMENTATION NOT VERIFIED. Работа остановлена по просьбе владельца до следующей команды. Это продолжение [candidate preparation](G02_candidate_egress_preparation_REPORT.md), не S17/S20/S21 и не старт G02.

## 1. Реализованный и незавершённый scope

SDK patch сохраняет собственные raw id/model/fingerprint ABSENT/NULL/VALUE каждого JSON data frame до decode/suppression. Drift/missing/type/duplicate/malformed, включая скрытое A→B→A, запрещают success. Native exact DeepSeek Flash scope, request-local state, no fallback/retry/drain. Converter/hooks проверяются до wire; mixed response families не обходят Chat guard. Native serializer сохраняет presence и explicit-zero usage, legacy вне scope не меняется. Strict AI RES adapter/required VALUE не ослаблены.

Отдельные pinned build/provenance/headless image и patched-image fixture реализованы и локально проверены. Три MEDIUM build findings исправлены и закрыты general/security re-review; actual fresh scripted source acquisition PASS. Full candidate build+actual binary provenance PASS,278.63s; Actual joint native regression PASS:24patched+8official cases,32passed/0failed/skipped,27deselected,35.70s. Positive SSE VALUE/NULL/ABSENT и контролируемые отказы подтверждены; original official-image terminal loss negative сохранён. Real provider/host freshness/product wiring/human acceptance/SLICE/G02 не объявляются готовыми.

## 2. Источники и полномочия

Registry v4.1, DOC076 v1.1 §3.1/7, ADR128/131/134 и [ADR135](../decisions/ADR-135-bifrost-candidate-fingerprint-patch.md). IMPLEMENTATION_CHARTER §1/AGENTS §10 разрешают техническое исправление текущего стека в пределах подготовки. Canonical/mirror/baseline не меняются. Official Bifrost image/S16/main Compose сохранены; локальная candidate packaging не является deployment/релизом или model approval. Technical authorization остаётся одним исходным ≤10USD/≤8attempts, расход0.

## 3. Файлы и scope

`infra/llm_poc/bifrost_patch/`: `fingerprint.patch`, `README.md`, `Dockerfile`, `manifest.json`, `headless-index.html`, `build.py`. `backend/tests/integration/test_flash_candidate_bifrost_patch.py` — build/provenance regressions и будущие actual-image scenarios. Shared implementation docs/ADR/план/prompt/review ведёт root. Source SDK не vendor-ится: patch содержит три existing Go files и пять helpers/tests; upstream go.mod/go.sum не меняются.

## 4. API / contracts / events

Нет изменений публичных AI RES DTO/endpoints/events и product gateway/factory. SDK helper facts — opaque in-memory metadata, не approval. Candidate build manifest0.1 — WORKING tooling provenance, не product contract. Headless UI stub нужен только для upstream go:embed; API inference/auth сохраняется, UI acceptance не заявляется.

## 5. Миграции и данные

Нового DDL и изменений БД/real profiles/accounts/tariffs/секретов нет; applied0020–0024 не переписываются. PG/migration/RLS проверки неприменимы к этому узкому SDK/build diff; прежние и будущие G156 gates остаются. Основной stack/volumes не перезапускались и не удалялись.

## 6. Решения

ADR135: отдельная patched candidate сборка Bifrost2.5.1 на commit7cb75fb2f8276ca48d0792c857fecb67b8879e2f, без замены framework. Raw id/model добавлены в тот же observer: иначе suppressed metadata normalization скрывала бы drift от строгого adapter. Hook/converter integrity и Chat-only union обязательны; first-value fill запрещён. Source — verified Git sparse snapshot, не checksum полного codeload. Builder existing project Go1.27.4 digest, runtime official Bifrost digest; localcore/workspace/locks/binary provenance проверяются явно.

## 7. Исправленные несогласованности

Official-image negative terminal fingerprint loss сохранён; fake source возвращает постоянный fingerprint, а SDK synthetic terminal раньше терял его. Peer review выявил duplicate declarations (compile blocker), потерю raw tuple после converter/hooks и mixed-family serializer bypass. Они устранены в reviewed patch. Build findings named promisor для fresh sparse fetch, scrub inherited Git controls и actual binary hash comparison также исправлены; final general/security source review APPROVE/open0. LOW mocked command-order regression рекомендован дополнительно к actual fresh fetch.

## 8. ECC и независимость

`g02_prerequisite_plan` автор patch/tests и исполнитель Go runtime. `g02_python_contract_review` — независимый Go/code/test reviewer SDK, автор build/fixture; свой build не review-ит. `g02_scope_security_review` — отдельный read-only security/Go reviewer SDK/build. Root — architect/integration/docs и independent source inspection build. Прочитаны ECC go-reviewer/architect/security/test checklists, native Claude agents/hooks/slash commands не подключались. `.claude/skills/golang-testing/SKILL.md` отсутствует; компенсация — доступный go-reviewer, реальный behavioral TDD/race/vet и отдельные reviewers. Staticcheck не установлен; установка не выполнялась. [Протокол](../reviews/G02_BIFROST_PATCH_REVIEWS.md).

## 9. Команды и evidence

HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, ветка `feat/g02-manager-tools-planning`, рабочий diff; macOS host, Go1.27.4 linux/arm64 в pinned builder. Host Go1.26.3 несовместим с upstream go1.27.3 и для tests не использовался. GOTOOLCHAIN=local, GOFLAGS=-mod=readonly, GOMAXPROCS=2/-p1, task-owned cache, readonly source/locks. Exact reviewed SDK patch SHA256 **ec45313c57bb94c75fbec20725b5b41205159012ed131547ccadb4ba7355b025**.

| Проверка | Фактический результат |
|---|---|
| Behavioral RED: unchanged verified core + только новый public handler test, `go test ... -run TestFlashNativeStreamPreservesEveryPresenceAndZeroUsage` | exit1 ожидаем; parent +3presence subtests FAIL на реальном terminal fingerprint, не missing helper/compile |
| Targeted final Go normal, schemas/openai new metadata tests | exit0; **11parenttests+134subtests PASS**,0failed |
| Targeted final Go `-race`, те же cases/exact patch | exit0; **11+134 PASS**,0failed; без race warnings |
| `go vet` для `./schemas ./providers/openai` | exit0, empty log |
| Fresh source `git apply --check`;4upstream lock hashes before/after | exit0; unchanged reference/RED/GREEN |
| Go/code/test и separate security final SDK review | APPROVE/open0 по exact ec453… revision; source-only, не собственный запуск tests reviewers |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/integration/test_flash_candidate_bifrost_patch.py -k 'not actual_patched' --tb=short` (root cwd) | автор14passed/24deselected,0.12s; initial9/13pass исторические промежуточные, это отдельный pure слой |
| `backend/.venv/bin/python -B infra/llm_poc/bifrost_patch/build.py snapshot --output /tmp/g02-bifrost-buildtool-fresh-20261118-v1` | exit0; actual NEW init/promisor/lazycheckout под scrubbed env,1452files, SHA256becb11af…e54d9c exactexpected |
| Cold candidate build + actual artifact provenance | exit0,278.63s; image sha256:ab781fd7c8032ead0009e62b577c40e29503b73e47e84742f4dd1670a8a62615; actual binary SHA08a355456ba9947a1fe009587e2eb4525cf1b3a0158649d968adc9a1cd4f99b8; localcore/locks/noINTERP verified; [durable proof](../reviews/G02_BIFROST_BUILD_PROVENANCE.json) |
| `make pre-push-fast` (root, SDK/fixture source freeze) | exit0,Ruff0,mypy191files0issues,15importsKEPT;1281passed/4warnings,8.01s |
| `make infra-check infra-scan-secrets` (root) | exit0;RuffPASS,4Composecombinations0violations;secrets0 |
| General/security build source delta review | APPROVE/open0 на build.py SHA256 f75552059311308f70c7f2597eb6fed421fd3154661bfb9f79b09a14ea4eb7d0; actual image ещё не acceptance |
| `.venv/bin/python -B -m pytest -q tests/integration/test_flash_candidate_bifrost_patch.py tests/integration/test_flash_candidate_bifrost.py -k 'actual_patched or actual_bifrost or actual_pinned_bifrost' --tb=short` (backend cwd) | автор **32passed/0failed/skipped,27deselected,35.70s**;24patched+8official disjoint, не складывать с прежними overlapping runs |
| Verified Git sparse source snapshot |1452regularfiles; selected LICENSE/core/transports; deterministic USTAR37,386,240bytes SHA256 becb11aff118386888f4977c429e23f9e78ce1e9aaa5d2846d96671acee54d9c; commit/tree/blob inventory verified |

Temporary logs `/tmp/g02-bifrost-go-{red,final,race-final,vet-final}.log` не гарантируются следующей сессии; существенные counts/refs сохранены здесь. Ранний patch49bba… содержал duplicate declarations (source HIGH, исправлен до GREEN); bc096… и e9e… — промежуточные revisions. На e9e normal9parents+82subtests PASS; obsolete race остановлен exit143 намеренно перед изменением source, не PASS. Финальные11+134 относятся только ec453…. Source full codeload timeout/partial download не использован; exact Git sparse snapshot получен отдельно. Source fetch в новом fresh-CI tooling подтверждён отдельной успешной fresh acquisition после promisor fix.

### 9.1. Фактические команды Go runtime

```sh
docker run --rm --name g02-sdk-go-red-7cb75fb2 --cpus=2 --memory=3g --pids-limit=384 -e GOTOOLCHAIN=local -e GOMAXPROCS=2 -e GOFLAGS=-mod=readonly -e GOWORK=off -e GOCACHE=/task-cache/build -e GOMODCACHE=/task-cache/mod -e GOPATH=/task-cache/gopath -v /tmp/g02-bifrost-fingerprint-full-7cb75fb2-red:/source:ro -v /tmp/g02-bifrost-go-cache-7cb75fb2:/task-cache -w /source/core golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea go test -p 1 -json -count=1 -run '^TestFlashNativeStreamPreservesEveryPresenceAndZeroUsage$' ./providers/openai > /tmp/g02-bifrost-go-red.log 2>&1
docker run --rm --name g02-sdk-go-final-7cb75fb2 --cpus=2 --memory=3g --pids-limit=384 -e GOTOOLCHAIN=local -e GOMAXPROCS=2 -e GOFLAGS=-mod=readonly -e GOWORK=off -e GOCACHE=/task-cache/build -e GOMODCACHE=/task-cache/mod -e GOPATH=/task-cache/gopath -v /tmp/g02-bifrost-fingerprint-full-7cb75fb2-green:/source:ro -v /tmp/g02-bifrost-go-cache-7cb75fb2:/task-cache -w /source/core golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea go test -p 1 -json -count=1 -run '^Test(ChatStreamMetadata|Flash)' ./schemas ./providers/openai > /tmp/g02-bifrost-go-final.log 2>&1
docker run --rm --name g02-sdk-go-race-final-7cb75fb2 --cpus=2 --memory=3g --pids-limit=384 -e GOTOOLCHAIN=local -e GOMAXPROCS=2 -e GOFLAGS=-mod=readonly -e GOWORK=off -e GOCACHE=/task-cache/build -e GOMODCACHE=/task-cache/mod -e GOPATH=/task-cache/gopath -v /tmp/g02-bifrost-fingerprint-full-7cb75fb2-green:/source:ro -v /tmp/g02-bifrost-go-cache-7cb75fb2:/task-cache -w /source/core golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea go test -race -p 1 -json -count=1 -run '^Test(ChatStreamMetadata|Flash)' ./schemas ./providers/openai > /tmp/g02-bifrost-go-race-final.log 2>&1
docker run --rm --name g02-sdk-go-vet-7cb75fb2 --cpus=2 --memory=3g --pids-limit=384 -e GOTOOLCHAIN=local -e GOMAXPROCS=2 -e GOFLAGS=-mod=readonly -e GOWORK=off -e GOCACHE=/task-cache/build -e GOMODCACHE=/task-cache/mod -e GOPATH=/task-cache/gopath -v /tmp/g02-bifrost-fingerprint-full-7cb75fb2-green:/source:ro -v /tmp/g02-bifrost-go-cache-7cb75fb2:/task-cache -w /source/core golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea go vet -p 1 ./schemas ./providers/openai > /tmp/g02-bifrost-go-vet-final.log 2>&1
```

В Docker entrypoint не передавались реальные credentials/project data. Staticcheck availability проверена отдельным `docker run --rm --network none` того же pinned builder: Go1.27.4linux/arm64, staticcheck unavailable. Остановка только собственного obsolete race container: `docker stop --time 2 g02-sdk-go-race-7cb75fb2`, результат143 исторический. Основной dev stack не останавливался.

### 9.2. Фактический cold build (repo root, session61704)

```sh
backend/.venv/bin/python -B - <<'PY'
import json, runpy, time
from pathlib import Path
ns=runpy.run_path('infra/llm_poc/bifrost_patch/build.py')
started=time.monotonic()
try:
 image, proof=ns['build_image'](Path('/tmp/g02-bifrost-buildtool-fresh-20261118-v1/source.tar'))
except Exception as failure:
 print(json.dumps({'buildFailureType':type(failure).__name__,'elapsedSeconds':round(time.monotonic()-started,2)}))
 underlying=failure.__context__
 if underlying is not None and hasattr(underlying,'build_log'):
  for item in underlying.build_log:
   if 'error' in item:
    print(json.dumps({'publicSDKBuildError':str(item['error'])[:2000]}))
   elif 'stream' in item and any(term in item['stream'].lower() for term in ('error','cannot','undefined','failed','not found','updates to go','missing go.sum')):
    print(json.dumps({'publicSDKBuildDiagnostic':item['stream'][-2000:]}))
 raise SystemExit(1)
proof['elapsedSeconds']=round(time.monotonic()-started,2)
out=Path('/tmp/g02-bifrost-candidate-image-20261118-v1'); out.mkdir(exist_ok=True)
(out/'build-provenance.json').write_text(json.dumps(proof,sort_keys=True,indent=2)+'\n')
print(json.dumps(proof,sort_keys=True))
PY
```

Exit0,278.63s; build inputs frozen f7555205…/ec453…, no error/retry/lock edits. Temporary snapshot — checked fresh acquisition output. Для будущего cold rebuild без /tmp cache использовать штатный `build.py snapshot/build` по закреплённому manifest, а не считать временный каталог evidence.

## 10. Security cases

Raw tri-state/id/model every frame, suppressed finish/usage A→B→A, malformed/duplicate/Unicode/type/missing, converter mutation/drop/replacement, hook mutation/drop/skip/error rewrite/new fact, forged chat-shaped TextCompletion и все other response pointer families, safe constant errors/no fallback/no success terminal/upstream abandon, JSON+Sonic serializer, zero usage/legacy, request-local concurrent isolation. Эти SDK cases проверены Go runtime; actual native image/full pipeline прошёл отдельный32case fake-upstream suite.

## 11. Review

Два независимых final SDK APPROVE/open0. Build source получил отдельные general/security review,3MEDIUM CLOSED/open0; actual-image acceptance ему не присваивается. [Детали](../reviews/G02_BIFROST_PATCH_REVIEWS.md).

## 12. Ограничения

Candidate image собран, provenance и functional native suite проверены на linux/arm64 с искусственным провайдером. Нет нового full pre-pr/Linux CI, Git delivery, live provider evidence или человеческого approval. Supply-chain/vulnerability checks нового отдельного образа пока не выполнялись; source review не является такой проверкой. Headless candidate не считается official image/UI acceptance. Локальные Go tests не подтверждают реальные provider metadata/capabilities/стоимость. Modelcalls/spend0. Не менять Go locks/global toolchain, не публиковать образ, не перезапускать main stack ради этого среза.

## 13. Документация

ADR135/ADL/HANDOFF/STATUS/G02_WORK/план подготовки, текущий отчёт/review; normative и mirror без правок. После actual build дополняются evidence/ECC/traceability/gaps только фактическими результатами.

## 14. DoD

SDK implementation/behavioral RED→GREEN/race/vet/independent review — выполнены. Build pure-security fixes/re-review/fresh fetch — выполнены. Actual image build/provenance/24patched+8official native scenarios — выполнены; fixture general/security final source APPROVE/open0. Full pre-pr/Linux CI/live-provider/model approvals не выполнены, полного VERIFIED нет. Полный G156 IMPLEMENTATION NOT VERIFIED, подготовка IN_PROGRESS.

## 15. Следующий безопасный шаг

SDK/build/native tests текущего пункта завершены. По просьбе владельца остановиться; новую работу сегодня не начинать. При новой команде сначала восстановить full AGENTS/CONTEXT_RETENTION/HANDOFF/Git, затем ближайший unfinished G156 seam — concrete development host composition/gate для готового candidate runner. Весь временный runtime освобождён/cleaned, own caches оставлены; main stack не перезапускался. Cached images/source/tmp paths — удобство, не обязательная предпосылка: build.py умеет fresh fixed-source fetch и reproducible local build. Затем остаются concrete trusted host/freshness, product wiring/owner lifecycle, safe key/live/human acceptance/SLICE. G02/S17/S20/S21 NOT_STARTED до отдельного нового согласия владельца после реального завершения подготовки.

Fixture assertion delta source-approved: testSHA `4dbb9f8ad43b4bf4d4024895a980d9f209160b5a547d05563784c5edf29b5680`, helperSHA `69cd4234d824dcd2159ba5926df2d3b594ac215472148970c402153e804c0de4`, два read-only APPROVE/open0. WrongVK конкретный401/403/no dispatch; control outcomes требуют dispatchreach+actualcallback, lateKNOWN допускается; FP/model controlledSDK refusal boolean, id/duplicate/truncation stack refusal. После этого source checkpoint actual24patched+8official PASS,35.70s; runtime очищен и освобождён. Mainstack/API/officialtags не тронуты.

## Завершающий checkpoint по просьбе владельца

2026-11-18 (Москва): «Заканчивай сейчас свой текущий пункт, продолжим уже завтра ... задокументируй». SDK/build/native compatibility срез локально TESTED, не весь допуск модели. Ни одна следующая подготовительная реализация сегодня не начата. Следующий scope — concrete trusted host/freshness/key composition для candidate runner; product admission/owner lifecycle/wiring остаётся отдельным незавершённым блоком, не разрешено подделывать approval. Затем final security/supply-chain/pre-pr/Linux CI, live/human acceptance и SLICE-01. До S20 отдельно ADR129/G107. G02/S17/S20/S21 NOT_STARTED до нового согласия после завершения подготовки.

Scope9files зафиксирован [code/test/build hash manifest](../reviews/G02_BIFROST_PATCH_CODE_HASHES.json); source patch8Go files живёт внутри reviewed patch. Build proof сохранён в репозитории, не только /tmp. Ветка/HEAD прежние; все изменения в рабочем дереве, commit/push/PR/merge на этой подготовке не выполнялись. Исходные локальные NCP16/OD19/canonical/mirror changes сохранены; не включать их автоматически в будущий commit. Ни providers keys/realaccounts/tariffs/profile approvals, ни modelcalls не создавались; расход0USD. Дата следующей сессии не обнуляет исходный10USD authorization.

Финальная документальная проверка root:74canonical/73manifest hashes,0missing/mismatch;339реальных local Markdown file links,0missing;9SDK/build/test hashes,0mismatch. Первоначальный разовый link checker ошибочно принял Python `ns[...]()` внутри code fence за Markdown link; исправлен только ephemeral read-only checker (fenced code исключается согласно Markdown), repo gates/команды не менялись. Original40file checkpoint:30byte-identical+10authorized implementation doc edits,0missing; canonical/mirror/старые пользовательские отчёты byte-identical. `git diff --check` exit0; `make infra-scan-secrets` exit0/0findings. Новых tests/runtime после просьбы владельца остановиться не запускалось: только docs/сохранность/read-only checks и secret scan. Авторские source/runtime results выше сохранены до остановки.
