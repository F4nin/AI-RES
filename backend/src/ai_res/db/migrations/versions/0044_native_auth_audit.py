"""Correlate successful native authorization without storing request or token data.

Revision ID: de41cebc90f2
Revises: 972e162ebb42
"""
from alembic import op

revision: str = "de41cebc90f2"
down_revision: str | None = "972e162ebb42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.platform_auth_events ADD COLUMN action text,
        DROP CONSTRAINT ck_platform_auth_reason,
        ADD CONSTRAINT ck_platform_auth_reason CHECK ((
            (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST') AND action IS NULL)
            OR (reason='AUTHORIZED' AND action IN ('AUTHORIZE_START','REGISTER_TASK','CHECK_TASK'))
        ) IS TRUE)
    """)
    op.execute("""
        ALTER POLICY p_platform_auth_events_insert ON platform.platform_auth_events WITH CHECK ((
            (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST') AND action IS NULL)
            OR (reason='AUTHORIZED' AND action IN ('AUTHORIZE_START','REGISTER_TASK','CHECK_TASK'))
        ) IS TRUE)
    """)
    op.execute("GRANT INSERT(action) ON platform.platform_auth_events TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would change security audit history.")
