-- AI RES domain DB roles (S04, PDB-0001 prerequisite). ADR-015 / Migration & Access Strategy §2 / DOC-069 adapted by ADR-034, ADR-036.
-- Runs as the cluster bootstrap principal (superuser) through psql, AFTER infra provisioning created ai_res_owner/ai_res_db/ai_res_checkpointer
-- (the test harness creates them itself). Idempotent: attributes and memberships are re-asserted on every run, so drift is corrected.
-- Required psql variables (values come from Compose secrets / test harness, never from this file):
--   migrator_pw api_pw outbox_pw consumer_pw auditor_pw backup_pw
-- Why here and not in an Alembic revision: ai_res_migrator has no CREATEROLE, so it cannot create roles or set passwords (Strategy §1.5, §2).
\set ON_ERROR_STOP on
SET log_statement = 'none';  -- ALTER ROLE ... PASSWORD must never reach the server log even if the server logs DDL
SET log_min_duration_statement = -1;
SET log_min_error_statement = panic;  -- a failing ALTER ROLE ... PASSWORD must not echo the statement (and the password) into the server log
SET password_encryption = 'scram-sha-256';

SELECT 'CREATE ROLE ai_res_owner NOLOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_res_owner') \gexec
SELECT format('CREATE ROLE %I NOLOGIN', r) FROM (VALUES ('ai_res_api_group'), ('ai_res_outbox_group'), ('ai_res_consumer_group'),
  ('ai_res_auditor_group'), ('ai_res_checkpointer_group')) v(r) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) \gexec
SELECT format('CREATE ROLE %I LOGIN', r) FROM (VALUES ('ai_res_migrator'), ('ai_res_api'), ('ai_res_outbox_dispatcher'), ('ai_res_event_consumer'),
  ('ai_res_auditor'), ('ai_res_backup')) v(r) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) \gexec
SELECT 'CREATE DATABASE ai_res_db OWNER ai_res_owner' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_res_db') \gexec

-- Attributes: none of them may ever carry SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS.
ALTER ROLE ai_res_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_api_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_outbox_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_consumer_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_auditor_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_checkpointer_group NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE ai_res_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'migrator_pw';
ALTER ROLE ai_res_api LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'api_pw';
ALTER ROLE ai_res_outbox_dispatcher LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'outbox_pw';
ALTER ROLE ai_res_event_consumer LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'consumer_pw';
ALTER ROLE ai_res_auditor LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'auditor_pw';
SELECT 'ALTER ROLE ai_res_checkpointer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
 WHERE EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_res_checkpointer') \gexec
-- Backup identity: no data privileges here; its pgBackRest privilege profile is defined with the backup stage (S32, KNOWN_GAPS).
ALTER ROLE ai_res_backup LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'backup_pw';

-- Membership. Anything that is not in the expected set is revoked (drift correction): nobody except the migrator may be a member of the
-- owner, and no ai_res_* identity may hold any other role (e.g. pg_read_all_data) or have unexpected members.
SELECT format('REVOKE %I FROM %I GRANTED BY %I', g.rolname, m.rolname, gr.rolname)
  FROM pg_auth_members am JOIN pg_roles g ON g.oid = am.roleid JOIN pg_roles m ON m.oid = am.member JOIN pg_roles gr ON gr.oid = am.grantor
 WHERE (m.rolname LIKE 'ai\_res\_%' OR g.rolname LIKE 'ai\_res\_%')
   AND (g.rolname, m.rolname) NOT IN (('ai_res_api_group', 'ai_res_api'), ('ai_res_outbox_group', 'ai_res_outbox_dispatcher'),
        ('ai_res_consumer_group', 'ai_res_event_consumer'), ('ai_res_auditor_group', 'ai_res_auditor'), ('ai_res_owner', 'ai_res_migrator'),
        ('ai_res_checkpointer_group', 'ai_res_checkpointer')) \gexec
-- Options are asserted explicitly: a leftover ADMIN OPTION would let the member hand the role on. REVOKE ... OPTION FOR clears the flags first.
REVOKE ADMIN OPTION FOR ai_res_owner FROM ai_res_migrator;
REVOKE ADMIN OPTION FOR ai_res_api_group FROM ai_res_api;
REVOKE ADMIN OPTION FOR ai_res_outbox_group FROM ai_res_outbox_dispatcher;
REVOKE ADMIN OPTION FOR ai_res_consumer_group FROM ai_res_event_consumer;
REVOKE ADMIN OPTION FOR ai_res_auditor_group FROM ai_res_auditor;
GRANT ai_res_owner TO ai_res_migrator WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT ai_res_api_group TO ai_res_api WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT ai_res_outbox_group TO ai_res_outbox_dispatcher WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT ai_res_consumer_group TO ai_res_event_consumer WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT ai_res_auditor_group TO ai_res_auditor WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
SELECT 'GRANT ai_res_checkpointer_group TO ai_res_checkpointer WITH ADMIN FALSE, INHERIT TRUE, SET FALSE' WHERE EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_res_checkpointer') \gexec

-- Database access: PUBLIC has nothing; only the identities that must connect. The backup identity gets no application connect right.
ALTER DATABASE ai_res_db OWNER TO ai_res_owner;  -- drift correction: the database is owned by the NOLOGIN owner, never by a login role
REVOKE ALL ON DATABASE ai_res_db FROM PUBLIC;
SELECT format('REVOKE ALL ON DATABASE ai_res_db FROM %I', r.rolname)  -- any explicit grant outside the expected set is drift
  FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a JOIN pg_roles r ON r.oid = a.grantee
 WHERE d.datname = 'ai_res_db' AND a.grantee <> 0 AND r.rolname <> 'ai_res_owner'
   AND r.rolname NOT IN ('ai_res_migrator', 'ai_res_api', 'ai_res_outbox_dispatcher', 'ai_res_event_consumer', 'ai_res_auditor', 'ai_res_checkpointer', 'postgres')
 GROUP BY r.rolname \gexec
GRANT CONNECT ON DATABASE ai_res_db TO ai_res_migrator, ai_res_api, ai_res_outbox_dispatcher, ai_res_event_consumer, ai_res_auditor;

-- Runtime defaults (fixed search_path = pg_catalog; timeouts are WORKING technical values from DOC-069 §8, ADR-046, not SLOs).
-- No tenant GUC is ever set at role/session level. RESET ALL first, so a manually added setting cannot survive a re-run.
SELECT format('ALTER ROLE %I IN DATABASE %I RESET ALL', r.rolname, d.datname)
  FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole JOIN pg_database d ON d.oid = s.setdatabase
 WHERE s.setdatabase <> 0 AND r.rolname LIKE 'ai\_res\_%' \gexec
ALTER ROLE ai_res_migrator RESET ALL;
ALTER ROLE ai_res_api RESET ALL;
ALTER ROLE ai_res_outbox_dispatcher RESET ALL;
ALTER ROLE ai_res_event_consumer RESET ALL;
ALTER ROLE ai_res_auditor RESET ALL;
ALTER ROLE ai_res_backup RESET ALL;
ALTER ROLE ai_res_api SET search_path = pg_catalog;
ALTER ROLE ai_res_outbox_dispatcher SET search_path = pg_catalog;
ALTER ROLE ai_res_event_consumer SET search_path = pg_catalog;
ALTER ROLE ai_res_auditor SET search_path = pg_catalog;
ALTER ROLE ai_res_api SET statement_timeout = '15s';
ALTER ROLE ai_res_outbox_dispatcher SET statement_timeout = '15s';
ALTER ROLE ai_res_event_consumer SET statement_timeout = '15s';
ALTER ROLE ai_res_auditor SET statement_timeout = '15s';
ALTER ROLE ai_res_api SET lock_timeout = '2s';
ALTER ROLE ai_res_outbox_dispatcher SET lock_timeout = '2s';
ALTER ROLE ai_res_event_consumer SET lock_timeout = '2s';
ALTER ROLE ai_res_auditor SET lock_timeout = '2s';
ALTER ROLE ai_res_api SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE ai_res_outbox_dispatcher SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE ai_res_event_consumer SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE ai_res_auditor SET idle_in_transaction_session_timeout = '30s';
