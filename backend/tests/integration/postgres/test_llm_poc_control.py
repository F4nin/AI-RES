"""Fixed-account control over real PG; synthetic reservations, no provider calls."""
import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.session import create_session_factory
from ai_res.modules.model_registry.poc_control import (
    BODY_CODEC_VERSION,
    CandidateClaimedAttempt,
    CandidateClaimRequest,
    CandidateControlDenied,
    CandidateControlService,
    CandidateControlUnavailable,
    CandidateSettlementRequest,
)

from .conftest import Pg
from .test_llm_poc_paid_ledger import PLAN, RESERVE, TARIFF, binding, break_audit, counts, ledger, seed_account
from .test_model_admission import api_engine as api_engine

pytestmark = pytest.mark.postgres


def service(engine: AsyncEngine, account, *, plan=PLAN, tariff=TARIFF) -> CandidateControlService:
    return CandidateControlService(create_session_factory(engine), account, plan, tariff)


def claim_request(request) -> CandidateClaimRequest:
    return CandidateClaimRequest(BODY_CODEC_VERSION, "SSE" if request.stream else "TEXT", request.body_sha256,
                                 request.payload_bytes, request.stream, request.max_output_tokens)


def unknown(attempt_id, body_hash) -> CandidateSettlementRequest:
    return CandidateSettlementRequest(attempt_id, body_hash, "UNKNOWN", reason="TIMEOUT")


async def test_unknown_body_never_reserves_a_case_and_denial_is_audited(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    with pytest.raises(CandidateControlDenied):
        await service(api_engine, account).claim(claim_request(binding()))
    balance = await ledger(api_engine, account).balance()
    assert balance.attempts == 0 and balance.used_or_reserved == 0 and counts(migrated) == (0, 0, 1)


@pytest.mark.parametrize("plan,tariff", [("f" * 64, TARIFF), (PLAN, "f" * 64)])
async def test_server_expected_manifests_are_required_even_for_known_reservation(migrated: Pg, api_engine: AsyncEngine, plan, tariff):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    with pytest.raises(CandidateControlDenied):
        await service(api_engine, account, plan=plan, tariff=tariff).claim(claim_request(ticket.binding))
    assert counts(migrated) == (1, 0, 2)
    with migrated.connect() as conn:
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("RESERVED",)


async def test_claim_reconstructs_server_ticket_and_replay_fails_after_new_connections(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    result = await control.claim(claim_request(ticket.binding))
    assert result.attempt_id == ticket.attempt_id and result.request_ref == ticket.binding.request_ref
    assert result.body_sha256 == ticket.binding.body_sha256 and result.max_output_tokens == 256
    await api_engine.dispose()
    with pytest.raises(CandidateControlDenied):
        await service(api_engine, account).claim(claim_request(ticket.binding))
    state = await ledger(api_engine, account).balance()
    assert state.pending and state.attempts == 1 and state.used_or_reserved == RESERVE
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_audit WHERE action='CLAIM'").fetchone() == (1,)


async def test_concurrent_control_claims_never_return_two_positive_replies(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    command = claim_request(ticket.binding)
    results = await asyncio.gather(service(api_engine, account).claim(command), service(api_engine, account).claim(command), return_exceptions=True)
    assert sum(isinstance(value, CandidateClaimedAttempt) for value in results) == 1
    assert sum(isinstance(value, CandidateControlDenied) for value in results) == 1
    assert counts(migrated) == (1, 0, 3)


@pytest.mark.parametrize("changes", [{"template_case": "JSON"}, {"payload_bytes": 129}, {"stream": True}, {"max_output_tokens": 255}])
async def test_declared_case_or_limits_must_match_reserved_case(migrated: Pg, api_engine: AsyncEngine, changes):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    with pytest.raises(CandidateControlDenied):
        await service(api_engine, account).claim(replace(claim_request(ticket.binding), **changes))
    with migrated.connect() as conn:
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("RESERVED",)


async def test_explicit_recheck_is_still_exact_hash_and_limit_bound(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    request = binding(case_ref="RECHECK", stream=True)
    ticket = await ledger(api_engine, account).reserve(request)
    control = service(api_engine, account)
    command = replace(claim_request(request), template_case="SSE")
    claimed = await control.claim(command)
    assert claimed.attempt_id == ticket.attempt_id and claimed.stream is True
    settled = await control.settle(unknown(ticket.attempt_id, request.body_sha256))
    assert settled.outcome == "UNKNOWN" and (await ledger(api_engine, account).balance()).used_or_reserved == RESERVE


async def test_lookup_transaction_finishes_before_locked_ledger_revalidation(migrated: Pg, api_engine: AsyncEngine, monkeypatch):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    original = control._ledger.claim_dispatch

    async def revalidated(stored_ticket, stored_binding):
        # A single-host invocation must release its read checkout before the
        # ledger obtains a new protected UoW, rather than nesting transactions.
        assert api_engine.pool.checkedout() == 0
        return await original(stored_ticket, stored_binding)

    monkeypatch.setattr(control._ledger, "claim_dispatch", revalidated)
    assert (await control.claim(claim_request(ticket.binding))).attempt_id == ticket.attempt_id


async def test_state_change_after_lookup_is_revalidated_and_never_dispatches(migrated: Pg, api_engine: AsyncEngine, monkeypatch):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    original = control._ledger.claim_dispatch

    async def changed_after_lookup(stored_ticket, stored_binding):
        with migrated.connect("ai_res_api") as conn, conn.transaction():
            conn.execute("SELECT set_config('app.llm_poc_budget_id',%s,true)", [str(account)])
            conn.execute("UPDATE platform.llm_poc_budget_accounts SET blocked=true WHERE id=%s", [account])
        return await original(stored_ticket, stored_binding)

    monkeypatch.setattr(control._ledger, "claim_dispatch", changed_after_lookup)
    with pytest.raises(CandidateControlDenied):
        await control.claim(claim_request(ticket.binding))
    assert (await ledger(api_engine, account).balance()).blocked
    with migrated.connect() as conn:
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("RESERVED",)


async def test_settlement_uses_exact_attempt_and_body_and_known_usage_replay_is_idempotent(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    await control.claim(claim_request(ticket.binding))
    for wrong in (unknown(uuid4(), ticket.binding.body_sha256), unknown(ticket.attempt_id, "d" * 64)):
        with pytest.raises(CandidateControlDenied):
            await control.settle(wrong)
    request = CandidateSettlementRequest(ticket.attempt_id, ticket.binding.body_sha256, "KNOWN", 100, 20, "provider-fixture-1")
    assert (await control.settle(request)).outcome == "KNOWN"
    before = counts(migrated)
    assert (await control.settle(request)).outcome == "KNOWN" and counts(migrated) == before
    assert (await ledger(api_engine, account).balance()).used_or_reserved < RESERVE


@pytest.mark.parametrize("outcome,input_tokens,output_tokens", [("KNOWN", True, 1), ("KNOWN", 2_000_000, 257), ("INVALID_USAGE", None, None)])
async def test_invalid_or_overrun_settlement_commits_charge_and_block_before_refusal(migrated: Pg, api_engine: AsyncEngine,
                                                                                   outcome, input_tokens, output_tokens):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    await control.claim(claim_request(ticket.binding))
    request = CandidateSettlementRequest(ticket.attempt_id, ticket.binding.body_sha256, outcome, input_tokens, output_tokens, "provider-fixture-1")
    with pytest.raises(CandidateControlDenied):
        await control.settle(request)
    state = await ledger(api_engine, account).balance()
    assert state.blocked and not state.pending
    with migrated.connect() as conn:
        assert conn.execute("SELECT outcome FROM platform.llm_poc_settlements").fetchone()[0] in {"INVALID_USAGE", "OVERRUN"}


@pytest.mark.parametrize("phase", ["claim", "settlement"])
async def test_audit_outage_is_unavailable_and_retains_full_reserve_after_new_connections(migrated: Pg, api_engine: AsyncEngine, phase):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    if phase == "settlement":
        await control.claim(claim_request(ticket.binding))
    break_audit(migrated)
    with pytest.raises(CandidateControlUnavailable):
        if phase == "claim":
            await control.claim(claim_request(ticket.binding))
        else:
            await control.settle(unknown(ticket.attempt_id, ticket.binding.body_sha256))
    await api_engine.dispose()
    state = await ledger(api_engine, account).balance()
    assert state.pending and state.used_or_reserved == RESERVE and counts(migrated)[1] == 0


@pytest.mark.parametrize("facts", [
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "input_tokens": 2_000_001},
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "output_tokens": None},
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "provider_request_ref": "provider-fixture"},
    {"outcome": "KNOWN", "input_tokens": 10, "output_tokens": 2, "provider_request_ref": "provider-fixture", "reason": None},
])
async def test_direct_mixed_settlement_facts_commit_full_charge_and_sticky_block(migrated: Pg, api_engine: AsyncEngine, facts):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding())
    control = service(api_engine, account)
    await control.claim(claim_request(ticket.binding))
    with pytest.raises(CandidateControlDenied):
        await control.settle(CandidateSettlementRequest(ticket.attempt_id, ticket.binding.body_sha256, **facts))
    state = await ledger(api_engine, account).balance()
    assert state.blocked and not state.pending and state.used_or_reserved == RESERVE
    with migrated.connect() as conn:
        assert conn.execute("SELECT outcome FROM platform.llm_poc_settlements").fetchone() == ("INVALID_USAGE",)


@pytest.mark.parametrize("changes", [{"max_output_tokens": 255}, {"stream": True}])
async def test_matching_malformed_reservation_cannot_make_an_invalid_codec_claim_valid(migrated: Pg, api_engine: AsyncEngine, changes):
    account = seed_account(migrated)
    ticket = await ledger(api_engine, account).reserve(binding(**changes))
    with pytest.raises(CandidateControlDenied):
        await service(api_engine, account).claim(claim_request(ticket.binding))
    with migrated.connect() as conn:
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("RESERVED",)
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_audit WHERE action='CLAIM'").fetchone() == (0,)
