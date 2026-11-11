# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S06 repositories under the real api role: version pointer CAS, unknown type, human-only confirmation/approval, upload verification and idempotent finalization."""
import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.requirements.repository import NewRequirementVersion, RequirementRepository, StateConflict
from ai_res.modules.sources.repository import NewUpload, SourceRepository, UploadRow
from ai_res.platform.clock import utc_now
from ai_res.platform.concurrency import AggregateVersionConflict
from ai_res.platform.config import load_settings
from ai_res.platform.problems import ProblemError

from .conftest import Pg

pytestmark = pytest.mark.postgres
ORG, PRJ, USER = uuid4(), uuid4(), uuid4()
SHA = b"\x33" * 32


@pytest.fixture
def world(migrated: Pg) -> Pg:
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [ORG])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [PRJ, ORG])
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'u@example.test','u@example.test','u')", [USER, ORG])
    return migrated


@pytest.fixture
async def api(world: Pg, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    pw = tmp_path / "pw"
    pw.write_text(world.passwords["ai_res_api"])
    engine = create_runtime_engine(load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": world.host, "AI_RES_DB_PORT": str(world.port), "AI_RES_DB_USER": "ai_res_api",
                                                  "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "test-s06", "AI_RES_DB_POOL_SIZE": "4"}))
    yield engine
    await engine.dispose()


def uow(engine: AsyncEngine) -> UnitOfWork:
    return UnitOfWork(create_session_factory(engine))


def version(text_: str = "The system shall X", declared: str = "FR", **kw) -> NewRequirementVersion:
    return NewRequirementVersion(statement=text_, author_type="MANAGER", declared_type=declared, **kw)


async def test_requirement_numbering_versions_pointer_and_stale_cas(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = RequirementRepository(u.session)
        r1 = await repo.create(ORG, PRJ, version())
        r2 = await repo.create(ORG, PRJ, version("second", "NFR"))
        assert (r1.display_number, r2.display_number) == (1, 2)  # counter, not MAX()+1
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = RequirementRepository(u.session)
        v2, n = await repo.add_version(ORG, PRJ, r1.id, r1.row_version, version("changed", change_reason="clarified"))
        assert n == 2
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(AggregateVersionConflict):  # stale expected row_version
            await RequirementRepository(u.session).add_version(ORG, PRJ, r1.id, r1.row_version, version("lost update", change_reason="x"))
    with world.connect() as c:
        assert c.execute("SELECT r.current_version_id = %s, r.last_version_number, (SELECT statement FROM requirements.requirement_versions WHERE id = %s) FROM requirements.requirements r WHERE r.id = %s",
                         [v2, r1.current_version_id, r1.id]).fetchone() == (True, 2, "The system shall X")  # version 1 content is untouched


async def test_unknown_type_is_kept_as_unknown_with_declared_text(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = RequirementRepository(u.session)
        assert await repo.resolve_type("fr") == ("UNKNOWN", "fr")  # case differs: not silently "FR"
        assert await repo.resolve_type("FR") == ("FR", None)
        row = await repo.create(ORG, PRJ, version(declared="SAFETY"))
    with world.connect() as c:
        assert c.execute("SELECT requirement_type, declared_type_text FROM requirements.requirement_versions WHERE id=%s", [row.current_version_id]).fetchone() == ("UNKNOWN", "SAFETY")


async def status_of(world: Pg, vid) -> tuple:
    with world.connect() as c:
        return c.execute("SELECT status, confirmed_by IS NOT NULL, confirmed_at IS NOT NULL FROM requirements.requirement_versions WHERE id=%s", [vid]).fetchone()


async def test_confirmation_and_approval_report_what_really_happened(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        row = await RequirementRepository(u.session).create(ORG, PRJ, version())
    vid = row.current_version_id
    async with uow(api) as u:  # approving a CANDIDATE is a state conflict, never a silent success
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(StateConflict):
            await RequirementRepository(u.session).mark_approved(vid)
    async with uow(api) as u:  # an unknown (or invisible) version is "not found"
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(ProblemError):
            await RequirementRepository(u.session).confirm(uuid4(), USER)
    async with uow(api) as u:  # CANDIDATE -> APPROVED written directly: refused (no approval fact; the transition guard would refuse it too)
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(IntegrityError, match="cannot become APPROVED without an APPROVED approval"):
            await u.session.execute(text("UPDATE requirements.requirement_versions SET status = 'APPROVED' WHERE id = :id"), {"id": vid})
    assert await status_of(world, vid) == ("CANDIDATE", False, False)
    async with uow(api) as u:  # CONFIRMED but with no approval fact: the facts guard refuses APPROVED
        await u.with_tenant(ORG, PRJ)
        repo = RequirementRepository(u.session)
        await repo.confirm(vid, USER)
        with pytest.raises(IntegrityError, match="cannot become APPROVED without an APPROVED approval"):
            await repo.mark_approved(vid)
    assert await status_of(world, vid) == ("CANDIDATE", False, False)  # the failed transaction left nothing behind
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = RequirementRepository(u.session)
        with pytest.raises(ValueError, match="decision"):
            await repo.record_approval(ORG, PRJ, vid, USER, "MAYBE")
        await repo.confirm(vid, USER)
        await repo.record_approval(ORG, PRJ, vid, USER, "APPROVED")
        await repo.mark_approved(vid)
    assert await status_of(world, vid) == ("APPROVED", True, True)
    async with uow(api) as u:  # confirming again is a conflict, not a repeated success
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(StateConflict):
            await RequirementRepository(u.session).confirm(vid, USER)


async def test_parallel_creates_get_distinct_consecutive_numbers(api: AsyncEngine, world: Pg):
    async def one() -> int:
        async with uow(api) as u:
            await u.with_tenant(ORG, PRJ)
            return (await RequirementRepository(u.session).create(ORG, PRJ, version())).display_number

    numbers = await asyncio.gather(*(one() for _ in range(4)))
    assert sorted(numbers) == [1, 2, 3, 4]  # the counter row lock serialises allocation


async def verified_upload(repo: SourceRepository, src, sha: bytes = SHA):
    up = await repo.register_upload(NewUpload(ORG, PRJ, src, f"o/{uuid4()}", "text/markdown", 5, sha, utc_now() + timedelta(minutes=15)))
    return await repo.verify_upload(await repo.mark_uploaded(up), 5, sha)


async def test_upload_verification_outcomes_and_their_codes(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = SourceRepository(u.session)
        src = await repo.create_source(ORG, PRJ, "FILE", "spec.md")
        ups = {}
        for name, size, sha in (("checksum", 5, b"\x00" * 32), ("size", 6, SHA), ("ok", 5, SHA)):
            up = await repo.register_upload(NewUpload(ORG, PRJ, src, f"o/{uuid4()}", "text/markdown", 5, SHA, utc_now() + timedelta(minutes=15)))
            ups[name] = await repo.verify_upload(await repo.mark_uploaded(up), size, sha)
        late = await repo.register_upload(NewUpload(ORG, PRJ, src, f"o/{uuid4()}", "text/markdown", 5, SHA, utc_now() - timedelta(seconds=1)))
        ups["late"] = await repo.verify_upload(await repo.mark_uploaded(late), 5, SHA)
    assert {k: v.status for k, v in ups.items()} == {"checksum": "REJECTED", "size": "REJECTED", "ok": "VERIFIED", "late": "EXPIRED"}
    with world.connect() as c:
        codes = dict(c.execute("SELECT id::text, rejection_code FROM sources.uploads WHERE rejection_code IS NOT NULL").fetchall())
    assert sorted(codes.values()) == ["CHECKSUM_MISMATCH", "SIZE_MISMATCH"]


async def test_finalization_is_idempotent_deduplicated_and_race_safe(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = SourceRepository(u.session)
        src = await repo.create_source(ORG, PRJ, "FILE", "spec.md")
        first = await verified_upload(repo, src)
        other = await verified_upload(repo, src)  # a second upload with identical content
    async def finalize(upload):
        async with uow(api) as u:
            await u.with_tenant(ORG, PRJ)
            return await SourceRepository(u.session).finalize_version(ORG, PRJ, upload, received_at=utc_now(), provenance={"connector": "file-upload"})

    results = await asyncio.gather(finalize(first), finalize(first), finalize(other))  # concurrent finalizers: no IntegrityError, one version
    assert sum(r.created for r in results) == 1 and len({r.id for r in results}) == 1
    with world.connect() as c:
        assert c.execute("SELECT count(*), max(version_number) FROM sources.source_versions WHERE source_id=%s", [src]).fetchone() == (1, 1)
        assert c.execute("SELECT current_version_id = %s FROM sources.sources WHERE id=%s", [results[0].id, src]).fetchone() == (True,)
    again = await finalize(first)
    assert (again.created, again.is_current) == (False, True)
    async with uow(api) as u:  # unknown/invisible source -> not found, not a bare NoResultFound
        await u.with_tenant(ORG, PRJ)
        with pytest.raises(ProblemError):
            await SourceRepository(u.session).finalize_version(ORG, PRJ, UploadRow(uuid4(), uuid4(), "VERIFIED", 1), received_at=utc_now(), provenance={})


async def test_sources_refuse_out_of_order_use_with_typed_conflicts_and_ignore_a_forged_dto(api: AsyncEngine, world: Pg):
    async with uow(api) as u:
        await u.with_tenant(ORG, PRJ)
        repo = SourceRepository(u.session)
        src = await repo.create_source(ORG, PRJ, "FILE", "a")
        other = await repo.create_source(ORG, PRJ, "FILE", "b")
        pending = await repo.register_upload(NewUpload(ORG, PRJ, src, f"o/{uuid4()}", "t/p", 5, SHA, utc_now() + timedelta(minutes=5)))
        with pytest.raises(StateConflict):
            await repo.verify_upload(pending, 5, SHA)  # skipping UPLOADED
        with pytest.raises(StateConflict):
            await repo.finalize_version(ORG, PRJ, pending, received_at=utc_now(), provenance={})  # not VERIFIED
        ok = await verified_upload(repo, src)
        forged = UploadRow(ok.id, other, ok.status, ok.row_version)  # DTO names the OTHER source
        result = await repo.finalize_version(ORG, PRJ, forged, received_at=utc_now(), provenance={})
        assert result.created
    with world.connect() as c:
        assert c.execute("SELECT source_id FROM sources.source_versions WHERE id=%s", [result.id]).fetchone() == (src,)  # the database row decides
        assert c.execute("SELECT last_version_number FROM sources.sources WHERE id=%s", [other]).fetchone() == (0,)
