"""PDB-0010/0011 (part): artifacts (types, statuses, artifacts, immutable versions, validation_reports, publications), governance (reviews, approvals, change_requests, baselines, baseline_items), S06 slice B.

Revision ID: b9d246f1a3c8
Revises: a1e83c5d7b04

Validation, Review, Approval and Publication are separate insert-only facts (DOC-005 §9.2, Artifacts Lifecycle §6.2). The database refuses a version status that
claims a fact that does not exist: APPROVED needs an APPROVED `governance.approvals` row by a human user for exactly that version, PUBLISHED needs a publication,
IN_BASELINE needs a baseline item. A baseline is an immutable snapshot: it and its items are insert-only and complete at COMMIT (`item_count`).
Artifact status vocabulary and transitions are WORKING (Artifacts Lifecycle §6.1 is an "initial proposed dictionary"): they live in a registry table and a minimal graph. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "b9d246f1a3c8"
down_revision: str | None = "a1e83c5d7b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = ("organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
         "AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid")
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"


def common(t: str) -> str:
    return (f"row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),\n"
            "    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()")


FUNCTIONS = """
CREATE FUNCTION governance.guard_version_facts() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE ok boolean;
BEGIN  -- BEFORE UPDATE of a version status. Args: [0] kind: REQUIREMENT | ARTIFACT. A status may only claim facts that exist for exactly this version.
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
  IF NEW.status = 'APPROVED' THEN
    IF TG_ARGV[0] = 'REQUIREMENT' THEN
      SELECT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.requirement_version_id = NEW.id AND a.decision = 'APPROVED') INTO ok;
    ELSE
      SELECT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.artifact_version_id = NEW.id AND a.decision = 'APPROVED') INTO ok;
    END IF;
    IF NOT ok THEN RAISE EXCEPTION '% version % cannot become APPROVED without an APPROVED approval of a human user for this exact version', TG_ARGV[0], NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSIF NEW.status = 'IN_BASELINE' THEN
    SELECT EXISTS (SELECT 1 FROM governance.baseline_items i WHERE i.requirement_version_id = NEW.id) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'requirement version % cannot become IN_BASELINE without a baseline item', NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSIF NEW.status = 'PUBLISHED' THEN
    SELECT EXISTS (SELECT 1 FROM artifacts.publications p WHERE p.artifact_version_id = NEW.id) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'artifact version % cannot become PUBLISHED without a publication', NEW.id USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION artifacts.guard_publication_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE s text;
BEGIN  -- only an APPROVED (or already PUBLISHED, another channel) version can be published; publication never changes content
  SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
  IF s IS NULL OR s NOT IN ('APPROVED','PUBLISHED') THEN
    RAISE EXCEPTION 'artifact version % is % and cannot be published', NEW.artifact_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION governance.guard_baseline_item_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE b timestamptz; s text;
BEGIN  -- items exist only in the transaction that created the baseline, and only for approved versions
  SELECT created_at INTO b FROM governance.baselines WHERE id = NEW.baseline_id;
  IF b IS NULL OR b <> now() THEN
    RAISE EXCEPTION 'baseline % is sealed: items can only be added in the transaction that creates it', NEW.baseline_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.requirement_version_id IS NOT NULL THEN
    SELECT status INTO s FROM requirements.requirement_versions WHERE id = NEW.requirement_version_id;
    IF s IS NULL OR s NOT IN ('APPROVED','IN_BASELINE') THEN RAISE EXCEPTION 'requirement version % is % and cannot enter a baseline', NEW.requirement_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  ELSE
    SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
    IF s IS NULL OR s NOT IN ('APPROVED','PUBLISHED') THEN RAISE EXCEPTION 'artifact version % is % and cannot enter a baseline', NEW.artifact_version_id, coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION governance.assert_baseline_complete() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE n int; expected int;
BEGIN  -- deferred: the baseline holds exactly item_count items (a partial snapshot rolls the transaction back)
  SELECT item_count INTO expected FROM governance.baselines WHERE id = (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  IF expected IS NULL THEN RETURN NULL; END IF;
  SELECT count(*) INTO n FROM governance.baseline_items WHERE baseline_id = (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  IF n <> expected THEN RAISE EXCEPTION 'baseline % declares % items but holds %', (to_jsonb(NEW) ->> TG_ARGV[0]), expected, n USING ERRCODE = 'integrity_constraint_violation'; END IF;
  RETURN NULL;
END $f$;
"""

TABLES = """
CREATE TABLE artifacts.artifact_types (
    code text CONSTRAINT pk_artifact_types PRIMARY KEY CONSTRAINT ck_artifact_types_code CHECK (code ~ '^[A-Z][A-Z_]*$'),
    title text NOT NULL,
    source_of_truth_mode text NOT NULL CONSTRAINT ck_artifact_types_source_of_truth_mode CHECK (source_of_truth_mode IN ('DOMAIN_MODEL','NATIVE_SPEC','DOCUMENT_SOURCE','EXTERNAL_SOURCE')));
INSERT INTO artifacts.artifact_types (code, title, source_of_truth_mode) VALUES ('REQUIREMENTS_CATALOG','Requirements catalog','DOMAIN_MODEL'),
  ('OPENAPI','OpenAPI specification','NATIVE_SPEC'),('ASYNCAPI','AsyncAPI specification','NATIVE_SPEC'),('JSON_SCHEMA','JSON Schema','NATIVE_SPEC'),
  ('RESEARCH_BRIEF','Research brief','DOCUMENT_SOURCE');

CREATE TABLE artifacts.artifact_version_statuses (code text CONSTRAINT pk_artifact_version_statuses PRIMARY KEY CONSTRAINT ck_artifact_version_statuses_code CHECK (code ~ '^[A-Z][A-Z_]*$'));
INSERT INTO artifacts.artifact_version_statuses (code) VALUES ('DRAFT'),('GENERATING'),('VALIDATION_FAILED'),('READY_FOR_REVIEW'),('IN_REVIEW'),('CHANGES_REQUESTED'),
  ('APPROVED'),('PUBLISHED'),('SUPERSEDED'),('REJECTED'),('ARCHIVED');

CREATE TABLE artifacts.artifacts (
    id uuid CONSTRAINT pk_artifacts PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    artifact_type text NOT NULL CONSTRAINT fk_artifacts_artifact_type_artifact_types REFERENCES artifacts.artifact_types(code) ON DELETE RESTRICT,
    source_of_truth_mode text NOT NULL CONSTRAINT ck_artifacts_source_of_truth_mode CHECK (source_of_truth_mode IN ('DOMAIN_MODEL','NATIVE_SPEC','DOCUMENT_SOURCE','EXTERNAL_SOURCE')),
    title text NOT NULL CONSTRAINT ck_artifacts_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    purpose text NULL, owner_user_id uuid NULL, epic_id uuid NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_artifacts_status CHECK (status IN ('ACTIVE','ARCHIVED')),
    current_version_id uuid NULL,
    last_version_number integer NOT NULL DEFAULT 0 CONSTRAINT ck_artifacts_last_version_number CHECK (last_version_number >= 0),
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_artifacts_last_event_sequence CHECK (last_event_sequence >= 0),
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON_artifacts},
    CONSTRAINT ck_artifacts_pointer_needs_version CHECK (current_version_id IS NULL OR last_version_number > 0),
    CONSTRAINT uq_artifacts_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_artifacts_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_artifacts_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_artifacts_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_artifacts_epic_id ON artifacts.artifacts (epic_id) WHERE epic_id IS NOT NULL;

CREATE TABLE artifacts.artifact_versions (
    id uuid CONSTRAINT pk_artifact_versions PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    version_number integer NOT NULL CONSTRAINT ck_artifact_versions_version_number CHECK (version_number > 0),
    schema_version text NOT NULL CONSTRAINT ck_artifact_versions_schema_version CHECK (length(schema_version) BETWEEN 1 AND 100),
    content_ref jsonb NOT NULL CONSTRAINT ck_artifact_versions_content_ref CHECK (jsonb_typeof(content_ref) = 'object'),
    content_checksum bytea NOT NULL CONSTRAINT ck_artifact_versions_content_checksum CHECK (octet_length(content_checksum) = 32),
    provenance jsonb NOT NULL CONSTRAINT ck_artifact_versions_provenance CHECK (jsonb_typeof(provenance) = 'object'),
    change_reason text NULL, author_type text NOT NULL CONSTRAINT ck_artifact_versions_author_type CHECK (author_type IN ('USER','MANAGER','WORKER_RUN','IMPORT')), author_id uuid NULL,
    status text NOT NULL DEFAULT 'DRAFT' CONSTRAINT fk_artifact_versions_status_artifact_version_statuses REFERENCES artifacts.artifact_version_statuses(code) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_artifact_versions_change_reason CHECK (version_number = 1 OR length(btrim(change_reason)) > 0),
    CONSTRAINT uq_artifact_versions_artifact_id_version_number UNIQUE (artifact_id, version_number),
    CONSTRAINT uq_artifact_versions_artifact_id_id UNIQUE (artifact_id, id),
    CONSTRAINT uq_artifact_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_artifact_versions_artifact_id_artifacts FOREIGN KEY (organization_id, project_id, artifact_id) REFERENCES artifacts.artifacts(organization_id, project_id, id) ON DELETE RESTRICT);
ALTER TABLE artifacts.artifacts ADD CONSTRAINT fk_artifacts_current_version_id_artifact_versions
    FOREIGN KEY (id, current_version_id) REFERENCES artifacts.artifact_versions(artifact_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE artifacts.validation_reports (
    id uuid CONSTRAINT pk_validation_reports PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    artifact_version_id uuid NOT NULL,
    validators jsonb NOT NULL CONSTRAINT ck_validation_reports_validators CHECK (jsonb_typeof(validators) = 'array' AND jsonb_array_length(validators) > 0),
    status text NOT NULL CONSTRAINT ck_validation_reports_status CHECK (status IN ('PASSED','PASSED_WITH_WARNINGS','FAILED','ERROR')),
    findings jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_validation_reports_findings CHECK (jsonb_typeof(findings) = 'array'),
    produced_by_type text NOT NULL CONSTRAINT ck_validation_reports_produced_by_type CHECK (produced_by_type IN ('SYSTEM','SERVICE','WORKER_RUN')), produced_by_id uuid NULL,
    validated_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_validation_reports_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_validation_reports_artifact_version_id ON artifacts.validation_reports (artifact_version_id);

CREATE TABLE governance.change_requests (
    id uuid CONSTRAINT pk_change_requests PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    display_number bigint NOT NULL CONSTRAINT ck_change_requests_display_number CHECK (display_number > 0),
    title text NOT NULL CONSTRAINT ck_change_requests_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    rationale text NOT NULL CONSTRAINT ck_change_requests_rationale CHECK (length(btrim(rationale)) > 0),
    base_baseline_id uuid NULL,
    status text NOT NULL DEFAULT 'DRAFT' CONSTRAINT ck_change_requests_status CHECK (status ~ '^[A-Z][A-Z_]*$'),
    requested_by uuid NOT NULL,
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_change_requests_last_event_sequence CHECK (last_event_sequence >= 0),
    {COMMON_change_requests},
    CONSTRAINT uq_change_requests_organization_id_project_id_display_number UNIQUE (organization_id, project_id, display_number),
    CONSTRAINT uq_change_requests_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_change_requests_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_change_requests_requested_by_users FOREIGN KEY (organization_id, requested_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);

CREATE TABLE governance.baselines (
    id uuid CONSTRAINT pk_baselines PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    baseline_number integer NOT NULL CONSTRAINT ck_baselines_baseline_number CHECK (baseline_number > 0),
    name text NOT NULL CONSTRAINT ck_baselines_name CHECK (length(btrim(name)) BETWEEN 1 AND 240),
    previous_baseline_id uuid NULL, change_request_id uuid NULL,
    item_count integer NOT NULL CONSTRAINT ck_baselines_item_count CHECK (item_count > 0),
    last_event_sequence bigint NOT NULL DEFAULT 1 CONSTRAINT ck_baselines_last_event_sequence CHECK (last_event_sequence = 1),
    created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_baselines_change_control CHECK ((previous_baseline_id IS NULL) = (baseline_number = 1) AND (baseline_number = 1 OR change_request_id IS NOT NULL)),
    CONSTRAINT uq_baselines_organization_id_project_id_baseline_number UNIQUE (organization_id, project_id, baseline_number),
    CONSTRAINT uq_baselines_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_baselines_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_baselines_previous_baseline_id_baselines FOREIGN KEY (organization_id, project_id, previous_baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_baselines_change_request_id_change_requests FOREIGN KEY (organization_id, project_id, change_request_id) REFERENCES governance.change_requests(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_baselines_created_by_users FOREIGN KEY (organization_id, created_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
ALTER TABLE governance.change_requests ADD CONSTRAINT fk_change_requests_base_baseline_id_baselines
    FOREIGN KEY (organization_id, project_id, base_baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT;

CREATE TABLE governance.baseline_items (
    id uuid CONSTRAINT pk_baseline_items PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    baseline_id uuid NOT NULL, requirement_version_id uuid NULL, artifact_version_id uuid NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_baseline_items_exactly_one_target CHECK ((requirement_version_id IS NOT NULL) <> (artifact_version_id IS NOT NULL)),
    CONSTRAINT fk_baseline_items_baseline_id_baselines FOREIGN KEY (organization_id, project_id, baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_baseline_items_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_baseline_items_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE UNIQUE INDEX uq_baseline_items_requirement ON governance.baseline_items (baseline_id, requirement_version_id) WHERE requirement_version_id IS NOT NULL;
CREATE UNIQUE INDEX uq_baseline_items_artifact ON governance.baseline_items (baseline_id, artifact_version_id) WHERE artifact_version_id IS NOT NULL;
CREATE INDEX ix_baseline_items_requirement_version_id ON governance.baseline_items (requirement_version_id) WHERE requirement_version_id IS NOT NULL;
CREATE INDEX ix_baseline_items_artifact_version_id ON governance.baseline_items (artifact_version_id) WHERE artifact_version_id IS NOT NULL;

CREATE TABLE governance.reviews (
    id uuid CONSTRAINT pk_reviews PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    requirement_version_id uuid NULL, artifact_version_id uuid NULL,
    reviewer_type text NOT NULL CONSTRAINT ck_reviews_reviewer_type CHECK (reviewer_type IN ('USER','WORKER_RUN')), reviewer_id uuid NOT NULL,
    outcome text NOT NULL CONSTRAINT ck_reviews_outcome CHECK (outcome IN ('NO_FINDINGS','FINDINGS','BLOCKING_FINDINGS')),
    findings jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_reviews_findings CHECK (jsonb_typeof(findings) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_reviews_exactly_one_target CHECK ((requirement_version_id IS NOT NULL) <> (artifact_version_id IS NOT NULL)),
    CONSTRAINT fk_reviews_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_reviews_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_reviews_requirement_version_id ON governance.reviews (requirement_version_id) WHERE requirement_version_id IS NOT NULL;
CREATE INDEX ix_reviews_artifact_version_id ON governance.reviews (artifact_version_id) WHERE artifact_version_id IS NOT NULL;

CREATE TABLE governance.approvals (
    id uuid CONSTRAINT pk_approvals PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    requirement_version_id uuid NULL, artifact_version_id uuid NULL, baseline_id uuid NULL,
    decision text NOT NULL CONSTRAINT ck_approvals_decision CHECK (decision IN ('APPROVED','REJECTED')),
    approver_user_id uuid NOT NULL,
    rationale text NULL, decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_approvals_exactly_one_target CHECK ((requirement_version_id IS NOT NULL)::int + (artifact_version_id IS NOT NULL)::int + (baseline_id IS NOT NULL)::int = 1),
    CONSTRAINT fk_approvals_approver_user_id_users FOREIGN KEY (organization_id, approver_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_approvals_requirement_version_id_requirement_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_approvals_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_approvals_baseline_id_baselines FOREIGN KEY (organization_id, project_id, baseline_id) REFERENCES governance.baselines(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_approvals_requirement_version_id ON governance.approvals (requirement_version_id) WHERE requirement_version_id IS NOT NULL;
CREATE INDEX ix_approvals_artifact_version_id ON governance.approvals (artifact_version_id) WHERE artifact_version_id IS NOT NULL;
CREATE INDEX ix_approvals_baseline_id ON governance.approvals (baseline_id) WHERE baseline_id IS NOT NULL;
CREATE INDEX ix_approvals_approver_user_id ON governance.approvals (approver_user_id);

CREATE TABLE artifacts.publications (
    id uuid CONSTRAINT pk_publications PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    artifact_version_id uuid NOT NULL, channel text NOT NULL DEFAULT 'DEFAULT' CONSTRAINT ck_publications_channel CHECK (channel ~ '^[A-Z][A-Z_]*$'),
    published_by uuid NOT NULL, published_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_publications_artifact_version_id_channel UNIQUE (artifact_version_id, channel),
    CONSTRAINT fk_publications_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_publications_published_by_users FOREIGN KEY (organization_id, published_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
"""


def _rls(table: str, grants: str) -> None:
    name = table.split(".")[1]
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({SCOPE}) WITH CHECK ({SCOPE})")
    op.execute(f"CREATE POLICY p_{name}_owner_migration ON {table} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
    op.execute(f"GRANT {grants} ON {table} TO ai_res_api_group")


def _insert_only(table: str) -> None:
    name = table.split(".")[1]
    _rls(table, "SELECT, INSERT")
    op.execute(f"CREATE TRIGGER trg_{name}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute(f"CREATE TRIGGER trg_{name}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def _mutable(table: str, immutable: tuple[str, ...]) -> None:
    name = table.split(".")[1]
    _rls(table, "SELECT, INSERT, UPDATE")
    op.execute(f"CREATE TRIGGER trg_{name}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
    cols = ", ".join(f"'{c}'" for c in immutable)
    op.execute(f"CREATE TRIGGER trg_{name}_immutable_columns BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    sql = TABLES
    for t in ("artifacts", "change_requests"):
        sql = sql.replace("{COMMON_" + t + "}", common(t))
    op.execute(sql)
    op.execute("GRANT SELECT ON artifacts.artifact_types, artifacts.artifact_version_statuses TO ai_res_api_group")

    _mutable("artifacts.artifacts", ("id", "organization_id", "project_id", "artifact_type", "source_of_truth_mode", "created_at", "created_by"))
    _rls("artifacts.artifact_versions", "SELECT, INSERT, UPDATE")
    op.execute("CREATE TRIGGER trg_artifact_versions_immutable_columns BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'id', 'organization_id', 'project_id', 'artifact_id', 'version_number', 'schema_version', 'content_ref', 'content_checksum', 'provenance', 'change_reason', 'author_type', 'author_id', 'created_at')")
    op.execute("CREATE TRIGGER trg_artifact_versions_status BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'DRAFT>GENERATING', 'GENERATING>DRAFT', 'DRAFT>VALIDATION_FAILED', 'GENERATING>VALIDATION_FAILED', 'VALIDATION_FAILED>DRAFT', 'DRAFT>READY_FOR_REVIEW', "
               "'GENERATING>READY_FOR_REVIEW', 'READY_FOR_REVIEW>IN_REVIEW', 'READY_FOR_REVIEW>APPROVED', 'IN_REVIEW>CHANGES_REQUESTED', 'IN_REVIEW>APPROVED', 'IN_REVIEW>REJECTED', "
               "'CHANGES_REQUESTED>DRAFT', 'APPROVED>PUBLISHED', 'APPROVED>SUPERSEDED', 'PUBLISHED>SUPERSEDED', 'DRAFT>ARCHIVED', 'REJECTED>ARCHIVED', 'SUPERSEDED>ARCHIVED')")
    op.execute("CREATE TRIGGER trg_artifact_versions_facts BEFORE UPDATE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_version_facts('ARTIFACT')")
    op.execute("CREATE TRIGGER trg_artifact_versions_no_delete BEFORE DELETE ON artifacts.artifact_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE TRIGGER trg_artifact_versions_no_truncate BEFORE TRUNCATE ON artifacts.artifact_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    for parent, versions, fk in (("artifacts.artifacts", "artifacts.artifact_versions", "artifact_id"),):
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_artifact_versions_version_number AFTER INSERT ON {versions} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_version_number_contiguous('{fk}', '{parent}', '{versions}', '{fk}')")
        op.execute(f"CREATE CONSTRAINT TRIGGER trg_artifacts_version_number AFTER INSERT OR UPDATE OF last_version_number ON {parent} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION platform.assert_version_number_contiguous('id', '{parent}', '{versions}', '{fk}')")
    _insert_only("artifacts.validation_reports")
    _insert_only("artifacts.publications")
    op.execute("CREATE TRIGGER trg_publications_guard_insert BEFORE INSERT ON artifacts.publications FOR EACH ROW EXECUTE FUNCTION artifacts.guard_publication_insert()")

    _mutable("governance.change_requests", ("id", "organization_id", "project_id", "display_number", "requested_by", "created_at"))
    _insert_only("governance.baselines")
    _insert_only("governance.baseline_items")
    op.execute("CREATE TRIGGER trg_baseline_items_guard_insert BEFORE INSERT ON governance.baseline_items FOR EACH ROW EXECUTE FUNCTION governance.guard_baseline_item_insert()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_baseline_items_complete AFTER INSERT ON governance.baseline_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_complete('baseline_id')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_baselines_complete AFTER INSERT ON governance.baselines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_complete('id')")
    _insert_only("governance.reviews")
    _insert_only("governance.approvals")

    # requirement versions may only claim facts that exist (function created above; trigger belongs to the table of revision 0007)
    op.execute("CREATE TRIGGER trg_requirement_versions_facts BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_version_facts('REQUIREMENT')")


def downgrade() -> None:
    raise NotImplementedError("PDB-0010/0011 create domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
