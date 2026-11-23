"""Run the native authorizer on loopback with throw-away certificates and Temporal storage."""
import argparse
import asyncio
import datetime as dt
import errno
import hashlib
import os
import socket
import ssl
import subprocess
from contextlib import nullcontext
from pathlib import Path
from secrets import randbelow
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

import psycopg
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from google.protobuf.duration_pb2 import Duration
from temporalio.api.command.v1 import Command, CompleteWorkflowExecutionCommandAttributes
from temporalio.api.common.v1 import WorkflowType
from temporalio.api.enums.v1 import CommandType, TaskQueueKind
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    GetSystemInfoRequest,
    PollWorkflowTaskQueueRequest,
    RegisterNamespaceRequest,
    RespondWorkflowTaskCompletedRequest,
    StartWorkflowExecutionRequest,
)
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode, TLSConfig


def ports(count: int, *, postgres: bool = False) -> list[int]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for sock in sockets:
            if not postgres:
                sock.bind(("127.0.0.1", 0))
                continue
            # PostgreSQL Temporal v1.29.7 stores the advertised RPC ports as signed SMALLINT.
            for _ in range(100):
                try:
                    sock.bind(("127.0.0.1", 20000 + randbelow(12768)))
                    break
                except OSError as error:
                    if error.errno != errno.EADDRINUSE:
                        raise
            else:
                raise RuntimeError("could not reserve an available PostgreSQL probe RPC port")
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def certs(root: Path, *, runtime: bool = False) -> None:
    now = dt.datetime.now(dt.UTC)
    ca_key = generate_private_key(SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Isolated Temporal test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=2))
          .not_valid_after(now + dt.timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                      key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=None, decipher_only=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, SHA256()))
    (root / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    roles = ("server", "operator", "manager", "worker", "dispatcher", "reconciliation-observer", "backend-cancellation", "unregistered")
    if runtime:
        roles += ("operator-unlisted", "fixture-operator")
    for role in roles:
        key = generate_private_key(SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, role)])
        if role == "server":
            names = [x509.DNSName("temporal-workflow" if runtime else "temporal-auth-poc")]
        elif runtime and role != "fixture-operator":
            names = [x509.UniformResourceIdentifier("spiffe://ai-res/temporal/" + role.removesuffix("-unlisted"))]
        else:
            names = [x509.UniformResourceIdentifier("spiffe://temporal-auth-poc/" + role.removeprefix("fixture-"))]
        usage = ExtendedKeyUsageOID.SERVER_AUTH if role == "server" else ExtendedKeyUsageOID.CLIENT_AUTH
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=2))
                .not_valid_after(now + dt.timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .add_extension(x509.SubjectAlternativeName(names), critical=False)
                .add_extension(x509.ExtendedKeyUsage([usage]), critical=True).sign(ca_key, SHA256()))
        (root / f"{role}.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root / f"{role}.key").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))


def configure(root: Path, *, postgres: bool = False, frontend_ip: str = "127.0.0.1") -> int:
    network_ports = iter(ports(8, postgres=postgres))
    services = {name: {"rpc": {"grpcPort": next(network_ports), "membershipPort": next(network_ports),
                              "bindOnIP": frontend_ip if name == "frontend" else "127.0.0.1", "httpPort": 0}}
                for name in ("frontend", "history", "matching", "worker")}
    grpc_port = services["frontend"]["rpc"]["grpcPort"]

    def sqlite_store(name: str) -> dict:
        return {"sql": {"pluginName": "sqlite", "databaseName": name, "connectAddr": "localhost",
                        "connectProtocol": "tcp", "connectAttributes": {"cache": "private", "setup": True},
                        "maxConns": 1, "maxIdleConns": 1}}

    configuration = {
        "log": {"stdout": True, "level": "info"},
        "global": {
            "membership": {"broadcastAddress": "127.0.0.1", "maxJoinDuration": "10s"},
            "tls": {
                "frontend": {"server": {"certFile": str(root / "server.pem"), "keyFile": str(root / "server.key"),
                                        "requireClientAuth": True, "clientCaFiles": [str(root / "ca.pem")]}},
                "systemWorker": {"certFile": str(root / "operator.pem"), "keyFile": str(root / "operator.key"),
                                 "client": {"serverName": "temporal-auth-poc", "rootCaFiles": [str(root / "ca.pem")]}},
            },
        },
        "services": services,
        "persistence": {"defaultStore": "default", "visibilityStore": "visibility", "numHistoryShards": 1,
                        "datastores": {"default": sqlite_store("default"), "visibility": sqlite_store("visibility")}},
        "clusterMetadata": {"enableGlobalNamespace": False, "failoverVersionIncrement": 10,
                            "masterClusterName": "active", "currentClusterName": "active",
                            "clusterInformation": {"active": {"enabled": True, "initialFailoverVersion": 1,
                                                             "rpcName": "frontend", "rpcAddress": f"{frontend_ip}:{grpc_port}"}}},
        "dcRedirectionPolicy": {"policy": "noop"},
    }
    (root / "poc.yaml").write_text(yaml.safe_dump(configuration))
    return grpc_port


async def client(
    root: Path, port: int, identity: str | None, *, lazy: bool = True, rpc_identity: str | None = None, host: str = "127.0.0.1",
    domain: str = "temporal-auth-poc", namespace: str = "auth-poc",
) -> Client:
    tls = TLSConfig(
        server_root_ca_cert=(root / "ca.pem").read_bytes(), domain=domain,
        client_cert=(root / f"{identity}.pem").read_bytes() if identity else None,
        client_private_key=(root / f"{identity}.key").read_bytes() if identity else None,
    )
    return await Client.connect(f"{host}:{port}", namespace=namespace, tls=tls, lazy=lazy, identity=rpc_identity)


def check_frontend_certificate_required(root: Path, host: str, port: int, *, domain: str = "temporal-auth-poc") -> None:
    context = ssl.create_default_context(cafile=root / "ca.pem")
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["h2"])

    def handshake() -> None:
        with socket.create_connection((host, port), timeout=2) as raw, context.wrap_socket(raw, server_hostname=domain):
            pass

    try:
        handshake()
    except ssl.SSLError as error:
        if error.reason != "SSLV3_ALERT_HANDSHAKE_FAILURE":
            raise
    else:
        raise AssertionError("Temporal frontend accepted a connection without a client certificate")
    context.load_cert_chain(root / "operator.pem", root / "operator.key")
    handshake()


async def check(root: Path, port: int, process: subprocess.Popen[bytes] | None, *, assigned: bool = False, host: str = "127.0.0.1") -> None:
    operator = await client(root, port, "operator", host=host)
    last_error = None
    for _ in range(30):
        if process is not None and process.poll() is not None:
            raise RuntimeError("native server exited before accepting requests")
        try:
            await operator.workflow_service.get_system_info(GetSystemInfoRequest(), timeout=dt.timedelta(milliseconds=500))
            break
        except (RPCError, RuntimeError) as error:
            last_error = error
            await asyncio.sleep(0.25)
    else:
        raise RuntimeError("native server did not become ready") from last_error

    await operator.workflow_service.register_namespace(
        RegisterNamespaceRequest(namespace="auth-poc", workflow_execution_retention_period=Duration(seconds=86400)),
        timeout=dt.timedelta(seconds=4),
    )
    request = DescribeNamespaceRequest(namespace="auth-poc")
    result = await operator.workflow_service.describe_namespace(request, timeout=dt.timedelta(seconds=4))
    if result.namespace_info.name != "auth-poc":
        raise AssertionError("unexpected namespace response")
    print("PASS verified operator SAN and native namespace RPC")
    await asyncio.to_thread(check_frontend_certificate_required, root, host, port)
    denied_identities = ("worker", "unregistered") if assigned else ("manager", "worker", "unregistered")
    for identity in denied_identities:
        other = await client(root, port, identity, host=host)
        try:
            await other.workflow_service.describe_namespace(request, timeout=dt.timedelta(seconds=2))
        except RuntimeError as error:
            if identity == "unregistered" and "PermissionDenied" in str(error):
                continue
            raise RuntimeError(f"unexpected Temporal transport error for fixture identity {identity}") from error
        except RPCError as error:
            if error.status is not RPCStatusCode.PERMISSION_DENIED:
                raise AssertionError((identity, error.status)) from error
        else:
            raise AssertionError("protected RPC admitted an unauthorized identity")
    print("PASS native namespace ACL, unlisted SAN rejection, certificate required")


async def check_workflow(root: Path, port: int, available: Event, dsn: str) -> None:
    manager = await client(root, port, "manager")
    worker = await client(root, port, "worker")
    dispatcher = await client(root, port, "dispatcher")
    queue = TaskQueue(name="auth-poc-manager", kind=TaskQueueKind.TASK_QUEUE_KIND_NORMAL)
    poll = PollWorkflowTaskQueueRequest(namespace="auth-poc", task_queue=queue)
    for wrong_subject, wrong_queue in ((worker, queue), (manager, TaskQueue(name="auth-poc-worker"))):
        try:
            await wrong_subject.workflow_service.poll_workflow_task_queue(
                PollWorkflowTaskQueueRequest(namespace="auth-poc", task_queue=wrong_queue), timeout=dt.timedelta(seconds=3),
            )
        except RPCError as error:
            if error.status is not RPCStatusCode.PERMISSION_DENIED:
                raise
        else:
            raise AssertionError("cross-role or cross-queue polling was allowed")

    await dispatcher.workflow_service.start_workflow_execution(
        StartWorkflowExecutionRequest(namespace="auth-poc", workflow_id="auth-poc-fixture",
                                      workflow_type=WorkflowType(name="AuthPocFixture"), task_queue=queue,
                                      request_id=str(uuid4()), workflow_task_timeout=Duration(seconds=20)),
        retry=True, timeout=dt.timedelta(seconds=8),
    )
    task = await manager.workflow_service.poll_workflow_task_queue(poll, timeout=dt.timedelta(seconds=12))
    if not task.task_token:
        raise AssertionError("no synthetic Workflow Task issued")
    with psycopg.connect(dsn) as connection:
        receipt = connection.execute("SELECT queue, kind FROM receipt WHERE digest=%s", [hashlib.sha256(task.task_token).digest()]).fetchone()
    if receipt != ("auth-poc-manager", "workflow"):
        raise AssertionError("poll returned before writing a durable receipt")
    completed = RespondWorkflowTaskCompletedRequest(
        namespace="auth-poc", task_token=task.task_token, commands=[Command(
            command_type=CommandType.COMMAND_TYPE_COMPLETE_WORKFLOW_EXECUTION,
            complete_workflow_execution_command_attributes=CompleteWorkflowExecutionCommandAttributes(),
        )],
    )
    available.clear()
    try:
        await manager.workflow_service.respond_workflow_task_completed(completed, timeout=dt.timedelta(seconds=3))
    except RPCError as error:
        if error.status is not RPCStatusCode.PERMISSION_DENIED:
            raise
    else:
        raise AssertionError("native completion proceeded without a receipt check")
    finally:
        available.set()
    await manager.workflow_service.respond_workflow_task_completed(completed, timeout=dt.timedelta(seconds=5))
    print("PASS queue ACL, native register-before-deliver, PostgreSQL receipt, failure on receipt outage and bounded completion")


async def verify(root: Path, port: int, process: subprocess.Popen[bytes], available: Event, dsn: str) -> None:
    await check(root, port, process)
    await check_workflow(root, port, available, dsn)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--transport-only", action="store_true", help="Run the loopback mTLS and namespace checks without PostgreSQL")
    args = parser.parse_args()
    os.umask(0o077)
    with TemporaryDirectory(prefix="temporal-auth-poc-") as directory:
        root = Path(directory)
        certs(root)
        port = configure(root)
        output = root / "server.log"
        if args.transport_only:
            # The namespace checks never contact the fixture receipt service.
            (root / "receipt-address").write_text("127.0.0.1:9")
            (root / "receipt-key").write_bytes(bytes(64))
            receipts = nullcontext(None)
        else:
            from receipt_fixture import receipt_fixture

            receipts = receipt_fixture(root)
        with receipts as fixture, output.open("wb") as log:
            process = subprocess.Popen(  # noqa: S603
                [args.binary.resolve(), root], cwd=root, stdout=log, stderr=log,
                env={"LOCALHOST_IP": "127.0.0.1"},
            )
            try:
                if fixture is None:
                    asyncio.run(check(root, port, process))
                else:
                    asyncio.run(verify(root, port, process, *fixture))
            except (AssertionError, OSError, RPCError, RuntimeError):
                print(output.read_text()[-9500:])
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if process.returncode not in {0, -15}:
                    print(output.read_text()[-2500:])


if __name__ == "__main__":
    main()
