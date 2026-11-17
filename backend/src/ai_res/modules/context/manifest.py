"""Versioned ref-only manifest with canonical ordering and SHA-256 content identity."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Self
from uuid import UUID

from ai_res.modules.context.types import ContextItemKind, ContextRef, ResolvedRef

SCHEMA_VERSION = "1.0"
BUILDER_VERSION = "explicit-refs-v1"
_MANIFEST_KEYS = frozenset({"schemaVersion", "builderVersion", "organizationId", "projectId", "items"})
_ITEM_KEYS = frozenset({"kind", "versionId", "objectId", "versionNumber", "contentDigest"})


def _identifier(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("manifest identifier must be a UUID string")
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("invalid manifest identifier") from None


def _resolved_item(value: object) -> ResolvedRef:
    if not isinstance(value, dict) or value.keys() != _ITEM_KEYS:
        raise ValueError("invalid manifest item fields")
    if not isinstance(value["kind"], str):
        raise ValueError("invalid manifest item kind")
    try:
        kind = ContextItemKind(value["kind"])
    except ValueError:
        raise ValueError("unsupported manifest item kind") from None
    return ResolvedRef(
        ContextRef(kind, _identifier(value["versionId"])), _identifier(value["objectId"]), value["versionNumber"], value["contentDigest"],
    )


@dataclass(frozen=True, slots=True)
class ContextManifest:
    organization_id: UUID
    project_id: UUID
    items: tuple[ResolvedRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.organization_id, UUID) or not isinstance(self.project_id, UUID):
            raise ValueError("manifest scope requires UUID identifiers")
        if not isinstance(self.items, tuple) or not self.items or any(not isinstance(item, ResolvedRef) for item in self.items):
            raise ValueError("manifest requires a nonempty tuple of resolved references")
        if len({item.ref for item in self.items}) != len(self.items):
            raise ValueError("manifest references must be unique")
        object.__setattr__(self, "items", tuple(sorted(self.items, key=lambda item: (item.ref.kind.value, str(item.ref.version_id)))))

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON object; mutation cannot change the sealed value."""
        return {
            "schemaVersion": SCHEMA_VERSION,
            "builderVersion": BUILDER_VERSION,
            "organizationId": str(self.organization_id),
            "projectId": str(self.project_id),
            "items": [{
                "kind": item.ref.kind.value,
                "versionId": str(item.ref.version_id),
                "objectId": str(item.object_id),
                "versionNumber": item.version_number,
                "contentDigest": item.content_digest,
            } for item in self.items],
        }

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def from_dict(cls, value: object) -> Self:
        """Reject unsupported versions, extra fields and malformed refs without echoing data."""
        if not isinstance(value, dict) or value.keys() != _MANIFEST_KEYS:
            raise ValueError("invalid context manifest fields")
        if value["schemaVersion"] != SCHEMA_VERSION or value["builderVersion"] != BUILDER_VERSION:
            raise ValueError("unsupported context manifest version")
        if not isinstance(value["items"], list):
            raise ValueError("manifest items must be an array")
        return cls(_identifier(value["organizationId"]), _identifier(value["projectId"]), tuple(_resolved_item(item) for item in value["items"]))
