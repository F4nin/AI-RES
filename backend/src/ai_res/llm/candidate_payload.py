"""flash-candidate-body/0.1: synthetic candidate bytes, never dispatch authority.

The sole mutable input is a synthetic UUID marker. No project/user/source text or
arbitrary tool definition can enter these templates. Missing documented defaults
are made explicit; no unverified Bifrost message/tool transformation is guessed.
Consumers must send ``CandidateBody.content`` unchanged, using HTTP ``content=``:
the digest binds these final bytes, not a later JSON re-encoding. No I/O, approval,
grant, budget or model call is performed here. Never log the body or the marker.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, NoReturn
from uuid import UUID

CODEC_VERSION = "flash-candidate-body/0.1"
MAX_BODY_BYTES = 4096
MAX_OUTPUT_TOKENS = 256
_PROMPTS = (
    ("TEXT", "Synthetic Flash admission TEXT probe {marker}. Reply exactly OK."),
    ("JSON", 'Synthetic Flash admission JSON probe {marker}. Reply only with the JSON object {"ok":true}.'),
    ("TOOL", "Synthetic Flash admission TOOL probe {marker}. Call probe_check with ok=true."),
    ("SSE", "Synthetic Flash admission SSE probe {marker}. Reply exactly OK."),
    ("CANCEL", "Synthetic Flash admission CANCEL probe {marker}. Reply with a short sequence of words."),
    ("TIMEOUT", "Synthetic Flash admission TIMEOUT probe {marker}. Reply exactly OK."),
)


class CandidatePayloadError(ValueError):
    def __init__(self) -> None:
        super().__init__("Candidate body does not satisfy flash-candidate-body/0.1.")


def _require(condition: bool) -> None:
    if not condition:
        raise CandidatePayloadError()


def _serialize(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _template(case: str, marker: UUID) -> dict[str, Any]:
    pattern = next((prompt for name, prompt in _PROMPTS if name == case), None)
    _require(pattern is not None and isinstance(marker, UUID))
    assert pattern is not None
    # Replace exactly the marker placeholder; JSON's literal braces remain data.
    content = pattern.replace("{marker}", marker.hex)
    stream = case in ("SSE", "CANCEL")
    data: dict[str, Any] = {
        "model": "deepseek-flash", "messages": [{"role": "user", "content": content}],
        "max_tokens": (
            MAX_OUTPUT_TOKENS
        ),
        "thinking": {"type": "disabled"}, "stream": stream,
    }
    if stream:
        data["stream_options"] = {"include_usage": True}
    if case == "JSON":
        data["response_format"] = {"type": "json_object"}
    elif case == "TOOL":
        data["tools"] = [{"type": "function", "function": {
            "name": "probe_check", "description": "Synthetic admission probe; no action is performed.",
            "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}},
                           "required": ["ok"], "additionalProperties": False},
        }}]
        data["tool_choice"] = {"type": "function", "function": {"name": "probe_check"}}
    return data


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidatePayloadError()
        result[key] = value
    return result


def _nonfinite(_: str) -> NoReturn:
    raise CandidatePayloadError()


def _canonical_parts(raw: bytes) -> tuple[bytes, str, UUID, bool]:
    try:
        _require(type(raw) is bytes and 1 <= len(raw) <= MAX_BODY_BYTES)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        _require(isinstance(data, dict))
        _require(data.get("model") == "deepseek-flash")
        _require(type(data.get("max_tokens")) is int and data["max_tokens"] == MAX_OUTPUT_TOKENS)
        data.setdefault("thinking", {"type": "disabled"})
        data.setdefault("stream", False)
        _require(type(data["stream"]) is bool)
        if data["stream"]:
            data.setdefault("stream_options", {"include_usage": True})
        messages = data.get("messages")
        _require(isinstance(messages, list) and len(messages) == 1)
        message = messages[0]
        _require(isinstance(message, dict) and message.keys() == {"role", "content"}
                 and message["role"] == "user" and isinstance(message["content"], str))
        for case, prompt in _PROMPTS:
            prefix, suffix = prompt.split("{marker}")
            match = re.fullmatch(re.escape(prefix) + r"([0-9a-f]{32})" + re.escape(suffix), message["content"])
            if match is not None:
                marker = UUID(hex=match.group(1))
                expected = _serialize(_template(case, marker))
                # Compare encoded JSON, not Python equality: False != integer 0
                # and integer 256 != float 256.0 at this protocol boundary.
                _require(_serialize(data) == expected and len(expected) <= MAX_BODY_BYTES)
                return expected, case, marker, case in ("SSE", "CANCEL")
        raise CandidatePayloadError()
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise CandidatePayloadError() from None


@dataclass(frozen=True, slots=True, repr=False)
class CandidateBody:
    """Validated canonical bytes and derived metadata; constructing it grants nothing."""
    content: bytes
    body_sha256: str = field(init=False)
    payload_bytes: int = field(init=False)
    stream: bool = field(init=False)
    max_output_tokens: int = field(init=False, default=MAX_OUTPUT_TOKENS)
    case_ref: str = field(init=False)
    marker: UUID = field(init=False)
    codec_version: str = field(init=False, default=CODEC_VERSION)

    def __post_init__(self) -> None:
        content, case, marker, stream = _canonical_parts(self.content)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "body_sha256", hashlib.sha256(content).hexdigest())
        object.__setattr__(self, "payload_bytes", len(content))
        object.__setattr__(self, "stream", stream)
        object.__setattr__(self, "case_ref", case)
        object.__setattr__(self, "marker", marker)


def build_candidate_body(case: str, marker: UUID) -> CandidateBody:
    """Build one fixed synthetic template. RECHECK chooses a template/new marker externally."""
    _require(isinstance(case, str) and isinstance(marker, UUID))
    return CandidateBody(_serialize(_template(case, marker)))


def canonicalize_candidate_body(raw: bytes) -> CandidateBody:
    """Strict UTF-8 JSON -> final synthetic bytes. Refuses all extra execution parameters."""
    return CandidateBody(raw)
