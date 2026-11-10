"""Innermost error boundary: turns unhandled exceptions into a generic 500 Problem *inside* the middleware stack,
so correlation headers, request id and telemetry apply to 500 responses too (Starlette's own handler runs outside)."""
import logging

from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_res.platform.problems import PROBLEM_JSON, ErrorCode, problem_body

log = logging.getLogger("ai_res.boundary")


class ErrorBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except ClientDisconnect:
            log.info("client disconnected")  # nobody to answer; not a server error
        except Exception as exc:
            log.error("unhandled exception", extra={"exc_type": type(exc).__name__})  # type only: no message/traceback values
            if started:
                raise  # response already partially sent; let the server close the connection
            response = JSONResponse(problem_body(ErrorCode.INTERNAL_ERROR, 500, None), status_code=500, media_type=PROBLEM_JSON,
                                    headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)
