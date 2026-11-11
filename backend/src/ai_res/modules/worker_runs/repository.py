# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""WorkerRun aggregate + immutable WorkerResult persistence. Starting a run is a CAS that links the exact COMPLETED READY evaluation (ADR-052);
who may start it (Readiness Gate, final revalidation) is decided by the domain service before calling here."""
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.events.aggregate_events import AggregateKind, AppendedEvent, EventSpec, append_event, validate_transition_spec
from ai_res.platform.clock import utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.redaction import assert_no_sensitive_keys

TERMINAL = frozenset({"COMPLETED", "REWORK_REQUIRED", "REJECTED", "UNVERIFIED", "FAILED", "TIMED_OUT", "CANCELLED"})
WORKER_RUN_KIND = AggregateKind(
    aggregate_type="WORKER_RUN", table="agents.worker_runs", events_table="agents.worker_run_events", fk_column="worker_run_id",
    mutable={"status": None, "latest_readiness_evaluation_id": None, "started_with_readiness_evaluation_id": None, "started_at": None, "finished_at": None,
             "workflow_id": None, "workflow_run_id": None, "execution_envelope_ref": "jsonb", "result_ref": "jsonb", "problem_ref": "jsonb", "deadline_at": None,
             "updated_by": None})


@dataclass(frozen=True)
class NewWorkerRun:
    organization_id: UUID
    project_id: UUID
    operation_id: UUID
    task_id: UUID
    worker_definition_version_id: UUID
    context_package_version_id: UUID
    input_contract_version: str
    output_contract_version: str
    derived_from_worker_run_id: UUID | None = None
    derivation_reason: str | None = None
    attempt_number: int = 1
    created_by: UUID | None = None


@dataclass(frozen=True)
class WorkerRunRow:
    id: UUID
    organization_id: UUID
    project_id: UUID
    operation_id: UUID
    task_id: UUID
    status: str
    row_version: int
    last_event_sequence: int
    started_with_readiness_evaluation_id: UUID | None


_COLUMNS = "id, organization_id, project_id, operation_id, task_id, status, row_version, last_event_sequence, started_with_readiness_evaluation_id"


class WorkerRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, new: NewWorkerRun, created: EventSpec) -> tuple[WorkerRunRow, AppendedEvent]:
        rid = new_id()
        await self._s.execute(text(
            "INSERT INTO agents.worker_runs (id, organization_id, project_id, operation_id, task_id, worker_definition_version_id, status, derived_from_worker_run_id, "
            "derivation_reason, attempt_number, context_package_version_id, input_contract_version, output_contract_version, created_by) VALUES (:id, :org, :prj, :op, :task, :wdv, "
            "'CREATED', :derived, :reason, :attempt, :cpv, :icv, :ocv, :by)"),
            {"id": rid, "org": new.organization_id, "prj": new.project_id, "op": new.operation_id, "task": new.task_id, "wdv": new.worker_definition_version_id,
             "derived": new.derived_from_worker_run_id, "reason": new.derivation_reason, "attempt": new.attempt_number, "cpv": new.context_package_version_id,
             "icv": new.input_contract_version, "ocv": new.output_contract_version, "by": new.created_by})
        appended = await append_event(self._s, WORKER_RUN_KIND, aggregate_id=rid, organization_id=new.organization_id, project_id=new.project_id, operation_id=new.operation_id,
                                     expected_version=1, spec=created)
        row = await self.get(rid)
        if row is None:  # the row was just written by this transaction: invisible means the tenant context changed underneath us
            raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
        return row, appended

    async def get(self, run_id: UUID) -> WorkerRunRow | None:
        r = (await self._s.execute(text(f"SELECT {_COLUMNS} FROM agents.worker_runs WHERE id = :id"), {"id": run_id})).mappings().first()  # noqa: S608
        return None if r is None else WorkerRunRow(**r)

    async def transition(self, row: WorkerRunRow, to_status: str, spec: EventSpec, **changes: Any) -> AppendedEvent:
        validate_transition_spec(row.status, to_status, spec, changes)
        values: dict[str, Any] = {"status": to_status, **changes}
        if to_status in TERMINAL:
            values.setdefault("finished_at", utc_now())
        return await append_event(self._s, WORKER_RUN_KIND, aggregate_id=row.id, organization_id=row.organization_id, project_id=row.project_id, operation_id=row.operation_id,
                                  expected_version=row.row_version, spec=spec, changes=values)

    async def start(self, row: WorkerRunRow, evaluation_id: UUID, spec: EventSpec) -> AppendedEvent:
        """Links the evaluation used at dispatch (immutable afterwards) and moves the run to STARTING."""
        return await self.transition(row, "STARTING", spec, started_with_readiness_evaluation_id=evaluation_id, latest_readiness_evaluation_id=evaluation_id,
                                     started_at=utc_now())

    async def store_result(self, row: WorkerRunRow, contract_version: str, payload: Mapping[str, Any], created_by: UUID | None = None) -> UUID:
        """WorkerResult is immutable and unique per run; rework = a NEW WorkerRun with its own result (ADR-016)."""
        assert_no_sensitive_keys(payload, "payload")
        body = canonical_json(dict(payload))
        rid = new_id()
        await self._s.execute(text(
            "INSERT INTO agents.worker_results (id, organization_id, project_id, worker_run_id, contract_version, payload, payload_hash, created_by) "
            "VALUES (:id, :org, :prj, :run, :cv, CAST(:payload AS jsonb), :hash, :by)"),
            {"id": rid, "org": row.organization_id, "prj": row.project_id, "run": row.id, "cv": contract_version, "payload": body,
             "hash": hashlib.sha256(body.encode("utf-8")).digest(), "by": created_by})
        return rid
