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
| S05 | Core tenant и execution schema + RLS | VERIFIED по решению владельца (2026-11-11; локально: backend 297 passed, три раунда review; ветка `feat/s05-core-tenant-execution-schema-rls`). GitHub Actions на Linux зелёный (2026-11-11, PR #3; финальный коммит 6716730: ci 43034572213 и 43034582085, backend/infra-static/infra-runtime/contracts — success; ранее на 1cb09dc: ci 43029221024 и 43029232241 (повторный прогон), contracts 43029220792 и 43029232542); дельта третьего раунда отдельным агентом не пересматривалась (отчёт §11) | READY (S04 DONE) | — |
| S06 | Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules | VERIFIED по решению владельца (2026-11-11; локально: backend 331, runtime 95, infra static 172, contracts 19; три review). GitHub Actions на Linux зелёный (2026-11-11, PR #5, коммит a7db82c: ci 43074829225 и 43074859429, contracts 43074829230 и 43074859545 — backend/infra-static/infra-runtime/contracts success). Дельта после review отдельным агентом не пересматривалась; открыты G-69…G-74, OD-14 | — | `increments/S06_domain_content_schema_REPORT.md`, `reviews/S06_REVIEWS.md` |
| S07 | Identity, Local Auth, Policy Engine, Audit, Idempotency | VERIFIED по решению владельца (2026-11-11/12; локально `make pre-pr` ok: backend 676, runtime 99, infra 185, contracts 22; два прохода независимого review (4 + 2 агента), CRITICAL/HIGH нет; GitHub Actions на Linux зелёный (2026-11-11, PR #6, коммит 86328e4: ci 43111752244 и 43111759690, contracts 43111752277 и 43111759762 — backend/infra-static/infra-runtime/contracts success; ранее на c8e9040: ci 43107954898 и 43107964966)). Решения владельца R01/R03/SEC-05/SEC-06 внедрены (ADR-071…073); открыты NCP-12 (PROPOSED), OD-15 (WORKING), G-75…G-83 | READY | — |
| S08 | Read-only API vertical slices | VERIFIED (2026-11-12; GitHub Actions на Linux зелёный, PR #7, коммит 588055d: ci 43186306478 и 43186313460, contracts 43186306145 и 43186313578 — backend/infra-static/infra-runtime/contracts success; первый прогон упал на дрейфе дайджеста `caddy:2.11.9`, пин обновлён). Локально `make pre-pr` exit 0: backend 872, contracts 22, infra 185, runtime 99; schemathesis 13; review 3 агента — CRITICAL 0, HIGH 1 исправлен, дельта не пересматривалась). Дельта review отдельным агентом не пересматривалась. Открыты G-84…G-90, OD-17 | READY | `increments/S08_read_only_api_slices_REPORT.md`, `reviews/S08_REVIEWS.md` |
| S09 | Controlled write commands | VERIFIED (2026-11-12; PR #8 `feat/s09-controlled-write-commands`, коммит cc26beb; `make pre-pr` ok: backend 924, infra static 186, runtime 99; GitHub Actions на Linux зелёный: ci 43203466196 и 43203684744, contracts 43203466171 и 43203684738 — backend/infra-static/infra-runtime/contracts success; независимое review 4 агента — 0 CRITICAL/HIGH; приём загрузки MinIO не проверен, G-92) | READY (S08 DONE) | `increments/S09_controlled_write_commands_REPORT.md` |
| S10 | Outbox dispatcher, Inbox и CloudEvents | VERIFIED (2026-11-12; ветка `feat/s10-outbox-dispatcher-inbox-cloudevents`; `make pre-pr` exit 0: backend 964, contracts 22, infra static 186, runtime 99; review 3 агента — CRITICAL/HIGH нет, замечания исправлены; дельта review отдельным агентом не пересматривалась; GitHub Actions на Linux зелёный (2026-11-12, PR #9, коммит 248cd08: ci 43220712053 и 43220722294, contracts 43220712147 и 43220722299 — backend/infra-static/infra-runtime/contracts success)). OD-13 решён (ADR-084); открыты G-98…G-103, NCP-13 | READY (S09 DONE) | `increments/S10_outbox_dispatcher_inbox_cloudevents_REPORT.md`, `reviews/S10_REVIEWS.md` |
| S11 | Temporal foundation и dispatch Operation | VERIFIED (2026-11-12; локально backend 1025, infra 207; Linux CI зелёный (PR #11, ci 43233885212/43233901267: backend, infra-runtime, infra-static, contracts — success; contracts 43233885308/43233901331); влит в `main`; G-104/G-107 открыты) | — | `increments/S11_temporal_foundation_operation_dispatch_REPORT.md` |
| S12 | Operation API, process primitives, cancellation, SSE | VERIFIED (2026-11-12; локально backend 1110; Linux CI зелёный (PR #13: ci 43260641203/43260655454, contracts 43260641383/43260655429; PR #14 с исправлениями review: ci 43270400409/43270476037, contracts 43270400514/43270475542 — backend, infra-runtime, infra-static, contracts success), влит в `main` (6ee65da, 397692e); два раунда независимого review: CRITICAL 0, HIGH 1 — G-117, reconciler до S23 по решению владельца, ADR-094) | [отчёт](increments/S12_operation_api_process_primitives_sse_REPORT.md) | [reviews](reviews/S12_REVIEWS.md) |
| S13 | Observability stack и мониторинг | VERIFIED (2026-11-13; локально: backend 1116, infra 305, runtime 148, contracts 22; Linux CI зелёный (PR #16: ci 43301634548/43301768127, contracts 43301634628/43301768417 — backend, infra-runtime, infra-static, contracts success); review: CRITICAL 1 и HIGH исправлены/вынесены владельцу, дельта исправлений отдельным агентом не пересматривалась) | [отчёт](increments/S13_observability_stack_REPORT.md) | [reviews](reviews/S13_REVIEWS.md) |
| S14 | Worker contracts: Envelope/Result/Notice | VERIFIED (2026-11-13; локально, одним `make pre-pr`: backend 1236, infra 307, runtime 148, contracts 22; Linux CI зелёный (PR #18: ci 43428029283/43428039248, contracts 43428029128/43428039135 — backend, infra-runtime, infra-static, contracts success); review: CRITICAL 0, HIGH 2 — 1 исправлен, 1 граница Gate; дельта исправлений и ADR-104 отдельным агентом не пересматривались) | [отчёт](increments/S14_worker_contracts_runtime_validation_REPORT.md) | [reviews](reviews/S14_REVIEWS.md) |
| S15 | LLMGatewayPort и Model Registry (провайдер-нейтрально) | TESTED (2026-11-13, локально: backend 1286 passed, contracts 22, import-linter 12 kept; остальные стадии `make pre-pr` — см. отчёт §9); Linux CI после PR; не VERIFIED. Качество вывода модели не проверялось (только deterministic test double, ADR-022), реального провайдера нет (S16, OD-01); review: CRITICAL 0, HIGH 5 исправлены, дельта отдельным агентом не пересматривалась | [отчёт](increments/S15_llm_gateway_port_model_registry_REPORT.md) | [reviews](reviews/S15_REVIEWS.md) |
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
| PostgreSQL `ai_res_db` (миграции, роли, RLS) | TESTED (S04–S06 схемы; репозитории частично) | S04–S06 |
| Docker Compose / secrets / CI | VERIFIED (локально и на GitHub Actions) | S03 |
| Outbox / Inbox | VERIFIED (dispatcher/consumer — библиотека + CLI; в стеке не запущен, G-98) | S10 |
| Temporal, Manager Runtime, Worker Runtime | VERIFIED (skeleton: старт, ack, fail-closed; WorkerRun — S23) | S11, S20, S23 |
| LangGraph | NOT_STARTED | S23 |
| LLM Gateway (port / Bifrost) | TESTED (port, реестр, test double; провайдера нет) / BLOCKED (Bifrost: OD-01) | S15 / S16 |
| Readiness Gate | NOT_STARTED | S22 |
| MinIO / ingestion / retrieval | NOT_STARTED | S03, S27, S28 |
| Observability stack | NOT_STARTED | S13 |
| Web Workspace UI | NOT_STARTED | S35–S36 |

**Runtime implementation: NOT VERIFIED.** Security / performance / production readiness: NOT APPROVED (Readiness Audit v2.2 §6).
