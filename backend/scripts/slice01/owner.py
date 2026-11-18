"""Offline, explicitly confirmed SLICE owner decisions using existing services.

No model calls, grants, bindings, sessions or acceptance claims are created here.
prepare-decision only prepares review material; approve requires its exact UUID.
The migrator credential is confined to approve, separate from API authentication.
"""
import argparse
import asyncio
import importlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import Connection, event, text

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.llm.observed_identity import ManagedVersions
from ai_res.modules.iam.sessions import AuthenticatedSession, SessionService
from ai_res.modules.model_registry.admission import evidence_hash
from ai_res.modules.model_registry.identity_operator import IdentityAdmissionOperator, IdentityDecision, IdentityDecisionAction
from ai_res.modules.model_registry.owner_review import OwnerReview, OwnerReviewScope, OwnerReviewService, review_evidence
from ai_res.modules.model_registry.profile_approval import (
    ProfileApprovalAction,
    ProfileApprovalDecision,
    ProfileApprovalService,
    profile_snapshot_hash,
)
from ai_res.platform.config import load_settings
from ai_res.policy.config import PolicyConfig, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine
from ai_res.worker_contracts import WorkerContracts

from .common import (
    ORGANIZATION_ID,
    OWNER_ID,
    PROFILE_ID,
    SliceRefused,
    canonical,
    decode,
    digest,
    load_plan,
    read_owned,
    source_from_plan,
    write_new,
)

PLAN = Path("/config")
RESULTS = Path("/results")
CONTRACT = Path("/worker-contract.json")
SESSION = Path("/run/secrets/owner_session.json")
MIGRATOR_PASSWORD = Path("/run/secrets/migrator_db_password")
ACTIONS = ["ACCEPT_IDENTITY", "APPROVE_PROFILE_AND_ACCEPT_BIFROST"]
_DECISION_KEYS = {"version", "decisionId", "identityDecisionId", "correlationId", "manifestSha256",
                  "organizationId", "ownerId", "profileId", "actions", "review", "acceptanceSha256", "artifactSha256"}


def library_sha256() -> str:
    module_file = importlib.import_module("ai_res").__file__
    if module_file is None:
        raise SliceRefused("LIBRARY_CHANGED")
    root = Path(module_file).parent
    return digest(canonical([(p.relative_to(root).as_posix(), digest(p.read_bytes()))
                             for p in sorted(root.rglob("*.py"))]))


@dataclass(frozen=True, slots=True, repr=False)
class Inputs:
    plan: dict[str, Any]
    policy: PolicyConfig
    expectation: bytes
    observation: bytes
    acceptance: bytes
    artifact_sha256: dict[str, str]
    profile_sha256: str
    expectation_sha256: str
    observation_sha256: str


class OwnerUnconfirmed(RuntimeError):
    """Bounded status only: neither a rollback claim nor raw service error."""
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


def _object(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise SliceRefused("OWNER_ARTIFACT_INVALID")
    return value


def _uuid(value: Any) -> UUID:
    if not isinstance(value, str):
        raise SliceRefused("OWNER_DECISION_INVALID")
    parsed = UUID(value)
    if str(parsed) != value:
        raise SliceRefused("OWNER_DECISION_INVALID")
    return parsed


def target(plan: dict[str, Any]) -> tuple[str, int]:
    status, generation = plan.get("profileStatus", "CANDIDATE"), plan.get("admissionGeneration", 1)
    version = plan.get("experimentVersion", "1")
    if (not isinstance(version, str) or not 1 <= len(version) <= 4 or not version.isascii() or not version.isdecimal()
            or not 1 <= int(version) <= 1000 or str(int(version)) != version):
        raise SliceRefused("OWNER_TARGET_INVALID")
    if (status not in {"CANDIDATE", "APPROVED"} or type(generation) is not int or generation < 1
            or status == "CANDIDATE" and generation != 1
            or status == "APPROVED" and (generation < 2 or version == "1")):
        raise SliceRefused("OWNER_TARGET_INVALID")
    return status, generation


def decision_actions(plan: dict[str, Any]) -> list[str]:
    return list(ACTIONS) if target(plan)[0] == "CANDIDATE" else ["ACCEPT_IDENTITY"]


def load_inputs() -> Inputs:
    """Validate immutable local inputs before authentication or decision writes."""
    plan = load_plan(PLAN)
    _, generation = target(plan)
    if (plan["mode"] != "live" or plan["profileId"] != str(PROFILE_ID) or plan["profileVersion"] != 1
            or library_sha256() != plan["librarySha256"]):
        raise SliceRefused("OWNER_PLAN_CHANGED")
    contract = read_owned(CONTRACT)
    if digest(contract) != plan["workerContractSha256"]:
        raise SliceRefused("CONTRACT_CHANGED")
    WorkerContracts(decode(contract))
    source = source_from_plan(plan)
    if (plan["source"].get("license") != "MIT"
            or plan["source"]["provenance"].get("sourceSha256") != source.checksum):
        raise SliceRefused("SOURCE_CHANGED")
    policy = parse_policy_config(read_owned(PLAN / "policy.json"), plan["policySha256"])
    raw = {name: read_owned(RESULTS / name) for name in ("expectation.json", "observation.json", "acceptance.json")}
    expected, observed = review_evidence(raw["expectation.json"], raw["observation.json"])
    versions = ManagedVersions.from_dict(plan["managedVersions"])
    if (expected.managed_versions != versions or observed.managed_versions != versions
            or versions.profile_id != PROFILE_ID or versions.profile_version != 1
            or observed.request_ref != plan["phases"]["bootstrap"]
            or expected.admission_generation != generation
            or versions.config_sha256 != digest(canonical({k: v for k, v in plan.items()
                                                          if k not in {"manifestSha256", "managedVersions"}}))):
        raise SliceRefused("OWNER_EVIDENCE_CHANGED")
    profile_sha = profile_snapshot_hash(plan["profileSnapshot"])
    expected_sha, observed_sha = evidence_hash(expected).hex(), evidence_hash(observed).hex()
    acceptance = _object(decode(raw["acceptance.json"]), {"version", "manifestSha256", "profileId", "profileSha256",
        "expectationSha256", "observationSha256", "nativeEvidenceSha256", "evidence"})
    bindings = {"version": "slice01-acceptance/1", "manifestSha256": plan["manifestSha256"],
                "profileId": str(PROFILE_ID), "profileSha256": profile_sha,
                "expectationSha256": expected_sha, "observationSha256": observed_sha}
    if (any(acceptance[key] != value for key, value in bindings.items())
            or not isinstance(acceptance["evidence"], dict) or not acceptance["evidence"]
            or acceptance["nativeEvidenceSha256"] != digest(canonical(acceptance["evidence"]))):
        raise SliceRefused("ACCEPTANCE_CHANGED")
    evidence = acceptance["evidence"]
    references = ("toolHashes", "scriptsInitializerSha256", "bifrostImage", "nativeInputs", "librarySha256", "workerContractSha256")
    if evidence.get("status") != "LOCAL_CHECKS_PASSED" or any(evidence.get(key) != plan[key] for key in references):
        raise SliceRefused("NATIVE_EVIDENCE_CHANGED")
    return Inputs(plan, policy, raw["expectation.json"], raw["observation.json"], raw["acceptance.json"],
                  {name: digest(value) for name, value in raw.items()}, profile_sha, expected_sha, observed_sha)


def _review_bound(review: OwnerReview, inputs: Inputs) -> None:
    if (review.profile_sha256 != inputs.profile_sha256 or review.expectation_sha256 != inputs.expectation_sha256
            or review.observation_sha256 != inputs.observation_sha256 or review.policy_version != inputs.policy.version):
        raise SliceRefused("OWNER_REVIEW_CHANGED")


def decision_artifact(inputs: Inputs, review: OwnerReview) -> dict[str, Any]:
    _review_bound(review, inputs)
    return {"version": "slice01-owner-decision/1", "decisionId": str(uuid4()), "identityDecisionId": str(uuid4()),
            "correlationId": str(uuid4()), "manifestSha256": inputs.plan["manifestSha256"],
            "organizationId": str(ORGANIZATION_ID), "ownerId": str(OWNER_ID), "profileId": str(PROFILE_ID),
            "actions": decision_actions(inputs.plan), "review": asdict(review), "acceptanceSha256": digest(inputs.acceptance),
            "artifactSha256": dict(inputs.artifact_sha256)}


def load_decision(inputs: Inputs, confirmation: UUID) -> tuple[dict[str, Any], OwnerReview]:
    if not isinstance(confirmation, UUID):
        raise SliceRefused("EXPLICIT_OWNER_CONFIRMATION_REQUIRED")
    decision = _object(decode(read_owned(RESULTS / f"decision-{confirmation}.json")), _DECISION_KEYS)
    expected = {"version": "slice01-owner-decision/1", "decisionId": str(confirmation),
                "manifestSha256": inputs.plan["manifestSha256"], "organizationId": str(ORGANIZATION_ID),
                "ownerId": str(OWNER_ID), "profileId": str(PROFILE_ID), "actions": decision_actions(inputs.plan),
                "acceptanceSha256": digest(inputs.acceptance), "artifactSha256": inputs.artifact_sha256}
    if any(decision[key] != value for key, value in expected.items()):
        raise SliceRefused("OWNER_DECISION_CHANGED")
    identifiers = [_uuid(decision[key]) for key in ("decisionId", "identityDecisionId", "correlationId")]
    if len(set(identifiers)) != 3:
        raise SliceRefused("OWNER_DECISION_INVALID")
    review = OwnerReview(**_object(decision["review"], {"binding_sha256", "profile_sha256", "expectation_sha256",
                                                       "observation_sha256", "policy_version"}))
    _review_bound(review, inputs)
    return decision, review


def owner_transaction(connection: Connection) -> None:
    """Only registered on the isolated migrator engine; fixed local SQL only."""
    connection.execute(text("SET LOCAL ROLE ai_res_owner"))
    connection.execute(text("SELECT set_config('app.migration_mode','on',true)"))


def _receipt(name: str, value: dict[str, Any]) -> None:
    path = RESULTS / name
    try:
        write_new(path, value)
    except FileExistsError:
        if decode(read_owned(path)) != value:
            raise SliceRefused("OWNER_RECEIPT_CHANGED") from None


async def execute(action: str, confirmation: UUID | None = None) -> dict[str, Any]:
    if action not in {"prepare-decision", "approve", "accept-identity"} or (action != "prepare-decision") != isinstance(confirmation, UUID):
        raise SliceRefused("EXPLICIT_OWNER_CONFIRMATION_REQUIRED")
    inputs = load_inputs()
    profile_status, _ = target(inputs.plan)
    if action != "prepare-decision" and action != ("approve" if profile_status == "CANDIDATE" else "accept-identity"):
        raise SliceRefused("OWNER_ACTION_SCOPE_MISMATCH")
    decision, review = load_decision(inputs, confirmation) if confirmation is not None else (None, None)
    settings = load_settings(os.environ)
    if (settings.db_user != "ai_res_api" or settings.db_sslmode != "verify-full"
            or settings.db_name != "ai_res_db" or settings.db_password_file == MIGRATOR_PASSWORD):
        raise SliceRefused("API_IDENTITY_REQUIRED")
    api_engine = create_runtime_engine(settings)
    owner_engine = None
    status = "OWNER_PREPARATION_UNCONFIRMED" if action == "prepare-decision" else "IDENTITY_OUTCOME_UNCONFIRMED"
    try:
        factory = create_session_factory(api_engine)
        sessions = SessionService(factory, idle=timedelta(seconds=settings.session_idle_seconds),
            absolute=timedelta(seconds=settings.session_absolute_seconds),
            touch_interval=timedelta(seconds=settings.session_touch_interval_seconds))
        token = decode(read_owned(SESSION))["sessionToken"]
        if not isinstance(token, str):
            raise SliceRefused("OWNER_SESSION_REQUIRED")
        auth = await sessions.authenticate(token, touch=False)
        actor = auth.session
        if (not isinstance(actor, AuthenticatedSession) or actor.user_id != OWNER_ID or actor.organization_id != ORGANIZATION_ID
                or actor.second_factor_pending or actor.mfa_verified_at is None):
            raise SliceRefused("OWNER_MFA_SESSION_REQUIRED")
        policy = PolicyEnforcer(PolicyEngine(inputs.policy, factory), factory, inputs.policy,
                                timeout_seconds=settings.policy_timeout_seconds)
        scope = OwnerReviewScope(ORGANIZATION_ID, OWNER_ID, PROFILE_ID)
        if action == "prepare-decision":
            review = await OwnerReviewService(factory, policy, scope=scope).prepare(actor,
                expectation=inputs.expectation, observation=inputs.observation)
            artifact = decision_artifact(inputs, review)
            filename = f"decision-{artifact['decisionId']}.json"
            write_new(RESULTS / filename, artifact)
            return {"status": "OWNER_DECISION_PREPARED_NOT_APPROVED", "decisionId": artifact["decisionId"],
                    "decisionFile": filename,
                    "approvalAction": "approve" if profile_status == "CANDIDATE" else "accept-identity",
                    "decisionSha256": digest(canonical(artifact) + b"\n"), "manifestSha256": inputs.plan["manifestSha256"]}
        assert decision is not None and review is not None
        # Credentials are read only after exact confirmation and API authentication.
        # No SET ROLE hook is installed on the API engine.
        owner_settings = settings.model_copy(update={"db_user": "ai_res_migrator", "db_password_file": Path(MIGRATOR_PASSWORD),
                                                     "db_application_name": "slice01-owner"})
        owner_engine = create_runtime_engine(owner_settings)
        event.listen(owner_engine.sync_engine, "begin", owner_transaction)
        owner_factory = create_session_factory(owner_engine)
        identity = await IdentityAdmissionOperator(owner_factory, policy, scope=scope).execute(actor,
            IdentityDecision(_uuid(decision["identityDecisionId"]), _uuid(decision["correlationId"]),
                             IdentityDecisionAction.ACCEPT_IDENTITY, review),
            expectation=inputs.expectation, observation=inputs.observation)
        status = "IDENTITY_ACCEPTED_PROFILE_NOT_CONFIRMED"
        base = {"version": "slice01-owner-receipt/1", "manifestSha256": inputs.plan["manifestSha256"],
                "decisionId": decision["decisionId"], "identityDecisionId": decision["identityDecisionId"],
                "profileId": str(PROFILE_ID), "generation": identity.generation,
                "acceptanceSha256": digest(inputs.acceptance)}
        if profile_status == "APPROVED":
            status = "IDENTITY_ACCEPTED_RECEIPT_UNCONFIRMED"
            result = {**base, "status": "IDENTITY_ACCEPTED_PROFILE_APPROVAL_UNCHANGED"}
            _receipt(f"identity-receipt-{decision['decisionId']}.json", result)
            return result
        _receipt(f"identity-receipt-{decision['decisionId']}.json", {**base, "status": "IDENTITY_ACCEPTED_PROFILE_NOT_CONFIRMED"})
        approval = ProfileApprovalDecision(_uuid(decision["decisionId"]), _uuid(decision["correlationId"]),
            ProfileApprovalAction.APPROVE_PROFILE_AND_ACCEPT_BIFROST, inputs.profile_sha256, inputs.expectation_sha256,
            inputs.observation_sha256, digest(inputs.acceptance), inputs.policy.version)
        profile = await ProfileApprovalService(owner_factory, policy, scope=scope, owner_login="ai_res_migrator").execute(
            actor, approval, expectation=inputs.expectation, observation=inputs.observation, bifrost_acceptance=inputs.acceptance)
        status = "APPROVED_RECEIPT_UNCONFIRMED"
        result = {**base, "status": "IDENTITY_AND_PROFILE_APPROVED", "profileVersion": profile.profile_version}
        _receipt(f"approval-receipt-{decision['decisionId']}.json", result)
        return result
    except Exception:
        raise OwnerUnconfirmed(status) from None
    finally:
        try:
            if owner_engine is not None:
                await owner_engine.dispose()
        finally:
            await api_engine.dispose()


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise SliceRefused("OWNER_ARGUMENTS_REFUSED")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("action", choices=("prepare-decision", "approve", "accept-identity"))
        parser.add_argument("--confirm-decision", type=UUID)
        args = parser.parse_args(argv)
        print(json.dumps(asyncio.run(execute(args.action, args.confirm_decision))))
        return 0
    except OwnerUnconfirmed as error:
        print(json.dumps({"status": error.status}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"status": "OWNER_OPERATION_REFUSED"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
