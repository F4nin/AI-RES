"""S14: WorkerDefinition registry (agents.worker_definitions, agents.worker_definition_versions) and the FKs that make it the owner of `worker_definition_version_id`.

Revision ID: e8b4d2f6a193
Revises: d5a1c8e7f302

Additive (database-and-migrations.md): new tables, then the FKs as the enforce step; nothing is dropped or rewritten. Domain Model v1.9 lists `agents.worker_definitions` but defines no columns, so the shape below is ADR-102 (WORKING):
* `worker_definitions`: the nine logical Worker roles (BASELINED, project-context.md), seeded here; one row per role. A global registry like `iam.roles`
  (ADR-050): runtime SELECT-only, written only by revisions, hence RLS-exempt with a reason in `rls_coverage.sql`.
* `worker_definition_versions`: an immutable capability version of a role: contract versions it accepts/produces, its output schema id/version and the acceptance
  schema it requires. No version rows are seeded: their content (output schemas, criteria) is WORKING and arrives with the first Worker (S23). Only `status`
  moves, forward only (ACTIVE -> DEPRECATED -> RETIRED), a version is created ACTIVE, and a row is never deleted or truncated (a WorkerRun may point to it).
* `agents.worker_runs` and `execution.readiness_evaluations` now reference a version row, so "wrong capability" is decidable from data and a run cannot name a
  definition that does not exist. The registry is empty here, so a database that already holds runs or evaluations cannot satisfy the FKs: a precondition
  check stops the migration with a clear message (S11-S13 create no runs). Why one transaction is acceptable: the tables are empty by construction, so NOT VALID +
  VALIDATE and the plain indexes hold their locks for no measurable time; a populated database would need the split into two revisions and CONCURRENTLY.
* The database stores the REFERENCE only. Whether a version is ACTIVE or matches the run's contract versions is the Readiness Gate's decision (S22, check_code
  registry is WORKING, ADR-102); it is not duplicated in the start guard. ACTIVE -> RETIRED may skip DEPRECATED on purpose.
Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "e8b4d2f6a193"
down_revision: str | None = "d5a1c8e7f302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("ELICITATION", "RESEARCH", "BUSINESS_ANALYSIS", "REQUIREMENTS", "SYSTEM_ANALYSIS", "API_INTEGRATION", "MODELING_DIAGRAM_VALIDATION",
         "QUALITY_ASSURANCE", "TRACEABILITY_CHANGE")

DDL = f"""
CREATE TABLE agents.worker_definitions (
    id uuid CONSTRAINT pk_worker_definitions PRIMARY KEY,
    worker_role text NOT NULL CONSTRAINT ck_worker_definitions_worker_role CHECK (worker_role IN ({", ".join(f"'{r}'" for r in ROLES)})),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_worker_definitions_worker_role UNIQUE (worker_role));

CREATE TABLE agents.worker_definition_versions (
    id uuid CONSTRAINT pk_worker_definition_versions PRIMARY KEY,
    worker_definition_id uuid NOT NULL CONSTRAINT fk_worker_definition_versions_worker_definition_id REFERENCES agents.worker_definitions(id) ON DELETE RESTRICT,
    version text NOT NULL CONSTRAINT ck_worker_definition_versions_version CHECK (length(version) BETWEEN 1 AND 64),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_worker_definition_versions_status CHECK (status IN ('ACTIVE','DEPRECATED','RETIRED')),
    input_contract_version text NOT NULL CONSTRAINT ck_worker_definition_versions_input_contract_version CHECK (length(input_contract_version) BETWEEN 1 AND 32),
    output_contract_version text NOT NULL CONSTRAINT ck_worker_definition_versions_output_contract_version CHECK (length(output_contract_version) BETWEEN 1 AND 32),
    output_schema_id text NOT NULL CONSTRAINT ck_worker_definition_versions_output_schema_id CHECK (length(output_schema_id) BETWEEN 1 AND 200),
    output_schema_version text NOT NULL CONSTRAINT ck_worker_definition_versions_output_schema_version CHECK (length(output_schema_version) BETWEEN 1 AND 32),
    acceptance_schema jsonb NOT NULL DEFAULT '{{}}'::jsonb CONSTRAINT ck_worker_definition_versions_acceptance_schema CHECK (jsonb_typeof(acceptance_schema) = 'object'),
    runtime_profile_version text NULL CONSTRAINT ck_worker_definition_versions_runtime_profile_version CHECK (length(runtime_profile_version) BETWEEN 1 AND 64),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_worker_definition_versions_worker_definition_id_version UNIQUE (worker_definition_id, version));

CREATE FUNCTION agents.guard_worker_definition_version() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE rank_old int; rank_new int;
BEGIN  -- a version is a snapshot of a capability: it is born ACTIVE, only its status moves, and only forward; a row that a run may reference is never deleted
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'ACTIVE' THEN
      RAISE EXCEPTION 'a worker definition version is created ACTIVE (got %)', NEW.status USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'worker definition version % is never deleted (retire it instead)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.id, NEW.worker_definition_id, NEW.version, NEW.input_contract_version, NEW.output_contract_version, NEW.output_schema_id, NEW.output_schema_version,
      NEW.acceptance_schema, NEW.runtime_profile_version, NEW.created_at)
     IS DISTINCT FROM
     (OLD.id, OLD.worker_definition_id, OLD.version, OLD.input_contract_version, OLD.output_contract_version, OLD.output_schema_id, OLD.output_schema_version,
      OLD.acceptance_schema, OLD.runtime_profile_version, OLD.created_at) THEN
    RAISE EXCEPTION 'worker definition version % is immutable except for its status (publish a new version)', OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  rank_old := array_position(ARRAY['ACTIVE','DEPRECATED','RETIRED'], OLD.status);
  rank_new := array_position(ARRAY['ACTIVE','DEPRECATED','RETIRED'], NEW.status);
  IF rank_new < rank_old THEN
    RAISE EXCEPTION 'worker definition version % status may not go back from % to %', OLD.id, OLD.status, NEW.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_worker_definition_versions_guard BEFORE INSERT OR UPDATE OR DELETE ON agents.worker_definition_versions
  FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_definition_version();

CREATE FUNCTION agents.guard_worker_definition() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- the nine roles are fixed (BASELINED): a definition row is neither renamed nor removed
  RAISE EXCEPTION 'worker definition % is immutable', OLD.id USING ERRCODE = 'integrity_constraint_violation';
END $f$;
CREATE TRIGGER trg_worker_definitions_guard BEFORE UPDATE OR DELETE ON agents.worker_definitions
  FOR EACH ROW EXECUTE FUNCTION agents.guard_worker_definition();
CREATE TRIGGER trg_worker_definitions_no_truncate BEFORE TRUNCATE ON agents.worker_definitions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();
CREATE TRIGGER trg_worker_definition_versions_no_truncate BEFORE TRUNCATE ON agents.worker_definition_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification();

INSERT INTO agents.worker_definitions (id, worker_role) VALUES {", ".join(f"(gen_random_uuid(), '{r}')" for r in ROLES)};

DO $f$
BEGIN  -- the registry starts empty, so no existing run or evaluation can reference it: say so plainly instead of failing inside VALIDATE
  IF EXISTS (SELECT 1 FROM agents.worker_runs) OR EXISTS (SELECT 1 FROM execution.readiness_evaluations) THEN
    RAISE EXCEPTION 'S14 migration 0016 expects no WorkerRun or ReadinessEvaluation rows: their worker_definition_version_id has no registry row to point to' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END $f$;

ALTER TABLE agents.worker_runs ADD CONSTRAINT fk_worker_runs_worker_definition_version_id
  FOREIGN KEY (worker_definition_version_id) REFERENCES agents.worker_definition_versions(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE agents.worker_runs VALIDATE CONSTRAINT fk_worker_runs_worker_definition_version_id;
ALTER TABLE execution.readiness_evaluations ADD CONSTRAINT fk_readiness_evaluations_worker_definition_version_id
  FOREIGN KEY (worker_definition_version_id) REFERENCES agents.worker_definition_versions(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE execution.readiness_evaluations VALIDATE CONSTRAINT fk_readiness_evaluations_worker_definition_version_id;
-- FK columns get an index (G-59): a version is looked up from its runs and evaluations
CREATE INDEX ix_worker_runs_worker_definition_version_id ON agents.worker_runs (worker_definition_version_id);
CREATE INDEX ix_readiness_evaluations_worker_definition_version_id ON execution.readiness_evaluations (worker_definition_version_id);
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in ("agents.worker_definitions", "agents.worker_definition_versions"):
        op.execute(f"GRANT SELECT ON {table} TO ai_res_api_group")  # the registry is global reference data: runtime reads, only revisions write


def downgrade() -> None:
    raise NotImplementedError("S14 adds a registry that runs and evaluations reference; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
