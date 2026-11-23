"""Backend port for facts received from the trusted native task issuer (ADR-129)."""
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, WORKER_TASK_QUEUE
from ai_res.platform.ports import ServiceName

_NAMESPACE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


class TaskKind(StrEnum):
    WORKFLOW = "WORKFLOW"
    ACTIVITY = "ACTIVITY"


@dataclass(frozen=True, slots=True, repr=False)
class IssuanceLookup:
    token_digest: bytes
    principal: ServiceName
    namespace: str
    queue: str
    task_kind: TaskKind

    def __post_init__(self) -> None:
        admitted = (
            self.principal is ServiceName.MANAGER_RUNTIME and self.queue == MANAGER_TASK_QUEUE
            or self.principal is ServiceName.WORKER_RUNTIME and self.queue == WORKER_TASK_QUEUE and self.task_kind is TaskKind.ACTIVITY
        )
        if not (
            isinstance(self.token_digest, bytes) and len(self.token_digest) == 32 and isinstance(self.task_kind, TaskKind)
            and _NAMESPACE.fullmatch(self.namespace) and admitted
        ):
            raise ValueError("invalid task issuance identity or scope")


@dataclass(frozen=True, slots=True)
class TaskExecutionRef:
    operation_id: UUID
    workflow_run_id: UUID


_SELECT = text("""
    SELECT operation_id,workflow_run_id FROM platform.task_issuance_receipts
    WHERE token_digest=:digest AND principal=:principal AND namespace=:namespace AND queue=:queue AND task_kind=:kind
""")


def _params(key: IssuanceLookup) -> dict[str, str | bytes]:
    return {"digest": key.token_digest, "principal": key.principal.value, "namespace": key.namespace, "queue": key.queue, "kind": key.task_kind.value}


async def _read(session: AsyncSession, key: IssuanceLookup) -> TaskExecutionRef | None:
    found = (await session.execute(_SELECT, _params(key))).one_or_none()
    return None if found is None else TaskExecutionRef(found.operation_id, found.workflow_run_id)


class TaskIssuanceStore:
    """Short isolated DB transactions; no calls back into the orchestration engine."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def register(self, key: IssuanceLookup, ref: TaskExecutionRef) -> bool:
        async with UnitOfWork(self._factory) as uow:
            return await self.register_in(uow.session, key, ref)

    @staticmethod
    async def register_in(session: AsyncSession, key: IssuanceLookup, ref: TaskExecutionRef) -> bool:
        await session.execute(text("SELECT set_config('app.platform_action','auth.task_issue',true)"))
        await session.execute(text("""
            INSERT INTO platform.task_issuance_receipts (
                token_digest,principal,namespace,queue,task_kind,operation_id,workflow_run_id
            ) VALUES (:digest,:principal,:namespace,:queue,:kind,:operation,:run) ON CONFLICT DO NOTHING
        """), {**_params(key), "operation": ref.operation_id, "run": ref.workflow_run_id})
        return await _read(session, key) == ref

    async def check(self, key: IssuanceLookup) -> TaskExecutionRef | None:
        async with UnitOfWork(self._factory) as uow:
            return await self.check_in(uow.session, key)

    @staticmethod
    async def check_in(session: AsyncSession, key: IssuanceLookup) -> TaskExecutionRef | None:
        await session.execute(text("SELECT set_config('app.platform_action','auth.task_check',true)"))
        return await _read(session, key)
