"""Actual pinned Bifrost + real SLICE relay/ledger, entirely unpaid upstream."""
import hashlib
import importlib.util
import json
from datetime import UTC, datetime

import docker
import pytest
from scripts.slice01.common import BIFROST_IMAGE, ROOT, canonical
from scripts.slice01.prepare import prepare
from scripts.slice01.runtime import SliceRuntime

from .test_flash_candidate_bifrost import _fixture_image


@pytest.fixture(scope="module")
def slice_images():
    client = docker.from_env()
    try:
        try:
            bf = client.images.get(BIFROST_IMAGE).id
        except docker.errors.ImageNotFound:
            spec = importlib.util.spec_from_file_location("slice_native_builder", ROOT / "infra/llm_poc/bifrost_integrity/build.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            bf, _ = module.build_image()
    finally:
        client.close()
    return bf, _fixture_image()


@pytest.fixture
def slice_native(tmp_path, slice_images):
    bf, py = slice_images
    directory = tmp_path / "scenario"
    prepare(directory, mode="fixture", tariff_checked_at=datetime.now(UTC), bifrost_image=bf, python_image=py)
    runtime = SliceRuntime(directory)
    started = False
    try:
        state = runtime.start(fixture_entry=ROOT / "backend/tests/fixtures/slice01_native_relay.py")
        started = True
        yield runtime, state, directory
    finally:
        if started:
            runtime.stop()
        runtime.close()


def test_real_native_bootstrap_and_governed_transport_wire(slice_native):
    runtime, state, directory = slice_native
    caller = runtime.client.containers.get(state["containers"]["caller"]["id"])
    script = (ROOT / "backend/tests/fixtures/slice01_native_caller.py").read_text()
    result = caller.exec_run(["python", "-B", "-c", script], demux=True)
    assert result.exit_code == 0, "Native fixture caller failed; raw credential-bearing HTTP context withheld."
    summary = json.loads(result.output[0])
    assert summary == {"nativeFixture": "PASS", "attempts": 2, "providerCalls": 0}
    for phase in ("bootstrap", "run"):
        wire = json.loads((directory / "wallet" / (phase + "-wire.json")).read_bytes())
        assert wire["model"] == "deepseek-flash" and wire["max_tokens"] == 2048
        assert wire["thinking"] == {"type": "disabled"} and wire["stream"] is False
        assert "store" not in wire and "tools" not in wire and "fallbacks" not in wire
        request_ref = runtime.plan["phases"][phase]
        assert hashlib.sha256(canonical(wire)).hexdigest() == runtime.plan["requests"][request_ref]["bodySha256"]
    assert len(json.loads((directory / "wallet/run-wire.json").read_text())["messages"]) == 2
    request_ref = runtime.plan["phases"]["run"]
    quarantine = json.loads((directory / "results" / f"transport-quarantine-{request_ref}.json").read_bytes())
    validation = json.loads((directory / "results" / f"validation-{request_ref}.json").read_bytes())
    assert quarantine["status"] == "UNTRUSTED_TRANSPORT_OUTPUT" and validation["status"] == "PASSED"
    assert validation["quarantineSha256"] == hashlib.sha256(
        (directory / "results" / f"transport-quarantine-{request_ref}.json").read_bytes()).hexdigest()
    runtime.verify()


def test_fixture_cannot_reach_provider_or_main_data_network(slice_native):
    runtime, state, _ = slice_native
    for name, snap in state["containers"].items():
        c = runtime.client.containers.get(snap["id"])
        c.reload()
        assert len(c.attrs["NetworkSettings"]["Networks"]) == 1
        assert not c.attrs["HostConfig"].get("PortBindings")
        assert not any("api_db_password" in m["Destination"] or "owner_session" in m["Destination"] for m in c.attrs["Mounts"])
        for network_id in state["networks"]:
            assert runtime.client.networks.get(network_id).attrs["Internal"] is True
        if name == "relay":
            assert any("fixture_provider_key" in m["Source"] for m in c.attrs["Mounts"])
        assert not any("candidate/runtime/deepseek_api_key" in m["Source"] for m in c.attrs["Mounts"])
    bf = runtime.client.containers.get(state["containers"]["bifrost"]["id"])
    assert bf.exec_run(["nc", "-z", "-w", "1", "llm-gateway", "8081"]).exit_code == 0
    assert bf.exec_run(["nc", "-z", "-w", "1", "1.1.1.1", "443"]).exit_code != 0


def test_runtime_restart_is_not_silently_reaccepted(slice_native):
    runtime, state, _ = slice_native
    runtime.client.containers.get(state["containers"]["caller"]["id"]).restart()
    with pytest.raises(ValueError, match="RUNTIME_CHANGED"):
        runtime.verify()
