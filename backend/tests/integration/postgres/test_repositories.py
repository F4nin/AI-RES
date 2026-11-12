# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S05 slice E: repositories + Unit of Work under the real runtime roles (api, outbox dispatcher, event consumer).

Covers the stage-level negative tests: projection+event+outbox atomicity, stale CAS, forged ids, parallel sequence allocation through the repository,
rework after a terminal Operation (new Operation + Task + WorkerRun), Gate refusal, dispatcher ordering/lease/quarantine, inbox dedupe, idempotency races.
"""
import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events.aggregate_events import EventSpec, append_event
from ai_res.modules.events.envelope import EventRef
from ai_res.modules.events.inbox_repository import Delivery, InboxRepository
from ai_res.modules.events.outbox_repository import OutboxRepository
from ai_res.modules.idempotency.repository import IdempotencyOutcome, IdempotencyRepository
from ai_res.modules.operations.repository import OPERATION_KIND, NewOperation, OperationRepository, OperationRow
from ai_res.modules.readiness.repository import NewCheck, NewEvaluation, ReadinessRepository
from ai_res.modules.tasks.repository import NewEpic, NewTask, TaskRepository
from ai_res.modules.worker_runs.repository import NewWorkerRun, WorkerRunRepository
from ai_res.platform.clock import utc_now
from ai_res.platform.concurrency import AggregateVersionConflict
from ai_res.platform.config import load_settings
from ai_res.platform.problems import ErrorCode, ProblemError

from .conftest import Pg

pytestmark = pytest.mark.postgres
ORG_A, ORG_B, PRJ_A, PRJ_B = uuid4(), uuid4(), uuid4(), uuid4()
H = b"\x07" * 32


def spec(etype: str = "operation.accepted", dests: tuple[str, ...] = ("internal",), **kw: Any) -> EventSpec:
    kw.setdefault("schema_version", 1)
    kw.setdefault("actor_type", "SYSTEM")
    return EventSpec(event_type=etype, correlation_id=uuid4(), destinations=dests, **kw)


def new_operation(org: UUID = ORG_A, prj: UUID = PRJ_A, **kw: Any) -> NewOperation:
    return NewOperation(id=uuid4(), organization_id=org, project_id=prj, operation_type="PLAN_EXECUTION", initiator_type="USER", idempotency_scope="scope",
                        request_fingerprint=H, completion_policy_version="wip-1", completion_policy_snapshot={"mode": "all"}, correlation_id=uuid4(), **kw)


@pytest.fixture
def world(migrated: Pg) -> Pg:
    with migrated.connect() as c:
        for org in (ORG_A, ORG_B):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        for prj, org in ((PRJ_A, ORG_A), (PRJ_B, ORG_B)):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
    return migrated


@pytest.fixture
async def engine_for(world: Pg, tmp_path: Path) -> AsyncIterator[Callable[[str], AsyncEngine]]:
    created: list[AsyncEngine] = []

    def make(role: str) -> AsyncEngine:
        pw = tmp_path / f"{role}_pw"
        pw.write_text(world.passwords[role])
        settings = load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": world.host, "AI_RES_DB_PORT": str(world.port), "AI_RES_DB_USER": role,
                                  "AI_RES_DB_PASSWORD_FILE": str(pw), "AI_RES_DB_SSLMODE": "disable", "AI_RES_DB_APPLICATION_NAME": f"test-{role}", "AI_RES_DB_POOL_SIZE": "12"})
        eng = create_runtime_engine(settings)
        created.append(eng)
        return eng

    yield make
    for eng in created:
        await eng.dispose()


def tenant_uow(engine: AsyncEngine) -> UnitOfWork:
    return UnitOfWork(create_session_factory(engine))


NEXT_LEGAL = {"ACCEPTED": "QUEUED", "QUEUED": "RUNNING", "RUNNING": "RETRYING", "RETRYING": "RUNNING"}


async def count(world: Pg, sql: str, *args: Any) -> int:
    with world.connect() as c:
        return int(c.execute(sql, list(args)).fetchone()[0])  # type: ignore[index]


async def test_operation_create_and_transition_write_projection_events_and_outbox_together(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        row, first = await repo.create(new_operation(), spec(dests=("internal", "audit-sink")))
        assert (row.status, row.row_version, row.last_event_sequence, first.aggregate_sequence) == ("ACCEPTED", 2, 1, 1)
        second = await repo.transition(row, "FAILED", spec("operation.failed", from_status="ACCEPTED", to_status="FAILED"))
        assert (second.aggregate_sequence, second.row_version) == (2, 3)
    with world.connect() as c:
        assert c.execute("SELECT status, last_event_sequence, row_version, completed_at IS NOT NULL FROM operations.operations WHERE id=%s", [row.id]).fetchone() == ("FAILED", 2, 3, True)
        assert [r[0] for r in c.execute("SELECT aggregate_sequence FROM operations.operation_events WHERE operation_id=%s ORDER BY 1", [row.id])] == [1, 2]
        out = c.execute("SELECT destination, aggregate_sequence, envelope FROM audit.outbox_events WHERE aggregate_id=%s ORDER BY aggregate_sequence, destination", [row.id]).fetchall()
    assert [(d, s) for d, s, _ in out] == [("audit-sink", 1), ("internal", 1), ("internal", 2)]
    env = out[-1][2]
    # AsyncAPI v1.6 canonical message: exactly the nine CloudEvents attributes, everything else inside `data` (G-56 option A)
    assert set(env) == {"specversion", "id", "source", "type", "subject", "time", "datacontenttype", "dataschema", "data"}
    assert env["specversion"] == "1.0" and env["type"] == "com.aires.operation.failed.v1" and env["id"] == str(second.event_id)
    assert env["source"] == "urn:aires:operations" and env["subject"] == f"operations/{row.id}" and env["dataschema"].endswith("com.aires.operation.failed.v1")
    data = env["data"]
    assert (data["aggregateType"], data["aggregateSequence"], data["aggregateVersion"], data["operationId"], data["aggregateId"]) == ("OPERATION", 2, 3, str(row.id), str(row.id))
    assert (data["organizationId"], data["projectId"], data["eventId"], data["transition"]) == (str(ORG_A), str(PRJ_A), str(second.event_id), {"from": "ACCEPTED", "to": "FAILED"})
    assert "eventType" not in data and data["actor"] == {"type": "SYSTEM"}


async def test_failure_after_the_writes_rolls_back_projection_event_and_outbox(world: Pg, engine_for):
    op = new_operation()
    with pytest.raises(RuntimeError, match="boom"):
        async with tenant_uow(engine_for("ai_res_api")) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await OperationRepository(uow.session).create(op, spec())
            raise RuntimeError("boom")  # e.g. the Temporal start request failing is NOT inside the UoW, but any later step may fail
    assert [await count(world, f"SELECT count(*) FROM {t} WHERE {c} = %s", op.id) for t, c in
            (("operations.operations", "id"), ("operations.operation_events", "operation_id"), ("audit.outbox_events", "aggregate_id"))] == [0, 0, 0]


async def test_stale_version_missing_and_foreign_ids_never_write_and_do_not_leak(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_B, PRJ_B)
        foreign_row, _ = await OperationRepository(uow.session).create(new_operation(ORG_B, PRJ_B), spec())
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        mine, _ = await repo.create(new_operation(), spec())
        await repo.transition(mine, "QUEUED", spec("operation.started"))
        with pytest.raises(AggregateVersionConflict):  # `mine` is stale now
            await repo.transition(mine, "QUEUED", spec("operation.queued"))
    forged = OperationRow(foreign_row.id, ORG_A, PRJ_A, "PLAN_EXECUTION", "ACCEPTED", foreign_row.row_version, 0, None)
    missing = OperationRow(uuid4(), ORG_A, PRJ_A, "PLAN_EXECUTION", "ACCEPTED", 1, 0, None)
    problems = []
    for row in (forged, missing):  # another tenant's operation looks exactly like a missing one
        with pytest.raises(ProblemError) as exc:
            async with tenant_uow(api) as uow:
                await uow.with_tenant(ORG_A, PRJ_A)
                await OperationRepository(uow.session).transition(row, "QUEUED", spec("operation.started"))
        problems.append((exc.value.code, str(exc.value)))
    assert problems[0] == problems[1] and problems[0][0] == ErrorCode.RESOURCE_NOT_FOUND
    assert await count(world, "SELECT last_event_sequence FROM operations.operations WHERE id=%s", foreign_row.id) == 1  # untouched
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        assert await OperationRepository(uow.session).get(foreign_row.id) is None


async def test_creating_in_a_foreign_scope_is_refused_by_rls(world: Pg, engine_for):
    with pytest.raises(DBAPIError):
        async with tenant_uow(engine_for("ai_res_api")) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await OperationRepository(uow.session).create(new_operation(ORG_B, PRJ_B), spec())


async def test_event_payload_destinations_and_columns_are_validated_before_any_sql(world: Pg, engine_for):
    async with tenant_uow(engine_for("ai_res_api")) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        row, _ = await repo.create(new_operation(), spec())
        for bad in (spec(data={"nested": {"api_token": "x"}}), spec(data={"items": [{"password": "x"}]}), spec(dests=()), spec(dests=("a", "a")), spec(dests=("",)),
                    spec("operation.nonsense"), spec("worker_run.started"), spec(schema_version=2), spec(actor_type="WORKER_RUN"), spec(actor_type="")):
            with pytest.raises(ValueError):
                await repo.transition(row, "QUEUED", bad)
        with pytest.raises(ValueError, match="not updatable"):
            await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id, expected_version=row.row_version,
                               spec=spec(), changes={"organization_id": ORG_B})
        with pytest.raises(ValueError, match="not updatable"):  # an injection-shaped column name is data, not SQL
            await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id, expected_version=row.row_version,
                               spec=spec(), changes={"status = 'X', row_version": 1})
        assert (await repo.get(row.id)).row_version == row.row_version  # type: ignore[union-attr]


async def test_persist_012_parallel_transitions_through_the_repository_have_no_gap_or_duplicate(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        row, _ = await OperationRepository(uow.session).create(new_operation(), spec())

    async def worker() -> int:
        done = 0
        while done < 4:
            try:
                async with tenant_uow(api) as uow:
                    await uow.with_tenant(ORG_A, PRJ_A)
                    repo = OperationRepository(uow.session)
                    cur = await repo.get(row.id)
                    assert cur is not None
                    await repo.transition(cur, NEXT_LEGAL[cur.status], spec("operation.progress_updated"))  # ACCEPTED->QUEUED->RUNNING->RETRYING->RUNNING...
                done += 1
            except AggregateVersionConflict:
                await asyncio.sleep(0)  # lost the CAS race: reload and retry the whole use case
        return done

    assert sum(await asyncio.gather(*(worker() for _ in range(6)))) == 24
    with world.connect() as c:
        assert [r[0] for r in c.execute("SELECT aggregate_sequence FROM operations.operation_events WHERE operation_id=%s ORDER BY 1", [row.id])] == list(range(1, 26))
        assert c.execute("SELECT last_event_sequence, row_version FROM operations.operations WHERE id=%s", [row.id]).fetchone() == (25, 26)


# an evaluation is computed for the run's own versions (the start guard rejects a stale one), so runs and evaluations share these
WDV, CPV = uuid4(), uuid4()


def evaluation(run_id: UUID, outcome: str = "READY", number: int = 1) -> NewEvaluation:
    return NewEvaluation(worker_run_id=run_id, evaluation_number=number, evaluation_status="COMPLETED", gate_outcome=outcome, snapshot_hash=H, task_version=1,
                         worker_definition_version_id=WDV, context_package_version_id=CPV, ruleset_version="r1", policy_engine_version="p1",
                         grant_snapshot_ref={}, tool_allowlist_snapshot=[], output_contract_version="out-1", budget_profile_version="b1", dependency_snapshot={},
                         evaluator_version="e1", evaluated_at=utc_now())


async def test_gate_start_result_and_rework_after_a_terminal_operation(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        ops, tasks, runs, ready = OperationRepository(uow.session), TaskRepository(uow.session), WorkerRunRepository(uow.session), ReadinessRepository(uow.session)
        op1, _ = await ops.create(new_operation(), spec())
        epic = await tasks.create_epic(NewEpic(ORG_A, PRJ_A, "epic", "ACTIVE"))
        task1 = await tasks.create_task(NewTask(ORG_A, PRJ_A, op1.id, epic, "ANALYSIS", "analyse", "PROPOSED", "MANAGER", acceptance_criteria=("a", "b")))
        run1, _ = await runs.create(NewWorkerRun(ORG_A, PRJ_A, op1.id, task1.id, WDV, CPV, "in-1", "out-1"), spec("worker_run.created"))
        blocked = await ready.record(evaluation(run1.id, "BLOCKED", 1), [NewCheck("POLICY_OK", "FAIL", "HIGH", reason_code="POLICY_DENIED")])
        good = await ready.record(evaluation(run1.id, "READY", 2), [NewCheck("TASK_ACTIVE", "PASS", "INFO"), NewCheck("POLICY_OK", "PASS", "INFO")])
        run1 = await runs.get(run1.id)  # type: ignore[assignment]
    with pytest.raises(IntegrityError):  # the Gate outcome is BLOCKED: the run cannot start with it
        async with tenant_uow(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await WorkerRunRepository(uow.session).start(run1, blocked, spec("worker_run.started"))
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        runs = WorkerRunRepository(uow.session)
        await runs.start(run1, good, spec("worker_run.started"))
        run1 = await runs.get(run1.id)  # type: ignore[assignment]
        assert run1.started_with_readiness_evaluation_id == good and run1.status == "STARTING"
        await runs.transition(run1, "RUNNING", spec("worker_run.resumed"))
        run1 = await runs.get(run1.id)  # type: ignore[assignment]
        result_id = await runs.store_result(run1, "wip-1", {"summary": "findings"})
        await runs.transition(run1, "COMPLETED", spec("worker_run.completed"))
        for step in ("QUEUED", "RUNNING", "SUCCEEDED"):  # the legal path to a terminal Operation (State Machine v1.2)
            op1 = await OperationRepository(uow.session).get(op1.id)  # type: ignore[assignment]
            await OperationRepository(uow.session).transition(op1, step, spec(f"operation.{ {'QUEUED': 'queued', 'RUNNING': 'started', 'SUCCEEDED': 'succeeded'}[step] }"))
    with world.connect() as c:
        stored = c.execute("SELECT payload_hash, contract_version FROM agents.worker_results WHERE id=%s", [result_id]).fetchone()
    assert stored[0] == hashlib.sha256(b'{"summary":"findings"}').digest()  # type: ignore[index]

    for attempt in ("task", "run"):  # nothing new can be attached to a terminal Operation
        with pytest.raises(IntegrityError):
            async with tenant_uow(api) as uow:
                await uow.with_tenant(ORG_A, PRJ_A)
                if attempt == "task":
                    await TaskRepository(uow.session).create_task(NewTask(ORG_A, PRJ_A, op1.id, epic, "ANALYSIS", "late", "PROPOSED", "MANAGER"))
                else:
                    await WorkerRunRepository(uow.session).create(NewWorkerRun(ORG_A, PRJ_A, op1.id, task1.id, WDV, CPV, "in-1", "out-1"), spec("worker_run.created"))

    async with tenant_uow(api) as uow:  # ADR-034: rework = new root Operation + new Task (derived_from_task_id) + new WorkerRun (derived_from_worker_run_id)
        await uow.with_tenant(ORG_A, PRJ_A)
        op2, _ = await OperationRepository(uow.session).create(new_operation(), spec())
        task2 = await TaskRepository(uow.session).create_task(NewTask(ORG_A, PRJ_A, op2.id, epic, "ANALYSIS", "rework", "PROPOSED", "MANAGER", derived_from_task_id=task1.id))
        run2, _ = await WorkerRunRepository(uow.session).create(
            NewWorkerRun(ORG_A, PRJ_A, op2.id, task2.id, WDV, CPV, "in-1", "out-1", derived_from_worker_run_id=run1.id, derivation_reason="REWORK", attempt_number=2),
            spec("worker_run.created"))
        with pytest.raises(AggregateVersionConflict):  # a stale task row cannot be overwritten
            await TaskRepository(uow.session).update_task(task2.id, task2.row_version + 7, title="x")
        assert await TaskRepository(uow.session).update_task(task2.id, task2.row_version, title="rework v2") == task2.row_version + 1
    with world.connect() as c:
        assert c.execute("SELECT count(*) FROM agents.worker_results WHERE worker_run_id=%s", [run2.id]).fetchone() == (0,)  # the old result was neither moved nor reused
        assert c.execute("SELECT status FROM operations.operations WHERE id=%s", [op1.id]).fetchone() == ("SUCCEEDED",)


async def test_dispatcher_claims_in_aggregate_order_leases_expire_and_quarantine_blocks_successors(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        row, _ = await repo.create(new_operation(), spec())
        await repo.transition(row, "QUEUED", spec("operation.started"))
        other, _ = await repo.create(new_operation(), spec())

    async def claim(owner: str, limit: int = 10, lease: float = 30, max_attempts: int = 5) -> list[Any]:
        async with tenant_uow(disp) as uow:  # no tenant context: the dispatcher serves every tenant
            return await OutboxRepository(uow.session).claim(owner, limit, lease, max_attempts)

    first = await claim("d1")
    assert sorted((r.aggregate_sequence, r.aggregate_id == row.id) for r in first) == [(1, False), (1, True)]  # sequence 2 waits behind sequence 1
    assert await claim("d2") == []  # still leased by d1
    async with tenant_uow(disp) as uow:
        o = OutboxRepository(uow.session)
        seq1 = next(r for r in first if r.aggregate_id == row.id)
        assert not await o.mark_published(seq1.id, "someone-else", seq1.attempt_count)  # only the lease owner may publish
        assert not await o.mark_published(seq1.id, "d1", seq1.attempt_count + 1)  # the right owner with a token of another lease does not count
        assert await o.mark_published(seq1.id, "d1", seq1.attempt_count)
    nxt = await claim("d1")
    assert [(r.aggregate_id == row.id, r.aggregate_sequence) for r in nxt] == [(True, 2)]
    async with tenant_uow(disp) as uow:  # permanent failure of seq 2 -> quarantine; nothing after it may overtake (here: nothing else), and it is not re-claimed
        assert await OutboxRepository(uow.session).mark_failed(nxt[0].id, "d1", nxt[0].attempt_count, "SCHEMA_REJECTED", None, 5)
    assert await claim("d1") == []  # quarantined seq 2 is never re-claimed; `other` is still leased by d1
    other_row = next(r for r in first if r.aggregate_id == other.id)
    async with tenant_uow(disp) as uow:  # transient failure: back to PENDING in the future -> not claimable yet
        assert await OutboxRepository(uow.session).mark_failed(other_row.id, "d1", other_row.attempt_count, "TIMEOUT", utc_now() + timedelta(hours=1), 5)
    assert await claim("d1") == []
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET available_at = now() - interval '1 second' WHERE id = %s", [other_row.id])
    again = await claim("d3")
    assert [(r.id, r.attempt_count) for r in again] == [(other_row.id, 2)]
    with world.connect() as c:  # d3's lease expires (set explicitly: no wall-clock sleeping): another dispatcher reclaims it and d3 learns it lost ownership
        c.execute("UPDATE audit.outbox_events SET lease_until = now() - interval '1 second' WHERE id = %s", [other_row.id])
    reclaimed = await claim("d4")
    assert [r.id for r in reclaimed] == [other_row.id]
    async with tenant_uow(disp) as uow:
        assert not await OutboxRepository(uow.session).mark_published(other_row.id, "d3", again[0].attempt_count)
        assert await OutboxRepository(uow.session).mark_published(other_row.id, "d4", reclaimed[0].attempt_count)


async def test_concurrent_dispatchers_never_claim_the_same_row(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    for _ in range(6):
        async with tenant_uow(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            await OperationRepository(uow.session).create(new_operation(), spec())

    async def claim(owner: str) -> set[UUID]:
        async with tenant_uow(disp) as uow:
            return {r.id for r in await OutboxRepository(uow.session).claim(owner, 3, 30, 5)}

    a, b = await asyncio.gather(claim("d1"), claim("d2"))
    assert not (a & b)  # never the same row twice
    rest = await claim("d3")  # a recheck under SKIP LOCKED may legitimately return fewer rows than the limit
    rest |= await claim("d3")
    assert len(a | b | rest) == 6  # every row was claimed exactly once across the three claims


async def test_inbox_dedupes_reports_anomalies_and_a_crash_before_commit_leaves_no_trace(world: Pg, engine_for):
    consumer, ev, agg = engine_for("ai_res_event_consumer"), uuid4(), uuid4()
    with pytest.raises(RuntimeError):
        async with tenant_uow(consumer) as uow:
            assert await InboxRepository(uow.session).receive("c1", ev, "OPERATION", agg, 1, H) is Delivery.FIRST
            raise RuntimeError("crash before commit")  # PERSIST-016 mechanics: the delivery was never recorded
    async with tenant_uow(consumer) as uow:
        inbox = InboxRepository(uow.session)
        assert await inbox.receive("c1", ev, "OPERATION", agg, 1, H) is Delivery.FIRST
        assert await inbox.receive("c1", ev, "OPERATION", agg, 1, H) is Delivery.STUCK  # received, still PROCESSING
        assert await inbox.receive("c2", ev, "OPERATION", agg, 1, H) is Delivery.FIRST  # per-consumer
    async with tenant_uow(consumer) as uow:
        inbox = InboxRepository(uow.session)
        assert await inbox.mark_processed("c1", ev) is True
        assert await inbox.receive("c1", ev, "OPERATION", agg, 1, H) is Delivery.DUPLICATE  # duplicate after processing = successful no-op
        assert await inbox.mark_processed("c1", ev) is False  # second completion is visible, not silent
        assert await inbox.quarantine("c1", ev, "TOO_LATE") is False  # PROCESSED is final
        assert await inbox.mark_processed("c1", uuid4()) is False  # unknown event
        assert await inbox.quarantine("c2", ev, "BAD_PAYLOAD") is True
    with pytest.raises(ProblemError) as differs:  # same event id, different content: an anomaly, not a duplicate
        async with tenant_uow(consumer) as uow:
            await InboxRepository(uow.session).receive("c1", ev, "OPERATION", agg, 1, b"\x08" * 32)
    with pytest.raises(ProblemError) as moved:
        async with tenant_uow(consumer) as uow:
            await InboxRepository(uow.session).receive("c1", ev, "OPERATION", agg, 2, H)
    assert differs.value.code == moved.value.code == ErrorCode.VALIDATION_ERROR
    with world.connect() as c:
        assert sorted(c.execute("SELECT consumer_name, status FROM audit.inbox_messages").fetchall()) == [("c1", "PROCESSED"), ("c2", "QUARANTINED")]
    with pytest.raises(DBAPIError):  # error codes are short codes, never free text such as str(exception)
        async with tenant_uow(consumer) as uow:
            free_text_event = uuid4()
            await InboxRepository(uow.session).receive("c3", free_text_event, "OPERATION", agg, 1, H)
            await InboxRepository(uow.session).quarantine("c3", free_text_event, "postgresql://u:p@h/db failed")


async def test_poison_outbox_row_is_quarantined_after_max_attempts_and_blocks_its_successors(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        row, _ = await repo.create(new_operation(), spec())
        await repo.transition(row, "QUEUED", spec("operation.started"))  # sequence 2 waits behind sequence 1

    async def claim() -> list[Any]:
        async with tenant_uow(disp) as uow:
            return await OutboxRepository(uow.session).claim("d1", 10, 30, 2)

    for attempt in (1, 2):
        got = await claim()
        assert [(r.aggregate_sequence, r.attempt_count) for r in got] == [(1, attempt)]
        with world.connect() as c:
            c.execute("UPDATE audit.outbox_events SET lease_until = now() - interval '1 second' WHERE aggregate_id = %s AND aggregate_sequence = 1", [row.id])  # dispatcher crashed
    assert await claim() == []  # third claim: attempt cap reached -> quarantined, and sequence 2 stays blocked (no overtaking, no silent skip)
    with world.connect() as c:
        assert c.execute("SELECT aggregate_sequence, status, last_error_code FROM audit.outbox_events WHERE aggregate_id = %s ORDER BY 1", [row.id]).fetchall() == [
            (1, "QUARANTINED", "LEASE_EXPIRED_MAX_ATTEMPTS"), (2, "PENDING", None)]


async def test_transition_spec_must_describe_the_real_change_and_results_reject_secrets(world: Pg, engine_for):
    async with tenant_uow(engine_for("ai_res_api")) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        repo = OperationRepository(uow.session)
        row, _ = await repo.create(new_operation(), spec())
        for bad_spec, changes in ((spec(from_status="RUNNING"), {}), (spec(to_status="FAILED"), {}), (spec(), {"status": "SUCCEEDED"})):
            with pytest.raises(ValueError):
                await repo.transition(row, "QUEUED", bad_spec, **changes)
        with pytest.raises(ValueError, match="sensitive"):
            await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id, expected_version=row.row_version,
                               spec=spec(data={"detail": {"password": "x"}}))
        for bad in (spec(reason_code="free text, with a stack trace"), spec(refs=(EventRef("bad type!", uuid4()),)), spec(reason_code="lower_case")):
            with pytest.raises(ValueError):  # reason codes are machine codes, reference types are names: neither is a channel for free text
                await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id,
                                   expected_version=row.row_version, spec=bad)
        assert (await repo.get(row.id)).row_version == row.row_version  # type: ignore[union-attr]
        with pytest.raises(ValueError, match="naive"):
            await repo.transition(row, "QUEUED", spec(occurred_at=datetime(2026, 1, 1)))  # noqa: DTZ001 - the point of the test


async def test_persist_013_014_idempotency_replay_reuse_and_race(world: Pg, engine_for):
    api, key, fp = engine_for("ai_res_api"), b"\x0a" * 32, b"\x0b" * 32
    scope, exp = uuid4(), utc_now() + timedelta(days=1)

    async def begin(fingerprint: bytes = fp) -> Any:
        async with tenant_uow(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            return await IdempotencyRepository(uow.session).begin(ORG_A, PRJ_A, "PROJECT", scope, key, "k1", fingerprint, exp)

    results = await asyncio.gather(*(begin() for _ in range(10)))  # 10 concurrent first requests with the same key
    assert [r.outcome for r in results].count(IdempotencyOutcome.NEW) == 1
    assert {r.outcome for r in results} <= {IdempotencyOutcome.NEW, IdempotencyOutcome.IN_PROGRESS}
    new = next(r for r in results if r.outcome == IdempotencyOutcome.NEW)
    assert await count(world, "SELECT count(*) FROM platform.idempotency_records WHERE scope_id=%s", scope) == 1
    with pytest.raises(ProblemError) as exc:  # PERSIST-014: same key, different request
        await begin(b"\x0c" * 32)
    assert exc.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED
    resource = uuid4()
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await IdempotencyRepository(uow.session).complete(new.id, "COMPLETED", "OPERATION", resource, 202, {"operationId": str(resource)})
        with pytest.raises(ProblemError) as again:  # a finished record cannot be completed again
            await IdempotencyRepository(uow.session).complete(new.id, "COMPLETED", "OPERATION", resource, 202, None)
        assert again.value.code == ErrorCode.AGGREGATE_VERSION_CONFLICT
    replay = await begin()
    assert (replay.outcome, replay.resource_id, replay.response_status, replay.response_body_ref) == (IdempotencyOutcome.REPLAY, resource, 202, {"operationId": str(resource)})


async def test_outbox_fencing_by_attempt_expired_lease_and_bounded_retry(world: Pg, engine_for):
    api, disp = engine_for("ai_res_api"), engine_for("ai_res_outbox_dispatcher")

    async def claim(owner: str, max_attempts: int = 4) -> Any:
        async with tenant_uow(disp) as uow:
            return await OutboxRepository(uow.session).claim(owner, 10, 30, max_attempts)

    async def status(row_id: UUID) -> str:
        with world.connect() as c:
            return str(c.execute("SELECT status FROM audit.outbox_events WHERE id=%s", [row_id]).fetchone()[0])  # type: ignore[index]

    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await OperationRepository(uow.session).create(new_operation(), spec())
    (first,) = await claim("d1")
    with world.connect() as c:  # the lease expires, the dispatcher restarts under the SAME name and reclaims: the old handle must not work any more
        c.execute("UPDATE audit.outbox_events SET lease_until = now() - interval '1 second' WHERE id = %s", [first.id])
    async with tenant_uow(disp) as uow:
        assert not await OutboxRepository(uow.session).mark_published(first.id, "d1", first.attempt_count)  # expired and not yet reclaimed
    (second,) = await claim("d1")
    assert second.attempt_count == first.attempt_count + 1
    async with tenant_uow(disp) as uow:  # mark_failed is fenced like mark_published: another owner, or the right owner after the lease ran out, changes nothing
        assert not await OutboxRepository(uow.session).mark_failed(second.id, "d2", second.attempt_count, "TIMEOUT", utc_now(), 4)
    with world.connect() as c:
        c.execute("UPDATE audit.outbox_events SET lease_until = now() - interval '1 second' WHERE id = %s", [second.id])
    async with tenant_uow(disp) as uow:
        assert not await OutboxRepository(uow.session).mark_failed(second.id, "d1", second.attempt_count, "TIMEOUT", utc_now(), 4)
    assert await status(first.id) == "IN_FLIGHT"
    (second,) = await claim("d1")  # the expired lease is reclaimed: a new attempt, a fresh lease
    assert second.attempt_count == first.attempt_count + 2
    async with tenant_uow(disp) as uow:
        assert not await OutboxRepository(uow.session).mark_published(first.id, "d1", first.attempt_count)  # same owner name, stale attempt
        assert not await OutboxRepository(uow.session).mark_failed(first.id, "d1", first.attempt_count, "TIMEOUT", utc_now(), 4)
    assert await status(first.id) == "IN_FLIGHT"
    async with tenant_uow(disp) as uow:  # a transient failure within the budget goes back to PENDING (retry_at already due)
        assert await OutboxRepository(uow.session).mark_failed(second.id, "d1", second.attempt_count, "TIMEOUT", utc_now() - timedelta(seconds=1), 4)
    assert await status(first.id) == "PENDING"
    (third,) = await claim("d1")
    async with tenant_uow(disp) as uow:  # the budget (4 attempts) is spent: a transient error is quarantined instead of retrying forever
        assert await OutboxRepository(uow.session).mark_failed(third.id, "d1", third.attempt_count, "TIMEOUT", utc_now() - timedelta(seconds=1), 4)
    assert third.attempt_count == 4 and await status(first.id) == "QUARANTINED"
    assert await claim("d1") == []
    async with tenant_uow(disp) as uow:
        with pytest.raises(ValueError, match="machine code"):  # the stored error code is never an exception message (server DETAIL can carry digests/envelopes)
            await OutboxRepository(uow.session).mark_failed(third.id, "d1", third.attempt_count, "timeout: Failing row contains (...)", None, 4)


async def test_idempotency_expiry_key_id_and_project_mismatch_are_refused(world: Pg, engine_for):
    api, key, fp = engine_for("ai_res_api"), b"\x1a" * 32, b"\x1b" * 32
    scope = uuid4()

    async def begin(project: UUID | None = PRJ_A, key_id: str = "k1", expires: datetime | None = None) -> Any:
        async with tenant_uow(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            return await IdempotencyRepository(uow.session).begin(ORG_A, project, "PROJECT", scope, key, key_id, fp, expires or utc_now() + timedelta(days=1))

    created = await begin()
    assert created.outcome == IdempotencyOutcome.NEW
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ValueError, match="sensitive"):  # the stored response is replayed to later callers: no secret-looking keys
            await IdempotencyRepository(uow.session).complete(created.id, "COMPLETED", "OPERATION", uuid4(), 202, {"token": "x"})
    assert (await begin()).outcome == IdempotencyOutcome.IN_PROGRESS  # control: the same context is a legitimate retry (and the record is still unfinished)
    with pytest.raises(ProblemError) as exc:  # another HMAC key must not replay this record
        await begin(key_id="k2")
    assert exc.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED
    with pytest.raises(DBAPIError):  # another project than the tenant context: RLS refuses the write first (WITH CHECK); the repository's own project comparison is a second barrier no RLS-visible row can reach
        await begin(project=None)
    scope = uuid4()  # expires_at is immutable (even for the owner): an expired record is created already expired
    assert (await begin(expires=utc_now() - timedelta(seconds=1))).outcome == IdempotencyOutcome.NEW
    with pytest.raises(ProblemError) as expired:  # an expired record is neither replayed nor treated as new (G-58: purge/takeover policy is undecided)
        await begin()
    assert expired.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED


async def test_stored_payloads_reject_secret_keys_and_empty_updates(world: Pg, engine_for):
    api = engine_for("ai_res_api")
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        ops, tasks, runs = OperationRepository(uow.session), TaskRepository(uow.session), WorkerRunRepository(uow.session)
        op, _ = await ops.create(new_operation(), spec())
        epic = await tasks.create_epic(NewEpic(ORG_A, PRJ_A, "epic", "ACTIVE"))
        task = await tasks.create_task(NewTask(ORG_A, PRJ_A, op.id, epic, "ANALYSIS", "t", "PROPOSED", "MANAGER"))
        run, _ = await runs.create(NewWorkerRun(ORG_A, PRJ_A, op.id, task.id, WDV, CPV, "in-1", "out-1"), spec("worker_run.created"))
        ev = await ReadinessRepository(uow.session).record(evaluation(run.id, "READY", 1), [NewCheck("TASK_ACTIVE", "PASS", "INFO")])
        await runs.start(run, ev, spec("worker_run.started"))
        started = await runs.get(run.id)
        assert started is not None
        for bad in ({"a": {"api_token": "x"}}, {"items": [{"password": "x"}]}, {"keyDigest": "x"}, {"secretCiphertext": "x"}):
            with pytest.raises(ValueError, match="sensitive"):  # the payload is checked before any SQL
                await runs.store_result(started, "wip-1", bad)
        with pytest.raises(ValueError, match="sensitive"):  # persisted snapshots of the Gate are guarded too
            await ReadinessRepository(uow.session).record(evaluation(run.id, "READY", 2), [NewCheck("OTHER", "PASS", "INFO", details={"authorization": "x"})])
        with pytest.raises(ValueError, match="sensitive"):
            await ops.transition(op, "QUEUED", spec("operation.started"), result_ref={"credentials": "x"})
        with pytest.raises(ValueError, match="at least one change"):  # a bare version bump would invalidate other writers' If-Match for nothing
            await tasks.update_epic(epic, 1)
    with world.connect() as c:
        assert c.execute("SELECT count(*) FROM agents.worker_results").fetchone() == (0,)


async def test_a_reference_to_a_source_version_is_a_legitimate_event_reference(world: Pg, engine_for):
    """verification pass (security MEDIUM): `SourceVersion`/`source_id` name content, they are not content, and must not trip the secret-key guard."""
    async with tenant_uow(engine_for("ai_res_api")) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        row, _ = await OperationRepository(uow.session).create(new_operation(), spec())
        source = uuid4()
        legit = spec(refs=(EventRef("SourceVersion", source, uuid4()),), reason_code="SOURCE_CHANGED", data={"source_id": str(source)})
        appended = await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id,
                                      expected_version=row.row_version, spec=legit)
        assert appended.aggregate_sequence == 2
        with pytest.raises(ValueError, match="sensitive"):  # while a run-together secret key is now caught
            await append_event(uow.session, OPERATION_KIND, aggregate_id=row.id, organization_id=ORG_A, project_id=PRJ_A, operation_id=row.id,
                               expected_version=appended.row_version, spec=spec(data={"accesstoken": "x"}))
