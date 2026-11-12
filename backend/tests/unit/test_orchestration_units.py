"""S11 unit level: compact contracts, fail-closed versioning, HTTP error classification, start-command validation, Activity error mapping.
Behaviour against real Temporal/PostgreSQL is in tests/integration (this file proves the pure decisions)."""
import uuid
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from ai_res.modules.events import delivery
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.events.temporal_start import TemporalStartPublisher
from ai_res.orchestration.activities import ManagerActivities
from ai_res.orchestration.contracts import (
    CONTRACT_VERSION,
    START_DESTINATION,
    ContractError,
    OperationFailure,
    OperationRef,
    OperationState,
    OperationWorkflowInput,
    assert_compact,
    workflow_id_for,
)
from ai_res.orchestration.http_platform import HttpOperationPlatform
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError
from ai_res.platform.config import load_settings

REF = OperationRef(str(uuid4()), str(uuid4()), str(uuid4()))


def test_workflow_id_is_stable_and_derived_from_the_operation_id():
    op = uuid4()
    assert workflow_id_for(op) == workflow_id_for(op) == f"operation-{op}"
    with pytest.raises(TypeError):
        workflow_id_for(str(op))  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [0, 2, 99, -1, True, "1", None])
def test_unsupported_contract_major_fails_closed(version):
    with pytest.raises(ContractError):
        OperationWorkflowInput(version, REF, str(uuid4()))


@pytest.mark.parametrize("bad", ["", "not-a-uuid", str(uuid4()).upper(), str(uuid4()) + "0", "x" * 100, 5, None])
def test_references_must_be_canonical_uuid_strings(bad):
    with pytest.raises(ContractError):
        OperationRef(bad, str(uuid4()), str(uuid4()))


def test_compact_guard_rejects_content_secrets_and_nested_documents():
    ok = OperationWorkflowInput.create(uuid4(), uuid4(), uuid4(), uuid4())
    assert_compact(ok)
    for payload in ({"prompt": "x"}, {"password": "x"}, {"ref": "a" * 65}, {"doc": {"body": "x"}}, {"items": ["a"]}, {"value": 1.5}):
        with pytest.raises((ContractError, ValueError)):
            assert_compact(payload)


def test_failure_and_state_codes_are_machine_codes_not_free_text():
    for bad in ("lower", "has space", "", "X" * 65, "WITH-DASH"):
        with pytest.raises(ContractError):
            OperationFailure(REF, bad)
    assert OperationState(REF.operation_id, "RUNNING").status == "RUNNING"


def mock_platform(handler):
    return HttpOperationPlatform("http://internal", lambda: "token", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(("status", "expected"), [(500, PlatformTransientError), (503, PlatformTransientError), (429, PlatformTransientError),
                                                  (409, PlatformTransientError), (408, PlatformTransientError), (401, PlatformPermanentError),
                                                  (403, PlatformPermanentError), (404, PlatformPermanentError), (412, PlatformPermanentError),
                                                  (422, PlatformPermanentError), (302, PlatformPermanentError)])
async def test_http_status_classification_transient_vs_permanent(status, expected):
    platform = mock_platform(lambda request: httpx.Response(status, json={"code": "X"}))
    with pytest.raises(expected):
        await platform.acknowledge_start(REF)


async def test_network_faults_are_transient_and_malformed_success_is_permanent():
    def boom(request):
        raise httpx.ConnectError("no route")
    with pytest.raises(PlatformTransientError):
        await mock_platform(boom).acknowledge_start(REF)
    with pytest.raises(PlatformPermanentError):
        await mock_platform(lambda r: httpx.Response(200, json={"status": "lower-case"})).acknowledge_start(REF)
    ok = await mock_platform(lambda r: httpx.Response(200, json={"operationId": REF.operation_id, "status": "RUNNING"})).acknowledge_start(REF)
    assert ok.status == "RUNNING"


async def test_the_client_sends_a_fresh_bearer_token_per_call_and_never_follows_redirects():
    seen: list[str] = []
    tokens = iter(["t1", "t2"])

    def handler(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"operationId": REF.operation_id, "status": "RUNNING"})
    platform = HttpOperationPlatform("http://internal", lambda: next(tokens), transport=httpx.MockTransport(handler))
    await platform.acknowledge_start(REF)
    await platform.acknowledge_start(REF)
    assert seen == ["Bearer t1", "Bearer t2"]


class Boom:
    def __init__(self, exc):
        self.exc = exc

    async def acknowledge_start(self, ref):
        raise self.exc

    async def record_failure(self, failure):
        raise self.exc


@pytest.mark.parametrize(("exc", "non_retryable"), [(PlatformTransientError("x"), False), (PlatformPermanentError("x"), True), (ContractError("x"), True)])
async def test_activity_maps_platform_errors_to_temporal_retry_semantics(exc, non_retryable):
    with pytest.raises(ApplicationError) as err:
        await ManagerActivities._call(Boom(exc).acknowledge_start(REF))
    assert err.value.non_retryable is non_retryable


def row(**over) -> OutboxRow:
    op = uuid4()
    base = dict(id=uuid4(), event_id=uuid4(), destination=START_DESTINATION, aggregate_type="OPERATION", aggregate_id=op, aggregate_sequence=1,
                event_type="operation.accepted", schema_version=1, attempt_count=1, replay_count=0,
                envelope={"data": {"operationId": str(op), "organizationId": str(uuid4()), "projectId": str(uuid4()), "correlationId": str(uuid4())}})
    base.update(over)
    return OutboxRow(**base)


def test_start_command_is_built_from_identifiers_only():
    request = TemporalStartPublisher.request_from(row())
    assert request.contract_version == CONTRACT_VERSION and uuid.UUID(request.operation.operation_id)


@pytest.mark.parametrize("over", [{"destination": "aires.project.events"}, {"aggregate_type": "WORKER_RUN"}, {"event_type": "operation.cancelled"},
                                  {"envelope": {"data": "x"}}, {"envelope": {"data": {}}}, {"envelope": {}}])
def test_anything_but_a_well_formed_start_command_is_permanent(over):
    with pytest.raises(delivery.PermanentDeliveryError):
        TemporalStartPublisher.request_from(row(**over))


def test_start_command_describing_another_aggregate_is_rejected():
    r = row()
    forged = row(aggregate_id=uuid4(), envelope=r.envelope)  # the envelope names an Operation other than the outbox row's aggregate
    with pytest.raises(delivery.PermanentDeliveryError):
        TemporalStartPublisher.request_from(forged)


def test_temporal_settings_are_validated_and_secrets_stay_out_of_env():
    s = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_TEMPORAL_ADDRESS": "temporal:7233"})
    assert s.temporal_namespace == "ai-res" and s.temporal_address == "temporal:7233"
    for bad in ("http://temporal:7233", "temporal", "temporal:7233/x", "user:pw@temporal:7233"):
        with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError or ConfigError, either is a refusal
            load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_TEMPORAL_ADDRESS": bad})
    assert timedelta(seconds=60) <= timedelta(seconds=load_settings({"AI_RES_ENVIRONMENT": "test"}).service_token_max_ttl_seconds)
