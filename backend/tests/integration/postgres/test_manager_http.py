"""Public v1.3 intake with the separately admitted dispatch composition."""
import asyncio
import socket
import ssl
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import uvicorn
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator, FormatChecker
from temporalio.client import Client

from ai_res.api import write_api
from ai_res.api.app import create_app
from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.application.observe_operations import TemporalExecutionObserver
from ai_res.application.plan_approval_consumer import PlanApprovalSchedule
from ai_res.application.plan_execution import prepare_approved_plan_event
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.application.reconcile_operations import has_confirmed_start, prepare_assigned_start, recover_unacknowledged_start
from ai_res.application.reconcile_scheduler import BoundStartSchedule, BoundStartScheduler, ReconciliationScope
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm import LLMLimits
from ai_res.llm.transport import TransportResult
from ai_res.llm.types import FinishReason, Usage
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.events.temporal_start import AssignedTemporalStartPublisher, assigned_start_request
from ai_res.modules.iam.platform_credentials import PlatformCredentialIssuer, PlatformCredentialLimits, PlatformCredentialVerifier
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanSnapshot, PlanVersionRepository
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.client import AssignedOperationStarter, AssignedStart, OperationCanceller
from ai_res.orchestration.contracts import START_DESTINATION, AssignedWorkflowInput, workflow_id_for
from ai_res.orchestration.manager_workflows import ManagerIntakeWorkflow, PlanExecutionWorkflow
from ai_res.runtime.manager_activities import assigned_manager_worker
from ai_res.runtime.manager_reasoning import ManagerReasoning, ManagerReasoningInput
from ai_res.runtime.platform_control_client import ManagerHttpPlatform, PlatformControlClient
from tests.integration.temporal.conftest import client, temporal_address  # noqa: F401
from tests.integration.test_candidate_control_tls import certificates
from tests.unit.test_llm_gateway import Rig, profile

from .test_write_api import CONTRACTS, World, conforms, key, send

pytestmark = pytest.mark.postgres


@pytest.mark.temporal
async def test_reconcile_real_terminated_plan_after_ack(iam_world, tmp_path, client: Client):  # noqa: F811
    w = World(iam_world, tmp_path)
    org = iam_world.org_a
    item = PlanItemSpec(id=uuid4(), title="Approved fixture", task_type="ANALYSIS")
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Post-ACK fixture", "ACTIVE"))
        version, digest = await PlanVersionRepository(uow.session).propose(
            org, w.p1, epic, PlanSnapshot(goal="Approved fixture", items=(item,), entries=(item.id,)),
        )
    async with await w.client("analyst") as analyst:
        approved = await send(analyst, "post", f"/plan-versions/{version}/decision",
                              {"decision": "APPROVE", "contentHash": digest.hex(), "approvedItemIds": [str(item.id)]},
                              {**key(), "If-Match": '"v1"'})
        assert approved.status_code == 201
    (approved_event,), = w.rows("SELECT event_id FROM work.plan_version_events WHERE plan_version_id=%s AND event_type='plan.version.approved'", version)
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        operation = await prepare_approved_plan_event(uow.session, approved_event, dispatch_namespace=client.namespace)
    row, = w.rows("""
        SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
        FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
    """, START_DESTINATION, operation)
    request, operation_type = assigned_start_request(OutboxRow(*row))
    observer = TemporalExecutionObserver(client, deadline=timedelta(seconds=2))
    result = await AssignedOperationStarter(client).start(request, operation_type)
    assert await recover_unacknowledged_start(w.services.factory, observer, request, operation_type=operation_type, namespace=client.namespace)
    (correlation,), = w.rows("SELECT correlation_id FROM platform.operation_execution_assignments WHERE operation_id=%s", operation)
    async with UnitOfWork(w.services.factory) as uow:
        assert (await OperationOrchestrationService.acknowledge_start_in(uow, request.operation, correlation)).status == "RUNNING"
    handle = client.get_workflow_handle_for(PlanExecutionWorkflow.run, workflow_id_for(operation), run_id=str(result.run_id))
    await handle.terminate(reason="Disposable Temporal fixture")

    schedule = BoundStartSchedule(scopes=(ReconciliationScope(organization_id=org, project_id=w.p1),),
                                  admitted_operation_types=("PLAN_EXECUTION",), include_post_ack=True,
                                  page_size=1, interval_seconds=1, page_timeout_seconds=4, rpc_timeout_seconds=2,
                                  server_name="fixture", ca_file=tmp_path / "ca", certificate_file=tmp_path / "crt", private_key_file=tmp_path / "key")
    scheduler = BoundStartScheduler(w.services.factory, observer, schedule)
    await scheduler.run_once()
    await scheduler.run_once()
    assert w.rows("SELECT status,problem_ref->>'code' FROM operations.operations WHERE id=%s", operation) == [("FAILED", "WORKFLOW_TERMINATED")]
    assert w.count("work.tasks", "operation_id=%s", operation) == 0
    assert w.count("audit.audit_events", "action=%s AND object_id=%s", "OPERATION_POST_ACK_RECONCILED", operation) == 1


async def test_public_manager_intake_authorizes_then_accepts_once(iam_world, tmp_path):
    w = World(iam_world, tmp_path, manager_dispatch_namespace="fixture")
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Intake", "ACTIVE"))
    path = f"/epics/{epic}/manager-messages"
    valid, foreign = uuid4(), uuid4()
    with iam_world.pg.connect() as connection:
        for project, version in ((w.p1, valid), (w.p2, foreign)):
            source = uuid4()
            with connection.transaction():
                connection.execute(
                    "INSERT INTO sources.sources(id,organization_id,project_id,source_kind,title,current_version_id,last_version_number) "
                    "VALUES (%s,%s,%s,'GIT_REPOSITORY','Fixture',%s,1)", [source, org, project, version],
                )
                connection.execute(
                    "INSERT INTO sources.source_versions(id,organization_id,project_id,source_id,version_number,media_type,size_bytes,"
                    "checksum_sha256,external_ref,provenance,received_at) VALUES (%s,%s,%s,%s,1,'text/plain',3,%s,'{}','{}',now())",
                    [version, org, project, source, bytes(32)],
                )
    body = {"message": "Synthetic user intake", "expectedResponseMode": "CLARIFICATION", "attachmentRefs": [str(valid)]}

    async with await w.client("viewer") as viewer:
        assert (await send(viewer, "post", path, body, key())).status_code == 403
    async with await w.client("analyst", csrf=False) as analyst:
        assert (await send(analyst, "post", path, body, key())).status_code == 403
    async with await w.client("outsider") as outsider:
        assert (await send(outsider, "post", path, body, key())).status_code == 404
    async with await w.client("analyst") as analyst:
        missing = await send(analyst, "post", path, body | {"attachmentRefs": [str(uuid4())]}, key())
        assert missing.status_code == 404
        assert (await send(analyst, "post", path, body | {"attachmentRefs": [str(foreign)]}, key())).status_code == 404
        oversized_refs = {"message": "Fixture", "attachmentRefs": [str(valid)] * 4500}
        assert (await send(analyst, "post", path, oversized_refs, key())).status_code == 422
        headers = key()
        accepted = await send(analyst, "post", path, body, headers)
        assert accepted.status_code == 202, accepted.json()
        op_id = UUID(accepted.json()["id"])
        assert accepted.headers["Location"] == f"/api/v1/operations/{op_id}"
        conforms(accepted.json(), "Operation")
        assert accepted.json()["epicId"] == str(epic) and accepted.json()["status"] == "ACCEPTED"
        assert (await send(analyst, "post", path, body, headers)).json() == accepted.json()
        assert (await send(analyst, "post", path, body | {"message": "Different"}, headers)).status_code == 409
    assert w.count("operations.operations", "id = %s", op_id) == 1
    assert w.count("work.manager_interactions", "operation_id = %s", op_id) == 1
    assert w.count("audit.outbox_events", "aggregate_id = %s AND destination = %s", op_id, START_DESTINATION) == 1
    assert w.count("platform.operation_execution_assignments", "operation_id = %s", op_id) == 1


@pytest.mark.parametrize(("change", "status"), [("grant", 403), ("session", 401), ("deadline", 422)])
async def test_manager_message_checks_authority_and_deadline_while_reading(iam_world, tmp_path, monkeypatch, change, status):
    w = World(iam_world, tmp_path, manager_dispatch_namespace="fixture")
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Intake permissions", "ACTIVE"))
    if change == "deadline":
        monkeypatch.setattr(write_api, "WRITE_BODY_TIMEOUT_SECONDS", 0.01)

    async with await w.client("analyst") as analyst:
        async def body():
            yield b'{"message":'
            if change == "grant":
                with iam_world.pg.connect() as connection:
                    connection.execute(
                        "UPDATE project.project_memberships SET role_code='READ_ONLY_VIEWER',row_version=row_version+1 "
                        "WHERE project_id=%s AND user_id=%s",
                        (w.p1, w.u["analyst"]),
                    )
            elif change == "session":
                assert (await analyst.post("/api/v1/auth/logout")).status_code == 204
            else:
                await asyncio.sleep(0.1)
            yield b'"Synthetic intake"}'

        rejected = await analyst.post(
            f"/api/v1/epics/{epic}/manager-messages", content=body(), headers={**key(), "Content-Type": "application/json"},
        )
        assert rejected.status_code == status
    assert w.count("operations.operations", "project_id = %s AND operation_type = 'MANAGER_MESSAGE'", w.p1) == 0
    assert w.count("work.manager_interactions", "epic_id = %s", epic) == 0
    assert w.count("platform.operation_execution_assignments", "project_id = %s", w.p1) == 0
    assert w.count("audit.outbox_events", "project_id = %s AND destination = %s", w.p1, START_DESTINATION) == 0


@pytest.mark.temporal
async def test_manager_http_to_temporal_and_private_postgres_commands(iam_world, tmp_path, monkeypatch, client: Client):  # noqa: F811
    w = World(iam_world, tmp_path, manager_dispatch_namespace=client.namespace)
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Process fixture", "ACTIVE"))
        other_epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Other Epic fixture", "ACTIVE"))
    message = "private-manager-intake-fixture-canary"
    async with await w.client("analyst") as analyst:
        accepted = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": message}, key())
        assert accepted.status_code == 202
    oid = UUID(accepted.json()["id"])
    def event_for(operation: UUID) -> OutboxRow:
        row, = w.rows("""
            SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
            FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
        """, START_DESTINATION, operation)
        return OutboxRow(*row)

    observer = TemporalExecutionObserver(client, deadline=timedelta(seconds=2))

    async def recover(request: AssignedWorkflowInput, operation_type: str) -> bool:
        return await recover_unacknowledged_start(w.services.factory, observer, request, operation_type=operation_type, namespace=client.namespace)

    async def confirmed(request: AssignedWorkflowInput, operation_type: str) -> bool:
        return await has_confirmed_start(w.services.factory, request, operation_type=operation_type, namespace=client.namespace)

    async def prepare(request: AssignedWorkflowInput, operation_type: str) -> bool:
        return await prepare_assigned_start(w.services.factory, request, operation_type=operation_type, namespace=client.namespace)

    async def start_and_recover(operation: UUID) -> AssignedStart:
        request, operation_type = assigned_start_request(event_for(operation))
        result = await AssignedOperationStarter(client).start(request, operation_type)
        assert await recover(request, operation_type)
        return result

    intake, intake_type = assigned_start_request(event_for(oid))
    started = await AssignedOperationStarter(client).start(intake, intake_type)

    role_factory = create_session_factory(iam_world.engine("ai_res_platform_api"))
    signing = Ed25519PrivateKey.generate()
    ttl = timedelta(seconds=20)
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 4096, 2048)
    platform = create_platform_v2_app(PlatformOperationControl(role_factory, failure_codes=frozenset()),
                                      PlatformCredentialVerifier([signing.public_key()], limits), max_body_bytes=4096, body_timeout_seconds=2)
    host = "platform-g02.test"
    ca, cert, cert_key = certificates(tmp_path / "platform-g02", hostname=host)
    resolve = socket.getaddrinfo

    def resolve_fixture(hostname, *args, **kwargs):
        return resolve("127.0.0.1" if hostname in (host, host.encode()) else hostname, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_fixture)
    model = profile()
    gateway = Rig(model).gw
    gateway.transport.script.append(TransportResult(
        output='{"goal":"Capture workflow","scope":null,"primary_question":"Who owns the work?"}',
        finish_reason=FinishReason.STOP, usage=Usage(3, 7), provider_request_ref="synthetic-fixture",
    ))

    async def approved_fixture_context(reference, text):
        return ManagerReasoningInput(reference.operation.operation_id, model.id, "run-1", "INTERNAL", LLMLimits(100, 10), text)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            platform, host="127.0.0.1", port=port, ssl_certfile=str(cert), ssl_keyfile=str(cert_key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
            proxy_headers=False, access_log=False, log_config=None, log_level="critical", ws="none",
        ))
        serve = asyncio.create_task(server.serve(sockets=[listener]))
        control = PlatformControlClient(f"https://{host}:{port}", ca_file=ca, issuer=PlatformCredentialIssuer(signing, limits), ttl=ttl, timeout_seconds=2)
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
            async with assigned_manager_worker(client, ManagerHttpPlatform(control, approved_fixture_context), ManagerReasoning(gateway)):
                async with asyncio.timeout(12):
                    while not w.count("platform.platform_auth_events", "reason = 'ASSIGNMENT_DENIED'"):
                        await asyncio.sleep(0.03)
                assert not gateway.transport.calls
                assert await recover(intake, intake_type)
                starter_double = AsyncMock(spec=AssignedOperationStarter)
                binder_double = AsyncMock()
                await AssignedTemporalStartPublisher(starter_double, binder_double, confirmed, prepare).publish(event_for(oid))
                starter_double.start.assert_not_awaited()
                binder_double.assert_not_awaited()
                handle = client.get_workflow_handle_for(ManagerIntakeWorkflow.run, workflow_id_for(oid), run_id=str(started.run_id))
                assert (await asyncio.wait_for(handle.result(), timeout=20)).status == "SUCCEEDED"
                assert message not in (await handle.fetch_history()).to_json()

            parent, child, excluded = uuid4(), uuid4(), uuid4()
            graph = PlanSnapshot(goal="Capture workflow", entries=(parent, excluded), items=(
                PlanItemSpec(id=parent, title="Intake", task_type="ANALYSIS"),
                PlanItemSpec(id=child, title="Review intake", task_type="ANALYSIS", predecessors=(parent,)),
                PlanItemSpec(id=excluded, title="Outside approved scope", task_type="ANALYSIS"),
            ))
            schemas = yaml.safe_load((CONTRACTS / "openapi/extensions/manager_proposal.yaml").read_text())["components"]

            def validate_proposal_contract(payload, schema):
                Draft202012Validator({"$ref": f"#/components/schemas/{schema}", "components": schemas},
                                     format_checker=FormatChecker()).validate(payload)

            async with await w.client("analyst") as analyst:
                intake_result = await analyst.get(f"/api/v1/operations/{oid}")
                assert intake_result.status_code == 200 and intake_result.json()["status"] == "SUCCEEDED"
                proposal_id = intake_result.json()["resultRef"]
                proposal_path = f"/manager-proposal-versions/{proposal_id}"
                proposal = await analyst.get(f"/api/v1{proposal_path}")
                assert proposal.status_code == 200 and proposal.headers["ETag"] == '"v1"'
                assert proposal.headers["Cache-Control"] == "no-store"
                validate_proposal_contract(proposal.json(), "ManagerProposalVersion")
                assert message not in proposal.text
                proposal_decision = {"decision": "APPROVE", "contentHash": proposal.json()["contentHash"]}
                validate_proposal_contract(proposal_decision, "ManagerProposalDecisionRequest")
                assert (await send(analyst, "post", f"{proposal_path}/decision", proposal_decision, {**key(), "If-Match": '"v1"'})).status_code == 403
                draft_body = {"expectedVersion": 0, "proposalVersionId": proposal_id, "goal": graph.goal, "entries": [str(item) for item in graph.entries],
                              "items": [{"id": str(item.id), "title": item.title, "taskType": item.task_type,
                                         "predecessors": [str(ref) for ref in item.predecessors]} for item in graph.items]}
                assert (await send(analyst, "post", f"/epics/{epic}/plans", draft_body, key())).status_code == 409
                assert (await send(analyst, "post", f"/epics/{other_epic}/plans", draft_body, key())).status_code == 404

            async with await w.client("viewer") as viewer, await w.client("outsider") as outsider:
                visible_operation = await viewer.get(f"/api/v1/operations/{oid}")
                assert visible_operation.status_code == 200 and visible_operation.json()["resultRef"] is None
                assert (await viewer.get(f"/api/v1{proposal_path}")).status_code == 404
                assert (await send(outsider, "post", f"{proposal_path}/decision", proposal_decision, {**key(), "If-Match": '"v1"'})).status_code == 404
            with w.iam.pg.connect() as db:
                db.execute("INSERT INTO project.project_memberships (id,organization_id,project_id,user_id,role_code) VALUES (%s,%s,%s,%s,'ANALYST')",
                           [uuid4(), org, w.p1, w.u["outsider"]])
            async with await w.client("outsider") as second_analyst:
                oversized = await send(second_analyst, "post", f"{proposal_path}/decision",
                                       {**proposal_decision, "comment": "x" * 1_048_576}, {**key(), "If-Match": '"v1"'})
                assert oversized.status_code == 422
                assert (await send(second_analyst, "post", f"{proposal_path}/decision", proposal_decision, key())).status_code == 428
                assert (await send(second_analyst, "post", f"{proposal_path}/decision", {**proposal_decision, "contentHash": "00" * 32},
                                   {**key(), "If-Match": '"v1"'})).status_code == 412
                headers = {**key(), "If-Match": '"v1"'}
                approved_proposal = await send(second_analyst, "post", f"{proposal_path}/decision", proposal_decision, headers)
                assert approved_proposal.status_code == 201, approved_proposal.json()
                validate_proposal_contract(approved_proposal.json(), "ManagerProposalDecisionReceipt")
                assert (await send(second_analyst, "post", f"{proposal_path}/decision", proposal_decision, headers)).json() == approved_proposal.json()

            async with await w.client("analyst") as analyst:
                assert (await send(analyst, "post", f"/epics/{epic}/plans", {**draft_body, "goal": "Changed goal"}, key())).status_code == 422
                draft = await send(analyst, "post", f"/epics/{epic}/plans", draft_body, key())
                assert draft.status_code == 201, draft.json()
                version = UUID(draft.json()["id"])
                (lineage,), = w.rows("SELECT snapshot->'proposal_origin' FROM work.plan_versions WHERE id=%s", version)
                assert lineage == {"proposal_version_id": proposal_id, "decision_id": approved_proposal.json()["decisionId"],
                                   "content_hash": proposal_decision["contentHash"]}
                assert w.count("governance.plan_version_decisions") == 0
                decision = await send(
                    analyst, "post", f"/plan-versions/{version}/decision",
                    {"decision": "APPROVE", "contentHash": draft.json()["contentHash"], "approvedItemIds": [str(parent), str(child)]},
                    {**key(), "If-Match": draft.headers["ETag"]},
                )
                assert decision.status_code == 201
            event, = w.rows("SELECT event_id FROM work.plan_version_events WHERE plan_version_id=%s AND event_type='plan.version.approved'", version)
            assert w.count("work.plan_executions", "plan_version_id=%s", version) == 0
            approval_file = tmp_path / "plan-approval.json"
            approval_file.write_text(PlanApprovalSchedule(
                scopes=(ReconciliationScope(organization_id=org, project_id=w.p1),),
                interval_seconds=0.05, page_timeout_seconds=2.0, page_size=1,
            ).model_dump_json())
            approval_app = create_app(
                w.settings.model_copy(update={"plan_approval_config_file": approval_file}),
                identity=w.services, plan_dispatch_namespace=client.namespace,
            )
            async with approval_app.router.lifespan_context(approval_app), asyncio.timeout(5):
                while not (prepared := w.rows("SELECT operation_id FROM work.plan_executions WHERE plan_version_id=%s", version)):
                    await asyncio.sleep(0.05)
            (plan,), = prepared
            assert w.count("audit.outbox_events", "aggregate_id=%s AND destination=%s", plan, START_DESTINATION) == 1
            plan_start = await start_and_recover(plan)
            async with assigned_manager_worker(client, ManagerHttpPlatform(control, approved_fixture_context), ManagerReasoning(gateway)):
                async with asyncio.timeout(10):
                    while w.rows("SELECT status FROM operations.operations WHERE id=%s", plan) != [("WAITING_FOR_DEPENDENCY",)]:
                        await asyncio.sleep(0.03)
                async with await w.client("analyst") as analyst:
                    cancelled = await send(analyst, "post", f"/operations/{plan}/cancel", {}, key())
                    assert cancelled.status_code == 202, cancelled.json()
                await OperationCanceller(client).signal(plan)
                plan_handle = client.get_workflow_handle_for(PlanExecutionWorkflow.run, workflow_id_for(plan), run_id=str(plan_start.run_id))
                assert (await asyncio.wait_for(plan_handle.result(), timeout=20)).status == "CANCELLED"
            async with UnitOfWork(w.services.factory) as uow:
                await uow.with_tenant(org, w.p1)
                await PlanVersionRepository(uow.session).propose(org, w.p1, epic, graph)
                assert await prepare_approved_plan_event(uow.session, event[0], dispatch_namespace=client.namespace) == plan
        finally:
            await control.aclose()
            server.should_exit = True
            await asyncio.wait_for(serve, timeout=5)

    assert w.rows("SELECT status FROM operations.operations WHERE id=%s", oid) == [("SUCCEEDED",)]
    assert w.rows("SELECT goal,primary_question FROM work.manager_proposal_versions") == [("Capture workflow", "Who owns the work?")]
    assert w.count("governance.manager_proposal_decisions") == 1
    assert w.count("agents.worker_runs") == 0
    assert w.rows("SELECT title,status FROM work.tasks ORDER BY title") == [("Intake", "PROPOSED"), ("Review intake", "PROPOSED")]
    assert w.count("work.task_dependencies") == 1
    assert len(gateway.transport.calls) == 1


@pytest.mark.temporal
async def test_reconcile_terminated_intake_before_domain_start(iam_world, tmp_path, client: Client):  # noqa: F811
    w = World(iam_world, tmp_path, manager_dispatch_namespace=client.namespace)
    org = iam_world.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Terminated intake", "ACTIVE"))
    async with await w.client("analyst") as analyst:
        response = await send(analyst, "post", f"/epics/{epic}/manager-messages", {"message": "Pre-start failure fixture"}, key())
        assert response.status_code == 202
    operation_id = UUID(response.json()["id"])
    row, = w.rows("""
        SELECT id,event_id,destination,aggregate_type,aggregate_id,aggregate_sequence,event_type,schema_version,envelope,attempt_count,replay_count
        FROM audit.outbox_events WHERE destination=%s AND aggregate_id=%s
    """, START_DESTINATION, operation_id)
    request, operation_type = assigned_start_request(OutboxRow(*row))
    started = await AssignedOperationStarter(client).start(request, operation_type)
    observer = TemporalExecutionObserver(client, deadline=timedelta(seconds=5))
    assert await recover_unacknowledged_start(w.services.factory, observer, request, operation_type=operation_type, namespace=client.namespace)
    schedule = BoundStartSchedule(scopes=(ReconciliationScope(organization_id=org, project_id=w.p1),),
                                  page_size=1, interval_seconds=1, page_timeout_seconds=8, rpc_timeout_seconds=5,
                                  server_name="temporal.test", ca_file=tmp_path / "ca", certificate_file=tmp_path / "cert",
                                  private_key_file=tmp_path / "key")
    scheduler = BoundStartScheduler(w.services.factory, observer, schedule)
    await scheduler.run_once()
    assert w.rows("SELECT status FROM operations.operations WHERE id=%s", operation_id) == [("ACCEPTED",)]
    handle = client.get_workflow_handle(workflow_id_for(operation_id), run_id=str(started.run_id))
    await handle.terminate(reason="fixture")
    await scheduler.run_once()
    await scheduler.run_once()
    assert w.rows("SELECT status,problem_ref FROM operations.operations WHERE id=%s", operation_id) == [
        ("FAILED", {"code": "WORKFLOW_TERMINATED"}),
    ]
    assert w.count("audit.audit_events", "object_id=%s AND action='OPERATION_RECONCILED_FAILURE'", operation_id) == 1
    assert w.count("audit.outbox_events", "aggregate_id=%s AND event_type='operation.failed'", operation_id) == 1
