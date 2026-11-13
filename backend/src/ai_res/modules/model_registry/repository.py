# ruff: noqa: E501  -- long prose lines in docstrings and comments
"""Loads the Model Registry snapshot from `platform.model_profiles` (read-only: profiles are created and approved by the owner, never by runtime code).

The database CHECKs mirror the model, so an invalid row is a defect. A CANDIDATE row cannot take calls anyway, so it is skipped with a logged warning (one
unapproved draft must not stop every LLM call); an invalid row in any other status fails the WHOLE load with the row id (it may be in use: never a quietly smaller registry).
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.llm.registry import CostRates, Egress, ModelProfile, ModelRegistry, ProfileStatus, RetryClass
from ai_res.llm.types import Capability

_log = logging.getLogger("ai_res.llm")
_COLUMNS = ("id, profile_key, profile_version, provider, provider_model_id, pinned_model_version, capabilities, context_window_tokens, max_output_tokens, "
            "data_classifications, allowed_regions, egress, cost_currency, cost_input_per_million, cost_output_per_million, rate_limit_rpm, rate_limit_tpm, "
            "timeout_seconds, retry_class, fallback_group, evaluation_manifest_ref, status, approved_at, deprecated_at")


class RegistryLoadError(Exception):
    """A stored profile row is not a valid ModelProfile. Names the row only, never its values."""

    def __init__(self, profile_id: UUID) -> None:
        super().__init__(f"model profile {profile_id} is not valid")
        self.profile_id = profile_id


async def load_model_registry(session: AsyncSession) -> ModelRegistry:
    rows = (await session.execute(text(f"SELECT {_COLUMNS} FROM platform.model_profiles"))).all()  # noqa: S608 - fixed column list
    profiles: list[ModelProfile] = []
    for r in rows:
        try:
            rates = None if r.cost_currency is None else CostRates(currency=r.cost_currency, input_per_million=Decimal(r.cost_input_per_million),
                                                                   output_per_million=Decimal(r.cost_output_per_million))
            profiles.append(ModelProfile(
                id=r.id, profile_key=r.profile_key, profile_version=r.profile_version, provider=r.provider, provider_model_id=r.provider_model_id,
                pinned_model_version=r.pinned_model_version, capabilities=frozenset(Capability(c) for c in r.capabilities),
                context_window_tokens=r.context_window_tokens, max_output_tokens=r.max_output_tokens, data_classifications=frozenset(r.data_classifications),
                allowed_regions=frozenset(r.allowed_regions), egress=Egress(r.egress), timeout_seconds=float(r.timeout_seconds),
                retry_class=RetryClass(r.retry_class), status=ProfileStatus(r.status), cost_rates=rates, rate_limit_rpm=r.rate_limit_rpm,
                rate_limit_tpm=r.rate_limit_tpm, fallback_group=r.fallback_group, evaluation_manifest_ref=r.evaluation_manifest_ref,
                approved_at=r.approved_at, deprecated_at=r.deprecated_at))
        except (ValueError, TypeError, ArithmeticError):
            if r.status == ProfileStatus.CANDIDATE.value:
                _log.warning("invalid CANDIDATE model profile skipped", extra={"model_profile_id": str(r.id)})
                continue
            raise RegistryLoadError(r.id) from None
    if not profiles:
        _log.warning("model registry is empty: every LLM call will be refused")
    return ModelRegistry(profiles)  # duplicates cannot occur under the UNIQUE constraint
