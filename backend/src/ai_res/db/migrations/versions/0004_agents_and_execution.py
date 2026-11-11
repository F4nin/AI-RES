"""PDB-0004/0005: agents (worker_runs, worker_run_events, worker_results) and execution (readiness_evaluations, readiness_check_results), S05 slice C.

Revision ID: b27f90c6d315
Revises: 8e4a6b13c2d7

Database-level Readiness Gate invariants (State Machine v1.2 `invariants`, Physical Model v1.2 §6): a started WorkerRun references exactly one COMPLETED
READY/READY_WITH_LIMITATIONS evaluation of the same run and that link never changes; evaluations, check results, results and event history are
insert-only for every principal; terminal runs are frozen. Transition legality and TOCTOU revalidation stay in the domain service (S13).
Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "b27f90c6d315"
down_revision: str | None = "8e4a6b13c2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = ("organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
         "AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid")
RUN_SCOPE = ("EXISTS (SELECT 1 FROM agents.worker_runs wr WHERE wr.id = worker_run_id AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
             "AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")
COMMON = """row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"""
TERMINAL_ARGS = "'status','COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED','FAILED','TIMED_OUT','CANCELLED'"
TERMINAL = "('COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED','FAILED','TIMED_OUT','CANCELLED')"
STARTED_ONLY = "('STARTING','RUNNING','WAITING_FOR_HUMAN','WAITING_FOR_DEPENDENCY','RESULT_SUBMITTED','VALIDATING','REVIEW_PENDING','QA_PENDING','COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED')"

FUNCTIONS = """
CREATE FUNCTION agents.guard_worker_run_start() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE st text; outcome text; num integer;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.started_with_readiness_evaluation_id IS NOT NULL
     AND NEW.started_with_readiness_evaluation_id IS DISTINCT FROM OLD.started_with_readiness_evaluation_id THEN
    RAISE EXCEPTION 'started_with_readiness_evaluation_id of a started WorkerRun is immutable' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.started_with_readiness_evaluation_id IS NOT NULL AND (TG_OP = 'INSERT' OR OLD.started_with_readiness_evaluation_id IS NULL) THEN
    IF TG_OP = 'UPDATE' THEN  -- serialises with execution.lock_run_for_evaluation(): a concurrent evaluation insert commits (or we do) before the check below, which then reads it
      PERFORM 1 FROM agents.worker_runs WHERE id = NEW.id FOR NO KEY UPDATE;
    END IF;
    SELECT evaluation_status, gate_outcome, evaluation_number INTO st, outcome, num FROM execution.readiness_evaluations
     WHERE id = NEW.started_with_readiness_evaluation_id AND worker_run_id = NEW.id;
    IF NOT FOUND THEN RETURN NEW; END IF;  -- absent or another run's evaluation: the deferred composite FK rejects it at COMMIT
    IF st <> 'COMPLETED' OR outcome NOT IN ('READY', 'READY_WITH_LIMITATIONS') THEN
      RAISE EXCEPTION 'a WorkerRun may start only with a COMPLETED READY/READY_WITH_LIMITATIONS evaluation (got % / %)', st, coalesce(outcome, 'NULL')
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM execution.readiness_evaluations n WHERE n.worker_run_id = NEW.id AND n.evaluation_number > num) THEN
      RAISE EXCEPTION 'the start evaluation (number %) is not the latest of the run: a newer evaluation exists, so this one is stale', num
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION agents.assert_worker_run_started_ready() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE r record;
BEGIN  -- deferred to COMMIT: re-checks the start evaluation in its FINAL state, so inserting the evaluation after the run (same transaction) cannot bypass the Gate
  IF NEW.started_with_readiness_evaluation_id IS NULL THEN RETURN NULL; END IF;
  SELECT e.evaluation_number AS num, e.evaluation_status, e.gate_outcome, e.context_package_version_id AS cpv, e.worker_definition_version_id AS wdv, e.output_contract_version AS ocv
    INTO r FROM execution.readiness_evaluations e WHERE e.id = NEW.started_with_readiness_evaluation_id AND e.worker_run_id = NEW.id;
  IF NOT FOUND THEN RETURN NULL; END IF;  -- the composite FK reports absent or foreign evaluations
  IF r.evaluation_status <> 'COMPLETED' OR r.gate_outcome NOT IN ('READY', 'READY_WITH_LIMITATIONS') THEN
    RAISE EXCEPTION 'a WorkerRun may start only with a COMPLETED READY/READY_WITH_LIMITATIONS evaluation (got % / %)', r.evaluation_status, coalesce(r.gate_outcome, 'NULL')
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF r.cpv <> NEW.context_package_version_id OR r.wdv <> NEW.worker_definition_version_id OR r.ocv <> NEW.output_contract_version THEN
    RAISE EXCEPTION 'the start evaluation was computed for other ContextPackageVersion/WorkerDefinitionVersion/output contract than the run uses (stale evaluation)'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM execution.readiness_evaluations n WHERE n.worker_run_id = NEW.id AND n.evaluation_number > r.num) THEN
    RAISE EXCEPTION 'the start evaluation (number %) is not the latest of the run: a newer evaluation exists, so this one is stale', r.num  -- committed concurrently or inserted later in this transaction
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END $f$;

CREATE FUNCTION agents.require_started_open_run() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE started uuid; st text;
BEGIN  -- a WorkerResult exists only for a run that passed the Readiness Gate and is not terminal (results are immutable: a bad row could never be corrected)
  SELECT started_with_readiness_evaluation_id, status INTO started, st FROM agents.worker_runs WHERE id = NEW.worker_run_id FOR NO KEY UPDATE;  -- waits for a concurrent status UPDATE or a twin insert (FOR SHARE then deadlocked on the unique index)
  IF NOT FOUND THEN RETURN NEW; END IF;  -- absent or invisible run: the composite FK reports it
  IF started IS NULL THEN
    RAISE EXCEPTION 'WorkerRun % has not started with a ReadinessEvaluation: no result can be stored', NEW.worker_run_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF st IN ('COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED','FAILED','TIMED_OUT','CANCELLED') THEN
    RAISE EXCEPTION 'WorkerRun % is terminal (%): no result can be stored', NEW.worker_run_id, st USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION execution.lock_run_for_evaluation() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- the FK only takes KEY SHARE on the run, which does not conflict with the UPDATE that starts it: lock explicitly so "new evaluation" and "start with the previous one" serialise
  PERFORM 1 FROM agents.worker_runs WHERE id = NEW.worker_run_id FOR NO KEY UPDATE;
  RETURN NEW;
END $f$;

CREATE FUNCTION execution.guard_check_result_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE ts timestamptz;
BEGIN  -- an evaluation is immutable once committed: its check results are written in the same transaction (created_at defaults to now())
  SELECT created_at INTO ts FROM execution.readiness_evaluations WHERE id = NEW.readiness_evaluation_id;
  IF ts IS NOT NULL AND ts <> now() THEN
    RAISE EXCEPTION 'check results must be written in the transaction that created the evaluation' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
"""

TABLES = f"""
ALTER TABLE work.tasks ADD CONSTRAINT uq_tasks_organization_id_project_id_operation_id_id UNIQUE (organization_id, project_id, operation_id, id);

CREATE TABLE agents.worker_runs (
    id uuid CONSTRAINT pk_worker_runs PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    operation_id uuid NOT NULL, task_id uuid NOT NULL,
    worker_definition_version_id uuid NOT NULL,
    status text NOT NULL CONSTRAINT ck_worker_runs_status CHECK (status IN ('CREATED','PREPARING','WAITING_FOR_GATE','BLOCKED','QUEUED','STARTING','RUNNING','WAITING_FOR_HUMAN','WAITING_FOR_DEPENDENCY','RESULT_SUBMITTED','VALIDATING','REVIEW_PENDING','QA_PENDING','COMPLETED','REWORK_REQUIRED','REJECTED','UNVERIFIED','FAILED','TIMED_OUT','CANCELLED','CANCEL_REQUESTED')),
    derived_from_worker_run_id uuid NULL,
    derivation_reason text NULL CONSTRAINT ck_worker_runs_derivation_reason CHECK (derivation_reason IN ('RETRY','REWORK','NEW_CONTEXT','INDEPENDENT_REVIEW','REEXECUTION','SPECIALIST_HANDOFF')),
    attempt_number integer NOT NULL DEFAULT 1 CONSTRAINT ck_worker_runs_attempt_number CHECK (attempt_number > 0),
    context_package_version_id uuid NOT NULL,
    latest_readiness_evaluation_id uuid NULL, started_with_readiness_evaluation_id uuid NULL,
    workflow_id text NULL, workflow_run_id text NULL,
    input_contract_version text NOT NULL, output_contract_version text NOT NULL,
    execution_envelope_ref jsonb NULL, result_ref jsonb NULL, problem_ref jsonb NULL,
    started_at timestamptz NULL, finished_at timestamptz NULL, deadline_at timestamptz NULL,
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_worker_runs_last_event_sequence CHECK (last_event_sequence >= 0),
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON.format(t="worker_runs")},
    CONSTRAINT ck_worker_runs_lineage_has_reason CHECK ((derived_from_worker_run_id IS NULL) = (derivation_reason IS NULL)),
    CONSTRAINT ck_worker_runs_derived_not_self CHECK (derived_from_worker_run_id IS NULL OR derived_from_worker_run_id <> id),
    CONSTRAINT ck_worker_runs_finished_iff_terminal CHECK ((status IN {TERMINAL}) = (finished_at IS NOT NULL)),
    CONSTRAINT ck_worker_runs_started_has_evaluation CHECK ((status NOT IN {STARTED_ONLY} AND started_at IS NULL) OR started_with_readiness_evaluation_id IS NOT NULL),
    CONSTRAINT uq_worker_runs_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT uq_worker_runs_organization_id_project_id_task_id_attempt_number UNIQUE (organization_id, project_id, task_id, attempt_number),  -- a retried command cannot create a second run for the same attempt
    CONSTRAINT fk_worker_runs_operation_id_task_id_tasks FOREIGN KEY (organization_id, project_id, operation_id, task_id) REFERENCES work.tasks(organization_id, project_id, operation_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_worker_runs_derived_from_worker_run_id_worker_runs FOREIGN KEY (organization_id, project_id, derived_from_worker_run_id) REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_worker_runs_operation_id_created_at ON agents.worker_runs (operation_id, created_at DESC);
CREATE INDEX ix_worker_runs_task_id_created_at ON agents.worker_runs (task_id, created_at DESC);
CREATE INDEX ix_worker_runs_lineage ON agents.worker_runs (derived_from_worker_run_id) WHERE derived_from_worker_run_id IS NOT NULL;
CREATE INDEX ix_worker_runs_schedulable ON agents.worker_runs (status, created_at) WHERE status IN ('CREATED','PREPARING','WAITING_FOR_GATE','QUEUED','STARTING');

CREATE TABLE execution.readiness_evaluations (
    id uuid CONSTRAINT pk_readiness_evaluations PRIMARY KEY,
    worker_run_id uuid NOT NULL CONSTRAINT fk_readiness_evaluations_worker_run_id_worker_runs REFERENCES agents.worker_runs(id) ON DELETE RESTRICT,
    evaluation_number integer NOT NULL CONSTRAINT ck_readiness_evaluations_evaluation_number CHECK (evaluation_number > 0),
    evaluation_status text NOT NULL CONSTRAINT ck_readiness_evaluations_evaluation_status CHECK (evaluation_status IN ('COMPLETED','EVALUATOR_ERROR')),
    gate_outcome text NULL CONSTRAINT ck_readiness_evaluations_gate_outcome CHECK (gate_outcome IN ('READY','READY_WITH_LIMITATIONS','BLOCKED','STALE')),
    snapshot_hash bytea NOT NULL CONSTRAINT ck_readiness_evaluations_snapshot_hash CHECK (octet_length(snapshot_hash) = 32),
    task_version bigint NOT NULL, plan_version_id uuid NULL,
    worker_definition_version_id uuid NOT NULL, context_package_version_id uuid NOT NULL,
    ruleset_version text NOT NULL, policy_engine_version text NOT NULL,
    grant_snapshot_ref jsonb NOT NULL, tool_allowlist_snapshot jsonb NOT NULL,
    output_contract_version text NOT NULL, budget_profile_version text NOT NULL,
    dependency_snapshot jsonb NOT NULL, evaluator_version text NOT NULL,
    blockers jsonb NOT NULL DEFAULT '[]'::jsonb, limitations jsonb NOT NULL DEFAULT '[]'::jsonb, evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_readiness_evaluations_outcome_matches_status CHECK ((evaluation_status = 'COMPLETED') = (gate_outcome IS NOT NULL AND evaluated_at IS NOT NULL)),
    CONSTRAINT ck_readiness_evaluations_ready_without_blockers CHECK (gate_outcome IS DISTINCT FROM 'READY' OR blockers = '[]'::jsonb),
    CONSTRAINT uq_readiness_evaluations_worker_run_id_evaluation_number UNIQUE (worker_run_id, evaluation_number),
    CONSTRAINT uq_readiness_evaluations_worker_run_id_id UNIQUE (worker_run_id, id));
CREATE INDEX ix_readiness_evaluations_worker_run_id_created_at ON execution.readiness_evaluations (worker_run_id, created_at DESC);

CREATE TABLE execution.readiness_check_results (
    id uuid CONSTRAINT pk_readiness_check_results PRIMARY KEY,
    worker_run_id uuid NOT NULL, readiness_evaluation_id uuid NOT NULL,
    check_code text NOT NULL CONSTRAINT ck_readiness_check_results_check_code CHECK (check_code ~ '^[A-Z][A-Z0-9_]*$'),
    result text NOT NULL CONSTRAINT ck_readiness_check_results_result CHECK (result IN ('PASS','FAIL','WARN','NOT_APPLICABLE')),
    severity text NOT NULL CONSTRAINT ck_readiness_check_results_severity CHECK (severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
    reason_code text NULL, evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb, details jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_readiness_check_results_worker_run_id_readiness_evaluations FOREIGN KEY (worker_run_id, readiness_evaluation_id) REFERENCES execution.readiness_evaluations(worker_run_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_readiness_check_results_readiness_evaluation_id_check_code UNIQUE (readiness_evaluation_id, check_code));

ALTER TABLE agents.worker_runs
  ADD CONSTRAINT fk_worker_runs_latest_readiness_evaluation_id_readiness_evaluations FOREIGN KEY (id, latest_readiness_evaluation_id)
    REFERENCES execution.readiness_evaluations(worker_run_id, id) DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT fk_worker_runs_started_with_readiness_evaluation_id_readiness_evaluations FOREIGN KEY (id, started_with_readiness_evaluation_id)
    REFERENCES execution.readiness_evaluations(worker_run_id, id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE agents.worker_run_events (
    event_id uuid CONSTRAINT pk_worker_run_events PRIMARY KEY,
    worker_run_id uuid NOT NULL CONSTRAINT fk_worker_run_events_worker_run_id_worker_runs REFERENCES agents.worker_runs(id) ON DELETE RESTRICT,
    aggregate_sequence bigint NOT NULL CONSTRAINT ck_worker_run_events_aggregate_sequence CHECK (aggregate_sequence > 0),
    aggregate_version bigint NOT NULL CONSTRAINT ck_worker_run_events_aggregate_version CHECK (aggregate_version > 0),
    event_type text NOT NULL, schema_version integer NOT NULL CONSTRAINT ck_worker_run_events_schema_version CHECK (schema_version > 0),
    source text NOT NULL, subject text NOT NULL, occurred_at timestamptz NOT NULL,
    correlation_id uuid NOT NULL, causation_id uuid NULL,
    actor_type text NOT NULL CONSTRAINT ck_worker_run_events_actor_type CHECK (actor_type IN ('SYSTEM','USER','MANAGER','WORKER','SERVICE')), actor_id uuid NULL, reason_code text NULL, from_status text NULL, to_status text NULL,
    data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_worker_run_events_worker_run_id_aggregate_sequence UNIQUE (worker_run_id, aggregate_sequence));
CREATE INDEX ix_worker_run_events_worker_run_id_occurred_at ON agents.worker_run_events (worker_run_id, occurred_at DESC);

CREATE TABLE agents.worker_results (
    id uuid CONSTRAINT pk_worker_results PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, worker_run_id uuid NOT NULL,
    contract_version text NOT NULL,
    payload jsonb NOT NULL CONSTRAINT ck_worker_results_payload CHECK (jsonb_typeof(payload) = 'object'),
    payload_hash bytea NOT NULL CONSTRAINT ck_worker_results_payload_hash CHECK (octet_length(payload_hash) = 32),
    created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_worker_results_organization_id_project_id_worker_run_id UNIQUE (organization_id, project_id, worker_run_id),  -- scoped: a foreign tenant gets an FK error, not a unique-violation existence oracle
    CONSTRAINT fk_worker_results_worker_run_id_worker_runs FOREIGN KEY (organization_id, project_id, worker_run_id) REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT);
"""

APPEND_ONLY = {  # table -> (RLS predicate, short name)
    "execution.readiness_evaluations": RUN_SCOPE, "execution.readiness_check_results": RUN_SCOPE,
    "agents.worker_run_events": RUN_SCOPE, "agents.worker_results": SCOPE,
}
IMMUTABLE_RUN_COLUMNS = ("id", "organization_id", "project_id", "operation_id", "task_id", "worker_definition_version_id", "derived_from_worker_run_id",
                         "derivation_reason", "attempt_number", "context_package_version_id", "input_contract_version", "output_contract_version", "created_at")


def _rls(table: str, predicate: str, grants: str) -> None:
    name = table.split(".")[1]
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({predicate}) WITH CHECK ({predicate})")
    op.execute(f"GRANT {grants} ON {table} TO ai_res_api_group")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute(TABLES)
    _rls("agents.worker_runs", SCOPE, "SELECT, INSERT, UPDATE")
    cols = ", ".join(f"'{c}'" for c in IMMUTABLE_RUN_COLUMNS)
    op.execute("CREATE TRIGGER trg_worker_runs_touch BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
    op.execute(f"CREATE TRIGGER trg_worker_runs_immutable_columns BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")
    op.execute(f"CREATE TRIGGER trg_worker_runs_freeze_terminal BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in({TERMINAL_ARGS})")
    op.execute("CREATE TRIGGER trg_worker_runs_guard_start BEFORE INSERT OR UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_run_start()")
    op.execute("CREATE TRIGGER trg_worker_results_require_started_run BEFORE INSERT ON agents.worker_results FOR EACH ROW EXECUTE FUNCTION agents.require_started_open_run()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_worker_runs_started_ready AFTER INSERT OR UPDATE OF started_with_readiness_evaluation_id ON agents.worker_runs "
               "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION agents.assert_worker_run_started_ready()")
    op.execute("CREATE TRIGGER trg_worker_runs_require_open_operation BEFORE INSERT ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION work.require_open_operation()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_worker_runs_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON agents.worker_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'agents.worker_runs', 'agents.worker_run_events', 'worker_run_id')")
    for table, predicate in APPEND_ONLY.items():
        name = table.split(".")[1]
        _rls(table, predicate, "SELECT, INSERT")
        op.execute(f"CREATE TRIGGER trg_{name}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{name}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_worker_run_events_sequence AFTER INSERT ON agents.worker_run_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_event_sequence_contiguous('worker_run_id', 'agents.worker_runs', 'agents.worker_run_events', 'worker_run_id')")
    op.execute("CREATE TRIGGER trg_readiness_evaluations_lock_run BEFORE INSERT ON execution.readiness_evaluations FOR EACH ROW EXECUTE FUNCTION execution.lock_run_for_evaluation()")
    op.execute("CREATE TRIGGER trg_readiness_check_results_same_transaction BEFORE INSERT ON execution.readiness_check_results FOR EACH ROW EXECUTE FUNCTION execution.guard_check_result_insert()")


def downgrade() -> None:
    raise NotImplementedError("PDB-0004/0005 create domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
