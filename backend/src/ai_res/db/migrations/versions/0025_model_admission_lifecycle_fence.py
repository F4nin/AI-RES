"""G156: serialize observed profile lifecycle with admission, without new grants.

Revision ID: b86d2af275e0
Revises: a75c0eb164d9

Existing profile snapshots/lifecycle constraints, admissions and API SELECT-only
rights remain intact. No real profile, approval or authorization is seeded.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b86d2af275e0"
down_revision: str | None = "a75c0eb164d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
CREATE FUNCTION platform.fence_model_profile_lifecycle() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
BEGIN
  IF OLD.identity_mode='FLASH_OBSERVED' AND
     ROW(NEW.status,NEW.approved_at,NEW.approved_by,NEW.deprecated_at) IS DISTINCT FROM
     ROW(OLD.status,OLD.approved_at,OLD.approved_by,OLD.deprecated_at) THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
      'ai_res.model_profile_lifecycle:' || OLD.id::text, 0));
  END IF;
  RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION platform.fence_model_profile_lifecycle() FROM PUBLIC;
CREATE TRIGGER trg_model_profiles_lifecycle_fence BEFORE UPDATE ON platform.model_profiles
  FOR EACH ROW EXECUTE FUNCTION platform.fence_model_profile_lifecycle();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise NotImplementedError("Removing admission lifecycle fencing is unsafe; use a reviewed forward-fix.")
