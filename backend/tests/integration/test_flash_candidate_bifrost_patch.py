"""ADR135 build provenance and actual patched-image behavior, never live admission."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from . import test_flash_candidate_bifrost as official

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "infra/llm_poc/bifrost_patch/build.py"
SPEC = importlib.util.spec_from_file_location("candidate_bifrost_build_tool", TOOL)
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build
SPEC.loader.exec_module(build)


def snapshot_fixture(*, bad_path=None, symlink=False):
    files = {"LICENSE": b"synthetic license", "core/go.mod": b"synthetic core lock", "transports/go.mod": b"synthetic transport lock"}
    if bad_path:
        files[bad_path] = b"synthetic forbidden entry"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), 0o644
            if symlink and name == "LICENSE":
                info.type, info.linkname, info.size = tarfile.SYMTYPE, "/outside", 0
                archive.addfile(info)
            else:
                archive.addfile(info, io.BytesIO(content))
    raw = stream.getvalue()
    manifest = {"source": {"archiveSha256": hashlib.sha256(raw).hexdigest(), "archiveBytes": len(raw), "fileCount": len(files)},
                "license": {"sha256": hashlib.sha256(files["LICENSE"]).hexdigest()},
                "moduleLocks": {name: hashlib.sha256(content).hexdigest() for name, content in files.items() if name.endswith("go.mod")}}
    return raw, manifest


def test_build_manifest_binds_verified_sparse_source_and_fixed_toolchains():
    manifest = build.load_manifest()
    assert manifest["source"]["sourceKind"] == "verified-git-sparse"
    assert manifest["source"]["commit"] == "7cb75fb2f8276ca48d0792c857fecb67b8879e2f"
    assert manifest["source"]["tree"] == "fe862c3b2236a41ae4f3bc969f992500e2cb22d0"
    assert "@sha256:" in manifest["builder"] and "@sha256:" in manifest["runtime"]
    assert manifest["goVersion"] == "go1.27.4" and manifest["ui"]["mode"] == "HEADLESS_INFERENCE_ONLY"
    assert manifest["source"]["selection"] == ["LICENSE", "core/**", "transports/**"]


def test_source_snapshot_checksum_and_lock_bytes_are_both_verified():
    raw, manifest = snapshot_fixture()
    files = build.verify_snapshot(raw, manifest)
    assert files["core/go.mod"][0] == b"synthetic core lock"
    with pytest.raises(build.CandidateBuildError):
        build.verify_snapshot(raw + b"different", manifest)
    manifest["moduleLocks"]["core/go.mod"] = "0" * 64
    with pytest.raises(build.CandidateBuildError):
        build.verify_snapshot(raw, manifest)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "core/../../escape", "docs/not-selected", "core\\escape"])
def test_source_archive_refuses_escape_or_unselected_paths_even_with_matching_checksum(path):
    raw, manifest = snapshot_fixture(bad_path=path)
    with pytest.raises(build.CandidateBuildError):
        build.verify_snapshot(raw, manifest)


def test_source_archive_refuses_symlinks_even_with_matching_checksum():
    raw, manifest = snapshot_fixture(symlink=True)
    with pytest.raises(build.CandidateBuildError):
        build.verify_snapshot(raw, manifest)


def test_build_input_reader_never_follows_symlink_or_reads_fifo(tmp_path):
    path = tmp_path / "input"
    outside = tmp_path / "outside"
    outside.write_bytes(b"synthetic forbidden input")
    path.symlink_to(outside)
    with pytest.raises(build.CandidateBuildError):
        build.read_input(path, 32)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(build.CandidateBuildError):
        build.read_input(path, 32)


def test_git_commands_scrub_hostile_inherited_git_and_askpass_environment(tmp_path, monkeypatch):
    trap = tmp_path / "trap"
    trap.write_text("untouched")
    bad = {"GIT_DIR": str(trap), "GIT_WORK_TREE": str(trap), "GIT_COMMON_DIR": str(trap), "GIT_INDEX_FILE": str(trap),
           "GIT_OBJECT_DIRECTORY": str(trap), "GIT_CONFIG_COUNT": "999", "GIT_CONFIG_PARAMETERS": "evil",
           "GIT_CONFIG_KEY_99": "evil", "GIT_CONFIG_VALUE_99": "evil", "GIT_SSL_NO_VERIFY": "true",
           "GIT_CUSTOM_FUTURE_ENV": "evil", "GIT_ASKPASS": "/evil", "SSH_ASKPASS": "/evil", "SSH_ASKPASS_REQUIRE": "force"}
    for key, value in bad.items():
        monkeypatch.setenv(key, value)
    seen = []
    def fake_run(command, **options):
        seen.append(options["env"])
        return SimpleNamespace(stdout=b"synthetic", returncode=0)
    monkeypatch.setattr(build.subprocess, "run", fake_run)
    assert build.run(["git", "--version"]) == b"synthetic"
    env = seen[0]
    assert not any(key in env for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                                        "GIT_CONFIG_PARAMETERS", "GIT_CUSTOM_FUTURE_ENV", "GIT_SSL_NO_VERIFY", "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE"))
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_GLOBAL"] == os.devnull and env["GIT_CONFIG_SYSTEM"] == os.devnull
    assert env.get("GIT_ASKPASS") != "/evil" and env.get("GIT_CONFIG_COUNT") != "999"
    assert "evil" not in env.values() and trap.read_text() == "untouched"


def test_fresh_fetch_registers_fixed_promisor_origin_before_fetch_and_sparse_checkout(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(build, "run", lambda command: commands.append(command) or b"")
    monkeypatch.setattr(build, "make_snapshot", lambda directory, manifest: (b"synthetic snapshot", []))
    assert build.fetch_snapshot(tmp_path / "fresh") == (b"synthetic snapshot", [])
    origin = next(index for index, command in enumerate(commands) if command[-4:] == ["remote", "add", "origin", build.ORIGIN])
    promisor = next(index for index, command in enumerate(commands) if command[-3:] == ["config", "remote.origin.promisor", "true"])
    partial_filter = next(index for index, command in enumerate(commands) if command[-3:] == ["config", "remote.origin.partialclonefilter", "blob:none"])
    fetch = next(index for index, command in enumerate(commands) if "fetch" in command)
    sparse = next(index for index, command in enumerate(commands) if "sparse-checkout" in command and "set" in command)
    checkout = next(index for index, command in enumerate(commands) if "checkout" in command)
    assert origin < promisor < partial_filter < fetch < sparse < checkout
    assert commands[fetch][-2:] == ["origin", build.COMMIT]


def proof_archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), 0o644
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


@pytest.mark.parametrize("tamper", ["none", "binary", "sidecar"])
def test_provenance_hashes_actual_binary_in_stopped_container_and_refuses_tampered_sidecar(monkeypatch, tamper):
    binary, license_bytes = b"synthetic compiled binary", b"synthetic license"
    digest = hashlib.sha256(binary).hexdigest()
    manifest = {"goVersion": "go1.27.4", "license": {"sha256": hashlib.sha256(license_bytes).hexdigest()}}
    manifest_raw = json.dumps(manifest).encode()
    files = {"local-core.json": json.dumps({"Path": "github.com/maximhq/bifrost/core", "Main": True, "Dir": "/src/core"}).encode(),
             "go-build-info.txt": b"/out/main: go1.27.4\n dep github.com/maximhq/bifrost/core (devel)\n",
             "elf-program-headers.txt": b"ELF executable without dynamic loader", "LICENSE": license_bytes,
             "source-manifest.json": manifest_raw, "binary.sha256": (("b" * 64 if tamper == "sidecar" else digest) + "  main\n").encode()}
    calls = []
    class StoppedContainer:
        def get_archive(self, path):
            calls.append(path)
            if path == "/app/main":
                actual = binary + b"tampered" if tamper == "binary" else binary
                return iter([proof_archive({"main": actual})]), {}
            return iter([proof_archive({"candidate-provenance/" + name: value for name, value in files.items()})]), {}

        def remove(self, **options):
            calls.append(("remove", options))

    def create(*args, **options):
        assert options["network_mode"] == "none" and options["entrypoint"] == ["/bin/true"]
        return StoppedContainer()
    monkeypatch.setattr(build, "read_input", lambda path, limit: manifest_raw)
    client = SimpleNamespace(containers=SimpleNamespace(create=create))
    if tamper == "none":
        assert build.image_provenance(client, "sha256:" + "a" * 64, manifest)["binarySha256"] == digest
        assert "/app/main" in calls
    else:
        with pytest.raises(build.CandidateBuildError):
            build.image_provenance(client, "sha256:" + "a" * 64, manifest)
    assert calls[-1] == ("remove", {"v": True})


@pytest.fixture(scope="module")
def patched_bifrost(tmp_path_factory):
    """Cold build is explicit here; every listener is internal/unpublished."""
    image_id, provenance = build.build_image()
    directory = tmp_path_factory.mktemp("patched-flash-bifrost")
    (directory / "build-provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    from uuid import uuid4
    key = "sk-bf-" + uuid4().hex + uuid4().hex
    config = (REPO / "infra/llm_poc/config.template.json").read_text()
    config = config.replace("$LLM_RELAY_AUTH", official.AUTH).replace("$BIFROST_ADMIN_PASSWORD", uuid4().hex + uuid4().hex)
    config = config.replace("sk-bf-$BIFROST_VIRTUAL_KEY", key)
    config_file = directory / "config.json"
    config_file.write_text(config)
    config_file.chmod(0o644)
    with ExitStack() as stack:
        network = stack.enter_context(Network(docker_network_kw={"internal": True}))
        relay = DockerContainer(official._fixture_image()).with_network(network).with_network_aliases("llm-gateway")
        relay.with_env("PYTHONPATH", "/candidate-src").with_env("PYTHONDONTWRITEBYTECODE", "1")
        for source, target in ((REPO / "backend/src", "/candidate-src"), (REPO / "infra/llm_poc/relay.py", "/fixture/relay.py"),
                               (REPO / "backend/tests/fixtures/flash_candidate_fake_relay.py", "/fixture/fake.py"), (config_file, "/fixture/config.json")):
            relay.with_volume_mapping(source, target, "ro")
        relay.with_kwargs(user="10001:10001", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"], mem_limit="256m", pids_limit=128)
        relay.tmpfs = {"/tmp": "uid=10001,gid=10001,mode=0700"}
        relay.with_command(["python", "-B", "/fixture/fake.py"])
        stack.enter_context(relay)
        official._wait(relay, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)"])
        candidate = DockerContainer(image_id).with_network(network).with_network_aliases("bifrost-poc")
        candidate.with_volume_mapping(config_file, "/fixture/config.json", "ro")
        for resource in ("pricing.json", "model-parameters.json", "mcp-library.json"):
            candidate.with_volume_mapping(REPO / "infra/llm_poc" / resource, "/etc/bifrost/" + resource, "ro")
        candidate.with_kwargs(entrypoint=["/bin/sh", "-c"], user="1000:1000", read_only=True, cap_drop=["ALL"],
                              security_opt=["no-new-privileges:true"], mem_limit="512m", pids_limit=256)
        candidate.tmpfs = {"/app/data": "uid=1000,gid=1000,mode=0700", "/tmp": "uid=1000,gid=1000,mode=0700"}
        candidate.with_command(["cp /fixture/config.json /app/data/config.json && exec /app/main -app-dir /app/data "
                                "-host 0.0.0.0 -port 8080 -log-level error -log-style json"])
        stack.enter_context(candidate)
        official._wait(candidate, ["wget", "-q", "--spider", "http://127.0.0.1:8080/health"])
        assert network._unwrap_network.attrs["Internal"] is True
        for item in (relay, candidate):
            wrapped = item.get_wrapped_container()
            wrapped.reload()
            assert set(wrapped.attrs["NetworkSettings"]["Networks"]) == {network.name}
            assert not wrapped.attrs["HostConfig"]["PortBindings"] and not any(wrapped.attrs["NetworkSettings"]["Ports"].values())
        yield SimpleNamespace(relay=relay, key=key, provenance=provenance)


def probe_actual(fixture, case):
    code, raw = fixture.relay.exec(["python", "-B", "/fixture/fake.py", "--probe", case])
    assert code == 0, "Synthetic patched-image helper failed; no raw output is exported."
    assert fixture.key.encode() not in raw
    return json.loads(raw)


@pytest.mark.parametrize("case,presence", [("SSE", "VALUE"), ("SSE_ABSENT", "ABSENT"), ("SSE_NULL", "NULL")])
def test_actual_patched_image_preserves_every_observed_fingerprint_state(patched_bifrost, case, presence):
    """Candidate observation only; ABSENT/NULL never establish admission readiness."""
    captured = probe_actual(patched_bifrost, case)
    result, facts, digest = captured["evidence"], captured["diagnostics"], captured["expected_sha256"]
    assert result.get("outcome") == "COMPLETE" and result["capabilityOk"] is True
    assert result["identity"]["fingerprint"] == {"presence": presence, "value": "synthetic-wire-fingerprint" if presence == "VALUE" else None}
    assert result["identity"]["responseModelId"] == "deepseek-flash" and result["usage"] == {"inputTokens": 12, "outputTokens": 2}
    assert facts["claims"].count(digest) == 1 and sum(item["sha256"] == digest for item in facts["outgoing"]) == 1
    assert sum(item.get("canonical_sha256") == digest for item in facts["received"]) == 1
    assert sum(item["body_sha256"] == digest and item["outcome"] == "KNOWN" for item in facts["settlements"]) == 1
    assert patched_bifrost.provenance["elfWithoutInterpreter"] is True


@pytest.mark.parametrize("case", ["SSE_FP_FINISH", "SSE_FP_USAGE", "SSE_ID_FINISH", "SSE_ID_USAGE", "SSE_MODEL_FINISH", "SSE_MODEL_USAGE",
                                "SSE_MISSING_FP", "SSE_NULL_FP", "SSE_FP_TYPE", "SSE_FP_DUPLICATE", "SSE_MISSING_ID", "SSE_NULL_MODEL",
                                "SSE_MALFORMED", "SSE_TRUNCATED", "SSE_ERROR", "SSE_CREDENTIAL", "SSE_EMPTY"])
def test_actual_patched_image_refuses_hidden_drift_malformed_or_secret_facts(patched_bifrost, case):
    """Stack refusal; isolated Go tests identify SDK behavior behind relay checks.

    In particular ID conflicts, duplicates and truncation may first be refused
    by the real relay. FP/model drift has an additional SDK error attribution.
    """
    captured = probe_actual(patched_bifrost, case)
    assert captured["evidence"] == {"error": "INVALID_RESPONSE"}
    assert "synthetic private failure" not in json.dumps(captured)
    facts, digest = captured["diagnostics"], captured["expected_sha256"]
    assert facts["claims"].count(digest) == 1 and sum(item["sha256"] == digest for item in facts["outgoing"]) == 1
    if case in {"SSE_FP_FINISH", "SSE_FP_USAGE", "SSE_MODEL_FINISH", "SSE_MODEL_USAGE"}:
        assert any(record.get("controlled_metadata_refusal") or any(event.get("controlled_metadata_refusal") for event in record.get("events", []))
                   for record in captured["bifrost_response"])


@pytest.mark.parametrize("case,outcome", [("CANCEL", "CANCELLED"), ("TIMEOUT", "TIMEOUT")])
def test_actual_patched_image_controlled_outcomes_are_not_completed_evidence(patched_bifrost, case, outcome):
    captured = probe_actual(patched_bifrost, case)
    result, facts, digest = captured["evidence"], captured["diagnostics"], captured["expected_sha256"]
    assert result["outcome"] == outcome and result["usage"] is None and result["capabilityOk"] is False
    assert facts["claims"].count(digest) == 1 and sum(item["sha256"] == digest for item in facts["outgoing"]) == 1
    assert sum(item.get("canonical_sha256") == digest for item in facts["received"]) == 1
    settlements = [item for item in facts["settlements"] if item["body_sha256"] == digest]
    assert len(settlements) == 1 and settlements[0]["outcome"] in {"KNOWN", "UNKNOWN"}
    if settlements[0]["outcome"] == "KNOWN":
        assert settlements[0]["input_tokens"] == 12 and settlements[0]["output_tokens"] == 2
    else:
        assert settlements[0]["reason"] in {"CANCEL", "TIMEOUT", "NETWORK", "UNTRUSTED_RESPONSE"}


@pytest.mark.parametrize("case", ["AUTH_WRONG", "AUTH_MISSING"])
def test_actual_patched_headless_image_keeps_inference_auth_enforced(patched_bifrost, case):
    captured = probe_actual(patched_bifrost, case)
    if case == "AUTH_WRONG":
        assert captured["evidence"] == {"error": "HTTP_REFUSED"}
        assert captured["bifrost_response"][0]["status"] in {401, 403}
    else:
        assert captured["evidence"]["outcome"] == "AUTH_REFUSED" and captured["evidence"]["httpStatus"] in {401, 403}
    assert captured["expected_sha256"] not in captured["diagnostics"]["claims"]
    assert not any(item["sha256"] == captured["expected_sha256"] for item in captured["diagnostics"]["outgoing"])
