"""Shared human, exact-content and separation-of-duties checks for decisions."""

import hmac
from uuid import UUID

from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, Principal, ServiceIdentity
from ai_res.platform.problems import ErrorCode, ProblemError


def require_human_approver(actor: Principal | ServiceIdentity, policy: PolicyDecision) -> UUID:
    """Require an authenticated human and the caller's exact-target Policy decision."""
    if not isinstance(actor, Principal) or actor.expires_at <= utc_now() or policy.effect is not Effect.ALLOW:
        raise ProblemError(ErrorCode.ACCESS_DENIED, "An authorized human decision is required.")
    return UUID(actor.user_id)


def require_approval_binding(
    approver: UUID,
    stored_hash: bytes,
    supplied_hash: bytes,
    *,
    conflict_message: str,
    excluded_approver: UUID | None = None,
) -> None:
    """Check immutable content and enforce any policy-required separation."""
    if not hmac.compare_digest(stored_hash, supplied_hash):
        raise ProblemError(ErrorCode.VERSION_CONFLICT, conflict_message)
    if approver == excluded_approver:
        raise ProblemError(ErrorCode.ACCESS_DENIED, "A different approver is required.")
