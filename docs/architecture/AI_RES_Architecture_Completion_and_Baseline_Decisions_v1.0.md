# AI RES — Завершение архитектурных блоков и baseline решений

**Версия:** 1.0  
**Дата:** 2026-11-10  
**Статус:** BASELINED — архитектурные решения приняты в рамках делегирования владельца проекта; runtime-реализация и security certification не заявляются.  
**Назначение:** закрыть оставшиеся архитектурные вопросы по модели, памяти/знаниям, инструментам, оценке, обучению, безопасности, UX и интеграциям; определить точные границы MVP и post-MVP.

## 1. Правило источников и принятия решений

1. Ранее явно подтверждённые пользователем решения имеют приоритет.
2. При отсутствии решения используются исходные главы 2–10 как методическая основа, затем архитектурные рекомендации AI RES.
3. Новые решения этого документа приняты по делегированию пользователя «самостоятельно выбрать лучшие рекомендованные решения». Они являются архитектурным baseline, но не доказательством реализации.
4. Требования, зависящие от реальных нагрузок, security review, правовых ограничений или корпоративных политик, фиксируются как проверяемые gates, а не как выдуманные числовые гарантии.
5. Исторические документы сохраняются. Для реализации используется только текущий Registry и версии из него.

## 2. Канонический MVP сценарий

AI RES MVP — web workspace для одного аналитика/команды, работающий с несколькими проектами и Epics. Основной сквозной сценарий: создание проекта и Epic → подключение/загрузка источников → извлечение фактов и кандидатов требований → диалоговое уточнение с Manager → динамический Plan/Tasks → Readiness Gate → выполнение Workers → независимая QA по политике → управление требованиями/решениями/рисками → модели/API/артефакты по контексту → трассируемость и impact analysis → человеческое утверждение → baseline и экспорт документации.

MVP не обещает полностью автономный анализ без человека, универсальную поддержку всех интеграций, обучение весов по production feedback или автоматическое изменение внешних систем.

## 3. Model Gateway и модельный слой

### 3.1 Решение

- Внутренний контракт `LLMGatewayPort` — единственная точка доступа Manager/Worker к LLM.
- Bifrost выбран как предпочтительный gateway implementation для MVP deployment, за внутренним адаптером. Это не доменная зависимость: допускается замена gateway без изменения Worker contracts.
- До включения Bifrost в production-like profile обязательны PoC и security acceptance: structured output, tool calling, streaming, timeout/cancellation, provider errors, retries, fallback, rate limits, usage metering, redaction, secrets, egress, logging, model pinning и отсутствие prompt/response capture по умолчанию.
- MVP начинается с одного проверенного provider/model profile. Multi-provider и local model support сохраняются в архитектурном контракте, но не являются обязательным release criterion первого vertical slice.
- Model Registry хранит provider, model ID, version/snapshot, capabilities, context limits, modalities, data classification allowance, region/egress constraints, cost metadata, rate limits, deprecation status и evaluation status.
- Model routing — детерминированная policy по Worker role, task class, sensitivity, structured-output requirement, latency/cost budget и model capability. LLM не может сам выбрать запрещённый provider или повысить data classification.
- Fallback разрешён только между заранее allowlisted model profiles с равными/более строгими data handling constraints. Fallback не может расширять egress, доступ к данным или tool grants.

### 3.2 Запрещено

- Прямые provider SDK/API вызовы из Manager/Worker Runtime.
- Provider credentials в prompt, WorkerRunEnvelope, Temporal history, tool result или telemetry.
- Автоматическое переключение на публичную модель при недоступности локальной модели без Policy Engine approval.
- Непривязанные к версии model aliases в baseline evaluation/release evidence.

## 4. Knowledge, Memory и Retrieval

### 4.1 Разделение типов данных

- Source of Truth: исходные документы и внешние snapshots в MinIO; метаданные, версии, ACL, provenance и relationships в PostgreSQL.
- Project Knowledge: извлечённые утверждения, факты, решения, требования, фрагменты, embeddings и индексы с provenance.
- Episodic/Run Memory: WorkerRun results, notices, tool outcomes и summaries; привязаны к проекту/Epic/Task/Run и ACL.
- Semantic/Experience Memory: только проверенные reusable patterns/playbooks/examples; в MVP — ограниченный каталог одобренных примеров, не автоматическое изменение поведения.
- Working Context: краткосрочный контекст LangGraph/Manager/Worker, ограниченный конкретным Run и ContextPackageVersion.

Общая память не равна контексту конкретного WorkerRun. Никакая память не предоставляет разрешение на доступ.

### 4.2 MVP retrieval stack

- PostgreSQL Full Text Search (`tsvector`/GIN) + `pgvector` для dense semantic retrieval.
- Hybrid retrieval: lexical + vector candidate retrieval, ACL filtering before ranking/assembly, optional reranking only within authorized candidate set.
- PostgreSQL — metadata/provenance/ACL/source of truth; MinIO — оригиналы и большие immutable payloads. Redis — только cache/ephemeral coordination, никогда не source of truth.
- Отдельная vector DB, GraphRAG и graph database не входят в MVP. Добавлять их только по retrieval benchmark и измеримому bottleneck.
- Embedding model/version фиксируется на индексе; смена модели создаёт новую index generation, не перезаписывает старую молча.
- Chunking хранит source version, fragment locator, offsets/page/sheet/section, content hash, parser version, embedding model/version и ACL inheritance.
- Retrieval results несут provenance refs, confidence/score components, freshness, limitations и access decision metadata.

### 4.3 Безопасность и обновление

- ACL применяется до retrieval, reranking, summarization, graph traversal, cache response и export.
- Cache key включает tenant/project/ACL scope и version; отзыв доступа инвалидирует/обходит старые cache entries.
- Индексация и Impact Assessment — независимые pipelines. Успешная индексация не подтверждает актуальность требований/решений.
- Изменение источника создаёт SourceVersion/ChangeSet и Impact Assessment; active ContextPackageVersion и Baseline immutable.
- Удаление/retention выполняется по data governance policy с учётом legal hold, audit и backup lifecycle.

## 5. Tool Registry и Tool Gateway

- Все инструменты имеют versioned `ToolDefinition`, typed input/output schema, owner, purpose, risk class, side-effect class, required scopes, data classification, timeout, retry policy, idempotency semantics, network destinations, audit fields и health state.
- Tool Registry описывает доступность, но не выдаёт право. Каждая операция проходит Policy & Permission Engine непосредственно перед вызовом.
- Tool Gateway/Adapter — единственная точка исполнения; Manager/Workers не получают произвольный network access.
- Внутренние инструменты используют typed application ports. MCP поддерживается как adapter/protocol boundary для совместимых внешних tools; неизвестный MCP server не доверенный и не подключается автоматически.
- MCP server изолируется как отдельная trust boundary; allowlist tools, schema validation, auth, egress policy, timeout, output size limits, audit и per-call authorization обязательны.
- Runtime code generation/Cloudflare Code Mode не входит в базовый MVP. Разрешён только отдельный sandbox PoC после threat review; generated code не получает credentials, host mounts, Docker socket или произвольный egress.
- Side effects во внешних системах выключены в MVP, кроме операций, явно перечисленных как безопасные локальные операции. GitHub/GitLab — read-only.

## 6. Orchestration и Worker model

- Manager-led orchestration; Temporal — durable workflow; LangGraph — reasoning внутри ограниченных Manager/Worker steps.
- Workflow orchestration не передаёт бизнес-решения LLM. Состояния, gates, permissions, approvals, idempotency и recovery детерминированы backend/domain services.
- Девять Workers остаются логическими специализациями общего Worker Runtime pool.
- Worker-to-Worker direct communication запрещена; CONSULTATION, DELEGATED_SUBTASK и HANDOFF проходят через Manager/Workflow Engine.
- QA независима от автора результата; критические артефакты/требования проходят отдельный QA WorkerRun по task-class policy.
- Worker не пишет в доменные таблицы, не меняет grants, не утверждает требования/Baseline и не расширяет scope.

## 7. Evaluation Framework и release gates

### 7.1 Evaluation layers

1. Contract/schema tests — структуры WorkerResult, API, events, tool inputs/outputs.
2. Deterministic domain tests — lifecycle, permissions, transitions, traceability, artifact validation.
3. Component evals — retrieval, planning, tool selection, elicitation, requirement extraction, QA.
4. Workflow evals — полный сценарий Epic, fan-out/fan-in, rework, cancellation, recovery.
5. Security/adversarial evals — prompt injection, cross-project leakage, tool abuse, unauthorized side effects, data exfiltration.
6. Human review/calibration — выборка результатов и разбор disagreement.

### 7.2 Evaluation Set

Каждый case включает `case_id`, task_class, scenario, sanitized input/context fixture, expected assertions/rubric, risk/severity, source/provenance, dataset version, split, owner, last_reviewed_at и known limitations. Production feedback не попадает в golden set автоматически: сначала triage, sanitization, consent/rights check, deduplication и reviewer approval.

### 7.3 Gates

- Никакой release при critical security/privacy regression, schema/contract breakage, cross-tenant leakage или нарушении reserved human decision.
- Для deterministic checks — 100% pass на обязательном suite.
- Для model-based quality — thresholds задаются отдельно по task class после baseline measurement; не устанавливать общий искусственный процент на весь продукт.
- LLM-as-judge не является единственным acceptance oracle. Используются deterministic assertions, rubric-based judge, human sample review и pairwise regression.
- Model, prompt, tool, retrieval, embedding, workflow и ruleset versions pin-ятся в evaluation manifest.
- Shadow/canary включаются только после reproducible offline evaluation и rollback plan.

## 8. Learning & Experience Lifecycle

- MVP использует non-parametric improvement: curated exemplars, approved playbooks, prompt/rules revisions и evaluation set updates через governance.
- Human feedback, QA defects и production incidents сначала становятся Improvement Signals; не меняют prompts/models/memory автоматически.
- Learning data проходит provenance, data minimization, de-identification, rights/consent review, tenant isolation и retention policy.
- Fine-tuning (SFT/DPO/RFT/RLVR), cross-tenant training и automatic policy/prompt adaptation исключены из MVP.
- A0 Observe, A1 Recommend, A2 Prepare — допустимые MVP autonomy levels. A3 Controlled execution и A4 Bounded autonomy отключены по умолчанию и требуют отдельного capability/action/environment grant, evaluation evidence, security approval, monitoring и rollback.
- Успешные запуски и накопленный опыт не расширяют permissions и не повышают autonomy автоматически.

## 9. UX и человеко-машинное взаимодействие

- Основной канал MVP — web Project Workspace с persistent project/Epic context.
- Четыре режима Manager: reactive, proactive, asynchronous, consultative; proactive инициативы группируются и ограничиваются policy/rate limits.
- Manager показывает текущую цель, Plan/Task status, причины ожидания, evidence/provenance, uncertainty, assumptions, limitations, proposed changes и ожидаемое действие человека.
- Human approval всегда привязан к точной версии объекта и scope; изменения после approval требуют нового approval.
- Уведомления только для решений, блокеров, существенных изменений и завершений; технический шум остаётся в activity/audit.
- UX не должен показывать внутренние chain-of-thought. Показываются краткое обоснование, доказательства, ограничения и ссылки на источники.

## 10. Integrations MVP

- File intake: PDF, DOCX, Markdown, TXT, XLSX, CSV, images; OpenAPI/Swagger import.
- GitHub/GitLab read-only для выбранных repositories; ограниченный polling/sync, checkpoint, pagination, deduplication, rate limits и webhook signature/replay validation если webhooks включены.
- Connector Registry + Adapter + Gateway + External Object Mapping; Source/SourceVersion остаются canonical provenance.
- Jira/Confluence/SharePoint, outbound writes и bidirectional sync — post-MVP.
- Интеграция не становится источником истины для требований AI RES без явной ownership/mapping policy.

## 11. Security baseline

- Security controls SEC-001..SEC-0xx P0 применяются как mandatory MVP controls; object-level authorization, project/tenant isolation, scoped WorkerRun grants, tool authorization, secret isolation, prompt-injection defense, audit and secure file intake обязательны.
- Local Authentication MVP; Argon2id password hashing; server-side opaque sessions; HttpOnly/Secure/SameSite cookies; CSRF for state-changing requests; MFA for privileged admin in production-like profile; OIDC Authorization Code + PKCE later.
- PostgreSQL least-privilege identities, RLS defense-in-depth, no runtime DDL/owner/superuser/BYPASSRLS; Manager/Worker Runtime без прямых DB credentials.
- SOPS/age for encrypted-at-rest configuration in repository + Docker Compose secrets at runtime; age private key out-of-band. Future Vault/Secret Manager adapter.
- No secrets/prompts/raw documents in logs/traces/Temporal history by default. Egress allowlist; non-root containers; no privileged mode/Docker socket.
- Security baseline does not equal penetration-test certification. Security test evidence is a release gate.

## 12. Performance, retention и эксплуатация

- Не назначать неподтверждённые численные SLO/throughput/concurrency. Утвердить метод измерения и capacity test scenarios; thresholds задаются после representative load tests.
- RPO ≤1h / RTO ≤4h остаются provisional objectives до restore rehearsal.
- Retention разделяется для domain events, audit, telemetry, source files, embeddings/index generations, sessions, idempotency, inbox/outbox и backups. До утверждения legal/data retention policy не выполнять автоматическое destructive purge.
- Observability: OpenTelemetry + Collector, Prometheus, Grafana, Loki, Tempo, Alertmanager; Langfuse optional profile with content capture disabled by default.
- Telemetry may fail-open with bounded buffers; audit for protected mutations is durable/fail-closed.

## 13. Out of scope MVP

GraphRAG/graph DB, separate vector DB, multi-agent swarm, direct A2A, fine-tuning, self-modifying agents, automatic tool/code generation, arbitrary external writes, bidirectional sync, SaaS multi-tenancy, Kubernetes production topology, universal multimodality, autonomous A3/A4.

## 14. Решения, требующие runtime evidence, а не дальнейшего проектного угадывания

- Bifrost PoC/security acceptance.
- Embedding model choice and retrieval benchmark.
- Numeric latency/cost/capacity targets.
- Backup restore and RPO/RTO drills.
- RLS/tenant isolation and credential rotation tests.
- Model quality thresholds by task class.
- Retention periods/legal hold schedule.
- User guide screenshots and accessibility validation after UI release.

## 15. Критерий архитектурного завершения

Architecture baseline is complete when each in-scope capability has: owner, domain object, lifecycle, API/event contract or explicit no-API boundary, authorization boundary, evidence/provenance, failure/recovery semantics, acceptance tests, MVP/post-MVP scope, and traceability to requirements. Runtime readiness is a separate gate.
