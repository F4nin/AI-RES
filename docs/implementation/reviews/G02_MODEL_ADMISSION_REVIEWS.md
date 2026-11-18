# G156: независимые review durable admission foundation

**Дата:** 2026-11-17. Проверен HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff. Это review отключённой подготовки, не real-provider approval или VERIFIED G156. Авторы не рецензировали собственные изменения; оба проверяющих работали read-only, blind-first до авторского отчёта. Docker/runtime они не запускали.

## Scope 0020–0022

Новые admission tables/grants/RLS/triggers, `modules/model_registry/admission.py`, PG cases state/concurrency/audit failure/migrations/process restart/logical restore и точечные изменения legacy gates. Root и отдельный исполнитель создавали код и запускали тесты; reviewers оценивали чужой фактический код и тесты.

| Проверяющий / компетенции | Результат |
|---|---|
| `g02_python_contract_review`: database/Python/code/tests | Final APPROVE, открытых findings0 |
| `g02_scope_security_review`: security/code/fail-closed | Final APPROVE, открытых findings0 |

Исправлены до final verdict:

- MEDIUM: pending barrier только текущей generation мог пропустить unresolved старый receipt. До первого применения0020 установлен single-flight по всему profile; regression проверяет owner advance после audit failure и отказ нового engine.
- MEDIUM: session-dependent `CHECK(writer_role=current_user)` ломал восстановление исторического audit actor под другой ролью. Forward0022 удаляет только CHECK, сохраняя DEFAULT/NOT NULL и column grants против подмены. Реальный logical dump/restore проверен автором, reviewer runtime себе не приписывает.
- LOW: описание restart/restore ограничено process loss/logical restore; physical/power-loss/PITR/product recovery не заявляются.

Final legacy-test delta отдельно APPROVE у database/Python reviewer: закрытый catalogue расширен ровно четырьмя таблицами; `TRUNCATE … CASCADE` доходит до защитного trigger; точное исключение одного DROP CHECK0022 с count1 сохраняет остальные offline DDL bans.

## 0023: отдельный последующий expand

До первого применения security reviewer независимо выдал DDL APPROVE/open0: новый immutable identity_mode, nullable pin только для exact Flash observed mode, CHECK IS TRUE закрывает SQL NULL loophole, old pin CHECK/snapshot trigger/grants сохранены, seeds отсутствуют. Root отдельно просмотрел DDL и добавил только точное второе исключение DROP NOT NULL с count1; общий DROP запрет остаётся.

Final0023: оба независимых reviewers APPROVE/open0. Database/Python reviewer проверил frozen SHA256 `2e8ee8f916cd2c0d16f8e4f844b5dd441d77d2eae898a94b7371b3f2e83163d2`, mode/loader/guard и сопутствующие tests/sharedfixture/два exact DROP exceptions. Security reviewer полностью просмотрел DDL/readonly DTO/pinnedloader/guard и16new PGcases. Никаких author report или собственных runtime запусков. Реальные PG56cases выполнял автор, root отдельно проверил fast957 и drift/upgrades/legacy7; результаты не приписываются reviewer. Snapshot/drift не входили в независимый verdict0023; root просмотрел generated diff вручную и запустил actual drift отдельно.

## Ограничения

Global owner authentication/approval lifecycle, candidate permit/ledger/runner, Bifrost/live stream, product host authorization и реальное model approval не реализованы этим foundation. Profile lifecycle/control epoch ещё нужно координировать до product wiring. G02/S17/S20/S21 не начаты; после подготовки нужно новое согласие владельца. Полный pre-pr и Linux CI текущего diff ещё не выполнялись.
