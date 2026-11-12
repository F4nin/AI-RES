"""S10: consumer Inbox sequence checkpoint and the replay counter of quarantined outbox rows.

Revision ID: d5a1c8e7f302
Revises: c2e95b71a408

Expand-only (database-and-migrations.md): one new table and one defaulted column, nothing is dropped or rewritten.
* `audit.inbox_checkpoints` (Event Model v1.4 §9.2 step 3-4): the last aggregate sequence a consumer applied, per (consumer, aggregate). It is advanced in the
  SAME transaction as the Inbox marker and the consumer's local effect, so a crash before COMMIT leaves no trace. A trigger makes it strictly monotonic: the
  checkpoint can never go backwards, and its identity columns are immutable. Cross-tenant by design like `audit.inbox_messages` (ADR-034): only the event
  consumer group may touch it.
* `audit.outbox_events.replay_count` (Event Model §16 metric "replay count"): how often a quarantined row was put back by a controlled replay. The dispatcher
  group already updates delivery columns; this one is added to its column grant.
Plain CREATE INDEX (not CONCURRENTLY) because Alembic runs the revision in one transaction and the table is still small at S10; later indexes on a grown outbox
must be CONCURRENTLY. The CHECK is added NOT VALID and validated separately (database-and-migrations.md). Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "d5a1c8e7f302"
down_revision: str | None = "c2e95b71a408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"

TABLES = """
ALTER TABLE audit.outbox_events ADD COLUMN replay_count integer NOT NULL DEFAULT 0;
ALTER TABLE audit.outbox_events ADD CONSTRAINT ck_outbox_events_replay_count CHECK (replay_count >= 0) NOT VALID;
ALTER TABLE audit.outbox_events VALIDATE CONSTRAINT ck_outbox_events_replay_count;

CREATE FUNCTION audit.assert_replay_count_step() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- replay_count is a counter of controlled replays: it moves by exactly one, and only together with QUARANTINED -> PENDING
  IF NEW.replay_count IS DISTINCT FROM OLD.replay_count
     AND NOT (NEW.replay_count = OLD.replay_count + 1 AND OLD.status = 'QUARANTINED' AND NEW.status = 'PENDING') THEN
    RAISE EXCEPTION 'outbox row % replay_count may only grow by one when a quarantined row is replayed', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

-- claim path (ADR-085): the dispatcher scans only undelivered rows, in delivery order; quarantine/status counts get their own narrow indexes
CREATE INDEX ix_outbox_events_claim_pending ON audit.outbox_events (created_at, aggregate_sequence) WHERE status = 'PENDING';
CREATE INDEX ix_outbox_events_claim_lease ON audit.outbox_events (lease_until) WHERE status = 'IN_FLIGHT';
CREATE INDEX ix_outbox_events_quarantined ON audit.outbox_events (created_at) WHERE status = 'QUARANTINED';

CREATE FUNCTION audit.assert_checkpoint_advances() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- a consumer checkpoint only moves forward: a regression would let an old event be applied again
  IF NEW.last_sequence <= OLD.last_sequence THEN
    RAISE EXCEPTION 'inbox checkpoint of % for % % must advance (% -> %)', OLD.consumer_name, OLD.aggregate_type, OLD.aggregate_id, OLD.last_sequence, NEW.last_sequence
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE TABLE audit.inbox_checkpoints (
    consumer_name text NOT NULL CONSTRAINT ck_inbox_checkpoints_consumer_name CHECK (length(consumer_name) BETWEEN 1 AND 200),
    aggregate_type text NOT NULL CONSTRAINT fk_inbox_checkpoints_aggregate_type_aggregate_types REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT,
    aggregate_id uuid NOT NULL,
    last_sequence bigint NOT NULL CONSTRAINT ck_inbox_checkpoints_last_sequence CHECK (last_sequence > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_inbox_checkpoints PRIMARY KEY (consumer_name, aggregate_type, aggregate_id));
"""


def upgrade() -> None:
    op.execute(TABLES)
    op.execute("GRANT UPDATE (replay_count) ON audit.outbox_events TO ai_res_outbox_group")
    op.execute("CREATE TRIGGER trg_outbox_events_replay_count_step BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION audit.assert_replay_count_step()")

    op.execute("ALTER TABLE audit.inbox_checkpoints ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit.inbox_checkpoints FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY p_inbox_checkpoints_consumer_all ON audit.inbox_checkpoints FOR ALL TO ai_res_consumer_group USING (true) WITH CHECK (true)")
    op.execute(f"CREATE POLICY p_inbox_checkpoints_owner_migration ON audit.inbox_checkpoints FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
    op.execute("GRANT SELECT, INSERT ON audit.inbox_checkpoints TO ai_res_consumer_group")
    op.execute("GRANT UPDATE (last_sequence, updated_at) ON audit.inbox_checkpoints TO ai_res_consumer_group")
    op.execute("CREATE TRIGGER trg_inbox_checkpoints_immutable_columns BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'consumer_name', 'aggregate_type', 'aggregate_id')")
    op.execute("CREATE TRIGGER trg_inbox_checkpoints_advance BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION audit.assert_checkpoint_advances()")


def downgrade() -> None:
    raise NotImplementedError("S10 adds a table that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
