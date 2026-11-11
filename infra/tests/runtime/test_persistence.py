"""S04 runtime evidence against the live stack: migration job outcome, role/grant state, network access per role, and the automated
audit SQL (backend/ops/postgres). Negative checks have positive controls. A skipped run is NOT evidence."""
import re
from pathlib import Path

import pytest

from tests.runtime.helpers import exec_in, inspect
from tests.runtime.test_stack import _psql

pytestmark = pytest.mark.runtime
BACKEND = Path(__file__).resolve().parents[3] / "backend"
OPS = BACKEND / "ops" / "postgres"
HEAD = re.search(r'revision: str = "([0-9a-f]+)"', next((BACKEND / "src/ai_res/db/migrations/versions").glob("0001_*.py")).read_text()).group(1)
SCHEMAS = ["iam", "organization", "project", "work", "requirements", "sources", "knowledge", "decisions", "artifacts", "traceability",
           "governance", "agents", "context", "integrations", "audit", "platform", "operations", "execution"]


def _su(sql, secret_values, db="ai_res_db"):
    return _psql("postgres", "postgres_superuser_password", db, sql, secret_values)


def _as(user, secret, sql, secret_values, db="ai_res_db", sslmode="require"):
    """Over TCP + TLS from inside the postgres container, so that pg_hba (hostssl rules) is what is being exercised."""
    pgpass = f"postgres:5432:*:{user}:{secret_values[secret]}\n"
    sql_q = sql.replace("'", "'\\''")
    script = ("cat > /tmp/pgpass.t && chmod 600 /tmp/pgpass.t && PGPASSFILE=/tmp/pgpass.t PGSSLMODE=" + sslmode
              + f" psql -v ON_ERROR_STOP=1 -tA -h postgres -U {user} -d {db} -c '{sql_q}'; rc=$?; rm -f /tmp/pgpass.t; exit $rc")
    return exec_in("postgres", "sh", "-c", script, stdin=pgpass)


def test_migrate_job_completed_and_database_is_at_head(secret_values):
    st = inspect("migrate")["State"]
    assert st["Status"] == "exited" and st["ExitCode"] == 0
    assert _su("select version_num from platform.alembic_version", secret_values).stdout.strip() == HEAD
    names = "','".join(SCHEMAS)  # constant list defined in this module, not external input
    owned = _su(f"select count(*) from pg_namespace where nspname in ('{names}') and pg_get_userbyid(nspowner)='ai_res_owner'", secret_values)  # noqa: S608
    assert owned.stdout.strip() == "18"


def test_langgraph_and_temporal_are_not_managed_by_alembic(secret_values):
    r = _su("select nspname||':'||pg_get_userbyid(nspowner) from pg_namespace where nspname='langgraph'", secret_values)
    assert r.stdout.strip() == "langgraph:ai_res_owner"  # created by S03 provisioning, untouched by migrations (ADR-036)
    assert not {"temporal", "langgraph"} & set(SCHEMAS)  # the allowlist itself never contains foreign schemas
    assert _su("select to_regclass('platform.alembic_version') is not null", secret_values).stdout.strip() == "t"


def _install_audit_scripts(secret_values) -> None:
    """Copies audit.sh + SQL into the postgres container (tmpfs /tmp) exactly as they are in the repository."""
    for name in ("audit.sh", "preflight.sql", "postflight.sql", "grants_audit.sql", "rls_coverage.sql"):
        res = exec_in("postgres", "sh", "-c", f"mkdir -p /tmp/audit && cat > /tmp/audit/{name}", stdin=OPS.joinpath(name).read_text())
        assert res.returncode == 0, res.stderr


def _audit(secret_values, mode="post"):
    pgpass = f"localhost:5432:*:postgres:{secret_values['postgres_superuser_password']}\n"
    script = ("cat > /tmp/pgpass.t && chmod 600 /tmp/pgpass.t && PGPASSFILE=/tmp/pgpass.t PGHOST=/var/run/postgresql PGUSER=postgres PGDATABASE=ai_res_db "
              f"sh /tmp/audit/audit.sh {mode}; rc=$?; rm -f /tmp/pgpass.t; exit $rc")
    return exec_in("postgres", "sh", "-c", script, stdin=pgpass)


def test_audit_gate_passes_on_the_clean_live_database(secret_values):
    """Grants audit / postflight / RLS coverage run through the same gate script the release uses (CI gate for persistence)."""
    _install_audit_scripts(secret_values)
    res = _audit(secret_values)
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
    assert "no violations" in res.stdout


def test_audit_gate_fails_on_a_deliberately_broken_state_positive_control(secret_values):
    """A gate that cannot fail proves nothing: create real drift, expect exit 1 and the specific check names, then clean up."""
    _install_audit_scripts(secret_values)
    assert _su("create table work.s04_gate_probe(id int, organization_id uuid)", secret_values).returncode == 0
    try:
        res = _audit(secret_values)
        assert res.returncode == 1, f"{res.stdout}\n{res.stderr}"
        for check in ("non_owner_owns_app_object", "rls_not_enabled_and_forced", "table_without_rls_not_exempt"):
            assert check in res.stdout, res.stdout
    finally:
        assert _su("drop table if exists work.s04_gate_probe", secret_values).returncode == 0
    assert _audit(secret_values).returncode == 0  # clean again


def test_preflight_gate_is_clean_on_the_live_database(secret_values):
    _install_audit_scripts(secret_values)
    res = _audit(secret_values, "preflight")
    # the bootstrap superuser is the connecting identity here, which preflight (correctly) reports; the migration identity is checked in Testcontainers
    assert res.returncode == 1 and "connected_as_privileged" in res.stdout, f"{res.stdout}\n{res.stderr}"


def test_all_domain_roles_have_scram_passwords_and_no_privileged_attributes(secret_values):
    r = _su("select count(*) from pg_roles where rolname like 'ai\\_res\\_%' and (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls)",
            secret_values, "postgres")
    assert r.stdout.strip() == "0"
    r = _su("select count(*) from pg_authid where rolname in ('ai_res_migrator','ai_res_api','ai_res_outbox_dispatcher','ai_res_event_consumer',"
            "'ai_res_auditor','ai_res_backup') and rolpassword like 'SCRAM-SHA-256$%'", secret_values, "postgres")
    assert r.stdout.strip() == "6"


def test_runtime_roles_connect_over_tls_with_fixed_search_path_and_cannot_ddl(secret_values):
    for user, secret in (("ai_res_api", "api_db_password"), ("ai_res_outbox_dispatcher", "outbox_db_password"),
                         ("ai_res_event_consumer", "consumer_db_password"), ("ai_res_auditor", "auditor_db_password")):
        assert _as(user, secret, "show search_path", secret_values).stdout.strip() == "pg_catalog"  # positive control: login works
        for ddl in ("create table work.s04_probe(id int)", "create schema evil", "create table public.s04_probe(id int)"):
            r = _as(user, secret, ddl, secret_values)
            assert r.returncode != 0 and "permission denied" in r.stderr, (user, ddl, r.stderr)
        r = _as(user, secret, "set role ai_res_owner", secret_values)
        assert r.returncode != 0 and "permission denied" in r.stderr, r.stderr


def test_migrator_may_set_role_owner_but_not_create_without_it(secret_values):
    assert _as("ai_res_migrator", "migrator_db_password", "select 1", secret_values).stdout.strip() == "1"
    r = _as("ai_res_migrator", "migrator_db_password", "create table work.s04_probe(id int)", secret_values)
    assert r.returncode != 0 and "permission denied" in r.stderr


def test_cleartext_cross_database_and_backup_identity_are_rejected_by_pg_hba(secret_values):
    assert _as("ai_res_api", "api_db_password", "select 1", secret_values).stdout.strip() == "1"  # positive control: same credentials work over TLS
    clear = _as("ai_res_api", "api_db_password", "select 1", secret_values, sslmode="disable")
    assert clear.returncode != 0 and "pg_hba.conf" in clear.stderr
    other = _as("ai_res_api", "api_db_password", "select 1", secret_values, db="temporal_db")
    assert other.returncode != 0 and "pg_hba.conf" in other.stderr
    backup = _as("ai_res_backup", "backup_db_password", "select 1", secret_values)
    assert backup.returncode != 0 and "pg_hba.conf" in backup.stderr  # no hba line on purpose (S32)
    cross = _as("temporal", "temporal_db_password", "select 1", secret_values, db="ai_res_db")
    assert cross.returncode != 0 and "pg_hba.conf" in cross.stderr


def test_api_and_other_runtime_containers_have_no_database_credentials():
    """PERSIST-023 (credential part): the API does not get DB passwords until a stage needs them; Manager/Worker never do."""
    env = inspect("api")["Config"]["Env"]
    assert not [e for e in env if e.startswith("AI_RES_DB_")], "api must not be configured with database credentials in S04"
    for svc in ("api", "reverse-proxy", "temporal-ui", "otel-collector", "minio"):
        mounted = {m["Destination"] for m in inspect(svc)["Mounts"] if "_db_password" in m["Destination"]}
        assert not mounted, (svc, mounted)


def test_api_startup_does_not_run_migrations():
    """The API container's command is the server, not alembic; migrations exist only as the separate `migrate` job. The unit test
    tests/unit/test_no_startup_migration.py proves the application code never imports Alembic. (Decision: the API and migrate jobs share
    one image, so Alembic is present in it; it is never started by the API process.)"""
    cfg = inspect("api")["Config"]
    assert "alembic" not in " ".join([*(cfg.get("Cmd") or []), *(cfg.get("Entrypoint") or [])]).lower()
    mig = inspect("migrate")["Config"]
    assert (mig.get("Cmd") or [])[:1] == ["alembic"]
    from tests.runtime.helpers import compose
    res = compose("logs", "api")
    assert res.returncode == 0 and res.stdout.strip(), "api logs must be readable and non-empty for this check to mean anything"
    assert "alembic" not in res.stdout.lower() and "migrat" not in res.stdout.lower()
