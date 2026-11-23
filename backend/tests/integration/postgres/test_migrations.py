"""PERSIST-001 (upgrade from empty), PERSIST-004 (autocommit_block / CONCURRENTLY), PERSIST-020-style lock safety, allowlist (DBM-002)."""
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from psycopg import errors
from psycopg.types.json import Jsonb

from ai_res.db.base import DOMAIN_SCHEMAS
from ai_res.orchestration.contracts import EXECUTION_ASSIGNMENT_REF, START_DESTINATION, workflow_id_for

from .conftest import BACKEND, Pg, alembic_config, run_audit
from .test_audit_platform_schema import outbox_sql
from .test_operations_work_schema import event_sql, new_op

pytestmark = pytest.mark.postgres


def test_persist_001_upgrade_from_empty_reaches_head(empty_db: Pg, upgrade):
    upgrade()  # a REAL `alembic upgrade head` from an empty database: the audits below must not run on a template clone (CI-01, ADR-118)
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with empty_db.connect() as c:
        assert c.execute("SELECT version_num FROM platform.alembic_version").fetchall() == [(head,)]
        schemas = {r[0] for r in c.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema'")}
        assert set(DOMAIN_SCHEMAS) <= schemas
        owners = c.execute(
            "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = ANY(%s)", [list(DOMAIN_SCHEMAS)]
        ).fetchall()
        assert {o for _, o in owners} == {"ai_res_owner"} and len(owners) == 18
        assert run_audit(c, "postflight.sql") == []
        assert run_audit(c, "grants_audit.sql") == []
        assert run_audit(c, "rls_coverage.sql") == []


def test_g02_upgrade_preserves_project_from_previous_head(empty_db: Pg, upgrade):
    upgrade("c97e3bf386f1")
    with empty_db.connect() as c:
        organization = c.execute("INSERT INTO organization.organizations(id,name) VALUES (gen_random_uuid(),'Prior organization') RETURNING id").fetchone()[0]
        project = c.execute(
            "INSERT INTO project.projects(id,organization_id,name,project_type) "
            "VALUES (gen_random_uuid(),%s,'Prior project','GREENFIELD') RETURNING id", (organization,),
        ).fetchone()[0]

    upgrade()
    with empty_db.connect() as c:
        assert c.execute("SELECT organization_id,name FROM project.projects WHERE id=%s", (project,)).fetchone() == (organization, "Prior project")
        assert c.execute("SELECT version_num FROM platform.alembic_version").fetchone() == (
            ScriptDirectory.from_config(alembic_config()).get_current_head(),
        )
        assert run_audit(c, "grants_audit.sql") == []


def test_upgrade_backfills_only_the_exact_assigned_outbox_route(empty_db: Pg, upgrade):
    upgrade("4dd4da8ee5c2")
    org, project, assignment, invalid_assignment = (uuid4() for _ in range(4))
    with empty_db.connect(autocommit=False) as c:
        c.execute("INSERT INTO organization.organizations(id,name) VALUES (%s,'Prior organization')", (org,))
        c.execute("INSERT INTO project.projects(id,organization_id,name,project_type) VALUES (%s,%s,'Prior project','GREENFIELD')", (project, org))
        exact = new_op(c, org, project, op_type="MANAGER_MESSAGE")
        forged = new_op(c, org, project, op_type="MANAGER_MESSAGE")
        invalid = new_op(c, org, project, op_type="MANAGER_MESSAGE")
        for operation, target, namespace in ((exact, assignment, "blue"), (invalid, invalid_assignment, "Invalid_History")):
            c.execute("""
                INSERT INTO platform.operation_execution_assignments(id,organization_id,project_id,operation_id,workflow_id,workflow_type,
                    namespace,task_queue,workflow_contract_version,input_digest,correlation_id,allowed_actions)
                VALUES (%s,%s,%s,%s,%s,'ManagerIntakeWorkflow',%s,'ai-res-manager',1,%s,%s,ARRAY['operation.acknowledge_start'])
            """, (target, org, project, operation, workflow_id_for(operation), namespace, b"h" * 32, uuid4()))
        statement = outbox_sql(dest=START_DESTINATION).replace(
            "'aggregateSequence', p.seq)", "'aggregateSequence', p.seq, 'refs', %s::jsonb)",
        )
        for operation, target in ((exact, assignment), (forged, assignment), (invalid, invalid_assignment)):
            refs = Jsonb([{"resourceType": EXECUTION_ASSIGNMENT_REF, "resourceId": str(target)}])
            event = uuid4()
            c.execute("UPDATE operations.operations SET last_event_sequence=1,row_version=row_version+1 WHERE id=%s", (operation,))
            c.execute(event_sql(1), (event, operation, uuid4()))
            c.execute(statement, (refs, uuid4(), org, project, event, operation, 1))
        c.execute("UPDATE audit.outbox_events SET status='QUARANTINED',attempt_count=4,last_error_code='PUBLISH_FAILED' WHERE aggregate_id=%s", (exact,))

    upgrade()
    with empty_db.connect() as c:
        rows = c.execute("""
            SELECT aggregate_id,dispatch_assignment_id,dispatch_namespace,status,attempt_count,last_error_code FROM audit.outbox_events
        """).fetchall()
        assert set(rows) == {
            (exact, assignment, "blue", "QUARANTINED", 4, "PUBLISH_FAILED"),
            (forged, None, None, "QUARANTINED", 0, "OUTBOX_ROUTE_UNRESOLVED"),
            (invalid, None, None, "QUARANTINED", 0, "OUTBOX_ROUTE_UNRESOLVED"),
        }
        assert run_audit(c, "grants_audit.sql") == []
    with empty_db.connect("ai_res_api", autocommit=False) as c:
        c.execute("SELECT set_config('app.organization_id',%s,true),set_config('app.project_id',%s,true)", (str(org), str(project)))
        assert c.execute("SELECT replay_count FROM audit.inspect_assigned_start_replay(%s)", (exact,)).fetchall() == [(0,)]
        assert c.execute("SELECT replay_count FROM audit.inspect_assigned_start_replay(%s)", (invalid,)).fetchall() == []
        event = c.execute("SELECT event_id FROM operations.operation_events WHERE operation_id=%s", (invalid,)).fetchone()[0]
        with pytest.raises(errors.CheckViolation, match="ck_outbox_assigned_route_resolved"):
            c.execute(statement, (refs, uuid4(), org, project, event, invalid, 1))
        c.rollback()
    with empty_db.connect("ai_res_outbox_dispatcher") as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute("UPDATE audit.outbox_events SET dispatch_namespace='red' WHERE aggregate_id=%s", (exact,))


def test_upgrade_is_idempotent_at_head(migrated: Pg):
    command.upgrade(alembic_config(), "head")
    with migrated.connect() as c:
        assert c.execute("SELECT count(*) FROM platform.alembic_version").fetchone() == (1,)


@pytest.mark.parametrize(("previous", "action"), [
    ("382befc90d62", "CHECK_TASK"),
    ("13f3c5d9b7a2", "AUTHORIZE_RECONCILIATION_DESCRIBE"),
    ("7dcb4f29a2e1", "AUTHORIZE_BOUND_STATUS"),
    ("a47ca6b2015f", "AUTHORIZE_BOUND_STATUS"),
])
def test_native_reconciliation_upgrade_preserves_existing_audit(empty_db: Pg, upgrade, previous, action):
    upgrade(previous)
    with empty_db.connect("ai_res_platform_api") as connection:
        connection.execute("""
            INSERT INTO platform.platform_auth_events(id,correlation_id,reason,action)
            VALUES (gen_random_uuid(),gen_random_uuid(),'AUTHORIZED',%s)
        """, (action,))
    upgrade()
    with empty_db.connect() as connection:
        assert connection.execute("SELECT reason,action FROM platform.platform_auth_events").fetchall() == [("AUTHORIZED", action)]
        assert run_audit(connection, "grants_audit.sql") == []


def test_downgrade_of_security_baseline_is_refused(migrated: Pg):
    with pytest.raises(NotImplementedError, match="(?i)forward-fix"):
        command.downgrade(alembic_config(), "base")
    with migrated.connect() as c:
        assert c.execute("SELECT count(*) FROM platform.alembic_version").fetchone() == (1,)


def test_preflight_is_clean_on_a_provisioned_server(empty_db: Pg):
    with empty_db.connect("ai_res_migrator") as c:
        assert run_audit(c, "preflight.sql") == []


def test_preflight_fires_on_privileged_connection_and_held_migration_lock(empty_db: Pg):
    with empty_db.connect() as su:  # connected as the bootstrap superuser: must be reported
        assert "connected_as_privileged" in {k for k, _ in run_audit(su, "preflight.sql")}
    holder = empty_db.connect("ai_res_migrator")
    try:
        holder.execute("SELECT pg_advisory_lock(hashtextextended('ai_res.alembic.migrations', 0))")
        with empty_db.connect("ai_res_migrator") as c:
            assert "migration_in_progress" in {k for k, _ in run_audit(c, "preflight.sql")}
    finally:
        holder.close()
    with empty_db.connect("ai_res_migrator") as c:  # lock released with the session -> clean again (positive control)
        assert run_audit(c, "preflight.sql") == []


def test_migrator_is_not_superuser_and_superuser_is_refused(empty_db: Pg, migrate_env, tmp_path, monkeypatch):
    pw = tmp_path / "su"
    pw.write_text(empty_db.superuser_pw)
    migrate_env(AI_RES_DB_USER="postgres", AI_RES_DB_PASSWORD_FILE=str(pw))
    with pytest.raises(RuntimeError, match="SUPERUSER"):
        command.upgrade(alembic_config(), "head")
    with empty_db.connect() as c:
        assert c.execute("SELECT to_regclass('platform.alembic_version')").fetchone() == (None,)


@pytest.mark.parametrize("sabotage, expected", [
    ("ALTER ROLE ai_res_api BYPASSRLS", "forbidden attributes"),
    ("ALTER ROLE ai_res_outbox_dispatcher CREATEROLE", "forbidden attributes"),
    ("GRANT ai_res_owner TO ai_res_api", "must not be members of ai_res_owner"),
    ("ALTER ROLE ai_res_event_consumer RESET search_path", "search_path"),
    ("ALTER ROLE ai_res_api_group LOGIN", "group roles must be NOLOGIN"),
])
def test_revision_fails_fast_on_weak_role_provisioning(empty_db: Pg, upgrade, sabotage: str, expected: str):
    with empty_db.connect() as c:
        c.execute(sabotage.encode())
    with pytest.raises(Exception, match=expected):
        upgrade()
    with empty_db.connect() as c:  # nothing half-applied: transactional DDL rolled the schemas back
        assert c.execute("SELECT count(*) FROM pg_namespace WHERE nspname IN ('iam','operations')").fetchone() == (0,)
        assert c.execute("SELECT to_regclass('platform.alembic_version')").fetchone() == (None,)


def test_provisioning_corrects_drift_on_rerun(empty_db: Pg):
    with empty_db.connect() as c:
        c.execute("ALTER ROLE ai_res_api CREATEDB BYPASSRLS")
        c.execute("GRANT ai_res_owner TO ai_res_outbox_dispatcher")
        c.execute("GRANT pg_read_all_data TO ai_res_auditor")
        c.execute("GRANT ai_res_api_group TO ai_res_backup")
        c.execute("ALTER ROLE ai_res_api SET work_mem = '1GB'")
        c.execute("ALTER ROLE ai_res_api IN DATABASE ai_res_db SET search_path = public")
        c.execute("ALTER ROLE ai_res_api SET app.organization_id = '00000000-0000-0000-0000-000000000001'")
        c.execute("GRANT ai_res_api_group TO ai_res_api WITH ADMIN OPTION")
        c.execute("GRANT ai_res_owner TO ai_res_migrator WITH ADMIN OPTION")
        c.execute("GRANT CONNECT ON DATABASE ai_res_db TO ai_res_backup")
        c.execute("ALTER DATABASE ai_res_db OWNER TO postgres")
    empty_db.provision()
    with empty_db.connect() as c:
        assert c.execute("SELECT rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname='ai_res_api'").fetchone() == (False, False)
        assert c.execute("SELECT pg_has_role('ai_res_outbox_dispatcher','ai_res_owner','MEMBER')").fetchone() == (False,)
        assert c.execute("SELECT pg_has_role('ai_res_auditor','pg_read_all_data','MEMBER'), pg_has_role('ai_res_backup','ai_res_api_group','MEMBER')"
                         ).fetchone() == (False, False)
        assert c.execute("SELECT count(*) FROM pg_db_role_setting s JOIN pg_roles r ON r.oid=s.setrole WHERE r.rolname='ai_res_api' "
                         "AND EXISTS (SELECT 1 FROM unnest(s.setconfig) x WHERE x LIKE 'work_mem=%' OR x LIKE 'app.%')").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM pg_db_role_setting s JOIN pg_roles r ON r.oid=s.setrole WHERE r.rolname='ai_res_api' "
                         "AND s.setdatabase <> 0").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM pg_auth_members WHERE admin_option").fetchone() == (0,)
        assert c.execute("SELECT has_database_privilege('ai_res_backup', 'ai_res_db', 'CONNECT'), pg_get_userbyid(datdba) "
                         "FROM pg_database WHERE datname='ai_res_db'").fetchone() == (False, "ai_res_owner")


def test_concurrent_migrator_fails_fast_instead_of_waiting_forever(empty_db: Pg, upgrade):
    holder = empty_db.connect("ai_res_migrator", dbname="ai_res_db")
    try:
        holder.execute("SELECT pg_advisory_lock(hashtextextended('ai_res.alembic.migrations', 0))")
        with pytest.raises(Exception, match="lock timeout|canceling statement"):
            upgrade()
    finally:
        holder.close()
    with empty_db.connect() as c:
        assert c.execute("SELECT count(*) FROM pg_namespace WHERE nspname = 'iam'").fetchone() == (0,)  # nothing applied (PERSIST-020 shape)


def _scratch_scripts(tmp_path: Path, extra_revision: str | None = None) -> Path:
    dst = tmp_path / "scratch_migrations"
    shutil.copytree(BACKEND / "src/ai_res/db/migrations", dst, ignore=shutil.ignore_patterns("__pycache__"))
    if extra_revision is not None:
        head = ScriptDirectory.from_config(alembic_config()).get_current_head()
        (dst / "versions" / "9000_test_only_concurrent_index.py").write_text(extra_revision.replace("__HEAD__", str(head)))
    return dst


SYNTHETIC = '''"""TEST-ONLY revision (ADR-011): proves autocommit_block + CREATE INDEX CONCURRENTLY under SET ROLE ai_res_owner. Never shipped."""
from alembic import op

revision = "ffff00000002"
down_revision = "__HEAD__"  # replaced by the real head of the shipped chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE work.s04_probe (id uuid PRIMARY KEY, organization_id uuid NOT NULL)")
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY ix_s04_probe_organization_id ON work.s04_probe (organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE work.s04_probe")
'''


MODE_ON = '''"""TEST-ONLY revision: switches the owner migration flag on and leaves it on."""
from alembic import op

revision = "ffff00000003"
down_revision = "__HEAD__"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE work.mm_probe (v text)")
    op.execute("SELECT set_config('app.migration_mode', 'on', true)")


def downgrade() -> None:
    op.execute("DROP TABLE work.mm_probe")
'''
MODE_READ = '''"""TEST-ONLY revision: records the flag a LATER revision of the same upgrade observes."""
from alembic import op

revision = "ffff00000004"
down_revision = "ffff00000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO work.mm_probe SELECT coalesce(current_setting('app.migration_mode', true), 'unset')")


def downgrade() -> None:
    pass
'''


def test_migration_mode_does_not_leak_into_the_next_revision(empty_db: Pg, migrate_env, tmp_path):
    """All revisions of one upgrade share a transaction: a flag switched on by one revision must be off again for the next (verification pass, LOW)."""
    scripts = _scratch_scripts(tmp_path, MODE_ON.replace("ffff00000002", "ffff00000003"))
    (scripts / "versions" / "9001_test_only_mode_read.py").write_text(MODE_READ)
    command.upgrade(alembic_config(scripts), "head")
    with empty_db.connect() as c:
        assert c.execute("SELECT v FROM work.mm_probe").fetchall() == [("off",)]


def test_persist_004_concurrent_index_runs_in_autocommit_block(empty_db: Pg, migrate_env, tmp_path):
    cfg = alembic_config(_scratch_scripts(tmp_path, SYNTHETIC))
    command.upgrade(cfg, "head")
    with empty_db.connect() as c:
        assert c.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = 'work.ix_s04_probe_organization_id'::regclass").fetchone() == (True,)
        assert c.execute("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'work.s04_probe'::regclass").fetchone() == ("ai_res_owner",)
        # a table with organization_id and no RLS must be reported by the coverage check (DBM-017)
        assert ("rls_not_enabled_and_forced", "work.s04_probe") in run_audit(c, "rls_coverage.sql")
    import io
    buf = io.StringIO()
    cfg.output_buffer = buf
    command.upgrade(cfg, "d4c18a7e5b92:head", sql=True)
    assert "CREATE INDEX CONCURRENTLY" in buf.getvalue() and "COMMIT" in buf.getvalue()


def test_alembic_does_not_see_or_touch_foreign_schemas(empty_db: Pg, migrate_env, tmp_path):
    with empty_db.connect() as c:  # created by a superuser before migration, like provisioning does for langgraph (ADR-036)
        c.execute("CREATE SCHEMA langgraph")
        c.execute("CREATE TABLE langgraph.checkpoints (thread_id text PRIMARY KEY)")
        c.execute("CREATE SCHEMA temporal")
        c.execute("CREATE TABLE temporal.schema_version (v int)")
        c.execute("CREATE TABLE public.foreign_table (v int)")
    scratch = _scratch_scripts(tmp_path)
    cfg = alembic_config(scratch)
    command.upgrade(cfg, "head")
    command.revision(cfg, message="autogen probe", autogenerate=True, rev_id="ffff00000003")
    generated = next((scratch / "versions").glob("ffff00000003*.py")).read_text()
    for forbidden in ("langgraph", "temporal", "'checkpoints'", "foreign_table", "alembic_version"):
        assert forbidden not in generated, f"autogenerate saw {forbidden}"
    with empty_db.connect() as c:
        assert c.execute("SELECT count(*) FROM langgraph.checkpoints").fetchone() == (0,)
        assert c.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='langgraph'").fetchone() == ("postgres",)
        with pytest.raises(errors.UndefinedTable):
            c.execute("SELECT 1 FROM platform.foreign_table")
