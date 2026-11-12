"""S13 runtime evidence on the live Compose stack (`make up`): redaction BEFORE the backends, label cardinality, access isolation, fail-open degradation.
Every negative check has a positive control (the carrier of a canary provably reached the backend), otherwise "nothing found" proves nothing.
A skipped run is NOT evidence (the stack fixture skips only locally; CI sets AI_RES_REQUIRE_STACK=1)."""
import base64
import json
import time
import urllib.parse
import uuid

import pytest

from tests.runtime.helpers import compose, container_id, exec_in, inspect, sh

OBS_SERVICES = ["otel-collector", "prometheus", "alertmanager", "loki", "tempo", "grafana"]
OBS_NETWORK = "ai-res_observability"
FORBIDDEN_LABELS = {"project_id", "task_id", "worker_run_id", "trace_id", "span_id", "user_id", "organization_id", "request_id", "operation_id", "session_id",
                    "event_id", "aggregate_id", "workflow_id", "password", "token", "authorization"}
SENDER = r'''
import json, sys, time, urllib.request
base, kind, payload = "http://otel-collector:4318", sys.argv[1], sys.argv[2]
req = urllib.request.Request(f"{base}/v1/{kind}", data=payload.encode(), headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(req, timeout=10).status)
'''


def send_otlp(kind: str, payload: dict) -> None:
    res = sh(["docker", "run", "--rm", "--network", OBS_NETWORK, "--read-only", "--cap-drop", "ALL", "--user", "10001:10001", "--entrypoint", "python",
              "ai-res/api:dev", "-c", SENDER, kind, json.dumps(payload)], timeout=120)
    assert res.returncode == 0 and res.stdout.strip() == "200", (res.stdout, res.stderr[-300:])


def attrs(**kv: str) -> list[dict]:
    return [{"key": k.replace("__", "."), "value": {"stringValue": v}} for k, v in kv.items()]


def get(service: str, url: str, header: str | None = None) -> str:
    cmd = ["wget", "-qO-", *([f"--header={header}"] if header else []), url]
    res = exec_in(service, *cmd)
    return res.stdout if res.returncode == 0 else ""


def poll(fn, timeout: float = 90, every: float = 3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        out = fn()
        if out:
            return out
        time.sleep(every)
    return None


@pytest.fixture(scope="module")
def canary() -> dict[str, str]:
    tag = uuid.uuid4().hex[:12]
    return {"tag": tag, "secret": f"S13SECRET{tag}", "jwt": f"eyJ{tag}abcdefgh.eyJ{tag}ijklmnop.sig{tag}", "dsn": f"postgresql://svc:S13PW{tag}@db.internal:5432/x",
            "prompt": f"S13PROMPT{tag} summarise the confidential contract", "service": f"canary-s13-{tag}", "trace": uuid.uuid4().hex, "span": uuid.uuid4().hex[:16]}


def test_redaction_keeps_canaries_out_of_loki(canary):
    now = str(time.time_ns())
    send_otlp("logs", {"resourceLogs": [{
        "resource": {"attributes": attrs(service__name=canary["service"], db__password=canary["secret"], deployment__environment__name="local")},
        "scopeLogs": [{"logRecords": [{
            "timeUnixNano": now, "severityText": "ERROR", "traceId": canary["trace"], "spanId": canary["span"],
            "body": {"stringValue": f"login failed password={canary['secret']} auth Bearer {canary['jwt']} dsn {canary['dsn']} marker={canary['tag']}"},
            "attributes": attrs(authorization=f"Bearer {canary['secret']}", session_token=canary["secret"], prompt=canary["prompt"], ai_res__request_id=f"req-{canary['tag']}",
                                note=f"see {canary['dsn']}"),
        }]}]}]})
    q = urllib.parse.quote(f'{{service_name="{canary["service"]}"}}')

    def fetch() -> str:
        start = str(int(time.time_ns() - 600 * 1e9))
        out = get("loki", f"http://127.0.0.1:3100/loki/api/v1/query_range?query={q}&limit=50&start={start}")
        return out if canary["tag"] in out else ""

    body = poll(fetch)
    assert body, "positive control: the record reached Loki (marker is not a secret)"
    for secret in (canary["secret"], canary["jwt"], canary["dsn"], canary["prompt"], f"S13PW{canary['tag']}"):
        assert secret not in body, f"canary leaked into Loki: {secret[:12]}…"
    assert "[REDACTED]" in body, "masked, not silently dropped"
    assert f"req-{canary['tag']}" in body, "allowlisted correlation attribute survives (the allowlist is not a blanket delete)"


def test_the_loki_detector_finds_a_canary_that_bypasses_the_collector(canary):
    """Sabotage/positive control for the redaction test above: the same kind of secret pushed straight into Loki IS found by the same query, so the
    redaction test cannot pass merely because the detector is blind."""
    stream = f"bypass-s13-{canary['tag']}"
    body = json.dumps({"streams": [{"stream": {"service_name": stream}, "values": [[str(time.time_ns()), f"password={canary['secret']} bypass"]]}]})
    res = exec_in("loki", "wget", "-qO-", "--header=Content-Type: application/json", f"--post-data={body}", "http://127.0.0.1:3100/loki/api/v1/push")
    assert res.returncode == 0, res.stderr
    q = urllib.parse.quote(f'{{service_name="{stream}"}}')
    found = poll(lambda: canary["secret"] in get("loki", f"http://127.0.0.1:3100/loki/api/v1/query_range?query={q}&limit=5&start={int(time.time_ns() - 600 * 1e9)}"))
    assert found, "the detector must see an unredacted secret"


def test_redaction_keeps_canaries_out_of_tempo(canary):
    now = time.time_ns()
    send_otlp("traces", {"resourceSpans": [{
        "resource": {"attributes": attrs(service__name=canary["service"], db__password=canary["secret"])},
        "scopeSpans": [{"spans": [{
            "traceId": canary["trace"], "spanId": canary["span"], "name": "s13.canary", "kind": 2, "startTimeUnixNano": str(now - 10_000_000), "endTimeUnixNano": str(now),
            "status": {"code": 2, "message": f"failed token={canary['secret']}"},
            "attributes": attrs(http__route="/api/v1/x", ai_res__request_id=f"req-{canary['tag']}", http__request__header__authorization=f"Bearer {canary['jwt']}",
                                ai_res__prompt=canary["prompt"], gen_ai__prompt=canary["prompt"], db__statement=f"select '{canary['secret']}'",
                                ai_res__tool_name=f"Bearer {canary['jwt']}"),
            "events": [{"name": "exception", "timeUnixNano": str(now), "attributes": attrs(
                exception__type="ValueError", exception__message=f"bad password={canary['secret']}", exception__stacktrace=f"File x.py line 1 {canary['dsn']}")}],
        }]}]}]})

    def fetch() -> str:
        out = get("tempo", f"http://127.0.0.1:3200/api/traces/{canary['trace']}")
        return out if "s13.canary" in out else ""

    body = poll(fetch)
    assert body, "positive control: the span reached Tempo"
    for secret in (canary["secret"], canary["jwt"], canary["dsn"], canary["prompt"], f"S13PW{canary['tag']}"):
        assert secret not in body, f"canary leaked into Tempo: {secret[:12]}…"
    assert f"req-{canary['tag']}" in body and "ValueError" in body, "allowlisted attributes and the exception TYPE survive"
    assert "exception.message" not in body and "exception.stacktrace" not in body


def test_high_cardinality_ids_never_become_prometheus_labels(canary):
    now = str(time.time_ns())
    point = {"asDouble": 1, "timeUnixNano": now, "attributes": attrs(outcome="ok", project_id=str(uuid.uuid4()), task_id=str(uuid.uuid4()), trace_id=canary["trace"],
                                                                      password=canary["secret"], worker_run_id=str(uuid.uuid4()))}
    send_otlp("metrics", {"resourceMetrics": [{
        "resource": {"attributes": attrs(service__name=canary["service"], deployment__environment__name="local")},
        "scopeMetrics": [{"metrics": [{"name": "ai_res.s13.canary", "gauge": {"dataPoints": [point]}}]}]}]})

    def series() -> list[dict]:
        out = get("prometheus", "http://127.0.0.1:9090/api/v1/series?match[]=" + urllib.parse.quote(f'ai_res_s13_canary{{service_name="{canary["service"]}"}}'))
        return json.loads(out)["data"] if out else []

    found = poll(series, timeout=120)
    assert found, "positive control: the metric reached Prometheus"
    labels = set().union(*(s.keys() for s in found))
    assert "outcome" in labels, "allowlisted label survives"
    assert not labels & FORBIDDEN_LABELS, f"high-cardinality/sensitive labels leaked: {labels & FORBIDDEN_LABELS}"


def test_every_prometheus_label_name_is_free_of_forbidden_identifiers():
    names = set(json.loads(get("prometheus", "http://127.0.0.1:9090/api/v1/labels"))["data"])
    assert {"job", "instance"} <= names, "positive control: labels were read"
    assert not names & FORBIDDEN_LABELS, names & FORBIDDEN_LABELS


def test_metric_names_outside_the_allowlist_are_dropped(canary):
    now = str(time.time_ns())
    send_otlp("metrics", {"resourceMetrics": [{
        "resource": {"attributes": attrs(service__name=canary["service"])},
        "scopeMetrics": [{"metrics": [{"name": f"unlisted.s13.{canary['tag']}", "gauge": {"dataPoints": [{"asDouble": 1, "timeUnixNano": now}]}},
                                      {"name": "ai_res.s13.control", "gauge": {"dataPoints": [{"asDouble": 1, "timeUnixNano": now}]}}]}]}]})
    assert poll(lambda: "ai_res_s13_control" in get("prometheus", "http://127.0.0.1:9090/api/v1/label/__name__/values"), timeout=120), "positive control"
    assert f"unlisted_s13_{canary['tag']}" not in get("prometheus", "http://127.0.0.1:9090/api/v1/label/__name__/values")


# ---- access isolation (OBS-SEC-005/009) -------------------------------------------------------------------------------------
@pytest.mark.parametrize("service", OBS_SERVICES)
def test_no_observability_service_publishes_a_host_port(service):
    assert not (inspect(service)["HostConfig"].get("PortBindings") or {}), service


def test_grafana_rejects_anonymous_and_serves_provisioned_dashboards(secret_values):
    assert get("grafana", "http://127.0.0.1:3000/api/search") == "", "anonymous access is refused"
    token = base64.b64encode(f"admin:{secret_values['grafana_admin_password']}".encode()).decode()
    found = json.loads(get("grafana", "http://127.0.0.1:3000/api/search?type=dash-db", f"Authorization: Basic {token}"))
    assert {d["uid"] for d in found} >= {"ai-res-platform", "ai-res-api", "ai-res-outbox", "ai-res-temporal", "ai-res-postgresql", "ai-res-telemetry"}
    sources = json.loads(get("grafana", "http://127.0.0.1:3000/api/datasources", f"Authorization: Basic {token}"))
    assert {s["uid"] for s in sources} >= {"prometheus", "loki", "tempo", "alertmanager"}


def test_default_grafana_credentials_do_not_work():
    token = base64.b64encode(b"admin:admin").decode()
    assert get("grafana", "http://127.0.0.1:3000/api/search", f"Authorization: Basic {token}") == ""


def test_dashboard_queries_are_valid_promql_against_the_live_prometheus():
    """Every Prometheus expression in every provisioned dashboard parses and executes (status=success); an empty result is fine, a syntax error is not."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "observability" / "grafana" / "dashboards"
    exprs = [t["expr"] for f in root.glob("*.json") for p in json.loads(f.read_text())["panels"] for t in p["targets"] if t["datasource"]["uid"] == "prometheus"]
    assert len(exprs) >= 25
    for expr in exprs:
        out = json.loads(get("prometheus", "http://127.0.0.1:9090/api/v1/query?query=" + urllib.parse.quote(expr)) or '{"status":"error"}')
        assert out["status"] == "success", expr


def test_alert_rules_are_loaded_and_healthy():
    groups = json.loads(get("prometheus", "http://127.0.0.1:9090/api/v1/rules"))["data"]["groups"]
    rules = [r for g in groups for r in g["rules"]]
    assert len(rules) >= 10 and all(r["health"] == "ok" for r in rules), [r["name"] for r in rules if r["health"] != "ok"]
    assert {"TargetDown", "OutboxQuarantined", "TelemetryExportFailing"} <= {r["name"] for r in rules}


# ---- degradation: telemetry loss must not break the domain (OBS-MON-014) -------------------------------------------------
def _api_probe() -> tuple[str, float]:
    start = time.monotonic()
    res = sh(["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", "https://localhost:8443/api/v1/projects"], timeout=30)
    return res.stdout.strip(), time.monotonic() - start


def test_stopping_every_telemetry_backend_does_not_break_the_api():
    before, _ = _api_probe()
    assert before == "401", "positive control: the API answers (authentication is required, not an error)"
    stopped = ["otel-collector", "loki", "tempo", "prometheus", "alertmanager", "grafana"]
    try:
        assert compose("stop", *stopped, timeout=180).returncode == 0
        for _ in range(15):
            code, took = _api_probe()
            assert code == "401" and took < 3, f"API degraded while telemetry is down: {code} in {took:.1f}s"
        for svc in ("api", "platform-api", "outbox-dispatcher", "manager-runtime", "worker-runtime"):
            st = inspect(svc)["State"]
            assert st["Status"] == "running" and st["Health"]["Status"] == "healthy", svc
    finally:
        compose("up", "-d", "--no-deps", *stopped, timeout=300)
    assert poll(lambda: all(inspect(s)["State"].get("Health", {}).get("Status") == "healthy" for s in stopped if s != "otel-collector")
                and inspect("otel-collector")["State"]["Status"] == "running", timeout=120), "the stack recovers"
    assert _api_probe()[0] == "401"


def test_telemetry_flows_again_after_the_backends_return():
    """Recovery evidence: traffic after the outage becomes visible in Tempo again (the pipeline is not wedged)."""
    for _ in range(5):
        _api_probe()
    assert poll(lambda: "ai-res-api" in get("tempo", "http://127.0.0.1:3200/api/search/tag/service.name/values"), timeout=120)
    assert container_id("otel-collector")
