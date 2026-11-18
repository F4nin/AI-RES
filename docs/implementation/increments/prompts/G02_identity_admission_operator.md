# G156 — isolated identity-admission operator

Поручение: продолжить подготовку2026-11-18 после ADR139. Scope/границы —
[ADR140](../../decisions/ADR-140-identity-admission-operator.md).

Реализовать backend-only explicit human ACCEPT_IDENTITY/BLOCK, exact authenticated
owner/session/MFA/Policy и повтор ADR139 binding под final lifecycle fence.
NOLOGIN EXECUTE-only operator, пустой owner-only login binding, две hardened definer
routines и append-only global audit, additive0026. Нет product routing/activation,
real provisioning, credentials, seeds/model calls или изменения canonical/contracts.

Проверить на disposablePG16: exact/wrong/absent owner/login/scope; sessions/MFA/
membership/status/policy failure; state/evidence tampering, races/pending/drift/
block/reapproval, duplicate/reused decision, audit rollback и restart; реальные API/
operator grants и function settings/allowlist drift, empty/previous upgrade/snapshot.
Independent database/general/Python и security review до apply и после fixes.
Root author/runtime/integrator; ECC planner/architect отдельные read-only задания,
python-testing/verification-loop прочитанные checklists; native commands не заявлять.
Сохранить report/evidence/traceability/context; bounded seam только TESTED.
G156 full pre-pr/LinuxCI/live/human/SLICE pending; G02/S17/S20/S21 NOT_STARTED.
