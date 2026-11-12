"""HTTP implementation of `OperationPlatform` for the runtimes: internal Platform API + a fresh short-lived service token per call (Auth v1.1 §8).

Failure classification (Process v1.9 §13.1): connection faults, timeouts, 5xx, 429 and 409 are TRANSIENT (bounded Temporal retry); 401/403/404/4xx are PERMANENT
(never retried: a revoked or forged identity must fail closed, not hammer the API). Response bodies are never logged or echoed.
"""
from collections.abc import Callable
from datetime import timedelta

import httpx
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ai_res.orchestration.contracts import ContractError, OperationFailure, OperationRef, OperationState
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError

TOKEN_TTL = timedelta(seconds=60)  # WORKING: well under service_token_max_ttl_seconds

_TRACE_CONTEXT = TraceContextTextMapPropagator()


def _problem_code(response: httpx.Response) -> str | None:
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) else None


class HttpOperationPlatform:
    def __init__(self, base_url: str, mint_token: Callable[[], str], *, timeout_seconds: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, transport=transport, follow_redirects=False)
        self._mint = mint_token

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._mint()}"}
        _TRACE_CONTEXT.inject(headers)  # W3C traceparent only (never baggage): the Platform API span continues the Activity span
        return headers

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict[str, str]) -> OperationState:
        try:
            response = await self._client.post(path, json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise PlatformTransientError(type(exc).__name__) from None
        status = response.status_code
        if status == 409 and _problem_code(response) == "STATE_TRANSITION_NOT_ALLOWED":
            raise PlatformPermanentError("transition not allowed")  # a state error: retrying cannot make an illegal transition legal
        if status in (408, 409, 425, 429) or status >= 500:
            raise PlatformTransientError(f"http {status}")  # 409 otherwise = a lost compare-and-swap race: the retry sees the winner
        if status != 200:
            raise PlatformPermanentError(f"http {status}")
        try:
            data = response.json()
            return OperationState(str(data["operationId"]), str(data["status"]))
        except (ValueError, KeyError, TypeError, ContractError):
            raise PlatformPermanentError("malformed response") from None

    @staticmethod
    def _scope(ref: OperationRef) -> dict[str, str]:
        return {"organizationId": ref.organization_id, "projectId": ref.project_id}

    async def acknowledge_start(self, ref: OperationRef) -> OperationState:
        return await self._post(f"/internal/v1/operations/{ref.operation_id}/start-acknowledgement", self._scope(ref))

    async def confirm_cancellation(self, ref: OperationRef) -> OperationState:
        return await self._post(f"/internal/v1/operations/{ref.operation_id}/cancellation-confirmation", self._scope(ref))

    async def record_failure(self, failure: OperationFailure) -> OperationState:
        return await self._post(f"/internal/v1/operations/{failure.operation.operation_id}/failure", {**self._scope(failure.operation), "code": failure.code})
