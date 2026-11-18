"""Runs inside an isolated fixture caller. All approvals/HTTP usage are synthetic."""
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
from scripts.slice01.common import canonical, load_plan, messages, native_body, read_owned, source_from_plan
from scripts.slice01.ledger import SliceLedger
from scripts.slice01.producer import CapturingTransport, capture_and_validate
from scripts.slice01.requirements import ExperimentIds

from ai_res.llm.observed_identity import ManagedVersions
from ai_res.llm.registry import CostRates, Egress, ModelProfile, ProfileIdentityMode, ProfileStatus, RetryClass
from ai_res.llm.transport import TransportCall
from ai_res.llm.types import Capability
from ai_res.worker_contracts import WorkerContracts


async def run():
    plan = load_plan(Path("/config"))
    assert plan["mode"] == "fixture"
    key = "sk-bf-" + read_owned(Path("/run/secrets/bifrost_virtual_key")).decode().strip()
    ledger = SliceLedger(Path("/wallet/ledger.jsonl"), manifest_sha256=plan["manifestSha256"])
    for phase in ("bootstrap", "run"):
        ref = plan["phases"][phase]
        await ledger.reserve(ref, tokens=10, cost=Decimal(0), currency="USD")
        await ledger.arm(ref)
        if phase == "bootstrap":
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                r = await client.post("http://bifrost-poc:8080/v1/chat/completions", content=canonical(native_body(messages(plan, phase))),
                    headers={"x-bf-vk": key, "content-type": "application/json"})
                assert r.status_code == 200
                assert r.json()["choices"][0]["message"]["content"] == "OK"
        else:
            # Test fixture ONLY, never a clone used for live candidate dispatch.
            profile = ModelProfile(id=UUID(plan["profileId"]), profile_key="fixture-slice", profile_version=1,
                provider="deepseek", provider_model_id="deepseek-flash", pinned_model_version=None,
                identity_mode=ProfileIdentityMode.FLASH_OBSERVED, capabilities=frozenset({Capability.CHAT}),
                context_window_tokens=8192, max_output_tokens=2048, data_classifications=frozenset({"INTERNAL"}),
                allowed_regions=frozenset({"cn"}), egress=Egress.EXTERNAL, timeout_seconds=30, retry_class=RetryClass.NONE,
                status=ProfileStatus.APPROVED, approved_at=datetime.now(UTC),
                cost_rates=CostRates(currency="USD", input_per_million=Decimal("0.30"), output_per_million=Decimal("1.20")))
            async with CapturingTransport(virtual_key=key, allow_observed=True, request_ref=ref, results_dir=Path("/results")) as transport:
                response = await transport.complete(TransportCall(profile=profile, request_id=ref, messages=messages(plan, phase),
                    max_output_tokens=2048, timeout_seconds=30, managed_versions=ManagedVersions.from_dict(plan["managedVersions"])))
                # TransportResult is normalized, but the public validator expects LLMResponse.
                from ai_res.llm.types import LLMResponse, ModelIdentity
                identity = ModelIdentity(profile.id, profile.profile_key, 1, "deepseek", "deepseek-flash", None,
                                         observation=response.observation)
                normalized = LLMResponse(identity=identity, output=response.output, finish_reason=response.finish_reason,
                    usage=response.usage, latency_ms=0, provider_request_ref=response.provider_request_ref, tool_calls=response.tool_calls)
                assert transport.receipt is not None and transport.capture_error is None
                capture_and_validate(normalized, source_from_plan(plan),
                    ExperimentIds(UUID(plan["experiment"]["workerRunId"]), UUID(plan["experiment"]["taskId"])),
                    WorkerContracts.from_file(Path("/worker-contract.json")), request_ref=ref,
                    capture=transport.receipt, balance=await ledger.balance(), confirmed=True, directory=Path("/results"))
    balance = await ledger.balance()
    assert balance.attempts == 2 and not balance.pending and not balance.blocked
    print(canonical({"nativeFixture": "PASS", "attempts": 2, "providerCalls": 0}).decode())


asyncio.run(run())
