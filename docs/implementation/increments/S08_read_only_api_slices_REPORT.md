# S08 — Read-only API vertical slices: Increment Report

**Дата:** 2026-11-12 · **Промпт:** `increments/prompts/S08_read_only_api_slices.md` · **Итоговый статус:** TESTED (локально; Linux CI не запускался, коммитов и PR нет; VERIFIED — по решению владельца после CI)

## 1. Что реализовано
12 GET Public API v1.3: listProjects, getProject, listEpics, getEpic, listTasks, getTask, listRequirements, listRequirementVersions, listSources, listArtifacts, listArtifactVersions, getWorkerRun — с ACL через Policy Engine, cursor-пагинацией, ETag (getProject, getTask), явными DTO. Записи (S09) и Operations/SSE (S12) не затронуты. Не реализовано: индекс расположения объектов (G-87), троттлинг (G-88).

## 2. Нормативная база и проверка Registry
Registry v4.1 и все документы из промпта существуют в `docs/architecture/`. Расхождения (не блокируют): у Project нет колонки `goal` (G-84); нет таблицы определений Worker для `workerRole` (G-85); форма `result_ref` не определена (G-86); списки версий в OAS без `limit`/`cursor` (G-89). `docs/architecture/` не менялся.

## 3. Созданные и изменённые файлы
| Файл | Изменение |
|---|---|
| `backend/src/ai_res/api/read_api.py` | новые маршруты, DTO-мапперы, пагинация, разрешение проекта |
| `backend/src/ai_res/modules/readmodel/queries.py` | запросы чтения (keyset) |
| `backend/src/ai_res/api/app.py`, `api/identity.py` | регистрация маршрутов; общая зависимость сессии |
| `backend/src/ai_res/policy/{policy_config.json,.sha256}` | 7 read-действий, версия 2026-11-12.1 |
| `backend/src/ai_res/policy/{enforcer,engine}.py` | `decide`/`record_allow`, якорь аудита отказа, константа причины |
| `backend/src/ai_res/platform/config.py` | `cursor_ttl_seconds`, `read_lookup_max_projects` (WORKING) |
| `backend/tests/integration/postgres/test_read_api.py`, `test_read_api_schemathesis.py`, `test_policy_engine.py` | тесты |
| `backend/pyproject.toml`, `uv.lock` | dev-зависимость schemathesis 4.33.2 |
| `docs/implementation/*` | ADR-074…077, G-84…G-90, OD-15/OD-17, трассируемость, review, отчёт |

## 4. Изменения API / контрактов / событий
Новые эндпоинты — только GET из OAS v1.3. Аддитивно: `limit`/`cursor` на двух списках версий (G-89). Событий нет. Overlay и OAS не менялись.

## 5. Миграции и совместимость
Миграций нет, схема и RLS не менялись (ADR-075). Версия политики 2026-11-12.1 — новая конфигурация с пересчитанной контрольной суммой.

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-074 | слой чтения, DTO, пагинация, ETag | ACCEPTED |
| ADR-075 | разрешение проекта по id, видимость списков, без вложенных соединений | ACCEPTED |
| ADR-076 | матрица read (решение владельца: только члены проекта + org AUDITOR), WORKING | ACCEPTED |
| ADR-077 | поля без источника: `goal` null, `workerRole` UNKNOWN | ACCEPTED |

## 7. Устранённые несогласованности / NCP
Исправлено в коде S07: отказ по неизвестному проекту давал 503 вместо 404 (аудит не мог привязаться к проекту). NCP не готовились.

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `security-reviewer`, `code-reviewer`, `silent-failure-hunter` | независимое blind-first review | `reviews/S08_REVIEWS.md`: CRITICAL 0, HIGH 1 (исправлено) |
| не запускались: `planner`, `architect`, `fastapi-reviewer`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, `type-design-analyzer`, команды `/plan`, `/code-review`, `/quality-gate` | — | компенсация: TDD и мутационные проверки inline; архитектурное соответствие — ADR и import-linter |

## 9. Тесты и проверки
| Gate | Команда | Результат |
|---|---|---|
| G1 | `make backend-check` (ruff, mypy, lint-imports) | passed; 8 контрактов импорта kept |
| G2–G3 | `make backend-test` (PostgreSQL 16, Testcontainers) | 872 passed |
| G4 | schemathesis (`test_read_api_schemathesis`) по всем 12 GET; `make contracts-test` | 13 passed; contracts 22 passed |
| G5 | `test_read_api`, `test_policy_engine` | входят в 872 |
| G6 | миграций нет | N/A |
| прочее | `make infra-test` / `infra-test-runtime` | 185 / 99 passed |
| сводно | `make pre-pr` | exit 0 («all CI-equivalent checks passed») |

Мутационная проверка: удаление обязательного поля из DTO — schemathesis падает (2 failed). Исключены проверки schemathesis `ignored_auth` и `positive_data_acceptance` (обоснование в тесте: 401 проверяются отдельно; невалидный подписанный курсор — 400 по замыслу).

## 10. Security / authorization cases
IDOR: чужой проект/организация и несуществующий id → идентичный 404 для всех 11 по-объектных маршрутов; 401 без сессии на всех 12; списки без недоступных объектов; курсор чужого пользователя/другой операции/испорченный/просроченный/с неверной формой → 400 без обращения к БД и аудиту; отзыв проектной роли → немедленный 404; отзыв членства в организации → 401; PROJECT_ADMIN без MFA → 404/пустой список; равенство SQL-видимости и Policy Engine (роли × MFA × статус членства); 60 параллельных запросов без исчерпания пула; предел перебора → 503.

## 11. Независимое review
`reviews/S08_REVIEWS.md`. Дельта исправлений отдельным агентом не пересматривалась.

## 12. Не выполненные проверки, ограничения, риски
Linux CI не запускался. G-87 (стоимость промаха), G-88 (нет троттлинга), OD-17. Матрица политик WORKING. Параметры `cursor_ttl_seconds`, `read_lookup_max_projects` — WORKING.

## 13. Обновлённые документы и статусы
STATUS, ADL (074–077), KNOWN_GAPS (G-84…G-90), DECISIONS_PENDING (OD-15, OD-17), CONTRACT/REQUIREMENTS_TRACEABILITY, ECC_USAGE, CONTEXT_HANDOFF, reviews/S08_REVIEWS.md.

## 14. Статус DoD
✅ все GET соответствуют OAS и проходят ACL-тесты · ✅ endpoint вне контракта не создан · ✅ результаты созданы, заглушек нет (помеченные UNKNOWN/null — G-84/85) · ✅ обязательные тесты раздела 9 зелёные · N/A миграции · ✅ negative-тесты · ➖ observability: используются существующие middleware (OTel, redaction) без новых метрик · ✅ review (3 агента; CRITICAL/HIGH устранены) · ✅ документы · ❌ Linux CI.

## 15. Можно ли начинать следующий этап
Да, S09 (Controlled write commands) разблокирован по зависимостям; рекомендуется сначала PR и зелёный Linux CI. Для S09 важны: формат ETag `"v<N>"` уже совместим с `parse_if_match`; `goal` (G-84) нужен для createProject.
