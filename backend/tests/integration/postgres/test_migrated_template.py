"""CI-01 (ADR-118): `migrated` is a clone of a database migrated once per session instead of a per-test `alembic upgrade head`.
That is only acceptable while the clone is indistinguishable from a fresh migration and every test still starts from a pristine copy."""
from typing import Any

import psycopg
import pytest
from alembic.script import ScriptDirectory

from .conftest import DB, TEMPLATE_DB, Pg, alembic_config
from .snapshot import build_snapshot

pytestmark = pytest.mark.postgres
# Columns whose values legitimately differ between two migrations of the same revision (generated ids, migration-time stamps): excluded from the content hash.
VOLATILE_TYPES = ("uuid", "timestamp with time zone", "timestamp without time zone", "date")


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


def _content_hashes(pg: Pg) -> dict[str, str]:
    """md5 over the stable columns of every row of every table, so a changed seed value cannot hide behind an equal row count."""
    out: dict[str, str] = {}
    with pg.connect() as c:
        cols = c.execute("SELECT table_schema, table_name, column_name FROM information_schema.columns c WHERE table_schema NOT IN "
                         "('pg_catalog', 'information_schema') AND data_type <> ALL(%s) AND EXISTS (SELECT 1 FROM information_schema.tables t "
                         "WHERE t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE') "
                         "ORDER BY 1, 2, ordinal_position", [list(VOLATILE_TYPES)]).fetchall()
        grouped: dict[tuple[str, str], list[str]] = {}
        for schema, table, column in cols:
            grouped.setdefault((schema, table), []).append(f'"{column}"')
        for (schema, table), columns in grouped.items():
            row_expr = f"row({', '.join(columns)})::text"
            row = c.execute(f"SELECT md5(coalesce(string_agg({row_expr}, '|' ORDER BY {row_expr}), '')) "  # noqa: S608 - names come from the catalog
                            f'FROM "{schema}"."{table}"').fetchone()
            assert row is not None
            out[f"{schema}.{table}"] = str(row[0])
    return out


def _sequences(pg: Pg) -> list[tuple[Any, ...]]:
    with pg.connect() as c:
        return c.execute("SELECT schemaname, sequencename, last_value FROM pg_sequences ORDER BY 1, 2").fetchall()


def _database_level(pg: Pg) -> dict[str, Any]:
    """Everything CREATE DATABASE ... TEMPLATE does not copy, which `build_snapshot` does not (or only partly) show."""
    with pg.connect(dbname="postgres") as c:
        meta = c.execute("SELECT pg_get_userbyid(datdba), datconnlimit, datcollate, datctype, datallowconn, datistemplate, "
                         "shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s", [DB]).fetchone()
        settings = c.execute("SELECT coalesce(r.rolname, '<all roles>'), s.setconfig FROM pg_db_role_setting s "
                             "LEFT JOIN pg_roles r ON r.oid = s.setrole WHERE s.setdatabase = (SELECT oid FROM pg_database WHERE datname = %s) "
                             "ORDER BY 1", [DB]).fetchall()
    return {"meta": meta, "settings": settings}


def _version(pg: Pg) -> str:
    with pg.connect() as c:
        row = c.execute("SELECT version_num FROM platform.alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _fingerprint(pg: Pg) -> dict[str, Any]:
    return {"snapshot": build_snapshot(pg), "rows": _row_counts(pg), "content": _content_hashes(pg), "sequences": _sequences(pg),
            "database_level": _database_level(pg), "version": _version(pg)}


def test_a_clone_is_identical_to_a_fresh_migration(empty_db: Pg, upgrade):
    upgrade()  # the real path: provisioned empty database -> alembic upgrade head
    fresh = _fingerprint(empty_db)
    empty_db.clone_template()
    clone = _fingerprint(empty_db)
    for part in fresh:
        assert clone[part] == fresh[part], f"the clone differs from a fresh migration in: {part}"
    # not a vacuous comparison: the seeded registries really are in both databases
    assert len(fresh["rows"]) > 20
    assert sum(fresh["rows"].values()) > 0
    assert any(h != _EMPTY_HASH for h in fresh["content"].values())
    assert fresh["version"] == ScriptDirectory.from_config(alembic_config()).get_current_head()


_EMPTY_HASH = "d41d8cd98f00b204e9800998ecf8427e"  # md5('') - the hash of a table without rows


def test_the_parity_check_detects_a_clone_whose_database_acl_was_not_reapplied(empty_db: Pg, upgrade):
    """CREATE DATABASE ... TEMPLATE does not copy the database ACL. The comparison above must notice if provisioning were skipped."""
    upgrade()
    fresh = build_snapshot(empty_db)
    try:
        with empty_db.connect(dbname="postgres") as c:
            c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
            c.execute(f"CREATE DATABASE {DB} OWNER ai_res_owner TEMPLATE {TEMPLATE_DB}")  # deliberately without provision()
        broken = build_snapshot(empty_db)
        differing = set(fresh.splitlines()) ^ set(broken.splitlines())
        assert any("DATABASE ACL" in line for line in differing), "the snapshot does not show a lost database ACL"
    finally:
        empty_db.provision()
    assert build_snapshot(empty_db) == fresh


def test_the_content_check_detects_a_changed_seed_value_with_the_same_row_count(migrated: Pg):
    before, counts = _content_hashes(migrated), _row_counts(migrated)
    tampered = None
    with migrated.connect() as c:
        c.execute("SET session_replication_role = replica")  # the registries are guarded by immutability triggers; this connection only, to simulate drift
        candidates = c.execute("SELECT table_schema, table_name, column_name FROM information_schema.columns WHERE data_type = 'text' "
                               "AND table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2, ordinal_position").fetchall()
        for schema, table, column in candidates:
            if not counts.get(f"{schema}.{table}"):
                continue  # only a table that really holds seed rows can show a content change
            try:
                with c.transaction():
                    c.execute(f'UPDATE "{schema}"."{table}" SET "{column}" = "{column}" || \'-x\'')  # noqa: S608 - names come from the catalog
                tampered = f"{schema}.{table}"
                break
            except psycopg.Error:
                continue  # a CHECK / unique constraint rejected this column: try the next one
    assert tampered is not None, "no seeded text column could be tampered with: the test would be vacuous"
    assert _row_counts(migrated) == counts
    assert _content_hashes(migrated)[tampered] != before[tampered]


def test_every_clone_starts_pristine_not_from_the_previous_tests_data(migrated: Pg):
    before = _row_counts(migrated)
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (gen_random_uuid(), 'left behind by a previous test')")
    assert _row_counts(migrated)["organization.organizations"] == before["organization.organizations"] + 1
    migrated.clone_template()
    assert _row_counts(migrated) == before


def test_the_template_is_sealed(migrated: Pg):
    with pytest.raises(psycopg.OperationalError, match="not currently accepting connections"):
        migrated.connect(dbname=TEMPLATE_DB)
    with migrated.connect(dbname="postgres") as c:
        row = c.execute("SELECT datistemplate, datallowconn FROM pg_database WHERE datname = %s", [TEMPLATE_DB]).fetchone()
    assert row == (True, False)
