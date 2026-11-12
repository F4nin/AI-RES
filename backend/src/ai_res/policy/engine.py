# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Policy & Permission Engine (ADR-017, IAM v1.5 §2/§5): in-process, deny-by-default, versioned, fail-closed.

Subject attributes are read from PostgreSQL under the REQUEST's organization (never from the client): the user must be ACTIVE, the organization
membership ACTIVE, and a grant must come from the matrix. Decision order: configuration valid -> action known -> resource type matches ->
organization scope present -> actor type supported -> autonomy level permitted -> subject resolvable and active -> grant (self / org role /
project role) -> MFA for privileged grants -> approval. Every refusal carries a stable reason code and the policy version.

RLS is defense-in-depth here too: the lookup runs inside the transaction-local tenant context of the request's organization/project.
"""
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.platform.ports import Effect, PolicyDecision, PolicyRequest
from ai_res.policy.config import PolicyConfig, PolicyConfigError, load_packaged_policy

_log = logging.getLogger("ai_res.policy")
INVALID_VERSION = "invalid-config"
REASON_RESOURCE_NOT_VISIBLE = "resource_not_visible"  # shared with the enforcer: it decides where a denial audit row is anchored
AUTONOMY_ALLOWED = frozenset({"A0", "A1", "A2"})  # A3/A4 are outside the MVP (project-context.md)


def _uuid(value: str | None) -> UUID | None:
    try:
        return None if value is None else UUID(value)
    except ValueError:
        return None


class PolicyEngine:
    """Implements PolicyDecisionPort. Use `PolicyEngine.from_packaged(factory)`; with `config=None` every request is denied."""

    def __init__(self, config: PolicyConfig | None, factory: async_sessionmaker[AsyncSession]) -> None:
        self._config, self._factory = config, factory

    @classmethod
    def from_packaged(cls, factory: async_sessionmaker[AsyncSession]) -> "PolicyEngine":
        try:
            return cls(load_packaged_policy(), factory)
        except PolicyConfigError as exc:
            _log.error("policy configuration rejected, engine is DENY-ALL: %s", exc)  # alert hook: this log line is the signal (S13 wires alerting)
            return cls(None, factory)

    @property
    def policy_version(self) -> str:
        return INVALID_VERSION if self._config is None else self._config.version

    def _deny(self, reason: str) -> PolicyDecision:
        return PolicyDecision(effect=Effect.DENY, reason_code=reason, policy_version=self.policy_version)

    async def decide(self, request: PolicyRequest) -> PolicyDecision:
        cfg = self._config
        if cfg is None:
            return self._deny("policy_config_invalid")
        rule = cfg.actions.get(request.action)
        if rule is None:
            return self._deny("unknown_action")
        if request.resource_type.upper() != rule.resource_type:
            return self._deny("resource_type_mismatch")
        org, actor, project = _uuid(request.organization_id), _uuid(request.actor_id), _uuid(request.project_id)
        if org is None or actor is None or (request.project_id is not None and project is None):
            return self._deny("missing_scope")
        attrs = request.attributes
        if attrs.get("actor_type", "USER") != "USER":  # services/Manager/Worker Runs get their own grant check (Worker Run grants, S14+): until then deny
            return self._deny("human_only_action" if rule.human_only else "actor_type_unsupported")
        level = attrs.get("autonomy_level")
        if level is not None and level not in AUTONOMY_ALLOWED:
            return self._deny("autonomy_not_permitted")
        mfa_verified = attrs.get("mfa_verified") is True  # only a real True counts; truthy strings/ints do not

        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(org, project)
            subject = (await uow.session.execute(text(
                "SELECT u.status AS user_status, m.role_code AS org_role, m.status AS membership_status FROM iam.users u "
                "LEFT JOIN organization.memberships m ON m.organization_id = u.organization_id AND m.user_id = u.id WHERE u.organization_id = :o AND u.id = :u"),
                {"o": org, "u": actor})).mappings().first()
            project_role: str | None = None
            if project is not None:
                row = (await uow.session.execute(text(
                    "SELECT pm.role_code, pm.status FROM project.projects p LEFT JOIN project.project_memberships pm "
                    "ON pm.organization_id = p.organization_id AND pm.project_id = p.id AND pm.user_id = :u WHERE p.organization_id = :o AND p.id = :p"),
                    {"o": org, "u": actor, "p": project})).mappings().first()
                if row is None:
                    return self._deny(REASON_RESOURCE_NOT_VISIBLE)  # unknown project (or another organization's): same answer as a missing one
                project_role = row["role_code"] if row["status"] == "ACTIVE" else None
        if subject is None:
            return self._deny("subject_not_found")
        if subject["user_status"] != "ACTIVE":
            return self._deny("subject_inactive")

        if subject["membership_status"] not in (None, "ACTIVE"):
            return self._deny("membership_inactive")  # an explicitly revoked organization membership closes every grant, project roles and self-service included
        org_role = subject["org_role"]  # None for a project-only user (no organization membership row)
        grants: list[tuple[str, str | None]] = []  # (reason, privileged role that needs MFA or None)
        if rule.self_allowed and (request.resource_id is None or _uuid(request.resource_id) == actor):
            grants.append(("allowed_self", None))
        if org_role is not None and org_role in rule.org_roles:
            grants.append((f"allowed_role:{org_role}", org_role))
        if project_role is not None and project_role in rule.project_roles:
            grants.append((f"allowed_role:{project_role}", project_role))
        if not grants:
            return self._deny("no_matching_grant")

        mfa_blocked = False
        for reason, role in grants:
            needs_mfa = rule.requires_mfa or (role is not None and role in cfg.privileged_roles)
            if needs_mfa and not mfa_verified:
                mfa_blocked = True
                continue
            if rule.approval_required:
                return PolicyDecision(effect=Effect.APPROVAL_REQUIRED, reason_code="approval_required", policy_version=cfg.version)
            return PolicyDecision(effect=Effect.ALLOW, reason_code=reason, policy_version=cfg.version)
        return self._deny("mfa_required" if mfa_blocked else "no_matching_grant")
