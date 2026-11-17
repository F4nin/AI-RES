# G01 — Правила и контекст: паспорт работы

**Дата:** 2026-11-17 · **Группа:** IN_PROGRESS · **S19:** VERIFIED/DONE · **S18:** NOT_STARTED (следующий после доставки S19 closeout).

## Идентификация и полномочия

Поручение: «Реализуй группу G01 по DEVELOPMENT_GROUPS.md с сохранением всех этапов, проверок и правил AGENTS.md.» Разрешён последовательный полный цикл S19 → S18 по AGENTS§10–11/ADR124, с отдельными этапами/отчётами/review/PR/CI. Group definition `docs/implementation/DEVELOPMENT_GROUPS.md` — исходный локальный process-документ, оставлен вне stage commit. Не включены UI/S17/прочие группы, real model/WorkerRun, расширение permissions или human approval требований/Baseline. После DONE группы остановиться.

Исполнитель/координатор общих файлов и runtime — `/root`. Ограниченные авторские подзадачи выполнялись в непересекающихся файлах; это не параллельный запуск других групп. Reviewers read-only, blind-first и не авторы проверяемого кода. Владелец подтвердил единственное активное редактирование. Worktree `/Users/ekaterinamarusova/AI-RES-Workspace/AI-RES`.

Начальная fetch-проверенная база main745e7d989a75b5457497742e371f60aa8e33ffc0. До G01 существовали12 governance изменений: AGENTS, ADL, HANDOFF, DECISIONS_PENDING, ECC_USAGE, ROADMAP, STATUS, prompt index, CONTEXT_RETENTION, tooling README, DEVELOPMENT_GROUPS, GROUP_WORK_TEMPLATE. Они сохранены, shared file hunks разделены через index без reset/stash/перезаписи. Original snapshots `/tmp/g01-original-worktree.json` и `/tmp/g01-s19-post-publish-original.json` — временная страховка, не постоянное evidence; текущий original diff остаётся в рабочем дереве.

## План и зависимости

| Этап | Источники / evidence | Зависимости | Реализация / готовность | Доставка |
|---|---|---|---|---|
| S19 | [Промпт](../increments/prompts/S19_context_package_versioning.md), [отчёт](../increments/S19_context_package_versioning_REPORT.md), [review](../reviews/S19_IMPLEMENTATION_REVIEWS.md), [ADR125](../decisions/ADR-125-context-manifest.md) | S06/S07 DONE: существующие reports, PR5/6 MERGED, Git/STATUS; canonical74/74 | VERIFIED/DONE explicit-ref slice; production caller отсутствует, G157 | [PR31](https://github.com/F4nin/AI-RES/pull/31) MERGED15:17:13UTC; head a2752087d8a40189a44667ef770c0f3665301942, merge99e5ec15cfb2343022cd972f0b66e4adfccbe435; exact-head и post-merge CI success |
| S18 | [Промпт](../increments/prompts/S18_rules_registry_rules_engine.md); read-only план/architecture assessment подготовлены | S06/S07 повторно проверить перед стартом, завершить docs-only S19 closeout | NOT_STARTED; исходные зависимости READY, новых owner-блокеров механизма не выявлено | — |

## Выполненный S19 и gates

Trusted internal build/retrieve, strict immutable manifest exact Requirement/Source/Artifact refs, SHA256/provenance, module-owned metadata ports, current ACL/replay, atomic audit/HMAC idempotency, CAS и безопасный failed-build audit. Нет public route/event/model/нового grant. Nullable expand0018 (`a41c8f92d603`) добавляет manifest и server-stamped xid8 seal; legacy snapshots не переписываются, SAVEPOINT работает. G72 sealing часть исправлена; остальное G72/G73 остаётся открытым.

Local full pre-pr exit0: backend1565/541warnings,infra369,отдельныйruntime148,contracts22,Renovate10,PoC19, failed/errors/skipped0. Targeted107=20builder+13metadata+70manifest+1previous-migration+3schema; fast695/14kept, audit0knownvulns, digest21/0mismatch. Existing secrets24/0written, volumes сохранены; OTel/current authorization tests реальны, source text/credentials в result/audit/telemetry не включены. Mutation прежнего lock-order обнаружена2/2 (DeadlockDetected), production source не менялся.

Три отдельные independent final reviews APPROVE/openfindings0: code/Python/architecture/types/tests, security/silent-failure, DB/silent-failure. Устранены duplicate refs, missing failure audit, lock inversion; docs MEDIUM duplicate G157 также исправлен. Exact hashes и ECC actual methods — review/report/ECC_USAGE. Native Claude commands/hooks не запускались.

Все8 source-head push/PR checks success: ci44110008365/44110036973, contracts44110008513/44110037177. Отдельные [post-merge ci44112572923](https://github.com/F4nin/AI-RES/actions/runs/44112572923)/[contracts44112573004](https://github.com/F4nin/AI-RES/actions/runs/44112573004) success: backend1565,infra-static221,runtime148,PoC19,contracts22,Renovate10; failed/errors/skipped0; дополнительные audit/digest/SBOM/security gates success. Third-party CVE report-only G24 не закрыт. Fetch/diff a2752087 vs99e5ec1 exit0: identical trees.

## Владение файлами и средой

Root владеет source integration/Make/CI/manifests/migration head/STATUS/HANDOFF/ADL/ECC/traceability/snapshot. Новые ADR резервирует root. Runtime общий, root выполняет Compose/migrations последовательно; reviewers его не меняют. S19 штатно пересобрал API и применил expand0018 в проверенном dev/test, без удаления volumes/данных/существующих secrets. Перед S18 сверить фактический head и совместимость данных; Testcontainers отдельны. Production/bootstrap/secret rotation/destructive actions и новые model расходы не разрешены.

G157: будущая вызывающая команда должна отдельно авторизовать свой action; read checks builder определяют inclusion/read metadata. Перед production caller требуется pool-pressure/saturation assessment (здесь не измерено). S18 сохранит отдельную границу Rules Engine/Policy, unknown packaged lifecycle actions DENY, без новых production grants/catalogue.

## Следующий S18: рамки предварительного плана

Read-only planner/TDD/test-analysis и architect/security assessment не запускали код этапа. План: ограниченный typed declarative DSL без eval/network/files; complete applicable SYSTEM/ORG/PROJECT registry, deterministic immutable rule/fact/time snapshots; persisted evaluations/audit; human exact-version lifecycle/исключения; no SYSTEM override, higher-level allowance и finite expiry. Использовать I0 NO_IMPACT → I4 CRITICAL для minimumImpactClass; не смешивать с тремя processing категориями. UNKNOWN facts fail closed, исторический replay не permission. Approval требует реальных human session+Policy; fixture-only constrained PolicyConfig для PG acceptance, packaged unknown actions DENY. OD14/роли/активный системный каталог не изобретаются и остаются условиями будущего admission.

## Продолжение и остановка

Текущая ветка docs/s19-closeout от99e5ec1 меняет только Markdown/evidence; её точные HEAD/PR/CI/доставку проверить через Git. После closeout автоматически перейти к S18 из проверенной интегрированной базы, сохраняя G1–G9/полный pre-pr/Linux CI/independent review. Паспорт обновить при старте S18. При blocker сохранить evidence и остановить затронутую работу; другую группу не выбирать. После DONE обоих этапов проверить общий результат, сохранить links/limitations и остановиться.

Время локальных suites и Linux jobs сохранено в stage report/CI; общего корректного замера группового ускорения нет. Ручное уточнение владельца об exclusive editing не расширяло scope. Конфликты shared user-doc hunks разрешены сохранением вне stage commit, не перезаписью.
