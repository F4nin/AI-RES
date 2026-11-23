"""Authorize one live Outbox lease before calling the already protected Temporal path."""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.assigned_dispatch import AssignedDeliveryBackend
from ai_res.db.session import UnitOfWork
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.delivery_lease import DeliveryLease
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.iam.platform_credentials import VerifiedDeliveryCredential
from ai_res.platform.clock import utc_now
from ai_res.platform.problems import ErrorCode, ProblemError


class AssignedDeliveryControl:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], backend: AssignedDeliveryBackend, contract: EventContract,
    ) -> None:
        self._factory, self._backend, self._contract = factory, backend, contract

    async def deliver(self, credential: VerifiedDeliveryCredential, lease: DeliveryLease, correlation: UUID) -> None:
        try:
            async with UnitOfWork(self._factory) as uow:
                result = (await uow.session.execute(text("""
                    SELECT * FROM audit.authorize_assigned_delivery(
                        :row,:owner,:attempt,:replay,:namespace,:nonce,:expires,:correlation
                    )
                """), {"row": lease.row_id, "owner": lease.lease_owner, "attempt": lease.attempt, "replay": lease.replay_count,
                       "namespace": self._backend.namespace, "nonce": credential.nonce, "expires": credential.expires_at,
                       "correlation": correlation})).mappings().one()
        except SQLAlchemyError:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Delivery authorization unavailable.") from None
        now = utc_now()
        if result["decision"] == "EXPIRED_OR_REPLAY" or now >= credential.expires_at:
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")
        if result["decision"] != "AUTHORIZED" or now >= result["lease_until"]:
            raise ProblemError(ErrorCode.OPERATION_NOT_READY, "Delivery lease is unavailable.")
        row = OutboxRow(**{key: value for key, value in result.items() if key not in {"decision", "lease_until"}})
        self._contract.check_row(row)
        await self._backend.publish(row)
