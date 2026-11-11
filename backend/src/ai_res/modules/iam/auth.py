# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Local authentication: login, logout, password change (Auth v1.1 §3.2, §4, §6; AUTH-003/005/007/008/013; ADR-061/062).

Properties enforced here:
* Throttling is decided BEFORE any credential check, so a refused attempt reveals nothing about the account.
* Every login path spends exactly one Argon2 verification (a decoy hash when the account/credential is missing) and returns the same 401.
* The audit row (with the operational reason) and the session are written in the SAME transaction as the decision; an audit failure aborts it.
* A presented session is revoked on login (fixation), other sessions are revoked on password change (AUTH-008).
* Nothing sensitive reaches audit `details`, exceptions or logs.
"""
import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import affected
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy, PasswordPolicyError
from ai_res.modules.iam.sessions import AuthenticatedSession, IssuedSession, RevokeReason, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, Reservation
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

log = logging.getLogger(__name__)
GENERIC_FAILURE = "Invalid credentials."


@dataclass(frozen=True, slots=True)
class LoginResult:
    session: IssuedSession
    mfa_required: bool  # an ACTIVE TOTP factor exists: the session is NOT mfa-verified until the second factor is presented


def normalise_email(email: str) -> str | None:
    value = email.strip().lower()
    return value if 3 <= len(value) <= 320 else None


def _invalid() -> ProblemError:
    return ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, GENERIC_FAILURE)


def wrong_current_password() -> ProblemError:
    """The session is valid; only the confirmation failed. 422 (not 401) so a client does not mistake it for an expired session and sign the user out (ADR-072)."""
    return ProblemError(ErrorCode.VALIDATION_ERROR, "The current password is incorrect.", errors=[{"field": "currentPassword", "reason": "invalid_current_password"}])


def rate_limited(delay: timedelta) -> ProblemError:
    seconds = max(1, int(delay.total_seconds()) + 1)
    return ProblemError(ErrorCode.RATE_LIMITED, "Too many attempts. Try again later.", headers={"Retry-After": str(seconds)})


class AuthService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], sessions: SessionService, hasher: PasswordHasherService, policy: PasswordPolicy,
                 throttle: LoginThrottle, *, clock: Callable[[], datetime] = utc_now, max_concurrent_hashes: int = 4) -> None:
        self._factory, self._sessions, self._hasher, self._policy, self._throttle, self._clock = factory, sessions, hasher, policy, throttle, clock
        # At most N Argon2 computations run at once and at most N credential transactions are open at once. The executor (not a semaphore around to_thread) bounds the
        # REAL threads, because a cancelled request stops waiting but its thread keeps running; the slot is taken BEFORE a pool connection, so waiting requests hold none.
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_hashes, thread_name_prefix="argon2")
        self._slots = asyncio.Semaphore(max_concurrent_hashes)

    async def _run(self, fn: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)

    async def _verify(self, stored: str | None, password: str) -> bool:
        """Argon2 off the event loop (tens of ms and `memory_kib` of RAM each); exactly one verification on every path (a decoy when there is no stored hash)."""
        if stored:
            return bool(await self._run(self._hasher.verify, stored, password))
        return bool(await self._run(self._hasher.verify_unknown_account, password))

    async def _hash(self, password: str) -> str:
        return str(await self._run(self._hasher.hash, password))

    @staticmethod
    def _account_key(organization_id: UUID, email_normalised: str) -> str:
        return f"{organization_id}:{email_normalised}"

    async def login(self, *, organization_id: UUID, email: str, password: str, client_ip: str, request_id: str | None,
                    replace: AuthenticatedSession | None = None) -> LoginResult:
        email_n = normalise_email(email) or ""
        account = self._account_key(organization_id, email_n)
        reservation = self._throttle.reserve(account, client_ip)  # atomic check-and-count BEFORE any await: a burst cannot slip through
        if reservation.delay is not None:
            raise rate_limited(reservation.delay)  # not audited per request (an attacker could flood the log); the transition into a block is
        result: LoginResult | None = None
        try:
            result = await self._login_in_transaction(organization_id, email_n, password, client_ip, request_id, account, reservation, replace)
        except BaseException:
            self._throttle.release(reservation)  # an infrastructure error says nothing about the credentials: do not count it against the user
            raise
        if result is None:
            raise _invalid()  # raised after the transaction committed, so the failure audit row is kept
        self._throttle.release(reservation)  # success is settled only after the commit
        return result

    async def _login_in_transaction(self, organization_id: UUID, email_n: str, password: str, client_ip: str, request_id: str | None, account: str,
                                    reservation: Reservation, replace: AuthenticatedSession | None) -> LoginResult | None:
        result: LoginResult | None = None
        async with self._slots, UnitOfWork(self._factory) as uow:
            await uow.with_tenant(organization_id)
            s = uow.session
            org_exists = (await s.execute(text("SELECT 1 FROM organization.organizations WHERE id = :o"), {"o": organization_id})).first() is not None
            row = None
            if org_exists and email_n:
                row = (await s.execute(text(
                    "SELECT u.id AS user_id, u.status, c.id AS credential_id, c.password_hash, c.row_version, "
                    "NOT EXISTS (SELECT 1 FROM organization.memberships m WHERE m.organization_id = u.organization_id AND m.user_id = u.id AND m.status <> 'ACTIVE') AS member FROM iam.users u "
                    "LEFT JOIN iam.credentials c ON c.organization_id = u.organization_id AND c.user_id = u.id AND c.kind = 'PASSWORD' "
                    "WHERE u.organization_id = :o AND u.email_normalized = :e"), {"o": organization_id, "e": email_n})).mappings().first()
            stored = row["password_hash"] if row is not None else None
            verified = await self._verify(stored, password)  # exactly one verification
            active = row is not None and row["status"] == "ACTIVE" and bool(row["member"])  # an explicitly revoked organization membership closes the door like a disabled account
            if verified and active and row is not None and stored is not None:
                if self._hasher.needs_rehash(stored):
                    await s.execute(text("UPDATE iam.credentials SET password_hash = :h, password_changed_at = password_changed_at, row_version = row_version + 1 WHERE id = :id AND row_version = :rv"),
                                    {"h": await self._hash(password), "id": row["credential_id"], "rv": row["row_version"]})
                issued = await self._sessions.create_in(s, organization_id, row["user_id"])
                if replace is not None and replace.organization_id == organization_id:
                    await self._sessions.revoke_in(s, replace.session_id, RevokeReason.ROTATED)  # fixation: same transaction as the new session
                mfa = bool((await s.execute(text("SELECT EXISTS (SELECT 1 FROM iam.mfa_factors WHERE user_id = :u AND status = 'ACTIVE')"), {"u": row["user_id"]})).scalar())
                await self._audit(s, organization_id, "AUTH_LOGIN_SUCCEEDED", AuditOutcome.SUCCEEDED, str(row["user_id"]), "SESSION", str(issued.session_id), request_id,
                                  details={"method": "password", "secondFactorPending": mfa})
                result = LoginResult(issued, mfa)
            else:
                if org_exists:
                    reason = "unknown_account" if row is None else ("account_disabled" if not active else "invalid_credentials")
                    actor = None if row is None else str(row["user_id"])
                    await self._audit(s, organization_id, "AUTH_LOGIN_FAILED", AuditOutcome.DENIED, actor, "USER", actor, request_id, reason=reason, details={"method": "password"})
                    if reservation.newly_blocked:
                        await self._audit(s, organization_id, "AUTH_RATE_LIMITED", AuditOutcome.DENIED, actor, "USER", actor, request_id, reason="progressive_delay", details={"scope": "login"})
                    if reservation.signal:  # ip/global threshold crossed: an alert signal, nobody is refused because of it (ADR-071)
                        await self._audit(s, organization_id, "AUTH_RATE_LIMITED", AuditOutcome.FAILED, actor, "USER", actor, request_id, reason=f"{reservation.signal}_threshold_signal", details={"scope": "login"})
        if result is not None and replace is not None and replace.organization_id != organization_id:
            try:  # the login already committed: a failure here must not turn it into a 500 without a cookie (the presented session still expires on its own)
                await self._sessions.revoke(replace.organization_id, replace.session_id, RevokeReason.ROTATED)  # cookie of another organization: separate transaction
            except Exception:
                log.exception("revoking a presented session of another organization failed after a successful login")
        return result

    async def logout(self, current: AuthenticatedSession, *, request_id: str | None) -> None:
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(current.organization_id)
            await self._sessions.revoke_in(uow.session, current.session_id, RevokeReason.LOGOUT)
            await self._audit(uow.session, current.organization_id, "AUTH_LOGOUT", AuditOutcome.SUCCEEDED, str(current.user_id), "SESSION", str(current.session_id), request_id)

    async def change_password(self, current: AuthenticatedSession, *, current_password: str, new_password: str, client_ip: str, request_id: str | None) -> None:
        """Re-authenticates with the current password (Auth v1.1 §3.2), applies the password policy, replaces the hash with a CAS and revokes every OTHER session."""
        account = f"pwchange:{current.organization_id}:{current.user_id}"
        reservation = self._throttle.reserve(account, client_ip)
        if reservation.delay is not None:
            raise rate_limited(reservation.delay)
        failed = False
        try:
            async with self._slots, UnitOfWork(self._factory) as uow:
                await uow.with_tenant(current.organization_id)
                s = uow.session
                row = (await s.execute(text("SELECT id, password_hash, row_version FROM iam.credentials WHERE user_id = :u AND kind = 'PASSWORD'"), {"u": current.user_id})).mappings().first()
                stored = row["password_hash"] if row is not None else None
                verified = await self._verify(stored, current_password)
                if not verified or row is None:
                    await self._audit(s, current.organization_id, "AUTH_PASSWORD_CHANGED", AuditOutcome.DENIED, str(current.user_id), "USER", str(current.user_id), request_id, reason="invalid_current_password")
                    failed = True
                else:
                    try:
                        self._policy.check(new_password)
                    except PasswordPolicyError as exc:
                        raise ProblemError(ErrorCode.VALIDATION_ERROR, "The new password does not meet the password policy.", errors=[{"field": "newPassword", "reason": exc.reason}]) from None
                    r = await s.execute(text("UPDATE iam.credentials SET password_hash = :h, password_changed_at = :now, row_version = row_version + 1 WHERE id = :id AND row_version = :rv"),
                                        {"h": await self._hash(new_password), "now": require_utc(self._clock()), "id": row["id"], "rv": row["row_version"]})
                    if affected(r) != 1:
                        raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "The credential changed concurrently; retry.")
                    revoked = await self._sessions.revoke_all_for_user_in(s, current.user_id, RevokeReason.CREDENTIALS_CHANGED, except_session_id=current.session_id)
                    await self._audit(s, current.organization_id, "AUTH_PASSWORD_CHANGED", AuditOutcome.SUCCEEDED, str(current.user_id), "USER", str(current.user_id), request_id,
                                      details={"otherDevicesSignedOut": revoked})
        except BaseException:
            self._throttle.release(reservation)  # right current password but policy/CAS/infrastructure error: not a guessing attempt
            raise
        if failed:
            raise wrong_current_password()
        self._throttle.release(reservation)

    async def reauthenticate(self, current: AuthenticatedSession, *, password: str, purpose: str, client_ip: str, request_id: str | None) -> None:
        """Fresh proof of the password before a sensitive step (NIST 800-63B §6.1.2; ADR-072). Throttled; the outcome is audited; wrong password -> 422."""
        account = f"reauth:{current.organization_id}:{current.user_id}"
        reservation = self._throttle.reserve(account, client_ip)
        if reservation.delay is not None:
            raise rate_limited(reservation.delay)
        ok = False
        try:
            async with self._slots, UnitOfWork(self._factory) as uow:
                await uow.with_tenant(current.organization_id)
                row = (await uow.session.execute(text("SELECT password_hash FROM iam.credentials WHERE user_id = :u AND kind = 'PASSWORD'"), {"u": current.user_id})).mappings().first()
                ok = await self._verify(row["password_hash"] if row is not None else None, password) and row is not None
                await self._audit(uow.session, current.organization_id, "AUTH_REAUTHENTICATED", AuditOutcome.SUCCEEDED if ok else AuditOutcome.DENIED, str(current.user_id), "USER",
                                  str(current.user_id), request_id, reason=None if ok else "invalid_current_password", details={"purpose": purpose})
        except BaseException:
            self._throttle.release(reservation)
            raise
        if not ok:
            raise wrong_current_password()
        self._throttle.release(reservation)

    async def _audit(self, s: AsyncSession, organization_id: UUID, action: str, outcome: AuditOutcome, actor_id: str | None, object_type: str, object_id: str | None,
                     request_id: str | None, *, reason: str | None = None, details: dict[str, Any] | None = None) -> None:
        await SqlAuditWriter(s).write(AuditRecord(action=action, outcome=outcome, resource_type=object_type, resource_id=object_id, actor_id=actor_id, organization_id=str(organization_id),
                                                  request_id=request_id, reason_code=reason, details=details), occurred_at=self._clock())
