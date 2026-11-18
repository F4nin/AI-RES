"""Explicit human Flash/profile acceptance on an isolated existing owner connection.

No login, binding, policy grant, profile, session or budget is provisioned. The
normal API and runtimes cannot become the owner. A supplied digest is the human's
exact acceptance target, not a claim that this service evaluated model quality.
"""
import hashlib
import hmac
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.sessions import AuthenticatedSession, SessionService
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, evidence_hash, lock_profile_lifecycle
from ai_res.modules.model_registry.owner_review import OwnerReviewScope, OwnerReviewService, review_evidence
from ai_res.modules.model_registry.repository import RegistryLoadError, load_model_registry
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ProblemError
from ai_res.policy.enforcer import PolicyEnforcer

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_POLICY = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_LOGIN = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
ACTION = "model_profile.approve"


class ProfileApprovalAction(StrEnum):
    APPROVE_PROFILE_AND_ACCEPT_BIFROST = "APPROVE_PROFILE_AND_ACCEPT_BIFROST"


@dataclass(frozen=True, slots=True, repr=False)
class ProfileApprovalDecision:
    decision_id: UUID
    correlation_id: UUID
    action: ProfileApprovalAction
    profile_sha256: str
    expectation_sha256: str
    observation_sha256: str
    bifrost_acceptance_sha256: str
    policy_version: str

    def __post_init__(self) -> None:
        if (not isinstance(self.decision_id, UUID) or not isinstance(self.correlation_id, UUID)
                or not isinstance(self.action, ProfileApprovalAction)
                or any(not isinstance(v, str) or not _HASH.fullmatch(v) for v in (
                    self.profile_sha256, self.expectation_sha256, self.observation_sha256, self.bifrost_acceptance_sha256))
                or not isinstance(self.policy_version, str) or not _POLICY.fullmatch(self.policy_version)):
            raise AdmissionDenied("INVALID_PROFILE_APPROVAL")


@dataclass(frozen=True, slots=True, repr=False)
class ProfileApprovalReceipt:
    decision_id: UUID
    profile_id: UUID
    profile_version: int
    generation: int


def profile_snapshot_hash(snapshot: str) -> str:
    """Hash PostgreSQL's complete JSON text without lossy numeric conversion."""
    return hashlib.sha256(canonical_json(snapshot).encode()).hexdigest()


class ProfileApprovalService(OwnerReviewService):
    """Use reviewed live-subject checks; the owner factory is never a runtime port."""

    def __init__(self, factory: async_sessionmaker[AsyncSession], policy: PolicyEnforcer, *,
                 scope: OwnerReviewScope | None = None, owner_login: str | None = None,
                 sessions: SessionService | None = None) -> None:
        super().__init__(factory, policy, scope=scope)
        self._owner_login, self._sessions = owner_login, sessions

    async def execute_token(self, token: str, command: ProfileApprovalDecision, *, expectation: str | bytes,
                            observation: str | bytes, bifrost_acceptance: bytes) -> ProfileApprovalReceipt:
        if self._sessions is None:
            raise AdmissionDenied("OWNER_UNCONFIGURED")
        try:
            result = await self._sessions.authenticate(token, touch=False)
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None
        except ProblemError:
            raise AdmissionDenied("OWNER_REQUIRED") from None
        if result.session is None:
            raise AdmissionDenied("OWNER_REQUIRED")
        return await self.execute(result.session, command, expectation=expectation, observation=observation,
                                  bifrost_acceptance=bifrost_acceptance)

    async def _owner_connection(self, s: AsyncSession, actor: AuthenticatedSession) -> None:
        login = self._owner_login
        if not isinstance(login, str) or not _LOGIN.fullmatch(login):
            raise AdmissionDenied("OWNER_UNCONFIGURED")
        row = (await s.execute(text(
            "SELECT session_user::text AS login,current_user::text AS effective,"
            "r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb AS elevated,"
            "pg_has_role(session_user,'ai_res_owner','MEMBER') AS owner_member "
            "FROM pg_catalog.pg_roles r WHERE r.rolname=session_user"))).mappings().one()
        if (row["login"] != login or row["effective"] not in (login, "ai_res_owner")
                or row["elevated"] or row["owner_member"] is not True):
            raise AdmissionDenied("OWNER_CONNECTION_REQUIRED")
        # Fixed role name; runtime roles have no membership and cannot reach it.
        await s.execute(text("SET LOCAL ROLE ai_res_owner"))
        await s.execute(text("SELECT set_config('app.migration_mode','on',true)"))
        scope = self._actor(actor)
        bound = (await s.execute(text(
            "SELECT 1 FROM platform.model_admission_operators WHERE database_login=session_user "
            "AND organization_id=:o AND user_id=:u AND profile_id=:p FOR SHARE"),
            {"o": scope.organization_id, "u": scope.user_id, "p": scope.profile_id})).scalar_one_or_none()
        if bound != 1:
            raise AdmissionDenied("OWNER_BINDING_REQUIRED")

    async def _snapshot(self, s: AsyncSession, actor: AuthenticatedSession, command: ProfileApprovalDecision) -> dict[str, Any]:
        scope = self._actor(actor)
        subject = await self._subject(s, actor)
        # One decision UUID is globally unique, even across different profiles.
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ai_res.profile_approval:' || CAST(:d AS uuid)::text,0))"),
                        {"d": command.decision_id})
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ai_res.single_approved_model_profile',0))"))
        await lock_profile_lifecycle(s, scope.profile_id)
        await s.execute(text("SELECT set_config('app.model_profile_id',:p,true)"), {"p": str(scope.profile_id)})
        prior = (await s.execute(text(
            "SELECT action,actor_type,object_type,result,organization_id,actor_id,object_id,details FROM audit.audit_events WHERE id=:d"),
            {"d": command.decision_id})).mappings().first()
        profile = (await s.execute(text(
            "SELECT to_jsonb(p)::text AS snapshot,p.profile_version,p.status,p.approved_by,p.approved_at::text AS approved_at,"
            "p.deprecated_at,clock_timestamp() AS checked_at "
            "FROM platform.model_profiles p WHERE p.id=:p AND p.identity_mode='FLASH_OBSERVED' "
            "AND p.provider='deepseek' AND p.provider_model_id='deepseek-flash' AND p.pinned_model_version IS NULL"),
            {"p": scope.profile_id})).mappings().first()
        if profile is None:
            raise AdmissionDenied("PROFILE_UNAVAILABLE")
        if prior is None:
            try:
                candidate = (await load_model_registry(s)).get(scope.profile_id)
            except RegistryLoadError:
                raise AdmissionDenied("PROFILE_UNAVAILABLE") from None
            if candidate is None:
                raise AdmissionDenied("PROFILE_UNAVAILABLE")
            another = (await s.execute(text(
                "SELECT EXISTS(SELECT 1 FROM platform.model_profiles WHERE status='APPROVED' AND id<>:p)"),
                {"p": scope.profile_id})).scalar_one()
            if another:
                raise AdmissionDenied("ONE_APPROVED_PROFILE_ONLY")
        control = (await s.execute(text(
            "SELECT current_generation,blocked FROM platform.model_admission_controls WHERE profile_id=:p FOR UPDATE"),
            {"p": scope.profile_id})).mappings().first()
        generation = 0 if control is None else control["current_generation"]
        current = (await s.execute(text(
            "SELECT expectation_sha256 FROM platform.model_admission_versions WHERE profile_id=:p AND generation=:g"),
            {"p": scope.profile_id, "g": generation})).scalar_one_or_none()
        pending = (await s.execute(text(
            "SELECT EXISTS(SELECT 1 FROM platform.model_admission_calls WHERE profile_id=:p AND status='IN_FLIGHT')"),
            {"p": scope.profile_id})).scalar_one()
        # Reacquire live facts AFTER every possible decision/fence/control wait.
        if not hmac.compare_digest(subject, await self._subject(s, actor)):
            raise AdmissionDenied("OWNER_CHANGED")
        return {"subject": subject, "profile": dict(profile), "control": None if control is None else dict(control),
                "current": None if current is None else bytes(current), "pending": pending,
                "prior": None if prior is None else dict(prior), "generation": generation}

    async def execute(self, actor: AuthenticatedSession, command: ProfileApprovalDecision, *, expectation: str | bytes,
                      observation: str | bytes, bifrost_acceptance: bytes) -> ProfileApprovalReceipt:
        scope = self._actor(actor)
        if not isinstance(command, ProfileApprovalDecision):
            raise AdmissionDenied("INVALID_PROFILE_APPROVAL")
        ProfileApprovalDecision(**asdict(command))
        expected, observed = review_evidence(expectation, observation)
        if (expected.managed_versions.profile_id != scope.profile_id
                or evidence_hash(expected).hex() != command.expectation_sha256
                or evidence_hash(observed).hex() != command.observation_sha256
                or not isinstance(bifrost_acceptance, bytes) or not 1 <= len(bifrost_acceptance) <= 1_048_576
                or hashlib.sha256(bifrost_acceptance).hexdigest() != command.bifrost_acceptance_sha256):
            raise AdmissionDenied("INVALID_APPROVAL_EVIDENCE")
        payload = {**asdict(command), "decision_id": str(command.decision_id), "correlation_id": str(command.correlation_id),
                   "organization_id": str(scope.organization_id), "user_id": str(scope.user_id),
                   "session_id": str(actor.session_id), "profile_id": str(scope.profile_id)}
        command_hash = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        request = PolicyRequest(actor_id=str(scope.user_id), organization_id=str(scope.organization_id), action=ACTION,
                                resource_type="MODEL_PROFILE_APPROVAL", resource_id=str(scope.profile_id),
                                attributes={"actor_type": "USER", "mfa_verified": True})
        try:
            async with UnitOfWork(self._factory) as uow:
                await self._owner_connection(uow.session, actor)
                await uow.with_tenant(scope.organization_id)
                initial = await self._snapshot(uow.session, actor, command)
            decision = await self._policy.decide(request)
            if decision.policy_version != command.policy_version:
                raise AdmissionDenied("STALE_APPROVAL_POLICY")
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                await self._owner_connection(s, actor)
                await uow.with_tenant(scope.organization_id)
                final = await self._snapshot(s, actor, command)
                if initial["subject"] != final["subject"]:
                    raise AdmissionDenied("OWNER_CHANGED")
                prior = final["prior"]
                if prior is not None:
                    p, details = final["profile"], prior["details"]
                    if (prior["action"] != "MODEL_PROFILE_APPROVED" or prior["actor_type"] != "USER"
                            or prior["object_type"] != "MODEL_PROFILE" or prior["result"] != "SUCCEEDED"
                            or prior["organization_id"] != scope.organization_id
                            or prior["actor_id"] != scope.user_id or prior["object_id"] != scope.profile_id
                            or not isinstance(details, dict) or details.get("commandSha256") != command_hash
                            or p["status"] not in ("APPROVED", "DEPRECATED", "RETIRED") or p["approved_by"] != scope.user_id
                            or not isinstance(p["approved_at"], str) or details.get("approvedAt") != p["approved_at"]
                            or details.get("profileVersion") != p["profile_version"]
                            or type(details.get("generation")) is not int or details["generation"] < 1):
                        raise AdmissionDenied("DECISION_ID_REUSED")
                    return ProfileApprovalReceipt(command.decision_id, scope.profile_id,
                        details["profileVersion"], details["generation"])
                p, control = final["profile"], final["control"]
                if (p["status"] != "CANDIDATE" or p["profile_version"] != expected.managed_versions.profile_version
                        or profile_snapshot_hash(p["snapshot"]) != command.profile_sha256
                        or control is None or control["blocked"] or final["pending"]
                        or final["generation"] != expected.admission_generation
                        or final["current"] != bytes.fromhex(command.expectation_sha256)):
                    raise AdmissionDenied("STALE_PROFILE_APPROVAL")
                approved_at = (await s.execute(text(
                    "UPDATE platform.model_profiles SET status='APPROVED',approved_by=:u,approved_at=clock_timestamp() "
                    "WHERE id=:p AND status='CANDIDATE' AND (deprecated_at IS NULL OR deprecated_at>clock_timestamp()) "
                    "RETURNING approved_at::text"), {"p": scope.profile_id, "u": scope.user_id})).scalar_one_or_none()
                if not isinstance(approved_at, str):
                    raise AdmissionDenied("STALE_PROFILE_APPROVAL")
                await self._policy.record_allow(request, decision, session=s)
                # Existing audit PK is the replay fence; all data are references
                # and hashes, never the raw evidence or credential/session token.
                details = {"commandSha256": command_hash, "profileSha256": command.profile_sha256,
                           "expectationSha256": command.expectation_sha256, "observationSha256": command.observation_sha256,
                           "bifrostAcceptanceSha256": command.bifrost_acceptance_sha256, "policyVersion": command.policy_version,
                           "sessionId": str(actor.session_id), "databaseLogin": self._owner_login,
                           "profileVersion": p["profile_version"], "generation": final["generation"], "approvedAt": approved_at}
                await s.execute(text(
                    "INSERT INTO audit.audit_events(id,organization_id,occurred_at,actor_type,actor_id,action,object_type,object_id,"
                    "result,reason_code,correlation_id,details) VALUES(:d,:o,clock_timestamp(),'USER',:u,'MODEL_PROFILE_APPROVED',"
                    "'MODEL_PROFILE',:p,'SUCCEEDED','HUMAN_PROFILE_AND_BIFROST_ACCEPTED',:c,CAST(:details AS jsonb))"),
                    {"d": command.decision_id, "o": scope.organization_id, "u": scope.user_id, "p": scope.profile_id,
                     "c": command.correlation_id, "details": canonical_json(details)})
                # Session expiry can advance during DML/audit waits; rollback all
                # writes if the human is no longer live before commit.
                if not hmac.compare_digest(final["subject"], await self._subject(s, actor)):
                    raise AdmissionDenied("OWNER_CHANGED")
                live = (await s.execute(text(
                    "SELECT deprecated_at IS NULL OR deprecated_at>clock_timestamp() FROM platform.model_profiles WHERE id=:p"),
                    {"p": scope.profile_id})).scalar_one()
                if live is not True:
                    raise AdmissionDenied("STALE_PROFILE_APPROVAL")
            return ProfileApprovalReceipt(command.decision_id, scope.profile_id, p["profile_version"], final["generation"])
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None
        except ProblemError:
            raise AdmissionDenied("OWNER_AUTHORIZATION_REFUSED") from None
