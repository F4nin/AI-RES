"""Private TLS listener for ar2 Operation callbacks. The public app never mounts these routes."""
import os
import ssl
from argparse import ArgumentParser
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI

from ai_res.api.platform_auth_control import register_native_auth_control
from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.application.native_auth_control import NativeAuthControl
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.platform_credentials import PlatformCredentialLimits, PlatformCredentialVerifier
from ai_res.modules.iam.service_tokens import load_public_keys
from ai_res.platform.config import ConfigError, Settings, load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.ports import ServiceName
from ai_res.platform.redaction import configure_logging


def create_listener(settings: Settings, *, require_native_auth: bool = False) -> uvicorn.Config:
    certificate, key = settings.platform_tls_certificate_file, settings.platform_tls_key_file
    body_limit, credential_limit = settings.platform_request_max_bytes, settings.platform_credential_max_bytes
    concurrency = settings.platform_listener_max_connections
    if body_limit is None or credential_limit is None or concurrency is None:
        raise ConfigError("private Platform body, credential and concurrency limits are required")
    if certificate is None or key is None:
        raise ConfigError("private Platform TLS certificate and key are required")
    if settings.db_user != "ai_res_platform_api" or settings.db_name != "ai_res_db":
        raise ConfigError("the private listener requires its dedicated database role")
    if settings.db_sslmode != "verify-full" or settings.db_sslrootcert_file is None:
        raise ConfigError("the private listener requires verified PostgreSQL TLS")
    if settings.service_public_keys_file is None:
        raise ConfigError("the private listener requires the Manager public key registry")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(certificate, key)
    except (ValueError, OSError):
        raise ConfigError("invalid private Platform TLS configuration") from None
    registry = load_public_keys(settings.service_public_keys_file)
    manager_keys = registry.get(ServiceName.MANAGER_RUNTIME, ())
    if not manager_keys:
        raise ConfigError("the private listener requires a Manager public key")
    limits = PlatformCredentialLimits(
        timedelta(seconds=settings.service_token_max_ttl_seconds), timedelta(0),
        body_limit, credential_limit,
    )
    native_keys = registry.get(ServiceName.TEMPORAL_AUTH_CONTROL, ())
    if require_native_auth and (not native_keys or set(registry) != {ServiceName.MANAGER_RUNTIME, ServiceName.TEMPORAL_AUTH_CONTROL}):
        raise ConfigError("protected Platform requires its dedicated Manager and native auth-control registry")
    if set(manager_keys) & set(native_keys):
        raise ConfigError("Manager and native auth-control keys must be distinct")
    verifier = PlatformCredentialVerifier(
        [Ed25519PublicKey.from_public_bytes(raw) for raw in manager_keys], limits,
        auth_control_keys=[Ed25519PublicKey.from_public_bytes(raw) for raw in native_keys],
    )
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-platform-api")
    engine = create_runtime_engine(settings, telemetry_name="platform-api")
    factory = create_session_factory(engine)
    control = PlatformOperationControl(factory, failure_codes=frozenset(settings.platform_operation_failure_codes))
    app = create_platform_v2_app(
        control, verifier, max_body_bytes=limits.max_body_bytes,
        body_timeout_seconds=settings.platform_api_timeout_seconds, tracer_provider=telemetry.tracer_provider,
    )

    if native_keys:
        register_native_auth_control(app, NativeAuthControl(factory, control), control, verifier,
                                     max_bytes=limits.max_body_bytes, timeout_seconds=settings.platform_api_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app.router.lifespan_context = lifespan
    return uvicorn.Config(
        app, host=str(settings.platform_listener_bind_host), port=8443,
        ssl_certfile=str(certificate), ssl_keyfile=str(key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
        limit_concurrency=concurrency,
        http="h11", ws="none", h11_max_incomplete_event_size=credential_limit * 2,
        access_log=False, log_config=None, server_header=False, proxy_headers=False,
    )


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--require-native-auth", action="store_true")
    try:
        uvicorn.Server(create_listener(load_settings(os.environ), require_native_auth=parser.parse_args().require_native_auth)).run()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
