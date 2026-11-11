"""PDB-0008/0009 (part): requirements (types, requirements, immutable versions, epic/task links), sources (sources, uploads, immutable versions), knowledge.extraction_records, S06 slice A.

Revision ID: a1e83c5d7b04
Revises: f3a96b1c8e47

Identity + immutable version pattern (ADR-056): the aggregate row carries the mutable pointer/counters (`current_version_id`, `last_version_number`,
`row_version`); a version row is insert-only except for the explicitly named lifecycle columns, whose transitions are guarded by the database
(`platform.guard_status_transition`). The pointer is a DEFERRABLE composite FK `(id, current_version_id) -> versions(parent_id, id)`: it can only name a
version of the same aggregate (and therefore of the same tenant). Version numbers are contiguous (checked at COMMIT). Unknown requirement types are stored as
UNKNOWN with the declared text, never mapped to a neighbouring type. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "a1e83c5d7b04"
down_revision: str | None = "f3a96b1c8e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = ("organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
         "AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid")
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"


def common(t: str) -> str:
    return (f"row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),\n"
            "    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()")


FUNCTIONS = """
CREATE FUNCTION platform.guard_status_transition() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE i int; o text := to_jsonb(OLD) ->> TG_ARGV[0]; n text := to_jsonb(NEW) ->> TG_ARGV[0];
BEGIN  -- TG_ARGV[0] = status column, TG_ARGV[1..] = allowed 'FROM>TO' pairs; a status that is not changed is not checked
  IF o IS NOT DISTINCT FROM n THEN RETURN NEW; END IF;
  FOR i IN 1 .. TG_NARGS - 1 LOOP
    IF TG_ARGV[i] = o || '>' || n THEN RETURN NEW; END IF;
  END LOOP;
  RAISE EXCEPTION '%.% status transition % -> % is not allowed', TG_TABLE_SCHEMA, TG_TABLE_NAME, o, n USING ERRCODE = 'integrity_constraint_violation';
END $f$;

CREATE FUNCTION platform.advance_by_one() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- TG_ARGV[0] = counter column: a numbering counter moves forward by exactly one per statement (no gaps, no rewinding, no jumps)
  IF (to_jsonb(NEW) ->> TG_ARGV[0])::bigint <> (to_jsonb(OLD) ->> TG_ARGV[0])::bigint + 1 THEN
    RAISE EXCEPTION '%.% must advance by exactly 1', TG_TABLE_NAME, TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION platform.assert_version_number_contiguous() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE pid uuid; last_no int; mx int; no int; has_prev boolean;
BEGIN  -- deferred to COMMIT. Args: [0] column of NEW holding the aggregate id, [1] aggregate table, [2] version table, [3] version-table FK column to the aggregate.
  pid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
  EXECUTE format('SELECT last_version_number FROM %s WHERE id = $1', TG_ARGV[1]::regclass) INTO last_no USING pid;
  IF last_no IS NULL THEN RETURN NULL; END IF;
  EXECUTE format('SELECT coalesce(max(version_number), 0) FROM %s WHERE %I = $1', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO mx USING pid;
  IF mx <> last_no THEN
    RAISE EXCEPTION 'version numbers of % are not contiguous: last_version_number=%, max version number=%', pid, last_no, mx USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_RELID <> TG_ARGV[2]::regclass THEN RETURN NULL; END IF;
  no := (to_jsonb(NEW) ->> 'version_number')::int;
  IF no > 1 THEN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE %I = $1 AND version_number = $2)', TG_ARGV[2]::regclass, TG_ARGV[3]) INTO has_prev USING pid, no - 1;
    IF NOT has_prev THEN RAISE EXCEPTION 'version numbers of % have a gap before %', pid, no USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END IF;
  RETURN NULL;
END $f$;

CREATE FUNCTION sources.guard_source_version_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE u record;
BEGIN  -- a version made from an upload needs a VERIFIED upload of the SAME source with the same checksum, size and media type (checksum verified before processing)
  IF NEW.upload_id IS NOT NULL THEN
    SELECT * INTO u FROM sources.uploads WHERE id = NEW.upload_id;
    IF NOT FOUND OR u.status <> 'VERIFIED' OR u.source_id <> NEW.source_id OR u.verified_sha256 <> NEW.checksum_sha256 OR u.actual_size_bytes <> NEW.size_bytes
       OR u.object_key IS DISTINCT FROM NEW.object_key OR u.declared_media_type <> NEW.media_type THEN
      RAISE EXCEPTION 'source version %: its upload is missing, not VERIFIED, or does not match source/checksum/size/media type/object key', NEW.id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $f$;
"""

TABLES = """
CREATE TABLE platform.display_number_counters (
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    counter_kind text NOT NULL CONSTRAINT ck_display_number_counters_counter_kind CHECK (counter_kind ~ '^[A-Z][A-Z_]*$'),
    last_number bigint NOT NULL DEFAULT 0 CONSTRAINT ck_display_number_counters_last_number CHECK (last_number >= 0),
    CONSTRAINT pk_display_number_counters PRIMARY KEY (organization_id, project_id, counter_kind),
    CONSTRAINT fk_display_number_counters_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);

CREATE TABLE requirements.requirement_types (
    code text CONSTRAINT pk_requirement_types PRIMARY KEY CONSTRAINT ck_requirement_types_code CHECK (code ~ '^[A-Za-z][A-Za-z]*$'),
    title text NOT NULL);
INSERT INTO requirements.requirement_types (code, title) VALUES ('BR','Business requirement'),('StR','Stakeholder requirement'),('UR','User requirement'),
  ('FR','Functional requirement'),('NFR','Non-functional requirement'),('SyR','System requirement'),('IR','Interface requirement'),('DR','Data requirement'),
  ('IntR','Integration requirement'),('CON','Constraint'),('TR','Transition requirement'),('UNKNOWN','Type not in the registry (declared text kept; owner decision pending)');

CREATE TABLE requirements.requirements (
    id uuid CONSTRAINT pk_requirements PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    display_number bigint NOT NULL CONSTRAINT ck_requirements_display_number CHECK (display_number > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_requirements_status CHECK (status IN ('ACTIVE','ARCHIVED')),
    current_version_id uuid NULL,
    last_version_number integer NOT NULL DEFAULT 0 CONSTRAINT ck_requirements_last_version_number CHECK (last_version_number >= 0),
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_requirements_last_event_sequence CHECK (last_event_sequence >= 0),
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON_requirements},
    CONSTRAINT ck_requirements_pointer_needs_version CHECK (current_version_id IS NULL OR last_version_number > 0),
    CONSTRAINT uq_requirements_organization_id_project_id_display_number UNIQUE (organization_id, project_id, display_number),
    CONSTRAINT uq_requirements_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_requirements_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);

CREATE TABLE requirements.requirement_versions (
    id uuid CONSTRAINT pk_requirement_versions PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    version_number integer NOT NULL CONSTRAINT ck_requirement_versions_version_number CHECK (version_number > 0),
    requirement_type text NOT NULL CONSTRAINT fk_requirement_versions_requirement_type_requirement_types REFERENCES requirements.requirement_types(code) ON DELETE RESTRICT,
    declared_type_text text NULL CONSTRAINT ck_requirement_versions_declared_type_text CHECK (length(btrim(declared_type_text)) BETWEEN 1 AND 100),
    statement text NOT NULL CONSTRAINT ck_requirement_versions_statement CHECK (length(btrim(statement)) > 0),
    rationale text NULL, priority text NULL CONSTRAINT ck_requirement_versions_priority CHECK (priority ~ '^[A-Z][A-Z_]*$'),
    acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_requirement_versions_acceptance_criteria CHECK (jsonb_typeof(acceptance_criteria) = 'array'),
    constraints_info jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_requirement_versions_constraints_info CHECK (jsonb_typeof(constraints_info) = 'array'),
    provenance_refs jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_requirement_versions_provenance_refs CHECK (jsonb_typeof(provenance_refs) = 'array'),
    change_reason text NULL,
    author_type text NOT NULL CONSTRAINT ck_requirement_versions_author_type CHECK (author_type IN ('USER','MANAGER','WORKER_RUN','IMPORT')),
    author_id uuid NULL,
    status text NOT NULL DEFAULT 'CANDIDATE' CONSTRAINT ck_requirement_versions_status CHECK (status IN ('EXTRACTED','CANDIDATE','CONFIRMED','APPROVED','IN_BASELINE','SUPERSEDED','REJECTED')),
    confirmed_by uuid NULL, confirmed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_requirement_versions_unknown_type_keeps_text CHECK ((requirement_type = 'UNKNOWN') = (declared_type_text IS NOT NULL)),
    CONSTRAINT ck_requirement_versions_change_reason CHECK (version_number = 1 OR length(btrim(change_reason)) > 0),
    CONSTRAINT ck_requirement_versions_confirmed CHECK ((status IN ('CONFIRMED','APPROVED','IN_BASELINE')) <= (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)),
    CONSTRAINT uq_requirement_versions_requirement_id_version_number UNIQUE (requirement_id, version_number),
    CONSTRAINT uq_requirement_versions_requirement_id_id UNIQUE (requirement_id, id),
    CONSTRAINT uq_requirement_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_requirement_versions_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_requirement_versions_confirmed_by_users FOREIGN KEY (organization_id, confirmed_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
ALTER TABLE requirements.requirements ADD CONSTRAINT fk_requirements_current_version_id_requirement_versions
    FOREIGN KEY (id, current_version_id) REFERENCES requirements.requirement_versions(requirement_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE requirements.requirement_epics (
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    requirement_id uuid NOT NULL, epic_id uuid NOT NULL,
    created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_requirement_epics PRIMARY KEY (requirement_id, epic_id),
    CONSTRAINT fk_requirement_epics_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_requirement_epics_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_requirement_epics_epic_id ON requirements.requirement_epics (epic_id);

CREATE TABLE work.task_requirements (
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    task_id uuid NOT NULL, requirement_id uuid NOT NULL, requirement_version_id uuid NULL,
    created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_task_requirements PRIMARY KEY (task_id, requirement_id),
    CONSTRAINT fk_task_requirements_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_requirements_requirement_id_requirements FOREIGN KEY (organization_id, project_id, requirement_id) REFERENCES requirements.requirements(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_requirements_requirement_version_id_req_versions FOREIGN KEY (requirement_id, requirement_version_id) REFERENCES requirements.requirement_versions(requirement_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_task_requirements_requirement_id ON work.task_requirements (requirement_id);

CREATE TABLE sources.sources (
    id uuid CONSTRAINT pk_sources PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    source_kind text NOT NULL CONSTRAINT ck_sources_source_kind CHECK (source_kind IN ('FILE','OPENAPI_IMPORT','GIT_REPOSITORY')),
    title text NOT NULL CONSTRAINT ck_sources_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    status text NOT NULL DEFAULT 'ACTIVE' CONSTRAINT ck_sources_status CHECK (status IN ('ACTIVE','ARCHIVED')),
    current_version_id uuid NULL,
    last_version_number integer NOT NULL DEFAULT 0 CONSTRAINT ck_sources_last_version_number CHECK (last_version_number >= 0),
    last_event_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_sources_last_event_sequence CHECK (last_event_sequence >= 0),
    created_by uuid NULL, updated_by uuid NULL,
    {COMMON_sources},
    CONSTRAINT ck_sources_pointer_needs_version CHECK (current_version_id IS NULL OR last_version_number > 0),
    CONSTRAINT uq_sources_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_sources_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);

CREATE TABLE sources.uploads (
    id uuid CONSTRAINT pk_uploads PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    object_key text NOT NULL CONSTRAINT ck_uploads_object_key CHECK (length(object_key) BETWEEN 1 AND 1024),
    declared_media_type text NOT NULL CONSTRAINT ck_uploads_declared_media_type CHECK (length(declared_media_type) BETWEEN 1 AND 255),
    declared_size_bytes bigint NOT NULL CONSTRAINT ck_uploads_declared_size_bytes CHECK (declared_size_bytes > 0),
    declared_sha256 bytea NOT NULL CONSTRAINT ck_uploads_declared_sha256 CHECK (octet_length(declared_sha256) = 32),
    status text NOT NULL DEFAULT 'PENDING' CONSTRAINT ck_uploads_status CHECK (status IN ('PENDING','UPLOADED','VERIFIED','REJECTED','EXPIRED')),
    expires_at timestamptz NOT NULL,
    actual_size_bytes bigint NULL, verified_sha256 bytea NULL CONSTRAINT ck_uploads_verified_sha256 CHECK (octet_length(verified_sha256) = 32),
    finalized_at timestamptz NULL, rejection_code text NULL CONSTRAINT ck_uploads_rejection_code CHECK (rejection_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    created_by uuid NULL,
    {COMMON_uploads},
    CONSTRAINT ck_uploads_verified_matches_declared CHECK (status <> 'VERIFIED' OR (verified_sha256 = declared_sha256 AND actual_size_bytes = declared_size_bytes AND finalized_at IS NOT NULL)),
    CONSTRAINT ck_uploads_rejected_has_code CHECK (status <> 'REJECTED' OR rejection_code IS NOT NULL),
    CONSTRAINT uq_uploads_object_key UNIQUE (object_key),
    CONSTRAINT uq_uploads_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_uploads_source_id_sources FOREIGN KEY (organization_id, project_id, source_id) REFERENCES sources.sources(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_uploads_source_id ON sources.uploads (source_id);
CREATE INDEX ix_uploads_pending_expires_at ON sources.uploads (expires_at) WHERE status IN ('PENDING','UPLOADED');

CREATE TABLE sources.source_versions (
    id uuid CONSTRAINT pk_source_versions PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    version_number integer NOT NULL CONSTRAINT ck_source_versions_version_number CHECK (version_number > 0),
    upload_id uuid NULL,
    media_type text NOT NULL CONSTRAINT ck_source_versions_media_type CHECK (length(media_type) BETWEEN 1 AND 255),
    size_bytes bigint NOT NULL CONSTRAINT ck_source_versions_size_bytes CHECK (size_bytes >= 0),
    checksum_sha256 bytea NOT NULL CONSTRAINT ck_source_versions_checksum_sha256 CHECK (octet_length(checksum_sha256) = 32),
    object_key text NULL, external_ref jsonb NULL CONSTRAINT ck_source_versions_external_ref CHECK (jsonb_typeof(external_ref) = 'object'),
    provenance jsonb NOT NULL CONSTRAINT ck_source_versions_provenance CHECK (jsonb_typeof(provenance) = 'object'),
    received_at timestamptz NOT NULL, created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_versions_exactly_one_location CHECK ((object_key IS NOT NULL) <> (external_ref IS NOT NULL)),
    CONSTRAINT ck_source_versions_object_iff_upload CHECK ((object_key IS NOT NULL) = (upload_id IS NOT NULL)),  -- a stored object is always the verified upload's object (review C5)
    CONSTRAINT uq_source_versions_source_id_version_number UNIQUE (source_id, version_number),
    CONSTRAINT uq_source_versions_source_id_checksum_sha256 UNIQUE (source_id, checksum_sha256),
    CONSTRAINT uq_source_versions_source_id_id UNIQUE (source_id, id),
    CONSTRAINT uq_source_versions_upload_id UNIQUE (upload_id),
    CONSTRAINT uq_source_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_source_versions_source_id_sources FOREIGN KEY (organization_id, project_id, source_id) REFERENCES sources.sources(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_source_versions_upload_id_uploads FOREIGN KEY (organization_id, project_id, upload_id) REFERENCES sources.uploads(organization_id, project_id, id) ON DELETE RESTRICT);
ALTER TABLE sources.sources ADD CONSTRAINT fk_sources_current_version_id_source_versions
    FOREIGN KEY (id, current_version_id) REFERENCES sources.source_versions(source_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE knowledge.extraction_records (
    id uuid CONSTRAINT pk_extraction_records PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL,
    source_version_id uuid NOT NULL,
    pipeline_name text NOT NULL CONSTRAINT ck_extraction_records_pipeline_name CHECK (length(pipeline_name) BETWEEN 1 AND 100),
    pipeline_version text NOT NULL CONSTRAINT ck_extraction_records_pipeline_version CHECK (length(pipeline_version) BETWEEN 1 AND 100),
    parser_version text NOT NULL CONSTRAINT ck_extraction_records_parser_version CHECK (length(parser_version) BETWEEN 1 AND 100),
    attempt integer NOT NULL DEFAULT 1 CONSTRAINT ck_extraction_records_attempt CHECK (attempt > 0),
    status text NOT NULL DEFAULT 'STARTED' CONSTRAINT ck_extraction_records_status CHECK (status IN ('STARTED','SUCCEEDED','PARTIAL','FAILED')),
    tool_ref text NULL, input_version_refs jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_extraction_records_input_version_refs CHECK (jsonb_typeof(input_version_refs) = 'array'),
    error_code text NULL CONSTRAINT ck_extraction_records_error_code CHECK (error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    operation_id uuid NULL,
    started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz NULL, created_by uuid NULL,
    CONSTRAINT ck_extraction_records_completed_iff_finished CHECK ((status = 'STARTED') = (completed_at IS NULL)),
    CONSTRAINT ck_extraction_records_failed_has_code CHECK (status <> 'FAILED' OR error_code IS NOT NULL),
    CONSTRAINT uq_extraction_records_run UNIQUE (source_version_id, pipeline_name, pipeline_version, parser_version, attempt),
    CONSTRAINT fk_extraction_records_source_version_id_source_versions FOREIGN KEY (organization_id, project_id, source_version_id) REFERENCES sources.source_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_extraction_records_operation_id_operations FOREIGN KEY (organization_id, project_id, operation_id) REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT);
CREATE INDEX ix_extraction_records_source_version_id ON knowledge.extraction_records (source_version_id);
CREATE INDEX ix_extraction_records_operation_id ON knowledge.extraction_records (operation_id) WHERE operation_id IS NOT NULL;
"""


def _rls(table: str, grants: str) -> None:
    name = table.split(".")[1]
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({SCOPE}) WITH CHECK ({SCOPE})")
    op.execute(f"CREATE POLICY p_{name}_owner_migration ON {table} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
    op.execute(f"GRANT {grants} ON {table} TO ai_res_api_group")


def _guards(table: str, *, immutable: tuple[str, ...], touch: bool = True) -> None:
    name = table.split(".")[1]
    if touch:
        op.execute(f"CREATE TRIGGER trg_{name}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
    cols = ", ".join(f"'{c}'" for c in immutable)
    op.execute(f"CREATE TRIGGER trg_{name}_immutable_columns BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")


def _insert_only(table: str) -> None:
    name = table.split(".")[1]
    op.execute(f"CREATE TRIGGER trg_{name}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute(f"CREATE TRIGGER trg_{name}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def _version_numbers(parent: str, versions: str, fk_column: str) -> None:
    pname, vname = parent.split(".")[1], versions.split(".")[1]
    op.execute(f"CREATE CONSTRAINT TRIGGER trg_{vname}_version_number AFTER INSERT ON {versions} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               f"EXECUTE FUNCTION platform.assert_version_number_contiguous('{fk_column}', '{parent}', '{versions}', '{fk_column}')")
    op.execute(f"CREATE CONSTRAINT TRIGGER trg_{pname}_version_number AFTER INSERT OR UPDATE OF last_version_number ON {parent} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               f"EXECUTE FUNCTION platform.assert_version_number_contiguous('id', '{parent}', '{versions}', '{fk_column}')")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute(TABLES.replace("{COMMON_requirements}", common("requirements")).replace("{COMMON_sources}", common("sources")).replace("{COMMON_uploads}", common("uploads")))

    # reference registry (ADR-013 pattern): runtime SELECT-only, changed only by revisions
    op.execute("GRANT SELECT ON requirements.requirement_types TO ai_res_api_group")

    # numbering counters: row lock + advance by exactly one (MAX()+1 is forbidden)
    _rls("platform.display_number_counters", "SELECT, INSERT, UPDATE")
    op.execute("CREATE TRIGGER trg_display_number_counters_advance BEFORE UPDATE ON platform.display_number_counters FOR EACH ROW EXECUTE FUNCTION platform.advance_by_one('last_number')")
    op.execute("CREATE TRIGGER trg_display_number_counters_immutable_columns BEFORE UPDATE ON platform.display_number_counters FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable('organization_id', 'project_id', 'counter_kind')")

    # requirements
    _rls("requirements.requirements", "SELECT, INSERT, UPDATE")
    _guards("requirements.requirements", immutable=("id", "organization_id", "project_id", "display_number", "created_at", "created_by"))
    _rls("requirements.requirement_versions", "SELECT, INSERT, UPDATE")
    _guards("requirements.requirement_versions", touch=False, immutable=(
        "id", "organization_id", "project_id", "requirement_id", "version_number", "requirement_type", "declared_type_text", "statement", "rationale", "priority",
        "acceptance_criteria", "constraints_info", "provenance_refs", "change_reason", "author_type", "author_id", "created_at"))
    # DOC-003 lifecycle (BASELINED statuses; the transition graph is the minimal one implied by the document: forward only, nothing leaves REJECTED/SUPERSEDED)
    op.execute("CREATE TRIGGER trg_requirement_versions_status BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'EXTRACTED>CANDIDATE', 'EXTRACTED>CONFIRMED', 'EXTRACTED>REJECTED', 'EXTRACTED>SUPERSEDED', 'CANDIDATE>CONFIRMED', 'CANDIDATE>REJECTED', 'CANDIDATE>SUPERSEDED', "
               "'CONFIRMED>APPROVED', 'CONFIRMED>REJECTED', 'CONFIRMED>SUPERSEDED', 'APPROVED>IN_BASELINE', 'APPROVED>SUPERSEDED', 'IN_BASELINE>SUPERSEDED')")
    op.execute("CREATE TRIGGER trg_requirement_versions_write_once BEFORE UPDATE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('confirmed_by', 'confirmed_at')")
    op.execute("CREATE TRIGGER trg_requirement_versions_no_delete BEFORE DELETE ON requirements.requirement_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE TRIGGER trg_requirement_versions_no_truncate BEFORE TRUNCATE ON requirements.requirement_versions FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    _version_numbers("requirements.requirements", "requirements.requirement_versions", "requirement_id")
    _rls("requirements.requirement_epics", "SELECT, INSERT")
    _rls("work.task_requirements", "SELECT, INSERT")

    # sources
    _rls("sources.sources", "SELECT, INSERT, UPDATE")
    _guards("sources.sources", immutable=("id", "organization_id", "project_id", "source_kind", "created_at", "created_by"))
    _rls("sources.uploads", "SELECT, INSERT, UPDATE")
    _guards("sources.uploads", immutable=("id", "organization_id", "project_id", "source_id", "object_key", "declared_media_type", "declared_size_bytes", "declared_sha256",
                                         "expires_at", "created_at", "created_by"))
    op.execute("CREATE TRIGGER trg_uploads_status BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'PENDING>UPLOADED', 'PENDING>REJECTED', 'PENDING>EXPIRED', 'UPLOADED>VERIFIED', 'UPLOADED>REJECTED', 'UPLOADED>EXPIRED')")
    op.execute("CREATE TRIGGER trg_uploads_write_once BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('actual_size_bytes', 'verified_sha256', 'finalized_at', 'rejection_code')")
    op.execute("CREATE TRIGGER trg_uploads_freeze_finished BEFORE UPDATE ON sources.uploads FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'VERIFIED', 'REJECTED', 'EXPIRED')")
    _rls("sources.source_versions", "SELECT, INSERT")
    _insert_only("sources.source_versions")
    op.execute("CREATE TRIGGER trg_source_versions_guard_insert BEFORE INSERT ON sources.source_versions FOR EACH ROW EXECUTE FUNCTION sources.guard_source_version_insert()")
    _version_numbers("sources.sources", "sources.source_versions", "source_id")

    # extraction records: a finished record is never mutated; a parser/pipeline change is a NEW record
    _rls("knowledge.extraction_records", "SELECT, INSERT, UPDATE")
    _guards("knowledge.extraction_records", touch=False, immutable=(
        "id", "organization_id", "project_id", "source_version_id", "pipeline_name", "pipeline_version", "parser_version", "attempt", "tool_ref", "input_version_refs",
        "operation_id", "started_at", "created_by"))
    op.execute("CREATE TRIGGER trg_extraction_records_status BEFORE UPDATE ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'STARTED>SUCCEEDED', 'STARTED>PARTIAL', 'STARTED>FAILED')")
    op.execute("CREATE TRIGGER trg_extraction_records_freeze_finished BEFORE UPDATE ON knowledge.extraction_records FOR EACH ROW EXECUTE FUNCTION platform.freeze_when_status_in('status', 'SUCCEEDED', 'PARTIAL', 'FAILED')")


def downgrade() -> None:
    raise NotImplementedError("PDB-0008/0009 create domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
