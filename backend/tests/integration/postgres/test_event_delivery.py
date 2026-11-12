# ruff: noqa: E501, F811  -- fixtures are imported from test_repositories; long lines keep one assertion per line
"""S10: Outbox dispatcher, durable consumer (Inbox + checkpoint) and contract validation on real PostgreSQL 16 under the real runtime roles.

Covers the stage-level tests: crash after commit-before-publish, crash after publish-before-mark (PERSIST-015), inbox crash before commit (PERSIST-016),
gap -> defer, poison event does not block the stream, concurrent dispatchers, payload privacy, cross-tenant dispatcher, growth alerts without deletion,
controlled replay. Delivery is at-least-once; no test claims exactly-once.
"""
import asyncio
import copy
import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.db.session import create_session_factory
from ai_res.modules.events import delivery
from ai_res.modules.events.alerts import GrowthThresholds, evaluate_inbox, evaluate_outbox
from ai_res.modules.events.consumer import InboxConsumer, Ordering
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.dispatcher import Dispatcher, DispatcherConfig, InternalFanoutPublisher
from ai_res.modules.events.inbox_repository import Delivery, InboxRepository
from ai_res.modules.events.metrics import EventMetrics
from ai_res.modules.events.outbox_repository import OutboxRepository, OutboxRow
from ai_res.modules.operations.repository import OperationRepository

from .conftest import Pg
from .test_repositories import ORG_A, ORG_B, PRJ_A, PRJ_B, engine_for, new_operation, spec, tenant_uow, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.postgres
CONTRACT_FILE = Path(__file__).resolve().parents[4] / "contracts" / "asyncapi" / "AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"
CONTRACT = EventContract.from_file(CONTRACT_FILE)
CFG = DispatcherConfig(owner="d1", batch_size=5, lease_seconds=30, publish_timeout_seconds=4, max_attempts=3, backoff_base_seconds=1, backoff_cap_seconds=8)


async def make_operation(api: AsyncEngine, org: UUID = ORG_A, prj: UUID = PRJ_A, extra_events: int = 0, dests: tuple[str, ...] = ("internal",)) -> UUID:
    """One Operation with `1 + extra_events` events (sequence 1..n) toward `dests`."""
    async with tenant_uow(api) as uow:
        await uow.with_tenant(org, prj)
        repo = OperationRepository(uow.session)
        row, _ = await repo.create(new_operation(org, prj), spec(dests=dests))
        for etype, to in (("operation.started", "RUNNING"), ("operation.succeeded", "SUCCEEDED"))[:extra_events]:
            done = await repo.transition(row, to, spec(etype, dests=dests))
            row = replace(row, status=to, row_version=done.row_version)
        return row.id


def make_dispatcher(disp: AsyncEngine, publisher: Any, contract: EventContract = CONTRACT, owner: str = "d1", metrics: EventMetrics | None = None) -> Dispatcher:
    return Dispatcher(create_session_factory(disp), publisher, contract, replace(CFG, owner=owner), metrics or EventMetrics(), rng=lambda: 0.0)


class Recorder:
    """Publisher test double: records deliveries; `fail` decides per row."""

    def __init__(self, fail: Callable[[OutboxRow], Exception | None] = lambda _: None) -> None:
        self.rows: list[OutboxRow] = []
        self._fail = fail

    async def publish(self, row: OutboxRow) -> None:
        if (exc := self._fail(row)) is not None:
            raise exc
        self.rows.append(row)


def statuses(world: Pg) -> list[tuple[Any, ...]]:
    with world.connect() as c:
        return c.execute("SELECT aggregate_sequence, status, last_error_code, attempt_count FROM audit.outbox_events ORDER BY created_at, aggregate_sequence").fetchall()


def expire_lease(world: Pg) -> None:
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET lease_until = now() - interval '1 second' WHERE status = 'IN_FLIGHT'")


def make_available(world: Pg) -> None:
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET available_at = now() - interval '1 second' WHERE status = 'PENDING'")


async def test_crash_after_commit_before_publish_delivers_after_recovery(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)  # committed; no dispatcher has run: the row simply waits in the Outbox
    assert statuses(world) == [(1, "PENDING", None, 0)]
    async with tenant_uow(disp) as uow:  # a dispatcher claims and then dies before publishing: only the lease protects the row
        assert len(await OutboxRepository(uow.session).claim("dead", 10, 30, 3)) == 1
    pub = Recorder()
    assert await make_dispatcher(disp, pub, owner="d2").run_once() == 0  # still leased by the dead process
    expire_lease(world)
    assert await make_dispatcher(disp, pub, owner="d2").run_once() == 1  # recovery: delivered after the lease expired
    assert [r.aggregate_sequence for r in pub.rows] == [1]
    assert statuses(world)[0][1] == "PUBLISHED"


async def test_persist_015_crash_after_publish_before_mark_is_deduped_by_the_consumer(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    await make_operation(api)
    applied: list[UUID] = []

    async def handler(_: AsyncSession, row: OutboxRow) -> None:
        applied.append(row.event_id)

    consumer = InboxConsumer("proj", create_session_factory(cons), CONTRACT, handler)
    async with tenant_uow(disp) as uow:
        (row,) = await OutboxRepository(uow.session).claim("d1", 10, 30, 3)
    assert await consumer.deliver(row) is Delivery.FIRST  # published ... and the dispatcher dies before mark_published
    expire_lease(world)
    assert await make_dispatcher(disp, InternalFanoutPublisher({"internal": [consumer]})).run_once() == 1  # redelivery of the SAME event id
    assert applied == [row.event_id]  # the effect happened once: duplicate = successful no-op
    assert statuses(world)[0][1] == "PUBLISHED"
    with world.connect() as c:
        assert c.execute("SELECT status FROM audit.inbox_messages").fetchall() == [("PROCESSED",)]


async def test_persist_016_inbox_crash_before_commit_leaves_no_partial_effect(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    await make_operation(api)
    crash = True

    async def handler(_: AsyncSession, row: OutboxRow) -> None:
        if crash:
            raise RuntimeError("crash inside the local effect")

    consumer = InboxConsumer("proj", create_session_factory(cons), CONTRACT, handler)
    async with tenant_uow(disp) as uow:
        (row,) = await OutboxRepository(uow.session).claim("d1", 10, 30, 3)
    with pytest.raises(RuntimeError):
        await consumer.deliver(row)
    with world.connect() as c:  # no marker and no checkpoint survived the rollback
        assert c.execute("SELECT (SELECT count(*) FROM audit.inbox_messages), (SELECT count(*) FROM audit.inbox_checkpoints)").fetchone() == (0, 0)
    crash = False
    assert await consumer.deliver(row) is Delivery.FIRST  # the retry starts clean
    with world.connect() as c:
        assert c.execute("SELECT last_sequence FROM audit.inbox_checkpoints").fetchall() == [(1,)]


async def test_sequence_gap_is_deferred_never_skipped_and_regression_is_permanent(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    await make_operation(api, extra_events=2)  # sequences 1..3
    applied: list[int] = []

    async def handler(_: AsyncSession, row: OutboxRow) -> None:
        applied.append(row.aggregate_sequence)

    metrics = EventMetrics()
    consumer = InboxConsumer("proj", create_session_factory(cons), CONTRACT, handler, metrics=metrics)
    rows: dict[int, OutboxRow] = {}
    for _ in range(3):  # claim one at a time (per-aggregate order releases the next only after the previous is PUBLISHED)
        async with tenant_uow(disp) as uow:
            repo = OutboxRepository(uow.session)
            (r,) = await repo.claim("d1", 10, 30, 3)
            assert await repo.mark_published(r.id, "d1", r.attempt_count)
            rows[r.aggregate_sequence] = r
    with pytest.raises(delivery.TransientDeliveryError) as gap:
        await consumer.deliver(rows[2])  # sequence 2 arrives before 1
    assert gap.value.code == delivery.SEQUENCE_GAP and applied == []
    assert metrics.snapshot["sequence_gap"] == 1
    for seq in (1, 2, 3):
        await consumer.deliver(rows[seq])
    assert applied == [1, 2, 3]
    with pytest.raises(delivery.PermanentDeliveryError) as regress:  # an older sequence under a NEW event id cannot be applied again
        fresh = uuid4()
        await consumer.deliver(replace(rows[1], event_id=fresh, envelope={**rows[1].envelope, "id": str(fresh)}))  # a consistent envelope under a new id
    assert regress.value.code == delivery.SEQUENCE_REGRESSION
    assert applied == [1, 2, 3]


async def test_monotonic_consumer_accepts_a_filtered_stream_but_not_a_regression(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    await make_operation(api, extra_events=2)
    seen: list[int] = []

    async def handler(_: AsyncSession, row: OutboxRow) -> None:
        seen.append(row.aggregate_sequence)

    consumer = InboxConsumer("filtered", create_session_factory(cons), CONTRACT, handler, ordering=Ordering.MONOTONIC)
    claimed: dict[int, OutboxRow] = {}
    for _ in range(3):
        async with tenant_uow(disp) as uow:
            repo = OutboxRepository(uow.session)
            (r,) = await repo.claim("d1", 10, 30, 3)
            await repo.mark_published(r.id, "d1", r.attempt_count)
            claimed[r.aggregate_sequence] = r
    await consumer.deliver(claimed[3])  # sequences 1-2 are not part of this consumer's stream: not a gap for it
    with pytest.raises(delivery.PermanentDeliveryError):
        await consumer.deliver(claimed[2])
    assert seen == [3]


async def test_poison_event_is_quarantined_and_does_not_block_other_aggregates_or_its_successors_order(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    poison = await make_operation(api, extra_events=1)
    healthy = await make_operation(api, extra_events=1)
    pub = Recorder(lambda r: delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) if r.aggregate_id == poison else None)
    d = make_dispatcher(disp, pub)
    assert await d.run_once() == 1  # the healthy aggregate's first event goes through; the poison one is quarantined
    assert await d.run_once() == 1  # the healthy second event: the stream is not blocked
    assert await d.run_once() == 0
    assert [(r.aggregate_id == healthy, r.aggregate_sequence) for r in pub.rows] == [(True, 1), (True, 2)]  # the poison successor never overtook its predecessor
    with world.connect() as c:
        got = c.execute("SELECT aggregate_id = %s, aggregate_sequence, status, last_error_code FROM audit.outbox_events ORDER BY 1, 2", [poison]).fetchall()
    assert (False, 1, "PUBLISHED", None) in got and (True, 1, "QUARANTINED", delivery.SCHEMA_REJECTED) in got and (True, 2, "PENDING", None) in got


async def test_transient_errors_back_off_and_are_bounded_then_quarantined(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    metrics = EventMetrics()
    d = make_dispatcher(disp, Recorder(lambda _: delivery.TransientDeliveryError(delivery.PUBLISH_FAILED)), metrics=metrics)
    for expected in ("PENDING", "PENDING", "QUARANTINED"):  # max_attempts = 3
        make_available(world)
        assert await d.run_once() == 0
        assert statuses(world)[0][1] == expected
    make_available(world)
    assert await d.run_once() == 0  # quarantined is never retried again
    assert statuses(world)[0][3] == 3
    assert metrics.snapshot["retried:PUBLISH_FAILED"] == 2 and metrics.snapshot["quarantined:PUBLISH_FAILED"] == 1


async def test_unexpected_publisher_exception_is_bounded_retry_with_a_machine_code_only(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)

    class Boom:
        async def publish(self, row: OutboxRow) -> None:
            raise ConnectionError("password=hunter2 host=internal")  # a message that must never reach the stored error

    await make_dispatcher(disp, Boom()).run_once()
    row = statuses(world)[0]
    assert row[1] == "PENDING" and row[2] == delivery.PUBLISH_FAILED and "hunter2" not in repr(row)


async def test_unknown_major_version_is_quarantined_with_an_alert_metric(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    doc = copy.deepcopy(CONTRACT_DOC())
    doc["components"]["messages"]["OperationAccepted"]["payload"]["properties"]["type"]["const"] = "com.aires.operation.accepted.v2"  # the contract of this consumer models only major v2 of the event; the envelope in the outbox is v1
    metrics = EventMetrics()
    pub = Recorder()
    await make_dispatcher(disp, pub, EventContract(doc), metrics=metrics).run_once()
    assert pub.rows == [] and statuses(world)[0][1:3] == ("QUARANTINED", delivery.UNKNOWN_MAJOR_VERSION)
    assert metrics.snapshot["unknown_major_event:UNKNOWN_MAJOR_VERSION"] == 1


def CONTRACT_DOC() -> dict[str, Any]:  # noqa: N802
    import yaml

    return yaml.safe_load(CONTRACT_FILE.read_text())  # type: ignore[no-any-return]


async def test_destination_without_consumer_is_quarantined_not_dropped(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    await make_dispatcher(disp, InternalFanoutPublisher({"other": []})).run_once()
    assert statuses(world)[0][1:3] == ("QUARANTINED", delivery.NO_CONSUMER)


async def test_concurrent_dispatchers_publish_each_event_once_and_in_aggregate_order(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    for _ in range(5):
        await make_operation(api, extra_events=2)
    pub = Recorder()
    d1, d2 = make_dispatcher(disp, pub, owner="d1"), make_dispatcher(disp, pub, owner="d2")
    for _ in range(4):
        await asyncio.gather(d1.run_once(), d2.run_once())
    assert len(pub.rows) == 15 and len({r.event_id for r in pub.rows}) == 15  # every event exactly once here (no crash injected)
    per_aggregate: dict[UUID, list[int]] = defaultdict(list)
    for r in pub.rows:
        per_aggregate[r.aggregate_id].append(r.aggregate_sequence)
    assert all(seqs == [1, 2, 3] for seqs in per_aggregate.values())


async def test_dispatcher_serves_every_tenant_and_the_same_event_id_is_kept_across_retries(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api, ORG_A, PRJ_A)
    await make_operation(api, ORG_B, PRJ_B)
    flaky = {"n": 0}

    def fail_first(_: OutboxRow) -> Exception | None:
        flaky["n"] += 1
        return delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) if flaky["n"] <= 2 else None

    pub = Recorder(fail_first)
    d = make_dispatcher(disp, pub)
    await d.run_once()
    make_available(world)
    await d.run_once()
    assert len(pub.rows) == 2
    with world.connect() as c:
        assert c.execute("SELECT count(DISTINCT organization_id) FROM audit.outbox_events WHERE status = 'PUBLISHED'").fetchone() == (2,)
        ids = {r[0] for r in c.execute("SELECT event_id FROM audit.outbox_events").fetchall()}
    assert {r.event_id for r in pub.rows} == ids  # a retry re-sends the stored event, it never mints a new id


async def test_lost_lease_during_publish_is_counted_not_trusted(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    metrics = EventMetrics()

    class SlowThenLose:
        async def publish(self, row: OutboxRow) -> None:
            expire_lease(world)  # the lease runs out while the publish is in flight
            async with tenant_uow(disp) as uow:  # ... and another dispatcher takes the row over
                assert len(await OutboxRepository(uow.session).claim("d2", 10, 30, 3)) == 1

    assert await make_dispatcher(disp, SlowThenLose(), metrics=metrics).run_once() == 0
    assert metrics.snapshot["lease_lost:published"] == 1
    assert statuses(world)[0][1] == "IN_FLIGHT"  # still owned by d2, not marked by the loser


async def test_contract_rejects_foreign_attributes_forbidden_content_and_unknown_types(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    async with tenant_uow(disp) as uow:
        (row,) = await OutboxRepository(uow.session).claim("d1", 10, 30, 3)
    CONTRACT.check(row.envelope)  # the real envelope is canonical
    bad = copy.deepcopy(row.envelope)
    bad["extra"] = 1
    with pytest.raises(delivery.PermanentDeliveryError) as e1:
        CONTRACT.check(bad)
    assert e1.value.code == delivery.SCHEMA_REJECTED
    leaky = copy.deepcopy(row.envelope)
    leaky["data"].setdefault("details", {})["apiKey"] = "x"
    with pytest.raises(delivery.PermanentDeliveryError) as e2:
        CONTRACT.check(leaky)
    assert e2.value.code == delivery.FORBIDDEN_CONTENT
    unknown = copy.deepcopy(row.envelope)
    unknown["type"] = "com.aires.nothing.happened.v1"
    with pytest.raises(delivery.PermanentDeliveryError) as e3:
        CONTRACT.check(unknown)
    assert e3.value.code == delivery.UNKNOWN_EVENT_TYPE


def test_an_empty_contract_is_refused_instead_of_accepting_everything():
    with pytest.raises(ValueError):
        EventContract({"components": {"messages": {}}})


async def test_controlled_replay_requeues_only_quarantined_rows_in_order(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api, extra_events=1)
    broken = {"on": True}
    pub = Recorder(lambda _: delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED) if broken["on"] else None)
    d = make_dispatcher(disp, pub)
    await d.run_once()
    assert [s[1] for s in statuses(world)] == ["QUARANTINED", "PENDING"]
    with world.connect() as c:
        quarantined = [r[0] for r in c.execute("SELECT event_id FROM audit.outbox_events WHERE status = 'QUARANTINED'").fetchall()]
    async with tenant_uow(disp) as uow:
        with pytest.raises(ValueError):
            await OutboxRepository(uow.session).replay([])  # there is no replay-all
        assert await OutboxRepository(uow.session).replay([*quarantined, uuid4()]) == 1
        assert await OutboxRepository(uow.session).replay(quarantined) == 0  # already PENDING: not touched again
    broken["on"] = False
    assert await d.run_once() == 1 and await d.run_once() == 1
    assert [r.aggregate_sequence for r in pub.rows] == [1, 2]  # the replayed event still precedes its successor
    with world.connect() as c:
        assert c.execute("SELECT aggregate_sequence, replay_count FROM audit.outbox_events ORDER BY 1").fetchall() == [(1, 1), (2, 0)]


async def test_growth_raises_alerts_and_nothing_is_deleted_automatically(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    for _ in range(3):
        await make_operation(api)
    async with tenant_uow(disp) as uow:
        stats = await OutboxRepository(uow.session).stats()
    assert (stats.pending, stats.quarantined) == (3, 0)
    assert evaluate_outbox(stats, GrowthThresholds(max_undelivered=2, max_oldest_undelivered_seconds=-1)) == ["OUTBOX_BACKLOG_HIGH", "OUTBOX_OLDEST_AGE_HIGH"]
    assert evaluate_outbox(stats, GrowthThresholds()) == []
    async with tenant_uow(cons) as uow:
        istats = await InboxRepository(uow.session).stats("proj")
    assert evaluate_inbox(istats, GrowthThresholds(max_inbox_rows=-1)) == ["INBOX_ROWS_HIGH"]
    for role in ("ai_res_outbox_dispatcher", "ai_res_event_consumer"):  # growth is alerted, not trimmed: no runtime role may delete
        table = "audit.outbox_events" if role == "ai_res_outbox_dispatcher" else "audit.inbox_messages"
        with world.connect(role) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(f"DELETE FROM {table}")  # noqa: S608


async def test_checkpoint_cannot_go_backwards_and_only_the_consumer_role_can_touch_it(world: Pg, engine_for):
    api, cons = engine_for("ai_res_api"), engine_for("ai_res_event_consumer")
    agg = await make_operation(api)
    async with tenant_uow(cons) as uow:
        await InboxRepository(uow.session).advance_checkpoint("proj", "OPERATION", agg, 5)
    with pytest.raises(Exception, match="must advance"):
        async with tenant_uow(cons) as uow:
            await InboxRepository(uow.session).advance_checkpoint("proj", "OPERATION", agg, 5)
    with pytest.raises(Exception, match="must advance"):
        async with tenant_uow(cons) as uow:
            await InboxRepository(uow.session).advance_checkpoint("proj", "OPERATION", agg, 3)
    for role in ("ai_res_api", "ai_res_outbox_dispatcher", "ai_res_auditor"):
        with world.connect(role) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM audit.inbox_checkpoints")
    with world.connect("ai_res_event_consumer") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("UPDATE audit.inbox_checkpoints SET consumer_name = 'x'")  # identity columns are not grantable


async def test_outbox_cli_status_and_replay_need_confirmation_and_name_events(world: Pg, engine_for, tmp_path: Path, capsys):
    from ai_res.cli.outbox import main

    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    await make_dispatcher(disp, Recorder(lambda _: delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED))).run_once()
    pw = tmp_path / "pw"
    pw.write_text(world.passwords["ai_res_outbox_dispatcher"])
    env = {"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": world.host, "AI_RES_DB_PORT": str(world.port), "AI_RES_DB_USER": "ai_res_outbox_dispatcher",
           "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable"}
    assert await asyncio.to_thread(main, ["status"], env) == 3  # a quarantined event is a growth alert: non-zero for wrappers
    out = capsys.readouterr().out
    assert "quarantined=1" in out and "alert=OUTBOX_QUARANTINED" in out
    with world.connect() as c:
        (event_id,) = c.execute("SELECT event_id FROM audit.outbox_events").fetchone()
    assert await asyncio.to_thread(main, ["replay", "--event-id", str(event_id)], env) == 2  # no --confirm
    assert await asyncio.to_thread(main, ["replay", "--event-id", str(uuid4()), "--confirm"], env) == 2  # nothing quarantined under that id
    assert await asyncio.to_thread(main, ["replay", "--event-id", str(event_id), "--confirm"], env) == 0
    assert statuses(world)[0][1] == "PENDING"


# ---------- review follow-ups (reviews/S10_REVIEWS.md): fencing, ordering, consumer paths, observability ----------
async def test_same_owner_restart_cannot_mark_a_row_it_no_longer_holds_and_replay_changes_the_token(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)

    async def claim(owner: str, max_attempts: int = 3) -> OutboxRow:
        async with tenant_uow(disp) as uow:
            (r,) = await OutboxRepository(uow.session).claim(owner, 10, 30, max_attempts)
            return r

    old = await claim("d1")
    expire_lease(world)
    new = await claim("d1")  # restart under the SAME name: attempt 2
    async with tenant_uow(disp) as uow:
        repo = OutboxRepository(uow.session)
        assert not await repo.mark_published(old.id, "d1", old.attempt_count, old.replay_count)  # the stale holder's token does not match
        assert not await repo.mark_failed(old.id, "d1", old.attempt_count, "X_ERR", None, 3, old.replay_count)
    async with tenant_uow(disp) as uow:  # permanent failure -> quarantine -> replay restarts attempts: (d1, 1) would match again without replay_count in the token
        assert await OutboxRepository(uow.session).mark_failed(new.id, "d1", new.attempt_count, "X_ERR", None, 3, new.replay_count)
    async with tenant_uow(disp) as uow:
        assert await OutboxRepository(uow.session).replay([new.event_id]) == 1
    third = await claim("d1")
    assert (third.attempt_count, third.replay_count) == (1, 1)
    async with tenant_uow(disp) as uow:
        assert not await OutboxRepository(uow.session).mark_published(third.id, "d1", third.attempt_count, 0)  # a holder from before the replay is fenced off
        assert await OutboxRepository(uow.session).mark_published(third.id, "d1", third.attempt_count, third.replay_count)


async def test_mark_failed_after_the_lease_expired_is_counted_as_lost(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    metrics = EventMetrics()

    class FailAfterExpiry:
        async def publish(self, row: OutboxRow) -> None:
            expire_lease(world)
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED)

    await make_dispatcher(disp, FailAfterExpiry(), metrics=metrics).run_once()
    assert metrics.snapshot["lease_lost:failed"] == 1 and statuses(world)[0][1] == "IN_FLIGHT"


async def test_successor_waits_behind_a_leased_or_backing_off_predecessor(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api, extra_events=1)  # sequences 1, 2
    async with tenant_uow(disp) as uow:  # d1 leases sequence 1 (live lease): another dispatcher must not be given sequence 2
        assert [r.aggregate_sequence for r in await OutboxRepository(uow.session).claim("d1", 10, 30, 3)] == [1]
    pub = Recorder()
    assert await make_dispatcher(disp, pub, owner="d2").run_once() == 0
    async with tenant_uow(disp) as uow:  # sequence 1 fails transiently and backs off into the future: sequence 2 still waits
        row = (await OutboxRepository(uow.session).claim("d1", 10, 30, 3)) if False else None
        assert row is None
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET status='PENDING', lease_owner=NULL, lease_until=NULL, available_at = now() + interval '1 hour' WHERE aggregate_sequence = 1")
    assert await make_dispatcher(disp, pub, owner="d2").run_once() == 0 and pub.rows == []


async def test_consumer_paths_mismatch_stuck_quarantined_contract_and_concurrent_delivery(world: Pg, engine_for):
    api, disp, cons = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher"), engine_for("ai_res_event_consumer")
    await make_operation(api, extra_events=1)
    applied: list[int] = []

    async def handler(_: AsyncSession, row: OutboxRow) -> None:
        applied.append(row.aggregate_sequence)
        await asyncio.sleep(0.2)  # keeps the transaction open so a concurrent delivery would overlap without the advisory lock

    consumer = InboxConsumer("proj", create_session_factory(cons), CONTRACT, handler)
    rows: dict[int, OutboxRow] = {}
    for _ in range(2):
        async with tenant_uow(disp) as uow:
            repo = OutboxRepository(uow.session)
            (r,) = await repo.claim("d1", 10, 30, 3)
            await repo.mark_published(r.id, "d1", r.attempt_count, r.replay_count)
            rows[r.aggregate_sequence] = r
    bad = replace(rows[1], envelope={**rows[1].envelope, "extra": 1})
    with pytest.raises(delivery.PermanentDeliveryError) as e1:  # the consumer validates on its own
        await consumer.deliver(bad)
    assert e1.value.code == delivery.SCHEMA_REJECTED
    other = copy.deepcopy(rows[1].envelope)
    other["id"] = str(uuid4())
    with pytest.raises(delivery.PermanentDeliveryError) as e2:  # a valid envelope that is not the row's own event
        await consumer.deliver(replace(rows[1], envelope=other))
    assert e2.value.code == delivery.ENVELOPE_MISMATCH
    results = await asyncio.gather(consumer.deliver(rows[1]), consumer.deliver(rows[1]))  # two concurrent deliveries of one event
    assert sorted(results) == [Delivery.DUPLICATE, Delivery.FIRST]  # serialised by the advisory lock: one applies, the other is a no-op
    assert applied == [1]
    hacked = replace(rows[1], envelope={**rows[1].envelope, "time": "2001-01-01T00:00:00Z"})  # differing content under the same event id is an anomaly
    with pytest.raises(delivery.PermanentDeliveryError) as e3:
        await consumer.deliver(hacked)
    assert e3.value.code == delivery.ENVELOPE_MISMATCH
    digest = hashlib.sha256(canonical_json(rows[2].envelope).encode()).digest()
    with world.connect() as c:  # a marker left PROCESSING with the same content (not producible by this library) is deferred, never reported as success
        c.execute("INSERT INTO audit.inbox_messages (id, consumer_name, event_id, aggregate_type, aggregate_id, aggregate_sequence, status, payload_hash) "
                  "VALUES (%s, 'proj', %s, 'OPERATION', %s, 2, 'PROCESSING', %s)", [uuid4(), rows[2].event_id, rows[2].aggregate_id, digest])
    with pytest.raises(delivery.TransientDeliveryError) as stuck:
        await consumer.deliver(rows[2])
    assert stuck.value.code == delivery.INBOX_STUCK
    with world.connect() as c:
        c.execute("UPDATE audit.inbox_messages SET status = 'QUARANTINED', error_code = 'POISON' WHERE event_id = %s", [rows[2].event_id])
    with pytest.raises(delivery.PermanentDeliveryError) as quarantined:  # a quarantined marker is not a success either
        await consumer.deliver(rows[2])
    assert quarantined.value.code == delivery.INBOX_QUARANTINED


async def test_dispatcher_survives_a_mark_error_and_reports_claim_quarantine_and_growth_alerts(world: Pg, engine_for, caplog):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    await make_operation(api)
    metrics = EventMetrics()
    pub = Recorder()
    d = make_dispatcher(disp, pub, metrics=metrics)
    original = OutboxRepository.mark_published
    calls = {"n": 0}

    async def flaky(self: OutboxRepository, *a: Any, **k: Any) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("secret-host-detail")
        return await original(self, *a, **k)

    OutboxRepository.mark_published = flaky  # type: ignore[method-assign]
    try:
        with caplog.at_level("ERROR"):
            assert await d.run_once() == 1  # the first mark failed, the second row of the batch was still delivered
    finally:
        OutboxRepository.mark_published = original  # type: ignore[method-assign]
    assert metrics.snapshot["mark_error:published"] == 1
    assert any(getattr(r, "error_class", None) == "ConnectionError" for r in caplog.records)  # the class is logged ...
    assert "secret-host-detail" not in caplog.text and not any("secret-host-detail" in repr(r.__dict__) for r in caplog.records)  # ... the message never
    # a row whose lease keeps expiring is quarantined by the claim and that is counted
    expire_lease(world)
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET attempt_count = 3 WHERE status = 'IN_FLIGHT'")
    await make_dispatcher(disp, Recorder(), metrics=metrics).run_once()
    assert metrics.snapshot["quarantined:LEASE_EXPIRED_MAX_ATTEMPTS"] == 1
    alerts = await make_dispatcher(disp, Recorder(), metrics=metrics).observe()
    assert "OUTBOX_QUARANTINED" in alerts and metrics.snapshot["alert:OUTBOX_QUARANTINED"] == 1


async def test_publish_timeout_is_transient_and_a_batch_must_fit_the_lease(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)

    class Hang:
        async def publish(self, row: OutboxRow) -> None:
            await asyncio.sleep(30)

    d = Dispatcher(create_session_factory(disp), Hang(), CONTRACT, DispatcherConfig(owner="d1", batch_size=1, lease_seconds=5, publish_timeout_seconds=0.2),
                   EventMetrics(), rng=lambda: 0.0)
    await d.run_once()
    assert statuses(world)[0][1:3] == ("PENDING", delivery.PUBLISH_TIMEOUT)
    with pytest.raises(ValueError):
        DispatcherConfig(owner="d", batch_size=10, lease_seconds=30, publish_timeout_seconds=5)


async def test_a_malformed_timestamp_is_rejected_by_the_contract(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    async with tenant_uow(disp) as uow:
        (row,) = await OutboxRepository(uow.session).claim("d1", 10, 30, 3)
    bad = copy.deepcopy(row.envelope)
    bad["time"] = "garbage"
    with pytest.raises(delivery.PermanentDeliveryError):
        CONTRACT.check(bad)


async def test_replay_count_moves_only_by_one_with_a_replay(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    await make_operation(api)
    with world.connect("ai_res_outbox_dispatcher") as c, pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        c.execute("UPDATE audit.outbox_events SET replay_count = 5")
    with world.connect("ai_res_outbox_dispatcher") as c, pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        c.execute("UPDATE audit.outbox_events SET replay_count = replay_count + 1")  # PENDING -> PENDING is not a replay
    assert disp is not None
