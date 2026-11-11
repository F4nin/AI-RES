"""PDB-0006/0007 (part): audit (aggregate_types, outbox_events, inbox_messages, audit_events) and platform.idempotency_records, S05 slice D.

Revision ID: d4c18a7e5b92
Revises: b27f90c6d315

ADR-034: the API appends to outbox/audit (INSERT-only, no SELECT/UPDATE/DELETE); the outbox dispatcher and the event consumer are cross-tenant by
design (explicit `USING (true)` policies for exactly those two service groups, allow-listed in rls_coverage.sql) and change only delivery/progress
columns; the auditor reads audit_events per organization. Projection + event + outbox atomicity is completed by a deferred check that every outbox row
describes a real event of its aggregate. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "d4c18a7e5b92"
down_revision: str | None = "b27f90c6d315"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
PRJ = "NULLIF(current_setting('app.project_id', true), '')::uuid"
SCOPE = f"organization_id = {ORG} AND project_id = {PRJ}"

FUNCTIONS = """
CREATE FUNCTION audit.assert_outbox_matches_event() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE found boolean; op_id uuid;
BEGIN  -- deferred to COMMIT: an outbox row without its event (or for another aggregate/sequence) is an orphan and rolls the whole transaction back
  IF NEW.aggregate_type = 'OPERATION' THEN
    SELECT EXISTS (SELECT 1 FROM operations.operation_events e WHERE e.event_id = NEW.event_id AND e.operation_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    op_id := NEW.aggregate_id;
  ELSIF NEW.aggregate_type = 'WORKER_RUN' THEN
    SELECT EXISTS (SELECT 1 FROM agents.worker_run_events e WHERE e.event_id = NEW.event_id AND e.worker_run_id = NEW.aggregate_id
                    AND e.aggregate_sequence = NEW.aggregate_sequence AND e.event_type = NEW.event_type AND e.schema_version = NEW.schema_version) INTO found;
    SELECT r.operation_id INTO op_id FROM agents.worker_runs r WHERE r.id = NEW.aggregate_id;
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
     OR NEW.envelope ->> 'type' IS DISTINCT FROM 'com.aires.' || NEW.event_type || '.v' || NEW.schema_version
     OR NEW.envelope #>> '{data,eventId}' IS DISTINCT FROM NEW.event_id::text
     OR NEW.envelope #>> '{data,organizationId}' IS DISTINCT FROM NEW.organization_id::text
     OR NEW.envelope #>> '{data,projectId}' IS DISTINCT FROM NEW.project_id::text
     OR NEW.envelope #>> '{data,aggregateType}' IS DISTINCT FROM NEW.aggregate_type
     OR NEW.envelope #>> '{data,aggregateId}' IS DISTINCT FROM NEW.aggregate_id::text
     OR NEW.envelope #>> '{data,aggregateSequence}' IS DISTINCT FROM NEW.aggregate_sequence::text
     OR NEW.envelope #>> '{data,operationId}' IS DISTINCT FROM op_id::text
     OR NEW.envelope ->> 'subject' IS DISTINCT FROM (CASE NEW.aggregate_type WHEN 'OPERATION' THEN 'operations' ELSE 'worker-runs' END) || '/' || NEW.aggregate_id::text
     OR NEW.envelope ->> 'source' IS DISTINCT FROM (CASE NEW.aggregate_type WHEN 'OPERATION' THEN 'urn:aires:operations' ELSE 'urn:aires:worker-runs' END)
     OR NEW.envelope ->> 'dataschema' IS DISTINCT FROM 'urn:aires:schemas:com.aires.' || NEW.event_type || '.v' || NEW.schema_version THEN
    RAISE EXCEPTION 'outbox row % has an envelope that does not match its event/tenant columns', NEW.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END $f$;
"""

TABLES = """
CREATE TABLE audit.aggregate_types (
    code text CONSTRAINT pk_aggregate_types PRIMARY KEY CONSTRAINT ck_aggregate_types_code CHECK (code ~ '^[A-Z][A-Z_]*$'));
INSERT INTO audit.aggregate_types (code) VALUES ('OPERATION'), ('WORKER_RUN');

CREATE TABLE audit.outbox_events (
    id uuid CONSTRAINT pk_outbox_events PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    event_id uuid NOT NULL,
    destination text NOT NULL CONSTRAINT ck_outbox_events_destination CHECK (length(destination) BETWEEN 1 AND 200),
    aggregate_type text NOT NULL CONSTRAINT fk_outbox_events_aggregate_type_aggregate_types REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT,
    aggregate_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL CONSTRAINT ck_outbox_events_aggregate_sequence CHECK (aggregate_sequence > 0),
    event_type text NOT NULL,
    schema_version integer NOT NULL CONSTRAINT ck_outbox_events_schema_version CHECK (schema_version > 0),
    envelope jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CONSTRAINT ck_outbox_events_status CHECK (status IN ('PENDING','IN_FLIGHT','PUBLISHED','QUARANTINED')),
    available_at timestamptz NOT NULL DEFAULT now(),
    attempt_count integer NOT NULL DEFAULT 0 CONSTRAINT ck_outbox_events_attempt_count CHECK (attempt_count >= 0),
    last_error_code text NULL CONSTRAINT ck_outbox_events_last_error_code CHECK (last_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'), lease_owner text NULL, lease_until timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz NULL,
    CONSTRAINT ck_outbox_events_lease_iff_in_flight CHECK ((status = 'IN_FLIGHT') = (lease_owner IS NOT NULL AND lease_until IS NOT NULL) AND (lease_owner IS NULL) = (lease_until IS NULL)),
    CONSTRAINT ck_outbox_events_published_iff_published CHECK ((status = 'PUBLISHED') = (published_at IS NOT NULL)),
    CONSTRAINT uq_outbox_events_event_id_destination UNIQUE (event_id, destination),
    CONSTRAINT uq_outbox_events_aggregate_type_aggregate_id_aggregate_sequence_destination UNIQUE (aggregate_type, aggregate_id, aggregate_sequence, destination),
    CONSTRAINT fk_outbox_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_outbox_events_pending ON audit.outbox_events (available_at, created_at) WHERE status IN ('PENDING','IN_FLIGHT');

CREATE TABLE audit.inbox_messages (
    id uuid CONSTRAINT pk_inbox_messages PRIMARY KEY,
    consumer_name text NOT NULL CONSTRAINT ck_inbox_messages_consumer_name CHECK (length(consumer_name) BETWEEN 1 AND 200),
    event_id uuid NOT NULL,
    aggregate_type text NOT NULL CONSTRAINT fk_inbox_messages_aggregate_type_aggregate_types REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT,
    aggregate_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL CONSTRAINT ck_inbox_messages_aggregate_sequence CHECK (aggregate_sequence > 0),
    status text NOT NULL CONSTRAINT ck_inbox_messages_status CHECK (status IN ('PROCESSING','PROCESSED','QUARANTINED')),
    payload_hash bytea NOT NULL CONSTRAINT ck_inbox_messages_payload_hash CHECK (octet_length(payload_hash) = 32),
    received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz NULL, error_code text NULL CONSTRAINT ck_inbox_messages_error_code CHECK (error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    CONSTRAINT ck_inbox_messages_processed_iff_processed CHECK ((status = 'PROCESSED') = (processed_at IS NOT NULL)),
    CONSTRAINT uq_inbox_messages_consumer_name_event_id UNIQUE (consumer_name, event_id));
CREATE INDEX ix_inbox_messages_consumer_name_status_received_at ON audit.inbox_messages (consumer_name, status, received_at);

CREATE TABLE audit.audit_events (
    id uuid CONSTRAINT pk_audit_events PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NULL,
    occurred_at timestamptz NOT NULL,
    actor_type text NOT NULL CONSTRAINT ck_audit_events_actor_type CHECK (actor_type IN ('USER','SYSTEM','MANAGER','SERVICE','WORKER_RUN')),
    actor_id uuid NULL,
    action text NOT NULL CONSTRAINT ck_audit_events_action CHECK (action ~ '^[A-Z][A-Z0-9_]*$'),
    object_type text NOT NULL CONSTRAINT ck_audit_events_object_type CHECK (object_type ~ '^[A-Z][A-Z0-9_]*$'),
    object_id uuid NULL,
    result text NOT NULL CONSTRAINT ck_audit_events_result CHECK (result IN ('SUCCEEDED','DENIED','FAILED')),
    reason_code text NULL,
    correlation_id uuid NOT NULL, causation_id uuid NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb, version_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_audit_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_audit_events_organization_id_occurred_at ON audit.audit_events (organization_id, occurred_at DESC);
CREATE INDEX ix_audit_events_actor_id ON audit.audit_events (actor_id) WHERE actor_id IS NOT NULL;
CREATE INDEX ix_audit_events_object ON audit.audit_events (object_type, object_id);

CREATE TABLE platform.idempotency_records (
    id uuid CONSTRAINT pk_idempotency_records PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NULL,
    scope_type text NOT NULL CONSTRAINT ck_idempotency_records_scope_type CHECK (scope_type ~ '^[A-Z][A-Z_]*$'),
    scope_id uuid NOT NULL,
    key_digest bytea NOT NULL CONSTRAINT ck_idempotency_records_key_digest CHECK (octet_length(key_digest) = 32),
    key_id text NOT NULL CONSTRAINT ck_idempotency_records_key_id CHECK (length(key_id) BETWEEN 1 AND 100),
    request_fingerprint bytea NOT NULL CONSTRAINT ck_idempotency_records_request_fingerprint CHECK (octet_length(request_fingerprint) = 32),
    resource_type text NULL, resource_id uuid NULL,
    status text NOT NULL CONSTRAINT ck_idempotency_records_status CHECK (status IN ('IN_PROGRESS','COMPLETED','REJECTED')),
    response_status integer NULL, response_body_ref jsonb NULL,
    created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, completed_at timestamptz NULL,
    CONSTRAINT ck_idempotency_records_completed_iff_finished CHECK ((status = 'IN_PROGRESS') = (completed_at IS NULL)),
    CONSTRAINT uq_idempotency_records_organization_id_scope_type_scope_id_key_digest UNIQUE (organization_id, scope_type, scope_id, key_digest),
    CONSTRAINT fk_idempotency_records_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_idempotency_records_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_idempotency_records_expires_at ON platform.idempotency_records (expires_at);
"""


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute(TABLES)

    # --- outbox: API INSERT-only (scoped); dispatcher cross-tenant, delivery columns only (ADR-034 (2), (4)) ---
    _enable("audit.outbox_events")
    op.execute(f"CREATE POLICY p_outbox_events_api_insert ON audit.outbox_events FOR INSERT TO ai_res_api_group WITH CHECK ({SCOPE})")
    op.execute("CREATE POLICY p_outbox_events_dispatcher_select ON audit.outbox_events FOR SELECT TO ai_res_outbox_group USING (true)")
    op.execute("CREATE POLICY p_outbox_events_dispatcher_update ON audit.outbox_events FOR UPDATE TO ai_res_outbox_group USING (true) WITH CHECK (true)")
    op.execute("GRANT INSERT ON audit.outbox_events TO ai_res_api_group")
    op.execute("GRANT SELECT ON audit.outbox_events TO ai_res_outbox_group")
    op.execute("GRANT UPDATE (status, available_at, attempt_count, last_error_code, lease_owner, lease_until, published_at) ON audit.outbox_events TO ai_res_outbox_group")
    op.execute("CREATE TRIGGER trg_outbox_events_immutable_columns BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'id', 'organization_id', 'project_id', 'event_id', 'destination', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'event_type', 'schema_version', 'envelope', 'created_at')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_outbox_events_matches_event AFTER INSERT ON audit.outbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit.assert_outbox_matches_event()")

    # --- inbox: cross-tenant consumer, progress columns only ---
    _enable("audit.inbox_messages")
    op.execute("CREATE POLICY p_inbox_messages_consumer_all ON audit.inbox_messages FOR ALL TO ai_res_consumer_group USING (true) WITH CHECK (true)")
    op.execute("GRANT SELECT, INSERT ON audit.inbox_messages TO ai_res_consumer_group")
    op.execute("GRANT UPDATE (status, processed_at, error_code) ON audit.inbox_messages TO ai_res_consumer_group")
    op.execute("CREATE TRIGGER trg_inbox_messages_immutable_columns BEFORE UPDATE ON audit.inbox_messages FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'id', 'consumer_name', 'event_id', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'payload_hash', 'received_at')")

    # --- audit log: API INSERT-only; nobody rewrites it; the auditor reads one organization at a time ---
    _enable("audit.audit_events")
    op.execute(f"CREATE POLICY p_audit_events_api_insert ON audit.audit_events FOR INSERT TO ai_res_api_group WITH CHECK (organization_id = {ORG} AND (project_id IS NULL OR project_id = {PRJ}))")
    op.execute(f"CREATE POLICY p_audit_events_auditor_select ON audit.audit_events FOR SELECT TO ai_res_auditor_group USING (organization_id = {ORG})")
    op.execute("GRANT INSERT ON audit.audit_events TO ai_res_api_group")
    op.execute("GRANT SELECT ON audit.audit_events TO ai_res_auditor_group")
    op.execute("CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit.audit_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit.audit_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")

    # --- idempotency: scoped, fingerprint-bound, frozen once finished (ADR-024) ---
    _enable("platform.idempotency_records")
    pred = f"organization_id = {ORG} AND project_id IS NOT DISTINCT FROM {PRJ}"
    op.execute(f"CREATE POLICY p_idempotency_records_tenant_scope ON platform.idempotency_records FOR ALL TO ai_res_api_group USING ({pred}) WITH CHECK ({pred})")
    op.execute("GRANT SELECT, INSERT, UPDATE ON platform.idempotency_records TO ai_res_api_group")
    op.execute("CREATE TRIGGER trg_idempotency_records_immutable_columns BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'id', 'organization_id', 'project_id', 'scope_type', 'scope_id', 'key_digest', 'key_id', 'request_fingerprint', 'created_at', 'expires_at')")
    op.execute("CREATE TRIGGER trg_idempotency_records_freeze_finished BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'COMPLETED', 'REJECTED')")


def downgrade() -> None:
    raise NotImplementedError("PDB-0006 creates domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
