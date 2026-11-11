# ruff: noqa: E501, S608, SIM117  -- fixed literal SQL in test fixtures
"""S06: domain content schema (requirements, sources, artifacts, governance, context, decisions, traceability, rules) under real runtime roles.

Seeding runs as the bootstrap superuser in explicit transactions (RLS/privileges are bypassed, FKs/triggers/deferred checks still apply); behaviour is
asserted as `ai_res_api` with transaction-local tenant context, exactly like production (ADR-056..059).
"""
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from psycopg import errors

from .conftest import Pg, alembic_config, run_audit
from .test_operations_work_schema import ORG_A, ORG_B, PRJ_A1, PRJ_A2, PRJ_B, api

pytestmark = pytest.mark.postgres
SHA = b"\x11" * 32
SHA2 = b"\x22" * 32
BAD = (psycopg.IntegrityError, errors.InsufficientPrivilege)


class Ids:
    def __init__(self) -> None:
        self.user, self.req, self.rv, self.src, self.sv, self.art, self.av = (uuid4() for _ in range(7))


def tx(pg: Pg) -> psycopg.Connection[Any]:
    return pg.connect(autocommit=False)


def seed_tenants(c: psycopg.Connection[Any]) -> UUID:
    user = uuid4()
    for org in (ORG_A, ORG_B):
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
    for prj, org in ((PRJ_A1, ORG_A), (PRJ_A2, ORG_A), (PRJ_B, ORG_B)):
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
    c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'u@example.test','u@example.test','u')", [user, ORG_A])
    return user


def add_requirement(c: psycopg.Connection[Any], org: UUID, prj: UUID, n: int = 1, status: str = "CANDIDATE", rtype: str = "FR") -> tuple[UUID, UUID]:
    rid, vid = uuid4(), uuid4()
    c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number, current_version_id, last_version_number) VALUES (%s,%s,%s,%s,%s,1)", [rid, org, prj, n, vid])
    c.execute("INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, statement, author_type, status) "
              "VALUES (%s,%s,%s,%s,1,%s,'The system shall X','USER',%s)", [vid, org, prj, rid, rtype, status])
    return rid, vid


@pytest.fixture
def world(migrated: Pg) -> tuple[Pg, UUID, UUID, UUID]:
    c = tx(migrated)
    user = seed_tenants(c)
    req, rv = add_requirement(c, ORG_A, PRJ_A1)
    c.commit()
    c.close()
    return migrated, user, req, rv


def test_audits_clean_and_every_new_table_is_rls_forced(world):
    pg, *_ = world
    with pg.connect() as c:
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == [] and run_audit(c, "postflight.sql") == []
        missing = c.execute("""SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                                WHERE c.relkind = 'r' AND n.nspname IN ('requirements','sources','knowledge','decisions','artifacts','traceability','governance','context')
                                  AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
                                  AND n.nspname || '.' || c.relname NOT IN ('requirements.requirement_types','artifacts.artifact_types','artifacts.artifact_version_statuses',
                                       'traceability.object_types','traceability.link_types','traceability.link_type_rules')""").fetchall()
        assert missing == []


def test_requirement_version_content_is_immutable_and_never_deleted(world):
    pg, _, req, rv = world
    for sql in ("UPDATE requirements.requirement_versions SET statement = 'changed' WHERE id = %s", "UPDATE requirements.requirement_versions SET requirement_type = 'NFR' WHERE id = %s",
                "DELETE FROM requirements.requirement_versions WHERE id = %s"):
        with api(pg, ORG_A, PRJ_A1) as c:
            with pytest.raises(BAD + (errors.InsufficientPrivilege,)):
                c.execute(sql, [rv])


def test_unknown_requirement_type_is_stored_as_unknown_never_a_neighbour(world):
    pg, *_ = world
    c = tx(pg)
    rid, vid = uuid4(), uuid4()
    c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number, current_version_id, last_version_number) VALUES (%s,%s,%s,2,%s,1)", [rid, ORG_A, PRJ_A1, vid])
    ins = ("INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, declared_type_text, statement, author_type) "
           "VALUES (%s,%s,%s,%s,1,%s,%s,'s','USER')")
    with pytest.raises(errors.ForeignKeyViolation):
        c.execute(ins, [vid, ORG_A, PRJ_A1, rid, "SAFETY", None])  # not in the registry: rejected, not rewritten to the nearest known type
    c.rollback()
    c = tx(pg)
    c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number, current_version_id, last_version_number) VALUES (%s,%s,%s,2,%s,1)", [rid, ORG_A, PRJ_A1, vid])
    with pytest.raises(errors.CheckViolation):
        c.execute(ins, [vid, ORG_A, PRJ_A1, rid, "UNKNOWN", None])  # UNKNOWN must keep what was declared
    c.rollback()
    c = tx(pg)
    c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number, current_version_id, last_version_number) VALUES (%s,%s,%s,2,%s,1)", [rid, ORG_A, PRJ_A1, vid])
    c.execute(ins, [vid, ORG_A, PRJ_A1, rid, "UNKNOWN", "SAFETY"])
    c.commit()
    c.close()
    with api(pg, ORG_A, PRJ_A1) as a:
        assert a.execute("SELECT requirement_type, declared_type_text FROM requirements.requirement_versions WHERE id=%s", [vid]).fetchone() == ("UNKNOWN", "SAFETY")


def test_requirement_lifecycle_needs_human_confirmation_and_a_real_approval(world):
    pg, user, _, rv = world
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE requirements.requirement_versions SET status = 'APPROVED' WHERE id = %s", [rv])  # CANDIDATE -> APPROVED skips CONFIRMED
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE requirements.requirement_versions SET status = 'CONFIRMED' WHERE id = %s", [rv])  # no confirming human
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("UPDATE requirements.requirement_versions SET status = 'CONFIRMED', confirmed_by = %s, confirmed_at = now() WHERE id = %s", [user, rv])
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE requirements.requirement_versions SET status = 'APPROVED' WHERE id = %s", [rv])  # no approval fact for this version
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("UPDATE requirements.requirement_versions SET status = 'CONFIRMED', confirmed_by = %s, confirmed_at = now() WHERE id = %s", [user, rv])
        c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, requirement_version_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, rv, user])
        c.execute("UPDATE requirements.requirement_versions SET status = 'APPROVED' WHERE id = %s", [rv])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:  # an approval is a fact: not editable, not deletable; the approver must be a user of the organization (no worker / foreign user)
        with pytest.raises(BAD):
            c.execute("UPDATE governance.approvals SET decision = 'REJECTED' WHERE requirement_version_id = %s", [rv])
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, requirement_version_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, rv, uuid4()])


def test_version_numbers_and_current_pointer_are_consistent_at_commit(world):
    pg, _, req, _ = world
    with api(pg, ORG_A, PRJ_A1) as c:  # counter bumped without a version -> gap rejected at COMMIT
        c.execute("UPDATE requirements.requirements SET last_version_number = 2, row_version = row_version + 1 WHERE id = %s", [req])
        with pytest.raises(psycopg.IntegrityError):
            c.commit()
    other, other_v = add_requirement_commit(pg, 7)
    with api(pg, ORG_A, PRJ_A1) as c:  # the pointer may only name a version of the SAME requirement
        c.execute("UPDATE requirements.requirements SET current_version_id = %s, row_version = row_version + 1 WHERE id = %s", [other_v, req])
        with pytest.raises(errors.ForeignKeyViolation):
            c.commit()


def add_requirement_commit(pg: Pg, n: int) -> tuple[UUID, UUID]:
    c = tx(pg)
    ids = add_requirement(c, ORG_A, PRJ_A1, n)
    c.commit()
    c.close()
    return ids


def test_requirement_numbering_is_unique_per_project_and_counter_only_advances_by_one(world):
    pg, *_ = world
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO platform.display_number_counters (organization_id, project_id, counter_kind) VALUES (%s,%s,'REQUIREMENT')", [ORG_A, PRJ_A1])
        assert c.execute("UPDATE platform.display_number_counters SET last_number = last_number + 1 WHERE project_id=%s AND counter_kind='REQUIREMENT' RETURNING last_number", [PRJ_A1]).fetchone() == (1,)
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE platform.display_number_counters SET last_number = 10 WHERE project_id=%s", [PRJ_A1])
    with pytest.raises(errors.UniqueViolation):
        add_requirement_commit(pg, 1)  # display number 1 already taken in PRJ_A1


def seed_source(pg: Pg, *, verified: bool = True, sha: bytes = SHA) -> tuple[UUID, UUID, UUID]:
    src, up = uuid4(), uuid4()
    c = tx(pg)
    c.execute("INSERT INTO sources.sources (id, organization_id, project_id, source_kind, title) VALUES (%s,%s,%s,'FILE','spec')", [src, ORG_A, PRJ_A1])
    c.execute("INSERT INTO sources.uploads (id, organization_id, project_id, source_id, object_key, declared_media_type, declared_size_bytes, declared_sha256, expires_at) "
              "VALUES (%s,%s,%s,%s,%s,'text/plain',5,%s, now() + interval '1 hour')", [up, ORG_A, PRJ_A1, src, f"k/{up}", SHA])
    if verified:
        c.execute("UPDATE sources.uploads SET status='UPLOADED', row_version=2 WHERE id=%s", [up])
        c.execute("UPDATE sources.uploads SET status='VERIFIED', actual_size_bytes=5, verified_sha256=%s, finalized_at=now(), row_version=3 WHERE id=%s", [SHA, up])
    c.commit()
    c.close()
    return src, up, uuid4()


def add_source_version(pg: Pg, src: UUID, up: UUID | None, sha: bytes, n: int = 1) -> None:
    c = tx(pg)
    vid = uuid4()
    key = f"k/{up}" if up else None
    c.execute("INSERT INTO sources.source_versions (id, organization_id, project_id, source_id, version_number, upload_id, media_type, size_bytes, checksum_sha256, object_key, provenance, received_at) "
              "VALUES (%s,%s,%s,%s,%s,%s,'text/plain',5,%s,%s,'{}'::jsonb, now())", [vid, ORG_A, PRJ_A1, src, n, up, sha, key])
    c.execute("UPDATE sources.sources SET last_version_number=%s, current_version_id=%s, row_version=row_version+1 WHERE id=%s", [n, vid, src])
    c.commit()
    c.close()


def test_source_version_needs_a_verified_matching_upload_and_is_deduplicated_by_checksum(world):
    pg, *_ = world
    src, up, _ = seed_source(pg, verified=False)
    with pytest.raises(psycopg.IntegrityError):
        add_source_version(pg, src, up, SHA)  # upload still PENDING: checksum not verified
    src, up, _ = seed_source(pg)
    with pytest.raises(psycopg.IntegrityError):
        add_source_version(pg, src, up, SHA2)  # checksum differs from the verified upload
    add_source_version(pg, src, up, SHA)
    with pytest.raises(errors.UniqueViolation):
        add_source_version(pg, src, None, SHA, n=2) if False else dup_ingest(pg, src)  # duplicate ingestion: same checksum -> no second SourceVersion
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(BAD):
            c.execute("UPDATE sources.source_versions SET media_type = 'x/y' WHERE source_id = %s", [src])


def dup_ingest(pg: Pg, src: UUID) -> None:
    c = tx(pg)
    c.execute("INSERT INTO sources.source_versions (id, organization_id, project_id, source_id, version_number, media_type, size_bytes, checksum_sha256, external_ref, provenance, received_at) "
              "VALUES (%s,%s,%s,%s,2,'text/plain',5,%s,'{\"url\":\"u\"}'::jsonb,'{}'::jsonb, now())", [uuid4(), ORG_A, PRJ_A1, src, SHA])


def test_extraction_record_is_frozen_when_finished_and_a_parser_change_is_a_new_record(world):
    pg, *_ = world
    src, up, _ = seed_source(pg)
    add_source_version(pg, src, up, SHA)
    with api(pg, ORG_A, PRJ_A1) as c:
        sv = c.execute("SELECT current_version_id FROM sources.sources WHERE id=%s", [src]).fetchone()[0]  # type: ignore[index]
        ins = ("INSERT INTO knowledge.extraction_records (id, organization_id, project_id, source_version_id, pipeline_name, pipeline_version, parser_version) VALUES (%s,%s,%s,%s,'p','1',%s)")
        e1 = uuid4()
        c.execute(ins, [e1, ORG_A, PRJ_A1, sv, "parser-1"])
        c.execute("UPDATE knowledge.extraction_records SET status='SUCCEEDED', completed_at=now() WHERE id=%s", [e1])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE knowledge.extraction_records SET error_code='X' WHERE id=%s", [e1])  # finished record is not mutated
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, sv, "parser-2"])  # parser version change -> new record
        assert c.execute("SELECT count(*) FROM knowledge.extraction_records WHERE source_version_id=%s", [sv]).fetchone() == (2,)


def seed_artifact_version(pg: Pg, status: str = "READY_FOR_REVIEW") -> tuple[UUID, UUID]:
    art, av = uuid4(), uuid4()
    c = tx(pg)
    c.execute("INSERT INTO artifacts.artifacts (id, organization_id, project_id, artifact_type, source_of_truth_mode, title, current_version_id, last_version_number) VALUES (%s,%s,%s,'OPENAPI','NATIVE_SPEC','api',%s,1)", [art, ORG_A, PRJ_A1, av])
    c.execute("INSERT INTO artifacts.artifact_versions (id, organization_id, project_id, artifact_id, version_number, schema_version, content_ref, content_checksum, provenance, author_type, status) "
              "VALUES (%s,%s,%s,%s,1,'1','{\"objectKey\":\"k\"}'::jsonb,%s,'{}'::jsonb,'WORKER_RUN','DRAFT')", [av, ORG_A, PRJ_A1, art, SHA])
    if status != "DRAFT":  # a version is born DRAFT and earns every later status through a legal transition
        c.execute("UPDATE artifacts.artifact_versions SET status=%s WHERE id=%s", [status, av])
    c.commit()
    c.close()
    return art, av


def test_artifact_validation_review_approval_publication_are_separate_facts(world):
    pg, user, *_ = world
    _, av = seed_artifact_version(pg)
    with api(pg, ORG_A, PRJ_A1) as c:  # a passing validation report does not approve
        c.execute("INSERT INTO artifacts.validation_reports (id, organization_id, project_id, artifact_version_id, validators, status, validated_at, produced_by_type) VALUES (%s,%s,%s,%s,'[{\"name\":\"lint\",\"version\":\"1\"}]'::jsonb,'PASSED',now(),'SYSTEM')", [uuid4(), ORG_A, PRJ_A1, av])
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE artifacts.artifact_versions SET status='APPROVED' WHERE id=%s", [av])
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:  # nor does an approval publish
        c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, artifact_version_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, av, user])
        c.execute("UPDATE artifacts.artifact_versions SET status='APPROVED' WHERE id=%s", [av])
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE artifacts.artifact_versions SET status='PUBLISHED' WHERE id=%s", [av])
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, artifact_version_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, av, user])
        c.execute("UPDATE artifacts.artifact_versions SET status='APPROVED' WHERE id=%s", [av])
        c.execute("INSERT INTO artifacts.publications (id, organization_id, project_id, artifact_version_id, published_by) VALUES (%s,%s,%s,%s,%s)", [uuid4(), ORG_A, PRJ_A1, av, user])
        c.execute("UPDATE artifacts.artifact_versions SET status='PUBLISHED' WHERE id=%s", [av])
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE artifacts.artifact_versions SET content_checksum=%s WHERE id=%s", [SHA2, av])  # publication never changes content
        c.rollback()
    _, draft = seed_artifact_version(pg, "DRAFT")
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):
            c.execute("INSERT INTO artifacts.publications (id, organization_id, project_id, artifact_version_id, published_by) VALUES (%s,%s,%s,%s,%s)", [uuid4(), ORG_A, PRJ_A1, draft, user])


def approved_requirement(pg: Pg, user: UUID, n: int) -> UUID:
    c = tx(pg)
    _, vid = add_requirement(c, ORG_A, PRJ_A1, n)
    c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, requirement_version_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, vid, user])
    c.execute("UPDATE requirements.requirement_versions SET status='CONFIRMED', confirmed_by=%s, confirmed_at=now() WHERE id=%s", [user, vid])
    c.execute("UPDATE requirements.requirement_versions SET status='APPROVED' WHERE id=%s", [vid])
    c.commit()
    c.close()
    return vid


def create_baseline(c: psycopg.Connection[Any], user: UUID, versions: list[UUID], declared: int | None = None) -> UUID:
    bid = uuid4()
    c.execute("INSERT INTO governance.baselines (id, organization_id, project_id, baseline_number, name, item_count, created_by) VALUES (%s,%s,%s,1,'b1',%s,%s)", [bid, ORG_A, PRJ_A1, declared or len(versions), user])
    c.execute("INSERT INTO governance.approvals (id, organization_id, project_id, baseline_id, decision, approver_user_id) VALUES (%s,%s,%s,%s,'APPROVED',%s)", [uuid4(), ORG_A, PRJ_A1, bid, user])
    for v in versions:
        c.execute("INSERT INTO governance.baseline_items (id, organization_id, project_id, baseline_id, requirement_version_id) VALUES (%s,%s,%s,%s,%s)", [uuid4(), ORG_A, PRJ_A1, bid, v])
    return bid


def event_row(c: psycopg.Connection[Any], table: str, fk: str, agg: UUID, seq: int) -> None:
    c.execute(f"INSERT INTO {table} (event_id, {fk}, aggregate_sequence, aggregate_version, event_type, schema_version, source, subject, occurred_at, correlation_id, actor_type, data) "
              "VALUES (%s,%s,%s,1,'baseline.created',1,'urn:aires:baselines','baselines/x', now(), %s, 'USER', '{}'::jsonb)", [uuid4(), agg, seq, uuid4()])


def test_baseline_is_an_immutable_complete_snapshot_of_approved_versions(world):
    pg, user, _, candidate = world
    rv = approved_requirement(pg, user, 20)
    with api(pg, ORG_A, PRJ_A1) as c:  # a CANDIDATE version cannot enter a baseline
        with pytest.raises(psycopg.IntegrityError):
            create_baseline(c, user, [candidate])
    with api(pg, ORG_A, PRJ_A1) as c:  # declared item_count must match at COMMIT (rolled back as a whole)
        create_baseline(c, user, [rv], declared=2)
        event_row(c, "governance.baseline_events", "baseline_id", c.execute("SELECT id FROM governance.baselines").fetchone()[0], 1)  # type: ignore[index]
        with pytest.raises(psycopg.IntegrityError):
            c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute("SELECT count(*) FROM governance.baselines").fetchone() == (0,)
        bid = create_baseline(c, user, [rv])
        event_row(c, "governance.baseline_events", "baseline_id", bid, 1)
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:  # after creation nothing changes: not the baseline, not its items
        for sql in ("UPDATE governance.baselines SET name = 'x' WHERE id = %s", "DELETE FROM governance.baselines WHERE id = %s", "UPDATE governance.baseline_items SET requirement_version_id = requirement_version_id WHERE baseline_id = %s",
                    "DELETE FROM governance.baseline_items WHERE baseline_id = %s"):
            with pytest.raises(BAD):
                c.execute(sql, [bid])
            c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:  # a sealed baseline takes no late items
        with pytest.raises(psycopg.IntegrityError):
            c.execute("INSERT INTO governance.baseline_items (id, organization_id, project_id, baseline_id, requirement_version_id) VALUES (%s,%s,%s,%s,%s)", [uuid4(), ORG_A, PRJ_A1, bid, rv])
    with api(pg, ORG_A, PRJ_A1) as c:  # IN_BASELINE is claimed only with a baseline item, and the approved content stays frozen
        c.execute("UPDATE requirements.requirement_versions SET status='IN_BASELINE' WHERE id=%s", [rv])
        with pytest.raises(BAD):
            c.execute("UPDATE requirements.requirement_versions SET statement='rewritten' WHERE id=%s", [rv])


def test_traceability_types_come_from_registries_and_endpoints_must_exist(world):
    pg, user, req, rv = world
    _, req2 = add_requirement_commit(pg, 30)
    ins = ("INSERT INTO traceability.traceability_links (id, organization_id, project_id, source_object_type, source_object_id, target_object_type, target_object_id, link_type, origin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'AGENT')")
    r2 = pg.connect().execute("SELECT requirement_id FROM requirements.requirement_versions WHERE id=%s", [req2]).fetchone()[0]  # type: ignore[index]
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute(ins, [uuid4(), ORG_A, PRJ_A1, "REQUIREMENT", req, "REQUIREMENT", r2, "REFINES"])
        c.commit()
    cases = [("REQUIREMENT", req, "REQUIREMENT", r2, "MADE_UP", psycopg.IntegrityError),  # link_type outside the registry
             ("MADE_UP", req, "REQUIREMENT", r2, "REFINES", psycopg.IntegrityError),  # object_type outside the registry
             ("REQUIREMENT", req, "TASK", uuid4(), "REFINES", psycopg.IntegrityError),  # pair not allowed by the registry
             ("REQUIREMENT", req, "REQUIREMENT", uuid4(), "DEPENDS_ON", psycopg.IntegrityError)]  # endpoint does not exist
    for st, sid, tt, tid, lt, exc in cases:
        with api(pg, ORG_A, PRJ_A1) as c:
            with pytest.raises(exc):
                c.execute(ins, [uuid4(), ORG_A, PRJ_A1, st, sid, tt, tid, lt])
    with api(pg, ORG_B, PRJ_B) as c:  # a foreign tenant's object is not an endpoint (and its existence is not revealed)
        with pytest.raises(psycopg.IntegrityError):
            c.execute(ins, [uuid4(), ORG_B, PRJ_B, "REQUIREMENT", req, "REQUIREMENT", r2, "REFINES"])
    with api(pg, ORG_A, PRJ_A1) as c:  # confirming needs a subject and evidence
        lid = c.execute("SELECT id FROM traceability.traceability_links LIMIT 1").fetchone()[0]  # type: ignore[index]
        with pytest.raises(errors.CheckViolation):
            c.execute("UPDATE traceability.traceability_links SET status='CONFIRMED', confirmed_by=%s, confirmed_at=now(), row_version=row_version+1 WHERE id=%s", [user, lid])


def test_decision_objects_are_separate_typed_tables(world):
    pg, user, *_ = world
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO decisions.decisions (id, organization_id, project_id, title, status, question) VALUES (%s,%s,%s,'t','OPEN','q?')", [uuid4(), ORG_A, PRJ_A1])
        c.execute("INSERT INTO decisions.risks (id, organization_id, project_id, title, status, risk_event) VALUES (%s,%s,%s,'t','IDENTIFIED','e')", [uuid4(), ORG_A, PRJ_A1])
        assert c.execute("SELECT probability, impact FROM decisions.risks").fetchone() == ("UNKNOWN", "UNKNOWN")  # no invented numeric calibration
        with pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO decisions.conflicts (id, organization_id, project_id, title, status, conflicting_refs) VALUES (%s,%s,%s,'t','OPEN','[{\"id\":1}]'::jsonb)", [uuid4(), ORG_A, PRJ_A1])
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO decisions.decisions (id, organization_id, project_id, title, status, question, approver_user_id) VALUES (%s,%s,%s,'t','OPEN','q',%s)", [uuid4(), ORG_A, PRJ_A1, uuid4()])


def test_rules_system_rules_are_read_only_and_unapproved_versions_are_not_active(world):
    pg, user, *_ = world
    sys_rule = uuid4()
    with pg.connect() as c:
        c.execute("INSERT INTO governance.rules (id, level, rule_key, title) VALUES (%s,'SYSTEM','sys.no-weaken','s')", [sys_rule])
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute("SELECT count(*) FROM governance.rules WHERE id=%s", [sys_rule]).fetchone() == (1,)  # SYSTEM rules are visible to every tenant
        with pytest.raises(BAD):
            c.execute("INSERT INTO governance.rules (id, level, rule_key, title) VALUES (%s,'SYSTEM','x','x')", [uuid4()])  # a tenant cannot create or weaken SYSTEM rules
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute("UPDATE governance.rules SET title='weakened', row_version=row_version+1 WHERE id=%s", [sys_rule]).rowcount == 0  # RLS: the row is not updatable, nothing changes
        assert c.execute("SELECT title FROM governance.rules WHERE id=%s", [sys_rule]).fetchone() == ("s",)
    rid = uuid4()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO governance.rules (id, level, organization_id, project_id, rule_key, title) VALUES (%s,'PROJECT',%s,%s,'p.rule','p')", [rid, ORG_A, PRJ_A1])
        v1, v2 = uuid4(), uuid4()
        for v, n in ((v1, 1), (v2, 2)):
            c.execute("INSERT INTO governance.rule_versions (id, rule_id, level, organization_id, project_id, version_number, condition, action, author_type) VALUES (%s,%s,'PROJECT',%s,%s,%s,'{}'::jsonb,'{}'::jsonb,'MANAGER')", [v, rid, ORG_A, PRJ_A1, n])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):
            c.execute("UPDATE governance.rule_versions SET status='APPROVED' WHERE id=%s", [v1])  # DRAFT cannot jump to APPROVED
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("UPDATE governance.rule_versions SET status='PROPOSED' WHERE id=%s", [v1])
        with pytest.raises(errors.CheckViolation):
            c.execute("UPDATE governance.rule_versions SET status='APPROVED' WHERE id=%s", [v1])  # approval needs an approver, a time and a validity start
        c.rollback()
    with api(pg, ORG_A, PRJ_A1) as c:
        for v in (v1, v2):
            c.execute("UPDATE governance.rule_versions SET status='PROPOSED' WHERE id=%s", [v])
        c.execute("UPDATE governance.rule_versions SET status='APPROVED', approver_user_id=%s, approved_at=now(), valid_from=now() WHERE id=%s", [user, v1])
        with pytest.raises(errors.UniqueViolation):
            c.execute("UPDATE governance.rule_versions SET status='APPROVED', approver_user_id=%s, approved_at=now(), valid_from=now() WHERE id=%s", [user, v2])  # one active version per rule


def test_context_package_version_is_complete_immutable_and_sealed(world):
    pg, user, _, rv = world
    pkg, ver = uuid4(), uuid4()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO context.context_packages (id, organization_id, project_id, name, current_version_id, last_version_number) VALUES (%s,%s,%s,'ctx',%s,1)", [pkg, ORG_A, PRJ_A1, ver])
        c.execute("INSERT INTO context.context_package_versions (id, organization_id, project_id, context_package_id, version_number, item_count, content_digest) VALUES (%s,%s,%s,%s,1,2,%s)", [ver, ORG_A, PRJ_A1, pkg, SHA])
        c.execute("INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, requirement_version_id, inclusion_role) VALUES (%s,%s,%s,%s,'REQUIREMENT_VERSION',%s,'PRIMARY')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
        with pytest.raises(psycopg.IntegrityError):
            c.commit()  # declared 2 items, wrote 1
    with api(pg, ORG_A, PRJ_A1) as c:  # item kind and reference must agree (exactly one typed FK)
        c.execute("INSERT INTO context.context_packages (id, organization_id, project_id, name, current_version_id, last_version_number) VALUES (%s,%s,%s,'ctx',%s,1)", [pkg, ORG_A, PRJ_A1, ver])
        c.execute("INSERT INTO context.context_package_versions (id, organization_id, project_id, context_package_id, version_number, item_count, content_digest) VALUES (%s,%s,%s,%s,1,1,%s)", [ver, ORG_A, PRJ_A1, pkg, SHA])
        with pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, requirement_version_id, inclusion_role) VALUES (%s,%s,%s,%s,'SOURCE_VERSION',%s,'PRIMARY')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO context.context_packages (id, organization_id, project_id, name, current_version_id, last_version_number) VALUES (%s,%s,%s,'ctx',%s,1)", [pkg, ORG_A, PRJ_A1, ver])
        c.execute("INSERT INTO context.context_package_versions (id, organization_id, project_id, context_package_id, version_number, item_count, content_digest) VALUES (%s,%s,%s,%s,1,1,%s)", [ver, ORG_A, PRJ_A1, pkg, SHA])
        c.execute("INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, requirement_version_id, inclusion_role) VALUES (%s,%s,%s,%s,'REQUIREMENT_VERSION',%s,'PRIMARY')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError):  # sealed: no late item
            c.execute("INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, requirement_version_id, inclusion_role) VALUES (%s,%s,%s,%s,'REQUIREMENT_VERSION',%s,'EXTRA')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(BAD):
            c.execute("UPDATE context.context_package_versions SET content_digest=%s WHERE id=%s", [SHA2, ver])


def test_event_history_is_append_only_contiguous_and_outbox_stays_fail_closed(world):
    pg, user, req, _ = world
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("UPDATE requirements.requirements SET last_event_sequence = 1, row_version = row_version + 1 WHERE id = %s", [req])
        with pytest.raises(psycopg.IntegrityError):
            c.commit()  # counter moved without an event
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("UPDATE requirements.requirements SET last_event_sequence = 1, row_version = row_version + 1 WHERE id = %s", [req])
        event_row(c, "requirements.requirement_events", "requirement_id", req, 1)
        c.commit()
    with api(pg, ORG_A, PRJ_A1) as c:
        for sql in ("UPDATE requirements.requirement_events SET data = '{}'::jsonb WHERE requirement_id = %s", "DELETE FROM requirements.requirement_events WHERE requirement_id = %s"):
            with pytest.raises(BAD):
                c.execute(sql, [req])
            c.rollback()
    with api(pg, ORG_B, PRJ_B) as c:  # the history of another tenant's aggregate is invisible
        assert c.execute("SELECT count(*) FROM requirements.requirement_events").fetchone() == (0,)
    with api(pg, ORG_A, PRJ_A1) as c:  # outbox for the new aggregates is rejected until the envelope form is decided (OD-13)
        c.execute("UPDATE requirements.requirements SET last_event_sequence = 2, row_version = row_version + 1 WHERE id = %s", [req])
        event_row(c, "requirements.requirement_events", "requirement_id", req, 2)
        eid = c.execute("SELECT event_id FROM requirements.requirement_events WHERE aggregate_sequence = 2").fetchone()[0]  # type: ignore[index]
        c.execute("INSERT INTO audit.outbox_events (id, organization_id, project_id, event_id, destination, aggregate_type, aggregate_id, aggregate_sequence, event_type, schema_version, envelope) "
                  "VALUES (%s,%s,%s,%s,'internal','REQUIREMENT',%s,2,'requirement.version_created',1,'{}'::jsonb)", [uuid4(), ORG_A, PRJ_A1, eid, req])
        with pytest.raises(psycopg.IntegrityError):
            c.commit()


def test_rls_isolation_for_every_new_tenant_table(world):
    pg, user, req, rv = world
    _, av = seed_artifact_version(pg)
    src, up, _ = seed_source(pg)
    with pg.connect() as c:
        tables = [r[0] for r in c.execute("""SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                      WHERE c.relkind = 'r' AND c.relrowsecurity AND n.nspname IN ('requirements','sources','knowledge','decisions','artifacts','traceability','governance','context')
                        AND c.relname <> 'rules' AND c.relname <> 'rule_versions'
                        AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'project_id') ORDER BY 1""")]
        total_a = sum(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables)  # type: ignore[index]
    assert total_a >= 5 and 'governance.baseline_items' in tables
    for org, prj in ((ORG_B, PRJ_B), (ORG_A, PRJ_A2)):  # other organization; other project of the same organization
        with api(pg, org, prj) as c:
            leaked = {t: n for t in tables if (n := c.execute(f"SELECT count(*) FROM {t}").fetchone()[0])}  # type: ignore[index]
            assert leaked == {}
    with api(pg, None) as c:  # no tenant context: default deny
        assert {t for t in tables if c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]} == set()  # type: ignore[index]
    with api(pg, ORG_B, PRJ_B) as c:  # cross-tenant writes are refused, not silently dropped
        with pytest.raises(BAD):
            c.execute("INSERT INTO requirements.requirements (id, organization_id, project_id, display_number) VALUES (%s,%s,%s,99)", [uuid4(), ORG_A, PRJ_A1])
    with api(pg, ORG_A, PRJ_A2) as c:  # cross-project IDOR inside one organization: the row is invisible, the update touches nothing
        assert c.execute("UPDATE requirements.requirements SET status='ARCHIVED', row_version=row_version+1 WHERE id=%s", [req]).rowcount == 0


def test_upgrade_from_previous_revision_keeps_s06_data(empty_db: Pg, migrate_env):
    """Rows written under 0010 (before the 0011 insert-time guards, indexes and constraints) survive the upgrade; S05 data survives too."""
    org, prj, epic, user, rid, vid, src = (uuid4() for _ in range(7))
    command.upgrade(alembic_config(), "d85a3f6c1e07")  # head before the hardening revision
    with empty_db.connect(autocommit=False) as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [org])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [prj, org])
        c.execute("INSERT INTO work.epics (id, organization_id, project_id, title, status) VALUES (%s,%s,%s,'e','ACTIVE')", [epic, org, prj])
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'u@example.test','u@example.test','u')", [user, org])
        add_requirement(c, org, prj, 1)
        c.execute("INSERT INTO sources.sources (id, organization_id, project_id, source_kind, title) VALUES (%s,%s,%s,'FILE','s')", [src, org, prj])
        c.commit()
    command.upgrade(alembic_config(), "head")
    with empty_db.connect() as c:
        assert c.execute("SELECT title, row_version FROM work.epics WHERE id=%s", [epic]).fetchone() == ("e", 1)
        assert c.execute("SELECT count(*), min(display_number) FROM requirements.requirements WHERE organization_id=%s", [org]).fetchone() == (1, 1)
        assert c.execute("SELECT count(*) FROM requirements.requirement_versions WHERE organization_id=%s AND status='CANDIDATE'", [org]).fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM sources.sources WHERE id=%s", [src]).fetchone() == (1,)
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == []


def test_every_new_rls_table_has_a_tenant_bound_policy_for_api(world):
    """Non-vacuous companion of the data-based isolation test: EVERY RLS table of the S06 schemas (event tables and rules included, seeded or not) has an api policy whose
    predicate is bound to the transaction-local tenant setting, or is an allow-listed registry without any api write privilege."""
    pg, *_ = world
    with pg.connect() as c:
        rows = c.execute("""SELECT n.nspname || '.' || t.relname,
                                   coalesce(bool_or(pg_get_expr(p.polqual, p.polrelid) LIKE '%app.organization_id%' OR pg_get_expr(p.polwithcheck, p.polrelid) LIKE '%app.organization_id%'
                                                    OR pg_get_expr(p.polqual, p.polrelid) LIKE '%app.project_id%'), false)
                              FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace
                              LEFT JOIN pg_policy p ON p.polrelid = t.oid AND EXISTS (SELECT 1 FROM unnest(p.polroles) r WHERE pg_get_userbyid(r) = 'ai_res_api_group')
                             WHERE t.relkind = 'r' AND t.relrowsecurity AND n.nspname IN ('requirements','sources','knowledge','decisions','artifacts','traceability','governance','context')
                             GROUP BY 1""").fetchall()
        unbound = [name for name, bound in rows if not bound]
    assert unbound == [], unbound
    assert {"requirements.requirement_events", "sources.source_events", "artifacts.artifact_events", "governance.baseline_events", "governance.change_request_events",
            "governance.rules", "governance.rule_versions"} <= {name for name, _ in rows}


def test_rules_and_event_history_are_isolated_between_projects_and_tenants(world):
    pg, user, req, _ = world
    rid = uuid4()
    with pg.connect() as c:
        c.execute("INSERT INTO governance.rules (id, level, organization_id, project_id, rule_key, title) VALUES (%s,'PROJECT',%s,%s,'iso.rule','r')", [rid, ORG_A, PRJ_A1])
        c.execute("INSERT INTO governance.rules (id, level, organization_id, rule_key, title) VALUES (%s,'ORGANIZATION',%s,'iso.org','r')", [uuid4(), ORG_A])
    with api(pg, ORG_A, PRJ_A1) as c:
        assert c.execute("SELECT count(*) FROM governance.rules WHERE level <> 'SYSTEM'").fetchone() == (2,)  # own project rule + own organization rule
    with api(pg, ORG_A, PRJ_A2) as c:
        assert c.execute("SELECT count(*) FROM governance.rules WHERE level <> 'SYSTEM'").fetchone() == (1,)  # another project: only the organization-level rule
    with api(pg, ORG_B, PRJ_B) as c:
        assert c.execute("SELECT count(*) FROM governance.rules WHERE level <> 'SYSTEM'").fetchone() == (0,)


def test_lifecycle_facts_cannot_be_supplied_at_creation(world):
    """Review C1: every status guard also holds on INSERT (a row cannot be born APPROVED/VERIFIED/CONFIRMED/PUBLISHED with fabricated facts)."""
    pg, user, req, _ = world
    src, up, _ = seed_source(pg, verified=False)
    cases = [
        ("INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, statement, author_type, status, confirmed_by, confirmed_at) "
         "VALUES (%s,%s,%s,%s,2,'FR','s','USER','APPROVED',%s,now())", [uuid4(), ORG_A, PRJ_A1, req, user], r"must start in one of \(EXTRACTED,CANDIDATE\)"),
        ("INSERT INTO sources.uploads (id, organization_id, project_id, source_id, object_key, declared_media_type, declared_size_bytes, declared_sha256, expires_at, status, actual_size_bytes, verified_sha256, finalized_at) "
         "VALUES (%s,%s,%s,%s,%s,'t/p',5,%s, now() + interval '1 hour','VERIFIED',5,%s,now())", [uuid4(), ORG_A, PRJ_A1, src, f"k/{uuid4()}", SHA, SHA], r"must start in one of \(PENDING\)"),
    ]
    for sql, params, msg in cases:
        with api(pg, ORG_A, PRJ_A1) as c:
            with pytest.raises(psycopg.IntegrityError, match=msg):
                c.execute(sql, params)
    art, av = seed_artifact_version(pg)
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError, match=r"must start in one of \(DRAFT\)"):
            c.execute("INSERT INTO artifacts.artifact_versions (id, organization_id, project_id, artifact_id, version_number, schema_version, content_ref, content_checksum, provenance, author_type, status) "
                      "VALUES (%s,%s,%s,%s,2,'1','{}'::jsonb,%s,'{}'::jsonb,'USER','PUBLISHED')", [uuid4(), ORG_A, PRJ_A1, art, SHA])
    rid = uuid4()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO governance.rules (id, level, organization_id, project_id, rule_key, title) VALUES (%s,'PROJECT',%s,%s,'r','r')", [rid, ORG_A, PRJ_A1])
        with pytest.raises(psycopg.IntegrityError, match=r"must start in one of \(DRAFT\)"):
            c.execute("INSERT INTO governance.rule_versions (id, rule_id, level, organization_id, project_id, version_number, condition, action, author_type, status, approver_user_id, approved_at, valid_from) "
                      "VALUES (%s,%s,'PROJECT',%s,%s,1,'{}'::jsonb,'{}'::jsonb,'MANAGER','APPROVED',%s,now(),now())", [uuid4(), rid, ORG_A, PRJ_A1, user])


def test_baseline_needs_a_human_approval_and_a_gapless_chain(world):
    pg, user, *_ = world
    rv = approved_requirement(pg, user, 40)
    with api(pg, ORG_A, PRJ_A1) as c:  # baseline without its approval fact rolls back at commit
        bid = uuid4()
        c.execute("INSERT INTO governance.baselines (id, organization_id, project_id, baseline_number, name, item_count, created_by) VALUES (%s,%s,%s,1,'b',1,%s)", [bid, ORG_A, PRJ_A1, user])
        c.execute("INSERT INTO governance.baseline_items (id, organization_id, project_id, baseline_id, requirement_version_id) VALUES (%s,%s,%s,%s,%s)", [uuid4(), ORG_A, PRJ_A1, bid, rv])
        event_row(c, "governance.baseline_events", "baseline_id", bid, 1)
        with pytest.raises(psycopg.IntegrityError):
            c.commit()


def test_rule_item_of_another_tenant_or_unapproved_cannot_enter_a_context(world):
    pg, user, _, rv = world
    foreign, own = uuid4(), uuid4()
    with pg.connect() as c:
        rule, own_rule = uuid4(), uuid4()
        c.execute("INSERT INTO governance.rules (id, level, organization_id, project_id, rule_key, title) VALUES (%s,'PROJECT',%s,%s,'b.rule','b')", [rule, ORG_B, PRJ_B])
        c.execute("INSERT INTO governance.rule_versions (id, rule_id, level, organization_id, project_id, version_number, condition, action, author_type) VALUES (%s,%s,'PROJECT',%s,%s,1,'{}'::jsonb,'{}'::jsonb,'MANAGER')", [foreign, rule, ORG_B, PRJ_B])
        c.execute("INSERT INTO governance.rules (id, level, organization_id, project_id, rule_key, title) VALUES (%s,'PROJECT',%s,%s,'a.rule','a')", [own_rule, ORG_A, PRJ_A1])
        c.execute("INSERT INTO governance.rule_versions (id, rule_id, level, organization_id, project_id, version_number, condition, action, author_type) VALUES (%s,%s,'PROJECT',%s,%s,1,'{}'::jsonb,'{}'::jsonb,'MANAGER')", [own, own_rule, ORG_A, PRJ_A1])  # same tenant, still DRAFT
    pkg, ver = uuid4(), uuid4()
    with api(pg, ORG_A, PRJ_A1) as c:
        c.execute("INSERT INTO context.context_packages (id, organization_id, project_id, name, current_version_id, last_version_number) VALUES (%s,%s,%s,'ctx',%s,1)", [pkg, ORG_A, PRJ_A1, ver])
        c.execute("INSERT INTO context.context_package_versions (id, organization_id, project_id, context_package_id, version_number, item_count, content_digest) VALUES (%s,%s,%s,%s,1,2,%s)", [ver, ORG_A, PRJ_A1, pkg, SHA])
        for rule_version in (foreign, own):  # a foreign tenant's version and an unapproved own version are both refused
            c.execute("SAVEPOINT s")
            with pytest.raises(psycopg.IntegrityError):
                c.execute("INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, rule_version_id, inclusion_role) VALUES (%s,%s,%s,%s,'RULE_VERSION',%s,'POLICY')", [uuid4(), ORG_A, PRJ_A1, ver, rule_version])
            c.execute("ROLLBACK TO SAVEPOINT s")
        c.rollback()  # the package version declares items that were (rightly) refused: nothing may be committed


@pytest.mark.parametrize(("table", "extra_col", "extra_val"), [
    ("requirement_versions", "confirmed_by", "user"), ("requirement_versions", "confirmed_at", "now()"), ("uploads", "verified_sha256", "sha"),
    ("uploads", "rejection_code", "'X'"), ("uploads", "finalized_at", "now()")])
def test_each_lifecycle_fact_is_refused_at_creation_by_name(world, table, extra_col, extra_val):
    pg, user, req, _ = world
    src, up, _ = seed_source(pg, verified=False)
    val = {"user": user, "sha": SHA}.get(extra_val)
    ph = "%s" if val is not None else extra_val
    params = [] if val is None else [val]
    if table == "requirement_versions":
        sql = (f"INSERT INTO requirements.requirement_versions (id, organization_id, project_id, requirement_id, version_number, requirement_type, statement, author_type, status, {extra_col}) "
               f"VALUES (%s,%s,%s,%s,2,'FR','s','USER','CANDIDATE',{ph})")
        head = [uuid4(), ORG_A, PRJ_A1, req]
    else:
        sql = (f"INSERT INTO sources.uploads (id, organization_id, project_id, source_id, object_key, declared_media_type, declared_size_bytes, declared_sha256, expires_at, status, {extra_col}) "
               f"VALUES (%s,%s,%s,%s,%s,'t/p',5,%s, now() + interval '1 hour','PENDING',{ph})")
        head = [uuid4(), ORG_A, PRJ_A1, src, f"k/{uuid4()}", SHA]
    with api(pg, ORG_A, PRJ_A1) as c:
        with pytest.raises(psycopg.IntegrityError, match=f"{extra_col}"):
            c.execute(sql, head + params)

