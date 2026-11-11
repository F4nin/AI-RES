"""Transaction-local tenant context + RLS default deny + pool hygiene (PERSIST-008/009/010 mechanics, DBM-008..010).

S04 ships no domain tables, so a TEST-ONLY probe table with the same policy shape as DOC-069 (NULLIF(current_setting(..., true), '')::uuid,
ENABLE + FORCE) is created by the owner role. All reads/writes below go through the real `ai_res_api` login role via the runtime engine.
"""
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.db.tenant_context import set_tenant_context
from ai_res.platform.config import load_settings

from .conftest import Pg

pytestmark = pytest.mark.postgres
ORG_A, ORG_B, PRJ_A1, PRJ_A2 = uuid4(), uuid4(), uuid4(), uuid4()
SCOPE = ("organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
         "AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid")


@pytest.fixture
def probe(migrated: Pg) -> Pg:
    with migrated.connect() as c:
        c.execute("SET ROLE ai_res_owner")
        c.execute("CREATE TABLE work.rls_probe (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                  "organization_id uuid NOT NULL, project_id uuid NOT NULL, note text)")
        c.execute("ALTER TABLE work.rls_probe ENABLE ROW LEVEL SECURITY")
        c.execute("ALTER TABLE work.rls_probe FORCE ROW LEVEL SECURITY")
        c.execute(f"CREATE POLICY p_rls_probe_tenant_scope ON work.rls_probe FOR ALL TO ai_res_api_group USING ({SCOPE}) WITH CHECK ({SCOPE})")
        c.execute("GRANT SELECT, INSERT, UPDATE ON work.rls_probe TO ai_res_api_group")
        c.execute("RESET ROLE")
        for org, prj, note in ((ORG_A, PRJ_A1, "a1"), (ORG_A, PRJ_A2, "a2"), (ORG_B, uuid4(), "b")):  # superuser bypasses RLS: seeding only
            c.execute("INSERT INTO work.rls_probe (organization_id, project_id, note) VALUES (%s, %s, %s)", [org, prj, note])
        assert c.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid='work.rls_probe'::regclass").fetchone() == (True, True)
    return migrated


@pytest.fixture
async def engine(probe: Pg, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    pw = tmp_path / "api_pw"
    pw.write_text(probe.passwords["ai_res_api"])
    settings = load_settings({
        "AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": probe.host, "AI_RES_DB_PORT": str(probe.port), "AI_RES_DB_USER": "ai_res_api",
        "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "ai-res-api-test", "AI_RES_DB_POOL_SIZE": "1",
    })
    eng = create_runtime_engine(settings)
    try:
        yield eng
    finally:
        await eng.dispose()


async def _notes(session) -> list[str]:  # type: ignore[no-untyped-def]
    return sorted((await session.execute(text("SELECT note FROM work.rls_probe"))).scalars().all())


async def test_missing_context_is_default_deny_for_reads_and_writes(engine: AsyncEngine):
    uow = UnitOfWork(create_session_factory(engine))
    async with uow:
        assert await _notes(uow.session) == []
        with pytest.raises(DBAPIError, match="row-level security"):
            await uow.session.execute(text("INSERT INTO work.rls_probe (organization_id, project_id, note) VALUES (:o, :p, 'x')"), {"o": ORG_A, "p": PRJ_A1})


async def test_context_scopes_rows_to_organization_and_project(engine: AsyncEngine):
    factory = create_session_factory(engine)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A1)
        assert await _notes(uow.session) == ["a1"]
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A2)
        assert await _notes(uow.session) == ["a2"]
    async with UnitOfWork(factory) as uow:  # PERSIST-008/011 shape: tenant B (or a forged project of A) sees nothing of A
        await uow.with_tenant(ORG_B, PRJ_A1)
        assert await _notes(uow.session) == []
        with pytest.raises(DBAPIError, match="row-level security"):  # cannot write into another tenant's scope either
            await uow.session.execute(text("INSERT INTO work.rls_probe (organization_id, project_id, note) VALUES (:o, :p, 'x')"), {"o": ORG_A, "p": PRJ_A1})


async def test_organization_only_context_matches_no_project_scoped_rows(engine: AsyncEngine):
    async with UnitOfWork(create_session_factory(engine)) as uow:
        await uow.with_tenant(ORG_A)
        assert await _notes(uow.session) == []


async def test_empty_string_context_returns_zero_rows_not_an_error(engine: AsyncEngine):
    async with UnitOfWork(create_session_factory(engine)) as uow:
        await uow.session.execute(text("SELECT set_config('app.organization_id', '', true), set_config('app.project_id', '', true)"))
        assert await _notes(uow.session) == []


async def test_context_does_not_leak_across_commit_rollback_and_pool_reuse(engine: AsyncEngine):
    """Every transaction below (including the first, committed one) must run on the SAME physical connection, otherwise nothing is proven."""
    factory = create_session_factory(engine)
    probe_sql = text("SELECT current_setting('app.organization_id', true), current_setting('app.project_id', true), pg_backend_pid()")
    pids = set()
    async with UnitOfWork(factory) as uow:  # committed transaction
        await uow.with_tenant(ORG_A, PRJ_A1)
        first = (await uow.session.execute(probe_sql)).one()
        assert first[0] == str(ORG_A)
        pids.add(first[2])
    async with UnitOfWork(factory) as uow:
        org, prj, pid = (await uow.session.execute(probe_sql)).one()
        pids.add(pid)
        assert org in (None, "") and prj in (None, "")
        assert await _notes(uow.session) == []
    with pytest.raises(RuntimeError, match="boom"):  # rolled-back transaction
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(ORG_B, PRJ_A1)
            raise RuntimeError("boom")
    async with UnitOfWork(factory) as uow:
        org, prj, pid = (await uow.session.execute(probe_sql)).one()
        pids.add(pid)
        assert org in (None, "") and prj in (None, "")
    assert len(pids) == 1, "test must reuse one pooled connection to prove anything (PERSIST-010)"


async def test_unit_of_work_commits_and_rolls_back_atomically(engine: AsyncEngine, probe: Pg):
    factory = create_session_factory(engine)
    ins = text("INSERT INTO work.rls_probe (organization_id, project_id, note) VALUES (:o, :p, :n)")
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A1)
        await uow.session.execute(ins, {"o": ORG_A, "p": PRJ_A1, "n": "committed"})
    with pytest.raises(RuntimeError):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(ORG_A, PRJ_A1)
            await uow.session.execute(ins, {"o": ORG_A, "p": PRJ_A1, "n": "rolled-back"})
            raise RuntimeError("fail after write")
    with probe.connect() as c:
        notes = {r[0] for r in c.execute("SELECT note FROM work.rls_probe")}
    assert "committed" in notes and "rolled-back" not in notes


async def test_tenant_context_can_be_set_only_once_per_transaction(engine: AsyncEngine):
    factory = create_session_factory(engine)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A1)
        assert await _notes(uow.session) == ["a1"]
        with pytest.raises(RuntimeError, match="already set"):
            await uow.with_tenant(ORG_B, PRJ_A1)
        assert await _notes(uow.session) == ["a1"]  # the original scope is still in force
    async with UnitOfWork(factory) as uow:  # a new transaction starts clean and may set its own
        await uow.with_tenant(ORG_A, PRJ_A2)
        assert await _notes(uow.session) == ["a2"]


async def test_failed_begin_does_not_leak_the_session():
    class BoomFactory:
        closed = False

        def __call__(self):  # type: ignore[no-untyped-def]
            outer = self

            class S:
                async def begin(self):  # type: ignore[no-untyped-def]
                    raise ConnectionError("db down")

                async def close(self) -> None:
                    outer.closed = True

            return S()

    factory = BoomFactory()
    with pytest.raises(ConnectionError):
        async with UnitOfWork(factory):  # type: ignore[arg-type]
            pass
    assert factory.closed


async def test_unit_of_work_has_no_session_outside_the_block(engine: AsyncEngine):
    uow = UnitOfWork(create_session_factory(engine))
    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.session
    async with uow:
        pass
    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.session


async def test_engine_applies_timeouts_application_name_and_fixed_search_path(engine: AsyncEngine):
    async with engine.connect() as conn:
        q = text("SELECT current_setting('application_name'), current_setting('search_path'), current_setting('statement_timeout')")
        row = (await conn.execute(q)).one()
        assert row == ("ai-res-api-test", "pg_catalog", "15s")
        assert (await conn.execute(text("SELECT current_user, session_user"))).one() == ("ai_res_api", "ai_res_api")
    assert "password" not in repr(engine.url) and "***" in str(engine.url)


async def test_malicious_looking_values_are_data_not_sql(engine: AsyncEngine):
    """set_config goes through bind parameters; the helper accepts only UUID objects, and the SQL layer treats any text as a plain value."""
    async with engine.connect() as conn:
        await conn.begin()
        evil = "x'); DROP TABLE work.rls_probe; --"
        await conn.execute(text("SELECT set_config('app.organization_id', :v, true)"), {"v": evil})
        assert (await conn.execute(text("SELECT current_setting('app.organization_id', true)"))).scalar_one() == evil
        await conn.rollback()
    with pytest.raises(TypeError):
        async with engine.connect() as conn:
            await set_tenant_context(conn, evil, None)  # type: ignore[arg-type]
