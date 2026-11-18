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

### 16.3 Checkpoint по команде владельца перед обновлением контекста

Владелец попросил сообщить после текущих тестов и сохранить продолжение. Новые
изменения после этой команды не начинаются. CodeHEAD38f5955b4c363b5a0a38c6e1db69de5daeb97aff,
[pushCI44308586420](https://github.com/F4nin/AI-RES/actions/runs/44308586420)PASS
alljobs, backend2740/541warnings/870.89s, lockeddependencyauditclean.
PRCI44308595231 проверяется отдельно перед передачей. LocalGo/race8parent+42sub
twicePASS,vet0,native12PASS/152.32s,secret0. Exactimagec52717de… longidle
922.37seconds/182guardedhealthchecksPASS/0providercalls/controlsunchanged:
[proof](../reviews/G02_CONFIGURATION_INTEGRITY_ROUTING_IDLE_EVIDENCE.json).

Параллельный productport DRAFT не интегрирован в root/PR: локальная ветка
wip/g156-observed-wiring-checkpoint, commit37338251fc2525a5b9bfb378b9bd1d19ceba9fb4,
worktree /tmp/g156-observed-wiring-38f5955. Source14files/740insertions/47deletions,
pure1495PASS/4warnings/10.50s,Ruff0/mypy198/imports15kept. НЕТ PG/pre-pr/LinuxCI/
provider/independentreview. Сохранён [checkpoint](../reviews/G02_OBSERVED_WIRING_DRAFT_CHECKPOINT.json)
с exacthashes/commands/logs. LocalGitcommit сохраняетчерновик, не доставка.

KnownHIGH в DRAFT: SSEidentity X→approvedY можетфинализироватьVALIDATED(Y), хотя
outputотклонён, поэтому durable block не выставлен. Первый следующий fix: при
любом intra-streamidentity/ref inconsistency finalize malformed/noobservation и
reverse-drift regression, затем независимые general/securityreviews. Новаяработа
остановлена по checkpointsteering, дефект не скрыт и не принят какPASS. Root38
этого кода не содержит. Legacy/technical candidate rootgates не доказывают готовность
этого productport. Fullprofileactivation/humanownerCLI/actualpolicy/budget/managed
version composition остаются отдельно в том же MVPпункте; реальных approvals/
permissions/seeds/adminbootstrap не создано. ADR106 допускает owner provisioning
CANDIDATE без новых grants, но migratorcredential неhumanapproval; не имитировать
ownerActor/session/MFA из чата и не ослаблять defaultdeny.

FinalPRCI44308595231 alljobsSUCCESS too: backend2740PASS/541warnings/1186.47s,
lockeddependencyauditclean; bothcontracts38SUCCESS. Codeverification attaches to
38f5955, laterdocs-onlycheckpoint notnewruntimecode. Ownerrequestedcontextupdate;
workstopsatthischeckpoint, fullG156/modelapproval notclosed.

Ownerfinalsteering: «Давай документируй, я обновлю контекст и продолжим работу по
подготовительному этапу». Checkpointdocs pushed1e971f5 (runtimecodeidentical38),
автоматический PRCI44312593429 на1e ещё IN_PROGRESS; contracts1ePASS. Послеэтой
проверки дальнейшее уточнениеhandoff/status/report сохраняется локальнымdocs-only
diff, безновогоpush/CIцикла. Общийдопуск/G02 не закрываются; firstcontinuation —
readfullAGENTS/CONTEXT_RETENTION/currentGit +newCIstatus, затемknownHIGHdraftfix
иreview/integration втомжепоручении. Никаких новых paidcalls/approval/bootstrap
после шестой попытки не было. Source38 exact4hashes unchanged.

Исправление после замечания владельца: documentationpush был лишним и запустил
повтор44312593429. Root отменил его, GitHub подтвердил completed/cancelled.
Источник38 сохраняетобауспешныхCI, runtimecode1e byte-identical38. Отмена не
объявляетсяPASS новогоSHA. Дальнейшая работа/проверки/commit/push/CI до продолжения
не выполняются; последнее уточнение сохранено локально без публикации.

## Продолжение G156 после возобновления владельцем — ADR141, 2026-11-18

Это завершение того же порученного допуска, не новый подготовительный этап.
Старт: `feat/g02-manager-tools-planning`, HEAD1e971f57c2ed19f2897db00ef5184e2dc58efd7f;
пять существующих docs-only правок сохранены. Draft3733825 из отдельного local
worktree перенесён в root без изменения его исторического checkpoint. Runtime
tariff `infra/llm_poc/candidate_tariff.json` остаётся untracked, не входит в commit.

### Реализация и совместимость

- Product factory теперь допускает explicit `bifrost-observed` только с injected
  registry/budget/transport/admission. Unconfigured остаётся default. Backend
  ModelRegistryAdmission связывает exact request/profile и существующий durable
  guard; caller authorization/managed versions проверяются до и после finalize.
- Flash observed имеет NULL pin и обязательную observation; immutable consumers
  сохраняют прежнюю модель. Retry/fallback/embedding observed профиля запрещены.
  SSE bounded и не выдаётся до terminal validation/durable finalize. Reverse
  identity/ref/terminal inconsistency всегда malformed; последняя approved identity
  не скрывает ранний drift. Unknown outcome сохраняет pending и worst-case charge.
- Новый offline `ai_res.cli.model_profile` реализует личное owner approval полного
  профиля+Bifrost artifact, default preview. Нужны существующий MFA session token,
  exact command UUID confirmation, owner DB binding и отдельная API factory для
  authentication. Новых ALLOW/roles/grants/DDL/public endpoint нет. Complete profile/
  expectation/observation/acceptance hashes, global single-APPROVED fence, executable
  candidate validation и atomic lifecycle+audit/replay. getpass fallback запрещён.

Новые source files: `llm/admission.py`, `modules/model_registry/gateway_admission.py`,
`modules/model_registry/profile_approval.py`, `cli/model_profile.py`; изменены
существующие adapter/factory/gateway/registry/routing/transport/types/config и
model-registry readers. Шесть новых test files проверяют эти boundaries;
[20 exact code/test hashes](../reviews/G02_OBSERVED_APPROVAL_CODE_HASHES.json).
Миграций/изменений данных продуктовых проектов нет; frozen0017/0020–26, canonical,
contracts/mirror/compatibility baseline и main Compose configuration не менялись.
Public API/events и Temporal/LangGraph process surfaces не расширены.

### ECC и независимое review

Root: scope/architecture, behavioral RED→GREEN, fixes/CLI/actual PG/integration/docs;
локальные python-testing/verification-loop checklists. `activation_scope`: отдельный
read-only planner/architect, затем bounded author service+unit. Два независимых
blind-first general/Python/architecture/silent-failure и security/database reviewers
проверяли чужой source; author не reviewer себя. Все findings закрыты,
final APPROVE/open0, test-only delta отдельно APPROVE. [Протокол](../reviews/G02_OBSERVED_APPROVAL_REVIEWS.md).
Нативные Claude agents/hooks/slash commands, product QA и human approval не заявлены.

### Проверки текущей версии

Среда Darwin arm64, Python3.13.5, uv0.11.31, PostgreSQL16.15/Testcontainers,
Docker29.2.0; full stack — только existing local dev/test. Для cryptographic infra
checks выбран установленный OpenSSL3.6.3 вместо несовместимого LibreSSL3.3.6,
только через PATH процесса, без глобальных изменений.

| Gate/команда | Фактический результат |
|---|---|
| Registry canonical existence/unique IDs/paths | 74present/0missing/0duplicates |
| Initial RED observed regressions | 6failed/39deselected, ожидаемый воспроизведённый defect |
| Observed unit files | 50passed/0failed/skipped после fixes |
| Observed actual PG path | 10passed/0failed/skipped/7.56s |
| Approval/CLI actual PG+pure joint | 53passed/0failed/skipped/12.61s (21PG+32pure) |
| `make pre-push-fast` | exit0, Ruff0/mypy204files/15importsKEPT; 1538passed/4existingwarnings/10.13s; после scanner fix1538passed/11.58s |
| Full backend внутри pre-pr | 2853passed/0failed/skipped,541existingwarnings,734.95s |
| Final affected PG | 31passed/0failed/skipped,17.04s; expiry trigger-entry proof включён |
| Full pre-pr | contracts22PASS/7.77s,Renovate10PASS,backend2853PASS,infra-static0violations; exit2 на scanner false positives, оставшиеся gates возобновлены отдельно |

Первый общий pre-pr был прерван exit130 после выявления неподходящего системного
openssl, не объявлен PASS. Полный прогон запущен заново с process-only PATH
`/opt/homebrew/opt/openssl@3/bin:$PATH`, лог `/tmp/g156-final-pre-pr-openssl.log`.
После старта изменён только PG expiry-test: nontransactional sequence подтверждает
вход в audit trigger до rollback, исключая ложный PASS от раннего expiry. Для этой
дельты выполнен отдельный affected31PG PASS, runtime source не менялся.
Scanner отверг3 path/reference expressions как literal assignments; после явного
выделения validated auth config и fixture credential variables false positives
устранены без allowlist/отключения scanner. Последняя test-only dictionary layout
правка проверена Ruff; actual credential values/behavior не менялись. Два независимых
reviewers отдельно подтвердили эквивалентность final CLI refactor.
Ранний PG fixture попытался изменить immutable profile fields и был отвергнут;
исправлен fixture initial INSERT, protection не отключалась. CLI unit tests также
выявили ошибочные exception-message assertions; исправлены на reason codes.

### Действительные решения и готовая dev-установка

Владелец отдельно подтвердил точный **50USD/месяц** и **INTERNAL только для обычных
данных без ПДн/коммерческой тайны**. Это не общий словарь классификации и не новый
SLICE budget. Затем прямо поручил самому создать необходимые объекты с defaults,
персональную настройку выполнить позже. Новых вопросов о default admin не требуется.

Штатным `ai_res.cli.bootstrap` создан первый ORGANIZATION_OWNER:
организация AI RES, имя Administrator, e-mail admin@ai-res.local. Уникальный
случайный пароль сохранён в `infra/secrets/local-admin/initial_password` (0600,
parent0700, ignored); metadata в том же private каталоге. В БД только Argon2id hash.
Bootstrap audited/one-shot, контейнер удалён `--rm`. Две попытки до dispatch были
отвергнуты Docker Compose из-за неподдерживаемого `run --no-build`; флаг убран,
пароль не ротировался/не генерировался повторно, единственный actual bootstrap PASS.
Read-only до bootstrap: users/activeowners/MFA/profiles/bindings все0.

Фактический HTTPS login через Caddy с trusted local root CA: HTTP200, exact user/org,
opaque ai_res_session cookie; Origin+CSRF logoutHTTP204. Пароль, bootstrap secret,
session/csrf tokens не выведены и не попали в отчёт/argv/env. Этот первый smoke
проверил существующий running API image; final stack smoke повторить после pre-pr
rebuild перед приписыванием результата новой реализации. MFA не подделывалась;
личная настройка оставлена владельцу согласно его указанию.

### Оставшиеся границы и следующий шаг

Код owner approval и observed product path реализован, actual profile/identity/
Bifrost approval не совершались. Factory по умолчанию выключена; missing settings/
permissions не превращаются в ALLOW. Monthly budget decision не доказывает real
ledger enforcement. Предыдущие live TEXT/JSON/TOOL/SSE evidence остаются историей;
CANCEL закрыл HTTP и сохранил UNKNOWN reserve, actual billing/provider compute-stop
не доказаны. TIMEOUT завершился COMPLETE и не объявляется timeoutPASS.
В этом продолжении provider calls/spend0; исходный10USD/8attempt ledger не менялся.
Последний подтверждённый баланс:6attempts,0.6005034USD used/reserved,9.3994966remaining.
Новых платных attempts ради повторения CANCEL не нужно.

G156 пока IN_PROGRESS; G02/S17/S20/S21 и SLICE не запускались. После завершения
кодовых gates сохранить delivery evidence; персональная конфигурация/приёмка
реального профиля — с владельцем позже по его прямому указанию. Самостоятельное
расширение продукта/permissions или превращение chat approval в MFA session запрещено.

### Финальный локальный checkpoint перед единственной доставкой

**Поручение владельца уточнено:** SLICE-01 не начинать; закончить все реализации
перед ним, сохранить checkpoint и остановиться для обновления контекста. После
создания default admin никаких новых вопросов о персональной настройке не ставить.

`make -j1 pre-pr` с process-only OpenSSL3.6.3 выполнил contracts22/7.77s,
Renovate10, backend static/mypy204/import15 и full backend2853/734.95s; exit2 на
scanner path-expression false positives. После fixes выполнены fast1538/11.58s,
affected31PG/17.04s; затем
`PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" make -j1 infra-scan-secrets up infra-test infra-test-runtime llm-poc-up llm-poc-check`
**exit0**: scanner0findings, infra369/149.58s, runtime148/141.41s, PoC19/0failed;
rendered configurations22/22/22/24services,0violations. Runtime executions в
infra-test и отдельном target не считать уникальными тестами. Полный backend
после эквивалентного config refactor не повторяли: затронутые проверки выполнены,
никакие checks/allowlists не отключались. Единый исходный `make pre-pr` exit0 не
заявляется; сохранены честные exit codes полного прогона и его возобновления.

Rebuilt API содержит все14 reviewed production source files с **0hashmismatch**.
Actual trusted-CA HTTPS login200/exactbootstrapuser/opaque cookie и Origin+CSRF
logout204 повторно PASS на новом образе. Guarded existing candidate BF/control/relay
container IDs не изменились; volumes/24main dev secrets не сбрасывались/не ротировались.
Новых provider calls, fallback, реальных model grants/approval или расходов нет.

Source review: два independent APPROVE/open0; конечный test-only fixture layout
дополнительно general APPROVE. G1–G9 covered в указанном technical scope; G6 DDL
N/A (нет migration), существующая PostgreSQL suite выполнена полностью. Public API,
upload/connector/Temporal changes N/A — соответствующие поверхности не менялись;
existing regression suite всё равно выполнялась. Security tests содержат actual
API/owner separation, revoke/outage/auditfail/sessionexpiry, exact evidence/replay,
durable next-call block, conservative cancellation; real quality/timeout/human
model acceptance отдельно не заявлены.

**Доставка:** один code+docs commit/push в существующий draft PR34; Linux CI на
новом exact SHA проверяется отдельно. Повторный docs-only push для сохранения CI
слов запрещён текущим пожеланием владельца: финальное CI evidence/handoff сохранить
локально и в итоговом ответе/PR description, не запуская второй CI cycle.
Code local TESTED; полный real-provider G156 NOT VERIFIED, actual setup deferred
by owner. Следующего инкремента/SLICE/G02 не запускать.
