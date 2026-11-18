"""Bounded human command validation; no model/person approval occurs here."""
from dataclasses import replace
from uuid import uuid4

import pytest

from ai_res.modules.model_registry.admission import AdmissionDenied
from ai_res.modules.model_registry.identity_operator import IdentityDecision, IdentityDecisionAction
from ai_res.modules.model_registry.owner_review import OwnerReview


def command():
    review = OwnerReview(*(["a" * 64] * 4), "synthetic-policy")
    return IdentityDecision(uuid4(), uuid4(), IdentityDecisionAction.ACCEPT_IDENTITY, review)


def test_human_command_is_explicit_and_does_not_expose_review_in_repr():
    value = command()
    assert value.action is IdentityDecisionAction.ACCEPT_IDENTITY
    assert "a" * 64 not in repr(value)


@pytest.mark.parametrize("field,value", [("decision_id", "bad"), ("correlation_id", None),
    ("action", "ACCEPT_IDENTITY"), ("action", True), ("review", None)])
def test_untyped_or_missing_decision_fields_refuse(field, value):
    with pytest.raises(AdmissionDenied):
        replace(command(), **{field: value})
