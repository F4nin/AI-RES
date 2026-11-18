"""Isolated native-Bifrost development probes; never a product transport/factory.

Pinned wire source: maximhq/bifrost 7cb75fb2f8276ca48d0792c857fecb67b8879e2f,
core/schemas/chatcompletions.go and bifrost.go (RoutingInfo). Native request
conversion into final provider bytes still requires the actual pinned-Bifrost
proof. Only the relay's canonical body + durable claim can authorize egress.
There is no provider key, retry, fallback, tool execution or approval here.
"""
import asyncio
import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, NoReturn, Self

import httpx

from ai_res.llm.candidate_payload import CandidateBody
from ai_res.llm.candidate_probe import (
    CandidateProbeError,
    CandidateProbeEvidence,
    CandidateProbeUsage,
    ProbeErrorCode,
    ProbeOutcome,
    safe_probe_ref,
)
from ai_res.llm.observed_identity import (
    FingerprintPresence,
    InvalidIdentityEvidence,
    ObservedFingerprint,
    ObservedProviderIdentity,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FlashCandidateSettings:
    """WORKING safety bounds for synthetic probes; not product SLOs."""
    inference_url: str = "http://bifrost-poc:8080/v1/chat/completions"
    max_response_bytes: int = 65_536
    max_event_bytes: int = 16_384
    max_stream_bytes: int = 131_072

    def __post_init__(self) -> None:
        try:
            url = httpx.URL(self.inference_url)
            valid = (url.scheme in {"http", "https"} and url.host == "bifrost-poc" and url.port in {None, 8080}
                     and url.path == "/v1/chat/completions" and not url.userinfo and not url.query and not url.fragment)
        except (ValueError, TypeError, httpx.InvalidURL):
            valid = False
        if (not valid or any(type(value) is not int or not 1 <= value <= 131_072
                             for value in (self.max_response_bytes, self.max_event_bytes, self.max_stream_bytes))):
            raise ValueError("Invalid candidate inference endpoint or limits.")


def _require(condition: bool, code: ProbeErrorCode = ProbeErrorCode.INVALID_RESPONSE) -> None:
    if not condition:
        raise CandidateProbeError(code)


def _object(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict))
    return dict(value)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _nonfinite(_: str) -> NoReturn:
    raise CandidateProbeError()


def _json(raw: bytes | str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return _object(value)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise CandidateProbeError() from None


def _identity(data: dict[str, Any], credential: str) -> tuple[ObservedProviderIdentity, str]:
    _require(data.get("error") is None and data.get("is_bifrost_error", False) is False)
    route = _object(_object(data.get("extra_fields")).get("routing_info"))
    # These are the pinned source's actual/requested routing fields. Never use
    # the request as a fallback for missing observed routing or response facts.
    _require(route.get("provider") == "deepseek" and route.get("model") == "deepseek-flash"
             and route.get("requested_model") == "deepseek-flash"
             and route.get("requested_provider") == "deepseek"
             and ("is_fallback" not in route or route["is_fallback"] is False)
             and route.get("resolved_key_alias") is None and route.get("server_side_fallback_model") is None)
    ref, model = data.get("id"), data.get("model")
    _require(safe_probe_ref(ref) and safe_probe_ref(model))
    # Heuristic secret scanners cannot recognize every virtual-key shape. Check
    # the actual injected credential before retaining any partial/terminal fact.
    _require(all(not isinstance(value, str) or credential not in value
                 for value in (ref, model, data.get("system_fingerprint"), route.get("provider"),
                               route.get("requested_model"), route.get("model"))))
    presence = (FingerprintPresence.ABSENT if "system_fingerprint" not in data else
                FingerprintPresence.NULL if data["system_fingerprint"] is None else FingerprintPresence.VALUE)
    try:
        identity = ObservedProviderIdentity(route["provider"], route["requested_model"], route["model"], str(model),
                                            ObservedFingerprint(presence, data.get("system_fingerprint")))
    except InvalidIdentityEvidence:
        raise CandidateProbeError() from None
    return identity, str(ref)


def _usage(value: Any) -> CandidateProbeUsage:
    data = _object(value)
    inp, out = data.get("prompt_tokens"), data.get("completion_tokens")
    if type(inp) is not int or type(out) is not int:
        raise CandidateProbeError(ProbeErrorCode.INVALID_USAGE)
    usage = CandidateProbeUsage(inp, out)
    if "total_tokens" in data:
        _require(type(data["total_tokens"]) is int and data["total_tokens"] == usage.input_tokens + usage.output_tokens,
                 ProbeErrorCode.INVALID_USAGE)
    return usage


def _choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise CandidateProbeError()
    choice = _object(choices[0])
    _require(type(choice.get("index")) is int and choice["index"] == 0)
    return choice


def _text(message: dict[str, Any]) -> str:
    text = message.get("content")
    _require(text is None or isinstance(text, str))
    _require(all(message.get(field) is None or message[field] == "" for field in ("reasoning_content", "refusal")))
    return text or ""


def _ok_object(raw: str) -> bool:
    try:
        value = _json(raw)
        return value.keys() == {"ok"} and value["ok"] is True
    except CandidateProbeError:
        return False  # A capability mismatch is reported, never silently accepted.


def _capability(case: str, message: dict[str, Any], finish: Any) -> bool:
    text = _text(message)
    _require(isinstance(finish, str) and finish in {"stop", "length", "content_filter", "tool_calls"})
    tools = message.get("tool_calls")
    if case == "TOOL":
        if finish != "tool_calls" or not isinstance(tools, list) or len(tools) != 1:
            return False
        call = _object(tools[0])
        function = _object(call.get("function"))
        return (not text and call.get("type") == "function" and safe_probe_ref(call.get("id"))
                and function.get("name") == "probe_check" and isinstance(function.get("arguments"), str)
                and _ok_object(function["arguments"]))
    _require(tools is None or tools == [])
    return finish == "stop" and (_ok_object(text) if case == "JSON" else text.strip() == "OK")


@dataclass(slots=True, repr=False)
class _StreamFacts:
    identity: ObservedProviderIdentity | None = None
    ref: str | None = None
    usage: CandidateProbeUsage | None = None
    text: str = ""
    finish: str | None = None
    count: int = 0
    done: bool = False

    def add(self, data: dict[str, Any], credential: str) -> None:
        _require(not self.done)
        identity, ref = _identity(data, credential)
        _require(data.get("object") == "chat.completion.chunk")
        if self.identity is not None:
            _require(identity == self.identity and ref == self.ref)
        self.identity, self.ref = identity, ref
        self.count += 1
        _require(self.count <= 2048)
        incoming = data.get("usage")
        if incoming is not None:
            _require(self.usage is None)
            self.usage = _usage(incoming)
        if data.get("choices") == []:
            _require(self.finish is not None and incoming is not None)
            return
        _require(self.finish is None)
        choice = _choice(data)
        delta = _object(choice.get("delta"))
        _require("role" not in delta or delta["role"] == "assistant")
        _require(delta.get("tool_calls") is None or delta["tool_calls"] == [])
        self.text += _text(delta)
        _require(len(self.text.encode("utf-8")) <= 65_536)
        finish = choice.get("finish_reason")
        _require(finish is None or (isinstance(finish, str) and finish in {"stop", "length", "content_filter"}))
        _require(incoming is None or finish is not None)
        self.finish = finish


class FlashCandidateProbe:
    """Synthetic-only candidate seam; caller must close it. No product port is implemented."""
    def __init__(self, *, virtual_key: str, settings: FlashCandidateSettings | None = None,
                 http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        if (not isinstance(virtual_key, str) or not 1 <= len(virtual_key) <= 512
                or any(not 33 <= ord(char) <= 126 for char in virtual_key)):
            raise ValueError("A valid mounted candidate virtual key is required.")
        self._credential = virtual_key
        self._settings = settings or FlashCandidateSettings()
        self._client = httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=http_transport,
                                        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def native_request(body: CandidateBody) -> bytes:
        """Native envelope only. Relay independently validates final provider bytes."""
        _require(isinstance(body, CandidateBody), ProbeErrorCode.INVALID_REQUEST)
        data = _json(CandidateBody(body.content).content)
        data["model"] = "deepseek/deepseek-flash"
        data["max_completion_tokens"] = data.pop("max_tokens")
        data["fallbacks"], data["store"] = [], False
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

    async def _chunks(self, response: httpx.Response, limit: int) -> AsyncIterator[bytes]:
        _require(response.headers.get("content-encoding", "identity").lower() == "identity")
        size = 0
        async for raw in response.aiter_bytes():
            size += len(raw)
            _require(size <= limit)
            yield raw

    async def _events(self, response: httpx.Response) -> AsyncIterator[bytes]:
        # Line framing is byte-incremental (including split CRLF and UTF-8).
        line, payload = bytearray(), bytearray()
        event_size = 0
        after_cr = False
        async for raw in self._chunks(response, self._settings.max_stream_bytes):
            for byte in raw:
                if after_cr:
                    after_cr = False
                    if byte == 10:
                        continue
                event_size += 1
                _require(event_size <= self._settings.max_event_bytes)
                if byte not in (10, 13):
                    line.append(byte)
                    continue
                after_cr = byte == 13
                value = bytes(line)
                line.clear()
                try:
                    value.decode("utf-8")
                except UnicodeError:
                    raise CandidateProbeError() from None
                if not value:
                    if payload:
                        yield bytes(payload[:-1])
                    payload.clear()
                    event_size = 0
                elif value.startswith(b"data:"):
                    content = value[5:]
                    payload.extend(content[1:] if content.startswith(b" ") else content)
                    payload.extend(b"\n")
                elif value.startswith(b"event:"):
                    _require(value[6:].strip() in {b"", b"message"})
                else:
                    # SSE comments/id/retry are framing metadata, never evidence.
                    _require(value.startswith((b":", b"id:", b"retry:")))
        _require(not line and not payload)

    async def _stream(self, response: httpx.Response, body: CandidateBody, facts: _StreamFacts) -> ProbeOutcome:
        _require(response.headers.get("content-type", "").split(";")[0].strip().lower() == "text/event-stream")
        async for raw in self._events(response):
            _require(not facts.done)
            if raw == b"[DONE]":
                _require(facts.finish is not None and facts.usage is not None and facts.identity is not None)
                facts.done = True
                continue
            facts.add(_json(raw), self._credential)
            if body.case_ref == "CANCEL" and facts.text:
                return ProbeOutcome.CANCELLED
        _require(facts.done)
        return ProbeOutcome.COMPLETE

    async def _complete(self, response: httpx.Response, body: CandidateBody) -> CandidateProbeEvidence:
        _require(response.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json")
        raw = bytearray()
        async for chunk in self._chunks(response, self._settings.max_response_bytes):
            raw.extend(chunk)
        data = _json(bytes(raw))
        identity, ref = _identity(data, self._credential)
        _require(data.get("object") == "chat.completion")
        choice = _choice(data)
        message = _object(choice.get("message"))
        _require(message.get("role") == "assistant")
        return CandidateProbeEvidence(body.case_ref, body.body_sha256, datetime.now(UTC), ProbeOutcome.COMPLETE,
                                      identity, ref, _usage(data.get("usage")), _capability(body.case_ref, message, choice.get("finish_reason")))

    async def probe(self, body: CandidateBody, *, timeout_seconds: float) -> CandidateProbeEvidence:
        _require(isinstance(body, CandidateBody) and isinstance(timeout_seconds, int | float) and not isinstance(timeout_seconds, bool)
                 and math.isfinite(timeout_seconds) and 0 < timeout_seconds <= 120, ProbeErrorCode.INVALID_REQUEST)
        native = self.native_request(body)
        # Refuse concurrent calls rather than queueing automatic later dispatch.
        _require(not self._lock.locked(), ProbeErrorCode.INVALID_REQUEST)
        facts = _StreamFacts()
        async with self._lock:
            try:
                async with asyncio.timeout(timeout_seconds):
                    request = self._client.build_request("POST", self._settings.inference_url, content=native, timeout=timeout_seconds,
                                                         headers={"x-bf-vk": self._credential, "content-type": "application/json",
                                                                  "accept-encoding": "identity", "x-request-id": "candidate-" + body.marker.hex})
                    request.headers.pop("cookie", None)
                    response = await self._client.send(request, stream=True)
                    try:
                        _require(response.status_code == 200, ProbeErrorCode.HTTP_REFUSED)
                        if not body.stream:
                            return await self._complete(response, body)
                        outcome = await self._stream(response, body, facts)
                        return CandidateProbeEvidence(body.case_ref, body.body_sha256, datetime.now(UTC), outcome,
                                                      facts.identity, facts.ref, facts.usage if outcome is ProbeOutcome.COMPLETE else None,
                                                      outcome is ProbeOutcome.COMPLETE and facts.finish == "stop" and facts.text.strip() == "OK",
                                                      facts.count)
                    finally:
                        await response.aclose()
            except (TimeoutError, httpx.TimeoutException):
                return CandidateProbeEvidence(body.case_ref, body.body_sha256, datetime.now(UTC), ProbeOutcome.TIMEOUT,
                                              facts.identity, facts.ref, None, False, facts.count)
            except httpx.TransportError:
                raise CandidateProbeError(ProbeErrorCode.CONNECTION_FAILED) from None
