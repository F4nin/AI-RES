"""Trusted assignment issuance and exact binding for private operation callbacks."""
import hashlib
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import affected, canonical_json
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.orchestration.contracts import (
    ASSIGNED_WORKFLOW_TYPES,
    CONTRACT_VERSION,
    MANAGER_TASK_QUEUE,
    AssignedWorkflowInput,
    OperationRef,
    assert_compact,
    workflow_id_for,
)
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError


def assigned_input_digest(request: AssignedWorkflowInput) -> bytes:
    """Stable logical payload hash shared by dispatch and the trusted authorizer."""
    assert_compact(request)
    return hashlib.sha256(canonical_json(asdict(request)).encode("utf-8")).digest()


@dataclass(frozen=True, slots=True)
class PlatformExecution:
    operation: OperationRef
    correlation_id: UUID


class OperationAssignments:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self, operation_id: UUID, *, namespace: str, actions: frozenset[PlatformAction], assignment_id: UUID | None = None,
    ) -> AssignedWorkflowInput:
        """Issue an exact assignment for an admitted persisted Operation inside its tenant UoW."""
        operation = (await self._session.execute(text("""
            SELECT organization_id,project_id,operation_type,correlation_id
            FROM operations.operations WHERE id=:operation AND status='ACCEPTED' FOR SHARE
        """), {"operation": operation_id})).one_or_none()
        workflow_type = None if operation is None else ASSIGNED_WORKFLOW_TYPES.get(operation.operation_type)
        if operation is None or workflow_type is None:
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Operation cannot be assigned to a workflow.")
        assignment = assignment_id or new_id()
        request = AssignedWorkflowInput(
            CONTRACT_VERSION, OperationRef(str(operation_id), str(operation.organization_id), str(operation.project_id)), str(assignment),
        )
        await self._session.execute(text("""
            INSERT INTO platform.operation_execution_assignments (
                id, organization_id, project_id, operation_id, workflow_id, workflow_type, namespace, task_queue,
                workflow_contract_version, input_digest, correlation_id, allowed_actions
            ) VALUES (:id,:org,:project,:operation,:workflow,:workflow_type,:namespace,:queue,:version,:digest,:correlation,:actions)
        """), {"id": assignment, "org": operation.organization_id, "project": operation.project_id, "operation": operation_id,
               "workflow": workflow_id_for(operation_id), "workflow_type": workflow_type, "namespace": namespace,
               "queue": MANAGER_TASK_QUEUE, "version": request.contract_version, "digest": assigned_input_digest(request),
               "correlation": operation.correlation_id, "actions": sorted(action.value for action in actions)})
        return request

    async def bind_run(self, assignment_id: UUID, operation_id: UUID, workflow_run_id: UUID) -> bool:
        """After trusted Temporal observation; a request body or an ar2 signature cannot set the binding."""
        result = await self._session.execute(text("""
            UPDATE platform.operation_execution_assignments SET workflow_run_id = :run
            WHERE id = :id AND operation_id = :operation AND revoked_at IS NULL
              AND (workflow_run_id IS NULL OR workflow_run_id = :run)
        """), {"id": assignment_id, "operation": operation_id, "run": workflow_run_id})
        return affected(result) == 1

    async def resolve(
        self, assignment_id: UUID, operation_id: UUID, workflow_id: str, workflow_run_id: UUID, action: PlatformAction,
    ) -> PlatformExecution | None:
        scope = (await self._session.execute(text("""
            SELECT organization_id, project_id, correlation_id
            FROM platform.resolve_operation_assignment(:id,:operation,:workflow,:run,:action)
        """), {"id": assignment_id, "operation": operation_id, "workflow": workflow_id,
               "run": workflow_run_id, "action": action.value})).one_or_none()
        if scope is None:
            return None
        return PlatformExecution(
            OperationRef(str(operation_id), str(scope.organization_id), str(scope.project_id)),
            scope.correlation_id,
        )
