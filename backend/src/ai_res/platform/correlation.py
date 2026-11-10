"""Request-id propagation. Correlation IDs are NOT authorization context (security.md). Trace context: see telemetry.py."""
import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)

_RID_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")
_TP_RE = re.compile(r"00-(?!0{32})[0-9a-f]{32}-(?!0{16})[0-9a-f]{16}-[0-9a-f]{2}")


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def valid_traceparent(value: str | None) -> str | None:
    return value if value and _TP_RE.fullmatch(value) else None


class CorrelationMiddleware:
    """Keep a valid incoming X-Request-ID, otherwise generate one; set X-Request-ID on the response (replacing any other)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next((v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"x-request-id"), "")
        rid = incoming if _RID_RE.fullmatch(incoming) else uuid.uuid4().hex
        token = _REQUEST_ID.set(rid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                message["headers"] = [*kept, (b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _REQUEST_ID.reset(token)
