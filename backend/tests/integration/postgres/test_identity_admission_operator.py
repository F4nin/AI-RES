# ruff: noqa: E501 -- explicit synthetic PostgreSQL fixture SQL
"""Actual EXECUTE-only operator login; synthetic owner decisions, never live approval."""
import asyncio
import hashlib
import json
import secrets
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import timedelta
from importlib import resources
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from psycopg import errors, sql
from sqlalchemy import text

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, ModelAdmissionGuard, evidence_hash
from ai_res.modules.model_registry.identity_operator import IdentityAdmissionOperator, IdentityDecision, IdentityDecisionAction
from ai_res.platform.ports import Effect, PolicyDecision
from ai_res.policy.config import load_packaged_policy, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

from .conftest import alembic_config, run_audit
from .test_model_admission import install_generation, observed, seed
from .test_model_owner_review import ReviewWorld
from .test_model_registry import approve

pytestmark = pytest.mark.postgres
SNAPSHOT = "platform.owner_identity_snapshot(uuid,uuid,uuid,uuid,uuid)"
APPLY = "platform.apply_owner_identity_decision(uuid,uuid,uuid,uuid,uuid,jsonb,text,text,text)"


class OperatorWorld(ReviewWorld):
    def __init__(self, iam):
        super().__init__(iam)
        self.login = "op_" + uuid4().hex
        iam.pg.passwords[self.login] = secrets.token_urlsafe(24)
        with iam.pg.connect() as c:
            c.execute(sql.SQL("CREATE ROLE {} LOGIN INHERIT PASSWORD {}").format(sql.Identifier(self.login), sql.Literal(iam.pg.passwords[self.login])))
            c.execute(sql.SQL("GRANT CONNECT ON DATABASE ai_res_db TO {}").format(sql.Identifier(self.login)))
            c.execute(sql.SQL("GRANT ai_res_model_admission_operator TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE").format(sql.Identifier(self.login)))
            c.execute("INSERT INTO platform.model_admission_operators(database_login,organization_id,user_id,profile_id) VALUES(%s,%s,%s,%s)",
                      [self.login, iam.org_a, iam.user_a, self.profile_id])
        self.engine = iam.engine(self.login)
        self.operator_factory = create_session_factory(self.engine)
        data = json.loads(resources.files("ai_res.policy").joinpath("policy_config.json").read_text())
        data["version"] = "2026-11-18.140"
        data["actions"]["model_admission.review"] = {"resourceType": "MODEL_ADMISSION_REVIEW", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
            "requiresMfa": True, "humanOnly": True, "auditAllow": True}
        for action in ("model_admission.accept_identity", "model_admission.block"):
            data["actions"][action] = {"resourceType": "MODEL_ADMISSION_DECISION", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
                "requiresMfa": True, "humanOnly": True, "auditAllow": True}
        raw = json.dumps(data).encode()
        self.config = parse_policy_config(raw, hashlib.sha256(raw).hexdigest())
        self.policy = PolicyEnforcer(PolicyEngine(self.config, self.factory), self.factory, self.config, timeout_seconds=2)

    def operator(self, *, policy=None, scope=True, factory=None):
        return IdentityAdmissionOperator(factory or self.operator_factory, policy or self.policy, scope=self.scope if scope is True else scope)

    async def command(self, actor, action=IdentityDecisionAction.ACCEPT_IDENTITY):
        review = await self.prepare(actor=actor)
        return IdentityDecision(uuid4(), uuid4(), action, review)

    async def execute(self, actor, command, *, service=None, expected=None, observation=None):
        return await (service or self.operator()).execute(actor, command, expectation=json.dumps((expected or self.expected).to_dict()),
            observation=json.dumps((observation or self.observation).to_dict()))

    def next_evidence(self):
        self.expected = replace(self.expected, admission_generation=self.expected.admission_generation + 1)
        self.observation = observed(self.expected)
        self.expected = replace(self.expected, evidence_sha256=evidence_hash(self.observation).hex())

    def decisions(self):
        return self.sql("SELECT action,generation,database_login,user_id,session_id,policy_version,correlation_id,reason_code FROM platform.model_admission_decisions")


@pytest.fixture
async def world(iam_world):
    value = OperatorWorld(iam_world)
    yield value
    await value.engine.dispose()
    with iam_world.pg.connect() as c:
        c.execute(sql.SQL("REVOKE CONNECT ON DATABASE ai_res_db FROM {}").format(sql.Identifier(value.login)))
        c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(value.login)))
    del iam_world.pg.passwords[value.login]


async def test_explicit_identity_acceptance_is_atomic_and_never_activates_candidate(world):
    actor = await world.actor()
    command = await world.command(actor)
    receipt = await world.execute(actor, command)
    assert (receipt.decision_id, receipt.profile_id, receipt.generation, receipt.action) == (command.decision_id, world.profile_id, 1, command.action)
    assert world.sql("SELECT status,approved_at,approved_by FROM platform.model_profiles") == [("CANDIDATE", None, None)]
    assert world.sql("SELECT current_generation,blocked,call_sequence FROM platform.model_admission_controls") == [(1, False, 0)]
    assert world.decisions() == [("ACCEPT_IDENTITY", 1, world.login, actor.user_id, actor.session_id, world.config.version, command.correlation_id, "HUMAN_IDENTITY_ACCEPTED")]
    assert len(world.sql("SELECT expectation_sha256 FROM platform.model_admission_versions")) == 1
    with pytest.raises(AdmissionDenied):
        await ModelAdmissionGuard(world.factory).begin(world.profile_id, world.expected.managed_versions, request_ref="cannot-run-candidate")
    with world.iam.pg.connect(world.login) as c:
        assert c.execute("SELECT coalesce(current_setting('app.migration_mode',true),'')").fetchone()[0] != "on"
        assert c.execute("SELECT current_user,session_user").fetchone() == (world.login, world.login)


async def test_reapproval_creates_generation_and_preserves_original_profile_approval(world):
    actor = await world.actor()
    await world.execute(actor, await world.command(actor))
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    before = world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p")
    world.sql("UPDATE platform.model_admission_controls SET blocked=true")
    world.next_evidence()
    await world.execute(actor, await world.command(actor))
    assert world.sql("SELECT current_generation,blocked FROM platform.model_admission_controls") == [(2, False)]
    assert world.sql("SELECT generation FROM platform.model_admission_versions ORDER BY generation") == [(1,), (2,)]
    assert world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p") == before


async def test_lost_reply_replay_never_unblocks_later_revocation_and_new_session_refuses(world):
    actor = await world.actor()
    command = await world.command(actor)
    receipt = await world.execute(actor, command)
    await world.engine.dispose()  # New DB connection/new service after committed response is lost.
    assert await world.execute(actor, command, service=world.operator()) == receipt
    world.sql("UPDATE platform.model_admission_controls SET blocked=true")
    assert await world.execute(actor, command) == receipt
    assert world.sql("SELECT current_generation,blocked FROM platform.model_admission_controls") == [(1, True)]
    assert len(world.decisions()) == 1
    with pytest.raises((AdmissionDenied, AdmissionUnavailable)):
        await world.execute(await world.actor(), command)


async def test_decision_id_reuse_refuses_other_correlation_action_or_evidence(world):
    actor = await world.actor()
    command = await world.command(actor)
    await world.execute(actor, command)
    for changed in (replace(command, correlation_id=uuid4()), replace(command, action=IdentityDecisionAction.BLOCK)):
        with pytest.raises(AdmissionDenied) as caught:
            await world.execute(actor, changed)
        assert caught.value.code == "DECISION_ID_REUSED"
    assert len(world.decisions()) == 1


async def test_concurrent_identical_decisions_commit_once(world):
    actor = await world.actor()
    command = await world.command(actor)
    results = await asyncio.gather(*(world.execute(actor, command) for _ in range(4)))
    assert all(value == results[0] for value in results)
    assert len(world.decisions()) == 1
    assert world.sql("SELECT count(*) FROM platform.model_admission_versions") == [(1,)]


async def test_competing_human_decisions_have_one_winner(world):
    actor = await world.actor()
    command = await world.command(actor)
    results = await asyncio.gather(world.execute(actor, command), world.execute(actor, replace(command, decision_id=uuid4())), return_exceptions=True)
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert len(world.decisions()) == 1


@pytest.mark.parametrize("scenario", ["unconfigured", "other_owner", "forged_session", "forged_org", "service", "api_factory", "wrong_profile", "no_login_binding"])
async def test_wrong_identity_or_database_principal_has_no_authority(world, scenario):
    actor = await world.actor()
    command = await world.command(actor)
    service = world.operator()
    if scenario == "unconfigured":
        service = world.operator(scope=None)
    elif scenario == "other_owner":
        actor = await world.actor(other=True)
    elif scenario == "forged_session":
        actor = replace(actor, session_id=uuid4())
    elif scenario == "forged_org":
        actor = replace(actor, organization_id=world.iam.org_b)
    elif scenario == "service":
        actor = object()
    elif scenario == "api_factory":
        service = world.operator(factory=world.factory)
    elif scenario == "wrong_profile":
        service = world.operator(scope=replace(world.scope, profile_id=uuid4()))
    else:
        world.sql("ALTER TABLE platform.model_admission_operators DISABLE TRIGGER trg_model_admission_operators_append_only")
        world.sql("DELETE FROM platform.model_admission_operators")  # Only disposable superuser fixture can remove a binding.
    with pytest.raises((AdmissionDenied, AdmissionUnavailable)):
        await world.execute(actor, command, service=service)
    assert world.decisions() == []


@pytest.mark.parametrize("scenario", ["logout", "disabled", "membership", "factor", "cleared_mfa", "cached_mfa"])
async def test_live_authority_revocation_blocks_new_decision(world, scenario):
    actor = await world.actor()
    command = await world.command(actor)
    if scenario == "logout":
        world.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1")
    elif scenario == "disabled":
        world.sql("UPDATE iam.users SET status='DISABLED',row_version=row_version+1 WHERE id=%s", actor.user_id)
    elif scenario == "membership":
        world.sql("UPDATE organization.memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", actor.user_id)
    elif scenario == "factor":
        world.sql("UPDATE iam.mfa_factors SET status='REVOKED',row_version=row_version+1")
    elif scenario == "cleared_mfa":
        world.sql("UPDATE iam.sessions SET mfa_verified_at=NULL,row_version=row_version+1")
    else:
        actor = replace(actor, second_factor_pending=True)
    with pytest.raises((AdmissionDenied, AdmissionUnavailable)):
        await world.execute(actor, command)
    assert world.decisions() == []


@pytest.mark.parametrize("scenario", ["packaged", "deny", "approval", "outage", "garbage", "timeout", "policy_version"])
async def test_independent_execute_policy_is_fail_closed(world, scenario):
    actor = await world.actor()
    command = await world.command(actor)
    class Engine:
        async def decide(self, request):
            if scenario == "outage":
                raise RuntimeError("private-provider-data")
            if scenario == "garbage":
                return True
            if scenario == "timeout":
                await asyncio.sleep(1)
            effect = Effect.ALLOW if scenario == "policy_version" else Effect.APPROVAL_REQUIRED if scenario == "approval" else Effect.DENY
            return PolicyDecision(effect=effect, reason_code="synthetic", policy_version="different")
    config = load_packaged_policy() if scenario == "packaged" else world.config
    policy = PolicyEnforcer(PolicyEngine(config, world.factory) if scenario == "packaged" else Engine(), world.factory, config, timeout_seconds=0.02)
    with pytest.raises(AdmissionDenied) as caught:
        await world.execute(actor, command, service=world.operator(policy=policy))
    assert "private-provider-data" not in str(caught.value)
    assert world.decisions() == []


@pytest.mark.parametrize("scenario", ["profile", "block", "pending", "generation", "subject_during_policy", "session_during_policy"])
async def test_review_binding_is_recomputed_after_waits_and_policy(world, scenario):
    actor = await world.actor()
    install_generation(world.iam.pg, world.expected)
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    world.next_evidence()
    command = await world.command(actor)
    service = world.operator()
    if scenario == "profile":
        world.sql("UPDATE platform.model_profiles SET deprecated_at=clock_timestamp()+interval '1 day'")
    elif scenario == "block":
        world.sql("UPDATE platform.model_admission_controls SET blocked=true")
    elif scenario == "pending":
        await ModelAdmissionGuard(world.factory).begin(world.profile_id, world.expected.managed_versions, request_ref="pending")
    elif scenario == "generation":
        install_generation(world.iam.pg, world.expected)
    else:
        original = world.policy
        class ChangingEngine:
            async def decide(self, request):
                assert not world.sql("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND state='idle in transaction'", world.login)
                if scenario == "subject_during_policy":
                    world.sql("UPDATE organization.memberships SET row_version=row_version+1 WHERE user_id=%s", actor.user_id)
                else:
                    world.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1")
                return await original.decide(request)
        service = world.operator(policy=PolicyEnforcer(ChangingEngine(), world.factory, world.config, timeout_seconds=2))
    with pytest.raises((AdmissionDenied, AdmissionUnavailable)):
        await world.execute(actor, command, service=service)
    assert world.decisions() == []


async def test_pending_blocks_acceptance_but_owner_block_preserves_unresolved_call(world):
    actor = await world.actor()
    install_generation(world.iam.pg, world.expected)
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    guard = ModelAdmissionGuard(world.factory)
    ticket = await guard.begin(world.profile_id, world.expected.managed_versions, request_ref="in-flight")
    world.next_evidence()
    command = await world.command(actor)
    with pytest.raises(AdmissionUnavailable):
        await world.execute(actor, command)
    before = world.sql("SELECT to_jsonb(v)::text FROM platform.model_admission_calls v")
    await world.execute(actor, replace(command, action=IdentityDecisionAction.BLOCK))
    assert world.sql("SELECT blocked FROM platform.model_admission_controls") == [(True,)]
    assert world.sql("SELECT to_jsonb(v)::text FROM platform.model_admission_calls v") == before
    with pytest.raises(AdmissionDenied):
        await guard.finalize(ticket, observed(replace(world.expected, admission_generation=1), request_ref="in-flight"))
    assert world.sql("SELECT to_jsonb(v)::text FROM platform.model_admission_calls v") == before


async def test_global_audit_failure_rolls_back_generation_and_control(world):
    actor = await world.actor()
    command = await world.command(actor)
    world.sql("CREATE TRIGGER synthetic_decision_audit_failure BEFORE INSERT ON platform.model_admission_decisions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    with pytest.raises(AdmissionUnavailable):
        await world.execute(actor, command)
    assert world.sql("SELECT count(*) FROM platform.model_admission_versions") == [(0,)]
    assert world.sql("SELECT count(*) FROM platform.model_admission_controls") == [(0,)]
    assert world.decisions() == []


@pytest.mark.parametrize("field", ["binding_sha256", "profile_sha256", "expectation_sha256", "observation_sha256"])
async def test_tampered_review_digest_cannot_authorize_decision(world, field):
    actor = await world.actor()
    command = await world.command(actor)
    command = replace(command, review=replace(command.review, **{field: "0" * 64}))
    with pytest.raises(AdmissionDenied) as caught:
        await world.execute(actor, command)
    assert caught.value.code == "STALE_REVIEW" and world.decisions() == []


@pytest.mark.parametrize("missing", [True, False])
async def test_direct_operator_sql_cannot_omit_or_null_generation(world, missing):
    actor = await world.actor()
    command = await world.command(actor)
    expected = world.expected.to_dict()
    if missing:
        del expected["admissionGeneration"]
    else:
        expected["admissionGeneration"] = None
    eh = hashlib.sha256(canonical_json(expected).encode()).hexdigest()
    cmd = {"decisionId": str(command.decision_id), "correlationId": str(command.correlation_id), "action": command.action.value,
        "review": asdict(command.review) | {"expectation_sha256": eh}, "expectationSha256": eh,
        "observationSha256": evidence_hash(world.observation).hex()}
    with world.iam.pg.connect(world.login) as c:
        state = c.execute("SELECT platform.owner_identity_snapshot(%s,%s,%s,%s,%s)",
            [actor.organization_id, actor.user_id, actor.session_id, world.profile_id, command.decision_id]).fetchone()[0]
        with pytest.raises(errors.CheckViolation, match="stale generation"):
            c.execute("SELECT platform.apply_owner_identity_decision(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                [actor.organization_id, actor.user_id, actor.session_id, world.profile_id, command.decision_id,
                 canonical_json(state), canonical_json(cmd), canonical_json(expected), canonical_json(world.observation.to_dict())])
    assert world.decisions() == [] and world.sql("SELECT count(*) FROM platform.model_admission_versions") == [(0,)]


async def _wait_for_operator_lock(world):
    async def wait():
        while not world.sql("SELECT 1 FROM pg_stat_activity WHERE usename=%s AND wait_event_type='Lock'", world.login):
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait(), timeout=2)


@pytest.mark.parametrize("expiry", ["idle", "absolute", "profile"])
async def test_time_expiry_while_waiting_for_fence_rolls_back(world, expiry):
    if expiry != "profile":
        sessions = SessionService(world.factory, idle=timedelta(milliseconds=650),
            absolute=timedelta(milliseconds=650) if expiry == "absolute" else timedelta(seconds=30), touch_interval=timedelta(milliseconds=10))
        issued = await sessions.create(world.iam.org_a, world.iam.user_a, mfa_verified=True)
        actor = (await sessions.authenticate(issued.token, touch=False)).session
        assert actor is not None
    else:
        actor = await world.actor()
        world.sql("UPDATE platform.model_profiles SET deprecated_at=clock_timestamp()+interval '650 milliseconds'")
    command = await world.command(actor)
    with world.iam.pg.connect() as blocker:
        blocker.execute("SELECT pg_advisory_lock(hashtextextended('ai_res.model_profile_lifecycle:' || %s,0))", [str(world.profile_id)])
        task = asyncio.create_task(world.execute(actor, command))
        try:
            await _wait_for_operator_lock(world)
            await asyncio.sleep(0.7)
        finally:
            blocker.execute("SELECT pg_advisory_unlock(hashtextextended('ai_res.model_profile_lifecycle:' || %s,0))", [str(world.profile_id)])
        with pytest.raises(AdmissionUnavailable):
            await task
    assert world.decisions() == [] and world.sql("SELECT count(*) FROM platform.model_admission_controls") == [(0,)]


async def test_factor_first_lock_order_allows_mfa_reset_to_revoke_session(world):
    actor = await world.actor()
    command = await world.command(actor)
    with world.iam.pg.connect(autocommit=False) as reset:
        reset.execute("SET LOCAL lock_timeout='400ms'")
        reset.execute("UPDATE iam.mfa_factors SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", [actor.user_id])
        task = asyncio.create_task(world.execute(actor, command))
        await _wait_for_operator_lock(world)
        reset.execute("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='MFA_RESET',row_version=row_version+1 WHERE id=%s", [actor.session_id])
        reset.commit()
        with pytest.raises(AdmissionUnavailable):
            await task
    assert world.decisions() == []


async def test_operator_custom_guc_never_confers_owner_table_access_and_restores_after_function(world):
    actor = await world.actor()
    async with UnitOfWork(world.operator_factory) as uow:
        await uow.session.execute(text("SELECT set_config('app.migration_mode','sentinel',true)"))
        await uow.session.execute(text("SELECT set_config('search_path','public,pg_temp',true)"))
        await world.operator()._snapshot(uow.session, actor, uuid4())
        assert (await uow.session.execute(text("SELECT current_setting('app.migration_mode')"))).scalar_one() == "sentinel"
    with world.iam.pg.connect(world.login) as c:
        c.execute("SELECT set_config('app.migration_mode','on',false)")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("SELECT * FROM platform.model_admission_decisions")


async def test_committed_decision_survives_new_python_interpreter(world):
    actor = await world.actor()
    command = await world.command(actor)
    await world.execute(actor, command)
    child = """
import json,sys,psycopg
from pathlib import Path
d=json.load(sys.stdin)
with psycopg.connect(host=d['host'],port=d['port'],dbname='ai_res_db',user=d['login'],password=Path(d['passwordFile']).read_text(),sslmode='disable') as c:
 r=c.execute('SELECT platform.owner_identity_snapshot(%s,%s,%s,%s,%s)',d['args']).fetchone()[0]['receipt']
 print(json.dumps({'generation':r['generation'],'action':r['action']}))
"""
    data = {"host": world.iam.pg.host, "port": world.iam.pg.port, "login": world.login,
        "passwordFile": str(world.iam.tmp_path / f"{world.login}_pw"),
        "args": [str(value) for value in (actor.organization_id, actor.user_id, actor.session_id, world.profile_id, command.decision_id)]}
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-B", "-c", child], input=json.dumps(data), text=True,
        capture_output=True, timeout=20, check=False)
    assert result.returncode == 0, "Child failed; raw output withheld."
    assert json.loads(result.stdout) == {"generation": 1, "action": "ACCEPT_IDENTITY"}
    assert len(world.decisions()) == 1


async def test_operator_and_api_have_no_direct_data_or_authority_grants(world):
    with world.iam.pg.connect() as c:
        assert run_audit(c, "grants_audit.sql") == [] and run_audit(c, "rls_coverage.sql") == []
    with world.iam.pg.connect(world.login) as c:
        for statement in ("SELECT * FROM platform.model_profiles", "SELECT * FROM iam.sessions", "SELECT * FROM platform.model_admission_operators",
            "SELECT * FROM platform.model_admission_decisions", "UPDATE platform.model_admission_controls SET blocked=false",
            "INSERT INTO platform.model_admission_versions DEFAULT VALUES", "SET ROLE ai_res_owner", "SET ROLE ai_res_api_group", "CREATE TABLE platform.op_attack(id int)"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(statement)
    with world.iam.pg.connect("ai_res_api") as c:
        for signature in (SNAPSHOT, APPLY):
            assert c.execute("SELECT has_function_privilege(current_user,%s,'EXECUTE')", [signature]).fetchone() == (False,)
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("SELECT platform.owner_identity_snapshot(%s,%s,%s,%s,%s)", [world.iam.org_a, world.iam.user_a, uuid4(), world.profile_id, uuid4()])


@pytest.mark.parametrize("statement,code", [
    (f"GRANT EXECUTE ON FUNCTION {SNAPSHOT} TO ai_res_api", "operator_definer_configuration"),
    (f"ALTER FUNCTION {SNAPSHOT} SET search_path=public,pg_catalog", "operator_definer_configuration"),
    (f"ALTER FUNCTION {SNAPSHOT} SECURITY INVOKER", "operator_definer_configuration"),
    ("GRANT SELECT ON platform.model_profiles TO ai_res_model_admission_operator", "operator_table_privilege"),
    ("GRANT ai_res_api_group TO ai_res_model_admission_operator", "operator_role_escalation"),
    ("GRANT ai_res_model_admission_operator TO ai_res_api", "runtime_operator_authority"),
    ("GRANT ai_res_model_admission_operator TO ai_res_api WITH INHERIT FALSE, SET TRUE", "runtime_operator_authority"),
    ("GRANT SET ON PARAMETER app.migration_mode TO ai_res_api", "runtime_parameter_privilege"),
    ("GRANT SET ON PARAMETER app.migration_mode TO PUBLIC", "unexpected_parameter_acl"),
    ("GRANT ALTER SYSTEM ON PARAMETER app.migration_mode TO ai_res_owner", "unexpected_parameter_acl"),
    ("REVOKE SET ON PARAMETER app.migration_mode FROM ai_res_owner", "owner_parameter_acl_missing"),
    ("CREATE FUNCTION platform.owner_identity_snapshot() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'", "security_definer_function"),
])
def test_grants_audit_detects_operator_boundary_drift(migrated, statement, code):
    with migrated.connect(autocommit=False) as c:
        assert run_audit(c, "grants_audit.sql") == []
        c.execute(statement)
        assert code in {value[0] for value in run_audit(c, "grants_audit.sql")}
        c.rollback()  # Role/parameter ACLs are cluster-wide; a DB clone cannot undo them.


def test_additive_upgrade_preserves_previous_generation_receipt_audit_and_no_authority_seeds(empty_db, upgrade):
    revisions = [r for r in ScriptDirectory.from_config(alembic_config()).walk_revisions()
                 if Path(r.path).name.endswith("_identity_admission_operator.py")]
    assert len(revisions) == 1
    revision = revisions[0]
    upgrade(revision.down_revision)
    expected = seed(empty_db)
    tables = ("model_profiles", "model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit")
    with empty_db.connect() as c:
        call_id = uuid4()
        c.execute("INSERT INTO platform.model_admission_calls(id,profile_id,generation,call_sequence,request_ref,expected_sha256) VALUES(%s,%s,1,1,'old-pending',%s)",
            [call_id, expected.managed_versions.profile_id, evidence_hash(expected)])
        c.execute("INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code) VALUES(%s,%s,%s,'BEGIN','RESERVED')",
            [uuid4(), expected.managed_versions.profile_id, call_id])
        c.execute("UPDATE platform.model_admission_controls SET call_sequence=1,blocked=true")
        before = [c.execute(sql.SQL("SELECT to_jsonb(v)::text FROM platform.{} v ORDER BY 1").format(sql.Identifier(t))).fetchall() for t in tables]
    upgrade(revision.revision)
    with empty_db.connect() as c:
        after = [c.execute(sql.SQL("SELECT to_jsonb(v)::text FROM platform.{} v ORDER BY 1").format(sql.Identifier(t))).fetchall() for t in tables]
        assert after == before
        assert c.execute("SELECT count(*) FROM platform.model_admission_operators").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM platform.model_admission_decisions").fetchone() == (0,)
        assert run_audit(c, "grants_audit.sql") == [] and run_audit(c, "rls_coverage.sql") == []
