"""Require an approved mapping at commit for any Task created by Platform API.

Revision ID: 3f6a0e614b92
Revises: 44a630d91fe1
"""
from alembic import op

revision: str = "3f6a0e614b92"
down_revision: str | None = "44a630d91fe1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION work.require_platform_plan_item() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM work.plan_item_tasks m
                JOIN work.plan_executions e ON e.operation_id=m.operation_id
                JOIN governance.plan_version_decisions d ON d.id=e.decision_id AND d.plan_version_id=e.plan_version_id
                WHERE m.operation_id=NEW.operation_id AND m.task_id=NEW.id
                  AND d.decision='APPROVE' AND m.item_id=ANY(d.approved_items)
            ) THEN
                RAISE EXCEPTION 'Task needs an approved PlanItem mapping' USING ERRCODE='integrity_constraint_violation';
            END IF;
            RETURN NULL;
        END $f$
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_task_platform_plan_item AFTER INSERT ON work.tasks
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (current_user='ai_res_platform_api')
        EXECUTE FUNCTION work.require_platform_plan_item()
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would weaken the Platform task boundary.")
