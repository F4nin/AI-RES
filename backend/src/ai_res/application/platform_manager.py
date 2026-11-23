"""Private application commands restricted to the resolved Manager or Plan execution."""
from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest
from uuid import UUID

from sqlalchemy import text

from ai_res.application.plan_execution import create_approved_task
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.epics.manager_proposals import ManagerProposalRepository, ProposalContent
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.operations.execution_authority import PlatformExecution
from ai_res.modules.operations.repository import OperationRepository
from ai_res.modules.tasks.plan_versions import PlanSnapshot
from ai_res.orchestration.contracts import OperationState
from ai_res.orchestration.manager_context import IssuedManagerContext, ManagerEpicContext
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError


class ManagerCredentialExpired(Exception):
    """A request expired while waiting for its Operation lock."""


@dataclass(frozen=True, slots=True, repr=False)
class AssignedManagerInput:
    operation_id: str
    message: str
    context: IssuedManagerContext | None = None


async def execute_manager_command(
    uow: UnitOfWork, execution: PlatformExecution, action: PlatformAction, draft: ProposalContent | None, *, expires_at: datetime,
    bound_assignment: tuple[UUID, UUID] | None = None, epic_context: bool = False,
) -> AssignedManagerInput | OperationState:
    operation = execution.operation
    oid = UUID(operation.operation_id)
    await uow.with_tenant(UUID(operation.organization_id), UUID(operation.project_id))
    repo = OperationRepository(uow.session)
    lock = await uow.session.execute(text("SELECT id FROM operations.operations WHERE id=:id FOR NO KEY UPDATE"), {"id": oid})
    if expires_at <= utc_now():
        raise ManagerCredentialExpired
    row = await repo.get(oid) if lock.scalar_one_or_none() is not None else None
    expected_type = "PLAN_EXECUTION" if action is PlatformAction.MATERIALIZE_PLAN_TASKS else "MANAGER_MESSAGE"
    if row is None or row.operation_type != expected_type:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Assigned Operation not found.")
    state = OperationState(operation.operation_id, row.status)

    if action is PlatformAction.READ_MANAGER_INPUT and row.status != "RUNNING":
        raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Manager intake is not running.")
    if action is PlatformAction.MATERIALIZE_PLAN_TASKS:
        if row.status != "RUNNING":
            return state
        plan = (await uow.session.execute(text("""
            SELECT v.snapshot,d.approved_items
            FROM work.plan_executions e
            JOIN work.plan_versions v ON v.id=e.plan_version_id
            JOIN governance.plan_version_decisions d ON d.id=e.decision_id AND d.plan_version_id=e.plan_version_id
            WHERE e.operation_id=:operation AND d.decision='APPROVE'
        """), {"operation": oid})).one_or_none()
        if plan is None:
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "No approved PlanVersion is assigned.")
        graph = PlanSnapshot.model_validate(plan.snapshot).graph()
        approved = frozenset(plan.approved_items)
        graph.validate_approval(approved)
        for item in graph.order():
            if item in approved:
                await create_approved_task(uow.session, oid, item, correlation_id=execution.correlation_id)
        await repo.transition(row, "WAITING_FOR_DEPENDENCY", EventSpec(
            "operation.waiting_for_dependency", 1, "MANAGER", execution.correlation_id, (DOMAIN_DESTINATION,),
            from_status="RUNNING", to_status="WAITING_FOR_DEPENDENCY",
        ))
        await _audit(uow, execution, "PLAN_TASKS_MATERIALIZED")
        return OperationState(operation.operation_id, "WAITING_FOR_DEPENDENCY")

    if action is PlatformAction.RECORD_MANAGER_DRAFT and row.status not in {"RUNNING", "SUCCEEDED"}:
        return state
    interaction = (await uow.session.execute(text("""
        SELECT id FROM work.manager_interactions WHERE operation_id=:operation
    """), {"operation": oid})).scalar_one_or_none()
    if interaction is None:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Assigned Manager interaction not found.")
    if action is PlatformAction.READ_MANAGER_INPUT:
        message = (await uow.session.execute(text("SELECT message FROM work.manager_interactions WHERE id=:id"),
                                             {"id": interaction})).scalar_one()
        context = None
        if epic_context:
            if bound_assignment is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Assigned context not found.")
            assignment_id, run_id = bound_assignment
            captured = (await uow.session.execute(text("""
                SELECT context_id,epic_state FROM platform.capture_manager_epic_context(:operation,:assignment,:run)
            """), {"operation": oid, "assignment": assignment_id, "run": run_id})).one_or_none()
            if captured is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Assigned context not found.")
            context = IssuedManagerContext(captured.context_id, ManagerEpicContext.model_validate(captured.epic_state))
        else:
            await _audit(uow, execution, "MANAGER_INPUT_READ")
        if expires_at <= utc_now():
            raise ManagerCredentialExpired
        return AssignedManagerInput(operation.operation_id, str(message), context)
    if action is not PlatformAction.RECORD_MANAGER_DRAFT or draft is None:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "A Manager draft is required.")
    if bound_assignment is not None:
        matches = (await uow.session.execute(text("""
            SELECT platform.manager_epic_context_matches_draft(:operation,:context)
        """), {"operation": oid, "context": draft.context_version_id})).scalar_one()
        if not matches or (epic_context and draft.context_version_id is None):
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Assigned Manager context does not match the draft.")
        if expires_at <= utc_now():
            raise ManagerCredentialExpired
    if row.status == "SUCCEEDED":
        recorded = (await uow.session.execute(text(
            "SELECT content_hash FROM work.manager_proposal_versions WHERE interaction_id=:interaction"
        ), {"interaction": interaction})).scalar_one_or_none()
        if recorded is None or not compare_digest(bytes(recorded), draft.digest()):
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "This completed intake has a different proposal.")
        return state
    proposal = await ManagerProposalRepository(uow.session).propose(row.organization_id, row.project_id, interaction, draft)
    await repo.transition(row, "SUCCEEDED", EventSpec(
        "operation.succeeded", 1, "MANAGER", execution.correlation_id, (DOMAIN_DESTINATION,),
        from_status="RUNNING", to_status="SUCCEEDED",
    ), result_ref={"id": str(proposal.id)})
    await _audit(uow, execution, "MANAGER_DRAFT_RECORDED")
    if expires_at <= utc_now():
        raise ManagerCredentialExpired
    return OperationState(operation.operation_id, "SUCCEEDED")


async def _audit(uow: UnitOfWork, execution: PlatformExecution, action: str) -> None:
    operation = execution.operation
    await SqlAuditWriter(uow.session).write(AuditRecord(
        action=action, outcome=AuditOutcome.SUCCEEDED, resource_type="OPERATION", actor_type="SERVICE",
        organization_id=operation.organization_id, project_id=operation.project_id, resource_id=operation.operation_id,
        request_id=str(execution.correlation_id),
    ))
