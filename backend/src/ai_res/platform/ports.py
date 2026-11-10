"""Ports for cross-cutting capabilities. Implementations arrive in S07 (auth/policy/audit/idempotency).

Shapes are fixed here because S07 implementations and every later enforcement point depend on them.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from ai_res.platform.problems import ErrorCode, ProblemError


# ---------- identities ----------
class ServiceName(StrEnum):
    API = "API"
    MANAGER_RUNTIME = "MANAGER_RUNTIME"
    WORKER_RUNTIME = "WORKER_RUNTIME"
    TEMPORAL_ACTIVITY = "TEMPORAL_ACTIVITY"
    CONNECTOR = "CONNECTOR"
    LLM_GATEWAY = "LLM_GATEWAY"
    OUTBOX_DISPATCHER = "OUTBOX_DISPATCHER"
    EVENT_CONSUMER = "EVENT_CONSUMER"


@dataclass(frozen=True, slots=True, kw_only=True)
class Principal:
    """Authenticated browser user. Ids come from server-side session state, never from the client."""
    user_id: str
    session_id: str
    mfa_verified: bool
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceIdentity:
    name: ServiceName
    audience: ServiceName
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


class AuthenticationPort(Protocol):
    async def authenticate_session(self, session_token: str) -> Principal | None:
        """Principal for a valid, unexpired, unrevoked session; None otherwise (reason is audited by the implementation)."""


class ServiceIdentityPort(Protocol):
    async def verify_service_token(self, token: str, audience: ServiceName) -> ServiceIdentity | None: ...


# ---------- policy ----------
class Effect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyRequest:
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id or not self.action or not self.resource_type:
            raise ValueError("actor_id, action and resource_type are required")
        if self.project_id is not None and self.organization_id is None:
            raise ValueError("project_id requires organization_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDecision:
    effect: Effect
    reason_code: str
    policy_version: str
    approval_ref: str | None = None  # set when effect is APPROVAL_REQUIRED and an approval request exists

    def __post_init__(self) -> None:
        if not isinstance(self.effect, Effect) or not self.reason_code or not self.policy_version:
            raise ValueError("invalid policy decision")


class PolicyDecisionPort(Protocol):
    async def decide(self, request: PolicyRequest) -> PolicyDecision: ...


def _require_timeout(value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError("timeout_seconds must be a positive number (None would disable fail-closed behaviour)")


async def decide_fail_closed(policy: PolicyDecisionPort, request: PolicyRequest, *, timeout_seconds: float) -> PolicyDecision:
    """Returns only ALLOW decisions. Outage, malformed decision or unexpected error -> 503 POLICY_ENGINE_UNAVAILABLE
    (never allow); DENY -> 403 (object-scoped reads must map this to a controlled 404
    at the call site, security.md); APPROVAL_REQUIRED -> 403 with reason `approval_required` (a human decision is needed)."""
    _require_timeout(timeout_seconds)
    try:
        async with asyncio.timeout(timeout_seconds):  # a hung engine fails closed; the timeout value is set by the caller (WORKING)
            decision = await policy.decide(request)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("policy returned a non-decision")
    except ProblemError:
        raise
    except Exception as exc:
        raise ProblemError(ErrorCode.POLICY_ENGINE_UNAVAILABLE, "Policy decision unavailable.") from exc
    if decision.effect is Effect.ALLOW:
        return decision
    reason = "approval_required" if decision.effect is Effect.APPROVAL_REQUIRED else "denied"
    raise ProblemError(ErrorCode.ACCESS_DENIED, "Access denied." if reason == "denied" else "Human approval required.",
                       errors=[{"field": "policy", "reason": reason}])


# ---------- audit ----------
class AuditOutcome(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditRecord:
    actor_id: str
    action: str
    outcome: AuditOutcome
    resource_type: str
    resource_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    reason_code: str | None = None
    policy_version: str | None = None
    request_id: str | None = None
    occurred_at: datetime | None = field(default=None)  # set by the writer (server clock) when None


class AuditWriterPort(Protocol):
    async def write(self, record: AuditRecord) -> None:
        """Must raise on failure and must join the caller's transaction (S07). Callers abort the protected action on error."""


async def audit_or_abort(writer: AuditWriterPort, record: AuditRecord, *, timeout_seconds: float) -> None:
    _require_timeout(timeout_seconds)
    try:
        async with asyncio.timeout(timeout_seconds):
            await writer.write(record)
    except Exception as exc:
        raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Audit unavailable; action not performed.") from exc


# ---------- idempotency ----------
class IdempotencyOutcome(StrEnum):
    NEW = "NEW"
    REPLAY = "REPLAY"  # same key + fingerprint, completed: return the stored result
    IN_PROGRESS = "IN_PROGRESS"  # same key + fingerprint, first execution not finished
    CONFLICT = "CONFLICT"  # same key, different fingerprint -> 409 IDEMPOTENCY_KEY_REUSED


@dataclass(frozen=True, slots=True, kw_only=True)
class IdempotencyRequest:
    tenant_scope: str  # organization/actor scope the HMAC digest is bound to
    command: str
    key: str
    fingerprint: str


@dataclass(frozen=True, slots=True, kw_only=True)
class IdempotencyResult:
    outcome: IdempotencyOutcome
    response_ref: str | None = None  # reference to the stored result when REPLAY


class IdempotencyStorePort(Protocol):
    async def begin(self, request: IdempotencyRequest) -> IdempotencyResult: ...

    async def complete(self, request: IdempotencyRequest, response_ref: str) -> None: ...


def raise_if_idempotency_conflict(result: IdempotencyResult) -> None:
    if result.outcome is IdempotencyOutcome.CONFLICT:
        raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "Idempotency-Key was used with a different request.")
