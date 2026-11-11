-- Post-deployment checks (Blueprint §10, DBM-006/012/016). Returns violations as (check, detail). Empty result = pass. Read-only.
WITH allow(schema_name) AS (VALUES ('iam'),('organization'),('project'),('work'),('requirements'),('sources'),('knowledge'),('decisions'),
  ('artifacts'),('traceability'),('governance'),('agents'),('context'),('integrations'),('audit'),('platform'),('operations'),('execution'))
SELECT 'missing_role', r FROM unnest(ARRAY['ai_res_owner','ai_res_migrator','ai_res_api','ai_res_outbox_dispatcher','ai_res_event_consumer','ai_res_auditor',
  'ai_res_backup','ai_res_api_group','ai_res_outbox_group','ai_res_consumer_group','ai_res_auditor_group','ai_res_checkpointer_group']) r
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)  -- without this, every role check below would pass vacuously
UNION ALL
SELECT 'forbidden_role_attribute', rolname FROM pg_roles
 WHERE rolname LIKE 'ai_res\_%'
   AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
UNION ALL
SELECT 'owner_can_login', rolname FROM pg_roles WHERE rolname = 'ai_res_owner' AND rolcanlogin
UNION ALL
SELECT 'member_of_owner', rolname FROM pg_roles
 WHERE rolname LIKE 'ai_res\_%' AND rolname NOT IN ('ai_res_owner', 'ai_res_migrator') AND pg_has_role(oid, 'ai_res_owner', 'MEMBER')
UNION ALL
SELECT 'missing_schema', schema_name FROM allow WHERE NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = schema_name)
UNION ALL
SELECT 'schema_not_owned_by_owner', n.nspname FROM pg_namespace n JOIN allow ON allow.schema_name = n.nspname
 WHERE pg_get_userbyid(n.nspowner) IS DISTINCT FROM 'ai_res_owner'
UNION ALL
SELECT 'unexpected_schema', nspname FROM pg_namespace
 WHERE nspname NOT LIKE 'pg\_%' AND nspname NOT IN ('information_schema', 'public', 'langgraph') AND nspname NOT IN (SELECT schema_name FROM allow)
UNION ALL
SELECT 'public_has_schema_privilege', n.nspname || ':' || a.privilege_type
  FROM pg_namespace n, aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
 WHERE a.grantee = 0 AND (n.nspname IN (SELECT schema_name FROM allow) OR (n.nspname = 'public' AND a.privilege_type = 'CREATE'))
UNION ALL
SELECT 'public_database_privilege', a.privilege_type
  FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
 WHERE d.datname = current_database() AND a.grantee = 0
UNION ALL
SELECT 'runtime_search_path_not_fixed', r.rolname FROM pg_roles r
 WHERE r.rolname IN ('ai_res_api','ai_res_outbox_dispatcher','ai_res_event_consumer','ai_res_auditor') AND NOT EXISTS (
   SELECT 1 FROM pg_db_role_setting s WHERE s.setrole = r.oid AND s.setdatabase = 0 AND 'search_path=pg_catalog' = ANY(s.setconfig))
UNION ALL
SELECT 'invalid_index', n.nspname || '.' || c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE NOT i.indisvalid AND n.nspname IN (SELECT schema_name FROM allow)
UNION ALL
SELECT 'not_validated_constraint', n.nspname || '.' || k.conname FROM pg_constraint k JOIN pg_namespace n ON n.oid = k.connamespace
 WHERE NOT k.convalidated AND n.nspname IN (SELECT schema_name FROM allow)
UNION ALL
SELECT 'role_setting_in_database', r.rolname || ' in database oid ' || s.setdatabase FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
 WHERE s.setdatabase <> 0 AND r.rolname LIKE 'ai\_res\_%'  -- would override the role-wide fixed search_path/timeouts
UNION ALL
SELECT 'tenant_guc_in_role_setting', r.rolname || ' ' || c FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole, unnest(s.setconfig) c
 WHERE r.rolname LIKE 'ai\_res\_%' AND c LIKE 'app.%'  -- the tenant context is transaction-local only (Blueprint §7.3)
UNION ALL
SELECT 'membership_admin_option', pg_get_userbyid(m.member) || ' has ADMIN OPTION on ' || pg_get_userbyid(m.roleid) FROM pg_auth_members m
 WHERE m.admin_option AND (pg_get_userbyid(m.member) LIKE 'ai\_res\_%' OR pg_get_userbyid(m.roleid) LIKE 'ai\_res\_%')
UNION ALL
SELECT 'membership_set_option', pg_get_userbyid(m.member) || ' may SET ROLE ' || pg_get_userbyid(m.roleid) FROM pg_auth_members m
 WHERE m.set_option AND pg_get_userbyid(m.roleid) LIKE 'ai\_res\_%' AND NOT (pg_get_userbyid(m.roleid) = 'ai_res_owner' AND pg_get_userbyid(m.member) = 'ai_res_migrator')
UNION ALL
SELECT 'missing_version_table', 'platform.alembic_version' WHERE to_regclass('platform.alembic_version') IS NULL
UNION ALL
SELECT 'version_table_rows', n || ' rows (exactly one expected)'
  FROM (SELECT (xpath('/row/c/text()', query_to_xml('select count(*) as c from platform.alembic_version', false, true, '')))[1]::text::int AS n
         WHERE to_regclass('platform.alembic_version') IS NOT NULL) v  -- dynamic text: no parse error when the table is missing
 WHERE n <> 1
UNION ALL
SELECT 'database_not_owned_by_owner', datname FROM pg_database WHERE datname = current_database() AND pg_get_userbyid(datdba) <> 'ai_res_owner';
