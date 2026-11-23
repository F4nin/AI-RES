"""Include the admitted input digest and domain outcome in Workflow Task authorization.

Revision ID: 382befc90d62
Revises: 44a7b39ee210
"""
from alembic import op

revision: str = "382befc90d62"
down_revision: str | None = "44a7b39ee210"
branch_labels = None
depends_on = None

_CONTEXT = "platform.bound_workflow_task_command_binding(uuid,uuid,text,text,bytea)"


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION platform.bound_workflow_task_command_binding(oid uuid, rid uuid, ns text, q text, digest bytea)
        RETURNS TABLE(assignment_id uuid, workflow_type text, workflow_contract_version integer, input_digest bytea, operation_status text)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT c.assignment_id,c.workflow_type,c.workflow_contract_version,a.input_digest,o.status::text
            FROM platform.bound_workflow_task_context(oid,rid,ns,q,digest) c
            JOIN platform.operation_execution_assignments a ON a.id=c.assignment_id
            JOIN operations.operations o ON o.id=a.operation_id AND o.organization_id=a.organization_id AND o.project_id=a.project_id
        $f$
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_CONTEXT} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_CONTEXT} TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove a native authorization boundary.")
