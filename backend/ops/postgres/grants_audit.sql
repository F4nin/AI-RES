-- Grants audit (Blueprint §9, Strategy §2.1, CI gate "runtime principals have no DDL/BYPASSRLS"). Violations as (check, detail). Empty = pass.
-- Runtime principals = every login/group role below except the migrator and the owner. Roles that do not exist yet are skipped.
WITH rt(rolname) AS (VALUES ('ai_res_api'),('ai_res_platform_api'),('ai_res_outbox_dispatcher'),('ai_res_event_consumer'),('ai_res_auditor'),('ai_res_backup'),
  ('ai_res_checkpointer'),('ai_res_api_group'),('ai_res_platform_api_group'),('ai_res_outbox_group'),('ai_res_consumer_group'),('ai_res_auditor_group'),('ai_res_checkpointer_group'),
  ('ai_res_model_admission_operator')),
rt_existing AS (SELECT rolname FROM rt WHERE EXISTS (SELECT 1 FROM pg_roles p WHERE p.rolname = rt.rolname)),
allow(schema_name) AS (VALUES ('iam'),('organization'),('project'),('work'),('requirements'),('sources'),('knowledge'),('decisions'),
  ('artifacts'),('traceability'),('governance'),('agents'),('context'),('integrations'),('audit'),('platform'),('operations'),('execution')),
app_tables AS (
  SELECT c.oid, n.nspname || '.' || c.relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT LIKE 'pg\_%' AND n.nspname NOT IN ('information_schema','langgraph')),
dom_funcs AS (
  SELECT p.oid, p.proowner, p.proacl, p.prosecdef, p.proconfig, n.nspname || '.' || p.proname AS name FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname IN (SELECT schema_name FROM allow)),
reviewed_definers(signature) AS (VALUES
  ('platform.owner_identity_snapshot(uuid,uuid,uuid,uuid,uuid)'),
  ('platform.apply_owner_identity_decision(uuid,uuid,uuid,uuid,uuid,jsonb,text,text,text)')),
platform_definer(signature, introduced_table) AS (VALUES
  ('platform.resolve_operation_assignment(uuid,uuid,text,uuid,text)','platform.operation_execution_assignments'),
  ('platform.matches_operation_dispatch(uuid,text,text,text,text,integer,bytea)','platform.task_issuance_receipts'),
  ('platform.matches_bound_manager_task(uuid,uuid,text,text)','platform.task_issuance_receipts'),
  ('platform.bound_workflow_task_context(uuid,uuid,text,text,bytea)','platform.task_issuance_receipts'),
  ('platform.bound_workflow_task_command_binding(uuid,uuid,text,text,bytea)','platform.task_issuance_receipts'),
  ('platform.matches_reconciliation_describe(uuid,uuid,text)','platform.task_issuance_receipts'),
  ('platform.matches_bound_execution_status(uuid,uuid,text)',NULL),
  ('platform.capture_manager_epic_context(uuid,uuid,uuid)','platform.manager_epic_context_versions'),
  ('platform.manager_epic_context_matches_draft(uuid,uuid)','platform.manager_epic_context_versions')),
api_definer(signature) AS (VALUES
  ('audit.inspect_assigned_start_replay(uuid)'),
  ('audit.approve_assigned_start_replay(uuid,uuid,integer,uuid,uuid,uuid,uuid)'),
  ('audit.authorize_assigned_delivery(uuid,text,integer,integer,text,uuid,timestamptz,uuid)')),
dom_types AS (  -- base/domain/enum/range/multirange types; table row types ('c') follow their table
  SELECT t.oid, t.typowner, t.typacl, n.nspname || '.' || t.typname AS name FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
   WHERE n.nspname IN (SELECT schema_name FROM allow) AND t.typtype IN ('b','d','e','r','m')
     AND NOT (t.typcategory = 'A' AND EXISTS (SELECT 1 FROM pg_type e WHERE e.oid = t.typelem AND e.typtype = 'c')))  -- auto array types of table rows
SELECT 'missing_role', rt.rolname FROM rt WHERE rt.rolname <> 'ai_res_checkpointer' AND rt.rolname <> 'ai_res_checkpointer_group'
   AND NOT EXISTS (SELECT 1 FROM pg_roles p WHERE p.rolname = rt.rolname)  -- a skipped role would make every check below vacuous
UNION ALL
SELECT 'forbidden_table_privilege', rt.rolname || ' ' || p || ' on ' || t.name
  FROM rt_existing rt CROSS JOIN app_tables t CROSS JOIN unnest(ARRAY['TRUNCATE','REFERENCES','TRIGGER']) p
 WHERE has_table_privilege(rt.rolname, t.oid, p) OR (p = 'REFERENCES' AND has_any_column_privilege(rt.rolname, t.oid, p))
UNION ALL
SELECT 'api_delete_privilege', rt.rolname || ' DELETE on ' || t.name
  FROM rt_existing rt CROSS JOIN app_tables t
 WHERE rt.rolname IN ('ai_res_api','ai_res_api_group') AND has_table_privilege(rt.rolname, t.oid, 'DELETE')
UNION ALL
SELECT 'read_only_role_can_write', rt.rolname || ' ' || p || ' on ' || t.name  -- table- AND column-level grants (has_table_privilege alone misses the latter)
  FROM rt_existing rt CROSS JOIN app_tables t CROSS JOIN unnest(ARRAY['INSERT','UPDATE']) p
 WHERE rt.rolname IN ('ai_res_auditor','ai_res_auditor_group','ai_res_backup') AND has_any_column_privilege(rt.rolname, t.oid, p)
UNION ALL
SELECT 'read_only_role_can_write', rt.rolname || ' DELETE on ' || t.name
  FROM rt_existing rt CROSS JOIN app_tables t
 WHERE rt.rolname IN ('ai_res_auditor','ai_res_auditor_group','ai_res_backup') AND has_table_privilege(rt.rolname, t.oid, 'DELETE')
UNION ALL
SELECT 'runtime_can_create_in_schema', rt.rolname || ' on ' || n.nspname
  FROM rt_existing rt CROSS JOIN pg_namespace n
 WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname <> 'information_schema' AND has_schema_privilege(rt.rolname, n.oid, 'CREATE')
UNION ALL
SELECT 'checkpointer_in_domain_schema', rt.rolname || ' ' || p || ' on ' || a.schema_name  -- ADR-036: the checkpointer touches only `langgraph`
  FROM rt_existing rt CROSS JOIN allow a CROSS JOIN unnest(ARRAY['USAGE','CREATE']) p
 WHERE rt.rolname IN ('ai_res_checkpointer','ai_res_checkpointer_group') AND has_schema_privilege(rt.rolname, a.schema_name, p)
UNION ALL
SELECT 'runtime_database_privilege', rt.rolname || ' ' || p
  FROM rt_existing rt CROSS JOIN unnest(ARRAY['CREATE','TEMPORARY']) p WHERE has_database_privilege(rt.rolname, current_database(), p)
UNION ALL
SELECT 'runtime_parameter_privilege', rt.rolname || ' ' || a.privilege_type || ' on ' || pa.parname
 FROM rt_existing rt CROSS JOIN pg_parameter_acl pa CROSS JOIN LATERAL aclexplode(pa.paracl) a
 WHERE CASE WHEN a.grantee=0 THEN true ELSE pg_has_role(rt.rolname,a.grantee,'MEMBER') END
UNION ALL
SELECT 'unexpected_parameter_acl', pa.parname FROM pg_parameter_acl pa CROSS JOIN LATERAL aclexplode(pa.paracl) a
 WHERE pa.parname='app.migration_mode' AND
  (NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid=a.grantee AND (r.rolsuper OR r.rolname='ai_res_owner'))
   OR (a.grantee=(SELECT oid FROM pg_roles WHERE rolname='ai_res_owner') AND
      (a.privilege_type<>'SET' OR a.is_grantable OR NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid=a.grantor AND r.rolsuper))))
UNION ALL
SELECT 'owner_parameter_acl_missing','app.migration_mode' WHERE NOT EXISTS
 (SELECT 1 FROM pg_parameter_acl pa CROSS JOIN LATERAL aclexplode(pa.paracl) a
  WHERE pa.parname='app.migration_mode' AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname='ai_res_owner')
    AND a.privilege_type='SET' AND NOT a.is_grantable)
UNION ALL
SELECT 'runtime_predefined_role', rt.rolname || ' in ' || p
  FROM rt_existing rt CROSS JOIN unnest(ARRAY['pg_read_all_data','pg_write_all_data','pg_execute_server_program','pg_read_server_files',
    'pg_write_server_files','pg_signal_backend','pg_monitor']) p WHERE pg_has_role(rt.rolname, p, 'MEMBER')
UNION ALL
SELECT 'runtime_owns_object', rt.rolname || ' owns ' || c.relname
  FROM rt_existing rt JOIN pg_roles r ON r.rolname = rt.rolname JOIN pg_class c ON c.relowner = r.oid
UNION ALL
SELECT 'runtime_owns_schema', rt.rolname || ' owns ' || n.nspname
  FROM rt_existing rt JOIN pg_roles r ON r.rolname = rt.rolname JOIN pg_namespace n ON n.nspowner = r.oid
UNION ALL
SELECT 'runtime_owns_function_or_type', rt.rolname || ' owns ' || f.name
  FROM rt_existing rt JOIN pg_roles r ON r.rolname = rt.rolname JOIN dom_funcs f ON f.proowner = r.oid
UNION ALL
SELECT 'runtime_owns_function_or_type', rt.rolname || ' owns ' || t.name
  FROM rt_existing rt JOIN pg_roles r ON r.rolname = rt.rolname JOIN dom_types t ON t.typowner = r.oid
UNION ALL
SELECT 'non_owner_owns_app_object', pg_get_userbyid(c.relowner) || ' owns ' || n.nspname || '.' || c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname NOT IN ('information_schema','langgraph','public') AND c.relkind NOT IN ('i','I','S','t','c')
   AND pg_get_userbyid(c.relowner) <> 'ai_res_owner'
UNION ALL
SELECT 'non_owner_owns_function_or_type', pg_get_userbyid(f.proowner) || ' owns ' || f.name FROM dom_funcs f WHERE pg_get_userbyid(f.proowner) <> 'ai_res_owner'
UNION ALL
SELECT 'non_owner_owns_function_or_type', pg_get_userbyid(t.typowner) || ' owns ' || t.name FROM dom_types t WHERE pg_get_userbyid(t.typowner) <> 'ai_res_owner'
UNION ALL
SELECT 'public_execute_on_function', f.name
  FROM dom_funcs f, aclexplode(coalesce(f.proacl, acldefault('f', f.proowner))) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'
UNION ALL
SELECT 'public_usage_on_type', t.name
  FROM dom_types t, aclexplode(coalesce(t.typacl, acldefault('T', t.typowner))) a WHERE a.grantee = 0 AND a.privilege_type = 'USAGE'
UNION ALL
SELECT 'security_definer_function', f.name FROM dom_funcs f WHERE f.prosecdef
  AND NOT EXISTS (SELECT 1 FROM reviewed_definers d WHERE f.oid=to_regprocedure(d.signature))
  AND NOT EXISTS (SELECT 1 FROM platform_definer d WHERE f.oid=to_regprocedure(d.signature))
  AND NOT EXISTS (SELECT 1 FROM api_definer d WHERE f.oid=to_regprocedure(d.signature))
UNION ALL
SELECT 'api_definer_configuration', d.signature FROM api_definer d JOIN dom_funcs f ON f.oid=to_regprocedure(d.signature)
 WHERE NOT f.prosecdef OR pg_get_userbyid(f.proowner)<>'ai_res_owner'
    OR f.proconfig IS NULL OR NOT f.proconfig @> ARRAY['search_path=pg_catalog','app.migration_mode=on']
    OR cardinality(f.proconfig)<>2 OR NOT has_function_privilege('ai_res_api_group',f.oid,'EXECUTE')
    OR EXISTS (SELECT 1 FROM aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
       WHERE a.grantee NOT IN (f.proowner,(SELECT oid FROM pg_roles WHERE rolname='ai_res_api_group')) OR a.is_grantable)
UNION ALL
SELECT 'api_unexpected_replay_executor', rt.rolname FROM rt_existing rt
 WHERE rt.rolname NOT IN ('ai_res_api','ai_res_api_group')
   AND EXISTS (SELECT 1 FROM api_definer d WHERE to_regprocedure(d.signature) IS NOT NULL
     AND has_function_privilege(rt.rolname,to_regprocedure(d.signature),'EXECUTE'))
UNION ALL
SELECT 'platform_definer_configuration', d.signature FROM platform_definer d LEFT JOIN dom_funcs f ON f.oid=to_regprocedure(d.signature)
 WHERE (f.oid IS NOT NULL OR to_regclass(d.introduced_table) IS NOT NULL) AND
  (f.oid IS NULL OR NOT f.prosecdef OR pg_get_userbyid(f.proowner)<>'ai_res_owner'
   OR f.proconfig IS NULL OR NOT f.proconfig @> ARRAY['search_path=pg_catalog','app.migration_mode=on']
   OR cardinality(f.proconfig)<>2
   OR NOT has_function_privilege('ai_res_platform_api_group',f.oid,'EXECUTE')
   OR EXISTS (SELECT 1 FROM aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
      WHERE a.grantee NOT IN (f.proowner,(SELECT oid FROM pg_roles WHERE rolname='ai_res_platform_api_group')) OR a.is_grantable))
UNION ALL
SELECT 'platform_unexpected_executor', rt.rolname FROM rt_existing rt
 WHERE rt.rolname NOT IN ('ai_res_platform_api','ai_res_platform_api_group') AND
 (pg_has_role(rt.rolname,'ai_res_platform_api_group','MEMBER') OR EXISTS
   (SELECT 1 FROM platform_definer d WHERE to_regprocedure(d.signature) IS NOT NULL
    AND has_function_privilege(rt.rolname,to_regprocedure(d.signature),'EXECUTE')))
UNION ALL
-- ADR140/DOC068 §1.13: exact reviewed signatures, owner, settings and ACL, never a name-only exception.
SELECT 'operator_definer_configuration', d.signature FROM reviewed_definers d LEFT JOIN dom_funcs f ON f.oid=to_regprocedure(d.signature)
 WHERE to_regclass('platform.model_admission_decisions') IS NOT NULL AND
  (f.oid IS NULL OR NOT f.prosecdef OR pg_get_userbyid(f.proowner)<>'ai_res_owner'
   OR f.proconfig IS NULL OR NOT f.proconfig @> ARRAY['search_path=pg_catalog','app.migration_mode=on']
   OR cardinality(f.proconfig)<>2
   OR NOT has_function_privilege('ai_res_model_admission_operator',f.oid,'EXECUTE')
   OR EXISTS (SELECT 1 FROM aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
      WHERE a.grantee NOT IN (f.proowner,(SELECT oid FROM pg_roles WHERE rolname='ai_res_model_admission_operator')) OR a.is_grantable))
UNION ALL
SELECT 'operator_table_privilege', p || ' on ' || t.name FROM app_tables t
 CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) p
 WHERE has_table_privilege('ai_res_model_admission_operator',t.oid,p)
    OR (p<>'DELETE' AND has_any_column_privilege('ai_res_model_admission_operator',t.oid,p))
UNION ALL
SELECT 'operator_unexpected_execute', f.name FROM dom_funcs f
 WHERE has_function_privilege('ai_res_model_admission_operator',f.oid,'EXECUTE')
 AND NOT EXISTS (SELECT 1 FROM reviewed_definers d WHERE f.oid=to_regprocedure(d.signature))
UNION ALL
SELECT 'runtime_operator_authority', rt.rolname FROM rt_existing rt
 WHERE rt.rolname<>'ai_res_model_admission_operator' AND
 (pg_has_role(rt.rolname,'ai_res_model_admission_operator','MEMBER') OR EXISTS
   (SELECT 1 FROM reviewed_definers d WHERE to_regprocedure(d.signature) IS NOT NULL
    AND has_function_privilege(rt.rolname,to_regprocedure(d.signature),'EXECUTE')))
UNION ALL
SELECT 'operator_role_escalation', r.rolname FROM pg_roles r WHERE r.rolname='ai_res_model_admission_operator'
 AND (r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls
      OR EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid))
UNION ALL
SELECT 'default_acl_missing', 'owner default privileges for ' || x.kind || ' still grant PUBLIC (ALTER DEFAULT PRIVILEGES REVOKE was lost)'
  FROM (VALUES ('f', 'FUNCTIONS'), ('T', 'TYPES')) x(typ, kind)
 WHERE NOT EXISTS (
   SELECT 1 FROM pg_default_acl d WHERE d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = 'ai_res_owner') AND d.defaclnamespace = 0
      AND d.defaclobjtype = x.typ AND NOT EXISTS (SELECT 1 FROM aclexplode(d.defaclacl) a WHERE a.grantee = 0));
