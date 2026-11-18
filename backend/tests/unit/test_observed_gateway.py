"""Observed product path with synthetic HTTP/authority only; no model approval."""
import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from ai_res.llm.adapters.bifrost import BifrostSettings, BifrostTransport
from ai_res.llm.admission import ObservedAdmissionCall
from ai_res.llm.budget import Budget, InMemoryBudgetLedger
from ai_res.llm.errors import GatewayUnconfigured, ModelProfileNotApproved, ProviderTimeout, ProviderUnavailable
from ai_res.llm.factory import build_llm_gateway
from ai_res.llm.gateway import GovernedLLMGateway
from ai_res.llm.observed_identity import FingerprintPresence, IdentityObservation, ManagedVersions
from ai_res.llm.port import UnconfiguredLLMGateway
from ai_res.llm.registry import Egress, ModelProfile, ModelRegistry, ProfileIdentityMode, ProfileStatus, RetryClass
from ai_res.llm.types import Capability, LLMLimits, LLMRequest, Message, Role, StaticCatalog, StreamEnd, TextDelta
from ai_res.platform.config import ConfigError, Settings

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROFILE = dict(id=UUID(int=110), profile_key="observed-fixture", profile_version=1,
               provider="deepseek", provider_model_id="deepseek-flash", pinned_model_version=None,
               identity_mode=ProfileIdentityMode.FLASH_OBSERVED,
               capabilities=frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT, Capability.TOOL_CALLING, Capability.STREAMING}),
               context_window_tokens=4096, max_output_tokens=1024, data_classifications=frozenset({"PUBLIC"}),
               allowed_regions=frozenset({"test"}), egress=Egress.EXTERNAL, timeout_seconds=5,
               retry_class=RetryClass.NONE, status=ProfileStatus.APPROVED, approved_at=NOW)


def profile(**changes):
    return ModelProfile(**(PROFILE | changes))


def request(p, **changes):
    return LLMRequest(**(dict(request_id="observed-1", model_profile_id=p.id, purpose="TEST",
                             messages=(Message(Role.USER, "hello"),), budget_scope="test-run", data_classification="PUBLIC",
                             limits=LLMLimits(64, 2)) | changes))


def frame(**changes):
    return dict(id="synthetic-response", model="deepseek-v4-flash", system_fingerprint="synthetic-fingerprint",
                choices=[dict(index=0, finish_reason="stop", message=dict(content="answer"))],
                usage=dict(prompt_tokens=7, completion_tokens=3, total_tokens=10),
                extra_fields=dict(routing_info=dict(provider="deepseek", model="deepseek-flash"))) | changes


class Authority:
    def __init__(self, *, deny_begin=False, deny_finalize=False):
        self.calls = []
        self.deny_begin, self.deny_finalize = deny_begin, deny_finalize
        self.blocked = False
        self.started = asyncio.Event()

    async def begin(self, p, req):
        self.calls.append("begin")
        if self.deny_begin or self.blocked:
            raise ModelProfileNotApproved()
        self.started.set()
        versions = ManagedVersions("a" * 40, p.id, p.profile_version, "b" * 64, "c" * 64, None)
        return ObservedAdmissionCall(versions, object())

    async def finalize(self, call, observation):
        self.calls.append(observation)
        if self.deny_finalize:
            raise ModelProfileNotApproved(possibly_billed=True)
        if (not isinstance(observation, IdentityObservation) or observation.identity.response_model_id != "deepseek-v4-flash"
                or observation.identity.fingerprint.presence is not FingerprintPresence.VALUE
                or observation.identity.fingerprint.value != "synthetic-fingerprint"):
            self.blocked = True
            raise ModelProfileNotApproved(possibly_billed=True)


def gateway(p, adapter, admission):
    ledger = InMemoryBudgetLedger()
    ledger.establish("test-run", Budget(max_total_tokens=10_000))
    return GovernedLLMGateway(registry=lambda: ModelRegistry([p]), transport=adapter, ledger=ledger,
                              admission=admission), ledger


def test_null_pin_is_only_explicit_flash_and_never_enables_embedding_or_fallback():
    p = profile()
    assert p.pinned_model_version is None
    for changes in (dict(identity_mode=ProfileIdentityMode.IMMUTABLE), dict(provider_model_id="deepseek-v4-pro"),
                    dict(pinned_model_version="deepseek-flash"), dict(fallback_group="other"),
                    dict(capabilities=frozenset({Capability.EMBEDDING})), dict(retry_class=RetryClass.BOUNDED)):
        with pytest.raises(ValueError):
            profile(**changes)


async def test_default_or_denied_authority_never_dispatches():
    p = profile()
    sent = []
    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(lambda r: sent.append(r))) as adapter:
        for authority, error in ((None, GatewayUnconfigured), (Authority(deny_begin=True), ModelProfileNotApproved)):
            gw, _ = gateway(p, adapter, authority)
            with pytest.raises(error):
                await gw.chat(request(p))
    assert sent == []


async def test_complete_keeps_actual_observation_and_finalizes_before_return():
    p, authority, sent = profile(), Authority(), []

    def handle(r):
        sent.append(r)
        assert authority.calls == ["begin"]
        return httpx.Response(200, json=frame())

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        gw, ledger = gateway(p, adapter, authority)
        result = await gw.chat(request(p))
    assert result.identity.pinned_model_version is None
    assert result.identity.observation.identity.response_model_id == "deepseek-v4-flash"
    assert result.identity.observation is authority.calls[-1]
    assert result.output == "answer" and ledger.usage("test-run")[0] == 10
    assert json.loads(sent[0].content)["fallbacks"] == []


async def test_finalize_failure_discards_paid_result_without_retry():
    p, authority, sent = profile(), Authority(deny_finalize=True), []

    def handle(r):
        sent.append(r)
        return httpx.Response(200, json=frame())

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        gw, ledger = gateway(p, adapter, authority)
        with pytest.raises(ModelProfileNotApproved):
            await gw.chat(request(p))
    assert len(sent) == 1 and ledger.usage("test-run")[0] >= 10


async def test_observed_stream_waits_for_terminal_validation_and_durable_finalize():
    p, authority = profile(), Authority()
    gate = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ("data: " + json.dumps(frame(usage=None, choices=[dict(index=0, delta=dict(content="first"), finish_reason=None)])) + "\n\n").encode()
            await gate.wait()
            yield ("data: " + json.dumps(frame(choices=[dict(index=0, delta={}, finish_reason="stop")])) + "\n\ndata: [DONE]\n\n").encode()

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Stream(),
                                                                                           headers={"content-type": "text/event-stream"}))) as adapter:
        gw, _ = gateway(p, adapter, authority)
        iterator = gw.stream_chat(request(p, stream=True))
        first = asyncio.create_task(anext(iterator))
        await authority.started.wait()
        await asyncio.sleep(0)
        assert not first.done()
        gate.set()
        assert await first == TextDelta("first")
        assert len(authority.calls) == 2
        assert isinstance(await anext(iterator), StreamEnd)
        await iterator.aclose()


@pytest.mark.parametrize("mode", ["JSON", "TOOL"])
async def test_native_schema_and_tools_remain_governed(mode):
    p, authority = profile(), Authority()
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
    tools = ({"type": "function", "function": {"name": "lookup", "parameters": schema}},)
    message = dict(content='{"answer":"ok"}') if mode == "JSON" else dict(content=None, tool_calls=[
        dict(id="tool-1", type="function", function=dict(name="lookup", arguments='{"answer":"ok"}'))])
    payload = frame(choices=[dict(index=0, finish_reason="stop" if mode == "JSON" else "tool_calls", message=message)])
    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as adapter:
        gw, _ = gateway(p, adapter, authority)
        gw._catalog = StaticCatalog(schemas={"test-schema": schema}, tools={"test-tools": tools})
        if mode == "JSON":
            result = await gw.structured(request(p, response_schema_ref="test-schema"))
            assert result.output == {"answer": "ok"}
        else:
            result = await gw.chat(request(p, tool_definitions_ref="test-tools"))
            assert result.tool_calls[0].arguments == {"answer": "ok"}
    assert result.identity.pinned_model_version is None and len(authority.calls) == 2


@pytest.mark.parametrize("change", ["missing-id", "missing-model", "missing-routing", "missing-fingerprint", "null-fingerprint", "pro", "drift"])
async def test_missing_or_unexpected_identity_blocks_result_and_next_dispatch(change):
    p, authority, sent = profile(), Authority(), []
    payload = frame()
    if change.startswith("missing-"):
        payload.pop({"id": "id", "model": "model", "routing": "extra_fields", "fingerprint": "system_fingerprint"}[change[8:]])
    elif change == "null-fingerprint":
        payload["system_fingerprint"] = None
    elif change == "pro":
        payload["model"] = "deepseek-v4-pro"
    else:
        payload["system_fingerprint"] = "changed-fingerprint"

    def handle(r):
        sent.append(r)
        return httpx.Response(200, json=payload)

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        gw, _ = gateway(p, adapter, authority)
        with pytest.raises(ModelProfileNotApproved):
            await gw.chat(request(p))
        with pytest.raises(ModelProfileNotApproved):
            await gw.chat(request(p, request_id="observed-2"))
    assert len(sent) == 1 and authority.blocked


@pytest.mark.parametrize("failure", ["cancel", "timeout", "unavailable"])
async def test_unknown_outcome_is_not_finalized_or_retried_and_retains_worst_case_charge(failure):
    p, authority, sent = profile(timeout_seconds=0.02), Authority(), []
    entered = asyncio.Event()

    async def handle(r):
        sent.append(r)
        entered.set()
        if failure == "unavailable":
            return httpx.Response(503)
        await asyncio.Event().wait()

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        gw, ledger = gateway(p, adapter, authority)
        task = asyncio.create_task(gw.chat(request(p)))
        await entered.wait()
        if failure == "cancel":
            task.cancel()
        error = {"cancel": asyncio.CancelledError, "timeout": ProviderTimeout, "unavailable": ProviderUnavailable}[failure]
        with pytest.raises(error):
            await task
    assert len(sent) == 1 and authority.calls == ["begin"]
    assert ledger.usage("test-run")[0] == 66


@pytest.mark.parametrize("failure", ["cancel", "finalize", "late-drift", "reverse-drift", "reverse-ref", "bound"])
async def test_failed_observed_stream_never_publishes_buffered_output(failure):
    p, authority, emitted = profile(), Authority(deny_finalize=failure == "finalize"), []
    entered = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            first = frame(usage=None, choices=[dict(index=0, delta=dict(content="first"), finish_reason=None)])
            if failure == "reverse-drift":
                first["system_fingerprint"] = "changed-fingerprint"
            if failure == "reverse-ref":
                first["id"] = "other-response"
            yield ("data: " + json.dumps(first) + "\n\n").encode()
            entered.set()
            if failure == "cancel":
                await asyncio.Event().wait()
            end = frame(choices=[dict(index=0, delta={}, finish_reason="stop")])
            if failure == "late-drift":
                end["system_fingerprint"] = "changed-fingerprint"
            yield ("data: " + json.dumps(end) + "\n\ndata: [DONE]\n\n").encode()

    settings = BifrostSettings(max_stream_bytes=600) if failure == "bound" else BifrostSettings()
    async with BifrostTransport(settings, virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Stream(),
                                                                                           headers={"content-type": "text/event-stream"}))) as adapter:
        gw, ledger = gateway(p, adapter, authority)

        async def collect():
            async for chunk in gw.stream_chat(request(p, stream=True)):
                emitted.append(chunk)

        task = asyncio.create_task(collect())
        await entered.wait()
        if failure == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ModelProfileNotApproved):
            await task
        if failure in {"late-drift", "reverse-drift", "reverse-ref", "bound"}:
            assert authority.blocked
            with pytest.raises(ModelProfileNotApproved):
                await gw.chat(request(p, request_id="after-failed-stream"))
    assert emitted == []
    assert ledger.usage("test-run")[0] == (10 if failure == "finalize" else 66)
    assert len(authority.calls) == (1 if failure == "cancel" else 2 if failure == "finalize" else 3)


async def test_observed_transport_is_explicit_and_default_factory_stays_disabled():
    p, sent = profile(), []
    versions = ManagedVersions("a" * 40, p.id, 1, "b" * 64, "c" * 64, None)
    from ai_res.llm.transport import TransportCall
    async with BifrostTransport(virtual_key="synthetic-vk", http_transport=httpx.MockTransport(lambda r: sent.append(r))) as adapter:
        with pytest.raises(GatewayUnconfigured):
            await adapter.complete(TransportCall(request_id="test", profile=p, messages=(Message(Role.USER, "test"),),
                                                 max_output_tokens=1, timeout_seconds=1, managed_versions=versions))
    assert sent == []
    assert isinstance(build_llm_gateway(Settings()), UnconfiguredLLMGateway)
    with pytest.raises(ConfigError):
        build_llm_gateway(Settings(llm_gateway="bifrost-observed"))


async def test_explicit_factory_composes_the_same_governed_path():
    p, authority = profile(), Authority()
    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=frame()))) as adapter:
        _, ledger = gateway(p, adapter, authority)
        gw = build_llm_gateway(Settings(llm_gateway="bifrost-observed"), registry=lambda: ModelRegistry([p]),
                               ledger=ledger, transport=adapter, admission=authority)
        assert (await gw.chat(request(p))).identity.observation is authority.calls[-1]


@pytest.mark.parametrize("change", ["profile", "reference"])
async def test_inconsistent_terminal_envelope_blocks_even_when_observation_is_approved(change):
    from dataclasses import replace

    from ai_res.llm.types import FinishReason, ModelIdentity, Usage

    p, authority, emitted = profile(), Authority(), []

    class Transport:
        max_stream_bytes = 65536
        conservative_usage_on_error = True

        async def stream(self, call):
            from ai_res.llm.observed_identity import extract_bifrost_observation

            observation = extract_bifrost_observation(frame(), managed_versions=call.managed_versions,
                observed_at=NOW, request_ref=call.request_id, request_model_id=p.provider_model_id)
            identity = ModelIdentity(p.id, p.profile_key, p.profile_version, p.provider, p.provider_model_id,
                                     None, observation=observation)
            if change == "profile":
                identity = replace(identity, profile_key="other-profile")
            yield TextDelta("unaccepted")
            yield StreamEnd(identity, FinishReason.STOP, Usage(7, 3),
                            "other-response" if change == "reference" else observation.provider_request_ref)

    gw, _ = gateway(p, Transport(), authority)
    with pytest.raises(ModelProfileNotApproved):
        async for chunk in gw.stream_chat(request(p, stream=True)):
            emitted.append(chunk)
    assert not emitted and authority.blocked and authority.calls[-1] == b""
