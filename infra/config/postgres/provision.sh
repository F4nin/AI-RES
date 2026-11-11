#!/bin/bash
# One-shot, idempotent provisioning of databases/roles that exist outside Alembic's remit (S03):
#   temporal_db (+ temporal_visibility_db) owned by role `temporal` (ADR-028), ai_res_db, schema `langgraph` + role ai_res_checkpointer (ADR-036).
# Domain roles are provisioned by provision_roles.sql (S04); schemas/grants/RLS by Alembic (S04+). Passwords are read from Compose secrets inside psql and never reach argv, env or logs.
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

# Domain roles (S04, ADR-015): attributes, passwords, memberships, database grants and fixed role defaults, re-asserted on every run.
# Passwords are read inside psql from Compose secrets (never argv/env/logs); schemas and grants are created later by the Alembic migrate job.
# A failing `cat` inside a psql backtick is not caught by ON_ERROR_STOP and would set an EMPTY password: refuse to run without every secret.
for s in migrator api outbox consumer auditor backup; do
  test -s "/run/secrets/${s}_db_password" || { echo "missing or empty secret ${s}_db_password" >&2; exit 1; }
done
psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d postgres <<'SQL'
\set migrator_pw `cat /run/secrets/migrator_db_password`
\set api_pw `cat /run/secrets/api_db_password`
\set outbox_pw `cat /run/secrets/outbox_db_password`
\set consumer_pw `cat /run/secrets/consumer_db_password`
\set auditor_pw `cat /run/secrets/auditor_db_password`
\set backup_pw `cat /run/secrets/backup_db_password`
\i /provision/provision_roles.sql
SQL
echo "provisioning complete"
