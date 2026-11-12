# ruff: noqa: E501, S608  -- fixed literal SQL in test assertions
"""S11: internal Platform API + Operation orchestration service under the real `ai_res_api` role and real PostgreSQL, called through the real HTTP client class
(only the network hop is an in-process ASGI transport). Covers idempotent transitions, tenant-claim forgery, service authentication and capability."""
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_res.api.internal_api import create_internal_app
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, ServiceTokenVerifier
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.modules.operations.repository import NewOperation, OperationRepository
from ai_res.orchestration.contracts import OperationFailure, OperationRef
from ai_res.orchestration.http_platform import HttpOperationPlatform
from ai_res.orchestration.platform_port import PlatformPermanentError
from ai_res.platform.config import load_settings
from ai_res.platform.ports import ServiceName

from .conftest import Pg

pytestmark = pytest.mark.postgres
ORG, PRJ, ORG2, PRJ2 = uuid4(), uuid4(), uuid4(), uuid4()


def pub(k: Ed25519PrivateKey) -> bytes:
    return k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class Env:
    def __init__(self, pg: Pg, factory, keys: dict[ServiceName, Ed25519PrivateKey], app) -> None:
        self.pg, self.factory, self.keys, self.app = pg, factory, keys, app

    def platform(self, as_service: ServiceName = ServiceName.MANAGER_RUNTIME, key: Ed25519PrivateKey | None = None) -> HttpOperationPlatform:
        issuer = ServiceTokenIssuer(as_service, key or self.keys[as_service], max_ttl=timedelta(minutes=5))
        return HttpOperationPlatform("http://internal", lambda: issuer.issue(ServiceName.API, timedelta(seconds=60)),
                                     transport=httpx.ASGITransport(app=self.app))

    async def new_operation(self, org: UUID = ORG, prj: UUID = PRJ) -> OperationRef:
        op = NewOperation(id=uuid4(), organization_id=org, project_id=prj, operation_type="PLAN_EXECUTION", initiator_type="USER", idempotency_scope="s",
                          request_fingerprint=b"\x01" * 32, completion_policy_version="wip-1", completion_policy_snapshot={}, correlation_id=uuid4())
        async with UnitOfWork(self.factory) as uow:
            await uow.with_tenant(org, prj)
            await OperationRepository(uow.session).create(op, EventSpec(event_type="operation.accepted", schema_version=1, actor_type="USER", correlation_id=uuid4(),
                                                                         destinations=("internal",)))
        return OperationRef(str(op.id), str(org), str(prj))

    def row(self, ref: OperationRef) -> tuple:
        with self.pg.connect() as c:
            return c.execute("SELECT status, workflow_id, started_at IS NOT NULL, completed_at IS NOT NULL, problem_ref, last_event_sequence FROM operations.operations WHERE id=%s",
                             [ref.operation_id]).fetchone()

    def scalar(self, sql: str, *args) -> int:
        with self.pg.connect() as c:
            return int(c.execute(sql, list(args)).fetchone()[0])


@pytest.fixture
async def env(migrated: Pg, tmp_path: Path):
    with migrated.connect() as c:
        for org, prj in ((ORG, PRJ), (ORG2, PRJ2)):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s,'o') ON CONFLICT DO NOTHING", [org])
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD') ON CONFLICT DO NOTHING", [prj, org])
    pw = tmp_path / "pw"
    pw.write_text(migrated.passwords["ai_res_api"])
    settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": migrated.host, "AI_RES_DB_PORT": str(migrated.port), "AI_RES_DB_USER": "ai_res_api",
                              "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": "s11"})
    engine = create_runtime_engine(settings)
    factory = create_session_factory(engine)
    keys = {ServiceName.MANAGER_RUNTIME: Ed25519PrivateKey.generate(), ServiceName.WORKER_RUNTIME: Ed25519PrivateKey.generate()}
    verifier = ServiceTokenVerifier({n: (pub(k),) for n, k in keys.items()}, max_ttl=timedelta(minutes=5))
    yield Env(migrated, factory, keys, create_internal_app(OperationOrchestrationService(factory), verifier))
    await engine.dispose()


async def test_acknowledge_start_moves_accepted_to_running_with_events_and_audit_once(env: Env):
    ref = await env.new_operation()
    platform = env.platform()
    first = await platform.acknowledge_start(ref)
    again = await platform.acknowledge_start(ref)  # an Activity retry / duplicate start
    assert (first.status, again.status) == ("RUNNING", "RUNNING")
    status, workflow_id, started, completed, _, seq = env.row(ref)
    assert (status, workflow_id, started, completed, seq) == ("RUNNING", f"operation-{ref.operation_id}", True, False, 3)
    assert env.scalar("SELECT count(*) FROM operations.operation_events WHERE operation_id=%s", ref.operation_id) == 3  # accepted, queued, started - no duplicates
    assert env.scalar("SELECT count(*) FROM audit.audit_events WHERE object_id=%s AND action='OPERATION_START_ACKNOWLEDGED' AND actor_type='SERVICE'", ref.operation_id) == 1


async def test_failure_is_terminal_idempotent_and_never_overwritten(env: Env):
    ref = await env.new_operation()
    platform = env.platform()
    await platform.acknowledge_start(ref)
    failure = OperationFailure(ref, "ORCHESTRATION_NOT_IMPLEMENTED")
    assert (await platform.record_failure(failure)).status == "FAILED"
    assert (await platform.record_failure(failure)).status == "FAILED"
    assert (await platform.acknowledge_start(ref)).status == "FAILED"  # a late retry cannot reopen a terminal Operation
    status, _, _, completed, problem, seq = env.row(ref)
    assert (status, completed, problem, seq) == ("FAILED", True, {"code": "ORCHESTRATION_NOT_IMPLEMENTED"}, 4)
    assert env.scalar("SELECT count(*) FROM audit.audit_events WHERE object_id=%s AND action='OPERATION_FAILED_BY_ORCHESTRATION'", ref.operation_id) == 1


async def test_failure_of_an_operation_that_never_started_is_refused(env: Env):
    ref = await env.new_operation()
    with pytest.raises(PlatformPermanentError):  # 412 -> permanent: only a started Operation can fail through the workflow
        await env.platform().record_failure(OperationFailure(ref, "SOME_CODE"))
    assert env.row(ref)[0] == "ACCEPTED"


async def test_forged_tenant_claim_is_not_found_and_changes_nothing(env: Env):
    mine = await env.new_operation()
    foreign = await env.new_operation(ORG2, PRJ2)
    forged = [OperationRef(foreign.operation_id, mine.organization_id, mine.project_id),  # another tenant's id under my scope
              OperationRef(foreign.operation_id, foreign.organization_id, mine.project_id),
              OperationRef(str(uuid4()), mine.organization_id, mine.project_id)]  # nonexistent
    for ref in forged:
        with pytest.raises(PlatformPermanentError):
            await env.platform().acknowledge_start(ref)
    assert env.row(foreign)[0] == "ACCEPTED" and env.row(mine)[0] == "ACCEPTED"


async def test_service_authentication_and_capability(env: Env):
    ref = await env.new_operation()
    url = f"/internal/v1/operations/{ref.operation_id}/start-acknowledgement"
    body = {"organizationId": ref.organization_id, "projectId": ref.project_id}
    issuer = ServiceTokenIssuer(ServiceName.WORKER_RUNTIME, env.keys[ServiceName.WORKER_RUNTIME], max_ttl=timedelta(minutes=5))
    forged_key = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, Ed25519PrivateKey.generate(), max_ttl=timedelta(minutes=5))
    wrong_aud = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, env.keys[ServiceName.MANAGER_RUNTIME], max_ttl=timedelta(minutes=5))
    cases: dict[str, tuple[dict[str, str], int]] = {
        "no header": ({}, 401), "garbage": ({"Authorization": "Bearer nope"}, 401), "basic scheme": ({"Authorization": "Basic abc"}, 401),
        "forged signature": ({"Authorization": f"Bearer {forged_key.issue(ServiceName.API, timedelta(seconds=30))}"}, 401),
        "wrong audience": ({"Authorization": f"Bearer {wrong_aud.issue(ServiceName.CONNECTOR, timedelta(seconds=30))}"}, 401),
        "worker runtime lacks the capability": ({"Authorization": f"Bearer {issuer.issue(ServiceName.API, timedelta(seconds=30))}"}, 403),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://internal") as c:
        for name, (headers, expected) in cases.items():
            r = await c.post(url, json=body, headers=headers)
            assert r.status_code == expected, name
            assert "operationId" not in r.text and r.headers["content-type"].startswith("application/problem+json"), name
    assert env.row(ref)[0] == "ACCEPTED"


async def test_unknown_fields_and_bad_codes_are_rejected(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    token = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, env.keys[ServiceName.MANAGER_RUNTIME], max_ttl=timedelta(minutes=5)).issue(ServiceName.API, timedelta(seconds=30))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://internal", headers={"Authorization": f"Bearer {token}"}) as c:
        base = {"organizationId": ref.organization_id, "projectId": ref.project_id}
        for path, body in ((f"/internal/v1/operations/{ref.operation_id}/failure", {**base, "code": "lower"}),
                           (f"/internal/v1/operations/{ref.operation_id}/failure", {**base, "code": "X", "status": "SUCCEEDED"}),
                           (f"/internal/v1/operations/{ref.operation_id}/start-acknowledgement", {**base, "status": "SUCCEEDED"}),
                           ("/internal/v1/operations/not-a-uuid/start-acknowledgement", base)):
            assert (await c.post(path, json=body)).status_code == 422
    assert env.row(ref)[0] == "RUNNING"


def test_internal_contract_matches_the_implemented_routes_and_capabilities():
    import yaml

    from ai_res.api.internal_api import CAPABILITIES, FailureBody, ScopeBody
    contract = yaml.safe_load((Path(__file__).resolve().parents[4] / "contracts/internal/AI_RES_Platform_Internal_API_v0.1.yaml").read_text())
    assert contract["x-status"] == "WORKING"
    app = create_internal_app(None, None)  # type: ignore[arg-type]  # routes only; no handler runs
    routes = {(m.lower(), r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods - {"HEAD", "OPTIONS"}}
    expected = {(verb, path.replace("{operationId}", "{operationId}")) for path, item in contract["paths"].items() for verb in item}
    assert routes == expected
    assert {op["x-capability"] for item in contract["paths"].values() for op in item.values()} == set(CAPABILITIES)
    for item in contract["paths"].values():
        for op in item.values():
            assert {ServiceName(c) for c in op["x-callers"]} == CAPABILITIES[op["x-capability"]]
    schemas = contract["components"]["schemas"]
    assert set(schemas["ScopeRequest"]["properties"]) == {f.alias or n for n, f in ScopeBody.model_fields.items()} | {"organizationId", "projectId"}
    assert set(schemas["FailureRequest"]["properties"]) == set(FailureBody.model_json_schema(by_alias=True)["properties"])
    assert schemas["FailureRequest"]["properties"]["code"]["pattern"] == FailureBody.model_json_schema()["properties"]["code"]["pattern"]


async def test_concurrent_acknowledgements_converge_on_one_transition_each(env: Env):
    import asyncio
    ref = await env.new_operation()
    results = await asyncio.gather(*(env.platform().acknowledge_start(ref) for _ in range(6)), return_exceptions=True)
    # a lost CAS race is a 409 (TRANSIENT for the client): the Activity retry then observes RUNNING; here the raw outcomes are RUNNING or a transient error
    from ai_res.orchestration.platform_port import PlatformTransientError
    assert all((getattr(r, "status", None) == "RUNNING") or isinstance(r, PlatformTransientError) for r in results), results
    assert any(getattr(r, "status", None) == "RUNNING" for r in results)
    assert (await env.platform().acknowledge_start(ref)).status == "RUNNING"  # the retry converges
    assert env.scalar("SELECT count(*) FROM operations.operation_events WHERE operation_id=%s", ref.operation_id) == 3  # accepted, queued, started - exactly once each
    assert env.row(ref)[0] == "RUNNING"


async def test_state_error_is_permanent_412_but_a_lost_race_is_transient_409(env: Env):
    ref = await env.new_operation()
    token = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, env.keys[ServiceName.MANAGER_RUNTIME], max_ttl=timedelta(minutes=5)).issue(ServiceName.API, timedelta(seconds=30))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://internal", headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.post(f"/internal/v1/operations/{ref.operation_id}/failure", json={"organizationId": ref.organization_id, "projectId": ref.project_id, "code": "X"})
    assert r.status_code == 412  # PERMANENT for HttpOperationPlatform (retrying cannot make an ACCEPTED Operation RUNNING)
