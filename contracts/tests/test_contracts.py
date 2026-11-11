"""S01 negative/positive tests for the contract toolchain. Each validator must fail on a targeted defect."""
import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

import contracts_lib as L

C = L.CONTRACTS
OAS, ASY = C / "openapi/AI_RES_Public_API_v1.3.yaml", C / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"
EX = C / "examples"


def write(tmp, name, data):
    p = tmp / name
    p.write_text(yaml.safe_dump(data) if name.endswith(("yaml", "yml")) else json.dumps(data))
    return p


# ---- positive baseline ----
def test_current_contracts_valid():
    assert L.verify_mirror() == []
    assert L.validate_openapi(OAS) == []
    assert L.validate_asyncapi(ASY) == []
    reg = L.schema_registry()
    assert [e for f in sorted((C / "json-schema").rglob("*.json")) for e in L.validate_jsonschema(f, reg)] == []


# ---- openapi ----
def test_openapi_broken_ref(tmp_path):
    d = L.load(OAS)
    d["paths"]["/me"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/Nope"}
    assert L.validate_openapi(write(tmp_path, "o.yaml", d))


def test_openapi_wrong_type(tmp_path):
    d = L.load(OAS)
    d["paths"] = "not-an-object"
    assert L.validate_openapi(write(tmp_path, "o.yaml", d))


def test_openapi_missing_required_field(tmp_path):
    d = L.load(OAS)
    del d["info"]
    assert L.validate_openapi(write(tmp_path, "o.yaml", d))


# ---- asyncapi ----
def test_asyncapi_unknown_field_and_missing_required(tmp_path):
    d = L.load(ASY)
    d["bogusTopLevel"] = 1
    assert L.validate_asyncapi(write(tmp_path, "a.yaml", d))
    d = L.load(ASY)
    del d["info"]
    assert L.validate_asyncapi(write(tmp_path, "a.yaml", d))


def test_asyncapi_broken_ref(tmp_path):
    d = L.load(ASY)
    name = next(iter(d["components"]["messages"]))
    d["components"]["messages"][name]["payload"] = {"$ref": "#/components/schemas/Missing"}
    assert any("unresolved" in e for e in L.validate_asyncapi(write(tmp_path, "a.yaml", d)))


# ---- json schema ----
def test_jsonschema_broken_ref_and_bad_type(tmp_path):
    meta = "https://json-schema.org/draft/2020-12/schema"
    good = {"$schema": meta, "$defs": {"d": {"type": "string"}}, "properties": {"x": {"$ref": "#/$defs/d"}}}
    assert L.validate_jsonschema(write(tmp_path, "good.json", good), L.schema_registry()) == []  # positive control
    bad = {"$schema": meta, "$defs": {"d": {"type": "string"}}, "properties": {"x": {"$ref": "#/$defs/none"}}}
    assert L.validate_jsonschema(write(tmp_path, "bad.json", bad), L.schema_registry())
    assert L.validate_jsonschema(write(tmp_path, "type.json", {"$schema": meta, "type": "nonsense"}), L.schema_registry())
    assert L.validate_jsonschema(write(tmp_path, "noschema.json", {"type": "object"}), L.schema_registry())  # missing $schema


def test_examples_valid_and_invalid():
    schema = EX / "worker_notice.schema.json"
    reg = L.schema_registry()
    assert L.validate_instance(schema, EX / "valid/worker_notice_blocker.json", reg) == []
    for f in sorted((EX / "invalid").glob("*.json")):
        assert L.validate_instance(schema, f, reg), f.name


# ---- mirror ----
def test_mirror_detects_single_byte_change(tmp_path):
    root = tmp_path / "contracts"
    shutil.copytree(C, root, ignore=shutil.ignore_patterns("node_modules", ".venv", "baseline"))
    target = root / "openapi/AI_RES_Public_API_v1.3.yaml"
    data = bytearray(target.read_bytes())
    data[-1] ^= 0x01
    target.write_bytes(bytes(data))
    errs = L.verify_mirror(contracts=root, repo=L.REPO)
    assert any("openapi" in e for e in errs)


# ---- breaking-change detection ----
def test_breaking_endpoint_removal_and_required_field():
    old = L.load(OAS)
    new = copy.deepcopy(old)
    del new["paths"]["/me"]
    assert any("path removed: /me" in b for b in L.breaking_openapi(old, new))
    new = copy.deepcopy(old)
    op = new["paths"]["/projects"]["post"]
    body = L.deref(op["requestBody"], new)
    schema = body["content"]["application/json"]["schema"]
    schema.setdefault("required", []).append("brandNewRequired")
    schema.setdefault("properties", {})["brandNewRequired"] = {"type": "string"}
    new["paths"]["/projects"]["post"]["requestBody"] = body
    assert any("new required" in b for b in L.breaking_openapi(old, new))


def test_breaking_additive_optional_is_not_breaking():
    old = L.load(OAS)
    new = copy.deepcopy(old)
    new["components"]["schemas"]["__AddedByTest"] = {"type": "object"}
    assert L.breaking_openapi(old, new) == []
    d = L.deref(old["paths"]["/me"]["get"]["responses"]["200"], old)
    sch = d["content"]["application/json"]["schema"]
    sch2 = copy.deepcopy(sch)
    sch2.setdefault("properties", {})["optionalExtra"] = {"type": "string"}
    assert L.schema_breaks(sch, sch2, "response", "x") == []
    assert L.schema_breaks(sch, sch2, "request", "x") == []


def test_breaking_asyncapi_message_removed_and_jsonschema_removed_property():
    old = L.load(ASY)
    new = copy.deepcopy(old)
    del new["components"]["messages"][next(iter(new["components"]["messages"]))]
    assert any("message removed" in b for b in L.breaking_asyncapi(old, new))
    a = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    b = {"type": "object", "properties": {}, "required": []}
    assert L.breaking_jsonschema(a, b)


# ---- overlay (ADR-009) ----
def test_overlay_is_additive_only():
    base = {"paths": {"/a": {"get": {"operationId": "a"}}}}
    merged, errs = L.merge_overlay(base, {"paths": {"/b": {"get": {"operationId": "b"}}}})
    assert errs == [] and "/b" in merged["paths"]
    _, errs = L.merge_overlay(base, {"paths": {"/a": {"get": {"operationId": "changed"}}}})
    assert errs


# ---- spectral rules (AI RES) ----
def test_spectral_rules_flag_bad_contract(tmp_path):
    import cli
    d = L.load(OAS)
    d["paths"]["/projects"]["get"]["parameters"] = [{"name": "offset", "in": "query", "schema": {"type": "integer"}}]
    post = d["paths"]["/projects"]["post"]
    post["parameters"] = []
    post["responses"]["400"] = {"description": "bad", "content": {"application/json": {"schema": {"type": "object"}}}}
    patch = d["paths"]["/projects/{projectId}"]["patch"]
    patch["parameters"] = [p for p in patch.get("parameters", []) if "IfMatch" not in str(p)]
    f = write(tmp_path, "bad.yaml", d)
    codes = {c for c, _, _ in cli.spectral_findings(f)}
    assert {"aires-no-offset-pagination", "aires-idempotency-key", "aires-problem-details"} <= codes


def test_new_spectral_findings_rejected_against_baseline():
    import cli
    assert cli.cmd_lint_openapi() == []


def test_breaking_worker_schema_defs_property_removed():
    old = L.load(C / "json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json")
    new = copy.deepcopy(old)
    prop = next(iter(new["$defs"]["EvidenceReference"]["properties"]))
    del new["$defs"]["EvidenceReference"]["properties"][prop]
    assert any(prop in b for b in L.breaking_jsonschema(old, new))
    new = copy.deepcopy(old)
    del new["$defs"]["WorkerNotice"]
    assert any("definition removed" in b for b in L.breaking_jsonschema(old, new))
    assert L.breaking_jsonschema(old, copy.deepcopy(old)) == []


def test_breaking_enum_direction():
    a, b = {"type": "string", "enum": ["A", "B"]}, {"type": "string", "enum": ["A"]}
    assert L.schema_breaks(a, b, "request", "x") and not L.schema_breaks(a, b, "response", "x")
    assert L.schema_breaks(b, a, "response", "x") and not L.schema_breaks(b, a, "request", "x")


def test_lint_gate_fails_closed_when_spectral_breaks(monkeypatch):
    import cli
    class R:  # simulated crashed spectral: no stdout, exit 2
        returncode, stdout, stderr = 2, "", "ruleset load error"
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError):
        cli.spectral_findings()
    assert cli.main(["cli", "lint-openapi"]) == 1  # crash is reported as FAIL, not ok


def test_overlay_directory_rules(tmp_path, monkeypatch):
    ext = tmp_path / "openapi" / "extensions"
    ext.mkdir(parents=True)
    monkeypatch.setattr(L, "CONTRACTS", tmp_path)
    (ext / "a.yaml").write_text("")                      # empty overlay
    (ext / "b.json").write_text("{}")                    # stray file type
    _, errs = L.merged_document("openapi", OAS)
    assert any("empty" in e for e in errs) and any("unsupported overlay" in e for e in errs)
    (ext / "a.yaml").write_text("x-status: WORKING\nx-source: [DOC-023]\nsecurity: []\n")
    _, errs = L.merged_document("openapi", OAS)
    assert any("may only extend" in e for e in errs)     # cannot add top-level security


# ---- S07 identity overlay ----
IDENTITY_OVERLAY = C / "openapi/extensions/identity_auth.yaml"


def test_identity_overlay_is_working_and_every_post_is_idempotent_or_explicitly_exempt():
    ov = L.load(IDENTITY_OVERLAY)
    assert ov["x-status"] == "WORKING" and ov["x-source"]
    for path, item in ov["paths"].items():
        for method, op in item.items():
            if method == "post":
                assert len(op.get("x-idempotency-exempt", "")) >= 20, f"{path}: POST without Idempotency-Key needs a written reason"


def test_identity_overlay_cannot_override_canonical_paths(tmp_path):
    doc, errs = L.merged_document("openapi", OAS)
    assert errs == [] and "/auth/login" in doc["paths"] and "/me" in doc["paths"]
    ov = L.load(IDENTITY_OVERLAY)
    _, redefine = L.merge_overlay(L.load(OAS), {"paths": {"/me": {"get": {"operationId": "other"}}}})
    assert redefine and ov  # redefining a canonical operation is an error


def test_identity_login_never_documents_a_session_in_the_body_schema():
    ov = L.load(IDENTITY_OVERLAY)
    props = ov["components"]["schemas"]["SessionInfo"]["properties"]
    assert not {"token", "sessionToken", "session"} & set(props)  # the session secret travels only in the HttpOnly cookie
    assert ov["components"]["schemas"]["LoginRequest"]["properties"]["password"]["writeOnly"] is True
