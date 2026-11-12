"""Object-store port for upload verification (Source and Context Lifecycle v1.3: checksum verification before processing).

`stat` asks the store what it ACTUALLY holds for an object key: size and the SHA-256 the store computed and verified when the object was PUT
(`x-amz-checksum-sha256`, S3 checksum mode). The client's claim is never the evidence. An object without a store-verified SHA-256 cannot be verified and is
reported as such (fail closed), never accepted on declared values. The request is a presigned HEAD (60 s), so no long-lived credential is placed in a header.
"""
import base64
import binascii
from dataclasses import dataclass
from typing import Protocol

import httpx

from ai_res.modules.sources.presign import StorageCredentials, presign_url
from ai_res.platform.clock import utc_now


@dataclass(frozen=True)
class ObservedObject:
    size_bytes: int
    sha256: bytes | None  # None: the store reports no verified SHA-256 for this object


class ObjectStoreError(Exception):
    """The store could not answer (network, 5xx, malformed response): TRANSIENT for the caller, nothing is concluded about the object."""


class ObjectStore(Protocol):
    async def stat(self, object_key: str) -> ObservedObject | None:
        """None = the object does not exist (yet)."""
        ...


class S3ObjectStore:
    def __init__(self, endpoint: str, bucket: str, region: str, credentials: StorageCredentials, *, timeout_seconds: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._endpoint, self._bucket, self._region, self._credentials = endpoint, bucket, region, credentials
        self._timeout, self._transport = timeout_seconds, transport

    async def stat(self, object_key: str) -> ObservedObject | None:
        headers = {"x-amz-checksum-mode": "ENABLED"}
        url = presign_url("HEAD", self._endpoint, f"/{self._bucket}/{object_key}", headers, self._credentials, region=self._region, now=utc_now(),
                          expires_seconds=60)
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, follow_redirects=False) as client:  # closed on every path
                response = await client.head(url, headers=headers)
        except httpx.HTTPError as exc:
            raise ObjectStoreError(type(exc).__name__) from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ObjectStoreError(f"http {response.status_code}")
        try:
            size = int(response.headers["content-length"])
        except (KeyError, ValueError):
            raise ObjectStoreError("malformed response") from None
        raw = response.headers.get("x-amz-checksum-sha256")
        if raw is None:
            return ObservedObject(size, None)
        try:
            digest = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return ObservedObject(size, None)  # e.g. a composite multipart checksum ("<b64>-N"): permanently unverifiable, rejected rather than retried forever
        return ObservedObject(size, digest if len(digest) == 32 else None)
