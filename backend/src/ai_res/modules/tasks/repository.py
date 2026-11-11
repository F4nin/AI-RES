# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Epic / Task / TaskDependency persistence. A Task always belongs to an open Operation (ADR-012): the database rejects anything else."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import bind_value, cas_update
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError

EPIC_UPDATABLE: Mapping[str, str | None] = {"title": None, "goal": None, "scope_description": None, "outcome_criteria": None, "status": None, "priority": None,
                                            "owner_user_id": None, "updated_by": None}
TASK_UPDATABLE: Mapping[str, str | None] = {"title": None, "description": None, "acceptance_criteria": "jsonb", "status": None, "priority": None,
                                            "owner_user_id": None, "updated_by": None}


@dataclass(frozen=True)
class NewEpic:
    organization_id: UUID
    project_id: UUID
    title: str
    status: str
    goal: str | None = None
    created_by: UUID | None = None


@dataclass(frozen=True)
class NewTask:
    organization_id: UUID
    project_id: UUID
    operation_id: UUID
    epic_id: UUID
    task_type: str
    title: str
    status: str
    initiator_type: str
    description: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    priority: str | None = None
    derived_from_task_id: UUID | None = None
    initiator_id: UUID | None = None
    created_by: UUID | None = None


@dataclass(frozen=True)
class TaskRow:
    id: UUID
    operation_id: UUID
    epic_id: UUID
    status: str
    title: str
    row_version: int
    derived_from_task_id: UUID | None


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_epic(self, new: NewEpic) -> UUID:
        eid = new_id()
        await self._s.execute(text("INSERT INTO work.epics (id, organization_id, project_id, title, goal, status, created_by) VALUES (:id, :org, :prj, :title, :goal, :status, :by)"),
                              {"id": eid, "org": new.organization_id, "prj": new.project_id, "title": new.title, "goal": new.goal, "status": new.status, "by": new.created_by})
        return eid

    async def create_task(self, new: NewTask) -> TaskRow:
        tid = new_id()
        await self._s.execute(text(
            "INSERT INTO work.tasks (id, organization_id, project_id, operation_id, epic_id, derived_from_task_id, task_type, title, description, acceptance_criteria, status, "
            "priority, initiator_type, initiator_id, created_by) VALUES (:id, :org, :prj, :op, :epic, :derived, :ttype, :title, :descr, CAST(:ac AS jsonb), :status, :prio, :itype, "
            ":iid, :by)"),
            {"id": tid, "org": new.organization_id, "prj": new.project_id, "op": new.operation_id, "epic": new.epic_id, "derived": new.derived_from_task_id,
             "ttype": new.task_type, "title": new.title, "descr": new.description, "ac": bind_value(list(new.acceptance_criteria), "jsonb"), "status": new.status,
             "prio": new.priority, "itype": new.initiator_type, "iid": new.initiator_id, "by": new.created_by})
        task = await self.get_task(tid)
        if task is None:
            raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
        return task

    async def get_task(self, task_id: UUID) -> TaskRow | None:
        r = (await self._s.execute(text("SELECT id, operation_id, epic_id, status, title, row_version, derived_from_task_id FROM work.tasks WHERE id = :id"),
                                   {"id": task_id})).mappings().first()
        return None if r is None else TaskRow(**r)

    async def update_task(self, task_id: UUID, expected_version: int, **changes: Any) -> int:
        if not changes:
            raise ValueError("nothing to update")
        return await cas_update(self._s, "work.tasks", task_id, expected_version, changes, TASK_UPDATABLE)

    async def update_epic(self, epic_id: UUID, expected_version: int, **changes: Any) -> int:
        return await cas_update(self._s, "work.epics", epic_id, expected_version, changes, EPIC_UPDATABLE)

    async def add_dependency(self, organization_id: UUID, project_id: UUID, task_id: UUID, depends_on_task_id: UUID, created_by: UUID | None = None) -> UUID:
        """Cycle detection is the planner's deterministic check before plan activation (Domain Model §16); the database blocks self/duplicate/cross-project."""
        did = new_id()
        await self._s.execute(text("INSERT INTO work.task_dependencies (id, organization_id, project_id, task_id, depends_on_task_id, created_by) VALUES (:id, :org, :prj, :t, :d, :by)"),
                              {"id": did, "org": organization_id, "prj": project_id, "t": task_id, "d": depends_on_task_id, "by": created_by})
        return did
