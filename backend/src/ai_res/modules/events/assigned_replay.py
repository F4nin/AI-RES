"""Exact replay approval for assigned Start quarantine."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.ids import new_id


@dataclass(frozen=True, slots=True)
class QuarantinedStart:
    event_id: UUID
    replay_count: int


async def inspect_quarantined_start(session: AsyncSession, operation_id: UUID) -> QuarantinedStart | None:
    row = (await session.execute(text(
        "SELECT event_id,replay_count FROM audit.inspect_assigned_start_replay(:operation)"
    ), {"operation": operation_id})).one_or_none()
    return None if row is None else QuarantinedStart(row.event_id, row.replay_count)


async def approve_quarantined_start(
    session: AsyncSession, operation_id: UUID, expected: QuarantinedStart, *, actor_id: UUID, session_id: UUID, correlation_id: UUID,
) -> bool:
    result = await session.execute(text(
        "SELECT audit.approve_assigned_start_replay(:operation,:event,:count,:actor,:session_id,:correlation,:audit_ref)"
    ), {"operation": operation_id, "event": expected.event_id, "count": expected.replay_count, "actor": actor_id,
        "session_id": session_id, "correlation": correlation_id, "audit_ref": new_id()})
    return bool(result.scalar_one())
