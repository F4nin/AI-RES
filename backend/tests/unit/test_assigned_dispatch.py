"""The Backend composition rejects incorrect protected transport before delivery."""
import base64
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from temporalio.client import Client
from temporalio.service import ConnectConfig, TLSConfig

from ai_res.api.serve_assigned_delivery import _delivery_public_keys
from ai_res.application.assigned_dispatch import AssignedDeliveryBackend
from ai_res.modules.events import delivery
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.orchestration.contracts import START_DESTINATION
from ai_res.platform.config import ConfigError

START_TLS = TLSConfig(server_root_ca_cert=b"fixture CA", domain="temporal.test", client_cert=b"start cert", client_private_key=b"start key")
CANCEL_TLS = replace(START_TLS, client_cert=b"cancel cert", client_private_key=b"cancel key")


def client(config: ConnectConfig, namespace: str) -> Client:
    fixture = Mock(spec=Client)
    fixture.namespace = namespace
    fixture.service_client = SimpleNamespace(config=config)
    return fixture


@pytest.mark.parametrize(("cancel_config", "namespace", "message"), [
    (ConnectConfig("temporal:7233", tls=False), "protected", "direct Temporal mTLS"),
    (ConnectConfig("temporal:7233", tls=replace(CANCEL_TLS, server_root_ca_cert=None)), "protected", "direct Temporal mTLS"),
    (ConnectConfig("other:7233", tls=CANCEL_TLS), "protected", "same protected Temporal namespace"),
    (ConnectConfig("temporal:7233", tls=CANCEL_TLS), "wrong", "same protected Temporal namespace"),
    (ConnectConfig("temporal:7233", tls=replace(CANCEL_TLS, verification_server_name="other.test")), "protected", "same protected Temporal namespace"),
    (ConnectConfig("temporal:7233", tls=START_TLS), "protected", "separate Temporal identities"),
    (ConnectConfig("temporal:7233", tls=CANCEL_TLS, api_key="fixture"), "protected", "only mTLS authentication"),
    (ConnectConfig("temporal:7233", tls=CANCEL_TLS, rpc_metadata={"Authorization": "fixture"}), "protected", "only mTLS authentication"),
])
def test_backend_refuses_misconfigured_temporal_transport(cancel_config, namespace, message):
    start = client(ConnectConfig("temporal:7233", tls=START_TLS), "protected")
    with pytest.raises(ConfigError, match=message):
        AssignedDeliveryBackend(Mock(), start_client=start, cancel_client=client(cancel_config, namespace), cancel_deadline=timedelta(seconds=2))


async def test_backend_checks_route_before_database_or_temporal_io():
    start = client(ConnectConfig("temporal:7233", tls=START_TLS), "protected")
    cancel = client(ConnectConfig("temporal:7233", tls=CANCEL_TLS), "protected")
    factory = Mock()
    backend = AssignedDeliveryBackend(factory, start_client=start, cancel_client=cancel, cancel_deadline=timedelta(seconds=2))
    row = OutboxRow(uuid4(), uuid4(), START_DESTINATION, "OPERATION", uuid4(), 1, "operation.accepted", 1, {}, 1)
    for namespace in (None, "wrong"):
        with pytest.raises(delivery.PermanentDeliveryError) as mismatch:
            await backend.publish(replace(row, dispatch_namespace=namespace))
        assert mismatch.value.code == delivery.ENVELOPE_MISMATCH
    factory.assert_not_called()
    start.start_workflow.assert_not_called()


def test_assigned_delivery_listener_rejects_mixed_public_key_registry(tmp_path):
    dispatcher = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    manager = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    registry = tmp_path / "keys"
    registry.write_text("OUTBOX_DISPATCHER " + base64.b64encode(dispatcher).decode() + "\nMANAGER_RUNTIME "
                        + base64.b64encode(manager).decode() + "\n")
    with pytest.raises(ConfigError, match="Outbox-only"):
        _delivery_public_keys(registry)


def test_assigned_delivery_listener_accepts_multiple_keys_for_outbox_rotation(tmp_path):
    keys = [Ed25519PrivateKey.generate().public_key().public_bytes_raw() for _ in range(2)]
    registry = tmp_path / "keys"
    registry.write_text("".join("OUTBOX_DISPATCHER " + base64.b64encode(key).decode() + "\n" for key in keys))
    assert len(_delivery_public_keys(registry)) == 2
