"""Separate, disabled-by-default candidate control ASGI app (ADR134).

Never mounted in either product app. HTTPS scope is necessary, not proof of TLS
termination: composition must separately verify private CA/hostname configuration
and disable untrusted proxy headers. Existing Ed25519 service authentication proves
only LLM_GATEWAY identity; fixed server-owned account/plan plus the paid ledger
still decide claim eligibility. No cookie, reserve or approval operation exists.
"""
import asyncio
import json
from typing import Any, NoReturn
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ai_res.modules.model_registry.poc_control import (
    CONTROL_VERSION,
    CandidateClaimRequest,
    CandidateControlDenied,
    CandidateControlPort,
    CandidateControlUnavailable,
    CandidateSettlementRequest,
)
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceIdentity, ServiceIdentityPort, ServiceName

MAX_REQUEST_BYTES = 4096
CAPABILITIES = {"claim": frozenset({ServiceName.LLM_GATEWAY}), "settlement": frozenset({ServiceName.LLM_GATEWAY})}


class _InvalidRequest(ValueError):
    def __init__(self, status: int = 400) -> None:
        self.status = status


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status, headers={"cache-control": "no-store"})


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidRequest()
        result[key] = value
    return result


def _nonfinite(_: str) -> NoReturn:
    raise _InvalidRequest()


async def _body(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise _InvalidRequest()
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise _InvalidRequest()
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1 or lengths and (not lengths[0].isdigit() or len(lengths[0]) > 10):
        raise _InvalidRequest()
    if lengths and int(lengths[0]) > MAX_REQUEST_BYTES:
        raise _InvalidRequest(413)
    raw = bytearray()
    # WORKING bounded read, not a product SLO. No unbounded authenticated upload.
    async with asyncio.timeout(5):
        async for part in request.stream():
            if len(raw)+len(part) > MAX_REQUEST_BYTES:
                raise _InvalidRequest(413)
            raw.extend(part)
    if lengths and len(raw) != int(lengths[0]):
        raise _InvalidRequest()
    try:
        data = json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        raise _InvalidRequest() from None
    if not isinstance(data, dict) or data.get("version") != CONTROL_VERSION:
        raise _InvalidRequest()
    return data


def _claim(data: dict[str, Any]) -> CandidateClaimRequest:
    if set(data) != {"version", "codecVersion", "templateCase", "bodySha256", "payloadBytes", "stream", "maxOutputTokens"}:
        raise _InvalidRequest()
    return CandidateClaimRequest(data["codecVersion"], data["templateCase"], data["bodySha256"], data["payloadBytes"], data["stream"], data["maxOutputTokens"])


def _settlement(data: dict[str, Any]) -> CandidateSettlementRequest:
    required = {"version", "attemptId", "bodySha256", "outcome"}
    allowed = required | {"inputTokens", "outputTokens", "providerRequestRef", "reason"}
    if not required <= set(data) <= allowed or not isinstance(data["attemptId"], str):
        raise _InvalidRequest()
    try:
        attempt = UUID(data["attemptId"])
    except ValueError:
        raise _InvalidRequest() from None
    if str(attempt) != data["attemptId"]:
        raise _InvalidRequest()
    # Preserve omitted versus explicit-null fields for outcome-exclusive DTO
    # validation; contradictory facts must reach durable INVALID_USAGE handling.
    facts = {name: data[key] for key, name in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
                                              ("providerRequestRef", "provider_request_ref"), ("reason", "reason")) if key in data}
    return CandidateSettlementRequest(attempt, data["bodySha256"], data["outcome"], **facts)


def create_poc_admission_app(service: CandidateControlPort, verifier: ServiceIdentityPort, *, enabled: bool = False) -> Starlette:
    async def endpoint(request: Request) -> Response:
        if enabled is not True:
            return _error("CANDIDATE_CONTROL_DISABLED", 503)
        if request.scope.get("scheme") != "https":
            return _error("HTTPS_REQUIRED", 403)
        if request.scope.get("query_string") or "cookie" in request.headers:
            return _error("INVALID_REQUEST", 400)
        authorization = request.headers.getlist("authorization")
        if len(authorization) != 1 or len(authorization[0]) > 1100:
            return _error("AUTHENTICATION_REQUIRED", 401)
        scheme, _, token = (
            authorization[0].partition(" ")
        )
        if scheme.lower() != "bearer" or not token:
            return _error("AUTHENTICATION_REQUIRED", 401)
        try:
            identity = await verifier.verify_service_token(token, ServiceName.API)
        except Exception:
            return _error("CANDIDATE_CONTROL_UNAVAILABLE", 503)
        if not isinstance(identity, ServiceIdentity) or identity.audience is not ServiceName.API or identity.expires_at <= utc_now():
            return _error("AUTHENTICATION_REQUIRED", 401)
        action = "claim" if request.url.path == "/candidate/v1/claim" else "settlement"
        if identity.name not in CAPABILITIES[action]:
            return _error("ACCESS_DENIED", 403)
        try:
            data = await _body(request)
            if action == "claim":
                try:
                    command = _claim(data)
                except CandidateControlDenied:
                    raise _InvalidRequest() from None
                result = await service.claim(command)
                return JSONResponse({"version": CONTROL_VERSION, "attemptId": str(result.attempt_id), "requestRef": result.request_ref,
                                     "bodySha256": result.body_sha256, "payloadBytes": result.payload_bytes, "stream": result.stream,
                                     "maxOutputTokens": result.max_output_tokens,
                                     }, headers={"cache-control": "no-store"})
            try:
                settlement = _settlement(data)
            except CandidateControlDenied:
                raise _InvalidRequest() from None
            recorded = await service.settle(settlement)
            return JSONResponse({"version": CONTROL_VERSION, "attemptId": str(recorded.attempt_id), "outcome": recorded.outcome},
                                headers={"cache-control": "no-store"})
        except _InvalidRequest as error:
            return _error("INVALID_REQUEST", error.status)
        except CandidateControlDenied:
            return _error("CANDIDATE_CONTROL_DENIED", 409)
        except (CandidateControlUnavailable, TimeoutError):
            return _error("CANDIDATE_CONTROL_UNAVAILABLE", 503)
        except Exception:
            return _error("CANDIDATE_CONTROL_UNAVAILABLE", 503)

    return Starlette(routes=[Route("/candidate/v1/claim", endpoint, methods=["POST"]),
                             Route("/candidate/v1/settlement", endpoint, methods=["POST"])])
