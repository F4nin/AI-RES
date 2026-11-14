"""CI-01 (ADR-118): `migrated` is a clone of a database migrated once per session instead of a per-test `alembic upgrade head`.
That is only acceptable while the clone is indistinguishable from a fresh migration and every test still starts from a pristine copy."""
import psycopg
import pytest
from alembic.script import ScriptDirectory

from .conftest import DB, TEMPLATE_DB, Pg, alembic_config
from .snapshot import build_snapshot

pytestmark = pytest.mark.postgres


def _row_counts(pg: Pg) -> dict[str, int]:
    out: dict[str, int] = {}
    with pg.connect() as c:
        tables = c.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' "
                           "AND table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2").fetchall()
        for schema, table in tables:
            row = c.execute(f'SELECT count(*) FROM "{schema}"."{table}"').fetchone()  # noqa: S608 - names come from the catalog
            assert row is not None
            out[f"{schema}.{table}"] = int(row[0])
    return out


def _version(pg: Pg) -> str:
    with pg.connect() as c:
        row = c.execute("SELECT version_num FROM platform.alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def test_a_clone_is_identical_to_a_fresh_migration(empty_db: Pg, upgrade, migrated_template):
    upgrade()  # the real path: provisioned empty database -> alembic upgrade head
    fresh_snapshot, fresh_rows, fresh_version = build_snapshot(empty_db), _row_counts(empty_db), _version(empty_db)
    empty_db.clone_template()
    assert build_snapshot(empty_db) == fresh_snapshot  # schema, ownership, grants, RLS, role settings and the database ACL
    assert _row_counts(empty_db) == fresh_rows  # seeded registry rows included
    assert _version(empty_db) == fresh_version == ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert len(fresh_rows) > 20  # not a vacuous comparison


def test_the_parity_check_detects_a_clone_whose_database_acl_was_not_reapplied(empty_db: Pg, upgrade, migrated_template):
    """CREATE DATABASE ... TEMPLATE does not copy the database ACL. The comparison above must notice if provisioning were skipped."""
    upgrade()
    fresh = build_snapshot(empty_db)
    with empty_db.connect(dbname="postgres") as c:
        c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {DB} OWNER ai_res_owner TEMPLATE {TEMPLATE_DB}")  # deliberately without provision()
    assert build_snapshot(empty_db) != fresh
    empty_db.provision()
    assert build_snapshot(empty_db) == fresh


def test_every_clone_starts_pristine_not_from_the_previous_tests_data(migrated: Pg):
    before = _row_counts(migrated)
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (gen_random_uuid(), 'left behind by a previous test')")
    assert _row_counts(migrated)["organization.organizations"] == before["organization.organizations"] + 1
    migrated.clone_template()
    assert _row_counts(migrated) == before


def test_the_template_is_sealed(migrated: Pg):
    with pytest.raises(psycopg.OperationalError):
        migrated.connect(dbname=TEMPLATE_DB)
    with migrated.connect(dbname="postgres") as c:
        row = c.execute("SELECT datistemplate, datallowconn FROM pg_database WHERE datname = %s", [TEMPLATE_DB]).fetchone()
    assert row == (True, False)
