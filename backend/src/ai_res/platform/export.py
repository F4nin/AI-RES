"""Process-wide OTLP export of traces, metrics and logs (DOC-024 §3/§7, ADR-095).

Operational telemetry is FAIL-OPEN: every queue and timeout is bounded, an unreachable Collector never raises into request handling, never blocks a
response and never grows memory without limit (OBS-MON-014/015). Loss is measured (`ai_res.telemetry.export_failures`). Nothing here is a source of
truth and nothing here touches the Audit Log (PostgreSQL), which is a separate circuit.

Without `otlp_endpoint` nothing is exported and the OpenTelemetry API stays a no-op. Logs are sanitised BEFORE they reach the exporter (same redaction as
stdout) and the Collector redacts again (defence in depth, OBS-SEC-003).
"""
import contextlib
import logging
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogExportResult
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricExportResult, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult

from ai_res.platform.config import Settings
from ai_res.platform.redaction import RedactingJsonFormatter, redact, redact_text

log = logging.getLogger("ai_res.telemetry")
_STD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}
_WARN_EVERY_SECONDS = 60.0


class _Loss:
    """Counts failed exports per signal and says so (rate-limited) on the process log. Process-local snapshot + one OTel counter."""

    def __init__(self) -> None:
        self.snapshot: Counter[str] = Counter()
        self._last_warned = float("-inf")
        self._counter = metrics.get_meter("ai_res.telemetry").create_counter(
            "ai_res.telemetry.export_failures", description="Telemetry batches that could not be exported to the Collector")

    def record(self, signal: str) -> None:
        self.snapshot[signal] += 1
        self._counter.add(1, {"operation": signal})
        now = time.monotonic()
        if now - self._last_warned >= _WARN_EVERY_SECONDS:
            self._last_warned = now
            log.warning("telemetry export failing; data is dropped (fail-open)", extra={"signal": signal})


def _counted(base: type, result_ok: Any, method: str = "export") -> type:
    """Subclass of an OTLP exporter that reports every non-OK result as loss. The exporter already swallows transport errors."""

    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            res = getattr(super(cls, self), method)(*args, **kwargs)
        except Exception:  # noqa: BLE001 - an exporter must never raise into the processor thread's caller
            self._loss.record(self._signal)
            return self._failure
        if res != result_ok:
            self._loss.record(self._signal)
        return res

    cls = type(f"Counting{base.__name__}", (base,), {method: wrapper})
    return cls


_CountingSpanExporter: Any = _counted(OTLPSpanExporter, SpanExportResult.SUCCESS)
_CountingMetricExporter: Any = _counted(OTLPMetricExporter, MetricExportResult.SUCCESS)
_CountingLogExporter: Any = _counted(OTLPLogExporter, LogExportResult.SUCCESS)


class _SanitizingLogHandler(LoggingHandler):
    """OTLP log handler that exports a REDACTED copy of the record: the message, every extra field and (as type only) the exception. The original
    record, still needed by the stdout handler, is not touched. Records of `ai_res.telemetry` are never exported (no feedback loop on export failure)."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == log.name:
            return
        clean = logging.makeLogRecord(record.__dict__)
        try:
            clean.msg, clean.args = redact_text(record.getMessage()), ()
        except Exception:  # noqa: BLE001 - a malformed %-format must not break logging (fail-open); export a fixed marker instead
            clean.msg, clean.args = "[unformattable log message]", ()
        for key in [k for k in clean.__dict__ if k not in _STD_ATTRS]:
            setattr(clean, key, redact(clean.__dict__[key], key))
        if record.exc_info and record.exc_info[0]:
            clean.exc_type = record.exc_info[0].__name__
        clean.exc_info, clean.exc_text, clean.stack_info = None, None, None  # a traceback carries values and paths: type only
        super().emit(clean)


class _RateLimitedFilter(logging.Filter):
    def __init__(self, every: float = _WARN_EVERY_SECONDS) -> None:
        super().__init__()
        self._every, self._last = every, float("-inf")

    def filter(self, record: logging.LogRecord) -> bool:
        now = time.monotonic()
        if now - self._last < self._every:
            return False
        self._last = now
        return True


@dataclass
class TelemetryHandle:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider | None
    logger_provider: LoggerProvider | None
    loss: _Loss | None

    def shutdown(self) -> None:
        """Flush and stop. Bounded by the export timeout; failures are ignored (fail-open)."""
        if self in _ACTIVE:
            _ACTIVE.remove(self)  # process_tracer() must not hand out a shut-down provider
        for provider in (self.tracer_provider, self.meter_provider, self.logger_provider):
            if provider is not None:
                with contextlib.suppress(Exception):  # shutting down telemetry must never fail the process
                    provider.shutdown()


_ACTIVE: list[TelemetryHandle] = []


def process_tracer(name: str = "ai_res") -> Any:
    """Tracer of the provider installed for this process, or None when `install_telemetry` was not called (library code then simply does not trace)."""
    return _ACTIVE[-1].tracer_provider.get_tracer(name) if _ACTIVE else None


def resource_for(settings: Settings, service_name: str) -> Resource:
    attributes = {"service.name": service_name, "deployment.environment.name": settings.environment}
    if settings.release_id:
        attributes |= {"service.version": settings.release_id, "ai_res.release_id": settings.release_id}
    return Resource.create(attributes)


def install_telemetry(settings: Settings, service_name: str) -> TelemetryHandle:
    """Configure traces/metrics/logs export for this process. Returns a handle whose `tracer_provider` is always usable (no exporter without an endpoint)."""
    resource = resource_for(settings, service_name)
    tracer_provider = TracerProvider(resource=resource)
    endpoint = settings.otlp_endpoint
    if endpoint is None:
        handle = TelemetryHandle(tracer_provider, None, None, None)
        _ACTIVE.append(handle)
        return handle
    base = endpoint.rstrip("/")
    timeout = settings.otlp_export_timeout_seconds
    loss = _Loss()

    def tune(exporter: Any, signal: str) -> Any:
        exporter._loss, exporter._signal = loss, signal  # noqa: SLF001
        exporter._failure = {"traces": SpanExportResult.FAILURE, "metrics": MetricExportResult.FAILURE, "logs": LogExportResult.FAILURE}[signal]  # noqa: SLF001
        return exporter

    span_exporter = tune(_CountingSpanExporter(endpoint=f"{base}/v1/traces", timeout=timeout), "traces")
    tracer_provider.add_span_processor(BatchSpanProcessor(
        span_exporter, max_queue_size=settings.otlp_queue_size, max_export_batch_size=min(512, settings.otlp_queue_size),
        schedule_delay_millis=5_000, export_timeout_millis=int(timeout * 1000)))

    metric_exporter = tune(_CountingMetricExporter(endpoint=f"{base}/v1/metrics", timeout=timeout), "metrics")
    meter_provider = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=int(settings.otlp_metric_interval_seconds * 1000), export_timeout_millis=int(timeout * 1000))])
    metrics.set_meter_provider(meter_provider)

    log_exporter = tune(_CountingLogExporter(endpoint=f"{base}/v1/logs", timeout=timeout), "logs")
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(
        log_exporter, max_queue_size=settings.otlp_queue_size, max_export_batch_size=min(512, settings.otlp_queue_size),
        schedule_delay_millis=5_000, export_timeout_millis=int(timeout * 1000)))
    handler = _SanitizingLogHandler(level=logging.INFO, logger_provider=logger_provider)
    for name in ("ai_res", "uvicorn.error"):
        lg = logging.getLogger(name)
        for old in [h for h in lg.handlers if isinstance(h, _SanitizingLogHandler)]:  # installing twice must not export every record twice
            lg.removeHandler(old)
        lg.addHandler(handler)

    # The SDK reports exporter trouble through the `opentelemetry` logger on every failed batch; keep it to one redacted line a minute on stderr.
    sdk_log = logging.getLogger("opentelemetry")
    sdk_log.handlers.clear()
    stderr = logging.StreamHandler()
    stderr.setFormatter(RedactingJsonFormatter())
    stderr.addFilter(_RateLimitedFilter())
    sdk_log.addHandler(stderr)
    sdk_log.propagate = False
    handle = TelemetryHandle(tracer_provider, meter_provider, logger_provider, loss)
    _ACTIVE.append(handle)
    return handle
