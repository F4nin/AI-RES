"""Private v5 binds the draft to a metadata-only snapshot."""
from jsonschema import Draft202012Validator

import contracts_lib as L

V5 = L.CONTRACTS / "internal/AI_RES_Platform_Internal_API_v0.5.yaml"
ROOT = "/internal/v5/operations/{operationId}"
OP = "75f04762-d122-47ee-ba84-e58a45af5692"
RUN = "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf"
CONTEXT = "7b4367c2-aec6-4cca-a483-713d3bde20b8"


def test_only_exact_bound_v5_commands_and_no_store():
    assert L.validate_openapi(V5) == []
    v5 = L.load(V5)
    assert list(v5["paths"]) == [f"{ROOT}/manager-input", f"{ROOT}/manager-draft"]
    read, draft = (path["post"] for path in v5["paths"].values())
    assert read["x-action"] == "manager.read_input" and draft["x-action"] == "manager.record_draft"
    assert read["x-caller"] == draft["x-caller"] == "MANAGER_RUNTIME"
    assert read["responses"]["200"]["headers"]["Cache-Control"] == {"required": True, "schema": {"const": "no-store"}}
    assert v5["security"] == [{"platformAr2": []}]

    request = {"workflowId": f"operation-{OP}", "workflowRunId": RUN}
    schemas = v5["components"]["schemas"]
    v3 = L.load(V5.with_name("AI_RES_Platform_Internal_API_v0.3.yaml"))
    assert schemas["OperationStatus"] == v3["components"]["schemas"]["OperationStatus"]
    assert Draft202012Validator(schemas["ExecutionRequest"]).is_valid(request)
    assert not Draft202012Validator(schemas["ExecutionRequest"]).is_valid({**request, "epicId": OP})
    validator = Draft202012Validator(schemas["ContextDraft"], format_checker=Draft202012Validator.FORMAT_CHECKER)
    proposal = {**request, "goal": None, "scope": None, "primaryQuestion": None}
    assert not validator.is_valid(proposal)
    assert validator.is_valid({**proposal, "contextVersionId": CONTEXT})
    assert not validator.is_valid({**proposal, "contextVersionId": CONTEXT, "approval": "APPROVE"})


def test_snapshot_cannot_contain_history_text_or_negative_counters():
    v5 = L.load(V5)
    schema = v5["components"]["schemas"]["ContextInput"]
    validator = Draft202012Validator({**schema, "components": v5["components"]})
    state = {
        "epicVersion": 1, "epicStatus": "ACTIVE", "operationVersion": 3, "operationStatus": "RUNNING",
        "questionSequence": 1, "hasOpenQuestion": True, "planVersion": None, "planDecision": None, "taskCounts": {"PROPOSED": 2},
    }
    payload = {"operationId": OP, "message": "Intake fixture", "contextVersionId": CONTEXT, "epicState": state}
    assert validator.is_valid(payload)
    assert not validator.is_valid({**payload, "recentQuestions": []})
    for extra in ({"scope": "canary"}, {"openQuestionId": OP}, {"taskCounts": {"PROPOSED": -1}}, {"operationStatus": "SUCCEEDED"}):
        assert not validator.is_valid({**payload, "epicState": {**state, **extra}})
