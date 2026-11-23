"""Cycles, unreachable branches and exact partial-approval dependency closure."""
from uuid import uuid4

import pytest

from ai_res.modules.tasks.plan_graph import PlanDependency, PlanGraph, PlanGraphCode, PlanGraphError


def test_reject_cycle_and_missing_predecessor():
    first, second = uuid4(), uuid4()
    cyclic = PlanGraph((PlanDependency(first, frozenset({second})), PlanDependency(second, frozenset({first}))), frozenset())
    with pytest.raises(PlanGraphError) as error:
        cyclic.order()
    assert error.value.code is PlanGraphCode.CYCLE
    missing = PlanGraph((PlanDependency(first, frozenset({second})),), frozenset())
    with pytest.raises(PlanGraphError) as denied:
        missing.order()
    assert denied.value.code is PlanGraphCode.MISSING_PREDECESSOR


def test_unreachable_branch_rejected():
    first, disconnected = uuid4(), uuid4()
    graph = PlanGraph((PlanDependency(first), PlanDependency(disconnected)), frozenset({first}))
    with pytest.raises(PlanGraphError) as denied:
        graph.order()
    assert denied.value.code is PlanGraphCode.UNREACHABLE_ITEM


def test_partial_approval_and_independent_parallel_ready_paths():
    first, second, child = uuid4(), uuid4(), uuid4()
    graph = PlanGraph((PlanDependency(first), PlanDependency(second), PlanDependency(child, frozenset({first}))), frozenset({first, second}))
    with pytest.raises(PlanGraphError) as denied:
        graph.validate_approval(frozenset({second, child}))
    assert denied.value.code is PlanGraphCode.UNAPPROVED_PREDECESSOR
    assert graph.ready(frozenset({first, second, child}), frozenset()) == tuple(sorted((first, second)))
    assert graph.ready(frozenset({first, child}), frozenset({first})) == (child,)
    assert graph.ready(frozenset({second}), frozenset()) == (second,)
