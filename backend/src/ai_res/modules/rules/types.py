"""Strict immutable facts, scopes and rule snapshots; no business catalogue or grants."""
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Self
from uuid import UUID

from ai_res.platform.redaction import scan_secrets

if TYPE_CHECKING:
    from ai_res.modules.rules.language import Condition, RuleDefinition

type Scalar = bool | int | float | str
_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_FIELD = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _code(value: object) -> bool:
    return isinstance(value, str) and _CODE.fullmatch(value) is not None and not scan_secrets(value).found


def _hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _utc(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _shape(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != keys:
        raise ValueError("unsupported snapshot fields")
    return value


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("identifier must be a UUID string")
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("invalid identifier") from None


def _dt(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be a UTC string")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid UTC timestamp") from None
    if not _utc(result):
        raise ValueError("timestamp must be UTC")
    return result


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _enum[T: StrEnum](cls: type[T], value: object) -> T:
    if not isinstance(value, str):
        raise ValueError("invalid enum value")
    try:
        return cls(value)
    except ValueError:
        raise ValueError("unsupported enum value") from None


def _scalar(value: object) -> bool:
    return type(value) in (bool, int) or (type(value) is float and math.isfinite(value)) or _code(value)


class FactType(StrEnum):
    BOOL = "BOOL"
    INT = "INT"
    NUMBER = "NUMBER"
    CODE = "CODE"


def value_matches(value: object, kind: FactType) -> bool:
    if kind is FactType.BOOL:
        return type(value) is bool
    if kind is FactType.INT:
        return type(value) is int
    if kind is FactType.NUMBER:
        return type(value) is int or (type(value) is float and math.isfinite(value))
    return kind is FactType.CODE and _code(value)


@dataclass(frozen=True, slots=True)
class FactField:
    name: str
    type: FactType

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _FIELD.fullmatch(self.name) is None or not isinstance(self.type, FactType):
            raise ValueError("invalid fact field")


@dataclass(frozen=True, slots=True)
class FactSchema:
    version: str
    fields: tuple[FactField, ...]

    def __post_init__(self) -> None:
        if self.version != "1.0" or not isinstance(self.fields, tuple) or not self.fields or any(not isinstance(f, FactField) for f in self.fields):
            raise ValueError("invalid fact schema")
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ValueError("duplicate fact field")
        object.__setattr__(self, "fields", tuple(sorted(self.fields, key=lambda f: f.name)))

    def field_type(self, name: str) -> FactType:
        for field in self.fields:
            if field.name == name:
                return field.type
        raise ValueError("unknown fact field")

    def validate(self, facts: "FactSnapshot") -> None:
        if not isinstance(facts, FactSnapshot) or facts.schema_version != self.version:
            raise ValueError("fact schema mismatch")
        for name, value in facts.values:
            if not value_matches(value, self.field_type(name)):
                raise ValueError("fact value type mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": self.version, "fields": [{"name": f.name, "type": f.type.value} for f in self.fields]}

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _shape(value, {"schemaVersion", "fields"})
        if not isinstance(data["fields"], list):
            raise ValueError("fact fields must be an array")
        fields = []
        for raw in data["fields"]:
            field = _shape(raw, {"name", "type"})
            fields.append(FactField(field["name"], _enum(FactType, field["type"])))
        return cls(data["schemaVersion"], tuple(fields))


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    id: UUID
    version: int
    context_id: UUID
    values: tuple[tuple[str, Scalar], ...]
    context_hash: str
    provider_version: str = "context-metadata-v1"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.context_id, UUID) or type(self.version) is not int or self.version <= 0:
            raise ValueError("invalid fact identity")
        if not _hash(self.context_hash) or not _code(self.provider_version) or self.schema_version != "1.0":
            raise ValueError("invalid fact provenance")
        if not isinstance(self.values, tuple):
            raise ValueError("fact values must be immutable pairs")
        for pair in self.values:
            if not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str) or _FIELD.fullmatch(pair[0]) is None or not _scalar(pair[1]):
                raise ValueError("invalid fact value")
        if len({pair[0] for pair in self.values}) != len(self.values):
            raise ValueError("duplicate fact name")
        object.__setattr__(self, "values", tuple(sorted(self.values)))

    def get(self, name: str) -> Scalar:
        for field, value in self.values:
            if field == name:
                return value
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": self.schema_version, "id": str(self.id), "version": self.version, "contextId": str(self.context_id),
                "contextHash": self.context_hash, "providerVersion": self.provider_version, "values": dict(self.values)}

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _shape(value, {"schemaVersion", "id", "version", "contextId", "contextHash", "providerVersion", "values"})
        if not isinstance(data["values"], dict):
            raise ValueError("fact values must be an object")
        return cls(_uuid(data["id"]), data["version"], _uuid(data["contextId"]), tuple(data["values"].items()),
                   data["contextHash"], data["providerVersion"], data["schemaVersion"])


class RuleLevel(IntEnum):
    SYSTEM = 0
    ORGANIZATION = 1
    ORG = 1
    PROJECT = 2


@dataclass(frozen=True, slots=True)
class EvaluationScope:
    organization_id: UUID
    project_id: UUID
    object_type: str
    object_id: UUID
    operation: str

    def __post_init__(self) -> None:
        if (any(not isinstance(v, UUID) for v in (self.organization_id, self.project_id, self.object_id))
                or not _code(self.object_type) or not _code(self.operation)):
            raise ValueError("invalid evaluation scope")

    def to_dict(self) -> dict[str, Any]:
        return {"organizationId": str(self.organization_id), "projectId": str(self.project_id), "objectType": self.object_type,
                "objectId": str(self.object_id), "operation": self.operation}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _shape(value, {"organizationId", "projectId", "objectType", "objectId", "operation"})
        return cls(_uuid(data["organizationId"]), _uuid(data["projectId"]), data["objectType"], _uuid(data["objectId"]), data["operation"])


@dataclass(frozen=True, slots=True)
class RuleScope:
    level: RuleLevel
    organization_id: UUID | None = None
    project_id: UUID | None = None
    object_type: str | None = None
    object_id: UUID | None = None
    operation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.level, RuleLevel):
            raise ValueError("invalid rule level")
        for identifier in (self.organization_id, self.project_id, self.object_id):
            if identifier is not None and not isinstance(identifier, UUID):
                raise ValueError("invalid rule scope identifier")
        if (self.level is RuleLevel.SYSTEM and (self.organization_id is not None or self.project_id is not None)
                or self.level is RuleLevel.ORGANIZATION and (self.organization_id is None or self.project_id is not None)
                or self.level is RuleLevel.PROJECT and (self.organization_id is None or self.project_id is None)):
            raise ValueError("rule level and tenant scope disagree")
        if (any(value is not None and not _code(value) for value in (self.object_type, self.operation))
                or self.object_id is not None and self.object_type is None):
            raise ValueError("invalid rule applicability")

    def covers(self, scope: EvaluationScope) -> bool:
        return (isinstance(scope, EvaluationScope) and all(expected is None or expected == actual for expected, actual in (
            (self.organization_id, scope.organization_id), (self.project_id, scope.project_id), (self.object_type, scope.object_type),
            (self.object_id, scope.object_id), (self.operation, scope.operation))))

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level.name, "organizationId": None if self.organization_id is None else str(self.organization_id),
                "projectId": None if self.project_id is None else str(self.project_id), "objectType": self.object_type,
                "objectId": None if self.object_id is None else str(self.object_id), "operation": self.operation}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _shape(value, {"level", "organizationId", "projectId", "objectType", "objectId", "operation"})
        if data["level"] not in ("SYSTEM", "ORGANIZATION", "PROJECT"):
            raise ValueError("unsupported rule level")
        return cls(RuleLevel[data["level"]], None if data["organizationId"] is None else _uuid(data["organizationId"]),
                   None if data["projectId"] is None else _uuid(data["projectId"]), data["objectType"],
                   None if data["objectId"] is None else _uuid(data["objectId"]), data["operation"])


class RuleStatus(StrEnum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class ImpactClass(StrEnum):
    I0_NO_IMPACT = "I0_NO_IMPACT"
    I1_LOCAL = "I1_LOCAL"
    I2_DEPENDENT = "I2_DEPENDENT"
    I3_BROAD = "I3_BROAD"
    I4_CRITICAL = "I4_CRITICAL"
    I0 = "I0_NO_IMPACT"
    I1 = "I1_LOCAL"
    I2 = "I2_DEPENDENT"
    I3 = "I3_BROAD"
    I4 = "I4_CRITICAL"


class EffectKind(StrEnum):
    REQUIRE = "REQUIRE"
    FORBID = "FORBID"
    ESCALATE = "ESCALATE"
    MINIMUM_IMPACT = "MINIMUM_IMPACT"
    MINIMUM_IMPACT_CLASS = "MINIMUM_IMPACT"
    ALLOW_EXCEPTION = "ALLOW_EXCEPTION"


@dataclass(frozen=True, slots=True)
class RuleEffect:
    kind: EffectKind
    target: str | None = None
    impact: ImpactClass | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EffectKind):
            raise ValueError("invalid effect kind")
        if self.kind is EffectKind.MINIMUM_IMPACT:
            if self.target is not None or not isinstance(self.impact, ImpactClass):
                raise ValueError("impact effect requires an exact impact class")
        elif not _code(self.target) or self.impact is not None:
            raise ValueError("effect requires a bounded target code")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, **({"impact": self.impact.value} if self.impact is not None else {"target": self.target})}

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict):
            raise ValueError("effect must be an object")
        kind = _enum(EffectKind, value.get("kind"))
        data = _shape(value, {"kind", "impact"} if kind is EffectKind.MINIMUM_IMPACT else {"kind", "target"})
        if kind is EffectKind.MINIMUM_IMPACT:
            value = data["impact"]
            if isinstance(value, str) and value in ("I0", "I1", "I2", "I3", "I4"):
                value = ImpactClass[value].value
            return cls(kind, impact=_enum(ImpactClass, value))
        return cls(kind, target=data["target"])


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    rule_id: UUID
    version_id: UUID
    version_number: int
    key: str
    scope: RuleScope
    condition: "Condition"
    effects: tuple[RuleEffect, ...]
    status: RuleStatus
    author_type: str = "USER"
    author_id: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    suspended: bool = False
    object_type: str | None = None

    def __post_init__(self) -> None:
        from ai_res.modules.rules.language import Condition
        if not isinstance(self.rule_id, UUID) or not isinstance(self.version_id, UUID) or type(self.version_number) is not int or self.version_number < 1:
            raise ValueError("invalid rule identity")
        if not _code(self.key) or not isinstance(self.scope, RuleScope) or not isinstance(self.condition, Condition) or not isinstance(self.status, RuleStatus):
            raise ValueError("invalid rule snapshot")
        if not isinstance(self.effects, tuple) or not self.effects or any(not isinstance(e, RuleEffect) for e in self.effects):
            raise ValueError("rule effects must be a nonempty immutable tuple")
        if len(set(self.effects)) != len(self.effects):
            raise ValueError("duplicate rule effects")
        if self.author_type not in ("USER", "MANAGER", "WORKER_RUN", "IMPORT") or type(self.suspended) is not bool:
            raise ValueError("invalid rule author or suspension flag")
        if self.object_type is not None and (not _code(self.object_type) or self.scope.object_type not in (None, self.object_type)):
            raise ValueError("invalid or contradictory object type applicability")
        if any(v is not None and not isinstance(v, UUID) for v in (self.author_id, self.approved_by)):
            raise ValueError("invalid author or approver identifier")
        if any(v is not None and not _utc(v) for v in (self.approved_at, self.valid_from, self.valid_to)):
            raise ValueError("rule timestamps must be UTC")
        approval = (self.approved_by, self.approved_at, self.valid_from)
        if any(v is not None for v in approval) and not all(v is not None for v in approval):
            raise ValueError("approval facts must be complete")
        if self.status in (RuleStatus.APPROVED, RuleStatus.RETIRED) and self.approved_by is None:
            raise ValueError("published rule requires human approval facts")
        if self.valid_to is not None and (self.valid_from is None or self.valid_to <= self.valid_from):
            raise ValueError("invalid rule validity interval")
        object.__setattr__(self, "effects", tuple(sorted(set(self.effects), key=lambda e: e.content_hash)))

    @property
    def rule_key(self) -> str:
        return self.key

    @property
    def definition(self) -> "RuleDefinition":
        from ai_res.modules.rules.language import RuleDefinition
        return RuleDefinition(self.condition, self.effects)

    @property
    def definition_hash(self) -> str:
        return self.definition.content_hash

    @property
    def content_hash(self) -> str:
        return canonical_hash({k: v for k, v in self.to_dict().items()
                               if k not in ("status", "approvedBy", "approvedAt", "validFrom", "validTo", "suspended")})

    def is_active(self, at: datetime) -> bool:
        if not _utc(at):
            raise ValueError("evaluation time must be UTC")
        return (self.status is RuleStatus.APPROVED and not self.suspended and self.approved_by is not None
                and self.approved_at is not None and self.approved_at <= at and self.valid_from is not None and self.valid_from <= at
                and (self.valid_to is None or at < self.valid_to))

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": "1.0", "ruleId": str(self.rule_id), "versionId": str(self.version_id), "versionNumber": self.version_number,
                "key": self.key, "scope": self.scope.to_dict(), "definition": self.definition.to_dict(), "status": self.status.value,
                "authorType": self.author_type, "authorId": None if self.author_id is None else str(self.author_id),
                "approvedBy": None if self.approved_by is None else str(self.approved_by), "approvedAt": _iso(self.approved_at),
                "validFrom": _iso(self.valid_from), "validTo": _iso(self.valid_to), "suspended": self.suspended, "objectType": self.object_type}

    @classmethod
    def from_dict(cls, value: object, schema: FactSchema) -> Self:
        from ai_res.modules.rules.language import parse_definition
        data = _shape(value, {"schemaVersion", "ruleId", "versionId", "versionNumber", "key", "scope", "definition", "status", "authorType",
                              "authorId", "approvedBy", "approvedAt", "validFrom", "validTo", "suspended", "objectType"})
        if data["schemaVersion"] != "1.0":
            raise ValueError("unsupported rule snapshot version")
        definition = parse_definition(data["definition"], schema)
        return cls(_uuid(data["ruleId"]), _uuid(data["versionId"]), data["versionNumber"], data["key"], RuleScope.from_dict(data["scope"]),
                   definition.condition, definition.effects, _enum(RuleStatus, data["status"]), data["authorType"],
                   None if data["authorId"] is None else _uuid(data["authorId"]), None if data["approvedBy"] is None else _uuid(data["approvedBy"]),
                   _dt(data["approvedAt"]), _dt(data["validFrom"]), _dt(data["validTo"]), data["suspended"], data["objectType"])


@dataclass(frozen=True, slots=True)
class RuleException:
    id: UUID
    target_version_id: UUID
    target_content_hash: str
    target_effect_hash: str
    permission_version_id: UUID
    scope: EvaluationScope
    valid_from: datetime
    valid_to: datetime
    approved_by: UUID
    approved_at: datetime
    reason_code: str
    risk_refs: tuple[UUID, ...]
    compensation_refs: tuple[UUID, ...]
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(v, UUID) for v in (self.id, self.target_version_id, self.permission_version_id, self.approved_by)):
            raise ValueError("exception requires exact identities and human approval")
        if (not _hash(self.target_content_hash) or not _hash(self.target_effect_hash)
                or not isinstance(self.scope, EvaluationScope) or not _code(self.reason_code)):
            raise ValueError("invalid exception target or scope")
        if any(not _utc(v) for v in (self.valid_from, self.valid_to, self.approved_at)) or self.valid_to <= self.valid_from:
            raise ValueError("exception requires a finite UTC validity interval")
        if self.revoked_at is not None and not _utc(self.revoked_at):
            raise ValueError("invalid exception revocation time")
        for refs in (self.risk_refs, self.compensation_refs):
            if not isinstance(refs, tuple) or not refs or any(not isinstance(v, UUID) for v in refs) or len(set(refs)) != len(refs):
                raise ValueError("exception requires immutable risk and compensation references")

    @property
    def target_rule_hash(self) -> str:
        return self.target_content_hash

    @property
    def allowance_rule_version_id(self) -> UUID:
        return self.permission_version_id

    def is_active(self, at: datetime) -> bool:
        if not _utc(at):
            raise ValueError("evaluation time must be UTC")
        return self.approved_at <= at and self.valid_from <= at < self.valid_to and (self.revoked_at is None or at < self.revoked_at)

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": "1.0", "id": str(self.id), "targetVersionId": str(self.target_version_id), "targetContentHash": self.target_content_hash,
                "targetEffectHash": self.target_effect_hash, "permissionVersionId": str(self.permission_version_id), "scope": self.scope.to_dict(),
                "validFrom": _iso(self.valid_from), "validTo": _iso(self.valid_to), "approvedBy": str(self.approved_by), "approvedAt": _iso(self.approved_at),
                "reasonCode": self.reason_code, "riskRefs": [str(v) for v in self.risk_refs], "compensationRefs": [str(v) for v in self.compensation_refs],
                "revokedAt": _iso(self.revoked_at)}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _shape(value, {"schemaVersion", "id", "targetVersionId", "targetContentHash", "targetEffectHash", "permissionVersionId", "scope",
                              "validFrom", "validTo", "approvedBy", "approvedAt", "reasonCode", "riskRefs", "compensationRefs", "revokedAt"})
        if data["schemaVersion"] != "1.0" or not isinstance(data["riskRefs"], list) or not isinstance(data["compensationRefs"], list):
            raise ValueError("invalid exception format")
        start, end, approved = _dt(data["validFrom"]), _dt(data["validTo"]), _dt(data["approvedAt"])
        if start is None or end is None or approved is None:
            raise ValueError("exception timestamps are required")
        return cls(_uuid(data["id"]), _uuid(data["targetVersionId"]), data["targetContentHash"], data["targetEffectHash"], _uuid(data["permissionVersionId"]),
                   EvaluationScope.from_dict(data["scope"]), start, end, _uuid(data["approvedBy"]), approved, data["reasonCode"],
                   tuple(_uuid(v) for v in data["riskRefs"]), tuple(_uuid(v) for v in data["compensationRefs"]), _dt(data["revokedAt"]))


ExceptionSnapshot = RuleException
