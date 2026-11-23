"""Rebuild the intake and planning state of an already authorized Epic."""
import hashlib
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json


@dataclass(frozen=True, slots=True)
class IntakeState:
    interaction_id: UUID
    received_event_id: UUID
    operation_id: UUID
    operation_status: str
    operation_version: int


@dataclass(frozen=True, slots=True)
class ProposalState:
    version_id: UUID
    interaction_id: UUID
    decision_id: UUID | None
    decision: str | None


@dataclass(frozen=True, slots=True)
class PlanState:
    version_id: UUID
    version_number: int
    decision_id: UUID | None
    decision: str | None


@dataclass(frozen=True, slots=True, repr=False)
class ManagerEpicState:
    epic_id: UUID
    epic_version: int
    status: str
    goal: str | None
    scope: str | None
    intake: IntakeState | None
    proposal: ProposalState | None
    question_sequence: int
    open_question_id: UUID | None
    plan: PlanState | None
    task_counts: tuple[tuple[str, int], ...]
    snapshot_version: str


@dataclass(frozen=True, slots=True)
class ManagerEpicMetadata:
    epic_version: int
    epic_status: str
    operation_version: int
    operation_status: str
    question_sequence: int
    has_open_question: bool
    plan_version: int | None
    plan_decision: str | None
    task_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class AssignedEpicMetadata:
    version: str
    state: ManagerEpicMetadata


_EPIC_INTAKE = """
    FROM work.epics e
    LEFT JOIN LATERAL (
        SELECT i.id AS interaction_id, received.event_id AS received_event_id, i.operation_id,
               o.status AS operation_status, o.row_version AS operation_version
        FROM work.manager_interactions i
        JOIN work.manager_interaction_events received ON received.interaction_id=i.id
            AND received.aggregate_sequence=1 AND received.event_type='manager.interaction.received'
        JOIN operations.operations o ON o.organization_id=i.organization_id
            AND o.project_id=i.project_id AND o.id=i.operation_id
        WHERE (i.organization_id, i.project_id, i.epic_id)=(e.organization_id, e.project_id, e.id)
          AND (CAST(:assigned_operation AS uuid) IS NULL OR i.operation_id=:assigned_operation)
        ORDER BY i.created_at DESC, i.id DESC LIMIT 1
    ) intake ON true
"""

_EPIC_PROPOSAL = """
    LEFT JOIN LATERAL (
        SELECT v.id AS version_id, i.id AS interaction_id, d.id AS decision_id, d.decision
        FROM work.manager_interactions i
        JOIN work.manager_proposal_versions v ON (v.organization_id, v.project_id, v.interaction_id)
            =(i.organization_id, i.project_id, i.id)
        LEFT JOIN governance.manager_proposal_decisions d ON (d.organization_id, d.project_id, d.proposal_version_id)
            =(v.organization_id, v.project_id, v.id)
        WHERE (i.organization_id, i.project_id, i.epic_id)=(e.organization_id, e.project_id, e.id)
        ORDER BY i.created_at DESC, i.id DESC LIMIT 1
    ) proposal ON true
"""

_EPIC_PROGRESS = """
    LEFT JOIN LATERAL (
        SELECT j.sequence, CASE WHEN j.event_kind='PROPOSED' THEN j.question_id END AS open_question_id
        FROM work.manager_question_journal j
        WHERE (j.organization_id, j.project_id, j.epic_id)=(e.organization_id, e.project_id, e.id)
        ORDER BY j.sequence DESC LIMIT 1
    ) question ON true
    LEFT JOIN LATERAL (
        SELECT v.id AS version_id, v.version_number, d.id AS decision_id, d.decision
        FROM work.plans p
        JOIN work.plan_versions v ON (v.organization_id, v.project_id, v.plan_id)
            =(p.organization_id, p.project_id, p.id) AND v.version_number=p.last_version
        LEFT JOIN governance.plan_version_decisions d ON (d.organization_id, d.project_id, d.plan_version_id)
            =(v.organization_id, v.project_id, v.id)
        WHERE (p.organization_id, p.project_id, p.epic_id)=(e.organization_id, e.project_id, e.id)
    ) plan ON true
    LEFT JOIN LATERAL (
        SELECT jsonb_object_agg(status, task_count) AS counts
        FROM (
            SELECT t.status, COUNT(*) AS task_count
            FROM work.tasks t
            WHERE (t.organization_id, t.project_id, t.epic_id)=(e.organization_id, e.project_id, e.id)
            GROUP BY t.status
        ) statuses
    ) tasks ON true
"""

_EPIC_STATE = text(f"""
    SELECT e.id, e.row_version, e.status, e.goal, e.scope_description,
           intake.interaction_id, intake.received_event_id, intake.operation_id,
           intake.operation_status, intake.operation_version,
           proposal.version_id AS proposal_version_id, proposal.interaction_id AS proposal_interaction_id,
           proposal.decision_id AS proposal_decision_id, proposal.decision AS proposal_decision,
           COALESCE(question.sequence, 0) AS question_sequence, question.open_question_id,
           plan.version_id AS plan_version_id, plan.version_number, plan.decision_id AS plan_decision_id,
           plan.decision AS plan_decision, tasks.counts AS task_counts
    {_EPIC_INTAKE}
    {_EPIC_PROPOSAL}
    {_EPIC_PROGRESS}
    WHERE e.id=:epic_id
""")

_ASSIGNED_EPIC_METADATA = text(f"""
    SELECT e.row_version, e.status, intake.operation_version, intake.operation_status,
           COALESCE(question.sequence, 0) AS question_sequence,
           (question.open_question_id IS NOT NULL) AS has_open_question,
           plan.version_number, plan.decision, tasks.counts AS task_counts
    {_EPIC_INTAKE}
    {_EPIC_PROGRESS}
    WHERE e.id=:epic_id AND intake.operation_id=:assigned_operation
""")


async def load_manager_epic_state(
    session: AsyncSession, epic_id: UUID, *, assigned_operation: UUID | None = None,
) -> ManagerEpicState | None:
    """Use one PostgreSQL snapshot. Caller owns Policy checks and tenant scope."""
    row = (await session.execute(_EPIC_STATE, {"epic_id": epic_id, "assigned_operation": assigned_operation})).one_or_none()
    if row is None or (assigned_operation is not None and row.operation_id is None):
        return None
    intake = None if row.interaction_id is None else IntakeState(
        row.interaction_id, row.received_event_id, row.operation_id, row.operation_status, row.operation_version,
    )
    proposal = None if row.proposal_version_id is None else ProposalState(
        row.proposal_version_id, row.proposal_interaction_id, row.proposal_decision_id, row.proposal_decision,
    )
    plan = None if row.plan_version_id is None else PlanState(
        row.plan_version_id, row.version_number, row.plan_decision_id, row.plan_decision,
    )
    snapshot = {name: str(value) if isinstance(value, UUID) else value for name, value in row._mapping.items()}
    version = hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
    return ManagerEpicState(
        row.id, row.row_version, row.status, row.goal, row.scope_description, intake, proposal,
        row.question_sequence, row.open_question_id, plan, tuple(sorted((row.task_counts or {}).items())), f"1:{version}",
    )


async def load_assigned_epic_metadata(session: AsyncSession, epic_id: UUID, operation_id: UUID) -> AssignedEpicMetadata | None:
    """Read only the permitted metadata. Caller owns the tenant and assignment authority."""
    row = (await session.execute(_ASSIGNED_EPIC_METADATA, {"epic_id": epic_id, "assigned_operation": operation_id})).one_or_none()
    if row is None:
        return None
    view = ManagerEpicMetadata(
        row.row_version, row.status, row.operation_version, row.operation_status,
        row.question_sequence, row.has_open_question, row.version_number, row.decision,
        tuple(sorted((row.task_counts or {}).items())),
    )
    payload = {"epicId": str(epic_id), "operationId": str(operation_id), "metadata": asdict(view)}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return AssignedEpicMetadata(f"1:{digest}", view)
