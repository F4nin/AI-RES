"""Trusted standalone operator: candidate evidence or an admitted Requirements call.

This is not a Worker Runtime. API credentials and the owner's session stay here,
never in messages, Bifrost, relay, WorkerResult, logs, or Temporal history.
"""
import argparse
import asyncio
import importlib
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm.admission import ObservedAdmissionCall
from ai_res.llm.errors import InvalidRequest, LLMError, LLMErrorCode
from ai_res.llm.gateway import GovernedLLMGateway
from ai_res.llm.observed_identity import IdentityExpectation, ManagedVersions, extract_bifrost_observation
from ai_res.llm.registry import ProfileStatus
from ai_res.llm.transport import TransportCall, TransportResult
from ai_res.llm.types import LLMLimits, LLMRequest, LLMResponse
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.admission import ModelAdmissionGuard, evidence_hash
from ai_res.modules.model_registry.gateway_admission import ModelRegistryAdmission
from ai_res.modules.model_registry.repository import load_model_registry
from ai_res.platform.config import load_settings
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.redaction import scan_secrets
from ai_res.policy.config import parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine
from ai_res.worker_contracts.validation import WorkerContracts

from .common import (
    ORGANIZATION_ID,
    OWNER_ID,
    PROFILE_ID,
    SliceBifrostTransport,
    SliceRefused,
    canonical,
    decode,
    digest,
    load_plan,
    messages,
    native_body,
    read_owned,
    source_from_plan,
    write_new,
)
from .ledger import SliceBalance, SliceLedger
from .requirements import ExperimentIds, SliceValidationError, Source, ValidatedResult, validate_response

PLAN = Path("/config")
RESULTS = Path("/results")
WALLET = Path("/wallet/ledger.jsonl")
MAX_CAPTURE_PAYLOAD_BYTES = 2_097_152  # Same normalized-response bound as the Bifrost adapter.
MAX_CAPTURE_BYTES = MAX_CAPTURE_PAYLOAD_BYTES + 65_536
MAX_CAPTURE_SCAN_DEPTH = 32
MAX_CAPTURE_SCAN_TEXT_BYTES = 16_777_216
MAX_CAPTURE_SCAN_VALUES = 100_000
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_VALIDATION_REASONS = frozenset({"BAD_SOURCE", "BAD_IDS", "BAD_REQUEST_REF", "INPUT_SECRET", "OUTPUT_SECRET", "BAD_RESPONSE",
    "MALFORMED_JSON", "RESULT_REJECTED", "ID_MISMATCH", "UNGROUNDED_FINDING", "TYPE_MISMATCH", "INJECTION_DETECTED"})


class DiagnosticRefused(SliceRefused):
    def __init__(self, reason: str) -> None:
        allowed = _VALIDATION_REASONS | {"CAPTURE_UNAVAILABLE", "CAPTURE_REFUSED", "ACCOUNTING_UNCONFIRMED",
            "QUARANTINE_MISMATCH", "VALIDATION_UNAVAILABLE", "DIAGNOSTIC_UNAVAILABLE", "GATEWAY_UNAVAILABLE"}
        self.reason = reason if reason in allowed or reason in {item.value for item in LLMErrorCode} else "VALIDATION_UNAVAILABLE"
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class QuarantineReceipt:
    request_ref: str
    filename: str
    sha256: str
    payload_sha256: str
    size_bytes: int
    received_at: str


def _private_results(directory: Path, request_ref: str) -> None:
    info = directory.lstat()
    if (not isinstance(request_ref, str) or not _REF.fullmatch(request_ref) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise DiagnosticRefused("CAPTURE_REFUSED")


def _model_payload(response: TransportResult | LLMResponse) -> dict[str, Any]:
    observed = response.observation if isinstance(response, TransportResult) else response.identity.observation
    return {"output": response.output, "finishReason": response.finish_reason.value,
            "usage": {
                "inputTokens": response.usage.input_tokens,
                "outputTokens": response.usage.output_tokens,
            },
            "toolCalls": [{"callId": item.call_id, "name": item.name, "arguments": dict(item.arguments)} for item in response.tool_calls],
            "providerRequestRef": response.provider_request_ref, "observation": None if observed is None else observed.to_dict()}


def _screen_capture(payload: dict[str, Any]) -> None:
    # Every stage may contain JSON inside a string (for example bootstrap's
    # choices[].message.content). Repeated decoding is screening, not acceptance.
    stack: list[tuple[Any, int]] = [(payload, 0)]
    seen: set[str] = set()
    text_bytes, values = 0, 0
    while stack:
        item, depth = stack.pop()
        values += 1
        if depth > MAX_CAPTURE_SCAN_DEPTH or values > MAX_CAPTURE_SCAN_VALUES:
            raise DiagnosticRefused("CAPTURE_REFUSED")
        if isinstance(item, str):
            if item in seen:
                continue
            seen.add(item)
            try:
                text_bytes += len(item.encode("utf-8"))
            except UnicodeError:
                raise DiagnosticRefused("CAPTURE_REFUSED") from None
            if text_bytes > MAX_CAPTURE_SCAN_TEXT_BYTES:
                raise DiagnosticRefused("CAPTURE_REFUSED")
            if scan_secrets(item).found:
                raise DiagnosticRefused("OUTPUT_SECRET")
            try:
                # Keep all duplicate-key values; last-value-wins parsing could
                # discard a credential before it reaches this rejection screen.
                decoded = json.loads(item, object_pairs_hook=list)
            except json.JSONDecodeError:
                continue  # Malformed nonsecret output remains capturable data.
            except (ValueError, TypeError, RecursionError, OverflowError):
                raise DiagnosticRefused("CAPTURE_REFUSED") from None
            stack.append((decoded, depth + 1))
        elif isinstance(item, dict):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list | tuple):
            stack.extend((value, depth + 1) for value in item)


def capture_quarantine(payload: dict[str, Any], *, request_ref: str, directory: Path,
                       stage: str = "transport") -> QuarantineReceipt:
    """Private normalized transport output, never an accepted WorkerResult.

    Upstream relay guards have already run. This is an explicitly untrusted local
    diagnostic, not raw HTTP, a domain artifact, or a telemetry/logging payload.
    """
    if stage not in {"transport", "bootstrap"}:
        raise DiagnosticRefused("CAPTURE_REFUSED")
    _private_results(directory, request_ref)
    encoded = canonical(payload)
    if len(encoded) > MAX_CAPTURE_PAYLOAD_BYTES:
        raise DiagnosticRefused("CAPTURE_REFUSED")
    _screen_capture(payload)
    received_at = datetime.now(UTC).isoformat()
    filename = f"{stage}-quarantine-{request_ref}.json"
    artifact = {"version": "slice01-quarantine/1", "status": "UNTRUSTED_TRANSPORT_OUTPUT", "stage": stage,
                "requestRef": request_ref, "receivedAt": received_at,
                "gatewayFinalization": "NOT_YET_CONFIRMED", "accounting": "NOT_YET_CONFIRMED", "response": payload}
    raw = canonical(artifact) + b"\n"
    if len(raw) > MAX_CAPTURE_BYTES:
        raise DiagnosticRefused("CAPTURE_REFUSED")
    write_new(directory / filename, artifact)
    return QuarantineReceipt(request_ref, filename, digest(raw), digest(encoded), len(raw), received_at)


def _machine_error(error: Exception) -> str:
    return error.code.value if isinstance(error, LLMError) and isinstance(error.code, LLMErrorCode) else "GATEWAY_UNAVAILABLE"


def _diagnostic(directory: Path, request_ref: str, stage: str, data: dict[str, Any]) -> None:
    try:
        if stage not in {"transport-error", "gateway-error", "validation"} or len(canonical(data)) > 65_536:
            raise DiagnosticRefused("DIAGNOSTIC_UNAVAILABLE")
        _private_results(directory, request_ref)
        write_new(directory / f"{stage}-{request_ref}.json", {"version": "slice01-diagnostic/1", "requestRef": request_ref, **data})
    except Exception:
        raise DiagnosticRefused("DIAGNOSTIC_UNAVAILABLE") from None


class CapturingTransport(SliceBifrostTransport):
    """Persist normalized output before the gateway finalizes observed admission."""
    def __init__(self, *, request_ref: str, results_dir: Path, **kwargs: Any) -> None:
        _private_results(results_dir, request_ref)
        self.request_ref, self.results_dir = request_ref, results_dir
        self.receipt: QuarantineReceipt | None = None
        self.capture_error: str | None = None
        self._attempted = False
        super().__init__(**kwargs)

    async def complete(self, call: TransportCall) -> TransportResult:
        if call.request_id != self.request_ref or self._attempted:
            raise InvalidRequest("SLICE transport request refused")
        self._attempted = True
        try:
            result = await super().complete(call)
        except Exception as error:
            _diagnostic(self.results_dir, self.request_ref, "transport-error",
                        {"status": "TRANSPORT_FAILED", "reason": _machine_error(error)})
            raise
        try:
            self.receipt = capture_quarantine(_model_payload(result), request_ref=self.request_ref, directory=self.results_dir)
        except Exception as error:
            # Preserve real gateway finalization/accounting even if local capture
            # fails. The producer withholds the result after the gateway returns.
            self.capture_error = error.reason if isinstance(error, DiagnosticRefused) else "CAPTURE_UNAVAILABLE"
        return result


def capture_and_validate(response: LLMResponse, source: Source, ids: ExperimentIds, contracts: WorkerContracts,
                         *, request_ref: str, capture: QuarantineReceipt, balance: SliceBalance,
                         confirmed: bool, directory: Path) -> ValidatedResult:
    if not confirmed or balance.pending or balance.blocked:
        raise DiagnosticRefused("ACCOUNTING_UNCONFIRMED")
    _private_results(directory, request_ref)
    if (capture.request_ref != request_ref or capture.filename != f"transport-quarantine-{request_ref}.json"
            or capture.payload_sha256 != digest(canonical(_model_payload(response)))
            or digest(read_owned(directory / capture.filename, limit=MAX_CAPTURE_BYTES)) != capture.sha256):
        raise DiagnosticRefused("QUARANTINE_MISMATCH")
    receipt = {"quarantineFile": capture.filename, "quarantineSha256": capture.sha256,
               "quarantineBytes": capture.size_bytes, "receivedAt": capture.received_at, "accounting": "CONFIRMED",
               "usage": {
                   "inputTokens": response.usage.input_tokens,
                   "outputTokens": response.usage.output_tokens,
               },
               "usedOrReservedUSD": str(balance.used_or_reserved), "remainingUSD": str(balance.remaining)}
    try:
        accepted = validate_response(response, source, ids, contracts)
    except Exception as error:
        reason = error.code if isinstance(error, SliceValidationError) and error.code in _VALIDATION_REASONS else "VALIDATION_UNAVAILABLE"
        _diagnostic(directory, request_ref, "validation", {**receipt, "status": "REJECTED", "reason": reason})
        raise DiagnosticRefused(reason) from None
    _diagnostic(directory, request_ref, "validation", {**receipt, "status": "PASSED", "reason": "DETERMINISTIC_CHECKS_PASSED"})
    return accepted


def experiment_target(plan: dict[str, Any]) -> tuple[ProfileStatus, int]:
    status, generation = plan.get("profileStatus", "CANDIDATE"), plan.get("admissionGeneration", 1)
    version = plan.get("experimentVersion", "1")
    if (not isinstance(version, str) or not 1 <= len(version) <= 4 or not version.isascii() or not version.isdecimal()
            or not 1 <= int(version) <= 1000 or str(int(version)) != version):
        raise SliceRefused("EXPERIMENT_TARGET_INVALID")
    if (status not in {"CANDIDATE", "APPROVED"} or type(generation) is not int or generation < 1
            or status == "CANDIDATE" and generation != 1
            or status == "APPROVED" and (generation < 2 or version == "1")):
        raise SliceRefused("EXPERIMENT_TARGET_INVALID")
    return ProfileStatus(status), generation


def library_sha256() -> str:
    module = importlib.import_module("ai_res")
    if module.__file__ is None:
        raise SliceRefused("LIBRARY_UNAVAILABLE")
    root = Path(module.__file__).parent
    return digest(canonical([(p.relative_to(root).as_posix(), digest(p.read_bytes()))
                             for p in sorted(root.rglob("*.py"))]))


class ConfirmedLedger:
    """Expose swallowed gateway settlement failures to the publishing caller."""
    def __init__(self, ledger: SliceLedger) -> None:
        self.ledger, self.confirmed = ledger, False

    async def reserve(self, *args: Any, **kwargs: Any) -> Any:
        return await self.ledger.reserve(*args, **kwargs)

    async def settle(self, *args: Any, **kwargs: Any) -> None:
        await self.ledger.settle(*args, **kwargs)
        self.confirmed = True

    async def release(self, *args: Any, **kwargs: Any) -> None:
        await self.ledger.release(*args, **kwargs)


async def execute(phase: str) -> dict[str, Any]:
    preflight = phase == "preflight"
    if preflight:
        phase = "bootstrap"
    plan = load_plan(PLAN)
    bootstrap_status, admission_generation = experiment_target(plan)
    required_status = bootstrap_status if phase == "bootstrap" else ProfileStatus.APPROVED
    if plan["mode"] != "live" or phase not in {"bootstrap", "run"}:
        raise SliceRefused("LIVE_PHASE_REQUIRED")
    if library_sha256() != plan["librarySha256"]:
        raise SliceRefused("LIBRARY_CHANGED")
    contract_raw = read_owned(Path("/worker-contract.json"))
    if digest(contract_raw) != plan["workerContractSha256"]:
        raise SliceRefused("CONTRACT_CHANGED")
    contracts = WorkerContracts(decode(contract_raw))
    settings = load_settings(os.environ)
    if settings.db_user != "ai_res_api" or settings.db_sslmode != "verify-full":
        raise SliceRefused("API_IDENTITY_REQUIRED")
    engine = create_runtime_engine(settings)
    factory = create_session_factory(engine)
    ledger = SliceLedger(WALLET, manifest_sha256=plan["manifestSha256"])
    policy_raw = read_owned(PLAN / "policy.json")
    config = parse_policy_config(policy_raw, plan["policySha256"])
    policy = PolicyEnforcer(PolicyEngine(config, factory), factory, config, timeout_seconds=settings.policy_timeout_seconds)
    sessions = SessionService(factory, idle=timedelta(seconds=settings.session_idle_seconds),
        absolute=timedelta(seconds=settings.session_absolute_seconds), touch_interval=timedelta(seconds=settings.session_touch_interval_seconds))
    session_file = decode(read_owned(Path("/run/secrets/owner_session.json")))
    session_token = session_file["sessionToken"]
    versions = ManagedVersions.from_dict(plan["managedVersions"])
    request_ref = plan["phases"][phase]

    async def authorize(profile: Any, request: LLMRequest) -> bool:
        if load_plan(PLAN) != plan or request.request_id != request_ref or request.budget_scope != request_ref:
            raise SliceRefused("REQUEST_CHANGED")
        auth = await sessions.authenticate(session_token)
        actor = auth.session
        if (actor is None or actor.user_id != OWNER_ID or actor.organization_id != ORGANIZATION_ID
                or actor.second_factor_pending or actor.mfa_verified_at is None):
            raise SliceRefused("OWNER_MFA_SESSION_REQUIRED")
        req = PolicyRequest(actor_id=str(actor.user_id), organization_id=str(actor.organization_id),
            action="slice01.invoke", resource_type="SLICE01_REQUEST", resource_id=str(PROFILE_ID),
            attributes={"actor_type": "USER", "mfa_verified": True})
        decision = await policy.decide(req)  # no DB transaction held across Policy I/O
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(actor.organization_id)
            await policy.lock_subject_grants(uow.session, actor.user_id, actor.organization_id, None)
            factors = (await uow.session.execute(text(
                "SELECT id FROM iam.mfa_factors WHERE organization_id=:o AND user_id=:u "
                "AND status='ACTIVE' ORDER BY id FOR SHARE"), {"o": ORGANIZATION_ID, "u": OWNER_ID})).scalars().all()
            if not factors:
                raise SliceRefused("OWNER_MFA_SESSION_REQUIRED")
            if not await lock_authenticated_session(uow.session, actor):
                raise SliceRefused("OWNER_MFA_SESSION_REQUIRED")
            owner = (await uow.session.execute(text(
                "SELECT 1 FROM organization.memberships m JOIN iam.users u ON u.id=m.user_id AND u.organization_id=m.organization_id "
                "WHERE m.organization_id=:o AND m.user_id=:u AND m.role_code='ORGANIZATION_OWNER' "
                "AND m.status='ACTIVE' AND u.status='ACTIVE'"), {"o": ORGANIZATION_ID, "u": OWNER_ID})).scalar_one_or_none()
            facts = (await uow.session.execute(text(
                "SELECT p.status,(p.deprecated_at IS NULL OR p.deprecated_at>clock_timestamp()) AS available,"
                "((to_jsonb(p)-'status'-'approved_at'-'approved_by'-'deprecated_at')::text) AS immutable "
                "FROM platform.model_profiles p WHERE p.id=:p"), {"p": PROFILE_ID})).mappings().one()
            if (owner != 1 or facts["available"] is not True
                    or digest(facts["immutable"].encode()) != plan["immutableProfileSha256"]
                    or facts["status"] != required_status.value
                    or profile.id != PROFILE_ID or request.model_profile_id != PROFILE_ID):
                raise SliceRefused("PROFILE_OR_OWNER_CHANGED")
            if phase == "bootstrap" and bootstrap_status is ProfileStatus.APPROVED:
                await uow.session.execute(text("SELECT set_config('app.model_profile_id',:p,true)"), {"p": str(PROFILE_ID)})
                control = (await uow.session.execute(text(
                    "SELECT c.current_generation,c.blocked FROM platform.model_admission_controls c "
                    "JOIN platform.model_admission_versions v ON v.profile_id=c.profile_id AND v.generation=c.current_generation "
                    "WHERE c.profile_id=:p"),
                    {"p": PROFILE_ID})).mappings().first()
                pending = (await uow.session.execute(text(
                    "SELECT EXISTS(SELECT 1 FROM platform.model_admission_calls WHERE profile_id=:p AND status='IN_FLIGHT')"),
                    {"p": PROFILE_ID})).scalar_one()
                if (control is None or control["blocked"] or pending
                        or control["current_generation"] + 1 != admission_generation):
                    raise SliceRefused("PROBE_ADMISSION_NOT_READY")
            await policy.record_allow(req, decision, session=uow.session)
        return True

    try:
        async with UnitOfWork(factory) as uow:
            registry = await load_model_registry(uow.session)
        profile = registry.get(PROFILE_ID)
        if profile is None or profile.status is not required_status:
            raise SliceRefused("PROFILE_NOT_READY")
        request = LLMRequest(request_id=request_ref, model_profile_id=PROFILE_ID, purpose="SLICE01",
            messages=messages(plan, phase), budget_scope=request_ref, data_classification="INTERNAL", limits=LLMLimits(2048, 30))
        await authorize(profile, request)
        if preflight:
            return {"status": "OWNER_MFA_POLICY_PROFILE_VALIDATED", "providerCalls": 0, "reservedUSD": "0"}
        key = "sk-bf-" + read_owned(Path("/run/secrets/bifrost_virtual_key")).decode().strip()
        if phase == "bootstrap":
            reservation = await ledger.reserve(request_ref, tokens=2048, cost=Decimal(0), currency="USD")
            await authorize(profile, request)
            await ledger.arm(request_ref)
            start = time.monotonic()
            # Explicit quarantined configuration probe, separate from admitted
            # Requirements execution. Actual profile status is never cloned.
            async with (
                httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as client,
                client.stream("POST", "http://bifrost-poc:8080/v1/chat/completions",
                    content=canonical(native_body(request.messages)), headers={"x-bf-vk": key,
                        "content-type": "application/json", "accept-encoding": "identity", "x-request-id": request_ref}) as raw,
            ):
                if raw.status_code != 200 or raw.headers.get("content-encoding", "identity") != "identity":
                    raise SliceRefused("CANDIDATE_PROBE_FAILED")
                response_bytes = bytearray()
                async for part in raw.aiter_bytes():
                    if len(response_bytes) + len(part) > 1_048_576:
                        raise SliceRefused("PROVIDER_RESPONSE_TOO_LARGE")
                    response_bytes.extend(part)
            data = decode(bytes(response_bytes))
            capture_quarantine(data, request_ref=request_ref, directory=RESULTS, stage="bootstrap")
            observation = extract_bifrost_observation(data, managed_versions=versions, observed_at=datetime.now(UTC),
                                                      request_ref=request_ref, request_model_id="deepseek-flash")
            choice = data["choices"][0]
            if (len(data["choices"]) != 1 or choice["finish_reason"] != "stop"
                    or choice["message"].get("tool_calls") or choice["message"].get("content", "").strip() != "OK"):
                raise SliceRefused("CANDIDATE_CHAT_NOT_CONFIRMED")
            usage = data["usage"]
            rates = profile.cost_rates
            if rates is None:
                raise SliceRefused("TARIFF_MISSING")
            await ledger.settle(reservation, tokens=usage["prompt_tokens"] + usage["completion_tokens"],
                cost=rates.cost(usage["prompt_tokens"], usage["completion_tokens"]))  # idempotent relay ACK
            await authorize(profile, request)
            balance = await ledger.balance()
            if balance.pending or balance.blocked:
                raise SliceRefused("ACCOUNTING_UNCONFIRMED")
            expected = IdentityExpectation(versions, observation.identity, admission_generation, evidence_hash(observation).hex())
            write_new(RESULTS / "observation.json", observation.to_dict())
            write_new(RESULTS / "expectation.json", expected.to_dict())
            result = {"status": ("CANDIDATE_OBSERVED_NOT_APPROVED" if bootstrap_status is ProfileStatus.CANDIDATE
                                  else "CONFIGURATION_OBSERVED_IDENTITY_REVIEW_REQUIRED"), "profileId": str(PROFILE_ID),
                      "requestRef": request_ref, "latencyMs": int((time.monotonic() - start) * 1000),
                      "usage": {"inputTokens": usage["prompt_tokens"], "outputTokens": usage["completion_tokens"]},
                      "usedOrReservedUSD": str(balance.used_or_reserved), "remainingUSD": str(balance.remaining),
                      "observationSha256": evidence_hash(observation).hex()}
            write_new(RESULTS / "bootstrap.json", result)
            return result

        class ArmedAdmission(ModelRegistryAdmission):
            async def begin(self, p: Any, r: LLMRequest) -> ObservedAdmissionCall:
                call = await super().begin(p, r)  # commits durable admission before ARM/I/O
                await ledger.arm(r.request_id)
                return call

        admission = ArmedAdmission(ModelAdmissionGuard(factory), authorize=authorize, managed_versions=lambda p, r: versions)
        confirmed = ConfirmedLedger(ledger)
        async with CapturingTransport(virtual_key=key, allow_observed=True, request_ref=request_ref, results_dir=RESULTS) as transport:
            gateway = GovernedLLMGateway(registry=lambda: registry, transport=transport, ledger=confirmed, admission=admission)
            try:
                response = await gateway.chat(request)
            except Exception as error:
                reason = _machine_error(error)
                _diagnostic(RESULTS, request_ref, "gateway-error", {"status": "GATEWAY_FAILED", "reason": reason,
                    "quarantineFile": None if transport.receipt is None else transport.receipt.filename})
                raise DiagnosticRefused(reason) from None
        balance = await ledger.balance()
        if not confirmed.confirmed or balance.pending or balance.blocked:
            _diagnostic(RESULTS, request_ref, "validation", {"status": "WITHHELD", "reason": "ACCOUNTING_UNCONFIRMED"})
            raise DiagnosticRefused("ACCOUNTING_UNCONFIRMED")
        if transport.receipt is None or transport.capture_error is not None:
            _diagnostic(RESULTS, request_ref, "validation", {"status": "WITHHELD", "reason": transport.capture_error or "CAPTURE_UNAVAILABLE"})
            raise DiagnosticRefused(transport.capture_error or "CAPTURE_UNAVAILABLE")
        # Source schema is a fixed pinned local input, not a caller URL.
        ids = ExperimentIds(UUID(plan["experiment"]["workerRunId"]), UUID(plan["experiment"]["taskId"]))
        accepted = capture_and_validate(response, source_from_plan(plan), ids, contracts, request_ref=request_ref,
            capture=transport.receipt, balance=balance, confirmed=confirmed.confirmed, directory=RESULTS)
        await authorize(profile, request)
        if response.identity.observation is None:
            raise SliceRefused("IDENTITY_OBSERVATION_REQUIRED")
        result = {"status": "DETERMINISTIC_CHECKS_PASSED_OWNER_REVIEW_REQUIRED", "receivedAt": datetime.now(UTC).isoformat(),
                  "requestRef": request_ref, "result": accepted.to_dict(), "identity": response.identity.observation.to_dict(),
                  "usage": {
                      "inputTokens": response.usage.input_tokens,
                      "outputTokens": response.usage.output_tokens,
                  },
                  "usedOrReservedUSD": str(balance.used_or_reserved), "remainingUSD": str(balance.remaining)}
        write_new(RESULTS / "requirements-result.json", result)
        return {k: result[k] for k in ("status", "requestRef", "usage", "usedOrReservedUSD", "remainingUSD")}
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "bootstrap", "run"))
    try:
        print(json.dumps(asyncio.run(execute(parser.parse_args().phase))))
        return 0
    except DiagnosticRefused as error:
        print(json.dumps({"status": "SLICE_REFUSED", "reason": error.reason}), file=sys.stderr)
        return 2
    except Exception as error:
        print(json.dumps({"status": "SLICE_REFUSED", "errorType": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
