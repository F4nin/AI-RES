# AI RES — Требования к отказоустойчивости и восстановлению

**Версия:** 1.0 | **Статус:** WORKING | **Этап:** 15

## 1. Требования

### REL-001 — Durable workflow
Долгие процессы MUST сохранять состояние в Temporal и восстанавливаться после перезапуска Manager/Worker Runtime без потери canonical domain state.

### REL-002 — Разделение источников истины
Domain state, Temporal execution state, object storage и telemetry MUST иметь явные границы ответственности. Ни один telemetry/cache store не является источником истины.

### REL-003 — Bounded retries
Каждая retryable operation MUST иметь ограничение attempts, timeout, backoff/jitter и классификацию ошибок. Permanent/policy errors не повторяются автоматически.

### REL-004 — Cancellation propagation
Cancellation MUST распространяться на Worker/LLM/tool execution, насколько это поддерживают зависимости; поздние результаты отменённого Run не должны незаметно менять доменное состояние.

### REL-005 — Idempotent Activities
Каждая mutating Temporal Activity MUST иметь idempotency strategy, deduplication key или reconciliation procedure.

### REL-006 — External side effects
Для external APIs exactly-once не гарантируется. Connector MUST поддерживать idempotency key/stable external ID либо reconciliation и outcome-unknown handling.

### REL-007 — Transactional event consistency
Domain mutation and event publication MUST use transactional outbox or equivalent consistency mechanism where asynchronous events are required.

### REL-008 — Circuit breaker
Внешние providers/connectors с повторяющейся деградацией MUST иметь bounded circuit-breaker behavior or equivalent admission control.

### REL-009 — Bulkheads
Worker execution, ingestion, evaluation and API/control plane MUST have resource/concurrency isolation to limit blast radius.

### REL-010 — Graceful degradation
Отказ optional Redis, Langfuse or telemetry backend MUST NOT stop core business workflow, subject to audit/security requirements.

### REL-011 — Audit fail-closed
Если обязательная запись Domain/Security Audit не может быть надёжно сохранена, защищённое доменное действие MUST NOT be committed.

### REL-012 — Storage dependency
Операции, требующие bytes из MinIO, MUST fail safely when object unavailable; metadata MUST NOT mark an object available before durable write confirmation.

### REL-013 — Temporal outage
При недоступности Temporal система MUST NOT сообщать, что длительная работа надёжно запущена, если workflow не принят durable engine.

### REL-014 — Provider outage
LLM provider outage MUST result in bounded retry, approved fallback or explicit waiting/blocked state. Privacy/locality/model policy MUST NOT be bypassed.

### REL-015 — Retry amplification control
Retries MUST consume shared budgets and respect provider rate limits; cascading retry storms MUST be prevented.

### REL-016 — Health/readiness
Instances MUST pass readiness checks before receiving traffic/polling work. Liveness and readiness are distinct.

### REL-017 — Recovery manifest
Recovery package MUST identify PostgreSQL PITR point, MinIO snapshot/version, release/config/ruleset versions and unfinished workflow reconciliation inputs.

### REL-018 — Independent backup domains
PostgreSQL and MinIO objects MUST be backed up independently and linked through Recovery Manifest. Backup copies for production On-prem MUST be independent of the primary host/storage failure domain.

### REL-019 — RPO/RTO targets
Current project targets RPO ≤ 1 hour and RTO ≤ 4 hours remain provisional targets from Infrastructure v1.4. They MUST be validated through restore drills and not represented as achieved guarantees before evidence exists.

### REL-020 — Recovery reconciliation
After restore, platform MUST reconcile Domain DB ↔ Temporal Workflows ↔ Worker Runs ↔ MinIO objects ↔ external side effects. Ambiguous states require operator/human decision.

### REL-021 — DR drills
Before production-like release, restore drills MUST measure actual RPO/RTO, data consistency, workflow recovery and external side-effect reconciliation.

### REL-022 — Single-node limitation
Documentation MUST clearly state that single-node Docker Compose MVP does not provide node-level HA. HA requires separate topology and failure-domain design.

### REL-023 — Rollback safety
Application rollback MUST account for DB schema compatibility, Temporal persistence compatibility, object versions and external side effects. DB migrations are not assumed reversible.

### REL-024 — Partial failure tests
Tests MUST cover API, Manager, Worker, Temporal, PostgreSQL, MinIO, LLM provider, connector, Redis optional profile, telemetry backend and disk pressure failures.

### REL-025 — Data integrity
Integrity checks MUST detect dangling object references, incomplete writes, duplicate side effects, inconsistent workflow/domain status and missing audit events.

### REL-026 — Recovery audit
Recovery, manual reconciliation, replay, compensation and operator override MUST be authorized and audited.

### REL-027 — Degraded mode visibility
UI/API MUST expose queued, throttled, blocked, degraded, waiting and recovery states with meaningful reason categories; no fabricated progress/ETA.

### REL-028 — Security boundary
Resilience mechanisms MUST NOT bypass ACL, policy, Readiness Gate, human approval or security controls during fallback/retry/recovery.

## 2. Открытые параметры
- Confirmed RPO/RTO after drills.
- Production backup destination and encryption/key recovery.
- HA topology and failover objectives.
- Provider fallback matrix and acceptable privacy/model changes.
- Retry/circuit-breaker values.
- Recovery reconciliation automation scope.
- Data integrity check cadence.

## 3. Acceptance criteria
- Worker/Manager restart recovery tested with Temporal.
- Duplicate Activity delivery does not duplicate domain/external side effects.
- Optional component failure does not break core path.
- Critical audit failure blocks protected mutations.
- Backup restore and cross-store reconciliation tested.
- Actual RPO/RTO recorded from drills.
- Single-node and production HA limitations clearly documented.
