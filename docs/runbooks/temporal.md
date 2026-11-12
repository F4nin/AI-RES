# Runbook — Temporal, Manager/Worker Runtime и запуск Operation (S11)

Статус: ненормативный; ссылается на Contracts v1.10 §9, Decision v1.6 §2.5. Все значения таймаутов/retry — WORKING (ADR-087): не утверждены.

## Топология
`outbox-dispatcher` (роль `ai_res_outbox_dispatcher`) → Temporal (`ai-res`, очередь `ai-res-manager`) → `manager-runtime` (workflow + Manager Activities) → внутренний `platform-api:8001` (service-токен MANAGER_RUNTIME) → Application Service → PostgreSQL. `worker-runtime` слушает `ai-res-workers`, WorkerRun не исполняет (до S23). Manager/Worker не имеют DB-секретов и сети `data`. Temporal UI — только сеть `admin`.

## Путь одной Operation
1. Accepted-событие Operation с destination `orchestration.operation-start` (в одной транзакции с Operation).
2. Dispatcher стартует workflow `operation-<operationId>` (повтор безопасен: `ENSURED` / `ALREADY_FINISHED`).
3. Первая Activity: ACCEPTED→QUEUED→RUNNING (идемпотентно). 4. Skeleton: терминальный FAILED `ORCHESTRATION_NOT_IMPLEMENTED` (до S21/S23; ADR-089).

## Диагностика
- Состояние процессов: `docker compose ps`; логи — `docker compose logs manager-runtime|worker-runtime|outbox-dispatcher|platform-api` (JSON, с редакцией). Healthcheck'и проверяют лишь достижимость Temporal / HTTP-ответ (G-108).
- Workflow: `docker compose exec temporal temporal workflow describe --address 127.0.0.1:7233 -n ai-res -w operation-<id>`.
- Очередь событий: `python -m ai_res.cli.outbox status` (см. outbox.md). Строка `orchestration.operation-start` в `QUARANTINED`: `SCHEMA_REJECTED`/`ENVELOPE_MISMATCH` — плохая команда старта (чинить производителя), `PUBLISH_FAILED` — Temporal недоступен/неверный namespace.
- Метрика `start_already_finished` / warning «start redelivered for a closed workflow»: если Operation при этом не терминальна — зависший случай, см. ниже.

## Зависшая Operation (G-107 — reconciler ещё нет)
Признак: Operation в ACCEPTED/RUNNING, а workflow завершён (Failed) — Platform API был недоступен дольше `ACTIVITY_BUDGET`. Автоматического восстановления нет; повторная доставка не поможет (REJECT_DUPLICATE). Действие: передать владельцу/оператору; править строки вручную нельзя. Поэтому реальные типы Operation нельзя направлять на маршрут до reconciler'а.

## Версии и replay
Изменение последовательности команд workflow — только за `workflow.patched(<id>)` либо новым major/типом; перед релизом `AI_RES_REGENERATE_HISTORY=1 pytest tests/integration/temporal -k replay` сохраняет историю, записанную ПРЕДЫДУЩИМ кодом, новый код обязан её проиграть.

## Чего нельзя
Открывать Temporal UI/порт 7233 наружу; давать Manager/Worker DB-секреты или сеть `data`; стартовать workflow руками на реальных Operation; править `workflow_id` в БД.
