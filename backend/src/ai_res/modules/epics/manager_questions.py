"""Rebuildable question state for Manager intake (Process v1.9 §4–5 and §17)."""
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID


class AnswerDisposition(StrEnum):
    ANSWERED = "ANSWERED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class QuestionProposed:
    sequence: int
    question_id: UUID
    interaction_id: UUID
    topic: str


@dataclass(frozen=True, slots=True)
class QuestionAnswered:
    sequence: int
    question_id: UUID
    interaction_id: UUID
    disposition: AnswerDisposition


type QuestionEvent = QuestionProposed | QuestionAnswered


@dataclass(frozen=True, slots=True)
class ResolvedQuestion:
    question: QuestionProposed
    answer: QuestionAnswered


class QuestionTransitionError(ValueError):
    """Invalid or incomplete question history."""


@dataclass(frozen=True, slots=True)
class ManagerQuestionState:
    last_sequence: int = 0
    primary: QuestionProposed | None = None
    resolved: tuple[ResolvedQuestion, ...] = ()

    def apply(self, event: QuestionEvent) -> "ManagerQuestionState":
        if event.sequence != self.last_sequence + 1:
            raise QuestionTransitionError("question event sequence is not contiguous")
        if isinstance(event, QuestionProposed):
            if self.primary is not None:
                raise QuestionTransitionError("an unanswered primary question already exists")
            if not event.topic or any(
                item.question.topic == event.topic or item.question.question_id == event.question_id
                for item in self.resolved
            ):
                raise QuestionTransitionError("question already covered or missing a topic")
            return replace(self, last_sequence=event.sequence, primary=event)
        if self.primary is None or event.question_id != self.primary.question_id:
            raise QuestionTransitionError("answer targets a different question")
        return ManagerQuestionState(
            last_sequence=event.sequence,
            resolved=(*self.resolved, ResolvedQuestion(self.primary, event)),
        )

    @classmethod
    def rebuild(cls, events: Iterable[QuestionEvent]) -> "ManagerQuestionState":
        state = cls()
        for event in events:
            state = state.apply(event)
        return state
