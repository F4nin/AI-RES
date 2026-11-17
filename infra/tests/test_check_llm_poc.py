"""The no-paid probe must refuse a live relay before attempting any inference request."""
import io
import json
import sys
import urllib.request
from copy import deepcopy

import check_llm_poc as probe
import pytest


@pytest.mark.parametrize("health", [{"status": "enabled"}, {"status": "unknown"}, {}])
def test_probe_checks_disabled_state_before_any_model_shaped_request(monkeypatch, health):
    requested = []

    class Reply(io.BytesIO):
        status = 200

    class Opener:
        def open(self, request, timeout):
            requested.append(request)
            assert request == "http://127.0.0.1:8081/health"
            return Reply(json.dumps(health).encode())

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"bifrost_virtual_key": "fixture", "bifrost_admin_password": "fixture"})))
    with pytest.raises(SystemExit) as stopped:
        exec(compile(probe.PROBE, "isolated_poc_probe", "exec"), {})  # noqa: S102 -- execute only our fixed probe, with network mocked
    assert stopped.value.code == 2
    assert requested == ["http://127.0.0.1:8081/health"]


def test_host_preflight_refuses_commands_provider_env_and_secret_mounts_that_could_enable_live_inference():
    model = {"Config": {"Cmd": ["python", "/poc/relay.py"], "Env": []}, "Mounts": [{"Destination": "/run/secrets/llm_relay_auth"}]}
    assert probe.disabled_relay_configuration(model)
    for kind in ("command", "provider_env", "provider_mount"):
        changed = deepcopy(model)
        if kind == "command":
            changed["Config"]["Cmd"].append("--allow-provider-calls")
        elif kind == "provider_env":
            changed["Config"]["Env"].append("AI_RES_DEEPSEEK_API_KEY_FILE=/run/secrets/provider")
        else:
            changed["Mounts"].append({"Destination": "/run/secrets/provider"})
        assert not probe.disabled_relay_configuration(changed)
