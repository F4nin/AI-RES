# G02 — Инструменты и планирование Manager

**Checkpoint перед обновлениемконтекста:** CODE38f5955 technicalCIpush+PR alljobsPASS,
Go/race/vet/native12PASS, guardedidle922.37s/182checksPASS. FullG156/modelactivation
ещёНЕзакрыты. Productobservedwiring сохранён отдельно вLOCALbranch
wip/g156-observed-wiring-checkpoint@3733825, неintegrated/published:1495purePASS,
knownHIGHreverseSSEdrift NOT_FIXED, noindependentreview/PG/pre-pr/CI.
[Draftcheckpoint](../reviews/G02_OBSERVED_WIRING_DRAFT_CHECKPOINT.json).
По просьбе владельца после текущихтестов работа остановлена дляобновленияконтекста.


**Актуальный прогон2026-11-18:** localpre-pr PASS(backend2740/infra369/runtime148/poc19/contracts22);
HEAD504ceb0 LinuxPR44300787624/push44300778838 alljobsPASS, backend2740/541warnings/14:31,
locked dependency auditclean. На реальном DeepSeek TEXT/JSON/TOOL/SSE COMPLETE/capabilitytrue,
stablefingerprintbc19ba97cbe016479903222bb1578db6, usage+ledgerKNOWN. CANCEL locally
closed; initialCLI accountingunconfirmed thenauthoritativeSETTLED/UNKNOWN/fullreserve.
TIMEOUTcase returnedCOMPLETE within10s: timeoutNOTOBSERVED. Original6/8attempts,
used+reserved0.6005034USD,remaining9.3994966,pendingfalse/blockedfalse; providerbilling
notverified. [Metadata evidence](../reviews/G02_FLASH_LIVE_EVIDENCE.json). No humanmodelapproval.
Concrete15minhousekeepingSQLdrift found/isolated; minimal3file candidate routingstore
fix source-reviewed twiceAPPROVE/open0, build/native/longidle/newexactCI running.
No newstage/framework, noSQLexceptions/auth weakening. G156 IN_PROGRESS; product
profile/observedgateway/human/SLICE prerequisites remain, G02 NOT_STARTED.


**Текущее завершение2026-11-18:** владелец потребовал закончить допуск как
конечный MVP-результат с необходимыми тестами, затем вернуться к группам.
ADR140 operator локально TESTED306jointPG/1434fastPASS, два independent APPROVE;
[отчёт](../increments/G02_identity_admission_operator_REPORT.md). Launcher existing
contexts готов:22purePASS/два independent APPROVE, [review](../reviews/G02_CANDIDATE_LAUNCH_REVIEWS.md).
Finalpre-pr/LinuxCI и real setup в работе; provider key получен только как локальный
SOPS ciphertext, value не раскрывался, calls/spend0. Не добавлять самостоятельные
подготовительные механизмы без concrete blocker; product gateway/APPROVED не нужны
до первого profileless candidate probe. G02 NOT_STARTED; подготовка ещё IN_PROGRESS.

**Checkpoint2026-11-18 / ADR139:** authenticated owner identity-review preparation
локально TESTED; newPG42PASS, jointPG187PASS, contracts22PASS, два independent
APPROVE/open0. [Отчёт](../increments/G02_owner_review_binding_REPORT.md).
Exact owner/session/MFA/Policy/evidence/full profile/state binding реализован;
нет approval DML/grants/migrations или включения. Следующий seam — отдельный
operator lifecycle executor с exact human decision/global audit, затем observed
gateway. Finalgates/key/live/human/SLICE остаются; G156 IN_PROGRESS/NOT VERIFIED,
G02/S17/S20/S21 NOT_STARTED до нового согласия после подготовки.

**Checkpoint 2026-11-18 / ADR138:** lifecycle fence локально TESTED, forward0025;
PG111PASS, fast1419PASS, contracts22PASS, два independent APPROVE/open0.
[Отчёт](../increments/G02_admission_lifecycle_fence_REPORT.md).
Новая команда продолжения сняла остановку ADR137 только для подготовки.
Owner lifecycle/authenticated evidence binding и observed gateway ещё нужны;
fence не является dispatch authority. Затем finalgates/key/live/human/SLICE.
G156 IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED до нового согласия после подготовки.

**Актуально2026-11-18 / ADR137:** [configuration integrity](../increments/G02_candidate_configuration_integrity_REPORT.md) локально TESTED:Go8+42normal/racePASS,vet0,fast1419PASS/4warnings,newnative12PASS/final104.20s,legacy65PASSизjointс1testfixturefailure(исправлен/повторnew12). Два independent source APPROVE/15hashes0mismatch. Новый отдельный candidate: freshbootstrap,hardroutefreeze,stickyfile/live/readonlylogicalSQLiteguard безexclusions;host0.2actualnamespace+env-ihealth+bootbindingpreclaim,settlementpreserved. Official/SDK/mainstack/frozen/canonical не заменены,realcalls/spend0. **Владелец поручил закончить документирование и остановиться до обновления контекста/новойзадачи.** G156 IN_PROGRESS/G02/S17/S20/S21 NOT_STARTED. Следующий preparatory seam — product admission/owner lifecycle/wiring; потом finalgates/tariff+account/key/live/human/SLICE. Старые ниже configOPEN checkpoints — история до нового механизма, не отмена общего G156 OPEN.

**Актуальный native audit2026-11-18:** [проверка](../increments/G02_bifrost_effective_isolation_REPORT.md) локально TESTED:6nativePASS/final7.18s,host78PASS,fast1390PASS/4warnings,два independent APPROVE/open0. Штатный renderer/selected live+DB settings/auth/network/logs проверены на новом disabled-provider стенде. Admin mutation live/SQLite при unchanged rendered config/image/canonical inspect воспроизведена — effective integrity gate OPEN. Mounts-order false-refusal исправлен без исключения полей из hash. Следующий preparatory seam — actual rendered/effective/admin/SQLite enforcement до reserve/claim; не key/live. Main18containers/frozen0020–24/SDK/canonical/secrets сохранены;calls/spend0. Подготовка IN_PROGRESS,G02/S17/S20/S21 NOT_STARTED. Ниже прежние checkpoints сохраняются как история; финальные live/human/SLICE/CI gates не сняты.

**Актуальное продолжение2026-11-18:** новая команда разрешила следующий preparatory seam. ADR136 host gate/composition локально TESTED:fast1389,PG22,affected142PASS,два independent APPROVE/open0. [Отчёт](../increments/G02_candidate_development_host_REPORT.md), [review](../reviews/G02_DEVELOPMENT_HOST_REVIEWS.md). G02 NOT_STARTED/подготовка IN_PROGRESS. Следующий seam — actual isolated topology/effective mutable Bifrost config integrity, затем оставшиеся admission/lifecycle/final/live/human/SLICE gates. Default env listener accounting-only, реальные accounts/tariffs/keys/calls отсутствуют. Source review не доказывает mutable SQLite/admin state. Предыдущая остановка ниже снята только для подготовки этой командой; group consent не выдано.

**Поручение:** владелец, 2026-11-17: продолжить подготовку и реализацию G02 по DEVELOPMENT_GROUPS, восстановить фактический контекст, сохранить локальные изменения; учесть ADR-128/129, не обходить зависимости, допуск модели и SLICE-01; вопросы обсуждать по одному.

**Уточнение владельца 2026-11-17:** «как выполнишь подготовительные шаги обязательно скажи. G02 без моего согласия не начинай». Продолжается только подготовка внешних предпосылок. Старт S17/S20/S21 требует нового явного согласия владельца после отчёта о готовности; прежнее поручение не использовать как автоматическое разрешение перехода в продуктовую группу.

**Статус группы:** NOT_STARTED, ожидает нового согласия владельца. **Подготовка G156:** IN_PROGRESS. S17/S20/S21 NOT_STARTED, вход в S17 также требует завершённого SLICE-01. Ближайшая работа — [Flash admission](G02_FLASH_ADMISSION.md). Когда подготовительные условия будут действительно выполнены, отдельно уведомить владельца; локально TESTED guard не выдавать за полную готовность подготовки.

**Завершающий preparatory checkpoint ADR135,2026-11-18:** отдельная local patch/build того же Bifrost2.5.1 для actual terminal SSE fingerprint bug. SDK автор g02_prerequisite_plan, build/fixture автор g02_python_contract_review, Go/security reviewers проверяют только чужое. Root shared docs/integration. SDK exactec453… normal/race11parents+134subPASS,vet exit0,два independent APPROVE. Build source/fresh acquisition/image+actualbinary provenance и24patched+8official nativecases PASS, два final source review APPROVE/open0; wholeG156 NOT VERIFIED. Runtime очищен/освобождён, owncaches оставлены. По просьбе владельца остановиться до новой команды; завтра начать с конкретного host composition/gate scope по HANDOFF, SDK не повторять без новой причины. Official image/main stack/strict adapter/required metadata не менять. Modelcalls0, G02 NOT_STARTED.

**Metadata decision принято и реализовано по делегированию владельца:** ADR131, активный внутренний контракт0.2. Fingerprint VALUE обязателен для expectation; ABSENT/NULL остаются candidate facts. Parser/schema/direct construction совпадают, прежний0.1 не принимается активным parser. Повторного вопроса optional/mandatory нет. Live values/evidence/Bifrost/profile approvals остаются до включения. Durable foundation0020–0022 локально TESTED; полный G156 NOT VERIFIED, mode expand0023 локально TESTED.

## Git и сохранность работы

- Worktree: текущий репозиторий AI-RES; исполнитель/координатор — основной Codex. Другие группы не поручены.
- Проверенная база/HEAD: `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, merge PR33. История содержит G01/S18 и S19; G01 не переоткрывается.
- Исходная ветка: `docs/ncp16-flash-identity-exception`; создана `feat/g02-manager-tools-planning` от того же HEAD с сохранением всего исходного diff.
- До начала: 19 изменённых tracked + 10 новых файлов по NCP16/OD19 (ADR128/129), docs/architecture и manifest pointer включены. Это существующая работа владельца; не включать автоматически в commit. Канонические файлы, зеркало и прежние отчёты этой сессией не редактируются. HANDOFF/STATUS/ECC дополняются без удаления исходных записей.
- Общий PR/SHA/новое Linux CI: отсутствуют. Исторические PASS G01/S16 не относятся к новому diff.

## Порядок и зависимости

| Работа | Источники | Проверенные предпосылки / оставшиеся условия | Статус |
|---|---|---|---|
| G-156: технический допуск Flash | ADR128; DOC076 §3.1/7; [план](G02_FLASH_ADMISSION.md) | Контракт0.2 и durable foundation0020–0022 локально проверены;0023 mode expand локально TESTED. Ledger/candidate runner/live evidence и approvals ещё нужны | IN_PROGRESS; полный механизм NOT VERIFIED |
| SLICE-01, внешний мини-этап | ADR115; TEST_DATA_SOURCES | Технический S16 DONE; нужен допущенный Flash, проверенная лицензия выбранного источника и отдельный бюджет SLICE. Общий потолок 10 USD допуска на SLICE не переносится | NOT_STARTED / BLOCKED |
| S17 | [промпт](../increments/prompts/S17_tool_registry_tool_gateway.md) | S07/S12, ARCH-01 DONE; SLICE-01 ещё не выполнен | NOT_STARTED / PENDING_DEPS |
| S20 | [промпт](../increments/prompts/S20_project_epic_intake_manager.md) | S12/S15/S19 DONE; по порядку группы после S17. До первого producer нужны OD19 enforcement и G107 reconciler+allowlist | NOT_STARTED / PENDING_DEPS |
| S21 | [промпт](../increments/prompts/S21_plan_task_orchestration.md) | Внутренний реализованный контракт S20 в общей ветке; replay/versioning/plan gates остаются | NOT_STARTED / PENDING_DEPS |

Внешняя предпосылка требует своего DONE до зависимого Sxx. Реализация → общая отладка → независимое review/исправления → финальные gates и один PR группы по AGENTS §11/ADR127. Отдельный полный pre-pr/CI/PR каждого внутреннего Sxx не требуется. Подготовка G-156 не разрешает пропустить SLICE-01, перейти в другую группу или назвать модель APPROVED.

## Scope и владение

Текущая подготовка включает pure identity contract0.2 и durable admission foundation0020–0022: четыре технические таблицы, immutable evidence, pending barrier, sticky block, security audit, PG/restart/logical restore tests. Следующий0023 добавляет честный observed profile mode/readonly reference без fake pin; локально проверен на PostgreSQL, без product wiring. Product factory/routing/immutable transport guards не включаются, реальные profile/approval/grant/classification seeds не создаются.

Основной исполнитель ведёт shared tests/snapshot и implementation-документы. `g02_prerequisite_plan` получил ограниченное авторство новых persistence/mode компонентов; отдельные read-only database/Python и security reviewers проверяют чужой код blind-first. ADR132 фиксирует durable foundation, не выдаёт human authority и не меняет BASELINED.

Runtime использовался только последовательно в disposable PostgreSQL Testcontainers. Основной Compose stack/volumes/данные/secrets не менялись; платных вызовов0.После scoped0023 tests исполнитель освободил runtime; root последовательно завершил snapshot и actual drift/upgrades, контейнеры тестов завершены. Это владение рабочим runtime, не требование для следующей сессии: перед возобновлением проверить фактически работающие процессы/контейнеры. Сброс volumes и ротация существующих secrets не разрешены. Внешнему исследованию передавались только общие официальные DeepSeek/PostgreSQL вопросы без проектного содержимого.

## Gates и продолжение

Для чистого validator выполнены fast/contracts и независимое review; для0020–0022 добавлены реальные PG32cases и profile/RLS/grants/failure/concurrency/process/logical restore coverage. Initial full backend1901passed/3legacy failures, после точечных test fixes affected+upgrade/drift11passed; полного green повторно нет.0023 отдельно:56PGpassed,fast957passed,actual drift/upgrades7passed,два reviewers APPROVE. Pre-pr/Linux CI итоговой подготовки ещё не выполнены; локальные checkpoints не являются real-provider approval или VERIFIED G156. Все применимые G1–G9 и DoD будущих Sxx сохраняются. Подробная readiness matrix — в плане подготовки.

Первый внешний operational blocker live candidate PoC — безопасный setup provider key после готового плана расходов. Значение ключа не запрашивать в чате. Состав обязательной identity metadata выбран по делегированию владельца (ADR131); точные реальные значения/evidence проходят человеческую приёмку до включения. Список классификаций также нужен перед включением, а не для начала отключённой разработки. Первый ответ не auto-approval. Технические выборы OD19 повторно владельцу не возвращать; PoC ADR129 и G107 остаются обязательными до реального producer S20.

Identity checkpoint — [первый отчёт](../increments/G02_flash_admission_preparation_REPORT.md); persistence/current checks — [durable report](../increments/G02_model_admission_persistence_REPORT.md) и [review](../reviews/G02_MODEL_ADMISSION_REVIEWS.md). При остановке HANDOFF/STATUS обновляются; незакрытые G156/SLICE/OD19 не теряются. При DONE всей G02 — остановка до нового поручения.

**Текущий preparatory checkpoint (ADR133):** ledger локально TESTED,0024 frozen; PG40cases/process+restore,fast957,actual drift/upgrades/security6passed,два independent APPROVE. [Отчёт](../increments/G02_flash_paid_ledger_REPORT.md). Runtime tests завершены; следующие runtime действия предварительно проверить по фактическому состоянию. Новых real accounts/tariffs/keys/calls нет. Ближайшая незавершённая часть — candidate egress/runner; read-only план A/privateTLS backend claim остаётся PROPOSED/NOT_IMPLEMENTED/NOT_SECURITY_ACCEPTED. Подготовка не завершена, о старте G02 вопрос не ставится.

**ADR134, checkpoint2026-11-18:** private backend service/ASGI + codec/client/relay/TLS + native profileless probe + runner реализованы и локально TESTED. Fast1281passed,runner43passed с14realPG, independent security re-review APPROVE/open0. Actual Bifrost8passed включает negative terminal fingerprint loss: SSE compatibility BLOCKED; TEXT/JSON/TOOL fake-upstream проходят. Root владеет relay/client/TLS/tests/docs/contracts; g02_prerequisite_plan автор control/runner, g02_python_contract_review автор codec/probe/Bifrost fixture. General cross-review только чужих файлов, g02_scope_security_review независимый security reviewer всех. Concrete trusted host/freshness/product wiring/owner lifecycle/key/live/SLICE остаются. [Отчёт](../increments/G02_candidate_egress_preparation_REPORT.md), [review](../reviews/G02_CANDIDATE_EGRESS_REVIEWS.md). Main stack не перезапускался, frozen0020–24 неизменны, modelcalls/spend0. Portable fixture own-image build+21cases PASS, security delta APPROVE/open0; временные containers/network удалены, runtime освобождён. При возобновлении проверить фактическое состояние. Подготовка IN_PROGRESS, G02 NOT_STARTED.
