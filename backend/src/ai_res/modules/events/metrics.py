"""Delivery metrics (Event Model v1.4 §16): counters and backlog gauges through the OpenTelemetry metrics API.

Attributes are low-cardinality machine codes only (`reason`, `outcome`): never event, aggregate, tenant or consumer-supplied ids (security.md). Without a
configured MeterProvider the API is a no-op, so losing telemetry never stops delivery. The in-process `snapshot` mirrors the counters for tests and the
runbook's `outbox status` command.
"""
from collections import Counter
from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from ai_res.modules.events.inbox_repository import InboxStats
from ai_res.modules.events.outbox_repository import OutboxStats

_COUNTERS = {
    "published": "Outbox rows delivered", "retried": "Outbox deliveries rescheduled after a transient error", "quarantined": "Outbox rows quarantined",
    "lease_lost": "Delivery results discarded because the lease was lost", "replayed": "Quarantined rows put back by controlled replay",
    "inbox_duplicate": "Inbox duplicate deliveries (successful no-op)", 
    "start_already_finished": "Operation start redelivered for a closed workflow (G-107)", "inbox_processed": "Inbox events applied",
    "sequence_gap": "Deliveries deferred by a sequence gap",
    "unknown_major_event": "Events of an unknown type or major version (alert)", "alert": "Growth alerts raised by the periodic backlog check",
    "mark_error": "Database errors while recording a delivery result (the delivery may repeat)",
}


class EventMetrics:
    def __init__(self) -> None:
        meter = metrics.get_meter("ai_res.events")
        self._instruments = {name: meter.create_counter(f"ai_res.events.{name}", description=text) for name, text in _COUNTERS.items()}
        self._gauges: dict[str, float] = {}
        meter.create_observable_gauge("ai_res.outbox.backlog", callbacks=[self._observe_outbox], description="Outbox rows by status")
        meter.create_observable_gauge("ai_res.outbox.oldest_undelivered_age", callbacks=[self._observe_age], unit="s",
                                      description="Age of the oldest undelivered row")
        meter.create_observable_gauge("ai_res.inbox.backlog", callbacks=[self._observe_inbox], description="Inbox rows by status")
        self.snapshot: Counter[str] = Counter()

    def count(self, name: str, reason: str | None = None) -> None:
        if name not in self._instruments:
            raise ValueError(f"unknown metric {name!r}")
        self._instruments[name].add(1, {"reason": reason} if reason else {})
        self.snapshot[name if reason is None else f"{name}:{reason}"] += 1

    def record_outbox(self, stats: OutboxStats) -> None:
        self._gauges.update({"outbox.PENDING": stats.pending, "outbox.IN_FLIGHT": stats.in_flight, "outbox.QUARANTINED": stats.quarantined,
                             "outbox.PUBLISHED": stats.published, "age": stats.oldest_undelivered_age_seconds})

    def record_inbox(self, stats: InboxStats) -> None:
        self._gauges.update({"inbox.PROCESSING": stats.processing, "inbox.PROCESSED": stats.processed, "inbox.QUARANTINED": stats.quarantined})

    def _observe(self, prefix: str) -> Iterable[Observation]:
        return [Observation(v, {"status": k.split(".", 1)[1]}) for k, v in self._gauges.items() if k.startswith(prefix)]

    def _observe_outbox(self, _: CallbackOptions) -> Iterable[Observation]:
        return self._observe("outbox.")

    def _observe_inbox(self, _: CallbackOptions) -> Iterable[Observation]:
        return self._observe("inbox.")

    def _observe_age(self, _: CallbackOptions) -> Iterable[Observation]:
        return [Observation(self._gauges["age"])] if "age" in self._gauges else []



_shared: EventMetrics | None = None


def get_event_metrics() -> EventMetrics:
    """One process-wide instance: the observable gauges are registered once, not per dispatcher/consumer."""
    global _shared  # noqa: PLW0603
    if _shared is None:
        _shared = EventMetrics()
    return _shared
