"""S13: OTLP export is fail-open, bounded, measured and sanitised (OBS-MON-014/015, OBS-SEC-001/003/004)."""
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from ai_res.api.app import create_app
from ai_res.platform.config import Settings
from ai_res.platform.export import install_telemetry

SECRET = "hunter2-CANARY-7731"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnkifQ.c2lnbmF0dXJl"


class _Sink(BaseHTTPRequestHandler):
    bodies: list[bytes] = []

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        type(self).bodies.append(self.rfile.read(n))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def sink():
    _Sink.bodies = []
    srv = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", _Sink
    srv.shutdown()


@pytest.fixture(autouse=True)
def _restore_logging():
    handlers = {n: list(logging.getLogger(n).handlers) for n in ("ai_res", "uvicorn.error", "opentelemetry")}
    yield
    for n, h in handlers.items():
        logging.getLogger(n).handlers[:] = h
    logging.getLogger("opentelemetry").propagate = True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_without_endpoint_nothing_is_exported_and_provider_is_usable():
    handle = install_telemetry(Settings(), "t")
    assert handle.meter_provider is None and handle.loss is None
    with handle.tracer_provider.get_tracer("t").start_as_current_span("x"):
        pass
    handle.shutdown()


def test_dead_collector_never_breaks_requests_and_loss_is_counted():
    settings = Settings(otlp_endpoint=f"http://127.0.0.1:{_free_port()}", otlp_export_timeout_seconds=1, otlp_queue_size=16)
    handle = install_telemetry(settings, "t")
    app = create_app(settings, tracer_provider=handle.tracer_provider)
    client = TestClient(app, raise_server_exceptions=False)
    start = time.monotonic()
    for _ in range(200):
        client.get("/nope")  # 404 through the full middleware stack
        logging.getLogger("ai_res.test").warning("work continues")
    assert time.monotonic() - start < 5, "request handling must not wait for the exporter"
    handle.tracer_provider.force_flush(2000)
    t0 = time.monotonic()
    handle.shutdown()
    assert time.monotonic() - t0 < 15, "shutdown with a dead Collector is bounded"
    assert handle.loss is not None and handle.loss.snapshot["traces"] >= 1


def test_logs_are_sanitised_before_export_and_original_record_is_untouched(sink):
    url, srv = sink
    handle = install_telemetry(Settings(otlp_endpoint=url, otlp_export_timeout_seconds=2), "t")
    lg = logging.getLogger("ai_res.sanitize")
    lg.setLevel(logging.INFO)
    seen: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record)

    lg.addHandler(_Keep())
    try:
        raise ValueError(f"password={SECRET}")
    except ValueError:
        lg.error("login failed password=%s auth %s", SECRET, JWT, exc_info=True, extra={"session_token": SECRET, "prompt": SECRET, "ai_res.request_id": "r-1"})
    handle.logger_provider.force_flush(3000)  # type: ignore[union-attr]
    handle.shutdown()
    blob = b"".join(srv.bodies)
    assert blob, "the log batch reached the sink"
    assert SECRET.encode() not in blob and JWT.encode() not in blob
    assert b"ValueError" in blob  # the exception TYPE is kept, the message and traceback are not
    assert seen[0].exc_info is not None, "stdout handlers still see the original record"


def test_metrics_reach_the_collector_endpoint(sink):
    url, srv = sink
    handle = install_telemetry(Settings(otlp_endpoint=url, otlp_metric_interval_seconds=1, otlp_export_timeout_seconds=2), "t")
    handle.meter_provider.get_meter("t").create_counter("ai_res.test.counter").add(1)  # type: ignore[union-attr]
    handle.meter_provider.force_flush(3000)  # type: ignore[union-attr]
    handle.shutdown()
    assert any(b"ai_res.test.counter" in b for b in srv.bodies)
