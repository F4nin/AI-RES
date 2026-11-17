"""Wire behavior against an injected HTTP transport; no provider calls or real pin evidence."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from ai_res.llm import errors as E
from ai_res.llm.adapters.bifrost import BifrostSettings, BifrostTransport, ImmutableModelEvidence
from ai_res.llm.registry import Egress, ModelProfile, ProfileStatus, RetryClass
from ai_res.llm.transport import TransportCall, TransportEmbeddingCall
from ai_res.llm.types import Capability, FinishReason, Message, Role, StreamEnd, TextDelta, ToolCallChunk

SNAPSHOT = "synthetic-snapshot-20260101"  # a fixture, NOT a supported DeepSeek model
PROFILE = ModelProfile(id=UUID(int=100), profile_key="fixture", profile_version=1, provider="deepseek", provider_model_id=SNAPSHOT,
                       pinned_model_version=SNAPSHOT, capabilities=frozenset({Capability.CHAT, Capability.STREAMING, Capability.TOOL_CALLING}),
                       context_window_tokens=4096, max_output_tokens=1024, data_classifications=frozenset({"PUBLIC"}),
                       allowed_regions=frozenset({"test"}), egress=Egress.EXTERNAL, timeout_seconds=5, retry_class=RetryClass.NONE,
                       status=ProfileStatus.APPROVED, approved_at=datetime(2026, 1, 1, tzinfo=UTC))
EVIDENCE = ImmutableModelEvidence(provider="deepseek", request_model_id=SNAPSHOT, response_model_id=SNAPSHOT,
                                  pinned_model_version=SNAPSHOT, evidence_ref="unit-fixture-only", expected_fingerprint="fixture-backend")
CALL = TransportCall(request_id="fixture-1", profile=PROFILE, messages=(Message(Role.USER, "hello"),), max_output_tokens=64, timeout_seconds=2)
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
TOOLS = ({"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {"q": {"type": "string"}},
                                                                                  "required": ["q"], "additionalProperties": False}}},)


def response(**changes):
    base = {"id": "chat-fixture-1", "model": SNAPSHOT, "system_fingerprint": "fixture-backend", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "answer"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            "extra_fields": {"routing_info": {"provider": "deepseek", "model": SNAPSHOT, "requested_model": SNAPSHOT}}}
    return {**base, **changes}


def event(delta=None, finish=None, usage=None, **changes):
    return response(object="chat.completion.chunk", usage=usage,
                    choices=[{"index": 0, "delta": delta or {}, "finish_reason": finish}], **changes)


def sse(*events, done=True):
    text = "".join("data: " + json.dumps(item) + "\r\n\r\n" for item in events)
    return (text + ("data: [DONE]\r\n\r\n" if done else "")).encode()


def transport(handler, *, evidence=(EVIDENCE,), settings=None, key="unit-virtual-key"):
    return BifrostTransport(settings or BifrostSettings(), virtual_key=key, immutable_evidence=evidence,
                            http_transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("model", [SNAPSHOT, "deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro"])
async def test_missing_pin_evidence_refuses_before_http(model):
    sent = []
    async with transport(lambda r: sent.append(r), evidence=()) as adapter:
        with pytest.raises(E.GatewayUnconfigured):
            await adapter.complete(replace(CALL, profile=replace(PROFILE, provider_model_id=model)))
    assert sent == []


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp", "deepseek-v4-pro"])
async def test_binding_and_version_label_do_not_make_a_known_rolling_alias_immutable(model):
    sent = []
    binding = replace(EVIDENCE, request_model_id=model, response_model_id=model)
    async with transport(lambda r: sent.append(r), evidence=(binding,)) as adapter:
        with pytest.raises(E.GatewayUnconfigured):
            await adapter.complete(replace(CALL, profile=replace(PROFILE, provider_model_id=model)))
    assert sent == []


@pytest.mark.parametrize("settings", ["https://example.com/v1/chat/completions", "http://127.0.0.1/v1/chat/completions",
                                     "http://bifrost:8080/providers", "http://u:p@bifrost:8080/v1/chat/completions",
                                     "http://bifrost:8080/v1/chat/completions?model=x", "http://bifrost:8080/v1/chat/completions#x"])
def test_endpoint_configuration_rejects_external_ip_admin_and_credential_urls(settings):
    with pytest.raises(ValueError):
        BifrostSettings(inference_url=settings)


async def test_request_wire_auth_no_fallback_and_parsed_result():
    sent = []

    def handle(r):
        sent.append(r)
        return httpx.Response(200, json=response())

    async with transport(handle) as adapter:
        result = await adapter.complete(CALL)
    request = sent[0]
    assert request.url == "http://bifrost-poc:8080/v1/chat/completions"
    assert request.headers["x-bf-vk"] == "unit-virtual-key" and "authorization" not in request.headers
    body = json.loads(request.content)
    assert body["model"] == "deepseek/" + SNAPSHOT
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["fallbacks"] == [] and body["max_completion_tokens"] == 64
    assert result.output == "answer" and result.usage.total == 10 and result.provider_request_ref == "chat-fixture-1"


async def test_candidate_and_missing_gateway_credential_do_not_make_http_calls():
    sent = []
    async with transport(lambda r: sent.append(r)) as adapter:
        with pytest.raises(E.ModelProfileNotApproved):
            await adapter.complete(replace(CALL, profile=replace(PROFILE, status=ProfileStatus.CANDIDATE, approved_at=None)))
    async with transport(lambda r: sent.append(r), key=None) as adapter:
        with pytest.raises(E.GatewayUnconfigured):
            await adapter.complete(CALL)
    assert sent == []


@pytest.mark.parametrize("changes", [
    {"model": "other"}, {"model": None}, {"system_fingerprint": "changed"}, {"system_fingerprint": None},
    {"extra_fields": {}}, {"extra_fields": {"routing_info": {"provider": "other", "model": SNAPSHOT}}},
    {"extra_fields": {"routing_info": {"provider": "deepseek", "model": "other"}}},
    {"extra_fields": {"routing_info": {"provider": "deepseek", "model": SNAPSHOT, "is_fallback": True}}},
    {"extra_fields": {"routing_info": {"provider": "deepseek", "model": SNAPSHOT, "server_side_fallback_model": SNAPSHOT}}},
    {"extra_fields": {"routing_info": {"provider": "deepseek", "model": SNAPSHOT, "resolved_key_alias": {"model_id": SNAPSHOT}}}},
    {"usage": None}, {"usage": {"prompt_tokens": True, "completion_tokens": 3}},
    {"usage": {"prompt_tokens": -1, "completion_tokens": 3}}, {"usage": {"prompt_tokens": 7, "completion_tokens": 1000}},
    {"usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 12}},
    {"choices": []}, {"choices": [{"index": 0, "finish_reason": "unexpected", "message": {"content": "x"}}]},
])
async def test_unknown_identity_usage_and_finish_are_refused_without_output(changes):
    async with transport(lambda r: httpx.Response(200, json=response(**changes))) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await adapter.complete(CALL)


async def test_structured_output_and_tool_arguments_are_parsed_and_validated():
    async with transport(lambda r: httpx.Response(200, json=response(
            choices=[{"index": 0, "finish_reason": "stop", "message": {"content": '{"answer":"ok"}'}}]))) as adapter:
        result = await adapter.complete(replace(CALL, response_schema=SCHEMA))
        assert result.output == {"answer": "ok"}
    tools = [{"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"hello"}'}}]
    async with transport(lambda r: httpx.Response(200, json=response(
            choices=[{"index": 0, "finish_reason": "tool_calls", "message": {"content": None, "tool_calls": tools}}]))) as adapter:
        result = await adapter.complete(replace(CALL, tool_definitions=TOOLS))
        assert result.tool_calls[0].arguments == {"q": "hello"} and result.finish_reason is FinishReason.TOOL_CALLS


@pytest.mark.parametrize("content", ['{"answer":4}', '[]', 'not JSON'])
async def test_invalid_structured_output_is_refused(content):
    async with transport(lambda r: httpx.Response(200, json=response(
            choices=[{"index": 0, "finish_reason": "stop", "message": {"content": content}}]))) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await adapter.complete(replace(CALL, response_schema=SCHEMA))


@pytest.mark.parametrize("name,arguments", [("unapproved", '{"q":"x"}'), ("lookup", '{"q":1}'), ("lookup", '[]'), ("lookup", '{')])
async def test_unapproved_or_invalid_tools_are_refused(name, arguments):
    tc = [{"id": "call-1", "type": "function", "function": {"name": name, "arguments": arguments}}]
    async with transport(lambda r: httpx.Response(200, json=response(
            choices=[{"index": 0, "finish_reason": "tool_calls", "message": {"content": None, "tool_calls": tc}}]))) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await adapter.complete(replace(CALL, tool_definitions=TOOLS))


@pytest.mark.parametrize("status,error", [(302, E.ProviderRejected), (400, E.ProviderRejected), (401, E.ProviderRejected),
                                         (403, E.ProviderRejected), (429, E.ProviderRateLimited), (500, E.ProviderUnavailable),
                                         (503, E.ProviderUnavailable), (504, E.ProviderTimeout)])
async def test_http_error_mapping_never_echoes_provider_body_and_never_redirects(status, error):
    calls = []

    def handle(r):
        calls.append(r)
        return httpx.Response(status, headers={"Location": "https://example.com", "Retry-After": "3"},
                              json={"error": {"message": "private provider payload"}})

    async with transport(handle) as adapter:
        with pytest.raises(error) as exc:
            await adapter.complete(CALL)
    assert "private provider payload" not in str(exc.value) and exc.value.__cause__ is None
    assert exc.value.possibly_billed is True
    assert len(calls) == 1
    if status == 429:
        assert exc.value.retry_after_seconds == 3


@pytest.mark.parametrize("exception,error", [(httpx.ConnectError, E.ProviderUnavailable), (httpx.ReadTimeout, E.ProviderTimeout)])
async def test_transport_errors_are_sanitized(exception, error):
    def handle(r):
        raise exception("private URL or credentials", request=r)

    async with transport(handle) as adapter:
        with pytest.raises(error) as exc:
            await adapter.complete(CALL)
    assert "private URL" not in str(exc.value) and exc.value.__cause__ is None
    assert exc.value.possibly_billed is True


async def test_body_and_sse_event_limits_are_enforced():
    config = BifrostSettings(max_response_bytes=128, max_event_bytes=128)
    async with transport(lambda r: httpx.Response(200, content=b"x" * 129), settings=config) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await adapter.complete(CALL)
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"data: " + b"x" * 129),
                         settings=config) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await anext(adapter.stream(CALL))


async def test_sse_is_incremental_checks_identity_before_every_delta_and_requires_finish_usage():
    async def handle(r):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            event({"content": "one"}), event({"content": "two"}), event(finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3})))

    async with transport(handle) as adapter:
        chunks = [c async for c in adapter.stream(CALL)]
    assert chunks[:2] == [TextDelta("one"), TextDelta("two")]
    assert isinstance(chunks[2], StreamEnd) and chunks[2].usage.total == 10


@pytest.mark.parametrize("bad", [event({"content": "bad"}, model="other"), event({"content": "bad"}, extra_fields={})])
async def test_sse_identity_drift_blocks_that_chunk(bad):
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(event({"content": "ok"}), bad))) as adapter:
        stream = adapter.stream(CALL)
        assert await anext(stream) == TextDelta("ok")
        with pytest.raises(E.InvalidProviderOutput):
            await anext(stream)


@pytest.mark.parametrize("body", [sse(event({"content": "one"})), sse(event(finish="stop")),
                                sse(event(finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3}), done=False)])
async def test_sse_missing_end_finish_or_usage_is_not_success(body):
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            _ = [c async for c in adapter.stream(CALL)]


async def test_sse_tools_are_not_exposed_until_complete_and_validated():
    a = {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":'}}]}
    b = {"tool_calls": [{"index": 0, "function": {"arguments": '"hello"}'}}]}
    body = sse(event(a), event(b), event(finish="tool_calls", usage={"prompt_tokens": 7, "completion_tokens": 3}))
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)) as adapter:
        chunks = [c async for c in adapter.stream(replace(CALL, tool_definitions=TOOLS))]
    assert len(chunks) == 2 and isinstance(chunks[0], ToolCallChunk)
    assert chunks[0].call.arguments == {"q": "hello"} and isinstance(chunks[1], StreamEnd)


async def test_stream_in_band_error_is_typed_and_body_not_echoed():
    body = sse({"is_bifrost_error": True, "status_code": 429, "error": {"message": "private"}, "extra_fields": {"retry_after_ms": 2500}})
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)) as adapter:
        with pytest.raises(E.ProviderRateLimited) as exc:
            await anext(adapter.stream(CALL))
    assert exc.value.retry_after_seconds == 2.5 and "private" not in str(exc.value)
    assert exc.value.possibly_billed is True


class SlowStream(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        yield sse(event({"content": "first"}), done=False)
        self.waiting.set()
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


async def test_cancellation_and_consumer_close_close_http_stream():
    for cancel in (False, True):
        wire = SlowStream()
        async with transport(lambda r, wire=wire: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=wire)) as adapter:
            stream = adapter.stream(CALL)
            assert await anext(stream) == TextDelta("first")
            if cancel:
                task = asyncio.create_task(anext(stream))
                await wire.waiting.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await stream.aclose()
        assert wire.closed


async def test_embeddings_are_explicitly_unsupported_without_http():
    sent = []
    async with transport(lambda r: sent.append(r)) as adapter:
        with pytest.raises(E.CapabilityNotSupported):
            await adapter.embed(TransportEmbeddingCall(request_id="embed-1", profile=PROFILE, inputs=("text",), timeout_seconds=1))
    assert sent == []


@pytest.mark.parametrize("remote", ["https://example.com/schema", "file:///etc/passwd"])
async def test_schema_references_cannot_trigger_network_or_filesystem_retrieval(remote):
    sent = []
    async with transport(lambda r: sent.append(r)) as adapter:
        with pytest.raises(E.InvalidRequest):
            await adapter.complete(replace(CALL, response_schema={"$ref": remote}))
    assert sent == []


async def test_duplicate_json_keys_and_nonfinite_numbers_are_refused():
    duplicate = json.dumps(response()).replace('"model": "' + SNAPSHOT + '"', '"model":"other","model":"' + SNAPSHOT + '"', 1)
    for body in (duplicate, json.dumps(response()).replace('"prompt_tokens": 7', '"prompt_tokens": NaN')):
        async with transport(lambda r, body=body: httpx.Response(200, content=body)) as adapter:
            with pytest.raises(E.InvalidProviderOutput):
                await adapter.complete(CALL)


async def test_http_header_deadline_is_bounded_even_with_a_slow_transport():
    async def handle(r):
        await asyncio.Event().wait()

    async with transport(handle) as adapter:
        with pytest.raises(E.ProviderTimeout):
            await asyncio.wait_for(anext(adapter.stream(replace(CALL, timeout_seconds=0.01))), timeout=0.5)


async def test_environment_proxy_is_not_used(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://invalid-proxy.example")
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid-proxy.example")
    # Construction must not read ambient proxy configuration; hook the constructor
    # to observe security-relevant arguments while keeping the HTTP fixture local.
    real = httpx.AsyncClient
    arguments = []

    def construct(**kw):
        arguments.append(kw)
        return real(**kw)

    monkeypatch.setattr(httpx, "AsyncClient", construct)
    async with transport(lambda r: httpx.Response(200, json=response())) as adapter:
        await adapter.complete(CALL)
    assert arguments[0]["trust_env"] is False and arguments[0]["follow_redirects"] is False


async def test_sse_early_usage_cannot_be_used_as_the_final_charge():
    body = sse(event({"content": "one"}, usage={"prompt_tokens": 7, "completion_tokens": 0}), event(finish="stop"))
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            _ = [c async for c in adapter.stream(CALL)]


class Fragments(httpx.AsyncByteStream):
    def __init__(self, data, step):
        self.data, self.step, self.closed = data, step, False

    async def __aiter__(self):
        for start in range(0, len(self.data), self.step):
            yield self.data[start:start + self.step]

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("step", [1, 7, 2048])
async def test_sse_network_fragmentation_and_comment_heartbeats(step):
    body = b": heartbeat\r\n\r\n" + sse(event({"content": "текст"}), event(finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3}))
    wire = Fragments(body, step)
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=wire)) as adapter:
        chunks = [c async for c in adapter.stream(CALL)]
    assert chunks[0] == TextDelta("текст") and isinstance(chunks[1], StreamEnd) and wire.closed


async def test_sse_aggregate_stream_and_fragmented_tool_limits():
    body = sse(event({"content": "a" * 50}), event({"content": "b" * 50}), event(finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3}))
    wire = Fragments(body, 23)
    settings = BifrostSettings(max_stream_bytes=len(body) - 1)
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=wire), settings=settings) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            _ = [c async for c in adapter.stream(CALL)]
    assert wire.closed
    tools = {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"large"}'}}]}
    async with transport(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(event(tools))),
                         settings=BifrostSettings(max_tool_argument_bytes=4)) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            await anext(adapter.stream(replace(CALL, tool_definitions=TOOLS)))


async def test_binding_profile_version_mismatch_denies_before_http():
    sent = []
    async with transport(lambda r: sent.append(r)) as adapter:
        with pytest.raises(E.GatewayUnconfigured):
            await adapter.complete(replace(CALL, profile=replace(PROFILE, pinned_model_version="other-snapshot")))
    assert sent == []


async def test_gateway_cookies_do_not_cross_request_scopes():
    sent = []

    def handle(r):
        sent.append(r)
        return httpx.Response(200, json=response(), headers={"set-cookie": "untrusted_scope=other; Path=/"})

    async with transport(handle) as adapter:
        await adapter.complete(CALL)
        await adapter.complete(replace(CALL, request_id="fixture-2"))
    assert all("cookie" not in r.headers for r in sent)


async def test_preflight_refusal_is_not_marked_as_a_billed_provider_call():
    async with transport(lambda r: None, evidence=()) as adapter:
        with pytest.raises(E.GatewayUnconfigured) as refusal:
            await adapter.complete(CALL)
        assert refusal.value.possibly_billed is False
    async with transport(lambda r: None) as adapter:
        with pytest.raises(E.InvalidRequest) as refusal:
            await adapter.complete(replace(CALL, response_schema={"$ref": "https://example.com/schema"}))
        assert refusal.value.possibly_billed is False


async def test_postdispatch_identity_refusal_is_marked_possibly_billed():
    async with transport(lambda r: httpx.Response(200, json=response(model="different"))) as adapter:
        with pytest.raises(E.InvalidProviderOutput) as failure:
            await adapter.complete(CALL)
    assert failure.value.possibly_billed is True


@pytest.mark.parametrize("stream", [False, True])
async def test_unpaired_unicode_in_provider_tool_arguments_is_a_typed_billed_refusal(stream):
    tool = {"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": chr(0xD800)}}
    if stream:
        payload = sse(event({"tool_calls": [{"index": 0, **tool}]}))
        reply = httpx.Response(200, content=payload, headers={"content-type": "text/event-stream"})
    else:
        payload = response(choices=[{"index": 0, "finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [tool]}}])
        reply = httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})
    async with transport(lambda _: reply) as adapter:
        with pytest.raises(E.InvalidProviderOutput) as failure:
            if stream:
                await anext(adapter.stream(replace(CALL, tool_definitions=TOOLS)))
            else:
                await adapter.complete(replace(CALL, tool_definitions=TOOLS))
    assert failure.value.possibly_billed is True


@pytest.mark.parametrize("stream", [False, True])
async def test_invalid_unicode_content_never_reaches_normalized_result(stream):
    if stream:
        reply = httpx.Response(200, content=sse(event({"content": chr(0xD800)})), headers={"content-type": "text/event-stream"})
    else:
        payload = response(choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": chr(0xD800)}}])
        reply = httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})
    async with transport(lambda _: reply) as adapter:
        with pytest.raises(E.InvalidProviderOutput):
            if stream:
                await anext(adapter.stream(CALL))
            else:
                await adapter.complete(CALL)
