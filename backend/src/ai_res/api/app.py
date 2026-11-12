"""Application factory. S02 exposes no domain endpoints (contract-first: endpoints arrive with their OAS operations)."""
import os
from collections.abc import Mapping

from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider

from ai_res.api.events_api import register_events_api
from ai_res.api.identity import IdentityServices, build_identity_services, register_identity
from ai_res.api.read_api import register_read_api
from ai_res.api.write_api import StorageConfig, register_write_api
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.modules.sources.object_store import ObjectStore
from ai_res.platform.boundary import ErrorBoundaryMiddleware
from ai_res.platform.config import Settings, cursor_key_ring, load_settings
from ai_res.platform.correlation import CorrelationMiddleware
from ai_res.platform.export import install_telemetry
from ai_res.platform.problems import install_problem_handlers
from ai_res.platform.redaction import configure_logging
from ai_res.platform.telemetry import SERVICE_NAME, TelemetryMiddleware, build_tracer_provider


def create_app(settings: Settings, tracer_provider: TracerProvider | None = None, identity: IdentityServices | None = None,
               idempotency: IdempotencyService | None = None, storage: StorageConfig | None = None,
               object_store: ObjectStore | None = None) -> FastAPI:
    app = FastAPI(title="AI RES", docs_url=None, redoc_url=None, openapi_url=None)  # no schema/UI exposure in S02
    install_problem_handlers(app)
    provider = tracer_provider or build_tracer_provider()
    app.state.settings = settings
    # add_middleware: last added is outermost. Order outer->inner: correlation, telemetry, error boundary.
    if identity is not None:
        register_identity(app, identity)
        register_read_api(app, identity)
        register_events_api(app, identity)
        register_write_api(app, identity, idempotency=idempotency, storage=storage, object_store=object_store)
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(TelemetryMiddleware, tracer=provider.get_tracer(SERVICE_NAME))
    app.add_middleware(CorrelationMiddleware)
    return app


def create_app_from_env(env: Mapping[str, str] | None = None) -> FastAPI:
    """Production entrypoint: validates configuration, loads required secrets (from files) and installs redacting logging for
    ai_res and uvicorn loggers, or refuses to start. Telemetry is exported over OTLP when `otlp_endpoint` is set (fail-open, S13)."""
    settings = load_settings(os.environ if env is None else env)
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-api")  # fail-open: an unreachable Collector never stops the API
    ring = cursor_key_ring(settings)  # raises ConfigError when the cursor key file is missing/short
    # missing DB/MFA configuration => the API refuses to start (fail closed)
    app = create_app(settings, tracer_provider=telemetry.tracer_provider, identity=build_identity_services(settings))
    app.state.cursor_key_ring = ring
    return app
