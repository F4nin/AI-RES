"""Honest observed-profile persistence, no real model or human admission evidence."""
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from psycopg import errors
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm.registry import ProfileStatus
from ai_res.modules.model_registry.admission import AdmissionDenied, ModelAdmissionGuard
from ai_res.modules.model_registry.observed_profiles import ObservedProfileLoadError, load_observed_profile_reference
from ai_res.modules.model_registry.repository import RegistryLoadError, load_model_registry

from .conftest import Pg, alembic_config, run_audit
from .test_model_admission import api_engine as api_engine
from .test_model_admission import expected_for, install_generation, seed
from .test_model_registry import add_profile, approve

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("overrides", [
    {"pinned_model_version": None},
    {"identity_mode": "UNKNOWN", "pinned_model_version": None},
    {"identity_mode": None},
    {"identity_mode": "FLASH_OBSERVED", "pinned_model_version": "not-a-pin"},
    {"identity_mode": "FLASH_OBSERVED", "pinned_model_version": None, "provider": "other"},
    {"identity_mode": "FLASH_OBSERVED", "pinned_model_version": None, "provider_model_id": "deepseek-v4-pro"},
    {"identity_mode": "IMMUTABLE", "pinned_model_version": "latest"},
    {"identity_mode": "IMMUTABLE", "pinned_model_version": " "},
])
def test_profile_mode_combinations_fail_closed_including_sql_null(migrated: Pg, overrides):
    fields = {"provider": "deepseek", "provider_model_id": "deepseek-flash"} | overrides
    with migrated.connect() as conn, pytest.raises((errors.CheckViolation, errors.NotNullViolation)):
        add_profile(conn, **fields)


def test_observed_row_uses_null_pin_without_weakening_old_immutable_rows(migrated: Pg):
    with migrated.connect() as conn:
        immutable = add_profile(conn, "legacy-fixture")
        observed = add_profile(conn, "observed-fixture", provider="deepseek", provider_model_id="deepseek-flash",
                               identity_mode="FLASH_OBSERVED", pinned_model_version=None)
        assert conn.execute("SELECT identity_mode,pinned_model_version FROM platform.model_profiles WHERE id=%s",
                            [immutable]).fetchone() == ("IMMUTABLE", "2026-01-01")
        assert conn.execute("SELECT identity_mode,pinned_model_version FROM platform.model_profiles WHERE id=%s",
                            [observed]).fetchone() == ("FLASH_OBSERVED", None)


def test_mode_and_pin_remain_immutable_even_for_db_owner(migrated: Pg):
    with migrated.connect() as conn:
        profile = add_profile(conn, provider="deepseek", provider_model_id="deepseek-flash")
        with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
            conn.execute("UPDATE platform.model_profiles SET identity_mode='FLASH_OBSERVED',pinned_model_version=NULL WHERE id=%s", [profile])
        observed = add_profile(conn, "observed-fixture", provider="deepseek", provider_model_id="deepseek-flash",
                               identity_mode="FLASH_OBSERVED", pinned_model_version=None)
        with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
            conn.execute("UPDATE platform.model_profiles SET identity_mode='IMMUTABLE',pinned_model_version='synthetic-pin' WHERE id=%s", [observed])


async def test_legacy_loader_skips_candidate_observed_but_never_converts_active_observed(migrated: Pg, api_engine: AsyncEngine):
    with migrated.connect() as conn:
        legacy = add_profile(conn, "legacy-fixture")
        approve(conn, legacy)
        observed = add_profile(conn, "observed-fixture", provider="deepseek", provider_model_id="deepseek-flash",
                               identity_mode="FLASH_OBSERVED", pinned_model_version=None)
    factory = create_session_factory(api_engine)
    async with UnitOfWork(factory) as uow:
        registry = await load_model_registry(uow.session)
        assert registry.get(legacy) is not None and registry.get(observed) is None
    with migrated.connect() as conn:
        approve(conn, observed)  # Synthetic DB-owner fixture only; no production approval path.
    async with UnitOfWork(factory) as uow:
        with pytest.raises(RegistryLoadError):
            await load_model_registry(uow.session)


async def test_readonly_observed_reference_reports_metadata_without_execution_or_approval(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated, approved=False)
    factory = create_session_factory(api_engine)
    async with UnitOfWork(factory) as uow:
        ref = await load_observed_profile_reference(uow.session, expected.managed_versions.profile_id)
        assert ref is not None and ref.status is ProfileStatus.CANDIDATE
        assert ref.pinned_model_version is None and ref.identity_mode.value == "FLASH_OBSERVED"
        assert ref.provider == "deepseek" and ref.provider_model_id == "deepseek-flash"
        assert not hasattr(ref, "usable_at") and not hasattr(ref, "capabilities")
        with pytest.raises(FrozenInstanceError):
            ref.profile_version = 2
        assert await load_observed_profile_reference(uow.session, uuid4()) is None
    with pytest.raises(AdmissionDenied) as denied:
        await ModelAdmissionGuard(factory).begin(ref.profile_id, expected.managed_versions, request_ref="cannot-admit-by-read")
    assert denied.value.code == "PROFILE_UNAVAILABLE"


async def test_new_reader_and_guard_refuse_immutable_profile_without_conversion(migrated: Pg, api_engine: AsyncEngine):
    with migrated.connect() as conn:
        profile = add_profile(conn, provider="deepseek", provider_model_id="deepseek-flash")
        approve(conn, profile)
    expected = expected_for(profile)
    install_generation(migrated, expected)
    factory = create_session_factory(api_engine)
    async with UnitOfWork(factory) as uow:
        with pytest.raises(ObservedProfileLoadError):
            await load_observed_profile_reference(uow.session, profile)
    with pytest.raises(AdmissionDenied) as denied:
        await ModelAdmissionGuard(factory).begin(profile, expected.managed_versions, request_ref="cannot-infer-observed")
    assert denied.value.code == "PROFILE_UNAVAILABLE"


def test_runtime_keeps_readonly_registry_grants_for_new_identity_mode(migrated: Pg):
    expected = seed(migrated, approved=False)
    with migrated.connect("ai_res_api") as conn:
        assert conn.execute("SELECT identity_mode,pinned_model_version FROM platform.model_profiles WHERE id=%s",
                            [expected.managed_versions.profile_id]).fetchone() == ("FLASH_OBSERVED", None)
        for statement in ("UPDATE platform.model_profiles SET status='APPROVED'", "UPDATE platform.model_profiles SET identity_mode='IMMUTABLE'",
                          "INSERT INTO platform.model_profiles(id,profile_key,profile_version) VALUES(gen_random_uuid(),'no',1)"):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(statement)


def test_upgrade_previous_head_preserves_profile_values_and_seeds_no_observed_rows(empty_db: Pg, upgrade):
    scripts = ScriptDirectory.from_config(alembic_config())
    revision = next(r for r in scripts.walk_revisions() if Path(r.path).name.endswith("_model_profile_identity_mode.py"))
    assert isinstance(revision.down_revision, str)
    upgrade(revision.down_revision)
    with empty_db.connect() as conn:
        profile = add_profile(conn, "previous-mode-fixture")
        before = conn.execute("SELECT to_jsonb(p) FROM platform.model_profiles p WHERE id=%s", [profile]).fetchone()[0]
    upgrade(revision.revision)
    with empty_db.connect() as conn:
        actual = conn.execute("SELECT to_jsonb(p) FROM platform.model_profiles p WHERE id=%s", [profile]).fetchone()[0]
        assert actual.pop("identity_mode") == "IMMUTABLE" and actual == before
        assert conn.execute("SELECT count(*) FROM platform.model_profiles WHERE identity_mode='FLASH_OBSERVED'").fetchone() == (0,)
        assert run_audit(conn, "rls_coverage.sql") == [] and run_audit(conn, "grants_audit.sql") == []


async def test_readonly_reference_revalidates_corrupt_metadata_without_echoing_it(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated, approved=False)
    # A SQL projection with malformed values represents a broken row/unsupported
    # contract, never a way to create an executable profile. Use the real reader
    # constructor separately because production CHECKs reject this data first.
    from ai_res.modules.model_registry.observed_profiles import ObservedProfileReference, ProfileIdentityMode
    with pytest.raises(ValueError) as invalid:
        ObservedProfileReference(expected.managed_versions.profile_id, "invalid\nmetadata", 1, ProfileIdentityMode.FLASH_OBSERVED,
                                 "deepseek", "deepseek-flash", None, ProfileStatus.CANDIDATE, None, None)
    assert "invalid\nmetadata" not in str(invalid.value)
    async with UnitOfWork(create_session_factory(api_engine)) as uow:
        # The read remains a normal parameterized SQL read under runtime SELECT,
        # not a bypass around the reference validation or a grant producer.
        assert (await uow.session.execute(text("SELECT status FROM platform.model_profiles WHERE id=:p"),
                                         {"p": expected.managed_versions.profile_id})).scalar_one() == "CANDIDATE"
