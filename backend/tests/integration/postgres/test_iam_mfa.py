# ruff: noqa: E501, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S07 slice 4: TOTP MFA + recovery codes (AUTH-006): encrypted seed, replay rejection, one-time recovery codes, throttling, fixation, reset."""
import asyncio
import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pyotp
import pytest

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.auth import AuthService
from ai_res.modules.iam.mfa import MfaService
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy
from ai_res.modules.iam.secretbox import SecretBox
from ai_res.modules.iam.sessions import AuthenticatedSession, AuthFailure, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy
from ai_res.platform.problems import ErrorCode, ProblemError

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 11, 11, 12, 0, 5, tzinfo=UTC)
PASSWORD = "correct horse battery staple 42"
IP = "203.0.113.9"


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


class Rig:
    def __init__(self, world: Any, clock: Clock) -> None:
        self.world, self.clock = world, clock
        factory = create_session_factory(world.engine())
        hasher = PasswordHasherService(time_cost=1, memory_kib=8, parallelism=1)
        self.sessions = SessionService(factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12), touch_interval=timedelta(minutes=1), clock=clock)
        self.throttle = LoginThrottle(ThrottlePolicy(account_ip_threshold=3, ip_threshold=50, account_threshold=50, global_threshold=500, base_delay=timedelta(seconds=2),
                                                     max_delay=timedelta(seconds=60), window=timedelta(minutes=15)), clock)
        self.auth = AuthService(factory, self.sessions, hasher, PasswordPolicy(denylist=frozenset()), self.throttle, clock=clock)
        self.mfa = MfaService(factory, self.sessions, SecretBox("k1", {"k1": bytes(range(32))}), self.throttle, issuer="AI RES", window=1, clock=clock)
        with world.pg.connect() as c:
            c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)",
                      [uuid4(), world.org_a, world.user_a, hasher.hash(PASSWORD)])

    async def login(self) -> AuthenticatedSession:
        r = await self.auth.login(organization_id=self.world.org_a, email="a@example.com", password=PASSWORD, client_ip=IP, request_id="req-abcdef12")
        out = (await self.sessions.authenticate(r.session.token)).session
        assert out is not None
        self.token = r.session.token
        return out

    def totp(self, secret: str, offset: int = 0) -> str:
        return pyotp.TOTP(secret).at(int(self.clock.now.timestamp()) + offset * 30)

    async def enrolled(self) -> tuple[str, list[str], AuthenticatedSession]:
        """Enrols MFA and returns (secret, recovery codes, a fresh login session that still has to present the second factor)."""
        s = await self.login()
        e = await self.mfa.begin_enrollment(s, request_id="req-abcdef12")
        done = await self.mfa.confirm_enrollment(s, self.totp(e.secret), client_ip=IP, request_id="req-abcdef12")
        self.clock.advance(seconds=31)  # the enrolment code's step must not be reusable for the next verification
        return e.secret, done.recovery_codes, await self.login()

    def audit_actions(self) -> list[str]:
        with self.world.pg.connect() as c:
            return [r[0] for r in c.execute("SELECT action FROM audit.audit_events ORDER BY occurred_at, id").fetchall()]


@pytest.fixture
def rig(iam_world: Any) -> Rig:
    return Rig(iam_world, Clock())


async def test_enrolment_stores_only_encrypted_seed_and_hashed_codes_and_elevates_the_session(rig: Rig) -> None:
    s = await rig.login()
    e = await rig.mfa.begin_enrollment(s, request_id="req-abcdef12")
    assert e.otpauth_uri.startswith("otpauth://totp/") and e.secret in e.otpauth_uri and "AI%20RES" in e.otpauth_uri
    done = await rig.mfa.confirm_enrollment(s, rig.totp(e.secret), client_ip=IP, request_id="req-abcdef12")
    assert len(done.recovery_codes) == 10 and done.session.mfa_verified_at == rig.clock.now
    assert (await rig.sessions.authenticate(rig.token)).failure is AuthFailure.REVOKED  # privilege elevation rotated the id
    with rig.world.pg.connect() as c:
        dump = repr(c.execute("SELECT to_jsonb(f)::text FROM iam.mfa_factors f").fetchall()) + repr(c.execute("SELECT to_jsonb(r)::text FROM iam.mfa_recovery_codes r").fetchall())
        assert c.execute("SELECT status FROM iam.mfa_factors").fetchone()[0] == "ACTIVE"
    assert e.secret not in dump and all(code not in dump for code in done.recovery_codes)
    assert e.secret not in repr(rig.audit_actions()) and "AUTH_MFA_ENROLLED" in rig.audit_actions()


async def test_wrong_code_does_not_confirm_enrolment(rig: Rig) -> None:
    s = await rig.login()
    e = await rig.mfa.begin_enrollment(s, request_id="req-abcdef12")
    with pytest.raises(ProblemError) as err:
        await rig.mfa.confirm_enrollment(s, "000000" if rig.totp(e.secret) != "000000" else "111111", client_ip=IP, request_id="req-abcdef12")
    assert err.value.code is ErrorCode.AUTHENTICATION_REQUIRED
    with rig.world.pg.connect() as c:
        assert c.execute("SELECT status FROM iam.mfa_factors").fetchone()[0] == "PENDING"


async def test_restarting_enrolment_replaces_the_pending_factor_but_active_factor_blocks_it(rig: Rig) -> None:
    s = await rig.login()
    first = await rig.mfa.begin_enrollment(s, request_id="req-abcdef12")
    second = await rig.mfa.begin_enrollment(s, request_id="req-abcdef12")
    assert first.secret != second.secret
    with rig.world.pg.connect() as c:
        assert sorted(r[0] for r in c.execute("SELECT status FROM iam.mfa_factors").fetchall()) == ["PENDING", "REVOKED"]
    await rig.mfa.confirm_enrollment(s, rig.totp(second.secret), client_ip=IP, request_id="req-abcdef12")
    rig.clock.advance(seconds=31)
    with pytest.raises(ProblemError) as err:
        await rig.mfa.begin_enrollment(await rig.login(), request_id="req-abcdef12")
    assert err.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED  # changing a factor is the privileged reset procedure, not a re-enrol


async def test_second_factor_after_login_elevates_to_a_new_session_and_kills_the_old_token(rig: Rig) -> None:
    secret, _, s = await rig.enrolled()
    assert s.mfa_verified_at is None
    old = rig.token
    elevated = await rig.mfa.verify(s, rig.totp(secret), client_ip=IP, request_id="req-abcdef12")
    assert elevated.mfa_verified_at == rig.clock.now and elevated.token != old
    assert (await rig.sessions.authenticate(old)).failure is AuthFailure.REVOKED  # fixation
    assert (await rig.sessions.authenticate(elevated.token)).session is not None


async def test_totp_code_cannot_be_replayed_even_in_parallel(rig: Rig) -> None:
    secret, _, _ = await rig.enrolled()
    code = rig.totp(secret)
    a, b = await rig.login(), await rig.login()
    results = await asyncio.gather(rig.mfa.verify(a, code, client_ip=IP, request_id="req-abcdef12"), rig.mfa.verify(b, code, client_ip="198.51.100.7", request_id="req-abcdef12"),
                                   return_exceptions=True)
    assert sum(isinstance(r, ProblemError) for r in results) == 1 and sum(not isinstance(r, BaseException) for r in results) == 1


async def test_sequential_replay_is_rejected_but_the_next_step_works(rig: Rig) -> None:
    secret, _, s = await rig.enrolled()
    code = rig.totp(secret)
    await rig.mfa.verify(s, code, client_ip=IP, request_id="req-abcdef12")
    with pytest.raises(ProblemError):
        await rig.mfa.verify(await rig.login(), code, client_ip=IP, request_id="req-abcdef12")
    rig.clock.advance(seconds=31)
    assert (await rig.mfa.verify(await rig.login(), rig.totp(secret), client_ip=IP, request_id="req-abcdef12")).mfa_verified_at is not None


async def test_clock_drift_inside_the_window_is_tolerated_and_outside_it_is_not(rig: Rig) -> None:
    secret, _, s = await rig.enrolled()
    assert (await rig.mfa.verify(s, rig.totp(secret, offset=1), client_ip=IP, request_id="req-abcdef12")).mfa_verified_at is not None
    rig.clock.advance(seconds=95)
    with pytest.raises(ProblemError):
        await rig.mfa.verify(await rig.login(), pyotp.TOTP(secret).at(int(rig.clock.now.timestamp()) - 300), client_ip=IP, request_id="req-abcdef12")


async def test_recovery_code_works_once_in_any_format_and_then_never_again(rig: Rig) -> None:
    _, codes, s = await rig.enrolled()
    sloppy = codes[0].lower().replace("-", " ")
    assert (await rig.mfa.verify(s, sloppy, client_ip=IP, request_id="req-abcdef12")).mfa_verified_at is not None
    with pytest.raises(ProblemError):
        await rig.mfa.verify(await rig.login(), codes[0], client_ip=IP, request_id="req-abcdef12")
    assert (await rig.mfa.verify(await rig.login(), codes[1], client_ip=IP, request_id="req-abcdef12")).mfa_verified_at is not None
    assert "AUTH_MFA_RECOVERY_USED" in rig.audit_actions()


async def test_parallel_use_of_one_recovery_code_succeeds_once(rig: Rig) -> None:
    _, codes, _ = await rig.enrolled()
    a, b = await rig.login(), await rig.login()
    results = await asyncio.gather(rig.mfa.verify(a, codes[2], client_ip=IP, request_id="req-abcdef12"), rig.mfa.verify(b, codes[2], client_ip=IP, request_id="req-abcdef12"),
                                   return_exceptions=True)
    assert sum(not isinstance(r, BaseException) for r in results) == 1


async def test_guessing_codes_is_throttled_before_any_check(rig: Rig) -> None:
    secret, _, s = await rig.enrolled()
    for _ in range(3):
        with pytest.raises(ProblemError):
            await rig.mfa.verify(s, "000000" if rig.totp(secret) != "000000" else "111111", client_ip=IP, request_id="req-abcdef12")
    with pytest.raises(ProblemError) as err:
        await rig.mfa.verify(s, rig.totp(secret), client_ip=IP, request_id="req-abcdef12")  # even the right code waits
    assert err.value.code is ErrorCode.RATE_LIMITED and err.value.status == 429


async def test_verifying_without_an_active_factor_is_refused(rig: Rig) -> None:
    with pytest.raises(ProblemError) as err:
        await rig.mfa.verify(await rig.login(), "123456", client_ip=IP, request_id="req-abcdef12")
    assert err.value.code is ErrorCode.AUTHENTICATION_REQUIRED


async def test_regenerating_recovery_codes_requires_an_mfa_verified_session_and_burns_the_old_ones(rig: Rig) -> None:
    secret, old_codes, s = await rig.enrolled()
    with pytest.raises(ProblemError) as err:
        await rig.mfa.regenerate_recovery_codes(s, request_id="req-abcdef12")  # session has not presented the second factor
    assert err.value.code is ErrorCode.ACCESS_DENIED
    elevated = await rig.mfa.verify(s, rig.totp(secret), client_ip=IP, request_id="req-abcdef12")
    current = (await rig.sessions.authenticate(elevated.token)).session
    assert current is not None
    new_codes = await rig.mfa.regenerate_recovery_codes(current, request_id="req-abcdef12")
    assert len(new_codes) == 10 and not set(new_codes) & set(old_codes)
    with pytest.raises(ProblemError):
        await rig.mfa.verify(await rig.login(), old_codes[3], client_ip=IP, request_id="req-abcdef12")
    assert (await rig.mfa.verify(await rig.login(), new_codes[0], client_ip=IP, request_id="req-abcdef12")).mfa_verified_at is not None


def make_owner(rig: Rig) -> Any:
    from uuid import uuid4
    uid = uuid4()
    with rig.world.pg.connect() as c:
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'boss@example.com','boss@example.com','u')", [uid, rig.world.org_a])
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,'ORGANIZATION_OWNER')", [uuid4(), rig.world.org_a, uid])
    return uid


async def test_privileged_reset_revokes_factors_codes_and_every_session_and_is_audited(rig: Rig) -> None:
    secret, codes, s = await rig.enrolled()
    other = rig.token
    await rig.mfa.reset(rig.world.org_a, rig.world.user_a, actor_id=make_owner(rig), request_id="req-abcdef12")
    assert (await rig.sessions.authenticate(other)).failure is AuthFailure.REVOKED
    with rig.world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM iam.mfa_factors WHERE status <> 'REVOKED'").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM iam.mfa_recovery_codes WHERE used_at IS NULL").fetchone()[0] == 0
    r = await rig.auth.login(organization_id=rig.world.org_a, email="a@example.com", password=PASSWORD, client_ip=IP, request_id="req-abcdef12")
    assert r.mfa_required is False  # back to un-enrolled; enrolment can start again
    assert "AUTH_MFA_RESET" in rig.audit_actions()


async def test_the_database_refuses_to_move_the_replay_step_backwards(rig: Rig) -> None:
    await rig.enrolled()
    with rig.world.pg.connect() as c:
        step = c.execute("SELECT last_used_step FROM iam.mfa_factors").fetchone()[0]
        assert step is not None
        with pytest.raises(Exception, match="can only increase"):
            c.execute("UPDATE iam.mfa_factors SET last_used_step = %s, row_version = row_version + 1", [step - 1])


async def test_a_factor_row_copied_to_another_user_does_not_decrypt(rig: Rig) -> None:
    secret, _, _ = await rig.enrolled()
    with rig.world.pg.connect() as c:
        blob = bytes(c.execute("SELECT secret_ciphertext FROM iam.mfa_factors").fetchone()[0])
    with pytest.raises(Exception):  # noqa: B017 - SecretBoxError
        SecretBox("k1", {"k1": bytes(range(32))}).open(blob, b"mfa-totp:%s:%s:%s" % (str(rig.world.org_b).encode(), str(rig.world.user_b).encode(), b"x"))
    assert base64.b32decode(secret) not in blob


# ---- review fixes (S07) ----
async def test_resetting_an_unknown_user_is_refused_and_not_audited_as_a_success(rig: Rig) -> None:
    from uuid import uuid4
    with pytest.raises(ProblemError) as err:
        await rig.mfa.reset(rig.world.org_a, uuid4(), actor_id=make_owner(rig), request_id="req-abcdef12")
    assert err.value.code is ErrorCode.RESOURCE_NOT_FOUND
    assert "AUTH_MFA_RESET" not in rig.audit_actions()


async def test_secrets_never_appear_in_the_repr_of_issued_values(rig: Rig) -> None:
    s = await rig.login()
    e = await rig.mfa.begin_enrollment(s, request_id="req-abcdef12")
    done = await rig.mfa.confirm_enrollment(s, rig.totp(e.secret), client_ip=IP, request_id="req-abcdef12")
    text = repr(e) + repr(done) + repr(done.session)
    assert e.secret not in text and done.recovery_codes[0] not in text and done.session.token not in text and done.session.csrf_token not in text


async def test_an_owner_cannot_reset_their_own_second_factor_through_the_privileged_path(rig: Rig) -> None:
    owner = make_owner(rig)
    with pytest.raises(ProblemError) as err:
        await rig.mfa.reset(rig.world.org_a, owner, actor_id=owner, request_id="req-abcdef12")
    assert err.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    assert "AUTH_MFA_RESET" not in rig.audit_actions()


async def test_an_unreadable_seed_is_refused_like_a_wrong_code_but_the_operator_is_told(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    secret, _, s = await rig.enrolled()
    with rig.world.pg.connect() as c:
        c.execute("UPDATE iam.mfa_factors SET secret_ciphertext = decode(repeat('ab', 40), 'hex'), row_version = row_version + 1 WHERE status = 'ACTIVE'")
    with caplog.at_level("ERROR"), pytest.raises(ProblemError) as err:
        await rig.mfa.verify(s, rig.totp(secret), client_ip=IP, request_id="req-abcdef12")
    assert err.value.status == 401  # the client learns nothing new
    assert any("cannot be decrypted" in r.getMessage() for r in caplog.records) and secret not in caplog.text
