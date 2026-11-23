"""Outbox publisher for the Operation start command (S11; Decision v1.6 §2.5 steps 3-4, Spec v1.13 rule 2).

Dispatcher -> Temporal: reads ONLY identifiers from the event (operation, tenant scope, correlation), builds the compact workflow input and starts the Workflow
under the ID derived from the Operation ID. A redelivery is harmless (USE_EXISTING / REJECT_DUPLICATE). The Operation status is NOT touched here: the
dispatcher role has no write access to domain tables; QUEUED/RUNNING are set by the workflow's first Activity through the Application Service, so a start that
Temporal accepted but nobody confirmed stays ACCEPTED and is visible to reconciliation (G-107) rather than being reported as running.
Errors: an event that is not a well-formed start command is PERMANENT (quarantine, replayable); Temporal unavailable/timeouts are TRANSIENT (bounded retry).
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from temporalio.service import RPCError, RPCStatusCode

from ai_res.modules.events import delivery
from ai_res.modules.events.metrics import get_event_metrics
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.orchestration.client import AssignedOperationCanceller, AssignedOperationStarter, CancelOutcome, OperationCanceller, OperationStarter, StartOutcome
from ai_res.orchestration.contracts import (
    ASSIGNED_WORKFLOW_TYPES,
    CANCEL_DESTINATION,
    CONTRACT_VERSION,
    EXECUTION_ASSIGNMENT_REF,
    START_DESTINATION,
    AssignedCancellation,
    AssignedWorkflowInput,
    ContractError,
    OperationRef,
    OperationWorkflowInput,
)

log = logging.getLogger("ai_res.events.temporal_start")
TRANSIENT_RPC = frozenset({RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED, RPCStatusCode.RESOURCE_EXHAUSTED, RPCStatusCode.ABORTED,
                           RPCStatusCode.CANCELLED, RPCStatusCode.UNKNOWN, RPCStatusCode.INTERNAL})
START_EVENT_TYPES = frozenset({"operation.accepted", "com.aires.operation.accepted.v1"})


class TemporalStartPublisher:
    def __init__(self, starter: OperationStarter) -> None:
        self._starter = starter

    @staticmethod
    def request_from(row: OutboxRow) -> OperationWorkflowInput:
        if row.destination != START_DESTINATION or row.aggregate_type != "OPERATION" or row.event_type not in START_EVENT_TYPES:
            raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
        data: Any = row.envelope.get("data")
        if not isinstance(data, dict):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
        references = data.get("refs", [])
        if not isinstance(references, list) or any(
            isinstance(ref, dict) and ref.get("resourceType") == EXECUTION_ASSIGNMENT_REF for ref in references
        ):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)  # only the protected V3 dispatcher may act on the assignment

        try:
            request = OperationWorkflowInput(CONTRACT_VERSION, OperationRef(str(data["operationId"]), str(data["organizationId"]), str(data["projectId"])),
                                             str(data["correlationId"]))
        except (KeyError, ContractError):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
        if request.operation.operation_id != str(row.aggregate_id):
            raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)  # the command must describe the aggregate it came from
        return request

    async def publish(self, row: OutboxRow) -> None:
        request = self.request_from(row)
        try:
            outcome = await self._starter.start(request)
        except RPCError as exc:
            # INVALID_ARGUMENT / NOT_FOUND (namespace) / PERMISSION_DENIED are configuration faults: retrying cannot help -> quarantine, status visible.
            log.error("temporal start rejected", extra={"rpc_status": exc.status.name})
            code = delivery.PUBLISH_FAILED if exc.status in TRANSIENT_RPC else delivery.SCHEMA_REJECTED
            raise (delivery.TransientDeliveryError if exc.status in TRANSIENT_RPC else delivery.PermanentDeliveryError)(code) from exc
        except (ConnectionError, OSError, TimeoutError, RuntimeError) as exc:
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from exc
        if outcome is StartOutcome.ALREADY_FINISHED:  # normal after a success; an anomaly if the Operation is not terminal (G-107): never silent
            get_event_metrics().count("start_already_finished")
            log.warning("start redelivered for a closed workflow", extra={"operation_id": request.operation.operation_id})


def assigned_start_request(row: OutboxRow) -> tuple[AssignedWorkflowInput, str]:
    if (row.destination != START_DESTINATION or row.aggregate_type != "OPERATION" or row.event_type not in START_EVENT_TYPES
            or row.schema_version != CONTRACT_VERSION):
        raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
    data = row.envelope.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("refs"), list) or not isinstance(data.get("details"), dict):
        raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
    assignments = [ref.get("resourceId") for ref in data["refs"] if isinstance(ref, dict) and ref.get("resourceType") == EXECUTION_ASSIGNMENT_REF]
    operation_type = data["details"].get("operationType")
    if len(assignments) != 1 or not isinstance(operation_type, str) or operation_type not in ASSIGNED_WORKFLOW_TYPES:
        raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
    assignment_id = assignments[0]
    if not isinstance(assignment_id, str):
        raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
    try:
        request = AssignedWorkflowInput(
            CONTRACT_VERSION, OperationRef(data["operationId"], data["organizationId"], data["projectId"]), assignment_id,
        )
    except (KeyError, ContractError):
        raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
    if request.operation.operation_id != str(row.aggregate_id):
        raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
    return request, operation_type


class AssignedTemporalStartPublisher:
    """Publish only to admitted workflows. The binder verifies the exact run via its own authority."""

    def __init__(
        self, starter: AssignedOperationStarter, bind: Callable[[AssignedWorkflowInput, str, UUID], Awaitable[bool]],
        already_bound: Callable[[AssignedWorkflowInput, str], Awaitable[bool]],
        prepare: Callable[[AssignedWorkflowInput, str], Awaitable[bool]],
    ) -> None:
        self._starter, self._bind, self._already_bound = starter, bind, already_bound
        self._prepare = prepare

    async def publish(self, row: OutboxRow) -> None:
        request, operation_type = assigned_start_request(row)
        try:
            if not await self._prepare(request, operation_type):
                return
            result = await self._starter.start(request, operation_type)
            bound = await self._bind(request, operation_type, result.run_id)
        except RPCError as error:
            if error.status is RPCStatusCode.PERMISSION_DENIED and await self._already_bound(request, operation_type):
                return
            if error.status in TRANSIENT_RPC:
                raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from None
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
        except (ConnectionError, OSError, TimeoutError, RuntimeError):
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from None
        if not bound:
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED)


CANCEL_EVENT_TYPES = frozenset({"operation.cancel_requested", "com.aires.operation.cancel_requested.v1"})


def _cancel_data(row: OutboxRow) -> tuple[UUID, dict[str, Any], list[Any]]:
    if row.destination != CANCEL_DESTINATION or row.aggregate_type != "OPERATION" or row.event_type not in CANCEL_EVENT_TYPES:
        raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
    data = row.envelope.get("data")
    try:
        if not isinstance(data, dict):
            raise ValueError
        operation_id = UUID(str(data["operationId"]))
        refs = data.get("refs", [])
        if not isinstance(refs, list):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
    if operation_id != row.aggregate_id:
        raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
    return operation_id, data, refs


class TemporalCancelPublisher:
    """Outbox -> Temporal signal for an Operation in CANCEL_REQUESTED. At-least-once is harmless: the signal only sets a flag and the domain reconciliation
    is idempotent. A closed/unknown Workflow is not an error of delivery: the Operation stays CANCEL_REQUESTED and is visible to reconciliation (G-107)."""

    def __init__(self, canceller: OperationCanceller) -> None:
        self._canceller = canceller

    @staticmethod
    def operation_id_from(row: OutboxRow) -> UUID:
        operation_id, _, refs = _cancel_data(row)
        if any(isinstance(ref, dict) and ref.get("resourceType") == EXECUTION_ASSIGNMENT_REF for ref in refs):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
        return operation_id

    async def publish(self, row: OutboxRow) -> None:
        operation_id = self.operation_id_from(row)
        try:
            outcome = await self._canceller.signal(operation_id)
        except RPCError as exc:
            log.error("temporal cancel signal rejected", extra={"rpc_status": exc.status.name})
            raise (delivery.TransientDeliveryError if exc.status in TRANSIENT_RPC else delivery.PermanentDeliveryError)(
                delivery.PUBLISH_FAILED if exc.status in TRANSIENT_RPC else delivery.SCHEMA_REJECTED) from exc
        except (ConnectionError, OSError, TimeoutError, RuntimeError) as exc:
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from exc
        if outcome is CancelOutcome.NO_RUNNING_WORKFLOW:
            get_event_metrics().count("cancel_without_workflow")
            log.warning("cancel requested but no running workflow", extra={"operation_id": str(operation_id)})


class AssignedTemporalCancelPublisher:
    def __init__(self, canceller: AssignedOperationCanceller, settled: Callable[[AssignedCancellation], Awaitable[bool]]) -> None:
        self._canceller, self._settled = canceller, settled

    async def publish(self, row: OutboxRow) -> None:
        operation_id, data, refs = _cancel_data(row)
        assignments = [ref for ref in refs if isinstance(ref, dict) and ref.get("resourceType") == EXECUTION_ASSIGNMENT_REF]
        if len(assignments) != 1 or row.schema_version != CONTRACT_VERSION:
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
        ref = assignments[0]
        try:
            scope = OperationRef(str(operation_id), data["organizationId"], data["projectId"])
            assignment_id = UUID(ref["resourceId"])
            if "versionId" not in ref:
                raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED)  # an assigned request cannot fall back to a generic signal
            bound = AssignedCancellation(scope, assignment_id, UUID(ref["versionId"]))
        except (KeyError, TypeError, ValueError):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
        if await self._settled(bound):
            return
        try:
            await self._canceller.signal(operation_id, bound.workflow_run_id, bound.assignment_id)
        except RPCError as exc:
            if exc.status in {RPCStatusCode.PERMISSION_DENIED, RPCStatusCode.NOT_FOUND} and await self._settled(bound):
                return
            if exc.status in TRANSIENT_RPC:
                raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from None
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) from None
        except (ConnectionError, OSError, TimeoutError, RuntimeError):
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from None
