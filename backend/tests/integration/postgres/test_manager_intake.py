"""Authorized intake, exact attachment refs and metadata-only transaction output."""
from dataclasses import asdict, replace
from datetime import timedelta
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from ai_res.application.manager_intake import AuthorizedIntake, persist_manager_intake
from ai_res.application.platform_manager import execute_manager_command
from ai_res.application.reconcile_operations import reconcile_bound_start
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.epics.manager_interactions import ManagerInteractionRepository, ManagerMessage, ResponseMode
from ai_res.modules.epics.manager_proposals import HumanDecision, ManagerProposalRepository, ProposalContent
from ai_res.modules.epics.manager_question_journal import ManagerQuestionJournal
from ai_res.modules.epics.manager_questions import AnswerDisposition, ManagerQuestionState, QuestionAnswered, QuestionProposed
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.modules.operations.execution_authority import OperationAssignments, PlatformExecution
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.operations.reconciliation import ExecutionObservation, ExecutionState
from ai_res.modules.readmodel.manager_epic import load_assigned_epic_metadata, load_manager_epic_state
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanSnapshot, PlanVersionRepository
from ai_res.modules.tasks.repository import NewEpic, NewTask, TaskRepository
from ai_res.orchestration.contracts import OperationRef
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, Principal, ServiceIdentity, ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.telemetry import build_tracer_provider

from .test_repositories import ORG_A, ORG_B, PRJ_A, PRJ_B, engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("draft_commits", [False, True])
async def test_post_ack_manager_joins_current_draft_without_retrying_external_effect(world, engine_for, draft_commits):  # noqa: F811
    user, run, correlation = uuid4(), uuid4(), uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) "
            "VALUES (%s,%s,'reconcile@example.test','reconcile@example.test','Analyst')",
            [user, ORG_A],
        )
    factory = create_session_factory(engine_for("ai_res_api"))
    idem = IdempotencyService(IdempotencyKeyRing("fixture", {"fixture": b"f" * 32}), timedelta(minutes=5))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Manager Reconciliation", "ACTIVE"))
        scope = AuthorizedIntake(ORG_A, PRJ_A, epic, user, correlation)
        operation = await persist_manager_intake(uow.session, idem, scope, ManagerMessage("Synthetic intake"),
                                                 idempotency_key="post-ack-manager", dispatch_namespace="fixture")
        assignment = (await uow.session.execute(text("SELECT id FROM platform.operation_execution_assignments WHERE operation_id=:id"),
                                                {"id": operation})).scalar_one()
        assert await OperationAssignments(uow.session).bind_run(assignment, operation, run)
    ref = OperationRef(str(operation), str(ORG_A), str(PRJ_A))
    async with UnitOfWork(factory) as uow:
        assert (await OperationOrchestrationService.acknowledge_start_in(uow, ref, correlation)).status == "RUNNING"

    class Observer:
        async def observe(self, request):
            assert (request.operation_id, request.assignment_id, request.workflow_run_id) == (operation, assignment, run)
            if draft_commits:
                async with UnitOfWork(factory) as uow:
                    await execute_manager_command(uow, PlatformExecution(ref, correlation), PlatformAction.RECORD_MANAGER_DRAFT,
                                                  ProposalContent("Synthetic draft", None, None), expires_at=utc_now() + timedelta(minutes=1))
            return ExecutionObservation(assignment, ExecutionState.FAILED)

    exporter = InMemorySpanExporter()
    tracer = build_tracer_provider(exporter).get_tracer(__name__)
    with tracer.start_as_current_span("fixture"):
        assert not await reconcile_bound_start(factory, Observer(), ref, admitted_types=frozenset({"MANAGER_MESSAGE"}), include_post_ack=True)
    effect, = [event.attributes for span in exporter.get_finished_spans() for event in span.events
               if event.name == "operation.reconciliation.effect"]
    assert effect == {"operation_type": "MANAGER_MESSAGE", "outcome": "DRAFT_COMMITTED" if draft_commits else "DOMAIN_OUTCOME_REQUIRED"}
    if not draft_commits:
        assert not await reconcile_bound_start(factory, Observer(), ref, admitted_types=frozenset({"MANAGER_MESSAGE"}), include_post_ack=True)
    with world.connect() as connection:
        expected = "SUCCEEDED" if draft_commits else "RUNNING"
        assert connection.execute("SELECT status FROM operations.operations WHERE id=%s", [operation]).fetchone() == (expected,)
        assert connection.execute("SELECT count(*) FROM work.manager_proposal_versions").fetchone() == (int(draft_commits),)
        assert connection.execute("SELECT count(*) FROM audit.audit_events WHERE action='OPERATION_POST_ACK_RECONCILED'").fetchone() == (0,)
        observations = connection.execute(
            "SELECT reason_code,details->>'observedStatus' FROM audit.audit_events WHERE action='OPERATION_RECONCILIATION_REQUIRED'",
        ).fetchall()
        assert observations == ([] if draft_commits else [("DOMAIN_OUTCOME_REQUIRED", "FAILED")])


async def test_manager_intake_atomic_idempotent_and_metadata_only(world, engine_for):  # noqa: F811
    user, other_project = uuid4(), uuid4()
    approver_id = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO project.projects(id,organization_id,name,project_type) VALUES (%s,%s,'Other project','GREENFIELD')",
            [other_project, ORG_A],
        )
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'a@example.test','a@example.test','Analyst')",
            [user, ORG_A],
        )
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'r@example.test','r@example.test','Reviewer')",
            [approver_id, ORG_A],
        )
    factory = create_session_factory(engine_for("ai_res_api"))
    idem = IdempotencyService(IdempotencyKeyRing("fixture", {"fixture": b"f" * 32}), timedelta(minutes=5))
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Fixture Epic", "ACTIVE"))
        empty_state = await load_manager_epic_state(uow.session, epic)
        assert empty_state is not None
        assert empty_state.intake is empty_state.proposal is empty_state.plan is None
        assert (empty_state.question_sequence, empty_state.open_question_id, empty_state.task_counts) == (0, None, ())
    scope = AuthorizedIntake(ORG_A, PRJ_A, epic, user, uuid4())
    message = ManagerMessage("fixture canary: untrusted message", expected_response_mode=ResponseMode.CLARIFICATION)

    async def accept(value: ManagerMessage, key: str):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            return await persist_manager_intake(uow.session, idem, scope, value, idempotency_key=key)

    key = "manager-intake-fixture-1"
    operation = await accept(message, key)
    assert await accept(message, key) == operation
    with pytest.raises(ProblemError) as conflict:
        await accept(replace(message, text="other payload"), key)
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    with pytest.raises(ProblemError) as missing:
        await accept(replace(message, attachment_versions=(uuid4(),)), "manager-intake-fixture-2")
    assert missing.value.code is ErrorCode.RESOURCE_NOT_FOUND
    with world.connect() as connection:
        assert connection.execute("SELECT count(*) FROM operations.operations WHERE operation_type='MANAGER_MESSAGE'").fetchone() == (1,)
        interaction = connection.execute("SELECT id FROM work.manager_interactions WHERE operation_id=%s", [operation]).fetchone()[0]
        events = connection.execute("SELECT envelope FROM audit.outbox_events").fetchall()
        assert [(item["type"], item["data"]["interactionId"]) for item, in events if "interactionId" in item["data"]] == [
            ("aires.manager.interaction.received.v1", str(interaction)),
        ]
        assert "fixture canary" not in repr(events)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        stored = await ManagerInteractionRepository(uow.session).get(interaction)
        assert stored is not None and stored.message == message and stored.author_id == user
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_B, PRJ_B)
        assert await ManagerInteractionRepository(uow.session).get(interaction) is None


    policy = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")
    expiry = utc_now() + timedelta(minutes=1)
    reviewer = Principal(user_id=str(approver_id), session_id=str(uuid4()), mfa_verified=True, expires_at=expiry)
    author = replace(reviewer, user_id=str(user))
    manager = ServiceIdentity(name=ServiceName.MANAGER_RUNTIME, audience=ServiceName.API, expires_at=expiry)
    content = ProposalContent("Proposed goal", None, "Who owns the process?")
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = ManagerProposalRepository(uow.session)
        draft = await repo.propose(ORG_A, PRJ_A, interaction, content)
        assert await repo.propose(ORG_A, PRJ_A, interaction, content) == draft
        with pytest.raises(ProblemError) as denied:
            await repo.record_human_decision(ORG_A, PRJ_A, draft, HumanDecision.APPROVE, manager, policy,
                                             require_separation=True, comment=None)
        assert denied.value.code is ErrorCode.ACCESS_DENIED
        with pytest.raises(ProblemError) as self_approval:
            await repo.record_human_decision(ORG_A, PRJ_A, draft, HumanDecision.APPROVE, author, policy,
                                             require_separation=True, comment=None)
        assert self_approval.value.code is ErrorCode.ACCESS_DENIED
        stale = replace(draft, content_hash=b"q" * 32)
        with pytest.raises(ProblemError) as mismatched:
            await repo.record_human_decision(ORG_A, PRJ_A, stale, HumanDecision.APPROVE, reviewer, policy,
                                             require_separation=True, comment=None)
        assert mismatched.value.code is ErrorCode.VERSION_CONFLICT
        assert await repo.record_human_decision(ORG_A, PRJ_A, draft, HumanDecision.APPROVE, reviewer, policy,
                                                require_separation=True, comment=None)
    with world.connect() as connection:
        result = connection.execute(
            "SELECT proposal_version_id,content_hash,approver_id,decision FROM governance.manager_proposal_decisions"
        ).fetchall()
        assert result == [(draft.id, draft.content_hash, approver_id, "APPROVE")]

    second_operation = await accept(ManagerMessage("Unknown"), "manager-intake-fixture-3")
    with world.connect() as connection:
        second = connection.execute("SELECT id FROM work.manager_interactions WHERE operation_id=%s", [second_operation]).fetchone()[0]
    proposed = QuestionProposed(0, draft.id, interaction, "project.owner")
    answered = QuestionAnswered(0, draft.id, second, AnswerDisposition.UNKNOWN)
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        journal = ManagerQuestionJournal(uow.session)
        initial = await journal.record(epic, proposed, scope.correlation_id)
        assert initial.primary == replace(proposed, sequence=1)
        projection = await load_manager_epic_state(uow.session, epic)
        assert projection is not None
        assert (projection.question_sequence, projection.open_question_id) == (1, draft.id)
        assert await journal.record(epic, proposed, scope.correlation_id) == initial
        with pytest.raises(ProblemError) as still_waiting:
            await journal.record(epic, replace(proposed, interaction_id=second, question_id=uuid4()), scope.correlation_id)
        assert still_waiting.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
        resolved = await journal.record(epic, answered, scope.correlation_id)
        assert resolved.resolved[0].answer == replace(answered, sequence=2)

    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        rebuilt = await ManagerQuestionJournal(uow.session).load(epic)
        assert rebuilt.state == ManagerQuestionState.rebuild(rebuilt.events) == resolved
        item = PlanItemSpec(id=uuid4(), title="Synthetic plan item", task_type="ANALYSIS")
        plans = PlanVersionRepository(uow.session)
        version, digest = await plans.propose(ORG_A, PRJ_A, epic, PlanSnapshot(goal="Synthetic goal", items=(item,), entries=(item.id,)))
        await plans.decide(ORG_A, PRJ_A, version, digest, reviewer, policy, decision="APPROVE", approved=frozenset({item.id}), comment=None)
        task = await TaskRepository(uow.session).create_task(NewTask(ORG_A, PRJ_A, operation, epic, "ANALYSIS", "Synthetic task", "PROPOSED", "USER"))
        expected = await load_manager_epic_state(uow.session, epic)
        assert expected is not None and expected.intake is not None and expected.proposal is not None and expected.plan is not None
        assert (expected.intake.interaction_id, expected.intake.operation_id) == (second, second_operation)
        assert (expected.proposal.version_id, expected.proposal.interaction_id, expected.proposal.decision) == (draft.id, interaction, "APPROVE")
        assert (expected.plan.version_id, expected.plan.version_number, expected.plan.decision) == (version, 1, "APPROVE")
        assert (expected.question_sequence, expected.open_question_id, expected.task_counts) == (2, None, ((task.status, 1),))
        assert expected.epic_version == projection.epic_version
        assert expected.snapshot_version != projection.snapshot_version
        assert expected.snapshot_version.startswith("1:") and len(expected.snapshot_version) == 66
        serialized = repr(asdict(expected))
        assert "fixture canary" not in serialized and "Who owns the process?" not in serialized and "project.owner" not in serialized
        # The original Operation's assignment receives its own state even while a newer intake exists.
        assigned = await load_assigned_epic_metadata(uow.session, epic, operation)
        latest = await load_assigned_epic_metadata(uow.session, epic, second_operation)
        assert assigned is not None and latest is not None and assigned.version != latest.version
        assert assigned.state.question_sequence == 2 and assigned.state.has_open_question is False
        assert assigned.state.plan_decision == "APPROVE" and assigned.state.task_counts == ((task.status, 1),)
        assert not {"goal", "scope", "open_question_id", "message", "answer"} & set(asdict(assigned.state))
        assert await load_assigned_epic_metadata(uow.session, epic, uuid4()) is None
    before_start = assigned
    ref = OperationRef(str(operation), str(ORG_A), str(PRJ_A))
    async with UnitOfWork(factory) as uow:
        assert (await OperationOrchestrationService.acknowledge_start_in(uow, ref, scope.correlation_id)).status == "RUNNING"
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        assert await load_manager_epic_state(uow.session, epic) == expected
        assigned = await load_assigned_epic_metadata(uow.session, epic, operation)
        assert assigned is not None and assigned.version != before_start.version
        assert assigned.state.operation_status == "RUNNING"
        assert assigned.state.operation_version > before_start.state.operation_version
        assert latest.state.operation_status == "ACCEPTED"
        assert await load_assigned_epic_metadata(uow.session, epic, second_operation) == latest
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_B, PRJ_B)
        assert (await ManagerQuestionJournal(uow.session).load(epic)).events == ()
        assert await load_manager_epic_state(uow.session, epic) is None
        assert await load_assigned_epic_metadata(uow.session, epic, operation) is None
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, other_project)
        assert await load_manager_epic_state(uow.session, epic) is None
        assert await load_assigned_epic_metadata(uow.session, epic, operation) is None
    async with UnitOfWork(factory) as uow:
        assert await load_manager_epic_state(uow.session, epic) is None
        assert await load_assigned_epic_metadata(uow.session, epic, operation) is None
    with world.connect() as connection:
        event, = connection.execute(
            "SELECT envelope FROM audit.outbox_events WHERE event_type='manager.question.proposed'",
        ).fetchall()
        assert event[0]["data"]["questionId"] == str(draft.id)
        assert "project.owner" not in repr(event) and "Who owns the process?" not in repr(event)
        # The metadata projection works with the Epic content and Proposal tables denied.
        connection.execute("REVOKE SELECT ON work.epics, work.manager_proposal_versions FROM ai_res_api_group")
        connection.execute("GRANT SELECT (id,organization_id,project_id,row_version,status) ON work.epics TO ai_res_api_group")
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        assert await load_assigned_epic_metadata(uow.session, epic, operation) == assigned
