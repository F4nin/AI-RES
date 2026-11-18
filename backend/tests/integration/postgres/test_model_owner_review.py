# ruff: noqa: E501 -- explicit synthetic fixture SQL
"""Real PG/API-role owner-review mechanics; no actual person/model is approved."""
import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from importlib import resources
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, ModelAdmissionGuard, evidence_hash
from ai_res.modules.model_registry.owner_review import ACTION, OwnerReviewScope, OwnerReviewService
from ai_res.platform.ports import Effect, PolicyDecision
from ai_res.policy.config import load_packaged_policy, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

from .test_model_admission import expected_for, install_generation, observed
from .test_model_registry import add_profile, approve

pytestmark = pytest.mark.postgres


class ReviewWorld:
    def __init__(self, iam):
        self.iam = iam
        self.factory = create_session_factory(iam.engine())
        self.sessions = SessionService(self.factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12), touch_interval=timedelta(minutes=1))
        with iam.pg.connect() as c:
            c.execute("UPDATE organization.memberships SET role_code='ORGANIZATION_OWNER',row_version=row_version+1")
            # Synthetic already-enrolled factor; no real seed/keys or MFA claims.
            for org, user in ((iam.org_a, iam.user_a), (iam.org_b, iam.user_b)):
                c.execute("INSERT INTO iam.mfa_factors(id,organization_id,user_id,factor_type,status,secret_ciphertext,confirmed_at) "
                          "VALUES(%s,%s,%s,'TOTP','ACTIVE',decode(repeat('ab',40),'hex'),clock_timestamp())", [uuid4(), org, user])
            self.profile_id = add_profile(c, key="owner-review", provider="deepseek", provider_model_id="deepseek-flash", identity_mode="FLASH_OBSERVED", pinned_model_version=None)
        self.scope = OwnerReviewScope(iam.org_a, iam.user_a, self.profile_id)
        self.expected = expected_for(self.profile_id)
        self.observation = observed(self.expected)
        self.expected = replace(self.expected, evidence_sha256=evidence_hash(self.observation).hex())
        data = json.loads(resources.files("ai_res.policy").joinpath("policy_config.json").read_text())
        data["version"] = "2026-11-18.139"
        data["actions"][ACTION] = {"resourceType": "MODEL_ADMISSION_REVIEW", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
                                    "requiresMfa": True, "humanOnly": True, "auditAllow": True}
        raw = json.dumps(data).encode()
        self.config = parse_policy_config(raw, hashlib.sha256(raw).hexdigest())
        self.policy = PolicyEnforcer(PolicyEngine(self.config, self.factory), self.factory, self.config, timeout_seconds=2)

    def service(self, *, policy=None, scope=True):
        return OwnerReviewService(self.factory, policy or self.policy, scope=self.scope if scope is True else scope)

    async def actor(self, *, other=False, mfa=True):
        org, user = (self.iam.org_b, self.iam.user_b) if other else (self.iam.org_a, self.iam.user_a)
        issued = await self.sessions.create(org, user, mfa_verified=mfa)
        actor = (await self.sessions.authenticate(issued.token)).session
        assert actor is not None
        return actor

    async def prepare(self, *, service=None, actor=None, previous=None, expected=None, observation=None):
        return await (service or self.service()).prepare(actor or await self.actor(),
            expectation=json.dumps((expected or self.expected).to_dict()), observation=json.dumps((observation or self.observation).to_dict()), previous=previous)

    def sql(self, statement, *params):
        with self.iam.pg.connect() as c:
            return c.execute(statement, list(params)).fetchall() if statement.lstrip().startswith("SELECT") else c.execute(statement, list(params))

    def domain_snapshot(self):
        with self.iam.pg.connect() as c:
            return [c.execute(sql.SQL("SELECT to_jsonb(t)::text FROM platform.{} t ORDER BY 1").format(sql.Identifier(table))).fetchall()
                    for table in ("model_profiles", "model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit")]


@pytest.fixture
def world(iam_world):
    return ReviewWorld(iam_world)


async def test_exact_human_review_revalidates_without_approving_or_mutating_profile(world):
    actor = await world.actor()
    before = world.domain_snapshot()
    review = await world.prepare(actor=actor)
    assert await world.prepare(actor=actor, previous=review) == review
    assert world.domain_snapshot() == before
    audits = world.sql("SELECT action,actor_id,object_type,object_id,details FROM audit.audit_events")
    assert len(audits) == 2
    assert all(r[:4] == ("POLICY_DECISION", actor.user_id, "MODEL_ADMISSION_REVIEW", world.profile_id) for r in audits)
    assert all(r[4]["policyAction"] == ACTION for r in audits)
    assert "synthetic-fingerprint" not in repr(audits)
    with world.iam.pg.connect("ai_res_api") as c:
        assert c.execute("SELECT has_table_privilege(current_user,'platform.model_profiles','UPDATE')").fetchone() == (False,)


@pytest.mark.parametrize("scenario", ["unconfigured", "other_owner", "same_org_owner", "wrong_profile", "service", "forged_session", "forged_org"])
async def test_exact_binding_cannot_be_replaced_by_tenant_owner_role(world, scenario):
    actor, service = await world.actor(), world.service()
    if scenario == "unconfigured":
        service = world.service(scope=None)
    elif scenario == "other_owner":
        actor = await world.actor(other=True)
    elif scenario == "same_org_owner":
        other = uuid4()
        world.sql("INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES(%s,%s,'other@example.test','other@example.test','Other')", other, world.iam.org_a)
        world.sql("INSERT INTO organization.memberships(id,organization_id,user_id,role_code) VALUES(%s,%s,%s,'ORGANIZATION_OWNER')", uuid4(), world.iam.org_a, other)
        issued = await world.sessions.create(world.iam.org_a, other, mfa_verified=True)
        actor = (await world.sessions.authenticate(issued.token)).session
        assert actor is not None
    elif scenario == "wrong_profile":
        service = world.service(scope=replace(world.scope, profile_id=uuid4()))
    elif scenario == "service":
        actor = object()
    elif scenario == "forged_session":
        actor = replace(actor, session_id=uuid4())
    else:
        actor = replace(actor, organization_id=world.iam.org_b)
    before = world.domain_snapshot()
    with pytest.raises(AdmissionDenied):
        await world.prepare(service=service, actor=actor)
    assert world.domain_snapshot() == before


@pytest.mark.parametrize("scenario", ["logout", "idle", "absolute", "disabled", "revoked_member", "missing_member", "mfa_cleared", "mfa_revoked", "cached_mfa"])
async def test_captured_actor_cannot_survive_live_authority_changes(world, scenario):
    if scenario in ("idle", "absolute"):
        short = SessionService(world.factory, idle=timedelta(milliseconds=150),
                               absolute=timedelta(seconds=60) if scenario == "idle" else timedelta(milliseconds=150),
                               touch_interval=timedelta(milliseconds=10))
        issued = await short.create(world.iam.org_a, world.iam.user_a, mfa_verified=True)
        actor = (await short.authenticate(issued.token, touch=False)).session
        assert actor is not None
        await asyncio.sleep(0.2)
    else:
        actor = await world.actor(mfa=scenario != "cached_mfa")
    if scenario == "logout":
        world.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1")
    elif scenario in ("idle", "absolute"):
        pass  # Actual expiry above; immutable lifetime columns are untouched.
    elif scenario == "disabled":
        world.sql("UPDATE iam.users SET status='DISABLED',row_version=row_version+1 WHERE id=%s", actor.user_id)
    elif scenario == "revoked_member":
        world.sql("UPDATE organization.memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", actor.user_id)
    elif scenario == "missing_member":
        world.sql("DELETE FROM organization.memberships WHERE user_id=%s", actor.user_id)
    elif scenario == "mfa_cleared":
        world.sql("UPDATE iam.sessions SET mfa_verified_at=NULL,row_version=row_version+1")
    elif scenario == "mfa_revoked":
        world.sql("UPDATE iam.mfa_factors SET status='REVOKED',row_version=row_version+1")
    else:
        actor = replace(actor, mfa_verified_at=world.observation.observed_at, second_factor_pending=False)
    with pytest.raises(AdmissionDenied):
        await world.prepare(actor=actor)


@pytest.mark.parametrize("scenario", ["packaged", "deny", "approval", "outage", "garbage", "timeout"])
async def test_policy_failures_never_create_review_or_admission(world, scenario):
    class Policy:
        async def decide(self, request):
            if scenario == "outage":
                raise RuntimeError("private-provider-content")
            if scenario == "garbage":
                return True
            if scenario == "timeout":
                await asyncio.sleep(1)
            return PolicyDecision(effect=Effect.APPROVAL_REQUIRED if scenario == "approval" else Effect.DENY,
                                  reason_code="fixture_denied", policy_version=world.config.version)
    if scenario == "packaged":
        config = load_packaged_policy()
        policy = PolicyEnforcer(PolicyEngine(config, world.factory), world.factory, config, timeout_seconds=1)
    else:
        policy = PolicyEnforcer(Policy(), world.factory, world.config, timeout_seconds=0.02)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(service=world.service(policy=policy))
    assert "private-provider-content" not in str(caught.value)
    assert world.sql("SELECT count(*) FROM platform.model_admission_versions") == [(0,)]


@pytest.mark.parametrize("field", ["binding_sha256", "profile_sha256", "expectation_sha256", "observation_sha256", "policy_version"])
async def test_tampered_review_comparison_refuses(world, field):
    actor = await world.actor()
    review = await world.prepare(actor=actor)
    altered = replace(review, **{field: "0" * 64 if field != "policy_version" else "unknown"})
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=actor, previous=altered)
    assert caught.value.code == "STALE_REVIEW"


async def test_first_approval_lifecycle_invalidates_candidate_review(world):
    actor = await world.actor()
    review = await world.prepare(actor=actor)
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=actor, previous=review)
    assert caught.value.code == "STALE_REVIEW"


async def test_reapproval_review_binds_generation_block_and_pending_without_clearing_them(world):
    actor = await world.actor()
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    install_generation(world.iam.pg, world.expected)
    next_expected = replace(world.expected, admission_generation=2)
    review = await world.prepare(actor=actor, expected=next_expected)
    guard = ModelAdmissionGuard(world.factory)
    ticket = await guard.begin(world.profile_id, world.expected.managed_versions, request_ref="pending-owner-review")
    with pytest.raises(AdmissionDenied):
        await world.prepare(actor=actor, expected=next_expected, previous=review)
    pending_review = await world.prepare(actor=actor, expected=next_expected)
    before = world.domain_snapshot()
    assert await world.prepare(actor=actor, expected=next_expected, previous=pending_review) == pending_review
    assert world.domain_snapshot() == before
    with pytest.raises(AdmissionDenied):
        await guard.finalize(ticket, "{")
    with pytest.raises(AdmissionDenied):
        await world.prepare(actor=actor, expected=next_expected, previous=pending_review)
    install_generation(world.iam.pg, next_expected)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=actor, expected=next_expected)
    assert caught.value.code == "STALE_REVIEW_GENERATION"


async def test_audit_outage_returns_no_review(world):
    world.sql("CREATE FUNCTION audit.fixture_review_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture'; END $$")
    world.sql("CREATE TRIGGER fixture_review_failure BEFORE INSERT ON audit.audit_events FOR EACH ROW EXECUTE FUNCTION audit.fixture_review_failure()")
    before = world.domain_snapshot()
    with pytest.raises(AdmissionUnavailable):
        await world.prepare()
    assert world.domain_snapshot() == before


async def test_policy_wait_does_not_hold_transaction_and_revocation_is_revalidated(world):
    actor = await world.actor()
    original = PolicyEngine(world.config, world.factory)
    class RevokeDuringPolicy:
        async def decide(self, request):
            decision = await original.decide(request)
            # Would time out if a caller UoW still held membership SHARE locks.
            world.sql("UPDATE organization.memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", actor.user_id)
            return decision
    policy = PolicyEnforcer(RevokeDuringPolicy(), world.factory, world.config, timeout_seconds=2)
    with pytest.raises(AdmissionDenied):
        await world.prepare(actor=actor, service=world.service(policy=policy))


async def test_missing_lifecycle_fence_fails_closed(world):
    world.sql("ALTER TABLE platform.model_profiles DISABLE TRIGGER trg_model_profiles_lifecycle_fence")
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare()
    assert caught.value.code == "LIFECYCLE_FENCE_UNAVAILABLE"


async def test_replacement_session_and_changed_policy_invalidate_previous_review(world):
    actor = await world.actor()
    review = await world.prepare(actor=actor)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=await world.actor(), previous=review)
    assert caught.value.code == "STALE_REVIEW"
    config = replace(world.config, version="2026-11-18.140")
    policy = PolicyEnforcer(PolicyEngine(config, world.factory), world.factory, config, timeout_seconds=2)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=actor, service=world.service(policy=policy), previous=review)
    assert caught.value.code == "STALE_REVIEW"


async def test_active_subject_change_during_policy_wait_invalidates_decision(world):
    actor = await world.actor()
    original = PolicyEngine(world.config, world.factory)
    class ChangeDuringPolicy:
        async def decide(self, request):
            decision = await original.decide(request)
            world.sql("UPDATE organization.memberships SET row_version=row_version+1 WHERE user_id=%s", actor.user_id)
            return decision
    policy = PolicyEnforcer(ChangeDuringPolicy(), world.factory, world.config, timeout_seconds=2)
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare(actor=actor, service=world.service(policy=policy))
    assert caught.value.code == "OWNER_CHANGED"


async def test_expiry_while_waiting_for_profile_fence_does_not_return_review(world):
    # This lock is held by an independent real PG connection. Detect its waiter
    # before letting the short-lived session expire, rather than guessing order.
    sessions = SessionService(world.factory, idle=timedelta(seconds=1), absolute=timedelta(seconds=2), touch_interval=timedelta(milliseconds=10))
    issued = await sessions.create(world.iam.org_a, world.iam.user_a, mfa_verified=True)
    actor = (await sessions.authenticate(issued.token, touch=False)).session
    assert actor is not None
    with world.iam.pg.connect(autocommit=False) as owner:
        owner.execute("SELECT pg_advisory_xact_lock(hashtextextended('ai_res.model_profile_lifecycle:' || %s,0))", [str(world.profile_id)])
        task = asyncio.create_task(world.prepare(actor=actor))
        try:
            for _ in range(100):
                waiters = world.sql("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted")
                if waiters[0][0] > 0:
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("review never waited for lifecycle fence")
            await asyncio.sleep(1.05)
        finally:
            owner.rollback()
            result = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
    assert isinstance(result[0], AdmissionDenied)
    assert world.sql("SELECT count(*) FROM audit.audit_events WHERE result='SUCCEEDED'") == [(0,)]


async def test_factor_first_reset_does_not_deadlock_review_session(world):
    actor = await world.actor()
    pg = world.iam.pg
    reset = await psycopg.AsyncConnection.connect(host=pg.host, port=pg.port, dbname="ai_res_db", user="ai_res_api",
                                                password=pg.passwords["ai_res_api"], sslmode="disable", autocommit=False)
    task = None
    try:
        await reset.execute("SELECT set_config('app.organization_id',%s,true)", [str(actor.organization_id)])
        await reset.execute("SET LOCAL lock_timeout='1000ms'")
        await reset.execute("UPDATE iam.mfa_factors SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", [actor.user_id])
        task = asyncio.create_task(world.prepare(actor=actor))
        for _ in range(100):
            waiting = world.sql("SELECT count(*) FROM pg_stat_activity WHERE usename='ai_res_api' AND wait_event_type='Lock'")
            if waiting[0][0] > 0:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("review did not wait for reset factor")
        # Existing MFA reset/verify lock order is factor -> session. This UPDATE
        # must finish while review waits for the factor, without a session cycle.
        await reset.execute("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='MFA_RESET',row_version=row_version+1 WHERE id=%s", [actor.session_id])
        await reset.commit()
        result = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
        assert isinstance(result[0], AdmissionDenied)
    finally:
        await reset.rollback()
        await reset.close()
        if task is not None:
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)


async def test_full_profile_digest_preserves_numeric_precision_and_other_profile_is_independent(world):
    from decimal import Decimal
    actor = await world.actor()
    with world.iam.pg.connect() as c:
        pid = add_profile(c, key="numeric-review", provider="deepseek", provider_model_id="deepseek-flash", identity_mode="FLASH_OBSERVED",
                          pinned_model_version=None, cost_currency="USD", cost_input_per_million=Decimal("12345678901234.123456"),
                          cost_output_per_million=Decimal("12345678901234.123457"))
    world.scope = replace(world.scope, profile_id=pid)
    world.expected = expected_for(pid)
    world.observation = observed(world.expected)
    world.expected = replace(world.expected, evidence_sha256=evidence_hash(world.observation).hex())
    review = await world.prepare(actor=actor)
    raw = world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=%s", pid)[0][0]
    assert "12345678901234.123456" in raw and "12345678901234.123457" in raw
    # The full string is bound without decoding PostgreSQL numerics to float.
    assert review.profile_sha256 == hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with world.iam.pg.connect() as c:
        approve(c, world.profile_id)
    assert await world.prepare(actor=actor, previous=review) == review


@pytest.mark.parametrize("scenario", ["immutable", "retired", "deprecated", "wrong_version"])
async def test_unsupported_profile_state_refuses(world, scenario):
    if scenario == "immutable":
        with world.iam.pg.connect() as c:
            pid = add_profile(c, key="immutable-target")
        world.scope = replace(world.scope, profile_id=pid)
        world.expected = expected_for(pid)
        world.observation = observed(world.expected)
        world.expected = replace(world.expected, evidence_sha256=evidence_hash(world.observation).hex())
    elif scenario == "wrong_version":
        world.expected = replace(world.expected, managed_versions=replace(world.expected.managed_versions, profile_version=2))
        world.observation = replace(world.observation, managed_versions=world.expected.managed_versions)
        world.expected = replace(world.expected, evidence_sha256=evidence_hash(world.observation).hex())
    else:
        with world.iam.pg.connect() as c:
            approve(c, world.profile_id)
            c.execute("UPDATE platform.model_profiles SET status='DEPRECATED',deprecated_at=clock_timestamp() WHERE id=%s", [world.profile_id])
            if scenario == "retired":
                c.execute("UPDATE platform.model_profiles SET status='RETIRED' WHERE id=%s", [world.profile_id])
    with pytest.raises(AdmissionDenied) as caught:
        await world.prepare()
    assert caught.value.code == "REVIEW_TARGET_UNAVAILABLE"
