# ruff: noqa: E501, S608  -- fixed literal SQL in test assertions
"""S11 end to end on REAL PostgreSQL + REAL Temporal: Operation + Outbox (one transaction) -> dispatcher (role ai_res_outbox_dispatcher) -> TemporalStartPublisher ->
OperationWorkflow on the Manager worker -> Activities -> internal Platform API -> Application Service (role ai_res_api) -> Operation FAILED (skeleton, fail closed).
No WorkerRun exists anywhere on this path. The only in-process shortcut is the ASGI transport between the Manager worker and the internal API app."""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.exc import IntegrityError
from temporalio.client import Client

from ai_res.api.internal_api import create_internal_app
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.dispatcher import Dispatcher, DispatcherConfig, InternalFanoutPublisher
from ai_res.modules.events.envelope import DOMAIN_DESTINATION, EventRef
from ai_res.modules.events.outbox_repository import OutboxRepository
from ai_res.modules.events.temporal_start import TemporalStartPublisher
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, ServiceTokenVerifier
from ai_res.modules.operations.cancellation import request_cancellation
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.operations.repository import NewOperation, OperationRepository
from ai_res.orchestration.client import OperationStarter
from ai_res.orchestration.contracts import CANCEL_DESTINATION, EXECUTION_ASSIGNMENT_REF, START_DESTINATION, OperationRef, workflow_id_for
from ai_res.orchestration.http_platform import HttpOperationPlatform
from ai_res.orchestration.workers import manager_worker
from ai_res.platform.config import load_settings
from ai_res.platform.ports import ServiceName
from tests.integration.postgres.test_internal_platform_api import pub
from tests.integration.temporal.conftest import client, temporal_address  # noqa: F401  (fixtures)

from .conftest import Pg

pytestmark = [pytest.mark.postgres, pytest.mark.temporal]
ORG, PRJ = uuid4(), uuid4()
CONTRACT = Path(__file__).resolve().parents[4] / "contracts/asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"


def engine_for(pg: Pg, role: str, tmp_path: Path):
    pw = tmp_path / f"{role}_pw"
    pw.write_text(pg.passwords[role])
    return create_runtime_engine(load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": pg.host, "AI_RES_DB_PORT": str(pg.port), "AI_RES_DB_USER": role,
                                                "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "s11-e2e"}))


async def test_outbox_to_temporal_to_operation_end_to_end(migrated: Pg, client: Client, tmp_path: Path):  # noqa: F811
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s,'o')", [ORG])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [PRJ, ORG])
    api, dispatcher_engine = engine_for(migrated, "ai_res_api", tmp_path), engine_for(migrated, "ai_res_outbox_dispatcher", tmp_path)
    key = Ed25519PrivateKey.generate()
    app = create_internal_app(OperationOrchestrationService(create_session_factory(api)),
                              ServiceTokenVerifier({ServiceName.MANAGER_RUNTIME: (pub(key),)}, max_ttl=timedelta(minutes=5)))
    issuer = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, key, max_ttl=timedelta(minutes=5))
    platform = HttpOperationPlatform("http://internal", lambda: issuer.issue(ServiceName.API, timedelta(seconds=60)), transport=httpx.ASGITransport(app=app))

    op_id, corr = uuid4(), uuid4()
    op = NewOperation(id=op_id, organization_id=ORG, project_id=PRJ, operation_type="PLAN_EXECUTION", initiator_type="USER", idempotency_scope="s",
                      request_fingerprint=b"\x02" * 32, completion_policy_version="wip-1", completion_policy_snapshot={}, correlation_id=corr)
    async with UnitOfWork(create_session_factory(api)) as uow:  # the accepted event also feeds a destination this dispatcher has NO route for
        await uow.with_tenant(ORG, PRJ)
        await OperationRepository(uow.session).create(op, EventSpec(event_type="operation.accepted", schema_version=1, actor_type="USER", correlation_id=corr,
                                                                     destinations=(START_DESTINATION, DOMAIN_DESTINATION)))
    start = TemporalStartPublisher(OperationStarter(client))
    dispatcher = Dispatcher(create_session_factory(dispatcher_engine), InternalFanoutPublisher({START_DESTINATION: [start.publish]}),
                            EventContract.from_file(CONTRACT), DispatcherConfig(owner="e2e", destinations=(START_DESTINATION,)))
    try:
        async with manager_worker(client, platform):
            assert await dispatcher.run_once() == 1
            result = await client.get_workflow_handle(workflow_id_for(op_id)).result()
            assert result["outcome"] == "SKELETON_FAILED_CLOSED"
            # duplicate delivery of the SAME command (lease lost / crash after publish): put the row back and deliver again
            with migrated.connect() as c:
                c.execute("UPDATE audit.outbox_events SET status='PENDING', published_at=NULL, available_at=now() WHERE aggregate_id=%s AND destination=%s", [op_id, START_DESTINATION])
            assert await dispatcher.run_once() == 1
        with migrated.connect() as c:
            row = c.execute("SELECT status, workflow_id, problem_ref FROM operations.operations WHERE id=%s", [op_id]).fetchone()
            events = [r[0] for r in c.execute("SELECT event_type FROM operations.operation_events WHERE operation_id=%s ORDER BY aggregate_sequence", [op_id])]
            by_dest = dict(c.execute("SELECT destination, status FROM audit.outbox_events WHERE aggregate_id=%s AND aggregate_sequence=1", [op_id]).fetchall())
            workflows = [w async for w in client.list_workflows(f"WorkflowId = '{workflow_id_for(op_id)}'")]
        assert row == ("FAILED", f"operation-{op_id}", {"code": "ORCHESTRATION_NOT_IMPLEMENTED"})
        assert [e.split(".")[-2] if e.startswith("com.") else e.split(".")[-1] for e in events] == ["accepted", "queued", "started", "failed"]  # duplicate start added nothing
        assert by_dest == {START_DESTINATION: "PUBLISHED", DOMAIN_DESTINATION: "PENDING"}  # the other destination was left for its own consumer, not quarantined
        assert len(workflows) == 1
        with migrated.connect() as c:
            assert c.execute("SELECT count(*) FROM agents.worker_runs").fetchone()[0] == 0  # no WorkerRun is created by the skeleton
    finally:
        await platform.aclose()
        await api.dispose()
        await dispatcher_engine.dispose()


async def test_claim_by_destination_never_touches_other_destinations_even_when_their_leases_expire(migrated: Pg, tmp_path: Path):
    org, prj = uuid4(), uuid4()
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s,'o')", [org])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
    api, disp = engine_for(migrated, "ai_res_api", tmp_path), engine_for(migrated, "ai_res_outbox_dispatcher", tmp_path)
    try:
        op_id = uuid4()
        async with UnitOfWork(create_session_factory(api)) as uow:
            await uow.with_tenant(org, prj)
            await OperationRepository(uow.session).create(
                NewOperation(id=op_id, organization_id=org, project_id=prj, operation_type="PLAN_EXECUTION", initiator_type="USER", idempotency_scope="s",
                             request_fingerprint=b"\x04" * 32, completion_policy_version="wip-1", completion_policy_snapshot={}, correlation_id=uuid4()),
                EventSpec(event_type="operation.accepted", schema_version=1, actor_type="USER", correlation_id=uuid4(), destinations=(START_DESTINATION, DOMAIN_DESTINATION)))
        factory = create_session_factory(disp)
        async with UnitOfWork(factory) as uow:
            claimed = await OutboxRepository(uow.session).claim("a", 10, 30, 3, [START_DESTINATION])
        assert [r.destination for r in claimed] == [START_DESTINATION]
        with migrated.connect() as c:  # the foreign destination's row sits IN_FLIGHT with an expired lease and a spent attempt budget
            c.execute("UPDATE audit.outbox_events SET status='IN_FLIGHT', lease_owner='other', lease_until=now() - interval '1 minute', attempt_count=9 WHERE aggregate_id=%s AND destination=%s",
                      [op_id, DOMAIN_DESTINATION])
        async with UnitOfWork(factory) as uow:
            repo = OutboxRepository(uow.session)
            await repo.claim("a", 10, 30, 3, [START_DESTINATION])
            assert repo.claim_quarantined == 0
            for bad in ([], [""]):
                with pytest.raises(ValueError):
                    await repo.claim("a", 10, 30, 3, bad)
        with migrated.connect() as c:
            assert c.execute("SELECT status FROM audit.outbox_events WHERE aggregate_id=%s AND destination=%s", [op_id, DOMAIN_DESTINATION]).fetchone() == ("IN_FLIGHT",)
    finally:
        await api.dispose()
        await disp.dispose()


async def test_start_routes_keep_other_dispatchers_rows_and_expired_leases(migrated: Pg, tmp_path: Path):
    org, project = uuid4(), uuid4()
    unassigned, blue, expired_blue, red, expired_red = (uuid4() for _ in range(5))
    actor = uuid4()
    with migrated.connect() as db:
        db.execute("INSERT INTO organization.organizations (id,name) VALUES (%s,'o')", [org])
        db.execute("INSERT INTO project.projects (id,organization_id,name,project_type) VALUES (%s,%s,'p','GREENFIELD')", [project, org])
        db.execute("INSERT INTO iam.users (id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'route@example.test','route@example.test','Analyst')",
                   [actor, org])
    api, disp = engine_for(migrated, "ai_res_api", tmp_path), engine_for(migrated, "ai_res_outbox_dispatcher", tmp_path)
    try:
        api_factory, factory = create_session_factory(api), create_session_factory(disp)

        async def create(oid, namespace, *, routing_namespace=None):
            async with UnitOfWork(api_factory) as uow:
                await uow.with_tenant(org, project)
                correlation = uuid4()
                op = NewOperation(id=oid, organization_id=org, project_id=project, operation_type="MANAGER_MESSAGE", initiator_type="USER",
                                  idempotency_scope=str(oid), request_fingerprint=b"\x05" * 32, completion_policy_version="wip-1",
                                  completion_policy_snapshot={}, correlation_id=correlation)
                assignment = uuid4()
                refs = () if namespace is None else (EventRef(EXECUTION_ASSIGNMENT_REF, assignment),)
                await OperationRepository(uow.session).create(op, EventSpec(
                    "operation.accepted", 1, "USER", correlation, (START_DESTINATION,),
                    refs=refs, dispatch_namespace=routing_namespace or namespace,
                ))
                if namespace is not None:
                    bindings = OperationAssignments(uow.session)
                    await bindings.register(oid, namespace=namespace, assignment_id=assignment, actions=frozenset({
                        PlatformAction.ACKNOWLEDGE_START, PlatformAction.CONFIRM_CANCELLATION,
                    }))
                    assert await bindings.bind_run(assignment, oid, uuid4())

        for oid, namespace in ((unassigned, None), (blue, "blue"), (expired_blue, "blue"), (red, "red"), (expired_red, "red")):
            await create(oid, namespace)
        with pytest.raises(IntegrityError, match="fk_outbox_dispatch_route"):
            await create(uuid4(), "red", routing_namespace="blue")
        for oid in (blue, red):
            async with UnitOfWork(api_factory) as uow:
                await OperationOrchestrationService.acknowledge_start_in(uow, OperationRef(str(oid), str(org), str(project)), uuid4())
            async with UnitOfWork(api_factory) as uow:
                await uow.with_tenant(org, project)
                assert (await request_cancellation(uow.session, oid, actor_id=actor, correlation_id=uuid4())).status == "CANCEL_REQUESTED"
        with migrated.connect() as db:
            db.execute("UPDATE audit.outbox_events SET status='IN_FLIGHT', lease_owner='protected', lease_until=now()-interval '1 minute', attempt_count=3 "
                       "WHERE aggregate_id=ANY(%s)", [[expired_blue, expired_red]])
        async with UnitOfWork(factory) as uow:
            repo = OutboxRepository(uow.session)
            claimed = await repo.claim("legacy", 10, 30, 3, [START_DESTINATION, CANCEL_DESTINATION])
            assert [row.aggregate_id for row in claimed] == [unassigned]
            assert repo.claim_quarantined == 0
        async with UnitOfWork(factory) as uow:
            repo = OutboxRepository(uow.session)
            claimed = await repo.claim("blue", 10, 30, 3, [START_DESTINATION, CANCEL_DESTINATION], assigned_namespace="blue")
            assert {(row.aggregate_id, row.destination) for row in claimed} == {(blue, START_DESTINATION), (blue, CANCEL_DESTINATION)}
            assert repo.claim_quarantined == 1
        with migrated.connect() as db:
            assert db.execute("SELECT status,attempt_count FROM audit.outbox_events WHERE aggregate_id=%s AND dispatch_namespace='red'",
                              [expired_red]).fetchone() == ("IN_FLIGHT", 3)
            assert db.execute("SELECT DISTINCT status,attempt_count FROM audit.outbox_events WHERE aggregate_id=%s AND dispatch_namespace='red'",
                              [red]).fetchall() == [("PENDING", 0)]
        async with UnitOfWork(factory) as uow:
            repo = OutboxRepository(uow.session)
            claimed = await repo.claim("red", 10, 30, 3, [START_DESTINATION, CANCEL_DESTINATION], assigned_namespace="red")
            assert {(row.aggregate_id, row.destination) for row in claimed} == {(red, START_DESTINATION), (red, CANCEL_DESTINATION)}
            assert repo.claim_quarantined == 1
    finally:
        await api.dispose()
        await disp.dispose()
