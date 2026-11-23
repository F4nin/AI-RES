"""Application factory. S02 exposes no domain endpoints (contract-first: endpoints arrive with their OAS operations)."""
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider

from ai_res.api.events_api import register_events_api
from ai_res.api.identity import IdentityServices, build_identity_services, register_identity
from ai_res.api.notification_api import register_notification_api
from ai_res.api.read_api import register_read_api
from ai_res.api.write_api import StorageConfig, register_write_api
from ai_res.application.notification_delivery import load_notification_schedule, start_notification_delivery
from ai_res.application.plan_approval_consumer import start_plan_approval_consumer
from ai_res.application.reconcile_scheduler import start_bound_reconciliation
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.modules.sources.object_store import ObjectStore
from ai_res.platform.boundary import ErrorBoundaryMiddleware
from ai_res.platform.config import ConfigError, Settings, cursor_key_ring, load_settings
from ai_res.platform.correlation import CorrelationMiddleware
from ai_res.platform.export import install_telemetry
from ai_res.platform.problems import install_problem_handlers
from ai_res.platform.redaction import configure_logging
from ai_res.platform.telemetry import SERVICE_NAME, TelemetryMiddleware, build_tracer_provider


def create_app(settings: Settings, tracer_provider: TracerProvider | None = None, identity: IdentityServices | None = None,
               idempotency: IdempotencyService | None = None, storage: StorageConfig | None = None,
               object_store: ObjectStore | None = None, *, manager_dispatch_namespace: str | None = None,
               plan_dispatch_namespace: str | None = None) -> FastAPI:
    provider = tracer_provider or build_tracer_provider()
    schedule = load_notification_schedule(settings.notification_schedule_file) if settings.notification_schedule_file is not None else None

    @asynccontextmanager
    async def background_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if identity is None:
            raise ConfigError("Backend background services require persistence")
        if settings.plan_approval_config_file is not None and plan_dispatch_namespace is None:
            raise ConfigError("the plan approval consumer requires separate Plan dispatch admission")
        async with AsyncExitStack() as lifespans:
            if schedule is not None:
                await lifespans.enter_async_context(start_notification_delivery(
                    identity.factory, schedule, provider.get_tracer("ai_res.notification.delivery"),
                ))
            if settings.reconciliation_config_file is not None:
                await lifespans.enter_async_context(start_bound_reconciliation(
                    settings, identity.factory, provider.get_tracer("ai_res.operation.reconciliation"),
                ))
            if settings.plan_approval_config_file is not None and plan_dispatch_namespace is not None:
                await lifespans.enter_async_context(start_plan_approval_consumer(
                    settings.plan_approval_config_file, identity.factory, plan_dispatch_namespace,
                    provider.get_tracer("ai_res.plan.approval"),
                ))
            yield

    app = FastAPI(title="AI RES", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=background_lifespan if settings.reconciliation_config_file or settings.plan_approval_config_file or schedule else None)
    install_problem_handlers(app)
    app.state.settings = settings
    # add_middleware: last added is outermost. Order outer->inner: correlation, telemetry, error boundary.
    if identity is not None:
        register_identity(app, identity)
        if schedule is not None:
            register_notification_api(app, identity, schedule)
        register_read_api(app, identity)
        register_events_api(app, identity)
        register_write_api(app, identity, idempotency=idempotency, storage=storage, object_store=object_store,
                           manager_dispatch_namespace=manager_dispatch_namespace)
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
