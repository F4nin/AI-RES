"""Operation state machine (State Machine v1.2 `operationStatuses`/`transitions`/`terminalStatuses`; Architecture Decision v1.6 §2.4).

The table is a code constant (the runtime never reads `docs/architecture`); `tests/unit/test_operation_state_machine.py` keeps it byte-for-byte equal to the
baselined JSON. A terminal Operation is never reopened, a transition that is not in the table is refused BEFORE anything is written.
"""
from collections.abc import Mapping

from ai_res.platform.problems import ErrorCode, ProblemError

STATUSES = ("ACCEPTED", "QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING", "CANCEL_REQUESTED",
            "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED")
TERMINAL = frozenset({"SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED"})
TRANSITIONS: Mapping[str, frozenset[str]] = {
    "ACCEPTED": frozenset({"QUEUED", "FAILED", "CANCELLED"}),
    "QUEUED": frozenset({"RUNNING", "WAITING_FOR_DEPENDENCY", "FAILED", "CANCEL_REQUESTED", "CANCELLED"}),
    "RUNNING": frozenset({"WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING", "CANCEL_REQUESTED", "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED"}),
    "WAITING_FOR_HUMAN": frozenset({"QUEUED", "RUNNING", "CANCEL_REQUESTED", "FAILED", "CANCELLED"}),
    "WAITING_FOR_DEPENDENCY": frozenset({"QUEUED", "RUNNING", "RETRYING", "CANCEL_REQUESTED", "FAILED", "CANCELLED"}),
    "RETRYING": frozenset({"QUEUED", "RUNNING", "WAITING_FOR_DEPENDENCY", "FAILED", "CANCEL_REQUESTED", "CANCELLED"}),
    "CANCEL_REQUESTED": frozenset({"CANCELLED", "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED"}),
    "SUCCEEDED": frozenset(), "PARTIALLY_SUCCEEDED": frozenset(), "FAILED": frozenset(), "CANCELLED": frozenset(),
}


def is_allowed(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def require_transition(from_status: str, to_status: str) -> None:
    """Unknown or illegal transition -> 409 STATE_TRANSITION_NOT_ALLOWED (a caller error, never retried as a lost race)."""
    if from_status not in TRANSITIONS or to_status not in TRANSITIONS or not is_allowed(from_status, to_status):
        raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Operation status transition is not allowed.")
