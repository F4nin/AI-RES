"""Product port -> real PG admission; HTTP/approvals are synthetic fixtures only."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm.adapters.bifrost import BifrostTransport
from ai_res.llm.budget import Budget, InMemoryBudgetLedger
from ai_res.llm.errors import ModelProfileNotApproved
from ai_res.llm.gateway import GovernedLLMGateway
from ai_res.llm.observed_identity import IdentityObservation
from ai_res.llm.types import LLMLimits, LLMRequest, Message, Role, StreamEnd
from ai_res.modules.model_registry.gateway_admission import ModelRegistryAdmission
from ai_res.modules.model_registry.repository import load_model_registry

from .test_model_admission import api_engine, counts, expected_for, guard, install_generation
from .test_model_registry import add_profile, approve

pytestmark = pytest.mark.postgres
__all__ = ["api_engine"]


def payload(expected, *, stream=False, fingerprint=None, reference="synthetic-response"):
    return {"id": reference, "model": expected.identity.response_model_id,
            "system_fingerprint": fingerprint or expected.identity.fingerprint.value,
            "extra_fields": {"routing_info": {"provider": "deepseek", "model": "deepseek-flash"}},
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            "choices": [{"index": 0, "finish_reason": "stop",
                         **({"delta": {"content": "synthetic-output"}} if stream else {"message": {"content": "synthetic-output"}})}]}


async def compose(pg, engine, adapter, *, authorize=None, versions=None):
    # Create immutable synthetic profile fields correctly from the start.
    with pg.connect() as c:
        profile_id = add_profile(c, key="product-observed", provider="deepseek", provider_model_id="deepseek-flash",
                                 identity_mode="FLASH_OBSERVED", pinned_model_version=None,
                                 capabilities=["CHAT", "STREAMING"], retry_class="NONE")
        approve(c, profile_id)
    expected = expected_for(profile_id)
    install_generation(pg, expected)
    async with UnitOfWork(create_session_factory(engine)) as uow:
        registry = await load_model_registry(uow.session)
    p = registry.get(expected.managed_versions.profile_id)

    async def allow(profile, request):
        return True  # TEST ONLY, real caller authority is injected separately

    ledger = InMemoryBudgetLedger()
    ledger.establish("synthetic-budget", Budget(max_total_tokens=10000))
    admission = ModelRegistryAdmission(guard(engine), authorize=authorize or allow,
                                       managed_versions=versions or (lambda p, r: expected.managed_versions))
    gw = GovernedLLMGateway(registry=lambda: registry, transport=adapter, ledger=ledger, admission=admission)
    req = LLMRequest(request_id="product-observed-1", model_profile_id=p.id, purpose="TEST",
                     messages=(Message(Role.USER, "synthetic-input"),), budget_scope="synthetic-budget",
                     data_classification="INTERNAL", limits=LLMLimits(64, 2))
    return expected, gw, req


@pytest.mark.parametrize("stream", [False, True])
async def test_real_admission_commits_before_dispatch_and_finalizes_before_publication(migrated, api_engine, stream):
    expected = None

    def handle(request):
        assert counts(migrated) == (1, 1)
        with migrated.connect() as c:
            assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("IN_FLIGHT",)
        data = payload(expected, stream=stream)
        if stream:
            return httpx.Response(200, content=("data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n").encode(),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=data)

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        expected, gw, req = await compose(migrated, api_engine, adapter)
        if stream:
            chunks = []
            async for chunk in gw.stream_chat(replace(req, stream=True)):
                assert counts(migrated) == (1, 2)
                chunks.append(chunk)
            identity = chunks[-1].identity
            assert isinstance(chunks[-1], StreamEnd)
        else:
            identity = (await gw.chat(req)).identity
    assert isinstance(identity.observation, IdentityObservation)
    with migrated.connect() as c:
        assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("VALIDATED",)
        assert c.execute("SELECT DISTINCT writer_role FROM platform.model_admission_audit").fetchall() == [("ai_res_api",)]


@pytest.mark.parametrize("change", ["late-drift", "reverse-drift", "reverse-reference"])
async def test_real_stream_inconsistency_blocks_next_dispatch_across_connections(migrated, api_engine, change):
    sent, emitted = [], []
    expected = None

    def handle(request):
        sent.append(request)
        first = payload(expected, stream=True,
                        fingerprint="other-fingerprint" if change == "reverse-drift" else None,
                        reference="other-response" if change == "reverse-reference" else "synthetic-response")
        first["usage"] = None
        first["choices"][0]["finish_reason"] = None
        end = payload(expected, stream=True, fingerprint="other-fingerprint" if change == "late-drift" else None)
        body = "".join("data: " + json.dumps(frame) + "\n\n" for frame in (first, end)) + "data: [DONE]\n\n"
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        expected, gw, req = await compose(migrated, api_engine, adapter)
        with pytest.raises(ModelProfileNotApproved):
            async for chunk in gw.stream_chat(replace(req, stream=True)):
                emitted.append(chunk)
        await api_engine.dispose()
        with pytest.raises(ModelProfileNotApproved):
            await gw.chat(replace(req, request_id="product-observed-2"))
    assert len(sent) == 1 and not emitted and counts(migrated) == (1, 2)
    with migrated.connect() as c:
        assert c.execute("SELECT blocked FROM platform.model_admission_controls").fetchone() == (True,)
        assert c.execute("SELECT status,observed_sha256 FROM platform.model_admission_calls").fetchone() == ("BLOCKED", None)


@pytest.mark.parametrize("change", ["revoke", "policy-outage", "generation", "audit-outage", "cancel"])
async def test_real_product_refuses_result_and_preserves_unresolved_receipt(migrated, api_engine, change):
    expected = None
    sent, emitted = [], []
    dispatched = asyncio.Event()
    allowed = True

    async def authorize(profile, request):
        if dispatched.is_set() and change == "policy-outage":
            raise RuntimeError("synthetic-private-policy-error")
        return allowed

    async def handle(request):
        nonlocal allowed
        sent.append(request)
        dispatched.set()
        if change == "revoke":
            allowed = False
        if change == "generation":
            install_generation(migrated, replace(expected, admission_generation=2))
        if change == "audit-outage":
            with migrated.connect() as c:
                c.execute("CREATE FUNCTION platform.fixture_fail_product_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                          "BEGIN RAISE EXCEPTION 'synthetic-private-audit-error'; END $$")
                c.execute("CREATE TRIGGER fixture_fail_product_audit BEFORE INSERT ON platform.model_admission_audit "
                          "FOR EACH ROW EXECUTE FUNCTION platform.fixture_fail_product_audit()")
        if change == "cancel":
            await asyncio.Event().wait()
        return httpx.Response(200, json=payload(expected))

    async with BifrostTransport(virtual_key="synthetic-vk", allow_observed=True,
                               http_transport=httpx.MockTransport(handle)) as adapter:
        expected, gw, req = await compose(migrated, api_engine, adapter, authorize=authorize)
        task = asyncio.create_task(gw.chat(req))
        await dispatched.wait()
        if change == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if change == "cancel" else ModelProfileNotApproved):
            emitted.append(await task)
        allowed = True
        await api_engine.dispose()
        with pytest.raises(ModelProfileNotApproved):
            await gw.chat(replace(req, request_id="product-observed-2"))
    assert len(sent) == 1 and not emitted and counts(migrated) == (1, 1)
    with migrated.connect() as c:
        assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("IN_FLIGHT",)
