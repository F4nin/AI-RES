"""Apply a terminal G-107 observation to the exact captured Operation version."""
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from opentelemetry import metrics, trace
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.observe_operations import BoundExecutionObservationRequest, TemporalExecutionObserver
from ai_res.application.reconcile_effects import (
    POST_ACK_STATUSES,
    TERMINAL_EXECUTIONS,
    WORKFLOW_FAILURE_CODES,
    EffectReconciliation,
    reconcile_post_ack_effects,
)
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.operations.execution_authority import OperationAssignments, assigned_input_digest
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState
from ai_res.modules.operations.repository import OperationRepository
from ai_res.modules.operations.state_machine import TERMINAL
from ai_res.orchestration.contracts import (
    ASSIGNED_WORKFLOW_TYPES,
    CONTRACT_VERSION,
    MANAGER_TASK_QUEUE,
    AssignedCancellation,
    AssignedWorkflowInput,
    OperationRef,
    workflow_id_for,
)
from ai_res.platform.concurrency import AggregateVersionConflict
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

_PRE_ACK_STATUSES = frozenset({"ACCEPTED", "QUEUED", "CANCEL_REQUESTED"})
_OBSERVATIONS = metrics.get_meter(__name__).create_counter("ai_res.operation.reconciliation.observations")
_EFFECTS = metrics.get_meter(__name__).create_counter("ai_res.operation.reconciliation.effects")


async def has_settled_cancellation(factory: async_sessionmaker[AsyncSession], request: AssignedCancellation, *, namespace: str) -> bool:
    """Backend proof for Outbox replay once the exact cancellation no longer needs a signal."""
    async with UnitOfWork(factory) as uow:
        operation = request.operation
        await uow.with_tenant(UUID(operation.organization_id), UUID(operation.project_id))
        result = await uow.session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.id=:assignment AND a.operation_id=:operation AND a.workflow_id=:workflow
                  AND a.workflow_run_id=:run AND a.namespace=:namespace AND a.task_queue=:queue
                  AND a.workflow_contract_version=:major AND o.cancel_requested_at IS NOT NULL AND o.status=ANY(:terminal)
            )
        """), {"assignment": request.assignment_id, "operation": UUID(operation.operation_id),
               "workflow": workflow_id_for(UUID(operation.operation_id)), "run": request.workflow_run_id,
               "namespace": namespace, "queue": MANAGER_TASK_QUEUE, "major": CONTRACT_VERSION, "terminal": sorted(TERMINAL)})
        return bool(result.scalar_one())


@dataclass(frozen=True, slots=True)
class TerminalWorkflowEvidence:
    """Created by the trusted, purpose-bound Temporal observer following ADR-129."""
    assignment_id: UUID
    operation_id: UUID
    workflow_id: str
    workflow_run_id: UUID
    expected_operation_version: int
    state: ExecutionState


class BoundExecutionObserver(Protocol):
    async def observe(self, request: BoundExecutionObservationRequest) -> ExecutionObservation: ...


@dataclass(frozen=True, slots=True)
class BoundStartPage:
    checked: int
    corrected: int
    next_after: UUID | None
    timed_out: bool = False


async def reconcile_bound_start_page(
    factory: async_sessionmaker[AsyncSession], observer: BoundExecutionObserver, *, organization_id: UUID, project_id: UUID,
    admitted_types: frozenset[str], page_size: int, after: UUID | None = None, timeout_seconds: float | None = None,
    include_post_ack: bool = False,
) -> BoundStartPage:
    """Check one page for a trusted Backend scope. Start a new scan at None after the last page."""
    if page_size < 1:
        raise ValueError("reconciliation page size must be positive")
    operation_types = sorted(admitted_types.intersection(ASSIGNED_WORKFLOW_TYPES))
    if not operation_types:
        return BoundStartPage(0, 0, None)

    query = text("""
        SELECT o.id
        FROM operations.operations o
        JOIN platform.operation_execution_assignments a ON a.operation_id=o.id
        WHERE o.organization_id=:organization AND o.project_id=:project
          AND ((o.started_at IS NULL AND o.status=ANY(:pre_ack))
               OR (o.started_at IS NOT NULL AND o.status=ANY(:post_ack)))
          AND o.operation_type=ANY(:types)
          AND a.revoked_at IS NULL AND a.workflow_run_id IS NOT NULL
          AND a.task_queue=:queue AND a.workflow_contract_version=:major
          AND (CAST(:after AS uuid) IS NULL OR o.id > :after)
        ORDER BY o.id
        LIMIT :limit
    """)
    parameters = {"organization": organization_id, "project": project_id, "types": operation_types, "after": after,
                  "limit": page_size + 1, "queue": MANAGER_TASK_QUEUE, "major": CONTRACT_VERSION, "pre_ack": sorted(_PRE_ACK_STATUSES),
                  "post_ack": sorted(POST_ACK_STATUSES) if include_post_ack else []}
    candidates: Sequence[UUID] = ()
    checked, corrected = 0, 0
    timed_out = False
    budget = asyncio.timeout(timeout_seconds)
    try:
        async with budget:
            async with UnitOfWork(factory) as uow:
                await uow.with_tenant(organization_id, project_id)
                candidates = (await uow.session.execute(query, parameters)).scalars().all()

            for operation_id in candidates[:page_size]:
                checked += 1
                operation = OperationRef(str(operation_id), str(organization_id), str(project_id))
                if await reconcile_bound_start(factory, observer, operation, admitted_types=admitted_types, include_post_ack=include_post_ack):
                    corrected += 1
    except TimeoutError:
        if not budget.expired() or checked == 0:
            raise
        timed_out = True
    # Even a timed-out candidate gets another turn after the next full scan.
    next_after = candidates[checked - 1] if len(candidates) > checked else None
    return BoundStartPage(checked, corrected, next_after, timed_out)


async def reconcile_bound_start(
    factory: async_sessionmaker[AsyncSession], observer: BoundExecutionObserver,
    operation: OperationRef, *, admitted_types: frozenset[str], include_post_ack: bool = False,
) -> bool:
    """Revalidate the known binding and reconcile a verified terminal observation."""
    organization_id, project_id = UUID(operation.organization_id), UUID(operation.project_id)
    operation_id = UUID(operation.operation_id)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(organization_id, project_id)
        row = await OperationRepository(uow.session).get(operation_id)
        if row is None or row.operation_type not in admitted_types:
            return False
        workflow_type = ASSIGNED_WORKFLOW_TYPES.get(row.operation_type)
        if workflow_type is None:
            return False
        binding = (await uow.session.execute(text("""
            SELECT a.id,a.namespace,a.workflow_run_id,o.started_at
            FROM platform.operation_execution_assignments a JOIN operations.operations o ON o.id=a.operation_id
            WHERE a.operation_id=:operation AND a.workflow_type=:type AND a.task_queue=:queue
              AND a.workflow_contract_version=:major AND a.revoked_at IS NULL AND a.workflow_run_id IS NOT NULL
              AND o.row_version=:version
              AND ((o.started_at IS NULL AND o.status=ANY(:pre_ack))
                   OR (o.started_at IS NOT NULL AND o.status=ANY(:post_ack)))
        """), {"operation": operation_id, "type": workflow_type, "queue": MANAGER_TASK_QUEUE,
               "major": CONTRACT_VERSION, "version": row.row_version, "pre_ack": sorted(_PRE_ACK_STATUSES),
               "post_ack": sorted(POST_ACK_STATUSES) if include_post_ack else []})).one_or_none()
        if binding is None:
            return False
        request = BoundExecutionObservationRequest(binding.id, operation_id, workflow_type, binding.workflow_run_id, binding.namespace)
        post_ack = binding.started_at is not None

    observation = await observer.observe(request)
    state = observation.state if observation.assignment_id == request.assignment_id else ExecutionState.SCOPE_MISMATCH
    attributes = {"outcome": state.value}
    _OBSERVATIONS.add(1, attributes)
    trace.get_current_span().add_event("operation.reconciliation.observation", attributes)
    if post_ack:
        if state not in TERMINAL_EXECUTIONS:
            return False
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(organization_id, project_id)
            effect = await reconcile_post_ack_effects(uow.session, request, row.row_version, state)
        effect_attributes = {"outcome": effect.value, "operation_type": row.operation_type}
        _EFFECTS.add(1, effect_attributes)
        trace.get_current_span().add_event("operation.reconciliation.effect", effect_attributes)
        return effect is EffectReconciliation.CORRECTED
    if state is ExecutionState.CANCELLED and row.status == "CANCEL_REQUESTED":
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(organization_id, project_id)
            return await _confirm_pre_ack_cancellation(uow, request, operation, row.row_version)
    if state not in WORKFLOW_FAILURE_CODES:
        return False
    evidence = TerminalWorkflowEvidence(
        request.assignment_id, operation_id, workflow_id_for(operation_id), request.workflow_run_id, row.row_version, state,
    )
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(organization_id, project_id)
        return await apply_reconciled_failure(uow.session, evidence, admitted_types=admitted_types)


async def _confirm_pre_ack_cancellation(
    uow: UnitOfWork, request: BoundExecutionObservationRequest, operation: OperationRef, version: int,
) -> bool:
    """Revalidate exact authority and no ACK under locks before confirming observed cancellation."""
    correlation = (await uow.session.execute(text("""
        SELECT correlation_id FROM platform.operation_execution_assignments
        WHERE id=:assignment AND operation_id=:operation AND workflow_id=:workflow AND workflow_run_id=:run
          AND namespace=:namespace AND workflow_type=:type AND task_queue=:queue AND workflow_contract_version=:major
          AND revoked_at IS NULL AND :action=ANY(allowed_actions)
        FOR SHARE
    """), {"assignment": request.assignment_id, "operation": request.operation_id, "workflow": workflow_id_for(request.operation_id),
           "run": request.workflow_run_id, "namespace": request.namespace, "type": request.workflow_type, "queue": MANAGER_TASK_QUEUE,
           "major": CONTRACT_VERSION, "action": PlatformAction.CONFIRM_CANCELLATION.value})).scalar_one_or_none()
    if correlation is None:
        return False
    locked = (await uow.session.execute(text("""
        SELECT id FROM operations.operations WHERE id=:operation AND row_version=:version
          AND started_at IS NULL AND status='CANCEL_REQUESTED' AND cancel_requested_at IS NOT NULL
        FOR NO KEY UPDATE
    """), {"operation": request.operation_id, "version": version})).scalar_one_or_none()
    row = await OperationRepository(uow.session).get(locked) if locked is not None else None
    if row is None or ASSIGNED_WORKFLOW_TYPES.get(row.operation_type) != request.workflow_type:
        return False
    result = await OperationOrchestrationService.confirm_loaded_cancellation(uow, row, operation, correlation)
    return result.status == "CANCELLED"


async def apply_reconciled_failure(
    session: AsyncSession, evidence: TerminalWorkflowEvidence, *, admitted_types: frozenset[str],
) -> bool:
    """Run in a tenant UoW after external I/O. False means stale, missing or unadmitted."""
    code = WORKFLOW_FAILURE_CODES.get(evidence.state)
    if code is None or evidence.workflow_id != workflow_id_for(evidence.operation_id):
        return False
    repo = OperationRepository(session)
    operation = await repo.get(evidence.operation_id)
    if (
        operation is None or operation.operation_type not in admitted_types
        or operation.row_version != evidence.expected_operation_version or operation.status not in _PRE_ACK_STATUSES
    ):
        return False
    binding = (await session.execute(text("""
        SELECT a.correlation_id FROM platform.operation_execution_assignments a JOIN operations.operations o ON o.id=a.operation_id
        WHERE a.id=:assignment AND a.operation_id=:operation AND a.workflow_id=:workflow AND a.workflow_run_id=:run AND a.revoked_at IS NULL
          AND a.workflow_type=:type AND a.task_queue=:queue AND a.workflow_contract_version=:major
          AND o.started_at IS NULL AND o.row_version=:version
        FOR SHARE OF a
    """), {"assignment": evidence.assignment_id, "operation": evidence.operation_id,
           "workflow": evidence.workflow_id, "run": evidence.workflow_run_id,
           "type": ASSIGNED_WORKFLOW_TYPES.get(operation.operation_type), "queue": MANAGER_TASK_QUEUE,
           "major": CONTRACT_VERSION, "version": evidence.expected_operation_version})).one_or_none()
    if binding is None:
        return False
    transition = EventSpec(
        "operation.failed", 1, "SYSTEM", binding.correlation_id, (DOMAIN_DESTINATION,),
        from_status=operation.status, to_status="FAILED", reason_code=code,
    )
    try:
        await repo.transition(operation, "FAILED", transition, problem_ref={"code": code})
    except AggregateVersionConflict:
        return False
    await SqlAuditWriter(session).write(AuditRecord(
        action="OPERATION_RECONCILED_FAILURE", outcome=AuditOutcome.SUCCEEDED, resource_type="OPERATION",
        actor_type="SYSTEM", resource_id=str(operation.id), organization_id=str(operation.organization_id),
        project_id=str(operation.project_id), request_id=str(binding.correlation_id), reason_code=code,
    ))
    return True


async def recover_unacknowledged_start(
    factory: async_sessionmaker[AsyncSession], observer: TemporalExecutionObserver,
    request: AssignedWorkflowInput, *, operation_type: str, namespace: str,
) -> bool:
    """The trusted reconciliation caller supplies the persisted intent. Observe before the tenant transaction."""
    run_id = await observer.discover_initial_run(request, operation_type, namespace)
    if run_id is None:
        return False
    return await bind_verified_initial_run(factory, request, operation_type=operation_type, namespace=namespace, run_id=run_id)


async def bind_verified_initial_run(
    factory: async_sessionmaker[AsyncSession], request: AssignedWorkflowInput, *, operation_type: str, namespace: str, run_id: UUID,
) -> bool:
    """Record the Run proven by the protected frontend or the trusted history observer."""
    workflow_type = ASSIGNED_WORKFLOW_TYPES.get(operation_type)
    if workflow_type is None:
        return False
    ref = request.operation
    oid, assignment = UUID(ref.operation_id), UUID(request.assignment_id)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(UUID(ref.organization_id), UUID(ref.project_id))
        matches = (await uow.session.execute(text("""
            SELECT a.id FROM platform.operation_execution_assignments a
            JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
            WHERE a.id=:assignment AND a.operation_id=:operation AND a.namespace=:namespace
              AND a.workflow_type=:type AND a.workflow_contract_version=:major AND a.input_digest=:digest
              AND a.task_queue=:queue
              AND a.revoked_at IS NULL AND o.operation_type=:operation_type
              AND (o.status IN ('ACCEPTED','QUEUED') OR a.workflow_run_id=:run)
            FOR NO KEY UPDATE OF a
        """), {"assignment": assignment, "operation": oid, "namespace": namespace,
               "type": workflow_type, "queue": MANAGER_TASK_QUEUE, "major": request.contract_version,
               "digest": assigned_input_digest(request), "operation_type": operation_type, "run": run_id})).scalar_one_or_none()
        return matches is not None and await OperationAssignments(uow.session).bind_run(assignment, oid, run_id)


async def has_confirmed_start(
    factory: async_sessionmaker[AsyncSession], request: AssignedWorkflowInput, *, operation_type: str, namespace: str,
) -> bool:
    """A stable execution binding proves prior dispatch when the Outbox acknowledgment was lost."""
    workflow_type = ASSIGNED_WORKFLOW_TYPES.get(operation_type)
    if workflow_type is None:
        return False
    ref = request.operation
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(UUID(ref.organization_id), UUID(ref.project_id))
        confirmed = await uow.session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON o.id=a.operation_id
                WHERE a.id=:assignment AND a.operation_id=:operation AND a.namespace=:namespace
                  AND a.workflow_type=:type AND a.workflow_contract_version=:major AND a.input_digest=:digest
                  AND a.revoked_at IS NULL AND a.workflow_run_id IS NOT NULL AND o.operation_type=:operation_type
            )
        """), {"assignment": UUID(request.assignment_id), "operation": UUID(ref.operation_id), "namespace": namespace,
               "type": workflow_type, "major": request.contract_version, "digest": assigned_input_digest(request), "operation_type": operation_type})
        return bool(confirmed.scalar_one())


async def prepare_assigned_start(
    factory: async_sessionmaker[AsyncSession], request: AssignedWorkflowInput, *, operation_type: str, namespace: str,
) -> bool:
    """Fence the outgoing RPC or settle an exact command cancelled before admission."""
    workflow_type = ASSIGNED_WORKFLOW_TYPES.get(operation_type)
    ref = request.operation
    oid, assignment = UUID(ref.operation_id), UUID(request.assignment_id)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(UUID(ref.organization_id), UUID(ref.project_id))
        target = (await uow.session.execute(text("""
            SELECT workflow_run_id,start_admitted FROM platform.operation_execution_assignments
            WHERE id=:assignment AND operation_id=:operation AND workflow_id=:workflow AND namespace=:namespace
              AND workflow_type=:type AND workflow_contract_version=:major AND input_digest=:digest
              AND task_queue=:queue AND revoked_at IS NULL
            FOR NO KEY UPDATE
        """), {"assignment": assignment, "operation": oid, "workflow": workflow_id_for(oid), "namespace": namespace, "type": workflow_type,
               "major": request.contract_version, "digest": assigned_input_digest(request), "queue": MANAGER_TASK_QUEUE})).one_or_none()
        operation = (await uow.session.execute(text("""
            SELECT operation_type,status,cancel_requested_at FROM operations.operations WHERE id=:operation
        """), {"operation": oid})).one_or_none()
        if target is None or operation is None or operation.operation_type != operation_type:
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Operation cannot be dispatched.")
        if target.workflow_run_id is not None or (
            operation.status == "CANCELLED" and operation.cancel_requested_at is not None and not target.start_admitted
        ):
            return False
        if operation.status != "ACCEPTED":
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Operation cannot be dispatched.")
        if not target.start_admitted:
            await uow.session.execute(text("""
                UPDATE platform.operation_execution_assignments SET start_admitted=true WHERE id=:assignment
            """), {"assignment": assignment})
        return True
