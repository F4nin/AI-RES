"""PDB-0001: domain schemas, ownership, schema-level grants, default privileges (no tables).

Revision ID: 3b7e9c41a0d2
Revises:

Roles themselves are provisioned outside Alembic (ops/postgres/provision_roles.sql; the migrator has no CREATEROLE). This revision
fails fast when that provisioning is missing or weaker than the baseline (ADR-015): it never repairs role attributes.
Table-level grants and RLS arrive with the tables (S05+). Names below are frozen literals: a revision must not depend on code that changes.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "3b7e9c41a0d2"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `platform` already exists (env.py bootstrap for alembic_version); it is verified, not created, here.
NEW_SCHEMAS = (
    "iam", "organization", "project", "work", "requirements", "sources", "knowledge", "decisions", "artifacts",
    "traceability", "governance", "agents", "context", "integrations", "audit", "operations", "execution",
)
ALL_SCHEMAS = (*NEW_SCHEMAS, "platform")
# Schema USAGE per group (least privilege, ADR-034): the API is the only domain writer and needs `audit` for outbox/audit inserts.
USAGE = {
    "ai_res_api_group": ALL_SCHEMAS,
    "ai_res_outbox_group": ("operations", "agents", "audit"),
    "ai_res_consumer_group": ("operations", "agents", "execution", "audit"),
    "ai_res_auditor_group": ("audit",),
}
LOGIN_ROLES = ("ai_res_migrator", "ai_res_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor", "ai_res_backup")
RUNTIME_LOGIN = ("ai_res_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor")
GROUPS = ("ai_res_api_group", "ai_res_outbox_group", "ai_res_consumer_group", "ai_res_auditor_group", "ai_res_checkpointer_group")

PREFLIGHT = """
DO $$
DECLARE r record; missing text;
BEGIN
  IF current_user <> 'ai_res_owner' THEN
    RAISE EXCEPTION 'migrations must run as ai_res_owner (SET ROLE), current_user=%', current_user;
  END IF;
  FOR r IN SELECT n AS rolname FROM unnest(%(required)s::text[]) n LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.rolname) THEN
      RAISE EXCEPTION 'required role % is missing: run ops/postgres/provision_roles.sql first', r.rolname;
    END IF;
  END LOOP;
  SELECT string_agg(rolname, ', ') INTO missing FROM pg_roles
   WHERE rolname = ANY(%(required)s::text[] || ARRAY['ai_res_checkpointer'])  -- created by infra provisioning; checked when present
     AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'roles carry forbidden attributes: %', missing; END IF;
  SELECT string_agg(rolname, ', ') INTO missing FROM pg_roles
   WHERE rolname = ANY(%(logins)s::text[]) AND NOT rolcanlogin;
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'login roles cannot log in: %', missing; END IF;
  SELECT string_agg(rolname, ', ') INTO missing FROM pg_roles
   WHERE rolname = ANY(%(groups)s::text[]) AND rolcanlogin;
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'group roles must be NOLOGIN: %', missing; END IF;
  SELECT string_agg(rolname, ', ') INTO missing FROM pg_roles
   WHERE rolname = ANY(%(runtime)s::text[] || %(groups)s::text[] || ARRAY['ai_res_backup']) AND pg_has_role(rolname, 'ai_res_owner', 'MEMBER');
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'runtime/group roles must not be members of ai_res_owner: %', missing; END IF;
  SELECT string_agg(r2.rolname, ', ') INTO missing FROM pg_roles r2
   WHERE r2.rolname = ANY(%(runtime)s::text[]) AND NOT EXISTS (
     SELECT 1 FROM pg_db_role_setting s WHERE s.setrole = r2.oid AND s.setdatabase = 0 AND 'search_path=pg_catalog' = ANY(s.setconfig));
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'runtime roles lack fixed search_path=pg_catalog: %', missing; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'platform' AND nspowner = (SELECT oid FROM pg_roles WHERE rolname = 'ai_res_owner')) THEN
    RAISE EXCEPTION 'schema platform must exist and be owned by ai_res_owner';
  END IF;
END $$
"""


def _lit(items: Sequence[str]) -> str:
    return "ARRAY[" + ", ".join(f"'{i}'" for i in items) + "]"


def upgrade() -> None:
    required = (*GROUPS, "ai_res_owner", *LOGIN_ROLES)
    op.execute(
        PREFLIGHT.replace("%(required)s", _lit(required)).replace("%(logins)s", _lit(LOGIN_ROLES))
        .replace("%(groups)s", _lit(GROUPS)).replace("%(runtime)s", _lit(RUNTIME_LOGIN))
    )
    # PUBLIC must not create objects anywhere in the database (Strategy §1.9, DBM-012).
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    for schema in NEW_SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema} AUTHORIZATION ai_res_owner")  # strict: an existing schema is drift and must fail
    for schema in ALL_SCHEMAS:
        op.execute(f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC")
    for group, schemas in USAGE.items():
        op.execute(f"GRANT USAGE ON SCHEMA {', '.join(schemas)} TO {group}")  # USAGE only: never CREATE
    # Tables/sequences are closed to PUBLIC by default in PostgreSQL; the explicit REVOKEs document intent. FUNCTIONS/TYPES are the substantive ones
    # (PUBLIC would otherwise get EXECUTE/USAGE). Grants are added in the revision that creates each object.
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TABLES FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON SEQUENCES FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE ai_res_owner REVOKE ALL ON TYPES FROM PUBLIC")


def downgrade() -> None:
    raise NotImplementedError(
        "PDB-0001 is the security baseline of ai_res_db; dropping schemas is destructive. Forward-fix with a new revision, "
        "or restore from backup/PITR with an explicit owner decision (Blueprint §11)."
    )
