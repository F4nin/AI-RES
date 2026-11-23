"""Exact-version plans, human decisions and approved PlanItem to Task lineage.

Revision ID: 62012d30b8c4
Revises: 7e41f5ae9b21
"""
from collections.abc import Sequence

from alembic import op

revision: str = "62012d30b8c4"
down_revision: str | None = "7e41f5ae9b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work.plans (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            epic_id uuid NOT NULL,
            last_version integer NOT NULL DEFAULT 0 CHECK (last_version >= 0),
            UNIQUE(organization_id,project_id,id),
            UNIQUE(organization_id,project_id,epic_id),
            FOREIGN KEY(organization_id,project_id,epic_id) REFERENCES work.epics(organization_id,project_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE work.plan_versions (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            plan_id uuid NOT NULL,
            version_number integer NOT NULL CHECK (version_number > 0),
            content_hash bytea NOT NULL CHECK (octet_length(content_hash)=32),
            snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot)='object'),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(plan_id,version_number),
            UNIQUE(organization_id,project_id,id),
            UNIQUE(organization_id,project_id,id,content_hash),
            FOREIGN KEY(organization_id,project_id,plan_id) REFERENCES work.plans(organization_id,project_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE governance.plan_version_decisions (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            plan_version_id uuid NOT NULL UNIQUE,
            content_hash bytea NOT NULL,
            approver_id uuid NOT NULL,
            decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT','REQUEST_CHANGES')),
            approved_items uuid[] NOT NULL,
            comment text,
            decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((decision='APPROVE') = (cardinality(approved_items)>0)),
            CHECK (array_position(approved_items,NULL) IS NULL),
            UNIQUE(organization_id,project_id,plan_version_id,id),
            FOREIGN KEY(organization_id,project_id,plan_version_id,content_hash)
                REFERENCES work.plan_versions(organization_id,project_id,id,content_hash) ON DELETE RESTRICT,
            FOREIGN KEY(organization_id,approver_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE work.plan_executions (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            operation_id uuid PRIMARY KEY,
            plan_version_id uuid NOT NULL,
            decision_id uuid NOT NULL UNIQUE,
            UNIQUE(organization_id,project_id,operation_id),
            FOREIGN KEY(organization_id,project_id,operation_id)
                REFERENCES operations.operations(organization_id,project_id,id) ON DELETE RESTRICT,
            FOREIGN KEY(organization_id,project_id,plan_version_id,decision_id)
                REFERENCES governance.plan_version_decisions(organization_id,project_id,plan_version_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE work.plan_item_tasks (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            operation_id uuid NOT NULL,
            item_id uuid NOT NULL,
            task_id uuid NOT NULL UNIQUE,
            PRIMARY KEY(operation_id,item_id),
            FOREIGN KEY(organization_id,project_id,operation_id)
                REFERENCES work.plan_executions(organization_id,project_id,operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(organization_id,project_id,operation_id,task_id)
                REFERENCES work.tasks(organization_id,project_id,operation_id,id) ON DELETE RESTRICT
        )
    """)
    tables = (
        "work.plans", "work.plan_versions", "governance.plan_version_decisions", "work.plan_executions", "work.plan_item_tasks",
    )
    for table in tables:
        name = table.split(".")[1]
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{name}_tenant ON {table} TO ai_res_api_group USING ({_SCOPE})")
        op.execute(f"""
            CREATE POLICY p_{name}_migration ON {table} TO ai_res_owner
            USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
            WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        """)
        op.execute(f"GRANT SELECT, INSERT ON {table} TO ai_res_api_group")
        if table != "work.plans":
            op.execute(f"""
                CREATE TRIGGER trg_{name}_immutable BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
            """)
    op.execute("GRANT UPDATE(last_version) ON work.plans TO ai_res_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove immutable planning history.")
