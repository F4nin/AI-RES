"""TOTP (RFC 6238 via pyotp: SHA-1, 6 digits, 30 s — what authenticator apps support) and one-time recovery codes."""
import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime

import pyotp

STEP_SECONDS = 30
_DIGITS = re.compile(r"\A[0-9]{6}\Z")


def new_totp_secret() -> str:
    return pyotp.random_base32()  # 160 bits


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret, interval=STEP_SECONDS).provisioning_uri(name=account, issuer_name=issuer)


def is_totp_shape(code: str) -> bool:
    return _DIGITS.match(code.strip()) is not None


def match_totp_step(secret: str, code: str, now: datetime, *, window: int) -> int | None:
    """The time step the code belongs to, trying the current step first, or None. Constant-time comparison; the caller must still reject a
    step that is not newer than the last accepted one (replay)."""
    code = code.strip()
    if not _DIGITS.match(code):
        return None
    totp = pyotp.TOTP(secret, interval=STEP_SECONDS)
    current = int(now.timestamp()) // STEP_SECONDS
    candidates = [current, *[s for k in range(1, window + 1) for s in (current - k, current + k)]]
    found: int | None = None
    for step in candidates:  # no early exit: timing does not reveal which step matched
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code) and found is None:
            found = step
    return found


def generate_recovery_codes(count: int) -> list[str]:
    """120 bits each, shown to the user once as 4-character groups. Entropy this high makes a plain SHA-256 digest safe to store."""
    out: list[str] = []
    while len(out) < count:
        raw = base64.b32encode(secrets.token_bytes(15)).decode().rstrip("=")
        code = "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))
        if code not in out:
            out.append(code)
    return out


def normalise_recovery_code(code: str) -> str:
    return re.sub(r"[\s-]+", "", code).upper()


def recovery_digest(code: str) -> bytes:
    return hashlib.sha256(normalise_recovery_code(code).encode("ascii", "ignore")).digest()
