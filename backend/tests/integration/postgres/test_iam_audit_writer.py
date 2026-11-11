# ruff: noqa: E501
"""S07: fail-closed audit writer (SEC-019, AUTH-013): same transaction as the action, RLS-pinned scope, no secrets, append-only."""
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.audit.writer import SqlAuditWriter, correlation_uuid
from ai_res.platform.ports import AuditOutcome, AuditRecord

pytestmark = pytest.mark.postgres


def rec(org: Any, **kw: Any) -> AuditRecord:
    base: dict[str, Any] = {"action": "AUTH_LOGIN_SUCCEEDED", "outcome": AuditOutcome.SUCCEEDED, "resource_type": "session", "organization_id": str(org)}
    base.update(kw)
    return AuditRecord(**base)


async def test_writes_a_mapped_row_in_the_callers_transaction(iam_world: Any) -> None:
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    async with uow:
        await uow.with_tenant(iam_world.org_a)
        await SqlAuditWriter(uow.session).write(rec(iam_world.org_a, actor_id=str(iam_world.user_a), request_id="req-1234567890", policy_version="p1",
                                                    details={"method": "password"}, outcome=AuditOutcome.ALLOWED))
    with iam_world.pg.connect() as c:
        row = c.execute("SELECT actor_type, actor_id, action, object_type, result, details->>'method', details->>'policyVersion', correlation_id FROM audit.audit_events").fetchone()
    assert row[:7] == ("USER", iam_world.user_a, "AUTH_LOGIN_SUCCEEDED", "SESSION", "SUCCEEDED", "password", "p1")
    assert row[7] == correlation_uuid("req-1234567890")


def test_correlation_is_deterministic_and_keeps_uuid_ids() -> None:
    u = uuid4()
    assert correlation_uuid(str(u)) == u and correlation_uuid("abc-request-id") == correlation_uuid("abc-request-id")
    assert correlation_uuid(None) != correlation_uuid(None)


async def test_audit_failure_rolls_back_the_protected_action(iam_world: Any) -> None:
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    with pytest.raises(ValueError, match="sensitive"):
        async with uow:
            await uow.with_tenant(iam_world.org_a)
            await uow.session.execute(text("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (:i, :o, 'p', 'GREENFIELD')"),
                                      {"i": uuid4(), "o": iam_world.org_a})  # the protected action
            await SqlAuditWriter(uow.session).write(rec(iam_world.org_a, details={"password": "x"}))
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM project.projects").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM audit.audit_events").fetchone()[0] == 0


async def test_database_error_in_audit_insert_aborts_the_action_too(iam_world: Any) -> None:
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    with pytest.raises(DBAPIError):
        async with uow:
            await uow.with_tenant(iam_world.org_a)
            await uow.session.execute(text("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (:i, :o, 'p', 'GREENFIELD')"),
                                      {"i": uuid4(), "o": iam_world.org_a})
            await SqlAuditWriter(uow.session).write(rec(iam_world.org_a, action="lower_case_is_invalid"))  # violates ck_audit_events_action
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM project.projects").fetchone()[0] == 0


async def test_rls_refuses_audit_rows_for_another_organization_or_without_context(iam_world: Any) -> None:
    for tenant_org, record_org in ((iam_world.org_a, iam_world.org_b), (None, iam_world.org_a)):
        uow = UnitOfWork(create_session_factory(iam_world.engine()))
        with pytest.raises(DBAPIError):
            async with uow:
                if tenant_org is not None:
                    await uow.with_tenant(tenant_org)
                await SqlAuditWriter(uow.session).write(rec(record_org))
    with iam_world.pg.connect() as c:
        assert c.execute("SELECT count(*) FROM audit.audit_events").fetchone()[0] == 0


async def test_record_without_organization_is_refused_before_touching_the_database(iam_world: Any) -> None:
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    with pytest.raises(ValueError, match="organization_id"):
        async with uow:
            await SqlAuditWriter(uow.session).write(AuditRecord(action="A", outcome=AuditOutcome.DENIED, resource_type="x"))


async def test_audit_rows_are_append_only_for_the_api_role(iam_world: Any) -> None:
    uow = UnitOfWork(create_session_factory(iam_world.engine()))
    async with uow:
        await uow.with_tenant(iam_world.org_a)
        await SqlAuditWriter(uow.session).write(rec(iam_world.org_a))
    for sql in ("UPDATE audit.audit_events SET reason_code = 'x'", "DELETE FROM audit.audit_events"):
        uow = UnitOfWork(create_session_factory(iam_world.engine()))
        with pytest.raises(DBAPIError):
            async with uow:
                await uow.with_tenant(iam_world.org_a)
                await uow.session.execute(text(sql))
