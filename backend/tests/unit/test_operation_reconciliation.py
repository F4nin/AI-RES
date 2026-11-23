"""G-107 deterministic rules before scheduler/store wiring."""
from dataclasses import replace
from uuid import uuid4

import pytest

from ai_res.modules.operations.reconciliation import (
    DispatchSnapshot,
    DispatchState,
    ExecutionObservation,
    ExecutionState,
    ReconciliationAction,
    decide_reconciliation,
)

_ADMITTED = frozenset({"MANAGER_MESSAGE"})


@pytest.mark.parametrize(("operation", "delivery", "execution", "expected"), [
    ("ACCEPTED", DispatchState.PUBLISHED, ExecutionState.ABSENT, ReconciliationAction.RETRY_DISPATCH),
    ("ACCEPTED", DispatchState.PENDING, ExecutionState.ABSENT, ReconciliationAction.KEEP),
    ("ACCEPTED", DispatchState.MISSING, ExecutionState.ABSENT, ReconciliationAction.INVESTIGATE),
    ("RUNNING", DispatchState.PUBLISHED, ExecutionState.COMPLETED,
     ReconciliationAction.REQUIRE_DOMAIN_OUTCOME),
    ("RUNNING", DispatchState.PUBLISHED, ExecutionState.ABSENT, ReconciliationAction.INVESTIGATE),
    ("RUNNING", DispatchState.PUBLISHED, ExecutionState.UNAVAILABLE, ReconciliationAction.RETRY_OBSERVATION),
    ("QUEUED", DispatchState.PUBLISHED, ExecutionState.FAILED, ReconciliationAction.RECORD_FAILURE),
    ("CANCEL_REQUESTED", DispatchState.PUBLISHED, ExecutionState.FAILED, ReconciliationAction.REQUIRE_DOMAIN_OUTCOME),
    ("CANCEL_REQUESTED", DispatchState.PUBLISHED, ExecutionState.CANCELLED, ReconciliationAction.REQUIRE_DOMAIN_OUTCOME),
    ("SUCCEEDED", DispatchState.QUARANTINED, ExecutionState.FAILED, ReconciliationAction.KEEP),
])
def test_reconciliation_uses_authoritative_operation_status(operation, delivery, execution, expected):
    snapshot = DispatchSnapshot(uuid4(), "MANAGER_MESSAGE", 3, operation, delivery, uuid4(), uuid4(), start_acknowledged=False)
    assert decide_reconciliation(snapshot, ExecutionObservation(snapshot.assignment_id, execution), admitted_types=_ADMITTED) is expected


def test_unadmitted_operation_wrong_assignment_or_missing_outbox_cannot_retry():
    snapshot = DispatchSnapshot(uuid4(), "MANAGER_MESSAGE", 3, "ACCEPTED", DispatchState.PUBLISHED, uuid4(), uuid4())
    observation = ExecutionObservation(snapshot.assignment_id, ExecutionState.ABSENT)
    for unbound, observed in (
        (replace(snapshot, operation_type="SOURCE_INGESTION"), observation),
        (replace(snapshot, outbox_id=None), observation),
        (snapshot, replace(observation, assignment_id=uuid4())),
    ):
        assert decide_reconciliation(unbound, observed, admitted_types=_ADMITTED) is ReconciliationAction.INVESTIGATE


@pytest.mark.parametrize("acknowledged", [True, None])
def test_requeued_started_or_unverified_operation_requires_domain_proof(acknowledged):
    snapshot = DispatchSnapshot(uuid4(), "MANAGER_MESSAGE", 7, "QUEUED", DispatchState.PUBLISHED, uuid4(), uuid4(), start_acknowledged=acknowledged)
    terminal = ExecutionObservation(snapshot.assignment_id, ExecutionState.FAILED)
    assert decide_reconciliation(snapshot, terminal, admitted_types=_ADMITTED) is ReconciliationAction.REQUIRE_DOMAIN_OUTCOME
