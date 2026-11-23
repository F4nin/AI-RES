"""Persist the recipient's workspace feed and frequency selection.

Revision ID: 95ce548ce5b0
Revises: 28a56a9341ce
"""
from alembic import op

revision = "95ce548ce5b0"
down_revision = "28a56a9341ce"
branch_labels = None
depends_on = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid
AND project_id = NULLIF(current_setting('app.project_id',true),'')::uuid
AND recipient_id = NULLIF(current_setting('app.notification_recipient_id',true),'')::uuid"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE project.notification_preferences (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            recipient_id uuid NOT NULL,
            interval_seconds integer NOT NULL CONSTRAINT ck_notification_interval CHECK (interval_seconds > 0),
            row_version bigint NOT NULL CONSTRAINT ck_notification_preference_version CHECK (row_version >= 2),
            CONSTRAINT pk_notification_preferences PRIMARY KEY (organization_id,project_id,recipient_id),
            CONSTRAINT fk_notification_preference_project FOREIGN KEY (organization_id,project_id)
                REFERENCES project.projects(organization_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_notification_preference_recipient FOREIGN KEY (organization_id,recipient_id)
                REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT
        );
        CREATE TABLE project.notification_deliveries (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            recipient_id uuid NOT NULL,
            id uuid NOT NULL,
            mandatory boolean NOT NULL,
            cutoff_at timestamptz NOT NULL,
            published_at timestamptz,
            CONSTRAINT pk_notification_deliveries PRIMARY KEY (organization_id,project_id,recipient_id,id),
            CONSTRAINT fk_notification_delivery_project FOREIGN KEY (organization_id,project_id)
                REFERENCES project.projects(organization_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_notification_delivery_recipient FOREIGN KEY (organization_id,recipient_id)
                REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT,
            CONSTRAINT ck_notification_mandatory_published CHECK (NOT mandatory OR published_at IS NOT NULL)
        );
        CREATE UNIQUE INDEX uq_notification_active_digest
            ON project.notification_deliveries(organization_id,project_id,recipient_id)
            WHERE published_at IS NULL;
        CREATE INDEX ix_notification_deliveries_published
            ON project.notification_deliveries(organization_id,project_id,recipient_id,published_at DESC,id DESC)
            WHERE published_at IS NOT NULL;
        CREATE INDEX ix_notification_deliveries_mandatory
            ON project.notification_deliveries(organization_id,project_id,recipient_id,published_at DESC,id DESC)
            WHERE mandatory;
        CREATE TABLE project.notification_events (
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            recipient_id uuid NOT NULL,
            event_id uuid NOT NULL CONSTRAINT fk_notification_event_source REFERENCES operations.operation_events(event_id) ON DELETE RESTRICT,
            operation_id uuid NOT NULL,
            proposal_version_id uuid CONSTRAINT fk_notification_event_proposal REFERENCES work.manager_proposal_versions(id) ON DELETE RESTRICT,
            occurred_at timestamptz NOT NULL,
            delivery_id uuid NOT NULL,
            CONSTRAINT pk_notification_events PRIMARY KEY (organization_id,project_id,recipient_id,event_id),
            CONSTRAINT fk_notification_event_delivery FOREIGN KEY (organization_id,project_id,recipient_id,delivery_id)
                REFERENCES project.notification_deliveries(organization_id,project_id,recipient_id,id) ON DELETE RESTRICT,
            CONSTRAINT fk_notification_event_operation FOREIGN KEY (organization_id,project_id,operation_id)
                REFERENCES operations.operations(organization_id,project_id,id) ON DELETE RESTRICT,
            CONSTRAINT ck_notification_single_failure CHECK (proposal_version_id IS NOT NULL OR delivery_id=event_id)
        );
        CREATE INDEX ix_notification_events_delivery
            ON project.notification_events(organization_id,project_id,recipient_id,delivery_id,occurred_at DESC,event_id DESC);
        CREATE INDEX ix_manager_operations_notification_candidates
            ON operations.operations(organization_id,project_id,initiator_id,id)
            WHERE operation_type='MANAGER_MESSAGE' AND status IN ('FAILED','SUCCEEDED');
        CREATE INDEX ix_manager_interactions_notification_recipients
            ON work.manager_interactions(organization_id,project_id,author_id);
    """)
    for name, mutable in (
        ("notification_preferences", "interval_seconds,row_version"),
        ("notification_deliveries", "published_at"),
        ("notification_events", None),
    ):
        op.execute(f"ALTER TABLE project.{name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE project.{name} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{name}_scope ON project.{name} TO ai_res_api_group USING ({_SCOPE}) WITH CHECK ({_SCOPE})")
        op.execute(f"""
            CREATE POLICY p_{name}_migration ON project.{name} TO ai_res_owner
            USING (COALESCE(current_setting('app.migration_mode',true),'')='on')
            WITH CHECK (COALESCE(current_setting('app.migration_mode',true),'')='on')
        """)
        op.execute(f"GRANT SELECT, INSERT ON project.{name} TO ai_res_api_group")
        if mutable is not None:
            op.execute(f"GRANT UPDATE ({mutable}) ON project.{name} TO ai_res_api_group")
    op.execute("""
        CREATE TRIGGER trg_notification_delivery_publish_once BEFORE UPDATE ON project.notification_deliveries
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('published_at');
        CREATE TRIGGER trg_notification_events_immutable BEFORE UPDATE OR DELETE ON project.notification_events
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve delivered notifications and preferences.")
