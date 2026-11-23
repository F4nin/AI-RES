"""Private ar2 Manager and Plan commands under the actual scoped DB principal."""
import json
from asyncio import gather
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg import errors
from sqlalchemy import text

from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.application import platform_manager
from ai_res.application.manager_intake import AuthorizedIntake, persist_manager_intake
from ai_res.application.plan_execution import prepare_plan_execution
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.epics.manager_interactions import ManagerMessage
from ai_res.modules.epics.manager_question_journal import ManagerQuestionJournal
from ai_res.modules.epics.manager_questions import AnswerDisposition, QuestionAnswered, QuestionProposed
from ai_res.modules.events import delivery
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.events.temporal_start import TemporalStartPublisher, assigned_start_request
from ai_res.modules.iam.platform_credentials import (
    PlatformAction,
    PlatformCredentialIssuer,
    PlatformCredentialLimits,
    PlatformCredentialVerifier,
    PlatformRequest,
)
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.modules.operations.execution_authority import OperationAssignments, assigned_input_digest
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanSnapshot, PlanVersionRepository
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.contracts import START_DESTINATION, OperationRef, workflow_id_for
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, Principal
from ai_res.platform.problems import ErrorCode, ProblemError

from .test_repositories import ORG_A, PRJ_A, engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("use_context", [False, True])
async def test_private_manager_can_draft_and_materialize_only_approved_tasks(world, engine_for, monkeypatch, use_context):  # noqa: F811
    actor_id = uuid4()
    with world.connect() as connection:
        connection.execute(
            "INSERT INTO iam.users(id,organization_id,email,email_normalized,display_name) VALUES (%s,%s,'a@example.test','a@example.test','Analyst')",
            [actor_id, ORG_A],
        )
    api = create_session_factory(engine_for("ai_res_api"))
    platform = create_session_factory(engine_for("ai_res_platform_api"))
    signing_key = Ed25519PrivateKey.generate()
    ttl = timedelta(seconds=20)
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 4_096, 2_048)
    issuer = PlatformCredentialIssuer(signing_key, limits)
    app = create_platform_v2_app(PlatformOperationControl(platform, failure_codes=frozenset()),
                                 PlatformCredentialVerifier([signing_key.public_key()], limits), max_body_bytes=4_096, body_timeout_seconds=2)
    idem = IdempotencyService(IdempotencyKeyRing("fixture", {"fixture": b"e" * 32}), timedelta(minutes=5))
    correlation = uuid4()
    intake_run, plan_run = uuid4(), uuid4()
    async with UnitOfWork(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(ORG_A, PRJ_A, "Assigned Epic", "ACTIVE"))
        scope = AuthorizedIntake(ORG_A, PRJ_A, epic, actor_id, correlation)
        previous = await persist_manager_intake(
            uow.session, idem, scope, ManagerMessage("Earlier interaction"), idempotency_key="previous-question",
        )
        unclassified = await persist_manager_intake(
            uow.session, idem, scope, ManagerMessage("Synthetic unclassified answer"), idempotency_key="previous-answer-fixture",
        )
        interaction_ids = dict((await uow.session.execute(text("""
            SELECT operation_id,id FROM work.manager_interactions WHERE operation_id=ANY(:operations)
        """), {"operations": [previous, unclassified]})).all())
        question = uuid4()
        journal = ManagerQuestionJournal(uow.session)
        await journal.record(epic, QuestionProposed(0, question, interaction_ids[previous], "private.topic"), correlation)
        resolved = await journal.record(epic, QuestionAnswered(0, question, interaction_ids[unclassified], AnswerDisposition.ANSWERED), correlation)
        assert resolved.last_sequence == 2
        intake = await persist_manager_intake(
            uow.session, idem, scope, ManagerMessage("Private intake input"),
            idempotency_key="private-intake-case", dispatch_namespace="isolated-test",
        )
        bindings = OperationAssignments(uow.session)

        async def bind(operation_id: UUID, workflow_run: UUID) -> UUID:
            assignment = (await uow.session.execute(text(
                "SELECT id FROM platform.operation_execution_assignments WHERE operation_id=:op",
            ), {"op": operation_id})).scalar_one()
            assert await bindings.bind_run(assignment, operation_id, workflow_run)
            return assignment

        intake_assignment = await bind(intake, intake_run)
        root, child, excluded = uuid4(), uuid4(), uuid4()
        specification = PlanSnapshot(goal="Approved plan", items=(
            PlanItemSpec(id=root, title="Root", task_type="ANALYSIS"),
            PlanItemSpec(id=child, title="Child", task_type="ANALYSIS", predecessors=(root,)),
            PlanItemSpec(id=excluded, title="Excluded", task_type="ANALYSIS"),
        ), entries=(root, excluded))
        plans = PlanVersionRepository(uow.session)
        version, digest = await plans.propose(ORG_A, PRJ_A, epic, specification)
        principal = Principal(user_id=str(actor_id), session_id=str(uuid4()), mfa_verified=True, expires_at=utc_now() + timedelta(minutes=2))
        authorization = PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")
        decision = await plans.decide(ORG_A, PRJ_A, version, digest, principal, authorization,
                                      decision="APPROVE", approved=frozenset({root, child}), comment=None)
        plan = await prepare_plan_execution(uow.session, ORG_A, PRJ_A, version, decision, correlation, dispatch_namespace="isolated-test")
        plan_assignment = await bind(plan, plan_run)

    with world.connect() as connection:
        assignments = connection.execute("""
            SELECT o.id,o.event_id,o.destination,o.aggregate_type,o.aggregate_id,o.aggregate_sequence,o.event_type,o.schema_version,
                   o.envelope,o.attempt_count,o.replay_count,a.input_digest
            FROM audit.outbox_events o JOIN platform.operation_execution_assignments a ON a.operation_id=o.aggregate_id
            WHERE o.destination=%s
        """, [START_DESTINATION]).fetchall()
        assert len(assignments) == 2
        for *row, digest in assignments:
            delivery_row = OutboxRow(*row)
            request, operation_type = assigned_start_request(delivery_row)
            assert request.assignment_id == str(intake_assignment if operation_type == "MANAGER_MESSAGE" else plan_assignment)
            assert assigned_input_digest(request) == bytes(digest)
            with pytest.raises(delivery.PermanentDeliveryError):
                TemporalStartPublisher.request_from(delivery_row)

    with pytest.raises(ProblemError) as legacy_denied:
        await OperationOrchestrationService(api).acknowledge_start(OperationRef(str(intake), str(ORG_A), str(PRJ_A)), correlation)
    assert legacy_denied.value.code is ErrorCode.RESOURCE_NOT_FOUND

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://platform.test") as client:
        async def post(
            oid: UUID, assignment: UUID, run: UUID, action: PlatformAction, *,
            adaptive: bool = False, context: bool = False, path: str | None = None, **extra,
        ):
            body = json.dumps({"workflowId": workflow_id_for(oid), "workflowRunId": str(run), **extra}).encode()
            request = PlatformRequest(action, oid, body, adaptive_input=adaptive, epic_context=context)
            credential = issuer.issue(request, assignment_id=assignment, ttl=ttl)
            return await client.post(path or request.path, content=body, headers={"Authorization": f"Bearer {credential}"})

        read = PlatformAction.READ_MANAGER_INPUT
        save = PlatformAction.RECORD_MANAGER_DRAFT
        prepare = PlatformAction.MATERIALIZE_PLAN_TASKS
        ack = PlatformAction.ACKNOWLEDGE_START
        options = {"goal": "Draft", "scope": None, "primaryQuestion": "Who will own the work?"}
        assert (await post(intake, intake_assignment, intake_run, read)).status_code == 409
        assert (await post(intake, intake_assignment, intake_run, read, adaptive=True)).status_code == 409
        assert (await post(intake, intake_assignment, intake_run, ack)).status_code == 200
        assert (await post(intake, plan_assignment, intake_run, read)).status_code == 404
        assert (await post(intake, intake_assignment, plan_run, read)).status_code == 404
        with monkeypatch.context() as expired_at_lock:
            expired_at_lock.setattr(platform_manager, "utc_now", lambda: utc_now() + ttl)
            assert (await post(intake, intake_assignment, intake_run, read)).status_code == 401
        message = await post(intake, intake_assignment, intake_run, read)
        assert message.status_code == 200, message.json()
        assert message.headers["Cache-Control"] == "no-store"
        assert message.json() == {"operationId": str(intake), "message": "Private intake input"}
        v4 = f"/internal/v4/operations/{intake}/manager-input"
        assert (await post(intake, intake_assignment, intake_run, read, path=v4)).status_code == 401
        assert (await post(intake, intake_assignment, intake_run, read, adaptive=True, path=v4.replace("/v4/", "/v3/"))).status_code == 401
        assert (await post(intake, intake_assignment, plan_run, read, adaptive=True)).status_code == 404
        assert (await post(intake, intake_assignment, intake_run, read, adaptive=True, epicId=str(epic))).status_code == 422
        adaptive = await post(intake, intake_assignment, intake_run, read, adaptive=True)
        assert adaptive.status_code == 200 and adaptive.headers["Cache-Control"] == "no-store"
        assert adaptive.json() == {
            "operationId": str(intake), "message": "Private intake input", "recentQuestions": [], "historyTruncated": False,
        }
        assert (await post(intake, intake_assignment, intake_run, save, **options, approval="APPROVE")).status_code == 422
        issued = None
        if use_context:
            v5 = v4.replace("/v4/", "/v5/")
            assert (await post(intake, intake_assignment, intake_run, read, path=v5)).status_code == 401
            assert (await post(intake, plan_assignment, intake_run, read, context=True)).status_code == 404
            assert (await post(intake, intake_assignment, plan_run, read, context=True)).status_code == 404
            assert (await post(intake, intake_assignment, intake_run, read, context=True, epicId=str(epic))).status_code == 422
            assert (await post(intake, intake_assignment, intake_run, save, context=True, **options)).status_code == 422
            assert (await post(intake, intake_assignment, intake_run, save, context=True,
                               **options, contextVersionId=str(uuid4()))).status_code == 409
            with monkeypatch.context() as expires_during_capture:
                reading = iter((utc_now(), utc_now() + ttl))
                expires_during_capture.setattr(platform_manager, "utc_now", lambda: next(reading))
                assert (await post(intake, intake_assignment, intake_run, read, context=True)).status_code == 401
            with world.connect() as connection:
                assert connection.execute("SELECT count(*) FROM platform.manager_epic_context_versions").fetchone() == (0,)
            first, concurrent = await gather(
                post(intake, intake_assignment, intake_run, read, context=True),
                post(intake, intake_assignment, intake_run, read, context=True),
            )
            assert first.status_code == concurrent.status_code == 200, (first.json(), concurrent.json())
            assert first.headers["Cache-Control"] == "no-store"
            assert first.json() == concurrent.json()
            issued = UUID(first.json()["contextVersionId"])
            assert first.json() == {
                "operationId": str(intake), "message": "Private intake input", "contextVersionId": str(issued),
                "epicState": {"epicVersion": 1, "epicStatus": "ACTIVE", "operationVersion": first.json()["epicState"]["operationVersion"],
                              "operationStatus": "RUNNING", "questionSequence": 2, "hasOpenQuestion": False,
                              "planVersion": 1, "planDecision": "APPROVE", "taskCounts": {}},
            }
            assert first.json()["epicState"]["operationVersion"] > 1
            with world.connect() as connection:
                connection.execute("UPDATE work.epics SET status='PAUSED',row_version=row_version+1 WHERE id=%s", (epic,))
            again = await post(intake, intake_assignment, intake_run, read, context=True)
            assert again.status_code == 200 and again.json() == first.json()
            with world.connect() as connection:
                interaction_id, = connection.execute(
                    "SELECT id FROM work.manager_interactions WHERE operation_id=%s", (intake,),
                ).fetchone()
                assert connection.execute("""
                    SELECT has_function_privilege('ai_res_api','platform.capture_manager_epic_context(uuid,uuid,uuid)','EXECUTE'),
                           has_any_column_privilege('ai_res_platform_api','platform.manager_epic_context_versions','SELECT'),
                           has_any_column_privilege('ai_res_platform_api','work.epics','SELECT')
                """).fetchone() == (False, False, False)
            with world.connect("ai_res_platform_api", autocommit=False) as role:
                for assignment, run in ((None, None), (plan_assignment, plan_run), (intake_assignment, intake_run)):
                    role.execute("""
                        SELECT set_config('app.organization_id',%s,true),set_config('app.project_id',%s,true),
                               set_config('app.platform_operation_id',%s,true),set_config('app.platform_action','manager.record_draft',true),
                               set_config('app.platform_assignment_id',%s,true),set_config('app.platform_workflow_run_id',%s,true)
                    """, (str(ORG_A), str(PRJ_A), str(intake), str(assignment or ""), str(run or "")))
                    with pytest.raises(errors.InsufficientPrivilege):
                        role.execute("""
                            INSERT INTO work.manager_proposal_versions(id,organization_id,project_id,interaction_id,content_hash)
                            VALUES (gen_random_uuid(),%s,%s,%s,%s)
                        """, (ORG_A, PRJ_A, interaction_id, b"p" * 32))
                    role.rollback()
                role.execute("""
                    SELECT set_config('app.organization_id',%s,true),set_config('app.project_id',%s,true),
                           set_config('app.platform_operation_id',%s,true),set_config('app.platform_action','manager.read_input',true),
                           set_config('app.platform_assignment_id',%s,true),set_config('app.platform_workflow_run_id',%s,true)
                """, (str(ORG_A), str(PRJ_A), str(intake), str(intake_assignment), str(intake_run)))
                assert role.execute("SELECT * FROM platform.capture_manager_epic_context(%s,%s,%s)",
                                    (intake, intake_assignment, plan_run)).fetchall() == []
                assert role.execute("SELECT * FROM platform.capture_manager_epic_context(%s,%s,%s)",
                                    (intake, intake_assignment, intake_run)).fetchall() == [(issued, first.json()["epicState"])]
            assert (await post(intake, intake_assignment, intake_run, save, **options)).status_code == 409
            assert (await post(intake, intake_assignment, intake_run, save, context=True,
                               **options, contextVersionId=str(uuid4()))).status_code == 409
            options["contextVersionId"] = str(issued)
        saved = await post(intake, intake_assignment, intake_run, save, context=use_context, **options)
        assert saved.status_code == 200, saved.json()
        assert saved.json()["status"] == "SUCCEEDED"
        assert (await post(intake, intake_assignment, intake_run, save, context=use_context, **options)).json() == saved.json()
        assert (await post(intake, intake_assignment, intake_run, save, context=use_context,
                           **(options | {"goal": "Other"}))).status_code == 409
        if use_context:
            with world.connect() as connection:
                connection.execute("UPDATE platform.operation_execution_assignments SET revoked_at=now() WHERE id=%s", (intake_assignment,))
            assert (await post(intake, intake_assignment, intake_run, read, context=True)).status_code == 404
            assert (await post(intake, intake_assignment, intake_run, save, context=True, **options)).status_code == 404
        assert (await post(plan, plan_assignment, plan_run, ack)).status_code == 200
        assert (await post(plan, plan_assignment, plan_run, prepare, itemIds=[str(excluded)])).status_code == 422
        tasks = await post(plan, plan_assignment, plan_run, prepare)
        assert tasks.status_code == 200, tasks.json()
        assert tasks.json()["status"] == "WAITING_FOR_DEPENDENCY"
        assert (await post(plan, plan_assignment, plan_run, prepare)).json() == tasks.json()

    with world.connect() as connection:
        digest_input = {"goal": "Draft", "scope": None, "primary_question": "Who will own the work?"}
        if issued is not None:
            digest_input["context_version_id"] = str(issued)
        digest = sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode()).digest()
        assert connection.execute("SELECT goal,primary_question,context_version_id,content_hash FROM work.manager_proposal_versions").fetchall() == [
            ("Draft", "Who will own the work?", issued, digest),
        ]
        assert connection.execute("SELECT id,assignment_id,workflow_run_id FROM platform.manager_epic_context_versions").fetchall() == (
            [(issued, intake_assignment, intake_run)] if use_context else []
        )
        disclosure = connection.execute(
            "SELECT object_id,details,correlation_id FROM audit.audit_events WHERE action='MANAGER_INPUT_READ'",
        ).fetchall()
        assert disclosure == [(intake, {}, correlation)] * (6 if use_context else 2)
        assert connection.execute("SELECT count(*) FROM governance.manager_proposal_decisions").fetchone() == (0,)
        assert connection.execute("SELECT title,status FROM work.tasks ORDER BY title").fetchall() == [("Child", "PROPOSED"), ("Root", "PROPOSED")]
        assert connection.execute("SELECT count(*) FROM work.task_dependencies").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM agents.worker_runs").fetchone() == (0,)
