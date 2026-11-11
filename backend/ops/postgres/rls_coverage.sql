-- RLS coverage (DBM-017, Blueprint §9). Default-fail: EVERY table in the domain schemas must have ENABLE + FORCE RLS and a policy, unless it is
-- listed in `exempt` with a reason. Adding a table without RLS therefore breaks CI until someone justifies it here (reviewed in the PR).
WITH allow(schema_name) AS (VALUES ('iam'),('organization'),('project'),('work'),('requirements'),('sources'),('knowledge'),('decisions'),
  ('artifacts'),('traceability'),('governance'),('agents'),('context'),('integrations'),('audit'),('platform'),('operations'),('execution')),
cross_tenant(policy_name, reason) AS (VALUES
  ('audit.outbox_events / p_outbox_events_dispatcher_select', 'outbox dispatcher is cross-tenant by design (ADR-034 (4))'),
  ('audit.outbox_events / p_outbox_events_dispatcher_update', 'outbox dispatcher claims/updates delivery columns only (column grants + trigger)'),
  ('audit.inbox_messages / p_inbox_messages_consumer_all', 'event consumer is cross-tenant by design (ADR-034 (4)); progress columns only')),
exempt(table_name, reason) AS (VALUES ('platform.alembic_version', 'Alembic bookkeeping; not tenant data, no runtime grants'),
  ('iam.roles', 'global reference data (ADR-050); runtime SELECT-only, writable only by migrations'),
  ('operations.operation_types', 'global operation_type registry (ADR-013); runtime SELECT-only, extended only by revisions'),
  ('audit.aggregate_types', 'global aggregate_type registry (ADR-016); no runtime grants, extended only by revisions')),
tbl AS (
  SELECT c.oid, c.relrowsecurity AS rls, c.relforcerowsecurity AS forced, n.nspname || '.' || c.relname AS name,
         EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname IN ('organization_id','project_id') AND NOT a.attisdropped) AS scoped
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r','p') AND NOT c.relispartition AND n.nspname IN (SELECT schema_name FROM allow))
SELECT 'rls_not_enabled_and_forced', name FROM tbl
 WHERE scoped AND NOT (rls AND forced) AND name NOT IN (SELECT table_name FROM exempt)
UNION ALL
SELECT 'table_without_rls_not_exempt', name FROM tbl
 WHERE NOT (rls AND forced) AND name NOT IN (SELECT table_name FROM exempt)
UNION ALL
SELECT 'rls_without_policy', name FROM tbl WHERE rls AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = tbl.oid)
UNION ALL
SELECT 'owner_migration_policy_missing', name FROM tbl   -- ADR-034 (5): under FORCE RLS the owner sees nothing without its own explicit, gated policy (a backfill would silently be a no-op)
 WHERE rls AND forced AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = tbl.oid AND p.polroles = ARRAY[(SELECT oid FROM pg_roles WHERE rolname = 'ai_res_owner')]
   AND pg_get_expr(p.polqual, p.polrelid) = '(COALESCE(current_setting(''app.migration_mode''::text, true), ''''::text) = ''on''::text)'   -- exact: "true OR gate" must not pass
   AND pg_get_expr(p.polwithcheck, p.polrelid) = pg_get_expr(p.polqual, p.polrelid))
UNION ALL
SELECT 'rls_policy_to_public', t.name || ' / ' || p.polname FROM tbl t JOIN pg_policy p ON p.polrelid = t.oid WHERE p.polroles = '{0}'::oid[]
UNION ALL
SELECT 'rls_policy_always_true', t.name || ' / ' || p.polname FROM tbl t JOIN pg_policy p ON p.polrelid = t.oid
 WHERE (pg_get_expr(p.polqual, p.polrelid) = 'true' OR pg_get_expr(p.polwithcheck, p.polrelid) = 'true')
   AND (t.name || ' / ' || p.polname NOT IN (SELECT policy_name FROM cross_tenant)  -- an allow-listed policy must still target ONLY the service groups
        OR EXISTS (SELECT 1 FROM unnest(p.polroles) r WHERE r = 0 OR pg_get_userbyid(r) NOT IN ('ai_res_outbox_group','ai_res_consumer_group')))
UNION ALL
SELECT 'exempt_table_writable_by_runtime', t.name || ' ' || p FROM tbl t CROSS JOIN unnest(ARRAY['INSERT','UPDATE','DELETE']) p
 WHERE t.name IN (SELECT table_name FROM exempt) AND EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname LIKE 'ai\_res\_%' AND r.rolname NOT IN ('ai_res_owner','ai_res_migrator')
   AND (has_table_privilege(r.oid, t.oid, p) OR (p <> 'DELETE' AND has_any_column_privilege(r.oid, t.oid, p))))
UNION ALL
SELECT 'view_without_security_invoker', n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'v' AND n.nspname IN (SELECT schema_name FROM allow) AND NOT coalesce('security_invoker=true' = ANY(c.reloptions), false)
UNION ALL
SELECT 'materialized_view_in_domain_schema', n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'm' AND n.nspname IN (SELECT schema_name FROM allow);  -- cannot carry RLS: forbidden until reviewed
