"""G02 workflows with references only. Legacy OperationWorkflow histories stay replayable."""
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ai_res.orchestration.contracts import (
        CANCEL_SIGNAL,
        MANAGER_INTAKE_WORKFLOW,
        MANAGER_TASK_QUEUE,
        PLAN_EXECUTION_WORKFLOW,
        AssignedWorkflowInput,
        OperationRef,
        OperationState,
        workflow_id_for,
    )
    from ai_res.orchestration.workflows import ACTIVITY_BUDGET, ACTIVITY_RETRY, ACTIVITY_TIMEOUT

MANAGER_TURN = "complete_manager_intake"
PLAN_PREPARE = "prepare_plan_tasks"
BOUND_CANCEL = "confirm_bound_cancellation"
BOUND_ACK = "acknowledge_bound_start"
_TERMINAL = frozenset({"CANCELLED", "FAILED", "SUCCEEDED", "PARTIALLY_SUCCEEDED"})
_CANCELLATION_RECHECK = timedelta(seconds=30)  # WORKING; uses the existing Activity timeout cadence.


@dataclass(frozen=True, slots=True)
class BoundWorkflowCall:
    operation: OperationRef
    assignment_id: str
    workflow_id: str
    workflow_run_id: str

    def __post_init__(self) -> None:
        if self.workflow_id != workflow_id_for(UUID(self.operation.operation_id)):
            raise ValueError("workflow does not match the Operation reference")
        if str(UUID(self.workflow_run_id)) != self.workflow_run_id or str(UUID(self.assignment_id)) != self.assignment_id:
            raise ValueError("workflow needs canonical execution references")


def _bound(request: AssignedWorkflowInput) -> BoundWorkflowCall:
    info = workflow.info()
    return BoundWorkflowCall(request.operation, request.assignment_id, info.workflow_id, info.run_id)


async def _acknowledge(reference: BoundWorkflowCall) -> OperationState:
    state: OperationState = await workflow.execute_activity(
        BOUND_ACK, reference, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
        start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY,
    )
    return state


async def _confirm_cancellation(reference: BoundWorkflowCall) -> OperationState:
    state: OperationState = await workflow.execute_activity(
        BOUND_CANCEL, reference, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
        start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY,
    )
    while state.status == "CANCEL_REQUESTED":
        await workflow.sleep(_CANCELLATION_RECHECK)
        state = await workflow.execute_activity(
            BOUND_CANCEL, reference, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
            start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY,
        )
    return state


@workflow.defn(name=MANAGER_INTAKE_WORKFLOW)
class ManagerIntakeWorkflow:
    def __init__(self) -> None:
        self._cancellation = False

    @workflow.signal(name=CANCEL_SIGNAL)
    def request_cancel(self) -> None:
        self._cancellation = True

    @workflow.run
    async def run(self, request: AssignedWorkflowInput) -> OperationState:
        reference = _bound(request)
        state = await _acknowledge(reference)
        if state.status == "CANCEL_REQUESTED" or self._cancellation:
            state = await _confirm_cancellation(reference)
        if state.status != "RUNNING":
            return state
        # The single paid Activity attempt communicates only its resulting Operation status.
        # G-107 reconciles interrupted attempts against database state.
        result: OperationState = await workflow.execute_activity(
            MANAGER_TURN, reference, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
            start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        if result.status == "CANCEL_REQUESTED" or self._cancellation and result.status not in _TERMINAL:
            return await _confirm_cancellation(reference)
        return result


@workflow.defn(name=PLAN_EXECUTION_WORKFLOW)
class PlanExecutionWorkflow:
    def __init__(self) -> None:
        self._cancellation = False

    @workflow.signal(name=CANCEL_SIGNAL)
    def request_cancel(self) -> None:
        self._cancellation = True

    @workflow.run
    async def run(self, request: AssignedWorkflowInput) -> OperationState:
        reference = _bound(request)
        state = await _acknowledge(reference)
        if state.status == "CANCEL_REQUESTED" or self._cancellation:
            state = await _confirm_cancellation(reference)
        if state.status not in {"RUNNING", "WAITING_FOR_DEPENDENCY"}:
            return state
        prepared: OperationState = await workflow.execute_activity(
            PLAN_PREPARE, reference, result_type=OperationState, task_queue=MANAGER_TASK_QUEUE,
            start_to_close_timeout=ACTIVITY_TIMEOUT, schedule_to_close_timeout=ACTIVITY_BUDGET, retry_policy=ACTIVITY_RETRY,
        )
        if prepared.status == "CANCEL_REQUESTED":
            prepared = await _confirm_cancellation(reference)
        if prepared.status not in {"RUNNING", "WAITING_FOR_DEPENDENCY"}:
            return prepared
        while True:
            await workflow.wait_condition(lambda: self._cancellation)
            self._cancellation = False
            state = await _confirm_cancellation(reference)
            if state.status in _TERMINAL:
                return state
