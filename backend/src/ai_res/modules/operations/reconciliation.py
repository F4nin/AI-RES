"""Decisions for G-107 based on current Operation, dispatch and verified Temporal facts."""
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ai_res.modules.operations.state_machine import TERMINAL, is_allowed


class DispatchState(StrEnum):
    MISSING = "MISSING"
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    QUARANTINED = "QUARANTINED"


class ExecutionState(StrEnum):
    ABSENT = "ABSENT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    TERMINATED = "TERMINATED"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"


class ReconciliationAction(StrEnum):
    KEEP = "KEEP"
    RETRY_OBSERVATION = "RETRY_OBSERVATION"
    RETRY_DISPATCH = "RETRY_DISPATCH"
    RECORD_FAILURE = "RECORD_FAILURE"
    CONFIRM_CANCELLATION = "CONFIRM_CANCELLATION"
    REQUIRE_DOMAIN_OUTCOME = "REQUIRE_DOMAIN_OUTCOME"
    INVESTIGATE = "INVESTIGATE"


@dataclass(frozen=True, slots=True)
class DispatchSnapshot:
    """Dispatch intent under the captured Operation version, independently authenticated."""
    operation_id: UUID
    operation_type: str
    row_version: int
    operation_status: str
    dispatch_state: DispatchState
    outbox_id: UUID | None
    assignment_id: UUID
    start_acknowledged: bool | None = None


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    """Observation returned by a purpose-bound Temporal read of the exact assignment."""
    assignment_id: UUID
    state: ExecutionState


_FAILED_EXECUTION = frozenset({ExecutionState.FAILED, ExecutionState.TIMED_OUT, ExecutionState.TERMINATED})


def decide_reconciliation(
    snapshot: DispatchSnapshot,
    execution: ExecutionObservation,
    *,
    admitted_types: frozenset[str],
) -> ReconciliationAction:
    """Pure decision. An application applier must repeat assignment and row version checks before any action."""
    if snapshot.operation_status in TERMINAL:
        return ReconciliationAction.KEEP
    if snapshot.operation_type not in admitted_types or snapshot.assignment_id != execution.assignment_id:
        return ReconciliationAction.INVESTIGATE
    if execution.state is ExecutionState.UNAVAILABLE:
        return ReconciliationAction.RETRY_OBSERVATION
    if execution.state is ExecutionState.RUNNING:
        return ReconciliationAction.KEEP
    before_start = snapshot.start_acknowledged is False and snapshot.operation_status in {"ACCEPTED", "QUEUED"}
    if execution.state in _FAILED_EXECUTION and before_start:
        return (ReconciliationAction.RECORD_FAILURE if is_allowed(snapshot.operation_status, "FAILED")
                else ReconciliationAction.INVESTIGATE)
    if execution.state in _FAILED_EXECUTION or execution.state in {ExecutionState.COMPLETED, ExecutionState.CANCELLED}:
        # A terminal Workflow does not establish the post-ACK domain outcome.
        return ReconciliationAction.REQUIRE_DOMAIN_OUTCOME
    if before_start and execution.state is ExecutionState.ABSENT and snapshot.operation_status == "ACCEPTED":
        if snapshot.dispatch_state is DispatchState.PENDING:
            return ReconciliationAction.KEEP
        if snapshot.dispatch_state is DispatchState.PUBLISHED and snapshot.outbox_id is not None:
            return ReconciliationAction.RETRY_DISPATCH
    return ReconciliationAction.INVESTIGATE
