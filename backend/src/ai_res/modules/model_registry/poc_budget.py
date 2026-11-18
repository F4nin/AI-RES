"""Bounded Flash technical ledger foundation; no runner or dispatch authority.

Amounts derive from immutable account tariffs/reservations/settlements in ai_res_db.
No caller supplies a cost, creates an account or resets its original authorization.
This module does not verify tariff freshness, authenticate a host, sign a permit,
call a model or wire the sole egress. A claim is a DB state fact, not a portable
authorization token. Missing host/tariff/relay integration still forbids live calls.

All requests bind hashes/references only, never prompt/response bytes. A RESERVED
or CLAIMED attempt surviving a crash blocks new reservations. Explicit UNKNOWN
settlement after handled failure charges the full reserve; there is no automatic
recovery, unknown refund, retry, budget extension or expiration policy here.
"""
import hashlib
import hmac
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.llm.registry import CostRates
from ai_res.platform.ids import new_id
from ai_res.platform.redaction import scan_secrets

AUTHORIZATION_KEY = "FLASH_TECHNICAL_ADMISSION_2026_11_17"
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CASES = frozenset({"TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT", "RECHECK"})
_UNKNOWN = frozenset({"TIMEOUT", "CANCEL", "NETWORK", "PROVIDER_ERROR", "UNTRUSTED_RESPONSE"})
_ACCOUNT_COLUMNS = ("id,authorization_key,currency,max_cost,original_spend,max_attempts,input_bound,output_bound,body_bound,"
                    "provider,model_id,http_method,upstream_host,upstream_path,plan_sha256,tariff_sha256,"
                    "input_per_million,output_per_million,attempt_sequence,blocked")


class PaidLedgerDenied(ValueError):
    def __init__(self, code: str = "BINDING_MISMATCH") -> None:
        super().__init__("Technical paid ledger refused the operation.")
        self.code = code


class PaidLedgerUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Technical paid ledger dependency unavailable.")


def _ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_REF.fullmatch(value)) and not scan_secrets(value).found


def _hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


@dataclass(frozen=True, slots=True, repr=False)
class ProbeRequestBinding:
    request_ref: str
    case_ref: str
    body_sha256: str
    payload_bytes: int
    stream: bool
    max_output_tokens: int
    plan_sha256: str
    tariff_sha256: str
    provider: str = "deepseek"
    model_id: str = "deepseek-flash"
    method: str = "POST"
    host: str = "api.deepseek.com"
    path: str = "/chat/completions"

    def __post_init__(self) -> None:
        if (not _ref(self.request_ref) or not isinstance(self.case_ref, str) or self.case_ref not in _CASES
                or not all(_hash(value) for value in (self.body_sha256, self.plan_sha256, self.tariff_sha256))
                or type(self.payload_bytes) is not int or not 1 <= self.payload_bytes <= 4096 or type(self.stream) is not bool
                or type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 256
                or (self.provider, self.model_id, self.method, self.host, self.path)
                != ("deepseek", "deepseek-flash", "POST", "api.deepseek.com", "/chat/completions")):
            raise PaidLedgerDenied()


@dataclass(frozen=True, slots=True, repr=False)
class ProbeAttemptTicket:
    account_id: UUID
    attempt_id: UUID
    sequence: int
    binding: ProbeRequestBinding
    reserved_cost: Decimal

    def __post_init__(self) -> None:
        if (not isinstance(self.account_id, UUID) or not isinstance(self.attempt_id, UUID)
                or type(self.sequence) is not int or not 1 <= self.sequence <= 8 or not isinstance(self.binding, ProbeRequestBinding)
                or not isinstance(self.reserved_cost, Decimal) or not self.reserved_cost.is_finite() or not 0 < self.reserved_cost <= 10):
            raise PaidLedgerDenied()
        replace(self.binding)


@dataclass(frozen=True, slots=True, repr=False)
class DispatchClaim:
    """Committed one-use claim mechanics, never a bearer permission for a relay."""
    ticket: ProbeAttemptTicket


@dataclass(frozen=True, slots=True, repr=False)
class SettlementSnapshot:
    attempt_id: UUID
    outcome: str
    charged_cost: Decimal
    replay: bool


@dataclass(frozen=True, slots=True, repr=False)
class PaidBalance:
    cap: Decimal
    used_or_reserved: Decimal
    remaining: Decimal
    attempts: int
    blocked: bool
    pending: bool


@dataclass(frozen=True, slots=True, repr=False)
class _UsageFact:
    outcome: str
    reason: str
    input_tokens: int | None
    output_tokens: int | None
    provider_ref: str | None

    def proof(self) -> bytes:
        value = {"kind": self.outcome, "reason": self.reason, "inputTokens": self.input_tokens,
                 "outputTokens": self.output_tokens, "providerRequestRef": self.provider_ref}
        return hashlib.sha256(canonical_json(value).encode()).digest()


class TechnicalPaidLedger:
    def __init__(self, factory: async_sessionmaker[AsyncSession], account_id: UUID) -> None:
        if not isinstance(account_id, UUID):
            raise PaidLedgerDenied("ACCOUNT_MISSING")
        self._factory, self._account_id = factory, account_id

    async def _account(self, session: AsyncSession, *, lock: bool = True) -> Any:
        await session.execute(text("SELECT set_config('app.llm_poc_budget_id',:a,true)"), {"a": str(self._account_id)})
        suffix = " FOR UPDATE" if lock else ""
        row = (await session.execute(text(f"SELECT {_ACCOUNT_COLUMNS} FROM platform.llm_poc_budget_accounts WHERE id=:a{suffix}"),  # noqa: S608
                                     {"a": self._account_id})).mappings().first()
        if row is None or row["authorization_key"] != AUTHORIZATION_KEY:
            # No account exists to anchor an audit. Never manufacture one.
            raise PaidLedgerDenied("ACCOUNT_MISSING")
        return row

    async def _used(self, session: AsyncSession, original_spend: Decimal) -> Decimal:
        amount = (await session.execute(text(
            "SELECT coalesce(sum(coalesce(s.charged_cost,a.reserved_cost)),0) FROM platform.llm_poc_attempts a "
            "LEFT JOIN platform.llm_poc_settlements s ON s.account_id=a.account_id AND s.attempt_id=a.id WHERE a.account_id=:a"),
            {"a": self._account_id})).scalar_one()
        return original_spend + Decimal(amount)

    async def _audit(self, session: AsyncSession, action: str, reason: str, attempt: UUID | None = None) -> None:
        await session.execute(text("INSERT INTO platform.llm_poc_budget_audit(id,account_id,attempt_id,action,reason_code) VALUES(:id,:a,:t,:act,:r)"),
                              {"id": new_id(), "a": self._account_id, "t": attempt, "act": action, "r": reason})

    async def _deny(self, session: AsyncSession, reason: str, attempt: UUID | None = None) -> PaidLedgerDenied:
        await self._audit(session, "DENY", reason, attempt)
        return PaidLedgerDenied(reason)  # Raise only after the caller's audit commits.

    def _account_binding(self, account: Any, binding: ProbeRequestBinding) -> bool:
        return (bytes(account["plan_sha256"]).hex() == binding.plan_sha256 and bytes(account["tariff_sha256"]).hex() == binding.tariff_sha256
                and binding.payload_bytes <= account["body_bound"] and binding.max_output_tokens <= account["output_bound"]
                and (binding.provider, binding.model_id, binding.method, binding.host, binding.path)
                == (account["provider"], account["model_id"], account["http_method"], account["upstream_host"], account["upstream_path"]))

    async def balance(self) -> PaidBalance:
        try:
            async with UnitOfWork(self._factory) as uow:
                account = await self._account(uow.session)
                used = await self._used(uow.session, Decimal(account["original_spend"]))
                pending = (await uow.session.execute(text("SELECT 1 FROM platform.llm_poc_attempts WHERE account_id=:a "
                                                         "AND state IN ('RESERVED','CLAIMED') LIMIT 1"), {"a": self._account_id})).first() is not None
                cap = Decimal(account["max_cost"])
                return PaidBalance(cap, used, cap-used, account["attempt_sequence"], account["blocked"], pending)
        except SQLAlchemyError:
            raise PaidLedgerUnavailable() from None

    async def reserve(self, binding: ProbeRequestBinding) -> ProbeAttemptTicket:
        binding = replace(binding)  # Strict validation without retaining raw request data.
        denied: PaidLedgerDenied | None = None
        ticket: ProbeAttemptTicket | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                account = await self._account(s)
                reason: str | None = None
                if account["blocked"]:
                    reason = "ACCOUNT_BLOCKED"
                elif not self._account_binding(account, binding):
                    reason = "BINDING_MISMATCH"
                else:
                    previous = (await s.execute(text("SELECT request_ref,body_sha256 FROM platform.llm_poc_attempts WHERE account_id=:a "
                                                     "AND (request_ref=:r OR body_sha256=:b) LIMIT 1"),
                                                {"a": self._account_id, "r": binding.request_ref, "b": bytes.fromhex(binding.body_sha256)})).mappings().first()
                    pending = (await s.execute(text("SELECT 1 FROM platform.llm_poc_attempts WHERE account_id=:a "
                                                    "AND state IN ('RESERVED','CLAIMED') LIMIT 1"), {"a": self._account_id})).first()
                    if previous is not None:
                        reason = "REQUEST_REUSED" if previous["request_ref"] == binding.request_ref else "BODY_REUSED"
                    elif pending is not None:
                        reason = "PENDING"
                    elif account["attempt_sequence"] >= account["max_attempts"]:
                        reason = "ATTEMPTS_EXHAUSTED"
                rates = CostRates(currency=account["currency"], input_per_million=Decimal(account["input_per_million"]),
                                  output_per_million=Decimal(account["output_per_million"]))
                reservation = rates.cost(account["input_bound"], account["output_bound"])
                used = await self._used(s, Decimal(account["original_spend"]))
                if reason is None and used+reservation > Decimal(account["max_cost"]):
                    reason = "BUDGET_EXHAUSTED"
                if reason is not None:
                    denied = await self._deny(s, reason)
                else:
                    sequence = account["attempt_sequence"]+1
                    attempt = new_id()
                    await s.execute(text("UPDATE platform.llm_poc_budget_accounts SET attempt_sequence=:n WHERE id=:a"),
                                    {"n": sequence, "a": self._account_id})
                    row = (await s.execute(text("INSERT INTO platform.llm_poc_attempts(id,account_id,sequence,request_ref,case_ref,body_sha256,"
                                                "payload_bytes,stream,max_output_tokens) VALUES(:id,:a,:n,:r,:c,:b,:size,:stream,:out) "
                                                "RETURNING reserved_cost"),
                                           {"id": attempt, "a": self._account_id, "n": sequence, "r": binding.request_ref, "c": binding.case_ref,
                                            "b": bytes.fromhex(binding.body_sha256), "size": binding.payload_bytes, "stream": binding.stream,
                                            "out": binding.max_output_tokens})).first()
                    assert row is not None
                    await self._audit(s, "RESERVE", "RESERVED", attempt)
                    ticket = ProbeAttemptTicket(self._account_id, attempt, sequence, binding, Decimal(row[0]))
            if denied is not None:
                raise denied
            assert ticket is not None
            return ticket
        except SQLAlchemyError:
            raise PaidLedgerUnavailable() from None

    async def _attempt(self, session: AsyncSession, account: Any, ticket: ProbeAttemptTicket) -> Any:
        if ticket.account_id != self._account_id or not self._account_binding(account, ticket.binding):
            return None
        row = (await session.execute(text("SELECT id,sequence,request_ref,case_ref,body_sha256,payload_bytes,stream,max_output_tokens,"
                                          "plan_sha256,tariff_sha256,reserved_cost,state FROM platform.llm_poc_attempts "
                                          "WHERE account_id=:a AND id=:t"), {"a": self._account_id, "t": ticket.attempt_id})).mappings().first()
        binding = ticket.binding
        if (row is None or row["sequence"] != ticket.sequence or row["request_ref"] != binding.request_ref or row["case_ref"] != binding.case_ref
                or bytes(row["body_sha256"]).hex() != binding.body_sha256 or row["payload_bytes"] != binding.payload_bytes
                or row["stream"] is not binding.stream or row["max_output_tokens"] != binding.max_output_tokens
                or bytes(row["plan_sha256"]).hex() != binding.plan_sha256 or bytes(row["tariff_sha256"]).hex() != binding.tariff_sha256
                or Decimal(row["reserved_cost"]) != ticket.reserved_cost):
            return None
        return row

    async def claim_dispatch(self, ticket: ProbeAttemptTicket, binding: ProbeRequestBinding) -> DispatchClaim:
        ticket, binding = replace(ticket), replace(binding)
        denied: PaidLedgerDenied | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                account = await self._account(s)
                attempt = await self._attempt(s, account, ticket)
                if ticket.binding != binding or attempt is None:
                    denied = await self._deny(s, "BINDING_MISMATCH")
                elif account["blocked"]:
                    denied = await self._deny(s, "ACCOUNT_BLOCKED", ticket.attempt_id)
                elif attempt["state"] != "RESERVED":
                    denied = await self._deny(s, "CLAIM_REPLAY", ticket.attempt_id)
                else:
                    await s.execute(text("UPDATE platform.llm_poc_attempts SET state='CLAIMED' WHERE account_id=:a AND id=:t"),
                                    {"a": self._account_id, "t": ticket.attempt_id})
                    await self._audit(s, "CLAIM", "CLAIMED", ticket.attempt_id)
            if denied is not None:
                raise denied
            return DispatchClaim(ticket)
        except SQLAlchemyError:
            raise PaidLedgerUnavailable() from None

    async def record_usage(self, ticket: ProbeAttemptTicket, *, input_tokens: object, output_tokens: object,
                           provider_request_ref: object) -> SettlementSnapshot:
        if (type(input_tokens) is int and type(output_tokens) is int and 0 <= input_tokens <= 9_223_372_036_854_775_807
                and 0 <= output_tokens <= 9_223_372_036_854_775_807 and _ref(provider_request_ref)):
            fact = _UsageFact("KNOWN", "USAGE", input_tokens, output_tokens, str(provider_request_ref))
        else:
            fact = _UsageFact("INVALID_USAGE", "INVALID_USAGE", None, None, None)
        return await self._settle(replace(ticket), fact)

    async def record_unknown(self, ticket: ProbeAttemptTicket, *, reason: str) -> SettlementSnapshot:
        fact = (_UsageFact("UNKNOWN", reason, None, None, None) if isinstance(reason, str) and reason in _UNKNOWN
                else _UsageFact("INVALID_USAGE", "INVALID_USAGE", None, None, None))
        return await self._settle(replace(ticket), fact)

    async def _settle(self, ticket: ProbeAttemptTicket, fact: _UsageFact) -> SettlementSnapshot:
        denied: PaidLedgerDenied | None = None
        result: SettlementSnapshot | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                account = await self._account(s)
                attempt = await self._attempt(s, account, ticket)
                if attempt is None:
                    denied = await self._deny(s, "BINDING_MISMATCH")
                else:
                    prior = (await s.execute(text("SELECT outcome,charged_cost,proof_sha256 FROM platform.llm_poc_settlements "
                                                  "WHERE account_id=:a AND attempt_id=:t"),
                                             {"a": self._account_id, "t": ticket.attempt_id})).mappings().first()
                    if prior is not None:
                        if hmac.compare_digest(bytes(prior["proof_sha256"]), fact.proof()):
                            result = SettlementSnapshot(ticket.attempt_id, prior["outcome"], Decimal(prior["charged_cost"]), True)
                        else:
                            await s.execute(text("UPDATE platform.llm_poc_budget_accounts SET blocked=true WHERE id=:a"), {"a": self._account_id})
                            denied = await self._deny(s, "SETTLEMENT_CONFLICT", ticket.attempt_id)
                    elif attempt["state"] != "CLAIMED":
                        denied = await self._deny(s, "INVALID_STATE", ticket.attempt_id)
                    else:
                        row = (await s.execute(text("INSERT INTO platform.llm_poc_settlements(id,account_id,attempt_id,outcome,reason_code,"
                                                    "input_tokens,output_tokens,provider_request_ref,proof_sha256) "
                                                    "VALUES(:id,:a,:t,:o,:r,:i,:out,:ref,:hash) RETURNING outcome,charged_cost"),
                                               {"id": new_id(), "a": self._account_id, "t": ticket.attempt_id, "o": fact.outcome, "r": fact.reason,
                                                "i": fact.input_tokens, "out": fact.output_tokens, "ref": fact.provider_ref, "hash": fact.proof()})).first()
                        assert row is not None
                        result = SettlementSnapshot(ticket.attempt_id, row[0], Decimal(row[1]), False)
                        action = "BLOCK" if result.outcome in ("OVERRUN", "INVALID_USAGE") else "SETTLE"
                        await self._audit(s, action, result.outcome, ticket.attempt_id)
            if denied is not None:
                raise denied
            assert result is not None
            if result.outcome in ("OVERRUN", "INVALID_USAGE"):
                raise PaidLedgerDenied(result.outcome)  # Charge + sticky block + audit have already committed.
            return result
        except SQLAlchemyError:
            raise PaidLedgerUnavailable() from None
