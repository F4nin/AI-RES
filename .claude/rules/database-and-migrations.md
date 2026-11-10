# database-and-migrations.md — База данных и миграции

**Нормативные источники:** `AI_RES_Persistence_Implementation_Blueprint_v1.0.md` · `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md` · `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md` · `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` · `AI_RES_Identity_Access_Control_v1.5.md`

---

## Топология баз данных (BASELINED)

| База | Назначение | Владелец/роли |
|---|---|---|
| `ai_res_db` | Доменная БД AI RES | `ai_res_owner` (NOLOGIN), отдельный migrator, least-privilege runtime principals |
| `temporal_db` | Temporal persistence | Управляется Temporal; AI RES не мигрирует |
| LangGraph checkpoint schema | Internal agent state | Изолированная schema в `ai_res_db` или отдельная; не смешивать с доменными таблицами |

**Запрещено:**
- Cross-database FK между `ai_res_db` и `temporal_db`.
- Смешивать LangGraph checkpoint tables с доменными таблицами AI RES.
- Создавать отдельную БД на каждый домен/bounded context в MVP.

---

## Alembic (BASELINED)

- Alembic + SQLAlchemy 2.x — единственный инструмент миграций для `ai_res_db`.
- Migration job — **отдельный от API startup**; не запускать из `app.on_startup()` или аналогов.
- Revisions immutable после применения.
- Autogenerate требует manual review diff перед commit; не коммитить autogenerate без проверки.
- Явный allowlist schemas в Alembic env: только доменные schemas `ai_res_db`. Temporal/LangGraph schemas в allowlist не включать.
- `platform.alembic_version` (или выбранная таблица версий) отделена от `temporal.schema_version`.

---

## Порядок реализации persistence (из Persistence Blueprint §14)

Обязательная последовательность — нельзя пропускать шаги:

1. Pin dependencies (Alembic, SQLAlchemy, psycopg версии).
2. Alembic env + schema allowlist + версионная таблица.
3. Тест upgrade from empty DB.
4. Additive revisions (новые таблицы/колонки).
5. Role/grant/RLS revisions.
6. Resumable backfill dry-run + approved mapping.
7. Validation и NOT NULL/FK contract revisions.
8. Repositories / Unit of Work / tenant context.
9. PERSIST-001..024 acceptance tests.
10. Preflight/postflight checks и recovery runbooks.

---

## Несовместимые изменения (expand/contract)

Для любого breaking schema change:

```
1. expand      — добавить новое (колонка, таблица), старое не трогать
2. backfill    — заполнить новое поле; resumable; не блокировать таблицу
3. validate    — убедиться, что всё заполнено корректно
4. enforce     — добавить NOT NULL, FK, CHECK VALID
5. contract    — убрать старое (только после deploy и verification)
```

- Большие индексы: `CREATE INDEX CONCURRENTLY`.
- FK и CHECK: `NOT VALID` → отдельная `VALIDATE CONSTRAINT` без lock.
- Statement timeout и lock timeout обязательны для миграций на production-like данных.
- Деструктивные шаги (DROP TABLE, DROP COLUMN, TRUNCATE): запрещены без: backup/PITR evidence + явного решения владельца + restore drill.

---

## PostgreSQL roles и доступ (BASELINED)

| Роль | Права | Что запрещено |
|---|---|---|
| `ai_res_owner` | Владелец объектов (NOLOGIN) | Прямой login |
| `ai_res_migrator` | DDL в рамках deploy job | Runtime доступ к API |
| `ai_res_api` | DML на domain tables | DDL, BYPASSRLS, TRUNCATE, DELETE без WHERE |
| `ai_res_outbox_dispatcher` | Чтение/lease/mark Outbox | DML на domain tables, DDL |
| `ai_res_event_consumer` | Inbox + локальный эффект consumer | DDL, BYPASSRLS |
| `ai_res_auditor` | SELECT утверждённых audit записей | Любая запись |
| backup identity | Backup/WAL archiving | Runtime доступ |

Login-роли включаются в `*_group` роли (DOC-069). Ролей `ai_res_manager` / `ai_res_worker` нет: Manager и Worker Runtime работают через Application Services (DOC-064 §10, DOC-005, DOC-019 §4; ADR-015 в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`).

**Manager Runtime и Worker Runtime не получают DB credentials PostgreSQL.** Всё domain write — только через Application Service.

---

## Row Level Security (BASELINED)

- RLS: `ENABLE FORCE` на tenant tables (tenant = organization/project scoped).
- Transaction-local tenant context: устанавливается при старте транзакции, не сохраняется между соединениями пула.
- Fail-closed без tenant context: без `SET LOCAL` запрос отклоняется (default deny policy).
- Pooled connection: tenant context сбрасывается при возврате соединения в пул; использовать `RESET` или `DISCARD` / connection lifecycle hook.
- RLS — defense-in-depth; **не замена Policy Engine**.
- Custom GUC не считается безопасным против arbitrary SQL под API identity.

---

## Транзакционные инварианты (BASELINED)

- Projection update + aggregate event + Outbox record — **одна транзакция**. Rollback оставляет ни одной из трёх записей.
- Не держать транзакцию открытой во время: LLM RPC, Temporal RPC, HTTP/tool call, human wait.
- Optimistic concurrency: `row_version` / expected version; stale update → 409 `AGGREGATE_VERSION_CONFLICT`.
- Idempotency key: хранить как HMAC digest с tenant/scope binding; fingerprint mismatch → 409 `IDEMPOTENCY_KEY_REUSED`.
- Outbox dispatcher: lease не держит DB lock во время network call; bounded retry + jitter + quarantine.

**WORKING (требует отдельного Implementation ADR до production):**
- HMAC key rotation policy для idempotency keys.
- Конкретные значения lease duration, retry backoff thresholds.

---

## Backup и восстановление (BASELINED — цели)

- **Инструмент:** pgBackRest + WAL Archiving.
- **RPO:** ≤ 1 час (цель, не гарантия до recovery drills).
- **RTO:** ≤ 4 часа (цель, не гарантия до recovery drills).
- MinIO objects резервируются отдельно от PostgreSQL.
- Secrets резервируются отдельно и в зашифрованном виде.
- Recovery Manifest: связывает PostgreSQL backup/PITR point, MinIO snapshot, версии конфигурации и незавершённые Temporal Workflows.
- После restore: Recovery Reconciliation — проверить незавершённые WorkerRuns и внешние side effects; неоднозначные случаи → human escalation.

---

## CI acceptance gates для persistence

Обязательны для инкремента с миграциями:

- Schema drift check между design DDL и actual migration state.
- RLS coverage: все tenant tables покрыты политиками.
- Grants audit: runtime principals не имеют DDL/BYPASSRLS.
- Forbidden role attributes: no SUPERUSER, no BYPASSRLS у runtime principals.
- Upgrade from empty DB: `alembic upgrade head` от пустой БД.
- Upgrade from previous revision: `alembic upgrade` от предыдущего состояния.
- Tenant isolation test: данные tenant A не видны под credentials tenant B.
- Missing context default-deny: запрос без transaction-local tenant context отклоняется.
- Pooled connection context reset: контекст не утекает между соединениями.
