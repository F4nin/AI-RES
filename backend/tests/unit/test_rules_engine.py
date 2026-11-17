"""Deterministic rule decisions, exact waivers and reproducible validation bases."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from ai_res.modules.rules.engine import EvaluationResult, evaluate_rules
from ai_res.modules.rules.language import Condition
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
from ai_res.modules.rules.validation import ValidationReport, validate_rule

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)
ORG, PROJECT, OBJECT, HUMAN = (UUID(int=n) for n in range(1, 5))
SCOPE = EvaluationScope(ORG, PROJECT, "TASK", OBJECT, "ANALYZE")
FACTS = FactSnapshot(UUID(int=5), 1, UUID(int=6), (("enabled", True), ("amount", 2)), "a" * 64)
SCHEMA = FactSchema("1.0", (FactField("enabled", FactType.BOOL), FactField("amount", FactType.INT)))


def rule(n: int, effect: RuleEffect, *, level: RuleLevel = RuleLevel.SYSTEM, condition: Condition | None = None) -> RuleSnapshot:
    scope = RuleScope(level, ORG if level is not RuleLevel.SYSTEM else None, PROJECT if level is RuleLevel.PROJECT else None)
    return RuleSnapshot(UUID(int=100 + n), UUID(int=200 + n), 1, f"rule.{n}", scope,
                        condition or Condition("eq", "enabled", True), (effect,), RuleStatus.APPROVED,
                        approved_by=HUMAN, approved_at=NOW - timedelta(days=2), valid_from=NOW - timedelta(days=1),
                        valid_to=NOW + timedelta(days=2))


def waiver(target: RuleSnapshot, permission: RuleSnapshot, **changes) -> RuleException:
    return replace(RuleException(UUID(int=300), target.version_id, target.content_hash, target.effects[0].content_hash,
                                 permission.version_id, SCOPE, NOW - timedelta(hours=1), NOW + timedelta(hours=1),
                                 HUMAN, NOW - timedelta(hours=2), "TEST_EXCEPTION", (UUID(int=301),), (UUID(int=302),)), **changes)


def test_all_levels_accumulate_and_lower_rule_cannot_remove_system_obligation():
    system = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"))
    project = rule(2, RuleEffect(EffectKind.FORBID, "QA"), level=RuleLevel.PROJECT)
    result = evaluate_rules((system, project), FACTS, SCOPE, NOW)
    assert result.status.value == "conflict"
    assert result.obligations == result.restrictions == ("QA",)
    assert {x.version_id for x in result.matched} == {system.version_id, project.version_id}


def test_rule_input_order_does_not_change_result_or_hash():
    rules = (rule(1, RuleEffect(EffectKind.REQUIRE, "QA")), rule(2, RuleEffect(EffectKind.ESCALATE, "REVIEW")))
    forward = evaluate_rules(rules, FACTS, SCOPE, NOW)
    reverse = evaluate_rules(tuple(reversed(rules)), FACTS, SCOPE, NOW)
    assert forward == reverse
    assert forward.content_hash == reverse.content_hash
    assert EvaluationResult.from_dict(forward.to_dict()) == forward


@pytest.mark.parametrize("state", [RuleStatus.DRAFT, RuleStatus.PROPOSED, RuleStatus.RETIRED])
def test_unapproved_or_retired_rules_are_considered_but_never_applied(state):
    item = replace(rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE")), status=state)
    result = evaluate_rules((item,), FACTS, SCOPE, NOW)
    assert len(result.considered) == 1 and result.applied == ()
    assert result.status.value == "insufficient_data"


@pytest.mark.parametrize("changes", [
    {"valid_from": NOW + timedelta(seconds=1)},
    {"valid_to": NOW},
    {"suspended": True},
])
def test_scheduled_expired_or_suspended_rules_do_not_apply(changes):
    item = replace(rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE")), **changes)
    result = evaluate_rules((item,), FACTS, SCOPE, NOW)
    assert not result.applied and not result.restrictions


@pytest.mark.parametrize("condition", [Condition("ne", "missing", True), Condition("not", children=(Condition("eq", "missing", True),))])
def test_missing_fact_is_unknown_even_under_ne_or_not(condition):
    result = evaluate_rules((rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), condition=condition),), FACTS, SCOPE, NOW)
    assert result.status.value == "insufficient_data"
    assert result.missing == ("missing",) and not result.matched


def test_exists_missing_is_explicit_false_and_empty_ruleset_is_not_permission():
    item = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), condition=Condition("exists", "missing"))
    result = evaluate_rules((item,), FACTS, SCOPE, NOW)
    assert result.missing == () and not result.restrictions
    assert result.status.value == "insufficient_data"
    assert evaluate_rules((), FACTS, SCOPE, NOW).status.value == "insufficient_data"


def test_forbid_blocks_and_minimum_impact_preserves_strictest_class():
    rules = (rule(1, RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I1)),
             rule(2, RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I4)),
             rule(3, RuleEffect(EffectKind.FORBID, "EXECUTE")))
    result = evaluate_rules(rules, FACTS, SCOPE, NOW)
    assert result.status.value == "blocked" and result.minimum_impact_class is ImpactClass.I4


def test_exact_lower_waiver_leaves_matching_system_effect_in_force():
    system = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"))
    lower = rule(2, RuleEffect(EffectKind.REQUIRE, "QA"), level=RuleLevel.PROJECT)
    permission = rule(3, RuleEffect(EffectKind.ALLOW_EXCEPTION, lower.key))
    result = evaluate_rules((lower, permission, system), FACTS, SCOPE, NOW, (waiver(lower, permission),))
    assert result.obligations == ("QA",)
    assert len(result.waived) == 1 and result.waived[0].rule_version_id == lower.version_id
    assert result.status.value == "pass_with_obligations"


@pytest.mark.parametrize("fault", ["expired", "stale_hash", "wrong_scope", "revoked", "too_long", "permission_draft", "permission_false"])
def test_invalid_or_stale_exception_cannot_remove_original_restriction(fault):
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    exception = waiver(target, permission)
    if fault == "expired":
        exception = replace(exception, valid_from=NOW - timedelta(hours=2), valid_to=NOW)
    elif fault == "stale_hash":
        exception = replace(exception, target_content_hash="0" * 64)
    elif fault == "wrong_scope":
        exception = replace(exception, scope=replace(SCOPE, object_id=UUID(int=999)))
    elif fault == "revoked":
        exception = replace(exception, revoked_at=NOW)
    elif fault == "too_long":
        exception = replace(exception, valid_to=NOW + timedelta(days=3))
    elif fault == "permission_draft":
        permission = replace(permission, status=RuleStatus.DRAFT)
    else:
        permission = replace(permission, condition=Condition("eq", "enabled", False))
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (exception,))
    assert result.status.value == "blocked" and result.restrictions == ("EXECUTE",) and not result.waived
    assert result.exception_reasons


def test_system_rule_is_never_a_waiver_target():
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"))
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (waiver(target, permission),))
    assert result.status.value == "blocked" and not result.waived
    assert "SYSTEM_OVERRIDE_FORBIDDEN" in {reason for _, reason in result.exception_reasons}


def test_structural_duplicate_and_conflicting_basis_are_detected():
    candidate = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), level=RuleLevel.PROJECT)
    duplicate = replace(candidate, rule_id=UUID(int=998), version_id=UUID(int=999), key="another")
    report = validate_rule(candidate, SCHEMA, (duplicate,))
    assert not report.valid and "EXACT_DUPLICATE" in report.errors
    conflict = rule(3, RuleEffect(EffectKind.FORBID, "QA"))
    report = validate_rule(candidate, SCHEMA, (conflict,))
    assert not report.valid and "RULE_EFFECT_CONFLICT" in report.errors
    assert ValidationReport.from_dict(report.to_dict()) == report


def test_validation_basis_changes_when_upper_rule_snapshot_changes():
    candidate = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), level=RuleLevel.PROJECT)
    upper = rule(2, RuleEffect(EffectKind.REQUIRE, "AUDIT"))
    before = validate_rule(candidate, SCHEMA, (upper,))
    after = validate_rule(candidate, SCHEMA, (replace(upper, status=RuleStatus.RETIRED),))
    assert before.basis_fingerprint != after.basis_fingerprint
    assert validate_rule(candidate, SCHEMA, ()).valid


def test_unknown_condition_field_fails_validation():
    candidate = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), condition=Condition("eq", "missing", True))
    report = validate_rule(candidate, SCHEMA, ())
    assert not report.valid and "UNKNOWN_FACT_FIELD" in report.errors


def test_explicit_waiver_of_all_lower_effects_can_pass_without_granting_access():
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (waiver(target, permission),))
    assert result.status.value == "pass" and result.restrictions == () and len(result.waived) == 1
    assert evaluate_rules((permission,), FACTS, SCOPE, NOW).status.value == "insufficient_data"


def test_explicit_i0_floor_can_pass_without_other_obligations():
    result = evaluate_rules((rule(1, RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I0)),), FACTS, SCOPE, NOW)
    assert result.status.value == "pass" and result.minimum_impact_class is ImpactClass.I0


@pytest.mark.parametrize("op,expected", [("lt", False), ("le", True), ("gt", False), ("ge", True), ("eq", True), ("ne", False)])
def test_numeric_comparison_boundaries(op, expected):
    result = evaluate_rules((rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), condition=Condition(op, "amount", 2)),), FACTS, SCOPE, NOW)
    assert bool(result.matched) is expected


def test_bool_does_not_compare_as_number_and_missing_all_any_use_three_valued_logic():
    comparison = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), condition=Condition("ne", "enabled", 1))
    assert evaluate_rules((comparison,), FACTS, SCOPE, NOW).missing == ("enabled",)
    false_and_missing = Condition("all", children=(Condition("eq", "enabled", False), Condition("eq", "missing", True)))
    true_or_missing = Condition("any", children=(Condition("eq", "enabled", True), Condition("eq", "missing", True)))
    assert not evaluate_rules((replace(comparison, condition=false_and_missing),), FACTS, SCOPE, NOW).missing
    assert evaluate_rules((replace(comparison, condition=true_or_missing),), FACTS, SCOPE, NOW).status.value == "pass_with_obligations"


def test_exception_permission_must_apply_to_the_same_object_type():
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = replace(rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key)), object_type="ARTIFACT")
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (waiver(target, permission),))
    assert result.status.value == "blocked" and not result.waived


def test_structural_near_duplicate_is_found_without_claiming_semantic_completeness():
    a, b = Condition("eq", "enabled", True), Condition("ge", "amount", 1)
    candidate = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"), condition=Condition("all", children=(a, b)))
    duplicate = replace(candidate, rule_id=UUID(int=998), version_id=UUID(int=999), key="another", condition=Condition("all", children=(b, a)))
    report = validate_rule(candidate, SCHEMA, (duplicate,))
    assert not report.valid and "STRUCTURAL_NEAR_DUPLICATE" in report.errors
    assert report.near_duplicates == (duplicate.version_id,)


@pytest.mark.parametrize("field,value", [("engineVersion", "2.0"), ("factVersion", True), ("factContentHash", "nope"), ("extra", "unexpected")])
def test_result_decoder_rejects_invalid_or_unknown_contract_fields(field, value):
    data = evaluate_rules((rule(1, RuleEffect(EffectKind.REQUIRE, "QA")),), FACTS, SCOPE, NOW).to_dict()
    data[field] = value
    with pytest.raises(ValueError):
        EvaluationResult.from_dict(data)


def test_project_minimum_cannot_lower_a_system_floor():
    system = rule(1, RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I4))
    project = rule(2, RuleEffect(EffectKind.MINIMUM_IMPACT, impact=ImpactClass.I1), level=RuleLevel.PROJECT)
    result = evaluate_rules((project, system), FACTS, SCOPE, NOW)
    assert result.minimum_impact_class is ImpactClass.I4
    assert len(result.matched) == 2


@pytest.mark.parametrize("level", [RuleLevel.ORGANIZATION, RuleLevel.PROJECT])
def test_permission_at_same_or_lower_level_cannot_waive_organization_restriction(level):
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.ORGANIZATION)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key), level=level)
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (waiver(target, permission),))
    assert result.status.value == "blocked" and not result.waived
    assert result.exception_reasons == ((UUID(int=300), "EXCEPTION_PERMISSION_NOT_HIGHER"),)


@pytest.mark.parametrize("fault", ["wrong_key", "wrong_effect", "wrong_version", "permission_expired", "permission_missing_fact", "not_started"])
def test_waiver_requires_exact_effect_version_and_effective_matching_permission(fault):
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    exception = waiver(target, permission)
    if fault == "wrong_key":
        permission = replace(permission, effects=(RuleEffect(EffectKind.ALLOW_EXCEPTION, "another.rule"),))
    elif fault == "wrong_effect":
        exception = replace(exception, target_effect_hash="0" * 64)
    elif fault == "wrong_version":
        exception = replace(exception, target_version_id=UUID(int=999))
    elif fault == "permission_expired":
        permission = replace(permission, valid_to=NOW)
    elif fault == "permission_missing_fact":
        permission = replace(permission, condition=Condition("eq", "missing", True))
    else:
        exception = replace(exception, valid_from=NOW + timedelta(seconds=1))
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (exception,))
    assert result.status.value == "blocked" and result.restrictions == ("EXECUTE",) and not result.waived


@pytest.mark.parametrize("delta,waived", [(timedelta(hours=-1), True), (timedelta(hours=1, microseconds=-1), True), (timedelta(hours=1), False)])
def test_exception_interval_includes_start_and_excludes_end(delta, waived):
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    result = evaluate_rules((target, permission), FACTS, SCOPE, NOW + delta, (waiver(target, permission),))
    assert bool(result.waived) is waived
    assert result.status.value == ("pass" if waived else "blocked")


def test_historical_snapshot_replay_before_revocation_is_reproducible():
    target = rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=RuleLevel.PROJECT)
    permission = rule(2, RuleEffect(EffectKind.ALLOW_EXCEPTION, target.key))
    exception = replace(waiver(target, permission), revoked_at=NOW + timedelta(minutes=1))
    historical = evaluate_rules((target, permission), FACTS, SCOPE, NOW, (exception,))
    current = evaluate_rules((target, permission), FACTS, SCOPE, NOW + timedelta(minutes=1), (exception,))
    assert historical.status.value == "pass" and current.status.value == "blocked"
    assert evaluate_rules((target, permission), FACTS, SCOPE, NOW, (exception,)) == historical


@pytest.mark.parametrize("scope", [
    RuleScope(RuleLevel.ORGANIZATION, UUID(int=999)),
    RuleScope(RuleLevel.PROJECT, ORG, UUID(int=999)),
    RuleScope(RuleLevel.PROJECT, ORG, PROJECT, object_type="ARTIFACT"),
    RuleScope(RuleLevel.PROJECT, ORG, PROJECT, object_type="TASK", object_id=UUID(int=999)),
    RuleScope(RuleLevel.PROJECT, ORG, PROJECT, operation="EXPORT"),
])
def test_rule_outside_any_scope_dimension_is_not_applied(scope):
    item = replace(rule(1, RuleEffect(EffectKind.FORBID, "EXECUTE"), level=scope.level), scope=scope)
    result = evaluate_rules((item,), FACTS, SCOPE, NOW)
    assert result.status.value == "insufficient_data" and not result.applied and not result.restrictions


def test_object_type_metadata_is_enforced_and_disjoint_types_do_not_conflict_in_validation():
    first = replace(rule(1, RuleEffect(EffectKind.REQUIRE, "QA")), object_type="TASK")
    second = replace(rule(2, RuleEffect(EffectKind.FORBID, "QA")), object_type="ARTIFACT")
    result = evaluate_rules((first, second), FACTS, SCOPE, NOW)
    assert result.obligations == ("QA",) and not result.restrictions
    assert validate_rule(second, SCHEMA, (first,)).valid


def test_duplicate_active_version_of_same_rule_is_rejected():
    first = rule(1, RuleEffect(EffectKind.REQUIRE, "QA"))
    second = replace(first, version_id=UUID(int=999), version_number=2)
    with pytest.raises(ValueError, match="multiple active versions"):
        evaluate_rules((first, second), FACTS, SCOPE, NOW)


def test_result_dict_is_detached_from_immutable_result():
    result = evaluate_rules((rule(1, RuleEffect(EffectKind.REQUIRE, "QA")),), FACTS, SCOPE, NOW)
    data = result.to_dict()
    data["obligations"].append("EXTRA")
    assert result.obligations == ("QA",) and result.to_dict()["obligations"] == ["QA"]
