# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Account lifecycle changes that must end sessions immediately (Auth v1.1 §3.1, §6; AUTH-008): disable a user, revoke an organization membership.

Both run inside the CALLER's transaction (`*_in`): the handler has already passed the Policy Engine (`iam.user.disable`, `iam.membership.revoke`) and the
change, the session revocation and the audit row commit together. Lock-out guards: nobody disables or demotes themselves, and the last active
ORGANIZATION_OWNER cannot be removed.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import affected
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.iam.sessions import RevokeReason, SessionService
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

_RANK = {"ORGANIZATION_OWNER": 2, "ORGANIZATION_ADMIN": 1}  # every other (or no) organization role ranks 0


async def ensure_may_act_on(s: AsyncSession, factory: async_sessionmaker[AsyncSession], organization_id: UUID, actor_id: UUID, subject_id: UUID, *, action: str,
                            policy_version: str | None = None) -> None:
    """Role hierarchy (ADR-073, WORKING): an actor may act on a user whose organization role ranks strictly below their own; an OWNER may also act on another OWNER.
    Without it a compromised administrator could disable or reset the MFA of the owners who are meant to control administrators."""
    # Serialise per organization BEFORE reading roles: rank check, last-owner count and the UPDATE then see one consistent picture (READ COMMITTED), and two owners
    # disabling each other cannot both pass.
    await s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('owner-guard:' || CAST(:o AS text), 0))"), {"o": organization_id})
    rows = (await s.execute(text("SELECT user_id, role_code FROM organization.memberships WHERE organization_id = :o AND status = 'ACTIVE' AND user_id IN (:a, :u)"),
                            {"o": organization_id, "a": actor_id, "u": subject_id})).mappings().all()
    roles = {r["user_id"]: r["role_code"] for r in rows}
    actor_role, subject_role = roles.get(actor_id), roles.get(subject_id)
    actor_rank, subject_rank = _RANK.get(actor_role or "", 0), _RANK.get(subject_role or "", 0)
    if actor_rank > subject_rank or (actor_role == "ORGANIZATION_OWNER" and subject_role == "ORGANIZATION_OWNER"):
        return
    await _audit_hierarchy_denial(factory, organization_id, actor_id, subject_id, action, policy_version)
    raise ProblemError(ErrorCode.ACCESS_DENIED, "Access denied.", errors=[{"field": "policy", "reason": "role_hierarchy"}])


async def _audit_hierarchy_denial(factory: async_sessionmaker[AsyncSession], organization_id: UUID, actor_id: UUID, subject_id: UUID, action: str, policy_version: str | None) -> None:
    """The caller's transaction rolls back on the refusal, so the denial is recorded in its OWN transaction (same convention as PolicyEnforcer). If it cannot be
    recorded the action is still not performed, and the caller sees 503 rather than a refusal that left no trace."""
    try:
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(organization_id)
            await SqlAuditWriter(uow.session).write(AuditRecord(
                action="POLICY_DECISION", outcome=AuditOutcome.DENIED, resource_type="USER", resource_id=str(subject_id), actor_id=str(actor_id), organization_id=str(organization_id),
                reason_code="role_hierarchy", policy_version=policy_version, details={"policyAction": action, "effect": "DENY", "check": "role_hierarchy"}), occurred_at=utc_now())
    except Exception as exc:
        raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Audit unavailable; action not performed.") from exc


class AccountService:
    def __init__(self, sessions: SessionService, factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions, self._factory = sessions, factory

    async def _guard(self, s: AsyncSession, organization_id: UUID, actor_id: UUID, user_id: UUID, action: str, policy_version: str) -> None:
        if actor_id == user_id:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "You cannot do this to your own account.")
        await ensure_may_act_on(s, self._factory, organization_id, actor_id, user_id, action=action, policy_version=policy_version)
        owner_left = (await s.execute(text(
            "SELECT count(*) FROM organization.memberships m JOIN iam.users u ON u.organization_id = m.organization_id AND u.id = m.user_id "
            "WHERE m.organization_id = :o AND m.role_code = 'ORGANIZATION_OWNER' AND m.status = 'ACTIVE' AND u.status = 'ACTIVE' AND m.user_id <> :u"), {"o": organization_id, "u": user_id})).scalar_one()
        is_owner = (await s.execute(text("SELECT 1 FROM organization.memberships WHERE organization_id = :o AND user_id = :u AND role_code = 'ORGANIZATION_OWNER' AND status = 'ACTIVE'"),
                                    {"o": organization_id, "u": user_id})).first() is not None
        if is_owner and owner_left == 0:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The last active organization owner cannot be removed.")

    async def _exists(self, s: AsyncSession, organization_id: UUID, user_id: UUID) -> None:
        if (await s.execute(text("SELECT 1 FROM iam.users WHERE organization_id = :o AND id = :u"), {"o": organization_id, "u": user_id})).first() is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")  # also what another organization's user looks like (RLS)

    async def disable_user_in(self, s: AsyncSession, organization_id: UUID, actor_id: UUID, user_id: UUID, *, policy_version: str, request_id: str | None) -> int:
        await self._exists(s, organization_id, user_id)
        await self._guard(s, organization_id, actor_id, user_id, "iam.user.disable", policy_version)
        r = await s.execute(text("UPDATE iam.users SET status = 'DISABLED', row_version = row_version + 1 WHERE organization_id = :o AND id = :u AND status = 'ACTIVE'"), {"o": organization_id, "u": user_id})
        if affected(r) != 1:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The account is already disabled.")  # no false "succeeded" audit row
        revoked = await self._sessions.revoke_all_for_user_in(s, user_id, RevokeReason.USER_DISABLED)
        await SqlAuditWriter(s).write(AuditRecord(action="AUTH_ACCOUNT_DISABLED", outcome=AuditOutcome.SUCCEEDED, resource_type="USER", resource_id=str(user_id), actor_id=str(actor_id),
                                                  organization_id=str(organization_id), request_id=request_id, policy_version=policy_version, details={"devicesSignedOut": revoked}), occurred_at=utc_now())
        return revoked

    async def revoke_membership_in(self, s: AsyncSession, organization_id: UUID, actor_id: UUID, user_id: UUID, *, policy_version: str, request_id: str | None) -> int:
        await self._exists(s, organization_id, user_id)
        await self._guard(s, organization_id, actor_id, user_id, "iam.membership.revoke", policy_version)
        r = await s.execute(text("UPDATE organization.memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE organization_id = :o AND user_id = :u AND status <> 'REVOKED'"),
                            {"o": organization_id, "u": user_id})
        if affected(r) < 1:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The user has no active membership in this organization.")
        revoked = await self._sessions.revoke_all_for_user_in(s, user_id, RevokeReason.ROLE_REVOKED)
        await SqlAuditWriter(s).write(AuditRecord(action="AUTH_SESSION_REVOKED", outcome=AuditOutcome.SUCCEEDED, resource_type="USER", resource_id=str(user_id), actor_id=str(actor_id),
                                                  organization_id=str(organization_id), request_id=request_id, reason_code="role_revoked", policy_version=policy_version,
                                                  details={"membershipsRevoked": affected(r), "devicesSignedOut": revoked}), occurred_at=utc_now())
        return revoked
