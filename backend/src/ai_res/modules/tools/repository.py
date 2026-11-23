"""Current scoped grant lookup and transactional call accounting."""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.tools.contracts import ToolCall, ToolRef, ToolSubject, ToolTarget
from ai_res.modules.tools.grants import WorkerToolGrant


class SqlWorkerToolGrants:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, subject: ToolSubject, grant_id: UUID) -> WorkerToolGrant | None:
        grant = (await self._session.execute(text("""
            SELECT g.* FROM agents.worker_tool_grants g
            WHERE g.id = :grant_id AND g.worker_run_id = :run_id
              AND g.organization_id = :org AND g.project_id = :project
              AND g.identity_id = :identity AND g.environment = :environment
        """), {
            "grant_id": grant_id, "run_id": subject.run_id, "org": subject.organization_id,
            "project": subject.project_id, "identity": subject.identity_id, "environment": subject.environment,
        })).mappings().one_or_none()
        if grant is None:
            return None
        return WorkerToolGrant(
            id=grant["id"], subject=subject, tool=ToolRef(grant["tool_id"], grant["tool_version"]),
            operation=grant["operation"], contract_version=grant["contract_version"],
            target=ToolTarget(resource_type=grant["resource_type"], resource_id=grant["resource_id"],
                              classification=grant["classification"]),
            permission_scope=grant["permission_scope"], allowed_model_profiles=frozenset(grant["allowed_model_profiles"]),
            budget_ref=grant["budget_ref"], expires_at=grant["expires_at"], revoked_at=grant["revoked_at"],
        )

    async def claim_rate(self, subject: ToolSubject, call: ToolCall, maximum: int) -> bool:
        # A single row serializes concurrent claims for the exact grant. Backward clock movement does not reset it.
        claim = await self._session.execute(text("""
            WITH tick AS (SELECT clock_timestamp() AS now)
            UPDATE agents.worker_tool_grants g
            SET rate_count = CASE WHEN g.rate_minute + interval '1 minute' > tick.now THEN g.rate_count + 1 ELSE 1 END,
                rate_minute = CASE
                    WHEN g.rate_minute + interval '1 minute' > tick.now THEN g.rate_minute
                    ELSE tick.now
                END
            FROM tick
            WHERE g.id = :grant_id AND g.worker_run_id = :run_id AND g.identity_id = :identity
              AND g.revoked_at IS NULL AND g.expires_at > clock_timestamp()
              AND (g.rate_minute IS NULL OR g.rate_minute + interval '1 minute' <= tick.now OR g.rate_count < :maximum)
            RETURNING g.id
        """), {"grant_id": call.grant_id, "run_id": subject.run_id, "identity": subject.identity_id, "maximum": maximum})
        return claim.scalar_one_or_none() is not None
