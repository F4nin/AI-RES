# Execution Prompts — индекс

Один этап — один самостоятельный промпт. Источник последовательности: `docs/implementation/IMPLEMENTATION_ROADMAP.md` (ADR-010). Общий шаблон отчёта: `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`; отчёт этапа — `docs/implementation/increments/<ID>_<slug>_REPORT.md`.

Статусы готовности: **READY** — можно исполнять сейчас; **PENDING_DEPS** — промпт готов, ждёт DONE зависимостей; **BLOCKED** — требует решения владельца (DECISIONS_PENDING.md); **BLOCKED (транзитивно)** — зависит от BLOCKED этапа; **DONE** — выполнен.

| ID | Название | Промпт | Зависимости | Статус готовности | Разрешено начинать |
|---|---|---|---|---|---|
| S00 | Repository reconnaissance и baseline manifest | [`S00_repository_reconnaissance.md`](S00_repository_reconnaissance.md) | — | DONE | — |
| S01 | Contract toolchain и CI-валидация контрактов | [`S01_contract_toolchain.md`](S01_contract_toolchain.md) | S00 | DONE | — |
| S02 | Backend skeleton и platform primitives (без БД) | [`S02_backend_skeleton_platform_primitives.md`](S02_backend_skeleton_platform_primitives.md) | S01 | DONE | — |
| S03 | Local infrastructure (Docker Compose), secrets и CI baseline | [`S03_local_infrastructure_secrets_ci.md`](S03_local_infrastructure_secrets_ci.md) | S02 | DONE | — |
| S04 | Persistence foundation: Alembic, schemas, роли | [`S04_persistence_foundation.md`](S04_persistence_foundation.md) | S03 | DONE | — |
| S05 | Core tenant и execution schema + RLS | [`S05_core_tenant_execution_schema_rls.md`](S05_core_tenant_execution_schema_rls.md) | S04 | READY | **Да** |
| S06 | Domain content schema: requirements, sources, artifacts, context, decisions, traceability, rules | [`S06_domain_content_schema.md`](S06_domain_content_schema.md) | S05 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S07 | Identity, Local Auth, Policy Engine, Audit, Idempotency | [`S07_identity_auth_policy_audit_idempotency.md`](S07_identity_auth_policy_audit_idempotency.md) | S05 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S08 | Read-only API vertical slices | [`S08_read_only_api_slices.md`](S08_read_only_api_slices.md) | S06, S07 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S09 | Controlled write commands | [`S09_controlled_write_commands.md`](S09_controlled_write_commands.md) | S08 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S10 | Outbox dispatcher, Inbox и CloudEvents | [`S10_outbox_dispatcher_inbox_cloudevents.md`](S10_outbox_dispatcher_inbox_cloudevents.md) | S09 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S11 | Temporal foundation и dispatch Operation | [`S11_temporal_foundation_operation_dispatch.md`](S11_temporal_foundation_operation_dispatch.md) | S10 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S12 | Operation API, process primitives, cancellation, SSE | [`S12_operation_api_process_primitives_sse.md`](S12_operation_api_process_primitives_sse.md) | S11 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S13 | Observability stack и мониторинг | [`S13_observability_stack.md`](S13_observability_stack.md) | S03, S10 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S14 | Worker contracts: Envelope/Result/Notice | [`S14_worker_contracts_runtime_validation.md`](S14_worker_contracts_runtime_validation.md) | S12 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S15 | LLMGatewayPort и Model Registry (провайдер-нейтрально) | [`S15_llm_gateway_port_model_registry.md`](S15_llm_gateway_port_model_registry.md) | S11 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S16 | Bifrost PoC и первый утверждённый provider profile | [`S16_bifrost_poc_provider_profile.md`](S16_bifrost_poc_provider_profile.md) | S15, S13 | BLOCKED | Нет |
| S17 | Tool Registry и Tool Gateway | [`S17_tool_registry_tool_gateway.md`](S17_tool_registry_tool_gateway.md) | S07, S12 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S18 | Rules Registry и Rules Engine | [`S18_rules_registry_rules_engine.md`](S18_rules_registry_rules_engine.md) | S07, S06 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S19 | ContextPackageVersion (минимальный Context Builder) | [`S19_context_package_versioning.md`](S19_context_package_versioning.md) | S06, S07 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S20 | Project/Epic intake и Manager interaction | [`S20_project_epic_intake_manager.md`](S20_project_epic_intake_manager.md) | S12, S15, S19 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S21 | Plan & Task orchestration | [`S21_plan_task_orchestration.md`](S21_plan_task_orchestration.md) | S20 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S22 | Readiness Gate | [`S22_readiness_gate.md`](S22_readiness_gate.md) | S14, S17, S18, S19, S21 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S23 | WorkerRun lifecycle и LangGraph runtime | [`S23_worker_run_lifecycle_langgraph.md`](S23_worker_run_lifecycle_langgraph.md) | S22, S15 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S24 | Manager–Worker coordination | [`S24_manager_worker_coordination.md`](S24_manager_worker_coordination.md) | S23 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S25 | Independent QA и rework | [`S25_independent_qa_rework.md`](S25_independent_qa_rework.md) | S24 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S26 | Requirements lifecycle, approvals, decisions & uncertainty | [`S26_requirements_lifecycle_approvals_decisions.md`](S26_requirements_lifecycle_approvals_decisions.md) | S25 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S27 | Knowledge ingestion и indexing | [`S27_knowledge_ingestion_indexing.md`](S27_knowledge_ingestion_indexing.md) | S12, S15 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S28 | Retrieval API и полный Context Builder | [`S28_retrieval_api_context_builder.md`](S28_retrieval_api_context_builder.md) | S27, S19 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S29 | Connector MVP (read-only) | [`S29_connector_mvp_read_only.md`](S29_connector_mvp_read_only.md) | S27, S17 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S30 | Source change, traceability и Impact Assessment | [`S30_source_change_traceability_impact.md`](S30_source_change_traceability_impact.md) | S28, S29, S25 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S31 | Artifact, Change Request и Baseline lifecycle | [`S31_artifact_cr_baseline_lifecycle.md`](S31_artifact_cr_baseline_lifecycle.md) | S30, S26 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S32 | Recovery и reconciliation | [`S32_recovery_reconciliation.md`](S32_recovery_reconciliation.md) | S31 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S33 | Evaluation harness и release gates | [`S33_evaluation_harness_release_gates.md`](S33_evaluation_harness_release_gates.md) | S32, S16 | BLOCKED | Нет |
| S34 | Learning signals и curated experience | [`S34_learning_signals_curated_experience.md`](S34_learning_signals_curated_experience.md) | S33 | BLOCKED (транзитивно: S16, S33) | Нет |
| S35 | Web Project Workspace UI: foundation | [`S35_web_workspace_ui_foundation.md`](S35_web_workspace_ui_foundation.md) | S12 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S36 | Web Workspace UI: Manager, plan, results, traceability, artifacts | [`S36_web_workspace_ui_manager_results.md`](S36_web_workspace_ui_manager_results.md) | S35, S31 | PENDING_DEPS | Нет (после DONE зависимостей) |
| S37 | Contract & security verification, hardening | [`S37_contract_security_verification_hardening.md`](S37_contract_security_verification_hardening.md) | S32, S36, S16 | BLOCKED (транзитивно: S16) | Нет |
| S38 | Performance, capacity и resilience drills | [`S38_performance_capacity_resilience_drills.md`](S38_performance_capacity_resilience_drills.md) | S37 | BLOCKED | Нет |
| S39 | UI/UX acceptance, runbooks и productization | [`S39_ui_ux_acceptance_runbooks_productization.md`](S39_ui_ux_acceptance_runbooks_productization.md) | S37, S36 | BLOCKED (транзитивно: S16) | Нет |

Обновлять при изменении статуса этапа (вместе с `IMPLEMENTATION_STATUS.md`).
