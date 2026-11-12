"""streamProjectEvents (ADR-033, ADR-092): Server-Sent Events from the per-aggregate event histories, never from the Outbox.

Authorization is checked at connect AND on every poll: the session is re-authenticated and the read right re-decided, so a revoked session, membership or role
closes the stream (`event: close`, reason `access_revoked`) instead of leaking further events. Each event is an ACL-neutral projection (no `data`).
`Last-Event-ID` is an opaque HMAC-signed cursor bound to the session, the project and this endpoint: a forged cursor, another session's or project's cursor
is a 400, never a silent restart. A cursor older than the retained history yields `event: gap` (resynchronise from REST); the REST snapshot stays the truth.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.responses import StreamingResponse

from ai_res.api.identity import IdentityServices
from ai_res.db.session import UnitOfWork
from ai_res.modules.events.stream import MAX_TRACKED, Position, ProjectEventReader, StreamEvent
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.platform.clock import utc_now
from ai_res.platform.pagination import InvalidCursor, decode_cursor, encode_cursor
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError

AUDIENCE = "project-events"
_log = logging.getLogger("ai_res.api.events")


def _frame(event: str, data: dict[str, Any], event_id: str | None = None) -> bytes:
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


def _projection(e: StreamEvent) -> dict[str, Any]:
    return {"eventId": str(e.event_id), "aggregateType": e.aggregate_type, "aggregateId": str(e.aggregate_id), "sequence": e.sequence, "type": e.event_type,
            "occurredAt": e.occurred_at.isoformat().replace("+00:00", "Z"), "fromStatus": e.from_status, "toStatus": e.to_status, "reasonCode": e.reason_code}


def register_events_api(app: FastAPI, services: IdentityServices) -> None:
    settings, enforcer, factory = services.settings, services.enforcer, services.factory
    if services.current_session is None:
        raise RuntimeError("register_identity must run before register_events_api")
    router = APIRouter(prefix="/api/v1")
    settle, retention = timedelta(seconds=settings.sse_settle_seconds), timedelta(seconds=settings.sse_retention_seconds)

    def request_of(s: AuthenticatedSession, project_id: UUID) -> PolicyRequest:
        return PolicyRequest(actor_id=str(s.user_id), action="project.events_read", resource_type="PROJECT", resource_id=str(project_id),
                             organization_id=str(s.organization_id), project_id=str(project_id), attributes={"mfa_verified": s.mfa_verified_at is not None})

    @router.get("/projects/{project_id}/events")
    async def stream_project_events(project_id: UUID, request: Request, s: Annotated[AuthenticatedSession, Depends(services.current_session)],
                                    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None) -> StreamingResponse:
        ring = getattr(request.app.state, "cursor_key_ring", None)
        if ring is None:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Event streaming is not configured.")
        await enforcer.decide(request_of(s, project_id), conceal=True)  # a project the caller cannot read is a 404, the same as a missing one
        filters = {"organization": str(s.organization_id), "project": str(project_id)}
        subject = str(s.session_id)
        gap = False
        if last_event_id:
            try:
                position = Position.from_keyset(decode_cursor(ring, last_event_id, subject=subject, audience=AUDIENCE, filters=filters))
            except (InvalidCursor, ValueError):
                raise ProblemError(ErrorCode.VALIDATION_ERROR, "Last-Event-ID is not valid for this stream.",
                                   errors=[{"field": "Last-Event-ID", "reason": "invalid_cursor"}]) from None
            gap = ProjectEventReader.retention_gap(position.watermark, retention)
            if gap:
                position = Position(utc_now() - settle, {})  # resume from now; the client is told to resynchronise first
        else:
            position = Position(utc_now() - settle, {})
        token = request.cookies.get(settings.session_cookie_name, "")

        def cursor_for(p: Position) -> str:
            return encode_cursor(ring, subject=subject, audience=AUDIENCE, filters=filters, keyset=p.to_keyset(), ttl_seconds=settings.sse_retention_seconds)

        async def events() -> AsyncIterator[bytes]:
            nonlocal position
            if gap:
                yield _frame("gap", {"reason": "retention", "resync": f"/api/v1/projects/{project_id}"})
            deadline = utc_now() + timedelta(seconds=settings.sse_max_seconds)
            first = True
            while utc_now() < deadline:
                if not first:
                    await asyncio.sleep(settings.sse_poll_interval_seconds)
                first = False
                try:  # access is re-proven on EVERY poll: session first, then the read right
                    current = (await services.sessions.authenticate(token, touch=False)).session
                    if current is None or current.session_id != s.session_id or current.second_factor_pending:
                        raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Session ended.")
                    await enforcer.decide(request_of(current, project_id), conceal=True)
                except ProblemError as exc:
                    revoked = exc.code in (ErrorCode.AUTHENTICATION_REQUIRED, ErrorCode.ACCESS_DENIED, ErrorCode.RESOURCE_NOT_FOUND)
                    if not revoked:  # a dependency outage is not a revocation: the client must keep reconnecting
                        _log.error("event stream closed: authorization check unavailable (%s)", exc.code)
                    yield _frame("close", {"reason": "access_revoked" if revoked else "unavailable"})
                    return
                except Exception:  # an authorization outage never keeps a stream open (fail closed)
                    _log.exception("event stream closed: authorization could not be re-checked")
                    yield _frame("close", {"reason": "unavailable"})
                    return
                try:
                    async with UnitOfWork(factory) as uow:
                        await uow.with_tenant(s.organization_id, project_id)
                        batch, after = await ProjectEventReader(uow.session, project_id, settle).read_new(position)
                except Exception:
                    _log.exception("event stream closed: history could not be read")
                    yield _frame("close", {"reason": "unavailable"})
                    return
                running = position
                for event in batch:
                    running = running.advanced([event])
                    yield _frame("event", _projection(event), cursor_for(Position(after.watermark if event is batch[-1] else running.watermark, running.seen)))
                position = after
                if len(after.seen) > MAX_TRACKED:  # the delivered batch is already out; the cursor can no longer be bounded, so the client resynchronises
                    yield _frame("gap", {"reason": "cursor_overflow", "resync": f"/api/v1/projects/{project_id}"})
                    yield _frame("close", {"reason": "resync"})
                    return
                if not batch:
                    yield b": keep-alive\n\n"
            yield _frame("close", {"reason": "max_duration"})

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    app.include_router(router)
