"""G02 Activity composition. Sensitive input exists only in this process, outside history."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from ai_res.orchestration.activities import PERMANENT
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, OperationState
from ai_res.orchestration.manager_workflows import (
    BOUND_ACK,
    BOUND_CANCEL,
    MANAGER_TURN,
    PLAN_PREPARE,
    BoundWorkflowCall,
    ManagerIntakeWorkflow,
    PlanExecutionWorkflow,
)
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError
from ai_res.runtime.manager_reasoning import ManagerDraft, ManagerReasoning, ManagerReasoningInput


class G02PlatformPort(Protocol):
    async def acknowledge_manager_start(self, reference: BoundWorkflowCall) -> OperationState: ...
    async def manager_input(self, reference: BoundWorkflowCall) -> ManagerReasoningInput: ...
    async def record_manager_draft(
        self, reference: BoundWorkflowCall, draft: ManagerDraft, *, context_version_id: UUID | None = None,
    ) -> OperationState: ...
    async def prepare_plan_tasks(self, reference: BoundWorkflowCall) -> OperationState: ...
    async def confirm_cancellation(self, reference: BoundWorkflowCall) -> OperationState: ...


@asynccontextmanager
async def _history_safe_failures() -> AsyncIterator[None]:
    try:
        yield
    except PlatformTransientError:
        failure = ApplicationError("platform temporarily unavailable", type="PlatformTransientError")
    except PlatformPermanentError:
        failure = ApplicationError("platform rejected the request", type=PERMANENT, non_retryable=True)
    except Exception:
        failure = ApplicationError("Manager Activity failed", type="ManagerActivityFailed", non_retryable=True)
    else:
        return
    raise failure from None


class ManagerActivities:
    def __init__(self, platform: G02PlatformPort, reasoning: ManagerReasoning) -> None:
        self._platform, self._reasoning = platform, reasoning

    @activity.defn(name=BOUND_ACK)
    async def acknowledge_start(self, reference: BoundWorkflowCall) -> OperationState:
        async with _history_safe_failures():
            return await self._platform.acknowledge_manager_start(reference)
        raise AssertionError("Activity produced no Operation state")

    @activity.defn(name=MANAGER_TURN)
    async def complete_intake(self, reference: BoundWorkflowCall) -> OperationState:
        async with _history_safe_failures():
            state = await self._platform.acknowledge_manager_start(reference)
            if state.status != "RUNNING":
                return state
            inputs = await self._platform.manager_input(reference)
            # The idempotent acknowledgement rechecks the exact assignment and current state after the protected read.
            state = await self._platform.acknowledge_manager_start(reference)
            if state.status != "RUNNING":
                return state
            draft = await self._reasoning.draft(inputs)
            context = inputs.epic_context
            if context is None:
                return await self._platform.record_manager_draft(reference, draft)
            if context.state.has_open_question and draft.primary_question is not None:
                draft = draft.model_copy(update={"primary_question": None})
            return await self._platform.record_manager_draft(reference, draft, context_version_id=context.version_id)
        raise AssertionError("Activity produced no Operation state")

    @activity.defn(name=PLAN_PREPARE)
    async def prepare_plan(self, reference: BoundWorkflowCall) -> OperationState:
        async with _history_safe_failures():
            return await self._platform.prepare_plan_tasks(reference)
        raise AssertionError("Activity produced no Operation state")

    @activity.defn(name=BOUND_CANCEL)
    async def confirm_cancellation(self, reference: BoundWorkflowCall) -> OperationState:
        async with _history_safe_failures():
            return await self._platform.confirm_cancellation(reference)
        raise AssertionError("Activity produced no Operation state")


def assigned_manager_worker(client: Client, platform: G02PlatformPort, reasoning: ManagerReasoning, *, build_id: str | None = None) -> Worker:
    """Host only assignment-bound Manager actions on the existing Manager queue."""
    actions = ManagerActivities(platform, reasoning)
    return Worker(client, task_queue=MANAGER_TASK_QUEUE, workflows=[ManagerIntakeWorkflow, PlanExecutionWorkflow],
                  activities=[actions.acknowledge_start, actions.complete_intake, actions.prepare_plan, actions.confirm_cancellation],
                  max_cached_workflows=0, disable_eager_activity_execution=True, build_id=build_id)
