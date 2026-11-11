"""Cookie attributes, Origin/Referer validation and constant-time comparison for cookie-authenticated requests (Auth v1.1 §6, AUTH-007).

Pure functions (no DB): the middleware/dependencies call them. CORS is deny-by-default: nothing here adds CORS headers.
"""
import hmac
from typing import Any
from urllib.parse import urlsplit

from ai_res.platform.config import Settings
from ai_res.platform.problems import ErrorCode, ProblemError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
COOKIE_PATH = "/api/v1"  # limited path, no Domain attribute (host-only cookie)


def constant_time_equal(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode("utf-8", "surrogatepass"), b.encode("utf-8", "surrogatepass"))


def _origin_of(url: str) -> str | None:
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    port = f":{u.port}" if u.port else ""
    return f"{u.scheme}://{u.hostname}{port}"


def check_state_change_origin(method: str, *, origin: str | None, referer: str | None, allowed: tuple[str, ...]) -> None:
    """Unsafe methods must come from an allowlisted origin. Origin wins; Referer is used only when Origin is absent. An empty allowlist refuses
    everything (fail closed: a deployment without configured origins cannot accept cookie-authenticated writes)."""
    if method.upper() in SAFE_METHODS:
        return
    candidate = origin if origin is not None else (_origin_of(referer) if referer else None)
    if candidate is None or candidate not in allowed:
        raise ProblemError(ErrorCode.ACCESS_DENIED, "Request origin is not allowed.", errors=[{"field": "origin", "reason": "origin_not_allowed"}])


def build_session_cookie(settings: Settings, token: str) -> dict[str, Any]:
    """Keyword arguments for `Response.set_cookie`. A browser-session cookie: lifetime is enforced server-side (idle/absolute)."""
    return {"key": settings.session_cookie_name, "value": token, "httponly": True, "secure": settings.cookie_secure, "samesite": "lax",
            "path": COOKIE_PATH, "domain": None}


def clear_session_cookie_args(settings: Settings) -> dict[str, Any]:
    return {"key": settings.session_cookie_name, "path": COOKIE_PATH, "domain": None, "httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
