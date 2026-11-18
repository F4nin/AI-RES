# G156 candidate egress / ADR134 — независимое review

**Checkpoint:** 2026-11-18, `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff. Это протокол текущего candidate среза, не review будущего SDK patch/host gate или approval модели. [Scope/evidence](../increments/G02_candidate_egress_preparation_REPORT.md).

## Независимость и способ работы

`g02_prerequisite_plan` автор control/runner, поэтому проверял только чужие codec/client/relay/native probe файлы. `g02_python_contract_review` автор codec/probe/Bifrost fixture, поэтому general/database/Python review выполнял только для backend control/root TLS/schema. Root — автор client/relay/serving/TLS/shared contracts и интегратор, его проверка своего кода не объявляется независимой. `g02_scope_security_review` не автор: blind-first read-only review всех security boundaries и delta re-review. Reviewers не запускали чужие runtime проверки; результаты авторских/root tests указаны отдельно в отчёте. Native Claude agents/commands не подключались: ECC инструкции применены доступными отдельными агентами и checklists.

## Findings и исправления

| Finding | Severity | Исправление / evidence | Результат |
|---|---|---|---|
| Противоречащие outcome поля могли игнорироваться, включая explicit null | MEDIUM | Presence sentinel в API/direct DTO; normalization INVALID_USAGE/full reservation/block, PG+ASGI negatives | CLOSED, general/security re-review |
| Поэлементная redaction пропускала split secret; interleaving choice мог стирать tail | MEDIUM | Stateful structural tails; streaming templates допускают только choice0 и не допускают tool/function channels; regression cases | CLOSED, security re-review |
| TLS key read helper сам не гарантирует mode/regular-file/symlink policy | MEDIUM | Explicit O_NOFOLLOW/NONBLOCK/fstat/mode/size/SSL pair verification; real TLS/negative tests | CLOSED, security re-review |
| Native identity/model/fingerprint мог сохранить известный virtual key | MEDIUM | Проверка actual credential substring до metadata retention, JSON/SSE/cancel/partial timeout regressions | CLOSED, security re-review |
| Recursive source hash читал скрытые credentials и не имел aggregate bounds | MEDIUM | Exact12non-codefiles; .py-only discovery; filters до read, fail-closed scandir, 2048files/4096entries/64MiBaggregate/8MiBfile local guards; forbidden-read/bounds regressions | CLOSED, final independent re-review |
| malformed evidence kind list/dict вызывал TypeError и оставлял fd/flock | LOW | Type guard/cleanup; malformed JSONL и reopen tests | CLOSED, final independent re-review |
| Claim metadata допускала несовпадающий cap/stream | LOW | Exact cap256 и stream iff SSE/CANCEL | CLOSED |
| Schema `$` мог принять trailing LF | LOW | Exact length/end constraints и newline negatives | CLOSED |

## Последний verdict

General reviewers APPROVE по перечисленным чужим компонентам; dedicated security reviewer **APPROVE, прежние MEDIUM+LOW CLOSED, новых findings0** после runner fixes и narrow relay `cache-control:no-cache` delta. Read-only `git diff --check` scoped paths exit0; reviewer source-checked regression tests, не заявляет их самостоятельный запуск. Source-binding изменение не исключает legitimate `platform/artifacts` code. Negative source tests включают forbidden reads внутри старых roots, traversal/errors/count/bytes/entries. JSONL cleanup проверяется повторным открытием lock.

Открытый неблокирующий DTO design LOW: конструктор evidence сам по себе допускает COMPLETE SSE с chunk_count0, хотя actual probe такого результата не создаёт. Не считать constructor полноценным transport verifier; можно усилить при следующей затронутой правке. Это не разрешение принимать synthetic evidence в host.

**Известный functional blocker отдельно:** actual official Bifrost теряет terminal fingerprint; SSE evidence правильно отклонено. Verdict guards не означает SSE compatibility, model admission, human acceptance, full pre-pr/Linux CI или готовность подготовки. Portable fixture-bootstrap delta и возможный SDK fix требуют нового scoped review.

## Portable bootstrap delta

Независимый security reviewer выявил MEDIUM: `.dockerignore` читался до symlink/regular-file проверки. Исправлено bounded opened-descriptor чтением до parsing для ignore/COPYinputs (NOFOLLOW/NONBLOCK/CLOEXEC/fstat;64KiB ignore/4MiB file/32MiB context), одинаковые captured bytes входят в tar/hash/build. Добавлены forbidden-read/symlink/FIFO/directory/size/aggregate negatives. Final independent re-review **APPROVE, MEDIUM CLOSED/open0**, scoped diffcheck0; reviewer runtime не запускал. Автор отдельно21passed41.40s,13bootstrap+8actualBifrost; source fixture SHA256 `a4a34ca1d1eec8658ed1d5fbd88692a8ee91456c1347df383085f137d3eb8bbb`. Root formatting-only scanner delta guards не меняет, source-checked reviewer. SDK patch остаётся не реализованной.
