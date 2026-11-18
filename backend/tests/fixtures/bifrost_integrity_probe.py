"""Container-only probes for the hardened candidate. Never export raw replies."""
import base64
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def probe(action):
    values = json.loads(Path("/fixture/credentials.json").read_bytes())
    admin = {"Authorization": "Basic " + base64.b64encode(("ai-res-poc:" + values["bifrost_admin_password"]).encode()).decode()}
    virtual = {"x-bf-vk": "sk-bf-" + values["bifrost_virtual_key"]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, method="GET", headers=None, body=None):
        req = urllib.request.Request("http://bifrost-poc:8080" + path, method=method,  # noqa: S310 - fixed internal fixture origin
            data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError()
            return response.code
    if action == "health":
        result = {"status": request("/health")}
    elif action == "routes":
        result = {}
        paths = [("/api/config", "GET"), ("/api/config", "PUT"), ("/api/providers", "GET"), ("/api/providers/deepseek", "DELETE"),
                 ("/api/governance/virtual-keys", "POST"), ("/", "GET"), ("/metrics", "GET"), ("/v1/models", "GET"),
                 ("/openai/v1/chat/completions", "POST"), ("/health?x=1", "GET"), ("/health/", "GET"), ("/%68ealth", "GET"),
                 ("/api/../health", "GET"), ("/health", "OPTIONS"), ("/health", "HEAD")]
        for index, (path, method) in enumerate(paths):
            for label, headers in (("anonymous", {}), ("admin", admin), ("virtual", virtual)):
                result[str(index) + "_" + label] = request(path, method, headers, {"client_config": {"drop_excess_requests": False}}
                                                         if method in {"PUT", "POST"} else None) == 403
    elif action == "auth":
        body = {"model": "deepseek/deepseek-flash", "messages": [{"role": "user", "content": "synthetic-auth-probe"}], "max_tokens": 16}
        result = {}
        for label, headers in (("missing", {}), ("wrong", {"x-bf-vk": "sk-bf-invalid"}),
                               ("direct", {"Authorization": "Bearer synthetic-invalid", "x-bf-direct-key": "true"})):
            result[label] = request("/v1/chat/completions", "POST", headers, body) in {401, 403}
    else:
        raise ValueError()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--proxy":
            class HealthyProxy(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
            HTTPServer(("0.0.0.0", 8082), HealthyProxy).serve_forever()  # noqa: S104 - internal throwaway attack fixture
        else:
            probe(sys.argv[1])
    except Exception:
        print('{"probe_refused":true}')
        sys.exit(2)
