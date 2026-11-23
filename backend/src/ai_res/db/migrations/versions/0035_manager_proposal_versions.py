"""Immutable Manager proposal and separate exact-version human decision.

Revision ID: 7e41f5ae9b21
Revises: cafc3983e401
"""
from collections.abc import Sequence

from alembic import op

revision: str = "7e41f5ae9b21"
down_revision: str | None = "cafc3983e401"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work.manager_proposal_versions (
            id uuid CONSTRAINT pk_manager_proposals PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            interaction_id uuid NOT NULL,
            goal text CHECK (length(goal) <= 20000),
            scope text CHECK (length(scope) <= 20000),
            primary_question text CHECK (length(primary_question) <= 20000),
            content_hash bytea NOT NULL CHECK (octet_length(content_hash) = 32),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(organization_id,project_id,id,content_hash),
            UNIQUE(interaction_id),
            FOREIGN KEY(organization_id,project_id,interaction_id)
                REFERENCES work.manager_interactions(organization_id,project_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE governance.manager_proposal_decisions (
            id uuid CONSTRAINT pk_manager_proposal_decisions PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            proposal_version_id uuid NOT NULL UNIQUE,
            content_hash bytea NOT NULL,
            approver_id uuid NOT NULL,
            decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT','REQUEST_CHANGES')),
            comment text CHECK (length(comment) <= 20000),
            decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            FOREIGN KEY(organization_id,project_id,proposal_version_id,content_hash)
                REFERENCES work.manager_proposal_versions(organization_id,project_id,id,content_hash) ON DELETE RESTRICT,
            FOREIGN KEY(organization_id,approver_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT
        )
    """)
    for schema, name in (("work", "manager_proposal_versions"), ("governance", "manager_proposal_decisions")):
        table = f"{schema}.{name}"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{name}_tenant ON {table} TO ai_res_api_group USING ({_SCOPE})")
        op.execute(f"""
            CREATE POLICY p_{name}_migration ON {table} TO ai_res_owner
            USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
            WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        """)
        op.execute(f"GRANT SELECT, INSERT ON {table} TO ai_res_api_group")
        op.execute(f"""
            CREATE TRIGGER trg_{name}_immutable BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
        """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove proposal decisions.")
