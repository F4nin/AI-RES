"""Assignment-bound Manager draft and Plan materialization (DOC-068 v1.3).

Revision ID: 44a630d91fe1
Revises: b4968d15c120
"""
# ruff: noqa: S608 -- fixed migration predicates and column lists
from alembic import op

revision: str = "44a630d91fe1"
down_revision: str | None = "b4968d15c120"
branch_labels = None
depends_on = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid"""
_OP = "NULLIF(current_setting('app.platform_operation_id', true), '')::uuid"
_ACTION = "current_setting('app.platform_action', true)"
_PLAN = f"{_ACTION} = 'plan.materialize_tasks'"
_DRAFT = f"{_ACTION} = 'manager.record_draft'"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.operation_execution_assignments
        DROP CONSTRAINT ck_operation_assignment_actions,
        ADD CONSTRAINT ck_operation_assignment_actions CHECK (
            cardinality(allowed_actions) > 0 AND array_position(allowed_actions,NULL) IS NULL
            AND CASE workflow_type
                WHEN 'ManagerIntakeWorkflow' THEN allowed_actions <@ ARRAY[
                    'operation.acknowledge_start','operation.record_failure','operation.confirm_cancellation',
                    'manager.read_input','manager.record_draft']::text[]
                WHEN 'PlanExecutionWorkflow' THEN allowed_actions <@ ARRAY[
                    'operation.acknowledge_start','operation.record_failure','operation.confirm_cancellation','plan.materialize_tasks']::text[]
                ELSE allowed_actions <@ ARRAY[
                    'operation.acknowledge_start','operation.record_failure','operation.confirm_cancellation']::text[]
            END
        )
    """)
    op.execute("GRANT USAGE ON SCHEMA work, governance TO ai_res_platform_api_group")
    op.execute("GRANT UPDATE(result_ref) ON operations.operations TO ai_res_platform_api_group")
    op.execute("GRANT SELECT(id,organization_id,project_id,operation_id,message) ON work.manager_interactions TO ai_res_platform_api_group")
    op.execute(f"""
        CREATE POLICY p_manager_interactions_platform ON work.manager_interactions FOR SELECT TO ai_res_platform_api_group
        USING ({_SCOPE} AND operation_id={_OP} AND {_ACTION} IN ('manager.read_input','manager.record_draft'))
    """)
    op.execute("""
        GRANT SELECT(id,interaction_id,content_hash),
          INSERT(id,organization_id,project_id,interaction_id,goal,scope,primary_question,content_hash)
        ON work.manager_proposal_versions TO ai_res_platform_api_group
    """)
    op.execute(f"""
        CREATE POLICY p_manager_proposals_platform ON work.manager_proposal_versions TO ai_res_platform_api_group
        USING ({_SCOPE} AND {_DRAFT} AND EXISTS (
            SELECT 1 FROM work.manager_interactions i WHERE i.id=interaction_id AND i.operation_id={_OP}
        ))
    """)
    op.execute("GRANT SELECT(organization_id,project_id,operation_id,plan_version_id,decision_id) ON work.plan_executions TO ai_res_platform_api_group")
    op.execute("GRANT SELECT(id,plan_id,snapshot) ON work.plan_versions TO ai_res_platform_api_group")
    op.execute("GRANT SELECT(id,epic_id) ON work.plans TO ai_res_platform_api_group")
    op.execute("GRANT SELECT(id,plan_version_id,approved_items,decision) ON governance.plan_version_decisions TO ai_res_platform_api_group")
    for table, predicate in (
        ("work.plan_executions", f"{_SCOPE} AND operation_id={_OP}"),
        ("work.plan_versions", "EXISTS (SELECT 1 FROM work.plan_executions e WHERE e.plan_version_id=plan_versions.id)"),
        ("work.plans", "EXISTS (SELECT 1 FROM work.plan_versions v WHERE v.plan_id=plans.id)"),
        ("governance.plan_version_decisions", "EXISTS (SELECT 1 FROM work.plan_executions e WHERE e.decision_id=plan_version_decisions.id)"),
    ):
        name = table.split(".")[1]
        op.execute(f"CREATE POLICY p_{name}_platform ON {table} FOR SELECT TO ai_res_platform_api_group USING ({_PLAN} AND {predicate})")

    op.execute("""
        GRANT SELECT(id,operation_id,epic_id,status,title,row_version,derived_from_task_id,last_event_sequence),
          INSERT(id,organization_id,project_id,operation_id,epic_id,derived_from_task_id,task_type,title,description,
                 acceptance_criteria,status,priority,initiator_type,initiator_id,created_by),
          UPDATE(row_version,last_event_sequence)
        ON work.tasks TO ai_res_platform_api_group
    """)
    op.execute(f"""
        CREATE POLICY p_tasks_platform ON work.tasks TO ai_res_platform_api_group
        USING ({_SCOPE} AND {_PLAN} AND operation_id={_OP} AND status='PROPOSED')
    """)
    op.execute("GRANT INSERT(id,organization_id,project_id,task_id,depends_on_task_id,created_by) ON work.task_dependencies TO ai_res_platform_api_group")
    op.execute(f"""
        CREATE POLICY p_task_dependencies_platform ON work.task_dependencies FOR INSERT TO ai_res_platform_api_group
        WITH CHECK ({_SCOPE} AND {_PLAN}
            AND EXISTS (SELECT 1 FROM work.tasks t WHERE t.id=task_id AND t.operation_id={_OP})
            AND EXISTS (SELECT 1 FROM work.tasks t WHERE t.id=depends_on_task_id AND t.operation_id={_OP}))
    """)
    op.execute("""
        GRANT SELECT(operation_id,item_id,task_id), INSERT(organization_id,project_id,operation_id,item_id,task_id)
        ON work.plan_item_tasks TO ai_res_platform_api_group
    """)
    op.execute(f"""
        CREATE POLICY p_plan_item_tasks_platform ON work.plan_item_tasks TO ai_res_platform_api_group
        USING ({_SCOPE} AND {_PLAN} AND operation_id={_OP})
        WITH CHECK ({_SCOPE} AND {_PLAN} AND operation_id={_OP} AND EXISTS (
            SELECT 1 FROM work.plan_executions e JOIN governance.plan_version_decisions d ON d.id=e.decision_id
            WHERE e.operation_id={_OP} AND d.decision='APPROVE' AND item_id=ANY(d.approved_items)
        ))
    """)
    op.execute("""
        GRANT INSERT ON work.task_events TO ai_res_platform_api_group;
        GRANT SELECT(event_id,task_id,aggregate_sequence,event_type,schema_version) ON work.task_events TO ai_res_platform_api_group;
    """)
    op.execute(f"""
        CREATE POLICY p_task_events_platform ON work.task_events TO ai_res_platform_api_group
        USING ({_PLAN} AND EXISTS (SELECT 1 FROM work.tasks t WHERE t.id=task_id AND t.operation_id={_OP}))
    """)
    op.execute(f"""
        CREATE POLICY p_task_outbox_platform ON audit.outbox_events FOR INSERT TO ai_res_platform_api_group
        WITH CHECK ({_SCOPE} AND {_PLAN} AND aggregate_type='TASK' AND EXISTS (
            SELECT 1 FROM work.tasks t WHERE t.id=aggregate_id AND t.operation_id={_OP}
        ))
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would revoke in-flight assignments.")
