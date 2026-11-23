"""Backend-owned definitions and invocation scope for the internal Tool Gateway."""
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator
from referencing import Registry

from ai_res.platform.ports import ServiceName

type JsonObject = dict[str, Any]

_TOOL_ID = re.compile(r"[a-z][a-z0-9_.-]{0,95}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?")


class ToolErrorCode(StrEnum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    APPROVAL_REQUIRED = "approval_required"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    EXECUTION = "execution"
    RATE_LIMIT = "rate_limit"
    CONFLICT = "conflict"


class ToolError(Exception):
    def __init__(self, code: ToolErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class ToolKind(StrEnum):
    LOCAL = "local"
    API = "api"
    MCP = "mcp"


class SideEffect(StrEnum):
    NONE = "none"
    DOMAIN_WRITE = "domain_write"


class ToolStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    DEPRECATED = "deprecated"


@dataclass(frozen=True, slots=True)
class ToolRef:
    tool_id: str
    version: str

    def __post_init__(self) -> None:
        if not _TOOL_ID.fullmatch(self.tool_id) or not _VERSION.fullmatch(self.version):
            raise ValueError("tool references require an exact version")


@dataclass(frozen=True, slots=True)
class ToolLimits:
    timeout_seconds: float
    input_bytes: int
    output_bytes: int
    calls_per_minute: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be finite and positive")
        if any(type(value) is not int or value <= 0 for value in
               (self.input_bytes, self.output_bytes, self.calls_per_minute)):
            raise ValueError("tool limits must be positive integers")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolDefinition:
    ref: ToolRef
    contract_version: str
    name: str
    description: str
    owner: str
    provider: str
    adapter_id: str
    kind: ToolKind
    operation: str
    resource_type: str
    stateful: bool
    side_effect: SideEffect
    risk: str
    required_scope: str
    worker_types: frozenset[str]
    classifications: frozenset[str]
    environments: frozenset[str]
    input_schema: str
    output_schema: str
    limits: ToolLimits
    requires_human_approval: bool = False
    status: ToolStatus = ToolStatus.ACTIVE
    network_destinations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not _VERSION.fullmatch(self.contract_version):
            raise ValueError("invalid tool contract version")
        if self.side_effect is SideEffect.DOMAIN_WRITE and (self.kind is not ToolKind.LOCAL or not self.stateful):
            raise ValueError("only transactional local domain writes can have side effects")
        if self.side_effect is SideEffect.NONE and self.operation not in {"read", "validate"}:
            raise ValueError("invalid operation for a tool without side effects")
        if self.kind is ToolKind.LOCAL and self.network_destinations:
            raise ValueError("local tools cannot declare network destinations")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSubject:
    """Supplied only by a trusted backend entry point after transport authentication and run binding."""
    organization_id: UUID
    project_id: UUID
    epic_id: UUID
    task_id: UUID
    run_id: UUID
    worker_definition_version_id: UUID
    worker_type: str
    service: ServiceName
    identity_id: UUID
    identity_expires_at: datetime
    environment: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolTarget:
    """Resource and classification resolved by Backend, outside the model-supplied argument object."""
    resource_type: str
    resource_id: UUID
    classification: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    ref: ToolRef
    contract_version: str
    operation: str
    grant_id: UUID
    target: ToolTarget
    idempotency_key: str | None = None


def compile_schema(encoded: str) -> Draft202012Validator:
    schema = json.loads(encoded)
    if not isinstance(schema, dict) or schema.get("type") != "object" or "$schema" in schema:
        raise ValueError("tool schemas must be Draft 2020-12 object schemas")
    Draft202012Validator.check_schema(schema)
    # The empty registry permits in-document references and provides no network retrieval.
    return Draft202012Validator(schema, registry=Registry(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def validated_object(value: object, validator: Draft202012Validator, byte_limit: int, error: ToolErrorCode) -> JsonObject:
    if not isinstance(value, dict):
        raise ToolError(error)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > byte_limit:
            raise ToolError(error)
        snapshot: JsonObject = json.loads(encoded)
        if not validator.is_valid(snapshot):
            raise ToolError(error)
    except ToolError:
        raise
    except Exception:
        # Schema resolution and serialization failures must not disclose arguments or adapter output.
        raise ToolError(error) from None
    return snapshot
