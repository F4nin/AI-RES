"""Manager proposals remain drafts. A separate human command refers to exact stored content."""
import hashlib
import hmac
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.platform.human_approval import require_approval_binding, require_human_approver
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyDecision, Principal, ServiceIdentity
from ai_res.platform.problems import ErrorCode, ProblemError


@dataclass(frozen=True, slots=True)
class ProposalContent:
    goal: str | None
    scope: str | None
    primary_question: str | None
    context_version_id: UUID | None = None

    def digest(self) -> bytes:
        parts = asdict(self)
        context = parts.pop("context_version_id")
        if context is not None:
            parts["context_version_id"] = str(context)
        return hashlib.sha256(canonical_json(parts).encode()).digest()


@dataclass(frozen=True, slots=True)
class ProposalVersionRef:
    id: UUID
    content_hash: bytes


class HumanDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class ManagerProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def propose(
        self, organization_id: UUID, project_id: UUID, interaction_id: UUID, content: ProposalContent,
    ) -> ProposalVersionRef:
        digest = content.digest()
        version = new_id()
        result = await self._session.execute(text("""
            INSERT INTO work.manager_proposal_versions (
                id,organization_id,project_id,interaction_id,goal,scope,primary_question,content_hash,context_version_id
            ) VALUES (:id,:org,:project,:interaction,:goal,:scope,:primary_question,:digest,:context_version_id)
            ON CONFLICT (interaction_id) DO NOTHING RETURNING id
        """), {"id": version, "org": organization_id, "project": project_id, "interaction": interaction_id,
               "digest": digest, **asdict(content)})
        if result.scalar_one_or_none() is None:
            saved = (await self._session.execute(text("""
                SELECT id,content_hash FROM work.manager_proposal_versions WHERE interaction_id=:interaction
            """), {"interaction": interaction_id})).one_or_none()
            if saved is None or not hmac.compare_digest(bytes(saved.content_hash), digest):
                raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "A different proposal was already recorded.")
            version = saved.id
        return ProposalVersionRef(version, digest)

    async def record_human_decision(
        self, organization_id: UUID, project_id: UUID, version: ProposalVersionRef, decision: HumanDecision,
        actor: Principal | ServiceIdentity, policy: PolicyDecision, *, require_separation: bool, comment: str | None,
        correlation_id: UUID | None = None,
    ) -> UUID:
        """Caller obtains the Principal and decision from authenticated session and exact-target Policy."""
        approved_by = require_human_approver(actor, policy)
        row = (await self._session.execute(text("""
            SELECT p.content_hash,i.author_id FROM work.manager_proposal_versions p
            JOIN work.manager_interactions i ON i.id=p.interaction_id
            WHERE p.id=:id AND p.organization_id=:org AND p.project_id=:project
        """), {"id": version.id, "org": organization_id, "project": project_id})).one_or_none()
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Proposal not found.")
        require_approval_binding(
            approved_by, bytes(row.content_hash), version.content_hash, conflict_message="Proposal version changed.",
            excluded_approver=row.author_id if require_separation else None,
        )
        ref = new_id()
        recorded = await self._session.execute(text("""
            INSERT INTO governance.manager_proposal_decisions (
                id,organization_id,project_id,proposal_version_id,content_hash,approver_id,decision,comment
            ) VALUES (:id,:org,:project,:version,:digest,:actor,:decision,:comment)
            ON CONFLICT (proposal_version_id) DO NOTHING RETURNING id
        """), {"id": ref, "org": organization_id, "project": project_id, "version": version.id,
               "digest": version.content_hash, "actor": approved_by, "decision": decision.value, "comment": comment})
        if recorded.scalar_one_or_none() is None:
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "A decision was already recorded.")
        await SqlAuditWriter(self._session).write(AuditRecord(
            action="MANAGER_PROPOSAL_DECISION", outcome=AuditOutcome.SUCCEEDED, resource_type="MANAGER_PROPOSAL_VERSION",
            actor_id=str(approved_by), organization_id=str(organization_id), project_id=str(project_id),
            resource_id=str(version.id), policy_version=policy.policy_version,
            request_id=None if correlation_id is None else str(correlation_id),
            details={"decisionId": str(ref), "decision": decision.value},
        ))
        return ref

    async def approved_plan_origin(
        self, proposal_id: UUID, epic_id: UUID, *, goal: str, scope: str | None,
    ) -> tuple[UUID, str]:
        """Resolve immutable approval inside the caller's authorized tenant transaction."""
        row = (await self._session.execute(text("""
            SELECT p.goal,p.scope,p.content_hash,d.id AS decision_id
            FROM work.manager_proposal_versions p
            JOIN work.manager_interactions i ON (i.organization_id,i.project_id,i.id)
                =(p.organization_id,p.project_id,p.interaction_id)
            LEFT JOIN governance.manager_proposal_decisions d ON (d.organization_id,d.project_id,d.proposal_version_id,d.content_hash)
                =(p.organization_id,p.project_id,p.id,p.content_hash) AND d.decision='APPROVE' AND d.approver_id<>i.author_id
            WHERE p.id=:proposal AND i.epic_id=:epic
        """), {"proposal": proposal_id, "epic": epic_id})).one_or_none()
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Proposal not found.")
        if row.decision_id is None:
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "An independently approved Proposal is required.")
        if row.goal != goal or row.scope != scope:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Plan goal and scope must match the approved Proposal.")
        return row.decision_id, bytes(row.content_hash).hex()
