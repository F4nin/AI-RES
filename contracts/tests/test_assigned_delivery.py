"""The private dispatch handoff carries only the lease and returns no domain data."""
from jsonschema import Draft202012Validator

import contracts_lib as L

WIRE = L.CONTRACTS / "internal/AI_RES_Assigned_Outbox_Delivery_Internal_API_v1.0.yaml"


def test_assigned_delivery_wire_is_closed_and_private():
    assert L.validate_openapi(WIRE) == []
    contract = L.load(WIRE)
    assert contract["security"] == [{"deliveryAr2": []}]
    assert list(contract["paths"]) == ["/internal/assigned-delivery/v1"]
    command = contract["paths"]["/internal/assigned-delivery/v1"]["post"]
    assert command["x-caller"] == "OUTBOX_DISPATCHER" and command["x-action"] == "outbox.deliver_assigned"
    assert "content" not in command["responses"]["204"]
    assert command["responses"]["204"]["headers"]["Cache-Control"]["required"] is True
    schema = contract["components"]["schemas"]["DeliveryLease"]
    valid = {"rowId": "75f04762-d122-47ee-ba84-e58a45af5692", "leaseOwner": "fixture", "attempt": 1, "replayCount": 0}
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    assert validator.is_valid(valid)
    for unknown in ("workflowRunId", "organizationId", "namespace", "envelope"):
        assert not validator.is_valid({**valid, unknown: "external"})
    assert not validator.is_valid({**valid, "attempt": 0})
