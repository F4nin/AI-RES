# Runbook: миграции `ai_res_db` (S04)

**Статус:** процедура проверена на локальном стеке и в Testcontainers (PostgreSQL 16.15). Production-проверки (backup/PITR, restore rehearsal) — вне S04: `IMPLEMENTATION NOT VERIFIED` для production. Нормативная основа: Persistence Blueprint §4, §10, §11; Migration & Access Strategy §4–§7.

## Принципы
- Единственный путь DDL — одноразовое задание `migrate` (Compose) / команда `alembic upgrade head` под `ai_res_migrator`. Запуск из API startup запрещён и проверяется тестами (`test_no_startup_migration.py`, `test_api_startup_does_not_run_migrations`).
- `ai_res_migrator` (LOGIN, NOINHERIT) после подключения делает `SET ROLE ai_res_owner`; все объекты принадлежат NOLOGIN-роли `ai_res_owner`. `env.py` отказывается работать под SUPERUSER/BYPASSRLS.
- Роли и пароли создаёт provisioning (`infra/config/postgres/provision_roles.sql`, суперпользователь), потому что у migrator нет CREATEROLE. Ревизия PDB-0001 **проверяет** роли и падает целиком, если они слабее базовой линии (она ничего не «чинит»).
- Одна ревизия — одна цель; имена constraints/indexes явные; downgrade только для обратимых изменений (PDB-0001: `NotImplementedError` — forward-fix).
- Несовместимые изменения — expand → backfill → validate → enforce → contract; `CREATE INDEX CONCURRENTLY` только в `autocommit_block`; FK/CHECK `NOT VALID` → `VALIDATE CONSTRAINT`.

## Применение (локально)
1. `make up` (создаёт секреты, поднимает Postgres, provisioning, затем `migrate`, затем API) либо `make migrate` на поднятом стеке.
2. Проверка: `make infra-test-runtime` (миграция на `head`, 18 схем у `ai_res_owner`, audit SQL без нарушений).
3. Повтор безопасен: `alembic upgrade head` на актуальной БД — no-op.

## Перед изменением pg_hba / ролей
- `pg_hba.conf` пересобирается entrypoint-ом **только при старте** контейнера `postgres`: после правки `entrypoint.sh` выполните `docker compose -p ai-res -f infra/compose.yaml -f infra/compose.dev.yaml restart postgres`, затем `make up`. (Найдено при S04: без перезапуска migrate получал `pg_hba.conf rejects connection`.)
- `provision_roles.sql` идемпотентен и **возвращает роли к эталону**: снимает лишние членства (в т.ч. `pg_read_all_data`), сбрасывает role-level настройки (`RESET ALL`) и заново выставляет атрибуты. Запуск — через `postgres-provision` (`docker compose run --rm --no-deps postgres-provision`).

## Проверки до и после (Blueprint §10)
| Когда | Что | Как |
|---|---|---|
| До | версия PG 16, migrator не привилегирован, нет удерживаемой миграционной блокировки и долгих транзакций, роли существуют | `backend/ops/postgres/preflight.sql` (пусто = ок) |
| До | один head, нет веток, имена файлов `NNNN_intent.py` | `tests/unit/test_migration_graph.py` |
| До | offline SQL для ревью | `alembic upgrade base:head --sql` (PERSIST-004) |
| После | `alembic current == head`, роли/схемы/PUBLIC-права/search_path/invalid index/not validated constraint | `postflight.sql` |
| После | runtime-роли без TRUNCATE/REFERENCES/TRIGGER/DELETE(api)/CREATE/predefined roles/ownership | `grants_audit.sql` |
| После | таблицы с `organization_id`/`project_id` имеют ENABLE+FORCE RLS и политику | `rls_coverage.sql` |
| После | схема совпадает с reviewed snapshot (PERSIST-024) | `test_schema_drift.py`; обновление — `make db-snapshot` и ручной разбор diff |

Release gate: `PGHOST=… PGUSER=… PGDATABASE=ai_res_db backend/ops/postgres/audit.sh [preflight|post]` — exit 0 только без нарушений, exit 1 при нарушениях, exit 2 при ошибке запуска или пустом файле (не «зелёный по умолчанию»).

Все SQL-проверки возвращают строки-нарушения; **пустой результат = пройдено**. Они выполняются в CI (backend integration) и на живом стеке (`infra/tests/runtime/test_persistence.py`).

## Сбой миграции
1. Остановить выкатку; не повторять вслепую и не удалять объекты вручную.
2. Все ревизии идут в одной транзакции (кроме `autocommit_block`): после падения проверьте `platform.alembic_version` и фактическое состояние (`postflight.sql`). Для ревизии с `CONCURRENTLY` проверьте invalid index (`postflight.sql`, `invalid_index`) и перестройте индекс новой ревизией.
3. «Lock timeout» при старте — другой migrator держит advisory lock (`ai_res.alembic.migrations`) либо долгая транзакция держит блокировки объектов: найдите владельца в `pg_locks`/`pg_stat_activity`, не убивайте процессы без разбора.
4. Исправление — новой ревизией (forward-fix). Откат данных — только PITR по решению владельца (Blueprint §11); откат Alembic downgrade не считается безопасным.

## Таймауты (WORKING, ADR-047)
Профиль миграции в Compose: `statement_timeout` 60 с, `lock_timeout` 5 с, `idle_in_transaction_session_timeout` 60 с. Runtime-роли: 15 с / 2 с / 30 с (значения шаблона DOC-069 §8). Это технические значения, не SLO (OD-02); менять — конфигурацией, с записью в ADR.

## Ограничения S04
- Доменных таблиц нет (S05–S06): «upgrade from previous revision» (PERSIST-002) тривиален до появления второй реальной ревизии; тест будет добавлен в S05.
- Backup/restore (PERSIST-021), ротация секретов (PERSIST-022) — S32/S37.
- Профиль привилегий `ai_res_backup` не определён (S32): роль создана без прав на данные и не имеет строки в `pg_hba`.
