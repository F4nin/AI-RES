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
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from ai_res.llm.adapters.candidate_control import CandidateClaimReceipt, CandidateControlClient, CandidateControlUnavailable
from ai_res.llm.candidate_payload import CandidatePayloadError, canonicalize_candidate_body
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, load_private_key
from ai_res.platform.config import Settings
from ai_res.platform.ports import ServiceName
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
_HEADERS = frozenset({b"host", b"authorization", b"content-type", b"content-length", b"accept", b"user-agent",
                      b"accept-encoding", b"connection", b"x-request-id", b"traceparent", b"cache-control"})


@dataclass(frozen=True, slots=True, kw_only=True)
class RelayConfig:
    auth_token: str = field(repr=False)
    provider_key: str | None = field(default=None, repr=False)
    allow_provider_calls: bool = False
    max_body_bytes: int = 4096
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
    cache = [value for name, value in raw if name == b"cache-control"]
    if (len(hosts) != 1 or hosts[0] not in [host.encode("ascii") for host in config.allowed_hosts]
            or len(lengths) > 1 or len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json"
            or len(cache) > 1 or cache and cache[0] != b"no-cache"
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
               client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
               control_client: CandidateControlClient | None = None) -> Starlette:
    """Dependency injection is test composition only; upstream hostname/port/path are never configuration or request inputs."""
    slots = asyncio.Semaphore(config.max_concurrent)

    async def health(request: Request) -> Response:
        if request.scope.get("raw_path") != b"/health" or request.scope.get("query_string"):
            return _error("NOT_FOUND", 404)
        return JSONResponse({"status": "enabled" if config.allow_provider_calls and control_client is not None else "disabled"})

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
        if control_client is None:
            return _error("CANDIDATE_CONTROL_REQUIRED", 503)
        if slots.locked():
            return _error("RELAY_BUSY", 429)
        await slots.acquire()
        client: httpx.AsyncClient | None = None
        upstream: httpx.Response | None = None
        handed_off = False
        receipt: CandidateClaimReceipt | None = None
        accounting_attempted = False
        unknown_reason = "NETWORK"
        redaction_tails: dict[tuple[str, ...], str] = {}
        redaction_bytes = 0
        tail_length = max(len(provider_key), len(config.auth_token))-1
        deadline = asyncio.get_running_loop().time() + config.total_timeout_seconds

        async def account_known(result: dict[str, Any]) -> None:
            nonlocal accounting_attempted
            assert control_client is not None and receipt is not None
            usage = result.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            # Mark attempted before the RPC: lost ACK may already be committed.
            # Never follow it with a conflicting UNKNOWN or another dispatch.
            accounting_attempted = True
            await control_client.settle_known(receipt, input_tokens=usage.get("prompt_tokens"),
                                               output_tokens=usage.get("completion_tokens"), provider_request_ref=result.get("id"))

        def safe_result(result: dict[str, Any]) -> None:
            nonlocal redaction_bytes
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if provider_key in encoded or config.auth_token in encoded:
                raise _Failure("UPSTREAM_FORMAT_INVALID", 502)

            def scan(value: Any, path: tuple[str, ...] = ()) -> None:
                nonlocal redaction_bytes
                if isinstance(value, str):
                    previous = redaction_tails.get(path, "")
                    joined = previous+value
                    if provider_key in joined or config.auth_token in joined:
                        raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                    tail = joined[-tail_length:]
                    redaction_bytes += len(tail.encode())-len(previous.encode())
                    if path not in redaction_tails:
                        redaction_bytes += len(repr(path).encode())
                    if redaction_bytes > config.max_response_bytes:
                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                    redaction_tails[path] = tail
                elif isinstance(value, dict):
                    for key, item in value.items():
                        scan(item, (*path, key))
                elif isinstance(value, list):
                    # One conservative channel per structural string field:
                    # tool/choice array positions cannot evade split detection.
                    for item in value:
                        scan(item, (*path, "*"))

            scan(result)

        async def close() -> None:
            nonlocal client, upstream, accounting_attempted
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
                try:
                    if receipt is not None and not accounting_attempted:
                        # No successful evidence is returned for this outcome.
                        # A failed callback leaves DB state authoritative, without
                        # refunding or reopening any one-use claim.
                        accounting_attempted = True
                        with contextlib.suppress(CandidateControlUnavailable):
                            await control_client.settle_unknown(receipt, reason=unknown_reason)
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
                try:
                    candidate = canonicalize_candidate_body(bytes(raw))
                except CandidatePayloadError:
                    raise _Failure("INVALID_REQUEST") from None
                stream = candidate.stream
                address = _public_address(await resolver(UPSTREAM_HOST, UPSTREAM_PORT))
                host = f"[{address}]" if ":" in address else address
                client = client_factory(verify=True, trust_env=False, follow_redirects=False,
                                        timeout=httpx.Timeout(15.0, connect=5.0, pool=1.0, write=5.0),
                                        limits=httpx.Limits(max_connections=config.max_concurrent, max_keepalive_connections=0))
                outgoing = client.build_request("POST", f"https://{host}{UPSTREAM_PATH}", content=candidate.content,
                                                headers={"host": UPSTREAM_HOST, "authorization": "Bearer " + provider_key,
                                                         "content-type": "application/json", "accept-encoding": "identity",
                                                         "accept": "text/event-stream" if stream else "application/json"},
                                                extensions={"sni_hostname": UPSTREAM_HOST})
                receipt = await control_client.claim(candidate)
                upstream = await client.send(outgoing, stream=True)
                if upstream.status_code != 200:
                    unknown_reason = "PROVIDER_ERROR"
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
                        nonlocal unknown_reason
                        total = 0
                        pending = bytearray()
                        observed: dict[str, Any] = {}
                        ended = False
                        try:
                            async with asyncio.timeout_at(deadline):
                                async for part in response.aiter_bytes():
                                    total += len(part)
                                    if total > config.max_response_bytes:
                                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                                    pending.extend(part)
                                    # Normalize SSE line endings before splitting
                                    # events; the byte/event bound applies first.
                                    pending[:] = pending.replace(b"\r\n", b"\n")
                                    while b"\n\n" in pending:
                                        event, _, rest = pending.partition(b"\n\n")
                                        pending[:] = rest
                                        if len(event) > 65_536:
                                            raise _Failure("UPSTREAM_TOO_LARGE", 502)
                                        lines = event.split(b"\n")
                                        if any(line and not line.startswith((b"data:", b":")) for line in lines):
                                            raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                        data = b"\n".join(line[5:].lstrip(b" ") for line in lines if line.startswith(b"data:"))
                                        if not data:
                                            continue
                                        if data == b"[DONE]":
                                            if "usage" not in observed or "id" not in observed:
                                                raise _Failure("UPSTREAM_USAGE_MISSING", 502)
                                            await account_known(observed)
                                            ended = True
                                            yield b"data: [DONE]\n\n"
                                            return
                                        value = _loads(data)
                                        if not isinstance(value, dict) or "error" in value:
                                            raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                        choices = value.get("choices", [])
                                        if not isinstance(choices, list) or len(choices) > 1:
                                            raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                        for choice in choices:
                                            # These streaming templates request exactly one
                                            # text choice and no tools. Refuse extra semantic
                                            # channels before any fragment can be exported;
                                            # they must not overwrite a secret-prefix tail.
                                            if (not isinstance(choice, dict) or type(choice.get("index")) is not int
                                                    or choice["index"] != 0):
                                                raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                            delta = choice.get("delta", {})
                                            if (not isinstance(delta, dict) or delta.get("tool_calls") not in (None, [])
                                                    or delta.get("function_call") is not None
                                                    or delta.get("content") is not None and not isinstance(delta["content"], str)):
                                                raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                        safe_result(value)
                                        if "id" in value:
                                            if "id" in observed and observed["id"] != value["id"]:
                                                raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                            observed["id"] = value["id"]
                                        if value.get("usage") is not None:
                                            if "usage" in observed and observed["usage"] != value["usage"]:
                                                raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                                            observed["usage"] = value["usage"]
                                        yield b"data: "+data+b"\n\n"
                                    if len(pending) > 65_536:
                                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                                if not ended:
                                    raise _Failure("UPSTREAM_STREAM_INCOMPLETE", 502)
                        except asyncio.CancelledError:
                            unknown_reason = "CANCEL"
                            raise
                        except (TimeoutError, httpx.HTTPError, OSError, _Failure, ValueError, UnicodeError, RecursionError,
                                CandidateControlUnavailable) as error:
                            unknown_reason = "TIMEOUT" if isinstance(error, TimeoutError) else "UNTRUSTED_RESPONSE"
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
                    safe_result(result)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise _Failure("UPSTREAM_FORMAT_INVALID", 502) from exc
                await account_known(result)
                return JSONResponse(result, headers={"cache-control": "no-store"})
        except _Failure as exc:
            return _error(exc.code, exc.status)
        except TimeoutError:
            unknown_reason = "TIMEOUT"
            return _error("UPSTREAM_TIMEOUT", 504)
        except CandidateControlUnavailable:
            return _error("CANDIDATE_CONTROL_UNAVAILABLE", 503)
        except (httpx.HTTPError, OSError):
            unknown_reason = "NETWORK"
            return _error("UPSTREAM_UNAVAILABLE", 502)
        except asyncio.CancelledError:
            unknown_reason = "CANCEL"
            raise
        except ClientDisconnect:
            unknown_reason = "CANCEL"
            return _error("CLIENT_DISCONNECTED", 400)
        finally:
            if not handed_off:
                await close()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> Any:
        try:
            yield
        finally:
            if control_client is not None:
                await control_client.aclose()

    return Starlette(lifespan=lifespan, routes=[Route("/health", health, methods=["GET"]),
                             Route("/{path:path}", dispatch, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "CONNECT", "HEAD"])])


def _mounted_bytes(path: Path) -> bytes:
    """Read a bounded regular, non-writable-by-others mounted file, never echo it."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 4096:
                raise ValueError("unsafe secret file")
            return stream.read(4097)
    except OSError:
        raise ValueError("cannot load mounted file") from None


def read_secret_file(path: Path) -> str:
    """Compose secrets may be 0444; credential values are never printed."""
    try:
        value = _mounted_bytes(path).decode("ascii").strip()
        if not _SECRET.fullmatch(value):
            raise ValueError("invalid secret file")
        return value
    except (OSError, UnicodeError) as exc:
        raise ValueError("cannot load secret file") from exc


def control_from_env(env: dict[str, str]) -> CandidateControlClient:
    """Explicit host composition only; does not establish tariff freshness/approval."""
    try:
        allowed = {"AI_RES_CANDIDATE_SERVICE_KEY_FILE", "AI_RES_CANDIDATE_CA_FILE", "AI_RES_CANDIDATE_CONTROL_URL"}
        if any(key.startswith("AI_RES_CANDIDATE_") and key not in allowed for key in env):
            raise ValueError("unknown candidate client host configuration")
        key_file = Path(env["AI_RES_CANDIDATE_SERVICE_KEY_FILE"])
        ca_file = Path(env["AI_RES_CANDIDATE_CA_FILE"])
        _mounted_bytes(key_file)
        _mounted_bytes(ca_file)
        maximum = Settings().service_token_max_ttl_seconds
        seconds = int(env.get("AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS", str(maximum)))
        if not 0 < seconds <= maximum:
            raise ValueError("invalid service identity lifetime")
        lifetime = timedelta(seconds=seconds)
        issuer = ServiceTokenIssuer(ServiceName.LLM_GATEWAY, load_private_key(key_file), max_ttl=lifetime)
        return CandidateControlClient(env.get("AI_RES_CANDIDATE_CONTROL_URL", "https://llm-poc-control:8443"), ca_file=ca_file,
                                      token_supplier=lambda: issuer.issue(ServiceName.API, lifetime))
    except Exception:
        raise ValueError("candidate control host configuration unavailable") from None


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
        control = control_from_env(dict(os.environ)) if args.allow_provider_calls else None
    except (KeyError, ValueError):
        raise SystemExit("invalid relay configuration; mounted credentials required") from None
    # No access logs or request exception repr; downstream errors are normalized in dispatch/chunks.
    # Isolated opt-in Compose network, never a host-published listener.
    uvicorn.run(create_app(config, control_client=control), host="0.0.0.0", port=8081,  # noqa: S104 - isolated container bind
                access_log=False, log_level="critical", server_header=False, proxy_headers=False)


if __name__ == "__main__":
    main()
