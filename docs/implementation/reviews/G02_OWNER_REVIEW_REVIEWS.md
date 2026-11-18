# G156 / ADR139 — independent owner-review source reviews

**Дата:** 2026-11-18. Ветка `feat/g02-manager-tools-planning`, HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff.
[Final4 hashes](G02_OWNER_REVIEW_CODE_HASHES.json).

## Независимость и способ применения ECC

Root — единственный автор кода/tests/документов и оператор PostgreSQL. Прочитанные
python-testing/verification-loop использованы как checklists; native Claude hooks/
commands, продуктовый QA Worker и human/security owner не имитировались.

`owner_plan` — отдельный read-only planner/architect по actual interfaces/authority,
затем независимый general/Python/database/pr-test source reviewer. Прочитал ECC
planner/architect/code-reviewer/python-reviewer/database-reviewer/pr-test-analyzer.
`owner_normative` — отдельная normative reconnaissance, затем blind-first security/
architect/silent-failure source reviewer, с прочитанными ECC instructions.
Ни один не писал файлы, не запускал tests/Docker и не читал авторский отчёт до
выводов. Reviewers исследовали исходники/IAM/schema/Policy/ADR; runtime — только root.

До кода обе роли подтвердили полезный ограниченный seam: точный owner binding
дополняет Policy, но не даёт runtime/migrator credential. Полный lifecycle executor
требует отдельной защищённой composition и поэтому остаётся OPEN.

## Initial findings и исправления

`owner_plan`: WARNING, два MEDIUM, CRITICAL/HIGH0.

1. Сессия могла истечь во время ожидания ADR138 fence после первой live проверки.
   Исправлено final subject/session/MFA и scheduled deprecation recheck после
   model/control/current/pending reads, до policy audit. Добавлен реальный waiter
   expiry case. Физическая валидность во время audit/commit не обещается.
2. Порядок session SHARE → factor SHARE создавал цикл с MFA reset/verify, где
   factor обновляется до revoke/rotation session. Исправлен factor → session.
   Новый controlled двухсоединённый PG interleave воспроизвёл pre-fix session lock
   timeout; corrected suite проверяет отсутствие этого цикла и безопасный отказ.

`owner_normative` первоначально APPROVE без найденного source defect; предложил
LOW evidence enhancement active subject mutation, replacement session/policy,
unsupported targets. Добавлены все перечисленные cases, plus exact same-org
другой owner, high-precision complete-row snapshot и unrelated profile isolation.
Его первоначальный verdict не подменяет findings другого reviewer; оба повторно
проверили их исправления и final delta.

## Final verdict

Оба независимых reviewers: **APPROVE / open findings0**, сверили4final hashes.
Подтвердили exact owner/profile/default deny, DB-derived MFA/status, Policy вне
транзакций, повтор subject после ожидания, lossless full profile hash, exact actual
observation/expectation hashes и generation/block/pending binding без изменения
admission. Shared helper сохраняет прежний ADR138 SQL/порядок. Root дополнительно
обратил extraction и получил точный initial admission.py SHA256.

После runtime-neutral docstring уточнения оба повторно проверили source SHA
`809fe749e07496ace91935411fc531b1715ed057c25bb18fd59d0f19de036650` и ADR139/prompt:
**APPROVE / open0**. Остальные3hashes прежние. Отчёт/контекст проверяются отдельно
после первичного blind-first source verdict; это не дополнительное runtime evidence.

Scope verdict: preparation/revalidation identity-review material, без approval DML/
grants/routes/config enabling. Материал не human decision/provenance attestation/
dispatch capability. Реальные Bifrost/profile acceptance, полный G156, pre-pr/Linux
CI и SLICE этим review не подтверждаются. Root-команды/counts/limitations — в
[отчёте](../increments/G02_owner_review_binding_REPORT.md).

После blind-first source verdict `owner_plan` отдельно прочитал финальный отчёт,
protocol/hashes и новые context/status/plan/passport/ECC/gap/traceability/index
записи: closeout docs APPROVE/open0. Независимо повторил4source hashes; runtime и
preservation/link counts не исполнял. Рекомендация дописать final scanner result
в §16 выполнена root (0findings/exit0).
