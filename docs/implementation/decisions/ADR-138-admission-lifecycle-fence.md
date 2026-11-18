# ADR-138 — transaction fence lifecycle профиля и admission

**Дата:** 2026-11-18. **Статус:** ACCEPTED техническое решение в порученной подготовке;
реализация и evidence — в отдельном отчёте. Полный G156 NOT VERIFIED.

## Причина

ADR132 прямо оставил lifecycle coordination до product wiring. Control row lock
не защищает обычный SELECT status/deprecated_at от конкурентного owner UPDATE.
FOR SHARE потребовал бы UPDATE privilege API на model_profiles, сейчас SELECT-only.

## Решение

Новая forward0025 после0024: invoker BEFORE UPDATE trigger, только actual lifecycle
изменения FLASH_OBSERVED, берёт `pg_advisory_xact_lock(hashtextextended(
'ai_res.model_profile_lifecycle:' || canonical_profile_uuid, 0))`.
Guard берёт тот же exclusive transaction lock до control FOR UPDATE и читает
lifecycle отдельным statement после ожидания. READ COMMITTED обязателен; другой
isolation, missing/disabled/wrong trigger или replication mode не origin — отказ.

Уже выданная квитанция не удерживает lock во время provider I/O. Finalize заново
берёт fence; если revoke committed первым, результат не принимается. Если guard
первым получил lock, его commit упорядочен до owner transition, который ждёт.
Никаких DB транзакций через сеть/ожидание модели, новых grants или definer functions.
Существующие monotonic status/immutable approval/deprecation и generation fence
сохраняются, отдельный durable epoch для этой гонки не нужен.

Будущий owner service обязан брать advisory первым, затем profile/control. Owner
transaction control→profile/advisory может вызвать deadlock; DB timeout/deadlock
даёт безопасный отказ/rollback, begin без ticket либо finalize с прежним pending.
Автоматический retry/unblock не добавляется. Hash collision даёт только лишнее
ожидание, не принятие чужого профиля. Locks освобождаются commit/rollback.

Триггер не пишет новый audit: он сериализует существующую owner мутацию, не является
human lifecycle command. Guard сохраняет прежний атомарный receipt/security audit.
Аутентифицированный owner lifecycle с собственным audit ещё требуется до включения.

## Границы и совместимость

Нет profile/identity/approval/key seeds, платных вызовов, публичных API/events,
factory/adapter изменений или расширения human/service authority. Frozen0017/0020–24
не редактируются. Pinned путь остаётся прежним. Migration не переписывает данные,
добавляет только function/trigger; downgrade запрещён, исправления forward.

Это transaction ordering, не гарантия отсутствия нового provider I/O после уже
выданного ticket, скрытого drift, физических wall-clock expiry в момент commit или
защита от trusted DBA, отключающего safeguards. Product host/final execution grant
и guard→dispatch window требуют будущей интеграции. Full G156 и human acceptance
не закрываются этим механизмом.

## Источники механизма

Проверены официальные PostgreSQL16: [transaction advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS),
[READ COMMITTED snapshots](https://www.postgresql.org/docs/16/transaction-iso.html#XACT-READ-COMMITTED),
[BEFORE trigger semantics](https://www.postgresql.org/docs/16/trigger-definition.html).
Проектные сведения во внешний поиск не передавались.
