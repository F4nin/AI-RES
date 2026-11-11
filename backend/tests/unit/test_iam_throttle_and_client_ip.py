"""AUTH-005: progressive delay instead of permanent lockout; forged X-Forwarded-For must not bypass the limit."""
from datetime import UTC, datetime, timedelta

import pytest

from ai_res.api.client_ip import parse_trusted_proxies, resolve_client_ip
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def policy(**kw: object) -> ThrottlePolicy:
    base = {"account_ip_threshold": 3, "ip_threshold": 6, "account_threshold": 5, "global_threshold": 50,
            "base_delay": timedelta(seconds=2), "max_delay": timedelta(seconds=60), "window": timedelta(minutes=15), "max_entries": 1000,
            "enforce_ip_global": True}  # the legacy hard-limit mode; signal mode has its own tests below
    base.update(kw)
    return ThrottlePolicy(**base)  # type: ignore[arg-type]


def test_failures_below_threshold_do_not_delay() -> None:
    t = LoginThrottle(policy(), Clock())
    for _ in range(2):
        assert t.record_failure("acct", "1.1.1.1") is False
    assert t.retry_after("acct", "1.1.1.1") is None


def test_threshold_reached_blocks_with_progressive_delay_capped_at_max() -> None:
    clock = Clock()
    t = LoginThrottle(policy(), clock)
    delays = []
    for _ in range(9):
        t.record_failure("acct", "1.1.1.1")
        d = t.retry_after("acct", "1.1.1.1")
        delays.append(d.total_seconds() if d else 0)
        clock.now += timedelta(seconds=(d.total_seconds() if d else 0) + 0.001)  # the caller waits out the delay and tries again
    assert delays[:2] == [0, 0] and delays[2] == 2 and delays[3] == 4 and delays[4] == 8
    assert max(delays) == 60  # capped


def test_first_blocking_failure_is_reported_once_for_audit() -> None:
    t = LoginThrottle(policy(), Clock())
    flags = [t.record_failure("acct", "1.1.1.1") for _ in range(5)]
    assert flags.count(True) == 1 and flags.index(True) == 2


def test_block_is_temporary_not_a_permanent_lockout() -> None:
    clock = Clock()
    t = LoginThrottle(policy(), clock)
    for _ in range(6):
        t.record_failure("acct", "1.1.1.1")
    assert t.retry_after("acct", "1.1.1.1") is not None
    clock.now += timedelta(minutes=16)  # quiet window passes
    assert t.retry_after("acct", "1.1.1.1") is None
    assert t.record_failure("acct", "1.1.1.1") is False  # counting starts afresh


def test_attacker_on_another_ip_cannot_lock_the_victim_pair_out() -> None:
    t = LoginThrottle(policy(), Clock())
    for _ in range(3):
        t.record_failure("victim", "6.6.6.6")
    assert t.retry_after("victim", "6.6.6.6") is not None
    assert t.retry_after("victim", "9.9.9.9") is None  # the real user's (account, ip) pair is untouched


def test_distributed_guessing_against_one_account_hits_the_account_threshold() -> None:
    t = LoginThrottle(policy(), Clock())
    for i in range(5):
        t.record_failure("victim", f"10.0.0.{i}")  # each ip stays under its own thresholds
    assert t.retry_after("victim", "10.0.0.99") is not None


def test_one_ip_spraying_many_accounts_hits_the_ip_threshold() -> None:
    t = LoginThrottle(policy(), Clock())
    for i in range(6):
        t.record_failure(f"acct{i}", "7.7.7.7")
    assert t.retry_after("brand-new-account", "7.7.7.7") is not None


def test_global_threshold_slows_everyone_but_stays_bounded() -> None:
    t = LoginThrottle(policy(global_threshold=10), Clock())
    for i in range(10):
        t.record_failure(f"a{i}", f"10.1.0.{i}")
    d = t.retry_after("someone", "8.8.8.8")
    assert d is not None and d <= timedelta(seconds=60)


def test_success_clears_only_the_account_ip_pair() -> None:
    t = LoginThrottle(policy(), Clock())
    for _ in range(3):
        t.record_failure("acct", "1.1.1.1")
    t.record_success("acct", "1.1.1.1")
    assert t.retry_after("acct", "1.1.1.1") is None


def test_memory_is_bounded_under_key_flooding() -> None:
    t = LoginThrottle(policy(max_entries=100), Clock())
    for i in range(1000):
        t.record_failure(f"junk{i}", f"10.2.{i // 250}.{i % 250}")
    assert t.size() <= 100 + 4  # the cap plus the few fixed keys


def test_policy_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        policy(account_ip_threshold=0)
    with pytest.raises(ValueError):
        policy(max_delay=timedelta(seconds=1))


# ---------- client ip ----------
TRUSTED = parse_trusted_proxies(("172.18.0.0/16",))


def test_xff_is_ignored_when_peer_is_not_a_trusted_proxy() -> None:
    assert resolve_client_ip("203.0.113.9", "1.2.3.4", TRUSTED) == "203.0.113.9"


def test_xff_is_ignored_when_no_proxy_is_configured() -> None:
    assert resolve_client_ip("172.18.0.5", "1.2.3.4", ()) == "172.18.0.5"


def test_trusted_proxy_xff_takes_the_rightmost_untrusted_hop_so_client_prepending_is_useless() -> None:
    # client sent "X-Forwarded-For: 66.66.66.66"; Caddy appended the real peer
    assert resolve_client_ip("172.18.0.5", "66.66.66.66, 203.0.113.9", TRUSTED) == "203.0.113.9"
    assert resolve_client_ip("172.18.0.5", "66.66.66.66, 203.0.113.9, 172.18.0.7", TRUSTED) == "203.0.113.9"


@pytest.mark.parametrize("xff", ["", "garbage", "999.1.1.1", "1.1.1.1,, ", "unknown"])
def test_malformed_xff_falls_back_to_the_peer(xff: str) -> None:
    assert resolve_client_ip("172.18.0.5", xff, TRUSTED) == "172.18.0.5"


def test_missing_peer_is_a_single_shared_bucket_not_a_bypass() -> None:
    assert resolve_client_ip(None, "1.2.3.4", TRUSTED) == "unknown"


def test_trusted_proxy_config_rejects_bad_cidr() -> None:
    with pytest.raises(ValueError):
        parse_trusted_proxies(("not-a-cidr",))


# ---- review fixes (S07): reservation before the credential check, active blocks survive flooding ----
def test_reservation_counts_the_attempt_before_the_credential_check_so_a_burst_cannot_slip_through() -> None:
    t = LoginThrottle(policy(account_ip_threshold=3, ip_threshold=100, account_threshold=100, global_threshold=1000), Clock())
    outcomes = [t.reserve("acct", "1.1.1.1") for _ in range(8)]  # 8 "parallel" attempts, none has finished its credential check yet
    allowed = [o for o in outcomes if o.delay is None]
    assert len(allowed) == 3 and all(o.delay is not None for o in outcomes[3:])  # the pair threshold admits exactly 3 in flight


def test_release_after_success_gives_the_attempt_back_and_clears_the_pair() -> None:
    t = LoginThrottle(policy(account_ip_threshold=3, ip_threshold=3, account_threshold=3, global_threshold=3), Clock())
    for _ in range(50):  # a stream of legitimate logins must never accumulate towards ip/account/global blocks
        r = t.reserve("acct", "1.1.1.1")
        assert r.delay is None
        t.release(r)
    assert t.retry_after("acct", "1.1.1.1") is None


def test_release_does_not_undo_real_failures() -> None:
    t = LoginThrottle(policy(account_ip_threshold=100, ip_threshold=100, account_threshold=3, global_threshold=1000), Clock())
    t.reserve("acct", "9.9.9.9")
    t.reserve("acct", "9.9.9.9")  # two failed guesses stay counted
    ok = t.reserve("acct", "2.2.2.2")
    t.release(ok)
    assert t.reserve("acct", "3.3.3.3").delay is None  # third attempt on the account is the last one admitted ...
    assert t.reserve("acct", "4.4.4.4").delay is not None  # ... and the next one waits: the success did not erase the evidence


def test_flooding_with_unique_accounts_cannot_evict_an_active_block() -> None:
    clock = Clock()
    t = LoginThrottle(policy(max_entries=50, account_ip_threshold=2, global_threshold=100_000), clock)  # global must not mask the eviction question
    for _ in range(3):
        t.record_failure("victim", "5.5.5.5")
    assert t.retry_after("victim", "5.5.5.5") is not None
    for i in range(400):  # attacker floods unique accounts from unique addresses
        t.record_failure(f"junk{i}", f"10.0.{i // 250}.{i % 250}")
    assert t.retry_after("victim", "5.5.5.5") is not None


# ---- ADR-071: ip/global counters are signals by default ----
def test_by_default_ip_and_global_counters_signal_but_never_refuse() -> None:
    t = LoginThrottle(policy(enforce_ip_global=False, account_ip_threshold=100, account_threshold=100, ip_threshold=3, global_threshold=5), Clock())
    signals = []
    for i in range(10):  # one shared proxy address spraying many accounts
        r = t.reserve(f"acct{i}", "10.0.0.1")
        assert r.delay is None  # nobody is locked out because of the shared address or the global volume
        if r.signal:
            signals.append(r.signal)
    assert signals == ["ip", "global"]  # each crossing is reported once
    assert t.retry_after("someone-else", "10.0.0.1") is None


def test_in_signal_mode_the_account_still_slows_down_guessing_from_anywhere() -> None:
    t = LoginThrottle(policy(enforce_ip_global=False, account_threshold=3, account_ip_threshold=100, ip_threshold=1000, global_threshold=1000), Clock())
    for i in range(3):
        t.reserve("victim", f"198.51.100.{i}")
    assert t.retry_after("victim", "198.51.100.77") is not None
