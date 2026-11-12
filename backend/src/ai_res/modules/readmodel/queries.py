# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Read-only query services for the Public API GET operations (S08, ADR-074).

Every function receives a session that is ALREADY inside a transaction-local tenant context and returns plain mappings of exactly the columns the
DTO mappers need (never ORM entities). Authorization is decided by the caller (Policy Engine); RLS only narrows further. Lists are keyset-paged on a
stable total order and fetch limit+1 rows so `hasMore` needs no count query.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

Row = Mapping[str, Any]


@dataclass(frozen=True)
class Slice:
    """limit+1 fetch result: `items` holds at most `limit` rows, `has_more` says whether another page exists."""
    items: list[Row]
    has_more: bool


def _slice(rows: Sequence[Row], limit: int) -> Slice:
    return Slice([dict(r) for r in rows[:limit]], len(rows) > limit)


def parse_ts_keyset(after: list[Any] | None) -> tuple[datetime | None, UUID | None]:
    """Keyset [iso timestamp, uuid]; the cursor is HMAC-signed so a malformed one is a bug or tampering, both -> ValueError -> invalid cursor."""
    if after is None:
        return None, None
    if len(after) != 2 or not isinstance(after[0], str) or not isinstance(after[1], str):
        raise ValueError("malformed keyset")
    return datetime.fromisoformat(after[0]), UUID(after[1])


def parse_num_keyset(after: list[Any] | None) -> tuple[int | None, UUID | None]:
    if after is None:
        return None, None
    if len(after) != 2 or not isinstance(after[0], int) or isinstance(after[0], bool) or not isinstance(after[1], str):
        raise ValueError("malformed keyset")
    return after[0], UUID(after[1])


class ReadQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _all(self, sql: str, params: dict[str, Any]) -> list[Row]:
        return [dict(r) for r in (await self._s.execute(text(sql), params)).mappings().all()]

    async def _one(self, sql: str, params: dict[str, Any]) -> Row | None:
        row = (await self._s.execute(text(sql), params)).mappings().first()
        return None if row is None else dict(row)

    # -- projects ---------------------------------------------------------------------------------------------------------------------------------
    async def visible_projects(self, org: UUID, actor: UUID, *, plain_roles: Sequence[str], privileged_roles: Sequence[str], org_roles: Sequence[str],
                               mfa_verified: bool, limit: int, after: list[Any] | None = None, only: UUID | None = None) -> Slice:
        """Projects the actor may read, mirroring PolicyEngine.decide for `project.read` (active user, no revoked organization membership, a granting
        project/org role; privileged roles count only with a verified second factor). A consistency test pins this SQL to the engine decision."""
        ts, pid = parse_ts_keyset(after)
        rows = await self._all(
            "SELECT p.id, p.organization_id, p.name, p.description, p.goal, p.project_type, p.status, p.row_version, p.created_at, p.updated_at "
            "FROM project.projects p JOIN iam.users u ON u.organization_id = p.organization_id AND u.id = :actor AND u.status = 'ACTIVE' "
            "LEFT JOIN organization.memberships m ON m.organization_id = p.organization_id AND m.user_id = u.id "
            "LEFT JOIN project.project_memberships pm ON pm.organization_id = p.organization_id AND pm.project_id = p.id AND pm.user_id = u.id AND pm.status = 'ACTIVE' "
            "WHERE p.organization_id = :org AND COALESCE(m.status, 'ACTIVE') = 'ACTIVE' "
            "AND (pm.role_code = ANY(:plain) OR (:mfa AND pm.role_code = ANY(:priv)) OR (m.status = 'ACTIVE' AND m.role_code = ANY(:orgr) AND (:mfa OR m.role_code <> ALL(:priv)))) "
            "AND (CAST(:only AS uuid) IS NULL OR p.id = :only) "
            "AND (CAST(:ts AS timestamptz) IS NULL OR (p.created_at, p.id) > (CAST(:ts AS timestamptz), CAST(:pid AS uuid))) "
            "ORDER BY p.created_at, p.id LIMIT :lim",
            {"org": org, "actor": actor, "plain": list(plain_roles), "priv": list(privileged_roles), "orgr": list(org_roles), "mfa": mfa_verified,
             "only": only, "ts": ts, "pid": pid, "lim": limit + 1})
        return _slice(rows, limit)

    async def get_project(self, project_id: UUID) -> Row | None:
        return await self._one("SELECT id, organization_id, name, description, goal, project_type, status, row_version, created_at, updated_at FROM project.projects WHERE id = :i", {"i": project_id})

    # -- work -------------------------------------------------------------------------------------------------------------------------------------
    async def list_epics(self, project_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        ts, eid = parse_ts_keyset(after)
        return _slice(await self._all(
            "SELECT id, project_id, title, goal, status, created_at FROM work.epics WHERE project_id = :p "
            "AND (CAST(:ts AS timestamptz) IS NULL OR (created_at, id) > (CAST(:ts AS timestamptz), CAST(:e AS uuid))) ORDER BY created_at, id LIMIT :lim",
            {"p": project_id, "ts": ts, "e": eid, "lim": limit + 1}), limit)

    async def get_epic(self, epic_id: UUID) -> Row | None:
        return await self._one("SELECT id, project_id, title, goal, status FROM work.epics WHERE id = :i", {"i": epic_id})

    async def list_tasks(self, epic_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        ts, tid = parse_ts_keyset(after)
        return _slice(await self._all(
            "SELECT id, epic_id, title, status, priority, created_at FROM work.tasks WHERE epic_id = :e "
            "AND (CAST(:ts AS timestamptz) IS NULL OR (created_at, id) > (CAST(:ts AS timestamptz), CAST(:t AS uuid))) ORDER BY created_at, id LIMIT :lim",
            {"e": epic_id, "ts": ts, "t": tid, "lim": limit + 1}), limit)

    async def get_task(self, task_id: UUID) -> Row | None:
        return await self._one("SELECT id, project_id, epic_id, title, status, priority, row_version FROM work.tasks WHERE id = :i", {"i": task_id})

    # -- requirements -----------------------------------------------------------------------------------------------------------------------------
    async def list_requirements(self, project_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        n, rid = parse_num_keyset(after)
        return _slice(await self._all(
            "SELECT r.id, r.project_id, r.display_number, r.current_version_id, v.status AS lifecycle_status FROM requirements.requirements r "
            "JOIN requirements.requirement_versions v ON v.id = r.current_version_id WHERE r.project_id = :p "
            "AND (CAST(:n AS bigint) IS NULL OR (r.display_number, r.id) > (CAST(:n AS bigint), CAST(:r AS uuid))) ORDER BY r.display_number, r.id LIMIT :lim",
            {"p": project_id, "n": n, "r": rid, "lim": limit + 1}), limit)

    async def get_requirement(self, requirement_id: UUID) -> Row | None:
        return await self._one(
            "SELECT r.id, r.project_id, r.display_number, r.current_version_id, r.row_version, v.status AS lifecycle_status FROM requirements.requirements r "
            "JOIN requirements.requirement_versions v ON v.id = r.current_version_id WHERE r.id = :i", {"i": requirement_id})

    async def get_requirement_version(self, version_id: UUID) -> Row | None:
        return await self._one("SELECT id, requirement_id, version_number, statement, change_reason FROM requirements.requirement_versions WHERE id = :i", {"i": version_id})

    async def list_requirement_versions(self, requirement_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        n, vid = parse_num_keyset(after)
        return _slice(await self._all(
            "SELECT id, requirement_id, version_number, statement, change_reason FROM requirements.requirement_versions WHERE requirement_id = :r "
            "AND (CAST(:n AS integer) IS NULL OR (version_number, id) > (CAST(:n AS integer), CAST(:v AS uuid))) ORDER BY version_number, id LIMIT :lim",
            {"r": requirement_id, "n": n, "v": vid, "lim": limit + 1}), limit)

    # -- sources / artifacts ----------------------------------------------------------------------------------------------------------------------
    async def list_sources(self, project_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        ts, sid = parse_ts_keyset(after)
        return _slice(await self._all(
            "SELECT id, project_id, title, source_kind, current_version_id, created_at FROM sources.sources WHERE project_id = :p "
            "AND (CAST(:ts AS timestamptz) IS NULL OR (created_at, id) > (CAST(:ts AS timestamptz), CAST(:s AS uuid))) ORDER BY created_at, id LIMIT :lim",
            {"p": project_id, "ts": ts, "s": sid, "lim": limit + 1}), limit)

    async def list_artifacts(self, project_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        ts, aid = parse_ts_keyset(after)
        return _slice(await self._all(
            "SELECT id, project_id, title, artifact_type, current_version_id, created_at FROM artifacts.artifacts WHERE project_id = :p "
            "AND (CAST(:ts AS timestamptz) IS NULL OR (created_at, id) > (CAST(:ts AS timestamptz), CAST(:a AS uuid))) ORDER BY created_at, id LIMIT :lim",
            {"p": project_id, "ts": ts, "a": aid, "lim": limit + 1}), limit)

    async def list_artifact_versions(self, artifact_id: UUID, limit: int, after: list[Any] | None) -> Slice:
        n, vid = parse_num_keyset(after)
        return _slice(await self._all(
            "SELECT id, artifact_id, version_number, status AS lifecycle_status FROM artifacts.artifact_versions WHERE artifact_id = :a "
            "AND (CAST(:n AS integer) IS NULL OR (version_number, id) > (CAST(:n AS integer), CAST(:v AS uuid))) ORDER BY version_number, id LIMIT :lim",
            {"a": artifact_id, "n": n, "v": vid, "lim": limit + 1}), limit)

    # -- worker runs ------------------------------------------------------------------------------------------------------------------------------
    async def get_worker_run(self, run_id: UUID) -> Row | None:
        return await self._one(
            "SELECT w.id, w.project_id, w.task_id, w.status, w.context_package_version_id, w.created_at, w.operation_id, w.row_version, w.derived_from_worker_run_id, "
            "w.derivation_reason, w.attempt_number, w.latest_readiness_evaluation_id, w.started_with_readiness_evaluation_id, w.started_at, w.finished_at, "
            "w.result_ref, w.problem_ref FROM agents.worker_runs w WHERE w.id = :i", {"i": run_id})

    # -- operations ---------------------------------------------------------------------------------------------------------------------------------
    async def get_operation(self, operation_id: UUID) -> Row | None:
        """The persisted projection only (Temporal is never asked). `root_operation_id` walks the parent chain inside the caller's tenant (RLS)."""
        return await self._one(
            "WITH RECURSIVE chain AS (SELECT o.id, o.parent_operation_id, 0 AS depth FROM operations.operations o WHERE o.id = :i "
            "UNION ALL SELECT p.id, p.parent_operation_id, c.depth + 1 FROM operations.operations p JOIN chain c ON p.id = c.parent_operation_id WHERE c.depth < 16) "
            "SELECT o.id, o.organization_id, o.project_id, o.parent_operation_id, o.operation_type, o.status, o.initiator_type, o.initiator_id, o.correlation_id, "
            "o.created_at, o.started_at, o.completed_at, o.result_ref, o.problem_ref, o.row_version, o.progress_snapshot, "
            "(SELECT id FROM chain ORDER BY depth DESC LIMIT 1) AS root_operation_id FROM operations.operations o WHERE o.id = :i", {"i": operation_id})

    # -- project resolution for by-id GETs --------------------------------------------------------------------------------------------------------
    async def exists_in_project(self, table: str, object_id: UUID, project_id: UUID) -> bool:
        if table not in _PROJECT_SCOPED_TABLES:
            raise ValueError("table is not a registered project-scoped resource")  # never interpolate a caller-supplied identifier
        return await self._one(f"SELECT 1 AS x FROM {table} WHERE id = :i AND project_id = :p", {"i": object_id, "p": project_id}) is not None  # noqa: S608 - allowlisted constant


_PROJECT_SCOPED_TABLES = frozenset({"work.epics", "work.tasks", "requirements.requirements", "artifacts.artifacts", "agents.worker_runs", "operations.operations", "sources.uploads"})
