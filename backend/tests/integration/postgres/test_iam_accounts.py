# ruff: noqa: E501, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S07 slice 6: AUTH-008 — disabling a user or revoking a role ends sessions immediately; lock-out guards; enforcement end to end with the Policy Engine."""
import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.iam.accounts import AccountService
from ai_res.modules.iam.auth import AuthService
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy
from ai_res.modules.iam.sessions import AuthFailure, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.config import load_packaged_policy
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple 42"


class Rig:
    def __init__(self, world: Any) -> None:
        self.w = world
        self.factory = create_session_factory(world.engine())
        h = PasswordHasherService(time_cost=1, memory_kib=8, parallelism=1)
        self.sessions = SessionService(self.factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12), touch_interval=timedelta(minutes=1))
        self.auth = AuthService(self.factory, self.sessions, h, PasswordPolicy(denylist=frozenset()), LoginThrottle(ThrottlePolicy(
            account_ip_threshold=50, ip_threshold=50, account_threshold=50, global_threshold=500, base_delay=timedelta(seconds=2), max_delay=timedelta(seconds=60), window=timedelta(minutes=15))))
        self.accounts = AccountService(self.sessions, self.factory)
        self.engine = PolicyEngine(load_packaged_policy(), self.factory)
        self.enforcer = PolicyEnforcer(self.engine, self.factory, load_packaged_policy(), timeout_seconds=2.0)
        self.admin, self.owner, self.target = uuid4(), uuid4(), world.user_a
        with world.pg.connect() as c:
            for uid, mail, role in ((self.admin, "admin@example.com", "ORGANIZATION_ADMIN"), (self.owner, "owner@example.com", "ORGANIZATION_OWNER")):
                c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,'u')", [uid, world.org_a, mail, mail])
                c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,%s)", [uuid4(), world.org_a, uid, role])
            c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)", [uuid4(), world.org_a, world.user_a, h.hash(PASSWORD)])

    async def act(self, action: str, actor: Any, target: Any, mfa: bool = True) -> int:
        """What an API handler does: authorize, then change + revoke + audit in ONE transaction."""
        async with UnitOfWork(self.factory) as uow:
            await uow.with_tenant(self.w.org_a)
            d = await self.enforcer.authorize(PolicyRequest(actor_id=str(actor), action=action, resource_type="USER", resource_id=str(target), organization_id=str(self.w.org_a),
                                                            attributes={"mfa_verified": mfa}), session=uow.session, conceal=True)
            fn = self.accounts.disable_user_in if action == "iam.user.disable" else self.accounts.revoke_membership_in
            return await fn(uow.session, self.w.org_a, actor, target, policy_version=d.policy_version, request_id="req-abcdef12")


@pytest.fixture
def rig(iam_world: Any) -> Rig:
    return Rig(iam_world)


async def test_disabling_a_user_ends_all_their_sessions_blocks_login_and_is_audited(rig: Rig) -> None:
    a, b = await rig.sessions.create(rig.w.org_a, rig.target), await rig.sessions.create(rig.w.org_a, rig.target)
    assert await rig.act("iam.user.disable", rig.admin, rig.target) == 2
    assert (await rig.sessions.authenticate(a.token)).failure is AuthFailure.REVOKED and (await rig.sessions.authenticate(b.token)).failure is AuthFailure.REVOKED
    with pytest.raises(ProblemError) as e:
        await rig.auth.login(organization_id=rig.w.org_a, email="a@example.com", password=PASSWORD, client_ip="203.0.113.9", request_id=None)
    assert e.value.code is ErrorCode.AUTHENTICATION_REQUIRED
    with rig.w.pg.connect() as c:
        rows = c.execute("SELECT action, details->>'policyVersion', details->>'devicesSignedOut' FROM audit.audit_events WHERE action = 'AUTH_ACCOUNT_DISABLED'").fetchall()
    assert rows == [("AUTH_ACCOUNT_DISABLED", load_packaged_policy().version, "2")]


async def test_revoking_a_membership_ends_sessions_and_the_policy_stops_granting(rig: Rig) -> None:
    s = await rig.sessions.create(rig.w.org_a, rig.admin)
    assert (await rig.engine.decide(PolicyRequest(actor_id=str(rig.admin), action="iam.user.disable", resource_type="USER", organization_id=str(rig.w.org_a),
                                                  attributes={"mfa_verified": True}))).effect.value == "ALLOW"
    assert await rig.act("iam.membership.revoke", rig.owner, rig.admin) == 1
    assert (await rig.sessions.authenticate(s.token)).failure is AuthFailure.REVOKED
    d = await rig.engine.decide(PolicyRequest(actor_id=str(rig.admin), action="iam.user.disable", resource_type="USER", organization_id=str(rig.w.org_a), attributes={"mfa_verified": True}))
    assert d.effect.value == "DENY" and d.reason_code == "membership_inactive"


async def test_a_user_without_the_right_role_or_mfa_changes_nothing(rig: Rig) -> None:
    s = await rig.sessions.create(rig.w.org_a, rig.target)
    for actor, mfa in ((rig.w.user_a, True), (rig.admin, False)):  # an auditor, and an admin without a verified second factor
        with pytest.raises(ProblemError) as e:
            await rig.act("iam.user.disable", actor, rig.target, mfa=mfa)
        assert e.value.code is ErrorCode.RESOURCE_NOT_FOUND  # concealed
    assert (await rig.sessions.authenticate(s.token)).session is not None


async def test_lockout_guards_self_and_last_owner(rig: Rig) -> None:
    with pytest.raises(ProblemError) as e:
        await rig.act("iam.user.disable", rig.admin, rig.admin)
    assert e.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    with pytest.raises(ProblemError) as e2:
        await rig.act("iam.membership.revoke", rig.admin, rig.owner)  # the only active owner: the hierarchy stops an admin first (ADR-073) ...
    assert e2.value.code is ErrorCode.ACCESS_DENIED  # ... and the last-owner guard stays as defence in depth (see the concurrent two-owner test)
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT status FROM organization.memberships WHERE user_id = %s", [rig.owner]).fetchone()[0] == "ACTIVE"


async def test_unknown_user_and_other_organizations_user_look_the_same(rig: Rig) -> None:
    for target in (uuid4(), rig.w.user_b):
        with pytest.raises(ProblemError) as e:
            await rig.act("iam.user.disable", rig.admin, target)
        assert e.value.code is ErrorCode.RESOURCE_NOT_FOUND and e.value.status == 404
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT status FROM iam.users WHERE id = %s", [rig.w.user_b]).fetchone()[0] == "ACTIVE"


# ---- review fixes (S07) ----
async def test_two_owners_cannot_remove_each_other_concurrently(rig: Rig) -> None:
    second = uuid4()
    with rig.w.pg.connect() as c:
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'o2@example.com','o2@example.com','u')", [second, rig.w.org_a])
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,'ORGANIZATION_OWNER')", [uuid4(), rig.w.org_a, second])
    results = await asyncio.gather(rig.act("iam.user.disable", rig.owner, second), rig.act("iam.user.disable", second, rig.owner), return_exceptions=True)
    assert sum(not isinstance(r, BaseException) for r in results) == 1  # one wins, the other is refused as "last owner"
    with rig.w.pg.connect() as c:
        active = c.execute("SELECT count(*) FROM organization.memberships m JOIN iam.users u ON u.id = m.user_id "
                           "WHERE m.organization_id = %s AND m.role_code = 'ORGANIZATION_OWNER' AND m.status = 'ACTIVE' AND u.status = 'ACTIVE'", [rig.w.org_a]).fetchone()[0]
    assert active == 1


async def test_disabling_an_already_disabled_user_is_refused_and_not_audited_as_a_success(rig: Rig) -> None:
    await rig.act("iam.user.disable", rig.admin, rig.target)
    with pytest.raises(ProblemError) as e:
        await rig.act("iam.user.disable", rig.admin, rig.target)
    assert e.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM audit.audit_events WHERE action = 'AUTH_ACCOUNT_DISABLED'").fetchone()[0] == 1


async def test_a_revoked_member_cannot_log_in_again_and_a_surviving_session_is_refused(rig: Rig) -> None:
    survivor = await rig.sessions.create(rig.w.org_a, rig.target)
    with rig.w.pg.connect() as c:  # revoke the membership behind the service's back: the session row itself stays valid
        c.execute("UPDATE organization.memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = %s", [rig.target])
    assert (await rig.sessions.authenticate(survivor.token)).failure is AuthFailure.MEMBERSHIP_REVOKED
    with pytest.raises(ProblemError) as e:
        await rig.auth.login(organization_id=rig.w.org_a, email="a@example.com", password=PASSWORD, client_ip="203.0.113.9", request_id=None)
    assert e.value.code is ErrorCode.AUTHENTICATION_REQUIRED


async def test_a_refused_actor_changes_nothing_at_all(rig: Rig) -> None:
    with pytest.raises(ProblemError):
        await rig.act("iam.user.disable", rig.admin, rig.target, mfa=False)
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT status FROM iam.users WHERE id = %s", [rig.target]).fetchone()[0] == "ACTIVE"
        assert c.execute("SELECT count(*) FROM audit.audit_events WHERE action = 'AUTH_ACCOUNT_DISABLED'").fetchone()[0] == 0


async def test_role_hierarchy_an_admin_cannot_act_on_an_owner_or_a_peer(rig: Rig) -> None:
    """ADR-073: the actor's organization role must rank strictly above the subject's (an OWNER may also act on another OWNER)."""
    peer = uuid4()
    with rig.w.pg.connect() as c:
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'peer@example.com','peer@example.com','u')", [peer, rig.w.org_a])
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,'ORGANIZATION_ADMIN')", [uuid4(), rig.w.org_a, peer])
    for subject in (rig.owner, peer):  # an admin against an owner, and against another admin
        with pytest.raises(ProblemError) as e:
            await rig.act("iam.user.disable", rig.admin, subject)
        assert e.value.code is ErrorCode.ACCESS_DENIED and e.value.errors == [{"field": "policy", "reason": "role_hierarchy"}]
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM iam.users WHERE status = 'DISABLED'").fetchone()[0] == 0
    await rig.act("iam.user.disable", rig.admin, rig.target)  # below an admin: allowed
    await rig.act("iam.user.disable", rig.owner, peer)  # an owner may act on an admin


def hierarchy_denials(rig: Rig) -> list[tuple[Any, ...]]:
    with rig.w.pg.connect() as c:
        return c.execute("SELECT actor_id, object_id, result, reason_code, details->>'policyAction' FROM audit.audit_events "
                         "WHERE action = 'POLICY_DECISION' AND reason_code = 'role_hierarchy'").fetchall()


async def test_a_hierarchy_denial_leaves_an_audit_trace_even_though_the_action_rolls_back(rig: Rig) -> None:
    with pytest.raises(ProblemError):
        await rig.act("iam.user.disable", rig.admin, rig.owner)
    assert hierarchy_denials(rig) == [(rig.admin, rig.owner, "DENIED", "role_hierarchy", "iam.user.disable")]
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT status FROM iam.users WHERE id = %s", [rig.owner]).fetchone()[0] == "ACTIVE"
    with pytest.raises(ProblemError):
        await rig.act("iam.membership.revoke", rig.admin, rig.owner)
    assert len(hierarchy_denials(rig)) == 2


async def test_when_the_denial_cannot_be_recorded_the_action_is_still_refused_with_503(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_res.modules.audit.writer import SqlAuditWriter

    real = SqlAuditWriter.write

    async def write(self: Any, record: Any, **kw: Any) -> None:
        if record.reason_code == "role_hierarchy":
            raise RuntimeError("audit down")
        await real(self, record, **kw)

    monkeypatch.setattr(SqlAuditWriter, "write", write)
    with pytest.raises(ProblemError) as e:
        await rig.act("iam.user.disable", rig.admin, rig.owner)
    assert e.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE and e.value.status == 503
    with rig.w.pg.connect() as c:
        assert c.execute("SELECT status FROM iam.users WHERE id = %s", [rig.owner]).fetchone()[0] == "ACTIVE"
