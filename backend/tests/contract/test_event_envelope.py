"""The Operation/WorkerRun event envelope against the REAL canonical messages of AsyncAPI v1.6 (G-56 option A), with the pinned jsonschema validator.

Static schema validation is not runtime evidence of delivery; it proves only that what append_event writes has the contract's shape.
"""
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import jsonschema
import pytest
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ai_res.modules.events.envelope import (
    OPERATION_EVENT_TYPES,
    WORKER_RUN_EVENT_TYPES,
    EventRef,
    build_envelope,
    event_type_name,
)
from ai_res.platform.clock import utc_now

ROOT = Path(__file__).resolve().parents[3] / "contracts"
ASYNCAPI = ROOT / "asyncapi" / "AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"
STATE_MACHINE = ROOT / "json-schema" / "common" / "AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json"
TYPE = re.compile(r"^com\.aires\.((?:operation|worker_run)\.[a-z_]+)\.v1$")
# Normative conflict recorded in KNOWN_GAPS G-56: State Machine v1.2 lists this event type, AsyncAPI v1.6 has no canonical message for it.
LISTED_BUT_NOT_MODELLED = {"worker_run.created"}


@pytest.fixture(scope="module")
def asyncapi() -> dict[str, Any]:
    return yaml.safe_load(ASYNCAPI.read_text())


@pytest.fixture(scope="module")
def canonical(asyncapi: dict[str, Any]) -> dict[str, str]:
    """short event type -> JSON pointer of its message payload schema inside the AsyncAPI document."""
    found: dict[str, str] = {}
    for name, message in asyncapi["components"]["messages"].items():
        const = message.get("payload", {}).get("properties", {}).get("type", {}).get("const", "")
        match = TYPE.match(const)
        if match:
            found[match.group(1)] = f"#/components/messages/{name}/payload"
    return found


def validator(asyncapi: dict[str, Any], pointer: str) -> jsonschema.Draft202012Validator:
    registry = Registry().with_resource("urn:aires:asyncapi", Resource.from_contents(asyncapi, default_specification=DRAFT202012))
    return jsonschema.Draft202012Validator({"$ref": f"urn:aires:asyncapi{pointer}"}, registry=registry, format_checker=jsonschema.FormatChecker())


def envelope(short: str, aggregate_type: str, *, full: bool) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if full:
        extra = {"actor_id": uuid4(), "causation_id": uuid4(), "reason_code": "SOME_REASON", "from_status": "A", "to_status": "B",
                 "details": {"note": "typed", "n": 1}, "refs": (EventRef("TASK", uuid4(), uuid4()), EventRef("OPERATION", uuid4()))}
    base: dict[str, Any] = {"actor_id": None, "causation_id": None, "reason_code": None, "from_status": None, "to_status": None, "details": {}, "refs": ()}
    return build_envelope(
        aggregate_type=aggregate_type, aggregate_id=uuid4(), event_id=uuid4(), sequence=3, version=4, occurred_at=utc_now(), organization_id=uuid4(),
        project_id=uuid4(), operation_id=uuid4(), event_type=short, schema_version=1, actor_type="MANAGER", correlation_id=uuid4(), **{**base, **extra})


def aggregate_of(short: str) -> str:
    return "OPERATION" if short.startswith("operation.") else "WORKER_RUN"


def test_registries_equal_state_machine_v1_2_and_asyncapi_gap_is_exactly_the_recorded_one(canonical: dict[str, str]):
    sm = json.loads(STATE_MACHINE.read_text())
    assert set(sm["operationEventTypes"]) == OPERATION_EVENT_TYPES and set(sm["workerRunEventTypes"]) == WORKER_RUN_EVENT_TYPES
    registry = OPERATION_EVENT_TYPES | WORKER_RUN_EVENT_TYPES
    assert set(canonical) <= registry, "AsyncAPI models an event type that the registry does not know"
    assert registry - set(canonical) == LISTED_BUT_NOT_MODELLED, "the AsyncAPI/State Machine gap changed: update G-56 and this test deliberately"


@pytest.mark.parametrize("full", [False, True], ids=["minimal", "all-optionals"])
def test_every_canonical_event_type_builds_a_valid_cloudevent(asyncapi: dict[str, Any], canonical: dict[str, str], full: bool):
    assert len(canonical) == 14 + 22  # all canonical Operation and WorkerRun messages are exercised, none skipped silently
    for short, pointer in sorted(canonical.items()):
        built = envelope(short, aggregate_of(short), full=full)
        errors = sorted(validator(asyncapi, pointer).iter_errors(built), key=str)
        assert not errors, f"{short}: {[e.message for e in errors][:3]}"
        assert built["type"] == event_type_name(short, 1) and "eventType" not in built["data"]


def test_the_schema_really_rejects_deviations(asyncapi: dict[str, Any], canonical: dict[str, str]):
    v = validator(asyncapi, canonical["operation.started"])
    good = envelope("operation.started", "OPERATION", full=True)
    assert v.is_valid(good)
    extra_attribute = {**good, "organizationid": str(uuid4())}  # the previous (non-conforming) shape
    no_dataschema = {k: x for k, x in good.items() if k != "dataschema"}
    no_operation_id = {**good, "data": {k: x for k, x in good["data"].items() if k != "operationId"}}
    bad_actor = {**good, "data": {**good["data"], "actor": {"type": "WORKER_RUN"}}}
    event_type_in_data = {**good, "data": {**good["data"], "eventType": "operation.started"}}
    for broken in (extra_attribute, no_dataschema, no_operation_id, bad_actor, event_type_in_data):
        assert not v.is_valid(broken)


def test_worker_run_events_carry_the_owning_operation_and_derived_subject():
    built = envelope("worker_run.started", "WORKER_RUN", full=False)
    assert built["source"] == "urn:aires:worker-runs" and built["subject"] == f"worker-runs/{built['data']['aggregateId']}"
    assert built["data"]["aggregateType"] == "WORKER_RUN" and built["data"]["operationId"] != built["data"]["aggregateId"]


@pytest.mark.parametrize("aggregate_type, short, version, actor", [
    ("OPERATION", "worker_run.started", 1, "SYSTEM"), ("WORKER_RUN", "operation.started", 1, "SYSTEM"), ("OPERATION", "operation.unknown", 1, "SYSTEM"),
    ("OPERATION", "operation.started", 2, "SYSTEM"), ("OPERATION", "operation.started", 1, "WORKER_RUN"), ("PLAN", "operation.started", 1, "SYSTEM")])
def test_unknown_identity_fails_closed(aggregate_type: str, short: str, version: int, actor: str):
    with pytest.raises(ValueError):
        build_envelope(aggregate_type=aggregate_type, aggregate_id=uuid4(), event_id=uuid4(), sequence=1, version=1, occurred_at=utc_now(),
                       organization_id=uuid4(), project_id=uuid4(), operation_id=uuid4(), event_type=short, schema_version=version, actor_type=actor,
                       actor_id=None, correlation_id=uuid4(), causation_id=None, reason_code=None, from_status=None, to_status=None, details={}, refs=())
