# S04 — независимые review и disposition

**Дата:** 2026-11-11 · Метод: четыре агента ECC (`code-reviewer`, `database-reviewer`, `security-reviewer`, `silent-failure-hunter`), read-only, параллельно, независимо от автора. Ограничение (ADR-035/037): та же модель, что и автор, поэтому это не человеческое review; дополнительные слои ADR-037 для S04 не требуются (S04 не в списке P0-этапов S03/S05/S07/S37). `security-reviewer` и `database-reviewer` код не исполняли (статический анализ); `code-reviewer` прогнал тесты.

**Итог:** CRITICAL — 0, HIGH — 0 у всех четырёх. MEDIUM/LOW приняты и исправлены, либо зафиксированы как gaps. Все исправления перепроверены полным прогоном (backend 159, infra static 77, runtime 95).

## code-reviewer — APPROVE
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | `test_no_startup_migration` смешивает «не мигрирует» и «не импортирует SQLAlchemy»; построчный скан обходится алиасом | **Исправлено:** проверка только `alembic`/`ai_res.db.migrations` в `sys.modules` + AST-скан импортов и `create_all`; тест самого сканера (алиасы) |
| 2 | MEDIUM | runtime-тест «API не мигрирует» грепал логи и проходил при любом поведении; Alembic есть в образе API | **Исправлено:** проверяется `Cmd/Entrypoint` api и `migrate`, логи непусты; решение «один образ» зафиксировано в ADR-047 (G-45) |
| 3 | MEDIUM | `with_tenant` можно вызвать повторно внутри транзакции | **Исправлено:** второй вызов → `RuntimeError`; тест |
| 4 | LOW | тест утечки не фиксирует pid первой транзакции; путаный докстринг | **Исправлено** |
| 5 | LOW | при падении `begin()` сессия не закрывается | **Исправлено** + тест |
| 6 | LOW | запрет `sslmode=disable` только для prod | **Исправлено:** разрешено лишь для local/test |
| 7 | LOW | `prepend_sys_path` в образе указывает на несуществующий `/app/src` | **Исправлено:** комментарий |

## database-reviewer — HIGH+ нет
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | `RESET ALL` не трогает `IN DATABASE`-настройки; нет проверки tenant GUC на уровне роли | **Исправлено:** provisioning сбрасывает все `IN DATABASE`; postflight `role_setting_in_database`, `tenant_guc_in_role_setting`; тесты |
| 2 | MEDIUM | drift членства по паре, не по опциям (ADMIN OPTION) | **Исправлено:** `REVOKE ADMIN OPTION FOR` + явные `WITH ADMIN/INHERIT/SET`; postflight `membership_admin_option`, `membership_set_option`; тест drift |
| 3 | MEDIUM | `ai_res_checkpointer(_group)` не в аудите | **Исправлено:** включены; `checkpointer_in_domain_schema` |
| 4 | MEDIUM | владение функциями/типами не проверялось | **Исправлено:** `non_owner_owns_function_or_type`, `runtime_owns_function_or_type` |
| 5 | MEDIUM | нет проверок PUBLIC EXECUTE/USAGE, SECURITY DEFINER, default ACL, column-level, записи у auditor/backup | **Исправлено** (7 новых проверок; dispatcher/consumer на домен — по таблицам в S05) |
| 6 | MEDIUM | RLS-coverage по наличию колонок; нет политик TO PUBLIC/`true`, views, partitions | **Исправлено:** default-fail + явный `exempt`; `rls_policy_to_public`, `rls_policy_always_true`, `view_without_security_invoker`, matview; партиции исключены |
| 7 | LOW | `hostssl all postgres all` без ограничения адреса | **Gap G-44** (наследие S03) |
| 8 | LOW | preflight: фильтр advisory lock без БД/objsubid | **Исправлено** |
| 9 | LOW | `log_statement` мог писать пароль | **Исправлено:** `SET log_statement='none'`, `log_min_duration_statement=-1` |
| 10 | LOW | атрибуты `ai_res_checkpointer` не re-assert | **Исправлено** (NOREPLICATION и др.; preflight проверяет при наличии) |
| 11 | LOW | `REVOKE ALL ON SCHEMA public` снимает и USAGE | **Решение зафиксировано** в ADR-046 (pgvector — отдельное решение в S27) |
| 12 | LOW | ADP на таблицы/последовательности — no-op | **Исправлено:** комментарий в ревизии |
| 13 | LOW | postflight без фильтра схем | **Исправлено** |

## security-reviewer — HIGH+ нет
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | LOW | запись `local.enc.yaml` не атомарна | **Исправлено:** tmp + fsync + `os.replace` + `.bak`; `*.tmp` в `.gitignore` |
| 2 | LOW | пароль может попасть в лог через `log_statement`/duration, stderr psql | **Исправлено** частично (`log_statement=none`, duration −1); остаточный риск — пароль в тексте `ALTER ROLE` виден суперпользователю в `pg_stat_activity` во время выполнения; SCRAM-verifier на клиенте — **gap G-42** |
| 3 | INFO | `sslmode=disable` | см. code-reviewer #6 |
| 4 | INFO | ADMIN OPTION при повторном GRANT | **Исправлено** (см. database #2) |
| 5 | INFO | `hostssl all postgres all` достижим из `data`, где появится API с DB-credentials | **Gap G-44** |
| 6 | INFO | Alembic в образе API | **Gap G-45** |
Остальная модель угроз (обход ограничений `ai_res_api`, динамический SQL, утечка пароля в repr/ошибках, единственный путь DDL, ослабление S03) — обходов не найдено.

## silent-failure-hunter — HIGH+ нет
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | `IN DATABASE` настройки невидимы проверкам | **Исправлено** (см. database #1) |
| 2 | MEDIUM | отсутствие ролей → все role-проверки пусты | **Исправлено:** `missing_role` в postflight/grants_audit; тест |
| 3 | MEDIUM | version table: пустая/не head проходит | **Исправлено:** ровно одна строка (`version_table_rows`); сравнение с head — в тестах (`HEAD`) |
| 4 | MEDIUM | audit SQL нигде не вызывается как gate | **Исправлено:** `audit.sh` (exit 1/2), runbook, runtime-тесты gate с positive control |
| 5 | MEDIUM | `long_transaction` слеп без `pg_read_all_stats` | **Gap G-41** (best-effort, помечено в SQL) |
| 6 | MEDIUM | запись секретов не атомарна | **Исправлено** (см. security #1) |
| 7 | LOW | cleanup в `finally` env.py | **Исправлено:** вложенные try/finally, проверка результата unlock |
| 8 | LOW | владелец БД и лишний CONNECT не корректируются | **Исправлено:** `ALTER DATABASE … OWNER`, отзыв лишних grants; тест |
| 9 | LOW | пустой `cat` секрета → пустой пароль | **Исправлено:** `test -s` в `provision.sh` |
| 10 | LOW | USAGE-матрица не в postflight | **Принято:** покрыта snapshot и тестом матрицы |
| 11 | LOW | `UPDATE_SCHEMA_SNAPSHOT` превращает тест в skip | **Исправлено:** запрещён при `CI` |
| 12 | LOW | `assert` в `__aexit__` | **Исправлено** |
| 13 | LOW | runtime-тесты без проверки причины/непустоты | **Исправлено** (`pg_hba.conf` в stderr, positive controls, rc) |
| A–D | — | вакуозные тесты: preflight без positive control; покрыто 3 из 14 проверок postflight; runtime audit без control; `raises` слишком широк; default privileges не проверены для функций | **Исправлено:** 37 sabotage-случаев на каждый класс нарушений; preflight positive controls; gate падает на реальном дрейфе; `raises(InsufficientPrivilege)`; тест EXECUTE для функций |

## Мутационные проверки автора
- Tenant context `set_config(..., false)` вместо `true` → `test_context_does_not_leak_across_commit_rollback_and_pool_reuse` падает (проверено, код восстановлен).
- Мутации `ALTER DEFAULT PRIVILEGES` / отдельных веток audit SQL, предложенные review, покрыты positive-control тестами (проверяется имя конкретного нарушения); отдельный прогон каждой мутации не выполнялся.

## Не проводилось
- Повторное независимое review после исправлений (исправления проверены тестами и вторым полным прогоном, но не вторым проходом агентов). Фиксируется как ограничение в отчёте.
