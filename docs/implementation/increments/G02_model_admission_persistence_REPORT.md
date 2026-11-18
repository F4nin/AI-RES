# Подготовка G02 — durable guard foundation: checkpoint

**Дата:** 2026-11-17. **Scope:** [ADR132](../decisions/ADR-132-model-admission-persistence.md), [план подготовки](../groups/G02_FLASH_ADMISSION.md), [паспорт](../groups/G02_WORK.md). **Статус:** локальный persistence/mode checkpoint TESTED; подготовка IN_PROGRESS; полный G156 и общая подготовка NOT VERIFIED. G02/S17/S20/S21 NOT_STARTED и требуют нового явного согласия владельца после подготовки.

## 1. Реализация

В существующей ai_res_db добавлены immutable generations, control projection, durable call receipts и append-only metadata-only security audit. Begin коммитит IN_FLIGHT receipt+audit до возврата ticket; сам guard не вызывает LLM. Single-flight действует на весь профиль, включая старые generations. Мismatch/malformed finalize коммитит sticky block+terminal receipt+audit до controlled refusal. Audit/DB failure не уничтожает ранее committed pending; следующий begin отказывается, в том числе в новом процессе. Unknown outcome не очищается по TTL.

Exact ticket/profile/generation/request/managed versions/hash проверяются; валидный exact finalize replay не создаёт дубли audit, разные evidence для того же receipt отказываются. Runtime не создаёт approval generations, не меняет active generation и не снимает block. Owner generation fixtures в тестах не являются реальным human approval.

## 2. Нормативные источники

AGENTS§5/7/10/11, CONTEXT_RETENTION; Registryv4.1, DOC076v1.1§3.1/7, ADR128/131; Persistence Blueprint DOC072§7–9/12/14; MigrationStrategy DOC068; IAM/Security baseline и существующий0017/S15 code. Canonical/Registry/машинное зеркало не менялись. На исходном checkpoint0022 profile mode ещё не было; последующий0023 expand описан ниже. Реальный owner identity binding/approval не реализованы.

## 3. Scope файлов

| Файлы | Изменение |
|---|---|
| `db/migrations/versions/0020_model_admission_guard.py` | Новые4таблицы/constraints/RLS/узкие grants/immutable triggers, без profile seeds |
| `0021_model_admission_reapproval.py` | Forward guard: unblock требует новой generation даже для owner |
| `0022_model_admission_restore_actor.py` | Forward correction session-dependent CHECK, исторические audit actors восстанавливаются |
| `0023_model_profile_identity_mode.py`, `observed_profiles.py`, `repository.py` | Последующий narrow observed mode expand/readonly reference и fail-closed pinned loader |
| `tests/integration/postgres/test_observed_model_profiles.py`, `test_llm_gateway.py`, `test_migration_graph.py` | Compatibility/SQLNULL/mode tests, explicit legacy fixture и exact reviewed DDL exceptions |
| `modules/model_registry/admission.py` | Typed ticket, короткие UoW, strict metadata parsing, durable begin/finalize, safe errors |
| `tests/integration/postgres/test_model_admission.py` | Реальные state/concurrency/RLS/grants/audit failure cases |
| `test_model_admission_migration.py`, `test_model_admission_restart.py` | Previous-data preservation, owner reapproval constraint, два интерпретатора, logical dump/restore |
| `ops/postgres/schema_snapshot.sql` | Штатная генерация и ручной diff review; только новые guard objects/grants/policies |
| `test_audit_platform_schema.py` | Закрытый перечень таблиц расширен ровно4новыми, без ослабления security checks |
| ADR132/ADL, этот report/review и implementation context | Scope, evidence, оставшиеся условия и новый owner start gate |

На старте40локальных файлов предыдущей подготовки/NCP16/OD19 сохранены. Ветка `feat/g02-manager-tools-planning`, HEAD`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + текущий diff. Новый код не включён в продуктовый factory/transport. Git-доставка пока не выполнялась, исходный чужой diff не переносился автоматически.

## 4. Контракты/API/events

Новый внутренний ModelAdmissionGuard/AdmissionTicket и DB technical records используют строгий expectation/observation contract0.2. Endpoint, публичный API, WorkerResult, domain event/Outbox consumer и новый runtime principal не вводятся. Служебный GUC exact profile — defense-in-depth, не proof человеческой/Run авторизации. Будущий authenticated host должен проверять bound execution/Policy до доступа; текущий guard вызывают только тесты/trusted composition, product wiring отсутствует.

## 5. Миграции/совместимость

Цепь:0019`b621f4d8a905`→0020`c93e6a7d20b1`→0021`d42f7b8c31a6`→0022`e53a8c9d42b7`→0023`f64b9da053c8`. Применённые revisions не редактировались; refinements отдельными forward migrations. На foundation0022 existing model_profiles/pin/approval trigger/grants не менялись. Последующий0023 сохраняет mandatory nonempty pin для IMMUTABLE и разрешает NULL только exact DeepSeek Flash в explicit FLASH_OBSERVED; CHECK IS TRUE закрывает SQL NULL loophole. Snapshot trigger делает mode immutable; legacy rows получают IMMUTABLE без изменения прежних значений. Production seed/approval/grants не добавляются. 0022 CHECK drop не удаляет данных/колонок и сохраняет column grant анти-подмену. Все применения только в disposable Testcontainers PostgreSQL; dev-стек/volumes/production не менялись.

ENABLE+FORCE RLS/default deny на4technical tables, transaction-local app.model_profile_id, owner migration policy по существующему шаблону. Никаких runtime-write exempt entries или новых DB roles. Generic RLS/grants checkers не ослаблялись. Snapshot generation не доказывает drift0: независимые drift/empty+previous upgrade checks действительно выполнены отдельно, результаты ниже.

## 6. Решения

ADR132 — durable pending receipt, conservative single-flight, global technical security audit без фиктивного tenant, runtime без approval path; последующие0021/22 сохраняют историю и усиливают lifecycle/restore correctness. Owner personally approval не интерпретируется как право любого ORGANIZATION_OWNER глобально утверждать модель.

## 7. Findings/исправления

- MEDIUM: draft pending query/index только current generation. Исправлено до первого применения0020: query по всем IN_FLIGHT профиля +unique(profile_id), PG regression audit failure→owner advance→new engine deny.
- Owner unblock с той же generation, замеченный автором при freeze: исправлен forward0021, PG negative/positive case.
- MEDIUM: session-dependent audit writer CHECK мешал logical restore под другой ролью. Исправлен forward0022, anti-forgery column grants сохранены; проверен реальный dump/restore исторических фактов.
- LOW wording evidence: docstring уточнён — logical restore проверяется, physical/power-loss/PITR/product drill не заявляются.
- Полный backend прогон выявил устаревший закрытый список таблиц S05; добавлены ровно4новые таблицы. Результаты текущей регрессии/оставшиеся failures фиксируются ниже после завершения прогона, не объявляются PASS заранее.

## 8. ECC

Отдельный g02_prerequisite_plan: planner/architect read-only к actualregistry/IAM/audit/persistence, затем ограниченное авторство0020/admission.py/PGtests, TDD/static/checklists. Root — coordinator, новые0021/22, upgrade/process/restore tests и snapshot/context. Авторы не reviewers своих файлов. Независимые g02_python_contract_review применил database/Python/code/test компетенции, g02_scope_security_review — security/code, blind-first/read-only без авторского отчёта; final delta reviews по0019→0022 APPROVE/openfindings0. Runtime tests выполняли автор/интегратор; reviewer их себе не приписывает. Native Claude commands/hooks не запускались.

## 9. Проверки

Среда: Darwin arm64, Python3.13.5, uv0.11.31, Docker29.2.0; PG16image берётся exact tag+digest из текущего Compose. Shared runtime: по очереди автор→root, только отдельные Testcontainers; Compose основной stack не менялся. Проверенный scope — указанный HEAD+working diff, включая ранее сохранённые canonical/mirror-pointer изменения, которым новый runtime PASS отдельно не приписывается.

| Проверка | Команда | Результат |
|---|---|---|
| Автор, первый PG срез | В backend:`.venv/bin/python -m pytest -q tests/integration/postgres/test_model_admission.py tests/integration/postgres/test_model_admission_migration.py` | exit0;20passed,затем расширенный28passed/0failed/skipped |
| Root0021+два процесса | В backend:`.venv/bin/python -m pytest -q tests/integration/postgres/test_model_admission.py tests/integration/postgres/test_model_admission_migration.py tests/integration/postgres/test_model_admission_restart.py` | exit0;31passed/0failed/skipped |
| Root0022+logical restore | Та же команда после forward0022/нового кейса | exit0;32passed/0failed/skipped,17.79s |
| Static | `make backend-check` | exit0;ruff0,mypy178sourcefiles0issues,15importcontractsKEPT/0broken |
| Snapshot | `make db-snapshot` | Штатная генерация exit0/1intentional skip (не PASS теста); повтор после0022 оправдан DDL change. Ручной diff267additions/0deletions, новые объекты только |
| Полный backend до обновления legacy expectations | `make backend-test` | exit2;1901passed/3failed/541warnings/0skipped,359.89s. Все3failures описаны ниже; этот прогон не объявляется PASS |
| Затронутые legacy cases + migration/drift | В backend:`.venv/bin/python -m pytest -q tests/unit/test_migration_graph.py tests/integration/postgres/test_audit_platform_schema.py::test_audits_clean_and_tables_exist tests/integration/postgres/test_model_registry.py::test_profile_is_immutable_except_lifecycle_and_never_deleted_or_truncated tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py::test_persist_001_upgrade_from_empty_reaches_head tests/integration/postgres/test_migration_safety.py::test_persist_002_upgrade_from_previous_revision_keeps_data_and_matches_snapshot` | exit0;11passed/0failed/skipped,8.52s после исправлений; включает actual drift0/empty+previous upgrades |
|0023 scoped PostgreSQL | В backend:`.venv/bin/python -m pytest -q tests/integration/postgres/test_observed_model_profiles.py tests/integration/postgres/test_model_registry.py tests/integration/postgres/test_model_admission.py tests/integration/postgres/test_model_admission_migration.py tests/integration/postgres/test_model_admission_restart.py` | Автор:exit0;56passed/0failed/skipped,24.63s; включает16new mode cases |
|0023 fast | `make pre-push-fast` | Root:exit0;ruff0,mypy180sourcefiles0issues,15importcontractsKEPT,957passed/4warnings/0failed/skipped,9.72s |
|0023 snapshot | `make db-snapshot` | Root:exit0,1intentionalskip/4.51s — только генерация. Ручной diff271additions/1deletion: новые objects и nullable pin+mode constraints, история/данные не удаляются |
|0023 actual drift/upgrades/legacy security | В backend:`.venv/bin/python -m pytest -q tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py::test_persist_001_upgrade_from_empty_reaches_head tests/integration/postgres/test_migration_safety.py::test_persist_002_upgrade_from_previous_revision_keeps_data_and_matches_snapshot tests/integration/postgres/test_audit_platform_schema.py::test_audits_clean_and_tables_exist tests/integration/postgres/test_model_registry.py::test_profile_is_immutable_except_lifecycle_and_never_deleted_or_truncated` | Root:exit0,7passed/0failed/skipped,9.26s; actual drift0, empty+previous upgrades |
|Docs / secrets / preservation | `python3 docs/implementation/tools/check_prompts.py`; `make infra-scan-secrets`; read-only registry/manifest/local-links/hash comparison; `git diff --check` | exit0;40prompts/0issues,0secretfindings;74canonical/73manifesthashes0mismatch;262localfilelinks0missing;initial40files31byteidentical+9authorizedimplementationdocedits0unexpected |

## 10. Security evidence

Три failures полного прогона относились к существующим тестовым expectations, изменившимся из-за добавленных объектов: closed catalogue дополнен ровно4таблицами; TRUNCATE attack усилен до CASCADE, чтобы проверить BEFORE TRUNCATE guard после появления FKs; blanket DROP ban сохранён, с единственным exact-one-statement исключением для audited0022 DROP CONSTRAINT (не table/schema/column). Исходные security assertions не отключены. Production code после этого не менялся в foundation; все3случая и drift/upgrades прошли отдельный11case прогон. Свежий полный прогон на совокупной подготовке остаётся перед итоговой приёмкой; старый exit2 не скрыт.

Реальные API LOGIN и column grants: нет generation/approval/unblock, DELETE/TRUNCATE/DDL; writer/time нельзя подменить INSERT, actual DB writer_role сохраняется. Exact-profile FORCE RLS отсутствие/чужой/сброшенный context не выпускают записи. Cross-profile receipts, stale reply, expected hash/managed/ref mismatch, candidate/wrong provider/Pro, missing fingerprint и malformed outcomes отказываются. При отказе final audit pending остаётся после reopening/process loss; смена generation не снимает unknown-outcome barrier. Raw payload не хранится, только bounded metadata/hash/reason; ошибки не раскрывают DB/provider text.

## 11. Независимое review

Ссылки/verdicts/исправления — [G02_MODEL_ADMISSION_REVIEWS](../reviews/G02_MODEL_ADMISSION_REVIEWS.md). Два отдельных reviewer, blind-first; CRITICAL/HIGH не обнаружены, MEDIUM устранены и пересмотрены. Root-owned root tests/migrations также отдельно проверены; свежие Python process и logical restore не выдаются за full recovery acceptance.

## 12. Невыполнено/ограничения

Честное observed-profile представление0023 реализовано и проверено локально; нет его product routing, authenticated global owner setup/human approval API, atomic profile-status/control-epoch coupling, durable paid ledger/candidate runner, Bifrost transport integration/stream aggregation и real-provider evidence. IMMUTABLE pin остаётся mandatory; observed fixtures после0023 используют NULL pin, synthetic approval только в tests. Readonly observed reference не имеет capabilities/usable_at и не является executable ModelProfile; legacy loader не преобразует его в fake pin. Сервис не имеет HTTP endpoint и не выдаёт Run/model grants. Телеметрия нового product host/stream пока не подключена вместе с отсутствующим wiring; metadata-only audit реализован отдельно и не подменяет observability. Полный pre-pr/LinuxCI/supply-chain/release/backup-PITR drills не запускались; ни product VERIFIED, ни полная готовность подготовки не заявляются. Key не подключён,modelcalls0,cost0USD.

## 13. Контекст

Граница владельца сохранена: только подготовка; после её фактического завершения уведомить, G02/S17/S20/S21 не стартовать без нового явного согласия. Обновляются паспорт, HANDOFF/STATUS, gaps/traceability/ECC/ADL и readiness matrix. Уже принятые ADR128/129/131/предыдущие source changes не переоткрываются.

## 14. DoD текущего среза

✅Реальный durable mechanism/constraints/role-negative tests/independent reviews. ✅32targetedPG cases, process exit и logical restore. ✅Affected legacy/upgrade/drift11passed после3failures полного backend. ⏳Повтор полного backend и общий pre-pr/Linux CI не выполнены. ✅Observed representation0023/PG56cases/два independent review APPROVE. ❌Полный G156 admission/product routing/live evidence/owner approval. G02 NOT_STARTED; текущая foundation не завершает всю подготовку.

## 15. Следующий разрешённый шаг

Следующий шаг — отдельный bounded technical ledger/candidate permit/runner и безопасный key setup; после live evidence — human exactvalues/Bifrost/profile approvals и SLICE01 с отдельными данными/бюджетом. Перед S20 сохраняются ADR129/G107. Начало S17/S20/S21 — только после новой команды владельца, даже если все технические предпосылки готовы. Сейчас новый вопрос о старте не запрашивается.

## 16. 0023: независимый checkpoint и frozen migrations

Code/DDL до первого применения отдельно просмотрены root и двумя независимыми reviewers: database/Python и security final APPROVE/open0. Reviewers не запускали Docker/tests; author PG56 и root fast/drift evidence приведены выше. Старые applied revisions не редактировались;0023 применён только в disposable test DB и после первого применения заморожен.

| Revision | SHA-256 |
|---|---|
|0020|`858e2f06afa4fbcb61fa3175a850e2c0455e468eb98e6a158d33d8dd132f599c`|
|0021|`44b094ecd486175389aee9738b2a80df657cdae60b5b855a71e5b12b5395f2cd`|
|0022|`6d60dfa9d34850aedfb4baa79115003c6d47f7dabdf707f283e9d3bb9aa902a5`|
|0023|`2e8ee8f916cd2c0d16f8e4f844b5dd441d77d2eae898a94b7371b3f2e83163d2`|

Этот checkpoint не закрывает полную подготовку и не разрешает G02. Следующий read-only технический план ledger/permit/runner не считается реализованным кодом.
