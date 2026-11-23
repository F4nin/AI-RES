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
-- ROLE ai_res_model_admission_operator NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
-- ROLE ai_res_outbox_dispatcher LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_outbox_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
-- ROLE ai_res_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
-- ROLE ai_res_platform_api LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_platform_api_group NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
-- GRANT ai_res_api_group TO ai_res_api INHERIT=t SET=f
-- GRANT ai_res_auditor_group TO ai_res_auditor INHERIT=t SET=f
-- GRANT ai_res_consumer_group TO ai_res_event_consumer INHERIT=t SET=f
-- GRANT ai_res_outbox_group TO ai_res_outbox_dispatcher INHERIT=t SET=f
-- GRANT ai_res_owner TO ai_res_migrator INHERIT=f SET=t
-- GRANT ai_res_platform_api_group TO ai_res_platform_api INHERIT=t SET=f
-- DATABASE ACL ai_res_api=c/ai_res_owner,ai_res_auditor=c/ai_res_owner,ai_res_event_consumer=c/ai_res_owner,ai_res_migrator=c/ai_res_owner,ai_res_outbox_dispatcher=c/ai_res_owner,ai_res_owner=CTc/ai_res_owner,ai_res_platform_api=c/ai_res_owner
-- PARAMETER ACL app.migration_mode ai_res_owner=s/postgres,postgres=sA/postgres

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

CREATE FUNCTION agents.guard_worker_definition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN  -- the nine roles are fixed (BASELINED): a definition row is neither renamed nor removed
  RAISE EXCEPTION 'worker definition % is immutable', OLD.id USING ERRCODE = 'integrity_constraint_violation';
END $$;

ALTER FUNCTION agents.guard_worker_definition() OWNER TO ai_res_owner;

CREATE FUNCTION agents.guard_worker_definition_version() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE rank_old int; rank_new int;
BEGIN  -- a version is a snapshot of a capability: it is born ACTIVE, only its status moves, and only forward; a row that a run may reference is never deleted
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'ACTIVE' THEN
      RAISE EXCEPTION 'a worker definition version is created ACTIVE (got %)', NEW.status USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'worker definition version % is never deleted (retire it instead)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.id, NEW.worker_definition_id, NEW.version, NEW.input_contract_version, NEW.output_contract_version, NEW.output_schema_id, NEW.output_schema_version,
      NEW.acceptance_schema, NEW.runtime_profile_version, NEW.created_at)
     IS DISTINCT FROM
     (OLD.id, OLD.worker_definition_id, OLD.version, OLD.input_contract_version, OLD.output_contract_version, OLD.output_schema_id, OLD.output_schema_version,
      OLD.acceptance_schema, OLD.runtime_profile_version, OLD.created_at) THEN
    RAISE EXCEPTION 'worker definition version % is immutable except for its status (publish a new version)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  rank_old := array_position(ARRAY['ACTIVE','DEPRECATED','RETIRED'], OLD.status);
  rank_new := array_position(ARRAY['ACTIVE','DEPRECATED','RETIRED'], NEW.status);
  IF rank_new < rank_old THEN
    RAISE EXCEPTION 'worker definition version % status may not go back from % to %', OLD.id, OLD.status, NEW.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION agents.guard_worker_definition_version() OWNER TO ai_res_owner;

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

CREATE FUNCTION audit.approve_assigned_start_replay(operation_ref uuid, event_ref uuid, expected_count integer, actor_ref uuid, session_ref uuid, request_ref uuid, audit_ref uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
        DECLARE
            org uuid := NULLIF(current_setting('app.organization_id',true),'')::uuid;
            prj uuid := NULLIF(current_setting('app.project_id',true),'')::uuid;
            assignment_ref uuid;
        BEGIN
            PERFORM 1 FROM organization.memberships m
            WHERE (m.organization_id,m.user_id)=(org,actor_ref) FOR SHARE;
            IF EXISTS (
                SELECT 1 FROM organization.memberships m
                WHERE (m.organization_id,m.user_id)=(org,actor_ref) AND m.status<>'ACTIVE'
            ) THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM iam.users u
            WHERE (u.organization_id,u.id)=(org,actor_ref) AND u.status='ACTIVE' FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM project.project_memberships m
                WHERE m.organization_id=org AND m.project_id=prj AND m.user_id=actor_ref
                  AND m.role_code='PROJECT_ADMIN' AND m.status='ACTIVE'
                FOR SHARE
            ) THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM iam.sessions s
            WHERE (s.organization_id,s.user_id,s.id)=(org,actor_ref,session_ref)
              AND s.revoked_at IS NULL AND s.mfa_verified_at IS NOT NULL
              AND s.idle_expires_at>clock_timestamp() AND s.absolute_expires_at>clock_timestamp() FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            SELECT a.id INTO assignment_ref FROM platform.operation_execution_assignments a
            WHERE (a.organization_id,a.project_id,a.operation_id)=(org,prj,operation_ref)
              AND a.revoked_at IS NULL FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM operations.operations o
            WHERE (o.organization_id,o.project_id,o.id)=(org,prj,operation_ref)
            FOR SHARE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            PERFORM 1 FROM audit.outbox_events e
            WHERE (e.organization_id,e.project_id,e.aggregate_id)=(org,prj,operation_ref)
              AND e.event_id=event_ref AND e.destination='orchestration.operation-start'
              AND e.status='QUARANTINED' AND e.replay_count=expected_count
            FOR UPDATE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            UPDATE audit.outbox_events e
            SET status='PENDING', available_at=now(), attempt_count=0, replay_count=e.replay_count+1
            FROM audit.inspect_assigned_start_replay(operation_ref) visible
            WHERE (e.organization_id,e.project_id,e.aggregate_id)=(org,prj,operation_ref)
              AND e.event_id=event_ref AND e.event_id=visible.event_id
              AND e.destination='orchestration.operation-start' AND e.status='QUARANTINED'
              AND e.replay_count=expected_count AND e.replay_count=visible.replay_count
              AND EXISTS (
                SELECT 1 FROM iam.sessions s WHERE s.id=session_ref
                  AND s.idle_expires_at>clock_timestamp() AND s.absolute_expires_at>clock_timestamp()
              );
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            INSERT INTO audit.audit_events(
                id,organization_id,project_id,occurred_at,actor_type,actor_id,action,object_type,object_id,result,correlation_id,details
            ) VALUES (
                audit_ref,org,prj,clock_timestamp(),'USER',actor_ref,'OPERATION_START_REPLAY_APPROVED','OPERATION',
                operation_ref,'SUCCEEDED',request_ref,
                jsonb_build_object('eventId',event_ref,'assignmentId',assignment_ref,'replayCount',expected_count+1)
            );
            RETURN true;
        END $$;

ALTER FUNCTION audit.approve_assigned_start_replay(operation_ref uuid, event_ref uuid, expected_count integer, actor_ref uuid, session_ref uuid, request_ref uuid, audit_ref uuid) OWNER TO ai_res_owner;

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

CREATE FUNCTION audit.authorize_assigned_delivery(row_ref uuid, owner_ref text, attempt integer, generation integer, namespace_ref text, request_nonce uuid, credential_expires timestamp with time zone, request_correlation uuid) RETURNS TABLE(decision text, id uuid, event_id uuid, destination text, aggregate_type text, aggregate_id uuid, aggregate_sequence bigint, event_type text, schema_version integer, envelope jsonb, attempt_count integer, replay_count integer, dispatch_namespace text, lease_until timestamp with time zone)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
        DECLARE
            leased audit.outbox_events%ROWTYPE;
            result text;
        BEGIN
            INSERT INTO platform.platform_request_nonces(issuer,nonce,expires_at)
            SELECT 'OUTBOX_DISPATCHER',request_nonce,credential_expires WHERE credential_expires>clock_timestamp()
            ON CONFLICT DO NOTHING;
            IF NOT FOUND OR credential_expires<=clock_timestamp() THEN
                result := 'EXPIRED_OR_REPLAY';
            ELSE
                SELECT e.* INTO leased FROM audit.outbox_events e
                WHERE e.id=row_ref AND e.status='IN_FLIGHT' AND e.lease_owner=owner_ref
                  AND e.attempt_count=attempt AND e.replay_count=generation AND e.dispatch_namespace=namespace_ref
                  AND e.dispatch_assignment_id IS NOT NULL AND e.lease_until>clock_timestamp()
                  AND e.destination IN ('orchestration.operation-start','orchestration.operation-cancel')
                FOR SHARE OF e;
                result := CASE
                    WHEN credential_expires<=clock_timestamp() THEN 'EXPIRED_OR_REPLAY'
                    WHEN FOUND AND leased.lease_until>clock_timestamp() THEN 'AUTHORIZED'
                    ELSE 'ASSIGNMENT_DENIED'
                END;
            END IF;
            INSERT INTO platform.platform_auth_events(id,correlation_id,reason,action)
            VALUES (gen_random_uuid(),request_correlation,result,'AUTHORIZE_ASSIGNED_DELIVERY');
            IF result <> 'AUTHORIZED' THEN leased := NULL; END IF;
            RETURN QUERY SELECT result,leased.id,leased.event_id,leased.destination,leased.aggregate_type,leased.aggregate_id,
                leased.aggregate_sequence,leased.event_type,leased.schema_version,leased.envelope,leased.attempt_count,
                leased.replay_count,leased.dispatch_namespace,leased.lease_until;
        END $$;

ALTER FUNCTION audit.authorize_assigned_delivery(row_ref uuid, owner_ref text, attempt integer, generation integer, namespace_ref text, request_nonce uuid, credential_expires timestamp with time zone, request_correlation uuid) OWNER TO ai_res_owner;

CREATE FUNCTION audit.guard_assigned_start_quarantine() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
        BEGIN
            IF current_user <> 'ai_res_owner' AND OLD.status='QUARANTINED'
              AND OLD.destination='orchestration.operation-start'
              AND (OLD.envelope #> '{data,refs}') @> '[{"resourceType":"OPERATION_EXECUTION_ASSIGNMENT"}]'::jsonb
            THEN
                RAISE EXCEPTION 'assigned Start requires audited replay approval' USING ERRCODE='insufficient_privilege';
            END IF;
            RETURN NEW;
        END $$;

ALTER FUNCTION audit.guard_assigned_start_quarantine() OWNER TO ai_res_owner;

CREATE FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid) RETURNS TABLE(event_id uuid, replay_count integer)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT e.event_id,e.replay_count
            FROM audit.outbox_events e
            JOIN platform.operation_execution_assignments a
              ON (a.organization_id,a.project_id,a.operation_id,a.id,a.namespace)
                =(e.organization_id,e.project_id,e.aggregate_id,e.dispatch_assignment_id,e.dispatch_namespace)
            JOIN operations.operations o
              ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
            WHERE e.aggregate_id=operation_ref AND e.aggregate_type='OPERATION' AND e.aggregate_sequence=1
              AND e.event_type='operation.accepted' AND e.destination='orchestration.operation-start'
              AND e.status='QUARANTINED' AND a.revoked_at IS NULL
              AND (o.status='ACCEPTED' OR a.workflow_run_id IS NOT NULL)
              AND e.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
              AND e.project_id=NULLIF(current_setting('app.project_id',true),'')::uuid
        $$;

ALTER FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid) OWNER TO ai_res_owner;

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
DECLARE creator xid8;
BEGIN
  SELECT creation_transaction_id INTO creator FROM context.context_package_versions WHERE id = NEW.context_package_version_id;
  IF creator IS NULL OR creator <> pg_current_xact_id() THEN
    RAISE EXCEPTION 'context package version is sealed' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.rule_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM governance.rule_versions r WHERE r.id = NEW.rule_version_id AND r.status = 'APPROVED') THEN
    RAISE EXCEPTION 'rule version is not approved or visible' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION context.guard_item_insert() OWNER TO ai_res_owner;

CREATE FUNCTION context.stamp_creation_transaction() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.creation_transaction_id := pg_current_xact_id();
  RETURN NEW;
END $$;

ALTER FUNCTION context.stamp_creation_transaction() OWNER TO ai_res_owner;

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

CREATE FUNCTION governance.guard_rule_record_scope() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE version_ref uuid; target governance.rule_versions%ROWTYPE;
BEGIN
  version_ref := (to_jsonb(NEW) ->> CASE TG_TABLE_NAME WHEN 'rule_validation_reports' THEN 'proposal_version_id'
     WHEN 'rule_exceptions' THEN 'target_version_id' ELSE 'rule_version_id' END)::uuid;
  SELECT * INTO target FROM governance.rule_versions WHERE id=version_ref;
  IF target.id IS NULL OR target.organization_id IS DISTINCT FROM NEW.organization_id
     OR (target.project_id IS NOT NULL AND target.project_id IS DISTINCT FROM NEW.project_id) THEN
    RAISE EXCEPTION 'rule record is outside its target tenant scope' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF TG_TABLE_NAME='rule_runtime_controls' THEN
    IF target.level IS DISTINCT FROM NEW.level THEN
      RAISE EXCEPTION 'rule control level mismatch' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSIF TG_TABLE_NAME='rule_exceptions' THEN
    IF target.level='SYSTEM' OR NOT EXISTS (SELECT 1 FROM governance.rule_versions p WHERE p.id=NEW.permission_version_id
      AND (p.level='SYSTEM' OR (p.organization_id=NEW.organization_id AND (p.project_id IS NULL OR p.project_id=NEW.project_id)))) THEN
      RAISE EXCEPTION 'rule exception target or permission is outside its scope' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION governance.guard_rule_record_scope() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.apply_owner_identity_decision(o uuid, u uuid, sid uuid, p uuid, d uuid, reviewed jsonb, cmd_text text, expected_text text, observed_text text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $_$
DECLARE state jsonb; cmd jsonb; exp jsonb; obs jsonb; r jsonb; cmd_hash text; eh text; oh text; gen integer; act text;
BEGIN
  IF octet_length(cmd_text)>16384 OR octet_length(expected_text)>65536 OR octet_length(observed_text)>65536 THEN
    RAISE EXCEPTION 'decision too large' USING ERRCODE='check_violation';
  END IF;
  state:=platform.owner_identity_snapshot(o,u,sid,p,d);
  IF reviewed IS DISTINCT FROM state THEN RAISE EXCEPTION 'stale decision state' USING ERRCODE='check_violation'; END IF;
  cmd:=cmd_text::jsonb; exp:=expected_text::jsonb; obs:=observed_text::jsonb; r:=cmd->'review'; act:=cmd->>'action';
  cmd_hash:=encode(sha256(convert_to(cmd_text,'UTF8')),'hex');
  eh:=encode(sha256(convert_to(expected_text,'UTF8')),'hex'); oh:=encode(sha256(convert_to(observed_text,'UTF8')),'hex');
  IF (cmd->>'decisionId'=d::text AND (cmd->>'correlationId')::uuid IS NOT NULL AND act IN ('ACCEPT_IDENTITY','BLOCK')
    AND cmd->>'expectationSha256'=eh AND cmd->>'observationSha256'=oh
    AND r->>'expectation_sha256'=eh AND r->>'observation_sha256'=oh
    AND r->>'binding_sha256' ~ '^[0-9a-f]{64}$' AND r->>'profile_sha256' ~ '^[0-9a-f]{64}$'
    AND r->>'policy_version' ~ '^[A-Za-z0-9_.:-]{1,128}$'
    AND exp->>'schemaVersion'='0.2' AND obs->>'schemaVersion'='0.2' AND exp->>'kind'='EXPECTATION' AND obs->>'kind'='OBSERVATION'
    AND exp->>'evidenceSha256'=oh AND exp->'identity'=obs->'identity' AND exp->'managedVersions'=obs->'managedVersions'
    AND exp->'managedVersions'->>'profileId'=p::text
    AND (exp->'managedVersions'->>'profileVersion')::integer=((state->>'profile')::jsonb->>'profile_version')::integer) IS NOT TRUE THEN
    RAISE EXCEPTION 'invalid decision' USING ERRCODE='check_violation';
  END IF;
  IF state->'receipt'<>'null'::jsonb THEN
    IF state->'receipt'->>'command_sha256'<>cmd_hash THEN RAISE EXCEPTION 'decision reused' USING ERRCODE='check_violation'; END IF;
    RETURN state->'receipt';
  END IF;
  gen:=(state->>'generation')::integer;
  IF (exp->>'admissionGeneration')::integer IS DISTINCT FROM gen+1 THEN RAISE EXCEPTION 'stale generation' USING ERRCODE='check_violation'; END IF;
  IF act='ACCEPT_IDENTITY' THEN
    IF state->'pending'<>'[]'::jsonb THEN RAISE EXCEPTION 'unresolved calls' USING ERRCODE='check_violation'; END IF;
    gen:=gen+1;
    INSERT INTO platform.model_admission_versions(profile_id,generation,profile_version,expectation,expectation_sha256)
      VALUES(p,gen,(exp->'managedVersions'->>'profileVersion')::integer,exp,decode(eh,'hex'));
    INSERT INTO platform.model_admission_controls(profile_id,current_generation) VALUES(p,gen)
      ON CONFLICT(profile_id) DO UPDATE SET current_generation=EXCLUDED.current_generation,blocked=false;
  ELSE
    IF gen=0 THEN RAISE EXCEPTION 'no admission to block' USING ERRCODE='check_violation'; END IF;
    UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=p;
  END IF;
  INSERT INTO platform.model_admission_decisions(decision_id,profile_id,organization_id,user_id,session_id,action,generation,
    command_sha256,review_sha256,profile_sha256,expectation_sha256,observation_sha256,policy_version,reason_code,correlation_id)
    VALUES(d,p,o,u,sid,act,gen,cmd_hash,r->>'binding_sha256',r->>'profile_sha256',eh,oh,r->>'policy_version',
      CASE WHEN act='ACCEPT_IDENTITY' THEN 'HUMAN_IDENTITY_ACCEPTED' ELSE 'HUMAN_BLOCKED' END,(cmd->>'correlationId')::uuid);
  RETURN jsonb_build_object('generation',gen,'action',act,'command_sha256',cmd_hash);
END $_$;

ALTER FUNCTION platform.apply_owner_identity_decision(o uuid, u uuid, sid uuid, p uuid, d uuid, reviewed jsonb, cmd_text text, expected_text text, observed_text text) OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.bound_workflow_task_command_binding(oid uuid, rid uuid, ns text, q text, digest bytea) RETURNS TABLE(assignment_id uuid, workflow_type text, workflow_contract_version integer, input_digest bytea, operation_status text)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT c.assignment_id,c.workflow_type,c.workflow_contract_version,a.input_digest,o.status::text
            FROM platform.bound_workflow_task_context(oid,rid,ns,q,digest) c
            JOIN platform.operation_execution_assignments a ON a.id=c.assignment_id
            JOIN operations.operations o ON o.id=a.operation_id AND o.organization_id=a.organization_id AND o.project_id=a.project_id
        $$;

ALTER FUNCTION platform.bound_workflow_task_command_binding(oid uuid, rid uuid, ns text, q text, digest bytea) OWNER TO ai_res_owner;

CREATE FUNCTION platform.bound_workflow_task_context(oid uuid, rid uuid, ns text, q text, digest bytea) RETURNS TABLE(assignment_id uuid, workflow_type text, workflow_contract_version integer)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT a.id,a.workflow_type,a.workflow_contract_version
            FROM platform.operation_execution_assignments a
            JOIN platform.task_issuance_receipts r ON r.operation_id=a.operation_id AND r.workflow_run_id=a.workflow_run_id
            WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.task_queue=q AND a.revoked_at IS NULL
              AND r.token_digest=digest AND r.principal='MANAGER_RUNTIME' AND r.namespace=ns AND r.queue=q AND r.task_kind='WORKFLOW'
              AND a.task_queue='ai-res-manager' AND a.workflow_type IN ('ManagerIntakeWorkflow','PlanExecutionWorkflow')
            FOR SHARE OF a
        $$;

ALTER FUNCTION platform.bound_workflow_task_context(oid uuid, rid uuid, ns text, q text, digest bytea) OWNER TO ai_res_owner;

CREATE FUNCTION platform.capture_manager_epic_context(oid uuid, aid uuid, rid uuid) RETURNS TABLE(context_id uuid, epic_state jsonb)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
        DECLARE
            binding record;
            intake record;
        BEGIN
            SELECT * INTO binding FROM platform.lock_manager_epic_context_assignment(oid,'manager.read_input');
            IF NOT FOUND OR binding.assignment_id IS DISTINCT FROM aid OR binding.workflow_run_id IS DISTINCT FROM rid
            THEN RETURN; END IF;

            SELECT i.id AS interaction_id,i.epic_id,o.row_version INTO intake
            FROM operations.operations o
            JOIN work.manager_interactions i ON (i.organization_id,i.project_id,i.operation_id)=(o.organization_id,o.project_id,o.id)
            WHERE (o.organization_id,o.project_id,o.id)=(binding.organization_id,binding.project_id,oid)
              AND o.operation_type='MANAGER_MESSAGE' AND o.status='RUNNING'
            FOR NO KEY UPDATE OF o;
            IF NOT FOUND THEN RETURN; END IF;

            IF NOT EXISTS (SELECT 1 FROM platform.manager_epic_context_versions c WHERE c.operation_id=oid) THEN
                INSERT INTO platform.manager_epic_context_versions
                    (id,organization_id,project_id,interaction_id,operation_id,assignment_id,workflow_run_id,epic_state)
                SELECT gen_random_uuid(),e.organization_id,e.project_id,intake.interaction_id,oid,aid,rid,
                       jsonb_build_object('epicVersion',e.row_version,'epicStatus',e.status,
                           'operationVersion',intake.row_version,'operationStatus','RUNNING',
                           'questionSequence',COALESCE(q.sequence,0),'hasOpenQuestion',COALESCE(q.is_open,false),
                           'planVersion',p.version_number,'planDecision',p.decision,'taskCounts',COALESCE(t.counts,'{}'::jsonb))
                FROM work.epics e
                LEFT JOIN LATERAL (
                    SELECT j.sequence,j.event_kind='PROPOSED' AS is_open FROM work.manager_question_journal j
                    WHERE (j.organization_id,j.project_id,j.epic_id)=(e.organization_id,e.project_id,e.id)
                    ORDER BY j.sequence DESC LIMIT 1
                ) q ON true
                LEFT JOIN LATERAL (
                    SELECT v.version_number,d.decision FROM work.plans pl
                    JOIN work.plan_versions v ON (v.organization_id,v.project_id,v.plan_id,v.version_number)
                        =(pl.organization_id,pl.project_id,pl.id,pl.last_version)
                    LEFT JOIN governance.plan_version_decisions d ON (d.organization_id,d.project_id,d.plan_version_id)
                        =(v.organization_id,v.project_id,v.id)
                    WHERE (pl.organization_id,pl.project_id,pl.epic_id)=(e.organization_id,e.project_id,e.id)
                ) p ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_object_agg(status,task_count) AS counts FROM (
                        SELECT task.status,count(*) AS task_count FROM work.tasks task
                        WHERE (task.organization_id,task.project_id,task.epic_id)=(e.organization_id,e.project_id,e.id)
                        GROUP BY task.status
                    ) totals
                ) t ON true
                WHERE (e.organization_id,e.project_id,e.id)=(binding.organization_id,binding.project_id,intake.epic_id)
                ON CONFLICT (operation_id) DO NOTHING;
            END IF;
            RETURN QUERY SELECT c.id,c.epic_state FROM platform.manager_epic_context_versions c
            WHERE (c.organization_id,c.project_id,c.interaction_id,c.operation_id,c.assignment_id,c.workflow_run_id)
                =(binding.organization_id,binding.project_id,intake.interaction_id,oid,aid,rid);
            IF FOUND THEN
                INSERT INTO audit.audit_events(id,organization_id,project_id,occurred_at,actor_type,action,object_type,
                                               object_id,result,correlation_id,details)
                VALUES (gen_random_uuid(),binding.organization_id,binding.project_id,clock_timestamp(),'SERVICE',
                        'MANAGER_INPUT_READ','OPERATION',oid,'SUCCEEDED',binding.correlation_id,'{}'::jsonb);
            END IF;
        END $$;

ALTER FUNCTION platform.capture_manager_epic_context(oid uuid, aid uuid, rid uuid) OWNER TO ai_res_owner;

CREATE FUNCTION platform.fence_model_profile_lifecycle() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
  IF OLD.identity_mode='FLASH_OBSERVED' AND
     ROW(NEW.status,NEW.approved_at,NEW.approved_by,NEW.deprecated_at) IS DISTINCT FROM
     ROW(OLD.status,OLD.approved_at,OLD.approved_by,OLD.deprecated_at) THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
      'ai_res.model_profile_lifecycle:' || OLD.id::text, 0));
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.fence_model_profile_lifecycle() OWNER TO ai_res_owner;

CREATE FUNCTION platform.finish_llm_poc_settlement() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  UPDATE platform.llm_poc_attempts SET state='SETTLED' WHERE account_id=NEW.account_id AND id=NEW.attempt_id;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.finish_llm_poc_settlement() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.guard_admission_reapproval_generation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF OLD.blocked AND NOT NEW.blocked AND NEW.current_generation<=OLD.current_generation THEN
    RAISE EXCEPTION 'clearing an admission block requires a new generation'
      USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_admission_reapproval_generation() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_llm_poc_account() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF (to_jsonb(NEW)-'attempt_sequence'-'blocked') IS DISTINCT FROM (to_jsonb(OLD)-'attempt_sequence'-'blocked')
     OR NEW.attempt_sequence NOT IN (OLD.attempt_sequence,OLD.attempt_sequence+1) OR (OLD.blocked AND NOT NEW.blocked) THEN
    RAISE EXCEPTION 'technical budget cannot be reset, enlarged or unblocked' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_llm_poc_account() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_llm_poc_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE account platform.llm_poc_budget_accounts%ROWTYPE; used_cost numeric;
BEGIN
  SELECT * INTO account FROM platform.llm_poc_budget_accounts WHERE id=NEW.account_id FOR UPDATE;
  IF account.id IS NULL THEN
    RAISE EXCEPTION 'technical budget unavailable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF TG_OP='INSERT' THEN
    IF account.blocked OR NEW.sequence<>account.attempt_sequence OR NEW.state<>'RESERVED' OR NEW.claimed_at IS NOT NULL THEN
      RAISE EXCEPTION 'invalid technical reservation' USING ERRCODE='integrity_constraint_violation';
    END IF;
    SELECT account.original_spend+coalesce(sum(coalesce(s.charged_cost,a.reserved_cost)),0) INTO used_cost
      FROM platform.llm_poc_attempts a LEFT JOIN platform.llm_poc_settlements s ON s.account_id=a.account_id AND s.attempt_id=a.id
      WHERE a.account_id=NEW.account_id;
    NEW.reserved_cost := (account.input_bound*account.input_per_million+account.output_bound*account.output_per_million)/1000000;
    NEW.plan_sha256 := account.plan_sha256;
    NEW.tariff_sha256 := account.tariff_sha256;
    IF used_cost+NEW.reserved_cost>account.max_cost OR NEW.sequence>account.max_attempts THEN
      RAISE EXCEPTION 'technical budget exhausted' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSE
    IF (to_jsonb(NEW)-'state'-'claimed_at') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'claimed_at') THEN
      RAISE EXCEPTION 'technical request binding is immutable' USING ERRCODE='integrity_constraint_violation';
    END IF;
    IF OLD.state='RESERVED' AND NEW.state='CLAIMED' AND NOT account.blocked THEN
      NEW.claimed_at := clock_timestamp();
    ELSIF OLD.state='CLAIMED' AND NEW.state='SETTLED' AND NEW.claimed_at IS NOT DISTINCT FROM OLD.claimed_at
      AND EXISTS (SELECT 1 FROM platform.llm_poc_settlements WHERE account_id=NEW.account_id AND attempt_id=NEW.id) THEN
      NULL;
    ELSE
      RAISE EXCEPTION 'technical dispatch claim cannot be replayed' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_llm_poc_attempt() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_llm_poc_settlement() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE account platform.llm_poc_budget_accounts%ROWTYPE; attempt platform.llm_poc_attempts%ROWTYPE;
BEGIN
  SELECT * INTO account FROM platform.llm_poc_budget_accounts WHERE id=NEW.account_id FOR UPDATE;
  SELECT * INTO attempt FROM platform.llm_poc_attempts WHERE account_id=NEW.account_id AND id=NEW.attempt_id;
  IF account.id IS NULL OR attempt.id IS NULL OR attempt.state<>'CLAIMED' THEN
    RAISE EXCEPTION 'technical settlement requires an unresolved dispatch claim' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF NEW.outcome IN ('KNOWN','OVERRUN') THEN
    IF NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL OR NEW.input_tokens<0 OR NEW.output_tokens<0 THEN
      RAISE EXCEPTION 'invalid technical usage' USING ERRCODE='integrity_constraint_violation';
    END IF;
    NEW.charged_cost := (NEW.input_tokens*account.input_per_million+NEW.output_tokens*account.output_per_million)/1000000;
    NEW.outcome := CASE WHEN NEW.input_tokens>account.input_bound OR NEW.output_tokens>attempt.max_output_tokens THEN 'OVERRUN' ELSE 'KNOWN' END;
  ELSE
    NEW.charged_cost := attempt.reserved_cost;
  END IF;
  IF NEW.outcome IN ('OVERRUN','INVALID_USAGE') THEN
    UPDATE platform.llm_poc_budget_accounts SET blocked=true WHERE id=NEW.account_id;
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_llm_poc_settlement() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_model_admission_call() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.status<>'IN_FLIGHT' OR NEW.finalized_at IS NOT NULL OR NEW.observed_sha256 IS NOT NULL THEN
      RAISE EXCEPTION 'admission call starts unresolved' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSIF OLD.status<>'IN_FLIGHT' OR NEW.status NOT IN ('VALIDATED','BLOCKED')
     OR (to_jsonb(NEW)-'status'-'observed_sha256'-'finalized_at') IS DISTINCT FROM
        (to_jsonb(OLD)-'status'-'observed_sha256'-'finalized_at') THEN
    RAISE EXCEPTION 'admission call binding and terminal evidence are immutable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_model_admission_call() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_model_admission_control() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.profile_id IS DISTINCT FROM OLD.profile_id THEN
    RAISE EXCEPTION 'admission profile binding is immutable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF current_user='ai_res_owner' THEN
    IF NEW.current_generation IS DISTINCT FROM OLD.current_generation AND NEW.current_generation<=OLD.current_generation THEN
      RAISE EXCEPTION 'admission generation must advance' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSE
    IF NEW.current_generation IS DISTINCT FROM OLD.current_generation OR (OLD.blocked AND NOT NEW.blocked) THEN
      RAISE EXCEPTION 'runtime cannot approve or clear an admission block' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  IF NEW.call_sequence NOT IN (OLD.call_sequence,OLD.call_sequence+1) THEN
    RAISE EXCEPTION 'admission sequence must advance once' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_model_admission_control() OWNER TO ai_res_owner;

CREATE FUNCTION platform.guard_model_profile() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE rank_old int; rank_new int;
BEGIN  -- a profile version is a snapshot: born CANDIDATE, only its lifecycle moves, forward only; a row that a run may reference is never deleted
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'CANDIDATE' OR NEW.approved_at IS NOT NULL OR NEW.approved_by IS NOT NULL THEN
      RAISE EXCEPTION 'a model profile is created CANDIDATE and unapproved (approval is a separate, human step)' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'model profile % is never deleted (retire it instead)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'status' - 'approved_at' - 'approved_by' - 'deprecated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'approved_at' - 'approved_by' - 'deprecated_at') THEN
    RAISE EXCEPTION 'model profile % is immutable except for its lifecycle (publish a new profile_version)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.approved_at IS NOT NULL AND (NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.approved_by IS DISTINCT FROM OLD.approved_by) THEN
    RAISE EXCEPTION 'the approval of model profile % is not rewritten', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.deprecated_at IS NOT NULL AND NEW.deprecated_at IS DISTINCT FROM OLD.deprecated_at THEN
    RAISE EXCEPTION 'deprecated_at of model profile % is not rewritten', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  rank_old := array_position(ARRAY['CANDIDATE','APPROVED','DEPRECATED','RETIRED'], OLD.status);
  rank_new := array_position(ARRAY['CANDIDATE','APPROVED','DEPRECATED','RETIRED'], NEW.status);
  IF rank_new < rank_old THEN
    RAISE EXCEPTION 'model profile % status may not go back from % to %', OLD.id, OLD.status, NEW.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

ALTER FUNCTION platform.guard_model_profile() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.keep_operation_assignment_binding() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
        BEGIN
            IF OLD.revoked_at IS NOT NULL
                OR (OLD.workflow_run_id IS NOT NULL AND NEW.workflow_run_id IS DISTINCT FROM OLD.workflow_run_id)
                OR (OLD.start_admitted AND NOT NEW.start_admitted)
            THEN
                RAISE EXCEPTION 'operation assignment is immutable after binding/revocation' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$;

ALTER FUNCTION platform.keep_operation_assignment_binding() OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.lock_manager_epic_context_assignment(oid uuid, expected_action text) RETURNS TABLE(assignment_id uuid, workflow_run_id uuid, organization_id uuid, project_id uuid, correlation_id uuid)
    LANGUAGE sql
    SET search_path TO 'pg_catalog'
    AS $$
            SELECT a.id,a.workflow_run_id,a.organization_id,a.project_id,a.correlation_id
            FROM platform.operation_execution_assignments a
            WHERE a.operation_id=oid AND a.revoked_at IS NULL AND a.workflow_type='ManagerIntakeWorkflow'
              AND expected_action=ANY(a.allowed_actions) AND expected_action=current_setting('app.platform_action',true)
              AND a.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
              AND a.project_id=NULLIF(current_setting('app.project_id',true),'')::uuid
              AND oid=NULLIF(current_setting('app.platform_operation_id',true),'')::uuid
              AND a.id=NULLIF(current_setting('app.platform_assignment_id',true),'')::uuid
              AND a.workflow_run_id=NULLIF(current_setting('app.platform_workflow_run_id',true),'')::uuid
            FOR SHARE OF a
        $$;

ALTER FUNCTION platform.lock_manager_epic_context_assignment(oid uuid, expected_action text) OWNER TO ai_res_owner;

CREATE FUNCTION platform.manager_epic_context_matches_draft(oid uuid, cid uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
        DECLARE
            binding record;
            issued record;
        BEGIN
            SELECT * INTO binding FROM platform.lock_manager_epic_context_assignment(oid,'manager.record_draft');
            IF NOT FOUND THEN RETURN false; END IF;

            PERFORM 1 FROM operations.operations o
            WHERE (o.organization_id,o.project_id,o.id)=(binding.organization_id,binding.project_id,oid)
              AND o.operation_type='MANAGER_MESSAGE' AND o.status IN ('RUNNING','SUCCEEDED')
            FOR NO KEY UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;

            SELECT c.id,c.assignment_id,c.workflow_run_id INTO issued
            FROM platform.manager_epic_context_versions c WHERE c.operation_id=oid;
            IF NOT FOUND THEN RETURN cid IS NULL; END IF;
            RETURN (issued.id,issued.assignment_id,issued.workflow_run_id)
                IS NOT DISTINCT FROM (cid,binding.assignment_id,binding.workflow_run_id);
        END $$;

ALTER FUNCTION platform.manager_epic_context_matches_draft(oid uuid, cid uuid) OWNER TO ai_res_owner;

CREATE FUNCTION platform.matches_bound_execution_status(oid uuid, rid uuid, ns text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.revoked_at IS NULL
                  AND a.task_queue='ai-res-manager' AND a.workflow_contract_version=1
                  AND (o.operation_type,a.workflow_type) IN (
                      ('MANAGER_MESSAGE','ManagerIntakeWorkflow'),('PLAN_EXECUTION','PlanExecutionWorkflow')
                  )
                  AND o.status IN ('ACCEPTED','QUEUED','RUNNING','WAITING_FOR_HUMAN','WAITING_FOR_DEPENDENCY','RETRYING','CANCEL_REQUESTED')
            )
        $$;

ALTER FUNCTION platform.matches_bound_execution_status(oid uuid, rid uuid, ns text) OWNER TO ai_res_owner;

CREATE FUNCTION platform.matches_bound_manager_task(oid uuid, rid uuid, ns text, queue text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.task_queue=queue
                  AND a.task_queue='ai-res-manager' AND a.workflow_type IN ('ManagerIntakeWorkflow','PlanExecutionWorkflow')
                  AND a.revoked_at IS NULL
                FOR SHARE OF a
            )
        $$;

ALTER FUNCTION platform.matches_bound_manager_task(oid uuid, rid uuid, ns text, queue text) OWNER TO ai_res_owner;

CREATE FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major integer, digest bytea) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.id=aid AND a.workflow_id=wid AND a.workflow_type=wtype AND a.namespace=ns AND a.task_queue=queue
                  AND a.workflow_contract_version=major AND a.input_digest=digest AND a.revoked_at IS NULL
                  AND a.start_admitted AND a.workflow_run_id IS NULL AND o.status='ACCEPTED' AND a.task_queue='ai-res-manager'
                  AND ((o.operation_type='MANAGER_MESSAGE' AND a.workflow_type='ManagerIntakeWorkflow')
                    OR (o.operation_type='PLAN_EXECUTION' AND a.workflow_type='PlanExecutionWorkflow'))
                  AND EXISTS (
                      SELECT 1 FROM audit.outbox_events e WHERE e.aggregate_id=o.id AND e.organization_id=o.organization_id
                        AND e.project_id=o.project_id AND e.aggregate_type='OPERATION'
                        AND e.event_type='operation.accepted' AND e.destination='orchestration.operation-start'
                        AND e.status IN ('PENDING','IN_FLIGHT')
                        AND e.envelope #> '{data,refs}' @> jsonb_build_array(
                            jsonb_build_object('resourceType','OPERATION_EXECUTION_ASSIGNMENT','resourceId',a.id::text))
                  )
            )
        $$;

ALTER FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major integer, digest bytea) OWNER TO ai_res_owner;

CREATE FUNCTION platform.matches_reconciliation_describe(oid uuid, rid uuid, ns text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform.operation_execution_assignments a
                JOIN operations.operations o ON (o.organization_id,o.project_id,o.id)=(a.organization_id,a.project_id,a.operation_id)
                WHERE a.operation_id=oid AND a.workflow_run_id=rid AND a.namespace=ns AND a.revoked_at IS NULL
                  AND a.task_queue='ai-res-manager' AND a.workflow_type='ManagerIntakeWorkflow' AND a.workflow_contract_version=1
                  AND o.operation_type='MANAGER_MESSAGE' AND o.status IN ('ACCEPTED','QUEUED')
            )
        $$;

ALTER FUNCTION platform.matches_reconciliation_describe(oid uuid, rid uuid, ns text) OWNER TO ai_res_owner;

CREATE FUNCTION platform.owner_identity_snapshot(o uuid, u uuid, sid uuid, p uuid, d uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
DECLARE member jsonb; usr jsonb; factors jsonb; mfa text; profile text;
  control text; current_record text; pending jsonb; gen integer; receipt jsonb;
BEGIN
  IF current_setting('transaction_isolation')<>'read committed' OR current_setting('session_replication_role')<>'origin' THEN
    RAISE EXCEPTION 'operator isolation unavailable' USING ERRCODE='check_violation';
  END IF;
  PERFORM 1 FROM platform.model_admission_operators b WHERE b.database_login=session_user AND b.profile_id=p
    AND b.organization_id=o AND b.user_id=u FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'operator unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT jsonb_build_object('role_code',m.role_code,'status',m.status,'row_version',m.row_version) INTO member
    FROM organization.memberships m WHERE m.organization_id=o AND m.user_id=u AND m.status='ACTIVE' FOR SHARE;
  SELECT jsonb_build_object('status',v.status,'row_version',v.row_version) INTO usr
    FROM iam.users v WHERE v.organization_id=o AND v.id=u AND v.status='ACTIVE' FOR SHARE;
  IF member IS NULL OR usr IS NULL THEN RAISE EXCEPTION 'owner unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT coalesce(jsonb_agg(f.id::text ORDER BY f.id),'[]'::jsonb) INTO factors FROM
    (SELECT v.id FROM iam.mfa_factors v WHERE v.organization_id=o AND v.user_id=u AND v.status='ACTIVE' ORDER BY v.id FOR SHARE) f;
  IF factors='[]'::jsonb THEN RAISE EXCEPTION 'MFA unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT v.mfa_verified_at::text INTO mfa FROM iam.sessions v WHERE v.id=sid AND v.organization_id=o AND v.user_id=u
    AND v.revoked_at IS NULL AND v.idle_expires_at>clock_timestamp() AND v.absolute_expires_at>clock_timestamp() FOR SHARE;
  IF mfa IS NULL THEN RAISE EXCEPTION 'session unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgrelid='platform.model_profiles'::regclass
    AND t.tgname='trg_model_profiles_lifecycle_fence' AND NOT t.tgisinternal AND t.tgenabled IN ('O','A')
    AND t.tgtype=19 AND t.tgnargs=0 AND t.tgattr=''::pg_catalog.int2vector AND t.tgqual IS NULL
    AND t.tgfoid=pg_catalog.to_regprocedure('platform.fence_model_profile_lifecycle()')) THEN
    RAISE EXCEPTION 'lifecycle fence unavailable' USING ERRCODE='check_violation';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('ai_res.model_profile_lifecycle:' || p::text,0));
  SELECT to_jsonb(v)::text INTO profile FROM platform.model_profiles v WHERE v.id=p AND v.identity_mode='FLASH_OBSERVED'
    AND v.provider='deepseek' AND v.provider_model_id='deepseek-flash' AND v.pinned_model_version IS NULL
    AND v.status IN ('CANDIDATE','APPROVED') AND (v.deprecated_at IS NULL OR v.deprecated_at>clock_timestamp());
  IF profile IS NULL THEN RAISE EXCEPTION 'profile unavailable' USING ERRCODE='check_violation'; END IF;
  SELECT to_jsonb(c)::text,c.current_generation INTO control,gen FROM platform.model_admission_controls c WHERE c.profile_id=p FOR UPDATE;
  gen:=coalesce(gen,0);
  SELECT to_jsonb(v)::text INTO current_record FROM platform.model_admission_versions v WHERE v.profile_id=p AND v.generation=gen;
  IF control IS NOT NULL AND current_record IS NULL THEN RAISE EXCEPTION 'admission unavailable' USING ERRCODE='check_violation'; END IF;
  SELECT coalesce(jsonb_agg(x.snapshot ORDER BY x.call_sequence),'[]'::jsonb) INTO pending FROM
    (SELECT to_jsonb(v)::text AS snapshot,v.call_sequence FROM platform.model_admission_calls v WHERE v.profile_id=p AND v.status='IN_FLIGHT') x;
  SELECT jsonb_build_object('command_sha256',v.command_sha256,'generation',v.generation,'action',v.action) INTO receipt
    FROM platform.model_admission_decisions v WHERE v.decision_id=d AND v.profile_id=p AND v.organization_id=o AND v.user_id=u
    AND v.database_login=session_user AND v.session_id=sid;
  -- Row locks cannot stop time. Recheck AFTER the fence/control waits.
  IF NOT EXISTS(SELECT 1 FROM iam.sessions v WHERE v.id=sid AND v.user_id=u AND v.organization_id=o
    AND v.revoked_at IS NULL AND v.mfa_verified_at IS NOT NULL AND v.idle_expires_at>clock_timestamp() AND v.absolute_expires_at>clock_timestamp())
    OR NOT EXISTS(SELECT 1 FROM platform.model_profiles v WHERE v.id=p AND (v.deprecated_at IS NULL OR v.deprecated_at>clock_timestamp())) THEN
    RAISE EXCEPTION 'owner or profile expired' USING ERRCODE='insufficient_privilege';
  END IF;
  RETURN jsonb_build_object('subject',jsonb_build_object('member',member,'user',usr,'factors',factors,'mfaAt',mfa),
    'profile',profile,'control',control,'current',current_record,'pending',pending,'generation',gen,'receipt',receipt);
END $$;

ALTER FUNCTION platform.owner_identity_snapshot(o uuid, u uuid, sid uuid, p uuid, d uuid) OWNER TO ai_res_owner;

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

CREATE FUNCTION platform.resolve_operation_assignment(aid uuid, oid uuid, wid text, rid uuid, action text) RETURNS TABLE(organization_id uuid, project_id uuid, correlation_id uuid)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    SET "app.migration_mode" TO 'on'
    AS $$
            SELECT a.organization_id, a.project_id, a.correlation_id
            FROM platform.operation_execution_assignments a
            WHERE a.id = aid AND a.operation_id = oid AND a.workflow_id = wid AND a.workflow_run_id = rid
              AND a.revoked_at IS NULL AND action = ANY(a.allowed_actions)
            FOR SHARE OF a
        $$;

ALTER FUNCTION platform.resolve_operation_assignment(aid uuid, oid uuid, wid text, rid uuid, action text) OWNER TO ai_res_owner;

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

CREATE FUNCTION work.require_platform_plan_item() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM work.plan_item_tasks m
                JOIN work.plan_executions e ON e.operation_id=m.operation_id
                JOIN governance.plan_version_decisions d ON d.id=e.decision_id AND d.plan_version_id=e.plan_version_id
                WHERE m.operation_id=NEW.operation_id AND m.task_id=NEW.id
                  AND d.decision='APPROVE' AND m.item_id=ANY(d.approved_items)
            ) THEN
                RAISE EXCEPTION 'Task needs an approved PlanItem mapping' USING ERRCODE='integrity_constraint_violation';
            END IF;
            RETURN NULL;
        END $$;

ALTER FUNCTION work.require_platform_plan_item() OWNER TO ai_res_owner;

CREATE FUNCTION work.require_unsealed_interaction() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
        BEGIN
            PERFORM 1 FROM work.manager_interactions i
            WHERE i.id=NEW.interaction_id AND i.organization_id=NEW.organization_id AND i.project_id=NEW.project_id
            FOR NO KEY UPDATE;
            IF NOT FOUND OR EXISTS (
                SELECT 1 FROM work.manager_interaction_events e
                WHERE e.interaction_id=NEW.interaction_id
            ) THEN
                RAISE EXCEPTION 'Manager interaction attachments are sealed' USING ERRCODE='integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$;

ALTER FUNCTION work.require_unsealed_interaction() OWNER TO ai_res_owner;

SET default_table_access_method = heap;

CREATE TABLE agents.worker_definition_versions (
    id uuid NOT NULL,
    worker_definition_id uuid NOT NULL,
    version text NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    input_contract_version text NOT NULL,
    output_contract_version text NOT NULL,
    output_schema_id text NOT NULL,
    output_schema_version text NOT NULL,
    acceptance_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    runtime_profile_version text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_worker_definition_versions_acceptance_schema CHECK ((jsonb_typeof(acceptance_schema) = 'object'::text)),
    CONSTRAINT ck_worker_definition_versions_input_contract_version CHECK (((length(input_contract_version) >= 1) AND (length(input_contract_version) <= 32))),
    CONSTRAINT ck_worker_definition_versions_output_contract_version CHECK (((length(output_contract_version) >= 1) AND (length(output_contract_version) <= 32))),
    CONSTRAINT ck_worker_definition_versions_output_schema_id CHECK (((length(output_schema_id) >= 1) AND (length(output_schema_id) <= 200))),
    CONSTRAINT ck_worker_definition_versions_output_schema_version CHECK (((length(output_schema_version) >= 1) AND (length(output_schema_version) <= 32))),
    CONSTRAINT ck_worker_definition_versions_runtime_profile_version CHECK (((length(runtime_profile_version) >= 1) AND (length(runtime_profile_version) <= 64))),
    CONSTRAINT ck_worker_definition_versions_status CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'DEPRECATED'::text, 'RETIRED'::text]))),
    CONSTRAINT ck_worker_definition_versions_version CHECK (((length(version) >= 1) AND (length(version) <= 64)))
);

ALTER TABLE agents.worker_definition_versions OWNER TO ai_res_owner;

CREATE TABLE agents.worker_definitions (
    id uuid NOT NULL,
    worker_role text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_worker_definitions_worker_role CHECK ((worker_role = ANY (ARRAY['ELICITATION'::text, 'RESEARCH'::text, 'BUSINESS_ANALYSIS'::text, 'REQUIREMENTS'::text, 'SYSTEM_ANALYSIS'::text, 'API_INTEGRATION'::text, 'MODELING_DIAGRAM_VALIDATION'::text, 'QUALITY_ASSURANCE'::text, 'TRACEABILITY_CHANGE'::text])))
);

ALTER TABLE agents.worker_definitions OWNER TO ai_res_owner;

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

CREATE TABLE agents.worker_tool_grants (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    worker_run_id uuid NOT NULL,
    identity_id uuid NOT NULL,
    environment text NOT NULL,
    tool_id text NOT NULL,
    tool_version text NOT NULL,
    contract_version text NOT NULL,
    operation text NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid NOT NULL,
    classification text NOT NULL,
    permission_scope text NOT NULL,
    allowed_model_profiles text[] NOT NULL,
    budget_ref uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    rate_minute timestamp with time zone,
    rate_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_worker_tool_grant_rate_count CHECK ((rate_count >= 0)),
    CONSTRAINT ck_worker_tool_grant_rate_window CHECK (((rate_minute IS NULL) = (rate_count = 0)))
);

ALTER TABLE ONLY agents.worker_tool_grants FORCE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_tool_grants OWNER TO ai_res_owner;

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
    dispatch_assignment_id uuid,
    dispatch_namespace text,
    CONSTRAINT ck_outbox_assigned_route_resolved CHECK (((dispatch_namespace IS NOT NULL) OR (status = ANY (ARRAY['QUARANTINED'::text, 'PUBLISHED'::text])) OR (destination <> ALL (ARRAY['orchestration.operation-start'::text, 'orchestration.operation-cancel'::text])) OR (NOT COALESCE(((envelope #> '{data,refs}'::text[]) @> '[{"resourceType": "OPERATION_EXECUTION_ASSIGNMENT"}]'::jsonb), false)))),
    CONSTRAINT ck_outbox_dispatch_route CHECK ((((dispatch_assignment_id IS NULL) AND (dispatch_namespace IS NULL)) OR ((dispatch_assignment_id IS NOT NULL) AND (dispatch_namespace IS NOT NULL) AND (dispatch_namespace ~ '^[a-z0-9][a-z0-9-]{0,62}$'::text) AND (aggregate_type = 'OPERATION'::text) AND (((destination = 'orchestration.operation-start'::text) AND (event_type = 'operation.accepted'::text) AND (aggregate_sequence = 1)) OR ((destination = 'orchestration.operation-cancel'::text) AND (event_type = 'operation.cancel_requested'::text))) AND (jsonb_array_length(jsonb_path_query_array(envelope, '$."data"."refs"[*]?(@."resourceType" == "OPERATION_EXECUTION_ASSIGNMENT")'::jsonpath)) = 1) AND COALESCE(((envelope #> '{data,refs}'::text[]) @> jsonb_build_array(jsonb_build_object('resourceType', 'OPERATION_EXECUTION_ASSIGNMENT', 'resourceId', (dispatch_assignment_id)::text))), false)))),
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
    builder_manifest jsonb,
    creation_transaction_id xid8,
    CONSTRAINT ck_context_package_versions_builder_manifest CHECK ((jsonb_typeof(builder_manifest) = 'object'::text)),
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

CREATE TABLE governance.manager_proposal_decisions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    proposal_version_id uuid NOT NULL,
    content_hash bytea NOT NULL,
    approver_id uuid NOT NULL,
    decision text NOT NULL,
    comment text,
    decided_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT manager_proposal_decisions_comment_check CHECK ((length(comment) <= 20000)),
    CONSTRAINT manager_proposal_decisions_decision_check CHECK ((decision = ANY (ARRAY['APPROVE'::text, 'REJECT'::text, 'REQUEST_CHANGES'::text])))
);

ALTER TABLE ONLY governance.manager_proposal_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.manager_proposal_decisions OWNER TO ai_res_owner;

CREATE TABLE governance.plan_version_decisions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_version_id uuid NOT NULL,
    content_hash bytea NOT NULL,
    approver_id uuid NOT NULL,
    decision text NOT NULL,
    approved_items uuid[] NOT NULL,
    comment text,
    decided_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT plan_version_decisions_approved_items_check CHECK ((array_position(approved_items, NULL::uuid) IS NULL)),
    CONSTRAINT plan_version_decisions_check CHECK (((decision = 'APPROVE'::text) = (cardinality(approved_items) > 0))),
    CONSTRAINT plan_version_decisions_decision_check CHECK ((decision = ANY (ARRAY['APPROVE'::text, 'REJECT'::text, 'REQUEST_CHANGES'::text])))
);

ALTER TABLE ONLY governance.plan_version_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.plan_version_decisions OWNER TO ai_res_owner;

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

CREATE TABLE governance.rule_evaluations (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    context_version_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    evaluated_at timestamp with time zone NOT NULL,
    engine_version text NOT NULL,
    schema_version text NOT NULL,
    input_snapshot jsonb NOT NULL,
    input_hash bytea NOT NULL,
    result jsonb NOT NULL,
    result_hash bytea NOT NULL,
    previous_evaluation_id uuid,
    CONSTRAINT ck_rule_evaluations_engine CHECK ((engine_version ~ '^[A-Za-z0-9_.-]{1,80}$'::text)),
    CONSTRAINT ck_rule_evaluations_input CHECK ((jsonb_typeof(input_snapshot) = 'object'::text)),
    CONSTRAINT ck_rule_evaluations_input_hash CHECK ((octet_length(input_hash) = 32)),
    CONSTRAINT ck_rule_evaluations_not_self CHECK ((previous_evaluation_id IS DISTINCT FROM id)),
    CONSTRAINT ck_rule_evaluations_result CHECK ((jsonb_typeof(result) = 'object'::text)),
    CONSTRAINT ck_rule_evaluations_result_hash CHECK ((octet_length(result_hash) = 32)),
    CONSTRAINT ck_rule_evaluations_schema CHECK ((schema_version ~ '^[A-Za-z0-9_.-]{1,80}$'::text))
);

ALTER TABLE ONLY governance.rule_evaluations FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_evaluations OWNER TO ai_res_owner;

CREATE TABLE governance.rule_exception_revocations (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    exception_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    revoked_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY governance.rule_exception_revocations FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_exception_revocations OWNER TO ai_res_owner;

CREATE TABLE governance.rule_exceptions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    target_version_id uuid NOT NULL,
    target_content_hash bytea NOT NULL,
    target_effect_hash bytea NOT NULL,
    permission_version_id uuid NOT NULL,
    object_type text NOT NULL,
    object_id uuid NOT NULL,
    operation text NOT NULL,
    approved_by uuid NOT NULL,
    approved_at timestamp with time zone NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone NOT NULL,
    reason_code text NOT NULL,
    risk_refs uuid[] NOT NULL,
    compensation_refs uuid[] NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_hash bytea NOT NULL,
    CONSTRAINT ck_rule_exceptions_compensation CHECK (((cardinality(compensation_refs) > 0) AND (array_position(compensation_refs, NULL::uuid) IS NULL))),
    CONSTRAINT ck_rule_exceptions_content_hash CHECK ((octet_length(target_content_hash) = 32)),
    CONSTRAINT ck_rule_exceptions_effect_hash CHECK ((octet_length(target_effect_hash) = 32)),
    CONSTRAINT ck_rule_exceptions_finite_validity CHECK ((isfinite(valid_from) AND isfinite(valid_to) AND (valid_to > valid_from) AND (approved_at <= valid_from))),
    CONSTRAINT ck_rule_exceptions_object_type CHECK ((object_type ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'::text)),
    CONSTRAINT ck_rule_exceptions_operation CHECK ((operation ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'::text)),
    CONSTRAINT ck_rule_exceptions_reason CHECK ((reason_code ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'::text)),
    CONSTRAINT ck_rule_exceptions_risks CHECK (((cardinality(risk_refs) > 0) AND (array_position(risk_refs, NULL::uuid) IS NULL))),
    CONSTRAINT ck_rule_exceptions_snapshot CHECK ((jsonb_typeof(snapshot) = 'object'::text)),
    CONSTRAINT ck_rule_exceptions_snapshot_hash CHECK ((octet_length(snapshot_hash) = 32))
);

ALTER TABLE ONLY governance.rule_exceptions FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_exceptions OWNER TO ai_res_owner;

CREATE TABLE governance.rule_runtime_controls (
    id uuid NOT NULL,
    rule_version_id uuid NOT NULL,
    level text NOT NULL,
    organization_id uuid,
    project_id uuid,
    sequence bigint NOT NULL,
    action text NOT NULL,
    actor_id uuid NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_rule_controls_action CHECK ((action = ANY (ARRAY['PUBLISH'::text, 'SUSPEND'::text, 'RESUME'::text, 'RETIRE'::text]))),
    CONSTRAINT ck_rule_controls_level CHECK ((level = ANY (ARRAY['SYSTEM'::text, 'ORGANIZATION'::text, 'PROJECT'::text]))),
    CONSTRAINT ck_rule_controls_scope CHECK ((((level = 'SYSTEM'::text) AND (organization_id IS NULL) AND (project_id IS NULL)) OR ((level = 'ORGANIZATION'::text) AND (organization_id IS NOT NULL) AND (project_id IS NULL)) OR ((level = 'PROJECT'::text) AND (organization_id IS NOT NULL) AND (project_id IS NOT NULL)))),
    CONSTRAINT ck_rule_controls_sequence CHECK ((sequence > 0))
);

ALTER TABLE ONLY governance.rule_runtime_controls FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_runtime_controls OWNER TO ai_res_owner;

CREATE TABLE governance.rule_validation_reports (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid,
    proposal_version_id uuid NOT NULL,
    proposal_hash bytea NOT NULL,
    basis_hash bytea NOT NULL,
    basis jsonb NOT NULL,
    result jsonb NOT NULL,
    result_hash bytea NOT NULL,
    actor_id uuid NOT NULL,
    evaluated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_rule_validation_basis CHECK ((jsonb_typeof(basis) = 'object'::text)),
    CONSTRAINT ck_rule_validation_basis_hash CHECK ((octet_length(basis_hash) = 32)),
    CONSTRAINT ck_rule_validation_proposal_hash CHECK ((octet_length(proposal_hash) = 32)),
    CONSTRAINT ck_rule_validation_result CHECK ((jsonb_typeof(result) = 'object'::text)),
    CONSTRAINT ck_rule_validation_result_hash CHECK ((octet_length(result_hash) = 32))
);

ALTER TABLE ONLY governance.rule_validation_reports FORCE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_validation_reports OWNER TO ai_res_owner;

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
    last_version_number integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_rules_applies_to_object_type CHECK ((applies_to_object_type ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_rules_last_version_number CHECK ((last_version_number >= 0)),
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

CREATE TABLE platform.llm_poc_attempts (
    id uuid NOT NULL,
    account_id uuid NOT NULL,
    sequence integer NOT NULL,
    request_ref text NOT NULL,
    case_ref text NOT NULL,
    body_sha256 bytea NOT NULL,
    payload_bytes integer NOT NULL,
    stream boolean NOT NULL,
    max_output_tokens integer NOT NULL,
    plan_sha256 bytea NOT NULL,
    tariff_sha256 bytea NOT NULL,
    reserved_cost numeric NOT NULL,
    state text DEFAULT 'RESERVED'::text NOT NULL,
    claimed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_lpa_body_hash CHECK ((octet_length(body_sha256) = 32)),
    CONSTRAINT ck_lpa_bytes CHECK (((payload_bytes >= 1) AND (payload_bytes <= 4096))),
    CONSTRAINT ck_lpa_case CHECK ((case_ref = ANY (ARRAY['TEXT'::text, 'JSON'::text, 'TOOL'::text, 'SSE'::text, 'CANCEL'::text, 'TIMEOUT'::text, 'RECHECK'::text]))),
    CONSTRAINT ck_lpa_claim_time CHECK ((((state = 'RESERVED'::text) AND (claimed_at IS NULL)) OR ((state = ANY (ARRAY['CLAIMED'::text, 'SETTLED'::text])) AND (claimed_at IS NOT NULL)))),
    CONSTRAINT ck_lpa_cost CHECK (((reserved_cost > (0)::numeric) AND (reserved_cost < 'Infinity'::numeric))),
    CONSTRAINT ck_lpa_output CHECK (((max_output_tokens >= 1) AND (max_output_tokens <= 256))),
    CONSTRAINT ck_lpa_plan CHECK ((octet_length(plan_sha256) = 32)),
    CONSTRAINT ck_lpa_request CHECK (((request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'::text) AND (request_ref !~ '[[:space:]]'::text))),
    CONSTRAINT ck_lpa_sequence CHECK (((sequence >= 1) AND (sequence <= 8))),
    CONSTRAINT ck_lpa_state CHECK ((state = ANY (ARRAY['RESERVED'::text, 'CLAIMED'::text, 'SETTLED'::text]))),
    CONSTRAINT ck_lpa_tariff CHECK ((octet_length(tariff_sha256) = 32))
);

ALTER TABLE ONLY platform.llm_poc_attempts FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_attempts OWNER TO ai_res_owner;

CREATE TABLE platform.llm_poc_budget_accounts (
    id uuid NOT NULL,
    authorization_key text NOT NULL,
    currency text NOT NULL,
    max_cost numeric NOT NULL,
    original_spend numeric NOT NULL,
    max_attempts integer NOT NULL,
    input_bound bigint NOT NULL,
    output_bound integer NOT NULL,
    body_bound integer NOT NULL,
    provider text NOT NULL,
    model_id text NOT NULL,
    http_method text NOT NULL,
    upstream_host text NOT NULL,
    upstream_path text NOT NULL,
    plan_sha256 bytea NOT NULL,
    tariff_sha256 bytea NOT NULL,
    input_per_million numeric NOT NULL,
    output_per_million numeric NOT NULL,
    attempt_sequence integer DEFAULT 0 NOT NULL,
    blocked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_lpba_attempts CHECK (((max_attempts >= 1) AND (max_attempts <= 8))),
    CONSTRAINT ck_lpba_authorization CHECK ((authorization_key = 'FLASH_TECHNICAL_ADMISSION_2026_11_17'::text)),
    CONSTRAINT ck_lpba_body CHECK ((body_bound = 4096)),
    CONSTRAINT ck_lpba_cap CHECK (((max_cost > (0)::numeric) AND (max_cost <= (10)::numeric))),
    CONSTRAINT ck_lpba_currency CHECK ((currency = 'USD'::text)),
    CONSTRAINT ck_lpba_host CHECK ((upstream_host = 'api.deepseek.com'::text)),
    CONSTRAINT ck_lpba_input CHECK ((input_bound = 2000000)),
    CONSTRAINT ck_lpba_input_rate CHECK (((input_per_million >= (0)::numeric) AND (input_per_million < 'Infinity'::numeric))),
    CONSTRAINT ck_lpba_method CHECK ((http_method = 'POST'::text)),
    CONSTRAINT ck_lpba_model CHECK ((model_id = 'deepseek-flash'::text)),
    CONSTRAINT ck_lpba_original CHECK (((original_spend >= (0)::numeric) AND (original_spend <= max_cost))),
    CONSTRAINT ck_lpba_output CHECK ((output_bound = 256)),
    CONSTRAINT ck_lpba_output_rate CHECK (((output_per_million >= (0)::numeric) AND (output_per_million < 'Infinity'::numeric))),
    CONSTRAINT ck_lpba_path CHECK ((upstream_path = '/chat/completions'::text)),
    CONSTRAINT ck_lpba_plan CHECK ((octet_length(plan_sha256) = 32)),
    CONSTRAINT ck_lpba_provider CHECK ((provider = 'deepseek'::text)),
    CONSTRAINT ck_lpba_reservable CHECK (((((((input_bound)::numeric * input_per_million) + ((output_bound)::numeric * output_per_million)) / (1000000)::numeric) > (0)::numeric) AND (((((input_bound)::numeric * input_per_million) + ((output_bound)::numeric * output_per_million)) / (1000000)::numeric) <= max_cost))),
    CONSTRAINT ck_lpba_sequence CHECK (((attempt_sequence >= 0) AND (attempt_sequence <= max_attempts))),
    CONSTRAINT ck_lpba_tariff CHECK ((octet_length(tariff_sha256) = 32))
);

ALTER TABLE ONLY platform.llm_poc_budget_accounts FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_budget_accounts OWNER TO ai_res_owner;

CREATE TABLE platform.llm_poc_budget_audit (
    id uuid NOT NULL,
    account_id uuid NOT NULL,
    attempt_id uuid,
    action text NOT NULL,
    reason_code text NOT NULL,
    writer_role text DEFAULT CURRENT_USER NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_lpau_action CHECK ((action = ANY (ARRAY['RESERVE'::text, 'CLAIM'::text, 'SETTLE'::text, 'DENY'::text, 'BLOCK'::text]))),
    CONSTRAINT ck_lpau_reason CHECK ((reason_code = ANY (ARRAY['RESERVED'::text, 'CLAIMED'::text, 'KNOWN'::text, 'UNKNOWN'::text, 'OVERRUN'::text, 'INVALID_USAGE'::text, 'ACCOUNT_BLOCKED'::text, 'BUDGET_EXHAUSTED'::text, 'ATTEMPTS_EXHAUSTED'::text, 'PENDING'::text, 'BINDING_MISMATCH'::text, 'REQUEST_REUSED'::text, 'BODY_REUSED'::text, 'CLAIM_REPLAY'::text, 'SETTLEMENT_CONFLICT'::text, 'INVALID_STATE'::text])))
);

ALTER TABLE ONLY platform.llm_poc_budget_audit FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_budget_audit OWNER TO ai_res_owner;

CREATE TABLE platform.llm_poc_settlements (
    id uuid NOT NULL,
    account_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    outcome text NOT NULL,
    reason_code text NOT NULL,
    input_tokens bigint,
    output_tokens bigint,
    provider_request_ref text,
    proof_sha256 bytea NOT NULL,
    charged_cost numeric NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_lps_charge CHECK (((charged_cost >= (0)::numeric) AND (charged_cost < 'Infinity'::numeric))),
    CONSTRAINT ck_lps_input CHECK ((input_tokens >= 0)),
    CONSTRAINT ck_lps_outcome CHECK ((outcome = ANY (ARRAY['KNOWN'::text, 'UNKNOWN'::text, 'OVERRUN'::text, 'INVALID_USAGE'::text]))),
    CONSTRAINT ck_lps_output CHECK ((output_tokens >= 0)),
    CONSTRAINT ck_lps_proof CHECK ((octet_length(proof_sha256) = 32)),
    CONSTRAINT ck_lps_provider_ref CHECK (((provider_request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'::text) AND (provider_request_ref !~ '[[:space:]]'::text))),
    CONSTRAINT ck_lps_reason CHECK ((reason_code = ANY (ARRAY['USAGE'::text, 'TIMEOUT'::text, 'CANCEL'::text, 'NETWORK'::text, 'PROVIDER_ERROR'::text, 'UNTRUSTED_RESPONSE'::text, 'INVALID_USAGE'::text]))),
    CONSTRAINT ck_lps_shape CHECK (((((outcome = ANY (ARRAY['KNOWN'::text, 'OVERRUN'::text])) AND (input_tokens IS NOT NULL) AND (output_tokens IS NOT NULL) AND (provider_request_ref IS NOT NULL) AND (reason_code = 'USAGE'::text)) OR ((outcome = 'UNKNOWN'::text) AND (input_tokens IS NULL) AND (output_tokens IS NULL) AND (provider_request_ref IS NULL) AND (reason_code = ANY (ARRAY['TIMEOUT'::text, 'CANCEL'::text, 'NETWORK'::text, 'PROVIDER_ERROR'::text, 'UNTRUSTED_RESPONSE'::text]))) OR ((outcome = 'INVALID_USAGE'::text) AND (input_tokens IS NULL) AND (output_tokens IS NULL) AND (provider_request_ref IS NULL) AND (reason_code = 'INVALID_USAGE'::text))) IS TRUE))
);

ALTER TABLE ONLY platform.llm_poc_settlements FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_settlements OWNER TO ai_res_owner;

CREATE TABLE platform.manager_epic_context_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    interaction_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    workflow_run_id uuid NOT NULL,
    epic_state jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT manager_epic_context_versions_epic_state_check CHECK ((jsonb_typeof(epic_state) = 'object'::text))
);

ALTER TABLE ONLY platform.manager_epic_context_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.manager_epic_context_versions OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_audit (
    id uuid NOT NULL,
    profile_id uuid NOT NULL,
    call_id uuid NOT NULL,
    event_type text NOT NULL,
    reason_code text NOT NULL,
    writer_role text DEFAULT CURRENT_USER NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_maa_event_reason CHECK ((((event_type = 'BEGIN'::text) AND (reason_code = 'RESERVED'::text)) OR ((event_type = 'VALIDATED'::text) AND (reason_code = 'MATCH'::text)) OR ((event_type = 'BLOCKED'::text) AND (reason_code = ANY (ARRAY['IDENTITY_MISMATCH'::text, 'MALFORMED_OBSERVATION'::text]))))),
    CONSTRAINT ck_maa_reason CHECK ((reason_code = ANY (ARRAY['RESERVED'::text, 'MATCH'::text, 'IDENTITY_MISMATCH'::text, 'MALFORMED_OBSERVATION'::text]))),
    CONSTRAINT ck_maa_type CHECK ((event_type = ANY (ARRAY['BEGIN'::text, 'VALIDATED'::text, 'BLOCKED'::text])))
);

ALTER TABLE ONLY platform.model_admission_audit FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_audit OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_calls (
    id uuid NOT NULL,
    profile_id uuid NOT NULL,
    generation integer NOT NULL,
    call_sequence bigint NOT NULL,
    request_ref text NOT NULL,
    expected_sha256 bytea NOT NULL,
    status text DEFAULT 'IN_FLIGHT'::text NOT NULL,
    observed_sha256 bytea,
    finalized_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_mcall_expected CHECK ((octet_length(expected_sha256) = 32)),
    CONSTRAINT ck_mcall_final CHECK ((((status = 'IN_FLIGHT'::text) AND (finalized_at IS NULL) AND (observed_sha256 IS NULL)) OR ((status = 'VALIDATED'::text) AND (finalized_at IS NOT NULL) AND (observed_sha256 IS NOT NULL)) OR ((status = 'BLOCKED'::text) AND (finalized_at IS NOT NULL)))),
    CONSTRAINT ck_mcall_observed CHECK (((observed_sha256 IS NULL) OR (octet_length(observed_sha256) = 32))),
    CONSTRAINT ck_mcall_ref CHECK (((request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'::text) AND (request_ref !~ '[[:space:]]'::text))),
    CONSTRAINT ck_mcall_sequence CHECK ((call_sequence > 0)),
    CONSTRAINT ck_mcall_status CHECK ((status = ANY (ARRAY['IN_FLIGHT'::text, 'VALIDATED'::text, 'BLOCKED'::text])))
);

ALTER TABLE ONLY platform.model_admission_calls FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_calls OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_controls (
    profile_id uuid NOT NULL,
    current_generation integer NOT NULL,
    blocked boolean DEFAULT false NOT NULL,
    call_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_mac_sequence CHECK ((call_sequence >= 0))
);

ALTER TABLE ONLY platform.model_admission_controls FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_controls OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_decisions (
    decision_id uuid NOT NULL,
    profile_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id uuid NOT NULL,
    database_login name DEFAULT SESSION_USER NOT NULL,
    action text NOT NULL,
    generation integer NOT NULL,
    command_sha256 text NOT NULL,
    review_sha256 text NOT NULL,
    profile_sha256 text NOT NULL,
    expectation_sha256 text NOT NULL,
    observation_sha256 text NOT NULL,
    policy_version text NOT NULL,
    reason_code text NOT NULL,
    correlation_id uuid NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_mad_action CHECK ((action = ANY (ARRAY['ACCEPT_IDENTITY'::text, 'BLOCK'::text]))),
    CONSTRAINT ck_mad_action_reason CHECK ((((action = 'ACCEPT_IDENTITY'::text) AND (reason_code = 'HUMAN_IDENTITY_ACCEPTED'::text)) OR ((action = 'BLOCK'::text) AND (reason_code = 'HUMAN_BLOCKED'::text)))),
    CONSTRAINT ck_mad_command CHECK ((command_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_mad_expectation CHECK ((expectation_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_mad_generation CHECK ((generation > 0)),
    CONSTRAINT ck_mad_observation CHECK ((observation_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_mad_policy CHECK ((policy_version ~ '^[A-Za-z0-9_.:-]{1,128}$'::text)),
    CONSTRAINT ck_mad_profile CHECK ((profile_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_mad_reason CHECK ((reason_code = ANY (ARRAY['HUMAN_IDENTITY_ACCEPTED'::text, 'HUMAN_BLOCKED'::text]))),
    CONSTRAINT ck_mad_review CHECK ((review_sha256 ~ '^[0-9a-f]{64}$'::text))
);

ALTER TABLE ONLY platform.model_admission_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_decisions OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_operators (
    database_login name NOT NULL,
    profile_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

ALTER TABLE ONLY platform.model_admission_operators FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_operators OWNER TO ai_res_owner;

CREATE TABLE platform.model_admission_versions (
    profile_id uuid NOT NULL,
    generation integer NOT NULL,
    profile_version integer NOT NULL,
    expectation jsonb NOT NULL,
    expectation_sha256 bytea NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_mav_expectation CHECK ((jsonb_typeof(expectation) = 'object'::text)),
    CONSTRAINT ck_mav_generation CHECK ((generation > 0)),
    CONSTRAINT ck_mav_hash CHECK ((octet_length(expectation_sha256) = 32)),
    CONSTRAINT ck_mav_profile_version CHECK ((profile_version > 0))
);

ALTER TABLE ONLY platform.model_admission_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_versions OWNER TO ai_res_owner;

CREATE TABLE platform.model_profiles (
    id uuid NOT NULL,
    profile_key text NOT NULL,
    profile_version integer NOT NULL,
    provider text NOT NULL,
    provider_model_id text NOT NULL,
    pinned_model_version text,
    capabilities text[] NOT NULL,
    context_window_tokens integer NOT NULL,
    max_output_tokens integer NOT NULL,
    data_classifications text[] NOT NULL,
    allowed_regions text[] NOT NULL,
    egress text NOT NULL,
    cost_currency text,
    cost_input_per_million numeric(20,6),
    cost_output_per_million numeric(20,6),
    rate_limit_rpm integer,
    rate_limit_tpm integer,
    timeout_seconds numeric(8,3) NOT NULL,
    retry_class text NOT NULL,
    fallback_group text,
    evaluation_manifest_ref text,
    status text DEFAULT 'CANDIDATE'::text NOT NULL,
    approved_at timestamp with time zone,
    approved_by uuid,
    deprecated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    identity_mode text DEFAULT 'IMMUTABLE'::text NOT NULL,
    CONSTRAINT ck_model_profiles_allowed_regions CHECK (((cardinality(allowed_regions) >= 1) AND (array_to_string(allowed_regions, ','::text) ~ '^[a-z0-9][a-z0-9-]{0,31}(,[a-z0-9][a-z0-9-]{0,31})*$'::text))),
    CONSTRAINT ck_model_profiles_approval_recorded CHECK (((status = 'CANDIDATE'::text) OR ((approved_at IS NOT NULL) AND (approved_by IS NOT NULL)))),
    CONSTRAINT ck_model_profiles_capabilities CHECK (((cardinality(capabilities) >= 1) AND (capabilities <@ ARRAY['CHAT'::text, 'STRUCTURED_OUTPUT'::text, 'TOOL_CALLING'::text, 'STREAMING'::text, 'VISION'::text, 'EMBEDDING'::text]))),
    CONSTRAINT ck_model_profiles_context_window_tokens CHECK ((context_window_tokens >= 1)),
    CONSTRAINT ck_model_profiles_cost_currency CHECK ((cost_currency ~ '^[A-Z]{3}$'::text)),
    CONSTRAINT ck_model_profiles_cost_input_per_million CHECK ((cost_input_per_million >= (0)::numeric)),
    CONSTRAINT ck_model_profiles_cost_output_per_million CHECK ((cost_output_per_million >= (0)::numeric)),
    CONSTRAINT ck_model_profiles_cost_rates_complete CHECK ((((cost_currency IS NULL) = (cost_input_per_million IS NULL)) AND ((cost_currency IS NULL) = (cost_output_per_million IS NULL)))),
    CONSTRAINT ck_model_profiles_data_classifications CHECK (((cardinality(data_classifications) >= 1) AND (array_to_string(data_classifications, ','::text) ~ '^[A-Z][A-Z0-9_]{0,31}(,[A-Z][A-Z0-9_]{0,31})*$'::text))),
    CONSTRAINT ck_model_profiles_egress CHECK ((egress = ANY (ARRAY['LOCAL'::text, 'EXTERNAL'::text]))),
    CONSTRAINT ck_model_profiles_evaluation_manifest_ref CHECK (((length(evaluation_manifest_ref) >= 1) AND (length(evaluation_manifest_ref) <= 500))),
    CONSTRAINT ck_model_profiles_fallback_group CHECK ((fallback_group ~ '^[a-z][a-z0-9_.-]{0,63}$'::text)),
    CONSTRAINT ck_model_profiles_identity_binding CHECK (((((identity_mode = 'IMMUTABLE'::text) AND (pinned_model_version IS NOT NULL)) OR ((identity_mode = 'FLASH_OBSERVED'::text) AND (pinned_model_version IS NULL) AND (provider = 'deepseek'::text) AND (provider_model_id = 'deepseek-flash'::text))) IS TRUE)),
    CONSTRAINT ck_model_profiles_identity_mode CHECK ((identity_mode = ANY (ARRAY['IMMUTABLE'::text, 'FLASH_OBSERVED'::text]))),
    CONSTRAINT ck_model_profiles_max_output_tokens CHECK (((max_output_tokens >= 1) AND (max_output_tokens <= context_window_tokens))),
    CONSTRAINT ck_model_profiles_pinned_model_version CHECK ((((length(btrim(pinned_model_version)) >= 1) AND (length(btrim(pinned_model_version)) <= 100)) AND (lower(btrim(pinned_model_version)) <> ALL (ARRAY['latest'::text, 'stable'::text, 'default'::text, 'current'::text, 'newest'::text])))),
    CONSTRAINT ck_model_profiles_profile_key CHECK ((profile_key ~ '^[a-z][a-z0-9_.-]{0,63}$'::text)),
    CONSTRAINT ck_model_profiles_profile_version CHECK ((profile_version >= 1)),
    CONSTRAINT ck_model_profiles_provider CHECK (((length(provider) >= 1) AND (length(provider) <= 64))),
    CONSTRAINT ck_model_profiles_provider_model_id CHECK (((length(provider_model_id) >= 1) AND (length(provider_model_id) <= 200))),
    CONSTRAINT ck_model_profiles_rate_limit_rpm CHECK ((rate_limit_rpm >= 1)),
    CONSTRAINT ck_model_profiles_rate_limit_tpm CHECK ((rate_limit_tpm >= 1)),
    CONSTRAINT ck_model_profiles_retry_class CHECK ((retry_class = ANY (ARRAY['NONE'::text, 'BOUNDED'::text]))),
    CONSTRAINT ck_model_profiles_status CHECK ((status = ANY (ARRAY['CANDIDATE'::text, 'APPROVED'::text, 'DEPRECATED'::text, 'RETIRED'::text]))),
    CONSTRAINT ck_model_profiles_timeout_seconds CHECK ((timeout_seconds > (0)::numeric))
);

ALTER TABLE platform.model_profiles OWNER TO ai_res_owner;

CREATE TABLE platform.operation_execution_assignments (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    workflow_id text NOT NULL,
    workflow_type text NOT NULL,
    namespace text NOT NULL,
    task_queue text NOT NULL,
    workflow_contract_version integer NOT NULL,
    input_digest bytea NOT NULL,
    correlation_id uuid NOT NULL,
    allowed_actions text[] NOT NULL,
    workflow_run_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_at timestamp with time zone,
    start_admitted boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_operation_assignment_actions CHECK (((cardinality(allowed_actions) > 0) AND (array_position(allowed_actions, NULL::text) IS NULL) AND
CASE workflow_type
    WHEN 'ManagerIntakeWorkflow'::text THEN (allowed_actions <@ ARRAY['operation.acknowledge_start'::text, 'operation.record_failure'::text, 'operation.confirm_cancellation'::text, 'manager.read_input'::text, 'manager.record_draft'::text])
    WHEN 'PlanExecutionWorkflow'::text THEN (allowed_actions <@ ARRAY['operation.acknowledge_start'::text, 'operation.record_failure'::text, 'operation.confirm_cancellation'::text, 'plan.materialize_tasks'::text])
    ELSE (allowed_actions <@ ARRAY['operation.acknowledge_start'::text, 'operation.record_failure'::text, 'operation.confirm_cancellation'::text])
END)),
    CONSTRAINT ck_operation_assignment_digest CHECK ((octet_length(input_digest) = 32)),
    CONSTRAINT ck_operation_assignment_workflow_id CHECK ((workflow_id = ('operation-'::text || (operation_id)::text)))
);

ALTER TABLE ONLY platform.operation_execution_assignments FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.operation_execution_assignments OWNER TO ai_res_owner;

CREATE TABLE platform.platform_auth_events (
    id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    reason text NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    action text,
    CONSTRAINT ck_platform_auth_reason CHECK (((((reason = ANY (ARRAY['INVALID_CREDENTIAL'::text, 'EXPIRED_OR_REPLAY'::text, 'ASSIGNMENT_DENIED'::text, 'INVALID_REQUEST'::text])) AND (action IS NULL)) OR ((reason = 'AUTHORIZED'::text) AND (action = ANY (ARRAY['AUTHORIZE_START'::text, 'REGISTER_TASK'::text, 'CHECK_TASK'::text, 'AUTHORIZE_RECONCILIATION_DESCRIBE'::text, 'AUTHORIZE_BOUND_STATUS'::text, 'AUTHORIZE_BOUND_CANCEL'::text]))) OR ((action = 'AUTHORIZE_ASSIGNED_DELIVERY'::text) AND (reason = ANY (ARRAY['AUTHORIZED'::text, 'EXPIRED_OR_REPLAY'::text, 'ASSIGNMENT_DENIED'::text])))) IS TRUE))
);

ALTER TABLE ONLY platform.platform_auth_events FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.platform_auth_events OWNER TO ai_res_owner;

CREATE TABLE platform.platform_request_nonces (
    issuer text NOT NULL,
    nonce uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_platform_nonce_issuer CHECK ((issuer = ANY (ARRAY['MANAGER_RUNTIME'::text, 'TEMPORAL_AUTH_CONTROL'::text, 'OUTBOX_DISPATCHER'::text])))
);

ALTER TABLE ONLY platform.platform_request_nonces FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.platform_request_nonces OWNER TO ai_res_owner;

CREATE TABLE platform.task_issuance_receipts (
    token_digest bytea NOT NULL,
    principal text NOT NULL,
    namespace text NOT NULL,
    queue text NOT NULL,
    task_kind text NOT NULL,
    operation_id uuid NOT NULL,
    workflow_run_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT task_issuance_receipts_check CHECK ((((principal = 'MANAGER_RUNTIME'::text) AND (queue = 'ai-res-manager'::text) AND (task_kind = ANY (ARRAY['WORKFLOW'::text, 'ACTIVITY'::text]))) OR ((principal = 'WORKER_RUNTIME'::text) AND (queue = 'ai-res-workers'::text) AND (task_kind = 'ACTIVITY'::text)))),
    CONSTRAINT task_issuance_receipts_namespace_check CHECK ((namespace ~ '^[a-z0-9][a-z0-9-]{0,62}$'::text)),
    CONSTRAINT task_issuance_receipts_token_digest_check CHECK ((octet_length(token_digest) = 32))
);

ALTER TABLE ONLY platform.task_issuance_receipts FORCE ROW LEVEL SECURITY;

ALTER TABLE platform.task_issuance_receipts OWNER TO ai_res_owner;

CREATE TABLE project.notification_deliveries (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    id uuid NOT NULL,
    mandatory boolean NOT NULL,
    cutoff_at timestamp with time zone NOT NULL,
    published_at timestamp with time zone,
    CONSTRAINT ck_notification_mandatory_published CHECK (((NOT mandatory) OR (published_at IS NOT NULL)))
);

ALTER TABLE ONLY project.notification_deliveries FORCE ROW LEVEL SECURITY;

ALTER TABLE project.notification_deliveries OWNER TO ai_res_owner;

CREATE TABLE project.notification_events (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    event_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    proposal_version_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    delivery_id uuid NOT NULL,
    CONSTRAINT ck_notification_single_failure CHECK (((proposal_version_id IS NOT NULL) OR (delivery_id = event_id)))
);

ALTER TABLE ONLY project.notification_events FORCE ROW LEVEL SECURITY;

ALTER TABLE project.notification_events OWNER TO ai_res_owner;

CREATE TABLE project.notification_preferences (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    interval_seconds integer NOT NULL,
    row_version bigint NOT NULL,
    CONSTRAINT ck_notification_interval CHECK ((interval_seconds > 0)),
    CONSTRAINT ck_notification_preference_version CHECK ((row_version >= 2))
);

ALTER TABLE ONLY project.notification_preferences FORCE ROW LEVEL SECURITY;

ALTER TABLE project.notification_preferences OWNER TO ai_res_owner;

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

CREATE TABLE work.manager_interaction_attachments (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    interaction_id uuid NOT NULL,
    ordinal integer NOT NULL,
    source_version_id uuid NOT NULL,
    CONSTRAINT ck_manager_attachment_ordinal CHECK ((ordinal >= 0))
);

ALTER TABLE ONLY work.manager_interaction_attachments FORCE ROW LEVEL SECURITY;

ALTER TABLE work.manager_interaction_attachments OWNER TO ai_res_owner;

CREATE TABLE work.manager_interaction_events (
    event_id uuid NOT NULL,
    interaction_id uuid NOT NULL,
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
    CONSTRAINT manager_interaction_events_actor_type_check CHECK ((actor_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'SERVICE'::text]))),
    CONSTRAINT manager_interaction_events_aggregate_sequence_check CHECK ((aggregate_sequence > 0)),
    CONSTRAINT manager_interaction_events_aggregate_version_check CHECK ((aggregate_version > 0)),
    CONSTRAINT manager_interaction_events_event_type_check CHECK ((event_type = ANY (ARRAY['manager.interaction.received'::text, 'manager.question.proposed'::text]))),
    CONSTRAINT manager_interaction_events_schema_version_check CHECK ((schema_version = 1))
);

ALTER TABLE ONLY work.manager_interaction_events FORCE ROW LEVEL SECURITY;

ALTER TABLE work.manager_interaction_events OWNER TO ai_res_owner;

CREATE TABLE work.manager_interactions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    author_id uuid NOT NULL,
    message text NOT NULL,
    expected_response_mode text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_manager_message_length CHECK (((length(message) >= 1) AND (length(message) <= 20000))),
    CONSTRAINT ck_manager_response_mode CHECK ((expected_response_mode = ANY (ARRAY['NORMAL'::text, 'PROPOSE_PLAN'::text, 'CLARIFICATION'::text, 'REVIEW_RESULT'::text]))),
    CONSTRAINT manager_interactions_last_event_sequence_check CHECK ((last_event_sequence >= 0)),
    CONSTRAINT manager_interactions_row_version_check CHECK ((row_version > 0))
);

ALTER TABLE ONLY work.manager_interactions FORCE ROW LEVEL SECURITY;

ALTER TABLE work.manager_interactions OWNER TO ai_res_owner;

CREATE TABLE work.manager_proposal_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    interaction_id uuid NOT NULL,
    goal text,
    scope text,
    primary_question text,
    content_hash bytea NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    context_version_id uuid,
    CONSTRAINT manager_proposal_versions_content_hash_check CHECK ((octet_length(content_hash) = 32)),
    CONSTRAINT manager_proposal_versions_goal_check CHECK ((length(goal) <= 20000)),
    CONSTRAINT manager_proposal_versions_primary_question_check CHECK ((length(primary_question) <= 20000)),
    CONSTRAINT manager_proposal_versions_scope_check CHECK ((length(scope) <= 20000))
);

ALTER TABLE ONLY work.manager_proposal_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE work.manager_proposal_versions OWNER TO ai_res_owner;

CREATE TABLE work.manager_question_journal (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    sequence bigint NOT NULL,
    interaction_id uuid NOT NULL,
    question_id uuid NOT NULL,
    event_kind text NOT NULL,
    topic text,
    disposition text,
    CONSTRAINT manager_question_journal_check CHECK (((((event_kind = 'PROPOSED'::text) AND ((length(topic) >= 1) AND (length(topic) <= 128)) AND (disposition IS NULL)) OR ((event_kind = 'RESOLVED'::text) AND (topic IS NULL) AND (disposition = ANY (ARRAY['ANSWERED'::text, 'UNKNOWN'::text])))) IS TRUE)),
    CONSTRAINT manager_question_journal_sequence_check CHECK ((sequence > 0))
);

ALTER TABLE ONLY work.manager_question_journal FORCE ROW LEVEL SECURITY;

ALTER TABLE work.manager_question_journal OWNER TO ai_res_owner;

CREATE TABLE work.plan_executions (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    plan_version_id uuid NOT NULL,
    decision_id uuid NOT NULL
);

ALTER TABLE ONLY work.plan_executions FORCE ROW LEVEL SECURITY;

ALTER TABLE work.plan_executions OWNER TO ai_res_owner;

CREATE TABLE work.plan_item_tasks (
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    item_id uuid NOT NULL,
    task_id uuid NOT NULL
);

ALTER TABLE ONLY work.plan_item_tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE work.plan_item_tasks OWNER TO ai_res_owner;

CREATE TABLE work.plan_version_events (
    event_id uuid NOT NULL,
    plan_version_id uuid NOT NULL,
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
    CONSTRAINT plan_version_events_actor_type_check CHECK ((actor_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'SERVICE'::text, 'SYSTEM'::text]))),
    CONSTRAINT plan_version_events_aggregate_sequence_check CHECK ((aggregate_sequence > 0)),
    CONSTRAINT plan_version_events_aggregate_version_check CHECK ((aggregate_version > 0)),
    CONSTRAINT plan_version_events_event_type_check CHECK ((event_type = ANY (ARRAY['plan.version.proposed'::text, 'plan.version.approved'::text, 'plan.version.rejected'::text]))),
    CONSTRAINT plan_version_events_schema_version_check CHECK ((schema_version = 1))
);

ALTER TABLE ONLY work.plan_version_events FORCE ROW LEVEL SECURITY;

ALTER TABLE work.plan_version_events OWNER TO ai_res_owner;

CREATE TABLE work.plan_versions (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    version_number integer NOT NULL,
    content_hash bytea NOT NULL,
    snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT plan_versions_content_hash_check CHECK ((octet_length(content_hash) = 32)),
    CONSTRAINT plan_versions_last_event_sequence_check CHECK ((last_event_sequence >= 0)),
    CONSTRAINT plan_versions_row_version_check CHECK ((row_version > 0)),
    CONSTRAINT plan_versions_snapshot_check CHECK ((jsonb_typeof(snapshot) = 'object'::text)),
    CONSTRAINT plan_versions_version_number_check CHECK ((version_number > 0))
);

ALTER TABLE ONLY work.plan_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE work.plan_versions OWNER TO ai_res_owner;

CREATE TABLE work.plans (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    last_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT plans_last_version_check CHECK ((last_version >= 0))
);

ALTER TABLE ONLY work.plans FORCE ROW LEVEL SECURITY;

ALTER TABLE work.plans OWNER TO ai_res_owner;

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

CREATE TABLE work.task_events (
    event_id uuid NOT NULL,
    task_id uuid NOT NULL,
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
    CONSTRAINT task_events_actor_type_check CHECK ((actor_type = ANY (ARRAY['USER'::text, 'MANAGER'::text, 'SERVICE'::text, 'SYSTEM'::text]))),
    CONSTRAINT task_events_aggregate_sequence_check CHECK ((aggregate_sequence > 0)),
    CONSTRAINT task_events_aggregate_version_check CHECK ((aggregate_version > 0)),
    CONSTRAINT task_events_event_type_check CHECK ((event_type = 'task.created'::text)),
    CONSTRAINT task_events_schema_version_check CHECK ((schema_version = 1))
);

ALTER TABLE ONLY work.task_events FORCE ROW LEVEL SECURITY;

ALTER TABLE work.task_events OWNER TO ai_res_owner;

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
    last_event_sequence bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_tasks_acceptance_criteria CHECK ((jsonb_typeof(acceptance_criteria) = 'array'::text)),
    CONSTRAINT ck_tasks_derived_not_self CHECK (((derived_from_task_id IS NULL) OR (derived_from_task_id <> id))),
    CONSTRAINT ck_tasks_initiator_type CHECK ((initiator_type = ANY (ARRAY['USER'::text, 'SYSTEM'::text, 'MANAGER'::text, 'SERVICE'::text]))),
    CONSTRAINT ck_tasks_row_version CHECK ((row_version > 0)),
    CONSTRAINT ck_tasks_status CHECK ((status ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_tasks_task_type CHECK ((task_type ~ '^[A-Z][A-Z_]*$'::text)),
    CONSTRAINT ck_tasks_title CHECK (((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 240))),
    CONSTRAINT tasks_last_event_sequence_check CHECK ((last_event_sequence >= 0))
);

ALTER TABLE ONLY work.tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE work.tasks OWNER TO ai_res_owner;

ALTER TABLE ONLY agents.worker_definition_versions
    ADD CONSTRAINT pk_worker_definition_versions PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_definitions
    ADD CONSTRAINT pk_worker_definitions PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_results
    ADD CONSTRAINT pk_worker_results PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_run_events
    ADD CONSTRAINT pk_worker_run_events PRIMARY KEY (event_id);

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT pk_worker_runs PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_tool_grants
    ADD CONSTRAINT pk_worker_tool_grants PRIMARY KEY (id);

ALTER TABLE ONLY agents.worker_definition_versions
    ADD CONSTRAINT uq_worker_definition_versions_worker_definition_id_version UNIQUE (worker_definition_id, version);

ALTER TABLE ONLY agents.worker_definitions
    ADD CONSTRAINT uq_worker_definitions_worker_role UNIQUE (worker_role);

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

ALTER TABLE ONLY governance.manager_proposal_decisions
    ADD CONSTRAINT manager_proposal_decisions_proposal_version_id_key UNIQUE (proposal_version_id);

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

ALTER TABLE ONLY governance.manager_proposal_decisions
    ADD CONSTRAINT pk_manager_proposal_decisions PRIMARY KEY (id);

ALTER TABLE ONLY governance.reviews
    ADD CONSTRAINT pk_reviews PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_evaluations
    ADD CONSTRAINT pk_rule_evaluations PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_exception_revocations
    ADD CONSTRAINT pk_rule_exception_revocations PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT pk_rule_exceptions PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_runtime_controls
    ADD CONSTRAINT pk_rule_runtime_controls PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_validation_reports
    ADD CONSTRAINT pk_rule_validation_reports PRIMARY KEY (id);

ALTER TABLE ONLY governance.rule_versions
    ADD CONSTRAINT pk_rule_versions PRIMARY KEY (id);

ALTER TABLE ONLY governance.rules
    ADD CONSTRAINT pk_rules PRIMARY KEY (id);

ALTER TABLE ONLY governance.plan_version_decisions
    ADD CONSTRAINT plan_version_decisions_organization_id_project_id_plan_vers_key UNIQUE (organization_id, project_id, plan_version_id, id);

ALTER TABLE ONLY governance.plan_version_decisions
    ADD CONSTRAINT plan_version_decisions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY governance.plan_version_decisions
    ADD CONSTRAINT plan_version_decisions_plan_version_id_key UNIQUE (plan_version_id);

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

ALTER TABLE ONLY governance.rule_runtime_controls
    ADD CONSTRAINT uq_rule_controls_version_sequence UNIQUE (rule_version_id, sequence);

ALTER TABLE ONLY governance.rule_evaluations
    ADD CONSTRAINT uq_rule_evaluations_scope_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY governance.rule_exception_revocations
    ADD CONSTRAINT uq_rule_exception_revocations_exception UNIQUE (exception_id);

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT uq_rule_exceptions_scope_id UNIQUE (organization_id, project_id, id);

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

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_operation_id_key UNIQUE (operation_id);

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_organization_id_project_id_in_key UNIQUE (organization_id, project_id, interaction_id, id);

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY platform.bootstrap_state
    ADD CONSTRAINT pk_bootstrap_state PRIMARY KEY (singleton);

ALTER TABLE ONLY platform.display_number_counters
    ADD CONSTRAINT pk_display_number_counters PRIMARY KEY (organization_id, project_id, counter_kind);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT pk_idempotency_records PRIMARY KEY (id);

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT pk_llm_poc_attempts PRIMARY KEY (id);

ALTER TABLE ONLY platform.llm_poc_budget_accounts
    ADD CONSTRAINT pk_llm_poc_budget_accounts PRIMARY KEY (id);

ALTER TABLE ONLY platform.llm_poc_budget_audit
    ADD CONSTRAINT pk_llm_poc_budget_audit PRIMARY KEY (id);

ALTER TABLE ONLY platform.llm_poc_settlements
    ADD CONSTRAINT pk_llm_poc_settlements PRIMARY KEY (id);

ALTER TABLE ONLY platform.model_admission_audit
    ADD CONSTRAINT pk_model_admission_audit PRIMARY KEY (id);

ALTER TABLE ONLY platform.model_admission_calls
    ADD CONSTRAINT pk_model_admission_calls PRIMARY KEY (id);

ALTER TABLE ONLY platform.model_admission_controls
    ADD CONSTRAINT pk_model_admission_controls PRIMARY KEY (profile_id);

ALTER TABLE ONLY platform.model_admission_decisions
    ADD CONSTRAINT pk_model_admission_decisions PRIMARY KEY (decision_id);

ALTER TABLE ONLY platform.model_admission_operators
    ADD CONSTRAINT pk_model_admission_operators PRIMARY KEY (database_login, profile_id);

ALTER TABLE ONLY platform.model_admission_versions
    ADD CONSTRAINT pk_model_admission_versions PRIMARY KEY (profile_id, generation);

ALTER TABLE ONLY platform.model_profiles
    ADD CONSTRAINT pk_model_profiles PRIMARY KEY (id);

ALTER TABLE ONLY platform.operation_execution_assignments
    ADD CONSTRAINT pk_operation_execution_assignments PRIMARY KEY (id);

ALTER TABLE ONLY platform.platform_auth_events
    ADD CONSTRAINT pk_platform_auth_events PRIMARY KEY (id);

ALTER TABLE ONLY platform.platform_request_nonces
    ADD CONSTRAINT pk_platform_request_nonces PRIMARY KEY (issuer, nonce);

ALTER TABLE ONLY platform.task_issuance_receipts
    ADD CONSTRAINT task_issuance_receipts_pkey PRIMARY KEY (token_digest);

ALTER TABLE ONLY platform.operation_execution_assignments
    ADD CONSTRAINT uq_assignment_dispatch_route UNIQUE (organization_id, project_id, operation_id, id, namespace);

ALTER TABLE ONLY platform.idempotency_records
    ADD CONSTRAINT uq_idempotency_records_organization_id_scope_type_scope_id_key_ UNIQUE (organization_id, scope_type, scope_id, key_digest);

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT uq_lpa_body UNIQUE (account_id, body_sha256);

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT uq_lpa_request UNIQUE (account_id, request_ref);

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT uq_lpa_scope_id UNIQUE (account_id, id);

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT uq_lpa_sequence UNIQUE (account_id, sequence);

ALTER TABLE ONLY platform.llm_poc_budget_accounts
    ADD CONSTRAINT uq_lpba_authorization UNIQUE (authorization_key);

ALTER TABLE ONLY platform.llm_poc_settlements
    ADD CONSTRAINT uq_lps_attempt UNIQUE (attempt_id);

ALTER TABLE ONLY platform.model_admission_audit
    ADD CONSTRAINT uq_maa_call_event UNIQUE (call_id, event_type);

ALTER TABLE ONLY platform.model_admission_versions
    ADD CONSTRAINT uq_mav_binding UNIQUE (profile_id, generation, expectation_sha256);

ALTER TABLE ONLY platform.model_admission_calls
    ADD CONSTRAINT uq_mcall_request UNIQUE (profile_id, request_ref);

ALTER TABLE ONLY platform.model_admission_calls
    ADD CONSTRAINT uq_mcall_scope_id UNIQUE (profile_id, id);

ALTER TABLE ONLY platform.model_admission_calls
    ADD CONSTRAINT uq_mcall_sequence UNIQUE (profile_id, call_sequence);

ALTER TABLE ONLY platform.model_profiles
    ADD CONSTRAINT uq_model_profiles_profile_key_profile_version UNIQUE (profile_key, profile_version);

ALTER TABLE ONLY platform.operation_execution_assignments
    ADD CONSTRAINT uq_operation_execution_assignment UNIQUE (operation_id);

ALTER TABLE ONLY project.notification_deliveries
    ADD CONSTRAINT pk_notification_deliveries PRIMARY KEY (organization_id, project_id, recipient_id, id);

ALTER TABLE ONLY project.notification_events
    ADD CONSTRAINT pk_notification_events PRIMARY KEY (organization_id, project_id, recipient_id, event_id);

ALTER TABLE ONLY project.notification_preferences
    ADD CONSTRAINT pk_notification_preferences PRIMARY KEY (organization_id, project_id, recipient_id);

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

ALTER TABLE ONLY work.manager_interaction_events
    ADD CONSTRAINT manager_interaction_events_interaction_id_aggregate_sequenc_key UNIQUE (interaction_id, aggregate_sequence);

ALTER TABLE ONLY work.manager_proposal_versions
    ADD CONSTRAINT manager_proposal_versions_interaction_id_key UNIQUE (interaction_id);

ALTER TABLE ONLY work.manager_proposal_versions
    ADD CONSTRAINT manager_proposal_versions_organization_id_project_id_id_con_key UNIQUE (organization_id, project_id, id, content_hash);

ALTER TABLE ONLY work.manager_question_journal
    ADD CONSTRAINT manager_question_journal_interaction_id_event_kind_key UNIQUE (interaction_id, event_kind);

ALTER TABLE ONLY work.manager_question_journal
    ADD CONSTRAINT manager_question_journal_pkey PRIMARY KEY (organization_id, project_id, epic_id, sequence);

ALTER TABLE ONLY work.epic_events
    ADD CONSTRAINT pk_epic_events PRIMARY KEY (event_id);

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT pk_epics PRIMARY KEY (id);

ALTER TABLE ONLY work.manager_interaction_attachments
    ADD CONSTRAINT pk_manager_interaction_attachments PRIMARY KEY (interaction_id, ordinal);

ALTER TABLE ONLY work.manager_interaction_events
    ADD CONSTRAINT pk_manager_interaction_events PRIMARY KEY (event_id);

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT pk_manager_interactions PRIMARY KEY (id);

ALTER TABLE ONLY work.manager_proposal_versions
    ADD CONSTRAINT pk_manager_proposals PRIMARY KEY (id);

ALTER TABLE ONLY work.task_dependencies
    ADD CONSTRAINT pk_task_dependencies PRIMARY KEY (id);

ALTER TABLE ONLY work.task_requirements
    ADD CONSTRAINT pk_task_requirements PRIMARY KEY (task_id, requirement_id);

ALTER TABLE ONLY work.tasks
    ADD CONSTRAINT pk_tasks PRIMARY KEY (id);

ALTER TABLE ONLY work.plan_executions
    ADD CONSTRAINT plan_executions_decision_id_key UNIQUE (decision_id);

ALTER TABLE ONLY work.plan_executions
    ADD CONSTRAINT plan_executions_organization_id_project_id_operation_id_key UNIQUE (organization_id, project_id, operation_id);

ALTER TABLE ONLY work.plan_executions
    ADD CONSTRAINT plan_executions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY work.plan_item_tasks
    ADD CONSTRAINT plan_item_tasks_pkey PRIMARY KEY (operation_id, item_id);

ALTER TABLE ONLY work.plan_item_tasks
    ADD CONSTRAINT plan_item_tasks_task_id_key UNIQUE (task_id);

ALTER TABLE ONLY work.plan_version_events
    ADD CONSTRAINT plan_version_events_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY work.plan_version_events
    ADD CONSTRAINT plan_version_events_plan_version_id_aggregate_sequence_key UNIQUE (plan_version_id, aggregate_sequence);

ALTER TABLE ONLY work.plan_versions
    ADD CONSTRAINT plan_versions_organization_id_project_id_id_content_hash_key UNIQUE (organization_id, project_id, id, content_hash);

ALTER TABLE ONLY work.plan_versions
    ADD CONSTRAINT plan_versions_organization_id_project_id_id_key UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY work.plan_versions
    ADD CONSTRAINT plan_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY work.plan_versions
    ADD CONSTRAINT plan_versions_plan_id_version_number_key UNIQUE (plan_id, version_number);

ALTER TABLE ONLY work.plans
    ADD CONSTRAINT plans_organization_id_project_id_epic_id_key UNIQUE (organization_id, project_id, epic_id);

ALTER TABLE ONLY work.plans
    ADD CONSTRAINT plans_organization_id_project_id_id_key UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY work.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);

ALTER TABLE ONLY work.task_events
    ADD CONSTRAINT task_events_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY work.task_events
    ADD CONSTRAINT task_events_task_id_aggregate_sequence_key UNIQUE (task_id, aggregate_sequence);

ALTER TABLE ONLY work.epic_events
    ADD CONSTRAINT uq_epic_events_epic_id_aggregate_sequence UNIQUE (epic_id, aggregate_sequence);

ALTER TABLE ONLY work.epics
    ADD CONSTRAINT uq_epics_organization_id_project_id_id UNIQUE (organization_id, project_id, id);

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT uq_manager_interaction_operation UNIQUE (operation_id);

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT uq_manager_interaction_tenant UNIQUE (organization_id, project_id, id);

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

CREATE INDEX ix_worker_runs_worker_definition_version_id ON agents.worker_runs USING btree (worker_definition_version_id);

CREATE INDEX ix_worker_tool_grants_run ON agents.worker_tool_grants USING btree (organization_id, project_id, worker_run_id);

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

CREATE INDEX ix_outbox_protected_route ON audit.outbox_events USING btree (dispatch_namespace, created_at, aggregate_sequence) WHERE ((dispatch_namespace IS NOT NULL) AND (status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text])));

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

CREATE INDEX ix_readiness_evaluations_worker_definition_version_id ON execution.readiness_evaluations USING btree (worker_definition_version_id);

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

CREATE INDEX ix_rule_evaluations_actor_id ON governance.rule_evaluations USING btree (actor_id);

CREATE INDEX ix_rule_evaluations_actor_scope ON governance.rule_evaluations USING btree (organization_id, actor_id);

CREATE INDEX ix_rule_evaluations_context_scope ON governance.rule_evaluations USING btree (organization_id, project_id, context_version_id);

CREATE INDEX ix_rule_evaluations_context_version_id ON governance.rule_evaluations USING btree (context_version_id);

CREATE INDEX ix_rule_evaluations_previous_evaluation_id ON governance.rule_evaluations USING btree (previous_evaluation_id);

CREATE INDEX ix_rule_evaluations_previous_scope ON governance.rule_evaluations USING btree (organization_id, project_id, previous_evaluation_id);

CREATE INDEX ix_rule_exception_revocations_actor_id ON governance.rule_exception_revocations USING btree (actor_id);

CREATE INDEX ix_rule_exception_revocations_actor_scope ON governance.rule_exception_revocations USING btree (organization_id, actor_id);

CREATE INDEX ix_rule_exception_revocations_exception_scope ON governance.rule_exception_revocations USING btree (organization_id, project_id, exception_id);

CREATE INDEX ix_rule_exceptions_approved_by ON governance.rule_exceptions USING btree (approved_by);

CREATE INDEX ix_rule_exceptions_approver_scope ON governance.rule_exceptions USING btree (organization_id, approved_by);

CREATE INDEX ix_rule_exceptions_permission_version_id ON governance.rule_exceptions USING btree (permission_version_id);

CREATE INDEX ix_rule_exceptions_scope ON governance.rule_exceptions USING btree (organization_id, project_id);

CREATE INDEX ix_rule_exceptions_target_version_id ON governance.rule_exceptions USING btree (target_version_id);

CREATE INDEX ix_rule_runtime_controls_actor_id ON governance.rule_runtime_controls USING btree (actor_id);

CREATE INDEX ix_rule_runtime_controls_actor_scope ON governance.rule_runtime_controls USING btree (organization_id, actor_id);

CREATE INDEX ix_rule_runtime_controls_scope ON governance.rule_runtime_controls USING btree (organization_id, project_id);

CREATE INDEX ix_rule_validation_reports_actor_id ON governance.rule_validation_reports USING btree (actor_id);

CREATE INDEX ix_rule_validation_reports_actor_scope ON governance.rule_validation_reports USING btree (organization_id, actor_id);

CREATE INDEX ix_rule_validation_reports_proposal_version_id ON governance.rule_validation_reports USING btree (proposal_version_id);

CREATE INDEX ix_rule_validation_reports_scope ON governance.rule_validation_reports USING btree (organization_id, project_id);

CREATE INDEX ix_rule_versions_approver_user_id ON governance.rule_versions USING btree (approver_user_id);

CREATE UNIQUE INDEX uq_baseline_items_artifact ON governance.baseline_items USING btree (baseline_id, artifact_version_id) WHERE (artifact_version_id IS NOT NULL);

CREATE UNIQUE INDEX uq_baseline_items_requirement ON governance.baseline_items USING btree (baseline_id, requirement_version_id) WHERE (requirement_version_id IS NOT NULL);

CREATE UNIQUE INDEX uq_rule_versions_one_approved ON governance.rule_versions USING btree (rule_id) WHERE (status = 'APPROVED'::text);

CREATE UNIQUE INDEX uq_rules_scope_rule_key ON governance.rules USING btree (level, COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), rule_key);

CREATE INDEX ix_sessions_user_id_active ON iam.sessions USING btree (user_id) WHERE (revoked_at IS NULL);

CREATE UNIQUE INDEX ux_mfa_factors_active_per_user ON iam.mfa_factors USING btree (user_id, factor_type) WHERE (status <> 'REVOKED'::text);

CREATE INDEX ix_extraction_records_operation_id ON knowledge.extraction_records USING btree (operation_id) WHERE (operation_id IS NOT NULL);

CREATE INDEX ix_extraction_records_source_version_id ON knowledge.extraction_records USING btree (source_version_id);

CREATE INDEX ix_manager_operations_notification_candidates ON operations.operations USING btree (organization_id, project_id, initiator_id, id) WHERE ((operation_type = 'MANAGER_MESSAGE'::text) AND (status = ANY (ARRAY['FAILED'::text, 'SUCCEEDED'::text])));

CREATE INDEX ix_operation_events_operation_id_occurred_at ON operations.operation_events USING btree (operation_id, occurred_at DESC);

CREATE INDEX ix_operations_active_status ON operations.operations USING btree (status, updated_at) WHERE (status <> ALL (ARRAY['SUCCEEDED'::text, 'PARTIALLY_SUCCEEDED'::text, 'FAILED'::text, 'CANCELLED'::text]));

CREATE INDEX ix_operations_parent_operation_id ON operations.operations USING btree (parent_operation_id) WHERE (parent_operation_id IS NOT NULL);

CREATE INDEX ix_operations_project_id_created_at ON operations.operations USING btree (project_id, created_at DESC);

CREATE INDEX ix_bootstrap_state_organization_id ON platform.bootstrap_state USING btree (organization_id);

CREATE INDEX ix_idempotency_records_expires_at ON platform.idempotency_records USING btree (expires_at);

CREATE UNIQUE INDEX ix_lpa_single_flight ON platform.llm_poc_attempts USING btree (account_id) WHERE (state = ANY (ARRAY['RESERVED'::text, 'CLAIMED'::text]));

CREATE INDEX ix_lpau_attempt_scope ON platform.llm_poc_budget_audit USING btree (account_id, attempt_id);

CREATE INDEX ix_lps_attempt_scope ON platform.llm_poc_settlements USING btree (account_id, attempt_id);

CREATE INDEX ix_maa_call_scope ON platform.model_admission_audit USING btree (profile_id, call_id);

CREATE INDEX ix_mad_profile ON platform.model_admission_decisions USING btree (profile_id, generation);

CREATE INDEX ix_mad_subject ON platform.model_admission_decisions USING btree (organization_id, user_id);

CREATE INDEX ix_mao_profile ON platform.model_admission_operators USING btree (profile_id);

CREATE INDEX ix_mao_subject ON platform.model_admission_operators USING btree (organization_id, user_id);

CREATE UNIQUE INDEX ix_mcall_single_flight ON platform.model_admission_calls USING btree (profile_id) WHERE (status = 'IN_FLIGHT'::text);

CREATE INDEX ix_model_profiles_approved_by ON platform.model_profiles USING btree (approved_by);

CREATE INDEX ix_notification_deliveries_mandatory ON project.notification_deliveries USING btree (organization_id, project_id, recipient_id, published_at DESC, id DESC) WHERE mandatory;

CREATE INDEX ix_notification_deliveries_published ON project.notification_deliveries USING btree (organization_id, project_id, recipient_id, published_at DESC, id DESC) WHERE (published_at IS NOT NULL);

CREATE INDEX ix_notification_events_delivery ON project.notification_events USING btree (organization_id, project_id, recipient_id, delivery_id, occurred_at DESC, event_id DESC);

CREATE INDEX ix_project_events_project_id_occurred_at ON project.project_events USING btree (project_id, occurred_at DESC);

CREATE UNIQUE INDEX uq_notification_active_digest ON project.notification_deliveries USING btree (organization_id, project_id, recipient_id) WHERE (published_at IS NULL);

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

CREATE INDEX ix_manager_attachment_version ON work.manager_interaction_attachments USING btree (organization_id, project_id, source_version_id);

CREATE INDEX ix_manager_interactions_epic ON work.manager_interactions USING btree (organization_id, project_id, epic_id, created_at, id);

CREATE INDEX ix_manager_interactions_notification_recipients ON work.manager_interactions USING btree (organization_id, project_id, author_id);

CREATE INDEX ix_task_dependencies_depends_on_task_id ON work.task_dependencies USING btree (depends_on_task_id);

CREATE INDEX ix_task_requirements_requirement_id ON work.task_requirements USING btree (requirement_id);

CREATE INDEX ix_tasks_epic_id ON work.tasks USING btree (epic_id);

CREATE INDEX ix_tasks_operation_id_status_priority ON work.tasks USING btree (operation_id, status, priority);

CREATE TRIGGER trg_worker_definition_versions_guard BEFORE INSERT OR DELETE OR UPDATE ON agents.worker_definition_versions FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_definition_version();

CREATE TRIGGER trg_worker_definition_versions_no_truncate BEFORE TRUNCATE ON agents.worker_definition_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_worker_definitions_guard BEFORE DELETE OR UPDATE ON agents.worker_definitions FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_definition();

CREATE TRIGGER trg_worker_definitions_no_truncate BEFORE TRUNCATE ON agents.worker_definitions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

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

CREATE TRIGGER trg_assigned_start_quarantine BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION audit.guard_assigned_start_quarantine();

CREATE TRIGGER trg_audit_events_append_only BEFORE DELETE OR UPDATE ON audit.audit_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit.audit_events FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_inbox_checkpoints_advance BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION audit.assert_checkpoint_advances();

CREATE TRIGGER trg_inbox_checkpoints_immutable_columns BEFORE UPDATE ON audit.inbox_checkpoints FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('consumer_name', 'aggregate_type', 'aggregate_id');

CREATE TRIGGER trg_inbox_messages_immutable_columns BEFORE UPDATE ON audit.inbox_messages FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'consumer_name', 'event_id', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'payload_hash', 'received_at');

CREATE TRIGGER trg_outbox_dispatch_route_immutable BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('dispatch_assignment_id', 'dispatch_namespace');

CREATE TRIGGER trg_outbox_events_immutable_columns BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'event_id', 'destination', 'aggregate_type', 'aggregate_id', 'aggregate_sequence', 'event_type', 'schema_version', 'envelope', 'created_at');

CREATE CONSTRAINT TRIGGER trg_outbox_events_matches_event AFTER INSERT ON audit.outbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit.assert_outbox_matches_event();

CREATE TRIGGER trg_outbox_events_replay_count_step BEFORE UPDATE ON audit.outbox_events FOR EACH ROW EXECUTE FUNCTION audit.assert_replay_count_step();

CREATE TRIGGER trg_context_package_items_append_only BEFORE DELETE OR UPDATE ON context.context_package_items FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_context_package_items_complete AFTER INSERT ON context.context_package_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('context_package_version_id');

CREATE TRIGGER trg_context_package_items_guard_insert BEFORE INSERT ON context.context_package_items FOR EACH ROW EXECUTE FUNCTION context.guard_item_insert();

CREATE TRIGGER trg_context_package_items_no_truncate BEFORE TRUNCATE ON context.context_package_items FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_context_package_versions_append_only BEFORE DELETE OR UPDATE ON context.context_package_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_context_package_versions_complete AFTER INSERT ON context.context_package_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('id');

CREATE TRIGGER trg_context_package_versions_creation_transaction BEFORE INSERT ON context.context_package_versions FOR EACH ROW EXECUTE FUNCTION context.stamp_creation_transaction();

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

CREATE TRIGGER trg_manager_proposal_decisions_immutable BEFORE DELETE OR UPDATE ON governance.manager_proposal_decisions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_plan_version_decisions_immutable BEFORE DELETE OR UPDATE ON governance.plan_version_decisions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_reviews_append_only BEFORE DELETE OR UPDATE ON governance.reviews FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_reviews_no_truncate BEFORE TRUNCATE ON governance.reviews FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_controls_scope BEFORE INSERT ON governance.rule_runtime_controls FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();

CREATE TRIGGER trg_rule_evaluations_append_only BEFORE DELETE OR UPDATE ON governance.rule_evaluations FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_evaluations_no_truncate BEFORE TRUNCATE ON governance.rule_evaluations FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_exception_revocations_append_only BEFORE DELETE OR UPDATE ON governance.rule_exception_revocations FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_exception_revocations_no_truncate BEFORE TRUNCATE ON governance.rule_exception_revocations FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_exceptions_append_only BEFORE DELETE OR UPDATE ON governance.rule_exceptions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_exceptions_no_truncate BEFORE TRUNCATE ON governance.rule_exceptions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_exceptions_scope BEFORE INSERT ON governance.rule_exceptions FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();

CREATE TRIGGER trg_rule_runtime_controls_append_only BEFORE DELETE OR UPDATE ON governance.rule_runtime_controls FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_runtime_controls_no_truncate BEFORE TRUNCATE ON governance.rule_runtime_controls FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_validation_reports_append_only BEFORE DELETE OR UPDATE ON governance.rule_validation_reports FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_validation_reports_no_truncate BEFORE TRUNCATE ON governance.rule_validation_reports FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_rule_validation_scope BEFORE INSERT ON governance.rule_validation_reports FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();

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

CREATE TRIGGER trg_llm_poc_attempts_append_only BEFORE DELETE ON platform.llm_poc_attempts FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_attempts_no_truncate BEFORE TRUNCATE ON platform.llm_poc_attempts FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_budget_accounts_append_only BEFORE DELETE ON platform.llm_poc_budget_accounts FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_budget_accounts_no_truncate BEFORE TRUNCATE ON platform.llm_poc_budget_accounts FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_budget_audit_append_only BEFORE DELETE OR UPDATE ON platform.llm_poc_budget_audit FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_budget_audit_no_truncate BEFORE TRUNCATE ON platform.llm_poc_budget_audit FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_settlements_append_only BEFORE DELETE OR UPDATE ON platform.llm_poc_settlements FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_llm_poc_settlements_no_truncate BEFORE TRUNCATE ON platform.llm_poc_settlements FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_lpa_guard BEFORE INSERT OR UPDATE ON platform.llm_poc_attempts FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_attempt();

CREATE TRIGGER trg_lpba_guard BEFORE UPDATE ON platform.llm_poc_budget_accounts FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_account();

CREATE TRIGGER trg_lps_finish AFTER INSERT ON platform.llm_poc_settlements FOR EACH ROW EXECUTE FUNCTION platform.finish_llm_poc_settlement();

CREATE TRIGGER trg_lps_guard BEFORE INSERT ON platform.llm_poc_settlements FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_settlement();

CREATE TRIGGER trg_mac_guard BEFORE UPDATE ON platform.model_admission_controls FOR EACH ROW EXECUTE FUNCTION platform.guard_model_admission_control();

CREATE TRIGGER trg_mac_reapproval_generation BEFORE UPDATE ON platform.model_admission_controls FOR EACH ROW EXECUTE FUNCTION platform.guard_admission_reapproval_generation();

CREATE TRIGGER trg_manager_epic_context_immutable BEFORE DELETE OR UPDATE ON platform.manager_epic_context_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_manager_epic_context_no_truncate BEFORE TRUNCATE ON platform.manager_epic_context_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_mcall_guard BEFORE INSERT OR UPDATE ON platform.model_admission_calls FOR EACH ROW EXECUTE FUNCTION platform.guard_model_admission_call();

CREATE TRIGGER trg_model_admission_audit_append_only BEFORE DELETE OR UPDATE ON platform.model_admission_audit FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_audit_no_truncate BEFORE TRUNCATE ON platform.model_admission_audit FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_calls_no_delete BEFORE DELETE ON platform.model_admission_calls FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_calls_no_truncate BEFORE TRUNCATE ON platform.model_admission_calls FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_controls_no_delete BEFORE DELETE ON platform.model_admission_controls FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_controls_no_truncate BEFORE TRUNCATE ON platform.model_admission_controls FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_decisions_append_only BEFORE DELETE OR UPDATE ON platform.model_admission_decisions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_decisions_no_truncate BEFORE TRUNCATE ON platform.model_admission_decisions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_operators_append_only BEFORE DELETE OR UPDATE ON platform.model_admission_operators FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_operators_no_truncate BEFORE TRUNCATE ON platform.model_admission_operators FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_versions_append_only BEFORE DELETE OR UPDATE ON platform.model_admission_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_admission_versions_no_truncate BEFORE TRUNCATE ON platform.model_admission_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_model_profiles_guard BEFORE INSERT OR DELETE OR UPDATE ON platform.model_profiles FOR EACH ROW EXECUTE FUNCTION platform.guard_model_profile();

CREATE TRIGGER trg_model_profiles_lifecycle_fence BEFORE UPDATE ON platform.model_profiles FOR EACH ROW EXECUTE FUNCTION platform.fence_model_profile_lifecycle();

CREATE TRIGGER trg_model_profiles_no_truncate BEFORE TRUNCATE ON platform.model_profiles FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_operation_assignment_binding BEFORE UPDATE ON platform.operation_execution_assignments FOR EACH ROW EXECUTE FUNCTION platform.keep_operation_assignment_binding();

CREATE TRIGGER trg_task_issuance_receipts_immutable BEFORE DELETE OR UPDATE ON platform.task_issuance_receipts FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_notification_delivery_publish_once BEFORE UPDATE ON project.notification_deliveries FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('published_at');

CREATE TRIGGER trg_notification_events_immutable BEFORE DELETE OR UPDATE ON project.notification_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

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

CREATE TRIGGER trg_manager_interaction_attachments_immutable BEFORE DELETE OR UPDATE ON work.manager_interaction_attachments FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_manager_interaction_attachments_sealed BEFORE INSERT ON work.manager_interaction_attachments FOR EACH ROW EXECUTE FUNCTION work.require_unsealed_interaction();

CREATE TRIGGER trg_manager_interaction_body_immutable BEFORE UPDATE ON work.manager_interactions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'epic_id', 'operation_id', 'author_id', 'message', 'expected_response_mode', 'created_at');

CREATE TRIGGER trg_manager_interaction_events_immutable BEFORE DELETE OR UPDATE ON work.manager_interaction_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_manager_interaction_events_sequence AFTER INSERT ON work.manager_interaction_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('interaction_id', 'work.manager_interactions', 'work.manager_interaction_events', 'interaction_id');

CREATE TRIGGER trg_manager_interactions_no_delete BEFORE DELETE ON work.manager_interactions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_manager_interactions_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.manager_interactions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'work.manager_interactions', 'work.manager_interaction_events', 'interaction_id');

CREATE TRIGGER trg_manager_proposal_versions_immutable BEFORE DELETE OR UPDATE ON work.manager_proposal_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_manager_question_journal_immutable BEFORE DELETE OR UPDATE ON work.manager_question_journal FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_plan_executions_immutable BEFORE DELETE OR UPDATE ON work.plan_executions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_plan_item_tasks_immutable BEFORE DELETE OR UPDATE ON work.plan_item_tasks FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE TRIGGER trg_plan_version_events_immutable BEFORE DELETE OR UPDATE ON work.plan_version_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_plan_version_events_sequence AFTER INSERT ON work.plan_version_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('plan_version_id', 'work.plan_versions', 'work.plan_version_events', 'plan_version_id');

CREATE TRIGGER trg_plan_versions_content_immutable BEFORE UPDATE ON work.plan_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'plan_id', 'version_number', 'content_hash', 'snapshot', 'created_at');

CREATE TRIGGER trg_plan_versions_no_delete BEFORE DELETE ON work.plan_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_plan_versions_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.plan_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'work.plan_versions', 'work.plan_version_events', 'plan_version_id');

CREATE TRIGGER trg_task_events_immutable BEFORE DELETE OR UPDATE ON work.task_events FOR EACH ROW EXECUTE FUNCTION platform.reject_modification();

CREATE CONSTRAINT TRIGGER trg_task_events_sequence AFTER INSERT ON work.task_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('task_id', 'work.tasks', 'work.task_events', 'task_id');

CREATE CONSTRAINT TRIGGER trg_task_platform_plan_item AFTER INSERT ON work.tasks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN ((CURRENT_USER = 'ai_res_platform_api'::name)) EXECUTE FUNCTION work.require_platform_plan_item();

CREATE TRIGGER trg_tasks_immutable_columns BEFORE UPDATE ON work.tasks FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('id', 'organization_id', 'project_id', 'operation_id', 'epic_id', 'derived_from_task_id', 'initiator_type', 'initiator_id', 'created_at');

CREATE TRIGGER trg_tasks_require_open_operation BEFORE INSERT ON work.tasks FOR EACH ROW EXECUTE FUNCTION work.require_open_operation();

CREATE CONSTRAINT TRIGGER trg_tasks_sequence AFTER INSERT OR UPDATE OF last_event_sequence ON work.tasks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.assert_event_sequence_contiguous('id', 'work.tasks', 'work.task_events', 'task_id');

CREATE TRIGGER trg_tasks_touch BEFORE UPDATE ON work.tasks FOR EACH ROW EXECUTE FUNCTION platform.touch_row();

ALTER TABLE ONLY agents.worker_definition_versions
    ADD CONSTRAINT fk_worker_definition_versions_worker_definition_id FOREIGN KEY (worker_definition_id) REFERENCES agents.worker_definitions(id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY agents.worker_runs
    ADD CONSTRAINT fk_worker_runs_worker_definition_version_id FOREIGN KEY (worker_definition_version_id) REFERENCES agents.worker_definition_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY agents.worker_tool_grants
    ADD CONSTRAINT fk_worker_tool_grant_run FOREIGN KEY (organization_id, project_id, worker_run_id) REFERENCES agents.worker_runs(organization_id, project_id, id) ON DELETE RESTRICT;

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
    ADD CONSTRAINT fk_outbox_dispatch_route FOREIGN KEY (organization_id, project_id, aggregate_id, dispatch_assignment_id, dispatch_namespace) REFERENCES platform.operation_execution_assignments(organization_id, project_id, operation_id, id, namespace) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

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
    ADD CONSTRAINT fk_readiness_evaluations_worker_definition_version_id FOREIGN KEY (worker_definition_version_id) REFERENCES agents.worker_definition_versions(id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY governance.rule_runtime_controls
    ADD CONSTRAINT fk_rule_controls_actor FOREIGN KEY (organization_id, actor_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_runtime_controls
    ADD CONSTRAINT fk_rule_controls_scope FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_runtime_controls
    ADD CONSTRAINT fk_rule_controls_version FOREIGN KEY (rule_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_evaluations
    ADD CONSTRAINT fk_rule_evaluations_actor FOREIGN KEY (organization_id, actor_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_evaluations
    ADD CONSTRAINT fk_rule_evaluations_context FOREIGN KEY (organization_id, project_id, context_version_id) REFERENCES context.context_package_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_evaluations
    ADD CONSTRAINT fk_rule_evaluations_previous FOREIGN KEY (organization_id, project_id, previous_evaluation_id) REFERENCES governance.rule_evaluations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exception_revocations
    ADD CONSTRAINT fk_rule_exception_revocations_actor FOREIGN KEY (organization_id, actor_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exception_revocations
    ADD CONSTRAINT fk_rule_exception_revocations_exception FOREIGN KEY (organization_id, project_id, exception_id) REFERENCES governance.rule_exceptions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT fk_rule_exceptions_approver FOREIGN KEY (organization_id, approved_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT fk_rule_exceptions_permission FOREIGN KEY (permission_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT fk_rule_exceptions_scope FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_exceptions
    ADD CONSTRAINT fk_rule_exceptions_target FOREIGN KEY (target_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_validation_reports
    ADD CONSTRAINT fk_rule_validation_actor FOREIGN KEY (organization_id, actor_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_validation_reports
    ADD CONSTRAINT fk_rule_validation_proposal FOREIGN KEY (proposal_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.rule_validation_reports
    ADD CONSTRAINT fk_rule_validation_scope FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY governance.manager_proposal_decisions
    ADD CONSTRAINT manager_proposal_decisions_organization_id_approver_id_fkey FOREIGN KEY (organization_id, approver_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.manager_proposal_decisions
    ADD CONSTRAINT manager_proposal_decisions_organization_id_project_id_prop_fkey FOREIGN KEY (organization_id, project_id, proposal_version_id, content_hash) REFERENCES work.manager_proposal_versions(organization_id, project_id, id, content_hash) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.plan_version_decisions
    ADD CONSTRAINT plan_version_decisions_organization_id_approver_id_fkey FOREIGN KEY (organization_id, approver_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY governance.plan_version_decisions
    ADD CONSTRAINT plan_version_decisions_organization_id_project_id_plan_ver_fkey FOREIGN KEY (organization_id, project_id, plan_version_id, content_hash) REFERENCES work.plan_versions(organization_id, project_id, id, content_hash) ON DELETE RESTRICT;

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

ALTER TABLE ONLY platform.llm_poc_attempts
    ADD CONSTRAINT fk_lpa_account FOREIGN KEY (account_id) REFERENCES platform.llm_poc_budget_accounts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.llm_poc_budget_audit
    ADD CONSTRAINT fk_lpau_account FOREIGN KEY (account_id) REFERENCES platform.llm_poc_budget_accounts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.llm_poc_budget_audit
    ADD CONSTRAINT fk_lpau_attempt FOREIGN KEY (account_id, attempt_id) REFERENCES platform.llm_poc_attempts(account_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.llm_poc_settlements
    ADD CONSTRAINT fk_lps_attempt FOREIGN KEY (account_id, attempt_id) REFERENCES platform.llm_poc_attempts(account_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_audit
    ADD CONSTRAINT fk_maa_call FOREIGN KEY (profile_id, call_id) REFERENCES platform.model_admission_calls(profile_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_controls
    ADD CONSTRAINT fk_mac_generation FOREIGN KEY (profile_id, current_generation) REFERENCES platform.model_admission_versions(profile_id, generation) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_decisions
    ADD CONSTRAINT fk_mad_generation FOREIGN KEY (profile_id, generation) REFERENCES platform.model_admission_versions(profile_id, generation) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_decisions
    ADD CONSTRAINT fk_mad_profile FOREIGN KEY (profile_id) REFERENCES platform.model_profiles(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_decisions
    ADD CONSTRAINT fk_mad_subject FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_operators
    ADD CONSTRAINT fk_mao_profile FOREIGN KEY (profile_id) REFERENCES platform.model_profiles(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_operators
    ADD CONSTRAINT fk_mao_subject FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_versions
    ADD CONSTRAINT fk_mav_profile FOREIGN KEY (profile_id) REFERENCES platform.model_profiles(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_admission_calls
    ADD CONSTRAINT fk_mcall_generation FOREIGN KEY (profile_id, generation, expected_sha256) REFERENCES platform.model_admission_versions(profile_id, generation, expectation_sha256) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.model_profiles
    ADD CONSTRAINT fk_model_profiles_approved_by_users FOREIGN KEY (approved_by) REFERENCES iam.users(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.operation_execution_assignments
    ADD CONSTRAINT fk_operation_assignment_operation FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES platform.operation_execution_assignments(id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_organization_id_project_id_i_fkey FOREIGN KEY (organization_id, project_id, interaction_id) REFERENCES work.manager_interactions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY platform.manager_epic_context_versions
    ADD CONSTRAINT manager_epic_context_versions_organization_id_project_id_o_fkey FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_deliveries
    ADD CONSTRAINT fk_notification_delivery_project FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_deliveries
    ADD CONSTRAINT fk_notification_delivery_recipient FOREIGN KEY (organization_id, recipient_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_events
    ADD CONSTRAINT fk_notification_event_delivery FOREIGN KEY (organization_id, project_id, recipient_id, delivery_id) REFERENCES project.notification_deliveries(organization_id, project_id, recipient_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_events
    ADD CONSTRAINT fk_notification_event_operation FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_events
    ADD CONSTRAINT fk_notification_event_proposal FOREIGN KEY (proposal_version_id) REFERENCES work.manager_proposal_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_events
    ADD CONSTRAINT fk_notification_event_source FOREIGN KEY (event_id) REFERENCES operations.operation_events(event_id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_preferences
    ADD CONSTRAINT fk_notification_preference_project FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY project.notification_preferences
    ADD CONSTRAINT fk_notification_preference_recipient FOREIGN KEY (organization_id, recipient_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY work.manager_interaction_attachments
    ADD CONSTRAINT fk_manager_attachment_interaction FOREIGN KEY (organization_id, project_id, interaction_id) REFERENCES work.manager_interactions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_interaction_attachments
    ADD CONSTRAINT fk_manager_attachment_version FOREIGN KEY (organization_id, project_id, source_version_id) REFERENCES sources.source_versions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT fk_manager_interaction_author FOREIGN KEY (organization_id, author_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT fk_manager_interaction_epic FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_interactions
    ADD CONSTRAINT fk_manager_interaction_operation FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

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

ALTER TABLE ONLY work.manager_interaction_events
    ADD CONSTRAINT manager_interaction_events_interaction_id_fkey FOREIGN KEY (interaction_id) REFERENCES work.manager_interactions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_proposal_versions
    ADD CONSTRAINT manager_proposal_versions_organization_id_project_id_inte_fkey1 FOREIGN KEY (organization_id, project_id, interaction_id, context_version_id) REFERENCES platform.manager_epic_context_versions(organization_id, project_id, interaction_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_proposal_versions
    ADD CONSTRAINT manager_proposal_versions_organization_id_project_id_inter_fkey FOREIGN KEY (organization_id, project_id, interaction_id) REFERENCES work.manager_interactions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_question_journal
    ADD CONSTRAINT manager_question_journal_organization_id_project_id_epic_i_fkey FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.manager_question_journal
    ADD CONSTRAINT manager_question_journal_organization_id_project_id_intera_fkey FOREIGN KEY (organization_id, project_id, interaction_id) REFERENCES work.manager_interactions(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_executions
    ADD CONSTRAINT plan_executions_organization_id_project_id_operation_id_fkey FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_executions
    ADD CONSTRAINT plan_executions_organization_id_project_id_plan_version_id_fkey FOREIGN KEY (organization_id, project_id, plan_version_id, decision_id) REFERENCES governance.plan_version_decisions(organization_id, project_id, plan_version_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_item_tasks
    ADD CONSTRAINT plan_item_tasks_organization_id_project_id_operation_id_fkey FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES work.plan_executions(organization_id, project_id, operation_id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_item_tasks
    ADD CONSTRAINT plan_item_tasks_organization_id_project_id_operation_id_ta_fkey FOREIGN KEY (organization_id, project_id, operation_id, task_id) REFERENCES work.tasks(organization_id, project_id, operation_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_version_events
    ADD CONSTRAINT plan_version_events_plan_version_id_fkey FOREIGN KEY (plan_version_id) REFERENCES work.plan_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plan_versions
    ADD CONSTRAINT plan_versions_organization_id_project_id_plan_id_fkey FOREIGN KEY (organization_id, project_id, plan_id) REFERENCES work.plans(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.plans
    ADD CONSTRAINT plans_organization_id_project_id_epic_id_fkey FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY work.task_events
    ADD CONSTRAINT task_events_task_id_fkey FOREIGN KEY (task_id) REFERENCES work.tasks(id) ON DELETE RESTRICT;

CREATE POLICY p_worker_results_owner_migration ON agents.worker_results TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_results_tenant_scope ON agents.worker_results TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_worker_run_events_owner_migration ON agents.worker_run_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_run_events_tenant_scope ON agents.worker_run_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = worker_run_events.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM agents.worker_runs wr
  WHERE ((wr.id = worker_run_events.worker_run_id) AND (wr.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (wr.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_worker_runs_owner_migration ON agents.worker_runs TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_runs_platform_bound ON agents.worker_runs FOR SELECT TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_worker_runs_tenant_scope ON agents.worker_runs TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_worker_tool_grants_migration ON agents.worker_tool_grants TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_worker_tool_grants_tenant ON agents.worker_tool_grants TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE agents.worker_results ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_run_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents.worker_tool_grants ENABLE ROW LEVEL SECURITY;

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

CREATE POLICY p_audit_platform_bound ON audit.audit_events FOR INSERT TO ai_res_platform_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (object_type = 'OPERATION'::text) AND (object_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_inbox_checkpoints_consumer_all ON audit.inbox_checkpoints TO ai_res_consumer_group USING (true) WITH CHECK (true);

CREATE POLICY p_inbox_checkpoints_owner_migration ON audit.inbox_checkpoints TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_inbox_messages_consumer_all ON audit.inbox_messages TO ai_res_consumer_group USING (true) WITH CHECK (true);

CREATE POLICY p_inbox_messages_owner_migration ON audit.inbox_messages TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_outbox_events_api_insert ON audit.outbox_events FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_outbox_events_dispatcher_select ON audit.outbox_events FOR SELECT TO ai_res_outbox_group USING (true);

CREATE POLICY p_outbox_events_dispatcher_update ON audit.outbox_events FOR UPDATE TO ai_res_outbox_group USING (true) WITH CHECK (true);

CREATE POLICY p_outbox_events_owner_migration ON audit.outbox_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_outbox_platform_bound ON audit.outbox_events FOR INSERT TO ai_res_platform_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (aggregate_type = 'OPERATION'::text) AND (aggregate_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_outbox_platform ON audit.outbox_events FOR INSERT TO ai_res_platform_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (aggregate_type = 'TASK'::text) AND (EXISTS ( SELECT 1
   FROM work.tasks t
  WHERE ((t.id = outbox_events.aggregate_id) AND (t.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))))));

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

ALTER TABLE governance.manager_proposal_decisions ENABLE ROW LEVEL SECURITY;

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

CREATE POLICY p_manager_proposal_decisions_migration ON governance.manager_proposal_decisions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_proposal_decisions_tenant ON governance.manager_proposal_decisions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_plan_version_decisions_migration ON governance.plan_version_decisions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plan_version_decisions_platform ON governance.plan_version_decisions FOR SELECT TO ai_res_platform_api_group USING (((current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (EXISTS ( SELECT 1
   FROM work.plan_executions e
  WHERE (e.decision_id = plan_version_decisions.id)))));

CREATE POLICY p_plan_version_decisions_tenant ON governance.plan_version_decisions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_reviews_owner_migration ON governance.reviews TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_reviews_tenant_scope ON governance.reviews TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_rule_evaluations_insert ON governance.rule_evaluations FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_evaluations_owner_migration ON governance.rule_evaluations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_evaluations_select ON governance.rule_evaluations FOR SELECT TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_exception_revocations_insert ON governance.rule_exception_revocations FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_exception_revocations_owner_migration ON governance.rule_exception_revocations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_exception_revocations_select ON governance.rule_exception_revocations FOR SELECT TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_exceptions_insert ON governance.rule_exceptions FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_exceptions_owner_migration ON governance.rule_exceptions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_exceptions_select ON governance.rule_exceptions FOR SELECT TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_runtime_controls_insert ON governance.rule_runtime_controls FOR INSERT TO ai_res_api_group WITH CHECK (((level <> 'SYSTEM'::text) AND ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rule_runtime_controls_owner_migration ON governance.rule_runtime_controls TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_runtime_controls_select ON governance.rule_runtime_controls FOR SELECT TO ai_res_api_group USING (((level = 'SYSTEM'::text) OR ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rule_validation_reports_insert ON governance.rule_validation_reports FOR INSERT TO ai_res_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_validation_reports_owner_migration ON governance.rule_validation_reports TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_validation_reports_select ON governance.rule_validation_reports FOR SELECT TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_versions_insert ON governance.rule_versions FOR INSERT TO ai_res_api_group WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rule_versions_owner_migration ON governance.rule_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rule_versions_read ON governance.rule_versions FOR SELECT TO ai_res_api_group USING (((level = 'SYSTEM'::text) OR ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rule_versions_update ON governance.rule_versions FOR UPDATE TO ai_res_api_group USING (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rules_insert ON governance.rules FOR INSERT TO ai_res_api_group WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_rules_owner_migration ON governance.rules TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_rules_read ON governance.rules FOR SELECT TO ai_res_api_group USING (((level = 'SYSTEM'::text) OR ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_rules_update ON governance.rules FOR UPDATE TO ai_res_api_group USING (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((level <> 'SYSTEM'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND ((project_id IS NULL) OR (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

ALTER TABLE governance.plan_version_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.reviews ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_evaluations ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_exception_revocations ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_exceptions ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_runtime_controls ENABLE ROW LEVEL SECURITY;

ALTER TABLE governance.rule_validation_reports ENABLE ROW LEVEL SECURITY;

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

CREATE POLICY p_operation_event_sequence_platform ON operations.operation_events FOR SELECT TO ai_res_platform_api_group USING (((operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid) AND (EXISTS ( SELECT 1
   FROM operations.operations o
  WHERE (o.id = operation_events.operation_id)))));

CREATE POLICY p_operation_events_owner_migration ON operations.operation_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_operation_events_platform_bound ON operations.operation_events FOR INSERT TO ai_res_platform_api_group WITH CHECK ((operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid));

CREATE POLICY p_operation_events_tenant_scope ON operations.operation_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM operations.operations o
  WHERE ((o.id = operation_events.operation_id) AND (o.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (o.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM operations.operations o
  WHERE ((o.id = operation_events.operation_id) AND (o.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (o.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_operations_owner_migration ON operations.operations TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_operations_platform_bound ON operations.operations TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)));

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

ALTER TABLE platform.llm_poc_attempts ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_budget_accounts ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_budget_audit ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.llm_poc_settlements ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.manager_epic_context_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_audit ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_calls ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_controls ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_operators ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.model_admission_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.operation_execution_assignments ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_bootstrap_state_owner_migration ON platform.bootstrap_state TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_bootstrap_state_tenant_scope ON platform.bootstrap_state TO ai_res_api_group USING ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid)) WITH CHECK ((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid));

CREATE POLICY p_display_number_counters_owner_migration ON platform.display_number_counters TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_display_number_counters_tenant_scope ON platform.display_number_counters TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_idempotency_records_owner_migration ON platform.idempotency_records TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_idempotency_records_tenant_scope ON platform.idempotency_records TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (NOT (project_id IS DISTINCT FROM (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))));

CREATE POLICY p_llm_poc_attempts_insert ON platform.llm_poc_attempts FOR INSERT TO ai_res_api_group WITH CHECK ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_attempts_owner_migration ON platform.llm_poc_attempts TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_llm_poc_attempts_read ON platform.llm_poc_attempts FOR SELECT TO ai_res_api_group USING ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_attempts_update ON platform.llm_poc_attempts FOR UPDATE TO ai_res_api_group USING ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid)) WITH CHECK ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_budget_accounts_owner_migration ON platform.llm_poc_budget_accounts TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_llm_poc_budget_accounts_read ON platform.llm_poc_budget_accounts FOR SELECT TO ai_res_api_group USING ((id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_budget_accounts_update ON platform.llm_poc_budget_accounts FOR UPDATE TO ai_res_api_group USING ((id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid)) WITH CHECK ((id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_budget_audit_insert ON platform.llm_poc_budget_audit FOR INSERT TO ai_res_api_group WITH CHECK ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_budget_audit_owner_migration ON platform.llm_poc_budget_audit TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_llm_poc_budget_audit_read ON platform.llm_poc_budget_audit FOR SELECT TO ai_res_api_group USING ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_settlements_insert ON platform.llm_poc_settlements FOR INSERT TO ai_res_api_group WITH CHECK ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_llm_poc_settlements_owner_migration ON platform.llm_poc_settlements TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_llm_poc_settlements_read ON platform.llm_poc_settlements FOR SELECT TO ai_res_api_group USING ((account_id = (NULLIF(current_setting('app.llm_poc_budget_id'::text, true), ''::text))::uuid));

CREATE POLICY p_manager_epic_context_owner ON platform.manager_epic_context_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_audit_owner_migration ON platform.model_admission_audit TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_audit_read ON platform.model_admission_audit FOR SELECT TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_audit_write ON platform.model_admission_audit FOR INSERT TO ai_res_api_group WITH CHECK ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_calls_finalize ON platform.model_admission_calls FOR UPDATE TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid)) WITH CHECK ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_calls_owner_migration ON platform.model_admission_calls TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_calls_read ON platform.model_admission_calls FOR SELECT TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_calls_write ON platform.model_admission_calls FOR INSERT TO ai_res_api_group WITH CHECK ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_controls_owner_migration ON platform.model_admission_controls TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_controls_read ON platform.model_admission_controls FOR SELECT TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_controls_write ON platform.model_admission_controls FOR UPDATE TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid)) WITH CHECK ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_model_admission_decisions_owner_migration ON platform.model_admission_decisions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_operators_owner_migration ON platform.model_admission_operators TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_versions_owner_migration ON platform.model_admission_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_model_admission_versions_read ON platform.model_admission_versions FOR SELECT TO ai_res_api_group USING ((profile_id = (NULLIF(current_setting('app.model_profile_id'::text, true), ''::text))::uuid));

CREATE POLICY p_operation_assignments_api_tenant ON platform.operation_execution_assignments TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_operation_assignments_owner_migration ON platform.operation_execution_assignments TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_platform_auth_events_admin ON platform.platform_auth_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_platform_auth_events_insert ON platform.platform_auth_events FOR INSERT TO ai_res_platform_api_group WITH CHECK (((((reason = ANY (ARRAY['INVALID_CREDENTIAL'::text, 'EXPIRED_OR_REPLAY'::text, 'ASSIGNMENT_DENIED'::text, 'INVALID_REQUEST'::text])) AND (action IS NULL)) OR ((reason = 'AUTHORIZED'::text) AND (action = ANY (ARRAY['AUTHORIZE_START'::text, 'REGISTER_TASK'::text, 'CHECK_TASK'::text, 'AUTHORIZE_RECONCILIATION_DESCRIBE'::text, 'AUTHORIZE_BOUND_STATUS'::text, 'AUTHORIZE_BOUND_CANCEL'::text])))) IS TRUE));

CREATE POLICY p_platform_nonces_migration ON platform.platform_request_nonces TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_platform_nonces_platform_insert ON platform.platform_request_nonces FOR INSERT TO ai_res_platform_api_group WITH CHECK (((issuer = ANY (ARRAY['MANAGER_RUNTIME'::text, 'TEMPORAL_AUTH_CONTROL'::text])) AND (expires_at > clock_timestamp())));

CREATE POLICY p_task_issuance_receipts_control ON platform.task_issuance_receipts TO ai_res_platform_api_group USING ((current_setting('app.platform_action'::text, true) = ANY (ARRAY['auth.task_issue'::text, 'auth.task_check'::text]))) WITH CHECK ((current_setting('app.platform_action'::text, true) = 'auth.task_issue'::text));

CREATE POLICY p_task_issuance_receipts_migration ON platform.task_issuance_receipts TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

ALTER TABLE platform.platform_auth_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.platform_request_nonces ENABLE ROW LEVEL SECURITY;

ALTER TABLE platform.task_issuance_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.notification_deliveries ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.notification_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE project.notification_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_notification_deliveries_migration ON project.notification_deliveries TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_notification_deliveries_scope ON project.notification_deliveries TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_notification_events_migration ON project.notification_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_notification_events_scope ON project.notification_events TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_notification_preferences_migration ON project.notification_preferences TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_notification_preferences_scope ON project.notification_preferences TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (recipient_id = (NULLIF(current_setting('app.notification_recipient_id'::text, true), ''::text))::uuid)));

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

ALTER TABLE work.manager_interaction_attachments ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.manager_interaction_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.manager_interactions ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.manager_proposal_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.manager_question_journal ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_epic_events_owner_migration ON work.epic_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_epic_events_tenant_scope ON work.epic_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM work.epics p
  WHERE ((p.id = epic_events.epic_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM work.epics p
  WHERE ((p.id = epic_events.epic_id) AND (p.organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (p.project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)))));

CREATE POLICY p_epics_owner_migration ON work.epics TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_epics_tenant_scope ON work.epics TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_manager_interaction_attachments_migration ON work.manager_interaction_attachments TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_interaction_attachments_tenant ON work.manager_interaction_attachments TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_manager_interaction_events_migration ON work.manager_interaction_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_interaction_events_tenant ON work.manager_interaction_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM work.manager_interactions p
  WHERE (p.id = manager_interaction_events.interaction_id))));

CREATE POLICY p_manager_interactions_migration ON work.manager_interactions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_interactions_platform ON work.manager_interactions FOR SELECT TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = ANY (ARRAY['manager.read_input'::text, 'manager.record_draft'::text]))));

CREATE POLICY p_manager_interactions_tenant ON work.manager_interactions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_manager_proposal_versions_migration ON work.manager_proposal_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_proposal_versions_tenant ON work.manager_proposal_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_manager_proposals_context ON work.manager_proposal_versions AS RESTRICTIVE FOR INSERT TO ai_res_platform_api_group WITH CHECK (platform.manager_epic_context_matches_draft((NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid, context_version_id));

CREATE POLICY p_manager_proposals_platform ON work.manager_proposal_versions TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'manager.record_draft'::text) AND (EXISTS ( SELECT 1
   FROM work.manager_interactions i
  WHERE ((i.id = manager_proposal_versions.interaction_id) AND (i.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))))));

CREATE POLICY p_manager_question_journal_migration ON work.manager_question_journal TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_manager_question_journal_tenant ON work.manager_question_journal TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (EXISTS ( SELECT 1
   FROM work.manager_interactions i
  WHERE ((i.id = manager_question_journal.interaction_id) AND (i.epic_id = manager_question_journal.epic_id))))));

CREATE POLICY p_plan_executions_migration ON work.plan_executions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plan_executions_platform ON work.plan_executions FOR SELECT TO ai_res_platform_api_group USING (((current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_plan_executions_tenant ON work.plan_executions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_plan_item_tasks_migration ON work.plan_item_tasks TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plan_item_tasks_platform ON work.plan_item_tasks TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid) AND (EXISTS ( SELECT 1
   FROM (work.plan_executions e
     JOIN governance.plan_version_decisions d ON ((d.id = e.decision_id)))
  WHERE ((e.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid) AND (d.decision = 'APPROVE'::text) AND (plan_item_tasks.item_id = ANY (d.approved_items)))))));

CREATE POLICY p_plan_item_tasks_tenant ON work.plan_item_tasks TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_plan_version_events_migration ON work.plan_version_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plan_version_events_tenant ON work.plan_version_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM work.plan_versions p
  WHERE (p.id = plan_version_events.plan_version_id))));

CREATE POLICY p_plan_versions_migration ON work.plan_versions TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plan_versions_platform ON work.plan_versions FOR SELECT TO ai_res_platform_api_group USING (((current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (EXISTS ( SELECT 1
   FROM work.plan_executions e
  WHERE (e.plan_version_id = plan_versions.id)))));

CREATE POLICY p_plan_versions_tenant ON work.plan_versions TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_plans_migration ON work.plans TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_plans_platform ON work.plans FOR SELECT TO ai_res_platform_api_group USING (((current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (EXISTS ( SELECT 1
   FROM work.plan_versions v
  WHERE (v.plan_id = plans.id)))));

CREATE POLICY p_plans_tenant ON work.plans TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_dependencies_owner_migration ON work.task_dependencies TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_dependencies_platform ON work.task_dependencies FOR INSERT TO ai_res_platform_api_group WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (EXISTS ( SELECT 1
   FROM work.tasks t
  WHERE ((t.id = task_dependencies.task_id) AND (t.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid)))) AND (EXISTS ( SELECT 1
   FROM work.tasks t
  WHERE ((t.id = task_dependencies.depends_on_task_id) AND (t.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))))));

CREATE POLICY p_task_dependencies_tenant_scope ON work.task_dependencies TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_task_events_migration ON work.task_events TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_events_platform ON work.task_events TO ai_res_platform_api_group USING (((current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (EXISTS ( SELECT 1
   FROM work.tasks t
  WHERE ((t.id = task_events.task_id) AND (t.operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid))))));

CREATE POLICY p_task_events_tenant ON work.task_events TO ai_res_api_group USING ((EXISTS ( SELECT 1
   FROM work.tasks p
  WHERE (p.id = task_events.task_id))));

CREATE POLICY p_task_requirements_owner_migration ON work.task_requirements TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_task_requirements_tenant_scope ON work.task_requirements TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

CREATE POLICY p_tasks_owner_migration ON work.tasks TO ai_res_owner USING ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text)) WITH CHECK ((COALESCE(current_setting('app.migration_mode'::text, true), ''::text) = 'on'::text));

CREATE POLICY p_tasks_platform ON work.tasks TO ai_res_platform_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid) AND (current_setting('app.platform_action'::text, true) = 'plan.materialize_tasks'::text) AND (operation_id = (NULLIF(current_setting('app.platform_operation_id'::text, true), ''::text))::uuid) AND (status = 'PROPOSED'::text)));

CREATE POLICY p_tasks_tenant_scope ON work.tasks TO ai_res_api_group USING (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid))) WITH CHECK (((organization_id = (NULLIF(current_setting('app.organization_id'::text, true), ''::text))::uuid) AND (project_id = (NULLIF(current_setting('app.project_id'::text, true), ''::text))::uuid)));

ALTER TABLE work.plan_executions ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.plan_item_tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.plan_version_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.plan_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.plans ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.task_dependencies ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.task_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.task_requirements ENABLE ROW LEVEL SECURITY;

ALTER TABLE work.tasks ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA agents TO ai_res_api_group;
GRANT USAGE ON SCHEMA agents TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA agents TO ai_res_consumer_group;
GRANT USAGE ON SCHEMA agents TO ai_res_platform_api_group;

GRANT USAGE ON SCHEMA artifacts TO ai_res_api_group;

GRANT USAGE ON SCHEMA audit TO ai_res_api_group;
GRANT USAGE ON SCHEMA audit TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA audit TO ai_res_consumer_group;
GRANT USAGE ON SCHEMA audit TO ai_res_auditor_group;
GRANT USAGE ON SCHEMA audit TO ai_res_platform_api_group;

GRANT USAGE ON SCHEMA context TO ai_res_api_group;

GRANT USAGE ON SCHEMA decisions TO ai_res_api_group;

GRANT USAGE ON SCHEMA execution TO ai_res_api_group;
GRANT USAGE ON SCHEMA execution TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA governance TO ai_res_api_group;
GRANT USAGE ON SCHEMA governance TO ai_res_platform_api_group;

GRANT USAGE ON SCHEMA iam TO ai_res_api_group;

GRANT USAGE ON SCHEMA integrations TO ai_res_api_group;

GRANT USAGE ON SCHEMA knowledge TO ai_res_api_group;

GRANT USAGE ON SCHEMA operations TO ai_res_api_group;
GRANT USAGE ON SCHEMA operations TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA operations TO ai_res_consumer_group;
GRANT USAGE ON SCHEMA operations TO ai_res_platform_api_group;

GRANT USAGE ON SCHEMA organization TO ai_res_api_group;

GRANT USAGE ON SCHEMA platform TO ai_res_api_group;
GRANT USAGE ON SCHEMA platform TO ai_res_model_admission_operator;
GRANT USAGE ON SCHEMA platform TO ai_res_platform_api_group;

GRANT USAGE ON SCHEMA project TO ai_res_api_group;

REVOKE USAGE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA requirements TO ai_res_api_group;

GRANT USAGE ON SCHEMA sources TO ai_res_api_group;

GRANT USAGE ON SCHEMA traceability TO ai_res_api_group;

GRANT USAGE ON SCHEMA work TO ai_res_api_group;
GRANT USAGE ON SCHEMA work TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION agents.assert_worker_run_started_ready() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.guard_worker_definition() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.guard_worker_definition_version() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.guard_worker_run_start() FROM PUBLIC;

REVOKE ALL ON FUNCTION agents.require_started_open_run() FROM PUBLIC;

REVOKE ALL ON FUNCTION artifacts.guard_publication_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.approve_assigned_start_replay(operation_ref uuid, event_ref uuid, expected_count integer, actor_ref uuid, session_ref uuid, request_ref uuid, audit_ref uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION audit.approve_assigned_start_replay(operation_ref uuid, event_ref uuid, expected_count integer, actor_ref uuid, session_ref uuid, request_ref uuid, audit_ref uuid) TO ai_res_api_group;

REVOKE ALL ON FUNCTION audit.assert_checkpoint_advances() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_outbox_matches_event() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.assert_replay_count_step() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.authorize_assigned_delivery(row_ref uuid, owner_ref text, attempt integer, generation integer, namespace_ref text, request_nonce uuid, credential_expires timestamp with time zone, request_correlation uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION audit.authorize_assigned_delivery(row_ref uuid, owner_ref text, attempt integer, generation integer, namespace_ref text, request_nonce uuid, credential_expires timestamp with time zone, request_correlation uuid) TO ai_res_api_group;

REVOKE ALL ON FUNCTION audit.guard_assigned_start_quarantine() FROM PUBLIC;

REVOKE ALL ON FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION audit.inspect_assigned_start_replay(operation_ref uuid) TO ai_res_api_group;

REVOKE ALL ON FUNCTION context.assert_package_version_complete() FROM PUBLIC;

REVOKE ALL ON FUNCTION context.guard_item_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION context.stamp_creation_transaction() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.guard_check_result_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION execution.lock_run_for_evaluation() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.assert_baseline_approved() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.assert_baseline_complete() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_approval_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_baseline_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_baseline_item_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_rule_approver() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_rule_record_scope() FROM PUBLIC;

REVOKE ALL ON FUNCTION governance.guard_version_facts() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.advance_by_one() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.apply_owner_identity_decision(o uuid, u uuid, sid uuid, p uuid, d uuid, reviewed jsonb, cmd_text text, expected_text text, observed_text text) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.apply_owner_identity_decision(o uuid, u uuid, sid uuid, p uuid, d uuid, reviewed jsonb, cmd_text text, expected_text text, observed_text text) TO ai_res_model_admission_operator;

REVOKE ALL ON FUNCTION platform.assert_event_sequence_contiguous() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.assert_version_number_contiguous() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.bound_workflow_task_command_binding(oid uuid, rid uuid, ns text, q text, digest bytea) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.bound_workflow_task_command_binding(oid uuid, rid uuid, ns text, q text, digest bytea) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.bound_workflow_task_context(oid uuid, rid uuid, ns text, q text, digest bytea) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.bound_workflow_task_context(oid uuid, rid uuid, ns text, q text, digest bytea) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.capture_manager_epic_context(oid uuid, aid uuid, rid uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.capture_manager_epic_context(oid uuid, aid uuid, rid uuid) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.fence_model_profile_lifecycle() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.finish_llm_poc_settlement() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.forbid_unset() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.freeze_when_status_in() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_admission_reapproval_generation() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_llm_poc_account() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_llm_poc_attempt() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_llm_poc_settlement() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_model_admission_call() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_model_admission_control() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_model_profile() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.guard_status_transition() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_columns_immutable() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_non_decreasing() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_operation_assignment_binding() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.keep_terminal_status() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.lock_manager_epic_context_assignment(oid uuid, expected_action text) FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.manager_epic_context_matches_draft(oid uuid, cid uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.manager_epic_context_matches_draft(oid uuid, cid uuid) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.matches_bound_execution_status(oid uuid, rid uuid, ns text) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.matches_bound_execution_status(oid uuid, rid uuid, ns text) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.matches_bound_manager_task(oid uuid, rid uuid, ns text, queue text) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.matches_bound_manager_task(oid uuid, rid uuid, ns text, queue text) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major integer, digest bytea) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.matches_operation_dispatch(aid uuid, wid text, wtype text, ns text, queue text, major integer, digest bytea) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.matches_reconciliation_describe(oid uuid, rid uuid, ns text) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.matches_reconciliation_describe(oid uuid, rid uuid, ns text) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.owner_identity_snapshot(o uuid, u uuid, sid uuid, p uuid, d uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.owner_identity_snapshot(o uuid, u uuid, sid uuid, p uuid, d uuid) TO ai_res_model_admission_operator;

REVOKE ALL ON FUNCTION platform.reject_modification() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.require_initial_state() FROM PUBLIC;

REVOKE ALL ON FUNCTION platform.resolve_operation_assignment(aid uuid, oid uuid, wid text, rid uuid, action text) FROM PUBLIC;
GRANT ALL ON FUNCTION platform.resolve_operation_assignment(aid uuid, oid uuid, wid text, rid uuid, action text) TO ai_res_platform_api_group;

REVOKE ALL ON FUNCTION platform.touch_row() FROM PUBLIC;

REVOKE ALL ON FUNCTION sources.guard_source_version_insert() FROM PUBLIC;

REVOKE ALL ON FUNCTION traceability.assert_endpoint_exists() FROM PUBLIC;

REVOKE ALL ON FUNCTION work.require_open_operation() FROM PUBLIC;

REVOKE ALL ON FUNCTION work.require_platform_plan_item() FROM PUBLIC;

REVOKE ALL ON FUNCTION work.require_unsealed_interaction() FROM PUBLIC;

GRANT SELECT ON TABLE agents.worker_definition_versions TO ai_res_api_group;

GRANT SELECT ON TABLE agents.worker_definitions TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE agents.worker_results TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE agents.worker_run_events TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE agents.worker_runs TO ai_res_api_group;

GRANT SELECT(operation_id) ON TABLE agents.worker_runs TO ai_res_platform_api_group;

GRANT SELECT(status) ON TABLE agents.worker_runs TO ai_res_platform_api_group;

GRANT SELECT ON TABLE agents.worker_tool_grants TO ai_res_api_group;

GRANT UPDATE(rate_minute) ON TABLE agents.worker_tool_grants TO ai_res_api_group;

GRANT UPDATE(rate_count) ON TABLE agents.worker_tool_grants TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.artifact_events TO ai_res_api_group;

GRANT SELECT ON TABLE artifacts.artifact_types TO ai_res_api_group;

GRANT SELECT ON TABLE artifacts.artifact_version_statuses TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE artifacts.artifact_versions TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE artifacts.artifacts TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.publications TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE artifacts.validation_reports TO ai_res_api_group;

GRANT INSERT ON TABLE audit.audit_events TO ai_res_api_group;
GRANT SELECT ON TABLE audit.audit_events TO ai_res_auditor_group;
GRANT INSERT ON TABLE audit.audit_events TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

GRANT UPDATE(last_sequence) ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

GRANT UPDATE(updated_at) ON TABLE audit.inbox_checkpoints TO ai_res_consumer_group;

GRANT SELECT,INSERT ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(status) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(processed_at) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT UPDATE(error_code) ON TABLE audit.inbox_messages TO ai_res_consumer_group;

GRANT INSERT ON TABLE audit.outbox_events TO ai_res_api_group;
GRANT SELECT ON TABLE audit.outbox_events TO ai_res_outbox_group;
GRANT INSERT ON TABLE audit.outbox_events TO ai_res_platform_api_group;

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

GRANT SELECT,INSERT ON TABLE governance.manager_proposal_decisions TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.plan_version_decisions TO ai_res_api_group;

GRANT SELECT(id) ON TABLE governance.plan_version_decisions TO ai_res_platform_api_group;

GRANT SELECT(plan_version_id) ON TABLE governance.plan_version_decisions TO ai_res_platform_api_group;

GRANT SELECT(decision) ON TABLE governance.plan_version_decisions TO ai_res_platform_api_group;

GRANT SELECT(approved_items) ON TABLE governance.plan_version_decisions TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE governance.reviews TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.rule_evaluations TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.rule_exception_revocations TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.rule_exceptions TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.rule_runtime_controls TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE governance.rule_validation_reports TO ai_res_api_group;

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
GRANT INSERT ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT(event_id) ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT(operation_id) ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT(aggregate_sequence) ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT(event_type) ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT(schema_version) ON TABLE operations.operation_events TO ai_res_platform_api_group;

GRANT SELECT ON TABLE operations.operation_types TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE operations.operations TO ai_res_api_group;

GRANT SELECT(id) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(organization_id) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(project_id) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(operation_type) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(status),UPDATE(status) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT UPDATE(workflow_id) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT UPDATE(result_ref) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT UPDATE(problem_ref) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT UPDATE(started_at) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(completed_at),UPDATE(completed_at) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(last_event_sequence),UPDATE(last_event_sequence) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT(row_version),UPDATE(row_version) ON TABLE operations.operations TO ai_res_platform_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.memberships TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE organization.organizations TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE platform.bootstrap_state TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE platform.display_number_counters TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE platform.idempotency_records TO ai_res_api_group;

GRANT SELECT ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(account_id) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(sequence) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(request_ref) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(case_ref) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(body_sha256) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(payload_bytes) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(stream) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT INSERT(max_output_tokens) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT UPDATE(state) ON TABLE platform.llm_poc_attempts TO ai_res_api_group;

GRANT SELECT ON TABLE platform.llm_poc_budget_accounts TO ai_res_api_group;

GRANT UPDATE(attempt_sequence) ON TABLE platform.llm_poc_budget_accounts TO ai_res_api_group;

GRANT UPDATE(blocked) ON TABLE platform.llm_poc_budget_accounts TO ai_res_api_group;

GRANT SELECT ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT INSERT(account_id) ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT INSERT(attempt_id) ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT INSERT(action) ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT INSERT(reason_code) ON TABLE platform.llm_poc_budget_audit TO ai_res_api_group;

GRANT SELECT ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(account_id) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(attempt_id) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(outcome) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(reason_code) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(input_tokens) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(output_tokens) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(provider_request_ref) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT INSERT(proof_sha256) ON TABLE platform.llm_poc_settlements TO ai_res_api_group;

GRANT SELECT ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT INSERT(profile_id) ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT INSERT(call_id) ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT INSERT(event_type) ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT INSERT(reason_code) ON TABLE platform.model_admission_audit TO ai_res_api_group;

GRANT SELECT ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(profile_id) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(generation) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(call_sequence) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(request_ref) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT INSERT(expected_sha256) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT UPDATE(status) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT UPDATE(observed_sha256) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT UPDATE(finalized_at) ON TABLE platform.model_admission_calls TO ai_res_api_group;

GRANT SELECT ON TABLE platform.model_admission_controls TO ai_res_api_group;

GRANT UPDATE(blocked) ON TABLE platform.model_admission_controls TO ai_res_api_group;

GRANT UPDATE(call_sequence) ON TABLE platform.model_admission_controls TO ai_res_api_group;

GRANT SELECT ON TABLE platform.model_admission_versions TO ai_res_api_group;

GRANT SELECT ON TABLE platform.model_profiles TO ai_res_api_group;

GRANT SELECT ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(organization_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(project_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(operation_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(workflow_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(workflow_type) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(namespace) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(task_queue) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(workflow_contract_version) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(input_digest) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(correlation_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(allowed_actions) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT UPDATE(workflow_run_id) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT UPDATE(revoked_at) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT UPDATE(start_admitted) ON TABLE platform.operation_execution_assignments TO ai_res_api_group;

GRANT INSERT(id) ON TABLE platform.platform_auth_events TO ai_res_platform_api_group;

GRANT INSERT(correlation_id) ON TABLE platform.platform_auth_events TO ai_res_platform_api_group;

GRANT INSERT(reason) ON TABLE platform.platform_auth_events TO ai_res_platform_api_group;

GRANT INSERT(action) ON TABLE platform.platform_auth_events TO ai_res_platform_api_group;

GRANT INSERT(issuer) ON TABLE platform.platform_request_nonces TO ai_res_platform_api_group;

GRANT INSERT(nonce) ON TABLE platform.platform_request_nonces TO ai_res_platform_api_group;

GRANT INSERT(expires_at) ON TABLE platform.platform_request_nonces TO ai_res_platform_api_group;

GRANT SELECT(token_digest),INSERT(token_digest) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(principal),INSERT(principal) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(namespace),INSERT(namespace) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(queue),INSERT(queue) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(task_kind),INSERT(task_kind) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(operation_id),INSERT(operation_id) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT(workflow_run_id),INSERT(workflow_run_id) ON TABLE platform.task_issuance_receipts TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE project.notification_deliveries TO ai_res_api_group;

GRANT UPDATE(published_at) ON TABLE project.notification_deliveries TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE project.notification_events TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE project.notification_preferences TO ai_res_api_group;

GRANT UPDATE(interval_seconds) ON TABLE project.notification_preferences TO ai_res_api_group;

GRANT UPDATE(row_version) ON TABLE project.notification_preferences TO ai_res_api_group;

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

GRANT SELECT,INSERT ON TABLE work.manager_interaction_attachments TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.manager_interaction_events TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.manager_interactions TO ai_res_api_group;

GRANT SELECT(id) ON TABLE work.manager_interactions TO ai_res_platform_api_group;

GRANT SELECT(organization_id) ON TABLE work.manager_interactions TO ai_res_platform_api_group;

GRANT SELECT(project_id) ON TABLE work.manager_interactions TO ai_res_platform_api_group;

GRANT SELECT(operation_id) ON TABLE work.manager_interactions TO ai_res_platform_api_group;

GRANT SELECT(message) ON TABLE work.manager_interactions TO ai_res_platform_api_group;

GRANT UPDATE(row_version) ON TABLE work.manager_interactions TO ai_res_api_group;

GRANT UPDATE(last_event_sequence) ON TABLE work.manager_interactions TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.manager_proposal_versions TO ai_res_api_group;

GRANT SELECT(id),INSERT(id) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(organization_id) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(project_id) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT SELECT(interaction_id),INSERT(interaction_id) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(goal) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(scope) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(primary_question) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT SELECT(content_hash),INSERT(content_hash) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT INSERT(context_version_id) ON TABLE work.manager_proposal_versions TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE work.manager_question_journal TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.plan_executions TO ai_res_api_group;

GRANT SELECT(organization_id) ON TABLE work.plan_executions TO ai_res_platform_api_group;

GRANT SELECT(project_id) ON TABLE work.plan_executions TO ai_res_platform_api_group;

GRANT SELECT(operation_id) ON TABLE work.plan_executions TO ai_res_platform_api_group;

GRANT SELECT(plan_version_id) ON TABLE work.plan_executions TO ai_res_platform_api_group;

GRANT SELECT(decision_id) ON TABLE work.plan_executions TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE work.plan_item_tasks TO ai_res_api_group;

GRANT INSERT(organization_id) ON TABLE work.plan_item_tasks TO ai_res_platform_api_group;

GRANT INSERT(project_id) ON TABLE work.plan_item_tasks TO ai_res_platform_api_group;

GRANT SELECT(operation_id),INSERT(operation_id) ON TABLE work.plan_item_tasks TO ai_res_platform_api_group;

GRANT SELECT(item_id),INSERT(item_id) ON TABLE work.plan_item_tasks TO ai_res_platform_api_group;

GRANT SELECT(task_id),INSERT(task_id) ON TABLE work.plan_item_tasks TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE work.plan_version_events TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.plan_versions TO ai_res_api_group;

GRANT SELECT(id) ON TABLE work.plan_versions TO ai_res_platform_api_group;

GRANT SELECT(plan_id) ON TABLE work.plan_versions TO ai_res_platform_api_group;

GRANT SELECT(snapshot) ON TABLE work.plan_versions TO ai_res_platform_api_group;

GRANT UPDATE(row_version) ON TABLE work.plan_versions TO ai_res_api_group;

GRANT UPDATE(last_event_sequence) ON TABLE work.plan_versions TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.plans TO ai_res_api_group;

GRANT SELECT(id) ON TABLE work.plans TO ai_res_platform_api_group;

GRANT SELECT(epic_id) ON TABLE work.plans TO ai_res_platform_api_group;

GRANT UPDATE(last_version) ON TABLE work.plans TO ai_res_api_group;

GRANT SELECT,INSERT ON TABLE work.task_dependencies TO ai_res_api_group;

GRANT INSERT(id) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT INSERT(organization_id) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT INSERT(project_id) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT INSERT(task_id) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT INSERT(depends_on_task_id) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT INSERT(created_by) ON TABLE work.task_dependencies TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE work.task_events TO ai_res_api_group;
GRANT INSERT ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT(event_id) ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT(task_id) ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT(aggregate_sequence) ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT(event_type) ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT(schema_version) ON TABLE work.task_events TO ai_res_platform_api_group;

GRANT SELECT,INSERT ON TABLE work.task_requirements TO ai_res_api_group;

GRANT SELECT,INSERT,UPDATE ON TABLE work.tasks TO ai_res_api_group;

GRANT SELECT(id),INSERT(id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(organization_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(project_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(operation_id),INSERT(operation_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(epic_id),INSERT(epic_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(derived_from_task_id),INSERT(derived_from_task_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(task_type) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(title),INSERT(title) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(description) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(acceptance_criteria) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(status),INSERT(status) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(priority) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(initiator_type) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(initiator_id) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT INSERT(created_by) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(row_version),UPDATE(row_version) ON TABLE work.tasks TO ai_res_platform_api_group;

GRANT SELECT(last_event_sequence),UPDATE(last_event_sequence) ON TABLE work.tasks TO ai_res_platform_api_group;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TYPES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC;
