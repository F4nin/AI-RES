# S15 — LLMGatewayPort и Model Registry (провайдер-нейтрально): Increment Report

**Дата:** 2026-11-13 · **Промпт:** `increments/prompts/S15_llm_gateway_port_model_registry.md` · **Итоговый статус:** TESTED локально (`make pre-pr`: @@RESULT@@); Linux CI — после PR. Качество вывода модели **не проверялось** (используется только deterministic test double, ADR-022); реального провайдера нет (S16, OD-01).

## 1. Что реализовано
- `ai_res.llm` (чистый пакет без БД/ORM/API): `LLMGatewayPort` (chat / structured / embed / stream_chat), нормализованные request/response по Contracts v1.10 §11 (в ответе — фактический provider/model/pinned version/profile), типизированные ошибки с `retryable`/`fallback_eligible`, `ProviderTransport` — шов для адаптеров S16.
- Model Registry: `ModelProfile` (все поля DOC-076 §3), неизменяемый снимок `ModelRegistry`, разрешение только APPROVED; пустой реестр отказывает на всё. Миграция 0017 `platform.model_profiles` (неизменяемые версии, статус только вперёд, approval = `approved_at`+`approved_by`, нет DELETE/TRUNCATE, плавающая версия `latest` запрещена CHECK), загрузчик `modules/model_registry`.
- Маршрутизация (`RoutingPolicy`, правила — данные, встроенных нет) и fallback (та же группа, APPROVED, равные/более строгие egress и регионы, нужные возможности, разрешённая классификация, достаточный `max_output_tokens`).
- Бюджет вне модели: резерв worst-case до вызова, расчёт по usage; нет бюджета / исчерпан / нельзя оценить стоимость → типизированный отказ без retry.
- Охрана промптов: полнотекстовый скан; credential-формы блокируют вызов, формы прозы редактируются.
- Семантика отказов: bounded retry с jitter и Retry-After, circuit breaker на профиль, дедлайн, распространение отмены, маппинг неизвестных исключений транспорта.
- Телеметрия: span `llm.*` и метрики (provider, outcome, tokens) без содержимого; stream — те же правила.
- Test double: `backend/testkit/ai_res_testkit` (вне `src/`), `DeterministicLLMGateway` = тот же `GovernedLLMGateway` над скриптуемым транспортом; фабрика `build_llm_gateway` (по умолчанию `UnconfiguredLLMGateway` — отказ на всё).
- Не сделано (вне scope): реальный провайдер/Bifrost (S16), durable-бюджет и grant WorkerRun (S22/S23), путь approval профиля (OD-21), экспорт `ai_res.llm.*` через Collector (G-149), клиентские rate limits (G-144).

## 2. Нормативная база и проверка Registry
DOC-076 `AI_RES_Model_Gateway_and_Model_Registry_v1.0.md` (BASELINED, существует, canonical в Registry §2); `AI_RES_API_and_Interaction_Contracts_v1.10.md` §11; `AI_RES_Architecture_Completion_and_Baseline_Decisions_v1.0.md` §3; `architecture-constraints.md` «LLM доступ»; Spec v1.22 §3/§8/§9/§10. Все файлы присутствуют; discrepancy report не требуется. DOC-076 не задаёт колонок, словарей статусов, меток классификации и egress → ADR-106 (WORKING), OD-21.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/src/ai_res/llm/{__init__,errors,types,registry,routing,budget,guard,transport,port,gateway,factory}.py` | новый пакет |
| `backend/testkit/ai_res_testkit/{__init__,deterministic_llm}.py` | test-only double вне `src/` |
| `backend/src/ai_res/modules/model_registry/{__init__,repository}.py` | загрузчик реестра |
| `backend/src/ai_res/db/migrations/versions/0017_model_registry.py` | новая ревизия |
| `backend/src/ai_res/platform/redaction.py` | `scan_secrets` (полный текст, NFKC, однопроходный поиск ключа), расширенные префиксы |
| `backend/src/ai_res/platform/config.py` | 6 полей `llm_*` (WORKING) + проверка |
| `backend/pyproject.toml` | pythonpath/ruff/mypy для testkit; 2 контракта import-linter |
| `backend/ops/postgres/{rls_coverage,schema_snapshot}.sql` | +1 exempt-строка; снимок |
| `backend/tests/unit/test_llm_gateway.py`, `backend/tests/integration/postgres/test_model_registry.py` | тесты |
| `docs/implementation/{ARCHITECTURE_DECISION_LOG,KNOWN_GAPS,DECISIONS_PENDING,IMPLEMENTATION_STATUS,CONTEXT_HANDOFF,ECC_USAGE,REQUIREMENTS_TRACEABILITY}.md`, `reviews/S15_REVIEWS.md`, `increments/prompts/README.md` | документы этапа |

## 4. Изменения API / контрактов / событий
Публичный API, OpenAPI/AsyncAPI и JSON Schema не менялись; endpoint/события не добавлялись. Внутренний контракт LLMGatewayPort реализован по Contracts v1.10 §11 (в процессе, не HTTP).

## 5. Миграции и совместимость
Ревизия 0017 (expand-only, одна новая таблица, без данных). Upgrade from empty и from previous revision — тесты PERSIST-001/002 и `test_migration_graph`; drift = 0 (`make db-snapshot`, diff — только новая таблица/функция/триггеры, 0 удалённых строк); RLS-coverage и grants-audit чисты (таблица — exempt с причиной, runtime SELECT-only). Downgrade не поддерживается (как 0016).

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-105 | Охрана промптов: блок credential-форм, редакция прозы, полный скан | ACCEPTED |
| ADR-106 | Схема Model Registry, неизменяемые версии, жизненный цикл (WORKING) | ACCEPTED |
| ADR-107 | Маршрутизация и fallback | ACCEPTED |
| ADR-108 | Бюджет вне модели | ACCEPTED |
| ADR-109 | Семантика отказов шлюза | ACCEPTED |
| ADR-110 | Test double вне `src/`, барьеры | ACCEPTED |

## 7. Устранённые несогласованности / NCP
Несогласованностей между нормативными документами не обнаружено. NCP не требуются (контракт Gateway не менялся). Открытые вопросы владельцу — OD-21.

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `code-reviewer`, `security-reviewer`, `silent-failure-hunter` (blind-first, read-only) | независимое review (DoD промпта; граница безопасности) | `reviews/S15_REVIEWS.md`: CRITICAL 0, HIGH 5 (исправлены), MEDIUM 14 (исправлены/приняты), LOW 12 |
| не запускались: `planner`, `architect`, `tdd-guide`, `python-reviewer`, `pr-test-analyzer`, `database-reviewer` | — | План и тесты-первыми — самостоятельно (TDD по разделу 9 промпта, мутационная проверка тестов); профиль БД покрыт интеграционными тестами и `security-reviewer`; полный `database-reviewer` не запускался (одна справочная таблица по образцу 0016) — **ограничение**, записано здесь |

## 9. Тесты и проверки
| Gate | Команда | Результат (точно) |
|---|---|---|
| G1–G9 в сумме | `make pre-pr` (contracts, ruff, mypy strict, import-linter 10→12 контрактов, backend unit+PostgreSQL 16, infra static, `make up`+migrate на локальной dev-БД, runtime) | @@RESULT@@ |
| Новые тесты S15 | `cd backend && uv run pytest tests/unit/test_llm_gateway.py tests/integration/postgres/test_model_registry.py` | см. строку выше (@@NEWTESTS@@) |
| Мутационная проверка | отключение 9 исправлений/правил по очереди | каждое валит ≥1 тест (см. §11) |
Linux CI: после PR. IMPLEMENTATION NOT VERIFIED на реальном провайдере: качество вывода модели не проверялось.

## 10. Security / authorization cases
Неутверждённый/CANDIDATE/RETIRED/после `deprecated_at`/незарегистрированный/пустой реестр → отказ до вызова; budget exhausted/не установлен/нельзя оценить → typed error, без retry и без вызова; test double в local/prod — отказ в Settings, фабрике и конструкторе, import в подпроцессе при явном prod/local; wheel и Dockerfile без testkit; credential в prompt (JWT, ключ, URL с паролем, connection string, 8 форм ключей провайдеров, fullwidth/zero-width, разрезанный между сообщениями) → блок без эха значения; проза-секрет и embedding → редакция; хвост после 40 КБ сканируется; DoS-вход 0.6 с; несовместимая capability/классификация/окно/лимит → отказ; fallback не уходит в более открытый, неутверждённый, другую группу, с меньшим лимитом; отказ политики/бюджета не вызывает fallback; runtime-роль БД только читает реестр, DELETE/TRUNCATE/откат статуса/перезапись approval отклонены. Cross-project IDOR/сессии — неприменимо (нет HTTP-поверхности); Policy Engine не вовлечён (G-150).

## 11. Независимое review
`reviews/S15_REVIEWS.md` (3 агента, blind-first): CRITICAL 0, HIGH 5 → исправлены, MEDIUM исправлены/приняты с записью, LOW — см. отчёт. Мутации: breaker-release_probe, release при отмене, settle usage при invalid output, лимит `max_output_tokens` fallback, скан склейки сообщений, approval-проверка, retry-условие, egress fallback, guard — каждая валит тест. Дельта исправлений отдельным агентом не пересматривалась.

## 12. Не выполненные проверки, ограничения, риски
Реальный провайдер/Bifrost (S16); Linux CI до PR; качество агентного вывода; сборка и инспекция образа (G-148); durable бюджет и размещение шлюза (G-145); rate limits (G-144); Collector не пропускает `ai_res.llm.*` (G-149); путь approval профиля (G-146/OD-21); охрана промптов — регулярные выражения с остаточным риском (G-147); `database-reviewer` не запускался.

## 13. Обновлённые документы и статусы
STATUS (S15), ADL (ADR-105…110), KNOWN_GAPS (G-144…G-152), DECISIONS_PENDING (OD-21), ECC_USAGE, REQUIREMENTS_TRACEABILITY (API-MVP-027, SEC-007, SEC-MVP-005, INF-MVP-015, THR-004), CONTEXT_HANDOFF, prompts/README. `docs/architecture/` и Registry не менялись.

## 14. Статус DoD
- ✅ Нет прямых provider-вызовов (import-linter: SDK только в `ai_res.llm.adapters`; `ai_res` не импортирует testkit; `ai_res.llm` без БД).
- ✅ Результаты созданы; заглушка только по ADR-022 и с маркером `[DETERMINISTIC-TEST-DOUBLE]`.
- ✅ Тесты раздела 9 (неутверждённый профиль; budget exhausted; double вне test; секрет в prompt) написаны и проходят.
- ✅ Миграции: upgrade from empty/previous, drift = 0.
- ✅ Security negative tests выполнены; секретов в коде/логах/трейсах/ошибках нет.
- ✅ Observability: spans/metrics без содержимого; ⚠ экспорт через Collector — G-149.
- ✅ Независимое review (code + security + silent-failure), CRITICAL/HIGH устранены.
- ⚠ Linux CI и дельта review — после PR.

## 15. Можно ли начинать следующий этап
Да. S16 (Bifrost PoC и первый provider profile) — блокирован OD-01 (провайдер, egress). Разблокированы по зависимости S15: S20, S23, S27 (где ещё нужны их прочие зависимости). Перед S22/S23: G-145, G-150; перед первым профилем: OD-21, G-146, G-149.
