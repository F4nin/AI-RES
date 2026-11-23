"""Canonical Manager intake question behavior, independent of the transport."""
from dataclasses import replace
from uuid import uuid4

import pytest

from ai_res.modules.epics.manager_questions import (
    AnswerDisposition,
    ManagerQuestionState,
    QuestionAnswered,
    QuestionProposed,
    QuestionTransitionError,
)


def test_rebuild_matches_incremental_state_and_preserves_unknown():
    opened = QuestionProposed(1, uuid4(), uuid4(), "project.goal")
    unknown = QuestionAnswered(2, opened.question_id, uuid4(), AnswerDisposition.UNKNOWN)
    next_question = QuestionProposed(3, uuid4(), uuid4(), "project.actors")
    state = ManagerQuestionState.rebuild([opened, unknown, next_question])
    assert state == ManagerQuestionState().apply(opened).apply(unknown).apply(next_question)
    assert state.primary == next_question
    assert state.resolved[0].answer.disposition is AnswerDisposition.UNKNOWN


def test_question_cannot_skip_an_event_repeat_a_topic_or_answer_a_different_question():
    opened = QuestionProposed(1, uuid4(), uuid4(), "project.goal")
    state = ManagerQuestionState().apply(opened)
    with pytest.raises(QuestionTransitionError, match="primary"):
        state.apply(QuestionProposed(2, uuid4(), uuid4(), "project.actors"))
    with pytest.raises(QuestionTransitionError, match="different question"):
        state.apply(QuestionAnswered(2, uuid4(), uuid4(), AnswerDisposition.ANSWERED))
    with pytest.raises(QuestionTransitionError, match="contiguous"):
        state.apply(QuestionAnswered(3, opened.question_id, uuid4(), AnswerDisposition.ANSWERED))
    resolved = state.apply(QuestionAnswered(2, opened.question_id, uuid4(), AnswerDisposition.ANSWERED))
    with pytest.raises(QuestionTransitionError, match="covered"):
        resolved.apply(replace(opened, question_id=uuid4(), sequence=3))
