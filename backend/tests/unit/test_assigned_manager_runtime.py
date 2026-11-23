from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from temporalio.service import TLSConfig

from ai_res.llm import UnconfiguredLLMGateway
from ai_res.platform.config import ConfigError, load_settings
from ai_res.runtime.assigned_manager import compose_assigned_manager
from tests.unit.test_llm_gateway import Rig, profile


@pytest.mark.parametrize(("failure", "message"), [
    ("gateway", "requires trusted intake and model authority"),
    ("input", "requires trusted intake and model authority"),
    ("db", "cannot have database credentials"),
    ("limits", "requires a Platform endpoint and request limits"),
    ("key", "requires a Temporal endpoint and Platform signing key"),
    ("mTLS", "requires direct Temporal mTLS"),
    ("expiry", "credential lifetime exceeds the configured limits"),
])
async def test_manager_refuses_invalid_composition_before_connecting(failure, message, tmp_path, monkeypatch):
    settings = load_settings({
        "AI_RES_ENVIRONMENT": "test", "AI_RES_TEMPORAL_ADDRESS": "temporal-workflow:7233",
        "AI_RES_PLATFORM_API_URL": "https://platform-api:8443",
        "AI_RES_PLATFORM_REQUEST_MAX_BYTES": "4096", "AI_RES_PLATFORM_CREDENTIAL_MAX_BYTES": "2048",
        "AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS": "30",
    })
    if failure == "db":
        settings = settings.model_copy(update={"db_password_file": tmp_path / "unread-db-secret"})
    elif failure == "limits":
        settings = settings.model_copy(update={"platform_credential_max_bytes": None})

    tls = TLSConfig(server_root_ca_cert=b"fixture", domain="temporal-workflow", client_cert=b"fixture", client_private_key=b"fixture")
    connect = AsyncMock()
    monkeypatch.setattr("ai_res.runtime.assigned_manager.Client.connect", connect)
    build_input = AsyncMock()
    with pytest.raises(ConfigError, match=message):
        async with compose_assigned_manager(
            settings, temporal_tls=TLSConfig() if failure == "mTLS" else tls, platform_ca_file=tmp_path / "unread-ca",
            credential_ttl=timedelta(seconds=31 if failure == "expiry" else 20),
            signing_key=None if failure == "key" else Ed25519PrivateKey.generate(),
            build_input=None if failure == "input" else build_input,
            gateway=UnconfiguredLLMGateway() if failure == "gateway" else Rig(profile()).gw,
        ):
            pytest.fail("invalid Manager composition yielded a worker")
    connect.assert_not_called()
    build_input.assert_not_called()
