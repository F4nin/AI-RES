# S10 — Outbox dispatcher, Inbox и CloudEvents: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S10_outbox_dispatcher_inbox_cloudevents.md` · **Итоговый статус:** VERIFIED (локально `make pre-pr` ok; GitHub Actions на Linux зелёный (2026-11-12, PR #9, коммит 248cd08: ci 43220712053 и 43220722294, contracts 43220712147 и 43220722299 — backend/infra-static/infra-runtime/contracts success))

## 1. Что реализовано
- **OD-13 решён владельцем (2026-11-12) → ADR-084:** `dataschema = urn:aires:schemas:<type>`; `source` — URN по виду агрегата; NCP-09…11 — следовать AsyncAPI (правки нормативных документов остаются NCP).
- **Dispatcher** (`modules/events/dispatcher.py`): claim отдельной транзакцией → проверка контракта → publish без открытой транзакции (таймаут) → mark под fencing (owner, attempt, replay_count); transient → backoff с jitter, бюджет попыток, затем карантин; permanent → карантин; неизвестный тип/major → карантин + счётчик `unknown_major_event`; нет consumer'а → карантин `NO_CONSUMER`. `run_forever` со счётчиком ошибок и периодической проверкой роста (`observe`).
- **Контрактная валидация** (`contract.py`): envelope целиком против сообщений AsyncAPI v1.6 (+ `format: date-time`), ключи секретов/контента в `data`, согласие envelope со строкой (`check_row`); пустой контракт — ошибка старта.
- **Durable consumer** (`consumer.py`): Inbox marker + checkpoint + эффект в одной транзакции; режимы CONTIGUOUS (gap → defer, не пропуск) и MONOTONIC; advisory lock на (consumer, aggregate).
- **Controlled replay** и операторский CLI `python -m ai_res.cli.outbox status|replay --confirm`; метрики OpenTelemetry (`metrics.py`), алерты роста без автоудаления (`alerts.py`); runbook `docs/runbooks/outbox.md`.
- **Не сделано (намеренно, с пробелами):** Compose-сервис dispatcher и маршруты `destination → consumers` (нет consumer'ов до S12; запуск без них отправил бы всё в карантин) — G-98; упаковка файла контракта в образ — G-99; аудит replay и роль утверждающего — G-100; replay на стороне Inbox, retention, маршрутизация алертов — G-101; реальный MeterProvider, нагрузка — G-102. **Dispatcher как процесс в стеке не запускается.**

## 2. Нормативная база и проверка Registry
Event Model v1.4 §4, §8–§9, §15–§17; AsyncAPI v1.6; Physical Model v1.2 §8–§9; API Contracts v1.10 §13; Resilience §1; Persistence Blueprint (PERSIST-015/016). Файлы canonical и существуют (Registry v4.1). Discrepancy: Event Model §15 («consumers игнорируют неизвестные опциональные поля») ↔ закрытая схема AsyncAPI → NCP-13 / G-103.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/src/ai_res/db/migrations/versions/0015_inbox_checkpoints_outbox_replay.py` | новая: `audit.inbox_checkpoints`, `outbox_events.replay_count`, индексы claim, триггеры |
| `modules/events/{dispatcher,consumer,contract,delivery,alerts,metrics}.py` | новые |
| `modules/events/{outbox,inbox}_repository.py` | stats, replay, fencing с replay_count, checkpoint, QUARANTINED |
| `modules/events/envelope.py` | комментарии: формы dataschema/source = DECIDED (значения не менялись) |
| `cli/outbox.py` | новый |
| `backend/ops/postgres/{rls_coverage.sql,schema_snapshot.sql}` | exempt для политики checkpoint, снимок схемы |
| `backend/pyproject.toml`, `uv.lock` | runtime: jsonschema, referencing, rfc3339-validator, pyyaml; dev: types-* |
| `tests/integration/postgres/test_event_delivery.py`, `tests/unit/test_event_delivery_units.py` | новые; правки `test_migrations.py`, `test_audit_platform_schema.py` (списки) |
| `docs/runbooks/outbox.md`, ADL (ADR-084…086), KNOWN_GAPS (G-98…G-103, G-56/G-57), DECISIONS_PENDING (OD-13 закрыт), NCP-13, reviews/S10_REVIEWS.md | документация |

## 4. Изменения API / контрактов / событий
Публичный API не менялся. Контракты событий не менялись (wire-форма из S05/S09, значения dataschema/source зафиксированы). Нового endpoint/события нет.

## 5. Миграции и совместимость
Ревизия `0015` (expand-only: таблица + колонка с default, CHECK через NOT VALID → VALIDATE). Upgrade from empty и from previous revision (PERSIST-001/002), drift snapshot, RLS coverage, grants audit — в `make pre-pr` зелёные. Индексы создаются без CONCURRENTLY (таблица мала; для выросшей — только CONCURRENTLY, записано в ревизии). Downgrade запрещён (как в S05–S09).

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-084 | OD-13: формы dataschema/source (решение владельца) | ACCEPTED |
| ADR-085 | Dispatcher, классификация ошибок, WORKING-конфигурация (batch 8, lease 60 с, timeout 5 с, attempts 8, backoff 1–60 с, пороги алертов) | ACCEPTED |
| ADR-086 | Consumer: checkpoint, режимы порядка, контрактная валидация | ACCEPTED |

## 7. Устранённые несогласованности / NCP
NCP-09…11 остаются PROPOSED (решение: следовать AsyncAPI). Новое NCP-13 (§15 ↔ закрытая схема).

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `code-reviewer`, `database-reviewer`, `silent-failure-hunter` (blind-first, read-only) | независимое review (ecc-precedence п. 2) | `reviews/S10_REVIEWS.md`: CRITICAL 0, HIGH 0 (два «HIGH» silent-failure исправлены), остальное исправлено или в gaps |
| `planner`, `architect`, `tdd-guide`, `python-reviewer`, `pr-test-analyzer` | не запускались (план — вертикальные срезы по промпту; профильные агенты не нужны сверх трёх) | отмечено |

## 9. Тесты и проверки
| Gate | Команда | Результат |
|---|---|---|
| G1–G9 локально | `make pre-pr` | exit 0: backend **964 passed** (PostgreSQL 16 Testcontainers, 14:13), contracts **22**, infra static **186**, runtime **99**; ruff, mypy strict, import-linter (8 kept) чисто |
| S10 | `uv run --locked pytest -q tests/unit/test_event_delivery_units.py tests/integration/postgres/test_event_delivery.py` | зелёные в составе полного прогона |
| Linux CI | GitHub Actions, PR #9 | success: ci 43220712053, 43220722294 (backend 11м05с/8м35с, infra-static, infra-runtime), contracts 43220712147, 43220722299 |

Обязательные тесты промпта покрыты: crash after commit-before-publish; PERSIST-015 (crash after publish-before-mark → duplicate → no-op); PERSIST-016 (inbox crash before commit → нет следа); gap → defer; poison не блокирует поток; конкурентные dispatcher'ы; payload privacy (контракт, ключи, логи); dispatcher видит все tenants; рост → алерт, без удаления (у ролей нет DELETE).

## 10. Security / authorization cases
Fencing: чужой owner, чужой attempt, тот же owner после рестарта, до/после replay; lease lost (published/failed) не принимается как успех; подделанный/чужой envelope (`ENVELOPE_MISMATCH`, триггер БД); чувствительные ключи в `data`; неизвестный тип/major; checkpoint нельзя откатить, другие роли не читают `inbox_checkpoints`; `replay_count` меняется только на +1 при replay; текст исключений не попадает ни в БД, ни в логи (только класс/код).

## 11. Независимое review
`reviews/S10_REVIEWS.md` (три агента). Дельта после исправлений агентом не пересматривалась; проверена тестами.

## 12. Не выполненные проверки, ограничения, риски
Dispatcher не развёрнут и не проверен как процесс в стеке (G-98); метрики не проверены на реальном MeterProvider; план запроса claim и `stats()` не измерены на большом backlog (G-102); аудит replay (G-100); WORKING-значения не откалиброваны (OD-02). Exactly-once нигде не заявляется.

## 13. Обновлённые документы и статусы
STATUS (S10 TESTED), CONTEXT_HANDOFF, ADL, KNOWN_GAPS, DECISIONS_PENDING, NCP, ECC_USAGE, REQUIREMENTS_TRACEABILITY (PERSIST-015/016), runbook.

## 14. Статус DoD
- ✅ Тесты доставки зелёные на PostgreSQL; ✅ exactly-once не заявлен; ✅ результаты созданы (dispatcher, inbox-библиотека, тесты, отчёт); ✅ миграция: empty/previous/drift; ✅ negative security tests; ✅ review проведено, CRITICAL/HIGH устранены.
- ⚠️ Observability: инструментировано, экспорт не проверен (G-102). ⚠️ Dispatcher «как процесс» — библиотека и CLI, без Compose (G-98). ❌ VERIFIED: ждёт Linux CI.

## 15. Можно ли начинать следующий этап
Да, после слияния PR #9 в `main` (ветку S11 создавать от актуального `main`). Первый consumer (S12, SSE) закроет G-98. Дополнительно в PR #10 исправлен нестабильный тест S08.
