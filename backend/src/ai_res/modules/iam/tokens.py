"""Opaque session and CSRF tokens (Auth v1.1 §6, ADR-062).

A session token is `<organization id hex>.<256-bit random>`. The organization part is only a LOOKUP HINT used to choose the tenant context under
which the session row is read (pre-auth lookup, G-48); it proves nothing. Authority comes from the random part: only its SHA-256 digest is stored,
and a forged hint can at most select an organization in which no row has that digest.

The CSRF token is derived from the session token (HMAC-SHA256, key = token), so it is stable for the life of the session and a page reload can
obtain it again from an authenticated GET, while a cross-site page can neither read the cookie (HttpOnly) nor the response (no CORS).
"""
import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from uuid import UUID

_TOKEN = re.compile(r"\A([0-9a-f]{32})\.([A-Za-z0-9_-]{43})\Z")
_CSRF_CONTEXT = b"ai-res-csrf-v1"


@dataclass(frozen=True, slots=True)
class ParsedSessionToken:
    organization_id: UUID  # lookup hint only
    raw: str


def new_session_token(organization_id: UUID) -> str:
    return f"{organization_id.hex}.{secrets.token_urlsafe(32)}"


def parse_session_token(value: str) -> ParsedSessionToken | None:
    m = _TOKEN.match(value)
    if m is None:
        return None
    try:
        return ParsedSessionToken(UUID(hex=m.group(1)), value)
    except ValueError:
        return None


def session_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def csrf_token_for(session_token: str) -> str:
    mac = hmac.new(session_token.encode("ascii"), _CSRF_CONTEXT, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def csrf_digest(csrf_token: str) -> bytes:
    return hashlib.sha256(csrf_token.encode("utf-8", "surrogatepass")).digest()
