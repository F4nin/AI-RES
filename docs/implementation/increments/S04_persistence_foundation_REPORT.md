# S04 — Persistence foundation: Alembic, schemas, роли: Increment Report

**Дата:** 2026-11-11 · **Промпт:** `increments/prompts/S04_persistence_foundation.md` · **Итоговый статус:** VERIFIED (локально: Testcontainers PostgreSQL 16.15 и живой Compose-стек). **GitHub Actions на Linux для S04 не прогонялся** (G-43). Production-проверки (backup/PITR, restore, ротация секретов) вне этапа: `IMPLEMENTATION NOT VERIFIED` для production.

## 1. Что реализовано
- Alembic environment: allowlist 18 схем (ADR-014), `platform.alembic_version`, naming convention, `SET ROLE ai_res_owner`, advisory lock, lock/statement timeouts, offline `--sql`, отказ под SUPERUSER/BYPASSRLS.
- Ревизия PDB-0001: fail-fast preflight ролей, 17 схем + `platform` (bootstrap), USAGE-гранты по ADR-034, default privileges. Таблиц нет (S05–S06).
- Provisioning ролей (ADR-015/036): группы `*_group`, LOGIN-роли migrator/api/outbox_dispatcher/event_consumer/auditor/backup, SCRAM-пароли из Compose secrets, drift-коррекция.
- Отдельная одноразовая служба `migrate` (Compose), секреты (6 новых, слияние в существующий SOPS-файл без перезаписи), строки `pg_hba` для login-ролей (backup намеренно без строки).
- Runtime-слой: `db/engine.py`, `session.py` (Unit of Work), `tenant_context.py` (`set_config(…, true)`, один раз на транзакцию), поля `db_*` в строгом `Settings`.
- Контроль дрейфа и аудит: `ops/postgres/{preflight,postflight,grants_audit,rls_coverage}.sql`, `audit.sh` (release gate), reviewed `schema_snapshot.sql`.
- Не сделано (по scope или плану): доменные таблицы и реальные RLS-политики (S05–S06), PERSIST-002 на реальной «предыдущей» ревизии, профиль `ai_res_backup` (S32), CI-прогон на Linux.

## 2. Нормативная база и проверка Registry
Registry v4.1: все нормативные источники промпта существуют и canonical (DOC-068, DOC-072, DOC-064, DOC-019 — BASELINED; DOC-069 — WORKING, использован как шаблон с адаптацией по ADR-034). Нормативные документы `docs/architecture/` не изменялись.
**Discrepancy:** (а) промпт и DOC-072 §5 говорят «PDB-0001 создаёт роли», но DOC-068 §1.5/§2 лишает migrator CREATEROLE — разрешено ADR-046 (provisioning вне Alembic + проверка в ревизии); (б) DOC-072 §5 (PDB-0003/0008/0009) — N/A по ADR-011; (в) `infra/config/postgres/` вместо `backend/ops/postgres/` для `provision_roles.sql` (политика Compose запрещает bind-mount вне `infra/`). NCP не требуются.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/alembic.ini`, `backend/src/ai_res/db/{__init__,base,engine,session,tenant_context}.py` | новые |
| `backend/src/ai_res/db/migrations/{env.py,script.py.mako,versions/0001_platform_schemas_and_roles.py}` | новые |
| `backend/src/ai_res/platform/config.py` | поля `db_*`, guard TLS |
| `backend/ops/postgres/{preflight,postflight,grants_audit,rls_coverage}.sql`, `audit.sh`, `schema_snapshot.sql` | новые |
| `backend/tests/unit/{test_db_layer,test_migration_graph,test_no_startup_migration}.py`, `backend/tests/integration/postgres/*` (conftest, snapshot, 4 test-модуля) | новые |
| `backend/pyproject.toml`, `uv.lock`, `Dockerfile`, `tests/architecture/test_import_rules.py` | зависимости (SQLAlchemy 2.0.57, Alembic 1.20.1, psycopg 3.3.8, testcontainers 4.15.0), import-linter контракт, alembic.ini в образ |
| `infra/config/postgres/{provision_roles.sql (нов.),provision.sh,entrypoint.sh}` | роли, проверка секретов, hba |
| `infra/compose.yaml`, `infra/scripts/{check_compose,secrets_dev,wait_stack}.py` | служба `migrate`, секреты, политики, слияние секретов, атомарная запись |
| `infra/tests/{test_check_compose.py,runtime/*}` | новые/обновлённые проверки |
| `Makefile`, `.github/workflows/ci.yml`, `.gitignore` | `migrate`, `test-integration`, `db-snapshot`, секреты-заглушки CI |
| `docs/runbooks/migrations.md`, `docs/implementation/*` | runbook, ADL (ADR-046…049), STATUS, KNOWN_GAPS, TRACEABILITY, ECC_USAGE, LOCAL_DEVELOPMENT, HANDOFF, reviews |

## 4. Изменения API / контрактов / событий
Нет: публичные endpoint, OpenAPI/AsyncAPI/JSON Schema не менялись (`make contracts-test`: 19 passed).

## 5. Миграции и совместимость
Одна ревизия `3b7e9c41a0d2` (PDB-0001), единственный head. Upgrade from empty — на Testcontainers и на живом стеке (`migrate` exit 0, TLS verify-full). Повторный upgrade — no-op. Downgrade запрещён (`NotImplementedError`, forward-fix). «Previous revision» тривиален (G-47). Drift = 0 против `schema_snapshot.sql`. PDB-0001 правилась после первого локального применения (только dev/тестовые контейнеры; ни общей среды, ни релиза) — зафиксировано в ADR-046.

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-046 | Роли: provisioning под суперпользователем, ревизия проверяет, drift-коррекция | ACCEPTED |
| ADR-047 | Миграционная среда, служба `migrate`, WORKING-таймауты (60 с / 5 с / 60 с; runtime 15 с / 2 с / 30 с) | ACCEPTED |
| ADR-048 | Snapshot (pg_dump + каталог), audit SQL как gate, positive controls | ACCEPTED |
| ADR-049 | Engine / Unit of Work / tenant context / конфигурация | ACCEPTED |

## 7. Устранённые несогласованности / NCP
См. §2. NCP не создавались. Изменений нормативных документов нет.

## 8. ECC
См. `ECC_USAGE.md`. Использованы четыре review-агента; `planner`, `architect`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, перечисленные skills и commands **не запускались** — компенсация описана там же.

## 9. Тесты и проверки
| Gate | Команда | Результат (точно) |
|---|---|---|
| G1 Static | `make backend-check` | ruff: All checks passed; mypy --strict: no issues in 27 files; import-linter: 5 kept, 0 broken |
| G1 Static | `make infra-check` | 12 services checked, 0 violation(s) ×3 профиля |
| G2 Unit | `cd backend && uv run --locked pytest tests/unit tests/architecture -q` | 75 passed |
| G3 Integration | `cd backend && uv run --locked pytest tests/integration -q` | 84 passed (migrations 15, roles/grants 55, tenant context 11, drift 3) на PostgreSQL 16.15 (Testcontainers) |
| G3/G5 Runtime | `make infra-test-runtime` | 95 passed на живом стеке (в т.ч. 14 новых S04) |
| Backend всего | `cd backend && uv run --locked pytest -q` | 159 passed |
| Infra static | `cd infra && uv run --locked pytest -q --ignore=tests/runtime` | 77 passed |
| G4 Contract | `make contracts-test` | 19 passed |
| G5 secrets | `infra/scripts/scan_secrets.py` | 0 findings |
| G6 Migration | upgrade from empty; single head; offline SQL; lock timeout; weak-role sabotage ×5; drift | см. выше; previous revision — N/A (G-47) |
| G7 Review | 4 агента | CRITICAL/HIGH 0; `reviews/S04_REVIEWS.md` |
| G8/G9 | документы и отчёт | этот файл, ADL, STATUS, TRACEABILITY, KNOWN_GAPS |
Мутационная проверка: tenant context `set_config(…, false)` → тест утечки падает (подтверждено).

## 10. Security / authorization cases
Под реальными login-ролями (не owner/superuser): runtime-роли — отказ в CREATE TABLE/SCHEMA/EXTENSION/TEMP, ALTER/DROP/TRUNCATE/DELETE/SELECT на объектах owner, `SET ROLE ai_res_owner|migrator`, `COPY … TO PROGRAM`, `CREATE ROLE`; migrator без `SET ROLE` не создаёт объекты; backup не подключается (hba); cleartext и cross-database отвергнуты hba (живой стек); нет SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS; пароли только SCRAM; tenant context: default deny на чтение и запись, чужой tenant/проект — 0 строк и WITH CHECK-отказ, пустая строка → 0 строк, нет утечки через commit/rollback/pool, нельзя сменить tenant внутри транзакции, не-UUID отвергается; migrator-суперпользователь отвергнут; конкурентный migrator падает по lock timeout; 37 sabotage-случаев audit SQL; у api/прочих сервисов нет DB credentials. Не проверено: Policy Engine (S07), реальные доменные политики (S05), Manager/Worker (S11/S23).

## 11. Независимое review
`reviews/S04_REVIEWS.md`: CRITICAL 0, HIGH 0; все MEDIUM исправлены или записаны (G-41…G-45). Повторный проход агентов после исправлений не выполнялся.

## 12. Не выполненные проверки, ограничения, риски
G-41 (preflight long_transaction best-effort), G-42 (пароль литералом в `ALTER ROLE`), G-43 (нет Linux-CI; Testcontainers без TLS), G-44 (`postgres` в hba без CIDR), G-45 (Alembic в образе API), G-46 (ADR вне `adrs.py`), G-47 (PERSIST-002/005–014 полно — S05; backup — S32). PERSIST-015/016 — S10, -021 — S32, -022 — S37 (ADR-035). Значения таймаутов — WORKING.

## 13. Обновлённые документы и статусы
STATUS (S04 VERIFIED), ADL (ADR-046…049), KNOWN_GAPS (G-41…G-47), REQUIREMENTS_TRACEABILITY (24 строки), ECC_USAGE, LOCAL_DEVELOPMENT, CONTEXT_HANDOFF, `docs/runbooks/migrations.md`, reviews. Не обновлялись: `prompts/README.md` (генерируется, G-46), DECISIONS_PENDING (новых вопросов к владельцу нет), CONTRACT_TRACEABILITY_MAP (контракты не менялись).

## 14. Статус DoD
- ✅ PERSIST-тесты этапа (001, 003, 004, 024; 002 — частично) на PostgreSQL 16 (Testcontainers) — ✅
- ✅ Grants audit автоматизирован (gate `audit.sh`, тесты в backend и на живом стеке); подключение в GitHub Actions — через `make backend-test` и `infra-runtime` job (первый прогон на Linux не выполнен, G-43)
- ✅ `.claude/rules/database-and-migrations.md` согласован с ADR-015 (без изменений)
- ✅ Результаты созданы, заглушек нет (test-only ревизия и probe-таблицы — только в тестах, маркированы)
- ✅ Тесты проверяют реальное поведение; команды и результаты выше
- ✅ Gates G1–G9 (G6: previous revision — N/A с обоснованием)
- ✅ Миграции: upgrade from empty; drift = 0
- ✅ Security/authorization negative tests выполнены; секреты не обнаружены (scan 0)
- ◐ Observability: компоненты `db/*` не инструментированы OTel (нет эксплуатационных вызовов до S08/S10); логирование не содержит DSN/паролей. Фиксируется для S08/S10
- ◐ Независимое review: ✅ проведено (4 агента); ❌ повторного прохода нет
- ✅ Документы и статусы обновлены
- ✅ Критических открытых дефектов нет

## 15. Можно ли начинать следующий этап
Да, S05 (Core tenant и execution schema + RLS): зависимость S04 выполнена (ADR-032). Рекомендуется перед S05 один раз прогнать ветку в GitHub Actions (G-43) и решить G-46.
