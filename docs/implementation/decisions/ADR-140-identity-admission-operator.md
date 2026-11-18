# ADR-140 — isolated identity-admission operator

**Дата:** 2026-11-18. **Статус:** ACCEPTED technical scope в порученной подготовке
G156, implementation/review IN_PROGRESS. G02/S17/S20/S21 NOT_STARTED.

## Решение

После ADR139 реализовать отдельный backend-only executor человеческого решения
ACCEPT_IDENTITY либо BLOCK. Identity acceptance сохраняет новую immutable generation
и может снять sticky block только при отсутствии IN_FLIGHT receipts. BLOCK сохраняет
все receipts. Профиль, его status и первоначальный approver/time не изменяются:
полная Bifrost/security/profile приёмка остаётся отдельной предпосылкой включения.
Основания: DOC076 v1.1 §3.1/7, IAM v1.5 §8, Auth v1.1 §5/6, DOC068 §1.13,
Blueprint §7/9/14, owner OD01/21 decision2026-11-14 и ADR132/138/139.

NOLOGIN operator group не получает memberships, credentials, API inheritance или
табличных прав. Только EXECUTE двух exact SECURITY DEFINER routines, owner NOLOGIN,
search_path=pg_catalog, schema-qualified SQL, function-local migration_mode=on.
Обычным API/PUBLIC/runtime EXECUTE закрыт. Owner-only immutable binding связывает
session_user login с exact organization/user/profile; таблица изначально пустая.
Provisioning реального login/binding/ключа/профиля этим срезом не выполняется.

Snapshot routine заново проверяет binding, live user/member/factor/session,
READ COMMITTED/origin/exact lifecycle fence и полный profile/control/current/pending.
Lock order membership→user→factor→session→fence→control. После ожиданий повторно
проверяется время. Executor сверяет ADR139 digests, независимо вызывает отдельный
Policy action вне UoW; final snapshot и mutation используют одну короткую operator
UoW. Mutation вновь читает snapshot, сравнивает exact state и атомарно записывает
generation/block + отдельный append-only global decision audit. При любой ошибке
нет частичного изменения. Operator credential — trusted boundary; SQL routine не
подменяет application Policy или provenance/capability проверки evidence.

Decision UUID и canonical command hash дают bounded replay без повторной записи;
replay снова требует live owner/binding/Policy. Другой command с тем же UUID отвергается.
Audit хранит exact actor/org/session/profile, policy/review/evidence hashes,
generation/action/reason/correlation и фактический session_user, без payload/секретов.
Review/decision metadata не reusable grant и не разрешение model dispatch.

Новая additive0026; frozen0017/0020–25 не править. Exact definer audit allowlist
проверяет signatures/owner/settings/ACL; неизвестные definers остаются нарушением.
До first apply необходимы independent database/security DDL reviews. Проверки:
actual disposable PG роли/negative/races/replay/rollback/upgrades/drift, fast,
contracts/secrets и два final independent reviews. Full G156 pre-pr/LinuxCI/live/
human/SLICE остаются общей приёмкой подготовки; этот seam не выдаёт VERIFIED.
