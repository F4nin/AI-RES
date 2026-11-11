"""Short-lived, audience-scoped service credentials (Auth v1.1 §8, IAM v1.5 §3, AUTH-012).

A service token is `ar1.<payload>.<signature>`: the payload is `{iss, aud, iat, exp, jti}` (no roles, no secrets) and the signature is Ed25519 over
a domain-separated prefix + `ar1.<payload>`. Each service signs with ITS OWN private key and verifiers hold the public keys per issuer, so a Worker
cannot mint a Manager token and a verifier cannot forge one. Tokens are not browser sessions (different shape, different verifier) and never
carry user authority. A service identity proves WHICH component is calling; it is not a Worker Run grant and not a permission (Policy Engine).

Lifetime is capped (`max_ttl`, WORKING default in Settings) at issue AND at verification. Verification never raises: anything wrong is `None`.
"""
import base64
import binascii
import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ai_res.platform.clock import utc_now
from ai_res.platform.config import ConfigError, Settings, read_secret_file
from ai_res.platform.ports import ServiceIdentity, ServiceName

_PREFIX = "ar1"
_DOMAIN = b"ai-res-service-token-v1\x00"
_MAX_LEN = 1024
_CLAIMS = {"iss", "aud", "iat", "exp", "jti"}
SKEW = timedelta(seconds=30)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate claim")
        out[k] = v
    return out


class ServiceTokenIssuer:
    def __init__(self, issuer: ServiceName, private_key: Ed25519PrivateKey, *, max_ttl: timedelta, clock: Callable[[], datetime] = utc_now) -> None:
        self._iss, self._key, self._max, self._clock = issuer, private_key, max_ttl, clock

    def issue(self, audience: ServiceName, ttl: timedelta) -> str:
        if audience is self._iss:
            raise ValueError("a service does not issue tokens to itself")
        if not timedelta(0) < ttl <= self._max:
            raise ValueError("ttl must be positive and not above the configured maximum")
        now = self._clock()
        claims = {"iss": self._iss.value, "aud": audience.value, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp()),
                  "jti": secrets.token_urlsafe(12)}
        body = _b64e(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
        return f"{_PREFIX}.{body}.{_b64e(self._key.sign(_DOMAIN + f'{_PREFIX}.{body}'.encode()))}"


class ServiceTokenVerifier:
    """Implements ServiceIdentityPort. `public_keys[issuer]` lists the accepted raw 32-byte public keys (two during a rotation)."""

    def __init__(self, public_keys: Mapping[ServiceName, Sequence[bytes]], *, max_ttl: timedelta, clock: Callable[[], datetime] = utc_now) -> None:
        self._keys = {n: tuple(Ed25519PublicKey.from_public_bytes(k) for k in ks) for n, ks in public_keys.items()}
        self._max, self._clock = max_ttl, clock

    async def verify_service_token(self, token: str, audience: ServiceName) -> ServiceIdentity | None:
        try:
            return self._verify(token, audience)
        except Exception:  # noqa: BLE001 - a verifier must answer "no" to anything malformed, never raise into the request path
            return None

    def _verify(self, token: str, audience: ServiceName) -> ServiceIdentity | None:
        if not isinstance(token, str) or len(token) > _MAX_LEN:
            return None
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _PREFIX:
            return None
        claims = json.loads(_b64d(parts[1]).decode("utf-8"), object_pairs_hook=_unique)
        if not isinstance(claims, dict) or set(claims) != _CLAIMS:
            return None
        issuer, aud = ServiceName(claims["iss"]), ServiceName(claims["aud"])
        iat, exp = claims["iat"], claims["exp"]
        if aud is not audience or issuer is aud or isinstance(iat, bool) or isinstance(exp, bool) or not isinstance(iat, int) or not isinstance(exp, int):
            return None
        if not isinstance(claims["jti"], str) or not claims["jti"]:
            return None
        now = self._clock()
        if not 0 < exp - iat <= self._max.total_seconds() or now.timestamp() >= exp or iat > now.timestamp() + SKEW.total_seconds():
            return None
        signed, signature = _DOMAIN + f"{parts[0]}.{parts[1]}".encode(), _b64d(parts[2])
        for key in self._keys.get(issuer, ()):
            try:
                key.verify(signature, signed)
            except InvalidSignature:
                continue
            return ServiceIdentity(name=issuer, audience=aud, expires_at=datetime.fromtimestamp(exp, tz=now.tzinfo))
        return None


# ---------- key material from files (Compose secrets) ----------
def load_private_key(path: Any) -> Ed25519PrivateKey:
    """File content: base64 of the raw 32-byte Ed25519 seed."""
    try:
        seed = base64.b64decode(read_secret_file(path), validate=True)
        return Ed25519PrivateKey.from_private_bytes(seed)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError("service signing key must be base64 of a 32-byte Ed25519 seed") from exc


def load_public_keys(path: Any) -> dict[ServiceName, tuple[bytes, ...]]:
    """File content: one `<SERVICE_NAME> <base64 32-byte public key>` per line; repeat a service to accept several keys during rotation."""
    out: dict[ServiceName, list[bytes]] = {}
    for line in read_secret_file(path).decode("ascii", "replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        try:
            name, raw = ServiceName(parts[0]), base64.b64decode(parts[1], validate=True)
            if len(parts) != 2 or len(raw) != 32:
                raise ValueError
            Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, IndexError, binascii.Error) as exc:
            raise ConfigError("service public keys: each line must be '<SERVICE_NAME> <base64 32-byte key>'") from exc
        out.setdefault(name, []).append(raw)
    return {n: tuple(v) for n, v in out.items()}


def verifier_from_settings(settings: Settings) -> ServiceTokenVerifier:
    if settings.service_public_keys_file is None:
        raise ConfigError("service_public_keys_file is required")
    return ServiceTokenVerifier(load_public_keys(settings.service_public_keys_file), max_ttl=timedelta(seconds=settings.service_token_max_ttl_seconds))
