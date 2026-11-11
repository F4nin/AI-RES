# ruff: noqa: E501, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S07 slice 5: one-time bootstrap of the first administrator (AUTH-004): no default credentials, secret presented and compared, single claim, closed afterwards."""
import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ai_res.cli.bootstrap import main as cli_main
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.iam.auth import AuthService
from ai_res.modules.iam.bootstrap import BootstrapError, bootstrap_first_admin
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy

pytestmark = pytest.mark.postgres
SECRET = b"s3cr3t-bootstrap-value-from-compose-secret"
PASSWORD = "an administrator passphrase 2026"


@pytest.fixture
def world(migrated: Any, tmp_path: Path) -> Any:
    from .conftest import IamWorld

    class Empty(IamWorld):
        def __init__(self) -> None:  # no seeded organizations: this is a brand-new installation
            self.pg, self.tmp_path, self._engines = migrated, tmp_path, []

    return Empty()


def hasher() -> PasswordHasherService:
    return PasswordHasherService(time_cost=1, memory_kib=8, parallelism=1)


async def run(world: Any, **kw: Any) -> Any:
    base: dict[str, Any] = {"expected_secret": SECRET, "presented_secret": SECRET, "organization_name": "Acme", "admin_email": "Admin@Example.com",
                            "admin_name": "Ada Admin", "password": PASSWORD}
    base.update(kw)
    try:
        return await bootstrap_first_admin(create_session_factory(world.engine()), hasher(), PasswordPolicy(denylist=frozenset()), **base)
    finally:
        await world.dispose()


def counts(world: Any) -> tuple[int, int, int, int]:
    with world.pg.connect() as c:
        return tuple(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("organization.organizations", "iam.users", "iam.credentials", "platform.bootstrap_state"))  # type: ignore[return-value]


async def test_a_fresh_installation_has_no_users_credentials_or_default_account(world: Any) -> None:
    assert counts(world) == (0, 0, 0, 0)


async def test_bootstrap_creates_owner_with_argon2id_hash_membership_claim_and_audit(world: Any) -> None:
    r = await run(world)
    assert counts(world) == (1, 1, 1, 1)
    with world.pg.connect() as c:
        h = c.execute("SELECT password_hash FROM iam.credentials").fetchone()[0]
        role = c.execute("SELECT role_code FROM organization.memberships WHERE user_id = %s", [r.user_id]).fetchone()[0]
        email = c.execute("SELECT email_normalized FROM iam.users").fetchone()[0]
        audit = c.execute("SELECT action, actor_type, reason_code, details::text FROM audit.audit_events").fetchall()
    assert h.startswith("$argon2id$") and PASSWORD not in h and role == "ORGANIZATION_OWNER" and email == "admin@example.com"
    assert audit == [("AUTH_ACCOUNT_INVITED", "SYSTEM", "bootstrap_first_administrator", '{"role": "ORGANIZATION_OWNER"}')]
    assert SECRET.decode() not in repr(audit)


async def test_the_created_administrator_can_log_in_with_the_chosen_password(world: Any) -> None:
    r = await run(world)
    factory = create_session_factory(world.engine())
    h = hasher()
    sessions = SessionService(factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12), touch_interval=timedelta(minutes=1))
    throttle = LoginThrottle(ThrottlePolicy(account_ip_threshold=5, ip_threshold=20, account_threshold=10, global_threshold=500, base_delay=timedelta(seconds=2),
                                            max_delay=timedelta(seconds=60), window=timedelta(minutes=15)))
    login = await AuthService(factory, sessions, h, PasswordPolicy(denylist=frozenset()), throttle).login(
        organization_id=r.organization_id, email="admin@example.com", password=PASSWORD, client_ip="203.0.113.9", request_id=None)
    assert login.session.user_id == r.user_id and login.mfa_required is False  # the owner must now enrol TOTP before privileged actions


async def test_wrong_or_empty_secret_creates_nothing_and_leaves_bootstrap_available(world: Any) -> None:
    for presented in (b"wrong-secret-value", b"", SECRET + b"x"):
        with pytest.raises(BootstrapError) as e:
            await run(world, presented_secret=presented)
        assert e.value.code == "invalid_secret" and SECRET.decode() not in str(e.value)
    with pytest.raises(BootstrapError):
        await run(world, expected_secret=b"", presented_secret=b"")  # a missing server-side secret never authorises anything
    assert counts(world) == (0, 0, 0, 0)
    await run(world)
    assert counts(world) == (1, 1, 1, 1)


async def test_weak_password_or_bad_input_creates_nothing(world: Any) -> None:
    for kw, code in (({"password": "short"}, "weak_password_too_short"), ({"admin_email": "not-an-email"}, "invalid_email"), ({"organization_name": "  "}, "invalid_name")):
        with pytest.raises(BootstrapError) as e:
            await run(world, **kw)
        assert e.value.code == code
    assert counts(world) == (0, 0, 0, 0)


async def test_second_bootstrap_is_refused_even_with_the_right_secret_and_creates_no_second_organization(world: Any) -> None:
    await run(world)
    with pytest.raises(BootstrapError) as e:
        await run(world, organization_name="Second", admin_email="other@example.com")
    assert e.value.code == "already_bootstrapped"
    assert counts(world) == (1, 1, 1, 1)


async def test_two_concurrent_bootstraps_produce_exactly_one_installation(world: Any) -> None:
    results = await asyncio.gather(run(world, organization_name="A", admin_email="a@example.com"), run(world, organization_name="B", admin_email="b@example.com"), return_exceptions=True)
    assert sum(not isinstance(r, BaseException) for r in results) == 1
    assert [r.code for r in results if isinstance(r, BootstrapError)] == ["already_bootstrapped"]
    assert counts(world) == (1, 1, 1, 1)  # the losing transaction rolled back its organization too


async def test_the_claim_row_cannot_be_changed_or_removed_by_the_api_role(world: Any) -> None:
    r = await run(world)
    for sql in ("UPDATE platform.bootstrap_state SET consumed_at = now()", "DELETE FROM platform.bootstrap_state", "TRUNCATE platform.bootstrap_state"):
        uow = UnitOfWork(create_session_factory(world.engine()))
        with pytest.raises(DBAPIError):
            async with uow:
                await uow.with_tenant(r.organization_id)
                await uow.session.execute(text(sql))
    await world.dispose()
    assert counts(world)[3] == 1


# ---------- CLI ----------
def cli_env(world: Any, tmp_path: Path, with_secret: bool = True) -> dict[str, str]:
    pw = tmp_path / "api_pw"
    pw.write_text(world.pg.passwords["ai_res_api"])
    env = {"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": world.pg.host, "AI_RES_DB_PORT": str(world.pg.port), "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(pw),
           "AI_RES_DB_SSLMODE": "disable", "AI_RES_ARGON2_TIME_COST": "1", "AI_RES_ARGON2_MEMORY_KIB": "8"}
    if with_secret:
        sf = tmp_path / "bootstrap_secret"
        sf.write_bytes(SECRET + b"\n")
        env["AI_RES_BOOTSTRAP_SECRET_FILE"] = str(sf)
    return env


def prompts(*answers: str) -> Any:
    it = iter(answers)
    return lambda _label: next(it)


ARGS = ["--organization-name", "Acme", "--admin-email", "admin@example.com", "--admin-name", "Ada"]


def test_cli_creates_the_administrator_prints_only_ids_and_never_the_secrets(world: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_main(ARGS, cli_env(world, tmp_path), prompts(SECRET.decode(), PASSWORD, PASSWORD))
    out = capsys.readouterr()
    assert code == 0 and "organization_id=" in out.out and "user_id=" in out.out
    assert SECRET.decode() not in out.out + out.err and PASSWORD not in out.out + out.err
    assert counts(world) == (1, 1, 1, 1)


def test_cli_exit_codes_for_refusals_and_configuration_errors(world: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(ARGS, cli_env(world, tmp_path), prompts("wrong", PASSWORD, PASSWORD)) == 2
    assert cli_main(ARGS, cli_env(world, tmp_path), prompts(SECRET.decode(), PASSWORD, "different")) == 2  # password confirmation mismatch
    assert cli_main(ARGS, cli_env(world, tmp_path, with_secret=False), prompts(SECRET.decode(), PASSWORD, PASSWORD)) == 1
    err = capsys.readouterr().err
    assert "invalid_secret" in err and "password_mismatch" in err and "configuration error" in err
    assert SECRET.decode() not in err and PASSWORD not in err
    assert counts(world) == (0, 0, 0, 0)
    assert cli_main(ARGS, cli_env(world, tmp_path), prompts(SECRET.decode(), PASSWORD, PASSWORD)) == 0
    assert cli_main(ARGS, cli_env(world, tmp_path), prompts(SECRET.decode(), PASSWORD, PASSWORD)) == 2  # one time only
