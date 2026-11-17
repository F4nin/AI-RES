"""S16: actual secret rendering and the least-privilege Bifrost configuration. No provider calls or real credentials.

Field names are from maximhq/bifrost transports/v2.5.1 config.schema.json. These policy/renderer tests do not replace
validation by the pinned upstream binary or its live auth and isolation tests.
"""
import json
import os
import stat
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "llm_poc" / "start-bifrost.sh"
TEMPLATE = ROOT / "llm_poc" / "config.template.json"
SYNTHETIC = {
    "bifrost_admin_password": "a1" * 32,
    "bifrost_virtual_key": "b2" * 32,
    "llm_relay_auth": "c3" * 32,
}


def render(tmp_path, *, values=None, template=TEMPLATE, extra_env=None):
    secret_dir = tmp_path / "secrets"
    app_dir = tmp_path / "app"
    secret_dir.mkdir(exist_ok=True)
    app_dir.mkdir(exist_ok=True)
    for name, value in (SYNTHETIC if values is None else values).items():
        (secret_dir / name).write_text(value)
    env = {**os.environ, "APP_DIR": str(app_dir), "BIFROST_SECRETS_DIR": str(secret_dir), "BIFROST_CONFIG_TEMPLATE": str(template),
           **(extra_env or {})}
    result = subprocess.run(["/bin/sh", str(START), "--render-only"], capture_output=True, text=True, env=env, check=False)
    assert not any(value in result.stdout + result.stderr for value in SYNTHETIC.values())
    return result, app_dir


def test_rendered_configuration_requires_auth_and_limits_provider_and_model(tmp_path):
    result, app_dir = render(tmp_path)
    assert result.returncode == 0 and result.stdout == result.stderr == ""
    config = json.loads((app_dir / "config.json").read_text())
    assert stat.S_IMODE((app_dir / "config.json").stat().st_mode) == 0o600
    assert config["version"] == 2
    client = config["client"]
    assert client["enforce_auth_on_inference"] is True and client["allow_direct_keys"] is False
    assert client["whitelisted_routes"] == client["allowed_origins"] == []
    auth = config["governance"]["auth_config"]
    assert auth["is_enabled"] is True and auth["disable_auth_on_inference"] is False
    assert auth["admin_password"] == SYNTHETIC["bifrost_admin_password"]
    provider = config["providers"]["deepseek"]
    assert set(config["providers"]) == {"deepseek"}
    key, = provider["keys"]
    assert key["value"] == SYNTHETIC["llm_relay_auth"] and key["models"] == ["deepseek-flash"]
    virtual_key, = config["governance"]["virtual_keys"]
    assert virtual_key["value"] == "sk-bf-" + SYNTHETIC["bifrost_virtual_key"]
    assert virtual_key["allow_all_providers"] is False and virtual_key["is_active"] is True
    permission, = virtual_key["provider_configs"]
    assert permission["provider"] == "deepseek" and permission["allowed_models"] == ["deepseek-flash"]
    assert permission["key_ids"] == [key["id"]]
    assert provider["network_config"]["base_url"] == "http://llm-gateway:8081"
    assert provider["network_config"]["allow_private_network"] is True  # fixed relay on its isolated Compose network
    assert provider["network_config"]["max_retries"] == 0


def test_no_content_stores_raw_payloads_or_external_connectors(tmp_path):
    result, app_dir = render(tmp_path)
    assert result.returncode == 0
    config = json.loads((app_dir / "config.json").read_text())
    # Actual pinned Bifrost refused file-only auth: governance needs a config store. Its SQLite database is ephemeral tmpfs metadata,
    # separate from the domain PostgreSQL database. No content log store is enabled.
    assert config["config_store"] == {"enabled": True, "type": "sqlite", "config": {"path": "/app/data/config.db"}}
    assert config["logs_store"] == {"enabled": False}
    assert config["plugins"] == []
    client = config["client"]
    assert client["enable_logging"] is False and client["disable_content_logging"] is True
    assert client["retain_content_in_object_storage"] is False
    assert client["allow_per_request_content_storage_override"] is False and client["logging_headers"] == []
    assert config["governance"]["virtual_keys"][0]["disable_content_logging"] is True
    provider = config["providers"]["deepseek"]
    assert all(provider[key] is False for key in ("send_back_raw_request", "send_back_raw_response", "store_raw_request_response"))
    assert "mcp" not in config and "vector_store" not in config


def test_catalog_bootstrap_uses_only_local_sources_and_no_background_provider_discovery(tmp_path):
    result, app_dir = render(tmp_path)
    assert result.returncode == 0
    config = json.loads((app_dir / "config.json").read_text())
    pricing = config["framework"]["pricing"]
    assert pricing["live_models_sync_interval"] == pricing["mcp_library_sync_interval"] == 0
    assert pricing["pricing_sync_interval"] >= 3600
    for field, filename in (("pricing_url", "pricing.json"), ("model_parameters_url", "model-parameters.json"),
                            ("mcp_library_url", "mcp-library.json")):
        assert pricing[field] == "file:///etc/bifrost/" + filename
        json.loads((ROOT / "llm_poc" / filename).read_text())
    assert json.loads((ROOT / "llm_poc" / "mcp-library.json").read_text()) == {"servers": []}


def test_local_price_table_is_conservative_peak_metadata_and_never_asserts_a_model_pin():
    # Official DeepSeek pricing, checked 2026-11-17: peak cache-miss input $0.30/M, output $1.20/M.
    # https://api-docs.deepseek.com/quick_start/pricing/ . This operator snapshot deliberately does not discount off-peak/cache hits;
    # it is metadata for the candidate PoC, not a bill or the relay's durable budget authority.
    prices = json.loads((ROOT / "llm_poc" / "pricing.json").read_text(), parse_float=Decimal)
    assert set(prices) == {"deepseek/deepseek-flash"}
    flash = prices["deepseek/deepseek-flash"]
    assert flash["input_cost_per_token"] * 1_000_000 == Decimal("0.30")
    assert flash["output_cost_per_token"] * 1_000_000 == Decimal("1.20")
    assert flash["provider"] == "deepseek" and flash["mode"] == "chat"
    capabilities = json.loads((ROOT / "llm_poc" / "model-parameters.json").read_text())
    assert set(capabilities) == {"deepseek/deepseek-flash"}
    assert capabilities["deepseek/deepseek-flash"]["supports_response_schema"] is False  # JSON mode != native JSON Schema enforcement
    assert "server_side_model" not in capabilities["deepseek/deepseek-flash"]  # no inference of actual immutable identity from alias


@pytest.mark.parametrize("name", SYNTHETIC)
@pytest.mark.parametrize("bad", ["", "a" * 63, "a" * 65, "A" * 64, "g" * 64, '"' * 64, "a" * 64 + "\nextra", "a" * 64 + "\n\n"])
def test_bad_credentials_refuse_before_creating_config(tmp_path, name, bad):
    result, app_dir = render(tmp_path, values={**SYNTHETIC, name: bad})
    assert result.returncode != 0
    assert not list(app_dir.iterdir())


@pytest.mark.parametrize("name", SYNTHETIC)
def test_missing_secret_refuses_without_fallback(tmp_path, name):
    result, app_dir = render(tmp_path, values={k: v for k, v in SYNTHETIC.items() if k != name})
    assert result.returncode != 0 and not list(app_dir.iterdir())


def test_one_trailing_newline_is_accepted_and_rerender_replaces_insecure_existing_file(tmp_path):
    result, app_dir = render(tmp_path, values={k: v + "\n" for k, v in SYNTHETIC.items()})
    assert result.returncode == 0
    output = app_dir / "config.json"
    output.chmod(0o644)
    result, _ = render(tmp_path)
    assert result.returncode == 0 and stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(app_dir.glob("config.json.tmp.*"))


@pytest.mark.parametrize("replacement", ["$UNKNOWN", "$BIFROST_ADMIN_PASSWORD $BIFROST_ADMIN_PASSWORD", "removed"])
def test_unknown_duplicate_or_missing_template_placeholder_leaves_no_partial_config(tmp_path, replacement):
    template = tmp_path / "bad-template.json"
    template.write_text(TEMPLATE.read_text().replace("$BIFROST_ADMIN_PASSWORD", replacement))
    result, app_dir = render(tmp_path, template=template)
    assert result.returncode != 0 and not list(app_dir.iterdir())


def test_unknown_option_refuses_without_reading_or_output(tmp_path):
    result = subprocess.run(["/bin/sh", str(START), "--unknown"], capture_output=True, text=True, check=False)
    assert result.returncode != 0 and result.stdout == "" and not list(tmp_path.iterdir())


def test_rendered_credentials_are_not_exported_or_passed_to_external_commands(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    evidence = tmp_path / "command-evidence.json"
    # Intercept the real renderer's atomic publish step. Store booleans only, never a copy of the inherited environment.
    move = commands / "mv"
    move.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"secrets = {list(SYNTHETIC.values())!r}\n"
        "names = ['loaded_secret', 'admin_password', 'virtual_key', 'relay_auth', 'trailing']\n"
        "clean_env = not any(name in os.environ for name in names)\n"
        "clean_env = clean_env and not any(secret in value for secret in secrets for value in os.environ.values())\n"
        "clean_args = not any(secret in value for secret in secrets for value in sys.argv)\n"
        f"Path({str(evidence)!r}).write_text(json.dumps([clean_env, clean_args]))\n"
        "assert sys.argv[1] == '-f'\n"
        "os.replace(sys.argv[2], sys.argv[3])\n"
    )
    move.chmod(0o700)
    result, app_dir = render(tmp_path, extra_env={"PATH": str(commands) + os.pathsep + os.environ.get("PATH", "")})
    assert result.returncode == 0 and (app_dir / "config.json").is_file()
    assert json.loads(evidence.read_text()) == [True, True]
