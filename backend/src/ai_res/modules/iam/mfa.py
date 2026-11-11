# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""TOTP MFA and one-time recovery codes (Auth v1.1 §5, AUTH-006; Secrets v1.1).

* The seed is encrypted (AES-256-GCM, bound to org/user/factor) and shown ONCE at enrolment; recovery codes are shown once and stored only as digests.
* Replay: the accepting UPDATE is a compare-and-set on `last_used_step` (monotonic, also enforced by a trigger), so parallel submissions of one code
  succeed at most once. A recovery code is consumed by `UPDATE ... WHERE used_at IS NULL`.
* Attempts share the login throttle (key `mfa:<org>:<user>`) and are refused BEFORE any code is checked.
* A successful second factor, and enrolment, rotate the session id and mark it mfa-verified (privilege elevation).
* Reset is a privileged procedure: the CALLER must have authorised it through the Policy Engine; this service performs and audits it.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import affected
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.iam.accounts import ensure_may_act_on
from ai_res.modules.iam.auth import rate_limited
from ai_res.modules.iam.secretbox import SecretBox, SecretBoxError
from ai_res.modules.iam.sessions import AuthenticatedSession, IssuedSession, RevokeReason, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, Reservation
from ai_res.modules.iam.totp import generate_recovery_codes, is_totp_shape, match_totp_step, new_totp_secret, provisioning_uri, recovery_digest
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

RECOVERY_CODE_COUNT = 10  # WORKING


@dataclass(frozen=True, slots=True)
class Enrollment:
    secret: str = field(repr=False)  # shown once so the user can add it to an authenticator; never stored in clear
    otpauth_uri: str = field(repr=False)  # embeds the secret


@dataclass(frozen=True, slots=True)
class ConfirmedEnrollment:
    session: IssuedSession  # rotated, mfa-verified
    recovery_codes: list[str] = field(repr=False)  # shown once


def _bad_code() -> ProblemError:
    return ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Invalid verification code.")


def _aad(org: UUID, user: UUID, factor: UUID) -> bytes:
    return f"mfa-totp:{org}:{user}:{factor}".encode()


class MfaService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], sessions: SessionService, box: SecretBox, throttle: LoginThrottle, *, issuer: str, window: int,
                 clock: Callable[[], datetime] = utc_now) -> None:
        self._factory, self._sessions, self._box, self._throttle, self._issuer, self._window, self._clock = factory, sessions, box, throttle, issuer, window, clock

    # ---------- enrolment ----------
    async def begin_enrollment(self, current: AuthenticatedSession, *, request_id: str | None) -> Enrollment:
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(current.organization_id)
            s = uow.session
            if (await s.execute(text("SELECT 1 FROM iam.mfa_factors WHERE user_id = :u AND status = 'ACTIVE'"), {"u": current.user_id})).first() is not None:
                raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "A second factor is already enrolled; changing it requires the reset procedure.")
            await s.execute(text("UPDATE iam.mfa_factors SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = :u AND status = 'PENDING'"), {"u": current.user_id})
            email = (await s.execute(text("SELECT email FROM iam.users WHERE id = :u"), {"u": current.user_id})).scalar_one()
            secret, factor = new_totp_secret(), new_id()
            await s.execute(text("INSERT INTO iam.mfa_factors (id, organization_id, user_id, factor_type, secret_ciphertext, status) VALUES (:id, :o, :u, 'TOTP', :c, 'PENDING')"),
                            {"id": factor, "o": current.organization_id, "u": current.user_id, "c": self._box.seal(secret.encode(), _aad(current.organization_id, current.user_id, factor))})
            await self._audit(s, current, "AUTH_MFA_ENROLLMENT_STARTED", AuditOutcome.SUCCEEDED, request_id)
        return Enrollment(secret, provisioning_uri(secret, email, self._issuer))

    async def confirm_enrollment(self, current: AuthenticatedSession, code: str, *, client_ip: str, request_id: str | None) -> ConfirmedEnrollment:
        account = self._account(current)
        reservation = self._reserve(account, client_ip)
        failed = False
        result: ConfirmedEnrollment | None = None
        try:
            result, failed = await self._confirm_in_transaction(current, code, reservation, request_id)
        except BaseException:
            self._throttle.release(reservation)
            raise
        if failed or result is None:
            raise _bad_code()
        self._throttle.release(reservation)
        return result

    async def _confirm_in_transaction(self, current: AuthenticatedSession, code: str, reservation: Reservation, request_id: str | None) -> tuple[ConfirmedEnrollment | None, bool]:
        failed = False
        result: ConfirmedEnrollment | None = None
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(current.organization_id)
            s = uow.session
            row = (await s.execute(text("SELECT id, secret_ciphertext FROM iam.mfa_factors WHERE user_id = :u AND status = 'PENDING'"), {"u": current.user_id})).mappings().first()
            step = None if row is None else self._match(row, current, code)
            ok = False
            if row is not None and step is not None:
                r = await s.execute(text("UPDATE iam.mfa_factors SET status = 'ACTIVE', confirmed_at = :now, last_used_step = :step, row_version = row_version + 1 "
                                         "WHERE id = :id AND status = 'PENDING'"), {"now": require_utc(self._clock()), "step": step, "id": row["id"]})
                ok = affected(r) == 1
            if ok:
                codes = await self._issue_recovery_codes(s, current)
                issued = await self._sessions.rotate_in(s, current, mfa_verified=True)
                await self._audit(s, current, "AUTH_MFA_ENROLLED", AuditOutcome.SUCCEEDED, request_id)
                result = ConfirmedEnrollment(issued, codes)
            else:
                failed = True
                await self._fail(s, current, reservation, "AUTH_MFA_ENROLLED", "invalid_code", request_id)
        return result, failed

    # ---------- second factor at login ----------
    async def verify(self, current: AuthenticatedSession, code: str, *, client_ip: str, request_id: str | None) -> IssuedSession:
        account = self._account(current)
        reservation = self._reserve(account, client_ip)
        try:
            issued = await self._verify_in_transaction(current, code, reservation, request_id)
        except BaseException:
            self._throttle.release(reservation)
            raise
        if issued is None:
            raise _bad_code()
        self._throttle.release(reservation)
        return issued

    async def _verify_in_transaction(self, current: AuthenticatedSession, code: str, reservation: Reservation, request_id: str | None) -> IssuedSession | None:
        issued: IssuedSession | None = None
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(current.organization_id)
            s = uow.session
            factor = (await s.execute(text("SELECT id, secret_ciphertext FROM iam.mfa_factors WHERE user_id = :u AND status = 'ACTIVE'"), {"u": current.user_id})).mappings().first()
            method, reason = "totp", "no_active_factor"
            if factor is not None:
                if is_totp_shape(code):
                    step = self._match(factor, current, code)
                    reason = "invalid_code"
                    if step is not None:
                        r = await s.execute(text("UPDATE iam.mfa_factors SET last_used_step = :step, row_version = row_version + 1 "
                                                 "WHERE id = :id AND status = 'ACTIVE' AND (last_used_step IS NULL OR last_used_step < :step)"), {"step": step, "id": factor["id"]})
                        reason = "" if affected(r) == 1 else "code_replayed"
                else:
                    method, reason = "recovery", "invalid_code"
                    r = await s.execute(text("UPDATE iam.mfa_recovery_codes SET used_at = :now, row_version = row_version + 1 WHERE user_id = :u AND code_digest = :d AND used_at IS NULL"),
                                        {"now": require_utc(self._clock()), "u": current.user_id, "d": recovery_digest(code)})
                    reason = "" if affected(r) == 1 else "invalid_code"
            if factor is not None and reason == "":
                issued = await self._sessions.rotate_in(s, current, mfa_verified=True)
                await self._audit(s, current, "AUTH_MFA_RECOVERY_USED" if method == "recovery" else "AUTH_MFA_VERIFIED", AuditOutcome.SUCCEEDED, request_id, details={"method": method})
            else:
                await self._fail(s, current, reservation, "AUTH_MFA_FAILED", reason, request_id, details={"method": method})
        return issued

    # ---------- recovery codes / reset ----------
    async def regenerate_recovery_codes(self, current: AuthenticatedSession, *, request_id: str | None) -> list[str]:
        if current.mfa_verified_at is None:
            raise ProblemError(ErrorCode.ACCESS_DENIED, "Second-factor verification is required.", errors=[{"field": "session", "reason": "mfa_required"}])
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(current.organization_id)
            s = uow.session
            await s.execute(text("UPDATE iam.mfa_recovery_codes SET used_at = :now, row_version = row_version + 1 WHERE user_id = :u AND used_at IS NULL"),
                            {"now": require_utc(self._clock()), "u": current.user_id})  # superseded codes are marked used: rows are never deleted
            codes = await self._issue_recovery_codes(s, current)
            await self._audit(s, current, "AUTH_MFA_RECOVERY_CODES_REGENERATED", AuditOutcome.SUCCEEDED, request_id)
        return codes

    async def reset(self, organization_id: UUID, user_id: UUID, *, actor_id: UUID, request_id: str | None) -> None:
        """Privileged: removes every factor and recovery code of `user_id` and ends all of that user's sessions. Authorisation is the caller's (Policy Engine)."""
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(organization_id)
            s = uow.session
            now = require_utc(self._clock())
            await ensure_may_act_on(s, self._factory, organization_id, actor_id, user_id, action="iam.user.mfa_reset")
            if (await s.execute(text("SELECT 1 FROM iam.users WHERE organization_id = :o AND id = :u"), {"o": organization_id, "u": user_id})).first() is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")  # unknown or another organization's user: no success audit row
            await s.execute(text("UPDATE iam.mfa_factors SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = :u AND status <> 'REVOKED'"), {"u": user_id})
            await s.execute(text("UPDATE iam.mfa_recovery_codes SET used_at = :now, row_version = row_version + 1 WHERE user_id = :u AND used_at IS NULL"), {"now": now, "u": user_id})
            await self._sessions.revoke_all_for_user_in(s, user_id, RevokeReason.MFA_RESET)
            await SqlAuditWriter(s).write(AuditRecord(action="AUTH_MFA_RESET", outcome=AuditOutcome.SUCCEEDED, resource_type="USER", resource_id=str(user_id), actor_id=str(actor_id),
                                                      organization_id=str(organization_id), request_id=request_id), occurred_at=self._clock())

    # ---------- helpers ----------
    @staticmethod
    def _account(current: AuthenticatedSession) -> str:
        return f"mfa:{current.organization_id}:{current.user_id}"

    def _reserve(self, account: str, ip: str) -> Reservation:
        """Atomic check-and-count before the code is examined (a burst of guesses cannot all pass the gate); `release` after a correct code."""
        reservation = self._throttle.reserve(account, ip)
        if reservation.delay is not None:
            raise rate_limited(reservation.delay)
        return reservation

    def _match(self, factor: Any, current: AuthenticatedSession, code: str) -> int | None:
        try:
            secret = self._box.open(bytes(factor["secret_ciphertext"]), _aad(current.organization_id, current.user_id, factor["id"])).decode()
        except SecretBoxError:
            return None  # an undecryptable seed never authenticates; treated as a failed attempt
        return match_totp_step(secret, code, require_utc(self._clock()), window=self._window)

    async def _issue_recovery_codes(self, s: AsyncSession, current: AuthenticatedSession) -> list[str]:
        codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
        for code in codes:
            await s.execute(text("INSERT INTO iam.mfa_recovery_codes (id, organization_id, user_id, code_digest) VALUES (:id, :o, :u, :d)"),
                            {"id": new_id(), "o": current.organization_id, "u": current.user_id, "d": recovery_digest(code)})
        return codes

    async def _fail(self, s: AsyncSession, current: AuthenticatedSession, reservation: Reservation, action: str, reason: str, request_id: str | None, *,
                    details: dict[str, Any] | None = None) -> None:
        await self._audit(s, current, action, AuditOutcome.DENIED, request_id, reason=reason, details=details)
        if reservation.signal:
            await self._audit(s, current, "AUTH_RATE_LIMITED", AuditOutcome.FAILED, request_id, reason=f"{reservation.signal}_threshold_signal", details={"scope": "mfa"})
        if reservation.newly_blocked:
            await self._audit(s, current, "AUTH_RATE_LIMITED", AuditOutcome.DENIED, request_id, reason="progressive_delay", details={"scope": "mfa"})

    async def _audit(self, s: AsyncSession, current: AuthenticatedSession, action: str, outcome: AuditOutcome, request_id: str | None, *, reason: str | None = None,
                     details: dict[str, Any] | None = None) -> None:
        await SqlAuditWriter(s).write(AuditRecord(action=action, outcome=outcome, resource_type="USER", resource_id=str(current.user_id), actor_id=str(current.user_id),
                                                  organization_id=str(current.organization_id), request_id=request_id, reason_code=reason, details=details), occurred_at=self._clock())
