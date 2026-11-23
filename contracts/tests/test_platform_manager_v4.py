"""The adaptive intake response is narrow, versioned and private."""
import pytest
from jsonschema import Draft202012Validator

import contracts_lib as L

V4 = L.CONTRACTS / "internal/AI_RES_Platform_Internal_API_v0.4.yaml"
V3 = V4.with_name("AI_RES_Platform_Internal_API_v0.3.yaml")
ROUTE = "/internal/v4/operations/{operationId}/manager-input"
V3_ROUTE = ROUTE.replace("/v4/", "/v3/")
OPERATION_ID = "75f04762-d122-47ee-ba84-e58a45af5692"
RUN_ID = "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf"
QUESTION_ID = "7b4367c2-aec6-4cca-a483-713d3bde20b8"
ANSWER = {"questionId": QUESTION_ID, "topic": "project.owner", "disposition": "ANSWERED", "answer": "The operations lead."}


@pytest.fixture
def v4():
    return L.load(V4)


def test_v4_keeps_the_existing_action_and_forbids_client_selected_context(v4):
    assert L.validate_openapi(V4) == []
    assert L.verify_mirror() == []
    mapping = L.load(L.CONTRACTS / "mirror-map.json")
    assert any(L.CONTRACTS / entry["published"] == V4 for entry in mapping["files"])
    assert list(v4["paths"]) == [ROUTE]
    operation = v4["paths"][ROUTE]["post"]
    old = L.load(V3)["paths"][V3_ROUTE]["post"]
    assert operation["x-caller"] == old["x-caller"] == "MANAGER_RUNTIME"
    assert operation["x-action"] == old["x-action"] == "manager.read_input"
    assert v4["security"] == [{"platformAr2": []}]
    body = L.deref(operation["requestBody"], v4)
    schema = L.deref(body["content"]["application/json"]["schema"], v4)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    valid = {"workflowId": f"operation-{OPERATION_ID}", "workflowRunId": RUN_ID}
    assert validator.is_valid(valid)
    for field in ("epicId", "projectId", "organizationId", "questionId", "sourceRefs", "limit", "cursor"):
        assert not validator.is_valid({**valid, field: "caller-controlled"})


@pytest.mark.parametrize("disposition,answer,valid", [
    ("ANSWERED", "The operations lead.", True),
    ("ANSWERED", None, True),
    ("UNKNOWN", None, True),
    ("OPEN", None, True),
    ("UNKNOWN", "An asserted fact", False),
    ("OPEN", "An asserted fact", False),
    ("APPROVED", None, False),
])
def test_v4_distinguishes_open_unknown_and_admitted_answers(v4, disposition, answer, valid):
    post = v4["paths"][ROUTE]["post"]
    response = post["responses"]["200"]["content"]["application/json"]["schema"]
    schema = L.deref(response, v4)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    item = {**ANSWER, "disposition": disposition, "answer": answer}
    payload = {"operationId": OPERATION_ID, "message": "Continue intake", "recentQuestions": [item], "historyTruncated": False}
    assert validator.is_valid(payload) is valid
    assert not validator.is_valid({**payload, "epicId": "extra"})
    assert not validator.is_valid({**payload, "recentQuestions": [{**item, "approval": "APPROVED"}]})
    assert not validator.is_valid({**payload, "recentQuestions": [ANSWER] * 9})
    assert not validator.is_valid({**payload, "recentQuestions": [{**ANSWER, "answer": "x" * 20001}]})
