"""ADR-034 (5): explicit migration policies for `ai_res_owner` under FORCE RLS, S05 slice F.

Revision ID: f3a96b1c8e47
Revises: d4c18a7e5b92

Migrations run as `ai_res_owner` (SET ROLE by the migrator). FORCE ROW LEVEL SECURITY applies to the table owner too, so without a policy a backfill or data
fix on a tenant table sees ZERO rows and finishes "successfully" as a silent no-op. This revision gives every RLS-protected table one policy for the owner
role, enabled only while the transaction-local flag `app.migration_mode` is 'on'. A revision that backfills tenant data sets it explicitly
(`SELECT set_config('app.migration_mode', 'on', true)`); `env.py` switches it off again after every revision (all revisions of one upgrade share a transaction), so a revision enables it for itself only. Without the flag the owner stays default-deny. Runtime principals are unaffected (the policy is
`TO ai_res_owner` only, and they are not members of the owner role: checked by revision 0001). `rls_coverage.sql` now fails for any RLS table that lacks
this policy, so a later revision that adds a table must create it (same statement as below).
Frozen literals only (see 0002).
"""
# ruff: noqa: E501, S608  -- DDL is built only from catalog names of this database (no external input)
from collections.abc import Sequence

from alembic import op

revision: str = "f3a96b1c8e47"
down_revision: str | None = "d4c18a7e5b92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("iam", "organization", "project", "work", "requirements", "sources", "knowledge", "decisions", "artifacts", "traceability", "governance",
           "agents", "context", "integrations", "audit", "platform", "operations", "execution")
GATE_SQL = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"
GATE = GATE_SQL.replace("'", "''")  # embedded in the SQL string literal passed to format() below: quotes are doubled


def upgrade() -> None:
    schemas = ", ".join(f"'{s}'" for s in SCHEMAS)
    op.execute(f"""
DO $m$
DECLARE t record;
BEGIN
  FOR t IN SELECT n.nspname AS s, c.relname AS r FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','p') AND NOT c.relispartition AND c.relrowsecurity AND c.relforcerowsecurity AND n.nspname IN ({schemas})
  LOOP
    IF length('p_' || t.r || '_owner_migration') > 63 THEN RAISE EXCEPTION 'table name % is too long for its owner migration policy name (PostgreSQL would truncate it)', t.r; END IF;
    EXECUTE format('CREATE POLICY %I ON %I.%I FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})', 'p_' || t.r || '_owner_migration', t.s, t.r);
  END LOOP;
END $m$""")


def downgrade() -> None:
    raise NotImplementedError("Policies protect tables that hold data; forward-fix with a new revision or restore from backup/PITR (Blueprint §11).")
