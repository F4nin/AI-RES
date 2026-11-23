"""Persist PlanVersion and Task events and seal accepted attachment sets.

Revision ID: 2f7d90e4b1ac
Revises: 62012d30b8c4
"""
# ruff: noqa: E501, S608 -- DDL interpolates only frozen schema constants from this revision.
from collections.abc import Sequence

from alembic import op

revision: str = "2f7d90e4b1ac"
down_revision: str | None = "62012d30b8c4"
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
  ELSIF NEW.aggregate_type = 'PLAN_VERSION' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM work.plan_version_events e WHERE e.event_id=NEW.event_id AND e.plan_version_id=NEW.aggregate_id
                    AND e.aggregate_sequence=NEW.aggregate_sequence AND e.event_type=NEW.event_type AND e.schema_version=NEW.schema_version) INTO found;
    expected_source := 'urn:aires:plan-versions'; expected_subject := 'plan-versions/' || NEW.aggregate_id::text;
  ELSIF NEW.aggregate_type = 'TASK' THEN
    domain := true;
    SELECT EXISTS (SELECT 1 FROM work.task_events e WHERE e.event_id=NEW.event_id AND e.task_id=NEW.aggregate_id
                    AND e.aggregate_sequence=NEW.aggregate_sequence AND e.event_type=NEW.event_type AND e.schema_version=NEW.schema_version) INTO found;
    expected_source := 'urn:aires:tasks'; expected_subject := 'tasks/' || NEW.aggregate_id::text;
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
    op.execute("ALTER TABLE work.tasks ADD COLUMN last_event_sequence bigint NOT NULL DEFAULT 0 CHECK (last_event_sequence >= 0)")
    op.execute("ALTER TABLE work.plan_versions ADD COLUMN row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0)")
    op.execute("ALTER TABLE work.plan_versions ADD COLUMN last_event_sequence bigint NOT NULL DEFAULT 0 CHECK (last_event_sequence >= 0)")
    op.execute("DROP TRIGGER trg_plan_versions_immutable ON work.plan_versions")
    op.execute("""
        CREATE TRIGGER trg_plan_versions_content_immutable BEFORE UPDATE ON work.plan_versions
        FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable(
            'id','organization_id','project_id','plan_id','version_number','content_hash','snapshot','created_at')
    """)
    op.execute("""
        CREATE TRIGGER trg_plan_versions_no_delete BEFORE DELETE ON work.plan_versions
        FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
    """)
    op.execute("GRANT UPDATE(row_version,last_event_sequence) ON work.plan_versions TO ai_res_api_group")
    specs = (
        ("plan_versions", "plan_version_events", "plan_version_id", "'plan.version.proposed','plan.version.approved','plan.version.rejected'"),
        ("tasks", "task_events", "task_id", "'task.created'"),
    )
    for parent, table, fk, types in specs:
        op.execute(f"""
            CREATE TABLE work.{table} (
                event_id uuid PRIMARY KEY,
                {fk} uuid NOT NULL REFERENCES work.{parent}(id) ON DELETE RESTRICT,
                aggregate_sequence bigint NOT NULL CHECK (aggregate_sequence > 0),
                aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
                event_type text NOT NULL CHECK (event_type IN ({types})),
                schema_version integer NOT NULL CHECK (schema_version = 1),
                source text NOT NULL, subject text NOT NULL, occurred_at timestamptz NOT NULL, correlation_id uuid NOT NULL,
                causation_id uuid, actor_type text NOT NULL CHECK (actor_type IN ('USER','MANAGER','SERVICE','SYSTEM')),
                actor_id uuid, reason_code text, from_status text, to_status text, data jsonb NOT NULL,
                UNIQUE({fk},aggregate_sequence)
            )
        """)
        op.execute(f"ALTER TABLE work.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY p_{table}_tenant ON work.{table} TO ai_res_api_group
            USING (EXISTS (SELECT 1 FROM work.{parent} p WHERE p.id = {fk}))
        """)
        op.execute(f"""
            CREATE POLICY p_{table}_migration ON work.{table} TO ai_res_owner
            USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
            WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        """)
        op.execute(f"GRANT SELECT, INSERT ON work.{table} TO ai_res_api_group")
        op.execute(f"""
            CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON work.{table}
            FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()
        """)
        op.execute(f"""
            CREATE CONSTRAINT TRIGGER trg_{table}_sequence AFTER INSERT ON work.{table}
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous(
                '{fk}','work.{parent}','work.{table}','{fk}')
        """)
        op.execute(f"""
            CREATE CONSTRAINT TRIGGER trg_{parent}_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.{parent}
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous(
                'id','work.{parent}','work.{table}','{fk}')
        """)
    op.execute("INSERT INTO audit.aggregate_types(code) VALUES ('PLAN_VERSION'), ('TASK')")
    op.execute(OUTBOX_FUNCTION)
    op.execute("""
        CREATE FUNCTION work.require_unsealed_interaction() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        DECLARE sequence_number bigint;
        BEGIN
            SELECT i.last_event_sequence INTO sequence_number FROM work.manager_interactions i
            WHERE i.id=NEW.interaction_id AND i.organization_id=NEW.organization_id AND i.project_id=NEW.project_id
            FOR NO KEY UPDATE;
            IF sequence_number IS DISTINCT FROM 0 THEN
                RAISE EXCEPTION 'Manager interaction attachments are sealed' USING ERRCODE='integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $f$
    """)
    op.execute("""
        CREATE TRIGGER trg_manager_interaction_attachments_sealed BEFORE INSERT ON work.manager_interaction_attachments
        FOR EACH ROW EXECUTE FUNCTION work.require_unsealed_interaction()
    """)


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove event history.")
