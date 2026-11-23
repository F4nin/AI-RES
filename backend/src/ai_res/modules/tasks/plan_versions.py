"""Immutable planning snapshots and dependency-closed exact-version decisions."""
import hashlib
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.events.aggregate_events import AggregateKind, EventSpec, append_event
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.tasks.plan_graph import PlanDependency, PlanGraph, PlanGraphError
from ai_res.platform.human_approval import require_approval_binding, require_human_approver
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyDecision, Principal, ServiceIdentity
from ai_res.platform.problems import ErrorCode, ProblemError

_PLAN_VERSION = AggregateKind(
    "PLAN_VERSION", "work.plan_versions", "work.plan_version_events", "plan_version_id", {},
)


class PlanItemSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    task_type: str = Field(pattern=r"^[A-Z][A-Z_]*$")
    predecessors: tuple[UUID, ...] = ()
    rationale: str | None = None
    description: str | None = None
    expected_output: str | None = None
    acceptance_criteria: tuple[str, ...] = ()

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, title: str) -> str:
        if not title.strip():
            raise ValueError("PlanItem title must not be blank")
        return title

    @field_validator("predecessors")
    @classmethod
    def unique_predecessors(cls, ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(ids) != len(set(ids)):
            raise ValueError("PlanItem predecessors must be unique")
        return ids


class PlanProposalOrigin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    proposal_version_id: UUID
    decision_id: UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    goal: str
    scope: str | None = None
    rationale: str | None = None
    items: tuple[PlanItemSpec, ...]
    entries: tuple[UUID, ...]
    proposal_origin: PlanProposalOrigin | None = None

    @field_validator("entries")
    @classmethod
    def unique_entries(cls, ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(ids) != len(set(ids)):
            raise ValueError("Plan entries must be unique")
        return ids

    def graph(self) -> PlanGraph:
        return PlanGraph(tuple(PlanDependency(item.id, frozenset(item.predecessors)) for item in self.items), frozenset(self.entries))


class PlanVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def propose(
        self, organization_id: UUID, project_id: UUID, epic_id: UUID, snapshot: PlanSnapshot, *, correlation_id: UUID | None = None,
        actor_id: UUID | None = None, expected_version: int | None = None,
    ) -> tuple[UUID, bytes]:
        try:
            snapshot.graph().order()
        except PlanGraphError as error:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, f"Invalid plan graph: {error.code.value}.") from None
        # Preserve the stored representation and hash for plans without a Proposal.
        body = canonical_json(snapshot.model_dump(mode="json", exclude={"proposal_origin"} if snapshot.proposal_origin is None else None))
        digest = hashlib.sha256(body.encode()).digest()
        await self._s.execute(text("""
            INSERT INTO work.plans (id,organization_id,project_id,epic_id)
            VALUES (:id,:org,:project,:epic) ON CONFLICT (organization_id,project_id,epic_id) DO NOTHING
        """), {"id": new_id(), "org": organization_id, "project": project_id, "epic": epic_id})
        plan = (await self._s.execute(text("""
            UPDATE work.plans SET last_version=last_version+1
            WHERE organization_id=:org AND project_id=:project AND epic_id=:epic
                AND (CAST(:expected AS integer) IS NULL OR last_version=:expected)
            RETURNING id,last_version
        """), {"org": organization_id, "project": project_id, "epic": epic_id, "expected": expected_version})).one_or_none()
        if plan is None:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "Plan version changed.")
        version = new_id()
        await self._s.execute(text("""
            INSERT INTO work.plan_versions(id,organization_id,project_id,plan_id,version_number,content_hash,snapshot)
            VALUES (:id,:org,:project,:plan,:sequence,:hash,CAST(:snapshot AS jsonb))
        """), {"id": version, "org": organization_id, "project": project_id, "plan": plan.id, "sequence": plan.last_version,
               "hash": digest, "snapshot": body})
        await append_event(
            self._s, _PLAN_VERSION, aggregate_id=version, organization_id=organization_id, project_id=project_id,
            operation_id=None, expected_version=1,
            spec=EventSpec("plan.version.proposed", 1, "MANAGER" if actor_id is None else "USER", correlation_id or new_id(), (DOMAIN_DESTINATION,),
                           actor_id=actor_id,
                           data={"planId": str(plan.id), "planVersionId": str(version), "epicId": str(epic_id)}),
        )
        return version, digest

    async def decide(
        self, organization_id: UUID, project_id: UUID, version_id: UUID, content_hash: bytes,
        actor: Principal | ServiceIdentity, policy: PolicyDecision, *, decision: str, approved: frozenset[UUID],
        comment: str | None, expected_version: int | None = None,
        correlation_id: UUID | None = None,
    ) -> UUID:
        actor_id = require_human_approver(actor, policy)
        version = (await self._s.execute(text("""
            SELECT v.content_hash,v.snapshot,v.version_number,v.row_version,p.epic_id
            FROM work.plan_versions v JOIN work.plans p ON p.id=v.plan_id
            WHERE v.id=:id AND v.organization_id=:org AND v.project_id=:project
        """), {"id": version_id, "org": organization_id, "project": project_id})).one_or_none()
        if version is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Plan version not found.")
        if expected_version is not None and version.version_number != expected_version:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "Plan version changed.")
        require_approval_binding(actor_id, bytes(version.content_hash), content_hash, conflict_message="Plan version changed.")
        snapshot = PlanSnapshot.model_validate(version.snapshot)
        if decision == "APPROVE":
            try:
                snapshot.graph().validate_approval(approved)
            except PlanGraphError as error:
                raise ProblemError(ErrorCode.VALIDATION_ERROR, f"Invalid approved set: {error.code.value}.") from None
        elif approved or decision not in {"REJECT", "REQUEST_CHANGES"}:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid plan decision.")
        decision_id = new_id()
        result = await self._s.execute(text("""
            INSERT INTO governance.plan_version_decisions (
                id,organization_id,project_id,plan_version_id,content_hash,approver_id,decision,approved_items,comment
            ) VALUES (:id,:org,:project,:version,:hash,:actor,:decision,:items,:comment)
            ON CONFLICT (plan_version_id) DO NOTHING RETURNING id
        """), {"id": decision_id, "org": organization_id, "project": project_id, "version": version_id, "hash": content_hash,
               "actor": actor_id, "decision": decision, "items": sorted(approved), "comment": comment})
        if result.scalar_one_or_none() is None:
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "A decision was already recorded.")
        correlation = correlation_id or new_id()
        if decision in {"APPROVE", "REJECT"}:
            event_type, actor_key = ("plan.version.approved", "approvedBy") if decision == "APPROVE" else ("plan.version.rejected", "rejectedBy")
            await append_event(
                self._s, _PLAN_VERSION, aggregate_id=version_id, organization_id=organization_id, project_id=project_id,
                operation_id=None, expected_version=version.row_version,
                spec=EventSpec(event_type, 1, "USER", correlation, (DOMAIN_DESTINATION,), actor_id=actor_id,
                               data={"epicId": str(version.epic_id), "planVersionId": str(version_id), actor_key: str(actor_id)}),
            )
        await SqlAuditWriter(self._s).write(AuditRecord(
            action="PLAN_VERSION_DECISION", outcome=AuditOutcome.SUCCEEDED, resource_type="PLAN_VERSION",
            actor_id=str(actor_id), organization_id=str(organization_id), project_id=str(project_id),
            resource_id=str(version_id), policy_version=policy.policy_version, request_id=str(correlation),
            details={"decisionId": str(decision_id), "decision": decision},
        ))
        return decision_id
