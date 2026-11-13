"""DeterministicLLMGateway: a LLMGatewayPort implementation for tests ONLY (ADR-022). It does NOT evaluate model quality: output is a pure function of the input
(or a scripted reply), so reports built on it must say that agent output quality was not verified.

It is the real `GovernedLLMGateway` (registry, approval, budget, guard, retry, fallback all apply) over a scripted `DeterministicTransport`.
"""
import hashlib
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from ai_res.llm.budget import BudgetLedgerPort, InMemoryBudgetLedger
from ai_res.llm.errors import LLMError
from ai_res.llm.gateway import GatewayPolicy, GovernedLLMGateway
from ai_res.llm.registry import ModelRegistry
from ai_res.llm.transport import TransportCall, TransportEmbeddingCall, TransportEmbeddingResult, TransportResult
from ai_res.llm.types import ContractCatalogPort, FinishReason, StreamChunk, StreamEnd, TextDelta, Usage
from ai_res.platform.config import ConfigError, Settings

MARKER = "[DETERMINISTIC-TEST-DOUBLE]"
Step = LLMError | TransportResult  # a scripted outcome: raise the error or return the result


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _example(schema: Mapping[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        return {k: _example(props[k]) for k in schema.get("required", []) if k in props}
    return {"string": "x", "integer": 0, "number": 0, "boolean": False, "array": []}.get(kind) if isinstance(kind, str) else None


class DeterministicTransport:
    def __init__(self) -> None:
        self.script: deque[Step] = deque()  # consumed first; then the deterministic default applies
        self.calls: list[TransportCall | TransportEmbeddingCall] = []  # what reached the "provider" (tests assert redaction here)
        self.on_call: Callable[[], None] | None = None

    def _next(self) -> Step | None:
        if self.on_call:
            self.on_call()
        return self.script.popleft() if self.script else None

    async def complete(self, call: TransportCall) -> TransportResult:
        self.calls.append(call)
        step = self._next()
        if isinstance(step, LLMError):
            raise step
        if step is not None:
            return step
        d = _digest(call.request_id, *(m.content for m in call.messages))
        output: Any = _example(call.response_schema) if call.response_schema is not None else f"{MARKER} {d[:16]}"
        n_in = sum(len(m.content) for m in call.messages) // 4 + 1
        return TransportResult(output=output, finish_reason=FinishReason.STOP, usage=Usage(n_in, 8), provider_request_ref=f"det-{d[:12]}")

    async def stream(self, call: TransportCall) -> AsyncIterator[StreamChunk]:
        self.calls.append(call)
        step = self._next()
        if isinstance(step, LLMError):
            raise step
        text = f"{MARKER} {_digest(call.request_id)[:8]}"
        for word in text.split(" "):
            yield TextDelta(word + " ")
        yield StreamEnd(identity=None, finish_reason=FinishReason.STOP, usage=Usage(1, len(text.split())))  # type: ignore[arg-type]  # the gateway fills the identity

    async def embed(self, call: TransportEmbeddingCall) -> TransportEmbeddingResult:
        self.calls.append(call)
        step = self._next()
        if isinstance(step, LLMError):
            raise step
        vectors = tuple(tuple(b / 255 for b in hashlib.sha256(i.encode()).digest()[:8]) for i in call.inputs)
        return TransportEmbeddingResult(vectors=vectors, usage=Usage(sum(len(i) for i in call.inputs) // 4 + 1, 0), provider_request_ref="det-embed")


class DeterministicLLMGateway(GovernedLLMGateway):
    """Refuses to be built outside environment=test, whatever the caller did to obtain a Settings object."""

    def __init__(self, settings: Settings, *, registry: Callable[[], ModelRegistry], ledger: BudgetLedgerPort | None = None,
                 catalog: ContractCatalogPort | None = None, policy: GatewayPolicy | None = None, transport: DeterministicTransport | None = None,
                 **kwargs: Any) -> None:
        if settings.environment != "test":
            raise ConfigError("DeterministicLLMGateway is allowed only when environment=test (ADR-022)")
        self.transport = transport or DeterministicTransport()
        self.ledger = ledger or InMemoryBudgetLedger()
        super().__init__(registry=registry, transport=self.transport, ledger=self.ledger, catalog=catalog, policy=policy, **kwargs)
