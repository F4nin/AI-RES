"""Tenant-scoped persistence. Text stays in domain storage; orchestration and audit get refs."""
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.events.aggregate_events import AggregateKind, EventSpec, append_event
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.platform.ids import new_id

INTERACTION_KIND = AggregateKind(
    aggregate_type="MANAGER_INTERACTION", table="work.manager_interactions",
    events_table="work.manager_interaction_events", fk_column="interaction_id", mutable={},
)


class ResponseMode(StrEnum):
    NORMAL = "NORMAL"
    PROPOSE_PLAN = "PROPOSE_PLAN"
    CLARIFICATION = "CLARIFICATION"
    REVIEW_RESULT = "REVIEW_RESULT"


@dataclass(frozen=True, slots=True)
class ManagerMessage:
    text: str
    attachment_versions: tuple[UUID, ...] = ()
    expected_response_mode: ResponseMode | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.text) <= 20_000 or "\x00" in self.text:
            raise ValueError("message must contain 1 to 20000 compatible characters")


@dataclass(frozen=True, slots=True)
class ManagerInteraction:
    id: UUID
    organization_id: UUID
    project_id: UUID
    epic_id: UUID
    operation_id: UUID
    author_id: UUID
    message: ManagerMessage


class ManagerInteractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self, *, organization_id: UUID, project_id: UUID, epic_id: UUID, operation_id: UUID,
        author_id: UUID, message: ManagerMessage, correlation_id: UUID, causation_id: UUID,
    ) -> UUID:
        interaction_id = new_id()
        await self._session.execute(text("""
            INSERT INTO work.manager_interactions (
                id,organization_id,project_id,epic_id,operation_id,author_id,message,expected_response_mode
            ) VALUES (:id,:org,:project,:epic,:operation,:author,:message,:mode)
        """), {"id": interaction_id, "org": organization_id, "project": project_id, "epic": epic_id,
               "operation": operation_id, "author": author_id, "message": message.text,
               "mode": None if message.expected_response_mode is None else message.expected_response_mode.value})
        if message.attachment_versions:
            await self._session.execute(text("""
                INSERT INTO work.manager_interaction_attachments (organization_id,project_id,interaction_id,ordinal,source_version_id)
                VALUES (:org,:project,:id,:ordinal,:version)
            """), [{"org": organization_id, "project": project_id, "id": interaction_id, "ordinal": ordinal, "version": version}
                    for ordinal, version in enumerate(message.attachment_versions)])
        await append_event(
            self._session, INTERACTION_KIND, aggregate_id=interaction_id, organization_id=organization_id,
            project_id=project_id, operation_id=None, expected_version=1,
            spec=EventSpec("manager.interaction.received", 1, "USER", correlation_id, (DOMAIN_DESTINATION,),
                           data={"interactionId": str(interaction_id)}, actor_id=author_id, causation_id=causation_id),
        )
        return interaction_id

    async def get(self, interaction_id: UUID) -> ManagerInteraction | None:
        row = (await self._session.execute(text("""
            SELECT id,organization_id,project_id,epic_id,operation_id,author_id,message,expected_response_mode
            FROM work.manager_interactions WHERE id = :id
        """), {"id": interaction_id})).one_or_none()
        if row is None:
            return None
        refs = await self._session.execute(text("""
            SELECT source_version_id FROM work.manager_interaction_attachments WHERE interaction_id = :id ORDER BY ordinal
        """), {"id": interaction_id})
        mode = None if row.expected_response_mode is None else ResponseMode(row.expected_response_mode)
        return ManagerInteraction(
            row.id, row.organization_id, row.project_id, row.epic_id, row.operation_id, row.author_id,
            ManagerMessage(row.message, tuple(refs.scalars()), mode),
        )
