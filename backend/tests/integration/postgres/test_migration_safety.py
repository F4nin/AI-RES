# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""PERSIST-002 (upgrade from the previous revision with data) and PERSIST-017..020 (backfill resume, NOT VALID -> VALIDATE, interrupted concurrent
index, lock timeout) on a TEST-ONLY synthetic expand/backfill/validate revision (ADR-035). The synthetic revision lives only in a scratch copy of the
migration directory and is never shipped. Plus the operation_type registry <-> table drift check.
"""
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from psycopg import errors

from ai_res.modules.operations.repository import OPERATION_TYPES

from .conftest import BACKEND, Pg, alembic_config, run_audit

pytestmark = pytest.mark.postgres


class SimulatedStop(Exception):  # noqa: N818 - a test double for a killed process, deliberately not a BaseException
    pass
_SCRIPTS = ScriptDirectory.from_config(alembic_config())
HEAD = _SCRIPTS.get_current_head()
PREVIOUS_REVISION = _SCRIPTS.get_revision(HEAD).down_revision  # type: ignore[union-attr]

EXPAND = '''"""TEST-ONLY (ADR-035): expand step of an expand/backfill/validate/contract cycle on probe tables."""
from alembic import op

revision = "ffff00000003"
down_revision = "__HEAD__"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE work.s05_probe_parent (id uuid PRIMARY KEY, organization_id uuid NOT NULL)")
    op.execute("CREATE TABLE work.s05_probe_child (id uuid PRIMARY KEY, organization_id uuid NOT NULL, parent_id uuid, legacy_parent text)")
    op.execute("CREATE TABLE work.s05_probe_mapping (legacy_parent text PRIMARY KEY, parent_id uuid NOT NULL)")


def downgrade() -> None:
    op.execute("DROP TABLE work.s05_probe_mapping, work.s05_probe_child, work.s05_probe_parent")
'''


@pytest.fixture
def probe(empty_db: Pg, migrate_env, tmp_path: Path) -> Pg:
    dst = tmp_path / "scratch_migrations"
    shutil.copytree(BACKEND / "src/ai_res/db/migrations", dst, ignore=shutil.ignore_patterns("__pycache__"))
    (dst / "versions" / "9001_test_only_expand.py").write_text(EXPAND.replace("__HEAD__", HEAD))
    command.upgrade(alembic_config(dst), "head")
    return empty_db


def test_persist_002_upgrade_from_previous_revision_keeps_data_and_matches_snapshot(empty_db: Pg, upgrade):
    org, prj, epic = uuid4(), uuid4(), uuid4()
    upgrade(PREVIOUS_REVISION)
    with empty_db.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
        c.execute("INSERT INTO work.epics (id, organization_id, project_id, title, status) VALUES (%s,%s,%s,'e','ACTIVE')", [epic, org, prj])
        assert c.execute("SELECT count(*) FROM pg_policy WHERE polname LIKE 'p\\_%\\_owner\\_migration'").fetchone() == (0,)  # really the previous state: no owner policies yet
    upgrade()
    with empty_db.connect() as c:
        assert c.execute("SELECT version_num FROM platform.alembic_version").fetchone() == (HEAD,)
        assert c.execute("SELECT title, row_version FROM work.epics WHERE id=%s", [epic]).fetchone() == ("e", 1)
        assert c.execute("SELECT count(*) FROM project.projects WHERE id=%s", [prj]).fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM pg_policy WHERE polname LIKE 'p\\_%\\_owner\\_migration'").fetchone()[0] >= 20  # type: ignore[index]  # every RLS table got one
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == []  # no drift of the security posture after an incremental upgrade


def test_persist_017_backfill_stops_and_resumes_without_duplicate_mappings(probe: Pg):
    org, parents = uuid4(), {f"L{i}": uuid4() for i in range(6)}
    with probe.connect() as c:
        for pid in parents.values():
            c.execute("INSERT INTO work.s05_probe_parent (id, organization_id) VALUES (%s,%s)", [pid, org])
        for i in range(6):
            c.execute("INSERT INTO work.s05_probe_child (id, organization_id, legacy_parent) VALUES (%s,%s,%s)", [uuid4(), org, f"L{i % 3}"])  # many children per legacy key

    def batch(limit: int, interrupt_after: int | None = None) -> int:
        """One resumable batch: its own transaction, keyed on 'parent_id IS NULL' (the cursor is the data), idempotent mapping insert."""
        with probe.connect(autocommit=False) as c:  # synthetic probe tables carry NO RLS (test-only): this proves resumability only; FORCE-RLS behaviour of the owner is test_owner_backfill_on_a_forced_rls_table_*
            rows = c.execute("SELECT id, legacy_parent FROM work.s05_probe_child WHERE parent_id IS NULL ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", [limit]).fetchall()
            for n, (cid, legacy) in enumerate(rows):
                c.execute("INSERT INTO work.s05_probe_mapping (legacy_parent, parent_id) VALUES (%s,%s) ON CONFLICT (legacy_parent) DO NOTHING", [legacy, parents[legacy]])
                c.execute("UPDATE work.s05_probe_child SET parent_id = %s WHERE id = %s", [parents[legacy], cid])
                if interrupt_after is not None and n + 1 == interrupt_after:
                    c.rollback()
                    raise SimulatedStop  # simulated stop mid-batch: nothing of this batch may survive
            c.commit()
            return len(rows)

    assert batch(2) == 2
    with pytest.raises(SimulatedStop):
        batch(3, interrupt_after=2)
    with probe.connect() as c:
        assert c.execute("SELECT count(*) FROM work.s05_probe_child WHERE parent_id IS NOT NULL").fetchone() == (2,)  # the interrupted batch left no half-state
    while batch(2):
        pass
    with probe.connect() as c:
        assert c.execute("SELECT count(*) FROM work.s05_probe_child WHERE parent_id IS NULL").fetchone() == (0,)
        assert c.execute("SELECT count(*), count(DISTINCT legacy_parent) FROM work.s05_probe_mapping").fetchone() == (3, 3)  # restart produced no duplicate mappings
    assert batch(2) == 0  # re-running a finished backfill is a no-op


def test_owner_backfill_on_a_forced_rls_table_works_only_with_the_migration_policy(migrated: Pg):
    """ADR-034 (5), the part PERSIST-017's synthetic probe tables cannot show: FORCE RLS binds the OWNER too. Runs as the real migration path
    (ai_res_migrator -> SET ROLE ai_res_owner), never as the superuser (who bypasses RLS and would prove nothing)."""
    orgs, prjs = [uuid4(), uuid4()], [uuid4(), uuid4()]
    with migrated.connect() as c:
        for org, prj in zip(orgs, prjs, strict=True):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
    with migrated.connect("ai_res_migrator", autocommit=False) as c:
        c.execute("SET ROLE ai_res_owner")
        assert c.execute("SELECT count(*) FROM project.projects").fetchone() == (0,)  # control: without the flag the owner is default-deny (a backfill would be a silent no-op)
        c.execute("SELECT set_config('app.migration_mode', 'on', true)")
        assert c.execute("SELECT count(*) FROM project.projects").fetchone() == (2,)  # the explicit migration policy makes both tenants visible
        assert c.execute("UPDATE project.projects SET name = 'backfilled', row_version = row_version + 1").rowcount == 2  # optimistic concurrency binds backfills too
        c.commit()
        assert c.execute("SELECT count(*) FROM project.projects").fetchone() == (0,)  # the flag was transaction-local: it does not outlive the transaction
    with migrated.connect() as c:
        assert c.execute("SELECT count(*) FROM project.projects WHERE name = 'backfilled'").fetchone() == (2,)
    with migrated.connect("ai_res_api", autocommit=False) as c:  # the flag grants nothing to runtime principals (the policy is TO ai_res_owner only)
        c.execute("SELECT set_config('app.migration_mode', 'on', true)")
        assert c.execute("SELECT count(*) FROM project.projects").fetchone() == (0,)


def test_persist_018_not_valid_fk_then_validate_detects_orphans(probe: Pg):
    org, good, orphan = uuid4(), uuid4(), uuid4()
    with probe.connect() as c:
        c.execute("INSERT INTO work.s05_probe_parent (id, organization_id) VALUES (%s,%s)", [good, org])
        c.execute("INSERT INTO work.s05_probe_child (id, organization_id, parent_id) VALUES (%s,%s,%s)", [uuid4(), org, orphan])  # pre-existing orphan
        c.execute("ALTER TABLE work.s05_probe_child ADD CONSTRAINT fk_probe_child_parent FOREIGN KEY (parent_id) REFERENCES work.s05_probe_parent(id) NOT VALID")
        assert c.execute("SELECT convalidated FROM pg_constraint WHERE conname='fk_probe_child_parent'").fetchone() == (False,)
        with pytest.raises(errors.ForeignKeyViolation):  # NOT VALID still guards new rows
            c.execute("INSERT INTO work.s05_probe_child (id, organization_id, parent_id) VALUES (%s,%s,%s)", [uuid4(), org, uuid4()])
        with pytest.raises(errors.ForeignKeyViolation):  # VALIDATE finds the orphan; the constraint stays unvalidated (no silent contract)
            c.execute("ALTER TABLE work.s05_probe_child VALIDATE CONSTRAINT fk_probe_child_parent")
        assert c.execute("SELECT convalidated FROM pg_constraint WHERE conname='fk_probe_child_parent'").fetchone() == (False,)
        c.execute("DELETE FROM work.s05_probe_child WHERE parent_id = %s", [orphan])  # approved remediation
        c.execute("ALTER TABLE work.s05_probe_child VALIDATE CONSTRAINT fk_probe_child_parent")
        assert c.execute("SELECT convalidated FROM pg_constraint WHERE conname='fk_probe_child_parent'").fetchone() == (True,)


def test_persist_019_interrupted_concurrent_index_is_detected_and_repaired(probe: Pg):
    org = uuid4()
    with probe.connect() as c:
        for _ in range(2):  # duplicates make a UNIQUE concurrent build fail half-way, which leaves an INVALID index behind (as a killed build does)
            c.execute("INSERT INTO work.s05_probe_child (id, organization_id, legacy_parent) VALUES (%s,%s,'dup')", [uuid4(), org])
        with pytest.raises(errors.UniqueViolation):
            c.execute("CREATE UNIQUE INDEX CONCURRENTLY ux_probe_child_legacy ON work.s05_probe_child (legacy_parent)")
        invalid = "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE NOT i.indisvalid AND n.nspname = 'work'"
        assert c.execute(invalid).fetchall() == [("ux_probe_child_legacy",)]  # detection query (what preflight/postflight must report)
        c.execute("DROP INDEX CONCURRENTLY work.ux_probe_child_legacy")  # repair: drop the invalid index, fix data, rebuild
        c.execute("DELETE FROM work.s05_probe_child WHERE legacy_parent = 'dup' AND id::text <> (SELECT min(id::text) FROM work.s05_probe_child WHERE legacy_parent = 'dup')")
        c.execute("CREATE UNIQUE INDEX CONCURRENTLY ux_probe_child_legacy ON work.s05_probe_child (legacy_parent)")
        assert c.execute(invalid).fetchall() == []


def test_persist_020_lock_timeout_fails_safely_with_no_partial_change(probe: Pg):
    with probe.connect() as holder:
        holder.autocommit = False
        holder.execute("LOCK TABLE work.s05_probe_child IN ACCESS EXCLUSIVE MODE")  # another session holds the table, as a long transaction would
        with probe.connect("ai_res_migrator", autocommit=False) as m:
            m.execute("SET ROLE ai_res_owner")
            m.execute("SET LOCAL lock_timeout = '300ms'")
            with pytest.raises(errors.LockNotAvailable):
                m.execute("ALTER TABLE work.s05_probe_child ADD COLUMN contract_col text NOT NULL DEFAULT 'x'")
        holder.rollback()
    with probe.connect() as c:
        assert c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='s05_probe_child' AND column_name='contract_col'").fetchone() == (0,)


def test_operation_type_registry_in_code_equals_the_database_registry(migrated: Pg):
    with migrated.connect() as c:
        in_db = {r[0] for r in c.execute("SELECT code FROM operations.operation_types")}
        assert in_db == OPERATION_TYPES  # drift in either direction fails
        org, prj = uuid4(), uuid4()
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s,'o')", [org])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
        with pytest.raises(errors.ForeignKeyViolation):  # an unregistered type cannot be stored
            c.execute("INSERT INTO operations.operations (id, organization_id, project_id, operation_type, status, initiator_type, idempotency_scope, request_fingerprint, "
                      "completion_policy_version, completion_policy_snapshot, correlation_id) VALUES (%s,%s,%s,'NOT_REGISTERED','ACCEPTED','USER','s',%s,'v','{}',%s)",
                      [uuid4(), org, prj, b"\x01" * 32, uuid4()])
