"""LLMGatewayPort: the ONLY way Manager/Worker code reaches a model (ADR-031, architecture-constraints.md)."""
from collections.abc import AsyncIterator
from typing import Protocol

from ai_res.llm.errors import GatewayUnconfigured
from ai_res.llm.types import EmbeddingRequest, EmbeddingResponse, LLMRequest, LLMResponse, StreamChunk


class LLMGatewayPort(Protocol):
    async def chat(self, request: LLMRequest) -> LLMResponse: ...

    async def structured(self, request: LLMRequest) -> LLMResponse:
        """`request.response_schema_ref` is required; the output is validated against the named schema before it is returned."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

    def stream_chat(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """`request.stream` must be true. Governance happens before the first chunk; a failure mid-stream is raised, never retried or re-routed."""


class UnconfiguredLLMGateway:
    """Default gateway (`llm_gateway=unconfigured`): every call is refused, so a deployment without a provider decision cannot reach a model."""

    async def chat(self, request: LLMRequest) -> LLMResponse:
        raise GatewayUnconfigured("no LLM gateway is configured")

    async def structured(self, request: LLMRequest) -> LLMResponse:
        raise GatewayUnconfigured("no LLM gateway is configured")

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise GatewayUnconfigured("no LLM gateway is configured")

    def stream_chat(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        raise GatewayUnconfigured("no LLM gateway is configured")
