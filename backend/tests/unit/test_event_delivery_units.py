# ruff: noqa: E501
"""S10 pure logic: backoff bounds, dispatcher configuration, error codes, growth thresholds (no database)."""
import pytest

from ai_res.modules.events import delivery
from ai_res.modules.events.alerts import GrowthThresholds, evaluate_inbox, evaluate_outbox
from ai_res.modules.events.dispatcher import DispatcherConfig, backoff_seconds
from ai_res.modules.events.inbox_repository import InboxStats
from ai_res.modules.events.outbox_repository import OutboxStats

CFG = DispatcherConfig(owner="d", backoff_base_seconds=1, backoff_cap_seconds=30)


@pytest.mark.parametrize(("attempt", "ceiling"), [(1, 1), (2, 2), (3, 4), (6, 30), (50, 30)])
def test_backoff_is_exponential_capped_and_jittered_between_half_and_full(attempt, ceiling):
    assert backoff_seconds(CFG, attempt, lambda: 0.0) == ceiling / 2
    assert backoff_seconds(CFG, attempt, lambda: 1.0) == ceiling


@pytest.mark.parametrize("kw", [{"owner": ""}, {"batch_size": 0}, {"lease_seconds": 0}, {"max_attempts": 0}, {"backoff_cap_seconds": 0.5}, {"poll_interval_seconds": 0}])
def test_invalid_dispatcher_configuration_is_refused(kw):
    with pytest.raises(ValueError):
        DispatcherConfig(**{"owner": "d", **kw})


def test_error_codes_are_machine_codes_only():
    assert delivery.TransientDeliveryError(delivery.SEQUENCE_GAP).code == "SEQUENCE_GAP"
    with pytest.raises(ValueError):
        delivery.PermanentDeliveryError("connection refused for password=x")


def test_growth_alerts_fire_only_above_their_thresholds():
    t = GrowthThresholds(max_undelivered=10, max_oldest_undelivered_seconds=60, max_quarantined=0, max_outbox_rows=100)
    assert evaluate_outbox(OutboxStats(5, 5, 0, 0, 60.0), t) == []
    assert evaluate_outbox(OutboxStats(6, 5, 1, 90, 61.0), t) == ["OUTBOX_BACKLOG_HIGH", "OUTBOX_OLDEST_AGE_HIGH", "OUTBOX_QUARANTINED", "OUTBOX_ROWS_HIGH"]
    assert evaluate_inbox(InboxStats(0, 10, 0, 0.0), GrowthThresholds()) == []
    assert evaluate_inbox(InboxStats(1, 0, 2, 999.0), GrowthThresholds()) == ["INBOX_STUCK_AGE_HIGH", "INBOX_QUARANTINED"]
