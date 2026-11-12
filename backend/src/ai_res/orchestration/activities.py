"""Activities: the only place where Temporal-driven work touches the outside world (here: the Platform API port).

Both Activities are idempotent on the platform side, so Temporal's retry of an Activity can never create a second Operation or a second transition. Errors are
mapped to Temporal retry semantics: transient -> retryable ApplicationError, permanent -> non-retryable.
"""
from collections.abc import Awaitable

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ai_res.orchestration.contracts import ContractError, OperationFailure, OperationRef, OperationState
from ai_res.orchestration.platform_port import OperationPlatform, PlatformPermanentError, PlatformTransientError

ACK_ACTIVITY = "acknowledge_operation_start"
FAIL_ACTIVITY = "record_operation_failure"
CANCEL_ACTIVITY = "confirm_operation_cancellation"
WORKER_RUN_ACTIVITY = "execute_worker_run"
PERMANENT = "PermanentPlatformError"
NOT_AVAILABLE = "WORKER_RUN_EXECUTION_NOT_AVAILABLE"


class ManagerActivities:
    def __init__(self, platform: OperationPlatform) -> None:
        self._platform = platform

    @activity.defn(name=ACK_ACTIVITY)
    async def acknowledge_operation_start(self, ref: OperationRef) -> OperationState:
        return await self._call(self._platform.acknowledge_start(ref))

    @activity.defn(name=FAIL_ACTIVITY)
    async def record_operation_failure(self, failure: OperationFailure) -> OperationState:
        return await self._call(self._platform.record_failure(failure))

    @activity.defn(name=CANCEL_ACTIVITY)
    async def confirm_operation_cancellation(self, ref: OperationRef) -> OperationState:
        return await self._call(self._platform.confirm_cancellation(ref))

    @staticmethod
    async def _call(call: Awaitable[OperationState]) -> OperationState:
        try:
            return await call
        except PlatformTransientError as exc:
            raise ApplicationError("platform temporarily unavailable", type="PlatformTransientError") from exc
        except (PlatformPermanentError, ContractError) as exc:
            raise ApplicationError("platform rejected the request", type=PERMANENT, non_retryable=True) from exc


class WorkerActivities:
    """Worker Runtime registration only (S11). WorkerRun execution arrives with S23 behind the Readiness Gate; until then the Activity refuses, fail closed."""

    @activity.defn(name=WORKER_RUN_ACTIVITY)
    async def execute_worker_run(self) -> None:
        raise ApplicationError("WorkerRun execution is not available before S23", type=NOT_AVAILABLE, non_retryable=True)
