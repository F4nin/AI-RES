"""Deterministic structural validation; semantic completeness and human approval stay separate."""
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from ai_res.modules.rules.language import Condition, parse_condition
from ai_res.modules.rules.types import EffectKind, FactSchema, RuleLevel, RuleScope, RuleSnapshot, RuleStatus


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validation_basis_fingerprint(schema: FactSchema, basis: Sequence[RuleSnapshot]) -> str:
    """Lifecycle/approval changes invalidate publication validation even when rule content is unchanged."""
    ordered = sorted(basis, key=lambda item: str(item.version_id))
    if len({item.version_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate basis version")
    return _hash({"schema": schema.to_dict(), "rules": [item.to_dict() for item in ordered]})


def _normalized(condition: Condition) -> Any:
    data = condition.to_dict()
    if condition.children:
        children = [_normalized(child) for child in condition.children]
        if condition.op in ("all", "any"):
            children.sort(key=lambda child: json.dumps(child, sort_keys=True))
        data["children"] = children
    return data


def _overlaps(first: RuleScope, second: RuleScope) -> bool:
    return all(a is None or b is None or a == b for a, b in (
        (first.organization_id, second.organization_id), (first.project_id, second.project_id),
        (first.object_type, second.object_type), (first.object_id, second.object_id), (first.operation, second.operation)))


def _fields(condition: Condition) -> set[str]:
    return ({condition.field} if condition.field is not None else set()) | {name for child in condition.children for name in _fields(child)}


def _opposed(first: RuleSnapshot, second: RuleSnapshot) -> bool:
    requires = {item.target for item in first.effects if item.kind is EffectKind.REQUIRE}
    forbids = {item.target for item in first.effects if item.kind is EffectKind.FORBID}
    return bool(requires & {item.target for item in second.effects if item.kind is EffectKind.FORBID}
                or forbids & {item.target for item in second.effects if item.kind is EffectKind.REQUIRE})


def _scope(rule: RuleSnapshot) -> RuleScope:
    return rule.scope if rule.object_type is None else replace(rule.scope, object_type=rule.object_type)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    proposal_content_hash: str
    schema_content_hash: str
    basis_fingerprint: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    exact_duplicates: tuple[UUID, ...]
    near_duplicates: tuple[UUID, ...]
    conflicting_rules: tuple[UUID, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def content_hash(self) -> str:
        return _hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": "1.0", "proposalContentHash": self.proposal_content_hash, "schemaContentHash": self.schema_content_hash,
                "basisFingerprint": self.basis_fingerprint, "valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings),
                "exactDuplicates": [str(item) for item in self.exact_duplicates], "nearDuplicates": [str(item) for item in self.near_duplicates],
                "conflictingRules": [str(item) for item in self.conflicting_rules]}

    @classmethod
    def from_dict(cls, value: Any) -> "ValidationReport":
        expected = {"schemaVersion", "proposalContentHash", "schemaContentHash", "basisFingerprint", "valid", "errors", "warnings",
                    "exactDuplicates", "nearDuplicates", "conflictingRules"}
        if not isinstance(value, dict) or set(value) != expected or value["schemaVersion"] != "1.0":
            raise ValueError("invalid validation report")
        for name in ("proposalContentHash", "schemaContentHash", "basisFingerprint"):
            if not isinstance(value[name], str) or len(value[name]) != 64:
                raise ValueError("invalid validation hash")
            bytes.fromhex(value[name])
        for name in ("errors", "warnings", "exactDuplicates", "nearDuplicates", "conflictingRules"):
            if not isinstance(value[name], list) or any(not isinstance(item, str) for item in value[name]):
                raise ValueError("invalid validation list")
        result = cls(value["proposalContentHash"], value["schemaContentHash"], value["basisFingerprint"], tuple(value["errors"]),
                     tuple(value["warnings"]), tuple(UUID(x) for x in value["exactDuplicates"]), tuple(UUID(x) for x in value["nearDuplicates"]),
                     tuple(UUID(x) for x in value["conflictingRules"]))
        if type(value["valid"]) is not bool or result.to_dict() != value:
            raise ValueError("invalid validation report consistency")
        return result


def validate_rule(proposal: RuleSnapshot, schema: FactSchema, basis: Sequence[RuleSnapshot]) -> ValidationReport:
    errors: set[str] = set()
    warnings: set[str] = set()
    exact: set[UUID] = set()
    near: set[UUID] = set()
    conflicts: set[UUID] = set()
    if _fields(proposal.condition) - {field.name for field in schema.fields}:
        errors.add("UNKNOWN_FACT_FIELD")
    try:
        parse_condition(proposal.condition.to_dict(), schema)
    except ValueError:
        errors.add("INVALID_CONDITION")
    own_requires = {item.target for item in proposal.effects if item.kind is EffectKind.REQUIRE}
    own_forbids = {item.target for item in proposal.effects if item.kind is EffectKind.FORBID}
    if own_requires & own_forbids:
        errors.add("RULE_EFFECT_CONFLICT")
    for effect in proposal.effects:
        if effect.kind is EffectKind.ALLOW_EXCEPTION:
            targets = [item for item in basis if item.key == effect.target and _overlaps(_scope(item), _scope(proposal))]
            if not targets:
                errors.add("UNKNOWN_EXCEPTION_TARGET")
            if any(item.scope.level is RuleLevel.SYSTEM or item.scope.level <= proposal.scope.level for item in targets):
                errors.add("SYSTEM_OVERRIDE_FORBIDDEN")
    for other in basis:
        if other.rule_id == proposal.rule_id or other.scope.level > proposal.scope.level or not _overlaps(_scope(other), _scope(proposal)):
            continue
        same_condition = proposal.condition.to_dict() == other.condition.to_dict()
        same_effects = set(proposal.effects) == set(other.effects)
        if _scope(proposal) == _scope(other) and same_effects and other.status not in (RuleStatus.RETIRED, RuleStatus.REJECTED):
            if same_condition:
                errors.add("EXACT_DUPLICATE")
                exact.add(other.version_id)
            elif _normalized(proposal.condition) == _normalized(other.condition):
                errors.add("STRUCTURAL_NEAR_DUPLICATE")
                near.add(other.version_id)
        if other.status is RuleStatus.APPROVED and _opposed(proposal, other):
            if _normalized(proposal.condition) == _normalized(other.condition):
                errors.add("RULE_EFFECT_CONFLICT")
                conflicts.add(other.version_id)
            else:
                warnings.add("POTENTIAL_CONFLICT_REQUIRES_HUMAN_REVIEW")
    return ValidationReport(proposal.content_hash, schema.content_hash, validation_basis_fingerprint(schema, basis), tuple(sorted(errors)),
                            tuple(sorted(warnings)), tuple(sorted(exact, key=str)), tuple(sorted(near, key=str)), tuple(sorted(conflicts, key=str)))
