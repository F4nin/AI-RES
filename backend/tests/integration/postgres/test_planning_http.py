"""Public PlanVersion drafts, exact human decisions and the existing createTask shape."""
import asyncio
import json
from uuid import UUID, uuid4

import jsonschema
import pytest
import yaml

from ai_res.api import write_api
from ai_res.application.plan_execution import prepare_plan_execution
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.sessions import RevokeReason
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.tasks.repository import NewEpic, TaskRepository
from ai_res.orchestration.contracts import OperationRef

from .test_write_api import CONTRACTS, World, conforms, event_conforms, key, outbox, send, w  # noqa: F401

pytestmark = pytest.mark.postgres


async def test_public_decision_and_create_task_require_exact_approved_match(w: World):  # noqa: F811
    org = w.iam.org_a
    unique, twin_a, twin_b = uuid4(), uuid4(), uuid4()
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Work fixture", "ACTIVE"))
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p2)
        hidden_epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p2, "Hidden fixture", "ACTIVE"))
    entries = [str(ref) for ref in (unique, twin_a, twin_b)]
    draft = {"expectedVersion": 0, "goal": "Exercise original task command", "entries": entries, "items": [
        {"id": ref, "title": title, "taskType": "ANALYSIS"}
        for ref, title in zip(entries, ("Unique", "Same", "Same"), strict=True)
    ]}
    schemas = yaml.safe_load((CONTRACTS / "openapi/extensions/plan_decision.yaml").read_text())["components"]
    jsonschema.validate(draft, {"$ref": "#/components/schemas/PlanVersionDraftRequest", "components": schemas}, format_checker=jsonschema.FormatChecker())
    draft_path = f"/epics/{epic}/plans"
    async with await w.client(None) as anonymous:
        assert (await send(anonymous, "post", draft_path, draft, key())).status_code == 401
    async with await w.client("viewer") as viewer:
        assert (await send(viewer, "post", draft_path, draft, key())).status_code == 403
    async with await w.client("analyst", csrf=False) as analyst:
        assert (await send(analyst, "post", draft_path, draft, key())).status_code == 403
    async with await w.client("analyst", origin=False) as analyst:
        assert (await send(analyst, "post", draft_path, draft, key())).status_code == 403
    async with await w.client("analyst") as analyst:
        assert (await send(analyst, "post", f"/epics/{hidden_epic}/plans", draft, key())).status_code == 404
        assert (await send(analyst, "post", draft_path, {**draft, "entries": [str(unique)]}, key())).status_code == 422
        assert (await send(analyst, "post", draft_path, {**draft, "goal": "Bad\x00text"}, key())).status_code == 422
        assert (await send(analyst, "post", draft_path, {**draft, "goal": "a" * write_api.MAX_PLAN_DRAFT_BYTES}, key())).status_code == 422
        assert (await send(analyst, "post", draft_path, {name: value for name, value in draft.items() if name != "expectedVersion"}, key())).status_code == 422
        submitted_keys = [key(), key()]
        results = await asyncio.gather(*(send(analyst, "post", draft_path, draft, headers) for headers in submitted_keys))
        assert sorted(result.status_code for result in results) == [201, 412]
        draft_response, headers = next((result, headers) for result, headers in zip(results, submitted_keys, strict=True) if result.status_code == 201)
        assert draft_response.headers["ETag"] == '"v1"'
        assert draft_response.headers["Cache-Control"] == "no-store"
        replay = await send(analyst, "post", draft_path, draft, headers)
        assert replay.status_code == 201 and replay.json() == draft_response.json()
        assert (await send(analyst, "post", draft_path, {**draft, "goal": "Changed goal"}, headers)).status_code == 409
    content = draft_response.json()
    jsonschema.validate(content, {"$ref": "#/components/schemas/PlanVersionSnapshot", "components": schemas}, format_checker=jsonschema.FormatChecker())
    version, digest = UUID(content["id"]), content["contentHash"]
    assert w.count("work.plan_versions") == 1
    assert w.count("governance.plan_version_decisions") == 0
    assert w.count("operations.operations") == 0
    assert w.count("audit.audit_events", "action = 'PLAN_VERSION_PROPOSE' AND object_id = %s", version) == 1
    proposed, = outbox(w, version)
    assert proposed["type"] == "aires.plan.version.proposed.v1"
    assert proposed["data"]["actor"] == {"type": "USER", "id": str(w.u["analyst"])}
    plan_path = f"/api/v1/plan-versions/{version}"
    async with await w.client("analyst") as analyst:
        plan = await analyst.get(plan_path)
        assert plan.status_code == 200
        assert plan.headers["ETag"] == '"v1"'
        assert plan.headers["Cache-Control"] == "no-store"
        assert plan.json() == content
        assert plan.json()["items"][0]["id"] == str(unique)
    async with await w.client("outsider") as outsider:
        assert (await outsider.get(plan_path)).status_code == 404
    decision_path = f"/plan-versions/{version}/decision"
    task_path = f"/epics/{epic}/tasks"
    decision_body = {"decision": "APPROVE", "contentHash": digest, "approvedItemIds": entries}
    async with await w.client("viewer") as viewer:
        unavailable = await send(viewer, "post", decision_path, decision_body, {**key(), "If-Match": '"v1"'})
        assert unavailable.status_code == 403
    async with await w.client("analyst") as analyst:
        assert (await send(analyst, "post", decision_path, decision_body, {**key(), "If-Match": '"v2"'})).status_code == 412
        assert (await send(analyst, "post", decision_path, decision_body, key())).status_code == 428
        headers = {**key(), "If-Match": '"v1"'}
        approved = await send(analyst, "post", decision_path, decision_body, headers)
        assert approved.status_code == 201, approved.json()
        replay = await send(analyst, "post", decision_path, decision_body, headers)
        assert replay.status_code == 201 and replay.json() == approved.json()
        no_execution = await send(analyst, "post", task_path, {"title": "Unique", "taskType": "ANALYSIS"}, key())
        assert no_execution.status_code == 409
    decision = UUID(approved.json()["decisionId"])
    correlation = uuid4()
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        operation = await prepare_plan_execution(uow.session, org, w.p1, version, decision, correlation)
    service = OperationOrchestrationService(w.services.factory)
    await service.acknowledge_start(OperationRef(str(operation), str(org), str(w.p1)), correlation)

    async with await w.client("analyst") as analyst:
        ambiguous = await send(analyst, "post", task_path, {"title": "Same", "taskType": "ANALYSIS"}, key())
        assert ambiguous.status_code == 409
        missing = await send(analyst, "post", task_path, {"title": "Other", "taskType": "ANALYSIS"}, key())
        assert missing.status_code == 409
        body = {"title": "Unique", "taskType": "ANALYSIS"}
        headers = key()
        created = await send(analyst, "post", task_path, body, headers)
        assert created.status_code == 201, created.json()
        assert (await send(analyst, "post", task_path, body, headers)).json() == created.json()
        conforms(created.json(), "Task")
    async with await w.client("outsider") as outsider:
        hidden = await send(outsider, "post", task_path, {"title": "Unique", "taskType": "ANALYSIS"}, key())
        assert hidden.status_code == 404
    task_id = UUID(created.json()["id"])
    assert w.count("work.tasks", "operation_id = %s", operation) == 1
    assert [event["type"] for event in outbox(w, task_id)] == ["aires.task.created.v1"]
    for envelope in outbox(w, task_id) + outbox(w, version):
        event_conforms(envelope)


@pytest.mark.parametrize(("interruption", "expected"), [("session", 401), ("membership", 404), ("deadline", 422)])
async def test_plan_draft_rechecks_authority_after_body_stream(w: World, monkeypatch, interruption, expected):  # noqa: F811
    org = w.iam.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Revocation test", "ACTIVE"))
    item = str(uuid4())
    body = json.dumps({"expectedVersion": 0, "goal": "Goal", "entries": [item], "items": [
        {"id": item, "title": "Analyze", "taskType": "ANALYSIS"},
    ]}).encode()
    if interruption == "deadline":
        monkeypatch.setattr(write_api, "WRITE_BODY_TIMEOUT_SECONDS", 0.01)

    async with await w.client("analyst") as analyst:
        token = analyst.cookies.get(w.settings.session_cookie_name)
        assert token is not None
        session = (await w.services.sessions.authenticate(token)).session
        assert session is not None

        async def stream():
            yield body[:1]
            if interruption == "session":
                assert await w.services.sessions.revoke(org, session.session_id, RevokeReason.ADMIN_REVOKED)
            elif interruption == "membership":
                with w.iam.pg.connect() as connection:
                    connection.execute("UPDATE project.project_memberships SET status='REVOKED', row_version=row_version+1 "
                                       "WHERE project_id=%s AND user_id=%s", [w.p1, session.user_id])
            else:
                await asyncio.Event().wait()
            yield body[1:]

        response = await analyst.post(f"/api/v1/epics/{epic}/plans", content=stream(), headers={**key(), "Content-Type": "application/json"})
        assert response.status_code == expected, response.json()
    assert w.count("work.plan_versions") == 0


@pytest.mark.parametrize("action", ["plan.propose", "plan.decide"])
async def test_plan_write_rechecks_session_after_policy_preflight(w: World, monkeypatch, action):  # noqa: F811
    org = w.iam.org_a
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org, w.p1)
        epic = await TaskRepository(uow.session).create_epic(NewEpic(org, w.p1, "Current planning authority", "ACTIVE"))
    item = str(uuid4())
    draft = {"expectedVersion": 0, "goal": "Current planning authority",
             "items": [{"id": item, "title": "Analyze", "taskType": "ANALYSIS"}], "entries": [item]}
    draft_path = f"/epics/{epic}/plans"
    async with await w.client("analyst") as analyst:
        path, body, headers = draft_path, draft, key()
        if action == "plan.decide":
            prepared = await send(analyst, "post", draft_path, draft, key())
            assert prepared.status_code == 201, prepared.json()
            version = prepared.json()
            path = f"/plan-versions/{version['id']}/decision"
            body = {"decision": "APPROVE", "contentHash": version["contentHash"], "approvedItemIds": [item]}
            headers = {**key(), "If-Match": prepared.headers["ETag"]}

        actor = (await w.services.sessions.authenticate(analyst.cookies[w.settings.session_cookie_name])).session
        assert actor is not None
        original = w.services.enforcer.decide

        async def decide_and_revoke(request, **kwargs):
            decision = await original(request, **kwargs)
            if request.action == action:
                assert await w.services.sessions.revoke(org, actor.session_id, RevokeReason.ADMIN_REVOKED)
            return decision

        monkeypatch.setattr(w.services.enforcer, "decide", decide_and_revoke)
        assert (await send(analyst, "post", path, body, headers)).status_code == 401

    assert w.count("work.plan_versions") == int(action == "plan.decide")
    assert w.count("governance.plan_version_decisions") == 0
    assert w.count("operations.operations") == 0
    assert w.count("audit.outbox_events", "event_type = 'plan.version.approved'") == 0
