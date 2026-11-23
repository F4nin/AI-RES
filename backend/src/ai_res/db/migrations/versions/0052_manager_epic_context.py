"""Issue an immutable, assignment-scoped Epic snapshot for Manager Proposal provenance.

Revision ID: 4dd4da8ee5c2
Revises: a47ca6b2015f
"""
# ruff: noqa: S608 -- fixed migration predicates and identifiers
from alembic import op

revision = "4dd4da8ee5c2"
down_revision = "a47ca6b2015f"
branch_labels = None
depends_on = None

_CAPTURE = "platform.capture_manager_epic_context(uuid,uuid,uuid)"
_MATCH = "platform.manager_epic_context_matches_draft(uuid,uuid)"
_OWNER = "COALESCE(current_setting('app.migration_mode',true),'')='on'"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.manager_epic_context_versions (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            interaction_id uuid NOT NULL,
            operation_id uuid NOT NULL UNIQUE,
            assignment_id uuid NOT NULL REFERENCES platform.operation_execution_assignments(id) ON DELETE RESTRICT,
            workflow_run_id uuid NOT NULL,
            epic_state jsonb NOT NULL CHECK (jsonb_typeof(epic_state)='object'),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (organization_id,project_id,interaction_id,id),
            FOREIGN KEY (organization_id,project_id,interaction_id)
                REFERENCES work.manager_interactions(organization_id,project_id,id) ON DELETE RESTRICT,
            FOREIGN KEY (organization_id,project_id,operation_id)
                REFERENCES operations.operations(organization_id,project_id,id) ON DELETE RESTRICT
        );
        ALTER TABLE platform.manager_epic_context_versions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE platform.manager_epic_context_versions FORCE ROW LEVEL SECURITY;
        CREATE TRIGGER trg_manager_epic_context_immutable BEFORE UPDATE OR DELETE ON platform.manager_epic_context_versions
            FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();
        CREATE TRIGGER trg_manager_epic_context_no_truncate BEFORE TRUNCATE ON platform.manager_epic_context_versions
            FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();
        ALTER TABLE work.manager_proposal_versions ADD COLUMN context_version_id uuid,
            ADD FOREIGN KEY (organization_id,project_id,interaction_id,context_version_id)
                REFERENCES platform.manager_epic_context_versions(organization_id,project_id,interaction_id,id) ON DELETE RESTRICT;
        GRANT INSERT(context_version_id) ON work.manager_proposal_versions TO ai_res_platform_api_group;
    """)
    op.execute(f"""
        CREATE POLICY p_manager_epic_context_owner ON platform.manager_epic_context_versions TO ai_res_owner
            USING ({_OWNER}) WITH CHECK ({_OWNER});
    """)
    op.execute("""
        CREATE FUNCTION platform.lock_manager_epic_context_assignment(oid uuid, expected_action text)
        RETURNS TABLE(assignment_id uuid,workflow_run_id uuid,organization_id uuid,project_id uuid,correlation_id uuid)
        LANGUAGE sql SET search_path=pg_catalog AS $f$
            SELECT a.id,a.workflow_run_id,a.organization_id,a.project_id,a.correlation_id
            FROM platform.operation_execution_assignments a
            WHERE a.operation_id=oid AND a.revoked_at IS NULL AND a.workflow_type='ManagerIntakeWorkflow'
              AND expected_action=ANY(a.allowed_actions) AND expected_action=current_setting('app.platform_action',true)
              AND a.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
              AND a.project_id=NULLIF(current_setting('app.project_id',true),'')::uuid
              AND oid=NULLIF(current_setting('app.platform_operation_id',true),'')::uuid
              AND a.id=NULLIF(current_setting('app.platform_assignment_id',true),'')::uuid
              AND a.workflow_run_id=NULLIF(current_setting('app.platform_workflow_run_id',true),'')::uuid
            FOR SHARE OF a
        $f$;
        REVOKE EXECUTE ON FUNCTION platform.lock_manager_epic_context_assignment(uuid,text) FROM PUBLIC;

        CREATE FUNCTION platform.manager_epic_context_matches_draft(oid uuid,cid uuid)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
        DECLARE
            binding record;
            issued record;
        BEGIN
            SELECT * INTO binding FROM platform.lock_manager_epic_context_assignment(oid,'manager.record_draft');
            IF NOT FOUND THEN RETURN false; END IF;

            PERFORM 1 FROM operations.operations o
            WHERE (o.organization_id,o.project_id,o.id)=(binding.organization_id,binding.project_id,oid)
              AND o.operation_type='MANAGER_MESSAGE' AND o.status IN ('RUNNING','SUCCEEDED')
            FOR NO KEY UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;

            SELECT c.id,c.assignment_id,c.workflow_run_id INTO issued
            FROM platform.manager_epic_context_versions c WHERE c.operation_id=oid;
            IF NOT FOUND THEN RETURN cid IS NULL; END IF;
            RETURN (issued.id,issued.assignment_id,issued.workflow_run_id)
                IS NOT DISTINCT FROM (cid,binding.assignment_id,binding.workflow_run_id);
        END $f$;

        CREATE POLICY p_manager_proposals_context ON work.manager_proposal_versions AS RESTRICTIVE
            FOR INSERT TO ai_res_platform_api_group WITH CHECK (
                platform.manager_epic_context_matches_draft(
                    NULLIF(current_setting('app.platform_operation_id',true),'')::uuid,context_version_id
                )
            );
    """)
    op.execute("""
        CREATE FUNCTION platform.capture_manager_epic_context(oid uuid,aid uuid,rid uuid)
        RETURNS TABLE(context_id uuid,epic_state jsonb)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
        DECLARE
            binding record;
            intake record;
        BEGIN
            SELECT * INTO binding FROM platform.lock_manager_epic_context_assignment(oid,'manager.read_input');
            IF NOT FOUND OR binding.assignment_id IS DISTINCT FROM aid OR binding.workflow_run_id IS DISTINCT FROM rid
            THEN RETURN; END IF;

            SELECT i.id AS interaction_id,i.epic_id,o.row_version INTO intake
            FROM operations.operations o
            JOIN work.manager_interactions i ON (i.organization_id,i.project_id,i.operation_id)=(o.organization_id,o.project_id,o.id)
            WHERE (o.organization_id,o.project_id,o.id)=(binding.organization_id,binding.project_id,oid)
              AND o.operation_type='MANAGER_MESSAGE' AND o.status='RUNNING'
            FOR NO KEY UPDATE OF o;
            IF NOT FOUND THEN RETURN; END IF;

            IF NOT EXISTS (SELECT 1 FROM platform.manager_epic_context_versions c WHERE c.operation_id=oid) THEN
                INSERT INTO platform.manager_epic_context_versions
                    (id,organization_id,project_id,interaction_id,operation_id,assignment_id,workflow_run_id,epic_state)
                SELECT gen_random_uuid(),e.organization_id,e.project_id,intake.interaction_id,oid,aid,rid,
                       jsonb_build_object('epicVersion',e.row_version,'epicStatus',e.status,
                           'operationVersion',intake.row_version,'operationStatus','RUNNING',
                           'questionSequence',COALESCE(q.sequence,0),'hasOpenQuestion',COALESCE(q.is_open,false),
                           'planVersion',p.version_number,'planDecision',p.decision,'taskCounts',COALESCE(t.counts,'{}'::jsonb))
                FROM work.epics e
                LEFT JOIN LATERAL (
                    SELECT j.sequence,j.event_kind='PROPOSED' AS is_open FROM work.manager_question_journal j
                    WHERE (j.organization_id,j.project_id,j.epic_id)=(e.organization_id,e.project_id,e.id)
                    ORDER BY j.sequence DESC LIMIT 1
                ) q ON true
                LEFT JOIN LATERAL (
                    SELECT v.version_number,d.decision FROM work.plans pl
                    JOIN work.plan_versions v ON (v.organization_id,v.project_id,v.plan_id,v.version_number)
                        =(pl.organization_id,pl.project_id,pl.id,pl.last_version)
                    LEFT JOIN governance.plan_version_decisions d ON (d.organization_id,d.project_id,d.plan_version_id)
                        =(v.organization_id,v.project_id,v.id)
                    WHERE (pl.organization_id,pl.project_id,pl.epic_id)=(e.organization_id,e.project_id,e.id)
                ) p ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_object_agg(status,task_count) AS counts FROM (
                        SELECT task.status,count(*) AS task_count FROM work.tasks task
                        WHERE (task.organization_id,task.project_id,task.epic_id)=(e.organization_id,e.project_id,e.id)
                        GROUP BY task.status
                    ) totals
                ) t ON true
                WHERE (e.organization_id,e.project_id,e.id)=(binding.organization_id,binding.project_id,intake.epic_id)
                ON CONFLICT (operation_id) DO NOTHING;
            END IF;
            RETURN QUERY SELECT c.id,c.epic_state FROM platform.manager_epic_context_versions c
            WHERE (c.organization_id,c.project_id,c.interaction_id,c.operation_id,c.assignment_id,c.workflow_run_id)
                =(binding.organization_id,binding.project_id,intake.interaction_id,oid,aid,rid);
            IF FOUND THEN
                INSERT INTO audit.audit_events(id,organization_id,project_id,occurred_at,actor_type,action,object_type,
                                               object_id,result,correlation_id,details)
                VALUES (gen_random_uuid(),binding.organization_id,binding.project_id,clock_timestamp(),'SERVICE',
                        'MANAGER_INPUT_READ','OPERATION',oid,'SUCCEEDED',binding.correlation_id,'{}'::jsonb);
            END IF;
        END $f$
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_CAPTURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_CAPTURE} TO ai_res_platform_api_group")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_MATCH} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_MATCH} TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve issued Manager contexts and Proposal provenance.")
