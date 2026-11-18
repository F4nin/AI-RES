"""Human command and fail-closed boundaries; PostgreSQL semantics need real PG."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_res.db.cas import canonical_json
from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityExpectation,
    IdentityObservation,
    ManagedVersions,
    ObservedFingerprint,
    ObservedProviderIdentity,
)
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.model_registry.admission import AdmissionDenied, evidence_hash
from ai_res.modules.model_registry.owner_review import OwnerReviewScope
from ai_res.modules.model_registry.profile_approval import (
    ProfileApprovalAction,
    ProfileApprovalDecision,
    ProfileApprovalService,
    profile_snapshot_hash,
)


def command():
    return ProfileApprovalDecision(uuid4(), uuid4(), ProfileApprovalAction.APPROVE_PROFILE_AND_ACCEPT_BIFROST,
                                   "a" * 64, "b" * 64, "c" * 64, "d" * 64, "synthetic-policy")


def test_approval_command_requires_explicit_human_action_and_hides_evidence():
    value = command()
    assert value.action is ProfileApprovalAction.APPROVE_PROFILE_AND_ACCEPT_BIFROST
    assert "a" * 64 not in repr(value)


@pytest.mark.parametrize("field,value", [
    ("decision_id", "bad"), ("correlation_id", None), ("action", "APPROVE_PROFILE_AND_ACCEPT_BIFROST"),
    ("action", True), ("profile_sha256", "short"), ("expectation_sha256", "g" * 64),
    ("observation_sha256", None), ("bifrost_acceptance_sha256", ""), ("policy_version", "bad value"),
])
def test_untyped_or_unbound_decision_refuses(field, value):
    with pytest.raises(AdmissionDenied):
        replace(command(), **{field: value})


async def test_default_unconfigured_service_cannot_authenticate_or_mutate():
    service = ProfileApprovalService(None, None)
    with pytest.raises(AdmissionDenied):
        await service.execute_token("never-exported", command(), expectation=b"", observation=b"", bifrost_acceptance=b"")
    with pytest.raises(AdmissionDenied):
        await service.execute(None, command(), expectation=b"", observation=b"", bifrost_acceptance=b"")


def evidence():
    import hashlib
    now = datetime(2026, 11, 18, tzinfo=UTC)
    scope = OwnerReviewScope(uuid4(), uuid4(), uuid4())
    actor = AuthenticatedSession(uuid4(), scope.organization_id, scope.user_id, now,
                                 now + timedelta(hours=1), now + timedelta(hours=2), "", b"")
    versions = ManagedVersions("a" * 40, scope.profile_id, 1, "b" * 64, "c" * 64, None)
    identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "deepseek-flash",
                                       ObservedFingerprint(FingerprintPresence.VALUE, "synthetic-fingerprint"))
    observed = IdentityObservation(versions, identity, now, "synthetic-app-ref", "synthetic-provider-ref")
    expected = IdentityExpectation(versions, identity, 1, evidence_hash(observed).hex())
    bifrost = b"synthetic explicitly accepted Bifrost artifact"
    snapshot = '{"status":"CANDIDATE","profile_version":1,"cost_input_per_million":1.000001}'
    cmd = ProfileApprovalDecision(uuid4(), uuid4(), ProfileApprovalAction.APPROVE_PROFILE_AND_ACCEPT_BIFROST,
        profile_snapshot_hash(snapshot), evidence_hash(expected).hex(), evidence_hash(observed).hex(),
        hashlib.sha256(bifrost).hexdigest(), "synthetic-policy")
    return scope, actor, expected, observed, bifrost, snapshot, cmd


@pytest.mark.parametrize("changed", ["expected", "observation", "acceptance", "foreign-profile"])
async def test_evidence_and_exact_profile_binding_refuse_before_database_access(changed):
    scope, actor, expected, observed, bifrost, _, cmd = evidence()
    if changed == "expected":
        cmd = replace(cmd, expectation_sha256="f" * 64)
    elif changed == "observation":
        cmd = replace(cmd, observation_sha256="f" * 64)
    elif changed == "acceptance":
        bifrost += b"changed"
    else:
        scope = replace(scope, profile_id=uuid4())
    service = ProfileApprovalService(None, None, scope=scope, owner_login="configured-owner")
    with pytest.raises(AdmissionDenied) as caught:
        await service.execute(actor, cmd, expectation=canonical_json(expected.to_dict()),
                              observation=canonical_json(observed.to_dict()), bifrost_acceptance=bifrost)
    assert caught.value.code == "INVALID_APPROVAL_EVIDENCE"


async def test_token_authentication_does_not_touch_session_or_accept_a_missing_identity():
    calls = []

    class Sessions:
        async def authenticate(self, token, *, touch):
            calls.append((token, touch))
            return SimpleNamespace(session=None)

    service = ProfileApprovalService(None, None, sessions=Sessions())
    with pytest.raises(AdmissionDenied) as caught:
        await service.execute_token("private-synthetic-token", command(), expectation=b"", observation=b"", bifrost_acceptance=b"")
    assert caught.value.code == "OWNER_REQUIRED"
    assert calls == [("private-synthetic-token", False)]
