"""Durable consumer library (Event Model v1.4 §9.2): Inbox marker + sequence checkpoint + local effect in ONE transaction.

Algorithm per delivery (all inside one UoW under `ai_res_event_consumer`):
  1. serialise on (consumer, aggregate) with a transaction-scoped advisory lock;
  2. Inbox marker: duplicate event id -> successful no-op; a redelivery whose content differs raises (anomaly, not duplicate);
  3. sequence vs checkpoint: CONTIGUOUS consumers (apply every event of the aggregate) need exactly checkpoint+1 - a gap is DEFERRED (transient error,
     the event is retried later, never applied out of order, never skipped); a sequence <= checkpoint with a new event id is a regression (permanent);
     MONOTONIC consumers (see a filtered stream, so gaps are legitimate) only require a sequence above the checkpoint;
  4. the idempotent handler runs with the same session; the marker becomes PROCESSED and the checkpoint advances; COMMIT.
A crash anywhere before COMMIT leaves no marker, no checkpoint and no effect, so the next delivery starts clean. Handlers must not perform external side
effects directly (they go through their own outbox, §9.2 step 5).
"""
import hashlib
from collections.abc import Awaitable, Callable
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.modules.events import delivery
from ai_res.modules.events.alerts import GrowthThresholds, evaluate_inbox
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.inbox_repository import Delivery, InboxRepository
from ai_res.modules.events.metrics import EventMetrics, get_event_metrics
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.platform.problems import ProblemError

Handler = Callable[[AsyncSession, OutboxRow], Awaitable[None]]


class Ordering(StrEnum):
    CONTIGUOUS = "CONTIGUOUS"
    MONOTONIC = "MONOTONIC"


class InboxConsumer:
    def __init__(self, name: str, factory: async_sessionmaker[AsyncSession], contract: EventContract, handler: Handler,
                 ordering: Ordering = Ordering.CONTIGUOUS, metrics: EventMetrics | None = None) -> None:
        if not name:
            raise ValueError("a durable consumer needs a name (its Inbox namespace)")
        self.name, self._factory, self._contract, self._handler = name, factory, contract, handler
        self._ordering, self._metrics = ordering, metrics or get_event_metrics()

    async def __call__(self, row: OutboxRow) -> None:
        await self.deliver(row)

    async def deliver(self, row: OutboxRow) -> Delivery:
        self._contract.check_row(row)  # a consumer never trusts the dispatcher's validation
        digest = hashlib.sha256(canonical_json(row.envelope).encode()).digest()
        async with UnitOfWork(self._factory) as uow:
            inbox = InboxRepository(uow.session)
            await inbox.lock_aggregate(self.name, row.aggregate_type, row.aggregate_id)
            try:
                received = await inbox.receive(self.name, row.event_id, row.aggregate_type, row.aggregate_id, row.aggregate_sequence, digest)
            except ProblemError:
                raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH) from None
            if received is Delivery.DUPLICATE:
                self._metrics.count("inbox_duplicate")
                return received
            if received is Delivery.QUARANTINED:
                raise delivery.PermanentDeliveryError(delivery.INBOX_QUARANTINED)
            if received is Delivery.STUCK:
                raise delivery.TransientDeliveryError(delivery.INBOX_STUCK)
            last = await inbox.checkpoint(self.name, row.aggregate_type, row.aggregate_id)
            if row.aggregate_sequence <= last:
                raise delivery.PermanentDeliveryError(delivery.SEQUENCE_REGRESSION)
            if self._ordering is Ordering.CONTIGUOUS and row.aggregate_sequence != last + 1:
                self._metrics.count("sequence_gap")
                raise delivery.TransientDeliveryError(delivery.SEQUENCE_GAP)
            await self._handler(uow.session, row)
            if not await inbox.mark_processed(self.name, row.event_id):
                raise RuntimeError("inbox marker vanished inside its own transaction")
            await inbox.advance_checkpoint(self.name, row.aggregate_type, row.aggregate_id, row.aggregate_sequence)
        self._metrics.count("inbox_processed")
        return received

    async def observe(self, thresholds: GrowthThresholds | None = None) -> list[str]:
        """Inbox growth check of this consumer: records the gauges, raises one `alert` count per code, returns the codes."""
        async with UnitOfWork(self._factory) as uow:
            stats = await InboxRepository(uow.session).stats(self.name)
        self._metrics.record_inbox(stats)
        alerts = evaluate_inbox(stats, thresholds or GrowthThresholds())
        for code in alerts:
            self._metrics.count("alert", code)
        return alerts
