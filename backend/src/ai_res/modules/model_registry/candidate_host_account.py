"""Read-only original-account preflight; never establishes budget or approvals."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.model_registry.candidate_host import CandidateTariff
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest
from ai_res.modules.model_registry.poc_budget import AUTHORIZATION_KEY


async def verify_candidate_account(factory: async_sessionmaker[AsyncSession], account_id: UUID,
                                   manifest: CandidateRunManifest, tariff: CandidateTariff) -> None:
    """No transaction survives this check; the ledger revalidates under lock."""
    try:
        async with UnitOfWork(factory) as uow:
            await uow.session.execute(text("SELECT set_config('app.llm_poc_budget_id',:a,true)"), {"a": str(account_id)})
            row = (await uow.session.execute(text(
                "SELECT authorization_key,currency,max_cost,original_spend,max_attempts,input_bound,output_bound,body_bound,"
                "provider,model_id,http_method,upstream_host,upstream_path,plan_sha256,tariff_sha256,"
                "input_per_million,output_per_million FROM platform.llm_poc_budget_accounts WHERE id=:a"),
                {"a": account_id})).mappings().first()
            if (row is None or row["authorization_key"] != AUTHORIZATION_KEY
                    or row["currency"] != tariff.currency or not Decimal(0) < row["max_cost"] <= Decimal(10)
                    or not Decimal(0) <= row["original_spend"] <= row["max_cost"] or not 1 <= row["max_attempts"] <= 8
                    or row["input_bound"] != tariff.input_bound or row["output_bound"] != tariff.output_bound or row["body_bound"] != 4096
                    or (row["provider"], row["model_id"], row["http_method"], row["upstream_host"], row["upstream_path"])
                    != ("deepseek", "deepseek-flash", "POST", "api.deepseek.com", "/chat/completions")
                    or bytes(row["plan_sha256"]).hex() != manifest.plan_sha256
                    or bytes(row["tariff_sha256"]).hex() != manifest.tariff_sha256
                    or row["input_per_million"] != tariff.input_per_million or row["output_per_million"] != tariff.output_per_million):
                raise CandidateRunDenied("BINDING_MISMATCH")
    except SQLAlchemyError:
        raise CandidateRunDenied("ACCOUNTING_UNAVAILABLE") from None
