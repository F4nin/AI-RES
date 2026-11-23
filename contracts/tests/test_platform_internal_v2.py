"""S20 contract checks for the private Manager operation control interface."""
import pytest
from jsonschema import Draft202012Validator

import contracts_lib as L

INTERNAL = L.CONTRACTS / "internal/AI_RES_Platform_Internal_API_v0.2.yaml"
PUBLIC = L.CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml"
OPERATION_PREFIX = "/internal/v2/operations/{operationId}"
ACTIONS = {
    "start-acknowledgement": "operation.acknowledge_start",
    "failure": "operation.record_failure",
    "cancellation-confirmation": "operation.confirm_cancellation",
}
EXECUTION = {
    "workflowId": "operation-fixture",
    "workflowRunId": "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf",
}
CLAIMS = {
    "iss": "MANAGER_RUNTIME",
    "aud": "PLATFORM_API",
    "iat": 1,
    "exp": 60,
    "nonce": "a309390e-6dd1-46c6-a028-48f74070a7d0",
    "action": ACTIONS["start-acknowledgement"],
    "method": "POST",
    "path": "/internal/v2/operations/75f04762-d122-47ee-ba84-e58a45af5692/start-acknowledgement",
    "bodySha256": "a" * 64,
    "assignmentId": "c2865635-eac5-4af3-944e-55915e04bc3b",
}


@pytest.fixture
def internal():
    return L.load(INTERNAL)


def test_internal_v2_is_registered_valid_and_mirrored():
    mapping = L.load(L.CONTRACTS / "mirror-map.json")
    entries = [entry["source"] for entry in mapping["files"] if L.CONTRACTS / entry["published"] == INTERNAL]
    assert entries == [INTERNAL.name]
    manifest = L.load(L.REPO / mapping["manifest"])
    mirrored = [entry for entry in manifest["files"] if entry["path"] == INTERNAL.name]
    assert mirrored == [{"path": INTERNAL.name, "sha256": L.sha256(INTERNAL), "bytes": INTERNAL.stat().st_size}]
    assert L.verify_mirror() == []
    assert L.validate_openapi(INTERNAL) == []


def test_internal_v2_operations_are_absent_from_the_public_contract(internal):
    public, errors = L.merged_document("openapi", PUBLIC)

    assert errors == []
    assert not any(path.startswith("/internal/") for path in public["paths"])
    internal_operations = {item["post"]["operationId"] for item in internal["paths"].values()}
    assert all(
        operation.get("operationId") not in internal_operations
        for item in public["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
    )
    assert "platformRequest" not in public["components"].get("securitySchemes", {})


def test_internal_v2_routes_require_the_private_manager_credential(internal):
    assert internal["info"]["version"] == "0.2.0"
    assert internal["x-status"] == "BASELINED"
    assert internal["security"] == [{"platformRequest": []}]
    assert set(internal["components"]["securitySchemes"]) == {"platformRequest"}
    bearer = internal["components"]["securitySchemes"]["platformRequest"]
    assert (bearer["type"], bearer["scheme"], bearer["bearerFormat"]) == ("http", "bearer", "ar2")
    assert set(internal["paths"]) == {f"{OPERATION_PREFIX}/{suffix}" for suffix in ACTIONS}

    for suffix, action in ACTIONS.items():
        item = internal["paths"][f"{OPERATION_PREFIX}/{suffix}"]
        assert set(item) == {"parameters", "post"}
        operation = item["post"]
        assert "security" not in operation
        assert operation["x-action"] == action
        assert operation["x-caller"] == "MANAGER_RUNTIME"
        responses = operation["responses"]
        assert {"200", "401", "403", "404", "422", "503"} <= responses.keys()
        for status in responses.keys() - {"200"}:
            assert set(L.deref(responses[status], internal)["content"]) == {"application/problem+json"}


@pytest.mark.parametrize("suffix", ACTIONS)
def test_internal_v2_body_accepts_only_the_metadata_for_its_action(internal, suffix):
    operation = internal["paths"][f"{OPERATION_PREFIX}/{suffix}"]["post"]
    body = L.deref(operation["requestBody"], internal)
    assert body["required"] is True
    schema = body["content"]["application/json"]["schema"]
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    valid_body = {**EXECUTION, "code": "FIXTURE_FAILURE"} if suffix == "failure" else EXECUTION
    assert set(schema["properties"]) == set(schema["required"]) == valid_body.keys()
    assert validator.is_valid(valid_body)
    assert not validator.is_valid({**valid_body, "workflowRunId": "invalid"})
    assert not validator.is_valid({**valid_body, "workflowId": ""})
    for extra in ("organizationId", "projectId", "actorId", "credentials", "message", "prompt", "source"):
        assert not validator.is_valid({**valid_body, extra: "untrusted-value"}), extra


def test_internal_v2_signed_claims_require_exact_request_and_assignment(internal):
    schema = internal["components"]["schemas"]["PlatformRequestClaims"]
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

    assert set(schema["properties"]) == set(schema["required"]) == CLAIMS.keys()
    assert set(schema["properties"]["action"]["enum"]) == set(ACTIONS.values())
    assert validator.is_valid(CLAIMS)
    for field in CLAIMS:
        assert not validator.is_valid({name: value for name, value in CLAIMS.items() if name != field}), field
    for boundary_violation in (
        {"aud": "API"},
        {"iss": "WORKER_RUNTIME"},
        {"method": "GET"},
        {"action": "tool.execute"},
        {"bodySha256": "A" * 64},
        {"nonce": "invalid"},
        {"assignmentId": "invalid"},
        {"projectId": "client-supplied-tenant"},
    ):
        assert not validator.is_valid({**CLAIMS, **boundary_violation}), boundary_violation
