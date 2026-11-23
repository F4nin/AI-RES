"""Record possible native delivery before authorizing an assigned Start.

Revision ID: de184e3c4a21
Revises: 798e2a4f3d60
"""
from alembic import op

revision: str = "de184e3c4a21"
down_revision: str | None = "798e2a4f3d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.operation_execution_assignments
            ADD COLUMN start_admitted boolean NOT NULL DEFAULT true;
        ALTER TABLE platform.operation_execution_assignments
            ALTER COLUMN start_admitted SET DEFAULT false;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION platform.keep_operation_assignment_binding() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        BEGIN
            IF OLD.revoked_at IS NOT NULL
                OR (OLD.workflow_run_id IS NOT NULL AND NEW.workflow_run_id IS DISTINCT FROM OLD.workflow_run_id)
                OR (OLD.start_admitted AND NOT NEW.start_admitted)
            THEN
                RAISE EXCEPTION 'operation assignment is immutable after binding/revocation' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $f$
    """)
    op.execute("GRANT UPDATE(start_admitted) ON platform.operation_execution_assignments TO ai_res_api_group")
    op.execute("""
        CREATE OR REPLACE FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major int, digest bytea)
        RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.id=aid AND a.workflow_id=wid AND a.workflow_type=wtype AND a.namespace=ns AND a.task_queue=queue
                  AND a.workflow_contract_version=major AND a.input_digest=digest AND a.revoked_at IS NULL
                  AND a.start_admitted AND a.workflow_run_id IS NULL AND o.status='ACCEPTED' AND a.task_queue='ai-res-manager'
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


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve the durable Start admission fence.")
