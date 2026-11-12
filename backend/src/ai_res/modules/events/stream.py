# ruff: noqa: E501, S608  -- SQL over a frozen allowlist of event tables
"""Project event history reader for SSE (ADR-033, ADR-092; API Contracts v1.10; Event Model v1.4 §9-12).

Reads ONLY the append-only per-aggregate event histories (never the Outbox) under the caller's tenant context (RLS), and returns an ACL-neutral PROJECTION:
identity, type, ordering and status change - never `data` (details stay behind the REST resources that have their own authorization).
Position: a map {aggregate_id: last delivered sequence} plus a watermark time. Per-aggregate order is exact (sequence); the watermark only discovers
aggregates that are new to the cursor, and events younger than the settle window are held back so a transaction that commits late is not skipped (WORKING).
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.clock import utc_now

# (aggregate_type, events table, fk column, parent table, parent project column) - a frozen allowlist, never built from input
SOURCES: tuple[tuple[str, str, str, str, str], ...] = (
    ("OPERATION", "operations.operation_events", "operation_id", "operations.operations", "project_id"),
    ("WORKER_RUN", "agents.worker_run_events", "worker_run_id", "agents.worker_runs", "project_id"),
    ("PROJECT", "project.project_events", "project_id", "project.projects", "id"),
    ("EPIC", "work.epic_events", "epic_id", "work.epics", "project_id"),
    ("REQUIREMENT", "requirements.requirement_events", "requirement_id", "requirements.requirements", "project_id"),
)
MAX_TRACKED = 24  # the signed cursor must stay under the 2048-char token limit (~68 chars per aggregate); beyond it the client resynchronises from REST (gap)
BATCH = 200


@dataclass(frozen=True)
class StreamEvent:
    event_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence: int
    event_type: str
    occurred_at: datetime
    from_status: str | None
    to_status: str | None
    reason_code: str | None


@dataclass(frozen=True)
class Position:
    watermark: datetime
    seen: dict[str, int]  # aggregate_id -> last delivered sequence

    def advanced(self, events: list[StreamEvent]) -> "Position":
        seen = dict(self.seen)
        for e in events:
            seen[str(e.aggregate_id)] = max(seen.get(str(e.aggregate_id), 0), e.sequence)
        return Position(self.watermark, seen)

    def to_keyset(self) -> list[Any]:
        return [self.watermark.isoformat(), self.seen]

    @classmethod
    def from_keyset(cls, keyset: list[Any]) -> "Position":
        """A cursor that passed the HMAC check can still be malformed (older format): refuse rather than guess."""
        if len(keyset) != 2 or not isinstance(keyset[0], str) or not isinstance(keyset[1], dict) or len(keyset[1]) > MAX_TRACKED:
            raise ValueError("unsupported stream cursor")
        seen = {str(UUID(k)): int(v) for k, v in keyset[1].items() if isinstance(v, int) and v >= 0}
        return cls(datetime.fromisoformat(keyset[0]), seen)


class ProjectEventReader:
    def __init__(self, session: AsyncSession, project_id: UUID, settle: timedelta) -> None:
        self._s, self._project, self._settle = session, project_id, settle

    async def read_new(self, position: Position) -> tuple[list[StreamEvent], Position]:
        """Events after `position` and the position after them. The caller owns the tenant context (RLS keeps other projects invisible even if a query were wrong).

        An aggregate the cursor already knows continues from its last sequence; an unknown one is picked up only by the watermark (what was written after the
        stream began), so history from before the stream is not replayed. The watermark advances to the settle horizon only when the batch was not cut."""
        horizon = utc_now() - self._settle
        seen = _json(position.seen)
        out: list[StreamEvent] = []
        full = False
        for atype, events, fk, parent, pcol in SOURCES:
            rows = (await self._s.execute(text(
                f"SELECT e.event_id, e.{fk} AS aggregate_id, e.aggregate_sequence, e.event_type, e.occurred_at, e.from_status, e.to_status, e.reason_code "
                f"FROM {events} e JOIN {parent} p ON p.id = e.{fk} WHERE p.{pcol} = :project AND e.created_at <= :horizon "
                f"AND COALESCE(e.aggregate_sequence > (CAST(:seen AS jsonb) ->> CAST(e.{fk} AS text))::bigint, e.created_at > :watermark) "
                f"ORDER BY e.created_at, e.{fk}, e.aggregate_sequence LIMIT :lim"),
                {"project": self._project, "horizon": horizon, "watermark": position.watermark, "seen": seen, "lim": BATCH})).mappings().all()
            full = full or len(rows) == BATCH
            out += [StreamEvent(r["event_id"], atype, r["aggregate_id"], int(r["aggregate_sequence"]), r["event_type"], r["occurred_at"], r["from_status"], r["to_status"],
                                r["reason_code"]) for r in rows]
        out.sort(key=lambda e: (e.occurred_at, str(e.aggregate_id), e.sequence))
        delivered = self._contiguous(out, position)[:BATCH]
        full = full or len(out) > BATCH
        moved = position.advanced(delivered)
        return delivered, Position(position.watermark if full else max(position.watermark, horizon), moved.seen)

    @staticmethod
    def _contiguous(events: list[StreamEvent], position: Position) -> list[StreamEvent]:
        """A known aggregate continues exactly at last+1: a hole is held back (re-read next poll), never skipped over (no silent sequence gap)."""
        last = dict(position.seen)
        held: set[str] = set()
        out: list[StreamEvent] = []
        for e in sorted(events, key=lambda x: (x.occurred_at, str(x.aggregate_id), x.sequence)):
            key = str(e.aggregate_id)
            if key in held or (key in last and e.sequence != last[key] + 1):
                held.add(key)
                continue
            last[key] = e.sequence
            out.append(e)
        return out

    @staticmethod
    def retention_gap(watermark: datetime, retention: timedelta) -> bool:
        """True when the cursor points before the history we still keep: the client must resynchronise from the REST snapshot (a signal, never silence)."""
        return watermark < utc_now() - retention


def _json(value: dict[str, int]) -> str:
    return json.dumps(value, separators=(",", ":"))
