"""Internal Platform API (Contracts v1.10 §7.2): the ONLY way Manager/Worker Runtime change the domain. NOT public: it is a separate ASGI app on its own port,
never routed by the reverse proxy, authenticated by short-lived audience-scoped service tokens (Auth v1.1 §8) - not by browser sessions, no cookies, no CSRF.

Authorisation of a service call is a fixed capability table (WORKING, ADR-088): which service identity may call which narrow operation. A service
identity proves WHICH component calls; it is not a Worker Run grant and never widens into a user permission.
Unknown/invalid/expired tokens -> 401, a known service without the
capability -> 403 (denial audited by log only: no tenant context exists yet to write an audit row under RLS - G-106). The contract is
`contracts/internal/AI_RES_Platform_Internal_API_v0.1.yaml` (WORKING overlay).
"""
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ai_res.modules.audit.writer import correlation_uuid
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.orchestration.contracts import ContractError, OperationFailure, OperationRef
from ai_res.platform.boundary import ErrorBoundaryMiddleware
from ai_res.platform.correlation import CorrelationMiddleware, current_request_id
from ai_res.platform.ports import ServiceIdentity, ServiceIdentityPort, ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError, install_problem_handlers

CAPABILITIES: dict[str, frozenset[ServiceName]] = {  # WORKING (ADR-088)
    "operation.acknowledge_start": frozenset({ServiceName.MANAGER_RUNTIME}),
    "operation.record_failure": frozenset({ServiceName.MANAGER_RUNTIME}),
    "operation.confirm_cancellation": frozenset({ServiceName.MANAGER_RUNTIME}),
}


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid")


class ScopeBody(_Body):
    organization_id: UUID
    project_id: UUID


class FailureBody(ScopeBody):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")


def create_internal_app(service: OperationOrchestrationService, verifier: ServiceIdentityPort) -> FastAPI:
    app = FastAPI(title="AI RES internal platform API", docs_url=None, redoc_url=None, openapi_url=None)
    install_problem_handlers(app)

    def caller(capability: str):  # type: ignore[no-untyped-def]
        async def dependency(request: Request) -> ServiceIdentity:
            header = request.headers.get("authorization", "")
            scheme, _, token = header.partition(" ")
            identity = await verifier.verify_service_token(token, ServiceName.API) if scheme.lower() == "bearer" and token else None
            if identity is None:
                raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
            if identity.name not in CAPABILITIES[capability]:
                raise ProblemError(ErrorCode.ACCESS_DENIED, "Access denied.")
            return identity
        return Depends(dependency)

    def view(operation_id: UUID, state_status: str) -> dict[str, Any]:
        return {"operationId": str(operation_id), "status": state_status}

    def ref(operation_id: UUID, body: ScopeBody) -> OperationRef:
        try:
            return OperationRef(str(operation_id), str(body.organization_id), str(body.project_id))
        except ContractError:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid reference.") from None

    @app.post("/internal/v1/operations/{operationId}/start-acknowledgement")
    async def acknowledge_start(operationId: UUID, body: ScopeBody, _: Annotated[ServiceIdentity, caller("operation.acknowledge_start")]) -> dict[str, Any]:
        state = await service.acknowledge_start(ref(operationId, body), correlation_uuid(current_request_id()))
        return view(operationId, state.status)

    @app.post("/internal/v1/operations/{operationId}/failure")
    async def record_failure(operationId: UUID, body: FailureBody, _: Annotated[ServiceIdentity, caller("operation.record_failure")]) -> dict[str, Any]:
        state = await service.record_failure(OperationFailure(ref(operationId, body), body.code), correlation_uuid(current_request_id()))
        return view(operationId, state.status)

    @app.post("/internal/v1/operations/{operationId}/cancellation-confirmation")
    async def confirm_cancellation(operationId: UUID, body: ScopeBody,
                                   _: Annotated[ServiceIdentity, caller("operation.confirm_cancellation")]) -> dict[str, Any]:
        state = await service.confirm_cancellation(ref(operationId, body), correlation_uuid(current_request_id()))
        return view(operationId, state.status)

    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(CorrelationMiddleware)
    return app
