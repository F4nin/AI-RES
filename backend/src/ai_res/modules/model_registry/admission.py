"""Durable G156 guard foundation, deliberately without transport or approval wiring.

Only trusted backend composition may call this class. The exact-profile RLS GUC
is defense-in-depth, not a service/Run authorization credential. No endpoint, human
approval or enablement of observed profiles is supplied. Existing model_profiles
remain read-only; the guard requires explicit observed mode and NULL pin. Synthetic
PG fixtures prove guard mechanics only, never actual provider/profile approval.

Single-flight receipts remain unresolved on crash/finalization failure. No expiry
or automatic unlock is invented. Audit writes are metadata-only technical security
facts in ai_res_db, separate from tenant Domain Audit and operational telemetry.
Lifecycle changes and these DB-only UoWs share a transaction fence (ADR138).
The fence is released before provider I/O; a ticket is not a dispatch permit.
Future owner commands must take the lifecycle fence before locking controls.
"""
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.llm.observed_identity import (
    IdentityExpectation,
    IdentityMismatch,
    IdentityObservation,
    InvalidIdentityEvidence,
    ManagedVersions,
    compare_identity,
    parse_evidence,
)
from ai_res.platform.ids import new_id
from ai_res.platform.redaction import scan_secrets

_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class AdmissionDenied(ValueError):
    """Safe refusal; never includes a provider response, credential or DB exception."""

    def __init__(self, code: str = "ADMISSION_DENIED") -> None:
        super().__init__("Model admission refused.")
        self.code = code


class AdmissionUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Model admission dependency unavailable.")


def _reference(value: Any) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value) or scan_secrets(value).found:
        raise AdmissionDenied("INVALID_REQUEST_REFERENCE")
    return value


def evidence_hash(value: IdentityExpectation | IdentityObservation) -> bytes:
    """Hash bounded validated metadata, never a full model response."""
    return hashlib.sha256(canonical_json(value.to_dict()).encode("utf-8")).digest()


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionTicket:
    call_id: UUID
    profile_id: UUID
    profile_version: int
    generation: int
    call_sequence: int
    request_ref: str
    expected_sha256: str

    def __post_init__(self) -> None:
        if (not isinstance(self.call_id, UUID) or not isinstance(self.profile_id, UUID)
                or any(type(v) is not int or v < 1 for v in (self.profile_version, self.generation, self.call_sequence))
                or not isinstance(self.expected_sha256, str) or not _HASH.fullmatch(self.expected_sha256)):
            raise AdmissionDenied("INVALID_TICKET")
        _reference(self.request_ref)


async def lock_profile_lifecycle(session: AsyncSession, profile_id: UUID) -> None:
    """Acquire the ADR138 fence before profile/control reads in a short DB UoW."""
    if not isinstance(profile_id, UUID):
        raise AdmissionDenied("INVALID_PROFILE")
    # A fresh statement snapshot AFTER waiting is required. RR/Serializable
    # could keep the pre-wait lifecycle snapshot and are not supported here.
    ready = (await session.execute(text(
        "SELECT current_setting('transaction_isolation')='read committed' AS isolation_ok, "
        "current_setting('session_replication_role')='origin' AND EXISTS ("
        "SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgrelid='platform.model_profiles'::regclass "
        "AND t.tgname='trg_model_profiles_lifecycle_fence' AND NOT t.tgisinternal "
        "AND t.tgenabled IN ('O','A') AND t.tgtype=19 AND t.tgnargs=0 "
        "AND t.tgattr=''::pg_catalog.int2vector AND t.tgqual IS NULL "
        "AND t.tgfoid=pg_catalog.to_regprocedure('platform.fence_model_profile_lifecycle()')) AS fence_ready"
    ))).mappings().one()
    if not ready["isolation_ok"]:
        raise AdmissionDenied("UNSUPPORTED_ISOLATION")
    if not ready["fence_ready"]:
        raise AdmissionDenied("LIFECYCLE_FENCE_UNAVAILABLE")
    await session.execute(text(
        "SELECT pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended("
        "'ai_res.model_profile_lifecycle:' || CAST(:profile AS uuid)::text, 0))"), {"profile": profile_id})


class ModelAdmissionGuard:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def _control(self, session: AsyncSession, profile_id: UUID) -> Any:
        await lock_profile_lifecycle(session, profile_id)
        await session.execute(text("SELECT set_config('app.model_profile_id',:profile,true)"), {"profile": str(profile_id)})
        row = (await session.execute(text(
            "SELECT profile_id,current_generation,blocked,call_sequence FROM platform.model_admission_controls "
            "WHERE profile_id=:p FOR UPDATE"), {"p": profile_id})).mappings().first()
        if row is None:
            raise AdmissionDenied("ADMISSION_MISSING")
        return row

    async def _expectation(self, session: AsyncSession, profile_id: UUID, generation: int) -> IdentityExpectation:
        row = (await session.execute(text(
            "SELECT v.profile_version,v.expectation,v.expectation_sha256,p.provider,p.provider_model_id,p.profile_version AS actual_version,"
            "p.status,p.deprecated_at,p.identity_mode,p.pinned_model_version,clock_timestamp() AS checked_at FROM platform.model_admission_versions v "
            "JOIN platform.model_profiles p ON p.id=v.profile_id WHERE v.profile_id=:p AND v.generation=:g"),
            {"p": profile_id, "g": generation})).mappings().first()
        if row is None:
            raise AdmissionDenied("ADMISSION_MISSING")
        if (row["identity_mode"] != "FLASH_OBSERVED" or row["pinned_model_version"] is not None
                or row["provider"] != "deepseek" or row["provider_model_id"] != "deepseek-flash" or row["status"] != "APPROVED"
                or row["deprecated_at"] is not None and row["deprecated_at"] <= row["checked_at"]):
            raise AdmissionDenied("PROFILE_UNAVAILABLE")
        try:
            parsed = parse_evidence(json.dumps(row["expectation"]))
        except InvalidIdentityEvidence:
            raise AdmissionDenied("ADMISSION_INVALID") from None
        if (not isinstance(parsed, IdentityExpectation) or parsed.admission_generation != generation
                or parsed.managed_versions.profile_id != profile_id
                or parsed.managed_versions.profile_version != row["profile_version"] or row["profile_version"] != row["actual_version"]
                or not hmac.compare_digest(evidence_hash(parsed), bytes(row["expectation_sha256"]))):
            raise AdmissionDenied("ADMISSION_INVALID")
        return parsed

    async def _audit(self, session: AsyncSession, profile_id: UUID, call_id: UUID, event: str, reason: str) -> None:
        await session.execute(text(
            "INSERT INTO platform.model_admission_audit(id,profile_id,call_id,event_type,reason_code) VALUES(:id,:p,:c,:e,:r)"),
            {"id": new_id(), "p": profile_id, "c": call_id, "e": event, "r": reason})

    async def begin(self, profile_id: UUID, managed_versions: ManagedVersions, *, request_ref: str) -> AdmissionTicket:
        """Commit one unresolved receipt and audit before returning. Performs no model call."""
        request_ref = _reference(request_ref)
        try:
            versions = ManagedVersions.from_dict(managed_versions.to_dict())
        except (InvalidIdentityEvidence, AttributeError):
            raise AdmissionDenied("INVALID_MANAGED_VERSIONS") from None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                control = await self._control(s, profile_id)
                if control["blocked"]:
                    raise AdmissionDenied("PROFILE_BLOCKED")
                generation = control["current_generation"]
                expected = await self._expectation(s, profile_id, generation)
                if expected.managed_versions != versions:
                    raise AdmissionDenied("MANAGED_VERSION_MISMATCH")
                existing = (await s.execute(text(
                    "SELECT id FROM platform.model_admission_calls WHERE profile_id=:p "
                    "AND (status='IN_FLIGHT' OR request_ref=:r) LIMIT 1"),
                    {"p": profile_id, "r": request_ref})).first()
                if existing is not None:
                    raise AdmissionDenied("CALL_UNRESOLVED_OR_REUSED")
                sequence = control["call_sequence"] + 1
                call_id = new_id()
                digest = evidence_hash(expected)
                await s.execute(text("UPDATE platform.model_admission_controls SET call_sequence=:n WHERE profile_id=:p"),
                                {"n": sequence, "p": profile_id})
                await s.execute(text(
                    "INSERT INTO platform.model_admission_calls(id,profile_id,generation,call_sequence,request_ref,expected_sha256) "
                    "VALUES(:id,:p,:g,:n,:r,:h)"), {"id": call_id, "p": profile_id, "g": generation, "n": sequence, "r": request_ref, "h": digest})
                await self._audit(s, profile_id, call_id, "BEGIN", "RESERVED")
                ticket = AdmissionTicket(call_id, profile_id, versions.profile_version, generation, sequence, request_ref, digest.hex())
            return ticket
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None

    async def finalize(self, ticket: AdmissionTicket, observation: IdentityObservation | str | bytes) -> None:
        """Commit validation/block before returning/raising; failure leaves durable pending.

        Matching replays are accepted only under the same still-active unblocked
        generation and exact observation hash. A stale callback cannot block or
        clear a newer generation. An unknown ticket never creates a receipt.
        """
        if not isinstance(ticket, AdmissionTicket):
            raise AdmissionDenied("INVALID_TICKET")
        # Revalidate even an internally supplied DTO instead of trusting a cast.
        AdmissionTicket(ticket.call_id, ticket.profile_id, ticket.profile_version, ticket.generation, ticket.call_sequence,
                        ticket.request_ref, ticket.expected_sha256)
        parsed: IdentityObservation | None = None
        try:
            raw = json.dumps(observation.to_dict()) if isinstance(observation, IdentityObservation) else observation
            result = parse_evidence(raw)
            if isinstance(result, IdentityObservation):
                parsed = result
        except InvalidIdentityEvidence:
            pass  # A classified malformed outcome is persisted as BLOCKED below; raw bytes are never stored.
        digest = evidence_hash(parsed) if parsed is not None else None
        refusal: str | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                control = await self._control(s, ticket.profile_id)
                if control["current_generation"] != ticket.generation:
                    raise AdmissionDenied("STALE_GENERATION")
                if control["blocked"]:
                    raise AdmissionDenied("PROFILE_BLOCKED")
                expected = await self._expectation(s, ticket.profile_id, ticket.generation)
                if expected.managed_versions.profile_version != ticket.profile_version or evidence_hash(expected).hex() != ticket.expected_sha256:
                    raise AdmissionDenied("TICKET_BINDING_MISMATCH")
                row = (await s.execute(text(
                    "SELECT id,generation,call_sequence,request_ref,expected_sha256,status,observed_sha256 "
                    "FROM platform.model_admission_calls WHERE profile_id=:p AND id=:id"),
                    {"p": ticket.profile_id, "id": ticket.call_id})).mappings().first()
                if (row is None or row["generation"] != ticket.generation or row["call_sequence"] != ticket.call_sequence
                        or row["request_ref"] != ticket.request_ref or bytes(row["expected_sha256"]).hex() != ticket.expected_sha256):
                    raise AdmissionDenied("TICKET_BINDING_MISMATCH")
                if row["status"] != "IN_FLIGHT":
                    if row["status"] == "VALIDATED" and digest is not None and hmac.compare_digest(bytes(row["observed_sha256"]), digest):
                        return
                    raise AdmissionDenied("RESULT_REUSE_MISMATCH")
                if parsed is None:
                    refusal = "MALFORMED_OBSERVATION"
                else:
                    try:
                        compare_identity(parsed, expected, current_generation=ticket.generation)
                        if parsed.request_ref != ticket.request_ref:
                            refusal = "IDENTITY_MISMATCH"
                    except IdentityMismatch:
                        refusal = "IDENTITY_MISMATCH"
                terminal = "BLOCKED" if refusal is not None else "VALIDATED"
                if refusal is not None:
                    await s.execute(text("UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=:p"), {"p": ticket.profile_id})
                await s.execute(text(
                    "UPDATE platform.model_admission_calls SET status=:status,observed_sha256=:h,finalized_at=clock_timestamp() "
                    "WHERE profile_id=:p AND id=:id"), {"status": terminal, "h": digest, "p": ticket.profile_id, "id": ticket.call_id})
                await self._audit(s, ticket.profile_id, ticket.call_id, terminal, refusal or "MATCH")
            if refusal is not None:
                raise AdmissionDenied(refusal)
        except SQLAlchemyError:
            raise AdmissionUnavailable() from None
