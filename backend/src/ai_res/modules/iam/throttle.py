"""Login throttling with progressive delay (Auth v1.1 §4, AUTH-005).

Four counters per failed attempt: (account, ip), ip, account, global. Once a counter reaches its threshold, further attempts are refused for a delay
that doubles with every extra failure up to a cap, and the counter resets after a quiet window. There is no permanent lockout and an attacker
on another address cannot lock the victim's own (account, ip) pair out. Refused attempts are decided BEFORE any credential check, so the response
does not depend on whether the account exists.

LIMITATION (KNOWN_GAPS): state is process-local. It is exact for the MVP single-API-process topology (Compose); several API replicas would each
count separately and a restart clears it. A shared store behind the same interface is the upgrade path. All numbers are WORKING configuration.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ai_res.platform.clock import utc_now

_Key = tuple[str, ...]
_GLOBAL: _Key = ("global",)


@dataclass(frozen=True, slots=True)
class ThrottlePolicy:
    account_ip_threshold: int
    ip_threshold: int
    account_threshold: int
    global_threshold: int
    base_delay: timedelta
    max_delay: timedelta
    window: timedelta
    max_entries: int = 100_000
    enforce_ip_global: bool = False  # WORKING (ADR-071): False = ip/global counters only SIGNAL (audit/metric); account and (account, ip) deny

    def __post_init__(self) -> None:
        if min(self.account_ip_threshold, self.ip_threshold, self.account_threshold, self.global_threshold) < 1:
            raise ValueError("thresholds must be >= 1")
        if self.base_delay <= timedelta(0) or self.max_delay < self.base_delay or self.window <= timedelta(0) or self.max_entries < 10:
            raise ValueError("invalid delay/window/max_entries")
        if self.max_delay > self.window:
            raise ValueError("max_delay must not exceed the window: a block would outlive the counter that caused it")


@dataclass(frozen=True, slots=True)
class Reservation:
    """Result of `reserve`: the attempt is already counted when `delay` is None. Pass it to `release` after a SUCCESSFUL credential check."""
    delay: timedelta | None
    newly_blocked: bool
    account: str
    ip: str
    signal: str | None = None  # "ip" or "global": that counter just crossed its threshold (not enforced in signal mode)


@dataclass(slots=True)
class _Counter:
    failures: int = 0
    last_failure: datetime | None = None
    blocked_until: datetime | None = None


class LoginThrottle:
    def __init__(self, policy: ThrottlePolicy, clock: Callable[[], datetime] = utc_now) -> None:
        self._p, self._clock = policy, clock
        self._counters: dict[_Key, _Counter] = {}

    def size(self) -> int:
        return len(self._counters)

    def _keys(self, account: str, ip: str) -> list[tuple[_Key, int]]:
        p = self._p
        return [(("account_ip", account, ip), p.account_ip_threshold), (("ip", ip), p.ip_threshold),
                (("account", account), p.account_threshold), (_GLOBAL, p.global_threshold)]

    def retry_after(self, account: str, ip: str) -> timedelta | None:
        """Remaining delay if this attempt must be refused without checking credentials, else None."""
        now = self._clock()
        remaining = timedelta(0)
        for key, _ in self._keys(account, ip):
            c = self._counters.get(key)
            if not self._p.enforce_ip_global and (key[0] == "ip" or key == _GLOBAL):
                continue  # signal-only counters never refuse an attempt: behind one proxy address they would lock everybody out
            if c is not None and c.blocked_until is not None and c.blocked_until > now:
                remaining = max(remaining, c.blocked_until - now)
        return remaining if remaining > timedelta(0) else None

    def _bump(self, account: str, ip: str, now: datetime) -> str | None:
        signal: str | None = None
        for key, threshold in self._keys(account, ip):
            c = self._counters.setdefault(key, _Counter())
            if c.last_failure is not None and now - c.last_failure > self._p.window:
                c.failures, c.blocked_until = 0, None  # quiet window passed: start afresh (no permanent lockout)
            c.failures += 1
            c.last_failure = now
            if c.failures == threshold and (key[0] == "ip" or key == _GLOBAL):
                signal = key[0]
            if c.failures >= threshold:
                delay = min(self._p.base_delay * (2 ** min(c.failures - threshold, 20)), self._p.max_delay)
                c.blocked_until = now + delay
        self._bound(now)
        return signal

    def reserve(self, account: str, ip: str) -> Reservation:
        """Atomic check-and-count, to be called BEFORE the credential check (no await in between): concurrent attempts cannot all pass the gate
        before the first failure is recorded. A refused attempt is not counted. Call `release` if the credential check then succeeds."""
        now = self._clock()
        delay = self.retry_after(account, ip)
        if delay is not None:
            return Reservation(delay, False, account, ip)
        signal = self._bump(account, ip, now)
        return Reservation(None, self.retry_after(account, ip) is not None, account, ip, signal)

    def release(self, reservation: Reservation) -> None:
        """A reserved attempt turned out to be legitimate: give it back, so a stream of valid logins never accumulates towards ip/account/global blocks."""
        if reservation.delay is not None:
            return
        for key, threshold in self._keys(reservation.account, reservation.ip):
            c = self._counters.get(key)
            if c is None:
                continue
            c.failures = max(0, c.failures - 1)
            if c.failures < threshold:
                c.blocked_until = None
        self._counters.pop(("account_ip", reservation.account, reservation.ip), None)

    def record_failure(self, account: str, ip: str) -> bool:
        """Counts a failed credential check. True only when this failure moved the attempt from allowed to refused (audit AUTH_RATE_LIMITED once)."""
        was_open = self.retry_after(account, ip) is None
        self._bump(account, ip, self._clock())
        return was_open and self.retry_after(account, ip) is not None

    def record_success(self, account: str, ip: str) -> None:
        self._counters.pop(("account_ip", account, ip), None)  # only the pair: a success must not erase ip/account/global evidence

    def _bound(self, now: datetime) -> None:
        if len(self._counters) <= self._p.max_entries:
            return
        for key in [k for k, c in self._counters.items() if k != _GLOBAL and c.last_failure is not None and now - c.last_failure > self._p.window]:
            del self._counters[key]
        if len(self._counters) > self._p.max_entries:
            # Still flooded: evict down to 90% of the cap in ONE pass (amortised, not on every request). Never an active block.
            target = self._p.max_entries * 9 // 10
            evictable = [k for k, c in self._counters.items() if k != _GLOBAL and not (c.blocked_until is not None and c.blocked_until > now)]
            evictable.sort(key=lambda k: self._counters[k].last_failure or now)
            for key in evictable[: max(0, len(self._counters) - target)]:
                del self._counters[key]
