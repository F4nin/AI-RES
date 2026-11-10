# TEST_STRATEGY

Основание: Implementation Spec v1.22 §8 и Add. v1.1 §4, v1.2, v1.13–v1.18; Blueprint §12; `.claude/rules/testing-and-verification.md`; ADR-003, ADR-026. Статические проверки ≠ runtime evidence. Покрытие кода — дополнительная метрика, не DoD.

## 1. Типы проверок

| Тип | Что доказывает | Инструменты | Где обязательно |
|---|---|---|---|
| Static | Типы, стиль, архитектурные границы, схемы | ruff, mypy --strict, import-boundary tests, валидаторы контрактов (ADR-004) | Все этапы с кодом |
| Unit | Доменная логика, state machines, политики | pytest, hypothesis (stateful для state machines) | Все |
| Integration | Поведение с реальным PostgreSQL 16 / Temporal / MinIO | Testcontainers, temporalio test env, Compose | S04+ |
| Contract | Соответствие handler ↔ OpenAPI/AsyncAPI/JSON Schema; backward compatibility | schemathesis, jsonschema, oasdiff, AsyncAPI diff | S01, S08+ |
| Security / authorization | IDOR, ACL, CSRF, сессии, grants, fail-closed, injection, secrets | pytest negative suites, bandit, pip-audit, npm audit | S02+ |
| Migration | Upgrade from empty/previous, drift, роли, RLS coverage, backfill resume | Alembic + Testcontainers | S04–S06 и любые ревизии |
| Reliability / recovery | Duplicate/out-of-order delivery, crash points, replay, cancel races, restore | fault injection, Temporal replayer, restore drill | S10–S12, S23, S32 |
| E2E | Пользовательские сценарии через UI | Playwright, axe | S35–S36, S39 |
| Regression | Неизменность поведения при изменениях; AI-регрессия | pytest suites, eval harness | Все; S33 |
| Evaluation | Качество агентного вывода по task-class | eval harness (deterministic + rubric + adversarial) | S33 (пороги — OD-02) |
| Performance | Baseline, нагрузка, capacity | LT сценарии DOC-033 | S38 (SLO — OD-02) |

## 2. Обязательные негативные наборы (сквозные)

Cross-project IDOR без утечки; stale/revoked session → 401; revoked Worker grant; Policy outage → deny; invalid enum/transition; unknown major contract → fail closed; missing/stale If-Match → 412; idempotent retry без дублей, key reuse → 409; Worker не пишет в БД и не self-grant; Gate блокирует при failing checks; replay Temporal; Activities идемпотентны; outbox duplicate/out-of-order; SSE ACL/retention gap; отсутствие секретов в logs/traces/events/results; prompt injection из источников не исполняется.

## 3. Правила

- Тест проверяет поведение, а не наличие файла/импорт.
- SQLite не используется как доказательство PostgreSQL семантики.
- Test double LLM — только в `test` профиле (ADR-022); отчёт явно указывает, что качество модели не проверялось.
- Флейки не отключаются: карантин с issue в KNOWN_GAPS и сроком.
- Каждый отчёт этапа содержит точные команды и результаты (junit/xml в `reports/` при наличии).

## 4. Структура

`backend/tests/{unit,integration/postgres,integration/temporal,contract,security,architecture}`; `frontend/tests/{unit,e2e}`; `contracts/examples/{valid,invalid}`.

## Матрица PERSIST → этап (ADR-035)

| Тесты | Этап | Примечание |
|---|---|---|
| PERSIST-001, 002, 003 (single head), 004 (offline `--sql`) | S04 | `CREATE INDEX CONCURRENTLY` — autocommit_block |
| PERSIST-005…014, 017…020 | S05 | 017–020 на синтетической test-only ревизии (ADR-011) |
| PERSIST-015, 016 | S10 | Нужен dispatcher |
| PERSIST-021 | S32 | Restore/PITR |
| PERSIST-022 | S37 | Ротация секретов |
| PERSIST-023 | S03 / S23 | Compose-сеть: нет пути Manager/Worker → PostgreSQL |
| PERSIST-024 | S05 | — |

Отложенные тесты не считаются пройденными. Распределение 005…014/024 уточняется по тексту Blueprint §12 в S05; расхождение — в отчёт этапа.
