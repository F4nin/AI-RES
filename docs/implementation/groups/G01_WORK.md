# G01 — Правила и контекст: паспорт работы

**Дата:** 2026-11-17 · **Группа:** DONE при merge PR33 · **S19:** VERIFIED/DONE · **S18:** VERIFIED/DONE (ADR032). S19 closeout PR32 MERGEDd5342ac, contracts checks success.

## Идентификация и полномочия

Поручение: «Реализуй группу G01 по DEVELOPMENT_GROUPS.md с сохранением всех этапов, проверок и правил AGENTS.md.» Разрешён последовательный полный цикл S19 → S18 по AGENTS§10–11/ADR124, с отдельными этапами/отчётами/review/PR/CI. Group definition `docs/implementation/DEVELOPMENT_GROUPS.md` — исходный локальный process-документ, оставлен вне stage commit. Не включены UI/S17/прочие группы, real model/WorkerRun, расширение permissions или human approval требований/Baseline. После DONE группы остановиться.

Исполнитель/координатор общих файлов и runtime — `/root`. Ограниченные авторские подзадачи выполнялись в непересекающихся файлах; это не параллельный запуск других групп. Reviewers read-only, blind-first и не авторы проверяемого кода. Владелец подтвердил единственное активное редактирование. Worktree `/Users/ekaterinamarusova/AI-RES-Workspace/AI-RES`.

Начальная fetch-проверенная база main745e7d989a75b5457497742e371f60aa8e33ffc0. До G01 существовали12 governance изменений: AGENTS, ADL, HANDOFF, DECISIONS_PENDING, ECC_USAGE, ROADMAP, STATUS, prompt index, CONTEXT_RETENTION, tooling README, DEVELOPMENT_GROUPS, GROUP_WORK_TEMPLATE. Они сохранены, shared file hunks разделены через index без reset/stash/перезаписи. Original snapshots `/tmp/g01-original-worktree.json` и `/tmp/g01-s19-post-publish-original.json` — временная страховка, не постоянное evidence; текущий original diff остаётся в рабочем дереве.

## План и зависимости

| Этап | Источники / evidence | Зависимости | Реализация / готовность | Доставка |
|---|---|---|---|---|
| S19 | [Промпт](../increments/prompts/S19_context_package_versioning.md), [отчёт](../increments/S19_context_package_versioning_REPORT.md), [review](../reviews/S19_IMPLEMENTATION_REVIEWS.md), [ADR125](../decisions/ADR-125-context-manifest.md) | S06/S07 DONE: существующие reports, PR5/6 MERGED, Git/STATUS; canonical74/74 | VERIFIED/DONE explicit-ref slice; production caller отсутствует, G157 | [PR31](https://github.com/F4nin/AI-RES/pull/31) MERGED15:17:13UTC; head a2752087d8a40189a44667ef770c0f3665301942, merge99e5ec15cfb2343022cd972f0b66e4adfccbe435; exact-head и post-merge CI success |
| S18 | [Промпт](../increments/prompts/S18_rules_registry_rules_engine.md); read-only план/architecture assessment подготовлены | S06/S07 DONE повторно проверены, S19 source/closeout доставлены | VERIFIED/DONE; localpre-pr+186targeted+3reviews+all8sourceLinuxchecksSUCCESS | [PR33](https://github.com/F4nin/AI-RES/pull/33), head7dd8475 + closing docs delta; merge/checks см. PR metadata |

## Выполненный S19 и gates

Trusted internal build/retrieve, strict immutable manifest exact Requirement/Source/Artifact refs, SHA256/provenance, module-owned metadata ports, current ACL/replay, atomic audit/HMAC idempotency, CAS и безопасный failed-build audit. Нет public route/event/model/нового grant. Nullable expand0018 (`a41c8f92d603`) добавляет manifest и server-stamped xid8 seal; legacy snapshots не переписываются, SAVEPOINT работает. G72 sealing часть исправлена; остальное G72/G73 остаётся открытым.

Local full pre-pr exit0: backend1565/541warnings,infra369,отдельныйruntime148,contracts22,Renovate10,PoC19, failed/errors/skipped0. Targeted107=20builder+13metadata+70manifest+1previous-migration+3schema; fast695/14kept, audit0knownvulns, digest21/0mismatch. Existing secrets24/0written, volumes сохранены; OTel/current authorization tests реальны, source text/credentials в result/audit/telemetry не включены. Mutation прежнего lock-order обнаружена2/2 (DeadlockDetected), production source не менялся.

Три отдельные independent final reviews APPROVE/openfindings0: code/Python/architecture/types/tests, security/silent-failure, DB/silent-failure. Устранены duplicate refs, missing failure audit, lock inversion; docs MEDIUM duplicate G157 также исправлен. Exact hashes и ECC actual methods — review/report/ECC_USAGE. Native Claude commands/hooks не запускались.

Все8 source-head push/PR checks success: ci44110008365/44110036973, contracts44110008513/44110037177. Отдельные [post-merge ci44112572923](https://github.com/F4nin/AI-RES/actions/runs/44112572923)/[contracts44112573004](https://github.com/F4nin/AI-RES/actions/runs/44112573004) success: backend1565,infra-static221,runtime148,PoC19,contracts22,Renovate10; failed/errors/skipped0; дополнительные audit/digest/SBOM/security gates success. Third-party CVE report-only G24 не закрыт. Fetch/diff a2752087 vs99e5ec1 exit0: identical trees.

## Владение файлами и средой

Root владеет source integration/Make/CI/manifests/migration head/STATUS/HANDOFF/ADL/ECC/traceability/snapshot. Новые ADR резервирует root. Runtime общий, root выполняет Compose/migrations последовательно; reviewers его не меняют. S19 штатно пересобрал API и применил expand0018 в проверенном dev/test, без удаления volumes/данных/существующих secrets. Перед S18 сверить фактический head и совместимость данных; Testcontainers отдельны. Production/bootstrap/secret rotation/destructive actions и новые model расходы не разрешены.

G157: будущая вызывающая команда должна отдельно авторизовать свой action; read checks builder определяют inclusion/read metadata. Перед production caller требуется pool-pressure/saturation assessment (здесь не измерено). S18 сохранит отдельную границу Rules Engine/Policy, unknown packaged lifecycle actions DENY, без новых production grants/catalogue.

## Исторический checkpoint перед S18: рамки предварительного плана

Read-only planner/TDD/test-analysis и architect/security assessment не запускали код этапа. План: ограниченный typed declarative DSL без eval/network/files; complete applicable SYSTEM/ORG/PROJECT registry, deterministic immutable rule/fact/time snapshots; persisted evaluations/audit; human exact-version lifecycle/исключения; no SYSTEM override, higher-level allowance и finite expiry. Использовать I0 NO_IMPACT → I4 CRITICAL для minimumImpactClass; не смешивать с тремя processing категориями. UNKNOWN facts fail closed, исторический replay не permission. Approval требует реальных human session+Policy; fixture-only constrained PolicyConfig для PG acceptance, packaged unknown actions DENY. OD14/роли/активный системный каталог не изобретаются и остаются условиями будущего admission.

## Исторический checkpoint после S19; текущая остановка — раздел «Закрытие G01»

S19 source PR31 и closeout PR32 завершены. Текущая ветка feat/s18-rules-registry-engine отd5342ac содержит S18 DSL/engine/registry/persistence/human lifecycle/exceptions/current authorization/replay. Targeted186passed и3independentAPPROVE; финальный pre-pr/Linux/delivery продолжаются. Дополнительный отдельный docs-only PR не создаётся: evidence входит в S18 PR. При blocker сохранить evidence и остановить затронутую работу; другую группу не выбирать. После DONE обоих этапов проверить общий результат, сохранить links/limitations и остановиться.

Время локальных suites и Linux jobs сохранено в stage report/CI; общего корректного замера группового ускорения нет. Ручное уточнение владельца об exclusive editing не расширяло scope. Конфликты shared user-doc hunks разрешены сохранением вне stage commit, не перезаписью.


История старта S18: branch feat/s18-rules-registry-engine от проверенного интегрированного d5342ac915303a1de3d15f3a911b11243d656dc3. PR32 docs-only head6d33992/contracts44116381062/44116483451success, merged15:40:53UTC. Источники S18 перечитаны, CODE root/план+архитектура согласованы в scope. ADR126 резервирует root. Pure inputs/DSL и engine/validation — два ограниченных непересекающихся автора с TDD; root owns services/composition/integration/shared docs/snapshot; отдельный database author владеет migration/repositories/storage tests, независимый новый reviewer не автор. Новых permissions/catalogue не активировать; Policy fixture-only для acceptance, packaged unknown actions DENY.


Исторический checkpoint перед Linux CI: ADR126, migration0019 b621f4d8a905, trusted Context metadata provider1.0, exact rule/fact/time/exception snapshots, human lifecycle with defaultdeny Policy/separationNone, no SYSTEM override. Targeted186=141unit+45PG passed;3independent reviewers APPROVE/openfindings0. Исправлены2MEDIUM: evaluation context/scope mismatch и org-report read via projectgrant. Final hashes/report/review: [S18 report](../increments/S18_rules_registry_rules_engine_REPORT.md), [review](../reviews/S18_IMPLEMENTATION_REVIEWS.md). Fullpre-pr exit0 (backend1749,infra369,runtime148,contracts22,Renovate10,PoC19); finaltargeted186 иfast836/15contracts. Linux/delivery pending; G01 ещё неDONE. Original12 owner governance changes excluded. G157/G158 integration admission ограничения сохранены.

Исторический checkpoint создания PR: source S18:7dd847526fb7d713b6149d1dc37b12d0e9999ada,[PR33](https://github.com/F4nin/AI-RES/pull/33); exact source-head Linux push/PR ci44125407264/44125456727,contracts44125407362/44125456894 были запущены; итог SUCCESS зафиксирован в следующем разделе. Documentation closeout вошёл в тот же PR; исходные12 governance файлов не публикуются.

## Закрытие G01

S19 и S18 VERIFIED/DONE, включая их отдельные reports/reviews/PR и gates. S18 source7dd8475 all8Linuxpush/PRchecksSUCCESS: backend1751/541warnings,infra-static221,runtime148,PoC19,contracts22,Renovate10;failed/errors/skipped0. Дополнительные audit/digest/hadolint/actionlint/secret scan/SBOM jobs SUCCESS, G24 report-only остаётся. Final docs-only delta входит в тот же PR33, product tree не меняется; новые checks проверяются по точному finalhead до merge. При mergePR33 этот паспорт закрывает G01 DONE; итоговый mergeSHA/post-mergeCI проверяются по PR metadata/Git, а не записываются self-reference в commit. После доставки остановиться, другие группы не начинать. Original12 owner governance changes сохранены вне stage commits. G157/G158 и production/model/security-owner release approvals остаются отдельными условиями будущих этапов.
