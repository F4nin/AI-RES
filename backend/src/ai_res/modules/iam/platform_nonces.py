"""One-use receipt for a verified ar2 credential, committed before the protected transaction."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import affected
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.platform_credentials import VerifiedAuthControlCredential, VerifiedPlatformCredential


class PlatformRequestNonceStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def consume(self, credential: VerifiedPlatformCredential | VerifiedAuthControlCredential) -> bool:
        """Returns False for replay or expiration. Store faults propagate and deny the caller."""
        async with UnitOfWork(self._factory) as uow:
            result = await uow.session.execute(text("""
                INSERT INTO platform.platform_request_nonces (issuer, nonce, expires_at)
                SELECT :issuer, :nonce, :expires WHERE :expires > clock_timestamp()
                ON CONFLICT DO NOTHING
            """), {"issuer": credential.issuer.value, "nonce": credential.nonce, "expires": credential.expires_at})
            return affected(result) == 1
