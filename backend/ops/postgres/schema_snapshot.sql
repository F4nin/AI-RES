-- AI RES design snapshot of ai_res_db at Alembic head (S04). Regenerate: make db-snapshot. Do not edit by hand.

-- CATALOG
-- ROLE ai_res_api LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_api_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_auditor LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_auditor_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_backup LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_checkpointer_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_consumer_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_event_consumer LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_outbox_dispatcher LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_outbox_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- GRANT ai_res_api_group TO ai_res_api INHERIT=t SET=f
-- GRANT ai_res_auditor_group TO ai_res_auditor INHERIT=t SET=f
-- GRANT ai_res_consumer_group TO ai_res_event_consumer INHERIT=t SET=f
-- GRANT ai_res_outbox_group TO ai_res_outbox_dispatcher INHERIT=t SET=f
-- GRANT ai_res_owner TO ai_res_migrator INHERIT=f SET=t
-- DATABASE ACL ai_res_api=c/ai_res_owner,ai_res_auditor=c/ai_res_owner,ai_res_event_consumer=c/ai_res_owner,ai_res_migrator=c/ai_res_owner,ai_res_outbox_dispatcher=c/ai_res_owner,ai_res_owner=CTc/ai_res_owner

-- SCHEMA
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

CREATE SCHEMA agents;

ALTER SCHEMA agents OWNER TO ai_res_owner;

CREATE SCHEMA artifacts;

ALTER SCHEMA artifacts OWNER TO ai_res_owner;

CREATE SCHEMA audit;

ALTER SCHEMA audit OWNER TO ai_res_owner;

CREATE SCHEMA context;

ALTER SCHEMA context OWNER TO ai_res_owner;

CREATE SCHEMA decisions;

ALTER SCHEMA decisions OWNER TO ai_res_owner;

CREATE SCHEMA execution;

ALTER SCHEMA execution OWNER TO ai_res_owner;

CREATE SCHEMA governance;

ALTER SCHEMA governance OWNER TO ai_res_owner;

CREATE SCHEMA iam;

ALTER SCHEMA iam OWNER TO ai_res_owner;

CREATE SCHEMA integrations;

ALTER SCHEMA integrations OWNER TO ai_res_owner;

CREATE SCHEMA knowledge;

ALTER SCHEMA knowledge OWNER TO ai_res_owner;

CREATE SCHEMA operations;

ALTER SCHEMA operations OWNER TO ai_res_owner;

CREATE SCHEMA organization;

ALTER SCHEMA organization OWNER TO ai_res_owner;

CREATE SCHEMA platform;

ALTER SCHEMA platform OWNER TO ai_res_owner;

CREATE SCHEMA project;

ALTER SCHEMA project OWNER TO ai_res_owner;

CREATE SCHEMA requirements;

ALTER SCHEMA requirements OWNER TO ai_res_owner;

CREATE SCHEMA sources;

ALTER SCHEMA sources OWNER TO ai_res_owner;

CREATE SCHEMA traceability;

ALTER SCHEMA traceability OWNER TO ai_res_owner;

CREATE SCHEMA work;

ALTER SCHEMA work OWNER TO ai_res_owner;

CREATE FUNCTION agents.assert_worker_run_started_ready() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
END $$;

ALTER FUNCTION agents.assert_worker_run_started_ready() OWNER TO ai_res_owner;

CREATE FUNCTION agents.guard_worker_run_start() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
END $$;

ALTER FUNCTION agents.guard_worker_run_start() OWNER TO ai_res_owner;

CREATE FUNCTION agents.require_started_open_run() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
END $$;

ALTER FUNCTION agents.require_started_open_run() OWNER TO ai_res_owner;

CREATE FUNCTION audit.assert_outbox_matches_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
END $$;

ALTER FUNCTION audit.assert_outbox_matches_event() OWNER TO ai_res_owner;

CREATE FUNCTION execution.guard_check_result_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE ts timestamptz;
BEGIN  -- an evaluation is immutable once committed: its check results are written in the same transaction (created_at defaults to now())
  SELECT created_at INTO ts FROM execution.readiness_evaluations WHERE id = NEW.readiness_evaluation_id;
  IF ts IS NOT NULL AND ts <> now() THEN
    RAISE EXCEPTION 'check results must be written in the transaction that created the evaluation' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION execution.guard_check_result_insert() OWNER TO ai_res_owner;

CREATE FUNCTION execution.lock_run_for_evaluation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- the FK only takes KEY SHARE on the run, which does not conflict with the UPDATE that starts it: lock explicitly so "new evaluation" and "start with the previous one" serialise
  PERFORM 1 FROM agents.worker_runs WHERE id = NEW.worker_run_id FOR NO KEY UPDATE;
  RETURN NEW;
END $$;

ALTER FUNCTION execution.lock_run_for_evaluation() OWNER TO ai_res_owner;

CREATE FUNCTION platform.assert_event_sequence_contiguous() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
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
END $_$;

ALTER FUNCTION platform.assert_event_sequence_contiguous() OWNER TO ai_res_owner;

CREATE FUNCTION platform.forbid_unset() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN  -- once set, these columns (revoked_at, used_at, ...) never change again: a revoked session / used recovery code cannot be resurrected
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF o -> c <> 'null'::jsonb AND n -> c IS DISTINCT FROM o -> c THEN
      RAISE EXCEPTION 'column %.% is write-once', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.forbid_unset() OWNER TO ai_res_owner;

CREATE FUNCTION platform.freeze_when_status_in() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE i int;
BEGIN  -- TG_ARGV[0] = status column, TG_ARGV[1..] = terminal values: a terminal aggregate is never modified again (no reopening)
  FOR i IN 1 .. TG_NARGS - 1 LOOP
    IF to_jsonb(OLD) ->> TG_ARGV[0] = TG_ARGV[i] THEN
      RAISE EXCEPTION '%.% is terminal (%): modification rejected', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[i] USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.freeze_when_status_in() OWNER TO ai_res_owner;

CREATE FUNCTION platform.keep_columns_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF n -> c IS DISTINCT FROM o -> c THEN
      RAISE EXCEPTION 'column %.% is immutable', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.keep_columns_immutable() OWNER TO ai_res_owner;

CREATE FUNCTION platform.keep_terminal_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- TG_ARGV[0] = terminal status of a `status` column (REVOKED): it can be entered but never left
  IF OLD.status = TG_ARGV[0] AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION '%.status % is terminal', TG_TABLE_NAME, TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.keep_terminal_status() OWNER TO ai_res_owner;

CREATE FUNCTION platform.reject_modification() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  RAISE EXCEPTION '%.% is immutable: % rejected', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $$;

ALTER FUNCTION platform.reject_modification() OWNER TO ai_res_owner;

CREATE FUNCTION platform.touch_row() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.row_version IS DISTINCT FROM OLD.row_version + 1 THEN
    RAISE EXCEPTION 'row_version must advance by exactly 1 (expected %, got %): optimistic concurrency is mandatory', OLD.row_version + 1, NEW.row_version
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

ALTER FUNCTION platform.touch_row() OWNER TO ai_res_owner;

CREATE FUNCTION work.require_open_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE st text;
BEGIN  -- ADR-012: a Task is created only inside an active, non-terminal Operation; rework after terminal = a new Operation (ADR-034)
  IF NEW.operation_id IS NULL THEN RETURN NEW; END IF;  -- the NOT NULL constraint reports this case
  SELECT status INTO st FROM operations.operations WHERE id = NEW.operation_id FOR SHARE;  -- conflicts with a concurrent status UPDATE: no child can slip under a terminal Operation
  IF st IS NULL OR st IN ('SUCCEEDED','PARTIALLY_SUCCEEDED','FAILED','CANCELLED') THEN
    RAISE EXCEPTION 'task requires an open operation (operation % is %)', NEW.operation_id, coalesce(st, 'not visible') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION work.require_open_operation() OWNER TO ai_res_owner;

SET default_table_access_method = heap;

CREATE TABLE agents.worker_results (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    worker_run_id uuid NOT NULL,
    contract_version text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash bytea NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_worker_results_payload CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_worker_results_payload_hash CHECK ((octet_length(payload_hash) = 32))
);

ALTER TABLE ONLY agents.worker_results FORCE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_results OWNER TO ai_res_owner;

CREATE TABLE agents.worker_run_events (
    event_id uuid NOT NULL,
    worker_run_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    source text NOT NULL,
    subject text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    actor_type text NOT NULL,
    actor_id uuid,
    reason_code text,
    from_status text,
    to_status text,
    data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_worker_run_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_worker_run_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_worker_run_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_worker_run_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY agents.worker_run_events FORCE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_run_events OWNER TO ai_res_owner;

CREATE TABLE agents.worker_runs (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    task_id uuid NOT NULL,
    worker_definition_version_id uuid NOT NULL,
    status text NOT NULL,
    derived_from_worker_run_id uuid,
    derivation_reason text,
    attempt_number integer DEFAULT 1 NOT NULL,
    context_package_version_id uuid NOT NULL,
    latest_readiness_evaluation_id uuid,
    started_with_readiness_evaluation_id uuid,
    workflow_id text,
    workflow_run_id text,
    input_contract_version text NOT NULL,
    output_contract_version text NOT NULL,
    execution_envelope_ref jsonb,
    result_ref jsonb,
    problem_ref jsonb,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    deadline_at timestamp with time zone,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_worker_runs_attempt_number CHECK ((attempt_number > 0)),
    CONSTRAINT ck_worker_runs_derivation_reason CHECK ((derivation_reason = ANY (ARRAY['RETRY'::text, 'REWORK'::text, 'NEW_CONTEXT'::text, 'INDEPENDENT_REVIEW'::text, 'REEXECUTION'::text, 'SPECIALIST_HANDOFF'::text]))),
    CONSTRAINT ck_worker_runs_derived_not_self CHECK (((derived_from_worker_run_id IS NULL) OR (derived_from_worker_run_id <> id))),
    CONSTRAINT ck_worker_runs_finished_iff_terminal CHECK (((status = ANY (ARRAY['COMPLETED'::text, 'REWORK_REQUIRED'::text, 'REJECTED'::text, 'UNVERIFIED'::text, 'FAILED'::text, 'TIMED_OUT'::text, 'CANCELLED'::text])) = (finished_at IS NOT NULL))),
    CONSTRAINT ck_worker_runs_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_worker_runs_lineage_has_reason CHECK (((derived_from_worker_run_id IS NULL) = (derivation_reason IS NULL))),
    CONSTRAINT ck_worker_runs_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_worker_runs_started_has_evaluation CHECK ((((status <> ALL (ARRAY['STARTING'::text, 'RUNNING'::text, 'WAITING_FOR_HUMAN'::text, 'WAITING_FOR_DEPENDENCY'::text, 'RESULT_SUBMITTED'::text, 'VALIDATING'::text, 'REVIEW_PENDING'::text, 'QA_PENDING'::text, 'COMPLETED'::text, 'REWORK_REQUIRED'::text, 'REJECTED'::text, 'UNVERIFIED'::text])) AND (started_at IS NULL)) OR (started_with_readiness_evaluation_id IS NOT NULL))),
    CONSTRAINT ck_worker_runs_status CHECK ((status = ANY (ARRAY['CREATED'::text, 'PREPARING'::text, 'WAITING_FOR_GATE'::text, 'BLOCKED'::text, 'QUEUED'::text, 'STARTING'::text, 'RUNNING'::text, 'WAITING_FOR_HUMAN'::text, 'WAITING_FOR_DEPENDENCY'::text, 'RESULT_SUBMITTED'::text, 'VALIDATING'::text, 'REVIEW_PENDING'::text, 'QA_PENDING'::text, 'COMPLETED'::text, 'REWORK_REQUIRED'::text, 'REJECTED'::text, 'UNVERIFIED'::text, 'FAILED'::text, 'TIMED_OUT'::text, 'CANCELLED'::text, 'CANCEL_REQUESTED'::text])))
);

ALTER TABLE ONLY agents.worker_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_runs OWNER TO ai_res_owner;

CREATE TABLE audit.aggregate_types (
    code text NOT NULL,
    CONSTRAINT ck_aggregate_types_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE audit.aggregate_types OWNER TO ai_res_owner;

CREATE TABLE audit.audit_events (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    actor_type text NOT NULL,
    actor_id uuid,
    action text NOT NULL,
    object_type text NOT NULL,
    object_id uuid,
    result text NOT NULL,
    reason_code text,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    version_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_events_action CHECK ((action ~ '^[A-Z][A-Z0-9_]*$'::text)),
    CONSTRAINT ck_audit_events_actor_type CHECK ((actor_type = ANY (ARRAY['USER'::text, 'SYSTEM'::text, 'MANAGER'::text, 'SERVICE'::text, 'WORKER_RUN'::text]))),
    CONSTRAINT ck_audit_events_object_type CHECK ((object_type ~ '^[A-Z][A-Z0-9_]*$'::text)),
    CONSTRAINT ck_audit_events_result CHECK ((result = ANY (ARRAY['SUCCEEDED'::text, 'DENIED'::text, 'FAILED'::text])))
);

ALTER TABLE ONLY audit.audit_events FORCE ROW LEVEL SECURITY;

ALTER TABLE audit.audit_events OWNER TO ai_res_owner;

CREATE TABLE audit.inbox_messages (
    id uuid NOT NULL,
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL,
    status text NOT NULL,
    payload_hash bytea NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone,
    error_code text,
    CONSTRAINT ck_inbox_messages_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_inbox_messages_consumer_name CHECK (((length(consumer_name) >= 1) AND (length(consumer_name) <= 200))),
    CONSTRAINT ck_inbox_messages_error_code CHECK ((error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_inbox_messages_payload_hash CHECK ((octet_length(payload_hash) = 32)),
    CONSTRAINT ck_inbox_messages_processed_iff_processed CHECK (((status = 'PROCESSED'::text) = (processed_at IS NOT NULL))),
    CONSTRAINT ck_inbox_messages_status CHECK ((status = ANY (ARRAY['PROCESSING'::text, 'PROCESSED'::text, 'QUARANTINED'::text])))
);

ALTER TABLE ONLY audit.inbox_messages FORCE ROW LEVEL SECURITY;

ALTER TABLE audit.inbox_messages OWNER TO ai_res_owner;

CREATE TABLE audit.outbox_events (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_id uuid NOT NULL,
    destination text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    envelope jsonb NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_error_code text,
    lease_owner text,
    lease_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone,
    CONSTRAINT ck_outbox_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_outbox_events_attempt_count CHECK ((attempt_count >= 0)),
    CONSTRAINT ck_outbox_events_destination CHECK (((length(destination) >= 1) AND (length(destination) <= 200))),
    CONSTRAINT ck_outbox_events_last_error_code CHECK ((last_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_outbox_events_lease_iff_in_flight CHECK ((((status = 'IN_FLIGHT'::text) = ((lease_owner IS NOT NULL) AND (lease_until IS NOT NULL))) AND ((lease_owner IS NULL) = (lease_until IS NULL)))),
    CONSTRAINT ck_outbox_events_published_iff_published CHECK (((status = 'PUBLISHED'::text) = (published_at IS NOT NULL))),
    CONSTRAINT ck_outbox_events_schema_version CHECK ((schema_version > 0)),
    CONSTRAINT ck_outbox_events_status CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text, 'PUBLISHED'::text, 'QUARANTINED'::text])))
);

ALTER TABLE ONLY audit.outbox_events FORCE ROW LEVEL SECURITY;

ALTER TABLE audit.outbox_events OWNER TO ai_res_owner;

CREATE TABLE execution.readiness_check_results (
    id uuid NOT NULL,
    worker_run_id uuid NOT NULL,
    readiness_evaluation_id uuid NOT NULL,
    check_code text NOT NULL,
    result text NOT NULL,
    severity text NOT NULL,
    reason_code text,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_readiness_check_results_check_code CHECK ((check_code ~ '^[A-Z][A-Z0-9_]*$'::text)),
    CONSTRAINT ck_readiness_check_results_result CHECK ((result = ANY (ARRAY['PASS'::text, 'FAIL'::text, 'WARN'::text, 'NOT_APPLICABLE'::text]))),
    CONSTRAINT ck_readiness_check_results_severity CHECK ((severity = ANY (ARRAY['INFO'::text, 'LOW'::text, 'MEDIUM'::text, 'HIGH'::text, 'CRITICAL'::text])))
);

ALTER TABLE ONLY execution.readiness_check_results FORCE ROW LEVEL SECURITY;

ALTER TABLE execution.readiness_check_results OWNER TO ai_res_owner;

CREATE TABLE execution.readiness_evaluations (
    id uuid NOT NULL,
    worker_run_id uuid NOT NULL,
    evaluation_number integer NOT NULL,
    evaluation_status text NOT NULL,
    gate_outcome text,
    snapshot_hash bytea NOT NULL,
    task_version bigint NOT NULL,
    plan_version_id uuid,
    worker_definition_version_id uuid NOT NULL,
    context_package_version_id uuid NOT NULL,
    ruleset_version text NOT NULL,
    policy_engine_version text NOT NULL,
    grant_snapshot_ref jsonb NOT NULL,
    tool_allowlist_snapshot jsonb NOT NULL,
    output_contract_version text NOT NULL,
    budget_profile_version text NOT NULL,
    dependency_snapshot jsonb NOT NULL,
    evaluator_version text NOT NULL,
    blockers jsonb DEFAULT '[]'::jsonb NOT NULL,
    limitations jsonb DEFAULT '[]'::jsonb NOT NULL,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    evaluated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_readiness_evaluations_evaluation_number CHECK ((evaluation_number > 0)),
    CONSTRAINT ck_readiness_evaluations_evaluation_status CHECK ((evaluation_status = ANY (ARRAY['COMPLETED'::text, 'EVALUATOR_ERROR'::text]))),
    CONSTRAINT ck_readiness_evaluations_gate_outcome CHECK ((gate_outcome = ANY (ARRAY['READY'::text, 'READY_WITH_LIMITATIONS'::text, 'BLOCKED'::text, 'STALE'::text]))),
    CONSTRAINT ck_readiness_evaluations_outcome_matches_status CHECK (((evaluation_status = 'COMPLETED'::text) = ((gate_outcome IS NOT NULL) AND (evaluated_at IS NOT NULL)))),
    CONSTRAINT ck_readiness_evaluations_ready_without_blockers CHECK (((gate_outcome IS DISTINCT FROM 'READY'::text) OR (blockers = '[]'::jsonb))),
    CONSTRAINT ck_readiness_evaluations_snapshot_hash CHECK ((octet_length(snapshot_hash) = 32))
);

ALTER TABLE ONLY execution.readiness_evaluations FORCE ROW LEVEL SECURITY;

ALTER TABLE execution.readiness_evaluations OWNER TO ai_res_owner;

CREATE TABLE iam.credentials (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    kind text NOT NULL,
    password_hash text NOT NULL,
    password_changed_at timestamp with time zone DEFAULT now() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_credentials_argon2id CHECK (((password_hash ~~ '$argon2id$%'::text) AND (length(password_hash) <= 512))),
    CONSTRAINT ck_credentials_kind CHECK ((kind = 'PASSWORD'::text)),
    CONSTRAINT ck_credentials_row_version CHECK ((row_version > 0))
);

ALTER TABLE ONLY iam.credentials FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.credentials OWNER TO ai_res_owner;

CREATE TABLE iam.mfa_factors (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    factor_type text NOT NULL,
    secret_ciphertext bytea NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    confirmed_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_mfa_factors_factor_type CHECK ((factor_type = 'TOTP'::text)),
    CONSTRAINT ck_mfa_factors_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_mfa_factors_secret CHECK ((octet_length(secret_ciphertext) > 0)),
    CONSTRAINT ck_mfa_factors_status CHECK ((status = ANY (ARRAY['PENDING'::text, 'ACTIVE'::text, 'REVOKED'::text])))
);

ALTER TABLE ONLY iam.mfa_factors FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.mfa_factors OWNER TO ai_res_owner;

CREATE TABLE iam.mfa_recovery_codes (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    code_digest bytea NOT NULL,
    used_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_mfa_recovery_codes_digest CHECK ((octet_length(code_digest) = 32)),
    CONSTRAINT ck_mfa_recovery_codes_row_version CHECK ((row_version > 0))
);

ALTER TABLE ONLY iam.mfa_recovery_codes FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.mfa_recovery_codes OWNER TO ai_res_owner;

CREATE TABLE iam.roles (
    code text NOT NULL,
    org_level boolean NOT NULL,
    project_level boolean NOT NULL,
    CONSTRAINT ck_roles_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_roles_level CHECK ((org_level OR project_level))
);

ALTER TABLE iam.roles OWNER TO ai_res_owner;

CREATE TABLE iam.service_identities (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    service_kind text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_service_identities_kind CHECK ((service_kind = ANY (ARRAY['API'::text, 'MANAGER_RUNTIME'::text, 'WORKER_RUNTIME'::text, 'TEMPORAL_ACTIVITY'::text, 'CONNECTOR'::text, 'LLM_GATEWAY'::text]))),
    CONSTRAINT ck_service_identities_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 200))),
    CONSTRAINT ck_service_identities_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_service_identities_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'DISABLED'::text])))
);

ALTER TABLE ONLY iam.service_identities FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.service_identities OWNER TO ai_res_owner;

CREATE TABLE iam.sessions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_digest bytea NOT NULL,
    csrf_digest bytea NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    mfa_verified_at timestamp with time zone,
    revoked_at timestamp with time zone,
    revoked_reason text,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sessions_csrf_digest CHECK ((octet_length(csrf_digest) = 32)),
    CONSTRAINT ck_sessions_idle_within_absolute CHECK ((idle_expires_at <= absolute_expires_at)),
    CONSTRAINT ck_sessions_revocation CHECK (((revoked_at IS NULL) = (revoked_reason IS NULL))),
    CONSTRAINT ck_sessions_revoked_reason CHECK (((revoked_reason IS NULL) OR (length(revoked_reason) <= 100))),
    CONSTRAINT ck_sessions_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_sessions_session_digest CHECK ((octet_length(session_digest) = 32))
);

ALTER TABLE ONLY iam.sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.sessions OWNER TO ai_res_owner;

CREATE TABLE iam.users (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    email text NOT NULL,
    email_normalized text NOT NULL,
    display_name text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_users_display_name CHECK (((length(btrim(display_name)) >= 1) AND (length(btrim(display_name)) <= 200))),
    CONSTRAINT ck_users_email CHECK (((length(email) >= 3) AND (length(email) <= 320))),
    CONSTRAINT ck_users_email_normalized CHECK ((email_normalized = lower(btrim(email_normalized)))),
    CONSTRAINT ck_users_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_users_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'DISABLED'::text])))
);

ALTER TABLE ONLY iam.users FORCE ROW LEVEL SECURITY;

ALTER TABLE iam.users OWNER TO ai_res_owner;

CREATE TABLE operations.operation_events (
    event_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    aggregate_sequence bigint NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    source text NOT NULL,
    subject text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    actor_type text NOT NULL,
    actor_id uuid,
    reason_code text,
    from_status text,
    to_status text,
    data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_operation_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_operation_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_operation_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_operation_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY operations.operation_events FORCE ROW LEVEL SECURITY;

ALTER TABLE operations.operation_events OWNER TO ai_res_owner;

CREATE TABLE operations.operation_types (
    code text NOT NULL,
    CONSTRAINT ck_operation_types_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE operations.operation_types OWNER TO ai_res_owner;

CREATE TABLE operations.operations (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    parent_operation_id uuid,
    operation_type text NOT NULL,
    status text NOT NULL,
    initiator_type text NOT NULL,
    initiator_id uuid,
    idempotency_scope text NOT NULL,
    request_fingerprint bytea NOT NULL,
    completion_policy_version text NOT NULL,
    completion_policy_snapshot jsonb NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    workflow_id text,
    workflow_run_id text,
    progress_version bigint DEFAULT 0 NOT NULL,
    progress_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    result_ref jsonb,
    problem_ref jsonb,
    cancel_requested_at timestamp with time zone,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_operations_completed_iff_terminal CHECK (((status = ANY (ARRAY['SUCCEEDED'::text, 'PARTIALLY_SUCCEEDED'::text, 'FAILED'::text, 'CANCELLED'::text])) = (completed_at IS NOT NULL))),
    CONSTRAINT ck_operations_initiator_type CHECK ((initiator_type = ANY (ARRAY['USER'::text, 'SYSTEM'::text, 'MANAGER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_operations_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_operations_parent_not_self CHECK (((parent_operation_id IS NULL) OR (parent_operation_id <> id))),
    CONSTRAINT ck_operations_progress_version CHECK ((progress_version >= 0)),
    CONSTRAINT ck_operations_request_fingerprint CHECK ((octet_length(request_fingerprint) = 32)),
    CONSTRAINT ck_operations_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_operations_status CHECK ((status = ANY (ARRAY['ACCEPTED'::text, 'QUEUED'::text, 'RUNNING'::text, 'WAITING_FOR_HUMAN'::text, 'WAITING_FOR_DEPENDENCY'::text, 'RETRYING'::text, 'CANCEL_REQUESTED'::text, 'SUCCEEDED'::text, 'PARTIALLY_SUCCEEDED'::text, 'FAILED'::text, 'CANCELLED'::text])))
);

ALTER TABLE ONLY operations.operations FORCE ROW LEVEL SECURITY;

ALTER TABLE operations.operations OWNER TO ai_res_owner;

CREATE TABLE organization.memberships (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_code text NOT NULL,
    org_level boolean DEFAULT true NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_memberships_org_level CHECK (org_level),
    CONSTRAINT ck_memberships_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_memberships_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'SUSPENDED'::text, 'REVOKED'::text])))
);

ALTER TABLE ONLY organization.memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE organization.memberships OWNER TO ai_res_owner;

CREATE TABLE organization.organizations (
    id uuid NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_organizations_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 200))),
    CONSTRAINT ck_organizations_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_organizations_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text])))
);

ALTER TABLE ONLY organization.organizations FORCE ROW LEVEL SECURITY;

ALTER TABLE organization.organizations OWNER TO ai_res_owner;

CREATE TABLE platform.alembic_version (
    version_num character varying(32) NOT NULL
);

ALTER TABLE platform.alembic_version OWNER TO ai_res_owner;

CREATE TABLE platform.idempotency_records (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid,
    scope_type text NOT NULL,
    scope_id uuid NOT NULL,
    key_digest bytea NOT NULL,
    key_id text NOT NULL,
    request_fingerprint bytea NOT NULL,
    resource_type text,
    resource_id uuid,
    status text NOT NULL,
    response_status integer,
    response_body_ref jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT ck_idempotency_records_completed_iff_finished CHECK (((status = 'IN_PROGRESS'::text) = (completed_at IS NULL))),
    CONSTRAINT ck_idempotency_records_key_digest CHECK ((octet_length(key_digest) = 32)),
    CONSTRAINT ck_idempotency_records_key_id CHECK (((length(key_id) >= 1) AND (length(key_id) <= 100))),
    CONSTRAINT ck_idempotency_records_request_fingerprint CHECK ((octet_length(request_fingerprint) = 32)),
    CONSTRAINT ck_idempotency_records_scope_type CHECK ((scope_type ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_idempotency_records_status CHECK ((status = ANY (ARRAY['IN_PROGRESS'::text, 'COMPLETED'::text, 'REJECTED'::text])))
);

ALTER TABLE ONLY platform.idempotency_records FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.idempotency_records OWNER TO ai_res_owner;

CREATE TABLE project.project_memberships (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_code text NOT NULL,
    project_level boolean DEFAULT true NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_memberships_project_level CHECK (project_level),
    CONSTRAINT ck_project_memberships_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_project_memberships_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'SUSPENDED'::text, 'REVOKED'::text])))
);

ALTER TABLE ONLY project.project_memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE project.project_memberships OWNER TO ai_res_owner;

CREATE TABLE project.projects (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    project_type text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_projects_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 200))),
    CONSTRAINT ck_projects_project_type CHECK ((project_type = ANY (ARRAY['GREENFIELD'::text, 'BROWNFIELD'::text, 'HYBRID'::text, 'UNKNOWN'::text]))),
    CONSTRAINT ck_projects_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_projects_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text])))
);

ALTER TABLE ONLY project.projects FORCE ROW LEVEL SECURITY;

ALTER TABLE project.projects OWNER TO ai_res_owner;

CREATE TABLE work.epics (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    title text NOT NULL,
    goal text,
    scope_description text,
    outcome_criteria text,
    status text NOT NULL,
    priority text,
    owner_user_id uuid,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_epics_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_epics_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_epics_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY work.epics FORCE ROW LEVEL SECURITY;

ALTER TABLE work.epics OWNER TO ai_res_owner;

CREATE TABLE work.task_dependencies (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    depends_on_task_id uuid NOT NULL,
    dependency_type text DEFAULT 'BLOCKS'::text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_task_dependencies_dependency_type CHECK ((dependency_type = 'BLOCKS'::text)),
    CONSTRAINT ck_task_dependencies_not_self CHECK ((task_id <> depends_on_task_id))
);

ALTER TABLE ONLY work.task_dependencies FORCE ROW LEVEL SECURITY;

ALTER TABLE work.task_dependencies OWNER TO ai_res_owner;

CREATE TABLE work.tasks (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    derived_from_task_id uuid,
    task_type text NOT NULL,
    title text NOT NULL,
    description text,
    acceptance_criteria jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text NOT NULL,
    priority text,
    initiator_type text NOT NULL,
    initiator_id uuid,
    owner_user_id uuid,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_tasks_acceptance_criteria CHECK ((jsonb_typeof(acceptance_criteria) = 'array'::text)),
    CONSTRAINT ck_tasks_derived_not_self CHECK (((derived_from_task_id IS NULL) OR (derived_from_task_id <> id))),
    CONSTRAINT ck_tasks_initiator_type CHECK ((initiator_type = ANY (ARRAY['USER'::text, 'SYSTEM'::text, 'MANAGER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_tasks_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_tasks_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_tasks_task_type CHECK ((task_type ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_tasks_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY work.tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE work.tasks OWNER TO ai_res_owner;

ALTER TABLE ONLY agents.worker_results
    ADD CONSTRAINT pk_worker_results PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_run_events
    ADD CONSTRAINT pk_worker_run_events PRIMARY KEY (event_id);

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT pk_worker_runs PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_results
    ADD CONSTRAINT uq_worker_results_organization_id_project_id_worker_run_id UNIQUE (organization_id, project_id, worker_run_id);

ALTER TABLE ONLY agents.worker_run_events
    ADD CONSTRAINT uq_worker_run_events_worker_run_id_aggregate_sequence UNIQUE (worker_run_id, aggregate_sequence);

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT uq_worker_runs_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT uq_worker_runs_organization_id_project_id_task_id_attempt_numbe UNIQUE (organization_id, project_id, task_id, attempt_number);

ALTER TABLE ONLY audit.aggregate_types
    ADD CONSTRAINT pk_aggregate_types PRIMARY KEY (code);

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);

ALTER TABLE ONLY audit.inbox_messages
    ADD CONSTRAINT pk_inbox_messages PRIMARY KEY (id);

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT pk_outbox_events PRIMARY KEY (id);

ALTER TABLE ONLY audit.inbox_messages
    ADD CONSTRAINT uq_inbox_messages_consumer_name_event_id UNIQUE (consumer_name, event_id);

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT uq_outbox_events_aggregate_type_aggregate_id_aggregate_sequence UNIQUE (aggregate_type, aggregate_id, aggregate_sequence, destination);

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT uq_outbox_events_event_id_destination UNIQUE (event_id, destination);

ALTER TABLE ONLY execution.readiness_check_results
    ADD CONSTRAINT pk_readiness_check_results PRIMARY KEY (id);

ALTER TABLE ONLY execution.readiness_evaluations
    ADD CONSTRAINT pk_readiness_evaluations PRIMARY KEY (id);

ALTER TABLE ONLY execution.readiness_check_results
    ADD CONSTRAINT uq_readiness_check_results_readiness_evaluation_id_check_code UNIQUE (readiness_evaluation_id, check_code);

ALTER TABLE ONLY execution.readiness_evaluations
    ADD CONSTRAINT uq_readiness_evaluations_worker_run_id_evaluation_number UNIQUE (worker_run_id, evaluation_number);

ALTER TABLE ONLY execution.readiness_evaluations
    ADD CONSTRAINT uq_readiness_evaluations_worker_run_id_id UNIQUE (worker_run_id, id);

ALTER TABLE ONLY iam.credentials
    ADD CONSTRAINT pk_credentials PRIMARY KEY (id);

ALTER TABLE ONLY iam.mfa_factors
    ADD CONSTRAINT pk_mfa_factors PRIMARY KEY (id);

ALTER TABLE ONLY iam.mfa_recovery_codes
    ADD CONSTRAINT pk_mfa_recovery_codes PRIMARY KEY (id);

ALTER TABLE ONLY iam.roles
    ADD CONSTRAINT pk_roles PRIMARY KEY (code);

ALTER TABLE ONLY iam.service_identities
    ADD CONSTRAINT pk_service_identities PRIMARY KEY (id);

ALTER TABLE ONLY iam.sessions
    ADD CONSTRAINT pk_sessions PRIMARY KEY (id);

ALTER TABLE ONLY iam.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);

ALTER TABLE ONLY iam.credentials
    ADD CONSTRAINT uq_credentials_user_id_kind UNIQUE (user_id, kind);

ALTER TABLE ONLY iam.mfa_recovery_codes
    ADD CONSTRAINT uq_mfa_recovery_codes_user_id_code_digest UNIQUE (user_id, code_digest);

ALTER TABLE ONLY iam.roles
    ADD CONSTRAINT uq_roles_code_org_level UNIQUE (code, org_level);

ALTER TABLE ONLY iam.roles
    ADD CONSTRAINT uq_roles_code_project_level UNIQUE (code, project_level);

ALTER TABLE ONLY iam.service_identities
    ADD CONSTRAINT uq_service_identities_organization_id_name UNIQUE (organization_id, name);

ALTER TABLE ONLY iam.sessions
    ADD CONSTRAINT uq_sessions_session_digest UNIQUE (session_digest);

ALTER TABLE ONLY iam.users
    ADD CONSTRAINT uq_users_organization_id_email_normalized UNIQUE (organization_id, email_normalized);

ALTER TABLE ONLY iam.users
    ADD CONSTRAINT uq_users_organization_id_id UNIQUE (organization_id, id);

ALTER TABLE ONLY operations.operation_events
    ADD CONSTRAINT pk_operation_events PRIMARY KEY (event_id);

ALTER TABLE ONLY operations.operation_types
    ADD CONSTRAINT pk_operation_types PRIMARY KEY (code);

ALTER TABLE ONLY operations.operations
    ADD CONSTRAINT pk_operations PRIMARY KEY (id);

ALTER TABLE ONLY operations.operation_events
    ADD CONSTRAINT uq_operation_events_operation_id_aggregate_sequence UNIQUE (operation_id, aggregate_sequence);

ALTER TABLE ONLY operations.operations
    ADD CONSTRAINT uq_operations_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY organization.memberships
    ADD CONSTRAINT pk_memberships PRIMARY KEY (id);

ALTER TABLE ONLY organization.organizations
    ADD CONSTRAINT pk_organizations PRIMARY KEY (id);

ALTER TABLE ONLY organization.memberships
    ADD CONSTRAINT uq_memberships_organization_id_user_id UNIQUE (organization_id, user_id);

ALTER TABLE ONLY platform.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT pk_idempotency_records PRIMARY KEY (id);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT uq_idempotency_records_organization_id_scope_type_scope_id_key_ UNIQUE (organization_id, scope_type, scope_id, key_digest);

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT pk_project_memberships PRIMARY KEY (id);

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT pk_projects PRIMARY KEY (id);

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT uq_project_memberships_project_id_user_id UNIQUE (project_id, user_id);

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT uq_projects_organization_id_id UNIQUE (organization_id, id);

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT pk_epics PRIMARY KEY (id);

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT pk_task_dependencies PRIMARY KEY (id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT pk_tasks PRIMARY KEY (id);

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT uq_epics_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT uq_task_dependencies_task_id_depends_on_task_id UNIQUE (task_id, depends_on_task_id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT uq_tasks_operation_id_id UNIQUE (operation_id, id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT uq_tasks_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT uq_tasks_organization_id_project_id_operation_id_id UNIQUE (organization_id, project_id, operation_id, id);

CREATE INDEX ix_worker_run_events_worker_run_id_occurred_at ON agents.worker_run_events USING btree (worker_run_id, occurred_at DESC);

CREATE INDEX ix_worker_runs_lineage ON agents.worker_runs USING btree (derived_from_worker_run_id) WHERE (derived_from_worker_run_id IS NOT NULL);

CREATE INDEX ix_worker_runs_operation_id_created_at ON agents.worker_runs USING btree (operation_id, created_at DESC);

CREATE INDEX ix_worker_runs_schedulable ON agents.worker_runs USING btree (status, created_at) WHERE (status = ANY (ARRAY['CREATED'::text, 'PREPARING'::text, 'WAITING_FOR_GATE'::text, 'QUEUED'::text, 'STARTING'::text]));

CREATE INDEX ix_worker_runs_task_id_created_at ON agents.worker_runs USING btree (task_id, created_at DESC);

CREATE INDEX ix_audit_events_actor_id ON audit.audit_events USING btree (actor_id) WHERE (actor_id IS NOT NULL);

CREATE INDEX ix_audit_events_object ON audit.audit_events USING btree (object_type, object_id);

CREATE INDEX ix_audit_events_organization_id_occurred_at ON audit.audit_events USING btree (organization_id, occurred_at DESC);

CREATE INDEX ix_inbox_messages_consumer_name_status_received_at ON audit.inbox_messages USING btree (consumer_name, status, received_at);

CREATE INDEX ix_outbox_events_pending ON audit.outbox_events USING btree (available_at, created_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text]));

CREATE INDEX ix_readiness_evaluations_worker_run_id_created_at ON execution.readiness_evaluations USING btree (worker_run_id, created_at DESC);

CREATE INDEX ix_sessions_user_id_active ON iam.sessions USING btree (user_id) WHERE (revoked_at IS NULL);

CREATE UNIQUE INDEX ux_mfa_factors_active_per_user ON iam.mfa_factors USING btree (user_id, factor_type) WHERE (status <> 'REVOKED'::text);

CREATE INDEX ix_operation_events_operation_id_occurred_at ON operations.operation_events USING btree (operation_id, occurred_at DESC);

CREATE INDEX ix_operations_active_status ON operations.operations USING btree (status, updated_at) WHERE (status <> ALL (ARRAY['SUCCEEDED'::text, 'PARTIALLY_SUCCEEDED'::text, 'FAILED'::text, 'CANCELLED'::text]));

CREATE INDEX ix_operations_parent_operation_id ON operations.operations USING btree (parent_operation_id) WHERE (parent_operation_id IS NOT NULL);

CREATE INDEX ix_operations_project_id_created_at ON operations.operations USING btree (project_id, created_at DESC);

CREATE INDEX ix_idempotency_records_expires_at ON platform.idempotency_records USING btree (expires_at);

CREATE INDEX ix_task_dependencies_depends_on_task_id ON work.task_dependencies USING btree (depends_on_task_id);

CREATE INDEX ix_tasks_epic_id ON work.tasks USING btree (epic_id);

CREATE INDEX ix_tasks_operation_id_status_priority ON work.tasks USING btree (operation_id, status, priority);

CREATE TRIGGER trg_worker_results_append_only BEFORE DELETE OR UPDATE ON agents.worker_results FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_worker_results_no_truncate BEFORE TRUNCATE ON agents.worker_results FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_worker_results_require_started_run BEFORE INSERT ON agents.worker_results FOR EACH ROW EXECUTE FUNCTION agents.require_started_open_run();

CREATE TRIGGER trg_worker_run_events_append_only BEFORE DELETE OR UPDATE ON agents.worker_run_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_worker_run_events_no_truncate BEFORE TRUNCATE ON agents.worker_run_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_worker_run_events_sequence AFTER INSERT ON agents.worker_run_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('worker_run_id', 'agents.worker_runs', 'agents.worker_run_events', 'worker_run_id');

CREATE TRIGGER trg_worker_runs_freeze_terminal BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'COMPLETED', 'REWORK_REQUIRED', 'REJECTED', 'UNVERIFIED', 'FAILED', 'TIMED_OUT', 'CANCELLED');

CREATE TRIGGER trg_worker_runs_guard_start BEFORE INSERT OR UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_run_start();

CREATE TRIGGER trg_worker_runs_immutable_columns BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'operation_id', 'task_id', 'worker_definition_version_id', 'derived_from_worker_run_id', 'derivation_reason', 'attempt_number', 'context_package_version_id', 'input_contract_version', 'output_contract_version', 'created_at');

CREATE TRIGGER trg_worker_runs_require_open_operation BEFORE INSERT ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION work.require_open_operation();

CREATE CONSTRAINT TRIGGER trg_worker_runs_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON agents.worker_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'agents.worker_runs', 'agents.worker_run_events', 'worker_run_id');

CREATE CONSTRAINT TRIGGER trg_worker_runs_started_ready AFTER INSERT OR UPDATE OF started_with_readiness_evaluation_id ON agents.worker_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION agents.assert_worker_run_started_ready();

CREATE TRIGGER trg_worker_runs_touch BEFORE UPDATE ON agents.worker_runs FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_audit_events_append_only BEFORE DELETE OR UPDATE ON audit.audit_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit.audit_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_inbox_messages_immutable_columns BEFORE UPDATE ON audit.inbox_messages FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'consumer_name', 'event_id', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'payload_hash', 'received_at');

CREATE TRIGGER trg_outbox_events_immutable_columns BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'event_id', 'destination', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'event_type', 'schema_version', 'envelope', 'created_at');

CREATE CONSTRAINT TRIGGER trg_outbox_events_matches_event AFTER INSERT ON audit.outbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit.assert_outbox_matches_event();

CREATE TRIGGER trg_readiness_check_results_append_only BEFORE DELETE OR UPDATE ON execution.readiness_check_results FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_check_results_no_truncate BEFORE TRUNCATE ON execution.readiness_check_results FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_check_results_same_transaction BEFORE INSERT ON execution.readiness_check_results FOR EACH ROW EXECUTE FUNCTION execution.guard_check_result_insert();

CREATE TRIGGER trg_readiness_evaluations_append_only BEFORE DELETE OR UPDATE ON execution.readiness_evaluations FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_evaluations_lock_run BEFORE INSERT ON execution.readiness_evaluations FOR EACH ROW EXECUTE FUNCTION execution.lock_run_for_evaluation();

CREATE TRIGGER trg_readiness_evaluations_no_truncate BEFORE TRUNCATE ON execution.readiness_evaluations FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_credentials_immutable_columns BEFORE UPDATE ON iam.credentials FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id');

CREATE TRIGGER trg_credentials_touch BEFORE UPDATE ON iam.credentials FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_mfa_factors_immutable_columns BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id');

CREATE TRIGGER trg_mfa_factors_revoked_terminal BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED');

CREATE TRIGGER trg_mfa_factors_touch BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_mfa_recovery_codes_immutable_columns BEFORE UPDATE ON iam.mfa_recovery_codes FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id', 'code_digest');

CREATE TRIGGER trg_mfa_recovery_codes_touch BEFORE UPDATE ON iam.mfa_recovery_codes FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_mfa_recovery_codes_write_once BEFORE UPDATE ON iam.mfa_recovery_codes FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('used_at');

CREATE TRIGGER trg_service_identities_immutable_columns BEFORE UPDATE ON iam.service_identities FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'service_kind');

CREATE TRIGGER trg_service_identities_touch BEFORE UPDATE ON iam.service_identities FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_sessions_immutable_columns BEFORE UPDATE ON iam.sessions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id', 'session_digest', 'csrf_digest', 'absolute_expires_at', 'created_at');

CREATE TRIGGER trg_sessions_touch BEFORE UPDATE ON iam.sessions FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_sessions_write_once BEFORE UPDATE ON iam.sessions FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('revoked_at', 'revoked_reason');

CREATE TRIGGER trg_users_immutable_columns BEFORE UPDATE ON iam.users FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id');

CREATE TRIGGER trg_users_touch BEFORE UPDATE ON iam.users FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_operation_events_append_only BEFORE DELETE OR UPDATE ON operations.operation_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_operation_events_no_truncate BEFORE TRUNCATE ON operations.operation_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_operation_events_sequence AFTER INSERT ON operations.operation_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('operation_id', 'operations.operations', 'operations.operation_events', 'operation_id');

CREATE TRIGGER trg_operations_freeze_terminal BEFORE UPDATE ON operations.operations FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'SUCCEEDED', 'PARTIALLY_SUCCEEDED', 'FAILED', 'CANCELLED');

CREATE TRIGGER trg_operations_immutable_columns BEFORE UPDATE ON operations.operations FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'parent_operation_id', 'operation_type', 'initiator_type', 'initiator_id', 'idempotency_scope', 'request_fingerprint', 'correlation_id', 'completion_policy_version', 'completion_policy_snapshot', 'created_at');

CREATE CONSTRAINT TRIGGER trg_operations_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON operations.operations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'operations.operations', 'operations.operation_events', 'operation_id');

CREATE TRIGGER trg_operations_touch BEFORE UPDATE ON operations.operations FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_memberships_immutable_columns BEFORE UPDATE ON organization.memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id');

CREATE TRIGGER trg_memberships_revoked_terminal BEFORE UPDATE ON organization.memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED');

CREATE TRIGGER trg_memberships_touch BEFORE UPDATE ON organization.memberships FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_organizations_immutable_columns BEFORE UPDATE ON organization.organizations FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id');

CREATE TRIGGER trg_organizations_touch BEFORE UPDATE ON organization.organizations FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_idempotency_records_freeze_finished BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'COMPLETED', 'REJECTED');

CREATE TRIGGER trg_idempotency_records_immutable_columns BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'scope_type', 'scope_id', 'key_digest', 'key_id', 'request_fingerprint', 'created_at', 'expires_at');

CREATE TRIGGER trg_project_memberships_immutable_columns BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'user_id');

CREATE TRIGGER trg_project_memberships_revoked_terminal BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED');

CREATE TRIGGER trg_project_memberships_touch BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_projects_immutable_columns BEFORE UPDATE ON project.projects FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id');

CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON project.projects FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_epics_immutable_columns BEFORE UPDATE ON work.epics FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at');

CREATE TRIGGER trg_epics_touch BEFORE UPDATE ON work.epics FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_tasks_immutable_columns BEFORE UPDATE ON work.tasks FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'operation_id', 'epic_id', 'derived_from_task_id', 'initiator_type', 'initiator_id', 'created_at');

CREATE TRIGGER trg_tasks_require_open_operation BEFORE INSERT ON work.tasks FOR EACH ROW EXECUTE FUNCTION work.require_open_operation();

CREATE TRIGGER trg_tasks_touch BEFORE UPDATE ON work.tasks FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

ALTER TABLE ONLY agents.worker_results
    ADD CONSTRAINT fk_worker_results_worker_run_id_worker_runs FOREIGN KEY (organization_id, project_id, worker_run_id) REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY agents.worker_run_events
    ADD CONSTRAINT fk_worker_run_events_worker_run_id_worker_runs FOREIGN KEY (worker_run_id) REFERENCES agents.worker_runs(id) ON DELETE RESTRICT;

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT fk_worker_runs_derived_from_worker_run_id_worker_runs FOREIGN KEY (organization_id, project_id, derived_from_worker_run_id) REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT fk_worker_runs_latest_readiness_evaluation_id_readiness_evaluat FOREIGN KEY (id, latest_readiness_evaluation_id) REFERENCES execution.readiness_evaluations(worker_run_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT fk_worker_runs_operation_id_task_id_tasks FOREIGN KEY (organization_id, project_id, operation_id, task_id) REFERENCES work.tasks(organization_id, project_id, operation_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT fk_worker_runs_started_with_readiness_evaluation_id_readiness_e FOREIGN KEY (id, started_with_readiness_evaluation_id) REFERENCES execution.readiness_evaluations(worker_run_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT fk_audit_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.inbox_messages
    ADD CONSTRAINT fk_inbox_messages_aggregate_type_aggregate_types FOREIGN KEY (aggregate_type) REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT fk_outbox_events_aggregate_type_aggregate_types FOREIGN KEY (aggregate_type) REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT fk_outbox_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY execution.readiness_check_results
    ADD CONSTRAINT fk_readiness_check_results_worker_run_id_readiness_evaluations FOREIGN KEY (worker_run_id, readiness_evaluation_id) REFERENCES execution.readiness_evaluations(worker_run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY execution.readiness_evaluations
    ADD CONSTRAINT fk_readiness_evaluations_worker_run_id_worker_runs FOREIGN KEY (worker_run_id) REFERENCES agents.worker_runs(id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.credentials
    ADD CONSTRAINT fk_credentials_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.mfa_factors
    ADD CONSTRAINT fk_mfa_factors_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.mfa_recovery_codes
    ADD CONSTRAINT fk_mfa_recovery_codes_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.service_identities
    ADD CONSTRAINT fk_service_identities_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.sessions
    ADD CONSTRAINT fk_sessions_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY iam.users
    ADD CONSTRAINT fk_users_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY operations.operation_events
    ADD CONSTRAINT fk_operation_events_operation_id_operations FOREIGN KEY (operation_id) REFERENCES operations.operations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY operations.operations
    ADD CONSTRAINT fk_operations_operation_type_operation_types FOREIGN KEY (operation_type) REFERENCES operations.operation_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY operations.operations
    ADD CONSTRAINT fk_operations_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY operations.operations
    ADD CONSTRAINT fk_operations_parent_operation_id_operations FOREIGN KEY (organization_id, project_id, parent_operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY organization.memberships
    ADD CONSTRAINT fk_memberships_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY organization.memberships
    ADD CONSTRAINT fk_memberships_role_code_org_level_roles FOREIGN KEY (role_code, org_level) REFERENCES iam.roles(code, org_level) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT fk_idempotency_records_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT fk_idempotency_records_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_role_code_project_level_roles FOREIGN KEY (role_code, project_level) REFERENCES iam.roles(code, project_level) ON DELETE RESTRICT;

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT fk_projects_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT fk_epics_organization_id_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT fk_epics_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT fk_task_dependencies_depends_on_task_id_tasks FOREIGN KEY (organization_id, project_id, depends_on_task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT fk_task_dependencies_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT fk_tasks_derived_from_task_id_tasks FOREIGN KEY (organization_id, project_id, derived_from_task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT fk_tasks_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT fk_tasks_operation_id_operations FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT fk_tasks_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

CREATE POLICY p_worker_results_owner_migration ON agents.worker_results TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_results_tenant_scope ON agents.worker_results TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_worker_run_events_owner_migration ON agents.worker_run_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_run_events_tenant_scope ON agents.worker_run_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = worker_run_events.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = worker_run_events.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_worker_runs_owner_migration ON agents.worker_runs TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_runs_tenant_scope ON agents.worker_runs TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE agents.worker_results ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_run_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.inbox_messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.outbox_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_audit_events_api_insert ON audit.audit_events FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_audit_events_auditor_select ON audit.audit_events FOR SELECT TO ai_res_auditor_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_audit_events_owner_migration ON audit.audit_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_inbox_messages_consumer_all ON audit.inbox_messages TO ai_res_consumer_group USING (true) WITH CHECK (true);

CREATE POLICY p_inbox_messages_owner_migration ON audit.inbox_messages TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_outbox_events_api_insert ON audit.outbox_events FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_outbox_events_dispatcher_select ON audit.outbox_events FOR SELECT TO ai_res_outbox_group USING (true);

CREATE POLICY p_outbox_events_dispatcher_update ON audit.outbox_events FOR UPDATE TO ai_res_outbox_group USING (true) WITH CHECK (true);

CREATE POLICY p_outbox_events_owner_migration ON audit.outbox_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_readiness_check_results_owner_migration ON execution.readiness_check_results TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_readiness_check_results_tenant_scope ON execution.readiness_check_results TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = readiness_check_results.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = readiness_check_results.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_readiness_evaluations_owner_migration ON execution.readiness_evaluations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_readiness_evaluations_tenant_scope ON execution.readiness_evaluations TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = readiness_evaluations.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = readiness_evaluations.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

ALTER TABLE execution.readiness_check_results ENABLE ROW LEVEL SECURITY;

ALTER TABLE execution.readiness_evaluations ENABLE ROW LEVEL SECURITY;

ALTER TABLE iam.credentials ENABLE ROW LEVEL SECURITY;

ALTER TABLE iam.mfa_factors ENABLE ROW LEVEL SECURITY;

ALTER TABLE iam.mfa_recovery_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_credentials_owner_migration ON iam.credentials TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_credentials_tenant_scope ON iam.credentials TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_mfa_factors_owner_migration ON iam.mfa_factors TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_mfa_factors_tenant_scope ON iam.mfa_factors TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_mfa_recovery_codes_owner_migration ON iam.mfa_recovery_codes TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_mfa_recovery_codes_tenant_scope ON iam.mfa_recovery_codes TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_service_identities_owner_migration ON iam.service_identities TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_service_identities_tenant_scope ON iam.service_identities TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_sessions_owner_migration ON iam.sessions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_sessions_tenant_scope ON iam.sessions TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_users_owner_migration ON iam.users TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_users_tenant_scope ON iam.users TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

ALTER TABLE iam.service_identities ENABLE ROW LEVEL SECURITY;

ALTER TABLE iam.sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE iam.users ENABLE ROW LEVEL SECURITY;

ALTER TABLE operations.operation_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE operations.operations ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_operation_events_owner_migration ON operations.operation_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_operation_events_tenant_scope ON operations.operation_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM operations.operations o
  WHERE ((o.id = operation_events.operation_id) AND (o.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (o.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM operations.operations o
  WHERE ((o.id = operation_events.operation_id) AND (o.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (o.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_operations_owner_migration ON operations.operations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_operations_tenant_scope ON operations.operations TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE organization.memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE organization.organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_memberships_owner_migration ON organization.memberships TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_memberships_tenant_scope ON organization.memberships TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_organizations_owner_migration ON organization.organizations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_organizations_tenant_scope ON organization.organizations TO ai_res_api_group USING ((id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

ALTER TABLE platform.idempotency_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_idempotency_records_owner_migration ON platform.idempotency_records TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_idempotency_records_tenant_scope ON platform.idempotency_records TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_project_memberships_owner_migration ON project.project_memberships TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_project_memberships_tenant_scope ON project.project_memberships TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_projects_owner_migration ON project.projects TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_projects_tenant_scope ON project.projects TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

ALTER TABLE project.project_memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.epics ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_epics_owner_migration ON work.epics TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_epics_tenant_scope ON work.epics TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_dependencies_owner_migration ON work.task_dependencies TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_dependencies_tenant_scope ON work.task_dependencies TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_tasks_owner_migration ON work.tasks TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_tasks_tenant_scope ON work.tasks TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE work.task_dependencies ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.tasks ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA agents TO ai_res_api_group;
GRANT USAGE ON SCHEMA agents TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA agents TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA artifacts TO ai_res_api_group;

GRANT USAGE ON SCHEMA audit TO ai_res_api_group;
GRANT USAGE ON SCHEMA audit TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA audit TO ai_res_consumer_group;
GRANT USAGE ON SCHEMA audit TO ai_res_auditor_group;

GRANT USAGE ON SCHEMA context TO ai_res_api_group;

GRANT USAGE ON SCHEMA decisions TO ai_res_api_group;

GRANT USAGE ON SCHEMA execution TO ai_res_api_group;
GRANT USAGE ON SCHEMA execution TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA governance TO ai_res_api_group;

GRANT USAGE ON SCHEMA iam TO ai_res_api_group;

GRANT USAGE ON SCHEMA integrations TO ai_res_api_group;

GRANT USAGE ON SCHEMA knowledge TO ai_res_api_group;

GRANT USAGE ON SCHEMA operations TO ai_res_api_group;
GRANT USAGE ON SCHEMA operations TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA operations TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA organization TO ai_res_api_group;

GRANT USAGE ON SCHEMA platform TO ai_res_api_group;

GRANT USAGE ON SCHEMA project TO ai_res_api_group;

REVOKE USAGE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA requirements TO ai_res_api_group;

GRANT USAGE ON SCHEMA sources TO ai_res_api_group;

GRANT USAGE ON SCHEMA traceability TO ai_res_api_group;

GRANT USAGE ON SCHEMA work TO ai_res_api_group;

REVOKE ALL ON FUNCTION agents.assert_worker_run_started_ready() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.guard_worker_run_start() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.require_started_open_run() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_outbox_matches_event() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.guard_check_result_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.lock_run_for_evaluation() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.assert_event_sequence_contiguous() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.forbid_unset() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.freeze_when_status_in() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_columns_immutable() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_terminal_status() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.reject_modification() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.touch_row() FROM PUBLIC;

REVOKE ALL ON FUNCTION work.require_open_operation() FROM PUBLIC;

GRANT SELECT,INSERT ON TABLE agents.worker_results TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE agents.worker_run_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE agents.worker_runs TO ai_res_api_group;

GRANT INSERT ON TABLE audit.audit_events TO ai_res_api_group;
GRANT SELECT ON TABLE audit.audit_events TO ai_res_auditor_group;

GRANT SELECT,INSERT ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(status) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(processed_at) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(error_code) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT INSERT ON TABLE audit.outbox_events TO ai_res_api_group;
GRANT SELECT ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(status) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(available_at) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(attempt_count) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(last_error_code) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(lease_owner) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(lease_until) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT UPDATE(published_at) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT SELECT,INSERT ON TABLE execution.readiness_check_results TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE execution.readiness_evaluations TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.credentials TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.mfa_factors TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.mfa_recovery_codes TO ai_res_api_group;

GRANT SELECT ON TABLE iam.roles TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.service_identities TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.sessions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.users TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE operations.operation_events TO ai_res_api_group;

GRANT SELECT ON TABLE operations.operation_types TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE operations.operations TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.memberships TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.organizations TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE platform.idempotency_records TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE project.project_memberships TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE project.projects TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE work.epics TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.task_dependencies TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE work.tasks TO ai_res_api_group;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TYPES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC;
