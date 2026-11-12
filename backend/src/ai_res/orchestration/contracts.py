"""Compact Workflow/Activity contracts (API Contracts v1.10 §9.1, §9.2, §9.4, §9.5).

Everything that enters Temporal history is an opaque id, a short code or a version number - never a document, prompt, secret or evidence payload.
`assert_compact` enforces that at the boundary where the application builds a Temporal payload; the replay/history scan test enforces it on what Temporal
actually recorded. The contract version is a MAJOR number: an unsupported major fails closed (never a silent downgrade).
"""
from dataclasses import asdict, dataclass, fields
from typing import Any
from uuid import UUID

from ai_res.platform.redaction import assert_no_sensitive_keys

CONTRACT_VERSION = 1
SUPPORTED_CONTRACT_MAJORS = frozenset({1})
MANAGER_TASK_QUEUE = "ai-res-manager"
WORKER_TASK_QUEUE = "ai-res-workers"
OPERATION_WORKFLOW_TYPE = "OperationWorkflow"
MAX_REF_LEN = 64  # ids and codes only: a longer value is not a reference
SKELETON_FAILURE_CODE = "ORCHESTRATION_NOT_IMPLEMENTED"


class ContractError(ValueError):
    """A payload that is not a valid compact reference. Permanent: retrying the same input cannot succeed."""


def workflow_id_for(operation_id: UUID) -> str:
    """Stable, deterministic Workflow ID derived from the Operation ID (Decision v1.6 §2.5, Spec v1.13 rule 2). It is a correlation reference, not a key."""
    if not isinstance(operation_id, UUID):
        raise TypeError("operation_id must be a UUID")
    return f"operation-{operation_id}"


def _uuid_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_REF_LEN:
        raise ContractError(f"{name} must be a UUID string")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ContractError(f"{name} must be a canonical lower-case UUID string") from None
    return value


def _short_code(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REF_LEN or not value.replace("_", "").isalnum() or not value.isupper():
        raise ContractError(f"{name} must be an upper-case machine code of at most {MAX_REF_LEN} characters")
    return value


@dataclass(frozen=True)
class OperationRef:
    """Which Operation, in which tenant scope. The scope is a CLAIM of the caller: the Platform API proves it against the stored row (never trusted alone)."""
    operation_id: str
    organization_id: str
    project_id: str

    def __post_init__(self) -> None:
        for f in fields(self):
            _uuid_text(f.name, getattr(self, f.name))


@dataclass(frozen=True)
class OperationWorkflowInput:
    contract_version: int
    operation: OperationRef
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.contract_version, int) or isinstance(self.contract_version, bool) or self.contract_version not in SUPPORTED_CONTRACT_MAJORS:
            raise ContractError("unsupported workflow contract major version")  # fail closed
        if not isinstance(self.operation, OperationRef):
            raise ContractError("operation must be an OperationRef")
        _uuid_text("correlation_id", self.correlation_id)

    @classmethod
    def create(cls, operation_id: UUID, organization_id: UUID, project_id: UUID, correlation_id: UUID) -> "OperationWorkflowInput":
        return cls(CONTRACT_VERSION, OperationRef(str(operation_id), str(organization_id), str(project_id)), str(correlation_id))


@dataclass(frozen=True)
class OperationState:
    """What an Activity returns about the domain Operation: its status only (the domain row stays in PostgreSQL)."""
    operation_id: str
    status: str

    def __post_init__(self) -> None:
        _uuid_text("operation_id", self.operation_id)
        _short_code("status", self.status)


@dataclass(frozen=True)
class OperationFailure:
    operation: OperationRef
    code: str

    def __post_init__(self) -> None:
        _short_code("code", self.code)


@dataclass(frozen=True)
class OperationWorkflowResult:
    outcome: str  # SKELETON_FAILED_CLOSED | NOT_RUNNING | CANCELLED_CONFIRMED | CANCEL_PENDING
    status: str  # the domain status the workflow last observed

    def __post_init__(self) -> None:
        _short_code("outcome", self.outcome)
        _short_code("status", self.status)


def assert_compact(payload: Any) -> None:
    """Refuses a payload whose keys look like content or secrets, and any value that is not a short scalar (no nested documents)."""
    data = asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload
    assert_no_sensitive_keys(data)

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for item in v.values():
                walk(item)
        elif isinstance(v, str):
            if len(v) > MAX_REF_LEN:
                raise ContractError("a Temporal payload may carry references and codes only")
        elif not isinstance(v, int):
            raise ContractError("a Temporal payload may carry strings and integers only")

    walk(data)


# Outbox destination of the Operation start command (S11). The accepted-event of an Operation that must be orchestrated lists it next to the domain destination.
START_DESTINATION = "orchestration.operation-start"
# Outbox destination of the cancellation command (S12): the Workflow gets a signal; the domain decides CANCELLED only after reconciliation (Decision v1.6 §2.4).
CANCEL_DESTINATION = "orchestration.operation-cancel"
CANCEL_SIGNAL = "request_cancel"
