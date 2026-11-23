"""Expose only event metadata consumed by the deferred Outbox integrity check.

Revision ID: 7d13e0bc27f4
Revises: e694ab2bc7d0
"""
from collections.abc import Sequence

from alembic import op

revision: str = "7d13e0bc27f4"
down_revision: str | None = "e694ab2bc7d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT(event_id,event_type,schema_version) ON operations.operation_events TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve the Platform API privilege boundary.")
