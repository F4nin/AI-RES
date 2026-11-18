"""Real PG16 guard foundation; profiles and approvals are synthetic fixtures.

No provider, real snapshot, owner approval or enabled observed profile is proved.
"""
import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import errors, sql
from psycopg.types.json import Jsonb
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.cas import canonical_json
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityExpectation,
    IdentityObservation,
    ManagedVersions,
    ObservedFingerprint,
    ObservedProviderIdentity,
)
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, ModelAdmissionGuard, evidence_hash
from ai_res.platform.config import load_settings

from .conftest import Pg
from .test_model_registry import add_profile, approve

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 11, 17, tzinfo=UTC)
TABLES = ("model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit")


@pytest.fixture
async def api_engine(migrated: Pg, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    pw = tmp_path / "admission_api_pw"
    pw.write_text(migrated.passwords["ai_res_api"])
    settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": migrated.host, "AI_RES_DB_PORT": str(migrated.port),
                              "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable"})
    engine = create_runtime_engine(settings)
    try:
        yield engine
    finally:
        await engine.dispose()


def expected_for(profile_id: UUID, generation=1) -> IdentityExpectation:
    versions = ManagedVersions("a" * 40, profile_id, 1, "b" * 64, "c" * 64, None)
    identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "DeepSeek-V4.1-Flash-0000",
                                        ObservedFingerprint(FingerprintPresence.VALUE, "synthetic-fingerprint"))
    return IdentityExpectation(versions, identity, generation, "d" * 64)


def install_generation(pg: Pg, expected: IdentityExpectation) -> None:
    """DB-owner fixture setup, NOT a production human approval procedure."""
    with pg.connect() as c, c.transaction():
        c.execute("SET LOCAL ROLE ai_res_owner")
        c.execute("SELECT set_config('app.migration_mode','on',true)")
        c.execute("INSERT INTO platform.model_admission_versions(profile_id,generation,profile_version,expectation,expectation_sha256) VALUES(%s,%s,%s,%s,%s)",
                  [expected.managed_versions.profile_id, expected.admission_generation, expected.managed_versions.profile_version,
                   Jsonb(expected.to_dict()), evidence_hash(expected)])
        c.execute("INSERT INTO platform.model_admission_controls(profile_id,current_generation) VALUES(%s,%s) "
                  "ON CONFLICT(profile_id) DO UPDATE SET current_generation=EXCLUDED.current_generation,blocked=false",
                  [expected.managed_versions.profile_id, expected.admission_generation])


def seed(pg: Pg, *, approved=True, provider="deepseek", model="deepseek-flash", key="guard-fixture") -> IdentityExpectation:
    with pg.connect() as c:
        profile_id = add_profile(c, key=key, provider=provider, provider_model_id=model,
                                 identity_mode="FLASH_OBSERVED", pinned_model_version=None)
        if approved:
            approve(c, profile_id)
    expected = expected_for(profile_id)
    install_generation(pg, expected)
    return expected


def observed(expected: IdentityExpectation, request_ref="call-1") -> IdentityObservation:
    return IdentityObservation(expected.managed_versions, expected.identity, NOW, request_ref, "synthetic-provider-request")


def guard(engine: AsyncEngine) -> ModelAdmissionGuard:
    return ModelAdmissionGuard(create_session_factory(engine))


def counts(pg: Pg) -> tuple[int, int]:
    with pg.connect() as c:
        calls = c.execute("SELECT count(*) FROM platform.model_admission_calls").fetchone()[0]
        audits = c.execute("SELECT count(*) FROM platform.model_admission_audit").fetchone()[0]
        return calls, audits


async def test_missing_admission_cannot_reserve_or_dispatch(migrated: Pg, api_engine: AsyncEngine):
    profile_id = uuid4()
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).begin(profile_id, expected_for(profile_id).managed_versions, request_ref="call-1")
    assert error.value.code == "ADMISSION_MISSING" and counts(migrated) == (0, 0)


async def test_begin_commit_valid_finalization_and_exact_replay_have_no_duplicate_facts(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    assert counts(migrated) == (1, 1)
    await service.finalize(ticket, observed(expected))
    await service.finalize(ticket, observed(expected))
    assert counts(migrated) == (1, 2)
    with pytest.raises(AdmissionDenied):
        await service.begin(ticket.profile_id, expected.managed_versions, request_ref="call-1")
    assert counts(migrated) == (1, 2)
    with migrated.connect() as c:
        assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("VALIDATED",)
        assert c.execute("SELECT DISTINCT writer_role FROM platform.model_admission_audit").fetchall() == [("ai_res_api",)]


@pytest.mark.parametrize("approved,provider,model", [(False, "deepseek", "deepseek-flash"), (True, "other", "deepseek-flash"),
                                                    (True, "deepseek", "deepseek-v4-pro")])
async def test_candidate_or_wrong_provider_model_refuses_before_receipt(migrated: Pg, api_engine: AsyncEngine, approved, provider, model):
    if provider != "deepseek" or model != "deepseek-flash":
        # The storage contract now rejects invalid observed modes before a
        # profile/admission can exist, instead of manufacturing a fake pin.
        with pytest.raises(errors.CheckViolation):
            seed(migrated, approved=approved, provider=provider, model=model)
        assert counts(migrated) == (0, 0)
        return
    expected = seed(migrated, approved=approved, provider=provider, model=model)
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    assert error.value.code == "PROFILE_UNAVAILABLE" and counts(migrated) == (0, 0)


async def test_parallel_begins_reserve_only_one_single_flight_receipt(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    results = await asyncio.gather(*[guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref=f"call-{i}")
                                    for i in range(2)], return_exceptions=True)
    assert sum(isinstance(result, AdmissionDenied) for result in results) == 1
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert counts(migrated) == (1, 1)


async def test_identity_mismatch_commits_sticky_block_before_refusal_and_survives_new_connections(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    changed = replace(observed(expected), identity=replace(expected.identity, fingerprint=ObservedFingerprint(FingerprintPresence.VALUE, "drifted")))
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, changed)
    assert error.value.code == "IDENTITY_MISMATCH"
    with migrated.connect() as c:
        assert c.execute("SELECT blocked FROM platform.model_admission_controls").fetchone() == (True,)
        assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("BLOCKED",)
    await api_engine.dispose()  # New physical connections, no in-memory guard state.
    with pytest.raises(AdmissionDenied) as blocked:
        await guard(api_engine).begin(ticket.profile_id, expected.managed_versions, request_ref="call-2")
    assert blocked.value.code == "PROFILE_BLOCKED" and counts(migrated) == (1, 2)


@pytest.mark.parametrize("malformed", ["{", '{"sourceText":"private-fixture-text"}', '{"schemaVersion":"99.0"}'])
async def test_malformed_outcome_commits_block_without_storing_source_content(migrated: Pg, api_engine: AsyncEngine, malformed):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, malformed)
    assert error.value.code == "MALFORMED_OBSERVATION" and "private-fixture-text" not in str(error.value)
    with migrated.connect() as c:
        assert c.execute("SELECT status,observed_sha256 FROM platform.model_admission_calls").fetchone() == ("BLOCKED", None)
        records = c.execute("SELECT row_to_json(a)::text FROM platform.model_admission_audit a").fetchall()
        assert "private-fixture-text" not in str(records)


async def test_audit_failure_pending_survives_owner_generation_advance_and_new_connections(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with migrated.connect() as c:
        c.execute("CREATE FUNCTION platform.fixture_fail_admission_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                  "BEGIN RAISE EXCEPTION 'fixture audit outage'; END $$")
        c.execute("CREATE TRIGGER fixture_fail_admission_audit BEFORE INSERT ON platform.model_admission_audit "
                  "FOR EACH ROW EXECUTE FUNCTION platform.fixture_fail_admission_audit()")
    with pytest.raises(AdmissionUnavailable) as error:
        await guard(api_engine).finalize(ticket, observed(expected))
    assert "fixture audit outage" not in str(error.value)
    install_generation(migrated, replace(expected, admission_generation=2))
    await api_engine.dispose()
    with migrated.connect() as c:
        assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("IN_FLIGHT",)
        assert c.execute("SELECT current_generation,blocked FROM platform.model_admission_controls").fetchone() == (2, False)
    with pytest.raises(AdmissionDenied) as unresolved:
        await guard(api_engine).begin(ticket.profile_id, expected.managed_versions, request_ref="call-2")
    assert unresolved.value.code == "CALL_UNRESOLVED_OR_REUSED" and counts(migrated) == (1, 1)


async def test_owner_fixture_new_generation_rejects_stale_reply_without_erasing_pending(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    install_generation(migrated, replace(expected, admission_generation=2, evidence_sha256="e" * 64))
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, "malformed old reply")
    assert error.value.code == "STALE_GENERATION"
    with pytest.raises(AdmissionDenied):
        await guard(api_engine).begin(ticket.profile_id, expected.managed_versions, request_ref="call-2")
    with migrated.connect() as c:
        assert c.execute("SELECT current_generation,blocked,call_sequence FROM platform.model_admission_controls").fetchone() == (2, False, 1)
        assert c.execute("SELECT count(*) FROM platform.model_admission_versions").fetchone() == (2,)


async def test_owner_new_generation_after_terminal_block_can_begin_without_rewriting_old_evidence(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with pytest.raises(AdmissionDenied):
        await guard(api_engine).finalize(ticket, "malformed")
    next_expected = replace(expected, admission_generation=2, evidence_sha256="e" * 64)
    install_generation(migrated, next_expected)
    new_ticket = await guard(api_engine).begin(ticket.profile_id, next_expected.managed_versions, request_ref="call-2")
    await guard(api_engine).finalize(new_ticket, observed(next_expected, "call-2"))
    with pytest.raises(AdmissionDenied) as old:
        await guard(api_engine).finalize(ticket, observed(expected))
    assert old.value.code == "STALE_GENERATION" and counts(migrated) == (2, 4)


async def test_wrong_ticket_binding_cannot_finalize_or_release_pending(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    for wrong in (replace(ticket, request_ref="other"), replace(ticket, call_id=uuid4()), replace(ticket, expected_sha256="f" * 64),
                  replace(ticket, profile_version=2)):
        with pytest.raises(AdmissionDenied):
            await guard(api_engine).finalize(wrong, observed(expected))
    assert counts(migrated) == (1, 1)
    with pytest.raises(AdmissionDenied):
        await guard(api_engine).begin(ticket.profile_id, expected.managed_versions, request_ref="call-2")


async def test_known_foreign_profile_receipt_and_context_cannot_release_another_profile(migrated: Pg, api_engine: AsyncEngine):
    first = seed(migrated)
    second = seed(migrated, key="guard-fixture-b")
    service = guard(api_engine)
    ticket_a = await service.begin(first.managed_versions.profile_id, first.managed_versions, request_ref="call-a")
    ticket_b = await service.begin(second.managed_versions.profile_id, second.managed_versions, request_ref="call-b")
    for forged in (replace(ticket_a, call_id=ticket_b.call_id), replace(ticket_b, profile_id=ticket_a.profile_id)):
        with pytest.raises(AdmissionDenied):
            await service.finalize(forged, observed(first, "call-a"))
    with migrated.connect("ai_res_api") as api, api.transaction():
        api.execute("SELECT set_config('app.model_profile_id',%s,true)", [str(ticket_b.profile_id)])
        assert api.execute("SELECT id FROM platform.model_admission_calls WHERE id=%s", [ticket_a.call_id]).fetchall() == []
        changed = api.execute("UPDATE platform.model_admission_calls SET status='BLOCKED',finalized_at=clock_timestamp() WHERE id=%s", [ticket_a.call_id])
        assert changed.rowcount == 0
        with pytest.raises(errors.InsufficientPrivilege), api.transaction():
            api.execute("INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code) "
                        "VALUES(gen_random_uuid(),%s,%s,'BLOCKED','IDENTITY_MISMATCH')", [ticket_a.profile_id, ticket_a.call_id])
    assert counts(migrated) == (2, 2)
    with migrated.connect() as c:
        assert c.execute("SELECT DISTINCT status FROM platform.model_admission_calls").fetchall() == [("IN_FLIGHT",)]


async def test_begin_audit_failure_rolls_back_receipt_and_sequence_before_any_ticket(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    with migrated.connect() as c:
        c.execute("CREATE FUNCTION platform.fixture_fail_begin_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                  "BEGIN RAISE EXCEPTION 'fixture begin audit outage'; END $$")
        c.execute("CREATE TRIGGER fixture_fail_begin_audit BEFORE INSERT ON platform.model_admission_audit "
                  "FOR EACH ROW EXECUTE FUNCTION platform.fixture_fail_begin_audit()")
    for _ in range(2):
        with pytest.raises(AdmissionUnavailable):
            await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
        await api_engine.dispose()
        assert counts(migrated) == (0, 0)
        with migrated.connect() as c:
            assert c.execute("SELECT call_sequence FROM platform.model_admission_controls").fetchone() == (0,)


@pytest.mark.parametrize("invalid", ["old-contract", "missing-fingerprint", "hash-mismatch"])
async def test_stored_owner_fixture_metadata_still_requires_active_semantic_validation(migrated: Pg, api_engine: AsyncEngine, invalid):
    expected = seed(migrated)
    data = replace(expected, admission_generation=2).to_dict()
    if invalid == "old-contract":
        data["schemaVersion"] = "0.1"
    elif invalid == "missing-fingerprint":
        data["identity"]["fingerprint"] = {"presence": "NULL", "value": None}
    digest = hashlib.sha256(canonical_json(data).encode()).digest() if invalid != "hash-mismatch" else b"x" * 32
    with migrated.connect() as c, c.transaction():
        c.execute("SET LOCAL ROLE ai_res_owner")
        c.execute("SELECT set_config('app.migration_mode','on',true)")
        c.execute("INSERT INTO platform.model_admission_versions(profile_id,generation,profile_version,expectation,expectation_sha256) VALUES(%s,2,1,%s,%s)",
                  [expected.managed_versions.profile_id, Jsonb(data), digest])
        c.execute("UPDATE platform.model_admission_controls SET current_generation=2")
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    assert error.value.code == "ADMISSION_INVALID" and counts(migrated) == (0, 0)


@pytest.mark.parametrize("presence", [FingerprintPresence.ABSENT, FingerprintPresence.NULL])
async def test_missing_fingerprint_blocks_a_durable_result(migrated: Pg, api_engine: AsyncEngine, presence):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    result = replace(observed(expected), identity=replace(expected.identity, fingerprint=ObservedFingerprint(presence, None)))
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, result)
    assert error.value.code == "IDENTITY_MISMATCH" and counts(migrated) == (1, 2)


async def test_changed_managed_result_and_changed_terminal_replay_are_not_accepted(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    await guard(api_engine).finalize(ticket, observed(expected))
    changed = replace(observed(expected), provider_request_ref="changed-provider-reference")
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, changed)
    assert error.value.code == "RESULT_REUSE_MISMATCH" and counts(migrated) == (1, 2)
    next_ticket = await guard(api_engine).begin(ticket.profile_id, expected.managed_versions, request_ref="call-2")
    changed_versions = replace(expected.managed_versions, code_revision="f" * 40)
    with pytest.raises(AdmissionDenied) as mismatch:
        await guard(api_engine).finalize(next_ticket, replace(observed(expected, "call-2"), managed_versions=changed_versions))
    assert mismatch.value.code == "IDENTITY_MISMATCH" and counts(migrated) == (2, 4)


async def test_managed_version_or_request_mismatch_blocks_result(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    service = guard(api_engine)
    with pytest.raises(AdmissionDenied):
        await service.begin(expected.managed_versions.profile_id, replace(expected.managed_versions, config_sha256="f" * 64), request_ref="call-1")
    assert counts(migrated) == (0, 0)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with pytest.raises(AdmissionDenied):
        await service.finalize(ticket, replace(observed(expected), request_ref="other-call"))
    assert counts(migrated) == (1, 2)


async def test_profile_deprecation_is_checked_again_at_finalize(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with migrated.connect() as c:
        c.execute("UPDATE platform.model_profiles SET status='DEPRECATED',deprecated_at=clock_timestamp() WHERE id=%s", [ticket.profile_id])
    with pytest.raises(AdmissionDenied) as error:
        await guard(api_engine).finalize(ticket, observed(expected))
    assert error.value.code == "PROFILE_UNAVAILABLE" and counts(migrated) == (1, 1)


def test_runtime_default_deny_profile_context_resets_and_no_approval_privileges(migrated: Pg):
    expected = seed(migrated)
    with migrated.connect("ai_res_api") as api:
        for table in TABLES:
            assert api.execute(sql.SQL("SELECT count(*) FROM platform.{}").format(sql.Identifier(table))).fetchone() == (0,)
        with api.transaction():
            api.execute("SELECT set_config('app.model_profile_id',%s,true)", [str(expected.managed_versions.profile_id)])
            assert api.execute("SELECT count(*) FROM platform.model_admission_versions").fetchone() == (1,)
            for statement in ("UPDATE platform.model_admission_controls SET current_generation=2",
                              "UPDATE platform.model_admission_versions SET generation=2",
                              "INSERT INTO platform.model_admission_controls(profile_id,current_generation) VALUES(gen_random_uuid(),1)"):
                with pytest.raises(errors.InsufficientPrivilege), api.transaction():
                    api.execute(statement)
            for table in TABLES:
                for action in ("DELETE FROM", "TRUNCATE"):
                    with pytest.raises(errors.InsufficientPrivilege), api.transaction():
                        api.execute(f"{action} platform.{table}")
        assert api.execute("SELECT count(*) FROM platform.model_admission_versions").fetchone() == (0,)
        with api.transaction():
            api.execute("SELECT set_config('app.model_profile_id',%s,true)", [str(uuid4())])
            assert api.execute("SELECT count(*) FROM platform.model_admission_versions").fetchone() == (0,)


async def test_runtime_cannot_clear_block_rewrite_terminal_or_forge_audit_actor(migrated: Pg, api_engine: AsyncEngine):
    expected = seed(migrated)
    ticket = await guard(api_engine).begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="call-1")
    with pytest.raises(AdmissionDenied):
        await guard(api_engine).finalize(ticket, "malformed")
    with migrated.connect("ai_res_api") as api, api.transaction():
        api.execute("SELECT set_config('app.model_profile_id',%s,true)", [str(ticket.profile_id)])
        for statement in ("UPDATE platform.model_admission_controls SET blocked=false",
                          "UPDATE platform.model_admission_calls SET status='VALIDATED',observed_sha256=decode(repeat('ab',32),'hex')"):
            with pytest.raises(errors.IntegrityConstraintViolation), api.transaction():
                api.execute(statement)
        for statement in ("UPDATE platform.model_admission_calls SET request_ref='rewritten'",
                          "INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code,writer_role) "
                          "VALUES(gen_random_uuid(),%s,%s,'BEGIN','RESERVED','ai_res_owner')",
                          "INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code,occurred_at) "
                          "VALUES(gen_random_uuid(),%s,%s,'BEGIN','RESERVED',now())"):
            with pytest.raises(errors.InsufficientPrivilege), api.transaction():
                api.execute(statement, [ticket.profile_id, ticket.call_id] if "%s" in statement else None)


def test_owner_cannot_rewrite_or_remove_generation_and_audit_evidence(migrated: Pg):
    seed(migrated)
    with migrated.connect() as c, c.transaction():
        c.execute("SET LOCAL ROLE ai_res_owner")
        c.execute("SELECT set_config('app.migration_mode','on',true)")
        for statement in ("UPDATE platform.model_admission_versions SET expectation='{}'::jsonb",
                          "DELETE FROM platform.model_admission_versions", "TRUNCATE platform.model_admission_audit"):
            with pytest.raises(errors.IntegrityConstraintViolation), c.transaction():
                c.execute(statement)
