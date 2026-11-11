# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S05 slice D: audit (aggregate_types, outbox_events, inbox_messages, audit_events) + platform.idempotency_records (ADR-016, ADR-024, ADR-034, ADR-053).

Runtime principals are exercised through their real login roles: api (tenant context, INSERT-only on outbox/audit), outbox dispatcher and event consumer
(cross-tenant by design, narrow column grants), auditor (read-only, organization context).
"""
import threading
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from .conftest import Pg, run_audit
from .test_operations_work_schema import ORG_A, ORG_B, PRJ_A1, PRJ_A2, PRJ_B, api, event_sql, new_op

pytestmark = pytest.mark.postgres
H = b"\x04" * 32
KEY = b"\x05" * 32


def outbox_sql(status: str = "PENDING", dest: str = "internal") -> str:
    extra = ", lease_owner, lease_until" if status == "IN_FLIGHT" else ""
    extra_v = ", 'disp-1', now() + interval '30 seconds'" if status == "IN_FLIGHT" else ""
    # the envelope is derived from the same six parameters, so the row describes its own event and tenant (assert_outbox_matches_event binds them)
    return ("INSERT INTO audit.outbox_events (id, organization_id, project_id, event_id, destination, aggregate_type, aggregate_id, aggregate_sequence, event_type, "
            f"schema_version, envelope, status{extra}) SELECT p.id, p.org, p.prj, p.event_id, '{dest}', 'OPERATION', p.op, p.seq, 'operation.accepted', 1, "
            "jsonb_build_object('specversion', '1.0', 'id', p.event_id::text, 'type', 'com.aires.operation.accepted.v1', 'source', 'urn:aires:operations', "
            "'subject', 'operations/' || p.op::text, 'dataschema', 'urn:aires:schemas:com.aires.operation.accepted.v1', 'data', jsonb_build_object("
            "'eventId', p.event_id::text, 'organizationId', p.org::text, 'projectId', p.prj::text, 'aggregateType', 'OPERATION', 'aggregateId', p.op::text, "
            f"'operationId', p.op::text, 'aggregateSequence', p.seq)), '{status}'{extra_v} "
            "FROM (VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::bigint)) AS p(id, org, prj, event_id, op, seq)")


def append_event_with_outbox(c: psycopg.Connection[Any], org: UUID, prj: UUID, op: UUID, dest: str = "internal") -> tuple[UUID, int]:
    """The repository contract of TX-01: projection bump + event + outbox row in ONE transaction."""
    seq = c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 WHERE id=%s RETURNING last_event_sequence",
                    [op]).fetchone()[0]  # type: ignore[index]
    event_id = uuid4()
    c.execute(event_sql(seq), [event_id, op, uuid4()])
    c.execute(outbox_sql(dest=dest), [uuid4(), org, prj, event_id, op, seq])
    return event_id, int(seq)


def audit_sql(org: UUID, prj: UUID | None) -> tuple[str, list[Any]]:
    return ("INSERT INTO audit.audit_events (id, organization_id, project_id, occurred_at, actor_type, actor_id, action, object_type, object_id, result, correlation_id) "
            "VALUES (%s,%s,%s,now(),'USER',%s,'REQUIREMENT_APPROVE','REQUIREMENT',%s,'DENIED',%s)"), [uuid4(), org, prj, uuid4(), uuid4(), uuid4()]


def idem_sql() -> str:
    return ("INSERT INTO platform.idempotency_records (id, organization_id, project_id, scope_type, scope_id, key_digest, key_id, request_fingerprint, status, expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,'k1',%s,'IN_PROGRESS', now() + interval '1 day')")


def role(pg: Pg, name: str, org: UUID | None = None) -> psycopg.Connection[Any]:
    conn = pg.connect(name, autocommit=False)
    if org is not None:
        conn.execute("SELECT set_config('app.organization_id', %s, true)", [str(org)])
    return conn


@pytest.fixture
def world(migrated: Pg) -> tuple[Pg, dict[str, UUID]]:
    ids: dict[str, UUID] = {}
    with migrated.connect() as c:
        for org in (ORG_A, ORG_B):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        for prj, org in ((PRJ_A1, ORG_A), (PRJ_A2, ORG_A), (PRJ_B, ORG_B)):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
        ids["op"], ids["op_b"] = new_op(c, ORG_A, PRJ_A1), new_op(c, ORG_B, PRJ_B)
    return migrated, ids


def test_audits_clean_and_tables_exist(world):
    pg, _ = world
    with pg.connect() as c:
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == [] and run_audit(c, "postflight.sql") == []
        tables = {r[0] for r in c.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('audit','platform') AND tablename <> 'alembic_version'")}
        assert c.execute("SELECT array_agg(code ORDER BY code) FROM audit.aggregate_types").fetchone() == (["OPERATION", "WORKER_RUN"],)
    assert tables == {"audit.aggregate_types", "audit.outbox_events", "audit.inbox_messages", "audit.audit_events", "platform.idempotency_records"}


def test_cross_tenant_policies_are_an_explicit_allowlist_and_never_for_api(world):
    pg, _ = world
    with pg.connect() as c:
        rows = c.execute("""SELECT c.relname || '/' || p.polname, (SELECT array_agg(pg_get_userbyid(r) ORDER BY 1) FROM unnest(p.polroles) r)
                              FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
                             WHERE pg_get_expr(p.polqual, p.polrelid) = 'true' OR pg_get_expr(p.polwithcheck, p.polrelid) = 'true'""").fetchall()
        assert rows, "the cross-tenant policies of ADR-034 (4) must exist"
        for name, roles in rows:
            assert set(roles) <= {"ai_res_outbox_group", "ai_res_consumer_group"}, (name, roles)
        c.execute("SET ROLE ai_res_owner")
        c.execute("CREATE POLICY p_sabotage ON audit.outbox_events FOR SELECT TO ai_res_api_group USING (true)")
        c.execute("RESET ROLE")
        assert ("rls_policy_always_true", "audit.outbox_events / p_sabotage") in run_audit(c, "rls_coverage.sql")


def test_api_appends_outbox_and_audit_in_scope_but_cannot_read_update_or_delete_them(world):
    pg, ids = world
    with api(pg, ORG_A, PRJ_A1) as c:
        append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
        sql, params = audit_sql(ORG_A, PRJ_A1)
        c.execute(sql, params)
        sql, params = audit_sql(ORG_A, None)  # organization-level action
        c.execute(sql, params)
        c.commit()
    for table in ("audit.outbox_events", "audit.audit_events"):
        with api(pg, ORG_A, PRJ_A1) as c:
            for stmt in (f"SELECT 1 FROM {table}", f"UPDATE {table} SET created_at = now()" if table.endswith("outbox_events") else f"UPDATE {table} SET result = 'X'",
                         f"DELETE FROM {table}", f"TRUNCATE {table}"):
                with pytest.raises(errors.InsufficientPrivilege):  # THR-015: the API can never rewrite or erase audit/outbox
                    c.execute(stmt)
                c.rollback()
                c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
    with pg.connect() as c:
        assert c.execute("SELECT count(*) FROM audit.outbox_events").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM audit.audit_events").fetchone() == (2,)


def test_api_cannot_write_outbox_or_audit_for_another_scope(world):
    pg, ids = world
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute(outbox_sql(), [uuid4(), ORG_B, PRJ_B, uuid4(), ids["op_b"], 1])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute(outbox_sql(), [uuid4(), ORG_A, PRJ_A2, uuid4(), ids["op"], 1])  # sibling project
    for org, prj in ((ORG_B, PRJ_B), (ORG_A, PRJ_A2)):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
            sql, params = audit_sql(org, prj)
            c.execute(sql, params)
    with api(pg, ORG_A, None) as c, pytest.raises(errors.InsufficientPrivilege):  # no tenant context at all
        sql, params = audit_sql(ORG_A, PRJ_A1)
        c.execute(sql, params)


def test_outbox_row_must_describe_a_real_event_of_its_aggregate(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        event_id, seq = append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
    bad = {  # each variant references something that is not the committed event
        "unknown event": (uuid4(), ids["op"], seq),
        "wrong sequence": (event_id, ids["op"], seq + 1),
        "other aggregate": (event_id, ids["op_b"], seq),
    }
    for eid, agg, sq in bad.values():
        with pg.connect() as c, pytest.raises(errors.IntegrityConstraintViolation, match="outbox"), c.transaction():
            c.execute(outbox_sql(dest="second"), [uuid4(), ORG_A, PRJ_A1, eid, agg, sq])


def test_outbox_uniqueness_and_aggregate_type_registry(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        event_id, seq = append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
        with pytest.raises(errors.UniqueViolation), c.transaction():  # same event, same destination
            c.execute(outbox_sql(), [uuid4(), ORG_A, PRJ_A1, event_id, ids["op"], seq])
        c.execute(outbox_sql(dest="other"), [uuid4(), ORG_A, PRJ_A1, event_id, ids["op"], seq])  # another destination is a separate row
        with pytest.raises(errors.ForeignKeyViolation), c.transaction():
            c.execute(outbox_sql(dest="third").replace("'OPERATION'", "'NO_SUCH_AGGREGATE'"), [uuid4(), ORG_A, PRJ_A1, event_id, ids["op"], seq + 5])


def test_outbox_envelope_must_describe_its_own_event_and_tenant(world):
    """A forged envelope is routed on by consumers and SSE: the deferred trigger binds it to the row's event/tenant columns (security review MEDIUM-2)."""
    pg, ids = world
    forgeries = {
        "tenant": ("'organizationId', p.org::text", f"'organizationId', '{ORG_B}'"),
        "project": ("'projectId', p.prj::text", f"'projectId', '{PRJ_B}'"),
        "event id": ("'eventId', p.event_id::text", f"'eventId', '{uuid4()}'"),
        "type": ("'type', 'com.aires.operation.accepted.v1'", "'type', 'com.aires.operation.failed.v1'"),
        "sequence": ("'aggregateSequence', p.seq", "'aggregateSequence', p.seq + 1"),
        "aggregate": ("'aggregateId', p.op::text", f"'aggregateId', '{uuid4()}'"),
        "operation": ("'operationId', p.op::text", f"'operationId', '{uuid4()}'"),  # verification pass (database + security): routing attributes are bound too
        "source": ("'source', 'urn:aires:operations'", "'source', 'urn:evil'"),
        "subject": ("'subject', 'operations/' || p.op::text", f"'subject', 'operations/{uuid4()}'"),
        "dataschema": ("'dataschema', 'urn:aires:schemas:com.aires.operation.accepted.v1'", "'dataschema', 'urn:aires:schemas:other'")}
    for name, (genuine, forged) in forgeries.items():
        sql = outbox_sql()
        assert genuine in sql, name
        with pytest.raises(errors.IntegrityConstraintViolation, match="envelope"), api(pg, ORG_A, PRJ_A1) as c:  # raised by the deferred check at COMMIT
            seq = c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 WHERE id=%s "
                            "RETURNING last_event_sequence", [ids["op"]]).fetchone()[0]  # type: ignore[index]
            event_id = uuid4()
            c.execute(event_sql(seq), [event_id, ids["op"], uuid4()])
            c.execute(sql.replace(genuine, forged), [uuid4(), ORG_A, PRJ_A1, event_id, ids["op"], seq])
    sql = outbox_sql()
    for column, genuine, forged in (("event type", "'OPERATION', p.op, p.seq, 'operation.accepted', 1,", "'OPERATION', p.op, p.seq, 'operation.cancelled', 1,"),
                                    ("schema version", "'OPERATION', p.op, p.seq, 'operation.accepted', 1,", "'OPERATION', p.op, p.seq, 'operation.accepted', 2,")):
        assert genuine in sql, column
        with pytest.raises(errors.IntegrityConstraintViolation, match="does not describe an event"), api(pg, ORG_A, PRJ_A1) as c:  # the row's own columns must equal the event's
            seq = c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 WHERE id=%s "
                            "RETURNING last_event_sequence", [ids["op"]]).fetchone()[0]  # type: ignore[index]
            event_id = uuid4()
            c.execute(event_sql(seq), [event_id, ids["op"], uuid4()])
            c.execute(sql.replace(genuine, forged), [uuid4(), ORG_A, PRJ_A1, event_id, ids["op"], seq])
    with pg.connect() as c:  # nothing of the forged attempts survived
        assert c.execute("SELECT count(*) FROM audit.outbox_events").fetchone() == (0,)


def test_projection_event_outbox_are_atomic_both_ways(world):
    pg, ids = world
    with api(pg, ORG_A, PRJ_A1) as c:  # rollback: none of the three records survive
        append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InvalidTextRepresentation):  # failure in the LAST step undoes the first two
        c.execute("UPDATE operations.operations SET last_event_sequence = last_event_sequence + 1, row_version = row_version + 1 WHERE id=%s", [ids["op"]])
        c.execute(event_sql(1), [uuid4(), ids["op"], uuid4()])
        c.execute("INSERT INTO audit.outbox_events (id, organization_id, project_id) VALUES ('not-a-uuid', %s, %s)", [ORG_A, PRJ_A1])
    with pg.connect() as c:
        assert c.execute("SELECT (SELECT last_event_sequence FROM operations.operations WHERE id=%s), (SELECT count(*) FROM operations.operation_events), "
                         "(SELECT count(*) FROM audit.outbox_events)", [ids["op"]]).fetchone() == (0, 0, 0)


def test_dispatcher_claims_rows_across_tenants_but_changes_only_delivery_columns(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
        append_event_with_outbox(c, ORG_B, PRJ_B, ids["op_b"])
    with role(pg, "ai_res_outbox_dispatcher") as c:  # no tenant context at all
        rows = c.execute("SELECT id, organization_id FROM audit.outbox_events WHERE status='PENDING' ORDER BY created_at FOR UPDATE SKIP LOCKED").fetchall()
        assert {r[1] for r in rows} == {ORG_A, ORG_B}
        assert c.execute("UPDATE audit.outbox_events SET status='IN_FLIGHT', lease_owner='d1', lease_until=now()+interval '30 seconds', attempt_count=attempt_count+1").rowcount == 2
        c.commit()
    with role(pg, "ai_res_outbox_dispatcher") as c:
        c.execute("UPDATE audit.outbox_events SET status='PUBLISHED', published_at=now(), lease_owner=NULL, lease_until=NULL")
        c.commit()
    for stmt in ("UPDATE audit.outbox_events SET envelope = '{}'::jsonb", "UPDATE audit.outbox_events SET event_id = gen_random_uuid()",
                 "UPDATE audit.outbox_events SET organization_id = gen_random_uuid()", "DELETE FROM audit.outbox_events", "TRUNCATE audit.outbox_events",
                 "INSERT INTO audit.outbox_events (id) VALUES (gen_random_uuid())", "SELECT 1 FROM operations.operation_events", "SELECT 1 FROM audit.inbox_messages"):
        with role(pg, "ai_res_outbox_dispatcher") as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(stmt)
    with pg.connect() as c:  # defence in depth for the owner path: envelope and identity are immutable even if a grant slips
        for col in ("envelope = '{}'::jsonb", "event_id = gen_random_uuid()"):
            with pytest.raises(errors.IntegrityConstraintViolation):
                c.execute(f"UPDATE audit.outbox_events SET {col}")


def test_dispatcher_lease_claims_do_not_overlap_and_state_shape_is_enforced(world):
    pg, ids = world
    with pg.connect() as c, c.transaction():
        for _ in range(4):
            append_event_with_outbox(c, ORG_A, PRJ_A1, ids["op"])
    a, b = role(pg, "ai_res_outbox_dispatcher"), role(pg, "ai_res_outbox_dispatcher")
    try:
        got_a = {r[0] for r in a.execute("SELECT id FROM audit.outbox_events WHERE status='PENDING' ORDER BY created_at LIMIT 2 FOR UPDATE SKIP LOCKED")}
        got_b = {r[0] for r in b.execute("SELECT id FROM audit.outbox_events WHERE status='PENDING' ORDER BY created_at LIMIT 2 FOR UPDATE SKIP LOCKED")}
    finally:
        a.close(), b.close()
    assert len(got_a) == len(got_b) == 2 and not got_a & got_b  # SKIP LOCKED: two dispatchers never claim the same row
    with pg.connect() as c:
        for stmt in ("UPDATE audit.outbox_events SET status='IN_FLIGHT'",  # lease required
                     "UPDATE audit.outbox_events SET status='PUBLISHED'",  # published_at required
                     "UPDATE audit.outbox_events SET status='BOGUS'", "UPDATE audit.outbox_events SET attempt_count = -1"):
            with pytest.raises(errors.CheckViolation):
                c.execute(stmt)


def test_inbox_dedupes_per_consumer_and_exposes_only_progress_columns(world):
    pg, _ = world
    ins = ("INSERT INTO audit.inbox_messages (id, consumer_name, event_id, aggregate_type, aggregate_id, aggregate_sequence, status, payload_hash) "
           "VALUES (%s,'c1',%s,'OPERATION',%s,1,'PROCESSING',%s)")
    ev, agg = uuid4(), uuid4()
    with role(pg, "ai_res_event_consumer") as c:
        c.execute(ins, [uuid4(), ev, agg, H])
        assert c.execute(ins + " ON CONFLICT (consumer_name, event_id) DO NOTHING", [uuid4(), ev, agg, H]).rowcount == 0  # duplicate delivery = successful no-op
        c.execute(ins.replace("'c1'", "'c2'"), [uuid4(), ev, agg, H])  # another consumer processes the same event independently
        assert c.execute("UPDATE audit.inbox_messages SET status='PROCESSED', processed_at=now() WHERE consumer_name='c1'").rowcount == 1
        c.commit()
    with role(pg, "ai_res_event_consumer") as c, pytest.raises(errors.UniqueViolation):
        c.execute(ins, [uuid4(), ev, agg, H])
    for stmt in ("UPDATE audit.inbox_messages SET event_id = gen_random_uuid()", "UPDATE audit.inbox_messages SET payload_hash = decode(repeat('00', 32), 'hex')",
                 "DELETE FROM audit.inbox_messages", "TRUNCATE audit.inbox_messages", "SELECT 1 FROM audit.outbox_events", "SELECT 1 FROM operations.operations"):
        with role(pg, "ai_res_event_consumer") as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute(stmt)
    with pg.connect() as c:
        with pytest.raises(errors.CheckViolation):
            c.execute("UPDATE audit.inbox_messages SET status='PROCESSED', processed_at=NULL WHERE consumer_name='c2'")
        with pytest.raises(errors.IntegrityConstraintViolation):
            c.execute("UPDATE audit.inbox_messages SET payload_hash = decode(repeat('00', 32), 'hex')")
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute("SELECT 1 FROM audit.inbox_messages")


def test_audit_events_are_immutable_for_everyone_and_readable_by_the_auditor_per_organization(world):
    pg, _ = world
    with api(pg, ORG_A, PRJ_A1) as c:
        sql, params = audit_sql(ORG_A, PRJ_A1)
        c.execute(sql, params)
        c.commit()
    with api(pg, ORG_B, PRJ_B) as c:
        sql, params = audit_sql(ORG_B, None)
        c.execute(sql, params)
        c.commit()
    with pg.connect() as c:
        for stmt in ("UPDATE audit.audit_events SET result='X'", "DELETE FROM audit.audit_events", "TRUNCATE audit.audit_events"):
            with pytest.raises(errors.IntegrityConstraintViolation):
                c.execute(stmt)
    with role(pg, "ai_res_auditor", ORG_A) as c:
        assert [r[0] for r in c.execute("SELECT organization_id FROM audit.audit_events")] == [ORG_A]
        for stmt in ("UPDATE audit.audit_events SET result='X'", "DELETE FROM audit.audit_events", "INSERT INTO audit.audit_events (id) VALUES (gen_random_uuid())"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(stmt)
            c.rollback()
            c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
    with role(pg, "ai_res_auditor") as c:  # default deny without the organization context
        assert c.execute("SELECT count(*) FROM audit.audit_events").fetchone() == (0,)
    with role(pg, "ai_res_auditor", ORG_A) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute("SELECT 1 FROM audit.outbox_events")


def test_idempotency_records_are_scoped_frozen_when_finished_and_never_leak_keys(world):
    pg, ids = world
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute(idem_sql(), [uuid4(), ORG_A, PRJ_A1, "PROJECT", PRJ_A1, KEY, H])
        c.commit()
    cols = {r[0] for r in pg.connect().execute("SELECT column_name FROM information_schema.columns WHERE table_schema='platform' AND table_name='idempotency_records'")}
    assert {"key_digest", "key_id"} <= cols and not ({"idempotency_key", "raw_key", "key"} & cols)  # ADR-024: HMAC digest + key id, never the client key
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.UniqueViolation):  # same scope + same key: second request cannot create another record
        c.execute(idem_sql(), [uuid4(), ORG_A, PRJ_A1, "PROJECT", PRJ_A1, KEY, H])
    with api(pg, ORG_A, PRJ_A1) as c:  # a different scope may reuse the same digest
        c.execute(idem_sql(), [uuid4(), ORG_A, PRJ_A1, "PROJECT", ids["op"], KEY, H])
    with api(pg, ORG_B, PRJ_B) as c:  # foreign tenant: invisible, and its own insert with the same digest is independent (no existence oracle)
        assert c.execute("SELECT count(*) FROM platform.idempotency_records").fetchone() == (0,)
        c.execute(idem_sql(), [uuid4(), ORG_B, PRJ_B, "PROJECT", PRJ_A1, KEY, H])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute(idem_sql(), [uuid4(), ORG_B, PRJ_B, "PROJECT", PRJ_B, KEY, H])
    with api(pg, ORG_A, None) as c:  # project-scoped record is invisible at organization-only context
        assert c.execute("SELECT count(*) FROM platform.idempotency_records").fetchone() == (0,)
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute("UPDATE platform.idempotency_records SET status='COMPLETED', response_status=202, resource_type='OPERATION', resource_id=%s, completed_at=now() "
                         "WHERE scope_id=%s AND scope_type='PROJECT'", [ids["op"], PRJ_A1]).rowcount == 1
        c.commit()
    for stmt in ("UPDATE platform.idempotency_records SET status='IN_PROGRESS', completed_at=NULL", "UPDATE platform.idempotency_records SET response_status=500"):
        with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # a finished record is replayed, never rewritten
            c.execute(stmt + " WHERE scope_id = %s", [PRJ_A1])
    with api(pg, ORG_A, PRJ_A1) as c, pytest.raises(errors.IntegrityConstraintViolation):  # the fingerprint binds the key to its first request
        c.execute("UPDATE platform.idempotency_records SET request_fingerprint = %s WHERE scope_id = %s", [b"\x09" * 32, ids["op"]])
    with api(pg, ORG_A, PRJ_A1) as c:
        for stmt in ("DELETE FROM platform.idempotency_records", "TRUNCATE platform.idempotency_records"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(stmt)
            c.rollback()
            c.execute("SELECT set_config('app.organization_id', %s, true)", [str(ORG_A)])
    with pg.connect() as c:
        for bad, exc in ((b"short", errors.CheckViolation),):
            with pytest.raises(exc):
                c.execute(idem_sql(), [uuid4(), ORG_A, PRJ_A1, "PROJECT", uuid4(), bad, H])
        with pytest.raises(errors.CheckViolation):
            c.execute(idem_sql().replace("'IN_PROGRESS'", "'COMPLETED'"), [uuid4(), ORG_A, PRJ_A1, "PROJECT", uuid4(), KEY, H])  # COMPLETED needs completed_at


def test_persist_013_concurrent_same_key_creates_exactly_one_record(world):
    pg, _ = world
    scope, wins, losses, errs = uuid4(), [], [], []

    def attempt() -> None:
        try:
            with api(pg, ORG_A, PRJ_A1) as c:
                try:
                    c.execute(idem_sql(), [uuid4(), ORG_A, PRJ_A1, "PROJECT", scope, KEY, H])
                    c.commit()
                    wins.append(1)
                except errors.UniqueViolation:
                    c.rollback()
                    losses.append(1)
        except Exception as e:  # noqa: BLE001 - surfaced below
            errs.append(e)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errs, errs
    assert (len(wins), len(losses)) == (1, 9)
    with pg.connect() as c:
        assert c.execute("SELECT count(*) FROM platform.idempotency_records WHERE scope_id=%s", [scope]).fetchone() == (1,)


def test_aggregate_type_registry_is_read_only_for_runtime(world):
    pg, _ = world
    for name in ("ai_res_api", "ai_res_outbox_dispatcher", "ai_res_event_consumer"):
        with pg.connect(name) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute("INSERT INTO audit.aggregate_types (code) VALUES ('BACKDOOR')")
