"""Trusted backend composition of per-call authorization and durable admission.

No default authorizer or managed-version resolver is provided. This adapter does
not approve a profile, mint a Run grant, allocate a budget or hold a DB transaction
during provider I/O. Runtime receives only the pure gateway port.
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ai_res.llm.admission import ObservedAdmissionCall
from ai_res.llm.errors import ModelProfileNotApproved
from ai_res.llm.observed_identity import IdentityObservation, ManagedVersions
from ai_res.llm.registry import ModelProfile, ProfileIdentityMode
from ai_res.llm.types import LLMRequest
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionTicket, AdmissionUnavailable, ModelAdmissionGuard


@dataclass(frozen=True, slots=True, repr=False)
class _AuthorizedCall:
    ticket: AdmissionTicket
    profile: ModelProfile
    request: LLMRequest


class ModelRegistryAdmission:
    def __init__(self, guard: ModelAdmissionGuard, *,
                 authorize: Callable[[ModelProfile, LLMRequest], Awaitable[bool]],
                 managed_versions: Callable[[ModelProfile, LLMRequest], ManagedVersions]) -> None:
        self._guard, self._authorize, self._versions = guard, authorize, managed_versions

    async def begin(self, profile: ModelProfile, request: LLMRequest) -> ObservedAdmissionCall:
        """Authenticate/authorize the exact caller scope, then commit guard preflight."""
        if (profile.identity_mode is not ProfileIdentityMode.FLASH_OBSERVED or request.model_profile_id != profile.id
                or await self._authorize(profile, request) is not True):
            raise ModelProfileNotApproved("observed call authorization refused")
        versions = self._versions(profile, request)
        if versions.profile_id != profile.id or versions.profile_version != profile.profile_version:
            raise ModelProfileNotApproved("observed managed versions do not match the profile")
        try:
            ticket = await self._guard.begin(profile.id, versions, request_ref=request.request_id)
        except (AdmissionDenied, AdmissionUnavailable):
            raise ModelProfileNotApproved("observed admission refused or is unavailable") from None
        return ObservedAdmissionCall(versions, _AuthorizedCall(ticket, profile, request))

    async def finalize(self, call: ObservedAdmissionCall, observation: IdentityObservation | bytes) -> None:
        binding = call.ticket
        if not isinstance(binding, _AuthorizedCall):
            raise ModelProfileNotApproved("observed admission ticket is invalid", possibly_billed=True)
        # The first check preserves pending on denial; the second covers changes
        # while the guard waited on DB locks. Both run outside the guard UoW.
        await self._revalidate(binding, call.managed_versions)
        try:
            await self._guard.finalize(binding.ticket, observation)
        except (AdmissionDenied, AdmissionUnavailable):
            raise ModelProfileNotApproved("observed result admission refused or is unavailable", possibly_billed=True) from None
        await self._revalidate(binding, call.managed_versions)

    async def _revalidate(self, binding: _AuthorizedCall, expected: ManagedVersions) -> None:
        try:
            authorized = await self._authorize(binding.profile, binding.request)
            versions = self._versions(binding.profile, binding.request)
        except Exception:
            raise ModelProfileNotApproved("observed result authorization is unavailable", possibly_billed=True) from None
        if authorized is not True or versions != expected:
            raise ModelProfileNotApproved("observed result authorization refused", possibly_billed=True)
