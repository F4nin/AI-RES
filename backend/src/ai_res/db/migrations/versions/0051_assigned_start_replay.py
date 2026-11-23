"""Require a tenant-bound, audited approval for replaying an assigned Start.

Revision ID: a47ca6b2015f
Revises: de184e3c4a21
"""
from alembic import op

revision: str = "a47ca6b2015f"
down_revision: str | None = "de184e3c4a21"
branch_labels = None
depends_on = None

_INSPECT = "audit.inspect_assigned_start_replay(uuid)"
_REPLAY = "audit.approve_assigned_start_replay(uuid,uuid,integer,uuid,uuid,uuid,uuid)"


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION audit.guard_assigned_start_quarantine() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        BEGIN
            IF current_user <> 'ai_res_owner' AND OLD.status='QUARANTINED'
              AND OLD.destination='orchestration.operation-start'
              AND (OLD.envelope #> '{data,refs}') @> '[{"resourceType":"OPERATION_EXECUTION_ASSIGNMENT"}]'::jsonb
            THEN
                RAISE EXCEPTION 'assigned Start requires audited replay approval' USING ERRCODE='insufficient_privilege';
            END IF;
            RETURN NEW;
        END $f$;
        REVOKE EXECUTE ON FUNCTION audit.guard_assigned_start_quarantine() FROM PUBLIC;
        CREATE TRIGGER trg_assigned_start_quarantine BEFORE UPDATE ON audit.outbox_events
            FOR EACH ROW EXECUTE FUNCTION audit.guard_assigned_start_quarantine();
    """)
    op.execute("""
        CREATE FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid)
        RETURNS TABLE(event_id uuid, replay_count integer)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT e.event_id,e.replay_count
            FROM audit.outbox_events e
            JOIN platform.operation_execution_assignments a
              ON (a.organization_id,a.project_id,a.operation_id)=(e.organization_id,e.project_id,e.aggregate_id)
            JOIN operations.operations o
              ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
            WHERE e.aggregate_id=operation_ref AND e.aggregate_type='OPERATION' AND e.aggregate_sequence=1
              AND e.event_type='operation.accepted' AND e.destination='orchestration.operation-start'
              AND e.status='QUARANTINED' AND a.revoked_at IS NULL
              AND (o.status='ACCEPTED' OR a.workflow_run_id IS NOT NULL)
              AND e.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
              AND e.project_id=NULLIF(current_setting('app.project_id',true),'')::uuid
              AND (e.envelope #> '{data,refs}') @>
                jsonb_build_array(jsonb_build_object('resourceType','OPERATION_EXECUTION_ASSIGNMENT','resourceId',a.id::text))
        $f$;
    """)
    op.execute("""
        CREATE FUNCTION audit.approve_assigned_start_replay(
            operation_ref uuid, event_ref uuid, expected_count integer, actor_ref uuid, session_ref uuid, request_ref uuid, audit_ref uuid
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
        DECLARE
            org uuid := NULLIF(current_setting('app.organization_id',true),'')::uuid;
            prj uuid := NULLIF(current_setting('app.project_id',true),'')::uuid;
            assignment_ref uuid;
        BEGIN
            PERFORM 1 FROM organization.memberships m
            WHERE (m.organization_id,m.user_id)=(org,actor_ref) FOR SHARE;
            IF EXISTS (
                SELECT 1 FROM organization.memberships m
                WHERE (m.organization_id,m.user_id)=(org,actor_ref) AND m.status<>'ACTIVE'
            ) THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM iam.users u
            WHERE (u.organization_id,u.id)=(org,actor_ref) AND u.status='ACTIVE' FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM project.project_memberships m
                WHERE m.organization_id=org AND m.project_id=prj AND m.user_id=actor_ref
                  AND m.role_code='PROJECT_ADMIN' AND m.status='ACTIVE'
                FOR SHARE
            ) THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM iam.sessions s
            WHERE (s.organization_id,s.user_id,s.id)=(org,actor_ref,session_ref)
              AND s.revoked_at IS NULL AND s.mfa_verified_at IS NOT NULL
              AND s.idle_expires_at>clock_timestamp() AND s.absolute_expires_at>clock_timestamp() FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            SELECT a.id INTO assignment_ref FROM platform.operation_execution_assignments a
            WHERE (a.organization_id,a.project_id,a.operation_id)=(org,prj,operation_ref)
              AND a.revoked_at IS NULL FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM operations.operations o
            WHERE (o.organization_id,o.project_id,o.id)=(org,prj,operation_ref)
            FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM audit.outbox_events e
            WHERE (e.organization_id,e.project_id,e.aggregate_id)=(org,prj,operation_ref)
              AND e.event_id=event_ref AND e.destination='orchestration.operation-start'
              AND e.status='QUARANTINED' AND e.replay_count=expected_count
            FOR UPDATE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            UPDATE audit.outbox_events e
            SET status='PENDING', available_at=now(), attempt_count=0, replay_count=e.replay_count+1
            FROM audit.inspect_assigned_start_replay(operation_ref) visible
            WHERE (e.organization_id,e.project_id,e.aggregate_id)=(org,prj,operation_ref)
              AND e.event_id=event_ref AND e.event_id=visible.event_id
              AND e.destination='orchestration.operation-start' AND e.status='QUARANTINED'
              AND e.replay_count=expected_count AND e.replay_count=visible.replay_count
              AND EXISTS (
                SELECT 1 FROM iam.sessions s WHERE s.id=session_ref
                  AND s.idle_expires_at>clock_timestamp() AND s.absolute_expires_at>clock_timestamp()
              );
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            INSERT INTO audit.audit_events(
                id,organization_id,project_id,occurred_at,actor_type,actor_id,action,object_type,object_id,result,correlation_id,details
            ) VALUES (
                audit_ref,org,prj,clock_timestamp(),'USER',actor_ref,'OPERATION_START_REPLAY_APPROVED','OPERATION',
                operation_ref,'SUCCEEDED',request_ref,
                jsonb_build_object('eventId',event_ref,'assignmentId',assignment_ref,'replayCount',expected_count+1)
            );
            RETURN true;
        END $f$;
    """)
    for signature in (_INSPECT, _REPLAY):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO ai_res_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve replay approval and audit.")
