"""Authorize a reconciliation observer to describe an exact Manager Run before start ACK.

Revision ID: 13f3c5d9b7a2
Revises: 382befc90d62
"""
from alembic import op

revision: str = "13f3c5d9b7a2"
down_revision: str | None = "382befc90d62"
branch_labels = None
depends_on = None

_DESCRIBE = "platform.matches_reconciliation_describe(uuid,uuid,text)"
_AUDIT_PREDICATE = """(
    (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST') AND action IS NULL)
    OR (reason='AUTHORIZED' AND action IN ('AUTHORIZE_START','REGISTER_TASK','CHECK_TASK','AUTHORIZE_RECONCILIATION_DESCRIBE'))
) IS TRUE"""


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION platform.matches_reconciliation_describe(oid uuid, rid uuid, ns text)
        RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.revoked_at IS NULL
                  AND a.task_queue='ai-res-manager' AND a.workflow_type='ManagerIntakeWorkflow' AND a.workflow_contract_version=1
                  AND o.operation_type='MANAGER_MESSAGE' AND o.status IN ('ACCEPTED','QUEUED')
            )
        $f$
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_DESCRIBE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_DESCRIBE} TO ai_res_platform_api_group")
    op.execute(f"""
        ALTER TABLE platform.platform_auth_events
        DROP CONSTRAINT ck_platform_auth_reason,
        ADD CONSTRAINT ck_platform_auth_reason CHECK ({_AUDIT_PREDICATE})
    """)
    op.execute(f"ALTER POLICY p_platform_auth_events_insert ON platform.platform_auth_events WITH CHECK ({_AUDIT_PREDICATE})")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would change the native authorization audit boundary.")
