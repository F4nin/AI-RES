"""`python -m ai_res.cli.dispatcher` - the Outbox dispatcher process under the `ai_res_outbox_dispatcher` identity (closes G-98 for the start route).

Claims only the configured Start/Cancel routes. The ordinary dispatcher uses its internal Temporal client.
Protected delivery sends an exact signed lease to Backend over private HTTPS. Exit: 0 after a graceful stop."""
import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import timedelta

from ai_res.cli.assigned_delivery_client import AssignedDeliveryClient
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.dispatcher import Dispatcher, DispatcherConfig, InternalFanoutPublisher, Publisher
from ai_res.modules.events.temporal_start import TemporalCancelPublisher, TemporalStartPublisher
from ai_res.modules.iam.platform_credentials import AssignedDeliveryCredentialIssuer, PlatformCredentialLimits
from ai_res.modules.iam.service_tokens import load_private_key
from ai_res.orchestration.client import OperationCanceller, OperationStarter, connect
from ai_res.orchestration.contracts import CANCEL_DESTINATION, START_DESTINATION
from ai_res.platform.config import ConfigError, Settings, load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.redaction import configure_logging

log = logging.getLogger("ai_res.dispatcher")


@asynccontextmanager
async def delivery_publisher(settings: Settings, owner: str) -> AsyncIterator[Publisher]:
    url, ca = settings.assigned_delivery_url, settings.assigned_delivery_ca_file
    if url is None:
        if ca is not None:
            raise ConfigError("assigned delivery requires a private Backend URL")
        client = await connect(settings)
        starter, canceller = TemporalStartPublisher(OperationStarter(client)), TemporalCancelPublisher(OperationCanceller(client))
        yield InternalFanoutPublisher({START_DESTINATION: [starter.publish], CANCEL_DESTINATION: [canceller.publish]})
        return
    signing_key = settings.service_signing_key_file
    body, token = settings.platform_request_max_bytes, settings.platform_credential_max_bytes
    if (settings.db_user != "ai_res_outbox_dispatcher" or settings.db_name != "ai_res_db"
            or settings.db_sslmode != "verify-full" or settings.db_sslrootcert_file is None
            or ca is None or signing_key is None or body is None or token is None):
        raise ConfigError("protected Outbox requires its delivery role, verified TLS and signing settings")
    ttl = timedelta(seconds=settings.service_token_max_ttl_seconds)
    limits = PlatformCredentialLimits(ttl, timedelta(0), body, token)
    publisher = AssignedDeliveryClient(url, ca_file=ca, issuer=AssignedDeliveryCredentialIssuer(load_private_key(signing_key), limits),
                                       ttl=ttl, timeout_seconds=settings.platform_api_timeout_seconds, owner=owner)
    try:
        yield publisher
    finally:
        await publisher.aclose()


async def _run(env: Mapping[str, str]) -> None:
    settings = load_settings(env)
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-outbox-dispatcher")  # fail-open
    if settings.asyncapi_contract_file is None:
        raise ConfigError("asyncapi_contract_file is required (the dispatcher validates every event against the contract)")
    contract = EventContract.from_file(settings.asyncapi_contract_file)
    engine = create_runtime_engine(settings, telemetry_name="outbox-dispatcher")
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        owner = f"{socket.gethostname()}-{os.getpid()}"
        async with delivery_publisher(settings, owner) as publisher:
            config = DispatcherConfig(
                owner=owner, destinations=(START_DESTINATION, CANCEL_DESTINATION),
                assigned_namespace=settings.temporal_namespace if settings.assigned_delivery_url is not None else None,
            )
            await Dispatcher(create_session_factory(engine), publisher, contract, config).run_forever(stop)
    finally:
        await engine.dispose()
        telemetry.shutdown()


def main(env: Mapping[str, str] | None = None) -> int:
    try:
        asyncio.run(_run(os.environ if env is None else env))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
