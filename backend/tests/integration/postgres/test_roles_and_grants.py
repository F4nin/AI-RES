"""Runtime-role security (PERSIST-005/006/007 foundations, DBM-006/012/016). Every assertion runs under REAL login roles, never owner/superuser."""
import pytest
from psycopg import errors

from ai_res.db.base import DOMAIN_SCHEMAS

from .conftest import RUNTIME_ROLES, Pg, run_audit

pytestmark = pytest.mark.postgres
ALL_LOGIN = (*RUNTIME_ROLES, "ai_res_migrator", "ai_res_backup")
USAGE = {
    "ai_res_api": set(DOMAIN_SCHEMAS),
    "ai_res_outbox_dispatcher": {"operations", "agents", "audit"},
    "ai_res_event_consumer": {"operations", "agents", "execution", "audit"},
    "ai_res_auditor": {"audit"},
}


def test_no_privileged_attributes_and_owner_is_nologin(migrated: Pg):
    with migrated.connect() as c:
        rows = c.execute(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname LIKE 'ai\\_res\\_%'"
        ).fetchall()
        assert {r[0] for r in rows} >= {"ai_res_owner", "ai_res_migrator", "ai_res_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer",
                                         "ai_res_auditor", "ai_res_backup", "ai_res_api_group", "ai_res_outbox_group", "ai_res_consumer_group",
                                         "ai_res_auditor_group", "ai_res_checkpointer_group"}
        assert all(not any(r[1:6]) for r in rows), rows  # PERSIST-007: no SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS anywhere
        assert [r[6] for r in rows if r[0] == "ai_res_owner"] == [False]
        assert not any(r[6] for r in rows if r[0].endswith("_group"))
        assert c.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'ai\\_res\\_%' AND rolname ~ '(manager|worker)'").fetchone() == (0,)  # ADR-015


def test_passwords_are_scram_only(migrated: Pg):
    with migrated.connect() as c:
        stored = c.execute("SELECT rolname, rolpassword FROM pg_authid WHERE rolname = ANY(%s)", [list(ALL_LOGIN)]).fetchall()
    assert len(stored) == len(ALL_LOGIN) and all(p.startswith("SCRAM-SHA-256$") for _, p in stored)


@pytest.mark.parametrize("role", RUNTIME_ROLES)
def test_runtime_role_cannot_do_ddl_or_escalate(migrated: Pg, role: str):
    with migrated.connect() as owner_side:  # a table that exists, owned by the owner role, to attack with ALTER/DROP/TRUNCATE
        owner_side.execute("SET ROLE ai_res_owner")
        owner_side.execute("CREATE TABLE IF NOT EXISTS work.attack_target (id int)")
        owner_side.execute("RESET ROLE")
    with migrated.connect(role) as c:
        for stmt in (
            "CREATE TABLE work.x (id int)", "CREATE TABLE public.x (id int)", "CREATE SCHEMA evil", "CREATE TABLE audit.x (id int)",
            "ALTER TABLE work.attack_target ADD COLUMN y int", "DROP TABLE work.attack_target", "TRUNCATE work.attack_target",
            "DROP SCHEMA work", "CREATE ROLE evil", "ALTER ROLE ai_res_api BYPASSRLS", "SET ROLE ai_res_owner", "SET ROLE ai_res_migrator",
            "CREATE EXTENSION pg_trgm", "CREATE TEMP TABLE t (id int)", "COPY (SELECT 1) TO PROGRAM 'id'",
        ):
            with pytest.raises(errors.InsufficientPrivilege):  # exactly "permission denied": "object not found" would be a vacuous pass
                c.execute(stmt.encode())
        with pytest.raises(errors.InsufficientPrivilege):  # default privileges keep new owner objects closed (PERSIST-006 shape)
            c.execute("SELECT * FROM work.attack_target")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("DELETE FROM work.attack_target")


def test_default_privileges_close_new_functions_to_public(migrated: Pg):
    """The substantive effect of ALTER DEFAULT PRIVILEGES (tables/sequences are closed anyway): a function created by the owner is not
    executable by PUBLIC, hence not by runtime roles that merely have USAGE on the schema."""
    with migrated.connect() as c:
        c.execute("SET ROLE ai_res_owner")
        c.execute("CREATE FUNCTION work.s04_probe_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        c.execute("RESET ROLE")
        assert c.execute("SELECT has_function_privilege('ai_res_api', 'work.s04_probe_fn()', 'EXECUTE')").fetchone() == (False,)
        assert c.execute("SELECT has_function_privilege('ai_res_owner', 'work.s04_probe_fn()', 'EXECUTE')").fetchone() == (True,)  # positive control
    with migrated.connect("ai_res_api") as api, pytest.raises(errors.InsufficientPrivilege):
        api.execute("SELECT work.s04_probe_fn()")


def test_ddl_is_migrator_only_and_requires_set_role(migrated: Pg):
    with migrated.connect("ai_res_migrator") as c:
        with pytest.raises(errors.InsufficientPrivilege):  # connecting as the migrator is not enough: it owns nothing and has no CREATE
            c.execute("CREATE TABLE work.direct (id int)")
        c.execute("SET ROLE ai_res_owner")
        c.execute("CREATE TABLE work.via_owner (id int)")
        assert c.execute("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.via_owner'::regclass").fetchone() == ("ai_res_owner",)
        c.execute("DROP TABLE work.via_owner")


def test_backup_identity_has_no_application_access(migrated: Pg):
    import psycopg
    with pytest.raises(psycopg.OperationalError, match="permission denied|not allowed"):
        migrated.connect("ai_res_backup")


def test_schema_privilege_matrix_is_least_privilege(migrated: Pg):
    with migrated.connect() as c:
        for role in ("ai_res_migrator", "ai_res_backup", *RUNTIME_ROLES):
            for schema in (*DOMAIN_SCHEMAS, "public"):
                assert c.execute("SELECT has_schema_privilege(%s, %s, 'CREATE')", [role, schema]).fetchone() == (False,), (role, schema)
        for role, expected in USAGE.items():
            actual = {s for s in DOMAIN_SCHEMAS if c.execute("SELECT has_schema_privilege(%s, %s, 'USAGE')", [role, s]).fetchone() == (True,)}
            assert actual == expected, (role, actual ^ expected)
        for s in DOMAIN_SCHEMAS:  # PUBLIC has nothing in domain schemas
            assert c.execute("SELECT count(*) FROM pg_namespace n, aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a "
                             "WHERE n.nspname=%s AND a.grantee=0", [s]).fetchone() == (0,), s
        assert c.execute("SELECT has_database_privilege('ai_res_api', 'ai_res_db', 'CREATE'), has_database_privilege('ai_res_api', 'ai_res_db', 'TEMPORARY')"
                         ).fetchone() == (False, False)


@pytest.mark.parametrize("role", RUNTIME_ROLES)
def test_runtime_session_defaults_fix_search_path_and_timeouts(migrated: Pg, role: str):
    with migrated.connect(role) as c:
        assert c.execute("SHOW search_path").fetchone() == ("pg_catalog",)
        assert c.execute("SHOW statement_timeout").fetchone() == ("15s",)
        assert c.execute("SHOW lock_timeout").fetchone() == ("2s",)
        assert c.execute("SHOW idle_in_transaction_session_timeout").fetchone() == ("30s",)
        assert c.execute("SELECT current_setting('app.organization_id', true)").fetchone() in {(None,), ("",)}  # no tenant GUC at role level


def test_grants_audit_detects_forbidden_privileges(migrated: Pg):
    with migrated.connect() as c:
        c.execute("SET ROLE ai_res_owner")
        c.execute("CREATE TABLE work.audit_probe (id int)")
        c.execute("RESET ROLE")
        assert run_audit(c, "grants_audit.sql") == []
        c.execute("GRANT TRUNCATE, DELETE, SELECT ON work.audit_probe TO ai_res_api_group")
        c.execute("GRANT CREATE ON SCHEMA work TO ai_res_event_consumer")
        c.execute("GRANT pg_read_all_data TO ai_res_auditor")
        found = {k for k, _ in run_audit(c, "grants_audit.sql")}
        assert {"forbidden_table_privilege", "api_delete_privilege", "runtime_can_create_in_schema", "runtime_predefined_role"} <= found


def test_postflight_detects_drift(migrated: Pg):
    with migrated.connect() as c:
        c.execute("CREATE SCHEMA rogue")
        c.execute("GRANT USAGE ON SCHEMA iam TO PUBLIC")
        c.execute("GRANT CREATE ON SCHEMA public TO PUBLIC")
        c.execute("ALTER ROLE ai_res_api RESET search_path")
        found = {k for k, _ in run_audit(c, "postflight.sql")}
    assert {"unexpected_schema", "public_has_schema_privilege", "runtime_search_path_not_fixed"} <= found


# Every violation class of the audit SQL must fire on a deliberately broken state (otherwise "empty result" proves nothing). (sql, audit file, expected check)
SABOTAGE = [
    ("ALTER ROLE ai_res_api BYPASSRLS", "postflight.sql", "forbidden_role_attribute"),
    ("ALTER ROLE ai_res_owner LOGIN", "postflight.sql", "owner_can_login"),
    ("GRANT ai_res_owner TO ai_res_auditor", "postflight.sql", "member_of_owner"),
    ("ALTER SCHEMA iam OWNER TO postgres", "postflight.sql", "schema_not_owned_by_owner"),
    ("CREATE SCHEMA rogue", "postflight.sql", "unexpected_schema"),
    ("GRANT USAGE ON SCHEMA iam TO PUBLIC", "postflight.sql", "public_has_schema_privilege"),
    ("GRANT CONNECT ON DATABASE ai_res_db TO PUBLIC", "postflight.sql", "public_database_privilege"),
    ("ALTER ROLE ai_res_api RESET search_path", "postflight.sql", "runtime_search_path_not_fixed"),
    ("ALTER ROLE ai_res_api IN DATABASE ai_res_db SET search_path = public", "postflight.sql", "role_setting_in_database"),
    ("ALTER ROLE ai_res_api SET app.organization_id = '00000000-0000-0000-0000-000000000001'", "postflight.sql", "tenant_guc_in_role_setting"),
    ("GRANT ai_res_api_group TO ai_res_api WITH ADMIN OPTION", "postflight.sql", "membership_admin_option"),
    ("GRANT ai_res_api_group TO ai_res_api WITH SET TRUE", "postflight.sql", "membership_set_option"),
    ("ALTER DATABASE ai_res_db OWNER TO postgres", "postflight.sql", "database_not_owned_by_owner"),
    ("DROP TABLE platform.alembic_version", "postflight.sql", "missing_version_table"),
    ("INSERT INTO platform.alembic_version VALUES ('x')", "postflight.sql", "version_table_rows"),
    ("DROP SCHEMA operations", "postflight.sql", "missing_schema"),
    ("GRANT TRUNCATE ON platform.alembic_version TO ai_res_api_group", "grants_audit.sql", "forbidden_table_privilege"),
    ("GRANT DELETE ON platform.alembic_version TO ai_res_api", "grants_audit.sql", "api_delete_privilege"),
    ("GRANT INSERT (version_num) ON platform.alembic_version TO ai_res_auditor", "grants_audit.sql", "read_only_role_can_write"),
    ("GRANT CREATE ON SCHEMA work TO ai_res_outbox_dispatcher", "grants_audit.sql", "runtime_can_create_in_schema"),
    ("GRANT TEMPORARY ON DATABASE ai_res_db TO ai_res_event_consumer", "grants_audit.sql", "runtime_database_privilege"),
    ("GRANT pg_read_all_data TO ai_res_api", "grants_audit.sql", "runtime_predefined_role"),
    ("ALTER TABLE platform.alembic_version OWNER TO ai_res_api", "grants_audit.sql", "runtime_owns_object"),
    ("ALTER SCHEMA work OWNER TO ai_res_api", "grants_audit.sql", "runtime_owns_schema"),
    ("ALTER TABLE platform.alembic_version OWNER TO postgres", "grants_audit.sql", "non_owner_owns_app_object"),
    ("CREATE FUNCTION work.fn() RETURNS int LANGUAGE sql AS 'SELECT 1'", "grants_audit.sql", "non_owner_owns_function_or_type"),
    ("CREATE FUNCTION work.fn() RETURNS int LANGUAGE sql AS 'SELECT 1'", "grants_audit.sql", "public_execute_on_function"),
    ("CREATE FUNCTION work.fn() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'", "grants_audit.sql", "security_definer_function"),
    ("CREATE TYPE work.ty AS ENUM ('a')", "grants_audit.sql", "public_usage_on_type"),
    ("ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner GRANT EXECUTE ON FUNCTIONS TO PUBLIC", "grants_audit.sql", "default_acl_missing"),
    ("CREATE TABLE work.t1 (id int)", "rls_coverage.sql", "table_without_rls_not_exempt"),
    ("CREATE TABLE work.t2 (id int, organization_id uuid)", "rls_coverage.sql", "rls_not_enabled_and_forced"),
    ("CREATE TABLE work.t3 (id int); ALTER TABLE work.t3 ENABLE ROW LEVEL SECURITY; ALTER TABLE work.t3 FORCE ROW LEVEL SECURITY",
     "rls_coverage.sql", "rls_without_policy"),
    ("CREATE TABLE work.t4 (id int); ALTER TABLE work.t4 ENABLE ROW LEVEL SECURITY; ALTER TABLE work.t4 FORCE ROW LEVEL SECURITY; "
     "CREATE POLICY p ON work.t4 FOR ALL TO PUBLIC USING (id = 1)", "rls_coverage.sql", "rls_policy_to_public"),
    ("CREATE TABLE work.t5 (id int); ALTER TABLE work.t5 ENABLE ROW LEVEL SECURITY; ALTER TABLE work.t5 FORCE ROW LEVEL SECURITY; "
     "CREATE POLICY p ON work.t5 FOR ALL TO ai_res_api_group USING (true)", "rls_coverage.sql", "rls_policy_always_true"),
    ("CREATE VIEW work.v1 AS SELECT 1 AS x", "rls_coverage.sql", "view_without_security_invoker"),
    ("CREATE MATERIALIZED VIEW work.mv1 AS SELECT 1 AS x", "rls_coverage.sql", "materialized_view_in_domain_schema"),
]


@pytest.mark.parametrize("sabotage, audit, expected", SABOTAGE, ids=[f"{a.split('.')[0]}:{e}" for _, a, e in SABOTAGE])
def test_every_audit_check_fires_on_a_broken_state(migrated: Pg, sabotage: str, audit: str, expected: str):
    with migrated.connect() as c:
        assert run_audit(c, audit) == [], "precondition: the audited state is clean before sabotage"
        for stmt in sabotage.split("; "):
            c.execute(stmt.encode())
        assert expected in {k for k, _ in run_audit(c, audit)}


def test_audits_report_missing_roles_instead_of_passing_vacuously(migrated: Pg):
    with migrated.connect() as c:
        c.execute("ALTER ROLE ai_res_backup RENAME TO ai_res_backup_gone")
        try:
            assert ("missing_role", "ai_res_backup") in run_audit(c, "postflight.sql")
            assert ("missing_role", "ai_res_backup") in run_audit(c, "grants_audit.sql")
            assert "missing_role" in {k for k, _ in run_audit(c, "preflight.sql")}
        finally:
            c.execute("ALTER ROLE ai_res_backup_gone RENAME TO ai_res_backup")


def test_checkpointer_role_is_audited_when_present(migrated: Pg):
    """ADR-036: infra provisioning creates ai_res_checkpointer; it must never gain rights in the domain schemas."""
    with migrated.connect() as c:
        c.execute("CREATE ROLE ai_res_checkpointer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        try:
            assert run_audit(c, "grants_audit.sql") == []
            c.execute("GRANT USAGE ON SCHEMA iam TO ai_res_checkpointer")
            assert any(k == "checkpointer_in_domain_schema" for k, _ in run_audit(c, "grants_audit.sql"))
        finally:
            c.execute("REVOKE USAGE ON SCHEMA iam FROM ai_res_checkpointer")
            c.execute("DROP ROLE ai_res_checkpointer")
