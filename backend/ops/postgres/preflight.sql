-- Pre-deployment checks (Blueprint §10). Returns one row per violation: (check, detail). Empty result = pass. Read-only.
SELECT 'server_version', 'PostgreSQL major ' || (current_setting('server_version_num')::int / 10000) || ' (baseline is 16)'
 WHERE current_setting('server_version_num')::int / 10000 <> 16
UNION ALL
SELECT 'connected_as_privileged', session_user || ' must not be SUPERUSER/BYPASSRLS'
  FROM pg_roles WHERE rolname = session_user AND (rolsuper OR rolbypassrls)
UNION ALL
SELECT 'migration_in_progress', 'advisory migration lock is held by pid ' || pid
  FROM pg_locks WHERE locktype = 'advisory' AND granted AND objsubid = 1
   AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
   AND classid::bigint = (hashtextextended('ai_res.alembic.migrations', 0) >> 32) & 4294967295
   AND objid::bigint = hashtextextended('ai_res.alembic.migrations', 0) & 4294967295
UNION ALL
-- NOTE: as a non-superuser without pg_read_all_stats the migrator sees xact_start/state only for its own sessions, so this check is best-effort (KNOWN_GAPS G-41).
SELECT 'long_transaction', 'pid ' || pid || ' idle in transaction since ' || xact_start
  FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction' AND xact_start < now() - interval '5 minutes'
UNION ALL
SELECT 'missing_role', r FROM unnest(ARRAY['ai_res_owner','ai_res_migrator','ai_res_api','ai_res_outbox_dispatcher','ai_res_event_consumer',
  'ai_res_auditor','ai_res_backup','ai_res_api_group','ai_res_outbox_group','ai_res_consumer_group','ai_res_auditor_group']) r
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
