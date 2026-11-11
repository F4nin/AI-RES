"""S06 independent review fixes: insert-time lifecycle guards, upload-bound source versions, tenant-safe rule items, approver org check, baseline approval, FK indexes.

Revision ID: e6b4a91c7d32
Revises: d85a3f6c1e07

Findings of reviews/S06_REVIEWS.md (database-reviewer): C1 every status guard was UPDATE-only, so a row could be INSERTed already APPROVED/VERIFIED/CONFIRMED with
fabricated lifecycle facts; C2 a baseline needed no approval and could fork; C3 a context item could reference another tenant's rule version; C4 a rule approver could
belong to another organization; C5 (fixed in place in 0007, revision unreleased: no DROP in migrations) a source version could carry an object key without a verified upload; M4 missing FK indexes. Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "e6b4a91c7d32"
down_revision: str | None = "d85a3f6c1e07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = """
CREATE FUNCTION platform.require_initial_state() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE i int; n jsonb := to_jsonb(NEW);
BEGIN  -- BEFORE INSERT. Args: [0] status column, [1] comma-separated allowed initial statuses, [2..] columns that must be NULL at creation (lifecycle facts are earned, never supplied)
  IF (n ->> TG_ARGV[0] = ANY (string_to_array(TG_ARGV[1], ','))) IS NOT TRUE THEN  -- unknown column or NULL status fails closed
    RAISE EXCEPTION '%.% must start in one of (%), not %', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[1], n ->> TG_ARGV[0] USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  FOR i IN 2 .. TG_NARGS - 1 LOOP
    IF (n ? TG_ARGV[i]) IS NOT TRUE OR (n -> TG_ARGV[i]) IS DISTINCT FROM 'null'::jsonb THEN  -- a mistyped column name raises instead of skipping the rule
      RAISE EXCEPTION '%.%: column % cannot be supplied at creation', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_ARGV[i] USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $f$;

CREATE OR REPLACE FUNCTION context.guard_item_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE c timestamptz;
BEGIN  -- sealed after the creating transaction; a rule item must be an APPROVED rule version VISIBLE to this tenant (RLS: SYSTEM or own organization/project)
  SELECT created_at INTO c FROM context.context_package_versions WHERE id = NEW.context_package_version_id;
  IF c IS NULL OR c <> now() THEN
    RAISE EXCEPTION 'context package version % is sealed: items can only be added in the transaction that creates it', NEW.context_package_version_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.rule_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM governance.rule_versions r WHERE r.id = NEW.rule_version_id AND r.status = 'APPROVED') THEN
    RAISE EXCEPTION 'rule version % is not an approved rule version of this tenant', NEW.rule_version_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION governance.guard_rule_approver() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- tenant rule versions: the approver is a user of the SAME organization (SYSTEM versions are written only by revisions)
  IF NEW.approver_user_id IS NOT NULL AND NEW.organization_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM iam.users u WHERE u.id = NEW.approver_user_id AND u.organization_id = NEW.organization_id) THEN
    RAISE EXCEPTION 'rule version approver is not a user of the rule''s organization' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION governance.guard_baseline_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE prev int;
BEGIN  -- baselines form a chain: number n follows exactly number n-1 of the same project (no forks)
  IF NEW.previous_baseline_id IS NOT NULL THEN
    SELECT baseline_number INTO prev FROM governance.baselines WHERE id = NEW.previous_baseline_id;
    IF prev IS DISTINCT FROM NEW.baseline_number - 1 THEN
      RAISE EXCEPTION 'baseline % must follow baseline number %', NEW.baseline_number, NEW.baseline_number - 1 USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $f$;

CREATE FUNCTION governance.assert_baseline_approved() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN  -- deferred: a baseline exists only together with an APPROVED approval of a human user for exactly this baseline (written in the same transaction)
  IF NOT EXISTS (SELECT 1 FROM governance.approvals a WHERE a.baseline_id = NEW.id AND a.decision = 'APPROVED') THEN
    RAISE EXCEPTION 'baseline % has no APPROVED approval of a human user', NEW.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END $f$;

CREATE FUNCTION governance.guard_approval_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE s text;
BEGIN  -- a decision is recorded only for a version that can still be decided
  IF NEW.requirement_version_id IS NOT NULL THEN SELECT status INTO s FROM requirements.requirement_versions WHERE id = NEW.requirement_version_id;
  ELSIF NEW.artifact_version_id IS NOT NULL THEN SELECT status INTO s FROM artifacts.artifact_versions WHERE id = NEW.artifact_version_id;
  ELSE RETURN NEW; END IF;
  IF s IS NULL OR s IN ('REJECTED','SUPERSEDED','ARCHIVED') THEN
    RAISE EXCEPTION 'cannot record a decision for a version in status %', coalesce(s, 'missing') USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
"""

INDEXES = (
    ("governance.baseline_items", "baseline_id"), ("governance.baselines", "previous_baseline_id"), ("governance.baselines", "change_request_id"),
    ("governance.change_requests", "base_baseline_id"), ("governance.change_requests", "requested_by"), ("artifacts.publications", "published_by"),
    ("requirements.requirement_versions", "confirmed_by"), ("artifacts.artifacts", "owner_user_id"), ("governance.rule_versions", "approver_user_id"),
    ("traceability.traceability_links", "confirmed_by"), ("decisions.decisions", "owner_user_id"), ("decisions.decisions", "approver_user_id"))


def upgrade() -> None:
    op.execute(FUNCTIONS)
    ini = "CREATE TRIGGER trg_{n}_initial_state BEFORE INSERT ON {t} FOR EACH ROW EXECUTE FUNCTION platform.require_initial_state({a})"
    for t, args in (
        ("requirements.requirement_versions", "'status', 'EXTRACTED,CANDIDATE', 'confirmed_by', 'confirmed_at'"),
        ("artifacts.artifact_versions", "'status', 'DRAFT'"),
        ("sources.uploads", "'status', 'PENDING', 'actual_size_bytes', 'verified_sha256', 'finalized_at', 'rejection_code'"),
        ("knowledge.extraction_records", "'status', 'STARTED', 'completed_at', 'error_code'"),
        ("governance.rule_versions", "'status', 'DRAFT', 'approver_user_id', 'approved_at', 'valid_from', 'valid_to'"),
        ("traceability.traceability_links", "'status', 'PROPOSED', 'confirmed_by', 'confirmed_at', 'superseded_at'")):
        op.execute(ini.format(n=t.split(".")[1], t=t, a=args))
    # C4
    op.execute("CREATE TRIGGER trg_rule_versions_approver BEFORE INSERT OR UPDATE ON governance.rule_versions FOR EACH ROW EXECUTE FUNCTION governance.guard_rule_approver()")
    # C2
    op.execute("CREATE TRIGGER trg_baselines_guard_insert BEFORE INSERT ON governance.baselines FOR EACH ROW EXECUTE FUNCTION governance.guard_baseline_insert()")
    op.execute("CREATE CONSTRAINT TRIGGER trg_baselines_approved AFTER INSERT ON governance.baselines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION governance.assert_baseline_approved()")
    # M1
    op.execute("CREATE TRIGGER trg_approvals_guard_insert BEFORE INSERT ON governance.approvals FOR EACH ROW EXECUTE FUNCTION governance.guard_approval_insert()")
    # M4
    for table, column in INDEXES:
        op.execute(f"CREATE INDEX ix_{table.split('.')[1]}_{column} ON {table} ({column})")


def downgrade() -> None:
    raise NotImplementedError("Hardening of tables that hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
