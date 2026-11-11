# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Requirement / RequirementVersion persistence (ADR-056).

A requirement is an identity with a controlled pointer to its current immutable version. Creating a version bumps `last_version_number` and moves the
pointer in ONE compare-and-swap on the requirement row; the database re-checks contiguity and pointer ownership at COMMIT. An unknown type is stored as
UNKNOWN with the declared text and is never mapped to a neighbouring type. Confirmation needs a human user; APPROVED needs an approval fact for exactly
this version (the database refuses otherwise). Display numbers come from a counter row under lock, never MAX()+1.
"""
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import bind_value
from ai_res.platform.concurrency import AggregateVersionConflict, StateConflict
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError

AUTHOR_TYPES = frozenset({"USER", "MANAGER", "WORKER_RUN", "IMPORT"})
DECISIONS = frozenset({"APPROVED", "REJECTED"})



@dataclass(frozen=True)
class NewRequirementVersion:
    statement: str
    author_type: str
    declared_type: str
    rationale: str | None = None
    priority: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    provenance_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    change_reason: str | None = None
    author_id: UUID | None = None


@dataclass(frozen=True)
class RequirementRow:
    id: UUID
    display_number: int
    current_version_id: UUID | None
    last_version_number: int
    row_version: int


class RequirementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def resolve_type(self, declared: str) -> tuple[str, str | None]:
        """(registry code, declared text kept only for UNKNOWN). Exact, case-sensitive match: 'fr' is not 'FR' and 'SAFETY' is not the nearest known type."""
        found = (await self._s.execute(text("SELECT code FROM requirements.requirement_types WHERE code = :c AND code <> 'UNKNOWN'"), {"c": declared})).first()
        return (declared, None) if found else ("UNKNOWN", declared)

    async def _next_number(self, org: UUID, prj: UUID) -> int:
        await self._s.execute(text("INSERT INTO platform.display_number_counters (organization_id, project_id, counter_kind) VALUES (:o, :p, 'REQUIREMENT') ON CONFLICT DO NOTHING"), {"o": org, "p": prj})
        row = (await self._s.execute(text("UPDATE platform.display_number_counters SET last_number = last_number + 1 WHERE organization_id = :o AND project_id = :p AND counter_kind = 'REQUIREMENT' RETURNING last_number"),
                                     {"o": org, "p": prj})).one()
        return int(row[0])

    async def _insert_version(self, org: UUID, prj: UUID, requirement_id: UUID, number: int, v: NewRequirementVersion, vid: UUID) -> UUID:
        if v.author_type not in AUTHOR_TYPES:
            raise ValueError(f"author type {v.author_type!r} is not one of {sorted(AUTHOR_TYPES)}")
        rtype, declared_text = await self.resolve_type(v.declared_type)
        await self._s.execute(text(
            "INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, declared_type_text, statement, rationale, "
            "priority, acceptance_criteria, constraints_info, provenance_refs, change_reason, author_type, author_id) VALUES (:id, :o, :p, :rid, :n, :t, :dt, :st, :ra, :pr, "
            "CAST(:ac AS jsonb), CAST(:co AS jsonb), CAST(:pv AS jsonb), :cr, :at, :aid)"),
            {"id": vid, "o": org, "p": prj, "rid": requirement_id, "n": number, "t": rtype, "dt": declared_text, "st": v.statement, "ra": v.rationale, "pr": v.priority,
             "ac": bind_value(list(v.acceptance_criteria), "jsonb"), "co": bind_value(list(v.constraints), "jsonb"), "pv": bind_value(list(v.provenance_refs), "jsonb"),
             "cr": v.change_reason, "at": v.author_type, "aid": v.author_id})
        return vid

    async def create(self, org: UUID, prj: UUID, first: NewRequirementVersion, created_by: UUID | None = None) -> RequirementRow:
        rid, number = new_id(), await self._next_number(org, prj)
        vid = new_id()
        await self._s.execute(text("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number, current_version_id, last_version_number, created_by) VALUES (:id, :o, :p, :n, :v, 1, :by)"),
                              {"id": rid, "o": org, "p": prj, "n": number, "v": vid, "by": created_by})
        await self._insert_version(org, prj, rid, 1, first, vid)
        return RequirementRow(rid, number, vid, 1, 1)

    async def add_version(self, org: UUID, prj: UUID, requirement_id: UUID, expected_version: int, v: NewRequirementVersion, updated_by: UUID | None = None) -> tuple[UUID, int]:
        """New immutable version + pointer switch under a row_version compare-and-swap (stale -> AggregateVersionConflict / 412 at the API)."""
        if not v.change_reason:
            raise ValueError("a new version needs a change reason")
        if v.author_type not in AUTHOR_TYPES:
            raise ValueError(f"author type {v.author_type!r} is not one of {sorted(AUTHOR_TYPES)}")  # before any write
        vid = new_id()  # the pointer moves in the same compare-and-swap; the FK to the version is deferred to COMMIT
        row = (await self._s.execute(text(
            "UPDATE requirements.requirements SET last_version_number = last_version_number + 1, current_version_id = :v, row_version = row_version + 1, updated_by = :by "
            "WHERE id = :id AND row_version = :expected RETURNING last_version_number"), {"id": requirement_id, "expected": expected_version, "by": updated_by, "v": vid})).first()
        if row is None:
            exists = (await self._s.execute(text("SELECT 1 FROM requirements.requirements WHERE id = :id"), {"id": requirement_id})).first()
            if exists is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
            raise AggregateVersionConflict
        number = int(row[0])
        await self._insert_version(org, prj, requirement_id, number, v, vid)
        return vid, number

    async def _transition(self, version_id: UUID, to_status: str, from_statuses: tuple[str, ...], extra: str = "", params: dict[str, Any] | None = None) -> None:
        """Never reports success for a change that did not happen: zero rows -> not found (missing/invisible) or a state conflict."""
        row = (await self._s.execute(text(
            f"UPDATE requirements.requirement_versions SET status = :to{extra} WHERE id = :id AND status = ANY(:from) RETURNING status"),  # noqa: S608 - `extra` is a frozen literal of this module
            {"id": version_id, "to": to_status, "from": list(from_statuses), **(params or {})})).first()
        if row is None:
            current = (await self._s.execute(text("SELECT status FROM requirements.requirement_versions WHERE id = :id"), {"id": version_id})).first()
            if current is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
            raise StateConflict

    async def confirm(self, version_id: UUID, confirmed_by: UUID) -> None:
        """A human analyst confirms existence; this is not a business approval."""
        await self._transition(version_id, "CONFIRMED", ("EXTRACTED", "CANDIDATE"), ", confirmed_by = :u, confirmed_at = now()", {"u": confirmed_by})

    async def record_approval(self, org: UUID, prj: UUID, version_id: UUID, approver_user_id: UUID, decision: str, rationale: str | None = None) -> UUID:
        if decision not in DECISIONS:
            raise ValueError(f"decision {decision!r} is not one of {sorted(DECISIONS)}")
        aid = new_id()
        await self._s.execute(text("INSERT INTO governance.approvals (id, organization_id, project_id, requirement_version_id, decision, approver_user_id, rationale) VALUES (:id, :o, :p, :v, :d, :u, :r)"),
                              {"id": aid, "o": org, "p": prj, "v": version_id, "d": decision, "u": approver_user_id, "r": rationale})
        return aid

    async def mark_approved(self, version_id: UUID) -> None:
        """Allowed only after an APPROVED approval of a human user for exactly this version exists (database guard)."""
        await self._transition(version_id, "APPROVED", ("CONFIRMED",))
