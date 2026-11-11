"""S07: TOTP replay guard — last accepted time step per MFA factor (AUTH-006, Auth v1.1 §5).

Revision ID: f1a8c2d95b36
Revises: e6b4a91c7d32

Additive (expand-only): a nullable column plus a trigger that makes it monotonic, so a code accepted once can never be accepted again, across API
restarts and replicas. The accepting UPDATE is a compare-and-set in the application (`last_used_step < :step`); the trigger is defence in depth
against any other writer moving the step backwards. Frozen literals only (see 0002).
"""
# ruff: noqa: E501  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "f1a8c2d95b36"
down_revision: str | None = "e6b4a91c7d32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION platform.keep_non_decreasing() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE c text; n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD);
BEGIN  -- TG_ARGV = bigint columns that may only grow once set (NULL -> value is allowed, value -> smaller/NULL is not)
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF o ->> c IS NOT NULL AND (n ->> c IS NULL OR (n ->> c)::bigint < (o ->> c)::bigint) THEN
      RAISE EXCEPTION 'column %.% can only increase', TG_TABLE_NAME, c USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $f$;
ALTER TABLE iam.mfa_factors ADD COLUMN last_used_step bigint NULL CONSTRAINT ck_mfa_factors_last_used_step CHECK (last_used_step IS NULL OR last_used_step >= 0);
CREATE TRIGGER trg_mfa_factors_step_monotonic BEFORE UPDATE ON iam.mfa_factors FOR EACH ROW EXECUTE FUNCTION platform.keep_non_decreasing('last_used_step');
""")


def downgrade() -> None:
    raise NotImplementedError("Forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
