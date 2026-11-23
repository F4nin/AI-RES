"""Run the private Backend delivery listener under its own process and DB role."""
import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from ipaddress import ip_address
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI
from temporalio.client import Client
from temporalio.service import TLSConfig

from ai_res.api.assigned_delivery import create_assigned_delivery_app
from ai_res.application.assigned_delivery_control import AssignedDeliveryControl
from ai_res.application.assigned_dispatch import AssignedDeliveryBackend
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.events.contract import EventContract
from ai_res.modules.iam.platform_credentials import PlatformCredentialLimits, PlatformCredentialVerifier
from ai_res.modules.iam.service_tokens import load_public_keys
from ai_res.orchestration.client import temporal_runtime
from ai_res.platform.config import ConfigError, Settings, load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.ports import ServiceName
from ai_res.platform.redaction import configure_logging


def _delivery_public_keys(path: Path) -> tuple[Ed25519PublicKey, ...]:
    registry = load_public_keys(path)
    dispatch_keys = registry.get(ServiceName.OUTBOX_DISPATCHER, ())
    if not dispatch_keys or set(registry) != {ServiceName.OUTBOX_DISPATCHER}:
        raise ConfigError("assigned delivery requires an Outbox-only public key registry")
    return tuple(Ed25519PublicKey.from_public_bytes(raw) for raw in dispatch_keys)


def _temporal_tls(settings: Settings, certificate: Path | None, key: Path | None) -> TLSConfig:
    ca, server = settings.assigned_temporal_ca_file, settings.assigned_temporal_server_name
    if ca is None or server is None or certificate is None or key is None:
        raise ConfigError("assigned delivery requires purpose-specific Temporal mTLS files")
    try:
        root, cert, private = ca.read_bytes(), certificate.read_bytes(), key.read_bytes()
    except OSError:
        raise ConfigError("assigned delivery mTLS files cannot be read") from None
    if not (root and cert and private):
        raise ConfigError("assigned delivery mTLS files cannot be empty")
    return TLSConfig(server_root_ca_cert=root, domain=server, client_cert=cert, client_private_key=private)


def create_listener(settings: Settings) -> uvicorn.Config:
    certificate, key = settings.platform_tls_certificate_file, settings.platform_tls_key_file
    body, credential, concurrency = (
        settings.platform_request_max_bytes, settings.platform_credential_max_bytes, settings.platform_listener_max_connections,
    )
    if certificate is None or key is None or body is None or credential is None or concurrency is None:
        raise ConfigError("assigned delivery requires private TLS and explicit connection/request limits")
    if settings.db_user != "ai_res_api" or settings.db_name != "ai_res_db" or settings.db_sslmode != "verify-full" or settings.db_sslrootcert_file is None:
        raise ConfigError("assigned delivery requires the Backend database role with verified TLS")
    temporal_address = settings.temporal_address
    if settings.assigned_delivery_public_keys_file is None or settings.asyncapi_contract_file is None or temporal_address is None:
        raise ConfigError("assigned delivery requires service keys, the event contract and a Temporal endpoint")
    try:
        host = str(ip_address(settings.assigned_delivery_bind_host))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
    except (ValueError, OSError):
        raise ConfigError("invalid private assigned-delivery listener configuration") from None
    limits = PlatformCredentialLimits(timedelta(seconds=settings.service_token_max_ttl_seconds), timedelta(0), body, credential)
    verifier = PlatformCredentialVerifier([], limits, delivery_keys=_delivery_public_keys(settings.assigned_delivery_public_keys_file))
    start_tls = _temporal_tls(settings, settings.assigned_start_certificate_file, settings.assigned_start_key_file)
    cancel_tls = _temporal_tls(settings, settings.assigned_cancel_certificate_file, settings.assigned_cancel_key_file)
    contract = EventContract.from_file(settings.asyncapi_contract_file)
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-assigned-delivery")
    engine = create_runtime_engine(settings, telemetry_name="assigned-delivery")

    @asynccontextmanager
    async def lifespan(server: FastAPI) -> AsyncIterator[None]:
        try:
            # Native Start accepts a fixed RPC identity and compact input without workflow headers.
            runtime = temporal_runtime(settings)
            start = await Client.connect(temporal_address, namespace=settings.temporal_namespace, tls=start_tls,
                                         identity="ai-res-outbox-dispatcher", runtime=runtime)
            cancel = await Client.connect(temporal_address, namespace=settings.temporal_namespace, tls=cancel_tls, runtime=runtime)
            factory = create_session_factory(engine)
            backend = AssignedDeliveryBackend(factory, start_client=start, cancel_client=cancel,
                                              cancel_deadline=timedelta(seconds=settings.platform_api_timeout_seconds))
            listener = create_assigned_delivery_app(
                AssignedDeliveryControl(factory, backend, contract), verifier, max_body_bytes=body,
                timeout_seconds=settings.platform_api_timeout_seconds, tracer_provider=telemetry.tracer_provider,
            )
            server.mount("/", listener)
            yield
        finally:
            await engine.dispose()
            telemetry.shutdown()

    server = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False, lifespan=lifespan)
    return uvicorn.Config(
        server, host=host, port=settings.assigned_delivery_bind_port,
        ssl_certfile=str(certificate), ssl_keyfile=str(key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
        limit_concurrency=concurrency, http="h11", ws="none", h11_max_incomplete_event_size=credential * 2,
        access_log=False, log_config=None, server_header=False, proxy_headers=False,
    )


def main() -> None:
    try:
        uvicorn.Server(create_listener(load_settings(os.environ))).run()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
