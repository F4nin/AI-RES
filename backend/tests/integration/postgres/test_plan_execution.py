"""Exact-version approval and idempotent Task materialization in PostgreSQL."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ai_res.api.app import create_app
from ai_res.application import plan_execution
from ai_res.application.plan_execution import create_approved_task, prepare_approved_plan_page, prepare_plan_execution
from ai_res.application.reconcile_operations import TerminalWorkflowEvidence, apply_reconciled_failure, reconcile_bound_start_page
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState
from ai_res.modules.operations.repository import OperationRepository
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanSnapshot, PlanVersionRepository
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.contracts import OperationRef, workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.config import ConfigError
from ai_res.platform.ports import Effect, PolicyDecision, Principal, ServiceIdentity, ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.telemetry import build_tracer_provider

from .test_repositories import ORG_A, ORG_B, PRJ_A, PRJ_B, engine_for, world  # noqa: F401
from .test_write_api import World

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize(("scenario", "expected"), [
    ("empty_failed", "FAILED"), ("partial_failed", "RUNNING"), ("empty_completed", "RUNNING"),
    ("all_materialized", "RUNNING"), ("revoked", "RUNNING"), ("foreign", "RUNNING"), ("version_changed", "CANCEL_REQUESTED"),
    ("cancel_empty", "CANCELLED"), ("cancel_partial", "CANCEL_REQUESTED"), ("cancel_then_failed", "FAILED"),
    ("unrequested_cancel", "RUNNING"), ("audit_unavailable", "RUNNING"), ("requeued", "QUEUED"), ("concurrent", "FAILED"),
])
async def test_reconcile_plan_after_ack_requires_exact_local_effects(world, engine_for, monkeypatch, scenario, expected):  # noqa: F811
    person = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'rc@example.test','rc@example.test','Reviewer')",
            [person, ORG_A],
        )
    now = utc_now()
    actor = Principal(user_id=str(person), session_id=str(uuid4()), mfa_verified=True, expires_at=now + timedelta(minutes=1))
    policy = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")
    first, second = uuid4(), uuid4()
    snapshot = PlanSnapshot(goal="Reconcile approved branch", items=(
        PlanItemSpec(id=first, title="First", task_type="ANALYSIS"),
        PlanItemSpec(id=second, title="Second", task_type="ANALYSIS", predecessors=(first,)),
    ), entries=(first,))
    run, correlation = uuid4(), uuid4()
    factory = create_session_factory(engine_for("ai_res_api"))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Reconcile Plan", "ACTIVE"))
        repo = PlanVersionRepository(uow.session)
        version, digest = await repo.propose(ORG_A, PRJ_A, epic, snapshot)
        decision = await repo.decide(ORG_A, PRJ_A, version, digest, actor, policy, decision="APPROVE",
                                     approved=frozenset({first, second}), comment=None)
        operation = await prepare_plan_execution(uow.session, ORG_A, PRJ_A, version, decision, correlation, dispatch_namespace="fixture")
        assignment = (await uow.session.execute(text(
            "SELECT id FROM platform.operation_execution_assignments WHERE operation_id=:id",
        ), {"id": operation})).scalar_one()
        assert await OperationAssignments(uow.session).bind_run(assignment, operation, run)
    ref = OperationRef(str(operation), str(ORG_A), str(PRJ_A))
    async with UnitOfWork(factory) as uow:
        assert (await OperationOrchestrationService.acknowledge_start_in(uow, ref, correlation)).status == "RUNNING"

    async def request_cancel(uow):
        operations = OperationRepository(uow.session)
        row = await operations.get(operation)
        assert row
        await operations.transition(row, "CANCEL_REQUESTED", EventSpec(
            "operation.cancel_requested", 1, "USER", correlation, (DOMAIN_DESTINATION,),
            from_status="RUNNING", to_status="CANCEL_REQUESTED", data={"operationType": "PLAN_EXECUTION"},
        ), cancel_requested_at=utc_now())

    if scenario.startswith("cancel_"):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            if scenario == "cancel_partial":
                await create_approved_task(uow.session, operation, first)
            await request_cancel(uow)

    if scenario == "requeued":
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await create_approved_task(uow.session, operation, first)
            operations = OperationRepository(uow.session)
            for status, event in (("WAITING_FOR_DEPENDENCY", "operation.waiting_for_dependency"), ("QUEUED", "operation.queued")):
                row = await operations.get(operation)
                assert row
                await operations.transition(row, status, EventSpec(event, 1, "SYSTEM", correlation, (DOMAIN_DESTINATION,),
                                                                    from_status=row.status, to_status=status))
            row = await operations.get(operation)
            assert row
            evidence = TerminalWorkflowEvidence(assignment, operation, workflow_id_for(operation), run, row.row_version, ExecutionState.FAILED)
            assert not await apply_reconciled_failure(uow.session, evidence, admitted_types=frozenset({"PLAN_EXECUTION"}))

    class Observer:
        async def observe(self, request):
            assert (request.operation_id, request.assignment_id, request.workflow_run_id, request.namespace) == (operation, assignment, run, "fixture")
            if scenario in {"partial_failed", "all_materialized", "revoked", "version_changed"}:
                async with UnitOfWork(factory) as uow:
                    await uow.with_tenant(ORG_A, PRJ_A)
                    if scenario in {"partial_failed", "all_materialized"}:
                        await create_approved_task(uow.session, operation, first)
                        if scenario == "all_materialized":
                            await create_approved_task(uow.session, operation, second)
                    elif scenario == "revoked":
                        await uow.session.execute(text("UPDATE platform.operation_execution_assignments SET revoked_at=now() WHERE id=:id"),
                                                  {"id": assignment})
                    else:
                        await request_cancel(uow)
            outcomes = {"empty_completed": ExecutionState.COMPLETED, "all_materialized": ExecutionState.COMPLETED,
                        "cancel_empty": ExecutionState.CANCELLED, "cancel_partial": ExecutionState.CANCELLED,
                        "unrequested_cancel": ExecutionState.CANCELLED}
            return ExecutionObservation(request.assignment_id, outcomes.get(scenario, ExecutionState.FAILED))

    scope = (ORG_B, PRJ_B) if scenario == "foreign" else (ORG_A, PRJ_A)
    params = {"organization_id": scope[0], "project_id": scope[1], "admitted_types": frozenset({"PLAN_EXECUTION"}),
              "page_size": 1, "include_post_ack": True}
    corrected = expected in {"FAILED", "CANCELLED"}
    if scenario == "requeued":
        page = await reconcile_bound_start_page(factory, Observer(), organization_id=ORG_A, project_id=PRJ_A,
                                               admitted_types=frozenset({"PLAN_EXECUTION"}), page_size=1)
        assert (page.checked, page.corrected) == (0, 0)
    if scenario == "audit_unavailable":
        from ai_res.application import reconcile_effects

        async def broken_audit(self, record):
            assert record.action == "OPERATION_POST_ACK_RECONCILED"
            raise SQLAlchemyError("fixture audit unavailable")

        monkeypatch.setattr(reconcile_effects.SqlAuditWriter, "write", broken_audit)
        with pytest.raises(SQLAlchemyError, match="fixture audit unavailable"):
            await reconcile_bound_start_page(factory, Observer(), **params)
    elif scenario == "concurrent":
        pages = await asyncio.gather(*(reconcile_bound_start_page(factory, Observer(), **params) for _ in range(2)))
        assert sum(page.corrected for page in pages) == 1
    else:
        exporter = InMemorySpanExporter()
        with build_tracer_provider(exporter).get_tracer(__name__).start_as_current_span("fixture"):
            page = await reconcile_bound_start_page(factory, Observer(), **params)
        assert (page.checked, page.corrected) == (int(scenario != "foreign"), int(corrected))
        if scenario == "all_materialized":
            effect, = [event.attributes for span in exporter.get_finished_spans() for event in span.events
                       if event.name == "operation.reconciliation.effect"]
            assert effect == {"operation_type": "PLAN_EXECUTION", "outcome": "PLAN_MATERIALIZED"}
    if corrected:
        repeat = await reconcile_bound_start_page(factory, Observer(), organization_id=ORG_A, project_id=PRJ_A,
                                                 admitted_types=frozenset({"PLAN_EXECUTION"}), page_size=1, include_post_ack=True)
        assert (repeat.checked, repeat.corrected) == (0, 0)
    with world.connect() as connection:
        assert connection.execute("SELECT status FROM operations.operations WHERE id=%s", [operation]).fetchone() == (expected,)
        assert connection.execute("SELECT count(*) FROM work.plan_item_tasks WHERE operation_id=%s", [operation]).fetchone() == (
            {"partial_failed": 1, "cancel_partial": 1, "all_materialized": 2, "requeued": 1}.get(scenario, 0),
        )
        assert connection.execute("""
            SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_POST_ACK_RECONCILED' AND object_id=%s
        """, [operation]).fetchone() == (int(corrected),)
        assert connection.execute("""
            SELECT count(*) FROM audit.outbox_events WHERE aggregate_id=%s AND event_type IN ('operation.failed','operation.cancelled')
        """, [operation]).fetchone() == (int(corrected),)


async def test_exact_partial_decision_and_plan_task_lineage(world, engine_for):  # noqa: F811
    person_id = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'p@example.test','p@example.test','Planner')",
            [person_id, ORG_A],
        )
    actor = Principal(user_id=str(person_id), session_id=str(uuid4()), mfa_verified=True, expires_at=utc_now() + timedelta(minutes=2))
    policy = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")
    first, child, other = uuid4(), uuid4(), uuid4()
    snapshot = PlanSnapshot(goal="Constrained fixture", items=(
        PlanItemSpec(id=first, title="Intake", task_type="ANALYSIS"),
        PlanItemSpec(id=child, title="Review", task_type="ANALYSIS", predecessors=(first,)),
        PlanItemSpec(id=other, title="Independent", task_type="ANALYSIS"),
    ), entries=(first, other))
    factory = create_session_factory(engine_for("ai_res_api"))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Plan fixture", "ACTIVE"))
        repository = PlanVersionRepository(uow.session)
        version, digest = await repository.propose(ORG_A, PRJ_A, epic, snapshot)
        service = ServiceIdentity(name=ServiceName.MANAGER_RUNTIME, audience=ServiceName.API, expires_at=actor.expires_at)
        for caller, permission in (
            (service, policy),
            (replace(actor, expires_at=utc_now() - timedelta(seconds=1)), policy),
            (actor, replace(policy, effect=Effect.APPROVAL_REQUIRED)),
        ):
            with pytest.raises(ProblemError) as denied:
                await repository.decide(
                    ORG_A, PRJ_A, version, digest, caller, permission, decision="APPROVE", approved=frozenset({first}), comment=None,
                )
            assert denied.value.code is ErrorCode.ACCESS_DENIED
        with pytest.raises(ProblemError) as stale:
            await repository.decide(
                ORG_A, PRJ_A, version, b"q" * 32, actor, policy, decision="APPROVE", approved=frozenset({first}), comment=None,
            )
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        with pytest.raises(ProblemError) as partial:
            await repository.decide(
                ORG_A, PRJ_A, version, digest, actor, policy, decision="APPROVE", approved=frozenset({child}), comment=None,
            )
        assert partial.value.code is ErrorCode.VALIDATION_ERROR
        ref = await repository.decide(
            ORG_A, PRJ_A, version, digest, actor, policy, decision="APPROVE", approved=frozenset({first, child}), comment=None,
        )
        corr = uuid4()
        operation = await prepare_plan_execution(uow.session, ORG_A, PRJ_A, version, ref, corr)
        assert await prepare_plan_execution(uow.session, ORG_A, PRJ_A, version, ref, corr) == operation
        with pytest.raises(ProblemError) as waiting:
            await create_approved_task(uow.session, operation, first)
        assert waiting.value.code is ErrorCode.ACCESS_DENIED

    await OperationOrchestrationService(factory).acknowledge_start(OperationRef(str(operation), str(ORG_A), str(PRJ_A)), corr)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ProblemError) as unapproved:
            await create_approved_task(uow.session, operation, other)
        assert unapproved.value.code is ErrorCode.ACCESS_DENIED
        with pytest.raises(ProblemError) as early:
            await create_approved_task(uow.session, operation, child)
        assert early.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
        root_task = await create_approved_task(uow.session, operation, first)
        assert await create_approved_task(uow.session, operation, first) == root_task
        child_task = await create_approved_task(uow.session, operation, child)

    with world.connect() as connection:
        assert connection.execute("SELECT task_id,depends_on_task_id FROM work.task_dependencies").fetchone() == (child_task, root_task)
        assert connection.execute("SELECT count(*) FROM work.tasks WHERE operation_id=%s", [operation]).fetchone() == (2,)


async def test_committed_approval_page_is_scoped_and_idempotent(world, engine_for, monkeypatch):  # noqa: F811
    person_id = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'page@example.test','page@example.test','Planner')",
            [person_id, ORG_A],
        )
    actor = Principal(user_id=str(person_id), session_id=str(uuid4()), mfa_verified=True, expires_at=utc_now() + timedelta(minutes=2))
    policy = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")
    item = uuid4()
    snapshot = PlanSnapshot(goal="Page fixture", entries=(item,), items=(PlanItemSpec(id=item, title="Intake", task_type="ANALYSIS"),))
    factory = create_session_factory(engine_for("ai_res_api"))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repository = PlanVersionRepository(uow.session)
        approved = []
        for name in ("first", "second", "third", "superseded", "rejected"):
            epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, name, "ACTIVE"))
            version, digest = await repository.propose(ORG_A, PRJ_A, epic, snapshot)
            decision = await repository.decide(
                ORG_A, PRJ_A, version, digest, actor, policy, decision="REJECT" if name == "rejected" else "APPROVE",
                approved=frozenset() if name == "rejected" else frozenset({item}), comment=None,
            )
            if name in {"first", "second", "third"}:
                approved.append(decision)
            elif name == "superseded":
                await repository.propose(ORG_A, PRJ_A, epic, snapshot.model_copy(update={"goal": "New proposal"}))
        assert await prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=1) == 0

    assert await prepare_approved_plan_page(factory, ORG_B, PRJ_B, dispatch_namespace="fixture", page_size=1) == 0

    second_started = asyncio.Event()
    original = plan_execution.prepare_approved_plan_event
    committed = Mock()
    monkeypatch.setattr(plan_execution, "_APPROVALS_PREPARED", committed)
    called = []

    async def block_second(session, event_id, *, dispatch_namespace):
        called.append(event_id)
        if len(called) == 2:
            second_started.set()
            await asyncio.Future()
        return await original(session, event_id, dispatch_namespace=dispatch_namespace)

    with monkeypatch.context() as patch:
        patch.setattr(plan_execution, "prepare_approved_plan_event", block_second)
        poll = asyncio.create_task(prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=3))
        try:
            await asyncio.wait_for(second_started.wait(), timeout=5)
        finally:
            poll.cancel()
            with pytest.raises(asyncio.CancelledError):
                await poll
    with world.connect() as connection:
        assert connection.execute("SELECT count(*) FROM work.plan_executions").fetchone() == (1,)
    committed.add.assert_called_once_with(1)

    async def unavailable_audit(_writer, _record):
        raise RuntimeError("fixture audit store unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(plan_execution.SqlAuditWriter, "write", unavailable_audit)
        with pytest.raises(RuntimeError, match="fixture audit store unavailable"):
            await prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=1)
    with world.connect() as connection:
        assert connection.execute("SELECT count(*) FROM work.plan_executions").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM operations.operations WHERE operation_type='PLAN_EXECUTION'").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM audit.outbox_events WHERE destination='orchestration.operation-start'").fetchone() == (1,)
    committed.add.assert_called_once_with(1)

    assert await prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=1) == 1
    assert sum(await asyncio.gather(*(
        prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=1) for _ in range(2)
    ))) == 1
    assert await prepare_approved_plan_page(factory, ORG_A, PRJ_A, dispatch_namespace="fixture", page_size=1) == 0

    with world.connect() as connection:
        assert {row[0] for row in connection.execute("SELECT decision_id FROM work.plan_executions")} == set(approved)
        assert connection.execute("""
            SELECT count(*) FROM audit.outbox_events o
            JOIN work.plan_executions p ON p.operation_id=o.aggregate_id
            JOIN work.plan_version_events e ON e.plan_version_id=p.plan_version_id AND e.event_type='plan.version.approved'
            WHERE o.destination='orchestration.operation-start' AND o.envelope->'data'->>'causationId'=e.event_id::text
        """).fetchone() == (3,)
        assert connection.execute("""
            SELECT count(*), count(DISTINCT object_id) FROM audit.audit_events
            WHERE action='PLAN_EXECUTION_PREPARED' AND actor_type='SYSTEM'
        """).fetchone() == (3, 3)


async def test_backend_starts_approval_consumer_only_with_admitted_dispatch(iam_world, tmp_path):
    fixture = World(iam_world, tmp_path)
    org, project = iam_world.org_a, fixture.p1
    actor = Principal(user_id=str(fixture.u["analyst"]), session_id=str(uuid4()), mfa_verified=True, expires_at=utc_now() + timedelta(minutes=2))
    item = uuid4()
    snapshot = PlanSnapshot(goal="Backend lifecycle", entries=(item,), items=(PlanItemSpec(id=item, title="Intake", task_type="ANALYSIS"),))
    async with UnitOfWork(fixture.services.factory) as uow:
        await uow.with_tenant(org, project)
        repository = PlanVersionRepository(uow.session)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, project, "Lifecycle fixture", "ACTIVE"))
        version, digest = await repository.propose(org, project, epic, snapshot)
        decision = await repository.decide(
            org, project, version, digest, actor, PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test"),
            decision="APPROVE", approved=frozenset({item}), comment=None,
        )
    config = tmp_path / "plan-approval.json"
    config.write_text(f"""{{
        "scopes":[{{"organization_id":"{org}","project_id":"{project}"}}],
        "interval_seconds":0.05,"page_timeout_seconds":2.0,"page_size":1
    }}""")
    settings = fixture.settings.model_copy(update={"plan_approval_config_file": config})
    blocked = create_app(settings, identity=fixture.services, manager_dispatch_namespace="fixture")
    with pytest.raises(ConfigError, match="requires separate Plan dispatch admission"):
        async with blocked.router.lifespan_context(blocked):
            pytest.fail("consumer started without dispatch admission")
    assert fixture.count("work.plan_executions") == 0

    app = create_app(settings, identity=fixture.services, plan_dispatch_namespace="fixture")
    async with app.router.lifespan_context(app), asyncio.timeout(5):
        while not fixture.count("work.plan_executions", "decision_id=%s", decision):
            await asyncio.sleep(0.05)
    assert fixture.count("work.plan_executions") == 1
