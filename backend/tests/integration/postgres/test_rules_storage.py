# ruff: noqa: E501, S608 -- fixed fixture table allowlist, no application SQL input
"""S18 rule registry lifecycle and append-only records on real PostgreSQL."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from ai_res.db.session import UnitOfWork
from ai_res.modules.rules.registry import RuleRegistry
from ai_res.modules.rules.repository import RulesRepository
from ai_res.modules.rules.types import FactField, FactSchema, FactType, RuleStatus
from ai_res.platform.problems import ErrorCode, ProblemError

from .conftest import run_audit
from .test_read_api import World

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)
SCHEMA = FactSchema("1.0", (FactField("enabled", FactType.BOOL),))
CONDITION = {"op": "eq", "field": "enabled", "value": True}
ACTION = {"schemaVersion": "1.0", "effects": [{"kind": "REQUIRE", "target": "QA"}]}


@pytest.fixture
def rw(iam_world, tmp_path):
    return World(iam_world, tmp_path)


async def draft(w, *, rule_id=None, expected=1):
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(w.iam.org_a, w.ids["p1"])
        repo = RulesRepository(uow.session)
        rule_id = rule_id or await repo.create_rule(w.iam.org_a, w.ids["p1"], rule_key=f"test.{uuid4()}", title="QA", level="PROJECT", created_by=w.viewer)
        return await repo.create_version(rule_id, expected, condition=CONDITION, action=ACTION, author_id=w.viewer)


async def call(w, name, *args, **kwargs):
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(w.iam.org_a, w.ids["p1"])
        return await getattr(RulesRepository(uow.session), name)(*args, **kwargs)


async def publish(w, row, *, at=NOW, start=NOW-timedelta(hours=1)):
    rv = await call(w, "submit", row["id"], row["parent_row_version"])
    rv = await call(w, "schedule_approval", row["id"], rv, approver_user_id=w.viewer, approved_at=NOW-timedelta(hours=2), valid_from=start, valid_to=NOW+timedelta(days=1))
    return await call(w, "publish", row["id"], rv, at=at, actor_id=w.viewer)


async def test_rule_lifecycle_version_counter_and_complete_registry(rw):
    row = await draft(rw)
    assert row["version_number"] == 1 and row["status"] == "DRAFT" and row["parent_row_version"] == 2
    await publish(rw, row)
    current = await call(rw, "get_version", row["id"])
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a, rw.ids["p1"])
        snapshots = await RuleRegistry(uow.session, SCHEMA).snapshots()
    assert len(snapshots) == 1 and snapshots[0].status is RuleStatus.APPROVED
    second = await draft(rw, rule_id=row["rule_id"], expected=current["parent_row_version"])
    assert second["version_number"] == 2
    await publish(rw, second)
    assert (await call(rw, "get_version", row["id"]))["status"] == "RETIRED"
    assert (await call(rw, "get_version", second["id"]))["status"] == "APPROVED"
    assert rw.sql_one("SELECT count(*) FROM governance.rule_versions WHERE status='APPROVED'") == 1


async def test_manager_proposal_retains_rationale_and_stays_unapproved(rw):
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        repo = RulesRepository(uow.session)
        rule_id = await repo.create_rule(rw.iam.org_a,rw.ids["p1"],rule_key="manager.proposal",title="QA",level="PROJECT",created_by=None)
        row = await repo.create_version(rule_id,1,condition=CONDITION,action=ACTION,author_type="MANAGER",author_id=uuid4(),rationale="Require the declared QA check.")
        assert row["author_type"] == "MANAGER" and row["rationale"] == "Require the declared QA check."
        assert row["status"] == "DRAFT" and row["approver_user_id"] is None
        assert await RuleRegistry(uow.session,SCHEMA).snapshots() == ()


async def test_future_approval_does_not_retire_current_version(rw):
    first = await draft(rw)
    await publish(rw, first)
    old = await call(rw, "get_version", first["id"])
    future = await draft(rw, rule_id=first["rule_id"], expected=old["parent_row_version"])
    rv = await call(rw, "submit", future["id"], future["parent_row_version"])
    rv = await call(rw, "schedule_approval", future["id"], rv, approver_user_id=rw.viewer, approved_at=NOW, valid_from=NOW+timedelta(hours=1), valid_to=NOW+timedelta(days=1))
    with pytest.raises(ProblemError):
        await call(rw, "publish", future["id"], rv, at=NOW, actor_id=rw.viewer)
    assert (await call(rw, "get_version", first["id"]))["status"] == "APPROVED"
    assert (await call(rw, "get_version", future["id"]))["status"] == "PROPOSED"


async def test_counter_cas_rejects_concurrent_writers(rw):
    row = await draft(rw)
    outcomes = await asyncio.gather(draft(rw, rule_id=row["rule_id"], expected=2), draft(rw, rule_id=row["rule_id"], expected=2), return_exceptions=True)
    failures = [x for x in outcomes if isinstance(x, ProblemError)]
    assert len(failures) == 1 and failures[0].code == ErrorCode.VERSION_CONFLICT
    assert rw.sql_one("SELECT last_version_number FROM governance.rules WHERE id=%s", row["rule_id"]) == 2


async def test_rejected_snapshot_does_not_advance_counter_when_caller_handles_error(rw):
    row = await draft(rw)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        repo = RulesRepository(uow.session)
        with pytest.raises(ValueError):
            await repo.create_version(row["rule_id"],2,condition={"password":"CANARY"},action=ACTION)
    assert rw.sql_one("SELECT last_version_number FROM governance.rules WHERE id=%s",row["rule_id"]) == 1
    assert (await call(rw,"get_version",row["id"]))["parent_row_version"] == 2


async def test_suspend_resume_preserves_approval_and_uses_cas(rw):
    row = await draft(rw)
    rv = await publish(rw, row)
    rv = await call(rw, "suspend", row["id"], rv, at=NOW, actor_id=rw.viewer)
    assert (await call(rw, "get_version", row["id"]))["suspended"] is True
    rv = await call(rw, "resume", row["id"], rv, at=NOW, actor_id=rw.viewer)
    current = await call(rw, "get_version", row["id"])
    assert current["suspended"] is False and current["status"] == "APPROVED"
    assert current["parent_row_version"] == rv


async def test_registry_rejects_malformed_legacy_conditions(rw):
    row = await draft(rw)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        assert await RuleRegistry(uow.session,SCHEMA).snapshots() == ()
    bad = await call(rw,"create_version",row["rule_id"],2,condition={"eval":"bad"},action=ACTION,author_type="IMPORT")
    await publish(rw,bad)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        with pytest.raises(ProblemError):
            await RuleRegistry(uow.session, SCHEMA).snapshots()


async def test_new_tables_have_forced_rls_and_no_update_delete_or_truncate(rw):
    tables = ("rule_validation_reports","rule_evaluations","rule_exceptions","rule_runtime_controls","rule_exception_revocations")
    with rw.iam.pg.connect() as c:
        assert run_audit(c,"rls_coverage.sql") == [] and run_audit(c,"grants_audit.sql") == []
        for table in tables:
            row = c.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass", [f"governance.{table}"]).fetchone()
            assert row == (True,True)
    for table in tables:
        with rw.iam.pg.connect("ai_res_api") as c:
            for operation in ("UPDATE","DELETE","TRUNCATE"):
                with pytest.raises(psycopg.Error):
                    sql = f"UPDATE governance.{table} SET id=id" if operation == "UPDATE" else f"DELETE FROM governance.{table}" if operation == "DELETE" else f"TRUNCATE governance.{table}"
                    c.execute(sql)


async def test_registry_includes_system_org_and_project_without_caller_subset(rw):
    project_rule = await draft(rw)
    await publish(rw, project_rule)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        repo = RulesRepository(uow.session)
        org_rule = await repo.create_rule(rw.iam.org_a,None,rule_key="org.qa",title="QA",level="ORGANIZATION",created_by=rw.viewer)
        org_version = await repo.create_version(org_rule,1,condition=CONDITION,action=ACTION,author_id=rw.viewer)
    await publish(rw,org_version)
    system_rule, system_version = uuid4(),uuid4()
    from ai_res.db.cas import canonical_json
    with rw.iam.pg.connect(autocommit=False) as c:
        c.execute("INSERT INTO governance.rules (id,level,rule_key,title) VALUES (%s,'SYSTEM','system.qa','QA')",[system_rule])
        c.execute("INSERT INTO governance.rule_versions (id,rule_id,level,version_number,condition,action,author_type) VALUES (%s,%s,'SYSTEM',1,%s::jsonb,%s::jsonb,'USER')",
                  [system_version,system_rule,canonical_json(CONDITION),canonical_json(ACTION)])
        c.execute("UPDATE governance.rules SET last_version_number=1,row_version=row_version+1 WHERE id=%s",[system_rule])
        c.execute("UPDATE governance.rule_versions SET status='PROPOSED' WHERE id=%s",[system_version])
        c.execute("UPDATE governance.rule_versions SET status='APPROVED',approver_user_id=%s,approved_at=%s,valid_from=%s WHERE id=%s",[rw.viewer,NOW-timedelta(days=1),NOW-timedelta(days=1),system_version])
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        snapshots = await RuleRegistry(uow.session,SCHEMA).snapshots()
        assert {r.scope.level.name for r in snapshots} == {"SYSTEM","ORGANIZATION","PROJECT"}
        with pytest.raises(ProblemError):
            await RulesRepository(uow.session).suspend(system_version,2,at=NOW,actor_id=rw.viewer)


async def test_exception_snapshot_and_revocation_are_append_only_and_exact(rw):
    from ai_res.modules.rules.types import EvaluationScope, RuleException
    target = await draft(rw)
    await publish(rw,target)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        repo = RulesRepository(uow.session)
        permission_rule = await repo.create_rule(rw.iam.org_a,None,rule_key="org.waive",title="Waiver",level="ORGANIZATION",created_by=rw.viewer)
        permission = await repo.create_version(permission_rule,1,condition=CONDITION,action={"schemaVersion":"1.0","effects":[{"kind":"ALLOW_EXCEPTION","target":"QA"}]},author_id=rw.viewer)
    await publish(rw,permission)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        registry = RuleRegistry(uow.session,SCHEMA)
        target_snapshot = await registry.get(target["id"])
        exception = RuleException(uuid4(),target_snapshot.version_id,target_snapshot.content_hash,target_snapshot.effects[0].content_hash,permission["id"],
                                  EvaluationScope(rw.iam.org_a,rw.ids["p1"],"PROJECT",rw.ids["p1"],"ANALYZE"),NOW-timedelta(hours=1),NOW+timedelta(hours=1),
                                  rw.viewer,NOW-timedelta(hours=2),"TEST_WAIVER",(uuid4(),),(uuid4(),))
        await RulesRepository(uow.session).save_exception(exception)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        assert (await RuleRegistry(uow.session,SCHEMA).exceptions()) == (exception,)
        first = await RulesRepository(uow.session).revoke_exception(exception.id,actor_id=rw.viewer,at=NOW)
        assert await RulesRepository(uow.session).revoke_exception(exception.id,actor_id=rw.viewer,at=NOW) == first
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(rw.iam.org_a,rw.ids["p1"])
        revoked = await RuleRegistry(uow.session,SCHEMA).get_exception(exception.id)
        assert revoked.revoked_at == NOW and not revoked.is_active(NOW)
    with rw.iam.pg.connect("ai_res_api") as c, pytest.raises(psycopg.Error):
        c.execute("UPDATE governance.rule_exceptions SET snapshot='{}' WHERE id=%s",[exception.id])


async def evaluation_payload(w, *, variant="valid"):
    from ai_res.modules.context.types import ContextItemKind, ContextRef
    from ai_res.modules.rules.engine import ENGINE_VERSION, evaluate_rules
    from ai_res.modules.rules.types import EvaluationScope, FactSnapshot

    from .test_context_builder import client as context_client
    context_service, actor = await context_client(w)
    context = await context_service.build(actor,w.ids["p1"],(ContextRef(ContextItemKind.REQUIREMENT_VERSION,w.ids["reqv1"]),),key="storage-context-001")
    schema = FactSchema("1.0",(FactField("context_has_source",FactType.BOOL),))
    values = (("context_has_source",False),)
    if variant == "sensitive_fact":
        schema = FactSchema("1.0",(FactField("password",FactType.CODE),))
        values = (("password","CANARY"),)
    elif variant == "wrong_type":
        values = (("context_has_source","NOT_BOOLEAN"),)
    facts = FactSnapshot(uuid4(),1,uuid4() if variant == "wrong_context" else context.version_id,values,context.content_hash,
                         provider_version="forged-provider" if variant == "wrong_provider" else "context-metadata-v1")
    scope = EvaluationScope(w.iam.org_a,w.ids["p2"] if variant == "wrong_scope" else w.ids["p1"],
                            "PROJECT" if variant == "wrong_object_type" else "CONTEXT_PACKAGE_VERSION",uuid4() if variant == "wrong_object" else context.version_id,
                            "ANALYZE" if variant == "wrong_operation" else "CONTEXT_ASSESSMENT")
    result = evaluate_rules((),facts,scope,NOW).to_dict()
    inputs = {"engineVersion":ENGINE_VERSION,"schemaVersion":"1.0","schema":schema.to_dict(),"scope":scope.to_dict(),"asOf":NOW.isoformat(),
              "facts":facts.to_dict(),"rules":[],"exceptions":[]}
    if variant == "unknown_field":
        inputs["source_text"] = "CANARY"
    elif variant == "forged_result":
        result["status"] = "blocked"
    return {"organization_id":w.iam.org_a,"project_id":w.ids["p1"],"context_version_id":context.version_id,"actor_id":w.viewer,"evaluated_at":NOW,
            "engine_version":ENGINE_VERSION,"schema_version":"1.0","input_snapshot":inputs,"result":result}


async def test_typed_presence_metadata_is_stored_verbatim_with_reproducible_hash(rw):
    payload = await evaluation_payload(rw)
    eid = await call(rw,"save_evaluation",**payload)
    row = await call(rw,"get_evaluation",eid)
    assert row["input_snapshot"] == payload["input_snapshot"]
    assert row["input_snapshot"]["facts"]["values"] == {"context_has_source":False}
    from ai_res.modules.rules.types import canonical_hash
    assert bytes(row["input_hash"]).hex() == canonical_hash(payload["input_snapshot"])
    with rw.iam.pg.connect("ai_res_api") as c, pytest.raises(psycopg.Error):
        c.execute("UPDATE governance.rule_evaluations SET result='{}' WHERE id=%s",[eid])


@pytest.mark.parametrize("variant",["sensitive_fact","wrong_type","wrong_context","wrong_scope","wrong_object","wrong_object_type","wrong_operation","wrong_provider","unknown_field","forged_result"])
async def test_untrusted_evaluation_inputs_never_reach_persistence(rw,variant):
    payload = await evaluation_payload(rw,variant=variant)
    with pytest.raises(ValueError):
        await call(rw,"save_evaluation",**payload)
    assert rw.sql_one("SELECT count(*) FROM governance.rule_evaluations") == 0


async def test_counter_initializes_from_existing_versions_on_upgrade(empty_db,upgrade,tmp_path):
    from ai_res.db.cas import canonical_json
    from ai_res.db.session import create_session_factory

    from .conftest import IamWorld
    from .test_domain_content_schema import seed_tenants
    from .test_operations_work_schema import ORG_A, PRJ_A1
    upgrade("a41c8f92d603")
    rule_id = uuid4()
    with empty_db.connect(autocommit=False) as c:
        seed_tenants(c)
        c.execute("INSERT INTO governance.rules (id,level,organization_id,project_id,rule_key,title) VALUES (%s,'PROJECT',%s,%s,'legacy.counter','QA')",[rule_id,ORG_A,PRJ_A1])
        for number in (1,2):
            c.execute("INSERT INTO governance.rule_versions (id,rule_id,level,organization_id,project_id,version_number,condition,action,author_type) VALUES (%s,%s,'PROJECT',%s,%s,%s,%s::jsonb,%s::jsonb,'IMPORT')",
                      [uuid4(),rule_id,ORG_A,PRJ_A1,number,canonical_json(CONDITION),canonical_json(ACTION)])
    upgrade("head")
    iam = IamWorld(empty_db,tmp_path)
    try:
        async with UnitOfWork(create_session_factory(iam.engine())) as uow:
            await uow.with_tenant(ORG_A,PRJ_A1)
            row = await RulesRepository(uow.session).create_version(rule_id,2,condition=CONDITION,action=ACTION,author_type="IMPORT")
        assert row["version_number"] == 3 and row["parent_row_version"] == 3
        with empty_db.connect() as c:
            assert run_audit(c,"grants_audit.sql") == [] and run_audit(c,"rls_coverage.sql") == []
    finally:
        await iam.dispose()
