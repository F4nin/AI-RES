"""Actual PG16 API-role preflight; fixture-only accounts, never live enrollment."""
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg import sql
from sqlalchemy import text

from ai_res.db.session import create_session_factory
from ai_res.modules.model_registry.candidate_host import CandidateTariff
from ai_res.modules.model_registry.candidate_host_account import verify_candidate_account
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest

from .test_llm_poc_paid_ledger import PLAN, TARIFF, seed_account
from .test_model_admission import api_engine as api_engine

pytestmark = pytest.mark.postgres


def inputs():
    return (CandidateRunManifest("a" * 40, "b" * 64, "c" * 64, "d" * 64, None, "e" * 64, PLAN, TARIFF),
            CandidateTariff("USD", Decimal("0.30"), Decimal("1.20"), 2_000_000, 256, "f" * 64))


@pytest.mark.parametrize("mutation", [None, "missing", "other-account", "plan", "tariff", "input-rate", "output-rate"])
async def test_exact_original_account_and_rates_are_required_without_mutation(migrated, api_engine, mutation):
    manifest, tariff = inputs()
    account = uuid4() if mutation == "missing" else seed_account(migrated)
    if mutation == "other-account":
        account = uuid4()
    if mutation == "plan":
        manifest = replace(manifest, plan_sha256="1" * 64)
    if mutation == "tariff":
        manifest = replace(manifest, tariff_sha256="2" * 64)
    if mutation == "input-rate":
        tariff = replace(tariff, input_per_million=Decimal("0.31"))
    if mutation == "output-rate":
        tariff = replace(tariff, output_per_million=Decimal("1.21"))
    factory = create_session_factory(api_engine)
    if mutation is None:
        await verify_candidate_account(factory, account, manifest, tariff)
    else:
        with pytest.raises(CandidateRunDenied, match="BINDING_MISMATCH"):
            await verify_candidate_account(factory, account, manifest, tariff)
    assert api_engine.pool.checkedout() == 0
    async with factory() as session, session.begin():
        assert (await session.execute(text("SELECT current_setting('app.llm_poc_budget_id',true)"))).scalar() in {None, ""}
        assert (await session.execute(text("SELECT count(*) FROM platform.llm_poc_budget_accounts"))).scalar() == 0  # RLS default deny
    with migrated.connect() as connection:
        for table in ("llm_poc_attempts", "llm_poc_settlements", "llm_poc_budget_audit"):
            assert connection.execute(sql.SQL("SELECT count(*) FROM platform.{}").format(sql.Identifier(table))).fetchone() == (0,)


async def test_preflight_uses_api_grants_and_preserves_pending_accounting(migrated, api_engine):
    from .test_llm_poc_paid_ledger import binding, ledger

    account = seed_account(migrated)
    service = ledger(api_engine, account)
    await service.reserve(binding())
    before = await service.balance()
    await verify_candidate_account(create_session_factory(api_engine), account, *inputs())
    assert before.pending and await service.balance() == before
