"""Launch composition with explicit doubles; no DB, Docker, listener or provider."""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from ai_res.cli import candidate_launch as launch
from ai_res.modules.model_registry.poc_control import CandidateControlDenied
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceIdentity, ServiceName


def test_probe_dry_run_never_loads_settings_or_execution_resources(monkeypatch, capsys):
    monkeypatch.setattr(launch, "load_settings", lambda env: pytest.fail("dry run loaded settings"))
    monkeypatch.setattr(launch, "DockerCandidateObserver", lambda **kwargs: pytest.fail("dry run constructed observer"))
    assert launch.main(["probe", "--case", "TEXT"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "DRY_RUN"


@pytest.mark.parametrize("args", [[], ["probe", "--case", "TEXT", "--execute"],
    ["control", "--host-config", "/mounted/host"], ["--unrecognized-secret", "private-fixture"]])
def test_incomplete_launch_refuses_without_echoing_arguments(monkeypatch, capsys, args):
    monkeypatch.setattr(launch, "load_settings", lambda env: pytest.fail("invalid launch loaded settings"))
    assert launch.main(args) == 2
    assert "private-fixture" not in capsys.readouterr().err


def test_probe_execute_injects_existing_guarded_runner_context(monkeypatch, tmp_path):
    events = []
    settings = object()
    source = SimpleNamespace(code_revision="a" * 40, source_tree_sha256="b" * 64)
    monkeypatch.setattr(launch, "load_settings", lambda env: settings)
    monkeypatch.setattr(launch, "DockerCandidateObserver", lambda **kwargs: events.append(kwargs) or "observer")

    @asynccontextmanager
    async def host(config, root, evidence, actual_settings, virtual_key, *, docker_observer):
        assert (config, evidence, actual_settings, virtual_key, docker_observer) == (
            tmp_path / "host", tmp_path / "evidence", settings, tmp_path / "virtual", "observer")
        assert root == Path(launch.__file__).resolve().parents[4]
        events.append("opened")
        try:
            yield "runner", "manifest"
        finally:
            events.append("closed")

    def probe_main(args, *, host_factory):
        assert "--execute" in args and args[args.index("--case") + 1] == "TEXT"

        async def run():
            async with host_factory(source, tmp_path / "evidence") as result:
                assert result == ("runner", "manifest")
        asyncio.run(run())
        return 0

    monkeypatch.setattr(launch, "candidate_runner_host", host)
    monkeypatch.setattr(launch.flash_candidate, "main", probe_main)
    assert launch.main(["probe", "--case", "TEXT", "--execute", "--host-config", str(tmp_path / "host"),
        "--virtual-key-file", str(tmp_path / "virtual"), "--evidence-file", str(tmp_path / "evidence"),
        "--docker-executable", "/explicit/docker", "--docker-socket", "/explicit/docker.sock"]) == 0
    assert events == [{"executable": Path("/explicit/docker"), "socket_path": Path("/explicit/docker.sock")}, "opened", "closed"]


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "224.0.0.1", "ff02::1", "8.8.8.8", "169.254.1.2", "255.255.255.255", "not-an-ip"])  # noqa: S104 - denied inputs
def test_control_refuses_public_or_ambiguous_listen_addresses_before_resources(monkeypatch, capsys, address):
    monkeypatch.setattr(launch, "load_settings", lambda env: pytest.fail("unsafe listener loaded settings"))
    assert launch.main(["control", "--host-config", "/mounted/host", "--tls-cert-file", "/mounted/cert",
        "--tls-key-file", "/mounted/key", "--bind-address", address]) == 2
    assert address not in capsys.readouterr().err


@pytest.mark.parametrize("failure", [None, "serve", "cancel"])
async def test_control_uses_guarded_service_tls_auth_and_closes_resources(monkeypatch, tmp_path, failure):
    events = []
    attempt_id = "00000000-0000-4000-8000-000000000001"

    class Verifier:
        async def verify_service_token(self, token, audience):
            assert token == "fixture-service-token" and audience is ServiceName.API
            return ServiceIdentity(name=ServiceName.LLM_GATEWAY, audience=audience, expires_at=utc_now() + timedelta(minutes=1))

    class Service:
        async def claim(self, request):
            events.append("claim")
            raise CandidateControlDenied()

    @asynccontextmanager
    async def host(config, root, settings, *, docker_observer):
        events.append("opened")
        try:
            yield Service()
        finally:
            events.append("closed")

    class Server:
        def __init__(self, config):
            self.config = config

        async def serve(self):
            config = self.config
            assert config.host == "127.0.0.1" and config.port == 8443
            assert config.ssl_certfile == str(tmp_path / "cert") and config.ssl_keyfile == str(tmp_path / "key")
            assert config.proxy_headers is False and config.access_log is False and config.server_header is False
            async with httpx.AsyncClient(transport=httpx.ASGITransport(config.app), base_url="https://candidate") as client:
                body = {"version": "flash-candidate-control/0.1", "codecVersion": "flash-candidate-body/0.1",
                    "templateCase": "TEXT", "bodySha256": "a" * 64, "payloadBytes": 128, "stream": False, "maxOutputTokens": 256}
                assert (await client.post("/candidate/v1/claim", json=body)).status_code == 401
                headers = {"authorization": "Bearer fixture-service-token"}
                assert (await client.post("/candidate/v1/claim", json=body, headers=headers)).status_code == 409
                assert (await client.post("http://candidate/candidate/v1/claim", json=body, headers=headers)).status_code == 403
                # No generic execution or approval surface is installed.
                assert (await client.post("/approve", json={"id": attempt_id}, headers=headers)).status_code == 404
            if failure == "serve":
                raise RuntimeError("private-fixture")
            if failure == "cancel":
                raise asyncio.CancelledError()

    monkeypatch.setattr(launch, "serving_tls", lambda env: (tmp_path / "cert", tmp_path / "key"))
    monkeypatch.setattr(launch, "verifier_from_settings", lambda settings: Verifier())
    monkeypatch.setattr(launch, "candidate_control_host", host)
    monkeypatch.setattr(launch.uvicorn, "Server", Server)
    args = SimpleNamespace(host_config=tmp_path / "host", tls_cert_file=tmp_path / "cert", tls_key_file=tmp_path / "key",
                           bind_address="127.0.0.1", port=8443)
    if failure:
        with pytest.raises((RuntimeError, asyncio.CancelledError)):
            await launch.serve_control(args, object(), object())
    else:
        await launch.serve_control(args, object(), object())
    assert events == ["opened", "claim", "closed"]


def test_tls_or_config_failure_never_echoes_mounted_paths_or_private_details(monkeypatch, capsys):
    monkeypatch.setattr(launch, "load_settings", lambda env: (_ for _ in ()).throw(ValueError("private-fixture")))
    assert launch.main(["control", "--host-config", "/private-fixture/host", "--tls-cert-file", "/private-fixture/cert",
        "--tls-key-file", "/private-fixture/key"]) == 1
    assert "private-fixture" not in capsys.readouterr().err


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "192.168.1.10", "fd00::10"])
def test_control_accepts_only_explicit_private_or_loopback_listener(monkeypatch, address):
    seen = []
    monkeypatch.setattr(launch, "load_settings", lambda env: "settings")
    monkeypatch.setattr(launch, "DockerCandidateObserver", lambda **kwargs: "observer")

    async def serve(args, settings, observer):
        seen.append((args.bind_address, args.port, settings, observer))

    monkeypatch.setattr(launch, "serve_control", serve)
    assert launch.main(["control", "--host-config", "/mounted/host", "--tls-cert-file", "/mounted/cert",
        "--tls-key-file", "/mounted/key", "--bind-address", address]) == 0
    assert seen == [(address, 8443, "settings", "observer")]
