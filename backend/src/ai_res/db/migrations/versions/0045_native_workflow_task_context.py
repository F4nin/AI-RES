"""Narrow metadata for validating the commands of an issued Workflow Task.

Revision ID: 44a7b39ee210
Revises: de41cebc90f2
"""
from alembic import op

revision: str = "44a7b39ee210"
down_revision: str | None = "de41cebc90f2"
branch_labels = None
depends_on = None

_CONTEXT = "platform.bound_workflow_task_context(uuid,uuid,text,text,bytea)"


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION platform.bound_workflow_task_context(oid uuid, rid uuid, ns text, q text, digest bytea)
        RETURNS TABLE(assignment_id uuid, workflow_type text, workflow_contract_version integer)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT a.id,a.workflow_type,a.workflow_contract_version
            FROM platform.operation_execution_assignments a
            JOIN platform.task_issuance_receipts r ON r.operation_id=a.operation_id AND r.workflow_run_id=a.workflow_run_id
            WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.task_queue=q AND a.revoked_at IS NULL
              AND r.token_digest=digest AND r.principal='MANAGER_RUNTIME' AND r.namespace=ns AND r.queue=q AND r.task_kind='WORKFLOW'
              AND a.task_queue='ai-res-manager' AND a.workflow_type IN ('ManagerIntakeWorkflow','PlanExecutionWorkflow')
            FOR SHARE OF a
        $f$
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_CONTEXT} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_CONTEXT} TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove a native authorization boundary.")
