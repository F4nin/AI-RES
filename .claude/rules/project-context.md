# project-context.md — Контекст проекта AI RES

**Нормативные источники:** `AI_RES_Agent_Architecture_Concept_v4.6.md` · `AI_RES_MVP_Capability_Matrix_v3.3.md` · `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md`

---

## Что такое AI RES

AI RES — платформа полного цикла инженерии требований: elicitation → исследование → бизнес-анализ → системный анализ → требования → API/контракты → модели → документация → QA → согласование → Baseline → Change Control.

**Не является:** чат-ботом, набором ассистентов, системой общего назначения.

**Поддерживаемые режимы:** Greenfield и Brownfield. В Brownfield-проектах агент читает существующий код только в read-only; не рефакторит и не изменяет исходный код приложения самостоятельно.

---

## Агентная модель (BASELINED)

Один **Manager** и девять специализированных **Workers** — логические роли в общем Worker Runtime пуле. Не девять микросервисов.

| Worker | Специализация |
|---|---|
| Elicitation Worker | Выявление потребностей, вопросы, интервью |
| Research Worker | Исследование предметной области и источников |
| Business Analysis Worker | Цели, процессы, роли, бизнес-правила |
| Requirements Worker | Формализация, декомпозиция, спецификация (BR/FR/NFR/StR/UR/SyR/IR…) |
| System Analysis Worker | Системное поведение, сценарии, компоненты, NFR |
| API & Integration Worker | API, события, контракты, интеграции |
| Modeling & Diagram Validation Worker | UML/BPMN/ERD/C4, синтаксическая и семантическая проверка |
| Quality Assurance Worker | Независимая проверка качества и полноты |
| Traceability & Change Worker | Трассируемость, Impact Analysis, Change Request |

Manager — координатор и владелец сквозного аналитического результата Epic. Не заменяет Workers и не утверждает требования/Baseline от имени человека.

---

## Границы полномочий

**Manager может:**
- Принимать аналитические решения низкого риска самостоятельно при достаточных доказательствах.
- Формировать рекомендации для решений среднего риска.
- Инициировать Worker-to-Worker взаимодействие через typed CoordinationRequest → Policy → Temporal.

**Manager не может:**
- Утверждать требования, Baseline, бизнес-решения.
- Расширять permissions самостоятельно.
- Вызывать Workers минуя Policy Engine и Temporal.
- Эскалировать business-решения без передачи человеку.

**Worker не может:**
- Писать напрямую в domain DB.
- Self-grant permissions или расширять scope своей задачи.
- Запускать другой Worker напрямую.
- Автоматически становиться источником утверждённых требований.

Результат Worker → WorkerResult (immutable) → Manager orchestration acceptance → отдельно: QA Worker, Approval человека.

---

## MVP scope (BASELINED)

**Включено в MVP:**
- Manager + 9 Workers, один Worker Runtime пул.
- Workflow Engine (Temporal) + LangGraph reasoning.
- Readiness Gate перед каждым WorkerRun.
- PostgreSQL FTS + pgvector; MinIO originals; ACL-before-retrieval.
- Read-only коннекторы: файлы, OpenAPI import, GitHub/GitLab.
- Local Authentication + server-side sessions.
- Transactional Outbox + CloudEvents at-least-once.
- Artifact lifecycle (generate → validate → review → approve → publish).
- Traceability + Impact Assessment.
- Evaluation sets (task-class, deterministic + rubric + adversarial).
- OTel → Prometheus + Loki + Tempo + Grafana.
- Autonomy A0–A2 только.

**Явно за пределами MVP (не реализовывать без решения владельца):**
- Fine-tuning (SFT/DPO/RFT/RLVR).
- GraphRAG / отдельный vector DB.
- Runtime code generation, autonomous tool creation.
- Distributed A2A brokers, agent swarms.
- Autonomy A3/A4.
- OIDC external IdP (interface предусмотрен, adapter — post-MVP).
- Bidirectional sync / write operations к внешним системам.
- Shadow/Canary traffic splitting (только архитектурные предпосылки в MVP).
- PagerDuty, Evidently AI, advanced drift monitoring.
- Пользовательская документация и руководства (после UI acceptance).

Любая реализация функциональности за пределами MVP требует явного решения владельца проекта.
