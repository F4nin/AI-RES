# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Project aggregate persistence for the write commands (S09, ADR-078..). Creation and metadata change are ONE transaction of the caller:
projection + aggregate event (only where AsyncAPI v1.6 defines one) + outbox. Metadata change is a compare-and-swap on `row_version` (If-Match).
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import cas_update
from ai_res.modules.events.aggregate_events import AggregateKind, EventSpec, append_event
from ai_res.platform.ids import new_id

PROJECT_KIND = AggregateKind(aggregate_type="PROJECT", table="project.projects", events_table="project.project_events", fk_column="project_id", mutable={})
METADATA_COLUMNS = {"name": None, "description": None, "goal": None}
INITIAL_ROLE = "PROJECT_ADMIN"  # WORKING (ADR-083, OD-18): the creating human becomes the first project administrator


@dataclass(frozen=True)
class ProjectRow:
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    goal: str | None
    project_type: str
    status: str
    row_version: int
    created_at: Any
    updated_at: Any


_COLUMNS = "id, organization_id, name, description, goal, project_type, status, row_version, created_at, updated_at"


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, project_id: UUID) -> ProjectRow | None:
        r = (await self._s.execute(text(f"SELECT {_COLUMNS} FROM project.projects WHERE id = :id"), {"id": project_id})).mappings().first()  # noqa: S608
        return None if r is None else ProjectRow(**r)

    async def exists(self, project_id: UUID) -> bool:
        return (await self._s.execute(text("SELECT 1 FROM project.projects WHERE id = :id"), {"id": project_id})).first() is not None

    async def create(self, project_id: UUID, org: UUID, *, name: str, description: str | None, goal: str | None, project_type: str, creator: UUID,
                     created: EventSpec) -> ProjectRow:
        """Project + first administrator membership + ProjectCreated + outbox. The caller's tenant context is (org, project_id)."""
        await self._s.execute(text("INSERT INTO project.projects (id, organization_id, name, description, goal, project_type) VALUES (:id, :o, :n, :d, :g, :t)"),
                              {"id": project_id, "o": org, "n": name, "d": description, "g": goal, "t": project_type})
        await self._s.execute(text("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (:id, :o, :p, :u, :r)"),
                              {"id": new_id(), "o": org, "p": project_id, "u": creator, "r": INITIAL_ROLE})
        await append_event(self._s, PROJECT_KIND, aggregate_id=project_id, organization_id=org, project_id=project_id, operation_id=None, expected_version=1, spec=created)
        row = await self.get(project_id)
        assert row is not None  # written by this transaction  # noqa: S101
        return row

    async def update_metadata(self, project_id: UUID, expected_version: int, changes: dict[str, Any]) -> ProjectRow:
        """No event: AsyncAPI v1.6 defines no project-updated message and events without a contract are not invented (ADR-079); the audit row is the record."""
        await cas_update(self._s, "project.projects", project_id, expected_version, changes, METADATA_COLUMNS)
        row = await self.get(project_id)
        assert row is not None  # noqa: S101
        return row


def new_project_id() -> UUID:
    return new_id()
