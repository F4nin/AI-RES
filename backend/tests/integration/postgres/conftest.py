"""Real PostgreSQL 16 (Testcontainers, ADR-003) with the same image tag+digest as the Compose stack. SQLite is never a substitute.

Provisioning mirrors production: a superuser runs ops/postgres/provision_roles.sql (roles, passwords, database grants); the migrator then
runs Alembic as `ai_res_migrator` -> SET ROLE ai_res_owner. Passwords are random per test session and live only in tmp files/memory.
Limitation (documented in the S04 report): the container uses plain TCP, so TLS verify-full and pg_hba are covered by the Compose runtime tests.
"""
import io
import re
import secrets
import tarfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

BACKEND = Path(__file__).resolve().parents[3]
REPO = BACKEND.parent
DB = "ai_res_db"
TEMPLATE_DB = "ai_res_db_template"  # CI-01: ai_res_db migrated once per session, cloned for every `migrated` test (ADR-118)
LOGIN_ROLES = {
    "ai_res_migrator": "migrator_pw", "ai_res_api": "api_pw", "ai_res_outbox_dispatcher": "outbox_pw",
    "ai_res_event_consumer": "consumer_pw", "ai_res_auditor": "auditor_pw", "ai_res_backup": "backup_pw",
}
RUNTIME_ROLES = ("ai_res_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor")
pytestmark = pytest.mark.postgres


def _compose_postgres_image() -> str:
    m = re.search(r"image:\s*(postgres:16[^\s]+@sha256:[0-9a-f]{64})", (REPO / "infra" / "compose.yaml").read_text())
    assert m, "pinned postgres image not found in infra/compose.yaml"
    return m.group(1)


class Pg:
    """Handle to the throw-away server: superuser access, per-role connections and the provisioning step."""

    def __init__(self, container: PostgresContainer, superuser_pw: str, passwords: dict[str, str]) -> None:
        self.container = container
        self.host = container.get_container_host_ip()
        self.port = int(container.get_exposed_port(5432))
        self.superuser_pw = superuser_pw
        self.passwords = passwords  # role -> password

    def connect(self, role: str | None = None, dbname: str = DB, autocommit: bool = True) -> psycopg.Connection[Any]:
        user, pw = ("postgres", self.superuser_pw) if role is None else (role, self.passwords[role])
        return psycopg.connect(host=self.host, port=self.port, dbname=dbname, user=user, password=pw, sslmode="disable", autocommit=autocommit,
                               connect_timeout=10)

    def provision(self) -> None:
        sets = "".join(f"\\set {var} '{self.passwords[role]}'\n" for role, var in LOGIN_ROLES.items())
        wrapper = sets + "\\i /tmp/provision/provision_roles.sql\n"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            roles_sql = (REPO / "infra/config/postgres/provision_roles.sql").read_bytes()
            for name, data in (("provision/wrapper.sql", wrapper.encode()), ("provision/provision_roles.sql", roles_sql)):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o644
                tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        self.container.get_wrapped_container().put_archive("/tmp", buf)  # noqa: S108 - throw-away container
        code, out = self.container.exec(["psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-f", "/tmp/provision/wrapper.sql"])
        assert code == 0, out.decode(errors="replace")[-1500:]

    def reset_database(self) -> None:
        with self.connect(dbname="postgres") as c:
            c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        self.provision()  # creates ai_res_db owned by ai_res_owner, re-applies attributes and grants (also proves idempotency)

    def park_as_template(self) -> None:
        """Renames the freshly migrated ai_res_db to the template database; nobody may connect to it afterwards."""
        with self.connect(dbname="postgres") as c:
            if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", [TEMPLATE_DB]).fetchone():
                c.execute(f"ALTER DATABASE {TEMPLATE_DB} WITH IS_TEMPLATE false")  # a template database cannot be dropped
                c.execute(f"DROP DATABASE {TEMPLATE_DB} WITH (FORCE)")
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", [DB])
            c.execute(f"ALTER DATABASE {DB} RENAME TO {TEMPLATE_DB}")
            c.execute(f"ALTER DATABASE {TEMPLATE_DB} WITH IS_TEMPLATE true ALLOW_CONNECTIONS false")

    def clone_template(self) -> None:
        """Replaces ai_res_db with a copy of the migrated template. CREATE DATABASE copies objects and data but NOT the database ACL or role
        settings, so the idempotent provisioning script is re-applied exactly as after `reset_database` (the parity test proves the result is identical)."""
        with self.connect(dbname="postgres") as c:
            c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
            c.execute(f"CREATE DATABASE {DB} OWNER ai_res_owner TEMPLATE {TEMPLATE_DB}")
        self.provision()


@pytest.fixture(scope="session")
def pg() -> Iterator[Pg]:
    superuser_pw = secrets.token_urlsafe(24)
    passwords = {role: secrets.token_urlsafe(24) for role in LOGIN_ROLES}
    with PostgresContainer(_compose_postgres_image(), username="postgres", password=superuser_pw, dbname="postgres", driver=None) as container:
        yield Pg(container, superuser_pw, passwords)


@pytest.fixture
def empty_db(pg: Pg) -> Pg:
    pg.reset_database()
    return pg


def _migrator_env(pg: Pg, pw_file: Path) -> dict[str, str]:
    return {
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": pg.host, "AI_RES_DB_PORT": str(pg.port), "AI_RES_DB_USER": "ai_res_migrator",
        "AI_RES_DB_PASSWORD_FILE": str(pw_file), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "ai-res-migrate-test",
        "AI_RES_DB_STATEMENT_TIMEOUT_MS": "60000", "AI_RES_DB_LOCK_TIMEOUT_MS": "3000",
    }


@pytest.fixture
def migrate_env(pg: Pg, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Points env.py at the container as ai_res_migrator (password via file, like production)."""
    pw = tmp_path / "migrator_pw"
    pw.write_text(pg.passwords["ai_res_migrator"])
    for k, v in _migrator_env(pg, pw).items():
        monkeypatch.setenv(k, v)
    return lambda **extra: [monkeypatch.setenv(k, v) for k, v in extra.items()] and None


def alembic_config(script_location: Path | None = None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    if script_location is not None:
        cfg.set_main_option("script_location", str(script_location))
    return cfg


@pytest.fixture
def upgrade(empty_db: Pg, migrate_env: Callable[..., None]) -> Callable[..., None]:
    return lambda target="head", cfg=None: command.upgrade(cfg or alembic_config(), target)


@pytest.fixture(scope="session")
def migrated_template(pg: Pg, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Runs the real `alembic upgrade head` from an EMPTY database once per session (as ai_res_migrator, like production) and parks the result as a
    template. Tests that verify the migrations themselves keep using `empty_db` / `upgrade` and are unaffected."""
    pg.reset_database()
    pw = tmp_path_factory.mktemp("template_migrator") / "migrator_pw"
    pw.write_text(pg.passwords["ai_res_migrator"])
    with pytest.MonkeyPatch.context() as mp:
        for k, v in _migrator_env(pg, pw).items():
            mp.setenv(k, v)
        command.upgrade(alembic_config(), "head")
    pg.park_as_template()


@pytest.fixture
def migrated(pg: Pg, migrate_env: Callable[..., None], migrated_template: None) -> Pg:
    """A fresh, fully migrated ai_res_db for this test: a clone of the template (CI-01), not a per-test Alembic run."""
    pg.clone_template()
    return pg


def run_audit(conn: psycopg.Connection[Any], name: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in conn.execute((BACKEND / "ops" / "postgres" / name).read_text().encode()).fetchall()]


# ---------- S07 shared fixtures: organizations/users seeded by the superuser, runtime engines under the real API role ----------
class IamWorld:
    """Two organizations, each with one ACTIVE user, plus a factory for runtime engines (password via file, like production)."""

    def __init__(self, pg: Pg, tmp_path: Path) -> None:
        import uuid
        self.pg, self.tmp_path = pg, tmp_path
        self.org_a, self.org_b = uuid.uuid4(), uuid.uuid4()
        self.user_a, self.user_b = uuid.uuid4(), uuid.uuid4()
        self._engines: list[Any] = []
        with pg.connect() as c:
            for org, user, mail in ((self.org_a, self.user_a, "a@example.com"), (self.org_b, self.user_b, "b@example.com")):
                c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
                c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,'u')",
                          [user, org, mail, mail])
                c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) "
                          "VALUES (gen_random_uuid(), %s, %s, 'AUDITOR')", [org, user])  # an active member (login and sessions require it)

    def engine(self, role: str = "ai_res_api") -> Any:
        from ai_res.db.engine import create_runtime_engine
        from ai_res.platform.config import load_settings
        pw = self.tmp_path / f"{role}_pw"
        pw.write_text(self.pg.passwords[role])
        settings = load_settings({
            "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": self.pg.host, "AI_RES_DB_PORT": str(self.pg.port), "AI_RES_DB_USER": role,
            "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": f"test-{role}", "AI_RES_DB_POOL_SIZE": "8"})
        eng = create_runtime_engine(settings)
        self._engines.append(eng)
        return eng

    async def dispose(self) -> None:
        for eng in self._engines:
            await eng.dispose()


@pytest.fixture
async def iam_world(migrated: Pg, tmp_path: Path) -> Any:
    world = IamWorld(migrated, tmp_path)
    yield world
    await world.dispose()


def seed_worker_definition_version(c: psycopg.Connection[Any], version: str = "wd-test-1", role: str = "REQUIREMENTS", vid: UUID | None = None,
                                  **fields: Any) -> UUID:
    """Registry rows are written by the owner/migrator only (S14, ADR-102): tests seed one as the superuser. Idempotent per (role, version)."""
    vid = vid or uuid4()
    row = {"input_contract_version": "1.1", "output_contract_version": "1.1", "output_schema_id": "test.output", "output_schema_version": "1"} | fields
    c.execute(
        "INSERT INTO agents.worker_definition_versions (id, worker_definition_id, version, input_contract_version, output_contract_version, output_schema_id, "
        "output_schema_version) SELECT %s, d.id, %s, %s, %s, %s, %s FROM agents.worker_definitions d WHERE d.worker_role = %s "
        "ON CONFLICT (worker_definition_id, version) DO NOTHING",
        [vid, version, row["input_contract_version"], row["output_contract_version"], row["output_schema_id"], row["output_schema_version"], role])
    found = c.execute("SELECT v.id FROM agents.worker_definition_versions v JOIN agents.worker_definitions d ON d.id = v.worker_definition_id "
                      "WHERE d.worker_role = %s AND v.version = %s", [role, version]).fetchone()
    assert found is not None
    if (stored := c.execute("SELECT output_schema_id, output_schema_version FROM agents.worker_definition_versions WHERE id = %s", [found[0]]).fetchone()) != (
            row["output_schema_id"], row["output_schema_version"]):
        raise AssertionError(f"version {role}/{version} already exists with other content {stored}: a test would silently use the wrong capability")
    return found[0]
