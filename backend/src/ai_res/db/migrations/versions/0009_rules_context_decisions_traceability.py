"""PDB-0012..0015 (part): rules (rules, rule_versions), context (packages, immutable versions, items), decisions (seven typed objects), traceability (registries, links), S06 slice C.

Revision ID: c47e1b8a92d5
Revises: b9d246f1a3c8

Rules: SYSTEM rules carry no tenant (visible to all, writable only by revisions); an unapproved version is never "active" (one APPROVED version per rule).
Context: a package version and ALL its items are written in one transaction and the item count is verified at COMMIT; items reference exact versions through real FKs.
Decisions (DOC-051): seven separate typed tables, no generic notes table. Status vocabularies are not fixed by any normative document: regex-controlled (WORKING).
Traceability: link/object types and allowed pairs come from registries (FK), endpoints are checked for existence inside the tenant. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input); long lines keep each constraint reviewable
from collections.abc import Sequence

from alembic import op

revision: str = "c47e1b8a92d5"
down_revision: str | None = "b9d246f1a3c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
PRJ = "NULLIF(current_setting('app.project_id', true), '')::uuid"
SCOPE = f"organization_id = {ORG} AND project_id = {PRJ}"
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"
ENDPOINTS = {"REQUIREMENT": "requirements.requirements", "REQUIREMENT_VERSION": "requirements.requirement_versions", "SOURCE_VERSION": "sources.source_versions",
             "ARTIFACT_VERSION": "artifacts.artifact_versions", "TASK": "work.tasks", "EPIC": "work.epics", "DECISION": "decisions.decisions",
             "ASSUMPTION": "decisions.assumptions", "RISK": "decisions.risks", "ISSUE": "decisions.issues", "UNKNOWN_ITEM": "decisions.unknowns",
             "HYPOTHESIS": "decisions.hypotheses", "CONFLICT": "decisions.conflicts"}


def common(t: str) -> str:
    return (f"row_version bigint NOT NULL DEFAULT 1 CONSTRAINT ck_{t}_row_version CHECK (row_version > 0),\n"
            "    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()")


# (table, extra columns, array-typed columns) ; every object also gets title/status/owner/scope/evidence/provenance
DECISION_TABLES = {
    "decisions": ("question text NOT NULL CONSTRAINT ck_decisions_question CHECK (length(btrim(question)) > 0), alternatives jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_decisions_alternatives CHECK (jsonb_typeof(alternatives) = 'array'), "
                  "chosen_option text NULL, rationale text NULL, consequences text NULL, approver_user_id uuid NULL, review_trigger text NULL, scope_description text NULL"),
    "assumptions": ("statement text NOT NULL CONSTRAINT ck_assumptions_statement CHECK (length(btrim(statement)) > 0), consequences_if_wrong text NULL, verification_method text NULL, verification_criteria text NULL, "
                    "expires_at timestamptz NULL, review_trigger text NULL"),
    "risks": ("cause text NULL, risk_event text NOT NULL CONSTRAINT ck_risks_risk_event CHECK (length(btrim(risk_event)) > 0), consequences text NULL, probability text NOT NULL DEFAULT 'UNKNOWN' CONSTRAINT ck_risks_probability CHECK (probability ~ '^[A-Z][A-Z_]*$'), "
              "impact text NOT NULL DEFAULT 'UNKNOWN' CONSTRAINT ck_risks_impact CHECK (impact ~ '^[A-Z][A-Z_]*$'), triggers jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_risks_triggers CHECK (jsonb_typeof(triggers) = 'array'), "
              "mitigation text NULL, contingency text NULL, residual_risk text NULL"),
    "issues": "description text NOT NULL CONSTRAINT ck_issues_description CHECK (length(btrim(description)) > 0), actual_impact text NULL, resolution text NULL",
    "unknowns": ("information_gap text NOT NULL CONSTRAINT ck_unknowns_information_gap CHECK (length(btrim(information_gap)) > 0), affected_refs jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_unknowns_affected_refs CHECK (jsonb_typeof(affected_refs) = 'array'), "
                 "closing_condition text NULL"),
    "hypotheses": "statement text NOT NULL CONSTRAINT ck_hypotheses_statement CHECK (length(btrim(statement)) > 0), grounds text NULL, test_method text NULL, result text NULL",
    "conflicts": ("conflicting_refs jsonb NOT NULL CONSTRAINT ck_conflicts_conflicting_refs CHECK (jsonb_typeof(conflicting_refs) = 'array' AND jsonb_array_length(conflicting_refs) >= 2), "
                  "classification text NULL, resolution_approach text NULL"),
}


def _decision_ddl(name: str, extra: str) -> str:
    approver = (f",\n    CONSTRAINT fk_{name}_approver_user_id_users FOREIGN KEY (organization_id, approver_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT"
                if name == "decisions" else "")
    return f"""
CREATE TABLE decisions.{name} (
    id uuid CONSTRAINT pk_{name} PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, epic_id uuid NULL, task_id uuid NULL,
    title text NOT NULL CONSTRAINT ck_{name}_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    status text NOT NULL CONSTRAINT ck_{name}_status CHECK (status ~ '^[A-Z][A-Z_]*$'),
    owner_user_id uuid NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_{name}_evidence_refs CHECK (jsonb_typeof(evidence_refs) = 'array'),
    provenance jsonb NOT NULL DEFAULT '{{}}'::jsonb CONSTRAINT ck_{name}_provenance CHECK (jsonb_typeof(provenance) = 'object'),
    {extra},
    created_by uuid NULL, updated_by uuid NULL,
    {common(name)},
    CONSTRAINT uq_{name}_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_{name}_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_{name}_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_{name}_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_{name}_owner_user_id_users FOREIGN KEY (organization_id, owner_user_id) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT{approver});
CREATE INDEX ix_{name}_project_id_status ON decisions.{name} (project_id, status);
CREATE INDEX ix_{name}_epic_id ON decisions.{name} (epic_id) WHERE epic_id IS NOT NULL;
CREATE INDEX ix_{name}_task_id ON decisions.{name} (task_id) WHERE task_id IS NOT NULL;
"""


FUNCTIONS = f"""
CREATE FUNCTION context.guard_item_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE c timestamptz;
BEGIN  -- items exist only in the transaction that created their (immutable) package version
  SELECT created_at INTO c FROM context.context_package_versions WHERE id = NEW.context_package_version_id;
  IF c IS NULL OR c <> now() THEN
    RAISE EXCEPTION 'context package version % is sealed: items can only be added in the transaction that creates it', NEW.context_package_version_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION context.assert_package_version_complete() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE n int; expected int; vid uuid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
BEGIN  -- deferred: exactly item_count items (a partially written context snapshot rolls back)
  SELECT item_count INTO expected FROM context.context_package_versions WHERE id = vid;
  IF expected IS NULL THEN RETURN NULL; END IF;
  SELECT count(*) INTO n FROM context.context_package_items WHERE context_package_version_id = vid;
  IF n <> expected THEN RAISE EXCEPTION 'context package version % declares % items but holds %', vid, expected, n USING ERRCODE = 'integrity_constraint_violation'; END IF;
  RETURN NULL;
END $f$;

CREATE FUNCTION traceability.assert_endpoint_exists() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE t text; ok boolean; side text;
BEGIN  -- polymorphic endpoints cannot carry FKs: the object must exist in THIS tenant (RLS applies); an unmapped object type fails closed
  FOREACH side IN ARRAY ARRAY['source', 'target'] LOOP
    t := CASE to_jsonb(NEW) ->> (side || '_object_type') {" ".join(f"WHEN '{k}' THEN '{v}'" for k, v in ENDPOINTS.items())} END;
    IF t IS NULL THEN RAISE EXCEPTION 'traceability %: object type % has no endpoint mapping', side, to_jsonb(NEW) ->> (side || '_object_type') USING ERRCODE = 'integrity_constraint_violation'; END IF;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE id = $1 AND organization_id = $2 AND project_id = $3)', t::regclass)
      INTO ok USING (to_jsonb(NEW) ->> (side || '_object_id'))::uuid, NEW.organization_id, NEW.project_id;
    IF NOT ok THEN RAISE EXCEPTION 'traceability % endpoint % does not exist in this project', side, to_jsonb(NEW) ->> (side || '_object_id') USING ERRCODE = 'integrity_constraint_violation'; END IF;
  END LOOP;
  RETURN NEW;
END $f$;
"""

TABLES = f"""
CREATE TABLE governance.rules (
    id uuid CONSTRAINT pk_rules PRIMARY KEY,
    level text NOT NULL CONSTRAINT ck_rules_level CHECK (level IN ('SYSTEM','ORGANIZATION','PROJECT')),
    organization_id uuid NULL CONSTRAINT fk_rules_organization_id_organizations REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    project_id uuid NULL,
    rule_key text NOT NULL CONSTRAINT ck_rules_rule_key CHECK (rule_key ~ '^[A-Za-z][A-Za-z0-9_.-]{{0,99}}$'),
    title text NOT NULL CONSTRAINT ck_rules_title CHECK (length(btrim(title)) BETWEEN 1 AND 240),
    applies_to_object_type text NULL CONSTRAINT ck_rules_applies_to_object_type CHECK (applies_to_object_type ~ '^[A-Z][A-Z_]*$'),
    created_by uuid NULL,
    {common("rules")},
    CONSTRAINT ck_rules_level_scope CHECK ((level = 'SYSTEM' AND organization_id IS NULL AND project_id IS NULL) OR (level = 'ORGANIZATION' AND organization_id IS NOT NULL AND project_id IS NULL)
                                          OR (level = 'PROJECT' AND organization_id IS NOT NULL AND project_id IS NOT NULL)),
    CONSTRAINT uq_rules_id_level UNIQUE (id, level),
    CONSTRAINT uq_rules_id_organization_id UNIQUE (id, organization_id),
    CONSTRAINT uq_rules_id_project_id UNIQUE (id, project_id),
    CONSTRAINT fk_rules_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT);
CREATE UNIQUE INDEX uq_rules_scope_rule_key ON governance.rules (level, coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid), rule_key);

CREATE TABLE governance.rule_versions (
    id uuid CONSTRAINT pk_rule_versions PRIMARY KEY,
    rule_id uuid NOT NULL, level text NOT NULL, organization_id uuid NULL, project_id uuid NULL,
    version_number integer NOT NULL CONSTRAINT ck_rule_versions_version_number CHECK (version_number > 0),
    condition jsonb NOT NULL CONSTRAINT ck_rule_versions_condition CHECK (jsonb_typeof(condition) = 'object'),
    action jsonb NOT NULL CONSTRAINT ck_rule_versions_action CHECK (jsonb_typeof(action) = 'object'),
    applicability jsonb NOT NULL DEFAULT '{{}}'::jsonb CONSTRAINT ck_rule_versions_applicability CHECK (jsonb_typeof(applicability) = 'object'),
    rationale text NULL,
    author_type text NOT NULL CONSTRAINT ck_rule_versions_author_type CHECK (author_type IN ('USER','MANAGER','WORKER_RUN','IMPORT')), author_id uuid NULL,
    status text NOT NULL DEFAULT 'DRAFT' CONSTRAINT ck_rule_versions_status CHECK (status IN ('DRAFT','PROPOSED','APPROVED','REJECTED','RETIRED')),
    approver_user_id uuid NULL CONSTRAINT fk_rule_versions_approver_user_id_users REFERENCES iam.users(id) ON DELETE RESTRICT,
    approved_at timestamptz NULL, valid_from timestamptz NULL, valid_to timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_rule_versions_approved_facts CHECK ((status IN ('APPROVED','RETIRED')) <= (approver_user_id IS NOT NULL AND approved_at IS NOT NULL AND valid_from IS NOT NULL)),
    CONSTRAINT ck_rule_versions_level_scope CHECK ((level = 'SYSTEM' AND organization_id IS NULL AND project_id IS NULL) OR (level = 'ORGANIZATION' AND organization_id IS NOT NULL AND project_id IS NULL)
                                                  OR (level = 'PROJECT' AND organization_id IS NOT NULL AND project_id IS NOT NULL)),
    CONSTRAINT ck_rule_versions_validity CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CONSTRAINT uq_rule_versions_rule_id_version_number UNIQUE (rule_id, version_number),
    CONSTRAINT fk_rule_versions_rule_id_level_rules FOREIGN KEY (rule_id, level) REFERENCES governance.rules(id, level) ON DELETE RESTRICT,
    CONSTRAINT fk_rule_versions_rule_id_organization_id_rules FOREIGN KEY (rule_id, organization_id) REFERENCES governance.rules(id, organization_id) ON DELETE RESTRICT,
    CONSTRAINT fk_rule_versions_rule_id_project_id_rules FOREIGN KEY (rule_id, project_id) REFERENCES governance.rules(id, project_id) ON DELETE RESTRICT,
    CONSTRAINT uq_rule_versions_id UNIQUE (id));
CREATE UNIQUE INDEX uq_rule_versions_one_approved ON governance.rule_versions (rule_id) WHERE status = 'APPROVED';

CREATE TABLE context.context_packages (
    id uuid CONSTRAINT pk_context_packages PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, epic_id uuid NULL, task_id uuid NULL,
    name text NOT NULL CONSTRAINT ck_context_packages_name CHECK (length(btrim(name)) BETWEEN 1 AND 240),
    current_version_id uuid NULL,
    last_version_number integer NOT NULL DEFAULT 0 CONSTRAINT ck_context_packages_last_version_number CHECK (last_version_number >= 0),
    created_by uuid NULL,
    {common("context_packages")},
    CONSTRAINT ck_context_packages_pointer_needs_version CHECK (current_version_id IS NULL OR last_version_number > 0),
    CONSTRAINT uq_context_packages_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_context_packages_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_packages_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_packages_task_id_tasks FOREIGN KEY (organization_id, project_id, task_id) REFERENCES work.tasks(organization_id, project_id, id) ON DELETE RESTRICT);

CREATE TABLE context.context_package_versions (
    id uuid CONSTRAINT pk_context_package_versions PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, context_package_id uuid NOT NULL,
    version_number integer NOT NULL CONSTRAINT ck_context_package_versions_version_number CHECK (version_number > 0),
    item_count integer NOT NULL CONSTRAINT ck_context_package_versions_item_count CHECK (item_count > 0),
    content_digest bytea NOT NULL CONSTRAINT ck_context_package_versions_content_digest CHECK (octet_length(content_digest) = 32),
    created_by uuid NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_context_package_versions_context_package_id_version_number UNIQUE (context_package_id, version_number),
    CONSTRAINT uq_context_package_versions_context_package_id_id UNIQUE (context_package_id, id),
    CONSTRAINT uq_context_package_versions_organization_id_project_id_id UNIQUE (organization_id, project_id, id),
    CONSTRAINT fk_context_package_versions_context_package_id_context_packages FOREIGN KEY (organization_id, project_id, context_package_id) REFERENCES context.context_packages(organization_id, project_id, id) ON DELETE RESTRICT);
ALTER TABLE context.context_packages ADD CONSTRAINT fk_context_packages_current_version_id_context_package_versions
    FOREIGN KEY (id, current_version_id) REFERENCES context.context_package_versions(context_package_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE context.context_package_items (
    id uuid CONSTRAINT pk_context_package_items PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, context_package_version_id uuid NOT NULL,
    item_kind text NOT NULL CONSTRAINT ck_context_package_items_item_kind CHECK (item_kind IN ('SOURCE_VERSION','REQUIREMENT_VERSION','ARTIFACT_VERSION','RULE_VERSION')),
    source_version_id uuid NULL, requirement_version_id uuid NULL, artifact_version_id uuid NULL, rule_version_id uuid NULL,
    inclusion_role text NOT NULL CONSTRAINT ck_context_package_items_inclusion_role CHECK (inclusion_role ~ '^[A-Z][A-Z_]*$'),
    locator jsonb NULL CONSTRAINT ck_context_package_items_locator CHECK (jsonb_typeof(locator) = 'object'),
    provenance jsonb NOT NULL DEFAULT '{{}}'::jsonb CONSTRAINT ck_context_package_items_provenance CHECK (jsonb_typeof(provenance) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_context_package_items_kind_matches_ref CHECK (
        (item_kind = 'SOURCE_VERSION' AND source_version_id IS NOT NULL AND requirement_version_id IS NULL AND artifact_version_id IS NULL AND rule_version_id IS NULL)
     OR (item_kind = 'REQUIREMENT_VERSION' AND requirement_version_id IS NOT NULL AND source_version_id IS NULL AND artifact_version_id IS NULL AND rule_version_id IS NULL)
     OR (item_kind = 'ARTIFACT_VERSION' AND artifact_version_id IS NOT NULL AND source_version_id IS NULL AND requirement_version_id IS NULL AND rule_version_id IS NULL)
     OR (item_kind = 'RULE_VERSION' AND rule_version_id IS NOT NULL AND source_version_id IS NULL AND requirement_version_id IS NULL AND artifact_version_id IS NULL)),
    CONSTRAINT fk_context_package_items_context_package_version_id_versions FOREIGN KEY (organization_id, project_id, context_package_version_id) REFERENCES context.context_package_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_package_items_source_version_id_source_versions FOREIGN KEY (organization_id, project_id, source_version_id) REFERENCES sources.source_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_package_items_requirement_version_id_req_versions FOREIGN KEY (organization_id, project_id, requirement_version_id) REFERENCES requirements.requirement_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_package_items_artifact_version_id_artifact_versions FOREIGN KEY (organization_id, project_id, artifact_version_id) REFERENCES artifacts.artifact_versions(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_package_items_rule_version_id_rule_versions FOREIGN KEY (rule_version_id) REFERENCES governance.rule_versions(id) ON DELETE RESTRICT);
CREATE INDEX ix_context_package_items_context_package_version_id ON context.context_package_items (context_package_version_id);
CREATE INDEX ix_context_package_items_source_version_id ON context.context_package_items (source_version_id) WHERE source_version_id IS NOT NULL;
CREATE INDEX ix_context_package_items_requirement_version_id ON context.context_package_items (requirement_version_id) WHERE requirement_version_id IS NOT NULL;
CREATE INDEX ix_context_package_items_artifact_version_id ON context.context_package_items (artifact_version_id) WHERE artifact_version_id IS NOT NULL;
CREATE INDEX ix_context_package_items_rule_version_id ON context.context_package_items (rule_version_id) WHERE rule_version_id IS NOT NULL;

CREATE TABLE traceability.object_types (code text CONSTRAINT pk_object_types PRIMARY KEY CONSTRAINT ck_object_types_code CHECK (code ~ '^[A-Z][A-Z_]*$'));
CREATE TABLE traceability.link_types (code text CONSTRAINT pk_link_types PRIMARY KEY CONSTRAINT ck_link_types_code CHECK (code ~ '^[A-Z][A-Z_]*$'));
CREATE TABLE traceability.link_type_rules (
    link_type text NOT NULL CONSTRAINT fk_link_type_rules_link_type_link_types REFERENCES traceability.link_types(code) ON DELETE RESTRICT,
    source_object_type text NOT NULL CONSTRAINT fk_link_type_rules_source_object_type_object_types REFERENCES traceability.object_types(code) ON DELETE RESTRICT,
    target_object_type text NOT NULL CONSTRAINT fk_link_type_rules_target_object_type_object_types REFERENCES traceability.object_types(code) ON DELETE RESTRICT,
    CONSTRAINT pk_link_type_rules PRIMARY KEY (link_type, source_object_type, target_object_type));
INSERT INTO traceability.object_types (code) VALUES {", ".join(f"('{k}')" for k in ENDPOINTS)};
INSERT INTO traceability.link_types (code) VALUES ('REFINES'),('DEPENDS_ON'),('CONFLICTS_WITH'),('DUPLICATES'),('SUPERSEDES');
INSERT INTO traceability.link_type_rules (link_type, source_object_type, target_object_type) SELECT t.code, 'REQUIREMENT', 'REQUIREMENT' FROM traceability.link_types t;

CREATE TABLE traceability.traceability_links (
    id uuid CONSTRAINT pk_traceability_links PRIMARY KEY,
    organization_id uuid NOT NULL, project_id uuid NOT NULL, epic_id uuid NULL,
    source_object_type text NOT NULL, source_object_id uuid NOT NULL,
    target_object_type text NOT NULL, target_object_id uuid NOT NULL,
    link_type text NOT NULL,
    status text NOT NULL DEFAULT 'PROPOSED' CONSTRAINT ck_traceability_links_status CHECK (status IN ('PROPOSED','CONFIRMED','REJECTED','SUPERSEDED')),
    origin text NOT NULL CONSTRAINT ck_traceability_links_origin CHECK (origin IN ('HUMAN','AGENT','IMPORT','RULE')),
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT ck_traceability_links_evidence_refs CHECK (jsonb_typeof(evidence_refs) = 'array'),
    rationale text NULL, created_by uuid NULL,
    confirmed_by uuid NULL, confirmed_at timestamptz NULL, superseded_at timestamptz NULL,
    {common("traceability_links")},
    CONSTRAINT ck_traceability_links_not_self CHECK (NOT (source_object_type = target_object_type AND source_object_id = target_object_id)),
    CONSTRAINT ck_traceability_links_confirmed CHECK ((status <> 'CONFIRMED') OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL AND jsonb_array_length(evidence_refs) > 0)),
    CONSTRAINT ck_traceability_links_superseded CHECK ((status = 'SUPERSEDED') = (superseded_at IS NOT NULL)),
    CONSTRAINT fk_traceability_links_link_type_rules FOREIGN KEY (link_type, source_object_type, target_object_type) REFERENCES traceability.link_type_rules(link_type, source_object_type, target_object_type) ON DELETE RESTRICT,
    CONSTRAINT fk_traceability_links_organization_id_project_id_projects FOREIGN KEY (organization_id, project_id) REFERENCES project.projects(organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_traceability_links_epic_id_epics FOREIGN KEY (organization_id, project_id, epic_id) REFERENCES work.epics(organization_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_traceability_links_confirmed_by_users FOREIGN KEY (organization_id, confirmed_by) REFERENCES iam.users(organization_id, id) ON DELETE RESTRICT);
CREATE UNIQUE INDEX uq_traceability_links_live ON traceability.traceability_links (project_id, source_object_type, source_object_id, target_object_type, target_object_id, link_type) WHERE status IN ('PROPOSED','CONFIRMED');
CREATE INDEX ix_traceability_links_source ON traceability.traceability_links (source_object_type, source_object_id);
CREATE INDEX ix_traceability_links_target ON traceability.traceability_links (target_object_type, target_object_id);
CREATE INDEX ix_traceability_links_link_type_status ON traceability.traceability_links (link_type, status);
"""


def _enable(table: str) -> str:
    name = table.split(".")[1]
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_{name}_owner_migration ON {table} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
    return name


def _rls(table: str, grants: str) -> None:
    name = _enable(table)
    op.execute(f"CREATE POLICY p_{name}_tenant_scope ON {table} FOR ALL TO ai_res_api_group USING ({SCOPE}) WITH CHECK ({SCOPE})")
    op.execute(f"GRANT {grants} ON {table} TO ai_res_api_group")


def _insert_only(table: str) -> None:
    name = table.split(".")[1]
    _rls(table, "SELECT, INSERT")
    op.execute(f"CREATE TRIGGER trg_{name}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute(f"CREATE TRIGGER trg_{name}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def _mutable(table: str, immutable: tuple[str, ...]) -> None:
    name = table.split(".")[1]
    op.execute(f"CREATE TRIGGER trg_{name}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.touch_row()")
    cols = ", ".join(f"'{c}'" for c in immutable)
    op.execute(f"CREATE TRIGGER trg_{name}_immutable_columns BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable({cols})")


def upgrade() -> None:
    op.execute(FUNCTIONS)
    op.execute(TABLES)
    for name, extra in DECISION_TABLES.items():
        op.execute(_decision_ddl(name, extra))
        _rls(f"decisions.{name}", "SELECT, INSERT, UPDATE")
        _mutable(f"decisions.{name}", ("id", "organization_id", "project_id", "created_at", "created_by"))

    # rules: SYSTEM rules are readable by every tenant and writable by no runtime principal; tenant rules are scoped. Unapproved versions are data, never "active".
    read = f"level = 'SYSTEM' OR (organization_id = {ORG} AND (project_id IS NULL OR project_id = {PRJ}))"
    write = f"level <> 'SYSTEM' AND organization_id = {ORG} AND (project_id IS NULL OR project_id = {PRJ})"
    for table in ("governance.rules", "governance.rule_versions"):
        name = _enable(table)
        op.execute(f"CREATE POLICY p_{name}_read ON {table} FOR SELECT TO ai_res_api_group USING ({read})")
        op.execute(f"CREATE POLICY p_{name}_insert ON {table} FOR INSERT TO ai_res_api_group WITH CHECK ({write})")
        op.execute(f"CREATE POLICY p_{name}_update ON {table} FOR UPDATE TO ai_res_api_group USING ({write}) WITH CHECK ({write})")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO ai_res_api_group")
    _mutable("governance.rules", ("id", "level", "organization_id", "project_id", "rule_key", "created_at", "created_by"))
    op.execute("CREATE TRIGGER trg_rule_versions_immutable_columns BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.keep_columns_immutable("
               "'id', 'rule_id', 'level', 'organization_id', 'project_id', 'version_number', 'condition', 'action', 'applicability', 'rationale', 'author_type', 'author_id', 'created_at')")
    op.execute("CREATE TRIGGER trg_rule_versions_status BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'DRAFT>PROPOSED', 'DRAFT>REJECTED', 'PROPOSED>APPROVED', 'PROPOSED>REJECTED', 'APPROVED>RETIRED')")
    op.execute("CREATE TRIGGER trg_rule_versions_write_once BEFORE UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('approver_user_id', 'approved_at', 'valid_from', 'valid_to')")
    op.execute("CREATE TRIGGER trg_rule_versions_no_delete BEFORE DELETE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")

    # context
    _rls("context.context_packages", "SELECT, INSERT, UPDATE")
    _mutable("context.context_packages", ("id", "organization_id", "project_id", "epic_id", "task_id", "created_at", "created_by"))
    _insert_only("context.context_package_versions")
    _insert_only("context.context_package_items")
    op.execute("CREATE TRIGGER trg_context_package_items_guard_insert BEFORE INSERT ON context.context_package_items FOR EACH ROW EXECUTE FUNCTION context.guard_item_insert()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_context_package_items_complete AFTER INSERT ON context.context_package_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('context_package_version_id')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_context_package_versions_complete AFTER INSERT ON context.context_package_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION context.assert_package_version_complete('id')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_context_package_versions_version_number AFTER INSERT ON context.context_package_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_version_number_contiguous('context_package_id', 'context.context_packages', 'context.context_package_versions', 'context_package_id')")
    op.execute("CREATE CONSTRAINT TRIGGER trg_context_packages_version_number AFTER INSERT OR UPDATE OF last_version_number ON context.context_packages DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION platform.assert_version_number_contiguous('id', 'context.context_packages', 'context.context_package_versions', 'context_package_id')")

    # traceability
    op.execute("GRANT SELECT ON traceability.object_types, traceability.link_types, traceability.link_type_rules TO ai_res_api_group")
    _rls("traceability.traceability_links", "SELECT, INSERT, UPDATE")
    _mutable("traceability.traceability_links", ("id", "organization_id", "project_id", "epic_id", "source_object_type", "source_object_id", "target_object_type", "target_object_id",
                                                 "link_type", "origin", "created_by", "created_at"))
    op.execute("CREATE TRIGGER trg_traceability_links_status BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.guard_status_transition("
               "'status', 'PROPOSED>CONFIRMED', 'PROPOSED>REJECTED', 'PROPOSED>SUPERSEDED', 'CONFIRMED>SUPERSEDED')")
    op.execute("CREATE TRIGGER trg_traceability_links_write_once BEFORE UPDATE ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION platform.forbid_unset('confirmed_by', 'confirmed_at', 'superseded_at')")
    op.execute("CREATE TRIGGER trg_traceability_links_endpoints BEFORE INSERT ON traceability.traceability_links FOR EACH ROW EXECUTE FUNCTION traceability.assert_endpoint_exists()")


def downgrade() -> None:
    raise NotImplementedError("PDB-0012..0015 create domain tables that will hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
