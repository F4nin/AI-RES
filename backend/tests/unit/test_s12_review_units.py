"""S12 independent-review follow-ups (reviews/S12_REVIEWS.md): pure-logic tests for stream cursor strictness and contiguity, the object-store response parser,
the 409 retry classification and the cancel publisher's envelope checks."""
import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from ai_res.modules.events import delivery
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.events.stream import MAX_TRACKED, Position, ProjectEventReader, StreamEvent
from ai_res.modules.events.temporal_start import TemporalCancelPublisher
from ai_res.modules.sources.object_store import ObjectStoreError, S3ObjectStore
from ai_res.modules.sources.presign import StorageCredentials
from ai_res.orchestration.contracts import CANCEL_DESTINATION, OperationRef
from ai_res.orchestration.http_platform import HttpOperationPlatform
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError

NOW = datetime(2026, 11, 12, tzinfo=UTC)


def event(agg, seq, second=0):
    return StreamEvent(uuid4(), "OPERATION", agg, seq, "operation.started", NOW + timedelta(seconds=second), None, None, None)


def test_contiguity_holds_back_a_hole_and_keeps_later_events_of_that_aggregate_out():
    a = uuid4()
    position = Position(NOW, {str(a): 1})
    delivered = ProjectEventReader._contiguous([event(a, 3, 1), event(a, 4, 2)], position)
    assert delivered == []  # sequence 2 is missing: nothing after it is delivered (no silent gap)
    assert [e.sequence for e in ProjectEventReader._contiguous([event(a, 2, 0), event(a, 3, 1)], position)] == [2, 3]


def test_contiguity_is_per_aggregate_and_a_new_aggregate_may_start_anywhere():
    a, b = uuid4(), uuid4()
    out = ProjectEventReader._contiguous([event(a, 5, 0), event(b, 1, 1)], Position(NOW, {str(a): 1}))
    assert [e.aggregate_id for e in out] == [b]  # a is held back at its hole, b is unaffected


@pytest.mark.parametrize("keyset", [
    [NOW.isoformat()],  # wrong length
    [NOW.isoformat(), {}, 1],
    [NOW.isoformat(), {str(uuid4()): True}],  # bool is not a sequence
    [NOW.isoformat(), {str(uuid4()): 0}],
    [NOW.isoformat(), {str(uuid4()): "3"}],
    [NOW.isoformat(), {"not-a-uuid": 1}],
    [NOW.replace(tzinfo=None).isoformat(), {}],  # naive watermark
    [NOW.isoformat(), {str(uuid4()): 1 for _ in range(MAX_TRACKED + 1)}],
], ids=["short", "long", "bool", "zero", "str", "bad-uuid", "naive-tz", "overflow"])
def test_a_malformed_cursor_is_refused_not_repaired(keyset):
    with pytest.raises(ValueError):
        Position.from_keyset(keyset)


def test_a_valid_cursor_round_trips():
    a = uuid4()
    p = Position(NOW, {str(a): 7})
    assert Position.from_keyset(p.to_keyset()) == p


def store(handler):
    return S3ObjectStore("https://files.example.test", "b", "us-east-1", StorageCredentials("AK", "SK"), transport=httpx.MockTransport(handler))


def head(headers=None, status=200):
    return store(lambda request: httpx.Response(status, headers=headers or {}))


async def test_object_store_composite_checksum_is_unverifiable_not_an_outage():
    seen = await head({"content-length": "5", "x-amz-checksum-sha256": base64.b64encode(b"\x01" * 32).decode() + "-3"}).stat("k")
    assert seen is not None and seen.sha256 is None  # permanent: rejected by the caller, not retried forever


async def test_object_store_parses_a_verified_object_and_wrong_length_digest_is_unverifiable():
    ok = await head({"content-length": "5", "x-amz-checksum-sha256": base64.b64encode(b"\x01" * 32).decode()}).stat("k")
    short = await head({"content-length": "5", "x-amz-checksum-sha256": base64.b64encode(b"\x01" * 16).decode()}).stat("k")
    none = await head({"content-length": "5"}).stat("k")
    assert (ok.sha256, short.sha256, none.sha256) == (b"\x01" * 32, None, None) and ok.size_bytes == 5


@pytest.mark.parametrize("status", [403, 500, 503])
async def test_object_store_other_statuses_and_network_faults_are_transient_errors(status):
    with pytest.raises(ObjectStoreError):
        await head(status=status).stat("k")

    def boom(request):
        raise httpx.ConnectError("down")
    with pytest.raises(ObjectStoreError):
        await store(boom).stat("k")


async def test_object_store_missing_object_is_none_and_missing_length_is_an_error():
    assert await head(status=404).stat("k") is None
    with pytest.raises(ObjectStoreError):
        await head({}).stat("k")


REF = OperationRef(str(uuid4()), str(uuid4()), str(uuid4()))


def platform(response):
    return HttpOperationPlatform("http://platform", lambda: "token", transport=httpx.MockTransport(lambda request: response))


async def test_409_classification_by_problem_code():
    illegal = httpx.Response(409, json={"code": "STATE_TRANSITION_NOT_ALLOWED"})
    with pytest.raises(PlatformPermanentError):
        await platform(illegal).confirm_cancellation(REF)
    for lost_race in (httpx.Response(409, json={"code": "AGGREGATE_VERSION_CONFLICT"}), httpx.Response(409, text="not json"), httpx.Response(409, json=[1])):
        with pytest.raises(PlatformTransientError):
            await platform(lost_race).confirm_cancellation(REF)


def row(**over):
    op = uuid4()
    base = dict(id=uuid4(), event_id=uuid4(), destination=CANCEL_DESTINATION, aggregate_type="OPERATION", aggregate_id=op, aggregate_sequence=2,
                event_type="operation.cancel_requested", schema_version=1, envelope={"data": {"operationId": str(op)}}, attempt_count=0)
    return OutboxRow(**{**base, **over})


def test_cancel_publisher_accepts_only_a_matching_cancel_envelope():
    r = row()
    assert TemporalCancelPublisher.operation_id_from(r) == r.aggregate_id
    wrong = [row(destination="orchestration.operation-start"), row(aggregate_type="EPIC"), row(event_type="operation.started"), row(envelope={"data": {}}),
             row(envelope={"data": {"operationId": "x"}}), row(envelope={}), row(envelope={"data": {"operationId": str(uuid4())}})]
    for bad in wrong:
        with pytest.raises(delivery.PermanentDeliveryError):
            TemporalCancelPublisher.operation_id_from(bad)
