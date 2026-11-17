"""Pure, immutable exact-version references; no caller text is part of this model."""
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

_DIGEST = re.compile(r"[0-9a-fA-F]{64}\Z")


class ContextItemKind(StrEnum):
    REQUIREMENT_VERSION = "REQUIREMENT_VERSION"
    SOURCE_VERSION = "SOURCE_VERSION"
    ARTIFACT_VERSION = "ARTIFACT_VERSION"


@dataclass(frozen=True, slots=True)
class ContextRef:
    kind: ContextItemKind
    version_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ContextItemKind) or not isinstance(self.version_id, UUID):
            raise ValueError("context reference requires a typed kind and version identifier")


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    """Metadata resolved by the server from the authorized exact version."""

    ref: ContextRef
    object_id: UUID
    version_number: int
    content_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.ref, ContextRef) or not isinstance(self.object_id, UUID):
            raise ValueError("resolved reference requires a typed reference and object identifier")
        if type(self.version_number) is not int or self.version_number <= 0:
            raise ValueError("version number must be a positive integer")
        if not isinstance(self.content_digest, str) or _DIGEST.fullmatch(self.content_digest) is None:
            raise ValueError("content digest must be a SHA-256 hexadecimal value")
        object.__setattr__(self, "content_digest", self.content_digest.lower())
