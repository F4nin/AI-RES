"""Require a new immutable generation when even the owner clears a drift block.

Revision ID: d42f7b8c31a6
Revises: c93e6a7d20b1

Forward-only refinement of the guard foundation. No approval is seeded or exposed.
This enforces generation advancement, not proof of a human approval procedure.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d42f7b8c31a6"
down_revision: str | None = "c93e6a7d20b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION platform.guard_admission_reapproval_generation() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF OLD.blocked AND NOT NEW.blocked AND NEW.current_generation<=OLD.current_generation THEN
    RAISE EXCEPTION 'clearing an admission block requires a new generation'
      USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_mac_reapproval_generation BEFORE UPDATE ON platform.model_admission_controls
  FOR EACH ROW EXECUTE FUNCTION platform.guard_admission_reapproval_generation();
""")


def downgrade() -> None:
    raise NotImplementedError("Admission safety is forward-only; use a forward-fix or approved restore.")
