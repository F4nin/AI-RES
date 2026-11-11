# ruff: noqa: E501, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S07 slice 6: Policy & Permission Engine + enforcer (ADR-017, SEC-001/002/019/029, AUTH-006/012): deny-by-default matrix, fail-closed, audited decisions."""
import asyncio
import hashlib
import json
import logging
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.platform.ports import Effect, PolicyDecision, PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.config import PolicyConfig, load_packaged_policy, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

pytestmark = pytest.mark.postgres
ALLOW, DENY = Effect.ALLOW, Effect.DENY


class Cast:
    """Org A with one user per role plus the foreign-organization user from IamWorld."""

    def __init__(self, world: Any) -> None:
        self.w = world
        self.users: dict[str, Any] = {}
        self.project = uuid4()
        self.other_project = uuid4()
        with world.pg.connect() as c:
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [self.project, world.org_a])
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'q','GREENFIELD')", [self.other_project, world.org_b])
            for role, org_level in (("OWNER", "ORGANIZATION_OWNER"), ("ADMIN", "ORGANIZATION_ADMIN"), ("AUDITOR", "AUDITOR")):
                self._user(c, role, org_role=org_level)
            for role, project_role in (("ANALYST", "ANALYST"), ("PADMIN", "PROJECT_ADMIN")):
                self._user(c, role, project_role=project_role)
            self._user(c, "NOBODY")

    def _user(self, c: Any, name: str, org_role: str | None = None, project_role: str | None = None) -> None:
        uid = uuid4()
        self.users[name] = uid
        mail = f"{name.lower()}@example.com"
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,'u')", [uid, self.w.org_a, mail, mail])
        if org_role:
            c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,%s)", [uuid4(), self.w.org_a, uid, org_role])
        if project_role:
            c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (%s,%s,%s,%s,%s)", [uuid4(), self.w.org_a, self.project, uid, project_role])


@pytest.fixture
def cast(iam_world: Any) -> Cast:
    return Cast(iam_world)


@pytest.fixture
def engine(iam_world: Any, cast: Cast) -> PolicyEngine:
    return PolicyEngine(load_packaged_policy(), create_session_factory(iam_world.engine()))


def req(cast: Cast, who: str, action: str, *, target: str | None = None, mfa: bool = False, rtype: str = "USER", **kw: Any) -> PolicyRequest:
    actor = cast.users.get(who, who)
    return PolicyRequest(actor_id=str(actor), action=action, resource_type=rtype, resource_id=str(cast.users[target] if target else actor), organization_id=str(cast.w.org_a),
                         attributes={"mfa_verified": mfa, **kw.pop("attributes", {})}, **kw)


# independent oracle: (actor, action, target, mfa) -> (effect, reason)
SELF = ("iam.self.read", "iam.self.logout", "iam.self.password_change", "iam.self.mfa_manage")
ADMIN_ACTIONS = ("iam.user.disable", "iam.user.mfa_reset", "iam.membership.revoke")
MATRIX: list[tuple[str, str, str | None, bool, Effect, str]] = []
for who in ("OWNER", "ADMIN", "AUDITOR", "ANALYST", "PADMIN", "NOBODY"):
    for a in SELF:
        MATRIX.append((who, a, None, False, ALLOW, "allowed_self"))  # self-service needs no MFA, so a privileged user can ENROL MFA
        MATRIX.append((who, a, "OWNER" if who != "OWNER" else "ADMIN", False, DENY, "no_matching_grant"))  # never someone else's account
for a in ADMIN_ACTIONS:
    for who, mfa, effect, reason in (("OWNER", True, ALLOW, "allowed_role:ORGANIZATION_OWNER"), ("ADMIN", True, ALLOW, "allowed_role:ORGANIZATION_ADMIN"),
                                     ("OWNER", False, DENY, "mfa_required"), ("ADMIN", False, DENY, "mfa_required"),
                                     ("AUDITOR", True, DENY, "no_matching_grant"), ("ANALYST", True, DENY, "no_matching_grant"), ("PADMIN", True, DENY, "no_matching_grant"),
                                     ("NOBODY", True, DENY, "no_matching_grant")):
        MATRIX.append((who, a, "NOBODY", mfa, effect, reason))


def test_matrix_covers_every_action_of_the_packaged_policy() -> None:
    assert {m[1] for m in MATRIX} == set(load_packaged_policy().actions)  # a new action without a matrix row fails here


@pytest.mark.parametrize(("who", "action", "target", "mfa", "effect", "reason"), MATRIX)
async def test_policy_matrix(engine: PolicyEngine, cast: Cast, who: str, action: str, target: str | None, mfa: bool, effect: Effect, reason: str) -> None:
    d = await engine.decide(req(cast, who, action, target=target, mfa=mfa))
    assert (d.effect, d.reason_code) == (effect, reason) and d.policy_version == load_packaged_policy().version


@pytest.mark.parametrize("truthy", ["true", 1, "yes", None])
async def test_only_a_real_boolean_true_counts_as_mfa(engine: PolicyEngine, cast: Cast, truthy: Any) -> None:
    d = await engine.decide(req(cast, "ADMIN", "iam.user.disable", target="NOBODY", attributes={"mfa_verified": truthy}))
    assert (d.effect, d.reason_code) == (DENY, "mfa_required")


async def test_unknown_action_resource_mismatch_and_missing_scope_are_denied(engine: PolicyEngine, cast: Cast) -> None:
    assert (await engine.decide(req(cast, "OWNER", "iam.user.delete", mfa=True))).reason_code == "unknown_action"
    assert (await engine.decide(req(cast, "OWNER", "iam.user.disable", target="NOBODY", mfa=True, rtype="PROJECT"))).reason_code == "resource_type_mismatch"
    assert (await engine.decide(PolicyRequest(actor_id=str(cast.users["OWNER"]), action="iam.self.read", resource_type="USER"))).reason_code == "missing_scope"
    assert (await engine.decide(PolicyRequest(actor_id="not-a-uuid", action="iam.self.read", resource_type="USER", organization_id=str(cast.w.org_a)))).reason_code == "missing_scope"


async def test_actor_from_another_organization_is_not_a_subject_even_if_it_names_our_org(engine: PolicyEngine, cast: Cast) -> None:
    d = await engine.decide(PolicyRequest(actor_id=str(cast.w.user_b), action="iam.self.read", resource_type="USER", organization_id=str(cast.w.org_a), resource_id=str(cast.w.user_b)))
    assert (d.effect, d.reason_code) == (DENY, "subject_not_found")


async def test_disabled_user_and_revoked_membership_lose_access_immediately(engine: PolicyEngine, cast: Cast) -> None:
    with cast.w.pg.connect() as c:
        c.execute("UPDATE organization.memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = %s", [cast.users["ADMIN"]])
        c.execute("UPDATE iam.users SET status = 'DISABLED', row_version = row_version + 1 WHERE id = %s", [cast.users["OWNER"]])
    assert (await engine.decide(req(cast, "ADMIN", "iam.user.disable", target="NOBODY", mfa=True))).reason_code == "membership_inactive"
    assert (await engine.decide(req(cast, "OWNER", "iam.self.read"))).reason_code == "subject_inactive"


async def test_services_and_agents_are_not_users_and_human_only_actions_say_so(engine: PolicyEngine, cast: Cast) -> None:
    for actor_type in ("SERVICE", "MANAGER", "WORKER_RUN"):
        assert (await engine.decide(req(cast, "OWNER", "iam.user.disable", target="NOBODY", mfa=True, attributes={"actor_type": actor_type}))).reason_code == "human_only_action"
        assert (await engine.decide(req(cast, "OWNER", "iam.self.read", attributes={"actor_type": actor_type}))).reason_code == "actor_type_unsupported"  # AUTH-012


@pytest.mark.parametrize(("level", "effect"), [("A0", ALLOW), ("A1", ALLOW), ("A2", ALLOW), ("A3", DENY), ("A4", DENY), ("A9", DENY), ("", DENY)])
async def test_autonomy_levels_beyond_a2_are_not_permitted(engine: PolicyEngine, cast: Cast, level: str, effect: Effect) -> None:
    assert (await engine.decide(req(cast, "OWNER", "iam.self.read", attributes={"autonomy_level": level}))).effect is effect


def project_policy() -> PolicyConfig:
    doc = {"schemaVersion": 1, "version": "2026-11-11.9", "status": "WORKING", "privilegedRoles": ["PROJECT_ADMIN"], "actions": {
        "test.project.read": {"resourceType": "PROJECT", "allow": {"projectRoles": ["ANALYST", "PROJECT_ADMIN"]}},
        "test.project.manage": {"resourceType": "PROJECT", "allow": {"projectRoles": ["PROJECT_ADMIN"]}},
        "test.project.approve": {"resourceType": "PROJECT", "allow": {"projectRoles": ["PROJECT_ADMIN"]}, "approvalRequired": True}}}
    raw = json.dumps(doc).encode()
    return parse_policy_config(raw, hashlib.sha256(raw).hexdigest())


async def test_project_scoped_grants_and_privileged_project_role_needs_mfa(iam_world: Any, cast: Cast) -> None:
    eng = PolicyEngine(project_policy(), create_session_factory(iam_world.engine()))

    def preq(who: str, action: str, mfa: bool = False, project: Any = None) -> PolicyRequest:
        return PolicyRequest(actor_id=str(cast.users[who]), action=action, resource_type="PROJECT", organization_id=str(iam_world.org_a),
                             project_id=str(project or cast.project), attributes={"mfa_verified": mfa})
    assert (await eng.decide(preq("ANALYST", "test.project.read"))).effect is ALLOW
    assert (await eng.decide(preq("ANALYST", "test.project.manage"))).reason_code == "no_matching_grant"
    assert (await eng.decide(preq("PADMIN", "test.project.manage"))).reason_code == "mfa_required"
    assert (await eng.decide(preq("PADMIN", "test.project.manage", mfa=True))).effect is ALLOW
    assert (await eng.decide(preq("PADMIN", "test.project.approve", mfa=True))).effect is Effect.APPROVAL_REQUIRED  # a human decision is still needed
    assert (await eng.decide(preq("NOBODY", "test.project.read"))).reason_code == "no_matching_grant"
    assert (await eng.decide(preq("ANALYST", "test.project.read", project=cast.other_project))).reason_code == "resource_not_visible"  # another organization's project
    assert (await eng.decide(preq("ANALYST", "test.project.read", project=uuid4()))).reason_code == "resource_not_visible"  # same answer as a nonexistent one
    with cast.w.pg.connect() as c:
        c.execute("UPDATE project.project_memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = %s", [cast.users["ANALYST"]])
    assert (await eng.decide(preq("ANALYST", "test.project.read"))).reason_code == "no_matching_grant"


async def test_invalid_configuration_means_deny_everything_with_a_visible_version(iam_world: Any, cast: Cast, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from ai_res.policy import engine as engine_module
    from ai_res.policy.config import PolicyConfigError

    def broken() -> Any:
        raise PolicyConfigError("checksum mismatch")
    monkeypatch.setattr(engine_module, "load_packaged_policy", broken)
    with caplog.at_level(logging.ERROR, logger="ai_res.policy"):
        eng = PolicyEngine.from_packaged(create_session_factory(iam_world.engine()))
    assert "DENY-ALL" in caplog.text
    for action in ("iam.self.read", "iam.user.disable", "anything.else"):
        d = await eng.decide(req(cast, "OWNER", action, mfa=True))
        assert (d.effect, d.reason_code, d.policy_version) == (DENY, "policy_config_invalid", "invalid-config")


# ---------- enforcer ----------
def enforcer(world: Any, eng: Any, config: PolicyConfig | None = None, timeout: float = 2.0) -> PolicyEnforcer:
    return PolicyEnforcer(eng, create_session_factory(world.engine()), config or load_packaged_policy(), timeout_seconds=timeout)


def audit_rows(world: Any) -> list[tuple[Any, ...]]:
    with world.pg.connect() as c:
        return c.execute("SELECT action, result, reason_code, details->>'policyAction', details->>'policyVersion', actor_id FROM audit.audit_events ORDER BY occurred_at, id").fetchall()


async def test_allow_is_audited_with_policy_version_in_the_callers_transaction(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    async with uow:
        await uow.with_tenant(iam_world.org_a)
        await enf.authorize(req(cast, "OWNER", "iam.self.password_change"), session=uow.session)
    assert audit_rows(iam_world) == [("POLICY_DECISION", "SUCCEEDED", "allowed_self", "iam.self.password_change", load_packaged_policy().version, cast.users["OWNER"])]


async def test_audit_of_an_allow_rolls_back_with_the_protected_action(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    with pytest.raises(RuntimeError):
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await enf.authorize(req(cast, "OWNER", "iam.self.password_change"), session=uow.session)
            raise RuntimeError("the protected action failed")
    assert audit_rows(iam_world) == []


async def test_read_only_self_introspection_may_skip_the_allow_audit_but_denials_are_always_recorded(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
        await uow.with_tenant(iam_world.org_a)
        await enf.authorize(req(cast, "OWNER", "iam.self.read"), session=uow.session)
    assert audit_rows(iam_world) == []
    with pytest.raises(ProblemError):
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await enf.authorize(req(cast, "ANALYST", "iam.user.disable", target="NOBODY", mfa=True), session=uow.session)
    assert [(r[0], r[1], r[2]) for r in audit_rows(iam_world)] == [("POLICY_DECISION", "DENIED", "no_matching_grant")]


async def test_denial_is_audited_even_though_the_callers_transaction_rolls_back(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    with pytest.raises(ProblemError) as e:
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await uow.session.execute(text("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (:i, :o, 'p', 'GREENFIELD')"), {"i": uuid4(), "o": iam_world.org_a})
            await enf.authorize(req(cast, "ADMIN", "iam.user.disable", target="NOBODY", mfa=False), session=uow.session)
    assert e.value.code is ErrorCode.ACCESS_DENIED and e.value.status == 403 and e.value.errors == [{"field": "policy", "reason": "denied"}]
    rows = audit_rows(iam_world)
    assert len(rows) == 1 and rows[0][1] == "DENIED" and rows[0][2] == "mfa_required"
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM project.projects WHERE name = 'p' AND id NOT IN (%s, %s)", [cast.project, cast.other_project]).fetchone()[0] == 0


async def test_concealed_denial_is_indistinguishable_from_a_missing_object(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    with pytest.raises(ProblemError) as denied:
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await enf.authorize(req(cast, "ANALYST", "iam.user.disable", target="NOBODY", mfa=True), session=uow.session, conceal=True)
    assert denied.value.code is ErrorCode.RESOURCE_NOT_FOUND and denied.value.status == 404 and denied.value.detail == "Resource not found." and denied.value.errors is None


async def test_engine_outage_timeout_and_garbage_fail_closed_with_503(iam_world: Any, cast: Cast) -> None:
    class Down:
        async def decide(self, request: PolicyRequest) -> PolicyDecision:
            raise ConnectionError("database down")

    class Hung:
        async def decide(self, request: PolicyRequest) -> PolicyDecision:
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

    class Garbage:
        async def decide(self, request: PolicyRequest) -> Any:
            return {"effect": "ALLOW"}  # not a PolicyDecision

    for eng in (Down(), Hung(), Garbage()):
        with pytest.raises(ProblemError) as e:
            async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
                await uow.with_tenant(iam_world.org_a)
                await enforcer(iam_world, eng, timeout=0.2).authorize(req(cast, "OWNER", "iam.self.password_change"), session=uow.session)
        assert e.value.code is ErrorCode.POLICY_ENGINE_UNAVAILABLE and e.value.status == 503
    assert audit_rows(iam_world) == []


async def test_a_real_database_outage_inside_the_engine_fails_closed(iam_world: Any, cast: Cast) -> None:
    class BrokenFactory:
        def __call__(self) -> Any:
            raise ConnectionError("cannot connect")
    eng = PolicyEngine(load_packaged_policy(), BrokenFactory())  # type: ignore[arg-type]
    with pytest.raises(ProblemError) as e:
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await enforcer(iam_world, eng).authorize(req(cast, "OWNER", "iam.self.password_change"), session=uow.session)
    assert e.value.code is ErrorCode.POLICY_ENGINE_UNAVAILABLE


async def test_failed_allow_audit_aborts_the_action(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    enf = enforcer(iam_world, engine)
    with pytest.raises(Exception):  # noqa: B017 - RLS/validation error surfaces unchanged: the action must not proceed
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_b)  # context of ANOTHER organization: the audit insert is refused by RLS WITH CHECK
            await enf.authorize(req(cast, "OWNER", "iam.self.password_change"), session=uow.session)
    assert audit_rows(iam_world) == []


async def test_a_failing_denial_audit_still_refuses_the_action_with_503(iam_world: Any, cast: Cast, engine: PolicyEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_res.modules.audit.writer import SqlAuditWriter

    async def boom(self: Any, record: Any, **kw: Any) -> None:
        raise RuntimeError("audit down")

    monkeypatch.setattr(SqlAuditWriter, "write", boom)
    enf = enforcer(iam_world, engine)
    with pytest.raises(ProblemError) as e:
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await enf.authorize(req(cast, "ADMIN", "iam.user.disable", target="NOBODY", mfa=False), session=uow.session)
    assert e.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE and e.value.status == 503  # the action is not performed, and nothing pretends it was refused cleanly


async def test_a_revoked_organization_membership_closes_project_and_self_grants_too(iam_world: Any, cast: Cast, engine: PolicyEngine) -> None:
    with iam_world.pg.connect() as c:
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code, status) VALUES (%s,%s,%s,'AUDITOR','REVOKED')", [uuid4(), iam_world.org_a, cast.users["PADMIN"]])
    for action, project in (("iam.self.read", None), ("iam.user.disable", cast.project)):
        d = await engine.decide(req(cast, "PADMIN", action, project_id=None if project is None else str(project), mfa=True))
        assert d.effect.value == "DENY" and d.reason_code == "membership_inactive", action
