"""S16 relay behavior over ASGI + a controlled transport. No provider requests or model approval."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "infra" / "llm_poc" / "relay.py"
SPEC = importlib.util.spec_from_file_location("s16_egress_relay", SCRIPT)
assert SPEC and SPEC.loader
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)

AUTH = "synthetic-relay-credential-" + "a" * 40
PROVIDER = "synthetic-provider-credential-" + "b" * 40
PUBLIC = "93.184.216.34"


def body(**changes):
    return {"model": "deepseek-flash", "messages": [{"role": "user", "content": "synthetic question"}], "max_tokens": 32, **changes}


class Rig:
    def __init__(self, *, ips=(PUBLIC,), handler=None, enabled=True, **changes):
        self.requests = []
        self.client_options = []
        self.resolved = []
        self.handler = handler

        async def resolver(host, port):
            self.resolved.append((host, port))
            return ips

        async def handle(request):
            self.requests.append(request)
            if self.handler:
                return await self.handler(request)
            return httpx.Response(200, json={"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}})

        def client_factory(**options):
            self.client_options.append(options)
            return httpx.AsyncClient(transport=httpx.MockTransport(handle), **options)

        self.config = relay.RelayConfig(auth_token=AUTH, provider_key=PROVIDER, allow_provider_calls=enabled, **changes)
        self.app = relay.create_app(self.config, resolver=resolver, client_factory=client_factory)

    async def send(self, *, method="POST", path="/chat/completions", payload=None, headers=None, content=None):
        h = [("authorization", "Bearer " + AUTH), *(headers or [])]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app), base_url="http://relay") as client:
            if content is not None:
                return await client.request(method, path, content=content, headers=h)
            return await client.request(method, path, json=payload if payload is not None else body(), headers=h)


async def test_disabled_default_and_health_never_resolve_or_call_provider():
    r = Rig(enabled=False)
    response = await r.send()
    assert response.status_code == 503
    health = await r.send(method="GET", path="/health")
    assert health.status_code == 200 and health.json() == {"status": "disabled"}
    assert r.requests == r.resolved == []
    assert not relay.RelayConfig(auth_token=AUTH, provider_key=PROVIDER).allow_provider_calls


async def test_invalid_unicode_request_is_rejected_before_dns_or_provider():
    r = Rig()
    reply = await r.send(content=json.dumps(body(messages=[{"role": "user", "content": chr(0xD800)}])).encode(),
                         headers=[("content-type", "application/json")])
    assert reply.status_code == 400
    assert r.requests == r.resolved == []


async def test_invalid_unicode_upstream_json_has_a_sanitized_typed_refusal():
    async def handler(_):
        return httpx.Response(200, content=json.dumps({"output": chr(0xD800)}).encode(), headers={"content-type": "application/json"})

    r = Rig(handler=handler)
    reply = await r.send()
    assert reply.status_code == 502
    assert reply.json() == {"error": {"code": "UPSTREAM_FORMAT_INVALID"}}


async def test_fixed_upstream_verified_tls_numeric_address_and_replaced_credentials():
    r = Rig()
    response = await r.send(headers=[("user-agent", "synthetic-caller")])
    assert response.status_code == 200
    assert r.resolved == [("api.deepseek.com", 443)]
    assert len(r.requests) == 1
    request = r.requests[0]
    assert str(request.url) == f"https://{PUBLIC}/chat/completions"
    assert request.headers["host"] == "api.deepseek.com"
    assert request.extensions["sni_hostname"] == "api.deepseek.com"
    assert request.headers["authorization"] == "Bearer " + PROVIDER
    assert AUTH not in str(request.headers) and "synthetic-caller" not in str(request.headers)
    assert json.loads(request.content)["thinking"] == {"type": "disabled"}
    assert r.client_options[0]["verify"] is True
    assert r.client_options[0]["trust_env"] is False
    assert r.client_options[0]["follow_redirects"] is False


@pytest.mark.parametrize("authorization", [[], [("authorization", "Bearer wrong")], [("authorization", "Bearer " + AUTH)] * 2])
async def test_missing_wrong_or_duplicate_auth_refused_before_dns(authorization):
    r = Rig()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(r.app), base_url="http://relay") as client:
        response = await client.post("/chat/completions", json=body(), headers=authorization)
    assert response.status_code == 401
    assert not r.resolved and not r.requests


@pytest.mark.parametrize("method,path", [("CONNECT", "/chat/completions"), ("GET", "/chat/completions"),
    ("POST", "/responses"), ("POST", "/chat/completions?url=https://example.com"), ("POST", "/chat/%63ompletions"),
    ("POST", "/chat/completions/"), ("POST", "/v1/chat/completions")])
async def test_only_exact_method_and_raw_path_allowed(method, path):
    r = Rig()
    response = await r.send(method=method, path=path)
    assert response.status_code in (400, 404, 405)
    assert not r.resolved and not r.requests


@pytest.mark.parametrize("raw_path", [b"http://evil.example/chat/completions", b"//evil.example/chat/completions"])
async def test_absolute_raw_target_not_normalized_into_allowed_route(raw_path):
    # HTTPX normalizes URL syntax before ASGI; attack the raw ASGI target directly.
    r = Rig()
    outgoing = []
    async def receive():
        return {"type": "http.request", "body": json.dumps(body()).encode(), "more_body": False}
    async def send(message):
        outgoing.append(message)
    await r.app({"type": "http", "asgi": {"version": "3.0"}, "method": "POST", "scheme": "http",
                 "path": "/chat/completions", "raw_path": raw_path, "query_string": b"", "root_path": "",
                 "headers": [(b"host", b"relay"), (b"authorization", ("Bearer " + AUTH).encode()),
                             (b"content-type", b"application/json")]}, receive, send)
    assert outgoing[0]["status"] == 404 and not r.resolved and not r.requests


@pytest.mark.parametrize("headers", [[("host", "evil.example")], [("host", "relay"), ("host", "relay")],
    [("content-length", "1"), ("content-length", "2")], [("transfer-encoding", "chunked")],
    [("content-encoding", "gzip")], [("x-bf-eh-host", "evil.example")], [("x-forwarded-host", "evil.example")]])
async def test_header_smuggling_and_override_refused(headers):
    r = Rig()
    response = await r.send(headers=headers)
    assert response.status_code == 400
    assert not r.resolved and not r.requests


@pytest.mark.parametrize("changes", [{"model": "deepseek-v4-pro"}, {"model": "other/provider"}, {"max_tokens": 1025},
    {"max_tokens": True}, {"max_tokens": 0}, {"max_tokens": None}, {"thinking": {"type": "enabled"}},
    {"tools": [{"type": "deepseek_web_search"}]}, {"tools": [{"type": "deepseek_read_url"}]},
    {"extra_headers": {"Host": "evil.example"}}, {"messages": [{"role": "user", "content": [{"type": "image_url"}]}]},
    {"messages": [{"role": "user", "content": "x", "name": "override"}]}, {"messages": []}, {"stream": "true"},
    {"stream_options": {"unknown": True}}, {"temperature": float("inf")}, {"temperature": 10 ** 500},
    {"response_format": {"type": "json_schema"}}])
async def test_payload_can_only_express_bounded_text_flash_inference(changes):
    r = Rig()
    # stdlib deliberately serializes Infinity, which must be rejected as a non-JSON constant.
    raw = json.dumps(body(**changes)).encode()
    response = await r.send(content=raw, headers=[("content-type", "application/json")])
    assert response.status_code == 400
    assert not r.resolved and not r.requests


async def test_missing_cap_duplicate_json_keys_and_oversized_body_refused():
    r = Rig(max_body_bytes=1024)
    payload = body()
    payload.pop("max_tokens")
    assert (await r.send(payload=payload)).status_code == 400
    duplicate = b'{"model":"deepseek-flash","model":"deepseek-v4-pro"}'
    assert (await r.send(content=duplicate, headers=[("content-type", "application/json")])).status_code == 400
    assert (await r.send(payload=body(messages=[{"role": "user", "content": "x" * 1500}]))).status_code == 413
    assert not r.resolved and not r.requests


async def test_function_tools_and_json_output_allowed_without_execution():
    r = Rig()
    tools = [{"type": "function", "function": {"name": "lookup", "description": "synthetic", "parameters": {"type": "object", "properties": {}}}}]
    response = await r.send(payload=body(tools=tools, tool_choice="required", response_format={"type": "json_object"}))
    assert response.status_code == 200
    assert json.loads(r.requests[0].content)["tools"] == tools


@pytest.mark.parametrize("ips", [(), ("127.0.0.1",), ("10.0.0.1",), ("169.254.169.254",), ("::1",), ("fd00::1",),
    ("192.0.2.1",), (PUBLIC, "127.0.0.1"), ("not-an-ip",)])
async def test_dns_empty_private_reserved_or_mixed_answers_fail_closed(ips):
    r = Rig(ips=ips)
    response = await r.send()
    assert response.status_code == 502
    assert not r.requests


@pytest.mark.parametrize("status", [301, 307, 400, 401, 429, 500])
async def test_redirect_and_upstream_error_content_headers_are_not_exposed(status, caplog):
    async def handle(request):
        return httpx.Response(status, headers={"location": "http://127.0.0.1/private", "x-secret": PROVIDER}, content=PROVIDER + AUTH)
    r = Rig(handler=handle)
    response = await r.send()
    assert response.status_code == (429 if status == 429 else 502)
    assert PROVIDER not in response.text and AUTH not in response.text
    assert "location" not in response.headers and "x-secret" not in response.headers
    assert PROVIDER not in caplog.text and AUTH not in caplog.text
    assert len(r.requests) == 1


async def test_network_exception_sanitized_and_response_cap_enforced(caplog):
    async def fail(request):
        raise httpx.ConnectError(PROVIDER + AUTH)
    r = Rig(handler=fail)
    response = await r.send()
    assert response.status_code == 502
    assert PROVIDER not in caplog.text + response.text and AUTH not in caplog.text + response.text
    async def large(request):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"x" * 200)
    limited = Rig(handler=large, max_response_bytes=100)
    assert (await limited.send()).status_code == 502


class ControlledStream(httpx.AsyncByteStream):
    def __init__(self, *, wait=False, fail=False):
        self.wait = wait
        self.fail = fail
        self.closed = False
        self.started = asyncio.Event()

    async def __aiter__(self):
        self.started.set()
        if self.wait:
            await asyncio.Event().wait()
        yield b'data: {"choices":[]}\n\n'
        if self.fail:
            raise httpx.ReadError(PROVIDER + AUTH)
        yield b"data: [DONE]\n\n"

    async def aclose(self):
        self.closed = True


async def test_stream_copied_without_buffering_and_closed():
    stream = ControlledStream()
    async def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
    r = Rig(handler=handle)
    response = await r.send(payload=body(stream=True))
    assert response.status_code == 200 and "[DONE]" in response.text
    assert stream.closed
    assert json.loads(r.requests[0].content)["stream_options"] == {"include_usage": True}


async def test_midstream_failure_explicit_sanitized_and_closed(caplog):
    stream = ControlledStream(fail=True)
    async def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
    r = Rig(handler=handle)
    response = await r.send(payload=body(stream=True))
    assert "UPSTREAM_STREAM_FAILED" in response.text and "[DONE]" not in response.text
    assert PROVIDER not in response.text + caplog.text and AUTH not in response.text + caplog.text
    assert stream.closed


async def test_stream_total_deadline_and_concurrency_slot_released():
    stream = ControlledStream(wait=True)
    async def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
    r = Rig(handler=handle, total_timeout_seconds=0.05)
    first = asyncio.create_task(r.send(payload=body(stream=True)))
    await asyncio.wait_for(stream.started.wait(), 1)
    assert (await r.send()).status_code == 429
    response = await asyncio.wait_for(first, 1)
    assert "UPSTREAM_STREAM_FAILED" in response.text and stream.closed
    r.handler = None
    assert (await r.send()).status_code == 200


async def test_cancellation_closes_upstream_and_releases_concurrency():
    stream = ControlledStream(wait=True)
    async def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)
    r = Rig(handler=handle)
    first = asyncio.create_task(r.send(payload=body(stream=True)))
    await asyncio.wait_for(stream.started.wait(), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert stream.closed
    r.handler = None
    assert (await r.send()).status_code == 200


def test_secret_config_not_printed_and_secret_files_require_safe_mode(tmp_path):
    config = relay.RelayConfig(auth_token=AUTH, provider_key=PROVIDER)
    assert AUTH not in repr(config) and PROVIDER not in repr(config)
    secret = tmp_path / "synthetic"
    secret.write_text(AUTH)
    secret.chmod(0o600)
    assert relay.read_secret_file(secret) == AUTH
    secret.chmod(0o666)
    with pytest.raises(ValueError):
        relay.read_secret_file(secret)
    secret.chmod(0o600)
    secret.write_text("short")
    with pytest.raises(ValueError):
        relay.read_secret_file(secret)
    alias = tmp_path / "alias"
    alias.symlink_to(secret)
    with pytest.raises(ValueError):
        relay.read_secret_file(alias)


def test_disabled_config_needs_no_provider_key_and_live_requires_one():
    config = relay.RelayConfig(auth_token=AUTH)
    assert config.provider_key is None
    with pytest.raises(ValueError):
        relay.RelayConfig(auth_token=AUTH, allow_provider_calls=True)
