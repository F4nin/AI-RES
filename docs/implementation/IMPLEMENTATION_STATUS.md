# IMPLEMENTATION_STATUS

**Обновлено:** 2026-11-11 (S04 VERIFIED (локально); S03 VERIFIED; подготовительная фаза — `reviews/PREP_PHASE_REPORT.md`)

Статусы реализации: NOT_STARTED · IN_PROGRESS · IMPLEMENTED · TESTED · VERIFIED · BLOCKED · DEFERRED. IMPLEMENTED ≠ TESTED ≠ VERIFIED. DONE (для старта зависимых этапов) — по ADR-032.

| ID | Этап | Статус реализации | Готовность / примечание | Отчёт |
|---|---|---|---|---|
| S00 | Repository reconnaissance и baseline manifest | IMPLEMENTED (static evidence) | Воспроизводимость проверок — в S01 | [report](increments/S00_repository_reconnaissance_REPORT.md) |
| S01 | Contract toolchain и CI-валидация контрактов | VERIFIED (G-20, G-21 открыты) | DONE | [report](increments/S01_contract_toolchain_REPORT.md) |
| S02 | Backend skeleton и platform primitives (без БД) | VERIFIED (56 тестов; 2 прохода review; G-22 открыт) | DONE | [report](increments/S02_backend_skeleton_platform_primitives_REPORT.md) |
| S03 | Local infrastructure (Docker Compose), secrets и CI baseline | VERIFIED (локально и на GitHub Actions Linux, 2026-11-11): runtime 81 + статика 76, backend 58, contracts 19; повторное независимое review (security, silent-failure) — 0 открытых HIGH/CRITICAL; CI на Linux зелёный (G-27 закрыт, runs 42980598813, 42980597940) | DONE (ADR-032); слой 4 ADR-037 (security owner) — на S37 | [report](increments/S03_local_infrastructure_secrets_ci_REPORT.md) |
| S04 | Persistence foundation: Alembic, schemas, роли | VERIFIED (локально, 2026-11-11): backend 159 (unit 72 + arch 3 + PostgreSQL 16 integration 84), runtime 95, infra static 77, contracts 19; независимое review (4 агента) — 0 HIGH/CRITICAL; GitHub Actions на Linux зелёный (2026-11-11, PR #2: ci 42989650789, contracts 42989650777; G-43 в части Linux-CI закрыт) | DONE (ADR-032) | [report](increments/S04_persistence_foundation_REPORT.md) |
| S05 | Core tenant и execution schema + RLS | VERIFIED по решению владельца (2026-11-11; локально: backend 297 passed, три раунда review; ветка `feat/s05-core-tenant-execution-schema-rls`). GitHub Actions на Linux зелёный (2026-11-11, PR #3, коммит 1cb09dc: ci 43029221024 и 43029232241 (повторный прогон), contracts 43029220792 и 43029232542; backend, infra-static, infra-runtime — success); дельта третьего раунда отдельным агентом не пересматривалась (отчёт §11) | READY (S04 DONE) | — |
| S06 | Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules | NOT_STARTED | PENDING_DEPS | — |
| S07 | Identity, Local Auth, Policy Engine, Audit, Idempotency | NOT_STARTED | PENDING_DEPS | — |
| S08 | Read-only API vertical slices | NOT_STARTED | PENDING_DEPS | — |
| S09 | Controlled write commands | NOT_STARTED | PENDING_DEPS | — |
| S10 | Outbox dispatcher, Inbox и CloudEvents | NOT_STARTED | PENDING_DEPS | — |
| S11 | Temporal foundation и dispatch Operation | NOT_STARTED | PENDING_DEPS | — |
| S12 | Operation API, process primitives, cancellation, SSE | NOT_STARTED | PENDING_DEPS | — |
| S13 | Observability stack и мониторинг | NOT_STARTED | PENDING_DEPS | — |
| S14 | Worker contracts: Envelope/Result/Notice | NOT_STARTED | PENDING_DEPS | — |
| S15 | LLMGatewayPort и Model Registry (провайдер-нейтрально) | NOT_STARTED | PENDING_DEPS | — |
| S16 | Bifrost PoC и первый утверждённый provider profile | BLOCKED | BLOCKED | — |
| S17 | Tool Registry и Tool Gateway | NOT_STARTED | PENDING_DEPS | — |
| S18 | Rules Registry и Rules Engine | NOT_STARTED | PENDING_DEPS | — |
| S19 | ContextPackageVersion (минимальный Context Builder) | NOT_STARTED | PENDING_DEPS | — |
| S20 | Project/Epic intake и Manager interaction | NOT_STARTED | PENDING_DEPS | — |
| S21 | Plan & Task orchestration | NOT_STARTED | PENDING_DEPS | — |
| S22 | Readiness Gate | NOT_STARTED | PENDING_DEPS | — |
| S23 | WorkerRun lifecycle и LangGraph runtime | NOT_STARTED | PENDING_DEPS | — |
| S24 | Manager–Worker coordination | NOT_STARTED | PENDING_DEPS | — |
| S25 | Independent QA и rework | NOT_STARTED | PENDING_DEPS | — |
| S26 | Requirements lifecycle, approvals, decisions & uncertainty | NOT_STARTED | PENDING_DEPS | — |
| S27 | Knowledge ingestion и indexing | NOT_STARTED | PENDING_DEPS | — |
| S28 | Retrieval API и полный Context Builder | NOT_STARTED | PENDING_DEPS | — |
| S29 | Connector MVP (read-only) | NOT_STARTED | PENDING_DEPS | — |
| S30 | Source change, traceability и Impact Assessment | NOT_STARTED | PENDING_DEPS | — |
| S31 | Artifact, Change Request и Baseline lifecycle | NOT_STARTED | PENDING_DEPS | — |
| S32 | Recovery и reconciliation | NOT_STARTED | PENDING_DEPS | — |
| S33 | Evaluation harness и release gates | BLOCKED | BLOCKED | — |
| S34 | Learning signals и curated experience | BLOCKED | BLOCKED (транзитивно: S16, S33) | — |
| S35 | Web Project Workspace UI: foundation | NOT_STARTED | PENDING_DEPS | — |
| S36 | Web Workspace UI: Manager, plan, results, traceability, artifacts | NOT_STARTED | PENDING_DEPS | — |
| S37 | Contract & security verification, hardening | BLOCKED | BLOCKED (транзитивно: S16) | — |
| S38 | Performance, capacity и resilience drills | BLOCKED | BLOCKED | — |
| S39 | UI/UX acceptance, runbooks и productization | BLOCKED | BLOCKED (транзитивно: S16) | — |

## Компоненты runtime

| Компонент | Статус | Этап |
|---|---|---|
| Contract toolchain | VERIFIED | S01 |
| Backend API | NOT_STARTED | S02, S07–S12 |
| PostgreSQL `ai_res_db` (миграции, роли, RLS) | NOT_STARTED | S04–S06 |
| Docker Compose / secrets / CI | VERIFIED (локально и на GitHub Actions) | S03 |
| Outbox / Inbox | NOT_STARTED | S10 |
| Temporal, Manager Runtime, Worker Runtime | NOT_STARTED | S11, S20, S23 |
| LangGraph | NOT_STARTED | S23 |
| LLM Gateway (port / Bifrost) | NOT_STARTED / BLOCKED | S15 / S16 |
| Readiness Gate | NOT_STARTED | S22 |
| MinIO / ingestion / retrieval | NOT_STARTED | S03, S27, S28 |
| Observability stack | NOT_STARTED | S13 |
| Web Workspace UI | NOT_STARTED | S35–S36 |

**Runtime implementation: NOT VERIFIED.** Security / performance / production readiness: NOT APPROVED (Readiness Audit v2.2 §6).
