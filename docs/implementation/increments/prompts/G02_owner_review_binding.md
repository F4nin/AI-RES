# G156 — authenticated owner identity-review binding

## Основание и границы

Продолжение подготовки после ADR138 по команде владельца 2026-11-18.
[ADR139](../../decisions/ADR-139-authenticated-owner-review.md), DOC076 v1.1 §3.1/7,
IAM v1.5 §8, Auth v1.1, DOC068/072; owner decision2026-11-14 и ADR132/138.
G02/S17/S20/S21 не запускаются; actual human/profile acceptance не выполняется.

## Scope

Backend-only prepare/revalidate review material с exact provisioned owner org/user/
profile и default absent→deny. Живые session/user/member/MFA под locks, отдельный
Policy action без packaged grant. Policy I/O вне UoW, final live revalidation после
ожиданий, factor→session порядок относительно existing MFA reset/verify.

Привязать actual parsed canonical observation hash к expectation.evidenceSha256,
полную profile snapshot без float-loss, exact managed refs и generation/control/
pending состояние. Previous material сравнивается с заново прочитанными фактами.
Сохранить ADR138 readiness/fence SQL при вынесении shared helper.

Не добавлять approval DML/privileged application factory/grants/migrations,
transport/CLI/seeds/keys/model calls. Read policy audit относится к реальному
subject, не маскируется под global model approval. Материал не grant/decision/
provenance attestation; lifecycle executor/observed gateway остаются следующими.

## Проверки и ECC

Unit RED/GREEN parser/binding; real disposable PostgreSQL16 под actual API grants:
wrong/absent/same-role owner, forged cached MFA/revoked/expired/disabled subject,
policy deny/unknown/outage/timeout/approval-required, audit failure, stale/tampered
review, changed session/policy/profile/generation/block/pending. Actual fence-wait
expiry и reset lock interleave, numeric snapshot precision; прежний guard/lifecycle
regression. Fast/static/contracts/secrets/diff/source preservation по actual Makefile.

ECC planner/architect — ограниченные read-only задания; python-testing/verification-
loop — прочитанные checklists; independent code/Python/database/pr-test и security/
silent-failure reviews blind-first, без author report. Fix findings и повтор checks.
Native Claude commands/hooks/product QA/human approval не имитируются.

DoD этого среза — локально TESTED механизм с точными commands/counts/HEAD+diff,
review/hashes и сохранённым контекстом. Полный G156/pre-pr/Linux CI/live/human/SLICE
не объявлять выполненными. Отдельный профильный review executor обязателен позже.
