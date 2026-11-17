"""Requirement-owned semantic digests for exact immutable versions."""
import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadata


class RequirementVersionMetadataReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, version_id: UUID, organization_id: UUID, project_id: UUID) -> VersionMetadata:
        row = (await self._session.execute(text(
            "SELECT requirement_id,version_number,statement,rationale,requirement_type,declared_type_text,priority,"
            "acceptance_criteria,constraints_info,provenance_refs,change_reason FROM requirements.requirement_versions "
            "WHERE id=:i AND organization_id=:o AND project_id=:p"),
            {"i": version_id, "o": organization_id, "p": project_id})).mappings().first()
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        # Lifecycle metadata can change; the immutable semantic snapshot cannot.
        content = {key: row[key] for key in (
            "statement", "rationale", "requirement_type", "declared_type_text", "priority",
            "acceptance_criteria", "constraints_info", "provenance_refs", "change_reason")}
        digest = hashlib.sha256(canonical_json(content).encode()).hexdigest()
        return VersionMetadata(row["requirement_id"], int(row["version_number"]), digest)
