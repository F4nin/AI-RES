# S06 — независимые review

**Дата:** 2026-11-11 · **Метод:** ADR-035/037 — read-only агент `database-reviewer` (с учётом ecc-precedence: RLS через транзакционный контекст, не Supabase). Агент статически читал миграции 0007–0010, `rls_coverage.sql` и тесты; сам БД не запускал. Остальные агенты из списка промпта (`code-reviewer`, `silent-failure-hunter`, `architect`, `python-reviewer`, `pr-test-analyzer`, `type-design-analyzer`) **не запускались** — см. §3.

## 1. Находки и их устранение

| ID | Серьёзность | Суть | Статус |
|---|---|---|---|
| C1 | CRITICAL | Все status-guard-ы только на UPDATE: строку можно вставить сразу в APPROVED/VERIFIED/CONFIRMED/PUBLISHED с выдуманными фактами (requirement/artifact versions, uploads, rule_versions, traceability_links, extraction_records) | **Исправлено** (0011 `require_initial_state`, тесты `test_lifecycle_facts_cannot_be_supplied_at_creation`) |
| C2 | HIGH | Baseline без approval, возможен форк цепочки | **Частично**: approval человека в той же транзакции + `n` следует за `n-1` исправлено; статус Change Request не проверяется (словарь WORKING → G-72, OD-14) |
| C3 | HIGH | Элемент контекста мог ссылаться на rule_version чужого tenant / неутверждённую | **Исправлено** (0011 `guard_item_insert`, тест); статусы версий для остальных kind-ов — открыто (G-72) |
| C4 | HIGH | Approver rule_version мог быть пользователем другой организации | **Исправлено** (0011 `guard_rule_approver`); разделение author/approver — владельцу (OD-14) |
| C5 | HIGH | source_version с object_key без проверенного upload | **Исправлено** (CHECK `object_key ⇔ upload_id`, правка 0007: ревизия не выпускалась; DROP в миграциях запрещён тестом offline-SQL) |
| M1 | MEDIUM | Approval на REJECTED/SUPERSEDED версию | **Исправлено** (0011 `guard_approval_insert`); «последнее решение выигрывает» — открыто (G-72) |
| M2 | MEDIUM | APPROVED артефакта не требует validation_report | **Открыто** (G-72, OD-14: нужен ли review — WORKING) |
| M3 | MEDIUM | Запечатывание через `created_at = now()` | **Открыто** (G-72); подделка времени не позволяет расширить baseline (проверка числа элементов), риск — совпадение микросекунды |
| M4 | MEDIUM | Индексы под FK | **Исправлено** (0011, 12 индексов) |
| M5 | MEDIUM | Номера не привязаны к счётчикам | **Открыто** (G-72) |
| M6 | MEDIUM | expires_at upload не проверяется переходом | **Открыто** (G-72), до появления upload-потока |
| L1–L6 | LOW | SYSTEM-правила читаются без контекста (намеренно, нужен тест/пометка); CHECK уровня на rule_versions; монотонность указателя; IN_BASELINE->SUPERSEDED; lifecycle решений; event-таблицы без замечаний | Учтены в G-72; L1 — осознанное поведение (SYSTEM-правила глобальны) |

## 2. Второе review — `silent-failure-hunter` (репозитории, 0011, тесты)

| № | Серьёзность | Суть | Статус |
|---|---|---|---|
| 1 | HIGH | `confirm`/`mark_approved` сообщали успех при нуле изменённых строк | **Исправлено**: `RETURNING`, not-found / `StateConflict` |
| 2 | HIGH | Тест подтверждения ничего не проверял (оба UPDATE могли быть no-op) | **Исправлено**: статус и факты читаются после каждого шага, негативные случаи, точные сообщения |
| 3 | HIGH | Dedupe до блокировки → гонка финализаторов давала сырой IntegrityError; `.one()` на пропавший источник | **Исправлено**: блокировка источника первой, not-found; тест на 3 параллельных финализатора |
| 4 | HIGH | Dedupe по содержимому молча возвращал старую версию | **Частично**: результат несёт `is_current`; правило «откат к старому содержимому» — решение (G-72) |
| 5 | MEDIUM | `expires_at` не проверялся; неверный код при расхождении размера | **Исправлено** в репозитории (EXPIRED, SIZE_MISMATCH/CHECKSUM_MISMATCH, тест); на уровне БД — G-72 |
| 6 | MEDIUM | Guard-ы принимают противоречивые approval-факты | **Открыто**: доменное правило не определено → G-72, OD-14 (не изобретено); `decision` валидируется в репозитории |
| 7 | MEDIUM | `require_initial_state` fail-open при опечатке имени колонки | **Исправлено** (0011: `IS NOT TRUE`, `?`); параметризованный тест по колонкам |
| 8 | MEDIUM | ~40 широких `pytest.raises(IntegrityError)` | **Частично**: ключевые тесты проверяют текст guard-а; остальные широкие — известное ограничение |
| 9 | MEDIUM | Нет идемпотентности `create`/`register_upload` и теста конкурентности счётчика | Счётчик: **тест добавлен** (4 параллельных → 1..4). Idempotency-Key — слой выше (S07/S09) |
| 10–12 | LOW | org/prj от вызывающего; RLS-зависимость guard-а; CHECK уровня у rule_versions | CHECK **добавлен** (0009); остальное задокументировано |

## 3. Третье review — `code-reviewer` (scope, качество, миграции, документы)
0 CRITICAL, 0 HIGH, 8 MEDIUM, 7 LOW; вердикт APPROVE с обязательными правками. Устранено: два имени констрейнтов длиннее 63 символов (усечение PostgreSQL) укорочены; RLS-тест не был вакуумным — добавлены проверка привязки политики к tenant-контексту для ВСЕХ RLS-таблиц схем S06 и изоляции rules/event history по проектам и организациям; upgrade-тест теперь наполняет данные S06 до последней ревизии; assertion «really the previous state» восстановлен; `finalize_version`/`verify_upload` берут `source_id` и статус из БД (DTO не доверяется), несоответствие состояния — типизированный `StateConflict` (перенесён в `platform/concurrency.py`); `author_type` проверяется до записи; типы `datetime`; формулировки ADR-056/060 и G-70 приведены в соответствие с реальностью (проверка наличия факта, а не полномочий; продюсеров событий нет). Вынесено в G-72: SUPERSEDED прежней версии, путь EXTRACTED, привязка approval к актору (S07), слабые правила системных уровней, baseline без одобренного CR, `decisions.status` без initial-state guard. Не сделано: полный репозиторный слой (G-69).

## 4. Остаточный риск
Owner-роль может отключить триггеры (ops-уровень, как и в S05). Выводы агентов статические; динамически подтверждены только исправления с тестами. Дельта исправлений после третьего review отдельным агентом не пересматривалась.

## 5. Ограничения (честно)
Из перечисленных в промпте `architect`, `python-reviewer`, `pr-test-analyzer`, `type-design-analyzer` не запускались (запущены `database-reviewer`, `silent-failure-hunter`, `code-reviewer`). Статус этапа — не выше TESTED.
