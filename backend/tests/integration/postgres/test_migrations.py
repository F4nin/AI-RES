"""PERSIST-001 (upgrade from empty), PERSIST-004 (autocommit_block / CONCURRENTLY), PERSIST-020-style lock safety, allowlist (DBM-002)."""
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from psycopg import errors

from ai_res.db.base import DOMAIN_SCHEMAS

from .conftest import BACKEND, Pg, alembic_config, run_audit

pytestmark = pytest.mark.postgres


def test_persist_001_upgrade_from_empty_reaches_head(migrated: Pg):
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with migrated.connect() as c:
        assert c.execute("SELECT version_num FROM platform.alembic_version").fetchall() == [(head,)]
        schemas = {r[0] for r in c.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema'")}
        assert set(DOMAIN_SCHEMAS) <= schemas
        owners = c.execute(
            "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = ANY(%s)", [list(DOMAIN_SCHEMAS)]
        ).fetchall()
        assert {o for _, o in owners} == {"ai_res_owner"} and len(owners) == 18
        assert c.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname = ANY(%s) AND c.relkind='r'",
                         [[s for s in DOMAIN_SCHEMAS if s != "platform"]]).fetchone() == (0,)  # S04 creates no domain tables
        assert run_audit(c, "postflight.sql") == []
        assert run_audit(c, "grants_audit.sql") == []
        assert run_audit(c, "rls_coverage.sql") == []


def test_upgrade_is_idempotent_at_head(migrated: Pg):
    command.upgrade(alembic_config(), "head")
    with migrated.connect() as c:
        assert c.execute("SELECT count(*) FROM platform.alembic_version").fetchone() == (1,)


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
        (dst / "versions" / "0002_test_only_concurrent_index.py").write_text(extra_revision)
    return dst


SYNTHETIC = '''"""TEST-ONLY revision (ADR-011): proves autocommit_block + CREATE INDEX CONCURRENTLY under SET ROLE ai_res_owner. Never shipped."""
from alembic import op

revision = "ffff00000002"
down_revision = "3b7e9c41a0d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE work.s04_probe (id uuid PRIMARY KEY, organization_id uuid NOT NULL)")
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY ix_s04_probe_organization_id ON work.s04_probe (organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE work.s04_probe")
'''


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
    command.upgrade(cfg, "3b7e9c41a0d2:head", sql=True)
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
    for forbidden in ("langgraph", "temporal", "checkpoints", "foreign_table", "alembic_version"):
        assert forbidden not in generated, f"autogenerate saw {forbidden}"
    with empty_db.connect() as c:
        assert c.execute("SELECT count(*) FROM langgraph.checkpoints").fetchone() == (0,)
        assert c.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='langgraph'").fetchone() == ("postgres",)
        with pytest.raises(errors.UndefinedTable):
            c.execute("SELECT 1 FROM platform.foreign_table")
