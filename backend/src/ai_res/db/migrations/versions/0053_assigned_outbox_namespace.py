"""Pin protected Outbox delivery to the namespace of its exact assignment.

Revision ID: 7c4cb218720a
Revises: 4dd4da8ee5c2
"""
from alembic import op

revision = "7c4cb218720a"
down_revision = "4dd4da8ee5c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.operation_execution_assignments
            ADD CONSTRAINT uq_assignment_dispatch_route UNIQUE (organization_id,project_id,operation_id,id,namespace);
        ALTER TABLE audit.outbox_events ADD COLUMN dispatch_assignment_id uuid, ADD COLUMN dispatch_namespace text;
        ALTER TABLE audit.outbox_events
            ADD CONSTRAINT ck_outbox_dispatch_route CHECK (
                (dispatch_assignment_id IS NULL AND dispatch_namespace IS NULL) OR (
                    dispatch_assignment_id IS NOT NULL AND dispatch_namespace IS NOT NULL
                    AND dispatch_namespace ~ '^[a-z0-9][a-z0-9-]{0,62}$'
                    AND aggregate_type='OPERATION'
                    AND ((destination='orchestration.operation-start' AND event_type='operation.accepted' AND aggregate_sequence=1)
                        OR (destination='orchestration.operation-cancel' AND event_type='operation.cancel_requested'))
                    AND jsonb_array_length(jsonb_path_query_array(
                        envelope, '$.data.refs[*] ? (@.resourceType == "OPERATION_EXECUTION_ASSIGNMENT")'))=1
                    AND COALESCE((envelope #> '{data,refs}') @> jsonb_build_array(jsonb_build_object(
                        'resourceType','OPERATION_EXECUTION_ASSIGNMENT','resourceId',dispatch_assignment_id::text)),false)
                )
            ),
            ADD CONSTRAINT fk_outbox_dispatch_route FOREIGN KEY
                (organization_id,project_id,aggregate_id,dispatch_assignment_id,dispatch_namespace)
                REFERENCES platform.operation_execution_assignments(organization_id,project_id,operation_id,id,namespace)
                ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
        SELECT set_config('app.migration_mode','on',true);
        UPDATE audit.outbox_events o
        SET dispatch_assignment_id=a.id, dispatch_namespace=a.namespace
        FROM platform.operation_execution_assignments a
        WHERE (o.organization_id,o.project_id,o.aggregate_id)=(a.organization_id,a.project_id,a.operation_id)
          AND o.aggregate_type='OPERATION' AND a.namespace ~ '^[a-z0-9][a-z0-9-]{0,62}$'
          AND ((o.destination='orchestration.operation-start' AND o.event_type='operation.accepted' AND o.aggregate_sequence=1)
              OR (o.destination='orchestration.operation-cancel' AND o.event_type='operation.cancel_requested'))
          AND jsonb_array_length(jsonb_path_query_array(
                o.envelope, '$.data.refs[*] ? (@.resourceType == "OPERATION_EXECUTION_ASSIGNMENT")'))=1
          AND (o.envelope #> '{data,refs}') @> jsonb_build_array(jsonb_build_object(
                'resourceType','OPERATION_EXECUTION_ASSIGNMENT','resourceId',a.id::text));
        UPDATE audit.outbox_events o
        SET status='QUARANTINED',last_error_code='OUTBOX_ROUTE_UNRESOLVED',lease_owner=NULL,lease_until=NULL
        WHERE o.dispatch_namespace IS NULL AND o.status IN ('PENDING','IN_FLIGHT')
          AND o.destination IN ('orchestration.operation-start','orchestration.operation-cancel')
          AND (o.envelope #> '{data,refs}') @> '[{"resourceType":"OPERATION_EXECUTION_ASSIGNMENT"}]'::jsonb;
        SET CONSTRAINTS audit.fk_outbox_dispatch_route IMMEDIATE;
        SELECT set_config('app.migration_mode','off',true);
        ALTER TABLE audit.outbox_events ADD CONSTRAINT ck_outbox_assigned_route_resolved CHECK (
            dispatch_namespace IS NOT NULL OR status IN ('QUARANTINED','PUBLISHED')
            OR destination NOT IN ('orchestration.operation-start','orchestration.operation-cancel')
            OR NOT COALESCE((envelope #> '{data,refs}') @> '[{"resourceType":"OPERATION_EXECUTION_ASSIGNMENT"}]'::jsonb,false)
        );
        SET CONSTRAINTS audit.fk_outbox_dispatch_route DEFERRED;
        CREATE INDEX ix_outbox_protected_route ON audit.outbox_events(dispatch_namespace,created_at,aggregate_sequence)
            WHERE dispatch_namespace IS NOT NULL AND status IN ('PENDING','IN_FLIGHT');
        CREATE TRIGGER trg_outbox_dispatch_route_immutable BEFORE UPDATE ON audit.outbox_events
            FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('dispatch_assignment_id','dispatch_namespace');
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid)
        RETURNS TABLE(event_id uuid, replay_count integer)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT e.event_id,e.replay_count
            FROM audit.outbox_events e
            JOIN platform.operation_execution_assignments a
              ON (a.organization_id,a.project_id,a.operation_id,a.id,a.namespace)
                =(e.organization_id,e.project_id,e.aggregate_id,e.dispatch_assignment_id,e.dispatch_namespace)
            JOIN operations.operations o
              ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
            WHERE e.aggregate_id=operation_ref AND e.aggregate_type='OPERATION' AND e.aggregate_sequence=1
              AND e.event_type='operation.accepted' AND e.destination='orchestration.operation-start'
              AND e.status='QUARANTINED' AND a.revoked_at IS NULL
              AND (o.status='ACCEPTED' OR a.workflow_run_id IS NOT NULL)
              AND e.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
              AND e.project_id=NULLIF(current_setting('app.project_id',true),'')::uuid
        $f$;
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve the routing of outstanding Outbox intents.")
