# ADR-130 — G-156: отдельный контракт наблюдения Flash до допуска

**Уточнение по делегированию владельца, 2026-11-17:** [ADR131](ADR-131-flash-required-fingerprint.md) закрывает прежний вопрос о выборе состава: fingerprint VALUE обязателен для expectation; новый активный контракт0.2. Ниже сохранён исходный checkpoint0.1. Точные реальные значения и profile/Bifrost approvals ещё не получены; полный G156 NOT VERIFIED. Историческая schema0.1 не переписана.

| Поле | Значение |
|---|---|
| Дата / статус | 2026-11-17 / ACCEPTED Implementation Lead как отключённый технический срез; metadata human acceptance PENDING, full admission NOT VERIFIED |
| Основание | Прямое поручение продолжить подготовку G02; ADR128 уже принял ограниченное исключение, не его реализацию или approval профиля |
| Требования | DOC076 v1.1 §3.1/7, DOC075 §3.3, DOC078 §5.1; G156; AGENTS §7/§11 |
| Проблема | ModelIdentity/ModelProfile и BifrostTransport пока immutable-only. Удаление запрета rolling aliases без нового evidence/admission было бы обходом принятых gates |
| Решение | Начать с отдельного versioned internal observation/expectation contract, строгого validator и exact comparison в чистом llm пакете. Управляемые версии AI RES отделены от provider facts; fingerprint presence/value явно различаются. Код ничего не утверждает, не выполняет I/O и не подключён к product factory/transport |
| Альтернативы | Немедленно переписать profile/transport и включить Flash — отклонено: нет durable admission, live evidence/approval. Process-local sticky flag — не доказывает restart/concurrency. Повтор S16 — не нужен: milestone DONE |
| Контракт / совместимость | Новый WORKING internal overlay `contracts/internal/llm-observed-identity.v0.1.schema.json`, не canonical mirror и не публичный API. Существующие ModelIdentity/LLMGatewayPort/Worker/public/event contracts, baseline и migrations не меняются |
| Полномочия | Expected record — данные сравнения, не human credential/grant. Его создание не approval. Нельзя использовать validator как authorization/admission service или считать успешное сравнение разрешением вызова/публикации |
| Проверки | Реальные parser/normalization/comparison tests: strict version/type/fields, missing/null/value, unsupported provider/Pro/fallback, timestamp/ref bounds, safe errors, no autoapproval. Schema ↔ parser cases; отдельное read-only security/code review |
| Отложено | Forward migration/role map, PostgreSQL sticky block + generation/audit/reapproval/concurrency/restart, budget ledger/candidate probe path, adapter integration, live compatibility и owner acceptance — план G02_FLASH_ADMISSION. G156 остаётся OPEN |
| Риски | Чистый validator может быть ошибочно принят за product admission; исключается явной маркировкой и отсутствием wiring. Provider metadata не доказывает скрытую неизменность. Human-accepted values ещё не определены |
| Порядок | Подготовка G156 → реальный допуск → SLICE01 с отдельным бюджетом → S17; ADR129/G107 до первого S20 producer. Состав группы/roadmap/gates не меняются |
| Пересмотр | Результаты review/provider PoC; несовместимость фактической metadata с предложением; человеческая приёмка точного состава. Расширение exception вне Flash — только новое owner решение |

Подробный scope, paid plan, условия включения и последующая реализация — [план](../groups/G02_FLASH_ADMISSION.md); паспорт — [G02](../groups/G02_WORK.md). Это техническое решение не изменяет canonical и не заменяет предусмотренную DOC076 человеческую приёмку metadata/evidence, Bifrost и профиля.
