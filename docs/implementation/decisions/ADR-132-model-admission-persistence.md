# ADR-132 — G156: durable guard до подключения реального профиля

| Поле | Значение |
|---|---|
| Дата / статус | 2026-11-17 / ACCEPTED technical scope; реализация/PG evidence фиксируются в отчёте, полный G156 NOT VERIFIED |
| Основание | Продолжается порученная подготовка G02; ADR128/131 определили observed Flash exception и обязательный fingerprint. Нужен реальный durable механизм перед provider wiring |
| Источники | DOC076§3.1/7; DOC068§1–4; DOC072§7–9/12/14; IAM/Security baseline; AGENTS§5/7/11 |
| Решение | В существующей ai_res_db хранить immutable admission generations, control state, durable call receipts и metadata-only append-only security audit. Только новый forward0020 от0019, без правки применённых revisions. Single-flight per profile для текущего PoC (его план уже concurrency1), не продуктовый SLO |
| Причина durable receipt | Один block+audit в транзакции недостаточен: audit failure откатит block. Begin должен commit durable IN_FLIGHT receipt **до** внешнего вызова. Если finalize/audit падает, unresolved receipt сохраняется и блокирует новый begin после рестарта. Нет придуманного TTL/autoclear |
| Atomicity | Begin/finalize короткие UoW, row lock/CAS control и последовательность под lock. Никаких HTTP/LLM внутри транзакций. Block+terminal receipt+audit коммитятся вместе; controlled refusal после commit. Retry exact finalized evidence не дублирует transition/audit; другое evidence для того же request отвергается |
| Authority | Runtime не создаёт expected generations/не выбирает active generation/не снимает block. Owner/migrator остаётся отдельной технической DB authority; fixture setup — только synthetic tests, не новый production approval путь. Global model profile нельзя утвердить по роли ORGANIZATION_OWNER любого tenant. Exact authenticated owner binding и настоящий human lifecycle ещё нужны перед включением |
| RLS / grants | Новые технические global tables ENABLE+FORCE RLS/default deny, transaction-local exact model-profile context и явные узкие API grants. Никаких runtime-write RLS exemptions или расширения model_profiles UPDATE. GUC — defense-in-depth, не proof caller authorization. Будущий authenticated host обязан авторизовать bound execution/profile до доступа; сейчас endpoint/wiring отсутствуют |
| Audit | Отдельные минимальные model-admission security facts в PostgreSQL, без prompt/response/секретов. Не подставлять фиктивную organization в SqlAuditWriter: global технический контур не маскируется tenant-событием и не является telemetry. Сбой обязательного audit не даёт successful result/новый dispatch |
| Profile model | Existing0017 registry/pin/immutable snapshot/lifecycle/grants не ослабляются этой foundation. Реальный observed Flash profile пока нельзя создать/загрузить прежним pinned DTO без отдельного корректного expand mode. Не заполнять pin alias/fingerprint; никаких реальных profile seeds. FK на существующий registry; PG fixtures явно синтетические, не provider evidence |
| Compatibility | Additive tables/triggers нового механизма; no public API/Worker/event contracts, no baseline acceptance. Старый unconfigured factory/immutable-only Bifrost guard сохраняется. Полный real-profile path остаётся запрещённым |
| Boundaries | Этот срез не реализует human owner setup/approval CLI, honest observed profile mode, durable paid-spend ledger/candidate runner, Bifrost integration, stream aggregation, actual identity approval или SLICE01. Наличие guard не закрывает G146/151/156/OD19/G107 |
| Lifecycle / recovery | Unknown outcome остаётся unresolved без автоматического выпуска нового вызова. Recovery/reapproval — отдельная контролируемая аудируемая операция, не функция self-grant Runtime. Late/stale generation reply не принимается и не снимает новый block. Перед будущим owner lifecycle wiring нужно сериализовать profile lifecycle и control epoch; plain status read не объявлять атомарным revoke enforcement |
| Evidence | Настоящий PostgreSQL16/реальные API grants/RLS; concurrent begin, sticky block/new engine, stale/foreign receipt, audit failure→pending persistence, immutable generations/events, no UPDATE/DELETE/TRUNCATE escalation, empty/previous upgrade/drift и независимые database/security reviews. SQLite/test doubles не засчитываются |
| Риск / пересмотр | Консервативный single-flight снижает concurrency и может требовать явной reconciliation при crash; доступность принесена в пользу fail-closed. Расширение concurrency или runtime approval требует отдельного implementation evidence, не снятия защиты |

## Forward refinements и фактическая граница evidence

0020 `c93e6a7d20b1` был применён только в disposable PostgreSQL tests и после этого не редактируется. Дополнительные исправления — новые ревизии:

- 0021 `d42f7b8c31a6`: даже owner может снять sticky block только одновременно с переходом на новую immutable generation. Runtime по-прежнему не может менять generation/unblock; это не реализация human approval.
- 0022 `e53a8c9d42b7`: удалён только session-dependent `CHECK(writer_role=current_user)`, мешавший logical restore исторических audit rows под другой ролью. DEFAULT current_user/NOT NULL и column INSERT grants, исключающие writer/time, сохраняют защиту runtime от подмены. Данные/поля/история не удаляются. Причина соответствует [ограничениям CHECK PostgreSQL16](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS): проверка одной строки не должна менять результат от сессии.

Targeted PG evidence текущей foundation:32passed/0failed/skipped. Проверены два отдельных Python-процесса (первый завершился перед вторым), сохранение blocked/pending, а также настоящий pg_dump→fresh disposable DB→psql с побайтово/полями совпадающими историческими audit facts. Это не PostgreSQL power-loss/PITR/product recovery drill и не реальное model admission. Общая регрессия и проверка snapshot фиксируются отдельно в отчёте.

**Новая граница поручения владельца:** подготовку продолжать; после её фактического завершения уведомить владельца. G02/S17/S20/S21 не стартуют без нового явного согласия. Реализация этой foundation не означает, что все подготовительные условия выполнены.

Исполнение в общей G02 ветке, без промежуточного PR каждого шага. [План](../groups/G02_FLASH_ADMISSION.md) и [паспорт](../groups/G02_WORK.md); точный diff/проверки — [отчёт durable guard](../increments/G02_model_admission_persistence_REPORT.md). Предусмотренная человеческая приёмка модели/реальных values и обязательный SLICE01 перед S17 сохраняются.

## Последующий0023 expand observed representation

Принятое ADR128 исключение теперь честно представляется в DB без fake pin: identity_mode IMMUTABLE по умолчанию, FLASH_OBSERVED только exact DeepSeek Flash и NULL pin; CHECK IS TRUE сохраняет nonnull invariant остальных профилей. Existing snapshot guard freezes mode, старые профили не переводятся автоматически. Отдельный read-only metadata reference не executable; pinned loader пропускает неподключённый candidate observed и отказывает целиком для active observed. Guard требует explicit observed mode/NULLpin. Новых approval/grants/реальных rows нет, factory/Bifrost guards прежние.

До первого применения0023 два независимых reviewers одобрили DDL/code; real PG56cases, root fast957passed и actual drift/upgrades/legacy7passed. Migration0023 frozen; точный hash/команды — в отчёте. Исходное описание foundation0020–0022 выше историческое, его32tests не приписываются новому expand. Ledger/candidate transport и actual human/model admission по-прежнему не реализованы.
