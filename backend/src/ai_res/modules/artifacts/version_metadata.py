"""Artifact-owned checksum access without exporting artifact content."""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadata


class ArtifactVersionMetadataReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, version_id: UUID, organization_id: UUID, project_id: UUID) -> VersionMetadata:
        row = (await self._session.execute(text(
            "SELECT artifact_id,version_number,content_checksum FROM artifacts.artifact_versions "
            "WHERE id=:i AND organization_id=:o AND project_id=:p"),
            {"i": version_id, "o": organization_id, "p": project_id})).mappings().first()
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        return VersionMetadata(row["artifact_id"], int(row["version_number"]), bytes(row["content_checksum"]).hex())
