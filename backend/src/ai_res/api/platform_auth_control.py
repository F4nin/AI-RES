"""Fixed private metadata routes for the native Temporal frontend."""
import json
from asyncio import timeout
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from starlette.responses import JSONResponse

from ai_res.application.native_auth_control import (
    NativeAuthControl,
    NativeBoundCancellation,
    NativeReconciliationDescribe,
    NativeStartIntent,
    NativeTaskAuthorization,
)
from ai_res.application.platform_control import PlatformAuthFailure, PlatformOperationControl
from ai_res.modules.audit.writer import correlation_uuid
from ai_res.modules.iam.platform_credentials import AuthControlAction, AuthControlRequest, PlatformCredentialVerifier
from ai_res.modules.iam.service_tokens import _unique
from ai_res.modules.iam.task_issuance import IssuanceLookup, TaskExecutionRef, TaskKind
from ai_res.platform.boundary import read_bounded_body
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ports import ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")


class _StartBody(_Body):
    caller: Literal["OUTBOX_DISPATCHER"]
    assignment_id: UUID
    workflow_id: str = Field(pattern=r"^operation-[0-9a-f-]{36}$")
    workflow_type: Literal["ManagerIntakeWorkflow", "PlanExecutionWorkflow"]
    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    task_queue: Literal["ai-res-manager"]
    workflow_contract_version: Literal[1]
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _TaskBody(_Body):
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    principal: ServiceName
    namespace: str
    queue: str
    task_kind: TaskKind
    operation_id: UUID
    workflow_run_id: UUID


class _ReconciliationDescribeBody(_Body):
    operation_id: UUID
    workflow_run_id: UUID
    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")


class _BoundCancellationBody(_ReconciliationDescribeBody):
    assignment_id: UUID


def register_native_auth_control(
    app: FastAPI, control: NativeAuthControl, audit: PlatformOperationControl, verifier: PlatformCredentialVerifier,
    *, max_bytes: int, timeout_seconds: float,
) -> None:
    async def decide(request: Request, action: AuthControlAction) -> Response:
        correlation = correlation_uuid(current_request_id())
        credentials = request.headers.getlist("authorization")
        authorization = credentials[0] if len(credentials) == 1 else ""
        scheme, _, credential_text = authorization.partition(" ")
        raw_path = request.scope.get("raw_path")
        query = request.scope["query_string"]
        if (scheme.lower() != "bearer" or not isinstance(raw_path, bytes) or not verifier.matches_transport(
            credential_text, AuthControlRequest(action, b""), received_method=request.method, received_path=raw_path, received_query=query,
        )):
            await audit.record_auth_failure(PlatformAuthFailure.INVALID_CREDENTIAL, correlation)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        try:
            async with timeout(timeout_seconds):
                raw = await read_bounded_body(request, max_bytes)
        except (TimeoutError, ProblemError):
            await audit.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, correlation)
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid native authorization request.") from None
        credential = verifier.verify_auth_control(credential_text, AuthControlRequest(action, raw), received_method=request.method,
                                                 received_path=raw_path, received_query=query)
        if credential is None:
            await audit.record_auth_failure(PlatformAuthFailure.INVALID_CREDENTIAL, correlation)
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
            command: NativeStartIntent | NativeReconciliationDescribe | NativeBoundCancellation | NativeTaskAuthorization
            if action is AuthControlAction.AUTHORIZE_START:
                start = _StartBody.model_validate(data)
                command = NativeStartIntent(start.assignment_id, start.workflow_id, start.workflow_type, start.namespace, start.task_queue,
                                            start.workflow_contract_version, bytes.fromhex(start.input_sha256))
            elif action in {AuthControlAction.AUTHORIZE_RECONCILIATION_DESCRIBE, AuthControlAction.AUTHORIZE_BOUND_STATUS}:
                describe = _ReconciliationDescribeBody.model_validate(data)
                command = NativeReconciliationDescribe(describe.operation_id, describe.workflow_run_id, describe.namespace,
                                                       active_status_only=action is AuthControlAction.AUTHORIZE_BOUND_STATUS)
            elif action is AuthControlAction.AUTHORIZE_BOUND_CANCEL:
                cancellation = _BoundCancellationBody.model_validate(data)
                command = NativeBoundCancellation(cancellation.assignment_id, cancellation.operation_id, cancellation.workflow_run_id, cancellation.namespace)
            else:
                task = _TaskBody.model_validate(data)
                key = IssuanceLookup(bytes.fromhex(task.token_sha256), task.principal, task.namespace, task.queue, task.task_kind)
                command = NativeTaskAuthorization(key, TaskExecutionRef(task.operation_id, task.workflow_run_id),
                                                  action is AuthControlAction.REGISTER_TASK, action is AuthControlAction.WORKFLOW_TASK_CONTEXT)
        except (ValueError, ValidationError):
            await audit.record_auth_failure(PlatformAuthFailure.INVALID_REQUEST, correlation)
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid native authorization request.") from None
        context = await control.authorize(credential, command, correlation)
        headers = {"Cache-Control": "no-store"}
        if context is not None:
            return JSONResponse({"assignmentId": str(context.assignment_id), "workflowType": context.workflow_type,
                                 "workflowContractVersion": context.workflow_contract_version, "inputSha256": context.input_digest.hex(),
                                 "operationStatus": context.operation_status}, headers=headers)
        return Response(status_code=204, headers=headers)

    @app.post("/internal/auth-control/v1/authorize-start", status_code=204)
    async def check_start(request: Request) -> Response:
        return await decide(request, AuthControlAction.AUTHORIZE_START)

    @app.post("/internal/auth-control/v1/authorize-reconciliation-describe", status_code=204)
    async def check_reconciliation_describe(request: Request) -> Response:
        return await decide(request, AuthControlAction.AUTHORIZE_RECONCILIATION_DESCRIBE)

    @app.post("/internal/auth-control/v1/authorize-bound-status", status_code=204)
    async def check_bound_status(request: Request) -> Response:
        return await decide(request, AuthControlAction.AUTHORIZE_BOUND_STATUS)

    @app.post("/internal/auth-control/v1/authorize-bound-cancel", status_code=204)
    async def check_bound_cancel(request: Request) -> Response:
        return await decide(request, AuthControlAction.AUTHORIZE_BOUND_CANCEL)

    @app.post("/internal/auth-control/v1/register-task", status_code=204)
    async def register_task(request: Request) -> Response:
        return await decide(request, AuthControlAction.REGISTER_TASK)

    @app.post("/internal/auth-control/v1/check-task", status_code=204)
    async def check_task(request: Request) -> Response:
        return await decide(request, AuthControlAction.CHECK_TASK)

    @app.post("/internal/auth-control/v1/workflow-task-context")
    async def workflow_task_context(request: Request) -> Response:
        return await decide(request, AuthControlAction.WORKFLOW_TASK_CONTEXT)
