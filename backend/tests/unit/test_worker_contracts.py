"""S14: WorkerRunEnvelope / WorkerResult / WorkerNotice validation in the four points (DOC-007 v1.1, WORKING — ADR-021).

Points: ENQUEUE and PRE_EXECUTION validate the Envelope; RESULT_RECEIPT and DOWNSTREAM validate the Result and the Notice. Everything is fail-closed.
"""
import copy
import json
import math
from collections import UserDict
from pathlib import Path
from uuid import uuid4

import pytest

from ai_res.worker_contracts import (
    ContractViolation,
    Reason,
    ValidationPoint,
    WorkerContracts,
    WorkerNoticeModel,
    WorkerResultModel,
    WorkerRunEnvelopeModel,
    load_worker_contracts,
)

SCHEMA = Path(__file__).resolve().parents[3] / "contracts" / "json-schema" / "worker" / "AI_RES_Worker_Contracts_v1.1.schema.json"
# Fake secrets are assembled at run time: the repository secret scanner (and a reader) must not meet a literal one in the source.
FAKE_PEM = "-----BEGIN " + "PRIVATE KEY-----\nMIIB\n-----END " + "PRIVATE KEY-----"
FAKE_TOKEN = "use to" + "ken=gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789"
ENVELOPE_POINTS = [ValidationPoint.ENQUEUE, ValidationPoint.PRE_EXECUTION]
RESULT_POINTS = [ValidationPoint.RESULT_RECEIPT, ValidationPoint.DOWNSTREAM]


def _ref() -> dict:
    return {"objectType": "SourceVersion", "objectId": str(uuid4()), "versionId": str(uuid4())}


def envelope() -> dict:
    return {
        "contractVersion": "1.1", "workerRunId": str(uuid4()), "organizationId": str(uuid4()), "projectId": str(uuid4()), "epicId": str(uuid4()),
        "taskId": str(uuid4()), "workerDefinitionId": str(uuid4()), "workerRole": "REQUIREMENTS", "contextPackageVersionId": str(uuid4()),
        "contextChecksum": "a" * 64, "goal": "Formalise FR for login", "scope": {"included": ["login"], "excluded": []},
        "expectedOutputSchema": {"schemaId": "requirements.candidates", "schemaVersion": "1"},
        "acceptanceCriteria": [{"criterionId": "AC-1", "description": "each FR has evidence", "verificationMethod": "INDEPENDENT_QA"}],
        "allowedTools": [], "correlationId": str(uuid4()), "attempt": 1, "idempotencyKey": "k" * 32, "runPurpose": "PRIMARY"}


def result(**over) -> dict:
    base = {
        "contractVersion": "1.1", "workerRunId": str(uuid4()), "taskId": str(uuid4()), "workerRole": "REQUIREMENTS", "resultStatus": "COMPLETED",
        "summary": "done", "findings": [{"findingId": "F-1", "classification": "FACT", "statement": "login exists", "evidenceRefs": [_ref()]}],
        "proposedChanges": [], "artifactRefs": [], "questions": [], "blockers": [], "limitations": [],
        "validation": {"selfAssessment": "PASS"}, "completedAt": "2026-11-13T10:00:00Z"}
    base.update(over)
    return base


def notice(**over) -> dict:
    base = {"contractVersion": "1.1", "workerRunId": str(uuid4()), "noticeId": str(uuid4()), "noticeType": "BLOCKER", "severity": "HIGH",
            "message": "source unreadable", "createdAt": "2026-11-13T10:00:00Z"}
    base.update(over)
    return base


@pytest.fixture(scope="module")
def contracts() -> WorkerContracts:
    return WorkerContracts.from_file(SCHEMA)


def _bad(kind: str, point: ValidationPoint, payload: dict, contracts: WorkerContracts) -> ContractViolation:
    with pytest.raises(ContractViolation) as exc:
        contracts.check(kind, payload, point)
    assert exc.value.point is point
    return exc.value


# ---- valid payloads ----------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("point", ENVELOPE_POINTS)
def test_valid_envelope_is_accepted_and_typed(contracts, point):
    model = contracts.check("envelope", envelope(), point)
    assert isinstance(model, WorkerRunEnvelopeModel) and model.worker_role == "REQUIREMENTS"


@pytest.mark.parametrize("point", RESULT_POINTS)
def test_valid_result_and_notice_are_accepted(contracts, point):
    assert isinstance(contracts.check("result", result(), point), WorkerResultModel)
    contracts.check("notice", notice(), point)


# ---- unknown major: rejected in all four points ------------------------------------------------------------------------------------------------------

KINDS = [("envelope", envelope, ENVELOPE_POINTS), ("result", result, RESULT_POINTS), ("notice", notice, RESULT_POINTS)]


@pytest.mark.parametrize(("kind", "build", "points"), KINDS)
@pytest.mark.parametrize("version", ["2.0", "2.1", "0.9", "10.0", "2", "", None, 1.1, ["1.1"]])
def test_unknown_major_is_rejected_at_every_point(contracts, kind, build, points, version):
    for point in points:
        payload = build()
        payload["contractVersion"] = version
        assert _bad(kind, point, payload, contracts).reason is Reason.UNSUPPORTED_CONTRACT_VERSION


@pytest.mark.parametrize("version", ["1.0", "1.2", "1.10", "1.1.1"])
def test_same_major_other_minor_is_rejected_not_downgraded(contracts, version):
    payload = envelope()
    payload["contractVersion"] = version
    assert _bad("envelope", ValidationPoint.ENQUEUE, payload, contracts).reason is Reason.UNSUPPORTED_CONTRACT_VERSION


def test_missing_contract_version_is_rejected(contracts):
    payload = result()
    del payload["contractVersion"]
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, payload, contracts).reason is Reason.UNSUPPORTED_CONTRACT_VERSION


# ---- extra / missing fields ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("point", ENVELOPE_POINTS)
def test_envelope_extra_and_missing_fields_are_rejected(contracts, point):
    extra = envelope()
    extra["debugPrompt"] = "x"
    assert _bad("envelope", point, extra, contracts).reason is Reason.SCHEMA_REJECTED
    for key in ("workerRunId", "organizationId", "projectId", "contextPackageVersionId", "contextChecksum", "acceptanceCriteria", "idempotencyKey"):
        payload = envelope()
        del payload[key]
        assert _bad("envelope", point, payload, contracts).reason is Reason.SCHEMA_REJECTED, key


@pytest.mark.parametrize("point", RESULT_POINTS)
def test_result_and_notice_extra_and_missing_fields_are_rejected(contracts, point):
    assert _bad("result", point, result(rawLlmResponse="..."), contracts).reason is Reason.SCHEMA_REJECTED
    missing = result()
    del missing["findings"]
    assert _bad("result", point, missing, contracts).reason is Reason.SCHEMA_REJECTED
    assert _bad("notice", point, notice(extra=1), contracts).reason is Reason.SCHEMA_REJECTED
    no_msg = notice()
    del no_msg["message"]
    assert _bad("notice", point, no_msg, contracts).reason is Reason.SCHEMA_REJECTED


def test_invalid_enum_and_format_are_rejected(contracts):
    assert _bad("envelope", ValidationPoint.ENQUEUE, {**envelope(), "workerRole": "ADMIN"}, contracts).reason is Reason.SCHEMA_REJECTED
    assert _bad("envelope", ValidationPoint.ENQUEUE, {**envelope(), "taskId": "not-a-uuid"}, contracts).reason is Reason.SCHEMA_REJECTED
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(resultStatus="APPROVED"), contracts).reason is Reason.SCHEMA_REJECTED
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(completedAt="yesterday"), contracts).reason is Reason.SCHEMA_REJECTED


def test_conditional_envelope_rules(contracts):
    qa = {**envelope(), "runPurpose": "INDEPENDENT_QA"}
    assert _bad("envelope", ValidationPoint.ENQUEUE, qa, contracts).reason is Reason.SCHEMA_REJECTED  # needs parentWorkerRunId + reviewId
    contracts.check("envelope", {**qa, "parentWorkerRunId": str(uuid4()), "reviewId": str(uuid4())}, ValidationPoint.ENQUEUE)
    consultation = {**notice(), "noticeType": "CONSULTATION_REQUEST"}
    assert _bad("notice", ValidationPoint.RESULT_RECEIPT, consultation, contracts).reason is Reason.SCHEMA_REJECTED  # needs coordinationRequest


# ---- evidence and secrets -----------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("classification", ["FACT", "SOURCE_ASSERTION", "CONCLUSION"])
@pytest.mark.parametrize("point", RESULT_POINTS)
def test_claim_without_evidence_refs_is_rejected(contracts, classification, point):
    finding = {"findingId": "F-1", "classification": classification, "statement": "s", "evidenceRefs": []}
    assert _bad("result", point, result(findings=[finding]), contracts).reason is Reason.EVIDENCE_MISSING


@pytest.mark.parametrize("classification", ["HYPOTHESIS", "ASSUMPTION", "UNKNOWN"])
def test_uncertain_finding_may_have_no_evidence(contracts, classification):
    finding = {"findingId": "F-1", "classification": classification, "statement": "s", "evidenceRefs": [], "uncertainty": "unverified"}
    contracts.check("result", result(findings=[finding]), ValidationPoint.RESULT_RECEIPT)


@pytest.mark.parametrize("point", RESULT_POINTS)
def test_result_with_secret_key_or_value_is_rejected(contracts, point):
    by_value = result(summary="connect with password=hunter2hunter2")
    assert _bad("result", point, by_value, contracts).reason is Reason.FORBIDDEN_CONTENT
    token = result(limitations=["Authorization: Bearer abcdefghijklmnop"])
    assert _bad("result", point, token, contracts).reason is Reason.FORBIDDEN_CONTENT
    pem = result(blockers=[FAKE_PEM])
    assert _bad("result", point, pem, contracts).reason is Reason.FORBIDDEN_CONTENT


def test_long_text_is_scanned_completely(contracts):
    contracts.check("result", result(summary="plain words " * 2000), ValidationPoint.RESULT_RECEIPT)  # 24k characters, nothing secret: accepted
    hidden = result(summary=("plain words " * 1500) + " password=hunter2hunter2 " + ("plain words " * 500))  # secret beyond the first 8192 characters
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, hidden, contracts).reason is Reason.FORBIDDEN_CONTENT
    boundary = result(summary="x" * 7990 + " password=hunter2hunter2")  # straddles a window edge
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, boundary, contracts).reason is Reason.FORBIDDEN_CONTENT


def test_notice_with_secret_is_rejected(contracts):
    bad = notice(message="db url postgresql://u:p@host/db")
    assert _bad("notice", ValidationPoint.RESULT_RECEIPT, bad, contracts).reason is Reason.FORBIDDEN_CONTENT


def test_envelope_with_secret_is_rejected(contracts):
    bad = envelope()
    bad["goal"] = FAKE_TOKEN
    assert _bad("envelope", ValidationPoint.ENQUEUE, bad, contracts).reason is Reason.FORBIDDEN_CONTENT


def test_violation_never_echoes_payload_values(contracts):
    bad = result(summary="password=hunter2hunter2")
    violation = _bad("result", ValidationPoint.RESULT_RECEIPT, bad, contracts)
    assert "hunter2" not in str(violation) and "hunter2" not in json.dumps(violation.errors)
    schema_bad = result(resultStatus="TOP-SECRET-VALUE")
    violation = _bad("result", ValidationPoint.RESULT_RECEIPT, schema_bad, contracts)
    assert "TOP-SECRET-VALUE" not in str(violation) and "TOP-SECRET-VALUE" not in json.dumps(violation.errors)


# ---- misuse and loader ------------------------------------------------------------------------------------------------------------------------------

def test_kind_point_mismatch_is_a_programming_error(contracts):
    with pytest.raises(ValueError, match="point"):
        contracts.check("envelope", envelope(), ValidationPoint.RESULT_RECEIPT)
    with pytest.raises(ValueError, match="point"):
        contracts.check("result", result(), ValidationPoint.ENQUEUE)
    with pytest.raises(ValueError, match="kind"):
        contracts.check("coordination", {}, ValidationPoint.ENQUEUE)


def test_non_object_payload_is_rejected(contracts):
    for payload in (None, [], "x", 1):
        assert _bad("envelope", ValidationPoint.ENQUEUE, payload, contracts).reason is Reason.SCHEMA_REJECTED  # type: ignore[arg-type]


def test_loader_refuses_missing_or_empty_schema(tmp_path):
    with pytest.raises(OSError):
        WorkerContracts.from_file(tmp_path / "absent.json")
    empty = tmp_path / "empty.json"
    empty.write_text('{"$defs": {}}')
    with pytest.raises(ValueError, match="WorkerRunEnvelope"):
        WorkerContracts.from_file(empty)


def test_input_is_not_mutated(contracts):
    payload = envelope()
    before = copy.deepcopy(payload)
    contracts.check("envelope", payload, ValidationPoint.ENQUEUE)
    assert payload == before


# ---- parity: the Pydantic models agree with the canonical schema --------------------------------------------------------------------------------------

PARITY = [("WorkerRunEnvelope", WorkerRunEnvelopeModel), ("WorkerResult", WorkerResultModel), ("WorkerNotice", WorkerNoticeModel)]


@pytest.mark.parametrize(("name", "model"), PARITY)
def test_pydantic_fields_match_schema_properties(name, model):
    schema = json.loads(SCHEMA.read_text())["$defs"][name]
    aliases = {f.alias or n for n, f in model.model_fields.items()}
    assert aliases == set(schema["properties"])
    required = {f.alias or n for n, f in model.model_fields.items() if f.is_required()}
    assert required == set(schema["required"])


def test_startup_helper_refuses_unset_or_missing_schema(tmp_path):
    with pytest.raises(ValueError, match="fail-closed"):
        load_worker_contracts(None)
    with pytest.raises(OSError):
        load_worker_contracts(tmp_path / "absent.json")
    assert load_worker_contracts(SCHEMA).check("envelope", envelope(), ValidationPoint.ENQUEUE)


# ---- review fixes (S14 review round 1) ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_a_contract_violation_not_a_storage_error(contracts, bad):
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(metrics={"reportedCost": bad}), contracts).reason is Reason.SCHEMA_REJECTED


def test_lone_surrogate_is_a_contract_violation(contracts):
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(summary="broken \ud800 text"), contracts).reason is Reason.SCHEMA_REJECTED


def test_oversize_payload_is_rejected_before_scanning(contracts):
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(outcome="x" * 2_000_000), contracts).reason is Reason.SCHEMA_REJECTED


def test_non_json_containers_are_rejected(contracts):
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, UserDict(result()), contracts).reason is Reason.SCHEMA_REJECTED  # type: ignore[arg-type]
    _, snapshot = contracts.check_snapshot("result", result(questions=("a tuple is a JSON array",)), ValidationPoint.RESULT_RECEIPT)
    assert snapshot["questions"] == ["a tuple is a JSON array"]  # the snapshot holds plain JSON types only


def test_snapshot_is_independent_of_the_callers_object(contracts):
    payload = result()
    _, snapshot = contracts.check_snapshot("result", payload, ValidationPoint.RESULT_RECEIPT)
    payload["summary"] = "mutated after the check"
    payload["findings"][0]["statement"] = "mutated too"
    assert snapshot["summary"] == "done" and snapshot["findings"][0]["statement"] == "login exists"


def test_forbidden_content_names_the_field_but_not_the_value(contracts):
    violation = _bad("result", ValidationPoint.RESULT_RECEIPT, result(limitations=["ok", "password=hunter2hunter2"]), contracts)
    assert violation.errors == ["$/limitations/1: forbidden_content"] and "hunter2" not in str(violation)


@pytest.mark.parametrize("text", ["password\uff1dhunter2hunter2", "pass\u200bword=hunter2hunter2", "PASSWORD\uff1a hunter2hunter2"])
def test_unicode_tricks_do_not_hide_a_secret(contracts, text):
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, result(summary=text), contracts).reason is Reason.FORBIDDEN_CONTENT


@pytest.mark.parametrize("prose", [
    "Password: min 15 characters", "Token: refresh flow", "token: expires in 30 min", "Secret: rotate quarterly", "The password: must be hashed with Argon2id",
    "Authorization: required for every call", "api-key = optional"])
def test_requirements_prose_about_secrets_is_accepted(contracts, prose):
    """OD-20 / ADR-104: a secret word + separator + one short plain word describes a rule; it is not a credential."""
    contracts.check("result", result(summary=prose), ValidationPoint.RESULT_RECEIPT)


CREDENTIAL_LIKE = [
    "password=hunter2hunter2", "password: 12345678", 'password="tiger"', "password='tiger'", "token: " + FAKE_TOKEN, "secret=abc-def-ghi", "password: Hunter2",
    "passwordhunter: correct-horse", "Password: Bearer abcdefghijklmnop", "api_key=sk-" + "a" * 20, "token: abc.def", 'password:  "quoted words here"']


@pytest.mark.parametrize("value", CREDENTIAL_LIKE)
def test_credential_like_values_stay_rejected(contracts, value):
    violation = _bad("result", ValidationPoint.RESULT_RECEIPT, result(summary=value), contracts)
    assert violation.reason is Reason.FORBIDDEN_CONTENT and violation.errors == ["$/summary: forbidden_content"]


def test_descriptive_pair_does_not_shield_a_secret_next_to_it(contracts):
    mixed = result(summary="Password: min 15 characters, and the config says password=hunter2hunter2")
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, mixed, contracts).reason is Reason.FORBIDDEN_CONTENT
    bearer = result(summary="Authorization: required. Sent as Bearer abcdefghijklmnop")
    assert _bad("result", ValidationPoint.RESULT_RECEIPT, bearer, contracts).reason is Reason.FORBIDDEN_CONTENT


def test_accepted_risk_a_plain_word_after_the_separator_is_not_detected(contracts):
    """G-140: `password: tiger` cannot be told from prose. Pinned so the residual risk is visible; changing it needs a new owner decision."""
    contracts.check("result", result(summary="password: tiger"), ValidationPoint.RESULT_RECEIPT)
