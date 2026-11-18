"""Synthetic HTTP streams only; no provider calls, model approval or real usage."""
import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from ai_res.llm.adapters.flash_candidate import FlashCandidateProbe, FlashCandidateSettings
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.llm.candidate_probe import CandidateProbeError, CandidateProbeEvidence, CandidateProbeUsage, ProbeErrorCode, ProbeOutcome
from ai_res.llm.observed_identity import FingerprintPresence


def response(**changes):
    return {"id": "synthetic-request", "model": "deepseek-v4-flash", "object": "chat.completion",
            "system_fingerprint": "synthetic-fingerprint", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14},
            "extra_fields": {"routing_info": {"provider": "deepseek", "model": "deepseek-flash",
                                             "requested_provider": "deepseek", "requested_model": "deepseek-flash"}}, **changes}


def event(delta=None, finish=None, usage=None, **changes):
    return response(**({"object": "chat.completion.chunk", "usage": usage,
                        "choices": [{"index": 0, "delta": {} if delta is None else delta, "finish_reason": finish}]} | changes))


def sse(*events, done=True):
    return ("".join("data: " + json.dumps(value) + "\r\n\r\n" for value in events)
            + ("data: [DONE]\r\n\r\n" if done else "")).encode()


def adapter(handler, **kwargs):
    return FlashCandidateProbe(virtual_key="synthetic-vk", http_transport=httpx.MockTransport(handler), **kwargs)


async def test_native_request_is_derived_only_from_validated_synthetic_body_and_evidence_has_no_content(monkeypatch):
    sent = []
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    body = build_candidate_body("TEXT", uuid4())

    def handle(request):
        sent.append(request)
        return httpx.Response(200, json=response(), headers={"set-cookie": "secret=never-replay"})

    async with adapter(handle) as probe:
        result = await probe.probe(body, timeout_seconds=1)
    wire = json.loads(sent[0].content)
    assert wire["model"] == "deepseek/deepseek-flash" and wire["max_completion_tokens"] == 256
    assert wire["fallbacks"] == [] and wire["store"] is False and wire["thinking"] == {"type": "disabled"}
    assert wire["messages"] == json.loads(body.content)["messages"] and "max_tokens" not in wire
    assert sent[0].headers["x-bf-vk"] == "synthetic-vk" and "authorization" not in sent[0].headers
    assert result.outcome is ProbeOutcome.COMPLETE and result.capability_ok
    assert result.identity.response_model_id == "deepseek-v4-flash" and result.provider_request_ref == "synthetic-request"
    assert result.usage.input_tokens == 12 and result.usage.output_tokens == 2
    assert result.observed_at.utcoffset().total_seconds() == 0 and result.body_sha256 == body.body_sha256
    assert not hasattr(result, "content") and "synthetic-fingerprint" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.capability_ok = False


@pytest.mark.parametrize("presence", ["absent", "null", "value"])
async def test_fingerprint_presence_is_observed_without_autoacceptance(presence):
    data = response()
    if presence == "absent":
        data.pop("system_fingerprint")
    elif presence == "null":
        data["system_fingerprint"] = None
    async with adapter(lambda _: httpx.Response(200, json=data)) as probe:
        result = await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert result.identity.fingerprint.presence is {"absent": FingerprintPresence.ABSENT, "null": FingerprintPresence.NULL,
                                                  "value": FingerprintPresence.VALUE}[presence]
    assert not hasattr(result, "approved") and not hasattr(result, "managed_versions")


@pytest.mark.parametrize("case,content,reason,tools,ok", [
    ("TEXT", "wrong", "stop", None, False), ("JSON", '{"ok":true}', "stop", None, True),
    ("JSON", '{"ok":1}', "stop", None, False), ("JSON", '{"ok":true,"extra":1}', "stop", None, False),
    ("TOOL", None, "tool_calls", [{"id": "synthetic-tool", "type": "function", "function": {
        "name": "probe_check", "arguments": '{"ok":true}'}}], True),
    ("TOOL", None, "tool_calls", [{"id": "synthetic-tool", "type": "function", "function": {
        "name": "probe_check", "arguments": '{"ok":false}'}}], False),
    ("TIMEOUT", "OK", "stop", None, True),
])
async def test_capability_summaries_never_expose_or_execute_tool_arguments(case, content, reason, tools, ok):
    message = {"role": "assistant", "content": content}
    if tools is not None:
        message["tool_calls"] = tools
    data = response(choices=[{"index": 0, "finish_reason": reason, "message": message}])
    async with adapter(lambda _: httpx.Response(200, json=data)) as probe:
        result = await probe.probe(build_candidate_body(case, uuid4()), timeout_seconds=1)
    assert result.outcome is ProbeOutcome.COMPLETE and result.capability_ok is ok
    assert not hasattr(result, "tool_calls") and not hasattr(result, "output")


@pytest.mark.parametrize("changes", [
    {"extra_fields": {}}, {"model": ""}, {"id": ""}, {"system_fingerprint": "bad\n"},
    {"usage": {"prompt_tokens": True, "completion_tokens": 2}},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 257}},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 15}},
    {"error": {"message": "private raw failure"}}, {"choices": []},
])
async def test_missing_or_malformed_identity_usage_and_errors_refuse_safe(changes):
    async with adapter(lambda _: httpx.Response(200, json=response(**changes))) as probe:
        with pytest.raises(CandidateProbeError) as error:
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert "private" not in str(error.value)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, raw, *, pause=False):
        self.raw, self.pause, self.closed = raw, pause, False

    async def __aiter__(self):
        for byte in self.raw:
            yield bytes([byte])
        if self.pause:
            await asyncio.sleep(10)

    async def aclose(self):
        self.closed = True


def stream_response(raw, *, pause=False):
    return httpx.Response(200, stream=Bytes(raw, pause=pause), headers={"content-type": "text/event-stream"})


async def test_incremental_crlf_stream_requires_consistent_identity_finish_usage_and_done():
    raw = sse(event({"content": "O"}), event({"content": "K"}), event(finish="stop"),
              event(usage={"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14}, choices=[]))
    upstream = stream_response(raw)
    async with adapter(lambda _: upstream) as probe:
        result = await probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=2)
    assert result.outcome is ProbeOutcome.COMPLETE and result.capability_ok and result.chunk_count == 4
    assert result.usage.output_tokens == 2 and upstream.is_closed


@pytest.mark.parametrize("raw", [
    sse(event({"content": "OK"}), event(finish="stop"), done=False), sse(),
    sse(event({"content": "OK"}), event(finish="stop")),
    sse(event({"content": "OK"}), event(finish="stop"), {"error": {"message": "private"}}),
    sse(event({"content": "O"}), event({"content": "K"}, model="different-model")),
    sse(event({"content": "O"}), event({"content": "K"}, id="different-request")),
    b"event: error\ndata: {}\n\ndata: [DONE]\n\n", b"data: {\xff}\n\n",
])
async def test_incomplete_or_error_stream_never_emits_final_evidence_even_with_done(raw):
    upstream = stream_response(raw)
    async with adapter(lambda _: upstream) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=1)
    assert upstream.is_closed


async def test_intentional_cancel_closes_before_next_chunk_without_fabricated_final_usage():
    upstream = stream_response(sse(event({"content": "word"}), done=False), pause=True)
    async with adapter(lambda _: upstream) as probe:
        result = await probe.probe(build_candidate_body("CANCEL", uuid4()), timeout_seconds=1)
    assert result.outcome is ProbeOutcome.CANCELLED and not result.capability_ok and result.usage is None
    assert upstream.is_closed


async def test_timeout_is_distinct_from_cancel_and_closes_stream():
    upstream = httpx.Response(200, stream=Bytes(b"", pause=True), headers={"content-type": "application/json"})
    async with adapter(lambda _: upstream) as probe:
        result = await probe.probe(build_candidate_body("TIMEOUT", uuid4()), timeout_seconds=0.01)
    assert result.outcome is ProbeOutcome.TIMEOUT and result.identity is None and result.usage is None
    assert upstream.is_closed


async def test_external_task_cancellation_propagates_and_closes_response():
    upstream = stream_response(b"", pause=True)
    async with adapter(lambda _: upstream) as probe:
        task = asyncio.create_task(probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=10))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert upstream.is_closed


@pytest.mark.parametrize("status", [301, 401, 429, 500])
async def test_http_failures_never_retry(status):
    sent = []
    def handle(request):
        sent.append(request)
        return httpx.Response(status, text="private upstream body", headers={"location": "https://example.com"})
    async with adapter(handle) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert len(sent) == 1


@pytest.mark.parametrize("url", ["https://example.com/v1/chat/completions", "http://127.0.0.1:8080/v1/chat/completions",
                                "http://bifrost-poc:8080/providers", "http://a:b@bifrost-poc:8080/v1/chat/completions",
                                "http://bifrost-poc:8080/v1/chat/completions?x=1"])
def test_only_internal_native_inference_endpoint_can_be_configured(url):
    with pytest.raises(ValueError):
        FlashCandidateSettings(inference_url=url)


@pytest.mark.parametrize("key", [None, "", "bad\nkey", "a" * 513])
def test_virtual_key_is_required_and_never_echoed(key):
    with pytest.raises(ValueError) as error:
        FlashCandidateProbe(virtual_key=key)
    assert "bad" not in str(error.value)


async def test_cookie_from_one_response_is_not_sent_on_next_request():
    sent = []
    def handle(request):
        sent.append(request)
        return httpx.Response(200, json=response(), headers={"set-cookie": "secret=never-replay; Path=/"})
    async with adapter(handle) as probe:
        for _ in range(2):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert all("cookie" not in request.headers for request in sent)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
async def test_invalid_limits_refuse_before_http(timeout):
    sent = []
    async with adapter(lambda request: sent.append(request)) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=timeout)
    assert sent == []


@pytest.mark.parametrize("limit,value", [("max_response_bytes", 20), ("max_event_bytes", 20), ("max_stream_bytes", 20)])
async def test_incremental_size_limits_fail_closed(limit, value):
    settings = replace(FlashCandidateSettings(), **{limit: value})
    stream = limit != "max_response_bytes"
    raw = sse(event({"content": "OK"}), event(finish="stop"))
    upstream = stream_response(raw) if stream else httpx.Response(200, json=response())
    async with adapter(lambda _: upstream, settings=settings) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("SSE" if stream else "TEXT", uuid4()), timeout_seconds=1)


@pytest.mark.parametrize("finish", [[], {}, True, 1, "unknown"])
async def test_untrusted_finish_type_never_escapes_as_raw_exception(finish):
    data = response(choices=[{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": "OK"}}])
    async with adapter(lambda _: httpx.Response(200, json=data)) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)


@pytest.mark.parametrize("finish", [[], {}, True, 1, "unknown"])
async def test_untrusted_stream_finish_type_is_controlled(finish):
    async with adapter(lambda _: stream_response(sse(event({"content": "OK"}, finish=finish)))) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=1)


@pytest.mark.parametrize("case", ["TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT"])
def test_all_native_templates_preserve_closed_codec_content_and_output_cap(case):
    body = build_candidate_body(case, uuid4())
    native = json.loads(FlashCandidateProbe.native_request(body))
    codec = json.loads(body.content)
    for name, value in codec.items():
        if name not in {"model", "max_tokens"}:
            assert native[name] == value
    assert native.keys() == (codec.keys() - {"max_tokens"}) | {"max_completion_tokens", "fallbacks", "store"}


@pytest.mark.parametrize("field,value", [
    ("provider", "other"), ("model", "deepseek-v4-pro"), ("requested_model", None), ("requested_provider", None),
    ("is_fallback", True), ("is_fallback", 0), ("resolved_key_alias", {"model_id": "other"}),
    ("server_side_fallback_model", "other"),
])
async def test_observed_routing_is_never_guessed_or_redirected(field, value):
    data = response()
    data["extra_fields"]["routing_info"][field] = value
    async with adapter(lambda _: httpx.Response(200, json=data)) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)


@pytest.mark.parametrize("raw", [b'{"id":"first","id":"second"}', b'{"x":NaN}', b'{"x":Infinity}',
                              b'{"x":"\\ud800"}', b'{"x":"\xff"}', b'[]', b'\xff\xfe{\x00}\x00'])
async def test_duplicate_nonfinite_surrogate_non_utf8_and_nonobjects_refuse_safe(raw):
    async with adapter(lambda _: httpx.Response(200, content=raw, headers={"content-type": "application/json"})) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)


@pytest.mark.parametrize("inp,out", [(0, 0), (2_000_000, 256)])
def test_usage_boundaries(inp, out):
    assert CandidateProbeUsage(inp, out).input_tokens == inp


@pytest.mark.parametrize("inp,out", [(True, 2), (1.0, 2), (0, True), (-1, 0), (2_000_001, 0), (0, 257), (None, 1)])
def test_usage_types_and_bounds_are_strict(inp, out):
    with pytest.raises(CandidateProbeError) as error:
        CandidateProbeUsage(inp, out)
    assert error.value.code is ProbeErrorCode.INVALID_USAGE


@pytest.mark.parametrize("changes", [
    {"identity": None}, {"provider_request_ref": None}, {"usage": None}, {"chunk_count": True},
    {"observed_at": datetime(2026, 1, 1)}, {"outcome": "COMPLETE"}, {"case_ref": "RECHECK"},
    {"body_sha256": "a" * 64 + "\n"}, {"provider_request_ref": "unsafe\nref"},
    {"outcome": ProbeOutcome.CANCELLED}, {"outcome": ProbeOutcome.TIMEOUT},
])
async def test_evidence_dto_cannot_claim_impossible_completion_or_unsafe_metadata(changes):
    async with adapter(lambda _: httpx.Response(200, json=response())) as probe:
        result = await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    with pytest.raises(CandidateProbeError):
        replace(result, **changes)
    exported = result.to_dict()
    assert exported["version"] == "flash-candidate-evidence/0.1" and exported["observedAt"].endswith("Z")
    assert set(exported) == {"version", "caseRef", "bodySha256", "observedAt", "outcome", "identity", "providerRequestRef",
                             "usage", "capabilityOk", "chunkCount"}


async def test_pending_request_refuses_another_probe_without_queuing_dispatch():
    entered, release, sent = asyncio.Event(), asyncio.Event(), []
    async def handle(request):
        sent.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(200, json=response())
    async with adapter(handle) as probe:
        task = asyncio.create_task(probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1))
        await entered.wait()
        with pytest.raises(CandidateProbeError) as error:
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
        release.set()
        await task
    assert len(sent) == 1 and error.value.code is ProbeErrorCode.INVALID_REQUEST


async def test_timeout_during_response_headers_is_controlled_without_invented_identity():
    async def handle(_):
        await asyncio.sleep(10)
    async with adapter(handle) as probe:
        result = await probe.probe(build_candidate_body("TIMEOUT", uuid4()), timeout_seconds=0.01)
    assert result.outcome is ProbeOutcome.TIMEOUT and result.identity is None and result.usage is None


async def test_transport_failure_is_safe_and_never_retried():
    sent = []
    def handle(request):
        sent.append(request)
        raise httpx.ConnectError("private failure contains credential")
    async with adapter(handle) as probe:
        with pytest.raises(CandidateProbeError) as error:
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert len(sent) == 1 and error.value.code is ProbeErrorCode.CONNECTION_FAILED
    assert "private" not in str(error.value) and error.value.__cause__ is None


@pytest.mark.parametrize("change", ["fingerprint", "null-fingerprint", "absent-fingerprint", "provider-ref", "early-usage", "double-usage",
                                  "late-content", "double-done", "unterminated", "comment-utf8", "tool-delta"])
async def test_stream_identity_usage_order_and_terminal_state_are_strict(change):
    start = event({"content": "OK"})
    finish = event(finish="stop")
    usage = event(usage={"prompt_tokens": 12, "completion_tokens": 2}, choices=[])
    events = [start, finish, usage]
    if change == "fingerprint":
        finish["system_fingerprint"] = "different"
    elif change == "null-fingerprint":
        finish["system_fingerprint"] = None
    elif change == "absent-fingerprint":
        finish.pop("system_fingerprint")
    elif change == "provider-ref":
        finish["id"] = "different"
    elif change == "early-usage":
        start["usage"] = {"prompt_tokens": 12, "completion_tokens": 2}
    elif change == "double-usage":
        events.append(usage)
    elif change == "late-content":
        events.append(start)
    elif change == "tool-delta":
        start["choices"][0]["delta"] = {"tool_calls": [{"index": 0, "function": {"name": "never-execute"}}]}
    raw = sse(*events)
    if change == "double-done":
        raw += b"data: [DONE]\n\n"
    elif change == "unterminated":
        raw += b"data: partial"
    elif change == "comment-utf8":
        raw = b": \xff\n\n" + raw
    async with adapter(lambda _: stream_response(raw)) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=1)


async def test_split_multibyte_utf8_stream_and_multiline_events_are_parsed_incrementally():
    data = event({"content": "🚀"})
    encoded = json.dumps(data, ensure_ascii=False).replace(', "model"', ',\ndata: "model"').encode()
    raw = b": comment\nid: ignored\nretry: 100\nevent: message\ndata: " + encoded + b"\n\n"
    raw += sse(event(finish="stop"), event(usage={"prompt_tokens": 12, "completion_tokens": 2}, choices=[]))
    async with adapter(lambda _: stream_response(raw)) as probe:
        result = await probe.probe(build_candidate_body("SSE", uuid4()), timeout_seconds=1)
    assert result.outcome is ProbeOutcome.COMPLETE and not result.capability_ok


@pytest.mark.parametrize("stream", [False, True])
async def test_encoded_response_is_refused_before_decompression(stream):
    upstream = stream_response(b"data: [DONE]\n\n") if stream else httpx.Response(200, json=response())
    upstream.headers["content-encoding"] = "gzip"
    async with adapter(lambda _: upstream) as probe:
        with pytest.raises(CandidateProbeError):
            await probe.probe(build_candidate_body("SSE" if stream else "TEXT", uuid4()), timeout_seconds=1)


def test_controlled_incomplete_dto_has_no_approval_fields():
    result = CandidateProbeEvidence("TIMEOUT", "a" * 64, datetime.now(UTC), ProbeOutcome.TIMEOUT, None, None, None, False)
    assert result.to_dict()["identity"] is None


@pytest.mark.parametrize("field", ["id", "model", "system_fingerprint"])
async def test_exact_known_credential_cannot_escape_through_response_metadata(field):
    credential = str(uuid4())  # A token shape that generic secret heuristics cannot recognize.
    data = response(**{field: "prefix-" + credential + "-suffix"})
    async with FlashCandidateProbe(virtual_key=credential, http_transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as probe:
        with pytest.raises(CandidateProbeError) as error:
            await probe.probe(build_candidate_body("TEXT", uuid4()), timeout_seconds=1)
    assert credential not in str(error.value)


@pytest.mark.parametrize("case", ["SSE", "CANCEL", "TIMEOUT"])
@pytest.mark.parametrize("field", ["id", "model", "system_fingerprint"])
async def test_known_credential_cannot_escape_stream_partial_cancel_or_timeout_facts(case, field):
    credential = str(uuid4())
    first = event({"content": "word"}, **{field: credential})
    upstream = stream_response(sse(first, done=False), pause=True)
    if case == "TIMEOUT":
        # TIMEOUT is a non-stream template, so echo is refused in a complete JSON
        # response too; actual stream timeout is exercised by the SSE parameter.
        upstream = httpx.Response(200, json=response(**{field: credential}))
    async with FlashCandidateProbe(virtual_key=credential, http_transport=httpx.MockTransport(lambda _: upstream)) as probe:
        with pytest.raises(CandidateProbeError) as error:
            await probe.probe(build_candidate_body(case, uuid4()), timeout_seconds=0.05)
    assert credential not in str(error.value) and upstream.is_closed
