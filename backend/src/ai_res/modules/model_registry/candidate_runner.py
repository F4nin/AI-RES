"""Trusted development candidate orchestration, never profile admission.

Reserve is the only accounting mutation here. Only the relay may claim/settle;
errors cannot release money or repeat dispatch. The local evidence file is an
application append-only artifact, not the PostgreSQL security audit or approval.
"""
import fcntl
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.llm.candidate_payload import CandidateBody, canonicalize_candidate_body
from ai_res.llm.candidate_probe import CandidateProbeError, CandidateProbeEvidence, CandidateProbePort, ProbeOutcome, safe_probe_ref
from ai_res.modules.model_registry.poc_budget import (
    AUTHORIZATION_KEY,
    PaidLedgerDenied,
    PaidLedgerUnavailable,
    ProbeAttemptTicket,
    ProbeRequestBinding,
)
from ai_res.platform.clock import utc_now

RUN_VERSION = "flash-candidate-run/0.1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class CandidateRunDenied(ValueError):
    def __init__(self, code: str = "CANDIDATE_RUN_REFUSED") -> None:
        self.code = code if code in {"CANDIDATE_RUN_REFUSED", "HOST_UNCONFIGURED", "EVIDENCE_UNAVAILABLE", "BUDGET_DENIED",
                                    "ACCOUNTING_UNAVAILABLE", "ACCOUNTING_UNCONFIRMED", "BINDING_MISMATCH", "PROBE_REFUSED"} else "CANDIDATE_RUN_REFUSED"
        super().__init__(f"Candidate run refused: {self.code}.")


def _hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


@dataclass(frozen=True, slots=True, repr=False)
class CandidateRunManifest:
    """Profile-less managed candidate inputs supplied by trusted composition."""
    code_revision: str
    source_tree_sha256: str
    config_sha256: str
    prompt_sha256: str
    tools_sha256: str | None
    bifrost_image_sha256: str
    plan_sha256: str
    tariff_sha256: str

    def __post_init__(self) -> None:
        if (not isinstance(self.code_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", self.code_revision)
                or not all(_hash(value) for value in (self.source_tree_sha256, self.config_sha256, self.prompt_sha256,
                                                     self.bifrost_image_sha256, self.plan_sha256, self.tariff_sha256))
                or self.tools_sha256 is not None and not _hash(self.tools_sha256)):
            raise CandidateRunDenied()

    def to_dict(self) -> dict[str, Any]:
        return {"codeRevision": self.code_revision, "sourceTreeSha256": self.source_tree_sha256, "configSha256": self.config_sha256,
                "promptSha256": self.prompt_sha256, "toolsSha256": self.tools_sha256, "bifrostImageSha256": self.bifrost_image_sha256,
                "planSha256": self.plan_sha256, "tariffSha256": self.tariff_sha256}


class JsonlCandidateEvidence:
    """Exclusive bounded local append/fsync sink; preserves existing bytes."""
    def __init__(self, path: Path) -> None:
        self._path, self._fd = path, -1

    def __enter__(self) -> Self:
        try:
            self._fd = os.open(self._path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o777 != 0o600 or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Eight attempts need only small metadata records. This is a local
            # technical bound, not a product retention period or security SLO.
            if info.st_size > 1_048_576:
                raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
            existing = os.read(self._fd, info.st_size + 1)
            if existing:
                if not existing.endswith(b"\n"):
                    raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
                for line in existing.splitlines():
                    record = json.loads(line)
                    if (not isinstance(record, dict) or record.get("version") != RUN_VERSION
                            or not isinstance(record.get("kind"), str) or record["kind"] not in {"INTENT", "RESULT", "FAILED"}):
                        raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
            os.fsync(self._fd)
            # Persist creation of the directory entry as well as file content.
            parent = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            return self
        except (OSError, ValueError, TypeError, RecursionError):
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1
            raise CandidateRunDenied("EVIDENCE_UNAVAILABLE") from None

    def append(self, record: dict[str, Any]) -> None:
        if (self._fd < 0 or record.get("version") != RUN_VERSION or not isinstance(record.get("kind"), str)
                or record["kind"] not in {"INTENT", "RESULT", "FAILED"}):
            raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
        try:
            data = (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()
            if len(data) > 16_384 or os.fstat(self._fd).st_size + len(data) > 1_048_576:
                raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
            remaining = memoryview(data)
            while remaining:
                count = os.write(self._fd, remaining)
                if count <= 0:
                    raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
                remaining = remaining[count:]
            os.fsync(self._fd)
        except (OSError, ValueError, TypeError, RecursionError):
            raise CandidateRunDenied("EVIDENCE_UNAVAILABLE") from None

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


@dataclass(frozen=True, slots=True, repr=False)
class CandidateAccounting:
    state: str
    outcome: str | None
    reserved_cost: Decimal
    charged_cost: Decimal | None
    blocked: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_ref: str | None = None

    def __post_init__(self) -> None:
        if (self.state not in {"RESERVED", "CLAIMED", "SETTLED"} or type(self.blocked) is not bool
                or not isinstance(self.reserved_cost, Decimal) or not self.reserved_cost.is_finite() or self.reserved_cost <= 0
                or self.charged_cost is not None and (not isinstance(self.charged_cost, Decimal)
                                                      or not self.charged_cost.is_finite() or self.charged_cost < 0)):
            raise CandidateRunDenied("BINDING_MISMATCH")
        if self.state != "SETTLED":
            if any(value is not None for value in (self.outcome, self.charged_cost, self.input_tokens, self.output_tokens, self.provider_request_ref)):
                raise CandidateRunDenied("BINDING_MISMATCH")
        elif self.outcome not in {"KNOWN", "UNKNOWN", "INVALID_USAGE", "OVERRUN"} or self.charged_cost is None:
            raise CandidateRunDenied("BINDING_MISMATCH")
        elif self.outcome in {"KNOWN", "OVERRUN"}:
            if (type(self.input_tokens) is not int or type(self.output_tokens) is not int or self.input_tokens < 0 or self.output_tokens < 0
                    or not safe_probe_ref(self.provider_request_ref)):
                raise CandidateRunDenied("BINDING_MISMATCH")
        elif any(value is not None for value in (self.input_tokens, self.output_tokens, self.provider_request_ref)):
            raise CandidateRunDenied("BINDING_MISMATCH")

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "outcome": self.outcome, "reservedCostUsd": str(self.reserved_cost),
                "chargedCostUsd": str(self.charged_cost) if self.charged_cost is not None else None, "blocked": self.blocked,
                "inputTokens": self.input_tokens, "outputTokens": self.output_tokens, "providerRequestRef": self.provider_request_ref}


class CandidateAccountingReader:
    """Single-statement snapshot of this exact immutable attempt, no mutation."""
    def __init__(self, factory: async_sessionmaker[AsyncSession], account_id: UUID) -> None:
        if not isinstance(account_id, UUID):
            raise CandidateRunDenied()
        self._factory, self._account_id = factory, account_id

    async def read(self, ticket: ProbeAttemptTicket) -> CandidateAccounting:
        if ticket.account_id != self._account_id:
            raise CandidateRunDenied("BINDING_MISMATCH")
        try:
            async with UnitOfWork(self._factory) as uow:
                s = uow.session
                await s.execute(text("SELECT set_config('app.llm_poc_budget_id',:a,true)"), {"a": str(self._account_id)})
                row = (await s.execute(text(
                    "SELECT b.authorization_key,b.plan_sha256 AS account_plan,b.tariff_sha256 AS account_tariff,b.blocked,"
                    "a.sequence,a.request_ref,a.case_ref,a.body_sha256,a.payload_bytes,a.stream,a.max_output_tokens,"
                    "a.plan_sha256,a.tariff_sha256,a.reserved_cost,a.state,s.outcome,s.charged_cost,s.input_tokens,s.output_tokens,s.provider_request_ref "
                    "FROM platform.llm_poc_budget_accounts b JOIN platform.llm_poc_attempts a ON a.account_id=b.id "
                    "LEFT JOIN platform.llm_poc_settlements s ON s.account_id=a.account_id AND s.attempt_id=a.id "
                    "WHERE b.id=:account AND a.id=:attempt"), {"account": self._account_id, "attempt": ticket.attempt_id})).mappings().first()
                binding = ticket.binding
                if (row is None or row["authorization_key"] != AUTHORIZATION_KEY or row["sequence"] != ticket.sequence
                        or row["request_ref"] != binding.request_ref or row["case_ref"] != binding.case_ref
                        or bytes(row["body_sha256"]).hex() != binding.body_sha256 or row["payload_bytes"] != binding.payload_bytes
                        or row["stream"] is not binding.stream or row["max_output_tokens"] != binding.max_output_tokens
                        or Decimal(row["reserved_cost"]) != ticket.reserved_cost
                        or any(bytes(row[key]).hex() != expected for key, expected in (("account_plan", binding.plan_sha256),
                            ("account_tariff", binding.tariff_sha256), ("plan_sha256", binding.plan_sha256), ("tariff_sha256", binding.tariff_sha256)))):
                    raise CandidateRunDenied("BINDING_MISMATCH")
                return CandidateAccounting(row["state"], row["outcome"], Decimal(row["reserved_cost"]),
                                           Decimal(row["charged_cost"]) if row["charged_cost"] is not None else None, row["blocked"],
                                           row["input_tokens"], row["output_tokens"], row["provider_request_ref"])
        except SQLAlchemyError:
            raise CandidateRunDenied("ACCOUNTING_UNAVAILABLE") from None


class CandidateBudgetPort(Protocol):
    async def reserve(self, binding: ProbeRequestBinding) -> ProbeAttemptTicket: ...


class CandidateAccountingPort(Protocol):
    async def read(self, ticket: ProbeAttemptTicket) -> CandidateAccounting: ...


class CandidateHostGate(Protocol):
    """Concrete host authorization/key/route/freshness checks, not model approval."""
    async def validate(self, body: CandidateBody, manifest: CandidateRunManifest) -> None: ...


@dataclass(frozen=True, slots=True, repr=False)
class CandidateRunResult:
    attempt_id: UUID
    evidence: CandidateProbeEvidence
    accounting: CandidateAccounting


class CandidateRunner:
    def __init__(self, budget: CandidateBudgetPort, accounting: CandidateAccountingPort, probe: CandidateProbePort,
                 gate: CandidateHostGate, sink: JsonlCandidateEvidence) -> None:
        self._budget, self._accounting, self._probe, self._gate, self._sink = budget, accounting, probe, gate, sink

    async def run(self, body: CandidateBody, manifest: CandidateRunManifest, *, timeout_seconds: float) -> CandidateRunResult:
        if (not isinstance(body, CandidateBody) or canonicalize_candidate_body(body.content) != body or not isinstance(manifest, CandidateRunManifest)
                or type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30):
            raise CandidateRunDenied()
        with self._sink as sink:
            await self._gate.validate(body, manifest)
            binding = ProbeRequestBinding("flash-" + body.marker.hex, body.case_ref, body.body_sha256, body.payload_bytes,
                                          body.stream, body.max_output_tokens, manifest.plan_sha256, manifest.tariff_sha256)
            try:
                ticket = await self._budget.reserve(binding)
            except (PaidLedgerDenied, PaidLedgerUnavailable):
                raise CandidateRunDenied("BUDGET_DENIED") from None
            if not isinstance(ticket, ProbeAttemptTicket) or ticket.binding != binding:
                raise CandidateRunDenied("BINDING_MISMATCH")
            common = {"version": RUN_VERSION, "attemptId": str(ticket.attempt_id), "requestRef": binding.request_ref, "sequence": ticket.sequence,
                      "caseRef": body.case_ref, "codecVersion": body.codec_version, "bodySha256": body.body_sha256, "payloadBytes": body.payload_bytes,
                      "stream": body.stream, "maxOutputTokens": body.max_output_tokens, "managedCandidate": manifest.to_dict()}
            sink.append({**common, "kind": "INTENT", "recordedAt": utc_now().isoformat().replace("+00:00", "Z")})
            # A changed host condition after reservation stops here, preserving
            # the pending receipt rather than releasing money or dispatching.
            await self._gate.validate(body, manifest)
            try:
                observed = await self._probe.probe(body, timeout_seconds=timeout_seconds)
            except CandidateProbeError:
                accounting = await self._accounting.read(ticket)
                sink.append({**common, "kind": "FAILED", "recordedAt": utc_now().isoformat().replace("+00:00", "Z"),
                             "reason": "PROBE_REFUSED", "accounting": accounting.to_dict()})
                raise CandidateRunDenied("PROBE_REFUSED") from None
            accounting = await self._accounting.read(ticket)
            if (not isinstance(observed, CandidateProbeEvidence) or observed.body_sha256 != body.body_sha256 or observed.case_ref != body.case_ref):
                raise CandidateRunDenied("BINDING_MISMATCH")
            confirmed = accounting.state == "SETTLED" and not accounting.blocked and accounting.outcome == "UNKNOWN"
            if observed.outcome is ProbeOutcome.COMPLETE:
                confirmed = (accounting.state == "SETTLED" and not accounting.blocked and accounting.outcome == "KNOWN"
                             and observed.usage is not None and observed.provider_request_ref == accounting.provider_request_ref
                             and observed.usage.input_tokens == accounting.input_tokens and observed.usage.output_tokens == accounting.output_tokens)
            sink.append({**common, "kind": "RESULT", "recordedAt": utc_now().isoformat().replace("+00:00", "Z"),
                         "probe": observed.to_dict(), "accounting": accounting.to_dict(), "accountingConfirmed": confirmed})
            if not confirmed:
                raise CandidateRunDenied("ACCOUNTING_UNCONFIRMED")
            return CandidateRunResult(ticket.attempt_id, observed, accounting)
