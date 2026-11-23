"""Metadata authorization for the Temporal frontend. This service makes no Temporal RPC."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.platform_control import PlatformAuthFailure, PlatformOperationControl
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.platform_credentials import PlatformAction, VerifiedAuthControlCredential
from ai_res.modules.iam.platform_nonces import PlatformRequestNonceStore
from ai_res.modules.iam.task_issuance import IssuanceLookup, TaskExecutionRef, TaskIssuanceStore, TaskKind
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.orchestration.contracts import workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.ports import ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError


@dataclass(frozen=True, slots=True)
class NativeStartIntent:
    assignment_id: UUID
    workflow_id: str
    workflow_type: str
    namespace: str
    queue: str
    major: int
    input_digest: bytes


@dataclass(frozen=True, slots=True)
class NativeReconciliationDescribe:
    operation_id: UUID
    workflow_run_id: UUID
    namespace: str
    active_status_only: bool = False


@dataclass(frozen=True, slots=True)
class NativeBoundCancellation:
    assignment_id: UUID
    operation_id: UUID
    workflow_run_id: UUID
    namespace: str


@dataclass(frozen=True, slots=True)
class NativeTaskAuthorization:
    issuance: IssuanceLookup
    execution: TaskExecutionRef
    register: bool
    workflow_context: bool = False


@dataclass(frozen=True, slots=True)
class NativeWorkflowTaskContext:
    assignment_id: UUID
    workflow_type: str
    workflow_contract_version: int
    input_digest: bytes
    operation_status: str


class _CredentialExpired(Exception):
    """Roll back any issuance before auditing the expired request."""


class NativeAuthControl:
    def __init__(self, factory: async_sessionmaker[AsyncSession], audit: PlatformOperationControl) -> None:
        self._factory = factory
        self._nonces = PlatformRequestNonceStore(factory)
        self._audit = audit

    async def authorize(
        self, credential: VerifiedAuthControlCredential,
        command: NativeStartIntent | NativeReconciliationDescribe | NativeBoundCancellation | NativeTaskAuthorization,
        correlation_id: UUID,
    ) -> NativeWorkflowTaskContext | None:
        try:
            if credential.issuer is not ServiceName.TEMPORAL_AUTH_CONTROL or not await self._nonces.consume(credential):
                await self._audit.record_auth_failure(PlatformAuthFailure.EXPIRED_OR_REPLAY, correlation_id)
                raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
            async with UnitOfWork(self._factory) as uow:
                context = None
                if isinstance(command, NativeStartIntent):
                    action = "AUTHORIZE_START"
                    accepted = await _start(uow.session, command)
                elif isinstance(command, NativeReconciliationDescribe):
                    action = "AUTHORIZE_BOUND_STATUS" if command.active_status_only else "AUTHORIZE_RECONCILIATION_DESCRIBE"
                    accepted = await _describe(uow.session, command)
                elif isinstance(command, NativeBoundCancellation):
                    action = "AUTHORIZE_BOUND_CANCEL"
                    accepted = await _authorize_cancellation(uow, command)
                elif command.workflow_context:
                    action = "CHECK_TASK"
                    context = await _workflow_context(uow.session, command)
                    accepted = context is not None
                else:
                    action = "REGISTER_TASK" if command.register else "CHECK_TASK"
                    accepted = await _task(uow.session, command, credential)
                if credential.expires_at <= utc_now():
                    raise _CredentialExpired
                if accepted:
                    await uow.session.execute(text("""
                        INSERT INTO platform.platform_auth_events(id,correlation_id,reason,action)
                        VALUES (:id,:correlation,'AUTHORIZED',:action)
                    """), {"id": new_id(), "correlation": correlation_id, "action": action})
                    return context
        except _CredentialExpired:
            await self._audit.record_auth_failure(PlatformAuthFailure.EXPIRED_OR_REPLAY, correlation_id)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.") from None
        except SQLAlchemyError:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Native authorization unavailable.") from None
        await self._audit.record_auth_failure(PlatformAuthFailure.ASSIGNMENT_DENIED, correlation_id)
        raise ProblemError(ErrorCode.ACCESS_DENIED, "Native authorization denied.")


async def _start(session: AsyncSession, command: NativeStartIntent) -> bool:
    decision = await session.execute(text("""
        SELECT platform.matches_operation_dispatch(:assignment,:workflow,:type,:namespace,:queue,:major,:digest)
    """), {"assignment": command.assignment_id, "workflow": command.workflow_id, "type": command.workflow_type,
           "namespace": command.namespace, "queue": command.queue, "major": command.major, "digest": command.input_digest})
    return bool(decision.scalar_one())


async def _describe(session: AsyncSession, command: NativeReconciliationDescribe) -> bool:
    statement = (
        "SELECT platform.matches_bound_execution_status(:operation,:run,:namespace)" if command.active_status_only else
        "SELECT platform.matches_reconciliation_describe(:operation,:run,:namespace)"
    )
    decision = await session.execute(text(statement), {"operation": command.operation_id, "run": command.workflow_run_id,
                                                      "namespace": command.namespace})
    return bool(decision.scalar_one())


async def _authorize_cancellation(uow: UnitOfWork, command: NativeBoundCancellation) -> bool:
    # Resolve locks the exact assignment against revocation. Existing metadata
    # admission constrains its namespace, type, contract and queue.
    execution = await OperationAssignments(uow.session).resolve(
        command.assignment_id, command.operation_id, workflow_id_for(command.operation_id),
        command.workflow_run_id, PlatformAction.CONFIRM_CANCELLATION,
    )
    if execution is None or not await _describe(uow.session, NativeReconciliationDescribe(
        command.operation_id, command.workflow_run_id, command.namespace, active_status_only=True,
    )):
        return False
    operation = execution.operation
    await uow.with_tenant(UUID(operation.organization_id), UUID(operation.project_id))
    await uow.session.execute(text("SELECT set_config('app.platform_operation_id', :operation, true)"), {"operation": operation.operation_id})
    found = await uow.session.execute(text("""
        SELECT 1 FROM operations.operations WHERE id=:operation AND status='CANCEL_REQUESTED' FOR SHARE
    """), {"operation": command.operation_id})
    return found.scalar_one_or_none() is not None


async def _task(session: AsyncSession, command: NativeTaskAuthorization, credential: VerifiedAuthControlCredential) -> bool:
    key, ref = command.issuance, command.execution
    # Worker receipts require an admitted WorkerRun and are introduced with the Gate.
    if key.principal is not ServiceName.MANAGER_RUNTIME:
        return False
    decision = await session.execute(text("""
        SELECT platform.matches_bound_manager_task(:operation,:run,:namespace,:queue)
    """), {"operation": ref.operation_id, "run": ref.workflow_run_id, "namespace": key.namespace, "queue": key.queue})
    if credential.expires_at <= utc_now():
        raise _CredentialExpired
    if not decision.scalar_one():
        return False
    if command.register:
        return await TaskIssuanceStore.register_in(session, key, ref)
    return await TaskIssuanceStore.check_in(session, key) == ref


async def _workflow_context(session: AsyncSession, command: NativeTaskAuthorization) -> NativeWorkflowTaskContext | None:
    key, ref = command.issuance, command.execution
    if key.principal is not ServiceName.MANAGER_RUNTIME or key.task_kind is not TaskKind.WORKFLOW or command.register:
        return None
    result = (await session.execute(text("""
        SELECT assignment_id,workflow_type,workflow_contract_version,input_digest,operation_status
        FROM platform.bound_workflow_task_command_binding(:operation,:run,:namespace,:queue,:digest)
    """), {"operation": ref.operation_id, "run": ref.workflow_run_id, "namespace": key.namespace, "queue": key.queue,
           "digest": key.token_digest})).one_or_none()
    return None if result is None else NativeWorkflowTaskContext(*result)
