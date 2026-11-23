"""Explicit loopback native Temporal probe using PostgreSQL and the real Platform routes."""
import asyncio
import base64
import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
from contextlib import asynccontextmanager, nullcontext
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from secrets import token_hex
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.responses import Response
from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.enums.v1 import HistoryEventFilterType, TimeoutType, WorkflowExecutionStatus
from temporalio.api.history.v1 import History, HistoryEvent
from temporalio.api.workflowservice.v1 import (
    DescribeWorkflowExecutionRequest,
    GetWorkflowExecutionHistoryRequest,
    ListWorkflowExecutionsRequest,
    RequestCancelWorkflowExecutionRequest,
)
from temporalio.client import WorkflowHistory
from temporalio.service import RPCError, RPCStatusCode, TLSConfig
from temporalio.worker import Replayer
from testcontainers.community.postgres import PostgresContainer

from ai_res.api import write_api
from ai_res.api.app import create_app
from ai_res.api.platform_auth_control import register_native_auth_control
from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.api.serve_platform_v2 import create_listener
from ai_res.application import assigned_dispatch
from ai_res.application.assigned_dispatch import AssignedDeliveryBackend
from ai_res.application.native_auth_control import NativeAuthControl
from ai_res.application.observe_operations import BoundExecutionObservationRequest, TemporalExecutionObserver
from ai_res.application.plan_approval_consumer import PlanApprovalSchedule
from ai_res.application.plan_execution import prepare_plan_execution
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.application.reconcile_operations import bind_verified_initial_run, prepare_assigned_start
from ai_res.application.reconcile_scheduler import BoundStartSchedule, ReconciliationScope
from ai_res.cli.assigned_delivery_client import AssignedDeliveryClient
from ai_res.cli.outbox import main as outbox_cli
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm import LLMLimits
from ai_res.llm.transport import TransportResult
from ai_res.llm.types import FinishReason, Usage
from ai_res.modules.events import delivery
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.dispatcher import Dispatcher, DispatcherConfig
from ai_res.modules.events.outbox_repository import OutboxRepository, OutboxRow
from ai_res.modules.events.temporal_start import assigned_start_request
from ai_res.modules.iam.platform_credentials import (
    AssignedDeliveryCredentialIssuer,
    PlatformAction,
    PlatformCredentialIssuer,
    PlatformCredentialLimits,
    PlatformCredentialVerifier,
)
from ai_res.modules.iam.sessions import RevokeReason
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.reconciliation import ExecutionState
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.client import AssignedOperationCanceller, AssignedOperationStarter
from ai_res.orchestration.contracts import CANCEL_DESTINATION, MANAGER_INTAKE_WORKFLOW, PLAN_EXECUTION_WORKFLOW, START_DESTINATION, workflow_id_for
from ai_res.orchestration.manager_workflows import BoundWorkflowCall, ManagerIntakeWorkflow, PlanExecutionWorkflow
from ai_res.orchestration.platform_port import PlatformPermanentError
from ai_res.orchestration.workflows import ACTIVITY_TIMEOUT
from ai_res.platform.config import load_settings
from ai_res.platform.telemetry import build_tracer_provider
from ai_res.runtime.assigned_manager import compose_assigned_manager
from ai_res.runtime.manager_activities import assigned_manager_worker
from ai_res.runtime.manager_reasoning import ManagerReasoning, ManagerReasoningInput
from ai_res.runtime.platform_control_client import ManagerHttpPlatform, PlatformControlClient
from tests.integration.test_candidate_control_tls import certificates
from tests.unit.test_llm_gateway import Rig, profile

from .conftest import Pg, _compose_postgres_image
from .test_write_api import CONTRACTS, World, key, send

pytestmark = [pytest.mark.postgres, pytest.mark.temporal]


def candidate_history(storage: Pg, run_id: UUID) -> list[HistoryEvent]:
    # Temporal 1.29 uses the initial Run ID as tree_id and stores pages as Proto3.
    with storage.connect("temporal", dbname="temporal_db") as history_db:
        batches = history_db.execute("""
            SELECT data FROM history_node WHERE tree_id=%s AND data_encoding='Proto3' ORDER BY node_id
        """, (run_id.bytes,)).fetchall()
    return [event for data, in batches for event in History.FromString(data).events]
COMPOSE_CANDIDATE = os.environ.get("G02_NATIVE_COMPOSE_CANDIDATE") == "1"
COMPOSE_NETWORK = COMPOSE_CANDIDATE and os.environ.get("G02_NATIVE_COMPOSE_NETWORK") == "1"
COMPOSE_SECRETS = Path("/run/secrets")


class ComposePg(Pg):
    """Connect to the fresh, provisioned databases of the isolated Compose project."""

    def __init__(self):
        self.host, self.port = "postgres", 5432
        assert (socket.gethostbyname(self.host) == "127.0.0.1") is not COMPOSE_NETWORK
        self.sslrootcert = COMPOSE_SECRETS / "postgres_tls_ca_cert"
        self.superuser_pw = (COMPOSE_SECRETS / "postgres_superuser_password").read_text()
        self.passwords = {
            role: (COMPOSE_SECRETS / name).read_text()
            for role, name in (
                ("ai_res_api", "api_db_password"),
                ("ai_res_platform_api", "platform_api_db_password"),
                ("temporal", "temporal_db_password"),
            )
        }
        if COMPOSE_NETWORK:
            self.passwords["ai_res_outbox_dispatcher"] = (COMPOSE_SECRETS / "outbox_db_password").read_text()


@pytest.fixture(scope="session", autouse=True)
def _template_built_first(request):
    if not COMPOSE_CANDIDATE:
        request.getfixturevalue("migrated_template")


@pytest.fixture
def migrated(request):
    return ComposePg() if COMPOSE_CANDIDATE else request.getfixturevalue("migrated")


def candidate_listener(tmp_path, ca, cert, server_key, manager_key, native_key):
    registry = tmp_path / "candidate.keys"
    registry.write_text("".join(
        f"{service} {base64.b64encode(key.public_key().public_bytes_raw()).decode()}\n"
        for service, key in (("MANAGER_RUNTIME", manager_key), ("TEMPORAL_AUTH_CONTROL", native_key))
    ))
    listener = create_listener(load_settings({
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": "postgres", "AI_RES_DB_USER": "ai_res_platform_api",
        "AI_RES_DB_PASSWORD_FILE": str(COMPOSE_SECRETS / "platform_api_db_password"),
        "AI_RES_DB_SSLMODE": "verify-full", "AI_RES_DB_SSLROOTCERT_FILE": str(ca),
        "AI_RES_SERVICE_PUBLIC_KEYS_FILE": str(registry), "AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS": "30",
        "AI_RES_PLATFORM_TLS_CERTIFICATE_FILE": str(cert), "AI_RES_PLATFORM_TLS_KEY_FILE": str(server_key),
        "AI_RES_PLATFORM_REQUEST_MAX_BYTES": "4096", "AI_RES_PLATFORM_CREDENTIAL_MAX_BYTES": "2048",
        "AI_RES_PLATFORM_LISTENER_MAX_CONNECTIONS": "32", "AI_RES_PLATFORM_API_TIMEOUT_SECONDS": "2",
        "AI_RES_PLATFORM_LISTENER_BIND_HOST": socket.gethostbyname("platform-api") if COMPOSE_NETWORK else "127.0.0.1",
    }))
    return listener


def assert_compose_sql_tls(storage):
    with storage.connect(dbname="postgres") as connection:
        rows = connection.execute("""
            SELECT a.usename, a.datname, count(*) FILTER (WHERE s.ssl), count(*) FILTER (WHERE NOT s.ssl)
            FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid)
            WHERE a.usename IN ('temporal', 'ai_res_platform_api', 'ai_res_outbox_dispatcher')
            GROUP BY a.usename, a.datname
        """).fetchall()
    expected = {
        ("temporal", "temporal_db"), ("temporal", "temporal_visibility_db"), ("ai_res_platform_api", "ai_res_db"),
    }
    if COMPOSE_NETWORK:
        expected.add(("ai_res_outbox_dispatcher", "ai_res_db"))
    assert {(user, db) for user, db, *_ in rows} == expected
    assert all(secured > 0 and cleartext == 0 for _, _, secured, cleartext in rows)
    role_credential = storage.passwords["temporal"]
    for host, mode, error in (
        ("postgres", "disable", "pg_hba.conf rejects connection"),
        (socket.gethostbyname("postgres"), "verify-full", "does not match host name"),
    ):
        with pytest.raises(psycopg.OperationalError, match=error), psycopg.connect(
            host=host, port=5432, user="temporal", dbname="temporal_db", password=role_credential,
            sslmode=mode, sslrootcert=str(storage.sslrootcert), connect_timeout=3,
        ):
            pytest.fail("unverified PostgreSQL connection was accepted")


@asynccontextmanager
async def assigned_process(module, environment):
    inherited = {name: os.environ[name] for name in ("PATH", "PYTHONPATH") if name in os.environ}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", module, env={**inherited, "PYTHONDONTWRITEBYTECODE": "1", **environment},
    )
    try:
        yield process
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()


async def assert_assigned_delivery_processes(w, epic, storage, client_dir, frontend_address, platform_host, ca, cert, server_key):
    keypair = Ed25519PrivateKey.generate()
    signing_key = client_dir / "outbox-signing-key"
    signing_key.write_bytes(base64.b64encode(keypair.private_bytes_raw()))
    signing_key.chmod(0o600)
    registry = client_dir / "outbox-key-registry"
    registry.write_bytes(b"OUTBOX_DISPATCHER " + base64.b64encode(keypair.public_key().public_bytes_raw()) + b"\n")
    address = socket.gethostbyname(platform_host)
    with socket.socket() as reservation:
        reservation.bind((address, 0))
        port = reservation.getsockname()[1]
    common = {
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": "postgres", "AI_RES_DB_SSLMODE": "verify-full",
        "AI_RES_DB_SSLROOTCERT_FILE": str(storage.sslrootcert), "AI_RES_TEMPORAL_NAMESPACE": "auth-poc",
        "AI_RES_ASYNCAPI_CONTRACT_FILE": str(CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"),
        "AI_RES_PLATFORM_REQUEST_MAX_BYTES": "4096", "AI_RES_PLATFORM_CREDENTIAL_MAX_BYTES": "2048",
        "AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS": "30",
    }
    backend_env = common | {
        "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(COMPOSE_SECRETS / "api_db_password"),
        "AI_RES_ASSIGNED_DELIVERY_PUBLIC_KEYS_FILE": str(registry), "AI_RES_PLATFORM_TLS_CERTIFICATE_FILE": str(cert),
        "AI_RES_PLATFORM_TLS_KEY_FILE": str(server_key), "AI_RES_PLATFORM_LISTENER_MAX_CONNECTIONS": "16",
        "AI_RES_ASSIGNED_DELIVERY_BIND_HOST": address, "AI_RES_ASSIGNED_DELIVERY_BIND_PORT": str(port),
        "AI_RES_TEMPORAL_ADDRESS": frontend_address, "AI_RES_ASSIGNED_TEMPORAL_SERVER_NAME": "temporal-auth-poc",
        "AI_RES_ASSIGNED_TEMPORAL_CA_FILE": str(client_dir / "ca.pem"),
        "AI_RES_ASSIGNED_START_CERTIFICATE_FILE": str(client_dir / "dispatcher.pem"),
        "AI_RES_ASSIGNED_START_KEY_FILE": str(client_dir / "dispatcher.key"),
        "AI_RES_ASSIGNED_CANCEL_CERTIFICATE_FILE": str(client_dir / "backend-cancellation.pem"),
        "AI_RES_ASSIGNED_CANCEL_KEY_FILE": str(client_dir / "backend-cancellation.key"),
    }
    dispatcher_env = common | {
        "AI_RES_DB_USER": "ai_res_outbox_dispatcher", "AI_RES_DB_PASSWORD_FILE": str(COMPOSE_SECRETS / "outbox_db_password"),
        "AI_RES_SERVICE_SIGNING_KEY_FILE": str(signing_key), "AI_RES_ASSIGNED_DELIVERY_CA_FILE": str(ca),
        "AI_RES_ASSIGNED_DELIVERY_URL": f"https://{platform_host}:{port}",
    }
    async with assigned_process("ai_res.api.serve_assigned_delivery", backend_env) as backend:
        async with asyncio.timeout(12):
            while True:
                assert backend.returncode is None, f"delivery backend exited with {backend.returncode}"
                try:
                    _, writer = await asyncio.open_connection(address, port)
                except OSError:
                    await asyncio.sleep(0.05)
                else:
                    writer.close()
                    await writer.wait_closed()
                    break
        async with await w.client("analyst") as analyst:
            accepted = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Separate processes fixture"}, key())
            assert accepted.status_code == 202
            operation = UUID(accepted.json()["id"])
            outbox = create_session_factory(w.iam.engine("ai_res_outbox_dispatcher"))
            owner = "handoff-retry-fixture"
            async with UnitOfWork(outbox) as uow:
                rows = await OutboxRepository(uow.session).claim(owner, 20, 30, 3, [START_DESTINATION], assigned_namespace="auth-poc")
                event, = (row for row in rows if row.aggregate_id == operation)
            ttl = timedelta(seconds=20)
            limits = PlatformCredentialLimits(ttl, timedelta(0), 4096, 2048)
            first = AssignedDeliveryClient(
                dispatcher_env["AI_RES_ASSIGNED_DELIVERY_URL"], ca_file=ca, issuer=AssignedDeliveryCredentialIssuer(keypair, limits),
                ttl=ttl, timeout_seconds=5, owner=owner,
            )
            send_first = first._client.send

            async def lose_http_response(request, **kwargs):
                response = await send_first(request, **kwargs)
                assert response.status_code == 204
                await response.aclose()
                raise httpx.ReadError("fixture lost the private delivery response")

            try:
                with patch.object(first._client, "send", lose_http_response), pytest.raises(delivery.TransientDeliveryError):
                    await first.publish(event)
            finally:
                await first.aclose()
            run_id, = w.rows("SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", operation)[0]
            assert run_id is not None
            assert w.rows("SELECT status,attempt_count FROM audit.outbox_events WHERE id=%s", event.id) == [("IN_FLIGHT", 1)]
            # Backend settled the first call. The caller lost the outcome before recording publication.
            async with UnitOfWork(outbox) as uow:
                await uow.session.execute(text("UPDATE audit.outbox_events SET lease_until=now()-interval '1 second' WHERE id=:id"), {"id": event.id})
            async with assigned_process("ai_res.cli.dispatcher", dispatcher_env) as dispatcher:
                async with asyncio.timeout(20):
                    while w.rows("SELECT status,attempt_count FROM audit.outbox_events WHERE id=%s", event.id) != [("PUBLISHED", 2)]:
                        assert dispatcher.returncode is None, f"dispatcher exited with {dispatcher.returncode}"
                        await asyncio.sleep(0.05)
                assert w.rows("SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", operation) == [(run_id,)]
                async with UnitOfWork(outbox) as uow:
                    assert not await OutboxRepository(uow.session).mark_published(event.id, owner, event.attempt_count, event.replay_count)
                cancelled = await send(analyst, "post", f"/operations/{operation}/cancel", {}, key())
                assert cancelled.status_code == 202 and cancelled.json()["status"] == "CANCEL_REQUESTED"
                async with asyncio.timeout(15):
                    while w.rows("SELECT status FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s",
                                 operation, CANCEL_DESTINATION) != [("PUBLISHED",)]:
                        assert dispatcher.returncode is None
                        await asyncio.sleep(0.05)
            events = candidate_history(storage, run_id)
            assert sum(event.HasField("workflow_execution_signaled_event_attributes") for event in events) == 1
            assert w.count("platform.platform_auth_events", "action=%s AND reason=%s", "AUTHORIZE_ASSIGNED_DELIVERY", "AUTHORIZED") >= 3


@pytest.fixture
def temporal_postgres():
    password = token_hex(24)
    container = PostgresContainer(_compose_postgres_image(), username="postgres", password=password, dbname="postgres", driver=None)
    container.ports["5432"] = ("127.0.0.1", None)
    with container:
        running = container.get_wrapped_container()
        running.reload()
        bindings = running.attrs["NetworkSettings"]["Ports"].get("5432/tcp") or []
        assert len(bindings) == 1 and bindings[0]["HostIp"] == "127.0.0.1"
        yield Pg(container, password, {})


@pytest.mark.parametrize("store", [
    pytest.param("sqlite", marks=pytest.mark.skipif("G02_NATIVE_PROBE_BINARY" not in os.environ, reason="requires the pinned native probe build")),
    pytest.param("postgres", marks=pytest.mark.skipif(
        not {"G02_NATIVE_POSTGRES_PROBE_BINARY", "G02_TEMPORAL_SQL_TOOL", "G02_TEMPORAL_POSTGRES_SCHEMA_ROOT"} <= os.environ.keys(),
        reason="requires the pinned PostgreSQL test binary, schema tool and schema sources",
    )),
    pytest.param("compose", marks=pytest.mark.skipif(not COMPOSE_CANDIDATE, reason="requires the isolated Compose candidate")),
])
async def test_native_manager_workflow_with_platform_receipts(iam_world, tmp_path, store, request, monkeypatch):
    from check import certs, check, client, configure
    candidate = store == "compose"
    networked = candidate and COMPOSE_NETWORK
    lose_start_response = networked and os.environ.get("G02_PROBE_LOSE_START_RESPONSE") == "1"
    replay_exhausted_start = networked and os.environ.get("G02_PROBE_REPLAY_EXHAUSTED_START") == "1"
    manager_timeout = networked and os.environ.get("G02_PROBE_MANAGER_TIMEOUT") == "1"
    paginate_history = networked and os.environ.get("G02_PROBE_PAGINATE_HISTORY") == "1"
    frontend_host = "temporal-workflow" if networked else "127.0.0.1"

    w = World(iam_world, tmp_path, manager_dispatch_namespace="auth-poc")
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Native workflow", "ACTIVE"))
    async with await w.client("analyst") as analyst:
        accepted = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Loopback native fixture"}, key())
        assert accepted.status_code == 202
    oid = UUID(accepted.json()["id"])
    row, = w.rows("""
        SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
        FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
    """, START_DESTINATION, oid)
    event = OutboxRow(*row)
    assigned, operation_type = assigned_start_request(event)

    native_dir = Path("/native") if candidate else tmp_path / "native"
    client_dir = tmp_path / "native-clients" if candidate else native_dir
    client_dir.mkdir(mode=0o700)
    certs(client_dir)
    if candidate:
        for name in ("ca.pem", "server.pem", "server.key", "operator.pem", "operator.key"):
            shutil.copyfile(client_dir / name, native_dir / name)
    native_port = configure(native_dir, postgres=store != "sqlite", frontend_ip=socket.gethostbyname(frontend_host))
    process_env = {"LOCALHOST_IP": "127.0.0.1"}
    internode_ports = ()
    if store != "sqlite":
        from postgres_probe import configure_postgres, probe_internode_tls, write_postgres_configuration

        if candidate:
            storage = iam_world.pg
            internode_ports = write_postgres_configuration(native_dir, storage.port, storage.passwords["temporal"], candidate=True)
            for name in ("internode-ca.pem", "internode.pem", "internode.key"):
                shutil.copyfile(native_dir / name, client_dir / name)
        else:
            binary = Path(os.environ["G02_NATIVE_POSTGRES_PROBE_BINARY"]).resolve(strict=True)
            command = [binary, "-test.run=^TestServeNativePostgresProbe$", "-test.timeout=90s"]
            process_env["G02_NATIVE_POSTGRES_FIXTURE_DIR"] = str(native_dir)
            storage = request.getfixturevalue("temporal_postgres")
            with storage.connect(dbname="postgres") as fixture_database:
                internode_ports = configure_postgres(
                    native_dir, fixture_database, storage.port,
                    Path(os.environ["G02_TEMPORAL_SQL_TOOL"]).resolve(strict=True),
                    Path(os.environ["G02_TEMPORAL_POSTGRES_SCHEMA_ROOT"]).resolve(strict=True),
                )
    else:
        command = [Path(os.environ["G02_NATIVE_PROBE_BINARY"]).resolve(strict=True), native_dir]
    # Legacy fixture client is unused when the native auth-control probe is active.
    (native_dir / "receipt-address").write_text("127.0.0.1:9")
    (native_dir / "receipt-key").write_bytes(bytes(64))
    (native_dir / "observe-fixture-operation").write_text(str(oid))
    platform_host = "platform-api" if networked else "127.0.0.1"
    ca, cert, server_key = certificates(tmp_path / "private-platform", hostname=platform_host)
    manager_key, native_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    ttl = timedelta(seconds=20)
    limits = PlatformCredentialLimits(timedelta(seconds=30), timedelta(seconds=1), 4096, 2048)
    if candidate:
        config = candidate_listener(tmp_path, storage.sslrootcert, cert, server_key, manager_key, native_key)
        app = config.app
    else:
        verifier = PlatformCredentialVerifier([manager_key.public_key()], limits, auth_control_keys=[native_key.public_key()])
        factory = create_session_factory(iam_world.engine("ai_res_platform_api"))
        audit = PlatformOperationControl(factory, failure_codes=frozenset())
        app = create_platform_v2_app(audit, verifier, max_body_bytes=4096, body_timeout_seconds=2)
        register_native_auth_control(app, NativeAuthControl(factory, audit), audit, verifier, max_bytes=4096, timeout_seconds=2)
        config = uvicorn.Config(
            app, host="127.0.0.1", ssl_certfile=str(cert), ssl_keyfile=str(server_key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
            log_config=None, access_log=False, proxy_headers=False, ws="none",
        )
    authorization_unavailable = False
    reject_plan_materialization = False
    workflow_task_checks: list[tuple[str, str]] = []

    @app.middleware("http")
    async def simulate_auth_control_outage(request, call_next):
        if authorization_unavailable and request.url.path == "/internal/auth-control/v1/authorize-bound-status":
            return Response(status_code=503)
        if reject_plan_materialization and request.url.path.endswith("/plan-tasks"):
            return Response("fixture message that must stay outside Temporal history", status_code=422)
        if paginate_history and request.url.path.startswith("/internal/auth-control/v1/"):
            action = request.url.path.rsplit("/", 1)[-1]
            if action in {"register-task", "check-task", "workflow-task-context"}:
                receipt = await request.json()
                if receipt.get("operationId") == str(oid) and receipt.get("taskKind") == "WORKFLOW":
                    response = await call_next(request)
                    if response.status_code in {200, 204}:
                        workflow_task_checks.append((action, receipt["tokenSha256"]))
                    return response
        return await call_next(request)

    model = profile()
    gateway = Rig(model).gw
    gateway.transport.script.append(TransportResult(
        output='{"goal":"Native fixture draft","scope":null,"primary_question":null}', finish_reason=FinishReason.STOP,
        usage=Usage(3, 7), provider_request_ref="fixture",
    ))

    input_requested, resume_input = asyncio.Event(), asyncio.Event()

    async def model_context(ref, message):
        input_requested.set()
        await resume_input.wait()
        return ManagerReasoningInput(ref.operation.operation_id, model.id, "run-1", "INTERNAL", LLMLimits(100, 10), message)

    socket_context = nullcontext(None) if candidate else socket.socket()
    log_context = nullcontext(None) if candidate else (native_dir / "server.log").open("wb")
    with socket_context as listener, log_context as log:
        if listener:
            listener.bind(("127.0.0.1", 0))
            config.port = listener.getsockname()[1]
        origin = f"https://{platform_host}:{config.port}"
        (native_dir / "native-auth-origin").write_text(origin)
        (native_dir / "native-auth-ca").write_bytes(ca.read_bytes())
        seed_path = native_dir / "native-auth-seed"
        seed_path.write_bytes(native_key.private_bytes_raw())
        seed_path.chmod(0o600)
        server = uvicorn.Server(config)
        serve = asyncio.create_task(server.serve(sockets=[listener] if listener else None))
        control = PlatformControlClient(origin, ca_file=ca, issuer=PlatformCredentialIssuer(manager_key, limits), ttl=ttl, timeout_seconds=2)
        process = None if candidate else subprocess.Popen(command, cwd=native_dir, stdout=log, stderr=log, env=process_env)  # noqa: S603
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
            if networked:
                assert [sock.getsockname() for listener_server in server.servers for sock in listener_server.sockets] == [
                    (socket.gethostbyname("platform-api"), config.port),
                ]
            if candidate:
                (native_dir / "ready").touch(exist_ok=False)
            await check(client_dir, native_port, process, assigned=True, host=frontend_host)
            for internode_port in internode_ports:
                if networked:
                    with pytest.raises(ConnectionRefusedError):
                        socket.create_connection((frontend_host, internode_port), timeout=2).close()
                    continue
                await asyncio.to_thread(probe_internode_tls, client_dir, internode_port, "internode")
                for untrusted_identity in (None, "manager"):
                    with pytest.raises(ssl.SSLError):
                        await asyncio.to_thread(probe_internode_tls, client_dir, internode_port, untrusted_identity)
            publisher = await client(client_dir, native_port, "dispatcher", host=frontend_host, rpc_identity="ai-res-outbox-dispatcher")
            runtime = await client(client_dir, native_port, "manager", host=frontend_host, lazy=False, rpc_identity="ai-res-manager-runtime")
            observer = await client(client_dir, native_port, "operator", host=frontend_host)
            reconciler = await client(client_dir, native_port, "reconciliation-observer", host=frontend_host)
            start_fields = []
            build_start = publisher._impl._build_start_workflow_execution_request

            async def collect_start_shape(input):
                proto = await build_start(input)
                start_fields.extend(field.name for field, value in proto.ListFields())
                return proto

            publisher._impl._build_start_workflow_execution_request = collect_start_shape
            def describe_run(run_id):
                return DescribeWorkflowExecutionRequest(namespace=reconciler.namespace, execution=WorkflowExecution(
                    workflow_id=workflow_id_for(oid), run_id=str(run_id),
                ))

            async def bind_started(request, op_type, run_id):
                with pytest.raises(RPCError) as unbound:
                    await reconciler.workflow_service.describe_workflow_execution(describe_run(run_id), timeout=timedelta(seconds=2))
                assert unbound.value.status is RPCStatusCode.PERMISSION_DENIED
                # The mTLS frontend has already checked the initial event before returning the Start receipt.
                return await bind_verified_initial_run(
                    w.services.factory, request, operation_type=op_type, namespace=publisher.namespace, run_id=run_id,
                )

            starter = AssignedOperationStarter(publisher)

            async def prepare(request, op_type):
                return await prepare_assigned_start(w.services.factory, request, operation_type=op_type, namespace=publisher.namespace)

            if networked:
                backend_client = await client(client_dir, native_port, "backend-cancellation", host=frontend_host)
                backend_delivery = AssignedDeliveryBackend(
                    w.services.factory, start_client=publisher, cancel_client=backend_client, cancel_deadline=timedelta(seconds=2),
                )

                async def observe_before_bind(factory, request, *, operation_type, namespace, run_id):
                    if request.operation.operation_id == str(oid):
                        with pytest.raises(RPCError) as unbound:
                            await reconciler.workflow_service.describe_workflow_execution(describe_run(run_id), timeout=timedelta(seconds=2))
                        assert unbound.value.status is RPCStatusCode.PERMISSION_DENIED
                    return await bind_verified_initial_run(factory, request, operation_type=operation_type, namespace=namespace, run_id=run_id)

                monkeypatch.setattr(assigned_dispatch, "bind_verified_initial_run", observe_before_bind)
                with pytest.raises(delivery.PermanentDeliveryError) as untrusted_route:
                    await backend_delivery.publish(replace(event, dispatch_namespace="wrong-namespace"))
                assert untrusted_route.value.code == delivery.ENVELOPE_MISMATCH
                assert not start_fields

                dispatcher_factory = create_session_factory(iam_world.engine("ai_res_outbox_dispatcher"))
                event_contract = EventContract.from_file(CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml")
                configured = DispatcherConfig(owner="candidate-delivery", batch_size=1, destinations=(START_DESTINATION,),
                                              assigned_namespace=backend_delivery.namespace, max_attempts=1 if replay_exhausted_start else 8)
                outbox_dispatcher = Dispatcher(dispatcher_factory, backend_delivery, event_contract, configured)

                async def lose_ack(_repository, row_id, owner, attempt, replay_count):
                    assert (row_id, owner, attempt, replay_count) == (event.id, configured.owner, 1, 0)
                    return False

                if replay_exhausted_start:
                    with monkeypatch.context() as patch:
                        async def unavailable_before_send(_starter, _request, _op_type):
                            raise TimeoutError("fixture unavailable before sending Start")

                        patch.setattr(AssignedOperationStarter, "start", unavailable_before_send)
                        assert await outbox_dispatcher.run_once() == 0
                    assert not start_fields
                    assert w.rows("""
                        SELECT start_admitted,workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s
                    """, oid) == [(True, None)]
                    assert w.rows("SELECT status,attempt_count,replay_count FROM audit.outbox_events WHERE id=%s", event.id) == [("QUARANTINED", 1, 0)]
                    async with UnitOfWork(dispatcher_factory) as uow:
                        assert await OutboxRepository(uow.session).replay([event.event_id]) == 0
                    with pytest.raises(DBAPIError, match="requires audited replay approval"):
                        async with UnitOfWork(dispatcher_factory) as uow:
                            await uow.session.execute(text("UPDATE audit.outbox_events SET status='PENDING' WHERE id=:id"), {"id": event.id})
                    path = f"/operations/{oid}/start-replay"
                    async with await w.client("analyst") as analyst, await w.client("padmin", mfa=False) as weak_admin:
                        assert (await send(analyst, "get", path, None)).status_code == 403
                        assert (await send(weak_admin, "get", path, None)).status_code == 404
                    approve = write_api.approve_quarantined_start

                    async def revoke_before_approval(session, operation_id, target, *, actor_id, session_id, correlation_id):
                        assert await w.services.sessions.revoke(org, session_id, RevokeReason.LOGOUT)
                        return await approve(session, operation_id, target, actor_id=actor_id, session_id=session_id, correlation_id=correlation_id)

                    with monkeypatch.context() as revoked:
                        revoked.setattr(write_api, "approve_quarantined_start", revoke_before_approval)
                        async with await w.client("padmin", mfa=True) as signed_out:
                            target = await send(signed_out, "get", path, None)
                            assert target.status_code == 200
                            headers = {**key(), "If-Match": target.headers["ETag"]}
                            assert (await send(signed_out, "post", f"{path}/{event.event_id}", {}, headers)).status_code == 412
                    assert w.count("audit.audit_events", "object_id=%s AND action=%s", oid, "OPERATION_START_REPLAY_APPROVED") == 0
                    async with await w.client("padmin", mfa=True) as admin:
                        target = await send(admin, "get", path, None)
                        assert target.status_code == 200, target.json()
                        assert target.json()["eventId"] == str(event.event_id)
                        assert (await send(admin, "post", f"{path}/{event.event_id}", {}, key())).status_code == 428
                        assert (await send(admin, "post", f"{path}/{uuid4()}", {}, {**key(), "If-Match": target.headers["ETag"]})).status_code == 412
                        headers = {**key(), "If-Match": target.headers["ETag"]}
                        replay = await send(admin, "post", f"{path}/{event.event_id}", {}, headers)
                        assert replay.status_code == 202, replay.json()
                        assert (await send(admin, "post", f"{path}/{event.event_id}", {}, headers)).json() == replay.json()
                        assert (await send(admin, "post", f"{path}/{event.event_id}", {}, {**key(), "If-Match": target.headers["ETag"]})).status_code == 412
                    assert w.count("audit.audit_events", "object_id=%s AND action=%s", oid, "OPERATION_START_REPLAY_APPROVED") == 1
                    assert await outbox_dispatcher.run_once() == 1
                elif lose_start_response:
                    confirmed_runs: list[UUID] = []
                    original_start = AssignedOperationStarter.start

                    async def lose_first_reply(instance, request, op_type):
                        outcome = await original_start(instance, request, op_type)
                        confirmed_runs.append(outcome.run_id)
                        if len(confirmed_runs) == 1:
                            raise TimeoutError("fixture lost the accepted Start reply")
                        return outcome

                    with monkeypatch.context() as patch:
                        patch.setattr(AssignedOperationStarter, "start", lose_first_reply)
                        assert await outbox_dispatcher.run_once() == 0
                        assert len(confirmed_runs) == 1
                        assert w.rows(
                            "SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", oid,
                        ) == [(None,)]
                        assert w.rows("SELECT status,attempt_count,replay_count FROM audit.outbox_events WHERE id=%s", event.id) == [("PENDING", 1, 0)]
                        async with UnitOfWork(dispatcher_factory) as uow:
                            ready = await uow.session.execute(text("""
                                UPDATE audit.outbox_events SET available_at=now()
                                WHERE id=:id AND status='PENDING' AND attempt_count=1
                            """), {"id": event.id})
                            assert ready.rowcount == 1
                        assert await outbox_dispatcher.run_once() == 1
                    assert confirmed_runs == [confirmed_runs[0], confirmed_runs[0]]
                else:
                    with monkeypatch.context() as patch:
                        patch.setattr(OutboxRepository, "mark_published", lose_ack)
                        assert await outbox_dispatcher.run_once() == 0
                    assert w.rows("SELECT status,attempt_count,replay_count FROM audit.outbox_events WHERE id=%s", event.id) == [("IN_FLIGHT", 1, 0)]
                (run_id,), = w.rows("SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", oid)
                assert run_id is not None
            else:
                try:
                    assert await prepare(assigned, operation_type)
                    run_id = (await starter.start(assigned, operation_type)).run_id
                except RPCError as error:
                    operations = w.rows("SELECT reason,action FROM platform.platform_auth_events")
                    pytest.fail(f"native Start rejected ({error.status.name}), wire fields={start_fields}, audit={operations}")
                assert await bind_started(assigned, operation_type, run_id)

            describe = describe_run(run_id)
            assert w.rows("SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", oid) == [(run_id,)]
            reconciliation = TemporalExecutionObserver(reconciler, deadline=timedelta(seconds=2))
            bound = BoundExecutionObservationRequest(UUID(assigned.assignment_id), oid, MANAGER_INTAKE_WORKFLOW, run_id, reconciler.namespace)
            assert (await reconciliation.observe(bound)).state is ExecutionState.RUNNING
            authorization_unavailable = True
            with pytest.raises(RPCError) as unavailable:
                await reconciler.workflow_service.describe_workflow_execution(describe, timeout=timedelta(seconds=2))
            assert unavailable.value.status is RPCStatusCode.UNAVAILABLE
            assert (await reconciliation.observe(bound)).state is ExecutionState.UNAVAILABLE
            authorization_unavailable = False
            schedule = BoundStartSchedule(scopes=(ReconciliationScope(organization_id=org, project_id=w.p1),),
                                          page_size=1, interval_seconds=0.1, page_timeout_seconds=4, rpc_timeout_seconds=2,
                                          server_name="temporal-auth-poc", ca_file=client_dir / "ca.pem",
                                          certificate_file=client_dir / "reconciliation-observer.pem",
                                          private_key_file=client_dir / "reconciliation-observer.key")
            config_file = client_dir / "reconciliation.json"
            config_file.write_text(schedule.model_dump_json())
            backend_settings = w.settings.model_copy(update={"reconciliation_config_file": config_file,
                                                             "temporal_address": f"{frontend_host}:{native_port}", "temporal_namespace": reconciler.namespace})
            exporter = InMemorySpanExporter()
            backend = create_app(backend_settings, identity=w.services, tracer_provider=build_tracer_provider(exporter))
            audited = ("reason=%s AND action=%s", "AUTHORIZED", "AUTHORIZE_BOUND_STATUS")
            before = w.count("platform.platform_auth_events", *audited)
            async with backend.router.lifespan_context(backend), asyncio.timeout(5):
                while not any(event.name == "operation.reconciliation.observation" and event.attributes.get("outcome") == "RUNNING"
                              for span in exporter.get_finished_spans() if span.name == "operation.reconciliation.page" for event in span.events):
                    await asyncio.sleep(0.05)
            assert w.count("platform.platform_auth_events", *audited) > before
            assert w.rows("SELECT status FROM operations.operations WHERE id=%s", oid) == [("ACCEPTED",)]
            for caller, run in ((runtime, str(run_id)), (reconciler, ""), (reconciler, str(uuid4()))):
                rejected = DescribeWorkflowExecutionRequest(namespace=reconciler.namespace, execution=WorkflowExecution(
                    workflow_id=workflow_id_for(oid), run_id=run,
                ))
                with pytest.raises(RPCError) as denied:
                    await caller.workflow_service.describe_workflow_execution(rejected, timeout=timedelta(seconds=2))
                assert denied.value.status is RPCStatusCode.PERMISSION_DENIED
            async with assigned_manager_worker(runtime, ManagerHttpPlatform(control, model_context, epic_context=networked), ManagerReasoning(gateway),
                                               build_id="ai-res-manager-probe-1"):
                try:
                    async with asyncio.timeout(10):
                        await input_requested.wait()
                    assert w.rows("SELECT status FROM operations.operations WHERE id=%s", oid) == [("RUNNING",)]
                    visible = await reconciler.workflow_service.describe_workflow_execution(describe, timeout=timedelta(seconds=2))
                    assert {field.name for field, _ in visible.ListFields()} == {"workflow_execution_info"}
                    assert {field.name for field, _ in visible.workflow_execution_info.ListFields()} == {"execution", "type", "status", "task_queue"}
                    assert (await reconciliation.observe(bound)).state is ExecutionState.RUNNING
                    with pytest.raises(RPCError) as listing:
                        await reconciler.workflow_service.list_workflow_executions(
                            ListWorkflowExecutionsRequest(namespace=reconciler.namespace), timeout=timedelta(seconds=2),
                        )
                    assert listing.value.status is RPCStatusCode.PERMISSION_DENIED
                    with pytest.raises(RPCError) as cancellation:
                        await reconciler.workflow_service.request_cancel_workflow_execution(
                            RequestCancelWorkflowExecutionRequest(namespace=reconciler.namespace, workflow_execution=describe.execution,
                                                                  request_id=str(uuid4())), timeout=timedelta(seconds=2),
                        )
                    assert cancellation.value.status is RPCStatusCode.PERMISSION_DENIED
                finally:
                    resume_input.set()
                query = GetWorkflowExecutionHistoryRequest(
                    namespace=observer.namespace,
                    execution=WorkflowExecution(workflow_id=workflow_id_for(oid), run_id=str(run_id)),
                    history_event_filter_type=HistoryEventFilterType.HISTORY_EVENT_FILTER_TYPE_ALL_EVENT,
                    skip_archival=True,
                )
                for caller in (runtime, reconciler, publisher):
                    with pytest.raises(RPCError) as forbidden:
                        await caller.workflow_service.get_workflow_execution_history(query, timeout=timedelta(seconds=2))
                    assert forbidden.value.status is RPCStatusCode.PERMISSION_DENIED
                async with asyncio.timeout(20):
                    while True:
                        history = await observer.workflow_service.get_workflow_execution_history(query, timeout=timedelta(seconds=2))
                        assert not history.next_page_token
                        last = history.history.events[-1]
                        if last.HasField("workflow_execution_completed_event_attributes"):
                            break
                        await asyncio.sleep(0.10)
                wire = history.history.SerializeToString(deterministic=True)
                for canary in (b"Loopback native fixture", b"Native fixture draft"):
                    assert canary not in wire
                assert w.rows("SELECT status FROM operations.operations WHERE id=%s", oid) == [("SUCCEEDED",)]
                if networked:
                    record, = w.rows("""
                        SELECT c.id,c.workflow_run_id,c.epic_state->>'operationStatus'
                        FROM work.manager_proposal_versions p
                        JOIN platform.manager_epic_context_versions c ON c.id=p.context_version_id
                        WHERE c.operation_id=%s
                    """, oid)
                    context_version, recorded_run, status = record
                    assert (recorded_run, status) == (run_id, "RUNNING")
                    assert str(context_version).encode() not in wire and b"hasOpenQuestion" not in wire
                if paginate_history:
                    assert any(
                        action == "register-task" and workflow_task_checks[index + 1:index + 3] == [
                            ("check-task", digest), ("workflow-task-context", digest),
                        ]
                        for index, (action, digest) in enumerate(workflow_task_checks)
                    ), "a native Workflow Task must revalidate its receipt after continuing History"
                assert (await reconciliation.observe(bound)).state is ExecutionState.SCOPE_MISMATCH
                if store != "sqlite":
                    with storage.connect("temporal" if candidate else None,
                                         dbname="temporal_visibility_db" if candidate else "temporal_probe_visibility") as visibility:
                        async with asyncio.timeout(10):
                            while not visibility.execute("""
                                SELECT 1 FROM executions_visibility WHERE workflow_id=%s AND run_id=%s AND status=%s
                            """, (workflow_id_for(oid), str(run_id), WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED)).fetchone():
                                await asyncio.sleep(0.1)
                if candidate:
                    assert_compose_sql_tls(storage)
                if networked and not (lose_start_response or replay_exhausted_start):
                    # Advance only the disposable lease clock so this test need not wait for its expiry.
                    async with UnitOfWork(dispatcher_factory) as uow:
                        expired = await uow.session.execute(text("""
                            UPDATE audit.outbox_events SET lease_until=now()-interval '1 second'
                            WHERE id=:id AND lease_owner=:owner AND status='IN_FLIGHT' AND attempt_count=1
                        """), {"id": event.id, "owner": configured.owner})
                        assert expired.rowcount == 1
                    fields_before_redelivery = tuple(start_fields)
                    assert fields_before_redelivery and await outbox_dispatcher.run_once() == 1
                    assert tuple(start_fields) == fields_before_redelivery
                if networked:
                    expected_attempts = (1, 1) if replay_exhausted_start else (2, 0)
                    assert w.rows("SELECT status,attempt_count,replay_count FROM audit.outbox_events WHERE id=%s", event.id) == [
                        ("PUBLISHED", *expected_attempts),
                    ]
                    assert w.rows("SELECT workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", oid) == [(run_id,)]
                    history_after = await observer.workflow_service.get_workflow_execution_history(query, timeout=timedelta(seconds=2))
                    assert history_after.history.SerializeToString(deterministic=True) == wire
                    with storage.connect("temporal", dbname="temporal_visibility_db") as visibility:
                        rows = visibility.execute(
                            "SELECT rtrim(run_id),status FROM executions_visibility WHERE workflow_id=%s", (workflow_id_for(oid),),
                        ).fetchall()
                    assert rows == [(str(run_id), WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED)]
            if networked:
                async def start_approved_plan(expected_version: int, title: str):
                    item = str(uuid4())
                    async with await w.client("analyst") as analyst:
                        draft = await send(analyst, "post", f"/epics/{epic}/plans", {
                            "expectedVersion": expected_version, "goal": title, "entries": [item],
                            "items": [{"id": item, "title": title, "taskType": "ANALYSIS"}],
                        }, key())
                        assert draft.status_code == 201, draft.json()
                        version = UUID(draft.json()["id"])
                        approval = await send(analyst, "post", f"/plan-versions/{version}/decision",
                                              {"decision": "APPROVE", "contentHash": draft.json()["contentHash"], "approvedItemIds": [item]},
                                              {**key(), "If-Match": draft.headers["ETag"]})
                        assert approval.status_code == 201
                    async with UnitOfWork(w.services.factory) as uow:
                        await uow.with_tenant(org, w.p1)
                        plan = await prepare_plan_execution(uow.session, org, w.p1, version, UUID(approval.json()["decisionId"]), uuid4(),
                                                            dispatch_namespace=reconciler.namespace)
                    plan_event, = w.rows("""
                        SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,
                               envelope,attempt_count,replay_count
                        FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
                    """, START_DESTINATION, plan)
                    plan_input, plan_type = assigned_start_request(OutboxRow(*plan_event))
                    assert await prepare(plan_input, plan_type)
                    plan_run = (await starter.start(plan_input, plan_type)).run_id
                    assert await bind_verified_initial_run(w.services.factory, plan_input, operation_type=plan_type,
                                                           namespace=publisher.namespace, run_id=plan_run)
                    return plan, plan_input, plan_run

                plan, plan_input, plan_run = await start_approved_plan(0, "Native Plan fixture")
                assignment = UUID(plan_input.assignment_id)
                plan_bound = BoundExecutionObservationRequest(assignment, plan, PLAN_EXECUTION_WORKFLOW, plan_run, reconciler.namespace)
                assert (await reconciliation.observe(plan_bound)).state is ExecutionState.RUNNING
                ack = BoundWorkflowCall(plan_input.operation, plan_input.assignment_id, workflow_id_for(plan), str(plan_run))
                assert (await control.call(ack, PlatformAction.ACKNOWLEDGE_START)).status == "RUNNING"
                assert (await reconciliation.observe(plan_bound)).state is ExecutionState.RUNNING
                reject_plan_materialization = True
                config_file.write_text(schedule.model_copy(update={
                    "admitted_operation_types": ("PLAN_EXECUTION",), "include_post_ack": True,
                }).model_dump_json())
                async with assigned_manager_worker(runtime, ManagerHttpPlatform(control, model_context), ManagerReasoning(gateway),
                                                   build_id="ai-res-manager-probe-1"):
                    async with asyncio.timeout(15):
                        while (await reconciliation.observe(plan_bound)).state is not ExecutionState.FAILED:
                            await asyncio.sleep(0.05)
                async with backend.router.lifespan_context(backend), asyncio.timeout(10):
                    while w.rows("SELECT status FROM operations.operations WHERE id=%s", plan) != [("FAILED",)]:
                        await asyncio.sleep(0.05)
                assert w.count("work.plan_item_tasks", "operation_id=%s", plan) == 0
                assert w.count("audit.audit_events", "action=%s AND object_id=%s", "OPERATION_POST_ACK_RECONCILED", plan) == 1
                events = candidate_history(storage, plan_run)
                activity_failure, = [event.activity_task_failed_event_attributes.failure for event in events
                                     if event.HasField("activity_task_failed_event_attributes")]
                workflow_failure, = [event.workflow_execution_failed_event_attributes.failure for event in events
                                     if event.HasField("workflow_execution_failed_event_attributes")]
                assert activity_failure.application_failure_info.type == "PermanentPlatformError"
                assert workflow_failure.cause == activity_failure
                assert not activity_failure.stack_trace and not workflow_failure.stack_trace
                assert b"fixture message that must stay outside Temporal history" not in History(events=events).SerializeToString()
                await Replayer(workflows=[PlanExecutionWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(plan), events))

                async with await w.client("analyst") as analyst:
                    new_intake = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Assigned cancellation fixture"}, key())
                    assert new_intake.status_code == 202
                cancel_operation = UUID(new_intake.json()["id"])
                cancel_start, = w.rows("""
                    SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
                    FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
                """, START_DESTINATION, cancel_operation)
                cancel_input, cancel_type = assigned_start_request(OutboxRow(*cancel_start))
                assert await prepare(cancel_input, cancel_type)
                cancel_run = (await starter.start(cancel_input, cancel_type)).run_id
                cancel_assignment = UUID(cancel_input.assignment_id)
                cancel_key = key()
                async with await w.client("analyst") as analyst:
                    early_reply = await send(analyst, "post", f"/operations/{cancel_operation}/cancel", {}, cancel_key)
                    assert early_reply.status_code == 409, early_reply.json()
                    assert early_reply.json()["code"] == "OPERATION_NOT_READY"
                assert w.rows("SELECT status FROM operations.operations WHERE id=%s", cancel_operation) == [("ACCEPTED",)]
                assert w.count("audit.outbox_events", "aggregate_id=%s AND destination=%s", cancel_operation, CANCEL_DESTINATION) == 0
                assert (await starter.start(cancel_input, cancel_type)).run_id == cancel_run
                assert await bind_verified_initial_run(w.services.factory, cancel_input, operation_type=cancel_type,
                                                       namespace=publisher.namespace, run_id=cancel_run)
                protected_cancel = AssignedOperationCanceller(backend_client, deadline=timedelta(seconds=2))
                with pytest.raises(RPCError) as premature:
                    await protected_cancel.signal(cancel_operation, cancel_run, cancel_assignment)
                assert premature.value.status is RPCStatusCode.PERMISSION_DENIED
                async with await w.client("analyst") as analyst:
                    cancel_response = await send(analyst, "post", f"/operations/{cancel_operation}/cancel", {}, cancel_key)
                    assert cancel_response.status_code == 202, cancel_response.json()
                    assert cancel_response.json()["status"] == "CANCEL_REQUESTED"
                with pytest.raises(RPCError) as denied_principal:
                    await AssignedOperationCanceller(runtime, deadline=timedelta(seconds=2)).signal(cancel_operation, cancel_run, cancel_assignment)
                assert denied_principal.value.status is RPCStatusCode.PERMISSION_DENIED
                with pytest.raises(RPCError) as denied_run:
                    await protected_cancel.signal(cancel_operation, uuid4(), cancel_assignment)
                assert denied_run.value.status is RPCStatusCode.PERMISSION_DENIED

                contract = EventContract.from_file(CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml")
                legacy = Dispatcher(dispatcher_factory, backend_delivery, contract,
                                    DispatcherConfig(owner="legacy-cancel", destinations=(CANCEL_DESTINATION,)))
                protected = Dispatcher(dispatcher_factory, backend_delivery, contract, DispatcherConfig(
                    owner="protected-cancel", destinations=(CANCEL_DESTINATION,), assigned_namespace=backend_delivery.namespace,
                ))
                assert await legacy.run_once() == 0
                assert await protected.run_once() == 1
                await protected_cancel.signal(cancel_operation, cancel_run, cancel_assignment)

                async with assigned_manager_worker(runtime, ManagerHttpPlatform(control, model_context), ManagerReasoning(gateway),
                                                   build_id="ai-res-manager-probe-1"):
                    async with asyncio.timeout(15):
                        while w.rows("SELECT status FROM operations.operations WHERE id=%s", cancel_operation) != [("CANCELLED",)]:
                            await asyncio.sleep(0.05)
                        while not any(event.HasField("workflow_execution_completed_event_attributes") for event in candidate_history(storage, cancel_run)):
                            await asyncio.sleep(0.05)
                events = candidate_history(storage, cancel_run)
                signal, = [item.workflow_execution_signaled_event_attributes for item in events
                           if item.HasField("workflow_execution_signaled_event_attributes")]
                assert signal.signal_name == "request_cancel" and not signal.input.payloads
                await Replayer(workflows=[ManagerIntakeWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(cancel_operation), events))
                # A lost publication mark is retried against the same terminal binding, without another signal.
                async with UnitOfWork(dispatcher_factory) as uow:
                    await uow.session.execute(text("""
                        UPDATE audit.outbox_events SET status='PENDING',published_at=NULL,available_at=now()
                        WHERE aggregate_id=:operation AND destination=:destination
                    """), {"operation": cancel_operation, "destination": CANCEL_DESTINATION})
                with monkeypatch.context() as patch:
                    def unexpected_cancel(*_args):
                        pytest.fail("a settled cancellation must not send another signal")

                    patch.setattr(AssignedOperationCanceller, "signal", unexpected_cancel)
                    assert await protected.run_once() == 1
                assert w.rows("SELECT status,attempt_count FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s",
                              cancel_operation, CANCEL_DESTINATION) == [("PUBLISHED", 2)]

                reject_plan_materialization = False
                cancel_plan, cancel_plan_input, cancel_plan_run = await start_approved_plan(1, "Native Plan cancellation fixture")
                async with assigned_manager_worker(runtime, ManagerHttpPlatform(control, model_context), ManagerReasoning(gateway),
                                                   build_id="ai-res-manager-probe-1"):
                    async with asyncio.timeout(15):
                        while w.rows("SELECT status FROM operations.operations WHERE id=%s", cancel_plan) != [("WAITING_FOR_DEPENDENCY",)]:
                            await asyncio.sleep(0.05)
                    mapped_items = w.rows("SELECT item_id,task_id FROM work.plan_item_tasks WHERE operation_id=%s", cancel_plan)
                    assert len(mapped_items) == 1
                    async with await w.client("analyst") as analyst:
                        cancelled_plan = await send(analyst, "post", f"/operations/{cancel_plan}/cancel", {}, key())
                        assert cancelled_plan.status_code == 202, cancelled_plan.json()
                        assert cancelled_plan.json()["status"] == "CANCEL_REQUESTED"
                    assert await legacy.run_once() == 0
                    outage = Dispatcher(dispatcher_factory, backend_delivery, contract, DispatcherConfig(
                        owner="protected-cancel-outage", destinations=(CANCEL_DESTINATION,), assigned_namespace=backend_delivery.namespace,
                        max_attempts=1,
                    ))

                    async def cancel_unavailable(*_args):
                        raise TimeoutError

                    with monkeypatch.context() as patch:
                        patch.setattr(AssignedOperationCanceller, "signal", cancel_unavailable)
                        assert await outage.run_once() == 0
                    (cancel_event, status, attempts, generation, namespace), = w.rows("""
                        SELECT event_id,status,attempt_count,replay_count,dispatch_namespace
                        FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s
                    """, cancel_plan, CANCEL_DESTINATION)
                    assert (status, attempts, generation, namespace) == ("QUARANTINED", 1, 0, reconciler.namespace)
                    cancel_bound = BoundExecutionObservationRequest(
                        UUID(cancel_plan_input.assignment_id), cancel_plan, PLAN_EXECUTION_WORKFLOW, cancel_plan_run, reconciler.namespace,
                    )
                    assert (await reconciliation.observe(cancel_bound)).state is ExecutionState.RUNNING
                    cli_settings = {
                        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": iam_world.pg.host, "AI_RES_DB_SSLMODE": "verify-full",
                        "AI_RES_DB_USER": "ai_res_outbox_dispatcher", "AI_RES_DB_SSLROOTCERT_FILE": str(iam_world.pg.sslrootcert),
                        "AI_RES_DB_PASSWORD_FILE": str(COMPOSE_SECRETS / "outbox_db_password"),
                    }
                    replay_command = ["replay", "--event-id", str(cancel_event)]
                    assert await asyncio.to_thread(outbox_cli, replay_command, cli_settings) == 2
                    assert await asyncio.to_thread(outbox_cli, [*replay_command, "--confirm"], cli_settings) == 0
                    assert await asyncio.to_thread(outbox_cli, [*replay_command, "--confirm"], cli_settings) == 2
                    assert await legacy.run_once() == 0
                    assert await protected.run_once() == 1
                    async with asyncio.timeout(15):
                        while not any(event.HasField("workflow_execution_completed_event_attributes")
                                      for event in candidate_history(storage, cancel_plan_run)):
                            await asyncio.sleep(0.05)
                assert w.rows("SELECT status FROM operations.operations WHERE id=%s", cancel_plan) == [("CANCELLED",)]
                assert w.rows("SELECT item_id,task_id FROM work.plan_item_tasks WHERE operation_id=%s", cancel_plan) == mapped_items
                assert w.rows("SELECT status,attempt_count,replay_count FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s",
                              cancel_plan, CANCEL_DESTINATION) == [("PUBLISHED", 1, 1)]
                assert w.count("audit.audit_events", "action=%s AND object_id=%s", "OPERATION_CANCELLATION_CONFIRMED", cancel_plan) == 1
                events = candidate_history(storage, cancel_plan_run)
                plan_signal, = [event.workflow_execution_signaled_event_attributes for event in events
                                if event.HasField("workflow_execution_signaled_event_attributes")]
                assert plan_signal.signal_name == "request_cancel" and not plan_signal.input.payloads
                await Replayer(workflows=[PlanExecutionWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(cancel_plan), events))

                async with await w.client("analyst") as analyst:
                    never_started = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Cancel before Start admission"}, key())
                    assert never_started.status_code == 202
                    never_operation = UUID(never_started.json()["id"])
                    cancelled = await send(analyst, "post", f"/operations/{never_operation}/cancel", {}, key())
                    assert cancelled.status_code == 202 and cancelled.json()["status"] == "CANCELLED"
                never_start, = w.rows("""
                    SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,
                           attempt_count,replay_count,dispatch_namespace
                    FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
                """, START_DESTINATION, never_operation)
                never_event = OutboxRow(*never_start)
                never_input, never_type = assigned_start_request(never_event)
                with pytest.raises(RPCError) as denied_before_admission:
                    await starter.start(never_input, never_type)
                assert denied_before_admission.value.status is RPCStatusCode.PERMISSION_DENIED
                with monkeypatch.context() as patch:
                    def unexpected_start(*_args):
                        pytest.fail("a pre-admission cancellation must settle its command without Start")

                    patch.setattr(AssignedOperationStarter, "start", unexpected_start)
                    await backend_delivery.publish(never_event)
                assert w.rows("""
                    SELECT start_admitted,workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s
                """, never_operation) == [(False, None)]
            if manager_timeout:
                # The preceding Plan-only scenario mutates the shared schedule;
                # restore the precise Manager allowlist for this independent leg.
                config_file.write_text(schedule.model_copy(update={
                    "admitted_operation_types": ("MANAGER_MESSAGE",), "include_post_ack": True,
                }).model_dump_json())
                timeout_message = "Synthetic timeout intake"
                timeout_sentinel = "Disposable Activity expired before model call"
                async with await w.client("analyst") as analyst:
                    timeout_intake = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": timeout_message}, key())
                    assert timeout_intake.status_code == 202
                timeout_op = UUID(timeout_intake.json()["id"])
                timeout_event, = w.rows("""
                    SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
                    FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
                """, START_DESTINATION, timeout_op)
                timeout_input, timeout_type = assigned_start_request(OutboxRow(*timeout_event))
                assert await prepare(timeout_input, timeout_type)
                timeout_run = (await starter.start(timeout_input, timeout_type)).run_id
                timeout_assignment = UUID(timeout_input.assignment_id)
                async with UnitOfWork(w.services.factory) as uow:
                    await uow.with_tenant(org, w.p1)
                    assert await OperationAssignments(uow.session).bind_run(timeout_assignment, timeout_op, timeout_run)
                timeout_bound = BoundExecutionObservationRequest(timeout_assignment, timeout_op, MANAGER_INTAKE_WORKFLOW, timeout_run, reconciler.namespace)
                entered, release = asyncio.Event(), asyncio.Event()

                async def hold_before_model(ref, _message):
                    assert ref.operation.operation_id == str(timeout_op)
                    entered.set()
                    await release.wait()
                    raise RuntimeError(timeout_sentinel)

                async with assigned_manager_worker(runtime, ManagerHttpPlatform(control, hold_before_model), ManagerReasoning(gateway),
                                                   build_id="ai-res-manager-probe-1"):
                    try:
                        async with asyncio.timeout(10):
                            await entered.wait()
                        assert w.rows("SELECT status FROM operations.operations WHERE id=%s", timeout_op) == [("RUNNING",)]
                        async with asyncio.timeout(ACTIVITY_TIMEOUT.total_seconds() + 15):
                            while (await reconciliation.observe(timeout_bound)).state is not ExecutionState.FAILED:
                                await asyncio.sleep(0.20)
                    finally:
                        release.set()
                audit_scope = ("action=%s AND object_id=%s", "OPERATION_RECONCILIATION_REQUIRED", timeout_op)
                async with backend.router.lifespan_context(backend), asyncio.timeout(10):
                    while not w.count("audit.audit_events", *audit_scope):
                        await asyncio.sleep(0.05)
                assert w.count("audit.audit_events", *audit_scope) == 1
                assert w.rows("""
                    SELECT reason_code,details->>'observedStatus' FROM audit.audit_events WHERE action=%s AND object_id=%s
                """, "OPERATION_RECONCILIATION_REQUIRED", timeout_op) == [("DOMAIN_OUTCOME_REQUIRED", "FAILED")]
                assert w.rows("SELECT status FROM operations.operations WHERE id=%s", timeout_op) == [("RUNNING",)]
                events = candidate_history(storage, timeout_run)
                activity_timeout, = [event.activity_task_timed_out_event_attributes for event in events
                                     if event.HasField("activity_task_timed_out_event_attributes")]
                workflow_failure, = [event.workflow_execution_failed_event_attributes.failure for event in events
                                     if event.HasField("workflow_execution_failed_event_attributes")]
                assert activity_timeout.started_event_id > 0
                assert activity_timeout.failure.timeout_failure_info.timeout_type == TimeoutType.TIMEOUT_TYPE_START_TO_CLOSE
                assert workflow_failure.cause.timeout_failure_info.timeout_type == TimeoutType.TIMEOUT_TYPE_START_TO_CLOSE
                assert not workflow_failure.stack_trace and not workflow_failure.cause.stack_trace
                failure_info = workflow_failure.activity_failure_info
                assert (failure_info.scheduled_event_id, failure_info.started_event_id) == (
                    activity_timeout.scheduled_event_id, activity_timeout.started_event_id,
                )
                wire = History(events=events).SerializeToString()
                assert timeout_message.encode() not in wire and timeout_sentinel.encode() not in wire
                await Replayer(workflows=[ManagerIntakeWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(timeout_op), events))
            if networked and not (lose_start_response or replay_exhausted_start or manager_timeout):
                await assert_assigned_delivery_processes(
                    w, epic, storage, client_dir, f"{frontend_host}:{native_port}", platform_host, ca, cert, server_key,
                )
        finally:
            if process is not None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, 5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait)
            await control.aclose()
            server.should_exit = True
            await asyncio.wait_for(serve, timeout=5)

    assert w.rows("SELECT goal FROM work.manager_proposal_versions") == [("Native fixture draft",)]
    assert len(gateway.transport.calls) == 1
    assert w.count("platform.task_issuance_receipts", "operation_id=%s", oid) >= 2
    assert w.count("agents.worker_runs") == 0
    if candidate:
        with storage.connect("temporal", dbname="temporal_db") as history_db:
            assert history_db.execute("SELECT count(*) FROM history_node").fetchone()[0] > 0
    if store == "postgres":
        with storage.connect(dbname="temporal_probe_history") as history_db:
            assert history_db.execute("SELECT count(*) FROM history_node").fetchone()[0] > 0
        if archive := os.environ.get("G02_NATIVE_POSTGRES_EXPORT_DIR"):
            target = Path(archive).resolve(strict=True)
            assert target.is_dir() and target.stat().st_mode & 0o077 == 0
            for name in ("temporal_probe_history", "temporal_probe_visibility"):
                code, dump = storage.container.exec(["pg_dump", "-U", "postgres", "--no-owner", "--no-privileges", name])
                assert code == 0
                with (target / f"{name}.sql").open("xb") as output:
                    output.write(dump)
            with (target / "run.json").open("x") as manifest:
                json.dump({"workflow_id": workflow_id_for(oid), "run_id": str(run_id),
                           "history_sha256": hashlib.sha256(wire).hexdigest()}, manifest)


@pytest.mark.skipif(os.environ.get("G02_PROTECTED_ENTRYPOINTS") != "1", reason="requires the protected Compose services")
async def test_standalone_compose_protected_entrypoints(iam_world, tmp_path):
    from check import client

    w = World(iam_world, tmp_path, manager_dispatch_namespace="ai-res")
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Protected Compose", "ACTIVE"))
    message = "Private Compose intake canary"
    async with await w.client("analyst") as analyst:
        intake = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": message}, key())
        assert intake.status_code == 202, intake.json()
    oid = UUID(intake.json()["id"])

    async def delivered(operation, destination=START_DESTINATION):
        async with asyncio.timeout(20):
            while True:
                results = w.rows("""
                    SELECT status FROM audit.outbox_events
                    WHERE aggregate_id=%s AND destination=%s
                """, operation, destination)
                if results == [("PUBLISHED",)]:
                    break
                assert results and results != [("QUARANTINED",)], results
                await asyncio.sleep(0.1)
        binding, = w.rows("SELECT id, workflow_run_id FROM platform.operation_execution_assignments WHERE operation_id=%s", operation)
        assert binding[1] is not None
        return binding

    assignment, run_id = await delivered(oid)
    clients = Path("/clients")
    options = {"host": "temporal-workflow", "domain": "temporal-workflow", "namespace": "ai-res"}
    reconciler = await client(clients, 7233, "reconciliation-observer", lazy=False, **options)
    observation = TemporalExecutionObserver(reconciler, deadline=timedelta(seconds=2))
    bound = BoundExecutionObservationRequest(assignment, oid, MANAGER_INTAKE_WORKFLOW, run_id, "ai-res")
    assert (await observation.observe(bound)).state is ExecutionState.RUNNING
    schedule = BoundStartSchedule(
        scopes=(ReconciliationScope(organization_id=org, project_id=w.p1),), admitted_operation_types=("MANAGER_MESSAGE", "PLAN_EXECUTION"),
        page_size=1, interval_seconds=0.1, page_timeout_seconds=4, rpc_timeout_seconds=2, include_post_ack=True,
        server_name="temporal-workflow", ca_file=clients / "ca.pem", certificate_file=clients / "reconciliation-observer.pem",
        private_key_file=clients / "reconciliation-observer.key",
    )
    schedule_file = tmp_path / "bound-reconciliation.json"
    schedule_file.write_text(schedule.model_dump_json())
    settings = w.settings.model_copy(update={
        "reconciliation_config_file": schedule_file, "temporal_address": "temporal-workflow:7233", "temporal_namespace": "ai-res",
    })
    exporter = InMemorySpanExporter()
    application = create_app(settings, identity=w.services, tracer_provider=build_tracer_provider(exporter))
    async with application.router.lifespan_context(application), asyncio.timeout(8):
        while not any(event.name == "operation.reconciliation.observation" and event.attributes.get("outcome") == "RUNNING"
                      for span in exporter.get_finished_spans() if span.name == "operation.reconciliation.page" for event in span.events):
            await asyncio.sleep(0.05)

    manager_settings = w.settings.model_copy(update={
        "temporal_address": "temporal-workflow:7233", "temporal_namespace": "ai-res", "platform_api_url": "https://platform-api:8443",
        "platform_request_max_bytes": 4096, "platform_credential_max_bytes": 2048, "platform_api_timeout_seconds": 2,
        "service_token_max_ttl_seconds": 30,
    })
    manager_tls = TLSConfig(
        server_root_ca_cert=(clients / "ca.pem").read_bytes(), domain="temporal-workflow",
        client_cert=(clients / "manager.pem").read_bytes(), client_private_key=(clients / "manager.key").read_bytes(),
    )
    manager_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode((clients / "manager-signing-key").read_bytes()))
    model = profile()
    gateway = Rig(model).gw
    gateway.transport.script.append(TransportResult(
        output='{"goal":"Protected Compose draft","scope":null,"primary_question":null}', finish_reason=FinishReason.STOP,
        usage=Usage(3, 7), provider_request_ref="fixture",
    ))

    async def model_context(ref, raw_message):
        assert raw_message == message
        return ManagerReasoningInput(ref.operation.operation_id, model.id, "run-1", "INTERNAL", LLMLimits(100, 10), raw_message)

    @asynccontextmanager
    async def running_manager(*, input_builder=model_context):
        async with compose_assigned_manager(
            manager_settings, temporal_tls=manager_tls, platform_ca_file=clients / "platform-ca.pem", credential_ttl=timedelta(seconds=20),
            signing_key=manager_key, build_input=input_builder, gateway=gateway,
        ) as worker, worker:
            yield

    async def completed(operation, run, *, cancelled=False):
        async with asyncio.timeout(20):
            while True:
                events = candidate_history(iam_world.pg, run)
                if any(event.HasField("workflow_execution_completed_event_attributes") for event in events):
                    break
                await asyncio.sleep(0.1)
        expected = "CANCELLED" if cancelled else "SUCCEEDED"
        assert w.rows("SELECT status FROM operations.operations WHERE id=%s", operation) == [(expected,)]
        return events

    approval_file = tmp_path / "plan-approval.json"
    approval_file.write_text(PlanApprovalSchedule(
        scopes=schedule.scopes, interval_seconds=0.1, page_timeout_seconds=4, page_size=1,
    ).model_dump_json())
    approval_app = create_app(w.settings.model_copy(update={"plan_approval_config_file": approval_file}),
                              identity=w.services, plan_dispatch_namespace="ai-res")

    async def start_approved_plan(expected_version, title):
        item = str(uuid4())
        async with await w.client("analyst") as analyst:
            draft = await send(analyst, "post", f"/epics/{epic}/plans", {
                "expectedVersion": expected_version, "goal": title, "entries": [item],
                "items": [{"id": item, "title": title, "taskType": "ANALYSIS"}],
            }, key())
            assert draft.status_code == 201, draft.json()
            version = UUID(draft.json()["id"])
            approval = await send(analyst, "post", f"/plan-versions/{version}/decision",
                                  {"decision": "APPROVE", "contentHash": draft.json()["contentHash"], "approvedItemIds": [item]},
                                  {**key(), "If-Match": draft.headers["ETag"]})
            assert approval.status_code == 201, approval.json()
        decision = UUID(approval.json()["decisionId"])
        async with approval_app.router.lifespan_context(approval_app), asyncio.timeout(8):
            while not (prepared := w.rows("SELECT operation_id FROM work.plan_executions WHERE decision_id=%s", decision)):
                await asyncio.sleep(0.05)
        (operation,), = prepared
        return operation, UUID(item)

    async with running_manager():
        history = await completed(oid, run_id)
        assert message.encode() not in History(events=history).SerializeToString()
        await Replayer(workflows=[ManagerIntakeWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(oid), history))
        assert w.rows("""
            SELECT p.goal,c.workflow_run_id FROM work.manager_proposal_versions p
            JOIN platform.manager_epic_context_versions c ON c.id=p.context_version_id WHERE c.operation_id=%s
        """, oid) == [("Protected Compose draft", run_id)]
        assert w.count("platform.task_issuance_receipts", "operation_id=%s", oid) >= 2

        plan, item = await start_approved_plan(0, "Protected Plan")
        _, plan_run = await delivered(plan)
        async with asyncio.timeout(20):
            while w.rows("SELECT status FROM operations.operations WHERE id=%s", plan) != [("WAITING_FOR_DEPENDENCY",)]:
                await asyncio.sleep(0.1)
        tasks = w.rows("SELECT item_id, task_id FROM work.plan_item_tasks WHERE operation_id=%s", plan)
        assert len(tasks) == 1 and tasks[0][0] == item
        async with await w.client("analyst") as analyst:
            cancelled = await send(analyst, "post", f"/operations/{plan}/cancel", {}, key())
            assert cancelled.status_code == 202, cancelled.json()
        await delivered(plan, CANCEL_DESTINATION)
        plan_history = await completed(plan, plan_run, cancelled=True)
        await Replayer(workflows=[PlanExecutionWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(plan), plan_history))
        assert w.rows("SELECT item_id, task_id FROM work.plan_item_tasks WHERE operation_id=%s", plan) == tasks

    async with await w.client("analyst") as analyst:
        intake = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Cancel before Manager polls"}, key())
        assert intake.status_code == 202, intake.json()
        operation = UUID(intake.json()["id"])
        _, cancel_run = await delivered(operation)
        cancelled = await send(analyst, "post", f"/operations/{operation}/cancel", {}, key())
        assert cancelled.status_code == 202, cancelled.json()
        await delivered(operation, CANCEL_DESTINATION)
    async with running_manager():
        cancel_history = await completed(operation, cancel_run, cancelled=True)
    assert sum(event.HasField("workflow_execution_signaled_event_attributes") for event in cancel_history) == 1

    failed_plan, _ = await start_approved_plan(1, "Plan rejected after ACK")
    plan_assignment, failed_run = await delivered(failed_plan)
    failed_bound = BoundExecutionObservationRequest(plan_assignment, failed_plan, PLAN_EXECUTION_WORKFLOW, failed_run, "ai-res")
    original_call = PlatformControlClient.call
    rejected: list[BoundWorkflowCall] = []

    async def reject_materialization(self, reference, action, **kwargs):
        if action is PlatformAction.MATERIALIZE_PLAN_TASKS and reference.operation.operation_id == str(failed_plan):
            assert w.rows("SELECT status FROM operations.operations WHERE id=%s", failed_plan) == [("RUNNING",)]
            rejected.append(reference)
            raise PlatformPermanentError("Injected failure before Plan task materialization")
        return await original_call(self, reference, action, **kwargs)

    with patch.object(PlatformControlClient, "call", reject_materialization):
        async with running_manager(), asyncio.timeout(15):
            while (await observation.observe(failed_bound)).state is not ExecutionState.FAILED:
                await asyncio.sleep(0.1)
    rejected_call, = rejected
    assert (rejected_call.assignment_id, rejected_call.workflow_run_id) == (str(plan_assignment), str(failed_run))
    assert w.rows("SELECT status FROM operations.operations WHERE id=%s", failed_plan) == [("RUNNING",)]
    recovering_app = create_app(settings, identity=w.services)
    async with recovering_app.router.lifespan_context(recovering_app), asyncio.timeout(10):
        while w.rows("SELECT status FROM operations.operations WHERE id=%s", failed_plan) != [("FAILED",)]:
            await asyncio.sleep(0.05)
    assert w.count("work.plan_item_tasks", "operation_id=%s", failed_plan) == 0
    assert w.count("audit.audit_events", "action=%s AND object_id=%s", "OPERATION_POST_ACK_RECONCILED", failed_plan) == 1
    failed_history = candidate_history(iam_world.pg, failed_run)
    failure, = [event.workflow_execution_failed_event_attributes.failure for event in failed_history
                if event.HasField("workflow_execution_failed_event_attributes")]
    assert failure.cause.application_failure_info.type == "PermanentPlatformError"
    assert b"Injected failure before Plan task materialization" not in History(events=failed_history).SerializeToString()
    await Replayer(workflows=[PlanExecutionWorkflow]).replay_workflow(WorkflowHistory(workflow_id_for(failed_plan), failed_history))

    extra_source = "Unadmitted source text canary"

    async def assert_unadmitted_input(**input_changes):
        async with await w.client("analyst") as analyst:
            intake = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": message}, key())
            assert intake.status_code == 202, intake.json()
        unadmitted = UUID(intake.json()["id"])
        unadmitted_assignment, unadmitted_run = await delivered(unadmitted)
        unadmitted_bound = BoundExecutionObservationRequest(unadmitted_assignment, unadmitted, MANAGER_INTAKE_WORKFLOW, unadmitted_run, "ai-res")
        builder_calls = []

        async def unadmitted_input(reference, raw_message):
            builder_calls.append(reference)
            return replace(await model_context(reference, raw_message), **input_changes)

        async with running_manager(input_builder=unadmitted_input), asyncio.timeout(15):
            while (await observation.observe(unadmitted_bound)).state is not ExecutionState.FAILED:
                await asyncio.sleep(0.1)
        attempted, = builder_calls
        assert (attempted.assignment_id, attempted.workflow_run_id) == (str(unadmitted_assignment), str(unadmitted_run))
        assert w.count("work.manager_proposal_versions p JOIN work.manager_interactions i ON i.id=p.interaction_id", "i.operation_id=%s", unadmitted) == 0
        events = candidate_history(iam_world.pg, unadmitted_run)
        rejected_cause, = [event.workflow_execution_failed_event_attributes.failure.cause for event in events
                           if event.HasField("workflow_execution_failed_event_attributes")]
        assert rejected_cause.application_failure_info.type == "PermanentPlatformError"
        unadmitted_history = History(events=events).SerializeToString()
        assert message.encode() not in unadmitted_history and extra_source.encode() not in unadmitted_history

    await assert_unadmitted_input(approved_source_excerpts=(extra_source,))
    await assert_unadmitted_input(user_message=extra_source)

    assert w.count("platform.platform_auth_events", "action=%s AND reason=%s", "AUTHORIZE_ASSIGNED_DELIVERY", "AUTHORIZED") >= 5
    assert len(gateway.transport.calls) == 1
    async with httpx.AsyncClient(trust_env=False, timeout=2) as http:
        metrics = await http.get("http://temporal-metrics:9090/metrics")
        assert metrics.status_code == 200 and "# TYPE " in metrics.text
        assert str(oid) not in metrics.text and str(run_id) not in metrics.text and message not in metrics.text
        with pytest.raises(httpx.ConnectError):
            await http.get("http://temporal-workflow:9090/metrics")
