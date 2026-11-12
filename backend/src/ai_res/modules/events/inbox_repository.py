# ruff: noqa: E501
"""Consumer Inbox (event model: deduplication by (consumer_name, event_id); duplicate delivery = successful no-op).

Runs under `ai_res_event_consumer`. The Inbox row and the consumer's local effect share ONE transaction only when the effect is itself writable by that role;
S10 must decide how a domain projection is written (G-57). Ordering/gap handling (defer, never skip silently) is the consumer's responsibility in S10.
"""
import hmac
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import affected
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError


class Delivery(StrEnum):
    FIRST = "FIRST"  # process it
    DUPLICATE = "DUPLICATE"  # already received with identical content: successful no-op
    QUARANTINED = "QUARANTINED"  # a quarantined marker is not a success: the consumer must not report it as delivered
    STUCK = "STUCK"  # received earlier but still PROCESSING: the earlier attempt may have crashed after commit elsewhere; the consumer decides (S10)


class InboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def receive(self, consumer_name: str, event_id: UUID, aggregate_type: str, aggregate_id: UUID, aggregate_sequence: int, payload_hash: bytes) -> Delivery:
        """A redelivery whose content differs from the first one is an anomaly, not a duplicate: it raises instead of being dropped."""
        inserted = await self._s.execute(text(
            "INSERT INTO audit.inbox_messages (id, consumer_name, event_id, aggregate_type, aggregate_id, aggregate_sequence, status, payload_hash) "
            "VALUES (:id, :c, :e, :at, :aid, :seq, 'PROCESSING', :h) ON CONFLICT (consumer_name, event_id) DO NOTHING"),
            {"id": new_id(), "c": consumer_name, "e": event_id, "at": aggregate_type, "aid": aggregate_id, "seq": aggregate_sequence, "h": payload_hash})
        if affected(inserted) == 1:
            return Delivery.FIRST
        stored = (await self._s.execute(text("SELECT payload_hash, aggregate_sequence, status FROM audit.inbox_messages WHERE consumer_name = :c AND event_id = :e"),
                                        {"c": consumer_name, "e": event_id})).first()
        if stored is None or not hmac.compare_digest(bytes(stored[0]), payload_hash) or stored[1] != aggregate_sequence:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Redelivered event differs from the one first received.")
        return {"PROCESSING": Delivery.STUCK, "QUARANTINED": Delivery.QUARANTINED}.get(stored[2], Delivery.DUPLICATE)

    async def mark_processed(self, consumer_name: str, event_id: UUID) -> bool:
        """False = nothing was PROCESSING for this (consumer, event): the caller must treat it as a defect, never as success."""
        r = await self._s.execute(text("UPDATE audit.inbox_messages SET status = 'PROCESSED', processed_at = now(), error_code = NULL "
                                       "WHERE consumer_name = :c AND event_id = :e AND status = 'PROCESSING'"), {"c": consumer_name, "e": event_id})
        return affected(r) == 1

    async def quarantine(self, consumer_name: str, event_id: UUID, error_code: str) -> bool:
        r = await self._s.execute(text("UPDATE audit.inbox_messages SET status = 'QUARANTINED', error_code = :err WHERE consumer_name = :c AND event_id = :e "
                                       "AND status = 'PROCESSING'"), {"c": consumer_name, "e": event_id, "err": error_code})
        return affected(r) == 1

    async def lock_aggregate(self, consumer_name: str, aggregate_type: str, aggregate_id: UUID) -> None:
        """Serialises deliveries of one aggregate to one consumer for the rest of the transaction (two concurrent first deliveries would otherwise both pass the
        checkpoint read). Transaction-scoped: released by COMMIT/ROLLBACK, never leaks through the pool."""
        await self._s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"{consumer_name}|{aggregate_type}|{aggregate_id}"})

    async def checkpoint(self, consumer_name: str, aggregate_type: str, aggregate_id: UUID) -> int:
        """Last applied aggregate sequence; 0 = nothing applied yet."""
        row = (await self._s.execute(text("SELECT last_sequence FROM audit.inbox_checkpoints WHERE consumer_name = :c AND aggregate_type = :t AND aggregate_id = :a"),
                                     {"c": consumer_name, "t": aggregate_type, "a": aggregate_id})).first()
        return 0 if row is None else int(row[0])

    async def advance_checkpoint(self, consumer_name: str, aggregate_type: str, aggregate_id: UUID, sequence: int) -> None:
        """Strictly forward (a database trigger rejects a regression)."""
        await self._s.execute(text(
            "INSERT INTO audit.inbox_checkpoints (consumer_name, aggregate_type, aggregate_id, last_sequence) VALUES (:c, :t, :a, :s) "
            "ON CONFLICT (consumer_name, aggregate_type, aggregate_id) DO UPDATE SET last_sequence = EXCLUDED.last_sequence, updated_at = now()"),
            {"c": consumer_name, "t": aggregate_type, "a": aggregate_id, "s": sequence})

    async def stats(self, consumer_name: str) -> "InboxStats":
        r = (await self._s.execute(text(
            "SELECT count(*) FILTER (WHERE status = 'PROCESSING'), count(*) FILTER (WHERE status = 'PROCESSED'), count(*) FILTER (WHERE status = 'QUARANTINED'), "
            "coalesce(extract(epoch FROM now() - min(received_at) FILTER (WHERE status = 'PROCESSING')), 0) FROM audit.inbox_messages WHERE consumer_name = :c"),
            {"c": consumer_name})).one()
        return InboxStats(int(r[0]), int(r[1]), int(r[2]), float(r[3]))


@dataclass(frozen=True)
class InboxStats:
    """Inbox growth snapshot of one consumer; rows are never deleted automatically (ADR-030)."""
    processing: int
    processed: int
    quarantined: int
    oldest_processing_age_seconds: float
