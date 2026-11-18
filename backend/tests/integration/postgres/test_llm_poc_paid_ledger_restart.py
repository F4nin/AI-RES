"""Ledger state across interpreter exits and logical restore, using real PG16.

No inference occurs. This is neither physical/power-loss recovery nor a product
recovery drill; every child finishes its short DB operation before exiting.
"""
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import sql

from .conftest import Pg

pytestmark = pytest.mark.postgres
RESERVE = "0.6003072"
TABLES = ("llm_poc_budget_accounts", "llm_poc_attempts", "llm_poc_settlements", "llm_poc_budget_audit")

CHILD = r'''
import asyncio, hashlib, json, sys
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.model_registry.poc_budget import (
    PaidLedgerDenied, ProbeAttemptTicket, ProbeRequestBinding, TechnicalPaidLedger,
)
from ai_res.platform.config import load_settings

async def main():
    data = json.load(sys.stdin)
    engine = create_runtime_engine(load_settings(data['settings']))
    result = {}
    try:
        ledger = TechnicalPaidLedger(create_session_factory(engine), UUID(data['account']))
        if data['mode'] == 'balance':
            balance = await ledger.balance()
            result = {'code': 'BALANCE', 'used': str(balance.used_or_reserved.normalize()),
                      'attempts': balance.attempts, 'pending': balance.pending, 'blocked': balance.blocked}
        elif data['mode'] == 'repeat_claim':
            saved = data['ticket']
            binding = ProbeRequestBinding(**saved['binding'])
            ticket = ProbeAttemptTicket(UUID(saved['account']), UUID(saved['attempt']),
                                        saved['sequence'], binding, Decimal(saved['cost']))
            await ledger.claim_dispatch(ticket, binding)
            result = {'code': 'UNEXPECTED_REPLAY'}
        else:
            ref = data['requestRef']
            binding = ProbeRequestBinding(ref, 'TEXT', hashlib.sha256(ref.encode()).hexdigest(),
                                          128, False, 256, 'b' * 64, 'c' * 64)
            ticket = await ledger.reserve(binding)
            result = {'code': 'RESERVED', 'ticket': {
                'account': str(ticket.account_id), 'attempt': str(ticket.attempt_id),
                'sequence': ticket.sequence, 'binding': asdict(binding), 'cost': str(ticket.reserved_cost)}}
            if data['mode'] != 'reserve':
                await ledger.claim_dispatch(ticket, binding)
                result['code'] = 'CLAIMED'
            if data['mode'] == 'unknown':
                settled = await ledger.record_unknown(ticket, reason='TIMEOUT')
                result['code'] = settled.outcome
            elif data['mode'] in ('known', 'overrun'):
                settled = await ledger.record_usage(ticket, input_tokens=12,
                    output_tokens=257 if data['mode'] == 'overrun' else 2,
                    provider_request_ref='synthetic-billing-ref')
                result['code'] = settled.outcome
    except PaidLedgerDenied as error:
        result = {'code': error.code}
    finally:
        await engine.dispose()
    print(json.dumps(result))

asyncio.run(main())
'''


def seed_process_account(pg: Pg) -> UUID:
    """Synthetic DB-owner fixture; never a production authorization or tariff seed."""
    account = uuid4()
    with pg.connect() as conn:
        conn.execute("""INSERT INTO platform.llm_poc_budget_accounts(
            id,authorization_key,currency,max_cost,original_spend,max_attempts,input_bound,output_bound,body_bound,
            provider,model_id,http_method,upstream_host,upstream_path,plan_sha256,tariff_sha256,input_per_million,output_per_million)
            VALUES(%s,'FLASH_TECHNICAL_ADMISSION_2026_11_17','USD',10,0,8,2000000,256,4096,
                   'deepseek','deepseek-flash','POST','api.deepseek.com','/chat/completions',%s,%s,0.30,1.20)""",
                     [account, bytes.fromhex("b" * 64), bytes.fromhex("c" * 64)])
    return account


def execute_ledger(pg: Pg, tmp_path: Path, account: UUID, mode: str, request_ref: str = "process-probe", *, ticket=None):
    secret_file = tmp_path / "api_pw"
    secret_file.write_text(pg.passwords["ai_res_api"])
    secret_file.chmod(0o600)
    settings = {
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": pg.host, "AI_RES_DB_PORT": str(pg.port),
        "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(secret_file), "AI_RES_DB_SSLMODE": "disable",
    }
    # The path alone crosses stdin; secret values never appear in argv/env/output.
    result = subprocess.run([sys.executable, "-B", "-c", CHILD], input=json.dumps({
        "settings": settings, "account": str(account), "mode": mode, "requestRef": request_ref, "ticket": ticket,
    }), text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, "Ledger child failed; raw output withheld."
    return json.loads(result.stdout)


@pytest.mark.parametrize("first_mode,code", [("reserve", "RESERVED"), ("claim", "CLAIMED")])
def test_unresolved_reservation_and_claim_survive_interpreter_exit(migrated: Pg, tmp_path: Path, first_mode, code):
    account = seed_process_account(migrated)
    assert execute_ledger(migrated, tmp_path, account, first_mode)["code"] == code
    assert execute_ledger(migrated, tmp_path, account, "reserve", "another-process-probe")["code"] == "PENDING"
    balance = execute_ledger(migrated, tmp_path, account, "balance")
    assert balance == {"code": "BALANCE", "used": RESERVE, "attempts": 1, "pending": True, "blocked": False}


def test_claim_cannot_be_reissued_from_saved_ticket_in_a_new_process(migrated: Pg, tmp_path: Path):
    account = seed_process_account(migrated)
    first = execute_ledger(migrated, tmp_path, account, "claim")
    assert first["code"] == "CLAIMED"
    assert execute_ledger(migrated, tmp_path, account, "repeat_claim", ticket=first["ticket"])["code"] == "CLAIM_REPLAY"
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.llm_poc_budget_audit WHERE action='CLAIM'").fetchone() == (1,)


def test_unknown_charge_and_attempt_count_survive_a_new_process(migrated: Pg, tmp_path: Path):
    account = seed_process_account(migrated)
    assert execute_ledger(migrated, tmp_path, account, "unknown")["code"] == "UNKNOWN"
    balance = execute_ledger(migrated, tmp_path, account, "balance")
    assert balance == {"code": "BALANCE", "used": RESERVE, "attempts": 1, "pending": False, "blocked": False}
    assert execute_ledger(migrated, tmp_path, account, "reserve", "independent-next-case")["code"] == "RESERVED"
    later = execute_ledger(migrated, tmp_path, account, "balance")
    assert later["attempts"] == 2 and later["used"] == "1.2006144" and later["pending"]


def test_overrun_block_survives_a_new_process(migrated: Pg, tmp_path: Path):
    account = seed_process_account(migrated)
    assert execute_ledger(migrated, tmp_path, account, "overrun")["code"] == "OVERRUN"
    assert execute_ledger(migrated, tmp_path, account, "reserve", "after-overrun")["code"] == "ACCOUNT_BLOCKED"
    balance = execute_ledger(migrated, tmp_path, account, "balance")
    assert balance["blocked"] and balance["attempts"] == 1 and not balance["pending"]


def test_logical_restore_preserves_paid_ledger_and_historical_audit_actor(migrated: Pg, tmp_path: Path):
    account = seed_process_account(migrated)
    assert execute_ledger(migrated, tmp_path, account, "known")["code"] == "KNOWN"
    with migrated.connect() as conn:
        before = {table: conn.execute(sql.SQL("SELECT * FROM platform.{} ORDER BY id").format(sql.Identifier(table))).fetchall()
                  for table in TABLES}
        assert all(before.values()) and all(row[5] == "ai_res_api" for row in before["llm_poc_budget_audit"])
    code, dump = migrated.container.exec(["pg_dump", "-U", "postgres", "-d", "ai_res_db",
                                          "--exclude-schema=langgraph", "--exclude-schema=temporal"])
    assert code == 0, "Logical dump failed; raw output withheld."
    with migrated.connect(dbname="postgres") as conn:
        conn.execute("CREATE DATABASE ledger_restore_fixture OWNER ai_res_owner")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo("ledger_restore.sql")
        info.size, info.mode = len(dump), 0o600
        tar.addfile(info, io.BytesIO(dump))
    archive.seek(0)
    migrated.container.get_wrapped_container().put_archive("/tmp", archive)
    code, _ = migrated.container.exec(["psql", "-U", "postgres", "-d", "ledger_restore_fixture", "-v", "ON_ERROR_STOP=1",
                                       "-f", "/tmp/ledger_restore.sql"])
    assert code == 0, "Logical restore failed; raw output withheld."
    with migrated.connect(dbname="ledger_restore_fixture") as conn:
        assert conn.execute("SELECT current_user").fetchone() == ("postgres",)
        for table in TABLES:
            assert conn.execute(sql.SQL("SELECT * FROM platform.{} ORDER BY id").format(sql.Identifier(table))).fetchall() == before[table]
