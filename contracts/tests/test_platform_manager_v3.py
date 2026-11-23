"""S20/S21 checks for the private Manager input, draft and task commands."""
import pytest
from jsonschema import Draft202012Validator

import contracts_lib as L

INTERNAL = L.CONTRACTS / "internal/AI_RES_Platform_Internal_API_v0.3.yaml"
PUBLIC = L.CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml"
OPERATIONS = "/internal/v3/operations/{operationId}"
MANAGER_COMMANDS = ("manager-input", "manager-draft", "plan-tasks")
OPERATION_ID = "75f04762-d122-47ee-ba84-e58a45af5692"
EXECUTION = {
    "workflowId": "operation-fixture",
    "workflowRunId": "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf",
}
DRAFT = {"goal": "Capture the goal", "scope": "This Epic", "primaryQuestion": "Which audience?"}


@pytest.fixture
def internal():
    return L.load(INTERNAL)


def test_manager_contract_is_registered_valid_and_mirrored():
    mapping = L.load(L.CONTRACTS / "mirror-map.json")
    entries = [entry["source"] for entry in mapping["files"] if L.CONTRACTS / entry["published"] == INTERNAL]
    assert entries == [INTERNAL.name]
    manifest = L.load(L.REPO / mapping["manifest"])
    mirrored = [entry for entry in manifest["files"] if entry["path"] == INTERNAL.name]
    assert mirrored == [{"path": INTERNAL.name, "sha256": L.sha256(INTERNAL), "bytes": INTERNAL.stat().st_size}]
    assert L.verify_mirror() == []
    assert L.validate_openapi(INTERNAL) == []


def test_manager_commands_are_private_and_require_assigned_service_identity(internal):
    public, errors = L.merged_document("openapi", PUBLIC)
    assert errors == []
    assert not any(path.startswith("/internal/") for path in public["paths"])
    assert internal["info"]["version"] == "0.3.0"
    assert set(internal["paths"]) == {f"{OPERATIONS}/{command}" for command in MANAGER_COMMANDS}

    claims = internal["components"]["schemas"]["PlatformRequestClaims"]
    assert set(claims["required"]) == {"iss", "aud", "iat", "exp", "nonce", "action", "method", "path", "bodySha256", "assignmentId"}
    assert claims["additionalProperties"] is False
    assert claims["properties"]["iss"]["const"] == "MANAGER_RUNTIME"
    assert claims["properties"]["aud"]["const"] == "PLATFORM_API"
    assert claims["properties"]["method"]["const"] == "POST"
    actions = set()
    for item in internal["paths"].values():
        assert set(item) == {"parameters", "post"}
        [operation_id_parameter] = L.deref(item["parameters"], internal)
        assert (operation_id_parameter["name"], operation_id_parameter["in"], operation_id_parameter["required"]) == (
            "operationId", "path", True,
        )
        assert operation_id_parameter["schema"]["format"] == "uuid"
        operation = item["post"]
        assert operation["x-caller"] == "MANAGER_RUNTIME"
        actions.add(operation["x-action"])
        security = operation.get("security", internal.get("security", []))
        assert len(security) == 1 and len(security[0]) == 1
        scheme, scopes = next(iter(security[0].items()))
        assert scopes == []
        bearer = internal["components"]["securitySchemes"][scheme]
        assert (bearer["type"], bearer["scheme"], bearer["bearerFormat"]) == ("http", "bearer", "ar2")
        response_codes = operation["responses"].keys()
        assert {"200", "401", "403", "404", "422", "503"} <= response_codes
    assert len(actions) == len(MANAGER_COMMANDS)
    assert actions <= set(claims["properties"]["action"]["enum"])


@pytest.mark.parametrize("command", MANAGER_COMMANDS)
def test_manager_commands_accept_only_bounded_execution_and_draft_fields(internal, command):
    operation = internal["paths"][f"{OPERATIONS}/{command}"]["post"]
    body = L.deref(operation["requestBody"], internal)
    assert body["required"] is True
    schema = L.deref(body["content"]["application/json"]["schema"], internal)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

    valid_body = {**EXECUTION, **DRAFT} if command == "manager-draft" else EXECUTION
    assert set(schema["properties"]) == valid_body.keys()
    assert set(EXECUTION) <= set(schema["required"]) <= valid_body.keys()
    assert validator.is_valid(valid_body)
    for field in EXECUTION:
        assert not validator.is_valid({name: value for name, value in valid_body.items() if name != field}), field
    assert not validator.is_valid({**valid_body, "workflowRunId": "invalid"})
    assert not validator.is_valid({**valid_body, "workflowId": ""})
    for extra in ("organizationId", "projectId", "actorId", "approvalId", "planVersionId", "workerRunId", "taskIds"):
        assert not validator.is_valid({**valid_body, extra: "untrusted-value"}), extra
    if command == "manager-draft":
        assert validator.is_valid({**EXECUTION, **dict.fromkeys(DRAFT)})
        for field in DRAFT:
            assert not validator.is_valid({**valid_body, field: {"text": "unexpected shape"}}), field


@pytest.mark.parametrize("command", MANAGER_COMMANDS)
def test_manager_commands_disclose_only_their_typed_results(internal, command):
    response = internal["paths"][f"{OPERATIONS}/{command}"]["post"]["responses"]["200"]
    response = L.deref(response, internal)
    schema = L.deref(response["content"]["application/json"]["schema"], internal)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

    result = {"operationId": OPERATION_ID, "message": "What should the system do?"} if command == "manager-input" else {
        "operationId": OPERATION_ID, "status": "RUNNING",
    }
    assert set(schema["properties"]) == set(schema["required"]) == result.keys()
    assert validator.is_valid(result)
    assert not validator.is_valid({**result, "operationId": "invalid"})
    for extra in ("assignmentId", "approved", "approvalId", "workerRunId", "result", "tasks"):
        assert not validator.is_valid({**result, extra: "out-of-scope-result"}), extra
    if command != "manager-input":
        assert schema == L.deref(internal["components"]["schemas"]["OperationStatus"], internal)
        assert not validator.is_valid({**result, "status": "APPROVED"})
