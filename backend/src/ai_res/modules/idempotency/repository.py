# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Idempotency records (ADR-024, api-and-contracts.md). The key arrives here ONLY as an HMAC digest + key id (computed by the auth/policy layer, S07);
the raw client key never reaches storage. Same digest + same fingerprint -> replay; same digest + different fingerprint -> 409 IDEMPOTENCY_KEY_REUSED.
Concurrent first requests race on the scoped unique key: exactly one gets NEW.
"""
import hmac
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import affected, canonical_json
from ai_res.platform.clock import require_utc
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.redaction import assert_no_sensitive_keys


class IdempotencyOutcome(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"  # same request still running: caller answers 409/202 per contract, never executes again
    REPLAY = "REPLAY"  # finished: return the stored response


@dataclass(frozen=True)
class IdempotencyRecord:
    id: UUID
    outcome: IdempotencyOutcome
    status: str
    resource_type: str | None
    resource_id: UUID | None
    response_status: int | None
    response_body_ref: dict[str, Any] | None


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def begin(self, organization_id: UUID, project_id: UUID | None, scope_type: str, scope_id: UUID, key_digest: bytes, key_id: str,
                    request_fingerprint: bytes, expires_at: datetime) -> IdempotencyRecord:
        rid = new_id()
        inserted = (await self._s.execute(text(
            "INSERT INTO platform.idempotency_records (id, organization_id, project_id, scope_type, scope_id, key_digest, key_id, request_fingerprint, status, expires_at) "
            "VALUES (:id, :org, :prj, :st, :sid, :kd, :kid, :fp, 'IN_PROGRESS', :exp) ON CONFLICT (organization_id, scope_type, scope_id, key_digest) DO NOTHING "
            "RETURNING id"), {"id": rid, "org": organization_id, "prj": project_id, "st": scope_type, "sid": scope_id, "kd": key_digest, "kid": key_id,
                              "fp": request_fingerprint, "exp": require_utc(expires_at)})).first()
        if inserted is not None:
            return IdempotencyRecord(rid, IdempotencyOutcome.NEW, "IN_PROGRESS", None, None, None, None)
        # The conflicting row may belong to a concurrent, not-yet-committed transaction: ON CONFLICT waited for it, so it is visible now (READ COMMITTED).
        r = (await self._s.execute(text(
            "SELECT id, request_fingerprint, key_id, project_id, expires_at, now() AS db_now, status, resource_type, resource_id, response_status, response_body_ref FROM platform.idempotency_records "
            "WHERE organization_id = :org AND scope_type = :st AND scope_id = :sid AND key_digest = :kd"),
            {"org": organization_id, "st": scope_type, "sid": scope_id, "kd": key_digest})).mappings().first()
        if r is None:  # not visible under this project context (RLS) although the key exists: refuse rather than guess
            raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "The idempotency key cannot be used in this context.")
        if r["expires_at"] <= r["db_now"]:  # expiry/purge/takeover policy is undecided (G-58): refuse explicitly instead of replaying a stale response
            raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "The idempotency key has expired and cannot be reused.")
        if r["key_id"] != key_id or r["project_id"] != project_id:
            raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "The idempotency key cannot be used in this context.")
        if not hmac.compare_digest(bytes(r["request_fingerprint"]), request_fingerprint):
            raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "The idempotency key was already used with a different request.")
        outcome = IdempotencyOutcome.IN_PROGRESS if r["status"] == "IN_PROGRESS" else IdempotencyOutcome.REPLAY
        return IdempotencyRecord(r["id"], outcome, r["status"], r["resource_type"], r["resource_id"], r["response_status"], r["response_body_ref"])

    async def complete(self, record_id: UUID, status: str, resource_type: str | None, resource_id: UUID | None, response_status: int, response_body_ref: dict[str, Any] | None) -> None:
        assert_no_sensitive_keys(response_body_ref, "response_body_ref")  # the stored response is replayed to later callers
        r = await self._s.execute(text(
            "UPDATE platform.idempotency_records SET status = :st, resource_type = :rt, resource_id = :rid, response_status = :rs, response_body_ref = CAST(:body AS jsonb), "
            "completed_at = now() WHERE id = :id AND status = 'IN_PROGRESS'"),
            {"id": record_id, "st": status, "rt": resource_type, "rid": resource_id, "rs": response_status,
             "body": None if response_body_ref is None else canonical_json(response_body_ref)})
        if affected(r) != 1:
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Idempotency record is not in progress.")
