"""Bounded typed JSON AST; no evaluation, code loading, I/O or permission grants."""
from dataclasses import dataclass
from typing import Any, Self

from ai_res.modules.rules.types import FactSchema, FactType, RuleEffect, Scalar, _scalar, canonical_hash, value_matches

MAX_DEPTH = 16
MAX_NODES = 256
_COMPARE = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_LOGICAL = frozenset({"all", "any", "not"})


@dataclass(frozen=True, slots=True)
class Condition:
    op: str
    field: str | None = None
    value: Scalar | None = None
    children: tuple["Condition", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.op, str) or self.op not in _COMPARE | _LOGICAL | {"exists"} or not isinstance(self.children, tuple):
            raise ValueError("invalid condition operator or children")
        if self.op in _LOGICAL:
            if self.field is not None or self.value is not None or not self.children or any(not isinstance(c, Condition) for c in self.children):
                raise ValueError("invalid logical condition")
            if self.op == "not" and len(self.children) != 1:
                raise ValueError("not requires exactly one child")
        elif not isinstance(self.field, str) or self.children or (self.op == "exists" and self.value is not None):
            raise ValueError("invalid field condition")
        elif self.op in _COMPARE and not _scalar(self.value):
            raise ValueError("comparison value is required")
        stack, count = [(self, 1)], 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > MAX_DEPTH or count > MAX_NODES:
                raise ValueError("condition technical bounds exceeded")
            stack.extend((child, depth + 1) for child in node.children)

    def to_dict(self) -> dict[str, Any]:
        if self.op in _LOGICAL:
            return {"op": self.op, "children": [child.to_dict() for child in self.children]}
        return {"op": self.op, "field": self.field, **({} if self.op == "exists" else {"value": self.value})}


def parse_condition(data: object, schema: FactSchema) -> Condition:
    """Parse a closed typed AST; bounds are technical safeguards, not business limits."""
    if not isinstance(schema, FactSchema):
        raise ValueError("fact schema is required")
    remaining = MAX_NODES

    def parse(raw: object, depth: int) -> Condition:
        nonlocal remaining
        remaining -= 1
        if depth > MAX_DEPTH or remaining < 0 or not isinstance(raw, dict):
            raise ValueError("condition shape or technical bounds exceeded")
        op = raw.get("op")
        if not isinstance(op, str) or op not in _COMPARE | _LOGICAL | {"exists"}:
            raise ValueError("unsupported condition operator")
        if op in _LOGICAL:
            if raw.keys() != {"op", "children"} or not isinstance(raw["children"], list) or not raw["children"]:
                raise ValueError("invalid logical condition fields")
            return Condition(op, children=tuple(parse(child, depth + 1) for child in raw["children"]))
        if raw.keys() != ({"op", "field"} if op == "exists" else {"op", "field", "value"}) or not isinstance(raw["field"], str):
            raise ValueError("invalid comparison condition fields")
        kind = schema.field_type(raw["field"])
        if op == "exists":
            return Condition(op, raw["field"])
        if not value_matches(raw["value"], kind) or (op not in ("eq", "ne") and kind not in (FactType.INT, FactType.NUMBER)):
            raise ValueError("comparison operand type mismatch")
        return Condition(op, raw["field"], raw["value"])

    return parse(data, 1)


def parse_effects(data: object) -> tuple[RuleEffect, ...]:
    if not isinstance(data, list) or not data or len(data) > MAX_NODES:
        raise ValueError("effects require a nonempty bounded array")
    effects = tuple(RuleEffect.from_dict(raw) for raw in data)
    if len(set(effects)) != len(effects):
        raise ValueError("duplicate effects")
    return tuple(sorted(effects, key=lambda effect: effect.content_hash))


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    condition: Condition
    effects: tuple[RuleEffect, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0" or not isinstance(self.condition, Condition) or not isinstance(self.effects, tuple) or not self.effects:
            raise ValueError("invalid rule definition")
        if any(not isinstance(effect, RuleEffect) for effect in self.effects) or len(set(self.effects)) != len(self.effects):
            raise ValueError("invalid or duplicate rule effects")
        object.__setattr__(self, "effects", tuple(sorted(self.effects, key=lambda effect: effect.content_hash)))

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": self.schema_version, "condition": self.condition.to_dict(), "effects": [effect.to_dict() for effect in self.effects]}

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.to_dict())

    @classmethod
    def from_dict(cls, data: object, schema: FactSchema) -> Self:
        if not isinstance(data, dict) or data.keys() != {"schemaVersion", "condition", "effects"} or data["schemaVersion"] != "1.0":
            raise ValueError("unsupported rule definition format")
        return cls(parse_condition(data["condition"], schema), parse_effects(data["effects"]))


def parse_definition(data: object, schema: FactSchema) -> RuleDefinition:
    return RuleDefinition.from_dict(data, schema)
