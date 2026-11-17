# ruff: noqa: E501 -- fixed SQL fixture, no application input
"""S19 upgrades a database containing an immutable pre-builder snapshot."""
from uuid import uuid4

import psycopg
import pytest

from .conftest import run_audit
from .test_domain_content_schema import SHA, add_requirement, seed_tenants
from .test_operations_work_schema import ORG_A, PRJ_A1, api


def test_previous_revision_keeps_legacy_snapshot_sealed_and_roles_unchanged(empty_db, upgrade):
    upgrade("f3a9c1d7b542")
    pkg, ver = uuid4(), uuid4()
    with empty_db.connect(autocommit=False) as c:
        seed_tenants(c)
        _, rv = add_requirement(c, ORG_A, PRJ_A1)
        c.execute("INSERT INTO context.context_packages (id,organization_id,project_id,name,current_version_id,last_version_number) VALUES (%s,%s,%s,'legacy',%s,1)", [pkg, ORG_A, PRJ_A1, ver])
        c.execute("INSERT INTO context.context_package_versions (id,organization_id,project_id,context_package_id,version_number,item_count,content_digest) VALUES (%s,%s,%s,%s,1,1,%s)", [ver, ORG_A, PRJ_A1, pkg, SHA])
        c.execute("INSERT INTO context.context_package_items (id,organization_id,project_id,context_package_version_id,item_kind,requirement_version_id,inclusion_role) VALUES (%s,%s,%s,%s,'REQUIREMENT_VERSION',%s,'PRIMARY')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
        before = c.execute("SELECT context_package_id,version_number,item_count,content_digest,created_at FROM context.context_package_versions WHERE id=%s", [ver]).fetchone()
    upgrade("head")
    with empty_db.connect() as c:
        after = c.execute("SELECT context_package_id,version_number,item_count,content_digest,created_at FROM context.context_package_versions WHERE id=%s", [ver]).fetchone()
        assert before == after
        assert c.execute("SELECT builder_manifest,creation_transaction_id FROM context.context_package_versions WHERE id=%s", [ver]).fetchone() == (None, None)
        assert run_audit(c, "grants_audit.sql") == []
        assert run_audit(c, "rls_coverage.sql") == []
        assert run_audit(c, "postflight.sql") == []
    with api(empty_db, ORG_A, PRJ_A1) as c, pytest.raises(psycopg.IntegrityError, match="sealed"):
        c.execute("INSERT INTO context.context_package_items (id,organization_id,project_id,context_package_version_id,item_kind,requirement_version_id,inclusion_role) VALUES (%s,%s,%s,%s,'REQUIREMENT_VERSION',%s,'PRIMARY')", [uuid4(), ORG_A, PRJ_A1, ver, rv])
