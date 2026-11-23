"""Let the existing deferred trigger check sequence metadata for the bound Operation.

Revision ID: e694ab2bc7d0
Revises: 13baca8848ec
"""
from collections.abc import Sequence

from alembic import op

revision: str = "e694ab2bc7d0"
down_revision: str | None = "13baca8848ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT(operation_id, aggregate_sequence) ON operations.operation_events TO ai_res_platform_api_group")
    op.execute("""
        CREATE POLICY p_operation_event_sequence_platform ON operations.operation_events FOR SELECT TO ai_res_platform_api_group
        USING (
            operation_id = NULLIF(current_setting('app.platform_operation_id', true), '')::uuid
            AND EXISTS (SELECT 1 FROM operations.operations o WHERE o.id = operation_id)
        )
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve the Platform API privilege boundary.")
