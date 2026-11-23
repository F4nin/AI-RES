"""Request-bound ar2 credentials for the private Platform API (ADR-129, DOC-084)."""
import base64
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ai_res.modules.iam.service_tokens import _unique
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceName

_PREFIX = "ar2"
_DOMAIN = b"ai-res-platform-request-v2\x00"
_AUDIENCE = "PLATFORM_API"
_AUTH_CONTROL_AUDIENCE = "PLATFORM_AUTH_CONTROL"
_DELIVERY_AUDIENCE = "BACKEND_ASSIGNED_DELIVERY"
_CLAIMS = frozenset({"iss", "aud", "iat", "exp", "nonce", "action", "method", "path", "bodySha256"})


class PlatformAction(StrEnum):
    ACKNOWLEDGE_START = "operation.acknowledge_start"
    RECORD_FAILURE = "operation.record_failure"
    CONFIRM_CANCELLATION = "operation.confirm_cancellation"
    READ_MANAGER_INPUT = "manager.read_input"
    RECORD_MANAGER_DRAFT = "manager.record_draft"
    MATERIALIZE_PLAN_TASKS = "plan.materialize_tasks"


_ROUTE = {
    PlatformAction.ACKNOWLEDGE_START: (2, "start-acknowledgement"),
    PlatformAction.RECORD_FAILURE: (2, "failure"),
    PlatformAction.CONFIRM_CANCELLATION: (2, "cancellation-confirmation"),
    PlatformAction.READ_MANAGER_INPUT: (3, "manager-input"),
    PlatformAction.RECORD_MANAGER_DRAFT: (3, "manager-draft"),
    PlatformAction.MATERIALIZE_PLAN_TASKS: (3, "plan-tasks"),
}


@dataclass(frozen=True, slots=True)
class PlatformRequest:
    """Expected facts from the selected route, before parsing the bounded body."""
    action: PlatformAction
    operation_id: UUID
    body: bytes
    adaptive_input: bool = False
    epic_context: bool = False

    @property
    def path(self) -> str:
        version, suffix = _ROUTE[self.action]
        if self.adaptive_input:
            if self.action is not PlatformAction.READ_MANAGER_INPUT:
                raise ValueError("adaptive v4 is only defined for Manager input")
            version = 4
        if self.epic_context:
            if self.adaptive_input or self.action not in {PlatformAction.READ_MANAGER_INPUT, PlatformAction.RECORD_MANAGER_DRAFT}:
                raise ValueError("v5 is only defined for Manager context and draft")
            version = 5
        return f"/internal/v{version}/operations/{self.operation_id}/{suffix}"


class AuthControlAction(StrEnum):
    AUTHORIZE_START = "authorize-start"
    AUTHORIZE_RECONCILIATION_DESCRIBE = "authorize-reconciliation-describe"
    AUTHORIZE_BOUND_STATUS = "authorize-bound-status"
    AUTHORIZE_BOUND_CANCEL = "authorize-bound-cancel"
    REGISTER_TASK = "register-task"
    CHECK_TASK = "check-task"
    WORKFLOW_TASK_CONTEXT = "workflow-task-context"


@dataclass(frozen=True, slots=True)
class AuthControlRequest:
    action: AuthControlAction
    body: bytes

    @property
    def path(self) -> str:
        return f"/internal/auth-control/v1/{self.action.value}"


class AssignedDeliveryAction(StrEnum):
    DELIVER = "outbox.deliver_assigned"


ASSIGNED_DELIVERY_PATH = "/internal/assigned-delivery/v1"


@dataclass(frozen=True, slots=True)
class AssignedDeliveryRequest:
    body: bytes
    action = AssignedDeliveryAction.DELIVER
    path = ASSIGNED_DELIVERY_PATH


@dataclass(frozen=True, slots=True)
class VerifiedDeliveryCredential:
    nonce: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class VerifiedAuthControlCredential:
    issuer: ServiceName
    nonce: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class VerifiedPlatformCredential:
    issuer: ServiceName
    assignment_id: UUID
    nonce: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PlatformCredentialLimits:
    max_ttl: timedelta
    clock_skew: timedelta
    max_body_bytes: int
    max_token_bytes: int

    def __post_init__(self) -> None:
        if self.max_ttl < timedelta(seconds=1) or self.clock_skew < timedelta(0):
            raise ValueError("invalid Platform credential lifetime limits")
        if self.max_body_bytes <= 0 or self.max_token_bytes <= 0:
            raise ValueError("invalid Platform credential byte limits")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(encoded: str) -> bytes:
    data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    if _encode(data) != encoded:
        raise ValueError("noncanonical base64url")
    return data


type RequestToSign = PlatformRequest | AuthControlRequest | AssignedDeliveryRequest


def _bound_claims(request: RequestToSign) -> dict[str, str]:
    return {"action": request.action.value, "method": "POST", "path": request.path,
            "bodySha256": hashlib.sha256(request.body).hexdigest()}


class _RequestSigner:
    def __init__(
        self, key: Ed25519PrivateKey, limits: PlatformCredentialLimits, *, clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._key, self._limits, self._clock = key, limits, clock

    def _issue(self, request: RequestToSign, ttl: timedelta, issuer: ServiceName, audience: str, extra: dict[str, str]) -> str:
        if not timedelta(seconds=1) <= ttl <= self._limits.max_ttl or len(request.body) > self._limits.max_body_bytes:
            raise ValueError("request exceeds Platform credential limits")
        now = self._clock()
        claims = {
            "iss": issuer.value, "aud": audience,
            "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp()), "nonce": str(uuid4()),
            **extra, **_bound_claims(request),
        }
        payload = _encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signed = f"{_PREFIX}.{payload}"
        token = f"{signed}.{_encode(self._key.sign(_DOMAIN + signed.encode('ascii')))}"
        if len(token) > self._limits.max_token_bytes:
            raise ValueError("request exceeds Platform credential limits")
        return token


class PlatformCredentialIssuer(_RequestSigner):
    def issue(self, request: PlatformRequest, *, assignment_id: UUID, ttl: timedelta) -> str:
        return self._issue(request, ttl, ServiceName.MANAGER_RUNTIME, _AUDIENCE, {"assignmentId": str(assignment_id)})


class AuthControlCredentialIssuer(_RequestSigner):
    def issue(self, request: AuthControlRequest, *, ttl: timedelta) -> str:
        return self._issue(request, ttl, ServiceName.TEMPORAL_AUTH_CONTROL, _AUTH_CONTROL_AUDIENCE, {})


class AssignedDeliveryCredentialIssuer(_RequestSigner):
    def issue(self, request: AssignedDeliveryRequest, *, ttl: timedelta) -> str:
        return self._issue(request, ttl, ServiceName.OUTBOX_DISPATCHER, _DELIVERY_AUDIENCE, {})


class PlatformCredentialVerifier:
    def __init__(
        self, keys: Sequence[Ed25519PublicKey], limits: PlatformCredentialLimits,
        *, auth_control_keys: Sequence[Ed25519PublicKey] = (), delivery_keys: Sequence[Ed25519PublicKey] = (),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._keys, self._auth_control_keys = tuple(keys), tuple(auth_control_keys)
        self._delivery_keys = tuple(delivery_keys)
        self._limits, self._clock = limits, clock

    def matches_transport(
        self, token: str, request: RequestToSign, *, received_method: str, received_path: bytes, received_query: bytes,
    ) -> bool:
        return (
            0 < len(token) <= self._limits.max_token_bytes and token.isascii()
            and received_method == "POST" and received_path == request.path.encode("ascii") and not received_query
        )

    def verify(
        self, token: str, request: PlatformRequest, *, received_method: str, received_path: bytes, received_query: bytes,
    ) -> VerifiedPlatformCredential | None:
        if not self.matches_transport(token, request, received_method=received_method, received_path=received_path, received_query=received_query):
            return None
        claims = self._decode_claims(token, self._keys, request, extra=frozenset({"assignmentId"}))
        if claims is None or claims["iss"] != ServiceName.MANAGER_RUNTIME.value or claims["aud"] != _AUDIENCE:
            return None
        try:
            nonce, expires_at = self._lifetime(claims)
            assignment = _canonical_uuid(claims["assignmentId"])
        except (ValueError, TypeError, OverflowError, OSError):
            return None
        return VerifiedPlatformCredential(ServiceName.MANAGER_RUNTIME, assignment, nonce, expires_at)

    def verify_auth_control(
        self, token: str, request: AuthControlRequest, *, received_method: str, received_path: bytes, received_query: bytes,
    ) -> VerifiedAuthControlCredential | None:
        if not self.matches_transport(token, request, received_method=received_method, received_path=received_path, received_query=received_query):
            return None
        claims = self._decode_claims(token, self._auth_control_keys, request, extra=frozenset())
        if claims is None or claims["iss"] != ServiceName.TEMPORAL_AUTH_CONTROL.value or claims["aud"] != _AUTH_CONTROL_AUDIENCE:
            return None
        try:
            nonce, expires_at = self._lifetime(claims)
        except (ValueError, TypeError, OverflowError, OSError):
            return None
        return VerifiedAuthControlCredential(ServiceName.TEMPORAL_AUTH_CONTROL, nonce, expires_at)

    def verify_delivery(
        self, token: str, request: AssignedDeliveryRequest, *, received_method: str, received_path: bytes, received_query: bytes,
    ) -> VerifiedDeliveryCredential | None:
        if not self.matches_transport(token, request, received_method=received_method, received_path=received_path, received_query=received_query):
            return None
        claims = self._decode_claims(token, self._delivery_keys, request, extra=frozenset())
        if claims is None or claims["iss"] != ServiceName.OUTBOX_DISPATCHER.value or claims["aud"] != _DELIVERY_AUDIENCE:
            return None
        try:
            nonce, expires_at = self._lifetime(claims)
        except (ValueError, TypeError, OverflowError, OSError):
            return None
        return VerifiedDeliveryCredential(nonce, expires_at)

    def _decode_claims(
        self, token: str, keys: Sequence[Ed25519PublicKey], request: RequestToSign, *, extra: frozenset[str],
    ) -> dict[str, Any] | None:
        if len(request.body) > self._limits.max_body_bytes:
            return None
        try:
            prefix, payload, signature = token.split(".")
            if prefix != _PREFIX:
                return None
            signed = _DOMAIN + f"{prefix}.{payload}".encode("ascii")
            if not _valid_signature(keys, signed, _decode(signature)):
                return None
            claims = json.loads(_decode(payload).decode("utf-8"), object_pairs_hook=_unique)
            if (not isinstance(claims, dict) or set(claims) != _CLAIMS | extra
                    or any(claims[name] != expected for name, expected in _bound_claims(request).items())):
                return None
            return claims
        except (ValueError, TypeError, OverflowError, OSError):
            return None

    def _lifetime(self, claims: dict[str, Any]) -> tuple[UUID, datetime]:
        issued, expiry = claims["iat"], claims["exp"]
        now = self._clock().timestamp()
        if (type(issued) is not int or type(expiry) is not int or now >= expiry
                or not 0 < expiry - issued <= self._limits.max_ttl.total_seconds()
                or issued > now + self._limits.clock_skew.total_seconds()):
            raise ValueError("invalid credential lifetime")
        nonce = _canonical_uuid(claims["nonce"])
        if nonce.version != 4:
            raise ValueError("invalid credential nonce")
        return nonce, datetime.fromtimestamp(expiry, UTC)


def _valid_signature(keys: Sequence[Ed25519PublicKey], signed: bytes, signature: bytes) -> bool:
    for key in keys:
        try:
            key.verify(signature, signed)
        except InvalidSignature:
            continue
        return True
    return False


def _canonical_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("reference must be a UUID string")
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError("reference must be a canonical UUID string")
    return parsed
