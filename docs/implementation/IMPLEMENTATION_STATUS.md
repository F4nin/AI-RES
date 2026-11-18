# IMPLEMENTATION_STATUS

**SLICE-01: TESTED, финальная доставка IN_PROGRESS (2026-11-18).** Реальный governed
прогон V3 прошёл WorkerResult1.1, provenance, quote/line7, typeFR и secret checks.
[Результат](reviews/SLICE-01_RESULT.json), [отчёт](increments/SLICE-01_requirements_experiment_REPORT.md).
6 calls/0.0032058USD/remaining9.9967942 из разрешённых10USD, UNKNOWN/pending0.
MFA и личные profile/identity approvals фактические; APPROVED1/version1/generation3,
profile approval audit1. Старый account/runtime сохранён. Product/contracts/schema без diff.
V2scope371PASS, V3affected87PASS, fast1896PASS/4warnings, mypy10PASS,secrets0;
MFAcompat28PASS, independent reviewsAPPROVE/open0. Fullpre-pr PASS (backend3228/infra369/runtime148/PoC19),
newLinuxCI/Gitdelivery pending; VERIFIED пока не заявляется. S17/G02 не начаты.
Исторические статусы ниже не отменяют этого checkpoint.


**Final local gates:** contracts22/Renovate10/backend2853/fast1538/PG31/infra369/
runtime148/PoC19PASS; scanner0findings; rebuiltAPI14reviewedfiles/0hashmismatch и
trustedTLS admin login/logout PASS. Pre-pr scanner false positives исправлены,
завершён scoped resume exit0 без повтора полного backend; исходныйpre-pr exit2
не объявляется exit0. Следующий шаг только delivery PR34/exactLinuxCI, затем STOP
для обновления контекста. SLICE-01/G02 не начинать. После CI обновить evidence
ЛОКАЛЬНО без ещё одного docs-only push.

**Актуально, 2026-11-18 / ADR141.** По поручению владельца завершить все реализации
перед SLICE-01; SLICE-01/G02 не начинать, после завершения сохранить контекст.
Observed gateway draft373 интегрирован в root, HIGH reverse-SSE и final caller
reauthorization исправлены. Реализованы полный offline owner profile/Bifrost
approval CLI, exact auth/MFA/Policy/evidence, atomic audit/replay и one-APPROVED.
Новых migrations/grants/ALLOW/canonical/public API changes нет. Два независимых
source reviews APPROVE/open0; [20hashes](reviews/G02_OBSERVED_APPROVAL_CODE_HASHES.json),
[отчёт](increments/G02_identity_admission_operator_REPORT.md),
[review](reviews/G02_OBSERVED_APPROVAL_REVIEWS.md), [ADR141](decisions/ADR-141-observed-gateway-profile-approval.md).

Backend2853PASS/541existingwarnings; fast1538PASS/mypy204/15imports; final affected
PG31PASS/17.04s. Full pre-pr дошёл до scanner false positives; expressions исправлены
без ослабления checks, оставшиеся infra/runtime/PoC gates завершаются отдельно,
полный backend повторно не запускается. Точные команды/exit codes — в отчёте.
Git: feat/g02-manager-tools-planning, проверенная база1e971f5 + scoped20code/test
files и docs. PR34 остаётся текущей доставкой; один итоговый code+docs push после
локальных gates. Не делать второй checkpoint push ради слов/CI evidence.

Владелец подтвердил50USD/месяц и INTERNAL для обычных данных без ПДн/коммерческой
тайны, затем явно поручил самому создать default admin; дальнейшая персональная
настройка — позже с его помощью. Штатный bootstrap создал AI RES / Administrator /
admin@ai-res.local с уникальным случайным паролем в ignored
infra/secrets/local-admin/initial_password (0600,parent0700). Trusted HTTPS login200 /
opaque cookie / Origin+CSRF logout204 PASS, secret values не выводились.
Новых вопросов о создании default admin не задавать; пароль/metadata не коммитить.

Реальный model profile не утверждён/не включён, MFA не подделывалась. Настройка и
личная приёмка отложены владельцем; code readiness не заменяет эти действия.
Provider calls этого продолжения0, original10USD/8attempt account не менялся:
последнее подтверждённое6attempts/0.6005034usedOrReserved/9.3994966remaining.
Actual timeout не наблюдался в прежнем live case, не заявлять PASS. Перед любым
дальнейшим candidate call требуются свежие source/config/tariff/original balance.
G156 code locally TESTED, полный real-provider admission NOT VERIFIED; G02/S17/
S20/S21 и SLICE-01 NOT_STARTED. Остановка после текущей доставки для обновления
контекста. История ниже не очередь новой работы и не отмена актуального scope.

---

Исторические checkpoints:

**Последнее уточнение владельца:** лишний documentation push вызвал CI44312593429;
этот повтор отменён, COMPLETED/CANCELLED подтверждено. Runtimecode38 уже имеет
обаCI SUCCESS;1e меняеттолькодокументы. Не запускатьновуюработу/тесты/push/CI
до продолжения после обновленияконтекста. Это уточнение сохранено только локально.

**Последний docsHEAD1e971f5:** automaticrepeat PRCI44312593429 IN_PROGRESS,
contractsPASS; runtimecodeidenticalverified38. Finalcontext уточнёнлокальным
docs-onlydiffбезновогоpush. Поручениеприостановленодляобновленияконтекста владельцем;
G156 остаётся IN_PROGRESS, draft373/HIGH не интегрирован.

**Checkpoint перед обновлениемконтекста:** CODE38f5955 technicalCIpush+PR alljobsPASS,
Go/race/vet/native12PASS, guardedidle922.37s/182checksPASS. FullG156/modelactivation
ещёНЕзакрыты. Productobservedwiring сохранён отдельно вLOCALbranch
wip/g156-observed-wiring-checkpoint@3733825, неintegrated/published:1495purePASS,
knownHIGHreverseSSEdrift NOT_FIXED, noindependentreview/PG/pre-pr/CI.
[Draftcheckpoint](reviews/G02_OBSERVED_WIRING_DRAFT_CHECKPOINT.json).
По просьбе владельца после текущихтестов работа остановлена дляобновленияконтекста.


**Актуальный прогон2026-11-18:** localpre-pr PASS(backend2740/infra369/runtime148/poc19/contracts22);
HEAD504ceb0 LinuxPR44300787624/push44300778838 alljobsPASS, backend2740/541warnings/14:31,
locked dependency auditclean. На реальном DeepSeek TEXT/JSON/TOOL/SSE COMPLETE/capabilitytrue,
stablefingerprintbc19ba97cbe016479903222bb1578db6, usage+ledgerKNOWN. CANCEL locally
closed; initialCLI accountingunconfirmed thenauthoritativeSETTLED/UNKNOWN/fullreserve.
TIMEOUTcase returnedCOMPLETE within10s: timeoutNOTOBSERVED. Original6/8attempts,
used+reserved0.6005034USD,remaining9.3994966,pendingfalse/blockedfalse; providerbilling
notverified. [Metadata evidence](reviews/G02_FLASH_LIVE_EVIDENCE.json). No humanmodelapproval.
Concrete15minhousekeepingSQLdrift found/isolated; minimal3file candidate routingstore
fix source-reviewed twiceAPPROVE/open0, build/native/longidle/newexactCI running.
No newstage/framework, noSQLexceptions/auth weakening. G156 IN_PROGRESS; product
profile/observedgateway/human/SLICE prerequisites remain, G02 NOT_STARTED.


**Активное завершение допуска2026-11-18:** по уточнению владельца закончить
пункт как конечный MVP-результат, необходимые tests, затем вернуться к группам.
ADR140 identity operator локально TESTED: finaljointPG306PASS,fast1434PASS,
два independent APPROVE/open0; [отчёт](increments/G02_identity_admission_operator_REPORT.md).
Existing candidate launch соединён2новымиfiles:22purePASS, два independent
source APPROVE/open0; [review](reviews/G02_CANDIDATE_LAUNCH_REVIEWS.md).
Fullpre-pr/LinuxCI в работе. Владелец добавил SOPS-encrypted provider key; shape/
mode проверены без вывода. Provider plaintext не монтирован, calls/spend0.
Первый profileless candidate probe не требует product APPROVED/gateway; конечный
путь — [актуальный план](groups/G02_FLASH_ADMISSION.md). G156 IN_PROGRESS/
NOT VERIFIED, G02/S17/S20/S21 NOT_STARTED до нового согласия после подготовки.

**Checkpoint 2026-11-18 / ADR139: authenticated owner-review binding локально TESTED.**
Backend-only prepare/revalidate связывает exact configured owner+profile, живые
session/user/member/MFA, отдельный Policy action, actual observation/expectation
hashes и полный profile/control/generation/pending snapshot. Нет approval DML,
новых grants/migrations/routes или включённого профиля. Defaults deny.
[Отчёт](increments/G02_owner_review_binding_REPORT.md),
[review](reviews/G02_OWNER_REVIEW_REVIEWS.md),
[4 code hashes](reviews/G02_OWNER_REVIEW_CODE_HASHES.json).

Final joint PG187passed/0failed/errors/skipped/1existingwarning/73.17s,
newPG42passed/18.35s; contracts6/6+22passed. Два independent final source
APPROVE/open0; исправлены session-expiry-after-wait и factor/session lock inversion.
Final fast1428passed/4existingwarnings, Ruff0/mypy197files/15importsKEPT.
Финальные scope checks — в отчёте. Модельных calls/spend0.

**Далее:** narrowly privileged operator approval/lifecycle executor с exact human
решением и атомарным global audit; затем observed gateway integration. Материал
review не permission/approval/provenance attestation: executor снова authenticate/
authorize/revalidate. Real owner binding, evidence/Bifrost/profile acceptance,
final pre-pr/LinuxCI, reviewedtariff/account/key/live/SLICE остаются.
Подготовка G156 IN_PROGRESS/NOT VERIFIED, G02/S17/S20/S21 NOT_STARTED;
старт G02 только по новому согласию после всей подготовки. До S20 ADR129/G107.

**Git:** `feat/g02-manager-tools-planning`, HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + working diff.149initial files
сохранены кроме scoped helper/doc edits; frozen migrations/schema/canonical/
contracts/SDK/main stack/secrets этим срезом не менялись. Runtime только disposable
PG; commit/push/PR/newCI отсутствуют до общей приёмки подготовки. Исторический
ADR138 hash admission.py заменён новым helper-extraction hash только в ADR139
artifact; его собственный historical evidence не переписывается.
Ниже сохранена история checkpoints; актуальна эта сводка.

**Checkpoint 2026-11-18 / ADR138: admission lifecycle fence локально TESTED.**
Новая forward0025 и guard сериализуют lifecycle UPDATE observed Flash с begin/finalize
без новых runtime grants. READ COMMITTED и активный exact trigger/origin обязательны;
отказ сохраняет no-ticket/pending. [Отчёт](increments/G02_admission_lifecycle_fence_REPORT.md),
[review](reviews/G02_ADMISSION_LIFECYCLE_REVIEWS.md), [4 code hashes](reviews/G02_ADMISSION_LIFECYCLE_CODE_HASHES.json).

Final PG regression111passed/1existing warning/49.87s, fast1419passed/4warnings,
Ruff0/mypy196files/15importsKEPT, contracts6/6+22passed. Два independent source
reviewers APPROVE/open0, snapshot только+20lines к initial bytes; реальные calls/spend0.
FullG156/pre-pr/LinuxCI/live/human/SLICE NOT VERIFIED, подготовка IN_PROGRESS,
G02/S17/S20/S21 NOT_STARTED. Предыдущая остановка снята новой командой только для подготовки.

**Продолжение:** owner lifecycle с аутентификацией точного человека и привязкой evidence,
затем observed gateway integration; defaults disabled. Осталось5крупных блоков:
(1) admission/owner/wiring, (2) final regression/review/pre-pr/LinuxCI,
(3) reviewed tariff/original account/safe key setup, (4) live observations+human
Bifrost/profile approvals, (5) SLICE01(data/license/separatebudget).
ADR138 закрывает только гонку внутри первого блока. До S20 отдельно ADR129/G107.
Старт G02 требует нового явного согласия после всей подготовки.

**Git/runtime:** та же ветка `feat/g02-manager-tools-planning`, HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + working diff;142initial files
сохранены кроме scoped edits. Только disposable PG; main18IDs/StartedAt unchanged.
Задача не писала main data/secrets; checksum stores не проверялся.0025 frozen после
apply,0017/0020–24/SDK/canonical/contracts сохранены.
Commit/push/PR/newCI нет. Ниже исторические checkpoints, актуальна эта сводка.

**Checkpoint2026-11-18 / ADR137: configuration integrity локально TESTED.** Отдельный hardened candidate сохраняет SQLite/auth; fresh exact bootstrap, outer raw-URI allowlist, sticky mounted/rendered/marker/live/logicalSQLitesnapshot. Bookkeeping exceptions нет. Host0.2 связывает actual namespace/guardedhealth под env-i и image/source/StartedAt/Pid/RestartCount перед reserve/probe/onceclaim; settlement после отзыва сохраняется. [Отчёт](increments/G02_candidate_configuration_integrity_REPORT.md), [review](reviews/G02_CONFIGURATION_INTEGRITY_REVIEWS.md), [15code hashes](reviews/G02_CONFIGURATION_INTEGRITY_CODE_HASHES.json), [build proof](reviews/G02_CONFIGURATION_INTEGRITY_BUILD_PROVENANCE.json).

**Evidence:** Go normal/race8parent+42subPASS,vet0; finalfast1419passed/4warnings,mypy195files/15importsKEPT; corrected native12passed/104.20s. Legacy65casesPASS в joint run; тот run имел1test-fixture failure renderedrestore, после clean-env fix повторены new12, не заявлен единый77PASS. Два independent source reviewers APPROVE/open0 после typedSQL/proxy/sticky-test fixes и15hash checks. Image183fc5ac…/binaryd280f39e…; noELFinterpreter. Realprovidercalls/spend0; accounts/tariffs/keys/profiles/approvals не seed-ились. FullG156/pre-pr/LinuxCI/live/human/SLICE NOT VERIFIED; G02/S17/S20/S21 NOT_STARTED.

**Остановка после документирования по прямой команде владельца:** сообщить о сохранении, затем ждать обновления контекста и новой задачи на подготовку. Следующий seam самостоятельно не начинать. При новой команде: прочитать полныйAGENTS/CONTEXT_RETENTION и актуальныеfiles/Git; продолжение — product observed-admission/owner lifecycle/wiring, затем общиеfinalgates/reviewedtariff+originalaccount/safekeysetup/live+human/SLICE, доS20 ADR129/G107. Старт продуктовойG02 требует нового явного согласия после всей подготовки.

**Git/runtime:** `feat/g02-manager-tools-planning`,HEAD`db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, всё в рабочем diff, commit/push/PR/newCI не выполнялись. Исходные125files сохранены кроме authorizedscope additions; SDK/official/mainstack/frozen0020–24/canonical/contracts unchanged. Только owned disposable runtime/internalnet/tmpfs и test-only fault/proxy helpers; main18IDs/StartedAt сохранены. Logs `/tmp/g156-integrity-*` временные; постоянная сводка/evidence в report/artifacts выше. Предыдущие checkpoint записи ниже — история до ADR137, их «config gate OPEN» описывает прежний/official candidate; новый technical mechanism локально TESTED, весь G156 остаётся OPEN.

**Текущий checkpoint2026-11-18 — проверка изолированного Bifrost завершена, effective-config integrity gate OPEN.** Штатный renderer и mounted/rendered digests/mode, выбранные live+SQLite settings, auth/model/direct-key negatives, network/log checks: native6passed/0failed/skipped, final7.18s. **Admin PUT меняет live/SQLite при неизменных config bytes/image/canonical Docker inspect.** Это воспроизведённый пробел допуска, не security acceptance. [Отчёт](increments/G02_bifrost_effective_isolation_REPORT.md), [review](reviews/G02_BIFROST_ISOLATION_REVIEWS.md), [4code hashes](reviews/G02_BIFROST_ISOLATION_CODE_HASHES.json).

**Исправлен отдельный дефект host-инспектора:** Docker меняет порядок Mounts между чтениями. После проверки уникальных Destination mounts сортируются перед hash, все поля сохранены; RED1fail→GREEN78hosttestsPASS. Fast1390passed/4warnings,mypy194files,15importsKEPT; два independent source reviews APPROVE/open0. Existing descriptor hashes автоматически не принимаются; actual real descriptor пока отсутствует. Последняя test-only count-schema строка проверена native6/Ruff после fast.

**Ближайший безопасный шаг:** разработать/реализовать rendered/effective/admin/SQLite integrity enforcement перед reserve/claim, с mutation/restart/failure negatives. Потом оставшиеся admission/owner lifecycle/wiring, final pre-pr/LinuxCI, reviewed tariff/account/key setup, реальные observations+human Bifrost/profile acceptance, SLICE01 с отдельными data/license/budget gates. До S20 отдельно ADR129/G107. Modelcalls/spend0; реального ключа/accounts/tariffs/approval seeds нет. **Подготовка IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED до нового явного согласия после завершения подготовки.**

**Git/runtime:** `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, всё в рабочем diff; commit/push/PR/newCI не выполнялись. Новый runtime использовал только свои disposable containers/network/tmpfs; existing18main-stack container IDs/StartedAt сохранены. Main stack/config/secrets/official image/frozen0020–24/SDK/canonical не менялись. SDK image использован из cache с новым actual-binary proof. Предыдущие записи ниже — история, их «следующий шаг actual audit» заменён этим checkpoint.

**Текущий checkpoint2026-11-18, после новой команды владельца «Продолжаем реализовывать подготовительные этапы перед следующей группой»: ADR136 development host локально TESTED.** Предыдущая остановка снята этой командой только для подготовки. Concrete protected config/source/image/runtime/tariff gate, explicit local/test runner/control contexts, original-account preflight, claim revalidation и resource cleanup реализованы. Env-only standalone listener теперь accounting-only; baseCLI DRY_RUN/HOST_UNCONFIGURED. Fast1389passed/4warnings,mypy194files,15importsKEPT; realPG22passed(8new+14runner)9.62s; affected142passed0.75s; после final scanner fixture-only правки host77passed/Ruff10exit0. Два independent general/Python/database и security APPROVE/open0. [Отчёт](increments/G02_candidate_development_host_REPORT.md), [review](reviews/G02_DEVELOPMENT_HOST_REVIEWS.md), [10code hashes](reviews/G02_DEVELOPMENT_HOST_CODE_HASHES.json).

**Ближайший незавершённый seam:** фактическая isolated host topology/effective Bifrost config integrity: Docker inspect/mount/source bindings не доказывают неизменность mutable rendered `/app/data`/SQLite/admin state. До key/live этот runtime/config gate обязателен. Далее product admission/owner lifecycle/wiring, final regression/pre-pr/LinuxCI, свежие reviewed tariff/account/key setup, real technical evidence+human Bifrost/profile acceptance, SLICE01(data/license/separatebudget). Host требует нового процесса после code edits; actual local Docker endpoint задаётся trusted composition, не env auto-discovery. Реальных descriptor/account/key seeds не создавали; modelcalls/spend0. До S20 отдельно ADR129/G107. **Подготовка IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED до нового явного согласия после её завершения.**

Исторические checkpoints ниже сохраняются без переиздания evidence.

**2026-11-18, остановка по просьбе владельца до следующей команды:** текущий ADR135 SDK/build/native-fixture срез локально TESTED: Go normal/race11+134PASS,vet0; cold build/provenance278.63s; pure14PASS, runtime32PASS(24patched+8official,27deselected),35.70s; независимые Go/general/security APPROVE/open0. FullG156/pre-pr/LinuxCI/live approval/SLICE не завершены. Новую реализацию сегодня не начинать; G02/S17/S20/S21 NOT_STARTED. [Точная точка возобновления](CONTEXT_HANDOFF.md), [отчёт](increments/G02_bifrost_candidate_patch_REPORT.md).

**Уточнение владельца 2026-11-17: G02 NOT_STARTED, подготовка G156 IN_PROGRESS.** Продолжать подготовку и отдельно уведомить о её фактическом завершении; S17/S20/S21 без нового явного согласия не начинать. Локальный PASS/будущая готовность SLICE не являются таким согласием. [Паспорт](groups/G02_WORK.md); полная готовность подготовки пока не достигнута.

**ADR135 / local candidate Bifrost fix IN_PROGRESS,2026-11-18:** SDK patch локально TESTED normal/race11parents+134sub PASS,vet exit0,два independent APPROVE/open0; exactSHAec453… в [отчёте](increments/G02_bifrost_candidate_patch_REPORT.md). Build source/fresh acquisition/image/provenance/native32cases PASS, scoped source findings0; security acceptance реального провайдера и LinuxCI не заявлены. Required fingerprint/strict adapter/official image/main stack не ослабляются, modelcalls0. [ADR135](decisions/ADR-135-bifrost-candidate-fingerprint-patch.md); G156/SLICE/G02 не разблокированы.

**ADR134 / candidate egress IN_PROGRESS,2026-11-18:** codec/control/privateTLS/client/relay/profileless probe/runner локально TESTED; fast1281passed/4warnings,mypy191files,15importsKEPT, runner43passed(14realPG), security re-review APPROVE/open0. Actual Bifrost/fake upstream8passed включает negative terminal SSE fingerprint loss: **streaming compatibility остаётся BLOCKED**, guard не ослаблен. Portable fixture own-image build+21cases PASS, security delta APPROVE/open0; concrete trusted host/freshness/product wiring/owner lifecycle/key/live acceptance/SLICE ещё нужны. Новых migrations/main-stack restart/modelcalls нет. [Отчёт](increments/G02_candidate_egress_preparation_REPORT.md), [review](reviews/G02_CANDIDATE_EGRESS_REVIEWS.md). G156 OPEN, G02 NOT_STARTED.

**G156 / ADR133 — paid ledger локально TESTED, 2026-11-17.**0024 `a75c0eb164d9` frozen после disposable PG apply; один original authorization budget≤10USD/≤8attempts, durable reserve/onceclaim, UNKNOWN full hold, block/audit и permanent bodyhash uniqueness. Автор34PGcases; root40PGcases с отдельными процессами/logical restore, fast957passed/4warnings/mypy182files/15contractsKEPT и actual drift/upgrades/security6passed; всё exit0. Два final independent database/Python и security APPROVE/open0. Snapshot reviewed: total657add/1del к HEAD, включая предыдущие guard/mode changes. [Отчёт](increments/G02_flash_paid_ledger_REPORT.md), [review](reviews/G02_PAID_LEDGER_REVIEWS.md). Следующий незавершённый шаг — private-TLS candidate egress claim у relay + bounded runner; он только спланирован read-only. Ledger не даёт live authority; keys/calls/spend0, real accounts/tariffs не seed-ились. Full pre-pr/Linux CI текущего diff нет; подготовка не завершена, G02/S17/S20/S21 не начинаются. Ветка/HEAD прежние, все исходные локальные изменения сохранены; Git delivery не выполнялась.

**G156 durable foundation / ADR132, 2026-11-17:** реализованы0020–0022 и отключённый backend guard: immutable generations, profile-wide pending barrier, sticky block, metadata-only audit, narrow grants/FORCE RLS. Targeted PostgreSQL16:32passed/0failed/skipped, отдельные процессы и настоящий logical dump/restore; independent database/Python и security final APPROVE/open0. Full backend run:1901passed/3failed (legacy expectations); после точечных исправлений все3 + upgrades/drift/offline gates:11passed,exit0. Полный backend повторно ещё не объявлен PASS; pre-pr/Linux CI нет. 0023 honest observed mode/readonly reference теперь локально TESTED:56PGpassed,fast957passed/mypy180files,actual drift/upgrades/legacy7passed;два independent APPROVE. Nullable pin только exact Flash explicit mode, pinned DTO/factory/Bifrost guard не включены. Следующий шаг — ledger/isolated candidate permit/runner. Ledger/candidate runner/key/live/human approval/SLICE остаются. [Отчёт](increments/G02_model_admission_persistence_REPORT.md), [review](reviews/G02_MODEL_ADMISSION_REVIEWS.md). Исторические ниже «no DB/runtime» относятся к раннему validator checkpoint; основной dev-стек/secrets/платные вызовы не затронуты, применялись только disposable PG tests.

**G02 / ADR131, 2026-11-17:** по делегированию владельца выбран и реализован обязательный fingerprint VALUE для Flash expectation, contract0.2. Candidate absence/null остаются фактами; старая0.1 схема сохранена, текущий parser её отвергает. Выбор состава metadata CLOSED; точные live values и Bifrost/profile approvals ещё нужны. Это локальный отключённый срез, G156/G02 NOT VERIFIED, S17/S20/S21 NOT_STARTED. [ADR131](decisions/ADR-131-flash-required-fingerprint.md), [evidence](increments/G02_flash_admission_preparation_REPORT.md).

**G02, поручение 2026-11-17 — IN_PROGRESS, фаза подготовки G156.** [Паспорт](groups/G02_WORK.md), [план](groups/G02_FLASH_ADMISSION.md), ADR130. Создаётся отключённый observation/expectation validator; product admission/drift persistence не реализованы, G156 OPEN/NOT VERIFIED. S17/S20/S21 не начинались: сначала Flash admission→SLICE01→S17, OD19/G107 до первого producer S20. Исходные29локальных файлов сохранены; новый diff не наследует PASS прошлых CI. Код/контракты product runtime, DB/secrets и платные вызовы не включены. Результаты среза — [отчёт](increments/G02_flash_admission_preparation_REPORT.md).

**OD-19, делегирование владельца 2026-11-17:** выбор технического механизма принят Implementation Lead в [ADR-129](decisions/ADR-129-runtime-transport-and-authority.md) с учётом уже реализованных узлов. Сохраняются1Temporal namespace/2queues, отдельные Manager/Worker Runtime и общий pool9специализаций. Выбраны mTLS+native RPC/resource authorizer с durable task-issuance receipts; Platform API privateTLS+Ed25519 request binding, отдельный audience, durable nonces и server-owned execution assignments, узкая DB role/RLS/audit. **Это решение и план, не реализация:** protocolPoC NOT VERIFIED, код/контракты/миграции/секреты не менялись; G104/G106/G111 остаются OPEN до evidence, G107 reconciler+allowlist обязателен до первого producer. Owner-вопрос выбора механизма закрыт делегированием; rights/BASELINED/human/model/budget/SLICE gates не расширены.

**NCP-16, решение владельца 2026-11-17: ACCEPTED вариант B только для DeepSeek Flash первого среза.** Нормативная развилка закрыта; DOC-075/076/078 v1.1 и manifest v1.3 фиксируют исключение. Управляемые версии AI RES неизменяемы; наблюдаемая provider identity отделена, drift блокирует результат и дальнейшие вызовы затронутого профиля до повторной человеческой приёмки. Скрытый drift/возврат прежней модели не гарантируются. Это документационное изменение: identity/admission/drift runtime NOT IMPLEMENTED/NOT VERIFIED, профиль/Bifrost не утверждены, платные вызовы не разрешены. G-156 сохраняет технические условия допуска; SLICE-01 и G02 не разблокированы автоматически. Доступ к кабинету DeepSeek есть, владелец может создать ключ в любой момент; значение ключа не получено/не подключено. Последующим прямым решением владельца установлен общий потолок 10 USD на технический прогон допуска Flash/Bifrost, включая retries/ошибки с возможным списанием. Это не целевой расход и не лимит на каждый запуск; SLICE-01 автоматически не включён. До вызовов подготовить минимальный план с актуальными тарифами/верхней оценкой и контролем остатка; ключ ещё не подключён. [ADR-128](decisions/ADR-128-flash-observed-identity-exception.md).

**Организация работы, 2026-11-17:** [группы G01–G08](DEVELOPMENT_GROUPS.md), ADR-124, добавлены поверх S00–S39. ADR-127 уточняет цикл: сначала реализация Sxx группы, затем общая отладка/проверки/review/доставка; до приёмки внутренние этапы не считаются VERIFIED. Само документирование не запускает новые группы. Статусы ниже отражают фактическое отдельное поручение G01. Паспорта создаются при явном поручении на выбранную группу.

**Сверено:** 2026-11-16 по отчётам этапов и локальной истории Git. S01–S15 имеют документированный статус VERIFIED; эта сверка не является новым runtime-прогоном.

Статусы реализации: NOT_STARTED · IN_PROGRESS · IMPLEMENTED · TESTED · VERIFIED · BLOCKED · DEFERRED. IMPLEMENTED ≠ TESTED ≠ VERIFIED. DONE (для старта зависимых этапов) — по ADR-032.

**ARCH-01, 2026-11-17:** VERIFIED/DONE для dev-time import gate; локальный pre-pr, два независимых review, все восемь checks PR/push и отдельный post-merge Linux CI прошли. PR #23 слит; точные SHA/counts/ссылки — в отчёте. Общая историческая сверка выше не переиздаётся этим дополнением.

**S16 закрыт владельцем2026-11-17 (ADR-123):** технический gateway/adapter/relay/isolated Bifrost milestone DONE; evidence TESTED local+Linux+post-merge, полный pre-pr exit0. Реальный provider path NOT VERIFIED, его допуск BLOCKED по G-156/NCP-16/OD-01/21. Отложенная исходная приёмка перечислена в отчёте§17; закрытый S16 не повторять.

Готовность и разрешение владельца различаются: READY означает выполненные предпосылки для старта в указанном scope, но не поручение на реализацию. Несколько этапов могут быть READY одновременно; их статус реализации остаётся NOT_STARTED. Для S27 сохраняются ограничения на embeddings (OD-01/ADR-022) и подключение реальных Operation (OD-19/G-107).

| ID | Этап | Статус реализации | Готовность / примечание | Отчёт |
|---|---|---|---|---|
| S00 | Repository reconnaissance и baseline manifest | IMPLEMENTED (static evidence) | Воспроизводимость проверок — в S01 | [report](increments/S00_repository_reconnaissance_REPORT.md) |
| S01 | Contract toolchain и CI-валидация контрактов | VERIFIED (G-20, G-21 открыты) | DONE | [report](increments/S01_contract_toolchain_REPORT.md) |
| S02 | Backend skeleton и platform primitives (без БД) | VERIFIED (56 тестов; 2 прохода review; G-22 открыт) | DONE | [report](increments/S02_backend_skeleton_platform_primitives_REPORT.md) |
| S03 | Local infrastructure (Docker Compose), secrets и CI baseline | VERIFIED (локально и на GitHub Actions Linux, 2026-11-11): runtime 81 + статика 76, backend 58, contracts 19; повторное независимое review (security, silent-failure) — 0 открытых HIGH/CRITICAL; CI на Linux зелёный (G-27 закрыт, runs 42980598813, 42980597940) | DONE (ADR-032); слой 4 ADR-037 (security owner) — на S37 | [report](increments/S03_local_infrastructure_secrets_ci_REPORT.md) |
| S04 | Persistence foundation: Alembic, schemas, роли | VERIFIED (локально, 2026-11-11): backend 159 (unit 72 + arch 3 + PostgreSQL 16 integration 84), runtime 95, infra static 77, contracts 19; независимое review (4 агента) — 0 HIGH/CRITICAL; GitHub Actions на Linux зелёный (2026-11-11, PR #2: ci 42989650789, contracts 42989650777; G-43 в части Linux-CI закрыт) | DONE (ADR-032) | [report](increments/S04_persistence_foundation_REPORT.md) |
| S05 | Core tenant и execution schema + RLS | VERIFIED по решению владельца (2026-11-11; локально: backend 297 passed, три раунда review; ветка `feat/s05-core-tenant-execution-schema-rls`). GitHub Actions на Linux зелёный (2026-11-11, PR #3; финальный коммит 6716730: ci 43034572213 и 43034582085, backend/infra-static/infra-runtime/contracts — success; ранее на 1cb09dc: ci 43029221024 и 43029232241 (повторный прогон), contracts 43029220792 и 43029232542); дельта третьего раунда отдельным агентом не пересматривалась (отчёт §11) | DONE (ADR-032) | [report](increments/S05_core_tenant_execution_schema_rls_REPORT.md) |
| S06 | Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules | VERIFIED по решению владельца (2026-11-11; локально: backend 331, runtime 95, infra static 172, contracts 19; три review). GitHub Actions на Linux зелёный (2026-11-11, PR #5, коммит a7db82c: ci 43074829225 и 43074859429, contracts 43074829230 и 43074859545 — backend/infra-static/infra-runtime/contracts success). Дельта после review отдельным агентом не пересматривалась; открыты G-69…G-74, OD-14 | DONE (ADR-032) | [report](increments/S06_domain_content_schema_REPORT.md) |
| S07 | Identity, Local Auth, Policy Engine, Audit, Idempotency | VERIFIED по решению владельца (2026-11-11/12; локально `make pre-pr` ok: backend 676, runtime 99, infra 185, contracts 22; два прохода независимого review (4 + 2 агента), CRITICAL/HIGH нет; GitHub Actions на Linux зелёный (2026-11-11, PR #6, коммит 86328e4: ci 43111752244 и 43111759690, contracts 43111752277 и 43111759762 — backend/infra-static/infra-runtime/contracts success; ранее на c8e9040: ci 43107954898 и 43107964966)). Решения владельца R01/R03/SEC-05/SEC-06 внедрены (ADR-071…073); открыты NCP-12 (PROPOSED), OD-15 (WORKING), G-75…G-83 | DONE (ADR-032) | [report](increments/S07_identity_auth_policy_audit_idempotency_REPORT.md) |
| S08 | Read-only API vertical slices | VERIFIED (2026-11-12; GitHub Actions на Linux зелёный, PR #7, коммит 588055d: ci 43186306478 и 43186313460, contracts 43186306145 и 43186313578 — backend/infra-static/infra-runtime/contracts success; первый прогон упал на дрейфе дайджеста `caddy:2.11.9`, пин обновлён). Локально `make pre-pr` exit 0: backend 872, contracts 22, infra 185, runtime 99; schemathesis 13; review 3 агента — CRITICAL 0, HIGH 1 исправлен, дельта не пересматривалась). Дельта review отдельным агентом не пересматривалась. Открыты G-84…G-90, OD-17 | DONE (ADR-032) | [report](increments/S08_read_only_api_slices_REPORT.md) |
| S09 | Controlled write commands | VERIFIED (2026-11-12; PR #8 `feat/s09-controlled-write-commands`, коммит cc26beb; `make pre-pr` ok: backend 924, infra static 186, runtime 99; GitHub Actions на Linux зелёный: ci 43203466196 и 43203684744, contracts 43203466171 и 43203684738 — backend/infra-static/infra-runtime/contracts success; независимое review 4 агента — 0 CRITICAL/HIGH; приём загрузки MinIO не проверен, G-92) | DONE (ADR-032) | [report](increments/S09_controlled_write_commands_REPORT.md) |
| S10 | Outbox dispatcher, Inbox и CloudEvents | VERIFIED (2026-11-12; ветка `feat/s10-outbox-dispatcher-inbox-cloudevents`; `make pre-pr` exit 0: backend 964, contracts 22, infra static 186, runtime 99; review 3 агента — CRITICAL/HIGH нет, замечания исправлены; дельта review отдельным агентом не пересматривалась; GitHub Actions на Linux зелёный (2026-11-12, PR #9, коммит 248cd08: ci 43220712053 и 43220722294, contracts 43220712147 и 43220722299 — backend/infra-static/infra-runtime/contracts success)). OD-13 решён (ADR-084); открыты G-98…G-103, NCP-13 | DONE (ADR-032) | [report](increments/S10_outbox_dispatcher_inbox_cloudevents_REPORT.md) |
| S11 | Temporal foundation и dispatch Operation | VERIFIED (2026-11-12; локально backend 1025, infra 207; Linux CI зелёный (PR #11, ci 43233885212/43233901267: backend, infra-runtime, infra-static, contracts — success; contracts 43233885308/43233901331); влит в `main`; G-104/G-107 открыты) | DONE (ADR-032) | [report](increments/S11_temporal_foundation_operation_dispatch_REPORT.md) |
| S12 | Operation API, process primitives, cancellation, SSE | VERIFIED (2026-11-12; локально backend 1110; Linux CI зелёный (PR #13: ci 43260641203/43260655454, contracts 43260641383/43260655429; PR #14 с исправлениями review: ci 43270400409/43270476037, contracts 43270400514/43270475542 — backend, infra-runtime, infra-static, contracts success), влит в `main` (6ee65da, 397692e); два раунда независимого review: CRITICAL 0, HIGH 1 — G-117, reconciler до S23 по решению владельца, ADR-094) | DONE (ADR-032) | [report](increments/S12_operation_api_process_primitives_sse_REPORT.md) |
| S13 | Observability stack и мониторинг | VERIFIED (2026-11-13; локально: backend 1116, infra 305, runtime 148, contracts 22; Linux CI зелёный (PR #16: ci 43301634548/43301768127, contracts 43301634628/43301768417 — backend, infra-runtime, infra-static, contracts success); review: CRITICAL 1 и HIGH исправлены/вынесены владельцу, дельта исправлений отдельным агентом не пересматривалась) | DONE (ADR-032) | [report](increments/S13_observability_stack_REPORT.md) |
| S14 | Worker contracts: Envelope/Result/Notice | VERIFIED (2026-11-13; локально, одним `make pre-pr`: backend 1236, infra 307, runtime 148, contracts 22; Linux CI зелёный (PR #18: ci 43428029283/43428039248, contracts 43428029128/43428039135 — backend, infra-runtime, infra-static, contracts success); review: CRITICAL 0, HIGH 2 — 1 исправлен, 1 граница Gate; дельта исправлений и ADR-104 отдельным агентом не пересматривались) | DONE (ADR-032) | [report](increments/S14_worker_contracts_runtime_validation_REPORT.md) |
| S15 | LLMGatewayPort и Model Registry (провайдер-нейтрально) | VERIFIED (2026-11-13; локально `make pre-pr`: backend 1286, infra 307, runtime 148, contracts 22, import-linter 12 kept; Linux CI зелёный (PR #19: ci 43476639282/43476718776, contracts 43476639070/43476719560 — backend, infra-runtime, infra-static, contracts success)). Качество вывода модели не проверялось (только deterministic test double, ADR-022), реального провайдера нет (S16, OD-01); review: CRITICAL 0, HIGH 5 исправлены, дельта отдельным агентом не пересматривалась | DONE (ADR-032) | [report](increments/S15_llm_gateway_port_model_registry_REPORT.md) |
| S16 | LLM Gateway: технический механизм подключения провайдеров; исходная live-provider приёмка отложена | TESTED local+Linux+post-merge: HTTP/SSE adapter, relay, opt-in Bifrost2.5.1; полный pre-pr exit0 (backend1461,infra369,runtime148,PoC19), все8 checks153e3bb и отдельные post-merge091b976 success. Real provider path NOT VERIFIED | DONE по прямому решению владельца2026-11-17 в уточнённом техническом scope, ADR-123. NCP-16 PROPOSED, key/live tests/Bifrost acceptance/profile approval сохраняются перед включением; 0 USD model spend. Поддержка всех провайдеров runtime не заявляется | [report](increments/S16_bifrost_poc_provider_profile_REPORT.md) |
| S17 | Tool Registry и Tool Gateway | NOT_STARTED | PENDING_DEPS: SLICE-01 перед S17 (ADR115); ARCH-01 DONE. G02 подготовка G156 | — |
| S18 | Rules Registry и Rules Engine | VERIFIED — localpre-pr exit0 (backend1749/infra369/runtime148/contracts22/PoC19),finaltargeted186;3independentAPPROVE; exactsourceLinux backend1751/infra-static221/runtime148/contracts22/PoC19,all8checksSUCCESS | DONE (ADR032); доставка/закрытиеG01 через PR33 | [report](increments/S18_rules_registry_rules_engine_REPORT.md) |
| S19 | ContextPackageVersion (минимальный Context Builder) | VERIFIED: local pre-pr exit0 (backend1565,infra369,runtime148,contracts22,Renovate10,PoC19); targeted107; 3 independent reviews APPROVE; exact-head и post-merge Linux success | DONE (ADR-032), PR31 MERGED99e5ec1; G01: S18 отдельной строкой | [report](increments/S19_context_package_versioning_REPORT.md) |
| S20 | Project/Epic intake и Manager interaction | NOT_STARTED | PENDING_DEPS | — |
| S21 | Plan & Task orchestration | NOT_STARTED | PENDING_DEPS | — |
| S22 | Readiness Gate | NOT_STARTED | PENDING_DEPS | — |
| S23 | WorkerRun lifecycle и LangGraph runtime | NOT_STARTED | PENDING_DEPS | — |
| S24 | Manager–Worker coordination | NOT_STARTED | PENDING_DEPS | — |
| S25 | Independent QA и rework | NOT_STARTED | PENDING_DEPS | — |
| S26 | Requirements lifecycle, approvals, decisions & uncertainty | NOT_STARTED | PENDING_DEPS | — |
| S27 | Knowledge ingestion и indexing | NOT_STARTED | READY (embeddings — после OD-01) | — |
| S28 | Retrieval API и полный Context Builder | NOT_STARTED | PENDING_DEPS | — |
| S29 | Connector MVP (read-only) | NOT_STARTED | PENDING_DEPS | — |
| S30 | Source change, traceability и Impact Assessment | NOT_STARTED | PENDING_DEPS | — |
| S31 | Artifact, Change Request и Baseline lifecycle | NOT_STARTED | PENDING_DEPS | — |
| S32 | Recovery и reconciliation | NOT_STARTED | PENDING_DEPS | — |
| S33 | Evaluation harness и release gates | BLOCKED | BLOCKED | — |
| S34 | Learning signals и curated experience | BLOCKED | BLOCKED (S33 и допуск реального профиля OD-01/21; технический S16 DONE) | — |
| S35 | Web Project Workspace UI: foundation | NOT_STARTED | READY | — |
| S36 | Web Workspace UI: Manager, plan, results, traceability, artifacts | NOT_STARTED | PENDING_DEPS | — |
| S37 | Contract & security verification, hardening | BLOCKED | BLOCKED (незавершённые зависимости и real-provider/security acceptance OD-01/21; технический S16 DONE) | — |
| S38 | Performance, capacity и resilience drills | BLOCKED | BLOCKED | — |
| S39 | UI/UX acceptance, runbooks и productization | BLOCKED | BLOCKED (S37/S36 и допуск реального профиля; технический S16 DONE) | — |
| CI-01 | Ускорение CI и локального прогона тестов (мини-этап вне нумерации S, ADR-112) | VERIFIED (2026-11-14): `make pre-pr` exit 0; Linux CI зелёный на ветке и PR #20 (ci 25 → 9,4 мин); фильтр путей проверен; 2 слепых review без CRITICAL/HIGH; локальная ссылка `origin/main` содержит merge PR #20 (`0556444`); актуальность remote не проверялась | DONE (ADR-032); [промпт](increments/prompts/CI-01_faster_ci_pipeline.md) | [report](increments/CI-01_faster_ci_pipeline_REPORT.md) |
| DEP-01 | Renovate: настройка конфига и автоматические PR обновлений (мини-этап вне нумерации S, ADR-113/121) | DONE по решению владельца (2026-11-17); config VERIFIED, PR #25 MERGED `89d5a86`: strict+10 cases/18 deps, pre-pr exit0, 20 registry pins/0 mismatch, code/security reviews+delta 0 findings. PR/push и отдельный post-merge Linux CI success: backend1301, infra-static159, runtime148, contracts22, Renovate10 passed; failed/errors/skipped0; все дополнительные gates success | Закрыт владельцем перед очисткой контекста. App installation/onboarding и первый hosted run NOT VERIFIED, отдельный follow-up G-31; факт настройки Mend не утверждается. Alerts включены/проверены. Следующий этап — по новой команде и ROADMAP/ADR | [report](increments/DEP-01_renovate_dependency_updates_REPORT.md) |
| ARCH-01 | Контракты import-linter между доменными модулями (мини-этап вне нумерации S, ADR-114/120) | VERIFIED (2026-11-17): 14 kept/0 broken, 10 новых тестов; локальный pre-pr exit 0: backend 1301, contracts 22, infra 307, отдельный runtime 148 passed, 0 failed/errors/skipped; два независимых review — 0 findings. Linux CI зелёный на `1a45c4e` (PR #23: ci 44060321034/44060255903, contracts 44060321079/44060255864). MERGED `fe8b79b`, отдельные post-merge ci 44061994966 / contracts 44061994778 также success: backend 1301, infra-static 159, runtime 148, contracts 22; все дополнительные gates success | DONE (ADR-032); очередь S16/SLICE-01 перед S17 сохраняется | [report](increments/ARCH-01_domain_import_contracts_REPORT.md) |
| PROF-01 | Профили запуска Compose: dev-минимум и полный, метрики/дашборды в обоих (мини-этап вне нумерации S, ADR-116) | NOT_STARTED | PENDING_DEPS (после CI-01) | — |
| SLICE-01 | Тонкий экспериментальный прогон Requirements Worker с реальной моделью (мини-этап между S16 и S17, ADR-115) | TESTED | Реальный V3 прошёл; MFA/profile/identity approval фактические, 6 calls/0.0032058USD; финальные pre-pr/CI и доставка IN_PROGRESS | [report](increments/SLICE-01_requirements_experiment_REPORT.md) |

## Компоненты runtime

| Компонент | Статус | Этап |
|---|---|---|
| Contract toolchain | VERIFIED | S01 |
| Backend API | VERIFIED для реализованных срезов S02, S07–S12; полный продуктовый runtime не завершён | S02, S07–S12 |
| PostgreSQL `ai_res_db` (миграции, роли, RLS) | TESTED (S04–S06 схемы; репозитории частично) | S04–S06 |
| Docker Compose / secrets / CI | VERIFIED (локально и на GitHub Actions) | S03 |
| Outbox / Inbox | VERIFIED для S10; outbox-dispatcher добавлен в Compose в S11, полный путь остаётся частичным | S10–S11 |
| Temporal, Manager Runtime, Worker Runtime | VERIFIED (skeleton: старт, ack, fail-closed; WorkerRun — S23) | S11, S20, S23 |
| LangGraph | NOT_STARTED | S23 |
| LLM Gateway (port / Bifrost) | VERIFIED (port, реестр, test double) / TESTED (отключённый Bifrost adapter/relay, local+Linux); real provider/approval BLOCKED (OD-01, NCP-16) | S15 / S16 |
| Readiness Gate | NOT_STARTED | S22 |
| MinIO / ingestion / retrieval | MinIO VERIFIED в S03; ingestion и retrieval NOT_STARTED | S03, S27, S28 |
| Observability stack | VERIFIED для S13; известные gaps остаются в `KNOWN_GAPS.md` | S13 |
| Web Workspace UI | NOT_STARTED | S35–S36 |

**Runtime implementation: NOT VERIFIED.** Security / performance / production readiness: NOT APPROVED (Readiness Audit v2.2 §6).
