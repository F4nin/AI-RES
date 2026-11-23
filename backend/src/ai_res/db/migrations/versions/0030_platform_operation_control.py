"""Narrow private Platform API privileges and pre-tenant auth audit.

Revision ID: 13baca8848ec
Revises: 61c9df2b04ae
"""
from collections.abc import Sequence

from alembic import op

revision: str = "13baca8848ec"
down_revision: str | None = "61c9df2b04ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE = """organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid"""
_OPERATION = "NULLIF(current_setting('app.platform_operation_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA operations, agents, audit TO ai_res_platform_api_group")
    op.execute("""
        GRANT SELECT(id,organization_id,project_id,operation_type,status,row_version,last_event_sequence,completed_at),
              UPDATE(status,row_version,last_event_sequence,workflow_id,started_at,completed_at,problem_ref)
        ON operations.operations TO ai_res_platform_api_group
    """)
    op.execute(f"""
        CREATE POLICY p_operations_platform_bound ON operations.operations TO ai_res_platform_api_group
        USING ({_SCOPE} AND id = {_OPERATION}) WITH CHECK ({_SCOPE} AND id = {_OPERATION})
    """)
    op.execute("GRANT INSERT ON operations.operation_events TO ai_res_platform_api_group")
    op.execute(f"""
        CREATE POLICY p_operation_events_platform_bound ON operations.operation_events FOR INSERT TO ai_res_platform_api_group
        WITH CHECK (operation_id = {_OPERATION})
    """)
    op.execute("GRANT SELECT(operation_id,status) ON agents.worker_runs TO ai_res_platform_api_group")
    op.execute(f"""
        CREATE POLICY p_worker_runs_platform_bound ON agents.worker_runs FOR SELECT TO ai_res_platform_api_group
        USING ({_SCOPE} AND operation_id = {_OPERATION})
    """)
    op.execute("GRANT INSERT ON audit.audit_events, audit.outbox_events TO ai_res_platform_api_group")
    op.execute(f"""
        CREATE POLICY p_audit_platform_bound ON audit.audit_events FOR INSERT TO ai_res_platform_api_group
        WITH CHECK ({_SCOPE} AND object_type = 'OPERATION' AND object_id = {_OPERATION})
    """)
    op.execute(f"""
        CREATE POLICY p_outbox_platform_bound ON audit.outbox_events FOR INSERT TO ai_res_platform_api_group
        WITH CHECK ({_SCOPE} AND aggregate_type = 'OPERATION' AND aggregate_id = {_OPERATION})
    """)
    op.execute("""
        CREATE TABLE platform.platform_auth_events (
            id uuid CONSTRAINT pk_platform_auth_events PRIMARY KEY,
            correlation_id uuid NOT NULL,
            reason text NOT NULL CONSTRAINT ck_platform_auth_reason CHECK (
                reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST')
            ),
            occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("ALTER TABLE platform.platform_auth_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.platform_auth_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_platform_auth_events_insert ON platform.platform_auth_events FOR INSERT TO ai_res_platform_api_group
        WITH CHECK (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST'))
    """)
    op.execute("""
        CREATE POLICY p_platform_auth_events_admin ON platform.platform_auth_events TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    op.execute("GRANT INSERT(id,correlation_id,reason) ON platform.platform_auth_events TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove pre-tenant security events.")
