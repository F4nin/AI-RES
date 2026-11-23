# ruff: noqa: F811  -- pytest fixtures are imported by name
"""Exercise the actual gateway under the backend PostgreSQL role and scoped grant policies."""
from asyncio import gather
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege

from ai_res.application.tools import PROJECT_READ, ProjectToolService
from ai_res.db.session import create_session_factory
from ai_res.modules.tools.contracts import ToolCall, ToolError, ToolErrorCode, ToolLimits, ToolSubject, ToolTarget
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceName

from .conftest import Pg
from .test_repositories import ORG_A, ORG_B, PRJ_A, PRJ_B, WDV, engine_for, world  # noqa: F401
from .test_worker_result_service import created_run

pytestmark = pytest.mark.postgres


@pytest.fixture
async def tool_world(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    run = await created_run(api)
    with world.connect() as connection:
        epic = connection.execute("SELECT epic_id FROM work.tasks WHERE id = %s", [run.task_id]).fetchone()[0]
    subject = ToolSubject(
        organization_id=ORG_A, project_id=PRJ_A, epic_id=epic, task_id=run.task_id, run_id=run.id,
        worker_definition_version_id=WDV, worker_type="REQUIREMENTS", service=ServiceName.WORKER_RUNTIME,
        identity_id=uuid4(), identity_expires_at=utc_now() + timedelta(minutes=3), environment="test",
    )
    call = ToolCall(
        ref=PROJECT_READ, contract_version="1.0", operation="read", grant_id=uuid4(),
        target=ToolTarget(resource_type="PROJECT", resource_id=PRJ_A, classification="INTERNAL"),
    )
    service = ProjectToolService(create_session_factory(api), limits=ToolLimits(5, 256, 2048, 1),
                                 environment="test", policy_timeout=2, audit_timeout=2)
    return subject, call, service


def seed_grant(pg, subject, call):
    with pg.connect() as connection:
        connection.execute("""
            INSERT INTO agents.worker_tool_grants (
                id, organization_id, project_id, worker_run_id, identity_id, environment, tool_id,
                tool_version, contract_version, operation, resource_type, resource_id,
                classification, permission_scope, allowed_model_profiles, budget_ref, expires_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'project.read','{}',%s,clock_timestamp()+interval '5 minutes')
        """, [call.grant_id, subject.organization_id, subject.project_id, subject.run_id, subject.identity_id,
              subject.environment, call.ref.tool_id, call.ref.version, call.contract_version, call.operation,
              call.target.resource_type, call.target.resource_id, call.target.classification, uuid4()])


async def test_missing_grant_invalid_arguments_and_live_revocation(world, tool_world):
    subject, call, service = tool_world
    with pytest.raises(ToolError) as missing:
        await service.invoke(subject, call, {})
    assert missing.value.code is ToolErrorCode.AUTHORIZATION
    seed_grant(world, subject, call)
    with pytest.raises(ToolError) as invalid:
        await service.invoke(subject, call, {"extra": "fixture-canary"})
    assert invalid.value.code is ToolErrorCode.VALIDATION
    result = await service.invoke(subject, call, {})
    assert result["projectId"] == str(PRJ_A)
    with world.connect() as connection:
        connection.execute("UPDATE agents.worker_tool_grants SET revoked_at = clock_timestamp() WHERE id = %s", [call.grant_id])
    with pytest.raises(ToolError) as revoked:
        await service.invoke(subject, call, {})
    assert revoked.value.code is ToolErrorCode.AUTHORIZATION
    with world.connect() as connection:
        records = connection.execute(
            "SELECT action, result, details FROM audit.audit_events WHERE actor_id = %s ORDER BY occurred_at", [subject.run_id],
        ).fetchall()
    assert [record[0] for record in records].count("TOOL_CALL_AUTHORIZED") == 1
    assert [record[1] for record in records].count("DENIED") == 2
    assert "fixture-canary" not in repr(records)


async def test_grant_is_fenced_by_tenant_and_identity_and_cannot_be_extended_by_api(world, tool_world):
    subject, call, service = tool_world
    seed_grant(world, subject, call)
    for other in (replace(subject, identity_id=uuid4()), replace(subject, organization_id=ORG_B, project_id=PRJ_B)):
        with pytest.raises(ToolError) as denied:
            await service.invoke(other, call, {})
        assert denied.value.code is ToolErrorCode.AUTHORIZATION
    with world.connect("ai_res_api") as connection:
        assert connection.execute("SELECT id FROM agents.worker_tool_grants").fetchall() == []
        with pytest.raises(InsufficientPrivilege):
            connection.execute("UPDATE agents.worker_tool_grants SET permission_scope = 'other' WHERE id = %s", [call.grant_id])
        with pytest.raises(InsufficientPrivilege):
            connection.execute("INSERT INTO agents.worker_tool_grants DEFAULT VALUES")


async def test_concurrent_callers_share_the_grant_rate_budget(world, tool_world):
    subject, call, service = tool_world
    seed_grant(world, subject, call)
    results = await gather(service.invoke(subject, call, {}), service.invoke(subject, call, {}), return_exceptions=True)
    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, ToolError)]
    assert [result["projectId"] for result in successes] == [str(PRJ_A)]
    assert [error.code for error in failures] == [ToolErrorCode.RATE_LIMIT]


async def test_command_write_is_atomic_and_replayed_without_reapplying(world, tool_world, engine_for):
    from sqlalchemy import text

    from ai_res.application.tool_commands import CommandResultRef, SqlToolWriteExecutor
    from ai_res.application.tools import project_tool_registry
    from ai_res.db.session import UnitOfWork
    from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
    from ai_res.modules.tools.contracts import SideEffect

    subject, call, _ = tool_world
    declaration = project_tool_registry(ToolLimits(5, 256, 2048, 1), environment="test").active(PROJECT_READ).definition
    declaration = replace(declaration, side_effect=SideEffect.DOMAIN_WRITE, operation="update")
    call = replace(call, operation="update", idempotency_key="fixture-tool-key-001")
    factory = create_session_factory(engine_for("ai_res_api"))
    idem = IdempotencyService(IdempotencyKeyRing("test", {"test": b"q" * 32}), timedelta(minutes=5))
    executions = 0

    async def allow():
        pass

    async def execute(arguments, *, invalid=False):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(subject.organization_id, subject.project_id)

            class FixtureCommand:
                async def check_precondition(self, subject, call, arguments):
                    assert arguments["title"]

                async def apply(self, subject, call, arguments):
                    nonlocal executions
                    executions += 1
                    await uow.session.execute(
                        text("UPDATE project.projects SET name = :name, row_version = row_version + 1 WHERE id = :project"),
                        {"name": arguments["title"], "project": subject.project_id},
                    )
                    return CommandResultRef(subject.project_id, uuid4())

                async def verify_result(self, subject, call, result):
                    assert (await uow.session.execute(
                        text("SELECT name FROM project.projects WHERE id = :project"), {"project": subject.project_id},
                    )).scalar_one() == arguments["title"]

            def validate(output):
                if invalid:
                    raise ToolError(ToolErrorCode.EXECUTION)
                return output

            executor = SqlToolWriteExecutor(uow.session, idem, {declaration.adapter_id: FixtureCommand()})
            try:
                return await executor.execute(subject, call, declaration, arguments, validate, allow)
            except ToolError as error:
                # A product application may commit the denial audit while the effect and receipt are rolled back.
                return error.code

    assert await execute({"title": "Rejected effect"}, invalid=True) is ToolErrorCode.EXECUTION
    with world.connect() as connection:
        assert connection.execute("SELECT name FROM project.projects WHERE id = %s", [subject.project_id]).fetchone() != ("Rejected effect",)
        assert connection.execute("SELECT count(*) FROM platform.idempotency_records WHERE scope_id = %s", [subject.run_id]).fetchone() == (0,)
    first, second = await gather(execute({"title": "Committed effect"}), execute({"title": "Committed effect"}))
    assert first == second and first["resourceId"] == str(subject.project_id)
    assert executions == 2  # one rolled back attempt plus one committed command
    assert await execute({"title": "Conflict"}) is ToolErrorCode.CONFLICT


@pytest.mark.parametrize("failure", ["cancelled_operation", "expired_grant", "expired_identity", "wrong_contract"])
async def test_stale_or_cancelled_authority_blocks_calls(world, tool_world, failure):
    subject, call, service = tool_world
    seed_grant(world, subject, call)
    with world.connect() as connection:
        if failure == "cancelled_operation":
            connection.execute("""
                UPDATE operations.operations SET status = 'CANCELLED', completed_at = clock_timestamp(), row_version = row_version + 1
                WHERE id = (SELECT operation_id FROM agents.worker_runs WHERE id = %s)
            """, [subject.run_id])
        elif failure == "expired_grant":
            connection.execute("UPDATE agents.worker_tool_grants SET expires_at = clock_timestamp() WHERE id = %s", [call.grant_id])
        elif failure == "expired_identity":
            subject = replace(subject, identity_expires_at=utc_now())
        else:
            call = replace(call, contract_version="2.0")
    with pytest.raises(ToolError) as denied:
        await service.invoke(subject, call, {})
    assert denied.value.code is ToolErrorCode.AUTHORIZATION
