"""Actual renderer/native image/SQLite audit, without any real provider client.

Positive mutation tests document a still-OPEN gate. They do not certify config
immutability or enable candidate dispatch. No product/main-stack state is used.
"""
import hashlib
import json
import re
from contextlib import ExitStack
from types import SimpleNamespace
from uuid import uuid4

import docker
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from ai_res.modules.model_registry.candidate_host import runtime_observation

from . import test_flash_candidate_bifrost as native
from .test_flash_candidate_bifrost_patch import build

REPO = native.REPO
HELPER = REPO / "backend/tests/fixtures/bifrost_effective_audit.py"


def actual_file(container, path):
    """Hash inside the running mount namespace; Docker archive omits tmpfs.

    No rendered bytes leave the container. Paths are a closed audit allowlist,
    passed as a positional shell argument, never interpolated into shell code.
    """
    assert path in {"/app/data/config.json", "/poc/start-bifrost.sh", "/etc/bifrost/config.template.json",
                    "/etc/bifrost/pricing.json", "/etc/bifrost/model-parameters.json", "/etc/bifrost/mcp-library.json"}
    command = ('test -f "$1" && test ! -L "$1" && test "$(stat -c %s "$1")" -le 1048576 '
               '&& stat -c %a "$1" && sha256sum "$1"')
    code, raw = container.exec(["/bin/sh", "-c", command, "audit-file", path])
    assert code == 0, "Actual mounted-file hash failed; raw output withheld."
    match = re.fullmatch(rb"([0-7]{3,4})\n([0-9a-f]{64})  " + re.escape(path.encode()) + rb"\n", raw)
    assert match is not None, "Invalid mounted-file summary; raw output withheld."
    return match[2].decode("ascii"), int(match[1], 8)


def probe(fixture, action):
    code, raw = fixture.relay.exec(["python", "-B", "/fixture/audit.py", action])
    assert code == 0, "Isolated effective-config probe failed; raw output withheld."
    assert all(value.encode() not in raw for value in fixture.secrets.values()), "Audit output contains a synthetic credential."
    values = json.loads(raw)
    assert isinstance(values, dict) and values and all(type(value) is bool for value in values.values())
    assert len(values) == {"effective": 34, "auth": 10, "mutate": 5, "restore": 5}[action], "Incomplete audit summary."
    return values


def inspected(fixture):
    wrapped = fixture.bifrost.get_wrapped_container()
    wrapped.reload()
    return runtime_observation(wrapped.attrs, wrapped.id)


@pytest.fixture(scope="module")
def isolated_bifrost_audit(tmp_path_factory):
    image_id, provenance = build.build_image()  # cache reuse with fresh actual-binary proof; no forced cold rebuild
    directory = tmp_path_factory.mktemp("bifrost-effective-audit")
    secrets = {name: uuid4().hex + uuid4().hex for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth")}
    for name, value in secrets.items():
        path = directory / name
        path.write_text(value + "\n")
        path.chmod(0o444)  # synthetic throwaway fixture only; never real secret setup
    credentials = directory / "credentials.json"
    credentials.write_text(json.dumps(secrets))
    credentials.chmod(0o444)
    with ExitStack() as stack:
        client = docker.from_env()
        stack.callback(client.close)
        # Read-only identity baseline; never stop/update these existing services.
        baseline = {item.id: item.attrs["State"]["StartedAt"] for item in client.containers.list() if item.name.startswith("ai-res-")}
        network = stack.enter_context(Network(docker_network_kw={"internal": True}))
        relay = DockerContainer(native._fixture_image()).with_network(network).with_network_aliases("llm-gateway")
        relay.with_volume_mapping(HELPER, "/fixture/audit.py", "ro")
        relay.with_volume_mapping(credentials, "/fixture/credentials.json", "ro")
        relay.with_kwargs(user="10001:10001", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                          mem_limit="256m", pids_limit=128)
        relay.tmpfs = {"/tmp": "uid=10001,gid=10001,mode=0700"}
        relay.with_command(["python", "-B", "/fixture/audit.py"])
        stack.enter_context(relay)
        native._wait(relay, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)"])
        bifrost = DockerContainer(image_id).with_network(network).with_network_aliases("bifrost-poc")
        bifrost.with_volume_mapping(REPO / "infra/llm_poc/start-bifrost.sh", "/poc/start-bifrost.sh", "ro")
        for source in ("config.template.json", "pricing.json", "model-parameters.json", "mcp-library.json"):
            bifrost.with_volume_mapping(REPO / "infra/llm_poc" / source, "/etc/bifrost/" + source, "ro")
        for name in secrets:
            bifrost.with_volume_mapping(directory / name, "/run/secrets/" + name, "ro")
        bifrost.with_kwargs(entrypoint=["/bin/sh", "/poc/start-bifrost.sh"], user="1000:1000", read_only=True,
                            cap_drop=["ALL"], security_opt=["no-new-privileges:true"], mem_limit="512m", pids_limit=256)
        bifrost.tmpfs = {"/app/data": "uid=1000,gid=1000,mode=0700", "/tmp": "uid=1000,gid=1000,mode=0700"}
        bifrost.with_command([])
        stack.enter_context(bifrost)
        native._wait(bifrost, ["wget", "-q", "--spider", "http://127.0.0.1:8080/health"])
        fixture = SimpleNamespace(bifrost=bifrost, relay=relay, network=network, secrets=secrets, provenance=provenance, client=client)
        try:
            yield fixture
        finally:
            # Check before ExitStack cleanup, so failures still close both owned
            # containers/network and never remove a main-stack resource.
            current = {item.id: item.attrs["State"]["StartedAt"] for item in client.containers.list() if item.name.startswith("ai-res-")}
            assert all(current.get(key) == value for key, value in baseline.items()), "Existing stack container restarted or disappeared."


def test_actual_renderer_bytes_and_mode_match_template(isolated_bifrost_audit):
    fixture = isolated_bifrost_audit
    expected = (REPO / "infra/llm_poc/config.template.json").read_bytes()
    for name, value in fixture.secrets.items():
        marker = {"bifrost_admin_password": b"$BIFROST_ADMIN_PASSWORD", "bifrost_virtual_key": b"$BIFROST_VIRTUAL_KEY",
                  "llm_relay_auth": b"$LLM_RELAY_AUTH"}[name]
        expected = expected.replace(marker, value.encode())
    actual, mode = actual_file(fixture.bifrost, "/app/data/config.json")
    assert actual == hashlib.sha256(expected).hexdigest(), "Rendered container bytes differ from template."
    assert mode == 0o600
    for name in ("start-bifrost.sh", "config.template.json", "pricing.json", "model-parameters.json", "mcp-library.json"):
        target = "/poc/" + name if name.endswith(".sh") else "/etc/bifrost/" + name
        actual, _ = actual_file(fixture.bifrost, target)
        assert actual == hashlib.sha256((REPO / "infra/llm_poc" / name).read_bytes()).hexdigest()


def test_effective_live_and_sqlite_settings_match_required_policy(isolated_bifrost_audit):
    checks = probe(isolated_bifrost_audit, "effective")
    assert all(checks.values()), "Effective config refusal: " + ", ".join(key for key, value in checks.items() if not value)


def test_actual_inference_and_management_auth_boundaries(isolated_bifrost_audit):
    checks = probe(isolated_bifrost_audit, "auth")
    assert all(checks.values()), "Native auth refusal: " + ", ".join(key for key, value in checks.items() if not value)


def test_actual_internal_network_no_ports_and_bifrost_outbound_denial(isolated_bifrost_audit):
    fixture = isolated_bifrost_audit
    fixture.network._unwrap_network.reload()
    assert fixture.network._unwrap_network.attrs["Internal"] is True
    for container in (fixture.bifrost, fixture.relay):
        wrapped = container.get_wrapped_container()
        wrapped.reload()
        assert set(wrapped.attrs["NetworkSettings"]["Networks"]) == {fixture.network.name}
        assert not wrapped.attrs["HostConfig"]["PortBindings"] and not any(wrapped.attrs["NetworkSettings"]["Ports"].values())
    code, _ = fixture.bifrost.exec(["nc", "-z", "-w", "2", "llm-gateway", "8081"])
    assert code == 0, "Positive relay network control failed."
    code, _ = fixture.bifrost.exec(["nc", "-z", "-w", "2", "1.1.1.1", "443"])
    assert code != 0, "External numeric address unexpectedly reachable."


def test_admin_mutation_changes_live_and_sqlite_without_changing_inspect_or_file(isolated_bifrost_audit):
    """Successful reproduction means config-integrity gate remains OPEN."""
    fixture = isolated_bifrost_audit
    before, _ = actual_file(fixture.bifrost, "/app/data/config.json")
    snapshot = inspected(fixture)
    try:
        checks = probe(fixture, "mutate")
        assert all(checks.values()), "Native mutation reproduction failed: " + ", ".join(key for key, value in checks.items() if not value)
        after, _ = actual_file(fixture.bifrost, "/app/data/config.json")
        assert before == after, "Upstream file unexpectedly changed."
        assert inspected(fixture) == snapshot, "Docker observation unexpectedly detects admin mutation."
    finally:
        restored = probe(fixture, "restore")
        assert all(restored.values()), "Synthetic config restore failed."


def test_credentials_and_synthetic_content_absent_from_logs(isolated_bifrost_audit):
    fixture = isolated_bifrost_audit
    forbidden = [value.encode() for value in fixture.secrets.values()] + [b"sk-bf-" + fixture.secrets["bifrost_virtual_key"].encode(),
                                                                      b"ISOLATED_BIFROST_AUDIT_SYNTHETIC_CONTENT"]
    for container in (fixture.bifrost, fixture.relay):
        raw = container.get_wrapped_container().logs(stdout=True, stderr=True)
        assert not any(value in raw for value in forbidden), "Container logs contain a synthetic credential or content canary."
        environment = "\n".join(container.get_wrapped_container().attrs["Config"]["Env"]).encode()
        assert not any(value in environment for value in forbidden), "Container environment contains a credential or content canary."
