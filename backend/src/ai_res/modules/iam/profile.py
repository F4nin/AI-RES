"""Read model for `GET /me` (OAS getCurrentUser): the caller's own display data and the organization(s) they belong to. Tenant context must be set."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CurrentUserView:
    id: UUID
    display_name: str
    organizations: list[tuple[UUID, str]]


async def read_current_user(s: AsyncSession, organization_id: UUID, user_id: UUID) -> CurrentUserView | None:
    row = (await s.execute(text(
        "SELECT u.display_name, o.name FROM iam.users u JOIN organization.organizations o ON o.id = u.organization_id "
        "WHERE u.organization_id = :o AND u.id = :u AND u.status = 'ACTIVE'"), {"o": organization_id, "u": user_id})).first()
    return None if row is None else CurrentUserView(user_id, row[0], [(organization_id, row[1])])
