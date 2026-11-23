"""Plan delivery for one recipient's already authorized proactive events."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NotificationScope:
    organization_id: UUID
    project_id: UUID
    recipient_id: UUID


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    scope: NotificationScope
    event_id: UUID
    occurred_at: datetime
    mandatory: bool

    def __post_init__(self) -> None:
        if self.occurred_at.utcoffset() is None:
            raise ValueError("Notification time must include an offset")
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class NotificationPlan:
    immediate: tuple[UUID, ...]
    digest: tuple[UUID, ...]
    deferred: tuple[UUID, ...]
    next_digest_at: datetime | None = None


def plan_proactive_messages(
    scope: NotificationScope,
    pending: Iterable[NotificationEvent],
    *,
    now: datetime,
    digest_interval: timedelta | None,
    last_digest_at: datetime | None,
) -> NotificationPlan:
    """Prepare one digest at most. The caller supplies policy and delivery state."""
    if now.utcoffset() is None or (last_digest_at is not None and last_digest_at.utcoffset() is None):
        raise ValueError("Notification time must include an offset")
    if digest_interval is not None and digest_interval <= timedelta(0):
        raise ValueError("Digest interval must be positive")
    now = now.astimezone(UTC)

    by_id: dict[UUID, NotificationEvent] = {}
    for event in pending:
        if event.scope != scope:
            raise ValueError("Notification batch has a different scope")
        previous = by_id.setdefault(event.event_id, event)
        if previous != event:
            raise ValueError("Notification event has conflicting versions")

    events = sorted(by_id.values(), key=lambda event: (event.occurred_at, event.event_id))
    immediate = tuple(event.event_id for event in events if event.mandatory)
    routine = [event for event in events if not event.mandatory]
    routine_ids = tuple(event.event_id for event in routine)
    if digest_interval is None or not routine:
        return NotificationPlan(immediate, (), routine_ids)

    due = routine[0].occurred_at + digest_interval
    if last_digest_at is not None:
        due = max(due, last_digest_at.astimezone(UTC) + digest_interval)
    if now < due:
        return NotificationPlan(immediate, (), routine_ids, next_digest_at=due)
    ready = tuple(event.event_id for event in routine if event.occurred_at <= now)
    future = [event for event in routine if event.occurred_at > now]
    next_due = future[0].occurred_at + digest_interval if future else None
    return NotificationPlan(immediate, ready, tuple(event.event_id for event in future), next_due)
