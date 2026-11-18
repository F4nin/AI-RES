# Подготовка G02 — учёт расходов технического допуска Flash

**Дата:** 2026-11-17. **Статус компонента:** локально TESTED. Полная подготовка и G156 NOT VERIFIED; G02/S17/S20/S21 NOT_STARTED до нового согласия владельца. Основание: [ADR133](../decisions/ADR-133-flash-paid-ledger.md), [план](../groups/G02_FLASH_ADMISSION.md), [паспорт](../groups/G02_WORK.md).

## 1. Что реализовано

Отключённый backend ledger одного ранее разрешённого технического бюджета: суммарно ≤10 USD и ≤8 попыток. Тарифы, лимиты, исходный расход, план и привязка запроса неизменяемы; новая запись или новый процесс не создают второй кошелёк. Резервирование и однократное подтверждение отправки коммитят обязательный audit до возврата результата.

UNKNOWN сохраняет полный резерв. Незавершённая reservation/claim после выхода процесса блокирует новый reserve. Известный расход рассчитывается сервером; overrun и invalid usage сохраняют расход/block/audit до отказа. Повтор точного settlement не списывает средства дважды; конфликт evidence блокирует account. Реальных accounts/tariffs/keys/calls нет.

## 2. Нормативная база

AGENTS §5/7/10/11, CONTEXT_RETENTION, Registry4.1 и DOC076v1.1 §3.1/5/7; ADR128/131/132, принятый paid plan, DOC068/DOC072 и existing IAM/security/RLS/audit. Canonical документы не менялись. S16/G01 не переоткрывались.

## 3. Файлы и Git

| Файлы | Изменение |
|---|---|
| `backend/src/ai_res/db/migrations/versions/0024_llm_poc_paid_ledger.py` | Четыре технические таблицы, constraints/triggers/RLS и узкие grants |
| `backend/src/ai_res/modules/model_registry/poc_budget.py` | Typed bindings/tickets, accounting, reservation/claim/settlement и безопасные отказы |
| `backend/tests/integration/postgres/test_llm_poc_paid_ledger.py` | 34 случая: ограничения, concurrency, audit failures, grants/RLS, upgrade |
| `backend/tests/integration/postgres/test_llm_poc_paid_ledger_restart.py` | 6 случаев: отдельные процессы, replay/unknown/block и logical restore |
| `test_audit_platform_schema.py`, `ops/postgres/schema_snapshot.sql` | Закрытый catalogue дополнен ровно четырьмя таблицами; snapshot с ручным review |
| ADR133/ADL, report/review, plan/passport и implementation context | Scope, evidence и оставшиеся условия |

Ветка `feat/g02-manager-tools-planning`, проверенный HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff. Все прежние локальные изменения сохранены. Commit/push/PR/merge этого checkpoint не выполнялись. Existing BudgetLedgerPort/InMemoryBudgetLedger, product budget/ModelProfile/factory/BifrostTransport и relay этим срезом не менялись.

## 4. API и контракты

Добавлены только внутренние backend DTO/TechnicalPaidLedger. Публичного или private HTTP endpoint, domain event/WorkerResult/Run grant нет. DispatchClaim — ссылка на committed state, а не переносимое разрешение. Будущий host обязан авторизовать вызов, проверить актуальные тарифы и фактически отправляемый payload; без этого live calls запрещены.

## 5. Миграции и совместимость

Forward0024: `a75c0eb164d9` после `f64b9da053c8`. Применена только в disposable PostgreSQL и заморожена; SHA-256 `8e1ae3e9bc2249d9eaf40f0b5522dfdb72e6b85d8da86b67361e9ae29ff56751`. Applied revisions не переписывались.

Новые platform tables: `llm_poc_budget_accounts`, `llm_poc_attempts`, `llm_poc_settlements`, `llm_poc_budget_audit`. ENABLE+FORCE RLS/default deny, transaction-local exact account context, owner migration gate и narrow existing API column grants. Новых roles/exemptions/seeds нет. Runtime не создаёт account, не меняет cap/rates/plan и не снимает sticky block. Стоимость и audit writer/time задаёт сервер; session-dependent CHECK отсутствует. UNIQUE(account_id,body_sha256) действует на всю историю, включая settled attempts.

Upgrade from empty/previous, drift0 и generic grants/RLS/postflight действительно проверены отдельно от генерации snapshot. Основной dev stack/volumes/secrets/данные не менялись; все применения — disposable tests. Snapshot total diff к HEAD:657 additions/1 deletion, включая предыдущие guard/mode изменения; этот шаг добавил386 строк без новых удалений.

## 6. Технические решения

ADR133: bounded technical ledger вместо несовместимой подмены общего BudgetLedgerPort; immutable original authorization и отсутствие release_unknown/TTL/autoclear/reset. Tariff freshness не заменяется придуманным TTL: конкретная проверка официальных тарифов перед live/возобновлением остаётся будущему trusted host. Changed tariff требует остановки и контролируемого amendment без нового кошелька.

## 7. Findings и исправления

- MEDIUM: несколько READ COMMITTED чтений balance могли смешивать состояния. Исправлено до приёмки: короткий account FOR UPDATE; coordinated PG regression проверяет реальную блокировку и согласованность при concurrent overrun.
- LOW: unhashable unknown reason давал TypeError. Теперь malformed reason классифицируется как INVALID_USAGE с полным резервом/block/audit до безопасного отказа.
- Read-only egress analysis обнаружил replay старого body против новой reservation. До первого apply добавлен permanent body-hash UNIQUE. Будущий runner обязан включать уникальный synthetic marker в body каждой попытки; сам runner не реализован.

## 8. ECC

Отдельный `g02_prerequisite_plan` выполнил actual-code plan, затем ограниченное авторство трёх файлов/TDD/database/Python. Root интегрировал отдельный process/restore test, catalogue, snapshot и контекст. `g02_python_contract_review` независимо применил database/Python/code/test review; `g02_scope_security_review` — security/code и отдельный read-only architect/silent-failure analysis будущего egress.

Оба reviewers работали blind-first/read-only до авторского отчёта, проверили чужой код, frozen hash и обе тестовые дельты; final APPROVE/open0. Runtime выполняли автор/root. Native Claude commands/hooks не запускались. Подробности — [протокол](../reviews/G02_PAID_LEDGER_REVIEWS.md).

## 9. Проверки и evidence

Среда: Darwin arm64, Python3.13.5, uv0.11.31, Docker29.2.0, реальный PostgreSQL16 из exact Compose tag+digest. Runtime использовался последовательно: автор освободил Testcontainers перед запуском root.

| Проверка | Команда | Результат |
|---|---|---|
| TDD RED | Targeted pytest до реализации | exit2: missing module, не runtime evidence |
| Автор, первый PG apply | В backend: `.venv/bin/python -m pytest -q tests/integration/postgres/test_llm_poc_paid_ledger.py` | exit0;34passed/0failed/skipped,14.99s |
| Root, ledger + отдельные процессы/restore | В backend: `.venv/bin/python -m pytest -q tests/integration/postgres/test_llm_poc_paid_ledger_restart.py tests/integration/postgres/test_llm_poc_paid_ledger.py` | exit0;40passed/0failed/skipped,26.29s |
| Fast/static | `make pre-push-fast` | exit0;ruff0,mypy182sourcefiles0issues,15importcontracts KEPT,957passed/4warnings/0failed/skipped,8.53s |
| Snapshot generation | `make db-snapshot` | exit0;1intentional skip,4.00s — генерация, не PASS проверки drift |
| Actual drift/upgrades/security catalogue | В backend: `.venv/bin/python -m pytest -q tests/integration/postgres/test_schema_drift.py tests/integration/postgres/test_migrations.py::test_persist_001_upgrade_from_empty_reaches_head tests/integration/postgres/test_migration_safety.py::test_persist_002_upgrade_from_previous_revision_keeps_data_and_matches_snapshot tests/integration/postgres/test_audit_platform_schema.py::test_audits_clean_and_tables_exist` | exit0;6passed/0failed/skipped,8.61s; actual drift0/empty+previous upgrades |

Финальная сверка: prompts40/0issues, secret scan0findings, git diff --check0; все команды exit0. Read-only Registry/manifest/local-links checker:74canonical/73hashes0mismatch и283localfilelinks0missing. Initial40files:31byte-identical+9authorizedimplementationdocchanges; protected canonical/mirror unchanged. Frozen hashes0020–0024 повторно совпали. На checkpoint66dirtyfiles, без Git delivery. Предыдущие0023 evidence — в [отдельном отчёте](G02_model_admission_persistence_REPORT.md); они не засчитываются0024 автоматически. Исторический полный backend1901passed/3failed был до исправления legacy expectations; свежий полный green/pre-pr/Linux CI совокупной подготовки ещё не заявлены.

## 10. Проверенные security cases

Duplicate wallet; запрет runtime изменения account/cap/rates/plan, computed charge/audit actor forgery; exact refs/hash/route/plan/ticket; permanent body reuse; concurrent reserve/claim; UNKNOWN full hold/no refund; invalid usage/overrun commit-before-refusal; replay/conflicting settlements; audit failure на reserve/claim/settle; FORCE RLS/context reset и immutable history.

Отдельные процессы подтверждают pending/reserve/claim/unknown/block после выхода первого интерпретатора. Реальный pg_dump→fresh disposable DB→psql сохраняет exact rows всех четырёх таблиц, включая исторические API actor/time под ролью restore postgres. Это не физический crash/PITR/product recovery drill и не проверка provider invoice.

## 11. Независимое review

Два pre-apply DDL reviews и два final code/test reviews: APPROVE/open0; SHA0024 проверен независимо. MEDIUM/LOW исправлены и пересмотрены. Reviewer не запускал runtime/Docker и не читал авторский report до выводов. Root-owned process/restore tests и catalogue также проверены независимо. [Протокол](../reviews/G02_PAID_LEDGER_REVIEWS.md).

## 12. Ограничения

Нет private-TLS claim endpoint/сервисной capability, relay enforcement, candidate runner/stream metadata, host authorization/tariff freshness, key setup, live evidence/model human approval или SLICE. Ledger в runner без sole-egress check не защищает ceiling. Полный G156 и подготовка NOT VERIFIED; modelcalls0/cost0USD. Полный pre-pr/Linux CI/supply-chain/release/physical recovery не выполнялись на этом промежуточном checkpoint.

## 13. Контекст

Обновлены ADR133/ADL, passport/plan, HANDOFF/STATUS/ECC, traceability/gaps и report/review. Canonical/mirror локальные изменения сохранены без новых правок. Общая подготовка IN_PROGRESS; S17/S20/S21 NOT_STARTED.

## 14. DoD компонента

✅Код/forward migration, real PG40cases, coherent balance regression, process/restore, empty+previous/drift, static/fast и два final independent reviews. ❌Полный candidate paid path/human approval/SLICE. Локально TESTED ledger не означает готовность всей подготовки.

## 15. Следующий безопасный шаг

Отдельный узкий candidate egress seam по плану§6: private TLS backend claim для LLM_GATEWAY, versioned final-bytes binding, однократный dispatch у relay без DB credentials, затем bounded runner. После сводных gates — конкретный безопасный key setup, live evidence и human acceptance. SLICE01 имеет собственные данные/лицензию/бюджет. При полной готовности подготовки уведомить владельца и ждать нового согласия на G02.
