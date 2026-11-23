"""Use a verified private request and resolve its server-owned Operation assignment."""
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.platform_manager import AssignedManagerInput, ManagerCredentialExpired, execute_manager_command
from ai_res.db.session import UnitOfWork
from ai_res.modules.epics.manager_proposals import ProposalContent
from ai_res.modules.iam.platform_credentials import PlatformAction, VerifiedPlatformCredential
from ai_res.modules.iam.platform_nonces import PlatformRequestNonceStore
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.orchestration.contracts import OperationFailure, OperationState
from ai_res.platform.clock import utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError


class PlatformAuthFailure(StrEnum):
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    EXPIRED_OR_REPLAY = "EXPIRED_OR_REPLAY"
    ASSIGNMENT_DENIED = "ASSIGNMENT_DENIED"
    INVALID_REQUEST = "INVALID_REQUEST"


@dataclass(frozen=True, slots=True)
class PlatformOperationCommand:
    operation_id: UUID
    workflow_id: str
    workflow_run_id: UUID
    action: PlatformAction
    failure_code: str | None = None
    draft: ProposalContent | None = None
    epic_context: bool = False


class PlatformOperationControl:
    def __init__(self, factory: async_sessionmaker[AsyncSession], *, failure_codes: frozenset[str]) -> None:
        self._factory = factory
        self._nonces = PlatformRequestNonceStore(factory)
        self._failure_codes = failure_codes

    async def record_auth_failure(self, reason: PlatformAuthFailure, correlation_id: UUID) -> None:
        try:
            async with UnitOfWork(self._factory) as uow:
                await uow.session.execute(text("""
                    INSERT INTO platform.platform_auth_events(id,correlation_id,reason)
                    VALUES (:id,:correlation,:reason)
                """), {"id": new_id(), "correlation": correlation_id, "reason": reason.value})
        except SQLAlchemyError:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Security audit unavailable.") from None

    async def execute(
        self, credential: VerifiedPlatformCredential, command: PlatformOperationCommand, correlation_id: UUID,
    ) -> OperationState | AssignedManagerInput:
        try:
            if not await self._nonces.consume(credential):
                await self.record_auth_failure(PlatformAuthFailure.EXPIRED_OR_REPLAY, correlation_id)
                raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
            if command.action is PlatformAction.RECORD_FAILURE and command.failure_code not in self._failure_codes:
                await self.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, correlation_id)
                raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid operation failure code.")
            async with UnitOfWork(self._factory) as uow:
                execution = await OperationAssignments(uow.session).resolve(
                    credential.assignment_id, command.operation_id, command.workflow_id, command.workflow_run_id, command.action,
                )
                if execution is not None and credential.expires_at > utc_now():
                    await uow.session.execute(text(
                        "SELECT set_config('app.platform_operation_id', :operation, true), set_config('app.platform_action', :action, true), "
                        "set_config('app.platform_assignment_id', :assignment, true), set_config('app.platform_workflow_run_id', :run, true)"
                    ), {"operation": str(command.operation_id), "action": command.action.value,
                        "assignment": str(credential.assignment_id), "run": str(command.workflow_run_id)})
                    service = OperationOrchestrationService
                    if command.action is PlatformAction.ACKNOWLEDGE_START:
                        return await service.acknowledge_start_in(uow, execution.operation, execution.correlation_id)
                    if command.action is PlatformAction.CONFIRM_CANCELLATION:
                        return await service.confirm_cancellation_in(uow, execution.operation, execution.correlation_id)
                    if command.action is PlatformAction.RECORD_FAILURE and command.failure_code is not None:
                        return await service.record_failure_in(
                            uow, OperationFailure(execution.operation, command.failure_code), execution.correlation_id,
                        )
                    if command.action in {PlatformAction.READ_MANAGER_INPUT, PlatformAction.RECORD_MANAGER_DRAFT, PlatformAction.MATERIALIZE_PLAN_TASKS}:
                        return await execute_manager_command(
                            uow, execution, command.action, command.draft, expires_at=credential.expires_at,
                            bound_assignment=(credential.assignment_id, command.workflow_run_id), epic_context=command.epic_context,
                        )
        except ManagerCredentialExpired:
            await self.record_auth_failure(PlatformAuthFailure.EXPIRED_OR_REPLAY, correlation_id)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.") from None
        except SQLAlchemyError:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Platform control unavailable.") from None
        await self.record_auth_failure(PlatformAuthFailure.ASSIGNMENT_DENIED, correlation_id)
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Operation not found.")
