"""Source-owned checksum access; originals and locators stay inside the domain."""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadata


class SourceVersionMetadataReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, version_id: UUID, organization_id: UUID, project_id: UUID) -> VersionMetadata:
        row = (await self._session.execute(text(
            "SELECT source_id,version_number,checksum_sha256 FROM sources.source_versions "
            "WHERE id=:i AND organization_id=:o AND project_id=:p"),
            {"i": version_id, "o": organization_id, "p": project_id})).mappings().first()
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        return VersionMetadata(row["source_id"], int(row["version_number"]), bytes(row["checksum_sha256"]).hex())
