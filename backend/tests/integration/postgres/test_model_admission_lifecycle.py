"""Real PG16 lifecycle races; all profile/evidence/approval rows are synthetic.

No provider calls or production human authorization are exercised. Test pauses
are inside DB-only methods, never external I/O in an application transaction.
"""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from psycopg import errors, sql
from sqlalchemy import text

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionUnavailable, ModelAdmissionGuard, evidence_hash
from ai_res.platform.config import load_settings

from .conftest import alembic_config, run_audit
from .test_model_admission import api_engine as api_engine  # explicit fixture re-export
from .test_model_admission import counts, guard, observed, seed
from .test_model_registry import USER, add_profile, approve

pytestmark = pytest.mark.postgres
LOCK_SQL = "SELECT pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('ai_res.model_profile_lifecycle:' || %s::uuid::text, 0))"
REVOKE_SQL = "UPDATE platform.model_profiles SET status='DEPRECATED',deprecated_at=clock_timestamp() WHERE id=%s"


async def wait_blocked(pg, pid, operation):
    """Observe a real PG lock waiter; task timing alone cannot prove exclusion."""
    async with asyncio.timeout(5):
        while not operation.done():
            with pg.connect() as observer:
                blockers = observer.execute("SELECT pg_blocking_pids(%s)", [pid]).fetchone()[0]
            if blockers:
                return
            await asyncio.sleep(0.01)
    if operation.done():
        # Propagate unexpected DB errors instead of misclassifying them as proof.
        await operation
    pytest.fail("lifecycle operation completed without waiting for admission fence")


@pytest.mark.parametrize("phase", ["begin", "finalize"])
async def test_guard_first_lifecycle_update_waits_for_admission_commit(migrated, api_engine, phase):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    read, release = asyncio.Event(), asyncio.Event()

    class PausedGuard(ModelAdmissionGuard):
        async def _expectation(self, session, profile_id, generation):
            value = await super()._expectation(session, profile_id, generation)
            read.set()
            await release.wait()
            return value

    paused = PausedGuard(create_session_factory(api_engine))
    action = asyncio.create_task(paused.finalize(ticket, observed(expected, "first")) if ticket else
                                 paused.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first"))
    owner_action = None
    with migrated.connect("ai_res_migrator") as owner:
        owner.execute("SET ROLE ai_res_owner")
        owner.execute("SET statement_timeout='10s'")
        try:
            await asyncio.wait_for(read.wait(), 5)
            owner_action = asyncio.create_task(asyncio.to_thread(owner.execute, REVOKE_SQL, [expected.managed_versions.profile_id]))
            await wait_blocked(migrated, owner.info.backend_pid, owner_action)
            release.set()
            result = await asyncio.wait_for(action, 5)
            await asyncio.wait_for(owner_action, 5)
        finally:
            release.set()
            await asyncio.gather(action, *([owner_action] if owner_action else []), return_exceptions=True)
    with pytest.raises(AdmissionDenied) as refused:
        await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="after-revoke")
    assert refused.value.code == "PROFILE_UNAVAILABLE"
    if ticket:
        assert result is None and counts(migrated) == (1, 2)
    else:
        assert result.profile_id == expected.managed_versions.profile_id and counts(migrated) == (1, 1)
        with pytest.raises(AdmissionDenied):
            await service.finalize(result, observed(expected, "first"))


@pytest.mark.parametrize("phase", ["begin", "finalize"])
@pytest.mark.parametrize("change", ["status", "deprecated_at"])
async def test_owner_first_commit_is_seen_after_lock_wait(migrated, api_engine, phase, change):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    entered, pid = asyncio.Event(), []

    class VisibleGuard(ModelAdmissionGuard):
        async def _control(self, session, profile_id):
            pid.append((await session.execute(text("SELECT pg_backend_pid()"))).scalar_one())
            entered.set()
            return await super()._control(session, profile_id)

    guarded = VisibleGuard(create_session_factory(api_engine))
    with migrated.connect("ai_res_migrator", autocommit=False) as owner:
        owner.execute("SET LOCAL ROLE ai_res_owner")
        query = REVOKE_SQL if change == "status" else "UPDATE platform.model_profiles SET deprecated_at=clock_timestamp() WHERE id=%s"
        owner.execute(query, [expected.managed_versions.profile_id])
        action = asyncio.create_task(guarded.finalize(ticket, observed(expected, "first")) if ticket else
                                     guarded.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first"))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await wait_blocked(migrated, pid[0], action)
        finally:
            owner.commit()
            results = await asyncio.gather(action, return_exceptions=True)
    assert isinstance(results[0], AdmissionDenied) and results[0].code == "PROFILE_UNAVAILABLE"
    assert counts(migrated) == ((1, 1) if ticket else (0, 0))
    if ticket:
        with migrated.connect() as c:
            assert c.execute("SELECT status FROM platform.model_admission_calls").fetchone() == ("IN_FLIGHT",)


@pytest.mark.parametrize("phase", ["begin", "finalize"])
async def test_owner_rollback_releases_fence_and_preserves_usable_profile(migrated, api_engine, phase):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    entered, pid = asyncio.Event(), []

    class VisibleGuard(ModelAdmissionGuard):
        async def _control(self, session, profile_id):
            pid.append((await session.execute(text("SELECT pg_backend_pid()"))).scalar_one())
            entered.set()
            return await super()._control(session, profile_id)

    guarded = VisibleGuard(create_session_factory(api_engine))
    with migrated.connect("ai_res_migrator", autocommit=False) as owner:
        owner.execute("SET LOCAL ROLE ai_res_owner")
        owner.execute(REVOKE_SQL, [expected.managed_versions.profile_id])
        action = asyncio.create_task(guarded.finalize(ticket, observed(expected, "first")) if ticket else
                                     guarded.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first"))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await wait_blocked(migrated, pid[0], action)
        finally:
            owner.rollback()
            results = await asyncio.gather(action, return_exceptions=True)
    assert not isinstance(results[0], BaseException)
    if not ticket:
        await service.finalize(results[0], observed(expected, "first"))
    assert counts(migrated) == (1, 2)


@pytest.mark.parametrize("phase", ["begin", "finalize"])
@pytest.mark.parametrize("state", ["missing", "disabled", "replica", "wrong_function", "partial_columns", "conditional"])
async def test_unavailable_or_incomplete_trigger_never_accepts_admission(migrated, api_engine, phase, state):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    with migrated.connect() as c:
        if state in ("missing", "wrong_function", "partial_columns", "conditional"):
            c.execute("DROP TRIGGER trg_model_profiles_lifecycle_fence ON platform.model_profiles")
        if state == "disabled":
            c.execute("ALTER TABLE platform.model_profiles DISABLE TRIGGER trg_model_profiles_lifecycle_fence")
        elif state == "replica":
            c.execute("ALTER TABLE platform.model_profiles ENABLE REPLICA TRIGGER trg_model_profiles_lifecycle_fence")
        elif state == "wrong_function":
            c.execute("CREATE FUNCTION platform.fixture_noop_fence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
            c.execute("CREATE TRIGGER trg_model_profiles_lifecycle_fence BEFORE UPDATE ON platform.model_profiles "
                      "FOR EACH ROW EXECUTE FUNCTION platform.fixture_noop_fence()")
        elif state == "partial_columns":
            c.execute("CREATE TRIGGER trg_model_profiles_lifecycle_fence BEFORE UPDATE OF status ON platform.model_profiles "
                      "FOR EACH ROW EXECUTE FUNCTION platform.fence_model_profile_lifecycle()")
        elif state == "conditional":
            c.execute("CREATE TRIGGER trg_model_profiles_lifecycle_fence BEFORE UPDATE ON platform.model_profiles "
                      "FOR EACH ROW WHEN (false) EXECUTE FUNCTION platform.fence_model_profile_lifecycle()")
    with pytest.raises(AdmissionDenied) as refused:
        if ticket:
            await service.finalize(ticket, observed(expected, "first"))
        else:
            await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
    assert refused.value.code == "LIFECYCLE_FENCE_UNAVAILABLE"
    assert counts(migrated) == ((1, 1) if ticket else (0, 0))


@pytest.mark.parametrize("phase", ["begin", "finalize"])
@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_snapshot_isolation_refused_without_receipt_or_final_result(migrated, api_engine, phase, isolation):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    restricted = guard(api_engine.execution_options(isolation_level=isolation))
    with pytest.raises(AdmissionDenied) as refused:
        if ticket:
            await restricted.finalize(ticket, observed(expected, "first"))
        else:
            await restricted.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
    assert refused.value.code == "UNSUPPORTED_ISOLATION"
    assert counts(migrated) == ((1, 1) if ticket else (0, 0))


@pytest.mark.parametrize("phase", ["begin", "finalize"])
async def test_fence_timeout_is_safe_and_releases_transaction(migrated, api_engine, phase):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None

    class FastTimeoutGuard(ModelAdmissionGuard):
        async def _control(self, session, profile_id):
            await session.execute(text("SELECT set_config('lock_timeout','50ms',true)"))
            return await super()._control(session, profile_id)

    with migrated.connect("ai_res_migrator", autocommit=False) as owner:
        owner.execute("SET LOCAL ROLE ai_res_owner")
        owner.execute(REVOKE_SQL, [expected.managed_versions.profile_id])
        with pytest.raises(AdmissionUnavailable) as refused:
            timed = FastTimeoutGuard(create_session_factory(api_engine))
            if ticket:
                await timed.finalize(ticket, observed(expected, "first"))
            else:
                await timed.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
        assert str(refused.value) == "Model admission dependency unavailable."
        owner.rollback()
    assert counts(migrated) == ((1, 1) if ticket else (0, 0))
    if not ticket:
        ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
    await service.finalize(ticket, observed(expected, "first"))
    assert counts(migrated) == (1, 2)


async def test_unrelated_profile_does_not_wait_on_first_profile_lifecycle(migrated, api_engine):
    first, second = seed(migrated, key="first"), seed(migrated, key="second")
    with migrated.connect("ai_res_migrator", autocommit=False) as owner:
        owner.execute("SET LOCAL ROLE ai_res_owner")
        owner.execute(REVOKE_SQL, [first.managed_versions.profile_id])
        try:
            service = guard(api_engine)
            ticket = await asyncio.wait_for(service.begin(second.managed_versions.profile_id, second.managed_versions, request_ref="second"), 2)
            await asyncio.wait_for(service.finalize(ticket, observed(second, "second")), 2)
        finally:
            owner.rollback()
    assert counts(migrated) == (1, 2)


def test_api_profile_rights_and_trigger_function_are_not_elevated(migrated):
    expected = seed(migrated)
    with migrated.connect("ai_res_api") as api:
        assert api.execute("SELECT has_table_privilege(current_user,'platform.model_profiles','SELECT'),"
                           "has_any_column_privilege(current_user,'platform.model_profiles','UPDATE'),"
                           "has_table_privilege(current_user,'platform.model_profiles','INSERT'),"
                           "has_function_privilege(current_user,'platform.fence_model_profile_lifecycle()','EXECUTE')"
                           ).fetchone() == (True, False, False, False)
        with pytest.raises(errors.InsufficientPrivilege):
            api.execute(REVOKE_SQL, [expected.managed_versions.profile_id])
        with pytest.raises(errors.InsufficientPrivilege):
            api.execute("SELECT id FROM platform.model_profiles FOR SHARE")
        with pytest.raises(errors.InsufficientPrivilege):
            api.execute("ALTER TABLE platform.model_profiles DISABLE TRIGGER trg_model_profiles_lifecycle_fence")
    with migrated.connect() as c:
        assert c.execute("SELECT prosecdef,proconfig FROM pg_proc WHERE oid='platform.fence_model_profile_lifecycle()'::regprocedure").fetchone() == (
            False, ["search_path=pg_catalog"])


async def test_audit_failure_rolls_back_receipt_and_releases_fence(migrated, api_engine):
    expected = seed(migrated)
    with migrated.connect() as c:
        c.execute("CREATE FUNCTION platform.fixture_fail_begin_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                  "BEGIN RAISE EXCEPTION 'synthetic audit outage'; END $$")
        c.execute("CREATE TRIGGER fixture_fail_begin BEFORE INSERT ON platform.model_admission_audit "
                  "FOR EACH ROW EXECUTE FUNCTION platform.fixture_fail_begin_audit()")
    service = guard(api_engine)
    with pytest.raises(AdmissionUnavailable):
        await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
    assert counts(migrated) == (0, 0)
    with migrated.connect() as c, c.transaction():
        assert c.execute(LOCK_SQL.replace('pg_advisory_xact_lock', 'pg_try_advisory_xact_lock'), [expected.managed_versions.profile_id]).fetchone() == (True,)
        c.execute("DROP TRIGGER fixture_fail_begin ON platform.model_admission_audit")
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
    await service.finalize(ticket, observed(expected, "first"))
    assert counts(migrated) == (1, 2)


@pytest.mark.parametrize("change", ["status", "approved_at", "approved_by", "deprecated_at"])
async def test_every_observed_lifecycle_field_uses_fence(migrated, change):
    # CANDIDATE rows permit setting individual approval metadata; these remain
    # synthetic, are never routed, and approval semantics are not being changed.
    expected = seed(migrated, approved=False)
    with migrated.connect() as setup:
        pinned = add_profile(setup, key="pinned")
        approve(setup, pinned)  # creates synthetic FK user
    values = {"status": "DEPRECATED", "approved_at": datetime.now(UTC), "approved_by": USER,
              "deprecated_at": datetime.now(UTC) + timedelta(days=1)}
    with migrated.connect(autocommit=False) as lock, migrated.connect("ai_res_migrator") as owner:
        lock.execute(LOCK_SQL, [expected.managed_versions.profile_id])
        owner.execute("SET ROLE ai_res_owner")
        owner.execute("SET statement_timeout='10s'")
        # A valid status transition needs all approval fields in the same UPDATE.
        if change == "status":
            query, args = "UPDATE platform.model_profiles SET status=%s,approved_at=clock_timestamp(),approved_by=%s WHERE id=%s", [
                values[change], USER, expected.managed_versions.profile_id]
        else:
            query, args = sql.SQL("UPDATE platform.model_profiles SET {}=%s WHERE id=%s").format(sql.Identifier(change)), [
                values[change], expected.managed_versions.profile_id]
        action = asyncio.create_task(asyncio.to_thread(owner.execute, query, args))
        try:
            await wait_blocked(migrated, owner.info.backend_pid, action)
        finally:
            lock.rollback()
            await asyncio.wait_for(action, 5)


@pytest.mark.parametrize("phase", ["begin", "finalize"])
async def test_replica_session_mode_refuses_admission(migrated, api_engine, phase):
    expected = seed(migrated)
    service = guard(api_engine)
    ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first") if phase == "finalize" else None
    with migrated.connect() as c:
        c.execute("ALTER ROLE ai_res_api SET session_replication_role=replica")
    try:
        await api_engine.dispose()
        with pytest.raises(AdmissionDenied) as refused:
            if ticket:
                await service.finalize(ticket, observed(expected, "first"))
            else:
                await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
        assert refused.value.code == "LIFECYCLE_FENCE_UNAVAILABLE"
        assert counts(migrated) == ((1, 1) if ticket else (0, 0))
    finally:
        with migrated.connect() as c:
            c.execute("ALTER ROLE ai_res_api RESET session_replication_role")
        await api_engine.dispose()


async def test_previous_upgrade_preserves_all_evidence_and_old_schema_fails_closed(empty_db, upgrade, tmp_path):
    scripts = ScriptDirectory.from_config(alembic_config())
    revision = next(r for r in scripts.walk_revisions() if r.path.endswith("0025_model_admission_lifecycle_fence.py"))
    upgrade(revision.down_revision)
    expected = seed(empty_db)
    # Populate historical receipt/audit using the original0024 narrow grants.
    # This fixture is not an approval/dispatch path and performs no provider I/O.
    with empty_db.connect("ai_res_api") as c, c.transaction():
        profile_id, call_id = expected.managed_versions.profile_id, uuid4()
        c.execute("SELECT set_config('app.model_profile_id',%s,true)", [str(profile_id)])
        c.execute("UPDATE platform.model_admission_controls SET call_sequence=1 WHERE profile_id=%s", [profile_id])
        c.execute("INSERT INTO platform.model_admission_calls(id,profile_id,generation,call_sequence,request_ref,expected_sha256) "
                  "VALUES(%s,%s,1,1,'history',%s)", [call_id, profile_id, evidence_hash(expected)])
        c.execute("INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code) VALUES(%s,%s,%s,'BEGIN','RESERVED')",
                  [uuid4(), profile_id, call_id])
        c.execute("UPDATE platform.model_admission_calls SET status='VALIDATED',observed_sha256=%s,finalized_at=clock_timestamp() WHERE id=%s",
                  [evidence_hash(observed(expected, "history")), call_id])
        c.execute("INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code) VALUES(%s,%s,%s,'VALIDATED','MATCH')",
                  [uuid4(), profile_id, call_id])
    tables = ("model_profiles", "model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit")

    def data_snapshot():
        with empty_db.connect() as c:
            return {table: c.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t ORDER BY to_jsonb(t)::text").format(
                sql.Identifier("platform", table))).fetchall() for table in tables}

    before = data_snapshot()
    pw = tmp_path / "api_pw"
    pw.write_text(empty_db.passwords["ai_res_api"])
    settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": empty_db.host, "AI_RES_DB_PORT": str(empty_db.port),
                              "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable"})
    engine = create_runtime_engine(settings)
    try:
        service = guard(engine)
        with pytest.raises(AdmissionDenied) as refused:
            await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
        assert refused.value.code == "LIFECYCLE_FENCE_UNAVAILABLE"
        assert data_snapshot() == before
        upgrade(revision.revision)
        assert data_snapshot() == before
        with empty_db.connect() as c:
            assert run_audit(c, "grants_audit.sql") == [] and run_audit(c, "rls_coverage.sql") == []
        ticket = await service.begin(expected.managed_versions.profile_id, expected.managed_versions, request_ref="first")
        await service.finalize(ticket, observed(expected, "first"))
        assert counts(empty_db) == (2, 4)
    finally:
        await engine.dispose()
