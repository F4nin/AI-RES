# S09 — независимое review (2026-11-12)

Основание: `.claude/rules/ecc-precedence.md` («Когда запускать агентов-ревьюеров», п. 2): этап меняет границы безопасности (ACL, CSRF, подписанные URL), RLS/миграцию с заменой триггерной функции, контракты событий и fail-closed поведение. S09 не P0 по ADR-037.
Порядок: blind-first (агенты не читали отчёт автора и этот файл), агенты read-only, отчёты сохранены автором в сжатом виде. Состав: `security-reviewer`, `database-reviewer`, `silent-failure-hunter`, `code-reviewer`. Агенты не заменяют человеческое approval и независимый QA Worker.

**Итог:** CRITICAL — 0, HIGH — 0 во всех четырёх отчётах. Все ревьюеры отметили, что выводы статические (тесты агентами не запускались).

## 1. Исправлено в рамках этапа

| # | Источник | Находка | Исправление |
|---|---|---|---|
| R1 | database M2, silent M1 | Перехват `IntegrityViolation` в createProject скрывал любую ошибку целостности как «проиграл гонку» (500 без причины) | Принимается только SQLSTATE 23505 по `pk_projects`; иное логируется (только имя ограничения) и пробрасывается |
| R2 | database M1 | Гонка PATCH: CAS-проигравший получал 409 вместо 412 | `AggregateVersionConflict` → 412 `VERSION_CONFLICT` |
| R3 | security M2 | `proposeRequirementVersion` не проверял статус текущей версии: pointer мог уйти с версии `IN_BASELINE` | 409 `STATE_TRANSITION_NOT_ALLOWED` при `IN_BASELINE`/`REJECTED`/`SUPERSEDED` (WORKING, ADR-080/OD-18); тест `test_a_proposal_on_a_baselined_version_is_refused_and_the_pointer_stays` |
| R4 | silent M2/L5, code M5 | Не было теста сбоя завершающей транзакции createProject и проверки статуса COMPLETED записи идемпотентности | `test_create_project_resumes_after_a_failed_closing_transaction_and_ends_completed`, `test_successful_commands_close_their_idempotency_records`; tx3 логирует закрытие конкурентным запросом |
| R5 | code L7 | «PATCH не проверен с merge-patch+json» | Находка неверна: хелпер `send()` всегда шлёт PATCH как `application/merge-patch+json` |

## 2. Принято и зафиксировано (не исправлялось)

| # | Источник | Находка | Решение |
|---|---|---|---|
| A1 | security M1 | Учётка подписи не ограничена (можно указать root MinIO) | G-92: сервисная учётка с префиксной политикой — S27; в Compose секреты хранилища не подключены (uploads → 503) |
| A2 | security M3, silent L9, code L10 | Нет rate limiting; `locate()` — O(читаемых проектов) на by-id запись | G-87/G-88 (S33/S37), OD-17 |
| A3 | code M1 | Replay истёкшего/использованного intent → 409 `IDEMPOTENCY_KEY_REUSED` (код предназначен для иного fingerprint) | Осознанно (ADR-082); нужен отдельный зарегистрированный код или решение владельца — OD-18, G-95 |
| A4 | code M2 | Лимиты текстов/evidenceRefs не заданы в OAS (422 на валидное по OAS тело) | WORKING-значения, G-95/OD-18; требуется NCP на контракт |
| A5 | code M3, security L6 | `registrationKind` не хранится (только в аудите) | Нет колонки/семантики в схеме; не изобретаем (OD-18) |
| A6 | code M4 | Source создаётся при intent и остаётся сиротой при брошенной загрузке | Осознанно (ADR-082: Source+Upload в одной транзакции); очистка — S12/S27; проверить видимость в `GET sources` — G-96 |
| A7 | code M6, security L8 | Подпись PUT не проверена на живом MinIO; повтор PUT в окне TTL | G-92; IMPLEMENTATION NOT VERIFIED в части приёма хранилищем; finalize (S12) обязан проверять checksum |
| A8 | silent M3/M4 | Конфигурация загрузок и key ring проверяются лениво (503 при запросе, не на старте) | Fail-closed сохранён, поведение покрыто тестами; ранняя проверка на старте — G-97 |
| A9 | silent M2 | Запись createProject может остаться IN_PROGRESS между Tx2 и Tx3 | G-94 (политика истечения G-58); повтор с тем же ключом довершает |
| A10 | security L7, code L9 | Членство первого администратора вне отдельного policy-действия | Подтверждение владельца — OD-18 (ADR-083); отдельное действие `membership.grant_initial` — предложение |
| A11 | security L4 | Bidi/управляющие символы в однострочных полях | G-97: нормализация текстовых полей — вместе с политикой sanitisation (S12) |
| A12 | security L5 | `evidenceRefs` не проверяются на принадлежность проекту | Хранятся с `verified:false` (ADR-080); потребители обязаны разрешать их под ACL |
| A13 | database M3 | Расширение outbox-триггера на PROJECT/EPIC/REQUIREMENT требует записанного решения | ADR-079; старый негативный тест обновлён (регистрация типов агрегатов) |
| A14 | database M4 | Нет изоляционных тестов новых таблиц событий | Покрыто общими проверками `rls_coverage.sql`, `grants_audit.sql` (зелёные), insert-only/contiguity триггерами из 0010-шаблона; прямой tenant-тест для `project_events`/`epic_events` — G-96 |
| A15 | database L5–L9 | `expected_version=1` при создании; тип читается до блокировки; две конвенции 409/412; широкий UPDATE на счётчик; сообщение reserve_resource | Не меняют поведение; зафиксированы как долг (G-96) |
| A16 | silent L6–L8,L10, code L11 | Порядок валидации, нет аудита `organizationId` mismatch, идентичный PATCH поднимает row_version, ETag при replay | Информационно; без влияния на безопасность |

## 3. Тестовые пробелы, названные ревьюерами

Закрыты: сбой завершающей транзакции createProject, COMPLETED записи идемпотентности. Остаются (G-96): сбой аудита для команд кроме createEpic (откат проверен на сбое outbox), сбой Policy Engine для project.create, частично заданная конфигурация загрузок.

## 4. Статус

Независимое review выполнено; CRITICAL/HIGH отсутствуют. Дельта правок R1–R4 отдельным проходом агентов не пересматривалась (тесты 36/36 зелёные).
