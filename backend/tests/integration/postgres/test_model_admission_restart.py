"""Fresh guard processes see committed blocks/unresolved receipts in real PG16.

This tests guard process loss and logical restore, not physical/power-loss recovery or a product drill.
"""
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from ai_res.llm.observed_identity import IdentityExpectation

from .conftest import Pg
from .test_model_admission import seed

pytestmark = pytest.mark.postgres

CHILD = r'''
import asyncio, json, sys
from dataclasses import replace
from datetime import UTC, datetime
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.llm.observed_identity import (
    FingerprintPresence, IdentityObservation, ObservedFingerprint, parse_evidence,
)
from ai_res.modules.model_registry.admission import AdmissionDenied, ModelAdmissionGuard
from ai_res.platform.config import load_settings

async def main():
    data = json.load(sys.stdin)
    expected = parse_evidence(json.dumps(data['expectation']))
    engine = create_runtime_engine(load_settings(data['settings']))
    try:
        guard = ModelAdmissionGuard(create_session_factory(engine))
        ticket = await guard.begin(expected.managed_versions.profile_id, expected.managed_versions,
                                   request_ref=data['requestRef'])
        if data['mode'] == 'drift':
            changed = replace(expected.identity, fingerprint=ObservedFingerprint(FingerprintPresence.VALUE, 'changed-fixture'))
            observation = IdentityObservation(expected.managed_versions, changed, datetime.now(UTC),
                                              data['requestRef'], 'synthetic-provider-ref')
            await guard.finalize(ticket, observation)
        print(json.dumps({'code': 'RESERVED'}))
    except AdmissionDenied as error:
        print(json.dumps({'code': error.code}))
    finally:
        await engine.dispose()

asyncio.run(main())
'''


def execute_guard(pg: Pg, tmp_path: Path, expected: IdentityExpectation, mode: str, request_ref: str) -> str:
    secret_file = tmp_path / "api_pw"
    secret_file.write_text(pg.passwords["ai_res_api"])
    settings = {
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": pg.host, "AI_RES_DB_PORT": str(pg.port),
        "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(secret_file), "AI_RES_DB_SSLMODE": "disable",
    }
    # Only the path to a temporary secret mount goes over stdin; never a credential value in argv/env/output.
    result = subprocess.run([sys.executable, "-B", "-c", CHILD], input=json.dumps({
        "settings": settings, "expectation": expected.to_dict(), "mode": mode, "requestRef": request_ref,
    }), text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, "Guard child process failed; raw output withheld."
    return json.loads(result.stdout)["code"]


@pytest.mark.parametrize("mode,first,second", [("drift", "IDENTITY_MISMATCH", "PROFILE_BLOCKED"),
                                             ("reserve", "RESERVED", "CALL_UNRESOLVED_OR_REUSED")])
def test_guard_process_exit_preserves_durable_barrier(migrated: Pg, tmp_path: Path, mode, first, second):
    expected = seed(migrated)
    assert execute_guard(migrated, tmp_path, expected, mode, "process-call-1") == first
    # The first interpreter and its guard/engine have exited before the next one starts.
    assert execute_guard(migrated, tmp_path, expected, "reserve", "process-call-2") == second
    with migrated.connect() as conn:
        assert conn.execute("SELECT count(*) FROM platform.model_admission_calls").fetchone() == (1,)


def test_logical_restore_preserves_historical_api_actor_under_restore_role(migrated: Pg, tmp_path: Path):
    expected = seed(migrated)
    assert execute_guard(migrated, tmp_path, expected, "reserve", "before-dump") == "RESERVED"
    with migrated.connect() as conn:
        before = conn.execute("SELECT id,profile_id,call_id,event_type,reason_code,writer_role,occurred_at "
                              "FROM platform.model_admission_audit ORDER BY id").fetchall()
        assert before and before[0][5] == "ai_res_api"
    code, dump = migrated.container.exec(["pg_dump", "-U", "postgres", "-d", "ai_res_db",
                                          "--exclude-schema=langgraph", "--exclude-schema=temporal"])
    assert code == 0, "Logical dump failed; raw output withheld."
    with migrated.connect(dbname="postgres") as conn:
        conn.execute("CREATE DATABASE guard_restore_fixture OWNER ai_res_owner")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo("guard_restore.sql")
        info.size, info.mode = len(dump), 0o600
        tar.addfile(info, io.BytesIO(dump))
    archive.seek(0)
    migrated.container.get_wrapped_container().put_archive("/tmp", archive)
    code, _ = migrated.container.exec(["psql", "-U", "postgres", "-d", "guard_restore_fixture", "-v", "ON_ERROR_STOP=1",
                                       "-f", "/tmp/guard_restore.sql"])
    assert code == 0, "Logical restore failed; raw output withheld."
    with migrated.connect(dbname="guard_restore_fixture") as conn:
        assert conn.execute("SELECT current_user").fetchone() == ("postgres",)
        assert conn.execute("SELECT id,profile_id,call_id,event_type,reason_code,writer_role,occurred_at "
                            "FROM platform.model_admission_audit ORDER BY id").fetchall() == before
