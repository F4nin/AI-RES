"""ADR137 namespace grammar/guard integration, explicit doubles only."""
import hashlib
import json
from dataclasses import replace

import pytest

from ai_res.modules.model_registry.candidate_host import CandidateHostConfig, DockerCandidateObserver, runtime_observation
from ai_res.modules.model_registry.candidate_integrity import INTEGRITY_VERSION, NAMESPACE_FILES, namespace_observation
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied


def namespace_raw():
    marker = json.dumps({"version": INTEGRITY_VERSION, "bootNonce": "b" * 32, "configSha256": "a" * 64}, separators=(",", ":"))
    lines = ["FILES"]
    for path in NAMESPACE_FILES:
        sha = hashlib.sha256(marker.encode()).hexdigest() if path == NAMESPACE_FILES[-1] else "a" * 64
        mode, size = ("600", str(len(marker))) if path == NAMESPACE_FILES[-1] else ("600", "10")
        lines += [path, mode + " " + size, sha + "  " + path]
    return ("\n".join([*lines, "MARKER", marker, "HEALTHY"]) + "\n").encode()


def test_namespace_proof_is_deterministic_and_never_exports_marker_or_digest_in_repr():
    actual = namespace_observation(namespace_raw())
    assert actual == namespace_observation(namespace_raw()) and len(actual.files) == 10
    assert actual.boot_nonce not in repr(actual) and actual.namespace_sha256 not in repr(actual)


@pytest.mark.parametrize("change", ["oversize", "truncated", "health", "extra", "path", "mode", "symlink-summary", "version", "nonce", "config", "duplicate"])
def test_namespace_parser_cannot_accept_partial_unsafe_or_forged_summary(change):
    raw = namespace_raw()
    if change == "oversize":
        raw += b"x" * 16_384
    elif change == "truncated":
        raw = raw[:-20]
    elif change == "health":
        raw = raw.replace(b"HEALTHY", b"FAILED")
    elif change == "extra":
        raw += b"HEALTHY\n"
    elif change == "path":
        raw = raw.replace(b"/poc/start-bifrost.sh", b"/poc/other.sh")
    elif change == "mode":
        raw = raw.replace(b"600 10", b"666 10", 1)
    elif change == "symlink-summary":
        raw = raw.replace(b"600 10", b"777 10", 1)
    elif change == "version":
        raw = raw.replace(INTEGRITY_VERSION.encode(), b"candidate-other/9")
    elif change == "nonce":
        raw = raw.replace(("b" * 32).encode(), b"invalid")
    elif change == "config":
        raw = raw.replace(b'"configSha256":"' + b"a" * 64, b'"configSha256":"' + b"c" * 64)
    else:
        raw = raw.replace(b'"version":', b'"version":"duplicate","version":')
    with pytest.raises(CandidateRunDenied) as caught:
        namespace_observation(raw)
    assert "duplicate" not in str(caught.value)


@pytest.mark.parametrize("field", ["StartedAt", "Pid", "RestartCount"])
def test_same_container_restart_invalidates_runtime_binding(field):
    from .test_candidate_host import runtime_fixture
    data = runtime_fixture()
    original = runtime_observation(data, data["Id"])
    if field == "StartedAt":
        data["State"][field] = "2026-11-18T12:00:01.000000000Z"
    elif field == "Pid":
        data["State"][field] += 1
    else:
        data[field] += 1
    assert runtime_observation(data, data["Id"]).runtime_sha256 != original.runtime_sha256


def test_old_descriptor_has_no_implicit_integrity_authority(tmp_path):
    from .test_candidate_host import config_fixture
    _, _, _, path, document = config_fixture(tmp_path)
    document["version"] = "flash-candidate-host/0.1"
    document.pop("expectedIntegritySha256")
    path.write_text(json.dumps(document))
    with pytest.raises(CandidateRunDenied):
        CandidateHostConfig.load(path)


@pytest.mark.parametrize("failure", ["missing-marker", "restart", "wrong-entrypoint", "namespace-failure"])
async def test_real_observer_requires_fresh_guarded_health_and_same_boot(monkeypatch, failure):
    from .test_candidate_host import runtime_fixture
    before = runtime_fixture()
    if failure == "wrong-entrypoint":
        before["Config"]["Entrypoint"] = ["/app/main"]
    after = json.loads(json.dumps(before))
    after["RestartCount"] = 1
    answers = [json.dumps(before).encode(), namespace_raw(), json.dumps(after if failure == "restart" else before).encode()]
    calls = []
    async def command(self, args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            if failure == "namespace-failure":
                raise CandidateRunDenied()
            if failure == "missing-marker":
                return b"FILES\n"
        return answers.pop(0)
    monkeypatch.setattr(DockerCandidateObserver, "_command", command)
    with pytest.raises(CandidateRunDenied):
        await DockerCandidateObserver().observe(before["Id"])
    assert len(calls) == (1 if failure == "wrong-entrypoint" else 3 if failure == "restart" else 2)


@pytest.mark.parametrize("change", ["missing", "digest", "launch", "mounted-bytes"])
async def test_shared_gate_refuses_missing_changed_or_wrongly_mounted_integrity(tmp_path, change):
    from .test_candidate_host import gate_fixture
    gate, _, image, _, _, _ = gate_fixture(tmp_path)
    actual = image.value
    if change == "missing":
        image.value = replace(actual, integrity=None)
    elif change == "digest":
        image.value = replace(actual, integrity=replace(actual.integrity, namespace_sha256="0" * 64))
    elif change == "launch":
        image.value = replace(actual, hardened_launch=False)
    else:
        # Simulate host atomic replacement: inspector mount path is unchanged,
        # but the observed old namespace inode still has the original content.
        (tmp_path / "infra/llm_poc/pricing.json").write_text("changed host inode")
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()
