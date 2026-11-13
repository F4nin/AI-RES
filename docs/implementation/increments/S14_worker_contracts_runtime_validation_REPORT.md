# S14 — Worker contracts: Envelope/Result/Notice: Increment Report

**Дата:** 2026-11-13 · **Промпт:** `increments/prompts/S14_worker_contracts_runtime_validation.md` · **Итоговый статус:** TESTED (локально; Linux CI не запускался, дельта исправлений review не пересматривалась отдельным агентом — до VERIFIED нужны зелёный Linux CI и OD-20 решён ADR-104 уже после review, эта правка отдельным агентом не пересматривалась)

## 1. Что реализовано
- Пакет `ai_res.worker_contracts` (вне `modules`, без БД — его импортирует Worker Runtime): `WorkerContracts.check/check_snapshot` проверяет WorkerRunEnvelope (ENQUEUE, PRE_EXECUTION) и WorkerResult/WorkerNotice (RESULT_RECEIPT, DOWNSTREAM). Fail-closed: независимый JSON-снимок → `contractVersion` (только `1.1`) → JSON Schema (авторитет, форматы uuid/date-time) → правило evidence → значения, похожие на секреты. Неизменяемые Pydantic-модели + тест паритета со схемой.
- Реестр WorkerDefinition (миграция 0016): `agents.worker_definitions` (9 ролей, засеяны), `agents.worker_definition_versions` (неизменяемые версии, статус только вперёд), FK из `worker_runs` и `readiness_evaluations`.
- Сервис `store_worker_result`: контракт на RESULT_RECEIPT, принадлежность run/task/роли из реестра, запись проверенного снимка, отображение ошибок хранения.
- Не сделано (вне scope): исполнение WorkerRun (S23), проверка «wrong capability» в Gate (S22), загрузка схемы процессами (G-135), персистенция Notice (G-139).

## 2. Нормативная база и проверка Registry
DOC-007 `AI_RES_Worker_Contracts_v1.1.schema.json` (WORKING, существует, зеркало в `contracts/json-schema/worker/` идентично — проверено `cmp` ревьюером); DOC-006 §8; Domain Model v1.9 (`agents.worker_definitions` без колонок); Registry v4.1 §2 — DOC-007 WORKING. Discrepancy report: колонки `worker_definitions` в Domain Model не заданы → ADR-102 (WORKING), правило evidence в DOC-007 не задано → ADR-101 (WORKING). `docs/architecture/` не менялся.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/src/ai_res/worker_contracts/{__init__,models,validation}.py` | новый пакет |
| `backend/src/ai_res/modules/worker_runs/results.py` | новый сервис |
| `backend/src/ai_res/db/migrations/versions/0016_worker_definition_registry.py` | новая ревизия |
| `backend/src/ai_res/platform/config.py` | `worker_contract_schema_file` |
| `backend/ops/postgres/{rls_coverage,schema_snapshot}.sql` | +2 exempt-строки; снимок (+114 строк, 0 удалено) |
| `backend/tests/unit/test_worker_contracts.py` | 77 тестов |
| `backend/tests/integration/postgres/test_worker_definition_registry.py`, `test_worker_result_service.py` | 11 + 12 тестов |
| `backend/tests/integration/postgres/{conftest,test_agents_execution_schema,test_repositories}.py` | хелпер засева версии; FK требует существующую версию |
| `docs/implementation/{ARCHITECTURE_DECISION_LOG,KNOWN_GAPS,DECISIONS_PENDING,IMPLEMENTATION_STATUS,CONTEXT_HANDOFF,ECC_USAGE}.md`, `reviews/S14_REVIEWS.md` | документы этапа |

## 4. Изменения API / контрактов / событий
Публичный API, OpenAPI/AsyncAPI и JSON Schema не менялись. Нового endpoint/события нет. Внутренний контракт DOC-007 реализован как есть (WORKING); изменения полей — NCP-04.

## 5. Миграции и совместимость
Ревизия `e8b4d2f6a193` (0016), additive: 2 таблицы, триггеры, FK (NOT VALID + VALIDATE), индексы. Предусловие: нет строк в `worker_runs`/`readiness_evaluations` (иначе понятная ошибка). Upgrade from empty и from previous — тесты миграций (19 passed); drift = 0 после `make db-snapshot` (диф только добавляет). `make up` применил 0016 к локальной dev-БД (`migrate exit=0`). Downgrade — forward-fix (формат, который проверяет тест). RLS-покрытие и гранты — аудиты чисты; реестр — exempt (глобальный, runtime SELECT-only).

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-101 | Пакет вне `modules`, 4 точки, fail-closed, правило evidence и `MAX_PAYLOAD_BYTES` (WORKING) | ACCEPTED |
| ADR-102 | Глобальный реестр, неизменяемые версии, БД хранит только ссылку (статус/совпадение — Gate S22) | ACCEPTED |
| ADR-103 | Сохранение результата только через сервис, снимок, перечитывание run, SQLSTATE-отображение | ACCEPTED |
| ADR-104 | Решение владельца по OD-20: описательная пара «слово-секрет: слово» принимается, остальное отклоняется | ACCEPTED |

## 7. Устранённые несогласованности / NCP
NCP-04 (DOC-007 → v1.2 BASELINED) остаётся PROPOSED; дополнен наблюдениями: `workerRole` в Result — свободная строка (G-143), связь `output_contract_version` ↔ `contractVersion` не определена (G-136). Новых NCP не создано.

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `database-reviewer`, `silent-failure-hunter`, `code-reviewer` (blind-first, read-only) | Независимое review (ecc-precedence п. 2: миграция+RLS-исключения, fail-closed) | `reviews/S14_REVIEWS.md`: CRITICAL 0, HIGH 2 (1 исправлен, 1 — граница Gate), MEDIUM исправлены кроме OD-20 |
| `planner`, `architect`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, `type-design-analyzer`; `/plan`, `/quality-gate`, `/python-review`, `/test-coverage`, `verification-loop` | Указаны в промпте, **не запускались**: план по срезам составлен исполнителем и изложен пользователю; тесты писались до кода вручную; архитектурное соответствие проверено import-linter и `code-reviewer` | отмечено; покрытие как метрика не снималось |
Недоступные компетенции: отдельного архитектурного агента на дельту исправлений не было.

## 9. Тесты и проверки
| Gate | Команда | Результат (точно) |
|---|---|---|
| G1 | `make backend-check` (ruff, mypy, lint-imports) | чисто; import-linter 10 kept / 0 broken |
| G2/G3 | `make pre-pr` (весь целиком, одной командой, после всех правок и ADR-104): `backend-test` | **1236 passed**, 540 warnings (18 мин 26 с) |
| G2 | `pytest tests/unit/test_worker_contracts.py` | 97 passed |
| G3 | реестр + сервис + затронутые наборы (схемы, миграции, гранты, e2e) | 11 + 12 passed; 115 + 19 passed |
| G4 | `make contracts-check`, `make contracts-test` | прошли (22 passed) |
| G5 | `make infra-scan-secrets` | 0 находок (в первом прогоне было 3 — фиктивные секреты в тесте, исправлено) |
| G6 | `make up` (миграция 0016 на dev-БД), `make infra-test`, `make infra-test-runtime` | migrate exit=0; 307 passed; 148 passed; `pre-pr: all CI-equivalent checks passed`, exit=0 |
| G7 | 3 агента | см. §11 |
| G8/G9 | этот отчёт, ADR, gaps | выполнено |
Первый запуск `make pre-pr` остановился на secret scan (фиктивные секреты в unit-тесте); после исправления и всех правок review/ADR-104 весь `make pre-pr` пройден одной командой (exit=0).

## 10. Security / authorization cases
Unknown major/minor/тип версии — отклонены во всех 4 точках; лишние/недостающие поля; результат без evidence; секреты (ключ, значение, PEM, Bearer, URL с паролем, за пределом 8192 символов, full-width, нулевой ширины); значения не попадают в ошибки/метрики; чужой tenant → одинаковый 404; подделка организации в переданной строке; run не стартовал/терминален; повторный результат; NaN/суррогат/oversize; runtime-роль не пишет в реестр, другие роли не читают; запрет UPDATE/DELETE/TRUNCATE реестра.

## 11. Независимое review
`reviews/S14_REVIEWS.md`. Исправленное ревью-раундом не пересматривалось отдельным агентом.

## 12. Не выполненные проверки, ограничения, риски
Linux CI не запускался; схема не смонтирована в Compose, ни один процесс её не грузит (G-135); Gate не проверяет возможности (G-137); правило evidence — предположение (G-134); остаточный риск OD-20/ADR-104: `password: tiger` принимается (G-140); store_result публичен внутри backend (G-142).

## 13. Обновлённые документы и статусы
STATUS (S14), ADL (ADR-101…103), KNOWN_GAPS (G-134…G-143), DECISIONS_PENDING (OD-20), ECC_USAGE, CONTEXT_HANDOFF, `reviews/S14_REVIEWS.md`. REQUIREMENTS_TRACEABILITY: API-MVP-019/020/022, PROC-MVP-013/029 → PARTIAL (S14 TESTED локально). CONTRACT_TRACEABILITY_MAP: новый раздел «Internal Worker contracts DOC-007» и пометка о реестре WorkerDefinition. `check_prompts.py`: 40 prompts, issues 0.

## 14. Статус DoD
✅ 4 точки покрыты тестами · ✅ обязательные тесты §9 · ✅ миграции upgrade/drift · ✅ security negative tests · ✅ review (CRITICAL 0) · ⚠️ observability: счётчик `ai_res.worker_contracts.rejected` есть, дашборд/алерт — нет · ❌ Linux CI · ✅ traceability-карты · N/A Temporal replay (нет workflow-изменений).

## 15. Можно ли начинать следующий этап
S15 (LLM Gateway port) не зависит от S14 по промпту — можно после слияния PR. S22/S23 требуют закрыть G-135/G-137/G-142.
