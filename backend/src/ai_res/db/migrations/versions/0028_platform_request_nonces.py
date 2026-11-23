"""Durable, one-use authenticated request receipts for internal Platform API.

Revision ID: 4d8c7b2d61f3
Revises: 6e23a65c9ce0
"""
from collections.abc import Sequence

from alembic import op

revision: str = "4d8c7b2d61f3"
down_revision: str | None = "6e23a65c9ce0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.platform_request_nonces (
            issuer text NOT NULL CONSTRAINT ck_platform_nonce_issuer CHECK (issuer = 'MANAGER_RUNTIME'),
            nonce uuid NOT NULL,
            expires_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT pk_platform_request_nonces PRIMARY KEY (issuer, nonce)
        )
    """)
    op.execute("ALTER TABLE platform.platform_request_nonces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.platform_request_nonces FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_platform_nonces_platform_insert ON platform.platform_request_nonces
        FOR INSERT TO ai_res_platform_api_group WITH CHECK (expires_at > clock_timestamp())
    """)
    op.execute("""
        CREATE POLICY p_platform_nonces_migration ON platform.platform_request_nonces TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    op.execute("GRANT USAGE ON SCHEMA platform TO ai_res_platform_api_group")
    op.execute("GRANT INSERT(issuer, nonce, expires_at) ON platform.platform_request_nonces TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove replay protection receipts.")
