"""ADR137 actual hardened binary/namespace/SQLite, entirely synthetic upstream.

The mutation executable is built only as a test input and injected into tmpfs by
the trusted test host; it is never part of the candidate image or product build.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import docker
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from ai_res.modules.model_registry.candidate_host import (
    BIFROST_BIND_PATHS,
    HOST_VERSION,
    INPUT_PATHS,
    OFFICIAL_TARIFF_URL,
    CandidateDevelopmentGate,
    CandidateHostConfig,
    DockerCandidateObserver,
    GuardedCandidateControl,
)
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest
from ai_res.modules.model_registry.poc_budget import AUTHORIZATION_KEY
from ai_res.modules.model_registry.poc_control import CandidateControlDenied

from . import test_flash_candidate_bifrost as native
from .test_flash_candidate_bifrost_patch import probe_actual

REPO = native.REPO
SPEC = importlib.util.spec_from_file_location("candidate_integrity_native_build", REPO / "infra/llm_poc/bifrost_integrity/build.py")
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build
SPEC.loader.exec_module(build)


@pytest.fixture(scope="module")
def integrity_images():
    candidate, proof = build.build_image()
    python_image = native._fixture_image()
    return candidate, proof, python_image


@pytest.fixture(scope="module")
def sqlite_mutator():
    """Compile a closed fault injector using exactly pinned existing module locks."""
    manifest = build.base.load_manifest()
    with tempfile.TemporaryDirectory(prefix="candidate-sqlite-test-") as directory:
        root = Path(directory)
        # Source acquisition is public/pinned and verified by the existing tool;
        # a saved sparse cache is optional, never required to reproduce tests.
        cached = Path("/tmp/g02-bifrost-verified-sparse-7cb75fb2.tar")
        if cached.is_file():
            raw = build.base.read_input(cached, build.base.MAX_SOURCE)
        else:
            raw, _ = build.base.fetch_snapshot(root / "source")
        files = build.base.verify_snapshot(raw, manifest)
        for name in ("go.mod", "go.sum"):
            (root / name).write_bytes(files["transports/" + name][0])
        (root / "helper.go").write_bytes((REPO / "backend/tests/fixtures/candidate_sqlite_mutation.go").read_bytes())
        client = docker.from_env(timeout=240)
        try:
            try:
                client.containers.run(manifest["builder"], ["go", "build", "-tags", "sqlite_static,netgo",
                    "-ldflags=-w -s -extldflags '-static'", "-o", "/src/sqlite-mutator", "helper.go"],
                    volumes={str(root): {"bind": "/src", "mode": "rw"}}, working_dir="/src", user=f"{os.getuid()}:{os.getgid()}",
                    environment={"GOTOOLCHAIN": "local", "GOWORK": "off", "GOFLAGS": "-mod=readonly", "GOPATH": "/tmp/gopath",
                                 "GOCACHE": "/tmp/cache", "CGO_ENABLED": "1", "GOMAXPROCS": "2"},
                    read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                    tmpfs={"/tmp": "mode=1777"}, mem_limit="1g", pids_limit=256, remove=True)
            except docker.errors.ContainerError:
                raise AssertionError("Test-only SQLite mutator compilation failed; raw build output withheld.") from None
            for name in ("go.mod", "go.sum"):
                assert (root / name).read_bytes() == files["transports/" + name][0]
            return build.base.read_input(root / "sqlite-mutator", 16_777_216)
        finally:
            client.close()


@pytest.fixture
def hardened_candidate(tmp_path, integrity_images):
    candidate_image, proof, python_image = integrity_images
    inputs = tmp_path / "checkout"
    for relative in BIFROST_BIND_PATHS.values():
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
        target.chmod(0o644)
    credentials = {name: uuid4().hex + uuid4().hex for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth")}
    for name, value in credentials.items():
        (tmp_path / name).write_text(value + "\n")
        (tmp_path / name).chmod(0o444)
    credential_file = tmp_path / "credentials.json"
    credential_file.write_text(json.dumps(credentials))
    credential_file.chmod(0o444)
    rendered = (REPO / "infra/llm_poc/config.template.json").read_text()
    for name, marker in (("bifrost_admin_password", "$BIFROST_ADMIN_PASSWORD"), ("bifrost_virtual_key", "$BIFROST_VIRTUAL_KEY"),
                         ("llm_relay_auth", "$LLM_RELAY_AUTH")):
        rendered = rendered.replace(marker, credentials[name])
    rendered_file = tmp_path / "config.json"
    rendered_file.write_text(rendered)
    rendered_file.chmod(0o444)
    with ExitStack() as stack:
        client = docker.from_env()
        stack.callback(client.close)
        baseline = {x.id: x.attrs["State"]["StartedAt"] for x in client.containers.list() if x.name.startswith("ai-res-")}
        network = stack.enter_context(Network(docker_network_kw={"internal": True}))
        relay = DockerContainer(python_image).with_network(network).with_network_aliases("llm-gateway")
        relay.with_env("PYTHONPATH", "/candidate-src").with_env("PYTHONDONTWRITEBYTECODE", "1")
        for source, target in ((REPO / "backend/src", "/candidate-src"), (REPO / "infra/llm_poc/relay.py", "/fixture/relay.py"),
            (REPO / "backend/tests/fixtures/flash_candidate_fake_relay.py", "/fixture/fake.py"),
            (REPO / "backend/tests/fixtures/bifrost_integrity_probe.py", "/fixture/probe.py"),
            (rendered_file, "/fixture/config.json"), (credential_file, "/fixture/credentials.json")):
            relay.with_volume_mapping(source, target, "ro")
        relay.with_kwargs(user="10001:10001", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                          mem_limit="256m", pids_limit=128)
        relay.tmpfs = {"/tmp": "uid=10001,gid=10001,mode=0700"}
        relay.with_command(["python", "-B", "/fixture/fake.py"])
        stack.enter_context(relay)
        native._wait(relay, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)"])
        relay.get_wrapped_container().exec_run(["python", "-B", "/fixture/probe.py", "--proxy"], detach=True)
        native._wait(relay, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health',timeout=1)"])
        candidate = DockerContainer(candidate_image).with_network(network).with_network_aliases("bifrost-poc")
        candidate.with_env("APP_DIR", "/tmp/ignored-app-dir").with_env("BIFROST_CONFIG_TEMPLATE", "/tmp/ignored-template")
        candidate.with_env("http_proxy", "http://llm-gateway:8082").with_env("HTTP_PROXY", "http://llm-gateway:8082")
        for target, source in BIFROST_BIND_PATHS.items():
            candidate.with_volume_mapping(inputs / source, target, "ro")
        for name in credentials:
            candidate.with_volume_mapping(tmp_path / name, "/run/secrets/" + name, "ro")
        candidate.with_kwargs(user="1000:1000", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                              mem_limit="512m", pids_limit=256)
        # Exec is enabled only for the trusted test host's SQLite fault injector;
        # no product Compose or real admission descriptor uses this fixture.
        candidate.tmpfs = {"/app/data": "uid=1000,gid=1000,mode=0700", "/tmp": "exec,uid=1000,gid=1000,mode=0700"}
        candidate.with_command([])
        stack.enter_context(candidate)
        native._wait(candidate, ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "wget", "-q", "-O", "/dev/null", "-T", "2",
                                "http://127.0.0.1:8080/health"])
        fixture = SimpleNamespace(bifrost=candidate, relay=relay, key="sk-bf-" + credentials["bifrost_virtual_key"],
                                  secrets=credentials, provenance=proof, inputs=inputs, directory=tmp_path, network=network)
        try:
            yield fixture
        finally:
            current = {x.id: x.attrs["State"]["StartedAt"] for x in client.containers.list() if x.name.startswith("ai-res-")}
            assert all(current.get(key) == value for key, value in baseline.items()), "Existing stack changed during native fixture."


def native_probe(fixture, action):
    code, raw = fixture.relay.exec(["python", "-B", "/fixture/probe.py", action])
    assert code == 0, "Hardened candidate probe failed; raw output withheld."
    assert not any(value.encode() in raw for value in fixture.secrets.values())
    value = json.loads(raw)
    if action == "health":
        assert set(value) == {"status"} and type(value["status"]) is int
    else:
        assert len(value) == (45 if action == "routes" else 3) and all(type(item) is bool for item in value.values())
    return value


def test_actual_admin_and_alternative_routes_are_denied_even_with_admin_credentials(hardened_candidate):
    assert all(native_probe(hardened_candidate, "routes").values())
    assert all(native_probe(hardened_candidate, "auth").values())
    assert native_probe(hardened_candidate, "health") == {"status": 200}


def test_two_real_synthetic_sse_calls_keep_logical_state_stable_and_auth_active(hardened_candidate):
    for index in range(2):
        result = probe_actual(hardened_candidate, "SSE")
        assert result["evidence"]["outcome"] == "COMPLETE" and result["evidence"]["capabilityOk"] is True
        assert native_probe(hardened_candidate, "health") == {"status": 200}
        if index == 0:
            # Pinned governance tracker.go workerInterval is10s. Observe a real
            # background tick; this is a test window, not a product TTL/SLO.
            time.sleep(10.2)
            assert native_probe(hardened_candidate, "health") == {"status": 200}


def test_native_bootstrap_refuses_reused_sqlite_before_any_merge(hardened_candidate):
    fixture = hardened_candidate
    code, raw = fixture.bifrost.exec(["/app/main", "-app-dir", "/app/data", "-host", "127.0.0.1", "-port", "8099", "-log-level", "error"])
    assert code != 0 and b"candidate configuration integrity refused" in raw, "Reused-state bootstrap was not refused."
    assert not any(value.encode() in raw for value in fixture.secrets.values()), "Synthetic credential appeared in bootstrap error."
    assert native_probe(fixture, "health") == {"status": 200}


async def actual_gate(fixture):
    observation = await DockerCandidateObserver().observe(fixture.bifrost.get_wrapped_container().id)
    root = fixture.inputs
    snapshot = b"synthetic reviewed tariff"
    sha = build.base.sha
    tariff = {"version": "flash-candidate-tariff/0.1", "sourceUrl": OFFICIAL_TARIFF_URL, "snapshotSha256": sha(snapshot),
              "currency": "USD", "inputPerMillion": "0.30", "outputPerMillion": "1.20", "inputBound": 2_000_000, "outputBound": 256}
    for role, relative in INPUT_PATHS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if role == "tariff":
            path.write_text(json.dumps(tariff))
        elif not path.exists():
            path.write_text("synthetic " + role)
    manifest = CandidateRunManifest("a" * 40, "b" * 64, sha((root / INPUT_PATHS["config"]).read_bytes()),
        sha((root / INPUT_PATHS["prompt"]).read_bytes()), None, observation.image_sha256,
        sha((root / INPUT_PATHS["plan"]).read_bytes()), sha((root / INPUT_PATHS["tariff"]).read_bytes()))
    document = {"version": HOST_VERSION, "authorizationKey": AUTHORIZATION_KEY, "accountId": str(uuid4()), "manifest": manifest.to_dict(),
        "tariffSnapshotSha256": sha(snapshot), "bifrostContainerId": fixture.bifrost.get_wrapped_container().id,
        "expectedRuntimeSha256": observation.runtime_sha256, "expectedIntegritySha256": observation.integrity.namespace_sha256,
        "inputPaths": {**INPUT_PATHS, "tools": None}}
    path = fixture.directory / "host.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    class SyntheticTariff:
        async def snapshot_sha256(self):
            return sha(snapshot)
    return CandidateDevelopmentGate(CandidateHostConfig.load(path), root, source_reader=lambda: ("a" * 40, "b" * 64),
                                    tariff_observer=SyntheticTariff(), image_observer=DockerCandidateObserver())


@pytest.mark.parametrize("kind", ["rendered", "marker", "mounted"])
async def test_namespace_tamper_refuses_claim_and_stays_blocked_after_restoration(hardened_candidate, kind):
    fixture = hardened_candidate
    gate = await actual_gate(fixture)
    await gate.validate_host()
    if kind == "mounted":
        path = fixture.inputs / "infra/llm_poc/pricing.json"
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
    else:
        target = "/app/data/config.json" if kind == "rendered" else "/app/data/candidate-integrity.json"
        if kind == "marker":
            code, _ = fixture.bifrost.exec(["cp", target, "/tmp/original-marker"])
            assert code == 0
        code, _ = fixture.bifrost.exec(["/bin/sh", "-c", 'printf "\\n" >> "$1"', "tamper", target])
        assert code == 0
    class Service:
        calls = []
        async def claim(self, value):
            self.calls.append("claim")
        async def settle(self, value):
            self.calls.append("settle")
            return value
    service = Service()
    control = GuardedCandidateControl(service, gate)
    with pytest.raises(CandidateControlDenied):
        await control.claim(object())
    assert service.calls == []
    assert await control.settle("record-unknown") == "record-unknown" and service.calls == ["settle"]
    assert native_probe(fixture, "health") == {"status": 503}
    if kind == "mounted":
        path.write_bytes(original)
    elif kind == "rendered":
        code, _ = fixture.bifrost.exec(["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "/bin/sh", "/poc/start-bifrost.sh", "--render-only"])
        assert code == 0
    else:
        code, _ = fixture.bifrost.exec(["cp", "/tmp/original-marker", "/app/data/candidate-integrity.json"])
        assert code == 0
    assert native_probe(fixture, "health") == {"status": 503}


@pytest.mark.parametrize("kind", ["client", "schema"])
async def test_direct_sqlite_mutation_is_refused_without_changing_rendered_file(hardened_candidate, sqlite_mutator, kind):
    fixture = hardened_candidate
    gate = await actual_gate(fixture)
    await gate.validate_host()
    identifier = fixture.bifrost.get_wrapped_container().id
    command = [str(Path(shutil.which("docker"))), "--host", "unix:///var/run/docker.sock", "exec", "-i", identifier,
               "/bin/sh", "-c", "cat > /tmp/sqlite-mutator && chmod 700 /tmp/sqlite-mutator"]
    result = subprocess.run(command, input=sqlite_mutator, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=15)
    assert result.returncode == 0, "Test-only SQLite injector setup failed."
    code, raw = fixture.bifrost.exec(["/tmp/sqlite-mutator", kind])
    assert code == 0 and raw == b"MUTATED\n", "Closed SQLite mutation did not execute."
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()
    assert native_probe(fixture, "health") == {"status": 503}


async def test_actual_restart_invalidates_previously_reviewed_descriptor(hardened_candidate):
    gate = await actual_gate(hardened_candidate)
    await gate.validate_host()
    hardened_candidate.bifrost.get_wrapped_container().restart(timeout=3)
    native._wait(hardened_candidate.bifrost, ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "wget", "-q", "-O", "/dev/null", "-T", "2",
                                           "http://127.0.0.1:8080/health"])
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()


async def test_actual_host_atomic_replacement_cannot_reuse_reviewed_mount_binding(hardened_candidate):
    fixture = hardened_candidate
    gate = await actual_gate(fixture)
    await gate.validate_host()
    path = fixture.inputs / "infra/llm_poc/pricing.json"
    replacement = path.with_suffix(".replacement")
    replacement.write_bytes(path.read_bytes() + b"\n")
    os.replace(replacement, path)
    # Either the container still sees its old bound inode (host-byte comparison
    # fails) or Desktop reflects replacement (the compiled input guard fails).
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()


def test_hardened_fixture_keeps_networks_secrets_and_logs_isolated(hardened_candidate):
    fixture = hardened_candidate
    assert fixture.network._unwrap_network.attrs["Internal"] is True
    forbidden = [value.encode() for value in fixture.secrets.values()]
    for item in (fixture.bifrost, fixture.relay):
        wrapped = item.get_wrapped_container()
        wrapped.reload()
        assert set(wrapped.attrs["NetworkSettings"]["Networks"]) == {fixture.network.name}
        assert not wrapped.attrs["HostConfig"]["PortBindings"] and not any(wrapped.attrs["NetworkSettings"]["Ports"].values())
        assert not any(value in wrapped.logs() for value in forbidden), "Synthetic credential appeared in logs."
        environment = "\n".join(wrapped.attrs["Config"]["Env"]).encode()
        assert not any(value in environment for value in forbidden), "Synthetic credential appeared in environment."


async def test_proxy_cannot_spoof_fresh_host_health_after_integrity_failure(hardened_candidate):
    fixture = hardened_candidate
    await DockerCandidateObserver().observe(fixture.bifrost.get_wrapped_container().id)
    code, _ = fixture.bifrost.exec(["/bin/sh", "-c", "printf '\\n' >> /app/data/config.json"])
    assert code == 0 and native_probe(fixture, "health") == {"status": 503}
    # Positive attack control: inherited proxy lies200 even for failing health.
    code, _ = fixture.bifrost.exec(["wget", "-q", "-O", "/dev/null", "-T", "2", "http://127.0.0.1:8080/health"])
    assert code == 0, "Lying proxy control did not intercept inherited-env health."
    with pytest.raises(CandidateRunDenied):
        await DockerCandidateObserver().observe(fixture.bifrost.get_wrapped_container().id)
