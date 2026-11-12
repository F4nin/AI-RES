# ruff: noqa: E501, S105, S106  -- fixture credentials
"""S08: schemathesis contract run over every GET operation in scope against contracts/openapi (Public API v1.3), on the real app and PostgreSQL.

Path parameters are replaced by seeded ids of the caller's own project (so the happy path is exercised) or left random (so the 404 problem path is);
query parameters (limit, cursor) are generated, including invalid ones. Every response must conform to the operation's declared responses
(status, headers, content type, body schema) -- Problem responses are the `default` response.
"""
import asyncio
import threading
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import ignored_auth, positive_data_acceptance

from .test_read_api import OAS, World

pytestmark = pytest.mark.postgres
SCOPE = {"listProjects", "getProject", "listEpics", "getEpic", "listTasks", "getTask", "listRequirements", "listRequirementVersions", "listSources",
         "listArtifacts", "listArtifactVersions", "getWorkerRun"}
STATUSES: list[tuple[str, int]] = []
schema = schemathesis.openapi.from_dict(OAS).include(operation_id=sorted(SCOPE))


class Rig:
    """The app lives on its own event loop in a thread so a synchronous hypothesis test can drive it."""

    def __init__(self, world: World) -> None:
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.world = world
        issued = self.run(world.services.sessions.create(world.iam.org_a, world.viewer))
        self.cookie = issued.token
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=world.app, client=("198.51.100.7", 4444)), base_url="http://testserver")

    def run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=60)

    def close(self) -> None:
        self.run(self.client.aclose())
        self.loop.call_soon_threadsafe(self.loop.stop)


@pytest.fixture
def rig(iam_world: Any, tmp_path: Any) -> Iterator[Rig]:
    r = Rig(World(iam_world, tmp_path))
    yield r
    r.close()


def seeded(ids: dict[str, UUID], op: str) -> dict[str, str]:
    mapping = {"getProject": ("projectId", "p1"), "listEpics": ("projectId", "p1"), "listRequirements": ("projectId", "p1"), "listSources": ("projectId", "p1"),
               "listArtifacts": ("projectId", "p1"), "getEpic": ("epicId", "epic1"), "listTasks": ("epicId", "epic1"), "getTask": ("taskId", "task1"),
               "listRequirementVersions": ("requirementId", "req1"), "listArtifactVersions": ("artifactId", "art1"), "getWorkerRun": ("workerRunId", "run1")}
    if op not in mapping:
        return {}
    name, key = mapping[op]
    return {name: str(ids[key])}


@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_get_in_scope_conforms_to_the_openapi_contract(case: Any, request: pytest.FixtureRequest) -> None:
    op = case.operation.definition.raw.get("operationId")
    if case.method.upper() != "GET" or op not in SCOPE:
        return  # schemathesis also yields negative-method probes (e.g. TRACE); a skip here would skip the whole test
    rig: Rig = request.getfixturevalue("rig")
    positive = case.meta is None or str(case.meta.generation.mode).lower().endswith("positive")  # never rewrite the deliberately broken part of a negative case
    if positive and case.path_parameters is not None and seeded(rig.world.ids, op) and hash(str(case.path_parameters)) % 2 == 0:
        case.path_parameters = {**case.path_parameters, **seeded(rig.world.ids, op)}  # half of the examples reach the real object
    kwargs = case.as_transport_kwargs(base_url="http://testserver/api/v1")
    name = rig.world.settings.session_cookie_name
    cookies = dict(kwargs.get("cookies") or {})
    if name in cookies:  # the operation requires the session cookie: send the real one; when the case deliberately omits it (negative data) it stays omitted
        cookies[name] = rig.cookie
    response = rig.run(rig.client.request(kwargs["method"], kwargs["url"], params=kwargs.get("params"), headers=kwargs.get("headers"), cookies=cookies))
    STATUSES.append((op, response.status_code))
    # ignored_auth is excluded: the rig always sends the one valid session cookie, so "invalid generated auth" is never what is sent; the 401 paths of all
    # twelve reads are asserted in test_read_api.py instead. positive_data_acceptance is excluded: an opaque `cursor` string that is schema-valid but not one of
    # our signed cursors is a 400 by design (api-and-contracts.md), and invalid cursors are tested explicitly in test_read_api.py.
    case.validate_response(response, excluded_checks=[ignored_auth, positive_data_acceptance])


def test_the_contract_run_reached_real_objects_not_only_error_responses(rig: Rig) -> None:
    """Guards the guard: a run where every call was a 404 (wrong prefix, wrong ids) would pass the contract check vacuously."""
    ok = {op for op, status in STATUSES if status == 200}
    assert ok >= SCOPE, sorted(SCOPE - ok)
