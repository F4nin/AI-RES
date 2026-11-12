import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHistory
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.worker import Replayer, Worker

from ai_res.orchestration.activities import ACK_ACTIVITY, WORKER_RUN_ACTIVITY
from ai_res.orchestration.client import CancelOutcome, OperationCanceller, OperationStarter, StartOutcome
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, WORKER_TASK_QUEUE, OperationWorkflowInput, OperationWorkflowResult, workflow_id_for
from ai_res.orchestration.workers import manager_worker, worker_runtime_worker
from ai_res.orchestration.workflows import OperationWorkflow
from tests.integration.temporal.fakes import FakePlatform

pytestmark = pytest.mark.temporal
FIXTURES = Path(__file__).parent / "histories"


def handle_of(client: Client, req: OperationWorkflowInput):
    return client.get_workflow_handle(workflow_id_for(uuid.UUID(req.operation.operation_id)), result_type=OperationWorkflowResult)


def request() -> OperationWorkflowInput:
    return OperationWorkflowInput.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


@workflow.defn(name="OperationWorkflow")
class Changed:  # an extra command ahead of the recorded sequence: must be rejected by replay
    @workflow.run
    async def run(self, request: OperationWorkflowInput) -> None:
        await workflow.sleep(timedelta(seconds=1))
        await workflow.execute_activity(ACK_ACTIVITY, request.operation, task_queue=MANAGER_TASK_QUEUE, start_to_close_timeout=timedelta(seconds=5),
                                        retry_policy=RetryPolicy(maximum_attempts=1))


@asynccontextmanager
async def running(client: Client, platform: FakePlatform):
    async with manager_worker(client, platform):
        yield


async def test_start_runs_to_fail_closed_skeleton_and_no_worker_run(client: Client):
    platform, req = FakePlatform(), request()
    async with running(client, platform):
        assert await OperationStarter(client).start(req) is StartOutcome.ENSURED
        result = await handle_of(client, req).result()
    assert (result.outcome, result.status) == ("SKELETON_FAILED_CLOSED", "FAILED")
    assert platform.transitions == [(req.operation.operation_id, "RUNNING"), (req.operation.operation_id, "FAILED")]


async def test_duplicate_outbox_delivery_yields_one_workflow(client: Client):
    platform, req = FakePlatform(), request()
    starter = OperationStarter(client)
    async with running(client, platform):
        outcomes = [await starter.start(req) for _ in range(3)]  # running, then redelivered after completion too
        await handle_of(client, req).result()
        outcomes.append(await starter.start(req))
    assert outcomes[0] is StartOutcome.ENSURED and outcomes[-1] is StartOutcome.ALREADY_FINISHED
    found = [w async for w in client.list_workflows(f"WorkflowId = '{workflow_id_for(uuid.UUID(req.operation.operation_id))}'")]
    assert len(found) == 1
    assert platform.calls["ack"] == 1 and platform.calls["fail"] == 1  # the redelivery re-ran nothing


async def test_activity_retry_creates_no_second_transition(client: Client):
    platform, req = FakePlatform(transient_failures=2), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        result = await handle_of(client, req).result()
    assert platform.calls["ack"] == 3 and result.status == "FAILED"
    assert platform.transitions.count((req.operation.operation_id, "RUNNING")) == 1  # one Operation, one transition


async def test_permanent_platform_error_is_not_retried(client: Client):
    platform, req = FakePlatform(permanent=True), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        with pytest.raises(WorkflowFailureError):
            await handle_of(client, req).result()
    assert platform.calls["ack"] == 1


async def test_history_contains_only_references_and_codes(client: Client):
    platform, req = FakePlatform(), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        handle = handle_of(client, req)
        await handle.result()
        text = (await handle.fetch_history()).to_json()
    forbidden = re.compile(r"password|secret|authorization|bearer|api[_-]?key|private[_-]?key|BEGIN [A-Z ]*PRIVATE|prompt|-----BEGIN", re.I)
    assert not forbidden.search(text)
    payloads = re.findall(r'"data":\s*"([^"]+)"', text)
    assert len(payloads) >= 4  # workflow input + 2 activity inputs/results: a scan that found nothing must not pass
    for payload in payloads:  # every payload is compact base64 JSON of ids/codes
        import base64
        decoded = base64.b64decode(payload).decode()
        assert len(decoded) < 600
        json.loads(decoded)


async def test_replay_of_recorded_history_and_fixture(client: Client):
    platform, req = FakePlatform(), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        handle = handle_of(client, req)
        await handle.result()
        history = await handle.fetch_history()
    await Replayer(workflows=[OperationWorkflow]).replay_workflow(history)
    if os.environ.get("AI_RES_REGENERATE_HISTORY"):  # releasing a workflow change: keep the history recorded by the PREVIOUS code, then add the new one
        FIXTURES.mkdir(exist_ok=True)
        (FIXTURES / f"operation_workflow_v1_{len(list(FIXTURES.glob('*.json'))) + 1}.json").write_text(history.to_json())
    fixtures = sorted(FIXTURES.glob("operation_workflow_v1_*.json"))
    assert fixtures, "released histories must be kept as replay fixtures"
    for f in fixtures:
        await Replayer(workflows=[OperationWorkflow]).replay_workflow(WorkflowHistory.from_json("fixture", f.read_text()))


async def test_replay_detects_nondeterministic_change(client: Client):
    platform, req = FakePlatform(), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        handle = handle_of(client, req)
        await handle.result()
        history = await handle.fetch_history()

    result = await Replayer(workflows=[Changed]).replay_workflow(history, raise_on_replay_failure=False)
    assert result.replay_failure is not None


@workflow.defn(name="WorkerRuntimeProbe")
class Probe:  # test-only caller: standalone activity execution is unsupported by the pinned dev server
    @workflow.run
    async def run(self) -> None:
        await workflow.execute_activity(WORKER_RUN_ACTIVITY, task_queue=WORKER_TASK_QUEUE, start_to_close_timeout=timedelta(seconds=5),
                                        retry_policy=RetryPolicy(maximum_attempts=3))


async def test_worker_runtime_registers_but_refuses_worker_runs(client: Client):
    q = f"probe-{uuid.uuid4()}"
    async with Worker(client, task_queue=q, workflows=[Probe]), worker_runtime_worker(client):
        with pytest.raises(WorkflowFailureError) as err:
            await client.execute_workflow("WorkerRuntimeProbe", id=q, task_queue=q)
    activity_error = err.value.cause
    assert isinstance(activity_error, ActivityError)
    cause = activity_error.cause
    assert isinstance(cause, ApplicationError) and cause.type == "WORKER_RUN_EXECUTION_NOT_AVAILABLE" and cause.non_retryable


async def test_cancel_requested_before_the_start_is_acknowledged_is_reconciled_to_cancelled(client: Client):
    req = request()
    platform = FakePlatform(preset={req.operation.operation_id: "CANCEL_REQUESTED"})
    async with running(client, platform):
        await OperationStarter(client).start(req)
        result = await handle_of(client, req).result()
    assert (result.outcome, result.status) == ("CANCELLED_CONFIRMED", "CANCELLED")
    assert platform.calls["fail"] == 0  # the skeleton failure never runs over a cancel


async def test_cancel_that_wins_the_race_against_the_skeleton_failure_is_reconciled_not_left_pending(client: Client):
    platform, req = FakePlatform(cancel_wins_race=True), request()
    async with running(client, platform):
        await OperationStarter(client).start(req)
        result = await handle_of(client, req).result()
    assert (result.outcome, result.status) == ("CANCELLED_CONFIRMED", "CANCELLED")
    assert platform.transitions[-1] == (req.operation.operation_id, "CANCELLED") and platform.calls["confirm_cancel"] == 1


async def test_cancel_signal_reaches_a_running_workflow_and_a_missing_one_is_reported_not_raised(client: Client):
    req = request()
    canceller = OperationCanceller(client)
    # nothing to signal: reconciliation owns it (G-107)
    assert await canceller.signal(uuid.UUID(req.operation.operation_id)) is CancelOutcome.NO_RUNNING_WORKFLOW
    platform = FakePlatform(transient_failures=1)  # keeps the workflow alive in its first Activity retry long enough to be signalled
    async with running(client, platform):
        await OperationStarter(client).start(req)
        assert await canceller.signal(uuid.UUID(req.operation.operation_id)) is CancelOutcome.SIGNALLED
        result = await handle_of(client, req).result()
    # the domain never entered CANCEL_REQUESTED: the signal is a hint it does not back, so it is ignored and the Operation still ends terminal
    assert (result.outcome, result.status) == ("SKELETON_FAILED_CLOSED", "FAILED")
