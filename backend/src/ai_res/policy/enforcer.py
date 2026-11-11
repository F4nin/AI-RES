"""Enforcement point helper (IAM v1.5 §7): asks the engine, audits the decision, and refuses fail-closed.

* ALLOW: the decision audit row is written in the CALLER's session, so it commits or rolls back with the protected action (audit failure aborts it).
  Read-only self-introspection actions may opt out (`auditAllow: false`, WORKING; ADR-017 says "every decision" and this is a recorded deviation).
* DENY / APPROVAL_REQUIRED: written in its OWN transaction (the caller's transaction is about to roll back) and then ACCESS_DENIED (403) is raised;
  `conceal=True` raises the same 404 as a genuinely missing object so a denial does not reveal that the object exists (IDOR, security.md).
* Engine outage/timeout/garbage: 503 POLICY_ENGINE_UNAVAILABLE, never an allow.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.platform.ports import AuditOutcome, AuditRecord, Effect, PolicyDecision, PolicyDecisionPort, PolicyRequest, decide_or_fail
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.config import PolicyConfig


class PolicyEnforcer:
    def __init__(self, engine: PolicyDecisionPort, factory: async_sessionmaker[AsyncSession], config: PolicyConfig | None, *, timeout_seconds: float) -> None:
        self._engine, self._factory, self._config, self._timeout = engine, factory, config, timeout_seconds

    def _audit_record(self, request: PolicyRequest, decision: PolicyDecision) -> AuditRecord:
        outcome = AuditOutcome.SUCCEEDED if decision.effect is Effect.ALLOW else AuditOutcome.DENIED
        return AuditRecord(
            action="POLICY_DECISION", outcome=outcome, resource_type=request.resource_type, resource_id=request.resource_id, actor_id=request.actor_id,
            organization_id=request.organization_id, project_id=request.project_id, reason_code=decision.reason_code, policy_version=decision.policy_version,
            details={"policyAction": request.action, "effect": decision.effect.value})

    async def authorize(self, request: PolicyRequest, *, session: AsyncSession, conceal: bool = False) -> PolicyDecision:
        decision = await decide_or_fail(self._engine, request, timeout_seconds=self._timeout)
        if decision.effect is Effect.ALLOW:
            rule = None if self._config is None else self._config.actions.get(request.action)
            if rule is None or rule.audit_allow:
                await SqlAuditWriter(session).write(self._audit_record(request, decision))
            return decision
        await self._audit_denial(request, decision)
        if conceal:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        approval = decision.effect is Effect.APPROVAL_REQUIRED
        raise ProblemError(ErrorCode.ACCESS_DENIED, "Human approval required." if approval else "Access denied.",
                           errors=[{"field": "policy", "reason": "approval_required" if approval else "denied"}])

    async def _audit_denial(self, request: PolicyRequest, decision: PolicyDecision) -> None:
        if request.organization_id is None:
            return  # no organization to attach the row to (RLS and the FK need one); the refusal itself still happens
        try:
            async with UnitOfWork(self._factory) as uow:
                org = UUID(request.organization_id)
                await uow.with_tenant(org, UUID(request.project_id) if request.project_id else None)
                await SqlAuditWriter(uow.session).write(self._audit_record(request, decision))
        except Exception as exc:  # the request is denied either way; a failed denial row must not turn into an allow or hide the 403 behind a 500
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Audit unavailable; action not performed.") from exc
