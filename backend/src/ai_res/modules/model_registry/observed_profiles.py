"""Read-only reference to an observed Flash profile, never an executable model.

Loading lifecycle metadata does not authenticate an owner, approve evidence,
route a model, issue a grant or authorize a candidate probe. Unlike the legacy
executable ModelProfile this reference has no capabilities or usable_at method.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.llm.registry import ProfileIdentityMode as ProfileIdentityMode
from ai_res.llm.registry import ProfileStatus

_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


class ObservedProfileLoadError(ValueError):
    def __init__(self) -> None:
        super().__init__("Observed profile metadata is unsupported or invalid.")


@dataclass(frozen=True, slots=True, repr=False)
class ObservedProfileReference:
    profile_id: UUID
    profile_key: str
    profile_version: int
    identity_mode: ProfileIdentityMode
    provider: str
    provider_model_id: str
    pinned_model_version: None
    status: ProfileStatus
    approved_at: datetime | None
    deprecated_at: datetime | None

    def __post_init__(self) -> None:
        if (not isinstance(self.profile_id, UUID) or not isinstance(self.profile_key, str) or not _KEY.fullmatch(self.profile_key)
                or type(self.profile_version) is not int or not 1 <= self.profile_version <= 2_147_483_647
                or self.identity_mode is not ProfileIdentityMode.FLASH_OBSERVED or self.provider != "deepseek"
                or self.provider_model_id != "deepseek-flash" or self.pinned_model_version is not None
                or not isinstance(self.status, ProfileStatus)):
            raise ObservedProfileLoadError()
        for stamp in (self.approved_at, self.deprecated_at):
            if stamp is not None and (not isinstance(stamp, datetime) or stamp.utcoffset() != timedelta(0)):
                raise ObservedProfileLoadError()
        if self.status is not ProfileStatus.CANDIDATE and self.approved_at is None:
            raise ObservedProfileLoadError()


async def load_observed_profile_reference(session: AsyncSession, profile_id: UUID) -> ObservedProfileReference | None:
    """Parameterized metadata read; a candidate remains a candidate after loading."""
    if not isinstance(profile_id, UUID):
        raise ObservedProfileLoadError()
    row = (await session.execute(text(
        "SELECT id,profile_key,profile_version,identity_mode,provider,provider_model_id,pinned_model_version,status,approved_at,deprecated_at "
        "FROM platform.model_profiles WHERE id=:profile"), {"profile": profile_id})).mappings().first()
    if row is None:
        return None
    try:
        return ObservedProfileReference(row["id"], row["profile_key"], row["profile_version"], ProfileIdentityMode(row["identity_mode"]),
                                        row["provider"], row["provider_model_id"], row["pinned_model_version"], ProfileStatus(row["status"]),
                                        row["approved_at"], row["deprecated_at"])
    except (ValueError, TypeError):
        raise ObservedProfileLoadError() from None
