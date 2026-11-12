# S12 — Operation API, process primitives, cancellation, SSE: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S12_operation_api_process_primitives_sse.md` · **Итоговый статус:** VERIFIED (Linux CI зелёный: PR #13 и PR #14, см. IMPLEMENTATION_STATUS). `make pre-pr` целиком не запускался (см. §12).

## 1. Что реализовано
- Типизированные переходы Operation (`state_machine.py`, равна baselined JSON; применяется в `OperationRepository.transition`).
- `getOperation` (`GET /operations/{id}`, ETag, словарь OAS).
- `requestOperationCancellation` (`POST /operations/{id}/cancel`, 202): ACCEPTED → CANCELLED сразу; активная → CANCEL_REQUESTED + Outbox-команда; сигнал workflow и идемпотентная reconciliation `confirm_cancellation`; терминальный исход не перезаписывается.
- `completeUpload` (`POST /uploads/{id}/complete`, 202): проверка размера и SHA-256 хранилищем (`S3ObjectStore`, presigned HEAD), SourceVersion, Operation `SOURCE_INGESTION`.
- SSE `GET /projects/{id}/events`: из истории агрегатов, HMAC-курсор, ACL и сессия на каждом опросе, gap-сигнал, закрытие при отзыве.
- Не сделано: конвейер ingestion (S27), reconciler (G-107/G-117), история событий Operation (вне MVP).

## 2. Нормативная база и проверка Registry
Registry v4.1; State Machine v1.2; Decision v1.6 §2; API Contracts v1.10; ADR-033. Файлы на месте, discrepancy report не требуется.

## 3. Созданные и изменённые файлы
Новые: `api/events_api.py`, `modules/events/stream.py`, `modules/operations/{cancellation,state_machine}.py`, `modules/sources/object_store.py`, тесты `test_operation_cancellation.py`, `test_operation_state_machine.py`. Изменены: `api/{app,read_api,write_api,internal_api}.py`, `modules/operations/{repository,orchestration_service}.py`, `modules/readmodel/queries.py`, `modules/sources/repository.py`, `modules/iam/sessions.py` (`touch=`), `modules/events/{temporal_start,metrics}.py`, `cli/dispatcher.py`, `orchestration/*`, `platform/config.py` (sse_*), `policy/policy_config.{json,sha256}`, контракт внутреннего API, тесты write/read/policy/repositories/event_delivery/temporal.

## 4. Изменения API / контрактов / событий
Публичный OAS и AsyncAPI не менялись (операции `getOperation`, `requestOperationCancellation`, `completeUpload`, `streamProjectEvents` уже в OAS). Внутренний контракт v0.1: путь `cancellation-confirmation`. Новые destination Outbox: `orchestration.operation-cancel`.

## 5. Миграции и совместимость
Миграций нет. Политика: версия `2026-11-12.3`, SHA-256 пересчитан.

## 6. Решения, принятые самостоятельно
ADR-091 (переходы и отмена), ADR-092 (SSE), ADR-093 (completeUpload). WORKING: роли `operation.cancel`/`source.upload_complete`, `sse_*`, `completion_policy_version="wip-1"`.

## 7. Устранённые несогласованности / NCP
Новых NCP нет. Расхождение словаря initiator DB/OAS — G-112.

## 8. ECC: фактически использованные agents
`security-reviewer`, `silent-failure-hunter` (blind-first, read-only) → `reviews/S12_REVIEWS.md`. Context7 — общие вопросы по temporalio. Второй раунд (по решению владельца): `architect`, `code-reviewer`, `fastapi-reviewer`, `pr-test-analyzer`, `type-design-analyzer`. Не запускался `planner`.

## 9. Тесты и проверки
| Gate | Команда | Результат |
|---|---|---|
| lint / types | `uv run ruff check .`, `uv run mypy` | All checks passed; no issues in 125 source files |
| import-linter | `uv run lint-imports` | Contracts: 9 kept, 0 broken (поймал `sqlalchemy` в `api/`, исправлено) |
| полный backend (до исправлений review) | `uv run pytest -q -p no:cacheprovider` | **1084 passed**, 535 warnings, 16:40 |
| полный backend (после исправлений review) | то же | **1110 passed**, 535 warnings, 17:32; ruff, mypy, lint-imports чистые |
| contracts | `make contracts-check` | verify-mirror, validate-*, lint-openapi, breaking — [ok] |

## 10. Security / authorization cases
IDOR для cancel/completeUpload/SSE — один и тот же 404; viewer на completeUpload — 403; аноним на SSE — 401; подделанный, чужесессионный и «мусорный» Last-Event-ID — 422; отзыв сессии закрывает поток; терминальный исход не отменяется (409); подделанный tenant в confirm — 404; несовпадение размера/суммы и объект без проверенной суммы — отказ; истёкший intent — EXPIRED без обращения к хранилищу; недоступное хранилище — 503 без изменений; идемпотентный повтор не дублирует Operation/версию.

## 11. Независимое review
`reviews/S12_REVIEWS.md`: два раунда; CRITICAL 0, HIGH 1 (G-117, решение владельца: reconciler до S23, ADR-094); MEDIUM — исправлены по сути, остальные в gaps.

## 12. Не выполненные проверки, ограничения, риски
- `make pre-pr` и `make infra-test` локально не запускались; backend-набор и contracts-check выполнены локально, весь набор (backend, infra-static, infra-runtime, contracts) прошёл на Linux CI.
- completeUpload проверен против HTTP-фейка за реальным `S3ObjectStore`, не против живого MinIO (G-115).
- Все ревьюеры из промпта отработали (два раунда). Находки второго раунда: исправлены или в gaps (ADR-094, G-121, G-122).
- Открытые: G-112…G-120, в т.ч. HIGH G-117 (зависшая отмена).

## 13. Обновлённые документы и статусы
ADL (ADR-091…093), KNOWN_GAPS (G-112…G-120), ECC_USAGE, IMPLEMENTATION_STATUS, CONTEXT_HANDOFF, `reviews/S12_REVIEWS.md`. REQUIREMENTS_TRACEABILITY (API-MVP-009, -010) и CONTRACT_TRACEABILITY_MAP (4 операции) обновлены.

## 14. Статус DoD
✅ переходы и getOperation; ✅ cancel + reconciliation; ✅ completeUpload (проверка хранилищем, идемпотентность, IDOR); ✅ SSE (ACL, курсор, gap, отзыв); ✅ нет Operation Events history API; ✅ reviewers выполнены (два раунда); ✅ трассируемость; Linux CI зелёный (PR #13, PR #14).

## 15. Можно ли начинать следующий этап
Да — S13, после зелёного CI PR с исправлениями review; G-117/G-107 (reconciler) обязательны до S23.
