# S17 — Tool Registry и Tool Gateway

**Дата:** 2026-11-18 · **Статус:** IMPLEMENTED, локальный срез проверен.
**Scope evidence:** `7f0c29f9519217dba722ad1f5b6396d8a02216da` + рабочий diff
`feat/g02-tool-registry-manager`. Общая приёмка G02 предстоит.
[Промпт](prompts/S17_tool_registry_tool_gateway.md) · [Паспорт](../groups/G02_WORK.md)

Повторная локальная проверка 2026-11-20 на Darwin arm64, Python 3.13.5 и
PostgreSQL 16.15. Команда
`backend/.venv/bin/python -B -m pytest -c backend/pyproject.toml -q backend/tests/integration/postgres/test_worker_tool_service.py backend/tests/unit/test_tool_gateway.py backend/tests/unit/test_tool_mcp.py --tb=short`
вернула exit 0, 15 passed, 0 failed/skipped, 11.17 с. Полная приёмка
G02 остаётся открытой.

Общий `make backend-test` на Darwin arm64 2026-11-24 для того же HEAD
и актуального рабочего diff вернул exit 0, 3414 passed, 4 skipped. Пропуски
относятся к отдельно запускаемому native срезу S20/S21. Итоговый Ubuntu
`make pre-pr` того же HEAD с рабочим diff вернул exit 0, Backend 3419 passed.
Состав и результаты
общей приёмки см. в [отчёте S20](S20_project_epic_intake_manager_REPORT.md).

## 1. Что реализовано

Tool Definition с точными версиями, typed schema, классификацией и deployment
limits. Backend-only `project.metadata.read/1.0` использует tenant-scoped
Project Repository. Каталог сверяет доступность и свежую Policy, Gateway
проверяет каждый вызов, включая модель scope/expiry/revocation, input/output,
rate, timeout и метаданные аудита. Операция, Run и grant защищены согласованным
порядком блокировок. Отдельный transactional executor для локальных команд
проверяет предусловие и результат, связывает effect и durable replay receipt.
MCP adapter принимает только exact allowlist и требует явного включения.

## 2. Нормативная база и Registry

DOC-011 v1.0 §§3–7, 9–10, 13, 16 и дополнение v1.0, DOC-075 v1.1 §5,
DOC-018 v1.5 §§6–7, DOC-072 и DOC-068. Исходная сверка Registry v4.1 нашла
все 74 canonical пути. Открытых нормативных конфликтов в S17 не выявлено.

## 3. Файлы

- `backend/src/ai_res/modules/tools/`, `policy/tool_authority.py`,
  `application/tools.py`, `application/tool_commands.py`.
- `operations/repository.py`, `worker_runs/repository.py`, import boundaries.
- `0027_worker_tool_grants.py`, SQL snapshot, PostgreSQL и unit тесты шлюза.

## 4. API и контракты

Внутренняя типизированная граница. Используются существующие exact pins
`toolId/version/operations/grantRef` WorkerRunEnvelope. Публичных endpoint
и новых типов событий для S17 нет.

## 5. Миграция

Additive 0027 `6e23a65c9ce0` от `c97e3bf386f1`. Композитный FK запуска,
FORCE RLS, доступ на чтение и две колонки rate accounting у существующей
Backend роли. Владелец имеет ограниченный migration-mode policy.
Scope grant runtime API не редактирует. Backfill не требуется.

## 6. Техническое решение

[ADR-142](../ARCHITECTURE_DECISION_LOG.md) фиксирует схему каталога, порядок
локальной транзакции и распределение семейств инструментов по этапам.

## 7. Расхождения

Старые строки статуса ожидали SLICE-01. Проверены merged PR #34/#35 и CI.
Начало S17 разрешено новым поручением. Открытые transport gaps относятся
к интеграции последующих этапов.

## 8. ECC

[Журнал](../ECC_USAGE.md) фиксирует реально использованные planner,
architect, general/Python/database/security review, поиск fail-open,
анализ тестов и локальные checklists.

## 9. Проверки

Darwin arm64, Python 3.13.5, Docker 29.2.0, pinned PostgreSQL 16.15.
`make pre-push-fast` на рабочем diff до 0028 — exit 0, 1908 passed,
4 dependency warnings, 15 import contracts kept. Целевой прогон
`uv run --locked pytest -q tests/unit/test_tool_mcp.py tests/unit/test_tool_gateway.py tests/unit/test_manager_questions.py tests/integration/postgres/test_worker_tool_service.py tests/integration/postgres/test_migrations.py tests/integration/postgres/test_schema_drift.py`
из backend до 0028 — 36 passed, 1 существующее предупреждение, exit 0.
См. сводку группы для проверок после 0028.

## 10. Security cases

Проверены отсутствие, отзыв и expiry grant, истечение identity, другой
tenant/identity/contract, отмена родительской Operation, конкурентный лимит,
невалидный input/output, approval-required и отказы Policy/Audit. Отключённый
и неразрешённый MCP блокируются. Запись откатывается при ошибке output;
два параллельных вызова с одним ключом сохраняют один result ref.
Одинаковый ключ с другим запросом вызывает конфликт.

## 11. Независимое review

Два scoped APPROVE после исправлений, 0 открытых CRITICAL/HIGH.
[Запись review](../reviews/G02_S17_S20_REVIEWS.md).

## 12. Limitations

Вход доверенного Runtime и production grant lifecycle подключаются в
ADR-129/S22/S23. Реальной MCP сетевой интеграции и deployed write bindings нет.
Модель и платные вызовы для этапа не использовались. Общие pre-pr и Linux CI
запланированы на общий diff после реализации G02.

## 13. Документация и traceability

Обновлены STATUS, HANDOFF, group passport, ADL, ECC_USAGE и traceability.

## 14. DoD

Локальный per-call Gate, PostgreSQL и security tests, audit/telemetry и
independent review выполнены в описанном scope. До VERIFIED нужна общая
проверка группы на итоговой версии.

## 15. Следующий шаг

S20 продолжается в этой же группе. Перед первым producer обязательны
ADR-129 и G-107. S21 следует после реализованного intake/approval.
