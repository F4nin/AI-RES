# AI RES — Матрица методологии и трассируемости исходных глав

**Версия:** 1.2  
**Назначение:** проверить, какие положения предоставленных пользователем конспектов глав 2–10 использованы при проектировании AI RES, где они отражены и что требует дополнительной проработки.

## 1. Правила

- Исходные конспекты глав — методологическая база, но не автоматические требования к AI RES.
- Формулировки книги/конспекта отделяются от проектных решений AI RES.
- `Учтено` означает, что принцип явно отражён в проектном документе; не означает, что реализация готова.
- `Частично` означает, что принцип отражён фрагментарно или без полного lifecycle/операционных критериев.
- `Требует проверки` означает, что есть упоминания, но не выполнена предметная сверка каждого подпункта.
- `Неприменимо/отложено` требует rationale; не считается пропуском.

## 2. Матрица по главам

| Глава | Основные темы исходного конспекта | Документы AI RES, где отражено | Статус | Что осталось |
|---|---|---|---|---|
| 2. Проектирование агентских систем | Узкий сценарий; выбор модели; инструменты; память; оркестрация; компромиссы | Agent Architecture Concept; Tool Registry; Source & Context Lifecycle; Infrastructure (LLM Gateway) | Учтено по ключевым принципам | Сверить модельный selection/evaluation и критерии выбора моделей с фактическим MVP provider profile |
| 3. UX-дизайн для агентных систем | Пользователь/контекст; компетенции; модальности; автономность; sync/async; проактивность; контекст; прозрачность | UX Concept; Requirements Lifecycle; Agent Architecture Concept | Учтено по ключевым принципам | Проверить accessibility, error recovery UX, объяснимость permission denials и UX security confirmations |
| 4. Инструменты | Local/API/Plugins/MCP; stateful tools; code generation; конфигурация вызовов; безопасность инструментов | Tool Registry & Tool Management; External Integrations; Agent Architecture Concept | Учтено; security hardening продолжается | Проверить каждый MCP lifecycle, tool schema supply chain, sandbox PoC и human approval semantics; code execution отложено |
| 5. Оркестрация ИИ-агентов | Архетипы; tool selection; planning; workflow orchestration; multi-agent coordination; recovery | Agent Architecture Concept; Process Design & Algorithms; Requirements Lifecycle; API/Interaction Contracts | Учтено по ключевым принципам | Детальная сверка каждой стратегии рассуждения и критериев переключения между ними; runtime tests |
| 6. Знания и память | Context window; full-text/semantic/vector search; RAG; GraphRAG; память; актуальность; provenance; retrieval quality | Source & Context Lifecycle; Domain Model; Traceability/Impact Analysis; Agent Architecture Concept | Учтено частично/основа спроектирована | Отдельная спецификация retrieval evaluation, memory lifecycle/delete/retention, poisoning controls, index rebuild and freshness SLO |
| 7. Обучение в агентных системах | Exemplar Learning; Reflection; Experiential Learning; fine-tuning; SFT/DPO/RFT/RLVR; evaluation/data pipeline | Agent Architecture Concept; Evaluation/QA; MVP Capability Matrix | Частично | Нужен отдельный Learning & Improvement Lifecycle: feedback curation, dataset governance, approval, evaluation, release/rollback; fine-tuning/RL отложены |
| 8. От одного агента ко многим | Специализация; декомпозиция; параллелизм; изоляция; согласованность; координация; отказоустойчивость | Agent Architecture Concept; Process Design; Worker Contracts; Domain Events AsyncAPI; consistency audit | Учтено; дополнительно проверено | Runtime load/scale tests, concurrency budgets, failure injection, security isolation tests |
| 9. Проверки и измерения | Метрики; Evaluation Sets; component/integration/end-to-end tests; regression; gates; quality measurement | Requirements Lifecycle; QA/process docs; MVP Capability Matrix; Worker contracts | Учтено частично | Единый Evaluation Framework для платформы и агентов, паспорта метрик, versioned datasets, judge validation, security evals |
| 10. Мониторинг эксплуатации | Infrastructure/workflow/quality/user feedback metrics; logs/metrics/traces; telemetry security; dashboards/alerts; production feedback loop | Infrastructure Deployment & Operations; Agent Architecture Concept; Audit/Observability sections | Учтено на архитектурном уровне, детали требуют проверки | Проверить конкретные метрики, SLO/thresholds, retention, alert routing, dashboards, feedback-to-evaluation workflow |

## 3. Вывод

Все девять предоставленных глав 2–10 использованы как источники методологии при проектировании AI RES. Однако это не означает равную глубину проработки: главы 7, 9 и отдельные части 6 и 10 требуют самостоятельной детализации. Глава 4 также требует проверки безопасного lifecycle MCP/tools и границ runtime code generation.

## 4. Связь с этапами проекта

- Этап 13 Security Architecture должен использовать главы 4, 6, 9 и 10 как источники требований по инструментам, недоверенным данным, оценке безопасности и мониторингу.
- Отдельный последующий этап Learning & Improvement Lifecycle должен закрыть пробелы главы 7.
- Evaluation Framework должен конкретизировать главу 9 и security evaluation из этапа 13.
- Observability implementation design должен завершить детализацию главы 10.

## 5. Ограничение аудита

Эта версия является трассировочной картой на уровне глав и основных тем. Она не заявляет построчную проверку каждого пункта исходных конспектов. Для полного подтверждения требуется детальная матрица «исходный подпункт → принцип → проектное решение → документ/раздел → требование → тест».


---

## Дополнение v1.1 — предметная детализация главы 10 после этапа 14

| Подтема главы 10 | Решение/требование AI RES | Документ | Статус |
|---|---|---|---|
| Метрики инфраструктуры и workflow | Infrastructure, Temporal, DB, storage, queue, retries, latency | Observability Architecture §5; Monitoring Requirements OBS-MON-001/007 | Спроектировано |
| Агентные метрики | Manager/Worker/Run/Tool/LLM/quality outcomes | Agent Observability & Evaluation §3–6 | Спроектировано |
| Logs/metrics/traces и корреляция | OTel SDK/Collector; Prometheus/Loki/Tempo; correlation IDs | Observability Architecture §3/6/7 | Спроектировано |
| Dashboards/alerts | Шесть базовых dashboards; actionable alert contract | Observability Architecture §9; Monitoring Requirements §5 | Спроектировано |
| Security telemetry | Redaction, запрет raw content/secrets, ACL, retention separation | Monitoring Requirements OBS-SEC-001..011 | Спроектировано |
| Shadow/canary | Shadow безопасно и без side effects; canary только при наличии routing | Agent Observability §10; OBS-MON-021/022 | Спроектировано; реализация позже |
| Regression traces | Sanitized trace → review → Evaluation Set | Agent Observability §7 | Спроектировано |
| User feedback | Явные/ограниченные неявные сигналы, trace linkage, review | Agent Observability §8 | Спроектировано |
| Drift | KS/KL/PSI/embedding methods with calibrated baseline | Agent Observability §9 | Спроектировано; thresholds OPEN |
| Ownership/RACI | metric owner, technical owner, responder, reviewer | Agent Observability §12; Runbooks §1 | Роли предложены, фактические owners OPEN |
| Lifecycle checklist | Требования, архитектура, прототип, тестирование, релиз, эксплуатация | Runbooks §15; Observability Architecture §12 | Спроектировано |

Числовые пороги из исходного конспекта главы 10 не перенесены как нормативы AI RES. SLO, alert thresholds, retention и drift thresholds остаются открытыми до baseline/sizing/privacy review.

**Вывод по главе 10:** прежняя отметка «детали требуют проверки» заменяется на «архитектура и требования этапа 14 спроектированы; runtime instrumentation, calibration, drills и production validation не выполнены».


## Дополнение v1.2 — итоговая трассировка глав 2–10 к архитектурному baseline

| Глава | Методический фокус | AI RES нормативные документы | MVP disposition |
|---|---|---|---|
| 2 | Design, model choice, tools, memory, orchestration, trade-offs | Architecture Concept v4.5; Model Gateway v1.0; Tool Registry v1.0; Knowledge/Memory v1.0 | Manager-led, one approved model profile, typed tools, PostgreSQL FTS+pgvector |
| 3 | UX, autonomy, proactive/asynchronous modes, uncertainty, recovery | UX v1.2; Requirements Lifecycle v2.6; Productization Plan v1.3 | Web Workspace, four Manager modes, A0-A2, human approval |
| 4 | Tool types, MCP, tool execution, security and reliability | Tool Registry v1.0; Identity Access v1.4; Security Architecture v1.2 | Tool Gateway, allowlisted MCP adapter, no runtime codegen |
| 5 | Reasoning/orchestration patterns, workflow and context engineering | Architecture Concept v4.5; Process Design v1.8; Operation/WorkerRun state and event contracts | Temporal durable orchestration + LangGraph bounded reasoning |
| 6 | Memory types, RAG, hybrid retrieval, knowledge graphs, maintenance | Source/Context v1.2; Knowledge/Memory v1.0; Domain Model v1.8 | FTS+pgvector; graph DB/GraphRAG deferred |
| 7 | Non-parametric and parametric learning | Learning Lifecycle v1.0; CI Architecture v1.2; CI Requirements v1.2 | Curated non-parametric experience; no fine-tuning |
| 8 | Multi-agent topologies, communication, shared state | Architecture Concept v4.5; Worker Contracts; Event Model v1.3 | Manager-led, no swarm/A2A, shared runtime pool |
| 9 | Evaluation sets, component and end-to-end evaluation, release gates | Evaluation Framework v1.0; Agent Observability & Evaluation v1.1; CI contracts | Task-class sets, deterministic/security gates, human calibration |
| 10 | Production monitoring, telemetry, drift, incident feedback | Observability Architecture v1.1; Monitoring Requirements; Operational Runbooks | OTel/Grafana stack, safe telemetry, audit separation |

Книга задаёт методические принципы, но не предписывает выбранные AI RES технологии и статусы. Выбор PostgreSQL FTS+pgvector, Bifrost adapter, Temporal/LangGraph, local auth и другие конкретные решения — проектная адаптация AI RES.
