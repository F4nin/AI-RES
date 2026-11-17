"""Pure rules evaluation over complete, trusted snapshots; a result is never an access grant."""
import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from ai_res.modules.rules.language import Condition
from ai_res.modules.rules.types import (
    EffectKind,
    EvaluationScope,
    FactSnapshot,
    ImpactClass,
    RuleException,
    RuleLevel,
    RuleSnapshot,
)

ENGINE_VERSION = "1.0"
_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _time(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("evaluation time must be UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _uuid(value: Any) -> UUID:
    if not isinstance(value, str):
        raise ValueError("identifier must be a UUID string")
    return UUID(value)


def _tuple_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected a string list")
    return tuple(value)


class EvaluationStatus(StrEnum):
    PASS = "pass"  # noqa: S105 -- canonical evaluation status, not a credential
    PASS_WITH_OBLIGATIONS = "pass_with_obligations"  # noqa: S105 -- canonical status
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    INSUFFICIENT_DATA = "insufficient_data"


class TriState(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ConditionResult:
    outcome: TriState
    missing: tuple[str, ...] = ()


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and (not isinstance(value, float) or math.isfinite(value))


def evaluate_condition(condition: Condition, facts: FactSnapshot) -> ConditionResult:
    """Three-valued logic. Explicit existence checks distinguish absence from an unknown comparison."""
    op = condition.op
    if op in ("all", "any", "not"):
        if not condition.children or (op == "not" and len(condition.children) != 1):
            raise ValueError("invalid logical condition")
        children = tuple(evaluate_condition(child, facts) for child in condition.children)
        outcomes = {child.outcome for child in children}
        missing = tuple(sorted({name for child in children for name in child.missing}))
        if op == "not":
            return ConditionResult({TriState.TRUE: TriState.FALSE, TriState.FALSE: TriState.TRUE,
                                    TriState.UNKNOWN: TriState.UNKNOWN}[children[0].outcome], missing)
        decisive = TriState.FALSE if op == "all" else TriState.TRUE
        if decisive in outcomes:
            return ConditionResult(decisive)
        if TriState.UNKNOWN in outcomes:
            return ConditionResult(TriState.UNKNOWN, missing)
        return ConditionResult(TriState.TRUE if op == "all" else TriState.FALSE)
    if op not in ("eq", "ne", "lt", "le", "gt", "ge", "exists") or condition.field is None:
        raise ValueError("unknown condition operator")
    try:
        actual = facts.get(condition.field)
    except KeyError:
        return ConditionResult(TriState.FALSE) if op == "exists" else ConditionResult(TriState.UNKNOWN, (condition.field,))
    if op == "exists":
        return ConditionResult(TriState.TRUE)
    expected = condition.value
    comparable = (type(actual) is type(expected)) or (_is_number(actual) and _is_number(expected))
    if not comparable or ((op not in ("eq", "ne")) and not (_is_number(actual) and _is_number(expected))):
        return ConditionResult(TriState.UNKNOWN, (condition.field,))
    if op == "eq":
        matched = actual == expected
    elif op == "ne":
        matched = actual != expected
    elif op == "lt":
        matched = cast("int | float", actual) < cast("int | float", expected)
    elif op == "le":
        matched = cast("int | float", actual) <= cast("int | float", expected)
    elif op == "gt":
        matched = cast("int | float", actual) > cast("int | float", expected)
    else:
        matched = cast("int | float", actual) >= cast("int | float", expected)
    return ConditionResult(TriState.TRUE if matched else TriState.FALSE)


@dataclass(frozen=True, slots=True)
class RuleReference:
    rule_id: UUID
    version_id: UUID
    version_number: int
    content_hash: str

    def __post_init__(self) -> None:
        if (not isinstance(self.rule_id, UUID) or not isinstance(self.version_id, UUID)
                or type(self.version_number) is not int or self.version_number < 1
                or not isinstance(self.content_hash, str) or _HASH.fullmatch(self.content_hash) is None):
            raise ValueError("invalid exact rule reference")

    @classmethod
    def of(cls, rule: RuleSnapshot) -> "RuleReference":
        return cls(rule.rule_id, rule.version_id, rule.version_number, rule.content_hash)

    def to_dict(self) -> dict[str, Any]:
        return {"ruleId": str(self.rule_id), "versionId": str(self.version_id), "versionNumber": self.version_number,
                "contentHash": self.content_hash}

    @classmethod
    def from_dict(cls, value: Any) -> "RuleReference":
        if not isinstance(value, dict) or set(value) != {"ruleId", "versionId", "versionNumber", "contentHash"}:
            raise ValueError("invalid rule reference")
        if type(value["versionNumber"]) is not int or value["versionNumber"] < 1:
            raise ValueError("invalid rule version")
        if not isinstance(value["contentHash"], str) or len(value["contentHash"]) != 64:
            raise ValueError("invalid rule content hash")
        bytes.fromhex(value["contentHash"])
        return cls(_uuid(value["ruleId"]), _uuid(value["versionId"]), value["versionNumber"], value["contentHash"])


@dataclass(frozen=True, slots=True)
class WaivedEffect:
    exception_id: UUID
    rule_version_id: UUID
    effect_hash: str

    def __post_init__(self) -> None:
        if (not isinstance(self.exception_id, UUID) or not isinstance(self.rule_version_id, UUID)
                or not isinstance(self.effect_hash, str) or _HASH.fullmatch(self.effect_hash) is None):
            raise ValueError("invalid waived effect")

    def to_dict(self) -> dict[str, str]:
        return {"exceptionId": str(self.exception_id), "ruleVersionId": str(self.rule_version_id), "effectHash": self.effect_hash}


@dataclass(frozen=True, slots=True)
class RuleConflict:
    target: str
    required_by: tuple[UUID, ...]
    forbidden_by: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or _CODE.fullmatch(self.target) is None:
            raise ValueError("invalid conflict target")
        for refs in (self.required_by, self.forbidden_by):
            if not isinstance(refs, tuple) or not refs or any(not isinstance(item, UUID) for item in refs) or len(set(refs)) != len(refs):
                raise ValueError("invalid conflict references")

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "requiredBy": [str(item) for item in self.required_by],
                "forbiddenBy": [str(item) for item in self.forbidden_by]}


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    scope: EvaluationScope
    as_of: datetime
    fact_snapshot_id: UUID
    fact_version: int
    fact_content_hash: str
    considered: tuple[RuleReference, ...]
    applied: tuple[RuleReference, ...]
    matched: tuple[RuleReference, ...]
    waived: tuple[WaivedEffect, ...]
    conflicts: tuple[RuleConflict, ...]
    missing: tuple[str, ...]
    obligations: tuple[str, ...]
    restrictions: tuple[str, ...]
    escalations: tuple[str, ...]
    minimum_impact_class: ImpactClass | None
    status: EvaluationStatus
    explanation: tuple[str, ...]
    exception_reasons: tuple[tuple[UUID, str], ...]

    def __post_init__(self) -> None:
        _time(self.as_of)
        if (not isinstance(self.scope, EvaluationScope) or not isinstance(self.fact_snapshot_id, UUID)
                or type(self.fact_version) is not int or self.fact_version < 1
                or not isinstance(self.fact_content_hash, str) or _HASH.fullmatch(self.fact_content_hash) is None
                or not isinstance(self.status, EvaluationStatus)
                or (self.minimum_impact_class is not None and not isinstance(self.minimum_impact_class, ImpactClass))):
            raise ValueError("invalid evaluation metadata")
        for refs in (self.considered, self.applied, self.matched):
            if (not isinstance(refs, tuple) or any(not isinstance(item, RuleReference) for item in refs)
                    or len({item.version_id for item in refs}) != len(refs)):
                raise ValueError("invalid result rule references")
        if not set(self.matched) <= set(self.applied) <= set(self.considered):
            raise ValueError("result rule subsets disagree")
        for values in (self.missing, self.obligations, self.restrictions, self.escalations, self.explanation):
            if not isinstance(values, tuple) or any(not isinstance(item, str) or _CODE.fullmatch(item) is None for item in values):
                raise ValueError("invalid result machine codes")
        if not isinstance(self.waived, tuple) or any(not isinstance(item, WaivedEffect) for item in self.waived):
            raise ValueError("invalid waiver list")
        if not isinstance(self.conflicts, tuple) or any(not isinstance(item, RuleConflict) for item in self.conflicts):
            raise ValueError("invalid conflict list")
        if not isinstance(self.exception_reasons, tuple):
            raise ValueError("exception reasons must be immutable")
        for pair in self.exception_reasons:
            if (not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], UUID)
                    or not isinstance(pair[1], str) or _CODE.fullmatch(pair[1]) is None):
                raise ValueError("invalid exception reason")
        if bool(self.conflicts) != (self.status is EvaluationStatus.CONFLICT):
            raise ValueError("conflict status mismatch")
        if self.restrictions and self.status not in (EvaluationStatus.CONFLICT, EvaluationStatus.BLOCKED):
            raise ValueError("forbidden effect cannot pass")
        if self.status is EvaluationStatus.BLOCKED and not self.restrictions:
            raise ValueError("blocked result requires a restriction")
        if self.missing and self.status in (EvaluationStatus.PASS, EvaluationStatus.PASS_WITH_OBLIGATIONS):
            raise ValueError("unknown facts cannot pass")

    def to_dict(self) -> dict[str, Any]:
        return {
            "engineVersion": ENGINE_VERSION,
            "scope": {"organizationId": str(self.scope.organization_id), "projectId": str(self.scope.project_id),
                      "objectType": self.scope.object_type, "objectId": str(self.scope.object_id), "operation": self.scope.operation},
            "asOf": _time(self.as_of),
            "factSnapshotId": str(self.fact_snapshot_id), "factVersion": self.fact_version, "factContentHash": self.fact_content_hash,
            "considered": [item.to_dict() for item in self.considered], "applied": [item.to_dict() for item in self.applied],
            "matched": [item.to_dict() for item in self.matched], "waived": [item.to_dict() for item in self.waived],
            "conflicts": [item.to_dict() for item in self.conflicts], "missing": list(self.missing), "obligations": list(self.obligations),
            "restrictions": list(self.restrictions), "escalations": list(self.escalations),
            "minimumImpactClass": None if self.minimum_impact_class is None else self.minimum_impact_class.value,
            "status": self.status.value, "explanation": list(self.explanation),
            "exceptionReasons": [{"exceptionId": str(item), "reason": reason} for item, reason in self.exception_reasons],
        }

    @property
    def content_hash(self) -> str:
        return _hash(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "EvaluationResult":
        fields = {"engineVersion", "scope", "asOf", "factSnapshotId", "factVersion", "factContentHash", "considered", "applied", "matched",
                  "waived", "conflicts", "missing", "obligations", "restrictions", "escalations", "minimumImpactClass", "status", "explanation",
                  "exceptionReasons"}
        if not isinstance(value, dict) or set(value) != fields or value["engineVersion"] != ENGINE_VERSION:
            raise ValueError("invalid evaluation result version or fields")
        try:
            scope = value["scope"]
            if not isinstance(scope, dict) or set(scope) != {"organizationId", "projectId", "objectType", "objectId", "operation"}:
                raise ValueError("invalid result scope")
            parsed_scope = EvaluationScope(_uuid(scope["organizationId"]), _uuid(scope["projectId"]), scope["objectType"],
                                           _uuid(scope["objectId"]), scope["operation"])
            at = datetime.fromisoformat(value["asOf"])
            _time(at)
            waived = tuple(WaivedEffect(_uuid(item["exceptionId"]), _uuid(item["ruleVersionId"]), item["effectHash"]) for item in value["waived"])
            conflicts = tuple(RuleConflict(item["target"], tuple(_uuid(x) for x in item["requiredBy"]),
                                           tuple(_uuid(x) for x in item["forbiddenBy"])) for item in value["conflicts"])
            result = cls(parsed_scope, at, _uuid(value["factSnapshotId"]), value["factVersion"], value["factContentHash"],
                         tuple(RuleReference.from_dict(x) for x in value["considered"]),
                         tuple(RuleReference.from_dict(x) for x in value["applied"]), tuple(RuleReference.from_dict(x) for x in value["matched"]),
                         waived, conflicts, _tuple_strings(value["missing"]), _tuple_strings(value["obligations"]),
                         _tuple_strings(value["restrictions"]), _tuple_strings(value["escalations"]),
                         None if value["minimumImpactClass"] is None else ImpactClass(value["minimumImpactClass"]),
                         EvaluationStatus(value["status"]), _tuple_strings(value["explanation"]),
                         tuple((_uuid(item["exceptionId"]), item["reason"]) for item in value["exceptionReasons"]))
            if result.to_dict() != value:
                raise ValueError("noncanonical result")
            return result
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("invalid evaluation result") from exc


def _exception_reason(exception: RuleException, target: RuleSnapshot, permission: RuleSnapshot | None,
                      facts: FactSnapshot, scope: EvaluationScope, at: datetime) -> str | None:
    if target.scope.level is RuleLevel.SYSTEM:
        return "SYSTEM_OVERRIDE_FORBIDDEN"
    if exception.scope != scope:
        return "EXCEPTION_SCOPE_MISMATCH"
    if exception.revoked_at is not None and exception.revoked_at <= at:
        return "EXCEPTION_REVOKED"
    if at >= exception.valid_to:
        return "EXCEPTION_EXPIRED"
    if at < exception.valid_from or exception.approved_at > at:
        return "EXCEPTION_NOT_EFFECTIVE"
    if exception.target_content_hash != target.content_hash or exception.target_effect_hash not in {x.content_hash for x in target.effects}:
        return "EXCEPTION_TARGET_CHANGED"
    if (permission is None or not permission.is_active(at) or not permission.scope.covers(scope)
            or (permission.object_type is not None and permission.object_type != scope.object_type)):
        return "EXCEPTION_PERMISSION_UNAVAILABLE"
    if permission.scope.level >= target.scope.level:
        return "EXCEPTION_PERMISSION_NOT_HIGHER"
    if not any(effect.kind is EffectKind.ALLOW_EXCEPTION and effect.target == target.key for effect in permission.effects):
        return "EXCEPTION_PERMISSION_MISMATCH"
    if evaluate_condition(permission.condition, facts).outcome is not TriState.TRUE:
        return "EXCEPTION_PERMISSION_NOT_MATCHED"
    for parent in (target, permission):
        if parent.valid_from is None or exception.valid_from < parent.valid_from:
            return "EXCEPTION_INTERVAL_EXCEEDS_RULE"
        if parent.valid_to is not None and exception.valid_to > parent.valid_to:
            return "EXCEPTION_INTERVAL_EXCEEDS_RULE"
    return None


def evaluate_rules(rules: Sequence[RuleSnapshot], facts: FactSnapshot, scope: EvaluationScope, as_of: datetime,
                   exceptions: Sequence[RuleException] = ()) -> EvaluationResult:
    """Live callers select the complete registry and server time; historical calls only reproduce evidence."""
    _time(as_of)
    ordered = tuple(sorted(rules, key=lambda item: str(item.version_id)))
    if len({item.version_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate rule version snapshot")
    if len({item.id for item in exceptions}) != len(exceptions):
        raise ValueError("duplicate exception snapshot")
    by_id = {item.version_id: item for item in ordered}
    applied = tuple(item for item in ordered if item.is_active(as_of) and item.scope.covers(scope)
                    and (item.object_type is None or item.object_type == scope.object_type))
    if len({item.rule_id for item in applied}) != len(applied):
        raise ValueError("multiple active versions of one rule")
    conditions = {item.version_id: evaluate_condition(item.condition, facts) for item in applied}
    matched = tuple(item for item in applied if conditions[item.version_id].outcome is TriState.TRUE)
    missing = tuple(sorted({name for result in conditions.values() for name in result.missing}))
    reasons: list[tuple[UUID, str]] = []
    waivers: dict[tuple[UUID, str], UUID] = {}
    for exception in sorted(exceptions, key=lambda item: str(item.id)):
        target = by_id.get(exception.target_version_id)
        if target is None or target not in matched:
            reasons.append((exception.id, "EXCEPTION_TARGET_UNAVAILABLE"))
            continue
        reason = _exception_reason(exception, target, by_id.get(exception.permission_version_id), facts, scope, as_of)
        if reason is not None:
            reasons.append((exception.id, reason))
            continue
        key = (target.version_id, exception.target_effect_hash)
        if key in waivers:
            reasons.append((exception.id, "EXCEPTION_ALREADY_WAIVED"))
        else:
            waivers[key] = exception.id
    required: dict[str, set[UUID]] = {}
    forbidden: dict[str, set[UUID]] = {}
    escalations: set[str] = set()
    impacts: list[ImpactClass] = []
    mandatory = any(effect.kind is not EffectKind.ALLOW_EXCEPTION for item in matched for effect in item.effects)
    for item in matched:
        for effect in item.effects:
            if (item.version_id, effect.content_hash) in waivers:
                continue
            if effect.kind is EffectKind.ALLOW_EXCEPTION:
                continue
            if effect.kind is EffectKind.REQUIRE and effect.target is not None:
                required.setdefault(effect.target, set()).add(item.version_id)
            elif effect.kind is EffectKind.FORBID and effect.target is not None:
                forbidden.setdefault(effect.target, set()).add(item.version_id)
            elif effect.kind is EffectKind.ESCALATE and effect.target is not None:
                escalations.add(effect.target)
            elif effect.kind is EffectKind.MINIMUM_IMPACT and effect.impact is not None:
                impacts.append(effect.impact)
            else:
                raise ValueError("unsupported rule effect")
    conflicts = tuple(RuleConflict(target, tuple(sorted(required[target], key=str)), tuple(sorted(forbidden[target], key=str)))
                      for target in sorted(required.keys() & forbidden.keys()))
    if conflicts:
        status, explanation = EvaluationStatus.CONFLICT, ("RULE_EFFECT_CONFLICT",)
    elif forbidden:
        status, explanation = EvaluationStatus.BLOCKED, ("RULE_FORBIDS_OPERATION",)
    elif missing or not mandatory:
        status, explanation = EvaluationStatus.INSUFFICIENT_DATA, ("REQUIRED_FACTS_MISSING" if missing else "NO_MANDATORY_RULE_MATCHED",)
    elif required or escalations or any(item is not ImpactClass.I0_NO_IMPACT for item in impacts):
        status, explanation = EvaluationStatus.PASS_WITH_OBLIGATIONS, ("MANDATORY_RULE_OBLIGATIONS",)
    else:
        status, explanation = EvaluationStatus.PASS, ("EXPLICIT_RULES_WITHOUT_OBLIGATIONS",)
    return EvaluationResult(scope, as_of, facts.id, facts.version, facts.content_hash, tuple(RuleReference.of(x) for x in ordered),
                            tuple(RuleReference.of(x) for x in applied), tuple(RuleReference.of(x) for x in matched),
                            tuple(WaivedEffect(exception, version, effect) for (version, effect), exception in
                                  sorted(waivers.items(), key=lambda x: (str(x[0][0]), x[0][1]))),
                            conflicts, missing, tuple(sorted(required)), tuple(sorted(forbidden)), tuple(sorted(escalations)),
                            max(impacts, key=lambda x: list(ImpactClass).index(x)) if impacts else None, status, explanation, tuple(reasons))
