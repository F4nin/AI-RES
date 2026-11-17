# ruff: noqa: E501 -- test fixture SQL and call arguments kept together
"""S19 behavioral acceptance under the real API role, RLS and Policy Engine."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from ai_res.application.context import context_resolvers
from ai_res.db.session import UnitOfWork
from ai_res.modules.context.service import ContextApplicationService
from ai_res.modules.context.types import ContextItemKind, ContextRef
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.platform.problems import ErrorCode, ProblemError

from .test_read_api import World


@pytest.fixture
def cw(iam_world, tmp_path):
    return World(iam_world, tmp_path)


async def client(cw):
    issued = await cw.services.sessions.create(cw.iam.org_a, cw.viewer)
    auth = await cw.services.sessions.authenticate(issued.token)
    assert auth.session is not None
    service = ContextApplicationService(cw.services.factory, cw.services.enforcer,
                                       IdempotencyService(IdempotencyKeyRing("k1", {"k1": bytes(range(32))}), timedelta(hours=1)), context_resolvers)
    return service, auth.session


async def test_build_hash_replay_and_exact_immutable_versions(cw):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),)
    a = await service.build(actor, cw.ids["p1"], refs, key="context-build-0001")
    b = await service.build(actor, cw.ids["p1"], refs, key="context-build-0001")
    assert a == b
    assert (await service.retrieve(actor, cw.ids["p1"], a.version_id)) == a
    assert len(a.content_hash) == 64
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 1
    assert cw.sql_one("SELECT count(*) FROM audit.audit_events WHERE action='CONTEXT_PACKAGE_BUILT'") == 1
    # A new requirement version never modifies an already assembled package.
    async with UnitOfWork(cw.services.factory) as uow:
        await uow.with_tenant(cw.iam.org_a, cw.ids["p1"])
        from ai_res.modules.requirements.repository import NewRequirementVersion, RequirementRepository
        rv = NewRequirementVersion("Changed", "USER", "FR", change_reason="new evidence", author_id=cw.viewer)
        _, _ = await RequirementRepository(uow.session).add_version(cw.iam.org_a, cw.ids["p1"], cw.ids["req1"], cw.sql_one("SELECT row_version FROM requirements.requirements WHERE id=%s", cw.ids["req1"]), rv)
    assert await service.retrieve(actor, cw.ids["p1"], a.version_id) == a
    c = await service.build(actor, cw.ids["p1"], refs, key="context-build-0002", package_id=a.package_id, expected_version=1)
    assert c.version_number == 2 and c.content_hash == a.content_hash and c.version_id != a.version_id


@pytest.mark.parametrize("refkey", ["reqv2", "reqvb", None])
async def test_inaccessible_and_missing_ref_have_same_error_and_no_partial_package(cw, refkey):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),
            ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids[refkey] if refkey else uuid4()))
    with pytest.raises(ProblemError) as caught:
        await service.build(actor, cw.ids["p1"], refs, key="context-denied-01")
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert cw.sql_one("SELECT count(*) FROM context.context_packages") == 0
    assert cw.sql_one("SELECT count(*) FROM audit.audit_events WHERE action='CONTEXT_PACKAGE_BUILD_FAILED'") == 1


async def test_replay_and_retrieve_recheck_revoked_project_access(cw):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),)
    a = await service.build(actor, cw.ids["p1"], refs, key="context-revoke-01")
    cw.sql("UPDATE project.project_memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", cw.viewer)
    for operation in (service.retrieve(actor, cw.ids["p1"], a.version_id),
                      service.build(actor, cw.ids["p1"], refs, key="context-revoke-01")):
        with pytest.raises(ProblemError) as caught:
            await operation
        assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND


async def test_stale_write_and_key_reuse_do_not_mutate_package(cw):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),)
    a = await service.build(actor, cw.ids["p1"], refs, key="context-stale-001")
    with pytest.raises(ProblemError) as caught:
        await service.build(actor, cw.ids["p1"], refs, key="context-stale-001", package_id=a.package_id, expected_version=1)
    assert caught.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED
    with pytest.raises(ProblemError) as caught:
        await service.build(actor, cw.ids["p1"], refs, key="context-stale-002", package_id=a.package_id, expected_version=2)
    assert caught.value.code == ErrorCode.VERSION_CONFLICT
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 1


async def test_policy_outage_fails_closed(cw):
    service, actor = await client(cw)
    class Unavailable:
        async def decide(self, request):
            raise RuntimeError("unavailable")
    from ai_res.policy.enforcer import PolicyEnforcer
    service = ContextApplicationService(cw.services.factory, PolicyEnforcer(Unavailable(), cw.services.factory, None, timeout_seconds=1), service.idempotency, context_resolvers)
    with pytest.raises(ProblemError) as caught:
        await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-outage-01")
    assert caught.value.code == ErrorCode.POLICY_ENGINE_UNAVAILABLE
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 0


async def test_database_seal_uses_transaction_identity(cw):
    service, actor = await client(cw)
    a = await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-sealed-01")
    # Even if a caller spoofs timestamps, xmin belongs to the committed creator.
    async with UnitOfWork(cw.services.factory) as uow:
        await uow.with_tenant(cw.iam.org_a, cw.ids["p1"])
        with pytest.raises(Exception, match="sealed"):
            async with uow.session.begin_nested():
                await uow.session.execute(text(
                    "INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, "
                    "item_kind, requirement_version_id, inclusion_role) VALUES (:i,:o,:p,:v,'REQUIREMENT_VERSION',:r,'PRIMARY')"),
                    {"i": uuid4(), "o": cw.iam.org_a, "p": cw.ids["p1"], "v": a.version_id, "r": cw.ids["reqv1"]})


async def test_old_creation_timestamp_and_savepoint_still_allow_initial_items(cw):
    pkg, ver = uuid4(), uuid4()
    async with UnitOfWork(cw.services.factory) as uow:
        await uow.with_tenant(cw.iam.org_a, cw.ids["p1"])
        async with uow.session.begin_nested():
            params = {"pkg": pkg, "v": ver, "o": cw.iam.org_a, "p": cw.ids["p1"], "r": cw.ids["reqv1"]}
            await uow.session.execute(text(
                "INSERT INTO context.context_packages (id,organization_id,project_id,name,current_version_id,last_version_number) "
                "VALUES (:pkg,:o,:p,'test',:v,1)"), params)
            await uow.session.execute(text(
                "INSERT INTO context.context_package_versions (id,organization_id,project_id,context_package_id,version_number,item_count,content_digest,created_at) "
                "VALUES (:v,:o,:p,:pkg,1,1,decode(repeat('aa',32),'hex'),now()-interval '1 day')"), params)
            await uow.session.execute(text(
                "INSERT INTO context.context_package_items (id,organization_id,project_id,context_package_version_id,item_kind,requirement_version_id,inclusion_role) "
                "VALUES (gen_random_uuid(),:o,:p,:v,'REQUIREMENT_VERSION',:r,'PRIMARY')"), params)
    assert cw.sql_one("SELECT count(*) FROM context.context_package_items WHERE context_package_version_id=%s", ver) == 1


async def test_captured_session_cannot_survive_logout(cw):
    service, actor = await client(cw)
    cw.sql("UPDATE iam.sessions SET revoked_at=now(),revoked_reason='LOGOUT',row_version=row_version+1 WHERE id=%s", actor.session_id)
    with pytest.raises(ProblemError) as caught:
        await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-session1")
    assert caught.value.code == ErrorCode.AUTHENTICATION_REQUIRED
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 0


async def test_build_audit_failure_rolls_back_all_state(cw, monkeypatch):
    from ai_res.modules.audit.writer import SqlAuditWriter
    original = SqlAuditWriter.write
    async def unavailable(self, record, **kwargs):
        if record.action == "CONTEXT_PACKAGE_BUILT":
            raise RuntimeError("audit unavailable")
        return await original(self, record, **kwargs)
    monkeypatch.setattr(SqlAuditWriter, "write", unavailable)
    service, actor = await client(cw)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-audit-001")
    assert cw.sql_one("SELECT count(*) FROM context.context_packages") == 0
    assert cw.sql_one("SELECT count(*) FROM platform.idempotency_records") == 0


async def test_source_update_creates_new_manifest_without_mutating_old(cw):
    from ai_res.modules.sources.repository import NewUpload, SourceRepository
    from ai_res.platform.clock import utc_now
    async def upload(checksum):
        async with UnitOfWork(cw.services.factory) as uow:
            await uow.with_tenant(cw.iam.org_a, cw.ids["p1"])
            repo = SourceRepository(uow.session)
            uploaded = await repo.register_upload(NewUpload(cw.iam.org_a, cw.ids["p1"], cw.ids["src1"], str(uuid4()), "text/plain", 4,
                                                           checksum, utc_now()+timedelta(hours=1)))
            uploaded = await repo.mark_uploaded(uploaded)
            uploaded = await repo.verify_upload(uploaded, 4, checksum)
            return await repo.finalize_version(cw.iam.org_a, cw.ids["p1"], uploaded, received_at=utc_now(), provenance={"origin": "test"})
    service, actor = await client(cw)
    first = await upload(bytes([1])*32)
    refs = (ContextRef(ContextItemKind.SOURCE_VERSION, first.id),)
    a = await service.build(actor, cw.ids["p1"], refs, key="context-source-1")
    second = await upload(bytes([2])*32)
    b = await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.SOURCE_VERSION, second.id),), key="context-source-2",
                            package_id=a.package_id, expected_version=1)
    assert a.content_hash != b.content_hash
    assert await service.retrieve(actor, cw.ids["p1"], a.version_id) == a
    assert a.manifest.items[0].ref.version_id == first.id


async def test_concurrent_retry_creates_one_version_and_one_build_audit(cw):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),)
    a, b = await asyncio.wait_for(asyncio.gather(
        service.build(actor, cw.ids["p1"], refs, key="context-concurrent1"),
        service.build(actor, cw.ids["p1"], refs, key="context-concurrent1")), timeout=8)
    assert a == b
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 1
    assert cw.sql_one("SELECT count(*) FROM audit.audit_events WHERE action='CONTEXT_PACKAGE_BUILT'") == 1


async def test_concurrent_rebuild_cannot_overwrite_version(cw):
    service, actor = await client(cw)
    refs = (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),)
    a = await service.build(actor, cw.ids["p1"], refs, key="context-concurrent1")
    outcomes = await asyncio.wait_for(asyncio.gather(*[
        service.build(actor, cw.ids["p1"], refs, key=f"context-rebuild-{n}", package_id=a.package_id, expected_version=1)
        for n in (1, 2)], return_exceptions=True), timeout=8)
    failures = [x for x in outcomes if isinstance(x, ProblemError)]
    assert len(failures) == 1 and failures[0].code == ErrorCode.VERSION_CONFLICT
    assert len([x for x in outcomes if not isinstance(x, Exception)]) == 1
    assert cw.sql_one("SELECT last_version_number FROM context.context_packages") == 2
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 2


async def test_artifact_build_and_retrieve_without_exporting_content_ref(cw):
    service, actor = await client(cw)
    version = cw.sql_one("SELECT current_version_id FROM artifacts.artifacts WHERE id=%s", cw.ids["art1"])
    result = await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.ARTIFACT_VERSION, version),), key="context-artifact1")
    assert result.manifest.items[0].content_digest == bytes([1]*32).hex()
    assert (await service.retrieve(actor, cw.ids["p1"], result.version_id)) == result
    assert "contentRef" not in str(result.manifest.to_dict())


@pytest.mark.parametrize("legacy", [False, True])
async def test_duplicate_stored_ref_or_legacy_manifest_is_refused(cw, legacy):
    service, actor = await client(cw)
    refa = ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"])
    av = cw.sql_one("SELECT current_version_id FROM artifacts.artifacts WHERE id=%s", cw.ids["art1"])
    refb = ContextRef(ContextItemKind.ARTIFACT_VERSION, av)
    from ai_res.db.cas import canonical_json
    from ai_res.modules.context.manifest import ContextManifest
    pkg, ver = uuid4(), uuid4()
    async with UnitOfWork(cw.services.factory) as uow:
        await uow.with_tenant(cw.iam.org_a, cw.ids["p1"])
        manifest = ContextManifest(cw.iam.org_a, cw.ids["p1"], tuple([await service._resolve(uow.session, cw.iam.org_a, cw.ids["p1"], r) for r in (refa, refb)]))
        params = {"pkg": pkg, "v": ver, "o": cw.iam.org_a, "p": cw.ids["p1"], "r": refa.version_id,
                  "hash": bytes.fromhex(manifest.content_hash), "m": None if legacy else canonical_json(manifest.to_dict())}
        await uow.session.execute(text("INSERT INTO context.context_packages (id,organization_id,project_id,name,current_version_id,last_version_number) "
                                       "VALUES (:pkg,:o,:p,'test',:v,1)"), params)
        await uow.session.execute(text("INSERT INTO context.context_package_versions (id,organization_id,project_id,context_package_id,version_number,item_count,content_digest,builder_manifest) "
                                       "VALUES (:v,:o,:p,:pkg,1,2,:hash,CAST(:m AS jsonb))"), params)
        for _ in range(2):
            await uow.session.execute(text("INSERT INTO context.context_package_items (id,organization_id,project_id,context_package_version_id,item_kind,requirement_version_id,inclusion_role) "
                                           "VALUES (gen_random_uuid(),:o,:p,:v,'REQUIREMENT_VERSION',:r,'PRIMARY')"), params)
    with pytest.raises(ProblemError) as caught:
        await service.retrieve(actor, cw.ids["p1"], ver)
    assert caught.value.code == ErrorCode.STATE_TRANSITION_NOT_ALLOWED


@pytest.mark.parametrize("scope", ["user", "membership"])
async def test_concurrent_revocation_does_not_deadlock_or_allow_stale_build(cw, scope, monkeypatch):
    service, actor = await client(cw)
    if scope == "membership":
        cw.sql("INSERT INTO organization.memberships (id,organization_id,user_id,role_code) VALUES (gen_random_uuid(),%s,%s,'AUDITOR')", cw.iam.org_a, cw.viewer)
    locked, release, reached_grants = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_lock = cw.services.enforcer.lock_subject_grants
    async def observed_grants(*args, **kwargs):
        # With the old order this hook is reached with the session already
        # locked, creating the user/membership -> session inversion.
        reached_grants.set()
        return await original_lock(*args, **kwargs)
    monkeypatch.setattr(cw.services.enforcer, "lock_subject_grants", observed_grants)
    async def revoke():
        async with UnitOfWork(cw.services.factory) as uow:
            await uow.with_tenant(cw.iam.org_a)
            if scope == "user":
                sql = "UPDATE iam.users SET status='DISABLED',row_version=row_version+1 WHERE id=:u"
            else:
                sql = "UPDATE organization.memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=:u"
            await uow.session.execute(text(sql), {"u": cw.viewer})
            locked.set()
            await release.wait()
            from ai_res.modules.iam.sessions import RevokeReason
            await cw.services.sessions.revoke_all_for_user_in(uow.session, cw.viewer, RevokeReason.ROLE_REVOKED)
    revoker = asyncio.create_task(revoke())
    await asyncio.wait_for(locked.wait(), timeout=3)
    build = asyncio.create_task(service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-revoking"))
    try:
        await asyncio.wait_for(reached_grants.wait(), timeout=3)
    finally:
        release.set()
    await asyncio.wait_for(revoker, timeout=5)
    with pytest.raises(ProblemError) as caught:
        await asyncio.wait_for(build, timeout=5)
    assert caught.value.code in {ErrorCode.AUTHENTICATION_REQUIRED, ErrorCode.RESOURCE_NOT_FOUND}
    assert cw.sql_one("SELECT count(*) FROM context.context_package_versions") == 0


async def test_telemetry_has_fixed_labels_and_propagates_trace_without_source_text(cw, monkeypatch):
    from opentelemetry import trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    import ai_res.modules.context.service as instrumented
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("s19-test")
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(instrumented, "_tracer", tracer)
    monkeypatch.setattr(instrumented, "_counter", meters.get_meter("s19-test").create_counter("ai_res.context.operations"))
    service, actor = await client(cw)
    try:
        with tracer.start_as_current_span("parent") as parent:
            parent_context = parent.get_span_context()
            result = await service.build(actor, cw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, cw.ids["reqv1"]),), key="context-telemetry")
        spans = exporter.get_finished_spans()
        child = next(s for s in spans if s.name == "context.build")
        assert child.parent.span_id == parent_context.span_id
        assert child.context.trace_id == parent_context.trace_id
        assert not child.events and not child.attributes
        points = [p for rm in reader.get_metrics_data().resource_metrics for sm in rm.scope_metrics for metric in sm.metrics for p in metric.data.data_points]
        assert points and all(dict(p.attributes) == {"operation": "build", "outcome": "success"} for p in points)
        audit = cw.sql_one("SELECT details::text FROM audit.audit_events WHERE action='CONTEXT_PACKAGE_BUILT'")
        assert str(result.version_id) in audit and 'explicit-refs-v1' in audit
        assert 'The system shall' not in audit and 'csrf' not in audit
        assert trace.get_current_span().get_span_context().trace_id == 0
    finally:
        provider.shutdown()
        meters.shutdown()
