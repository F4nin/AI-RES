"""S07 slice 2: opaque server-side sessions under the real API role + FORCE RLS (AUTH-007, AUTH-008, fixation, cross-org)."""
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.sessions import AuthFailure, RevokeReason, SessionService
from ai_res.modules.iam.tokens import csrf_digest, csrf_token_for, new_session_token
from ai_res.platform.problems import ProblemError

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def svc(iam_world: Any, clock: Clock) -> SessionService:
    return SessionService(create_session_factory(iam_world.engine()), idle=timedelta(minutes=30), absolute=timedelta(hours=12),
                          touch_interval=timedelta(minutes=1), clock=clock)


async def test_create_then_authenticate_returns_principal_and_csrf(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    r = await svc.authenticate(issued.token)
    assert r.failure is None and r.session is not None
    assert (r.session.user_id, r.session.organization_id) == (iam_world.user_a, iam_world.org_a)
    assert r.session.csrf_token == issued.csrf_token == csrf_token_for(issued.token)
    assert r.session.mfa_verified_at is None


async def test_database_never_stores_the_raw_token_or_csrf_token(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    with iam_world.pg.connect() as c:
        dump = repr(c.execute("SELECT to_jsonb(s)::text FROM iam.sessions s").fetchall())
    secret_part = issued.token.split(".")[1]
    assert secret_part not in dump and issued.csrf_token not in dump
    with iam_world.pg.connect() as c:
        digests = c.execute("SELECT csrf_digest FROM iam.sessions").fetchone()
    assert bytes(digests[0]) == csrf_digest(issued.csrf_token)


async def test_malformed_and_unknown_tokens_are_refused(svc: SessionService, iam_world: Any) -> None:
    assert (await svc.authenticate("garbage")).failure is AuthFailure.MALFORMED
    assert (await svc.authenticate(new_session_token(iam_world.org_a))).failure is AuthFailure.UNKNOWN


async def test_token_of_org_a_with_org_b_hint_is_not_accepted(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    forged = new_session_token(iam_world.org_b).split(".")[0] + "." + issued.token.split(".")[1]  # B's hint + A's secret
    assert (await svc.authenticate(forged)).failure is AuthFailure.UNKNOWN


async def test_idle_timeout_expires_session_and_activity_extends_it(svc: SessionService, iam_world: Any, clock: Clock) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    clock.advance(minutes=29)
    assert (await svc.authenticate(issued.token)).session is not None  # slides idle window forward
    clock.advance(minutes=29)
    assert (await svc.authenticate(issued.token)).session is not None  # alive thanks to the previous touch
    clock.advance(minutes=31)
    assert (await svc.authenticate(issued.token)).failure is AuthFailure.IDLE_EXPIRED


async def test_absolute_lifetime_is_never_extended_by_activity(svc: SessionService, iam_world: Any, clock: Clock) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    for _ in range(24):  # one request every 29 minutes keeps the idle window open for 11 h 36 m
        clock.advance(minutes=29)
        assert (await svc.authenticate(issued.token)).session is not None
    clock.advance(minutes=29)  # 12 h 5 m since login
    assert (await svc.authenticate(issued.token)).failure is AuthFailure.ABSOLUTE_EXPIRED


async def test_idle_expiry_is_capped_by_absolute_expiry(svc: SessionService, iam_world: Any, clock: Clock) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    for _ in range(24):  # regular activity keeps the idle window open up to 11 h 36 m
        clock.advance(minutes=29)
        assert (await svc.authenticate(issued.token)).session is not None
    clock.advance(minutes=20)  # 11 h 56 m: now + 30 min would pass the 12 h cap
    r = await svc.authenticate(issued.token)
    assert r.session is not None and r.session.idle_expires_at == r.session.absolute_expires_at


async def test_revoked_session_is_refused_and_revocation_is_write_once(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    assert await svc.revoke(iam_world.org_a, issued.session_id, RevokeReason.LOGOUT) is True
    assert (await svc.authenticate(issued.token)).failure is AuthFailure.REVOKED
    assert await svc.revoke(iam_world.org_a, issued.session_id, RevokeReason.ADMIN_REVOKED) is False  # already revoked: reason is not rewritten
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT revoked_reason FROM iam.sessions").fetchone()[0] == "LOGOUT"


async def test_revoking_another_organizations_session_changes_nothing(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    assert await svc.revoke(iam_world.org_b, issued.session_id, RevokeReason.ADMIN_REVOKED) is False
    assert (await svc.authenticate(issued.token)).session is not None


async def test_rotation_changes_token_keeps_absolute_lifetime_and_kills_old_token(svc: SessionService, iam_world: Any, clock: Clock) -> None:
    first = await svc.create(iam_world.org_a, iam_world.user_a)
    current = (await svc.authenticate(first.token)).session
    assert current is not None
    clock.advance(hours=1)
    second = await svc.rotate(current, mfa_verified=True)
    assert second.token != first.token and second.session_id != first.session_id
    assert second.absolute_expires_at == first.absolute_expires_at  # rotation does not extend the 12 h cap
    assert (await svc.authenticate(first.token)).failure is AuthFailure.REVOKED  # fixation: the pre-login token is dead
    r = await svc.authenticate(second.token)
    assert r.session is not None and r.session.mfa_verified_at == clock.now


async def test_rotation_of_a_session_revoked_meanwhile_does_not_mint_a_new_one(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    current = (await svc.authenticate(issued.token)).session
    assert current is not None
    await svc.revoke(iam_world.org_a, issued.session_id, RevokeReason.LOGOUT)
    with pytest.raises(ProblemError):
        await svc.rotate(current)
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM iam.sessions").fetchone()[0] == 1


async def test_revoke_all_for_user_spares_the_excepted_session_and_other_users(svc: SessionService, iam_world: Any) -> None:
    keep = await svc.create(iam_world.org_a, iam_world.user_a)
    other = await svc.create(iam_world.org_a, iam_world.user_a)
    foreign = await svc.create(iam_world.org_b, iam_world.user_b)
    assert await svc.revoke_all_for_user(iam_world.org_a, iam_world.user_a, RevokeReason.PASSWORD_CHANGED, except_session_id=keep.session_id) == 1
    assert (await svc.authenticate(keep.token)).session is not None
    assert (await svc.authenticate(other.token)).failure is AuthFailure.REVOKED
    assert (await svc.authenticate(foreign.token)).session is not None


async def test_disabled_user_session_stops_working_immediately(svc: SessionService, iam_world: Any) -> None:
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    with iam_world.pg.connect() as c:
        c.execute("UPDATE iam.users SET status = 'DISABLED', row_version = row_version + 1 WHERE id = %s", [iam_world.user_a])
    assert (await svc.authenticate(issued.token)).failure is AuthFailure.USER_DISABLED


async def test_sessions_cannot_be_created_for_a_user_of_another_organization(svc: SessionService, iam_world: Any) -> None:
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await svc.create(iam_world.org_a, iam_world.user_b)  # composite FK (organization_id, user_id)


async def test_concurrent_touches_do_not_error_or_extend_beyond_absolute(svc: SessionService, iam_world: Any, clock: Clock) -> None:
    import asyncio
    issued = await svc.create(iam_world.org_a, iam_world.user_a)
    clock.advance(minutes=5)
    results = await asyncio.gather(*(svc.authenticate(issued.token) for _ in range(6)))
    assert all(r.session is not None for r in results)
