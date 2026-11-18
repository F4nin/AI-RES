"""Real PG reserve/read orchestration with an explicit synthetic relay double.

This proves no Bifrost/provider/TLS behavior. The double alone claims/settles;
the runner is restricted to reserve and exact read. No real account is seeded.
"""
import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.llm.candidate_probe import CandidateProbeError, CandidateProbeEvidence, CandidateProbeUsage, ProbeOutcome
from ai_res.llm.observed_identity import FingerprintPresence, ObservedFingerprint, ObservedProviderIdentity
from ai_res.modules.model_registry.candidate_runner import (
    CandidateAccountingReader,
    CandidateRunDenied,
    CandidateRunManifest,
    CandidateRunner,
    JsonlCandidateEvidence,
)
from ai_res.modules.model_registry.poc_control import BODY_CODEC_VERSION, CandidateClaimRequest, CandidateControlDenied, CandidateSettlementRequest
from ai_res.platform.clock import utc_now

from .conftest import Pg
from .test_llm_poc_control import service
from .test_llm_poc_paid_ledger import PLAN, RESERVE, TARIFF, binding, ledger, seed_account
from .test_model_admission import api_engine as api_engine

pytestmark = pytest.mark.postgres


def manifest():
    return CandidateRunManifest("a" * 40, "b" * 64, "c" * 64, "d" * 64, None, "e" * 64, PLAN, TARIFF)


class Gate:
    async def validate(self, body, managed):
        pass  # Explicit offline fixture; does not simulate live authorization.


class RecordingBudget:
    def __init__(self, engine, account):
        self.real, self.tickets = ledger(engine, account), []

    async def reserve(self, request):
        ticket = await self.real.reserve(request)
        self.tickets.append(ticket)
        return ticket


class SyntheticRelayProbe:
    def __init__(self, engine, account, path, *, outcome="KNOWN", started=None, resume=None):
        self.engine, self.control, self.path = engine, service(engine, account), path
        self.outcome, self.started, self.resume, self.calls = outcome, started, resume, 0

    async def probe(self, body, *, timeout_seconds):
        self.calls += 1
        assert self.engine.pool.checkedout() == 0
        assert json.loads(self.path.read_text().splitlines()[-1])["kind"] == "INTENT"
        claim = await self.control.claim(CandidateClaimRequest(BODY_CODEC_VERSION, body.case_ref, body.body_sha256,
                                                               body.payload_bytes, body.stream, body.max_output_tokens))
        if self.started is not None:
            self.started.set()
            await self.resume.wait()
        if self.outcome == "PENDING":
            raise CandidateProbeError()
        request = (CandidateSettlementRequest(claim.attempt_id, body.body_sha256, "UNKNOWN", reason="TIMEOUT") if self.outcome == "UNKNOWN"
                   else CandidateSettlementRequest(claim.attempt_id, body.body_sha256, "KNOWN", 10, 257 if self.outcome == "OVERRUN" else 2,
                                                   "provider-fixture"))
        try:
            await self.control.settle(request)
        except CandidateControlDenied:
            raise CandidateProbeError() from None
        identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "fixture-flash",
                                             ObservedFingerprint(FingerprintPresence.ABSENT, None))
        return CandidateProbeEvidence(body.case_ref, body.body_sha256, utc_now(), ProbeOutcome.COMPLETE, identity,
                                      "provider-fixture", CandidateProbeUsage(10, 2), True)


def components(engine, account, path, **probe_kwargs):
    budget = RecordingBudget(engine, account)
    reader = CandidateAccountingReader(create_session_factory(engine), account)
    probe = SyntheticRelayProbe(engine, account, path, **probe_kwargs)
    return CandidateRunner(budget, reader, probe, Gate(), JsonlCandidateEvidence(path)), budget, reader, probe


async def test_real_reserve_precedes_probe_and_exact_settlement_is_read(migrated: Pg, api_engine: AsyncEngine, tmp_path):
    account = seed_account(migrated)
    path = tmp_path / "evidence.jsonl"
    runner, budget, reader, probe = components(api_engine, account, path)
    result = await runner.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    assert len(budget.tickets) == probe.calls == 1
    assert result.accounting.outcome == "KNOWN" and result.accounting.charged_cost < RESERVE
    assert (await reader.read(budget.tickets[0])) == result.accounting
    assert json.loads(path.read_text().splitlines()[-1])["accountingConfirmed"] is True
    async with UnitOfWork(create_session_factory(api_engine)) as uow:
        # Transaction-local account context was reset on pool return.
        assert (await uow.session.execute(text("SELECT count(*) FROM platform.llm_poc_attempts"))).scalar_one() == 0


@pytest.mark.parametrize("change", ["sequence", "body", "plan", "tariff", "other-account", "other-attempt"])
async def test_reader_never_substitutes_another_ticket_or_manifest(migrated: Pg, api_engine: AsyncEngine, change):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    bad = {"sequence": replace(ticket, sequence=2), "body": replace(ticket, binding=replace(ticket.binding, body_sha256="d" * 64)),
           "plan": replace(ticket, binding=replace(ticket.binding, plan_sha256="d" * 64)),
           "tariff": replace(ticket, binding=replace(ticket.binding, tariff_sha256="d" * 64)),
           "other-account": replace(ticket, account_id=uuid4()), "other-attempt": replace(ticket, attempt_id=uuid4())}[change]
    reader = CandidateAccountingReader(create_session_factory(api_engine), account)
    with pytest.raises(CandidateRunDenied, match="BINDING_MISMATCH"):
        await reader.read(bad)
    assert (await reader.read(ticket)).state == "RESERVED"


async def test_intent_write_failure_holds_reserved_attempt_after_new_connections(migrated: Pg, api_engine: AsyncEngine, tmp_path, monkeypatch):
    account = seed_account(migrated)
    path = tmp_path / "evidence.jsonl"
    runner, budget, reader, probe = components(api_engine, account, path)
    monkeypatch.setattr(runner._sink, "append", lambda record: (_ for _ in ()).throw(CandidateRunDenied("EVIDENCE_UNAVAILABLE")))
    with pytest.raises(CandidateRunDenied):
        await runner.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    await api_engine.dispose()
    assert probe.calls == 0 and len(budget.tickets) == 1
    assert (await reader.read(budget.tickets[0])).state == "RESERVED"
    assert (await ledger(api_engine, account).balance()).pending


@pytest.mark.parametrize("outcome", ["PENDING", "UNKNOWN", "OVERRUN"])
async def test_failed_or_unconfirmed_probe_never_fakes_accounting_or_refunds(migrated: Pg, api_engine: AsyncEngine, tmp_path, outcome):
    account = seed_account(migrated)
    runner, budget, reader, probe = components(api_engine, account, tmp_path / "evidence.jsonl", outcome=outcome)
    with pytest.raises(CandidateRunDenied):
        await runner.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    await api_engine.dispose()
    assert probe.calls == len(budget.tickets) == 1
    state = await reader.read(budget.tickets[0])
    expected = ("CLAIMED", None) if outcome == "PENDING" else ("SETTLED", outcome)
    assert (state.state, state.outcome) == expected
    balance = await ledger(api_engine, account).balance()
    assert balance.attempts == 1
    if outcome in {"PENDING", "UNKNOWN"}:
        assert balance.used_or_reserved >= RESERVE
    else:
        assert balance.blocked


async def test_pending_after_restart_prevents_a_new_probe(migrated: Pg, api_engine: AsyncEngine, tmp_path):
    account = seed_account(migrated)
    first, _, _, first_probe = components(api_engine, account, tmp_path / "first.jsonl", outcome="PENDING")
    with pytest.raises(CandidateRunDenied):
        await first.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    await api_engine.dispose()
    second, budget, _, probe = components(api_engine, account, tmp_path / "second.jsonl")
    with pytest.raises(CandidateRunDenied, match="BUDGET_DENIED"):
        await second.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    assert first_probe.calls == 1 and probe.calls == len(budget.tickets) == 0


async def test_two_invocations_cannot_probe_while_the_first_claim_is_pending(migrated: Pg, api_engine: AsyncEngine, tmp_path):
    account = seed_account(migrated)
    started, resume = asyncio.Event(), asyncio.Event()
    first, _, _, first_probe = components(api_engine, account, tmp_path / "first.jsonl", started=started, resume=resume)
    running = asyncio.create_task(first.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10))
    await asyncio.wait_for(started.wait(), 3)
    second, _, _, second_probe = components(api_engine, account, tmp_path / "second.jsonl")
    try:
        with pytest.raises(CandidateRunDenied, match="BUDGET_DENIED"):
            await second.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    finally:
        resume.set()
        await running
    assert first_probe.calls == 1 and second_probe.calls == 0


async def test_missing_account_cannot_be_created_by_runner(migrated: Pg, api_engine: AsyncEngine, tmp_path):
    runner, budget, _, probe = components(api_engine, uuid4(), tmp_path / "evidence.jsonl")
    with pytest.raises(CandidateRunDenied, match="BUDGET_DENIED"):
        await runner.run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    assert probe.calls == len(budget.tickets) == 0
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_accounts").fetchone() == (0,)
