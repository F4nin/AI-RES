"""Actual disposable PostgreSQL owner orchestration, never the development DB.

Session authentication, synthetic active MFA, policy, services, SQL, role changes,
audit and replay are real. Existing Testcontainer fixtures use plaintext TCP: an
explicit engine adapter changes only sslmode for that server. These tests do not
prove TLS. Trusted frozen plan loading is isolated from the orchestration scope.
"""
import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from scripts.slice01 import owner
from scripts.slice01.common import canonical, decode, digest, write_new
from sqlalchemy import event

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.llm.observed_identity import IdentityObservation
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.admission import evidence_hash
from ai_res.modules.model_registry.profile_approval import profile_snapshot_hash
from ai_res.platform.config import Settings

from .test_model_admission import expected_for
from .test_model_owner_review import ReviewWorld
from .test_model_registry import add_profile

pytestmark = pytest.mark.postgres
SCHEMA = Path(__file__).resolve().parents[4] / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json"


class SliceWorld(ReviewWorld):
    """Reuse ReviewWorld SQL helpers with one valid no-retry Flash candidate."""
    def __init__(self, iam):
        self.iam = iam
        self.factory = create_session_factory(iam.engine())
        self.sessions = SessionService(self.factory, idle=timedelta(minutes=30), absolute=timedelta(hours=12),
                                       touch_interval=timedelta(minutes=1))
        with iam.pg.connect() as connection:
            connection.execute("UPDATE organization.memberships SET role_code='ORGANIZATION_OWNER',row_version=row_version+1")
            connection.execute(
                "INSERT INTO iam.mfa_factors(id,organization_id,user_id,factor_type,status,secret_ciphertext,confirmed_at) "
                "VALUES(%s,%s,%s,'TOTP','ACTIVE',decode(repeat('ab',40),'hex'),clock_timestamp())",
                [uuid4(), iam.org_a, iam.user_a])
            self.profile_id = add_profile(connection, key="slice-owner-fixture", provider="deepseek", provider_model_id="deepseek-flash",
                identity_mode="FLASH_OBSERVED", pinned_model_version=None, capabilities=["CHAT"], retry_class="NONE")
            connection.execute("INSERT INTO platform.model_admission_operators(database_login,organization_id,user_id,profile_id) "
                               "VALUES('ai_res_migrator',%s,%s,%s)", [iam.org_a, iam.user_a, self.profile_id])


@pytest.fixture
async def composed(iam_world, tmp_path, monkeypatch):
    world = SliceWorld(iam_world)
    issued = await world.sessions.create(iam_world.org_a, iam_world.user_a, mfa_verified=True)
    settings_files = {}
    for role in ("ai_res_api", "ai_res_migrator"):
        path = tmp_path / (role + "_password")
        path.write_text(iam_world.pg.passwords[role])
        path.chmod(0o600)
        settings_files[role] = path
    config, results = tmp_path / "slice-config", tmp_path / "slice-results"
    config.mkdir(mode=0o700)
    results.mkdir(mode=0o700)
    contract = tmp_path / "worker-contract.json"
    contract.write_bytes(SCHEMA.read_bytes())
    contract.chmod(0o600)
    policy = json.loads(resources.files("ai_res.policy").joinpath("policy_config.json").read_text())
    policy["version"] = "2026-11-18.143"
    for action, resource in (("model_admission.review", "MODEL_ADMISSION_REVIEW"),
                             ("model_admission.accept_identity", "MODEL_ADMISSION_DECISION"),
                             ("model_profile.approve", "MODEL_PROFILE_APPROVAL")):
        policy["actions"][action] = {"resourceType": resource, "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
                                      "requiresMfa": True, "humanOnly": True, "auditAllow": True}
    write_new(config / "policy.json", policy)
    source = "The service shall list published articles.\n"
    snapshot = world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=%s", world.profile_id)[0][0]
    plan = {"mode": "live", "profileId": str(world.profile_id), "profileVersion": 1,
            "librarySha256": owner.library_sha256(), "workerContractSha256": digest(contract.read_bytes()),
            "policySha256": digest((config / "policy.json").read_bytes()), "profileSnapshot": snapshot,
            "source": {"sourceId": str(uuid4()), "versionId": str(uuid4()), "checksum": digest(source.encode()),
                       "text": source, "license": "MIT", "provenance": {"sourceSha256": digest(source.encode())}},
            "phases": {"bootstrap": "slice-owner-synthetic-probe"}, "toolHashes": {"owner.py": digest(Path(owner.__file__).read_bytes())},
            "scriptsInitializerSha256": "e" * 64, "bifrostImage": "sha256:" + "a" * 64,
            "nativeInputs": {"/synthetic/config.json": "d" * 64}}
    expected = expected_for(world.profile_id)
    versions = replace(expected.managed_versions, config_sha256=digest(canonical(plan)))
    observation = IdentityObservation(versions, expected.identity, issued.mfa_verified_at,
                                      plan["phases"]["bootstrap"], "slice-owner-synthetic-provider")
    expected = replace(expected, managed_versions=versions, evidence_sha256=evidence_hash(observation).hex())
    plan["managedVersions"] = versions.to_dict()
    plan["manifestSha256"] = digest(canonical(plan))
    write_new(results / "observation.json", observation.to_dict())
    write_new(results / "expectation.json", expected.to_dict())
    native = {"status": "LOCAL_CHECKS_PASSED", "commands": ["isolated PostgreSQL fixture setup"],
              "limitations": ["Synthetic metadata; no Bifrost or provider execution, no TLS evidence."],
              **{key: copy.deepcopy(plan[key]) for key in ("toolHashes", "scriptsInitializerSha256", "bifrostImage",
                                                          "nativeInputs", "librarySha256", "workerContractSha256")}}
    acceptance = {"version": "slice01-acceptance/1", "manifestSha256": plan["manifestSha256"], "profileId": str(world.profile_id),
                  "profileSha256": profile_snapshot_hash(snapshot), "expectationSha256": evidence_hash(expected).hex(),
                  "observationSha256": evidence_hash(observation).hex(), "nativeEvidenceSha256": digest(canonical(native)), "evidence": native}
    write_new(results / "acceptance.json", acceptance)
    session = tmp_path / "owner-session.json"
    write_new(session, {"sessionToken": issued.token})
    settings = Settings(environment="test", db_host=iam_world.pg.host, db_port=iam_world.pg.port,
        db_user="ai_res_api", db_password_file=settings_files["ai_res_api"], db_sslmode="verify-full",
        db_sslrootcert_file=tmp_path / "unused-fixture-ca", policy_timeout_seconds=2)
    engines, statements, owner_roles = [], [], []

    def real_fixture_engine(config):
        assert config.db_sslmode == "verify-full"  # Owner's strict input check is unchanged.
        assert config.db_host == iam_world.pg.host and config.db_port == iam_world.pg.port
        engine = create_runtime_engine(config.model_copy(update={"db_sslmode": "disable", "db_sslrootcert_file": None}))
        engines.append((config.db_user, engine))

        @event.listens_for(engine.sync_engine, "after_cursor_execute")
        def capture(connection, cursor, statement, parameters, context, executemany):
            # Collect fixed SQL only. Parameters can contain session digests and
            # are deliberately excluded from evidence and assertion messages.
            statements.append((config.db_user, statement))
            if statement == "SELECT set_config('app.migration_mode','on',true)":
                row = connection.exec_driver_sql(
                    "SELECT session_user,current_user,current_setting('app.migration_mode',true)").one()
                owner_roles.append(tuple(row))

        return engine

    for name, value in {"PLAN": config, "RESULTS": results, "CONTRACT": contract, "SESSION": session,
                        "MIGRATOR_PASSWORD": settings_files["ai_res_migrator"], "PROFILE_ID": world.profile_id,
                        "ORGANIZATION_ID": iam_world.org_a, "OWNER_ID": iam_world.user_a}.items():
        monkeypatch.setattr(owner, name, value)
    monkeypatch.setattr(owner, "load_plan", lambda directory: copy.deepcopy(plan))
    monkeypatch.setattr(owner, "load_settings", lambda env: settings)
    monkeypatch.setattr(owner, "create_runtime_engine", real_fixture_engine)
    yield SimpleNamespace(world=world, issued=issued, results=results, engines=engines, statements=statements,
                          owner_roles=owner_roles, acceptance=acceptance, plan=plan)
    for _, engine in engines:
        await engine.dispose()


def state(world):
    return {"profile": world.sql("SELECT status,approved_by FROM platform.model_profiles WHERE id=%s", world.profile_id),
            "identity": world.sql("SELECT decision_id,generation,database_login FROM platform.model_admission_decisions"),
            "approval": world.sql("SELECT id,actor_id,object_id,details FROM audit.audit_events WHERE action='MODEL_PROFILE_APPROVED'")}


async def test_real_owner_orchestration_approves_audits_and_replays_once(composed):
    case, world = composed, composed.world
    prepared = await owner.execute("prepare-decision")
    assert prepared["status"] == "OWNER_DECISION_PREPARED_NOT_APPROVED"
    assert [role for role, _ in case.engines] == ["ai_res_api"]
    assert state(world) == {"profile": [("CANDIDATE", None)], "identity": [], "approval": []}
    decision = decode((case.results / prepared["decisionFile"]).read_bytes())
    result = await owner.execute("approve", UUID(prepared["decisionId"]))
    assert result["status"] == "IDENTITY_AND_PROFILE_APPROVED"
    actual = state(world)
    assert actual["profile"] == [("APPROVED", world.iam.user_a)]
    assert actual["identity"] == [(UUID(decision["identityDecisionId"]), 1, "ai_res_migrator")]
    assert actual["approval"][0][:3] == (UUID(decision["decisionId"]), world.iam.user_a, world.profile_id)
    assert actual["approval"][0][3]["bifrostAcceptanceSha256"] == digest((case.results / "acceptance.json").read_bytes())
    assert actual["approval"][0][3]["databaseLogin"] == "ai_res_migrator"
    assert case.owner_roles and set(case.owner_roles) == {("ai_res_migrator", "ai_res_owner", "on")}
    assert not any(role == "ai_res_api" and "SET LOCAL ROLE" in statement for role, statement in case.statements)
    # Both services must return their committed receipts after new connections.
    assert await owner.execute("approve", UUID(prepared["decisionId"])) == result
    assert state(world) == actual
    with world.iam.pg.connect("ai_res_migrator") as connection:
        assert connection.execute("SELECT session_user,current_user").fetchone() == ("ai_res_migrator", "ai_res_migrator")
        assert connection.execute("SELECT coalesce(current_setting('app.migration_mode',true),'')").fetchone()[0] != "on"


async def test_real_revoked_session_cannot_open_migrator_or_approve(composed):
    case, world = composed, composed.world
    prepared = await owner.execute("prepare-decision")
    world.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1 WHERE id=%s",
              case.issued.session_id)
    case.engines.clear()
    with pytest.raises(owner.OwnerUnconfirmed, match="IDENTITY_OUTCOME_UNCONFIRMED"):
        await owner.execute("approve", UUID(prepared["decisionId"]))
    assert [role for role, _ in case.engines] == ["ai_res_api"]
    assert state(world) == {"profile": [("CANDIDATE", None)], "identity": [], "approval": []}


async def test_fresh_mfa_session_can_prepare_new_immutable_decision_but_cannot_use_old_review(composed):
    case, world = composed, composed.world
    first = await owner.execute("prepare-decision")
    original = (case.results / first["decisionFile"]).read_bytes()
    world.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1 WHERE id=%s",
              case.issued.session_id)
    fresh = await world.sessions.create(world.iam.org_a, world.iam.user_a, mfa_verified=True)
    owner.SESSION.unlink()
    write_new(owner.SESSION, {"sessionToken": fresh.token})
    second = await owner.execute("prepare-decision")
    assert first["decisionId"] != second["decisionId"]
    assert (case.results / first["decisionFile"]).read_bytes() == original
    assert (case.results / second["decisionFile"]).is_file()
    assert not (case.results / "decision.json").exists()
    # A fresh live MFA session is authenticated, but the old review is bound to
    # the previous exact session. Real operator revalidation must reject it.
    with pytest.raises(owner.OwnerUnconfirmed, match="IDENTITY_OUTCOME_UNCONFIRMED"):
        await owner.execute("approve", UUID(first["decisionId"]))
    assert state(world) == {"profile": [("CANDIDATE", None)], "identity": [], "approval": []}
    assert not (case.results / f"identity-receipt-{first['decisionId']}.json").exists()
    result = await owner.execute("approve", UUID(second["decisionId"]))
    assert result["status"] == "IDENTITY_AND_PROFILE_APPROVED"
    assert (case.results / f"identity-receipt-{second['decisionId']}.json").is_file()
    assert (case.results / f"approval-receipt-{second['decisionId']}.json").is_file()
    assert len(state(world)["identity"]) == 1 and len(state(world)["approval"]) == 1


async def test_real_approved_profile_accepts_new_identity_generation_without_reapproval(composed, monkeypatch):
    case, world = composed, composed.world
    initial = await owner.execute("prepare-decision")
    await owner.execute("approve", UUID(initial["decisionId"]))
    profile_before = world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=%s", world.profile_id)[0][0]
    approval_before = state(world)["approval"]
    plan = case.plan
    plan.update({"profileStatus": "APPROVED", "admissionGeneration": 2, "experimentVersion": "2", "profileSnapshot": profile_before})
    plan["phases"]["bootstrap"] = "slice-owner-synthetic-reapproval-probe"
    expected = expected_for(world.profile_id, generation=2)
    versions = replace(expected.managed_versions,
        config_sha256=digest(canonical({key: value for key, value in plan.items() if key not in {"manifestSha256", "managedVersions"}})))
    observed = IdentityObservation(versions, expected.identity, datetime.now(UTC), plan["phases"]["bootstrap"], "synthetic-provider-v2")
    expected = replace(expected, managed_versions=versions, evidence_sha256=evidence_hash(observed).hex())
    plan["managedVersions"] = versions.to_dict()
    plan["manifestSha256"] = digest(canonical({key: value for key, value in plan.items() if key != "manifestSha256"}))
    # A new experiment has separate immutable files; v1 review material remains.
    results = case.results.parent / "slice-results-v2"
    results.mkdir(mode=0o700)
    write_new(results / "expectation.json", expected.to_dict())
    write_new(results / "observation.json", observed.to_dict())
    acceptance = copy.deepcopy(case.acceptance)
    acceptance.update({"manifestSha256": plan["manifestSha256"], "profileSha256": profile_snapshot_hash(profile_before),
                       "expectationSha256": evidence_hash(expected).hex(), "observationSha256": evidence_hash(observed).hex()})
    write_new(results / "acceptance.json", acceptance)
    monkeypatch.setattr(owner, "RESULTS", results)
    prepared = await owner.execute("prepare-decision")
    assert prepared["approvalAction"] == "accept-identity"
    decision = decode((results / prepared["decisionFile"]).read_bytes())
    assert decision["actions"] == ["ACCEPT_IDENTITY"]
    with pytest.raises(ValueError, match="OWNER_ACTION_SCOPE_MISMATCH"):
        await owner.execute("approve", UUID(prepared["decisionId"]))
    result = await owner.execute("accept-identity", UUID(prepared["decisionId"]))
    assert result["status"] == "IDENTITY_ACCEPTED_PROFILE_APPROVAL_UNCHANGED" and result["generation"] == 2
    assert await owner.execute("accept-identity", UUID(prepared["decisionId"])) == result
    assert world.sql("SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=%s", world.profile_id)[0][0] == profile_before
    assert state(world)["approval"] == approval_before
    assert sorted(row[1] for row in state(world)["identity"]) == [1, 2]
    assert world.sql("SELECT current_generation,blocked FROM platform.model_admission_controls WHERE profile_id=%s", world.profile_id) == [(2, False)]
    assert (results / f"identity-receipt-{prepared['decisionId']}.json").is_file()
    assert not (results / f"approval-receipt-{prepared['decisionId']}.json").exists()


@pytest.mark.parametrize("field", ["bifrostImage", "workerContractSha256"])
async def test_wrong_native_proof_refuses_before_any_database_engine(composed, field):
    case, world = composed, composed.world
    prepared = await owner.execute("prepare-decision")
    artifact = copy.deepcopy(case.acceptance)
    artifact["evidence"][field] = "wrong-frozen-input"
    artifact["nativeEvidenceSha256"] = digest(canonical(artifact["evidence"]))
    (case.results / "acceptance.json").unlink()
    write_new(case.results / "acceptance.json", artifact)
    case.engines.clear()
    with pytest.raises(ValueError, match="NATIVE_EVIDENCE_CHANGED"):
        await owner.execute("approve", UUID(prepared["decisionId"]))
    assert not case.engines and not case.owner_roles
    assert state(world) == {"profile": [("CANDIDATE", None)], "identity": [], "approval": []}
