# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S15: Model Registry table (migration 0017, ADR-106) on real PostgreSQL 16: immutability, forward-only lifecycle, approval recorded, runtime SELECT-only, loader."""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import errors
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm import errors as E
from ai_res.llm.registry import ProfileStatus
from ai_res.modules.model_registry.repository import load_model_registry
from ai_res.platform.config import load_settings

from .conftest import Pg, run_audit

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
ORG, USER = uuid4(), uuid4()


def add_profile(c, key: str = "alpha", version: int = 1, **over) -> UUID:  # type: ignore[no-untyped-def]
    pid = uuid4()
    row = {"provider": "prov", "provider_model_id": "m", "pinned_model_version": "2026-01-01", "capabilities": ["CHAT", "STRUCTURED_OUTPUT"], "context_window_tokens": 8000,
           "max_output_tokens": 1000, "data_classifications": ["INTERNAL"], "allowed_regions": ["eu"], "egress": "EXTERNAL", "timeout_seconds": 30, "retry_class": "BOUNDED"} | over
    cols = ", ".join(row)
    c.execute(f"INSERT INTO platform.model_profiles (id, profile_key, profile_version, {cols}) VALUES (%s, %s, %s, {', '.join(['%s'] * len(row))})", [pid, key, version, *row.values()])
    return pid


def approve(c, pid: UUID) -> None:  # type: ignore[no-untyped-def]
    c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o') ON CONFLICT DO NOTHING", [ORG])
    c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'u@example.test','u@example.test','u') ON CONFLICT DO NOTHING", [USER, ORG])
    c.execute("UPDATE platform.model_profiles SET status='APPROVED', approved_at=%s, approved_by=%s WHERE id=%s", [NOW, USER, pid])


def test_registry_starts_empty_and_audits_pass(migrated: Pg):
    with migrated.connect() as c:
        assert c.execute("SELECT count(*) FROM platform.model_profiles").fetchone() == (0,)
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == []


def test_profile_is_born_candidate_and_approval_needs_who_and_when(migrated: Pg):
    with migrated.connect() as c:
        with pytest.raises(errors.IntegrityConstraintViolation, match="CANDIDATE"):
            add_profile(c, "x", status="APPROVED", approved_at=NOW)
        pid = add_profile(c)
        with pytest.raises(errors.CheckViolation):  # approved without approved_by/approved_at
            c.execute("UPDATE platform.model_profiles SET status='APPROVED' WHERE id=%s", [pid])
        approve(c, pid)
        assert c.execute("SELECT status FROM platform.model_profiles WHERE id=%s", [pid]).fetchone() == ("APPROVED",)
        with pytest.raises(errors.IntegrityConstraintViolation, match="approval"):
            c.execute("UPDATE platform.model_profiles SET approved_at = now() WHERE id=%s", [pid])


def test_pinned_version_must_not_be_a_floating_alias_and_values_are_checked(migrated: Pg):
    with migrated.connect() as c:
        for alias in ("latest", " Latest ", "stable", ""):
            with pytest.raises(errors.CheckViolation):
                add_profile(c, f"k{len(alias)}{alias.strip()}", pinned_model_version=alias)
        for bad in ({"capabilities": ["TELEPATHY"]}, {"egress": "PUBLIC"}, {"max_output_tokens": 9000}, {"timeout_seconds": 0}, {"retry_class": "FOREVER"},
                    {"cost_currency": "EUR"}):  # rates are all-or-nothing
            with pytest.raises(errors.CheckViolation):
                add_profile(c, "bad", **bad)


def test_profile_is_immutable_except_lifecycle_and_never_deleted_or_truncated(migrated: Pg):
    with migrated.connect() as c:
        pid = add_profile(c)
        for column, value in (("pinned_model_version", "'2026-02-02'"), ("provider_model_id", "'other'"), ("profile_version", "2"), ("capabilities", "ARRAY['CHAT','VISION']"),
                              ("egress", "'LOCAL'"), ("context_window_tokens", "9000")):
            with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
                c.execute(f"UPDATE platform.model_profiles SET {column} = {value} WHERE id = %s", [pid])
        with pytest.raises(errors.IntegrityConstraintViolation, match="never deleted"):
            c.execute("DELETE FROM platform.model_profiles WHERE id=%s", [pid])
        with pytest.raises(errors.IntegrityConstraintViolation, match="TRUNCATE"):
            c.execute("TRUNCATE platform.model_profiles")
        with pytest.raises(errors.UniqueViolation):
            add_profile(c)  # same (profile_key, profile_version)
        assert add_profile(c, "alpha", 2)


def test_status_only_moves_forward(migrated: Pg):
    with migrated.connect() as c:
        pid = add_profile(c)
        approve(c, pid)
        c.execute("UPDATE platform.model_profiles SET status='DEPRECATED', deprecated_at=%s WHERE id=%s", [NOW, pid])
        for back in ("APPROVED", "CANDIDATE"):
            with pytest.raises(errors.IntegrityConstraintViolation, match="may not go back"):
                c.execute("UPDATE platform.model_profiles SET status=%s WHERE id=%s", [back, pid])
        with pytest.raises(errors.IntegrityConstraintViolation, match="deprecated_at"):
            c.execute("UPDATE platform.model_profiles SET deprecated_at = now() WHERE id=%s", [pid])
        c.execute("UPDATE platform.model_profiles SET status='RETIRED' WHERE id=%s", [pid])


def test_runtime_role_reads_but_never_writes_the_registry(migrated: Pg):
    with migrated.connect() as c:
        pid = add_profile(c)
    with migrated.connect("ai_res_api") as api:
        assert api.execute("SELECT id FROM platform.model_profiles").fetchone() == (pid,)
        for sql in ("INSERT INTO platform.model_profiles (id, profile_key, profile_version) VALUES (gen_random_uuid(), 'k', 1)",
                    "UPDATE platform.model_profiles SET status = 'APPROVED'", "DELETE FROM platform.model_profiles", "TRUNCATE platform.model_profiles"):
            with pytest.raises(errors.InsufficientPrivilege):
                api.execute(sql)


@pytest.fixture
async def api_engine(migrated: Pg, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    pw = tmp_path / "pw"
    pw.write_text(migrated.passwords["ai_res_api"])
    settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": migrated.host, "AI_RES_DB_PORT": str(migrated.port), "AI_RES_DB_USER": "ai_res_api",
                              "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable"})
    engine = create_runtime_engine(settings)
    yield engine
    await engine.dispose()


async def test_loader_builds_a_registry_that_resolves_only_approved_profiles(migrated: Pg, api_engine: AsyncEngine):
    with migrated.connect() as c:
        ok = add_profile(c, "alpha", cost_currency="EUR", cost_input_per_million=1.5, cost_output_per_million=3, fallback_group="g", rate_limit_rpm=60)
        approve(c, ok)
        cand = add_profile(c, "beta")
    async with UnitOfWork(create_session_factory(api_engine)) as uow:
        registry = await load_model_registry(uow.session)
    assert len(registry) == 2
    p = registry.resolve(ok, NOW)
    assert (p.status, p.provider, p.pinned_model_version, p.fallback_group, p.rate_limit_rpm) == (ProfileStatus.APPROVED, "prov", "2026-01-01", "g", 60)
    assert p.cost_rates is not None and str(p.cost_rates.input_per_million) == "1.500000" and p.cost_rates.currency == "EUR"
    with pytest.raises(E.ModelProfileNotApproved):
        registry.resolve(cand, NOW)
    with pytest.raises(E.ModelProfileNotFound):
        registry.resolve(uuid4(), NOW)


def test_label_and_region_vocabulary_is_enforced_by_the_database(migrated: Pg):
    with migrated.connect() as c:
        for bad in ({"data_classifications": ["internal"]}, {"data_classifications": ["OK", "bad label"]}, {"allowed_regions": ["EU"]}, {"allowed_regions": ["eu", ""]}):
            with pytest.raises(errors.CheckViolation):
                add_profile(c, "bad", **bad)
