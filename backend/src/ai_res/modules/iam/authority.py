"""Revalidate an authenticated internal caller's live session under a read lock."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.platform.problems import ErrorCode, ProblemError


async def lock_authenticated_session(s: AsyncSession, actor: AuthenticatedSession) -> bool:
    """No browser token is accepted here; the transport authenticates first.

    A captured AuthenticatedSession cannot survive logout, expiry, or MFA changes.
    The lock lasts until the protected operation commits or rolls back.
    """
    row = (await s.execute(text(
        "SELECT mfa_verified_at FROM iam.sessions WHERE id=:sid AND user_id=:u AND organization_id=:o "
        "AND revoked_at IS NULL AND idle_expires_at>clock_timestamp() AND absolute_expires_at>clock_timestamp() FOR SHARE"),
        {"sid": actor.session_id, "u": actor.user_id, "o": actor.organization_id})).first()
    if row is None or actor.second_factor_pending:
        raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
    enrolled = (await s.execute(text("SELECT 1 FROM iam.mfa_factors WHERE user_id=:u AND status='ACTIVE'"), {"u": actor.user_id})).first()
    if enrolled is not None and row[0] is None:
        raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
    return row[0] is not None
