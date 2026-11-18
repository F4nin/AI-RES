"""ADR134 fixed-account candidate claim/settlement control, not product authority.

This service cannot reserve a case, create an account, approve a profile or change
tariffs. Only immutable pre-reserved cases can be claimed. Lookup transactions end
before the existing paid ledger performs its locked final revalidation. Deployment
host authentication, tariff freshness, TLS configuration and live activation are
separate prerequisites; no model/provider call is performed here.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.llm.candidate_payload import CODEC_VERSION, MAX_OUTPUT_TOKENS
from ai_res.modules.model_registry.poc_budget import (
    AUTHORIZATION_KEY,
    PaidLedgerDenied,
    PaidLedgerUnavailable,
    ProbeAttemptTicket,
    ProbeRequestBinding,
    TechnicalPaidLedger,
)
from ai_res.platform.ids import new_id

CONTROL_VERSION = "flash-candidate-control/0.1"
BODY_CODEC_VERSION = CODEC_VERSION
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TEMPLATES = frozenset({"TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT"})
_ABSENT = object()


class CandidateControlDenied(ValueError):
    def __init__(self) -> None:
        super().__init__("Candidate control refused the operation.")


class CandidateControlUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Candidate control dependency unavailable.")


def _hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


@dataclass(frozen=True, slots=True, repr=False)
class CandidateClaimRequest:
    codec_version: str
    template_case: str
    body_sha256: str
    payload_bytes: int
    stream: bool
    max_output_tokens: int

    def __post_init__(self) -> None:
        if (self.codec_version != BODY_CODEC_VERSION or not isinstance(self.template_case, str) or self.template_case not in _TEMPLATES
                or not _hash(self.body_sha256) or type(self.payload_bytes) is not int or not 1 <= self.payload_bytes <= 4096
                or type(self.stream) is not bool or self.stream != (self.template_case in {"SSE", "CANCEL"})
                or type(self.max_output_tokens) is not int or self.max_output_tokens != MAX_OUTPUT_TOKENS):
            raise CandidateControlDenied()


@dataclass(frozen=True, slots=True, repr=False)
class CandidateSettlementRequest:
    attempt_id: UUID
    body_sha256: str
    outcome: str
    input_tokens: object = _ABSENT
    output_tokens: object = _ABSENT
    provider_request_ref: object = _ABSENT
    reason: object = _ABSENT

    def __post_init__(self) -> None:
        if (not isinstance(self.attempt_id, UUID) or not _hash(self.body_sha256) or not isinstance(self.outcome, str)
                or self.outcome not in {"KNOWN", "UNKNOWN", "INVALID_USAGE"}):
            raise CandidateControlDenied()
        # Presence matters: even explicit null in a field belonging to another
        # outcome is contradictory evidence, including at the direct DTO seam.
        mixed = (self.outcome == "KNOWN" and self.reason is not _ABSENT
                 or self.outcome == "UNKNOWN" and any(value is not _ABSENT for value in
                                                       (self.input_tokens, self.output_tokens, self.provider_request_ref)))
        if mixed or self.outcome == "INVALID_USAGE":
            object.__setattr__(self, "outcome", "INVALID_USAGE")
            for name in ("input_tokens", "output_tokens", "provider_request_ref", "reason"):
                object.__setattr__(self, name, _ABSENT)


@dataclass(frozen=True, slots=True, repr=False)
class CandidateClaimedAttempt:
    attempt_id: UUID
    request_ref: str
    body_sha256: str
    payload_bytes: int
    stream: bool
    max_output_tokens: int


@dataclass(frozen=True, slots=True, repr=False)
class CandidateSettlementResult:
    attempt_id: UUID
    outcome: str


class CandidateControlPort(Protocol):
    async def claim(self, request: CandidateClaimRequest) -> CandidateClaimedAttempt: ...

    async def settle(self, request: CandidateSettlementRequest) -> CandidateSettlementResult: ...


class CandidateControlService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], account_id: UUID, expected_plan_sha256: str, expected_tariff_sha256: str) -> None:
        if not isinstance(account_id, UUID) or not _hash(expected_plan_sha256) or not _hash(expected_tariff_sha256):
            raise CandidateControlDenied()
        self._factory, self._account_id = factory, account_id
        self._plan, self._tariff = expected_plan_sha256, expected_tariff_sha256
        self._ledger = TechnicalPaidLedger(factory, account_id)

    async def _denial_audit(self, session: AsyncSession) -> None:
        # This is the real fixed technical account, never a fabricated tenant.
        await session.execute(text("INSERT INTO platform.llm_poc_budget_audit(id,account_id,attempt_id,action,reason_code) "
                                   "VALUES(:id,:account,NULL,'DENY','BINDING_MISMATCH')"), {"id": new_id(), "account": self._account_id})

    async def _lookup(self, body_sha256: str, *, attempt_id: UUID | None = None, claim: CandidateClaimRequest | None = None) -> ProbeAttemptTicket:
        ticket: ProbeAttemptTicket | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                await s.execute(text("SELECT set_config('app.llm_poc_budget_id',:account,true)"), {"account": str(self._account_id)})
                account = (await s.execute(text("SELECT id,authorization_key,plan_sha256,tariff_sha256 FROM platform.llm_poc_budget_accounts "
                                                "WHERE id=:account"), {"account": self._account_id})).mappings().first()
                if account is not None:
                    row = (await s.execute(text("SELECT id,sequence,request_ref,case_ref,body_sha256,payload_bytes,stream,max_output_tokens,"
                                                "plan_sha256,tariff_sha256,reserved_cost,state FROM platform.llm_poc_attempts "
                                                "WHERE account_id=:account AND body_sha256=:hash "
                                                "AND (CAST(:attempt AS uuid) IS NULL OR id=CAST(:attempt AS uuid))"),
                                           {"account": self._account_id, "hash": bytes.fromhex(body_sha256), "attempt": attempt_id})).mappings().first()
                    matches = (account["authorization_key"] == AUTHORIZATION_KEY and bytes(account["plan_sha256"]).hex() == self._plan
                               and bytes(account["tariff_sha256"]).hex() == self._tariff and row is not None
                               and bytes(row["plan_sha256"]).hex() == self._plan and bytes(row["tariff_sha256"]).hex() == self._tariff)
                    if matches and row is not None and claim is not None:
                        matches = (row["state"] == "RESERVED" and row["payload_bytes"] == claim.payload_bytes and row["stream"] is claim.stream
                                   and row["max_output_tokens"] == claim.max_output_tokens and row["case_ref"] in {claim.template_case, "RECHECK"})
                    if matches and row is not None:
                        try:
                            binding = ProbeRequestBinding(row["request_ref"], row["case_ref"], bytes(row["body_sha256"]).hex(), row["payload_bytes"],
                                                          row["stream"], row["max_output_tokens"], self._plan, self._tariff)
                            ticket = ProbeAttemptTicket(self._account_id, row["id"], row["sequence"], binding, Decimal(row["reserved_cost"]))
                        except PaidLedgerDenied:
                            ticket = None
                    if ticket is None:
                        await self._denial_audit(s)
            # No DB transaction/connection from lookup survives into claim/settle.
            if ticket is None:
                raise CandidateControlDenied()
            return ticket
        except SQLAlchemyError:
            raise CandidateControlUnavailable() from None

    async def claim(self, request: CandidateClaimRequest) -> CandidateClaimedAttempt:
        ticket = await self._lookup(request.body_sha256, claim=request)
        try:
            claimed = await self._ledger.claim_dispatch(ticket, ticket.binding)
        except PaidLedgerDenied:
            raise CandidateControlDenied() from None
        except PaidLedgerUnavailable:
            raise CandidateControlUnavailable() from None
        result = claimed.ticket
        return CandidateClaimedAttempt(result.attempt_id, result.binding.request_ref, result.binding.body_sha256,
                                       result.binding.payload_bytes, result.binding.stream, result.binding.max_output_tokens)

    async def settle(self, request: CandidateSettlementRequest) -> CandidateSettlementResult:
        ticket = await self._lookup(request.body_sha256, attempt_id=request.attempt_id)
        try:
            if request.outcome == "KNOWN":
                result = await self._ledger.record_usage(ticket, input_tokens=request.input_tokens, output_tokens=request.output_tokens,
                                                        provider_request_ref=request.provider_request_ref)
            elif request.outcome == "UNKNOWN":
                reason = request.reason if isinstance(request.reason, str) else ""
                result = await self._ledger.record_unknown(ticket, reason=reason)
            else:
                result = await self._ledger.record_usage(ticket, input_tokens=None, output_tokens=None, provider_request_ref=None)
        except PaidLedgerDenied:
            # INVALID_USAGE/OVERRUN may already have committed accounting + block.
            # A controlled refusal never claims successful candidate evidence.
            raise CandidateControlDenied() from None
        except PaidLedgerUnavailable:
            raise CandidateControlUnavailable() from None
        return CandidateSettlementResult(result.attempt_id, result.outcome)
