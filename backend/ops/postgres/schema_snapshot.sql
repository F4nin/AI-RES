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

CREATE FUNCTION artifacts.guard_publication_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE s text;
BEGIN  -- only an APPROVED (or already PUBLISHED, another channel) version can be published; publication never changes content
  SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
  IF s IS NULL OR s NOT IN ('APPROVED','PUBLISHED') THEN
    RAISE EXCEPTION 'artifact version % is % and cannot be published', NEW.artifact_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION artifacts.guard_publication_insert() OWNER TO ai_res_owner;

CREATE FUNCTION audit.assert_checkpoint_advances() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- a consumer checkpoint only moves forward: a regression would let an old event be applied again
  IF NEW.last_sequence <= OLD.last_sequence THEN
    RAISE EXCEPTION 'inbox checkpoint of % for % % must advance (% -> %)', OLD.consumer_name, OLD.aggregate_type, OLD.aggregate_id, OLD.last_sequence, NEW.last_sequence
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION audit.assert_checkpoint_advances() OWNER TO ai_res_owner;

CREATE FUNCTION audit.assert_outbox_matches_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
END $$;

ALTER FUNCTION audit.assert_outbox_matches_event() OWNER TO ai_res_owner;

CREATE FUNCTION audit.assert_replay_count_step() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- replay_count is a counter of controlled replays: it moves by exactly one, and only together with QUARANTINED -> PENDING
  IF NEW.replay_count IS DISTINCT FROM OLD.replay_count
     AND NOT (NEW.replay_count = OLD.replay_count + 1 AND OLD.status = 'QUARANTINED' AND NEW.status = 'PENDING') THEN
    RAISE EXCEPTION 'outbox row % replay_count may only grow by one when a quarantined row is replayed', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION audit.assert_replay_count_step() OWNER TO ai_res_owner;

CREATE FUNCTION context.assert_package_version_complete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE n int; expected int; vid uuid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
BEGIN  -- deferred: exactly item_count items (a partially written context snapshot rolls back)
  SELECT item_count INTO expected FROM context.context_package_versions WHERE id = vid;
  IF expected IS NULL THEN RETURN NULL; END IF;
  SELECT count(*) INTO n FROM context.context_package_items WHERE context_package_version_id = vid;
  IF n <> expected THEN RAISE EXCEPTION 'context package version % declares % items but holds %', vid, expected, n USING ERRCODE = 'integrity_constraint_violation'; END IF;
  RETURN NULL;
END $$;

ALTER FUNCTION context.assert_package_version_complete() OWNER TO ai_res_owner;

CREATE FUNCTION context.guard_item_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE c timestamptz;
BEGIN  -- sealed after the creating transaction; a rule item must be an APPROVED rule version VISIBLE to this tenant (RLS: SYSTEM or own organization/project)
  SELECT created_at INTO c FROM context.context_package_versions WHERE id = NEW.context_package_version_id;
  IF c IS NULL OR c <> now() THEN
    RAISE EXCEPTION 'context package version % is sealed: items can only be added in the transaction that creates it', NEW.context_package_version_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.rule_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM governance.rule_versions r WHERE r.id = NEW.rule_version_id AND r.status = 'APPROVED') THEN
    RAISE EXCEPTION 'rule version % is not an approved rule version of this tenant', NEW.rule_version_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION context.guard_item_insert() OWNER TO ai_res_owner;

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

CREATE FUNCTION governance.assert_baseline_approved() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- deferred: a baseline exists only together with an APPROVED approval of a human user for exactly this baseline (written in the same transaction)
  IF NOT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.baseline_id = NEW.id AND a.decision = 'APPROVED') THEN
    RAISE EXCEPTION 'baseline % has no APPROVED approval of a human user', NEW.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END $$;

ALTER FUNCTION governance.assert_baseline_approved() OWNER TO ai_res_owner;

CREATE FUNCTION governance.assert_baseline_complete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE n int; expected int;
BEGIN  -- deferred: the baseline holds exactly item_count items (a partial snapshot rolls the transaction back)
  SELECT item_count INTO expected FROM governance.baselines WHERE id = (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  IF expected IS NULL THEN RETURN NULL; END IF;
  SELECT count(*) INTO n FROM governance.baseline_items WHERE baseline_id = (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  IF n <> expected THEN RAISE EXCEPTION 'baseline % declares % items but holds %', (to_jsonb(NEW) ->> TG_ARGV[0]), expected, n USING ERRCODE = 'integrity_constraint_violation'; END IF;
  RETURN NULL;
END $$;

ALTER FUNCTION governance.assert_baseline_complete() OWNER TO ai_res_owner;

CREATE FUNCTION governance.guard_approval_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE s text;
BEGIN  -- a decision is recorded only for a version that can still be decided
  IF NEW.requirement_version_id IS NOT NULL THEN SELECT status INTO s FROM requirements.requirement_versions WHERE id = NEW.requirement_version_id;
  ELSIF NEW.artifact_version_id IS NOT NULL THEN SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
  ELSE RETURN NEW; END IF;
  IF s IS NULL OR s IN ('REJECTED','SUPERSEDED','ARCHIVED') THEN
    RAISE EXCEPTION 'cannot record a decision for a version in status %', coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_approval_insert() OWNER TO ai_res_owner;

CREATE FUNCTION governance.guard_baseline_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE prev int;
BEGIN  -- baselines form a chain: number n follows exactly number n-1 of the same project (no forks)
  IF NEW.previous_baseline_id IS NOT NULL THEN
    SELECT baseline_number INTO prev FROM governance.baselines WHERE id = NEW.previous_baseline_id;
    IF prev IS DISTINCT FROM NEW.baseline_number - 1 THEN
      RAISE EXCEPTION 'baseline % must follow baseline number %', NEW.baseline_number, NEW.baseline_number - 1 USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_baseline_insert() OWNER TO ai_res_owner;

CREATE FUNCTION governance.guard_baseline_item_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE b timestamptz; s text;
BEGIN  -- items exist only in the transaction that created the baseline, and only for approved versions
  SELECT created_at INTO b FROM governance.baselines WHERE id = NEW.baseline_id;
  IF b IS NULL OR b <> now() THEN
    RAISE EXCEPTION 'baseline % is sealed: items can only be added in the transaction that creates it', NEW.baseline_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.requirement_version_id IS NOT NULL THEN
    SELECT status INTO s FROM requirements.requirement_versions WHERE id = NEW.requirement_version_id;
    IF s IS NULL OR s NOT IN ('APPROVED','IN_BASELINE') THEN RAISE EXCEPTION 'requirement version % is % and cannot enter a baseline', NEW.requirement_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSE
    SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
    IF s IS NULL OR s NOT IN ('APPROVED','PUBLISHED') THEN RAISE EXCEPTION 'artifact version % is % and cannot enter a baseline', NEW.artifact_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_baseline_item_insert() OWNER TO ai_res_owner;

CREATE FUNCTION governance.guard_rule_approver() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- tenant rule versions: the approver is a user of the SAME organization (SYSTEM versions are written only by revisions)
  IF NEW.approver_user_id IS NOT NULL AND NEW.organization_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM iam.users u WHERE u.id = NEW.approver_user_id AND u.organization_id = NEW.organization_id) THEN
    RAISE EXCEPTION 'rule version approver is not a user of the rule''s organization' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_rule_approver() OWNER TO ai_res_owner;

CREATE FUNCTION governance.guard_version_facts() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE ok boolean;
BEGIN  -- BEFORE UPDATE of a version status. Args: [0] kind: REQUIREMENT | ARTIFACT. A status may only claim facts that exist for exactly this version.
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
  IF NEW.status = 'APPROVED' THEN
    IF TG_ARGV[0] = 'REQUIREMENT' THEN
      SELECT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.requirement_version_id = NEW.id AND a.decision = 'APPROVED') INTO ok;
    ELSE
      SELECT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.artifact_version_id = NEW.id AND a.decision = 'APPROVED') INTO ok;
    END IF;
    IF NOT ok THEN RAISE EXCEPTION '% version % cannot become APPROVED without an APPROVED approval of a human user for this exact version', TG_ARGV[0], NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSIF NEW.status = 'IN_BASELINE' THEN
    SELECT EXISTS (SELECT 1 FROM governance.baseline_items i WHERE i.requirement_version_id = NEW.id) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'requirement version % cannot become IN_BASELINE without a baseline item', NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSIF NEW.status = 'PUBLISHED' THEN
    SELECT EXISTS (SELECT 1 FROM artifacts.publications p WHERE p.artifact_version_id = NEW.id) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'artifact version % cannot become PUBLISHED without a publication', NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_version_facts() OWNER TO ai_res_owner;

CREATE FUNCTION platform.advance_by_one() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- TG_ARGV[0] = counter column: a numbering counter moves forward by exactly one per statement (no gaps, no rewinding, no jumps)
  IF (to_jsonb(NEW) ->> TG_ARGV[0])::bigint <> (to_jsonb(OLD) ->> TG_ARGV[0])::bigint + 1 THEN
    RAISE EXCEPTION '%.% must advance by exactly 1', TG_TABLE_NAME, TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.advance_by_one() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.assert_version_number_contiguous() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
DECLARE pid uuid; last_no int; mx int; no int; has_prev boolean;
BEGIN  -- deferred to COMMIT. Args: [0] column of NEW holding the aggregate id, [1] aggregate table, [2] version table, [3] version-table FK column to the aggregate.
  pid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  EXECUTE format('SELECT last_version_number FROM %s WHERE id = $1', TG_ARGV[1]::regclass) INTO last_no USING pid;
  IF last_no IS NULL THEN RETURN NULL; END IF;
  EXECUTE format('SELECT coalesce(max(version_number), 0) FROM %s WHERE %I = $1', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO mx USING pid;
  IF mx <> last_no THEN
    RAISE EXCEPTION 'version numbers of % are not contiguous: last_version_number=%, max version number=%', pid, last_no, mx USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_RELID <> TG_ARGV[2]::regclass THEN RETURN NULL; END IF;
  no := (to_jsonb(NEW) ->> 'version_number')::int;
  IF no > 1 THEN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE %I = $1 AND version_number = $2)', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO has_prev USING pid, no - 1;
    IF NOT has_prev THEN RAISE EXCEPTION 'version numbers of % have a gap before %', pid, no USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NULL;
END $_$;

ALTER FUNCTION platform.assert_version_number_contiguous() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.guard_status_transition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE i int; o text := to_jsonb(OLD) ->> TG_ARGV[0]; n text := to_jsonb(NEW) ->> TG_ARGV[0];
BEGIN  -- TG_ARGV[0] = status column, TG_ARGV[1..] = allowed 'FROM>TO' pairs; a status that is not changed is not checked
  IF o IS NOT DISTINCT FROM n THEN RETURN NEW; END IF;
  FOR i IN 1 .. TG_NARGS - 1 LOOP
    IF TG_ARGV[i] = o || '>' || n THEN RETURN NEW; END IF;
  END LOOP;
  RAISE EXCEPTION '%.% status transition % -> % is not allowed', TG_TABLE_SCHEMA, TG_TABLE_NAME, o, n USING ERRCODE = 'integrity_constraint_violation';
END $$;

ALTER FUNCTION platform.guard_status_transition() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.keep_non_decreasing() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN  -- TG_ARGV = bigint columns that may only grow once set (NULL -> value is allowed, value -> smaller/NULL is not)
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF o ->> c IS NOT NULL AND (n ->> c IS NULL OR (n ->> c)::bigint < (o ->> c)::bigint) THEN
      RAISE EXCEPTION 'column %.% can only increase', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.keep_non_decreasing() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.require_initial_state() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE i int; n jsonb := to_jsonb(NEW);
BEGIN  -- BEFORE INSERT. Args: [0] status column, [1] comma-separated allowed initial statuses, [2..] columns that must be NULL at creation (lifecycle facts are earned, never supplied)
  IF (n ->> TG_ARGV[0] = ANY (string_to_array(TG_ARGV[1], ','))) IS NOT TRUE THEN  -- unknown column or NULL status fails closed
    RAISE EXCEPTION '%.% must start in one of (%), not %', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[1], n ->> TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  FOR i IN 2 .. TG_NARGS - 1 LOOP
    IF (n ? TG_ARGV[i]) IS NOT TRUE OR (n -> TG_ARGV[i]) IS DISTINCT FROM 'null'::jsonb THEN  -- a mistyped column name raises instead of skipping the rule
      RAISE EXCEPTION '%.%: column % cannot be supplied at creation', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[i] USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.require_initial_state() OWNER TO ai_res_owner;

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

CREATE FUNCTION sources.guard_source_version_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE u record;
BEGIN  -- a version made from an upload needs a VERIFIED upload of the SAME source with the same checksum, size and media type (checksum verified before processing)
  IF NEW.upload_id IS NOT NULL THEN
    SELECT * INTO u FROM sources.uploads WHERE id = NEW.upload_id;
    IF NOT FOUND OR u.status <> 'VERIFIED' OR u.source_id <> NEW.source_id OR u.verified_sha256 <> NEW.checksum_sha256 OR u.actual_size_bytes <> NEW.size_bytes
       OR u.object_key IS DISTINCT FROM NEW.object_key OR u.declared_media_type <> NEW.media_type THEN
      RAISE EXCEPTION 'source version %: its upload is missing, not VERIFIED, or does not match source/checksum/size/media type/object key', NEW.id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION sources.guard_source_version_insert() OWNER TO ai_res_owner;

CREATE FUNCTION traceability.assert_endpoint_exists() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
DECLARE t text; ok boolean; side text;
BEGIN  -- polymorphic endpoints cannot carry FKs: the object must exist in THIS tenant (RLS applies); an unmapped object type fails closed
  FOREACH side IN ARRAY ARRAY['source', 'target'] LOOP
    t := CASE to_jsonb(NEW) ->> (side || '_object_type') WHEN 'REQUIREMENT' THEN 'requirements.requirements' WHEN 'REQUIREMENT_VERSION' THEN 'requirements.requirement_versions' WHEN 'SOURCE_VERSION' THEN 'sources.source_versions' WHEN 'ARTIFACT_VERSION' THEN 'artifacts.artifact_versions' WHEN 'TASK' THEN 'work.tasks' WHEN 'EPIC' THEN 'work.epics' WHEN 'DECISION' THEN 'decisions.decisions' WHEN 'ASSUMPTION' THEN 'decisions.assumptions' WHEN 'RISK' THEN 'decisions.risks' WHEN 'ISSUE' THEN 'decisions.issues' WHEN 'UNKNOWN_ITEM' THEN 'decisions.unknowns' WHEN 'HYPOTHESIS' THEN 'decisions.hypotheses' WHEN 'CONFLICT' THEN 'decisions.conflicts' END;
    IF t IS NULL THEN RAISE EXCEPTION 'traceability %: object type % has no endpoint mapping', side, to_jsonb(NEW) ->> (side || '_object_type') USING ERRCODE = 'integrity_constraint_violation'; END IF;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE id = $1 AND organization_id = $2 AND project_id = $3)', t::regclass)
      INTO ok USING (to_jsonb(NEW) ->> (side || '_object_id'))::uuid, NEW.organization_id, NEW.project_id;
    IF NOT ok THEN RAISE EXCEPTION 'traceability % endpoint % does not exist in this project', side, to_jsonb(NEW) ->> (side || '_object_id') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END LOOP;
  RETURN NEW;
END $_$;

ALTER FUNCTION traceability.assert_endpoint_exists() OWNER TO ai_res_owner;

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

CREATE TABLE artifacts.artifact_events (
    event_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
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
    CONSTRAINT ck_artifact_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_artifact_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_artifact_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_artifact_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY artifacts.artifact_events FORCE ROW LEVEL SECURITY;

ALTER TABLE artifacts.artifact_events OWNER TO ai_res_owner;

CREATE TABLE artifacts.artifact_types (
    code text NOT NULL,
    title text NOT NULL,
    source_of_truth_mode text NOT NULL,
    CONSTRAINT ck_artifact_types_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_artifact_types_source_of_truth_mode CHECK ((source_of_truth_mode = ANY (ARRAY['DOMAIN_MODEL'::text, 'NATIVE_SPEC'::text, 'DOCUMENT_SOURCE'::text, 'EXTERNAL_SOURCE'::text])))
);

ALTER TABLE artifacts.artifact_types OWNER TO ai_res_owner;

CREATE TABLE artifacts.artifact_version_statuses (
    code text NOT NULL,
    CONSTRAINT ck_artifact_version_statuses_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE artifacts.artifact_version_statuses OWNER TO ai_res_owner;

CREATE TABLE artifacts.artifact_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    version_number integer NOT NULL,
    schema_version text NOT NULL,
    content_ref jsonb NOT NULL,
    content_checksum bytea NOT NULL,
    provenance jsonb NOT NULL,
    change_reason text,
    author_type text NOT NULL,
    author_id uuid,
    status text DEFAULT 'DRAFT'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_versions_author_type CHECK ((author_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'WORKER_RUN'::text, 'IMPORT'::text]))),
    CONSTRAINT ck_artifact_versions_change_reason CHECK (((version_number = 1) OR (length(btrim(change_reason)) > 0))),
    CONSTRAINT ck_artifact_versions_content_checksum CHECK ((octet_length(content_checksum) = 32)),
    CONSTRAINT ck_artifact_versions_content_ref CHECK ((jsonb_typeof(content_ref) = 'object'::text)),
    CONSTRAINT ck_artifact_versions_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_artifact_versions_schema_version CHECK (((length(schema_version) >= 1) AND (length(schema_version) <= 100))),
    CONSTRAINT ck_artifact_versions_version_number CHECK ((version_number > 0))
);

ALTER TABLE ONLY artifacts.artifact_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE artifacts.artifact_versions OWNER TO ai_res_owner;

CREATE TABLE artifacts.artifacts (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_type text NOT NULL,
    source_of_truth_mode text NOT NULL,
    title text NOT NULL,
    purpose text,
    owner_user_id uuid,
    epic_id uuid,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    current_version_id uuid,
    last_version_number integer DEFAULT 0 NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifacts_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_artifacts_last_version_number CHECK ((last_version_number >= 0)),
    CONSTRAINT ck_artifacts_pointer_needs_version CHECK (((current_version_id IS NULL) OR (last_version_number > 0))),
    CONSTRAINT ck_artifacts_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_artifacts_source_of_truth_mode CHECK ((source_of_truth_mode = ANY (ARRAY['DOMAIN_MODEL'::text, 'NATIVE_SPEC'::text, 'DOCUMENT_SOURCE'::text, 'EXTERNAL_SOURCE'::text]))),
    CONSTRAINT ck_artifacts_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text]))),
    CONSTRAINT ck_artifacts_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY artifacts.artifacts FORCE ROW LEVEL SECURITY;

ALTER TABLE artifacts.artifacts OWNER TO ai_res_owner;

CREATE TABLE artifacts.publications (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_version_id uuid NOT NULL,
    channel text DEFAULT 'DEFAULT'::text NOT NULL,
    published_by uuid NOT NULL,
    published_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_publications_channel CHECK ((channel ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE ONLY artifacts.publications FORCE ROW LEVEL SECURITY;

ALTER TABLE artifacts.publications OWNER TO ai_res_owner;

CREATE TABLE artifacts.validation_reports (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_version_id uuid NOT NULL,
    validators jsonb NOT NULL,
    status text NOT NULL,
    findings jsonb DEFAULT '[]'::jsonb NOT NULL,
    produced_by_type text NOT NULL,
    produced_by_id uuid,
    validated_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_validation_reports_findings CHECK ((jsonb_typeof(findings) = 'array'::text)),
    CONSTRAINT ck_validation_reports_produced_by_type CHECK ((produced_by_type = ANY (ARRAY['SYSTEM'::text, 'SERVICE'::text, 'WORKER_RUN'::text]))),
    CONSTRAINT ck_validation_reports_status CHECK ((status = ANY (ARRAY['PASSED'::text, 'PASSED_WITH_WARNINGS'::text, 'FAILED'::text, 'ERROR'::text]))),
    CONSTRAINT ck_validation_reports_validators CHECK (((jsonb_typeof(validators) = 'array'::text) AND (jsonb_array_length(validators) > 0)))
);

ALTER TABLE ONLY artifacts.validation_reports FORCE ROW LEVEL SECURITY;

ALTER TABLE artifacts.validation_reports OWNER TO ai_res_owner;

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

CREATE TABLE audit.inbox_checkpoints (
    consumer_name text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    last_sequence bigint NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_inbox_checkpoints_consumer_name CHECK (((length(consumer_name) >= 1) AND (length(consumer_name) <= 200))),
    CONSTRAINT ck_inbox_checkpoints_last_sequence CHECK ((last_sequence > 0))
);

ALTER TABLE ONLY audit.inbox_checkpoints FORCE ROW LEVEL SECURITY;

ALTER TABLE audit.inbox_checkpoints OWNER TO ai_res_owner;

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
    replay_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_outbox_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_outbox_events_attempt_count CHECK ((attempt_count >= 0)),
    CONSTRAINT ck_outbox_events_destination CHECK (((length(destination) >= 1) AND (length(destination) <= 200))),
    CONSTRAINT ck_outbox_events_last_error_code CHECK ((last_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_outbox_events_lease_iff_in_flight CHECK ((((status = 'IN_FLIGHT'::text) = ((lease_owner IS NOT NULL) AND (lease_until IS NOT NULL))) AND ((lease_owner IS NULL) = (lease_until IS NULL)))),
    CONSTRAINT ck_outbox_events_published_iff_published CHECK (((status = 'PUBLISHED'::text) = (published_at IS NOT NULL))),
    CONSTRAINT ck_outbox_events_replay_count CHECK ((replay_count >= 0)),
    CONSTRAINT ck_outbox_events_schema_version CHECK ((schema_version > 0)),
    CONSTRAINT ck_outbox_events_status CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text, 'PUBLISHED'::text, 'QUARANTINED'::text])))
);

ALTER TABLE ONLY audit.outbox_events FORCE ROW LEVEL SECURITY;

ALTER TABLE audit.outbox_events OWNER TO ai_res_owner;

CREATE TABLE context.context_package_items (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    context_package_version_id uuid NOT NULL,
    item_kind text NOT NULL,
    source_version_id uuid,
    requirement_version_id uuid,
    artifact_version_id uuid,
    rule_version_id uuid,
    inclusion_role text NOT NULL,
    locator jsonb,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_context_package_items_inclusion_role CHECK ((inclusion_role ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_context_package_items_item_kind CHECK ((item_kind = ANY (ARRAY['SOURCE_VERSION'::text, 'REQUIREMENT_VERSION'::text, 'ARTIFACT_VERSION'::text, 'RULE_VERSION'::text]))),
    CONSTRAINT ck_context_package_items_kind_matches_ref CHECK ((((item_kind = 'SOURCE_VERSION'::text) AND (source_version_id IS NOT NULL) AND (requirement_version_id IS NULL) AND (artifact_version_id IS NULL) AND (rule_version_id IS NULL)) OR ((item_kind = 'REQUIREMENT_VERSION'::text) AND (requirement_version_id IS NOT NULL) AND (source_version_id IS NULL) AND (artifact_version_id IS NULL) AND (rule_version_id IS NULL)) OR ((item_kind = 'ARTIFACT_VERSION'::text) AND (artifact_version_id IS NOT NULL) AND (source_version_id IS NULL) AND (requirement_version_id IS NULL) AND (rule_version_id IS NULL)) OR ((item_kind = 'RULE_VERSION'::text) AND (rule_version_id IS NOT NULL) AND (source_version_id IS NULL) AND (requirement_version_id IS NULL) AND (artifact_version_id IS NULL)))),
    CONSTRAINT ck_context_package_items_locator CHECK ((jsonb_typeof(locator) = 'object'::text)),
    CONSTRAINT ck_context_package_items_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text))
);

ALTER TABLE ONLY context.context_package_items FORCE ROW LEVEL SECURITY;

ALTER TABLE context.context_package_items OWNER TO ai_res_owner;

CREATE TABLE context.context_package_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    context_package_id uuid NOT NULL,
    version_number integer NOT NULL,
    item_count integer NOT NULL,
    content_digest bytea NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_context_package_versions_content_digest CHECK ((octet_length(content_digest) = 32)),
    CONSTRAINT ck_context_package_versions_item_count CHECK ((item_count > 0)),
    CONSTRAINT ck_context_package_versions_version_number CHECK ((version_number > 0))
);

ALTER TABLE ONLY context.context_package_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE context.context_package_versions OWNER TO ai_res_owner;

CREATE TABLE context.context_packages (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    name text NOT NULL,
    current_version_id uuid,
    last_version_number integer DEFAULT 0 NOT NULL,
    created_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_context_packages_last_version_number CHECK ((last_version_number >= 0)),
    CONSTRAINT ck_context_packages_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 240))),
    CONSTRAINT ck_context_packages_pointer_needs_version CHECK (((current_version_id IS NULL) OR (last_version_number > 0))),
    CONSTRAINT ck_context_packages_row_version CHECK ((row_version > 0))
);

ALTER TABLE ONLY context.context_packages FORCE ROW LEVEL SECURITY;

ALTER TABLE context.context_packages OWNER TO ai_res_owner;

CREATE TABLE decisions.assumptions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    statement text NOT NULL,
    consequences_if_wrong text,
    verification_method text,
    verification_criteria text,
    expires_at timestamp with time zone,
    review_trigger text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_assumptions_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_assumptions_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_assumptions_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_assumptions_statement CHECK ((length(btrim(statement)) > 0)),
    CONSTRAINT ck_assumptions_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_assumptions_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.assumptions FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.assumptions OWNER TO ai_res_owner;

CREATE TABLE decisions.conflicts (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    conflicting_refs jsonb NOT NULL,
    classification text,
    resolution_approach text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_conflicts_conflicting_refs CHECK (((jsonb_typeof(conflicting_refs) = 'array'::text) AND (jsonb_array_length(conflicting_refs) >= 2))),
    CONSTRAINT ck_conflicts_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_conflicts_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_conflicts_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_conflicts_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_conflicts_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.conflicts FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.conflicts OWNER TO ai_res_owner;

CREATE TABLE decisions.decisions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    question text NOT NULL,
    alternatives jsonb DEFAULT '[]'::jsonb NOT NULL,
    chosen_option text,
    rationale text,
    consequences text,
    approver_user_id uuid,
    review_trigger text,
    scope_description text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_decisions_alternatives CHECK ((jsonb_typeof(alternatives) = 'array'::text)),
    CONSTRAINT ck_decisions_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_decisions_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_decisions_question CHECK ((length(btrim(question)) > 0)),
    CONSTRAINT ck_decisions_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_decisions_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_decisions_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.decisions OWNER TO ai_res_owner;

CREATE TABLE decisions.hypotheses (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    statement text NOT NULL,
    grounds text,
    test_method text,
    result text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_hypotheses_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_hypotheses_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_hypotheses_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_hypotheses_statement CHECK ((length(btrim(statement)) > 0)),
    CONSTRAINT ck_hypotheses_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_hypotheses_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.hypotheses FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.hypotheses OWNER TO ai_res_owner;

CREATE TABLE decisions.issues (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    description text NOT NULL,
    actual_impact text,
    resolution text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issues_description CHECK ((length(btrim(description)) > 0)),
    CONSTRAINT ck_issues_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_issues_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_issues_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_issues_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_issues_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.issues FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.issues OWNER TO ai_res_owner;

CREATE TABLE decisions.risks (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    cause text,
    risk_event text NOT NULL,
    consequences text,
    probability text DEFAULT 'UNKNOWN'::text NOT NULL,
    impact text DEFAULT 'UNKNOWN'::text NOT NULL,
    triggers jsonb DEFAULT '[]'::jsonb NOT NULL,
    mitigation text,
    contingency text,
    residual_risk text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_risks_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_risks_impact CHECK ((impact ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_risks_probability CHECK ((probability ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_risks_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_risks_risk_event CHECK ((length(btrim(risk_event)) > 0)),
    CONSTRAINT ck_risks_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_risks_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_risks_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240))),
    CONSTRAINT ck_risks_triggers CHECK ((jsonb_typeof(triggers) = 'array'::text))
);

ALTER TABLE ONLY decisions.risks FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.risks OWNER TO ai_res_owner;

CREATE TABLE decisions.unknowns (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    task_id uuid,
    title text NOT NULL,
    status text NOT NULL,
    owner_user_id uuid,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance jsonb DEFAULT '{}'::jsonb NOT NULL,
    information_gap text NOT NULL,
    affected_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    closing_condition text,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_unknowns_affected_refs CHECK ((jsonb_typeof(affected_refs) = 'array'::text)),
    CONSTRAINT ck_unknowns_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_unknowns_information_gap CHECK ((length(btrim(information_gap)) > 0)),
    CONSTRAINT ck_unknowns_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_unknowns_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_unknowns_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_unknowns_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY decisions.unknowns FORCE ROW LEVEL SECURITY;

ALTER TABLE decisions.unknowns OWNER TO ai_res_owner;

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

CREATE TABLE governance.approvals (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    requirement_version_id uuid,
    artifact_version_id uuid,
    baseline_id uuid,
    decision text NOT NULL,
    approver_user_id uuid NOT NULL,
    rationale text,
    decided_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_approvals_decision CHECK ((decision = ANY (ARRAY['APPROVED'::text, 'REJECTED'::text]))),
    CONSTRAINT ck_approvals_exactly_one_target CHECK ((((((requirement_version_id IS NOT NULL))::integer + ((artifact_version_id IS NOT NULL))::integer) + ((baseline_id IS NOT NULL))::integer) = 1))
);

ALTER TABLE ONLY governance.approvals FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.approvals OWNER TO ai_res_owner;

CREATE TABLE governance.baseline_events (
    event_id uuid NOT NULL,
    baseline_id uuid NOT NULL,
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
    CONSTRAINT ck_baseline_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_baseline_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_baseline_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_baseline_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY governance.baseline_events FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.baseline_events OWNER TO ai_res_owner;

CREATE TABLE governance.baseline_items (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    baseline_id uuid NOT NULL,
    requirement_version_id uuid,
    artifact_version_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_baseline_items_exactly_one_target CHECK (((requirement_version_id IS NOT NULL) <> (artifact_version_id IS NOT NULL)))
);

ALTER TABLE ONLY governance.baseline_items FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.baseline_items OWNER TO ai_res_owner;

CREATE TABLE governance.baselines (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    baseline_number integer NOT NULL,
    name text NOT NULL,
    previous_baseline_id uuid,
    change_request_id uuid,
    item_count integer NOT NULL,
    last_event_sequence bigint DEFAULT 1 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_baselines_baseline_number CHECK ((baseline_number > 0)),
    CONSTRAINT ck_baselines_change_control CHECK ((((previous_baseline_id IS NULL) = (baseline_number = 1)) AND ((baseline_number = 1) OR (change_request_id IS NOT NULL)))),
    CONSTRAINT ck_baselines_item_count CHECK ((item_count > 0)),
    CONSTRAINT ck_baselines_last_event_sequence CHECK ((last_event_sequence = 1)),
    CONSTRAINT ck_baselines_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 240)))
);

ALTER TABLE ONLY governance.baselines FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.baselines OWNER TO ai_res_owner;

CREATE TABLE governance.change_request_events (
    event_id uuid NOT NULL,
    change_request_id uuid NOT NULL,
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
    CONSTRAINT ck_change_request_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_change_request_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_change_request_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_change_request_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY governance.change_request_events FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.change_request_events OWNER TO ai_res_owner;

CREATE TABLE governance.change_requests (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    display_number bigint NOT NULL,
    title text NOT NULL,
    rationale text NOT NULL,
    base_baseline_id uuid,
    status text DEFAULT 'DRAFT'::text NOT NULL,
    requested_by uuid NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_change_requests_display_number CHECK ((display_number > 0)),
    CONSTRAINT ck_change_requests_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_change_requests_rationale CHECK ((length(btrim(rationale)) > 0)),
    CONSTRAINT ck_change_requests_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_change_requests_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_change_requests_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY governance.change_requests FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.change_requests OWNER TO ai_res_owner;

CREATE TABLE governance.reviews (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    requirement_version_id uuid,
    artifact_version_id uuid,
    reviewer_type text NOT NULL,
    reviewer_id uuid NOT NULL,
    outcome text NOT NULL,
    findings jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_reviews_exactly_one_target CHECK (((requirement_version_id IS NOT NULL) <> (artifact_version_id IS NOT NULL))),
    CONSTRAINT ck_reviews_findings CHECK ((jsonb_typeof(findings) = 'array'::text)),
    CONSTRAINT ck_reviews_outcome CHECK ((outcome = ANY (ARRAY['NO_FINDINGS'::text, 'FINDINGS'::text, 'BLOCKING_FINDINGS'::text]))),
    CONSTRAINT ck_reviews_reviewer_type CHECK ((reviewer_type = ANY (ARRAY['USER'::text, 'WORKER_RUN'::text])))
);

ALTER TABLE ONLY governance.reviews FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.reviews OWNER TO ai_res_owner;

CREATE TABLE governance.rule_versions (
    id uuid NOT NULL,
    rule_id uuid NOT NULL,
    level text NOT NULL,
    organization_id uuid,
    project_id uuid,
    version_number integer NOT NULL,
    condition jsonb NOT NULL,
    action jsonb NOT NULL,
    applicability jsonb DEFAULT '{}'::jsonb NOT NULL,
    rationale text,
    author_type text NOT NULL,
    author_id uuid,
    status text DEFAULT 'DRAFT'::text NOT NULL,
    approver_user_id uuid,
    approved_at timestamp with time zone,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_rule_versions_action CHECK ((jsonb_typeof(action) = 'object'::text)),
    CONSTRAINT ck_rule_versions_applicability CHECK ((jsonb_typeof(applicability) = 'object'::text)),
    CONSTRAINT ck_rule_versions_approved_facts CHECK (((status = ANY (ARRAY['APPROVED'::text, 'RETIRED'::text])) <= ((approver_user_id IS NOT NULL) AND (approved_at IS NOT NULL) AND (valid_from IS NOT NULL)))),
    CONSTRAINT ck_rule_versions_author_type CHECK ((author_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'WORKER_RUN'::text, 'IMPORT'::text]))),
    CONSTRAINT ck_rule_versions_condition CHECK ((jsonb_typeof(condition) = 'object'::text)),
    CONSTRAINT ck_rule_versions_level_scope CHECK ((((level = 'SYSTEM'::text) AND (organization_id IS NULL) AND (project_id IS NULL)) OR ((level = 'ORGANIZATION'::text) AND (organization_id IS NOT NULL) AND (project_id IS NULL)) OR ((level = 'PROJECT'::text) AND (organization_id IS NOT NULL) AND (project_id IS NOT NULL)))),
    CONSTRAINT ck_rule_versions_status CHECK ((status = ANY (ARRAY['DRAFT'::text, 'PROPOSED'::text, 'APPROVED'::text, 'REJECTED'::text, 'RETIRED'::text]))),
    CONSTRAINT ck_rule_versions_validity CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to > valid_from))),
    CONSTRAINT ck_rule_versions_version_number CHECK ((version_number > 0))
);

ALTER TABLE ONLY governance.rule_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_versions OWNER TO ai_res_owner;

CREATE TABLE governance.rules (
    id uuid NOT NULL,
    level text NOT NULL,
    organization_id uuid,
    project_id uuid,
    rule_key text NOT NULL,
    title text NOT NULL,
    applies_to_object_type text,
    created_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_rules_applies_to_object_type CHECK ((applies_to_object_type ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_rules_level CHECK ((level = ANY (ARRAY['SYSTEM'::text, 'ORGANIZATION'::text, 'PROJECT'::text]))),
    CONSTRAINT ck_rules_level_scope CHECK ((((level = 'SYSTEM'::text) AND (organization_id IS NULL) AND (project_id IS NULL)) OR ((level = 'ORGANIZATION'::text) AND (organization_id IS NOT NULL) AND (project_id IS NULL)) OR ((level = 'PROJECT'::text) AND (organization_id IS NOT NULL) AND (project_id IS NOT NULL)))),
    CONSTRAINT ck_rules_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_rules_rule_key CHECK ((rule_key ~ '^[A-Za-z][A-Za-z0-9_.-]{0,99}$'::text)),
    CONSTRAINT ck_rules_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY governance.rules FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rules OWNER TO ai_res_owner;

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
    last_used_step bigint,
    CONSTRAINT ck_mfa_factors_factor_type CHECK ((factor_type = 'TOTP'::text)),
    CONSTRAINT ck_mfa_factors_last_used_step CHECK (((last_used_step IS NULL) OR (last_used_step >= 0))),
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

CREATE TABLE knowledge.extraction_records (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_version_id uuid NOT NULL,
    pipeline_name text NOT NULL,
    pipeline_version text NOT NULL,
    parser_version text NOT NULL,
    attempt integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'STARTED'::text NOT NULL,
    tool_ref text,
    input_version_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    error_code text,
    operation_id uuid,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    created_by uuid,
    CONSTRAINT ck_extraction_records_attempt CHECK ((attempt > 0)),
    CONSTRAINT ck_extraction_records_completed_iff_finished CHECK (((status = 'STARTED'::text) = (completed_at IS NULL))),
    CONSTRAINT ck_extraction_records_error_code CHECK ((error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_extraction_records_failed_has_code CHECK (((status <> 'FAILED'::text) OR (error_code IS NOT NULL))),
    CONSTRAINT ck_extraction_records_input_version_refs CHECK ((jsonb_typeof(input_version_refs) = 'array'::text)),
    CONSTRAINT ck_extraction_records_parser_version CHECK (((length(parser_version) >= 1) AND (length(parser_version) <= 100))),
    CONSTRAINT ck_extraction_records_pipeline_name CHECK (((length(pipeline_name) >= 1) AND (length(pipeline_name) <= 100))),
    CONSTRAINT ck_extraction_records_pipeline_version CHECK (((length(pipeline_version) >= 1) AND (length(pipeline_version) <= 100))),
    CONSTRAINT ck_extraction_records_status CHECK ((status = ANY (ARRAY['STARTED'::text, 'SUCCEEDED'::text, 'PARTIAL'::text, 'FAILED'::text])))
);

ALTER TABLE ONLY knowledge.extraction_records FORCE ROW LEVEL SECURITY;

ALTER TABLE knowledge.extraction_records OWNER TO ai_res_owner;

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

CREATE TABLE platform.bootstrap_state (
    singleton boolean DEFAULT true NOT NULL,
    organization_id uuid NOT NULL,
    secret_digest bytea NOT NULL,
    consumed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_bootstrap_state_secret_digest CHECK ((octet_length(secret_digest) = 32)),
    CONSTRAINT ck_bootstrap_state_singleton CHECK (singleton)
);

ALTER TABLE ONLY platform.bootstrap_state FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.bootstrap_state OWNER TO ai_res_owner;

CREATE TABLE platform.display_number_counters (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    counter_kind text NOT NULL,
    last_number bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_display_number_counters_counter_kind CHECK ((counter_kind ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_display_number_counters_last_number CHECK ((last_number >= 0))
);

ALTER TABLE ONLY platform.display_number_counters FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.display_number_counters OWNER TO ai_res_owner;

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

CREATE TABLE project.project_events (
    event_id uuid NOT NULL,
    project_id uuid NOT NULL,
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
    CONSTRAINT ck_project_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_project_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_project_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_project_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY project.project_events FORCE ROW LEVEL SECURITY;

ALTER TABLE project.project_events OWNER TO ai_res_owner;

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
    goal text,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_projects_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_projects_name CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 200))),
    CONSTRAINT ck_projects_project_type CHECK ((project_type = ANY (ARRAY['GREENFIELD'::text, 'BROWNFIELD'::text, 'HYBRID'::text, 'UNKNOWN'::text]))),
    CONSTRAINT ck_projects_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_projects_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text])))
);

ALTER TABLE ONLY project.projects FORCE ROW LEVEL SECURITY;

ALTER TABLE project.projects OWNER TO ai_res_owner;

CREATE TABLE requirements.requirement_epics (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY requirements.requirement_epics FORCE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirement_epics OWNER TO ai_res_owner;

CREATE TABLE requirements.requirement_events (
    event_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
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
    CONSTRAINT ck_requirement_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_requirement_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_requirement_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_requirement_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY requirements.requirement_events FORCE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirement_events OWNER TO ai_res_owner;

CREATE TABLE requirements.requirement_types (
    code text NOT NULL,
    title text NOT NULL,
    CONSTRAINT ck_requirement_types_code CHECK ((code ~ '^[A-Za-z][A-Za-z]*$'::text))
);

ALTER TABLE requirements.requirement_types OWNER TO ai_res_owner;

CREATE TABLE requirements.requirement_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    version_number integer NOT NULL,
    requirement_type text NOT NULL,
    declared_type_text text,
    statement text NOT NULL,
    rationale text,
    priority text,
    acceptance_criteria jsonb DEFAULT '[]'::jsonb NOT NULL,
    constraints_info jsonb DEFAULT '[]'::jsonb NOT NULL,
    provenance_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    change_reason text,
    author_type text NOT NULL,
    author_id uuid,
    status text DEFAULT 'CANDIDATE'::text NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_requirement_versions_acceptance_criteria CHECK ((jsonb_typeof(acceptance_criteria) = 'array'::text)),
    CONSTRAINT ck_requirement_versions_author_type CHECK ((author_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'WORKER_RUN'::text, 'IMPORT'::text]))),
    CONSTRAINT ck_requirement_versions_change_reason CHECK (((version_number = 1) OR (length(btrim(change_reason)) > 0))),
    CONSTRAINT ck_requirement_versions_confirmed CHECK (((status = ANY (ARRAY['CONFIRMED'::text, 'APPROVED'::text, 'IN_BASELINE'::text])) <= ((confirmed_by IS NOT NULL) AND (confirmed_at IS NOT NULL)))),
    CONSTRAINT ck_requirement_versions_constraints_info CHECK ((jsonb_typeof(constraints_info) = 'array'::text)),
    CONSTRAINT ck_requirement_versions_declared_type_text CHECK (((length(btrim(declared_type_text)) >= 1) AND (length(btrim(declared_type_text)) <= 100))),
    CONSTRAINT ck_requirement_versions_priority CHECK ((priority ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_requirement_versions_provenance_refs CHECK ((jsonb_typeof(provenance_refs) = 'array'::text)),
    CONSTRAINT ck_requirement_versions_statement CHECK ((length(btrim(statement)) > 0)),
    CONSTRAINT ck_requirement_versions_status CHECK ((status = ANY (ARRAY['EXTRACTED'::text, 'CANDIDATE'::text, 'CONFIRMED'::text, 'APPROVED'::text, 'IN_BASELINE'::text, 'SUPERSEDED'::text, 'REJECTED'::text]))),
    CONSTRAINT ck_requirement_versions_unknown_type_keeps_text CHECK (((requirement_type = 'UNKNOWN'::text) = (declared_type_text IS NOT NULL))),
    CONSTRAINT ck_requirement_versions_version_number CHECK ((version_number > 0))
);

ALTER TABLE ONLY requirements.requirement_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirement_versions OWNER TO ai_res_owner;

CREATE TABLE requirements.requirements (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    display_number bigint NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    current_version_id uuid,
    last_version_number integer DEFAULT 0 NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_requirements_display_number CHECK ((display_number > 0)),
    CONSTRAINT ck_requirements_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_requirements_last_version_number CHECK ((last_version_number >= 0)),
    CONSTRAINT ck_requirements_pointer_needs_version CHECK (((current_version_id IS NULL) OR (last_version_number > 0))),
    CONSTRAINT ck_requirements_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_requirements_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text])))
);

ALTER TABLE ONLY requirements.requirements FORCE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirements OWNER TO ai_res_owner;

CREATE TABLE sources.source_events (
    event_id uuid NOT NULL,
    source_id uuid NOT NULL,
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
    CONSTRAINT ck_source_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_source_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_source_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_source_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY sources.source_events FORCE ROW LEVEL SECURITY;

ALTER TABLE sources.source_events OWNER TO ai_res_owner;

CREATE TABLE sources.source_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    version_number integer NOT NULL,
    upload_id uuid,
    media_type text NOT NULL,
    size_bytes bigint NOT NULL,
    checksum_sha256 bytea NOT NULL,
    object_key text,
    external_ref jsonb,
    provenance jsonb NOT NULL,
    received_at timestamp with time zone NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_source_versions_checksum_sha256 CHECK ((octet_length(checksum_sha256) = 32)),
    CONSTRAINT ck_source_versions_exactly_one_location CHECK (((object_key IS NOT NULL) <> (external_ref IS NOT NULL))),
    CONSTRAINT ck_source_versions_external_ref CHECK ((jsonb_typeof(external_ref) = 'object'::text)),
    CONSTRAINT ck_source_versions_media_type CHECK (((length(media_type) >= 1) AND (length(media_type) <= 255))),
    CONSTRAINT ck_source_versions_object_iff_upload CHECK (((object_key IS NOT NULL) = (upload_id IS NOT NULL))),
    CONSTRAINT ck_source_versions_provenance CHECK ((jsonb_typeof(provenance) = 'object'::text)),
    CONSTRAINT ck_source_versions_size_bytes CHECK ((size_bytes >= 0)),
    CONSTRAINT ck_source_versions_version_number CHECK ((version_number > 0))
);

ALTER TABLE ONLY sources.source_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE sources.source_versions OWNER TO ai_res_owner;

CREATE TABLE sources.sources (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_kind text NOT NULL,
    title text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    current_version_id uuid,
    last_version_number integer DEFAULT 0 NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    created_by uuid,
    updated_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sources_last_event_sequence CHECK ((last_event_sequence >= 0)),
    CONSTRAINT ck_sources_last_version_number CHECK ((last_version_number >= 0)),
    CONSTRAINT ck_sources_pointer_needs_version CHECK (((current_version_id IS NULL) OR (last_version_number > 0))),
    CONSTRAINT ck_sources_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_sources_source_kind CHECK ((source_kind = ANY (ARRAY['FILE'::text, 'OPENAPI_IMPORT'::text, 'GIT_REPOSITORY'::text]))),
    CONSTRAINT ck_sources_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text]))),
    CONSTRAINT ck_sources_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240)))
);

ALTER TABLE ONLY sources.sources FORCE ROW LEVEL SECURITY;

ALTER TABLE sources.sources OWNER TO ai_res_owner;

CREATE TABLE sources.uploads (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    object_key text NOT NULL,
    declared_media_type text NOT NULL,
    declared_size_bytes bigint NOT NULL,
    declared_sha256 bytea NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    actual_size_bytes bigint,
    verified_sha256 bytea,
    finalized_at timestamp with time zone,
    rejection_code text,
    created_by uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_uploads_declared_media_type CHECK (((length(declared_media_type) >= 1) AND (length(declared_media_type) <= 255))),
    CONSTRAINT ck_uploads_declared_sha256 CHECK ((octet_length(declared_sha256) = 32)),
    CONSTRAINT ck_uploads_declared_size_bytes CHECK ((declared_size_bytes > 0)),
    CONSTRAINT ck_uploads_object_key CHECK (((length(object_key) >= 1) AND (length(object_key) <= 1024))),
    CONSTRAINT ck_uploads_rejected_has_code CHECK (((status <> 'REJECTED'::text) OR (rejection_code IS NOT NULL))),
    CONSTRAINT ck_uploads_rejection_code CHECK ((rejection_code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_uploads_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_uploads_status CHECK ((status = ANY (ARRAY['PENDING'::text, 'UPLOADED'::text, 'VERIFIED'::text, 'REJECTED'::text, 'EXPIRED'::text]))),
    CONSTRAINT ck_uploads_verified_matches_declared CHECK (((status <> 'VERIFIED'::text) OR ((verified_sha256 = declared_sha256) AND (actual_size_bytes = declared_size_bytes) AND (finalized_at IS NOT NULL)))),
    CONSTRAINT ck_uploads_verified_sha256 CHECK ((octet_length(verified_sha256) = 32))
);

ALTER TABLE ONLY sources.uploads FORCE ROW LEVEL SECURITY;

ALTER TABLE sources.uploads OWNER TO ai_res_owner;

CREATE TABLE traceability.link_type_rules (
    link_type text NOT NULL,
    source_object_type text NOT NULL,
    target_object_type text NOT NULL
);

ALTER TABLE traceability.link_type_rules OWNER TO ai_res_owner;

CREATE TABLE traceability.link_types (
    code text NOT NULL,
    CONSTRAINT ck_link_types_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE traceability.link_types OWNER TO ai_res_owner;

CREATE TABLE traceability.object_types (
    code text NOT NULL,
    CONSTRAINT ck_object_types_code CHECK ((code ~ '^[A-Z][A-Z_]*$'::text))
);

ALTER TABLE traceability.object_types OWNER TO ai_res_owner;

CREATE TABLE traceability.traceability_links (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid,
    source_object_type text NOT NULL,
    source_object_id uuid NOT NULL,
    target_object_type text NOT NULL,
    target_object_id uuid NOT NULL,
    link_type text NOT NULL,
    status text DEFAULT 'PROPOSED'::text NOT NULL,
    origin text NOT NULL,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    rationale text,
    created_by uuid,
    confirmed_by uuid,
    confirmed_at timestamp with time zone,
    superseded_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_traceability_links_confirmed CHECK (((status <> 'CONFIRMED'::text) OR ((confirmed_by IS NOT NULL) AND (confirmed_at IS NOT NULL) AND (jsonb_array_length(evidence_refs) > 0)))),
    CONSTRAINT ck_traceability_links_evidence_refs CHECK ((jsonb_typeof(evidence_refs) = 'array'::text)),
    CONSTRAINT ck_traceability_links_not_self CHECK ((NOT ((source_object_type = target_object_type) AND (source_object_id = target_object_id)))),
    CONSTRAINT ck_traceability_links_origin CHECK ((origin = ANY (ARRAY['HUMAN'::text, 'AGENT'::text, 'IMPORT'::text, 'RULE'::text]))),
    CONSTRAINT ck_traceability_links_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_traceability_links_status CHECK ((status = ANY (ARRAY['PROPOSED'::text, 'CONFIRMED'::text, 'REJECTED'::text, 'SUPERSEDED'::text]))),
    CONSTRAINT ck_traceability_links_superseded CHECK (((status = 'SUPERSEDED'::text) = (superseded_at IS NOT NULL)))
);

ALTER TABLE ONLY traceability.traceability_links FORCE ROW LEVEL SECURITY;

ALTER TABLE traceability.traceability_links OWNER TO ai_res_owner;

CREATE TABLE work.epic_events (
    event_id uuid NOT NULL,
    epic_id uuid NOT NULL,
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
    CONSTRAINT ck_epic_events_actor_type CHECK ((actor_type = ANY (ARRAY['SYSTEM'::text, 'USER'::text, 'MANAGER'::text, 'WORKER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_epic_events_aggregate_sequence CHECK ((aggregate_sequence > 0)),
    CONSTRAINT ck_epic_events_aggregate_version CHECK ((aggregate_version > 0)),
    CONSTRAINT ck_epic_events_schema_version CHECK ((schema_version > 0))
);

ALTER TABLE ONLY work.epic_events FORCE ROW LEVEL SECURITY;

ALTER TABLE work.epic_events OWNER TO ai_res_owner;

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
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_epics_last_event_sequence CHECK ((last_event_sequence >= 0)),
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

CREATE TABLE work.task_requirements (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    requirement_version_id uuid,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY work.task_requirements FORCE ROW LEVEL SECURITY;

ALTER TABLE work.task_requirements OWNER TO ai_res_owner;

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

ALTER TABLE ONLY artifacts.artifact_events
    ADD CONSTRAINT pk_artifact_events PRIMARY KEY (event_id);

ALTER TABLE ONLY artifacts.artifact_types
    ADD CONSTRAINT pk_artifact_types PRIMARY KEY (code);

ALTER TABLE ONLY artifacts.artifact_version_statuses
    ADD CONSTRAINT pk_artifact_version_statuses PRIMARY KEY (code);

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT pk_artifact_versions PRIMARY KEY (id);

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT pk_artifacts PRIMARY KEY (id);

ALTER TABLE ONLY artifacts.publications
    ADD CONSTRAINT pk_publications PRIMARY KEY (id);

ALTER TABLE ONLY artifacts.validation_reports
    ADD CONSTRAINT pk_validation_reports PRIMARY KEY (id);

ALTER TABLE ONLY artifacts.artifact_events
    ADD CONSTRAINT uq_artifact_events_artifact_id_aggregate_sequence UNIQUE (artifact_id, aggregate_sequence);

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT uq_artifact_versions_artifact_id_id UNIQUE (artifact_id, id);

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT uq_artifact_versions_artifact_id_version_number UNIQUE (artifact_id, version_number);

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT uq_artifact_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT uq_artifacts_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY artifacts.publications
    ADD CONSTRAINT uq_publications_artifact_version_id_channel UNIQUE (artifact_version_id, channel);

ALTER TABLE ONLY audit.aggregate_types
    ADD CONSTRAINT pk_aggregate_types PRIMARY KEY (code);

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);

ALTER TABLE ONLY audit.inbox_checkpoints
    ADD CONSTRAINT pk_inbox_checkpoints PRIMARY KEY (consumer_name, aggregate_type, aggregate_id);

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

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT pk_context_package_items PRIMARY KEY (id);

ALTER TABLE ONLY context.context_package_versions
    ADD CONSTRAINT pk_context_package_versions PRIMARY KEY (id);

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT pk_context_packages PRIMARY KEY (id);

ALTER TABLE ONLY context.context_package_versions
    ADD CONSTRAINT uq_context_package_versions_context_package_id_id UNIQUE (context_package_id, id);

ALTER TABLE ONLY context.context_package_versions
    ADD CONSTRAINT uq_context_package_versions_context_package_id_version_number UNIQUE (context_package_id, version_number);

ALTER TABLE ONLY context.context_package_versions
    ADD CONSTRAINT uq_context_package_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT uq_context_packages_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT pk_assumptions PRIMARY KEY (id);

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT pk_conflicts PRIMARY KEY (id);

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT pk_decisions PRIMARY KEY (id);

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT pk_hypotheses PRIMARY KEY (id);

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT pk_issues PRIMARY KEY (id);

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT pk_risks PRIMARY KEY (id);

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT pk_unknowns PRIMARY KEY (id);

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT uq_assumptions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT uq_conflicts_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT uq_decisions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT uq_hypotheses_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT uq_issues_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT uq_risks_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT uq_unknowns_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

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

ALTER TABLE ONLY governance.approvals
    ADD CONSTRAINT pk_approvals PRIMARY KEY (id);

ALTER TABLE ONLY governance.baseline_events
    ADD CONSTRAINT pk_baseline_events PRIMARY KEY (event_id);

ALTER TABLE ONLY governance.baseline_items
    ADD CONSTRAINT pk_baseline_items PRIMARY KEY (id);

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT pk_baselines PRIMARY KEY (id);

ALTER TABLE ONLY governance.change_request_events
    ADD CONSTRAINT pk_change_request_events PRIMARY KEY (event_id);

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT pk_change_requests PRIMARY KEY (id);

ALTER TABLE ONLY governance.reviews
    ADD CONSTRAINT pk_reviews PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT pk_rule_versions PRIMARY KEY (id);

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT pk_rules PRIMARY KEY (id);

ALTER TABLE ONLY governance.baseline_events
    ADD CONSTRAINT uq_baseline_events_baseline_id_aggregate_sequence UNIQUE (baseline_id, aggregate_sequence);

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT uq_baselines_organization_id_project_id_baseline_number UNIQUE (organization_id, project_id, baseline_number);

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT uq_baselines_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY governance.change_request_events
    ADD CONSTRAINT uq_change_request_events_change_request_id_aggregate_sequence UNIQUE (change_request_id, aggregate_sequence);

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT uq_change_requests_organization_id_project_id_display_number UNIQUE (organization_id, project_id, display_number);

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT uq_change_requests_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT uq_rule_versions_rule_id_version_number UNIQUE (rule_id, version_number);

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT uq_rules_id_level UNIQUE (id, level);

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT uq_rules_id_organization_id UNIQUE (id, organization_id);

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT uq_rules_id_project_id UNIQUE (id, project_id);

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

ALTER TABLE ONLY knowledge.extraction_records
    ADD CONSTRAINT pk_extraction_records PRIMARY KEY (id);

ALTER TABLE ONLY knowledge.extraction_records
    ADD CONSTRAINT uq_extraction_records_run UNIQUE (source_version_id, pipeline_name, pipeline_version, parser_version, attempt);

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

ALTER TABLE ONLY platform.bootstrap_state
    ADD CONSTRAINT pk_bootstrap_state PRIMARY KEY (singleton);

ALTER TABLE ONLY platform.display_number_counters
    ADD CONSTRAINT pk_display_number_counters PRIMARY KEY (organization_id, project_id, counter_kind);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT pk_idempotency_records PRIMARY KEY (id);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT uq_idempotency_records_organization_id_scope_type_scope_id_key_ UNIQUE (organization_id, scope_type, scope_id, key_digest);

ALTER TABLE ONLY project.project_events
    ADD CONSTRAINT pk_project_events PRIMARY KEY (event_id);

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT pk_project_memberships PRIMARY KEY (id);

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT pk_projects PRIMARY KEY (id);

ALTER TABLE ONLY project.project_events
    ADD CONSTRAINT uq_project_events_project_id_aggregate_sequence UNIQUE (project_id, aggregate_sequence);

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT uq_project_memberships_project_id_user_id UNIQUE (project_id, user_id);

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT uq_projects_organization_id_id UNIQUE (organization_id, id);

ALTER TABLE ONLY requirements.requirement_epics
    ADD CONSTRAINT pk_requirement_epics PRIMARY KEY (requirement_id, epic_id);

ALTER TABLE ONLY requirements.requirement_events
    ADD CONSTRAINT pk_requirement_events PRIMARY KEY (event_id);

ALTER TABLE ONLY requirements.requirement_types
    ADD CONSTRAINT pk_requirement_types PRIMARY KEY (code);

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT pk_requirement_versions PRIMARY KEY (id);

ALTER TABLE ONLY requirements.requirements
    ADD CONSTRAINT pk_requirements PRIMARY KEY (id);

ALTER TABLE ONLY requirements.requirement_events
    ADD CONSTRAINT uq_requirement_events_requirement_id_aggregate_sequence UNIQUE (requirement_id, aggregate_sequence);

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT uq_requirement_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT uq_requirement_versions_requirement_id_id UNIQUE (requirement_id, id);

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT uq_requirement_versions_requirement_id_version_number UNIQUE (requirement_id, version_number);

ALTER TABLE ONLY requirements.requirements
    ADD CONSTRAINT uq_requirements_organization_id_project_id_display_number UNIQUE (organization_id, project_id, display_number);

ALTER TABLE ONLY requirements.requirements
    ADD CONSTRAINT uq_requirements_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY sources.source_events
    ADD CONSTRAINT pk_source_events PRIMARY KEY (event_id);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT pk_source_versions PRIMARY KEY (id);

ALTER TABLE ONLY sources.sources
    ADD CONSTRAINT pk_sources PRIMARY KEY (id);

ALTER TABLE ONLY sources.uploads
    ADD CONSTRAINT pk_uploads PRIMARY KEY (id);

ALTER TABLE ONLY sources.source_events
    ADD CONSTRAINT uq_source_events_source_id_aggregate_sequence UNIQUE (source_id, aggregate_sequence);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT uq_source_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT uq_source_versions_source_id_checksum_sha256 UNIQUE (source_id, checksum_sha256);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT uq_source_versions_source_id_id UNIQUE (source_id, id);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT uq_source_versions_source_id_version_number UNIQUE (source_id, version_number);

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT uq_source_versions_upload_id UNIQUE (upload_id);

ALTER TABLE ONLY sources.sources
    ADD CONSTRAINT uq_sources_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY sources.uploads
    ADD CONSTRAINT uq_uploads_object_key UNIQUE (object_key);

ALTER TABLE ONLY sources.uploads
    ADD CONSTRAINT uq_uploads_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY traceability.link_type_rules
    ADD CONSTRAINT pk_link_type_rules PRIMARY KEY (link_type, source_object_type, target_object_type);

ALTER TABLE ONLY traceability.link_types
    ADD CONSTRAINT pk_link_types PRIMARY KEY (code);

ALTER TABLE ONLY traceability.object_types
    ADD CONSTRAINT pk_object_types PRIMARY KEY (code);

ALTER TABLE ONLY traceability.traceability_links
    ADD CONSTRAINT pk_traceability_links PRIMARY KEY (id);

ALTER TABLE ONLY work.epic_events
    ADD CONSTRAINT pk_epic_events PRIMARY KEY (event_id);

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT pk_epics PRIMARY KEY (id);

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT pk_task_dependencies PRIMARY KEY (id);

ALTER TABLE ONLY work.task_requirements
    ADD CONSTRAINT pk_task_requirements PRIMARY KEY (task_id, requirement_id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT pk_tasks PRIMARY KEY (id);

ALTER TABLE ONLY work.epic_events
    ADD CONSTRAINT uq_epic_events_epic_id_aggregate_sequence UNIQUE (epic_id, aggregate_sequence);

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

CREATE INDEX ix_artifact_events_artifact_id_occurred_at ON artifacts.artifact_events USING btree (artifact_id, occurred_at DESC);

CREATE INDEX ix_artifacts_epic_id ON artifacts.artifacts USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_artifacts_owner_user_id ON artifacts.artifacts USING btree (owner_user_id);

CREATE INDEX ix_publications_published_by ON artifacts.publications USING btree (published_by);

CREATE INDEX ix_validation_reports_artifact_version_id ON artifacts.validation_reports USING btree (artifact_version_id);

CREATE INDEX ix_audit_events_actor_id ON audit.audit_events USING btree (actor_id) WHERE (actor_id IS NOT NULL);

CREATE INDEX ix_audit_events_object ON audit.audit_events USING btree (object_type, object_id);

CREATE INDEX ix_audit_events_organization_id_occurred_at ON audit.audit_events USING btree (organization_id, occurred_at DESC);

CREATE INDEX ix_inbox_messages_consumer_name_status_received_at ON audit.inbox_messages USING btree (consumer_name, status, received_at);

CREATE INDEX ix_outbox_events_claim_lease ON audit.outbox_events USING btree (lease_until) WHERE (status = 'IN_FLIGHT'::text);

CREATE INDEX ix_outbox_events_claim_pending ON audit.outbox_events USING btree (created_at, aggregate_sequence) WHERE (status = 'PENDING'::text);

CREATE INDEX ix_outbox_events_pending ON audit.outbox_events USING btree (available_at, created_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text]));

CREATE INDEX ix_outbox_events_quarantined ON audit.outbox_events USING btree (created_at) WHERE (status = 'QUARANTINED'::text);

CREATE INDEX ix_context_package_items_artifact_version_id ON context.context_package_items USING btree (artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE INDEX ix_context_package_items_context_package_version_id ON context.context_package_items USING btree (context_package_version_id);

CREATE INDEX ix_context_package_items_requirement_version_id ON context.context_package_items USING btree (requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE INDEX ix_context_package_items_rule_version_id ON context.context_package_items USING btree (rule_version_id) WHERE (rule_version_id IS NOT NULL);

CREATE INDEX ix_context_package_items_source_version_id ON context.context_package_items USING btree (source_version_id) WHERE (source_version_id IS NOT NULL);

CREATE INDEX ix_assumptions_epic_id ON decisions.assumptions USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_assumptions_project_id_status ON decisions.assumptions USING btree (project_id, status);

CREATE INDEX ix_assumptions_task_id ON decisions.assumptions USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_conflicts_epic_id ON decisions.conflicts USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_conflicts_project_id_status ON decisions.conflicts USING btree (project_id, status);

CREATE INDEX ix_conflicts_task_id ON decisions.conflicts USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_decisions_approver_user_id ON decisions.decisions USING btree (approver_user_id);

CREATE INDEX ix_decisions_epic_id ON decisions.decisions USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_decisions_owner_user_id ON decisions.decisions USING btree (owner_user_id);

CREATE INDEX ix_decisions_project_id_status ON decisions.decisions USING btree (project_id, status);

CREATE INDEX ix_decisions_task_id ON decisions.decisions USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_hypotheses_epic_id ON decisions.hypotheses USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_hypotheses_project_id_status ON decisions.hypotheses USING btree (project_id, status);

CREATE INDEX ix_hypotheses_task_id ON decisions.hypotheses USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_issues_epic_id ON decisions.issues USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_issues_project_id_status ON decisions.issues USING btree (project_id, status);

CREATE INDEX ix_issues_task_id ON decisions.issues USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_risks_epic_id ON decisions.risks USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_risks_project_id_status ON decisions.risks USING btree (project_id, status);

CREATE INDEX ix_risks_task_id ON decisions.risks USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_unknowns_epic_id ON decisions.unknowns USING btree (epic_id) WHERE (epic_id IS NOT NULL);

CREATE INDEX ix_unknowns_project_id_status ON decisions.unknowns USING btree (project_id, status);

CREATE INDEX ix_unknowns_task_id ON decisions.unknowns USING btree (task_id) WHERE (task_id IS NOT NULL);

CREATE INDEX ix_readiness_evaluations_worker_run_id_created_at ON execution.readiness_evaluations USING btree (worker_run_id, created_at DESC);

CREATE INDEX ix_approvals_approver_user_id ON governance.approvals USING btree (approver_user_id);

CREATE INDEX ix_approvals_artifact_version_id ON governance.approvals USING btree (artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE INDEX ix_approvals_baseline_id ON governance.approvals USING btree (baseline_id) WHERE (baseline_id IS NOT NULL);

CREATE INDEX ix_approvals_requirement_version_id ON governance.approvals USING btree (requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE INDEX ix_baseline_events_baseline_id_occurred_at ON governance.baseline_events USING btree (baseline_id, occurred_at DESC);

CREATE INDEX ix_baseline_items_artifact_version_id ON governance.baseline_items USING btree (artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE INDEX ix_baseline_items_baseline_id ON governance.baseline_items USING btree (baseline_id);

CREATE INDEX ix_baseline_items_requirement_version_id ON governance.baseline_items USING btree (requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE INDEX ix_baselines_change_request_id ON governance.baselines USING btree (change_request_id);

CREATE INDEX ix_baselines_previous_baseline_id ON governance.baselines USING btree (previous_baseline_id);

CREATE INDEX ix_change_request_events_change_request_id_occurred_at ON governance.change_request_events USING btree (change_request_id, occurred_at DESC);

CREATE INDEX ix_change_requests_base_baseline_id ON governance.change_requests USING btree (base_baseline_id);

CREATE INDEX ix_change_requests_requested_by ON governance.change_requests USING btree (requested_by);

CREATE INDEX ix_reviews_artifact_version_id ON governance.reviews USING btree (artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE INDEX ix_reviews_requirement_version_id ON governance.reviews USING btree (requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE INDEX ix_rule_versions_approver_user_id ON governance.rule_versions USING btree (approver_user_id);

CREATE UNIQUE INDEX uq_baseline_items_artifact ON governance.baseline_items USING btree (baseline_id, artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE UNIQUE INDEX uq_baseline_items_requirement ON governance.baseline_items USING btree (baseline_id, requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE UNIQUE INDEX uq_rule_versions_one_approved ON governance.rule_versions USING btree (rule_id) WHERE (status = 'APPROVED'::text);

CREATE UNIQUE INDEX uq_rules_scope_rule_key ON governance.rules USING btree (level, COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), rule_key);

CREATE INDEX ix_sessions_user_id_active ON iam.sessions USING btree (user_id) WHERE (revoked_at IS NULL);

CREATE UNIQUE INDEX ux_mfa_factors_active_per_user ON iam.mfa_factors USING btree (user_id, factor_type) WHERE (status <> 'REVOKED'::text);

CREATE INDEX ix_extraction_records_operation_id ON knowledge.extraction_records USING btree (operation_id) WHERE (operation_id IS NOT NULL);

CREATE INDEX ix_extraction_records_source_version_id ON knowledge.extraction_records USING btree (source_version_id);

CREATE INDEX ix_operation_events_operation_id_occurred_at ON operations.operation_events USING btree (operation_id, occurred_at DESC);

CREATE INDEX ix_operations_active_status ON operations.operations USING btree (status, updated_at) WHERE (status <> ALL (ARRAY['SUCCEEDED'::text, 'PARTIALLY_SUCCEEDED'::text, 'FAILED'::text, 'CANCELLED'::text]));

CREATE INDEX ix_operations_parent_operation_id ON operations.operations USING btree (parent_operation_id) WHERE (parent_operation_id IS NOT NULL);

CREATE INDEX ix_operations_project_id_created_at ON operations.operations USING btree (project_id, created_at DESC);

CREATE INDEX ix_bootstrap_state_organization_id ON platform.bootstrap_state USING btree (organization_id);

CREATE INDEX ix_idempotency_records_expires_at ON platform.idempotency_records USING btree (expires_at);

CREATE INDEX ix_project_events_project_id_occurred_at ON project.project_events USING btree (project_id, occurred_at DESC);

CREATE INDEX ix_requirement_epics_epic_id ON requirements.requirement_epics USING btree (epic_id);

CREATE INDEX ix_requirement_events_requirement_id_occurred_at ON requirements.requirement_events USING btree (requirement_id, occurred_at DESC);

CREATE INDEX ix_requirement_versions_confirmed_by ON requirements.requirement_versions USING btree (confirmed_by);

CREATE INDEX ix_source_events_source_id_occurred_at ON sources.source_events USING btree (source_id, occurred_at DESC);

CREATE INDEX ix_uploads_pending_expires_at ON sources.uploads USING btree (expires_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'UPLOADED'::text]));

CREATE INDEX ix_uploads_source_id ON sources.uploads USING btree (source_id);

CREATE INDEX ix_traceability_links_confirmed_by ON traceability.traceability_links USING btree (confirmed_by);

CREATE INDEX ix_traceability_links_link_type_status ON traceability.traceability_links USING btree (link_type, status);

CREATE INDEX ix_traceability_links_source ON traceability.traceability_links USING btree (source_object_type, source_object_id);

CREATE INDEX ix_traceability_links_target ON traceability.traceability_links USING btree (target_object_type, target_object_id);

CREATE UNIQUE INDEX uq_traceability_links_live ON traceability.traceability_links USING btree (project_id, source_object_type, source_object_id, target_object_type, target_object_id, link_type) WHERE (status = ANY (ARRAY['PROPOSED'::text, 'CONFIRMED'::text]));

CREATE INDEX ix_epic_events_epic_id_occurred_at ON work.epic_events USING btree (epic_id, occurred_at DESC);

CREATE INDEX ix_task_dependencies_depends_on_task_id ON work.task_dependencies USING btree (depends_on_task_id);

CREATE INDEX ix_task_requirements_requirement_id ON work.task_requirements USING btree (requirement_id);

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

CREATE TRIGGER trg_artifact_events_append_only BEFORE DELETE OR UPDATE ON artifacts.artifact_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_artifact_events_no_truncate BEFORE TRUNCATE ON artifacts.artifact_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_artifact_events_sequence AFTER INSERT ON artifacts.artifact_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('artifact_id', 'artifacts.artifacts', 'artifacts.artifact_events', 'artifact_id');

CREATE TRIGGER trg_artifact_versions_facts BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_version_facts('ARTIFACT');

CREATE TRIGGER trg_artifact_versions_immutable_columns BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'artifact_id', 'version_number', 'schema_version', 'content_ref', 'content_checksum', 'provenance', 'change_reason', 'author_type', 'author_id', 'created_at');

CREATE TRIGGER trg_artifact_versions_initial_state BEFORE INSERT ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'DRAFT');

CREATE TRIGGER trg_artifact_versions_no_delete BEFORE DELETE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_artifact_versions_no_truncate BEFORE TRUNCATE ON artifacts.artifact_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_artifact_versions_status BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'DRAFT>GENERATING', 'GENERATING>DRAFT', 'DRAFT>VALIDATION_FAILED', 'GENERATING>VALIDATION_FAILED', 'VALIDATION_FAILED>DRAFT', 'DRAFT>READY_FOR_REVIEW', 'GENERATING>READY_FOR_REVIEW', 'READY_FOR_REVIEW>IN_REVIEW', 'READY_FOR_REVIEW>APPROVED', 'IN_REVIEW>CHANGES_REQUESTED', 'IN_REVIEW>APPROVED', 'IN_REVIEW>REJECTED', 'CHANGES_REQUESTED>DRAFT', 'APPROVED>PUBLISHED', 'APPROVED>SUPERSEDED', 'PUBLISHED>SUPERSEDED', 'DRAFT>ARCHIVED', 'REJECTED>ARCHIVED', 'SUPERSEDED>ARCHIVED');

CREATE CONSTRAINT TRIGGER trg_artifact_versions_version_number AFTER INSERT ON artifacts.artifact_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('artifact_id', 'artifacts.artifacts', 'artifacts.artifact_versions', 'artifact_id');

CREATE TRIGGER trg_artifacts_immutable_columns BEFORE UPDATE ON artifacts.artifacts FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'artifact_type', 'source_of_truth_mode', 'created_at', 'created_by');

CREATE CONSTRAINT TRIGGER trg_artifacts_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON artifacts.artifacts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'artifacts.artifacts', 'artifacts.artifact_events', 'artifact_id');

CREATE TRIGGER trg_artifacts_touch BEFORE UPDATE ON artifacts.artifacts FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE CONSTRAINT TRIGGER trg_artifacts_version_number AFTER INSERT OR UPDATE OF last_version_number ON artifacts.artifacts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('id', 'artifacts.artifacts', 'artifacts.artifact_versions', 'artifact_id');

CREATE TRIGGER trg_publications_append_only BEFORE DELETE OR UPDATE ON artifacts.publications FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_publications_guard_insert BEFORE INSERT ON artifacts.publications FOR EACH ROW EXECUTE FUNCTION artifacts.guard_publication_insert();

CREATE TRIGGER trg_publications_no_truncate BEFORE TRUNCATE ON artifacts.publications FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_validation_reports_append_only BEFORE DELETE OR UPDATE ON artifacts.validation_reports FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_validation_reports_no_truncate BEFORE TRUNCATE ON artifacts.validation_reports FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_audit_events_append_only BEFORE DELETE OR UPDATE ON audit.audit_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit.audit_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_inbox_checkpoints_advance BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION audit.assert_checkpoint_advances();

CREATE TRIGGER trg_inbox_checkpoints_immutable_columns BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('consumer_name', 'aggregate_type', 'aggregate_id');

CREATE TRIGGER trg_inbox_messages_immutable_columns BEFORE UPDATE ON audit.inbox_messages FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'consumer_name', 'event_id', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'payload_hash', 'received_at');

CREATE TRIGGER trg_outbox_events_immutable_columns BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'event_id', 'destination', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'event_type', 'schema_version', 'envelope', 'created_at');

CREATE CONSTRAINT TRIGGER trg_outbox_events_matches_event AFTER INSERT ON audit.outbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit.assert_outbox_matches_event();

CREATE TRIGGER trg_outbox_events_replay_count_step BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION audit.assert_replay_count_step();

CREATE TRIGGER trg_context_package_items_append_only BEFORE DELETE OR UPDATE ON context.context_package_items FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_context_package_items_complete AFTER INSERT ON context.context_package_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('context_package_version_id');

CREATE TRIGGER trg_context_package_items_guard_insert BEFORE INSERT ON context.context_package_items FOR EACH ROW EXECUTE FUNCTION context.guard_item_insert();

CREATE TRIGGER trg_context_package_items_no_truncate BEFORE TRUNCATE ON context.context_package_items FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_context_package_versions_append_only BEFORE DELETE OR UPDATE ON context.context_package_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_context_package_versions_complete AFTER INSERT ON context.context_package_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('id');

CREATE TRIGGER trg_context_package_versions_no_truncate BEFORE TRUNCATE ON context.context_package_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_context_package_versions_version_number AFTER INSERT ON context.context_package_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('context_package_id', 'context.context_packages', 'context.context_package_versions', 'context_package_id');

CREATE TRIGGER trg_context_packages_immutable_columns BEFORE UPDATE ON context.context_packages FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'epic_id', 'task_id', 'created_at', 'created_by');

CREATE TRIGGER trg_context_packages_touch BEFORE UPDATE ON context.context_packages FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE CONSTRAINT TRIGGER trg_context_packages_version_number AFTER INSERT OR UPDATE OF last_version_number ON context.context_packages DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('id', 'context.context_packages', 'context.context_package_versions', 'context_package_id');

CREATE TRIGGER trg_assumptions_immutable_columns BEFORE UPDATE ON decisions.assumptions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_assumptions_touch BEFORE UPDATE ON decisions.assumptions FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_conflicts_immutable_columns BEFORE UPDATE ON decisions.conflicts FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_conflicts_touch BEFORE UPDATE ON decisions.conflicts FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_decisions_immutable_columns BEFORE UPDATE ON decisions.decisions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_decisions_touch BEFORE UPDATE ON decisions.decisions FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_hypotheses_immutable_columns BEFORE UPDATE ON decisions.hypotheses FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_hypotheses_touch BEFORE UPDATE ON decisions.hypotheses FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_issues_immutable_columns BEFORE UPDATE ON decisions.issues FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_issues_touch BEFORE UPDATE ON decisions.issues FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_risks_immutable_columns BEFORE UPDATE ON decisions.risks FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_risks_touch BEFORE UPDATE ON decisions.risks FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_unknowns_immutable_columns BEFORE UPDATE ON decisions.unknowns FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at', 'created_by');

CREATE TRIGGER trg_unknowns_touch BEFORE UPDATE ON decisions.unknowns FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_readiness_check_results_append_only BEFORE DELETE OR UPDATE ON execution.readiness_check_results FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_check_results_no_truncate BEFORE TRUNCATE ON execution.readiness_check_results FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_check_results_same_transaction BEFORE INSERT ON execution.readiness_check_results FOR EACH ROW EXECUTE FUNCTION execution.guard_check_result_insert();

CREATE TRIGGER trg_readiness_evaluations_append_only BEFORE DELETE OR UPDATE ON execution.readiness_evaluations FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_readiness_evaluations_lock_run BEFORE INSERT ON execution.readiness_evaluations FOR EACH ROW EXECUTE FUNCTION execution.lock_run_for_evaluation();

CREATE TRIGGER trg_readiness_evaluations_no_truncate BEFORE TRUNCATE ON execution.readiness_evaluations FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_approvals_append_only BEFORE DELETE OR UPDATE ON governance.approvals FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_approvals_guard_insert BEFORE INSERT ON governance.approvals FOR EACH ROW EXECUTE FUNCTION governance.guard_approval_insert();

CREATE TRIGGER trg_approvals_no_truncate BEFORE TRUNCATE ON governance.approvals FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_baseline_events_append_only BEFORE DELETE OR UPDATE ON governance.baseline_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_baseline_events_no_truncate BEFORE TRUNCATE ON governance.baseline_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_baseline_events_sequence AFTER INSERT ON governance.baseline_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('baseline_id', 'governance.baselines', 'governance.baseline_events', 'baseline_id');

CREATE TRIGGER trg_baseline_items_append_only BEFORE DELETE OR UPDATE ON governance.baseline_items FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_baseline_items_complete AFTER INSERT ON governance.baseline_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_complete('baseline_id');

CREATE TRIGGER trg_baseline_items_guard_insert BEFORE INSERT ON governance.baseline_items FOR EACH ROW EXECUTE FUNCTION governance.guard_baseline_item_insert();

CREATE TRIGGER trg_baseline_items_no_truncate BEFORE TRUNCATE ON governance.baseline_items FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_baselines_append_only BEFORE DELETE OR UPDATE ON governance.baselines FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_baselines_approved AFTER INSERT ON governance.baselines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_approved();

CREATE CONSTRAINT TRIGGER trg_baselines_complete AFTER INSERT ON governance.baselines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_complete('id');

CREATE TRIGGER trg_baselines_guard_insert BEFORE INSERT ON governance.baselines FOR EACH ROW EXECUTE FUNCTION governance.guard_baseline_insert();

CREATE TRIGGER trg_baselines_no_truncate BEFORE TRUNCATE ON governance.baselines FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_baselines_sequence AFTER INSERT ON governance.baselines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'governance.baselines', 'governance.baseline_events', 'baseline_id');

CREATE TRIGGER trg_change_request_events_append_only BEFORE DELETE OR UPDATE ON governance.change_request_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_change_request_events_no_truncate BEFORE TRUNCATE ON governance.change_request_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_change_request_events_sequence AFTER INSERT ON governance.change_request_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('change_request_id', 'governance.change_requests', 'governance.change_request_events', 'change_request_id');

CREATE TRIGGER trg_change_requests_immutable_columns BEFORE UPDATE ON governance.change_requests FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'display_number', 'requested_by', 'created_at');

CREATE CONSTRAINT TRIGGER trg_change_requests_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON governance.change_requests DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'governance.change_requests', 'governance.change_request_events', 'change_request_id');

CREATE TRIGGER trg_change_requests_touch BEFORE UPDATE ON governance.change_requests FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_reviews_append_only BEFORE DELETE OR UPDATE ON governance.reviews FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_reviews_no_truncate BEFORE TRUNCATE ON governance.reviews FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_versions_approver BEFORE INSERT OR UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_approver();

CREATE TRIGGER trg_rule_versions_immutable_columns BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'rule_id', 'level', 'organization_id', 'project_id', 'version_number', 'condition', 'action', 'applicability', 'rationale', 'author_type', 'author_id', 'created_at');

CREATE TRIGGER trg_rule_versions_initial_state BEFORE INSERT ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'DRAFT', 'approver_user_id', 'approved_at', 'valid_from', 'valid_to');

CREATE TRIGGER trg_rule_versions_no_delete BEFORE DELETE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_versions_status BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'DRAFT>PROPOSED', 'DRAFT>REJECTED', 'PROPOSED>APPROVED', 'PROPOSED>REJECTED', 'APPROVED>RETIRED');

CREATE TRIGGER trg_rule_versions_write_once BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('approver_user_id', 'approved_at', 'valid_from', 'valid_to');

CREATE TRIGGER trg_rules_immutable_columns BEFORE UPDATE ON governance.rules FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'level', 'organization_id', 'project_id', 'rule_key', 'created_at', 'created_by');

CREATE TRIGGER trg_rules_touch BEFORE UPDATE ON governance.rules FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_credentials_immutable_columns BEFORE UPDATE ON iam.credentials FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id');

CREATE TRIGGER trg_credentials_touch BEFORE UPDATE ON iam.credentials FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_mfa_factors_immutable_columns BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'user_id');

CREATE TRIGGER trg_mfa_factors_revoked_terminal BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED');

CREATE TRIGGER trg_mfa_factors_step_monotonic BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_non_decreasing('last_used_step');

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

CREATE TRIGGER trg_extraction_records_freeze_finished BEFORE UPDATE ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'SUCCEEDED', 'PARTIAL', 'FAILED');

CREATE TRIGGER trg_extraction_records_immutable_columns BEFORE UPDATE ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'source_version_id', 'pipeline_name', 'pipeline_version', 'parser_version', 'attempt', 'tool_ref', 'input_version_refs', 'operation_id', 'started_at', 'created_by');

CREATE TRIGGER trg_extraction_records_initial_state BEFORE INSERT ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'STARTED', 'completed_at', 'error_code');

CREATE TRIGGER trg_extraction_records_status BEFORE UPDATE ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'STARTED>SUCCEEDED', 'STARTED>PARTIAL', 'STARTED>FAILED');

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

CREATE TRIGGER trg_bootstrap_state_append_only BEFORE DELETE OR UPDATE ON platform.bootstrap_state FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_bootstrap_state_no_truncate BEFORE TRUNCATE ON platform.bootstrap_state FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_display_number_counters_advance BEFORE UPDATE ON platform.display_number_counters FOR EACH ROW EXECUTE FUNCTION platform.advance_by_one('last_number');

CREATE TRIGGER trg_display_number_counters_immutable_columns BEFORE UPDATE ON platform.display_number_counters FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('organization_id', 'project_id', 'counter_kind');

CREATE TRIGGER trg_idempotency_records_freeze_finished BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'COMPLETED', 'REJECTED');

CREATE TRIGGER trg_idempotency_records_immutable_columns BEFORE UPDATE ON platform.idempotency_records FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'scope_type', 'scope_id', 'key_digest', 'key_id', 'request_fingerprint', 'created_at', 'expires_at');

CREATE TRIGGER trg_project_events_append_only BEFORE DELETE OR UPDATE ON project.project_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_project_events_no_truncate BEFORE TRUNCATE ON project.project_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_project_events_sequence AFTER INSERT ON project.project_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('project_id', 'project.projects', 'project.project_events', 'project_id');

CREATE TRIGGER trg_project_memberships_immutable_columns BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'user_id');

CREATE TRIGGER trg_project_memberships_revoked_terminal BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED');

CREATE TRIGGER trg_project_memberships_touch BEFORE UPDATE ON project.project_memberships FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_projects_immutable_columns BEFORE UPDATE ON project.projects FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id');

CREATE CONSTRAINT TRIGGER trg_projects_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON project.projects DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'project.projects', 'project.project_events', 'project_id');

CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON project.projects FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_requirement_events_append_only BEFORE DELETE OR UPDATE ON requirements.requirement_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_requirement_events_no_truncate BEFORE TRUNCATE ON requirements.requirement_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_requirement_events_sequence AFTER INSERT ON requirements.requirement_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('requirement_id', 'requirements.requirements', 'requirements.requirement_events', 'requirement_id');

CREATE TRIGGER trg_requirement_versions_facts BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_version_facts('REQUIREMENT');

CREATE TRIGGER trg_requirement_versions_immutable_columns BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'requirement_id', 'version_number', 'requirement_type', 'declared_type_text', 'statement', 'rationale', 'priority', 'acceptance_criteria', 'constraints_info', 'provenance_refs', 'change_reason', 'author_type', 'author_id', 'created_at');

CREATE TRIGGER trg_requirement_versions_initial_state BEFORE INSERT ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'EXTRACTED,CANDIDATE', 'confirmed_by', 'confirmed_at');

CREATE TRIGGER trg_requirement_versions_no_delete BEFORE DELETE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_requirement_versions_no_truncate BEFORE TRUNCATE ON requirements.requirement_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_requirement_versions_status BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'EXTRACTED>CANDIDATE', 'EXTRACTED>CONFIRMED', 'EXTRACTED>REJECTED', 'EXTRACTED>SUPERSEDED', 'CANDIDATE>CONFIRMED', 'CANDIDATE>REJECTED', 'CANDIDATE>SUPERSEDED', 'CONFIRMED>APPROVED', 'CONFIRMED>REJECTED', 'CONFIRMED>SUPERSEDED', 'APPROVED>IN_BASELINE', 'APPROVED>SUPERSEDED', 'IN_BASELINE>SUPERSEDED');

CREATE CONSTRAINT TRIGGER trg_requirement_versions_version_number AFTER INSERT ON requirements.requirement_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('requirement_id', 'requirements.requirements', 'requirements.requirement_versions', 'requirement_id');

CREATE TRIGGER trg_requirement_versions_write_once BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('confirmed_by', 'confirmed_at');

CREATE TRIGGER trg_requirements_immutable_columns BEFORE UPDATE ON requirements.requirements FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'display_number', 'created_at', 'created_by');

CREATE CONSTRAINT TRIGGER trg_requirements_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON requirements.requirements DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'requirements.requirements', 'requirements.requirement_events', 'requirement_id');

CREATE TRIGGER trg_requirements_touch BEFORE UPDATE ON requirements.requirements FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE CONSTRAINT TRIGGER trg_requirements_version_number AFTER INSERT OR UPDATE OF last_version_number ON requirements.requirements DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('id', 'requirements.requirements', 'requirements.requirement_versions', 'requirement_id');

CREATE TRIGGER trg_source_events_append_only BEFORE DELETE OR UPDATE ON sources.source_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_source_events_no_truncate BEFORE TRUNCATE ON sources.source_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_source_events_sequence AFTER INSERT ON sources.source_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('source_id', 'sources.sources', 'sources.source_events', 'source_id');

CREATE TRIGGER trg_source_versions_append_only BEFORE DELETE OR UPDATE ON sources.source_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_source_versions_guard_insert BEFORE INSERT ON sources.source_versions FOR EACH ROW EXECUTE FUNCTION sources.guard_source_version_insert();

CREATE TRIGGER trg_source_versions_no_truncate BEFORE TRUNCATE ON sources.source_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_source_versions_version_number AFTER INSERT ON sources.source_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('source_id', 'sources.sources', 'sources.source_versions', 'source_id');

CREATE TRIGGER trg_sources_immutable_columns BEFORE UPDATE ON sources.sources FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'source_kind', 'created_at', 'created_by');

CREATE CONSTRAINT TRIGGER trg_sources_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON sources.sources DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'sources.sources', 'sources.source_events', 'source_id');

CREATE TRIGGER trg_sources_touch BEFORE UPDATE ON sources.sources FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE CONSTRAINT TRIGGER trg_sources_version_number AFTER INSERT OR UPDATE OF last_version_number ON sources.sources DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_version_number_contiguous('id', 'sources.sources', 'sources.source_versions', 'source_id');

CREATE TRIGGER trg_uploads_freeze_finished BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'VERIFIED', 'REJECTED', 'EXPIRED');

CREATE TRIGGER trg_uploads_immutable_columns BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'source_id', 'object_key', 'declared_media_type', 'declared_size_bytes', 'declared_sha256', 'expires_at', 'created_at', 'created_by');

CREATE TRIGGER trg_uploads_initial_state BEFORE INSERT ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'PENDING', 'actual_size_bytes', 'verified_sha256', 'finalized_at', 'rejection_code');

CREATE TRIGGER trg_uploads_status BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'PENDING>UPLOADED', 'PENDING>REJECTED', 'PENDING>EXPIRED', 'UPLOADED>VERIFIED', 'UPLOADED>REJECTED', 'UPLOADED>EXPIRED');

CREATE TRIGGER trg_uploads_touch BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_uploads_write_once BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('actual_size_bytes', 'verified_sha256', 'finalized_at', 'rejection_code');

CREATE TRIGGER trg_traceability_links_endpoints BEFORE INSERT ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION traceability.assert_endpoint_exists();

CREATE TRIGGER trg_traceability_links_immutable_columns BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'epic_id', 'source_object_type', 'source_object_id', 'target_object_type', 'target_object_id', 'link_type', 'origin', 'created_by', 'created_at');

CREATE TRIGGER trg_traceability_links_initial_state BEFORE INSERT ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state('status', 'PROPOSED', 'confirmed_by', 'confirmed_at', 'superseded_at');

CREATE TRIGGER trg_traceability_links_status BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition('status', 'PROPOSED>CONFIRMED', 'PROPOSED>REJECTED', 'PROPOSED>SUPERSEDED', 'CONFIRMED>SUPERSEDED');

CREATE TRIGGER trg_traceability_links_touch BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

CREATE TRIGGER trg_traceability_links_write_once BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('confirmed_by', 'confirmed_at', 'superseded_at');

CREATE TRIGGER trg_epic_events_append_only BEFORE DELETE OR UPDATE ON work.epic_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_epic_events_no_truncate BEFORE TRUNCATE ON work.epic_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_epic_events_sequence AFTER INSERT ON work.epic_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('epic_id', 'work.epics', 'work.epic_events', 'epic_id');

CREATE TRIGGER trg_epics_immutable_columns BEFORE UPDATE ON work.epics FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'created_at');

CREATE CONSTRAINT TRIGGER trg_epics_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.epics DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'work.epics', 'work.epic_events', 'epic_id');

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

ALTER TABLE ONLY artifacts.artifact_events
    ADD CONSTRAINT fk_artifact_events_artifact_id_artifacts FOREIGN KEY (artifact_id) REFERENCES artifacts.artifacts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT fk_artifact_versions_artifact_id_artifacts FOREIGN KEY (organization_id, project_id, artifact_id) REFERENCES artifacts.artifacts(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifact_versions
    ADD CONSTRAINT fk_artifact_versions_status_artifact_version_statuses FOREIGN KEY (status) REFERENCES artifacts.artifact_version_statuses(code) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT fk_artifacts_artifact_type_artifact_types FOREIGN KEY (artifact_type) REFERENCES artifacts.artifact_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT fk_artifacts_current_version_id_artifact_versions FOREIGN KEY (id, current_version_id) REFERENCES artifacts.artifact_versions(artifact_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT fk_artifacts_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT fk_artifacts_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.artifacts
    ADD CONSTRAINT fk_artifacts_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.publications
    ADD CONSTRAINT fk_publications_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.publications
    ADD CONSTRAINT fk_publications_published_by_users FOREIGN KEY (organization_id, published_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY artifacts.validation_reports
    ADD CONSTRAINT fk_validation_reports_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.audit_events
    ADD CONSTRAINT fk_audit_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.inbox_checkpoints
    ADD CONSTRAINT fk_inbox_checkpoints_aggregate_type_aggregate_types FOREIGN KEY (aggregate_type) REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.inbox_messages
    ADD CONSTRAINT fk_inbox_messages_aggregate_type_aggregate_types FOREIGN KEY (aggregate_type) REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT fk_outbox_events_aggregate_type_aggregate_types FOREIGN KEY (aggregate_type) REFERENCES audit.aggregate_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY audit.outbox_events
    ADD CONSTRAINT fk_outbox_events_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT fk_context_package_items_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT fk_context_package_items_context_package_version_id_versions FOREIGN KEY (organization_id, project_id, context_package_version_id) REFERENCES context.context_package_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT fk_context_package_items_requirement_version_id_req_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT fk_context_package_items_rule_version_id_rule_versions FOREIGN KEY (rule_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_items
    ADD CONSTRAINT fk_context_package_items_source_version_id_source_versions FOREIGN KEY (organization_id, project_id, source_version_id) REFERENCES sources.source_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_package_versions
    ADD CONSTRAINT fk_context_package_versions_context_package_id_context_packages FOREIGN KEY (organization_id, project_id, context_package_id) REFERENCES context.context_packages(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT fk_context_packages_current_version_id_context_package_versions FOREIGN KEY (id, current_version_id) REFERENCES context.context_package_versions(context_package_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT fk_context_packages_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT fk_context_packages_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY context.context_packages
    ADD CONSTRAINT fk_context_packages_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT fk_assumptions_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT fk_assumptions_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT fk_assumptions_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.assumptions
    ADD CONSTRAINT fk_assumptions_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT fk_conflicts_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT fk_conflicts_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT fk_conflicts_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.conflicts
    ADD CONSTRAINT fk_conflicts_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT fk_decisions_approver_user_id_users FOREIGN KEY (organization_id, approver_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT fk_decisions_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT fk_decisions_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT fk_decisions_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.decisions
    ADD CONSTRAINT fk_decisions_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT fk_hypotheses_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT fk_hypotheses_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT fk_hypotheses_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.hypotheses
    ADD CONSTRAINT fk_hypotheses_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT fk_issues_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT fk_issues_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT fk_issues_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.issues
    ADD CONSTRAINT fk_issues_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT fk_risks_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT fk_risks_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT fk_risks_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.risks
    ADD CONSTRAINT fk_risks_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT fk_unknowns_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT fk_unknowns_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT fk_unknowns_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY decisions.unknowns
    ADD CONSTRAINT fk_unknowns_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY execution.readiness_check_results
    ADD CONSTRAINT fk_readiness_check_results_worker_run_id_readiness_evaluations FOREIGN KEY (worker_run_id, readiness_evaluation_id) REFERENCES execution.readiness_evaluations(worker_run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY execution.readiness_evaluations
    ADD CONSTRAINT fk_readiness_evaluations_worker_run_id_worker_runs FOREIGN KEY (worker_run_id) REFERENCES agents.worker_runs(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.approvals
    ADD CONSTRAINT fk_approvals_approver_user_id_users FOREIGN KEY (organization_id, approver_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.approvals
    ADD CONSTRAINT fk_approvals_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.approvals
    ADD CONSTRAINT fk_approvals_baseline_id_baselines FOREIGN KEY (organization_id, project_id, baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.approvals
    ADD CONSTRAINT fk_approvals_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baseline_events
    ADD CONSTRAINT fk_baseline_events_baseline_id_baselines FOREIGN KEY (baseline_id) REFERENCES governance.baselines(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baseline_items
    ADD CONSTRAINT fk_baseline_items_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baseline_items
    ADD CONSTRAINT fk_baseline_items_baseline_id_baselines FOREIGN KEY (organization_id, project_id, baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baseline_items
    ADD CONSTRAINT fk_baseline_items_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT fk_baselines_change_request_id_change_requests FOREIGN KEY (organization_id, project_id, change_request_id) REFERENCES governance.change_requests(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT fk_baselines_created_by_users FOREIGN KEY (organization_id, created_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT fk_baselines_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.baselines
    ADD CONSTRAINT fk_baselines_previous_baseline_id_baselines FOREIGN KEY (organization_id, project_id, previous_baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.change_request_events
    ADD CONSTRAINT fk_change_request_events_change_request_id_change_requests FOREIGN KEY (change_request_id) REFERENCES governance.change_requests(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT fk_change_requests_base_baseline_id_baselines FOREIGN KEY (organization_id, project_id, base_baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT fk_change_requests_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.change_requests
    ADD CONSTRAINT fk_change_requests_requested_by_users FOREIGN KEY (organization_id, requested_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.reviews
    ADD CONSTRAINT fk_reviews_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.reviews
    ADD CONSTRAINT fk_reviews_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT fk_rule_versions_approver_user_id_users FOREIGN KEY (approver_user_id) REFERENCES iam.users(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT fk_rule_versions_rule_id_level_rules FOREIGN KEY (rule_id, level) REFERENCES governance.rules(id, level) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT fk_rule_versions_rule_id_organization_id_rules FOREIGN KEY (rule_id, organization_id) REFERENCES governance.rules(id, organization_id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT fk_rule_versions_rule_id_project_id_rules FOREIGN KEY (rule_id, project_id) REFERENCES governance.rules(id, project_id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT fk_rules_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT fk_rules_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY knowledge.extraction_records
    ADD CONSTRAINT fk_extraction_records_operation_id_operations FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY knowledge.extraction_records
    ADD CONSTRAINT fk_extraction_records_source_version_id_source_versions FOREIGN KEY (organization_id, project_id, source_version_id) REFERENCES sources.source_versions(organization_id, project_id, id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY platform.bootstrap_state
    ADD CONSTRAINT fk_bootstrap_state_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.display_number_counters
    ADD CONSTRAINT fk_display_number_counters_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT fk_idempotency_records_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT fk_idempotency_records_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_events
    ADD CONSTRAINT fk_project_events_project_id_projects FOREIGN KEY (project_id) REFERENCES project.projects(id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.project_memberships
    ADD CONSTRAINT fk_project_memberships_role_code_project_level_roles FOREIGN KEY (role_code, project_level) REFERENCES iam.roles(code, project_level) ON DELETE RESTRICT;

ALTER TABLE ONLY project.projects
    ADD CONSTRAINT fk_projects_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organization.organizations(id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_epics
    ADD CONSTRAINT fk_requirement_epics_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_epics
    ADD CONSTRAINT fk_requirement_epics_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_events
    ADD CONSTRAINT fk_requirement_events_requirement_id_requirements FOREIGN KEY (requirement_id) REFERENCES requirements.requirements(id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT fk_requirement_versions_confirmed_by_users FOREIGN KEY (organization_id, confirmed_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT fk_requirement_versions_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirement_versions
    ADD CONSTRAINT fk_requirement_versions_requirement_type_requirement_types FOREIGN KEY (requirement_type) REFERENCES requirements.requirement_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY requirements.requirements
    ADD CONSTRAINT fk_requirements_current_version_id_requirement_versions FOREIGN KEY (id, current_version_id) REFERENCES requirements.requirement_versions(requirement_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY requirements.requirements
    ADD CONSTRAINT fk_requirements_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY sources.source_events
    ADD CONSTRAINT fk_source_events_source_id_sources FOREIGN KEY (source_id) REFERENCES sources.sources(id) ON DELETE RESTRICT;

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT fk_source_versions_source_id_sources FOREIGN KEY (organization_id, project_id, source_id) REFERENCES sources.sources(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY sources.source_versions
    ADD CONSTRAINT fk_source_versions_upload_id_uploads FOREIGN KEY (organization_id, project_id, upload_id) REFERENCES sources.uploads(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY sources.sources
    ADD CONSTRAINT fk_sources_current_version_id_source_versions FOREIGN KEY (id, current_version_id) REFERENCES sources.source_versions(source_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY sources.sources
    ADD CONSTRAINT fk_sources_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY sources.uploads
    ADD CONSTRAINT fk_uploads_source_id_sources FOREIGN KEY (organization_id, project_id, source_id) REFERENCES sources.sources(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.link_type_rules
    ADD CONSTRAINT fk_link_type_rules_link_type_link_types FOREIGN KEY (link_type) REFERENCES traceability.link_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.link_type_rules
    ADD CONSTRAINT fk_link_type_rules_source_object_type_object_types FOREIGN KEY (source_object_type) REFERENCES traceability.object_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.link_type_rules
    ADD CONSTRAINT fk_link_type_rules_target_object_type_object_types FOREIGN KEY (target_object_type) REFERENCES traceability.object_types(code) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.traceability_links
    ADD CONSTRAINT fk_traceability_links_confirmed_by_users FOREIGN KEY (organization_id, confirmed_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.traceability_links
    ADD CONSTRAINT fk_traceability_links_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.traceability_links
    ADD CONSTRAINT fk_traceability_links_link_type_rules FOREIGN KEY (link_type, source_object_type, target_object_type) REFERENCES traceability.link_type_rules(link_type, source_object_type, target_object_type) ON DELETE RESTRICT;

ALTER TABLE ONLY traceability.traceability_links
    ADD CONSTRAINT fk_traceability_links_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.epic_events
    ADD CONSTRAINT fk_epic_events_epic_id_epics FOREIGN KEY (epic_id) REFERENCES work.epics(id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT fk_epics_organization_id_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT fk_epics_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT fk_task_dependencies_depends_on_task_id_tasks FOREIGN KEY (organization_id, project_id, depends_on_task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT fk_task_dependencies_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_requirements
    ADD CONSTRAINT fk_task_requirements_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_requirements
    ADD CONSTRAINT fk_task_requirements_requirement_version_id_req_versions FOREIGN KEY (requirement_id, requirement_version_id) REFERENCES requirements.requirement_versions(requirement_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_requirements
    ADD CONSTRAINT fk_task_requirements_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT;

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

ALTER TABLE artifacts.artifact_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE artifacts.artifact_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE artifacts.artifacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_artifact_events_owner_migration ON artifacts.artifact_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_artifact_events_tenant_scope ON artifacts.artifact_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM artifacts.artifacts p
  WHERE ((p.id = artifact_events.artifact_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM artifacts.artifacts p
  WHERE ((p.id = artifact_events.artifact_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_artifact_versions_owner_migration ON artifacts.artifact_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_artifact_versions_tenant_scope ON artifacts.artifact_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_artifacts_owner_migration ON artifacts.artifacts TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_artifacts_tenant_scope ON artifacts.artifacts TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_publications_owner_migration ON artifacts.publications TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_publications_tenant_scope ON artifacts.publications TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_validation_reports_owner_migration ON artifacts.validation_reports TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_validation_reports_tenant_scope ON artifacts.validation_reports TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE artifacts.publications ENABLE ROW LEVEL SECURITY;

ALTER TABLE artifacts.validation_reports ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.inbox_checkpoints ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.inbox_messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit.outbox_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_audit_events_api_insert ON audit.audit_events FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_audit_events_auditor_select ON audit.audit_events FOR SELECT TO ai_res_auditor_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_audit_events_owner_migration ON audit.audit_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_inbox_checkpoints_consumer_all ON audit.inbox_checkpoints TO ai_res_consumer_group USING (true) WITH CHECK (true);

CREATE POLICY p_inbox_checkpoints_owner_migration ON audit.inbox_checkpoints TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_inbox_messages_consumer_all ON audit.inbox_messages TO ai_res_consumer_group USING (true) WITH CHECK (true);

CREATE POLICY p_inbox_messages_owner_migration ON audit.inbox_messages TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_outbox_events_api_insert ON audit.outbox_events FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_outbox_events_dispatcher_select ON audit.outbox_events FOR SELECT TO ai_res_outbox_group USING (true);

CREATE POLICY p_outbox_events_dispatcher_update ON audit.outbox_events FOR UPDATE TO ai_res_outbox_group USING (true) WITH CHECK (true);

CREATE POLICY p_outbox_events_owner_migration ON audit.outbox_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

ALTER TABLE context.context_package_items ENABLE ROW LEVEL SECURITY;

ALTER TABLE context.context_package_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE context.context_packages ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_context_package_items_owner_migration ON context.context_package_items TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_context_package_items_tenant_scope ON context.context_package_items TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_context_package_versions_owner_migration ON context.context_package_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_context_package_versions_tenant_scope ON context.context_package_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_context_packages_owner_migration ON context.context_packages TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_context_packages_tenant_scope ON context.context_packages TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE decisions.assumptions ENABLE ROW LEVEL SECURITY;

ALTER TABLE decisions.conflicts ENABLE ROW LEVEL SECURITY;

ALTER TABLE decisions.decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE decisions.hypotheses ENABLE ROW LEVEL SECURITY;

ALTER TABLE decisions.issues ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_assumptions_owner_migration ON decisions.assumptions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_assumptions_tenant_scope ON decisions.assumptions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_conflicts_owner_migration ON decisions.conflicts TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_conflicts_tenant_scope ON decisions.conflicts TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_decisions_owner_migration ON decisions.decisions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_decisions_tenant_scope ON decisions.decisions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_hypotheses_owner_migration ON decisions.hypotheses TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_hypotheses_tenant_scope ON decisions.hypotheses TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_issues_owner_migration ON decisions.issues TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_issues_tenant_scope ON decisions.issues TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_risks_owner_migration ON decisions.risks TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_risks_tenant_scope ON decisions.risks TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_unknowns_owner_migration ON decisions.unknowns TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_unknowns_tenant_scope ON decisions.unknowns TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE decisions.risks ENABLE ROW LEVEL SECURITY;

ALTER TABLE decisions.unknowns ENABLE ROW LEVEL SECURITY;

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

ALTER TABLE governance.approvals ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.baseline_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.baseline_items ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.baselines ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.change_request_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.change_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_approvals_owner_migration ON governance.approvals TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_approvals_tenant_scope ON governance.approvals TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_baseline_events_owner_migration ON governance.baseline_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_baseline_events_tenant_scope ON governance.baseline_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM governance.baselines p
  WHERE ((p.id = baseline_events.baseline_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM governance.baselines p
  WHERE ((p.id = baseline_events.baseline_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_baseline_items_owner_migration ON governance.baseline_items TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_baseline_items_tenant_scope ON governance.baseline_items TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_baselines_owner_migration ON governance.baselines TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_baselines_tenant_scope ON governance.baselines TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_change_request_events_owner_migration ON governance.change_request_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_change_request_events_tenant_scope ON governance.change_request_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM governance.change_requests p
  WHERE ((p.id = change_request_events.change_request_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM governance.change_requests p
  WHERE ((p.id = change_request_events.change_request_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_change_requests_owner_migration ON governance.change_requests TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_change_requests_tenant_scope ON governance.change_requests TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_reviews_owner_migration ON governance.reviews TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_reviews_tenant_scope ON governance.reviews TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_rule_versions_insert ON governance.rule_versions FOR INSERT TO ai_res_api_group WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_versions_owner_migration ON governance.rule_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_versions_read ON governance.rule_versions FOR SELECT TO ai_res_api_group USING (((level = 'SYSTEM'::text) OR ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rule_versions_update ON governance.rule_versions FOR UPDATE TO ai_res_api_group USING (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rules_insert ON governance.rules FOR INSERT TO ai_res_api_group WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rules_owner_migration ON governance.rules TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rules_read ON governance.rules FOR SELECT TO ai_res_api_group USING (((level = 'SYSTEM'::text) OR ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rules_update ON governance.rules FOR UPDATE TO ai_res_api_group USING (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

ALTER TABLE governance.reviews ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rules ENABLE ROW LEVEL SECURITY;

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

ALTER TABLE knowledge.extraction_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_extraction_records_owner_migration ON knowledge.extraction_records TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_extraction_records_tenant_scope ON knowledge.extraction_records TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

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

ALTER TABLE platform.bootstrap_state ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.display_number_counters ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.idempotency_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_bootstrap_state_owner_migration ON platform.bootstrap_state TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_bootstrap_state_tenant_scope ON platform.bootstrap_state TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_display_number_counters_owner_migration ON platform.display_number_counters TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_display_number_counters_tenant_scope ON platform.display_number_counters TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_idempotency_records_owner_migration ON platform.idempotency_records TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_idempotency_records_tenant_scope ON platform.idempotency_records TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_project_events_owner_migration ON project.project_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_project_events_tenant_scope ON project.project_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM project.projects p
  WHERE ((p.id = project_events.project_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM project.projects p
  WHERE ((p.id = project_events.project_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_project_memberships_owner_migration ON project.project_memberships TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_project_memberships_tenant_scope ON project.project_memberships TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_projects_owner_migration ON project.projects TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_projects_tenant_scope ON project.projects TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

ALTER TABLE project.project_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.project_memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_requirement_epics_owner_migration ON requirements.requirement_epics TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_requirement_epics_tenant_scope ON requirements.requirement_epics TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_requirement_events_owner_migration ON requirements.requirement_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_requirement_events_tenant_scope ON requirements.requirement_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM requirements.requirements p
  WHERE ((p.id = requirement_events.requirement_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM requirements.requirements p
  WHERE ((p.id = requirement_events.requirement_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_requirement_versions_owner_migration ON requirements.requirement_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_requirement_versions_tenant_scope ON requirements.requirement_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_requirements_owner_migration ON requirements.requirements TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_requirements_tenant_scope ON requirements.requirements TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE requirements.requirement_epics ENABLE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirement_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirement_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE requirements.requirements ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_source_events_owner_migration ON sources.source_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_source_events_tenant_scope ON sources.source_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM sources.sources p
  WHERE ((p.id = source_events.source_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM sources.sources p
  WHERE ((p.id = source_events.source_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_source_versions_owner_migration ON sources.source_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_source_versions_tenant_scope ON sources.source_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_sources_owner_migration ON sources.sources TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_sources_tenant_scope ON sources.sources TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_uploads_owner_migration ON sources.uploads TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_uploads_tenant_scope ON sources.uploads TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE sources.source_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE sources.source_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE sources.sources ENABLE ROW LEVEL SECURITY;

ALTER TABLE sources.uploads ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_traceability_links_owner_migration ON traceability.traceability_links TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_traceability_links_tenant_scope ON traceability.traceability_links TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE traceability.traceability_links ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.epic_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.epics ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_epic_events_owner_migration ON work.epic_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_epic_events_tenant_scope ON work.epic_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM work.epics p
  WHERE ((p.id = epic_events.epic_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM work.epics p
  WHERE ((p.id = epic_events.epic_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_epics_owner_migration ON work.epics TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_epics_tenant_scope ON work.epics TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_dependencies_owner_migration ON work.task_dependencies TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_dependencies_tenant_scope ON work.task_dependencies TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_requirements_owner_migration ON work.task_requirements TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_requirements_tenant_scope ON work.task_requirements TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_tasks_owner_migration ON work.tasks TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_tasks_tenant_scope ON work.tasks TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE work.task_dependencies ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.task_requirements ENABLE ROW LEVEL SECURITY;

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

REVOKE ALL ON FUNCTION artifacts.guard_publication_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_checkpoint_advances() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_outbox_matches_event() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_replay_count_step() FROM PUBLIC;

REVOKE ALL ON FUNCTION context.assert_package_version_complete() FROM PUBLIC;

REVOKE ALL ON FUNCTION context.guard_item_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.guard_check_result_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.lock_run_for_evaluation() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.assert_baseline_approved() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.assert_baseline_complete() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_approval_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_baseline_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_baseline_item_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_rule_approver() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_version_facts() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.advance_by_one() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.assert_event_sequence_contiguous() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.assert_version_number_contiguous() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.forbid_unset() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.freeze_when_status_in() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_status_transition() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_columns_immutable() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_non_decreasing() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_terminal_status() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.reject_modification() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.require_initial_state() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.touch_row() FROM PUBLIC;

REVOKE ALL ON FUNCTION sources.guard_source_version_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION traceability.assert_endpoint_exists() FROM PUBLIC;

REVOKE ALL ON FUNCTION work.require_open_operation() FROM PUBLIC;

GRANT SELECT,INSERT ON TABLE agents.worker_results TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE agents.worker_run_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE agents.worker_runs TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.artifact_events TO ai_res_api_group;

GRANT SELECT ON TABLE artifacts.artifact_types TO ai_res_api_group;

GRANT SELECT ON TABLE artifacts.artifact_version_statuses TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE artifacts.artifact_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE artifacts.artifacts TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.publications TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.validation_reports TO ai_res_api_group;

GRANT INSERT ON TABLE audit.audit_events TO ai_res_api_group;
GRANT SELECT ON TABLE audit.audit_events TO ai_res_auditor_group;

GRANT SELECT,INSERT ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

GRANT UPDATE(last_sequence) ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

GRANT UPDATE(updated_at) ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

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

GRANT UPDATE(replay_count) ON TABLE audit.outbox_events TO ai_res_outbox_group;

GRANT SELECT,INSERT ON TABLE context.context_package_items TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE context.context_package_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE context.context_packages TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.assumptions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.conflicts TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.decisions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.hypotheses TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.issues TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.risks TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE decisions.unknowns TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE execution.readiness_check_results TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE execution.readiness_evaluations TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.approvals TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.baseline_events TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.baseline_items TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.baselines TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.change_request_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE governance.change_requests TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.reviews TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE governance.rule_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE governance.rules TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.credentials TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.mfa_factors TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.mfa_recovery_codes TO ai_res_api_group;

GRANT SELECT ON TABLE iam.roles TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.service_identities TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.sessions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE iam.users TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE knowledge.extraction_records TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE operations.operation_events TO ai_res_api_group;

GRANT SELECT ON TABLE operations.operation_types TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE operations.operations TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.memberships TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.organizations TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE platform.bootstrap_state TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE platform.display_number_counters TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE platform.idempotency_records TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE project.project_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE project.project_memberships TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE project.projects TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE requirements.requirement_epics TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE requirements.requirement_events TO ai_res_api_group;

GRANT SELECT ON TABLE requirements.requirement_types TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE requirements.requirement_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE requirements.requirements TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE sources.source_events TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE sources.source_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE sources.sources TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE sources.uploads TO ai_res_api_group;

GRANT SELECT ON TABLE traceability.link_type_rules TO ai_res_api_group;

GRANT SELECT ON TABLE traceability.link_types TO ai_res_api_group;

GRANT SELECT ON TABLE traceability.object_types TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE traceability.traceability_links TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.epic_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE work.epics TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.task_dependencies TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.task_requirements TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE work.tasks TO ai_res_api_group;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TYPES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC;
