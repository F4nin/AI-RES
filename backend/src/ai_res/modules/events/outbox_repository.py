# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Dispatcher side of the Transactional Outbox (event model: at-least-once, per-aggregate order, lease without holding a DB lock across the network call).

Runs under `ai_res_outbox_dispatcher` (cross-tenant by design, ADR-034/053; delivery columns only). Claiming commits BEFORE any network I/O, so the lease
- not a row lock - protects the in-flight row; an expired lease is reclaimed. A row is claimable only when every earlier sequence of the same aggregate
and destination is PUBLISHED, so a quarantined or pending event is never overtaken (a sequence gap is never swallowed).
"""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import affected
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
RETURNING e.id, e.event_id, e.destination, e.aggregate_type, e.aggregate_id, e.aggregate_sequence, e.event_type, e.schema_version, e.envelope, e.attempt_count
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


ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def claim(self, owner: str, limit: int, lease_seconds: float, max_attempts: int) -> list[OutboxRow]:
        """`lease_seconds` and `max_attempts` are WORKING configuration (no approved values): the caller supplies them.
        A row whose lease expired after `max_attempts` claims (the dispatcher keeps dying on it) is quarantined, not leased again forever."""
        if limit < 1 or lease_seconds <= 0 or max_attempts < 1 or not owner:
            raise ValueError("limit, lease_seconds, max_attempts and owner must be positive/non-empty")
        await self._s.execute(text("UPDATE audit.outbox_events SET status = 'QUARANTINED', last_error_code = 'LEASE_EXPIRED_MAX_ATTEMPTS', lease_owner = NULL, lease_until = NULL "
                                   "WHERE status = 'IN_FLIGHT' AND lease_until < now() AND attempt_count >= :max"), {"max": max_attempts})
        rows = (await self._s.execute(_CLAIM, {"limit": limit, "owner": owner, "lease": lease_seconds})).mappings().all()
        return sorted((OutboxRow(**r) for r in rows), key=lambda r: (str(r.aggregate_id), r.aggregate_sequence))

    async def mark_published(self, row_id: UUID, owner: str, attempt: int) -> bool:
        """The fencing token is (`owner`, `attempt`): `attempt` is the `attempt_count` returned by the claim that produced this lease, and the lease must still be
        valid. False when the lease was lost (expired and possibly reclaimed, even by a restarted dispatcher with the same name): the caller treats the delivery
        as possibly duplicated, never as owned, and MUST act on False (the return value is the only signal)."""
        r = await self._s.execute(text(
            "UPDATE audit.outbox_events SET status = 'PUBLISHED', published_at = now(), lease_owner = NULL, lease_until = NULL, last_error_code = NULL "
            "WHERE id = :id AND status = 'IN_FLIGHT' AND lease_owner = :owner AND attempt_count = :attempt AND lease_until >= now()"),
            {"id": row_id, "owner": owner, "attempt": attempt})
        return affected(r) == 1

    async def mark_failed(self, row_id: UUID, owner: str, attempt: int, error_code: str, retry_at: datetime | None, max_attempts: int) -> bool:
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
            "WHERE id = :id AND status = 'IN_FLIGHT' AND lease_owner = :owner AND attempt_count = :attempt AND lease_until >= now()"),
            {"id": row_id, "owner": owner, "attempt": attempt, "err": error_code, "max": max_attempts, "retry": None if retry_at is None else require_utc(retry_at)})
        return affected(r) == 1
