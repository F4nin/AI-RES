"""S18: rule counter and append-only validation/evaluation/exception/control facts.

Revision ID: b621f4d8a905
Revises: a41c8f92d603

No active business rule or permission is seeded. Existing versions stay intact.
The one-time counter initialization is a migration, never runtime MAX()+1.
"""
# ruff: noqa: E501, S608 -- fixed schema/table/column literals only
from collections.abc import Sequence

from alembic import op

revision: str = "b621f4d8a905"
down_revision: str | None = "a41c8f92d603"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
PRJ = "NULLIF(current_setting('app.project_id', true), '')::uuid"
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"

DDL = """
ALTER TABLE governance.rules ADD COLUMN last_version_number integer NOT NULL DEFAULT 0
  CONSTRAINT ck_rules_last_version_number CHECK (last_version_number >= 0);
UPDATE governance.rules r SET last_version_number = s.last_no, row_version = r.row_version + 1
  FROM (SELECT rule_id,max(version_number) AS last_no FROM governance.rule_versions GROUP BY rule_id) s WHERE r.id=s.rule_id;

CREATE TABLE governance.rule_validation_reports (
  id uuid CONSTRAINT pk_rule_validation_reports PRIMARY KEY,
  organization_id uuid NOT NULL, project_id uuid NULL,
  proposal_version_id uuid NOT NULL CONSTRAINT fk_rule_validation_proposal REFERENCES governance.rule_versions(id) ON DELETE RESTRICT,
  proposal_hash bytea NOT NULL CONSTRAINT ck_rule_validation_proposal_hash CHECK (octet_length(proposal_hash)=32),
  basis_hash bytea NOT NULL CONSTRAINT ck_rule_validation_basis_hash CHECK (octet_length(basis_hash)=32),
  basis jsonb NOT NULL CONSTRAINT ck_rule_validation_basis CHECK (jsonb_typeof(basis)='object'),
  result jsonb NOT NULL CONSTRAINT ck_rule_validation_result CHECK (jsonb_typeof(result)='object'),
  result_hash bytea NOT NULL CONSTRAINT ck_rule_validation_result_hash CHECK (octet_length(result_hash)=32),
  actor_id uuid NOT NULL, evaluated_at timestamptz NOT NULL,
  CONSTRAINT fk_rule_validation_scope FOREIGN KEY (organization_id,project_id) REFERENCES project.projects(organization_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_validation_actor FOREIGN KEY (organization_id,actor_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT);

CREATE TABLE governance.rule_evaluations (
  id uuid CONSTRAINT pk_rule_evaluations PRIMARY KEY,
  organization_id uuid NOT NULL, project_id uuid NOT NULL,
  context_version_id uuid NOT NULL, actor_id uuid NOT NULL, evaluated_at timestamptz NOT NULL,
  engine_version text NOT NULL CONSTRAINT ck_rule_evaluations_engine CHECK (engine_version ~ '^[A-Za-z0-9_.-]{1,80}$'),
  schema_version text NOT NULL CONSTRAINT ck_rule_evaluations_schema CHECK (schema_version ~ '^[A-Za-z0-9_.-]{1,80}$'),
  input_snapshot jsonb NOT NULL CONSTRAINT ck_rule_evaluations_input CHECK (jsonb_typeof(input_snapshot)='object'),
  input_hash bytea NOT NULL CONSTRAINT ck_rule_evaluations_input_hash CHECK (octet_length(input_hash)=32),
  result jsonb NOT NULL CONSTRAINT ck_rule_evaluations_result CHECK (jsonb_typeof(result)='object'),
  result_hash bytea NOT NULL CONSTRAINT ck_rule_evaluations_result_hash CHECK (octet_length(result_hash)=32),
  previous_evaluation_id uuid NULL,
  CONSTRAINT uq_rule_evaluations_scope_id UNIQUE (organization_id,project_id,id),
  CONSTRAINT ck_rule_evaluations_not_self CHECK (previous_evaluation_id IS DISTINCT FROM id),
  CONSTRAINT fk_rule_evaluations_context FOREIGN KEY (organization_id,project_id,context_version_id) REFERENCES context.context_package_versions(organization_id,project_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_evaluations_actor FOREIGN KEY (organization_id,actor_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_evaluations_previous FOREIGN KEY (organization_id,project_id,previous_evaluation_id) REFERENCES governance.rule_evaluations(organization_id,project_id,id) ON DELETE RESTRICT);

CREATE TABLE governance.rule_exceptions (
  id uuid CONSTRAINT pk_rule_exceptions PRIMARY KEY,
  organization_id uuid NOT NULL, project_id uuid NOT NULL,
  target_version_id uuid NOT NULL CONSTRAINT fk_rule_exceptions_target REFERENCES governance.rule_versions(id) ON DELETE RESTRICT,
  target_content_hash bytea NOT NULL CONSTRAINT ck_rule_exceptions_content_hash CHECK (octet_length(target_content_hash)=32),
  target_effect_hash bytea NOT NULL CONSTRAINT ck_rule_exceptions_effect_hash CHECK (octet_length(target_effect_hash)=32),
  permission_version_id uuid NOT NULL CONSTRAINT fk_rule_exceptions_permission REFERENCES governance.rule_versions(id) ON DELETE RESTRICT,
  object_type text NOT NULL CONSTRAINT ck_rule_exceptions_object_type CHECK (object_type ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'),
  object_id uuid NOT NULL, operation text NOT NULL CONSTRAINT ck_rule_exceptions_operation CHECK (operation ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'),
  approved_by uuid NOT NULL, approved_at timestamptz NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz NOT NULL,
  reason_code text NOT NULL CONSTRAINT ck_rule_exceptions_reason CHECK (reason_code ~ '^[A-Za-z][A-Za-z0-9_.:-]{0,127}$'),
  risk_refs uuid[] NOT NULL CONSTRAINT ck_rule_exceptions_risks CHECK (cardinality(risk_refs)>0 AND array_position(risk_refs,NULL) IS NULL),
  compensation_refs uuid[] NOT NULL CONSTRAINT ck_rule_exceptions_compensation CHECK (cardinality(compensation_refs)>0 AND array_position(compensation_refs,NULL) IS NULL),
  snapshot jsonb NOT NULL CONSTRAINT ck_rule_exceptions_snapshot CHECK (jsonb_typeof(snapshot)='object'),
  snapshot_hash bytea NOT NULL CONSTRAINT ck_rule_exceptions_snapshot_hash CHECK (octet_length(snapshot_hash)=32),
  CONSTRAINT uq_rule_exceptions_scope_id UNIQUE (organization_id,project_id,id),
  CONSTRAINT ck_rule_exceptions_finite_validity CHECK (isfinite(valid_from) AND isfinite(valid_to) AND valid_to>valid_from AND approved_at<=valid_from),
  CONSTRAINT fk_rule_exceptions_scope FOREIGN KEY (organization_id,project_id) REFERENCES project.projects(organization_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_exceptions_approver FOREIGN KEY (organization_id,approved_by) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT);

CREATE TABLE governance.rule_runtime_controls (
  id uuid CONSTRAINT pk_rule_runtime_controls PRIMARY KEY,
  rule_version_id uuid NOT NULL CONSTRAINT fk_rule_controls_version REFERENCES governance.rule_versions(id) ON DELETE RESTRICT,
  level text NOT NULL CONSTRAINT ck_rule_controls_level CHECK (level IN ('SYSTEM','ORGANIZATION','PROJECT')),
  organization_id uuid NULL, project_id uuid NULL,
  sequence bigint NOT NULL CONSTRAINT ck_rule_controls_sequence CHECK (sequence>0),
  action text NOT NULL CONSTRAINT ck_rule_controls_action CHECK (action IN ('PUBLISH','SUSPEND','RESUME','RETIRE')),
  actor_id uuid NOT NULL, occurred_at timestamptz NOT NULL,
  CONSTRAINT uq_rule_controls_version_sequence UNIQUE (rule_version_id,sequence),
  CONSTRAINT ck_rule_controls_scope CHECK ((level='SYSTEM' AND organization_id IS NULL AND project_id IS NULL) OR (level='ORGANIZATION' AND organization_id IS NOT NULL AND project_id IS NULL)
    OR (level='PROJECT' AND organization_id IS NOT NULL AND project_id IS NOT NULL)),
  CONSTRAINT fk_rule_controls_scope FOREIGN KEY (organization_id,project_id) REFERENCES project.projects(organization_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_controls_actor FOREIGN KEY (organization_id,actor_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT);

CREATE TABLE governance.rule_exception_revocations (
  id uuid CONSTRAINT pk_rule_exception_revocations PRIMARY KEY,
  organization_id uuid NOT NULL, project_id uuid NOT NULL,
  exception_id uuid NOT NULL CONSTRAINT uq_rule_exception_revocations_exception UNIQUE,
  actor_id uuid NOT NULL, revoked_at timestamptz NOT NULL,
  CONSTRAINT fk_rule_exception_revocations_exception FOREIGN KEY (organization_id,project_id,exception_id) REFERENCES governance.rule_exceptions(organization_id,project_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_rule_exception_revocations_actor FOREIGN KEY (organization_id,actor_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT);

CREATE FUNCTION governance.guard_rule_record_scope() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE version_ref uuid; target governance.rule_versions%ROWTYPE;
BEGIN
  version_ref := (to_jsonb(NEW) ->> CASE TG_TABLE_NAME WHEN 'rule_validation_reports' THEN 'proposal_version_id'
     WHEN 'rule_exceptions' THEN 'target_version_id' ELSE 'rule_version_id' END)::uuid;
  SELECT * INTO target FROM governance.rule_versions WHERE id=version_ref;
  IF target.id IS NULL OR target.organization_id IS DISTINCT FROM NEW.organization_id
     OR (target.project_id IS NOT NULL AND target.project_id IS DISTINCT FROM NEW.project_id) THEN
    RAISE EXCEPTION 'rule record is outside its target tenant scope' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF TG_TABLE_NAME='rule_runtime_controls' THEN
    IF target.level IS DISTINCT FROM NEW.level THEN
      RAISE EXCEPTION 'rule control level mismatch' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSIF TG_TABLE_NAME='rule_exceptions' THEN
    IF target.level='SYSTEM' OR NOT EXISTS (SELECT 1 FROM governance.rule_versions p WHERE p.id=NEW.permission_version_id
      AND (p.level='SYSTEM' OR (p.organization_id=NEW.organization_id AND (p.project_id IS NULL OR p.project_id=NEW.project_id)))) THEN
      RAISE EXCEPTION 'rule exception target or permission is outside its scope' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_rule_validation_scope BEFORE INSERT ON governance.rule_validation_reports FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();
CREATE TRIGGER trg_rule_exceptions_scope BEFORE INSERT ON governance.rule_exceptions FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();
CREATE TRIGGER trg_rule_controls_scope BEFORE INSERT ON governance.rule_runtime_controls FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_record_scope();
"""


def upgrade() -> None:
    # FORCE RLS stays enabled; the migration-only owner policy admits the counter initialization.
    op.execute("SELECT set_config('app.migration_mode','on',true)")
    op.execute(DDL)
    for table in ("rule_validation_reports", "rule_evaluations", "rule_exceptions", "rule_runtime_controls", "rule_exception_revocations"):
        t = f"governance.{table}"
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{table}_owner_migration ON {t} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
        scoped = f"organization_id={ORG} AND (project_id IS NULL OR project_id={PRJ})"
        if table == "rule_runtime_controls":
            read = f"level='SYSTEM' OR ({scoped})"
            write = f"level<>'SYSTEM' AND ({scoped})"
        else:
            read = write = scoped
        op.execute(f"CREATE POLICY p_{table}_select ON {t} FOR SELECT TO ai_res_api_group USING ({read})")
        op.execute(f"CREATE POLICY p_{table}_insert ON {t} FOR INSERT TO ai_res_api_group WITH CHECK ({write})")
        op.execute(f"GRANT SELECT,INSERT ON {t} TO ai_res_api_group")
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {t} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    for table, column in (
        ("rule_validation_reports", "proposal_version_id"), ("rule_validation_reports", "actor_id"),
        ("rule_evaluations", "context_version_id"), ("rule_evaluations", "actor_id"), ("rule_evaluations", "previous_evaluation_id"),
        ("rule_exceptions", "target_version_id"), ("rule_exceptions", "permission_version_id"), ("rule_exceptions", "approved_by"),
        ("rule_runtime_controls", "actor_id"), ("rule_exception_revocations", "actor_id"),
    ):
        op.execute(f"CREATE INDEX ix_{table}_{column} ON governance.{table} ({column})")

    for table, suffix, columns in (
        ("rule_validation_reports", "scope", "organization_id,project_id"),
        ("rule_validation_reports", "actor_scope", "organization_id,actor_id"),
        ("rule_evaluations", "context_scope", "organization_id,project_id,context_version_id"),
        ("rule_evaluations", "previous_scope", "organization_id,project_id,previous_evaluation_id"),
        ("rule_evaluations", "actor_scope", "organization_id,actor_id"),
        ("rule_exceptions", "scope", "organization_id,project_id"),
        ("rule_exceptions", "approver_scope", "organization_id,approved_by"),
        ("rule_runtime_controls", "scope", "organization_id,project_id"),
        ("rule_runtime_controls", "actor_scope", "organization_id,actor_id"),
        ("rule_exception_revocations", "exception_scope", "organization_id,project_id,exception_id"),
        ("rule_exception_revocations", "actor_scope", "organization_id,actor_id"),
    ):
        op.execute(f"CREATE INDEX ix_{table}_{suffix} ON governance.{table} ({columns})")


def downgrade() -> None:
    raise NotImplementedError("Rules evidence is append-only; forward-fix or restore with approval.")
