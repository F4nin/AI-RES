"""S18 typed snapshots and bounded declarative rule language."""
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from ai_res.modules.rules.language import Condition, parse_condition, parse_definition, parse_effects
from ai_res.modules.rules.types import (
    EffectKind,
    EvaluationScope,
    FactField,
    FactSchema,
    FactSnapshot,
    FactType,
    ImpactClass,
    RuleEffect,
    RuleException,
    RuleLevel,
    RuleScope,
    RuleSnapshot,
    RuleStatus,
)

ORG, PROJECT, OBJECT, VERSION, ACTOR = (UUID(int=n) for n in range(1, 6))
NOW = datetime(2026, 11, 17, tzinfo=UTC)
CONTEXT_HASH = "ab" * 32
SCHEMA = FactSchema("1.0", (FactField("count", FactType.INT), FactField("ready", FactType.BOOL),
                          FactField("score", FactType.NUMBER), FactField("kind", FactType.CODE)))


def definition() -> dict[str, Any]:
    return {"schemaVersion": "1.0", "condition": {"op": "eq", "field": "ready", "value": True}, "effects": [{"kind": "REQUIRE", "target": "QA_CHECK"}]}


def rule() -> RuleSnapshot:
    parsed = parse_definition(definition(), SCHEMA)
    return RuleSnapshot(OBJECT, VERSION, 1, "require.qa", RuleScope(RuleLevel.PROJECT, ORG, PROJECT), parsed.condition, parsed.effects,
                        RuleStatus.APPROVED, approved_by=ACTOR, approved_at=NOW, valid_from=NOW, valid_to=NOW + timedelta(days=1))


def test_fact_snapshots_are_typed_immutable_canonical_and_roundtrip() -> None:
    facts = FactSnapshot(OBJECT, 1, VERSION, (("ready", True), ("count", 2)), CONTEXT_HASH)
    SCHEMA.validate(facts)
    assert facts == FactSnapshot(OBJECT, 1, VERSION, (("count", 2), ("ready", True)), CONTEXT_HASH)
    assert FactSnapshot.from_dict(facts.to_dict()) == facts
    assert len(facts.content_hash) == 64
    with pytest.raises(KeyError):
        facts.get("missing")
    with pytest.raises(FrozenInstanceError):
        facts.version = 2  # type: ignore[misc]
    exported = facts.to_dict()
    exported["values"]["ready"] = False
    assert facts.get("ready") is True


@pytest.mark.parametrize(("field", "value"), [("count", True), ("count", 1.2), ("ready", 1), ("score", True), ("score", float("nan")),
                                               ("score", float("inf")), ("kind", "free text secret"), ("unknown", True)])
def test_schema_rejects_wrong_types_and_untrusted_fields(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        SCHEMA.validate(FactSnapshot(OBJECT, 1, VERSION, ((field, value),), CONTEXT_HASH))


@pytest.mark.parametrize("changes", [{"version": True}, {"id": str(OBJECT)}, {"context_id": None}, {"values": []},
                                      {"values": (("ready", True), ("ready", False))}, {"schema_version": "2.0"}])
def test_fact_snapshot_invariants(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(FactSnapshot(OBJECT, 1, VERSION, (("ready", True),), CONTEXT_HASH), **changes)


def test_every_safe_operator_parses_to_immutable_ast() -> None:
    for op in ("eq", "ne", "lt", "le", "gt", "ge"):
        cond = parse_condition({"op": op, "field": "count", "value": 2}, SCHEMA)
        assert cond.op == op and cond.field == "count" and cond.value == 2
    child = {"op": "exists", "field": "ready"}
    for op in ("all", "any"):
        cond = parse_condition({"op": op, "children": [child]}, SCHEMA)
        assert cond.children[0].op == "exists"
    cond = parse_condition({"op": "not", "children": [child]}, SCHEMA)
    with pytest.raises(FrozenInstanceError):
        cond.op = "eq"  # type: ignore[misc]
    assert parse_condition(cond.to_dict(), SCHEMA) == cond


@pytest.mark.parametrize("payload", [
    {"op": "exec", "code": "untrusted"}, {"op": "eq", "field": "ready", "value": 1},
    {"op": "lt", "field": "ready", "value": True}, {"op": "eq", "field": "unknown", "value": True},
    {"op": "eq", "field": "count", "value": True}, {"op": "exists", "field": "ready", "value": True},
    {"op": "all", "children": []}, {"op": "not", "children": []}, {"op": "not", "children": [{"op": "exists", "field": "ready"}] * 2},
    {"op": "all", "children": [{"op": "exists", "field": "ready"}], "code": "untrusted"},
])
def test_language_rejects_unknown_fields_types_and_unsafe_operators(payload: Any) -> None:
    with pytest.raises(ValueError):
        parse_condition(payload, SCHEMA)


def test_language_bounds_recursive_depth_and_total_nodes() -> None:
    payload: dict[str, Any] = {"op": "exists", "field": "ready"}
    for _ in range(16):
        payload = {"op": "not", "children": [payload]}
    with pytest.raises(ValueError):
        parse_condition(payload, SCHEMA)
    with pytest.raises(ValueError):
        parse_condition({"op": "all", "children": [{"op": "exists", "field": "ready"}] * 256}, SCHEMA)


def test_definition_hash_and_effects_are_stable_and_strict() -> None:
    parsed = parse_definition(definition(), SCHEMA)
    assert parse_definition(parsed.to_dict(), SCHEMA) == parsed
    assert len(parsed.content_hash) == 64
    assert RuleEffect.from_dict({"kind": "MINIMUM_IMPACT", "impact": "I4_CRITICAL"}).impact is ImpactClass.I4_CRITICAL
    assert RuleEffect(EffectKind.ALLOW_EXCEPTION, target="project.qa").target == "project.qa"
    with pytest.raises(ValueError):
        RuleEffect.from_dict({"kind": "ALLOW_ACCESS", "target": "anything"})
    with pytest.raises(ValueError):
        parse_definition({**definition(), "schemaVersion": "2.0"}, SCHEMA)
    with pytest.raises(ValueError):
        parse_definition({**definition(), "effects": []}, SCHEMA)


def test_hierarchy_scope_covers_only_its_explicit_tenant_and_object() -> None:
    scope = EvaluationScope(ORG, PROJECT, "ARTIFACT", OBJECT, "artifact.publish")
    assert RuleScope(RuleLevel.SYSTEM).covers(scope)
    assert RuleScope(RuleLevel.ORGANIZATION, ORG).covers(scope)
    assert RuleScope(RuleLevel.PROJECT, ORG, PROJECT).covers(scope)
    assert not RuleScope(RuleLevel.PROJECT, ORG, VERSION).covers(scope)
    assert not RuleScope(RuleLevel.PROJECT, ORG, PROJECT, "SOURCE").covers(scope)
    assert not RuleScope(RuleLevel.PROJECT, ORG, PROJECT, operation="artifact.generate").covers(scope)
    assert RuleScope.from_dict(RuleScope(RuleLevel.PROJECT, ORG, PROJECT).to_dict()) == RuleScope(RuleLevel.PROJECT, ORG, PROJECT)
    with pytest.raises(ValueError):
        RuleScope(RuleLevel.SYSTEM, ORG)
    with pytest.raises(ValueError):
        RuleScope(RuleLevel.PROJECT, ORG)


def test_approval_expiry_and_lifecycle_do_not_rewrite_immutable_rule_content() -> None:
    active = rule()
    assert active.is_active(NOW)
    assert not active.is_active(NOW - timedelta(seconds=1))
    assert not active.is_active(NOW + timedelta(days=1))
    assert not replace(active, status=RuleStatus.DRAFT).is_active(NOW)
    assert not replace(active, suspended=True).is_active(NOW)
    assert replace(active, status=RuleStatus.RETIRED).content_hash == active.content_hash
    assert replace(active, approved_by=OBJECT).content_hash == active.content_hash
    assert RuleSnapshot.from_dict(active.to_dict(), SCHEMA) == active
    assert active.definition_hash == parse_definition(definition(), SCHEMA).content_hash
    with pytest.raises(ValueError):
        replace(active, approved_by=None)
    with pytest.raises(ValueError):
        replace(active, version_number=True)
    with pytest.raises(ValueError):
        replace(active, valid_to=NOW)


def test_exception_is_exact_finite_human_approved_and_reproducible() -> None:
    target = rule()
    scope = EvaluationScope(ORG, PROJECT, "ARTIFACT", OBJECT, "artifact.publish")
    exc = RuleException(OBJECT, target.version_id, target.content_hash, target.effects[0].content_hash, VERSION, scope,
                        NOW, NOW + timedelta(days=1), ACTOR, NOW, "APPROVED_EXCEPTION", (VERSION,), (OBJECT,))
    assert exc.is_active(NOW)
    assert not exc.is_active(NOW + timedelta(days=1))
    assert not replace(exc, revoked_at=NOW).is_active(NOW)
    assert RuleException.from_dict(exc.to_dict()) == exc
    with pytest.raises(ValueError):
        replace(exc, valid_to=None)
    with pytest.raises(ValueError):
        replace(exc, approved_by=None)
    with pytest.raises(ValueError):
        replace(exc, risk_refs=[])


def test_schema_serialization_is_detached_and_field_order_canonical() -> None:
    assert FactSchema.from_dict(SCHEMA.to_dict()) == SCHEMA
    assert FactSchema(SCHEMA.version, tuple(reversed(SCHEMA.fields))).content_hash == SCHEMA.content_hash
    payload = SCHEMA.to_dict()
    payload["fields"][0]["type"] = "CODE"
    assert FactSchema.from_dict(payload) != SCHEMA
    with pytest.raises(ValueError):
        FactSchema("1.0", (FactField("duplicate", FactType.INT), FactField("duplicate", FactType.INT)))


@pytest.mark.parametrize("payload", [None, [], {"schemaVersion": "1.0", "fields": []},
                                      {"schemaVersion": "2.0", "fields": [{"name": "count", "type": "INT"}]},
                                      {"schemaVersion": "1.0", "fields": [{"name": "count", "type": "UNKNOWN"}]}])
def test_invalid_fact_schema_deserialization(payload: Any) -> None:
    with pytest.raises(ValueError):
        FactSchema.from_dict(payload)


@pytest.mark.parametrize("changes", [{"contextHash": "z" * 64}, {"version": True}, {"version": 0}, {"providerVersion": "free text"},
                                      {"schemaVersion": "2.0"}, {"values": {"context.secret": True}}, {"values": []}, {"unexpected": True}])
def test_fact_deserialization_rejects_unsafe_shapes(changes: dict[str, Any]) -> None:
    payload = FactSnapshot(OBJECT, 1, VERSION, (("ready", True),), CONTEXT_HASH).to_dict()
    payload.update(changes)
    with pytest.raises(ValueError):
        FactSnapshot.from_dict(payload)


def test_false_zero_and_missing_facts_remain_distinct() -> None:
    facts = FactSnapshot(OBJECT, 1, VERSION, (("count", 0), ("ready", False)), CONTEXT_HASH)
    SCHEMA.validate(facts)
    assert facts.get("ready") is False and facts.get("count") == 0
    with pytest.raises(KeyError):
        facts.get("unknown")
    SCHEMA.validate(FactSnapshot(OBJECT, 1, VERSION, (("score", 1.5), ("kind", "SOURCE")), CONTEXT_HASH))


@pytest.mark.parametrize("scope", [RuleScope(RuleLevel.SYSTEM), RuleScope(RuleLevel.ORGANIZATION, ORG), RuleScope(RuleLevel.PROJECT, ORG, PROJECT)])
def test_rule_scope_covers_only_its_bounds_and_roundtrips(scope: RuleScope) -> None:
    subject = EvaluationScope(ORG, PROJECT, "CONTEXT_PACKAGE_VERSION", OBJECT, "CONTEXT_ASSESSMENT")
    assert scope.covers(subject)
    assert RuleScope.from_dict(scope.to_dict()) == scope
    assert not replace(scope, operation="OTHER_OPERATION").covers(subject)
    assert not replace(scope, object_type="ARTIFACT").covers(subject)
    if scope.level is not RuleLevel.SYSTEM:
        assert not scope.covers(replace(subject, organization_id=OBJECT))
    if scope.level is RuleLevel.PROJECT:
        assert not scope.covers(replace(subject, project_id=OBJECT))


@pytest.mark.parametrize("arguments", [
    (RuleLevel.SYSTEM, ORG), (RuleLevel.ORGANIZATION,), (RuleLevel.ORGANIZATION, ORG, PROJECT), (RuleLevel.PROJECT, ORG), (0,),
])
def test_scope_level_cannot_disagree_with_tenant(arguments: tuple[Any, ...]) -> None:
    with pytest.raises(ValueError):
        RuleScope(*arguments)


def test_effect_shorthand_normalizes_to_canonical_impact_and_has_no_policy_grant() -> None:
    assert RuleEffect.from_dict({"kind": "MINIMUM_IMPACT", "impact": "I4"}) == RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I4_CRITICAL)
    effect = RuleEffect(EffectKind.REQUIRE, "QA_CHECK")
    assert effect.as_dict() == effect.to_dict()
    for payload in ({"kind": "REQUIRE", "target": "free text"}, {"kind": "REQUIRE", "target": "QA_CHECK", "grant": True},
                    {"kind": "MINIMUM_IMPACT", "target": "QA_CHECK"}, {"kind": "MINIMUM_IMPACT", "impact": "I5"}):
        with pytest.raises(ValueError):
            RuleEffect.from_dict(payload)
    with pytest.raises(ValueError):
        parse_effects([effect.to_dict(), effect.to_dict()])


def test_condition_constructor_cannot_hide_mutable_values_or_exceed_bounds() -> None:
    with pytest.raises(ValueError):
        Condition("eq", "kind", ["MUTABLE"])  # type: ignore[arg-type]
    exact = {"op": "all", "children": [{"op": "exists", "field": "ready"}] * 255}
    assert len(parse_condition(exact, SCHEMA).children) == 255
    payload: dict[str, Any] = {"op": "exists", "field": "ready"}
    for _ in range(15):
        payload = {"op": "not", "children": [payload]}
    assert parse_condition(payload, SCHEMA).op == "not"


@pytest.mark.parametrize("status", [RuleStatus.DRAFT, RuleStatus.PROPOSED, RuleStatus.REJECTED, RuleStatus.RETIRED])
def test_only_published_approved_rules_apply_even_when_approval_is_present(status: RuleStatus) -> None:
    assert not replace(rule(), status=status).is_active(NOW)


def test_activation_expiry_and_approval_time_are_explicit_and_exclusive() -> None:
    snapshot = rule()
    assert snapshot.is_active(NOW)
    assert not snapshot.is_active(NOW - timedelta(seconds=1))
    assert not snapshot.is_active(NOW + timedelta(days=1))
    assert not replace(snapshot, suspended=True).is_active(NOW)
    assert not replace(snapshot, approved_at=NOW + timedelta(seconds=1)).is_active(NOW)
    with pytest.raises(ValueError):
        snapshot.is_active(NOW.replace(tzinfo=None))


def test_snapshot_content_identity_excludes_lifecycle_but_serialization_retains_it() -> None:
    snapshot = rule()
    retired = replace(snapshot, status=RuleStatus.RETIRED, suspended=True)
    assert retired.content_hash == snapshot.content_hash
    assert retired.to_dict() != snapshot.to_dict()
    assert RuleSnapshot.from_dict(snapshot.to_dict(), SCHEMA) == snapshot
    assert replace(snapshot, key="other.key").content_hash != snapshot.content_hash
    assert replace(snapshot, object_type="ARTIFACT").content_hash != snapshot.content_hash
    assert replace(snapshot, key="other.key").definition_hash == snapshot.definition_hash
    payload = snapshot.to_dict()
    payload["definition"]["effects"][0]["target"] = "OTHER"
    assert snapshot.effects[0].target == "QA_CHECK"


@pytest.mark.parametrize("changes", [{"approved_by": None}, {"approved_at": None}, {"valid_from": None}, {"suspended": 1},
                                      {"effects": []}, {"effects": ()}, {"author_type": "UNKNOWN"}, {"valid_from": NOW.replace(tzinfo=None)},
                                      {"object_type": "free text"}, {"version_number": True}])
def test_rule_snapshot_invalid_states_are_unrepresentable(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(rule(), **changes)


@pytest.mark.parametrize("changes", [{"schemaVersion": "2.0"}, {"status": "ACTIVE"}, {"objectType": []}, {"unexpected": True},
                                      {"approvedAt": "untrusted"}, {"approvedBy": ACTOR}])
def test_rule_snapshot_deserialization_rejects_invalid_fields(changes: dict[str, Any]) -> None:
    payload = rule().to_dict()
    payload.update(changes)
    with pytest.raises(ValueError):
        RuleSnapshot.from_dict(payload, SCHEMA)


@pytest.mark.parametrize("credential", ["ghp_" + "x" * 24, "AKIA" + "A" * 16, "password:" + "test_value"],
                         ids=["github-shape", "aws-shape", "assignment-shape"])
def test_credential_shaped_codes_are_rejected_without_echoing_value(credential: str) -> None:
    with pytest.raises(ValueError) as fact_error:
        FactSnapshot(OBJECT, 1, VERSION, (("kind", credential),), CONTEXT_HASH)
    with pytest.raises(ValueError) as effect_error:
        RuleEffect(EffectKind.REQUIRE, target=credential)
    with pytest.raises(ValueError) as key_error:
        replace(rule(), key=credential)
    assert all(credential not in str(error.value) for error in (fact_error, effect_error, key_error))
