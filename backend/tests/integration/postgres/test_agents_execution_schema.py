# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S05 slice C: agents (worker_runs, worker_run_events, worker_results) + execution (readiness_evaluations, readiness_check_results), ADR-052.

Seeding as the bootstrap superuser; behaviour asserted as `ai_res_api`. The Readiness Gate invariants (State Machine v1.2 `invariants`) that the
database can decide on its own are tested here; transition legality and TOCTOU revalidation stay in the domain service (S13).
"""
import json
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from .conftest import Pg, run_audit
from .test_operations_work_schema import ORG_A, ORG_B, PRJ_A1, PRJ_A2, PRJ_B, api, new_epic, new_op, new_task

pytestmark = pytest.mark.postgres
H = b"\x03" * 32
TERMINAL_RUN = ("COMPLETED", "REWORK_REQUIRED", "REJECTED", "UNVERIFIED", "FAILED", "TIMED_OUT", "CANCELLED")


def new_run(c: psycopg.Connection[Any], org: UUID, prj: UUID, op: UUID, task: UUID, status: str = "CREATED", derived: UUID | None = None,
            reason: str | None = None) -> UUID:
    rid = uuid4()
    fin = "now()" if status in TERMINAL_RUN else "NULL"
    c.execute(
        "INSERT INTO agents.worker_runs (id, organization_id, project_id, operation_id, task_id, worker_definition_version_id, status, derived_from_worker_run_id, "
        "derivation_reason, context_package_version_id, input_contract_version, output_contract_version, finished_at, attempt_number) "
        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'in-1','out-1',{fin}, (SELECT coalesce(max(attempt_number), 0) + 1 FROM agents.worker_runs WHERE task_id = %s))",
        [rid, org, prj, op, task, uuid4(), status, derived, reason, uuid4(), task])  # each new run of a task is its next attempt (UNIQUE per task and attempt)
    return rid


def new_eval(c: psycopg.Connection[Any], run: UUID, number: int = 1, status: str = "COMPLETED", outcome: str | None = "READY", **overrides: Any) -> UUID:
    """The evaluation is computed for the run's own definition/context/output contract versions unless a test overrides them (stale-evaluation cases)."""
    eid = uuid4()
    c.execute(
        "INSERT INTO execution.readiness_evaluations (id, worker_run_id, evaluation_number, evaluation_status, gate_outcome, snapshot_hash, task_version, "
        "worker_definition_version_id, context_package_version_id, ruleset_version, policy_engine_version, grant_snapshot_ref, tool_allowlist_snapshot, "
        "output_contract_version, budget_profile_version, dependency_snapshot, evaluator_version, evaluated_at) "
        "SELECT %s, r.id, %s, %s, %s, %s, 1, coalesce(%s, r.worker_definition_version_id), coalesce(%s, r.context_package_version_id), 'r1','p1','{}','[]', "
        "coalesce(%s, r.output_contract_version), 'b1','{}','e1', now() FROM agents.worker_runs r WHERE r.id = %s",
        [eid, number, status, outcome, H, overrides.get("wdv"), overrides.get("cpv"), overrides.get("ocv"), run])
    return eid


def new_check(c: psycopg.Connection[Any], run: UUID, ev: UUID, code: str = "TASK_ACTIVE") -> UUID:
    cid = uuid4()
    c.execute("INSERT INTO execution.readiness_check_results (id, worker_run_id, readiness_evaluation_id, check_code, result, severity) "
              "VALUES (%s,%s,%s,%s,'PASS','INFO')", [cid, run, ev, code])
    return cid


def run_event_sql(seq: int) -> str:
    return ("INSERT INTO agents.worker_run_events (event_id, worker_run_id, aggregate_sequence, aggregate_version, event_type, schema_version, source, subject, "
            f"occurred_at, correlation_id, actor_type, data) VALUES (%s,%s,{seq},{seq},'worker_run.created',1,'ai-res/api','run',now(),%s,'SYSTEM','{{}}'::jsonb)")


def start(c: psycopg.Connection[Any], run: UUID, ev: UUID | None, status: str = "STARTING") -> Any:
    return c.execute("UPDATE agents.worker_runs SET started_with_readiness_evaluation_id = %s, status = %s, started_at = now(), row_version = row_version + 1 "
                     "WHERE id = %s", [ev, status, run])


@pytest.fixture
def world(migrated: Pg) -> tuple[Pg, dict[str, UUID]]:
    ids: dict[str, UUID] = {}
    with migrated.connect() as c:
        for org in (ORG_A, ORG_B):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        for prj, org in ((PRJ_A1, ORG_A), (PRJ_A2, ORG_A), (PRJ_B, ORG_B)):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
        epic = new_epic(c, ORG_A, PRJ_A1)
        ids["op"], ids["op2"] = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A1)
        ids["task"], ids["task_op2"] = new_task(c, ORG_A, PRJ_A1, ids["op"], epic), new_task(c, ORG_A, PRJ_A1, ids["op2"], epic)
        ids["run"] = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])
        ids["epic2"] = new_epic(c, ORG_A, PRJ_A2)
        ids["op_a2"] = new_op(c, ORG_A, PRJ_A2)
        ids["task_a2"] = new_task(c, ORG_A, PRJ_A2, ids["op_a2"], ids["epic2"])
        ids["run_a2"] = new_run(c, ORG_A, PRJ_A2, ids["op_a2"], ids["task_a2"])
    return migrated, ids


def test_audits_clean_and_tables_exist(world):
    pg, _ = world
    with pg.connect() as c:
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == [] and run_audit(c, "postflight.sql") == []
        tables = {r[0] for r in c.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('agents','execution')")}
    assert tables == {"agents.worker_runs", "agents.worker_run_events", "agents.worker_results", "execution.readiness_evaluations", "execution.readiness_check_results"}


@pytest.mark.parametrize("table", ["agents.worker_runs", "agents.worker_run_events", "agents.worker_results", "execution.readiness_evaluations", "execution.readiness_check_results"])
def test_default_deny_and_org_only_context(world, table: str):
    pg, ids = world
    with pg.connect() as c:
        with c.transaction():  # checks must be written in the evaluation's own transaction
            ev = new_eval(c, ids["run"])
            new_check(c, ids["run"], ev)
        start(c, ids["run"], ev)  # a WorkerResult exists only for a run that passed the Gate
        with c.transaction():
            c.execute(run_event_sql(1), [uuid4(), ids["run"], uuid4()])
            c.execute("UPDATE agents.worker_runs SET last_event_sequence = 1, row_version = row_version + 1 WHERE id = %s", [ids["run"]])
        c.execute("INSERT INTO agents.worker_results (id, organization_id, project_id, worker_run_id, contract_version, payload, payload_hash) "
                  "VALUES (%s,%s,%s,%s,'wip-1','{}',%s)", [uuid4(), ORG_A, PRJ_A1, ids["run"], H])
    for org, prj in ((None, None), (ORG_A, None)):
        with api(pg, org, prj) as c:
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= 1  # type: ignore[index]  # positive control


def test_tenant_and_sibling_project_isolation_including_forged_ids(world):
    pg, ids = world
    with pg.connect() as c:
        ev_a2 = new_eval(c, ids["run_a2"])
    with api(pg, ORG_A, PRJ_A1) as c:
        assert [r[0] for r in c.execute("SELECT id FROM agents.worker_runs")] == [ids["run"]]
        assert c.execute("SELECT count(*) FROM execution.readiness_evaluations WHERE id = %s", [ev_a2]).fetchone() == (0,)  # child of a foreign run
        assert c.execute("UPDATE agents.worker_runs SET status='PREPARING', row_version=row_version+1 WHERE id=%s", [ids["run_a2"]]).rowcount == 0
        # new_eval reads the run (INSERT..SELECT) and would silently insert nothing under RLS: forge the row with explicit values instead
        assert c.execute("SELECT count(*) FROM agents.worker_runs WHERE id = %s", [ids["run_a2"]]).fetchone() == (0,)
        with pytest.raises(errors.InsufficientPrivilege):  # evaluation attached to a run of another project
            c.execute(
                "INSERT INTO execution.readiness_evaluations (id, worker_run_id, evaluation_number, evaluation_status, gate_outcome, snapshot_hash, task_version, "
                "worker_definition_version_id, context_package_version_id, ruleset_version, policy_engine_version, grant_snapshot_ref, tool_allowlist_snapshot, "
                "output_contract_version, budget_profile_version, dependency_snapshot, evaluator_version, evaluated_at) "
                "VALUES (%s,%s,1,'COMPLETED','READY',%s,1,%s,%s,'r1','p1','{}','[]','out-1','b1','{}','e1',now())",
                [uuid4(), ids["run_a2"], H, uuid4(), uuid4()])


def test_worker_run_must_match_its_task_operation_and_scope(world):
    pg, ids = world
    with pg.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # task belongs to op2, run claims op
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task_op2"])
    with pg.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # task of another project
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task_a2"])
    with pg.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # scope claimed does not match the task
        new_run(c, ORG_A, PRJ_A2, ids["op"], ids["task"])


def test_worker_run_cannot_be_created_in_a_terminal_operation(world):
    pg, ids = world
    with pg.connect() as c:
        c.execute("UPDATE operations.operations SET status='SUCCEEDED', completed_at=now(), row_version=row_version+1 WHERE id=%s", [ids["op"]])
    with pg.connect() as c, pytest.raises(errors.IntegrityConstraintViolation):
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])


def test_started_states_require_a_readiness_evaluation(world):
    pg, ids = world
    for status in ("STARTING", "RUNNING", "RESULT_SUBMITTED"):
        with pg.connect() as c, pytest.raises(errors.CheckViolation):
            c.execute("UPDATE agents.worker_runs SET status=%s, row_version=row_version+1 WHERE id=%s", [status, ids["run"]])
    with pg.connect() as c, pytest.raises(errors.CheckViolation):  # started_at without evaluation
        c.execute("UPDATE agents.worker_runs SET started_at=now(), row_version=row_version+1 WHERE id=%s", [ids["run"]])


def test_start_accepts_only_a_completed_ready_evaluation_of_the_same_run(world):
    pg, ids = world
    with pg.connect() as c:
        bad = {o: new_eval(c, ids["run"], n, outcome=o) for n, o in enumerate(("BLOCKED", "STALE"), start=1)}
        err = new_eval(c, ids["run"], 3, status="EVALUATOR_ERROR", outcome=None)
        ok = new_eval(c, ids["run"], 4, outcome="READY_WITH_LIMITATIONS")
        foreign = new_eval(c, ids["run_a2"])
    for ev in (*bad.values(), err):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
            start(c, ids["run"], ev)
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.ForeignKeyViolation):  # evaluation of another run (deferred FK fires at COMMIT)
        start(c, ids["run"], foreign)
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        assert start(c, ids["run"], ok).rowcount == 1
        c.commit()


def test_started_with_is_immutable_once_set_but_latest_may_advance_before_start(world):
    pg, ids = world
    with pg.connect() as c:
        e1, e2 = new_eval(c, ids["run"], 1), new_eval(c, ids["run"], 2)
    with api(pg, ORG_A, PRJ_A1) as c:  # before start: latest follows each new evaluation
        for ev in (e1, e2):
            c.execute("UPDATE agents.worker_runs SET latest_readiness_evaluation_id=%s, row_version=row_version+1 WHERE id=%s", [ev, ids["run"]])
        start(c, ids["run"], e2)  # the start evaluation is the run's latest one (an older one is stale: test_start_requires_the_latest_evaluation)
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # re-pointing the historical link
        c.execute("UPDATE agents.worker_runs SET started_with_readiness_evaluation_id=%s, row_version=row_version+1 WHERE id=%s", [e1, ids["run"]])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
        c.execute("UPDATE agents.worker_runs SET started_with_readiness_evaluation_id=NULL, row_version=row_version+1 WHERE id=%s", [ids["run"]])
    with api(pg, ORG_A, PRJ_A1) as c:  # the run keeps living: latest may move after start, started_with stays e2
        c.execute("UPDATE agents.worker_runs SET status='RUNNING', latest_readiness_evaluation_id=%s, row_version=row_version+1 WHERE id=%s", [e1, ids["run"]])
        assert c.execute("SELECT started_with_readiness_evaluation_id FROM agents.worker_runs WHERE id=%s", [ids["run"]]).fetchone() == (e2,)


def test_start_requires_the_latest_evaluation(world):
    """A newer BLOCKED evaluation makes an older READY one stale (security + database review): the Gate cannot be won by picking a favourable evaluation."""
    pg, ids = world
    with pg.connect() as c:  # two transactions: the newer BLOCKED evaluation is already committed when the start happens
        old_ready, newer_blocked = new_eval(c, ids["run"], 1, outcome="READY"), new_eval(c, ids["run"], 2, outcome="BLOCKED")
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation, match="not the latest"):
        start(c, ids["run"], old_ready)
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation, match="COMPLETED READY"):
        start(c, ids["run"], newer_blocked)
        c.commit()
    with pg.connect() as c:  # one transaction: the newer evaluation is inserted AFTER the start was linked (deferred check at COMMIT)
        run = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])
        first = new_eval(c, run, 1)
    with pg.connect(autocommit=False) as c, pytest.raises(errors.IntegrityConstraintViolation, match="not the latest"):
        start(c, run, first)
        new_eval(c, run, 2, outcome="BLOCKED")
        c.commit()
    with pg.connect() as c:
        assert c.execute("SELECT status, started_with_readiness_evaluation_id FROM agents.worker_runs WHERE id=%s", [run]).fetchone() == ("CREATED", None)
        assert start(c, run, new_eval(c, run, 3)).rowcount == 1  # control: the newest READY evaluation starts the run


def _in_thread(work: Callable[[], None]) -> tuple[threading.Thread, list[BaseException]]:
    """Runs `work` in a thread; an exception it raises is captured (the main thread holds the other transaction)."""
    failures: list[BaseException] = []

    def target() -> None:
        try:
            work()
        except BaseException as exc:  # noqa: BLE001 - reported to the test, never swallowed
            failures.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, failures


def test_a_concurrent_evaluation_and_start_serialise_and_the_stale_start_loses(world):
    """database review (MEDIUM): an uncommitted newer evaluation must not let a start with the older one slip through (FK takes only KEY SHARE on the run)."""
    pg, ids = world
    with pg.connect() as c:
        old_ready = new_eval(c, ids["run"], 1)
    inserting = api(pg, ORG_A, PRJ_A1)
    new_eval(inserting, ids["run"], 2, outcome="BLOCKED")  # not committed yet

    def start_with_old() -> None:
        with api(pg, ORG_A, PRJ_A1) as c:
            start(c, ids["run"], old_ready)

    starter, failures = _in_thread(start_with_old)
    time.sleep(1.0)
    assert starter.is_alive(), "the start must wait for the transaction that is inserting a newer evaluation"
    inserting.commit()
    inserting.close()
    starter.join(timeout=15)
    assert not starter.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], errors.IntegrityConstraintViolation) and "not the latest" in str(failures[0])
    with pg.connect() as c:
        assert c.execute("SELECT status, started_with_readiness_evaluation_id FROM agents.worker_runs WHERE id=%s", [ids["run"]]).fetchone() == ("CREATED", None)


def test_a_start_that_wins_the_lock_makes_the_later_evaluation_wait_not_fail(world):
    pg, ids = world
    with pg.connect() as c:
        first = new_eval(c, ids["run"], 1)
    starting = api(pg, ORG_A, PRJ_A1)
    start(starting, ids["run"], first)

    def insert_newer() -> None:
        with api(pg, ORG_A, PRJ_A1) as c:
            new_eval(c, ids["run"], 2, outcome="BLOCKED")

    inserter, failures = _in_thread(insert_newer)
    time.sleep(1.0)
    assert inserter.is_alive(), "inserting an evaluation waits for the in-flight start of the same run"
    starting.commit()
    starting.close()
    inserter.join(timeout=15)
    assert not failures  # the run had started with what was the latest when it did; the later evaluation is an ordinary later fact
    with pg.connect() as c:
        assert c.execute("SELECT count(*) FROM execution.readiness_evaluations WHERE worker_run_id=%s", [ids["run"]]).fetchone() == (2,)


def test_twin_result_inserts_for_one_run_do_not_deadlock(world):
    """database review (MEDIUM): FOR SHARE on the run made the twin insert wait on the unique index while the first submitter updated the run: DeadlockDetected."""
    pg, ids = world
    with pg.connect() as c:
        start(c, ids["run"], new_eval(c, ids["run"]), status="RUNNING")
    ins = "INSERT INTO agents.worker_results (id, organization_id, project_id, worker_run_id, contract_version, payload, payload_hash) VALUES (%s,%s,%s,%s,'wip-1','{}',%s)"
    first = api(pg, ORG_A, PRJ_A1)
    first.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], H])

    def twin() -> None:
        with api(pg, ORG_A, PRJ_A1) as c:
            c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], H])

    thread, failures = _in_thread(twin)
    time.sleep(1.0)
    first.execute("UPDATE agents.worker_runs SET status='RESULT_SUBMITTED', row_version=row_version+1 WHERE id=%s", [ids["run"]])
    first.commit()
    first.close()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], errors.IntegrityError), failures  # a clean duplicate, never errors.DeadlockDetected
    with pg.connect() as c:
        assert c.execute("SELECT count(*) FROM agents.worker_results WHERE worker_run_id=%s", [ids["run"]]).fetchone() == (1,)


def test_a_result_needs_a_started_open_run_and_attempts_are_unique(world):
    pg, ids = world
    ins = "INSERT INTO agents.worker_results (id, organization_id, project_id, worker_run_id, contract_version, payload, payload_hash) VALUES (%s,%s,%s,%s,'wip-1','{}',%s)"
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation, match="has not started"):  # never passed the Gate
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], H])
    with pg.connect() as c:
        start(c, ids["run"], new_eval(c, ids["run"]))
        c.execute("UPDATE agents.worker_runs SET status='FAILED', finished_at=now(), row_version=row_version+1 WHERE id=%s", [ids["run"]])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation, match="terminal"):  # results are immutable: none may be added to a finished run
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], H])
    with pg.connect() as c:
        assert c.execute("SELECT count(*) FROM agents.worker_results").fetchone() == (0,)
        with pytest.raises(errors.UniqueViolation):  # a duplicated command cannot create a second run for the same task attempt
            c.execute("INSERT INTO agents.worker_runs (id, organization_id, project_id, operation_id, task_id, worker_definition_version_id, status, "
                      "context_package_version_id, input_contract_version, output_contract_version, attempt_number) VALUES (%s,%s,%s,%s,%s,%s,'CREATED',%s,'in-1','out-1',1)",
                      [uuid4(), ORG_A, PRJ_A1, ids["op"], ids["task"], uuid4(), uuid4()])


def test_evaluation_vocabulary_fail_closed_shape(world):
    pg, ids = world
    for kwargs in ({"status": "EVALUATOR_ERROR", "outcome": "READY"}, {"status": "COMPLETED", "outcome": None}, {"status": "IN_PROGRESS", "outcome": None},
                   {"status": "COMPLETED", "outcome": "MAYBE"}):
        with pg.connect() as c, pytest.raises(errors.CheckViolation):
            new_eval(c, ids["run"], **kwargs)
    with pg.connect() as c:
        new_eval(c, ids["run"], 1)
    with pg.connect() as c, pytest.raises(errors.UniqueViolation):
        new_eval(c, ids["run"], 1)


def test_evaluations_and_check_results_are_immutable_for_everyone(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        ev = new_eval(c, ids["run"])
        new_check(c, ids["run"], ev)
    for table in ("execution.readiness_evaluations", "execution.readiness_check_results"):
        with api(pg, ORG_A, PRJ_A1) as c:
            for sql in (f"UPDATE {table} SET created_at = now()", f"DELETE FROM {table}", f"TRUNCATE {table}"):
                with pytest.raises(errors.InsufficientPrivilege):
                    c.execute(sql)
                c.rollback()
                c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
        with pg.connect() as c:  # superuser: privilege checks pass, the trigger must still refuse
            for sql in (f"UPDATE {table} SET created_at = now()", f"DELETE FROM {table}", f"TRUNCATE {table}"):
                with pytest.raises((errors.IntegrityConstraintViolation, errors.FeatureNotSupported)):  # TRUNCATE of an FK-referenced table: refused by PostgreSQL
                    c.execute(sql)


def test_check_results_must_be_written_with_their_evaluation_and_stay_unique(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        ev = new_eval(c, ids["run"])
        new_check(c, ids["run"], ev, "TASK_ACTIVE")
        with pytest.raises(errors.UniqueViolation), c.transaction():
            new_check(c, ids["run"], ev, "TASK_ACTIVE")
        with pytest.raises(errors.ForeignKeyViolation), c.transaction():  # check bound to a different run than its evaluation
            new_check(c, ids["run_a2"], ev, "OTHER")
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # appending to a finished evaluation in a later transaction
        new_check(c, ids["run"], ev, "POLICY_OK")


def test_worker_result_is_immutable_single_per_run_and_secret_free_shape(world):
    pg, ids = world
    ins = "INSERT INTO agents.worker_results (id, organization_id, project_id, worker_run_id, contract_version, payload, payload_hash) VALUES (%s,%s,%s,%s,'wip-1',%s,%s)"
    with pg.connect() as c:
        start(c, ids["run"], new_eval(c, ids["run"]))
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], json.dumps({"summary": "ok"}), H])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.UniqueViolation):  # rework = a NEW run with its own result, never a second/overwritten one
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run"], "{}", H])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.CheckViolation):
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, ids["run_a2"], "[1]", H])
    with api(pg, ORG_A, PRJ_A1) as c:
        for sql in ("UPDATE agents.worker_results SET contract_version='x'", "DELETE FROM agents.worker_results", "TRUNCATE agents.worker_results"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()
            c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
    with pg.connect() as c:
        for sql in ("UPDATE agents.worker_results SET contract_version='x'", "DELETE FROM agents.worker_results", "TRUNCATE agents.worker_results"):
            with pytest.raises(errors.IntegrityConstraintViolation):
                c.execute(sql)
    with api(pg, ORG_B, PRJ_B) as c, pytest.raises(errors.ForeignKeyViolation):  # a result for a run of another tenant: FK error, never a unique-violation oracle
        c.execute(ins, [uuid4(), ORG_B, PRJ_B, ids["run"], "{}", H])
        c.commit()


def test_terminal_worker_run_is_frozen_and_finished_at_matches_terminality(world):
    pg, ids = world
    with pg.connect() as c, pytest.raises(errors.CheckViolation):
        c.execute("UPDATE agents.worker_runs SET status='FAILED', row_version=row_version+1 WHERE id=%s", [ids["run"]])  # terminal without finished_at
    with pg.connect() as c:
        c.execute("UPDATE agents.worker_runs SET status='FAILED', finished_at=now(), row_version=row_version+1 WHERE id=%s", [ids["run"]])
    for sql in ("UPDATE agents.worker_runs SET status='PREPARING', finished_at=NULL, row_version=row_version+1 WHERE id=%s",
                "UPDATE agents.worker_runs SET result_ref='{}', row_version=row_version+1 WHERE id=%s"):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
            c.execute(sql, [ids["run"]])


def test_lineage_is_project_local_and_needs_a_reason(world):
    pg, ids = world
    with pg.connect() as c:
        child = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"], derived=ids["run"], reason="SPECIALIST_HANDOFF")
        assert c.execute("SELECT derived_from_worker_run_id FROM agents.worker_runs WHERE id=%s", [child]).fetchone() == (ids["run"],)
    with pg.connect() as c, pytest.raises(errors.ForeignKeyViolation):
        new_run(c, ORG_A, PRJ_A2, ids["op_a2"], ids["task_a2"], derived=ids["run"], reason="RETRY")
    with pg.connect() as c, pytest.raises(errors.CheckViolation):
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"], derived=ids["run"], reason=None)
    with pg.connect() as c, pytest.raises(errors.CheckViolation):
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"], derived=None, reason="RETRY")
    with pg.connect() as c, pytest.raises(errors.CheckViolation):
        new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"], derived=ids["run"], reason="MADE_UP")


def test_worker_run_events_are_append_only_and_sequence_checked(world):
    pg, ids = world
    run = ids["run"]
    with api(pg, ORG_A, PRJ_A1) as c:
        for seq in (1, 2):
            c.execute("UPDATE agents.worker_runs SET last_event_sequence=%s, row_version=row_version+1 WHERE id=%s", [seq, run])
            c.execute(run_event_sql(seq), [uuid4(), run, uuid4()])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # gap
        c.execute("UPDATE agents.worker_runs SET last_event_sequence=4, row_version=row_version+1 WHERE id=%s", [run])
        c.execute(run_event_sql(4), [uuid4(), run, uuid4()])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # counter without event
        c.execute("UPDATE agents.worker_runs SET last_event_sequence=3, row_version=row_version+1 WHERE id=%s", [run])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.UniqueViolation):
        c.execute(run_event_sql(2), [uuid4(), run, uuid4()])
    with pg.connect() as c:
        for sql in ("UPDATE agents.worker_run_events SET reason_code='x'", "DELETE FROM agents.worker_run_events", "TRUNCATE agents.worker_run_events"):
            with pytest.raises(errors.IntegrityConstraintViolation):
                c.execute(sql)
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute("DELETE FROM agents.worker_run_events")


@pytest.mark.parametrize("role", ["ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor"])
def test_non_api_roles_have_no_access(world, role: str):
    pg, _ = world
    for table in ("agents.worker_runs", "agents.worker_run_events", "agents.worker_results", "execution.readiness_evaluations", "execution.readiness_check_results"):
        with pg.connect(role) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(f"SELECT 1 FROM {table} LIMIT 1")


def test_api_cannot_delete_or_ddl_and_worker_run_columns_are_versioned_and_immutable(world):
    pg, ids = world
    for sql in ("DELETE FROM agents.worker_runs", "TRUNCATE agents.worker_runs", "DROP TABLE agents.worker_runs"):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(sql)
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
        c.execute("UPDATE agents.worker_runs SET status='PREPARING' WHERE id=%s", [ids["run"]])  # no row_version bump
    for col, val in (("task_id", ids["task_op2"]), ("operation_id", ids["op2"]), ("context_package_version_id", uuid4()), ("attempt_number", 9)):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
            c.execute(f"UPDATE agents.worker_runs SET {col}=%s, row_version=row_version+1 WHERE id=%s", [val, ids["run"]])


def test_gate_cannot_be_bypassed_by_linking_the_evaluation_before_it_exists(world):
    pg, ids = world
    for outcome, status in (("BLOCKED", "COMPLETED"), ("STALE", "COMPLETED")):
        with pg.connect() as c:
            run = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])
        ev = uuid4()
        with pg.connect(autocommit=False) as c, pytest.raises(errors.IntegrityConstraintViolation, match="COMPLETED READY"):
            start(c, run, ev)  # link first: the BEFORE guard cannot see the evaluation yet
            c.execute(
                "INSERT INTO execution.readiness_evaluations (id, worker_run_id, evaluation_number, evaluation_status, gate_outcome, snapshot_hash, task_version, "
                "worker_definition_version_id, context_package_version_id, ruleset_version, policy_engine_version, grant_snapshot_ref, tool_allowlist_snapshot, "
                "output_contract_version, budget_profile_version, dependency_snapshot, evaluator_version, evaluated_at) "
                "SELECT %s, r.id, 1, %s, %s, %s, 1, r.worker_definition_version_id, r.context_package_version_id, 'r1','p1','{}','[]', r.output_contract_version, 'b1','{}','e1', now() "
                "FROM agents.worker_runs r WHERE r.id = %s", [ev, status, outcome, H, run])
            c.commit()  # the deferred check runs here
        with pg.connect() as c:
            assert c.execute("SELECT status, started_with_readiness_evaluation_id FROM agents.worker_runs WHERE id = %s", [run]).fetchone() == ("CREATED", None)


def test_start_evaluation_must_be_computed_for_the_runs_own_versions(world):
    pg, ids = world
    for override in ({"cpv": uuid4()}, {"wdv": uuid4()}, {"ocv": "out-2"}):
        with pg.connect() as c:
            run = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])
            stale = new_eval(c, run, **override)
        with pg.connect(autocommit=False) as c, pytest.raises(errors.IntegrityConstraintViolation, match="stale evaluation"):
            start(c, run, stale)
            c.commit()


def test_ready_cannot_carry_blockers(world):
    pg, ids = world
    with pg.connect() as c:
        run = new_run(c, ORG_A, PRJ_A1, ids["op"], ids["task"])
        ev = new_eval(c, run, outcome="BLOCKED")
        with pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO execution.readiness_evaluations (id, worker_run_id, evaluation_number, evaluation_status, gate_outcome, snapshot_hash, task_version, "
                      "worker_definition_version_id, context_package_version_id, ruleset_version, policy_engine_version, grant_snapshot_ref, tool_allowlist_snapshot, "
                      "output_contract_version, budget_profile_version, dependency_snapshot, evaluator_version, blockers, evaluated_at) "
                      "VALUES (%s,%s,2,'COMPLETED','READY',%s,1,%s,%s,'r1','p1','{}','[]','out-1','b1','{}','e1','[\"X\"]', now())", [uuid4(), run, H, uuid4(), uuid4()])
    assert ev


def test_child_cannot_slip_under_an_operation_that_turns_terminal_concurrently(world):
    pg, ids = world
    with pg.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
        epic = new_epic(c, ORG_A, PRJ_A1)
    finisher = pg.connect(autocommit=False)
    finisher.execute("UPDATE operations.operations SET status = 'CANCELLED', completed_at = now(), row_version = row_version + 1 WHERE id = %s", [op])
    result: list[BaseException | None] = []

    def insert_task() -> None:
        try:
            with pg.connect() as c:
                c.execute("SET lock_timeout = '5s'")
                new_task(c, ORG_A, PRJ_A1, op, epic)
            result.append(None)
        except BaseException as exc:  # noqa: BLE001 - the outcome is asserted below
            result.append(exc)

    import threading
    import time
    t = threading.Thread(target=insert_task)
    t.start()
    time.sleep(0.5)  # the inserter now waits on the row lock instead of reading a stale RUNNING
    finisher.commit()
    t.join(10)
    finisher.close()
    assert len(result) == 1 and isinstance(result[0], errors.IntegrityConstraintViolation)
