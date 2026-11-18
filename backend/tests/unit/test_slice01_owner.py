"""Offline owner composition with synthetic artifacts/services; no DB or approval."""
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from scripts.slice01 import owner
from scripts.slice01.common import canonical, digest, write_new

from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityExpectation,
    IdentityObservation,
    ManagedVersions,
    ObservedFingerprint,
    ObservedProviderIdentity,
)
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.model_registry.admission import evidence_hash
from ai_res.modules.model_registry.owner_review import OwnerReview
from ai_res.modules.model_registry.profile_approval import profile_snapshot_hash
from ai_res.platform.config import Settings
from ai_res.policy.config import PolicyConfigError

SCHEMA = Path(__file__).resolve().parents[3] / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json"


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    config, results = tmp_path / "config", tmp_path / "results"
    config.mkdir(mode=0o700)
    results.mkdir(mode=0o700)
    contract = tmp_path / "worker-contract.json"
    contract.write_bytes(SCHEMA.read_bytes())
    contract.chmod(0o600)
    policy = {"schemaVersion": 1, "version": "2026-11-18.143", "status": "WORKING",
              "privilegedRoles": ["ORGANIZATION_OWNER"], "actions": {
                  "model_admission.review": {"resourceType": "MODEL_ADMISSION_REVIEW",
                      "allow": {"orgRoles": ["ORGANIZATION_OWNER"]}, "requiresMfa": True, "humanOnly": True}}}
    write_new(config / "policy.json", policy)
    text = "The service shall list articles.\n"
    plan = {"mode": "live", "profileId": str(owner.PROFILE_ID), "profileVersion": 1,
            "librarySha256": "b" * 64, "workerContractSha256": digest(contract.read_bytes()),
            "policySha256": digest((config / "policy.json").read_bytes()), "profileSnapshot": '{"status":"CANDIDATE"}',
            "source": {"sourceId": str(uuid4()), "versionId": str(uuid4()), "checksum": digest(text.encode()),
                       "text": text, "license": "MIT", "provenance": {"sourceSha256": digest(text.encode())}},
            "phases": {"bootstrap": "synthetic-probe"}, "toolHashes": {"owner.py": "f" * 64},
            "scriptsInitializerSha256": "e" * 64, "bifrostImage": "sha256:" + "a" * 64,
            "nativeInputs": {"/synthetic/config.json": "d" * 64}}
    versions = ManagedVersions("a" * 40, owner.PROFILE_ID, 1, digest(canonical(plan)), "c" * 64, None)
    plan["managedVersions"] = versions.to_dict()
    plan["manifestSha256"] = digest(canonical(plan))
    identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "deepseek-flash",
                                       ObservedFingerprint(FingerprintPresence.VALUE, "synthetic-fingerprint"))
    observed = IdentityObservation(versions, identity, datetime.now(UTC), "synthetic-probe", "synthetic-provider")
    expected = IdentityExpectation(versions, identity, 1, evidence_hash(observed).hex())
    write_new(results / "expectation.json", expected.to_dict())
    write_new(results / "observation.json", observed.to_dict())
    evidence = {"command": "synthetic fixture only", "result": "isolated", "limitations": ["No actual runtime evidence."],
                "status": "LOCAL_CHECKS_PASSED", **{key: copy.deepcopy(plan[key]) for key in (
                    "toolHashes", "scriptsInitializerSha256", "bifrostImage", "nativeInputs", "librarySha256", "workerContractSha256")}}
    acceptance = {"version": "slice01-acceptance/1", "manifestSha256": plan["manifestSha256"],
                  "profileId": str(owner.PROFILE_ID), "profileSha256": profile_snapshot_hash(plan["profileSnapshot"]),
                  "expectationSha256": evidence_hash(expected).hex(), "observationSha256": evidence_hash(observed).hex(),
                  "nativeEvidenceSha256": digest(canonical(evidence)), "evidence": evidence}
    write_new(results / "acceptance.json", acceptance)
    monkeypatch.setattr(owner, "PLAN", config)
    monkeypatch.setattr(owner, "RESULTS", results)
    monkeypatch.setattr(owner, "CONTRACT", contract)
    monkeypatch.setattr(owner, "load_plan", lambda directory: copy.deepcopy(plan))
    monkeypatch.setattr(owner, "library_sha256", lambda: "b" * 64)
    return SimpleNamespace(plan=plan, results=results, acceptance=acceptance, expected=expected, observed=observed)


def review_for(inputs):
    return OwnerReview("d" * 64, inputs.profile_sha256, inputs.expectation_sha256,
                       inputs.observation_sha256, inputs.policy.version)


def rewrite(path, value):
    path.unlink()
    write_new(path, value)


def test_validated_inputs_and_explicit_decision_bind_bytes_actions_and_scope(prepared):
    inputs = owner.load_inputs()
    artifact = owner.decision_artifact(inputs, review_for(inputs))
    assert artifact["actions"] == ["ACCEPT_IDENTITY", "APPROVE_PROFILE_AND_ACCEPT_BIFROST"]
    assert artifact["acceptanceSha256"] == digest((prepared.results / "acceptance.json").read_bytes())
    write_new(prepared.results / f"decision-{artifact['decisionId']}.json", artifact)
    assert owner.load_decision(inputs, UUID(artifact["decisionId"]))[0] == artifact
    assert "synthetic fixture" not in repr(inputs)


@pytest.mark.parametrize("field", ["version", "manifestSha256", "profileId", "profileSha256", "expectationSha256",
                                   "observationSha256", "nativeEvidenceSha256", "evidence", "extra"])
def test_changed_acceptance_refuses_before_any_service(prepared, field):
    artifact = copy.deepcopy(prepared.acceptance)
    artifact[field] = {} if field == "evidence" else "changed"
    rewrite(prepared.results / "acceptance.json", artifact)
    with pytest.raises(ValueError):
        owner.load_inputs()


@pytest.mark.parametrize("field", ["status", "toolHashes", "scriptsInitializerSha256", "bifrostImage", "nativeInputs",
                                   "librarySha256", "workerContractSha256"])
def test_native_evidence_must_match_exact_frozen_runtime_and_contract(prepared, field):
    artifact = copy.deepcopy(prepared.acceptance)
    artifact["evidence"][field] = "wrong"
    artifact["nativeEvidenceSha256"] = digest(canonical(artifact["evidence"]))
    rewrite(prepared.results / "acceptance.json", artifact)
    with pytest.raises(ValueError, match="NATIVE_EVIDENCE_CHANGED"):
        owner.load_inputs()


@pytest.mark.parametrize("changed", ["library", "schema", "source", "policy", "versions", "request"])
def test_frozen_source_library_schema_policy_and_observation_bindings(prepared, monkeypatch, changed):
    if changed == "library":
        monkeypatch.setattr(owner, "library_sha256", lambda: "f" * 64)
    elif changed == "schema":
        owner.CONTRACT.write_bytes(b"{}")
    elif changed == "source":
        prepared.plan["source"]["text"] += "Changed after checksum."
    elif changed == "policy":
        (owner.PLAN / "policy.json").write_bytes(b"{}")
    elif changed == "versions":
        prepared.plan["managedVersions"]["profileId"] = str(uuid4())
    else:
        prepared.plan["phases"]["bootstrap"] = "other-probe"
    with pytest.raises((ValueError, PolicyConfigError)):
        owner.load_inputs()


@pytest.mark.parametrize("changed", ["confirmation", "actions", "owner", "profile", "bytes", "review", "duplicate-id", "extra"])
def test_decision_confirmation_scope_review_and_frozen_hashes_are_exact(prepared, changed):
    inputs = owner.load_inputs()
    artifact = owner.decision_artifact(inputs, review_for(inputs))
    confirmation = UUID(artifact["decisionId"])
    if changed == "confirmation":
        confirmation = uuid4()
    elif changed == "actions":
        artifact["actions"] = ["ACCEPT_IDENTITY"]
    elif changed == "owner":
        artifact["ownerId"] = str(uuid4())
    elif changed == "profile":
        artifact["profileId"] = str(uuid4())
    elif changed == "bytes":
        artifact["artifactSha256"]["acceptance.json"] = "e" * 64
    elif changed == "review":
        artifact["review"]["profile_sha256"] = "e" * 64
    elif changed == "duplicate-id":
        artifact["identityDecisionId"] = artifact["decisionId"]
    else:
        artifact["approved"] = True
    write_new(prepared.results / f"decision-{confirmation}.json", artifact)
    with pytest.raises(ValueError):
        owner.load_decision(inputs, confirmation)


@pytest.fixture
def services(prepared, monkeypatch):
    inputs = owner.load_inputs()
    events = []
    now = datetime.now(UTC)
    actor = AuthenticatedSession(uuid4(), owner.ORGANIZATION_ID, owner.OWNER_ID, now,
                                 now + timedelta(hours=1), now + timedelta(hours=2), "synthetic-csrf", b"synthetic-digest")
    settings = Settings(db_host="postgres", db_user="ai_res_api", db_password_file=Path("/run/secrets/api_db_password"),
                        db_sslrootcert_file=Path("/run/secrets/postgres_tls_ca_cert"))
    state = SimpleNamespace(inputs=inputs, events=events, actor=actor, identity_error=False, profile_error=False, settings=settings)

    class Engine:
        def __init__(self, label):
            self.label, self.sync_engine = label, object()

        async def dispose(self):
            events.append(("dispose", self.label))

    def engine(config):
        events.append(("engine", config.db_user, config.db_sslmode, config.db_password_file))
        return Engine(config.db_user)

    class Sessions:
        def __init__(self, *args, **kwargs):
            pass

        async def authenticate(self, token, *, touch):
            assert token == "fixture" and touch is False
            events.append(("authenticate",))
            return SimpleNamespace(session=state.actor)

    class Review:
        def __init__(self, *args, **kwargs):
            pass

        async def prepare(self, actor, **kwargs):
            assert actor is state.actor
            events.append(("review",))
            return review_for(inputs)

    class Identity:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, actor, command, **kwargs):
            events.append(("identity", command))
            if state.identity_error:
                raise RuntimeError("synthetic-private-session must never appear")
            return SimpleNamespace(generation=1)

    class Profile:
        def __init__(self, *args, **kwargs):
            assert kwargs["owner_login"] == "ai_res_migrator"

        async def execute(self, actor, command, **kwargs):
            events.append(("profile", command))
            assert kwargs["bifrost_acceptance"] == inputs.acceptance
            if state.profile_error:
                raise RuntimeError("synthetic-private-session must never appear")
            return SimpleNamespace(profile_version=1)

    session = prepared.results / "owner-session.json"
    write_new(session, {"sessionToken": "fixture"})
    monkeypatch.setattr(owner, "SESSION", session)
    monkeypatch.setattr(owner, "load_settings", lambda env: state.settings)
    monkeypatch.setattr(owner, "create_runtime_engine", engine)
    monkeypatch.setattr(owner, "create_session_factory", lambda engine: engine.label)
    monkeypatch.setattr(owner, "SessionService", Sessions)
    monkeypatch.setattr(owner, "PolicyEngine", lambda *args: None)
    monkeypatch.setattr(owner, "PolicyEnforcer", lambda *args, **kwargs: None)
    monkeypatch.setattr(owner, "OwnerReviewService", Review)
    monkeypatch.setattr(owner, "IdentityAdmissionOperator", Identity)
    monkeypatch.setattr(owner, "ProfileApprovalService", Profile)
    monkeypatch.setattr(owner.event, "listen", lambda engine, event, callback: events.append(("hook", event, callback)))
    return state


async def test_prepare_is_api_only_and_does_not_execute_either_decision(services, prepared):
    result = await owner.execute("prepare-decision")
    assert result["status"] == "OWNER_DECISION_PREPARED_NOT_APPROVED"
    assert [e[0] for e in services.events] == ["engine", "authenticate", "review", "dispose"]
    assert services.events[0][1] == "ai_res_api"
    assert result["decisionFile"] == f"decision-{result['decisionId']}.json"
    assert result["decisionSha256"] == digest((prepared.results / result["decisionFile"]).read_bytes())


async def test_new_preparation_preserves_previous_immutable_decision(services, prepared):
    first = await owner.execute("prepare-decision")
    original = (prepared.results / first["decisionFile"]).read_bytes()
    services.actor = replace(services.actor, session_id=uuid4())
    second = await owner.execute("prepare-decision")
    assert first["decisionId"] != second["decisionId"] and first["decisionFile"] != second["decisionFile"]
    assert (prepared.results / first["decisionFile"]).read_bytes() == original
    assert (prepared.results / second["decisionFile"]).is_file()
    assert not (prepared.results / "decision.json").exists()
    assert not any(event[0] in {"identity", "profile"} for event in services.events)


async def test_approved_profile_requires_explicit_identity_only_action_and_skips_profile_service(services, prepared, monkeypatch):
    inputs = replace(services.inputs, plan={**services.inputs.plan, "profileStatus": "APPROVED",
                                           "admissionGeneration": 2, "experimentVersion": "2"})
    monkeypatch.setattr(owner, "load_inputs", lambda: inputs)
    artifact = owner.decision_artifact(inputs, review_for(inputs))
    assert artifact["actions"] == ["ACCEPT_IDENTITY"]
    write_new(prepared.results / f"decision-{artifact['decisionId']}.json", artifact)
    with pytest.raises(ValueError, match="OWNER_ACTION_SCOPE_MISMATCH"):
        await owner.execute("approve", UUID(artifact["decisionId"]))
    assert not services.events
    result = await owner.execute("accept-identity", UUID(artifact["decisionId"]))
    assert result["status"] == "IDENTITY_ACCEPTED_PROFILE_APPROVAL_UNCHANGED"
    assert not any(event[0] == "profile" for event in services.events)
    assert (prepared.results / f"identity-receipt-{artifact['decisionId']}.json").is_file()
    assert not (prepared.results / f"approval-receipt-{artifact['decisionId']}.json").exists()


async def test_candidate_does_not_accept_identity_only_action(services):
    with pytest.raises(ValueError, match="OWNER_ACTION_SCOPE_MISMATCH"):
        await owner.execute("accept-identity", uuid4())
    assert not services.events


@pytest.mark.parametrize("version", ["2", "3", "1000"])
def test_later_explicit_versions_bind_current_generation_without_profile_reapproval(version):
    plan = {"profileStatus": "APPROVED", "admissionGeneration": 3, "experimentVersion": version}
    assert owner.target(plan) == ("APPROVED", 3)
    assert owner.decision_actions(plan) == ["ACCEPT_IDENTITY"]


@pytest.mark.parametrize("version", ["0", "01", "1001", "../../escape", True, 2])
def test_invalid_experiment_versions_fail_closed(version):
    with pytest.raises(ValueError, match="OWNER_TARGET_INVALID"):
        owner.target({"profileStatus": "APPROVED", "admissionGeneration": 2, "experimentVersion": version})


def test_decision_filename_requires_typed_uuid_before_any_path_access(prepared):
    with pytest.raises(ValueError, match="EXPLICIT_OWNER_CONFIRMATION_REQUIRED"):
        owner.load_decision(owner.load_inputs(), "../arbitrary-file")


async def test_confirmed_approval_authenticates_before_migrator_and_runs_both_explicit_actions(services, prepared):
    artifact = owner.decision_artifact(services.inputs, review_for(services.inputs))
    write_new(prepared.results / f"decision-{artifact['decisionId']}.json", artifact)
    result = await owner.execute("approve", UUID(artifact["decisionId"]))
    assert result["status"] == "IDENTITY_AND_PROFILE_APPROVED"
    kinds = [e[0] for e in services.events]
    assert kinds == ["engine", "authenticate", "engine", "hook", "identity", "profile", "dispose", "dispose"]
    assert services.events[2][1:3] == ("ai_res_migrator", "verify-full")
    identity, profile = services.events[4][1], services.events[5][1]
    assert identity.decision_id == UUID(artifact["identityDecisionId"])
    assert profile.decision_id == UUID(artifact["decisionId"]) and identity.decision_id != profile.decision_id
    assert identity.correlation_id == profile.correlation_id == UUID(artifact["correlationId"])
    assert identity.action.value == "ACCEPT_IDENTITY" and profile.action.value == "APPROVE_PROFILE_AND_ACCEPT_BIFROST"
    assert (prepared.results / f"identity-receipt-{artifact['decisionId']}.json").exists()
    assert (prepared.results / f"approval-receipt-{artifact['decisionId']}.json").exists()
    # Exact replay is safe; product services independently handle their DB replay.
    assert await owner.execute("approve", UUID(artifact["decisionId"])) == result


@pytest.mark.parametrize("phase", ["identity", "profile"])
async def test_partial_success_and_unknown_identity_are_not_reported_as_rollback_or_approval(services, prepared, phase):
    artifact = owner.decision_artifact(services.inputs, review_for(services.inputs))
    write_new(prepared.results / f"decision-{artifact['decisionId']}.json", artifact)
    setattr(services, phase + "_error", True)
    with pytest.raises(owner.OwnerUnconfirmed) as caught:
        await owner.execute("approve", UUID(artifact["decisionId"]))
    assert caught.value.status == ("IDENTITY_ACCEPTED_PROFILE_NOT_CONFIRMED" if phase == "profile" else "IDENTITY_OUTCOME_UNCONFIRMED")
    assert "synthetic-private-session" not in str(caught.value)
    assert (prepared.results / f"identity-receipt-{artifact['decisionId']}.json").exists() == (phase == "profile")
    assert not (prepared.results / f"approval-receipt-{artifact['decisionId']}.json").exists()


@pytest.mark.parametrize("case", ["no-confirmation", "wrong-confirmation", "no-mfa", "pending", "foreign-owner", "api-role", "tls"])
async def test_no_migrator_or_decisions_before_exact_confirmation_and_live_api_auth(services, prepared, case):
    artifact = owner.decision_artifact(services.inputs, review_for(services.inputs))
    write_new(prepared.results / f"decision-{artifact['decisionId']}.json", artifact)
    confirmation = UUID(artifact["decisionId"])
    if case == "no-confirmation":
        confirmation = None
    elif case == "wrong-confirmation":
        confirmation = uuid4()
    elif case == "no-mfa":
        services.actor = replace(services.actor, mfa_verified_at=None)
    elif case == "pending":
        services.actor = replace(services.actor, second_factor_pending=True)
    elif case == "foreign-owner":
        services.actor = replace(services.actor, user_id=uuid4())
    else:
        services.settings = services.settings.model_copy(update={"db_user": "ai_res_migrator"} if case == "api-role" else {"db_sslmode": "disable"})
    with pytest.raises((ValueError, FileNotFoundError, owner.OwnerUnconfirmed)):
        await owner.execute("approve", confirmation)
    assert not any(e[0] in {"hook", "identity", "profile"} or e[:2] == ("engine", "ai_res_migrator") for e in services.events)


def test_owner_role_hook_uses_only_fixed_transaction_local_sql():
    calls = []
    owner.owner_transaction(SimpleNamespace(execute=lambda statement: calls.append(str(statement))))
    assert calls == ["SET LOCAL ROLE ai_res_owner", "SELECT set_config('app.migration_mode','on',true)"]


def test_cli_argument_errors_never_echo_input_or_tokens(capsys):
    assert owner.main(["approve", "--confirm-decision", "synthetic-private-session"]) == 2
    output = capsys.readouterr()
    assert "synthetic-private-session" not in output.out + output.err
    assert "OWNER_OPERATION_REFUSED" in output.err
