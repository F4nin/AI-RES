"""S09: project goal, event history of PROJECT and EPIC, and outbox support for the three AsyncAPI v1.6 domain events of the write commands.

Revision ID: c2e95b71a408
Revises: a47d3e19c0b5

Expand-only (database-and-migrations.md): two nullable/defaulted columns and two new insert-only tables, nothing is dropped or rewritten.
* `project.projects.goal` closes G-84 (OAS `Project.goal`); `last_event_sequence` on projects and epics is the aggregate counter of TX-02.
* `project.project_events` / `work.epic_events` follow PDB-0016 (insert-only, RLS through the parent, contiguity verified at COMMIT).
* `audit.assert_outbox_matches_event` is replaced to accept PROJECT / EPIC / REQUIREMENT outbox rows. These aggregates belong to the older message
  family of AsyncAPI v1.6 (`aires.<name>.v1`, no Operation correlation), so their envelope is checked with that shape; the OPERATION / WORKER_RUN
  branches are unchanged. Anything else is still rejected (fail closed). Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "c2e95b71a408"
down_revision: str | None = "a47d3e19c0b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"
ORG = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
PRJ = "NULLIF(current_setting('app.project_id', true), '')::uuid"
# aggregate type, aggregate table, event table, fk column, constraint-name stem, predicate through the parent row `p`
AGGREGATES = (
    ("PROJECT", "project.projects", "project.project_events", "project_id", "project_events", f"p.organization_id = {ORG} AND p.id = {PRJ}"),
    ("EPIC", "work.epics", "work.epic_events", "epic_id", "epic_events", f"p.organization_id = {ORG} AND p.project_id = {PRJ}"),
)

OUTBOX_FUNCTION = """
CREATE OR REPLACE FUNCTION audit.assert_outbox_matches_event() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE found boolean; op_id uuid; domain boolean := false; expected_source text; expected_subject text;
BEGIN  -- deferred to COMMIT: an outbox row without its event (or for another aggregate/sequence) is an orphan and rolls the whole transaction back
  IF NEW.aggregate_type = 'OPERATION' THEN
    SELECT EXISTS (SELECT 1 FROM operations.operation_events e WHERE e.event_id = NEW.event_id AND e.operation_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    op_id := NEW.aggregate_id;
    expected_source := 'urn:aires:operations'; expected_subject := 'operations/' || NEW.aggregate_id::text;
  ELSIF NEW.aggregate_type = 'WORKER_RUN' THEN
    SELECT EXISTS (SELECT 1 FROM agents.worker_run_events e WHERE e.event_id = NEW.event_id AND e.worker_run_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    SELECT r.operation_id INTO op_id FROM agents.worker_runs r WHERE r.id = NEW.aggregate_id;
    expected_source := 'urn:aires:worker-runs'; expected_subject := 'worker-runs/' || NEW.aggregate_id::text;
  ELSIF NEW.aggregate_type = 'PROJECT' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM project.project_events e WHERE e.event_id = NEW.event_id AND e.project_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    expected_source := 'urn:aires:projects'; expected_subject := 'projects/' || NEW.aggregate_id::text;
  ELSIF NEW.aggregate_type = 'EPIC' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM work.epic_events e WHERE e.event_id = NEW.event_id AND e.epic_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    expected_source := 'urn:aires:epics'; expected_subject := 'epics/' || NEW.aggregate_id::text;
  ELSIF NEW.aggregate_type = 'REQUIREMENT' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM requirements.requirement_events e WHERE e.event_id = NEW.event_id AND e.requirement_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    expected_source := 'urn:aires:requirements'; expected_subject := 'requirements/' || NEW.aggregate_id::text;
  ELSE
    RAISE EXCEPTION 'outbox row % has aggregate_type % without an event-table mapping: extend audit.assert_outbox_matches_event in the revision that adds it', NEW.id, NEW.aggregate_type
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT found THEN
    RAISE EXCEPTION 'outbox row % does not describe an event of its aggregate (event %, % %, sequence %)', NEW.id, NEW.event_id, NEW.aggregate_type, NEW.aggregate_id, NEW.aggregate_sequence
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  -- the envelope is routed on by consumers and SSE: it must describe exactly this row's event and tenant (a forged envelope would be accepted otherwise)
  IF NEW.envelope ->> 'id' IS DISTINCT FROM NEW.event_id::text
     OR NEW.envelope ->> 'type' IS DISTINCT FROM (CASE WHEN domain THEN 'aires.' ELSE 'com.aires.' END) || NEW.event_type || '.v' || NEW.schema_version
     OR NEW.envelope #>> '{data,eventId}' IS DISTINCT FROM NEW.event_id::text
     OR NEW.envelope #>> '{data,organizationId}' IS DISTINCT FROM NEW.organization_id::text
     OR NEW.envelope #>> '{data,projectId}' IS DISTINCT FROM NEW.project_id::text
     OR NEW.envelope #>> '{data,aggregateType}' IS DISTINCT FROM NEW.aggregate_type
     OR NEW.envelope #>> '{data,aggregateId}' IS DISTINCT FROM NEW.aggregate_id::text
     OR NEW.envelope #>> '{data,aggregateSequence}' IS DISTINCT FROM NEW.aggregate_sequence::text
     OR NEW.envelope #>> '{data,operationId}' IS DISTINCT FROM op_id::text   -- NULL for the domain family: such an envelope carries no operationId
     OR NEW.envelope ->> 'subject' IS DISTINCT FROM expected_subject
     OR NEW.envelope ->> 'source' IS DISTINCT FROM expected_source
     OR NEW.envelope ->> 'dataschema' IS DISTINCT FROM 'urn:aires:schemas:' || (CASE WHEN domain THEN 'aires.' ELSE 'com.aires.' END) || NEW.event_type || '.v' || NEW.schema_version THEN
    RAISE EXCEPTION 'outbox row % has an envelope that does not match its event/tenant columns', NEW.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END $f$;
"""


def upgrade() -> None:
    op.execute("ALTER TABLE project.projects ADD COLUMN goal text NULL")
    op.execute("ALTER TABLE project.projects ADD COLUMN last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_projects_last_event_sequence CHECK (last_event_sequence >= 0)")
    op.execute("ALTER TABLE work.epics ADD COLUMN last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_epics_last_event_sequence CHECK (last_event_sequence >= 0)")
    for _atype, parent, events, fk, stem, predicate in AGGREGATES:
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
        policy = f"EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {fk} AND {predicate})"
        op.execute(f"ALTER TABLE {events} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {events} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{stem}_tenant_scope ON {events} FOR ALL TO ai_res_api_group USING ({policy}) WITH CHECK ({policy})")
        op.execute(f"CREATE POLICY p_{stem}_owner_migration ON {events} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
        op.execute(f"GRANT SELECT, INSERT ON {events} TO ai_res_api_group")
        op.execute(f"CREATE TRIGGER trg_{stem}_append_only BEFORE UPDATE OR DELETE ON {events} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{stem}_no_truncate BEFORE TRUNCATE ON {events} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_{stem}_sequence AFTER INSERT ON {events} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_event_sequence_contiguous('{fk}', '{parent}', '{events}', '{fk}')")
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_{parent_short}_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON {parent} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', '{parent}', '{events}', '{fk}')")
    op.execute("INSERT INTO audit.aggregate_types (code) VALUES ('PROJECT'), ('EPIC')")
    op.execute(OUTBOX_FUNCTION)


def downgrade() -> None:
    raise NotImplementedError("PDB-0017 creates event history that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
