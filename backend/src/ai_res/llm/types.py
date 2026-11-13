"""Normalized LLM request/response model (API Contracts v1.10 §11). Provider-neutral: nothing here names a provider SDK or wire format.

Requests are validated on construction (fail closed): a malformed request never reaches routing, the budget ledger or a provider. Responses carry the ACTUAL
provider/model/version/profile (DOC-076 §3), so a WorkerRun can record what really answered, also after a fallback.
"""
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from ai_res.llm.errors import InvalidRequest

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LABEL = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
_PURPOSE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
MAX_MESSAGES = 512


class Capability(StrEnum):
    CHAT = "CHAT"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    TOOL_CALLING = "TOOL_CALLING"
    STREAMING = "STREAMING"
    VISION = "VISION"
    EMBEDDING = "EMBEDDING"


class Role(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    TOOL = "TOOL"


class FinishReason(StrEnum):
    STOP = "STOP"
    LENGTH = "LENGTH"
    TOOL_CALLS = "TOOL_CALLS"
    CONTENT_FILTER = "CONTENT_FILTER"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role) or not isinstance(self.content, str):
            raise InvalidRequest("message needs a role and text content")


@dataclass(frozen=True, slots=True)
class LLMLimits:
    max_output_tokens: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if (not isinstance(self.max_output_tokens, int) or isinstance(self.max_output_tokens, bool) or self.max_output_tokens < 1
                or not isinstance(self.timeout_seconds, int | float) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0):
            raise InvalidRequest("limits need a positive max_output_tokens and timeout_seconds")


def _common(request_id: str, purpose: str, budget_scope: str, data_classification: str, traceparent: str | None) -> None:
    if not _ID.match(request_id or ""):
        raise InvalidRequest("request_id is required (1-128 characters: letters, digits, . _ : -)")
    if not _PURPOSE.match(purpose or ""):
        raise InvalidRequest("purpose is required (a short label)")
    if not _ID.match(budget_scope or ""):
        raise InvalidRequest("budget_scope is required: a call without a budget is refused")
    if not _LABEL.match(data_classification or ""):
        raise InvalidRequest("data_classification is required (UPPER_SNAKE label)")
    if traceparent is not None and not _TRACEPARENT.match(traceparent):
        raise InvalidRequest("traceparent must be a W3C trace-context value")


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequest:
    request_id: str  # correlation + idempotent request identity towards the provider adapter
    model_profile_id: UUID
    purpose: str
    messages: tuple[Message, ...]
    budget_scope: str  # the budget (e.g. a WorkerRun grant) this call is charged to; established by the platform, never by the caller
    data_classification: str
    limits: LLMLimits
    response_schema_ref: str | None = None
    tool_definitions_ref: str | None = None
    stream: bool = False
    traceparent: str | None = None

    def __post_init__(self) -> None:
        _common(self.request_id, self.purpose, self.budget_scope, self.data_classification, self.traceparent)
        if not isinstance(self.model_profile_id, UUID):
            raise InvalidRequest("model_profile_id must be a UUID")
        if not self.messages or len(self.messages) > MAX_MESSAGES or not all(isinstance(m, Message) for m in self.messages):
            raise InvalidRequest(f"1-{MAX_MESSAGES} messages are required")
        for ref in (self.response_schema_ref, self.tool_definitions_ref):
            if ref is not None and not _ID.match(ref):
                raise InvalidRequest("schema and tool references are short identifiers, not inline content")

    def required_capabilities(self) -> frozenset[Capability]:
        needed = {Capability.CHAT}
        if self.response_schema_ref:
            needed.add(Capability.STRUCTURED_OUTPUT)
        if self.tool_definitions_ref:
            needed.add(Capability.TOOL_CALLING)
        if self.stream:
            needed.add(Capability.STREAMING)
        return frozenset(needed)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingRequest:
    request_id: str
    model_profile_id: UUID
    purpose: str
    inputs: tuple[str, ...]
    budget_scope: str
    data_classification: str
    timeout_seconds: float
    traceparent: str | None = None

    def __post_init__(self) -> None:
        _common(self.request_id, self.purpose, self.budget_scope, self.data_classification, self.traceparent)
        if not isinstance(self.model_profile_id, UUID):
            raise InvalidRequest("model_profile_id must be a UUID")
        if not self.inputs or len(self.inputs) > MAX_MESSAGES or not all(isinstance(i, str) and i for i in self.inputs):
            raise InvalidRequest(f"1-{MAX_MESSAGES} non-empty inputs are required")
        if not isinstance(self.timeout_seconds, int | float) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise InvalidRequest("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """The provider/model/version/profile that ACTUALLY answered (recorded per WorkerRun, DOC-076 §3)."""
    model_profile_id: UUID
    profile_key: str
    profile_version: int
    provider: str
    provider_model_id: str
    pinned_model_version: str


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise InvalidRequest("token usage cannot be negative")

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, Any]  # a REQUEST for the caller to run a tool: the gateway never executes it (tool calls pass the Policy Engine separately)


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    identity: ModelIdentity
    output: str | Mapping[str, Any] | None
    finish_reason: FinishReason
    usage: Usage
    latency_ms: int
    tool_calls: tuple[ToolCall, ...] = ()
    provider_request_ref: str | None = None
    attempts: int = 1
    redactions: int = 0  # secret-shaped values replaced in the prompt before it left the process (counts only, never values)
    fallback_used: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingResponse:
    identity: ModelIdentity
    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    latency_ms: int
    provider_request_ref: str | None = None
    attempts: int = 1
    redactions: int = 0
    fallback_used: bool = False


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallChunk:
    call: ToolCall


@dataclass(frozen=True, slots=True)
class StreamEnd:
    identity: ModelIdentity
    finish_reason: FinishReason
    usage: Usage
    provider_request_ref: str | None = None


StreamChunk = TextDelta | ToolCallChunk | StreamEnd  # typed chunks (API Contracts v1.10 §11)


class ContractCatalogPort(Protocol):
    """Resolves the references a request carries into the contracts they name. Unknown reference -> None (the gateway refuses the call)."""

    def response_schema(self, ref: str) -> Mapping[str, Any] | None: ...

    def tool_definitions(self, ref: str) -> Sequence[Mapping[str, Any]] | None: ...


@dataclass(frozen=True, slots=True)
class EmptyCatalog:
    """Resolves nothing: structured output and tool calls are refused until a catalog is wired (fail closed)."""

    def response_schema(self, ref: str) -> Mapping[str, Any] | None:
        return None

    def tool_definitions(self, ref: str) -> Sequence[Mapping[str, Any]] | None:
        return None


@dataclass(frozen=True, slots=True)
class StaticCatalog:
    schemas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    tools: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)

    def response_schema(self, ref: str) -> Mapping[str, Any] | None:
        return self.schemas.get(ref)

    def tool_definitions(self, ref: str) -> Sequence[Mapping[str, Any]] | None:
        return self.tools.get(ref)
