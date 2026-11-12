# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S05 slice B: operations + work (ADR-011, ADR-012, ADR-013, ADR-034, ADR-051) under real runtime roles.

Seeding as the bootstrap superuser (bypasses RLS and privileges; FKs and triggers still apply). Behaviour is asserted as `ai_res_api`.
"""
import threading
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from .conftest import Pg, run_audit

pytestmark = pytest.mark.postgres
ORG_A, ORG_B = uuid4(), uuid4()
PRJ_A1, PRJ_A2, PRJ_B = uuid4(), uuid4(), uuid4()
FP = b"\x02" * 32
TERMINAL = ("SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED")


def op_sql(status: str = "ACCEPTED") -> str:
    done = "now()" if status in TERMINAL else "NULL"
    return (f"INSERT INTO operations.operations (id, organization_id, project_id, operation_type, status, initiator_type, idempotency_scope, "
            f"request_fingerprint, completion_policy_version, completion_policy_snapshot, correlation_id, completed_at) "
            f"VALUES (%s,%s,%s,%s,'{status}','USER','scope',%s,'wip-1','{{}}'::jsonb,%s,{done})")


def new_op(c: psycopg.Connection[Any], org: UUID, prj: UUID, status: str = "ACCEPTED", op_type: str = "PLAN_EXECUTION") -> UUID:
    oid = uuid4()
    c.execute(op_sql(status), [oid, org, prj, op_type, FP, uuid4()])
    return oid


def new_epic(c: psycopg.Connection[Any], org: UUID, prj: UUID) -> UUID:
    eid = uuid4()
    c.execute("INSERT INTO work.epics (id, organization_id, project_id, title, status) VALUES (%s,%s,%s,'epic','ACTIVE')", [eid, org, prj])
    return eid


def new_task(c: psycopg.Connection[Any], org: UUID, prj: UUID, op: UUID | None, epic: UUID, derived: UUID | None = None) -> UUID:
    tid = uuid4()
    c.execute("INSERT INTO work.tasks (id, organization_id, project_id, operation_id, epic_id, derived_from_task_id, task_type, title, status, initiator_type) "
              "VALUES (%s,%s,%s,%s,%s,%s,'ANALYSIS','t','PROPOSED','MANAGER')", [tid, org, prj, op, epic, derived])
    return tid


def event_sql(seq: int) -> str:
    return ("INSERT INTO operations.operation_events (event_id, operation_id, aggregate_sequence, aggregate_version, event_type, schema_version, source, "
            f"subject, occurred_at, correlation_id, actor_type, data) VALUES (%s,%s,{seq},{seq},'operation.accepted',1,'ai-res/api','op',now(),%s,'SYSTEM','{{}}'::jsonb)")


def allocate_and_append(c: psycopg.Connection[Any], op: UUID) -> int:
    """The repository contract: bump last_event_sequence under the row lock, then insert exactly that sequence (no MAX()+1)."""
    seq = c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 "
                    "WHERE id = %s RETURNING last_event_sequence", [op]).fetchone()[0]  # type: ignore[index]
    c.execute(event_sql(seq), [uuid4(), op, uuid4()])
    return int(seq)


def api(pg: Pg, org: UUID | None, project: UUID | None = None) -> psycopg.Connection[Any]:
    conn = pg.connect("ai_res_api", autocommit=False)
    if org is not None:
        conn.execute("SELECT set_config('app.organization_id', %s, true)", [str(org)])
        conn.execute("SELECT set_config('app.project_id', %s, true)", ["" if project is None else str(project)])
    return conn


@pytest.fixture
def seeded(migrated: Pg) -> Pg:
    with migrated.connect() as c:
        for org in (ORG_A, ORG_B):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        for prj, org in ((PRJ_A1, ORG_A), (PRJ_A2, ORG_A), (PRJ_B, ORG_B)):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
    return migrated


def test_audits_are_clean_and_tables_exist(seeded: Pg):
    with seeded.connect() as c:
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == [] and run_audit(c, "postflight.sql") == []
        tables = {r[0] for r in c.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('operations','work')")}
        assert tables == {"operations.operation_types", "operations.operations", "operations.operation_events", "work.epics", "work.epic_events", "work.tasks", "work.task_dependencies", "work.task_requirements"}
        assert c.execute("SELECT count(*) FROM pg_constraint WHERE conrelid='work.tasks'::regclass AND contype='u' "
                         "AND pg_get_constraintdef(oid) = 'UNIQUE (operation_id, id)'").fetchone() == (1,)  # ADR-011/012: target of the worker_runs composite FK


def test_operation_type_registry_is_seeded_read_only_and_enforced(seeded: Pg):
    with api(seeded, None) as c:
        assert {r[0] for r in c.execute("SELECT code FROM operations.operation_types")} == {"MANAGER_MESSAGE", "TASK_EXECUTION", "SOURCE_INGESTION", "PLAN_EXECUTION"}
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("INSERT INTO operations.operation_types (code) VALUES ('BACKDOOR')")
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):
        new_op(c, ORG_A, PRJ_A1, op_type="UNKNOWN_TYPE")


@pytest.mark.parametrize("table", ["operations.operations", "operations.operation_events", "work.epics", "work.tasks", "work.task_dependencies"])
def test_default_deny_without_context_and_with_organization_only_context(seeded: Pg, table: str):
    with seeded.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
        with c.transaction():  # the sequence invariant is checked at COMMIT, so event + counter must share one transaction
            c.execute(event_sql(1), [uuid4(), op, uuid4()])
            c.execute("UPDATE operations.operations SET last_event_sequence = 1, row_version = 2 WHERE id = %s", [op])
        epic = new_epic(c, ORG_A, PRJ_A1)
        t1, t2 = new_task(c, ORG_A, PRJ_A1, op, epic), new_task(c, ORG_A, PRJ_A1, op, epic)
        c.execute("INSERT INTO work.task_dependencies (id, organization_id, project_id, task_id, depends_on_task_id) VALUES (%s,%s,%s,%s,%s)",
                  [uuid4(), ORG_A, PRJ_A1, t1, t2])
    for org, prj in ((None, None), (ORG_A, None)):
        with api(seeded, org, prj) as c:
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)  # noqa: S608
    with api(seeded, ORG_A, PRJ_A1) as c:
        assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= 1  # type: ignore[index]  # noqa: S608 - the positive control


def test_tenants_and_sibling_projects_are_isolated(seeded: Pg):
    with seeded.connect() as c:
        op_a1, op_a2, op_b = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A2), new_op(c, ORG_B, PRJ_B)
    with api(seeded, ORG_A, PRJ_A1) as c:
        assert [r[0] for r in c.execute("SELECT id FROM operations.operations")] == [op_a1]
        assert c.execute("SELECT count(*) FROM operations.operations WHERE id = ANY(%s)", [[op_a2, op_b]]).fetchone() == (0,)  # forged ids: no leak
        assert c.execute("UPDATE operations.operations SET status='RUNNING', row_version=row_version+1 WHERE id=%s", [op_b]).rowcount == 0
        with pytest.raises(errors.InsufficientPrivilege):  # forged organization/project in the payload
            new_op(c, ORG_B, PRJ_B)
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        new_op(c, ORG_A, PRJ_A2)  # same organization, other project


def test_operation_vocabulary_and_completion_invariants(seeded: Pg):
    with seeded.connect() as c, pytest.raises(errors.CheckViolation):  # terminal status without completed_at
        c.execute(op_sql("SUCCEEDED").replace("now()", "NULL"), [uuid4(), ORG_A, PRJ_A1, "PLAN_EXECUTION", FP, uuid4()])
    with seeded.connect() as c, pytest.raises(errors.CheckViolation):
        c.execute(op_sql("NOT_A_STATUS"), [uuid4(), ORG_A, PRJ_A1, "PLAN_EXECUTION", FP, uuid4()])
    with seeded.connect() as c, pytest.raises(errors.CheckViolation):  # fingerprint must be a SHA-256
        c.execute(op_sql(), [uuid4(), ORG_A, PRJ_A1, "PLAN_EXECUTION", b"short", uuid4()])


def test_parent_operation_must_belong_to_the_same_project(seeded: Pg):
    with seeded.connect() as c:
        parent = new_op(c, ORG_A, PRJ_A2)
        with pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO operations.operations (id, organization_id, project_id, parent_operation_id, operation_type, status, initiator_type, "
                      "idempotency_scope, request_fingerprint, completion_policy_version, completion_policy_snapshot, correlation_id) "
                      "VALUES (%s,%s,%s,%s,'PLAN_EXECUTION','ACCEPTED','USER','s',%s,'v','{}',%s)", [uuid4(), ORG_A, PRJ_A1, parent, FP, uuid4()])


def test_terminal_operation_is_frozen_and_cannot_be_reopened(seeded: Pg):
    with api(seeded, ORG_A, PRJ_A1) as c:
        op = new_op(c, ORG_A, PRJ_A1)
        c.execute("UPDATE operations.operations SET status='FAILED', completed_at=now(), row_version=row_version+1 WHERE id=%s", [op])
        c.commit()
    for sql in ("UPDATE operations.operations SET status='RUNNING', completed_at=NULL, row_version=row_version+1 WHERE id=%s",
                "UPDATE operations.operations SET progress_version=progress_version+1, row_version=row_version+1 WHERE id=%s"):
        with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
            c.execute(sql, [op])


def test_task_requires_an_open_operation_of_the_same_project(seeded: Pg):
    with seeded.connect() as c:
        epic = new_epic(c, ORG_A, PRJ_A1)
        open_op, other_prj_op = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A2)
        done_op = new_op(c, ORG_A, PRJ_A1, status="SUCCEEDED")
    with api(seeded, ORG_A, PRJ_A1) as c:
        new_task(c, ORG_A, PRJ_A1, open_op, epic)  # positive control
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.NotNullViolation):
        new_task(c, ORG_A, PRJ_A1, None, epic)
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):
        new_task(c, ORG_A, PRJ_A1, other_prj_op, epic)
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # ADR-012: no new Task inside a terminal Operation
        new_task(c, ORG_A, PRJ_A1, done_op, epic)
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # epic from another project
        new_task(c, ORG_A, PRJ_A1, open_op, new_epic(c, ORG_A, PRJ_A2))


def test_rework_after_terminal_operation_is_a_new_operation_task_chain(seeded: Pg):
    with seeded.connect() as c:
        epic = new_epic(c, ORG_A, PRJ_A1)
        op1 = new_op(c, ORG_A, PRJ_A1)
        t1 = new_task(c, ORG_A, PRJ_A1, op1, epic)
        c.execute("UPDATE operations.operations SET status='FAILED', completed_at=now(), row_version=row_version+1 WHERE id=%s", [op1])
        op2 = new_op(c, ORG_A, PRJ_A1)
        t2 = new_task(c, ORG_A, PRJ_A1, op2, epic, derived=t1)  # ADR-034 (1)
    with api(seeded, ORG_A, PRJ_A1) as c:
        assert c.execute("SELECT derived_from_task_id FROM work.tasks WHERE id=%s", [t2]).fetchone() == (t1,)
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # lineage may not cross projects
        new_task(c, ORG_A, PRJ_A2, new_op(c, ORG_A, PRJ_A2), new_epic(c, ORG_A, PRJ_A2), derived=t1)


def test_completion_policy_is_frozen_at_creation(seeded: Pg):
    """The success semantics of a running Operation cannot be changed retroactively (security review LOW-2)."""
    with seeded.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
    for assignment in ("completion_policy_snapshot = '{\"mode\": \"any\"}'::jsonb", "completion_policy_version = 'other'"):
        with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
            c.execute(f"UPDATE operations.operations SET {assignment}, row_version = row_version + 1 WHERE id = %s", [op])
    with api(seeded, ORG_A, PRJ_A1) as c:  # control: the lifecycle columns are still writable
        assert c.execute("UPDATE operations.operations SET status = 'QUEUED', row_version = row_version + 1 WHERE id = %s", [op]).rowcount == 1


def test_task_identity_and_operation_binding_are_immutable_and_versioned(seeded: Pg):
    with seeded.connect() as c:
        epic = new_epic(c, ORG_A, PRJ_A1)
        op, op2 = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A1)
        t = new_task(c, ORG_A, PRJ_A1, op, epic)
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
        c.execute("UPDATE work.tasks SET operation_id=%s, row_version=row_version+1 WHERE id=%s", [op2, t])
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):
        c.execute("UPDATE work.tasks SET title='lww' WHERE id=%s", [t])
    with api(seeded, ORG_A, PRJ_A1) as c:
        assert c.execute("UPDATE work.tasks SET title='ok', row_version=row_version+1 WHERE id=%s", [t]).rowcount == 1


def test_task_dependencies_reject_self_cross_project_and_duplicates(seeded: Pg):
    with seeded.connect() as c:
        epic, e2 = new_epic(c, ORG_A, PRJ_A1), new_epic(c, ORG_A, PRJ_A2)
        op1, op2 = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A2)
        a, b, other = new_task(c, ORG_A, PRJ_A1, op1, epic), new_task(c, ORG_A, PRJ_A1, op1, epic), new_task(c, ORG_A, PRJ_A2, op2, e2)
    ins = "INSERT INTO work.task_dependencies (id, organization_id, project_id, task_id, depends_on_task_id) VALUES (%s,%s,%s,%s,%s)"
    with api(seeded, ORG_A, PRJ_A1) as c:
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, a, b])
        c.commit()
    for pair, exc in (((a, a), errors.CheckViolation), ((a, other), errors.ForeignKeyViolation), ((a, b), errors.UniqueViolation)):
        with seeded.connect() as c, pytest.raises(exc):
            c.execute(ins, [uuid4(), ORG_A, PRJ_A1, *pair])


def test_events_are_append_only_for_everyone_including_the_owner_path(seeded: Pg):
    with api(seeded, ORG_A, PRJ_A1) as c:
        op = new_op(c, ORG_A, PRJ_A1)
        assert allocate_and_append(c, op) == 1
        c.commit()
    with api(seeded, ORG_A, PRJ_A1) as c:
        for sql in ("UPDATE operations.operation_events SET reason_code='x'", "DELETE FROM operations.operation_events", "TRUNCATE operations.operation_events"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()
            c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
    with seeded.connect() as c:  # superuser passes privilege checks: the trigger must still refuse (defence in depth)
        for sql in ("UPDATE operations.operation_events SET reason_code='x'", "DELETE FROM operations.operation_events", "TRUNCATE operations.operation_events"):
            with pytest.raises(errors.IntegrityConstraintViolation):
                c.execute(sql)


def test_event_sequence_must_be_contiguous_and_match_last_event_sequence(seeded: Pg):
    with seeded.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
    with api(seeded, ORG_A, PRJ_A1) as c:  # two events in one transaction: fine
        assert (allocate_and_append(c, op), allocate_and_append(c, op)) == (1, 2)
        c.commit()
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # counter bumped, no event written
        c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 WHERE id=%s", [op])
        c.commit()
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # a gap: event 4 while the counter says 3
        c.execute("UPDATE operations.operations SET last_event_sequence = 3, row_version = row_version + 1 WHERE id=%s", [op])
        c.execute(event_sql(4), [uuid4(), op, uuid4()])
        c.commit()
    with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.UniqueViolation):  # duplicate sequence
        c.execute(event_sql(2), [uuid4(), op, uuid4()])
    with seeded.connect() as c:
        assert c.execute("SELECT last_event_sequence, (SELECT count(*) FROM operations.operation_events WHERE operation_id=%s) "
                         "FROM operations.operations WHERE id=%s", [op, op]).fetchone() == (2, 2)


def test_persist_012_concurrent_sequence_allocation_has_no_duplicates_or_gaps(seeded: Pg):
    with seeded.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
    workers, per_worker, errs, got = 8, 5, [], []

    def work() -> None:
        try:
            for _ in range(per_worker):
                with api(seeded, ORG_A, PRJ_A1) as c:
                    got.append(allocate_and_append(c, op))
                    c.commit()
        except Exception as e:  # noqa: BLE001 - surfaced by the assertion below
            errs.append(e)

    threads = [threading.Thread(target=work) for _ in range(workers)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errs, errs
    assert sorted(got) == list(range(1, workers * per_worker + 1))
    with seeded.connect() as c:
        assert c.execute("SELECT last_event_sequence, row_version FROM operations.operations WHERE id=%s", [op]).fetchone() == (40, 41)


def test_atomicity_rollback_leaves_neither_projection_nor_event(seeded: Pg):
    with seeded.connect() as c:
        op = new_op(c, ORG_A, PRJ_A1)
    with api(seeded, ORG_A, PRJ_A1) as c:
        allocate_and_append(c, op)
        c.rollback()
    with seeded.connect() as c:
        assert c.execute("SELECT last_event_sequence, row_version, (SELECT count(*) FROM operations.operation_events WHERE operation_id=%s) "
                         "FROM operations.operations WHERE id=%s", [op, op]).fetchone() == (0, 1, 0)


@pytest.mark.parametrize("role", ["ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor"])
def test_non_api_roles_have_no_access_to_operation_and_work_tables(seeded: Pg, role: str):
    for table in ("operations.operations", "operations.operation_events", "work.tasks", "work.epics", "work.task_dependencies"):
        with seeded.connect(role) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(f"SELECT 1 FROM {table} LIMIT 1")  # noqa: S608


def test_api_cannot_delete_truncate_or_alter_these_tables(seeded: Pg):
    for sql in ("DELETE FROM operations.operations", "TRUNCATE work.tasks", "DELETE FROM work.epics", "DROP TABLE work.tasks",
                "UPDATE operations.operation_types SET code='X'"):
        with api(seeded, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(sql)
