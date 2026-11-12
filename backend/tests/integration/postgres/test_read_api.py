# ruff: noqa: E501, S105, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S08: read-only Public API GET operations end to end on real PostgreSQL (ADR-074..077; API-MVP read, SEC-001/002).

Seeding as the bootstrap superuser; every request goes through the real app under the least-privilege `ai_res_api` role with a real session cookie.
Covers IDOR (identical 404 for foreign/missing objects), visibility of lists, cursor binding, ETag, revoked grants, OAS conformance and the equivalence of
the list visibility SQL with the Policy Engine decision.
"""
import asyncio
import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import jsonschema
import pytest
import yaml

from ai_res.api.app import create_app
from ai_res.api.identity import build_identity_services
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.readmodel.queries import ReadQueries
from ai_res.platform.config import load_settings
from ai_res.platform.pagination import KeyRing, encode_cursor
from ai_res.platform.ports import Effect, PolicyRequest
from ai_res.policy.engine import PolicyEngine

from .test_agents_execution_schema import new_run
from .test_operations_work_schema import new_epic, new_op, new_task

pytestmark = pytest.mark.postgres
CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
OAS = yaml.safe_load((CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml").read_text())


class World:
    """Org A: projects P1 (viewer is READ_ONLY_VIEWER) and P2 (viewer has no role); org B: project PB with its own objects."""

    def __init__(self, iam: Any, tmp_path: Path) -> None:
        self.iam = iam
        self.viewer = uuid4()
        self.ids: dict[str, UUID] = {}
        i = self.ids
        with iam.pg.connect() as c:
            c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'v@example.com','v@example.com','v')", [self.viewer, iam.org_a])
            for key, org, name in (("p1", iam.org_a, "P1"), ("p2", iam.org_a, "P2"), ("pb", iam.org_b, "PB")):
                i[key] = uuid4()
                c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,%s,'GREENFIELD')", [i[key], org, name])
            c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (gen_random_uuid(),%s,%s,%s,'READ_ONLY_VIEWER')", [iam.org_a, i["p1"], self.viewer])
            for key, org, prj in (("1", iam.org_a, i["p1"]), ("2", iam.org_a, i["p2"]), ("b", iam.org_b, i["pb"])):
                i[f"epic{key}"] = new_epic(c, org, prj)
                i[f"op{key}"] = new_op(c, org, prj)
                i[f"task{key}"] = new_task(c, org, prj, i[f"op{key}"], i[f"epic{key}"])
                i[f"run{key}"] = new_run(c, org, prj, i[f"op{key}"], i[f"task{key}"])
                i[f"req{key}"], i[f"art{key}"], i[f"src{key}"] = uuid4(), uuid4(), uuid4()
                with c.transaction():
                    c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number) VALUES (%s,%s,%s,%s)", [i[f"req{key}"], org, prj, 7])
                    vid = uuid4()
                    c.execute("INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, statement, author_type) "
                              "VALUES (%s,%s,%s,%s,1,'FR','The system shall X','IMPORT')", [vid, org, prj, i[f"req{key}"]])
                    c.execute("UPDATE requirements.requirements SET current_version_id = %s, last_version_number = 1, row_version = row_version + 1 WHERE id = %s", [vid, i[f"req{key}"]])
                    i[f"reqv{key}"] = vid
                with c.transaction():
                    c.execute("INSERT INTO artifacts.artifacts (id, organization_id, project_id, artifact_type, source_of_truth_mode, title) VALUES (%s,%s,%s,'OPENAPI','DOMAIN_MODEL','Art')", [i[f"art{key}"], org, prj])
                    vid = uuid4()
                    c.execute("INSERT INTO artifacts.artifact_versions (id, organization_id, project_id, artifact_id, version_number, schema_version, content_ref, content_checksum, provenance, author_type) "
                              "VALUES (%s,%s,%s,%s,1,'1','{}'::jsonb,%s,'{}'::jsonb,'IMPORT')", [vid, org, prj, i[f"art{key}"], b"\x01" * 32])
                    c.execute("UPDATE artifacts.artifacts SET current_version_id = %s, last_version_number = 1, row_version = row_version + 1 WHERE id = %s", [vid, i[f"art{key}"]])
                c.execute("INSERT INTO sources.sources (id, organization_id, project_id, source_kind, title) VALUES (%s,%s,%s,'FILE','Src')", [i[f"src{key}"], org, prj])
        key_file = tmp_path / "mfa.key"
        key_file.write_text(base64.b64encode(bytes(range(32))).decode())
        self.settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_COOKIE_SECURE": "false", "AI_RES_MFA_ENCRYPTION_KEY_FILE": str(key_file),
                                       "AI_RES_ARGON2_TIME_COST": "1", "AI_RES_ARGON2_MEMORY_KIB": "8", "AI_RES_DEFAULT_ORGANIZATION_ID": str(iam.org_a),
                                       "AI_RES_SSE_POLL_INTERVAL_SECONDS": "0.1", "AI_RES_SSE_SETTLE_SECONDS": "0.5", "AI_RES_SSE_MAX_SECONDS": "3"})
        self.services = build_identity_services(self.settings, create_session_factory(iam.engine()))
        self.app = create_app(self.settings, identity=self.services)
        self.app.state.cursor_key_ring = KeyRing("k1", {"k1": bytes(range(32, 64))})

    async def client(self, user: UUID | None, org: UUID | None = None, *, mfa: bool = False) -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("198.51.100.7", 4444)), base_url="http://testserver")
        if user is not None:
            issued = await self.services.sessions.create(org or self.iam.org_a, user, mfa_verified=mfa)
            c.cookies.set(self.settings.session_cookie_name, issued.token)
        return c

    def sql_one(self, statement: str, *params: Any) -> Any:
        with self.iam.pg.connect() as c:
            return c.execute(statement, list(params)).fetchone()[0]

    def sql(self, statement: str, *params: Any) -> None:
        with self.iam.pg.connect() as c:
            c.execute(statement, list(params))


@pytest.fixture
def w(iam_world: Any, tmp_path: Path) -> World:
    return World(iam_world, tmp_path)


def conforms(body: Any, schema: str) -> None:
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{schema}", "components": OAS["components"]}, format_checker=jsonschema.FormatChecker())


def stripped(r: httpx.Response) -> dict[str, Any]:
    return {k: v for k, v in r.json().items() if k not in ("requestId", "instance", "correlationId")}


async def test_unauthenticated_requests_are_401_on_every_read(w: World) -> None:
    async with await w.client(None) as c:
        i = w.ids
        for path in ("/projects", f"/projects/{i['p1']}", f"/projects/{i['p1']}/epics", f"/epics/{i['epic1']}", f"/epics/{i['epic1']}/tasks", f"/tasks/{i['task1']}",
                     f"/projects/{i['p1']}/requirements", f"/requirements/{i['req1']}/versions", f"/projects/{i['p1']}/sources", f"/projects/{i['p1']}/artifacts",
                     f"/artifacts/{i['art1']}/versions", f"/worker-runs/{i['run1']}"):
            assert (await c.get(f"/api/v1{path}")).status_code == 401, path


async def test_viewer_lists_only_the_project_they_hold_a_role_in_and_every_page_conforms(w: World) -> None:
    async with await w.client(w.viewer) as c:
        r = await c.get("/api/v1/projects")
        project = await c.get(f"/api/v1/projects/{w.ids['p1']}")
    assert r.status_code == 200 and [p["id"] for p in r.json()["data"]] == [str(w.ids["p1"])] and r.json()["page"] == {"nextCursor": None, "hasMore": False}
    conforms(r.json(), "ProjectPage")
    conforms(project.json(), "Project")
    assert project.headers["etag"] and r.headers["cache-control"] == "no-store"


async def test_org_auditor_sees_every_project_of_its_own_organization_and_nothing_of_another(w: World) -> None:
    async with await w.client(w.iam.user_a) as c:
        got = {p["id"] for p in (await c.get("/api/v1/projects")).json()["data"]}
        foreign = await c.get(f"/api/v1/projects/{w.ids['pb']}")
    assert got == {str(w.ids["p1"]), str(w.ids["p2"])} and foreign.status_code == 404


GETS = [("projects/{p}", "p"), ("projects/{p}/epics", "p"), ("projects/{p}/requirements", "p"), ("projects/{p}/sources", "p"), ("projects/{p}/artifacts", "p"),
        ("epics/{e}", "epic"), ("epics/{e}/tasks", "epic"), ("tasks/{e}", "task"), ("requirements/{e}/versions", "req"), ("artifacts/{e}/versions", "art"), ("worker-runs/{e}", "run"), ("operations/{e}", "op")]


@pytest.mark.parametrize(("template", "kind"), GETS)
async def test_foreign_and_missing_objects_get_one_identical_404(w: World, template: str, kind: str) -> None:
    def url(suffix: str | UUID) -> str:
        return "/api/v1/" + template.format(p=suffix, e=suffix)
    mine = w.ids["p1"] if kind == "p" else w.ids[f"{kind}1"]
    other_project = w.ids["p2"] if kind == "p" else w.ids[f"{kind}2"]  # same organization, a project the viewer holds no role in
    other_org = w.ids["pb"] if kind == "p" else w.ids[f"{kind}b"]
    async with await w.client(w.viewer) as c:
        own = await c.get(url(mine))
        answers = [await c.get(url(other_project)), await c.get(url(other_org)), await c.get(url(uuid4()))]
    assert own.status_code == 200
    assert [a.status_code for a in answers] == [404, 404, 404] and stripped(answers[0]) == stripped(answers[1]) == stripped(answers[2])


async def test_every_get_response_conforms_to_the_oas_schema(w: World) -> None:
    i = w.ids
    cases = [(f"/projects/{i['p1']}/epics", "EpicPage"), (f"/epics/{i['epic1']}", "Epic"), (f"/epics/{i['epic1']}/tasks", "TaskPage"), (f"/tasks/{i['task1']}", "Task"),
             (f"/projects/{i['p1']}/requirements", "RequirementPage"), (f"/requirements/{i['req1']}/versions", "RequirementVersionPage"),
             (f"/projects/{i['p1']}/sources", "SourcePage"), (f"/projects/{i['p1']}/artifacts", "ArtifactPage"),
             (f"/artifacts/{i['art1']}/versions", "ArtifactVersionPage"), (f"/worker-runs/{i['run1']}", "WorkerRun"),
             (f"/operations/{i['op1']}", "Operation")]
    async with await w.client(w.viewer) as c:
        for path, schema in cases:
            r = await c.get(f"/api/v1{path}")
            assert r.status_code == 200, (path, r.text)
            conforms(r.json(), schema)
        req = (await c.get(f"/api/v1/projects/{i['p1']}/requirements")).json()["data"][0]
    assert req["displayId"] == "REQ-000007"


async def test_get_operation_reads_the_projection_with_oas_vocabulary_and_etag(w: World) -> None:
    async with await w.client(w.viewer) as c:
        r = await c.get(f"/api/v1/operations/{w.ids['op1']}")
    body = r.json()
    assert r.status_code == 200 and r.headers["etag"] and r.headers["cache-control"] == "no-store"
    assert body["status"] == "ACCEPTED" and body["initiatorType"] in {"HUMAN", "SYSTEM", "MANAGER", "SCHEDULED"}  # store vocabulary USER/SERVICE is mapped, not leaked
    assert body["rootOperationId"] == body["id"] and body["parentOperationId"] is None and body["completedAt"] is None
    assert body["projectId"] == str(w.ids["p1"]) and body["organizationId"] == str(w.iam.org_a)


async def test_pagination_walks_every_row_once_and_cursors_are_bound(w: World) -> None:
    with w.iam.pg.connect() as c:
        for _ in range(4):
            new_epic(c, w.iam.org_a, w.ids["p1"])
    async with await w.client(w.viewer) as c:
        seen: list[str] = []
        cursor: str | None = None
        while True:
            r = await c.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"limit": 2, **({"cursor": cursor} if cursor else {})})
            body = r.json()
            seen += [e["id"] for e in body["data"]]
            cursor = body["page"]["nextCursor"]
            if not body["page"]["hasMore"]:
                break
        first = (await c.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"limit": 1})).json()["page"]["nextCursor"]
        other_endpoint = await c.get(f"/api/v1/projects/{w.ids['p1']}/sources", params={"cursor": first})
        tampered = await c.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"cursor": first[:-2] + "xx"})
        async with await w.client(w.iam.user_a) as other:
            foreign_user = await other.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"cursor": first})
    assert len(seen) == len(set(seen)) == 5 and cursor is None
    assert other_endpoint.status_code == tampered.status_code == foreign_user.status_code == 400


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc"])
async def test_limit_outside_the_oas_range_is_rejected(w: World, limit: str) -> None:
    async with await w.client(w.viewer) as c:
        r = await c.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"limit": limit})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json") and r.json()["code"] == "VALIDATION_ERROR"


async def test_etag_follows_row_version(w: World) -> None:
    async with await w.client(w.viewer) as c:
        before = [(await c.get(f"/api/v1/{p}")).headers["etag"] for p in (f"projects/{w.ids['p1']}", f"tasks/{w.ids['task1']}")]
        w.sql("UPDATE project.projects SET name = 'renamed', row_version = row_version + 1 WHERE id = %s", w.ids["p1"])
        w.sql("UPDATE work.tasks SET title = 'renamed', row_version = row_version + 1 WHERE id = %s", w.ids["task1"])
        after = [(await c.get(f"/api/v1/{p}")).headers["etag"] for p in (f"projects/{w.ids['p1']}", f"tasks/{w.ids['task1']}")]
        again = (await c.get(f"/api/v1/projects/{w.ids['p1']}")).headers["etag"]
    assert before == ['"v1"', '"v1"'] and after == ['"v2"', '"v2"'] and again == after[0]  # the "v<N>" shape is what parse_if_match (S09 writes) accepts


async def test_revoked_project_role_closes_access_immediately(w: World) -> None:
    async with await w.client(w.viewer) as c:
        assert (await c.get(f"/api/v1/epics/{w.ids['epic1']}")).status_code == 200
        w.sql("UPDATE project.project_memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = %s", w.viewer)
        answers = [(await c.get(f"/api/v1/{p}")).status_code for p in (f"epics/{w.ids['epic1']}", f"projects/{w.ids['p1']}", f"projects/{w.ids['p1']}/epics")]
        listed = (await c.get("/api/v1/projects")).json()["data"]
    assert answers == [404, 404, 404] and listed == []


async def test_revoked_organization_membership_ends_the_session(w: World) -> None:
    async with await w.client(w.iam.user_a) as c:
        assert (await c.get("/api/v1/projects")).status_code == 200
        w.sql("UPDATE organization.memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE user_id = %s", w.iam.user_a)
        assert (await c.get("/api/v1/projects")).status_code == 401


async def test_privileged_project_role_needs_a_verified_second_factor(w: World) -> None:
    w.sql("UPDATE project.project_memberships SET role_code = 'PROJECT_ADMIN', row_version = row_version + 1 WHERE user_id = %s", w.viewer)
    async with await w.client(w.viewer, mfa=False) as plain, await w.client(w.viewer, mfa=True) as verified:
        denied = [(await plain.get(f"/api/v1/projects/{w.ids['p1']}")).status_code, len((await plain.get("/api/v1/projects")).json()["data"])]
        allowed = [(await verified.get(f"/api/v1/projects/{w.ids['p1']}")).status_code, len((await verified.get("/api/v1/projects")).json()["data"])]
    assert denied == [404, 0] and allowed == [200, 1]


@pytest.mark.parametrize("project_role", [None, "PROJECT_ADMIN", "ANALYST", "REVIEWER_APPROVER", "READ_ONLY_VIEWER", "AUDITOR"])
@pytest.mark.parametrize("mfa", [False, True])
@pytest.mark.parametrize("org_role", [None, "ORGANIZATION_OWNER", "ORGANIZATION_ADMIN", "AUDITOR"])
@pytest.mark.parametrize("membership", ["ACTIVE", "REVOKED"])
async def test_list_visibility_sql_equals_the_policy_engine_decision(w: World, project_role: str | None, mfa: bool, org_role: str | None, membership: str) -> None:
    """The listing SQL re-states PolicyEngine.decide for project.read; this pins the two so a matrix change cannot silently diverge."""
    user, org, prj = uuid4(), w.iam.org_a, w.ids["p2"]
    with w.iam.pg.connect() as c:
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,'x')", [user, org, f"{user}@e.com", f"{user}@e.com"])
        if org_role:
            c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code, status) VALUES (gen_random_uuid(),%s,%s,%s,%s)", [org, user, org_role, membership])
        if project_role:
            c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (gen_random_uuid(),%s,%s,%s,%s)", [org, prj, user, project_role])
    cfg = w.services.enforcer.config
    assert cfg is not None
    rule = cfg.actions["project.read"]
    engine = PolicyEngine(cfg, w.services.factory)
    decision = await engine.decide(PolicyRequest(actor_id=str(user), action="project.read", resource_type="PROJECT", resource_id=str(prj), organization_id=str(org),
                                                 project_id=str(prj), attributes={"mfa_verified": mfa}))
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(org)
        page = await ReadQueries(uow.session).visible_projects(org, user, plain_roles=sorted(rule.project_roles - cfg.privileged_roles), privileged_roles=sorted(rule.project_roles & cfg.privileged_roles),
                                                               org_roles=sorted(rule.org_roles), mfa_verified=mfa, limit=100, only=prj)
    assert (decision.effect is Effect.ALLOW) == bool(page.items), (decision, page.items)


def audit_rows(w: World) -> int:
    with w.iam.pg.connect() as c:
        return int(c.execute("SELECT count(*) FROM audit.audit_events").fetchone()[0])


async def walk(c: httpx.AsyncClient, path: str, limit: int) -> tuple[list[str], int]:
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        r = await c.get(f"/api/v1{path}", params={"limit": limit, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        body = r.json()
        pages += 1
        seen += [row["id"] for row in body["data"]]
        cursor = body["page"]["nextCursor"]
        assert (cursor is None) == (not body["page"]["hasMore"])
        if not body["page"]["hasMore"]:
            return seen, pages


async def test_rows_with_identical_timestamps_are_neither_skipped_nor_repeated(w: World) -> None:
    with w.iam.pg.connect() as c, c.transaction():  # one transaction => identical created_at; the id is the tiebreaker
        for _ in range(5):
            new_epic(c, w.iam.org_a, w.ids["p1"])
    async with await w.client(w.viewer) as c:
        seen, pages = await walk(c, f"/projects/{w.ids['p1']}/epics", 2)
        exact, exact_pages = await walk(c, f"/projects/{w.ids['p1']}/epics", 6)  # 6 rows, limit 6: hasMore must be false, no cursor
    assert len(seen) == len(set(seen)) == 6 and pages == 3 and len(exact) == 6 and exact_pages == 1


async def test_project_and_numeric_keyset_listings_page_completely(w: World) -> None:
    with w.iam.pg.connect() as c:
        for n in range(3):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,%s,'GREENFIELD')", [uuid4(), w.iam.org_a, f"X{n}"])
        for n in (8, 9, 10):
            rid = uuid4()
            with c.transaction():
                c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number) VALUES (%s,%s,%s,%s)", [rid, w.iam.org_a, w.ids["p1"], n])
                vid = uuid4()
                c.execute("INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, statement, author_type) "
                          "VALUES (%s,%s,%s,%s,1,'FR','s','IMPORT')", [vid, w.iam.org_a, w.ids["p1"], rid])
                c.execute("UPDATE requirements.requirements SET current_version_id = %s, last_version_number = 1, row_version = row_version + 1 WHERE id = %s", [vid, rid])
    async with await w.client(w.iam.user_a) as c:
        projects, _ = await walk(c, "/projects", 2)
        reqs, _ = await walk(c, f"/projects/{w.ids['p1']}/requirements", 1)
    assert len(projects) == len(set(projects)) == 5 and len(reqs) == len(set(reqs)) == 4


async def test_bad_cursors_are_400_before_any_database_or_audit_work(w: World) -> None:
    ring = w.app.state.cursor_key_ring
    filters = {"org": str(w.iam.org_a), "scope": str(w.ids["p1"])}

    def signed(keyset: list[Any], now: float | None = None) -> str:
        return encode_cursor(ring, subject=str(w.viewer), audience="listEpics", filters=filters, keyset=keyset, ttl_seconds=60, now=now)
    async with await w.client(w.viewer) as c:
        before = audit_rows(w)
        answers = [await c.get(f"/api/v1/projects/{w.ids['p1']}/epics", params={"cursor": token})
                   for token in (signed(["not-a-timestamp", "x"]), signed([1]), signed(["2020-01-01T00:00:00+00:00", "not-a-uuid"]), signed(["2020-01-01T00:00:00+00:00", str(uuid4())], now=1.0))]
        after = audit_rows(w)
    assert [a.status_code for a in answers] == [400] * 4 and before == after


async def test_parallel_reads_and_denials_do_not_starve_the_connection_pool(w: World) -> None:
    async with await w.client(w.viewer) as c:
        urls = [f"/api/v1/projects/{w.ids['p2']}/epics", f"/api/v1/projects/{w.ids['p1']}/epics", f"/api/v1/tasks/{w.ids['task1']}", f"/api/v1/tasks/{uuid4()}"] * 15
        answers = await asyncio.wait_for(asyncio.gather(*(c.get(u) for u in urls)), timeout=60)
    assert sorted({a.status_code for a in answers}) == [200, 404] and [a.status_code for a in answers].count(200) == 30


async def test_by_id_lookup_is_refused_when_the_caller_can_read_more_projects_than_the_cap(w: World) -> None:
    capped = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_COOKIE_SECURE": "false", "AI_RES_MFA_ENCRYPTION_KEY_FILE": str(w.settings.mfa_encryption_key_file),
                            "AI_RES_ARGON2_TIME_COST": "1", "AI_RES_ARGON2_MEMORY_KIB": "8", "AI_RES_READ_LOOKUP_MAX_PROJECTS": "1"})
    services = build_identity_services(capped, create_session_factory(w.iam.engine()))
    app = create_app(capped, identity=services)
    app.state.cursor_key_ring = w.app.state.cursor_key_ring
    issued = await services.sessions.create(w.iam.org_a, w.iam.user_a)  # org AUDITOR: reads both projects of org A
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", cookies={capped.session_cookie_name: issued.token}) as c:
        by_id = await c.get(f"/api/v1/tasks/{w.ids['task1']}")
        scoped = await c.get(f"/api/v1/projects/{w.ids['p1']}/epics")
    assert by_id.status_code == 503 and scoped.status_code == 200


# ---------------------------------------------------------------- S12: streamProjectEvents (SSE, ADR-033 / ADR-092)
def sse_frames(text: str) -> list[dict[str, str]]:
    out = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        if fields:
            out.append(fields)
    return out


async def cancel_op(w: World) -> None:
    from ai_res.modules.operations.cancellation import request_cancellation
    async with UnitOfWork(w.services.factory) as uow:
        await uow.with_tenant(w.iam.org_a, w.ids["p1"])
        await request_cancellation(uow.session, w.ids["op1"], actor_id=w.iam.user_a, correlation_id=uuid4())


async def test_stream_delivers_new_events_as_an_acl_neutral_projection_with_resumable_ids(w: World) -> None:
    async with await w.client(w.viewer) as c:
        task = asyncio.create_task(c.get(f"/api/v1/projects/{w.ids['p1']}/events"))
        await asyncio.sleep(0.4)
        await cancel_op(w)
        r = await task
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream") and r.headers["cache-control"] == "no-store"
    frames = sse_frames(r.text)
    events = [f for f in frames if f.get("event") == "event"]
    assert len(events) == 1 and frames[-1] == {"event": "close", "data": '{"reason":"max_duration"}'}
    data = json.loads(events[0]["data"])
    assert data["type"] == "operation.cancelled" and data["aggregateId"] == str(w.ids["op1"]) and data["toStatus"] == "CANCELLED" and "data" not in data
    assert events[0]["id"], "every event carries an opaque resumable id"


async def test_stream_acl_unreadable_or_missing_project_is_404_and_anonymous_is_401(w: World) -> None:
    async with await w.client(w.viewer) as c:
        foreign = await c.get(f"/api/v1/projects/{w.ids['p2']}/events")
        missing = await c.get(f"/api/v1/projects/{uuid4()}/events")
    async with await w.client(None) as anon:
        unauth = await anon.get(f"/api/v1/projects/{w.ids['p1']}/events")
    assert (foreign.status_code, missing.status_code, unauth.status_code) == (404, 404, 401) and stripped(foreign) == stripped(missing)


async def test_forged_foreign_or_cross_project_last_event_id_is_rejected_not_restarted(w: World) -> None:
    async with await w.client(w.viewer) as c:
        task = asyncio.create_task(c.get(f"/api/v1/projects/{w.ids['p1']}/events"))
        await asyncio.sleep(0.4)
        await cancel_op(w)
        token = next(f["id"] for f in sse_frames((await task).text) if f.get("event") == "event")
        forged = await c.get(f"/api/v1/projects/{w.ids['p1']}/events", headers={"Last-Event-ID": token[:-3] + "AAA"})
        garbage = await c.get(f"/api/v1/projects/{w.ids['p1']}/events", headers={"Last-Event-ID": "not-a-cursor"})
    async with await w.client(w.iam.user_a) as other:  # another session replaying the first one's cursor
        stolen = await other.get(f"/api/v1/projects/{w.ids['p1']}/events", headers={"Last-Event-ID": token})
    assert (forged.status_code, garbage.status_code, stolen.status_code) == (422, 422, 422)


async def test_resuming_with_a_valid_cursor_does_not_repeat_delivered_events(w: World) -> None:
    async with await w.client(w.viewer) as c:
        task = asyncio.create_task(c.get(f"/api/v1/projects/{w.ids['p1']}/events"))
        await asyncio.sleep(0.4)
        await cancel_op(w)
        token = next(f["id"] for f in sse_frames((await task).text) if f.get("event") == "event")
        again = await c.get(f"/api/v1/projects/{w.ids['p1']}/events", headers={"Last-Event-ID": token})
    assert again.status_code == 200 and [f for f in sse_frames(again.text) if f.get("event") == "event"] == []


async def test_stream_closes_when_the_session_is_revoked_mid_stream(w: World) -> None:
    async with await w.client(w.viewer) as c:
        task = asyncio.create_task(c.get(f"/api/v1/projects/{w.ids['p1']}/events"))
        await asyncio.sleep(0.4)
        w.sql("UPDATE iam.sessions SET revoked_at = now(), revoked_reason = 'LOGOUT', row_version = row_version + 1 WHERE user_id = %s", w.viewer)
        r = await task
    frames = sse_frames(r.text)
    assert frames[-1] == {"event": "close", "data": '{"reason":"access_revoked"}'}


async def test_a_cursor_older_than_retention_gets_a_gap_signal_not_silence(w: World) -> None:
    from ai_res.modules.events.stream import Position
    async with await w.client(w.viewer) as c:
        session_id = w.sql_one("SELECT id FROM iam.sessions WHERE user_id = %s", w.viewer)
        old = Position(datetime(2020, 1, 1, tzinfo=UTC), {})
        token = encode_cursor(w.app.state.cursor_key_ring, subject=str(session_id), audience="project-events",
                              filters={"organization": str(w.iam.org_a), "project": str(w.ids["p1"])}, keyset=old.to_keyset(), ttl_seconds=600)
        r = await c.get(f"/api/v1/projects/{w.ids['p1']}/events", headers={"Last-Event-ID": token})
    assert sse_frames(r.text)[0]["event"] == "gap" and '"retention"' in sse_frames(r.text)[0]["data"]
