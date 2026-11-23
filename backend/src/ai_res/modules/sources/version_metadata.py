"""Source-owned checksum access; originals and locators stay inside the domain."""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadata


class SourceVersionMetadataReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, version_id: UUID, organization_id: UUID, project_id: UUID) -> VersionMetadata:
        return (await self.resolve_all((version_id,), organization_id, project_id))[0]

    async def resolve_all(self, version_ids: Sequence[UUID], organization_id: UUID, project_id: UUID) -> tuple[VersionMetadata, ...]:
        if not version_ids:
            return ()
        rows = (await self._session.execute(text(
            "SELECT id,source_id,version_number,checksum_sha256 FROM sources.source_versions "
            "WHERE id=ANY(:ids) AND organization_id=:o AND project_id=:p"),
            {"ids": list(set(version_ids)), "o": organization_id, "p": project_id})).mappings()
        by_id = {row["id"]: VersionMetadata(row["source_id"], int(row["version_number"]), bytes(row["checksum_sha256"]).hex()) for row in rows}
        try:
            return tuple(by_id[version] for version in version_ids)
        except KeyError:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.") from None
