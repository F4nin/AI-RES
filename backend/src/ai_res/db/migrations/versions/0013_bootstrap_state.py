"""S07: one-time bootstrap claim (AUTH-004, Auth v1.1 §3.1).

Revision ID: a47d3e19c0b5
Revises: f1a8c2d95b36

The first administrator can be created exactly once per installation. The claim is a singleton row (primary key on a constant): the second
INSERT fails with a unique violation even though the runtime role cannot SEE the first row (uniqueness ignores RLS), so the claim is atomic across
processes and cannot be bypassed by a different secret. The row is append-only (no UPDATE/DELETE/TRUNCATE) and tenant-scoped like everything else.
Frozen literals only (see 0002).
"""
# ruff: noqa: E501  -- DDL is built only from frozen literals in this file (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "a47d3e19c0b5"
down_revision: str | None = "f1a8c2d95b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"


def upgrade() -> None:
    op.execute("""
CREATE TABLE platform.bootstrap_state (
    singleton boolean CONSTRAINT pk_bootstrap_state PRIMARY KEY DEFAULT true CONSTRAINT ck_bootstrap_state_singleton CHECK (singleton),
    organization_id uuid NOT NULL CONSTRAINT fk_bootstrap_state_organization_id_organizations REFERENCES organization.organizations(id) ON DELETE RESTRICT,
    secret_digest bytea NOT NULL CONSTRAINT ck_bootstrap_state_secret_digest CHECK (octet_length(secret_digest) = 32),
    consumed_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ix_bootstrap_state_organization_id ON platform.bootstrap_state (organization_id);
""")
    op.execute("ALTER TABLE platform.bootstrap_state ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.bootstrap_state FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p_bootstrap_state_tenant_scope ON platform.bootstrap_state FOR ALL TO ai_res_api_group USING ({ORG}) WITH CHECK ({ORG})")
    op.execute(f"CREATE POLICY p_bootstrap_state_owner_migration ON platform.bootstrap_state FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
    op.execute("GRANT SELECT, INSERT ON platform.bootstrap_state TO ai_res_api_group")
    op.execute("CREATE TRIGGER trg_bootstrap_state_append_only BEFORE UPDATE OR DELETE ON platform.bootstrap_state FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
    op.execute("CREATE TRIGGER trg_bootstrap_state_no_truncate BEFORE TRUNCATE ON platform.bootstrap_state FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def downgrade() -> None:
    raise NotImplementedError("Forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
