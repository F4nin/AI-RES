from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from ai_res.application.proactive_messages import NotificationEvent, NotificationPlan, NotificationScope, plan_proactive_messages

SCOPE = NotificationScope(UUID(int=1), UUID(int=2), UUID(int=3))
START = datetime(2026, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(minutes=5)
FIRST = NotificationEvent(SCOPE, UUID(int=10), START, mandatory=False)
SECOND = NotificationEvent(SCOPE, UUID(int=11), START + timedelta(seconds=1), mandatory=False)
MANDATORY = NotificationEvent(SCOPE, UUID(int=12), START + timedelta(seconds=2), mandatory=True)


def test_groups_in_order_and_deduplicates_without_delaying_mandatory():
    events = [MANDATORY, SECOND, FIRST, SECOND, MANDATORY]
    pending = plan_proactive_messages(SCOPE, events, now=MANDATORY.occurred_at, digest_interval=INTERVAL, last_digest_at=None)
    assert pending == NotificationPlan((MANDATORY.event_id,), (), (FIRST.event_id, SECOND.event_id), START + INTERVAL)
    due = plan_proactive_messages(SCOPE, reversed(events), now=START + INTERVAL, digest_interval=INTERVAL, last_digest_at=None)
    assert due == NotificationPlan((MANDATORY.event_id,), (FIRST.event_id, SECOND.event_id), ())


def test_waits_full_interval_after_previous_delivery_and_preserves_unsent_events():
    previous = START + INTERVAL - timedelta(seconds=1)
    due = previous + INTERVAL
    waiting = plan_proactive_messages(SCOPE, [FIRST], now=due - timedelta(microseconds=1),
                                      digest_interval=INTERVAL, last_digest_at=previous)
    assert waiting == NotificationPlan((), (), (FIRST.event_id,), due)
    assert plan_proactive_messages(
        SCOPE, [FIRST], now=due, digest_interval=INTERVAL, last_digest_at=previous,
    ) == NotificationPlan((), (FIRST.event_id,), ())


def test_missing_digest_policy_defers_routine_and_keeps_mandatory():
    assert plan_proactive_messages(
        SCOPE, [FIRST, MANDATORY], now=START + INTERVAL, digest_interval=None, last_digest_at=None,
    ) == NotificationPlan((MANDATORY.event_id,), (), (FIRST.event_id,))


def test_daylight_saving_transition_preserves_elapsed_interval():
    local = ZoneInfo("America/New_York")
    previous = datetime(2026, 3, 8, 1, 45, tzinfo=local)
    wall_clock_boundary = datetime(2026, 3, 8, 3, 15, tzinfo=local)
    interval = timedelta(minutes=90)
    due = previous.astimezone(UTC) + interval
    assert plan_proactive_messages(
        SCOPE, [FIRST], now=wall_clock_boundary, digest_interval=interval, last_digest_at=previous,
    ) == NotificationPlan((), (), (FIRST.event_id,), due)


def test_future_routine_event_stays_pending_when_older_digest_is_due():
    now = START + INTERVAL
    future = replace(SECOND, occurred_at=now + timedelta(seconds=1))
    assert plan_proactive_messages(
        SCOPE, [FIRST, future], now=now, digest_interval=INTERVAL, last_digest_at=None,
    ) == NotificationPlan((), (FIRST.event_id,), (future.event_id,), future.occurred_at + INTERVAL)


@pytest.mark.parametrize("field", ["organization_id", "project_id", "recipient_id"])
def test_disallows_mixing_notification_scopes(field):
    event = replace(FIRST, scope=replace(SCOPE, **{field: UUID(int=99)}))
    with pytest.raises(ValueError, match="different scope"):
        plan_proactive_messages(SCOPE, [FIRST, event], now=START, digest_interval=INTERVAL, last_digest_at=None)


def test_disallows_conflicting_duplicate_event():
    with pytest.raises(ValueError, match="conflicting versions"):
        plan_proactive_messages(SCOPE, [FIRST, replace(FIRST, mandatory=True)], now=START,
                                digest_interval=INTERVAL, last_digest_at=None)
