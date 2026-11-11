# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Projection update + aggregate event + Outbox rows in ONE transaction (TX-01, coding-standards: Events and Outbox).

The caller's Unit of Work owns BEGIN/COMMIT. Sequence allocation is `UPDATE ... last_event_sequence + 1 ... RETURNING` under the aggregate row lock with
a row_version compare-and-swap (never MAX()+1); the database re-checks contiguity at COMMIT (platform.assert_event_sequence_contiguous) and that every
outbox row describes a real event (audit.assert_outbox_matches_event). At least one destination is mandatory here, which closes G-54 for repository users.
Event data must not carry secrets: sensitive keys are rejected, never silently redacted (a mutated payload would be a different event).
The envelope is the AsyncAPI v1.6 canonical CloudEvent (modules/events/envelope.py, G-56 option A); `EventSpec.data` becomes `data.details`.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json, raise_conflict_or_not_found, set_clause
from ai_res.modules.events.envelope import SOURCES, EventRef, build_envelope, subject_for, validate_event_identity
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.redaction import assert_no_sensitive_keys

MAX_DESTINATION_LEN = 200


@dataclass(frozen=True)
class AggregateKind:
    """Frozen description of an event-sourced-style aggregate table pair. Never built from external input."""
    aggregate_type: str
    table: str
    events_table: str
    fk_column: str
    mutable: Mapping[str, str | None]


@dataclass(frozen=True)
class EventSpec:
    """`event_type` is the short registry name (`operation.started`); `source`/`subject`/`type`/`dataschema` are derived, never supplied by the caller."""
    event_type: str
    schema_version: int
    actor_type: str
    correlation_id: UUID
    destinations: tuple[str, ...]
    data: Mapping[str, Any] = field(default_factory=dict)
    actor_id: UUID | None = None
    causation_id: UUID | None = None
    reason_code: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    occurred_at: datetime | None = None
    refs: tuple[EventRef, ...] = ()


@dataclass(frozen=True)
class AppendedEvent:
    event_id: UUID
    aggregate_sequence: int
    row_version: int


def validate_transition_spec(current_status: str, to_status: str, spec: EventSpec, changes: Mapping[str, Any]) -> None:
    """The event must describe the change that is really written (it cannot say RUNNING -> X while the row goes elsewhere)."""
    if "status" in changes:
        raise ValueError("the target status is the explicit `to_status` argument, not a change entry")
    if spec.from_status not in (None, current_status):
        raise ValueError(f"event from_status {spec.from_status!r} does not match the current status {current_status!r}")
    if spec.to_status not in (None, to_status):
        raise ValueError(f"event to_status {spec.to_status!r} does not match the target status {to_status!r}")


_REASON_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_RESOURCE_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")


def _validate(kind: AggregateKind, spec: EventSpec) -> None:
    validate_event_identity(kind.aggregate_type, spec.event_type, spec.schema_version, spec.actor_type)
    if not spec.destinations or len(set(spec.destinations)) != len(spec.destinations):
        raise ValueError("an event needs at least one unique outbox destination")
    if any(not d or len(d) > MAX_DESTINATION_LEN for d in spec.destinations):
        raise ValueError("invalid outbox destination")
    assert_no_sensitive_keys(spec.data)
    if spec.reason_code is not None and not _REASON_CODE.fullmatch(spec.reason_code):
        raise ValueError("reason code must be an upper-case machine code")
    if any(not _RESOURCE_TYPE.fullmatch(r.resource_type) for r in spec.refs):  # refs carry identifiers only; the type is a name (registry of types is WORKING), never free text
        raise ValueError("invalid resource type in an event reference")


_INSERT_OUTBOX = text(
    "INSERT INTO audit.outbox_events (id, organization_id, project_id, event_id, destination, aggregate_type, aggregate_id, aggregate_sequence, event_type, "
    "schema_version, envelope) VALUES (:id, :org, :prj, :event_id, :destination, :atype, :aid, :seq, :etype, :schema_version, CAST(:envelope AS jsonb))")


async def append_event(session: AsyncSession, kind: AggregateKind, *, aggregate_id: UUID, organization_id: UUID, project_id: UUID, operation_id: UUID,
                       expected_version: int, spec: EventSpec, changes: Mapping[str, Any] | None = None) -> AppendedEvent:
    _validate(kind, spec)
    event_id, occurred = new_id(), require_utc(spec.occurred_at) if spec.occurred_at else utc_now()  # every ValueError is raised before the counter moves
    params: dict[str, Any] = {"id": aggregate_id, "expected": expected_version}
    sets = ["last_event_sequence = last_event_sequence + 1", "row_version = row_version + 1", *set_clause(changes or {}, kind.mutable, params)]
    row = (await session.execute(text(
        f"UPDATE {kind.table} SET {', '.join(sets)} WHERE id = :id AND row_version = :expected RETURNING last_event_sequence, row_version"), params)).first()  # noqa: S608 - frozen kind
    if row is None:
        await raise_conflict_or_not_found(session, kind.table, aggregate_id)
    sequence, version = int(row[0]), int(row[1])
    await session.execute(text(
        f"INSERT INTO {kind.events_table} (event_id, {kind.fk_column}, aggregate_sequence, aggregate_version, event_type, schema_version, source, subject, occurred_at, "  # noqa: S608
        "correlation_id, causation_id, actor_type, actor_id, reason_code, from_status, to_status, data) VALUES (:event_id, :aid, :seq, :ver, :etype, :sv, :source, :subject, "
        ":occurred, :corr, :cause, :actor_type, :actor_id, :reason, :from_status, :to_status, CAST(:data AS jsonb))"),
        {"event_id": event_id, "aid": aggregate_id, "seq": sequence, "ver": version, "etype": spec.event_type, "sv": spec.schema_version, "source": SOURCES[kind.aggregate_type],
         "subject": subject_for(kind.aggregate_type, aggregate_id), "occurred": occurred, "corr": spec.correlation_id, "cause": spec.causation_id, "actor_type": spec.actor_type,
         "actor_id": spec.actor_id, "reason": spec.reason_code, "from_status": spec.from_status, "to_status": spec.to_status,
         "data": canonical_json(dict(spec.data))})
    attributes = build_envelope(
        aggregate_type=kind.aggregate_type, aggregate_id=aggregate_id, event_id=event_id, sequence=sequence, version=version, occurred_at=occurred,
        organization_id=organization_id, project_id=project_id, operation_id=operation_id, event_type=spec.event_type, schema_version=spec.schema_version,
        actor_type=spec.actor_type, actor_id=spec.actor_id, correlation_id=spec.correlation_id, causation_id=spec.causation_id, reason_code=spec.reason_code,
        from_status=spec.from_status, to_status=spec.to_status, details=spec.data, refs=spec.refs)
    envelope = canonical_json(attributes)
    for destination in spec.destinations:
        await session.execute(_INSERT_OUTBOX, {"id": new_id(), "org": organization_id, "prj": project_id, "event_id": event_id, "destination": destination,
                                               "atype": kind.aggregate_type, "aid": aggregate_id, "seq": sequence, "etype": spec.event_type,
                                               "schema_version": spec.schema_version, "envelope": envelope})
    return AppendedEvent(event_id, sequence, version)
