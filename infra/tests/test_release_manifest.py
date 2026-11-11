import json
from pathlib import Path

import jsonschema
import release_manifest as rm

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "releases" / "release-manifest.schema.json").read_text())
D = "sha256:" + "b" * 64
MODEL = {"services": {"postgres": {"image": f"postgres:16.15-bookworm@{D}"}, "api": {"image": "ai-res/api:dev"}}}


def test_third_party_has_digest_and_built_does_not(tmp_path):
    m = rm.build(MODEL, "x", "a" * 40, False, tmp_path)
    by = {s["name"]: s for s in m["services"]}
    assert by["postgres"]["digest"] == D and by["postgres"]["origin"] == "third-party" and by["postgres"]["image"] == "postgres:16.15-bookworm"
    assert by["api"]["digest"] is None and by["api"]["origin"] == "built"
    assert all(s["signature_verified"] is False for s in m["services"])


def test_manifest_contains_no_secret_like_keys_and_matches_schema_required_fields(tmp_path):
    m = rm.build(MODEL, "x", "a" * 40, True, tmp_path)
    assert set(SCHEMA["required"]) <= set(m)
    assert m["release_id"].endswith("-dirty") and not any("secret" in k or "password" in k for k in json.dumps(m).lower().split('"'))
    assert set(m) <= set(SCHEMA["properties"])


def test_sbom_hash_recorded_when_present(tmp_path):
    (tmp_path / "ai-res_api_dev.spdx.json").write_text("{}")
    m = rm.build(MODEL, "x", None, False, tmp_path)
    assert {s["name"]: s["sbom_sha256"] for s in m["services"]}["api"] is not None
    assert m["source_commit"] is None


def test_generated_manifest_validates_against_the_schema(tmp_path):
    for dirty, commit in ((True, "a" * 40), (False, None)):
        jsonschema.validate(rm.build(MODEL, "x", commit, dirty, tmp_path), SCHEMA)


def test_schema_rejects_signature_claims_and_unknown_fields(tmp_path):
    import pytest

    m = rm.build(MODEL, "x", "a" * 40, False, tmp_path)
    m["services"][0]["signature_verified"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(m, SCHEMA)
    m = rm.build(MODEL, "x", "a" * 40, False, tmp_path)
    m["secrets"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(m, SCHEMA)
