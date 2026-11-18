"""Synthetic-only native Bifrost audit helper; never mount real credentials here.

The HTTP server has no provider client. All inference attempts stop at a fixed
503. Only named booleans/counts leave the probe; admin/provider/VK replies stay
in memory because even redacted upstream APIs may carry credentials.
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE = "http://bifrost-poc:8080"
CANARY = "ISOLATED_BIFROST_AUDIT_SYNTHETIC_CONTENT"
COUNT = 0
LIMIT = 1_048_576


class DisabledProvider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        raw = json.dumps({"count": COUNT}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        global COUNT
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= LIMIT:
            self.send_error(400)
            return
        self.rfile.read(size)
        COUNT += 1
        raw = b'{"error":{"message":"AUDIT_PROVIDER_DISABLED","type":"audit_disabled"}}'
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def probe(action):
    secrets = json.loads(Path("/fixture/credentials.json").read_bytes())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    admin = {"Authorization": "Basic " + base64.b64encode(("ai-res-poc:" + secrets["bifrost_admin_password"]).encode()).decode()}
    vk = {"x-bf-vk": "sk-bf-" + secrets["bifrost_virtual_key"]}

    def request(path, headers=None, body=None, method=None):
        raw = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=raw, method=method,  # noqa: S310 - fixed local audit origin and closed callers
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read(LIMIT + 1)
            if len(content) > LIMIT:
                raise ValueError()
            return response.code, content

    def get(path):
        status, raw = request(path, admin)
        if status != 200:
            raise ValueError()
        return json.loads(raw)

    def count():
        with opener.open("http://127.0.0.1:8081/health", timeout=2) as response:
            return json.load(response)["count"]

    checks = {}
    if action == "effective":
        live, db = get("/api/config"), get("/api/config?from_db=true")
        expected = {"enable_logging": False, "disable_content_logging": True, "retain_content_in_object_storage": False,
                    "allow_per_request_content_storage_override": False, "allow_direct_keys": False,
                    "enforce_auth_on_inference": True, "drop_excess_requests": True, "max_request_body_size_mb": 1}
        for name, data in (("live", live), ("db", db)):
            for key, value in expected.items():
                actual = data["client_config"].get(key)
                checks[name + "_client_" + key] = key in data["client_config"] and actual == value
            # Upstream omits zero-valued slices. This check rules out an exposed
            # nonempty override; it does NOT prove hidden state is empty. Exact
            # bootstrap file bytes are checked separately inside the container.
            checks[name + "_zero_lists_empty_or_omitted"] = all(data["client_config"].get(key) in (None, []) for key in
                ("logging_headers", "whitelisted_routes", "allowed_origins"))
            checks[name + "_auth_enabled"] = data["auth_config"]["is_enabled"] is True
            checks[name + "_sqlite_connected"] = data["is_db_connected"] is True
            checks[name + "_logs_disconnected"] = data["is_logs_connected"] is False
            checks[name + "_cache_disconnected"] = data["is_cache_connected"] is False
            checks[name + "_object_storage_disconnected"] = data["is_object_storage_connected"] is False
            pricing = data["framework_config"]
            checks[name + "_local_catalogues"] = all(pricing[key] == "file:///etc/bifrost/" + filename for key, filename in
                (("pricing_url", "pricing.json"), ("model_parameters_url", "model-parameters.json"), ("mcp_library_url", "mcp-library.json")))
        providers = get("/api/providers")
        provider = get("/api/providers/deepseek")
        keys = get("/api/governance/virtual-keys")
        # Shapes/selected fields are verified against the actual pinned server,
        # not a mock response. Unknown shape fails without exporting the body.
        checks["only_deepseek"] = len(providers["providers"]) == 1 and providers["providers"][0]["name"] == "deepseek"
        actual = provider
        checks["fixed_relay_no_retries"] = (actual["network_config"]["base_url"] == "http://llm-gateway:8081"
            and actual["network_config"]["max_retries"] == 0 and actual["network_config"]["default_request_timeout_in_seconds"] == 30)
        checks["no_provider_raw_capture"] = all(actual[name] is False for name in
            ("send_back_raw_request", "send_back_raw_response", "store_raw_request_response"))
        actual_keys = keys["virtual_keys"]
        checks["one_active_scoped_virtual_key"] = (len(actual_keys) == 1 and actual_keys[0]["is_active"] is True
            and actual_keys[0]["allow_all_providers"] is False and actual_keys[0]["disable_content_logging"] is True
            and len(actual_keys[0]["provider_configs"]) == 1
            and actual_keys[0]["provider_configs"][0]["provider"] == "deepseek"
            and actual_keys[0]["provider_configs"][0]["allowed_models"] == ["deepseek-flash"])
    elif action == "auth":
        body = {"model": "deepseek/deepseek-flash", "messages": [{"role": "user", "content": CANARY}], "max_tokens": 16}
        before = count()
        for name, headers in (("anonymous", {}), ("wrong_vk", {"x-bf-vk": "sk-bf-invalid"}),
                               ("direct_key", {"Authorization": "Bearer synthetic-no-provider", "x-bf-direct-key": "true"})):
            checks[name + "_inference_denied"] = request("/v1/chat/completions", headers, body)[0] in {401, 403}
        for name, headers in (("anonymous", {}), ("virtual_key", vk)):
            checks[name + "_admin_denied"] = request("/api/config", headers)[0] in {401, 403}
        checks["denied_requests_never_reach_relay"] = count() == before
        pro = {**body, "model": "deepseek/deepseek-v4-pro"}
        checks["unapproved_model_denied"] = request("/v1/chat/completions", vk, pro)[0] in {400, 401, 403}
        checks["unapproved_model_never_reaches_relay"] = count() == before
        status, raw = request("/v1/chat/completions", vk, body)
        checks["positive_virtual_key_reaches_disabled_relay_once"] = status >= 500 and b"AUDIT_PROVIDER_DISABLED" in raw and count() == before + 1
        checks["admin_positive_control"] = request("/api/config", admin)[0] == 200
    elif action in {"mutate", "restore"}:
        original = get("/api/config")
        desired = action == "restore"
        # Upstream PUT requires positive log_retention_days even with logging
        # disabled and bootstrap's dormant default=0. Set 1 only in this
        # disposable fixture; logging stays disabled. Restore only backpressure,
        # then fixture teardown discards all SQLite state (no product retention).
        # Omit framework: PUT refuses file-bootstrap's mcp sync=0.
        client_config = {**original["client_config"], "drop_excess_requests": desired,
                         "log_retention_days": max(1, original["client_config"]["log_retention_days"])}
        status, error_body = request("/api/config", admin, {"client_config": client_config}, "PUT")
        if status != 200:
            # Closed diagnostic vocabulary only; never emit an upstream error.
            categories = {"retention": b"log_retention_days", "placement": b"extra_fields_placement",
                          "mcp": b"mcp_", "client_reload": b"reload client config", "store": b"save configuration",
                          "header_reload": b"reload header filter", "compat": b"compat plugin", "auth": b"unauthorized"}
            for name, marker in categories.items():
                checks["mutation_error_" + name] = marker not in error_body.lower()
        checks["admin_mutation_accepted"] = status == 200
        after = get("/api/config")
        checks["live_mutation_visible"] = after["client_config"]["drop_excess_requests"] is desired
        checks["sqlite_mutation_visible"] = get("/api/config?from_db=true")["client_config"]["drop_excess_requests"] is desired
        safety = ("enable_logging", "disable_content_logging", "allow_direct_keys", "enforce_auth_on_inference",
                  "retain_content_in_object_storage", "allow_per_request_content_storage_override")
        checks["selected_security_fields_preserved"] = all(original["client_config"][key] == after["client_config"][key] for key in safety)
        checks["framework_preserved"] = original["framework_config"] == after["framework_config"]
    else:
        raise ValueError()
    if not checks or any(type(value) is not bool for value in checks.values()):
        raise ValueError()
    # A fixed boolean-only schema prevents accidental upstream body export.
    print(json.dumps(checks, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        HTTPServer(("0.0.0.0", 8081), DisabledProvider).serve_forever()  # noqa: S104 - disposable internal network only
    else:
        try:
            probe(sys.argv[1])
        except Exception:
            print('{"audit_probe_failed":true}')
            sys.exit(2)
