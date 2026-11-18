"""G156 additive upgrade preserves legacy profiles and seeds no admission authority."""
from dataclasses import replace
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from psycopg import errors, sql

from .conftest import Pg, alembic_config, run_audit
from .test_model_admission import install_generation, seed
from .test_model_registry import add_profile

pytestmark = pytest.mark.postgres


def test_guard_upgrade_preserves_previous_profiles_and_starts_closed(empty_db: Pg, upgrade):
    scripts = ScriptDirectory.from_config(alembic_config())
    revisions = [r for r in scripts.walk_revisions() if Path(r.path).name.endswith("_model_admission_guard.py")]
    assert len(revisions) == 1
    revision = revisions[0]
    assert isinstance(revision.down_revision, str)
    upgrade(revision.down_revision)
    with empty_db.connect() as conn:
        # Synthetic previous-version row, never a real provider selector or approval.
        profile_id = add_profile(conn, "previous-guard-fixture")
        before = conn.execute("SELECT to_jsonb(p) FROM platform.model_profiles p WHERE id=%s", [profile_id]).fetchone()
    upgrade(revision.revision)
    with empty_db.connect() as conn:
        assert conn.execute("SELECT to_jsonb(p) FROM platform.model_profiles p WHERE id=%s", [profile_id]).fetchone() == before
        for table in ("model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit"):
            assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("platform", table))).fetchone() == (0,)
            assert conn.execute("SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) FROM pg_class WHERE oid=%s::regclass",
                                [f"platform.{table}"]).fetchone() == (True, True, "ai_res_owner")
        assert run_audit(conn, "rls_coverage.sql") == []
        assert run_audit(conn, "grants_audit.sql") == []
    with empty_db.connect("ai_res_api") as api:
        assert api.execute("SELECT id FROM platform.model_profiles WHERE id=%s", [profile_id]).fetchone() == (profile_id,)
        assert api.execute("SELECT count(*) FROM platform.model_admission_controls").fetchone() == (0,)


def test_even_owner_clearing_block_requires_new_immutable_generation(migrated: Pg):
    expected = seed(migrated)
    with migrated.connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE ai_res_owner")
        conn.execute("SELECT set_config('app.migration_mode','on',true)")
        conn.execute("UPDATE platform.model_admission_controls SET blocked=true")
        with pytest.raises(errors.IntegrityConstraintViolation, match="new generation"), conn.transaction():
            conn.execute("UPDATE platform.model_admission_controls SET blocked=false")
        assert conn.execute("SELECT current_generation,blocked FROM platform.model_admission_controls").fetchone() == (1, True)
    install_generation(migrated, replace(expected, admission_generation=2, evidence_sha256="e" * 64))
    with migrated.connect() as conn:
        assert conn.execute("SELECT current_generation,blocked FROM platform.model_admission_controls").fetchone() == (2, False)
        assert conn.execute("SELECT count(*) FROM platform.model_admission_versions").fetchone() == (2,)
