"""Rebuildable per-Epic Manager question journal.

Revision ID: b4968d15c120
Revises: 7eac89d49602
"""
from alembic import op

revision: str = "b4968d15c120"
down_revision: str | None = "7eac89d49602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work.manager_question_journal (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            epic_id uuid NOT NULL,
            sequence bigint NOT NULL CHECK (sequence > 0),
            interaction_id uuid NOT NULL,
            question_id uuid NOT NULL,
            event_kind text NOT NULL,
            topic text,
            disposition text,
            PRIMARY KEY (organization_id,project_id,epic_id,sequence),
            UNIQUE (interaction_id,event_kind),
            CHECK ((
                (event_kind='PROPOSED' AND length(topic) BETWEEN 1 AND 128 AND disposition IS NULL)
                OR (event_kind='RESOLVED' AND topic IS NULL AND disposition IN ('ANSWERED','UNKNOWN'))
            ) IS TRUE),
            FOREIGN KEY (organization_id,project_id,epic_id) REFERENCES work.epics(organization_id,project_id,id) ON DELETE RESTRICT,
            FOREIGN KEY (organization_id,project_id,interaction_id)
                REFERENCES work.manager_interactions(organization_id,project_id,id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE work.manager_question_journal ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE work.manager_question_journal FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_manager_question_journal_tenant ON work.manager_question_journal TO ai_res_api_group USING (
            organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
            AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
            AND EXISTS (
                SELECT 1 FROM work.manager_interactions i
                WHERE i.id=interaction_id AND i.epic_id=manager_question_journal.epic_id
            )
        )
    """)
    op.execute("""
        CREATE POLICY p_manager_question_journal_migration ON work.manager_question_journal TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    op.execute("GRANT SELECT, INSERT ON work.manager_question_journal TO ai_res_api_group")
    op.execute("""
        CREATE TRIGGER trg_manager_question_journal_immutable BEFORE UPDATE OR DELETE ON work.manager_question_journal
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove question history.")
