"""S15: Model Registry (platform.model_profiles) - immutable, versioned model profiles with an approval lifecycle (ADR-106).

Revision ID: f3a9c1d7b542
Revises: e8b4d2f6a193

Additive: one new table, nothing existing is touched. DOC-076 §3 lists the fields; the column shapes below are ADR-106 (WORKING):
* one row = one immutable VERSION of a routing alias (`profile_key`, `profile_version`); provider, model id, the PINNED model version, capabilities, limits,
  classifications, regions, egress, cost rates and timeouts never change after creation (evaluation/release evidence references an immutable version);
* only the lifecycle moves, forward only: CANDIDATE -> APPROVED -> DEPRECATED -> RETIRED (may skip), and a row is never deleted or truncated (a WorkerRun records the
  profile that answered);
* a profile is created CANDIDATE; APPROVED needs `approved_at` AND `approved_by` (a human; nothing automatic approves a profile, project-context.md);
* a floating alias such as `latest` is not a pin: refused by CHECK as well as by the application model;
* global reference data like `iam.roles` (ADR-050): runtime SELECT-only, written only by revisions/the owner, hence RLS-exempt with a reason in `rls_coverage.sql`.
No profile is seeded: the first one arrives with the provider decision (OD-01, S16). Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "f3a9c1d7b542"
down_revision: str | None = "e8b4d2f6a193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
CREATE TABLE platform.model_profiles (
    id uuid CONSTRAINT pk_model_profiles PRIMARY KEY,
    profile_key text NOT NULL CONSTRAINT ck_model_profiles_profile_key CHECK (profile_key ~ '^[a-z][a-z0-9_.-]{0,63}$'),
    profile_version integer NOT NULL CONSTRAINT ck_model_profiles_profile_version CHECK (profile_version >= 1),
    provider text NOT NULL CONSTRAINT ck_model_profiles_provider CHECK (length(provider) BETWEEN 1 AND 64),
    provider_model_id text NOT NULL CONSTRAINT ck_model_profiles_provider_model_id CHECK (length(provider_model_id) BETWEEN 1 AND 200),
    pinned_model_version text NOT NULL CONSTRAINT ck_model_profiles_pinned_model_version CHECK (length(btrim(pinned_model_version)) BETWEEN 1 AND 100 AND lower(btrim(pinned_model_version)) NOT IN ('latest','stable','default','current','newest')),
    capabilities text[] NOT NULL CONSTRAINT ck_model_profiles_capabilities CHECK (cardinality(capabilities) >= 1 AND capabilities <@ ARRAY['CHAT','STRUCTURED_OUTPUT','TOOL_CALLING','STREAMING','VISION','EMBEDDING']),
    context_window_tokens integer NOT NULL CONSTRAINT ck_model_profiles_context_window_tokens CHECK (context_window_tokens >= 1),
    max_output_tokens integer NOT NULL CONSTRAINT ck_model_profiles_max_output_tokens CHECK (max_output_tokens >= 1 AND max_output_tokens <= context_window_tokens),
    data_classifications text[] NOT NULL CONSTRAINT ck_model_profiles_data_classifications CHECK (cardinality(data_classifications) >= 1 AND array_to_string(data_classifications, ',') ~ '^[A-Z][A-Z0-9_]{0,31}(,[A-Z][A-Z0-9_]{0,31})*$'),
    allowed_regions text[] NOT NULL CONSTRAINT ck_model_profiles_allowed_regions CHECK (cardinality(allowed_regions) >= 1 AND array_to_string(allowed_regions, ',') ~ '^[a-z0-9][a-z0-9-]{0,31}(,[a-z0-9][a-z0-9-]{0,31})*$'),
    egress text NOT NULL CONSTRAINT ck_model_profiles_egress CHECK (egress IN ('LOCAL','EXTERNAL')),
    cost_currency text NULL CONSTRAINT ck_model_profiles_cost_currency CHECK (cost_currency ~ '^[A-Z]{3}$'),
    cost_input_per_million numeric(20,6) NULL CONSTRAINT ck_model_profiles_cost_input_per_million CHECK (cost_input_per_million >= 0),
    cost_output_per_million numeric(20,6) NULL CONSTRAINT ck_model_profiles_cost_output_per_million CHECK (cost_output_per_million >= 0),
    rate_limit_rpm integer NULL CONSTRAINT ck_model_profiles_rate_limit_rpm CHECK (rate_limit_rpm >= 1),
    rate_limit_tpm integer NULL CONSTRAINT ck_model_profiles_rate_limit_tpm CHECK (rate_limit_tpm >= 1),
    timeout_seconds numeric(8,3) NOT NULL CONSTRAINT ck_model_profiles_timeout_seconds CHECK (timeout_seconds > 0),
    retry_class text NOT NULL CONSTRAINT ck_model_profiles_retry_class CHECK (retry_class IN ('NONE','BOUNDED')),
    fallback_group text NULL CONSTRAINT ck_model_profiles_fallback_group CHECK (fallback_group ~ '^[a-z][a-z0-9_.-]{0,63}$'),
    evaluation_manifest_ref text NULL CONSTRAINT ck_model_profiles_evaluation_manifest_ref CHECK (length(evaluation_manifest_ref) BETWEEN 1 AND 500),
    status text NOT NULL DEFAULT 'CANDIDATE' CONSTRAINT ck_model_profiles_status CHECK (status IN ('CANDIDATE','APPROVED','DEPRECATED','RETIRED')),
    approved_at timestamptz NULL,
    approved_by uuid NULL CONSTRAINT fk_model_profiles_approved_by_users REFERENCES iam.users(id) ON DELETE RESTRICT,
    deprecated_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_model_profiles_profile_key_profile_version UNIQUE (profile_key, profile_version),
    CONSTRAINT ck_model_profiles_cost_rates_complete CHECK ((cost_currency IS NULL) = (cost_input_per_million IS NULL) AND (cost_currency IS NULL) = (cost_output_per_million IS NULL)),
    CONSTRAINT ck_model_profiles_approval_recorded CHECK (status = 'CANDIDATE' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)));

CREATE FUNCTION platform.guard_model_profile() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE rank_old int; rank_new int;
BEGIN  -- a profile version is a snapshot: born CANDIDATE, only its lifecycle moves, forward only; a row that a run may reference is never deleted
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'CANDIDATE' OR NEW.approved_at IS NOT NULL OR NEW.approved_by IS NOT NULL THEN
      RAISE EXCEPTION 'a model profile is created CANDIDATE and unapproved (approval is a separate, human step)' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'model profile % is never deleted (retire it instead)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'status' - 'approved_at' - 'approved_by' - 'deprecated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'approved_at' - 'approved_by' - 'deprecated_at') THEN
    RAISE EXCEPTION 'model profile % is immutable except for its lifecycle (publish a new profile_version)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.approved_at IS NOT NULL AND (NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.approved_by IS DISTINCT FROM OLD.approved_by) THEN
    RAISE EXCEPTION 'the approval of model profile % is not rewritten', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.deprecated_at IS NOT NULL AND NEW.deprecated_at IS DISTINCT FROM OLD.deprecated_at THEN
    RAISE EXCEPTION 'deprecated_at of model profile % is not rewritten', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  rank_old := array_position(ARRAY['CANDIDATE','APPROVED','DEPRECATED','RETIRED'], OLD.status);
  rank_new := array_position(ARRAY['CANDIDATE','APPROVED','DEPRECATED','RETIRED'], NEW.status);
  IF rank_new < rank_old THEN
    RAISE EXCEPTION 'model profile % status may not go back from % to %', OLD.id, OLD.status, NEW.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_model_profiles_guard BEFORE INSERT OR UPDATE OR DELETE ON platform.model_profiles
  FOR EACH ROW EXECUTE FUNCTION platform.guard_model_profile();
CREATE TRIGGER trg_model_profiles_no_truncate BEFORE TRUNCATE ON platform.model_profiles FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();
-- FK column gets an index (G-59)
CREATE INDEX ix_model_profiles_approved_by ON platform.model_profiles (approved_by);
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute("GRANT SELECT ON platform.model_profiles TO ai_res_api_group")  # global reference data: runtime reads, only revisions/the owner write


def downgrade() -> None:
    raise NotImplementedError("S15 adds a registry that WorkerRun records may reference by id; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
