"""Application factory. S02 exposes no domain endpoints (contract-first: endpoints arrive with their OAS operations)."""
import os
from collections.abc import Mapping

from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider

from ai_res.api.identity import IdentityServices, build_identity_services, register_identity
from ai_res.platform.boundary import ErrorBoundaryMiddleware
from ai_res.platform.config import Settings, cursor_key_ring, load_settings
from ai_res.platform.correlation import CorrelationMiddleware
from ai_res.platform.problems import install_problem_handlers
from ai_res.platform.redaction import configure_logging
from ai_res.platform.telemetry import SERVICE_NAME, TelemetryMiddleware, build_tracer_provider


def create_app(settings: Settings, tracer_provider: TracerProvider | None = None, identity: IdentityServices | None = None) -> FastAPI:
    app = FastAPI(title="AI RES", docs_url=None, redoc_url=None, openapi_url=None)  # no schema/UI exposure in S02
    install_problem_handlers(app)
    provider = tracer_provider or build_tracer_provider()
    app.state.settings = settings
    # add_middleware: last added is outermost. Order outer->inner: correlation, telemetry, error boundary.
    if identity is not None:
        register_identity(app, identity)
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(TelemetryMiddleware, tracer=provider.get_tracer(SERVICE_NAME))
    app.add_middleware(CorrelationMiddleware)
    return app


def create_app_from_env(env: Mapping[str, str] | None = None) -> FastAPI:
    """Production entrypoint: validates configuration, loads required secrets (from files) and installs redacting logging for
    ai_res and uvicorn loggers, or refuses to start. Exporting traces (OTLP) is not wired yet: S13 (G-22)."""
    settings = load_settings(os.environ if env is None else env)
    configure_logging(settings.log_level)
    ring = cursor_key_ring(settings)  # raises ConfigError when the cursor key file is missing/short
    app = create_app(settings, identity=build_identity_services(settings))  # missing DB/MFA configuration => the API refuses to start (fail closed)
    app.state.cursor_key_ring = ring
    return app
