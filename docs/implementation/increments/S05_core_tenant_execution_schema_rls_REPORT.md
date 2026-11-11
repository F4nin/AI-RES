# S05 — Core tenant и execution schema + RLS: Increment Report

**Дата:** 2026-11-11 · **Промпт:** `increments/prompts/S05_core_tenant_execution_schema_rls.md` · **Итоговый статус:** VERIFIED по решению владельца (2026-11-11) на основании локальной проверки (Testcontainers PostgreSQL 16, Docker) и трёх раундов review. **Оговорки к статусу:** GitHub Actions на Linux не запускался; дельта исправлений третьего (verification) раунда не пересматривалась отдельным агентом (см. §11–§12, §15). Ветка `feat/s05-core-tenant-execution-schema-rls`, ничего не закоммичено (OD-06).

## 1. Что реализовано
- **Схема (ревизии 0002–0006, 18 схем из S04):** `iam` (users, credentials, sessions, MFA, roles), `organization`, `project` (+ memberships), `operations` (operations, operation_events, operation_types), `work` (epics, tasks, task_dependencies), `agents` (worker_runs, worker_run_events, worker_results), `execution` (readiness_evaluations — единственная таблица Gate, readiness_check_results), `audit` (outbox_events, inbox_messages, audit_events, aggregate_types), `platform` (idempotency_records, функции-триггеры).
- **RLS:** ENABLE + FORCE на всех tenant-таблицах, default-deny без транзакционного контекста, политики через родителя для таблиц событий/результатов; cross-tenant только для двух сервисных групп (allowlist в `rls_coverage.sql`); **migration-политики owner** (ревизия 0006, ADR-055) под флагом `app.migration_mode`.
- **Инварианты в БД:** Gate (старт только с COMPLETED READY/READY_WITH_LIMITATIONS, версиями самого run и **последней** оценкой; deferred-проверка на commit закрывает обход порядком вставки); `worker_results` только для начатого нетерминального run; terminal Operation/WorkerRun заморожены; Task и WorkerRun не создаются под terminal Operation (`FOR SHARE`); append-only история/оценки/результаты/audit (права + триггеры + TRUNCATE); непрерывность `(aggregate, sequence)` O(log n) на commit без `MAX()+1`; write-once/terminal для revoked/used; UNIQUE попытки WorkerRun; envelope outbox привязан к событию и tenant.
- **Слой репозиториев (`db/cas.py`, `modules/{events,operations,tasks,worker_runs,readiness,idempotency}/`):** CAS по `row_version` (stale → AGGREGATE_VERSION_CONFLICT, чужой/отсутствующий id неразличимы), projection + event + outbox в одной транзакции, sequence через `UPDATE … RETURNING`, outbox dispatcher (claim с порядком по агрегату, lease, fencing owner+attempt+срок, лимит попыток, quarantine), inbox (дедупликация, аномалии), idempotency (HMAC digest, fingerprint, TTL), guard секретов на jsonb-границах.
- **Envelope событий (ADR-054, вариант A владельца):** CloudEvents 1.0 строго по каноническим сообщениям AsyncAPI v1.6, реестры типов = State Machine v1.2, контрактный тест на 36 типов.
- **Не сделано (по scope/плану):** доменные таблицы контента (S06), Policy Engine, auth, Audit Service (S07), HTTP-слой (S08/S09), dispatcher как процесс и SSE (S10), Gate-вычисления (S13). Проверка PERSIST-001..024 «по списку» не закрыта — см. §14.

## 2. Нормативная база и проверка Registry
Registry v4.1 и canonical-файлы из §2 присутствуют; `docs/architecture/` не изменялся. Использованы DOC-064/065 (DDL v1.0 — WORKING), Persistence Blueprint v1.0, Operation & Readiness Gate Decision v1.6, State Machine v1.2 (новее DDL: решено в пользу JSON, ADR-052), AsyncAPI v1.6, Event Model v1.4. Расхождения между самими нормативными документами оформлены как NCP-09…11 (не выбраны молча).

## 3. Созданные и изменённые файлы
- **Миграции:** `db/migrations/versions/0002_identity_organization_project.py`, `0003_operations_and_work.py`, `0004_agents_and_execution.py`, `0005_audit_outbox_inbox_idempotency.py`, `0006_owner_migration_policies.py`.
- **Код:** `db/cas.py`, `db/engine.py` (M), `platform/redaction.py` (M, общий guard секретов), `platform/clock.py` (M), `modules/events/{aggregate_events,envelope,inbox_repository,outbox_repository}.py`, `modules/{operations,tasks,worker_runs,readiness,idempotency}/repository.py`.
- **Ops/Make/зависимости:** `ops/postgres/rls_coverage.sql` (M, новое правило), `ops/postgres/schema_snapshot.sql` (M, перегенерирован и разобран построчно), `Makefile` (M, `tests/contract` в `backend-test-unit`), `backend/pyproject.toml` и `uv.lock` (M: dev-зависимости `jsonschema`, `referencing`, `pyyaml` — те же, что в `contracts/`).
- **Тесты:** `tests/contract/test_event_envelope.py`; `tests/integration/postgres/test_{identity_org_project,operations_work,agents_execution,audit_platform}_schema.py`, `test_repositories.py`, `test_migration_safety.py`; изменены `test_migrations.py`, `test_roles_and_grants.py`, `test_schema_drift.py`, `tests/unit/test_platform.py`.
- **Документы (ненормативные):** `ARCHITECTURE_DECISION_LOG.md` (ADR-050…055, генерируется из `tools/adrs.py`), `KNOWN_GAPS.md` (G-48…G-66), `DECISIONS_PENDING.md` (OD-12, OD-13), `decisions/NORMATIVE_CHANGE_PROPOSALS.md` (NCP-09…11), `CONTEXT_HANDOFF.md`, `reviews/S05_REVIEWS.md`, этот отчёт.

## 4. Изменения API / контрактов / событий
HTTP-поверхность и `contracts/` **не менялись**. Событийная поверхность: формат envelope в `audit.outbox_events` теперь соответствует AsyncAPI v1.6 для 36 смоделированных типов; в БД ещё нет production-данных, иммутабельные строки не мигрировались. Не-конформные места: `worker_run.created` (нет сообщения в AsyncAPI, NCP-11), `data.eventType` не включён (NCP-09), `correlationid`/`traceparent` не поддержаны как атрибуты (NCP-10), `dataschema`/`source` WorkerRun — WORKING (OD-13).

## 5. Миграции и совместимость
Greenfield (ADR-011): 0002–0006 аддитивны и создают таблицы; `downgrade` намеренно `NotImplementedError` (forward-fix или PITR, Blueprint §11). Ревизии 0002–0005 правились на месте, т.к. не были закоммичены и не применялись нигде, кроме тестовых БД; после коммита они immutable. Upgrade from empty и from previous revision (с данными) покрыты (PERSIST-001/002); snapshot-drift и аудиты (rls_coverage, grants_audit, postflight) чисты. Будущие ревизии с tenant-таблицами **обязаны** создавать owner-политику, иначе `rls_coverage.sql` падает.

## 6. Решения, принятые самостоятельно
ADR-050 (iam/organization/project), ADR-051 (operations/work), ADR-052 (agents/execution; JSON v1.2 побеждает DDL v1.0), ADR-053 (audit/outbox/inbox/idempotency), ADR-054 (envelope, по выбору владельца), ADR-055 (owner-политики, по выбору владельца, + hardening по review). WORKING-значения не присваивались: lease/backoff/max_attempts/TTL передаёт вызывающий; `check_code`, статусы Task/Epic — только формат.

## 7. Устранённые несогласованности / NCP
Расхождение DDL↔State Machine решено (ADR-052). Новые NCP-09 (`eventType`), NCP-10 (`correlationid`/`traceparent`), NCP-11 (`worker_run.created`) — PROPOSED, решение владельца (OD-13).

## 8. ECC
Использованы review-агенты (`database-reviewer`, `security-reviewer`, `silent-failure-hunter`, `architect`) только на чтение; hooks/MCP/loops не включались. Результаты ECC — вспомогательные, не нормативные.

## 9. Тесты и проверки (выполнено 2026-11-11)
| Команда | Результат |
|---|---|
| `make backend-test` (`cd backend && uv run --locked pytest -q`) | **297 passed**: unit 72 + architecture 3 + contract 11 + PostgreSQL 16 integration 211 |
| `make backend-check` (ruff, mypy 48 файлов, import-linter 5 контрактов) | exit 0, 0 broken |
| `python3 docs/implementation/tools/check_prompts.py` | 40 prompts, 0 issues |
| `make db-snapshot` + построчный разбор diff | снапшот соответствует миграциям (`test_migrated_schema_matches_committed_snapshot` зелёный) |
Не запускались (код не менялся): `make infra-test`, `make infra-test-runtime`, `make contracts-test`. **GitHub Actions (Linux) не запускался.**

## 10. Security / authorization cases
Проверено тестами под реальными ролями: default-deny без контекста и с контекстом только организации; изоляция tenant A/B и соседних проектов; подставленные чужие id (FK/RLS ошибка, без утечки существования; not-found неотличим от foreign); runtime-роли без DDL/TRUNCATE/DELETE/BYPASSRLS; API INSERT-only на outbox/audit; dispatcher/consumer cross-tenant только по allowlist и колонкам; подделанный envelope чужого tenant отклоняется; Gate не обходится ни порядком вставки, ни выбором старой оценки, ни результатом без старта; terminal не переоткрывается; write-once revoked/used; session absolute lifetime и completion policy неизменяемы; owner под FORCE RLS: default-deny без флага, видимость только с флагом, runtime флаг не использует; секреты в событиях, результатах, снапшотах и ответах idempotency отвергаются; параметры SQL скрыты в ошибках. Sabotage-тесты на каждое правило аудита (включая новое).
**Не проверено в S05 (по плану):** stale/revoked session (S07), revoked Worker grant и Policy Engine outage (S07/S13), prompt injection из source (S06/S13), upload checksum и webhook signature (S06/S10/S19), Temporal replay (S11).

## 11. Независимое review
Три раунда (ADR-037), детали и disposition — `reviews/S05_REVIEWS.md`. Третий раунд (verification-проход дельты, три агента, 26 мутаций): 0 CRITICAL/HIGH; подтверждённые MEDIUM/LOW исправлены (блокировки Gate/результата, привязка envelope, guard секретов, сброс `app.migration_mode`, fencing `mark_failed`) или внесены в gaps G-67/G-68. **Дельта третьего раунда отдельным агентом не пересматривалась** — подтверждена полным набором тестов и мутационной проверкой новых тестов гонок; решение о достаточности — за владельцем. Ограничение: ревьюер — та же модель, что автор; подпись security owner — перед релизным baseline (S37).

## 12. Не выполненные проверки, ограничения, риски
- Linux CI (GitHub Actions) — не запускался (в S04 это закрыто отдельным PR).
- Гарантия «событие ⇒ outbox» в БД не обеспечена (только репозиторием) — G-54; Gate проверяет форму, не содержание — G-60; переходы Task/lineage не в БД — G-61; fail-open непрерывности при невидимом агрегате и широкие права API на credential-таблицы — G-62; нет import-linter запрета для llm/runtime — G-63; атомарность с audit не проверена — G-64; реестр `operation_type` не утверждён — G-65; guard секретов только по ключам — G-66; серверный DETAIL ошибок БД и маппинг ошибок — G-67 (S08); наблюдаемость quarantine и параметры dispatcher — G-68 (S10); pre-auth lookup — G-48.
- Полную сериализацию «оценка ↔ старт» даёт только финальная ревалидация доменного сервиса (S13).
- `bool`-результаты inbox/outbox можно проигнорировать — обязательное правило для S10.

## 13. Обновлённые документы и статусы
Обновлены ненормативные документы реализации (список в §3); `docs/architecture/` и Registry **не менялись**. `IMPLEMENTATION_STATUS.md`: S05 остаётся IN_PROGRESS до решения по §15.

## 14. Статус DoD (§13 промпта) и PERSIST
- Выполнено и подтверждено запуском: миграции upgrade from empty/previous; RLS ENABLE+FORCE на всех tenant-таблицах и аудит; изоляция A/B/соседние проекты под реальными ролями; Task без operation_id и WorkerRun с чужой Task отклоняются; параллельная аллокация sequence без дублей/дыр; атомарность projection+event+outbox (rollback в обе стороны); immutable/append-only; rework после terminal Operation; backfill/resume и lock timeout (синтетические); owner-backfill под FORCE RLS (реальный путь).
- **PERSIST-001..024:** в тестах явно помечены 001, 002, 004, 012, 013, 014, 017–020, 024 (+003/005–008/010 по именам проверок в `test_migration_graph`, аудитах и схемных тестах — полное сопоставление «номер → тест» не составлено). **Не сопоставлено/отложено:** 009 и 011 (011 — только RLS, Policy Engine с S07 → частично), 015/016 → S10 (механика 016 проверена репозиторным тестом «crash before commit»), 021 → S32, 022 → S37, 023 → S03/S23 (G-63). **PERSIST-017..020 — синтетические** (probe-таблицы вне кода проекта): они доказывают поведение PostgreSQL, а не tooling AI RES; реальный FORCE-RLS-путь migrator → owner покрыт отдельным тестом. Заявление «PERSIST-001..024 зелёные» **не делается**.
- Не закрыто: audit в тесте атомарности (G-64).

## 15. Можно ли начинать следующий этап
Технически S06 (Domain content schema) и S07 (Identity/Auth/Policy/Audit/Idempotency) зависят от S05; **безопасный порядок:** (1) решение владельца: считать ли S05 VERIFIED по §11 или провести короткий verification-проход дельты; (2) запуск CI на Linux (PR); (3) решения OD-13/NCP-09…11 — до S10, не блокируют S06/S07; (4) S07 обязан закрыть G-48, G-62 (column grants), G-64.
