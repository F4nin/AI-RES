"""S19 immutable ref manifest: deterministic bytes, strict shape, no caller content."""
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from typing import Any
from uuid import UUID

import pytest

from ai_res.modules.context.manifest import ContextManifest
from ai_res.modules.context.types import ContextItemKind, ContextRef, ResolvedRef

ORG = UUID("10000000-0000-0000-0000-000000000001")
PROJECT = UUID("20000000-0000-0000-0000-000000000001")
VERSION = UUID("30000000-0000-0000-0000-000000000001")
OBJECT = UUID("40000000-0000-0000-0000-000000000001")


def item(kind: ContextItemKind = ContextItemKind.REQUIREMENT_VERSION) -> ResolvedRef:
    return ResolvedRef(ContextRef(kind, VERSION), OBJECT, 1, "a1" * 32)


def test_manifest_has_a_pinned_ref_only_shape_and_canonical_content_hash() -> None:
    manifest = ContextManifest(ORG, PROJECT, (item(),))
    expected = {
        "schemaVersion": "1.0", "builderVersion": "explicit-refs-v1", "organizationId": str(ORG), "projectId": str(PROJECT),
        "items": [{"kind": "REQUIREMENT_VERSION", "versionId": str(VERSION), "objectId": str(OBJECT), "versionNumber": 1, "contentDigest": "a1" * 32}],
    }
    assert manifest.to_dict() == expected
    expected_bytes = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert manifest.content_hash == hashlib.sha256(expected_bytes).hexdigest()
    assert ContextManifest.from_dict(expected) == manifest


def test_reordering_refs_cannot_change_manifest_or_hash() -> None:
    refs = tuple(item(kind) for kind in ContextItemKind)
    first = ContextManifest(ORG, PROJECT, refs)
    second = ContextManifest(ORG, PROJECT, tuple(reversed(refs)))
    assert first.items == second.items
    assert first.to_dict() == second.to_dict()
    assert first.content_hash == second.content_hash
    assert [ref.ref.kind.value for ref in first.items] == sorted(kind.value for kind in ContextItemKind)


@pytest.mark.parametrize("changed", [
    {"object_id": PROJECT}, {"version_number": 2}, {"content_digest": "b2" * 32},
    {"ref": ContextRef(ContextItemKind.REQUIREMENT_VERSION, PROJECT)}, {"ref": ContextRef(ContextItemKind.SOURCE_VERSION, VERSION)},
])
def test_every_resolved_ref_component_is_bound_to_hash(changed: dict[str, Any]) -> None:
    original = ContextManifest(ORG, PROJECT, (item(),))
    assert ContextManifest(ORG, PROJECT, (replace(item(), **changed),)).content_hash != original.content_hash


def test_tenant_is_bound_to_hash() -> None:
    original = ContextManifest(ORG, PROJECT, (item(),))
    assert replace(original, organization_id=PROJECT).content_hash != original.content_hash
    assert replace(original, project_id=ORG).content_hash != original.content_hash


def test_exported_dict_is_detached_from_frozen_manifest() -> None:
    manifest = ContextManifest(ORG, PROJECT, (item(),))
    before = manifest.content_hash
    exported = manifest.to_dict()
    exported["items"][0]["contentDigest"] = "b2" * 32
    exported["items"].append({"text": "untrusted"})
    assert manifest.content_hash == before
    assert manifest.to_dict()["items"] == [item_dict()]
    with pytest.raises(FrozenInstanceError):
        manifest.project_id = ORG  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        manifest.items[0].version_number = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        manifest.items[0].ref.version_id = PROJECT  # type: ignore[misc]


def item_dict() -> dict[str, Any]:
    return {"kind": "REQUIREMENT_VERSION", "versionId": str(VERSION), "objectId": str(OBJECT), "versionNumber": 1, "contentDigest": "a1" * 32}


@pytest.mark.parametrize("changes", [
    {"kind": "REQUIREMENT_VERSION"}, {"kind": "RULE_VERSION"}, {"kind": None}, {"version_id": str(VERSION)}, {"version_id": None},
])
def test_context_ref_requires_typed_kind_and_uuid(changes: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"kind": ContextItemKind.REQUIREMENT_VERSION, "version_id": VERSION}
    fields.update(changes)
    with pytest.raises(ValueError):
        ContextRef(**fields)


@pytest.mark.parametrize("changes", [
    {"ref": None}, {"object_id": str(OBJECT)}, {"object_id": None}, {"version_number": True}, {"version_number": False},
    {"version_number": 0}, {"version_number": -1}, {"version_number": 1.0}, {"version_number": "1"},
    {"content_digest": "a" * 63}, {"content_digest": "a" * 65}, {"content_digest": "g1" * 32}, {"content_digest": None},
])
def test_resolved_refs_reject_invalid_server_metadata(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(item(), **changes)


def test_uppercase_hex_is_canonicalized() -> None:
    original = item()
    assert replace(original, content_digest=original.content_digest.upper()) == original


@pytest.mark.parametrize("changes", [
    {"organization_id": str(ORG)}, {"project_id": str(PROJECT)}, {"items": ()}, {"items": []}, {"items": [item()]},
    {"items": (item(), item())}, {"items": (None,)},
])
def test_manifest_rejects_empty_duplicate_or_mutable_items(changes: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"organization_id": ORG, "project_id": PROJECT, "items": (item(),)}
    fields.update(changes)
    with pytest.raises(ValueError):
        ContextManifest(**fields)


@pytest.mark.parametrize("changes", [
    {"schemaVersion": "2.0"}, {"schemaVersion": "latest"}, {"schemaVersion": 1}, {"builderVersion": "other"},
    {"organizationId": "invalid"}, {"organizationId": ORG}, {"projectId": None}, {"items": []}, {"items": ()},
    {"items": [None]}, {"text": "caller text must not enter"}, {"provenance": {"password": "must not enter"}},
])
def test_from_dict_rejects_untrusted_envelope(changes: dict[str, Any]) -> None:
    payload = ContextManifest(ORG, PROJECT, (item(),)).to_dict()
    payload.update(changes)
    with pytest.raises(ValueError):
        ContextManifest.from_dict(payload)


@pytest.mark.parametrize("changes", [
    {"kind": "RULE_VERSION"}, {"versionId": "not-a-uuid"}, {"versionId": VERSION}, {"objectId": False},
    {"versionNumber": True}, {"contentDigest": "z" * 64}, {"locator": {"text": "must not enter"}}, {"provenance": {"unsafe": "must not enter"}},
])
def test_from_dict_rejects_untrusted_ref_fields(changes: dict[str, Any]) -> None:
    payload = ContextManifest(ORG, PROJECT, (item(),)).to_dict()
    payload["items"][0].update(changes)
    with pytest.raises(ValueError):
        ContextManifest.from_dict(payload)


@pytest.mark.parametrize("field", ["schemaVersion", "builderVersion", "organizationId", "projectId", "items"])
def test_from_dict_requires_every_manifest_field(field: str) -> None:
    payload = ContextManifest(ORG, PROJECT, (item(),)).to_dict()
    del payload[field]
    with pytest.raises(ValueError):
        ContextManifest.from_dict(payload)


@pytest.mark.parametrize("field", ["kind", "versionId", "objectId", "versionNumber", "contentDigest"])
def test_from_dict_requires_every_ref_field(field: str) -> None:
    payload = ContextManifest(ORG, PROJECT, (item(),)).to_dict()
    del payload["items"][0][field]
    with pytest.raises(ValueError):
        ContextManifest.from_dict(payload)


@pytest.mark.parametrize("payload", [None, [], "untrusted", 1, True])
def test_from_dict_rejects_non_objects_without_echoing_input(payload: Any) -> None:
    with pytest.raises(ValueError) as caught:
        ContextManifest.from_dict(payload)
    assert "untrusted" not in str(caught.value)
