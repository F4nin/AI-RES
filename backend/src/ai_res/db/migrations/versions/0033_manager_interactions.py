"""Immutable, tenant-scoped Manager intake and exact attachment refs.

Revision ID: ae62d804c91f
Revises: 7d13e0bc27f4
"""
from collections.abc import Sequence

from alembic import op

revision: str = "ae62d804c91f"
down_revision: str | None = "7d13e0bc27f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work.manager_interactions (
            id uuid CONSTRAINT pk_manager_interactions PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            epic_id uuid NOT NULL,
            operation_id uuid NOT NULL,
            author_id uuid NOT NULL,
            message text NOT NULL CONSTRAINT ck_manager_message_length CHECK (length(message) BETWEEN 1 AND 20000),
            expected_response_mode text CONSTRAINT ck_manager_response_mode CHECK (
                expected_response_mode IN ('NORMAL','PROPOSE_PLAN','CLARIFICATION','REVIEW_RESULT')
            ),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT uq_manager_interaction_tenant UNIQUE (organization_id,project_id,id),
            CONSTRAINT uq_manager_interaction_operation UNIQUE (operation_id),
            CONSTRAINT fk_manager_interaction_epic FOREIGN KEY (organization_id,project_id,epic_id)
                REFERENCES work.epics(organization_id,project_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_manager_interaction_operation FOREIGN KEY (organization_id,project_id,operation_id)
                REFERENCES operations.operations(organization_id,project_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_manager_interaction_author FOREIGN KEY (organization_id,author_id)
                REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX ix_manager_interactions_epic ON work.manager_interactions(organization_id,project_id,epic_id,created_at,id)")
    op.execute("""
        CREATE TABLE work.manager_interaction_attachments (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            interaction_id uuid NOT NULL,
            ordinal integer NOT NULL CONSTRAINT ck_manager_attachment_ordinal CHECK (ordinal >= 0),
            source_version_id uuid NOT NULL,
            CONSTRAINT pk_manager_interaction_attachments PRIMARY KEY (interaction_id,ordinal),
            CONSTRAINT fk_manager_attachment_interaction FOREIGN KEY (organization_id,project_id,interaction_id)
                REFERENCES work.manager_interactions(organization_id,project_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_manager_attachment_version FOREIGN KEY (organization_id,project_id,source_version_id)
                REFERENCES sources.source_versions(organization_id,project_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX ix_manager_attachment_version ON work.manager_interaction_attachments(organization_id,project_id,source_version_id)")
    for name in ("manager_interactions", "manager_interaction_attachments"):
        op.execute(f"ALTER TABLE work.{name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{name} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{name}_tenant ON work.{name} TO ai_res_api_group USING ({_SCOPE})")
        op.execute(f"""
            CREATE POLICY p_{name}_migration ON work.{name} TO ai_res_owner
            USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
            WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        """)
        op.execute(f"GRANT SELECT, INSERT ON work.{name} TO ai_res_api_group")
        op.execute(f"""
            CREATE TRIGGER trg_{name}_immutable BEFORE UPDATE OR DELETE ON work.{name}
            FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
        """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove user interactions.")
