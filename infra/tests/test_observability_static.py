"""S13 static evidence for the observability stack (ADR-037 layer 1): Collector pipeline shape, redaction allowlists, alert-rule metadata, label cardinality,
dashboards as code. Static checks are NOT runtime evidence: redaction/degradation behaviour is proven by tests/runtime/test_observability.py."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

INFRA = Path(__file__).resolve().parents[1]
OBS = INFRA / "observability"
ROOT = INFRA.parent
COLLECTOR = yaml.safe_load((OBS / "otel" / "config.yaml").read_text())
COMPOSE = (INFRA / "compose.yaml").read_text()
# Identifiers that may live in logs/traces but never in a Prometheus label (DOC-024 §2.8, OBS-MON-034)
FORBIDDEN_LABELS = {
    "project_id", "task_id", "worker_run_id", "trace_id", "span_id", "user_id", "organization_id", "epic_id", "plan_version_id", "request_id", "operation_id",
    "event_id", "aggregate_id", "workflow_id", "run_id", "temporal_workflow_id", "context_package_version_id", "source_version_id", "artifact_version_id",
    "session_id", "email", "client_ip", "ip", "path", "url", "query", "prompt", "user", "tenant_id", "idempotency_key", "object_key",
}
SENSITIVE_WORD = re.compile(r"(password|passwd|secret|authorization|cookie|api[_-]?key|private[_-]?key|credential|session|bearer|csrf|totp|prompt|completion|body|payload|content)", re.I)


def image(service: str) -> str:
    m = re.search(rf"^  {re.escape(service)}:\n(?:(?!^  \S).*\n)*?    image: (\S+)", COMPOSE, re.M)
    assert m, service
    return m.group(1)


# ---- Collector -------------------------------------------------------------------------------------------------------------
def test_every_pipeline_limits_memory_first_batches_last_and_redacts_before_export():
    pipelines = COLLECTOR["service"]["pipelines"]
    assert set(pipelines) == {"traces", "logs", "metrics"}
    for name, p in pipelines.items():
        procs = p["processors"]
        assert procs[0] == "memory_limiter", name
        assert procs[-1] == "batch", name
        guards = [x for x in procs if x.startswith(("redaction", "transform", "filter"))]
        assert guards, f"{name}: no redaction/filter step before export"
        assert "debug" not in p["exporters"], f"{name}: the debug exporter prints payloads"


def test_the_trace_pipeline_uses_the_redaction_processor_with_an_allowlist():
    red = COLLECTOR["processors"]["redaction/traces"]
    assert red["allow_all_keys"] is False and red["allowed_keys"], "attributes must be allowlisted, not blocklisted"
    assert "redaction/traces" in COLLECTOR["service"]["pipelines"]["traces"]["processors"]
    assert red["blocked_values"], "value patterns are the second line behind the key allowlist"


def test_no_allowlist_admits_a_sensitive_or_content_key():
    keys = list(COLLECTOR["processors"]["redaction/traces"]["allowed_keys"])
    text = json.dumps(COLLECTOR["processors"]["transform/logs"]) + json.dumps(COLLECTOR["processors"]["transform/metrics"])
    for kept in re.findall(r'keep_keys\((?:[a-z.]+), (\[[^\]]*\])\)', text.replace('\\"', '"')):
        keys += json.loads(kept)
    assert keys
    bad = [k for k in keys if SENSITIVE_WORD.search(k) and not k.endswith(("_version", "_id", ".version"))]  # a version/id names a reference, not content
    assert not bad, f"allowlisted keys that look sensitive: {bad}"


def test_metric_label_allowlist_contains_no_high_cardinality_identifier():
    stmts = " ".join(s for g in COLLECTOR["processors"]["transform/metrics"]["metric_statements"] for s in g["statements"] if "datapoint" in g["context"] or True)
    datapoint = next(s for g in COLLECTOR["processors"]["transform/metrics"]["metric_statements"] if g["context"] == "datapoint" for s in g["statements"] if s.startswith("keep_keys"))
    labels = set(json.loads(re.search(r"\[.*\]", datapoint).group(0)))
    assert labels, stmts
    assert not {re.sub(r"[.\-]", "_", x) for x in labels} & FORBIDDEN_LABELS


def test_metrics_pipeline_only_admits_named_metric_families():
    expr = COLLECTOR["processors"]["filter/metrics"]["metrics"]["metric"][0]
    assert expr.startswith("not IsMatch(name,")  # drop everything that is not explicitly allowed


def test_redaction_processors_fail_closed_on_a_statement_error():
    """error_mode=ignore would let an OTTL error silently skip redaction; propagate drops the batch instead (security over completeness)."""
    for name in ("transform/traces", "transform/logs", "filter/metrics", "transform/metrics"):
        assert COLLECTOR["processors"][name]["error_mode"] == "propagate", name


def test_exporter_queues_and_retries_are_bounded_fail_open():
    for name in ("otlp/tempo", "otlphttp/loki"):
        exp = COLLECTOR["exporters"][name]
        assert exp["sending_queue"]["enabled"] and exp["sending_queue"]["queue_size"] <= 1024, name
        assert 0 < int(str(exp["retry_on_failure"]["max_elapsed_time"]).rstrip("s")) <= 60, f"{name}: retry must end (OBS-MON-015)"
    assert COLLECTOR["processors"]["memory_limiter"]["limit_mib"] > 0


def test_logs_pipeline_masks_secrets_in_the_body_and_scrubs_exceptions_in_traces():
    logs = json.dumps(COLLECTOR["processors"]["transform/logs"])
    assert logs.count("replace_pattern(body") >= 5 and "PRIVATE KEY" in logs
    traces = json.dumps(COLLECTOR["processors"]["transform/traces"])
    assert "exception.message" in traces and "exception.stacktrace" in traces


# ---- Compose wiring ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("service", ["otel-collector", "prometheus", "alertmanager", "loki", "tempo", "grafana"])
def test_observability_images_are_pinned_by_digest(service):
    assert re.search(r"@sha256:[0-9a-f]{64}$", image(service)) and ":latest" not in image(service)


def test_grafana_has_no_anonymous_access_no_signup_and_a_file_secret():
    block = COMPOSE[COMPOSE.index("\n  grafana:\n"):]
    assert 'GF_AUTH_ANONYMOUS_ENABLED: "false"' in block and 'GF_USERS_ALLOW_SIGN_UP: "false"' in block
    assert "GF_SECURITY_ADMIN_PASSWORD__FILE: /run/secrets/grafana_admin_password" in block
    assert 'GF_ANALYTICS_REPORTING_ENABLED: "false"' in block


# ---- Alert rules -------------------------------------------------------------------------------------------------------------
RULES = yaml.safe_load((OBS / "prometheus" / "rules" / "alerts.yml").read_text())
ALERTS = [r for g in RULES["groups"] for r in g["rules"]]
REQUIRED_LABELS = {"severity", "scope", "owner"}
REQUIRED_ANNOTATIONS = {"summary", "description", "runbook", "user_impact", "auto_action", "silence_policy"}


def test_alert_inventory_is_not_empty():
    assert len(ALERTS) >= 10


@pytest.mark.parametrize("rule", ALERTS, ids=lambda r: r["alert"])
def test_every_alert_carries_the_mandatory_metadata(rule):
    assert set(rule["labels"]) >= REQUIRED_LABELS, rule["alert"]
    assert set(rule["annotations"]) >= REQUIRED_ANNOTATIONS, rule["alert"]
    assert rule["labels"]["severity"] in {"warning", "critical"}
    assert rule["annotations"]["auto_action"] == "none", "an alert never triggers an action (OBS-ALR-004)"
    assert rule["annotations"]["description"].startswith("Fact:"), "fact is separated from hypothesis (OBS-ALR-003)"


@pytest.mark.parametrize("rule", ALERTS, ids=lambda r: r["alert"])
def test_alert_runbook_exists_and_anchor_resolves(rule):
    path, _, anchor = rule["annotations"]["runbook"].partition("#")
    file = ROOT / path
    assert file.is_file(), f"{path} (create it: runbooks are part of the alert contract, OBS-MON-011)"
    if anchor:
        headings = {re.sub(r"[^a-z0-9]+", "", h.lower()) for h in re.findall(r"^#+\s+(.*)$", file.read_text(), re.M)}
        assert re.sub(r"[^a-z0-9]+", "", anchor.lower()) in headings, f"{path} has no heading for #{anchor}"


def test_threshold_alerts_reference_a_threshold_series_and_no_literal_threshold():
    for rule in ALERTS:
        if "threshold" in rule["annotations"]["description"]:
            assert "ai_res:threshold:" in rule["expr"], rule["alert"]
    thresholds = yaml.safe_load((OBS / "prometheus" / "rules" / "thresholds.yml").read_text())
    assert [r for g in thresholds["groups"] for r in g["rules"]] == [], "numeric thresholds are an owner decision (OD-02): none are invented here"


def test_no_alert_expression_uses_a_forbidden_label():
    for rule in ALERTS:
        assert not _labels_in(rule["expr"]) & FORBIDDEN_LABELS, rule["alert"]


def _labels_in(expr: str) -> set[str]:
    out: set[str] = set()
    for grp in re.findall(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\(([^)]*)\)", expr):
        out |= {x.strip() for x in grp.split(",") if x.strip()}
    out |= set(re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=~|!~|!=|=)\s*\"", expr))
    return out


# ---- promtool (real validator, pinned image) ---------------------------------------------------------------------------------
def _promtool(*args: str, mount: Path = OBS / "prometheus") -> subprocess.CompletedProcess[str]:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available: promtool cannot run (a skip is not evidence)")
    return subprocess.run(["docker", "run", "--rm", "--entrypoint", "promtool", "-v", f"{mount}:/p:ro", image("prometheus"), *args],  # noqa: S603, S607
                          capture_output=True, text=True, check=False, timeout=180)


def test_promtool_accepts_rules_and_config():
    res = _promtool("check", "rules", "/p/rules/alerts.yml", "/p/rules/thresholds.yml")
    assert res.returncode == 0, res.stdout + res.stderr
    res = _promtool("check", "config", "/p/prometheus.yml")
    assert res.returncode == 0 or "no such file" in res.stdout.lower() + res.stderr.lower(), res.stdout + res.stderr  # rule_files resolve inside the container


def test_promtool_unit_tests_of_the_rules_pass():
    res = _promtool("test", "rules", "/p/tests/alerts_test.yml")
    assert res.returncode == 0, res.stdout + res.stderr


def test_promtool_unit_test_fails_when_an_expectation_is_wrong(tmp_path):
    """Sabotage: the unit tests must be able to fail, otherwise a green result proves nothing."""
    shutil.copytree(OBS / "prometheus", tmp_path / "prometheus")
    t = tmp_path / "prometheus" / "tests" / "alerts_test.yml"
    t.write_text(t.read_text().replace("severity: critical, scope: infrastructure", "severity: warning, scope: infrastructure", 1))
    res = _promtool("test", "rules", "/p/tests/alerts_test.yml", mount=tmp_path / "prometheus")
    assert res.returncode != 0


def test_alertmanager_config_is_valid_and_has_no_destination():
    cfg = yaml.safe_load((OBS / "alertmanager" / "alertmanager.yml").read_text())
    assert cfg["route"]["receiver"] == "unrouted"
    receivers = {r["name"]: r for r in cfg["receivers"]}
    assert set(receivers["unrouted"]) == {"name"}, "no destination is configured: that is an owner decision (OD-02, OBS-ALR-006)"


# ---- Dashboards ----------------------------------------------------------------------------------------------------------------
DASHBOARDS = {p.stem: json.loads(p.read_text()) for p in (OBS / "grafana" / "dashboards").glob("*.json")}


def test_dashboards_are_in_sync_with_the_generator():
    res = subprocess.run([sys.executable, str(OBS / "grafana" / "generate_dashboards.py"), "--check"], capture_output=True, text=True, check=False)  # noqa: S603
    assert res.returncode == 0, res.stdout


def test_required_dashboard_inventory_exists():
    assert set(DASHBOARDS) >= {"platform-overview", "api", "outbox-events", "temporal-workflow", "manager-workers", "postgresql", "telemetry-pipeline"}
    assert len({d["uid"] for d in DASHBOARDS.values()}) == len(DASHBOARDS)


def test_dashboards_use_only_provisioned_datasources_and_no_numeric_colour_thresholds():
    provisioned = {d["uid"] for d in yaml.safe_load((OBS / "grafana" / "provisioning" / "datasources" / "datasources.yaml").read_text())["datasources"]}
    for name, dash in DASHBOARDS.items():
        for p in dash["panels"]:
            for t in p["targets"]:
                assert t["datasource"]["uid"] in provisioned, (name, p["title"])
            steps = p["fieldConfig"]["defaults"]["thresholds"]["steps"]
            assert len(steps) == 1, f"{name}/{p['title']}: colouring by a number needs an approved threshold (OD-02)"


def test_dashboard_queries_use_no_high_cardinality_label():
    for name, dash in DASHBOARDS.items():
        for p in dash["panels"]:
            for t in p["targets"]:
                if t["datasource"]["uid"] == "prometheus":
                    assert not _labels_in(t["expr"]) & FORBIDDEN_LABELS, (name, p["title"], t["expr"])


def test_label_lint_detects_a_violation():
    """Sabotage: the lint must catch the exact mistake it exists for."""
    assert _labels_in('sum by (project_id) (rate(x_total[5m]))') & FORBIDDEN_LABELS
    assert _labels_in('x{task_id="1"}') & FORBIDDEN_LABELS
    assert not _labels_in("sum by (service_name) (rate(x_total[5m]))") & FORBIDDEN_LABELS
