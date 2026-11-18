# G156 / ADR140 — independent identity-operator reviews

2026-11-18, root author/integrator/runtime operator; reviewers read-only,
blind-first, author report отсутствовал до выводов. Scope:0026, isolated operator,
shared ADR139 digest helper, role provisioning, grants/parameter ACL audit,
snapshot tooling и unit/PG tests. [Точные10hashes](G02_IDENTITY_OPERATOR_CODE_HASHES.json).

`executor_plan`: ECC planner/architect reconnaissance, затем independent general/
Python/database/test source review root-кода. `executor_normative`: canonical/
Registry/manifest/localref reconnaissance, затем independent security/architect/
silent-failure source review. Root не подменяет reviewers самопроверкой.

Pre-apply оба нашли2MEDIUM: inherited operator EXECUTE не ловился аудитом;
SQL NULL admissionGeneration обходил сравнение. Исправлены effective privileges/
membership audit и IS DISTINCT FROM; direct actualPG negatives добавлены. LOW:
ведущий profileFK index добавлен, дублирующий userFK удалён до first successful
apply. Оба design verdict APPROVE для disposablePG после исправлений.

Первая попытка apply полностью откатилась: non-superuser owner не имел explicit
SET parameter privilege для CREATE FUNCTION SET custom GUC. Отдельно оба reviewers
одобрили bootstrap owner-only GRANT SET без grant option/ALTER SYSTEM; функция
сохраняет automatic settings restoration. Добавлены exact/effective parameterACL
audit, catalog snapshot и drift negatives. Custom GUC не credential: обычный
runtime SET/set_config сам по себе не даёт owner-targeted RLS или owner membership.

Final security `executor_normative`: APPROVE/open0, проверены8source hashes, frozen
0026 d71b85583b1954e148aa62095aef3f05987019341488f6d9130b623e38bae626.
Final general/database `executor_plan`: APPROVE/open0, те же source/tests и fixes.
CRITICAL/HIGH/MEDIUM0. Проверенные scenarios: explicit owner+session/login binding,
Policy/finalstate, immutable generation, pending/block/replay/audit, role/function/
parameter privilege drift, expiry/reset ordering. Runtime reviewers не запускали.

Root actualPG60PASS, затем finaljoint306PASS включает new61/previous upgrade,
drift/roles/old guard/IAM/restart и дополнительные schema gates. Expanded run
56PASS/4FAIL был test-only clusterACL cleanup bug; исправлен rollback, final
общий набор проходит. Regenerated snapshot1SKIP — не тестPASS; actual drift
проверен повторно в finaljoint. Эти результаты не real model/human approval.

После final executor verdict `executor_plan` отдельно получил авторство только
candidate_launch.py + unit tests. Его verdict относится к root executor, не к
собственному launch-коду; launch требует другого независимого reviewer.
