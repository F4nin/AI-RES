# ruff: noqa: E501, S105, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S09: controlled write commands end to end on real PostgreSQL (ADR-078..083; API-MVP writes, PROC-MVP intake, UX-SRC upload).

Every request goes through the real app under the least-privilege `ai_res_api` role with a real session cookie, CSRF header and Origin. Seeding and
verification of stored state use the bootstrap superuser. `createTask` is out of scope (ADR-012 / NCP-08, S21).
"""
import asyncio
import base64
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import jsonschema
import pytest
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ai_res.api.app import create_app
from ai_res.api.identity import build_identity_services
from ai_res.api.write_api import StorageConfig
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events import aggregate_events
from ai_res.modules.events.contract import EventContract
from ai_res.modules.sources.object_store import S3ObjectStore
from ai_res.modules.sources.presign import StorageCredentials
from ai_res.platform.config import load_settings
from ai_res.platform.pagination import KeyRing

from .test_operations_work_schema import new_op

pytestmark = pytest.mark.postgres
CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
OAS = yaml.safe_load((CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml").read_text())
ASYNCAPI = yaml.safe_load((CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml").read_text())
ORIGIN = "http://app.test"
SHA = "ab" * 32
PDF = "application/pdf"
STORAGE = StorageConfig("https://files.example.test", "ai-res-sources", "us-east-1", StorageCredentials("AKIATESTACCESSKEY", "test-secret-key-not-real"), 1_000_000, frozenset({PDF, "text/plain"}), 300)


class World:
    """Org A with project P1 (padmin PROJECT_ADMIN, analyst ANALYST, viewer READ_ONLY_VIEWER, outsider no role) and project P2 (nobody); org admin `oadmin`."""

    def __init__(self, iam: Any, tmp_path: Path, storage: StorageConfig | None = STORAGE, object_store: Any = None) -> None:
        self.iam = iam
        self.u = {n: uuid4() for n in ("padmin", "analyst", "viewer", "outsider", "oadmin")}
        self.p1, self.p2, self.pb = uuid4(), uuid4(), uuid4()
        with iam.pg.connect() as c:
            for name, uid in self.u.items():
                c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,%s)", [uid, iam.org_a, f"{name}@example.com", f"{name}@example.com", name])
            c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (gen_random_uuid(),%s,%s,'ORGANIZATION_ADMIN')", [iam.org_a, self.u["oadmin"]])
            for pid, org, name in ((self.p1, iam.org_a, "P1"), (self.p2, iam.org_a, "P2"), (self.pb, iam.org_b, "PB")):
                c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,%s,'GREENFIELD')", [pid, org, name])
            for who, role in (("padmin", "PROJECT_ADMIN"), ("analyst", "ANALYST"), ("viewer", "READ_ONLY_VIEWER")):
                c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (gen_random_uuid(),%s,%s,%s,%s)", [iam.org_a, self.p1, self.u[who], role])
        key = tmp_path / "idem.keys"
        key.write_text("k1 " + base64.b64encode(bytes(range(64, 96))).decode() + "\n")
        mfa = tmp_path / "mfa.key"
        mfa.write_text(base64.b64encode(bytes(range(32))).decode())
        self.settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_COOKIE_SECURE": "false", "AI_RES_MFA_ENCRYPTION_KEY_FILE": str(mfa), "AI_RES_ARGON2_TIME_COST": "1",
                                       "AI_RES_ARGON2_MEMORY_KIB": "8", "AI_RES_DEFAULT_ORGANIZATION_ID": str(iam.org_a), "AI_RES_ALLOWED_ORIGINS": ORIGIN,
                                       "AI_RES_IDEMPOTENCY_KEYRING_FILE": str(key)})
        self.services = build_identity_services(self.settings, create_session_factory(iam.engine()))
        self.app = create_app(self.settings, identity=self.services, storage=storage, object_store=object_store)
        self.app.state.cursor_key_ring = KeyRing("k1", {"k1": bytes(range(32, 64))})

    async def client(self, who: str | UUID | None, *, mfa: bool = False, csrf: bool = True, origin: bool = True, org: UUID | None = None) -> httpx.AsyncClient:
        headers = {"Origin": ORIGIN} if origin else {}
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("198.51.100.7", 4444)), base_url="http://testserver", headers=headers)
        if who is not None:
            issued = await self.services.sessions.create(org or self.iam.org_a, self.u[who] if isinstance(who, str) else who, mfa_verified=mfa)
            c.cookies.set(self.settings.session_cookie_name, issued.token)
            if csrf:
                c.headers[self.settings.csrf_header_name] = issued.csrf_token
        return c

    def rows(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        with self.iam.pg.connect() as c:
            return c.execute(sql, list(params)).fetchall()

    def count(self, table: str, where: str = "true", *params: Any) -> int:
        return int(self.rows(f"SELECT count(*) FROM {table} WHERE {where}", *params)[0][0])


@pytest.fixture
def w(iam_world: Any, tmp_path: Path) -> World:
    return World(iam_world, tmp_path)


def key() -> dict[str, str]:
    return {"Idempotency-Key": f"key-{uuid4()}"}


def conforms(body: Any, schema: str) -> None:
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{schema}", "components": OAS["components"]}, format_checker=jsonschema.FormatChecker())


def event_conforms(envelope: dict[str, Any]) -> None:
    """The stored outbox envelope against the REAL AsyncAPI v1.6 message whose `type` const equals it."""
    name = next(n for n, schema in ASYNCAPI["components"]["schemas"].items() if schema.get("properties", {}).get("type", {}).get("const") == envelope["type"])
    registry = Registry().with_resource("urn:aires:asyncapi", Resource.from_contents(ASYNCAPI, default_specification=DRAFT202012))
    jsonschema.Draft202012Validator({"$ref": f"urn:aires:asyncapi#/components/schemas/{name}"}, registry=registry, format_checker=jsonschema.FormatChecker()).validate(envelope)


def stripped(r: httpx.Response) -> dict[str, Any]:
    return {k: v for k, v in r.json().items() if k not in ("requestId", "instance", "correlationId")}


def outbox(w: World, aggregate_id: UUID) -> list[dict[str, Any]]:
    return [r[0] for r in w.rows("SELECT envelope FROM audit.outbox_events WHERE aggregate_id = %s ORDER BY aggregate_sequence", aggregate_id)]


# ---------------------------------------------------------------- authentication, CSRF, Origin: every command, before anything else
WRITES = [("post", "/projects", {"organizationId": "{org}", "name": "N"}), ("patch", "/projects/{p1}", {"name": "N"}), ("post", "/projects/{p1}/epics", {"title": "E"}),
          ("post", "/projects/{p1}/requirements", {"statement": "S", "registrationKind": "CANDIDATE"}),
          ("post", "/requirements/{p1}/versions", {"statement": "S", "changeReason": "R"}),
          ("post", "/uploads", {"projectId": "{p1}", "fileName": "a.pdf", "contentType": PDF, "sizeBytes": 10, "sha256": SHA})]


def fill(w: World, value: Any) -> Any:
    if isinstance(value, str):
        return value.format(p1=w.p1, org=w.iam.org_a)
    if isinstance(value, dict):
        return {k: fill(w, v) for k, v in value.items()}
    return value


async def send(c: httpx.AsyncClient, method: str, path: str, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    h = dict(headers or {})
    if method == "patch":
        h["Content-Type"] = "application/merge-patch+json"
        return await c.request("PATCH", f"/api/v1{path}", content=json.dumps(body), headers=h)
    return await c.request(method.upper(), f"/api/v1{path}", json=body, headers=h)


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
async def test_unauthenticated_write_is_401(w: World, method: str, path: str, body: Any) -> None:
    async with await w.client(None) as c:
        r = await send(c, method, path.format(p1=w.p1), fill(w, body), {**key(), "If-Match": '"v1"'})
    assert r.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
async def test_missing_csrf_token_and_foreign_origin_are_refused_before_any_change(w: World, method: str, path: str, body: Any) -> None:
    for kwargs in ({"csrf": False}, {"origin": False}):
        async with await w.client("padmin", mfa=True, **kwargs) as c:
            r = await send(c, method, path.format(p1=w.p1), fill(w, body), {**key(), "If-Match": '"v1"'})
        assert r.status_code == 403 and r.json()["code"] == "ACCESS_DENIED", kwargs
    async with await w.client("padmin", mfa=True) as c:
        c.headers["Origin"] = "http://evil.test"
        assert (await send(c, method, path.format(p1=w.p1), fill(w, body), {**key(), "If-Match": '"v1"'})).status_code == 403
    assert w.count("project.projects") == 3 and w.count("work.epics") == 0 and w.count("sources.uploads") == 0


# ---------------------------------------------------------------- createProject
async def test_org_admin_creates_a_project_that_conforms_with_event_outbox_audit_and_first_administrator(w: World) -> None:
    async with await w.client("oadmin", mfa=True) as c:
        r = await c.post("/api/v1/projects", json={"organizationId": str(w.iam.org_a), "name": "New", "description": "d", "goal": "g", "projectType": "BROWNFIELD"}, headers=key())
        pid = UUID(r.json()["id"])
        got = await c.get(f"/api/v1/projects/{pid}")
    assert r.status_code == 201, r.text
    conforms(r.json(), "Project")
    assert r.json()["goal"] == "g" and r.json()["projectType"] == "BROWNFIELD" and r.headers["etag"] and r.headers["cache-control"] == "no-store"
    assert got.status_code == 200 and got.json() == r.json(), "the creator can read the project at once: they hold PROJECT_ADMIN"
    assert w.rows("SELECT role_code, status FROM project.project_memberships WHERE project_id = %s AND user_id = %s", pid, w.u["oadmin"]) == [("PROJECT_ADMIN", "ACTIVE")]
    [envelope] = outbox(w, pid)
    event_conforms(envelope)
    assert envelope["type"] == "aires.project.created.v1" and envelope["data"]["projectId"] == str(pid) and "operationId" not in envelope["data"]
    assert w.count("project.project_events", "project_id = %s AND aggregate_sequence = 1", pid) == 1
    actions = {a for (a,) in w.rows("SELECT action FROM audit.audit_events WHERE object_id = %s", pid)}
    assert {"PROJECT_CREATE", "PROJECT_MEMBERSHIP_INITIAL_GRANT", "POLICY_DECISION"} <= actions


async def test_create_project_requires_a_second_factor_the_org_admin_role_and_the_sessions_organization(w: World) -> None:
    body = {"organizationId": str(w.iam.org_a), "name": "X"}
    async with await w.client("oadmin", mfa=False) as c:
        no_mfa = await c.post("/api/v1/projects", json=body, headers=key())
    async with await w.client("analyst", mfa=True) as c:
        analyst = await c.post("/api/v1/projects", json=body, headers=key())
        foreign_org = await c.post("/api/v1/projects", json={**body, "organizationId": str(w.iam.org_b)}, headers=key())
    assert (no_mfa.status_code, analyst.status_code, foreign_org.status_code) == (403, 403, 403)
    assert w.count("project.projects") == 3


async def test_create_project_idempotent_retry_and_parallel_retries_create_exactly_one(w: World) -> None:
    body = {"organizationId": str(w.iam.org_a), "name": "Once"}
    headers = key()
    async with await w.client("oadmin", mfa=True) as c:
        first = await c.post("/api/v1/projects", json=body, headers=headers)
        again = await c.post("/api/v1/projects", json=body, headers=headers)
        other = await c.post("/api/v1/projects", json={**body, "name": "Other"}, headers=headers)
        parallel_headers = key()
        burst = await asyncio.gather(*[c.post("/api/v1/projects", json={**body, "name": "Burst"}, headers=parallel_headers) for _ in range(6)])
    assert first.status_code == again.status_code == 201 and first.json() == again.json()
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert {r.status_code for r in burst} <= {201, 409} and len({r.json()["id"] for r in burst if r.status_code == 201}) == 1 and any(r.status_code == 201 for r in burst)
    assert w.count("project.projects", "name = 'Once'") == 1 and w.count("project.projects", "name = 'Burst'") == 1
    assert w.count("audit.outbox_events", "aggregate_type = 'PROJECT'") == 2


async def test_create_project_validation_and_missing_idempotency_key(w: World) -> None:
    async with await w.client("oadmin", mfa=True) as c:
        base = {"organizationId": str(w.iam.org_a), "name": "V"}
        bad = [await c.post("/api/v1/projects", json={**base, "name": ""}, headers=key()), await c.post("/api/v1/projects", json={**base, "name": "   "}, headers=key()),
               await c.post("/api/v1/projects", json={**base, "projectType": "NOPE"}, headers=key()), await c.post("/api/v1/projects", json={**base, "extra": 1}, headers=key()),
               await c.post("/api/v1/projects", json=base), await c.post("/api/v1/projects", json=base, headers={"Idempotency-Key": "short"})]
    assert [r.status_code for r in bad] == [422] * 6 and all(r.json()["code"] == "VALIDATION_ERROR" for r in bad)
    assert w.count("project.projects") == 3


# ---------------------------------------------------------------- updateProjectMetadata
async def test_update_metadata_requires_if_match_and_advances_the_etag(w: World) -> None:
    async with await w.client("padmin", mfa=True) as c:
        etag = (await c.get(f"/api/v1/projects/{w.p1}")).headers["etag"]
        missing = await send(c, "patch", f"/projects/{w.p1}", {"name": "x"})
        malformed = await send(c, "patch", f"/projects/{w.p1}", {"name": "x"}, {"If-Match": "*"})
        ok = await send(c, "patch", f"/projects/{w.p1}", {"name": "Renamed", "goal": "G", "description": None}, {"If-Match": etag})
        stale = await send(c, "patch", f"/projects/{w.p1}", {"name": "Again"}, {"If-Match": etag})
        cleared = await send(c, "patch", f"/projects/{w.p1}", {"goal": None}, {"If-Match": ok.headers["etag"]})
        empty = await send(c, "patch", f"/projects/{w.p1}", {}, {"If-Match": cleared.headers["etag"]})
        null_name = await send(c, "patch", f"/projects/{w.p1}", {"name": None}, {"If-Match": cleared.headers["etag"]})
    assert (missing.status_code, malformed.status_code, ok.status_code, stale.status_code, cleared.status_code, empty.status_code, null_name.status_code) == (428, 412, 200, 412, 200, 422, 422)
    conforms(ok.json(), "Project")
    assert ok.json()["name"] == "Renamed" and ok.json()["goal"] == "G" and ok.json()["description"] is None and ok.headers["etag"] != etag
    assert cleared.json()["goal"] is None and cleared.json()["name"] == "Renamed"
    assert w.count("audit.audit_events", "action = 'PROJECT_UPDATE' AND object_id = %s", w.p1) == 2
    assert w.count("audit.outbox_events", "aggregate_id = %s", w.p1) == 0, "AsyncAPI v1.6 defines no project-updated message: none is invented (ADR-079)"


async def test_update_metadata_acl_and_idor(w: World) -> None:
    async with await w.client("viewer") as viewer, await w.client("analyst") as analyst, await w.client("outsider") as outsider, await w.client("padmin", mfa=True) as padmin:
        etag = (await padmin.get(f"/api/v1/projects/{w.p1}")).headers["etag"]
        denied = [await send(viewer, "patch", f"/projects/{w.p1}", {"name": "h"}, {"If-Match": etag}), await send(analyst, "patch", f"/projects/{w.p1}", {"name": "h"}, {"If-Match": etag})]
        hidden = await send(outsider, "patch", f"/projects/{w.p1}", {"name": "h"}, {"If-Match": etag})
        foreign = await send(padmin, "patch", f"/projects/{w.pb}", {"name": "h"}, {"If-Match": etag})
        missing = await send(padmin, "patch", f"/projects/{uuid4()}", {"name": "h"}, {"If-Match": etag})
        padmin_no_mfa = await w.client("padmin")
        async with padmin_no_mfa as nomfa:
            weak = await send(nomfa, "patch", f"/projects/{w.p1}", {"name": "h"}, {"If-Match": etag})
    assert [r.status_code for r in denied] == [403, 403]
    assert hidden.status_code == foreign.status_code == missing.status_code == weak.status_code == 404, "a privileged role without a second factor does not even see the project (S08 read matrix)"
    assert stripped(hidden) == stripped(foreign) == stripped(missing), "a foreign, an invisible and a missing project are indistinguishable"
    assert w.rows("SELECT name FROM project.projects WHERE id = %s", w.p1) == [("P1",)]


# ---------------------------------------------------------------- createEpic
async def test_analyst_creates_an_epic_with_event_and_outbox_and_retries_do_not_duplicate(w: World) -> None:
    headers = key()
    async with await w.client("analyst") as c:
        r = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "Epic", "goal": "g", "scope": "s"}, headers=headers)
        again = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "Epic", "goal": "g", "scope": "s"}, headers=headers)
        reused = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "Different"}, headers=headers)
        listed = await c.get(f"/api/v1/projects/{w.p1}/epics")
    assert r.status_code == again.status_code == 201 and r.json() == again.json() and reused.status_code == 409
    conforms(r.json(), "Epic")
    assert [e["id"] for e in listed.json()["data"]] == [r.json()["id"]]
    [envelope] = outbox(w, UUID(r.json()["id"]))
    event_conforms(envelope)
    assert envelope["type"] == "aires.epic.created.v1" and envelope["data"]["epicId"] == r.json()["id"]
    assert w.count("work.epics") == 1 and w.count("work.epic_events") == 1


async def test_epic_acl_idor_and_validation(w: World) -> None:
    async with await w.client("viewer") as viewer, await w.client("outsider") as outsider, await w.client("analyst") as analyst:
        denied = await viewer.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "E"}, headers=key())
        hidden = await outsider.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "E"}, headers=key())
        foreign = await analyst.post(f"/api/v1/projects/{w.pb}/epics", json={"title": "E"}, headers=key())
        other = await analyst.post(f"/api/v1/projects/{w.p2}/epics", json={"title": "E"}, headers=key())
        missing = await analyst.post(f"/api/v1/projects/{uuid4()}/epics", json={"title": "E"}, headers=key())
        bad = [await analyst.post(f"/api/v1/projects/{w.p1}/epics", json=b, headers=key()) for b in ({"title": ""}, {"title": " "}, {}, {"title": "E", "status": "DONE"})]
    assert denied.status_code == 403
    assert {hidden.status_code, foreign.status_code, other.status_code, missing.status_code} == {404}
    assert stripped(hidden) == stripped(foreign) == stripped(other) == stripped(missing)
    assert [r.status_code for r in bad] == [422] * 4 and w.count("work.epics") == 0


async def test_failed_outbox_insert_rolls_back_the_epic_the_event_the_audit_and_the_idempotency_record(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aggregate_events, "_INSERT_OUTBOX", text("INSERT INTO audit.no_such_outbox (id) VALUES (:id)"))
    headers = key()
    async with await w.client("analyst") as c:
        r = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "Doomed"}, headers=headers)
    assert r.status_code == 500 and "no_such_outbox" not in r.text
    assert w.count("work.epics") == 0 and w.count("work.epic_events") == 0 and w.count("audit.outbox_events") == 0
    assert w.count("platform.idempotency_records") == 0 and w.count("audit.audit_events", "action = 'EPIC_CREATE'") == 0
    monkeypatch.undo()
    async with await w.client("analyst") as c:
        retry = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "Doomed"}, headers=headers)
    assert retry.status_code == 201 and w.count("work.epics") == 1


# ---------------------------------------------------------------- requirements
async def register(c: httpx.AsyncClient, project: UUID, **body: Any) -> httpx.Response:
    return await c.post(f"/api/v1/projects/{project}/requirements", json={"statement": "The system shall X", "registrationKind": "CANDIDATE", **body}, headers=key())


async def test_register_candidate_is_a_candidate_not_an_approval_with_event_and_unverified_evidence(w: World) -> None:
    evidence = [str(uuid4())]
    async with await w.client("analyst") as c:
        r = await register(c, w.p1, requirementType="FR", evidenceRefs=evidence)
        unknown = await register(c, w.p1, requirementType="SAFETY", registrationKind="PROJECT_REQUIREMENT_PROPOSAL")
        untyped = await register(c, w.p1)
        listed = await c.get(f"/api/v1/projects/{w.p1}/requirements")
    assert r.status_code == unknown.status_code == untyped.status_code == 201
    conforms(r.json(), "Requirement")
    assert r.json()["lifecycleStatus"] == "CANDIDATE" and r.json()["displayId"] == "REQ-000001" and unknown.json()["displayId"] == "REQ-000002"
    assert r.headers["etag"] and len(listed.json()["data"]) == 3
    rid = UUID(r.json()["id"])
    [(version_status, rtype, refs, author)] = w.rows("SELECT status, requirement_type, provenance_refs, author_type FROM requirements.requirement_versions WHERE requirement_id = %s", rid)
    assert (version_status, rtype, author) == ("CANDIDATE", "FR", "USER") and refs == [{"type": "EVIDENCE_REF", "id": evidence[0], "verified": False}]
    assert w.rows("SELECT requirement_type, declared_type_text FROM requirements.requirement_versions WHERE requirement_id = %s", UUID(unknown.json()["id"])) == [("UNKNOWN", "SAFETY")], "an unknown type is kept as text, never mapped to a neighbour"
    assert w.rows("SELECT requirement_type, declared_type_text FROM requirements.requirement_versions WHERE requirement_id = %s", UUID(untyped.json()["id"])) == [("UNKNOWN", "UNSPECIFIED")]
    [envelope] = outbox(w, rid)
    event_conforms(envelope)
    assert envelope["type"] == "aires.requirement.version.created.v1" and envelope["data"]["versionNumber"] == 1
    assert w.count("governance.approvals") == 0


async def test_register_candidate_acl_idempotency_and_validation(w: World) -> None:
    headers = key()
    async with await w.client("analyst") as analyst, await w.client("viewer") as viewer, await w.client("outsider") as outsider:
        a = await analyst.post(f"/api/v1/projects/{w.p1}/requirements", json={"statement": "S", "registrationKind": "CANDIDATE"}, headers=headers)
        b = await analyst.post(f"/api/v1/projects/{w.p1}/requirements", json={"statement": "S", "registrationKind": "CANDIDATE"}, headers=headers)
        conflict = await analyst.post(f"/api/v1/projects/{w.p1}/requirements", json={"statement": "T", "registrationKind": "CANDIDATE"}, headers=headers)
        denied = await register(viewer, w.p1)
        hidden = await register(outsider, w.p1)
        foreign = await register(analyst, w.pb)
        bad = [await register(analyst, w.p1, statement=""), await register(analyst, w.p1, registrationKind="APPROVED"), await register(analyst, w.p1, evidenceRefs=["nope"]),
               await register(analyst, w.p1, status="APPROVED")]
    assert a.json() == b.json() and conflict.status_code == 409 and denied.status_code == 403 and hidden.status_code == foreign.status_code == 404
    assert [r.status_code for r in bad] == [422] * 4
    assert w.count("requirements.requirements") == 1


async def test_propose_version_creates_an_immutable_candidate_and_stale_if_match_is_412(w: World) -> None:
    async with await w.client("analyst") as c:
        reg = await register(c, w.p1, requirementType="NFR")
        rid, etag = reg.json()["id"], reg.headers["etag"]
        body = {"statement": "The system shall Y", "changeReason": "clarified", "rationale": "because"}
        missing = await c.post(f"/api/v1/requirements/{rid}/versions", json=body, headers=key())
        ok = await c.post(f"/api/v1/requirements/{rid}/versions", json=body, headers={**key(), "If-Match": etag})
        stale = await c.post(f"/api/v1/requirements/{rid}/versions", json=body, headers={**key(), "If-Match": etag})
        versions = await c.get(f"/api/v1/requirements/{rid}/versions")
    assert (missing.status_code, ok.status_code, stale.status_code) == (428, 201, 412)
    conforms(ok.json(), "RequirementVersion")
    assert ok.json()["versionNumber"] == 2 and ok.json()["changeReason"] == "clarified" and ok.headers["etag"] != etag
    assert [v["versionNumber"] for v in versions.json()["data"]] == [1, 2]
    rows = w.rows("SELECT version_number, status, statement, requirement_type FROM requirements.requirement_versions WHERE requirement_id = %s ORDER BY version_number", UUID(rid))
    assert rows == [(1, "CANDIDATE", "The system shall X", "NFR"), (2, "CANDIDATE", "The system shall Y", "NFR")], "the first version is untouched and the type carries over"
    assert w.rows("SELECT current_version_id = %s FROM requirements.requirements WHERE id = %s", UUID(ok.json()["id"]), UUID(rid)) == [(True,)]
    events = [e["data"] for e in outbox(w, UUID(rid))]
    assert [e["versionNumber"] for e in events] == [1, 2] and [e["aggregateSequence"] for e in events] == [1, 2]
    event_conforms(outbox(w, UUID(rid))[1])


async def test_concurrent_proposals_with_the_same_if_match_produce_exactly_one_version(w: World) -> None:
    async with await w.client("analyst") as c:
        reg = await register(c, w.p1)
        rid, etag = reg.json()["id"], reg.headers["etag"]
        results = await asyncio.gather(*[c.post(f"/api/v1/requirements/{rid}/versions", json={"statement": f"v{i}", "changeReason": "r"}, headers={**key(), "If-Match": etag}) for i in range(5)])
    assert sorted(r.status_code for r in results) == [201, 412, 412, 412, 412]
    assert w.count("requirements.requirement_versions", "requirement_id = %s", UUID(rid)) == 2


async def test_propose_version_idempotent_retry_acl_and_idor(w: World) -> None:
    async with await w.client("analyst") as analyst, await w.client("viewer") as viewer, await w.client("outsider") as outsider, await w.client("padmin", mfa=True) as padmin:
        reg = await register(analyst, w.p1)
        rid, etag = reg.json()["id"], reg.headers["etag"]
        headers = {**key(), "If-Match": etag}
        body = {"statement": "Y", "changeReason": "r"}
        first = await analyst.post(f"/api/v1/requirements/{rid}/versions", json=body, headers=headers)
        replay = await analyst.post(f"/api/v1/requirements/{rid}/versions", json=body, headers=headers)
        denied = await viewer.post(f"/api/v1/requirements/{rid}/versions", json=body, headers={**key(), "If-Match": first.headers["etag"]})
        hidden = await outsider.post(f"/api/v1/requirements/{rid}/versions", json=body, headers={**key(), "If-Match": etag})
        missing = await padmin.post(f"/api/v1/requirements/{uuid4()}/versions", json=body, headers={**key(), "If-Match": etag})
        bad = [await analyst.post(f"/api/v1/requirements/{rid}/versions", json=b, headers={**key(), "If-Match": first.headers["etag"]}) for b in ({"statement": "Y"}, {"changeReason": "r"}, {"statement": " ", "changeReason": "r"})]
    assert first.status_code == replay.status_code == 201 and first.json() == replay.json()
    assert w.count("requirements.requirement_versions", "requirement_id = %s", UUID(rid)) == 2
    assert denied.status_code == 403 and hidden.status_code == missing.status_code == 404 and stripped(hidden) == stripped(missing)
    assert [r.status_code for r in bad] == [422] * 3


async def test_an_existing_version_cannot_be_rewritten_through_the_runtime_role(w: World) -> None:
    async with await w.client("analyst") as c:
        reg = await register(c, w.p1)
        await c.post(f"/api/v1/requirements/{reg.json()['id']}/versions", json={"statement": "Y", "changeReason": "r"}, headers={**key(), "If-Match": reg.headers["etag"]})
        assert (await c.put(f"/api/v1/requirements/{reg.json()['id']}/versions/{reg.json()['currentVersionId']}", json={"statement": "Z"})).status_code in (404, 405)
    rid = UUID(reg.json()["id"])
    with w.iam.pg.connect() as sc:
        sc.execute("UPDATE requirements.requirement_versions SET status = 'CONFIRMED', confirmed_by = %s, confirmed_at = now() WHERE requirement_id = %s AND version_number = 1", [w.u["analyst"], rid])
    factory = create_session_factory(w.iam.engine())
    with pytest.raises(DBAPIError):
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(w.iam.org_a, w.p1)
            await uow.session.execute(text("UPDATE requirements.requirement_versions SET statement = 'tampered' WHERE requirement_id = :r AND version_number = 1"), {"r": rid})
    assert w.rows("SELECT statement FROM requirements.requirement_versions WHERE requirement_id = %s AND version_number = 1", rid) == [("The system shall X",)]


# ---------------------------------------------------------------- createUploadIntent
def upload_body(project: UUID, **over: Any) -> dict[str, Any]:
    return {"projectId": str(project), "fileName": "spec.pdf", "contentType": PDF, "sizeBytes": 1234, "sha256": SHA, **over}


async def test_upload_intent_is_short_lived_object_scoped_and_binds_type_size_and_checksum(w: World) -> None:
    async with await w.client("analyst") as c:
        r = await c.post("/api/v1/uploads", json=upload_body(w.p1, fileName="../../etc/passwd\x00.pdf"), headers=key())
    assert r.status_code == 201, r.text
    conforms(r.json(), "UploadIntent")
    body = r.json()
    url = httpx.URL(body["uploadUrl"])
    upload_id = UUID(body["uploadId"])
    assert url.host == "files.example.test" and url.path == f"/ai-res-sources/{w.iam.org_a}/{w.p1}/{upload_id}", "the object key is opaque: no file name in it"
    assert body["requiredHeaders"] == {"content-type": PDF, "content-length": "1234", "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(SHA)).decode()}
    query = dict(url.params.multi_items())
    assert 290 <= int(query["X-Amz-Expires"]) <= 300 and query["X-Amz-SignedHeaders"] == "content-length;content-type;host;x-amz-checksum-sha256" and "test-secret-key-not-real" not in str(url)
    assert w.rows("SELECT status, declared_size_bytes, declared_media_type, encode(declared_sha256, 'hex'), object_key FROM sources.uploads WHERE id = %s", upload_id) == [
        ("PENDING", 1234, PDF, SHA, f"{w.iam.org_a}/{w.p1}/{upload_id}")]
    assert w.rows("SELECT source_kind, title FROM sources.sources WHERE project_id = %s", w.p1) == [("FILE", "passwd.pdf")]
    assert w.count("audit.outbox_events") == 0, "AsyncAPI v1.6 has no upload-intent message: none is invented (ADR-082)"
    assert w.count("audit.audit_events", "action = 'UPLOAD_INTENT_CREATE'") == 1


async def test_upload_intent_limits_acl_idor_and_idempotency(w: World) -> None:
    headers = key()
    async with await w.client("analyst") as analyst, await w.client("viewer") as viewer, await w.client("outsider") as outsider:
        first = await analyst.post("/api/v1/uploads", json=upload_body(w.p1), headers=headers)
        replay = await analyst.post("/api/v1/uploads", json=upload_body(w.p1), headers=headers)
        reused = await analyst.post("/api/v1/uploads", json=upload_body(w.p1, sizeBytes=99), headers=headers)
        too_big = await analyst.post("/api/v1/uploads", json=upload_body(w.p1, sizeBytes=1_000_001), headers=key())
        wrong_type = await analyst.post("/api/v1/uploads", json=upload_body(w.p1, contentType="application/x-msdownload"), headers=key())
        denied = await viewer.post("/api/v1/uploads", json=upload_body(w.p1), headers=key())
        hidden = await outsider.post("/api/v1/uploads", json=upload_body(w.p1), headers=key())
        foreign = await analyst.post("/api/v1/uploads", json=upload_body(w.pb), headers=key())
        missing = await analyst.post("/api/v1/uploads", json=upload_body(uuid4()), headers=key())
        bad = [await analyst.post("/api/v1/uploads", json=upload_body(w.p1, **o), headers=key()) for o in ({"sha256": "xyz"}, {"sizeBytes": 0}, {"fileName": ""}, {"projectId": "nope"})]
    assert first.status_code == replay.status_code == 201 and first.json()["uploadId"] == replay.json()["uploadId"] and first.json()["requiredHeaders"] == replay.json()["requiredHeaders"]
    assert reused.status_code == 409 and too_big.status_code == wrong_type.status_code == 422 and denied.status_code == 403
    assert hidden.status_code == foreign.status_code == missing.status_code == 404 and stripped(hidden) == stripped(foreign) == stripped(missing)
    assert [r.status_code for r in bad] == [422] * 4
    assert w.count("sources.uploads") == 1 and w.count("sources.sources") == 1, "only the first request created anything"


async def test_an_expired_intent_cannot_be_replayed_into_a_fresh_url(iam_world: Any, tmp_path: Path) -> None:
    short = World(iam_world, tmp_path, storage=StorageConfig("https://files.example.test", "ai-res-sources", "us-east-1", STORAGE.credentials, 1_000_000, frozenset({PDF}), 3))
    headers = key()
    async with await short.client("analyst") as c:
        first = await c.post("/api/v1/uploads", json=upload_body(short.p1), headers=headers)
        await asyncio.sleep(3.6)
        replay = await c.post("/api/v1/uploads", json=upload_body(short.p1), headers=headers)
    assert first.status_code == 201 and replay.status_code == 409 and replay.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert short.count("sources.uploads") == 1


async def test_uploads_fail_closed_when_the_object_store_is_not_configured(iam_world: Any, tmp_path: Path) -> None:
    unconfigured = World(iam_world, tmp_path, storage=None)
    async with await unconfigured.client("analyst") as c:
        r = await c.post("/api/v1/uploads", json=upload_body(unconfigured.p1), headers=key())
    assert r.status_code == 503 and r.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert unconfigured.count("sources.uploads") == 0 and unconfigured.count("sources.sources") == 0


async def test_writes_fail_closed_without_an_idempotency_key_ring(iam_world: Any, tmp_path: Path) -> None:
    broken = World(iam_world, tmp_path)
    broken.settings = broken.settings.model_copy(update={"idempotency_keyring_file": tmp_path / "missing.keys"})
    broken.services.settings = broken.settings
    app = create_app(broken.settings, identity=broken.services, storage=STORAGE)
    broken.app = app
    async with await broken.client("analyst") as c:
        r = await c.post(f"/api/v1/projects/{broken.p1}/epics", json={"title": "E"}, headers=key())
    assert r.status_code == 503 and broken.count("work.epics") == 0


async def test_a_policy_engine_outage_refuses_the_write(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(*_: Any, **__: Any) -> Any:
        raise RuntimeError("engine down")
    monkeypatch.setattr(w.services.enforcer._engine, "decide", down)  # noqa: SLF001 - simulating an outage of the in-process engine
    async with await w.client("analyst") as c:
        r = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "E"}, headers=key())
    assert r.status_code == 503 and r.json()["code"] == "POLICY_ENGINE_UNAVAILABLE" and w.count("work.epics") == 0


# ---------------------------------------------------------------- review fixes (reviews/S09_REVIEWS.md)
async def test_a_proposal_on_a_baselined_version_is_refused_and_the_pointer_stays(w: World) -> None:
    async with await w.client("analyst") as c:
        reg = await register(c, w.p1)
        rid = UUID(reg.json()["id"])
        with w.iam.pg.connect() as sc:
            sc.execute("SET session_replication_role = replica")  # bypass the lifecycle guards only to stage a baselined version
            sc.execute("UPDATE requirements.requirement_versions SET status = 'IN_BASELINE', confirmed_by = %s, confirmed_at = now() WHERE requirement_id = %s", [w.u["analyst"], rid])
        refused = await c.post(f"/api/v1/requirements/{rid}/versions", json={"statement": "Y", "changeReason": "r"}, headers={**key(), "If-Match": reg.headers["etag"]})
    assert refused.status_code == 409 and refused.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    assert w.count("requirements.requirement_versions", "requirement_id = %s", rid) == 1 and w.count("audit.outbox_events", "aggregate_id = %s", rid) == 1


async def test_create_project_resumes_after_a_failed_closing_transaction_and_ends_completed(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_res.modules.idempotency.service import IdempotencyService

    body = {"organizationId": str(w.iam.org_a), "name": "Resumed"}
    headers = key()
    real = IdempotencyService.complete
    async def broken(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("closing transaction failed")
    monkeypatch.setattr(IdempotencyService, "complete", broken)
    async with await w.client("oadmin", mfa=True) as c:
        failed = await c.post("/api/v1/projects", json=body, headers=headers)
        assert failed.status_code == 500
        assert w.count("project.projects", "name = 'Resumed'") == 1, "the project exists once; only the record is still open"
        assert w.rows("SELECT status FROM platform.idempotency_records WHERE resource_type = 'PROJECT' OR (resource_type IS NULL AND status = 'IN_PROGRESS')") == [("IN_PROGRESS",)]
        monkeypatch.setattr(IdempotencyService, "complete", real)
        retry = await c.post("/api/v1/projects", json=body, headers=headers)
    assert retry.status_code == 201
    assert w.count("project.projects", "name = 'Resumed'") == 1 and w.count("audit.outbox_events", "aggregate_type = 'PROJECT'") == 1
    assert w.count("audit.audit_events", "action = 'PROJECT_CREATE'") == 1
    assert w.rows("SELECT status, resource_type, resource_id = %s FROM platform.idempotency_records WHERE resource_type = 'PROJECT' OR (resource_type IS NULL AND status = 'IN_PROGRESS')", UUID(retry.json()["id"])) == [("COMPLETED", "PROJECT", True)]


async def test_successful_commands_close_their_idempotency_records(w: World) -> None:
    async with await w.client("analyst") as c:
        epic = await c.post(f"/api/v1/projects/{w.p1}/epics", json={"title": "E"}, headers=key())
    assert w.rows("SELECT status, resource_type, resource_id = %s FROM platform.idempotency_records WHERE resource_type = 'EPIC'", UUID(epic.json()["id"])) == [("COMPLETED", "EPIC", True)]


# ---------------------------------------------------------------- S12: requestOperationCancellation (202 = the request is recorded, not that it is cancelled)
def seed_operation(w: World, status: str, project: UUID | None = None, org: UUID | None = None) -> UUID:
    with w.iam.pg.connect() as c:
        return new_op(c, org or w.iam.org_a, project or w.p1, status)


async def cancel(c: httpx.AsyncClient, op: UUID, headers: dict[str, str] | None = None) -> httpx.Response:
    return await c.post(f"/api/v1/operations/{op}/cancel", headers=headers if headers is not None else key())


async def test_analyst_cancels_a_running_operation_the_answer_is_202_with_location_and_only_a_request_is_recorded(w: World) -> None:
    op = seed_operation(w, "RUNNING")
    async with await w.client("analyst") as c:
        r = await cancel(c, op)
    assert r.status_code == 202 and r.headers["location"] == f"/api/v1/operations/{op}" and r.headers["etag"]
    conforms(r.json(), "Operation")
    assert r.json()["status"] == "CANCEL_REQUESTED" and r.json()["completedAt"] is None  # not cancelled: that comes after reconciliation
    assert w.count("operations.operations", "id = %s AND status = 'CANCEL_REQUESTED' AND cancel_requested_at IS NOT NULL", op) == 1
    assert w.count("audit.outbox_events", "aggregate_id = %s AND destination = 'orchestration.operation-cancel'", op) == 1
    assert w.count("audit.audit_events", "action = 'OPERATION_CANCEL_REQUESTED' AND object_id = %s", op) == 1
    EventContract.from_file(CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml").check(next(e for e in outbox(w, op) if e["type"].endswith("cancel_requested.v1")))


async def test_cancel_of_an_accepted_operation_is_cancelled_at_once_and_queues_no_orchestrator_command(w: World) -> None:
    op = seed_operation(w, "ACCEPTED")
    async with await w.client("padmin", mfa=True) as c:
        r = await cancel(c, op)
    assert r.status_code == 202 and r.json()["status"] == "CANCELLED" and r.json()["completedAt"]
    assert w.count("audit.outbox_events", "aggregate_id = %s AND destination = 'orchestration.operation-cancel'", op) == 0


async def test_cancel_idempotent_retry_returns_the_same_answer_and_writes_nothing_more(w: World) -> None:
    op, k = seed_operation(w, "RUNNING"), key()
    async with await w.client("analyst") as c:
        first, second = await cancel(c, op, k), await cancel(c, op, k)
        other_key = await cancel(c, op)  # a NEW key on a request that is already recorded: still the same state, no new event
    assert first.status_code == second.status_code == other_key.status_code == 202
    assert stripped(first) == stripped(second)
    assert w.count("operations.operation_events", "operation_id = %s AND event_type = 'operation.cancel_requested'", op) == 1


async def test_cancel_needs_an_idempotency_key_and_the_same_key_for_another_operation_is_reused(w: World) -> None:
    op, other, k = seed_operation(w, "RUNNING"), seed_operation(w, "RUNNING"), key()
    async with await w.client("analyst") as c:
        assert (await cancel(c, op, {})).status_code == 422  # the same answer as every other command without a key
        assert (await cancel(c, op, k)).status_code == 202
        reused = await cancel(c, other, k)
    assert reused.status_code == 409 and reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert w.count("operations.operations", "id = %s AND status = 'RUNNING'", other) == 1


async def test_a_finished_operation_cannot_be_cancelled_and_stays_untouched(w: World) -> None:
    op = seed_operation(w, "SUCCEEDED")
    async with await w.client("analyst") as c:
        r = await cancel(c, op)
    assert r.status_code == 409 and r.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    assert w.count("operations.operations", "id = %s AND status = 'SUCCEEDED'", op) == 1


async def test_cancel_acl_viewer_is_403_and_foreign_missing_and_unreadable_are_one_identical_404(w: World) -> None:
    mine, in_p2, in_org_b = seed_operation(w, "RUNNING"), seed_operation(w, "RUNNING", w.p2), seed_operation(w, "RUNNING", w.pb, w.iam.org_b)
    async with await w.client("viewer") as c:
        denied = await cancel(c, mine)
    async with await w.client("analyst") as c:
        answers = [await cancel(c, in_p2), await cancel(c, in_org_b), await cancel(c, uuid4())]
    assert denied.status_code == 403  # the viewer sees the operation, so an honest refusal
    assert [a.status_code for a in answers] == [404, 404, 404] and stripped(answers[0]) == stripped(answers[1]) == stripped(answers[2])
    assert w.count("operations.operations", "id = ANY(%s) AND status = 'RUNNING'", [mine, in_p2, in_org_b]) == 3  # nothing changed anywhere


async def test_cancel_requires_a_session_csrf_and_a_known_origin(w: World) -> None:
    op = seed_operation(w, "RUNNING")
    async with await w.client(None) as c:
        assert (await cancel(c, op)).status_code == 401
    async with await w.client("analyst", csrf=False) as c:
        assert (await cancel(c, op)).status_code == 403
    async with await w.client("analyst", origin=False) as c:
        assert (await cancel(c, op)).status_code == 403
    assert w.count("operations.operations", "id = %s AND status = 'RUNNING'", op) == 1


async def test_parallel_cancels_with_different_keys_record_exactly_one_request(w: World) -> None:
    op = seed_operation(w, "RUNNING")
    async with await w.client("analyst") as c:
        results = await asyncio.gather(*(cancel(c, op) for _ in range(5)))
    assert all(r.status_code in (202, 409) for r in results) and any(r.status_code == 202 for r in results)
    assert w.count("operations.operation_events", "operation_id = %s AND event_type = 'operation.cancel_requested'", op) == 1


# ---------------------------------------------------------------- S12: completeUpload (the object store's view decides; the pipeline itself is S27)
class FakeS3:
    """An in-process S3 responder behind the REAL `S3ObjectStore` (HTTP + presigned HEAD): only the network hop is replaced. Keys map to (size, sha256-hex | None)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[int, str | None]] = {}
        self.down = False
        self.heads: list[str] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.down:
                return httpx.Response(503)
            assert request.method == "HEAD" and "X-Amz-Signature" in str(request.url) and request.headers.get("x-amz-checksum-mode") == "ENABLED"
            key = request.url.path.removeprefix("/ai-res-sources/")
            self.heads.append(key)
            if key not in self.objects:
                return httpx.Response(404)
            size, digest = self.objects[key]
            headers = {"content-length": str(size)}
            if digest is not None:
                headers["x-amz-checksum-sha256"] = base64.b64encode(bytes.fromhex(digest)).decode()
            return httpx.Response(200, headers=headers)
        return httpx.MockTransport(handler)


@pytest.fixture
def s3() -> FakeS3:
    return FakeS3()


@pytest.fixture
def wu(iam_world: Any, tmp_path: Path, s3: FakeS3) -> World:
    store = S3ObjectStore(STORAGE.endpoint, STORAGE.bucket, STORAGE.region, STORAGE.credentials, transport=s3.transport())
    return World(iam_world, tmp_path, object_store=store)


async def new_intent(w: World, who: str = "analyst", **over: Any) -> tuple[UUID, str]:
    async with await w.client(who) as c:
        r = await c.post("/api/v1/uploads", json=upload_body(w.p1, **over), headers=key())
    assert r.status_code == 201, r.text
    upload_id = UUID(r.json()["uploadId"])
    return upload_id, w.rows("SELECT object_key FROM sources.uploads WHERE id = %s", upload_id)[0][0]


async def complete(c: httpx.AsyncClient, upload: UUID, sha: str = SHA, headers: dict[str, str] | None = None) -> httpx.Response:
    return await c.post(f"/api/v1/uploads/{upload}/complete", json={"sha256": sha}, headers=headers if headers is not None else key())


def upload_state(w: World, upload: UUID) -> tuple[Any, ...]:
    return w.rows("SELECT status, rejection_code FROM sources.uploads WHERE id = %s", upload)[0]


async def test_complete_upload_verifies_the_stored_object_creates_the_version_and_a_source_ingestion_operation(wu: World, s3: FakeS3) -> None:
    upload, object_key = await new_intent(wu)
    s3.objects[object_key] = (1234, SHA)
    async with await wu.client("analyst") as c:
        r = await complete(c, upload)
    assert r.status_code == 202, r.text
    conforms(r.json(), "Operation")
    op = UUID(r.json()["id"])
    assert r.headers["location"] == f"/api/v1/operations/{op}" and r.json()["operationType"] == "SOURCE_INGESTION" and r.json()["status"] == "ACCEPTED"
    assert upload_state(wu, upload) == ("VERIFIED", None)
    assert wu.rows("SELECT version_number, encode(checksum_sha256,'hex'), size_bytes FROM sources.source_versions WHERE upload_id = %s", upload) == [(1, SHA, 1234)]
    assert wu.count("audit.outbox_events", "aggregate_id = %s AND destination = 'orchestration.operation-start'", op) == 0  # no start command before G-107 is closed
    assert wu.count("audit.audit_events", "action = 'UPLOAD_COMPLETE' AND object_id IS NOT NULL") == 1


@pytest.mark.parametrize(("stored", "code"), [((1234, "cd" * 32), "CHECKSUM_MISMATCH"), ((1233, SHA), "SIZE_MISMATCH"), ((1234, None), "CHECKSUM_MISMATCH")],
                         ids=["other-checksum", "other-size", "store-reports-no-verified-checksum"])
async def test_a_bad_object_is_rejected_persistently_and_never_becomes_a_version(wu: World, s3: FakeS3, stored: tuple[int, str | None], code: str) -> None:
    upload, object_key = await new_intent(wu)
    s3.objects[object_key] = stored
    async with await wu.client("analyst") as c:
        r = await complete(c, upload)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "object"
    assert upload_state(wu, upload) == ("REJECTED", code)  # the verdict outlived the failed request
    assert wu.count("sources.source_versions", "upload_id = %s", upload) == 0 and wu.count("operations.operations", "operation_type = 'SOURCE_INGESTION'") == 0
    async with await wu.client("analyst") as c:
        assert (await complete(c, upload)).status_code == 409  # a rejected upload cannot be completed later


async def test_object_not_uploaded_yet_store_outage_and_wrong_client_checksum_change_nothing(wu: World, s3: FakeS3) -> None:
    upload, object_key = await new_intent(wu)
    async with await wu.client("analyst") as c:
        not_ready = await complete(c, upload)
        s3.objects[object_key] = (1234, SHA)
        s3.down = True
        outage = await complete(c, upload)
        s3.down = False
        wrong = await complete(c, upload, sha="cd" * 32)
    assert (not_ready.status_code, outage.status_code, wrong.status_code) == (409, 503, 422)
    assert not_ready.json()["code"] == "OPERATION_NOT_READY" and wrong.json()["errors"][0]["field"] == "sha256"
    assert upload_state(wu, upload) == ("PENDING", None) and wu.count("operations.operations", "operation_type = 'SOURCE_INGESTION'") == 0


async def test_complete_is_idempotent_for_the_same_key_and_a_second_key_cannot_complete_it_again(wu: World, s3: FakeS3) -> None:
    upload, object_key = await new_intent(wu)
    s3.objects[object_key] = (1234, SHA)
    k = key()
    async with await wu.client("analyst") as c:
        first, second = await complete(c, upload, headers=k), await complete(c, upload, headers=k)
        again = await complete(c, upload)
    assert first.status_code == second.status_code == 202 and first.json()["id"] == second.json()["id"]
    assert again.status_code == 409 and again.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    assert wu.count("sources.source_versions", "upload_id = %s", upload) == 1 and wu.count("operations.operations", "operation_type = 'SOURCE_INGESTION'") == 1


async def test_an_expired_upload_is_marked_expired_and_a_late_object_is_not_accepted(iam_world: Any, tmp_path: Path, s3: FakeS3) -> None:
    short = StorageConfig(STORAGE.endpoint, STORAGE.bucket, STORAGE.region, STORAGE.credentials, 1_000_000, frozenset({PDF}), 3)  # expires_at is immutable: use a short TTL
    w = World(iam_world, tmp_path, storage=short, object_store=S3ObjectStore(short.endpoint, short.bucket, short.region, short.credentials, transport=s3.transport()))
    upload, object_key = await new_intent(w)
    s3.objects[object_key] = (1234, SHA)
    await asyncio.sleep(3.6)
    async with await w.client("analyst") as c:
        r = await complete(c, upload)
    assert r.status_code == 422 and upload_state(w, upload) == ("EXPIRED", None) and w.count("sources.source_versions", "upload_id = %s", upload) == 0
    assert s3.heads == []  # an expired intent is decided before the store is asked


async def test_complete_upload_acl_viewer_is_403_and_foreign_missing_are_one_identical_404(wu: World, s3: FakeS3) -> None:
    upload, object_key = await new_intent(wu)
    s3.objects[object_key] = (1234, SHA)
    async with await wu.client("viewer") as v:
        denied = await complete(v, upload)
    async with await wu.client("outsider") as o:
        foreign, missing = await complete(o, upload), await complete(o, uuid4())
    assert denied.status_code == 403 and (foreign.status_code, missing.status_code) == (404, 404) and stripped(foreign) == stripped(missing)
    assert upload_state(wu, upload) == ("PENDING", None) and s3.heads == []  # nothing was even asked of the store
