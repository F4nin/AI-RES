"""G156 preparation: honest observed Flash profile representation, still disabled.

Revision ID: f64b9da053c8
Revises: e53a8c9d42b7

The one DROP NOT NULL is an expand: a new explicit mode permits NULL only for
the accepted DeepSeek Flash exception. The new IS TRUE constraint preserves
the non-NULL invariant for all immutable profiles; the original pin CHECK still
rejects empty/floating values. No profile, policy value, approval or grant is seeded.
The existing snapshot trigger freezes identity_mode along with all other config.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "f64b9da053c8"
down_revision: str | None = "e53a8c9d42b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.model_profiles ADD COLUMN identity_mode text NOT NULL DEFAULT 'IMMUTABLE' "
               "CONSTRAINT ck_model_profiles_identity_mode CHECK (identity_mode IN ('IMMUTABLE','FLASH_OBSERVED'))")
    op.execute("ALTER TABLE platform.model_profiles ALTER COLUMN pinned_model_version DROP NOT NULL")
    op.execute("ALTER TABLE platform.model_profiles ADD CONSTRAINT ck_model_profiles_identity_binding CHECK "
               "(((identity_mode='IMMUTABLE' AND pinned_model_version IS NOT NULL) OR "
               "(identity_mode='FLASH_OBSERVED' AND pinned_model_version IS NULL AND provider='deepseek' "
               "AND provider_model_id='deepseek-flash')) IS TRUE)")


def downgrade() -> None:
    raise NotImplementedError("Observed profile evidence cannot be recast as a pin; use a forward-fix or approved restore.")
