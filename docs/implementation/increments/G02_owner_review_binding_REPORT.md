# G156 — authenticated owner-review binding: Increment Report

**Дата:** 2026-11-18. **Промпт:** [scope](prompts/G02_owner_review_binding.md).
**Результат:** bounded identity-review preparation/revalidation локально TESTED.
Подготовка G156 IN_PROGRESS/NOT VERIFIED; G02/S17/S20/S21 NOT_STARTED.

## 1. Реализованный scope

Backend-only `OwnerReviewService`: exact configured owner organization/user/profile,
live session/user/member/MFA, отдельный Policy action и повтор сравнения материала.
Один parsed canonical observation связан SHA256 с evidenceSha256 expectation;
identity/managed refs совпадают. Binding включает human/session/MFA, policy version,
полный profile snapshot, control/current generation/pending и оба evidence hashes.
Предлагаемая generation ровно current+1, включая initial1 при отсутствии control.

Материал не является human decision, permission, доказательством происхождения
live observation либо полного Bifrost acceptance. Approval/lifecycle DML отсутствует.
Ничего не включает модель и не снимает pending/block. Нет production owner binding
или нового packaged grant; отсутствующая конфигурация/неизвестное action дают deny.

## 2. Нормативная база и источники

Восстановлены полный AGENTS/CONTEXT_RETENTION, CLAUDE/Registry/Spec с current
addenda, Charter/roadmap/status/handoff/tooling/gates/strategy и G02 plan/passport,
owner OD01/21 decision2026-11-14, ADR132/138. Применимые canonical: DOC076 v1.1
§3.1/7, IAM v1.5 §8, Auth v1.1 §5/6, security и DOC068/072 transaction/access
sections. Обычная tenant role не даёт global authority. Owner/migrator factory
не передаётся приложению; executor сохраняется отдельным preparatory seam.

Отдельная read-only normative reconnaissance:74canonical/0missing/0duplicateIDs/
paths;73manifest SHA+bytes/0mismatch;OpenAPI117/AsyncAPI360/Worker10 localrefs,
0missing. Agent прочитал применимые sections/current addenda; полного повторного
чтения всех больших unrelated canonical документов не заявляет. Первая неэффективная
repeated YAML проверка остановлена им exit130; cached полный повтор exit0/0.24s.
Это source reconnaissance, не pinned validation/runtime. Конфликтов scope не найдено.
Canonical/Registry/manifest и contract mirrors этим срезом не менялись.

## 3. Файлы и Git

Ветка `feat/g02-manager-tools-planning`, проверенный HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + накопленный working diff.
До edits сохранены SHA256/bytes149initial files. Предшествующая работа не
присваивается этому срезу. [Final4 source hashes](../reviews/G02_OWNER_REVIEW_CODE_HASHES.json).

| Файл/область | Изменение |
|---|---|
| `modules/model_registry/owner_review.py` | Новый bounded authenticated prepare/revalidate service |
| `modules/model_registry/admission.py` | Только extraction существующего ADR138 fence в shared helper |
| `tests/unit/test_model_owner_review.py` | 9new parser/hash/scope cases |
| `tests/integration/postgres/test_model_owner_review.py` | 42new actualPG cases |
| Implementation docs/evidence | ADR139, prompt/index/report/review/hashes, ADL/context/status/gap/passport/plan/ECC/traceability |

Reverse extraction воспроизвёл точный SHA256 initial admission.py: прежний guard
не переписан. Historical ADR138 hash/report сохраняются; новый hash принадлежит
ADR139. Итог сохранности/числа файлов — §16 после final scope checks.

## 4. API, contracts и events

Public API/OpenAPI/AsyncAPI/Worker DTO/internal wire schema и compatibility baseline
не меняются. Новый Python comparison object содержит5полей/digests, binding
domain marker0.1; это не wire contract или serialized grant. Новый internal Policy
action `model_admission.review`, без production config/grant. Existing contract0.2
сохраняется; consumer дополнительно сверяет actual observation hash. Нет generic
approval endpoint/CLI/новых событий либо routing/factory изменений.

## 5. Миграции, совместимость, данные

Миграций/DDL/grants/schema snapshot edits нет; frozen0017/0020–0025 сохранены.
Обычный API остаётся SELECT-only на profiles, owner/migration_mode не используется.
Только policy audit для реального authenticated subject в его организации; это
не фиктивная tenant запись global model approval. Profile/admission tables не
изменяются даже при repeated review. Full snapshot хешируется как PostgreSQL JSON
text, без преобразования numeric через float; иное DB rendering безопасно stale.

## 6. Самостоятельное техническое решение

[ADR139](../decisions/ADR-139-authenticated-owner-review.md): bounded read/review
preparation вместо преждевременного приложения с owner credentials. Policy I/O
вне UoW. Короткие subject transactions до/после Policy, live subject/MFA locks и
ADR138 fence перед control/profile reads. Executor и его privileges/global decision
audit будут отдельной реализацией; current review не выдаёт полномочия на запись.

## 7. Findings и исправления

Первый unit RED: отсутствующий module, exit2/1collectionerror. Первый PG run имел
32setup errors из-за ошибочных fixture-only MFA column names. После исправления
30passed/2failed: fixture пытался менять immutable absolute expiry. Заменено
реальными короткими session lifetimes и истечением; guards не ослаблялись.

General reviewer нашёл2MEDIUM: expiry при ожидании profile fence и session→factor
lock inversion относительно MFA reset. Добавлены final live checks и factor→session
порядок. Новый actualPG RED подтвердил pre-fix session locktimeout (1failed/
41deselected/5.24s/exit1); corrected final42 и joint187 проходят. Другой reviewer
предложил evidence enhancements: ACTIVE subject digest branch, replacement session/
policy, unsupported profiles, exact numeric snapshot; все добавлены.

## 8. ECC

Root — единственный author/integrator/runtime operator; явно прочитанные
python-testing/verification-loop как checklists. `owner_plan` — отдельный read-only
planner/architect, затем general/Python/database/pr-test reviewer; `owner_normative`
— read-only reconnaissance, затем independent security/architect/silent-failure
review. Нативные Claude commands/hooks не запускались; self-check не заменяет
независимость. [Протокол](../reviews/G02_OWNER_REVIEW_REVIEWS.md), ECC_USAGE обновлён.
Все обязательные компетенции bounded seam доступны; human/product QA не имитируются.

## 9. Проверки

Среда: Darwin arm64, Python3.13.5, uv0.11.31, Docker29.2.0, PostgreSQL16.15-bookworm
по existing Compose digest; реальные ai_res_api/migrator identities, disposable
Testcontainers. Проверялся HEAD выше +4final hashes; временные XML/logs `/tmp/g156-owner-*`
не обязательны для новой сессии, существенная сводка сохранена здесь.

| Команда | Результат |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_model_owner_review.py --tb=short` | 9passed/0failed/skipped/0.09s,exit0 до последующих PG enhancements |
| То же для `backend/tests/integration/postgres/test_model_owner_review.py`, XML `/tmp/g156-owner-pg-final.xml` | 42passed/0failed/errors/skipped/18.35s,exit0 |
| Final joint PG regression ниже | 187passed/0failed/errors/skipped/1existing xid8reflection warning/73.17s,exit0 |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | Final1428passed/0failed/skipped/4existingwarnings/9.65spytest;Ruff0,mypy197files0issues,15importsKEPT,exit0 |
| Те же offline env + `make -j1 contracts-check contracts-test` | 6/6validators,22passed/0failed/skipped/8.09s,exit0 |
| `infra/.venv/bin/python -B infra/scripts/scan_secrets.py` | 0findings,exit0; повтор finaldocs — §16 |
| `python3 -B docs/implementation/tools/check_prompts.py` | 40stageprompts/0issues,exit0; preparatory prompt source-reviewed отдельно |
| `git diff --check` | exit0; final scope/docs checks — §16 |

Final regression, после обеих MEDIUM fixes и final runtime-neutral docstring:

```sh
PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q \
  backend/tests/integration/postgres/test_model_owner_review.py \
  backend/tests/integration/postgres/test_model_admission_lifecycle.py \
  backend/tests/integration/postgres/test_model_admission.py \
  backend/tests/integration/postgres/test_model_admission_migration.py \
  backend/tests/integration/postgres/test_model_admission_restart.py \
  backend/tests/integration/postgres/test_observed_model_profiles.py \
  backend/tests/integration/postgres/test_model_registry.py \
  backend/tests/integration/postgres/test_schema_drift.py \
  backend/tests/integration/postgres/test_migrations.py \
  backend/tests/integration/postgres/test_iam_sessions.py \
  backend/tests/integration/postgres/test_iam_mfa.py \
  --tb=short --junitxml=/tmp/g156-owner-regression.xml
```

## 10. Security / authorization

Missing/wrong exact human, same-role owner в том же/другом tenant, forged org/
session/service actor; revoked/expired session, disabled user/membership deletion/
revocation, cleared/revoked/cachedMFA; Policy unknown/DENY/APPROVAL_REQUIRED/outage/
timeout/garbage; audit outage; subject mutation during Policy without held DB tx;
malformed/duplicate/unknown evidence, actual hash/managed identity mismatch;
tampered hashes/policy/session, profile lifecycle/unsupported state/version;
generation/block/pending stale without clearing; real fence-wait expiry и reset
interleave; lossless numeric full snapshot/unrelated profile; unchanged API grants.
Tests synthetic, не real provider metadata/human approval. Calls/spend0.

## 11. Независимое review

Два final independent source APPROVE/open0, каждый сверил4hashes и ADR139/prompt.
Initial2MEDIUM исправлены; CRITICAL/HIGH0. Runtime исполнял только root.
Source review не выдаёт human acceptance и не подтверждает будущий executor.

## 12. Ограничения и невыполненные gates

Нет durable approval decision/оператора исполнения, real owner provisioning,
complete acceptance manifest ingestion/provenance или observed gateway integration.
Один observation binding — только identity review material. Будущий executor
снова authenticate/authorize/revalidate и атомарно audit exact decision/generation;
review object нельзя использовать как reusable permit. Время проверяется до audit;
physical expiry во время самого audit/commit не исключается.

Full backend/pre-pr/Linux CI, global dependency audit/digests/SBOM, live evidence,
human approvals и SLICE не выполнялись в этом bounded промежуточном срезе.
Temporal/MinIO/Bifrost/SDK код не менялся, повтор native runtime не нужен для
извлечения helper/read-review. Доставка всей подготовки остаётся общей по паспорту:
накопленный исходный diff не присваивается и не коммитится автоматически. Новых
commit/push/PR/merge нет. Это не VERIFIED G156 и не отмена его общих gates.

## 13. Документация

ADR139/prompt/index/report/review/hashes, HANDOFF/STATUS, G02 passport/plan, ADL,
KNOWN_GAPS, ECC и обе traceability обновлены. Canonical/contracts/DECISIONS_PENDING/
ROADMAP не менялись: нет нового бизнес-решения, wire schema или порядка этапов.

## 14. DoD

G1/G2 fast PASS; G3 actualPG187PASS; G4 unchanged wire surfaces+validators/22tests
PASS; G5 scoped negatives/source review PASS, global supply-chain pending;
G6 schema unchanged, actual upgrades/drift/roles в совместной regression PASS;
G7 два final APPROVE/open0; G8/G9 docs/evidence. Bounded seam TESTED,
full G156 NOT VERIFIED; product stages NOT_STARTED.

## 15. Продолжение

Следующий безопасный preparatory seam — narrowly privileged operator lifecycle
executor: exact human decision/evidence/profile/generation binding, controlled
reapproval/revocation и атомарный global audit без owner credentials у приложения.
Затем observed gateway wiring; дальше общие finalgates/pre-pr/LinuxCI, reviewed
tariff/original account/safe key setup, live evidence+отдельные Bifrost/profile human
approvals и SLICE(data/license/separatebudget). До S20 ADR129/G107.
Подготовка ещё не завершена; G02/S17/S20/S21 требуют нового явного согласия после неё.

## 16. Final scope checks

149initial files →138byte-identical+11authorized helper/implementationdoc edits,
0missing,+8new files:19taskfiles (4code/15docs+evidence). Проверены4final source
hashes и29protected initial frozen/canonical/contract/SDK/schema paths без изменений.
314local Markdown filelinks/0missing; anchors/externalURLs не проверялись.
Final prompts40/0 и diffcheck exit0; повтор scanner после документации:
0findings/exit0. В момент final snapshot работают18containers; initial IDs/
StartedAt в этой сессии не снимались, поэтому равенство с initial не заявляется.
Root запускал только disposablePG, mainstack/данные/секреты задачей не менялись;
checksums stores не проверялись. Секреты/DSN/credential files в evidence не включены.
