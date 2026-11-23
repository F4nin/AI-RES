"""Durable task-issuance metadata, retaining no raw task token (ADR-129).

Revision ID: eaa9f382ce17
Revises: 3f6a0e614b92
"""
from alembic import op

revision: str = "eaa9f382ce17"
down_revision: str | None = "3f6a0e614b92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.task_issuance_receipts (
            token_digest bytea PRIMARY KEY CHECK (octet_length(token_digest)=32),
            principal text NOT NULL,
            namespace text NOT NULL CHECK (namespace ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
            queue text NOT NULL,
            task_kind text NOT NULL,
            operation_id uuid NOT NULL,
            workflow_run_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (principal='MANAGER_RUNTIME' AND queue='ai-res-manager' AND task_kind IN ('WORKFLOW','ACTIVITY'))
                OR (principal='WORKER_RUNTIME' AND queue='ai-res-workers' AND task_kind='ACTIVITY')
            )
        )
    """)
    op.execute("ALTER TABLE platform.task_issuance_receipts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.task_issuance_receipts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_task_issuance_receipts_control ON platform.task_issuance_receipts TO ai_res_platform_api_group
        USING (current_setting('app.platform_action', true) IN ('auth.task_issue','auth.task_check'))
        WITH CHECK (current_setting('app.platform_action', true)='auth.task_issue')
    """)
    op.execute("""
        CREATE POLICY p_task_issuance_receipts_migration ON platform.task_issuance_receipts TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '')='on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '')='on')
    """)
    op.execute("""
        GRANT SELECT(token_digest,principal,namespace,queue,task_kind,operation_id,workflow_run_id),
              INSERT(token_digest,principal,namespace,queue,task_kind,operation_id,workflow_run_id)
        ON platform.task_issuance_receipts TO ai_res_platform_api_group
    """)
    op.execute("""
        CREATE TRIGGER trg_task_issuance_receipts_immutable BEFORE UPDATE OR DELETE ON platform.task_issuance_receipts
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove issuance authority evidence.")
