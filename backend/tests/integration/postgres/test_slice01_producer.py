"""Actual PostgreSQL approved-probe checks before reserve/ARM/HTTP and on return.

Uses synthetic MFA and disposable PG. Authentication, policy, registry, control
queries and the file ledger are real. Existing fixture TCP is plaintext (the
owner fixture's explicit engine adapter); TLS is not evidence from these tests.
Only probe HTTP uses an in-memory MockTransport. No external request is made.
"""
import copy
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from scripts.slice01 import owner, producer
from scripts.slice01.common import canonical, digest, messages, upstream_body, write_new
from scripts.slice01.ledger import SliceLedger
from scripts.slice01.relay import canonical_body

from ai_res.modules.model_registry.admission import ModelAdmissionGuard

from .test_model_admission import expected_for, install_generation
from .test_model_registry import add_profile, approve
from .test_slice01_owner import composed  # noqa: F401 -- pytest fixture imported explicitly

pytestmark = pytest.mark.postgres


@pytest.fixture
async def probe_case(composed, tmp_path, monkeypatch):  # noqa: F811 -- imported pytest fixture
    world = composed.world
    with world.iam.pg.connect() as connection:
        profile_id = add_profile(connection, key="slice-probe-fixture", provider="deepseek", provider_model_id="deepseek-flash",
            identity_mode="FLASH_OBSERVED", pinned_model_version=None, capabilities=["CHAT"], retry_class="NONE",
            context_window_tokens=8192, max_output_tokens=2048, allowed_regions=["cn"],
            cost_currency="USD", cost_input_per_million=Decimal("0.30"), cost_output_per_million=Decimal("1.20"))
        approve(connection, profile_id)
        snapshot, immutable = connection.execute(
            "SELECT to_jsonb(p)::text,((to_jsonb(p)-'status'-'approved_at'-'approved_by'-'deprecated_at')::text) "
            "FROM platform.model_profiles p WHERE id=%s", [profile_id]).fetchone()
    expected = expected_for(profile_id)
    install_generation(world.iam.pg, expected)
    plan = copy.deepcopy(composed.plan)
    plan.update({"profileId": str(profile_id), "profileStatus": "APPROVED", "admissionGeneration": 2, "experimentVersion": "2",
                 "profileSnapshot": snapshot, "immutableProfileSha256": digest(immutable.encode())})
    plan["managedVersions"] = replace(expected.managed_versions, config_sha256="c" * 64).to_dict()
    plan["phases"] = {"bootstrap": "synthetic-approved-probe", "run": "synthetic-approved-run"}
    policy_path = owner.PLAN / "policy.json"
    policy = json.loads(policy_path.read_bytes())
    policy["actions"]["slice01.invoke"] = {"resourceType": "SLICE01_REQUEST", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
        "requiresMfa": True, "humanOnly": True, "auditAllow": True}
    policy_path.unlink()
    write_new(policy_path, policy)
    plan["policySha256"] = digest(policy_path.read_bytes())
    body = canonical_body(canonical(upstream_body(messages(plan, "bootstrap"))))
    plan["requests"] = {plan["phases"]["bootstrap"]: {"bodySha256": digest(body), "payloadBytes": len(body)}}
    plan["manifestSha256"] = digest(canonical({key: value for key, value in plan.items() if key != "manifestSha256"}))
    wallet_dir, results = tmp_path / "probe-wallet", tmp_path / "probe-results"
    wallet_dir.mkdir(mode=0o700)
    results.mkdir(mode=0o700)
    wallet = wallet_dir / "ledger.jsonl"
    SliceLedger.initialize(wallet, manifest_sha256=plan["manifestSha256"], requests=plan["requests"])
    original = wallet.read_bytes()
    virtual_key = tmp_path / "synthetic-virtual-key"
    virtual_key.write_text("synthetic-fixture-only")
    virtual_key.chmod(0o600)
    original_read = producer.read_owned
    actual_client = httpx.AsyncClient
    events = {"reserve": 0, "arm": 0, "http": 0}
    case = SimpleNamespace(world=world, profile_id=profile_id, expected=expected, plan=plan, wallet=wallet,
                           original=original, results=results, events=events, block_on_response=False, ledger=None)

    class WatchedLedger(SliceLedger):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            case.ledger = self

        async def reserve(self, *args, **kwargs):
            events["reserve"] += 1
            return await super().reserve(*args, **kwargs)

        async def arm(self, *args, **kwargs):
            events["arm"] += 1
            return await super().arm(*args, **kwargs)

    def read(path, **kwargs):
        mounted = {Path("/worker-contract.json"): owner.CONTRACT, Path("/run/secrets/owner_session.json"): owner.SESSION,
                   Path("/run/secrets/bifrost_virtual_key"): virtual_key}
        return original_read(mounted.get(path, path), **kwargs)

    async def upstream(request):
        events["http"] += 1
        assert case.block_on_response, "Negative preflight must never reach even the isolated HTTP fixture"
        request_ref = plan["phases"]["bootstrap"]
        reservation = await case.ledger.claim(request_ref, plan["requests"][request_ref]["bodySha256"])
        await case.ledger.settle_usage(reservation, input_tokens=10, output_tokens=1)
        world.sql("UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=%s", profile_id)
        return httpx.Response(200, json={"id": "synthetic-provider-ref", "model": "DeepSeek-V4.1-Flash-0000",
            "system_fingerprint": "synthetic-fingerprint", "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            "extra_fields": {"routing_info": {"provider": "deepseek", "model": "deepseek-flash", "requested_model": "deepseek-flash"}}})

    monkeypatch.setattr(producer, "PROFILE_ID", profile_id)
    monkeypatch.setattr(producer, "ORGANIZATION_ID", world.iam.org_a)
    monkeypatch.setattr(producer, "OWNER_ID", world.iam.user_a)
    monkeypatch.setattr(producer, "PLAN", owner.PLAN)
    monkeypatch.setattr(producer, "RESULTS", results)
    monkeypatch.setattr(producer, "WALLET", wallet)
    monkeypatch.setattr(producer, "load_plan", lambda directory: copy.deepcopy(plan))
    monkeypatch.setattr(producer, "load_settings", owner.load_settings)
    monkeypatch.setattr(producer, "create_runtime_engine", owner.create_runtime_engine)
    monkeypatch.setattr(producer, "SliceLedger", WatchedLedger)
    monkeypatch.setattr(producer, "read_owned", read)
    monkeypatch.setattr(producer.httpx, "AsyncClient", lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(upstream)))
    return case


@pytest.mark.parametrize("phase", ["bootstrap", "preflight"])
@pytest.mark.parametrize("changed", ["blocked", "pending", "generation"])
async def test_live_control_refusal_prevents_reserve_arm_and_probe_http(probe_case, phase, changed):
    case = probe_case
    if changed == "blocked":
        case.world.sql("UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=%s", case.profile_id)
    elif changed == "pending":
        await ModelAdmissionGuard(case.world.factory).begin(case.profile_id, case.expected.managed_versions, request_ref="synthetic-existing-inflight")
    else:
        install_generation(case.world.iam.pg, replace(case.expected, admission_generation=2))
    with pytest.raises(ValueError, match="PROBE_ADMISSION_NOT_READY"):
        await producer.execute(phase)
    assert case.events == {"reserve": 0, "arm": 0, "http": 0}
    assert case.wallet.read_bytes() == case.original and not list(case.results.iterdir())


async def test_healthy_approved_control_allows_readonly_preflight_without_minting_admission(probe_case):
    case = probe_case
    assert (await producer.execute("preflight"))["providerCalls"] == 0
    assert case.events == {"reserve": 0, "arm": 0, "http": 0}
    assert case.world.sql("SELECT count(*) FROM platform.model_admission_calls WHERE profile_id=%s", case.profile_id) == [(0,)]


async def test_postresponse_control_block_withholds_probe_evidence_but_preserves_known_charge(probe_case):
    case = probe_case
    case.block_on_response = True
    with pytest.raises(ValueError, match="PROBE_ADMISSION_NOT_READY"):
        await producer.execute("bootstrap")
    assert case.events == {"reserve": 1, "arm": 1, "http": 1}
    balance = await case.ledger.balance()
    assert balance.used_or_reserved == Decimal("0.0000042") and not balance.pending and not balance.blocked
    assert (case.results / "bootstrap-quarantine-synthetic-approved-probe.json").is_file()
    assert not (case.results / "expectation.json").exists() and not (case.results / "bootstrap.json").exists()
    assert case.world.sql("SELECT count(*) FROM platform.model_admission_calls WHERE profile_id=%s", case.profile_id) == [(0,)]
