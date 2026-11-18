"""Preserve historical audit actors across logical restore under a different role.

Revision ID: e53a8c9d42b7
Revises: d42f7b8c31a6

The session-dependent CHECK is invalid for persisted history. The actual writer
still comes from DEFAULT current_user; runtime column INSERT grants exclude it
and occurred_at. No rows/columns, defaults or privilege restrictions are removed.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "e53a8c9d42b7"
down_revision: str | None = "d42f7b8c31a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.model_admission_audit DROP CONSTRAINT ck_maa_writer")


def downgrade() -> None:
    raise NotImplementedError("Do not reintroduce a session-dependent audit CHECK; use a forward-fix or approved restore.")
