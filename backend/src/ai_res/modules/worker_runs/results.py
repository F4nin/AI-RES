"""Application Service that stores a WorkerResult (S14). The only write path: a Worker never writes `agents.worker_results` itself (api-and-contracts.md).

Order: contract validation at RESULT_RECEIPT (fail-closed) -> the run is re-read from the database under the caller's tenant context (a run of another
tenant is invisible: 404, no existence leak) -> the result must belong to this run, task and the run's Worker role -> immutable insert of the VALIDATED
SNAPSHOT (never the caller's object, which may change between check and write). The role comes from the WorkerDefinition registry row the run points to
(ADR-102), never from the payload's own claim. A run that has not started or is terminal, and a second result for the run, are refused by the database
(triggers of 0004) and reported as STATE_TRANSITION_NOT_ALLOWED; rework is a NEW WorkerRun with its own result (ADR-016)."""
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.worker_runs.repository import WorkerRunRepository, WorkerRunRow
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.worker_contracts import ContractViolation, ValidationPoint, WorkerContracts

_FOREIGN_KEY, _INTEGRITY_TRIGGER = "23503", "23000"  # PostgreSQL SQLSTATEs: foreign_key_violation; integrity_constraint_violation (raised by the 0004 guards)


def _violation_problem(violation: ContractViolation) -> ProblemError:
    return ProblemError(ErrorCode.VALIDATION_ERROR, f"WorkerResult rejected: {violation.reason.value}",
                        errors=[{"field": e.split(":")[0], "code": violation.reason.value} for e in violation.errors] or None)


async def store_worker_result(session: AsyncSession, contracts: WorkerContracts, run: WorkerRunRow, payload: Mapping[str, Any], *,
                              created_by: UUID | None = None) -> UUID:
    """`run` only names the target: its identity is re-read from the database, and a different organization/project/task in `run` is refused."""
    try:
        model, snapshot = contracts.check_snapshot("result", payload, ValidationPoint.RESULT_RECEIPT)
    except ContractViolation as violation:
        raise _violation_problem(violation) from None
    found = (await session.execute(
        text("SELECT r.organization_id, r.project_id, r.task_id, d.worker_role FROM agents.worker_runs r "
             "JOIN agents.worker_definition_versions v ON v.id = r.worker_definition_version_id "
             "JOIN agents.worker_definitions d ON d.id = v.worker_definition_id WHERE r.id = :id"), {"id": run.id})).one_or_none()
    if found is None or (found.organization_id, found.project_id) != (run.organization_id, run.project_id):
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "WorkerRun not found")
    if model.worker_run_id != run.id or model.task_id != found.task_id or model.worker_role != found.worker_role:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "WorkerResult does not belong to this WorkerRun, task or Worker role")
    try:
        async with session.begin_nested():  # the savepoint keeps the caller's transaction usable after a refused insert
            return await WorkerRunRepository(session).store_result(run, model.contract_version, snapshot, created_by)
    except DataError:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "WorkerResult rejected: not storable") from None  # the database refused a value; never echo it
    except IntegrityError as error:
        code = getattr(error.orig, "sqlstate", None)
        if code == _FOREIGN_KEY:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "WorkerRun not found") from None
        if code in {"23505", _INTEGRITY_TRIGGER}:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
                               "a WorkerResult cannot be stored: the run has not started, is terminal or already has one (rework = a new WorkerRun)") from None
        raise
