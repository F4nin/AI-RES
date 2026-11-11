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
-- ROLE ai_res_outbox_dispatcher LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS SET idle_in_transaction_session_timeout=30s, lock_timeout=2s, search_path=pg_catalog, statement_timeout=15s
-- ROLE ai_res_outbox_group NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- ROLE ai_res_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS 
-- GRANT ai_res_api_group TO ai_res_api INHERIT=t SET=f
-- GRANT ai_res_auditor_group TO ai_res_auditor INHERIT=t SET=f
-- GRANT ai_res_consumer_group TO ai_res_event_consumer INHERIT=t SET=f
-- GRANT ai_res_outbox_group TO ai_res_outbox_dispatcher INHERIT=t SET=f
-- GRANT ai_res_owner TO ai_res_migrator INHERIT=f SET=t
-- DATABASE ACL ai_res_api=c/ai_res_owner,ai_res_auditor=c/ai_res_owner,ai_res_event_consumer=c/ai_res_owner,ai_res_migrator=c/ai_res_owner,ai_res_outbox_dispatcher=c/ai_res_owner,ai_res_owner=CTc/ai_res_owner

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

SET default_table_access_method = heap;

CREATE TABLE platform.alembic_version (
    version_num character varying(32) NOT NULL
);

ALTER TABLE platform.alembic_version OWNER TO ai_res_owner;

ALTER TABLE ONLY platform.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

GRANT USAGE ON SCHEMA agents TO ai_res_api_group;
GRANT USAGE ON SCHEMA agents TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA agents TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA artifacts TO ai_res_api_group;

GRANT USAGE ON SCHEMA audit TO ai_res_api_group;
GRANT USAGE ON SCHEMA audit TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA audit TO ai_res_consumer_group;
GRANT USAGE ON SCHEMA audit TO ai_res_auditor_group;

GRANT USAGE ON SCHEMA context TO ai_res_api_group;

GRANT USAGE ON SCHEMA decisions TO ai_res_api_group;

GRANT USAGE ON SCHEMA execution TO ai_res_api_group;
GRANT USAGE ON SCHEMA execution TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA governance TO ai_res_api_group;

GRANT USAGE ON SCHEMA iam TO ai_res_api_group;

GRANT USAGE ON SCHEMA integrations TO ai_res_api_group;

GRANT USAGE ON SCHEMA knowledge TO ai_res_api_group;

GRANT USAGE ON SCHEMA operations TO ai_res_api_group;
GRANT USAGE ON SCHEMA operations TO ai_res_outbox_group;
GRANT USAGE ON SCHEMA operations TO ai_res_consumer_group;

GRANT USAGE ON SCHEMA organization TO ai_res_api_group;

GRANT USAGE ON SCHEMA platform TO ai_res_api_group;

GRANT USAGE ON SCHEMA project TO ai_res_api_group;

REVOKE USAGE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA requirements TO ai_res_api_group;

GRANT USAGE ON SCHEMA sources TO ai_res_api_group;

GRANT USAGE ON SCHEMA traceability TO ai_res_api_group;

GRANT USAGE ON SCHEMA work TO ai_res_api_group;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TYPES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC;
