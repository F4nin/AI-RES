"""Provider-facing seam. Adapters (S16: AI RES adapter -> Bifrost) implement `ProviderTransport`; only they may import a provider SDK (import-linter, ADR-031).

A transport receives an already governed call: approved profile, redacted messages, resolved schema/tool contracts, a deadline. It maps provider failures to the
typed errors of `ai_res.llm.errors` and never returns credentials. Credentials stay on its side of the seam (DOC-076 §5).
"""
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ai_res.llm.registry import ModelProfile
from ai_res.llm.types import FinishReason, Message, StreamChunk, ToolCall, Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportCall:
    request_id: str
    profile: ModelProfile
    messages: tuple[Message, ...]
    max_output_tokens: int
    timeout_seconds: float
    response_schema: Mapping[str, Any] | None = None
    tool_definitions: Sequence[Mapping[str, Any]] | None = None
    traceparent: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportEmbeddingCall:
    request_id: str
    profile: ModelProfile
    inputs: tuple[str, ...]
    timeout_seconds: float
    traceparent: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportResult:
    output: str | Mapping[str, Any] | None
    finish_reason: FinishReason
    usage: Usage
    tool_calls: tuple[ToolCall, ...] = ()
    provider_request_ref: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportEmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    provider_request_ref: str | None = None


class ProviderTransport(Protocol):
    async def complete(self, call: TransportCall) -> TransportResult: ...

    def stream(self, call: TransportCall) -> AsyncIterator[StreamChunk]: ...

    async def embed(self, call: TransportEmbeddingCall) -> TransportEmbeddingResult: ...
