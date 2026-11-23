"""Join a terminal observation to current domain facts under the execution locks."""
from enum import StrEnum
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.application.observe_operations import BoundExecutionObservationRequest
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.reconciliation import ExecutionState
from ai_res.modules.operations.repository import OperationRepository, OperationRow
from ai_res.modules.operations.state_machine import TERMINAL
from ai_res.orchestration.contracts import ASSIGNED_WORKFLOW_TYPES, CONTRACT_VERSION, MANAGER_TASK_QUEUE, workflow_id_for
from ai_res.platform.ports import AuditOutcome, AuditRecord

WORKFLOW_FAILURE_CODES = {
    ExecutionState.FAILED: "WORKFLOW_FAILED",
    ExecutionState.TIMED_OUT: "WORKFLOW_TIMED_OUT",
    ExecutionState.TERMINATED: "WORKFLOW_TERMINATED",
}
TERMINAL_EXECUTIONS = frozenset({*WORKFLOW_FAILURE_CODES, ExecutionState.COMPLETED, ExecutionState.CANCELLED})
POST_ACK_STATUSES = frozenset({"QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING", "CANCEL_REQUESTED"})


class EffectReconciliation(StrEnum):
    STALE = "STALE"
    DRAFT_COMMITTED = "DRAFT_COMMITTED"
    PLAN_MATERIALIZED = "PLAN_MATERIALIZED"
    DOMAIN_TERMINAL = "DOMAIN_TERMINAL"
    DOMAIN_OUTCOME_REQUIRED = "DOMAIN_OUTCOME_REQUIRED"
    CORRECTED = "CORRECTED"


async def reconcile_post_ack_effects(
    session: AsyncSession, request: BoundExecutionObservationRequest, expected_version: int, state: ExecutionState,
) -> EffectReconciliation:
    """Called in an exact tenant UoW after the observer RPC has completed."""
    if state not in TERMINAL_EXECUTIONS:
        return EffectReconciliation.STALE
    # Same lock order as private ar2. An Operation update lock fences task materialization, cancellation and new runs.
    correlation = (await session.execute(text("""
        SELECT correlation_id FROM platform.operation_execution_assignments
        WHERE id=:assignment AND operation_id=:operation AND workflow_id=:workflow AND workflow_run_id=:run
          AND namespace=:namespace AND workflow_type=:type AND task_queue=:queue AND workflow_contract_version=:major
          AND revoked_at IS NULL
        FOR SHARE
    """), {"assignment": request.assignment_id, "operation": request.operation_id, "workflow": workflow_id_for(request.operation_id),
           "run": request.workflow_run_id, "namespace": request.namespace, "type": request.workflow_type,
           "queue": MANAGER_TASK_QUEUE, "major": CONTRACT_VERSION})).scalar_one_or_none()
    if correlation is None:
        return EffectReconciliation.STALE
    metadata = (await session.execute(text("""
        SELECT started_at, result_ref->>'id' AS result_id FROM operations.operations
        WHERE id=:operation FOR UPDATE
    """), {"operation": request.operation_id})).one_or_none()
    repo = OperationRepository(session)
    row = await repo.get(request.operation_id)
    if (metadata is None or metadata.started_at is None or row is None
            or ASSIGNED_WORKFLOW_TYPES.get(row.operation_type) != request.workflow_type):
        return EffectReconciliation.STALE
    if row.status not in TERMINAL and (row.row_version != expected_version or row.status not in POST_ACK_STATUSES):
        return EffectReconciliation.STALE
    outcome = await _reconcile_current_effect(session, repo, row, correlation, metadata.result_id, state)
    if outcome in {EffectReconciliation.DOMAIN_OUTCOME_REQUIRED, EffectReconciliation.PLAN_MATERIALIZED}:
        observation_id = uuid5(row.id, f"post-ack:{request.assignment_id}:{request.workflow_run_id}:{row.row_version}:{state.value}:{outcome.value}")
        await SqlAuditWriter(session).write_once(AuditRecord(
            action="OPERATION_RECONCILIATION_REQUIRED", outcome=AuditOutcome.FAILED, resource_type="OPERATION",
            actor_type="SYSTEM", resource_id=str(row.id), organization_id=str(row.organization_id), project_id=str(row.project_id),
            request_id=str(correlation), reason_code=outcome.value,
            details={"observedStatus": state.value, "operationVersion": row.row_version},
        ), observation_id)
    return outcome


async def _reconcile_current_effect(
    session: AsyncSession, repo: OperationRepository, row: OperationRow, correlation: UUID, result_id: str | None, state: ExecutionState,
) -> EffectReconciliation:
    if row.status in TERMINAL:
        if row.operation_type == "MANAGER_MESSAGE" and row.status == "SUCCEEDED":
            verified = (await session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM work.manager_interactions i JOIN work.manager_proposal_versions p ON p.interaction_id=i.id
                    WHERE i.operation_id=:operation AND p.id::text=:result
                )
            """), {"operation": row.id, "result": result_id})).scalar_one()
            return EffectReconciliation.DRAFT_COMMITTED if verified else EffectReconciliation.DOMAIN_OUTCOME_REQUIRED
        return EffectReconciliation.DOMAIN_TERMINAL
    if row.operation_type != "PLAN_EXECUTION":
        # An absent Manager draft cannot prove that the external inference did not execute.
        return EffectReconciliation.DOMAIN_OUTCOME_REQUIRED

    plan = (await session.execute(text("""
        SELECT d.approved_items,
               ARRAY(SELECT m.item_id FROM work.plan_item_tasks m WHERE m.operation_id=e.operation_id) AS mapped,
               (SELECT count(*) FROM work.tasks t WHERE t.operation_id=e.operation_id) AS task_count,
               EXISTS (SELECT 1 FROM agents.worker_runs w WHERE w.operation_id=e.operation_id) AS has_runs,
               EXISTS (SELECT 1 FROM operations.operations c WHERE c.parent_operation_id=e.operation_id) AS has_children
        FROM work.plan_executions e
        JOIN governance.plan_version_decisions d ON (d.id,d.plan_version_id)=(e.decision_id,e.plan_version_id)
        JOIN operations.operations o ON o.id=e.operation_id
        WHERE e.operation_id=:operation AND d.decision='APPROVE'
          AND o.completion_policy_version='plan-approved-items/1'
          AND o.completion_policy_snapshot=jsonb_build_object('requiredPlanItems',to_jsonb(d.approved_items))
    """), {"operation": row.id})).one_or_none()
    if plan is None:
        return EffectReconciliation.DOMAIN_OUTCOME_REQUIRED
    if plan.task_count == len(plan.mapped) and set(plan.approved_items) == set(plan.mapped):
        return EffectReconciliation.PLAN_MATERIALIZED
    if plan.mapped or plan.task_count or plan.has_runs or plan.has_children:
        return EffectReconciliation.DOMAIN_OUTCOME_REQUIRED

    code = WORKFLOW_FAILURE_CODES.get(state)
    if code is not None and row.status in {"RUNNING", "CANCEL_REQUESTED"}:
        target, event = "FAILED", "operation.failed"
        changes = {"problem_ref": {"code": code}}
    elif state is ExecutionState.CANCELLED and row.status == "CANCEL_REQUESTED":
        target, event, code, changes = "CANCELLED", "operation.cancelled", "CANCELLATION_CONFIRMED", {}
    else:
        return EffectReconciliation.DOMAIN_OUTCOME_REQUIRED
    await repo.transition(row, target, EventSpec(event, 1, "SYSTEM", correlation, (DOMAIN_DESTINATION,),
                                                 from_status=row.status, to_status=target, reason_code=code), **changes)
    await SqlAuditWriter(session).write(AuditRecord(
        action="OPERATION_POST_ACK_RECONCILED", outcome=AuditOutcome.SUCCEEDED, resource_type="OPERATION",
        actor_type="SYSTEM", resource_id=str(row.id), organization_id=str(row.organization_id), project_id=str(row.project_id),
        request_id=str(correlation), reason_code=code, details={"observedStatus": state.value},
    ))
    return EffectReconciliation.CORRECTED
