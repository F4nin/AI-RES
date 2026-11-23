"""Private control authority derives tenant from the exact bound workflow execution."""
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from psycopg.errors import InsufficientPrivilege

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.operations.cancellation import request_cancellation
from ai_res.modules.operations.execution_authority import OperationAssignments, assigned_input_digest
from ai_res.modules.operations.repository import OperationRepository
from ai_res.orchestration.contracts import MANAGER_INTAKE_WORKFLOW, workflow_id_for

from .test_repositories import ORG_A, ORG_B, PRJ_A, PRJ_B, engine_for, new_operation, spec, world  # noqa: F401

pytestmark = pytest.mark.postgres


async def test_platform_resolves_only_server_owned_binding_and_actions(world, engine_for):  # noqa: F811
    api = create_session_factory(engine_for("ai_res_api"))
    platform = create_session_factory(engine_for("ai_res_platform_api"))
    operation = replace(new_operation(), operation_type="MANAGER_MESSAGE")
    workflow = workflow_id_for(operation.id)
    workflow_run = uuid4()
    ack = PlatformAction.ACKNOWLEDGE_START
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await OperationRepository(uow.session).create(operation, spec())
        request = await OperationAssignments(uow.session).register(operation.id, namespace="isolated-test", actions=frozenset({ack}))
        assignment = UUID(request.assignment_id)
    with world.connect() as connection:
        saved_type, saved_digest = connection.execute(
            "SELECT workflow_type,input_digest FROM platform.operation_execution_assignments WHERE id=%s", [assignment],
        ).fetchone()
        assert saved_type == MANAGER_INTAKE_WORKFLOW
        assert bytes(saved_digest) == assigned_input_digest(request)
    async with UnitOfWork(platform) as uow:
        assert await OperationAssignments(uow.session).resolve(assignment, operation.id, workflow, workflow_run, ack) is None
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_B, PRJ_B)
        assert not await OperationAssignments(uow.session).bind_run(assignment, operation.id, workflow_run)
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        bindings = OperationAssignments(uow.session)
        assert await bindings.bind_run(assignment, operation.id, workflow_run)
        assert not await bindings.bind_run(assignment, operation.id, uuid4())
    async with UnitOfWork(platform) as uow:
        bindings = OperationAssignments(uow.session)
        exact = await bindings.resolve(assignment, operation.id, workflow, workflow_run, ack)
        assert exact is not None and exact.operation.organization_id == str(ORG_A)
        for args in (
            (uuid4(), operation.id, workflow, workflow_run, ack),
            (assignment, uuid4(), workflow, workflow_run, ack),
            (assignment, operation.id, "other", workflow_run, ack),
            (assignment, operation.id, workflow, uuid4(), ack),
            (assignment, operation.id, workflow, workflow_run, PlatformAction.RECORD_FAILURE),
        ):
            assert await bindings.resolve(*args) is None
    with world.connect("ai_res_platform_api") as connection:
        with pytest.raises(InsufficientPrivilege):
            connection.execute("SELECT id FROM platform.operation_execution_assignments")
        with pytest.raises(InsufficientPrivilege):
            connection.execute("UPDATE platform.operation_execution_assignments SET workflow_run_id = %s", [uuid4()])


async def test_ar2_controller_consumes_nonce_checks_assignment_and_appends_once(world, engine_for):  # noqa: F811
    import json
    from datetime import timedelta

    import httpx
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ai_res.api.platform_v2 import create_platform_v2_app
    from ai_res.application.platform_control import PlatformOperationControl
    from ai_res.modules.iam.platform_credentials import (
        PlatformCredentialIssuer,
        PlatformCredentialLimits,
        PlatformCredentialVerifier,
        PlatformRequest,
    )

    api = create_session_factory(engine_for("ai_res_api"))
    platform = create_session_factory(engine_for("ai_res_platform_api"))
    operation = replace(new_operation(), operation_type="MANAGER_MESSAGE")
    workflow = workflow_id_for(operation.id)
    workflow_run = uuid4()
    ack = PlatformAction.ACKNOWLEDGE_START
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await OperationRepository(uow.session).create(operation, spec())
        bindings = OperationAssignments(uow.session)
        request = await bindings.register(operation.id, namespace="isolated-test", actions=frozenset({ack}))
        assignment = UUID(request.assignment_id)
        assert await bindings.bind_run(assignment, operation.id, workflow_run)

    key = Ed25519PrivateKey.generate()
    ttl = timedelta(seconds=20)
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=2), 512, 2048)
    signer = PlatformCredentialIssuer(key, limits)
    control = PlatformOperationControl(platform, failure_codes=frozenset())
    app = create_platform_v2_app(control, PlatformCredentialVerifier([key.public_key()], limits), max_body_bytes=512, body_timeout_seconds=2)
    payload = json.dumps({"workflowId": workflow, "workflowRunId": str(workflow_run)}).encode()
    request = PlatformRequest(ack, operation.id, payload)

    def headers(binding):
        return {"Authorization": "Bearer " + signer.issue(request, assignment_id=binding, ttl=ttl),
                "Content-Type": "application/json"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://platform.test") as client:
        wrong = await client.post(request.path, headers=headers(uuid4()), content=payload)
        assert wrong.status_code == 404
        altered = await client.post(request.path + "?unexpected=1", headers=headers(assignment), content=payload)
        assert altered.status_code == 401
        authorized = headers(assignment)
        first = await client.post(request.path, headers=authorized, content=payload)
        assert first.status_code == 200, first.json()
        assert first.json()["status"] == "RUNNING"
        replay = await client.post(request.path, headers=authorized, content=payload)
        assert replay.status_code == 401
        semantic_retry = await client.post(request.path, headers=headers(assignment), content=payload)
        assert semantic_retry.status_code == 200 and semantic_retry.json() == first.json()

    with world.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM operations.operation_events WHERE operation_id=%s", [operation.id],
        ).fetchone() == (3,)
        assert connection.execute(
            "SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_START_ACKNOWLEDGED' AND object_id=%s", [operation.id],
        ).fetchone() == (1,)
        events = connection.execute("SELECT reason FROM platform.platform_auth_events").fetchall()
        assert set(events) == {("ASSIGNMENT_DENIED",), ("INVALID_CREDENTIAL",), ("EXPIRED_OR_REPLAY",)}


async def test_reconcile_closed_workflow_from_accepted_exact_binding(world, engine_for):  # noqa: F811
    from ai_res.application.reconcile_operations import TerminalWorkflowEvidence, apply_reconciled_failure
    from ai_res.modules.operations.reconciliation import ExecutionState

    api = create_session_factory(engine_for("ai_res_api"))
    operation = replace(new_operation(), operation_type="MANAGER_MESSAGE")
    workflow_run = uuid4()
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        current, _ = await OperationRepository(uow.session).create(operation, spec())
        bindings = OperationAssignments(uow.session)
        request = await bindings.register(operation.id, namespace="isolated-test", actions=frozenset({PlatformAction.RECORD_FAILURE}))
        assignment = UUID(request.assignment_id)
        assert await bindings.bind_run(assignment, operation.id, workflow_run)
    observation = TerminalWorkflowEvidence(
        assignment, operation.id, workflow_id_for(operation.id), workflow_run, current.row_version, ExecutionState.FAILED,
    )
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        args = {"admitted_types": frozenset({"MANAGER_MESSAGE"})}
        assert not await apply_reconciled_failure(uow.session, replace(observation, workflow_run_id=uuid4()), **args)
        assert not await apply_reconciled_failure(uow.session, replace(observation, expected_operation_version=9), **args)
        assert await apply_reconciled_failure(uow.session, observation, **args)
        assert not await apply_reconciled_failure(uow.session, observation, **args)
    with world.connect() as connection:
        assert connection.execute("SELECT status FROM operations.operations WHERE id=%s", [operation.id]).fetchone() == ("FAILED",)
        assert connection.execute(
            "SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_RECONCILED_FAILURE' AND object_id=%s", [operation.id],
        ).fetchone() == (1,)


@pytest.mark.parametrize("operation_type", ["MANAGER_MESSAGE", "PLAN_EXECUTION"])
@pytest.mark.parametrize("authority", ["current", "revoked_during_observation", "missing_cancel_action"])
async def test_reconcile_confirmed_cancellation_before_ack(world, engine_for, operation_type, authority):  # noqa: F811
    from sqlalchemy import text

    from ai_res.application.reconcile_operations import reconcile_bound_start_page
    from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState

    factory = create_session_factory(engine_for("ai_res_api"))
    operation = replace(new_operation(), operation_type=operation_type)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await OperationRepository(uow.session).create(operation, spec())
        assignments = OperationAssignments(uow.session)
        action = PlatformAction.ACKNOWLEDGE_START if authority == "missing_cancel_action" else PlatformAction.CONFIRM_CANCELLATION
        request = await assignments.register(operation.id, namespace="isolated-test", actions=frozenset({action}))
        assignment, run = UUID(request.assignment_id), uuid4()
        assert await assignments.bind_run(assignment, operation.id, run)
        pending = await request_cancellation(uow.session, operation.id, actor_id=uuid4(), correlation_id=operation.correlation_id)
        assert pending.status == "CANCEL_REQUESTED"

    class Observer:
        def __init__(self, state, assignment_id=assignment, *, revoke=False):
            self.state, self.assignment_id, self.revoke = state, assignment_id, revoke

        async def observe(self, binding):
            assert (binding.assignment_id, binding.workflow_run_id) == (assignment, run)
            if self.revoke:
                async with UnitOfWork(factory) as uow:
                    await uow.with_tenant(ORG_A, PRJ_A)
                    await uow.session.execute(text("""
                        UPDATE platform.operation_execution_assignments SET revoked_at=clock_timestamp() WHERE id=:assignment
                    """), {"assignment": assignment})
            return ExecutionObservation(self.assignment_id, self.state)

    scope = {"organization_id": ORG_A, "project_id": PRJ_A, "admitted_types": frozenset({operation_type}), "page_size": 1}
    for uncertain in (Observer(ExecutionState.ABSENT), Observer(ExecutionState.COMPLETED), Observer(ExecutionState.CANCELLED, uuid4())):
        page = await reconcile_bound_start_page(factory, uncertain, **scope)
        assert (page.checked, page.corrected) == (1, 0)
    successful = authority == "current"
    confirmed = Observer(ExecutionState.CANCELLED, revoke=authority == "revoked_during_observation")
    assert (await reconcile_bound_start_page(factory, confirmed, **scope)).corrected == int(successful)
    assert (await reconcile_bound_start_page(factory, Observer(ExecutionState.CANCELLED), **scope)).checked == int(
        authority == "missing_cancel_action"
    )
    with world.connect() as connection:
        expected_status = "CANCELLED" if successful else "CANCEL_REQUESTED"
        assert connection.execute("SELECT status,started_at FROM operations.operations WHERE id=%s", [operation.id]).fetchone() == (
            expected_status, None,
        )
        assert connection.execute("""
            SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_CANCELLATION_CONFIRMED' AND object_id=%s
        """, [operation.id]).fetchone() == (int(successful),)


@pytest.mark.parametrize(("scenario", "expected", "observations"), [
    ("failed", True, 1),
    ("unavailable", False, 1),
    ("completed", False, 1),
    ("wrong_assignment", False, 1),
    ("revoked_during_rpc", False, 1),
    ("acknowledged_during_rpc", False, 1),
    ("foreign_tenant", False, 0),
    ("outside_allowlist", False, 0),
])
async def test_reconcile_bound_start_observes_then_rechecks_current_authority(world, engine_for, scenario, expected, observations):  # noqa: F811
    import asyncio

    from sqlalchemy import text

    from ai_res.application.observe_operations import BoundExecutionObservationRequest
    from ai_res.application.reconcile_operations import reconcile_bound_start
    from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
    from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState

    factory = create_session_factory(engine_for("ai_res_api"))
    operation = replace(new_operation(), operation_type="MANAGER_MESSAGE")
    run_id = uuid4()
    namespace = "isolated-test"
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await OperationRepository(uow.session).create(operation, spec())
        bindings = OperationAssignments(uow.session)
        request = await bindings.register(operation.id, namespace=namespace, actions=frozenset({PlatformAction.ACKNOWLEDGE_START}))
        assignment = UUID(request.assignment_id)
        assert await bindings.bind_run(assignment, operation.id, run_id)

    calls = []

    class Observer:
        async def observe(self, binding: BoundExecutionObservationRequest) -> ExecutionObservation:
            calls.append(binding)
            assert binding == BoundExecutionObservationRequest(assignment, operation.id, MANAGER_INTAKE_WORKFLOW, run_id, namespace)
            # A lifecycle change commits during the RPC, before the reconciler attempts any write.
            async with asyncio.timeout(3):
                if scenario == "revoked_during_rpc":
                    async with UnitOfWork(factory) as uow:
                        await uow.with_tenant(ORG_A, PRJ_A)
                        await uow.session.execute(text("""
                            UPDATE platform.operation_execution_assignments SET revoked_at=clock_timestamp() WHERE id=:id
                        """), {"id": assignment})
                elif scenario == "acknowledged_during_rpc":
                    async with UnitOfWork(factory) as uow:
                        state = await OperationOrchestrationService.acknowledge_start_in(uow, request.operation, operation.correlation_id)
                        assert state.status == "RUNNING"
            state = {"unavailable": ExecutionState.UNAVAILABLE, "completed": ExecutionState.COMPLETED}.get(scenario, ExecutionState.FAILED)
            return ExecutionObservation(uuid4() if scenario == "wrong_assignment" else assignment, state)

    ref = replace(request.operation, organization_id=str(ORG_B), project_id=str(PRJ_B)) if scenario == "foreign_tenant" else request.operation
    admitted = frozenset({"PLAN_EXECUTION" if scenario == "outside_allowlist" else "MANAGER_MESSAGE"})
    assert await reconcile_bound_start(factory, Observer(), ref, admitted_types=admitted) is expected
    assert len(calls) == observations
    if expected:
        assert not await reconcile_bound_start(factory, Observer(), ref, admitted_types=admitted)
        assert len(calls) == observations

    with world.connect() as connection:
        status = "FAILED" if expected else "RUNNING" if scenario == "acknowledged_during_rpc" else "ACCEPTED"
        assert connection.execute("SELECT status FROM operations.operations WHERE id=%s", [operation.id]).fetchone() == (status,)
        assert connection.execute("""
            SELECT reason_code,correlation_id FROM audit.audit_events
            WHERE action='OPERATION_RECONCILED_FAILURE' AND object_id=%s
        """, [operation.id]).fetchall() == ([("WORKFLOW_FAILED", operation.correlation_id)] if expected else [])


async def test_reconcile_bound_start_page_is_bounded_and_tenant_scoped(world, engine_for):  # noqa: F811
    from sqlalchemy import text

    from ai_res.application.observe_operations import BoundExecutionObservationRequest
    from ai_res.application.reconcile_operations import reconcile_bound_start_page
    from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState

    factory = create_session_factory(engine_for("ai_res_api"))
    sibling_project = uuid4()
    with world.connect() as connection:
        connection.execute("""
            INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'sibling','GREENFIELD')
        """, [sibling_project, ORG_A])
    candidates = [
        (1, ORG_A, PRJ_A, "MANAGER_MESSAGE", "bound"),
        (2, ORG_A, PRJ_A, "PLAN_EXECUTION", "bound"),
        (3, ORG_A, PRJ_A, "MANAGER_MESSAGE", "unbound"),
        (4, ORG_A, PRJ_A, "MANAGER_MESSAGE", "revoked"),
        (5, ORG_B, PRJ_B, "MANAGER_MESSAGE", "bound"),
        (6, ORG_A, PRJ_A, "MANAGER_MESSAGE", "bound"),
        (7, ORG_A, PRJ_A, "MANAGER_MESSAGE", "queued"),
        (8, ORG_A, sibling_project, "MANAGER_MESSAGE", "bound"),
        (9, ORG_A, PRJ_A, "MANAGER_MESSAGE", "cancellation_requested"),
    ]
    for number, org, project, operation_type, binding in candidates:
        operation = replace(new_operation(org, project), id=UUID(int=number), operation_type=operation_type)
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(org, project)
            repository = OperationRepository(uow.session)
            row, _ = await repository.create(operation, spec())
            assignments = OperationAssignments(uow.session)
            request = await assignments.register(
                operation.id, namespace="isolated-test", actions=frozenset({PlatformAction.ACKNOWLEDGE_START}),
            )
            assignment = UUID(request.assignment_id)
            if binding != "unbound":
                assert await assignments.bind_run(assignment, operation.id, uuid4())
            if binding == "revoked":
                await uow.session.execute(text("""
                    UPDATE platform.operation_execution_assignments SET revoked_at=clock_timestamp() WHERE id=:id
                """), {"id": assignment})
            if binding == "queued":
                await repository.transition(row, "QUEUED", spec("operation.queued", from_status="ACCEPTED", to_status="QUEUED"),
                                            workflow_id=workflow_id_for(operation.id))
            if binding == "cancellation_requested":
                cancelled = await request_cancellation(uow.session, operation.id, actor_id=uuid4(), correlation_id=operation.correlation_id)
                assert cancelled.status == "CANCEL_REQUESTED"

    calls = []

    class Observer:
        async def observe(self, binding: BoundExecutionObservationRequest) -> ExecutionObservation:
            calls.append(binding.operation_id)
            state = ExecutionState.UNAVAILABLE if binding.operation_id == UUID(int=1) else ExecutionState.FAILED
            return ExecutionObservation(binding.assignment_id, state)

    arguments = {"organization_id": ORG_A, "project_id": PRJ_A, "admitted_types": frozenset({"MANAGER_MESSAGE"}), "page_size": 2}
    observer = Observer()
    first = await reconcile_bound_start_page(factory, observer, **arguments)
    assert (first.checked, first.corrected, first.next_after) == (2, 1, UUID(int=6))
    assert calls == [UUID(int=1), UUID(int=6)]
    second = await reconcile_bound_start_page(factory, observer, after=first.next_after, **arguments)
    assert (second.checked, second.corrected, second.next_after) == (2, 2, None)
    retry = await reconcile_bound_start_page(factory, observer, **arguments)
    assert (retry.checked, retry.corrected, retry.next_after) == (1, 0, None)
    assert calls == [UUID(int=1), UUID(int=6), UUID(int=7), UUID(int=9), UUID(int=1)]

    with world.connect() as connection:
        assert connection.execute("SELECT id FROM operations.operations WHERE status='FAILED' ORDER BY id").fetchall() == [
            (UUID(int=6),), (UUID(int=7),), (UUID(int=9),),
        ]
        assert connection.execute("""
            SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_RECONCILED_FAILURE'
        """).fetchone() == (3,)


async def test_page_timeout_defers_slow_run_and_preserves_progress(world, engine_for):  # noqa: F811
    import asyncio

    from ai_res.application.observe_operations import BoundExecutionObservationRequest
    from ai_res.application.reconcile_operations import BoundStartPage, reconcile_bound_start_page
    from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState

    factory = create_session_factory(engine_for("ai_res_api"))
    first, slow, later = (UUID(int=number) for number in (1, 2, 3))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        for operation_id in (first, slow, later):
            operation = replace(new_operation(), id=operation_id, operation_type="MANAGER_MESSAGE")
            await OperationRepository(uow.session).create(operation, spec())
            assignments = OperationAssignments(uow.session)
            assignment = await assignments.register(operation_id, namespace="isolated-test", actions=frozenset({PlatformAction.ACKNOWLEDGE_START}))
            assert await assignments.bind_run(UUID(assignment.assignment_id), operation_id, uuid4())

    calls = []
    recovered = False

    class Observer:
        async def observe(self, binding: BoundExecutionObservationRequest) -> ExecutionObservation:
            calls.append(binding.operation_id)
            if binding.operation_id == slow and not recovered:
                await asyncio.Future()
            return ExecutionObservation(binding.assignment_id, ExecutionState.FAILED)

    observer = Observer()
    scope = {"organization_id": ORG_A, "project_id": PRJ_A, "admitted_types": frozenset({"MANAGER_MESSAGE"}), "page_size": 2}
    partial = await reconcile_bound_start_page(factory, observer, **scope, timeout_seconds=1)
    assert partial == BoundStartPage(2, 1, slow, timed_out=True)
    assert await reconcile_bound_start_page(factory, observer, **scope, after=partial.next_after) == BoundStartPage(1, 1, None)
    recovered = True
    assert await reconcile_bound_start_page(factory, observer, **scope) == BoundStartPage(1, 1, None)
    assert calls == [first, slow, later, slow]
    with world.connect() as connection:
        assert connection.execute("""
            SELECT object_id FROM audit.audit_events WHERE action='OPERATION_RECONCILED_FAILURE' ORDER BY object_id
        """).fetchall() == [(first,), (slow,), (later,)]
