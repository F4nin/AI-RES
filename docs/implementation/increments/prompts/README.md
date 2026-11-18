# Execution Prompts — индекс

Один этап — один самостоятельный промпт. Источник последовательности: `docs/implementation/IMPLEMENTATION_ROADMAP.md` (ADR-010). Общий шаблон отчёта: `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`; отчёт этапа — `docs/implementation/increments/<ID>_<slug>_REPORT.md`.

**Групповой режим (ADR-124/127):** [карта G01–G08](../../DEVELOPMENT_GROUPS.md) объединяет этапы для поручения и непрерывного выполнения. Градация S00–S39 и все промпты ниже сохраняются. Явное поручение на группу заменяет повторные поручения на входящие Sxx; внешние зависимости требуют DONE перед соответствующим Sxx, внутренние реализуются в общей ветке в порядке DAG, затем выполняются общая отладка/проверки/review и один PR. Отдельный полный pre-pr/CI/merge каждого Sxx перед следующим не требуется; финальные gates и статусы всех Sxx сохраняются. Блокирующие owner-решения не обходятся. Группа не меняет готовность этапов, SLICE-01/owner gates и не запускается документированием карты.

Статусы готовности: **READY** — необходимые предпосылки выполнены, но для реализации всё равно нужно поручение владельца; **PENDING_DEPS** — промпт готов, ждёт DONE зависимостей; **BLOCKED** — требует решения владельца (DECISIONS_PENDING.md); **BLOCKED (транзитивно)** — зависит от BLOCKED этапа; **DONE** — этап завершён (статус реализации и evidence см. в `IMPLEMENTATION_STATUS.md`).

| ID | Название | Промпт | Зависимости | Статус готовности | Разрешено начинать |
|---|---|---|---|---|---|
| S00 | Repository reconnaissance и baseline manifest | [`S00_repository_reconnaissance.md`](S00_repository_reconnaissance.md) | — | DONE | — |
| S01 | Contract toolchain и CI-валидация контрактов | [`S01_contract_toolchain.md`](S01_contract_toolchain.md) | S00 | DONE | — |
| S02 | Backend skeleton и platform primitives (без БД) | [`S02_backend_skeleton_platform_primitives.md`](S02_backend_skeleton_platform_primitives.md) | S01 | DONE | — |
| S03 | Local infrastructure (Docker Compose), secrets и CI baseline | [`S03_local_infrastructure_secrets_ci.md`](S03_local_infrastructure_secrets_ci.md) | S02 | DONE | — |
| S04 | Persistence foundation: Alembic, schemas, роли | [`S04_persistence_foundation.md`](S04_persistence_foundation.md) | S03 | DONE | — |
| S05 | Core tenant и execution schema + RLS | [`S05_core_tenant_execution_schema_rls.md`](S05_core_tenant_execution_schema_rls.md) | S04 | DONE | — |
| S06 | Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules | [`S06_domain_content_schema.md`](S06_domain_content_schema.md) | S05 | DONE | — |
| S07 | Identity, Local Auth, Policy Engine, Audit, Idempotency | [`S07_identity_auth_policy_audit_idempotency.md`](S07_identity_auth_policy_audit_idempotency.md) | S05 | DONE | — |
| S08 | Read-only API vertical slices | [`S08_read_only_api_slices.md`](S08_read_only_api_slices.md) | S06, S07 | DONE | — |
| S09 | Controlled write commands | [`S09_controlled_write_commands.md`](S09_controlled_write_commands.md) | S08 | DONE | — |
| S10 | Outbox dispatcher, Inbox и CloudEvents | [`S10_outbox_dispatcher_inbox_cloudevents.md`](S10_outbox_dispatcher_inbox_cloudevents.md) | S09 | DONE | — |
| S11 | Temporal foundation и dispatch Operation | [`S11_temporal_foundation_operation_dispatch.md`](S11_temporal_foundation_operation_dispatch.md) | S10 | DONE | — |
| S12 | Operation API, process primitives, cancellation, SSE | [`S12_operation_api_process_primitives_sse.md`](S12_operation_api_process_primitives_sse.md) | S11 | DONE | — |
| S13 | Observability stack и мониторинг | [`S13_observability_stack.md`](S13_observability_stack.md) | S03, S10 | DONE | — |
| S14 | Worker contracts: Envelope/Result/Notice | [`S14_worker_contracts_runtime_validation.md`](S14_worker_contracts_runtime_validation.md) | S12 | DONE | — |
| S15 | LLMGatewayPort и Model Registry (провайдер-нейтрально) | [`S15_llm_gateway_port_model_registry.md`](S15_llm_gateway_port_model_registry.md) | S11 | DONE | — |
| S16 | LLM Gateway: технический механизм подключения провайдеров | [`S16_bifrost_poc_provider_profile.md`](S16_bifrost_poc_provider_profile.md) | S15, S13 | DONE по решению владельца2026-11-17, ADR-123; технический срез TESTED local+Linux, PR #28 MERGED | Real-provider admission NOT VERIFIED/BLOCKED; исходные live/approval gates отложены, report§17. Не повторять закрытый milestone |
| S17 | Tool Registry и Tool Gateway | [`S17_tool_registry_tool_gateway.md`](S17_tool_registry_tool_gateway.md) | S07, S12 | PENDING_DEPS: SLICE-01 (ADR115); ARCH-01 DONE | Нет; G02 готовит G156, см. [паспорт](../../groups/G02_WORK.md) |
| S18 | Rules Registry и Rules Engine | [`S18_rules_registry_rules_engine.md`](S18_rules_registry_rules_engine.md) | S07, S06 | DONE | — (PR33, отчёт S18) |
| S19 | ContextPackageVersion (минимальный Context Builder) | [`S19_context_package_versioning.md`](S19_context_package_versioning.md) | S06, S07 | DONE | VERIFIED; PR31 MERGED99e5ec1, local/Linux/post-merge PASS; G01 далее S18 |
| S20 | Project/Epic intake и Manager interaction | [`S20_project_epic_intake_manager.md`](S20_project_epic_intake_manager.md) | S12, S15, S19 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S21 | Plan & Task orchestration | [`S21_plan_task_orchestration.md`](S21_plan_task_orchestration.md) | S20 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S22 | Readiness Gate | [`S22_readiness_gate.md`](S22_readiness_gate.md) | S14, S17, S18, S19, S21 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S23 | WorkerRun lifecycle и LangGraph runtime | [`S23_worker_run_lifecycle_langgraph.md`](S23_worker_run_lifecycle_langgraph.md) | S22, S15 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S24 | Manager–Worker coordination | [`S24_manager_worker_coordination.md`](S24_manager_worker_coordination.md) | S23 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S25 | Independent QA и rework | [`S25_independent_qa_rework.md`](S25_independent_qa_rework.md) | S24 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S26 | Requirements lifecycle, approvals, decisions & uncertainty | [`S26_requirements_lifecycle_approvals_decisions.md`](S26_requirements_lifecycle_approvals_decisions.md) | S25 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S27 | Knowledge ingestion и indexing | [`S27_knowledge_ingestion_indexing.md`](S27_knowledge_ingestion_indexing.md) | S12, S15 | READY (embeddings — после OD-01) | После поручения владельца |
| S28 | Retrieval API и полный Context Builder | [`S28_retrieval_api_context_builder.md`](S28_retrieval_api_context_builder.md) | S27, S19 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S29 | Connector MVP (read-only) | [`S29_connector_mvp_read_only.md`](S29_connector_mvp_read_only.md) | S27, S17 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S30 | Source change, traceability и Impact Assessment | [`S30_source_change_traceability_impact.md`](S30_source_change_traceability_impact.md) | S28, S29, S25 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S31 | Artifact, Change Request и Baseline lifecycle | [`S31_artifact_cr_baseline_lifecycle.md`](S31_artifact_cr_baseline_lifecycle.md) | S30, S26 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S32 | Recovery и reconciliation | [`S32_recovery_reconciliation.md`](S32_recovery_reconciliation.md) | S31 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S33 | Evaluation harness и release gates | [`S33_evaluation_harness_release_gates.md`](S33_evaluation_harness_release_gates.md) | S32, S16 | BLOCKED | Нет |
| S34 | Learning signals и curated experience | [`S34_learning_signals_curated_experience.md`](S34_learning_signals_curated_experience.md) | S33 | BLOCKED (S33 и допуск реального профиля OD-01/21; технический S16 DONE) | Нет |
| S35 | Web Project Workspace UI: foundation | [`S35_web_workspace_ui_foundation.md`](S35_web_workspace_ui_foundation.md) | S12 | READY | После поручения владельца |
| S36 | Web Workspace UI: Manager, plan, results, traceability, artifacts | [`S36_web_workspace_ui_manager_results.md`](S36_web_workspace_ui_manager_results.md) | S35, S31 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S37 | Contract & security verification, hardening | [`S37_contract_security_verification_hardening.md`](S37_contract_security_verification_hardening.md) | S32, S36, S16 | BLOCKED (зависимости и real-provider/security acceptance OD-01/21; технический S16 DONE) | Нет |
| S38 | Performance, capacity и resilience drills | [`S38_performance_capacity_resilience_drills.md`](S38_performance_capacity_resilience_drills.md) | S37 | BLOCKED | Нет |
| S39 | UI/UX acceptance, runbooks и productization | [`S39_ui_ux_acceptance_runbooks_productization.md`](S39_ui_ux_acceptance_runbooks_productization.md) | S37, S36 | BLOCKED (S37/S36 и допуск реального профиля; технический S16 DONE) | Нет |

При изменении статуса этапа сверять индекс с `IMPLEMENTATION_STATUS.md`. `READY` означает выполненные предпосылки, но не заменяет явное поручение владельца на реализацию. Для ещё не начатого этапа отдельно проверять зависимости и решения владельца.

## Мини-этапы вне нумерации S

| ID | Промпт | Зависимости / порядок | Готовность |
|---|---|---|---|
| ARCH-01 | [Контракты доменных импортов](ARCH-01_domain_import_contracts.md) | CI-01 DONE; до S17, ADR-114/120 | DONE (VERIFIED, PR #23); см. STATUS/report |
| DEP-01 | [Renovate dependency updates](DEP-01_renovate_dependency_updates.md) | CI-01 DONE, выбран владельцем 2026-11-17; ADR-113/121 | DONE по решению владельца; config VERIFIED (PR #25); App evidence NOT VERIFIED вынесено в follow-up G-31; см. STATUS |

Перечень остальных принятых мини-этапов и их текущие статусы — в STATUS и ADR-112…116. Эта запись не устанавливает новый порядок между ними.

### G156: продолжение подготовки2026-11-18

[Admission lifecycle fence](G02_admission_lifecycle_fence.md), ADR138: локально
TESTED, PG111PASS/fast1419PASS/contracts22PASS, два independent APPROVE.
[Отчёт](../G02_admission_lifecycle_fence_REPORT.md). Новая команда сняла прежнюю
остановку только для подготовки; owner lifecycle/product wiring и общие
final/live/human/SLICE gates остаются, G02 NOT_STARTED.

[Development host](G02_candidate_development_host.md), ADR136: локально TESTED offline host/claim/resource slice; [отчёт](../G02_candidate_development_host_REPORT.md). Actual effective config/topology и прочие G156/live/human/SLICE gates незавершены; S17/S20/S21 и G02 NOT_STARTED до нового явного согласия после завершения подготовки.

[Изолированный запуск и effective config audit](G02_bifrost_effective_isolation_audit.md): native6PASS, отдельный Mounts-order fix локально TESTED; воспроизведена admin mutation live/SQLite при unchanged file/inspect. [Отчёт](../G02_bifrost_effective_isolation_REPORT.md). Effective-integrity enforcement остаётся следующим preparatory seam до key/live; не старт G02.

[Candidate configuration integrity](G02_candidate_configuration_integrity.md), ADR137: локально TESTED, newnative12PASS/legacy65PASS/Go8+42normal+race/fast1419; [отчёт](../G02_candidate_configuration_integrity_REPORT.md). После документирования — остановка по команде владельца до новойзадачи; G02 NOT_STARTED, остальные G156/live/human/SLICE gates не сняты.

### G156: authenticated owner-review preparation2026-11-18

[Scope](G02_owner_review_binding.md), [ADR139](../../decisions/ADR-139-authenticated-owner-review.md):
локально TESTED material prepare/revalidate, без human approval/lifecycle DML.
Следующий preparatory seam — narrowly privileged operator executor/global audit,
затем observed gateway. G156 IN_PROGRESS, G02/S17/S20/S21 NOT_STARTED.

### G156: завершение MVP-допуска2026-11-18

[ADR140 operator scope](G02_identity_admission_operator.md),
[report](../G02_identity_admission_operator_REPORT.md): локально TESTED operator,
minimal existing candidate launch готов. По уточнению владельца закончить конечный
MVP-допуск с необходимыми проверками, затем вернуться к группам; текущий report
не новая остановка. Finalchecks/CI/guardedsetup→realcandidatecases→humanacceptance,
productintegration/SLICE со своими gates. G02/S17/S20/S21 NOT_STARTED.
