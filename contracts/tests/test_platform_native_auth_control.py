"""Private native authorization route and signed-credential schemas agree."""
import contracts_lib as L
from jsonschema import Draft202012Validator

NATIVE = L.CONTRACTS / "internal/platform-native-auth-control.v1.yaml"


def test_native_auth_control_declares_an_action_for_each_signed_route():
    assert L.validate_openapi(NATIVE) == []
    document = L.load(NATIVE)
    claims = document["components"]["schemas"]["AuthControlClaims"]
    assert set(claims["properties"]["action"]["enum"]) == {path.rsplit("/", 1)[-1] for path in document["paths"]}


def test_reconciliation_describe_requires_only_exact_run_metadata():
    document = L.load(NATIVE)
    metadata = {"operationId": "9b8d71d6-49c1-4307-aefe-d91ee4b037b9",
                "workflowRunId": "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf", "namespace": "default"}
    for action in ("authorize-reconciliation-describe", "authorize-bound-status"):
        operation = document["paths"][f"/internal/auth-control/v1/{action}"]["post"]
        schema = L.deref(operation["requestBody"]["content"]["application/json"]["schema"], document)
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        assert validator.is_valid(metadata)
        assert not validator.is_valid({key: value for key, value in metadata.items() if key != "workflowRunId"})
        assert not validator.is_valid({**metadata, "projectId": "external"})
        assert "content" not in operation["responses"]["204"]


def test_bound_cancel_requires_assignment_and_exact_run():
    document = L.load(NATIVE)
    operation = document["paths"]["/internal/auth-control/v1/authorize-bound-cancel"]["post"]
    schema = L.deref(operation["requestBody"]["content"]["application/json"]["schema"], document)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    intent = {"assignmentId": "9b8d71d6-49c1-4307-aefe-d91ee4b037b9", "operationId": "90ed515f-69af-4c52-b9dd-53a0be99ee8e",
              "workflowRunId": "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf", "namespace": "default"}
    assert validator.is_valid(intent)
    for key in intent:
        assert not validator.is_valid({name: value for name, value in intent.items() if name != key})
    assert not validator.is_valid({**intent, "signalName": "request_cancel"})
    assert "content" not in operation["responses"]["204"]
