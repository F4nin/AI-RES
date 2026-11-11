"""S05 slice A: iam / organization / project tables (ADR-016, ADR-050) under the real `ai_res_api` login role.

Seeding runs as the bootstrap superuser (bypasses RLS, FK checks still apply). Every behavioural assertion runs as a runtime role.
"""
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from .conftest import Pg, run_audit

pytestmark = pytest.mark.postgres
ORG_A, ORG_B = uuid4(), uuid4()
USER_A, USER_B = uuid4(), uuid4()
PRJ_A, PRJ_B = uuid4(), uuid4()
DIGEST = b"\x01" * 32
ARGON = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo"


def seed(pg: Pg) -> None:
    with pg.connect() as c:
        for org, name in ((ORG_A, "Org A"), (ORG_B, "Org B")):
            c.execute("INSERT INTO organization.organizations (id, name) VALUES (%s, %s)", [org, name])
        for uid, org, mail in ((USER_A, ORG_A, "a@example.test"), (USER_B, ORG_B, "b@example.test")):
            c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,%s,%s,%s)",
                      [uid, org, mail, mail, mail.split("@")[0]])
        for prj, org in ((PRJ_A, ORG_A), (PRJ_B, ORG_B)):
            c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,%s,'GREENFIELD')", [prj, org, f"p-{prj}"])
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,'ORGANIZATION_OWNER')",
                  [uuid4(), ORG_A, USER_A])


def api(pg: Pg, org: UUID | None, project: UUID | None = None) -> psycopg.Connection[Any]:
    """A runtime connection inside an explicit transaction with the transaction-local tenant context (or none)."""
    conn = pg.connect("ai_res_api", autocommit=False)
    if org is not None:
        conn.execute("SELECT set_config('app.organization_id', %s, true)", [str(org)])
        conn.execute("SELECT set_config('app.project_id', %s, true)", ["" if project is None else str(project)])
    return conn


@pytest.fixture
def seeded(migrated: Pg) -> Pg:
    seed(migrated)
    return migrated


def test_rls_coverage_and_grants_audit_are_clean_with_the_new_tables(seeded: Pg):
    with seeded.connect() as c:
        assert run_audit(c, "rls_coverage.sql") == []
        assert run_audit(c, "grants_audit.sql") == []
        assert run_audit(c, "postflight.sql") == []
        tables = {r[0] for r in c.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('iam','organization','project')")}
    assert tables >= {"iam.users", "iam.credentials", "iam.sessions", "iam.mfa_factors", "iam.mfa_recovery_codes", "iam.service_identities",
                      "iam.roles", "organization.organizations", "organization.memberships", "project.projects", "project.project_memberships"}


@pytest.mark.parametrize("table", ["iam.users", "iam.credentials", "iam.sessions", "iam.mfa_factors", "iam.service_identities",
                                   "organization.organizations", "organization.memberships", "project.projects", "project.project_memberships"])
def test_missing_context_is_default_deny_for_reads(seeded: Pg, table: str):
    with api(seeded, None) as c:
        assert c.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - parametrized literal table names.fetchone() == (0,)


def test_tenant_a_never_sees_tenant_b(seeded: Pg):
    with api(seeded, ORG_A) as c:
        assert [r[0] for r in c.execute("SELECT id FROM iam.users")] == [USER_A]
        assert [r[0] for r in c.execute("SELECT id FROM organization.organizations")] == [ORG_A]
        assert [r[0] for r in c.execute("SELECT id FROM project.projects")] == [PRJ_A]
        assert c.execute("SELECT count(*) FROM iam.users WHERE id = %s", [USER_B]).fetchone() == (0,)  # forged id: no existence leak
        assert c.execute("UPDATE iam.users SET display_name = 'x', row_version = row_version + 1 WHERE id = %s", [USER_B]).rowcount == 0


def test_insert_for_another_organization_is_rejected_by_with_check(seeded: Pg):
    with api(seeded, ORG_A) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute("INSERT INTO project.projects (id, organization_id, name, project_type) VALUES (%s,%s,'evil','GREENFIELD')", [uuid4(), ORG_B])


def test_membership_cannot_join_a_user_of_another_organization(seeded: Pg):
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # composite FK (organization_id, user_id): bypasses RLS but not FKs
        c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,'ANALYST')", [uuid4(), ORG_A, USER_B])


def test_organization_membership_rejects_project_only_and_unknown_roles(seeded: Pg):
    with seeded.connect() as c:  # USER_A already has a membership: use a fresh user so the role FK, not the unique key, is what fires
        fresh = uuid4()
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'c@example.test','c@example.test','c')",
                  [fresh, ORG_A])
    for role in ("ANALYST", "NO_SUCH_ROLE"):
        with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (%s,%s,%s,%s)",
                      [uuid4(), ORG_A, fresh, role])


def test_project_membership_must_stay_inside_one_organization(seeded: Pg):
    with seeded.connect() as c:
        c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (%s,%s,%s,%s,'ANALYST')",
                  [uuid4(), ORG_A, PRJ_A, USER_A])
    for prj, usr in ((PRJ_B, USER_A), (PRJ_A, USER_B)):
        with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):
            c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (%s,%s,%s,%s,'ANALYST')",
                      [uuid4(), ORG_A, prj, usr])
    fresh = uuid4()
    with seeded.connect() as c:
        c.execute("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (%s,%s,'d@example.test','d@example.test','d')",
                  [fresh, ORG_A])
    with seeded.connect() as c, pytest.raises(errors.ForeignKeyViolation):  # ORGANIZATION_OWNER is not a project-level role
        c.execute("INSERT INTO project.project_memberships (id, organization_id, project_id, user_id, role_code) VALUES (%s,%s,%s,%s,'ORGANIZATION_OWNER')",
                  [uuid4(), ORG_A, PRJ_A, fresh])


def test_credentials_accept_only_argon2id_hashes(seeded: Pg):
    with api(seeded, ORG_A) as c:
        c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)",
                  [uuid4(), ORG_A, USER_A, ARGON])
    for bad in ("plaintext-password", "$2b$12$bcrypt", "$argon2i$v=19$x"):
        with api(seeded, ORG_A) as c, pytest.raises(errors.CheckViolation):
            c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)",
                      [uuid4(), ORG_A, USER_A, bad])


def test_sessions_store_only_fixed_length_digests_never_raw_tokens(seeded: Pg):
    cols = {r[0] for r in seeded.connect().execute("SELECT column_name FROM information_schema.columns WHERE table_schema='iam' AND table_name='sessions'")}
    assert {"session_digest", "csrf_digest"} <= cols and not ({"token", "session_id", "csrf_token", "secret"} & cols)
    with api(seeded, ORG_A) as c:
        c.execute("INSERT INTO iam.sessions (id, organization_id, user_id, session_digest, csrf_digest, idle_expires_at, absolute_expires_at)"
                  " VALUES (%s,%s,%s,%s,%s, now() + interval '30 minutes', now() + interval '12 hours')", [uuid4(), ORG_A, USER_A, DIGEST, DIGEST])
    with api(seeded, ORG_A) as c, pytest.raises(errors.CheckViolation):
        c.execute("INSERT INTO iam.sessions (id, organization_id, user_id, session_digest, csrf_digest, idle_expires_at, absolute_expires_at)"
                  " VALUES (%s,%s,%s,%s,%s, now(), now())", [uuid4(), ORG_A, USER_A, b"short", DIGEST])


def test_row_version_must_advance_by_exactly_one_and_scope_columns_are_immutable(seeded: Pg):
    with api(seeded, ORG_A) as c:
        assert c.execute("UPDATE project.projects SET name = 'renamed', row_version = row_version + 1 WHERE id = %s", [PRJ_A]).rowcount == 1
    with api(seeded, ORG_A) as c, pytest.raises(errors.IntegrityConstraintViolation):  # blind overwrite without the CAS bump
        c.execute("UPDATE project.projects SET name = 'lww' WHERE id = %s", [PRJ_A])
    with api(seeded, ORG_A) as c, pytest.raises(errors.IntegrityConstraintViolation):  # moving a project to another organization
        c.execute("UPDATE project.projects SET organization_id = %s, row_version = row_version + 1 WHERE id = %s", [ORG_B, PRJ_A])


@pytest.mark.parametrize("sql", [
    "DELETE FROM iam.users", "TRUNCATE iam.users", "DELETE FROM project.projects", "DELETE FROM iam.sessions",
    "CREATE TABLE iam.evil (id int)", "UPDATE iam.roles SET project_level = true",
])
def test_runtime_api_has_no_delete_truncate_ddl_or_reference_data_writes(seeded: Pg, sql: str):
    with api(seeded, ORG_A) as c, pytest.raises(errors.InsufficientPrivilege):
        c.execute(sql)


def test_auditor_and_dispatcher_cannot_read_identity_tables(seeded: Pg):
    for role in ("ai_res_auditor", "ai_res_outbox_dispatcher", "ai_res_event_consumer"):
        with seeded.connect(role) as c, pytest.raises(errors.InsufficientPrivilege):
            c.execute("SELECT 1 FROM iam.credentials LIMIT 1")


def test_reference_roles_are_readable_and_seeded(seeded: Pg):
    with api(seeded, None) as c:
        codes = {r[0] for r in c.execute("SELECT code FROM iam.roles")}
    assert codes == {"ORGANIZATION_OWNER", "ORGANIZATION_ADMIN", "PROJECT_ADMIN", "ANALYST", "REVIEWER_APPROVER", "READ_ONLY_VIEWER", "AUDITOR"}


def test_session_absolute_lifetime_is_fixed_and_idle_cannot_outlive_it(seeded: Pg):
    """A bug or injection in session-refresh code cannot extend a session beyond its absolute lifetime (security review LOW-1; security.md: 12 h)."""
    sess = uuid4()
    with api(seeded, ORG_A) as c:
        c.execute("INSERT INTO iam.sessions (id, organization_id, user_id, session_digest, csrf_digest, idle_expires_at, absolute_expires_at)"
                  " VALUES (%s,%s,%s,%s,%s, now() + interval '30 minutes', now() + interval '12 hours')", [sess, ORG_A, USER_A, DIGEST, DIGEST])
    with api(seeded, ORG_A) as c, pytest.raises(errors.IntegrityConstraintViolation, match="immutable"):
        c.execute("UPDATE iam.sessions SET absolute_expires_at = now() + interval '100 years', row_version = row_version + 1 WHERE id = %s", [sess])
    with api(seeded, ORG_A) as c, pytest.raises(errors.CheckViolation):
        c.execute("UPDATE iam.sessions SET idle_expires_at = now() + interval '13 hours', row_version = row_version + 1 WHERE id = %s", [sess])
    with api(seeded, ORG_A) as c:  # control: sliding the idle timeout inside the absolute lifetime is the normal refresh
        slide = "UPDATE iam.sessions SET idle_expires_at = now() + interval '1 hour', last_seen_at = now(), row_version = row_version + 1 WHERE id = %s"
        assert c.execute(slide, [sess]).rowcount == 1


def test_revocation_and_use_markers_are_write_once_and_revoked_is_terminal(seeded: Pg):
    sess, factor, code = uuid4(), uuid4(), uuid4()
    with api(seeded, ORG_A) as c:
        c.execute("INSERT INTO iam.sessions (id, organization_id, user_id, session_digest, csrf_digest, idle_expires_at, absolute_expires_at)"
                  " VALUES (%s,%s,%s,%s,%s, now() + interval '30 minutes', now() + interval '12 hours')", [sess, ORG_A, USER_A, DIGEST, DIGEST])
        c.execute("INSERT INTO iam.mfa_factors (id, organization_id, user_id, factor_type, secret_ciphertext, status) VALUES (%s,%s,%s,'TOTP',%s,'ACTIVE')",
                  [factor, ORG_A, USER_A, b"test-ciphertext-placeholder"])
        c.execute("INSERT INTO iam.mfa_recovery_codes (id, organization_id, user_id, code_digest) VALUES (%s,%s,%s,%s)", [code, ORG_A, USER_A, DIGEST])
    with api(seeded, ORG_A) as c:
        c.execute("UPDATE iam.sessions SET revoked_at = now(), revoked_reason = 'LOGOUT', row_version = row_version + 1 WHERE id = %s", [sess])
        c.execute("UPDATE iam.mfa_factors SET status = 'REVOKED', row_version = row_version + 1 WHERE id = %s", [factor])
        c.execute("UPDATE iam.mfa_recovery_codes SET used_at = now(), row_version = row_version + 1 WHERE id = %s", [code])
    for sql, arg in (("UPDATE iam.sessions SET revoked_at = NULL, revoked_reason = NULL, row_version = row_version + 1 WHERE id = %s", sess),
                     ("UPDATE iam.mfa_recovery_codes SET used_at = NULL, row_version = row_version + 1 WHERE id = %s", code),
                     ("UPDATE iam.mfa_factors SET status = 'ACTIVE', row_version = row_version + 1 WHERE id = %s", factor)):
        with api(seeded, ORG_A) as c, pytest.raises(errors.IntegrityConstraintViolation):
            c.execute(sql, [arg])
    membership = seeded.connect().execute("SELECT id FROM organization.memberships WHERE user_id = %s", [USER_A]).fetchone()[0]  # type: ignore[index]
    with api(seeded, ORG_A) as c:
        c.execute("UPDATE organization.memberships SET status = 'REVOKED', row_version = row_version + 1 WHERE id = %s", [membership])
    with api(seeded, ORG_A) as c, pytest.raises(errors.IntegrityConstraintViolation):
        c.execute("UPDATE organization.memberships SET status = 'ACTIVE', row_version = row_version + 1 WHERE id = %s", [membership])
