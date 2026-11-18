# G156 — сериализация lifecycle профиля и admission

## Основание и scope

Продолжение подготовки по новой команде владельца 2026-11-18, после ADR137.
DOC076 v1.1 §3.1/7, DOC068, DOC072, ADR128/131/132 и
[план подготовки](../../groups/G02_FLASH_ADMISSION.md). G02/S17/S20/S21 не запускаются.

Закрыть конкретную гонку: guard читает lifecycle без согласования с owner UPDATE,
поэтому begin/finalize может использовать уже отозванный статус. Срез — техническая
координация существующего admission, не вся product observed integration.

## Реализация

- Новая forward revision после frozen0024; старые revisions не менять.
- Transaction advisory fence одного profile UUID: guard берёт его до control lock
  и отдельного lifecycle SELECT; BEFORE UPDATE trigger берёт тот же fence при
  изменении lifecycle observed Flash. Никаких UPDATE grants API/SECURITY DEFINER.
- Guard допускает только READ COMMITTED, установленный активный exact trigger и
  origin replication mode; неизвестное состояние — отказ до receipt/result.
- Никаких HTTP/LLM внутри UoW, новых epochs/TTL/autoretry/unblock/approval seeds.
- Сохранить generation/pending/sticky block/audit и неизменяемость pinned пути.

## Проверки и граница evidence

Настоящий disposable PostgreSQL16: RED воспроизведение гонки, затем owner-first и
guard-first begin/finalize, deprecation timestamp, rollback/lock release, unrelated
profile, timeout, неподдерживаемая isolation, missing/disabled trigger, прежние
grants/RLS/pending/replay. Проверять реальные blockers, не только задержку по времени.
Empty/previous upgrade, schema snapshot/drift и migration graph; fast/static и
scoped contract/security checks. Snapshot обновлять только явно и после review DDL.

Обязательны независимые read-only general/Python/database и security reviews,
blind-first до авторского отчёта; замечания исправить. ECC planner/architect,
python-testing/verification-loop — прочитанные инструкции и отдельные задания,
не native Claude commands. Проверяющие не авторы и не владельцы runtime.

Отчёт/ADR/traceability/ECC/handoff сохраняют фактический локальный TESTED checkpoint.
Full G156/pre-pr/Linux CI/live/human/SLICE остаются открытыми до общих gates.
Human owner lifecycle/API, observed gateway/factory/wire и safe key/live setup —
следующие самостоятельные seams; этот срез не создаёт права утверждения модели.
