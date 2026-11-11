#!/bin/bash
# One-shot, idempotent provisioning of databases/roles that exist outside Alembic's remit (S03):
#   temporal_db (+ temporal_visibility_db) owned by role `temporal` (ADR-028), ai_res_db, schema `langgraph` + role ai_res_checkpointer (ADR-036).
# Domain roles/RLS/grants belong to S05. Passwords are read from Compose secrets inside psql and never reach argv, env or logs.
set -euo pipefail
umask 077
export PGPASSFILE=/tmp/pgpass
printf 'postgres:5432:*:postgres:%s\n' "$(cat /run/secrets/postgres_superuser_password)" > "$PGPASSFILE"

psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d postgres <<'SQL'
SET log_min_error_statement = panic;  -- statements carrying passwords must not be echoed into the server log on error
SET password_encryption = 'scram-sha-256';
\set temporal_pw `cat /run/secrets/temporal_db_password`
\set checkpointer_pw `cat /run/secrets/checkpointer_db_password`

SELECT 'CREATE ROLE ai_res_owner NOLOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_res_owner') \gexec
SELECT 'CREATE ROLE temporal LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'temporal') \gexec
SELECT 'CREATE ROLE ai_res_checkpointer LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_res_checkpointer') \gexec
ALTER ROLE temporal PASSWORD :'temporal_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE ai_res_checkpointer PASSWORD :'checkpointer_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

SELECT 'CREATE DATABASE ai_res_db OWNER ai_res_owner' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_res_db') \gexec
SELECT 'CREATE DATABASE temporal_db OWNER temporal' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_db') \gexec
SELECT 'CREATE DATABASE temporal_visibility_db OWNER temporal' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility_db') \gexec
REVOKE ALL ON DATABASE ai_res_db, temporal_db, temporal_visibility_db FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
GRANT CONNECT ON DATABASE ai_res_db TO ai_res_checkpointer;
SQL

# Schema `langgraph` is created here (provisioning), never by runtime `setup()` DDL (ADR-036): the checkpointer gets USAGE only - no CREATE,
# no ownership. Checkpoint tables and their DML grants are provisioned with the pinned LangGraph schema in S23.
psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d ai_res_db <<'SQL'
CREATE SCHEMA IF NOT EXISTS langgraph AUTHORIZATION ai_res_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA langgraph TO ai_res_checkpointer;
SQL
echo "provisioning complete"
