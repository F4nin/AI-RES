"""Real Temporal (Testcontainers, no mocks, ADR-003 spirit): the pinned `temporalio/temporal` CLI image runs a dev server. It is NOT the Compose server
(1.29.7 on PostgreSQL): same API, in-memory persistence - recorded as G-105. Replay/idempotency evidence does not depend on the persistence backend."""
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from temporalio.client import Client
from testcontainers.core.container import DockerContainer

IMAGE = "temporalio/temporal@sha256:597a5dbbcc6e7716b326dde4a51622d5ea0879eb0cf06ff8a94381361d0a987d"  # CLI 1.5.1
pytestmark = pytest.mark.temporal


@pytest.fixture(scope="session")
def temporal_address() -> Iterator[str]:
    c = DockerContainer(IMAGE).with_exposed_ports(7233).with_command("server start-dev --ip 0.0.0.0 --headless")
    with c:
        address = f"{c.get_container_host_ip()}:{c.get_exposed_port(7233)}"
        deadline = time.monotonic() + 60
        import socket
        while time.monotonic() < deadline:
            try:
                socket.create_connection((c.get_container_host_ip(), int(c.get_exposed_port(7233))), timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        yield address


@pytest_asyncio.fixture
async def client(temporal_address: str) -> AsyncIterator[Client]:
    last: Exception | None = None
    for _ in range(40):
        try:
            yield await Client.connect(temporal_address)
            return
        except Exception as exc:  # noqa: BLE001 - the server needs a moment after the port opens
            last = exc
            time.sleep(0.5)
    raise RuntimeError("temporal did not become ready") from last
