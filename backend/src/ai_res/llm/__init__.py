"""LLM access (S15): LLMGatewayPort, Model Registry, routing, budgets, failure semantics.

Provider-neutral; provider SDKs may only live in `ai_res.llm.adapters` (S16)."""
from ai_res.llm.errors import LLMError, LLMErrorCode
from ai_res.llm.factory import build_llm_gateway
from ai_res.llm.gateway import GatewayPolicy, GovernedLLMGateway
from ai_res.llm.port import LLMGatewayPort, UnconfiguredLLMGateway
from ai_res.llm.registry import ModelProfile, ModelRegistry, ProfileStatus
from ai_res.llm.types import EmbeddingRequest, EmbeddingResponse, LLMLimits, LLMRequest, LLMResponse, Message, Role

__all__ = ["EmbeddingRequest", "EmbeddingResponse", "GatewayPolicy", "GovernedLLMGateway", "LLMError", "LLMErrorCode", "LLMGatewayPort", "LLMLimits",
           "LLMRequest", "LLMResponse", "Message", "ModelProfile", "ModelRegistry", "ProfileStatus", "Role", "UnconfiguredLLMGateway", "build_llm_gateway"]
