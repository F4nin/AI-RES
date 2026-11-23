"""Cancellation request (Decision v1.6 §2.4; State Machine v1.2): request -> stop/cleanup -> reconciliation -> terminal.

HTTP 202 confirms only that the request was recorded. For an assigned Operation,
the durable Start admission and exact binding distinguish a pre-start cancel
from a request that the orchestrator must deliver and reconcile.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION, EventRef
from ai_res.modules.operations.repository import OperationRepository, OperationRow
from ai_res.modules.operations.state_machine import TERMINAL
from ai_res.orchestration.contracts import CANCEL_DESTINATION, EXECUTION_ASSIGNMENT_REF, workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.problems import ErrorCode, ProblemError

CANCELLED_BEFORE_START = "CANCELLED_BEFORE_START"


async def request_cancellation(session: AsyncSession, operation_id: UUID, *, actor_id: UUID, correlation_id: UUID) -> OperationRow:
    repo = OperationRepository(session)
    row = await repo.get(operation_id)
    if row is None:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
    if row.status in TERMINAL:
        raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Operation has already finished.")  # the real outcome wins; nothing is written
    if row.status == "CANCEL_REQUESTED":
        return row  # idempotent by state: the request is already recorded

    # Start admission and Run binding take a conflicting assignment lock and
    # inspect the Operation only after obtaining it. Keep that order on cancel.
    assignment = (await session.execute(text("""
        SELECT id,workflow_run_id,start_admitted,revoked_at,namespace FROM platform.operation_execution_assignments
        WHERE operation_id=:operation FOR SHARE
    """), {"operation": row.id})).one_or_none()
    if row.status == "ACCEPTED" and (
        assignment is None or (not assignment.start_admitted and assignment.workflow_run_id is None)
    ):
        spec = EventSpec(event_type="operation.cancelled", schema_version=1, actor_type="USER", actor_id=actor_id, correlation_id=correlation_id,
                         destinations=(DOMAIN_DESTINATION,), from_status="ACCEPTED", to_status="CANCELLED", reason_code=CANCELLED_BEFORE_START)
        await repo.transition(row, "CANCELLED", spec, cancel_requested_at=utc_now())
    else:
        if assignment is not None and (assignment.workflow_run_id is None or assignment.revoked_at is not None):
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Operation execution is not available for cancellation yet.")
        if row.status == "ACCEPTED":
            queued = EventSpec(event_type="operation.queued", schema_version=1, actor_type="SERVICE", correlation_id=correlation_id,
                               destinations=(DOMAIN_DESTINATION,), from_status="ACCEPTED", to_status="QUEUED")
            await repo.transition(row, "QUEUED", queued, workflow_id=workflow_id_for(row.id))
            row = await _read_operation(repo, row.id)
        refs = () if assignment is None else (EventRef(EXECUTION_ASSIGNMENT_REF, assignment.id, assignment.workflow_run_id),)
        spec = EventSpec(event_type="operation.cancel_requested", schema_version=1, actor_type="USER", actor_id=actor_id, correlation_id=correlation_id,
                         destinations=(DOMAIN_DESTINATION, CANCEL_DESTINATION), from_status=row.status, to_status="CANCEL_REQUESTED", refs=refs,
                         dispatch_namespace=None if assignment is None else assignment.namespace)
        await repo.transition(row, "CANCEL_REQUESTED", spec, cancel_requested_at=utc_now())
    return await _read_operation(repo, operation_id)


async def _read_operation(repo: OperationRepository, operation_id: UUID) -> OperationRow:
    reread = await repo.get(operation_id)
    if reread is None:
        raise ProblemError(ErrorCode.INTERNAL_ERROR, "Operation vanished inside its own transaction.")
    return reread
