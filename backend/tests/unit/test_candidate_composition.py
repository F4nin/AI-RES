"""Host resource lifetimes; explicit doubles, no DB/Docker/provider evidence."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_res.cli import candidate_composition as composition
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied


@pytest.mark.parametrize("failure", [None, "gate", "account", "probe", "body", "cancel"])
async def test_runner_host_closes_acquired_resources_in_reverse_order(tmp_path, monkeypatch, failure):
    events = []
    account = uuid4()
    config = SimpleNamespace(account_id=account, manifest=object())
    settings = SimpleNamespace(db_user="ai_res_api", environment="test")

    class Tariff:
        async def __aenter__(self):
            events.append("tariff-open")
            return self

        async def __aexit__(self, *args):
            events.append("tariff-close")

    class Gate:
        def __init__(self, *args, **kwargs):
            pass

        async def validate_host(self):
            events.append("gate")
            if failure == "gate":
                raise CandidateRunDenied()

    class Engine:
        async def dispose(self):
            events.append("engine-close")

    class Probe:
        def __init__(self, **kwargs):
            events.append("probe-construct")
            if failure == "probe":
                raise ValueError("private fixture details")

        async def __aenter__(self):
            events.append("probe-open")
            return self

        async def __aexit__(self, *args):
            events.append("probe-close")

    async def account_check(*args):
        events.append("account")
        if failure == "account":
            raise CandidateRunDenied()

    monkeypatch.setattr(composition.CandidateHostConfig, "load", lambda path: config)
    monkeypatch.setattr(composition, "OfficialTariffObserver", Tariff)
    monkeypatch.setattr(composition, "CandidateDevelopmentGate", Gate)
    monkeypatch.setattr(composition, "_gate", lambda *args: Gate())
    monkeypatch.setattr(composition, "read_tariff_descriptor", lambda *args: object())
    monkeypatch.setattr(composition, "create_runtime_engine", lambda settings: events.append("engine-open") or Engine())
    monkeypatch.setattr(composition, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(composition, "verify_candidate_account", account_check)
    monkeypatch.setattr(composition, "mounted_virtual_key", lambda path: "fixture-virtual")
    monkeypatch.setattr(composition, "FlashCandidateProbe", Probe)
    monkeypatch.setattr(composition, "CandidateRunner", lambda *args: object())
    monkeypatch.setattr(composition, "TechnicalPaidLedger", lambda *args: object())
    monkeypatch.setattr(composition, "CandidateAccountingReader", lambda *args: object())

    async def run():
        async with composition.candidate_runner_host(tmp_path / "host.json", tmp_path, tmp_path / "evidence.jsonl",
                                                      settings, tmp_path / "virtual.key") as (_, manifest):
            assert manifest is config.manifest
            if failure == "body":
                raise ValueError("private fixture details")
            if failure == "cancel":
                raise asyncio.CancelledError()

    if failure is None:
        await run()
    else:
        with pytest.raises((ValueError, CandidateRunDenied, asyncio.CancelledError)):
            await run()
    assert events[-1] == "tariff-close"
    if "engine-open" in events:
        assert events.count("engine-close") == 1
    if "probe-open" in events:
        assert events[-3:] == ["probe-close", "engine-close", "tariff-close"]
    if failure == "gate":
        assert "engine-open" not in events and "account" not in events


@pytest.mark.parametrize("kind", ["symlink", "public", "fifo", "empty", "oversized", "newline", "provider", "rawhex"])
def test_virtual_key_mount_refuses_unsafe_material_without_echo(tmp_path, kind):
    import os

    path = tmp_path / "key"
    if kind == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.write_text("sk-bf-" + "a" * 64)
        path.chmod(0o600)
        if kind == "symlink":
            target = tmp_path / "link"
            target.symlink_to(path)
            path = target
        elif kind == "public":
            path.chmod(0o644)
        elif kind == "empty":
            path.write_bytes(b"")
        elif kind == "oversized":
            path.write_bytes(b"x" * 1025)
        elif kind == "newline":
            path.write_bytes(b"fixture\ninjected")
        elif kind == "provider":
            path.write_text("sk-" + "a" * 64)
        elif kind == "rawhex":
            path.write_text("a" * 64)
    with pytest.raises(CandidateRunDenied) as error:
        composition.mounted_virtual_key(path)
    assert "fixture" not in str(error.value)


def test_only_complete_bifrost_virtual_key_is_accepted(tmp_path):
    path = tmp_path / "virtual"
    value = "sk-bf-" + "a" * 64
    path.write_text(value + "\n")
    path.chmod(0o400)
    assert composition.mounted_virtual_key(path) == value


@pytest.mark.parametrize("failure", [None, "construct", "cancel"])
async def test_control_composition_revalidates_each_claim_keeps_settlement_and_closes(tmp_path, monkeypatch, failure):
    from ai_res.modules.model_registry.poc_control import CandidateControlDenied

    events = []
    manifest = SimpleNamespace(plan_sha256="a" * 64, tariff_sha256="b" * 64)
    config = SimpleNamespace(account_id=uuid4(), manifest=manifest)
    revoked = False

    class Tariff:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            events.append("tariff-close")

    class Engine:
        async def dispose(self):
            events.append("engine-close")

    class Gate:
        async def validate_host(self):
            events.append("gate")
            if revoked:
                raise CandidateRunDenied()

    class Control:
        def __init__(self, *args):
            if failure == "construct":
                raise ValueError("fixture construction")

        async def claim(self, request):
            events.append("claim")
            return "fixture receipt"

        async def settle(self, request):
            events.append("settle")
            return "fixture accounting"

    async def account_check(*args):
        events.append("account")

    monkeypatch.setattr(composition.CandidateHostConfig, "load", lambda path: config)
    monkeypatch.setattr(composition, "OfficialTariffObserver", Tariff)
    monkeypatch.setattr(composition, "_gate", lambda *args: Gate())
    monkeypatch.setattr(composition, "create_runtime_engine", lambda *args: Engine())
    monkeypatch.setattr(composition, "create_session_factory", lambda *args: object())
    monkeypatch.setattr(composition, "CandidateControlService", Control)
    monkeypatch.setattr(composition, "read_tariff_descriptor", lambda *args: object())
    monkeypatch.setattr(composition, "verify_candidate_account", account_check)

    async def run():
        nonlocal revoked
        async with composition.candidate_control_host(tmp_path / "config", tmp_path, SimpleNamespace(db_user="ai_res_api", environment="test")) as control:
            assert events == []  # Settlement need not wait for freshness at startup.
            for _ in range(2):
                assert await control.claim(object()) == "fixture receipt"
            assert events == ["gate", "account", "claim"] * 2
            revoked = True
            with pytest.raises(CandidateControlDenied):
                await control.claim(object())
            assert await control.settle(object()) == "fixture accounting"
            if failure == "cancel":
                raise asyncio.CancelledError()

    if failure:
        with pytest.raises((ValueError, asyncio.CancelledError)):
            await run()
    else:
        await run()
    assert events[-2:] == ["engine-close", "tariff-close"]


def test_composition_refuses_another_checkout_and_accepts_explicit_local_docker_paths(tmp_path, monkeypatch):
    from pathlib import Path

    with pytest.raises(CandidateRunDenied, match="BINDING_MISMATCH"):
        composition._gate(object(), tmp_path, object())
    seen = []
    monkeypatch.setattr(composition, "CandidateDevelopmentGate", lambda *args, **kwargs: seen.append(kwargs["image_observer"]))
    observer = composition.DockerCandidateObserver(executable=Path("/usr/bin/docker"), socket_path=tmp_path / "docker.sock")
    composition._gate(object(), Path(composition.__file__).resolve().parents[4], object(), observer)
    assert seen == [observer]


@pytest.mark.parametrize("runner", [False, True])
@pytest.mark.parametrize("settings", [SimpleNamespace(db_user="ai_res_api", environment="prod"),
                                     SimpleNamespace(db_user="ai_res_migrator", environment="test")])
async def test_production_or_privileged_host_refuses_before_config_or_resources(tmp_path, monkeypatch, runner, settings):
    monkeypatch.setattr(composition.CandidateHostConfig, "load", lambda path: pytest.fail("unsafe host read configuration"))
    context = (composition.candidate_runner_host(tmp_path / "config", tmp_path, tmp_path / "evidence", settings, tmp_path / "key")
               if runner else composition.candidate_control_host(tmp_path / "config", tmp_path, settings))
    with pytest.raises(CandidateRunDenied, match="HOST_UNCONFIGURED"):
        async with context:
            pytest.fail("unsafe host acquired resources")
