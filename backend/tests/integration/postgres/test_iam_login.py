# ruff: noqa: E501, S106, S608  -- fixed literal SQL in test helpers
"""S07 slice 3: local login, logout, password change under the real API role (AUTH-003/005/007/008/013, fixation, rate limiting)."""
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.auth import AuthService
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy
from ai_res.modules.iam.sessions import AuthFailure, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy
from ai_res.platform.problems import ErrorCode, ProblemError

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
WRONG = "wrong-password-123"  # fake test input, named neutrally so the repository secret scan keeps scanning this file
WRONG_CURRENT = "not-the-password-1"
PASSWORD = "correct horse battery staple 42"
IP = "203.0.113.9"


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class CountingHasher(PasswordHasherService):
    """Counts credential verifications: every login path must spend exactly one (AUTH-005)."""

    def __init__(self, **kw: int) -> None:
        super().__init__(**kw)
        self.verifications = 0

    def verify(self, stored_hash: str, password: str) -> bool:
        self.verifications += 1
        return super().verify(stored_hash, password)

    # verify_unknown_account() verifies a decoy through self.verify(), so it is counted there exactly once


class Rig:
    def __init__(self, world: Any, clock: Clock) -> None:
        self.world, self.clock = world, clock
        factory = create_session_factory(world.engine())
        self.hasher = CountingHasher(time_cost=1, memory_kib=8, parallelism=1)
        self.sessions = SessionService(factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12), touch_interval=timedelta(minutes=1), clock=clock)
        self.throttle = LoginThrottle(ThrottlePolicy(account_ip_threshold=3, ip_threshold=20, account_threshold=10, global_threshold=500, base_delay=timedelta(seconds=2),
                                                     max_delay=timedelta(seconds=60), window=timedelta(minutes=15)), clock)
        self.auth = AuthService(factory, self.sessions, self.hasher, PasswordPolicy(denylist=frozenset()), self.throttle, clock=clock)
        with world.pg.connect() as c:
            c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)",
                      [uuid4(), world.org_a, world.user_a, self.hasher.hash(PASSWORD)])
        self.hasher.verifications = 0

    async def login(self, email: str = "a@example.com", password: str = PASSWORD, ip: str = IP, org: Any = None, **kw: Any) -> Any:
        return await self.auth.login(organization_id=org or self.world.org_a, email=email, password=password, client_ip=ip, request_id="req-abcdef12", **kw)

    def audit(self, action: str | None = None) -> list[tuple[Any, ...]]:
        sql = "SELECT action, result, reason_code, actor_id, details::text FROM audit.audit_events" + (" WHERE action = %s" if action else "") + " ORDER BY occurred_at, id"
        with self.world.pg.connect() as c:
            return c.execute(sql, [action] if action else []).fetchall()


@pytest.fixture
def rig(iam_world: Any) -> Rig:
    return Rig(iam_world, Clock())


async def test_successful_login_issues_session_audits_and_stores_no_plaintext(rig: Rig) -> None:
    r = await rig.login(email="  A@Example.COM ")  # case/space-insensitive login identifier
    assert r.mfa_required is False
    assert (await rig.sessions.authenticate(r.session.token)).session is not None
    rows = rig.audit("AUTH_LOGIN_SUCCEEDED")
    assert len(rows) == 1 and rows[0][1] == "SUCCEEDED" and rows[0][3] == rig.world.user_a
    with rig.world.pg.connect() as c:
        stored = c.execute("SELECT password_hash FROM iam.credentials").fetchone()[0]
    assert stored.startswith("$argon2id$") and PASSWORD not in stored
    assert PASSWORD not in repr(rig.audit())


@pytest.mark.parametrize("case", ["wrong_password", "unknown_user", "disabled_user", "unknown_org", "no_credential"])
async def test_every_failure_path_is_one_identical_401_and_spends_exactly_one_verification(rig: Rig, case: str) -> None:
    kw: dict[str, Any] = {}
    if case == "wrong_password":
        kw = {"password": PASSWORD + "x"}
    elif case == "unknown_user":
        kw = {"email": "nobody@example.com"}
    elif case == "disabled_user":
        with rig.world.pg.connect() as c:
            c.execute("UPDATE iam.users SET status='DISABLED', row_version=row_version+1 WHERE id=%s", [rig.world.user_a])
    elif case == "unknown_org":
        kw = {"org": uuid4()}
    elif case == "no_credential":
        kw = {"email": "b@example.com", "org": rig.world.org_b}  # user exists, has no credential row
    with pytest.raises(ProblemError) as e:
        await rig.login(**kw)
    assert e.value.code is ErrorCode.AUTHENTICATION_REQUIRED and e.value.status == 401
    assert e.value.detail == "Invalid credentials." and e.value.errors is None
    assert rig.hasher.verifications == 1  # same work whether or not the account exists (AUTH-005)


async def test_failures_are_audited_with_operational_reason_but_client_gets_none(rig: Rig) -> None:
    for kw in ({"password": "x" * 20}, {"email": "ghost@example.com"}):
        with pytest.raises(ProblemError):
            await rig.login(**kw)
    reasons = [r[2] for r in rig.audit("AUTH_LOGIN_FAILED")]
    assert reasons == ["invalid_credentials", "unknown_account"]
    assert rig.audit("AUTH_LOGIN_FAILED")[1][3] is None  # no actor for an unknown account
    assert "x" * 20 not in repr(rig.audit())


async def test_brute_force_is_throttled_before_any_password_check_and_audited_once(rig: Rig) -> None:
    for _ in range(3):
        with pytest.raises(ProblemError):
            await rig.login(password=WRONG)
    before = rig.hasher.verifications
    with pytest.raises(ProblemError) as e:
        await rig.login(password=WRONG)
    assert e.value.code is ErrorCode.RATE_LIMITED and e.value.status == 429 and int(e.value.headers["Retry-After"]) >= 1
    assert rig.hasher.verifications == before  # refused before any credential check: no oracle
    assert len(rig.audit("AUTH_RATE_LIMITED")) == 1  # the transition into the block, not every refused request


async def test_a_nonexistent_account_is_throttled_exactly_like_an_existing_one(rig: Rig) -> None:
    for _ in range(3):
        with pytest.raises(ProblemError):
            await rig.login(email="ghost@example.com", password=WRONG)
    with pytest.raises(ProblemError) as e:
        await rig.login(email="ghost@example.com", password=WRONG)
    assert e.value.code is ErrorCode.RATE_LIMITED and e.value.status == 429


async def test_correct_password_during_a_block_is_still_refused_without_revealing_it_was_correct(rig: Rig) -> None:
    for _ in range(3):
        with pytest.raises(ProblemError):
            await rig.login(password=WRONG)
    with pytest.raises(ProblemError) as e:
        await rig.login()  # the right password
    assert e.value.code is ErrorCode.RATE_LIMITED
    rig.clock.now += timedelta(seconds=30)  # the delay has passed
    assert (await rig.login()).session.token


async def test_a_block_on_one_address_does_not_lock_the_real_user_out_elsewhere(rig: Rig) -> None:
    for _ in range(3):
        with pytest.raises(ProblemError):
            await rig.login(password=WRONG, ip="198.51.100.66")
    assert (await rig.login(ip="203.0.113.50")).session.token


async def test_login_replaces_a_presented_session_so_a_planted_cookie_is_dead_after_login(rig: Rig) -> None:
    planted = await rig.sessions.create(rig.world.org_a, rig.world.user_a)
    current = (await rig.sessions.authenticate(planted.token)).session
    r = await rig.login(replace=current)
    assert r.session.token != planted.token
    assert (await rig.sessions.authenticate(planted.token)).failure is AuthFailure.REVOKED


async def test_login_rehashes_when_cost_parameters_were_raised(rig: Rig) -> None:
    stronger = CountingHasher(time_cost=2, memory_kib=16, parallelism=1)
    rig.auth = AuthService(create_session_factory(rig.world.engine()), rig.sessions, stronger, PasswordPolicy(denylist=frozenset()), rig.throttle, clock=rig.clock)
    with rig.world.pg.connect() as c:
        before = c.execute("SELECT password_hash FROM iam.credentials").fetchone()[0]
    await rig.login()
    with rig.world.pg.connect() as c:
        after, version = c.execute("SELECT password_hash, row_version FROM iam.credentials").fetchone()
    assert after != before and "t=2" in after and version == 2 and stronger.verify(after, PASSWORD)


async def test_mfa_required_flag_reflects_an_active_totp_factor(rig: Rig) -> None:
    with rig.world.pg.connect() as c:
        c.execute("INSERT INTO iam.mfa_factors (id, organization_id, user_id, factor_type, secret_ciphertext, status, confirmed_at) VALUES (%s,%s,%s,'TOTP',%s,'ACTIVE',now())",
                  [uuid4(), rig.world.org_a, rig.world.user_a, b"x"])
    r = await rig.login()
    assert r.mfa_required is True and r.session.mfa_verified_at is None  # session exists but is NOT mfa-verified


async def test_logout_revokes_server_side_and_is_audited(rig: Rig) -> None:
    r = await rig.login()
    current = (await rig.sessions.authenticate(r.session.token)).session
    assert current is not None
    await rig.auth.logout(current, request_id="req-abcdef12")
    assert (await rig.sessions.authenticate(r.session.token)).failure is AuthFailure.REVOKED
    assert len(rig.audit("AUTH_LOGOUT")) == 1


async def test_password_change_requires_current_password_revokes_other_sessions_keeps_current(rig: Rig) -> None:
    other = (await rig.login()).session
    mine = (await rig.login()).session
    current = (await rig.sessions.authenticate(mine.token)).session
    assert current is not None
    new_pw = "another long passphrase 2026"
    with pytest.raises(ProblemError) as e:
        await rig.auth.change_password(current, current_password=WRONG_CURRENT, new_password=new_pw, client_ip=IP, request_id="req-abcdef12")
    assert e.value.code is ErrorCode.VALIDATION_ERROR and e.value.status == 422 and e.value.errors == [{"field": "currentPassword", "reason": "invalid_current_password"}]
    await rig.auth.change_password(current, current_password=PASSWORD, new_password=new_pw, client_ip=IP, request_id="req-abcdef12")
    assert (await rig.sessions.authenticate(other.token)).failure is AuthFailure.REVOKED  # AUTH-008
    assert (await rig.sessions.authenticate(mine.token)).session is not None
    with pytest.raises(ProblemError):
        await rig.login()  # old password no longer works
    assert (await rig.login(password=new_pw)).session.token
    assert [r[1] for r in rig.audit("AUTH_PASSWORD_CHANGED")] == ["DENIED", "SUCCEEDED"]
    assert new_pw not in repr(rig.audit()) and PASSWORD not in repr(rig.audit())


async def test_password_change_enforces_policy_and_keeps_old_password_on_rejection(rig: Rig) -> None:
    current = (await rig.sessions.authenticate((await rig.login()).session.token)).session
    assert current is not None
    with pytest.raises(ProblemError) as e:
        await rig.auth.change_password(current, current_password=PASSWORD, new_password="short", client_ip=IP, request_id="req-abcdef12")
    assert e.value.code is ErrorCode.VALIDATION_ERROR and e.value.errors == [{"field": "newPassword", "reason": "too_short"}]
    assert "short" not in str(e.value.detail)
    assert (await rig.login()).session.token  # unchanged


# ---- review fixes (S07) ----
async def test_a_burst_of_parallel_guesses_cannot_slip_through_the_throttle(rig: Rig) -> None:
    results = await asyncio.gather(*(rig.login(password=WRONG) for _ in range(12)), return_exceptions=True)
    codes = [r.code for r in results if isinstance(r, ProblemError)]
    assert codes.count(ErrorCode.AUTHENTICATION_REQUIRED) == 3  # account+ip threshold is 3: exactly three guesses were ever examined
    assert codes.count(ErrorCode.RATE_LIMITED) == 9
    assert len(rig.audit("AUTH_LOGIN_FAILED")) == 3


async def test_valid_logins_never_accumulate_towards_a_block(rig: Rig) -> None:
    for _ in range(10):
        await rig.login()
    assert rig.throttle.retry_after(f"{rig.world.org_a}:a@example.com", IP) is None


async def test_a_failing_audit_write_aborts_the_login_and_leaves_no_session(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_res.modules.audit.writer import SqlAuditWriter

    async def boom(self: Any, record: Any, **kw: Any) -> None:
        raise RuntimeError("audit down")

    monkeypatch.setattr(SqlAuditWriter, "write", boom)
    with pytest.raises(RuntimeError):
        await rig.login()
    with rig.world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM iam.sessions").fetchone()[0] == 0
