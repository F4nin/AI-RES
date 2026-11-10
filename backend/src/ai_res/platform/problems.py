"""RFC 9457 Problem Details with the stable code taxonomy of DOC-006 §16."""
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_res.platform.correlation import current_request_id

PROBLEM_JSON = "application/problem+json"
MAX_ERRORS = 20


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    STATE_TRANSITION_NOT_ALLOWED = "STATE_TRANSITION_NOT_ALLOWED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    AGGREGATE_VERSION_CONFLICT = "AGGREGATE_VERSION_CONFLICT"  # storage-level concurrency (database-and-migrations.md)
    PRECONDITION_REQUIRED = "PRECONDITION_REQUIRED"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    OPERATION_NOT_READY = "OPERATION_NOT_READY"
    POLICY_ENGINE_UNAVAILABLE = "POLICY_ENGINE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.AUTHENTICATION_REQUIRED: 401,
    ErrorCode.ACCESS_DENIED: 403,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.STATE_TRANSITION_NOT_ALLOWED: 409,
    ErrorCode.VERSION_CONFLICT: 412,
    ErrorCode.AGGREGATE_VERSION_CONFLICT: 409,
    ErrorCode.PRECONDITION_REQUIRED: 428,
    ErrorCode.IDEMPOTENCY_KEY_REUSED: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    ErrorCode.OPERATION_NOT_READY: 409,
    ErrorCode.POLICY_ENGINE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}
assert set(_STATUS) == set(ErrorCode), "every ErrorCode needs an HTTP status"
_TITLES = {c: c.value.replace("_", " ").capitalize() for c in ErrorCode}


class ProblemError(Exception):
    """Raise from application code; rendered as application/problem+json. `detail` must be safe for clients."""

    def __init__(self, code: ErrorCode, detail: str | None = None, *, status: int | None = None,
                 headers: dict[str, str] | None = None, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(code.value)
        resolved = _STATUS[code] if status is None else status
        if not 400 <= resolved <= 599:
            raise ValueError("problem status must be 4xx/5xx")
        self.code, self.detail, self.status = code, detail, resolved
        self.headers, self.errors = headers or {}, errors


def problem_body(code: ErrorCode, status: int, detail: str | None, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"type": f"urn:ai-res:problem:{code.value.lower()}", "title": _TITLES[code], "status": status,
                            "code": code.value}
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors[:MAX_ERRORS]
    if (rid := current_request_id()):
        body["requestId"] = rid
        body["instance"] = f"urn:ai-res:request:{rid}"
    return body


def _response(code: ErrorCode, status: int, detail: str | None, headers: dict[str, str] | None = None,
              errors: list[dict[str, str]] | None = None) -> JSONResponse:
    return JSONResponse(problem_body(code, status, detail, errors), status_code=status, media_type=PROBLEM_JSON,
                        headers={"Cache-Control": "no-store", **(headers or {})})


# Framework-level HTTP errors keep their own status. Unmapped 4xx -> VALIDATION_ERROR code (DOC-006 has no finer code), unmapped 5xx ->
# INTERNAL_ERROR; clients must key on `status` for these (ADR-041 consequences).
_HTTP_TO_CODE = {401: ErrorCode.AUTHENTICATION_REQUIRED, 403: ErrorCode.ACCESS_DENIED, 404: ErrorCode.RESOURCE_NOT_FOUND,
                 405: ErrorCode.VALIDATION_ERROR, 503: ErrorCode.DEPENDENCY_UNAVAILABLE,
                 409: ErrorCode.STATE_TRANSITION_NOT_ALLOWED, 412: ErrorCode.VERSION_CONFLICT,
                 428: ErrorCode.PRECONDITION_REQUIRED, 429: ErrorCode.RATE_LIMITED}


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError) -> JSONResponse:
        return _response(exc.code, exc.status, exc.detail, exc.headers, exc.errors)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and generic messages only: never echo client input (may contain secrets).
        errors = [{"field": "body" if e["type"] == "json_invalid" else ".".join(str(p) for p in e["loc"]),
                   "reason": str(e["type"])} for e in exc.errors()]
        return _response(ErrorCode.VALIDATION_ERROR, 422, "Request validation failed.", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_TO_CODE.get(exc.status_code, ErrorCode.VALIDATION_ERROR if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR)
        return _response(code, exc.status_code, None, dict(exc.headers) if exc.headers else None)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Generic body: no exception text, stack trace, or provider payload (api-and-contracts.md).
        return _response(ErrorCode.INTERNAL_ERROR, 500, None)
