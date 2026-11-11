"""PDB-0002b..0004: operations, operation_events, work (epics, tasks, task_dependencies), sequence/terminal/append-only guards (S05 slice B).

Revision ID: 8e4a6b13c2d7
Revises: 5c1d2e8f7a90

Greenfield (ADR-011): `work.tasks.operation_id` is NOT NULL with UNIQUE(operation_id, id) from the first revision. Final constraints, no backfill.
Event sequence integrity (PERSIST-012) is enforced by the database at COMMIT, in addition to the repository contract (lock the aggregate row,
bump last_event_sequence, insert that sequence): MAX()+1 is neither needed nor sufficient. Event history is append-only for every principal.
Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "8e4a6b13c2d7"
down_revision: str | None = "5c1d2e8f7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = ("organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
         "AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid")
COMMON = """row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"""
TERMINAL = "('SUCCEEDED','PARTIALLY_SUCCEEDED','FAILED','CANCELLED')"
OP_TERMINAL_ARGS = "'status','SUCCEEDED','PARTIALLY_SUCCEEDED','FAILED','CANCELLED'"

FUNCTIONS = """
CREATE FUNCTION platform.freeze_when_status_in() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE i int;
BEGIN  -- TG_ARGV[0] = status column, TG_ARGV[1..] = terminal values: a terminal aggregate is never modified again (no reopening)
  FOR i IN 1 .. TG_NARGS - 1 LOOP
    IF to_jsonb(OLD) ->> TG_ARGV[0] = TG_ARGV[i] THEN
      RAISE EXCEPTION '%.% is terminal (%): modification rejected', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[i] USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $f$;

CREATE FUNCTION platform.assert_event_sequence_contiguous() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE pid uuid; last_seq bigint; mx bigint; seq bigint; has_prev boolean;
BEGIN  -- deferred to COMMIT, O(log n) per call. Args: [0] field of NEW holding the aggregate id, [1] aggregate table, [2] event table, [3] event FK column.
  pid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  EXECUTE format('SELECT last_event_sequence FROM %s WHERE id = $1', TG_ARGV[1]::regclass) INTO last_seq USING pid;
  IF last_seq IS NULL THEN RETURN NULL; END IF;  -- aggregate invisible/absent: the FK and RLS already decide
  EXECUTE format('SELECT coalesce(max(aggregate_sequence), 0) FROM %s WHERE %I = $1', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO mx USING pid;
  IF mx <> last_seq THEN
    RAISE EXCEPTION 'event sequence of % is not contiguous: last_event_sequence=%, max event sequence=%', pid, last_seq, mx USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_RELID <> TG_ARGV[2]::regclass THEN RETURN NULL; END IF;  -- aggregate-row call: the maximum matches the counter
  seq := (to_jsonb(NEW) ->> 'aggregate_sequence')::bigint;  -- event-row call: every event except the first needs its predecessor (induction => no gaps; events are append-only)
  IF seq > 1 THEN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE %I = $1 AND aggregate_sequence = $2)', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO has_prev USING pid, seq - 1;  -- EXECUTE does not set FOUND
    IF NOT has_prev THEN
      RAISE EXCEPTION 'event sequence of % has a gap before %', pid, seq USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NULL;
END $f$;

CREATE FUNCTION work.require_open_operation() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE st text;
BEGIN  -- ADR-012: a Task is created only inside an active, non-terminal Operation; rework after terminal = a new Operation (ADR-034)
  IF NEW.operation_id IS NULL THEN RETURN NEW; END IF;  -- the NOT NULL constraint reports this case
  SELECT status INTO st FROM operations.operations WHERE id = NEW.operation_id FOR SHARE;  -- conflicts with a concurrent status UPDATE: no child can slip under a terminal Operation
  IF st IS NULL OR st IN ('SUCCEEDED','PARTIALLY_SUCCEEDED','FAILED','CANCELLED') THEN
    RAISE EXCEPTION 'task requires an open operation (operation % is %)', NEW.operation_id, coalesce(st, 'not visible') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
"""

TABLES = f"""
CREATE TABLE operations.operation_types (
    code text CONSTRAINT pk_operation_types PRIMARY KEY CONSTRAINT ck_operation_types_code CHECK (code ~ '^[A-Z][A-Z_]*$'));
INSERT INTO operations.operation_types (code) VALUES ('MANAGER_MESSAGE'), ('TASK_EXECUTION'), ('SOURCE_INGESTION'), ('PLAN_EXECUTION');

CREATE TABLE operations.operations (
    id uuid CONSTRAINT pk_operations PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    parent_operation_id uuid NULL,
    operation_type text NOT NULL CONSTRAINT fk_operations_operation_type_operation_types REFERENCES operations.operation_types(code) ON DELETE RESTRICT,
    status text NOT NULL CONSTRAINT ck_operations_status CHECK (status IN ('ACCEPTED','QUEUED','RUNNING','WAITING_FOR_HUMAN','WAITING_FOR_DEPENDENCY','RETRYING','CANCEL_REQUESTED','SUCCEEDED','PARTIALLY_SUCCEEDED','FAILED','CANCELLED')),
    initiator_type text NOT NULL CONSTRAINT ck_operations_initiator_type CHECK (initiator_type IN ('USER','SYSTEM','MANAGER','SERVICE')),
    initiator_id uuid NULL,
    idempotency_scope text NOT NULL,
    request_fingerprint bytea NOT NULL CONSTRAINT ck_operations_request_fingerprint CHECK (octet_length(request_fingerprint) = 32),
    completion_policy_version text NOT NULL,
    completion_policy_snapshot jsonb NOT NULL,
    correlation_id uuid NOT NULL, causation_id uuid NULL,
    workflow_id text NULL, workflow_run_id text NULL,
    progress_version bigint NOT NULL DEFAULT 0 CONSTRAINT ck_operations_progress_version CHECK (progress_version >= 0),
    progress_snapshot jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    result_ref jsonb NULL, problem_ref jsonb NULL,
    cancel_requested_at timestamptz NULL, started_at timestamptz NULL, completed_at timestamptz NULL,
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_operations_last_event_sequence CHECK (last_event_sequence >= 0),
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON.format(t="operations")},
    CONSTRAINT ck_operations_parent_not_self CHECK (parent_operation_id IS NULL OR parent_operation_id <> id),
    CONSTRAINT ck_operations_completed_iff_terminal CHECK ((status IN {TERMINAL}) = (completed_at IS NOT NULL)),
    CONSTRAINT uq_operations_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_operations_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_operations_parent_operation_id_operations FOREIGN KEY (organization_id, project_id, parent_operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_operations_project_id_created_at ON operations.operations (project_id, created_at DESC);
CREATE INDEX ix_operations_parent_operation_id ON operations.operations (parent_operation_id) WHERE parent_operation_id IS NOT NULL;
CREATE INDEX ix_operations_active_status ON operations.operations (status, updated_at) WHERE status NOT IN {TERMINAL};

CREATE TABLE operations.operation_events (
    event_id uuid CONSTRAINT pk_operation_events PRIMARY KEY,
    operation_id uuid NOT NULL CONSTRAINT fk_operation_events_operation_id_operations REFERENCES operations.operations(id) ON DELETE RESTRICT,
    aggregate_sequence bigint NOT NULL CONSTRAINT ck_operation_events_aggregate_sequence CHECK (aggregate_sequence > 0),
    aggregate_version bigint NOT NULL CONSTRAINT ck_operation_events_aggregate_version CHECK (aggregate_version > 0),
    event_type text NOT NULL, schema_version integer NOT NULL CONSTRAINT ck_operation_events_schema_version CHECK (schema_version > 0),
    source text NOT NULL, subject text NOT NULL, occurred_at timestamptz NOT NULL,
    correlation_id uuid NOT NULL, causation_id uuid NULL,
    actor_type text NOT NULL CONSTRAINT ck_operation_events_actor_type CHECK (actor_type IN ('SYSTEM','USER','MANAGER','WORKER','SERVICE')), actor_id uuid NULL, reason_code text NULL, from_status text NULL, to_status text NULL,
    data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_operation_events_operation_id_aggregate_sequence UNIQUE (operation_id, aggregate_sequence));
CREATE INDEX ix_operation_events_operation_id_occurred_at ON operations.operation_events (operation_id, occurred_at DESC);

CREATE TABLE work.epics (
    id uuid CONSTRAINT pk_epics PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    title text NOT NULL CONSTRAINT ck_epics_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    goal text NULL, scope_description text NULL, outcome_criteria text NULL,
    status text NOT NULL CONSTRAINT ck_epics_status CHECK (status ~ '^[A-Z][A-Z_]*$'),
    priority text NULL, owner_user_id uuid NULL,
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON.format(t="epics")},
    CONSTRAINT uq_epics_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_epics_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_epics_organization_id_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);

CREATE TABLE work.tasks (
    id uuid CONSTRAINT pk_tasks PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    derived_from_task_id uuid NULL,
    task_type text NOT NULL CONSTRAINT ck_tasks_task_type CHECK (task_type ~ '^[A-Z][A-Z_]*$'),
    title text NOT NULL CONSTRAINT ck_tasks_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    description text NULL,
    acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_tasks_acceptance_criteria CHECK (jsonb_typeof(acceptance_criteria) = 'array'),
    status text NOT NULL CONSTRAINT ck_tasks_status CHECK (status ~ '^[A-Z][A-Z_]*$'),
    priority text NULL,
    initiator_type text NOT NULL CONSTRAINT ck_tasks_initiator_type CHECK (initiator_type IN ('USER','SYSTEM','MANAGER','SERVICE')),
    initiator_id uuid NULL, owner_user_id uuid NULL,
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON.format(t="tasks")},
    CONSTRAINT ck_tasks_derived_not_self CHECK (derived_from_task_id IS NULL OR derived_from_task_id <> id),
    CONSTRAINT uq_tasks_operation_id_id UNIQUE (operation_id, id),
    CONSTRAINT uq_tasks_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_tasks_operation_id_operations FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_tasks_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_tasks_derived_from_task_id_tasks FOREIGN KEY (organization_id, project_id, derived_from_task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_tasks_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_tasks_operation_id_status_priority ON work.tasks (operation_id, status, priority);
CREATE INDEX ix_tasks_epic_id ON work.tasks (epic_id);

CREATE TABLE work.task_dependencies (
    id uuid CONSTRAINT pk_task_dependencies PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    task_id uuid NOT NULL, depends_on_task_id uuid NOT NULL,
    dependency_type text NOT NULL DEFAULT 'BLOCKS' CONSTRAINT ck_task_dependencies_dependency_type CHECK (dependency_type IN ('BLOCKS')),
    created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_task_dependencies_not_self CHECK (task_id <> depends_on_task_id),
    CONSTRAINT uq_task_dependencies_task_id_depends_on_task_id UNIQUE (task_id, depends_on_task_id),
    CONSTRAINT fk_task_dependencies_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_dependencies_depends_on_task_id_tasks FOREIGN KEY (organization_id, project_id, depends_on_task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_task_dependencies_depends_on_task_id ON work.task_dependencies (depends_on_task_id);
"""

# table -> (immutable columns, grants). RLS predicate is SCOPE for all tables here; events go through the parent aggregate.
MUTABLE = {
    "operations.operations": ("id", "organization_id", "project_id", "parent_operation_id", "operation_type", "initiator_type", "initiator_id",
                              "idempotency_scope", "request_fingerprint", "correlation_id", "completion_policy_version", "completion_policy_snapshot", "created_at"),  # the policy snapshot is frozen at creation
    "work.epics": ("id", "organization_id", "project_id", "created_at"),
    "work.tasks": ("id", "organization_id", "project_id", "operation_id", "epic_id", "derived_from_task_id", "initiator_type", "initiator_id", "created_at"),
}
EVENT_POLICY = ("EXISTS (SELECT 1 FROM operations.operations o WHERE o.id = operation_id AND o.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
                "AND o.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")


def _rls(table: str, predicate: str, grants: str) -> None:
    name = table.split(".")[1]
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({predicate}) WITH CHECK ({predicate})")
    op.execute(f"GRANT {grants} ON {table} TO ai_res_api_group")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute(TABLES)
    for table, immutable in MUTABLE.items():
        name = table.split(".")[1]
        _rls(table, SCOPE, "SELECT, INSERT, UPDATE")
        op.execute(f"CREATE TRIGGER trg_{name}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
        cols = ", ".join(f"'{c}'" for c in immutable)
        op.execute(f"CREATE TRIGGER trg_{name}_immutable_columns BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")
    # Terminal Operations are frozen (a terminal status is never reopened and nothing else changes after it).
    op.execute(f"CREATE TRIGGER trg_operations_freeze_terminal BEFORE UPDATE ON operations.operations FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in({OP_TERMINAL_ARGS})")
    op.execute("CREATE TRIGGER trg_tasks_require_open_operation BEFORE INSERT ON work.tasks FOR EACH ROW EXECUTE FUNCTION work.require_open_operation()")
    # Event history: append-only for every principal (privileges AND triggers), RLS through the parent aggregate.
    _rls("operations.operation_events", EVENT_POLICY, "SELECT, INSERT")
    op.execute("CREATE TRIGGER trg_operation_events_append_only BEFORE UPDATE OR DELETE ON operations.operation_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE TRIGGER trg_operation_events_no_truncate BEFORE TRUNCATE ON operations.operation_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_operation_events_sequence AFTER INSERT ON operations.operation_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_event_sequence_contiguous('operation_id', 'operations.operations', 'operations.operation_events', 'operation_id')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_operations_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON operations.operations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'operations.operations', 'operations.operation_events', 'operation_id')")
    _rls("work.task_dependencies", SCOPE, "SELECT, INSERT")
    # Reference registry (ADR-013): runtime read-only, changed only by revisions; exempt from RLS in rls_coverage.sql with a reason.
    op.execute("GRANT SELECT ON operations.operation_types TO ai_res_api_group")


def downgrade() -> None:
    raise NotImplementedError("PDB-0002b..0004 create domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
