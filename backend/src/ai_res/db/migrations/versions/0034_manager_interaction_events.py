"""Append-only Manager interaction event history and the canonical Outbox binding.

Revision ID: cafc3983e401
Revises: ae62d804c91f
"""
# ruff: noqa: E501 -- immutable SQL declarations follow the database constraints.
from collections.abc import Sequence

from alembic import op

revision: str = "cafc3983e401"
down_revision: str | None = "ae62d804c91f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
  ELSIF NEW.aggregate_type = 'MANAGER_INTERACTION' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM work.manager_interaction_events e WHERE e.event_id = NEW.event_id AND e.interaction_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    expected_source := 'urn:aires:manager-interactions'; expected_subject := 'manager-interactions/' || NEW.aggregate_id::text;
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
    op.execute("ALTER TABLE work.manager_interactions ADD COLUMN row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0)")
    op.execute("ALTER TABLE work.manager_interactions ADD COLUMN last_event_sequence bigint NOT NULL DEFAULT 0 CHECK (last_event_sequence >= 0)")
    op.execute("DROP TRIGGER trg_manager_interactions_immutable ON work.manager_interactions")
    op.execute("""
        CREATE TRIGGER trg_manager_interaction_body_immutable BEFORE UPDATE ON work.manager_interactions
        FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable(
            'id','organization_id','project_id','epic_id','operation_id','author_id','message','expected_response_mode','created_at'
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_manager_interactions_no_delete BEFORE DELETE ON work.manager_interactions
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
    """)
    op.execute("GRANT UPDATE(row_version,last_event_sequence) ON work.manager_interactions TO ai_res_api_group")
    op.execute("""
        CREATE TABLE work.manager_interaction_events (
            event_id uuid CONSTRAINT pk_manager_interaction_events PRIMARY KEY,
            interaction_id uuid NOT NULL REFERENCES work.manager_interactions(id) ON DELETE RESTRICT,
            aggregate_sequence bigint NOT NULL CHECK (aggregate_sequence > 0),
            aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
            event_type text NOT NULL CHECK (event_type IN ('manager.interaction.received','manager.question.proposed')),
            schema_version integer NOT NULL CHECK (schema_version = 1),
            source text NOT NULL, subject text NOT NULL, occurred_at timestamptz NOT NULL, correlation_id uuid NOT NULL,
            causation_id uuid, actor_type text NOT NULL CHECK (actor_type IN ('USER','MANAGER','SERVICE')),
            actor_id uuid, reason_code text, from_status text, to_status text, data jsonb NOT NULL,
            UNIQUE(interaction_id,aggregate_sequence)
        )
    """)
    op.execute("ALTER TABLE work.manager_interaction_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE work.manager_interaction_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_manager_interaction_events_tenant ON work.manager_interaction_events TO ai_res_api_group
        USING (EXISTS (SELECT 1 FROM work.manager_interactions p WHERE p.id = interaction_id))
    """)
    op.execute("""
        CREATE POLICY p_manager_interaction_events_migration ON work.manager_interaction_events TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    op.execute("GRANT SELECT, INSERT ON work.manager_interaction_events TO ai_res_api_group")
    op.execute("""
        CREATE TRIGGER trg_manager_interaction_events_immutable BEFORE UPDATE OR DELETE ON work.manager_interaction_events
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_manager_interaction_events_sequence AFTER INSERT ON work.manager_interaction_events
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous(
            'interaction_id','work.manager_interactions','work.manager_interaction_events','interaction_id'
        )
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_manager_interactions_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.manager_interactions
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous(
            'id','work.manager_interactions','work.manager_interaction_events','interaction_id'
        )
    """)
    op.execute("INSERT INTO audit.aggregate_types(code) VALUES ('MANAGER_INTERACTION')")
    op.execute(OUTBOX_FUNCTION)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove Manager event history.")
