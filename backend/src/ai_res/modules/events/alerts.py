"""Growth alerts for Outbox and Inbox (Event Model v1.4 §16; S10: "growth raises an alert, nothing is deleted automatically", ADR-030).

Thresholds are WORKING configuration (the Event Model leaves values to observability configuration "without load data"): the defaults are technical and
unapproved. Evaluation is pure: it returns machine codes; routing them to a pager is S13.
"""
from dataclasses import dataclass

from ai_res.modules.events.inbox_repository import InboxStats
from ai_res.modules.events.outbox_repository import OutboxStats

OUTBOX_BACKLOG_HIGH = "OUTBOX_BACKLOG_HIGH"
OUTBOX_OLDEST_AGE_HIGH = "OUTBOX_OLDEST_AGE_HIGH"
OUTBOX_QUARANTINED = "OUTBOX_QUARANTINED"
OUTBOX_ROWS_HIGH = "OUTBOX_ROWS_HIGH"
INBOX_STUCK_AGE_HIGH = "INBOX_STUCK_AGE_HIGH"
INBOX_QUARANTINED = "INBOX_QUARANTINED"
INBOX_ROWS_HIGH = "INBOX_ROWS_HIGH"


@dataclass(frozen=True)
class GrowthThresholds:
    """WORKING."""
    max_undelivered: int = 1000
    max_oldest_undelivered_seconds: float = 300.0
    max_quarantined: int = 0  # any quarantined event needs a human
    max_outbox_rows: int = 5_000_000  # PUBLISHED rows are kept: this is the "growth without automatic deletion" alert
    max_inbox_processing_age_seconds: float = 300.0
    max_inbox_rows: int = 5_000_000


def evaluate_outbox(stats: OutboxStats, t: GrowthThresholds) -> list[str]:
    alerts = []
    if stats.pending + stats.in_flight > t.max_undelivered:
        alerts.append(OUTBOX_BACKLOG_HIGH)
    if stats.oldest_undelivered_age_seconds > t.max_oldest_undelivered_seconds:
        alerts.append(OUTBOX_OLDEST_AGE_HIGH)
    if stats.quarantined > t.max_quarantined:
        alerts.append(OUTBOX_QUARANTINED)
    if stats.pending + stats.in_flight + stats.quarantined + stats.published > t.max_outbox_rows:
        alerts.append(OUTBOX_ROWS_HIGH)
    return alerts


def evaluate_inbox(stats: InboxStats, t: GrowthThresholds) -> list[str]:
    alerts = []
    if stats.oldest_processing_age_seconds > t.max_inbox_processing_age_seconds:
        alerts.append(INBOX_STUCK_AGE_HIGH)
    if stats.quarantined > t.max_quarantined:
        alerts.append(INBOX_QUARANTINED)
    if stats.processing + stats.processed + stats.quarantined > t.max_inbox_rows:
        alerts.append(INBOX_ROWS_HIGH)
    return alerts
