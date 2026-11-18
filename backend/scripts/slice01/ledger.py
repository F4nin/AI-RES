"""Durable spending control for the standalone SLICE-01 development tool only.

This is not a product budget, domain database, grant or model approval. The
operator initializes one immutable authorization file explicitly. Runtime never
creates it. A relay must claim an armed exact request before provider I/O and
settle before publishing a result. Explicit version authorization can replace the
active request allowlist while preserving this account and all spending history.
Unknown outcomes permanently stop this file; there is no reset, refund or unblock.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_res.llm.budget import Reservation
from ai_res.llm.errors import BudgetExhausted
from ai_res.platform.clock import utc_now
from ai_res.platform.redaction import scan_secrets

VERSION = "slice01-tool-ledger/0.1"
AUTHORIZATION = "SLICE01_REQUIREMENTS_TEST_2026_11_18"
CAP = Decimal("10")
INPUT_BOUND = 2_000_000
OUTPUT_BOUND = 2048
TOKEN_BOUND = INPUT_BOUND + OUTPUT_BOUND
INPUT_RATE = Decimal("0.30")
OUTPUT_RATE = Decimal("1.20")
RESERVED_COST = (INPUT_RATE * INPUT_BOUND + OUTPUT_RATE * OUTPUT_BOUND) / Decimal(1_000_000)
MAX_BODY_BYTES = 32_768
MAX_FILE_BYTES = 1_048_576
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_MONEY = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,18})?\Z")
_ZERO = "0" * 64


class SliceLedgerError(RuntimeError):
    """Fixed machine reason only; never includes file or request contents."""

    def __init__(self, code: str = "LEDGER_UNAVAILABLE") -> None:
        self.code = code
        super().__init__("SLICE-01 tooling ledger refused: " + code)


@dataclass(frozen=True, slots=True)
class SliceBalance:
    cap: Decimal
    used_or_reserved: Decimal
    remaining: Decimal
    attempts: int
    pending: bool
    blocked: bool


@dataclass(slots=True)
class _Attempt:
    reservation: Reservation
    state: str = "RESERVED"
    armed_at: datetime | None = None
    expires_at: datetime | None = None
    outcome: str | None = None
    settled_tokens: int | None = None
    settled_cost: Decimal | None = None


@dataclass(slots=True)
class _State:
    requests: dict[str, dict[str, Any]]
    records: list[dict[str, Any]]
    attempts: dict[str, _Attempt]
    active_requests: frozenset[str]
    current_manifest: str
    manifests: set[str]
    blocked: bool = False

    def used(self) -> Decimal:
        return sum((Decimal(0) if a.state == "RELEASED" else
                    a.settled_cost if a.settled_cost is not None else a.reservation.cost
                    for a in self.attempts.values()), Decimal(0))

    def pending(self) -> bool:
        return any(a.state in {"RESERVED", "ARMED", "CLAIMED"} for a in self.attempts.values())


def _require(condition: bool, code: str = "LEDGER_CORRUPT") -> None:
    if not condition:
        raise SliceLedgerError(code)


def _ref(value: object) -> bool:
    return isinstance(value, str) and _REF.fullmatch(value) is not None and not scan_secrets(value).found


def _hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SliceLedgerError("LEDGER_CORRUPT")


def _money(value: object) -> Decimal:
    _require(isinstance(value, str) and _MONEY.fullmatch(value) is not None)
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise SliceLedgerError("LEDGER_CORRUPT") from None
    _require(result.is_finite() and result >= 0)
    return result


def _stamp(value: object) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"))
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise SliceLedgerError("LEDGER_CORRUPT") from None
    _require(result.utcoffset() == timedelta(0))
    return result


def _requests(value: object) -> dict[str, dict[str, Any]]:
    _require(isinstance(value, dict) and 1 <= len(value) <= 256, "INVALID_MANIFEST")
    result: dict[str, dict[str, Any]] = {}
    assert isinstance(value, dict)
    for ref, item in value.items():
        _require(_ref(ref) and isinstance(item, dict) and set(item) == {"bodySha256", "payloadBytes"}, "INVALID_MANIFEST")
        _require(_hash(item["bodySha256"]) and type(item["payloadBytes"]) is int
                 and 1 <= item["payloadBytes"] <= MAX_BODY_BYTES, "INVALID_MANIFEST")
        result[ref] = dict(item)
    return result


def _header(manifest: str, requests: object) -> dict[str, Any]:
    _require(_hash(manifest), "INVALID_MANIFEST")
    return {"authorization": AUTHORIZATION, "manifestSha256": manifest, "currency": "USD", "maxCost": "10",
            "inputUpperBound": INPUT_BOUND, "outputUpperBound": OUTPUT_BOUND, "inputRatePerMillion": "0.30",
            "outputRatePerMillion": "1.20", "maxBodyBytes": MAX_BODY_BYTES, "requests": _requests(requests)}


def _record(kind: str, data: dict[str, Any], sequence: int, previous: str) -> dict[str, Any]:
    value = {"version": VERSION, "sequence": sequence, "previous": previous, "kind": kind, "data": data}
    return {**value, "sha256": hashlib.sha256(VERSION.encode() + b"\0" + _encode(value)).hexdigest()}


def _apply_version(state: _State, data: dict[str, Any]) -> None:
    _require(set(data) == {"parentManifestSha256", "manifestSha256", "requests", "authorizedAt"}, "VERSION_REFUSED")
    _require(not state.blocked and not state.pending(), "VERSION_REFUSED")
    parent, manifest = data["parentManifestSha256"], data["manifestSha256"]
    _require(parent == state.current_manifest and _hash(manifest) and manifest not in state.manifests, "VERSION_REFUSED")
    _stamp(data["authorizedAt"])
    fresh = _requests(data["requests"])
    _require(not state.requests.keys() & fresh.keys(), "REQUEST_REUSED")
    hashes = {entry["bodySha256"] for entry in fresh.values()}
    old_hashes = {entry["bodySha256"] for entry in state.requests.values()}
    _require(len(hashes) == len(fresh) and not hashes & old_hashes, "BODY_REUSED")
    state.requests.update(fresh)
    state.active_requests, state.current_manifest = frozenset(fresh), manifest
    state.manifests.add(manifest)


def _replay(raw: bytes, manifest: str) -> _State:
    _require(bool(raw) and raw.endswith(b"\n") and len(raw) <= MAX_FILE_BYTES)
    records: list[dict[str, Any]] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line, object_pairs_hook=_unique, parse_constant=_reject_constant)
            _require(isinstance(value, dict) and set(value) == {"version", "sequence", "previous", "kind", "data", "sha256"})
            _require(type(value["sequence"]) is int and value["sequence"] == len(records)
                     and isinstance(value["data"], dict) and value["version"] == VERSION)
            expected = _record(value["kind"], value["data"], len(records), records[-1]["sha256"] if records else _ZERO)
            _require(value == expected)
            records.append(value)
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise SliceLedgerError("LEDGER_CORRUPT") from None
    _require(bool(records) and records[0]["kind"] == "HEADER")
    header = records[0]["data"]
    initial = header.get("manifestSha256")
    _require(header == _header(initial, header.get("requests")))
    assert isinstance(initial, str)
    requests = _requests(header["requests"])
    state = _State(requests, records, {}, frozenset(requests), initial, {initial})
    for record in records[1:]:
        kind, data = record["kind"], record["data"]
        if kind == "AUTHORIZE_VERSION":
            _apply_version(state, data)
            continue
        if kind == "BLOCK":
            _require(set(data) == {"reason"} and data["reason"] in {"SETTLEMENT_CONFLICT", "INVALID_USAGE"})
            state.blocked = True
            continue
        ref, token = data.get("requestRef"), data.get("token")
        _require(_ref(ref) and ref in state.requests and type(token) is int)
        if kind == "RESERVE":
            _require(set(data) == {"requestRef", "token", "tokens", "cost"} and not state.blocked and not state.pending()
                     and ref in state.active_requests and ref not in state.attempts and token == len(state.attempts) + 1
                     and type(data["tokens"]) is int and data["tokens"] == TOKEN_BOUND
                     and _money(data["cost"]) == RESERVED_COST and state.used() + RESERVED_COST <= CAP)
            state.attempts[ref] = _Attempt(Reservation(ref, token, TOKEN_BOUND, RESERVED_COST))
            continue
        attempt = state.attempts.get(ref)
        _require(attempt is not None and attempt.reservation.token == token)
        assert attempt is not None
        if kind == "ARM":
            _require(set(data) == {"requestRef", "token", "armedAt", "expiresAt"}
                     and not state.blocked and attempt.state == "RESERVED")
            armed, expires = _stamp(data["armedAt"]), _stamp(data["expiresAt"])
            _require(timedelta(0) < expires - armed <= timedelta(seconds=30))
            attempt.state, attempt.armed_at, attempt.expires_at = "ARMED", armed, expires
        elif kind == "CLAIM":
            _require(set(data) == {"requestRef", "token", "bodySha256", "claimedAt"}
                     and not state.blocked and attempt.state == "ARMED"
                     and data["bodySha256"] == state.requests[ref]["bodySha256"])
            at = _stamp(data["claimedAt"])
            _require(attempt.armed_at is not None and attempt.expires_at is not None
                     and attempt.armed_at <= at < attempt.expires_at)
            attempt.state = "CLAIMED"
        elif kind == "RELEASE":
            _require(set(data) == {"requestRef", "token"} and attempt.state in {"RESERVED", "ARMED"})
            attempt.state = "RELEASED"
        elif kind == "SETTLE":
            _require(set(data) == {"requestRef", "token", "outcome", "tokens", "cost", "inputTokens", "outputTokens"}
                     and attempt.state == "CLAIMED" and data["outcome"] in {"KNOWN", "UNKNOWN"}
                     and type(data["tokens"]) is int)
            cost = _money(data["cost"])
            if data["outcome"] == "UNKNOWN":
                _require(data["tokens"] == TOKEN_BOUND and cost == RESERVED_COST
                         and data["inputTokens"] is None and data["outputTokens"] is None)
                state.blocked = True
            else:
                inp, out = data["inputTokens"], data["outputTokens"]
                _require(type(inp) is int and type(out) is int and 0 <= inp <= INPUT_BOUND and 0 <= out <= OUTPUT_BOUND
                         and data["tokens"] == inp + out and cost == _cost(inp, out))
            attempt.state, attempt.outcome = "SETTLED", data["outcome"]
            attempt.settled_tokens, attempt.settled_cost = data["tokens"], cost
        else:
            raise SliceLedgerError("LEDGER_CORRUPT")
    _require(manifest == state.current_manifest, "MANIFEST_MISMATCH")
    return state


def _cost(inp: int, out: int) -> Decimal:
    return (INPUT_RATE * inp + OUTPUT_RATE * out) / Decimal(1_000_000)


def _parent(path: Path) -> int:
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise SliceLedgerError("UNSAFE_FILE")
    return fd


def _safe(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600
             and info.st_nlink == 1 and info.st_size <= MAX_FILE_BYTES, "UNSAFE_FILE")
    return info


def _write(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        count = os.write(fd, remaining)
        _require(count > 0, "LEDGER_IO")
        remaining = remaining[count:]
    os.fsync(fd)


def _head(record: dict[str, Any], size: int) -> dict[str, Any]:
    return {"version": VERSION, "sequence": record["sequence"], "sha256": record["sha256"], "bytes": size}


def _check_head(parent: int, name: str, state: _State, size: int) -> None:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        _require(_safe(fd).st_size <= 4096, "LEDGER_CORRUPT")
        raw = os.read(fd, 4097)
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
        _require(_encode(value) == _encode(_head(state.records[-1], size)), "LEDGER_HEAD_MISMATCH")
    finally:
        os.close(fd)


def _advance_head(parent: int, name: str, record: dict[str, Any], size: int) -> None:
    temporary = ".slice01-head-" + uuid4().hex
    fd = -1
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        _write(fd, _encode(_head(record, size)) + b"\n")
        os.close(fd)
        fd = -1
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


class SliceLedger:
    def __init__(self, path: Path, *, manifest_sha256: str, clock: Callable[[], datetime] = utc_now) -> None:
        _require(_hash(manifest_sha256), "INVALID_MANIFEST")
        self.path, self.manifest_sha256, self._clock = Path(path), manifest_sha256, clock
        self._head_name = self.path.name + ".head"
        with self._locked():
            pass  # Existing file validation; never implicit account creation.

    @classmethod
    def initialize(cls, path: Path, *, manifest_sha256: str,
                   requests: Mapping[str, Mapping[str, Any]]) -> SliceLedger:
        first = _record("HEADER", _header(manifest_sha256, dict(requests)), 0, _ZERO)
        data = _encode(first) + b"\n"
        path, parent, fd, head_fd = Path(path), -1, -1, -1
        try:
            parent = _parent(path)
            head_name = path.name + ".head"
            try:
                os.stat(head_name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SliceLedgerError("ALREADY_INITIALIZED")
            fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
            _safe(fd)
            _write(fd, data)
            head_fd = os.open(head_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
            _write(head_fd, _encode(_head(first, len(data))) + b"\n")
            os.fsync(parent)
        except FileExistsError:
            raise SliceLedgerError("ALREADY_INITIALIZED") from None
        except OSError:
            raise SliceLedgerError("LEDGER_IO") from None
        finally:
            if fd >= 0:
                os.close(fd)
            if head_fd >= 0:
                os.close(head_fd)
            if parent >= 0:
                os.close(parent)
        return cls(path, manifest_sha256=manifest_sha256)

    @classmethod
    async def authorize_version(cls, path: Path, *, parent_manifest_sha256: str, manifest_sha256: str,
                                requests: Mapping[str, Mapping[str, Any]]) -> SliceLedger:
        """Explicit operator transition on an existing account; never initializes.

        The caller must finish/stop previous producers and revalidate external
        admission separately. A financial settlement is not that proof. A lost
        acknowledgement is inspected under the child manifest, never reset.
        """
        ledger = cls(path, manifest_sha256=parent_manifest_sha256)
        with ledger._locked() as locked:
            data = {"parentManifestSha256": parent_manifest_sha256, "manifestSha256": manifest_sha256,
                    "requests": dict(requests), "authorizedAt": ledger._now().isoformat().replace("+00:00", "Z")}
            _apply_version(locked[2], data)
            ledger._append(locked, "AUTHORIZE_VERSION", data)
        return cls(path, manifest_sha256=manifest_sha256)

    @contextmanager
    def _locked(self) -> Iterator[tuple[int, int, _State]]:
        parent, fd = -1, -1
        try:
            parent = _parent(self.path)
            fd = os.open(self.path.name, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
            _safe(fd)
            deadline = time.monotonic() + 1.0
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SliceLedgerError("LEDGER_BUSY") from None
                    time.sleep(0.005)
            _safe(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            raw = bytearray()
            while len(raw) <= MAX_FILE_BYTES:
                part = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            state = _replay(bytes(raw), self.manifest_sha256)
            _check_head(parent, self._head_name, state, len(raw))
            yield fd, parent, state
        except FileNotFoundError:
            raise SliceLedgerError("NOT_INITIALIZED") from None
        except OSError:
            raise SliceLedgerError("LEDGER_IO") from None
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError, InvalidOperation):
            raise SliceLedgerError("LEDGER_CORRUPT") from None
        finally:
            if fd >= 0:
                os.close(fd)
            if parent >= 0:
                os.close(parent)

    def _append(self, locked: tuple[int, int, _State], kind: str, data: dict[str, Any]) -> None:
        fd, parent, state = locked
        before, named = _safe(fd), os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
        _require((before.st_dev, before.st_ino) == (named.st_dev, named.st_ino), "UNSAFE_FILE")
        record = _record(kind, data, len(state.records), state.records[-1]["sha256"])
        encoded = _encode(record) + b"\n"
        _require(before.st_size + len(encoded) <= MAX_FILE_BYTES, "LEDGER_FULL")
        try:
            _write(fd, encoded)
            _advance_head(parent, self._head_name, record, before.st_size + len(encoded))
        except OSError:
            raise SliceLedgerError("LEDGER_IO") from None
        after = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
        _require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), "UNSAFE_FILE")

    @staticmethod
    def _attempt(state: _State, reservation: Reservation) -> _Attempt:
        _require(isinstance(reservation, Reservation), "RESERVATION_MISMATCH")
        attempt = state.attempts.get(reservation.scope)
        _require(attempt is not None and attempt.reservation == reservation, "RESERVATION_MISMATCH")
        assert attempt is not None
        return attempt

    def _now(self) -> datetime:
        value = self._clock()
        _require(isinstance(value, datetime) and value.utcoffset() == timedelta(0), "CLOCK_UNAVAILABLE")
        return value.astimezone(UTC)

    async def balance(self) -> SliceBalance:
        with self._locked() as (_, _, state):
            used = state.used()
            return SliceBalance(CAP, used, CAP - used, len(state.attempts), state.pending(), state.blocked)

    async def reserve(self, scope: str, *, tokens: int, cost: Decimal | None, currency: str | None) -> Reservation:
        _require(_ref(scope) and type(tokens) is int and 0 <= tokens <= TOKEN_BOUND
                 and isinstance(cost, Decimal) and cost.is_finite() and cost >= 0 and currency == "USD", "INVALID_RESERVATION")
        with self._locked() as locked:
            state = locked[2]
            _require(not state.blocked, "ACCOUNT_BLOCKED")
            _require(scope in state.active_requests, "REQUEST_NOT_ALLOWED")
            _require(scope not in state.attempts, "REQUEST_REUSED")
            _require(not state.pending(), "UNRESOLVED_RESERVATION")
            if state.used() + RESERVED_COST > CAP:
                raise BudgetExhausted("SLICE-01 testing ceiling exhausted")
            reservation = Reservation(scope, len(state.attempts) + 1, TOKEN_BOUND, RESERVED_COST)
            self._append(locked, "RESERVE", {"requestRef": scope, "token": reservation.token,
                                           "tokens": TOKEN_BOUND, "cost": str(RESERVED_COST)})
            return reservation

    async def arm(self, request_ref: str, *, ttl_seconds: float = 30) -> None:
        _require(type(ttl_seconds) in {int, float} and math.isfinite(ttl_seconds) and 0 < ttl_seconds <= 30, "INVALID_ARM")
        with self._locked() as locked:
            state = locked[2]
            attempt = state.attempts.get(request_ref)
            _require(not state.blocked and attempt is not None and attempt.state == "RESERVED", "ARM_REFUSED")
            assert attempt is not None
            at = self._now()
            self._append(locked, "ARM", {"requestRef": request_ref, "token": attempt.reservation.token,
                         "armedAt": at.isoformat().replace("+00:00", "Z"),
                         "expiresAt": (at + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")})

    async def claim(self, request_ref: str, body_sha256: str) -> Reservation:
        with self._locked() as locked:
            state = locked[2]
            attempt = state.attempts.get(request_ref)
            _require(not state.blocked and attempt is not None and attempt.state == "ARMED", "CLAIM_REFUSED")
            assert attempt is not None
            at = self._now()
            _require(_hash(body_sha256) and state.requests[request_ref]["bodySha256"] == body_sha256
                     and attempt.armed_at is not None and attempt.expires_at is not None
                     and attempt.armed_at <= at < attempt.expires_at, "CLAIM_REFUSED")
            self._append(locked, "CLAIM", {"requestRef": request_ref, "token": attempt.reservation.token,
                         "bodySha256": body_sha256, "claimedAt": at.isoformat().replace("+00:00", "Z")})
            return attempt.reservation

    async def release(self, reservation: Reservation) -> None:
        with self._locked() as locked:
            attempt = self._attempt(locked[2], reservation)
            if attempt.state == "RELEASED":
                return
            _require(attempt.state in {"RESERVED", "ARMED"}, "RELEASE_REFUSED")
            self._append(locked, "RELEASE", {
                "requestRef": reservation.scope,
                "token": reservation.token,
            })

    async def settle_usage(self, reservation: Reservation, *, input_tokens: int, output_tokens: int) -> None:
        if not (type(input_tokens) is int and type(output_tokens) is int
                and 0 <= input_tokens <= INPUT_BOUND and 0 <= output_tokens <= OUTPUT_BOUND):
            with self._locked() as locked:
                self._attempt(locked[2], reservation)
                self._append(locked, "BLOCK", {"reason": "INVALID_USAGE"})
            raise SliceLedgerError("INVALID_USAGE")
        await self._settle(reservation, input_tokens + output_tokens, _cost(input_tokens, output_tokens), input_tokens, output_tokens)

    async def settle_unknown(self, reservation: Reservation) -> None:
        await self._settle(reservation, TOKEN_BOUND, RESERVED_COST, None, None)

    async def settle(self, reservation: Reservation, *, tokens: int, cost: Decimal | None) -> None:
        _require(type(tokens) is int and 0 <= tokens <= TOKEN_BOUND
                 and isinstance(cost, Decimal) and cost.is_finite() and cost >= 0, "INVALID_USAGE")
        assert isinstance(cost, Decimal)
        if tokens == TOKEN_BOUND and cost == RESERVED_COST:
            # Gateway error fallback uses these same conservative values. A
            # relay may already have confirmed the actual maximum usage; its
            # identical producer acknowledgement must remain idempotent.
            with self._locked() as locked:
                attempt = self._attempt(locked[2], reservation)
                if (attempt.state, attempt.outcome, attempt.settled_tokens, attempt.settled_cost) == (
                    "SETTLED", "KNOWN", tokens, cost
                ):
                    return
            await self.settle_unknown(reservation)
            return
        # BudgetLedgerPort loses the token split. Fixed rates recover its exact
        # integer pair, while ordinary relay settlement records the real pair.
        out = (cost * Decimal(1_000_000) - INPUT_RATE * tokens) / (OUTPUT_RATE - INPUT_RATE)
        _require(out == out.to_integral_value() and 0 <= out <= min(tokens, OUTPUT_BOUND), "INVALID_USAGE")
        await self.settle_usage(reservation, input_tokens=tokens - int(out), output_tokens=int(out))

    async def _settle(self, reservation: Reservation, tokens: int, cost: Decimal,
                      inp: int | None, out: int | None) -> None:
        with self._locked() as locked:
            attempt = self._attempt(locked[2], reservation)
            outcome = "UNKNOWN" if inp is None else "KNOWN"
            if attempt.state == "SETTLED":
                if (attempt.outcome, attempt.settled_tokens, attempt.settled_cost) == (outcome, tokens, cost):
                    return
                self._append(locked, "BLOCK", {"reason": "SETTLEMENT_CONFLICT"})
                raise SliceLedgerError("SETTLEMENT_CONFLICT")
            _require(attempt.state == "CLAIMED", "SETTLEMENT_REFUSED")
            self._append(locked, "SETTLE", {"requestRef": reservation.scope, "token": reservation.token,
                         "outcome": outcome, "tokens": tokens, "cost": format(cost, "f"),
                         "inputTokens": inp, "outputTokens": out})
