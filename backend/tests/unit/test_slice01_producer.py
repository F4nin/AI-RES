"""Bounded private capture/diagnostics; no provider, DB or owner approval."""
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from scripts.slice01 import producer
from scripts.slice01.common import canonical, digest
from scripts.slice01.ledger import SliceBalance
from scripts.slice01.requirements import ExperimentIds, Source

from ai_res.llm.admission import ObservedAdmissionCall
from ai_res.llm.budget import Budget, InMemoryBudgetLedger
from ai_res.llm.errors import ModelProfileNotApproved, ProviderUnavailable
from ai_res.llm.gateway import GovernedLLMGateway
from ai_res.llm.observed_identity import (
    FingerprintPresence,
    IdentityObservation,
    ManagedVersions,
    ObservedFingerprint,
    ObservedProviderIdentity,
)
from ai_res.llm.registry import Egress, ModelProfile, ModelRegistry, ProfileIdentityMode, ProfileStatus, RetryClass
from ai_res.llm.transport import TransportResult
from ai_res.llm.types import Capability, FinishReason, LLMLimits, LLMRequest, LLMResponse, Message, ModelIdentity, Role, ToolCall, Usage
from ai_res.worker_contracts import WorkerContracts

REF = "slice-synthetic-run"
IDS = ExperimentIds(UUID(int=3), UUID(int=4))
SCHEMA = Path(__file__).resolve().parents[3] / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json"
NOW = datetime(2026, 11, 18, tzinfo=UTC)


def source():
    text = "The service shall list published articles.\n"
    return Source(UUID(int=1), UUID(int=2), digest(text.encode()), text)


def output():
    src = source()
    return canonical({"workerResult": {"contractVersion": "1.1", "workerRunId": str(IDS.worker_run_id), "taskId": str(IDS.task_id),
        "workerRole": "REQUIREMENTS", "resultStatus": "COMPLETED", "summary": "One candidate",
        "findings": [{"findingId": "F1", "classification": "SOURCE_ASSERTION", "statement": "List articles.", "evidenceRefs": [{
            "objectType": "SourceVersion", "objectId": str(src.version_id), "versionId": str(src.version_id),
            "checksum": src.checksum, "locator": "lines:1-1", "quote": "The service shall list published articles."}]}],
        "proposedChanges": [], "artifactRefs": [], "questions": [], "blockers": [], "limitations": [],
        "validation": {"selfAssessment": "NOT_RUN"}, "completedAt": "2026-11-18T00:00:00Z"},
        "findingTypes": [{"findingId": "F1", "declaredType": "FR"}]}).decode()


def response(text=None, **kwargs):
    return LLMResponse(**({"identity": ModelIdentity(UUID(int=5), "synthetic", 1, "fixture", "fixture", "fixture-version"),
        "output": output() if text is None else text, "finish_reason": FinishReason.STOP,
        "usage": Usage(100, 50), "latency_ms": 1} | kwargs))


@pytest.fixture
def private(tmp_path):
    tmp_path.chmod(0o700)
    return tmp_path


def validate(directory, data, **kwargs):
    captured = producer.capture_quarantine(producer._model_payload(data), request_ref=REF, directory=directory)
    return producer.capture_and_validate(data, source(), IDS, WorkerContracts.from_file(SCHEMA), request_ref=REF,
        capture=captured, balance=SliceBalance(Decimal(10), Decimal("0.001"), Decimal("9.999"), 1, False, False),
        confirmed=True, directory=directory, **kwargs)


def test_success_retains_untrusted_capture_and_separate_check_receipt(private, capsys):
    accepted = validate(private, response())
    captured = json.loads((private / f"transport-quarantine-{REF}.json").read_bytes())
    diagnostic = json.loads((private / f"validation-{REF}.json").read_bytes())
    assert accepted.worker_result["findings"][0]["findingId"] == "F1"
    assert captured["status"] == "UNTRUSTED_TRANSPORT_OUTPUT"
    assert captured["gatewayFinalization"] == captured["accounting"] == "NOT_YET_CONFIRMED"
    assert captured["response"]["output"] == output()
    assert diagnostic["status"] == "PASSED" and diagnostic["accounting"] == "CONFIRMED"
    assert "output" not in diagnostic and "workerResult" not in diagnostic
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in private.iterdir())
    assert not (private / "requirements-result.json").exists()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad,reason", [("{not-json", "RESULT_REJECTED"), ("```json\n{}\n```", "RESULT_REJECTED"),
                                        ("x" * 131_073, "MALFORMED_JSON")])
def test_rejection_keeps_full_private_response_and_only_fixed_reason_in_diagnostic(private, capsys, bad, reason):
    with pytest.raises(producer.DiagnosticRefused) as caught:
        validate(private, response(bad))
    assert caught.value.reason == reason
    captured = json.loads((private / f"transport-quarantine-{REF}.json").read_bytes())
    diagnostic = json.loads((private / f"validation-{REF}.json").read_bytes())
    assert captured["response"]["output"] == bad
    assert diagnostic["status"] == "REJECTED" and diagnostic["reason"] == reason
    assert "response" not in diagnostic and "output" not in diagnostic and "workerResult" not in diagnostic
    assert not (private / "requirements-result.json").exists()
    assert not capsys.readouterr().out


@pytest.mark.parametrize("case,reason", [("truncation", "BAD_RESPONSE"), ("tool", "BAD_RESPONSE"), ("hallucination", "UNGROUNDED_FINDING")])
def test_capture_does_not_execute_or_accept_untrusted_tools_and_false_evidence(private, case, reason):
    data = response()
    canary = private / "must-not-exist"
    if case == "truncation":
        data = replace(data, finish_reason=FinishReason.LENGTH)
    elif case == "tool":
        data = replace(data, tool_calls=(ToolCall("F1", "write", {"path": str(canary)}),))
    else:
        payload = json.loads(data.output)
        payload["workerResult"]["findings"][0]["evidenceRefs"][0]["quote"] = "Invented source claim."
        data = replace(data, output=json.dumps(payload))
    with pytest.raises(producer.DiagnosticRefused, match=reason):
        validate(private, data)
    assert not canary.exists()


def test_unknown_validation_exception_never_exports_its_text(private, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_SOURCE_OR_SECRET_MUST_NOT_LEAK")

    monkeypatch.setattr(producer, "validate_response", fail)
    with pytest.raises(producer.DiagnosticRefused, match="VALIDATION_UNAVAILABLE") as caught:
        validate(private, response())
    assert "PRIVATE_SOURCE" not in str(caught.value)
    assert "PRIVATE_SOURCE" not in (private / f"validation-{REF}.json").read_text()
    assert "PRIVATE_SOURCE" not in capsys.readouterr().out


def test_capture_is_bounded_private_and_never_overwrites_existing_bytes(private):
    original = producer.capture_quarantine({"output": "first"}, request_ref=REF, directory=private)
    with pytest.raises(FileExistsError):
        producer.capture_quarantine({"output": "second"}, request_ref=REF, directory=private)
    assert digest((private / original.filename).read_bytes()) == original.sha256
    with pytest.raises(producer.DiagnosticRefused, match="CAPTURE_REFUSED"):
        producer.capture_quarantine({"output": "x" * producer.MAX_CAPTURE_PAYLOAD_BYTES}, request_ref="oversized", directory=private)
    with pytest.raises(producer.DiagnosticRefused, match="CAPTURE_REFUSED"):
        producer.capture_quarantine({}, request_ref="../escaped", directory=private)
    private.chmod(0o755)
    with pytest.raises(producer.DiagnosticRefused, match="CAPTURE_REFUSED"):
        producer.capture_quarantine({}, request_ref="shared", directory=private)


@pytest.mark.parametrize("location", ["literal", "escaped-value", "escaped-key", "duplicate-key", "unicode", "tail"])
def test_secret_screen_runs_before_any_quarantine_write(private, location):
    fake = "gh" + "p_" + "a" * 32
    escaped = "\\u0067" + fake[1:]
    if location == "literal":
        payload = {"output": fake}
    elif location == "escaped-key":
        payload = {"output": '{"' + escaped + '":"ordinary"}'}
    elif location == "duplicate-key":
        payload = {"output": '{"summary":"' + escaped + '","summary":"ordinary"}'}
    elif location == "unicode":
        payload = {"output": json.dumps({"summary": fake.replace("ghp", "ｇｈｐ")})}
    elif location == "tail":
        payload = {"output": "ordinary text " * 800 + fake}
    else:
        payload = {"output": '{"summary":"' + escaped + '"}'}
    with pytest.raises(producer.DiagnosticRefused, match="OUTPUT_SECRET") as caught:
        producer.capture_quarantine(payload, request_ref=REF, directory=private)
    assert fake not in str(caught.value) and not list(private.iterdir())


@pytest.mark.parametrize("stage", ["bootstrap", "transport"])
@pytest.mark.parametrize("encoding", ["json", "double-json", "nested-field"])
def test_every_stage_screens_json_bearing_string_leaves_recursively(private, stage, encoding):
    embedded = '{"summary":"\\u0067hp_' + "a" * 32 + '"}'
    if encoding == "double-json":
        embedded = json.dumps(embedded)
    elif encoding == "nested-field":
        embedded = json.dumps({"metadata": embedded})
    payload = {"choices": [{"message": {"content": embedded}}]}
    with pytest.raises(producer.DiagnosticRefused, match="OUTPUT_SECRET"):
        producer.capture_quarantine(payload, request_ref=REF, directory=private, stage=stage)
    assert not list(private.iterdir())


def test_malformed_nonsecret_bootstrap_content_remains_private_untrusted_data(private):
    payload = {"choices": [{"message": {"content": "{malformed ordinary source-free output"}}]}
    receipt = producer.capture_quarantine(payload, request_ref=REF, directory=private, stage="bootstrap")
    assert json.loads((private / receipt.filename).read_bytes())["response"] == payload


@pytest.mark.parametrize("limit", ["depth", "bytes", "values"])
def test_decoded_screen_resource_limits_refuse_before_file_creation(private, monkeypatch, limit):
    payload = {"output": "[" * 64 + '"ordinary"' + "]" * 64} if limit == "depth" else {"output": "ordinary"}
    if limit == "bytes":
        monkeypatch.setattr(producer, "MAX_CAPTURE_SCAN_TEXT_BYTES", 2)
    elif limit == "values":
        monkeypatch.setattr(producer, "MAX_CAPTURE_SCAN_VALUES", 1)
    with pytest.raises(producer.DiagnosticRefused, match="CAPTURE_REFUSED"):
        producer.capture_quarantine(payload, request_ref=REF, directory=private)
    assert not list(private.iterdir())


@pytest.mark.parametrize("changed", ["payload", "file", "accounting"])
def test_validation_requires_capture_binding_and_confirmed_accounting(private, changed):
    data = response()
    receipt = producer.capture_quarantine(producer._model_payload(data), request_ref=REF, directory=private)
    if changed == "payload":
        data = replace(data, output="different")
    elif changed == "file":
        (private / receipt.filename).write_bytes(b"{}")
    with pytest.raises(producer.DiagnosticRefused):
        producer.capture_and_validate(data, source(), IDS, WorkerContracts.from_file(SCHEMA), request_ref=REF, capture=receipt,
            balance=SliceBalance(Decimal(10), Decimal("0.001"), Decimal("9.999"), 1, changed == "accounting", False),
            confirmed=True, directory=private)
    assert not (private / f"validation-{REF}.json").exists()


def observed_fixture():
    profile = ModelProfile(id=UUID(int=5), profile_key="synthetic", profile_version=1, provider="deepseek", provider_model_id="deepseek-flash",
        pinned_model_version=None, capabilities=frozenset({Capability.CHAT}), context_window_tokens=8192, max_output_tokens=2048,
        data_classifications=frozenset({"INTERNAL"}), allowed_regions=frozenset({"cn"}), egress=Egress.EXTERNAL, timeout_seconds=30,
        retry_class=RetryClass.NONE, status=ProfileStatus.APPROVED, approved_at=NOW, identity_mode=ProfileIdentityMode.FLASH_OBSERVED)
    versions = ManagedVersions("a" * 40, profile.id, 1, "b" * 64, "c" * 64, None)
    identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "deepseek-flash",
                                       ObservedFingerprint(FingerprintPresence.VALUE, "synthetic-fingerprint"))
    observation = IdentityObservation(versions, identity, NOW, REF, "synthetic-provider")
    request = LLMRequest(request_id=REF, model_profile_id=profile.id, purpose="SLICE01", messages=(Message(Role.USER, "synthetic"),),
                         budget_scope=REF, data_classification="INTERNAL", limits=LLMLimits(2048, 30))
    return profile, versions, observation, request


@pytest.mark.parametrize("finalize_fails", [False, True])
async def test_capture_precedes_real_gateway_finalization_even_when_finalization_refuses(private, monkeypatch, finalize_fails):
    profile, versions, observation, request = observed_fixture()
    returned = TransportResult(output="untrusted malformed output", finish_reason=FinishReason.STOP, usage=Usage(100, 50),
                               provider_request_ref=observation.provider_request_ref, observation=observation)

    async def complete(self, call):
        return returned

    class Admission:
        async def begin(self, p, r):
            return ObservedAdmissionCall(versions, object())

        async def finalize(self, call, observed):
            assert (private / f"transport-quarantine-{REF}.json").is_file()
            assert observed == observation
            if finalize_fails:
                raise RuntimeError("PRIVATE_ERROR_NOT_FOR_LOGS")

    monkeypatch.setattr(producer.SliceBifrostTransport, "complete", complete)
    ledger = InMemoryBudgetLedger()
    ledger.establish(REF, Budget(max_total_tokens=10_000))
    async with producer.CapturingTransport(request_ref=REF, results_dir=private, virtual_key="synthetic", allow_observed=True) as transport:
        gateway = GovernedLLMGateway(registry=lambda: ModelRegistry([profile]), transport=transport, ledger=ledger, admission=Admission())
        if finalize_fails:
            with pytest.raises(ModelProfileNotApproved):
                await gateway.chat(request)
        else:
            assert (await gateway.chat(request)).output == returned.output
        assert transport.receipt is not None and transport.capture_error is None
    assert not (private / "requirements-result.json").exists()


async def test_transport_error_receipt_is_fixed_and_does_not_contain_exception_text(private, monkeypatch):
    async def fail(self, call):
        raise ProviderUnavailable("PRIVATE_ERROR_NOT_FOR_LOGS", possibly_billed=True)

    monkeypatch.setattr(producer.SliceBifrostTransport, "complete", fail)
    async with producer.CapturingTransport(request_ref=REF, results_dir=private, virtual_key="synthetic") as transport:
        with pytest.raises(ProviderUnavailable):
            await transport.complete(SimpleNamespace(request_id=REF))
    diagnostic = (private / f"transport-error-{REF}.json").read_text()
    assert "PROVIDER_UNAVAILABLE" in diagnostic and "PRIVATE_ERROR" not in diagnostic


async def test_capture_io_failure_preserves_gateway_finalization_and_known_usage(private, monkeypatch):
    profile, versions, observation, request = observed_fixture()
    finalized = []

    async def complete(self, call):
        return TransportResult(output="synthetic output", finish_reason=FinishReason.STOP, usage=Usage(100, 50),
                               provider_request_ref=observation.provider_request_ref, observation=observation)

    def unavailable(*args, **kwargs):
        raise OSError("PRIVATE_STORAGE_ERROR")

    class Admission:
        async def begin(self, p, r):
            return ObservedAdmissionCall(versions, object())

        async def finalize(self, call, observed):
            finalized.append(observed)

    monkeypatch.setattr(producer.SliceBifrostTransport, "complete", complete)
    monkeypatch.setattr(producer, "capture_quarantine", unavailable)
    ledger = InMemoryBudgetLedger()
    ledger.establish(REF, Budget(max_total_tokens=10_000))
    async with producer.CapturingTransport(request_ref=REF, results_dir=private, virtual_key="synthetic", allow_observed=True) as transport:
        gateway = GovernedLLMGateway(registry=lambda: ModelRegistry([profile]), transport=transport, ledger=ledger, admission=Admission())
        assert (await gateway.chat(request)).output == "synthetic output"
        assert transport.receipt is None and transport.capture_error == "CAPTURE_UNAVAILABLE"
    assert finalized == [observation] and ledger.usage(REF)[0] == 150
    assert not (private / "requirements-result.json").exists()


async def test_decoded_secret_capture_refusal_still_finalizes_and_accounts_without_writing_secret(private, monkeypatch):
    profile, versions, observation, request = observed_fixture()
    finalized = []
    escaped = "\\u0067hp_" + "a" * 32

    async def complete(self, call):
        return TransportResult(output='{"summary":"' + escaped + '"}', finish_reason=FinishReason.STOP, usage=Usage(100, 50),
                               provider_request_ref=observation.provider_request_ref, observation=observation)

    class Admission:
        async def begin(self, p, r):
            return ObservedAdmissionCall(versions, object())

        async def finalize(self, call, observed):
            finalized.append(observed)

    monkeypatch.setattr(producer.SliceBifrostTransport, "complete", complete)
    ledger = InMemoryBudgetLedger()
    ledger.establish(REF, Budget(max_total_tokens=10_000))
    async with producer.CapturingTransport(request_ref=REF, results_dir=private, virtual_key="synthetic", allow_observed=True) as transport:
        gateway = GovernedLLMGateway(registry=lambda: ModelRegistry([profile]), transport=transport, ledger=ledger, admission=Admission())
        await gateway.chat(request)
        assert transport.receipt is None and transport.capture_error == "OUTPUT_SECRET"
    assert finalized == [observation] and ledger.usage(REF)[0] == 150
    assert not list(private.iterdir())


def test_stdout_rejection_reason_is_bounded_machine_metadata(monkeypatch, capsys):
    async def fail(phase):
        raise producer.DiagnosticRefused("UNGROUNDED_FINDING")

    monkeypatch.setattr(producer, "execute", fail)
    monkeypatch.setattr(producer.sys, "argv", ["producer", "run"])
    assert producer.main() == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err) == {"status": "SLICE_REFUSED", "reason": "UNGROUNDED_FINDING"}


@pytest.mark.parametrize("plan,status,generation", [({}, ProfileStatus.CANDIDATE, 1),
    ({"profileStatus": "APPROVED", "admissionGeneration": 2, "experimentVersion": "2"}, ProfileStatus.APPROVED, 2),
    ({"profileStatus": "APPROVED", "admissionGeneration": 3, "experimentVersion": "3"}, ProfileStatus.APPROVED, 3)])
def test_bootstrap_revalidates_explicit_actual_profile_status_and_new_generation(plan, status, generation):
    assert producer.experiment_target(plan) == (status, generation)


@pytest.mark.parametrize("plan", [{"profileStatus": "RETIRED"}, {"admissionGeneration": True},
    {"profileStatus": "APPROVED", "admissionGeneration": 1, "experimentVersion": "2"},
    {"profileStatus": "APPROVED", "admissionGeneration": 2, "experimentVersion": "1"}])
def test_invalid_generation_or_status_cannot_create_bootstrap_target(plan):
    with pytest.raises(ValueError):
        producer.experiment_target(plan)
