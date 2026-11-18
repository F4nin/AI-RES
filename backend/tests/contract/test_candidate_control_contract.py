"""WORKING candidate wire schema is structural; typed parsers add semantics."""
import json
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest

from ai_res.llm.adapters.candidate_control import CONTROL_VERSION as CLIENT_VERSION
from ai_res.llm.candidate_payload import CODEC_VERSION
from ai_res.modules.model_registry.poc_control import CONTROL_VERSION as SERVER_VERSION

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "contracts/internal/flash-candidate-control.v0.1.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def claim():
    return {"version": CLIENT_VERSION, "codecVersion": CODEC_VERSION, "templateCase": "TEXT", "bodySha256": "a" * 64,
            "payloadBytes": 256, "stream": False, "maxOutputTokens": 256}


def test_versioned_schema_is_valid_and_matches_both_implemented_wire_versions():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert CLIENT_VERSION == SERVER_VERSION == SCHEMA["$defs"]["claimRequest"]["properties"]["version"]["const"]
    VALIDATOR.validate(claim())


@pytest.mark.parametrize("change", [{"accountId": str(uuid4())}, {"price": 0}, {"version": "unknown/99"},
                                    {"codecVersion": "unknown/99"}, {"templateCase": "TEXT", "stream": True},
                                    {"templateCase": "SSE", "stream": False}, {"maxOutputTokens": 255}])
def test_unknown_scope_version_and_impossible_codec_metadata_are_not_valid_wire(change):
    with pytest.raises(jsonschema.ValidationError):
        VALIDATOR.validate(claim() | change)


def test_settlement_shapes_are_outcome_exclusive_and_cannot_declare_a_cost():
    common = {"version": CLIENT_VERSION, "attemptId": str(uuid4()), "bodySha256": "a" * 64}
    known = common | {"outcome": "KNOWN", "inputTokens": 12, "outputTokens": 2, "providerRequestRef": "synthetic-provider"}
    unknown = common | {"outcome": "UNKNOWN", "reason": "TIMEOUT"}
    for value in (known, unknown, common | {"outcome": "INVALID_USAGE"}):
        VALIDATOR.validate(value)
    for invalid in (known | {"reason": None}, unknown | {"inputTokens": None}, known | {"cost": 0}, known | {"inputTokens": True}):
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(invalid)


@pytest.mark.parametrize("field", ["bodySha256", "attemptId", "requestRef"])
def test_schema_reference_patterns_do_not_accept_trailing_line_feed(field):
    reply = {"version": CLIENT_VERSION, "attemptId": str(uuid4()), "requestRef": "synthetic-ref", "bodySha256": "a" * 64,
             "payloadBytes": 256, "stream": False, "maxOutputTokens": 256}
    reply[field] += "\n"
    with pytest.raises(jsonschema.ValidationError):
        VALIDATOR.validate(reply)
