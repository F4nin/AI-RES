"""Server-owned dispatch and exact Workflow Run binding for Platform API.

Revision ID: 61c9df2b04ae
Revises: 4d8c7b2d61f3
"""
from collections.abc import Sequence

from alembic import op

revision: str = "61c9df2b04ae"
down_revision: str | None = "4d8c7b2d61f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESOLVE = "platform.resolve_operation_assignment(uuid,uuid,text,uuid,text)"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.operation_execution_assignments (
            id uuid CONSTRAINT pk_operation_execution_assignments PRIMARY KEY,
            organization_id uuid NOT NULL,
            project_id uuid NOT NULL,
            operation_id uuid NOT NULL,
            workflow_id text NOT NULL CONSTRAINT ck_operation_assignment_workflow_id CHECK (workflow_id = 'operation-' || operation_id::text),
            workflow_type text NOT NULL,
            namespace text NOT NULL,
            task_queue text NOT NULL,
            workflow_contract_version integer NOT NULL,
            input_digest bytea NOT NULL CONSTRAINT ck_operation_assignment_digest CHECK (octet_length(input_digest) = 32),
            correlation_id uuid NOT NULL,
            allowed_actions text[] NOT NULL CONSTRAINT ck_operation_assignment_actions CHECK (
                cardinality(allowed_actions) > 0 AND array_position(allowed_actions,NULL) IS NULL
                AND allowed_actions <@ ARRAY['operation.acknowledge_start','operation.record_failure','operation.confirm_cancellation']::text[]
            ),
            workflow_run_id uuid,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            revoked_at timestamptz,
            CONSTRAINT uq_operation_execution_assignment UNIQUE (operation_id),
            CONSTRAINT fk_operation_assignment_operation FOREIGN KEY (organization_id, project_id, operation_id)
                REFERENCES operations.operations(organization_id, project_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE platform.operation_execution_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.operation_execution_assignments FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY p_operation_assignments_api_tenant ON platform.operation_execution_assignments TO ai_res_api_group USING (
            organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
            AND project_id = NULLIF(current_setting('app.project_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY p_operation_assignments_owner_migration ON platform.operation_execution_assignments TO ai_res_owner
        USING (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
        WITH CHECK (COALESCE(current_setting('app.migration_mode', true), '') = 'on')
    """)
    op.execute("""
        CREATE FUNCTION platform.keep_operation_assignment_binding() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        BEGIN
            IF OLD.revoked_at IS NOT NULL OR (
                OLD.workflow_run_id IS NOT NULL AND NEW.workflow_run_id IS DISTINCT FROM OLD.workflow_run_id
            ) THEN
                RAISE EXCEPTION 'operation assignment is immutable after binding/revocation' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $f$
    """)
    op.execute("""
        CREATE TRIGGER trg_operation_assignment_binding BEFORE UPDATE ON platform.operation_execution_assignments
        FOR EACH ROW EXECUTE FUNCTION platform.keep_operation_assignment_binding()
    """)
    op.execute("""
        GRANT SELECT,
          INSERT(id,organization_id,project_id,operation_id,workflow_id,workflow_type,namespace,task_queue,
                 workflow_contract_version,input_digest,correlation_id,allowed_actions),
          UPDATE(workflow_run_id,revoked_at)
        ON platform.operation_execution_assignments TO ai_res_api_group
    """)
    op.execute("""
        CREATE FUNCTION platform.resolve_operation_assignment(aid uuid, oid uuid, wid text, rid uuid, action text)
        RETURNS TABLE(organization_id uuid, project_id uuid, correlation_id uuid)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
            SELECT a.organization_id, a.project_id, a.correlation_id
            FROM platform.operation_execution_assignments a
            WHERE a.id = aid AND a.operation_id = oid AND a.workflow_id = wid AND a.workflow_run_id = rid
              AND a.revoked_at IS NULL AND action = ANY(a.allowed_actions)
            FOR SHARE OF a
        $f$
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_RESOLVE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_RESOLVE} TO ai_res_platform_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix. Downgrade would remove execution authority history.")
