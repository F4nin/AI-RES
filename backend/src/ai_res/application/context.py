"""Compose version readers without coupling the context module to domain peers."""
from collections.abc import Mapping
from types import MappingProxyType

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.artifacts.version_metadata import ArtifactVersionMetadataReader
from ai_res.modules.context.types import ContextItemKind
from ai_res.modules.requirements.version_metadata import RequirementVersionMetadataReader
from ai_res.modules.sources.version_metadata import SourceVersionMetadataReader
from ai_res.platform.version_metadata import VersionMetadataPort


def context_resolvers(session: AsyncSession) -> Mapping[ContextItemKind, VersionMetadataPort]:
    """Readers share the caller's authorized UoW and never open transactions themselves."""
    return MappingProxyType({
        ContextItemKind.REQUIREMENT_VERSION: RequirementVersionMetadataReader(session),
        ContextItemKind.SOURCE_VERSION: SourceVersionMetadataReader(session),
        ContextItemKind.ARTIFACT_VERSION: ArtifactVersionMetadataReader(session),
    })
