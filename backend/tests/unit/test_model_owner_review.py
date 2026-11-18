"""Identity review material is comparison input, never approval authority."""
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityExpectation,
    IdentityObservation,
    ManagedVersions,
    ObservedFingerprint,
    ObservedProviderIdentity,
)
from ai_res.modules.model_registry.admission import AdmissionDenied, evidence_hash
from ai_res.modules.model_registry.owner_review import OwnerReviewScope, review_evidence


def material():
    versions = ManagedVersions("a" * 40, uuid4(), 1, "b" * 64, "c" * 64, None)
    identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "DeepSeek-V4.1-Flash-0000",
                                        ObservedFingerprint(FingerprintPresence.VALUE, "synthetic-fingerprint"))
    expected = IdentityExpectation(versions, identity, 1, "d" * 64)
    observation = IdentityObservation(versions, identity, datetime(2026, 11, 17, tzinfo=UTC), "synthetic-call", "synthetic-provider-request")
    return replace(expected, evidence_sha256=evidence_hash(observation).hex()), observation


def test_review_requires_actual_observation_digest_and_exact_identity():
    expected, observation = material()
    assert review_evidence(json.dumps(expected.to_dict()), json.dumps(observation.to_dict())) == (expected, observation)
    with pytest.raises(AdmissionDenied):
        review_evidence(json.dumps(replace(expected, evidence_sha256="0" * 64).to_dict()), json.dumps(observation.to_dict()))
    changed = replace(observation, managed_versions=replace(observation.managed_versions, config_sha256="e" * 64))
    with pytest.raises(AdmissionDenied):
        review_evidence(json.dumps(expected.to_dict()), json.dumps(changed.to_dict()))


@pytest.mark.parametrize("raw", ["{", '{"schemaVersion":"99"}', '{"sourceText":"private-source"}', '{"kind":"OBSERVATION","kind":"EXPECTATION"}'])
def test_invalid_review_evidence_is_safely_refused(raw):
    expected, observation = material()
    for args in ((raw, json.dumps(observation.to_dict())), (json.dumps(expected.to_dict()), raw)):
        with pytest.raises(AdmissionDenied) as caught:
            review_evidence(*args)
        assert "private-source" not in str(caught.value)


@pytest.mark.parametrize("bad", [None, "owner", 1, True])
def test_scope_needs_explicit_uuid_identity_and_profile(bad):
    with pytest.raises(AdmissionDenied):
        OwnerReviewScope(bad, uuid4(), uuid4())
