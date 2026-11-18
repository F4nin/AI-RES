"""One-case candidate CLI and local append-only evidence; no provider/DB calls."""
import json
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_res.cli.flash_candidate import CandidateSourceBinding, main, source_binding
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.llm.candidate_probe import CandidateProbeError, CandidateProbeEvidence, CandidateProbeUsage, ProbeOutcome
from ai_res.llm.observed_identity import FingerprintPresence, ObservedFingerprint, ObservedProviderIdentity
from ai_res.modules.model_registry.candidate_runner import (
    RUN_VERSION,
    CandidateAccounting,
    CandidateRunDenied,
    CandidateRunManifest,
    CandidateRunner,
    JsonlCandidateEvidence,
)
from ai_res.modules.model_registry.poc_budget import PaidLedgerDenied, ProbeAttemptTicket
from ai_res.platform.clock import utc_now


def test_default_cli_is_dry_run_without_constructing_a_host(capsys):
    def forbidden(*args):
        pytest.fail("Dry run constructed an execution host")

    assert main(["--case", "TEXT"], host_factory=forbidden) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "DRY_RUN" and data["caseRef"] == "TEXT" and data["maxOutputTokens"] == 256
    assert "messages" not in data and "content" not in data


def test_execute_without_a_trusted_composition_refuses_without_creating_evidence(tmp_path, capsys):
    path = tmp_path / "evidence.jsonl"
    assert main(["--case", "TEXT", "--execute", "--evidence-file", str(path)]) == 2
    assert not path.exists() and "HOST_UNCONFIGURED" in capsys.readouterr().err


def test_evidence_preflight_append_fsync_and_exclusive_lock(tmp_path):
    path = tmp_path / "evidence.jsonl"
    with JsonlCandidateEvidence(path) as sink:
        sink.append({"kind": "INTENT", "version": RUN_VERSION})
        with pytest.raises(CandidateRunDenied), JsonlCandidateEvidence(path):
            pytest.fail("Second writer acquired an exclusive evidence lock")
        sink.append({"kind": "RESULT", "version": RUN_VERSION})
    assert path.stat().st_mode & 0o777 == 0o600
    with JsonlCandidateEvidence(path) as sink:
        sink.append({"kind": "INTENT", "version": RUN_VERSION})
    assert [json.loads(line)["kind"] for line in path.read_text().splitlines()] == ["INTENT", "RESULT", "INTENT"]


@pytest.mark.parametrize("mutation", ["symlink", "permissions", "partial", "directory", "unrelated-jsonl"])
def test_unsafe_or_truncated_evidence_is_never_overwritten(tmp_path, mutation):
    path = tmp_path / "evidence.jsonl"
    if mutation == "directory":
        path.mkdir()
    else:
        path.write_text('{"existing":"metadata"}' + ("" if mutation == "partial" else "\n"))
        path.chmod(0o600)
        if mutation == "symlink":
            target = path
            path = tmp_path / "link"
            path.symlink_to(target)
        elif mutation == "permissions":
            path.chmod(0o644)
    with pytest.raises(CandidateRunDenied), JsonlCandidateEvidence(path):
        pytest.fail("Unsafe evidence was opened")


def test_source_manifest_hashes_dirty_and_new_relevant_files_but_never_secret_files(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    source = root / "backend/src/ai_res"
    source.mkdir(parents=True)
    (source / "first.py").write_text("first = 1\n")
    (root / "secret.key").write_text("private-fixture")
    monkeypatch.setattr("ai_res.cli.flash_candidate._git_head", lambda root: "a" * 40)
    monkeypatch.setattr("ai_res.cli.flash_candidate._FILES", ())
    original = source_binding(root)
    (root / "secret.key").write_text("different-private-fixture")
    assert source_binding(root) == original
    (source / "first.py").write_text("first = 2\n")
    assert source_binding(root).source_tree_sha256 != original.source_tree_sha256
    changed = source_binding(root)
    (source / "new.py").write_text("new = 3\n")
    assert source_binding(root).source_tree_sha256 != changed.source_tree_sha256
    assert isinstance(original, CandidateSourceBinding) and original.code_revision == "a" * 40


def test_source_manifest_refuses_symlink_escape(tmp_path, monkeypatch):
    source = tmp_path / "backend/src/ai_res"
    source.mkdir(parents=True)
    outside = tmp_path / "private.key"
    outside.write_text("private-fixture")
    (source / "escaped.py").symlink_to(outside)
    monkeypatch.setattr("ai_res.cli.flash_candidate._git_head", lambda root: "a" * 40)
    monkeypatch.setattr("ai_res.cli.flash_candidate._FILES", ())
    with pytest.raises(CandidateRunDenied):
        source_binding(tmp_path)


@pytest.mark.parametrize("family,relative", [("bifrost_patch", name) for name in
    ("fingerprint.patch", "build.py", "manifest.json", "Dockerfile", "headless-index.html")] + [("bifrost_integrity", name) for name in
    ("integrity.patch", "build.py", "manifest.json", "Dockerfile", "start-candidate.sh")])
def test_candidate_build_inputs_are_bound_to_actual_source(tmp_path, monkeypatch, family, relative):
    import ai_res.cli.flash_candidate as cli

    (tmp_path / "backend/src/ai_res").mkdir(parents=True)
    # Populate exactly the production discovery inputs, then change one actual
    # patch/build dependency. A Git HEAD alone cannot bind this dirty worktree.
    for name in cli._FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture input\n")
    path = tmp_path / "infra/llm_poc" / family / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("first fixture\n")
    monkeypatch.setattr(cli, "_git_head", lambda root: "a" * 40)
    original = cli.source_binding(tmp_path)
    path.write_text("changed fixture\n")
    assert cli.source_binding(tmp_path).source_tree_sha256 != original.source_tree_sha256


def test_git_provenance_ignores_redirect_environment_and_rejects_parent_checkout(tmp_path, monkeypatch):
    import shutil
    import subprocess

    from ai_res.cli.flash_candidate import _git_head

    clean_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    clean_env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    git = shutil.which("git")
    assert git is not None
    roots = [tmp_path / "actual", tmp_path / "unrelated"]
    for root in roots:
        root.mkdir()
        subprocess.run([git, "init", "--quiet"], cwd=root, env=clean_env, check=True, capture_output=True, timeout=5)
        subprocess.run([git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "-c", "core.hooksPath=/dev/null",
                        "-c", "commit.gpgSign=false", "commit", "--quiet", "--allow-empty", "-m", root.name],
                       cwd=root, env=clean_env, check=True, capture_output=True, timeout=5)
    expected = _git_head(roots[0])
    assert expected != _git_head(roots[1])
    monkeypatch.setenv("GIT_DIR", str(roots[1] / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(roots[1]))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    assert _git_head(roots[0]) == expected
    child = roots[0] / "nested"
    child.mkdir()
    with pytest.raises(CandidateRunDenied):
        _git_head(child)


def test_source_discovery_never_reads_hidden_credentials_or_artifacts_inside_roots(tmp_path, monkeypatch):
    import ai_res.cli.flash_candidate as cli
    source = tmp_path / "backend/src/ai_res"
    source.mkdir(parents=True)
    (source / "safe.py").write_text("safe = True\n")
    forbidden = [source / ".credentials.json", source / ".credentials.py", source / "secrets/private.py",
                 source / "artifacts/private.py", tmp_path / "infra/llm_poc/credentials.json", tmp_path / "contracts/internal/.private.json"]
    for path in forbidden:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private-fixture")
    original = cli._source_bytes
    read = []

    def checked(path, *args):
        assert path not in forbidden
        read.append(path)
        return original(path, *args)

    monkeypatch.setattr(cli, "_source_bytes", checked)
    monkeypatch.setattr(cli, "_git_head", lambda root: "a" * 40)
    monkeypatch.setattr(cli, "_FILES", ())
    source_binding(tmp_path)
    assert read == [source / "safe.py"]


@pytest.mark.parametrize("failure", ["traversal", "count", "bytes", "entries"])
def test_source_discovery_errors_or_input_caps_refuse_instead_of_partial_hash(tmp_path, monkeypatch, failure):
    import ai_res.cli.flash_candidate as cli
    source = tmp_path / "backend/src/ai_res"
    source.mkdir(parents=True)
    (source / "first.py").write_text("first = 1\n")
    (source / "second.py").write_text("second = 2\n")
    monkeypatch.setattr(cli, "_git_head", lambda root: "a" * 40)
    monkeypatch.setattr(cli, "_FILES", ())
    if failure == "traversal":
        monkeypatch.setattr(cli.os, "scandir", lambda path: (_ for _ in ()).throw(PermissionError()))
    elif failure == "count":
        monkeypatch.setattr(cli, "SOURCE_MAX_FILES", 1)
    elif failure == "bytes":
        monkeypatch.setattr(cli, "SOURCE_MAX_TOTAL_BYTES", 1)
    else:
        monkeypatch.setattr(cli, "SOURCE_MAX_ENTRIES", 1)
    with pytest.raises(CandidateRunDenied, match="BINDING_MISMATCH"):
        source_binding(tmp_path)


@pytest.mark.parametrize("kind", [[], {}])
def test_malformed_existing_evidence_closes_fd_and_releases_lock(tmp_path, kind):
    path = tmp_path / "evidence.jsonl"
    path.write_text(json.dumps({"version": RUN_VERSION, "kind": kind}) + "\n")
    path.chmod(0o600)
    sink = JsonlCandidateEvidence(path)
    with pytest.raises(CandidateRunDenied, match="EVIDENCE_UNAVAILABLE"):
        sink.__enter__()
    assert sink._fd == -1
    path.write_text(json.dumps({"version": RUN_VERSION, "kind": "INTENT"}) + "\n")
    with JsonlCandidateEvidence(path) as fresh, pytest.raises(CandidateRunDenied):
        fresh.append({"version": RUN_VERSION, "kind": kind})
    assert os.stat(path).st_size > 0


def manifest():
    return CandidateRunManifest("a" * 40, "b" * 64, "c" * 64, "d" * 64, None, "e" * 64, "f" * 64, "1" * 64)


class Budget:
    def __init__(self, *, denied=False):
        self.tickets = []
        self.denied = denied

    async def reserve(self, binding):
        if self.denied:
            raise PaidLedgerDenied()
        ticket = ProbeAttemptTicket(uuid4(), uuid4(), 1, binding, Decimal("0.6003072"))
        self.tickets.append(ticket)
        return ticket


class Gate:
    def __init__(self, *, deny_at=None):
        self.calls = 0
        self.deny_at = deny_at

    async def validate(self, body, managed):
        self.calls += 1
        if self.calls == self.deny_at:
            raise CandidateRunDenied("HOST_UNCONFIGURED")


class Accounting:
    def __init__(self, value=None):
        self.calls = []
        self.value = value or CandidateAccounting("SETTLED", "KNOWN", Decimal("0.6003072"), Decimal("0.0000054"), False, 10, 2, "provider-fixture")

    async def read(self, ticket):
        self.calls.append(ticket)
        return self.value


class Probe:
    def __init__(self, path, *, failure=False, outcome=ProbeOutcome.COMPLETE):
        self.calls = []
        self.path = path
        self.failure = failure
        self.outcome = outcome

    async def probe(self, body, *, timeout_seconds):
        assert json.loads(self.path.read_text().splitlines()[-1])["kind"] == "INTENT"
        self.calls.append(body)
        if self.failure:
            raise CandidateProbeError()
        identity = ObservedProviderIdentity("deepseek", "deepseek-flash", "deepseek-flash", "fixture-flash",
                                             ObservedFingerprint(FingerprintPresence.ABSENT, None))
        return CandidateProbeEvidence(body.case_ref, body.body_sha256, utc_now(), self.outcome, identity,
                                      "provider-fixture", CandidateProbeUsage(10, 2) if self.outcome is ProbeOutcome.COMPLETE else None,
                                      self.outcome is ProbeOutcome.COMPLETE, 1 if body.stream else 0)


async def test_runner_reserves_and_fsyncs_intent_before_exactly_one_probe_then_reads_its_ticket(tmp_path):
    path = tmp_path / "evidence.jsonl"
    budget, gate, probe, accounting = Budget(), Gate(), Probe(path), Accounting()
    runner = CandidateRunner(budget, accounting, probe, gate, JsonlCandidateEvidence(path))
    body = build_candidate_body("TEXT", uuid4())
    result = await runner.run(body, manifest(), timeout_seconds=10)
    assert len(budget.tickets) == len(probe.calls) == len(accounting.calls) == 1 and gate.calls == 2
    assert accounting.calls == budget.tickets and result.attempt_id == budget.tickets[0].attempt_id
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert records[0]["kind"] == "INTENT" and records[1]["accountingConfirmed"] is True
    exported = path.read_text()
    assert "Synthetic" not in exported and "messages" not in exported and "profileId" not in exported and "pinned" not in exported


@pytest.mark.parametrize("failure", ["sink-preflight", "gate-before", "budget", "intent", "gate-after", "probe"])
async def test_failures_never_dispatch_before_durable_intent_or_repeat_or_release(tmp_path, monkeypatch, failure):
    path = tmp_path / "evidence.jsonl"
    budget = Budget(denied=failure == "budget")
    gate = Gate(deny_at=1 if failure == "gate-before" else 2 if failure == "gate-after" else None)
    probe, accounting = Probe(path, failure=failure == "probe"), Accounting()
    sink = JsonlCandidateEvidence(path)
    if failure == "sink-preflight":
        monkeypatch.setattr("ai_res.modules.model_registry.candidate_runner.os.fsync", lambda fd: (_ for _ in ()).throw(OSError()))
    elif failure == "intent":
        monkeypatch.setattr(sink, "append", lambda record: (_ for _ in ()).throw(CandidateRunDenied("EVIDENCE_UNAVAILABLE")))
    with pytest.raises(CandidateRunDenied):
        await CandidateRunner(budget, accounting, probe, gate, sink).run(build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    assert len(probe.calls) == (1 if failure == "probe" else 0)
    assert len(budget.tickets) == (1 if failure in {"intent", "gate-after", "probe"} else 0)


async def test_global_budget_balance_cannot_substitute_for_exact_attempt_accounting(tmp_path):
    path = tmp_path / "evidence.jsonl"
    pending = CandidateAccounting("CLAIMED", None, Decimal("0.6003072"), None, False)
    budget, probe = Budget(), Probe(path)
    with pytest.raises(CandidateRunDenied, match="ACCOUNTING_UNCONFIRMED"):
        await CandidateRunner(budget, Accounting(pending), probe, Gate(), JsonlCandidateEvidence(path)).run(
            build_candidate_body("TEXT", uuid4()), manifest(), timeout_seconds=10)
    record = json.loads(path.read_text().splitlines()[-1])
    assert record["accountingConfirmed"] is False and record["accounting"]["chargedCostUsd"] is None
    assert len(budget.tickets) == len(probe.calls) == 1


async def test_cancel_evidence_is_not_transport_completion_and_uses_unknown_full_hold(tmp_path):
    path = tmp_path / "evidence.jsonl"
    unknown = CandidateAccounting("SETTLED", "UNKNOWN", Decimal("0.6003072"), Decimal("0.6003072"), False)
    result = await CandidateRunner(Budget(), Accounting(unknown), Probe(path, outcome=ProbeOutcome.CANCELLED), Gate(),
                                   JsonlCandidateEvidence(path)).run(build_candidate_body("CANCEL", uuid4()), manifest(), timeout_seconds=10)
    assert result.evidence.outcome is ProbeOutcome.CANCELLED and result.evidence.capability_ok is False


@pytest.mark.parametrize("failure", [None, "runner", "source-binding"])
def test_execute_host_context_is_closed_on_success_and_every_refusal(tmp_path, monkeypatch, capsys, failure):
    events = []
    source = CandidateSourceBinding("a" * 40, "b" * 64)
    monkeypatch.setattr("ai_res.cli.flash_candidate.source_binding", lambda root: source)

    class PreparedRunner:
        async def run(self, body, managed, *, timeout_seconds):
            events.append("probe-once")
            assert body.case_ref == "JSON" and timeout_seconds == 10
            if failure == "runner":
                raise CandidateRunDenied("PROBE_REFUSED")
            return SimpleNamespace(attempt_id=uuid4(), evidence=SimpleNamespace(outcome=ProbeOutcome.COMPLETE))

    @asynccontextmanager
    async def factory(actual_source, path):
        assert actual_source == source and path == tmp_path / "evidence.jsonl"
        events.append("host-enter")
        try:
            managed = manifest()
            if failure == "source-binding":
                managed = replace(managed, source_tree_sha256="2" * 64)
            yield PreparedRunner(), managed
        finally:
            events.append("host-close")

    result = main(["--case", "JSON", "--execute", "--evidence-file", str(tmp_path / "evidence.jsonl")], host_factory=factory)
    assert result == (0 if failure is None else 2)
    assert events == (["host-enter", "host-close"] if failure == "source-binding" else ["host-enter", "probe-once", "host-close"])
    assert "Synthetic" not in capsys.readouterr().out
