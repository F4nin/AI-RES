"""Connection-pool and error metrics of an AsyncEngine (S13, OBS-MON-001).

PostgreSQL server-side metrics (locks, replication, bloat) need a monitoring role that the baselined role set does not contain (NCP-15, G-125); until it is
decided this application-side view is the PostgreSQL signal. Attributes are fixed low-cardinality codes: the pool name is a per-process constant and the error
type is a DBAPI exception class name - never SQL text, parameters or identifiers.
"""
from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from sqlalchemy import event
from sqlalchemy.engine.interfaces import ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

_POOL = "db.client.connection.pool.name"


def register_pool_metrics(engine: AsyncEngine, pool_name: str) -> None:
    pool = engine.sync_engine.pool
    meter = metrics.get_meter("ai_res.db")

    def connections(_: CallbackOptions) -> Iterable[Observation]:
        if not isinstance(pool, QueuePool):
            return []
        used = pool.checkedout()
        return [Observation(used, {_POOL: pool_name, "db.client.connection.state": "used"}),
                Observation(max(pool.checkedin(), 0), {_POOL: pool_name, "db.client.connection.state": "idle"})]

    def limit(_: CallbackOptions) -> Iterable[Observation]:
        # pool_size + max_overflow: the real ceiling (a pool at pool_size is NOT saturated while overflow connections may still be opened)
        return [Observation(pool.size() + max(getattr(pool, "_max_overflow", 0), 0), {_POOL: pool_name})] if isinstance(pool, QueuePool) else []

    meter.create_observable_gauge("db.client.connection.count", callbacks=[connections], description="Pooled connections by state")
    meter.create_observable_gauge("db.client.connection.max", callbacks=[limit], description="Maximum pooled connections (pool_size + max_overflow)")
    errors = meter.create_counter("ai_res.db.errors", description="Database errors seen by the application, by exception class")

    @event.listens_for(engine.sync_engine, "handle_error")
    def _count(ctx: ExceptionContext) -> None:
        original = ctx.original_exception
        errors.add(1, {_POOL: pool_name, "error.type": type(original).__name__[:64]})
