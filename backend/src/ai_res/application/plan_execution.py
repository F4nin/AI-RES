"""Materialization of approved PlanItems under a platform-owned PLAN_EXECUTION."""
import hashlib
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import metrics
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.events.aggregate_events import AggregateKind, EventSpec, append_event
from ai_res.modules.events.envelope import DOMAIN_DESTINATION, EventRef
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.repository import NewOperation, OperationRepository
from ai_res.modules.tasks.plan_versions import PlanSnapshot
from ai_res.modules.tasks.repository import NewTask, TaskRepository
from ai_res.orchestration.contracts import EXECUTION_ASSIGNMENT_REF, START_DESTINATION
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

_TASK = AggregateKind("TASK", "work.tasks", "work.task_events", "task_id", {})
_APPROVALS_PREPARED = metrics.get_meter(__name__).create_counter("ai_res.plan.approval.prepared")


async def prepare_plan_execution(
    session: AsyncSession, organization_id: UUID, project_id: UUID, version_id: UUID, decision_id: UUID, correlation_id: UUID,
    *, dispatch_namespace: str | None = None, causation_id: UUID | None = None,
) -> UUID:
    """Uses a current authorized tenant context. The dispatcher is attached after transport admission."""
    approved = (await session.execute(text("""
        SELECT d.approved_items,v.version_number,p.last_version
        FROM governance.plan_version_decisions d
        JOIN work.plan_versions v ON v.id=d.plan_version_id
        JOIN work.plans p ON p.id=v.plan_id
        WHERE d.organization_id=:org AND d.project_id=:project AND d.plan_version_id=:version AND d.id=:decision
          AND d.decision='APPROVE'
        FOR UPDATE OF p
    """), {"org": organization_id, "project": project_id, "version": version_id, "decision": decision_id})).one_or_none()
    if approved is None:
        raise ProblemError(ErrorCode.VERSION_CONFLICT, "A current approved PlanVersion is required.")
    exists = (await session.execute(text("""
        SELECT operation_id FROM work.plan_executions WHERE decision_id=:decision
    """), {"decision": decision_id})).scalar_one_or_none()
    if exists is not None:
        return UUID(str(exists))
    if approved.version_number != approved.last_version:
        raise ProblemError(ErrorCode.VERSION_CONFLICT, "A current approved PlanVersion is required.")
    operation_id = new_id()
    assignment = new_id() if dispatch_namespace is not None else None
    destinations = (DOMAIN_DESTINATION, START_DESTINATION) if assignment is not None else (DOMAIN_DESTINATION,)
    refs = (EventRef(EXECUTION_ASSIGNMENT_REF, assignment),) if assignment is not None else ()
    await OperationRepository(session).create(
        NewOperation(
            id=operation_id, organization_id=organization_id, project_id=project_id, operation_type="PLAN_EXECUTION",
            initiator_type="MANAGER", idempotency_scope=f"plan-execution:{decision_id}",
            request_fingerprint=hashlib.sha256(decision_id.bytes).digest(),
            completion_policy_version="plan-approved-items/1",
            completion_policy_snapshot={"requiredPlanItems": [str(item) for item in approved.approved_items]},
            correlation_id=correlation_id,
        ),
        EventSpec("operation.accepted", 1, "MANAGER", correlation_id, destinations, refs=refs, causation_id=causation_id,
                  data={"operationType": "PLAN_EXECUTION"}, dispatch_namespace=dispatch_namespace),
    )
    if assignment is not None and dispatch_namespace is not None:
        await OperationAssignments(session).register(
            operation_id, namespace=dispatch_namespace, assignment_id=assignment,
            actions=frozenset({PlatformAction.ACKNOWLEDGE_START, PlatformAction.RECORD_FAILURE, PlatformAction.CONFIRM_CANCELLATION,
                              PlatformAction.MATERIALIZE_PLAN_TASKS}),
        )
    await session.execute(text("""
        INSERT INTO work.plan_executions(organization_id,project_id,operation_id,plan_version_id,decision_id)
        VALUES (:org,:project,:operation,:plan_version,:decision)
    """), {"org": organization_id, "project": project_id, "operation": operation_id, "plan_version": version_id, "decision": decision_id})
    await SqlAuditWriter(session).write(AuditRecord(
        action="PLAN_EXECUTION_PREPARED", outcome=AuditOutcome.SUCCEEDED, resource_type="OPERATION", actor_type="SYSTEM",
        resource_id=str(operation_id), organization_id=str(organization_id), project_id=str(project_id), request_id=str(correlation_id),
    ))
    return operation_id


async def create_approved_task(
    session: AsyncSession, operation_id: UUID, item_id: UUID, *, actor_id: UUID | None = None, correlation_id: UUID | None = None,
) -> UUID:
    """Call in the authorized tenant transaction after the Operation has started."""
    bound = (await session.execute(text("""
        SELECT e.organization_id,e.project_id,p.epic_id,v.snapshot,d.approved_items
        FROM work.plan_executions e
        JOIN work.plan_versions v ON v.id=e.plan_version_id
        JOIN work.plans p ON p.id=v.plan_id
        JOIN operations.operations o ON o.id=e.operation_id
        JOIN governance.plan_version_decisions d ON d.id=e.decision_id AND d.plan_version_id=e.plan_version_id
        WHERE e.operation_id=:operation AND o.operation_type='PLAN_EXECUTION' AND o.status='RUNNING' AND d.decision='APPROVE'
        FOR SHARE OF o
    """), {"operation": operation_id})).one_or_none()
    if bound is None or item_id not in bound.approved_items:
        raise ProblemError(ErrorCode.ACCESS_DENIED, "The PlanItem is outside the active approved execution.")
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                          {"key": f"plan-task:{operation_id}:{item_id}"})
    mapped_tasks = await session.execute(text("""
        SELECT item_id,task_id FROM work.plan_item_tasks WHERE operation_id=:operation
    """), {"operation": operation_id})
    mapping: dict[UUID, UUID] = {row.item_id: row.task_id for row in mapped_tasks}
    if item_id in mapping:
        return UUID(str(mapping[item_id]))
    snapshot = PlanSnapshot.model_validate(bound.snapshot)
    item = next((item for item in snapshot.items if item.id == item_id), None)
    if item is None or any(p not in mapping for p in item.predecessors):
        raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The PlanItem predecessors have not been materialized.")
    tasks = TaskRepository(session)
    task = await tasks.create_task(NewTask(
        bound.organization_id, bound.project_id, operation_id, bound.epic_id, item.task_type, item.title, "PROPOSED", "MANAGER",
        description=item.description, acceptance_criteria=item.acceptance_criteria,
    ))
    for predecessor in item.predecessors:
        await tasks.add_dependency(bound.organization_id, bound.project_id, task.id, mapping[predecessor])
    await session.execute(text("""
        INSERT INTO work.plan_item_tasks(organization_id,project_id,operation_id,item_id,task_id)
        VALUES (:org,:project,:operation,:item,:task)
    """), {"org": bound.organization_id, "project": bound.project_id, "operation": operation_id, "item": item_id, "task": task.id})
    await append_event(
        session, _TASK, aggregate_id=task.id, organization_id=bound.organization_id, project_id=bound.project_id,
        operation_id=None, expected_version=task.row_version,
        spec=EventSpec("task.created", 1, "USER" if actor_id else "MANAGER", correlation_id or new_id(), (DOMAIN_DESTINATION,),
                       actor_id=actor_id, data={"taskId": str(task.id), "epicId": str(bound.epic_id)}),
    )
    return task.id


@dataclass(frozen=True, slots=True)
class RequestedTask:
    title: str
    task_type: str
    description: str | None
    acceptance_criteria: tuple[str, ...]


async def create_matching_approved_task(
    session: AsyncSession, epic_id: UUID, requested: RequestedTask, *, actor_id: UUID | None = None, correlation_id: UUID | None = None,
) -> UUID:
    """Public v1.3 request resolves an exact, unique match within its authorized Epic."""
    plan_id = (await session.execute(text("SELECT id FROM work.plans WHERE epic_id=:epic FOR SHARE"),
                                     {"epic": epic_id})).scalar_one_or_none()
    if plan_id is None:
        raise ProblemError(ErrorCode.OPERATION_NOT_READY, "No active approved plan item matches the request.")
    candidates = (await session.execute(text("""
        SELECT e.operation_id,v.snapshot,d.approved_items
        FROM work.plan_executions e
        JOIN work.plan_versions v ON v.id=e.plan_version_id
        JOIN operations.operations o ON o.id=e.operation_id
        JOIN governance.plan_version_decisions d ON d.id=e.decision_id AND d.plan_version_id=e.plan_version_id
        WHERE v.plan_id=:plan AND o.operation_type='PLAN_EXECUTION' AND o.status='RUNNING' AND d.decision='APPROVE'
        ORDER BY e.operation_id FOR SHARE OF o
    """), {"plan": plan_id})).all()
    matches: list[tuple[UUID, UUID]] = []
    for candidate in candidates:
        snapshot = PlanSnapshot.model_validate(candidate.snapshot)
        approved = frozenset(candidate.approved_items)
        for item in snapshot.items:
            if item.id in approved and RequestedTask(item.title, item.task_type, item.description, item.acceptance_criteria) == requested:
                matches.append((candidate.operation_id, item.id))
    if not matches:
        raise ProblemError(ErrorCode.OPERATION_NOT_READY, "No active approved plan item matches the request.")
    if len(matches) != 1:
        raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "More than one approved plan item matches the request.")
    operation_id, item_id = matches[0]
    return await create_approved_task(session, operation_id, item_id, actor_id=actor_id, correlation_id=correlation_id)


async def prepare_approved_plan_event(session: AsyncSession, event_id: UUID, *, dispatch_namespace: str) -> UUID:
    """Prepare one execution from a committed PlanVersionApproved event in the current tenant UoW."""
    approved = (await session.execute(text("""
        SELECT v.organization_id, v.project_id, e.plan_version_id, d.id AS decision_id, e.correlation_id
        FROM work.plan_version_events e
        JOIN work.plan_versions v ON v.id=e.plan_version_id
        JOIN governance.plan_version_decisions d ON d.plan_version_id=e.plan_version_id AND d.approver_id=e.actor_id
        WHERE e.event_id=:event AND e.event_type='plan.version.approved' AND e.schema_version=1
          AND e.actor_type='USER' AND d.decision='APPROVE' AND d.content_hash=v.content_hash
    """), {"event": event_id})).one_or_none()
    if approved is None:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Approved plan event not found.")
    return await prepare_plan_execution(
        session, approved.organization_id, approved.project_id, approved.plan_version_id, approved.decision_id, approved.correlation_id,
        dispatch_namespace=dispatch_namespace, causation_id=event_id,
    )


async def prepare_approved_plan_page(
    factory: async_sessionmaker[AsyncSession], organization_id: UUID, project_id: UUID, *, dispatch_namespace: str, page_size: int,
) -> int:
    """Consume committed approvals within a trusted project using the existing decision-to-execution marker."""
    if page_size < 1:
        raise ValueError("an approval page must contain at least one slot")
    prepared = 0
    query = text("""
        SELECT e.event_id, d.id AS decision_id
        FROM work.plan_version_events e
        JOIN work.plan_versions v ON v.id=e.plan_version_id
        JOIN work.plans p ON p.id=v.plan_id AND p.last_version=v.version_number
        JOIN governance.plan_version_decisions d ON d.plan_version_id=v.id AND d.approver_id=e.actor_id
        WHERE v.organization_id=:org AND v.project_id=:project
          AND e.event_type='plan.version.approved' AND e.schema_version=1 AND e.actor_type='USER'
          AND d.decision='APPROVE' AND d.content_hash=v.content_hash
          AND NOT EXISTS (SELECT 1 FROM work.plan_executions x WHERE x.decision_id=d.id)
        ORDER BY p.id
        LIMIT 1
        FOR UPDATE OF p SKIP LOCKED
    """)
    for _ in range(page_size):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(organization_id, project_id)
            candidate = (await uow.session.execute(query, {"org": organization_id, "project": project_id})).one_or_none()
            if candidate is None:
                break
            # Recheck with a fresh snapshot after acquiring the Plan lock.
            existing = (await uow.session.execute(text("""
                SELECT 1 FROM work.plan_executions WHERE decision_id=:decision
            """), {"decision": candidate.decision_id})).scalar_one_or_none()
            if existing is not None:
                continue
            await prepare_approved_plan_event(uow.session, candidate.event_id, dispatch_namespace=dispatch_namespace)
        _APPROVALS_PREPARED.add(1)
        prepared += 1
    return prepared
