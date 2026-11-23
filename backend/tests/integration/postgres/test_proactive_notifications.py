"""ADR-182 delivery and HTTP authorization under real PostgreSQL roles."""
import asyncio
import base64
import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import jsonschema
import pytest
import yaml
from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ai_res.api import notification_api
from ai_res.api.app import create_app
from ai_res.application import notification_delivery
from ai_res.application.notification_delivery import NotificationSchedule, NotificationScheduler, publish_digest, publish_mandatory
from ai_res.application.proactive_messages import NotificationScope
from ai_res.db.session import UnitOfWork
from ai_res.modules.epics.manager_proposals import ManagerProposalRepository, ProposalContent
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.repository import OperationRepository
from ai_res.platform.clock import utc_now
from ai_res.platform.problems import ErrorCode, ProblemError

from .conftest import Pg, run_audit
from .test_write_api import OAS, World, key

pytestmark = pytest.mark.postgres
OVERLAY = Path(__file__).resolve().parents[4] / "contracts/openapi/extensions/proactive_notifications.yaml"


def _assert_contract(body: Any, schema: str) -> None:
    schemas = {**OAS["components"]["schemas"], **yaml.safe_load(OVERLAY.read_text())["components"]["schemas"]}
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{schema}", "components": {"schemas": schemas}},
                        format_checker=jsonschema.FormatChecker())


@pytest.fixture
def notifications(iam_world: Any, tmp_path: Path) -> tuple[World, NotificationSchedule]:
    world = World(iam_world, tmp_path)
    schedule = NotificationSchedule.model_validate({
        "projects": ({"organization_id": iam_world.org_a, "project_id": world.p1, "digest_intervals_seconds": (5, 10)},),
        "poll_interval_seconds": 1, "page_timeout_seconds": 5, "page_size": 3,
    })
    path = tmp_path / "notification-schedule.json"
    path.write_text(schedule.model_dump_json())
    cursor_key_ring = world.app.state.cursor_key_ring
    world.app = create_app(world.settings.model_copy(update={"notification_schedule_file": path}), identity=world.services,
                           manager_dispatch_namespace="ai-res")
    world.app.state.cursor_key_ring = cursor_key_ring
    return world, schedule


async def _intake(client: httpx.AsyncClient, epic: str) -> UUID:
    response = await client.post(f"/api/v1/epics/{epic}/manager-messages", json={"message": "private user text"}, headers=key())
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


async def _terminal(
    world: World, operation: UUID, *, success: bool, exact: bool = True, occurred_at: Any = None,
) -> tuple[UUID, UUID | None]:
    org, project = world.iam.org_a, world.p1
    async with UnitOfWork(world.services.factory) as uow:
        await uow.with_tenant(org, project)
        repo = OperationRepository(uow.session)
        row = await repo.get(operation)
        assert row is not None
        correlation = uuid4()
        if not success:
            event = await repo.transition(row, "FAILED", EventSpec(
                "operation.failed", 1, "SERVICE", correlation, (DOMAIN_DESTINATION,), to_status="FAILED", occurred_at=occurred_at,
            ))
            return event.event_id, None
        for status, event_type in (("QUEUED", "operation.queued"), ("RUNNING", "operation.started")):
            await repo.transition(row, status, EventSpec(event_type, 1, "SERVICE", correlation, (DOMAIN_DESTINATION,), to_status=status))
            row = await repo.get(operation)
            assert row is not None
        interaction = (await uow.session.execute(text(
            "SELECT id FROM work.manager_interactions WHERE operation_id=:op",
        ), {"op": operation})).scalar_one()
        proposal = await ManagerProposalRepository(uow.session).propose(org, project, interaction, ProposalContent("private proposal text", None, None))
        event = await repo.transition(row, "SUCCEEDED", EventSpec(
            "operation.succeeded", 1, "MANAGER", correlation, (DOMAIN_DESTINATION,), to_status="SUCCEEDED", occurred_at=occurred_at,
        ), result_ref={"id": str(proposal.id if exact else uuid4())})
        return event.event_id, proposal.id


async def test_feed_delivers_mandatory_and_digests_once_with_exact_refs(notifications, monkeypatch):
    world, schedule = notifications
    project = f"/api/v1/projects/{world.p1}"
    feed, pref = f"{project}/notifications", f"{project}/notification-preferences"
    start = utc_now()
    tracer = trace.get_tracer(__name__)
    async with await world.client("analyst") as analyst, await world.client("viewer") as viewer, await world.client("outsider") as outsider:
        epic = await analyst.post(f"{project}/epics", json={"title": "Intake"}, headers=key())
        assert epic.status_code == 201, epic.text
        failed = await _intake(analyst, epic.json()["id"])
        successful = [await _intake(analyst, epic.json()["id"]) for _ in range(2)]
        mismatched = await _intake(analyst, epic.json()["id"])
        failed_event, _ = await _terminal(world, failed, success=False, occurred_at=start)
        proposal_events = [await _terminal(world, op, success=True, occurred_at=start) for op in successful]
        await _terminal(world, mismatched, success=True, exact=False, occurred_at=start)
        monkeypatch.setattr(notification_delivery, "utc_now", lambda: start)
        background_pass = asyncio.Event()
        run_once = NotificationScheduler.run_once

        async def signal_pass(self):
            await run_once(self)
            background_pass.set()

        monkeypatch.setattr(NotificationScheduler, "run_once", signal_pass)
        async with world.app.router.lifespan_context(world.app), asyncio.timeout(5):
            await background_pass.wait()
        original = NotificationScheduler(world.services.factory, schedule, tracer)
        before = (await analyst.get(feed)).json()
        _assert_contract(before, "ProjectNotificationPage")
        assert before["data"][0]["kind"] == "MANDATORY"
        assert before["data"][0]["items"][0]["eventId"] == str(failed_event)
        assert len(before["data"]) == 1
        initial = await analyst.get(pref)
        _assert_contract(initial.json(), "ProjectNotificationPreferences")
        assert initial.json() == {"selectedIntervalSeconds": None, "allowedIntervalSeconds": [5, 10]}
        selected = await analyst.put(pref, json={"intervalSeconds": 5}, headers={"If-Match": initial.headers["etag"]})
        assert selected.status_code == 200
        assert (await analyst.get(feed)).json() == before
        monkeypatch.setattr(notification_delivery, "utc_now", lambda: start + timedelta(seconds=5))
        restarted = NotificationScheduler(world.services.factory, schedule, tracer)
        await asyncio.gather(original.run_once(), restarted.run_once())
        page = await analyst.get(feed, params={"limit": 1})
        assert page.status_code == 200, page.text
        data = page.json()
        _assert_contract(data, "ProjectNotificationPage")
        assert data["data"][0]["kind"] == "DIGEST"
        assert {(r["eventId"], r["proposalVersionId"]) for r in data["data"][0]["items"]} == {
            (str(eid), str(proposal)) for eid, proposal in proposal_events
        }
        cursor = data["page"]["nextCursor"]
        next_page = await analyst.get(feed, params={"limit": 1, "cursor": cursor})
        assert next_page.json() == before
        assert "private user text" not in page.text and "private proposal text" not in page.text
        assert (await viewer.get(feed)).json()["data"] == []
        assert (await viewer.get(feed, params={"cursor": cursor})).status_code == 400
        denied = await outsider.get(feed)
        assert denied.status_code == 404
        assert world.count("project.notification_events") == 3
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PUBLISHED'") == 2
        later = await _intake(analyst, epic.json()["id"])
        later_event, _ = await _terminal(world, later, success=True, occurred_at=start + timedelta(seconds=2))
        monkeypatch.setattr(notification_delivery, "utc_now", lambda: start + timedelta(seconds=9))
        await restarted.run_once()
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PUBLISHED'") == 2
        monkeypatch.setattr(notification_delivery, "utc_now", lambda: start + timedelta(seconds=10))
        await restarted.run_once()
        assert (await analyst.get(feed)).json()["data"][0]["items"][0]["eventId"] == str(later_event)
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PUBLISHED'") == 3
        # The former analyst may still read Operations but loses access to all proposal refs.
        with world.iam.pg.connect() as connection:
            connection.execute(
                "UPDATE project.project_memberships SET role_code='READ_ONLY_VIEWER',row_version=row_version+1"
                " WHERE project_id=%s AND user_id=%s",
                (world.p1, world.u["analyst"]),
            )
        assert (await analyst.get(feed)).json() == before
        assert (await analyst.get(pref)).status_code == 404


async def test_preference_change_requires_current_csrf_origin_version_and_recipient(notifications):
    world, _ = notifications
    pref = f"/api/v1/projects/{world.p1}/notification-preferences"
    async with (
        await world.client("analyst") as analyst,
        await world.client("analyst", csrf=False) as no_csrf,
        await world.client("analyst", origin=False) as no_origin,
        await world.client("viewer") as viewer,
        await world.client(None) as anonymous,
    ):
        initial = await analyst.get(pref)
        etag = {"If-Match": initial.headers["etag"]}
        consumed = False

        async def body():
            nonlocal consumed
            consumed = True
            yield b'{"intervalSeconds": 5}'

        assert (await anonymous.put(pref, content=body(), headers=etag)).status_code == 401
        assert not consumed
        oversized = await analyst.put(pref, content=b" " * 300 + b'{"intervalSeconds": 5}', headers=etag)
        assert oversized.status_code == 422
        assert (await no_csrf.put(pref, json={"intervalSeconds": 5}, headers=etag)).status_code == 403
        assert (await no_origin.put(pref, json={"intervalSeconds": 5}, headers=etag)).status_code == 403
        assert (await viewer.put(pref, json={"intervalSeconds": 5}, headers=etag)).status_code == 404
        assert (await analyst.put(pref, json={"intervalSeconds": 5})).status_code == 428
        assert (await analyst.put(pref, json={"intervalSeconds": 20}, headers=etag)).status_code == 422
        assert (await analyst.put(pref, json={"intervalSeconds": 5, "recipientId": str(world.u["viewer"])}, headers=etag)).status_code == 422
        results = await asyncio.gather(*(analyst.put(pref, json={"intervalSeconds": seconds}, headers=etag) for seconds in (5, 10)))
        assert sorted(result.status_code for result in results) == [200, 412]
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PREFERENCE_UPDATED'") == 1
        winner = next(result for result in results if result.status_code == 200)
        next_selection = 10 if winner.json()["selectedIntervalSeconds"] == 5 else 5
        updated = await analyst.put(pref, json={"intervalSeconds": next_selection}, headers={"If-Match": winner.headers["etag"]})
        assert updated.status_code == 200 and updated.headers["etag"] != winner.headers["etag"]
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PREFERENCE_UPDATED'") == 2
        assert world.count("project.notification_preferences") == 1
    with world.iam.pg.connect("ai_res_api", autocommit=False) as connection:
        connection.execute("SELECT set_config('app.organization_id', %s, true)", (str(world.iam.org_a),))
        connection.execute("SELECT set_config('app.project_id', %s, true)", (str(world.p1),))
        assert connection.execute("SELECT count(*) FROM project.notification_preferences").fetchone() == (0,)
        connection.execute("SELECT set_config('app.notification_recipient_id', %s, true)", (str(world.u["viewer"]),))
        assert connection.execute("SELECT count(*) FROM project.notification_preferences").fetchone() == (0,)
        connection.execute("SELECT set_config('app.notification_recipient_id', %s, true)", (str(world.u["analyst"]),))
        assert connection.execute("SELECT count(*) FROM project.notification_preferences").fetchone() == (1,)
        connection.execute("SELECT set_config('app.project_id', %s, true)", (str(world.p2),))
        assert connection.execute("SELECT count(*) FROM project.notification_preferences").fetchone() == (0,)


async def test_preference_rechecks_current_grant_after_receiving_the_body(notifications):
    world, _ = notifications
    pref = f"/api/v1/projects/{world.p1}/notification-preferences"
    async with await world.client("analyst") as analyst:
        initial = await analyst.get(pref)

        async def body():
            with world.iam.pg.connect() as connection:
                connection.execute(
                    "UPDATE project.project_memberships SET role_code='READ_ONLY_VIEWER',row_version=row_version+1"
                    " WHERE project_id=%s AND user_id=%s",
                    (world.p1, world.u["analyst"]),
                )
            yield b'{"intervalSeconds": 5}'

        denied = await analyst.put(pref, content=body(), headers={"If-Match": initial.headers["etag"]})
        assert denied.status_code == 404
        assert world.count("project.notification_preferences") == 0
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PREFERENCE_UPDATED'") == 0


async def test_digest_backlog_continues_at_the_next_visit_and_feed_scan_conceals_hidden_positions(notifications, monkeypatch):
    world, schedule = notifications
    project = f"/api/v1/projects/{world.p1}"
    feed, pref = f"{project}/notifications", f"{project}/notification-preferences"
    scope = NotificationScope(world.iam.org_a, world.p1, world.u["analyst"])
    start = utc_now()
    monkeypatch.setattr(notification_delivery, "_DIGEST_BATCH_SIZE", 2)
    monkeypatch.setattr(notification_api, "_MAX_FEED_CANDIDATES", 2)

    async with await world.client("analyst") as analyst:
        epic = await analyst.post(f"{project}/epics", json={"title": "Backlog"}, headers=key())
        assert epic.status_code == 201, epic.text
        initial = await analyst.get(pref)
        assert (await analyst.put(pref, json={"intervalSeconds": 5}, headers={"If-Match": initial.headers["etag"]})).status_code == 200

        pairs = []
        for index in range(5):
            operation = await _intake(analyst, epic.json()["id"])
            pairs.append(await _terminal(world, operation, success=True, occurred_at=start + timedelta(milliseconds=index)))
        failed = await _intake(analyst, epic.json()["id"])
        failure, _ = await _terminal(world, failed, success=False, occurred_at=start)

        async def run_at(seconds: int) -> tuple[int, int]:
            monkeypatch.setattr(notification_delivery, "utc_now", lambda: start + timedelta(seconds=seconds))
            mandatory = await publish_mandatory(world.services.factory, scope, batch_size=1)
            return mandatory, await publish_digest(world.services.factory, scope, schedule.projects[0])

        async def fail_digest(*_args):
            raise SQLAlchemyError("deliberate test failure")

        with monkeypatch.context() as failure_patch:
            failure_patch.setattr(notification_delivery, "utc_now", lambda: start)
            failure_patch.setattr(notification_delivery, "_continue_digest", fail_digest)
            await NotificationScheduler(world.services.factory, schedule, trace.get_tracer(__name__)).run_once()

        pending = (await analyst.get(feed)).json()
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PUBLISHED'") == 1
        assert await run_at(5) == (0, 0)
        assert [d["kind"] for d in pending["data"]] == ["MANDATORY"]
        assert await run_at(6) == (0, 0)
        assert (await analyst.get(feed)).json() == pending
        assert await run_at(7) == (0, 1)
        assert world.count("audit.audit_events", "action = 'NOTIFICATION_PUBLISHED'") == 2
        assert world.count("project.notification_deliveries", "NOT mandatory") == 1

        # A denial for two exact refs must not scan/audit through the entire digest or expose either ref in plaintext continuation.
        hidden = {str(proposal) for _, proposal in pairs[-2:]}
        original = world.services.enforcer.decide
        exact_checks = 0

        async def deny_exact(request, **kwargs):
            nonlocal exact_checks
            if request.action == "manager.proposal.read" and request.resource_id is not None:
                exact_checks += 1
                if request.resource_id in hidden:
                    raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
            return await original(request, **kwargs)

        monkeypatch.setattr(world.services.enforcer, "decide", deny_exact)
        first_page = (await analyst.get(feed)).json()
        assert first_page["data"] == [] and first_page["page"]["hasMore"] and exact_checks == 2
        cursor = first_page["page"]["nextCursor"]
        encoded = cursor.split(".")[0]
        signed_payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        assert all(value not in signed_payload for value in {*hidden, *(str(event) for event, _ in pairs)})
        page2 = (await analyst.get(feed, params={"cursor": cursor})).json()
        assert [len(d["items"]) for d in page2["data"]] == [2] and exact_checks == 4
        page3 = (await analyst.get(feed, params={"cursor": page2["page"]["nextCursor"]})).json()
        assert [d["kind"] for d in page3["data"]] == ["DIGEST", "MANDATORY"] and exact_checks == 5
        assert page3["data"][0]["id"] == page2["data"][0]["id"]
        assert page3["data"][1]["items"][0]["eventId"] == str(failure)
        actual = {item["eventId"] for d in [*page2["data"], page3["data"][0]] for item in d["items"]}
        assert actual == {str(event) for event, _ in pairs[:3]}


@pytest.mark.parametrize("include_digests", [True, False])
def test_feed_continuation_generic_plan_seeks_both_keysets(notifications, include_digests):
    world, _ = notifications
    # EXPLAIN GENERIC_PLAN uses PostgreSQL's positional parameter syntax, without supplying cursor values.
    parameters = ("org", "project", "recipient", "before_time", "before_id", "head_limit", "limit", "before_occurred", "before_event")
    sql = notification_delivery._FEED_QUERIES[True, include_digests].text
    for index, name in enumerate(parameters, start=1):
        sql = re.sub(rf":{name}\b", f"${index}", sql)
    with world.iam.pg.connect("ai_res_api", autocommit=False) as conn:
        for name, value in (
            ("organization_id", world.iam.org_a), ("project_id", world.p1), ("notification_recipient_id", world.u["analyst"]),
        ):
            conn.execute("SELECT set_config(%s,%s,true)", (f"app.{name}", str(value)))
        # A tiny fixture is not a selectivity benchmark. Isolate available B-tree paths for this regression.
        conn.execute("SET LOCAL enable_seqscan=off")
        conn.execute("SET LOCAL enable_bitmapscan=off")
        [plans] = conn.execute(f"EXPLAIN (GENERIC_PLAN ON, COSTS OFF, FORMAT JSON) {sql}").fetchone()

    def index_conditions(plan):
        if "Index Cond" in plan:
            yield plan["Index Cond"]
        for child in plan.get("Plans", ()):
            yield from index_conditions(child)

    conditions = tuple(index_conditions(plans[0]["Plan"]))
    assert any("ROW(published_at, id) < ROW" in condition for condition in conditions)
    assert any("ROW(occurred_at, event_id) < ROW" in condition for condition in conditions)


def test_upgrade_from_previous_revision_preserves_existing_data(empty_db: Pg, upgrade):
    upgrade("28a56a9341ce")
    with empty_db.connect() as connection:
        org_id = connection.execute("INSERT INTO organization.organizations(id,name) VALUES(gen_random_uuid(),'Existing') RETURNING id").fetchone()[0]
    upgrade()
    with empty_db.connect() as connection:
        assert connection.execute("SELECT name FROM organization.organizations WHERE id=%s", (org_id,)).fetchone() == ("Existing",)
        assert connection.execute("SELECT version_num FROM platform.alembic_version").fetchone() == ("95ce548ce5b0",)
        assert run_audit(connection, "grants_audit.sql") == []
        assert run_audit(connection, "rls_coverage.sql") == []
        for role in ("ai_res_platform_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer"):
            assert connection.execute("SELECT has_table_privilege(%s,'project.notification_events','SELECT')", (role,)).fetchone() == (False,)
