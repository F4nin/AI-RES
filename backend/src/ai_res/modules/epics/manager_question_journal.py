"""Persist question transitions and rebuild one Epic's adaptive intake state."""
from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.epics.manager_interactions import INTERACTION_KIND
from ai_res.modules.epics.manager_questions import (
    AnswerDisposition,
    ManagerQuestionState,
    QuestionAnswered,
    QuestionEvent,
    QuestionProposed,
    QuestionTransitionError,
)
from ai_res.modules.events.aggregate_events import EventSpec, append_event
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.platform.problems import ErrorCode, ProblemError


@dataclass(frozen=True, slots=True)
class QuestionJournalState:
    state: ManagerQuestionState
    events: tuple[QuestionEvent, ...]


class ManagerQuestionJournal:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, epic_id: UUID) -> QuestionJournalState:
        records = await self._session.execute(text("""
            SELECT sequence,question_id,interaction_id,event_kind,topic,disposition
            FROM work.manager_question_journal WHERE epic_id=:epic ORDER BY sequence
        """), {"epic": epic_id})
        events: tuple[QuestionEvent, ...] = tuple(
            QuestionProposed(row.sequence, row.question_id, row.interaction_id, row.topic)
            if row.event_kind == "PROPOSED" else
            QuestionAnswered(row.sequence, row.question_id, row.interaction_id, AnswerDisposition(row.disposition))
            for row in records
        )
        return QuestionJournalState(ManagerQuestionState.rebuild(events), events)

    async def record(self, epic_id: UUID, event: QuestionEvent, correlation_id: UUID) -> ManagerQuestionState:
        """Lock the owning Epic, check exact interaction and append one accepted transition."""
        scope = (await self._session.execute(text("""
            SELECT i.organization_id,i.project_id,i.row_version
            FROM work.manager_interactions i JOIN work.epics e ON e.id=i.epic_id
            WHERE e.id=:epic AND i.id=:interaction
            FOR NO KEY UPDATE OF e
        """), {"epic": epic_id, "interaction": event.interaction_id})).one_or_none()
        if scope is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Manager interaction not found.")
        history = await self.load(epic_id)
        prior = next((saved for saved in history.events
                      if saved.interaction_id == event.interaction_id and type(saved) is type(event)), None)
        if prior is not None:
            if prior == replace(event, sequence=prior.sequence):
                return history.state
            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "A different question transition already exists.")
        try:
            next_event = replace(event, sequence=history.state.last_sequence + 1)
            state = history.state.apply(next_event)
        except QuestionTransitionError:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Question transition not allowed.") from None
        is_proposal = isinstance(next_event, QuestionProposed)
        if isinstance(next_event, QuestionProposed) and not 1 <= len(next_event.topic) <= 128:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Question topic reference is invalid.")
        await self._session.execute(text("""
            INSERT INTO work.manager_question_journal (
                organization_id,project_id,epic_id,sequence,interaction_id,question_id,event_kind,topic,disposition
            ) VALUES (:org,:project,:epic,:sequence,:interaction,:question,:kind,:topic,:disposition)
        """), {"org": scope.organization_id, "project": scope.project_id, "epic": epic_id, "sequence": next_event.sequence,
               "interaction": next_event.interaction_id, "question": next_event.question_id, "kind": "PROPOSED" if is_proposal else "RESOLVED",
               "topic": next_event.topic if isinstance(next_event, QuestionProposed) else None,
               "disposition": next_event.disposition.value if isinstance(next_event, QuestionAnswered) else None})
        if is_proposal:
            await append_event(
                self._session, INTERACTION_KIND, aggregate_id=next_event.interaction_id,
                organization_id=scope.organization_id, project_id=scope.project_id, operation_id=None, expected_version=scope.row_version,
                spec=EventSpec("manager.question.proposed", 1, "MANAGER", correlation_id, (DOMAIN_DESTINATION,),
                               data={"interactionId": str(next_event.interaction_id), "questionId": str(next_event.question_id)}),
            )
        return state
