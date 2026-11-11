"""Session factory and Unit of Work (Blueprint §7.1–7.2).

The Application Service owns the Unit of Work. Repositories receive the session and never commit. No network/LLM/Temporal call
may happen while the UoW is open (coding-standards: no transaction across external RPC).
"""
from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, AsyncSessionTransaction, async_sessionmaker

from ai_res.db.tenant_context import set_tenant_context


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False + DTO snapshots: no lazy loads after the transaction closes; autobegin off keeps the boundary explicit.
    return async_sessionmaker(engine, expire_on_commit=False, autobegin=False)


class UnitOfWork:
    """`async with UnitOfWork(factory) as uow:` -> BEGIN; clean exit -> COMMIT; any exception -> ROLLBACK (exception propagates)."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._session: AsyncSession | None = None
        self._tx: AsyncSessionTransaction | None = None
        self._tenant_set = False

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._session

    async def __aenter__(self) -> Self:
        session = self._factory()
        try:
            self._tx = await session.begin()
        except BaseException:
            await session.close()  # a failed BEGIN (unreachable DB, pool timeout) must not leak the session
            raise
        self._session = session
        self._tenant_set = False
        return self

    async def with_tenant(self, organization_id: UUID, project_id: UUID | None = None) -> None:
        """Call right after authorization and before any domain statement; the setting dies with this transaction.
        Exactly once per transaction: switching tenant mid-transaction would let one use case read as A and write as B."""
        if self._tenant_set:
            raise RuntimeError("tenant context is already set for this transaction")
        await set_tenant_context(self.session, organization_id, project_id)
        self._tenant_set = True

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        session, tx = self._session, self._tx
        if session is None or tx is None:
            raise RuntimeError("UnitOfWork exited without being entered")
        try:
            if exc_type is None:
                await tx.commit()
            else:
                await tx.rollback()
        finally:
            await session.close()
            self._session = self._tx = None
            self._tenant_set = False
