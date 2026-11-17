"""Bifrost native HTTP transport; not wired into production by default (S16).

Wire reference: maximhq/bifrost, transports/v2.5.1, 7cb75fb2f8276ca48d0792c857fecb67b8879e2f,
docs/openapi/schemas/inference/{chat,common}.yaml and core/schemas/{chatcompletions,bifrost}.go.

An evidence record is a trusted composition input backed by independently verified provider documentation,
NOT proof manufactured from a model/version string. There are no built-in records. In particular the
documented DeepSeek aliases cannot meet the current immutable-version requirement (NCP-16 unresolved).
Gateway authorization/budget/redaction happen before this seam. This module adds no approval bypass,
provider credentials, retries, fallback, tool execution or public configuration endpoint.
"""
import asyncio
import json
import math
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, NoReturn, Self

import httpx
import jsonschema
from referencing import Registry
from referencing.exceptions import Unresolvable

from ai_res.llm.errors import (
    CapabilityNotSupported,
    GatewayUnconfigured,
    InvalidProviderOutput,
    InvalidRequest,
    LLMError,
    ModelProfileNotApproved,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from ai_res.llm.registry import ProfileStatus
from ai_res.llm.transport import TransportCall, TransportEmbeddingCall, TransportEmbeddingResult, TransportResult
from ai_res.llm.types import FinishReason, ModelIdentity, StreamChunk, StreamEnd, TextDelta, ToolCall, ToolCallChunk, Usage

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HOSTS = frozenset({"bifrost-poc", "bifrost"})
_ROLLING_DEEPSEEK = frozenset({"deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"})
_FINISH = {"stop": FinishReason.STOP, "length": FinishReason.LENGTH, "tool_calls": FinishReason.TOOL_CALLS,
           "content_filter": FinishReason.CONTENT_FILTER}


@dataclass(frozen=True, slots=True, kw_only=True)
class BifrostSettings:
    """WORKING transport limits, not product SLOs. Internal URL validation complements network egress enforcement."""
    inference_url: str = "http://bifrost-poc:8080/v1/chat/completions"
    max_request_bytes: int = 2_097_152
    max_response_bytes: int = 2_097_152
    max_event_bytes: int = 65_536
    max_stream_bytes: int = 8_388_608
    max_tool_calls: int = 32
    max_tool_argument_bytes: int = 65_536

    def __post_init__(self) -> None:
        try:
            u = httpx.URL(self.inference_url)
            valid = (u.scheme in {"http", "https"} and u.host in _HOSTS and u.port in {None, 8080}
                     and not u.userinfo and not u.query and not u.fragment and u.path == "/v1/chat/completions")
        except (ValueError, TypeError, httpx.InvalidURL):
            valid = False
        if not valid:
            raise ValueError("Bifrost inference URL must name the internal inference endpoint")
        for value in (self.max_request_bytes, self.max_response_bytes, self.max_event_bytes, self.max_stream_bytes,
                      self.max_tool_calls, self.max_tool_argument_bytes):
            if type(value) is not int or value < 1:
                raise ValueError("Bifrost transport limits must be positive integers")


@dataclass(frozen=True, slots=True, kw_only=True)
class ImmutableModelEvidence:
    """Binding supplied by trusted deployment composition after verifying an immutable selector with the provider.

    Neither a fingerprint nor this record's existence establishes provider pinning. An empty collection
    is the default. Synthetic selectors belong only in unit fixtures; real DeepSeek aliases are refused.
    """
    provider: str
    request_model_id: str
    response_model_id: str
    pinned_model_version: str
    evidence_ref: str
    expected_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and _NAME.fullmatch(v) for v in (
                self.provider, self.request_model_id, self.response_model_id, self.pinned_model_version, self.evidence_ref)):
            raise ValueError("immutable evidence needs exact identifiers and an evidence reference")
        if self.expected_fingerprint is not None and (not isinstance(self.expected_fingerprint, str) or not _NAME.fullmatch(self.expected_fingerprint)):
            raise ValueError("invalid expected fingerprint")


def _invalid() -> InvalidProviderOutput:
    return InvalidProviderOutput("Bifrost response does not satisfy the verified transport contract")


def _utf8_size(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError:
        raise _invalid() from None


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid()
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _invalid()
        out[key] = value
    return out


def _json(raw: bytes | str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        # JSON escapes can decode to unpaired surrogates. Refuse every such scalar before content or tool data can escape.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return _object(value)
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None


def _nonfinite(value: str) -> NoReturn:
    raise _invalid()


def _check_schema(schema: Mapping[str, Any]) -> None:
    """Catalog schemas are local data: do not let validation perform external I/O."""
    todo: list[Any] = [schema]
    seen: set[int] = set()
    while todo:
        value = todo.pop()
        if isinstance(value, dict | list):
            if id(value) in seen:
                continue
            seen.add(id(value))
            if isinstance(value, dict):
                for name in ("$ref", "$dynamicRef"):
                    if name in value and (not isinstance(value[name], str) or not value[name].startswith("#")):
                        raise InvalidRequest("Bifrost schemas must use local references")
                todo.extend(value.values())
            else:
                todo.extend(value)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except (jsonschema.SchemaError, RecursionError):
        raise InvalidRequest("invalid Bifrost schema") from None


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise _invalid()
    return value


def _reason(value: Any) -> FinishReason:
    if not isinstance(value, str) or value not in _FINISH:
        raise _invalid()
    return _FINISH[value]


def _usage(value: Any, call: TransportCall) -> Usage:
    data = _object(value)
    inp, out = data.get("prompt_tokens"), data.get("completion_tokens")
    if (type(inp) is not int or type(out) is not int or min(inp, out) < 0 or out > call.max_output_tokens
            or inp + out > call.profile.context_window_tokens):
        raise _invalid()
    if "total_tokens" in data and (type(data["total_tokens"]) is not int or data["total_tokens"] != inp + out):
        raise _invalid()
    return Usage(inp, out)


def _validate_schema(schema: Mapping[str, Any], value: Any) -> None:
    try:
        jsonschema.Draft202012Validator(schema, registry=Registry()).validate(value)
    except (jsonschema.ValidationError, jsonschema.SchemaError, Unresolvable, RecursionError):
        raise _invalid() from None


class BifrostTransport:
    """HTTP transport with incremental, identity-checked SSE. Close explicitly or use its async context manager."""

    conservative_usage_on_error = True  # real dispatch may have billed even when no response/chunk was received

    def __init__(self, settings: BifrostSettings | None = None, *, virtual_key: str | None = None,
                 immutable_evidence: Sequence[ImmutableModelEvidence] = (), http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings or BifrostSettings()
        if virtual_key is not None and (not isinstance(virtual_key, str) or not virtual_key or len(virtual_key) > 512
                                        or any(ord(c) < 33 or ord(c) > 126 for c in virtual_key)):
            raise ValueError("invalid Bifrost virtual-key credential")
        self._credential = virtual_key
        self._bindings = tuple(immutable_evidence)
        keys = [(e.provider, e.request_model_id, e.pinned_model_version) for e in self._bindings]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate immutable model evidence")
        self._client = httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=http_transport,
                                        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _binding(self, call: TransportCall) -> ImmutableModelEvidence:
        p = call.profile
        if p.status is not ProfileStatus.APPROVED:
            raise ModelProfileNotApproved("Bifrost transport requires an approved profile")
        if not self._credential or (p.provider.lower() == "deepseek" and p.provider_model_id.lower() in _ROLLING_DEEPSEEK):
            raise GatewayUnconfigured("no verified immutable Bifrost route is configured")
        for binding in self._bindings:
            if (p.provider, p.provider_model_id, p.pinned_model_version) == (
                    binding.provider, binding.request_model_id, binding.pinned_model_version):
                return binding
        raise GatewayUnconfigured("no verified immutable Bifrost route is configured")

    def _request(self, call: TransportCall, stream: bool) -> tuple[ImmutableModelEvidence, dict[str, str], bytes]:
        binding = self._binding(call)
        if (type(call.max_output_tokens) is not int or not 1 <= call.max_output_tokens <= call.profile.max_output_tokens
                or not isinstance(call.timeout_seconds, int | float) or isinstance(call.timeout_seconds, bool)
                or not math.isfinite(call.timeout_seconds) or call.timeout_seconds <= 0 or not isinstance(call.request_id, str)
                or not _NAME.fullmatch(call.request_id)):
            raise InvalidRequest("invalid Bifrost call limits or request identifier")
        data: dict[str, Any] = {"model": f"{binding.provider}/{binding.request_model_id}",
                                "messages": [{"role": m.role.value.lower(), "content": m.content} for m in call.messages],
                                "stream": stream, "max_completion_tokens": call.max_output_tokens, "fallbacks": [], "store": False}
        if call.tool_definitions is not None:
            self._tool_schemas(call)
            data["tools"] = call.tool_definitions
        if call.response_schema is not None:
            if stream:
                raise InvalidRequest("structured streaming is not supported")
            _check_schema(call.response_schema)
            data["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": call.response_schema}}
        if stream:
            data["stream_options"] = {"include_usage": True}
        try:
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, TypeError, RecursionError):
            raise InvalidRequest("Bifrost request cannot be encoded") from None
        if len(encoded) > self._settings.max_request_bytes:
            raise InvalidRequest("Bifrost request exceeds the transport limit")
        headers = {"content-type": "application/json", "accept-encoding": "identity", "x-request-id": call.request_id}
        if self._credential is not None:
            headers["x-bf-vk"] = self._credential
        if call.traceparent is not None:
            if not re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", call.traceparent):
                raise InvalidRequest("invalid trace context")
            headers["traceparent"] = call.traceparent
        return binding, headers, encoded

    @staticmethod
    def _identity(data: dict[str, Any], binding: ImmutableModelEvidence) -> None:
        routing = _object(_object(data.get("extra_fields")).get("routing_info"))
        if (data.get("model") != binding.response_model_id or routing.get("provider") != binding.provider
                or routing.get("model") != binding.request_model_id or routing.get("is_fallback", False) is not False
                or routing.get("server_side_fallback_model") not in (None, "")
                or routing.get("resolved_key_alias") is not None
                or routing.get("requested_model", binding.request_model_id) != binding.request_model_id):
            raise _invalid()
        if binding.expected_fingerprint is not None and data.get("system_fingerprint") != binding.expected_fingerprint:
            raise _invalid()

    @staticmethod
    def _http_status(status: int, retry_after: Any = None) -> None:
        if status == 200:
            return
        retry: float | None = None
        try:
            hint = float(retry_after)
            if math.isfinite(hint) and 0 <= hint <= 300:
                retry = hint
        except (ValueError, TypeError):
            pass
        if status == 429:
            raise ProviderRateLimited("Bifrost rate limited the request", retry_after_seconds=retry)
        if status in {408, 504}:
            raise ProviderTimeout("Bifrost request timed out")
        if status >= 500:
            raise ProviderUnavailable("Bifrost is unavailable")
        raise ProviderRejected("Bifrost refused the request")

    @classmethod
    def _error_frame(cls, data: dict[str, Any]) -> None:
        if data.get("error") is not None or data.get("is_bifrost_error") is True:
            status = data.get("status_code")
            extra = data.get("extra_fields")
            ms = extra.get("retry_after_ms") if isinstance(extra, dict) else None
            retry = ms / 1000 if isinstance(ms, int | float) and not isinstance(ms, bool) and 0 <= ms <= 300_000 else None
            if type(status) is int and 400 <= status <= 599:
                cls._http_status(status, retry)
            raise ProviderRejected("Bifrost reported an inference error")

    async def _raw(self, response: httpx.Response, *, limit: int, timeout: float) -> AsyncIterator[bytes]:
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise _invalid()
        total = 0
        remaining = timeout
        # Do not request a fixed chunk size: httpx would buffer a small SSE event
        # until that size was reached, defeating incremental delivery/cancellation.
        it = response.aiter_bytes().__aiter__()
        while True:
            start = time.monotonic()
            try:
                async with asyncio.timeout(remaining):
                    part = await anext(it)
            except StopAsyncIteration:
                return
            remaining -= time.monotonic() - start
            total += len(part)
            if total > limit:
                raise _invalid()
            yield part

    async def complete(self, call: TransportCall) -> TransportResult:
        binding, headers, body = self._request(call, False)
        try:
            return await self._complete_wire(call, binding, headers, body)
        except LLMError as error:
            error.possibly_billed = True
            raise

    async def _complete_wire(self, call: TransportCall, binding: ImmutableModelEvidence, headers: dict[str, str], body: bytes) -> TransportResult:
        try:
            async with asyncio.timeout(call.timeout_seconds):
                async with self._response(body, headers, call.timeout_seconds) as response:
                    self._http_status(response.status_code, response.headers.get("retry-after"))
                    parts = [part async for part in self._raw(response, limit=self._settings.max_response_bytes, timeout=call.timeout_seconds)]
                    data = _json(b"".join(parts))
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderTimeout("Bifrost request timed out") from None
        except httpx.TransportError:
            raise ProviderUnavailable("Bifrost connection failed") from None
        self._error_frame(data)
        self._identity(data, binding)
        choice = self._choice(data)
        reason = _reason(choice.get("finish_reason"))
        message = _object(choice.get("message"))
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise _invalid()
        output: str | Mapping[str, Any] | None = content
        tools = self._tools(message.get("tool_calls", []), call)
        if bool(tools) != (reason is FinishReason.TOOL_CALLS):
            raise _invalid()
        if call.response_schema is not None:
            if reason is not FinishReason.STOP or not isinstance(content, str):
                raise _invalid()
            output = _json(content)
            _validate_schema(call.response_schema, output)
        return TransportResult(output=output, finish_reason=reason, usage=_usage(data.get("usage"), call),
                               tool_calls=tools, provider_request_ref=_identifier(data.get("id")))

    @asynccontextmanager
    async def _response(self, body: bytes, headers: dict[str, str], timeout: float) -> AsyncIterator[httpx.Response]:
        request = self._client.build_request("POST", self._settings.inference_url, content=body, headers=headers, timeout=timeout)
        request.headers.pop("cookie", None)  # inference identities are explicit; never inherit a prior scope's cookies
        async with asyncio.timeout(timeout):
            response = await self._client.send(request, stream=True)
        try:
            yield response
        finally:
            await response.aclose()

    @staticmethod
    def _choice(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise _invalid()
        choice = _object(choices[0])
        if type(choice.get("index")) is not int or choice["index"] != 0:
            raise _invalid()
        return choice

    def _tool_schemas(self, call: TransportCall) -> dict[str, Mapping[str, Any]]:
        schemas: dict[str, Mapping[str, Any]] = {}
        for tool in call.tool_definitions or ():
            try:
                fn = _object(tool.get("function"))
                name = _identifier(fn.get("name"))
                schema = _object(fn.get("parameters"))
                if tool.get("type") != "function" or name in schemas:
                    raise InvalidRequest("invalid Bifrost tool definitions")
                _check_schema(schema)
            except (InvalidProviderOutput, jsonschema.SchemaError):
                raise InvalidRequest("invalid Bifrost tool definitions") from None
            schemas[name] = schema
        return schemas

    def _tools(self, value: Any, call: TransportCall) -> tuple[ToolCall, ...]:
        if not isinstance(value, list) or len(value) > self._settings.max_tool_calls:
            raise _invalid()
        schemas = self._tool_schemas(call)
        result: list[ToolCall] = []
        ids: set[str] = set()
        for item in value:
            tool = _object(item)
            fn = _object(tool.get("function"))
            name, ident = _identifier(fn.get("name")), _identifier(tool.get("id"))
            args = fn.get("arguments")
            if (tool.get("type") != "function" or name not in schemas or ident in ids or not isinstance(args, str)
                    or _utf8_size(args) > self._settings.max_tool_argument_bytes):
                raise _invalid()
            parsed = _json(args)
            _validate_schema(schemas[name], parsed)
            result.append(ToolCall(ident, name, parsed))
            ids.add(ident)
        return tuple(result)

    async def _events(self, response: httpx.Response, call: TransportCall) -> AsyncIterator[bytes]:
        if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "text/event-stream":
            raise _invalid()
        pending = b""
        data: list[bytes] = []
        event_size = 0
        async for part in self._raw(response, limit=self._settings.max_stream_bytes, timeout=call.timeout_seconds):
            pending += part
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                line = line.removesuffix(b"\r")
                event_size += len(line)
                if event_size > self._settings.max_event_bytes:
                    raise _invalid()
                if not line:
                    if data:
                        yield b"\n".join(data)
                    data, event_size = [], 0
                elif line.startswith(b"data:"):
                    data.append(line[5:].removeprefix(b" "))
                elif not line.startswith((b":", b"event:", b"id:")):
                    raise _invalid()
            if len(pending) + event_size > self._settings.max_event_bytes:
                raise _invalid()
        if pending or data:
            raise _invalid()

    async def stream(self, call: TransportCall) -> AsyncIterator[StreamChunk]:
        binding, headers, body = self._request(call, True)
        finished: FinishReason | None = None
        usage: Usage | None = None
        request_ref: str | None = None
        pending_tools: dict[int, dict[str, Any]] = {}
        try:
            async with self._response(body, headers, call.timeout_seconds) as response:
                self._http_status(response.status_code, response.headers.get("retry-after"))
                async for raw in self._events(response, call):
                    if raw == b"[DONE]":
                        if finished is None or usage is None or request_ref is None:
                            raise _invalid()
                        tools = self._tools(list(pending_tools.values()), call)
                        if bool(tools) != (finished is FinishReason.TOOL_CALLS):
                            raise _invalid()
                        for tool in tools:
                            yield ToolCallChunk(tool)
                        p = call.profile
                        identity = ModelIdentity(p.id, p.profile_key, p.profile_version, p.provider, p.provider_model_id, p.pinned_model_version)
                        yield StreamEnd(identity, finished, usage, request_ref)
                        return
                    data = _json(raw)
                    self._error_frame(data)
                    self._identity(data, binding)
                    ref = _identifier(data.get("id"))
                    if request_ref is not None and ref != request_ref:
                        raise _invalid()
                    request_ref = ref
                    if data.get("usage") is not None:
                        if usage is not None:
                            raise _invalid()
                        if finished is None and self._choice(data).get("finish_reason") is None:
                            raise _invalid()  # an early cumulative usage count cannot settle the whole stream
                        usage = _usage(data["usage"], call)
                    if data.get("choices") == [] and finished is not None and usage is not None:
                        continue
                    if finished is not None:
                        raise _invalid()
                    choice = self._choice(data)
                    delta = _object(choice.get("delta"))
                    text = delta.get("content")
                    if text is not None:
                        if not isinstance(text, str):
                            raise _invalid()
                        if text:
                            yield TextDelta(text)
                    if delta.get("tool_calls") is not None:
                        self._accumulate_tools(delta["tool_calls"], pending_tools)
                    if choice.get("finish_reason") is not None:
                        finished = _reason(choice["finish_reason"])
                raise _invalid()
        except (TimeoutError, httpx.TimeoutException):
            error = ProviderTimeout("Bifrost stream timed out")
            error.possibly_billed = True
            raise error from None
        except httpx.TransportError:
            unavailable = ProviderUnavailable("Bifrost stream connection failed")
            unavailable.possibly_billed = True
            raise unavailable from None
        except LLMError as error:
            error.possibly_billed = True
            raise

    def _accumulate_tools(self, value: Any, pending: dict[int, dict[str, Any]]) -> None:
        if not isinstance(value, list):
            raise _invalid()
        for value_item in value:
            item = _object(value_item)
            index = item.get("index")
            if type(index) is not int or not 0 <= index < self._settings.max_tool_calls:
                raise _invalid()
            current = pending.setdefault(index, {"function": {"arguments": ""}})
            for key in ("id", "type"):
                if key in item:
                    if key in current and current[key] != item[key]:
                        raise _invalid()
                    current[key] = item[key]
            function = _object(item.get("function"))
            if "name" in function:
                if "name" in current["function"] and current["function"]["name"] != function["name"]:
                    raise _invalid()
                current["function"]["name"] = function["name"]
            fragment = function.get("arguments", "")
            if not isinstance(fragment, str):
                raise _invalid()
            current["_argument_bytes"] = current.get("_argument_bytes", 0) + _utf8_size(fragment)
            if current["_argument_bytes"] > self._settings.max_tool_argument_bytes:
                raise _invalid()
            current["function"]["arguments"] += fragment

    async def embed(self, call: TransportEmbeddingCall) -> TransportEmbeddingResult:
        raise CapabilityNotSupported("Bifrost embeddings are outside the first provider profile")
