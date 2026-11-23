"""Personal workspace feed and versioned analyst preferences (ADR-182)."""
import base64
import hmac
import json
from asyncio import timeout
from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_res.api.identity import IdentityServices
from ai_res.application.notification_delivery import (
    NotificationDelivery,
    NotificationItem,
    NotificationPosition,
    NotificationPreference,
    NotificationSchedule,
    ProjectNotifications,
    Seconds,
    read_delivery_candidates,
    read_preference,
    set_notification_recipient,
    write_preference,
)
from ai_res.application.proactive_messages import NotificationScope
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.secretbox import SecretBox, SecretBoxError
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.readmodel.queries import parse_ts_keyset
from ai_res.platform.boundary import read_bounded_body
from ai_res.platform.concurrency import format_etag, parse_if_match
from ai_res.platform.correlation import current_request_id
from ai_res.platform.pagination import InvalidCursor, KeyRing, decode_cursor, encode_cursor, validate_limit
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError

_PREFERENCE_ACTION = "notification.preference.manage"
_FEED_AUDIENCE = "listProjectNotifications"
_CURSOR_CONTEXT = b"ai-res.workspace.notification.cursor.v1"
_MAX_FEED_CANDIDATES = 32  # at most two exact Policy evaluations per candidate
_MAX_PREFERRED_BODY_BYTES = 256
_PREFERENCE_BODY_TIMEOUT_SECONDS = 10


class NotificationPreferenceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_seconds: Seconds = Field(alias="intervalSeconds")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _delivery_response(delivery: NotificationDelivery) -> dict[str, Any]:
    return {
        "id": str(delivery.id),
        "kind": "MANDATORY" if delivery.items[0].proposal_version_id is None else "DIGEST",
        "publishedAt": _timestamp(delivery.published_at),
        "items": [{
            "eventId": str(item.event_id),
            "occurredAt": _timestamp(item.occurred_at),
            "operationId": str(item.operation_id),
            "proposalVersionId": None if item.proposal_version_id is None else str(item.proposal_version_id),
        } for item in delivery.items],
    }


def _cursor_box(ring: KeyRing) -> SecretBox:
    # Existing cursor signatures authenticate scope and expiry; this purpose-specific key protects the position.
    return SecretBox(ring.active_id, {kid: hmac.digest(key, _CURSOR_CONTEXT, "sha256") for kid, key in ring.keys.items()})


def _seal_position(ring: KeyRing, pos: NotificationPosition) -> str:
    value = [_timestamp(pos.published_at), str(pos.delivery_id), _timestamp(pos.occurred_at), str(pos.event_id)]
    return base64.urlsafe_b64encode(_cursor_box(ring).seal(json.dumps(value).encode(), _CURSOR_CONTEXT)).decode()


def _open_position(ring: KeyRing, keyset: list[Any]) -> NotificationPosition:
    try:
        if len(keyset) != 1 or not isinstance(keyset[0], str):
            raise ValueError
        payload = _cursor_box(ring).open(base64.b64decode(keyset[0], altchars=b"-_", validate=True), _CURSOR_CONTEXT)
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError
        published, delivery = parse_ts_keyset(data[:2])
        occurred, event = parse_ts_keyset(data[2:])
        if published is None or delivery is None or occurred is None or event is None:
            raise ValueError
        return NotificationPosition(published, delivery, occurred, event)
    except (SecretBoxError, ValueError, TypeError) as exc:
        raise InvalidCursor from exc


def _preference_response(pref: NotificationPreference, options: ProjectNotifications, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = format_etag(pref.version)
    return {"selectedIntervalSeconds": pref.selected, "allowedIntervalSeconds": sorted(options.digest_intervals_seconds)}


def _policy(
    session: AuthenticatedSession, project_id: UUID, action: str, resource_type: str, resource_id: UUID | None,
) -> PolicyRequest:
    return PolicyRequest(
        actor_id=str(session.user_id), action=action, resource_type=resource_type, resource_id=str(resource_id) if resource_id is not None else None,
        organization_id=str(session.organization_id), project_id=str(project_id),
        attributes={"mfa_verified": session.mfa_verified_at is not None},
    )


def register_notification_api(app: FastAPI, services: IdentityServices, schedule: NotificationSchedule) -> None:
    if services.current_session is None or services.origin_guard is None:
        raise RuntimeError("Register identity before the notification API")
    config = services.enforcer.config
    if config is None or _PREFERENCE_ACTION not in config.actions or config.actions[_PREFERENCE_ACTION].resource_type != "PROJECT":
        raise RuntimeError("Policy is missing the notification preference action")

    by_project = {(p.organization_id, p.project_id): p for p in schedule.projects}
    router = APIRouter(prefix="/api/v1")
    Session = Annotated[AuthenticatedSession, Depends(services.current_session)]
    OriginGuard = Annotated[None, Depends(services.origin_guard)]
    IfMatch = Annotated[str | None, Header(alias="If-Match")]
    Limit = Annotated[int | None, Query()]
    Cursor = Annotated[str | None, Query()]

    def options_for(s: AuthenticatedSession, project_id: UUID) -> ProjectNotifications:
        options = by_project.get((s.organization_id, project_id))
        if options is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        return options

    @router.get("/projects/{project_id}/notification-preferences", operation_id="getProjectNotificationPreferences")
    async def get_preference(project_id: UUID, response: Response, s: Session) -> dict[str, Any]:
        request = _policy(s, project_id, _PREFERENCE_ACTION, "PROJECT", project_id)
        decision = await services.enforcer.decide(request, conceal=True)
        options = options_for(s, project_id)
        async with UnitOfWork(services.factory) as uow:
            await set_notification_recipient(uow, NotificationScope(s.organization_id, project_id, s.user_id))
            await services.enforcer.record_allow(request, decision, session=uow.session)
            return _preference_response(await read_preference(uow.session), options, response)

    @router.put("/projects/{project_id}/notification-preferences", operation_id="setProjectNotificationPreferences")
    async def put_preference(
        project_id: UUID, request: Request, response: Response, s: Session,
        _: OriginGuard, if_match: IfMatch = None,
    ) -> dict[str, Any]:
        authorization = _policy(s, project_id, _PREFERENCE_ACTION, "PROJECT", project_id)
        await services.enforcer.decide(authorization, conceal=True)
        options = options_for(s, project_id)
        expected = parse_if_match(if_match)
        try:
            async with timeout(_PREFERENCE_BODY_TIMEOUT_SECONDS):
                raw = await read_bounded_body(request, _MAX_PREFERRED_BODY_BYTES)
            body = NotificationPreferenceChoice.model_validate_json(raw)
        except (TimeoutError, ValidationError):
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid notification preference.") from None
        if body.interval_seconds not in options.digest_intervals_seconds:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Choose a configured delivery frequency.",
                               errors=[{"field": "intervalSeconds", "reason": "not_configured"}])
        scope = NotificationScope(s.organization_id, project_id, s.user_id)
        async with UnitOfWork(services.factory) as uow:
            await set_notification_recipient(uow, scope, lock=True)
            await services.enforcer.lock_subject_grants(uow.session, s.user_id, s.organization_id, project_id)
            mfa_verified = await lock_authenticated_session(uow.session, s)
            await services.enforcer.authorize(
                replace(authorization, attributes={"mfa_verified": mfa_verified}), session=uow.session, conceal=True,
            )
            pref = await write_preference(
                uow.session, scope, selected=body.interval_seconds, expected=expected, request_id=current_request_id(),
            )
        return _preference_response(pref, options, response)

    async def visible_item(s: AuthenticatedSession, project_id: UUID, item: NotificationItem) -> bool:
        checks = [_policy(s, project_id, "operation.read", "OPERATION", item.operation_id)]
        if item.proposal_version_id is not None:
            checks.append(_policy(s, project_id, "manager.proposal.read", "MANAGER_PROPOSAL_VERSION", item.proposal_version_id))
        decisions = []
        try:
            for check in checks:
                decisions.append(await services.enforcer.decide(check, conceal=True))
        except ProblemError as exc:
            if exc.code is not ErrorCode.RESOURCE_NOT_FOUND:
                raise
            return False
        async with UnitOfWork(services.factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            for check, decision in zip(checks, decisions, strict=True):
                await services.enforcer.record_allow(check, decision, session=uow.session)
        return True

    @router.get("/projects/{project_id}/notifications", operation_id=_FEED_AUDIENCE)
    async def list_notifications(
        project_id: UUID, request: Request, response: Response, s: Session, limit: Limit = None, cursor: Cursor = None,
    ) -> dict[str, Any]:
        size = validate_limit(limit, 25)
        if size > 100:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "limit out of range.", errors=[{"field": "limit", "reason": "range"}])
        filters = {"org": str(s.organization_id), "project": str(project_id)}
        subject = str(s.user_id)
        ring = getattr(request.app.state, "cursor_key_ring", None)
        after = None
        if cursor:
            if not isinstance(ring, KeyRing):
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Pagination is not configured.")
            values = decode_cursor(ring, cursor, subject=subject, audience=_FEED_AUDIENCE, filters=filters)
            after = _open_position(ring, values)

        project_access = _policy(s, project_id, "project.read", "PROJECT", project_id)
        decision = await services.enforcer.decide(project_access, conceal=True)
        options_for(s, project_id)
        scope = NotificationScope(s.organization_id, project_id, s.user_id)
        # A former analyst should not need to scan proposal deliveries to reach a visible failure.
        proposal_access = _policy(s, project_id, "manager.proposal.read", "MANAGER_PROPOSAL_VERSION", None)
        include_digests = True
        try:
            await services.enforcer.decide(proposal_access, conceal=True)
        except ProblemError as exc:
            if exc.code is not ErrorCode.RESOURCE_NOT_FOUND:
                raise
            include_digests = False

        async with UnitOfWork(services.factory) as uow:
            await set_notification_recipient(uow, scope)
            await services.enforcer.record_allow(project_access, decision, session=uow.session)
            rows = await read_delivery_candidates(
                uow.session, scope, before=after, include_digests=include_digests, limit=_MAX_FEED_CANDIDATES + 1,
            )
        has_more = len(rows) > _MAX_FEED_CANDIDATES
        last = None
        visible: dict[tuple[UUID, datetime], list[NotificationItem]] = {}
        for position, item in rows[:_MAX_FEED_CANDIDATES]:
            if item is not None and await visible_item(s, project_id, item):
                delivery_key = (position.delivery_id, position.published_at)
                if len(visible) == size and delivery_key not in visible:
                    has_more = True
                    break
                visible.setdefault(delivery_key, []).append(item)
            last = position

        next_cursor = None
        if has_more and last is not None:
            if not isinstance(ring, KeyRing):
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Pagination is not configured.")
            next_cursor = encode_cursor(
                ring, subject=subject, audience=_FEED_AUDIENCE, filters=filters,
                keyset=[_seal_position(ring, last)], ttl_seconds=services.settings.cursor_ttl_seconds,
            )
        response.headers["Cache-Control"] = "no-store"
        data = [_delivery_response(NotificationDelivery(did, published, tuple(items))) for (did, published), items in visible.items()]
        return {"data": data, "page": {"hasMore": has_more, "nextCursor": next_cursor}}

    app.include_router(router)
