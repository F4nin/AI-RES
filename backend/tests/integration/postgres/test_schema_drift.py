"""PERSIST-024: schema drift fails CI. The committed snapshot is the reviewed design; `alembic upgrade head` must reproduce it exactly."""
import os
import re

import pytest

from .conftest import BACKEND, Pg
from .snapshot import build_snapshot

pytestmark = pytest.mark.postgres
SNAPSHOT = BACKEND / "ops" / "postgres" / "schema_snapshot.sql"


def test_migrated_schema_matches_committed_snapshot(migrated: Pg):
    actual = build_snapshot(migrated)
    if os.environ.get("UPDATE_SCHEMA_SNAPSHOT") == "1":
        assert not os.environ.get("CI"), "UPDATE_SCHEMA_SNAPSHOT must never be set in CI (it would turn the drift gate into a skip)"
        SNAPSHOT.write_text(actual)
        pytest.skip("snapshot regenerated: review the diff, then re-run without UPDATE_SCHEMA_SNAPSHOT")
    assert SNAPSHOT.exists(), "schema_snapshot.sql is missing: run `make db-snapshot` and review it"
    assert actual == SNAPSHOT.read_text(), "schema drift: migrations and the reviewed snapshot disagree (run `make db-snapshot`, review the diff)"


def test_snapshot_is_deterministic_and_secret_free(migrated: Pg):
    first, second = build_snapshot(migrated), build_snapshot(migrated)
    assert first == second
    for forbidden in ("SCRAM-SHA-256$", *migrated.passwords.values(), migrated.superuser_pw):
        assert forbidden not in first
    assert not re.search(r"\bPASSWORD\s+'", first)  # role-password syntax; the word alone is a legitimate enum value (iam.credentials.kind)


def test_drift_is_detected(migrated: Pg):
    baseline = build_snapshot(migrated)
    with migrated.connect() as c:
        c.execute("GRANT USAGE ON SCHEMA iam TO ai_res_auditor")
    assert build_snapshot(migrated) != baseline
    with migrated.connect() as c:
        c.execute("REVOKE USAGE ON SCHEMA iam FROM ai_res_auditor")
        c.execute("ALTER ROLE ai_res_api SET work_mem = '1GB'")
    assert build_snapshot(migrated) != baseline
