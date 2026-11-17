"""S16 opt-in fixed-destination PoC relay; not a model approval or general HTTP proxy.

WORKING safety limits deliberately constrain this probe to short text-only Flash calls.
The production factory stays disabled until model pinning and human acceptance are resolved.
CLI reads mounted secret files only; import/create_app never read the environment or files.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hmac
import ipaddress
import json
import math
import os
import re
import socket
import stat
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

UPSTREAM_HOST = "api.deepseek.com"
UPSTREAM_PORT = 443
UPSTREAM_PATH = "/chat/completions"
MODEL = "deepseek-flash"
_SECRET = re.compile(r"^[A-Za-z0-9_.:-]{32,256}$")
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_HEADERS = frozenset({b"host", b"authorization", b"content-type", b"content-length", b"accept", b"user-agent",
                      b"accept-encoding", b"connection", b"x-request-id", b"traceparent"})


@dataclass(frozen=True, slots=True, kw_only=True)
class RelayConfig:
    auth_token: str = field(repr=False)
    provider_key: str | None = field(default=None, repr=False)
    allow_provider_calls: bool = False
    max_body_bytes: int = 16_384
    max_response_bytes: int = 1_048_576
    max_concurrent: int = 1
    total_timeout_seconds: float = 30.0
    allowed_hosts: tuple[str, ...] = ("llm-gateway:8081", "llm-gateway", "relay", "127.0.0.1:8081")

    def __post_init__(self) -> None:
        if not _SECRET.fullmatch(self.auth_token) or (self.provider_key is not None and not _SECRET.fullmatch(self.provider_key)):
            raise ValueError("invalid relay credential configuration")
        if self.provider_key is not None and hmac.compare_digest(self.auth_token, self.provider_key):
            raise ValueError("relay and provider credentials must differ")
        if type(self.allow_provider_calls) is not bool:
            raise ValueError("provider calls require an explicit boolean")
        if self.allow_provider_calls and self.provider_key is None:
            raise ValueError("provider calls require a provider credential")
        if (type(self.max_body_bytes) is not int or not 256 <= self.max_body_bytes <= 65_536
                or type(self.max_response_bytes) is not int or not 1 <= self.max_response_bytes <= 2_097_152
                or type(self.max_concurrent) is not int or not 1 <= self.max_concurrent <= 4
                or not math.isfinite(self.total_timeout_seconds) or not 0 < self.total_timeout_seconds <= 60
                or not self.allowed_hosts):
            raise ValueError("invalid relay limit configuration")


class _Failure(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code, self.status = code, status


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise ValueError("non-JSON number")


def _loads(raw: bytes) -> Any:
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_constant)
    # Escaped invalid Unicode must be rejected before forwarding or ASGI response encoding.
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return value


def _payload(raw: bytes) -> tuple[dict[str, Any], bool]:
    try:
        payload = _loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _Failure("INVALID_JSON") from exc
    allowed = {"model", "messages", "max_tokens", "stream", "stream_options", "thinking", "temperature",
               "response_format", "tools", "tool_choice"}
    if not isinstance(payload, dict) or set(payload) - allowed or payload.get("model") != MODEL:
        raise _Failure("INVALID_REQUEST")
    cap = payload.get("max_tokens")
    if type(cap) is not int or not 1 <= cap <= 1024:
        raise _Failure("INVALID_TOKEN_CAP")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
        raise _Failure("INVALID_MESSAGES")
    for message in messages:
        if (not isinstance(message, dict) or set(message) != {"role", "content"}
                or message["role"] not in ("system", "user", "assistant")
                or not isinstance(message["content"], str) or len(message["content"]) > 8192):
            raise _Failure("INVALID_MESSAGES")
    stream = payload.get("stream", False)
    if type(stream) is not bool:
        raise _Failure("INVALID_STREAM")
    if "stream_options" in payload:
        options = payload["stream_options"]
        if (not isinstance(options, dict) or set(options) != {"include_usage"}
                or type(options["include_usage"]) is not bool or not stream):
            raise _Failure("INVALID_STREAM")
    if "thinking" in payload and payload["thinking"] != {"type": "disabled"}:
        raise _Failure("THINKING_DISABLED")
    if "temperature" in payload:
        temperature = payload["temperature"]
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2 or not math.isfinite(temperature):
            raise _Failure("INVALID_TEMPERATURE")
    if "response_format" in payload and payload["response_format"] not in ({"type": "text"}, {"type": "json_object"}):
        raise _Failure("INVALID_FORMAT")
    tool_names: set[str] = set()
    if "tools" in payload:
        tools = payload["tools"]
        if not isinstance(tools, list) or not 1 <= len(tools) <= 8:
            raise _Failure("INVALID_TOOLS")
        for tool in tools:
            if not isinstance(tool, dict) or set(tool) != {"type", "function"} or tool["type"] != "function":
                raise _Failure("INVALID_TOOLS")
            function = tool["function"]
            if (not isinstance(function, dict) or set(function) - {"name", "description", "parameters", "strict"}
                    or not isinstance(function.get("name"), str) or not _NAME.fullmatch(function["name"])
                    or function["name"] in tool_names or not isinstance(function.get("parameters"), dict)
                    or function["parameters"].get("type") != "object"
                    or ("description" in function and not isinstance(function["description"], str))
                    or ("strict" in function and type(function["strict"]) is not bool)):
                raise _Failure("INVALID_TOOLS")
            tool_names.add(function["name"])
    if "tool_choice" in payload:
        choice = payload["tool_choice"]
        named = (isinstance(choice, dict) and set(choice) == {"type", "function"} and choice["type"] == "function"
                 and isinstance(choice["function"], dict) and set(choice["function"]) == {"name"}
                 and isinstance(choice["function"]["name"], str) and choice["function"]["name"] in tool_names)
        if not tool_names or (choice not in ("auto", "none", "required") and not named):
            raise _Failure("INVALID_TOOL_CHOICE")
    payload["thinking"] = {"type": "disabled"}
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload, stream


async def _resolve(host: str, port: int) -> Sequence[str]:
    rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(str(row[4][0]) for row in rows)


def _public_address(addresses: Sequence[str]) -> str:
    if not addresses:
        raise _Failure("UPSTREAM_DNS_DENIED", 502)
    try:
        parsed = [ipaddress.ip_address(address) for address in addresses]
    except ValueError as exc:
        raise _Failure("UPSTREAM_DNS_DENIED", 502) from exc
    if any(not address.is_global for address in parsed):
        raise _Failure("UPSTREAM_DNS_DENIED", 502)
    return str(parsed[0])


def _validate_headers(request: Request, config: RelayConfig) -> None:
    raw = request.scope["headers"]
    auth = [value for name, value in raw if name == b"authorization"]
    expected = ("Bearer " + config.auth_token).encode("ascii")
    if len(auth) != 1 or not hmac.compare_digest(auth[0], expected):
        raise _Failure("UNAUTHORIZED", 401)
    hosts = [value for name, value in raw if name == b"host"]
    lengths = [value for name, value in raw if name == b"content-length"]
    types = [value for name, value in raw if name == b"content-type"]
    if (len(hosts) != 1 or hosts[0] not in [host.encode("ascii") for host in config.allowed_hosts]
            or len(lengths) > 1 or len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json"
            or any(name not in _HEADERS for name, _ in raw)):
        raise _Failure("INVALID_HEADERS")
    if lengths:
        if not lengths[0].isdigit() or len(lengths[0]) > 10:
            raise _Failure("INVALID_HEADERS")
        if int(lengths[0]) > config.max_body_bytes:
            raise _Failure("BODY_TOO_LARGE", 413)


class _StreamResponse(StreamingResponse):
    def __init__(self, content: Any, close: Callable[[], Awaitable[None]]) -> None:
        super().__init__(content, media_type="text/event-stream", headers={"cache-control": "no-store"})
        self._close = close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._close()


def create_app(config: RelayConfig, *, resolver: Callable[[str, int], Awaitable[Sequence[str]]] = _resolve,
               client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient) -> Starlette:
    """Dependency injection is test composition only; upstream hostname/port/path are never configuration or request inputs."""
    slots = asyncio.Semaphore(config.max_concurrent)

    async def health(request: Request) -> Response:
        if request.scope.get("raw_path") != b"/health" or request.scope.get("query_string"):
            return _error("NOT_FOUND", 404)
        return JSONResponse({"status": "enabled" if config.allow_provider_calls else "disabled"})

    async def dispatch(request: Request) -> Response:
        if (request.scope.get("raw_path") != UPSTREAM_PATH.encode("ascii") or request.scope.get("query_string")
                or request.method != "POST"):
            return _error("NOT_FOUND", 404)
        try:
            _validate_headers(request, config)
        except _Failure as exc:
            return _error(exc.code, exc.status)
        provider_key = config.provider_key
        if not config.allow_provider_calls or provider_key is None:
            return _error("PROVIDER_CALLS_DISABLED", 503)
        if slots.locked():
            return _error("RELAY_BUSY", 429)
        await slots.acquire()
        client: httpx.AsyncClient | None = None
        upstream: httpx.Response | None = None
        handed_off = False
        deadline = asyncio.get_running_loop().time() + config.total_timeout_seconds

        async def close() -> None:
            nonlocal client, upstream
            try:
                if upstream is not None:
                    with contextlib.suppress(httpx.HTTPError, OSError):
                        await upstream.aclose()
                    upstream = None
                if client is not None:
                    with contextlib.suppress(httpx.HTTPError, OSError):
                        await client.aclose()
                    client = None
            finally:
                slots.release()

        try:
            async with asyncio.timeout_at(deadline):
                raw = bytearray()
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > config.max_body_bytes:
                        raise _Failure("BODY_TOO_LARGE", 413)
                    raw.extend(chunk)
                content_length = request.headers.get("content-length")
                if content_length is not None and len(raw) != int(content_length):
                    raise _Failure("INVALID_BODY_LENGTH")
                payload, stream = _payload(bytes(raw))
                address = _public_address(await resolver(UPSTREAM_HOST, UPSTREAM_PORT))
                host = f"[{address}]" if ":" in address else address
                client = client_factory(verify=True, trust_env=False, follow_redirects=False,
                                        timeout=httpx.Timeout(15.0, connect=5.0, pool=1.0, write=5.0),
                                        limits=httpx.Limits(max_connections=config.max_concurrent, max_keepalive_connections=0))
                outgoing = client.build_request("POST", f"https://{host}{UPSTREAM_PATH}", json=payload,
                                                headers={"host": UPSTREAM_HOST, "authorization": "Bearer " + provider_key,
                                                         "content-type": "application/json", "accept-encoding": "identity",
                                                         "accept": "text/event-stream" if stream else "application/json"},
                                                extensions={"sni_hostname": UPSTREAM_HOST})
                upstream = await client.send(outgoing, stream=True)
                if upstream.status_code != 200:
                    raise _Failure("UPSTREAM_RATE_LIMIT" if upstream.status_code == 429 else "UPSTREAM_REJECTED",
                                   429 if upstream.status_code == 429 else 502)
                if upstream.headers.get("content-encoding", "identity").lower() != "identity":
                    raise _Failure("UPSTREAM_ENCODING_DENIED", 502)
                media = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if stream:
                    if media != "text/event-stream":
                        raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                    response = upstream

                    async def chunks() -> Any:
                        total = 0
                        try:
                            async with asyncio.timeout_at(deadline):
                                async for part in response.aiter_bytes():
                                    total += len(part)
                                    if total > config.max_response_bytes:
                                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                                    yield part
                        except (TimeoutError, httpx.HTTPError, OSError, _Failure):
                            # An explicit terminal error, no DONE: callers must fail the partial stream.
                            yield b'data: {"error":{"code":"UPSTREAM_STREAM_FAILED"}}\n\n'

                    handed_off = True
                    return _StreamResponse(chunks(), close)
                if media != "application/json":
                    raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                received = bytearray()
                async for part in upstream.aiter_bytes():
                    if len(received) + len(part) > config.max_response_bytes:
                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                    received.extend(part)
                try:
                    result = _loads(bytes(received))
                    if not isinstance(result, dict) or "error" in result:
                        raise ValueError("invalid successful response")
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise _Failure("UPSTREAM_FORMAT_INVALID", 502) from exc
                return JSONResponse(result, headers={"cache-control": "no-store"})
        except _Failure as exc:
            return _error(exc.code, exc.status)
        except TimeoutError:
            return _error("UPSTREAM_TIMEOUT", 504)
        except (httpx.HTTPError, OSError):
            return _error("UPSTREAM_UNAVAILABLE", 502)
        except ClientDisconnect:
            return _error("CLIENT_DISCONNECTED", 400)
        finally:
            if not handed_off:
                await close()

    return Starlette(routes=[Route("/health", health, methods=["GET"]),
                             Route("/{path:path}", dispatch, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "CONNECT", "HEAD"])])


def read_secret_file(path: Path) -> str:
    """Compose secret mounts may be 0444; reject writable-by-other, symlink, nonregular and excessive files. Never echo values."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 4096:
                raise ValueError("unsafe secret file")
            value = stream.read(4097).decode("ascii").strip()
        if not _SECRET.fullmatch(value):
            raise ValueError("invalid secret file")
        return value
    except (OSError, UnicodeError) as exc:
        raise ValueError("cannot load secret file") from exc


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Fixed-destination S16 PoC relay (disabled by default)")
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    try:
        provider_file = os.environ.get("AI_RES_DEEPSEEK_API_KEY_FILE")
        config = RelayConfig(auth_token=read_secret_file(Path(os.environ["AI_RES_LLM_RELAY_AUTH_FILE"])),
                             provider_key=read_secret_file(Path(provider_file)) if provider_file else None,
                             allow_provider_calls=args.allow_provider_calls)
    except (KeyError, ValueError):
        raise SystemExit("invalid relay configuration; mounted credentials required") from None
    # No access logs or request exception repr; downstream errors are normalized in dispatch/chunks.
    # Isolated opt-in Compose network, never a host-published listener.
    uvicorn.run(create_app(config), host="0.0.0.0", port=8081, access_log=False, log_level="critical", server_header=False)  # noqa: S104


if __name__ == "__main__":
    main()
