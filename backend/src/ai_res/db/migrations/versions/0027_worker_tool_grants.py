"""Worker tool authority, scoped to one Run, exact tool/contract and resource.

Revision ID: 6e23a65c9ce0
Revises: c97e3bf386f1
"""
from collections.abc import Sequence

from alembic import op

revision: str = "6e23a65c9ce0"
down_revision: str | None = "c97e3bf386f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE agents.worker_tool_grants (
            id uuid CONSTRAINT pk_worker_tool_grants PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            worker_run_id uuid NOT NULL,
            identity_id uuid NOT NULL,
            environment text NOT NULL,
            tool_id text NOT NULL,
            tool_version text NOT NULL,
            contract_version text NOT NULL,
            operation text NOT NULL,
            resource_type text NOT NULL,
            resource_id uuid NOT NULL,
            classification text NOT NULL,
            permission_scope text NOT NULL,
            allowed_model_profiles text[] NOT NULL,
            budget_ref uuid NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            rate_minute timestamptz,
            rate_count integer NOT NULL DEFAULT 0 CONSTRAINT ck_worker_tool_grant_rate_count CHECK (rate_count >= 0),
            CONSTRAINT ck_worker_tool_grant_rate_window CHECK ((rate_minute IS NULL) = (rate_count = 0)),
            CONSTRAINT fk_worker_tool_grant_run FOREIGN KEY (organization_id, project_id, worker_run_id)
                REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX ix_worker_tool_grants_run ON agents.worker_tool_grants(organization_id, project_id, worker_run_id)")
    op.execute("ALTER TABLE agents.worker_tool_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agents.worker_tool_grants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_worker_tool_grants_tenant ON agents.worker_tool_grants TO ai_res_api_group USING (
            organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
            AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY p_worker_tool_grants_migration ON agents.worker_tool_grants TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    # The execution path can account for calls. Issuance and revocation wiring belong to trusted lifecycle services.
    op.execute("GRANT SELECT, UPDATE(rate_minute, rate_count) ON agents.worker_tool_grants TO ai_res_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove Worker tool grants.")
