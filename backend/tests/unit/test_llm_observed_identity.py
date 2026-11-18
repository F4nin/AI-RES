"""Offline proposal tests. Synthetic metadata proves no provider compatibility or admission."""
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityExpectation,
    IdentityMismatch,
    IdentityNotAccepted,
    IdentityObservation,
    InvalidIdentityEvidence,
    ObservedFingerprint,
    compare_identity,
    extract_bifrost_observation,
    parse_evidence,
)

VERSIONS = {"codeRevision": "a" * 40, "profileId": "00000000-0000-0000-0000-000000000001", "profileVersion": 1,
            "configSha256": "b" * 64, "promptSha256": "c" * 64, "toolsSha256": None}
IDENTITY = {"provider": "deepseek", "requestModelId": "deepseek-flash", "routingModelId": "deepseek-flash",
            "responseModelId": "DeepSeek-V4.1-Flash-0000", "fingerprint": {"presence": "VALUE", "value": "fixture-backend"}}
OBSERVATION = {"schemaVersion": "0.2", "kind": "OBSERVATION", "managedVersions": VERSIONS, "identity": IDENTITY,
               "observedAt": "2026-11-17T00:00:00Z", "requestRef": "fixture-call", "providerRequestRef": "fixture-provider-call"}
EXPECTATION = {"schemaVersion": "0.2", "kind": "EXPECTATION", "managedVersions": VERSIONS, "identity": IDENTITY,
               "admissionGeneration": 7, "evidenceSha256": "d" * 64}


def observation(data=None):
    result = parse_evidence(json.dumps(OBSERVATION if data is None else data))
    assert isinstance(result, IdentityObservation)
    return result


def expectation(data=None):
    result = parse_evidence(json.dumps(EXPECTATION if data is None else data))
    assert isinstance(result, IdentityExpectation)
    return result


def wire():
    return {"id": "fixture-provider-call", "model": "DeepSeek-V4.1-Flash-0000", "system_fingerprint": "fixture-backend",
            "choices": [{"message": {"content": "Source content must never enter metadata evidence"}}],
            "extra_fields": {"routing_info": {"provider": "deepseek", "model": "deepseek-flash", "requested_model": "deepseek-flash"}}}


def test_real_extraction_roundtrip_and_comparison_produce_only_metadata():
    result = extract_bifrost_observation(wire(), managed_versions=observation().managed_versions,
                                        observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-flash")
    assert result.to_dict() == OBSERVATION
    compare_identity(result, expectation(), current_generation=7)
    assert parse_evidence(json.dumps(result.to_dict()).encode()) == result
    assert "Source content" not in json.dumps(result.to_dict())
    assert "fixture-backend" not in repr(result)


@pytest.mark.parametrize("record", [OBSERVATION, EXPECTATION])
def test_real_serialization_satisfies_proposed_machine_contract(record):
    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/llm-observed-identity.v0.2.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    parsed = parse_evidence(json.dumps(record))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(parsed.to_dict())
    assert parsed.to_dict() == record


@pytest.mark.parametrize("stamp", ["2026-11-17T00:00:00Z", "2026-11-17T00:00:00.1Z", "2026-11-17T00:00:00.123456Z"])
def test_schema_and_parser_accept_utc_timestamps_with_optional_microseconds(stamp):
    data = deepcopy(OBSERVATION)
    data["observedAt"] = stamp
    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/llm-observed-identity.v0.2.schema.json").read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(data)
    result = observation(data)
    assert result.observed_at == datetime.fromisoformat(stamp)


def test_record_and_nested_values_are_immutable_and_serialization_is_a_copy():
    result = observation()
    with pytest.raises(FrozenInstanceError):
        result.request_ref = "changed"
    with pytest.raises(FrozenInstanceError):
        result.identity.response_model_id = "changed"
    serialized = result.to_dict()
    serialized["identity"]["responseModelId"] = "changed"
    assert result.to_dict() == OBSERVATION
    with pytest.raises(InvalidIdentityEvidence):
        replace(result.managed_versions, profile_version=True)


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "DeepSeek-V4-Pro-0813", "other-model"])
def test_unexpected_or_pro_response_can_be_evidence_but_never_a_flash_expectation(model):
    observed, expected = deepcopy(OBSERVATION), deepcopy(EXPECTATION)
    observed["identity"]["responseModelId"] = expected["identity"]["responseModelId"] = model
    assert observation(observed).identity.response_model_id == model
    with pytest.raises(InvalidIdentityEvidence):
        expectation(expected)
    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/llm-observed-identity.v0.2.schema.json").read_text())
    assert not jsonschema.Draft202012Validator(schema).is_valid(expected)


@pytest.mark.parametrize("value", [True, 0, -1, 1.0, "7", 2147483648])
def test_expectation_and_comparison_require_strict_positive_generation(value):
    data = deepcopy(EXPECTATION)
    data["admissionGeneration"] = value
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))
    with pytest.raises(InvalidIdentityEvidence):
        compare_identity(observation(), expectation(), current_generation=value)


@pytest.mark.parametrize("path", [("requestRef",), ("providerRequestRef",), ("identity", "responseModelId"),
                                 ("identity", "fingerprint", "value"), ("managedVersions", "configSha256")])
def test_schema_and_parser_both_reject_final_newlines(path):
    data = deepcopy(OBSERVATION)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] += "\n"
    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/llm-observed-identity.v0.2.schema.json").read_text())
    assert not jsonschema.Draft202012Validator(schema).is_valid(data)
    with pytest.raises(InvalidIdentityEvidence):
        observation(data)


@pytest.mark.parametrize("presence,value", [("ABSENT", None), ("NULL", None), ("VALUE", "fixture-backend")])
def test_fingerprint_presence_is_preserved_from_wire_and_schema(presence, value):
    response = wire()
    if presence == "ABSENT":
        del response["system_fingerprint"]
    else:
        response["system_fingerprint"] = value
    result = extract_bifrost_observation(response, managed_versions=observation().managed_versions,
                                        observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-flash")
    assert result.to_dict()["identity"]["fingerprint"] == {"presence": presence, "value": value}
    assert parse_evidence(json.dumps(result.to_dict())) == result


@pytest.mark.parametrize("old,new", [("ABSENT", "NULL"), ("NULL", "ABSENT"), ("ABSENT", "VALUE"),
                                     ("NULL", "VALUE"), ("VALUE", "ABSENT"), ("VALUE", "NULL")])
def test_every_fingerprint_presence_change_is_refused(old, new):
    observed, expected = deepcopy(OBSERVATION), deepcopy(EXPECTATION)
    expected["identity"]["fingerprint"] = {"presence": old, "value": "fixture-backend" if old == "VALUE" else None}
    observed["identity"]["fingerprint"] = {"presence": new, "value": "fixture-backend" if new == "VALUE" else None}
    failure = IdentityMismatch if old == "VALUE" else InvalidIdentityEvidence
    with pytest.raises(failure):
        compare_identity(observation(observed), expectation(expected), current_generation=7)


def test_changed_fingerprint_and_response_model_mismatch_without_echo():
    for field in ("responseModelId", "fingerprint"):
        data = deepcopy(OBSERVATION)
        data["identity"][field] = "unexpected-response" if field == "responseModelId" else {"presence": "VALUE", "value": "changed-backend"}
        with pytest.raises(IdentityMismatch) as error:
            compare_identity(observation(data), expectation(), current_generation=7)
        assert "unexpected-response" not in str(error.value)
        assert "changed-backend" not in str(error.value)


def test_candidate_observation_never_approves_itself_and_generation_must_match():
    with pytest.raises(IdentityNotAccepted):
        compare_identity(observation(), None, current_generation=7)
    with pytest.raises(IdentityMismatch):
        compare_identity(observation(), expectation(), current_generation=8)


@pytest.mark.parametrize("version", ["1.0", "0.1", "0.3", "0", 0, None, True])
def test_unknown_or_malformed_contract_versions_fail_closed(version):
    data = deepcopy(OBSERVATION)
    data["schemaVersion"] = version
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("key", list(OBSERVATION))
def test_every_required_observation_field_is_required(key):
    data = deepcopy(OBSERVATION)
    del data[key]
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("key", list(IDENTITY))
def test_every_required_identity_field_is_required(key):
    data = deepcopy(OBSERVATION)
    del data["identity"][key]
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("key", list(VERSIONS))
def test_every_managed_version_field_is_required(key):
    data = deepcopy(OBSERVATION)
    del data["managedVersions"][key]
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("path", [(), ("identity",), ("identity", "fingerprint"), ("managedVersions",)])
def test_unknown_fields_cannot_smuggle_content(path):
    data = deepcopy(OBSERVATION)
    target = data
    for key in path:
        target = target[key]
    target["sourceText"] = "fixture-sensitive-body"
    with pytest.raises(InvalidIdentityEvidence) as error:
        parse_evidence(json.dumps(data))
    assert "fixture-sensitive-body" not in str(error.value)


@pytest.mark.parametrize("field,value", [("provider", "other"), ("requestModelId", "deepseek-v4-pro"),
                                        ("routingModelId", "deepseek-v4-pro"), ("responseModelId", "https://provider.invalid/model"),
                                        ("responseModelId", "x" * 129), ("responseModelId", "unsafe\nvalue")])
def test_scope_and_identifier_violations_are_refused(field, value):
    data = deepcopy(OBSERVATION)
    data["identity"][field] = value
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("field,value", [("profileVersion", True), ("profileVersion", 0), ("codeRevision", "main"),
                                        ("configSha256", "b" * 63), ("promptSha256", "C" * 64), ("toolsSha256", "latest"),
                                        ("profileId", "not-a-uuid")])
def test_managed_versions_are_exact_validated_references(field, value):
    data = deepcopy(OBSERVATION)
    data["managedVersions"][field] = value
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("field", list(VERSIONS))
def test_any_managed_version_change_prevents_comparison_match(field):
    data = deepcopy(OBSERVATION)
    alternatives = {"codeRevision": "e" * 40, "profileId": "00000000-0000-0000-0000-000000000002", "profileVersion": 2,
                    "configSha256": "e" * 64, "promptSha256": "e" * 64, "toolsSha256": "e" * 64}
    data["managedVersions"][field] = alternatives[field]
    with pytest.raises(IdentityMismatch):
        compare_identity(observation(data), expectation(), current_generation=7)


@pytest.mark.parametrize("stamp", ["2026-11-17", "2026-11-17T00:00:00", "2026-11-17T01:00:00+01:00", "2026-02-30T00:00:00Z"])
def test_only_valid_explicit_utc_timestamps_are_accepted(stamp):
    data = deepcopy(OBSERVATION)
    data["observedAt"] = stamp
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(data))


@pytest.mark.parametrize("stamp", [datetime(2026, 11, 17), datetime(2026, 11, 17, tzinfo=timezone(timedelta(hours=1)))])
def test_trusted_extraction_clock_must_supply_utc(stamp):
    with pytest.raises(InvalidIdentityEvidence):
        extract_bifrost_observation(wire(), managed_versions=observation().managed_versions,
                                    observed_at=stamp, request_ref="fixture-call", request_model_id="deepseek-flash")


@pytest.mark.parametrize("routing", [{}, {"provider": "deepseek"}, {"provider": "other", "model": "deepseek-flash"},
                                     {"provider": "deepseek", "model": "deepseek-v4-pro"},
                                     {"provider": "deepseek", "model": "deepseek-flash", "is_fallback": True},
                                     {"provider": "deepseek", "model": "deepseek-flash", "is_fallback": 0},
                                     {"provider": "deepseek", "model": "deepseek-flash", "server_side_fallback_model": "other"},
                                     {"provider": "deepseek", "model": "deepseek-flash", "resolved_key_alias": "other"},
                                     {"provider": "deepseek", "model": "deepseek-flash", "requested_model": "other"}])
def test_actual_bifrost_routing_failures_are_refused(routing):
    response = wire()
    response["extra_fields"] = {"routing_info": routing}
    with pytest.raises(InvalidIdentityEvidence):
        extract_bifrost_observation(response, managed_versions=observation().managed_versions,
                                    observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-flash")


@pytest.mark.parametrize("raw", ['{"schemaVersion":"0.2","schemaVersion":"0.2"}', '{"nested":{"x":1,"x":2}}',
                                 '{"x":NaN}', '[]', '{', b'\xff', " " * 16385])
def test_duplicate_malformed_nonfinite_or_oversized_json_is_refused(raw):
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(raw)


def test_secret_shaped_metadata_is_rejected_without_leaking_it():
    data = deepcopy(OBSERVATION)
    value = "sk-" + "x" * 32
    data["providerRequestRef"] = value
    with pytest.raises(InvalidIdentityEvidence) as error:
        parse_evidence(json.dumps(data))
    assert value not in str(error.value)


@pytest.mark.parametrize("value", [None, "", True, [], "x" * 129])
def test_provider_request_reference_is_mandatory_nonnull_and_bounded(value):
    data = deepcopy(OBSERVATION)
    data["providerRequestRef"] = value
    with pytest.raises(InvalidIdentityEvidence):
        observation(data)
    response = wire()
    response["id"] = value
    with pytest.raises(InvalidIdentityEvidence):
        extract_bifrost_observation(response, managed_versions=observation().managed_versions,
                                    observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-flash")


def test_extraction_refuses_missing_provider_request_reference_and_wrong_trusted_request_model():
    response = wire()
    del response["id"]
    with pytest.raises(InvalidIdentityEvidence):
        extract_bifrost_observation(response, managed_versions=observation().managed_versions,
                                    observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-flash")
    with pytest.raises(InvalidIdentityEvidence):
        extract_bifrost_observation(wire(), managed_versions=observation().managed_versions,
                                    observed_at=datetime(2026, 11, 17, tzinfo=UTC), request_ref="fixture-call", request_model_id="deepseek-v4-pro")


@pytest.mark.parametrize("presence", [FingerprintPresence.ABSENT, FingerprintPresence.NULL])
def test_expected_flash_identity_requires_fingerprint_value_even_for_direct_construction(presence):
    incomplete = replace(observation().identity, fingerprint=ObservedFingerprint(presence, None))
    with pytest.raises(InvalidIdentityEvidence):
        replace(expectation(), identity=incomplete)


def test_new_fingerprint_requirement_emits_versioned_evidence():
    assert observation().to_dict()["schemaVersion"] == "0.2"
    assert expectation().to_dict()["schemaVersion"] == "0.2"


@pytest.mark.parametrize("record", [OBSERVATION, EXPECTATION])
def test_pre_decision_evidence_needs_explicit_regeneration_not_silent_admission(record):
    previous = deepcopy(record)
    previous["schemaVersion"] = "0.1"
    with pytest.raises(InvalidIdentityEvidence):
        parse_evidence(json.dumps(previous))


@pytest.mark.parametrize("presence", ["ABSENT", "NULL"])
def test_expected_fingerprint_is_required_by_both_schema_and_semantic_parser(presence):
    data = deepcopy(EXPECTATION)
    data["identity"]["fingerprint"] = {"presence": presence, "value": None}
    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/llm-observed-identity.v0.2.schema.json").read_text())
    assert not jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).is_valid(data)
    with pytest.raises(InvalidIdentityEvidence):
        expectation(data)


@pytest.mark.parametrize("value", [None, "", " ", "fixture\n", "x" * 129])
def test_expected_fingerprint_value_cannot_be_empty_unsafe_or_oversized(value):
    data = deepcopy(EXPECTATION)
    data["identity"]["fingerprint"] = {"presence": "VALUE", "value": value}
    with pytest.raises(InvalidIdentityEvidence):
        expectation(data)
