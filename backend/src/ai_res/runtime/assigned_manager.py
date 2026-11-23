"""Compose the protected Manager around separately supplied model authority."""
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from temporalio.client import Client
from temporalio.service import TLSConfig
from temporalio.worker import Worker

from ai_res.llm import LLMGatewayPort, UnconfiguredLLMGateway
from ai_res.orchestration.client import temporal_runtime
from ai_res.orchestration.manager_workflows import BoundWorkflowCall
from ai_res.orchestration.platform_port import PlatformPermanentError
from ai_res.platform.config import ConfigError, Settings
from ai_res.runtime.manager_activities import assigned_manager_worker
from ai_res.runtime.manager_reasoning import ManagerReasoning, ManagerReasoningInput
from ai_res.runtime.platform_control_client import ManagerHttpPlatform, PlatformControlClient

# Must match the exact poll/command authorization in the native frontend.
_IDENTITY = "ai-res-manager-runtime"
_BUILD_ID = "ai-res-manager-g02-v1"

type ManagerInputBuilder = Callable[[BoundWorkflowCall, str], Awaitable[ManagerReasoningInput]]


@asynccontextmanager
async def compose_assigned_manager(
    settings: Settings, *, temporal_tls: TLSConfig, platform_ca_file: Path, signing_key: Ed25519PrivateKey, credential_ttl: timedelta,
    build_input: ManagerInputBuilder, gateway: LLMGatewayPort,
) -> AsyncIterator[Worker]:
    """Own the private transport for a Worker configured by a trusted host.

    The host supplies a purpose-bound input builder and an already governed
    gateway. Transport settings and service keys carry no model authority.
    """
    if not callable(build_input) or gateway is None or isinstance(gateway, UnconfiguredLLMGateway):
        raise ConfigError("assigned Manager requires trusted intake and model authority")
    if settings.db_host is not None or settings.db_user is not None or settings.db_password_file is not None:
        raise ConfigError("assigned Manager cannot have database credentials")
    address = settings.temporal_address
    if address is None or not isinstance(signing_key, Ed25519PrivateKey):
        raise ConfigError("assigned Manager requires a Temporal endpoint and Platform signing key")
    if (not isinstance(temporal_tls, TLSConfig) or not temporal_tls.domain or not temporal_tls.server_root_ca_cert
            or not temporal_tls.client_cert or not temporal_tls.client_private_key):
        raise ConfigError("assigned Manager requires direct Temporal mTLS")

    async def current_message_input(reference: BoundWorkflowCall, message: str) -> ManagerReasoningInput:
        inputs = await build_input(reference, message)
        if (inputs.user_message != message or inputs.approved_source_excerpts or inputs.recent_questions
                or inputs.history_truncated or inputs.epic_context is not None):
            raise PlatformPermanentError("assigned Manager v5 accepts only the admitted current message")
        return inputs

    control = PlatformControlClient.for_manager(settings, ca_file=platform_ca_file, signing_key=signing_key, ttl=credential_ttl)
    try:
        temporal = await Client.connect(address, namespace=settings.temporal_namespace, tls=temporal_tls,
                                        identity=_IDENTITY, runtime=temporal_runtime(settings))
        platform = ManagerHttpPlatform(control, current_message_input, epic_context=True)
        yield assigned_manager_worker(temporal, platform, ManagerReasoning(gateway), build_id=_BUILD_ID)
    finally:
        await control.aclose()
