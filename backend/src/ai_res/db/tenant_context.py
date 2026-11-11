"""Transaction-local tenant context (Blueprint §7.3, Strategy §3.2).

Applied only AFTER server-side authentication and Policy Engine authorization, once per transaction, via set_config(name, value, true)
with bind parameters. Never session-level SET. RLS policies read it with NULLIF(current_setting(name, true), '')::uuid, so a missing or
empty value matches no rows (default deny). RLS is defense-in-depth, not a replacement for the Policy Engine.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

ORGANIZATION_SETTING = "app.organization_id"
PROJECT_SETTING = "app.project_id"
_SET = text("SELECT set_config(:name, :value, true)")


async def set_tenant_context(session: AsyncSession | AsyncConnection, organization_id: UUID, project_id: UUID | None = None) -> None:
    """Must run inside the open transaction. `project_id=None` leaves the project scope empty (organization-scoped access only)."""
    if not isinstance(organization_id, UUID) or (project_id is not None and not isinstance(project_id, UUID)):
        raise TypeError("tenant context identifiers must be UUID instances")  # never coerce arbitrary strings into a security context
    await session.execute(_SET, {"name": ORGANIZATION_SETTING, "value": str(organization_id)})
    await session.execute(_SET, {"name": PROJECT_SETTING, "value": "" if project_id is None else str(project_id)})
