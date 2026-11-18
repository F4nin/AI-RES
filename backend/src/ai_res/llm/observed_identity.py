"""WORKING ADR-128/131 evidence contract and offline comparison, version 0.2.

This module performs no I/O, dispatch, approval, persistence or durable blocking.
An expectation is comparison input, never proof of human acceptance. A future
trusted admission service must authenticate its source and revalidate generation,
block state and audit atomically before exposing a result. Existing immutable-only
transport/factory guards remain untouched. Fixtures cannot establish live evidence.
"""
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, NoReturn
from uuid import UUID

from ai_res.platform.redaction import scan_secrets

SCHEMA_VERSION = "0.2"
MAX_EVIDENCE_BYTES = 16_384  # WORKING parser safety bound, not a product SLO
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")
_FLASH_RESPONSE = re.compile(r"(?:deepseek-flash|deepseek-v[0-9]+(?:\.[0-9]+)*-flash(?:-[A-Za-z0-9._-]+)?|"
                             r"DeepSeek-V[0-9]+(?:\.[0-9]+)*-Flash(?:-[A-Za-z0-9._-]+)?)\Z")
_FLASH = "deepseek-flash"


class InvalidIdentityEvidence(ValueError):
    def __init__(self) -> None:
        super().__init__("Identity evidence does not satisfy contract 0.2.")


class IdentityNotAccepted(ValueError):
    def __init__(self) -> None:
        super().__init__("Identity comparison requires an explicit expectation.")


class IdentityMismatch(ValueError):
    def __init__(self) -> None:
        super().__init__("Identity evidence does not match the expected binding.")


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidIdentityEvidence()


def _identifier(value: Any) -> str:
    _require(isinstance(value, str) and _ID.fullmatch(value) is not None)
    _require(not scan_secrets(value).found)
    return str(value)


def _hash(value: Any) -> str:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None)
    return str(value)


def _positive(value: Any) -> int:
    _require(type(value) is int and 1 <= value <= 2_147_483_647)
    return int(value)


def _object(value: Any, keys: set[str] | None = None) -> dict[str, Any]:
    _require(isinstance(value, dict))
    if keys is not None:
        _require(value.keys() == keys)
    return dict(value)


def _utc(value: Any) -> datetime:
    _require(isinstance(value, datetime) and value.utcoffset() == timedelta(0))
    return value.astimezone(UTC)  # type: ignore[no-any-return]


@dataclass(frozen=True, slots=True, repr=False)
class ManagedVersions:
    code_revision: str
    profile_id: UUID
    profile_version: int
    config_sha256: str
    prompt_sha256: str
    tools_sha256: str | None

    def __post_init__(self) -> None:
        _require(isinstance(self.code_revision, str) and _REVISION.fullmatch(self.code_revision) is not None)
        _require(isinstance(self.profile_id, UUID))
        _positive(self.profile_version)
        _hash(self.config_sha256)
        _hash(self.prompt_sha256)
        if self.tools_sha256 is not None:
            _hash(self.tools_sha256)

    @classmethod
    def from_dict(cls, value: Any) -> "ManagedVersions":
        data = _object(value, {"codeRevision", "profileId", "profileVersion", "configSha256", "promptSha256", "toolsSha256"})
        profile = data["profileId"]
        _require(isinstance(profile, str) and _UUID.fullmatch(profile) is not None)
        return cls(data["codeRevision"], UUID(profile), data["profileVersion"], data["configSha256"], data["promptSha256"], data["toolsSha256"])

    def to_dict(self) -> dict[str, Any]:
        return {"codeRevision": self.code_revision, "profileId": str(self.profile_id), "profileVersion": self.profile_version,
                "configSha256": self.config_sha256, "promptSha256": self.prompt_sha256, "toolsSha256": self.tools_sha256}


class FingerprintPresence(StrEnum):
    ABSENT = "ABSENT"
    NULL = "NULL"
    VALUE = "VALUE"


@dataclass(frozen=True, slots=True, repr=False)
class ObservedFingerprint:
    presence: FingerprintPresence
    value: str | None

    def __post_init__(self) -> None:
        _require(isinstance(self.presence, FingerprintPresence))
        if self.presence is FingerprintPresence.VALUE:
            _identifier(self.value)
        else:
            _require(self.value is None)

    @classmethod
    def from_dict(cls, value: Any) -> "ObservedFingerprint":
        data = _object(value, {"presence", "value"})
        _require(isinstance(data["presence"], str) and data["presence"] in {p.value for p in FingerprintPresence})
        return cls(FingerprintPresence(data["presence"]), data["value"])

    def to_dict(self) -> dict[str, Any]:
        return {"presence": self.presence.value, "value": self.value}


@dataclass(frozen=True, slots=True, repr=False)
class ObservedProviderIdentity:
    provider: str
    request_model_id: str
    routing_model_id: str
    response_model_id: str
    fingerprint: ObservedFingerprint

    def __post_init__(self) -> None:
        _require(self.provider == "deepseek" and self.request_model_id == _FLASH and self.routing_model_id == _FLASH)
        _identifier(self.response_model_id)
        _require(isinstance(self.fingerprint, ObservedFingerprint))

    @classmethod
    def from_dict(cls, value: Any) -> "ObservedProviderIdentity":
        data = _object(value, {"provider", "requestModelId", "routingModelId", "responseModelId", "fingerprint"})
        return cls(data["provider"], data["requestModelId"], data["routingModelId"], data["responseModelId"],
                   ObservedFingerprint.from_dict(data["fingerprint"]))

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "requestModelId": self.request_model_id, "routingModelId": self.routing_model_id,
                "responseModelId": self.response_model_id, "fingerprint": self.fingerprint.to_dict()}


@dataclass(frozen=True, slots=True, repr=False)
class IdentityObservation:
    managed_versions: ManagedVersions
    identity: ObservedProviderIdentity
    observed_at: datetime
    request_ref: str
    provider_request_ref: str

    def __post_init__(self) -> None:
        _require(isinstance(self.managed_versions, ManagedVersions) and isinstance(self.identity, ObservedProviderIdentity))
        _utc(self.observed_at)
        _identifier(self.request_ref)
        _identifier(self.provider_request_ref)

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": SCHEMA_VERSION, "kind": "OBSERVATION", "managedVersions": self.managed_versions.to_dict(),
                "identity": self.identity.to_dict(), "observedAt": _utc(self.observed_at).isoformat().replace("+00:00", "Z"),
                "requestRef": self.request_ref, "providerRequestRef": self.provider_request_ref}


@dataclass(frozen=True, slots=True, repr=False)
class IdentityExpectation:
    """Comparison input with a required observed fingerprint (ADR-131), never approval authority."""
    managed_versions: ManagedVersions
    identity: ObservedProviderIdentity
    admission_generation: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        _require(isinstance(self.managed_versions, ManagedVersions) and isinstance(self.identity, ObservedProviderIdentity))
        # Unknown/Pro response facts may be observed, but cannot become an expected Flash identity.
        _require(_FLASH_RESPONSE.fullmatch(self.identity.response_model_id) is not None)
        # Missing/null metadata remains useful candidate evidence, but cannot be an admitted expectation.
        _require(self.identity.fingerprint.presence is FingerprintPresence.VALUE)
        _positive(self.admission_generation)
        _hash(self.evidence_sha256)

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": SCHEMA_VERSION, "kind": "EXPECTATION", "managedVersions": self.managed_versions.to_dict(),
                "identity": self.identity.to_dict(), "admissionGeneration": self.admission_generation, "evidenceSha256": self.evidence_sha256}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidIdentityEvidence()
        result[key] = value
    return result


def _nonfinite(_: str) -> NoReturn:
    raise InvalidIdentityEvidence()


def parse_evidence(raw: str | bytes) -> IdentityObservation | IdentityExpectation:
    """Strict bounded standalone metadata JSON; no source/prompt/output fields allowed."""
    try:
        _require(isinstance(raw, str | bytes))
        _require(len(raw) <= MAX_EVIDENCE_BYTES)
        size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
        _require(size <= MAX_EVIDENCE_BYTES)
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        data = _object(json.loads(decoded, object_pairs_hook=_pairs, parse_constant=_nonfinite))
        _require(data.get("schemaVersion") == SCHEMA_VERSION)
        shared = {"schemaVersion", "kind", "managedVersions", "identity"}
        if data.get("kind") == "OBSERVATION":
            _object(data, shared | {"observedAt", "requestRef", "providerRequestRef"})
            stamp = data["observedAt"]
            _require(isinstance(stamp, str) and _TIME.fullmatch(stamp) is not None)
            return IdentityObservation(ManagedVersions.from_dict(data["managedVersions"]), ObservedProviderIdentity.from_dict(data["identity"]),
                                       datetime.fromisoformat(stamp), data["requestRef"], data["providerRequestRef"])
        _require(data.get("kind") == "EXPECTATION")
        _object(data, shared | {"admissionGeneration", "evidenceSha256"})
        return IdentityExpectation(ManagedVersions.from_dict(data["managedVersions"]), ObservedProviderIdentity.from_dict(data["identity"]),
                                   data["admissionGeneration"], data["evidenceSha256"])
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise InvalidIdentityEvidence() from None


def extract_bifrost_observation(response: dict[str, Any], *, managed_versions: ManagedVersions, observed_at: datetime,
                                request_ref: str, request_model_id: str) -> IdentityObservation:
    """Select bounded metadata from an already decoded Bifrost frame; never copy its choices/content.

    request_model_id/managed versions/time/correlation come from trusted composition,
    not provider text. This parser neither performs nor authorizes a candidate call.
    Unknown response model facts are evidence only and cannot create an expectation.
    """
    _require(request_model_id == _FLASH)
    data = _object(response)
    routing = _object(_object(data.get("extra_fields")).get("routing_info"))
    _require(routing.get("provider") == "deepseek" and routing.get("model") == _FLASH)
    _require(routing.get("is_fallback", False) is False and routing.get("server_side_fallback_model") in (None, "")
             and routing.get("resolved_key_alias") is None and routing.get("requested_model", _FLASH) == _FLASH)
    if "system_fingerprint" not in data:
        presence = FingerprintPresence.ABSENT
    else:
        presence = FingerprintPresence.NULL if data["system_fingerprint"] is None else FingerprintPresence.VALUE
    fingerprint = ObservedFingerprint(presence, data.get("system_fingerprint"))
    identity = ObservedProviderIdentity("deepseek", request_model_id, _FLASH, _identifier(data.get("model")), fingerprint)
    return IdentityObservation(managed_versions, identity, observed_at, request_ref, _identifier(data.get("id")))


def compare_identity(observation: IdentityObservation, expectation: IdentityExpectation | None, *, current_generation: int) -> None:
    """Compare only; no approval, state mutation, durable preflight or result publication.

    The caller must obtain/revalidate expectation and current_generation from trusted
    durable authority. Matching locally supplied objects cannot establish admission.
    """
    _require(isinstance(observation, IdentityObservation))
    _positive(current_generation)
    if expectation is None:
        raise IdentityNotAccepted()
    _require(isinstance(expectation, IdentityExpectation))
    if (expectation.admission_generation != current_generation or observation.managed_versions != expectation.managed_versions
            or observation.identity != expectation.identity):
        raise IdentityMismatch()
