"""PDB-0002a: iam, organization, project tables + shared row guards, RLS, grants (S05 slice A, ADR-016, ADR-050).

Revision ID: 5c1d2e8f7a90
Revises: 3b7e9c41a0d2

Greenfield (ADR-011): constraints are final from the first revision. Names below are frozen literals (a revision must not depend on code that
changes). Every table: ENABLE + FORCE RLS with a transaction-local tenant policy (default deny without context); `ai_res_api_group` gets
SELECT/INSERT/UPDATE only (never DELETE/TRUNCATE; grants_audit.sql enforces it).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "5c1d2e8f7a90"
down_revision: str | None = "3b7e9c41a0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"
COMMON = """row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"""

GUARDS = """
CREATE FUNCTION platform.touch_row() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF NEW.row_version IS DISTINCT FROM OLD.row_version + 1 THEN
    RAISE EXCEPTION 'row_version must advance by exactly 1 (expected %, got %): optimistic concurrency is mandatory', OLD.row_version + 1, NEW.row_version
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $f$;
CREATE FUNCTION platform.keep_columns_immutable() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF n -> c IS DISTINCT FROM o -> c THEN
      RAISE EXCEPTION 'column %.% is immutable', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $f$;
CREATE FUNCTION platform.forbid_unset() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN  -- once set, these columns (revoked_at, used_at, ...) never change again: a revoked session / used recovery code cannot be resurrected
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF o -> c <> 'null'::jsonb AND n -> c IS DISTINCT FROM o -> c THEN
      RAISE EXCEPTION 'column %.% is write-once', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $f$;
CREATE FUNCTION platform.keep_terminal_status() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- TG_ARGV[0] = terminal status of a `status` column (REVOKED): it can be entered but never left
  IF OLD.status = TG_ARGV[0] AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION '%.status % is terminal', TG_TABLE_NAME, TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE FUNCTION platform.reject_modification() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  RAISE EXCEPTION '%.% is immutable: % rejected', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $f$;
"""

TABLES = f"""
CREATE TABLE organization.organizations (
    id uuid CONSTRAINT pk_organizations PRIMARY KEY,
    name text NOT NULL CONSTRAINT ck_organizations_name CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_organizations_status CHECK (status IN ('ACTIVE','ARCHIVED')),
    {COMMON.format(t="organizations")});

CREATE TABLE iam.roles (
    code text CONSTRAINT pk_roles PRIMARY KEY CONSTRAINT ck_roles_code CHECK (code ~ '^[A-Z][A-Z_]*$'),
    org_level boolean NOT NULL, project_level boolean NOT NULL,
    CONSTRAINT ck_roles_level CHECK (org_level OR project_level),
    CONSTRAINT uq_roles_code_org_level UNIQUE (code, org_level),
    CONSTRAINT uq_roles_code_project_level UNIQUE (code, project_level));
INSERT INTO iam.roles (code, org_level, project_level) VALUES
  ('ORGANIZATION_OWNER', true, false), ('ORGANIZATION_ADMIN', true, false), ('PROJECT_ADMIN', false, true), ('ANALYST', false, true),
  ('REVIEWER_APPROVER', false, true), ('READ_ONLY_VIEWER', false, true), ('AUDITOR', true, true);

CREATE TABLE iam.users (
    id uuid CONSTRAINT pk_users PRIMARY KEY,
    organization_id uuid NOT NULL CONSTRAINT fk_users_organization_id_organizations REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    email text NOT NULL CONSTRAINT ck_users_email CHECK (length(email) BETWEEN 3 AND 320),
    email_normalized text NOT NULL CONSTRAINT ck_users_email_normalized CHECK (email_normalized = lower(btrim(email_normalized))),
    display_name text NOT NULL CONSTRAINT ck_users_display_name CHECK (length(btrim(display_name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE','DISABLED')),
    {COMMON.format(t="users")},
    CONSTRAINT uq_users_organization_id_id UNIQUE (organization_id, id),
    CONSTRAINT uq_users_organization_id_email_normalized UNIQUE (organization_id, email_normalized));

CREATE TABLE iam.credentials (
    id uuid CONSTRAINT pk_credentials PRIMARY KEY,
    organization_id uuid NOT NULL, user_id uuid NOT NULL,
    kind text NOT NULL CONSTRAINT ck_credentials_kind CHECK (kind IN ('PASSWORD')),
    password_hash text NOT NULL CONSTRAINT ck_credentials_argon2id CHECK (password_hash LIKE '$argon2id$%' AND length(password_hash) <= 512),
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    {COMMON.format(t="credentials")},
    CONSTRAINT fk_credentials_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_credentials_user_id_kind UNIQUE (user_id, kind));

CREATE TABLE iam.sessions (
    id uuid CONSTRAINT pk_sessions PRIMARY KEY,
    organization_id uuid NOT NULL, user_id uuid NOT NULL,
    session_digest bytea NOT NULL CONSTRAINT ck_sessions_session_digest CHECK (octet_length(session_digest) = 32),
    csrf_digest bytea NOT NULL CONSTRAINT ck_sessions_csrf_digest CHECK (octet_length(csrf_digest) = 32),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL, absolute_expires_at timestamptz NOT NULL,
    mfa_verified_at timestamptz NULL, revoked_at timestamptz NULL,
    revoked_reason text NULL CONSTRAINT ck_sessions_revoked_reason CHECK (revoked_reason IS NULL OR length(revoked_reason) <= 100),
    {COMMON.format(t="sessions")},
    CONSTRAINT ck_sessions_revocation CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL)),
    CONSTRAINT ck_sessions_idle_within_absolute CHECK (idle_expires_at <= absolute_expires_at),
    CONSTRAINT fk_sessions_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_sessions_session_digest UNIQUE (session_digest));
CREATE INDEX ix_sessions_user_id_active ON iam.sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE iam.mfa_factors (
    id uuid CONSTRAINT pk_mfa_factors PRIMARY KEY,
    organization_id uuid NOT NULL, user_id uuid NOT NULL,
    factor_type text NOT NULL CONSTRAINT ck_mfa_factors_factor_type CHECK (factor_type IN ('TOTP')),
    secret_ciphertext bytea NOT NULL CONSTRAINT ck_mfa_factors_secret CHECK (octet_length(secret_ciphertext) > 0),
    status text NOT NULL DEFAULT 'PENDING' CONSTRAINT ck_mfa_factors_status CHECK (status IN ('PENDING','ACTIVE','REVOKED')),
    confirmed_at timestamptz NULL,
    {COMMON.format(t="mfa_factors")},
    CONSTRAINT fk_mfa_factors_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
CREATE UNIQUE INDEX ux_mfa_factors_active_per_user ON iam.mfa_factors (user_id, factor_type) WHERE status <> 'REVOKED';

CREATE TABLE iam.mfa_recovery_codes (
    id uuid CONSTRAINT pk_mfa_recovery_codes PRIMARY KEY,
    organization_id uuid NOT NULL, user_id uuid NOT NULL,
    code_digest bytea NOT NULL CONSTRAINT ck_mfa_recovery_codes_digest CHECK (octet_length(code_digest) = 32),
    used_at timestamptz NULL,
    {COMMON.format(t="mfa_recovery_codes")},
    CONSTRAINT fk_mfa_recovery_codes_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_mfa_recovery_codes_user_id_code_digest UNIQUE (user_id, code_digest));

CREATE TABLE iam.service_identities (
    id uuid CONSTRAINT pk_service_identities PRIMARY KEY,
    organization_id uuid NOT NULL CONSTRAINT fk_service_identities_organization_id_organizations REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    service_kind text NOT NULL CONSTRAINT ck_service_identities_kind CHECK (service_kind IN
      ('API','MANAGER_RUNTIME','WORKER_RUNTIME','TEMPORAL_ACTIVITY','CONNECTOR','LLM_GATEWAY')),
    name text NOT NULL CONSTRAINT ck_service_identities_name CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_service_identities_status CHECK (status IN ('ACTIVE','DISABLED')),
    {COMMON.format(t="service_identities")},
    CONSTRAINT uq_service_identities_organization_id_name UNIQUE (organization_id, name));

CREATE TABLE organization.memberships (
    id uuid CONSTRAINT pk_memberships PRIMARY KEY,
    organization_id uuid NOT NULL, user_id uuid NOT NULL,
    role_code text NOT NULL, org_level boolean NOT NULL DEFAULT true CONSTRAINT ck_memberships_org_level CHECK (org_level),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_memberships_status CHECK (status IN ('ACTIVE','SUSPENDED','REVOKED')),
    {COMMON.format(t="memberships")},
    CONSTRAINT fk_memberships_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_memberships_role_code_org_level_roles FOREIGN KEY (role_code, org_level) REFERENCES iam.roles(code, org_level) ON DELETE RESTRICT,
    CONSTRAINT uq_memberships_organization_id_user_id UNIQUE (organization_id, user_id));

CREATE TABLE project.projects (
    id uuid CONSTRAINT pk_projects PRIMARY KEY,
    organization_id uuid NOT NULL CONSTRAINT fk_projects_organization_id_organizations REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    name text NOT NULL CONSTRAINT ck_projects_name CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    description text NULL,
    project_type text NOT NULL CONSTRAINT ck_projects_project_type CHECK (project_type IN ('GREENFIELD','BROWNFIELD','HYBRID','UNKNOWN')),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_projects_status CHECK (status IN ('ACTIVE','ARCHIVED')),
    {COMMON.format(t="projects")},
    CONSTRAINT uq_projects_organization_id_id UNIQUE (organization_id, id));

CREATE TABLE project.project_memberships (
    id uuid CONSTRAINT pk_project_memberships PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, user_id uuid NOT NULL,
    role_code text NOT NULL, project_level boolean NOT NULL DEFAULT true CONSTRAINT ck_project_memberships_project_level CHECK (project_level),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_project_memberships_status CHECK (status IN ('ACTIVE','SUSPENDED','REVOKED')),
    {COMMON.format(t="project_memberships")},
    CONSTRAINT fk_project_memberships_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_project_memberships_organization_id_user_id_users FOREIGN KEY (organization_id, user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_project_memberships_role_code_project_level_roles FOREIGN KEY (role_code, project_level) REFERENCES iam.roles(code, project_level) ON DELETE RESTRICT,
    CONSTRAINT uq_project_memberships_project_id_user_id UNIQUE (project_id, user_id));
"""

# table -> (RLS predicate, immutable columns). `organizations` is scoped by its own id.
MUTABLE = {
    "organization.organizations": ("id = NULLIF(current_setting('app.organization_id', true), '')::uuid", ("id",)),
    "iam.users": (ORG, ("id", "organization_id")), "iam.credentials": (ORG, ("id", "organization_id", "user_id")),
    "iam.sessions": (ORG, ("id", "organization_id", "user_id", "session_digest", "csrf_digest", "absolute_expires_at", "created_at")),  # the absolute lifetime is fixed at login (security.md: 12 h)
    "iam.mfa_factors": (ORG, ("id", "organization_id", "user_id")), "iam.mfa_recovery_codes": (ORG, ("id", "organization_id", "user_id", "code_digest")),
    "iam.service_identities": (ORG, ("id", "organization_id", "service_kind")),
    "organization.memberships": (ORG, ("id", "organization_id", "user_id")),
    "project.projects": (ORG, ("id", "organization_id")),
    "project.project_memberships": (ORG, ("id", "organization_id", "project_id", "user_id")),
}


WRITE_ONCE = {"iam.sessions": ("revoked_at", "revoked_reason"), "iam.mfa_recovery_codes": ("used_at",)}
REVOKED_IS_TERMINAL = ("iam.mfa_factors", "organization.memberships", "project.project_memberships")


def upgrade() -> None:
    op.execute(GUARDS)
    op.execute(TABLES)
    for table, (predicate, immutable) in MUTABLE.items():
        name = table.split(".")[1]
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({predicate}) WITH CHECK ({predicate})")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO ai_res_api_group")
        op.execute(f"CREATE TRIGGER trg_{name}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
        cols = ", ".join(f"'{c}'" for c in immutable)
        op.execute(f"CREATE TRIGGER trg_{name}_immutable_columns BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")
    for write_once_table, wo_cols in WRITE_ONCE.items():
        quoted = ", ".join(f"'{c}'" for c in wo_cols)
        op.execute(f"CREATE TRIGGER trg_{write_once_table.split(".")[1]}_write_once BEFORE UPDATE ON {write_once_table} FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset({quoted})")
    for table in REVOKED_IS_TERMINAL:
        op.execute(f"CREATE TRIGGER trg_{table.split('.')[1]}_revoked_terminal BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_terminal_status('REVOKED')")
    op.execute("GRANT SELECT ON iam.roles TO ai_res_api_group")  # reference data: runtime read-only; exempt from RLS (rls_coverage.sql)


def downgrade() -> None:
    raise NotImplementedError("PDB-0002a creates domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
