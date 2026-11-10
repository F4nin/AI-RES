# AI RES — План пользовательской документации, глоссария и непрерывного улучшения

**Версия:** 1.3  
**Статус:** PARTIALLY DESIGNED / post-implementation deliverables pending  
**Дата фиксации:** 2026-11-10  
**Связанный проект:** AI RES

## 1. Назначение и место в общей последовательности

Этот блок выполняется после завершения архитектурных этапов и реализации согласованного объёма AI RES, когда фактическое поведение, интерфейсы, роли, ограничения и эксплуатационные процессы можно описать и проверить.

Он не заменяет техническую документацию для разработчиков и эксплуатационные runbooks. Его результат — готовность продукта к использованию аналитиками и стейкхолдерами, единая терминология и управляемый процесс дальнейшего улучшения.

Предлагаемая последовательность:
1. Завершить текущие архитектурные этапы, включая этап 15 Performance, Scalability & Resilience.
2. Завершить реализацию согласованного объёма.
3. Провести acceptance, security, usability и operational validation.
4. Выполнить этот блок пользовательской документации, глоссария и Continuous Improvement.
5. Подготовить пользовательский релизный комплект и передать продукт пользователям.

**Важно:** документация описывает фактически реализованное поведение. Проектные намерения и нереализованные возможности должны быть явно обозначены.

## 2. Направление A — пользовательская документация (AI RES User Guide)

### 2.1. Аудитории

**Бизнес- и системные аналитики**
- назначение AI RES и границы его возможностей;
- создание организации, проекта и Epic;
- добавление источников и управление контекстом;
- работа с Manager, планами, задачами и Workers;
- elicitation, анализ, исследование и уточнение требований;
- работа с требованиями, решениями, рисками, моделями и артефактами;
- проверка результатов, QA, трассируемость и impact analysis;
- согласование, baseline, change control и история версий;
- исправление результатов и предоставление обратной связи;
- ошибки, ограничения и способы восстановления пользовательского процесса.

**Стейкхолдеры и руководители**
- обзор проекта, Epic, прогресса и ключевых решений;
- чтение требований, аналитических результатов и артефактов;
- понимание статусов, рисков, неопределённости и доказательств;
- review, комментарии, согласование и отклонение;
- влияние изменений и связь решений с требованиями;
- различие между рекомендацией ИИ и решением человека;
- эскалации и ситуации, требующие участия аналитика.

### 2.2. Формат и структура

Рекомендуемый комплект:
1. AI_RES_User_Guide.md — полное руководство пользователя.
2. AI_RES_Analyst_Guide.md — практическое руководство аналитика.
3. AI_RES_Stakeholder_Guide.md — руководство стейкхолдера.
4. AI_RES_Quick_Start.md — быстрый старт с первым проектом.
5. AI_RES_Workflow_Examples.md — сквозные сценарии Greenfield, Brownfield и Hybrid.
6. AI_RES_FAQ_and_Troubleshooting.md — вопросы, ошибки и способы решения.
7. Контекстные подсказки/onboarding внутри интерфейса — по возможности.

Документация должна включать реальные скриншоты, примеры, пошаговые сценарии, объяснение статусов и типовые решения. Скриншоты и инструкции создаются после фиксации реализованного UI, а не по проектным макетам.

### 2.3. Требования к достоверности

- Для каждого описанного действия должна существовать проверенная функция/экран.
- Различать доступные, ограниченные, экспериментальные и запланированные возможности.
- Не описывать внутренние технологии, если они не нужны пользователю.
- Объяснять, что ИИ предлагает, что выполняет автоматически, что требует подтверждения и что ему запрещено.
- Указывать ограничения, обработку ошибок, отмену/повтор, последствия действий и точки человеческого контроля.
- Версионировать документацию вместе с релизами продукта.

## 3. Направление B — единый глоссарий AI RES

### 3.1. Результат

Создать самостоятельный артефакт `AI_RES_Glossary_v1.0.md`, являющийся каноническим словарём терминов продукта. Дополнительно предусмотреть машинно-читаемое представление для использования приложением и агентами, например JSON/YAML, после определения схемы.

### 3.2. Области терминов

- бизнес-анализ и системный анализ;
- elicitation и engineering requirements;
- типы требований, критерии приёмки и quality;
- Project, Epic, Task, Plan, Plan Version;
- Manager, Worker, Worker Run, Agent Runtime;
- Workflow, Activity, Readiness Gate, Context Package;
- Source, Source Version, Evidence, Provenance;
- Knowledge, Memory, Retrieval, Evaluation;
- Artifact, Artifact Version, Representation, Baseline;
- Traceability, Impact Assessment, Change Request;
- Review, Verification, Independent QA, Approval;
- Autonomy, Permission, Policy, Human-in-the-loop;
- Observability, SLI/SLO, Drift, Feedback, Continuous Improvement.

### 3.3. Обязательные поля термина

- canonical_term — предпочтительное название;
- definition — точное определение;
- plain_language_explanation — объяснение простыми словами;
- domain/category — предметная область;
- synonyms — допустимые синонимы;
- deprecated_terms — нежелательные/устаревшие варианты;
- related_terms — связанные понятия;
- examples — контекстные примеры;
- usage_notes — правила употребления;
- status/version/owner — статус, версия и владелец записи;
- source/reference — источник определения или решение AI RES.

### 3.4. Правила управления

- Один термин — одно каноническое значение в рамках заданного контекста.
- Омонимы и термины с разным смыслом в разных доменах должны быть явно разграничены.
- Термины из внешних стандартов не переопределяются молча.
- Изменение определения проходит review и версионирование.
- Glossary используется в UI labels, user docs, generated artifacts, prompts/instructions и validation checks.
- Агент может предложить новый термин, но не может самостоятельно менять утверждённое определение.
- Терминологические конфликты выявляются при проверке документации и артефактов.

## 4. Направление C — Continuous Improvement & Autonomy Maturity

### 4.1. Цикл улучшения

1. **Observe:** сбор telemetry, outcomes, user feedback, QA findings, corrections, incidents and cost.
2. **Identify:** выявление повторяющихся ошибок, успешных паттернов, пробелов знаний и неэффективных workflow.
3. **Propose:** формирование Improvement Proposal с проблемой, evidence, гипотезой, ожидаемым эффектом, рисками и областью изменений.
4. **Evaluate:** проверка на versioned evaluation/regression sets, независимая QA и security/policy review.
5. **Approve:** решение уполномоченного человека/владельца правила в соответствии с классом изменения.
6. **Release:** контролируемая публикация новой версии знаний, шаблона, prompt, workflow, tool adapter или модели.
7. **Measure:** сравнение с baseline, проверка побочных эффектов и решение сохранить/откатить изменение.

### 4.2. Что система может улучшать

Разделять объекты улучшения:
- knowledge base / approved knowledge;
- retrieval/indexing/chunking/ranking;
- prompts и шаблоны;
- workflow и правила планирования;
- инструменты и connector adapters;
- evaluation rubrics и test sets;
- glossary и terminology rules;
- model/provider configuration;
- UI hints и пользовательские сценарии.

Изменения этих объектов имеют разные риски и разные процедуры утверждения. Изменение тестового набора или evaluator не должно незаметно менять критерии приёмки продукта.

### 4.3. Уровни автономности — предлагаемый механизм

| Уровень | Поведение | Допуск |
|---|---|---|
| A0 — Observe | Только собирает сигналы и выявляет проблемы | Базовый |
| A1 — Recommend | Предлагает улучшения и объясняет основания | После проверки качества сигналов |
| A2 — Prepare | Создаёт черновики изменений, тесты и план rollout; не активирует их | При наличии review |
| A3 — Controlled execution | Самостоятельно внедряет заранее разрешённые низкорисковые изменения в ограниченном scope, с rollback | Только после прохождения evaluation, security и approval gate |
| A4 — Bounded autonomy | Сам выбирает и выполняет действия в заранее утверждённых классах задач и бюджетах, с постоянным мониторингом и выборочным аудитом | Только для конкретной capability после доказанного допуска |

Уровни присваиваются не AI RES целиком, а отдельным capability/action class. Например, агент может иметь A4 для обновления чернового поискового индекса, A2 для изменения prompt и A0 для изменения security policy или утверждения бизнес-требований.

### 4.4. Оценка готовности к повышению автономности

Оценивать по совокупности:
- качество результата на репрезентативном versioned evaluation set;
- независимая QA и доля критичных дефектов;
- частота исправлений человеком и rework;
- стабильность на разных типах проектов/источников/языков;
- устойчивость к adversarial input и prompt injection;
- соблюдение permissions, auditability и policy constraints;
- частота ошибочных tool calls и side effects;
- latency, cost, resource consumption;
- успешность recovery и rollback;
- качество evidence/provenance и корректность эскалации;
- достаточность объёма наблюдений и статистическая неопределённость.

Повышение уровня автономности запрещено только на основании общего success rate, количества завершённых задач или субъективного впечатления.

### 4.5. Gates для повышения автономности

1. Capability и разрешённый scope формально описаны.
2. Определены запрещённые действия и human escalation conditions.
3. Есть достаточная репрезентативная evaluation выборка и baseline.
4. Критичные сценарии проходят regression и security tests.
5. Есть независимая QA и отсутствие открытых критических дефектов.
6. Есть budget/time/action limits, idempotency и rollback.
7. Включены telemetry, audit и alerting.
8. Проведён shadow/staged rollout, где применимо.
9. Назначен владелец capability и период пересмотра.
10. Изменение утверждено уполномоченным человеком.

### 4.6. Ограничения автономности

Накопление опыта само по себе не расширяет права агента. Запрещено автоматически:
- менять system-level rules, access policies и security controls;
- выдавать себе или другим агентам новые permissions;
- утверждать бизнес-требования, baseline или критические решения за человека;
- менять критерии оценки так, чтобы скрыть регрессию;
- автоматически обучаться на сырых пользовательских данных без reviewed dataset lifecycle;
- выполнять необратимые внешние side effects без соответствующего разрешения.

## 5. Метрики эффективности улучшений

Каждая Improvement Proposal должна содержать baseline, target, measurement window и guardrails.

Рекомендуемые группы:
- quality: pass rate, defect rate, critical defect rate, independent QA;
- rework: human correction rate, returned-for-rework rate;
- effectiveness: task completion by outcome class, first-pass acceptance;
- autonomy: eligible actions executed autonomously, human intervention rate, escalation correctness;
- safety: policy violations, unauthorized tool attempts, harmful side effects;
- evidence: provenance coverage, unsupported assertion rate;
- efficiency: time-to-completion, token/cost per accepted result, tool calls per task;
- reliability: retries, timeout, recovery success, rollback rate;
- user value: satisfaction, adoption, stakeholder decision latency.

Метрики сегментируются по capability, task class, project type, model/prompt/tool version. Улучшение одного показателя не принимается, если ухудшаются safety/quality guardrails.

## 6. Governance и роли

- Improvement Owner — отвечает за гипотезу и ожидаемый эффект.
- Capability Owner — отвечает за область автономности и ограничения.
- Evaluation Owner — поддерживает datasets, rubric и quality evidence.
- Security/Policy Reviewer — проверяет права, риски и безопасность.
- Approver — утверждает активацию в соответствии с уровнем риска.
- Release Owner — выполняет rollout/rollback и фиксирует версию.

В небольшой команде роли могут совмещаться, но не должны исчезать из процесса.

## 7. Связь с существующей архитектурой AI RES

- Observability (этап 14) поставляет telemetry, traces, alerts и feedback signals.
- Evaluation Framework (этап 9) проверяет кандидаты на улучшение и regression.
- Knowledge & Memory architecture управляет проверенным накоплением знаний.
- Rules Registry / Rules Engine / Policy & Permission Engine контролируют допустимые изменения и полномочия.
- Artifact Registry хранит версионируемые инструкции, шаблоны и документацию.
- Temporal выполняет durable improvement workflows, approvals, staged rollout и rollback.
- Manager предлагает и координирует улучшения, но не обходит approval gates.
- Glossary обеспечивает согласованную терминологию в данных и результатах.

## 8. Критерии завершения завершающего блока

1. Пользовательские руководства соответствуют реально реализованному UI и поведению.
2. Для ключевых сценариев есть пошаговые инструкции и примеры.
3. Глоссарий покрывает основные домены AI RES и имеет управляемый lifecycle.
4. Глоссарий доступен и людям, и агентам через утверждённый источник.
5. Continuous Improvement workflow имеет owner, evidence, evaluation, approval, release и rollback.
6. Уровень автономности задаётся отдельно по capability/action class.
7. Повышение автономности опирается на evaluation evidence и explicit approval.
8. Есть baseline и guardrail metrics, позволяющие обнаружить регрессию.
9. Изменения и решения версионируются и аудируются.
10. Документация и glossary проверены на соответствие фактическому продукту.

## 9. Статус

Этот документ фиксирует планируемый завершающий блок и проектные рекомендации. Он не означает, что пользовательские руководства, glossary, continuous improvement workflow или уровни автономности уже реализованы. Подробные схемы, data contracts, API и требования будут разработаны на соответствующем этапе проектирования/реализации.


---

## 10. Дополнение v1.1 — проектная часть выполнена до реализации

Чтобы не откладывать весь завершающий блок до конца реализации, его проектная часть оформлена отдельными нормативными документами:

- `AI_RES_Glossary_v1.0.md` — 59 терминологических записей с примерами и cross-references, PROPOSED до утверждения владельцами.
- `AI_RES_Glossary_v1.0.json` — машинно-читаемое представление записей.
- `AI_RES_Glossary_Entry_Schema_v1.1.json` и `AI_RES_Glossary_Document_Schema_v1.0.json` — схемы валидации записей и документа.
- `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.1.md` — архитектура Improvement Lifecycle и capability-scoped autonomy.
- `AI_RES_Continuous_Improvement_Requirements_v1.1.md` — 45 требований CI.
- `AI_RES_Continuous_Improvement_Contracts_v1.0.md` и `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json` — доменные контракты и схемы.
- `AI_RES_User_Documentation_Information_Architecture_v1.0.md` — структура пользовательской документации и release gates.

### 10.1. Что уже спроектировано
- каноническая структура Glossary Entry и его lifecycle;
- использование canonical terms в UI, пользовательских документах, промптах и генерируемых артефактах;
- Improvement Proposal, Evidence Store, Evaluation Orchestrator, Approval/Governance, Release Controller и Outcome Measurement;
- жизненный цикл Observe → Identify → Propose → Evaluate → Approve → Release → Measure;
- управление автономностью по capability/action class/environment/scope;
- обязательные evidence, независимая QA, hard guardrails, approvals, versioning, staged rollout and rollback;
- запрет self-approval, self-escalation и автоматического расширения прав вследствие накопления опыта.

### 10.2. Что остаётся после реализации
- провести терминологическое согласование и утвердить Glossary v1.0;
- дополнить определения реальными примерами из интерфейса и сценариев AI RES;
- подключить glossary validation к реальным UI/docs/artifact pipelines;
- реализовать Improvement workflow, registry, evaluation/approval/release integrations;
- собрать реальные evaluation baselines и thresholds;
- утвердить capability/action-class autonomy matrix;
- создать User Guide, Analyst Guide, Stakeholder Guide, Quick Start, Workflow Examples и FAQ по фактическому UI;
- провести usability validation пользовательской документации.

### 10.3. Дополнение v1.2 — уточнённый статус

Проектная часть блока 16 расширена: глоссарий имеет примеры и межтерминные связи, созданы document/entry schemas, доменные контракты Improvement Proposal/Evaluation Manifest/Autonomy Grant/Governance Decision и информационная архитектура пользовательских руководств. Это не означает runtime implementation. Предложенные endpoint/event names требуют интеграции в основные OpenAPI/AsyncAPI и согласования с Domain Model до разработки.

### 10.4. Ограничение статуса
Глоссарий v1.0 — проектный словарь со статусом PROPOSED, не окончательно утверждённый корпоративный стандарт. A0–A4 — предлагаемая шкала; её принятие требует отдельного решения. Архитектура и требования не доказывают наличие соответствующих runtime функций.


## Дополнение v1.3 — статус пользовательской документации

Пользовательские руководства (Quick Start, Analyst Guide, Stakeholder Guide, User Guide, Admin Guide, FAQ/Troubleshooting, Workflow Examples) являются будущими deliverables и создаются после UI release acceptance. Упоминания названий ниже не являются ссылками на уже существующие файлы. Содержание и screenshots должны проверяться на реально работающем UI; до этого не заявлять их готовность.
