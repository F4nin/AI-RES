"""Development candidate evidence, with no model approval or dispatch authority.

These types deliberately contain no managed profile/version, prompt, response or
tool arguments. Candidate facts (including missing fingerprints) cannot establish
an accepted identity. Accounting, admission and egress authorization are external.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from ai_res.llm.candidate_payload import CandidateBody
from ai_res.llm.observed_identity import ObservedProviderIdentity
from ai_res.platform.redaction import scan_secrets

EVIDENCE_VERSION = "flash-candidate-evidence/0.1"
_CASES = frozenset({"TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT"})
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class ProbeOutcome(StrEnum):
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class ProbeErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    INVALID_USAGE = "INVALID_USAGE"
    HTTP_REFUSED = "HTTP_REFUSED"
    CONNECTION_FAILED = "CONNECTION_FAILED"


class CandidateProbeError(ValueError):
    """Safe bounded code; no provider payload or exception is attached."""
    def __init__(self, code: ProbeErrorCode = ProbeErrorCode.INVALID_RESPONSE) -> None:
        self.code = code if isinstance(code, ProbeErrorCode) else ProbeErrorCode.INVALID_RESPONSE
        super().__init__(f"Candidate probe refused: {self.code.value}.")


def safe_probe_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_REF.fullmatch(value)) and not scan_secrets(value).found


@dataclass(frozen=True, slots=True, repr=False)
class CandidateProbeUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if (type(self.input_tokens) is not int or type(self.output_tokens) is not int
                or not 0 <= self.input_tokens <= 2_000_000 or not 0 <= self.output_tokens <= 256):
            raise CandidateProbeError(ProbeErrorCode.INVALID_USAGE)


@dataclass(frozen=True, slots=True, repr=False)
class CandidateProbeEvidence:
    """Local observation only. COMPLETE denotes transport completion, not acceptance."""
    case_ref: str
    body_sha256: str
    observed_at: datetime
    outcome: ProbeOutcome
    identity: ObservedProviderIdentity | None
    provider_request_ref: str | None
    usage: CandidateProbeUsage | None
    capability_ok: bool
    chunk_count: int = 0

    def __post_init__(self) -> None:
        if (not isinstance(self.case_ref, str) or self.case_ref not in _CASES
                or not isinstance(self.body_sha256, str) or not _HASH.fullmatch(self.body_sha256)
                or not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None
                or self.observed_at.utcoffset() != timedelta(0) or not isinstance(self.outcome, ProbeOutcome)
                or type(self.capability_ok) is not bool or type(self.chunk_count) is not int or not 0 <= self.chunk_count <= 2048
                or (self.identity is not None and not isinstance(self.identity, ObservedProviderIdentity))
                or (self.provider_request_ref is not None and not safe_probe_ref(self.provider_request_ref))
                or (self.usage is not None and not isinstance(self.usage, CandidateProbeUsage))
                or ((self.identity is None) != (self.provider_request_ref is None))):
            raise CandidateProbeError()
        if self.outcome is ProbeOutcome.COMPLETE:
            if self.identity is None or self.usage is None:
                raise CandidateProbeError()
        elif self.capability_ok or self.usage is not None:
            raise CandidateProbeError()
        if self.outcome is ProbeOutcome.CANCELLED and (self.case_ref != "CANCEL" or self.identity is None or not self.chunk_count):
            raise CandidateProbeError()

    def to_dict(self) -> dict[str, Any]:
        """Metadata-only export; never a persisted approval/expectation contract."""
        return {"version": EVIDENCE_VERSION, "caseRef": self.case_ref, "bodySha256": self.body_sha256,
                "observedAt": self.observed_at.isoformat().replace("+00:00", "Z"), "outcome": self.outcome.value,
                "identity": self.identity.to_dict() if self.identity else None, "providerRequestRef": self.provider_request_ref,
                "usage": {
                    "inputTokens": self.usage.input_tokens,
                    "outputTokens": self.usage.output_tokens,
                } if self.usage else None,
                "capabilityOk": self.capability_ok, "chunkCount": self.chunk_count}


class CandidateProbePort(Protocol):
    async def probe(self, body: CandidateBody, *, timeout_seconds: float) -> CandidateProbeEvidence: ...
