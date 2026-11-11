# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Operation aggregate persistence (Blueprint §3, TX-01). Statuses are validated by the database vocabulary; transition legality is the domain service's (S13)."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import bind_value
from ai_res.modules.events.aggregate_events import AggregateKind, AppendedEvent, EventSpec, append_event, validate_transition_spec
from ai_res.platform.clock import utc_now
from ai_res.platform.problems import ErrorCode, ProblemError

# WORKING (Architecture Decision v1.6 §2.6 / ADR-051): the exact operation_type registry is not final. Must equal operations.operation_types
# (tests/integration/postgres/test_migration_safety.py); extending it needs an Alembic revision AND this tuple, never one without the other.
OPERATION_TYPES = frozenset({"MANAGER_MESSAGE", "TASK_EXECUTION", "SOURCE_INGESTION", "PLAN_EXECUTION"})
TERMINAL = frozenset({"SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED"})
OPERATION_KIND = AggregateKind(
    aggregate_type="OPERATION", table="operations.operations", events_table="operations.operation_events", fk_column="operation_id",
    mutable={"status": None, "started_at": None, "completed_at": None, "cancel_requested_at": None, "workflow_id": None, "workflow_run_id": None,
             "progress_version": None, "progress_snapshot": "jsonb", "result_ref": "jsonb", "problem_ref": "jsonb", "updated_by": None})


@dataclass(frozen=True)
class NewOperation:
    id: UUID
    organization_id: UUID
    project_id: UUID
    operation_type: str
    initiator_type: str
    idempotency_scope: str
    request_fingerprint: bytes
    completion_policy_version: str
    completion_policy_snapshot: Mapping[str, Any]
    correlation_id: UUID
    initiator_id: UUID | None = None
    causation_id: UUID | None = None
    parent_operation_id: UUID | None = None
    created_by: UUID | None = None


@dataclass(frozen=True)
class OperationRow:
    id: UUID
    organization_id: UUID
    project_id: UUID
    operation_type: str
    status: str
    row_version: int
    last_event_sequence: int
    completed_at: datetime | None


_COLUMNS = "id, organization_id, project_id, operation_type, status, row_version, last_event_sequence, completed_at"


class OperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, new: NewOperation, accepted: EventSpec) -> tuple[OperationRow, AppendedEvent]:
        """Operation (ACCEPTED) + first event + outbox rows, atomically with the caller's transaction."""
        await self._s.execute(text(
            "INSERT INTO operations.operations (id, organization_id, project_id, parent_operation_id, operation_type, status, initiator_type, initiator_id, idempotency_scope, "
            "request_fingerprint, completion_policy_version, completion_policy_snapshot, correlation_id, causation_id, created_by) VALUES (:id, :org, :prj, :parent, :otype, "
            "'ACCEPTED', :itype, :iid, :scope, :fp, :cpv, CAST(:cps AS jsonb), :corr, :cause, :by)"),
            {"id": new.id, "org": new.organization_id, "prj": new.project_id, "parent": new.parent_operation_id, "otype": new.operation_type,
             "itype": new.initiator_type, "iid": new.initiator_id, "scope": new.idempotency_scope, "fp": new.request_fingerprint,
             "cpv": new.completion_policy_version, "cps": bind_value(dict(new.completion_policy_snapshot), "jsonb"), "corr": new.correlation_id,
             "cause": new.causation_id, "by": new.created_by})
        appended = await append_event(self._s, OPERATION_KIND, aggregate_id=new.id, organization_id=new.organization_id, project_id=new.project_id,
                                      operation_id=new.id, expected_version=1, spec=accepted)
        row = await self.get(new.id)
        if row is None:  # the row was just written by this transaction: invisible means the tenant context changed underneath us
            raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
        return row, appended

    async def get(self, operation_id: UUID) -> OperationRow | None:
        r = (await self._s.execute(text(f"SELECT {_COLUMNS} FROM operations.operations WHERE id = :id"), {"id": operation_id})).mappings().first()  # noqa: S608
        return None if r is None else OperationRow(**r)

    async def transition(self, row: OperationRow, to_status: str, spec: EventSpec, **changes: Any) -> AppendedEvent:
        """CAS on `row.row_version`; a terminal status also stamps completed_at (CHECK: terminal <=> completed_at)."""
        validate_transition_spec(row.status, to_status, spec, changes)
        values: dict[str, Any] = {"status": to_status, **changes}
        if to_status in TERMINAL:
            values.setdefault("completed_at", utc_now())
        return await append_event(self._s, OPERATION_KIND, aggregate_id=row.id, organization_id=row.organization_id, project_id=row.project_id, operation_id=row.id,
                                  expected_version=row.row_version, spec=spec, changes=values)
