# G156 / ADR137 — independent configuration-integrity reviews

**2026-11-18**, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + working diff; [15code hashes](G02_CONFIGURATION_INTEGRITY_CODE_HASHES.json), [build proof](G02_CONFIGURATION_INTEGRITY_BUILD_PROVENANCE.json), [report](../increments/G02_candidate_configuration_integrity_REPORT.md).

Root — build/Python/native author/integrator/runtime owner. `config_integrity_plan` — limited Go patch author, no runtime. Separate `bifrost_audit_review` — general/Go/Python/test; `bifrost_isolation_security` — security/Go/architect/silent-failure. Оба blind-first/read-only: выводы по actual code до author report, не авторы проверяемых файлов. Они не запускали Go/Docker/native tests и не подменяют human/security-owner acceptance.

| Finding | Reviewer / severity | Исправление |
|---|---|---|
| SQLite JSON frame терял storage class/байты | General, MEDIUM | typeof+CASE/CAST, INTEGER/REAL/TEXT/BLOB/NULL отдельно, lossless schema/rows,6collision и duplicate tests; CLOSED |
| Sticky tests восстанавливали не все повреждённые зависимости | General, LOW | Каждая зависимость восстановлена, `guard.check()==nil` перед final refusal; CLOSED |
| Namespace health наследовал proxy env | Security, MEDIUM | Fixed env-i Docker exec, argv unit, native lying-proxy200/direct503/observer deny; CLOSED |

**Final source verdicts:** general и security APPROVE/open0. Go patch `7a69b6e13e721ba722aadb2ffa1f75986e6780b9f9ed74da655cd31ef836331b`;15current file hashes пересчитаны каждым reviewer,0mismatch. Logical readonly SQLite transaction/WAL/typed framing/schema/order/multiplicity/bounds/noexclusions, compiled raw-route/fresh-bootstrap/file/live/marker checks, new source/build bindings/namespace/restart/settlement boundaries и test-only fault injector рассмотрены.

Оба reviewers отдельно рассмотрели tiny deltas: `.get("Cmd")` принимает только OCI omitted/null/empty CMD при exact entrypoint; test-only env-i restoration использует правильный rendered namespace при намеренно hostile APP_DIR. README согласован с logical/trusted-host/local-only scope. Env-i proxy fix и actual os.replace отрицательные tests получили delta APPROVE; никаких скрытых SQLite bookkeeping exceptions нет.

Author evidence отдельно: Go8parent+42subnormal/race PASS,vet0; finalfast1419PASS/4warnings; image/proofPASS; joint76PASS/1fixturefailure, legacy65PASS; после restore fix newnative12PASS/104.20s. Reviewers не аттестуют эти исполнения своими source verdicts. Полный pre-pr/LinuxCI/live/human/SLICE не выполнены этим срезом.

**Final documentation consistency review:** оба reviewers отдельно прочитали report/ADR137/prompt/README/top context/status/groups/gap/ADL/traceability/ECC/index после blind-first code review: APPROVE/open0. Проверены честное разделение joint76PASS/1fixturefailure и corrected12PASS/legacy65PASS, descriptor0.2/public boundaries, snapshot/trusted-host limitations и user stop-after-docs.

После этих verdict root заполнил только фактически выполненные closeout checks: scanner0; prompts40/0; Registry74/manifest73/15code hashes0mismatch; local links282/0missing; baseline125→110unchanged+15scoped/17new; main18IDs/StartedAt unchanged/other0; diffcheck0. Эти root исполнения не приписываются reviewers. Verdict относится к локальному technical diff, не wholeG156/production/profile approval. По команде владельца после документирования — остановка до новой задачи.
