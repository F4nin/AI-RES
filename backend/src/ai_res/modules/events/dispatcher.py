"""Outbox dispatcher (Event Model v1.4 §9.1): at-least-once delivery, lease without a DB lock across the network call, bounded retry, quarantine.

One pass (`run_once`): CLAIM in its own transaction (commit before any I/O) -> per row: validate against the contract, PUBLISH with no transaction
open, then MARK in a fresh short transaction under the fencing token (owner, attempt). The claim query releases a row only when every earlier sequence of its
aggregate and destination is PUBLISHED, so a retried, leased or quarantined event is never overtaken. Failure handling is explicit:
  * transient error  -> back to PENDING at `now + backoff(attempt)` (exponential, jittered, capped); after `max_attempts` -> quarantine, never an endless retry;
  * permanent error / contract rejection -> quarantine at once (kept for controlled replay, never dropped); an unknown type or major
    version also raises an alert metric;
  * lost lease (mark returned False) -> counted and logged: the delivery may have been duplicated, which the consumers' Inbox absorbs.
Exactly-once is NOT claimed anywhere. Lease, publish timeout, attempts, backoff and batch size are WORKING configuration (ADR-085):
defaults below are technical, not approved. batch_size * publish_timeout must fit into the lease (rows of one claim share it).
"""
import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.events import delivery
from ai_res.modules.events.alerts import GrowthThresholds, evaluate_outbox
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.metrics import EventMetrics, get_event_metrics
from ai_res.modules.events.outbox_repository import OutboxRepository, OutboxRow
from ai_res.platform.clock import utc_now

log = logging.getLogger("ai_res.events.dispatcher")


class Publisher(Protocol):
    async def publish(self, row: OutboxRow) -> None:
        """Raise TransientDeliveryError / PermanentDeliveryError; any other exception is treated as transient PUBLISH_FAILED."""
        ...


@dataclass(frozen=True)
class DispatcherConfig:
    """WORKING (no approved values, Event Model §18): technical defaults, overridable."""
    owner: str
    batch_size: int = 8
    lease_seconds: float = 60.0
    publish_timeout_seconds: float = 5.0
    max_attempts: int = 8
    backoff_base_seconds: float = 1.0
    backoff_cap_seconds: float = 60.0
    poll_interval_seconds: float = 1.0
    stats_interval_seconds: float = 30.0
    max_consecutive_errors: int = 10
    thresholds: GrowthThresholds = GrowthThresholds()
    destinations: tuple[str, ...] | None = None  # only these destinations are claimed (ADR-089); None = all

    def __post_init__(self) -> None:
        if not self.owner or self.batch_size < 1 or self.lease_seconds <= 0 or self.max_attempts < 1 or self.backoff_base_seconds <= 0:
            raise ValueError("invalid dispatcher configuration")
        if self.backoff_cap_seconds < self.backoff_base_seconds or self.poll_interval_seconds <= 0 or self.stats_interval_seconds <= 0:
            raise ValueError("invalid dispatcher configuration")
        if self.publish_timeout_seconds <= 0 or self.max_consecutive_errors < 1:
            raise ValueError("invalid dispatcher configuration")
        if self.batch_size * self.publish_timeout_seconds > self.lease_seconds * 0.8:  # rows of one claim share a lease and are delivered one after another
            raise ValueError("batch_size * publish_timeout_seconds must fit into 80% of the lease, or later rows of a batch lose their lease before delivery")


def backoff_seconds(config: DispatcherConfig, attempt: int, rng: Callable[[], float]) -> float:
    """Exponential, capped, half-jittered: between half and the full ceiling, so retries spread out but never collapse to zero."""
    ceiling = min(config.backoff_cap_seconds, config.backoff_base_seconds * float(2 ** max(attempt - 1, 0)))
    return ceiling / 2 + rng() * ceiling / 2


class InternalFanoutPublisher:
    """In-process delivery to the consumers registered per destination (no external broker in the MVP). A destination nobody listens to is a permanent
    error: dropping the event silently would lose it, so it is quarantined and alerted instead."""

    def __init__(self, routes: Mapping[str, Sequence[Callable[[OutboxRow], "asyncio.Future[None] | object"]]]) -> None:
        self._routes = {k: tuple(v) for k, v in routes.items()}

    async def publish(self, row: OutboxRow) -> None:
        consumers = self._routes.get(row.destination)
        if not consumers:
            raise delivery.PermanentDeliveryError(delivery.NO_CONSUMER)
        for consumer in consumers:  # each consumer is idempotent (Inbox): a retry after a partial fan-out re-delivers harmlessly
            await consumer(row)  # type: ignore[misc]


class Dispatcher:
    def __init__(self, factory: async_sessionmaker[AsyncSession], publisher: Publisher, contract: EventContract, config: DispatcherConfig,
                 metrics: EventMetrics | None = None, *, rng: Callable[[], float] = random.random) -> None:
        self._factory, self._publisher, self._contract, self._config = factory, publisher, contract, config
        self._metrics, self._rng = metrics or get_event_metrics(), rng

    async def run_once(self) -> int:
        """Returns the number of rows delivered in this pass."""
        c = self._config
        async with UnitOfWork(self._factory) as uow:
            repo = OutboxRepository(uow.session)
            rows = await repo.claim(c.owner, c.batch_size, c.lease_seconds, c.max_attempts, c.destinations)
            expired = repo.claim_quarantined
        for _ in range(expired):  # a row whose lease kept expiring was quarantined by the claim: that must be visible, not silent
            self._metrics.count("quarantined", "LEASE_EXPIRED_MAX_ATTEMPTS")
        if expired:
            log.error("outbox events quarantined after repeated lease expiry", extra={"count": expired})
        deadline = time.monotonic() + c.lease_seconds
        delivered = 0
        for row in rows:  # sorted by (aggregate, sequence); the claim yields at most one row per aggregate+destination
            if time.monotonic() >= deadline:  # the lease ran out before this row's turn: publishing now could not be marked; it will be reclaimed
                self._metrics.count("lease_lost", "expired_before_publish")
                continue
            delivered += await self._deliver(row)
        return delivered

    async def _deliver(self, row: OutboxRow) -> int:
        try:
            self._contract.check_row(row)
            try:
                await asyncio.wait_for(self._publisher.publish(row), timeout=self._config.publish_timeout_seconds)
            except TimeoutError:
                raise delivery.TransientDeliveryError(delivery.PUBLISH_TIMEOUT) from None
        except delivery.PermanentDeliveryError as exc:
            await self._fail(row, exc.code, permanent=True)
            return 0
        except delivery.TransientDeliveryError as exc:
            await self._fail(row, exc.code, permanent=False)
            return 0
        except Exception as exc:  # noqa: BLE001 - any publisher fault is bounded-retry material; only the class name is logged (messages may carry payload)
            log.warning("publish failed", extra={"error_class": type(exc).__name__, "attempt": row.attempt_count})
            await self._fail(row, delivery.PUBLISH_FAILED, permanent=False)
            return 0
        try:
            async with UnitOfWork(self._factory) as uow:
                ok = await OutboxRepository(uow.session).mark_published(row.id, self._config.owner, row.attempt_count, row.replay_count)
        except Exception as exc:  # noqa: BLE001 - published but not recorded: the row is redelivered after its lease expires (at-least-once); the batch carries on
            self._metrics.count("mark_error", "published")
            log.error("could not record a delivery", extra={"error_class": type(exc).__name__})
            return 0
        if not ok:
            self._metrics.count("lease_lost", "published")
            log.warning("lease lost after publish: delivery may be duplicated", extra={"attempt": row.attempt_count})
            return 0
        self._metrics.count("published")
        return 1

    async def _fail(self, row: OutboxRow, code: str, *, permanent: bool) -> None:
        c = self._config
        retry_at = None if permanent else utc_now() + timedelta(seconds=backoff_seconds(c, row.attempt_count, self._rng))
        try:
            async with UnitOfWork(self._factory) as uow:
                ok = await OutboxRepository(uow.session).mark_failed(row.id, c.owner, row.attempt_count, code, retry_at, c.max_attempts, row.replay_count)
        except Exception as exc:  # noqa: BLE001 - the row stays leased and is retried after the lease expires
            self._metrics.count("mark_error", "failed")
            log.error("could not record a delivery failure", extra={"error_class": type(exc).__name__, "reason": code})
            return
        if not ok:
            self._metrics.count("lease_lost", "failed")
            log.warning("lease lost before the failure was recorded", extra={"reason": code})
            return
        if code in (delivery.UNKNOWN_MAJOR_VERSION, delivery.UNKNOWN_EVENT_TYPE):
            self._metrics.count("unknown_major_event", code)
        if retry_at is None or row.attempt_count >= c.max_attempts:
            self._metrics.count("quarantined", code)
            log.error("outbox event quarantined", extra={"reason": code, "attempt": row.attempt_count})
        else:
            self._metrics.count("retried", code)
            log.warning("outbox delivery will be retried", extra={"reason": code, "attempt": row.attempt_count})

    async def observe(self) -> list[str]:
        """Backlog snapshot -> gauges, one `alert` count + error log per growth alert code (a quarantined event blocks its aggregate)."""
        async with UnitOfWork(self._factory) as uow:
            stats = await OutboxRepository(uow.session).stats()
        self._metrics.record_outbox(stats)
        alerts = evaluate_outbox(stats, self._config.thresholds)
        for code in alerts:
            self._metrics.count("alert", code)
            log.error("outbox growth alert", extra={"reason": code})
        return alerts

    async def run_forever(self, stop: asyncio.Event) -> None:
        """Delivers until `stop`. A database/loop error is counted and retried after the poll interval; `max_consecutive_errors` in a row end the loop
        loudly (the supervisor restarts the process) instead of spinning silently."""
        errors, last_stats = 0, float("-inf")
        while not stop.is_set():
            try:
                delivered = await self.run_once()
                if time.monotonic() - last_stats >= self._config.stats_interval_seconds:
                    last_stats = time.monotonic()
                    await self.observe()
                errors = 0
            except Exception as exc:  # noqa: BLE001 - class only: messages can carry SQL parameters
                errors += 1
                self._metrics.count("mark_error", "loop")
                log.error("dispatcher pass failed", extra={"error_class": type(exc).__name__, "consecutive": errors})
                if errors >= self._config.max_consecutive_errors:
                    raise
                delivered = 0
            if delivered == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._config.poll_interval_seconds)
