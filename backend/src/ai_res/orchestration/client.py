"""Temporal client adapter (API Contracts v1.10 §9.4): idempotent Workflow start from a stable ID derived from the Operation ID.

Duplicate Outbox delivery is the normal case (at-least-once): a second start of the same Operation must never create a second business process. Running
execution -> USE_EXISTING; an already closed one -> REJECT_DUPLICATE is reported as "already started" (a finished Operation is never re-run by a redelivery).
"""
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from opentelemetry.trace import Tracer
from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.workflowservice.v1 import SignalWorkflowExecutionRequest
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig
from temporalio.service import RPCError, RPCStatusCode, TLSConfig

from ai_res.orchestration.contracts import (
    ASSIGNED_WORKFLOW_TYPES,
    CANCEL_SIGNAL,
    MANAGER_TASK_QUEUE,
    OPERATION_WORKFLOW_TYPE,
    AssignedWorkflowInput,
    OperationWorkflowInput,
    assert_compact,
    workflow_id_for,
)
from ai_res.platform.config import ConfigError, Settings
from ai_res.platform.export import process_tracer


class StartOutcome(StrEnum):
    ENSURED = "ENSURED"  # the Workflow was started now, or is still running (Temporal does not say which: both mean "exactly one process exists")
    ALREADY_FINISHED = "ALREADY_FINISHED"  # a closed execution holds this ID: a redelivery never re-runs a finished Operation


_RUNTIMES: dict[tuple[str, float], Runtime] = {}  # Temporal recommends ONE Runtime per process (own threads + exporter)


def temporal_runtime(settings: Settings) -> Runtime | None:
    """SDK core metrics (schedule-to-start, poller and Activity counters) over OTLP/gRPC to the Collector (S13, G-108). None = SDK default (no export).
    The SDK exports in its own thread: an unreachable Collector cannot block Workflow or Activity execution (fail-open)."""
    if not settings.otlp_grpc_endpoint:
        return None
    key = (settings.otlp_grpc_endpoint, settings.otlp_metric_interval_seconds)
    if key in _RUNTIMES:
        return _RUNTIMES[key]
    period = timedelta(seconds=settings.otlp_metric_interval_seconds)
    config = OpenTelemetryConfig(url=settings.otlp_grpc_endpoint, metric_periodicity=period, durations_as_seconds=True)
    _RUNTIMES[key] = Runtime(telemetry=TelemetryConfig(metrics=config, metric_prefix="temporal_"))
    return _RUNTIMES[key]


async def connect(settings: Settings, tracer: Tracer | None = None, *, tls: TLSConfig | bool = False) -> Client:
    """`tracer` enables Workflow/Activity/StartWorkflow spans and trace-context propagation through Temporal headers (ids only, no payloads)."""
    if not settings.temporal_address:
        raise ConfigError("temporal_address is not configured")
    tracer = tracer or process_tracer("ai_res.temporal")
    interceptors = [TracingInterceptor(tracer)] if tracer is not None else []
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace, runtime=temporal_runtime(settings),
                                interceptors=interceptors, tls=tls)


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



@dataclass(frozen=True, slots=True)
class AssignedStart:
    run_id: UUID
    outcome: StartOutcome


class AssignedOperationStarter:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: AssignedWorkflowInput, operation_type: str) -> AssignedStart:
        workflow_type = ASSIGNED_WORKFLOW_TYPES.get(operation_type)
        if workflow_type is None:
            raise ValueError("Operation type has no assigned workflow")
        assert_compact(request)
        workflow_id = workflow_id_for(UUID(request.operation.operation_id))
        try:
            handle = await self._client.start_workflow(
                workflow_type, request, id=workflow_id, task_queue=MANAGER_TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING, id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
            run_id = handle.first_execution_run_id
            outcome = StartOutcome.ENSURED
        except WorkflowAlreadyStartedError as error:
            run_id = error.first_run_id or error.run_id
            outcome = StartOutcome.ALREADY_FINISHED
        if run_id is None:
            raise RuntimeError("Temporal did not return an execution reference")
        return AssignedStart(UUID(run_id), outcome)


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


class AssignedOperationCanceller:
    """Send the fixed signal to one Run using the dedicated cancellation client."""

    def __init__(self, client: Client, *, deadline: timedelta) -> None:
        if deadline <= timedelta(0):
            raise ValueError("Cancellation deadline must be positive")
        self._client = client
        self._deadline = deadline

    async def signal(self, operation_id: UUID, run_id: UUID, assignment_id: UUID) -> None:
        # Each assignment can have only one domain cancellation. Use its stable
        # id as both the authorization reference and Temporal deduplication key.
        await self._client.workflow_service.signal_workflow_execution(SignalWorkflowExecutionRequest(
            namespace=self._client.namespace,
            workflow_execution=WorkflowExecution(workflow_id=workflow_id_for(operation_id), run_id=str(run_id)),
            signal_name=CANCEL_SIGNAL,
            request_id=str(assignment_id),
        ), timeout=self._deadline)
