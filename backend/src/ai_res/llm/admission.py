"""Injected durable authority for the NCP-16 observed path; no persistence here.

Trusted backend composition supplies authorization and exact managed versions.
An observation or an in-memory ticket is never itself an approval or grant.
"""
from dataclasses import dataclass
from typing import Protocol

from ai_res.llm.errors import InvalidProviderOutput
from ai_res.llm.observed_identity import IdentityObservation, ManagedVersions
from ai_res.llm.registry import ModelProfile
from ai_res.llm.types import LLMRequest


@dataclass(frozen=True, slots=True, repr=False)
class ObservedAdmissionCall:
    managed_versions: ManagedVersions
    ticket: object


class ObservedAdmissionPort(Protocol):
    async def begin(self, profile: ModelProfile, request: LLMRequest) -> ObservedAdmissionCall:
        """Authorize and commit an unresolved receipt before external dispatch."""
        ...

    async def finalize(self, call: ObservedAdmissionCall, observation: IdentityObservation | bytes) -> None:
        """Durably validate or block; an unavailable dependency must refuse output."""
        ...


class ObservedIdentityInvalid(InvalidProviderOutput):
    """Static failure plus bounded metadata for durable drift blocking, never content."""

    def __init__(self, observation: IdentityObservation | None = None) -> None:
        super().__init__("Observed provider identity is missing, inconsistent or invalid", possibly_billed=True)
        self.observation = observation
