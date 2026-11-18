"""Private TLS, real service signatures and real PG accounting in one path.

The server runs on another event loop; a test-only NullPool prevents connections
from crossing loops. Ordinary pool/RLS reset semantics have separate PG tests.
All accounts/tariffs/usage are synthetic; there is no model/provider request.
"""
import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from ai_res.db.engine import build_url, connect_args
from ai_res.db.session import create_session_factory
from ai_res.llm.adapters.candidate_control import CandidateControlClient, CandidateControlUnavailable
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.modules.model_registry.poc_budget import ProbeRequestBinding, TechnicalPaidLedger
from ai_res.modules.model_registry.poc_control import CandidateControlService
from ai_res.platform.config import load_settings

from ..test_candidate_control_tls import tls_server as tls_server
from .conftest import Pg
from .test_llm_poc_paid_ledger import PLAN, RESERVE, TARIFF, break_audit, seed_account

pytestmark = pytest.mark.postgres


@pytest.fixture
async def control_factory(migrated: Pg, tmp_path):
    password_file = tmp_path / "api_pw"
    password_file.write_text(migrated.passwords["ai_res_api"])
    password_file.chmod(0o600)
    settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": migrated.host, "AI_RES_DB_PORT": str(migrated.port),
                              "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(password_file), "AI_RES_DB_SSLMODE": "disable"})
    engine = create_async_engine(build_url(settings), connect_args=connect_args(settings), poolclass=NullPool, hide_parameters=True)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


async def reserved(factory, account):
    body = build_candidate_body("TEXT", uuid4())
    ledger = TechnicalPaidLedger(factory, account)
    ticket = await ledger.reserve(ProbeRequestBinding("tls-probe", "TEXT", body.body_sha256, body.payload_bytes,
                                                     body.stream, body.max_output_tokens, PLAN, TARIFF))
    return ledger, ticket, body


async def test_actual_tls_claim_and_settlement_use_real_pg_once_only(migrated: Pg, control_factory, tls_server):
    account = seed_account(migrated)
    ledger, ticket, body = await reserved(control_factory, account)
    host = tls_server(service=CandidateControlService(control_factory, account, PLAN, TARIFF))
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue) as client:
        receipt = await client.claim(body)
        assert receipt.attempt_id == ticket.attempt_id
        await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="synthetic-tls-provider")
        with pytest.raises(CandidateControlUnavailable):
            await client.claim(body)
    balance = await ledger.balance()
    assert balance.used_or_reserved == Decimal("0.000006") and not balance.pending and balance.attempts == 1
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_audit WHERE action='CLAIM'").fetchone() == (1,)


async def test_settlement_ack_timeout_can_leave_committed_settled_state(migrated: Pg, control_factory, tls_server):
    account = seed_account(migrated)
    ledger, _, body = await reserved(control_factory, account)
    host = tls_server(service=CandidateControlService(control_factory, account, PLAN, TARIFF), delay_settlement_ack=1)
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue, timeout_seconds=0.4) as client:
        receipt = await client.claim(body)
        with pytest.raises(CandidateControlUnavailable):
            await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="synthetic-tls-provider")
    assert await asyncio.to_thread(host.settlement_recorded.wait, 2)
    balance = await ledger.balance()
    assert not balance.pending and balance.used_or_reserved == Decimal("0.000006")
    with migrated.connect() as conn:
        assert conn.execute("SELECT outcome FROM platform.llm_poc_settlements").fetchall() == [("KNOWN",)]
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("SETTLED",)
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_audit WHERE action='SETTLE'").fetchone() == (1,)


async def test_tls_callback_audit_failure_preserves_full_claimed_reserve(migrated: Pg, control_factory, tls_server):
    account = seed_account(migrated)
    ledger, _, body = await reserved(control_factory, account)
    host = tls_server(service=CandidateControlService(control_factory, account, PLAN, TARIFF))
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue) as client:
        receipt = await client.claim(body)
        break_audit(migrated)
        with pytest.raises(CandidateControlUnavailable):
            await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="synthetic-tls-provider")
    balance = await ledger.balance()
    assert balance.pending and balance.used_or_reserved == RESERVE and balance.attempts == 1
    with migrated.connect() as conn:
        assert conn.execute("SELECT state FROM platform.llm_poc_attempts").fetchone() == ("CLAIMED",)
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_settlements").fetchone() == (0,)


async def test_actual_tls_cannot_create_an_unreserved_case(migrated: Pg, control_factory, tls_server):
    account = seed_account(migrated)
    ledger = TechnicalPaidLedger(control_factory, account)
    host = tls_server(service=CandidateControlService(control_factory, account, PLAN, TARIFF))
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue) as client:
        with pytest.raises(CandidateControlUnavailable):
            await client.claim(build_candidate_body("TEXT", uuid4()))
    balance = await ledger.balance()
    assert balance.attempts == 0 and balance.used_or_reserved == 0 and not balance.pending
