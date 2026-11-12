"""CloudEvents 1.0 envelope of Operation / WorkerRun events, built exactly as the canonical messages of AsyncAPI v1.6 (G-56, option A).

Decision of the project owner (2026-11-11): the envelope conforms to `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml` now. Canonical messages carry only the nine
CloudEvents attributes (`additionalProperties: false`); tenant, aggregate, correlation and actor fields live in `data` (`OperationWorkerRunEventData`), and
event-specific fields live in `data.details`. Pure functions, no I/O: the shape is verified against the contract by tests/contract/test_event_envelope.py.

WORKING (not fixed by any normative document, kept in one place so that the owner's ruling is a one-line change):
  * `dataschema` URI form (`DATASCHEMA_PREFIX`): the documents only demand a stable URI identifying the schema of a concrete event version;
  * `source` of WorkerRun events (`SOURCES`): Event Model v1.4 §4 gives only the Operation example `urn:aires:operations`.
Known contract conflicts handled without choosing silently (see KNOWN_GAPS G-56): Event Model v1.4 §4 asks for `data.eventType`, AsyncAPI forbids it, and the
AsyncAPI canonical set has no `worker_run.created` message although State Machine v1.2 lists the event type.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from ai_res.platform.clock import to_rfc3339

# State Machine v1.2: operationEventTypes / workerRunEventTypes (drift-tested against the contract file).
OPERATION_EVENT_TYPES = frozenset({
    "operation.accepted", "operation.queued", "operation.started", "operation.waiting_for_human", "operation.waiting_for_dependency", "operation.resumed",
    "operation.retrying", "operation.cancel_requested", "operation.succeeded", "operation.partially_succeeded", "operation.failed", "operation.cancelled",
    "operation.child_created", "operation.progress_updated"})
WORKER_RUN_EVENT_TYPES = frozenset({
    "worker_run.created", "worker_run.preparation_started", "worker_run.gate_evaluation_requested", "worker_run.gate_evaluation_completed",
    "worker_run.blocked",
    "worker_run.queued", "worker_run.started", "worker_run.waiting_for_human", "worker_run.waiting_for_dependency", "worker_run.resumed",
    "worker_run.result_submitted", "worker_run.validation_completed", "worker_run.review_requested", "worker_run.qa_requested",
    "worker_run.completed", "worker_run.rework_required", "worker_run.rejected", "worker_run.unverified", "worker_run.cancel_requested",
    "worker_run.cancelled", "worker_run.failed", "worker_run.timed_out", "worker_run.derived"})
# S09 write commands: the three AsyncAPI v1.6 messages of the OLDER family (`aires.<name>.v1`, channel `aires.project.events`). They carry no Operation.
DOMAIN_EVENT_TYPES: Mapping[str, frozenset[str]] = {
    "PROJECT": frozenset({"project.created"}), "EPIC": frozenset({"epic.created"}), "REQUIREMENT": frozenset({"requirement.version.created"})}
DOMAIN_DESTINATION = "aires.project.events"  # AsyncAPI v1.6 channel address
EVENT_TYPES_BY_AGGREGATE: Mapping[str, frozenset[str]] = {"OPERATION": OPERATION_EVENT_TYPES, "WORKER_RUN": WORKER_RUN_EVENT_TYPES, **DOMAIN_EVENT_TYPES}

ACTOR_TYPES = frozenset({"SYSTEM", "USER", "MANAGER", "WORKER", "SERVICE"})  # AsyncAPI OperationWorkerRunEventData.actor.type
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})  # an unknown major version fails closed, never a silent downgrade

SOURCES: Mapping[str, str] = {"OPERATION": "urn:aires:operations", "WORKER_RUN": "urn:aires:worker-runs", "PROJECT": "urn:aires:projects",
                              "EPIC": "urn:aires:epics", "REQUIREMENT": "urn:aires:requirements"}  # WORKING except OPERATION (OD-13)
SUBJECT_PREFIX: Mapping[str, str] = {"OPERATION": "operations", "WORKER_RUN": "worker-runs", "PROJECT": "projects", "EPIC": "epics",
                                     "REQUIREMENT": "requirements"}  # Event Model v1.4 §4 (OPERATION, WORKER_RUN); the rest follow the same rule
DATASCHEMA_PREFIX = "urn:aires:schemas:"  # WORKING: dataschema = prefix + CloudEvents type (unique per event type and major version)


@dataclass(frozen=True)
class EventRef:
    """ACL-protected resource reference (`data.refs[]`): identifiers only, never content."""
    resource_type: str
    resource_id: UUID
    version_id: UUID | None = None


def event_type_name(short_name: str, schema_version: int, aggregate_type: str | None = None) -> str:
    prefix = "aires" if aggregate_type in DOMAIN_EVENT_TYPES else "com.aires"
    return f"{prefix}.{short_name}.v{schema_version}"


def subject_for(aggregate_type: str, aggregate_id: UUID) -> str:
    return f"{SUBJECT_PREFIX[aggregate_type]}/{aggregate_id}"


def validate_event_identity(aggregate_type: str, event_type: str, schema_version: int, actor_type: str) -> None:
    registry = EVENT_TYPES_BY_AGGREGATE.get(aggregate_type)
    if registry is None:
        raise ValueError(f"aggregate type {aggregate_type!r} has no event registry")
    if event_type not in registry:
        raise ValueError(f"event type {event_type!r} is not in the {aggregate_type} event registry")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported event schema version {schema_version!r}")
    if actor_type not in ACTOR_TYPES:
        raise ValueError(f"actor type {actor_type!r} is not one of {sorted(ACTOR_TYPES)}")


def build_envelope(*, aggregate_type: str, aggregate_id: UUID, event_id: UUID, sequence: int, version: int, occurred_at: datetime, organization_id: UUID,
                   project_id: UUID, operation_id: UUID | None, event_type: str, schema_version: int, actor_type: str, actor_id: UUID | None,
                   correlation_id: UUID, causation_id: UUID | None, reason_code: str | None, from_status: str | None, to_status: str | None,
                   details: Mapping[str, Any], refs: Sequence[EventRef]) -> dict[str, Any]:
    """Optional attributes are omitted, never null (CloudEvents); `data.eventType` is deliberately absent (AsyncAPI forbids it)."""
    validate_event_identity(aggregate_type, event_type, schema_version, actor_type)
    domain = aggregate_type in DOMAIN_EVENT_TYPES
    if domain == (operation_id is not None):
        raise ValueError("Operation/WorkerRun events need an operation id; the domain family carries none")
    type_name = event_type_name(event_type, schema_version, aggregate_type)
    occurred = to_rfc3339(occurred_at)
    actor: dict[str, Any] = {"type": actor_type}
    if actor_id is not None:
        actor["id"] = str(actor_id)
    data: dict[str, Any] = {
        "eventId": str(event_id), "schemaVersion": schema_version, "aggregateType": aggregate_type, "aggregateId": str(aggregate_id),
        "aggregateSequence": sequence, "aggregateVersion": version, "organizationId": str(organization_id), "projectId": str(project_id),
        "occurredAt": occurred, "actor": actor, "correlationId": str(correlation_id)}
    if operation_id is not None:
        data["operationId"] = str(operation_id)
    if causation_id is not None:
        data["causationId"] = str(causation_id)
    if reason_code is not None:
        data["reasonCode"] = reason_code
    if from_status is not None or to_status is not None:
        data["transition"] = {"from": from_status, "to": to_status}
    if refs:
        data["refs"] = [
            {"resourceType": r.resource_type, "resourceId": str(r.resource_id), **({"versionId": str(r.version_id)} if r.version_id else {})} for r in refs]
    if details:
        if domain:  # the older message family defines its identifiers directly under `data` (AsyncAPI v1.6), never nested
            clash = set(details) & set(data)
            if clash:
                raise ValueError(f"event details may not redefine envelope fields: {sorted(clash)}")
            data.update(details)
        else:
            data["details"] = dict(details)
    return {
        "specversion": "1.0", "id": str(event_id), "source": SOURCES[aggregate_type], "type": type_name, "subject": subject_for(aggregate_type, aggregate_id),
        "time": occurred, "datacontenttype": "application/json", "dataschema": DATASCHEMA_PREFIX + type_name, "data": data}
