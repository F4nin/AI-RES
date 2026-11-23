"""Temporal mechanics with synthetic Platform and deterministic LLM test doubles."""
import asyncio
import base64
import json
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from temporalio.client import Client, WorkflowFailureError
from temporalio.worker import Replayer

from ai_res.application.observe_operations import BoundExecutionObservationRequest, TemporalExecutionObserver
from ai_res.llm import LLMLimits
from ai_res.llm.transport import TransportResult
from ai_res.llm.types import FinishReason, Usage
from ai_res.modules.operations.reconciliation import ExecutionState
from ai_res.orchestration.client import AssignedOperationStarter, StartOutcome
from ai_res.orchestration.contracts import (
    CANCEL_SIGNAL,
    CONTRACT_VERSION,
    MANAGER_TASK_QUEUE,
    PLAN_EXECUTION_WORKFLOW,
    AssignedWorkflowInput,
    OperationRef,
    OperationState,
    assert_compact,
    workflow_id_for,
)
from ai_res.orchestration.manager_workflows import ManagerIntakeWorkflow, PlanExecutionWorkflow
from ai_res.runtime.manager_activities import assigned_manager_worker
from ai_res.runtime.manager_reasoning import IntakeQuestionContext, ManagerReasoning, ManagerReasoningInput, QuestionDisposition
from tests.unit.test_llm_gateway import Rig, profile

pytestmark = pytest.mark.temporal
CANARY = "fixture-private-intake-canary"
ANSWER_CANARY = "fixture-private-prior-answer-canary"


@pytest.mark.parametrize("scenario", ["success", "failure", "cancel_before_inference"])
async def test_intake_history_is_replayable_and_excludes_activity_exception_payload(client: Client, scenario: str):
    operation = OperationRef(str(uuid4()), str(uuid4()), str(uuid4()))
    request = AssignedWorkflowInput(CONTRACT_VERSION, operation, str(uuid4()))
    assert_compact(request)
    platform = AsyncMock()
    platform.acknowledge_manager_start.return_value = OperationState(operation.operation_id, "RUNNING")
    loaded = asyncio.Event()
    release = asyncio.Event()

    async def input_for(reference):
        assert reference.operation == operation and reference.assignment_id == request.assignment_id
        assert reference.workflow_run_id
        if scenario == "failure":
            raise RuntimeError(CANARY)
        loaded.set()
        await release.wait()
        return ManagerReasoningInput(
            "fixture", model.id, "run-1", "INTERNAL", LLMLimits(100, 10), CANARY,
            recent_questions=(IntakeQuestionContext(uuid4(), "project.owner", QuestionDisposition.ANSWERED, ANSWER_CANARY),),
        )

    model = profile()
    rig = Rig(model)
    rig.gw.transport.script.append(TransportResult(
        output='{"goal":"Fixture draft","scope":null,"primary_question":null}', finish_reason=FinishReason.STOP,
        usage=Usage(3, 7), provider_request_ref="fixture",
    ))
    platform.manager_input.side_effect = input_for
    platform.record_manager_draft.return_value = OperationState(operation.operation_id, "SUCCEEDED")
    platform.confirm_cancellation.return_value = OperationState(operation.operation_id, "CANCELLED")
    async with assigned_manager_worker(client, platform, ManagerReasoning(rig.gw)):
        handle = await client.start_workflow(ManagerIntakeWorkflow.run, request, id=workflow_id_for(UUID(operation.operation_id)),
                                             task_queue=MANAGER_TASK_QUEUE)
        if scenario == "failure":
            with pytest.raises(WorkflowFailureError) as error:
                await asyncio.wait_for(handle.result(), timeout=30)
            failure_cause = error.value.cause.cause
            assert failure_cause.type == "ManagerActivityFailed" and failure_cause.cause is None
            platform.record_manager_draft.assert_not_awaited()
        else:
            await asyncio.wait_for(loaded.wait(), timeout=30)
            if scenario == "cancel_before_inference":
                platform.acknowledge_manager_start.return_value = OperationState(operation.operation_id, "CANCEL_REQUESTED")
                await handle.signal(CANCEL_SIGNAL)
            release.set()
            result = await asyncio.wait_for(handle.result(), timeout=30)
            if scenario == "cancel_before_inference":
                assert result.status == "CANCELLED"
                platform.confirm_cancellation.assert_awaited_once()
                platform.record_manager_draft.assert_not_awaited()
                assert rig.gw.transport.calls == []
            else:
                assert result.status == "SUCCEEDED"
                assert len(rig.gw.transport.calls) == 1
                assert ANSWER_CANARY in rig.gw.transport.calls[0].messages[1].content
        history = await handle.fetch_history()

    history_json = history.to_json()
    for canary in (CANARY, ANSWER_CANARY):
        assert canary not in history_json
        assert base64.b64encode(canary.encode()).decode() not in history_json
    for event in json.loads(history_json)["events"]:
        for value in event.values():
            if isinstance(value, dict):
                for key in ("input", "result"):
                    for payload in value.get(key, {}).get("payloads", []):
                        data = base64.b64decode(payload["data"])
                        assert CANARY.encode() not in data and ANSWER_CANARY.encode() not in data
    await Replayer(workflows=[ManagerIntakeWorkflow]).replay_workflow(history)


async def test_plan_workflow_materializes_then_confirms_domain_cancellation(client: Client):
    operation = OperationRef(str(uuid4()), str(uuid4()), str(uuid4()))
    request = AssignedWorkflowInput(CONTRACT_VERSION, operation, str(uuid4()))
    platform = AsyncMock()
    platform.acknowledge_manager_start.return_value = OperationState(operation.operation_id, "RUNNING")
    prepared = asyncio.Event()

    async def prepare(reference):
        assert reference.operation == operation and reference.assignment_id == request.assignment_id
        prepared.set()
        return OperationState(operation.operation_id, "WAITING_FOR_DEPENDENCY")

    platform.prepare_plan_tasks.side_effect = prepare
    platform.confirm_cancellation.return_value = OperationState(operation.operation_id, "CANCELLED")
    async with assigned_manager_worker(client, platform, ManagerReasoning(Rig(profile()).gw)):
        starter = AssignedOperationStarter(client)
        started = await starter.start(request, "PLAN_EXECUTION")
        replayed = await starter.start(request, "PLAN_EXECUTION")
        assert started.outcome is StartOutcome.ENSURED and replayed.run_id == started.run_id
        handle = client.get_workflow_handle_for(
            PlanExecutionWorkflow.run, workflow_id_for(UUID(operation.operation_id)), run_id=str(started.run_id),
        )
        await asyncio.wait_for(prepared.wait(), timeout=30)
        await handle.signal(CANCEL_SIGNAL)
        assert (await asyncio.wait_for(handle.result(), timeout=30)).status == "CANCELLED"
        history = await handle.fetch_history()
        closed = await starter.start(request, "PLAN_EXECUTION")
        assert closed.outcome is StartOutcome.ALREADY_FINISHED and closed.run_id == started.run_id

    platform.prepare_plan_tasks.assert_awaited_once()
    platform.confirm_cancellation.assert_awaited_once()
    await Replayer(workflows=[PlanExecutionWorkflow]).replay_workflow(history)
    observer = TemporalExecutionObserver(client, deadline=timedelta(seconds=2))
    assert await observer.discover_initial_run(request, "PLAN_EXECUTION", client.namespace) == started.run_id
    assert await observer.discover_initial_run(replace(request, assignment_id=str(uuid4())), "PLAN_EXECUTION", client.namespace) is None
    assert await observer.discover_initial_run(request, "MANAGER_MESSAGE", client.namespace) is None
    observation = BoundExecutionObservationRequest(UUID(request.assignment_id), UUID(operation.operation_id), PLAN_EXECUTION_WORKFLOW,
                                               started.run_id, client.namespace)
    assert (await observer.observe(observation)).state is ExecutionState.COMPLETED
    assert (await observer.observe(replace(observation, workflow_run_id=uuid4()))).state is ExecutionState.ABSENT
    assert (await observer.observe(replace(observation, workflow_type="OperationWorkflow"))).state is ExecutionState.SCOPE_MISMATCH
