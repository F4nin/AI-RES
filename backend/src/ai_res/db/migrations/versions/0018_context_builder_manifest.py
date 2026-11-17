"""S19: optional versioned builder manifest and transaction-identity sealing.

Revision ID: a41c8f92d603
Revises: f3a9c1d7b542

Expand only: legacy snapshots remain immutable and are never invented/backfilled.
The new builder refuses to hydrate legacy versions without a manifest. Existing
clients may continue writing legacy snapshots; no NOT NULL/contract step here.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a41c8f92d603"
down_revision: str | None = "f3a9c1d7b542"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE context.context_package_versions ADD COLUMN builder_manifest jsonb NULL "
               "CONSTRAINT ck_context_package_versions_builder_manifest CHECK (jsonb_typeof(builder_manifest) = 'object')")
    op.execute("ALTER TABLE context.context_package_versions ADD COLUMN creation_transaction_id xid8 NULL")
    op.execute("""
CREATE FUNCTION context.stamp_creation_transaction() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  NEW.creation_transaction_id := pg_current_xact_id();
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_context_package_versions_creation_transaction BEFORE INSERT ON context.context_package_versions
  FOR EACH ROW EXECUTE FUNCTION context.stamp_creation_transaction();
CREATE OR REPLACE FUNCTION context.guard_item_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE creator xid8;
BEGIN
  SELECT creation_transaction_id INTO creator FROM context.context_package_versions WHERE id = NEW.context_package_version_id;
  IF creator IS NULL OR creator <> pg_current_xact_id() THEN
    RAISE EXCEPTION 'context package version is sealed' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.rule_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM governance.rule_versions r WHERE r.id = NEW.rule_version_id AND r.status = 'APPROVED') THEN
    RAISE EXCEPTION 'rule version is not approved or visible' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
""")


def downgrade() -> None:
    raise NotImplementedError("Context snapshots are immutable; forward-fix or restore with approval.")
