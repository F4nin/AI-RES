# ruff: noqa: E501  -- long prose lines in the module docstring
"""Model Registry (DOC-076 §3, ADR-106): immutable profile snapshots, resolved only when APPROVED.

A `ModelProfile` is one immutable VERSION of a routing alias (`profile_key`): provider, provider model id and the PINNED model version never change after
creation (evaluation and release evidence reference an immutable version). Only the lifecycle moves: CANDIDATE -> APPROVED -> DEPRECATED -> RETIRED. Approval is a
human/owner decision (project-context.md: no automatic approval); nothing in this package approves a profile.

The registry is DATA: no profile is built in. An empty registry refuses every call (fail closed); the first profile arrives with the provider decision (OD-01, S16).
"""
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from ai_res.llm.errors import ModelProfileNotApproved, ModelProfileNotFound
from ai_res.llm.types import Capability

_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_LABEL = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
_REGION = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_FLOATING_VERSIONS = frozenset({"latest", "stable", "default", "current", "newest"})  # an alias is not a pin (Completion Decisions §3.2)


class ProfileStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class Egress(StrEnum):
    """Where the prompt goes. Ordered by exposure; a fallback may never move to a higher one (DOC-076 §4). WORKING vocabulary (ADR-106)."""
    LOCAL = "LOCAL"
    EXTERNAL = "EXTERNAL"

    @property
    def rank(self) -> int:
        return {"LOCAL": 0, "EXTERNAL": 1}[self.value]


class RetryClass(StrEnum):
    NONE = "NONE"  # a single attempt
    BOUNDED = "BOUNDED"  # bounded retries with jitter on retryable errors (the numbers are gateway configuration, WORKING)


@dataclass(frozen=True, slots=True, kw_only=True)
class CostRates:
    """Decimal per million tokens in one explicit currency; never float (coding-standards.md). Rates are cost METADATA of the profile, not an invoice."""
    currency: str
    input_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z]{3}", self.currency) or self.input_per_million < 0 or self.output_per_million < 0:
            raise ValueError("cost rates need an ISO-4217-style currency and non-negative Decimal rates")

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (self.input_per_million * input_tokens + self.output_per_million * output_tokens) / Decimal(1_000_000)


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelProfile:
    id: UUID  # model_profile_id: what a request names
    profile_key: str  # routing alias; every WorkerRun records the actual id/provider/version instead
    profile_version: int
    provider: str
    provider_model_id: str
    pinned_model_version: str
    capabilities: frozenset[Capability]
    context_window_tokens: int
    max_output_tokens: int
    data_classifications: frozenset[str]  # labels this profile may receive; the vocabulary is the owner's (WORKING, ADR-106)
    allowed_regions: frozenset[str]
    egress: Egress
    timeout_seconds: float
    retry_class: RetryClass
    status: ProfileStatus
    cost_rates: CostRates | None = None  # None = unknown; a cost budget on such a profile is refused (BUDGET_UNENFORCEABLE)
    rate_limit_rpm: int | None = None  # stored for the adapter; enforcement lives with the gateway implementation (G-144)
    rate_limit_tpm: int | None = None
    fallback_group: str | None = None
    evaluation_manifest_ref: str | None = None
    approved_at: datetime | None = None
    deprecated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not _KEY.match(self.profile_key) or self.profile_version < 1:
            raise ValueError("profile_key must be a lower-case alias and profile_version >= 1")
        if not self.provider or not self.provider_model_id:
            raise ValueError("provider and provider_model_id are required")
        if not self.pinned_model_version or self.pinned_model_version.strip().lower() in _FLOATING_VERSIONS:
            raise ValueError("pinned_model_version must pin an exact model version, not an alias")
        if not self.capabilities or not self.data_classifications or not self.allowed_regions:
            raise ValueError("capabilities, data_classifications and allowed_regions must not be empty")
        if not all(_LABEL.match(c) for c in self.data_classifications) or not all(_REGION.match(r) for r in self.allowed_regions):
            raise ValueError("malformed data classification label or region")
        if self.context_window_tokens < 1 or not 1 <= self.max_output_tokens <= self.context_window_tokens or self.timeout_seconds <= 0:
            raise ValueError("context_window_tokens, max_output_tokens and timeout_seconds must be consistent and positive")
        if self.status in (ProfileStatus.APPROVED, ProfileStatus.DEPRECATED, ProfileStatus.RETIRED) and self.approved_at is None:
            raise ValueError("an approved profile carries approved_at")
        if self.fallback_group is not None and not _KEY.match(self.fallback_group):
            raise ValueError("fallback_group must be a lower-case label")

    def usable_at(self, now: datetime) -> bool:
        """APPROVED, and not past its scheduled deprecation. DEPRECATED/RETIRED profiles take no new calls (WORKING reading of the lifecycle, ADR-106)."""
        return self.status is ProfileStatus.APPROVED and (self.deprecated_at is None or now < self.deprecated_at)


class ModelRegistry:
    """Immutable snapshot of profiles. Build a new one to change anything; there is no mutator."""

    def __init__(self, profiles: Iterable[ModelProfile] = ()) -> None:
        by_id: dict[UUID, ModelProfile] = {}
        seen: set[tuple[str, int]] = set()
        for profile in profiles:
            if profile.id in by_id or (profile.profile_key, profile.profile_version) in seen:
                raise ValueError("duplicate model profile id or (profile_key, profile_version)")
            by_id[profile.id] = profile
            seen.add((profile.profile_key, profile.profile_version))
        self._by_id: Mapping[UUID, ModelProfile] = by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def all(self) -> tuple[ModelProfile, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda p: (p.profile_key, -p.profile_version)))

    def get(self, profile_id: UUID) -> ModelProfile | None:
        return self._by_id.get(profile_id)

    def resolve(self, profile_id: UUID, now: datetime) -> ModelProfile:
        """The profile a request names, only if it may take calls; otherwise a typed refusal (never a silent substitute)."""
        profile = self._by_id.get(profile_id)
        if profile is None:
            raise ModelProfileNotFound("model profile is not registered")
        if not profile.usable_at(now):
            raise ModelProfileNotApproved("model profile is not approved for use")
        return profile

