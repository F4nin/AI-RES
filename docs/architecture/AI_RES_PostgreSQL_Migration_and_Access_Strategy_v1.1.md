# AI RES — Стратегия миграций и модель доступа PostgreSQL

**Версия:** 1.1  
**Дата:** 10.11.2026  
**Статус:** BASELINED design decision для PostgreSQL `ai_res_db`; production rollout требует исполнения migration runbook, threat review и runtime tests.  
**Область:** миграции схем AI RES, роли PostgreSQL, привилегии, RLS, service identity, секреты, аудит и проверка доступа.

## 1. Принятые решения

1. Для доменной БД `ai_res_db` выбирается **Alembic + SQLAlchemy 2.x** как единый migration toolchain MVP. Это соответствует Python-ориентированному Backend/agent stack и позволяет версионировать DDL, data migrations и проверки в одном репозитории.
2. Alembic используется только для AI RES domain database. Миграции Temporal (`temporal_db`), LangGraph checkpoint storage и сторонних компонентов имеют отдельных владельцев и процедуры; Alembic AI RES не изменяет их схемы.
3. Все миграции — immutable, последовательные revision scripts с уникальными revision IDs, parent revision и обязательным review. `alembic revision --autogenerate` допускается только как генератор кандидата; результат всегда вручную проверяется и редактируется.
4. Изменения с несовместимостью выполняются по схеме **expand → backfill/migrate → validate → contract**. Destructive contract migration — отдельный релиз/approval после подтверждения отсутствия старых consumers и успешного backup/restore rehearsal.
5. Применение миграций выполняется отдельной deployment job с отдельной credential и ролью `ai_res_migrator`; API/Manager/Worker не выполняют DDL и не имеют membership в роли владельца схем.
6. Владелец схем/объектов — `ai_res_owner NOLOGIN`. `ai_res_migrator` может временно `SET ROLE ai_res_owner` в миграционной сессии; credential владельца не существует.
7. Runtime доступ предоставляется раздельным LOGIN identities для API, Outbox Dispatcher, Event Consumer, Read-only Operations и Backup. Manager Runtime и Worker Runtime **не получают прямых PostgreSQL credentials**; обращаются к доменным Application Services через внутренние аутентифицированные API/activities.
8. Runtime роли не являются владельцами объектов, не имеют `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`, `TRUNCATE`, `REFERENCES`, `TRIGGER`, `CREATE` в прикладных схемах или права менять политики.
9. `PUBLIC` лишается `CREATE` в `public`; доступ к схемам и таблицам выдаётся явными минимальными GRANT. `search_path` runtime ролей фиксируется на `pg_catalog`; приложение использует schema-qualified names.
10. RLS включается и принудительно применяется (`ENABLE` + `FORCE`) на tenant-scoped таблицах. Политики ограничивают `organization_id` и, где применимо, `project_id` контекстом текущей транзакции. RLS — дополнительный барьер против ошибок запросов, а не замена Policy & Permission Engine.
11. Контекст tenant/project передаётся через transaction-local settings (`set_config(..., true)`) после успешной серверной авторизации. Пул соединений не должен переносить контекст между транзакциями. Отсутствующий/пустой контекст даёт default-deny.
12. Поскольку одна общая runtime DB identity технически может задавать custom GUC, GUC-based RLS **не считается защитой от полностью скомпрометированного API process или произвольного SQL под этой ролью**. Это явно учитывается в threat model. Защита обеспечивается сочетанием API Policy Engine, параметризованных запросов, запрета произвольного SQL из LLM/Worker, узких DB grants, изоляции сетей и RLS как defense-in-depth.
13. RLS policy expressions не вызывают небезопасные `SECURITY DEFINER` функции. Если такая функция когда-либо необходима, отдельный security review обязателен: фиксированный безопасный `search_path`, полностью квалифицированные имена, минимальные права владельца, запрет динамического SQL без строгой валидации.
14. DB credentials выдаются через Secret Management, не хранятся в Git, Compose YAML, образах, prompt, Temporal payload или логах. Ротация поддерживает overlap двух credentials и rollout без простоя.
15. TLS обязателен для сетевых подключений к PostgreSQL вне loopback/private isolated socket; `pg_hba.conf` использует `hostssl` и SCRAM-SHA-256. Доступ по сети ограничен backend network и конкретными service identities.

## 2. Ролевая модель PostgreSQL

PostgreSQL roles не совпадают с бизнес-ролями AI RES (Analyst, Reviewer, Project Admin). Бизнес-доступ остаётся в IAM/Policy Engine. DB roles определяют полномочия процесса.

| Роль | LOGIN | Назначение | Разрешённые полномочия |
|---|---:|---|---|
| `ai_res_owner` | Нет | Владение схемами/объектами | DDL и полный контроль; недоступна приложению |
| `ai_res_migrator` | Да | Deployment migration job | `SET ROLE ai_res_owner`; не используется runtime |
| `ai_res_api` | Да | Backend Application Services | Минимальные SELECT/INSERT/UPDATE по доменным таблицам; без DELETE/DDL/TRUNCATE |
| `ai_res_outbox_dispatcher` | Да | Доставка Outbox | SELECT/UPDATE только Outbox; SELECT event envelope по необходимости |
| `ai_res_event_consumer` | Да | Обработка событий | SELECT/INSERT/UPDATE только Inbox и необходимые event records; domain aggregate mutation только через API |
| `ai_res_auditor` | Да | Read-only аудит | SELECT на явно разрешённые audit views/tables; без чтения секретных payload |
| `ai_res_backup` | Да | Backup/restore job | Отдельная контролируемая backup privilege profile; не runtime identity |
| `ai_res_manager_runtime` | Нет/не создаётся | Manager process | Нет DB credential; внутренний API |
| `ai_res_worker_runtime` | Нет/не создаётся | Worker process | Нет DB credential; scoped tool/API gateway |

LOGIN role names для конкретного окружения могут иметь suffix (`_dev`, `_stage`, `_prod`) и индивидуальные credentials. Групповые NOLOGIN роли — единый шаблон прав. Пароли не задаются SQL migration; credentials provisioned внешним Secret Manager/оператором.

### 2.1 Ownership и GRANT

- `ai_res_owner` — `NOLOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`.
- `ai_res_migrator` — отдельный LOGIN principal, `NOINHERIT`; deployment явно выполняет `SET ROLE ai_res_owner` после подключения.
- Runtime roles не владеют таблицами и не могут `SET ROLE ai_res_owner`.
- В `public` запрещён `CREATE` для `PUBLIC`; runtime `search_path` — `pg_catalog`.
- Для новых таблиц default privileges закрыты по умолчанию; GRANT добавляются в той же migration revision, что и таблица.
- Не использовать широкие `GRANT ALL ON ALL TABLES` для runtime.
- Не выдавать `pg_read_all_data`, `pg_write_all_data`, `pg_execute_server_program`, `pg_read_server_files` и `pg_write_server_files` runtime identities.

## 3. RLS и tenant isolation

### 3.1. Где включать RLS

RLS + FORCE применяется ко всем доступным через API таблицам, содержащим tenant/project data, включая минимум:

- `operations.operations`;
- `work.tasks`;
- `agents.worker_runs`;
- `execution.readiness_evaluations` и `execution.readiness_check_results`;
- `operations.operation_events` и `agents.worker_run_events` через проверку родительского aggregate;
- другие project-scoped таблицы AI RES, включённые в public/application query surface.

Технические таблицы Outbox/Inbox не открываются API/Frontend. Для них используются отдельные schema/table grants и собственные consumer identities; RLS не заменяет изоляцию доступа к delivery internals.

### 3.2. Transaction context

После проверки пользовательской/сервисной identity и Policy Engine, Application Service начинает транзакцию и устанавливает контекст:

```sql
SELECT set_config('app.organization_id', :organization_id::text, true);
SELECT set_config('app.project_id', :project_id::text, true);
```

Третий аргумент `true` обязателен: значение действует только в текущей транзакции и очищается при её завершении. Контекст устанавливается заново для каждой транзакции/checkout из пула. Нельзя использовать session-level `SET` в pooled connections.

RLS policy использует `NULLIF(current_setting('app.organization_id', true), '')::uuid`; NULL/отсутствующее значение не разрешает строки. Для таблиц с `project_id` проверяется также project context. Для таблиц без project scope — organization scope.

### 3.3. Границы RLS

- RLS не делает скрытые объекты автоматически безопасными в search, RAG, graph traversal, export, cache и event history: каждый путь обязан вызывать Policy Engine и применять ACL до раскрытия метаданных/содержимого.
- RLS не защищает от superuser, `BYPASSRLS` и владельца таблицы, если не включён FORCE. Runtime identities не получают эти свойства.
- Не считать GUC-контекст криптографически доверенным от скомпрометированного процесса с правом произвольного SQL.
- RLS policies должны тестироваться под реальными runtime roles, а не только под owner/superuser.
- Каждая новая tenant-scoped таблица должна иметь RLS policy и negative tests в той же миграции/PR. CI должен выявлять таблицы с `organization_id`/`project_id`, где RLS не включён.

## 4. Alembic migration strategy

### 4.1. Структура репозитория

```text
backend/
  db/
    metadata.py
    session.py
    migrations/
      env.py
      script.py.mako
      versions/
        <revision>_expand_....py
        <revision>_backfill_....py
        <revision>_contract_....py
    migration_checks/
      preflight.sql
      postflight.sql
      rls_coverage.sql
      grants_audit.sql
```

`env.py` подключает только `ai_res_db`, включает `include_schemas=True`, явный allowlist схем AI RES, naming convention для constraints и `compare_type=True`. `compare_server_default` включается осознанно после проверки drift. Схемы `temporal`, `langgraph` и extension/system schemas исключаются из domain migration ownership.

### 4.2. Правила revision

- Один revision — один логически связанный change set; revision ID неизменяем.
- Явные имена PK/FK/UK/CK/IX обязательны.
- Autogenerate не является источником истины: candidate diff вручную проверяется, особенно rename, CHECK, partial/expression indexes, triggers, RLS, grants, policies, partitioning и SQL functions.
- DDL/RLS/GRANT предпочтительно описывать явным SQL в revision (`op.execute`) с тестируемыми pre/postconditions.
- Не использовать `CREATE TABLE IF NOT EXISTS` как механизм миграционной идемпотентности. Alembic revision ledger гарантирует однократное применение; drift должен приводить к fail-fast.
- Revision должна иметь upgrade path; downgrade допускается только для обратимых additive changes. Для irreversible data transformations downgrade явно запрещён и описан forward-fix/restore plan.
- Migration job сериализуется (один migrator на DB); advisory lock может использоваться как дополнительная защита от параллельного запуска.
- Миграции запускаются отдельной job до переключения API на новую версию; API startup не запускает auto-migrate.

### 4.3. Expand → Backfill → Validate → Contract

**Expand:** добавить nullable column/table/index concurrently где возможно; добавить FK/CHECK как `NOT VALID` и затем `VALIDATE CONSTRAINT`; добавить dual-read/dual-write compatibility при необходимости. Старое приложение продолжает работать.

**Backfill:** отдельная resumable job с keyset pagination, ограниченными batch, checkpoint, rate limit, metrics и retry. Не выполнять большой backfill в одной долгой транзакции. Повторный запуск должен быть безопасным.

**Validate:** проверить counts, null/orphan checks, referential integrity, row checksums/sample, application compatibility, query plans, lock duration, RLS/grants. Записать evidence в deployment artifact.

**Contract:** только после подтверждения всех consumers — установить NOT NULL, переключить код на новое поле, удалить legacy path/column/constraint в отдельном релизе. Перед destructive step — backup/PITR readiness, restore test и explicit approval.

### 4.4. PostgreSQL operational rules

- Для больших таблиц индексы создавать `CREATE INDEX CONCURRENTLY` в отдельной Alembic revision с `autocommit_block`; учесть, что команда не выполняется внутри обычного transaction block.
- FK/CHECK на большие существующие таблицы добавлять `NOT VALID`, затем `VALIDATE CONSTRAINT` отдельно.
- Оценивать lock level и duration каждой миграции на production-like dataset; задать `lock_timeout` и `statement_timeout` для deployment migration session.
- Не менять типы/колонки с потенциальным table rewrite без оценки объёма и maintenance window.
- Не удалять старые колонки/таблицы в том же релизе, в котором код перестал их использовать.
- После миграции анализировать `pg_stat_user_tables`, `pg_stat_progress_create_index`, `pg_locks`, bloat/vacuum; `ANALYZE` после массового backfill.
- PITR/pgBackRest и MinIO backup остаются отдельными процессами; миграция не считается rollback-ом данных.

## 5. Legacy mapping Operation для существующих Task

`work.tasks.operation_id` остаётся nullable на Expand. До Contract требуется deterministic mapping:

1. Создать Operation для исторических Task по утверждённой группировке исходного пользовательского/системного запроса; если надёжной группировки нет — создать отдельную legacy-import Operation для каждой Task, не выдумывать общую родительскую команду.
2. Сохранить `legacy_source_type`, `legacy_source_id`, `mapping_method`, `mapping_confidence`, `mapped_at` в migration mapping table/audit evidence.
3. Не создавать фиктивные WorkerRuns задним числом, если исходный run evidence отсутствует.
4. Backfill `operation_id` пакетами, сверить количество Task до/после, orphan count = 0, duplicate mapping = 0.
5. Добавить composite unique/FK `NOT VALID` (если поддерживается выбранным ограничением), validate; затем `SET NOT NULL` отдельной contract revision.
6. Rollback после начала contract — forward-fix или PITR; не удалять созданные Operation/events, если они уже использованы.

## 6. Migration runbook

1. Проверить registry/baseline и совместимость приложения с целевой схемой.
2. Проверить свободное место, replication/backup health, WAL capacity, lock blockers и длительные транзакции.
3. Создать/проверить backup + PITR recovery point; для production изменений — restore rehearsal на отдельной среде.
4. Запустить preflight checks; мигратор получает временный доступ.
5. Выполнить Alembic upgrade одной deployment job; логировать revision, DB identity, start/end, duration и outcome без секретов.
6. Выполнить postflight, RLS coverage, grants audit, schema drift checks.
7. Развернуть совместимую версию приложения; выполнить smoke/integration tests.
8. После окна наблюдения — отдельный contract migration с approval.
9. Сохранить migration evidence и обновить Document Registry/Release Manifest.

При ошибке: остановить deployment; определить, завершилась ли транзакция revision; проверить Alembic version table и фактический schema state. Не выполнять слепой повтор/ручное удаление объектов. Исправить миграцию новой revision либо восстановить PITR по runbook.

## 7. Rotation и lifecycle credentials

- Секреты DB находятся во внешнем Secret Manager или защищённом deployment secret store; не в `.env` tracked files.
- Для ротации создать новый login principal/credential, назначить ту же group role, обновить connection pool, убедиться в успешных health checks, затем отозвать старый credential.
- Не ротировать `ai_res_owner`: он NOLOGIN.
- `ai_res_migrator` включать только на время deployment; после job отключать LOGIN/credential согласно operational policy.
- Утечка runtime credential требует revoke/rotate, завершения активных сессий, расследования и проверки audit logs.
- Connection pool: короткий checkout scope, transaction-local tenant context, `DISCARD ALL`/reset strategy при необходимости; не полагаться на connection reuse для security context.

## 8. Требования и acceptance criteria

| ID | Требование | Проверка |
|---|---|---|
| DBM-001 | Все domain migrations управляются Alembic | Fresh DB upgrade и upgrade from previous revision проходят CI |
| DBM-002 | Temporal/LangGraph schemas не управляются Alembic AI RES | Migration allowlist test |
| DBM-003 | Migration scripts immutable, reviewed, named constraints | CI lint + code review |
| DBM-004 | Несовместимые изменения проходят expand/backfill/validate/contract | Migration plan и compatibility tests |
| DBM-005 | Backfill resumable и bounded | Повторный запуск, interruption/resume test |
| DBM-006 | Runtime identities не имеют DDL/owner/BYPASSRLS | `pg_roles`, `has_table_privilege`, `has_schema_privilege` assertions |
| DBM-007 | Manager/Worker Runtime не имеют DB credentials | Deployment secret inventory + network test |
| DBM-008 | RLS FORCE + default-deny на tenant tables | Tests под runtime login roles, без owner/superuser |
| DBM-009 | Tenant context transaction-local | Pool reuse test: tenant A then B; no context leakage |
| DBM-010 | Отсутствующий context возвращает 0 rows/denies writes | Negative tests |
| DBM-011 | Policy Engine остаётся authoritative для ACL | BOLA/IDOR/search/RAG/export tests |
| DBM-012 | `public` CREATE отозван; search_path безопасен | Privilege/search_path audit |
| DBM-013 | DB credentials externalized and rotatable | Rotation drill |
| DBM-014 | TLS/SCRAM/network restrictions enforced | pg_hba inspection + connection tests |
| DBM-015 | Production migration имеет backup/PITR/restore evidence | Release gate |
| DBM-016 | Schema owner and migrator are separate from runtime | Role membership audit |
| DBM-017 | New tenant-scoped tables cannot omit RLS silently | CI RLS coverage check |

## 9. Явные ограничения и риски

- GUC-based RLS не защищает от злоумышленника, уже исполняющего произвольный SQL под общей API DB identity. Для более сильной изоляции потребуется отдельная модель credential/connection per tenant либо DB-side trusted identity assertion; это не вводится в MVP из-за сложности эксплуатации.
- RLS policy performance зависит от индексов на tenant/project columns и query shape; планы должны быть измерены.
- Alembic autogenerate может не обнаружить или неверно представить rename, некоторые CHECK, policies, grants, triggers и специальные индексы; обязательный manual review.
- `CREATE INDEX CONCURRENTLY` и некоторые DDL не могут выполняться внутри стандартной транзакции миграции; использовать явный Alembic autocommit block и проверку invalid index state.
- DDL design script v1.0 не является исполняемой migration history; его нужно преобразовать в последовательные Alembic revisions с preflight/backfill/contract gates.
- PostgreSQL owner/superuser и backup credentials являются high-trust credentials и требуют отдельного break-glass process.

## 10. Статус реализации

Данный документ BASELINES выбранные практики и требования к реализации. Создан SQL role/RLS reference script, но он является шаблоном, требующим адаптации имён таблиц и grants к фактической схеме. Alembic environment, миграции, реальные роли, policies и runtime tests **не развёрнуты**. Нельзя заявлять, что доступ или миграционная стратегия уже реализованы в работающей БД до выполнения deployment runbook и acceptance suite.

## 11. Источники и основание решений

- PostgreSQL Documentation — Schemas and Privileges: https://www.postgresql.org/docs/current/ddl-schemas.html
- PostgreSQL Documentation — Privileges: https://www.postgresql.org/docs/current/ddl-priv.html
- PostgreSQL Documentation — Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- Alembic Documentation — Autogenerate limitations and manual review: https://alembic.sqlalchemy.org/en/latest/autogenerate.html
- Alembic Documentation — Cookbook: https://alembic.sqlalchemy.org/en/latest/cookbook.html



## Дополнение v1.1 — Implementation Blueprint and release gates

Детальный layout репозитория, env.py contract, Alembic revision sequence, backfill protocol, Unit of Work, connection/pool policy, deployment preflight/postflight, rollback/forward-fix/restore, acceptance matrix и Definition of Done закреплены в `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`. Alembic использует один head и `platform.alembic_version`; schema allowlist ограничивает AI RES schemas; Temporal/LangGraph migrations исключены.

Ни одна destructive/contract migration не запускается без backup/PITR, проверенного restore evidence и явного approval. Backfill неоднозначных legacy Task не автоматизируется без достоверного provenance.
