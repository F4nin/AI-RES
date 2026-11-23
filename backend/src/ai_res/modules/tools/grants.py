"""Immutable scope read from the current grant source on every authorization."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ai_res.modules.tools.contracts import ToolRef, ToolSubject, ToolTarget


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerToolGrant:
    id: UUID
    subject: ToolSubject
    tool: ToolRef
    operation: str
    contract_version: str
    target: ToolTarget
    permission_scope: str
    allowed_model_profiles: frozenset[str]
    budget_ref: UUID
    expires_at: datetime
    revoked_at: datetime | None


class WorkerToolGrantSource(Protocol):
    async def get(self, subject: ToolSubject, grant_id: UUID) -> WorkerToolGrant | None:
        """Backend-owned current grant lookup. Implementations must exclude inactive runs."""
