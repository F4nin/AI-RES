"""Actual PG owner-only activation with synthetic MFA, policy and evidence."""
import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from importlib import resources
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, evidence_hash
from ai_res.modules.model_registry.owner_review import OwnerReviewScope
from ai_res.modules.model_registry.profile_approval import (
    ACTION,
    ProfileApprovalAction,
    ProfileApprovalDecision,
    ProfileApprovalService,
    profile_snapshot_hash,
)
from ai_res.policy.config import load_packaged_policy, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

from .test_model_admission import expected_for, install_generation, observed
from .test_model_owner_review import ReviewWorld
from .test_model_registry import add_profile, approve

pytestmark = pytest.mark.postgres
ACCEPTANCE = b'{"syntheticBifrostAcceptance":"fixture-only"}'


class ApprovalWorld(ReviewWorld):
    def __init__(self, iam):
        super().__init__(iam)
        with iam.pg.connect() as c:
            self.profile_id = add_profile(c, key="approval-fixture", provider="deepseek", provider_model_id="deepseek-flash",
                identity_mode="FLASH_OBSERVED", pinned_model_version=None, capabilities=["CHAT", "STREAMING"], retry_class="NONE")
            c.execute("INSERT INTO platform.model_admission_operators(database_login,organization_id,user_id,profile_id) "
                      "VALUES('ai_res_migrator',%s,%s,%s)", [iam.org_a, iam.user_a, self.profile_id])
        self.scope = OwnerReviewScope(iam.org_a, iam.user_a, self.profile_id)
        self.expected = expected_for(self.profile_id)
        self.observation = observed(self.expected)
        self.expected = replace(self.expected, evidence_sha256=evidence_hash(self.observation).hex())
        install_generation(iam.pg, self.expected)  # synthetic human identity acceptance fixture
        data = json.loads(resources.files("ai_res.policy").joinpath("policy_config.json").read_text())
        data["version"] = "2026-11-18.141"
        data["actions"][ACTION] = {"resourceType": "MODEL_PROFILE_APPROVAL", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
                                   "requiresMfa": True, "humanOnly": True, "auditAllow": True}
        raw = json.dumps(data).encode()
        self.policy_raw = raw
        self.config = parse_policy_config(raw, hashlib.sha256(raw).hexdigest())
        self.policy = PolicyEnforcer(PolicyEngine(self.config, self.factory), self.factory, self.config, timeout_seconds=2)
        self.owner_engine = iam.engine("ai_res_migrator")
        self.owner_factory = create_session_factory(self.owner_engine)

    def approval(self, *, factory=None, policy=None, scope=True, login="ai_res_migrator"):
        return ProfileApprovalService(factory or self.owner_factory, policy or self.policy,
            scope=self.scope if scope is True else scope, owner_login=login, sessions=self.sessions)

    def command(self):
        raw = self.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=%s", self.profile_id)[0][0]
        return ProfileApprovalDecision(uuid4(), uuid4(), ProfileApprovalAction.APPROVE_PROFILE_AND_ACCEPT_BIFROST,
            profile_snapshot_hash(raw), evidence_hash(self.expected).hex(), evidence_hash(self.observation).hex(),
            hashlib.sha256(ACCEPTANCE).hexdigest(), self.config.version)

    async def apply(self, actor, command, *, service=None, acceptance=ACCEPTANCE):
        return await (service or self.approval()).execute(actor, command, expectation=json.dumps(self.expected.to_dict()),
            observation=json.dumps(self.observation.to_dict()), bifrost_acceptance=acceptance)

    def approvals(self):
        return self.sql("SELECT id,actor_id,object_id,details FROM audit.audit_events WHERE action='MODEL_PROFILE_APPROVED'")

    def status(self):
        return self.sql("SELECT status,approved_by,approved_at IS NOT NULL FROM platform.model_profiles WHERE id=%s", self.profile_id)


@pytest.fixture
async def approval_world(iam_world):
    world = ApprovalWorld(iam_world)
    yield world
    await world.owner_engine.dispose()


async def test_human_approval_is_atomic_audited_and_exactly_replayable(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()
    result = await w.apply(actor, command)
    assert w.status() == [("APPROVED", actor.user_id, True)]
    assert result.profile_id == w.profile_id and result.generation == 1
    assert w.approvals()[0][:3] == (command.decision_id, actor.user_id, w.profile_id)
    await w.owner_engine.dispose()
    w.sql("UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=%s", w.profile_id)
    assert await w.apply(actor, command) == result
    assert len(w.approvals()) == 1
    assert w.sql("SELECT blocked FROM platform.model_admission_controls WHERE profile_id=%s", w.profile_id) == [(True,)]
    with w.iam.pg.connect("ai_res_migrator") as c:
        assert c.execute("SELECT current_user,session_user").fetchone() == ("ai_res_migrator", "ai_res_migrator")


async def test_concurrent_identical_decisions_do_not_duplicate_activation_or_audit(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()
    results = await asyncio.gather(*(w.apply(actor, command) for _ in range(3)))
    assert results == [results[0]] * 3 and len(w.approvals()) == 1


async def test_decision_id_reuse_cannot_change_exact_human_target(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()
    await w.apply(actor, command)
    with pytest.raises(AdmissionDenied):
        await w.apply(actor, replace(command, correlation_id=uuid4()))
    assert len(w.approvals()) == 1


@pytest.mark.parametrize("change", ["api", "unconfigured", "wrong-login", "other-human", "forged-session", "logout",
                                    "factor", "policy-deny", "profile-hash", "acceptance", "blocked", "generation", "pending"])
async def test_missing_authority_or_stale_evidence_never_activates(approval_world, change):
    w = approval_world
    actor, command, service = await w.actor(), w.command(), w.approval()
    acceptance = ACCEPTANCE
    if change == "api":
        service = w.approval(factory=w.factory, login="ai_res_api")
    elif change == "unconfigured":
        service = w.approval(scope=None)
    elif change == "wrong-login":
        service = w.approval(login="other_migrator")
    elif change == "other-human":
        actor = await w.actor(other=True)
    elif change == "forged-session":
        actor = replace(actor, session_id=uuid4())
    elif change == "logout":
        w.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1")
    elif change == "factor":
        w.sql("UPDATE iam.mfa_factors SET status='REVOKED',row_version=row_version+1")
    elif change == "policy-deny":
        config = load_packaged_policy()
        service = w.approval(policy=PolicyEnforcer(PolicyEngine(config, w.factory), w.factory, config, timeout_seconds=2))
    elif change == "profile-hash":
        command = replace(command, profile_sha256="e" * 64)
    elif change == "acceptance":
        acceptance = b"different-synthetic-acceptance"
    elif change == "blocked":
        w.sql("UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=%s", w.profile_id)
    elif change == "generation":
        install_generation(w.iam.pg, replace(w.expected, admission_generation=2))
    else:
        # Trusted disposable fixture proves the unresolved barrier, not a live call.
        from ai_res.modules.model_registry.admission import ModelAdmissionGuard

        with w.iam.pg.connect() as c:
            approve(c, w.profile_id)
        await ModelAdmissionGuard(w.factory).begin(w.profile_id, w.expected.managed_versions, request_ref="fixture-pending")
    before = w.status()
    with pytest.raises((AdmissionDenied, AdmissionUnavailable)):
        await w.apply(actor, command, service=service, acceptance=acceptance)
    assert w.status() == before and not w.approvals()


async def test_audit_outage_rolls_back_lifecycle_and_approval_fact(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()
    w.sql("CREATE FUNCTION audit.fixture_profile_audit_outage() RETURNS trigger LANGUAGE plpgsql AS $$ "
          "BEGIN IF NEW.action='MODEL_PROFILE_APPROVED' THEN RAISE EXCEPTION 'synthetic-private-audit'; END IF; RETURN NEW; END $$")
    w.sql("CREATE TRIGGER fixture_profile_audit_outage BEFORE INSERT ON audit.audit_events "
          "FOR EACH ROW EXECUTE FUNCTION audit.fixture_profile_audit_outage()")
    with pytest.raises(AdmissionUnavailable):
        await w.apply(actor, command)
    assert w.status() == [("CANDIDATE", None, False)] and not w.approvals()


async def test_other_approved_profile_blocks_activation(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()
    with w.iam.pg.connect() as c:
        other = add_profile(c, key="other-approved")
        approve(c, other)
    with pytest.raises(AdmissionDenied):
        await w.apply(actor, command)
    assert w.status() == [("CANDIDATE", None, False)] and not w.approvals()


async def test_authority_revoked_while_policy_waits_cannot_activate(approval_world):
    w = approval_world
    actor, command = await w.actor(), w.command()

    class PolicyWait:
        lock_subject_grants = w.policy.lock_subject_grants
        record_allow = w.policy.record_allow

        async def decide(self, request):
            decision = await w.policy.decide(request)
            w.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1")
            return decision

    with pytest.raises(AdmissionDenied):
        await w.apply(actor, command, service=w.approval(policy=PolicyWait()))
    assert w.status() == [("CANDIDATE", None, False)] and not w.approvals()


async def test_session_expiring_during_audit_wait_rolls_back_activation(approval_world):
    w = approval_world
    command = w.command()
    short = SessionService(w.factory, idle=timedelta(seconds=2), absolute=timedelta(seconds=60),
                           touch_interval=timedelta(milliseconds=10))
    issued = await short.create(w.iam.org_a, w.iam.user_a, mfa_verified=True)
    actor = (await short.authenticate(issued.token, touch=False)).session
    w.sql("CREATE SEQUENCE audit.fixture_profile_wait_entry")
    w.sql("GRANT USAGE ON SEQUENCE audit.fixture_profile_wait_entry TO ai_res_owner")
    w.sql("CREATE FUNCTION audit.fixture_profile_audit_wait() RETURNS trigger LANGUAGE plpgsql AS $$ "
          "BEGIN IF NEW.action='MODEL_PROFILE_APPROVED' THEN PERFORM nextval('audit.fixture_profile_wait_entry'); "
          "PERFORM pg_sleep(2.1); END IF; RETURN NEW; END $$")
    w.sql("CREATE TRIGGER fixture_profile_audit_wait BEFORE INSERT ON audit.audit_events "
          "FOR EACH ROW EXECUTE FUNCTION audit.fixture_profile_audit_wait()")
    with pytest.raises(AdmissionDenied):
        await w.apply(actor, command)
    assert w.status() == [("CANDIDATE", None, False)] and not w.approvals()
    # Sequence advancement survives rollback: refusal must have happened AFTER
    # entering the audit trigger, not merely from an early-expired session.
    assert w.sql("SELECT is_called FROM audit.fixture_profile_wait_entry") == [(True,)]


async def test_real_cli_composition_authenticates_token_and_uses_owner_only_for_activation(approval_world, tmp_path, monkeypatch, capsys):
    from ai_res.cli import model_profile
    from ai_res.platform.config import Settings

    w = approval_world
    command = w.command()
    issued = await w.sessions.create(w.iam.org_a, w.iam.user_a, mfa_verified=True)
    files = {}
    owner_value = w.iam.pg.passwords["ai_res_migrator"].encode()
    api_value = w.iam.pg.passwords["ai_res_api"].encode()
    fixture_inputs = {
        "expected": json.dumps(w.expected.to_dict()).encode(), "observed": json.dumps(w.observation.to_dict()).encode(),
        "acceptance": ACCEPTANCE, "policy": w.policy_raw,
        "migrator_password": owner_value,
        "api_password": api_value,
    }
    for name, value in fixture_inputs.items():
        files[name] = tmp_path / name
        files[name].write_bytes(value)
        files[name].chmod(0o600)
    settings = Settings(environment="test", db_host=w.iam.pg.host, db_port=w.iam.pg.port, db_user="ai_res_migrator",
                        db_password_file=files["migrator_password"], db_sslmode="disable")
    monkeypatch.setattr(model_profile, "load_settings", lambda env: settings)
    args = SimpleNamespace(owner_login="ai_res_migrator", auth_db_password_file=files["api_password"], policy_file=files["policy"],
        policy_sha256=hashlib.sha256(w.policy_raw).hexdigest(), expectation_file=files["expected"], observation_file=files["observed"],
        bifrost_acceptance_file=files["acceptance"], organization_id=w.iam.org_a, owner_user_id=w.iam.user_a, profile_id=w.profile_id)
    await model_profile._execute(args, command, {}, lambda _: issued.token)
    assert w.status() == [("APPROVED", w.iam.user_a, True)] and len(w.approvals()) == 1
    output = capsys.readouterr()
    assert "APPROVED" in output.out and issued.token not in output.out + output.err
