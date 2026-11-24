"""Three phases of a stock → native → stock acceptance on a disposable database."""

import asyncio
import hashlib
import json
import socket
import sys
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from ai_res.orchestration.client import OperationStarter, StartOutcome
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, OperationRef, OperationState, OperationWorkflowInput, OperationWorkflowResult, workflow_id_for
from ai_res.orchestration.workers import manager_worker
from ai_res.orchestration.workflows import OperationWorkflow
from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.enums.v1 import EventType, PendingWorkflowTaskState, TimeoutType, WorkflowExecutionStatus
from temporalio.api.history.v1 import History
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    DescribeWorkflowExecutionRequest,
    GetWorkflowExecutionHistoryRequest,
    PollWorkflowTaskQueueRequest,
)
from temporalio.client import Client, WorkflowHistory
from temporalio.service import RPCError, RPCStatusCode, TLSConfig
from temporalio.worker import Replayer
from tests.integration.temporal.fakes import FakePlatform

NAMESPACE = "ai-res"
NATIVE_HOST = "temporal-workflow"
SECRETS = Path("/run/secrets")
RPC_TIMEOUT = timedelta(seconds=8)
COMPLETED = WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED
RUNNING = WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING


@dataclass(frozen=True)
class Run:
    workflow_id: str
    run_id: str
    history_sha256: str

    def execution(self) -> WorkflowExecution:
        return WorkflowExecution(workflow_id=self.workflow_id, run_id=self.run_id)


async def temporal(role: str | None = None, *, identity: str | None = None) -> Client:
    if role is None:
        return await Client.connect("temporal:7233", namespace=NAMESPACE)
    tls = TLSConfig(
        server_root_ca_cert=(SECRETS / "temporal_frontend_ca").read_bytes(), domain=NATIVE_HOST,
        client_cert=(SECRETS / f"temporal_{role}_cert").read_bytes(), client_private_key=(SECRETS / f"temporal_{role}_key").read_bytes(),
    )
    return await Client.connect(f"{NATIVE_HOST}:7233", namespace=NAMESPACE, tls=tls, identity=identity)


async def namespace(client: Client) -> dict:
    description = await client.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=NAMESPACE), timeout=RPC_TIMEOUT)
    assert description.namespace_info.name == NAMESPACE
    return {"id": description.namespace_info.id, "retention_seconds": description.config.workflow_execution_retention_ttl.seconds}


def operation() -> OperationWorkflowInput:
    return OperationWorkflowInput.create(uuid4(), uuid4(), uuid4(), uuid4())


def digest(history: WorkflowHistory) -> str:
    return hashlib.sha256(History(events=history.events).SerializeToString(deterministic=True)).hexdigest()


def postgres(database: str) -> psycopg.Connection:
    # The disposable test probe uses Temporal's existing role. Nothing gets access from the production frontend.
    return psycopg.connect(
        host="postgres", dbname=database, user="temporal", password=(SECRETS / "temporal_db_password").read_text(),
        sslmode="verify-full", sslrootcert=str(SECRETS / "postgres_tls_ca_cert"), connect_timeout=4,
        autocommit=True, options="-c default_transaction_read_only=on -c statement_timeout=4000",
    )


def stored_history(run: Run) -> WorkflowHistory:
    # This fixture has no reset/ContinueAsNew. In Temporal 1.29 its initial Run ID is the history tree ID.
    with postgres("temporal_db") as database:
        batches = database.execute("SELECT data, data_encoding FROM history_node WHERE tree_id=%s ORDER BY node_id", (UUID(run.run_id).bytes,)).fetchall()
    assert batches and all(encoding == "Proto3" for _, encoding in batches)
    events = [event for data, _ in batches for event in History.FromString(data).events]
    assert [event.event_id for event in events] == list(range(1, len(events) + 1))
    assert events[0].workflow_execution_started_event_attributes.workflow_type.name == "OperationWorkflow"
    return WorkflowHistory(run.workflow_id, events)


def event_summary(history: WorkflowHistory) -> str:
    return ", ".join(f"{event.event_id}:{EventType.Name(event.event_type)}" for event in history.events)


def committed_event(run: Run, namespace_id: str, event_id: int) -> bool:
    with postgres("temporal_db") as database:
        row = database.execute("""
            SELECT next_event_id FROM executions WHERE namespace_id=%s AND workflow_id=%s AND run_id=%s
        """, (UUID(namespace_id).bytes, run.workflow_id, UUID(run.run_id).bytes)).fetchone()
    return row is not None and row[0] > event_id


async def wait_for_denied_task_timeout(run: Run, namespace_id: str, scheduled_id: int) -> None:
    try:
        async with asyncio.timeout(25):
            while True:
                history = stored_history(run)
                assert all(not event.HasField("workflow_task_completed_event_attributes") for event in history.events)
                started = {
                    event.event_id for event in history.events
                    if event.HasField("workflow_task_started_event_attributes")
                    and event.workflow_task_started_event_attributes.scheduled_event_id == scheduled_id
                }
                for event in history.events:
                    if not event.HasField("workflow_task_timed_out_event_attributes"):
                        continue
                    timeout = event.workflow_task_timed_out_event_attributes
                    if (timeout.scheduled_event_id == scheduled_id and timeout.started_event_id in started
                            and timeout.timeout_type == TimeoutType.TIMEOUT_TYPE_START_TO_CLOSE
                            and committed_event(run, namespace_id, event.event_id)):
                        # The history append precedes the execution update that schedules the replacement.
                        # A transient replacement need not emit a separate Scheduled event until it completes.
                        return
                await asyncio.sleep(0.25)
    except TimeoutError:
        raise AssertionError(f"native never committed the denied task's timeout: {event_summary(stored_history(run))}") from None


async def visible(run: Run, status: WorkflowExecutionStatus) -> None:
    async with asyncio.timeout(15):
        with postgres("temporal_visibility_db") as database:
            while True:
                rows = database.execute(
                    "SELECT rtrim(run_id),status,workflow_type_name FROM executions_visibility WHERE workflow_id=%s",
                    (run.workflow_id,),
                ).fetchall()
                if rows == [(run.run_id, status, "OperationWorkflow")]:
                    return
                await asyncio.sleep(0.1)


async def assert_terminal_replay(run: Run) -> None:
    history = stored_history(run)
    assert history.events[-1].HasField("workflow_execution_completed_event_attributes")
    assert digest(history) == run.history_sha256
    await Replayer(workflows=[OperationWorkflow]).replay_workflow(history)
    await visible(run, COMPLETED)


async def seed() -> dict:
    client = await temporal()
    identity = await namespace(client)
    normal, cancelled = operation(), operation()
    ack_started = asyncio.Event()
    drain = asyncio.Event()

    class DrainingPlatform(FakePlatform):
        async def acknowledge_start(self, ref: OperationRef) -> OperationState:
            if ref.operation_id == normal.operation.operation_id:
                ack_started.set()
                await drain.wait()
            return await super().acknowledge_start(ref)

    fixture = DrainingPlatform(preset={cancelled.operation.operation_id: "CANCEL_REQUESTED"})
    closed = []
    async with asyncio.timeout(30), manager_worker(client, fixture):
        for request, expected in ((cancelled, ("CANCELLED_CONFIRMED", "CANCELLED")), (normal, ("SKELETON_FAILED_CLOSED", "FAILED"))):
            ack_before = fixture.calls["ack"]
            assert await OperationStarter(client).start(request) is StartOutcome.ENSURED
            workflow_id = workflow_id_for(UUID(request.operation.operation_id))
            handle = client.get_workflow_handle(workflow_id, result_type=OperationWorkflowResult)
            if request == normal:
                await ack_started.wait()
                assert (await handle.describe()).status == RUNNING and fixture.calls["ack"] == ack_before
                drain.set()
            result = await handle.result()
            assert (result.outcome, result.status) == expected
            run = Run(workflow_id, (await handle.describe()).run_id, digest(await handle.fetch_history()))
            await assert_terminal_replay(run)
            closed.append(asdict(run))

    pending = operation()
    workflow_id = workflow_id_for(UUID(pending.operation.operation_id))
    handle = await client.start_workflow(
        OperationWorkflow.run, pending, id=workflow_id, task_queue=MANAGER_TASK_QUEUE, task_timeout=timedelta(seconds=3),
    )
    assert handle.first_execution_run_id
    run = Run(workflow_id, handle.first_execution_run_id, digest(await handle.fetch_history()))
    events = stored_history(run).events
    assert events[-1].HasField("workflow_task_scheduled_event_attributes") and len(events) == 2
    await visible(run, RUNNING)
    return {"namespace": identity, "closed": closed, "pending": asdict(run)}


async def denied(call, *expected: RPCStatusCode, message: str | None = None) -> None:
    try:
        await call
    except RPCError as error:
        assert error.status in expected and (message is None or message in str(error))
    else:
        raise AssertionError("protected Temporal admitted unsupported legacy access")


def assert_plaintext_rejected() -> None:
    with socket.create_connection((NATIVE_HOST, 7233), timeout=5) as connection:
        try:
            # HTTP/2 client connection preface followed by an empty SETTINGS frame.
            connection.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n" + b"\x00\x00\x00\x04\x00\x00\x00\x00\x00")
            response = connection.recv(1)
        except ConnectionResetError:
            return
        assert not response, "protected Temporal responded to plaintext HTTP/2"


async def native(manifest: dict) -> None:
    operator = await temporal("operator")
    assert await namespace(operator) == manifest["namespace"]
    await asyncio.to_thread(assert_plaintext_rejected)
    assert await namespace(await temporal("operator")) == manifest["namespace"]

    dispatcher = await temporal("dispatcher", identity="ai-res-outbox-dispatcher")
    await denied(OperationStarter(dispatcher).start(operation()), RPCStatusCode.PERMISSION_DENIED)
    observer = await temporal("reconciliation")
    for entry in manifest["closed"]:
        run = Run(**entry)
        execution = run.execution()
        await denied(operator.workflow_service.get_workflow_execution_history(
            GetWorkflowExecutionHistoryRequest(namespace=NAMESPACE, execution=execution), timeout=RPC_TIMEOUT,
        ), RPCStatusCode.PERMISSION_DENIED)
        await denied(observer.workflow_service.describe_workflow_execution(
            DescribeWorkflowExecutionRequest(namespace=NAMESPACE, execution=execution), timeout=RPC_TIMEOUT,
        ), RPCStatusCode.PERMISSION_DENIED)
        await assert_terminal_replay(run)

    # A started legacy Run is still running in storage. The native Manager cannot receive its task token or history.
    waiting = Run(**manifest["pending"])
    history = stored_history(waiting)
    assert digest(history) == waiting.history_sha256
    scheduled = history.events[-1]
    assert scheduled.HasField("workflow_task_scheduled_event_attributes")
    manager = await temporal("manager", identity="ai-res-manager-runtime")
    await denied(manager.workflow_service.poll_workflow_task_queue(PollWorkflowTaskQueueRequest(
        namespace=NAMESPACE, task_queue=TaskQueue(name=MANAGER_TASK_QUEUE), identity="ai-res-manager-runtime",
    ), timeout=RPC_TIMEOUT), RPCStatusCode.UNAVAILABLE, message="task issuance unavailable")
    await wait_for_denied_task_timeout(waiting, manifest["namespace"]["id"], scheduled.event_id)
    await visible(waiting, RUNNING)


async def rollback(manifest: dict) -> None:
    client = await temporal()
    assert await namespace(client) == manifest["namespace"]
    for entry in manifest["closed"]:
        run = Run(**entry)
        handle = client.get_workflow_handle(run.workflow_id, run_id=run.run_id)
        assert digest(await handle.fetch_history()) == run.history_sha256
        await assert_terminal_replay(run)

    # No Start retry is needed. The legacy Worker resumes the original Run after its native-denied task times out.
    waiting = Run(**manifest["pending"])
    handle = client.get_workflow_handle(waiting.workflow_id, run_id=waiting.run_id, result_type=OperationWorkflowResult)
    fixture = FakePlatform()
    try:
        async with asyncio.timeout(35), manager_worker(client, fixture):
            result = await handle.result()
    except TimeoutError:
        # Report only event names/positions and pending-task metadata. No payloads or tokens.
        try:
            execution = await handle.describe(rpc_timeout=timedelta(seconds=3))
            task = execution.raw_description.pending_workflow_task
            pending = f"{PendingWorkflowTaskState.Name(task.state)} attempt {task.attempt}"
        except RPCError as error:
            pending = f"Describe returned {error.status.name}"
        raise AssertionError(
            f"stock did not finish the original Run: {pending}; ack={fixture.calls['ack']}, fail={fixture.calls['fail']}; "
            f"history: {event_summary(stored_history(waiting))}"
        ) from None
    assert (result.outcome, result.status) == ("SKELETON_FAILED_CLOSED", "FAILED")
    assert fixture.calls["ack"] == fixture.calls["fail"] == 1
    history = await handle.fetch_history()
    assert history.run_id == waiting.run_id
    await assert_terminal_replay(Run(waiting.workflow_id, waiting.run_id, digest(history)))


def main() -> None:
    phase = sys.argv[1:]
    if phase == ["seed"]:
        print(json.dumps(asyncio.run(seed())))
    elif phase == ["native"]:
        asyncio.run(native(json.load(sys.stdin)))
    elif phase == ["rollback"]:
        asyncio.run(rollback(json.load(sys.stdin)))
    else:
        raise SystemExit("select seed, native or rollback")


if __name__ == "__main__":
    main()
