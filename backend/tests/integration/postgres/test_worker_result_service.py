# ruff: noqa: E501, F811  -- fixtures are imported by name (pytest fixtures); long literal fixtures
"""S14: storing a WorkerResult through the Application Service — contract check at RESULT_RECEIPT, ownership by run/task/role, immutability."""
import dataclasses
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ai_res.modules.operations.repository import OperationRepository
from ai_res.modules.readiness.repository import NewCheck, ReadinessRepository
from ai_res.modules.tasks.repository import NewEpic, NewTask, TaskRepository
from ai_res.modules.worker_runs.repository import NewWorkerRun, WorkerRunRepository, WorkerRunRow
from ai_res.modules.worker_runs.results import store_worker_result
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.worker_contracts import WorkerContracts

from .conftest import Pg
from .test_repositories import CPV, ORG_A, ORG_B, PRJ_A, PRJ_B, WDV, engine_for, evaluation, new_operation, spec, tenant_uow, world  # noqa: F401

pytestmark = pytest.mark.postgres
SCHEMA = Path(__file__).resolve().parents[4] / "contracts" / "json-schema" / "worker" / "AI_RES_Worker_Contracts_v1.1.schema.json"


def valid_result(run: WorkerRunRow, **over: Any) -> dict[str, Any]:
    ref = {"objectType": "SourceVersion", "objectId": str(uuid4()), "versionId": str(uuid4())}
    base: dict[str, Any] = {
        "contractVersion": "1.1", "workerRunId": str(run.id), "taskId": str(run.task_id), "workerRole": "REQUIREMENTS", "resultStatus": "COMPLETED", "summary": "done",
        "findings": [{"findingId": "F-1", "classification": "FACT", "statement": "login exists", "evidenceRefs": [ref]}], "proposedChanges": [], "artifactRefs": [],
        "questions": [], "blockers": [], "limitations": [], "validation": {"selfAssessment": "PASS"}, "completedAt": "2026-11-13T10:00:00Z"}
    return base | over


async def created_run(engine_for_api, *, start: bool = True) -> WorkerRunRow:
    async with tenant_uow(engine_for_api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        ops, tasks, runs, ready = OperationRepository(uow.session), TaskRepository(uow.session), WorkerRunRepository(uow.session), ReadinessRepository(uow.session)
        op, _ = await ops.create(new_operation(), spec())
        epic = await tasks.create_epic(NewEpic(ORG_A, PRJ_A, "epic", "ACTIVE"))
        task = await tasks.create_task(NewTask(ORG_A, PRJ_A, op.id, epic, "ANALYSIS", "analyse", "PROPOSED", "MANAGER", acceptance_criteria=("a",)))
        run, _ = await runs.create(NewWorkerRun(ORG_A, PRJ_A, op.id, task.id, WDV, CPV, "in-1", "out-1"), spec("worker_run.created"))
        if not start:
            return await runs.get(run.id)  # type: ignore[return-value]
        good = await ready.record(evaluation(run.id, "READY", 1), [NewCheck("TASK_ACTIVE", "PASS", "INFO")])
        run = await runs.get(run.id)  # type: ignore[assignment]
        await runs.start(run, good, spec("worker_run.started"))
        run = await runs.get(run.id)  # type: ignore[assignment]
        await runs.transition(run, "RUNNING", spec("worker_run.resumed"))
        return await runs.get(run.id)  # type: ignore[return-value]


async def started_run(engine_for_api) -> WorkerRunRow:
    return await created_run(engine_for_api)


@pytest.fixture(scope="module")
def contracts() -> WorkerContracts:
    return WorkerContracts.from_file(SCHEMA)


async def count_results(world: Pg, run: WorkerRunRow) -> int:
    with world.connect() as c:
        return int(c.execute("SELECT count(*) FROM agents.worker_results WHERE worker_run_id = %s", [run.id]).fetchone()[0])  # type: ignore[index]


async def test_valid_result_is_stored_once_and_a_second_one_is_refused(world: Pg, engine_for, contracts):
    api = engine_for("ai_res_api")
    run = await started_run(api)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        stored = await store_worker_result(uow.session, contracts, run, valid_result(run))
    assert stored and await count_results(world, run) == 1
    with world.connect() as c:
        assert c.execute("SELECT contract_version FROM agents.worker_results WHERE id = %s", [stored]).fetchone() == ("1.1",)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ProblemError) as exc:
            await store_worker_result(uow.session, contracts, run, valid_result(run, summary="second attempt"))
        assert exc.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    assert await count_results(world, run) == 1
    with world.connect() as c:
        assert c.execute("SELECT payload->>'summary' FROM agents.worker_results WHERE worker_run_id = %s", [run.id]).fetchone() == ("done",)  # the first result stands


@pytest.mark.parametrize("override", [
    {"contractVersion": "2.0"}, {"contractVersion": "1.2"}, {"rawLlmResponse": "x"}, {"findings": [{"findingId": "F", "classification": "FACT", "statement": "s", "evidenceRefs": []}]},
    {"summary": "password=hunter2hunter2"}])
async def test_contract_violations_store_nothing(world: Pg, engine_for, contracts, override):
    api = engine_for("ai_res_api")
    run = await started_run(api)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ProblemError) as exc:
            await store_worker_result(uow.session, contracts, run, valid_result(run, **override))
        assert exc.value.code is ErrorCode.VALIDATION_ERROR and "hunter2" not in str(exc.value.detail) + str(exc.value.errors)
    assert await count_results(world, run) == 0


@pytest.mark.parametrize("override", [{"workerRunId": str(uuid4())}, {"taskId": str(uuid4())}, {"workerRole": "RESEARCH"}])
async def test_result_must_belong_to_the_run_task_and_registered_role(world: Pg, engine_for, contracts, override):
    api = engine_for("ai_res_api")
    run = await started_run(api)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ProblemError) as exc:
            await store_worker_result(uow.session, contracts, run, valid_result(run, **override))
        assert exc.value.code is ErrorCode.VALIDATION_ERROR
    assert await count_results(world, run) == 0


async def test_run_that_has_not_started_or_is_terminal_gets_no_result(world: Pg, engine_for, contracts):
    api = engine_for("ai_res_api")
    fresh = await created_run(api, start=False)
    done = await started_run(api)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        await WorkerRunRepository(uow.session).transition(done, "COMPLETED", spec("worker_run.completed"))
    for run in (fresh, done):
        async with tenant_uow(api) as uow:
            await uow.with_tenant(ORG_A, PRJ_A)
            with pytest.raises(ProblemError) as exc:
                await store_worker_result(uow.session, contracts, run, valid_result(run))
            assert exc.value.code is ErrorCode.STATE_TRANSITION_NOT_ALLOWED
        assert await count_results(world, run) == 0


async def test_foreign_tenant_run_is_not_found_and_not_distinguishable(world: Pg, engine_for, contracts):
    api = engine_for("ai_res_api")
    run = await started_run(api)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_B, PRJ_B)  # another tenant: RLS hides the run
        with pytest.raises(ProblemError) as foreign:
            await store_worker_result(uow.session, contracts, run, valid_result(run))
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        with pytest.raises(ProblemError) as forged:  # right tenant context, but the caller's row claims another organization
            await store_worker_result(uow.session, contracts, dataclasses.replace(run, organization_id=ORG_B), valid_result(run))
    assert foreign.value.code is ErrorCode.RESOURCE_NOT_FOUND and forged.value.code is ErrorCode.RESOURCE_NOT_FOUND
    assert foreign.value.detail == forged.value.detail
    assert await count_results(world, run) == 0


async def test_stored_payload_is_the_validated_snapshot(world: Pg, engine_for, contracts):
    api = engine_for("ai_res_api")
    run = await started_run(api)
    payload = valid_result(run)
    async with tenant_uow(api) as uow:
        await uow.with_tenant(ORG_A, PRJ_A)
        stored = await store_worker_result(uow.session, contracts, run, payload)
    with world.connect() as c:
        row = c.execute("SELECT payload FROM agents.worker_results WHERE id = %s", [stored]).fetchone()
    assert row is not None and row[0] == payload  # strict JSON, identical to what was validated
