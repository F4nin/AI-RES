"""Isolated human identity decisions; no profile activation, transport or real setup.

Trusted composition supplies a dedicated EXECUTE-only operator factory plus normal
PolicyEnforcer. Neither API nor runtimes receive operator membership/credentials.
Input actor is already transport-authenticated; SQL rechecks its live DB facts.
The command is an explicit human decision, never automatically made from review.
No public endpoint, CLI or packaged policy grant is installed by this module.
"""
import hashlib
import hmac
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, evidence_hash
from ai_res.modules.model_registry.owner_review import OwnerReview, OwnerReviewScope, bind_owner_review, review_evidence
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ProblemError
from ai_res.policy.enforcer import PolicyEnforcer


class IdentityDecisionAction(StrEnum):
    ACCEPT_IDENTITY = "ACCEPT_IDENTITY"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True, repr=False)
class IdentityDecision:
    decision_id: UUID
    correlation_id: UUID
    action: IdentityDecisionAction
    review: OwnerReview

    def __post_init__(self) -> None:
        if (not isinstance(self.decision_id, UUID) or not isinstance(self.correlation_id, UUID)
                or not isinstance(self.action, IdentityDecisionAction) or not isinstance(self.review, OwnerReview)):
            raise AdmissionDenied("INVALID_OWNER_DECISION")
        OwnerReview(**asdict(self.review))


@dataclass(frozen=True, slots=True, repr=False)
class IdentityDecisionReceipt:
    decision_id: UUID
    profile_id: UUID
    generation: int
    action: IdentityDecisionAction


class IdentityAdmissionOperator:
    def __init__(self, factory: async_sessionmaker[AsyncSession], policy: PolicyEnforcer,
                 *, scope: OwnerReviewScope | None = None) -> None:
        self._factory, self._policy, self._scope = factory, policy, scope

    async def _snapshot(self, s: AsyncSession, actor: AuthenticatedSession, decision_id: UUID) -> dict[str, Any]:
        row = (await s.execute(text(
            "SELECT platform.owner_identity_snapshot(:o,:u,:sid,:p,:d)"),
            {"o": actor.organization_id, "u": actor.user_id, "sid": actor.session_id,
             "p": self._scope.profile_id if self._scope else None, "d": decision_id})).scalar_one()
        if not isinstance(row, dict):
            raise AdmissionUnavailable()
        return row

    async def execute(self, actor: AuthenticatedSession, command: IdentityDecision, *, expectation: str | bytes,
                      observation: str | bytes) -> IdentityDecisionReceipt:
        """Reauthenticate before/after independent Policy; final SQL/audit atomic.

        A matching committed decision can be replayed after fresh authentication
        and Policy, returning only its historical receipt. It grants no dispatch
        authority and never clears a later block. No external I/O inside UoW.
        """
        scope = self._scope
        if not isinstance(scope, OwnerReviewScope):
            raise AdmissionDenied("OWNER_UNCONFIGURED")
        if (not isinstance(actor, AuthenticatedSession) or actor.organization_id != scope.organization_id
                or actor.user_id != scope.user_id or actor.second_factor_pending):
            raise AdmissionDenied("OWNER_REQUIRED")
        if not isinstance(command, IdentityDecision):
            raise AdmissionDenied("INVALID_OWNER_DECISION")
        IdentityDecision(command.decision_id, command.correlation_id, command.action, command.review)
        expected, observed = review_evidence(expectation, observation)
        if expected.managed_versions.profile_id != scope.profile_id:
            raise AdmissionDenied("INVALID_REVIEW_EVIDENCE")
        payload = {"decisionId": str(command.decision_id), "correlationId": str(command.correlation_id),
                   "action": command.action.value, "review": asdict(command.review),
                   "expectationSha256": evidence_hash(expected).hex(), "observationSha256": evidence_hash(observed).hex()}
        encoded = canonical_json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        action = "model_admission.accept_identity" if command.action is IdentityDecisionAction.ACCEPT_IDENTITY else "model_admission.block"
        request = PolicyRequest(actor_id=str(scope.user_id), organization_id=str(scope.organization_id), action=action,
                                resource_type="MODEL_ADMISSION_DECISION", resource_id=str(scope.profile_id),
                                attributes={"actor_type": "USER", "mfa_verified": True})
        try:
            async with UnitOfWork(self._factory) as uow:
                initial = await self._snapshot(uow.session, actor, command.decision_id)
            decision = await self._policy.decide(request)
            if decision.policy_version != command.review.policy_version:
                raise AdmissionDenied("STALE_REVIEW_POLICY")
            async with UnitOfWork(self._factory) as uow:
                final = await self._snapshot(uow.session, actor, command.decision_id)
                if initial["subject"] != final["subject"]:
                    raise AdmissionDenied("OWNER_CHANGED")
                receipt = final["receipt"]
                if receipt is None:
                    actual = bind_owner_review(scope, actor,
                        subject_hash=hashlib.sha256(canonical_json(final["subject"]).encode()).hexdigest(),
                        policy_version=decision.policy_version, profile=final["profile"], control=final["control"],
                        current=final["current"], pending=final["pending"], expected=expected, observed=observed)
                    if actual != command.review or expected.admission_generation != final["generation"] + 1:
                        raise AdmissionDenied("STALE_REVIEW")
                elif not hmac.compare_digest(receipt["command_sha256"], digest):
                    raise AdmissionDenied("DECISION_ID_REUSED")
                result = (await uow.session.execute(text(
                    "SELECT platform.apply_owner_identity_decision(:o,:u,:sid,:p,:d,CAST(:state AS jsonb),:cmd,:expectation,:observation)"),
                    {"o": actor.organization_id, "u": actor.user_id, "sid": actor.session_id, "p": scope.profile_id,
                     "d": command.decision_id, "state": canonical_json(final), "cmd": encoded,
                     "expectation": canonical_json(expected.to_dict()), "observation": canonical_json(observed.to_dict())})).scalar_one()
                receipt = IdentityDecisionReceipt(command.decision_id, scope.profile_id, result["generation"], command.action)
            return receipt
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None
        except ProblemError:
            raise AdmissionDenied("OWNER_AUTHORIZATION_REFUSED") from None
