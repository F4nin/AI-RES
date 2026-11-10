-- AI RES PostgreSQL role and RLS reference template v1.0
-- Target: PostgreSQL 16+; apply only after schema/table inventory review.
-- This is NOT a production migration. Run as controlled DBA/bootstrap principal.
-- No passwords are created here. Provision LOGIN credentials via Secret Manager.

-- 1. Harden public schema defaults.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- 2. Group roles (NOLOGIN). Keep owner separate from runtime principals.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_res_owner') THEN
    CREATE ROLE ai_res_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_res_api_group') THEN
    CREATE ROLE ai_res_api_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_res_outbox_group') THEN
    CREATE ROLE ai_res_outbox_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_res_consumer_group') THEN
    CREATE ROLE ai_res_consumer_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_res_auditor_group') THEN
    CREATE ROLE ai_res_auditor_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;

-- 3. Example environment-specific LOGIN principals.
-- Create with CREATE ROLE ... LOGIN ... PASSWORD via a secret-injection procedure,
-- or provision externally and GRANT the group roles below.
-- Do NOT commit passwords or use this script to embed secrets.
-- CREATE ROLE ai_res_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- GRANT ai_res_owner TO ai_res_migrator;
-- CREATE ROLE ai_res_api_prod LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- GRANT ai_res_api_group TO ai_res_api_prod;
-- CREATE ROLE ai_res_outbox_prod LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- GRANT ai_res_outbox_group TO ai_res_outbox_prod;
-- CREATE ROLE ai_res_consumer_prod LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- GRANT ai_res_consumer_group TO ai_res_consumer_prod;

-- 4. Schema privileges. Owner creates objects; runtime gets USAGE only.
-- After review, transfer application schemas to the NOLOGIN owner role:
-- ALTER SCHEMA operations OWNER TO ai_res_owner;
-- ALTER SCHEMA work OWNER TO ai_res_owner;
-- ALTER SCHEMA agents OWNER TO ai_res_owner;
-- ALTER SCHEMA execution OWNER TO ai_res_owner;
-- ALTER SCHEMA audit OWNER TO ai_res_owner;
-- ALTER SCHEMA platform OWNER TO ai_res_owner;
GRANT USAGE ON SCHEMA operations, work, agents, execution, platform TO ai_res_api_group;
GRANT USAGE ON SCHEMA audit TO ai_res_outbox_group, ai_res_consumer_group, ai_res_auditor_group;
GRANT USAGE ON SCHEMA operations, agents TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA operations, agents, execution TO ai_res_consumer_group;

-- 5. Remove broad defaults. Add table-specific grants in each migration.
REVOKE ALL ON ALL TABLES IN SCHEMA operations, work, agents, execution, audit, platform FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA operations, work, agents, execution, audit, platform FROM PUBLIC;

-- Example grants for the execution slice. Review column-level update grants
-- and use stored application service methods for state transitions.
GRANT SELECT, INSERT, UPDATE ON operations.operations TO ai_res_api_group;
GRANT SELECT, INSERT ON operations.operation_events TO ai_res_api_group;
GRANT SELECT, INSERT, UPDATE ON work.tasks TO ai_res_api_group;
GRANT SELECT, INSERT, UPDATE ON agents.worker_runs TO ai_res_api_group;
GRANT SELECT, INSERT ON agents.worker_run_events TO ai_res_api_group;
GRANT SELECT, INSERT, UPDATE ON execution.readiness_evaluations TO ai_res_api_group;
GRANT SELECT, INSERT ON execution.readiness_check_results TO ai_res_api_group;
GRANT SELECT, INSERT, UPDATE ON platform.idempotency_records TO ai_res_api_group;

-- Dispatcher can claim/update delivery state, not mutate domain aggregates.
GRANT SELECT, INSERT, UPDATE ON audit.outbox_events TO ai_res_outbox_group;
GRANT SELECT ON operations.operation_events, agents.worker_run_events TO ai_res_outbox_group;

-- Consumer can deduplicate and checkpoint. Domain mutations go through API.
GRANT SELECT, INSERT, UPDATE ON audit.inbox_messages TO ai_res_consumer_group;
GRANT SELECT ON operations.operation_events, agents.worker_run_events TO ai_res_consumer_group;

-- Auditor receives read-only access only to explicitly approved audit records.
GRANT SELECT ON audit.audit_events TO ai_res_auditor_group;

-- No runtime DELETE/TRUNCATE/DDL grants. Do not grant owner role to runtime roles.

-- 6. Tenant context helper expressions. Set both values transaction-locally
-- after API Policy Engine authorization:
-- SELECT set_config('app.organization_id', :org_id::text, true);
-- SELECT set_config('app.project_id', :project_id::text, true);
-- Missing/empty settings resolve to NULL and therefore deny access.

-- 7. RLS policies for tables with direct organization_id/project_id columns.
-- Run only after confirming these columns exist on each target table.
ALTER TABLE operations.operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.operations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_operations_tenant_scope ON operations.operations;
CREATE POLICY p_operations_tenant_scope ON operations.operations
  FOR ALL TO ai_res_api_group
  USING (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  )
  WITH CHECK (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  );

ALTER TABLE work.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE work.tasks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_tasks_tenant_scope ON work.tasks;
CREATE POLICY p_tasks_tenant_scope ON work.tasks
  FOR ALL TO ai_res_api_group
  USING (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  )
  WITH CHECK (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  );

ALTER TABLE agents.worker_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.worker_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_worker_runs_tenant_scope ON agents.worker_runs;
CREATE POLICY p_worker_runs_tenant_scope ON agents.worker_runs
  FOR ALL TO ai_res_api_group
  USING (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  )
  WITH CHECK (
    organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  );

-- Child tables without tenant columns need policies through parent aggregate.
ALTER TABLE operations.operation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.operation_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_operation_events_tenant_scope ON operations.operation_events;
CREATE POLICY p_operation_events_tenant_scope ON operations.operation_events
  FOR ALL TO ai_res_api_group
  USING (EXISTS (
    SELECT 1 FROM operations.operations o
    WHERE o.id = operation_id
      AND o.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND o.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM operations.operations o
    WHERE o.id = operation_id
      AND o.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND o.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ));

ALTER TABLE agents.worker_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.worker_run_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_worker_run_events_tenant_scope ON agents.worker_run_events;
CREATE POLICY p_worker_run_events_tenant_scope ON agents.worker_run_events
  FOR ALL TO ai_res_api_group
  USING (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ));


ALTER TABLE execution.readiness_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution.readiness_evaluations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_readiness_evaluations_tenant_scope ON execution.readiness_evaluations;
CREATE POLICY p_readiness_evaluations_tenant_scope ON execution.readiness_evaluations
  FOR ALL TO ai_res_api_group
  USING (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ));

ALTER TABLE execution.readiness_check_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution.readiness_check_results FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_readiness_check_results_tenant_scope ON execution.readiness_check_results;
CREATE POLICY p_readiness_check_results_tenant_scope ON execution.readiness_check_results
  FOR ALL TO ai_res_api_group
  USING (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM agents.worker_runs wr
    WHERE wr.id = worker_run_id
      AND wr.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND wr.project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
  ));

-- Apply the same parent-scope pattern to every other tenant-scoped table.
-- This template intentionally fails if required schemas/tables/columns differ.

-- 8. Runtime safe defaults (apply to each LOGIN principal after provisioning):
-- ALTER ROLE ai_res_api_prod SET search_path = pg_catalog;
-- ALTER ROLE ai_res_api_prod SET statement_timeout = '15s';
-- ALTER ROLE ai_res_api_prod SET lock_timeout = '2s';
-- ALTER ROLE ai_res_api_prod SET idle_in_transaction_session_timeout = '30s';
-- ALTER ROLE ai_res_api_prod SET default_transaction_read_only = off;
-- Do not set a tenant GUC at role/session level.

-- 9. Privilege audit examples:
-- SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname LIKE 'ai_res_%';
-- SELECT has_table_privilege('ai_res_api_prod', 'operations.operations', 'DELETE'); -- must be false
-- SELECT has_schema_privilege('ai_res_api_prod', 'operations', 'CREATE'); -- must be false
-- Verify no runtime role is owner of tenant tables and no runtime role is member of ai_res_owner.
