"""Seal Manager attachments against the immutable initial event.

Revision ID: 7eac89d49602
Revises: 2f7d90e4b1ac
"""
from alembic import op

revision: str = "7eac89d49602"
down_revision: str | None = "2f7d90e4b1ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION work.require_unsealed_interaction() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        BEGIN
            PERFORM 1 FROM work.manager_interactions i
            WHERE i.id=NEW.interaction_id AND i.organization_id=NEW.organization_id AND i.project_id=NEW.project_id
            FOR NO KEY UPDATE;
            IF NOT FOUND OR EXISTS (
                SELECT 1 FROM work.manager_interaction_events e
                WHERE e.interaction_id=NEW.interaction_id
            ) THEN
                RAISE EXCEPTION 'Manager interaction attachments are sealed' USING ERRCODE='integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $f$
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would weaken attachment immutability.")
