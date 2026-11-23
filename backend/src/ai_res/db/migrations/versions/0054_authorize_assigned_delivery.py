"""Admit the exact signed Outbox lease to the trusted Backend.

Revision ID: 28a56a9341ce
Revises: 7c4cb218720a
"""
from alembic import op

revision = "28a56a9341ce"
down_revision = "7c4cb218720a"
branch_labels = None
depends_on = None

_AUTHORIZE = "audit.authorize_assigned_delivery(uuid,text,integer,integer,text,uuid,timestamptz,uuid)"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.platform_request_nonces
            DROP CONSTRAINT ck_platform_nonce_issuer,
            ADD CONSTRAINT ck_platform_nonce_issuer CHECK (issuer IN ('MANAGER_RUNTIME','TEMPORAL_AUTH_CONTROL','OUTBOX_DISPATCHER'));
        ALTER POLICY p_platform_nonces_platform_insert ON platform.platform_request_nonces
            WITH CHECK (issuer IN ('MANAGER_RUNTIME','TEMPORAL_AUTH_CONTROL') AND expires_at>clock_timestamp());
        ALTER TABLE platform.platform_auth_events
            DROP CONSTRAINT ck_platform_auth_reason,
            ADD CONSTRAINT ck_platform_auth_reason CHECK ((
                (reason IN ('INVALID_CREDENTIAL','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED','INVALID_REQUEST') AND action IS NULL)
                OR (reason='AUTHORIZED' AND action IN ('AUTHORIZE_START','REGISTER_TASK','CHECK_TASK',
                    'AUTHORIZE_RECONCILIATION_DESCRIBE','AUTHORIZE_BOUND_STATUS','AUTHORIZE_BOUND_CANCEL'))
                OR (action='AUTHORIZE_ASSIGNED_DELIVERY' AND reason IN ('AUTHORIZED','EXPIRED_OR_REPLAY','ASSIGNMENT_DENIED'))
            ) IS TRUE);
    """)
    op.execute("""
        CREATE FUNCTION audit.authorize_assigned_delivery(
            row_ref uuid, owner_ref text, attempt integer, generation integer, namespace_ref text,
            request_nonce uuid, credential_expires timestamptz, request_correlation uuid
        ) RETURNS TABLE(decision text, id uuid, event_id uuid, destination text, aggregate_type text,
            aggregate_id uuid, aggregate_sequence bigint, event_type text, schema_version integer, envelope jsonb,
            attempt_count integer, replay_count integer, dispatch_namespace text, lease_until timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
        DECLARE
            leased audit.outbox_events%ROWTYPE;
            result text;
        BEGIN
            INSERT INTO platform.platform_request_nonces(issuer,nonce,expires_at)
            SELECT 'OUTBOX_DISPATCHER',request_nonce,credential_expires WHERE credential_expires>clock_timestamp()
            ON CONFLICT DO NOTHING;
            IF NOT FOUND OR credential_expires<=clock_timestamp() THEN
                result := 'EXPIRED_OR_REPLAY';
            ELSE
                SELECT e.* INTO leased FROM audit.outbox_events e
                WHERE e.id=row_ref AND e.status='IN_FLIGHT' AND e.lease_owner=owner_ref
                  AND e.attempt_count=attempt AND e.replay_count=generation AND e.dispatch_namespace=namespace_ref
                  AND e.dispatch_assignment_id IS NOT NULL AND e.lease_until>clock_timestamp()
                  AND e.destination IN ('orchestration.operation-start','orchestration.operation-cancel')
                FOR SHARE OF e;
                result := CASE
                    WHEN credential_expires<=clock_timestamp() THEN 'EXPIRED_OR_REPLAY'
                    WHEN FOUND AND leased.lease_until>clock_timestamp() THEN 'AUTHORIZED'
                    ELSE 'ASSIGNMENT_DENIED'
                END;
            END IF;
            INSERT INTO platform.platform_auth_events(id,correlation_id,reason,action)
            VALUES (gen_random_uuid(),request_correlation,result,'AUTHORIZE_ASSIGNED_DELIVERY');
            IF result <> 'AUTHORIZED' THEN leased := NULL; END IF;
            RETURN QUERY SELECT result,leased.id,leased.event_id,leased.destination,leased.aggregate_type,leased.aggregate_id,
                leased.aggregate_sequence,leased.event_type,leased.schema_version,leased.envelope,leased.attempt_count,
                leased.replay_count,leased.dispatch_namespace,leased.lease_until;
        END $f$;
    """)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_AUTHORIZE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_AUTHORIZE} TO ai_res_api_group")


def downgrade() -> None:
    raise NotImplementedError("Use a forward-fix to preserve one-use delivery receipts and audit.")
