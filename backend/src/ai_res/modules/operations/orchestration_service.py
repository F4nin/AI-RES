"""Application Service behind the internal Platform API for Manager/Temporal (Decision v1.6 §2.5, Spec v1.13 r.2-3, 14).

Only this service changes an Operation on behalf of the orchestrator: a transition is validated, versioned (CAS), evented and audited in ONE
transaction. Temporal's status is never copied blindly: the workflow reports a domain outcome and the service decides from the stored row. Both commands are
idempotent, so an Activity retry or a redelivered start can never create a second transition. The tenant scope in the request is a CLAIM: it is applied as
the transaction-local context and the Operation must then be visible under it (RLS), otherwise the answer is the same controlled 404 as for a missing one.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.repository import OperationRepository, OperationRow
from ai_res.modules.operations.state_machine import TERMINAL
from ai_res.orchestration.contracts import OperationFailure, OperationRef, OperationState, workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

_DONE_AFTER_START = frozenset({"RUNNING", "WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING", "CANCEL_REQUESTED"}) | TERMINAL


class OperationOrchestrationService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @staticmethod
    def _spec(event_type: str, correlation_id: UUID, *, to_status: str, from_status: str, reason: str | None = None) -> EventSpec:
        return EventSpec(event_type=event_type, schema_version=1, actor_type="SERVICE", correlation_id=correlation_id, destinations=(DOMAIN_DESTINATION,),
                         from_status=from_status, to_status=to_status, reason_code=reason)

    @staticmethod
    async def _load(uow: UnitOfWork, ref: OperationRef) -> OperationRow:
        await uow.with_tenant(UUID(ref.organization_id), UUID(ref.project_id))
        row = await OperationRepository(uow.session).get(UUID(ref.operation_id))
        if row is None or row.organization_id != UUID(ref.organization_id) or row.project_id != UUID(ref.project_id):
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Operation not found.")
        return row

    @staticmethod
    async def _audit(uow: UnitOfWork, ref: OperationRef, action: str, details: dict[str, str]) -> None:
        await SqlAuditWriter(uow.session).write(AuditRecord(
            action=action, outcome=AuditOutcome.SUCCEEDED, resource_type="OPERATION", resource_id=ref.operation_id, actor_type="SERVICE",
            organization_id=ref.organization_id, project_id=ref.project_id, details=details))

    async def acknowledge_start(self, ref: OperationRef, correlation_id: UUID) -> OperationState:
        async with UnitOfWork(self._factory) as uow:
            repo = OperationRepository(uow.session)
            row = await self._load(uow, ref)
            if row.status in _DONE_AFTER_START:
                return OperationState(ref.operation_id, row.status)  # idempotent: a retried Activity or a duplicate start changes nothing
            if row.status != "ACCEPTED" and row.status != "QUEUED":
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Unexpected Operation status.")  # unreachable; fail closed (5xx, not a lookup miss)
            workflow_id = workflow_id_for(UUID(ref.operation_id))
            if row.status == "ACCEPTED":
                queued = self._spec("operation.queued", correlation_id, from_status="ACCEPTED", to_status="QUEUED")
                await repo.transition(row, "QUEUED", queued, workflow_id=workflow_id)
                reread = await repo.get(row.id)  # the tenant context is set once per transaction: re-read, do not re-load
                if reread is None:
                    raise ProblemError(ErrorCode.INTERNAL_ERROR, "Operation vanished inside its own transaction.")
                row = reread
            started = self._spec("operation.started", correlation_id, from_status="QUEUED", to_status="RUNNING")
            await repo.transition(row, "RUNNING", started, started_at=utc_now())
            await self._audit(uow, ref, "OPERATION_START_ACKNOWLEDGED", {"workflowId": workflow_id})
        return OperationState(ref.operation_id, "RUNNING")

    async def record_failure(self, failure: OperationFailure, correlation_id: UUID) -> OperationState:
        ref = failure.operation
        async with UnitOfWork(self._factory) as uow:
            row = await self._load(uow, ref)
            if row.status in TERMINAL:
                return OperationState(ref.operation_id, row.status)  # a terminal fact is never overwritten
            if row.status not in ("RUNNING", "CANCEL_REQUESTED"):
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "Operation is not running.")  # 412 = PERMANENT (state error); a lost CAS race is 409 = transient
            await OperationRepository(uow.session).transition(
                row, "FAILED",  # a real failure wins over a pending cancel
                self._spec("operation.failed", correlation_id, from_status=row.status, to_status="FAILED", reason=failure.code),
                problem_ref={"code": failure.code})
            await self._audit(uow, ref, "OPERATION_FAILED_BY_ORCHESTRATION", {"code": failure.code})
        return OperationState(ref.operation_id, "FAILED")

    async def confirm_cancellation(self, ref: OperationRef, correlation_id: UUID) -> OperationState:
        """Reconciliation before CANCELLED: only a CANCEL_REQUESTED Operation with no active WorkerRun becomes CANCELLED. A terminal status that already exists
        wins (an action that really completed is never reported as cancelled); with active branches the Operation stays CANCEL_REQUESTED (cleanup pending)."""
        async with UnitOfWork(self._factory) as uow:
            row = await self._load(uow, ref)
            if row.status != "CANCEL_REQUESTED":
                return OperationState(ref.operation_id, row.status)
            active = (await uow.session.execute(text(
                "SELECT count(*) FROM agents.worker_runs WHERE operation_id = :o "
                "AND status NOT IN ('COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED','FAILED','TIMED_OUT','CANCELLED')"), {"o": row.id})).scalar_one()
            if active:
                return OperationState(ref.operation_id, row.status)
            confirmed = self._spec("operation.cancelled", correlation_id, from_status="CANCEL_REQUESTED", to_status="CANCELLED",
                                   reason="CANCELLATION_CONFIRMED")
            await OperationRepository(uow.session).transition(row, "CANCELLED", confirmed)
            await self._audit(uow, ref, "OPERATION_CANCELLATION_CONFIRMED", {})
        return OperationState(ref.operation_id, "CANCELLED")
