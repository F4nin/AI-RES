"""Authenticated identity-review preparation, deliberately without approval DML.

Trusted composition must provision the exact human AND profile and supply policy.
Packaged policy has no review grant. Returned digests are review material, never
an authorization credential, human decision, evidence provenance attestation or
complete Bifrost acceptance. No public route/CLI, lifecycle mutation or enablement.
An executor must independently authenticate, authorize, revalidate and audit its
own transaction; passing this review cannot authorize a later write or dispatch.
"""
import hashlib
import hmac
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.llm.observed_identity import (
    IdentityExpectation,
    IdentityMismatch,
    IdentityObservation,
    InvalidIdentityEvidence,
    compare_identity,
    parse_evidence,
)
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, evidence_hash, lock_profile_lifecycle
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ProblemError
from ai_res.policy.enforcer import PolicyEnforcer

ACTION = "model_admission.review"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True, repr=False)
class OwnerReviewScope:
    """Operator-provisioned binding, never inferred from tenant role/client data."""
    organization_id: UUID
    user_id: UUID
    profile_id: UUID

    def __post_init__(self) -> None:
        if any(not isinstance(v, UUID) for v in (self.organization_id, self.user_id, self.profile_id)):
            raise AdmissionDenied("OWNER_UNCONFIGURED")


@dataclass(frozen=True, slots=True, repr=False)
class OwnerReview:
    """Versioned comparison receipt only; it cannot be consumed as a permission."""
    binding_sha256: str
    profile_sha256: str
    expectation_sha256: str
    observation_sha256: str
    policy_version: str

    def __post_init__(self) -> None:
        for digest in (self.binding_sha256, self.profile_sha256, self.expectation_sha256, self.observation_sha256):
            if not isinstance(digest, str) or not _HASH.fullmatch(digest):
                raise AdmissionDenied("INVALID_REVIEW")
        if not isinstance(self.policy_version, str) or not self.policy_version:
            raise AdmissionDenied("INVALID_REVIEW")


def review_evidence(expectation: str | bytes, observation: str | bytes) -> tuple[IdentityExpectation, IdentityObservation]:
    """Bind one canonical observation to its proposed expectation; no autoapproval."""
    try:
        expected, observed = parse_evidence(expectation), parse_evidence(observation)
        if not isinstance(expected, IdentityExpectation) or not isinstance(observed, IdentityObservation):
            raise InvalidIdentityEvidence()
        compare_identity(observed, expected, current_generation=expected.admission_generation)
        if not hmac.compare_digest(expected.evidence_sha256, evidence_hash(observed).hex()):
            raise InvalidIdentityEvidence()
    except (InvalidIdentityEvidence, IdentityMismatch):
        raise AdmissionDenied("INVALID_REVIEW_EVIDENCE") from None
    return expected, observed


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def bind_owner_review(scope: OwnerReviewScope, actor: AuthenticatedSession, *, subject_hash: str, policy_version: str,
                      profile: str, control: str | None, current: str | None, pending: list[str],
                      expected: IdentityExpectation, observed: IdentityObservation) -> OwnerReview:
    """Pure ADR139 comparison, shared by operator final revalidation; no permission."""
    profile_hash = _digest(profile)
    eh, oh = evidence_hash(expected).hex(), evidence_hash(observed).hex()
    binding = _digest({"schemaVersion": "0.1", "action": ACTION, "organizationId": str(scope.organization_id),
                       "userId": str(scope.user_id), "sessionId": str(actor.session_id), "subject": subject_hash,
                       "policyVersion": policy_version, "profile": profile_hash, "expectation": eh,
                       "observation": oh, "control": control, "current": current, "pending": pending})
    return OwnerReview(binding, profile_hash, eh, oh, policy_version)


class OwnerReviewService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], policy: PolicyEnforcer,
                 *, scope: OwnerReviewScope | None = None) -> None:
        self._factory, self._policy, self._scope = factory, policy, scope

    def _actor(self, actor: AuthenticatedSession) -> OwnerReviewScope:
        scope = self._scope
        if not isinstance(scope, OwnerReviewScope):
            raise AdmissionDenied("OWNER_UNCONFIGURED")
        if (not isinstance(actor, AuthenticatedSession) or actor.organization_id != scope.organization_id
                or actor.user_id != scope.user_id or not isinstance(actor.session_id, UUID)):
            raise AdmissionDenied("OWNER_REQUIRED")
        return scope

    async def _subject(self, s: AsyncSession, actor: AuthenticatedSession) -> str:
        # Same grant lock order as the existing policy enforcer. Real subject
        # status and DB MFA matter; cached actor flags are not proof of authority.
        await self._policy.lock_subject_grants(s, actor.user_id, actor.organization_id, None)
        member = (await s.execute(text(
            "SELECT role_code,status,row_version FROM organization.memberships WHERE organization_id=:o AND user_id=:u"),
            {"o": actor.organization_id, "u": actor.user_id})).mappings().first()
        user = (await s.execute(text("SELECT status,row_version FROM iam.users WHERE organization_id=:o AND id=:u"),
                                {"o": actor.organization_id, "u": actor.user_id})).mappings().first()
        if member is None or user is None or member["status"] != "ACTIVE" or user["status"] != "ACTIVE":
            raise AdmissionDenied("OWNER_REQUIRED")
        # Match MFA reset/verification: factor first, then session. Reversing
        # this order creates a cycle with reset's factor UPDATE -> session revoke.
        factors = (await s.execute(text(
            "SELECT id FROM iam.mfa_factors WHERE organization_id=:o AND user_id=:u AND status='ACTIVE' ORDER BY id FOR SHARE"),
            {"o": actor.organization_id, "u": actor.user_id})).scalars().all()
        if not factors:
            raise AdmissionDenied("OWNER_MFA_REQUIRED")
        if not await lock_authenticated_session(s, actor):
            raise AdmissionDenied("OWNER_MFA_REQUIRED")
        mfa_at = (await s.execute(text("SELECT mfa_verified_at::text FROM iam.sessions WHERE id=:sid"),
                                  {"sid": actor.session_id})).scalar_one()
        return _digest({"member": dict(member), "user": dict(user), "factors": [str(v) for v in factors], "mfaAt": mfa_at})

    async def prepare(self, actor: AuthenticatedSession, *, expectation: str | bytes, observation: str | bytes,
                      previous: OwnerReview | None = None) -> OwnerReview:
        """Recompute across policy/model waits; detect stale/tampered `previous`.

        Policy I/O happens outside DB transactions. The final transaction locks
        and rechecks live subject facts and then the profile lifecycle fence.
        Only the policy audit can be written; profile/admission rows stay intact.
        This material does not attest to physical commit-time authorization.
        """
        scope = self._actor(actor)
        expected, observed = review_evidence(expectation, observation)
        if expected.managed_versions.profile_id != scope.profile_id:
            raise AdmissionDenied("INVALID_REVIEW_EVIDENCE")
        if previous is not None and not isinstance(previous, OwnerReview):
            raise AdmissionDenied("INVALID_REVIEW")
        try:
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(scope.organization_id)
                subject_hash = await self._subject(uow.session, actor)
            request = PolicyRequest(actor_id=str(scope.user_id), organization_id=str(scope.organization_id),
                                    action=ACTION, resource_type="MODEL_ADMISSION_REVIEW", resource_id=str(scope.profile_id),
                                    attributes={"actor_type": "USER", "mfa_verified": True})
            decision = await self._policy.decide(request)
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(scope.organization_id)
                s = uow.session
                if not hmac.compare_digest(subject_hash, await self._subject(s, actor)):
                    raise AdmissionDenied("OWNER_CHANGED")
                await lock_profile_lifecycle(s, scope.profile_id)
                await s.execute(text("SELECT set_config('app.model_profile_id',:p,true)"), {"p": str(scope.profile_id)})
                # PostgreSQL serializes numerics losslessly; keep its complete
                # JSON text as an opaque string instead of parsing through float.
                row = (await s.execute(text(
                    "SELECT to_jsonb(p)::text AS snapshot,p.profile_version,p.status,p.deprecated_at,clock_timestamp() AS checked_at "
                    "FROM platform.model_profiles p WHERE p.id=:p AND p.identity_mode='FLASH_OBSERVED' "
                    "AND p.provider='deepseek' AND p.provider_model_id='deepseek-flash' AND p.pinned_model_version IS NULL"),
                    {"p": scope.profile_id})).mappings().first()
                if (row is None or row["status"] not in ("CANDIDATE", "APPROVED")
                        or row["deprecated_at"] is not None and row["deprecated_at"] <= row["checked_at"]
                        or row["profile_version"] != expected.managed_versions.profile_version):
                    raise AdmissionDenied("REVIEW_TARGET_UNAVAILABLE")
                control = (await s.execute(text(
                    "SELECT to_jsonb(c)::text AS snapshot,current_generation FROM platform.model_admission_controls c "
                    "WHERE profile_id=:p FOR UPDATE"), {"p": scope.profile_id})).mappings().first()
                generation = 0 if control is None else control["current_generation"]
                if expected.admission_generation != generation + 1:
                    raise AdmissionDenied("STALE_REVIEW_GENERATION")
                current = (await s.execute(text(
                    "SELECT to_jsonb(v)::text FROM platform.model_admission_versions v WHERE profile_id=:p AND generation=:g"),
                    {"p": scope.profile_id, "g": generation})).scalar_one_or_none()
                if control is not None and current is None:
                    raise AdmissionDenied("ADMISSION_INVALID")
                pending = (await s.execute(text(
                    "SELECT to_jsonb(c)::text FROM platform.model_admission_calls c WHERE profile_id=:p AND status='IN_FLIGHT' "
                    "ORDER BY call_sequence"), {"p": scope.profile_id})).scalars().all()
                review = bind_owner_review(scope, actor, subject_hash=subject_hash, policy_version=decision.policy_version,
                                           profile=row["snapshot"], control=None if control is None else control["snapshot"],
                                           current=current, pending=list(pending), expected=expected, observed=observed)
                if previous is not None and previous != review:
                    raise AdmissionDenied("STALE_REVIEW")
                # Locks cannot stop time: fence/control/SQL waits can outlive
                # the session or scheduled profile deprecation. Check again
                # after those waits and before auditing/exporting the material.
                if not hmac.compare_digest(subject_hash, await self._subject(s, actor)):
                    raise AdmissionDenied("OWNER_CHANGED")
                live = (await s.execute(text(
                    "SELECT deprecated_at IS NULL OR deprecated_at>clock_timestamp() FROM platform.model_profiles WHERE id=:p"),
                    {"p": scope.profile_id})).scalar_one()
                if not live:
                    raise AdmissionDenied("REVIEW_TARGET_UNAVAILABLE")
                await self._policy.record_allow(request, decision, session=s)
            return review
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None
        except ProblemError:
            raise AdmissionDenied("OWNER_AUTHORIZATION_REFUSED") from None
