# G156 / ADR135 — SDK и build review

**2026-11-18**, branch `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff. [Отчёт](../increments/G02_bifrost_candidate_patch_REPORT.md), [ADR135](../decisions/ADR-135-bifrost-candidate-fingerprint-patch.md).

## Независимость

SDK автор `g02_prerequisite_plan`. `g02_python_contract_review` независимо read-only проверил SDK code/tests blind-first, не читая author README/report; он автор build/fixture, поэтому его SDK verdict их не покрывает. `g02_scope_security_review` — отдельный read-only security/Go reviewer обоих boundaries. Root source-inspects build и ведёт shared integration/docs. Native Go/Claude agents не подключались: ECC role instructions применены существующими отдельными агентами. Reviewer Go/tests/Docker не запускал; author runtime evidence отдельно в отчёте.

## SDK findings

| Finding | Severity | Evidence / fix | Статус |
|---|---|---|---|
| Duplicate guard/tracker declarations в initial patch | HIGH / compile blocker | Повторные `:=`/var в одном block удалены до Go GREEN | CLOSED |
| Hooks/converter после observation меняли id/model/FP или теряли private fact; overlay FP не сохранял всю raw tuple | MEDIUM | Expected opaque fact snapshot до hook; converter/wrapper validates base+fact, sticky refusal/handler exit, controlled error не rewrite/skip; JSON/Sonic negatives | CLOSED |
| Mixed TextCompletion+ChatResponse обходил wrapper: serializer выбирает Text первым, его choices поддерживает chat shape | MEDIUM | Exact Chat-only pointer union до/после hooks; guarded stream mixed union reject BEFORE dispatch; each-family/reflection TEST + forged chat-shapedText negative | CLOSED |
| Hidden id/model usage-only A→B→A coverage | LOW | Добавлены usage-only drift/missing/null и Sonic path | CLOSED |

**Final SDK verdict:** independent Go/code/test и dedicated security **APPROVE/open0** на patch SHA256 `ec45313c57bb94c75fbec20725b5b41205159012ed131547ccadb4ba7355b025`. Request-local facts, before-suppression observer, native exact scope, own-fact copies/tri-state/zero usage/legacy и mixed-family refusals source-reviewed. Author normal/race11parents+134sub PASS и vet exit0 указаны отдельно, не приписываются reviewers.

## Build/provenance: текущие findings

| Finding | Severity | Требуемое исправление | Статус |
|---|---|---|---|
| Fresh git fetch URL+filter не создаёт named promisor remote; sparse lazy blob fetch на чистом clone может не работать | MEDIUM | Fixed named origin/promisor или proper no-checkout partial clone; fresh acquisition evidence | CLOSED, delta re-review |
| `run()` наследует GIT_DIR/WORK_TREE/config/SSL/askpass controls; temp operations могут затронуть чужой repo/обойти fixed-origin | MEDIUM | Scrub inherited Git controls, rebuild explicit safe env; hostile env regression без обращения к main repo | CLOSED, delta re-review |
| Binary SHA берётся из sidecar, не сравнивается с actual `/app/main` bytes | MEDIUM | Bounded actual artifact hashing stopped container/noexec + compare и tamper negative | CLOSED, delta re-review |

Три build findings независимо подтверждены dedicated security reviewer и затем CLOSED после исправлений; binary evidence gap сначала нашёл root. Других concrete findings в готовых tar/path/mode/size/hash/lock/patch/immutable-image/headless files на этом проходе нет. Actual fresh scripted fetch успешно выполнен автором отдельно от review; на момент source verdict binary build/native image runtime ещё не выполнялись; затем author build и32nativecases PASS, см. final checkpoint ниже. Final general+security source verdict APPROVE/open0 на build.py SHA256 `f75552059311308f70c7f2597eb6fed421fd3154661bfb9f79b09a14ea4eb7d0`, manifest binding совпал; это source approval, не actual-image acceptance. Промежуточные pure9passed не закрывают эти findings. Full preparation/model/profile/SLICE/G02 acceptance не заявлены.

Build delta: named origin/promisor/filter задаются до fetch, inherited GIT_*/askpass controls очищены с safe config для nested fetch; actual binary хешируется bounded streaming из stopped/no-network container и сравнивается с sidecar. Pure hostile-env/tamper regressions source-reviewed, author13passed отдельно. LOW общего reviewer: добавить mocked command-order test fetch bootstrap (actual fresh fetch уже проверен). Final SDK ec453… остаётся frozen.

## Actual patched fixture — source checkpoint

General test-analysis и dedicated security read-only source review initial fixture SHA `b20ce74b22b1089daeb415099def0201d3bacd4849fbd7cf3562c3f7372b43f0`, helper `06f40f9efec0d997651eac122b9ed9a5e850ccd673ae0af1f0a9433771393536`: один MEDIUM negative evidence gap. WrongVK должен доказывать exact401/403/no claim/no send; cancel/timeout — exactdigest claim/send/canonical receive1 и наблюдаемый settlement послеdrain, иначе setup delay/500 могли пройти. Known late settlement допустим, не форсироватьUNKNOWN. Hidden FP/model SDK refusal желательно атрибутировать controlled error boolean; relay id/duplicate/truncation refusal — stack evidence, Go tests отдельно доказывают SDK observer. Других concrete findings в internalnetwork/noports/MockTransport/FakeControl/ro mounts/cleanup/safe diagnostics нет. На этом первоначальном checkpoint исправления/source delta и actual24cases были pending; затем оба source review и actual runtime завершены, см. final checkpoint ниже.

Fixture delta final source verdict: general и dedicated security APPROVE/open0 по test4dbb9f8…/helper69cd423… . MEDIUM auth/non-dispatch outcome gaps CLOSED: exact401/403/no provider reach; exactdigest claim/canonical receive/outgoing1 + one actualcallback; controlledSDK refusal boolean дляFP/model, честная stack attribution. Runtime не запускался reviewers. Авторский cold image build+actualbinary provenance PASS278.63s отдельно; затем actual24patched+8official cases PASS32/0failed/skipped,27deselected,35.70s.

Final runtime evidence принадлежит автору build/fixture:14purePASS/24deselected и32nativePASS/27deselected, не запуск reviewers. Official negative сохранён. Runtime cleanup/release подтверждены; no main/API/officialtag changes. Current scoped source findings0; полный G156/live/security-owner acceptance и Linux CI не заявлены. Работа остановлена по просьбе владельца, новый scope не начат.
