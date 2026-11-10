"""OpenTelemetry setup and ASGI span middleware (ADR-025). Spans carry an allowlist of attributes only."""
from opentelemetry import context as otel_context
from opentelemetry.propagators.textmap import DefaultGetter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer, format_span_id, format_trace_id
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_res.platform.correlation import current_request_id, valid_traceparent

SERVICE_NAME = "ai-res-backend"
_PROPAGATOR = TraceContextTextMapPropagator()


def build_tracer_provider(exporter: SpanExporter | None = None) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


class TelemetryMiddleware:
    """One server span per request, a child of a *valid* incoming W3C traceparent. Records method, route template,
    status and request id only — never headers, query strings, cookies, bodies or exception messages/stack traces."""

    def __init__(self, app: ASGIApp, tracer: Tracer) -> None:
        self.app, self.tracer = app, tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = next((v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"traceparent"), None)
        carrier = {"traceparent": tp} if (tp := valid_traceparent(raw)) else {}
        parent = _PROPAGATOR.extract(carrier, otel_context.get_current(), getter=DefaultGetter())
        with self.tracer.start_as_current_span("http.request", context=parent, kind=SpanKind.SERVER,
                                               record_exception=False, set_status_on_exception=False) as span:
            span.set_attribute("http.request.method", scope["method"])
            if (rid := current_request_id()):
                span.set_attribute("ai_res.request_id", rid)
            ctx = span.get_span_context()
            traceparent = f"00-{format_trace_id(ctx.trace_id)}-{format_span_id(ctx.span_id)}-{int(ctx.trace_flags):02x}"

            async def send_wrapper(message: Message) -> None:
                if message["type"] == "http.response.start":
                    status = message["status"]
                    span.set_attribute("http.response.status_code", status)
                    span.set_attribute("http.route", getattr(scope.get("route"), "path", "unmatched"))
                    if status >= 500:
                        span.set_status(Status(StatusCode.ERROR))  # no description: never carries exception text
                    kept = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"traceparent"]
                    message["headers"] = [*kept, (b"traceparent", traceparent.encode())]
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                span.set_status(Status(StatusCode.ERROR))  # e.g. failure after the response started; no exception text recorded
                raise
