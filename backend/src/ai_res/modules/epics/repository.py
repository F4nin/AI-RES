# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Epic aggregate persistence for createEpic (S09): Epic + EpicCreated + outbox in one transaction of the caller."""
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.events.aggregate_events import AggregateKind, EventSpec, append_event
from ai_res.platform.ids import new_id

EPIC_KIND = AggregateKind(aggregate_type="EPIC", table="work.epics", events_table="work.epic_events", fk_column="epic_id", mutable={})
INITIAL_STATUS = "PROPOSED"  # WORKING: the Epic lifecycle vocabulary is not fixed by a normative document (ADR-080); the database accepts any upper-case code


class EpicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, org: UUID, project: UUID, *, title: str, goal: str | None, scope: str | None, created_by: UUID, make_spec: Callable[[UUID], EventSpec]) -> UUID:
        epic_id = new_id()
        await self._s.execute(text(
            "INSERT INTO work.epics (id, organization_id, project_id, title, goal, scope_description, status, created_by) "
            "VALUES (:id, :o, :p, :t, :g, :s, :st, :by)"), {"id": epic_id, "o": org, "p": project, "t": title, "g": goal, "s": scope, "st": INITIAL_STATUS, "by": created_by})
        await append_event(self._s, EPIC_KIND, aggregate_id=epic_id, organization_id=org, project_id=project, operation_id=None, expected_version=1, spec=make_spec(epic_id))
        return epic_id

