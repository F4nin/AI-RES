"""Operation state machine: parity with the baselined State Machine v1.2 JSON and exhaustive transition behaviour."""
import itertools
import json
from pathlib import Path

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from ai_res.modules.operations.state_machine import STATUSES, TERMINAL, TRANSITIONS, is_allowed, require_transition
from ai_res.platform.problems import ErrorCode, ProblemError

BASELINE = Path(__file__).resolve().parents[3] / "docs/architecture/AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json"


@pytest.fixture(scope="module")
def baseline() -> dict:
    if not BASELINE.is_file():
        pytest.skip("docs/architecture is not available in this checkout")  # CI checks the repository out whole; a missing baseline would be loud there
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_table_equals_the_baselined_json(baseline):
    assert list(STATUSES) == baseline["operationStatuses"]
    assert set(TERMINAL) == set(baseline["terminalStatuses"])
    assert {k: set(v) for k, v in TRANSITIONS.items()} == {k: set(v) for k, v in baseline["transitions"].items()}


def test_every_status_pair_is_decided_exactly_by_the_table():
    for a, b in itertools.product(STATUSES, STATUSES):
        if is_allowed(a, b):
            require_transition(a, b)
        else:
            with pytest.raises(ProblemError) as err:
                require_transition(a, b)
            assert err.value.code == ErrorCode.STATE_TRANSITION_NOT_ALLOWED, (a, b)


def test_terminal_statuses_have_no_exit_and_self_loops_are_not_transitions():
    assert all(not TRANSITIONS[t] for t in TERMINAL)
    assert not any(is_allowed(s, s) for s in STATUSES)


@pytest.mark.parametrize("bad", ["", "running", "UNKNOWN", "SUCCEEDED ", None])
def test_unknown_status_values_are_refused(bad):
    with pytest.raises(ProblemError):
        require_transition("RUNNING", bad)  # type: ignore[arg-type]
    with pytest.raises(ProblemError):
        require_transition(bad, "RUNNING")  # type: ignore[arg-type]


class OperationLifecycle(RuleBasedStateMachine):
    """Random walk: an attempted move is applied iff the baseline allows it, a terminal status is absorbing, and every reachable status is legal."""

    def __init__(self) -> None:
        super().__init__()
        self.status = "ACCEPTED"
        self.history = ["ACCEPTED"]

    @rule(to=st.sampled_from(STATUSES))
    def attempt(self, to: str) -> None:
        before = self.status
        try:
            require_transition(before, to)
        except ProblemError:
            assert not is_allowed(before, to)
            return
        assert before not in TERMINAL
        self.status = to
        self.history.append(to)

    @invariant()
    def terminal_is_absorbing(self) -> None:
        terminal_positions = [i for i, s in enumerate(self.history) if s in TERMINAL]
        assert len(terminal_positions) <= 1
        if terminal_positions:
            assert terminal_positions[0] == len(self.history) - 1


TestOperationLifecycle = OperationLifecycle.TestCase
