"""Ensure the G02 namespace exists using only the scoped operator capability."""

import asyncio
import os
from datetime import timedelta
from pathlib import Path

from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, GetSystemInfoRequest, RegisterNamespaceRequest
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode, TLSConfig


async def ensure() -> None:
    secrets = Path("/run/secrets")
    host = "temporal-workflow"
    namespace = "ai-res"
    tls = TLSConfig(
        server_root_ca_cert=(secrets / "temporal_frontend_ca").read_bytes(), domain=host,
        client_cert=(secrets / "temporal_operator_cert").read_bytes(), client_private_key=(secrets / "temporal_operator_key").read_bytes(),
    )
    client = await Client.connect(f"{host}:7233", namespace=namespace, tls=tls, lazy=True)
    service = client.workflow_service
    timeout = timedelta(seconds=2)
    async with asyncio.timeout(60):
        while True:
            try:
                await service.get_system_info(GetSystemInfoRequest(), timeout=timeout)
                break
            except RPCError as error:
                if error.status not in {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}:
                    raise
            except RuntimeError as error:
                # The SDK's lazy connection raises RuntimeError when it cannot reach the frontend.
                if "Unavailable" not in str(error) and "Connection refused" not in str(error):
                    raise
            await asyncio.sleep(0.5)
    request = DescribeNamespaceRequest(namespace=namespace)
    try:
        await service.describe_namespace(request, timeout=timeout)
    except RPCError as error:
        if error.status is not RPCStatusCode.NOT_FOUND:
            raise
        retention = int(os.environ["G02_NAMESPACE_RETENTION_SECONDS"])
        if retention < 1:
            raise ValueError("namespace retention must be positive") from None
        try:
            await service.register_namespace(RegisterNamespaceRequest(
                namespace=namespace, workflow_execution_retention_period=Duration(seconds=retention),
            ), timeout=timeout)
        except RPCError as register_error:
            if register_error.status is not RPCStatusCode.ALREADY_EXISTS:
                raise
        await service.describe_namespace(request, timeout=timeout)


if __name__ == "__main__":
    asyncio.run(ensure())
