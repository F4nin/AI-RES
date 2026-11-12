"""Temporal client adapter (API Contracts v1.10 §9.4): idempotent Workflow start from a stable ID derived from the Operation ID.

Duplicate Outbox delivery is the normal case (at-least-once): a second start of the same Operation must never create a second business process. Running
execution -> USE_EXISTING; an already closed one -> REJECT_DUPLICATE is reported as "already started" (a finished Operation is never re-run by a redelivery).
"""
from enum import StrEnum
from uuid import UUID

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from ai_res.orchestration.contracts import CANCEL_SIGNAL, MANAGER_TASK_QUEUE, OPERATION_WORKFLOW_TYPE, OperationWorkflowInput, assert_compact, workflow_id_for
from ai_res.platform.config import ConfigError, Settings


class StartOutcome(StrEnum):
    ENSURED = "ENSURED"  # the Workflow was started now, or is still running (Temporal does not say which: both mean "exactly one process exists")
    ALREADY_FINISHED = "ALREADY_FINISHED"  # a closed execution holds this ID: a redelivery never re-runs a finished Operation


async def connect(settings: Settings) -> Client:
    if not settings.temporal_address:
        raise ConfigError("temporal_address is not configured")
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


class OperationStarter:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: OperationWorkflowInput) -> StartOutcome:
        assert_compact(request)
        workflow_id = workflow_id_for(UUID(request.operation.operation_id))
        try:
            await self._client.start_workflow(OPERATION_WORKFLOW_TYPE, request, id=workflow_id, task_queue=MANAGER_TASK_QUEUE,
                                              id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING, id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        except WorkflowAlreadyStartedError:
            return StartOutcome.ALREADY_FINISHED
        return StartOutcome.ENSURED



class CancelOutcome(StrEnum):
    SIGNALLED = "SIGNALLED"
    NO_RUNNING_WORKFLOW = "NO_RUNNING_WORKFLOW"  # closed or unknown: the domain reconciler (G-107) owns an Operation still in CANCEL_REQUESTED


class OperationCanceller:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def signal(self, operation_id: UUID) -> CancelOutcome:
        """Signal only: the signal carries no payload, so nothing but the Workflow ID (derived from the Operation ID) leaves this process."""
        handle = self._client.get_workflow_handle(workflow_id_for(operation_id))
        try:
            await handle.signal(CANCEL_SIGNAL)
        except RPCError as exc:
            if exc.status is RPCStatusCode.NOT_FOUND:
                return CancelOutcome.NO_RUNNING_WORKFLOW
            raise
        return CancelOutcome.SIGNALLED
