"""Synthetic tariffs/accounts prove technical accounting mechanics, never paid calls."""
import asyncio
import hashlib
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.script import ScriptDirectory
from psycopg import errors, sql
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.session import create_session_factory
from ai_res.modules.model_registry.poc_budget import (
    AUTHORIZATION_KEY,
    DispatchClaim,
    PaidLedgerDenied,
    PaidLedgerUnavailable,
    ProbeAttemptTicket,
    ProbeRequestBinding,
    TechnicalPaidLedger,
)

from .conftest import Pg, alembic_config, run_audit
from .test_model_admission import api_engine as api_engine

pytestmark = pytest.mark.postgres
PLAN, TARIFF = "b" * 64, "c" * 64
RESERVE = Decimal("0.6003072")
TABLES = ("llm_poc_budget_accounts", "llm_poc_attempts", "llm_poc_settlements", "llm_poc_budget_audit")


def seed_account(pg: Pg, **overrides) -> UUID:
    """DB-owner synthetic setup only. No production account-creation path exists."""
    account_id = uuid4()
    fields = {"id": account_id, "authorization_key": AUTHORIZATION_KEY, "currency": "USD", "max_cost": Decimal("10"),
              "original_spend": Decimal("0"), "max_attempts": 8, "input_bound": 2_000_000, "output_bound": 256, "body_bound": 4096,
              "provider": "deepseek", "model_id": "deepseek-flash", "http_method": "POST", "upstream_host": "api.deepseek.com",
              "upstream_path": "/chat/completions", "plan_sha256": bytes.fromhex(PLAN), "tariff_sha256": bytes.fromhex(TARIFF),
              "input_per_million": Decimal("0.30"), "output_per_million": Decimal("1.20")} | overrides
    with pg.connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE ai_res_owner")
        conn.execute("SELECT set_config('app.migration_mode','on',true)")
        conn.execute(sql.SQL("INSERT INTO platform.llm_poc_budget_accounts ({}) VALUES ({})").format(
            sql.SQL(",").join(sql.Identifier(key) for key in fields), sql.SQL(",").join(sql.Placeholder() for _ in fields)), list(fields.values()))
    return account_id


def binding(request_ref="fixture-1", **changes) -> ProbeRequestBinding:
    # Digest of synthetic fixture bytes, not of any user/project content.
    body = hashlib.sha256(("synthetic-body-marker-" + request_ref).encode()).hexdigest()
    return replace(ProbeRequestBinding(request_ref, "TEXT", body, 128, False, 256, PLAN, TARIFF), **changes)


def ledger(engine: AsyncEngine, account_id: UUID) -> TechnicalPaidLedger:
    return TechnicalPaidLedger(create_session_factory(engine), account_id)


async def claimed(service: TechnicalPaidLedger, request_ref="fixture-1") -> ProbeAttemptTicket:
    request = binding(request_ref)
    ticket = await service.reserve(request)
    await service.claim_dispatch(ticket, request)
    return ticket


def counts(pg: Pg) -> tuple[int, int, int]:
    with pg.connect() as conn:
        return tuple(conn.execute(sql.SQL("SELECT count(*) FROM platform.{}").format(sql.Identifier(table))).fetchone()[0]
                     for table in TABLES[1:])


def break_audit(pg: Pg) -> None:
    with pg.connect() as conn:
        conn.execute("CREATE FUNCTION platform.fixture_lp_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$ "
                     "BEGIN RAISE EXCEPTION 'synthetic audit outage'; END $$")
        conn.execute("CREATE TRIGGER fixture_lp_audit_fail BEFORE INSERT ON platform.llm_poc_budget_audit "
                     "FOR EACH ROW EXECUTE FUNCTION platform.fixture_lp_audit_fail()")


async def test_account_starts_missing_and_no_runtime_wallet_is_created(migrated: Pg, api_engine: AsyncEngine):
    with pytest.raises(PaidLedgerDenied) as error:
        await ledger(api_engine, uuid4()).reserve(binding())
    assert error.value.code == "ACCOUNT_MISSING" and counts(migrated) == (0, 0, 0)
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_accounts").fetchone() == (0,)


async def test_full_reserve_once_claim_known_usage_and_exact_replay(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    service = ledger(api_engine, account)
    ticket = await service.reserve(binding())
    state = await service.balance()
    assert state.used_or_reserved == RESERVE and state.remaining == Decimal("10")-RESERVE and state.pending and state.attempts == 1
    assert counts(migrated) == (1, 0, 1)
    await service.claim_dispatch(ticket, binding())
    result = await service.record_usage(ticket, input_tokens=100, output_tokens=20, provider_request_ref="provider-fixture-1")
    assert result.charged_cost == Decimal("0.000054") and result.outcome == "KNOWN" and not result.replay
    replay = await service.record_usage(ticket, input_tokens=100, output_tokens=20, provider_request_ref="provider-fixture-1")
    assert replay.replay and counts(migrated) == (1, 1, 3)
    after = await service.balance()
    assert after.used_or_reserved == Decimal("0.000054") and not after.pending and not after.blocked
    with migrated.connect() as conn:
        assert conn.execute("SELECT DISTINCT writer_role FROM platform.llm_poc_budget_audit").fetchall() == [("ai_res_api",)]


async def test_unknown_charges_full_reserve_and_attempt_cap_is_independent_of_remaining_money(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated)
    service = ledger(api_engine, account)
    for index in range(8):
        ticket = await claimed(service, f"fixture-{index}")
        settlement = await service.record_unknown(ticket, reason="TIMEOUT")
        assert settlement.charged_cost == RESERVE and settlement.outcome == "UNKNOWN"
    before = await service.balance()
    assert before.used_or_reserved == Decimal("4.8024576") and before.remaining > 5 and before.attempts == 8
    with pytest.raises(PaidLedgerDenied) as error:
        await service.reserve(binding("ninth-attempt"))
    assert error.value.code == "ATTEMPTS_EXHAUSTED" and counts(migrated)[:2] == (8, 8)
    assert (await service.balance()).used_or_reserved == before.used_or_reserved


async def test_original_spend_counts_and_cost_ceiling_cannot_be_bypassed(migrated: Pg, api_engine: AsyncEngine):
    account = seed_account(migrated, max_cost=Decimal("1"), original_spend=Decimal("0.30"))
    service = ledger(api_engine, account)
    ticket = await claimed(service)
    await service.record_unknown(ticket, reason="CANCEL")
    assert (await service.balance()).used_or_reserved == Decimal("0.9003072")
    with pytest.raises(PaidLedgerDenied) as error:
        await service.reserve(binding("next-attempt"))
    assert error.value.code == "BUDGET_EXHAUSTED" and counts(migrated)[:2] == (1, 1)


async def test_concurrent_reservations_and_claims_return_only_one_dispatch_claim(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    results = await asyncio.gather(service.reserve(binding("one")), service.reserve(binding("two")), return_exceptions=True)
    tickets = [value for value in results if isinstance(value, ProbeAttemptTicket)]
    assert len(tickets) == 1 and sum(isinstance(value, PaidLedgerDenied) for value in results) == 1
    ticket = tickets[0]
    claims = await asyncio.gather(service.claim_dispatch(ticket, ticket.binding), service.claim_dispatch(ticket, ticket.binding), return_exceptions=True)
    assert sum(isinstance(value, DispatchClaim) for value in claims) == 1
    assert sum(isinstance(value, PaidLedgerDenied) and value.code == "CLAIM_REPLAY" for value in claims) == 1
    assert counts(migrated) == (1, 0, 4)


async def test_reusing_a_body_with_new_reference_is_refused_across_all_prior_attempts(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await claimed(service)
    await service.record_usage(ticket, input_tokens=10, output_tokens=1, provider_request_ref="provider-1")
    reused = binding("new-reference", body_sha256=ticket.binding.body_sha256)
    with pytest.raises(PaidLedgerDenied) as error:
        await service.reserve(reused)
    assert error.value.code == "BODY_REUSED" and counts(migrated) == (1, 1, 4)
    assert (await service.balance()).attempts == 1


@pytest.mark.parametrize("field", ["plan_sha256", "tariff_sha256"])
async def test_manifest_substitution_refuses_before_reservation_and_is_audited(migrated: Pg, api_engine: AsyncEngine, field):
    service = ledger(api_engine, seed_account(migrated))
    with pytest.raises(PaidLedgerDenied) as error:
        await service.reserve(binding(**{field: "f" * 64}))
    assert error.value.code == "BINDING_MISMATCH" and counts(migrated) == (0, 0, 1)


async def test_wrong_binding_and_ticket_never_release_or_claim_reserved_attempt(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await service.reserve(binding())
    for altered in (replace(ticket, account_id=uuid4()), replace(ticket, attempt_id=uuid4()),
                    replace(ticket, reserved_cost=Decimal("0.1")), replace(ticket, binding=replace(ticket.binding, body_sha256="d" * 64))):
        with pytest.raises(PaidLedgerDenied) as error:
            await service.claim_dispatch(altered, altered.binding)
        assert error.value.code == "BINDING_MISMATCH"
    assert (await service.balance()).pending and counts(migrated) == (1, 0, 5)


async def test_conflicting_settlement_cannot_refund_unknown_and_blocks_account(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await claimed(service)
    await service.record_unknown(ticket, reason="NETWORK")
    replay = await service.record_unknown(ticket, reason="NETWORK")
    assert replay.replay and replay.charged_cost == RESERVE
    with pytest.raises(PaidLedgerDenied) as error:
        await service.record_usage(ticket, input_tokens=0, output_tokens=0, provider_request_ref="forged-cheaper-usage")
    assert error.value.code == "SETTLEMENT_CONFLICT"
    balance = await service.balance()
    assert balance.blocked and balance.used_or_reserved == RESERVE and counts(migrated) == (1, 1, 4)


@pytest.mark.parametrize("input_tokens,output_tokens,provider_ref", [(True, 0, "provider-1"), (-1, 0, "provider-1"),
    (1.0, 0, "provider-1"), (None, None, None), (9_223_372_036_854_775_808, 0, "provider-1"), (1, 1, "sk-" + "x" * 32)])
async def test_invalid_usage_commits_full_charge_and_block_before_safe_refusal(migrated: Pg, api_engine: AsyncEngine,
                                                                            input_tokens, output_tokens, provider_ref):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await claimed(service)
    with pytest.raises(PaidLedgerDenied) as error:
        await service.record_usage(ticket, input_tokens=input_tokens, output_tokens=output_tokens, provider_request_ref=provider_ref)
    assert error.value.code == "INVALID_USAGE" and "sk-" not in str(error.value)
    assert (await service.balance()).blocked and (await service.balance()).used_or_reserved == RESERVE
    with migrated.connect() as conn:
        row = conn.execute("SELECT outcome,input_tokens,output_tokens,provider_request_ref,charged_cost FROM platform.llm_poc_settlements").fetchone()
        assert row == ("INVALID_USAGE", None, None, None, RESERVE)


async def test_unhashable_unknown_reason_is_classified_without_raw_type_error(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await claimed(service)
    with pytest.raises(PaidLedgerDenied) as error:
        await service.record_unknown(ticket, reason=["private-fixture"])  # type: ignore[arg-type]
    assert error.value.code == "INVALID_USAGE" and "private-fixture" not in str(error.value)
    assert (await service.balance()).blocked


async def test_overrun_persists_actual_charge_and_sticky_block_before_exception(migrated: Pg, api_engine: AsyncEngine):
    service = ledger(api_engine, seed_account(migrated))
    ticket = await claimed(service)
    with pytest.raises(PaidLedgerDenied) as error:
        await service.record_usage(ticket, input_tokens=2_000_000, output_tokens=257, provider_request_ref="provider-overrun")
    assert error.value.code == "OVERRUN"
    state = await service.balance()
    assert state.blocked and state.used_or_reserved == Decimal("0.6003084") and not state.pending
    with pytest.raises(PaidLedgerDenied) as blocked:
        await service.reserve(binding("after-overrun"))
    assert blocked.value.code == "ACCOUNT_BLOCKED"


@pytest.mark.parametrize("phase", ["reserve", "claim", "settle"])
async def test_audit_failure_never_returns_permission_or_releases_money(migrated: Pg, api_engine: AsyncEngine, phase):
    service = ledger(api_engine, seed_account(migrated))
    ticket = None if phase == "reserve" else await service.reserve(binding())
    if phase == "settle":
        await service.claim_dispatch(ticket, binding())
    break_audit(migrated)
    with pytest.raises(PaidLedgerUnavailable) as error:
        if phase == "reserve":
            await service.reserve(binding())
        elif phase == "claim":
            await service.claim_dispatch(ticket, binding())
        else:
            await service.record_usage(ticket, input_tokens=1, output_tokens=1, provider_request_ref="provider-1")
    assert "synthetic audit outage" not in str(error.value)
    await api_engine.dispose()
    state = await service.balance()
    if phase == "reserve":
        assert state.attempts == 0 and state.used_or_reserved == 0 and not state.pending
    else:
        assert state.attempts == 1 and state.used_or_reserved == RESERVE and state.pending
        with migrated.connect() as conn:
            assert conn.execute("SELECT count(*) FROM platform.llm_poc_settlements").fetchone() == (0,)


async def test_balance_is_coherent_while_an_overrun_settlement_waits(migrated: Pg, api_engine: AsyncEngine, monkeypatch):
    account = seed_account(migrated)
    service = ledger(api_engine, account)
    ticket = await claimed(service)
    reached, release = asyncio.Event(), asyncio.Event()
    original_used = service._used

    async def paused_used(session, original_spend):
        reached.set()
        await release.wait()
        return await original_used(session, original_spend)

    monkeypatch.setattr(service, "_used", paused_used)
    reading = asyncio.create_task(service.balance())
    await asyncio.wait_for(reached.wait(), 5)
    writing = None
    try:
        with migrated.connect("ai_res_api") as conn, conn.transaction():
            conn.execute("SELECT set_config('app.llm_poc_budget_id',%s,true)", [str(account)])
            with pytest.raises(errors.LockNotAvailable), conn.transaction():
                conn.execute("SELECT id FROM platform.llm_poc_budget_accounts WHERE id=%s FOR UPDATE NOWAIT", [account])
        writing = asyncio.create_task(ledger(api_engine, account).record_usage(ticket, input_tokens=2_000_000, output_tokens=257,
                                                                            provider_request_ref="provider-overrun"))
    finally:
        release.set()
    before = await reading
    assert not before.blocked and before.pending and before.used_or_reserved == RESERVE
    assert writing is not None
    with pytest.raises(PaidLedgerDenied):
        await writing
    after = await ledger(api_engine, account).balance()
    assert after.blocked and not after.pending and after.used_or_reserved == Decimal("0.6003084")


@pytest.mark.parametrize("overrides", [{"authorization_key": "another-wallet"}, {"max_cost": Decimal("11")}, {"max_cost": Decimal("NaN")},
    {"original_spend": Decimal("-1")}, {"max_attempts": 9}, {"input_per_million": Decimal("Infinity")},
    {"output_per_million": Decimal("NaN")}, {"model_id": "deepseek-v4-pro"}, {"currency": "EUR"}])
def test_db_rejects_new_authorization_or_invalid_budget_tariff_values(migrated: Pg, overrides):
    with pytest.raises(errors.CheckViolation):
        seed_account(migrated, **overrides)


def test_original_authorization_is_unique_and_owner_cannot_reset_immutable_policy(migrated: Pg):
    seed_account(migrated)
    with pytest.raises(errors.UniqueViolation):
        seed_account(migrated)
    with migrated.connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE ai_res_owner")
        conn.execute("SELECT set_config('app.migration_mode','on',true)")
        for change in ("max_cost=9", "original_spend=1", "input_per_million=0.1", "plan_sha256=decode(repeat('ab',32),'hex')"):
            with pytest.raises(errors.IntegrityConstraintViolation), conn.transaction():
                conn.execute(sql.SQL("UPDATE platform.llm_poc_budget_accounts SET {}").format(sql.SQL(change)))


def test_runtime_default_deny_and_narrow_column_grants_cannot_self_grant_or_forge_money(migrated: Pg):
    account = seed_account(migrated)
    with migrated.connect("ai_res_api") as conn:
        for table in TABLES:
            assert conn.execute(sql.SQL("SELECT count(*) FROM platform.{}").format(sql.Identifier(table))).fetchone() == (0,)
        with conn.transaction():
            conn.execute("SELECT set_config('app.llm_poc_budget_id',%s,true)", [str(account)])
            assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_accounts").fetchone() == (1,)
            for statement in ("INSERT INTO platform.llm_poc_budget_accounts(id) VALUES(gen_random_uuid())",
                              "UPDATE platform.llm_poc_budget_accounts SET max_cost=10", "UPDATE platform.llm_poc_budget_accounts SET original_spend=0",
                              "INSERT INTO platform.llm_poc_attempts(id,reserved_cost) VALUES(gen_random_uuid(),0)",
                              "INSERT INTO platform.llm_poc_settlements(id,charged_cost) VALUES(gen_random_uuid(),0)",
                              "INSERT INTO platform.llm_poc_budget_audit(id,writer_role) VALUES(gen_random_uuid(),'ai_res_owner')",
                              "INSERT INTO platform.llm_poc_budget_audit(id,occurred_at) VALUES(gen_random_uuid(),now())"):
                with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
                    conn.execute(statement)
            for table in TABLES:
                for action in ("DELETE FROM", "TRUNCATE"):
                    with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
                        conn.execute(sql.SQL("{} platform.{} CASCADE").format(sql.SQL(action), sql.Identifier(table))
                                     if action == "TRUNCATE" else sql.SQL("{} platform.{}").format(sql.SQL(action), sql.Identifier(table)))
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_accounts").fetchone() == (0,)


def test_empty_and_previous_upgrade_create_no_account_or_tariff(empty_db: Pg, upgrade):
    scripts = ScriptDirectory.from_config(alembic_config())
    revision = next(r for r in scripts.walk_revisions() if Path(r.path).name.endswith("_llm_poc_paid_ledger.py"))
    assert isinstance(revision.down_revision, str)
    upgrade(revision.down_revision)
    with empty_db.connect() as conn:
        before = conn.execute("SELECT count(*) FROM platform.model_profiles").fetchone()
    upgrade(revision.revision)
    with empty_db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.model_profiles").fetchone() == before
        for table in TABLES:
            assert conn.execute(sql.SQL("SELECT count(*) FROM platform.{}").format(sql.Identifier(table))).fetchone() == (0,)
            assert conn.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                                [f"platform.{table}"]).fetchone() == (True, True)
        assert run_audit(conn, "rls_coverage.sql") == [] and run_audit(conn, "grants_audit.sql") == []
