"""Metadata-only checks for the separate native auth-control caller.

Revision ID: 972e162ebb42
Revises: eaa9f382ce17
"""
from alembic import op

revision: str = "972e162ebb42"
down_revision: str | None = "eaa9f382ce17"
branch_labels = None
depends_on = None

_START = "platform.matches_operation_dispatch(uuid,text,text,text,text,int,bytea)"
_TASK = "platform.matches_bound_manager_task(uuid,uuid,text,text)"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.platform_request_nonces
        DROP CONSTRAINT ck_platform_nonce_issuer,
        ADD CONSTRAINT ck_platform_nonce_issuer CHECK (issuer IN ('MANAGER_RUNTIME','TEMPORAL_AUTH_CONTROL'))
    """)
    op.execute("""
        CREATE FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major int, digest bytea)
        RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.id=aid AND a.workflow_id=wid AND a.workflow_type=wtype AND a.namespace=ns AND a.task_queue=queue
                  AND a.workflow_contract_version=major AND a.input_digest=digest AND a.revoked_at IS NULL
                  AND a.workflow_run_id IS NULL AND o.status='ACCEPTED' AND a.task_queue='ai-res-manager'
                  AND ((o.operation_type='MANAGER_MESSAGE' AND a.workflow_type='ManagerIntakeWorkflow')
                    OR (o.operation_type='PLAN_EXECUTION' AND a.workflow_type='PlanExecutionWorkflow'))
                  AND EXISTS (
                      SELECT 1 FROM audit.outbox_events e WHERE e.aggregate_id=o.id AND e.organization_id=o.organization_id
                        AND e.project_id=o.project_id AND e.aggregate_type='OPERATION'
                        AND e.event_type='operation.accepted' AND e.destination='orchestration.operation-start'
                        AND e.status IN ('PENDING','IN_FLIGHT')
                        AND e.envelope #> '{data,refs}' @> jsonb_build_array(
                            jsonb_build_object('resourceType','OPERATION_EXECUTION_ASSIGNMENT','resourceId',a.id::text))
                  )
            )
        $f$
    """)
    op.execute("""
        CREATE FUNCTION platform.matches_bound_manager_task(oid uuid, rid uuid, ns text, queue text)
        RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.task_queue=queue
                  AND a.task_queue='ai-res-manager' AND a.workflow_type IN ('ManagerIntakeWorkflow','PlanExecutionWorkflow')
                  AND a.revoked_at IS NULL
                FOR SHARE OF a
            )
        $f$
    """)
    for signature in (_START, _TASK):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would change live native authorization.")
