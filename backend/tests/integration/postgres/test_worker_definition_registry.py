# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S14: the WorkerDefinition registry (migration 0016, ADR-102). Seeding as the superuser; behaviour asserted as `ai_res_api`, which only reads."""
from uuid import uuid4

import pytest
from psycopg import errors

from .conftest import Pg, run_audit, seed_worker_definition_version
from .test_agents_execution_schema import new_eval, new_run
from .test_operations_work_schema import ORG_A, PRJ_A1, new_epic, new_op, new_task

pytestmark = pytest.mark.postgres
ROLES = {"ELICITATION", "RESEARCH", "BUSINESS_ANALYSIS", "REQUIREMENTS", "SYSTEM_ANALYSIS", "API_INTEGRATION", "MODELING_DIAGRAM_VALIDATION",
         "QUALITY_ASSURANCE", "TRACEABILITY_CHANGE"}


def test_nine_roles_are_seeded_and_no_version_is(migrated: Pg):
    with migrated.connect() as c:
        assert {r[0] for r in c.execute("SELECT worker_role FROM agents.worker_definitions")} == ROLES
        assert c.execute("SELECT count(*) FROM agents.worker_definition_versions").fetchone() == (0,)
        assert run_audit(c, "rls_coverage.sql") == [] and run_audit(c, "grants_audit.sql") == []


def test_definition_rows_are_fixed(migrated: Pg):
    with migrated.connect() as c:
        with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
            c.execute("UPDATE agents.worker_definitions SET worker_role = 'RESEARCH' WHERE worker_role = 'ELICITATION'")
        with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
            c.execute("DELETE FROM agents.worker_definitions")
        with pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO agents.worker_definitions (id, worker_role) VALUES (%s, 'ADMIN')", [uuid4()])
        with pytest.raises(errors.UniqueViolation):
            c.execute("INSERT INTO agents.worker_definitions (id, worker_role) VALUES (%s, 'RESEARCH')", [uuid4()])


def test_version_is_immutable_except_status_and_status_moves_forward(migrated: Pg):
    with migrated.connect() as c:
        vid = seed_worker_definition_version(c, "v1")
        for column, value in (("output_schema_id", "'other'"), ("version", "'v2'"), ("acceptance_schema", "'{\"a\": 1}'::jsonb"), ("input_contract_version", "'2.0'")):
            with pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
                c.execute(f"UPDATE agents.worker_definition_versions SET {column} = {value} WHERE id = %s", [vid])
        with pytest.raises(errors.IntegrityConstraintViolation, match="never deleted"):
            c.execute("DELETE FROM agents.worker_definition_versions WHERE id = %s", [vid])
        c.execute("UPDATE agents.worker_definition_versions SET status = 'DEPRECATED' WHERE id = %s", [vid])
        c.execute("UPDATE agents.worker_definition_versions SET status = 'RETIRED' WHERE id = %s", [vid])
        for back in ("DEPRECATED", "ACTIVE"):
            with pytest.raises(errors.IntegrityConstraintViolation, match="may not go back"):
                c.execute("UPDATE agents.worker_definition_versions SET status = %s WHERE id = %s", [back, vid])
        with pytest.raises(errors.CheckViolation):
            c.execute("UPDATE agents.worker_definition_versions SET status = 'DELETED' WHERE id = %s", [vid])


def test_version_is_unique_per_definition_and_checks_hold(migrated: Pg):
    with migrated.connect() as c:
        seed_worker_definition_version(c, "v1")
        with pytest.raises(errors.UniqueViolation):
            c.execute("INSERT INTO agents.worker_definition_versions (id, worker_definition_id, version, input_contract_version, output_contract_version, output_schema_id, "
                      "output_schema_version) SELECT %s, id, 'v1', '1.1', '1.1', 's', '1' FROM agents.worker_definitions WHERE worker_role = 'REQUIREMENTS'", [uuid4()])
        assert seed_worker_definition_version(c, "v1", role="RESEARCH") != seed_worker_definition_version(c, "v1")  # same string, another role: separate row
        with pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO agents.worker_definition_versions (id, worker_definition_id, version, input_contract_version, output_contract_version, output_schema_id, "
                      "output_schema_version) SELECT %s, id, '', '1.1', '1.1', 's', '1' FROM agents.worker_definitions WHERE worker_role = 'REQUIREMENTS'", [uuid4()])


def test_runtime_role_reads_but_never_writes_the_registry(migrated: Pg):
    with migrated.connect() as c:
        vid = seed_worker_definition_version(c, "v1")
    with migrated.connect("ai_res_api") as api:
        assert api.execute("SELECT count(*) FROM agents.worker_definitions").fetchone() == (9,)
        assert api.execute("SELECT id FROM agents.worker_definition_versions").fetchone() == (vid,)
        for sql in ("INSERT INTO agents.worker_definitions (id, worker_role) VALUES (gen_random_uuid(), 'RESEARCH')",
                    "UPDATE agents.worker_definition_versions SET status = 'RETIRED'", "DELETE FROM agents.worker_definition_versions",
                    "TRUNCATE agents.worker_definitions"):
            with pytest.raises(errors.InsufficientPrivilege):
                api.execute(sql)


def test_run_and_evaluation_must_reference_an_existing_version(migrated: Pg):
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [ORG_A])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [PRJ_A1, ORG_A])
        epic = new_epic(c, ORG_A, PRJ_A1)
        op = new_op(c, ORG_A, PRJ_A1)
        task = new_task(c, ORG_A, PRJ_A1, op, epic)
        run = new_run(c, ORG_A, PRJ_A1, op, task)  # seeds and uses a real version
        with pytest.raises(errors.ForeignKeyViolation):
            new_eval(c, run, wdv=uuid4())
        c.execute("SELECT 1")  # connection stays usable (autocommit)
        with pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO agents.worker_runs (id, organization_id, project_id, operation_id, task_id, worker_definition_version_id, status, "
                      "context_package_version_id, input_contract_version, output_contract_version, attempt_number) VALUES (%s,%s,%s,%s,%s,%s,'CREATED',%s,'in','out',9)",
                      [uuid4(), ORG_A, PRJ_A1, op, task, uuid4(), uuid4()])
        used = c.execute("SELECT worker_definition_version_id FROM agents.worker_runs WHERE id = %s", [run]).fetchone()
        assert used is not None
        with pytest.raises(errors.IntegrityConstraintViolation):  # the guard trigger refuses first; ON DELETE RESTRICT is the second line behind it
            c.execute("DELETE FROM agents.worker_definition_versions WHERE id = %s", [used[0]])




def test_registry_cannot_be_truncated_even_with_cascade(migrated: Pg):
    with migrated.connect() as c:
        seed_worker_definition_version(c, "v1")
        for sql in ("TRUNCATE agents.worker_definitions CASCADE", "TRUNCATE agents.worker_definition_versions CASCADE", "TRUNCATE agents.worker_definition_versions"):
            with pytest.raises((errors.IntegrityConstraintViolation, errors.FeatureNotSupported)):
                c.execute(sql)
        assert c.execute("SELECT count(*) FROM agents.worker_definitions").fetchone() == (9,)


def test_a_version_is_born_active(migrated: Pg):
    with migrated.connect() as c:
        for status in ("DEPRECATED", "RETIRED"):
            with pytest.raises(errors.IntegrityConstraintViolation, match="created ACTIVE"):
                c.execute("INSERT INTO agents.worker_definition_versions (id, worker_definition_id, version, status, input_contract_version, output_contract_version, "
                          "output_schema_id, output_schema_version) SELECT %s, id, 'v9', %s, '1.1', '1.1', 's', '1' FROM agents.worker_definitions WHERE worker_role = 'RESEARCH'",
                          [uuid4(), status])


def test_constraint_names_fit_postgres_and_are_the_declared_ones(migrated: Pg):
    expected = {"fk_worker_definition_versions_worker_definition_id", "fk_worker_runs_worker_definition_version_id", "fk_readiness_evaluations_worker_definition_version_id"}
    with migrated.connect() as c:
        names = {r[0] for r in c.execute("SELECT conname FROM pg_constraint WHERE conname = ANY(%s)", [list(expected)])}
        assert names == expected  # stored under exactly these names: none was silently truncated
        too_long = [r[0] for r in c.execute("SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname IN ('agents','execution') "
                                            "AND length(conname) >= 63 AND conname LIKE '%worker\\_definition%'")]  # S05 names truncated earlier are G-141, not this revision
        assert too_long == []


def test_only_the_api_group_reads_the_registry(migrated: Pg):
    for role in ("ai_res_outbox_dispatcher", "ai_res_event_consumer", "ai_res_auditor"):  # the backup identity has no CONNECT at all
        with migrated.connect(role) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute("SELECT count(*) FROM agents.worker_definitions")


def test_the_database_stores_the_reference_only_capability_status_belongs_to_the_gate(migrated: Pg):
    """Documents the boundary (ADR-102, H1 of the review): a run may point to a RETIRED version, because whether a version is usable is the Readiness Gate's
    decision (S22, check_code registry WORKING). When S22 lands, this test must be replaced by the Gate's own negative test, not silently kept."""
    with migrated.connect() as c:
        c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, 'o')", [ORG_A])
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'p','GREENFIELD')", [PRJ_A1, ORG_A])
        epic, op = new_epic(c, ORG_A, PRJ_A1), new_op(c, ORG_A, PRJ_A1)
        task = new_task(c, ORG_A, PRJ_A1, op, epic)
        retired = seed_worker_definition_version(c, "v-old")
        c.execute("UPDATE agents.worker_definition_versions SET status = 'RETIRED' WHERE id = %s", [retired])
        assert new_run(c, ORG_A, PRJ_A1, op, task)  # the helper's own version
        c.execute("INSERT INTO agents.worker_runs (id, organization_id, project_id, operation_id, task_id, worker_definition_version_id, status, "
                  "context_package_version_id, input_contract_version, output_contract_version, attempt_number) VALUES (%s,%s,%s,%s,%s,%s,'CREATED',%s,'in','out',9)",
                  [uuid4(), ORG_A, PRJ_A1, op, task, retired, uuid4()])
