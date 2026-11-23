"""Opt-in Backend consumer for committed approvals in trusted tenant scopes."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from opentelemetry import metrics
from opentelemetry.trace import StatusCode, Tracer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.plan_execution import prepare_approved_plan_page
from ai_res.application.reconcile_scheduler import ReconciliationScope
from ai_res.platform.config import ConfigError

log = logging.getLogger(__name__)


class PlanApprovalSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    scopes: tuple[ReconciliationScope, ...] = Field(min_length=1)
    interval_seconds: float = Field(gt=0)
    page_timeout_seconds: float = Field(gt=0)
    page_size: int = Field(gt=0, lt=2**63)


@asynccontextmanager
async def start_plan_approval_consumer(
    config_file: Path, factory: async_sessionmaker[AsyncSession], dispatch_namespace: str, tracer: Tracer,
) -> AsyncIterator[None]:
    try:
        schedule = PlanApprovalSchedule.model_validate_json(config_file.read_bytes())
    except (OSError, ValidationError):
        raise ConfigError("invalid plan approval consumer configuration file") from None
    if len(set(schedule.scopes)) != len(schedule.scopes):
        raise ConfigError("plan approval consumer scopes must be unique")
    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(_consume(factory=factory, namespace=dispatch_namespace, schedule=schedule, tracer=tracer),
                                 name="plan-approval-consumer")
        try:
            yield
        finally:
            task.cancel()


async def _consume(factory: async_sessionmaker[AsyncSession], namespace: str, schedule: PlanApprovalSchedule, tracer: Tracer) -> None:
    meter = metrics.get_meter(__name__)
    pages = meter.create_counter("ai_res.plan.approval.pages")
    while True:
        for scope in schedule.scopes:
            with tracer.start_as_current_span("plan.approval.page", record_exception=False, set_status_on_exception=False) as span:
                try:
                    async with asyncio.timeout(schedule.page_timeout_seconds):
                        await prepare_approved_plan_page(
                            factory, scope.organization_id, scope.project_id, dispatch_namespace=namespace, page_size=schedule.page_size,
                        )
                except (SQLAlchemyError, TimeoutError) as exc:
                    span.set_status(StatusCode.ERROR)
                    pages.add(1, {"outcome": "failed"})
                    log.warning("plan approval page failed", extra={"error_class": type(exc).__name__})
                else:
                    pages.add(1, {"outcome": "scanned"})
        await asyncio.sleep(schedule.interval_seconds)
