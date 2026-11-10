# S00 (Spec Increment 0) — Repository Reconnaissance, Baseline Manifest и Discrepancy Report

**Дата:** 2026-11-10
**Основание:** Implementation Spec v1.22 §4 (Increment 0), Addendum v1.3 §1/§5, Readiness Audit v2.2 §4
**Статус инкремента:** IMPLEMENTED (документация/разведка). Код не создавался. `IMPLEMENTATION NOT VERIFIED` для любого runtime.

---

## 1. Состояние репозитория

| Объект | Факт |
|---|---|
| Ветка | `main`, 2 коммита (`6872162` baseline docs, `8fa9c64` CLAUDE.md) |
| Исходный код | Отсутствует. `src/`, `tests/`, `scripts/` — пустые каталоги (не отслеживаются git) |
| Lockfiles / pyproject / package.json | Отсутствуют |
| Миграции / Alembic metadata | Отсутствуют |
| CI конфигурация | Отсутствует |
| Docker Compose | Отсутствует |
| Тесты | Отсутствуют |
| Вывод | **Greenfield.** Нет существующих stack choices, которые нужно сохранять (Spec §4 Inc.0) |

### Локальная среда (для воспроизводимости проверок)

| Инструмент | Версия | Примечание |
|---|---|---|
| Python | 3.13.5 | 3.12 не установлен |
| uv | 0.11.31 | |
| Docker / Compose | 29.2.0 / v5.0.2 | daemon доступен |
| PostgreSQL (локальный) | 16.14 (Homebrew), `/tmp:5432` принимает подключения | Соответствует Blueprint §2 «PostgreSQL 16+» |
| Node / npm | 26.12.1 / 11.20.0 | см. G-03 (AsyncAPI parser) |
| Temporal CLI | отсутствует | будет через Docker image в Inc. 7 |

---

## 2. Implementation Baseline Manifest (сводка)

Источник: `docs/architecture/AI_RES_Document_Registry_v4.1.md` §2 и `AI_RES_Architecture_Baseline_Manifest_v1.2.json`.

| Проверка | Результат |
|---|---|
| Canonical records в Registry §2 | 74 |
| Уникальные DOC ID / уникальные paths | 74 / 74 |
| Отсутствующие файлы | 0 |
| Статусы | BASELINED 41, WORKING 33 |
| Файлов в SHA-256 manifest | 73 (manifest исключает сам себя — `self_hash: excluded_by_design`) |
| Несовпадения SHA-256 | **0** |
| Записи manifest вне Registry / Registry вне manifest | 0 / 1 (сам manifest — ожидаемо) |

Вывод: все canonical файлы присутствуют и побайтно совпадают с утверждённым baseline.

---

## 3. Валидация контрактов (static evidence)

Валидаторы установлены изолированно в scratchpad с закреплёнными версиями: `openapi-spec-validator==0.7.1`, `jsonschema==4.23.0`, `pyyaml==6.0.2`, `@stoplight/spectral-cli@6.14.2`, `@asyncapi/parser@3.4.0` (`@asyncapi/specs@6.11.1`). В Increment 1 они переносятся в репозиторий с lockfile.

| Контракт | Проверка | Результат |
|---|---|---|
| `AI_RES_Public_API_v1.3.yaml` (OAS 3.1.1) | openapi-spec-validator | **VALID**; 20 paths / 26 operations / 33 schemas |
| то же | Spectral `spectral:oas` | 0 errors, 24 warnings (`operation-description` отсутствует) |
| то же | `$ref` resolution | 117 local refs, 0 unresolved, 0 external |
| `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml` (AsyncAPI 3.1.0) | JSON Schema официальной спецификации 3.1.0 | **VALID**; 1 channel / 78 operations / 78 messages |
| то же | `$ref` resolution | 360 local refs, 0 unresolved |
| то же | `@asyncapi/parser@3.4.0` | **НЕ ВЫПОЛНЕНО** — uncaught `Error running Nimma` в валидаторе (G-03) |
| `AI_RES_Worker_Contracts_v1.1.schema.json` | Draft 2020-12 metaschema | VALID; 10 refs resolved |
| `AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json` | Draft 2020-12 metaschema | VALID |
| `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json` | Draft 2020-12 metaschema | VALID |
| `AI_RES_Glossary_Entry_Schema_v1.1.json`, `..._Document_Schema_v1.0.json` | metaschema | VALID |
| `AI_RES_Glossary_v1.1.json` | instance vs Document Schema (локальный registry для `$id`) | VALID |

OAS 3.2.1: совместимость не тестировалась; миграция не предлагается (Spec §4 Inc.0).

---

## 4. Discrepancy Report

| ID | Документ / область | Ожидание | Факт | Блокирует | Варианты |
|---|---|---|---|---|---|
| DR-01 | Physical Model v1.2 / DDL v1.0 (DOC-064/065), Blueprint §6 (DOC-072) | DDL жёстко зависит от **существующей** `work.tasks` (ALTER + composite FK, DDL стр. 59, 135) и предполагает legacy backfill Task→Operation (PDB-0008); organization/project/context/worker-definition — только UUID-колонки без FK | Репозиторий greenfield: ни одной таблицы нет; legacy Tasks отсутствуют. Кроме того, синхронный `createTask` (201) не создаёт Operation — конфликт с `operation_id NOT NULL` | Inc. 2 (persistence часть), Inc. 3 | (A) Greenfield-профиль: `work.tasks.operation_id NOT NULL` с первой ревизии, PDB-0008 = N/A с зафиксированным обоснованием; (B) сохранить expand/backfill последовательность формально. Рекомендация: A. **Решение владельца — DP-02** |
| DR-02 | DOC-005 Domain Model vs DDL | Физическая модель нужна для Project/Epic/Task/Requirement/Source/Artifact (Inc. 3–4) | Физический DDL существует только для execution slice (`operations`, `agents`, `execution`, `audit`, `platform`) | Inc. 3 | Вывести физические таблицы из DOC-005 как implementation-решения с review владельца. **DP-03** |
| DR-03 | Spec v1.22 §2, Addenda v1.3–v1.21 | Ссылки на актуальные версии | Исторические ссылки (Registry v4.0/v1.7/v1.9, Requirements v2.6 и др.) | Нет — Addendum v1.22 явно отдаёт приоритет Registry v4.1 | Синхронизировать в Spec v1.23 (решение владельца) |
| DR-04 | DOC-008 AsyncAPI v1.6 vs DOC-055 §3.2 | `readinessEvaluationId` | `gateResultId` в event schemas | Нет (зафиксированный план breaking-safe rename) | Одна таблица `execution.readiness_evaluations`; маппинг в event adapter |
| DR-05 | DOC-007 Worker Contracts | BASELINED контракт для Inc. 6 | WORKING | Inc. 6 | Финализировать до Inc. 6 (PR-7 в Initial Analysis) |
| DR-06 | Blueprint §3 repository layout | `backend/pyproject.toml`, `backend/src/ai_res/...` | Пустые `src/`, `tests/`, `scripts/` в корне | Нет | Следовать Blueprint (BASELINED): код в `backend/`; `contracts/` в корне (Spec §4 Inc.1). Пустые корневые каталоги не используются (ADR-005) |
| DR-07 | Persistence Blueprint §2, Spec v1.17 | Web-фреймворк / sync vs async stack | Не выбран (WORKING, `coding-standards.md`) | Inc. 2 (HTTP middleware) | **DP-01** |
| DR-08 | Spec Addendum v1.3 §4 vs текущая установка ECC | «не устанавливать/не предполагать Claude Code plugins до решения пользователя» | ECC установлен в `.claude/` (не закоммичен); владелец в текущей сессии поручил использовать ECC | Нет | Решение пользователя принято (ADR-007); ECC подчинён правилам AI RES (`ecc-precedence.md`); hooks/MCP ECC выключены |

| DR-09 | DOC-064 v1.2 §1/§3 (BASELINED) vs DDL v1.0 (DOC-065, WORKING) vs Roles SQL (DOC-069) | Таблицы `agents.worker_results`, `audit.audit_events`, `work.task_dependencies` | В DDL нет CREATE TABLE для них; Roles SQL стр. 78 выдаёт `GRANT SELECT ON audit.audit_events` — скрипт упадёт на пустой БД | Inc. 2P | Спроектировать DDL трёх таблиц по DOC-064/DOC-005 в составе DP-03; review владельца |
| DR-10 | `.claude/rules/database-and-migrations.md` vs DOC-064 (access), DOC-005, DOC-019, DOC-069 | Единый набор runtime-ролей | Правило проекта: `ai_res_manager`, `ai_res_worker`. Нормативно: `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor`; Manager/Worker без DB credentials; DOC-069 — `*_group` | Inc. 2P | Нормативные документы выше правил проекта; **DP-10** |

Противоречий между двумя BASELINED документами, требующих остановки Increment 1, не обнаружено.

---

## 7. Независимое ревью (ECC `architect`)

Проведено read-only ревью пакета; 15 замечаний (3 HIGH, 6 MEDIUM, 6 LOW). Ключевые факты перепроверены Implementation Lead по источникам (Blueprint §5, DOC-064 §1/§3, DDL, Roles SQL стр. 78, OAS `completeUpload` 202, DOC-015 §11.2) — подтверждены. Все замечания учтены:

| # | Замечание | Исправление |
|---|---|---|
| 1 HIGH | Порядок persistence нарушает Blueprint §5 | Roadmap: выделен Inc. 2P с цепочкой PDB-0001…0010 и PERSIST-001..024 до Inc. 3 |
| 2 HIGH | `createTask` (201) vs `operation_id NOT NULL` | Расширен DP-02; DR-01 дополнен |
| 3 HIGH | Отсутствуют DDL `worker_results`/`audit_events`/`task_dependencies` | DR-09 |
| 4 MED | Расхождение ролей БД | DR-10, DP-10 |
| 5–7 MED | Ошибки traceability map (`completeUpload`, SSE source, `worker_results`) | Исправлено в `docs/implementation/CONTRACT_TRACEABILITY_MAP.md` |
| 8 MED | ECC без trust-оценки (Spec Add. v1.3 §4) | ADR-007 уточнён; G-09 |
| 9 MED | Риск двух источников истины контрактов | ADR-009: `contracts/` — проверяемое зеркало с SHA-256 gate |
| 10 LOW | `deploy/compose/` vs DOC-015 §11.2 `infra/compose.yaml` | ADR-005 исправлен на `infra/` |
| 11 LOW | DR-01 завышен | Уточнён |
| 12 LOW | ETag в карте | Исправлено |
| 13 LOW | «VERIFIED (static)» невоспроизводимо | Статус Inc. 0 → IMPLEMENTED (static evidence) |
| 14 LOW | Битая ссылка, WORKING статусы DOC-050/065 | Исправлено |
| 15 LOW | Поддержка Python 3.13 не проверена | ADR-001: проверка при pin зависимостей |

---

## 5. Missing prerequisites (по Spec Addendum v1.3 §5)

| Gate-пункт | Статус |
|---|---|
| Baseline manifest и reconnaissance | ✅ выполнено (§1–2) |
| Registry references resolve | ✅ |
| OpenAPI/AsyncAPI/JSON Schema parse + validators | ✅ (кроме официального AsyncAPI parser — G-03) |
| Traceability map entities ↔ API/events | ✅ первичная версия: `docs/implementation/CONTRACT_TRACEABILITY_MAP.md` |
| Negative tests для security flows запланированы | ✅ в `IMPLEMENTATION_ROADMAP.md` по инкрементам |
| Docker Compose topology / secrets strategy задокументированы | ✅ в DOC-015 / DOC-019 (нормативно); реализация — Inc. 2+ |
| Increment plan ↔ requirements/contracts/migrations/tests/DoD | ✅ `IMPLEMENTATION_ROADMAP.md` |
| Unresolved decisions с owner и blocking-классификацией | ✅ `DECISIONS_PENDING.md` |

---

## 6. Delivery report (Spec §10 / CLAUDE.md §5.3)

1. **Файлы:** созданы трекеры (перенесены в `docs/implementation/`, ADR-006). Нормативные документы не изменялись.
2. **API/contract surface:** без изменений.
3. **Миграции:** нет.
4. **Тесты:** только статические проверки контрактов и целостности baseline (§2–3). Runtime tests отсутствуют — кода нет.
5. **Security/authorization cases:** не применимо (код отсутствует); запланированы в roadmap.
6. **Неразрешённые вопросы:** `DECISIONS_PENDING.md` (DP-01…DP-06), `KNOWN_GAPS.md`.
7. **Docs/contracts обновлены:** только development-документы; Registry не менялся.
8. **Следующий безопасный инкремент:** Increment 1 — contract toolchain (не зависит от DP-01/DP-02/DP-03).

---

## 8. Пост-обновление (подготовительная фаза, 2026-11-10)

Отчёт перенесён из `docs/development/INCREMENT_00_REPORT.md`. Решения DP-01/02/03/05/10 закрыты как ACCEPTED (ADR-008, ADR-011, ADR-012, ADR-016, ADR-014, ADR-015) по делегированию Master Implementation Initialization; актуальные открытые вопросы — `DECISIONS_PENDING.md` (OD-xx). Нумерация «Inc. N» в этом отчёте соответствует Spec; актуальная последовательность — S00–S39 (`IMPLEMENTATION_ROADMAP.md`, ADR-010). Ссылки DP-xx в §4 являются историческими.
