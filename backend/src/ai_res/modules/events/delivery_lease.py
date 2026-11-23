"""Wire proof of a particular protected Outbox lease."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DeliveryLease(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, extra="forbid", frozen=True)

    row_id: UUID
    lease_owner: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9._-]+$")
    attempt: int = Field(ge=1, le=2**31 - 1, strict=True)
    replay_count: int = Field(ge=0, le=2**31 - 1, strict=True)
