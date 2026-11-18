# G156 — isolated identity-admission operator: Increment Report

**Дата:**2026-11-18. [Промпт](prompts/G02_identity_admission_operator.md),
[ADR140](../decisions/ADR-140-identity-admission-operator.md).
**Результат:** механизм локально TESTED; весь допуск G156 ещё IN_PROGRESS.

## 1. Реализовано

Backend-only explicit human ACCEPT_IDENTITY/BLOCK: новая immutable generation,
pending barrier, sticky block и atomic global decision audit. Initial CANDIDATE
не становится APPROVED; первоначальный profile approver/time не переписываются.
Review заново вычисляется под live session/member/user/MFA и lifecycle fence;
самостоятельный execute Policy вне DB UoW. Same-session matching decision replay
возвращает historical receipt, не повторяет writes и не снимает поздний block.

## 2. Источники

Полные AGENTS/CONTEXT_RETENTION/CLAUDE/Registry/Spec с current addenda, Charter,
plan/passport/handoff/status/tooling/gates/strategy, owner OD01/21 decision,
ADR132/138/139; DOC076v1.1§3.1/7, IAM/Auth/Security и DOC068/072. Read-only
reconnaissance отдельного reviewer:74canonical/0missing/duplicates,
73manifest SHA+bytes/0mismatch; OpenAPI117/AsyncAPI360/Worker10refs/0missing.
Полного повторного чтения всех unrelated больших canonical документов не заявляем.

## 3. Scope и Git

`feat/g02-manager-tools-planning`, HEAD db8d4af34b0933aa2562adcf072b717eb0e3e3e9
+ working diff; initial157files сохранены по SHA перед edits. Новые0026/operator/
unit+PGtests; shared review helper, provisioning/audit/snapshot tooling и schema
snapshot. [10точныхhashes](../reviews/G02_IDENTITY_OPERATOR_CODE_HASHES.json).
Предшествующая работа не присваивается текущему срезу. Общая доставка допуска
остаётся впереди; этот отчёт не объявляет отдельный delivery или начало G02.

## 4. API/contracts/events

Public API/OpenAPI/AsyncAPI/Worker DTO/wire schemas не меняются; нет endpoint/CLI
для approval или product factory. Internal Python commands/receipts и2SQL routines.
Новые Policy actions accept_identity/block без packaged grants. Global технический
decision audit атомарен с guard state; нет domain event/consumer, Outbox N/A здесь.

## 5. Миграция и данные

Additive0026 c97e3bf386f1, parent b86d2af275e0; после successful apply frozen SHA
в hash artifact.2новые append-only owner-only FORCE RLS tables: пустой login/owner/
profile binding и global decision audit. Dormant NOLOGIN operator — только EXECUTE
2точных definer routines; API/PUBLIC/runtime прав не получают. Нет real login/
membership/binding/profile/key/account seeds. Owner-only parameter SET provision
нужен для function-local custom GUC; нет owner/migrator factory у приложения.
Upgrade populated previous сохраняет profiles/generation/pending/audit; actual
drift/roles/RLS проходят. Snapshot regenerated намеренно и reviewable; frozen0017/
0020–25/canonical/contracts/SDK не менялись. Mainstack этим срезом не изменялся.

## 6–8. Решения, fixes, ECC

ADR140 технический, не human acceptance. Root author/runtime/integrator;
python-testing/verification-loop прочитаны как checklists.2отдельных read-only
planner/architect/general/Python/database и security/silent-failure reviewers.
Нативные Claude commands/hooks/productQA/human approval не имитировались.
До successful apply исправлены inherited-EXECUTE audit, SQL NULL generation,
FKindex/duplicateFK и owner parameter privilege; последний потребовал полного
отката первой миграционной попытки. Expanded4fail — test-only clusterACL cleanup,
исправлен transaction rollback. [Review protocol](../reviews/G02_IDENTITY_OPERATOR_REVIEWS.md).

## 9. Проверки

Darwin arm64, Python3.13.5/uv0.11.31/Docker29.2.0/PostgreSQL16.15-bookworm existing
Compose digest, disposableTestcontainers. HEAD+10hashes выше; временные логи/XML
`/tmp/g156-executor-*` не обязательны для продолжения.

| Команда | Результат |
|---|---|
| python -B -m pytest -q unit/test_identity_admission_operator.py + test_model_owner_review.py + test_migration_graph.py | RED missingmodule1collectionerror; GREEN19passed/0.25s/exit0 |
| python -B -m pytest -q integration/postgres/test_identity_admission_operator.py | Firstapply44setuperrors/exit1, rollback; successful44passed/19.29s/exit0; expanded56passed4failed/26.81s; corrected60passed/26.91s/exit0 |
| UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast |1434passed/4existingwarnings/10.22s; Ruff0,mypy199files,15importsKEPT,exit0 |
| Те же offline env + make -j1 db-snapshot |exit0,1intentionalSKIP/3.94s; regeneration не PASS |
| Final joint PG ниже |306passed/0failed/errors/skipped/1existing xid8warning/112.51s,exit0 |

Final command, env PYTHONDONTWRITEBYTECODE=1, executable backend/.venv/bin/python -B:
`-m pytest -q` с путями `backend/tests/integration/postgres/` + test_identity_admission_operator.py,
test_model_owner_review.py,test_model_admission_lifecycle.py,test_model_admission.py,
test_model_admission_migration.py,test_model_admission_restart.py,test_observed_model_profiles.py,
test_model_registry.py,test_schema_drift.py,test_migrations.py,test_iam_sessions.py,
test_iam_mfa.py,test_roles_and_grants.py; `--tb=short --junitxml=/tmp/g156-executor-regression.xml`.

## 10–11. Security/review

Exact/absent/wrong human/login/scope; captured session/user/member/MFA revocation;
Policy deny/approval/outage/garbage/timeout/version; tampered4digests/full state;
pending acceptance denied/BLOCK preserved; concurrent same/different decisions;
lostreply replay without unblock, fresh interpreter durable receipt; expiry during
actual fence wait, factor-first MFA reset; audit failure rolls back all state;
API/operator direct grants denied; SQL missing/nullgeneration denied; function/
effective membership/parameterACL drift detected; GUC restored/no owner access.
Два independent source APPROVE/open0; runtime выполнял root. Metadata checks не
доказывают provenance/live capability и не дают physical commit-time expiry guarantee.

## 12–15. Границы и продолжение

G1/G2/G3/G5scoped/G6/G7PASS,G8/G9docs. Full pre-pr/LinuxCI/supplychain/live/human/
SLICE остаются общей приёмкой G156. Этот локальный checkpoint не завершает поручение
владельца закончить весь допуск. Продуктовые G02/S17/S20/S21 NOT_STARTED.

По уточнению владельца прекращено разрастание подготовительных срезов. Дальше
только существующий guarded candidate launch + общие необходимые проверки +
reviewed tariff/original account/safe key setup и реальный synthetic TEXT в прежнем
10USD/8attempt envelope, затем остальные plannedcases и отдельная human приёмка.
Product operator provisioning/APPROVED profile/observed gateway не нужны до первого
profileless probe. Canonical/Registry/contracts не менялись; implementation
ADR/status/handoff/plan/passport/ECC/traceability сохраняют фактическую фазу.
