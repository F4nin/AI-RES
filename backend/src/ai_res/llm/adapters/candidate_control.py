"""Private candidate control client, with no DB credentials or approval power.

Only the host supplies a service-token issuer and pinned private CA. There are no
retries, redirects or environment proxies. A lost HTTP acknowledgment never means
permission to dispatch again: the backend may already have committed its fact.
The caller must withhold successful evidence until accounting is acknowledged.
"""
import asyncio
import hashlib
import json
import math
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx

from ai_res.llm.candidate_payload import CandidateBody
from ai_res.platform.redaction import scan_secrets

CONTROL_VERSION = "flash-candidate-control/0.1"
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CLAIM_KEYS = frozenset({"version", "attemptId", "requestRef", "bodySha256", "payloadBytes", "stream", "maxOutputTokens"})
_UNKNOWN_REASONS = frozenset({"TIMEOUT", "CANCEL", "NETWORK", "PROVIDER_ERROR", "UNTRUSTED_RESPONSE"})


class CandidateControlUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Candidate control did not confirm the operation.")


def _safe_ref(value: object) -> bool:
    return isinstance(value, str) and bool(_REF.fullmatch(value)) and not scan_secrets(value).found


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateControlUnavailable()
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CandidateControlUnavailable()


@dataclass(frozen=True, slots=True, repr=False)
class CandidateClaimReceipt:
    attempt_id: UUID
    request_ref: str
    body_sha256: str
    payload_bytes: int
    stream: bool
    max_output_tokens: int

    def __post_init__(self) -> None:
        if (not isinstance(self.attempt_id, UUID) or not _safe_ref(self.request_ref)
                or not isinstance(self.body_sha256, str) or not _HASH.fullmatch(self.body_sha256)
                or type(self.payload_bytes) is not int or not 1 <= self.payload_bytes <= 4096
                or type(self.stream) is not bool or type(self.max_output_tokens) is not int or self.max_output_tokens != 256):
            raise CandidateControlUnavailable()


class CandidateControlClient:
    def __init__(self, control_url: str, *, ca_file: Path, token_supplier: Callable[[], str],
                 timeout_seconds: float = 5.0, http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        try:
            url = httpx.URL(control_url)
            if (url.scheme != "https" or url.host != "llm-poc-control" or url.userinfo or url.query or url.fragment
                    or url.path not in ("", "/") or type(timeout_seconds) not in (int, float)
                    or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30):
                raise CandidateControlUnavailable()
            context = ssl.create_default_context(cafile=ca_file)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except (ValueError, TypeError, OSError, httpx.InvalidURL):
            raise CandidateControlUnavailable() from None
        self._base = str(url).rstrip("/")
        self._token_supplier, self._timeout = token_supplier, timeout_seconds
        # Transport injection is for test composition; ordinary execution verifies
        # the private CA and hostname through this non-optional SSL context.
        self._client = httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False, transport=http_transport,
                                         timeout=httpx.Timeout(timeout_seconds),
                                         limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            try:
                token = self._token_supplier()
            except Exception:
                raise CandidateControlUnavailable() from None
            if not isinstance(token, str) or not 1 <= len(token) <= 1024 or any(not 33 <= ord(c) <= 126 for c in token):
                raise CandidateControlUnavailable()
            async with asyncio.timeout(self._timeout):
                request = self._client.build_request("POST", self._base+path, json=payload,
                                                     headers={"authorization": "Bearer "+token, "content-type": "application/json",
                                                              "accept": "application/json", "accept-encoding": "identity"})
                request.headers.pop("cookie", None)
                response = await self._client.send(request, stream=True)
                try:
                    if (response.status_code != 200 or response.headers.get("content-encoding", "identity").lower() != "identity"
                            or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"):
                        raise CandidateControlUnavailable()
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        if len(data)+len(part) > 4096:
                            raise CandidateControlUnavailable()
                        data.extend(part)
                    parsed = json.loads(bytes(data), object_pairs_hook=_unique, parse_constant=_reject_constant)
                    if not isinstance(parsed, dict):
                        raise CandidateControlUnavailable()
                    return parsed
                finally:
                    await response.aclose()
        except (TimeoutError, httpx.HTTPError, OSError, ValueError, TypeError, RecursionError):
            raise CandidateControlUnavailable() from None

    async def claim(self, body: CandidateBody) -> CandidateClaimReceipt:
        if (not isinstance(body, CandidateBody) or hashlib.sha256(body.content).hexdigest() != body.body_sha256
                or len(body.content) != body.payload_bytes):
            raise CandidateControlUnavailable()
        data = await self._post("/candidate/v1/claim", {
            "version": CONTROL_VERSION, "codecVersion": body.codec_version, "templateCase": body.case_ref,
            "bodySha256": body.body_sha256, "payloadBytes": body.payload_bytes, "stream": body.stream,
            "maxOutputTokens": body.max_output_tokens,
        })
        try:
            if set(data) != _CLAIM_KEYS or data["version"] != CONTROL_VERSION or not isinstance(data["attemptId"], str):
                raise CandidateControlUnavailable()
            receipt = CandidateClaimReceipt(UUID(data["attemptId"]), data["requestRef"], data["bodySha256"],
                                             data["payloadBytes"], data["stream"], data["maxOutputTokens"])
            if (receipt.body_sha256, receipt.payload_bytes, receipt.stream, receipt.max_output_tokens) != (
                    body.body_sha256, body.payload_bytes, body.stream, body.max_output_tokens):
                raise CandidateControlUnavailable()
            return receipt
        except (ValueError, TypeError, KeyError):
            raise CandidateControlUnavailable() from None

    async def _settle(self, receipt: CandidateClaimReceipt, facts: dict[str, Any]) -> None:
        if not isinstance(receipt, CandidateClaimReceipt):
            raise CandidateControlUnavailable()
        # Revalidate even internally supplied DTOs; never send an arbitrary object
        # or its repr to the private endpoint.
        CandidateClaimReceipt(receipt.attempt_id, receipt.request_ref, receipt.body_sha256,
                              receipt.payload_bytes, receipt.stream, receipt.max_output_tokens)
        data = await self._post("/candidate/v1/settlement", {
            "version": CONTROL_VERSION, "attemptId": str(receipt.attempt_id), "bodySha256": receipt.body_sha256, **facts,
        })
        if (set(data) != {"version", "attemptId", "outcome"} or data["version"] != CONTROL_VERSION
                or data["attemptId"] != str(receipt.attempt_id) or data["outcome"] != facts["outcome"]
                or data["outcome"] not in ("KNOWN", "UNKNOWN")):
            raise CandidateControlUnavailable()

    async def settle_known(self, receipt: CandidateClaimReceipt, *, input_tokens: object, output_tokens: object,
                           provider_request_ref: object) -> None:
        valid = (type(input_tokens) is int and type(output_tokens) is int
                 and 0 <= input_tokens <= 9_223_372_036_854_775_807 and 0 <= output_tokens <= 9_223_372_036_854_775_807
                 and _safe_ref(provider_request_ref))
        facts = ({"outcome": "KNOWN", "inputTokens": input_tokens, "outputTokens": output_tokens,
                  "providerRequestRef": provider_request_ref} if valid else {"outcome": "INVALID_USAGE"})
        await self._settle(receipt, facts)

    async def settle_unknown(self, receipt: CandidateClaimReceipt, *, reason: str) -> None:
        facts = ({"outcome": "UNKNOWN", "reason": reason} if isinstance(reason, str) and reason in _UNKNOWN_REASONS
                 else {"outcome": "INVALID_USAGE"})
        await self._settle(receipt, facts)
