# ruff: noqa: E501  -- long prose lines in the module docstring
"""GovernedLLMGateway: policy, budget, redaction and failure semantics around a `ProviderTransport` (DOC-076 §4-§6, ADR-109).

Order of every call (fail closed at each step, nothing reaches the provider before all pass):
 request validated on construction -> profile resolved (registered AND approved) -> capabilities / data classification / context window / output limit checked ->
 prompt guarded (block or redact) -> budget reserved (worst case) -> breaker consulted -> provider called under a deadline -> output validated -> usage settled.
Retry only for retryable errors, bounded, with jitter, honouring Retry-After; a budget or policy refusal is never retried. After the attempts on a profile are used up
by an availability failure, the next policy-approved fallback is tried (routing.fallback_candidates). Cancellation propagates and always releases the reservation.
Telemetry carries codes, counts and ids only: never prompt or response content.
"""
import asyncio
import json
import logging
import math
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar

import jsonschema
from opentelemetry import metrics, trace

from ai_res.llm.budget import BudgetLedgerPort, Reservation, worst_case_cost
from ai_res.llm.errors import (
    CapabilityNotSupported,
    CircuitOpen,
    DataClassificationNotAllowed,
    InputExceedsContextWindow,
    InvalidProviderOutput,
    InvalidRequest,
    LLMError,
    ProviderTimeout,
    ProviderUnavailable,
)
from ai_res.llm.guard import guard_inputs, guard_messages
from ai_res.llm.registry import ModelProfile, ModelRegistry, RetryClass
from ai_res.llm.routing import fallback_candidates
from ai_res.llm.transport import ProviderTransport, TransportCall, TransportEmbeddingCall
from ai_res.llm.types import (
    Capability,
    ContractCatalogPort,
    EmbeddingRequest,
    EmbeddingResponse,
    EmptyCatalog,
    LLMRequest,
    LLMResponse,
    Message,
    ModelIdentity,
    StreamChunk,
    StreamEnd,
    Usage,
)
from ai_res.platform.config import Settings

R = TypeVar("R", LLMResponse, EmbeddingResponse)
_log = logging.getLogger("ai_res.llm")
_tracer = trace.get_tracer("ai_res.llm")
_meter = metrics.get_meter("ai_res.llm")
_REQUESTS = _meter.create_counter("ai_res.llm.requests", description="LLM gateway calls by provider and outcome code")
_TOKENS = _meter.create_counter("ai_res.llm.tokens", description="Provider-reported tokens by provider and direction")
_LATENCY = _meter.create_histogram("ai_res.llm.duration", unit="s", description="Gateway call duration by provider and outcome code")


@dataclass(frozen=True, slots=True)
class GatewayPolicy:
    """WORKING technical defaults (ADR-109), not SLOs (OD-02). Supplied from configuration."""
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    circuit_failure_threshold: int = 5
    circuit_open_seconds: float = 30.0
    bytes_per_token_estimate: float = 3.0  # input size estimate only; the provider-reported usage is what is settled

    @classmethod
    def from_settings(cls, settings: Settings) -> "GatewayPolicy":
        return cls(settings.llm_retry_max_attempts, settings.llm_retry_base_delay_seconds, settings.llm_retry_max_delay_seconds,
                   settings.llm_circuit_failure_threshold, settings.llm_circuit_open_seconds, settings.llm_bytes_per_token_estimate)

    def __post_init__(self) -> None:
        if (self.retry_max_attempts < 1 or self.retry_base_delay_seconds < 0 or self.retry_max_delay_seconds < self.retry_base_delay_seconds
                or self.circuit_failure_threshold < 1 or self.circuit_open_seconds <= 0 or self.bytes_per_token_estimate <= 0):
            raise ValueError("invalid gateway policy")


class _Breaker:
    """Per-profile circuit breaker, process-local: opens after N consecutive availability failures, lets ONE probe through after the open period.
    A probe that ends without a verdict (cancelled, budget refusal, non-availability error) is handed back with `release_probe`; a probe also expires by itself
    after the open period, so no path can leave a profile closed for good."""

    def __init__(self, threshold: int, open_seconds: float, clock: Callable[[], float]) -> None:
        self._threshold, self._open, self._clock = threshold, open_seconds, clock
        self._failures: dict[object, int] = {}
        self._opened_at: dict[object, float] = {}
        self._probing: dict[object, float] = {}

    def allow(self, key: object) -> bool:
        opened = self._opened_at.get(key)
        if opened is None:
            return True
        now = self._clock()
        if now - opened < self._open:
            return False
        started = self._probing.get(key)
        if started is not None and now - started < self._open:
            return False
        self._probing[key] = now
        return True

    def release_probe(self, key: object) -> None:
        self._probing.pop(key, None)

    def success(self, key: object) -> None:
        self._failures.pop(key, None)
        self._opened_at.pop(key, None)
        self._probing.pop(key, None)

    def failure(self, key: object) -> None:
        self._probing.pop(key, None)
        n = self._failures.get(key, 0) + 1
        self._failures[key] = n
        if n >= self._threshold:
            self._opened_at[key] = self._clock()


@dataclass(frozen=True, slots=True)
class _Prepared:
    messages: tuple[Message, ...]
    redactions: int
    profiles: list[ModelProfile]
    schema: Mapping[str, Any] | None
    tools: Sequence[Mapping[str, Any]] | None
    tokens: int


def _identity(p: ModelProfile) -> ModelIdentity:
    return ModelIdentity(p.id, p.profile_key, p.profile_version, p.provider, p.provider_model_id, p.pinned_model_version)


class GovernedLLMGateway:
    def __init__(self, *, registry: Callable[[], ModelRegistry], transport: ProviderTransport, ledger: BudgetLedgerPort,
                 catalog: ContractCatalogPort | None = None, policy: GatewayPolicy | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, rng: random.Random | None = None) -> None:
        self._registry, self._transport, self._ledger = registry, transport, ledger
        self._catalog = catalog or EmptyCatalog()
        self._policy = policy or GatewayPolicy()
        self._clock, self._monotonic, self._sleep = clock, monotonic, sleep
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not security
        self._breaker = _Breaker(self._policy.circuit_failure_threshold, self._policy.circuit_open_seconds, monotonic)

    # ---- public port ----
    async def chat(self, request: LLMRequest) -> LLMResponse:
        if request.stream or request.response_schema_ref:
            raise InvalidRequest("chat() is for plain non-streaming calls; use structured() or stream_chat()")
        return await self._complete(request)

    async def structured(self, request: LLMRequest) -> LLMResponse:
        if request.stream or not request.response_schema_ref:
            raise InvalidRequest("structured() needs response_schema_ref and no streaming")
        return await self._complete(request)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        now = self._clock()
        registry = self._registry()
        primary = registry.resolve(request.model_profile_id, now)
        need = frozenset({Capability.EMBEDDING})
        if sum(self._estimate(i) for i in request.inputs) > primary.context_window_tokens:
            raise InputExceedsContextWindow("input exceeds the context window of the profile")
        inputs, redactions = guard_inputs(request.inputs)
        tokens = sum(self._estimate(i) for i in inputs)
        self._require(primary, need, request.data_classification)
        profiles = [primary, *self._fallbacks(registry, primary, request.data_classification, need, tokens, now)]

        async def run(p: ModelProfile) -> tuple[EmbeddingResponse, Usage]:
            call = TransportEmbeddingCall(request_id=request.request_id, profile=p, inputs=inputs,
                                          timeout_seconds=min(request.timeout_seconds, p.timeout_seconds), traceparent=request.traceparent)
            r = await self._transport.embed(call)
            return EmbeddingResponse(identity=_identity(p), vectors=r.vectors, usage=r.usage, latency_ms=0, provider_request_ref=r.provider_request_ref,
                                     redactions=redactions), r.usage

        async def attempt(p: ModelProfile) -> tuple[EmbeddingResponse, Usage]:
            return await asyncio.wait_for(run(p), timeout=min(request.timeout_seconds, p.timeout_seconds))

        return await self._governed("embed", request.budget_scope, profiles, tokens, 0, attempt)

    def stream_chat(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if not request.stream or request.response_schema_ref:
            raise InvalidRequest("stream_chat() needs stream=true and no response_schema_ref (streamed output is not schema-validated)")
        return self._stream(request)

    # ---- internals ----
    def _estimate(self, text: str) -> int:
        return math.ceil(len(text.encode("utf-8")) / self._policy.bytes_per_token_estimate)

    def _require(self, p: ModelProfile, need: frozenset[Capability], classification: str) -> None:
        if not need <= p.capabilities:
            raise CapabilityNotSupported("the profile does not support a required capability")  # incompatibility is reported, not hidden (Contracts §11)
        if classification not in p.data_classifications:
            raise DataClassificationNotAllowed("the profile may not receive this data classification")

    def _fallbacks(self, registry: ModelRegistry, primary: ModelProfile, classification: str, need: frozenset[Capability], tokens: int,
                   now: datetime, max_out: int = 1) -> tuple[ModelProfile, ...]:
        return fallback_candidates(registry, primary, now=now, data_classification=classification, required=need, context_tokens=tokens, max_output_tokens=max_out)

    def _prepare(self, request: LLMRequest) -> _Prepared:
        now = self._clock()
        registry = self._registry()
        primary = registry.resolve(request.model_profile_id, now)
        need = request.required_capabilities()
        self._require(primary, need, request.data_classification)
        if request.limits.max_output_tokens > primary.max_output_tokens:
            raise InvalidRequest("max_output_tokens exceeds the profile's maximum")
        schema = tools = None
        if request.response_schema_ref:
            schema = self._catalog.response_schema(request.response_schema_ref)
            if schema is None:
                raise InvalidRequest("response_schema_ref is not a known contract")
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.SchemaError:
                raise InvalidRequest("response schema is not a valid JSON Schema") from None
        if request.tool_definitions_ref:
            tools = self._catalog.tool_definitions(request.tool_definitions_ref)
            if tools is None:
                raise InvalidRequest("tool_definitions_ref is not a known contract")
        raw = sum(self._estimate(m.content) for m in request.messages)
        if raw + request.limits.max_output_tokens > primary.context_window_tokens:  # before the scan: its cost is bounded by the context window
            raise InputExceedsContextWindow("input plus output limit exceeds the context window of the profile")
        messages, redactions = guard_messages(request.messages)
        tokens = sum(self._estimate(m.content) for m in messages) + sum(self._estimate(json.dumps(x, default=str)) for x in (schema, tools) if x is not None)
        if tokens + request.limits.max_output_tokens > primary.context_window_tokens:
            raise InputExceedsContextWindow("input plus output limit exceeds the context window of the profile")
        profiles = [primary, *self._fallbacks(registry, primary, request.data_classification, need, tokens, now, request.limits.max_output_tokens)]
        return _Prepared(messages, redactions, profiles, schema, tools, tokens)

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        prep = self._prepare(request)
        messages, redactions, profiles, schema, tools, tokens = prep.messages, prep.redactions, prep.profiles, prep.schema, prep.tools, prep.tokens

        async def attempt(p: ModelProfile) -> tuple[LLMResponse, Usage]:
            started = self._monotonic()
            timeout = min(request.limits.timeout_seconds, p.timeout_seconds)
            call = TransportCall(request_id=request.request_id, profile=p, messages=messages, max_output_tokens=request.limits.max_output_tokens,
                                 timeout_seconds=timeout, response_schema=schema, tool_definitions=tools, traceparent=request.traceparent)
            r = await asyncio.wait_for(self._transport.complete(call), timeout=timeout)
            resp = LLMResponse(identity=_identity(p), output=r.output, finish_reason=r.finish_reason, usage=r.usage,
                               latency_ms=int((self._monotonic() - started) * 1000), tool_calls=r.tool_calls,
                               provider_request_ref=r.provider_request_ref, redactions=redactions)
            return resp, r.usage

        def validate(resp: LLMResponse) -> None:
            if schema is not None:
                self._validate_output(schema, resp.output)

        return await self._governed("chat", request.budget_scope, profiles, tokens, request.limits.max_output_tokens, attempt, validate)

    @staticmethod
    def _validate_output(schema: object, output: object) -> None:
        if not isinstance(output, dict):
            raise InvalidProviderOutput("structured output is not a JSON object")
        try:
            jsonschema.Draft202012Validator(schema).validate(output)  # type: ignore[arg-type]
        except jsonschema.ValidationError:
            raise InvalidProviderOutput("structured output does not match the response schema") from None  # never echo the provider's value

    async def _governed(self, kind: str, scope: str, profiles: list[ModelProfile], in_tokens: int, max_out: int,
                        attempt: Callable[[ModelProfile], Awaitable[tuple[R, Usage]]], validate: Callable[[R], None] = lambda _: None) -> R:
        last: LLMError | None = None
        tried = profiles[0]
        with _tracer.start_as_current_span(f"llm.{kind}", record_exception=False, set_status_on_exception=False) as span:
            started = self._monotonic()
            attempts = 0
            try:
                for index, profile in enumerate(profiles):
                    max_attempts = self._policy.retry_max_attempts if profile.retry_class is RetryClass.BOUNDED else 1
                    for n in range(1, max_attempts + 1):
                        if not self._breaker.allow(profile.id):
                            last = last or CircuitOpen("circuit is open for this profile")  # a real earlier failure stays the reported cause
                            break
                        try:
                            reservation = await self._reserve(scope, profile, in_tokens, max_out)
                        except LLMError:
                            self._breaker.release_probe(profile.id)
                            if index > 0 and last is not None:
                                break  # this fallback cannot be afforded/priced: the primary's failure remains the cause
                            raise
                        except BaseException:
                            self._breaker.release_probe(profile.id)
                            raise
                        tried = profile
                        attempts += 1
                        error: LLMError
                        try:
                            response, usage = await attempt(profile)
                        except TimeoutError:
                            error = ProviderTimeout("provider call exceeded its deadline")
                        except LLMError as exc:
                            error = exc
                        except asyncio.CancelledError:
                            await self._release_quietly(reservation)
                            self._breaker.release_probe(profile.id)
                            raise
                        except Exception as exc:  # a transport that did not map its failure: never leak its text, treat as unavailability
                            _log.warning("unmapped transport failure", extra={"error_type": type(exc).__name__})
                            error = ProviderUnavailable("provider call failed")
                        except BaseException:
                            await self._release_quietly(reservation)
                            self._breaker.release_probe(profile.id)
                            raise
                        else:
                            self._breaker.success(profile.id)  # the provider answered: its availability is fine whatever the content
                            await self._settle_quietly(reservation, usage.total, self._cost(profile, usage))  # tokens WERE spent, valid or not
                            try:
                                validate(response)
                            except LLMError as invalid:
                                raise invalid from None
                            self._record(span, profile, "OK", usage, started, attempts)
                            return replace(response, attempts=attempts, fallback_used=index > 0)
                        if isinstance(error, ProviderTimeout):  # the request reached the provider and may have been billed: charge the INPUT estimate (ADR-108)
                            rates = profile.cost_rates
                            await self._settle_quietly(reservation, in_tokens, rates.cost(in_tokens, 0) if rates else None)
                        else:
                            await self._release_quietly(reservation)  # no usage is known for any other failed attempt
                        last = error
                        if error.fallback_eligible:
                            self._breaker.failure(profile.id)
                        else:
                            self._breaker.release_probe(profile.id)
                        if not error.retryable or n == max_attempts:
                            break
                        await self._sleep(self._delay(n, error))
                    if last is not None and not last.fallback_eligible:
                        raise last  # a non-availability failure is not cured by another model
                if last is None:
                    raise CircuitOpen("no model profile is available")
                raise last
            except LLMError as exc:
                self._record(span, tried, exc.code.value, None, started, attempts)
                raise

    async def _reserve(self, scope: str, profile: ModelProfile, in_tokens: int, max_out: int) -> Reservation:
        cost = worst_case_cost(profile.cost_rates, in_tokens, max_out)
        return await self._ledger.reserve(scope, tokens=in_tokens + max_out, cost=cost,
                                          currency=profile.cost_rates.currency if profile.cost_rates else None)

    async def _release_quietly(self, reservation: Reservation) -> None:
        """Give the hold back without ever replacing the error being handled (a ledger fault is logged, the hold stays: the conservative side)."""
        try:
            await asyncio.shield(self._ledger.release(reservation))
        except Exception as exc:
            _log.error("budget release failed; the reservation stays held", extra={"error_type": type(exc).__name__, "budget_scope": reservation.scope})

    async def _settle_quietly(self, reservation: Reservation, tokens: int, cost: Decimal | None) -> None:
        """Charge actual usage. A ledger fault must not discard a response that was already paid for: it is logged and the (worst-case) hold stays."""
        try:
            await asyncio.shield(self._ledger.settle(reservation, tokens=tokens, cost=cost))
        except Exception as exc:
            _log.error("budget settle failed; the reservation stays held", extra={"error_type": type(exc).__name__, "budget_scope": reservation.scope})

    @staticmethod
    def _cost(profile: ModelProfile, usage: Usage) -> Decimal | None:
        return profile.cost_rates.cost(usage.input_tokens, usage.output_tokens) if profile.cost_rates else None

    def _delay(self, attempt_no: int, error: LLMError) -> float:
        p = self._policy
        backoff = min(p.retry_max_delay_seconds, p.retry_base_delay_seconds * 2 ** (attempt_no - 1))
        delay = self._rng.uniform(0, backoff)  # full jitter
        if error.retry_after_seconds is not None:
            delay = max(delay, min(error.retry_after_seconds, p.retry_max_delay_seconds))  # Retry-After honoured, capped
        return delay

    def _record(self, span: trace.Span, profile: ModelProfile, outcome: str, usage: Usage | None, started: float, attempts: int) -> None:
        labels = {"ai_res.llm.provider": profile.provider, "ai_res.llm.outcome": outcome}  # bounded: registry values and error codes
        _REQUESTS.add(1, labels)
        _LATENCY.record(self._monotonic() - started, labels)
        span.set_attribute("ai_res.llm.provider", profile.provider)
        span.set_attribute("ai_res.llm.model_profile_id", str(profile.id))
        span.set_attribute("ai_res.llm.outcome", outcome)
        span.set_attribute("ai_res.llm.attempts", attempts)
        if usage is not None:
            _TOKENS.add(usage.input_tokens, {"ai_res.llm.provider": profile.provider, "ai_res.llm.direction": "input"})
            _TOKENS.add(usage.output_tokens, {"ai_res.llm.provider": profile.provider, "ai_res.llm.direction": "output"})
            span.set_attribute("ai_res.llm.usage_total", usage.total)

    async def _stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Governance runs before the first chunk. No re-routing mid-stream (the first chunk may already be with the caller). The deadline bounds PROVIDER
        time only (waiting for the next chunk), never the consumer's pauses. Tokens already generated are charged: a stream that ends without StreamEnd, fails
        or is abandoned after the first chunk settles the worst-case hold instead of releasing it."""
        prep = self._prepare(request)
        profile = prep.profiles[0]
        if not self._breaker.allow(profile.id):
            raise CircuitOpen("circuit is open for this profile")
        started = self._monotonic()
        try:
            reservation = await self._reserve(request.budget_scope, profile, prep.tokens, request.limits.max_output_tokens)
        except BaseException:
            self._breaker.release_probe(profile.id)
            raise
        timeout = min(request.limits.timeout_seconds, profile.timeout_seconds)
        call = TransportCall(request_id=request.request_id, profile=profile, messages=prep.messages, max_output_tokens=request.limits.max_output_tokens,
                             timeout_seconds=timeout, tool_definitions=prep.tools, traceparent=request.traceparent)
        settled, received, ended, verdict = False, False, False, False
        provider_time = 0.0
        outcome = "OK"
        iterator = self._transport.stream(call).__aiter__()
        try:
            while True:
                remaining = timeout - provider_time
                waited = self._monotonic()
                try:
                    async with asyncio.timeout(max(remaining, 0)):
                        chunk = await anext(iterator)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise ProviderTimeout("provider stream exceeded its deadline") from None
                provider_time += self._monotonic() - waited
                if ended:
                    raise InvalidProviderOutput("provider sent data after the end of the stream")
                received = True
                if isinstance(chunk, StreamEnd):
                    ended = True
                    chunk = StreamEnd(_identity(profile), chunk.finish_reason, chunk.usage, chunk.provider_request_ref)
                    settled = True  # decided before the await: a cancellation inside it must not trigger a second settlement
                    await self._settle_quietly(reservation, chunk.usage.total, self._cost(profile, chunk.usage))
                    self._breaker.success(profile.id)
                    verdict = True
                    self._record_stream(profile, "OK", chunk.usage, started)
                yield chunk
            if not ended:
                raise InvalidProviderOutput("provider stream ended without a final usage record")
        except LLMError as exc:
            outcome = exc.code.value
            if not verdict:
                self._breaker.failure(profile.id) if exc.fallback_eligible else self._breaker.release_probe(profile.id)
                verdict = True
            raise
        except BaseException:
            outcome = "CANCELLED_OR_ABANDONED"
            raise
        finally:
            if not verdict:
                self._breaker.release_probe(profile.id)
            if not settled:
                if received:  # tokens were generated: charge the worst case rather than let the budget be bypassed
                    await self._settle_quietly(reservation, reservation.tokens, reservation.cost)
                else:
                    await self._release_quietly(reservation)
            if outcome != "OK":
                self._record_stream(profile, outcome, None, started)
            aclose = getattr(iterator, "aclose", None)
            if aclose is not None:
                await aclose()

    def _record_stream(self, profile: ModelProfile, outcome: str, usage: Usage | None, started: float) -> None:
        with _tracer.start_as_current_span("llm.stream", record_exception=False, set_status_on_exception=False) as span:
            self._record(span, profile, outcome, usage, started, 1)
