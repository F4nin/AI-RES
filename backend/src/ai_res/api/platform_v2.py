"""Private ar2 operation controller. Assembled on its own listener during ADR-129 cutover."""
import json
from asyncio import timeout
from math import isfinite
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request, Response
from opentelemetry.sdk.trace import TracerProvider
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from ai_res.application.platform_control import PlatformAuthFailure, PlatformOperationCommand, PlatformOperationControl
from ai_res.application.platform_manager import AssignedManagerInput
from ai_res.modules.audit.writer import correlation_uuid
from ai_res.modules.epics.manager_proposals import ProposalContent
from ai_res.modules.iam.platform_credentials import PlatformAction, PlatformCredentialVerifier, PlatformRequest
from ai_res.modules.iam.service_tokens import _unique
from ai_res.platform.boundary import ErrorBoundaryMiddleware, read_bounded_body
from ai_res.platform.correlation import CorrelationMiddleware, current_request_id
from ai_res.platform.problems import ErrorCode, ProblemError, install_problem_handlers
from ai_res.platform.telemetry import TelemetryMiddleware


class _ExecutionBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")
    workflow_id: str = Field(min_length=1)
    workflow_run_id: UUID


class _FailureBody(_ExecutionBody):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")


class _DraftBody(_ExecutionBody):
    goal: str | None = Field(max_length=20_000)
    scope: str | None = Field(max_length=20_000)
    primary_question: str | None = Field(max_length=20_000)

    @field_validator("goal", "scope", "primary_question")
    @classmethod
    def reject_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("invalid text")
        return value


class _ContextDraftBody(_DraftBody):
    context_version_id: UUID


_BODY_MODELS: dict[PlatformAction, type[_ExecutionBody]] = {PlatformAction.RECORD_FAILURE: _FailureBody, PlatformAction.RECORD_MANAGER_DRAFT: _DraftBody}


def create_platform_v2_app(
    control: PlatformOperationControl, verifier: PlatformCredentialVerifier, *,
    max_body_bytes: int, body_timeout_seconds: float, tracer_provider: TracerProvider | None = None,
) -> FastAPI:
    if max_body_bytes <= 0 or not isfinite(body_timeout_seconds) or body_timeout_seconds <= 0:
        raise ValueError("Platform API needs positive body size and duration limits")
    app = FastAPI(title="AI RES private Platform API", docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    install_problem_handlers(app)
    if tracer_provider is not None:
        app.add_middleware(TelemetryMiddleware, tracer=tracer_provider.get_tracer("ai_res.platform_api"))

    async def execute(
        request: Request, operation_id: UUID, action: PlatformAction, *, adaptive_input: bool = False, epic_context: bool = False,
    ) -> dict[str, Any]:
        request_id = correlation_uuid(current_request_id())
        headers = request.headers.getlist("authorization")
        authorization = headers[0] if len(headers) == 1 else ""
        scheme, _, token = authorization.partition(" ")
        raw_path = request.scope.get("raw_path")
        query = request.scope["query_string"]
        if (
            scheme.lower() != "bearer" or not isinstance(raw_path, bytes)
            or not verifier.matches_transport(token, PlatformRequest(action, operation_id, b"", adaptive_input, epic_context),
                                              received_method=request.method, received_path=raw_path, received_query=query)
        ):
            await control.record_auth_failure(PlatformAuthFailure.INVALID_CREDENTIAL, request_id)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        try:
            async with timeout(body_timeout_seconds):
                raw_body = await read_bounded_body(request, max_body_bytes)
        except TimeoutError:
            await control.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, request_id)
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Request body was not received within its time limit.") from None
        except ProblemError:
            await control.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, request_id)
            raise
        credential = verifier.verify(
            token, PlatformRequest(action, operation_id, raw_body, adaptive_input, epic_context), received_method=request.method,
            received_path=raw_path, received_query=query,
        )
        if credential is None:
            await control.record_auth_failure(PlatformAuthFailure.INVALID_CREDENTIAL, request_id)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        model = _ContextDraftBody if epic_context and action is PlatformAction.RECORD_MANAGER_DRAFT else _BODY_MODELS.get(action, _ExecutionBody)
        try:
            body = model.model_validate(json.loads(raw_body.decode("utf-8"), object_pairs_hook=_unique))
        except (ValueError, ValidationError):
            await control.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, request_id)
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid control request.") from None
        version = body.context_version_id if isinstance(body, _ContextDraftBody) else None
        proposal = ProposalContent(body.goal, body.scope, body.primary_question, version) if isinstance(body, _DraftBody) else None
        command = PlatformOperationCommand(operation_id, body.workflow_id, body.workflow_run_id, action,
                                           body.code if isinstance(body, _FailureBody) else None, proposal, epic_context=epic_context)
        state = await control.execute(credential, command, request_id)
        if isinstance(state, AssignedManagerInput):
            result = {"operationId": state.operation_id, "message": state.message}
            if epic_context:
                if state.context is None:
                    raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Assigned context unavailable.")
                return {**result, "contextVersionId": state.context.version_id, "epicState": state.context.state.model_dump(by_alias=True)}
            if adaptive_input:
                # A journal record alone does not establish current ACL or classification.
                return {**result, "recentQuestions": [], "historyTruncated": False}
            return result
        return {"operationId": state.operation_id, "status": state.status}

    @app.post("/internal/v2/operations/{operationId}/start-acknowledgement")
    async def acknowledge_start(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.ACKNOWLEDGE_START)

    @app.post("/internal/v2/operations/{operationId}/failure")
    async def record_failure(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.RECORD_FAILURE)

    @app.post("/internal/v2/operations/{operationId}/cancellation-confirmation")
    async def confirm_cancellation(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.CONFIRM_CANCELLATION)

    @app.post("/internal/v3/operations/{operationId}/manager-input")
    async def read_manager_input(request: Request, response: Response, operationId: UUID) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return await execute(request, operationId, PlatformAction.READ_MANAGER_INPUT)

    @app.post("/internal/v4/operations/{operationId}/manager-input")
    async def read_adaptive_manager_input(request: Request, response: Response, operationId: UUID) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return await execute(request, operationId, PlatformAction.READ_MANAGER_INPUT, adaptive_input=True)

    @app.post("/internal/v3/operations/{operationId}/manager-draft")
    async def record_manager_draft(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.RECORD_MANAGER_DRAFT)

    @app.post("/internal/v5/operations/{operationId}/manager-input")
    async def read_manager_context(request: Request, response: Response, operationId: UUID) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return await execute(request, operationId, PlatformAction.READ_MANAGER_INPUT, epic_context=True)

    @app.post("/internal/v5/operations/{operationId}/manager-draft")
    async def record_context_draft(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.RECORD_MANAGER_DRAFT, epic_context=True)

    @app.post("/internal/v3/operations/{operationId}/plan-tasks")
    async def materialize_plan_tasks(request: Request, operationId: UUID) -> dict[str, Any]:
        return await execute(request, operationId, PlatformAction.MATERIALIZE_PLAN_TASKS)

    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(CorrelationMiddleware)
    return app
