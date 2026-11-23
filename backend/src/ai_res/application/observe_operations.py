"""Observe an exact bound Temporal execution for G-107, outside the database transaction."""
import hashlib
from dataclasses import dataclass
from datetime import timedelta
from hmac import compare_digest
from uuid import UUID

from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.workflowservice.v1 import DescribeWorkflowExecutionRequest, GetWorkflowExecutionHistoryRequest
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from ai_res.modules.operations.execution_authority import assigned_input_digest
from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState
from ai_res.orchestration.contracts import (
    ASSIGNED_WORKFLOW_TYPES,
    MANAGER_INTAKE_WORKFLOW,
    MANAGER_TASK_QUEUE,
    PLAN_EXECUTION_WORKFLOW,
    AssignedWorkflowInput,
    workflow_id_for,
)

_STATUS_MAP: dict[int, ExecutionState] = {
    WorkflowExecutionStatus.RUNNING: ExecutionState.RUNNING,
    WorkflowExecutionStatus.COMPLETED: ExecutionState.COMPLETED,
    WorkflowExecutionStatus.FAILED: ExecutionState.FAILED,
    WorkflowExecutionStatus.TIMED_OUT: ExecutionState.TIMED_OUT,
    WorkflowExecutionStatus.TERMINATED: ExecutionState.TERMINATED,
    WorkflowExecutionStatus.CANCELED: ExecutionState.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class BoundExecutionObservationRequest:
    assignment_id: UUID
    operation_id: UUID
    workflow_type: str
    workflow_run_id: UUID
    namespace: str


class TemporalExecutionObserver:
    """Client identity/network settings are provisioned for the reconciliation purpose."""
    def __init__(self, client: Client, *, deadline: timedelta) -> None:
        if deadline <= timedelta(0):
            raise ValueError("a positive observation deadline is required")
        self._client = client
        self._deadline = deadline

    async def observe(self, request: BoundExecutionObservationRequest) -> ExecutionObservation:
        workflow_id = workflow_id_for(request.operation_id)
        if request.namespace != self._client.namespace or request.workflow_type not in {MANAGER_INTAKE_WORKFLOW, PLAN_EXECUTION_WORKFLOW}:
            return ExecutionObservation(request.assignment_id, ExecutionState.SCOPE_MISMATCH)
        execution = WorkflowExecution(workflow_id=workflow_id, run_id=str(request.workflow_run_id))
        try:
            result = await self._client.workflow_service.describe_workflow_execution(
                # One bounded RPC per scan. The scheduler retries unavailable observations on later passes.
                DescribeWorkflowExecutionRequest(namespace=request.namespace, execution=execution), retry=False, timeout=self._deadline,
            )
        except RPCError as error:
            if error.status is RPCStatusCode.NOT_FOUND:
                return ExecutionObservation(request.assignment_id, ExecutionState.ABSENT)
            if error.status in {RPCStatusCode.PERMISSION_DENIED, RPCStatusCode.UNAUTHENTICATED}:
                return ExecutionObservation(request.assignment_id, ExecutionState.SCOPE_MISMATCH)
            return ExecutionObservation(request.assignment_id, ExecutionState.UNAVAILABLE)
        info = result.workflow_execution_info
        if (info.execution.workflow_id != workflow_id or info.execution.run_id != execution.run_id
                or info.task_queue != MANAGER_TASK_QUEUE or info.type.name != request.workflow_type):
            return ExecutionObservation(request.assignment_id, ExecutionState.SCOPE_MISMATCH)
        return ExecutionObservation(request.assignment_id, _STATUS_MAP.get(info.status, ExecutionState.SCOPE_MISMATCH))

    async def discover_initial_run(
        self, request: AssignedWorkflowInput, operation_type: str, namespace: str,
    ) -> UUID | None:
        """Identify a lost Start acknowledgement by the exact first history event."""
        workflow_type = ASSIGNED_WORKFLOW_TYPES.get(operation_type)
        if workflow_type is None or namespace != self._client.namespace:
            return None
        workflow_id = workflow_id_for(UUID(request.operation.operation_id))
        try:
            response = await self._client.workflow_service.get_workflow_execution_history(
                GetWorkflowExecutionHistoryRequest(
                    namespace=namespace, execution=WorkflowExecution(workflow_id=workflow_id), maximum_page_size=1, skip_archival=True,
                ),
                timeout=self._deadline,
            )
        except RPCError as error:
            if error.status in {RPCStatusCode.NOT_FOUND, RPCStatusCode.PERMISSION_DENIED, RPCStatusCode.UNAUTHENTICATED}:
                return None
            raise
        events = response.history.events
        if not events or events[0].event_id != 1 or not events[0].HasField("workflow_execution_started_event_attributes"):
            return None
        started = events[0].workflow_execution_started_event_attributes
        if (started.workflow_type.name != workflow_type or started.task_queue.name != MANAGER_TASK_QUEUE
                or started.original_execution_run_id != started.first_execution_run_id or len(started.input.payloads) != 1):
            return None
        payload = started.input.payloads[0]
        if (dict(payload.metadata) != {"encoding": b"json/plain"} or len(payload.data) > 512
                or not compare_digest(hashlib.sha256(payload.data).digest(), assigned_input_digest(request))):
            return None
        try:
            run_id = UUID(started.original_execution_run_id)
        except ValueError:
            return None
        return run_id if str(run_id) == started.original_execution_run_id else None
