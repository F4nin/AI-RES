# G156 — isolated identity-admission operator: Increment Report

**Дата:**2026-11-18. [Промпт](prompts/G02_identity_admission_operator.md),
[ADR140](../decisions/ADR-140-identity-admission-operator.md).
**Результат:** механизм локально TESTED; весь допуск G156 ещё IN_PROGRESS.

## 1. Реализовано

Backend-only explicit human ACCEPT_IDENTITY/BLOCK: новая immutable generation,
pending barrier, sticky block и atomic global decision audit. Initial CANDIDATE
не становится APPROVED; первоначальный profile approver/time не переписываются.
Review заново вычисляется под live session/member/user/MFA и lifecycle fence;
самостоятельный execute Policy вне DB UoW. Same-session matching decision replay
возвращает historical receipt, не повторяет writes и не снимает поздний block.

## 2. Источники

Полные AGENTS/CONTEXT_RETENTION/CLAUDE/Registry/Spec с current addenda, Charter,
plan/passport/handoff/status/tooling/gates/strategy, owner OD01/21 decision,
ADR132/138/139; DOC076v1.1§3.1/7, IAM/Auth/Security и DOC068/072. Read-only
reconnaissance отдельного reviewer:74canonical/0missing/duplicates,
73manifest SHA+bytes/0mismatch; OpenAPI117/AsyncAPI360/Worker10refs/0missing.
Полного повторного чтения всех unrelated больших canonical документов не заявляем.

## 3. Scope и Git

`feat/g02-manager-tools-planning`, HEAD db8d4af34b0933aa2562adcf072b717eb0e3e3e9
+ working diff; initial157files сохранены по SHA перед edits. Новые0026/operator/
unit+PGtests; shared review helper, provisioning/audit/snapshot tooling и schema
snapshot. [10точныхhashes](../reviews/G02_IDENTITY_OPERATOR_CODE_HASHES.json).
Предшествующая работа не присваивается текущему срезу. Общая доставка допуска
остаётся впереди; этот отчёт не объявляет отдельный delivery или начало G02.

## 4. API/contracts/events

Public API/OpenAPI/AsyncAPI/Worker DTO/wire schemas не меняются; нет endpoint/CLI
для approval или product factory. Internal Python commands/receipts и2SQL routines.
Новые Policy actions accept_identity/block без packaged grants. Global технический
decision audit атомарен с guard state; нет domain event/consumer, Outbox N/A здесь.

## 5. Миграция и данные

Additive0026 c97e3bf386f1, parent b86d2af275e0; после successful apply frozen SHA
в hash artifact.2новые append-only owner-only FORCE RLS tables: пустой login/owner/
profile binding и global decision audit. Dormant NOLOGIN operator — только EXECUTE
2точных definer routines; API/PUBLIC/runtime прав не получают. Нет real login/
membership/binding/profile/key/account seeds. Owner-only parameter SET provision
нужен для function-local custom GUC; нет owner/migrator factory у приложения.
Upgrade populated previous сохраняет profiles/generation/pending/audit; actual
drift/roles/RLS проходят. Snapshot regenerated намеренно и reviewable; frozen0017/
0020–25/canonical/contracts/SDK не менялись. Mainstack этим срезом не изменялся.

## 6–8. Решения, fixes, ECC

ADR140 технический, не human acceptance. Root author/runtime/integrator;
python-testing/verification-loop прочитаны как checklists.2отдельных read-only
planner/architect/general/Python/database и security/silent-failure reviewers.
Нативные Claude commands/hooks/productQA/human approval не имитировались.
До successful apply исправлены inherited-EXECUTE audit, SQL NULL generation,
FKindex/duplicateFK и owner parameter privilege; последний потребовал полного
отката первой миграционной попытки. Expanded4fail — test-only clusterACL cleanup,
исправлен transaction rollback. [Review protocol](../reviews/G02_IDENTITY_OPERATOR_REVIEWS.md).

## 9. Проверки

Darwin arm64, Python3.13.5/uv0.11.31/Docker29.2.0/PostgreSQL16.15-bookworm existing
Compose digest, disposableTestcontainers. HEAD+10hashes выше; временные логи/XML
`/tmp/g156-executor-*` не обязательны для продолжения.

| Команда | Результат |
|---|---|
| python -B -m pytest -q unit/test_identity_admission_operator.py + test_model_owner_review.py + test_migration_graph.py | RED missingmodule1collectionerror; GREEN19passed/0.25s/exit0 |
| python -B -m pytest -q integration/postgres/test_identity_admission_operator.py | Firstapply44setuperrors/exit1, rollback; successful44passed/19.29s/exit0; expanded56passed4failed/26.81s; corrected60passed/26.91s/exit0 |
| UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast |1434passed/4existingwarnings/10.22s; Ruff0,mypy199files,15importsKEPT,exit0 |
| Те же offline env + make -j1 db-snapshot |exit0,1intentionalSKIP/3.94s; regeneration не PASS |
| Final joint PG ниже |306passed/0failed/errors/skipped/1existing xid8warning/112.51s,exit0 |

Final command, env PYTHONDONTWRITEBYTECODE=1, executable backend/.venv/bin/python -B:
`-m pytest -q` с путями `backend/tests/integration/postgres/` + test_identity_admission_operator.py,
test_model_owner_review.py,test_model_admission_lifecycle.py,test_model_admission.py,
test_model_admission_migration.py,test_model_admission_restart.py,test_observed_model_profiles.py,
test_model_registry.py,test_schema_drift.py,test_migrations.py,test_iam_sessions.py,
test_iam_mfa.py,test_roles_and_grants.py; `--tb=short --junitxml=/tmp/g156-executor-regression.xml`.

## 10–11. Security/review

Exact/absent/wrong human/login/scope; captured session/user/member/MFA revocation;
Policy deny/approval/outage/garbage/timeout/version; tampered4digests/full state;
pending acceptance denied/BLOCK preserved; concurrent same/different decisions;
lostreply replay without unblock, fresh interpreter durable receipt; expiry during
actual fence wait, factor-first MFA reset; audit failure rolls back all state;
API/operator direct grants denied; SQL missing/nullgeneration denied; function/
effective membership/parameterACL drift detected; GUC restored/no owner access.
Два independent source APPROVE/open0; runtime выполнял root. Metadata checks не
доказывают provenance/live capability и не дают physical commit-time expiry guarantee.

## 12–15. Границы и продолжение

G1/G2/G3/G5scoped/G6/G7PASS,G8/G9docs. Full pre-pr/LinuxCI/supplychain/live/human/
SLICE остаются общей приёмкой G156. Этот локальный checkpoint не завершает поручение
владельца закончить весь допуск. Продуктовые G02/S17/S20/S21 NOT_STARTED.

По уточнению владельца прекращено разрастание подготовительных срезов. Дальше
только существующий guarded candidate launch + общие необходимые проверки +
reviewed tariff/original account/safe key setup и реальный synthetic TEXT в прежнем
10USD/8attempt envelope, затем остальные plannedcases и отдельная human приёмка.
Product operator provisioning/APPROVED profile/observed gateway не нужны до первого
profileless probe. Canonical/Registry/contracts не менялись; implementation
ADR/status/handoff/plan/passport/ECC/traceability сохраняют фактическую фазу.

## 16. Общая приёмка подготовки и конкретные исправления

Накопленный approved scope173files опубликован commit896898983e0c4867533c5113dba77cd3bf1d8291,
[DraftPR34](https://github.com/F4nin/AI-RES/pull/34). Ключ добавлен владельцем через
SOPS/age в ignored localfolder, shape/mode проверены без вывода; provider plaintext
ещё не материализован/не монтирован, calls/spend0. Main secret values не ротировались.

Full localpre-pr corrected exit0: contracts22/7.82s,Renovate10,backend2740/541warnings/
629.04s,Ruff0/mypy200/15imports,infra369/143.48s,runtime148/151.87s,poc19/noexternalcalls.
Initial fullattempt1233PASS/1FAIL stale closed-table catalogue, interrupted after
563.64s; expectedset дополнен двумя новыми таблицами, все audit calls сохранены.
ДополнительныеEOF-only fixes двух прежних tests имеют identical AST. Snapshot
catalog trailing whitespace нормализован generator, actual drift повторён в fullsuite.
Raw git diffcheck patch-файлов помечает обязательные context prefixes (space+Go tab/
blankline); applied Go source проверяется gitapply --whitespace=error-all, full
nonpatchdiffcheck0. Frozen SDK fingerprint patch не менялся.

Linux896: contracts и infra-static/infra-runtimePASS, backend8FAIL/2732PASS/778.56s
на native observer Dockerinspect. Fixture default /usr/local/bin/docker отсутствует
на Ubuntu; новый test-only helper требует installed absolute CLI и передаёт его
явно всем4observers. Product observer trust/default/socket не меняется, skips нет.

Actual owned candidate выявил отдельный functional blocker: freshhealth200→503
после30s без inference при unchanged8inputs/renderedmarker. Metadata-only protected
SQLite copy показала sidekiq vk_expiry_cleanup/completed1; raw copies удалены.
Pinned source scheduler enqueue30s пишет journal, а fullSQLiteguard закономерно
блокирует изменение. Candidate patch теперь опускает только startupcall unused
workspace expirycleanup; sole stricttemplateVK non-expiring, per-request expiry/
auth продолжают independently enforced. Ни таблицы, ни columns не исключены из
snapshot; sticky block/admin deny сохранены. Это concrete MVPfix, не новый stage.

Два independent security/Go/general reviews APPROVE/open0; reverse delta воспроизводит
прежние patch/manifest/test hashes. Test теперь idles65s до firstSSE+health/auth,
затем прежние2SSE/10.2s и mutation negatives. Buildprovenance verified, новый image
b0e0b5f06c7e472129c9b1a2f8aee4e83d169ac5dda6b263536e8005b6b0d18c/staticbinary24e887a4…;
native12PASS/192.11s; [build proof](../reviews/G02_CONFIGURATION_INTEGRITY_IDLE_BUILD_PROVENANCE.json),
[3hashes](../reviews/G02_CONFIGURATION_INTEGRITY_IDLE_CODE_HASHES.json).
Go normal/race/vet и повтор exactSHA LinuxCI pending; failing896CI не засчитывается.

Candidate-only TLS/service/virtual credentials отдельно SOPS-encrypted; trusted
helper reuses pinned Renovate git/docker + copied existing CPython3.13.18/venv;
offline ABIimports smokePASS, без новой library/global install. Только selective
source mounts, provider key вне helper/BF. Actual account не seed-ился, runtime
relay disabled, original10USD/8attempts сохраняется. Current official pricing
подтверждена freshTLS2identical snapshots: peak/cachemiss0.30/1.20USDper1M;
[официальный источник](https://api-docs.deepseek.com/quick_start/pricing/).
Дальше finishaffectedchecks/CI и конкретный guarded setup→oneTEXT→accounting,
затем existingcases/humanacceptance/productintegration; G02 NOT_STARTED.

### 16.1 Повторный CI и диагностика (2026-11-18)

Commitabe40ea содержит concrete idle/CLI fixes; full affected native12PASS,
Go normal/race8parent+42sub twicePASS, vet exit0. Go first attempts failed due
noexec test tmpfs; corrected trusted builder exec tmpfs, source/guards unchanged.
Confirmed final command exit0, logs /tmp/g156-idle-go-command.log and results.log.

LinuxCI44297256856 и44297247246: contracts/static/runtimePASS; backend CANCELLED
by explicit20m job limit, stopped at44% after12m without per-test output.
This is not test failure evidence or PASS. Workflow-only followup increases
wallbudget45m for combined cold-native+PG suite and adds verbose test names/
durations/faulthandler180s, without skip/check removal. Independent general
source review APPROVE/open0; new exact-SHA Linux run must establish actual result.

Main runtime secrets equality24/24 verified, values/hashes not in report.
Prepared helper dry-runPASS, private TLS unauthenticatedclaim401PASS after
adding standard SKI/AKI/KeyUsage to owned candidate certificates; same keys/SAN/
validity, SOPS archive updated first, no main credential rotation. Reviewer
executor_normative inspected concrete owned metadata/source and found no new
security blocker; final enabled-relay delta needs inspect before firstTEXT.
Provider plaintext absent, account not inserted, paid calls/spend0.

### 16.2 Реальный provider и найденный runtime defect

Linux504ceb0a1d5132fa3fa8f9bc998bb8ddecd4cce2 passed allCI+contracts (PRci44300787624,
push44300778838), backend2740PASS/541warnings/871.69s, dependencyauditclean; infra-static
221+Renovate10, runtime148/149.20s, PoC19, supplychainpassed. Thirdparty report-only
findings remain perexistingpolicy; this is not a claim of zero findings acrossimages.
Faulthandler180sdump occurred during actualcoldDockerbuild, which completed196.61s;
secondfixturebuild165.37s. No test disabled, cancelledabeCI remainsnotaccepted.

Originalaccount insertedonce10USD/8attempts; noreset. StrictTLS/authenticatedclaim400
smokePASS. ExactexecutionhelperDockerobserver fixed Mac/helperAPI Config.OnBuild
schema mismatch; sameactualsnapshot/fixedguards. Relayprivatehostname pinned to
actualprivateIP becauseDockerresolved sharedoutbound address; TLS/SAN/CA unchanged.
Independent executionnamespace10checks/enabledruntime18checks/DNSdelta10checks PASS.

[Six realcases](../reviews/G02_FLASH_LIVE_EVIDENCE.json): TEXT/JSON/TOOL/SSE successful,
stableactualfingerprint and knownusage. CANCELinitiallyCLIexit2/CLAIMED/accounting
unconfirmed, laterreadonlyledgerSETTLED/UNKNOWN/full0.6003072reserve/pendingfalse;
originalappend-onlyresultnotrewritten. TIMEOUTwithdefault10s completedfast, so actual
timeoutnotobserved; no automaticretry.6attempts,used+reserved0.6005034,remaining
9.3994966USD,0pending/blocked; billingnotverified. No response/prompt/key saved in
artifact. Humanacceptance/profileactivation/productobservedwiring/SLICE notperformed.

Separate provider-free diagnostic clone failed at902.3s with staticSQL_DRIFT.
Protectedcopy comparison exposed only additionalgovernance_config static key
complexity_semantic_generations beyondinitialtimestamps; copiesdeleted, values
neverexported. Pinnedroutingv1.3.2 registry every15min savesemptyclaims plus a
distributedlock lifecycle. Preseedalone wouldnotfix transientlockwrites. Minimal
candidate-only routing.Init optionalConfigStore=nil disables unusedpersistence/
registry while actualgovernance/authstore stays. Strictcandidateemptyrules/vector/
complexity, soleprovider/adminroutesdeny/fullSQL/stickycheck unchanged. Sourcefix
onlypatch+exactbuildpathallowlist+manifesthashes; no dependency/vendor/newframework.
Two independent final3file reviews APPROVE/open0; purecheckedcontext1466files/4pins
unchangedPASS. Newbuild/affectedGo/native/15minidle/newexactCI pending; no claim of
closedruntimebug until evidence. Full localPG/pre-pr notrepeated forunchangedPython/
DB/contracts; finalLinuxstillrunsfullsuite.

Final3filefix localresults: immutableimagec52717de…/staticbinary2915a332…,
[provenance](../reviews/G02_CONFIGURATION_INTEGRITY_ROUTING_BUILD_PROVENANCE.json).
Normal/race8parent+42subtwicePASS,vet0; currentnative12PASS/152.32s/0skips,secret0.
920s provider-free guardedidle runs inparallelwithfinalexactLinuxCI; definitive
external results [PR34](https://github.com/F4nin/AI-RES/pull/34). These gates must
close before any furtherpaidcall. Runtimeprobe key/ownerapproval remain separate;
no architecture/publicAPI/migration changes in this concrete3filefix.
