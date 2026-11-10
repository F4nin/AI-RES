import logging

import httpx
import pytest
from fastapi import APIRouter, FastAPI, Header
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from ai_res.api.app import create_app
from ai_res.platform.concurrency import check_if_match
from ai_res.platform.config import Settings
from ai_res.platform.pagination import KeyRing
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.telemetry import build_tracer_provider

RING = KeyRing(active_id="k1", keys={"k1": b"a" * 32})


class Body(BaseModel):
    name: str
    count: int


def build_test_app(exporter: InMemorySpanExporter | None = None) -> FastAPI:
    """Test-only routes exercising the platform layer; the real app exposes no endpoints in S02."""
    app = create_app(Settings(environment="test"), build_tracer_provider(exporter))
    r = APIRouter()

    @r.get("/t/boom")
    async def boom() -> None:
        raise RuntimeError("super-secret-internal-detail postgres://user:pw@db/x")

    @r.get("/t/problem")
    async def problem() -> None:
        raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Not allowed.")

    @r.post("/t/body")
    async def body(b: Body) -> dict[str, str]:
        return {"name": b.name}

    @r.patch("/t/versioned")
    async def versioned(if_match: str | None = Header(default=None)) -> dict[str, bool]:
        check_if_match(if_match, current_row_version=3)
        return {"ok": True}

    @r.get("/t/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(r)
    return app


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
async def client(exporter: InMemorySpanExporter):
    # raise_app_exceptions=True: the error boundary must swallow server errors itself; none may escape to the transport.
    transport = httpx.ASGITransport(app=build_test_app(exporter))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """configure_logging mutates global loggers; restore handlers, level, propagate and filters after every test."""
    names = ("ai_res", "uvicorn.error", "uvicorn.access")
    saved = {n: (list(logging.getLogger(n).handlers), logging.getLogger(n).level, logging.getLogger(n).propagate,
                 list(logging.getLogger(n).filters)) for n in names}
    yield
    for n, (handlers, level, propagate, filters) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:], lg.filters[:] = handlers, filters
        lg.setLevel(level)
        lg.propagate = propagate
