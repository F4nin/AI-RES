"""PDB-0016: append-only event history of the S06 aggregates (requirement, source, artifact, baseline, change request) and aggregate_types, S06 slice D.

Revision ID: d85a3f6c1e07
Revises: c47e1b8a92d5

Same model as `operations.operation_events` (ADR-033/034): insert-only for every principal, RLS through the parent aggregate, per-aggregate contiguous sequence
verified at COMMIT. The aggregates are those that have messages in AsyncAPI v1.6. `audit.aggregate_types` is extended, but `audit.assert_outbox_matches_event`
is deliberately NOT extended here: it raises for an aggregate type without an event-table/envelope mapping, so an outbox row for these aggregates is rejected
(fail closed) until the envelope form (OD-13, owner: before S10) is decided. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "d85a3f6c1e07"
down_revision: str | None = "c47e1b8a92d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"
# aggregate type, aggregate table, event table, fk column, constraint-name stem
AGGREGATES = (
    ("REQUIREMENT", "requirements.requirements", "requirements.requirement_events", "requirement_id", "requirement_events"),
    ("SOURCE", "sources.sources", "sources.source_events", "source_id", "source_events"),
    ("ARTIFACT", "artifacts.artifacts", "artifacts.artifact_events", "artifact_id", "artifact_events"),
    ("BASELINE", "governance.baselines", "governance.baseline_events", "baseline_id", "baseline_events"),
    ("CHANGE_REQUEST", "governance.change_requests", "governance.change_request_events", "change_request_id", "change_request_events"),
)


def upgrade() -> None:
    for atype, parent, events, fk, stem in AGGREGATES:
        parent_short = parent.split(".")[1]
        op.execute(f"""
CREATE TABLE {events} (
    event_id uuid CONSTRAINT pk_{stem} PRIMARY KEY,
    {fk} uuid NOT NULL CONSTRAINT fk_{stem}_{fk}_{parent_short} REFERENCES {parent}(id) ON DELETE RESTRICT,
    aggregate_sequence bigint NOT NULL CONSTRAINT ck_{stem}_aggregate_sequence CHECK (aggregate_sequence > 0),
    aggregate_version bigint NOT NULL CONSTRAINT ck_{stem}_aggregate_version CHECK (aggregate_version > 0),
    event_type text NOT NULL, schema_version integer NOT NULL CONSTRAINT ck_{stem}_schema_version CHECK (schema_version > 0),
    source text NOT NULL, subject text NOT NULL, occurred_at timestamptz NOT NULL,
    correlation_id uuid NOT NULL, causation_id uuid NULL,
    actor_type text NOT NULL CONSTRAINT ck_{stem}_actor_type CHECK (actor_type IN ('SYSTEM','USER','MANAGER','WORKER','SERVICE')), actor_id uuid NULL,
    reason_code text NULL, from_status text NULL, to_status text NULL,
    data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_{stem}_{fk}_aggregate_sequence UNIQUE ({fk}, aggregate_sequence));
CREATE INDEX ix_{stem}_{fk}_occurred_at ON {events} ({fk}, occurred_at DESC)""")
        policy = (f"EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {fk} AND p.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
                  "AND p.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")
        op.execute(f"ALTER TABLE {events} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {events} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{stem}_tenant_scope ON {events} FOR ALL TO ai_res_api_group USING ({policy}) WITH CHECK ({policy})")
        op.execute(f"CREATE POLICY p_{stem}_owner_migration ON {events} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
        op.execute(f"GRANT SELECT, INSERT ON {events} TO ai_res_api_group")
        op.execute(f"CREATE TRIGGER trg_{stem}_append_only BEFORE UPDATE OR DELETE ON {events} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{stem}_no_truncate BEFORE TRUNCATE ON {events} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_{stem}_sequence AFTER INSERT ON {events} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_event_sequence_contiguous('{fk}', '{parent}', '{events}', '{fk}')")
        when = "INSERT" if atype == "BASELINE" else "INSERT OR UPDATE OF last_event_sequence"
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_{parent_short}_sequence AFTER {when} ON {parent} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', '{parent}', '{events}', '{fk}')")
    values = ", ".join(f"('{a[0]}')" for a in AGGREGATES)
    op.execute(f"INSERT INTO audit.aggregate_types (code) VALUES {values}")


def downgrade() -> None:
    raise NotImplementedError("PDB-0016 creates event history that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
