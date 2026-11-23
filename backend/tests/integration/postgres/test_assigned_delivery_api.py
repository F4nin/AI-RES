"""Signed lease handoff through the private route and real PostgreSQL roles."""
import json
from asyncio import create_task, gather, sleep, timeout
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text

from ai_res.api.assigned_delivery import create_assigned_delivery_app
from ai_res.application.assigned_delivery_control import AssignedDeliveryControl
from ai_res.application.assigned_dispatch import AssignedDeliveryBackend
from ai_res.application.manager_intake import AuthorizedIntake, persist_manager_intake
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.epics.manager_interactions import ManagerMessage
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.delivery_lease import DeliveryLease
from ai_res.modules.events.outbox_repository import OutboxRepository
from ai_res.modules.iam.platform_credentials import (
    ASSIGNED_DELIVERY_PATH,
    AssignedDeliveryCredentialIssuer,
    AssignedDeliveryRequest,
    PlatformAction,
    PlatformCredentialIssuer,
    PlatformCredentialLimits,
    PlatformCredentialVerifier,
    PlatformRequest,
)
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.contracts import START_DESTINATION

from .test_repositories import ORG_A, PRJ_A, engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres
CONTRACT = Path(__file__).resolve().parents[4] / "contracts/asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"


async def test_signed_handoff_requires_exact_current_lease_and_consumes_nonce(world, engine_for):  # noqa: F811
    user = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'lease@example.test','lease@example.test','Analyst')",
            (user, ORG_A),
        )
    api = create_session_factory(engine_for("ai_res_api"))
    outbox = create_session_factory(engine_for("ai_res_outbox_dispatcher"))
    idem = IdempotencyService(IdempotencyKeyRing("fixture", {"fixture": b"e" * 32}), timedelta(minutes=5))
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Lease fixture", "ACTIVE"))
        operation = await persist_manager_intake(
            uow.session, idem, AuthorizedIntake(ORG_A, PRJ_A, epic, user, uuid4()), ManagerMessage("Fixture"),
            idempotency_key="assigned-delivery-fixture", dispatch_namespace="blue",
        )
    with world.connect() as connection:
        row_id, = connection.execute("SELECT id FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s", (operation, START_DESTINATION)).fetchone()
        assert connection.execute("""
            SELECT has_table_privilege('ai_res_api','audit.outbox_events','SELECT'),
                   has_function_privilege('ai_res_outbox_dispatcher',
                       'audit.authorize_assigned_delivery(uuid,text,integer,integer,text,uuid,timestamptz,uuid)','EXECUTE')
        """).fetchone() == (False, False)

    backend = AsyncMock(spec=AssignedDeliveryBackend)
    backend.namespace = "blue"

    async def authorized_before_io(row):
        assert row.id == row_id and row.aggregate_id == operation and row.dispatch_namespace == "blue"
        with world.connect() as connection:
            assert connection.execute("""
                SELECT count(*) FROM platform.platform_auth_events WHERE action='AUTHORIZE_ASSIGNED_DELIVERY' AND reason='AUTHORIZED'
            """).fetchone() == (1,)

    backend.publish.side_effect = authorized_before_io
    key = Ed25519PrivateKey.generate()
    ttl = timedelta(seconds=15)
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 1024, 2048)
    issuer = AssignedDeliveryCredentialIssuer(key, limits)
    contract = EventContract.from_file(CONTRACT)
    app = create_assigned_delivery_app(AssignedDeliveryControl(api, backend, contract),
                                       PlatformCredentialVerifier([key.public_key()], limits, delivery_keys=[key.public_key()]),
                                       max_body_bytes=1024, timeout_seconds=2)
    proof = DeliveryLease(row_id=row_id, lease_owner="fixture", attempt=1, replay_count=0)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://backend.test") as client:
        async def send(body: bytes, token: str | None = None, suffix: str = "") -> httpx.Response:
            token = token or issuer.issue(AssignedDeliveryRequest(body), ttl=ttl)
            return await client.post(ASSIGNED_DELIVERY_PATH + suffix, content=body, headers={"Authorization": f"Bearer {token}"})

        body = proof.model_dump_json(by_alias=True).encode()
        denied = issuer.issue(AssignedDeliveryRequest(body), ttl=ttl)
        assert (await send(body, denied)).status_code == 409
        async with UnitOfWork(outbox) as uow:
            rows = await OutboxRepository(uow.session).claim("fixture", 1, 30, 3, [START_DESTINATION], assigned_namespace="blue")
            assert [row.id for row in rows] == [row_id]
        assert (await send(body, denied)).status_code == 401
        manager = PlatformCredentialIssuer(key, limits).issue(
            PlatformRequest(PlatformAction.ACKNOWLEDGE_START, operation, body), assignment_id=uuid4(), ttl=ttl,
        )
        assert (await send(body, manager)).status_code == 401
        assert (await send(body + b" ", issuer.issue(AssignedDeliveryRequest(body), ttl=ttl))).status_code == 401
        assert (await send(body, suffix="?namespace=blue")).status_code == 401
        assert (await send(json.dumps({**json.loads(body), "workflowRunId": str(uuid4())}).encode())).status_code == 422
        for field, value in (("leaseOwner", "wrong"), ("attempt", 2), ("replayCount", 1), ("rowId", str(uuid4()))):
            assert (await send(json.dumps({**json.loads(body), field: value}).encode())).status_code == 409
        backend.namespace = "other"
        assert (await send(body)).status_code == 409
        backend.namespace = "blue"
        assert (await send(body + b" " * 1024, denied)).status_code == 413
        backend.publish.assert_not_awaited()

        token = issuer.issue(AssignedDeliveryRequest(body), ttl=ttl)
        responses = await gather(send(body, token), send(body, token))
        assert sorted(response.status_code for response in responses) == [204, 401]
        success = next(response for response in responses if response.status_code == 204)
        assert success.content == b"" and success.headers["cache-control"] == "no-store"
        backend.publish.assert_awaited_once()

        async with UnitOfWork(outbox) as uow:
            await uow.session.execute(text("""
                UPDATE audit.outbox_events SET status='PENDING',lease_owner=NULL,lease_until=NULL WHERE id=:id
            """), {"id": row_id})
            raced = create_task(send(body))
            async with timeout(1.5):
                while True:
                    with world.connect() as connection:
                        waiting, = connection.execute("""
                            SELECT count(*) FROM pg_stat_activity
                            WHERE usename='ai_res_api' AND wait_event_type='Lock'
                              AND query LIKE '%audit.authorize_assigned_delivery(%'
                        """).fetchone()
                    if waiting:
                        break
                    await sleep(0.01)
        assert (await raced).status_code == 409
        backend.publish.assert_awaited_once()

        async with UnitOfWork(outbox) as uow:
            rows = await OutboxRepository(uow.session).claim("fixture", 1, 30, 3, [START_DESTINATION], assigned_namespace="blue")
            assert [(row.id, row.attempt_count) for row in rows] == [(row_id, 2)]
            await uow.session.execute(text("UPDATE audit.outbox_events SET lease_until=now()-interval '1 second' WHERE id=:id"), {"id": row_id})
        refreshed = proof.model_copy(update={"attempt": 2}).model_dump_json(by_alias=True).encode()
        assert (await send(refreshed)).status_code == 409
        backend.publish.assert_awaited_once()
