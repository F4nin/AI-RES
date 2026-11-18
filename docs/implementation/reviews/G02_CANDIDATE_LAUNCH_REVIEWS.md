# G156 — existing candidate launch composition review

2026-11-18. Только2новыхfile, автор `executor_plan`; root runtime/integration.
[Exact2hashes](G02_CANDIDATE_LAUNCH_CODE_HASHES.json).

`launch_general`: отдельный blind-first read-only code/Python/pr-test source review;
`executor_normative`: отдельный blind-first read-only security/silent-failure review.
Оба читали actual composition/control/runner/TLS/HostFactory callees, не author report.
Final APPROVE/open0, CRITICAL/HIGH/MEDIUM/LOW0. Runtime/tests reviewers не запускали.

Dryrun до settings/resources, explicit paths/execute, fixed privateTLS/Ed25519 app
и existing final-claim gate, private unicast listener, no proxy/accesslogs,
bounded redacted error boundary, async cleanup normal/error/cancel сохранены.
Нет real account/credential/owner/profile/grant provisioning или автоматического
approval/provider calls. Tests — explicit doubles реального ASGI auth/HTTPS/CLI
wiring, не доказательство настоящего TLS listener/live provider.

Author RED missingmodule exit2, GREEN22passed0.26s, Ruff2files PASS,
mypy1file PASS; root общий final pre-pr обеспечивает интеграционную проверку.
Для actual launch нужны reviewed namespace/DNS, exact hardened image/runtime/
source bindings, original ledger account, current tariff и safe relay-only key.
Default localhost не предполагает доступности bifrost-poc DNS с laptop host.
