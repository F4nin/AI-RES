# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Dispatcher side of the Transactional Outbox (event model: at-least-once, per-aggregate order, lease without holding a DB lock across the network call).

Runs under `ai_res_outbox_dispatcher` (cross-tenant by design, ADR-034/053; delivery columns only). Claiming commits BEFORE any network I/O, so the lease
- not a row lock - protects the in-flight row; an expired lease is reclaimed. A row is claimable only when every earlier sequence of the same aggregate
and destination is PUBLISHED, so a quarantined or pending event is never overtaken (a sequence gap is never swallowed).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import affected
from ai_res.modules.events.delivery import ERROR_CODE
from ai_res.platform.clock import require_utc

_CLAIM = text("""
WITH next AS (
  SELECT o.id FROM audit.outbox_events o
   WHERE ((o.status = 'PENDING' AND o.available_at <= now()) OR (o.status = 'IN_FLIGHT' AND o.lease_until < now()))
     AND NOT EXISTS (SELECT 1 FROM audit.outbox_events p
                      WHERE p.aggregate_type = o.aggregate_type AND p.aggregate_id = o.aggregate_id AND p.destination = o.destination
                        AND p.aggregate_sequence < o.aggregate_sequence AND p.status <> 'PUBLISHED')
   ORDER BY o.created_at, o.aggregate_sequence LIMIT :limit FOR UPDATE SKIP LOCKED)
UPDATE audit.outbox_events e SET status = 'IN_FLIGHT', lease_owner = :owner, lease_until = now() + make_interval(secs => :lease), attempt_count = e.attempt_count + 1
  FROM next WHERE e.id = next.id
RETURNING e.id, e.event_id, e.destination, e.aggregate_type, e.aggregate_id, e.aggregate_sequence, e.event_type, e.schema_version, e.envelope, e.attempt_count, e.replay_count
""")


@dataclass(frozen=True)
class OutboxRow:
    id: UUID
    event_id: UUID
    destination: str
    aggregate_type: str
    aggregate_id: UUID
    aggregate_sequence: int
    event_type: str
    schema_version: int
    envelope: dict[str, Any]
    attempt_count: int
    replay_count: int = 0  # part of the fencing token: replay restarts the attempt budget, so (owner, attempt) alone could match a stale holder



@dataclass(frozen=True)
class OutboxStats:
    """Delivery backlog snapshot (no ids, no content: safe as metric values). Rows are never deleted automatically (ADR-030)."""
    pending: int
    in_flight: int
    quarantined: int
    published: int
    oldest_undelivered_age_seconds: float  # 0 when nothing waits


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self.claim_quarantined = 0  # rows the last `claim` quarantined because their lease kept expiring (the caller reports them)

    async def claim(self, owner: str, limit: int, lease_seconds: float, max_attempts: int) -> list[OutboxRow]:
        """`lease_seconds` and `max_attempts` are WORKING configuration (no approved values): the caller supplies them.
        A row whose lease expired after `max_attempts` claims (the dispatcher keeps dying on it) is quarantined, not leased again forever."""
        if limit < 1 or lease_seconds <= 0 or max_attempts < 1 or not owner:
            raise ValueError("limit, lease_seconds, max_attempts and owner must be positive/non-empty")
        r = await self._s.execute(text("UPDATE audit.outbox_events SET status = 'QUARANTINED', last_error_code = 'LEASE_EXPIRED_MAX_ATTEMPTS', lease_owner = NULL, lease_until = NULL "
                                       "WHERE status = 'IN_FLIGHT' AND lease_until < now() AND attempt_count >= :max"), {"max": max_attempts})
        self.claim_quarantined = int(affected(r))
        rows = (await self._s.execute(_CLAIM, {"limit": limit, "owner": owner, "lease": lease_seconds})).mappings().all()
        return sorted((OutboxRow(**r) for r in rows), key=lambda r: (str(r.aggregate_id), r.aggregate_sequence))

    async def mark_published(self, row_id: UUID, owner: str, attempt: int, replay_count: int = 0) -> bool:
        """The fencing token is (`owner`, `attempt`, `replay_count`): `attempt` is the `attempt_count` returned by the claim that produced this lease (`replay_count` likewise: a replay restarts the attempt budget), and the lease must still be
        valid. False when the lease was lost (expired and possibly reclaimed, even by a restarted dispatcher with the same name): the caller treats the delivery
        as possibly duplicated, never as owned, and MUST act on False (the return value is the only signal)."""
        r = await self._s.execute(text(
            "UPDATE audit.outbox_events SET status = 'PUBLISHED', published_at = now(), lease_owner = NULL, lease_until = NULL, last_error_code = NULL "
            "WHERE id = :id AND status = 'IN_FLIGHT' AND lease_owner = :owner AND attempt_count = :attempt AND replay_count = :replay AND lease_until >= now()"),
            {"id": row_id, "owner": owner, "attempt": attempt, "replay": replay_count})
        return affected(r) == 1

    async def mark_failed(self, row_id: UUID, owner: str, attempt: int, error_code: str, retry_at: datetime | None, max_attempts: int,
                          replay_count: int = 0) -> bool:
        """`retry_at=None` quarantines (permanent error). Otherwise the row returns to PENDING at `retry_at` (backoff is the caller's WORKING policy), unless the attempt
        budget `max_attempts` (WORKING, supplied by the caller) is spent: then it is quarantined, so a transient error cannot retry forever (bounded retry).
        Same fencing as `mark_published`; False = lease lost, and the caller MUST act on it."""
        if not ERROR_CODE.fullmatch(error_code):  # the code is stored and echoed in alerts: a machine code, never an exception message (server DETAIL can carry digests/envelopes)
            raise ValueError("error code must be an upper-case machine code")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        r = await self._s.execute(text(
            "UPDATE audit.outbox_events SET status = CASE WHEN CAST(:retry AS timestamptz) IS NULL OR attempt_count >= :max THEN 'QUARANTINED' ELSE 'PENDING' END, "
            "available_at = coalesce(CAST(:retry AS timestamptz), available_at), last_error_code = :err, lease_owner = NULL, lease_until = NULL "
            "WHERE id = :id AND status = 'IN_FLIGHT' AND lease_owner = :owner AND attempt_count = :attempt AND replay_count = :replay AND lease_until >= now()"),
            {"id": row_id, "owner": owner, "attempt": attempt, "replay": replay_count, "err": error_code, "max": max_attempts, "retry": None if retry_at is None else require_utc(retry_at)})
        return affected(r) == 1

    async def stats(self) -> OutboxStats:
        r = (await self._s.execute(text(
            "SELECT count(*) FILTER (WHERE status = 'PENDING'), count(*) FILTER (WHERE status = 'IN_FLIGHT'), count(*) FILTER (WHERE status = 'QUARANTINED'), "
            "count(*) FILTER (WHERE status = 'PUBLISHED'), "
            "coalesce(extract(epoch FROM now() - min(created_at) FILTER (WHERE status IN ('PENDING','IN_FLIGHT'))), 0) FROM audit.outbox_events"))).one()
        return OutboxStats(int(r[0]), int(r[1]), int(r[2]), int(r[3]), float(r[4]))

    async def replay(self, event_ids: list[UUID]) -> int:
        # NOTE: the filter is by event id, so every destination's quarantined row of that event returns to delivery (uq event_id+destination).
        """Controlled replay of QUARANTINED rows: they return to PENDING with a fresh attempt budget and `replay_count + 1` (which also changes the fencing token of any stale holder); the previous error code stays for
        diagnosis. Only quarantined rows move (a published or leased row is untouched). Authorization and the approval of a replay (WORKING, Event Model §18) are the
        caller's: this repository only performs the transition. Per-aggregate order still holds - a replayed row is claimed before its successors."""
        if not event_ids:
            raise ValueError("replay needs explicit event ids: there is no replay-all")
        r = await self._s.execute(text(
            "UPDATE audit.outbox_events SET status = 'PENDING', attempt_count = 0, available_at = now(), replay_count = replay_count + 1 "
            "WHERE status = 'QUARANTINED' AND event_id = ANY(:ids)"), {"ids": event_ids})
        return int(affected(r))
