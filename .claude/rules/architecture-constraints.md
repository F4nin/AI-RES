# architecture-constraints.md — Архитектурные ограничения AI RES

**Нормативные источники:** `AI_RES_Agent_Architecture_Concept_v4.6.md` · `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` §3 · `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` · `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` · `AI_RES_Infrastructure_Deployment_Operations_v1.7.md`

---

## Топология процессов (BASELINED)

```
Reverse Proxy (единственная публичная точка)
  └── API
       ├── Manager Runtime          ← Task Queue: ai-res-manager
       └── Worker Runtime (пул)     ← Task Queue: ai-res-workers
            └── [9 логических специализаций, не 9 контейнеров]

Temporal          ← durable orchestration (temporal_db)
PostgreSQL        ← ai_res_db (domain), temporal_db, LangGraph checkpoint schema
MinIO             ← бинарные объекты (источники, артефакты, результаты)
LLM Gateway       ← единственный путь к LLM (Bifrost — кандидат, pending PoC)
Redis             ← опционально; не источник истины
```

Нельзя добавлять сервисы в топологию без решения владельца проекта.

---

## Non-negotiable constraints

### Backend
- Модульный монолитный Backend в MVP; не микросервисы.
- Одна доменная БД `ai_res_db`; отдельная `temporal_db`; LangGraph checkpoint schema изолирована.
- Нет отдельной БД на каждый домен/bounded context в MVP.
- Нет отдельного vector DB (pgvector в PostgreSQL).
- Нет графовой СУБД (GraphRAG отложен post-MVP).

### LLM доступ
- Все вызовы LLM — только через `LLMGatewayPort` (AI RES adapter).
- Прямые вызовы provider API из LangGraph nodes запрещены.
- **Bifrost (Maxim AI) — кандидат на MVP LLM Gateway, статус: PENDING PoC.** Нельзя считать утверждённой production-зависимостью до прохождения PoC и security review.
- Один одобренный model profile для первого vertical slice.

### Manager/Worker разделение
- Manager Runtime и Worker Runtime — **отдельные процессы**.
- Worker не имеет unrestricted SQL write в domain DB.
- Worker не управляет Docker/Kubernetes.
- Worker не вызывает peer Worker напрямую; только через typed CoordinationRequest → Manager decision → Policy → Temporal.
- Worker local LangGraph decomposition не создаёт доменные Task, не меняет PlanVersion, scope или бюджет.

### Temporal
- Temporal Workflow код **детерминистичен**; все I/O — только в Activities.
- В Temporal History хранятся IDs и компактные refs, не полные документы/промпты/secrets.
- Temporal Workflow ID/Run ID — correlation references, не PK доменных объектов.
- Temporal retry/continue-as-new не создают новую Operation или WorkerRun.
- Temporal Workflow/Activity API не экспонируются как публичные эндпоинты.
- Human decisions передаются через Temporal Signals/Updates после backend authorization.

### LangGraph
- LangGraph thread/checkpoint scope — один WorkerRun; Worker не читает чужой LangGraph state.
- LangGraph Interrupts — для внутренних пауз графа; не заменяют Temporal lifecycle Epic/Task.

### MinIO
- Бинарное содержимое источников и артефактов хранится в MinIO; PostgreSQL хранит метаданные, ACL, checksums и object keys.
- Объекты MinIO immutable при создании; новая версия Source/Artifact создаёт новый объект.
- MinIO Console не экспонируется через публичный API.

---

## Operation (BASELINED — подтверждено владельцем 2026-11-10)

- Canonical state Operation хранится в PostgreSQL `operations` schema.
- Создание Operation + Outbox record — **одна транзакция**.
- API отвечает 202 Accepted + Location. Dispatcher читает Outbox и стартует Temporal идемпотентно.
- Temporal статус не копируется вслепую в Operation status.
- Operation не заменяет Task/Epic/Artifact/WorkerRun и их lifecycle.
- Terminal Operation (SUCCEEDED/PARTIALLY_SUCCEEDED/FAILED/CANCELLED) не переоткрывается.
- Одна Operation на пользовательскую команду; fan-out — через Tasks/WorkerRuns внутри одной Operation.
- Дочерняя Operation — только для реально самостоятельной долгосрочной подкоманды.

**WORKING (требует детализации перед Increment 5/13):**
- Точный `operation_type` enum registry.
- Физическое имя schema (`operations` и `execution` vs альтернативы).
- Dispatch lease duration и стратегия транзакции финальной revalidation.

---

## Readiness Gate (BASELINED — подтверждено владельцем 2026-11-10)

- Обязателен перед **каждым** WorkerRun без исключений.
- Результат — immutable `ReadinessEvaluation` в PostgreSQL `execution` schema.
- WorkerRun не стартует без `started_with_readiness_evaluation_id`.
- Policy Engine недоступен → `BLOCKED` (fail-closed).
- Evaluator error → WorkerRun не стартует (fail-closed).
- LLM semantic assessment не может override детерминированную/security/policy проверку.
- `GateResult` — API projection поверх `ReadinessEvaluation`. **Не создавать две отдельные таблицы** `gate_results` и `readiness_evaluations`.
- Финальная revalidation перед dispatch: при любом изменении версий — новая evaluation, старая не переиспользуется.

**WORKING (требует детализации перед Increment 13):**
- Точный `check_code` registry.
- Dispatch lease duration.

---

## Версионирование доменных объектов (BASELINED)

Иммутабельные снимки: `RequirementVersion`, `SourceVersion`, `PlanVersion`, `ArtifactVersion`, `ContextPackageVersion`.

- Утверждённые и включённые в Baseline версии **не перезаписываются никогда**.
- Изменение содержания создаёт новую версию.
- WorkerRun всегда ссылается на конкретную `ContextPackageVersion`; обновление источника не мутирует уже используемый пакет.

---

## Трассируемость

- `TraceabilityLink` — типизированная таблица; `object_type/link_type` не принимать из пользовательского ввода без валидации по registry допустимых типов.
- Критичные бизнес-связи (Task–Requirement, ArtifactVersion–ValidationReport) — специализированные таблицы с FK.
- Детерминированные impact checks выполняются **до/параллельно** с семантическим анализом.
- Manager/Workers могут расширять оценку влияния, но **не понижать** обязательную детерминированную категорию I0–I4.

---

## Артефакты

- Validation, Review, Approval и Publication — **разные факты** с разными lifecycle; не объединять.
- Baseline — immutable снимок набора конкретных версий; изменение — только через Change Request, Impact Assessment, required approvals и создание новой Baseline.
- WorkerResult не становится автоматически утверждённым артефактом из-за статуса завершения.

---

## Запрещённые паттерны

- Dual-write «сначала Temporal, потом PostgreSQL» без Outbox/reconciliation.
- Доменное состояние живёт только в LLM-чате или Temporal history.
- Два разных источника истины для одного доменного объекта.
- Обход Readiness Gate любым путём.
- Автоматическое утверждение business-решений, Baseline, permission grant.
- Перезапись terminal WorkerResult или Baseline in-place.
- Прямой доступ Manager/Worker Runtime к PostgreSQL через credentials.
