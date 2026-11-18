"""SLICE-01 tooling: exact frozen CHAT requests, one-use budget claim, fixed egress.

No model approval, general proxy or fake-provider mode. Import/create_app never
read credentials; only main reads mounted files. Dependency injection is solely
for isolated behavioral tests. The original synthetic relay/account stay intact.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import socket
import stat
import sys
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, Protocol

import httpx
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ai_res.llm.budget import Reservation
from ai_res.platform.redaction import scan_secrets

UPSTREAM_HOST = "api.deepseek.com"
UPSTREAM_PORT = 443
UPSTREAM_PATH = "/chat/completions"
MAX_BODY_BYTES = 32768
MAX_RESPONSE_BYTES = 2097152
MAX_OUTPUT_TOKENS = 2048
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SECRET = re.compile(r"[A-Za-z0-9_.:-]{32,256}\Z")
_HEADERS = frozenset({b"host", b"authorization", b"content-type", b"content-length", b"accept", b"user-agent",
                      b"accept-encoding", b"connection", b"x-request-id", b"traceparent", b"cache-control"})


class RelayRefused(ValueError):
    def __init__(self) -> None:
        super().__init__("SLICE request or configuration refused.")


class _Failure(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code, self.status = code, status


class _Ledger(Protocol):
    async def claim(self, request_ref: str, body_sha256: str) -> Reservation: ...

    async def settle_usage(self, reservation: Reservation, *, input_tokens: int, output_tokens: int) -> None: ...

    async def settle_unknown(self, reservation: Reservation) -> None: ...


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RelayRefused()
        result[key] = value
    return result


def _nonfinite(_: str) -> NoReturn:
    raise RelayRefused()


def _encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _loads(raw: bytes) -> Any:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        _encode(value)  # Reject escaped lone surrogates and overflowing floats.
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise RelayRefused() from None


def canonical_body(raw: bytes) -> bytes:
    """Strict, bounded provider bytes; only false store/default false stream normalize.

    The exact canonical digest MUST match the server-owned manifest before claim.
    No unknown execution options, assistant/tool messages, streaming or thinking.
    """
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BODY_BYTES:
            raise RelayRefused()
        value = _loads(raw)
        required = {"model", "messages", "max_tokens", "thinking"}
        if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {"stream", "store"}:
            raise RelayRefused()
        if (value["model"] != "deepseek-flash" or type(value["max_tokens"]) is not int
                or value["max_tokens"] != MAX_OUTPUT_TOKENS or value["thinking"] != {"type": "disabled"}
                or "store" in value and value["store"] is not False or value.get("stream", False) is not False):
            raise RelayRefused()
        messages = value["messages"]
        if not isinstance(messages, list) or not 1 <= len(messages) <= 2:
            raise RelayRefused()
        for index, message in enumerate(messages):
            expected_role = "system" if len(messages) == 2 and index == 0 else "user"
            if (not isinstance(message, dict) or message.keys() != {"role", "content"}
                    or message["role"] != expected_role or not isinstance(message["content"], str) or not message["content"]):
                raise RelayRefused()
        value.pop("store", None)
        value["stream"] = False
        result = _encode(value)
        if len(result) > MAX_BODY_BYTES:
            raise RelayRefused()
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise RelayRefused() from None


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status, headers={"cache-control": "no-store"})


async def _resolve(host: str, port: int) -> Sequence[str]:
    rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(str(row[4][0]) for row in rows)


def _public_address(addresses: Sequence[str]) -> str:
    try:
        parsed = [ipaddress.ip_address(address) for address in addresses]
        if not parsed or any(not address.is_global or address.is_multicast or address.is_reserved
                             or address.is_unspecified or address.is_loopback or address.is_link_local or address.is_private
                             or getattr(address, "is_site_local", False) for address in parsed):
            raise ValueError
        return str(parsed[0])
    except (ValueError, TypeError):
        raise _Failure("UPSTREAM_DNS_DENIED", 502) from None


def _headers(request: Request, relay_auth: str) -> None:
    raw = request.scope["headers"]
    names = [name for name, _ in raw]
    auth = [value for name, value in raw if name == b"authorization"]
    if len(auth) != 1 or not hmac.compare_digest(auth[0], ("Bearer " + relay_auth).encode("ascii")):
        raise _Failure("UNAUTHORIZED", 401)
    if len(names) != len(set(names)) or any(name not in _HEADERS for name in names):
        raise _Failure("INVALID_HEADERS")
    values = dict(raw)
    if (values.get(b"host") not in (b"llm-gateway:8081", b"llm-gateway")
            or values.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json"
            or b"cache-control" in values and values[b"cache-control"] != b"no-cache"):
        raise _Failure("INVALID_HEADERS")
    length = values.get(b"content-length")
    if length is not None:
        if not length.isdigit() or len(length) > 10:
            raise _Failure("INVALID_HEADERS")
        if int(length) > MAX_BODY_BYTES:
            raise _Failure("BODY_TOO_LARGE", 413)


def _secret_free(value: Any, credentials: tuple[str, str]) -> None:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            plain = "".join(ch for ch in unicodedata.normalize("NFKC", item) if unicodedata.category(ch) != "Cf")
            if any(secret in plain for secret in credentials) or scan_secrets(item).found:
                raise _Failure("FORBIDDEN_CONTENT", 502)
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def _provider_result(raw: bytes, credentials: tuple[str, str]) -> tuple[dict[str, Any], int, int]:
    try:
        value = _loads(raw)
        if not isinstance(value, dict) or "error" in value:
            raise RelayRefused()
        _secret_free(value, credentials)
        if any(not isinstance(value.get(key), str) or not _ID.fullmatch(value[key])
               for key in ("id", "model", "system_fingerprint")):
            raise RelayRefused()
        if value.get("object", "chat.completion") != "chat.completion":
            raise RelayRefused()
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise RelayRefused()
        choice = choices[0]
        message = choice.get("message")
        if (type(choice.get("index")) is not int or choice["index"] != 0
                or choice.get("finish_reason") not in ("stop", "length", "content_filter")
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or not isinstance(message.get("content"), str) or message.get("tool_calls") not in (None, [])
                or message.get("function_call") is not None or message.get("reasoning_content") not in (None, "")):
            raise RelayRefused()
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise RelayRefused()
        incoming, outgoing, total = (usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
        if (type(incoming) is not int or not 0 <= incoming <= 2_000_000 or type(outgoing) is not int
                or not 0 <= outgoing <= MAX_OUTPUT_TOKENS or type(total) is not int or total != incoming + outgoing):
            raise RelayRefused()
        return value, incoming, outgoing
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise _Failure("UPSTREAM_FORMAT_INVALID", 502) from None


def create_app(*, ledger: _Ledger, requests: Mapping[str, Mapping[str, Any]], relay_auth: str, provider_key: str,
               resolver: Callable[[str, int], Awaitable[Sequence[str]]] = _resolve,
               client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
               timeout_seconds: float = 30.0, max_response_bytes: int = MAX_RESPONSE_BYTES) -> Starlette:
    """Only CLI supplies live composition; tests may inject isolated HTTP fixtures."""
    if (not isinstance(relay_auth, str) or not _SECRET.fullmatch(relay_auth)
            or not isinstance(provider_key, str) or not _SECRET.fullmatch(provider_key)
            or hmac.compare_digest(relay_auth, provider_key)
            or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30
            or type(max_response_bytes) is not int or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
            or not isinstance(requests, Mapping) or not 1 <= len(requests) <= 16):
        raise RelayRefused()
    frozen: dict[str, tuple[str, int]] = {}
    for ref, binding in requests.items():
        if (not isinstance(ref, str) or not _ID.fullmatch(ref) or not isinstance(binding, Mapping)
                or binding.keys() != {"bodySha256", "payloadBytes"} or not isinstance(binding["bodySha256"], str)
                or not _HASH.fullmatch(binding["bodySha256"]) or binding["bodySha256"] in frozen
                or type(binding["payloadBytes"]) is not int or not 1 <= binding["payloadBytes"] <= MAX_BODY_BYTES):
            raise RelayRefused()
        frozen[binding["bodySha256"]] = (ref, binding["payloadBytes"])
    slots = asyncio.Semaphore(1)
    credentials = (relay_auth, provider_key)

    async def health(request: Request) -> Response:
        if request.scope.get("raw_path") != b"/health" or request.scope.get("query_string"):
            return _error("NOT_FOUND", 404)
        return JSONResponse({"status": "ready"}, headers={"cache-control": "no-store"})

    async def dispatch(request: Request) -> Response:
        if (request.scope.get("raw_path") != UPSTREAM_PATH.encode("ascii")
                or request.scope.get("query_string") or request.method != "POST"):
            return _error("NOT_FOUND", 404)
        try:
            _headers(request, relay_auth)
        except _Failure as error:
            return _error(error.code, error.status)
        if slots.locked():
            return _error("RELAY_BUSY", 429)
        await slots.acquire()
        client: httpx.AsyncClient | None = None
        upstream: httpx.Response | None = None
        reservation: Reservation | None = None
        settlement_attempted = False
        result: Response | None = None
        try:
            async with asyncio.timeout(timeout_seconds):
                raw = bytearray()
                async for part in request.stream():
                    if len(raw) + len(part) > MAX_BODY_BYTES:
                        raise _Failure("BODY_TOO_LARGE", 413)
                    raw.extend(part)
                length = request.headers.get("content-length")
                if length is not None and len(raw) != int(length):
                    raise _Failure("INVALID_BODY_LENGTH")
                try:
                    content = canonical_body(bytes(raw))
                except RelayRefused:
                    raise _Failure("INVALID_REQUEST") from None
                _secret_free(_loads(content), credentials)
                digest = hashlib.sha256(content).hexdigest()
                binding = frozen.get(digest)
                if binding is None or binding[1] != len(content):
                    raise _Failure("REQUEST_NOT_ALLOWLISTED", 403)
                address = _public_address(await resolver(UPSTREAM_HOST, UPSTREAM_PORT))
                host = f"[{address}]" if ":" in address else address
                client = client_factory(verify=True, trust_env=False, follow_redirects=False,
                                        timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
                                        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))
                outgoing = client.build_request("POST", f"https://{host}{UPSTREAM_PATH}", content=content,
                    headers={"host": UPSTREAM_HOST, "authorization": "Bearer " + provider_key,
                             "content-type": "application/json", "accept-encoding": "identity", "accept": "application/json"},
                    extensions={"sni_hostname": UPSTREAM_HOST})
                try:
                    reservation = await ledger.claim(binding[0], digest)
                except Exception:
                    raise _Failure("BUDGET_CLAIM_REFUSED", 503) from None
                if not isinstance(reservation, Reservation) or reservation.scope != binding[0]:
                    raise _Failure("BUDGET_CLAIM_REFUSED", 503)
                upstream = await client.send(outgoing, stream=True)
                if upstream.status_code != 200:
                    raise _Failure("UPSTREAM_REJECTED", 502)
                if (upstream.headers.get("content-encoding", "identity").lower() != "identity"
                        or upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"):
                    raise _Failure("UPSTREAM_FORMAT_INVALID", 502)
                received = bytearray()
                async for part in upstream.aiter_bytes():
                    if len(received) + len(part) > max_response_bytes:
                        raise _Failure("UPSTREAM_TOO_LARGE", 502)
                    received.extend(part)
                value, incoming, outgoing_tokens = _provider_result(bytes(received), credentials)
                # Lost settlement acknowledgement may already mean durable KNOWN.
                # Never follow it with a conflicting UNKNOWN or another dispatch.
                settlement_attempted = True
                try:
                    await ledger.settle_usage(reservation, input_tokens=incoming, output_tokens=outgoing_tokens)
                except Exception:
                    raise _Failure("SETTLEMENT_UNAVAILABLE", 503) from None
                result = JSONResponse(value, headers={"cache-control": "no-store"})
        except _Failure as error:
            result = _error(error.code, error.status)
        except TimeoutError:
            result = _error("UPSTREAM_TIMEOUT", 504)
        except asyncio.CancelledError:
            raise
        except ClientDisconnect:
            result = _error("CLIENT_DISCONNECTED", 400)
        except (httpx.HTTPError, OSError):
            result = _error("UPSTREAM_UNAVAILABLE", 502)
        except Exception:
            result = _error("RELAY_UNAVAILABLE", 503)
        finally:
            try:
                for resource in (upstream, client):
                    if resource is None:
                        continue
                    try:
                        await resource.aclose()
                    except Exception:
                        if result is not None:
                            result = _error("UPSTREAM_CLOSE_FAILED", 503)
            finally:
                try:
                    if reservation is not None and not settlement_attempted:
                        try:
                            await ledger.settle_unknown(reservation)
                        except Exception:
                            if result is not None:
                                result = _error("ACCOUNTING_UNAVAILABLE", 503)
                finally:
                    slots.release()
        assert result is not None
        return result

    return Starlette(routes=[Route("/health", health, methods=["GET"]),
        Route("/{path:path}", dispatch, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "CONNECT", "HEAD"])])


def _mounted_bytes(path: Path, bound: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > bound:
            raise RelayRefused()
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            result = source.read(bound + 1)
        if len(result) > bound:
            raise RelayRefused()
        return result
    finally:
        os.close(descriptor)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise RelayRefused()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--plan-file", required=True, type=Path)
    parser.add_argument("--ledger-file", required=True, type=Path)
    parser.add_argument("--relay-auth-file", required=True, type=Path)
    parser.add_argument("--provider-key-file", required=True, type=Path)
    parser.add_argument("--bind", choices=("0.0.0.0", "127.0.0.1"), default="0.0.0.0")  # noqa: S104 - private container, no published port
    parser.add_argument("--port", type=int, choices=(8081,), default=8081)
    try:
        import uvicorn

        from .ledger import SliceLedger

        args = parser.parse_args(argv)
        plan = _loads(_mounted_bytes(args.plan_file, 1048576))
        if not isinstance(plan, dict) or not isinstance(plan.get("manifestSha256"), str) or not _HASH.fullmatch(plan["manifestSha256"]):
            raise RelayRefused()
        application = create_app(ledger=SliceLedger(args.ledger_file, manifest_sha256=plan["manifestSha256"]), requests=plan["requests"],
            relay_auth=_mounted_bytes(args.relay_auth_file, 512).decode("ascii").strip(),
            provider_key=_mounted_bytes(args.provider_key_file, 512).decode("ascii").strip())
        uvicorn.run(application, host=args.bind, port=args.port, access_log=False, log_config=None, log_level="critical",
                    server_header=False, proxy_headers=False)
        return 0
    except Exception:
        print("SLICE relay configuration or execution refused; details withheld.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
