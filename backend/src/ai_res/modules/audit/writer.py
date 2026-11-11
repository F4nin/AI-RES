# ruff: noqa: E501  -- one SQL statement per string keeps the query reviewable
"""Fail-closed audit writer (security.md "Telemetry и аудит", SEC-019, AUTH-013).

The writer is bound to the CALLER's session, so the audit row commits or rolls back together with the protected action: if the audit insert
fails the exception propagates and the whole transaction (including the action) is rolled back. Rows are append-only (trigger) and never
carry secret-looking keys (rejected, not silently redacted).
"""
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.redaction import assert_no_sensitive_keys

_RESULT = {AuditOutcome.ALLOWED: "SUCCEEDED", AuditOutcome.SUCCEEDED: "SUCCEEDED", AuditOutcome.DENIED: "DENIED", AuditOutcome.FAILED: "FAILED"}
_CORRELATION_NS = uuid.UUID("6f1c2f5e-3a0b-4c1d-9a55-0d2b7f3a11aa")  # fixed namespace: the same request id always maps to the same correlation uuid


def correlation_uuid(request_id: str | None) -> UUID:
    """audit.correlation_id is a uuid; request ids are free-form tokens. A uuid-shaped id is kept, any other is mapped deterministically."""
    if not request_id:
        return new_id()
    try:
        return UUID(request_id)
    except ValueError:
        return uuid.uuid5(_CORRELATION_NS, request_id)


class SqlAuditWriter:
    """Implements AuditWriterPort. Construct per Unit of Work, AFTER the tenant context is set (RLS WITH CHECK pins organization/project)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def write(self, record: AuditRecord, *, occurred_at: datetime | None = None) -> None:
        if record.organization_id is None:
            raise ValueError("audit record requires organization_id")
        assert_no_sensitive_keys(record.details, "details")
        params: dict[str, Any] = {
            "id": new_id(), "org": UUID(record.organization_id), "prj": None if record.project_id is None else UUID(record.project_id),
            "at": require_utc(occurred_at or record.occurred_at or utc_now()), "atype": record.actor_type,
            "aid": None if record.actor_id is None else UUID(record.actor_id), "action": record.action, "otype": record.resource_type.upper(),
            "oid": None if record.resource_id is None else UUID(record.resource_id), "result": _RESULT[record.outcome], "reason": record.reason_code,
            "corr": correlation_uuid(record.request_id),
            "details": canonical_json({**(record.details or {}), **({"policyVersion": record.policy_version} if record.policy_version else {})}),
        }
        await self._s.execute(text(
            "INSERT INTO audit.audit_events (id, organization_id, project_id, occurred_at, actor_type, actor_id, action, object_type, object_id, result, reason_code, correlation_id, details) "
            "VALUES (:id, :org, :prj, :at, :atype, :aid, :action, :otype, :oid, :result, :reason, :corr, CAST(:details AS jsonb))"), params)
