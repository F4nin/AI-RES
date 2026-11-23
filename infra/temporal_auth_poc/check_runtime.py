"""Exercise the standalone native server in the isolated, PostgreSQL-backed candidate."""

import asyncio
import base64
import datetime as dt
import socket
from argparse import ArgumentParser
from pathlib import Path
from secrets import token_bytes

from cryptography import x509
from cryptography.hazmat.primitives.hashes import SHA256
from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    GetSystemInfoRequest,
    RegisterNamespaceRequest,
)
from temporalio.service import RPCError, RPCStatusCode

if __package__:
    from .check import certs, check_frontend_certificate_required, client
    from .postgres_probe import _internode_certificates
else:
    from check import certs, check_frontend_certificate_required, client
    from postgres_probe import _internode_certificates

FRONTEND = "temporal-workflow"
NAMESPACE = "ai-res"
PORT = 7233
TIMEOUT = dt.timedelta(seconds=3)


def prepare(root: Path) -> dict[str, bytes]:
    clients = root / "clients"
    clients.mkdir()
    certs(clients, runtime=True)
    registry = root / "active-certs"
    registry.mkdir()
    for role in ("operator", "worker"):
        cert = x509.load_pem_x509_certificate((clients / f"{role}.pem").read_bytes())
        (registry / f"{role}.sha256").write_text(cert.fingerprint(SHA256()).hex() + "\n")
    internode = root / "internode"
    internode.mkdir()
    _internode_certificates(internode, server_name="temporal-internode")
    material = {
        "temporal_frontend_cert": clients / "server.pem",
        "temporal_frontend_key": clients / "server.key",
        "temporal_frontend_ca": clients / "ca.pem",
        "temporal_internode_cert": internode / "internode.pem",
        "temporal_internode_key": internode / "internode.key",
        "temporal_internode_ca": internode / "internode-ca.pem",
        # No auth-control endpoint is configured in this transport smoke check.
        "temporal_platform_ca": root / "postgres_tls_ca_cert",
    }
    secrets = {name: file.read_bytes() for name, file in material.items()}
    material["temporal_frontend_key"].unlink()
    secrets["temporal_auth_control_signing_key"] = base64.b64encode(token_bytes(32)) + b"\n"
    return secrets


async def assert_denied(rpc, request) -> None:
    try:
        await rpc(request, timeout=TIMEOUT)
    except RPCError as error:
        if error.status != RPCStatusCode.PERMISSION_DENIED:
            raise
    except RuntimeError as error:
        # On a first call the SDK can reject during its initial GetSystemInfo.
        if "PermissionDenied" not in str(error):
            raise
    else:
        raise AssertionError("native RPC accepted an inactive identity or unauthorized request")


async def check(*, existing_namespace: bool) -> None:
    root = Path("/clients")
    args = {"host": FRONTEND, "domain": FRONTEND, "namespace": NAMESPACE}
    operator = await client(root, PORT, "operator", **args)
    for _ in range(30):
        try:
            await operator.workflow_service.get_system_info(GetSystemInfoRequest(), timeout=TIMEOUT)
            break
        except (RuntimeError, RPCError):
            await asyncio.sleep(0.25)
    else:
        raise RuntimeError("native runtime did not become ready")

    service = operator.workflow_service
    if not existing_namespace:
        await service.register_namespace(
            RegisterNamespaceRequest(namespace=NAMESPACE, workflow_execution_retention_period=Duration(seconds=86400)),
            timeout=TIMEOUT,
        )
    request = DescribeNamespaceRequest(namespace=NAMESPACE)
    result = await service.describe_namespace(request, timeout=TIMEOUT)
    assert result.namespace_info.name == NAMESPACE
    if existing_namespace:
        assert result.namespace_info.id == Path("/active-certs/namespace-id").read_text()
        print("PASS the same namespace survives native Temporal restart against the same PostgreSQL stores")
        return
    (Path("/active-certs/namespace-id")).write_text(result.namespace_info.id)
    await assert_denied(service.describe_namespace, DescribeNamespaceRequest(namespace="auth-poc"))
    print("PASS native runtime and operator namespace RPCs with the provisioned Temporal PostgreSQL stores")

    await asyncio.to_thread(check_frontend_certificate_required, root, FRONTEND, PORT, domain=FRONTEND)
    for role in ("operator-unlisted", "fixture-operator", "worker"):
        other = await client(root, PORT, role, **args)
        await assert_denied(other.workflow_service.describe_namespace, request)
    print("PASS frontend requires a client certificate and rejects inactive leaves, fixture SAN and Worker namespace access")

    for host, port in (("temporal-data", PORT), ("temporal-platform", PORT), (FRONTEND, 7234), (FRONTEND, 7235)):
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        try:
            with socket.create_connection((host, port), timeout=1):
                raise AssertionError(f"unexpected Temporal listener at {host}:{port}")
        except ConnectionRefusedError:
            pass
    print("PASS frontend isolated to workflow network and internode listeners inaccessible from peers")

    pin = Path("/active-certs/operator.sha256")
    published = pin.read_bytes()
    pin.unlink()
    try:
        await assert_denied(service.describe_namespace, request)
    finally:
        pin.write_bytes(published)
    print("PASS leaf revocation applies to an already established connection")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--existing-namespace", action="store_true")
    asyncio.run(check(existing_namespace=parser.parse_args().existing_namespace))
