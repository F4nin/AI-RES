"""Immutable version metadata exported by owning domains, without source content."""
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

_DIGEST = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True, slots=True)
class VersionMetadata:
    object_id: UUID
    version_number: int
    content_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, UUID):
            raise ValueError("object identifier must be a UUID")
        if type(self.version_number) is not int or self.version_number <= 0:
            raise ValueError("version number must be a positive integer")
        if not isinstance(self.content_digest, str) or _DIGEST.fullmatch(self.content_digest) is None:
            raise ValueError("content digest must be a SHA-256 hexadecimal value")
        object.__setattr__(self, "content_digest", self.content_digest.lower())


class VersionMetadataPort(Protocol):
    async def resolve(self, version_id: UUID, organization_id: UUID, project_id: UUID) -> VersionMetadata:
        """Resolve an exact scoped version; missing and invisible versions are indistinguishable.

        Callers own authorization and the transaction-local tenant context. This port
        conveys metadata only and grants no access to the underlying content.
        """
