#!/usr/bin/env python3
"""No-paid S16 runtime checks. Local candidate only; never enables the relay or calls an external model.

Credentials go to the in-container probe over stdin, never argv/env/output. Only check names and booleans leave it.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", "infra/compose.yaml", "-f", "infra/compose.dev.yaml", "-f", "infra/compose.llm-poc.yaml", "--profile", "llm-poc"]
PROBE = r'''
import base64, json, sys, urllib.error, urllib.request
values = json.load(sys.stdin)
checks = {}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# This check must precede every model-shaped request, including anonymous/wrong-key probes.
with opener.open("http://127.0.0.1:8081/health", timeout=3) as r:
    disabled = r.status == 200 and json.load(r) == {"status": "disabled"}
if not disabled:
    print(json.dumps({"relay_disabled": False}))
    sys.exit(2)
checks["relay_disabled"] = True
def request(path, headers=None, model=None):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "S16_NO_PAID_CONTENT_CANARY"}],
                       "max_completion_tokens": 16}).encode() if model else None
    req = urllib.request.Request("http://bifrost-poc:8080" + path, data=body,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.read(65536).decode(errors="replace")
    except urllib.error.HTTPError as r:
        return r.code, r.read(65536).decode(errors="replace")
vk = {"x-bf-vk": "sk-bf-" + values["bifrost_virtual_key"]}
admin = {"Authorization": "Basic " + base64.b64encode(("ai-res-poc:" + values["bifrost_admin_password"]).encode()).decode()}
checks["bifrost_health"] = request("/health")[0] == 200
checks["anonymous_inference_denied"] = request("/v1/chat/completions", model="deepseek/deepseek-flash")[0] in (401, 403)
checks["wrong_virtual_key_denied"] = request("/v1/chat/completions", {"x-bf-vk": "sk-bf-invalid"}, "deepseek/deepseek-flash")[0] in (401, 403)
status, data = request("/v1/chat/completions", vk, "deepseek/deepseek-flash")
checks["scoped_key_reaches_disabled_relay"] = status >= 500 and "PROVIDER_CALLS_DISABLED" in data
checks["candidate_pro_denied"] = request("/v1/chat/completions", vk, "deepseek/deepseek-v4-pro")[0] in (400, 401, 403)
checks["anonymous_management_denied"] = request("/api/providers")[0] in (401, 403)
checks["inference_key_cannot_manage"] = request("/api/providers", vk)[0] in (401, 403)
checks["admin_positive_control"] = request("/api/providers", admin)[0] == 200
print(json.dumps(checks))
'''


def run(args: list[str], *, data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, input=data, capture_output=True, text=True, timeout=150, check=False)  # noqa: S603


def disabled_relay_configuration(model: dict) -> bool:
    config = model.get("Config") or {}
    return (config.get("Cmd") == ["python", "/poc/relay.py"]
            and not any(str(v).startswith("AI_RES_DEEPSEEK_API_KEY_FILE=") for v in config.get("Env") or [])
            and {m.get("Destination") for m in model.get("Mounts") or [] if str(m.get("Destination", "")).startswith("/run/secrets/")}
            == {"/run/secrets/llm_relay_auth"})


def main() -> int:
    relay_id = run([*COMPOSE, "ps", "-q", "llm-gateway"]).stdout.strip()
    inspected = run(["docker", "inspect", relay_id]) if relay_id else None
    if inspected is None or inspected.returncode or not disabled_relay_configuration(json.loads(inspected.stdout)[0]):
        print("FAIL: refusing inference probes against an unexpected or potentially live relay configuration")
        return 1
    values = {name: (ROOT / "infra" / "secrets" / "runtime" / name).read_text().strip()
              for name in ("bifrost_virtual_key", "bifrost_admin_password", "llm_relay_auth")}
    result = run([*COMPOSE, "exec", "-T", "llm-gateway", "python", "-c", PROBE], data=json.dumps(values))
    if result.returncode:
        print("FAIL: in-container HTTP probe failed; raw output withheld")
        return 1
    try:
        checks = json.loads(result.stdout)
        if not isinstance(checks, dict) or len(checks) != 9 or any(type(v) is not bool for v in checks.values()):
            raise ValueError("invalid probe")
    except ValueError:
        print("FAIL: in-container HTTP probe returned an invalid summary")
        return 1

    positive = run([*COMPOSE, "exec", "-T", "bifrost-poc", "nc", "-z", "-w", "3", "llm-gateway", "8081"])
    negative = run([*COMPOSE, "exec", "-T", "bifrost-poc", "nc", "-z", "-w", "3", "1.1.1.1", "443"])
    checks["bifrost_reaches_relay_positive_control"] = positive.returncode == 0
    checks["bifrost_has_no_direct_external_route"] = negative.returncode != 0
    for name, expected in (("bifrost-poc", {"ai-res_llm_poc", "ai-res_llm_upstream"}), ("llm-gateway", {"ai-res_llm_upstream", "ai-res_egress"})):
        cid = run([*COMPOSE, "ps", "-q", name]).stdout.strip()
        if not cid:
            checks[name + "_running"] = False
            continue
        inspection = run(["docker", "inspect", cid])
        if inspection.returncode:
            checks[name + "_inspect"] = False
            continue
        inspected = json.loads(inspection.stdout)[0]
        checks[name + "_network_boundary"] = set(inspected["NetworkSettings"]["Networks"]) == expected
        checks[name + "_no_host_ports"] = not inspected["HostConfig"].get("PortBindings")
        environment = "\n".join(inspected["Config"].get("Env") or [])
        checks[name + "_secrets_outside_environment"] = all(value not in environment for value in values.values())
    logs = run([*COMPOSE, "logs", "--no-color", "bifrost-poc", "llm-gateway"])
    checks["logs_available"] = logs.returncode == 0
    checks["no_credentials_or_content_in_logs"] = all(value not in logs.stdout for value in [*values.values(), "S16_NO_PAID_CONTENT_CANARY"])
    for name, passed in sorted(checks.items()):
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    failed = sum(not passed for passed in checks.values())
    print(f"{len(checks) - failed} passed, {failed} failed; no external model request executed")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
