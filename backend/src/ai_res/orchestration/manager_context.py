"""Metadata-only contract shared by the private Platform API and Manager Activity."""
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Status = Annotated[str, Field(pattern=r"^[A-Z][A-Z_]*$")]
PositiveVersion = Annotated[int, Field(ge=1)]
NonNegativeCount = Annotated[int, Field(ge=0)]


class ManagerEpicContext(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid", frozen=True, strict=True)

    epic_version: PositiveVersion
    epic_status: Status
    operation_version: PositiveVersion
    operation_status: Literal["RUNNING"]
    question_sequence: NonNegativeCount
    has_open_question: bool
    plan_version: PositiveVersion | None
    plan_decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"] | None
    task_counts: dict[Status, NonNegativeCount]


@dataclass(frozen=True, slots=True)
class IssuedManagerContext:
    version_id: UUID
    state: ManagerEpicContext
