-- RLS coverage (DBM-017, Blueprint §9). Default-fail: EVERY table in the domain schemas must have ENABLE + FORCE RLS and a policy, unless it is
-- listed in `exempt` with a reason. Adding a table without RLS therefore breaks CI until someone justifies it here (reviewed in the PR).
WITH allow(schema_name) AS (VALUES ('iam'),('organization'),('project'),('work'),('requirements'),('sources'),('knowledge'),('decisions'),
  ('artifacts'),('traceability'),('governance'),('agents'),('context'),('integrations'),('audit'),('platform'),('operations'),('execution')),
exempt(table_name, reason) AS (VALUES ('platform.alembic_version', 'Alembic bookkeeping; not tenant data, no runtime grants')),
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
SELECT 'rls_policy_to_public', t.name || ' / ' || p.polname FROM tbl t JOIN pg_policy p ON p.polrelid = t.oid WHERE p.polroles = '{0}'::oid[]
UNION ALL
SELECT 'rls_policy_always_true', t.name || ' / ' || p.polname FROM tbl t JOIN pg_policy p ON p.polrelid = t.oid
 WHERE pg_get_expr(p.polqual, p.polrelid) = 'true' OR pg_get_expr(p.polwithcheck, p.polrelid) = 'true'
UNION ALL
SELECT 'view_without_security_invoker', n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'v' AND n.nspname IN (SELECT schema_name FROM allow) AND NOT coalesce('security_invoker=true' = ANY(c.reloptions), false)
UNION ALL
SELECT 'materialized_view_in_domain_schema', n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'm' AND n.nspname IN (SELECT schema_name FROM allow);  -- cannot carry RLS: forbidden until reviewed
