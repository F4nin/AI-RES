"""Manager's ar2 client for the exact assigned execution, over private HTTPS."""
import json
import ssl
from asyncio import timeout
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ai_res.modules.iam.platform_credentials import PlatformAction, PlatformCredentialIssuer, PlatformCredentialLimits, PlatformRequest
from ai_res.orchestration.contracts import OperationState
from ai_res.orchestration.manager_context import IssuedManagerContext, ManagerEpicContext
from ai_res.orchestration.manager_workflows import BoundWorkflowCall
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError
from ai_res.platform.config import ConfigError, Settings
from ai_res.runtime.manager_reasoning import IntakeQuestionContext, ManagerDraft, ManagerReasoningInput, QuestionDisposition

_TRACE_CONTEXT = TraceContextTextMapPropagator()
_STATUS_RESPONSE_BYTES = 4096
_MESSAGE_RESPONSE_BYTES = 120_256  # The v3 producer emits non-ASCII Unicode directly.
_ADAPTIVE_RESPONSE_BYTES = 12 * 20_000 + 256 + 8 * (12 * (20_000 + 128) + 256)  # Also allows escaped surrogate pairs.
_CONTEXT_RESPONSE_BYTES = 12 * 20_000 + 4096
_STATUS = frozenset({
    "ACCEPTED", "QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING",
    "CANCEL_REQUESTED", "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED",
})


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate response field")
        result[name] = value
    return result


@dataclass(frozen=True, slots=True, repr=False)
class AdaptiveManagerRead:
    message: str
    questions: tuple[IntakeQuestionContext, ...]
    history_truncated: bool


class PlatformControlClient:
    @classmethod
    def for_manager(
        cls, settings: Settings, *, ca_file: Path, signing_key: Ed25519PrivateKey, ttl: timedelta,
    ) -> "PlatformControlClient":
        url, max_body, max_token = settings.platform_api_url, settings.platform_request_max_bytes, settings.platform_credential_max_bytes
        if url is None or max_body is None or max_token is None:
            raise ConfigError("assigned Manager requires a Platform endpoint and request limits")
        limits = PlatformCredentialLimits(timedelta(seconds=settings.service_token_max_ttl_seconds), timedelta(0), max_body, max_token)
        if not timedelta(seconds=1) <= ttl <= limits.max_ttl:
            raise ConfigError("assigned Manager credential lifetime exceeds the configured limits")
        try:
            return cls(url, ca_file=ca_file, issuer=PlatformCredentialIssuer(signing_key, limits), ttl=ttl,
                       timeout_seconds=settings.platform_api_timeout_seconds)
        except ValueError:
            raise ConfigError("invalid assigned Manager Platform transport") from None

    def __init__(self, url: str, *, ca_file: Path, issuer: PlatformCredentialIssuer, ttl: timedelta, timeout_seconds: float) -> None:
        try:
            origin = httpx.URL(url)
            if (origin.scheme != "https" or not origin.host or origin.userinfo or origin.query or origin.fragment
                    or origin.path not in ("", "/") or not 0 < timeout_seconds <= 60):
                raise ValueError
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=ca_file)
            context.verify_flags |= ssl.VERIFY_X509_STRICT
        except (ValueError, OSError, httpx.InvalidURL):
            raise ValueError("Platform control requires a valid private HTTPS origin and CA") from None
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._client = httpx.AsyncClient(base_url=origin, verify=context, timeout=timeout_seconds, trust_env=False, follow_redirects=False)
        self._issuer, self._ttl, self._timeout = issuer, ttl, timeout_seconds

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(
        self, reference: BoundWorkflowCall, action: PlatformAction, extra: dict[str, str | None], max_bytes: int, *, adaptive_input: bool = False,
        epic_context: bool = False,
    ) -> dict[str, Any]:
        body = {"workflowId": reference.workflow_id, "workflowRunId": reference.workflow_run_id, **extra}
        request = PlatformRequest(
            action, UUID(reference.operation.operation_id), json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
            adaptive_input=adaptive_input, epic_context=epic_context,
        )
        token = self._issuer.issue(request, assignment_id=UUID(reference.assignment_id), ttl=self._ttl)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept-Encoding": "identity"}
        _TRACE_CONTEXT.inject(headers)
        try:
            async with timeout(self._timeout), self._client.stream("POST", request.path, content=request.body, headers=headers) as response:
                if response.status_code == 404 and action is PlatformAction.ACKNOWLEDGE_START:
                    # Start can deliver a polling task just ahead of trusted Run binding.
                    # Only the non-paid acknowledgement Activity retries this response.
                    raise PlatformTransientError("Assigned execution is not ready")
                if response.status_code in (408, 409, 425, 429) or response.status_code >= 500:
                    raise PlatformTransientError("Platform control temporarily unavailable")
                if response.status_code != 200 or response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise PlatformPermanentError("Platform control rejected the request")
                if (adaptive_input or (epic_context and action is PlatformAction.READ_MANAGER_INPUT)) and response.headers.get("cache-control") != "no-store":
                    raise PlatformPermanentError("Invalid Platform control response")
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(payload) + len(chunk) > max_bytes:
                        raise PlatformPermanentError("Invalid Platform control response")
                    payload.extend(chunk)
            data = json.loads(payload, object_pairs_hook=_unique_fields)
        except (ValueError, KeyError, TypeError):
            raise PlatformPermanentError("Invalid Platform control response") from None
        except (TimeoutError, httpx.HTTPError):
            raise PlatformTransientError("Platform control temporarily unavailable") from None
        if not isinstance(data, dict) or data.get("operationId") != reference.operation.operation_id:
            raise PlatformPermanentError("Invalid Platform control response")
        return data

    async def call(self, reference: BoundWorkflowCall, action: PlatformAction, *, epic_context: bool = False, **fields: str | None) -> OperationState:
        data = await self._post(reference, action, fields, _STATUS_RESPONSE_BYTES, epic_context=epic_context)
        status = data.get("status")
        if set(data) != {"operationId", "status"} or not isinstance(status, str) or status not in _STATUS:
            raise PlatformPermanentError("Invalid Platform control response")
        return OperationState(reference.operation.operation_id, status)

    async def read_manager_message(self, reference: BoundWorkflowCall) -> str:
        data = await self._post(reference, PlatformAction.READ_MANAGER_INPUT, {}, _MESSAGE_RESPONSE_BYTES)
        message = data.get("message")
        if set(data) != {"operationId", "message"} or not isinstance(message, str) or not 1 <= len(message) <= 20_000:
            raise PlatformPermanentError("Invalid Platform control response")
        return message

    async def read_manager_context(self, reference: BoundWorkflowCall) -> tuple[str, IssuedManagerContext]:
        data = await self._post(reference, PlatformAction.READ_MANAGER_INPUT, {}, _CONTEXT_RESPONSE_BYTES, epic_context=True)
        message = data.get("message")
        if (set(data) != {"operationId", "message", "contextVersionId", "epicState"}
                or not isinstance(message, str) or not 1 <= len(message) <= 20_000 or "\x00" in message):
            raise PlatformPermanentError("Invalid Platform control response")
        try:
            version_id = UUID(data["contextVersionId"])
            if str(version_id) != data["contextVersionId"]:
                raise ValueError
            state = ManagerEpicContext.model_validate(data["epicState"])
        except (AttributeError, TypeError, ValueError):
            raise PlatformPermanentError("Invalid Platform control response") from None
        return message, IssuedManagerContext(version_id, state)

    async def read_adaptive_manager_input(self, reference: BoundWorkflowCall) -> AdaptiveManagerRead:
        data = await self._post(reference, PlatformAction.READ_MANAGER_INPUT, {}, _ADAPTIVE_RESPONSE_BYTES, adaptive_input=True)
        message, records, truncated = data.get("message"), data.get("recentQuestions"), data.get("historyTruncated")
        if (set(data) != {"operationId", "message", "recentQuestions", "historyTruncated"}
                or not isinstance(message, str) or not 1 <= len(message) <= 20_000 or "\x00" in message
                or not isinstance(records, list) or len(records) > 8 or not isinstance(truncated, bool)):
            raise PlatformPermanentError("Invalid Platform control response")
        questions: list[IntakeQuestionContext] = []
        try:
            for record in records:
                if (not isinstance(record, dict) or set(record) != {"questionId", "topic", "disposition", "answer"}
                        or not isinstance(record["questionId"], str)):
                    raise ValueError
                question = IntakeQuestionContext(
                    UUID(record["questionId"]), record["topic"], QuestionDisposition(record["disposition"]), record["answer"],
                )
                if str(question.question_id) != record["questionId"] or (questions and question.disposition is QuestionDisposition.OPEN):
                    raise ValueError
                questions.append(question)
            if len({question.question_id for question in questions}) != len(questions):
                raise ValueError
        except (TypeError, ValueError):
            raise PlatformPermanentError("Invalid Platform control response") from None
        return AdaptiveManagerRead(message, tuple(questions), truncated)


class ManagerHttpPlatform:
    """Combines private execution commands and a separately authorized model context."""

    def __init__(
        self, control: PlatformControlClient,
        build_input: Callable[[BoundWorkflowCall, str], Awaitable[ManagerReasoningInput]],
        *, adaptive_input: bool = False, epic_context: bool = False,
    ) -> None:
        if adaptive_input and epic_context:
            raise ValueError("Manager intake needs one private contract version")
        self._control, self._build_input = control, build_input
        self._adaptive_input = adaptive_input
        self._epic_context = epic_context

    async def acknowledge_manager_start(self, reference: BoundWorkflowCall) -> OperationState:
        return await self._control.call(reference, PlatformAction.ACKNOWLEDGE_START)

    async def manager_input(self, reference: BoundWorkflowCall) -> ManagerReasoningInput:
        if self._epic_context:
            message, context = await self._control.read_manager_context(reference)
            return replace(await self._build_input(reference, message), epic_context=context)
        if self._adaptive_input:
            adaptive = await self._control.read_adaptive_manager_input(reference)
            intake = await self._build_input(reference, adaptive.message)
            return replace(intake, recent_questions=adaptive.questions, history_truncated=adaptive.history_truncated)
        return await self._build_input(reference, await self._control.read_manager_message(reference))

    async def record_manager_draft(
        self, reference: BoundWorkflowCall, draft: ManagerDraft, *, context_version_id: UUID | None = None,
    ) -> OperationState:
        if self._epic_context != (context_version_id is not None):
            raise PlatformPermanentError("Manager draft version has no matching input")
        version = {} if context_version_id is None else {"contextVersionId": str(context_version_id)}
        return await self._control.call(reference, PlatformAction.RECORD_MANAGER_DRAFT,
                                        epic_context=self._epic_context, goal=draft.goal, scope=draft.scope,
                                        primaryQuestion=draft.primary_question, **version)

    async def prepare_plan_tasks(self, reference: BoundWorkflowCall) -> OperationState:
        state = await self._control.call(reference, PlatformAction.ACKNOWLEDGE_START)
        if state.status != "RUNNING":
            return state
        return await self._control.call(reference, PlatformAction.MATERIALIZE_PLAN_TASKS)

    async def confirm_cancellation(self, reference: BoundWorkflowCall) -> OperationState:
        return await self._control.call(reference, PlatformAction.CONFIRM_CANCELLATION)
