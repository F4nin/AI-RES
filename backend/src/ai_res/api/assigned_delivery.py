"""Private assigned-delivery listener, separate from public and native authorization APIs."""
import json
from asyncio import timeout

from fastapi import FastAPI, Request, Response
from opentelemetry.sdk.trace import TracerProvider
from pydantic import ValidationError

from ai_res.application.assigned_delivery_control import AssignedDeliveryControl
from ai_res.modules.audit.writer import correlation_uuid
from ai_res.modules.events.delivery import PermanentDeliveryError, TransientDeliveryError
from ai_res.modules.events.delivery_lease import DeliveryLease
from ai_res.modules.iam.platform_credentials import ASSIGNED_DELIVERY_PATH, AssignedDeliveryRequest, PlatformCredentialVerifier
from ai_res.modules.iam.service_tokens import _unique
from ai_res.platform.boundary import ErrorBoundaryMiddleware, read_bounded_body
from ai_res.platform.correlation import CorrelationMiddleware, current_request_id
from ai_res.platform.problems import ErrorCode, ProblemError, install_problem_handlers
from ai_res.platform.telemetry import TelemetryMiddleware


def create_assigned_delivery_app(
    control: AssignedDeliveryControl, verifier: PlatformCredentialVerifier, *, max_body_bytes: int, timeout_seconds: float,
    tracer_provider: TracerProvider | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    install_problem_handlers(app)
    if tracer_provider is not None:
        app.add_middleware(TelemetryMiddleware, tracer=tracer_provider.get_tracer("ai_res.assigned_delivery"))

    @app.post(ASSIGNED_DELIVERY_PATH, status_code=204)
    async def deliver(request: Request) -> Response:
        authorization = request.headers.getlist("authorization")
        value = authorization[0] if len(authorization) == 1 else ""
        scheme, _, token = value.partition(" ")
        path, query = request.scope.get("raw_path"), request.scope["query_string"]
        if (scheme.lower() != "bearer" or not isinstance(path, bytes)
                or not verifier.matches_transport(token, AssignedDeliveryRequest(b""), received_method=request.method,
                                                  received_path=path, received_query=query)):
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        try:
            async with timeout(timeout_seconds):
                try:
                    body = await read_bounded_body(request, max_body_bytes)
                except ProblemError:
                    raise ProblemError(ErrorCode.VALIDATION_ERROR, "Request body exceeds its limit.", status=413) from None
                credential = verifier.verify_delivery(token, AssignedDeliveryRequest(body), received_method=request.method,
                                                       received_path=path, received_query=query)
                if credential is None:
                    raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
                try:
                    lease = DeliveryLease.model_validate(json.loads(body.decode("utf-8"), object_pairs_hook=_unique), by_alias=True, by_name=False)
                except (ValueError, ValidationError):
                    raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid delivery lease.") from None
                await control.deliver(credential, lease, correlation_uuid(current_request_id()))
        except (TimeoutError, TransientDeliveryError):
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Delivery unavailable.") from None
        except PermanentDeliveryError:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Delivery rejected.") from None
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(CorrelationMiddleware)
    return app
