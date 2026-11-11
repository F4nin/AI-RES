# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""Idempotency service (ADR-024, api-and-contracts.md): scope `(organization, actor scope, command, key)`, HMAC digests with a key id, replay, 409.

* The raw `Idempotency-Key` is never stored: only HMAC-SHA256(key ring entry, org|scope|command|key) and the key id. The request fingerprint is also an HMAC
  (a plain hash of a small body can be dictionary-attacked), computed with the SAME ring entry as the record it is compared with.
* Rotation: the digest is computed under EVERY accepted key and an existing record under any of them wins, so an old key keeps deduplicating. A
  transaction-scoped advisory lock keyed by a ring-independent hash of the scope serialises requests on the rotation boundary, so two API instances with
  different rings cannot both insert. Retire a key only after the TTL of the records written with it (runbook: S37).
* Storage and the replay/409 decisions are `IdempotencyRepository` (S05); this class only derives digests and orchestrates.
"""
import base64
import binascii
import hashlib
import hmac
import re
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.idempotency.repository import IdempotencyRecord, IdempotencyRepository
from ai_res.platform.clock import utc_now
from ai_res.platform.config import ConfigError, Settings, read_secret_file
from ai_res.platform.problems import ErrorCode, ProblemError

_KEY = re.compile(r"\A[\x21-\x7e]{16,128}\Z")  # contract: 16..128 characters; printable ASCII, no whitespace/control
_KEY_ID = re.compile(r"\A[A-Za-z0-9._-]{1,32}\Z")


@dataclass(frozen=True, slots=True)
class IdempotencyKeyRing:
    active_id: str
    keys: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if self.active_id not in self.keys or any(len(k) != 32 for k in self.keys.values()) or any(not _KEY_ID.match(i) for i in self.keys):
            raise ValueError("invalid idempotency key ring")


def load_keyring(settings: Settings) -> IdempotencyKeyRing:
    if settings.idempotency_keyring_file is None:
        raise ConfigError("idempotency_keyring_file is required")
    keys: dict[str, bytes] = {}
    active: str | None = None
    for line in read_secret_file(settings.idempotency_keyring_file).decode("ascii", "replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or not _KEY_ID.match(parts[0]) or parts[0] in keys:
            raise ConfigError("idempotency key ring: each line must be '<key_id> <base64 key>' with unique ids")
        try:
            key = base64.b64decode(parts[1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigError("idempotency key ring: key is not base64") from exc
        if len(key) != 32:
            raise ConfigError("idempotency key ring: every key must decode to 32 bytes")
        keys[parts[0]] = key
        active = active or parts[0]  # the first entry is the active key
    if active is None:
        raise ConfigError("idempotency key ring is empty")
    return IdempotencyKeyRing(active, keys)


def _hmac(key: bytes, label: bytes, data: Any) -> bytes:
    return hmac.new(key, label + canonical_json(data).encode(), hashlib.sha256).digest()


class IdempotencyService:
    def __init__(self, ring: IdempotencyKeyRing, ttl: timedelta, *, clock: Callable[[], datetime] = utc_now) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._ring, self._ttl, self._clock = ring, ttl, clock

    async def begin(self, s: AsyncSession, *, organization_id: UUID, project_id: UUID | None, actor_type: str, actor_id: UUID, command: str, key: str,
                    payload: Any) -> IdempotencyRecord:
        """Call inside the Unit of Work of the command (tenant context set). NEW: execute the command; IN_PROGRESS/REPLAY: do not; mismatch -> 409."""
        if not _KEY.match(key):
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Idempotency-Key must be 16 to 128 printable characters.", errors=[{"field": "Idempotency-Key", "reason": "invalid"}])
        scope = {"org": str(organization_id), "scopeType": actor_type.upper(), "scopeId": str(actor_id), "command": command, "key": key}
        lock = struct.unpack(">q", hashlib.sha256(canonical_json(scope).encode()).digest()[:8])[0]  # ring-independent: same request => same lock on every instance
        await s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock})
        digests = {kid: _hmac(secret, b"idem-key|", scope) for kid, secret in self._ring.keys.items()}
        existing = (await s.execute(text(
            "SELECT key_digest, key_id FROM platform.idempotency_records WHERE organization_id = :o AND scope_type = :st AND scope_id = :sid AND key_digest = ANY(:d)"),
            {"o": organization_id, "st": actor_type.upper(), "sid": actor_id, "d": list(digests.values())})).mappings().first()
        kid = existing["key_id"] if existing is not None and existing["key_id"] in digests else self._ring.active_id
        fingerprint = _hmac(self._ring.keys[kid], b"idem-fp|", {"command": command, "project": None if project_id is None else str(project_id), "payload": payload})
        return await IdempotencyRepository(s).begin(organization_id, project_id, actor_type.upper(), actor_id, digests[kid], kid, fingerprint, self._clock() + self._ttl)

    async def complete(self, s: AsyncSession, record: IdempotencyRecord, *, status: str, resource_type: str | None, resource_id: UUID | None, response_status: int,
                       response_body_ref: dict[str, Any] | None) -> None:
        await IdempotencyRepository(s).complete(record.id, status, resource_type, resource_id, response_status, response_body_ref)
