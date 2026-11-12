# ruff: noqa: E501, S608, F811  -- fixed literal SQL in test assertions
"""S12: cancellation request + reconciliation on real PostgreSQL (State Machine v1.2; Decision v1.6 §2.4). The request is recorded first (202 semantics);
CANCELLED is written only by reconciliation, a terminal fact is never overwritten, and an Operation with an active WorkerRun stays CANCEL_REQUESTED."""
from uuid import UUID, uuid4

import pytest

from ai_res.db.session import UnitOfWork
from ai_res.modules.operations.cancellation import request_cancellation
from ai_res.orchestration.contracts import CANCEL_DESTINATION, OperationFailure, OperationRef
from ai_res.orchestration.platform_port import PlatformPermanentError
from ai_res.platform.problems import ErrorCode, ProblemError

from .test_agents_execution_schema import new_run
from .test_internal_platform_api import ORG, ORG2, PRJ, PRJ2, Env, env  # noqa: F401  (fixture)
from .test_operations_work_schema import new_epic, new_task

pytestmark = pytest.mark.postgres
USER = uuid4()


async def cancel(env: Env, ref: OperationRef) -> None:
    async with UnitOfWork(env.factory) as uow:
        await uow.with_tenant(UUID(ref.organization_id), UUID(ref.project_id))
        await request_cancellation(uow.session, UUID(ref.operation_id), actor_id=USER, correlation_id=uuid4())


def outbox_destinations(env: Env, ref: OperationRef) -> list[str]:
    with env.pg.connect() as c:
        return [r[0] for r in c.execute("SELECT destination FROM audit.outbox_events WHERE aggregate_id=%s AND event_type LIKE '%%cancel%%' ORDER BY destination", [ref.operation_id]).fetchall()]


async def test_cancel_before_start_is_immediately_cancelled_with_no_orchestrator_command(env: Env):
    ref = await env.new_operation()
    await cancel(env, ref)
    assert env.row(ref)[0] == "CANCELLED" and env.row(ref)[3] is True  # completed_at stamped with the terminal status
    assert CANCEL_DESTINATION not in outbox_destinations(env, ref)  # nothing was started, so there is nothing to tell Temporal


async def test_cancel_of_a_running_operation_only_records_the_request_and_queues_the_orchestrator_command(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    await cancel(env, ref)
    assert env.row(ref)[0] == "CANCEL_REQUESTED"  # 202 semantics: not cancelled yet
    assert CANCEL_DESTINATION in outbox_destinations(env, ref)
    assert env.scalar("SELECT count(*) FROM operations.operations WHERE id=%s AND cancel_requested_at IS NOT NULL", ref.operation_id) == 1
    await cancel(env, ref)  # idempotent by state: no second event, no second command
    assert outbox_destinations(env, ref).count(CANCEL_DESTINATION) == 1


async def test_reconciliation_turns_a_requested_cancel_into_cancelled_exactly_once(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    await cancel(env, ref)
    first = await env.platform().confirm_cancellation(ref)
    again = await env.platform().confirm_cancellation(ref)
    assert (first.status, again.status) == ("CANCELLED", "CANCELLED")
    assert env.scalar("SELECT count(*) FROM operations.operation_events WHERE operation_id=%s AND event_type='operation.cancelled'", ref.operation_id) == 1


async def test_confirm_is_a_no_op_unless_a_cancel_was_actually_requested(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    assert (await env.platform().confirm_cancellation(ref)).status == "RUNNING"  # a forged/premature signal cannot cancel anything
    assert env.row(ref)[0] == "RUNNING"


async def test_a_finished_operation_is_never_cancelled_or_reopened(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    await env.platform().record_failure(OperationFailure(ref, "SOME_FAILURE"))
    with pytest.raises(ProblemError) as err:
        await cancel(env, ref)
    assert err.value.code == ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    assert (await env.platform().confirm_cancellation(ref)).status == "FAILED" and env.row(ref)[0] == "FAILED"  # the real outcome wins over a late cancel


async def test_active_worker_run_keeps_the_operation_cancel_requested_until_it_is_reconciled(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    with env.pg.connect() as c:
        epic = new_epic(c, ORG, PRJ)
        task = new_task(c, ORG, PRJ, UUID(ref.operation_id), epic)
        run = new_run(c, ORG, PRJ, UUID(ref.operation_id), task)
    await cancel(env, ref)
    assert (await env.platform().confirm_cancellation(ref)).status == "CANCEL_REQUESTED"  # branch still active: no false CANCELLED
    with env.pg.connect() as c:
        c.execute("UPDATE agents.worker_runs SET status='CANCELLED', finished_at=now(), row_version=row_version+1 WHERE id=%s", [run])
    assert (await env.platform().confirm_cancellation(ref)).status == "CANCELLED"


async def test_confirm_with_a_forged_tenant_claim_is_the_same_404_as_a_missing_operation(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    await cancel(env, ref)
    forged = OperationRef(ref.operation_id, str(ORG2), str(PRJ2))
    with pytest.raises(PlatformPermanentError):
        await env.platform().confirm_cancellation(forged)
    assert env.row(ref)[0] == "CANCEL_REQUESTED"


async def test_a_real_failure_wins_over_a_pending_cancel_and_keeps_its_problem_code(env: Env):
    ref = await env.new_operation()
    await env.platform().acknowledge_start(ref)
    await cancel(env, ref)
    assert env.row(ref)[0] == "CANCEL_REQUESTED"
    state = await env.platform().record_failure(OperationFailure(ref, "SOME_FAILURE"))  # architect review M1: the outcome is not swallowed by the cancel
    assert state.status == "FAILED" and env.row(ref)[0] == "FAILED"
    assert env.scalar("SELECT count(*) FROM operations.operation_events WHERE operation_id=%s AND event_type='operation.failed' AND from_status='CANCEL_REQUESTED' "
                      "AND reason_code='SOME_FAILURE'", ref.operation_id) == 1
    assert (await env.platform().confirm_cancellation(ref)).status == "FAILED"  # and the late reconciliation cannot turn it into CANCELLED
