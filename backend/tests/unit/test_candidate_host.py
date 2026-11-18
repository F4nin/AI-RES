"""Host preparation only: actual files and explicit HTTP/Docker doubles, no live authority."""
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.modules.model_registry.candidate_host import (
    BIFROST_BIND_PATHS,
    HOST_VERSION,
    INPUT_PATHS,
    OFFICIAL_TARIFF_URL,
    CandidateDevelopmentGate,
    CandidateHostConfig,
    CandidateRuntimeObservation,
    DockerCandidateObserver,
    GuardedCandidateControl,
    OfficialTariffObserver,
    read_tariff_descriptor,
    runtime_observation,
)
from ai_res.modules.model_registry.candidate_integrity import NAMESPACE_FILES, CandidateIntegrityObservation
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest
from ai_res.modules.model_registry.poc_budget import AUTHORIZATION_KEY
from ai_res.modules.model_registry.poc_control import CandidateControlDenied


def sha(data):
    return hashlib.sha256(data).hexdigest()


def config_fixture(tmp_path):
    snapshot = b"reviewed synthetic official pricing snapshot"
    tariff = {"version": "flash-candidate-tariff/0.1", "sourceUrl": OFFICIAL_TARIFF_URL, "snapshotSha256": sha(snapshot),
              "currency": "USD", "inputPerMillion": "0.30", "outputPerMillion": "1.20", "inputBound": 2_000_000, "outputBound": 256}
    hashes = {}
    for role, relative in INPUT_PATHS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(tariff).encode() if role == "tariff" else f"synthetic-{role}".encode()
        path.write_bytes(content)
        hashes[role] = sha(content)
    manifest = CandidateRunManifest("a" * 40, "b" * 64, hashes["config"], hashes["prompt"], None, "e" * 64, hashes["plan"], hashes["tariff"])
    document = {"version": HOST_VERSION, "authorizationKey": AUTHORIZATION_KEY, "accountId": str(uuid4()), "manifest": manifest.to_dict(),
                "tariffSnapshotSha256": sha(snapshot), "bifrostContainerId": "f" * 64, "expectedRuntimeSha256": "1" * 64,
                "expectedIntegritySha256": "2" * 64,
                "inputPaths": {**INPUT_PATHS, "tools": None}}
    path = tmp_path / "host.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    return CandidateHostConfig.load(path), manifest, snapshot, path, document


class Observer:
    def __init__(self, value):
        self.value, self.calls = value, 0

    async def snapshot_sha256(self):
        self.calls += 1
        return self.value

    async def observe(self, container_id):
        self.calls += 1
        return self.value


def gate_fixture(tmp_path):
    config, manifest, snapshot, path, document = config_fixture(tmp_path)
    tariff = Observer(sha(snapshot))
    mounts = tuple((destination, str(tmp_path / relative)) for destination, relative in BIFROST_BIND_PATHS.items())
    for relative in BIFROST_BIND_PATHS.values():
        path_to_mount = tmp_path / relative
        if not path_to_mount.exists():
            path_to_mount.write_text("synthetic-reviewed-source")
    for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth"):
        secret_path = tmp_path / name
        secret_path.write_text("synthetic-mount")
        mounts += (("/run/secrets/" + name, str(secret_path)),)
    file_hashes = {destination: sha(Path(source).read_bytes()) for destination, source in mounts}
    integrity = CandidateIntegrityObservation("2" * 64, "b" * 32,
        tuple((destination, 0o600, file_hashes.get(destination, "a" * 64)) for destination in NAMESPACE_FILES))
    image = Observer(CandidateRuntimeObservation("e" * 64, "1" * 64, mounts, integrity, True))
    gate = CandidateDevelopmentGate(config, tmp_path, source_reader=lambda: ("a" * 40, "b" * 64),
                                    tariff_observer=tariff, image_observer=image)
    return gate, tariff, image, path, document, manifest


async def test_every_gate_validation_reads_fresh_tariff_and_actual_runtime(tmp_path):
    gate, tariff, image, _, _, manifest = gate_fixture(tmp_path)
    body = build_candidate_body("TEXT", uuid4())
    await gate.validate(body, manifest)
    await gate.validate(body, manifest)
    assert tariff.calls == image.calls == 2
    tariff.value = "0" * 64
    with pytest.raises(CandidateRunDenied):
        await gate.validate(body, manifest)


async def test_source_or_manifest_drift_refuses_before_external_observation(tmp_path):
    gate, tariff, image, _, _, manifest = gate_fixture(tmp_path)
    with pytest.raises(CandidateRunDenied):
        await gate.validate(build_candidate_body("TEXT", uuid4()), replace(manifest, source_tree_sha256="0" * 64))
    assert tariff.calls == image.calls == 0


async def test_revoked_host_stops_claim_but_never_blocks_settlement(tmp_path):
    gate, _, _, path, _, _ = gate_fixture(tmp_path)

    class Control:
        calls = []

        async def claim(self, request):
            self.calls.append("claim")
            return request

        async def settle(self, request):
            self.calls.append("settle")
            return request

    service = Control()
    guarded = GuardedCandidateControl(service, gate)
    marker = object()
    assert await guarded.claim(marker) is marker
    path.write_text("revoked")
    with pytest.raises(CandidateControlDenied):
        await guarded.claim(marker)
    assert await guarded.settle(marker) is marker
    assert service.calls == ["claim", "settle"]


async def test_official_observer_performs_new_bounded_get_each_time():
    requests = []

    def handle(request):
        requests.append(request)
        assert str(request.url) == OFFICIAL_TARIFF_URL and request.method == "GET"
        assert request.headers["cache-control"] == "no-cache"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, stream=httpx.ByteStream(b"snapshot"), headers={"content-type": "text/html"})

    async with OfficialTariffObserver(http_transport=httpx.MockTransport(handle)) as observer:
        assert await observer.snapshot_sha256() == sha(b"snapshot")
        assert await observer.snapshot_sha256() == sha(b"snapshot")
    assert len(requests) == 2


@pytest.mark.parametrize("change", ["unknown", "authorization", "account", "bool-account", "version", "input-path", "tools", "runtime-hash", "duplicates"])
def test_closed_config_cannot_change_authority_or_read_arbitrary_paths(tmp_path, change):
    _, _, _, path, document = config_fixture(tmp_path)
    if change == "unknown":
        document["allowProviderCalls"] = True
    elif change == "authorization":
        document["authorizationKey"] = "NEW_WALLET"
    elif change == "account":
        document["accountId"] = "wrong"
    elif change == "bool-account":
        document["accountId"] = True
    elif change == "version":
        document["version"] = "flash-candidate-host/9.0"
    elif change == "input-path":
        document["inputPaths"]["tariff"] = "secrets/provider-key"
    elif change == "tools":
        document["manifest"]["toolsSha256"] = "2" * 64
    elif change == "runtime-hash":
        document["expectedRuntimeSha256"] = "not-a-sha"
    path.write_text(json.dumps(document) if change != "duplicates" else '{"version":1,"version":2}')
    with pytest.raises(CandidateRunDenied):
        CandidateHostConfig.load(path)


@pytest.mark.parametrize("unsafe", ["symlink", "ancestor-symlink", "writable", "hardlink", "oversize", "empty", "fifo"])
def test_host_config_input_files_are_bounded_regular_and_protected(tmp_path, unsafe):
    _, _, _, path, _ = config_fixture(tmp_path)
    if unsafe == "symlink":
        target = tmp_path / "real.json"
        path.rename(target)
        path.symlink_to(target)
    elif unsafe == "ancestor-symlink":
        indirect = tmp_path / "alias"
        indirect.symlink_to(tmp_path, target_is_directory=True)
        path = indirect / path.name
    elif unsafe == "writable":
        path.chmod(0o666)
    elif unsafe == "hardlink":
        os.link(path, tmp_path / "hardlink")
    elif unsafe == "oversize":
        path.write_bytes(b"x" * 1_048_577)
    elif unsafe == "empty":
        path.write_bytes(b"")
    else:
        path.unlink()
        os.mkfifo(path)
    with pytest.raises(CandidateRunDenied):
        CandidateHostConfig.load(path)


@pytest.mark.parametrize("role", ["config", "plan", "tariff", "prompt"])
async def test_changed_managed_input_refuses_before_tariff_or_docker(tmp_path, role):
    gate, tariff, image, _, _, _ = gate_fixture(tmp_path)
    (tmp_path / INPUT_PATHS[role]).write_text("changed input")
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()
    assert tariff.calls == image.calls == 0


@pytest.mark.parametrize("change", ["image", "runtime", "mount-source", "missing-mount", "provider-key-mount"])
async def test_actual_container_binding_refuses_changed_image_configuration_or_mounts(tmp_path, change):
    gate, _, image, _, _, _ = gate_fixture(tmp_path)
    value = image.value
    if change == "image":
        image.value = replace(value, image_sha256="0" * 64)
    elif change == "runtime":
        image.value = replace(value, runtime_sha256="0" * 64)
    elif change == "mount-source":
        image.value = replace(value, bind_mounts=((value.bind_mounts[0][0], "/different/source"), *value.bind_mounts[1:]))
    elif change == "missing-mount":
        image.value = replace(value, bind_mounts=value.bind_mounts[1:])
    else:
        image.value = replace(value, bind_mounts=(*value.bind_mounts, ("/run/secrets/provider_key", "/sensitive/key")))
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()


async def test_local_config_mutated_during_fresh_fetch_refuses_final_revalidation(tmp_path):
    gate, tariff, _, path, _, _ = gate_fixture(tmp_path)

    async def mutate():
        path.write_text("revoked during network wait")
        return tariff.value

    tariff.snapshot_sha256 = mutate
    with pytest.raises(CandidateRunDenied):
        await gate.validate_host()


@pytest.mark.parametrize("failure", ["status", "redirect", "cached", "encoding", "media", "empty", "oversize", "network"])
async def test_fresh_official_observer_refuses_untrusted_or_unavailable_source(failure):
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "network":
            raise httpx.ConnectError("withheld synthetic detail")
        status = {"status": 503, "redirect": 302, "cached": 304}.get(failure, 200)
        body = b"" if failure == "empty" else b"x" * (1_048_577 if failure == "oversize" else 10)
        headers = {"content-type": "application/json" if failure == "media" else "text/html"}
        if failure == "encoding":
            headers["content-encoding"] = "gzip"
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(body))

    async with OfficialTariffObserver(http_transport=httpx.MockTransport(respond)) as observer:
        with pytest.raises(CandidateRunDenied):
            await observer.snapshot_sha256()
    assert len(calls) == 1


def runtime_fixture():
    return {"Id": "f" * 64, "Image": "sha256:" + "e" * 64,
            "State": {"Running": True, "StartedAt": "2026-11-18T12:00:00.000000000Z", "Pid": 100}, "RestartCount": 0,
            "Config": {"User": "1000:1000", "Env": ["PATH=/usr/bin", "CREDENTIAL_FILE=/run/secrets/example"],
                       "Entrypoint": ["/bin/sh", "/app/start-candidate.sh"], "Cmd": []},
            "HostConfig": {"ReadonlyRootfs": True, "Privileged": False, "NetworkMode": "isolated", "PidMode": "", "IpcMode": "",
                           "PortBindings": {}, "PublishAllPorts": False, "Devices": [], "DeviceRequests": [], "CapAdd": [],
                           "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"]},
            "Mounts": [{"Type": "bind", "Destination": "/poc/start-bifrost.sh", "Source": "/reviewed/start-bifrost.sh", "RW": False},
                       {"Type": "tmpfs", "Destination": "/app/data", "RW": True}],
            "NetworkSettings": {"Networks": {"candidate": {"NetworkID": "d" * 64, "Aliases": ["bifrost-poc"], "IPAddress": "10.0.0.4"}}}}


def test_runtime_hash_covers_actual_configuration_and_excludes_only_transient_ips():
    data = runtime_fixture()
    original = runtime_observation(data, "f" * 64)
    data["NetworkSettings"]["Networks"]["candidate"]["IPAddress"] = "10.0.0.99"
    assert runtime_observation(data, "f" * 64) == original
    data["Config"]["Cmd"] = ["changed"]
    assert runtime_observation(data, "f" * 64).runtime_sha256 != original.runtime_sha256
    assert "changed" not in repr(runtime_observation(data, "f" * 64))


def test_runtime_mount_order_is_irrelevant_but_mount_contents_remain_bound():
    """Docker returned different Mounts ordering for the same running container."""
    data = runtime_fixture()
    original = runtime_observation(data, "f" * 64)
    data["Mounts"].reverse()
    assert runtime_observation(data, "f" * 64) == original
    bound = next(mount for mount in data["Mounts"] if mount["Type"] == "bind")
    bound["Source"] = "/different/reviewed/source"
    assert runtime_observation(data, "f" * 64).runtime_sha256 != original.runtime_sha256


@pytest.mark.parametrize("change", ["root", "false-security", "privileged", "write-root", "hostnet", "hostpid", "hostipc", "published",
                                     "capadd", "socket", "write-bind", "other-tmpfs", "provider-key", "secret-env", "stopped", "bad-image"])
def test_runtime_refuses_known_unsafe_container_shapes(change):
    data = runtime_fixture()
    if change == "root":
        data["Config"]["User"] = "0:0"
    elif change == "false-security":
        data["HostConfig"]["SecurityOpt"] = ["no-new-privileges:false"]
    elif change == "privileged":
        data["HostConfig"]["Privileged"] = True
    elif change == "write-root":
        data["HostConfig"]["ReadonlyRootfs"] = False
    elif change in {"hostnet", "hostpid", "hostipc"}:
        data["HostConfig"][{"hostnet": "NetworkMode", "hostpid": "PidMode", "hostipc": "IpcMode"}[change]] = "host"
    elif change == "published":
        data["HostConfig"]["PortBindings"] = {"8080/tcp": [{"HostPort": "8080"}]}
    elif change == "capadd":
        data["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    elif change == "socket":
        data["Mounts"][0]["Source"] = "/var/run/docker.sock"
    elif change == "write-bind":
        data["Mounts"][0]["RW"] = True
    elif change == "other-tmpfs":
        data["Mounts"][1]["Destination"] = "/poc"
    elif change == "provider-key":
        data["Mounts"][0]["Destination"] = "/run/secrets/deepseek_api_key"
    elif change == "secret-env":
        data["Config"]["Env"].append("PROVIDER_API_KEY=fixture")
    elif change == "stopped":
        data["State"]["Running"] = False
    else:
        data["Image"] = "mutable-tag"
    with pytest.raises(CandidateRunDenied) as caught:
        runtime_observation(data, "f" * 64)
    assert "fixture" not in str(caught.value)


async def test_docker_inspector_uses_fixed_namespace_command_and_drains_split_output(monkeypatch):
    from .test_candidate_integrity import namespace_raw
    data = json.dumps(runtime_fixture()).encode()
    commands = []

    class Reader:
        def __init__(self, content):
            self.parts = [content[:17], content[17:100], content[100:], b""]

        async def read(self, count):
            return self.parts.pop(0)

    class Process:
        def __init__(self, content):
            self.stdout, self.returncode = Reader(content), None

        async def wait(self):
            self.returncode = 0
            return 0

    async def spawn(*command, **kwargs):
        commands.append((command, kwargs))
        return Process(namespace_raw() if command[3] == "exec" else data)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    actual = await DockerCandidateObserver().observe("f" * 64)
    assert actual.image_sha256 == "e" * 64
    command, options = commands[0]
    assert command[1:5] == ("--host", "unix:///var/run/docker.sock", "container", "inspect")
    assert options["env"] == {"DOCKER_CONFIG": "/nonexistent"} and "shell" not in options
    assert len(commands) == 3 and actual.integrity is not None
    assert commands[1][0][3:8] == ("exec", "f" * 64, "/usr/bin/env", "-i", "PATH=/usr/bin:/bin")


def test_tariff_descriptor_exports_only_immutable_decimal_rates(tmp_path):
    config, _, snapshot, _, _ = config_fixture(tmp_path)
    tariff = read_tariff_descriptor(config, tmp_path)
    assert str(tariff.input_per_million) == "0.30" and str(tariff.output_per_million) == "1.20"
    assert tariff.snapshot_sha256 == sha(snapshot) and tariff.input_bound == 2_000_000 and tariff.output_bound == 256


@pytest.mark.parametrize("field,value", [("sourceUrl", "https://wrong.example/"), ("snapshotSha256", "0" * 64), ("currency", "EUR"),
                                         ("inputBound", True), ("inputBound", 4096), ("outputBound", 1000),
                                         ("inputPerMillion", 0.3), ("inputPerMillion", "NaN"), ("inputPerMillion", "-1"),
                                         ("outputPerMillion", "0"), ("version", "flash-candidate-tariff/9.0")])
def test_tariff_descriptor_cannot_detach_rates_from_reviewed_official_snapshot(tmp_path, field, value):
    config, _, _, _, _ = config_fixture(tmp_path)
    path = tmp_path / INPUT_PATHS["tariff"]
    document = json.loads(path.read_text())
    document[field] = value
    content = json.dumps(document).encode()
    path.write_bytes(content)
    config = replace(config, manifest=replace(config.manifest, tariff_sha256=sha(content)))
    with pytest.raises(CandidateRunDenied):
        read_tariff_descriptor(config, tmp_path)


@pytest.mark.parametrize("stage", ["source", "tariff", "image"])
async def test_dependency_failure_is_fail_closed_and_does_not_export_exception(tmp_path, stage):
    gate, tariff, image, _, _, _ = gate_fixture(tmp_path)

    def fail_source():
        raise RuntimeError("synthetic-secret-do-not-export")

    async def fail_observer(*args):
        raise RuntimeError("synthetic-secret-do-not-export")

    if stage == "source":
        gate._source = fail_source
    elif stage == "tariff":
        tariff.snapshot_sha256 = fail_observer
    else:
        image.observe = fail_observer
    with pytest.raises(CandidateRunDenied) as caught:
        await gate.validate_host()
    assert "synthetic-secret" not in str(caught.value)


async def test_gate_cancellation_is_preserved(tmp_path):
    gate, tariff, _, _, _, _ = gate_fixture(tmp_path)

    async def cancelled():
        raise asyncio.CancelledError()

    tariff.snapshot_sha256 = cancelled
    with pytest.raises(asyncio.CancelledError):
        await gate.validate_host()


async def test_fresh_tariff_response_is_closed_when_stream_cancels():
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first fragment"
            raise asyncio.CancelledError()

        async def aclose(self):
            closed.append(True)

    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/html"}, stream=Stream()))
    async with OfficialTariffObserver(http_transport=transport) as observer:
        with pytest.raises(asyncio.CancelledError):
            await observer.snapshot_sha256()
    assert closed == [True]


@pytest.mark.parametrize("failure", ["oversize", "cancelled", "badjson", "exit"])
async def test_docker_reader_closes_its_process_on_refusal_and_cancellation(monkeypatch, failure):
    events = []

    class Reader:
        def __init__(self):
            self.count = 0

        async def read(self, count):
            self.count += 1
            if failure == "cancelled":
                raise asyncio.CancelledError()
            if failure == "oversize":
                return b"x" * 65_536
            return b"invalid" if self.count == 1 else b""

    class Process:
        stdout, returncode = Reader(), None

        def kill(self):
            events.append("kill")
            self.returncode = -9

        async def wait(self):
            events.append("wait")
            self.returncode = 1 if failure == "exit" else 0
            return self.returncode

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(asyncio.CancelledError if failure == "cancelled" else CandidateRunDenied):
        await DockerCandidateObserver().observe("f" * 64)
    assert "wait" in events
    assert ("kill" in events) is (failure in {"oversize", "cancelled"})
