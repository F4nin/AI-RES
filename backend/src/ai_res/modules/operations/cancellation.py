"""Cancellation request (Decision v1.6 §2.4; State Machine v1.2): request -> stop/cleanup -> reconciliation -> terminal.

HTTP 202 confirms only that the REQUEST was recorded. An Operation that never left ACCEPTED has nothing to stop and goes straight to CANCELLED; an active one
moves to CANCEL_REQUESTED and the cancel command is queued (Outbox) for the orchestrator, which reconciles and only then lets the domain say CANCELLED
(`OperationOrchestrationService.confirm_cancellation`). A terminal Operation is never reopened or overwritten: the real outcome wins over a late cancel.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.repository import OperationRepository, OperationRow
from ai_res.modules.operations.state_machine import TERMINAL
from ai_res.orchestration.contracts import CANCEL_DESTINATION
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
    if row.status == "ACCEPTED":
        spec = EventSpec(event_type="operation.cancelled", schema_version=1, actor_type="USER", actor_id=actor_id, correlation_id=correlation_id,
                         destinations=(DOMAIN_DESTINATION,), from_status="ACCEPTED", to_status="CANCELLED", reason_code=CANCELLED_BEFORE_START)
        await repo.transition(row, "CANCELLED", spec, cancel_requested_at=utc_now())
    else:
        spec = EventSpec(event_type="operation.cancel_requested", schema_version=1, actor_type="USER", actor_id=actor_id, correlation_id=correlation_id,
                         destinations=(DOMAIN_DESTINATION, CANCEL_DESTINATION), from_status=row.status, to_status="CANCEL_REQUESTED")
        await repo.transition(row, "CANCEL_REQUESTED", spec, cancel_requested_at=utc_now())
    reread = await repo.get(operation_id)
    if reread is None:
        raise ProblemError(ErrorCode.INTERNAL_ERROR, "Operation vanished inside its own transaction.")
    return reread
