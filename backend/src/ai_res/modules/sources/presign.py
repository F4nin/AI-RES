"""AWS Signature V4 query-string presigning (S3/MinIO), pure functions, stdlib only (ADR-081).

A presigned PUT carries its restrictions inside the signature: the signed headers (`content-length`, `content-type`, `x-amz-checksum-sha256`) must be sent
unchanged by the uploader or the object store rejects the request, so size, type and checksum are enforced by the store itself, not only by us later.
The payload is `UNSIGNED-PAYLOAD`. The function is verified against the published AWS example (tests/unit/test_presign.py).
"""
import base64
import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlsplit

from ai_res.platform.clock import require_utc

ALGORITHM = "AWS4-HMAC-SHA256"
MAX_EXPIRES_SECONDS = 604_800  # S3 limit for SigV4 presigned URLs


@dataclass(frozen=True, slots=True, repr=False)
class StorageCredentials:
    access_key: str
    secret_key: str

    def __repr__(self) -> str:
        return "StorageCredentials(access_key=<redacted>, secret_key=<redacted>)"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, day: str, region: str) -> bytes:
    return _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), day), region), "s3"), "aws4_request")


def _enc(value: str) -> str:
    return quote(value, safe="-_.~")


def presign_url(method: str, base_url: str, path: str, headers: Mapping[str, str], credentials: StorageCredentials, *, region: str, now: datetime,
                expires_seconds: int) -> str:
    """`base_url` is scheme://host[:port] (no path); `path` is the absolute object path (already virtual-host or path-style as the caller decided).
    `headers` are the headers the uploader must send; `host` is added from `base_url`. Header names are lower-cased, values stripped."""
    if not 1 <= expires_seconds <= MAX_EXPIRES_SECONDS:
        raise ValueError("expires_seconds out of range")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/") or parts.query or parts.username or parts.password:
        raise ValueError("base_url must be scheme://host[:port]")
    if not path.startswith("/"):
        raise ValueError("path must be absolute")
    at = require_utc(now)
    stamp, day = at.strftime("%Y%m%dT%H%M%SZ"), at.strftime("%Y%m%d")
    signed = {"host": parts.netloc, **{k.lower(): " ".join(v.split()) for k, v in headers.items()}}
    names = ";".join(sorted(signed))
    scope = f"{day}/{region}/s3/aws4_request"
    query = {"X-Amz-Algorithm": ALGORITHM, "X-Amz-Credential": f"{credentials.access_key}/{scope}", "X-Amz-Date": stamp,
             "X-Amz-Expires": str(expires_seconds), "X-Amz-SignedHeaders": names}
    canonical_query = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(query.items()))
    canonical_path = quote(path, safe="/-_.~")
    canonical = "\n".join([method.upper(), canonical_path, canonical_query, "".join(f"{k}:{signed[k]}\n" for k in sorted(signed)), names, "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join([ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signature = hmac.new(_signing_key(credentials.secret_key, day, region), to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{parts.scheme}://{parts.netloc}{canonical_path}?{canonical_query}&X-Amz-Signature={signature}"


def checksum_header(sha256_hex: str) -> str:
    """`x-amz-checksum-sha256` carries the base64 of the raw digest."""
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode()
