"""Bounded SLICE relay behavior with synthetic HTTP; no provider/model calls."""
import asyncio
import hashlib
import json
from decimal import Decimal

import httpx
import pytest
from scripts.slice01 import relay

from ai_res.llm.budget import Reservation

AUTH = "synthetic-relay-" + "a" * 32
KEY = "synthetic-provider-" + "b" * 32


def payload(**changes):
    return {"model": "deepseek-flash", "messages": [{"role": "system", "content": "Extract requirements."},
            {"role": "user", "content": "A user may sign in."}], "max_tokens": 2048,
            "thinking": {"type": "disabled"}, "stream": False, **changes}


def wire(value=None):
    return json.dumps(payload() if value is None else value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def provider(**changes):
    return {"id": "synthetic-response", "object": "chat.completion", "model": "deepseek-flash",
            "system_fingerprint": "synthetic-fingerprint", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "synthetic-output"}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38}, **changes}


class Ledger:
    def __init__(self, *, deny=False, settlement_failure=False, unknown_failure=False):
        self.events = []
        self.deny, self.settlement_failure, self.unknown_failure = deny, settlement_failure, unknown_failure

    async def claim(self, ref, digest):
        self.events.append(("claim", ref, digest))
        if self.deny:
            raise RuntimeError("synthetic-private-ledger-error")
        return Reservation(ref, 1, 2002048, Decimal("0.6024576"))

    async def settle_usage(self, reservation, *, input_tokens, output_tokens):
        self.events.append(("known", reservation.scope, input_tokens, output_tokens))
        if self.settlement_failure:
            raise RuntimeError("synthetic-private-settlement-error")

    async def settle_unknown(self, reservation):
        self.events.append(("unknown", reservation.scope))
        if self.unknown_failure:
            raise RuntimeError("synthetic-private-unknown-error")


def app(ledger, handler=None, *, addresses=("8.8.8.8",), requests=None, **kwargs):
    sent, options = [], []

    async def resolve(host, port):
        assert (host, port) == ("api.deepseek.com", 443)
        return addresses

    async def upstream(request):
        sent.append(request)
        ledger.events.append(("send",))
        if handler is None:
            return httpx.Response(200, json=provider())
        result = handler(request)
        return await result if hasattr(result, "__await__") else result

    def factory(**values):
        options.append(values)
        return httpx.AsyncClient(transport=httpx.MockTransport(upstream), **values)

    frozen = requests if requests is not None else {
        "slice-01-request": {"bodySha256": hashlib.sha256(wire()).hexdigest(), "payloadBytes": len(wire())}}
    application = relay.create_app(ledger=ledger, requests=frozen, relay_auth=AUTH, provider_key=KEY,
                                   resolver=resolve, client_factory=factory, **kwargs)
    return application, sent, options


async def call(application, body=None, *, headers=None, path="/chat/completions", method="POST"):
    base = {"authorization": "Bearer " + AUTH, "content-type": "application/json"}
    if headers is not None:
        base.update(headers)
    async with httpx.AsyncClient(base_url="http://llm-gateway:8081", transport=httpx.ASGITransport(app=application)) as client:
        return await client.request(method, path, content=wire() if body is None else body, headers=base)


def test_canonical_body_binds_semantics_without_accepting_unknown_execution_fields():
    value = payload(store=False)
    value.pop("stream")
    assert relay.canonical_body(wire(value)) == wire()


@pytest.mark.parametrize("change", [
    {"stream": True}, {"stream": 0}, {"store": True}, {"store": 0}, {"max_tokens": True},
    {"max_tokens": 256}, {"thinking": {"type": "enabled"}}, {"thinking": {"type": "disabled", "budget": 1}},
    {"tools": []}, {"temperature": 0}, {"model": "deepseek-pro"},
    {"messages": [{"role": "assistant", "content": "synthetic"}]},
])
def test_canonical_body_refuses_unfrozen_execution_options(change):
    with pytest.raises(ValueError):
        relay.canonical_body(wire(payload(**change)))


@pytest.mark.parametrize("raw", [b'{"model":"deepseek-flash","model":"deepseek-flash"}', b'{"x":NaN}',
                                 b'"\xff"', b'"\\ud800"', b"[", b"x" * 32769])
def test_canonical_body_rejects_malformed_or_oversized_input(raw):
    with pytest.raises(ValueError):
        relay.canonical_body(raw)


async def test_exact_once_claim_and_settlement_precede_success_with_pinned_public_tls_destination():
    ledger = Ledger()
    application, sent, options = app(ledger)
    result = await call(application)
    assert result.status_code == 200 and result.json() == provider()
    assert [event[0] for event in ledger.events] == ["claim", "send", "known"]
    request = sent[0]
    assert str(request.url) == "https://8.8.8.8/chat/completions" and request.content == wire()
    assert request.extensions["sni_hostname"] == "api.deepseek.com"
    assert request.headers["host"] == "api.deepseek.com" and request.headers["authorization"] == "Bearer " + KEY
    assert request.headers["accept-encoding"] == "identity" and AUTH not in str(request.headers)
    assert options[0]["verify"] is True and options[0]["trust_env"] is False and options[0]["follow_redirects"] is False
    assert "set-cookie" not in result.headers and result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers,path,method", [
    ({"authorization": "Bearer wrong"}, "/chat/completions", "POST"),
    ({"host": "elsewhere"}, "/chat/completions", "POST"),
    ({"x-unknown": "synthetic"}, "/chat/completions", "POST"),
    ({}, "/chat/completions?extra=1", "POST"), ({}, "/other", "POST"), ({}, "/chat/completions", "GET"),
])
async def test_request_boundary_refuses_before_claim_or_provider(headers, path, method):
    ledger = Ledger()
    application, sent, _ = app(ledger)
    result = await call(application, headers=headers, path=path, method=method)
    assert result.status_code >= 400 and not ledger.events and not sent


async def test_unlisted_or_wrong_length_digest_never_claims():
    for frozen in ({"other": {"bodySha256": "0" * 64, "payloadBytes": len(wire())}},
                   {"other": {"bodySha256": hashlib.sha256(wire()).hexdigest(), "payloadBytes": len(wire()) + 1}}):
        ledger = Ledger()
        application, sent, _ = app(ledger, requests=frozen)
        result = await call(application)
        assert result.status_code == 403 and not ledger.events and not sent


@pytest.mark.parametrize("addresses", [(), ("127.0.0.1",), ("8.8.8.8", "169.254.169.254"), ("bad-address",), ("::1",),
                                       ("ff0e::1",), ("fec0::1",), ("::ffff:127.0.0.1",)])
async def test_dns_refuses_nonpublic_or_mixed_answers_before_claim(addresses):
    ledger = Ledger()
    application, sent, _ = app(ledger, addresses=addresses)
    assert (await call(application)).status_code == 502
    assert not ledger.events and not sent


async def test_ledger_deny_never_dispatches_or_exports_internal_error():
    ledger = Ledger(deny=True)
    application, sent, _ = app(ledger)
    result = await call(application)
    assert result.status_code == 503 and not sent and "private" not in result.text


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_provider_errors_are_unknown_once_without_redirect_retry_or_raw_body(status):
    ledger = Ledger()
    application, sent, _ = app(ledger, lambda request: httpx.Response(status, text=KEY, headers={"location": "https://elsewhere.test"}))
    result = await call(application)
    assert result.status_code >= 400 and len(sent) == 1 and KEY not in result.text
    assert [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


@pytest.mark.parametrize("value", [provider(usage=None), provider(usage={"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2}),
                                  provider(usage={"prompt_tokens": 1, "completion_tokens": 2049, "total_tokens": 2050}),
                                  provider(usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3}),
                                  provider(choices=[{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "tool_calls": []}}]),
                                  provider(extra=KEY)])
async def test_invalid_usage_tools_or_secret_reflection_fail_closed_and_hold_full_reserve(value):
    ledger = Ledger()
    application, _, _ = app(ledger, lambda request: httpx.Response(200, json=value))
    result = await call(application)
    assert result.status_code == 502 and KEY not in result.text and "synthetic-output" not in result.text
    assert [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


async def test_settlement_failure_withholds_success_without_conflicting_unknown_settlement():
    ledger = Ledger(settlement_failure=True)
    application, _, _ = app(ledger)
    result = await call(application)
    assert result.status_code == 503 and "synthetic-output" not in result.text and "private" not in result.text
    assert [event[0] for event in ledger.events] == ["claim", "send", "known"]


async def test_total_deadline_holds_unknown_and_never_retries():
    async def wait(request):
        await asyncio.Event().wait()

    ledger = Ledger()
    application, sent, _ = app(ledger, wait, timeout_seconds=0.01)
    result = await call(application)
    assert result.status_code == 504 and len(sent) == 1
    assert [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


async def test_busy_second_request_cannot_claim_or_dispatch_and_cancellation_is_unknown():
    entered = asyncio.Event()

    async def wait(request):
        entered.set()
        await asyncio.Event().wait()

    ledger = Ledger()
    application, sent, _ = app(ledger, wait)
    first = asyncio.create_task(call(application))
    await entered.wait()
    assert (await call(application)).status_code == 429
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert len(sent) == 1 and [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


async def test_response_size_is_bounded_and_unknown_failure_never_exports_internal_error():
    ledger = Ledger(unknown_failure=True)
    application, _, _ = app(ledger, lambda request: httpx.Response(200, content=b"x" * 257,
                                                                 headers={"content-type": "application/json"}), max_response_bytes=256)
    result = await call(application)
    assert result.status_code >= 400 and "private" not in result.text
    assert [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


async def test_public_ipv6_destination_preserves_brackets_host_and_sni():
    application, sent, _ = app(Ledger(), addresses=("2001:4860:4860::8888",))
    assert (await call(application)).status_code == 200
    assert str(sent[0].url) == "https://[2001:4860:4860::8888]/chat/completions"
    assert sent[0].headers["host"] == "api.deepseek.com" and sent[0].extensions["sni_hostname"] == "api.deepseek.com"


@pytest.mark.parametrize("raw", [b'{"usage":{},"usage":{}}', b'"\xff"', b'{"x":Infinity}', b'"\\ud800"'])
async def test_malformed_provider_json_is_unknown_without_payload_disclosure(raw):
    ledger = Ledger()
    application, _, _ = app(ledger, lambda request: httpx.Response(200, content=raw, headers={"content-type": "application/json"}))
    result = await call(application)
    assert result.status_code == 502 and [event[0] for event in ledger.events] == ["claim", "send", "unknown"]


async def test_duplicate_authorization_and_incorrect_content_length_cannot_claim():
    ledger = Ledger()
    application, sent, _ = app(ledger)
    async with httpx.AsyncClient(base_url="http://llm-gateway:8081", transport=httpx.ASGITransport(app=application)) as client:
        result = await client.post("/chat/completions", content=wire(), headers=[
            ("authorization", "Bearer " + AUTH), ("authorization", "Bearer " + AUTH), ("content-type", "application/json")])
    assert result.status_code == 401
    assert (await call(application, headers={"content-length": "1"})).status_code == 400
    assert not ledger.events and not sent


def test_frozen_map_and_credentials_are_rejected_when_ambiguous():
    entry = {"bodySha256": hashlib.sha256(wire()).hexdigest(), "payloadBytes": len(wire())}
    with pytest.raises(ValueError):
        app(Ledger(), requests={"one": entry, "two": dict(entry)})
    with pytest.raises(ValueError):
        relay.create_app(ledger=Ledger(), requests={"one": entry}, relay_auth=AUTH, provider_key=AUTH)


async def test_caller_cannot_mutate_an_installed_frozen_request_map():
    entry = {"bodySha256": hashlib.sha256(wire()).hexdigest(), "payloadBytes": len(wire())}
    ledger = Ledger()
    application, _, _ = app(ledger, requests={"one": entry})
    changed = wire(payload(messages=[{"role": "user", "content": "A different source."}]))
    entry["bodySha256"], entry["payloadBytes"] = hashlib.sha256(changed).hexdigest(), len(changed)
    assert (await call(application, changed)).status_code == 403 and not ledger.events
    assert (await call(application)).status_code == 200


@pytest.mark.parametrize("unsafe", ["symlink", "shared", "large"])
def test_mounted_files_are_bounded_regular_and_not_shared_writable(tmp_path, unsafe):
    path = tmp_path / "input"
    path.write_bytes(b"synthetic-fixture")
    path.chmod(0o600)
    if unsafe == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    elif unsafe == "shared":
        path.chmod(0o620)
    else:
        path.write_bytes(b"x" * 33)
    with pytest.raises((OSError, ValueError)):
        relay._mounted_bytes(path, 32)


def test_cli_composes_actual_existing_ledger_with_keyword_only_manifest_without_inference(tmp_path, monkeypatch):
    import uvicorn
    from scripts.slice01.ledger import SliceLedger

    tmp_path.chmod(0o700)
    manifest = "a" * 64
    frozen = {"slice-cli": {"bodySha256": hashlib.sha256(wire()).hexdigest(), "payloadBytes": len(wire())}}
    journal = tmp_path / "ledger.jsonl"
    SliceLedger.initialize(journal, manifest_sha256=manifest, requests=frozen)
    before = journal.read_bytes()
    plan, auth, provider_key = (tmp_path / name for name in ("plan.json", "relay-auth", "provider-key"))
    for path, raw in ((plan, json.dumps({"manifestSha256": manifest, "requests": frozen})), (auth, AUTH), (provider_key, KEY)):
        path.write_text(raw)
        path.chmod(0o600)
    served = []
    monkeypatch.setattr(uvicorn, "run", lambda application, **options: served.append((application, options)))
    assert relay.main(["--plan-file", str(plan), "--ledger-file", str(journal), "--relay-auth-file", str(auth),
                       "--provider-key-file", str(provider_key), "--bind", "127.0.0.1", "--port", "8081"]) == 0
    assert len(served) == 1 and served[0][1]["access_log"] is False and served[0][1]["proxy_headers"] is False
    assert journal.read_bytes() == before
