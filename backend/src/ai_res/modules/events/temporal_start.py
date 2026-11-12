"""Outbox publisher for the Operation start command (S11; Decision v1.6 §2.5 steps 3-4, Spec v1.13 rule 2).

Dispatcher -> Temporal: reads ONLY identifiers from the event (operation, tenant scope, correlation), builds the compact workflow input and starts the Workflow
under the ID derived from the Operation ID. A redelivery is harmless (USE_EXISTING / REJECT_DUPLICATE). The Operation status is NOT touched here: the
dispatcher role has no write access to domain tables; QUEUED/RUNNING are set by the workflow's first Activity through the Application Service, so a start that
Temporal accepted but nobody confirmed stays ACCEPTED and is visible to reconciliation (G-107) rather than being reported as running.
Errors: an event that is not a well-formed start command is PERMANENT (quarantine, replayable); Temporal unavailable/timeouts are TRANSIENT (bounded retry).
"""
import logging
from typing import Any

from temporalio.service import RPCError, RPCStatusCode

from ai_res.modules.events import delivery
from ai_res.modules.events.metrics import get_event_metrics
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.orchestration.client import OperationStarter, StartOutcome
from ai_res.orchestration.contracts import CONTRACT_VERSION, START_DESTINATION, ContractError, OperationRef, OperationWorkflowInput

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
