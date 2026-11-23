"""Record successful authorization of a bound cancellation signal.

Revision ID: 798e2a4f3d60
Revises: 7dcb4f29a2e1
"""
from alembic import op

revision: str = "798e2a4f3d60"
down_revision: str | None = "7dcb4f29a2e1"
branch_labels = None
depends_on = None

_PREDICATE = """(
    (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST') AND action IS NULL)
    OR (reason='AUTHORIZED' AND action IN ('AUTHORIZE_START','REGISTER_TASK','CHECK_TASK',
        'AUTHORIZE_RECONCILIATION_DESCRIBE','AUTHORIZE_BOUND_STATUS','AUTHORIZE_BOUND_CANCEL'))
) IS TRUE"""


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE platform.platform_auth_events
        DROP CONSTRAINT ck_platform_auth_reason,
        ADD CONSTRAINT ck_platform_auth_reason CHECK ({_PREDICATE})
    """)
    op.execute(f"ALTER POLICY p_platform_auth_events_insert ON platform.platform_auth_events WITH CHECK ({_PREDICATE})")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve the cancellation authorization audit.")
