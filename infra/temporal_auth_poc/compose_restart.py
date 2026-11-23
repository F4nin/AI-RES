"""Verify a disposable native Temporal Run before and after a Compose restart."""

import asyncio
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from uuid import UUID

import psycopg
from check import certs, client, configure
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from postgres_probe import DATABASES, probe_internode_tls, write_postgres_configuration
from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.enums.v1 import HistoryEventFilterType, WorkflowExecutionStatus
from temporalio.api.workflowservice.v1 import GetSystemInfoRequest, GetWorkflowExecutionHistoryRequest
from temporalio.service import RPCError, RPCStatusCode

HERE = Path(__file__).resolve().parent


def prepare(root: Path, data: Path) -> None:
    certs(data)
    frontend = configure(root, postgres=True)
    for name in ("server.pem", "server.key"):
        shutil.move(data / name, root / name)
    for name in ("ca.pem", "operator.pem", "operator.key"):
        shutil.copyfile(data / name, root / name)
    history, matching = write_postgres_configuration(root, 5432, (data / "probe-password").read_text())
    for name in ("internode-ca.pem", "internode.pem", "internode.key"):
        shutil.copyfile(root / name, data / name)
    (data / "ports.json").write_text(json.dumps({"frontend": frontend, "history": history, "matching": matching}))
    operation = UUID(json.loads((data / "run.json").read_text())["workflow_id"].removeprefix("operation-"))
    (root / "observe-fixture-operation").write_text(str(operation))
    # History uses the existing fixture operator. Other authority checks still fail closed if called.
    (root / "native-auth-origin").write_text("https://127.0.0.1:9")
    (root / "native-auth-ca").write_bytes((root / "ca.pem").read_bytes())
    (root / "native-auth-seed").write_bytes(Ed25519PrivateKey.generate().private_bytes_raw())
    (root / "receipt-address").write_text("127.0.0.1:9")
    (root / "receipt-key").write_bytes(bytes(64))


async def verify(data: Path) -> str:
    manifest = json.loads((data / "run.json").read_text())
    ports = json.loads((data / "ports.json").read_text())
    port = ports["frontend"]
    operator = await client(data, port, "operator")
    async with asyncio.timeout(25):
        while True:
            try:
                await operator.workflow_service.get_system_info(GetSystemInfoRequest(), timeout=timedelta(seconds=1))
                break
            except (RPCError, RuntimeError):
                await asyncio.sleep(0.25)
    request = GetWorkflowExecutionHistoryRequest(
        namespace="auth-poc", execution=WorkflowExecution(workflow_id=manifest["workflow_id"], run_id=manifest["run_id"]),
        history_event_filter_type=HistoryEventFilterType.HISTORY_EVENT_FILTER_TYPE_ALL_EVENT, skip_archival=True,
    )
    reply = await operator.workflow_service.get_workflow_execution_history(request, timeout=timedelta(seconds=5))
    assert not reply.next_page_token and reply.history.events[-1].HasField("workflow_execution_completed_event_attributes")
    manager = await client(data, port, "manager")
    try:
        await manager.workflow_service.get_workflow_execution_history(request, timeout=timedelta(seconds=5))
    except RPCError as error:
        assert error.status is RPCStatusCode.PERMISSION_DENIED
    else:
        raise AssertionError("Manager could read the fixture operator's history")
    for service in ("history", "matching"):
        internal_port = ports[service]
        probe_internode_tls(data, internal_port, "internode")
        for identity in (None, "manager"):
            try:
                probe_internode_tls(data, internal_port, identity)
            except ssl.SSLError:
                continue
            raise AssertionError(f"{service} admitted an untrusted identity")
    with psycopg.connect(
        host="127.0.0.1", dbname=DATABASES["visibility"], user="temporal_probe",
        password=(data / "probe-password").read_text(), sslmode="disable", connect_timeout=5,
    ) as connection:
        assert connection.execute(
            "SELECT 1 FROM executions_visibility WHERE workflow_id=%s AND run_id=%s AND status=%s",
            (manifest["workflow_id"], manifest["run_id"], WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED),
        ).fetchall() == [(1,)]
    history_sha256 = hashlib.sha256(reply.history.SerializeToString(deterministic=True)).hexdigest()
    assert history_sha256 == manifest["history_sha256"]
    return history_sha256


def verify_compose(base: Path, archive: Path) -> None:
    server, verifier = base / "server", base / "verifier"
    server.mkdir()
    verifier.mkdir()
    shutil.copyfile(archive / "run.json", verifier / "run.json")
    admin_password_file = base / "postgres-password"
    admin_password_file.write_text(token_hex(24))
    probe_password = token_hex(24)
    (verifier / "probe-password").write_text(probe_password)
    # Docker Desktop projects the private binds. Native Linux uses the invoking user's numeric ownership.
    uid, gid = (1000, 1000) if sys.platform == "darwin" or os.getuid() == 0 else (os.getuid(), os.getgid())
    if sys.platform == "linux" and os.getuid() == 0:
        for path in (server, verifier, *verifier.iterdir()):
            os.chown(path, uid, gid)
    passwd = base / "passwd"
    passwd.write_text(f"temporal-probe:x:{uid}:{gid}:Temporal probe:/scratch:/nonexistent\n")
    passwd.chmod(0o644)
    environment = {
        **os.environ,
        "G02_RESTART_SERVER_DIR": str(server),
        "G02_RESTART_VERIFIER_DIR": str(verifier),
        "G02_RESTART_POSTGRES_PASSWORD_FILE": str(admin_password_file),
        "G02_RESTART_UID_MAP": str(passwd),
        "G02_RESTART_UID": str(uid),
        "G02_RESTART_GID": str(gid),
    }
    project = "aires-temporal-restart-" + token_hex(6)
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required for the Compose restart probe")
    command = [docker, "compose", "--env-file", "/dev/null", "-p", project, "-f", str(HERE / "compose.restart.yaml")]

    def compose(*args: str, input_data: bytes | None = None, capture: bool = False) -> bytes:
        return subprocess.run(  # noqa: S603
            [*command, *args], env=environment, input=input_data, stdout=subprocess.PIPE if capture else None,
            check=True, timeout=90,
        ).stdout

    psql = ("exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1")
    try:
        compose("up", "-d", "--wait", "postgres")
        # Generated lowercase hex and fixed fixture identifiers are the only SQL literals assembled here.
        sql = f"CREATE ROLE temporal_probe LOGIN PASSWORD '{probe_password}';\n"
        sql += "".join(f"CREATE DATABASE {name} OWNER temporal_probe;\n" for name in DATABASES.values())
        compose(*psql, "-U", "postgres", "-d", "postgres", input_data=sql.encode())
        for name in DATABASES.values():
            dump = (archive / f"{name}.sql").read_bytes()
            compose(*psql, "-U", "temporal_probe", "-d", name, input_data=dump, capture=True)
        compose("run", "--rm", "-T", "prepare", "prepare")
        compose("up", "-d", "temporal")

        def started(service: str) -> bytes:
            container = compose("ps", "-q", service, capture=True).decode().strip()
            if not container:
                raise RuntimeError(f"Compose service {service} has no running container")
            return subprocess.check_output(  # noqa: S603
                [docker, "inspect", "--format", "{{.State.StartedAt}}", container], timeout=10,
            )

        before = compose("run", "--rm", "-T", "verifier", "verify", capture=True)
        database_start, temporal_start = started("postgres"), started("temporal")
        compose("restart", "-t", "15", "temporal")
        after = compose("run", "--rm", "-T", "verifier", "verify", capture=True)
        assert started("postgres") == database_start and started("temporal") != temporal_start
        assert before.strip() == after.strip() and len(after.strip()) == 64
    finally:
        compose("down")
    print(f"PASS identical exact Run history at source, after restore and after Temporal restart, SHA-256 {after.decode().strip()}")


def main() -> None:
    os.umask(0o077)
    if sys.argv[1:] == ["--inside", "prepare"]:
        prepare(Path("/probe"), Path("/verifier"))
    elif sys.argv[1:] == ["--inside", "verify"]:
        print(asyncio.run(verify(Path("/verifier"))))
    elif len(sys.argv) == 1:
        repo = HERE.parents[1]
        with TemporaryDirectory(prefix="aires-temporal-restart-") as scratch:
            base = Path(scratch).resolve()
            archive = base / "archive"
            archive.mkdir()
            subprocess.run(  # noqa: S603
                [sys.executable, "-B", "-m", "pytest", "-c", "backend/pyproject.toml", "-q", "--tb=short",
                 "backend/tests/integration/postgres/test_native_assigned_workflow.py::test_native_manager_workflow_with_platform_receipts[postgres]"],
                cwd=repo, check=True, timeout=180,
                env={**os.environ, "G02_NATIVE_POSTGRES_EXPORT_DIR": str(archive), "PYTHONPATH": str(HERE)},
            )
            verify_compose(base, archive)
    else:
        raise SystemExit("Run compose_restart.py with the ADR-154 PostgreSQL probe inputs configured")


if __name__ == "__main__":
    main()
