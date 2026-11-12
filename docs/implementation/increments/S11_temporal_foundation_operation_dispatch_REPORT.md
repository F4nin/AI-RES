# S11 — Temporal foundation и dispatch Operation: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S11_temporal_foundation_operation_dispatch.md` · **Итоговый статус:** VERIFIED (Linux CI зелёный (PR #11, ci 43233885212/43233901267: backend, infra-runtime, infra-static, contracts — success; contracts 43233885308/43233901331); влит в `main`, b0991a5)

## 1. Что реализовано
- Пакеты `ai_res/orchestration` (контракты, `OperationWorkflow`, Activities, порт `OperationPlatform`, HTTP-клиент, воркеры) и `ai_res/runtime` (процессы `manager`, `worker`); очереди `ai-res-manager` / `ai-res-workers`; Manager и Worker не импортируют БД (контракт import-linter) и не имеют DB-секретов/сети `data`.
- Внутренний Platform API (`api/internal_api.py`, порт 8001): `start-acknowledgement` и `failure`, service-токен Ed25519, таблица capability, tenant-scope как заявление, проверяемое под RLS; сервис `OperationOrchestrationService` (transition + event + outbox + audit в одной транзакции).
- Идемпотентный старт из Outbox: `TemporalStartPublisher` + процесс `cli/dispatcher.py`; `claim(..., destinations=)` — dispatcher берёт только свои destination.
- Workflow-skeleton: подтверждение старта, затем терминальный FAILED `ORCHESTRATION_NOT_IMPLEMENTED` (WorkerRun не создаётся; ADR-089).
- Compose: `platform-api`, `outbox-dispatcher`, `manager-runtime`, `worker-runtime`, сеть `workflow`, секреты `manager_signing_key`/`service_public_keys`; runbook `docs/runbooks/temporal.md`.
- Не сделано (вне scope/за пределами): LangGraph и исполнение WorkerRun (S23), cancel (S12), reconciler (G-107), аутентификация Temporal (G-104), реальный производитель start-команды.

## 2. Нормативная база и проверка Registry
Registry v4.1; API Contracts v1.10 §7.2, §9; Decision v1.6 §2; Spec Inc. 7 / Add. v1.13; Infrastructure v1.7; Process v1.9 §13. Файлы на месте, discrepancy report не требуется. Нормативные документы и Registry не менялись.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/src/ai_res/orchestration/*`, `runtime/*` | новые пакеты |
| `backend/src/ai_res/api/{internal_api,serve_internal}.py`, `cli/dispatcher.py` | новые |
| `backend/src/ai_res/modules/operations/orchestration_service.py`, `modules/events/temporal_start.py` | новые |
| `modules/events/{outbox_repository,dispatcher,metrics}.py`, `platform/config.py`, `pyproject.toml`, `uv.lock` | destination-фильтр, метрика, настройки, зависимости (temporalio, httpx), контракт import-linter |
| `contracts/internal/AI_RES_Platform_Internal_API_v0.1.yaml` | WORKING overlay |
| `infra/compose.yaml`, `infra/scripts/{check_compose,secrets_dev,wait_stack}.py` | сервисы, сети, секреты, проверки |
| тесты: `backend/tests/integration/{temporal,postgres/test_internal_platform_api,postgres/test_orchestration_e2e}`, `unit/test_orchestration_units.py`, `infra/tests/*` | новые/расширены |
| docs: ADR-087…090, G-104…G-111, NCP-14, OD-19, `reviews/S11_REVIEWS.md`, `runbooks/temporal.md`, ECC_USAGE | см. §13 |

## 4. Изменения API / контрактов / событий
Публичный API и AsyncAPI не менялись. Добавлен внутренний контракт (WORKING, не за reverse proxy, NCP-14); событий с новыми схемами нет (используются существующие OperationEvent/CloudEvents). Новый Outbox destination `orchestration.operation-start` (строка маршрута, не контракт события). Совместимость: `claim(destinations=None)` по умолчанию = поведение S10.

## 5. Миграции и совместимость
Миграций нет (ревизии 0001–0015 без изменений). Роли/RLS не менялись; dispatcher работает под существующей `ai_res_outbox_dispatcher`.

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-087 | Пакеты без БД, компактные контракты, версионирование через major + patching + replay-fixtures; retry по времени | ACCEPTED |
| ADR-088 | Внутренний Platform API, service-токены, фиксированная capability-таблица | ACCEPTED |
| ADR-089 | Маршрут старта, фильтр destination, skeleton fail-closed | ACCEPTED |
| ADR-090 | Топология Compose: сеть `workflow`, секреты, изоляция | ACCEPTED |

WORKING-значения (не утверждены): `ACTIVITY_BUDGET` 15 мин, интервалы/коэффициент retry, TTL токена 60 с, таблица capability, порт 8001.

## 7. Устранённые несогласованности / NCP
NCP-14 (контракт внутреннего API; кто подтверждает QUEUED). Отклонения от буквы документов: QUEUED→RUNNING одной транзакцией в первой Activity (G-110); Worker Versioning не основной механизм (G-105).

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `security-reviewer`, `silent-failure-hunter`, `architect`, `code-reviewer` | blind-first независимое review | `reviews/S11_REVIEWS.md` |
| Context7 | только общие вопросы по temporalio (без кода и идентификаторов AI RES) | уточнён Replayer/WorkflowHistory/id-политики |
Не запускались: `planner`, `database-reviewer`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer` (основание — §11 review-файла). Temporal-специалиста в ECC нет — компенсация `architect` + `silent-failure-hunter`.

## 9. Тесты и проверки
| Gate | Команда | Результат (точно) |
|---|---|---|
| lint / types | `uv run ruff check .`, `uv run mypy` (backend) | All checks passed; Success: no issues found in 120 source files |
| import-linter | `make backend-check` | Contracts: 9 kept, 0 broken |
| S11 + unit набор после правок review | `uv run pytest tests/integration/temporal tests/integration/postgres/test_internal_platform_api.py tests/integration/postgres/test_orchestration_e2e.py tests/unit -q` | 289 passed (до двух добавленных тестов гонки/412; финальный полный прогон — ниже) |
| runtime стека | `make up`; `pytest tests/runtime -k "orchestr or manager_and_worker or healthy or secrets_mounted"` | 15 passed |
| contracts | `make contracts-check` | validate-openapi/asyncapi/jsonschema, lint-openapi, breaking — [ok]; `contracts/internal` в toolchain не входит (G-109) |
| полный `make pre-pr` | см. §12 | `make pre-pr`: backend `1025 passed` (15:48), infra static и contracts зелёные; `infra-test` в нём дал 1 failed (устаревший allowlist сети `data` в `test_persist_023…`, исправлен: добавлены `platform-api`/`outbox-dispatcher`, явная проверка, что Manager/Worker не на `data`); повторно `make infra-test` — `207 passed` |

## 10. Security / authorization cases
Без токена 401, неизвестный issuer 401, без capability 403, подмена tenant → тот же 404, что и отсутствие; терминальная Operation не переоткрывается; параллельные ack — по одному queued/started; повтор безопасен; дубль доставки Outbox → один workflow; retry Activity не создаёт второй переход; permanent-ошибка не ретраится; история Temporal без запрещённых данных (scan) и replay (fixture + негатив недетерминизма); Manager/Worker: нет DB env/секретов, `postgres` не резолвится из их сети; у Worker нет секретов; Worker Activity отказывает. Не проверялось: Worker с чужим стартом workflow (открыто — G-104).

## 11. Независимое review
`reviews/S11_REVIEWS.md`: CRITICAL 0; HIGH сведены в 4 группы — две исправлены (R1–R4), две зафиксированы с решением владельца (G-104/OD-19, G-108). Дельта правок отдельным агентом не пересматривалась.

## 12. Не выполненные проверки, ограничения, риски
- Compose-сервер Temporal 1.29.7 отличается от dev-сервера тестов (G-105).
- Нет reconciler'а, производителя start-команды и аутентификации Temporal (G-107, G-104): реальные типы Operation на маршрут направлять нельзя.
- В локальной БД остались тестовые организации/Operation (`s11-smoke`, `s11-runtime-test`).

## 13. Обновлённые документы и статусы
ADL (ADR-087…090), KNOWN_GAPS (G-104…G-111; G-98 PARTIAL, G-99 закрыт для dispatcher), NCP-14, DECISIONS_PENDING (OD-19), ECC_USAGE, IMPLEMENTATION_STATUS, CONTEXT_HANDOFF, runbook, review-файл. Traceability: INF-MVP-002 → IMPLEMENTED (частично, до S13/S32).

## 14. Статус DoD
✅ runtimes и очереди; ✅ skeleton + идемпотентный старт; ✅ replay-тесты; ✅ scan истории; ✅ изоляция Manager/Worker (статика + живой стек); ✅ runbook; ✅ reviews; ✅ зелёный Linux CI (ci 43233885212, 43233901267); ❌ аутентификация Temporal/reconciler — вне этапа, открыто.

## 15. Можно ли начинать следующий этап
Да — S12 (cancel + первый consumer), с условием: до первого производителя start-команды закрыть G-107 и принять решение по G-104/OD-19. CI S11 зелёный.
