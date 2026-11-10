# Архитектурный анализ AI RES — Первичный

**Версия:** 1.0  
**Дата анализа:** 2026-11-10  
**Составлен:** Claude Code (claude-sonnet-4-6) на основе нормативных документов проекта  
**Нормативная основа:** Registry v4.1 · Implementation Spec v1.22 · Architecture Concept v4.6  
**Статус источников:** 83 записи в реестре; 74 уникальных canonical файла; ни один не верифицирован в runtime.  
**Назначение:** первичный архитектурный анализ для ориентации команды реализации. Не является нормативным документом. Не изменяет и не заменяет ни один документ из Document Registry.

---

## 1. Назначение продукта и границы

### BASELINED

AI RES — **единая платформа полного цикла инженерии требований**. Не чат-бот и не набор ассистентов.

Три утверждённые цели:
1. Повышение производительности аналитиков.
2. Повышение полноты, непротиворечивости, тестируемости и доказательной обоснованности требований.
3. Максимальная автоматизация цикла от выявления потребностей до Baseline и Change Control.

**Охватываемые процессы:** первичное обращение / бизнес-проблема → работа с заказчиками/стейкхолдерами → elicitation → исследование → бизнес- и системный анализ → требования → API/данные/интеграции → модели → документация → QA → согласование → Baseline → Change Control.

**Поддерживаемые режимы:** Greenfield и Brownfield. Для Brownfield чтение существующего кода и систем **по умолчанию read-only**; агент не должен самостоятельно менять исходный код приложения.

### Граница ответственности (явно зафиксировано)

Система **не выполняет** без участия человека:
- утверждение требований, Baseline и бизнес-решений;
- escalation approval;
- выдачу или расширение permissions.

---

## 2. Пользовательские сценарии

### BASELINED

**Роли пользователей (UX Concept v1.2):**
- **Analyst** — основной работающий пользователь: создаёт проекты, Epics, ведёт диалог с Manager, рассматривает результаты, утверждает требования.
- **Stakeholder / Reviewer** — проверяет артефакты, утверждает решения.
- **Organization/Project Admin** — управляет членством, ролями, настройками; обязательна MFA.

**Ключевые сценарии:**
1. Аналитик создаёт проект и Epic, формулирует цель, scope и критерии.
2. Manager ведёт диалог с аналитиком: задаёт адаптивные уточняющие вопросы (Elicitation Worker).
3. Manager формирует план и граф задач; аналитик может подтвердить или скорректировать.
4. Запуск Workers: каждый Worker Run проходит обязательный Readiness Gate.
5. Аналитик наблюдает прогресс через статусы Operation (SSE или REST polling).
6. Аналитик рассматривает структурированные результаты Workers: выводы, источники, ограничения, неопределённость.
7. Независимая QA-проверка критичных результатов (отдельный WorkerRun).
8. Аналитик принимает или отклоняет артефакты; Baseline только через явное утверждение.
9. Change Control: анализ влияния → ChangeSet → Impact Assessment → новая версия.

**Режимы взаимодействия:**
- **Синхронный** — диалог в активной сессии.
- **Асинхронный** — долгосрочное выполнение; статус через Operation resource.

### WORKING

- Точные UX-каналы первого релиза (только web?).
- Правила частоты и режима инициативы Manager.
- Представление уверенности и неопределённости в UI.

---

## 3. Функциональные домены

### BASELINED — PostgreSQL schemas `ai_res_db`

| Schema | Ответственность |
|---|---|
| `iam` | Пользователи, членство, назначения ролей |
| `organization` | Организационная область |
| `project` | Проекты, участники, настройки |
| `work` | Epic, Task, Plan/PlanVersion, PlanItem |
| `requirements` | Requirement, RequirementVersion |
| `sources` | Source, SourceVersion, SourceFragment |
| `knowledge` | ExtractionRecord, SourceAssertion, DerivedFinding |
| `decisions` | Decision, Assumption, Risk, Issue, Unknown, Hypothesis, Conflict |
| `artifacts` | Artifact, ArtifactVersion, GenerationJob, ValidationReport |
| `traceability` | TraceabilityLink, ChangeSet, ImpactAssessment, ImpactItem |
| `governance` | Review, Approval, Baseline, ChangeRequest |
| `agents` | WorkerDefinition, WorkerRun, WorkerResult |
| `context` | ContextPackage, ContextPackageVersion, ContextPackageItem |
| `operations` | Operation, OperationEvent, OperationIdempotency |
| `execution` | ReadinessEvaluation, ReadinessCheckResults |
| `integrations` | Connector, ExternalConnection, SyncRun |
| `audit` | AuditEvent, OutboxEvent |

---

## 4. Backend Architecture

### BASELINED

**Принятые решения:**
- **Модульный монолитный Backend** — не микросервисы в MVP.
- Единая доменная БД `ai_res_db` PostgreSQL, логически разделённая схемами.
- Отдельная `temporal_db` для Temporal persistence.
- Отдельная PostgreSQL schema для LangGraph checkpoints (изолирована от доменных таблиц).
- **MinIO** для бинарного хранения файлов (sources, artifacts, worker results, exports, temporary).
- **Redis** опционален, подключается через отдельный Compose profile; не является источником истины.
- **Reverse Proxy** — единственная публичная точка входа.
- API не должен блокироваться на длительных агентных задачах: все долгосрочные операции → 202 Accepted + Operation resource.
- Все публичные эндпоинты: `/api/v1`, JSON camelCase, UUID идентификаторы, UTC RFC3339.

**Запрещено:**
- Отдельная БД на каждый домен в MVP.
- Графовая СУБД (GraphRAG отложен).
- Отдельный vector DB (pgvector в PostgreSQL).
- Прямой доступ Workers к PostgreSQL.
- Прямые вызовы Docker/Kubernetes API из Manager.

### WORKING

- Финальный выбор Python-фреймворка, ORM версии, HTTP-библиотеки.
- Точные настройки connection pool, таймауты, backpressure параметры.

---

## 5. Manager Runtime

### BASELINED

Manager — **центральный координатор**, владелец сквозного аналитического результата Epic. Модель Б: **ответственность за результат без полномочий самостоятельно утверждать бизнес-решения**.

**Функции Manager:**
- Понимает цель Epic, определяет направления анализа.
- Формирует и декомпозирует Tasks, строит граф зависимостей.
- Выбирает Workers, определяет последовательное/параллельное исполнение.
- Выполняет **обязательный Readiness Gate** перед каждым WorkerRun.
- Координирует Worker-to-Worker взаимодействие (через typed CoordinationRequest → Policy → Temporal).
- Контролирует выполнение, проверяет результаты, назначает независимую QA.
- Разрешает конфликты по уровню риска (низкий — самостоятельно, средний — рекомендация, высокий — эскалация человеку).
- Формирует Manager Epic State как **проекцию доменных событий** (не независимый источник истины).

**Task Queue:** `ai-res-manager`

**Граница Manager:**
- Не выполняет специализированный анализ вместо Workers.
- Не утверждает требования и Baseline.
- Не обходит политики доступа.
- Не вызывает Workers напрямую минуя Policy Engine и Temporal.

---

## 6. Worker Runtime и девять специализированных Workers

### BASELINED — Архитектура

Один общий пул Worker Runtime. Девять специализаций — **логические роли**, не обязательные девять микросервисов/контейнеров. Task Queue: `ai-res-workers`.

| # | Worker | Ответственность | Типичные результаты |
|---|---|---|---|
| 1 | **Elicitation Worker** | Выявление потребностей, вопросы, интервью | Карта пробелов, план интервью, структурированные ответы |
| 2 | **Research Worker** | Исследование предметной области, источников, систем | Исследовательский отчёт, реестр источников, факты с цитатами |
| 3 | **Business Analysis Worker** | Цели, процессы, роли, бизнес-правила | Модель целей, описание процессов, бизнес-правила |
| 4 | **Requirements Worker** | Формализация, декомпозиция, спецификация требований | Реестр требований (BR/StR/UR/FR/NFR/SyR/IR…), SRS |
| 5 | **System Analysis Worker** | Системное поведение, сценарии, компоненты, NFR | Системные сценарии, модели состояний, системные требования |
| 6 | **API & Integration Worker** | API, события, контракты, интеграции | OpenAPI/Swagger, каталог событий, интеграционные контракты |
| 7 | **Modeling & Diagram Validation Worker** | Создание и проверка моделей/диаграмм | UML/BPMN/ERD/C4, результаты синтаксической и семантической проверки |
| 8 | **Quality Assurance Worker** | Независимая проверка качества и полноты | QA-отчёт, дефекты с доказательствами, рекомендации по доработке |
| 9 | **Traceability & Change Worker** | Трассируемость, анализ влияния, изменения | Матрица трассируемости, impact analysis, данные для Change Request |

**Общие правила для всех Workers:**
- Работают только в пределах выданных полномочий и специализации.
- Явно разделяют: подтверждённые факты / выводы / гипотезы / допущения.
- Не пишут напрямую в domain DB.
- Не расширяют собственные grants.
- Не утверждают требования или Baseline.
- Не запускают peer Workers напрямую.
- Результат Worker → WorkerResult → Manager acceptance → отдельно: QA, Approval.

**Формы Worker-to-Worker взаимодействия (через Manager/Temporal):**
- **Consultation** — ограниченный запрос сведений; исходный Worker остаётся владельцем задачи.
- **Delegated subtask** — отдельная ограниченная подзадача через Manager decision.
- **Handoff** — контролируемая передача части работы; Manager явно определяет границы.
- **Independent QA** — отдельный WorkerRun QA Worker по решению Manager или обязательному правилу.

### WORKING

- Точные поля специализированных WorkerRunEnvelope/WorkerResult контрактов (DOC-007 статус `WORKING`).
- Механизм горизонтального масштабирования пула Workers.

---

## 7. Взаимодействие LangGraph и Temporal

### BASELINED

**Принципиальное разделение:**

| Компонент | Ответственность |
|---|---|
| **Temporal** | Durable workflow orchestration: длительные процессы, ожидание человека, таймеры, bounded retries, cancellation, checkpoint/resume, replay. |
| **LangGraph** | Internal agent reasoning: граф рассуждений, internal decomposition внутри одного WorkerRun. Scoped to single WorkerRun. |

**Правила интеграции:**
- Workflow-код Temporal **детерминистичен** (нет случайных вызовов, I/O, side effects напрямую).
- Все внешние вызовы — только через **Activities** (LLM, БД, HTTP, MinIO, Tools).
- Human decisions — через Temporal Signals/Updates после backend authorization.
- LangGraph Interrupts — для внутренних пауз графа; не заменяют Temporal lifecycle.
- В Temporal History хранятся только **IDs, компактные parameters и references** — не полные документы, промпты, source content.
- LangGraph thread/checkpoint scope — **один WorkerRun**; Worker не может читать чужой LangGraph state.
- Temporal Workflow ID/Run ID — **correlation references**, не PK доменных объектов.
- Temporal retry/continue-as-new не создают новую Operation или WorkerRun.
- Доменное состояние **не живёт только в Temporal history**: PostgreSQL — canonical source of truth.

**Task Queues:**
- `ai-res-manager` — Manager tasks.
- `ai-res-workers` — Worker tasks.

### WORKING / требует проверки PoC

- Bifrost + LangGraph/LangChain совместимость (streaming, structured output, tool calling, retries).
- Temporal Web UI — только internal admin, не публикуется.

### Открытые вопросы

- Конкретная версия Temporal и настройка namespace.
- Топология внутренних Temporal процессов в Docker Compose.
- LangGraph Checkpointer schema isolation (отдельная schema PostgreSQL).

---

## 8. Модель данных и основные доменные сущности

### BASELINED — ключевые сущности и инварианты

**Иерархия владения:**
```
Organization → Project → Epic → Task → WorkerRun → WorkerResult
                               ↓             ↓
                          PlanVersion   ContextPackageVersion (immutable)
                               ↓
                           PlanItem → Task
```

**Версионирование** — фундаментальный инвариант:
- `RequirementVersion`, `SourceVersion`, `PlanVersion`, `ArtifactVersion`, `ContextPackageVersion` — **immutable снимки**; утверждённые версии не перезаписываются никогда.
- Изменение содержания создаёт новую версию.

**Ключевые принципы хранения:**
- PostgreSQL: метаданные, версии, связи, ACL, embeddings (pgvector), FTS (tsvector/GIN).
- MinIO: бинарное содержимое источников и артефактов; объекты immutable.
- PK — UUIDv7 (рекомендован), UUIDv4 допустим.
- Человекочитаемые номера (`REQ-000123`) — display IDs, не PK.
- Время — `timestamptz` UTC.
- Статусы и типы — controlled enum/registry, не произвольные строки из LLM.

**Трассируемость:**
- `TraceabilityLink` — типизированная таблица с полиморфными ссылками. Критичные связи (Task–Requirement, ArtifactVersion–ValidationReport) — специализированные таблицы с FK.
- Нельзя принимать произвольные `object_type/link_type` из пользовательского ввода.

**Аудит и события:**
- `AuditEvent` — субъект, действие, объект, результат, время, scope, correlation IDs. Нельзя изменять/удалять.
- Transactional Outbox — projection update + aggregate event + Outbox record в **одной транзакции**.

---

## 9. Operation и Readiness Gate

### BASELINED — подтверждено владельцем проекта 2026-11-10 (DOC-055 v1.6)

**Operation:**
- Доменная сущность — представляет длительное действие с независимым lifecycle.
- Canonical state в PostgreSQL `operations` schema; Temporal — correlation reference, не источник истины.
- Статусы операции:
  - `ACCEPTED` — команда прошла синтаксическую/авторизационную проверку и Operation записана.
  - `QUEUED` — команда надёжно поставлена на запуск.
  - `RUNNING` — подтверждено начало исполняемого workflow этапа.
  - `WAITING_FOR_HUMAN` — требуется конкретное человеческое решение.
  - `WAITING_FOR_DEPENDENCY` — ожидается внешняя или внутренняя зависимость.
  - `RETRYING` — система выполняет разрешённую повторную попытку.
  - `CANCEL_REQUESTED` — запрос отмены принят, отмена ещё не подтверждена.
  - `SUCCEEDED` — целевой результат достигнут.
  - `PARTIALLY_SUCCEEDED` — достигнут частичный результат, остаток явно описан.
  - `FAILED` — операция завершилась неуспешно.
  - `CANCELLED` — подтверждённая отмена после cleanup/reconciliation.
- Terminal статусы: `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `CANCELLED`. Не могут быть вновь открыты.
- Создание Operation + Outbox в **одной транзакции**; API отвечает 202 + Location.
- Идемпотентное принятие: тот же fingerprint → та же Operation; тот же key + другой fingerprint → `IDEMPOTENCY_KEY_REUSED` (409).

**Readiness Gate:**
- Обязателен перед **каждым** WorkerRun.
- Результат сохраняется как **immutable `ReadinessEvaluation`** в PostgreSQL.
- WorkerRun не стартует без `started_with_readiness_evaluation_id`.
- Outcomes: `READY`, `READY_WITH_LIMITATIONS`, `BLOCKED`, `STALE`.
- `EVALUATOR_ERROR` → WorkerRun не стартует (fail-closed).
- Policy Engine недоступен → `BLOCKED` (fail-closed).
- LLM не может override детерминированную/security/policy проверку.

**11 групп обязательных проверок:**
1. Task/goal — существование, активность, scope.
2. Plan — PlanVersion, PlanItem разрешён, predecessor dependencies.
3. Worker capability — WorkerDefinition активна, contract version совместима.
4. Context — ContextPackageVersion существует, immutable, refs разрешены ACL.
5. Governance/rules — system/org/project rules, нет конфликта.
6. Permissions — grant активен, scope соответствует, срок не истёк.
7. Output contract — схема результата зарегистрирована.
8. Budget — time/token/cost/tool/concurrency не превышают policy limits.
9. Dependencies — predecessor/approval/review/source readiness.
10. Semantic readiness — Manager assessment (если required по классу задачи).
11. Runtime capability — модель/провайдер и инструменты доступны.

**TOCTOU и финальная revalidation:**
- Перед dispatch — короткая финальная revalidation; при любом изменении версий → новая evaluation.
- Старый GateResult не используется.

**Явное уточнение (требует согласования):**
- `GateResult` — API/domain projection поверх `ReadinessEvaluation`, не отдельная конкурирующая таблица. В текущих событиях используется `gateResultId`; при следующей breaking-safe версии переименовать в `readinessEvaluationId`.

### WORKING (не реализовано, подлежит детализации)

- Точный `operation_type` enum registry.
- Точный `check_code` registry.
- Физическое имя schema (`operations` + `execution` vs `agents/governance`).
- Срок retention (до утверждения юридических правил — не удалять автоматически).
- Dispatch lease duration и стратегия транзакции финальной revalidation.

---

## 10. Source & Context Lifecycle

### BASELINED

**15 базовых принципов (ключевые):**
1. Оригинал источника сохраняется неизменяемо.
2. Обновление → новая версия, не перезапись.
3. Извлечённое утверждение, кандидат требования и утверждённое требование — **разные сущности**.
4. Контекст WorkerRun **фиксирован и не меняется** во время выполнения.
5. Изменение источника → Impact Assessment, но **не автоматическое изменение** утверждённых объектов.
6. Детерминированные правила имеют приоритет над семантической оценкой.
7. Policy & Permission Engine независимо проверяет права.
8. QA-переоценка обязательна для критических изменений.
9. Невозможность доказать влияние не означает отсутствие влияния: неопределённость фиксируется.

**Категории источников:** документы/файлы (PDF/DOCX/MD/TXT/XLSX/CSV), OpenAPI/Swagger, репозитории (GitHub/GitLab read-only в MVP), базы данных (post-MVP).

**Ключевое разделение:**
- `SourceAssertion` — то, что утверждает сам источник.
- `DerivedFinding` — вывод/интерпретация AI RES с привязкой к доказательствам.
- Нельзя смешивать assertion с выводом агента.

**ContextPackageVersion** — immutable; содержит точные версии источников, требований, решений, артефактов, правил, разрешений. WorkerRun всегда ссылается на конкретную версию.

**Ingestion pipeline:**
Receive → валидация (malware/type) → immutable object storage → parse/OCR → normalize → fragment с locators → classify/sanitize → ACL/provenance → lexical/vector index → extraction → validation → публикация index completion.

**Retrieval pipeline:**
Query understanding → authorization scope → lexical + dense retrieval → **ACL filter до ranking** → deduplicate/merge → rerank authorized → freshness/authority weighting → evidence pack → Context Builder.

### WORKING

- Форматы/лимиты OCR, диаграммы.
- Точные пороги SLO sync, retention.
- Коннекторы к конкретным провайдерам (кроме GitHub/GitLab MVP).

---

## 11. Artifact Lifecycle

### BASELINED (инварианты из DOC-005 BASELINED; DOC-013 — WORKING)

**Инварианты:**
- `Artifact` — стабильная идентичность; `ArtifactVersion` — immutable снимок содержимого.
- `ArtifactRepresentation` связывает конкретную ArtifactVersion с форматом/рендерером.
- DOCX/PDF-экспорт — обычно представление, не канонический контент.
- OpenAPI/JSON Schema/диаграмма-as-code могут быть нативным source of truth.
- Validation, Review, Approval и Publication — **разные факты** с разными lifecycle.
- `Baseline` — immutable снимок набора конкретных версий; изменение — только через Change Request.

**Статусы артефактов:** DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → PUBLISHED → SUPERSEDED.

**GenerationJob** фиксирует попытку генерации/обновления/импорта.

---

## 12. Traceability и Change Impact

### BASELINED (инварианты из DOC-005; DOC-012 — WORKING)

**TraceabilityLink** — типизированная таблица с полями: source/target object type+id, link_type, status (PROPOSED/CONFIRMED/REJECTED/SUPERSEDED), origin (HUMAN/AGENT/IMPORT/RULE), evidence_refs, rationale.

**Типы зависимостей моделируются отдельно:**
- TaskDependency, RequirementDependency, ArtifactDependency, RuntimeDependency, Provenance/TraceabilityLink.

**Impact Analysis:**
- `ChangeSet` → `ImpactAssessment` → `ImpactItem[]` (затронутый объект, путь, категория I0–I4, evidence, статус, рекомендуемое действие).
- Классы I0–I4 — рекомендация AI RES, не confidence score.
- Детерминированные проверки выполняются **до/параллельно** с семантическим анализом.
- Manager/Workers могут расширять оценку, но **не понижать** обязательную детерминированную категорию.

---

## 13. Authentication, Authorization и Security

### BASELINED

**Аутентификация (DOC-023):**
- MVP: локальные учётные записи + `IdentityProvider` interface для будущего OIDC.
- Пароли: Argon2id с уникальной солью; минимум 15 символов.
- Первый admin: одноразовая bootstrap-процедура; default credentials запрещены.
- Browser sessions: opaque server-side session ID в cookie (`HttpOnly`, `Secure`, `SameSite=Lax`).
- Cookie name: `ai_res_session` (проектное предложение; требует security owner approval).
- CSRF protection для state-changing запросов (Header: `X-CSRF-Token`, проектное предложение).
- Idle timeout: 30 мин, absolute: 12 ч (configureable defaults).
- MFA обязательна для привилегированных ролей (TOTP для MVP).

**Авторизация:**
- Policy & Permission Engine — независимый уровень.
- Server-side ACL: каждый запрос проверяет organization/project/object scope.
- Аутентификация ≠ авторизация; UI visibility ≠ authorization.
- Policy Engine недоступен → fail-closed для критических операций.
- RLS в PostgreSQL — defense-in-depth, **не замена** Policy Engine.

**Сервисные идентичности:**
- API, Manager Runtime, Worker Runtime, Temporal Activities, Connector, LLM Gateway — **отдельные service identities**.
- Браузерные сессии не передаются Manager/Worker Runtime.
- Worker Run grant выдаётся отдельно и ограничен project/task/run/tools/model/budget.

**Security controls P0 — release blockers:**
- Opaque sessions + CSRF.
- Argon2id.
- Least-privilege PostgreSQL roles.
- RLS defense-in-depth.
- Secrets isolation.
- No direct DB credentials в Manager/Worker Runtime.

### WORKING / требует согласования

- Точные wire names (`ai_res_session`, `X-CSRF-Token`) — проектные предложения до security owner approval.
- Production-like activation остальных security controls (кроме уже выбранного Local Auth MVP).

---

## 14. Observability и Evaluation

### BASELINED — Design (DOC-024 v1.2, DOC-026 v1.2)

**Observability Stack MVP:**
- OpenTelemetry SDK → OTel Collector → Prometheus + Grafana Loki + Grafana Tempo → Grafana.
- Domain/Security Audit Log → PostgreSQL (отдельно от OTel pipeline).
- Langfuse — optional profile; content capture выключен по умолчанию.
- Alertmanager / Grafana Alerting.

**Правила:**
- Fail-open для telemetry; fail-closed для Audit Log.
- По умолчанию: **не собирать** secrets, full prompts, source fragments, documents.
- Высококардинальные IDs — в logs/traces, не в Prometheus labels.
- Коррелировать по: request_id, organization_id, project_id, epic_id, plan_version_id, task_id, worker_run_id, temporal_workflow_id, context_package_version_id, model_name, tool_name, ruleset_version, release_id.

**Span taxonomy:** `ai_res.request`, `ai_res.manager.plan`, `ai_res.readiness_gate`, `ai_res.temporal.workflow`, `ai_res.worker.run`, `ai_res.langgraph.node`, `ai_res.context.build`, `ai_res.retrieval`, `ai_res.llm.call`, `ai_res.tool.call`, `ai_res.artifact.generate`, `ai_res.validation`, `ai_res.review`, `ai_res.approval`, `ai_res.feedback.capture`, `ai_res.recovery.action`.

**MVP Dashboards:**
1. Platform Overview — health, availability, errors, saturation, disk.
2. Temporal & Workflow — backlog, schedule-to-start, retries, stuck workflows.
3. Manager & Workers — run duration/outcomes, blockers, readiness, QA.
4. LLM & Tools — latency, tokens, cost estimate, errors, fallback, tool success.
5. Product Quality — completion, verification distribution, rework, approvals, feedback.
6. Telemetry Pipeline — Collector export errors/dropped signals/backend health.

**Evaluation Framework (DOC-078 BASELINED):**
- Task-class based evaluation sets.
- Deterministic tests + human-calibrated rubric + adversarial/security tests.
- LLM judge не может быть единственным release gate.

**Agent Observability (DOC-026 BASELINED):**
- Метрики качества раздельны: execution outcome / orchestration acceptance / verification / independent QA / human approval.
- Feedback и telemetry не запускают автоматическое обучение или изменение поведения.

### WORKING

- Числовые SLO, пороги retention, sizing alerting.
- Задания task-class evaluation sets и пороги.
- Эмпирическая калибровка quality thresholds.
- On-call routing, PagerDuty (post-MVP).

---

## 15. Инфраструктура MVP

### BASELINED — Docker Compose

**Состав сервисов:**

| Сервис | Статус в MVP |
|---|---|
| `frontend` | MVP |
| `api` | MVP |
| `manager-runtime` | MVP |
| `worker-runtime` (общий пул) | MVP |
| `temporal` + внутренние процессы | MVP |
| `postgres` (содержит `ai_res_db` + `temporal_db`) | MVP |
| `minio` | MVP |
| `reverse-proxy` | MVP |
| `redis` | Optional profile |
| OTel Collector + Prometheus + Grafana + Loki + Tempo | MVP |
| `langfuse` | Optional profile |

**Сетевые сегменты (логические):**
- Ingress: Reverse Proxy + Frontend + API.
- Application: API + Manager + Worker + internal modules.
- Data: PostgreSQL + Temporal + MinIO + Redis.
- Controlled Egress: LLM Gateway + Connector Platform.

**LLM Gateway:**
- Собственный не разрабатывается.
- **Bifrost (Maxim AI)** — основной кандидат. Статус: **candidate, pending PoC**.
- Обязательна проверка: Docker Compose PoC, внешняя + локальная модель, совместимость с LangGraph, streaming/structured output/tool calling, secrets management, security audit.
- LLM access только через `LLMGatewayPort` interface (AI RES adapter).

**Persistence — стек:**
- Alembic + SQLAlchemy 2.x (BASELINED, DOC-072).
- Одноразовый migration job, отдельный от API startup.
- Роли: `ai_res_owner` (NOLOGIN), отдельный migrator, least-privilege runtime principals.
- RLS: ENABLE + FORCE на tenant tables.

**Backup:**
- pgBackRest + WAL Archiving.
- RPO ≤ 1 час, RTO ≤ 4 часа (цели, не гарантии до recovery drills).

---

## 16. Границы MVP и отложенная функциональность

### BASELINED — MVP включает

- Manager + 9 Workers (логические роли, один пул).
- Workflow Engine (Temporal) + LangGraph reasoning.
- Readiness Gate перед каждым WorkerRun.
- PostgreSQL FTS + pgvector; MinIO originals; ACL-before-retrieval.
- Read-only коннекторы: файлы, OpenAPI import, GitHub/GitLab.
- Local Authentication + server-side sessions.
- Transactional Outbox + CloudEvents.
- Artifact lifecycle (generate, validate, review, approve, publish).
- Traceability + Impact Assessment.
- Evaluation sets (task-class, deterministic + rubric + adversarial).
- OTel → Prometheus + Loki + Tempo + Grafana.
- Autonomy scale A0–A2 только (накопление опыта без изменения весов).

### После MVP (явно отложено)

| Возможность | Причина отложить |
|---|---|
| Fine-tuning (SFT/DPO/RFT/RLVR) | Требует качественных данных, стабильной оценки и доказательства необходимости |
| GraphRAG | Нужен benchmark для подтверждения ценности на реальных запросах |
| Runtime code generation, autonomous tool creation | Риски безопасности MVP |
| Distributed multi-agent infrastructure, A2A brokers | Не требуется для логических ролей в одном процессе |
| Agent swarms, democratic coordination | Противоречит выбранной Manager-based модели |
| Full multimodality (audio/video) | Только при подтверждённых сценариях |
| Automatic model weight update from production feedback | Запрещено без контролируемого контура |
| Shadow/Canary deployments | Архитектурные предпосылки в MVP; полное применение — при production нагрузке |
| Autonomy A3/A4 | Не активировать без отдельной утверждённой autonomy matrix и test evidence |
| OIDC external IdP | Pluggable interface готов; adapter — post-MVP |
| Bidirectional sync, write operations to external systems | Только read-only в MVP |
| PagerDuty, Evidently AI, advanced drift | После накопления production данных |
| User documentation, analyst guides | После UI acceptance (post-MVP, DOC-029) |

---

## Обнаруженные противоречия и несоответствия

### Противоречие 1 — версии документов в Implementation Spec

**Описание:** Секция 2 Implementation Spec v1.22 содержит ссылки на устаревшие версии:
- Requirements Lifecycle `v2.6` → актуальная `v2.7` (Registry DOC-003).
- Source & Context `v1.2` → актуальная `v1.3` (Registry DOC-010).
- External Integrations `v1.1` → актуальная `v1.2` (Registry DOC-014).
- Decisions/Assumptions `v1.1` → актуальная `v1.2` (Registry DOC-051).
- Continuous Improvement Architecture `v1.2` → актуальная `v1.3` (DOC-038).

**Резолюция:** Addendum v1.22 прямо указывает: «Registry v4.1 имеет приоритет над всеми versioned references в исторических разделах». Формальное противоречие снято, но секция 2 требует синхронизации при выпуске Implementation Spec v1.23.

**Ссылки:** `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` §2 vs Addendum v1.22 vs `AI_RES_Document_Registry_v4.1.md` §2.

### Противоречие 2 — именование `gateResultId` vs `readinessEvaluationId`

**Описание:** В текущих event schemas используется `gateResultId`; Architecture Decision v1.6 §3.2 прямо указывает, что стабильное имя хранения — `ReadinessEvaluation`, а `gateResultId` следует переименовать в `readinessEvaluationId` в следующей breaking-safe версии event schema.

**Статус:** известное, зафиксированное расхождение; не является ошибкой — это запланированное breaking-safe migration. Не создавать две таблицы `gate_results` и `readiness_evaluations`.

**Ссылки:** `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` §3.2 vs `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml`.

### Противоречие 3 — Worker Contracts (DOC-007) статус WORKING

**Описание:** `AI_RES_Worker_Contracts_v1.1.schema.json` имеет статус **WORKING**, тогда как implementation spec в Increment 6 требует реализовать typed WorkerRunEnvelope, WorkerResult и WorkerNotice. Контракт Worker — фундаментальный для многих инкрементов.

**Риск:** при реализации Increment 6 нет финализированного контракта.

**Рекомендация:** перевести DOC-007 в BASELINED до начала Increment 6, после финализации полей в рамках Increment 1–5.

**Ссылки:** `AI_RES_Document_Registry_v4.1.md` DOC-007 vs `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` Increment 6.

### Противоречие 4 — Self-referential audit

**Описание:** `AI_RES_Cross_Document_Consistency_Audit_v2.2.md` §4 ссылается на Implementation Spec v1.22 как на документ, обновлённый в ходе этого же аудита. Это self-referential, но логически корректно — не противоречие, а potential confusion point для читателя при разборе хронологии изменений.

---

## Открытые вопросы

| # | Вопрос | Область | Критичность |
|---|---|---|---|
| OQ-1 | Провайдер/модель LLM для первого vertical slice (Bifrost PoC не пройден) | LLM Gateway | Блокирует Increment 20 |
| OQ-2 | Физическое имя PostgreSQL schemas для `operations` и `execution` | Persistence | Блокирует миграции |
| OQ-3 | Exact `operation_type` enum registry | API/Domain | Блокирует Increment 5 |
| OQ-4 | Exact `check_code` registry для Readiness Gate | Gate | Блокирует Increment 13 |
| OQ-5 | Числовые SLO, пороги retention, observability sizing | Observability | Deployment gate |
| OQ-6 | Dispatch lease duration и стратегия транзакции финальной revalidation | Gate/Concurrency | Блокирует Increment 13 |
| OQ-7 | HMAC key rotation policy для idempotency keys | Persistence | Implementation ADR |
| OQ-8 | Юридические/организационные правила retention для Operation/WorkerRun events | Legal/Compliance | До production |
| OQ-9 | Python-фреймворк и HTTP-библиотека для Backend | Stack | Increment 0 |
| OQ-10 | Правила частоты инициативы Manager (UX) | UX | Increment 11 |
| OQ-11 | Версия Temporal и настройка namespace в Docker Compose | Infrastructure | Increment 0 |
| OQ-12 | LangGraph Checkpointer isolation: отдельная schema PostgreSQL | LangGraph | Increment 7 |
| OQ-13 | Задания task-class evaluation sets и пороги приёмки | Evaluation | Increment 25 |
| OQ-14 | On-call routing, PagerDuty или аналог | Observability | Post-MVP |

---

## Предложения, требующие согласования

| # | Предложение | Статус | Нормативный документ |
|---|---|---|---|
| PR-1 | Bifrost как LLM Gateway | Candidate, pending PoC | DOC-076, DOC-015 |
| PR-2 | `ai_res_session` как cookie name | Проектное предложение до security review | Impl.Spec §6, Auth §6 |
| PR-3 | `X-CSRF-Token` как CSRF header | Проектное предложение до security review | Impl.Spec §6 |
| PR-4 | A0–A4 autonomy scale | PROPOSED, не активировать A3/A4 без отдельного approval matrix | DOC-038 |
| PR-5 | Glossary v1.1 как нормативный UI label / prompt rule | BASELINED как глоссарий, не как нормативный label до Glossary Owner review | DOC-035 |
| PR-6 | CI/Continuous Improvement endpoints/events | BASELINED контракты, но CI endpoints не утверждены для включения в API | DOC-043 |
| PR-7 | Перевод DOC-007 (Worker Contracts) в BASELINED | Рекомендуется до Increment 6 | DOC-007 |

---

## Технические решения, требующие PoC

| # | Решение | Что нужно проверить |
|---|---|---|
| TR-1 | pgvector для embeddings | Benchmark качества retrieval на реальных проектных данных vs отдельный vector DB |
| TR-2 | PostgreSQL FTS + pgvector (hybrid search) | Recall@k, Precision@k, MRR на golden queries |
| TR-3 | Bifrost PoC | Docker Compose integration, LangGraph compatibility, streaming, tool calling, security audit |
| TR-4 | Temporal replay | Реализованные workflow должны проходить replay-тест без non-determinism |
| TR-5 | RLS ENABLE + FORCE | Тестировать под реальными runtime roles; ensure no BYPASSRLS для runtime principals |
| TR-6 | pgBackRest WAL Archiving | Recovery drill: PostgreSQL restore + MinIO snapshot reconciliation |
| TR-7 | LangGraph Checkpointer isolation | Отдельная PostgreSQL schema; отсутствие cross-schema FK с доменными таблицами |
| TR-8 | Alembic migrations | Upgrade from empty DB, upgrade from previous revision, expand/backfill/validate/contract sequence |
| TR-9 | Temporal Activity idempotency | Retry/replay не создаёт дублирующие WorkerRun или Operation |
| TR-10 | Outbox dispatcher concurrency | Lease mechanism не держит DB lock во время network call; bounded retry + quarantine |

---

## Перечень изученных документов

Документы, прочитанные полностью в ходе данного анализа:

| ID | Файл | Статус в реестре |
|---|---|---|
| DOC-022 | `AI_RES_Document_Registry_v4.1.md` | BASELINED |
| DOC-054 | `AI_RES_Cross_Document_Consistency_Audit_v2.2.md` | BASELINED |
| DOC-042 | `AI_RES_Pre_Implementation_Readiness_Audit_v2.2.md` | BASELINED |
| DOC-041 | `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` | BASELINED |
| DOC-055 | `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` | BASELINED |
| DOC-023 | `AI_RES_Authentication_and_Session_Management_v1.1.md` | BASELINED |
| DOC-077 | `AI_RES_Knowledge_Memory_Retrieval_Architecture_v1.0.md` | BASELINED |

---

## Перечень документов, изученных частично

Документы, прочитанные в объёме первых 150–500 строк (ограничение по размеру файла или достаточность для анализа):

| ID | Файл | Статус | Прочитанный объём |
|---|---|---|---|
| DOC-001 | `AI_RES_Agent_Architecture_Concept_v4.6.md` | BASELINED | §§1–3.8 (разделы Manager, Workers, методы взаимодействия) |
| DOC-009 | `AI_RES_MVP_Capability_Matrix_v3.3.md` | BASELINED | §§1–8 (полная матрица, MVP состав, отложенные возможности, пробелы) |
| DOC-005 | `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` | BASELINED | §§1–16 (все разделы) |
| DOC-015 | `AI_RES_Infrastructure_Deployment_Operations_v1.7.md` | WORKING | §§1–9 (стратегия, runtime, Temporal, хранилища, сети, LLM Gateway) |
| DOC-010 | `AI_RES_Source_and_Context_Lifecycle_v1.3.md` | BASELINED | §§1–4.2 (принципы, доменная модель, категории источников) |
| DOC-024 | `AI_RES_Observability_Architecture_v1.2.md` | BASELINED | §§1–12 (все разделы) |

---

## Документы, не читавшиеся в данном анализе

Следующие нормативные документы Registry v4.1 не читались. Их содержание представлено в данном анализе только через ссылки и выдержки из других документов.

| ID | Файл | Статус |
|---|---|---|
| DOC-002 | `AI_RES_Process_Design_and_Algorithms_v1.9.md` | BASELINED |
| DOC-003 | `AI_RES_Requirements_Lifecycle_v2.7.md` | BASELINED |
| DOC-004 | `AI_RES_UX_Concept_v1.2.md` | BASELINED |
| DOC-006 | `AI_RES_API_and_Interaction_Contracts_v1.10.md` | BASELINED |
| DOC-007 | `AI_RES_Worker_Contracts_v1.1.schema.json` | WORKING |
| DOC-008 | `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml` | BASELINED |
| DOC-011 | `AI_RES_Tool_Registry_and_Tool_Management_MVP_v1.0.md` | BASELINED |
| DOC-012 | `AI_RES_Traceability_Dependencies_Impact_Analysis_v1.0.md` | WORKING |
| DOC-013 | `AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md` | WORKING |
| DOC-014 | `AI_RES_External_Integrations_and_Project_Context_v1.2.md` | BASELINED |
| DOC-016 | `AI_RES_Security_Architecture_v1.2.md` | BASELINED |
| DOC-017 | `AI_RES_Threat_Model_v1.1.md` | BASELINED |
| DOC-018 | `AI_RES_Identity_Access_Control_v1.5.md` | BASELINED |
| DOC-019 | `AI_RES_Secrets_and_Key_Management_v1.1.md` | BASELINED |
| DOC-020 | `AI_RES_Security_Controls_and_Requirements_v1.2.md` | BASELINED |
| DOC-021 | `AI_RES_Methodology_and_Source_Traceability_Matrix_v1.2.md` | BASELINED |
| DOC-025 | `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md` | WORKING |
| DOC-026 | `AI_RES_Agent_Observability_and_Evaluation_v1.2.md` | BASELINED |
| DOC-027 | `AI_RES_Operational_Runbooks_v1.0.md` | WORKING |
| DOC-030 | `AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md` | WORKING |
| DOC-031 | `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md` | WORKING |
| DOC-032 | `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md` | WORKING |
| DOC-033 | `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md` | WORKING |
| DOC-035 | `AI_RES_Glossary_v1.1.md` | BASELINED |
| DOC-038 | `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.3.md` | BASELINED |
| DOC-039 | `AI_RES_Continuous_Improvement_Requirements_v1.3.md` | BASELINED |
| DOC-043 | `AI_RES_Continuous_Improvement_Contracts_v1.1.md` | BASELINED |
| DOC-050 | `AI_RES_Public_API_v1.3.yaml` | WORKING |
| DOC-051 | `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md` | BASELINED |
| DOC-056 | `AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json` | WORKING |
| DOC-057 | `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json` | WORKING |
| DOC-061 | `AI_RES_Operation_WorkerRun_Event_Model_v1.4.md` | BASELINED |
| DOC-064 | `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md` | BASELINED |
| DOC-065 | `AI_RES_PostgreSQL_Physical_Model_v1.0.sql` | WORKING |
| DOC-068 | `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md` | BASELINED |
| DOC-069 | `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql` | WORKING |
| DOC-072 | `AI_RES_Persistence_Implementation_Blueprint_v1.0.md` | BASELINED |
| DOC-075 | `AI_RES_Architecture_Completion_and_Baseline_Decisions_v1.0.md` | BASELINED |
| DOC-076 | `AI_RES_Model_Gateway_and_Model_Registry_v1.0.md` | BASELINED |
| DOC-078 | `AI_RES_Evaluation_and_Release_Gates_v1.0.md` | BASELINED |
| DOC-079 | `AI_RES_Learning_Experience_Lifecycle_v1.0.md` | BASELINED |

---

## Предложенная последовательность технических инкрементов реализации MVP

Порядок строго следует `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` §4 и дополнениям, с учётом блокирующих зависимостей.

**Критическое условие старта (Pre-condition Increment 0):** до первого изменения кода — baseline manifest и repository reconnaissance complete; discrepancy report закрыт; unresolved decisions перечислены с owner и blocking/non-blocking классификацией.

**Правило завершения каждого инкремента:** code diff + migration revision + automated test report + security evidence + runtime configuration + known limitations. Завершение не заявляется на основе только генерации кода или документации.

---

### Increment 0 — Repository reconnaissance

- Инспекция репозитория, стека, зависимостей, тестовой инфраструктуры.
- Discrepancy report между документацией и фактическим репозиторием.
- Implementation Baseline Manifest.
- Confirm OpenAPI/AsyncAPI/JSON Schema toolchain.
- **Результат:** план реализации, список missing prerequisites.

---

### Increment 1 — Contract toolchain

- Создать `contracts/` директории: openapi/, asyncapi/, json-schema/ (common/, worker/, events/, commands/), examples/.
- CI validation, lint, breaking-change detection.
- Pinned tool versions.
- **Результат:** validateable contracts, CI job.

---

### Increment 2 — Shared platform primitives

Реализовать в указанном порядке:
1. UUID и time serialization rules.
2. API Problem Details error model (RFC 9457).
3. request/correlation/trace context propagation.
4. Pagination contract.
5. ETag/If-Match и optimistic concurrency primitives.
6. Idempotency-Key storage и replay behavior.
7. Authentication/service identity middleware integration points.
8. Object-level authorization hooks и policy decision interface.
9. Audit writer interface.
- **Результат:** платформенные примитивы с negative/security tests.

---

### Increment 3 — Read-only vertical slices

- Read paths для: Project, Epic, Task, Requirement, Source, Artifact, WorkerRun.
- ACL enforcement на каждый запрос.
- Pagination, filtering, ETags, DTO mapping.
- Нельзя возвращать ORM entities напрямую.
- **Результат:** verified read API + authorization tests.

---

### Increment 4 — Controlled write commands

Реализовать в порядке:
1. Project/Epic/Task.
2. Requirement version proposals.
3. Source upload lifecycle.
4. Artifact lifecycle.
- Domain services, transaction boundaries, If-Match, idempotency, audit, outbox.
- **Результат:** verified write API + isolation tests.

---

### Increment 5 — Asynchronous operations and SSE

- Operation resource, Temporal start/cancel integration, SSE.
- API возвращает 202 и operation reference для длительных задач.
- SSE — проекция авторизованных domain events, не замена REST.
- **Результат:** Operation lifecycle + reconnect/replay tests.

---

### Increment 6 — Manager/Worker runtime contracts

- Typed WorkerRunEnvelope, WorkerResult и WorkerNotice schemas.
- Валидация в четырёх точках: enqueue / Worker execution / result persistence / downstream consumption.
- Worker не может писать domain data напрямую или self-grant permissions.
- **Результат:** validated contract pipeline.

---

### Increment 7 — Temporal + LangGraph integration

- Deterministic Workflow definitions и Activities для external effects.
- Idempotency, bounded retries, timeout, heartbeat, cancellation, reconciliation.
- Replay compatibility tests.
- LangGraph thread/checkpoint scope — один WorkerRun.
- **Результат:** verified durable execution + replay tests.

---

### Increment 8 — Events and integrations

- Transactional Outbox, CloudEvents envelope, idempotent consumer/inbox marker.
- Bounded retries, DLQ/quarantine.
- Connector Platform adapter contracts; GitHub/GitLab read-only.
- **Результат:** at-least-once delivery + deduplication tests.

---

### Increment 9 — Contract and security verification

- Полный пакет тестов: contract, integration, replay, idempotency, authorization, isolation, prompt injection, secret-leakage, failure-recovery.
- **Результат:** evidence + test reports; no unresolved critical/high.

---

### Increment 10 — Process primitives

- Typed lifecycle transitions, Process/GateResult model, Operation projection.
- Correlation, audit, outbox, idempotency, state transition tests.

---

### Increment 11 — Project/Epic intake

- Project creation, Manager intake, adaptive question state.
- Proposal persistence, human decision boundary.

---

### Increment 12 — Plan & Task orchestration

- Immutable PlanVersion, PlanItem/Task mapping.
- Dependency graph validation, cycle detection.
- Partial approval constraints, Temporal workflow skeleton.

---

### Increment 13 — Readiness Gate

- Deterministic check registry, GateResult/ReadinessEvaluation.
- Block reasons, staleness invalidation.
- Last-moment grant/cancellation check, TOCTOU revalidation.

---

### Increment 14 — Worker Run lifecycle

- Envelope validation, Temporal schedule/start.
- LangGraph thread scope, WorkerNotice/Result.
- Immutable persistence, Manager acceptance.

---

### Increment 15 — QA and rework

- Verification modes, independent QA, disagreement handling.
- New Run for rework, human approval separation.

---

### Increment 16 — Source ingestion and Impact Assessment

- Immutable SourceVersion, extraction provenance, indexing status.
- ChangeSet, deterministic + semantic impact, targeted revalidation.

---

### Increment 17 — Artifact / CR / Baseline lifecycle

- Generate, validate, review, approve, publish.
- Exact-version baseline и CR workflow.

---

### Increment 18 — Recovery and evaluation

- Error taxonomy, bounded retries, pause/cancel/resume, reconciliation.
- Process Evaluation Sets, regression, deployment gates.

---

### Increment 20 — LLM Gateway + Model Registry

- `LLMGatewayPort` + Model Registry + Bifrost PoC adapter.
- Никаких provider-specific вызовов из агентов напрямую.

---

### Increment 21 — Knowledge ingestion

- PostgreSQL FTS/pgvector + MinIO; provenance и ACL.
- ACL leakage tests — hard blockers.

---

### Increment 22 — Retrieval API + Context Builder

- Immutable context package; ACL-before-retrieval.
- ACL leakage tests — hard blockers.

---

### Increment 23 — Tool Registry/Gateway

- Typed tool contracts, per-call policy, MCP allowlist adapter.
- Side-effect tests.

---

### Increment 24 — Connector MVP

- file/OpenAPI/GitHub/GitLab read-only.
- Checkpoint, dedupe, rate-limit, partial sync.

---

### Increment 25 — Evaluation harness

- Task-class datasets, regression manifest.
- Human calibration и release gates.

---

### Increment 26 — Learning signal / curated experience

- Non-parametric curated experience workflow.
- Без fine-tuning или autonomous behavior update.

---

### Increment 27 — Security hardening

- Adversarial acceptance across API, retrieval, tools, files, secrets, RLS, event delivery.

---

### Increment 28 — UI/UX acceptance

- Accessibility, user guides от фактического running product.
- Operational runbooks.

---

> **Примечание:** данный анализ является производным документом и не является нормативным источником требований. При любом расхождении с нормативными документами Document Registry v4.1 и Implementation Spec v1.22 — приоритет за нормативными документами.
