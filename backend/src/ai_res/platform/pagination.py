"""Opaque, HMAC-signed cursors bound to subject and filter (api-and-contracts.md: cursor pagination).

Cursor wire form: base64url(json payload) + "." + base64url(hmac). Payload: v, kid, sub, flt (filter digest), k (keyset).
Keys come from a KeyRing so the signing key can rotate without invalidating cursors signed by retired-but-accepted keys.
"""
import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ai_res.platform.problems import ErrorCode, ProblemError

CURSOR_VERSION = 1
MAX_TOKEN_LEN = 2048
MAC_PREFIX = b"ai-res.cursor.v1\x00"  # domain separation: keys must not be shared with other HMAC uses
MAX_LIMIT = 200  # technical upper bound for a page size request; defaults per endpoint are set by their contracts


class InvalidCursor(ProblemError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.VALIDATION_ERROR, "Invalid cursor.", status=400, errors=[{"field": "cursor", "reason": "invalid"}])


@dataclass(frozen=True, repr=False, eq=False)
class KeyRing:
    """Signing keys by id; retired keys may stay for verification only. Secrets never appear in repr."""
    active_id: str
    keys: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if not self.keys or not self.active_id:
            raise ValueError("key ring needs a non-empty active key id and at least one key")
        if self.active_id not in self.keys:
            raise ValueError(f"active key id '{self.active_id}' is not in the key ring")
        for kid, secret in self.keys.items():
            if not kid or len(secret) < 32:
                raise ValueError(f"key '{kid}' is empty-named or shorter than 32 bytes")
        object.__setattr__(self, "keys", MappingProxyType(dict(self.keys)))

    def __repr__(self) -> str:
        return f"KeyRing(active_id={self.active_id!r}, key_ids={sorted(self.keys)})"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def filter_digest(filters: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:32]


def _mac(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, MAC_PREFIX + payload, hashlib.sha256).digest()


def encode_cursor(ring: KeyRing, *, subject: str, audience: str, filters: dict[str, Any], keyset: list[Any],
                  ttl_seconds: int, now: float | None = None) -> str:
    """audience identifies the list endpoint + sort order; callers put organization/project into `filters`.
    ttl_seconds has no default: page-token lifetime is chosen by the endpoint contract (WORKING)."""
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    issued = int(time.time() if now is None else now)
    payload = json.dumps({"v": CURSOR_VERSION, "kid": ring.active_id, "sub": subject, "aud": audience, "flt": filter_digest(filters),
                          "exp": issued + ttl_seconds, "k": keyset}, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_b64(_mac(ring.keys[ring.active_id], payload))}"


def decode_cursor(ring: KeyRing, token: str, *, subject: str, audience: str, filters: dict[str, Any],
                  now: float | None = None) -> list[Any]:
    """Return the keyset; tampering, foreign subject/endpoint, changed filter, expiry, unknown key -> InvalidCursor."""
    try:
        if len(token) > MAX_TOKEN_LEN:
            raise InvalidCursor
        body, mac = token.split(".")
        payload = _unb64(body)
        data = json.loads(payload)
        key = ring.keys.get(data["kid"])
        if key is None or data["v"] != CURSOR_VERSION:
            raise InvalidCursor
        if not hmac.compare_digest(_mac(key, payload), _unb64(mac)):
            raise InvalidCursor
        if data["sub"] != subject or data["aud"] != audience or data["flt"] != filter_digest(filters):
            raise InvalidCursor
        if data["exp"] < (time.time() if now is None else now):
            raise InvalidCursor
        keyset = data["k"]
        if not isinstance(keyset, list):
            raise InvalidCursor
        return keyset
    except InvalidCursor:
        raise
    except Exception as exc:  # malformed base64/json/structure
        raise InvalidCursor from exc


def validate_limit(limit: int | None, default: int) -> int:
    """Return the page size; out-of-range values are rejected (never silently clamped)."""
    if not 1 <= default <= MAX_LIMIT:
        raise ValueError("default page size out of range")
    if limit is None:
        return default
    if limit < 1 or limit > MAX_LIMIT:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "limit out of range.", errors=[{"field": "limit", "reason": "range"}])
    return limit
