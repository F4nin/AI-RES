# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Server-side opaque sessions in PostgreSQL (Auth v1.1 §6, AUTH-007/008, ADR-062).

Tokens: see `tokens.py`. Every read/write runs in a Unit of Work with the transaction-local tenant context chosen from the token's organization hint;
`iam.sessions` is FORCE-RLS, so a forged hint finds nothing. Expiry is judged against the injected clock; the database stores only digests.
Revocation is write-once (trigger); rotation never extends the absolute lifetime fixed at login.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import affected
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.tokens import csrf_digest, csrf_token_for, new_session_token, parse_session_token, session_digest
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError


class RevokeReason(StrEnum):
    LOGOUT = "LOGOUT"
    ROTATED = "ROTATED"
    CREDENTIALS_CHANGED = "CREDENTIALS_CHANGED"  # the user replaced their password (AUTH-008)
    USER_DISABLED = "USER_DISABLED"
    ROLE_REVOKED = "ROLE_REVOKED"
    MFA_RESET = "MFA_RESET"
    ADMIN_REVOKED = "ADMIN_REVOKED"


class AuthFailure(StrEnum):
    """Why a session was refused. For audit and tests only: the client always receives the same 401."""
    MALFORMED = "malformed"
    UNKNOWN = "unknown"
    REVOKED = "revoked"
    IDLE_EXPIRED = "idle_expired"
    ABSOLUTE_EXPIRED = "absolute_expired"
    USER_DISABLED = "user_disabled"
    MEMBERSHIP_REVOKED = "membership_revoked"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str = field(repr=False)  # returned once, set as the HttpOnly cookie; never stored or logged
    csrf_token: str = field(repr=False)
    session_id: UUID
    organization_id: UUID
    user_id: UUID
    idle_expires_at: datetime
    absolute_expires_at: datetime
    mfa_verified_at: datetime | None


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session_id: UUID
    organization_id: UUID
    user_id: UUID
    mfa_verified_at: datetime | None
    idle_expires_at: datetime
    absolute_expires_at: datetime
    csrf_token: str  # derived from the presented token (see tokens.py)
    csrf_digest: bytes
    second_factor_pending: bool = False  # an ACTIVE factor exists but this session has not presented it: usable ONLY to complete MFA or sign out


@dataclass(frozen=True, slots=True)
class SessionAuthResult:
    session: AuthenticatedSession | None
    failure: AuthFailure | None


class SessionService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], *, idle: timedelta, absolute: timedelta, touch_interval: timedelta,
                 clock: Callable[[], datetime] = utc_now) -> None:
        if idle <= timedelta(0) or absolute < idle or touch_interval <= timedelta(0):
            raise ValueError("invalid session timing: 0 < idle <= absolute and touch_interval > 0")
        self._factory, self._idle, self._absolute, self._touch, self._clock = factory, idle, absolute, touch_interval, clock

    def _uow(self) -> UnitOfWork:
        return UnitOfWork(self._factory)

    async def create(self, organization_id: UUID, user_id: UUID, *, mfa_verified: bool = False) -> IssuedSession:
        async with self._uow() as uow:
            await uow.with_tenant(organization_id)
            return await self.create_in(uow.session, organization_id, user_id, mfa_verified=mfa_verified)

    async def create_in(self, s: AsyncSession, organization_id: UUID, user_id: UUID, *, mfa_verified: bool = False) -> IssuedSession:
        """Joins the caller's transaction (tenant context must already be set): the session and its audit row commit or roll back together."""
        now = require_utc(self._clock())
        return await self._insert(s, organization_id, user_id, now, absolute=now + self._absolute, mfa_verified_at=now if mfa_verified else None)

    async def _insert(self, s: AsyncSession, org: UUID, user: UUID, now: datetime, *, absolute: datetime, mfa_verified_at: datetime | None) -> IssuedSession:
        token = new_session_token(org)
        csrf = csrf_token_for(token)
        idle = min(now + self._idle, absolute)
        sid = new_id()
        await s.execute(text(
            "INSERT INTO iam.sessions (id, organization_id, user_id, session_digest, csrf_digest, last_seen_at, idle_expires_at, absolute_expires_at, mfa_verified_at) "
            "VALUES (:id, :org, :uid, :sd, :cd, :now, :idle, :abs, :mfa)"),
            {"id": sid, "org": org, "uid": user, "sd": session_digest(token), "cd": csrf_digest(csrf), "now": now, "idle": idle, "abs": absolute, "mfa": mfa_verified_at})
        return IssuedSession(token, csrf, sid, org, user, idle, absolute, mfa_verified_at)

    async def authenticate(self, token: str) -> SessionAuthResult:
        parsed = parse_session_token(token)
        if parsed is None:
            return SessionAuthResult(None, AuthFailure.MALFORMED)
        now = require_utc(self._clock())
        async with self._uow() as uow:
            await uow.with_tenant(parsed.organization_id)  # lookup hint only; authority is the digest match below
            row = (await uow.session.execute(text(
                "SELECT s.id, s.organization_id, s.user_id, s.csrf_digest, s.last_seen_at, s.idle_expires_at, s.absolute_expires_at, s.mfa_verified_at, s.revoked_at, s.row_version, "
                "u.status AS user_status, EXISTS (SELECT 1 FROM iam.mfa_factors f WHERE f.organization_id = s.organization_id AND f.user_id = s.user_id AND f.status = 'ACTIVE') AS mfa_enrolled, "
                "NOT EXISTS (SELECT 1 FROM organization.memberships m WHERE m.organization_id = s.organization_id AND m.user_id = s.user_id AND m.status <> 'ACTIVE') AS org_member "
                "FROM iam.sessions s JOIN iam.users u ON u.organization_id = s.organization_id AND u.id = s.user_id WHERE s.session_digest = :d"),
                {"d": session_digest(token)})).mappings().first()
            if row is None:
                return SessionAuthResult(None, AuthFailure.UNKNOWN)
            if row["revoked_at"] is not None:
                return SessionAuthResult(None, AuthFailure.REVOKED)
            if now >= row["absolute_expires_at"]:
                return SessionAuthResult(None, AuthFailure.ABSOLUTE_EXPIRED)
            if now >= row["idle_expires_at"]:
                return SessionAuthResult(None, AuthFailure.IDLE_EXPIRED)
            if row["user_status"] != "ACTIVE":
                return SessionAuthResult(None, AuthFailure.USER_DISABLED)
            if not row["org_member"]:
                return SessionAuthResult(None, AuthFailure.MEMBERSHIP_REVOKED)  # a revoked membership ends access even if the session row survived
            idle_expires = row["idle_expires_at"]
            if now - row["last_seen_at"] >= self._touch:
                idle_expires = min(now + self._idle, row["absolute_expires_at"])
                # CAS on row_version: a concurrent touch/revoke wins and this extension is simply skipped (never resurrects a revoked row).
                touched = await uow.session.execute(text(
                    "UPDATE iam.sessions SET last_seen_at = :now, idle_expires_at = :idle, row_version = row_version + 1 WHERE id = :id AND row_version = :rv AND revoked_at IS NULL"),
                    {"now": now, "idle": idle_expires, "id": row["id"], "rv": row["row_version"]})
                if affected(touched) != 1:
                    idle_expires = row["idle_expires_at"]  # lost the CAS: report what the database really holds, not an extension that never happened
            return SessionAuthResult(AuthenticatedSession(row["id"], row["organization_id"], row["user_id"], row["mfa_verified_at"], idle_expires,
                                                           row["absolute_expires_at"], csrf_token_for(token), bytes(row["csrf_digest"]),
                                                           second_factor_pending=bool(row["mfa_enrolled"]) and row["mfa_verified_at"] is None), None)

    async def rotate(self, current: AuthenticatedSession, *, mfa_verified: bool = False) -> IssuedSession:
        """New id after login/MFA/privilege change (fixation defence). The absolute lifetime fixed at login is kept: rotation does not extend it."""
        async with self._uow() as uow:
            await uow.with_tenant(current.organization_id)
            return await self.rotate_in(uow.session, current, mfa_verified=mfa_verified)

    async def rotate_in(self, s: AsyncSession, current: AuthenticatedSession, *, mfa_verified: bool = False) -> IssuedSession:
        now = require_utc(self._clock())
        if not await self._revoke_one(s, current.session_id, RevokeReason.ROTATED, now):
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")  # lost a race with revoke/logout: no replacement is minted
        return await self._insert(s, current.organization_id, current.user_id, now, absolute=current.absolute_expires_at,
                                  mfa_verified_at=now if mfa_verified else current.mfa_verified_at)

    async def revoke(self, organization_id: UUID, session_id: UUID, reason: RevokeReason) -> bool:
        async with self._uow() as uow:
            await uow.with_tenant(organization_id)
            return await self.revoke_in(uow.session, session_id, reason)

    async def revoke_in(self, s: AsyncSession, session_id: UUID, reason: RevokeReason) -> bool:
        return await self._revoke_one(s, session_id, reason, require_utc(self._clock()))

    async def revoke_all_for_user(self, organization_id: UUID, user_id: UUID, reason: RevokeReason, *, except_session_id: UUID | None = None) -> int:
        async with self._uow() as uow:
            await uow.with_tenant(organization_id)
            return await self.revoke_all_for_user_in(uow.session, user_id, reason, except_session_id=except_session_id)

    async def revoke_all_for_user_in(self, s: AsyncSession, user_id: UUID, reason: RevokeReason, *, except_session_id: UUID | None = None) -> int:
        r = await s.execute(text(
            "UPDATE iam.sessions SET revoked_at = :now, revoked_reason = :reason, row_version = row_version + 1 "
            "WHERE user_id = :uid AND revoked_at IS NULL AND (CAST(:keep AS uuid) IS NULL OR id <> CAST(:keep AS uuid))"),
            {"now": require_utc(self._clock()), "reason": reason.value, "uid": user_id, "keep": except_session_id})
        return affected(r)

    @staticmethod
    async def _revoke_one(s: AsyncSession, session_id: UUID, reason: RevokeReason, now: datetime) -> bool:
        r = await s.execute(text(
            "UPDATE iam.sessions SET revoked_at = :now, revoked_reason = :reason, row_version = row_version + 1 WHERE id = :id AND revoked_at IS NULL"),
            {"now": now, "reason": reason.value, "id": session_id})
        return affected(r) == 1
