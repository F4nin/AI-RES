#!/usr/bin/env python3
"""Generates the Grafana dashboards (dashboards as code, S13). Output is committed; `--check` fails when the committed JSON differs (used by the tests).

Rules baked in here: Prometheus panels use only low-cardinality labels (OBS-MON-034); no panel colours by a numeric threshold (thresholds are an owner decision,
OD-02); latency panels show percentile AND sample rate (OBS-MON-016/033); technical success is never presented as quality (OBS-MON-031).
Usage: generate_dashboards.py [--check]
"""
import argparse
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}


def target(expr: str, legend: str = "", ds: dict | None = None, ref: str = "A") -> dict:
    return {"datasource": ds or PROM, "expr": expr, "legendFormat": legend, "refId": ref}


def panel(pid: int, title: str, kind: str, x: int, y: int, w: int, h: int, targets: list[dict], *, unit: str = "short", description: str = "") -> dict:
    return {"id": pid, "title": title, "type": kind, "description": description, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": targets[0]["datasource"], "targets": targets,
            "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}} if kind == "timeseries" else {}}


def dashboard(uid: str, title: str, description: str, panels: list[dict], tags: list[str] | None = None) -> dict:
    return {"uid": uid, "title": title, "description": description, "tags": ["ai-res", *(tags or [])], "schemaVersion": 39, "version": 1, "editable": False,
            "timezone": "utc", "refresh": "30s", "time": {"from": "now-1h", "to": "now"}, "templating": {"list": []}, "annotations": {"list": []}, "panels": panels,
            "links": []}


def build() -> dict[str, dict]:
    d: dict[str, dict] = {}
    d["platform-overview"] = dashboard("ai-res-platform", "AI RES / Platform Overview", "Health of every scrape target and shared infrastructure (OBS-MON-001).", [
        panel(1, "Targets up", "stat", 0, 0, 6, 4, [target("sum(up)", "up")], description="Count of scrape targets answering."),
        panel(2, "Targets down", "stat", 6, 0, 6, 4, [target("count(up == 0) or vector(0)", "down")]),
        panel(3, "Target status by job", "timeseries", 0, 4, 24, 8, [target("min by (job) (up)", "{{job}}")], description="1 = answering, 0 = not answering."),
        panel(4, "MinIO usable free / total", "timeseries", 0, 12, 12, 8,
              [target("minio_cluster_capacity_usable_free_bytes", "free"), target("minio_cluster_capacity_usable_total_bytes", "total", ref="B")], unit="bytes"),
        panel(5, "Active alerts", "table", 12, 12, 12, 8, [target('sum by (alertname, severity, scope) (ALERTS{alertstate="firing"})', "", ref="A")]),
        panel(6, "Firing alerts (count)", "stat", 0, 20, 6, 4, [target('count(ALERTS{alertstate="firing"}) or vector(0)', "firing")]),
        panel(7, "Numeric alert thresholds configured", "stat", 6, 20, 6, 4, [target('count({__name__=~"ai_res:threshold:.*"}) or vector(0)', "configured")],
              description="0 = every threshold-based alert is INERT (thresholds are an owner decision, OD-02). A quiet alert board then does not mean healthy."),
    ], ["platform"])
    d["api"] = dashboard("ai-res-api", "AI RES / API", "Inbound HTTP RED metrics of the public and internal APIs (OBS-MON-004). Logs and traces link by trace_id.", [
        panel(1, "Request rate by service", "timeseries", 0, 0, 12, 8, [target("sum by (service_name) (rate(http_server_request_duration_seconds_count[5m]))", "{{service_name}}")], unit="reqps"),
        panel(2, "Responses by status class", "timeseries", 12, 0, 12, 8,
              [target("sum by (service_name, http_response_status_class) (rate(http_server_request_duration_seconds_count[5m]))", "{{service_name}} {{http_response_status_class}}")], unit="reqps"),
        panel(3, "Latency p50 / p95 / p99", "timeseries", 0, 8, 12, 8, [
            target("histogram_quantile(0.5, sum by (le, service_name) (rate(http_server_request_duration_seconds_bucket[5m])))", "p50 {{service_name}}"),
            target("histogram_quantile(0.95, sum by (le, service_name) (rate(http_server_request_duration_seconds_bucket[5m])))", "p95 {{service_name}}", ref="B"),
            target("histogram_quantile(0.99, sum by (le, service_name) (rate(http_server_request_duration_seconds_bucket[5m])))", "p99 {{service_name}}", ref="C")],
            unit="s", description="Read together with the request rate: a percentile of a few requests is not a measurement (OBS-MON-033)."),
        panel(4, "Slowest routes (p95)", "timeseries", 12, 8, 12, 8,
              [target("histogram_quantile(0.95, sum by (le, http_route) (rate(http_server_request_duration_seconds_bucket[5m])))", "{{http_route}}")], unit="s"),
        panel(5, "Recent API logs (redacted)", "logs", 0, 16, 24, 10,
              [target('{service_name=~"ai-res-api|ai-res-platform-api"}', "", LOKI)]),
        panel(6, "Recent traces", "table", 0, 26, 24, 8, [{"datasource": TEMPO, "queryType": "traceql", "query": '{ resource.service.name =~ "ai-res-.*" }', "refId": "A"}]),
    ], ["api"])
    d["outbox-events"] = dashboard("ai-res-outbox", "AI RES / Outbox and events", "Delivery state and outcomes of the Transactional Outbox / Inbox (Event Model v1.4 §16).", [
        panel(1, "Outbox backlog by status", "timeseries", 0, 0, 12, 8, [target("sum by (status) (ai_res_outbox_backlog)", "{{status}}")]),
        panel(2, "Oldest undelivered row age", "timeseries", 12, 0, 12, 8, [target("max(ai_res_outbox_oldest_undelivered_age_seconds)", "age")], unit="s"),
        panel(3, "Deliveries by outcome", "timeseries", 0, 8, 12, 8, [
            target("sum(rate(ai_res_events_published_total[5m]))", "published"),
            target("sum(rate(ai_res_events_retried_total[5m]))", "retried", ref="B"),
            target("sum(rate(ai_res_events_quarantined_total[5m]))", "quarantined", ref="C"),
            target("sum(rate(ai_res_events_lease_lost_total[5m]))", "lease lost", ref="D")], unit="ops"),
        panel(4, "Inbox backlog by status", "timeseries", 12, 8, 12, 8, [target("sum by (status) (ai_res_inbox_backlog)", "{{status}}")]),
        panel(5, "Inbox outcomes", "timeseries", 0, 16, 12, 8, [
            target("sum(rate(ai_res_events_inbox_processed_total[5m]))", "processed"),
            target("sum(rate(ai_res_events_inbox_duplicate_total[5m]))", "duplicate (no-op)", ref="B"),
            target("sum(rate(ai_res_events_sequence_gap_total[5m]))", "deferred by gap", ref="C")], unit="ops"),
        panel(6, "Contract and reconciliation signals (increase 1h)", "timeseries", 12, 16, 12, 8, [
            target("sum(increase(ai_res_events_unknown_major_event_total[1h]))", "unknown major", ),
            target("sum(increase(ai_res_events_cancel_without_workflow_total[1h]))", "cancel without workflow", ref="B"),
            target("sum(increase(ai_res_events_start_already_finished_total[1h]))", "start for finished workflow", ref="C"),
            target("sum(increase(ai_res_events_mark_error_total[1h]))", "mark errors", ref="D")]),
    ], ["events"])
    d["temporal-workflow"] = dashboard("ai-res-temporal", "AI RES / Temporal and Workflow", "Temporal server and SDK worker signals (OBS-MON-007). Manager/Worker business outcomes arrive with S23+.", [
        panel(1, "Temporal server up", "stat", 0, 0, 6, 4, [target('min(up{job="temporal"})', "up")]),
        panel(2, "Pollers by task queue", "timeseries", 6, 0, 18, 4, [target("max by (task_queue, worker_type) (temporal_num_pollers)", "{{task_queue}} {{worker_type}}")]),
        panel(3, "Workflow-task schedule-to-start p95", "timeseries", 0, 4, 12, 8,
              [target("histogram_quantile(0.95, sum by (le, task_queue) (rate(temporal_workflow_task_schedule_to_start_latency_seconds_bucket[5m])))", "{{task_queue}}")], unit="s"),
        panel(4, "Activity schedule-to-start p95", "timeseries", 12, 4, 12, 8,
              [target("histogram_quantile(0.95, sum by (le, task_queue) (rate(temporal_activity_schedule_to_start_latency_seconds_bucket[5m])))", "{{task_queue}}")], unit="s"),
        panel(5, "Worker task slots used / available", "timeseries", 0, 12, 12, 8, [
            target("sum by (task_queue, worker_type) (temporal_worker_task_slots_used)", "used {{task_queue}} {{worker_type}}"),
            target("sum by (task_queue, worker_type) (temporal_worker_task_slots_available)", "available {{task_queue}} {{worker_type}}", ref="B")]),
        panel(6, "Failures and retries (rate)", "timeseries", 12, 12, 12, 8, [
            target("sum by (workflow_type) (rate(temporal_workflow_failed_total[5m]))", "workflow failed {{workflow_type}}"),
            target("sum by (activity_type) (rate(temporal_activity_execution_failed_total[5m]))", "activity failed {{activity_type}}", ref="B"),
            target("sum by (operation) (rate(temporal_request_failure_total[5m]))", "SDK request failure {{operation}}", ref="C")], unit="ops"),
        panel(7, "Server service errors by type", "timeseries", 0, 20, 12, 8, [target("sum by (error_type) (rate(service_error_with_type[5m]))", "{{error_type}}")], unit="ops"),
        panel(8, "Server persistence latency p95", "timeseries", 12, 20, 12, 8,
              [target("histogram_quantile(0.95, sum by (le, operation) (rate(persistence_latency_bucket[5m])))", "{{operation}}")], unit="s"),
    ], ["temporal"])
    d["manager-workers"] = dashboard("ai-res-manager-workers", "AI RES / Manager and Workers (runtime view)", "Runtime-level view of the Manager and Worker Runtime pollers (OBS-MON-008). WorkerRun outcomes, Readiness Gate results, blockers and QA arrive with S23+ (G-128).", [
        panel(1, "Runtime telemetry present", "stat", 0, 0, 12, 4, [target('count(target_info{job=~"ai-res-(manager|worker)-runtime"})', "runtimes")]),
        panel(2, "Pollers by task queue and type", "timeseries", 12, 0, 12, 4, [target("max by (task_queue, worker_type) (temporal_num_pollers)", "{{task_queue}} {{worker_type}}")]),
        panel(3, "Task slots used", "timeseries", 0, 4, 12, 8, [target("sum by (task_queue, worker_type) (temporal_worker_task_slots_used)", "{{task_queue}} {{worker_type}}")]),
        panel(4, "Activity failures (rate)", "timeseries", 12, 4, 12, 8, [target("sum by (activity_type) (rate(temporal_activity_execution_failed_total[5m]))", "{{activity_type}}")], unit="ops"),
        panel(5, "Workflow failures (rate)", "timeseries", 0, 12, 12, 8, [target("sum by (workflow_type) (rate(temporal_workflow_failed_total[5m]))", "{{workflow_type}}")], unit="ops"),
        panel(6, "Platform API calls from the runtimes (rate by class)", "timeseries", 12, 12, 12, 8,
              [target('sum by (http_response_status_class) (rate(http_server_request_duration_seconds_count{service_name="ai-res-platform-api"}[5m]))', "{{http_response_status_class}}")], unit="reqps"),
    ], ["workers"])
    d["postgresql"] = dashboard("ai-res-postgresql", "AI RES / PostgreSQL (application view)", "Application-side connection pool and error signals. Server-side PostgreSQL metrics need a monitoring role that is not part of the baselined role set (NCP-15, G-125).", [
        panel(1, "Pooled connections by state", "timeseries", 0, 0, 12, 8,
              [target("sum by (db_client_connection_pool_name, db_client_connection_state) (db_client_connection_count)", "{{db_client_connection_pool_name}} {{db_client_connection_state}}")]),
        panel(2, "Pool size", "stat", 12, 0, 6, 8, [target("max by (db_client_connection_pool_name) (db_client_connection_max)", "{{db_client_connection_pool_name}}")]),
        panel(3, "Database errors by class (rate)", "timeseries", 18, 0, 6, 8,
              [target("sum by (db_client_connection_pool_name, error_type) (rate(ai_res_db_errors_total[5m]))", "{{db_client_connection_pool_name}} {{error_type}}")], unit="ops"),
        panel(4, "Temporal persistence connections (server)", "timeseries", 0, 8, 12, 8, [
            target("max(persistence_sql_in_use)", "in use"), target("max(persistence_sql_open_conn)", "open", ref="B"), target("max(persistence_sql_max_open_conn)", "max", ref="C")]),
    ], ["postgresql"])
    d["telemetry-pipeline"] = dashboard("ai-res-telemetry", "AI RES / Telemetry Pipeline", "Health of the telemetry path itself: loss is measured, not assumed (OBS-MON-013).", [
        panel(1, "Collector sent (per second)", "timeseries", 0, 0, 12, 8, [
            target("sum by (exporter) (rate(otelcol_exporter_sent_spans[5m]))", "spans {{exporter}}"),
            target("sum by (exporter) (rate(otelcol_exporter_sent_log_records[5m]))", "logs {{exporter}}", ref="B"),
            target("sum by (exporter) (rate(otelcol_exporter_sent_metric_points[5m]))", "metric points {{exporter}}", ref="C")], unit="ops"),
        panel(2, "Collector send failures (per second)", "timeseries", 12, 0, 12, 8, [
            target("sum by (exporter) (rate(otelcol_exporter_send_failed_spans[5m]))", "spans {{exporter}}"),
            target("sum by (exporter) (rate(otelcol_exporter_send_failed_log_records[5m]))", "logs {{exporter}}", ref="B"),
            target("sum by (exporter) (rate(otelcol_exporter_send_failed_metric_points[5m]))", "metric points {{exporter}}", ref="C")], unit="ops"),
        panel(3, "Collector exporter queue fill", "timeseries", 0, 8, 12, 8, [target("otelcol_exporter_queue_size / otelcol_exporter_queue_capacity", "{{exporter}}")], unit="percentunit"),
        panel(4, "Application export failures (increase 5m)", "timeseries", 12, 8, 12, 8,
              [target("sum by (service_name, operation) (increase(ai_res_telemetry_export_failures_total[5m]))", "{{service_name}} {{operation}}")]),
        panel(5, "Collector memory (RSS)", "timeseries", 0, 16, 12, 8, [target("otelcol_process_memory_rss", "rss")], unit="bytes"),
        panel(6, "Receiver refused (memory limiter)", "timeseries", 12, 16, 12, 8, [
            target("sum(rate(otelcol_receiver_refused_spans[5m]))", "spans"), target("sum(rate(otelcol_receiver_refused_log_records[5m]))", "logs", ref="B"),
            target("sum(rate(otelcol_receiver_refused_metric_points[5m]))", "metric points", ref="C")], unit="ops"),
    ], ["telemetry"])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    bad = 0
    for name, dash in build().items():
        text = json.dumps(dash, indent=2, sort_keys=True) + "\n"
        path = OUT / f"{name}.json"
        if args.check:
            if not path.is_file() or path.read_text() != text:
                print(f"STALE: {path.name}")
                bad += 1
        else:
            path.write_text(text)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
