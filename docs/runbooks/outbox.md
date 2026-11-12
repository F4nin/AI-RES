# Runbook — Outbox, Inbox и доставка событий (S10)

Статус: ненормативный, ссылается на Event Model v1.4 §9, §15, §16. Значения lease/backoff/порогов — WORKING (ADR-085): не утверждены.

## Что гарантируется
At-least-once, порядок только внутри (aggregate, destination). Exactly-once не обещается: дубликаты гасит Inbox consumer'а `(consumer_name, event_id)`.

## Состояния строки `audit.outbox_events`
`PENDING` → `IN_FLIGHT` (lease) → `PUBLISHED`; ошибка: `PENDING` с `available_at` (backoff) или `QUARANTINED`. Строки не удаляются автоматически (ADR-030).

## Диагностика
`python -m ai_res.cli.outbox status` (под identity `ai_res_outbox_dispatcher`) — счётчики, возраст старейшей недоставленной строки, коды алертов. Без id и содержимого.

| Алерт | Значение | Действие |
|---|---|---|
| `OUTBOX_BACKLOG_HIGH` / `OUTBOX_OLDEST_AGE_HIGH` | dispatcher не успевает или не запущен | проверить процесс и ошибки publisher'а; новые события не теряются |
| `OUTBOX_QUARANTINED` | есть события, требующие человека | см. ниже |
| `OUTBOX_ROWS_HIGH` / `INBOX_ROWS_HIGH` | рост таблиц (удаления нет) | решение о retention — OD-02 (владелец) |
| `INBOX_STUCK_AGE_HIGH` | зависшая обработка consumer'а | искать упавший handler |
| метрика `unknown_major_event` | тип/major события неизвестен контракту | не «чинить» повтором: обновить контракт/consumer, затем replay |

## Карантин и controlled replay
Причина — `last_error_code` (машинный код): `SCHEMA_REJECTED`, `FORBIDDEN_CONTENT`, `UNKNOWN_EVENT_TYPE`, `UNKNOWN_MAJOR_VERSION`, `NO_CONSUMER`, `PUBLISH_FAILED` (исчерпан бюджет попыток), `LEASE_EXPIRED_MAX_ATTEMPTS`.
1. Устранить причину (контракт, consumer, publisher).
2. `python -m ai_res.cli.outbox replay --event-id <uuid> [--event-id …] --confirm` — только именованные события, replay-all нет. Строка возвращается в `PENDING` со свежим бюджетом, `replay_count + 1`; порядок внутри агрегата сохраняется (последующие события ждут).
3. Кто вправе подтверждать replay — WORKING (Event Model §18); пока решение оператора с доступом к роли dispatcher. Аудит replay в `audit.audit_events` не пишется (G-100).

## Sequence gap у consumer'а
`SEQUENCE_GAP` — transient: событие откладывается и повторяется, не применяется вне порядка и не пропускается. Затянувшийся gap = алерт `sequence_gap`; искать непросмотренные/карантинные события того же агрегата. Consumer на фильтрованном потоке объявляется `Ordering.MONOTONIC`.

## Потеря lease
Метрика `lease_lost`: результат не применён, доставка могла продублироваться — это норма при at-least-once.

## Чего нельзя
Править строки outbox/inbox вручную; удалять строки; запускать dispatcher без зарегистрированных consumer'ов (событие без получателя уйдёт в карантин `NO_CONSUMER`).
