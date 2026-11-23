"""Metadata-only native authorization with the actual Platform database role."""
import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text

from ai_res.api.platform_auth_control import register_native_auth_control
from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.application import native_auth_control
from ai_res.application.manager_intake import AuthorizedIntake, persist_manager_intake
from ai_res.application.native_auth_control import NativeAuthControl
from ai_res.application.plan_execution import prepare_plan_execution
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.application.reconcile_operations import prepare_assigned_start
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.epics.manager_interactions import ManagerMessage
from ai_res.modules.iam.platform_credentials import (
    AuthControlAction,
    AuthControlCredentialIssuer,
    AuthControlRequest,
    PlatformAction,
    PlatformCredentialIssuer,
    PlatformCredentialLimits,
    PlatformCredentialVerifier,
    PlatformRequest,
)
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.modules.operations.cancellation import request_cancellation
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanSnapshot, PlanVersionRepository
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.contracts import CONTRACT_VERSION, MANAGER_INTAKE_WORKFLOW, MANAGER_TASK_QUEUE, AssignedWorkflowInput, OperationRef, workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, Principal

from .test_repositories import ORG_A, PRJ_A, engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres


async def test_native_authorization_checks_intent_and_issues_only_exact_bound_receipts(world, engine_for, monkeypatch):  # noqa: F811
    actor = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'a@example.test','a@example.test','Analyst')",
            [actor, ORG_A],
        )
    api = create_session_factory(engine_for("ai_res_api"))
    platform = create_session_factory(engine_for("ai_res_platform_api"))
    ttl = timedelta(seconds=20)
    idem = IdempotencyService(IdempotencyKeyRing("fixture", {"fixture": b"e" * 32}), timedelta(minutes=5))
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Native auth fixture", "ACTIVE"))
        scope = AuthorizedIntake(ORG_A, PRJ_A, epic, actor, uuid4())
        operation = await persist_manager_intake(
            uow.session, idem, scope, ManagerMessage("Synthetic request"),
            idempotency_key="native-auth-fixture", dispatch_namespace="fixture",
        )
        assignment, input_digest = (await uow.session.execute(text(
            "SELECT id,input_digest FROM platform.operation_execution_assignments WHERE operation_id=:operation",
        ), {"operation": operation})).one()

    run = uuid4()
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 4096, 2048)
    native_key, manager_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    signing = AuthControlCredentialIssuer(native_key, limits)
    manager = PlatformCredentialIssuer(manager_key, limits)
    verifier = PlatformCredentialVerifier([manager_key.public_key()], limits, auth_control_keys=[native_key.public_key()])
    audit = PlatformOperationControl(platform, failure_codes=frozenset())
    app = create_platform_v2_app(audit, verifier, max_body_bytes=4096, body_timeout_seconds=2)
    register_native_auth_control(app, NativeAuthControl(platform, audit), audit, verifier, max_bytes=4096, timeout_seconds=2)
    start = {
        "caller": "OUTBOX_DISPATCHER", "assignmentId": str(assignment), "workflowId": workflow_id_for(operation),
        "workflowType": MANAGER_INTAKE_WORKFLOW, "namespace": "fixture", "taskQueue": MANAGER_TASK_QUEUE,
        "workflowContractVersion": 1, "inputSha256": bytes(input_digest).hex(),
    }
    task = {
        "tokenSha256": hashlib.sha256(b"synthetic task").hexdigest(), "principal": "MANAGER_RUNTIME", "namespace": "fixture",
        "queue": MANAGER_TASK_QUEUE, "taskKind": "WORKFLOW", "operationId": str(operation), "workflowRunId": str(run),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://platform.test") as client:
        async def post(action, value, *, credential=None):
            body = json.dumps(value).encode()
            request = AuthControlRequest(action, body)
            minted = credential or signing.issue(request, ttl=ttl)
            response = await client.post(request.path, content=body, headers={"Authorization": f"Bearer {minted}"})
            return response, minted

        authorize = AuthControlAction.AUTHORIZE_START
        assert (await post(authorize, start))[0].status_code == 403
        dispatch = AssignedWorkflowInput(CONTRACT_VERSION, OperationRef(str(operation), str(ORG_A), str(PRJ_A)), str(assignment))
        assert await prepare_assigned_start(api, dispatch, operation_type="MANAGER_MESSAGE", namespace="fixture")
        authorize_reply, token = await post(authorize, start)
        assert authorize_reply.status_code == 204 and authorize_reply.content == b"", authorize_reply.text
        assert (await post(authorize, start, credential=token))[0].status_code == 401
        assert (await post(authorize, start | {"inputSha256": "00" * 32}))[0].status_code == 403
        assert (await post(authorize, start | {"workflowType": "PlanExecutionWorkflow"}))[0].status_code == 403

        manager_request = PlatformRequest(PlatformAction.ACKNOWLEDGE_START, operation, b"{}")
        manager_credential = manager.issue(manager_request, assignment_id=UUID(str(assignment)), ttl=ttl)
        assert (await post(authorize, start, credential=manager_credential))[0].status_code == 401

        describe = AuthControlAction.AUTHORIZE_RECONCILIATION_DESCRIBE
        status_only = AuthControlAction("authorize-bound-status")
        observed = {"operationId": str(operation), "workflowRunId": str(run), "namespace": "fixture"}
        assert (await post(describe, observed))[0].status_code == 403
        assert (await post(status_only, observed))[0].status_code == 403
        assert (await post(describe, observed, credential=manager_credential))[0].status_code == 401
        register, check = AuthControlAction.REGISTER_TASK, AuthControlAction.CHECK_TASK
        assert (await post(register, task))[0].status_code == 403
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            assert await OperationAssignments(uow.session).bind_run(UUID(str(assignment)), operation, run)
        replied, describe_token = await post(describe, observed)
        assert replied.status_code == 204 and replied.content == b""
        assert replied.headers["Cache-Control"] == "no-store"
        assert (await post(describe, observed, credential=describe_token))[0].status_code == 401
        assert (await post(status_only, observed, credential=describe_token))[0].status_code == 401
        for changed in ({"operationId": str(uuid4())}, {"workflowRunId": str(uuid4())}, {"namespace": "elsewhere"}):
            assert (await post(describe, observed | changed))[0].status_code == 403
        revoked_run = uuid4()
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            revoked_operation = await persist_manager_intake(
                uow.session, idem, scope, ManagerMessage("Synthetic revoked request"),
                idempotency_key="native-auth-revoked-fixture", dispatch_namespace="fixture",
            )
            revoked_assignment = (await uow.session.execute(text(
                "SELECT id FROM platform.operation_execution_assignments WHERE operation_id=:operation",
            ), {"operation": revoked_operation})).scalar_one()
            assert await OperationAssignments(uow.session).bind_run(revoked_assignment, revoked_operation, revoked_run)
        revoked_observation = observed | {"operationId": str(revoked_operation), "workflowRunId": str(revoked_run)}
        assert (await post(describe, revoked_observation))[0].status_code == 204
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await uow.session.execute(text("""
                UPDATE platform.operation_execution_assignments SET revoked_at=clock_timestamp() WHERE id=:assignment
            """), {"assignment": revoked_assignment})
        assert (await post(describe, revoked_observation))[0].status_code == 403
        assert (await post(status_only, revoked_observation))[0].status_code == 403
        assert (await post(authorize, start))[0].status_code == 403
        assert (await post(check, task))[0].status_code == 403
        registered, _ = await post(register, task)
        assert registered.status_code == 204, registered.text
        fresh_receipt = task | {"tokenSha256": "7f" * 32}
        expiry_clock = iter((utc_now(), utc_now() + 2 * ttl))
        with monkeypatch.context() as clock:
            clock.setattr(native_auth_control, "utc_now", lambda: next(expiry_clock))
            assert (await post(register, fresh_receipt))[0].status_code == 401
        assert (await post(check, fresh_receipt))[0].status_code == 403
        assert (await post(register, task))[0].status_code == 204
        assert (await post(check, task))[0].status_code == 204
        scoped, _ = await post(AuthControlAction.WORKFLOW_TASK_CONTEXT, task)
        assert scoped.status_code == 200
        assert scoped.json() == {
            "assignmentId": str(assignment), "workflowType": MANAGER_INTAKE_WORKFLOW, "workflowContractVersion": 1,
            "inputSha256": bytes(input_digest).hex(), "operationStatus": "ACCEPTED",
        }
        assert (await post(AuthControlAction.WORKFLOW_TASK_CONTEXT, task | {"tokenSha256": "00" * 32}))[0].status_code == 403
        assert (await post(check, task | {"taskKind": "ACTIVITY"}))[0].status_code == 403
        assert (await post(check, task | {"workflowRunId": str(uuid4())}))[0].status_code == 403
        ack = PlatformRequest(PlatformAction.ACKNOWLEDGE_START, operation, json.dumps({
            "workflowId": workflow_id_for(operation), "workflowRunId": str(run),
        }).encode())
        credential = manager.issue(ack, assignment_id=UUID(str(assignment)), ttl=ttl)
        assert (await client.post(ack.path, content=ack.body, headers={"Authorization": f"Bearer {credential}"})).status_code == 200
        assert (await post(describe, observed))[0].status_code == 403
        status_reply, status_token = await post(status_only, observed)
        assert status_reply.status_code == 204 and status_reply.content == b""
        assert status_reply.headers["Cache-Control"] == "no-store"
        assert (await post(status_only, observed, credential=status_token))[0].status_code == 401
        with world.connect() as connection:
            query = "SELECT count(*) FROM platform.platform_auth_events WHERE reason='EXPIRED_OR_REPLAY' AND action IS NULL"
            before_expiry = connection.execute(query).fetchone()[0]
        with monkeypatch.context() as clock:
            clock.setattr(native_auth_control, "utc_now", lambda: utc_now() + ttl)
            assert (await post(status_only, observed))[0].status_code == 401
        with world.connect() as connection:
            assert connection.execute(query).fetchone()[0] == before_expiry + 1
        for changed in ({"operationId": str(uuid4())}, {"workflowRunId": str(uuid4())}, {"namespace": "elsewhere"}):
            assert (await post(status_only, observed | changed))[0].status_code == 403
        plan_run = uuid4()
        item = PlanItemSpec(id=uuid4(), title="Fixture", task_type="ANALYSIS")
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            plans = PlanVersionRepository(uow.session)
            plan_version, digest = await plans.propose(
                ORG_A, PRJ_A, epic, PlanSnapshot(goal="Fixture", items=(item,), entries=(item.id,)),
            )
            approver = Principal(user_id=str(actor), session_id=str(uuid4()), mfa_verified=True, expires_at=utc_now() + ttl)
            policy = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="fixture")
            decision = await plans.decide(ORG_A, PRJ_A, plan_version, digest, approver, policy, decision="APPROVE",
                                          approved=frozenset({item.id}), comment=None)
            plan = await prepare_plan_execution(uow.session, ORG_A, PRJ_A, plan_version, decision, uuid4(), dispatch_namespace="fixture")
            plan_assignment = (await uow.session.execute(text(
                "SELECT id FROM platform.operation_execution_assignments WHERE operation_id=:operation",
            ), {"operation": plan})).scalar_one()
            assert await OperationAssignments(uow.session).bind_run(plan_assignment, plan, plan_run)
        plan_observed = observed | {"operationId": str(plan), "workflowRunId": str(plan_run)}
        assert (await post(describe, plan_observed))[0].status_code == 403
        assert (await post(status_only, plan_observed))[0].status_code == 204
        assert (await post(status_only, plan_observed | {"workflowRunId": str(run)}))[0].status_code == 403
        plan_ack = PlatformRequest(PlatformAction.ACKNOWLEDGE_START, plan, json.dumps({
            "workflowId": workflow_id_for(plan), "workflowRunId": str(plan_run),
        }).encode())
        plan_token = manager.issue(plan_ack, assignment_id=plan_assignment, ttl=ttl)
        assert (await client.post(plan_ack.path, content=plan_ack.body, headers={"Authorization": f"Bearer {plan_token}"})).status_code == 200
        assert (await post(status_only, plan_observed))[0].status_code == 204
        cancel = AuthControlAction.AUTHORIZE_BOUND_CANCEL
        intent = plan_observed | {"assignmentId": str(plan_assignment)}
        assert (await post(cancel, intent))[0].status_code == 403
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await request_cancellation(uow.session, plan, actor_id=actor, correlation_id=uuid4())
        replied, cancel_token = await post(cancel, intent)
        assert replied.status_code == 204 and replied.content == b""
        assert replied.headers["Cache-Control"] == "no-store"
        assert (await post(cancel, intent, credential=cancel_token))[0].status_code == 401
        assert (await post(cancel, intent, credential=manager_credential))[0].status_code == 401
        for changed in ({"assignmentId": str(assignment)}, {"operationId": str(operation)},
                        {"workflowRunId": str(run)}, {"namespace": "elsewhere"}):
            assert (await post(cancel, intent | changed))[0].status_code == 403
        async with UnitOfWork(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await uow.session.execute(text("UPDATE platform.operation_execution_assignments SET revoked_at=clock_timestamp() WHERE id=:id"),
                                      {"id": plan_assignment})
        assert (await post(cancel, intent))[0].status_code == 403
    with world.connect() as connection:
        assert connection.execute("SELECT count(*) FROM platform.task_issuance_receipts").fetchone() == (1,)
        assert connection.execute(
            "SELECT action, COUNT(DISTINCT correlation_id) FROM platform.platform_auth_events WHERE reason='AUTHORIZED' GROUP BY action ORDER BY action",
        ).fetchall() == [
            ("AUTHORIZE_BOUND_CANCEL", 1), ("AUTHORIZE_BOUND_STATUS", 3), ("AUTHORIZE_RECONCILIATION_DESCRIBE", 2), ("AUTHORIZE_START", 1),
            ("CHECK_TASK", 2), ("REGISTER_TASK", 2),
        ]
        assert connection.execute("SELECT status FROM operations.operations WHERE id=%s", [operation]).fetchone() == ("RUNNING",)
