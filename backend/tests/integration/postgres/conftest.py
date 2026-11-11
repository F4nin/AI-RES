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

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

BACKEND = Path(__file__).resolve().parents[3]
REPO = BACKEND.parent
DB = "ai_res_db"
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


@pytest.fixture
def migrate_env(pg: Pg, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Points env.py at the container as ai_res_migrator (password via file, like production)."""
    pw = tmp_path / "migrator_pw"
    pw.write_text(pg.passwords["ai_res_migrator"])
    for k, v in {
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": pg.host, "AI_RES_DB_PORT": str(pg.port), "AI_RES_DB_USER": "ai_res_migrator",
        "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "ai-res-migrate-test",
        "AI_RES_DB_STATEMENT_TIMEOUT_MS": "60000", "AI_RES_DB_LOCK_TIMEOUT_MS": "3000",
    }.items():
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


@pytest.fixture
def migrated(empty_db: Pg, upgrade: Callable[..., None]) -> Pg:
    upgrade()
    return empty_db


def run_audit(conn: psycopg.Connection[Any], name: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in conn.execute((BACKEND / "ops" / "postgres" / name).read_text().encode()).fetchall()]
