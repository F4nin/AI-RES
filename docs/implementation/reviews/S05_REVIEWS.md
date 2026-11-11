# S05 — независимые review и disposition

**Дата:** 2026-11-11 · **Этап:** S05 (P0, ADR-037) · Метод: агенты ECC, read-only, параллельно, независимо от автора. Ограничение (ADR-035/037): та же модель, что и автор; это не замена подписи security owner (OD-03, один раз перед релизным baseline S37).

**Раунды.**
1. *Первый раунд (до паузы):* 6 review, 0 CRITICAL. HIGH: обход Gate порядком вставки (database + security + architect) и форма CloudEvents-envelope (architect). Подробные тексты того раунда не сохранены — известны только эти итоги из `CONTEXT_HANDOFF.md`; Gate-HIGH исправлен deferred-триггером, envelope — см. G-56.
2. *Второй раунд (ниже):* 4 review после правок первого — `database-reviewer`, `security-reviewer`, `silent-failure-hunter`, `architect`. CRITICAL — 0 у всех четырёх. HIGH: database (Gate не привязан к последней оценке), architect (H1 migration-политики, H2 envelope, H3 audit-атомарность). Все подтверждённые находки исправлены или внесены в gaps; решение владельца по G-56 принято (вариант A), по H1 принято (вариант 1).

3. *Третий раунд — verification-проход дельты (по решению владельца):* `database-reviewer`, `security-reviewer`, `silent-failure-hunter` (26 мутаций). CRITICAL/HIGH — 0; 2 MEDIUM (+1 MEDIUM по тестам) и 6 LOW подтверждены, исправлены в этом же проходе или внесены в gaps (ниже). После исправлений дельта третьего раунда **независимо не пересматривалась** — подтверждена только полным набором тестов и мутационной проверкой новых тестов гонок (ослабление блокировок роняет три теста).

Подтверждение находок: security и database-агенты воспроизводили дефекты PoC-тестами под ролью `ai_res_api` на PostgreSQL 16; silent-failure — мутациями на копии кода (19 мутаций). Architect запускал только чтение.

## security-reviewer
| # | Sev | Находка | Disposition |
|---|---|---|---|
| M1 | MEDIUM | Старая READY-оценка запускает run при более новой BLOCKED (воспроизведено) | **Исправлено:** BEFORE-guard и deferred-проверка требуют максимальный `evaluation_number`; тест `test_start_requires_the_latest_evaluation` (две транзакции и одна). Полная сериализация — G-60 |
| M2 | MEDIUM | Envelope outbox не привязан к событию/tenant (воспроизведено: envelope чужого tenant) | **Исправлено:** `assert_outbox_matches_event` сверяет id/type/eventId/organizationId/projectId/aggregate*; тест на 6 подделок (ADR-054) |
| L1 | LOW | `iam.sessions.absolute_expires_at` изменяем | **Исправлено:** immutable + CHECK idle ≤ absolute; тест |
| L2 | LOW | `completion_policy_*` Operation изменяемы | **Исправлено:** immutable; тест |
| L3 | LOW | Оракул существования по клиентскому PK (`NewOperation.id`) | **Gap G-52:** серверные ID обязательны для S08/S09 |
| L4 | LOW | Guard секретов узкий; нет токенов digest/ciphertext/hmac | **Исправлено частично:** guard на всех jsonb-границах + новые токены; ограничение «только ключи» — **G-66** |
| L5 | LOW | Нет `hide_parameters=True` | **Исправлено** |
| L6 | LOW | Полный доступ API к credential-таблицам | **Gap G-62:** column grants в S07 |
| L7 | LOW | Gate проверяет только форму | **Gap G-60** (S13) |
| — | процесс | Реестр `operation_type` — WORKING, засеян из ADR | **Gap G-65** |

## database-reviewer
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | HIGH | Gate не привязан к последней оценке (TOCTOU) | **Исправлено** (см. security M1) |
| 2 | MEDIUM | `worker_results` принимается для run без Gate | **Исправлено:** триггер `require_started_open_run` (FOR SHARE, нетерминальный); тест |
| 3 | MEDIUM | READY допускает FAIL-проверки | **Gap G-60** (зависит от WORKING `check_code`) |
| 4 | MEDIUM | Нет защиты от дублей WorkerRun | **Исправлено:** UNIQUE `(org, project, task_id, attempt_number)`; lineage между Task — **G-61** |
| 5 | LOW/MED | Событие без outbox-строки коммитится | **Gap G-54** (закрыто для пользователей репозитория) |
| 6 | LOW | Непрерывность пропускается при невидимом агрегате | **Gap G-62** (нужен произвольный GUC) |
| 7 | LOW | Нет индексов под FK, лишние UNIQUE | **Gap G-59** |
| 8 | LOW | Auth-таблицы под org-RLS: pre-auth lookup | **Gap G-48** (S07) |
| 9 | LOW | `rls_coverage.sql` не проверяет содержимое политик | **Gap G-59**; добавлена проверка гейтинга owner-политики |

Проверено и чисто: `FOR SHARE` против гонки status/insert, исправленный триггер непрерывности (O(log n)), deferred Gate-триггер, `forbid_unset`/`keep_terminal_status`, append-only (privileges + триггеры + TRUNCATE), ENABLE+FORCE RLS, composite FK, откат/повтор миграций.

## architect
| # | Sev | Находка | Disposition |
|---|---|---|---|
| H1 | HIGH | ADR-034 п.5 (migration-политики owner под FORCE RLS) выпал; PERSIST-017 идёт под суперпользователем | **Исправлено (вариант 1, владелец):** ревизия 0006, флаг `app.migration_mode`, правило аудита `owner_migration_policy_missing`, честный тест через migrator → `SET ROLE ai_res_owner` (ADR-055) |
| H2 | HIGH | Envelope не соответствует AsyncAPI v1.6 (G-56) | **Исправлено (вариант A, владелец):** ADR-054, `modules/events/envelope.py`, контрактный тест на 36 типов. Остаток: OD-13, NCP-09…11 |
| H3 | HIGH | Атомарность audit не тестируется | **Gap G-64:** репозитория audit в S05 нет; перенесено на S07 |
| M1 | MEDIUM | `event_type`/`actor_type` без реестра | **Исправлено частично:** реестр в коде (= State Machine v1.2, drift-тест) и CHECK на `actor_type`; CHECK на `event_type` не добавлен |
| M2 | MEDIUM | Три словаря актёров | **Gap G-64** |
| M3 | MEDIUM | Нет import-linter правил для llm/Manager/Worker | **Gap G-63** |
| M4 | MEDIUM | Нет отчёта и сохранённых review | **Исправлено:** этот файл и отчёт S05 |
| M5 | MEDIUM | PERSIST отложенные/частичные | **Отражено в отчёте §14** |
| L | LOW | Дубль G-48/G-60; G-54, G-59 неточны; пустой `limitations`; аллокация `evaluation_number`; `NewOperation.id`; project-RLS org-level; seed operation_type | **Исправлено/внесено:** G-48 объединён; G-54, G-59 переписаны; G-59/G-60/G-52/G-65; project-изоляция projects/memberships опирается на Policy Engine (S07, ADR-050) |

Проверено и чисто: нет `gate_results`, одна `ai_res_db`, нет cross-db FK, нет `MAX()+1`, имена/типы по coding-standards, словари = State Machine v1.2, WORKING-значения не присвоены молча, прочие тесты §9 промпта присутствуют.

## silent-failure-hunter
| # | Sev | Находка | Disposition |
|---|---|---|---|
| M1 | MEDIUM | TTL и key_id/project idempotency не покрыты (мутации M8, M19 проходили) | **Исправлено:** тест expiry/key_id/project (project-несовпадение — fail-closed ошибка RLS до сравнения) |
| M2 | MEDIUM | Секреты в `store_result` не покрыты | **Исправлено:** тест `test_stored_payloads_reject_secret_keys_and_empty_updates` |
| M3 | MEDIUM | `bool`-результаты inbox/outbox можно проигнорировать | **Смягчено:** docstring «caller MUST act», enum не вводился; обязательное правило для S10 |
| M4 | MEDIUM | PERSIST-017..020 синтетические | **Отражено честно** (отчёт §14); добавлен реальный тест owner-backfill |
| L5 | LOW | Fencing outbox только по owner | **Исправлено:** owner + attempt + срок lease |
| L6 | LOW | `mark_failed` без лимита попыток | **Исправлено:** `max_attempts` → QUARANTINED; тест |
| L7 | LOW | `cas_update`/`update_epic` без изменений | **Исправлено:** ValueError; тест |
| L8 | LOW | Статус Task меняется свободно | **Gap G-61** |
| L9 | LOW | Тавтология в тесте | **Исправлено** |
| L10 | LOW | `pytest.raises(ProblemError)` без `code` | **Исправлено:** проверяются коды |

Подтверждённо защищено мутациями (тесты падали): claim игнорирует sequence/lease/available_at/квоту попыток, `mark_*` без owner, inbox без sequence/hash, CAS без `row_version`, not-found как conflict (утечка), `from_status` не проверяется, дубли destination, секретные ключи в event data.

---

# Третий раунд — verification-проход дельты исправлений (2026-11-11)

Метод: те же ограничения (read-only агенты ECC, одна модель с автором). Database-агент воспроизвёл дефекты PoC на PostgreSQL 16; security-агент работал статически (без живой БД) — его выводы по триггеру и ролям подтверждены чтением; silent-failure — 26 мутаций на копии `backend/` (21 убита, 5 выжили).

## database-reviewer
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | Deadlock: `FOR SHARE` на run в `require_started_open_run`, twin-вставка ждёт на UNIQUE, первая обновляет статус (воспроизведено) | **Исправлено:** `FOR NO KEY UPDATE`; `test_twin_result_inserts_for_one_run_do_not_deadlock` (падает на старом поведении) |
| 2 | MEDIUM | Старт со старой оценкой возможен при незакоммиченной новой (FK берёт только KEY SHARE) (воспроизведено) | **Исправлено в S05 (решение владельца):** триггер `execution.lock_run_for_evaluation` (BEFORE INSERT на оценку, `FOR NO KEY UPDATE` на run) + та же блокировка в `guard_worker_run_start`; два теста гонки в обе стороны (падают без блокировки). Полная сериализация по-прежнему включает финальную ревалидацию S13 (G-60) |
| 3 | LOW | `app.migration_mode` живёт до конца всего `upgrade` (одна транзакция) (воспроизведено) | **Исправлено:** `on_version_apply` в `env.py` выключает флаг после каждой ревизии; тест на двух синтетических ревизиях |
| 4 | LOW | Триггер outbox не сверяет `event_type`/`schema_version` со строкой события | **Исправлено** (+ тест) |
| 5 | LOW | Правило `owner_migration_policy_missing` — подстрока; усечение имени политики | **Исправлено:** точное сравнение нормализованного выражения (+ sabotage t8 `true OR gate`); проверка длины имени в 0006 |

## security-reviewer
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | `is_sensitive_key` обходится слитными/множественными ключами; ложные срабатывания `source_id`, `SourceVersion`, из-за чего событие со ссылкой на источник нельзя записать | **Исправлено:** множественное число, слитные написания, пары `signing/encryption/access/master key`, токены `pwd`, `bearer`; content-токены не срабатывают на ключи-ссылки; `refs` проверяются по формату типа, не по ключам; тесты. Ограничение «только ключи» — G-66 |
| 2 | LOW | Триггер сверяет envelope частично (нет `source`/`subject`/`dataschema`/`operationId`) | **Исправлено:** все привязаны (+4 подделки в тесте) |
| 3 | LOW | `hide_parameters` не скрывает серверный DETAIL; `error_code` без проверки формата | **Частично:** формат `error_code`/`reason_code` проверяется в Python; маппинг ошибок — **G-67** (S08) |
| 4 | INFO | `reason_code` свободный текст | **Исправлено** (формат `[A-Z][A-Z0-9_]{0,63}`) |
| — | замечание | `tasks.acceptance_criteria` и `operations.context_package_snapshot` пишутся без guard | **Проверено:** значения задаёт доменный сервис из S08/S09, внешний ввод туда не попадает в S05; guard добавить при появлении команд (внесено в G-66 как граница метода) |

## silent-failure-hunter (26 мутаций: 21 убита, 5 выжили)
| # | Sev | Находка | Disposition |
|---|---|---|---|
| 1 | MEDIUM | `mark_failed` без `lease_owner` и без `lease_until >= now()` — мутанты выжили | **Исправлено:** тесты другого owner и истёкшего lease |
| 2 | LOW | Нет теста секретов в `IdempotencyRepository.complete` | **Исправлено** |
| 3 | LOW | Ветка `project_id` в idempotency недостижима при RLS | **Принято:** второй барьер, RLS WITH CHECK срабатывает раньше (G-68) |
| 4 | INFO | Первая проверка «последняя оценка» в `guard_worker_run_start` дублируется deferred-триггером | **Принято:** defense in depth (ранний отказ) |
| 5 | LOW | `claim` без наблюдаемости quarantine; `max_attempts` в двух местах; один код для expired и fingerprint | **Gap G-68** |
| 6 | LOW | `assert_no_sensitive_keys` обходит `set`/`frozenset` | **Исправлено** |

Подтверждённо защищено мутациями (тесты падали): fencing `mark_published` (owner/attempt/lease), `mark_failed` по attempt и лимиту попыток, «последняя оценка» в deferred-триггере, три ветки `require_started_open_run`, UNIQUE попытки, immutable `completion_policy_snapshot` и `absolute_expires_at`, owner-политика одной таблицы, expiry и `key_id` idempotency, секреты в `store_result`, пустой `cas_update`, not-found как конфликт, ленивый guard в `ReadinessRepository.record`.
