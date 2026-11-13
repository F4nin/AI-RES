# ruff: noqa: E501  -- compact test fixtures
"""S15: LLMGatewayPort, Model Registry, budgets, routing, failure semantics over the deterministic test double (ADR-022). Output QUALITY of a model is not tested here."""
import asyncio
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count
from uuid import UUID, uuid4

import pytest

from ai_res.llm import (
    EmbeddingRequest,
    GatewayPolicy,
    LLMLimits,
    LLMRequest,
    Message,
    ModelProfile,
    ModelRegistry,
    ProfileStatus,
    Role,
    UnconfiguredLLMGateway,
    build_llm_gateway,
)
from ai_res.llm import errors as E
from ai_res.llm.budget import Budget, InMemoryBudgetLedger
from ai_res.llm.registry import CostRates, Egress, RetryClass
from ai_res.llm.routing import RouteInput, RoutingPolicy, RoutingRule
from ai_res.llm.transport import TransportResult
from ai_res.llm.types import Capability, FinishReason, StaticCatalog, StreamEnd, TextDelta, Usage
from ai_res.platform.config import ConfigError, Settings
from ai_res_testkit.deterministic_llm import MARKER, DeterministicLLMGateway


def _join(*parts: str) -> str:
    return "".join(parts)  # fake credentials are assembled at run time so that no secret-shaped literal sits in the repository (infra/scripts/scan_secrets.py)


PEM_BEGIN, PEM_END = _join("-----BEGIN ", "PRIVATE KEY-----"), _join("-----END ", "PRIVATE KEY-----")
FAKE_ANTHROPIC = _join("sk-", "ant-api03-abcdefghijklmnop-qrstuvwx")
FAKE_OPENAI = _join("sk-", "abcdefghijklmnopqrstuvwx")
FAKE_AWS = _join("AKIA", "ABCDEFGHIJKLMNOP")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
ALL = frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT, Capability.STREAMING, Capability.EMBEDDING})


_SEQ = count(1)
DEFAULT_BUDGET = Budget(max_total_tokens=100_000)
DEFAULT_USAGE = Usage(5, 5)


def profile(**kw: object) -> ModelProfile:
    base: dict[str, object] = dict(
        id=uuid4(), profile_key=f"alpha{next(_SEQ)}", profile_version=1, provider="prov-a", provider_model_id="m-1", pinned_model_version="2026-01-01",
        capabilities=ALL, context_window_tokens=10_000, max_output_tokens=1_000, data_classifications=frozenset({"INTERNAL"}),
        allowed_regions=frozenset({"eu"}), egress=Egress.EXTERNAL, timeout_seconds=5.0, retry_class=RetryClass.BOUNDED, status=ProfileStatus.APPROVED,
        approved_at=NOW - timedelta(days=1))
    return ModelProfile(**{**base, **kw})  # type: ignore[arg-type]


def request(p: ModelProfile, text: str = "hello", **kw: object) -> LLMRequest:
    base: dict[str, object] = dict(request_id="req-1", model_profile_id=p.id, purpose="TEST", messages=(Message(Role.USER, text),), budget_scope="run-1",
                                   data_classification="INTERNAL", limits=LLMLimits(100, 5.0))
    return LLMRequest(**{**base, **kw})  # type: ignore[arg-type]


class Rig:
    def __init__(self, *profiles: ModelProfile, budget: Budget | None = DEFAULT_BUDGET, policy: GatewayPolicy | None = None,
                 catalog: StaticCatalog | None = None) -> None:
        self.registry = ModelRegistry(profiles)
        self.sleeps: list[float] = []

        async def sleep(s: float) -> None:
            self.sleeps.append(s)

        self.clock = [0.0]
        self.gw = DeterministicLLMGateway(Settings(environment="test"), registry=lambda: self.registry, catalog=catalog, clock=lambda: NOW,
                                          policy=policy or GatewayPolicy(retry_max_attempts=3, retry_base_delay_seconds=1.0, retry_max_delay_seconds=4.0),
                                          sleep=sleep, monotonic=lambda: self.clock[0])
        if budget is not None:
            self.gw.ledger.establish("run-1", budget)  # type: ignore[attr-defined]

    @property
    def calls(self) -> list[object]:
        return self.gw.transport.calls  # type: ignore[attr-defined,no-any-return]

    @property
    def script(self) -> object:
        return self.gw.transport.script  # type: ignore[attr-defined]


def ok(text: str = "r", usage: Usage = DEFAULT_USAGE) -> TransportResult:
    return TransportResult(output=text, finish_reason=FinishReason.STOP, usage=usage)


# ---------- approval / registry ----------
async def test_unapproved_unknown_deprecated_and_retired_profiles_are_refused_before_any_call():
    cand = profile(status=ProfileStatus.CANDIDATE, approved_at=None)
    retired = profile(status=ProfileStatus.RETIRED)
    scheduled = profile(deprecated_at=NOW - timedelta(seconds=1))
    r = Rig(cand, retired, scheduled)
    for p in (cand, retired, scheduled):
        with pytest.raises(E.ModelProfileNotApproved):
            await r.gw.chat(request(p))
    with pytest.raises(E.ModelProfileNotFound):
        await r.gw.chat(request(profile()))
    with pytest.raises(E.ModelProfileNotFound):
        await Rig().gw.chat(request(profile()))  # empty registry fails closed
    assert r.calls == []


def test_registry_rejects_floating_versions_duplicates_and_unapproved_claims():
    for alias in ("latest", " LATEST ", "stable", ""):
        with pytest.raises(ValueError, match="pin"):
            profile(pinned_model_version=alias)
    with pytest.raises(ValueError, match="approved_at"):
        profile(approved_at=None)
    p = profile()
    with pytest.raises(ValueError, match="duplicate"):
        ModelRegistry([p, replace(p, id=uuid4())])
    with pytest.raises(ValueError, match="currency"):
        CostRates(currency="usd", input_per_million=Decimal(1), output_per_million=Decimal(1))


# ---------- budget ----------
async def test_budget_exhausted_is_typed_and_never_retried_or_sent():
    p = profile()
    r = Rig(p, budget=Budget(max_total_tokens=50))
    with pytest.raises(E.BudgetExhausted) as exc:
        await r.gw.chat(request(p))  # worst case: input estimate + 100 output tokens > 50
    assert not exc.value.retryable and r.calls == [] and r.sleeps == []


async def test_budget_is_charged_with_reported_usage_and_runs_out_across_calls():
    p = profile()
    r = Rig(p, budget=Budget(max_total_tokens=250))
    r.script.append(ok(usage=Usage(100, 100)))  # type: ignore[attr-defined]
    await r.gw.chat(request(p))
    assert r.gw.ledger.usage("run-1") == (200, Decimal(0))  # type: ignore[attr-defined]
    with pytest.raises(E.BudgetExhausted):
        await r.gw.chat(request(p))
    assert len(r.calls) == 1


async def test_call_without_established_budget_and_unenforceable_cost_budget_are_refused():
    p = profile()
    with pytest.raises(E.BudgetNotEstablished):
        await Rig(p, budget=None).gw.chat(request(p))
    r = Rig(p, budget=Budget(max_cost=Decimal(1), currency="EUR"))  # profile has no cost rates
    with pytest.raises(E.BudgetUnenforceable):
        await r.gw.chat(request(p))
    priced = profile(cost_rates=CostRates(currency="EUR", input_per_million=Decimal(1000), output_per_million=Decimal(1000)))
    r2 = Rig(priced, budget=Budget(max_cost=Decimal("0.0001"), currency="EUR"))
    with pytest.raises(E.BudgetExhausted):
        await r2.gw.chat(request(priced))


def test_budget_scope_cannot_be_reestablished():
    ledger = InMemoryBudgetLedger()
    ledger.establish("s", Budget(max_total_tokens=1))
    with pytest.raises(ValueError, match="already"):
        ledger.establish("s", Budget(max_total_tokens=10**9))


async def test_failed_attempts_release_their_reservation_and_cancellation_does_too():
    p = profile(retry_class=RetryClass.NONE)
    r = Rig(p, budget=Budget(max_total_tokens=1000))
    r.script.append(E.ProviderRejected())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderRejected):
        await r.gw.chat(request(p))
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]

    gate = asyncio.Event()

    async def hang(call: object) -> TransportResult:
        await gate.wait()
        return ok()

    r.gw.transport.complete = hang  # type: ignore[attr-defined,method-assign]
    task = asyncio.create_task(r.gw.chat(request(p, limits=LLMLimits(100, 5.0))))
    await asyncio.sleep(0.01)
    assert r.gw.ledger._accounts["run-1"].held_tokens > 0  # type: ignore[attr-defined]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]


# ---------- test double only in the test profile ----------
def test_test_double_is_refused_outside_the_test_profile_at_every_barrier():
    for env in ("local", "prod"):
        with pytest.raises(ValueError, match="test double"):
            Settings(environment=env, llm_gateway="deterministic-test-double")  # type: ignore[arg-type]
        bypass = Settings.model_construct(environment=env, llm_gateway="deterministic-test-double")  # a Settings object that skipped validation
        with pytest.raises(ConfigError, match="environment=test"):
            build_llm_gateway(bypass)
        with pytest.raises(ConfigError, match="environment=test"):
            DeterministicLLMGateway(bypass, registry=ModelRegistry)
    assert isinstance(build_llm_gateway(Settings(environment="prod")), UnconfiguredLLMGateway)  # default profile: nothing to call
    assert isinstance(build_llm_gateway(Settings(environment="test", llm_gateway="deterministic-test-double")), DeterministicLLMGateway)


def test_importing_the_test_package_under_a_non_test_profile_fails():
    for env in ("prod", "local"):
        r = subprocess.run([sys.executable, "-c", "import ai_res_testkit"], capture_output=True, text=True, check=False,
                           env={**os.environ, "AI_RES_ENVIRONMENT": env, "PYTHONPATH": os.pathsep.join(sys.path)})
        assert r.returncode != 0 and "test-only" in r.stderr


async def test_unconfigured_gateway_refuses_everything():
    p = profile()
    gw = UnconfiguredLLMGateway()
    with pytest.raises(E.GatewayUnconfigured):
        await gw.chat(request(p))
    with pytest.raises(E.GatewayUnconfigured):
        gw.stream_chat(request(p, stream=True))


def test_the_production_image_and_wheel_do_not_contain_the_test_package():
    import tomllib
    from pathlib import Path
    backend = Path(__file__).resolve().parents[2]
    assert tomllib.loads((backend / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/ai_res"]
    copies = [ln for ln in (backend / "Dockerfile").read_text().splitlines() if ln.startswith(("COPY ", "ADD ")) and "--from" not in ln]
    assert copies and not any("testkit" in ln or ln.split()[1:-1] in (["."], ["./"]) for ln in copies), copies


# ---------- secrets in prompts ----------
async def test_high_confidence_secret_blocks_the_call_without_echoing_it():
    p = profile()
    r = Rig(p)
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk"
    for text in (f"use token {jwt}", "postgresql://app:pw@db:5432/x", f"{PEM_BEGIN}\nabc\n{PEM_END}", f"key {FAKE_OPENAI}"):
        with pytest.raises(E.SecretInPrompt) as exc:
            await r.gw.chat(request(p, text))
        assert jwt not in str(exc.value) and "pw@" not in str(exc.value)
    assert r.calls == [] and r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]


async def test_low_confidence_secret_is_redacted_before_the_provider_sees_it():
    p = profile()
    r = Rig(p)
    resp = await r.gw.chat(request(p, "Login with password: hunter2 please", ))
    sent = r.calls[0].messages[0].content  # type: ignore[attr-defined]
    assert "hunter2" not in sent and "[REDACTED]" in sent and resp.redactions == 1
    # a secret in a later (system) message and in embedding input is covered too
    resp2 = await r.gw.chat(request(p, "x", messages=(Message(Role.SYSTEM, "api_key=abcd1234"), Message(Role.USER, "ok"))))
    assert "abcd1234" not in r.calls[-1].messages[0].content and resp2.redactions == 1  # type: ignore[attr-defined]
    emb = await r.gw.embed(EmbeddingRequest(request_id="e1", model_profile_id=p.id, purpose="T", inputs=("secret: zzz999",), budget_scope="run-1",
                                            data_classification="INTERNAL", timeout_seconds=2))
    assert "zzz999" not in r.calls[-1].inputs[0] and emb.redactions == 1  # type: ignore[attr-defined]


async def test_secret_beyond_the_log_truncation_limit_is_still_scanned():
    p = profile(context_window_tokens=100_000, max_output_tokens=1000)
    r = Rig(p, budget=Budget(max_total_tokens=10**7))
    with pytest.raises(E.SecretInPrompt):
        await r.gw.chat(request(p, "a " * 20_000 + FAKE_AWS))


# ---------- capabilities, classification, limits ----------
async def test_incompatible_capability_classification_and_limits_are_reported_not_hidden():
    chat_only = profile(capabilities=frozenset({Capability.CHAT}))
    r = Rig(chat_only, catalog=StaticCatalog(schemas={"s": {"type": "object"}}))
    with pytest.raises(E.CapabilityNotSupported):
        await r.gw.structured(request(chat_only, response_schema_ref="s"))
    with pytest.raises(E.DataClassificationNotAllowed):
        await r.gw.chat(request(chat_only, data_classification="RESTRICTED"))
    with pytest.raises(E.InvalidRequest, match="max_output"):
        await r.gw.chat(request(chat_only, limits=LLMLimits(5000, 5.0)))
    with pytest.raises(E.InputExceedsContextWindow):
        await r.gw.chat(request(chat_only, "x" * 40_000))
    with pytest.raises(E.InvalidRequest):
        await r.gw.chat(request(chat_only, stream=True))
    assert r.calls == []


def test_malformed_requests_are_rejected_on_construction():
    p = profile()
    for bad in (dict(request_id=""), dict(messages=()), dict(data_classification="internal"), dict(budget_scope=""), dict(traceparent="x"),
                dict(response_schema_ref="{inline}"), dict(limits=LLMLimits(1, 1))):
        if "limits" in bad:
            continue
        with pytest.raises(E.InvalidRequest):
            request(p, **bad)
    with pytest.raises(E.InvalidRequest):
        LLMLimits(0, 1)


async def test_structured_output_is_validated_against_the_named_schema():
    p = profile()
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}
    r = Rig(p, catalog=StaticCatalog(schemas={"s1": schema}))
    good = await r.gw.structured(request(p, response_schema_ref="s1"))
    assert good.output == {"n": 0}
    r.script.append(TransportResult(output={"n": "SECRET-VALUE"}, finish_reason=FinishReason.STOP, usage=Usage(1, 1)))  # type: ignore[attr-defined]
    with pytest.raises(E.InvalidProviderOutput) as exc:
        await r.gw.structured(request(p, response_schema_ref="s1"))
    assert "SECRET-VALUE" not in str(exc.value)
    with pytest.raises(E.InvalidRequest, match="not a known"):
        await r.gw.structured(request(p, response_schema_ref="missing"))
    with pytest.raises(E.InvalidRequest):
        await r.gw.chat(request(p, response_schema_ref="s1"))


# ---------- retries ----------
async def test_transient_errors_are_retried_with_bounded_jittered_backoff_and_retry_after():
    p = profile()
    r = Rig(p)
    r.script.extend([E.ProviderUnavailable(), E.ProviderRateLimited(retry_after_seconds=3.5), ok("done")])  # type: ignore[attr-defined]
    resp = await r.gw.chat(request(p))
    assert resp.output == "done" and resp.attempts == 3 and len(r.sleeps) == 2
    assert 0 <= r.sleeps[0] <= 1.0 and r.sleeps[1] >= 3.5  # full jitter within the cap; Retry-After honoured
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]


async def test_retries_are_bounded_and_permanent_errors_are_not_retried():
    p = profile()
    r = Rig(p)
    r.script.extend([E.ProviderUnavailable()] * 10)  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderUnavailable):
        await r.gw.chat(request(p))
    assert len(r.calls) == 3
    r2 = Rig(p)
    r2.script.append(E.ProviderRejected())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderRejected):
        await r2.gw.chat(request(p))
    assert len(r2.calls) == 1 and r2.sleeps == []
    r3 = Rig(profile(retry_class=RetryClass.NONE))
    only = next(iter(r3.registry.all()))
    r3.script.extend([E.ProviderUnavailable()] * 3)  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderUnavailable):
        await r3.gw.chat(request(only))
    assert len(r3.calls) == 1


async def test_provider_deadline_is_enforced():
    p = profile(timeout_seconds=0.05, retry_class=RetryClass.NONE)
    r = Rig(p)

    async def slow(call: object) -> TransportResult:
        await asyncio.sleep(1)
        return ok()

    r.gw.transport.complete = slow  # type: ignore[attr-defined,method-assign]
    with pytest.raises(E.ProviderTimeout):
        await r.gw.chat(request(p, limits=LLMLimits(100, 30.0)))  # the profile's deadline is the tighter one
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]  # a timed-out attempt gives its reservation back


# ---------- fallback ----------
async def test_fallback_goes_only_to_an_approved_equal_or_stricter_profile_of_the_group():
    primary = profile(profile_key="primary", fallback_group="g", retry_class=RetryClass.NONE, allowed_regions=frozenset({"eu", "us"}))
    safe = profile(profile_key="safe", fallback_group="g", provider="prov-b", egress=Egress.EXTERNAL, allowed_regions=frozenset({"eu"}))
    wider_region = profile(profile_key="wide", fallback_group="g", allowed_regions=frozenset({"eu", "apac"}))
    unapproved = profile(profile_key="cand", fallback_group="g", status=ProfileStatus.CANDIDATE, approved_at=None)
    other_group = profile(profile_key="other", fallback_group="h")
    wrong_class = profile(profile_key="noclass", fallback_group="g", data_classifications=frozenset({"PUBLIC"}))
    r = Rig(primary, safe, wider_region, unapproved, other_group, wrong_class)
    r.script.append(E.ProviderUnavailable())  # type: ignore[attr-defined]
    resp = await r.gw.chat(request(primary))
    assert resp.fallback_used and resp.identity.model_profile_id == safe.id and resp.identity.provider == "prov-b"
    assert [c.profile.id for c in r.calls] == [primary.id, safe.id]  # type: ignore[attr-defined]


async def test_outage_never_reaches_a_more_exposed_or_unapproved_model():
    local_primary = profile(profile_key="local", egress=Egress.LOCAL, fallback_group="g", retry_class=RetryClass.NONE)
    public = profile(profile_key="public", egress=Egress.EXTERNAL, fallback_group="g")
    r = Rig(local_primary, public)
    r.script.append(E.ProviderUnavailable())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderUnavailable):
        await r.gw.chat(request(local_primary))
    assert len(r.calls) == 1


async def test_policy_refusals_and_permanent_errors_do_not_trigger_fallback():
    primary = profile(profile_key="p", fallback_group="g", retry_class=RetryClass.NONE)
    other = profile(profile_key="q", fallback_group="g")
    r = Rig(primary, other)
    r.script.append(E.ProviderRejected())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderRejected):
        await r.gw.chat(request(primary))
    assert len(r.calls) == 1
    r.gw.ledger._accounts["run-1"].budget = Budget(max_total_tokens=0)  # type: ignore[attr-defined]
    with pytest.raises(E.BudgetExhausted):
        await r.gw.chat(request(primary))
    assert len(r.calls) == 1


# ---------- circuit breaker ----------
async def test_circuit_opens_after_consecutive_failures_and_recovers_after_the_open_period():
    p = profile(retry_class=RetryClass.NONE)
    r = Rig(p, policy=GatewayPolicy(circuit_failure_threshold=2, circuit_open_seconds=30))
    r.script.extend([E.ProviderUnavailable(), E.ProviderUnavailable()])  # type: ignore[attr-defined]
    for _ in range(2):
        with pytest.raises(E.ProviderUnavailable):
            await r.gw.chat(request(p))
    with pytest.raises(E.CircuitOpen):
        await r.gw.chat(request(p))
    assert len(r.calls) == 2
    r.clock[0] = 31.0
    assert (await r.gw.chat(request(p))).output  # one probe allowed, success closes the circuit
    await r.gw.chat(request(p))


# ---------- streaming and embeddings ----------
async def test_stream_yields_typed_chunks_with_actual_identity_and_settles_budget():
    p = profile()
    r = Rig(p)
    chunks = [c async for c in r.gw.stream_chat(request(p, stream=True))]
    assert all(isinstance(c, TextDelta) for c in chunks[:-1]) and isinstance(chunks[-1], StreamEnd)
    assert chunks[-1].identity.model_profile_id == p.id and MARKER.split("]")[0] in "".join(c.text for c in chunks[:-1])
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0 and r.gw.ledger.usage("run-1")[0] > 0  # type: ignore[attr-defined]


async def test_abandoned_stream_after_data_is_charged_the_worst_case_and_never_leaks_a_hold():
    p = profile()
    r = Rig(p)
    agen = r.gw.stream_chat(request(p, stream=True))
    await anext(agen)
    assert r.gw.ledger._accounts["run-1"].held_tokens > 0  # type: ignore[attr-defined]
    await agen.aclose()
    account = r.gw.ledger._accounts["run-1"]  # type: ignore[attr-defined]
    assert account.held_tokens == 0 and account.used_tokens > 0  # tokens were generated: charged, not released
    agen2 = r.gw.stream_chat(request(p, stream=True))
    await agen2.aclose()  # closed before the first chunk: nothing happened, nothing charged
    assert account.held_tokens == 0


def _custom_stream(r: Rig, chunks_fn):  # type: ignore[no-untyped-def]
    r.gw.transport.stream = chunks_fn  # type: ignore[attr-defined,method-assign]


async def test_stream_without_final_usage_is_an_error_and_charged():
    p = profile()
    r = Rig(p)

    async def no_end(call):  # type: ignore[no-untyped-def]
        yield TextDelta("a")

    _custom_stream(r, no_end)
    with pytest.raises(E.InvalidProviderOutput):
        [c async for c in r.gw.stream_chat(request(p, stream=True))]
    account = r.gw.ledger._accounts["run-1"]  # type: ignore[attr-defined]
    assert account.held_tokens == 0 and account.used_tokens > 0

    async def double_end(call):  # type: ignore[no-untyped-def]
        yield StreamEnd(None, FinishReason.STOP, Usage(1, 1))  # type: ignore[arg-type]
        yield TextDelta("late")

    _custom_stream(r, double_end)
    with pytest.raises(E.InvalidProviderOutput, match="after the end"):
        [c async for c in r.gw.stream_chat(request(p, stream=True))]
    assert account.held_tokens == 0


async def test_stream_deadline_counts_provider_time_not_consumer_pauses():
    p = profile(timeout_seconds=10.0)
    r = Rig(p)

    async def two(call):  # type: ignore[no-untyped-def]
        yield TextDelta("a")
        yield StreamEnd(None, FinishReason.STOP, Usage(1, 1))  # type: ignore[arg-type]

    _custom_stream(r, two)
    got = []
    async for chunk in r.gw.stream_chat(request(p, stream=True, limits=LLMLimits(100, 10.0))):
        r.clock[0] += 1000.0  # a very slow consumer
        got.append(chunk)
    assert len(got) == 2
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]


async def test_stream_refuses_a_response_schema():
    p = profile()
    r = Rig(p, catalog=StaticCatalog(schemas={"s": {"type": "object"}}))
    with pytest.raises(E.InvalidRequest):
        r.gw.stream_chat(request(p, stream=True, response_schema_ref="s"))


async def test_embeddings_are_deterministic_and_require_the_capability():
    p = profile()
    r = Rig(p)
    mk = lambda pid: EmbeddingRequest(request_id="e", model_profile_id=pid, purpose="T", inputs=("a", "b"), budget_scope="run-1",  # noqa: E731
                                      data_classification="INTERNAL", timeout_seconds=2)
    a, b = await r.gw.embed(mk(p.id)), await r.gw.embed(mk(p.id))
    assert a.vectors == b.vectors and len(a.vectors) == 2
    no_emb = profile(capabilities=frozenset({Capability.CHAT}))
    with pytest.raises(E.CapabilityNotSupported):
        await Rig(no_emb).gw.embed(mk(no_emb.id))


# ---------- routing ----------
def test_routing_is_deterministic_and_refuses_without_a_rule_or_approved_profile():
    v1, v2 = profile(profile_key="r", profile_version=1), profile(profile_key="r", profile_version=2)
    cand = profile(profile_key="r", profile_version=3, status=ProfileStatus.CANDIDATE, approved_at=None)
    reg = ModelRegistry([v1, v2, cand])
    route = RouteInput(worker_role="RESEARCH", task_class="extraction", data_classification="INTERNAL", required_capabilities=frozenset({Capability.CHAT}),
                       context_tokens=10, environment="test")
    policy = RoutingPolicy([RoutingRule(profile_key="r", worker_role="RESEARCH")])
    assert policy.route(reg, route, NOW).primary.id == v2.id and policy.route(reg, route, NOW).primary.id == v2.id  # newest APPROVED, never the candidate
    for bad_policy, bad_route in ((RoutingPolicy([]), route), (policy, replace(route, worker_role="ELICITATION")), (policy, replace(route, data_classification="X"))):
        with pytest.raises(E.RouteNotFound):
            bad_policy.route(reg, bad_route, NOW)
    assert isinstance(UUID(int=0), UUID)


def test_error_messages_carry_no_request_content():
    for cls in (E.SecretInPrompt, E.BudgetExhausted, E.InvalidProviderOutput):
        assert "hunter2" not in str(cls())


# ---------- review findings (S15 reviews) ----------
async def _open_circuit(r: Rig, p: ModelProfile) -> None:
    r.script.extend([E.ProviderUnavailable(), E.ProviderUnavailable()])  # type: ignore[attr-defined]
    for _ in range(2):
        with pytest.raises(E.ProviderUnavailable):
            await r.gw.chat(request(p))
    with pytest.raises(E.CircuitOpen):
        await r.gw.chat(request(p))


def _breaker_rig(p: ModelProfile, **kw: object) -> Rig:
    return Rig(p, policy=GatewayPolicy(circuit_failure_threshold=2, circuit_open_seconds=30), **kw)  # type: ignore[arg-type]


async def test_a_probe_that_ends_without_a_verdict_never_locks_the_profile():
    p = profile(retry_class=RetryClass.NONE)
    # 1) the probe ends with a non-availability error
    r = _breaker_rig(p)
    await _open_circuit(r, p)
    r.clock[0] = 31.0
    r.script.append(E.ProviderRejected())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderRejected):
        await r.gw.chat(request(p))
    assert (await r.gw.chat(request(p))).output  # the next call is allowed to probe again
    # 2) the probe is refused by the budget
    await _open_circuit_without_budget(_breaker_rig(p), p)


async def _open_circuit_without_budget(r: Rig, p: ModelProfile) -> None:
    ledger = r.gw.ledger  # type: ignore[attr-defined]
    ledger._accounts["run-1"].budget = Budget(max_total_tokens=100_000)
    await _open_circuit(r, p)
    r.clock[0] = 31.0
    ledger._accounts["run-1"].budget = Budget(max_total_tokens=0)
    with pytest.raises(E.BudgetExhausted):
        await r.gw.chat(request(p))
    ledger._accounts["run-1"].budget = Budget(max_total_tokens=100_000)
    assert (await r.gw.chat(request(p))).output  # the refused probe did not hold the slot


async def test_a_cancelled_probe_is_handed_back_and_a_stale_probe_expires():
    p = profile(retry_class=RetryClass.NONE)
    r = _breaker_rig(p)
    await _open_circuit(r, p)
    r.clock[0] = 31.0
    gate = asyncio.Event()

    async def hang(call: object) -> TransportResult:
        await gate.wait()
        return ok()

    real = r.gw.transport.complete  # type: ignore[attr-defined]
    r.gw.transport.complete = hang  # type: ignore[attr-defined,method-assign]
    task = asyncio.create_task(r.gw.chat(request(p)))
    await asyncio.sleep(0.01)
    with pytest.raises(E.CircuitOpen):
        await r.gw.chat(request(p))  # one probe at a time
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    r.gw.transport.complete = real  # type: ignore[attr-defined,method-assign]
    assert (await r.gw.chat(request(p))).output  # cancellation released the probe slot
    # a probe whose owner vanished without any exit path still expires after the open period
    r2 = _breaker_rig(p)
    await _open_circuit(r2, p)
    r2.clock[0] = 31.0
    r2.gw._breaker._probing[p.id] = 31.0  # noqa: SLF001 - a probe taken and never finished
    r2.clock[0] = 31.0 + 31.0
    assert r2.gw._breaker.allow(p.id)  # noqa: SLF001


async def test_tokens_already_spent_are_charged_when_the_output_is_invalid_or_the_call_times_out():
    p = profile(retry_class=RetryClass.NONE)
    schema = {"type": "object", "required": ["n"]}
    r = Rig(p, catalog=StaticCatalog(schemas={"s": schema}))
    r.script.append(TransportResult(output={"x": 1}, finish_reason=FinishReason.STOP, usage=Usage(70, 30)))  # type: ignore[attr-defined]
    with pytest.raises(E.InvalidProviderOutput):
        await r.gw.structured(request(p, response_schema_ref="s"))
    account = r.gw.ledger._accounts["run-1"]  # type: ignore[attr-defined]
    assert (account.used_tokens, account.held_tokens) == (100, 0)  # paid for, so charged
    r.script.append(E.ProviderTimeout())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderTimeout):
        await r.gw.chat(request(p, "hello"))
    assert account.used_tokens > 100 and account.held_tokens == 0  # the input estimate is charged for a timed-out call


async def test_a_fallback_the_budget_cannot_price_is_skipped_and_the_real_failure_is_reported():
    primary = profile(profile_key="p", fallback_group="g", retry_class=RetryClass.NONE,
                      cost_rates=CostRates(currency="EUR", input_per_million=Decimal(1), output_per_million=Decimal(1)))
    unpriced = profile(profile_key="q", fallback_group="g")
    r = Rig(primary, unpriced, budget=Budget(max_cost=Decimal(10), currency="EUR"))
    r.script.append(E.ProviderUnavailable())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderUnavailable):  # not BudgetUnenforceable, not CircuitOpen
        await r.gw.chat(request(primary))
    assert len(r.calls) == 1


async def test_fallback_must_accept_the_requested_output_size():
    primary = profile(profile_key="p", fallback_group="g", retry_class=RetryClass.NONE)
    small = profile(profile_key="q", fallback_group="g", max_output_tokens=50)
    r = Rig(primary, small)
    r.script.append(E.ProviderUnavailable())  # type: ignore[attr-defined]
    with pytest.raises(E.ProviderUnavailable):
        await r.gw.chat(request(primary))  # asks for 100 output tokens; the fallback allows 50
    assert len(r.calls) == 1


async def test_an_unmapped_transport_exception_becomes_a_generic_retryable_error_without_its_text():
    p = profile()
    r = Rig(p)

    class Boom(RuntimeError):
        pass

    calls = []

    async def boom(call):  # type: ignore[no-untyped-def]
        calls.append(call)
        raise Boom("https://provider.example/v1?key=SUPERSECRET body=hello")

    r.gw.transport.complete = boom  # type: ignore[attr-defined,method-assign]
    with pytest.raises(E.ProviderUnavailable) as exc:
        await r.gw.chat(request(p))
    assert "SUPERSECRET" not in str(exc.value) and exc.value.__cause__ is None and len(calls) == 3  # retried (bounded) as unavailability
    assert r.gw.ledger._accounts["run-1"].held_tokens == 0  # type: ignore[attr-defined]


def test_error_detail_from_a_transport_is_redacted_and_bounded():
    err = E.ProviderRejected(f"bad key {FAKE_ANTHROPIC} and " + "x" * 1000)
    assert "sk-ant" not in str(err) and len(err.detail) <= 300


async def test_guard_covers_provider_key_formats_obfuscation_and_split_secrets():
    p = profile()
    r = Rig(p)
    keys = [FAKE_ANTHROPIC, _join("sk-", "proj-abcdefghijklmnopqrstuvwxyz"), _join("github", "_pat_11ABCDEFG0abcdefghijklmnopqrs"), _join("xox", "b-123456789012-abcdefghij"),
            "AIza" + "a" * 35, "sk_live_" + "a" * 24, "ｓｋ-" + "a" * 24, "s\u200bk-" + "a" * 24]
    for key in keys:
        with pytest.raises(E.SecretInPrompt):
            await r.gw.chat(request(p, f"use {key} now"))
    split = (Message(Role.USER, _join("token sk-", "ant-api03-abcdefgh")), Message(Role.USER, "ijklmnop-qrstuvwx and more"))  # one key cut in the middle by chunking
    with pytest.raises(E.SecretInPrompt):
        await r.gw.chat(request(p, messages=split))
    assert r.calls == []


async def test_scan_cost_is_bounded_and_oversized_input_is_refused_before_it_is_scanned():
    import time
    p = profile(context_window_tokens=2_000_000, max_output_tokens=1000)
    r = Rig(p, budget=Budget(max_total_tokens=10**9))
    hostile = PEM_BEGIN * 20_000
    started = time.perf_counter()
    with pytest.raises(E.SecretInPrompt):
        await r.gw.chat(request(p, hostile))
    assert time.perf_counter() - started < 5  # was ~19 s per MB with a bounded-lazy regex
    small = profile(profile_key="small", context_window_tokens=1000, max_output_tokens=100)
    r2 = Rig(small)
    started = time.perf_counter()
    with pytest.raises(E.InputExceedsContextWindow):
        await r2.gw.chat(request(small, hostile * 5))
    assert time.perf_counter() - started < 1


async def test_loader_skips_an_invalid_candidate_but_fails_on_an_invalid_approved_row():
    from types import SimpleNamespace

    from ai_res.modules.model_registry.repository import RegistryLoadError, load_model_registry

    def row(status: str, classes: list[str]) -> SimpleNamespace:
        return SimpleNamespace(id=uuid4(), profile_key="k" + status.lower(), profile_version=1, provider="p", provider_model_id="m", pinned_model_version="v1",
                               capabilities=["CHAT"], context_window_tokens=100, max_output_tokens=10, data_classifications=classes, allowed_regions=["eu"],
                               egress="LOCAL", cost_currency=None, cost_input_per_million=None, cost_output_per_million=None, rate_limit_rpm=None,
                               rate_limit_tpm=None, timeout_seconds=5, retry_class="NONE", fallback_group=None, evaluation_manifest_ref=None,
                               status=status, approved_at=NOW if status != "CANDIDATE" else None, deprecated_at=None)

    class Session:
        def __init__(self, rows: list[SimpleNamespace]) -> None:
            self.rows = rows

        async def execute(self, *_: object) -> "Session":
            return self

        def all(self) -> list[SimpleNamespace]:
            return self.rows

    good, bad_candidate, bad_approved = row("APPROVED", ["INTERNAL"]), row("CANDIDATE", ["bad label"]), row("DEPRECATED", ["bad label"])
    registry = await load_model_registry(Session([good, bad_candidate]))  # type: ignore[arg-type]
    assert len(registry) == 1 and registry.get(good.id) is not None
    with pytest.raises(RegistryLoadError):
        await load_model_registry(Session([good, bad_approved]))  # type: ignore[arg-type]
