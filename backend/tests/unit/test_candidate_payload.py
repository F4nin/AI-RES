"""Real synthetic body codec behavior; no model, Bifrost or egress is invoked."""
import hashlib
import json
from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from ai_res.llm.candidate_payload import CandidateBody, CandidatePayloadError, build_candidate_body, canonicalize_candidate_body

CASES = ("TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT")
MARKER = UUID("12345678-1234-1234-1234-123456789abc")


def encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def payload(case: str = "TEXT") -> dict:
    return json.loads(build_candidate_body(case, MARKER).content)


@pytest.mark.parametrize("case", CASES)
def test_builder_yields_bounded_exact_bytes_and_metadata(case):
    result = build_candidate_body(case, MARKER)
    data = json.loads(result.content)
    assert result.codec_version == "flash-candidate-body/0.1"
    assert result.case_ref == case and result.marker == MARKER
    assert result.payload_bytes == len(result.content) <= 4096
    assert result.body_sha256 == hashlib.sha256(result.content).hexdigest()
    assert result.content == encoded(data)
    assert data["model"] == "deepseek-flash" and data["max_tokens"] == result.max_output_tokens == 256
    assert data["thinking"] == {"type": "disabled"}
    assert data["stream"] is result.stream is (case in ("SSE", "CANCEL"))
    assert len(data["messages"]) == 1 and data["messages"][0]["role"] == "user"
    assert MARKER.hex in data["messages"][0]["content"]
    assert canonicalize_candidate_body(result.content) == result
    assert "Synthetic" not in repr(result) and MARKER.hex not in repr(result)


def test_text_template_is_a_specific_synthetic_request_not_an_arbitrary_message():
    assert payload()["messages"] == [{"role": "user", "content":
        "Synthetic Flash admission TEXT probe 12345678123412341234123456789abc. Reply exactly OK."}]
    with pytest.raises(FrozenInstanceError):
        build_candidate_body("TEXT", MARKER).content = b"changed"


def test_marker_changes_final_wire_bytes_and_digest_without_changing_case():
    previous, current = build_candidate_body("JSON", MARKER), build_candidate_body("JSON", uuid4())
    assert previous.content != current.content and previous.body_sha256 != current.body_sha256
    assert previous.case_ref == current.case_ref == "JSON"


def test_json_and_tool_templates_have_only_exact_safe_structures():
    data = payload("JSON")
    assert data["response_format"] == {"type": "json_object"}
    assert "JSON" in data["messages"][0]["content"]
    data = payload("TOOL")
    assert data["tool_choice"] == {"type": "function", "function": {"name": "probe_check"}}
    assert data["tools"] == [{"type": "function", "function": {"name": "probe_check",
        "description": "Synthetic admission probe; no action is performed.", "parameters": {
            "type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}}}]
    for case in ("SSE", "CANCEL"):
        assert payload(case)["stream_options"] == {"include_usage": True}


@pytest.mark.parametrize("case", CASES)
def test_whitespace_order_and_only_documented_absence_defaults_normalize(case):
    data = payload(case)
    del data["thinking"]
    if case in ("SSE", "CANCEL"):
        del data["stream_options"]
    else:
        del data["stream"]
    raw = json.dumps(dict(reversed(list(data.items()))), indent=2).encode()
    assert canonicalize_candidate_body(raw) == build_candidate_body(case, MARKER)


@pytest.mark.parametrize("case,marker", [("RECHECK", MARKER), ("text", MARKER), ("OTHER", MARKER),
    (None, MARKER), (True, MARKER), ("TEXT", "12345678-1234-1234-1234-123456789abc"), ("TEXT", None)])
def test_builder_refuses_unknown_template_or_non_uuid_marker_without_echo(case, marker):
    with pytest.raises(CandidatePayloadError) as error:
        build_candidate_body(case, marker)
    assert "OTHER" not in str(error.value)


@pytest.mark.parametrize("key,value", [("model", "deepseek-v4-pro"), ("model", "deepseek/deepseek-flash"),
    ("max_tokens", 256.0), ("max_tokens", True), ("max_tokens", 257), ("max_tokens", 1),
    ("stream", 0), ("stream", None), ("stream", True), ("thinking", None),
    ("thinking", {"type": "enabled"}), ("thinking", {"type": "disabled", "other": False}),
    ("stream_options", {"include_usage": True})])
def test_text_template_execution_parameters_cannot_be_changed(key, value):
    data = payload()
    data[key] = value
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(encoded(data))


@pytest.mark.parametrize("key,value", [("fallbacks", []), ("temperature", 0), ("n", 1), ("user", "private-value"),
    ("codecVersion", "flash-candidate-body/0.2"), ("max_completion_tokens", 256), ("response_format", {"type": "text"})])
def test_unknown_or_extra_fields_do_not_cross_the_egress_boundary(key, value):
    data = payload()
    data[key] = value
    with pytest.raises(CandidatePayloadError) as error:
        canonicalize_candidate_body(encoded(data))
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize("messages", [[], [{"role": "system", "content": "private-source"}],
    [{"role": "user", "content": "private-source"}], [{"role": "user", "content": [{"type": "text", "text": "private-source"}]}],
    [{"role": "user", "content": "Synthetic Flash admission TEXT probe 12345678123412341234123456789ABC. Reply exactly OK."}]])
def test_messages_have_no_arbitrary_text_or_unverified_provider_shape_normalization(messages):
    data = payload()
    data["messages"] = messages
    with pytest.raises(CandidatePayloadError) as error:
        canonicalize_candidate_body(encoded(data))
    assert "private-source" not in str(error.value)


@pytest.mark.parametrize("value", [False, 1, None, {"include_usage": False}, {"include_usage": 1}, {"include_usage": True, "other": False}])
def test_stream_options_require_exact_true_usage(value):
    data = payload("SSE")
    data["stream_options"] = value
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(encoded(data))


@pytest.mark.parametrize("change", ["tool-name", "property-type", "extra-tool", "bool-as-integer", "choice"])
def test_tool_template_cannot_smuggle_a_real_tool_schema_or_boolean_coercion(change):
    data = payload("TOOL")
    if change == "tool-name":
        data["tools"][0]["function"]["name"] = "real_action"
    elif change == "property-type":
        data["tools"][0]["function"]["parameters"]["properties"]["ok"]["type"] = "string"
    elif change == "extra-tool":
        data["tools"].append(data["tools"][0])
    elif change == "bool-as-integer":
        data["tools"][0]["function"]["parameters"]["additionalProperties"] = 0
    else:
        data["tool_choice"] = "auto"
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(encoded(data))


@pytest.mark.parametrize("raw", [b"", b"[]", b"null", b"{}", b"{", b"\xff", b" " * 4097,
    b'{"model":"deepseek-flash","model":"deepseek-flash"}', b'{"nested":{"duplicate":1,"duplicate":2}}',
    b'{"max_tokens":NaN}', b'{"max_tokens":Infinity}', b'{"messages":"\\ud800"}',
    '{"model":"deepseek-flash"}'.encode("utf-16"), b'\xef\xbb\xbf{}'])
def test_duplicate_invalid_utf8_nonfinite_unknown_and_oversized_payloads_are_refused(raw):
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(raw)


def test_canonical_dto_cannot_be_built_from_non_bytes_or_arbitrary_provider_content():
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body("private-source")
    with pytest.raises(CandidatePayloadError):
        CandidateBody(b'{"messages":[{"role":"user","content":"private-source"}]}')


@pytest.mark.parametrize("key", ["model", "max_tokens", "messages"])
def test_only_documented_defaults_can_fill_missing_fields(key):
    data = payload()
    del data[key]
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(encoded(data))


def test_size_boundary_counts_raw_utf8_bytes_before_canonicalization():
    content = build_candidate_body("TEXT", MARKER).content
    padded = content + b" " * (4096-len(content))
    assert canonicalize_candidate_body(padded).content == content
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(padded + b" ")
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(bytearray(content))


def test_derived_wire_metadata_cannot_be_supplied_to_the_dto_constructor():
    content = build_candidate_body("TEXT", MARKER).content
    with pytest.raises(TypeError):
        CandidateBody(content, body_sha256="a" * 64)
    with pytest.raises(TypeError):
        CandidateBody(content, stream=True)
    with pytest.raises(CandidatePayloadError):
        canonicalize_candidate_body(b"[" * 1100 + b"0" + b"]" * 1100)
