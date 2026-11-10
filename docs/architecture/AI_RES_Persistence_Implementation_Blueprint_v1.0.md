# AI RES — Persistence Implementation Blueprint

**Версия:** 1.0  
**Дата:** 2026-11-10  
**Статус:** BASELINED implementation blueprint для PostgreSQL persistence slice; репозиторный scaffold и migration examples являются implementation assets, но live deployment не заявляется.  
**Назначение:** закрыть переход от архитектурной модели PostgreSQL к воспроизводимой реализации Alembic, access control, migration operations и acceptance tests.

## 1. Цель и границы

Blueprint определяет реализационный контракт для `ai_res_db` по доменному execution slice: Operation, Task association, WorkerRun, ReadinessEvaluation, event history, Outbox/Inbox, idempotency. Он дополняет, но не заменяет Domain Model, Physical Model, Migration & Access Strategy и Event Model.

Вне области: миграции Temporal `temporal_db`, LangGraph checkpoint store, MinIO object content, полная миграция всех доменных bounded contexts. Эти хранилища имеют независимых владельцев и runbooks.

**Нормативное разделение:**
- PostgreSQL `ai_res_db` — источник истины доменных состояний и delivery records.
- Alembic — единственный schema migration authority для AI RES PostgreSQL schemas.
- SQLAlchemy 2.x — application persistence/query layer; ORM не является источником доменных правил.
- Domain/Application Services — единственный путь доменных записей.
- Runtime agents не получают прямые DB credentials.
- Temporal RPC, LLM, HTTP, MinIO и другие внешние действия не выполняются внутри DB-транзакции.

## 2. Принятый технологический baseline

| Компонент | Решение | Обоснование / ограничение |
|---|---|---|
| PostgreSQL | PostgreSQL 16+ (MVP baseline) | Использовать конкретный minor release из lock/deployment manifest; обновления minor отдельно тестировать |
| Driver | psycopg 3 | Современный поддерживаемый PostgreSQL driver; async API — только если backend выбрал async stack целиком |
| ORM / SQL | SQLAlchemy 2.x | Typed Core/ORM; критические concurrency операции выражать явным SQL |
| Migrations | Alembic | Версионированные immutable revisions; autogenerate только как draft |
| Migration execution | Отдельный one-shot job | Не запускать миграции при старте API/Runtime |
| Isolation | READ COMMITTED | Row locks, unique constraints, compare-and-swap; SERIALIZABLE точечно и с retry |
| Pool | SQLAlchemy pool / PgBouncer transaction mode only after compatibility test | Session state запрещён; tenant context transaction-local |
| Test DB | Реальный PostgreSQL того же major | SQLite не считается заменой PostgreSQL для integration/RLS/concurrency tests |
| Test harness | pytest + pytest-postgresql/Testcontainers (выбрать один в repo) | CI должен запускать PostgreSQL integration tests |

Версии пакетов фиксируются lock-файлом. Нельзя использовать плавающие `latest` в production image.

## 3. Обязательная структура репозитория

```text
backend/
  pyproject.toml
  alembic.ini
  src/ai_res/
    db/
      __init__.py
      base.py                 # metadata registry; import all mapped models
      engine.py               # runtime engine, pool, TLS, timeouts
      session.py              # transaction/session factories
      tenant_context.py       # transaction-local context helper
      migrations/
        env.py
        script.py.mako
        versions/
          0001_platform_schemas_and_roles.py
          0002_execution_core_tables.py
          0003_operation_task_worker_run_constraints.py
          0004_event_outbox_inbox_idempotency.py
          0005_readiness_and_rls.py
          0006_indexes_and_constraints_validate.py
    modules/
      operations/repository.py
      tasks/repository.py
      worker_runs/repository.py
      readiness/repository.py
      events/outbox_repository.py
      events/inbox_repository.py
      idempotency/repository.py
  tests/
    unit/domain/
    integration/postgres/
      conftest.py
      test_migrations.py
      test_constraints.py
      test_rls_isolation.py
      test_transaction_context.py
      test_outbox_inbox.py
      test_idempotency_concurrency.py
      test_aggregate_sequence.py
      test_backfill_resume.py
    contract/
  ops/postgres/
    preflight.sql
    postflight.sql
    role_grants.sql
    backup_restore_checklist.md
```

Если репозиторий использует другой Python package layout, можно изменить каталоги, но границы и обязанности компонентов должны сохраниться. Не создавать параллельный Alembic environment для каждой схемы в рамках одной `ai_res_db`, если нет отдельного deployment lifecycle и owner.

## 4. Alembic configuration contract

### 4.1. Единственный migration head

MVP использует один Alembic version table в отдельной технической схеме `platform`, например `platform.alembic_version`. Один deployment job применяет ревизии к allowlist схем `operations`, `work`, `agents`, `execution`, `audit`, `platform` и другим явно зарегистрированным AI RES схемам.

Запрещено:
- сканировать/изменять `temporal`, `public` или схемы сторонних компонентов без отдельного решения;
- использовать `Base.metadata.create_all()` в production;
- выполнять `alembic upgrade head` при старте каждого API/Runtime replica;
- редактировать уже применённую revision; исправление — новая revision;
- принимать autogenerate без ручного diff review.

### 4.2. env.py requirements

`env.py` обязан:
1. Получать DSN только из environment/Secret Manager; не сохранять секрет в `alembic.ini`.
2. Использовать migration identity, не runtime identity.
3. Устанавливать `version_table_schema="platform"`.
4. Ограничивать `include_name`/`include_object` явным allowlist схем и объектов.
5. Не включать системные и Temporal schemas в metadata diff.
6. Настраивать `compare_type=True`, `compare_server_default` осознанно; каждое отличие проверяется вручную.
7. Запускать online migrations с `lock_timeout` и `statement_timeout`, установленными по migration profile.
8. Поддерживать offline SQL generation для review, но не считать её заменой реального upgrade test.
9. Запрещать application startup выполнять migration.

### 4.3. Revision policy

Формат revision: `<short_hash>`; filename: `<sequence>_<intent>.py`. Revision содержит `revision`, `down_revision`, `branch_labels`, `depends_on`, `upgrade()`, `downgrade()`.

- Каждая revision выполняет одну логическую, reviewable цель.
- Имена constraints/indexes стабильны и явно задаются.
- Data backfill отделяется от schema DDL для больших наборов.
- `CREATE INDEX CONCURRENTLY` выполняется в Alembic autocommit block; revision помечается как требующая отдельного operational runbook, учитывая, что concurrent build может оставить invalid index при сбое.
- `NOT VALID` FK/CHECK затем валидируется отдельным шагом через `VALIDATE CONSTRAINT`.
- Downgrade допустим только для обратимого изменения без потери пользовательских данных. В остальных случаях downgrade явно raises `NotImplementedError` с forward-fix/restore инструкцией; нельзя делать вид, что destructive downgrade безопасен.

## 5. Каноническая цепочка миграций для persistence slice

| Revision | Назначение | Контрольный gate |
|---|---|---|
| PDB-0001 | Создание схем, owner/role grants, Alembic version schema | Сверить schema allowlist и privileges |
| PDB-0002 | Создание Operation и event history | PK/FK/check/index validation |
| PDB-0003 | Expand Task.operation_id nullable + composite unique support | Не включать NOT NULL до mapping |
| PDB-0004 | Создание WorkerRun и lineage; FK после подготовки Task key | Проверить ownership/cardinality |
| PDB-0005 | ReadinessEvaluation и check results | Composite FK на evaluation |
| PDB-0006 | Outbox, Inbox, idempotency records | Уникальности event/destination/consumer/key scope |
| PDB-0007 | Tenant RLS policies + FORCE + grants | Runtime role isolation tests |
| PDB-0008 | Legacy Task→Operation backfill (separate resumable job) | Zero orphan / duplicate mapping |
| PDB-0009 | Validate FK/CHECK, Task.operation_id NOT NULL | Explicit data validation sign-off |
| PDB-0010 | Concurrent indexes, final query indexes, cleanup | Query plan and lock review |

Реальные revision IDs и dependency graph генерируются в репозитории. Эта таблица — целевой порядок, а не утверждение, что миграции уже созданы/применены.

## 6. Legacy Task backfill — обязательный безопасный алгоритм

Нельзя автоматически создавать Operation на каждую существующую Task без анализа: старые Task могут принадлежать разным пользовательским командам, Epic или планам. Mapping должен быть построен по надёжному источнику происхождения (command/run/plan/execution batch). Если источник отсутствует или неоднозначен — запись отправляется в exception report для ручного решения; не придумывать связь.

Backfill protocol:
1. Создать mapping table `platform.task_operation_backfill_map(task_id PK, operation_id, mapping_source, mapping_confidence, approved_by, approved_at, batch_id)`.
2. Создать Operation для доказуемых исторических групп команд; сохранить provenance и пометить `initiator_type=SYSTEM` / migration reason.
3. Вставлять mapping пакетами по стабильному cursor (например, `tasks.id > last_seen_id`), не OFFSET.
4. Для каждого batch: `UPDATE work.tasks ... WHERE operation_id IS NULL`, commit, записать checkpoint и counts в migration ledger.
5. Повторный запуск безопасен: `WHERE operation_id IS NULL`; конфликт mapping — остановка и quarantine.
6. Проверить `NULL count = 0`, отсутствие cross-project/org mismatch, отсутствие task с несколькими mapping.
7. Добавить FK `NOT VALID`, затем `VALIDATE CONSTRAINT`.
8. Только после approval установить `NOT NULL`.
9. Сохранить mapping/audit report в течение установленного retention; не удалять legacy identifiers до подтверждённого cutover.

Для исторических Task без достоверной команды использовать отдельную явно утверждённую synthetic/migration Operation class (например `LEGACY_IMPORT`) только если domain owner подтвердит семантику. Не маскировать неизвестное происхождение под пользовательскую команду.

## 7. Transaction and repository implementation contract

### 7.1. Общие правила

- Каждая Application Service operation открывает явную транзакцию `BEGIN → domain checks → writes → COMMIT`.
- Репозитории не делают скрытый commit и не открывают независимую транзакцию внутри use case.
- Нельзя возвращать ORM объект, который будет лениво читать БД после закрытия транзакции; возвращать DTO/snapshot.
- Любая доменная мутация проверяет organization/project ACL до изменения и повторно применяет scope в SQL predicates/RLS.
- Aggregate transition использует `SELECT ... FOR UPDATE` или compare-and-swap `WHERE row_version=:expected`; проверяет state transition в domain layer.
- Обновление projection, event history, aggregate sequence/version и outbox destinations — одна DB transaction.
- Никаких network/LLM/Temporal calls внутри транзакции. Сначала commit command/outbox; dispatcher выполняет внешний вызов после commit.
- Не использовать `SELECT MAX(sequence)+1`; блокировать aggregate row, increment `last_event_sequence` и `row_version` атомарно.
- Deadlock/serialization failures: ограниченный retry всего use case с jitter, только если операция идемпотентна; не retry произвольных side effects.

### 7.2. Unit of Work

`ApplicationService` владеет Unit of Work. Внутри него repositories получают одну Session/Connection. Domain logic принимает загруженные aggregate и immutable command DTO. DB adapters реализуют persistence; доменные модели не импортируют SQLAlchemy.

### 7.3. Transaction-local tenant context

В начале каждой транзакции после серверной аутентификации и authorization service выставляет `SET LOCAL` / `set_config(..., true)` для organization/project context. Контекст никогда не выставляется через session-level `SET`, не передаётся от клиента напрямую и не сохраняется между транзакциями. При pool reuse отсутствие контекста должно приводить к default-deny.

RLS дополняет, но не заменяет object-level Policy Engine. Shared API database identity + arbitrary SQL compromise может позволить подменить custom GUC; поэтому защищаем SQL injection, ограничиваем query surface, используем параметризованные запросы и не выдаём агентам DB credentials.

## 8. Connection and pool policy

- Runtime connection URL/credentials — отдельные для API, Outbox Dispatcher, Event Consumer, Auditor и Migrator.
- `application_name` обязателен и включает service + deployment/version, без пользовательских данных.
- TLS verify-full для сетевого PostgreSQL; SCRAM-SHA-256; certificate/secret rotation без логирования DSN.
- `pool_pre_ping=True`; pool recycle — настраиваемый operational value.
- Transaction pooler допустим только при отсутствии session-level state, temp-table reliance и prepared-statement incompatibility; протестировать выбранный PgBouncer mode с драйвером/ORM.
- Установить statement/lock/idle-in-transaction timeouts. Долгие backfills используют отдельное соединение/job и не удерживают транзакцию на весь процесс.
- `idle_in_transaction_session_timeout` включён с согласованным значением; длительные workflow ожидания никогда не удерживают DB transaction.
- DB unavailable → protected domain mutation fails closed; read degradation допустим только по explicit endpoint policy.

## 9. RLS, grants и security acceptance

1. Owner `ai_res_owner` — NOLOGIN; schema/table ownership только у owner/migration principal по контролируемой процедуре.
2. `ai_res_migrator` получает DDL только для allowlisted AI RES schemas; не получает SUPERUSER/BYPASSRLS.
3. Runtime roles не имеют CREATE/ALTER/DROP, ownership, TRUNCATE, broad DELETE, `BYPASSRLS`, `CREATEROLE`, `CREATEDB`.
4. `FORCE ROW LEVEL SECURITY` включён на tenant scoped tables, где это применимо; policy учитывает organization и project.
5. Default privileges настроены так, чтобы новые таблицы не становились автоматически доступными PUBLIC/runtime.
6. PUBLIC лишён CREATE на database schemas; `search_path` фиксируется/защищается, в SQL используются schema-qualified names.
7. Worker/Manager Runtime не имеют DB network route и DB secrets. API не передаёт DSN в tool/LLM context.
8. Outbox dispatcher получает только нужные SELECT/UPDATE/lease permissions; event consumer — ограниченные Inbox + owned projection operations через application service, не широкую запись во все схемы.
9. Audit reader — SELECT-only на разрешённые views/columns, с ACL redaction.
10. Backup role имеет только необходимые backup privileges и не используется приложениями.

## 10. Migration deployment pipeline

### Pre-deployment
- registry/spec version check;
- migration head and branch check (single head required unless explicitly reviewed);
- schema drift report;
- database connectivity and version check;
- backup/PITR status and restore evidence for risky/contract changes;
- free disk, replication lag (if applicable), long-running transactions and lock holders;
- preflight SQL + permissions check;
- compatibility check: old app version works with expanded schema.

### Deployment
1. Maintenance/feature flag decision based on migration class.
2. Execute one-shot Alembic job with migrator credentials.
3. Apply additive schema revisions.
4. Run resumable backfill as separate job with batch size, checkpoint, rate limit and stop control.
5. Validate counts, FKs, constraints, RLS and application dual-read/dual-write if applicable.
6. Deploy application version that uses new fields/contracts.
7. Observe errors/latency/locks and outbox lag.
8. Run contract revision only after explicit approval and rollback/forward-fix decision.

### Post-deployment
- alembic current == expected head;
- no multiple heads/unapplied revisions;
- constraints valid;
- orphan/NULL checks pass;
- runtime role privilege diff passes;
- RLS isolation suite passes;
- outbox/inbox health and backlog within thresholds;
- application smoke and recovery checks pass;
- deployment evidence stored in release record.

## 11. Rollback, forward-fix and restore

DB migrations are not presumed reversible. Policy:
- additive/expand revision: rollback usually by application rollback; schema can remain safely expanded;
- backfill: pause/resume; reverse mapping only if proven lossless and approved;
- contract/destructive revision: no blind downgrade; forward-fix preferred; restore/PITR only with explicit data-loss/RPO decision and cross-store Recovery Manifest;
- restoring `ai_res_db` requires reconciliation with MinIO object versions, Temporal executions, external side effects and event delivery state;
- Temporal DB is never rolled back using AI RES Alembic.

Before production contract: backup restore rehearsal on isolated environment and evidence of DB + MinIO + workflow reconciliation. Existing RPO/RTO remain targets until measured.

## 12. Test and acceptance matrix

| ID | Test | Expected result | Gate |
|---|---|---|---|
| PERSIST-001 | Alembic upgrade empty DB | Reaches expected head | Required |
| PERSIST-002 | Upgrade previous supported revision | Data preserved, no drift | Required |
| PERSIST-003 | One head / revision graph | No accidental branches | Required |
| PERSIST-004 | Offline SQL review | SQL matches reviewed revision | Required |
| PERSIST-005 | Runtime role DDL attempt | Permission denied | Required |
| PERSIST-006 | Runtime role TRUNCATE/DELETE protected rows | Permission denied | Required |
| PERSIST-007 | Owner/BYPASSRLS flags | Runtime has neither | Required |
| PERSIST-008 | Tenant A reads Tenant B | Zero rows / denied | Required |
| PERSIST-009 | Missing tenant context | Default deny | Required |
| PERSIST-010 | Connection pool context reuse | No tenant leakage | Required |
| PERSIST-011 | Cross-project forged IDs | Denied by Policy + RLS | Required |
| PERSIST-012 | Event sequence concurrent updates | Unique contiguous sequence per successful event (no duplicate) | Required |
| PERSIST-013 | Idempotency same key/fingerprint concurrency | One resource, same response | Required |
| PERSIST-014 | Same key, different fingerprint | `IDEMPOTENCY_KEY_REUSED` | Required |
| PERSIST-015 | Outbox crash after publish before mark | Duplicate delivery safely deduped | Required |
| PERSIST-016 | Inbox crash before commit | No partial local effect | Required |
| PERSIST-017 | Backfill stop/restart | Safe resume, no duplicate mappings | Required |
| PERSIST-018 | FK NOT VALID then VALIDATE | Validation detects orphan | Required |
| PERSIST-019 | Concurrent index interrupted | Invalid index detected and repaired | Required |
| PERSIST-020 | Alembic lock timeout | Deployment fails safely, no hidden partial contract | Required |
| PERSIST-021 | Backup restore rehearsal | Recovery manifest reconciled | Production gate |
| PERSIST-022 | Secret rotation | New credentials work; old revoked | Required |
| PERSIST-023 | Manager/Worker Runtime DB access | No secret and no network path | Required |
| PERSIST-024 | Schema drift | CI fails | Required |

PostgreSQL integration tests MUST run against actual PostgreSQL major used by deployment. SQLite-only tests do not satisfy these criteria.

## 13. Deliverables Claude Code must create

1. `pyproject.toml` with pinned SQLAlchemy/Alembic/psycopg/test dependencies.
2. `alembic.ini` without secrets.
3. `src/ai_res/db/migrations/env.py` with schema allowlist and metadata imports.
4. Initial reviewed revisions and a single migration head.
5. SQLAlchemy engine/session/Unit of Work and transaction-local tenant context helper.
6. Repositories and Application Services for Operation/Task/WorkerRun/ReadinessEvaluation/Event Outbox/Inbox/Idempotency.
7. Role/grant/RLS migration revisions and deployment role provisioning script.
8. Preflight/postflight SQL and backfill CLI with checkpoint/resume/dry-run/report.
9. PostgreSQL integration and security acceptance suite.
10. CI jobs: migration upgrade, schema drift, RLS/grants, tests, artifact validation.
11. Operational runbooks for upgrade, backfill, validate, contract, forward-fix, restore, credentials rotation.
12. Release evidence: migration head, checksums, test reports, role grants diff, RLS results, backup/restore evidence.

## 14. Definition of Done

Persistence Implementation Blueprint is implemented only when:
- repository contains the migration environment and pinned dependencies;
- fresh DB upgrade and supported upgrade path pass;
- one migration head and schema allowlist are enforced;
- RLS and role tests pass under real non-owner DB roles;
- backfill is dry-run validated and restartable;
- Operation/WorkerRun event+projection+Outbox atomicity tests pass;
- Inbox dedupe and idempotency concurrency tests pass;
- preflight/postflight and recovery runbooks exist;
- backup restore/reconciliation evidence exists before production contract migration;
- Document Registry and implementation evidence reflect actual state.

Документирование/создание scaffold не равно runtime implementation. До исполнения этих критериев статус остаётся `DESIGN BASELINED / IMPLEMENTATION NOT VERIFIED`.

## 15. Cross-document requirements

Нормативные детали распределены по:
- `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md` — таблицы, constraints, transactions;
- `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md` — migration/access policies;
- `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md` — persistence ownership and relations;
- `AI_RES_Process_Design_and_Algorithms_v1.8.md` — migration/runtime transaction processes;
- `AI_RES_Identity_Access_Control_v1.3.md` — identity and DB role boundary;
- `AI_RES_Infrastructure_Deployment_Operations_v1.7.md` — deployment and operations;
- `AI_RES_API_and_Interaction_Contracts_v1.9.md` — API/Application Service DB boundary;
- `AI_RES_Operation_WorkerRun_Event_Model_v1.3.md` — event persistence mapping;
- `AI_RES_Claude_Code_Implementation_Spec_v1.19.md` — implementation order and DoD;
- `AI_RES_Document_Registry_v3.8.md` — current document index.
