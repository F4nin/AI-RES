"""OperationWorkflow skeleton (S11). Deterministic: no I/O, no clock, no randomness; every effect is an Activity with a bounded retry policy.

Versioning (ADR-087): the input carries a MAJOR contract version; behaviour changes of this workflow ship behind `workflow.patched(<id>)` and every released
history is kept as a replay fixture. Worker Versioning is a technical hypothesis (needs a PoC), not relied upon.

Skeleton behaviour: confirm the start (domain QUEUED/RUNNING), then - because no executable plan exists before S21/S23 - record a terminal FAILED with
`ORCHESTRATION_NOT_IMPLEMENTED`. It is never reported as succeeded and no WorkerRun is created or executed. Both Activities retry for a bounded TIME
(`ACTIVITY_BUDGET`, WORKING); if the Platform API stays unavailable longer, the workflow fails and the Operation can stay ACCEPTED/RUNNING: that gap is
closed only by the Operation <-> Temporal reconciler (G-107), which MUST exist before any operation type is routed to the start destination.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():  # no module side effect (logging setup etc.) is re-executed inside the deterministic sandbox
    from ai_res.orchestration.activities import ACK_ACTIVITY, CANCEL_ACTIVITY, FAIL_ACTIVITY, PERMANENT
    from ai_res.orchestration.contracts import (
        CANCEL_SIGNAL,
        MANAGER_TASK_QUEUE,
        OPERATION_WORKFLOW_TYPE,
        SKELETON_FAILURE_CODE,
        ContractError,
        OperationFailure,
        OperationState,
        OperationWorkflowInput,
        OperationWorkflowResult,
    )

# WORKING (no approved values, Process v1.9 §13.2): technical defaults, bounded - never an endless retry.
ACTIVITY_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0, maximum_interval=timedelta(seconds=30),
                             non_retryable_error_types=[PERMANENT])  # attempts are bounded by ACTIVITY_BUDGET, not by a count
ACTIVITY_TIMEOUT = timedelta(seconds=30)
ACTIVITY_BUDGET = timedelta(minutes=15)  # WORKING: total time one Activity (all attempts) may take; ack/fail are idempotent so long retry is safe


@workflow.defn(name=OPERATION_WORKFLOW_TYPE)
class OperationWorkflow:
    def __init__(self) -> None:
        self._cancel_requested = False

    @workflow.signal(name=CANCEL_SIGNAL)
    def request_cancel(self) -> None:
        """Only a flag: the domain already holds CANCEL_REQUESTED; the Workflow stops at its next checkpoint and asks the domain to reconcile."""
        self._cancel_requested = True

    async def _reconcile_cancellation(self, request: OperationWorkflowInput) -> OperationWorkflowResult | None:
        """The domain is the authority, the signal is only a hint: reconciliation (idempotent) answers CANCELLED, CANCEL_REQUESTED (cleanup pending) or the
        status it already had. A flag the domain does not back (premature or forged signal) changes nothing: None = carry on as if it never arrived."""
        state = await workflow.execute_activity(CANCEL_ACTIVITY, request.operation, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
                                                start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY)
        if state.status == "CANCELLED":
            return OperationWorkflowResult("CANCELLED_CONFIRMED", state.status)
        if state.status == "CANCEL_REQUESTED":
            return OperationWorkflowResult("CANCEL_PENDING", state.status)
        return None

    @workflow.run
    async def run(self, request: OperationWorkflowInput) -> OperationWorkflowResult:
        try:
            OperationWorkflowInput(request.contract_version, request.operation, request.correlation_id)  # re-validate what Temporal deserialised
        except ContractError as exc:
            raise ApplicationError("invalid workflow input", type="ContractError", non_retryable=True) from exc
        state = await workflow.execute_activity(ACK_ACTIVITY, request.operation, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
                                                start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET,
                                                retry_policy=ACTIVITY_RETRY)
        if state.status == "CANCEL_REQUESTED" or self._cancel_requested:  # checkpoint 1: nothing was started, so a real cancellation is reconciled at once
            cancelled = await self._reconcile_cancellation(request)
            if cancelled is not None:
                return cancelled
        if state.status != "RUNNING":  # terminal or otherwise not ours to drive: nothing to orchestrate
            return OperationWorkflowResult("NOT_RUNNING", state.status)
        final = await workflow.execute_activity(FAIL_ACTIVITY, OperationFailure(request.operation, SKELETON_FAILURE_CODE), result_type=OperationState,
                                                task_queue=MANAGER_TASK_QUEUE, start_to_close_timeout=ACTIVITY_TIMEOUT,
                                                schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY)
        if final.status == "CANCEL_REQUESTED":  # the cancel won the race against the skeleton failure: reconcile instead of leaving it pending (closes S11 L7)
            cancelled = await self._reconcile_cancellation(request)
            if cancelled is not None:
                return cancelled
        return OperationWorkflowResult("SKELETON_FAILED_CLOSED", final.status)
