"""Backend scheduler for purpose-bound Operation reconciliation."""
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode, Tracer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.service import RPCError, TLSConfig

from ai_res.application.observe_operations import TemporalExecutionObserver
from ai_res.application.reconcile_operations import BoundExecutionObserver, reconcile_bound_start_page
from ai_res.orchestration.client import connect
from ai_res.orchestration.contracts import ASSIGNED_WORKFLOW_TYPES
from ai_res.platform.config import ConfigError, Settings

_MANAGER_INTAKE = frozenset({"MANAGER_MESSAGE"})  # ADR-151 compatibility for existing deployments.
log = logging.getLogger(__name__)


class ReconciliationScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    project_id: UUID


class BoundStartSchedule(BaseModel):
    """Explicit Backend deployment settings. Scope and budgets come from a trusted file."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    scopes: tuple[ReconciliationScope, ...] = Field(min_length=1)
    admitted_operation_types: tuple[str, ...] = ("MANAGER_MESSAGE",)
    page_size: int = Field(gt=0, lt=2**63 - 1)  # PostgreSQL LIMIT includes a one-row lookahead
    interval_seconds: float = Field(gt=0)
    page_timeout_seconds: float = Field(gt=0)
    rpc_timeout_seconds: float = Field(ge=0.000001, lt=timedelta.max.total_seconds())
    server_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
    ca_file: Path
    certificate_file: Path
    private_key_file: Path = Field(repr=False)
    include_post_ack: bool = False

    @model_validator(mode="after")
    def _check_schedule(self) -> "BoundStartSchedule":
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("reconciliation scope is repeated")
        if (not self.admitted_operation_types or len(set(self.admitted_operation_types)) != len(self.admitted_operation_types)
                or not set(self.admitted_operation_types) <= set(ASSIGNED_WORKFLOW_TYPES)):
            raise ValueError("reconciliation operation types must be a unique non-empty admitted set")
        if self.page_timeout_seconds <= self.page_size * self.rpc_timeout_seconds:
            raise ValueError("reconciliation page budget must exceed the sum of its RPC deadlines")
        return self


def load_bound_start_schedule(settings: Settings) -> BoundStartSchedule:
    if settings.reconciliation_config_file is None or settings.temporal_address is None:
        raise ConfigError("reconciliation requires its configuration file and temporal_address")
    try:
        raw = settings.reconciliation_config_file.read_bytes()
        # Reject ambiguous trusted configuration before Pydantic's JSON parser
        # (which otherwise accepts the last occurrence of a duplicate key).
        json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        return BoundStartSchedule.model_validate_json(raw)
    except (OSError, ValueError, ValidationError):
        raise ConfigError("invalid reconciliation configuration file") from None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


class BoundStartScheduler:
    def __init__(self, factory: async_sessionmaker[AsyncSession], observer: BoundExecutionObserver,
                 config: BoundStartSchedule, *, tracer: Tracer | None = None) -> None:
        self._factory, self._observer, self._config = factory, observer, config
        self._admitted_types = frozenset(config.admitted_operation_types)
        self._after: dict[ReconciliationScope, UUID | None] = dict.fromkeys(config.scopes)
        self._tracer = tracer or trace.get_tracer(__name__)
        meter = metrics.get_meter(__name__)
        self._pages = meter.create_counter("ai_res.operation.reconciliation.pages")
        self._operations = meter.create_counter("ai_res.operation.reconciliation.operations")

    async def run_once(self) -> None:
        """Give each configured project one page and retain its cursor on failure."""
        for scope in self._config.scopes:
            with self._tracer.start_as_current_span("operation.reconciliation.page", record_exception=False, set_status_on_exception=False) as span:
                try:
                    page = await reconcile_bound_start_page(
                        self._factory, self._observer, organization_id=scope.organization_id, project_id=scope.project_id,
                        admitted_types=self._admitted_types, page_size=self._config.page_size, after=self._after[scope],
                        timeout_seconds=self._config.page_timeout_seconds, include_post_ack=self._config.include_post_ack,
                    )
                except (SQLAlchemyError, TimeoutError) as exc:
                    span.set_status(StatusCode.ERROR)
                    self._pages.add(1, {"outcome": "failed"})
                    log.warning("operation reconciliation page failed", extra={"error_class": type(exc).__name__})
                    continue
                self._after[scope] = page.next_after
                if page.timed_out:
                    span.set_status(StatusCode.ERROR)
                self._pages.add(1, {"outcome": "timed_out" if page.timed_out else "scanned"})
                self._operations.add(page.checked, {"outcome": "checked"})
                self._operations.add(page.corrected, {"outcome": "corrected"})

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._config.interval_seconds)


@asynccontextmanager
async def start_bound_reconciliation(settings: Settings, factory: async_sessionmaker[AsyncSession], tracer: Tracer) -> AsyncIterator[None]:
    schedule = load_bound_start_schedule(settings)
    try:
        ca, cert, key = (path.read_bytes() for path in (schedule.ca_file, schedule.certificate_file, schedule.private_key_file))
    except OSError:
        raise ConfigError("reconciliation requires readable mTLS files") from None
    if not (ca and cert and key):
        raise ConfigError("reconciliation requires nonempty mTLS files")
    tls = TLSConfig(server_root_ca_cert=ca, domain=schedule.server_name, client_cert=cert, client_private_key=key)
    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(_run_bound_reconciliation(settings, factory, schedule, tls, tracer), name="manager-start-reconciliation")
        try:
            yield
        finally:
            task.cancel()


async def _run_bound_reconciliation(settings: Settings, factory: async_sessionmaker[AsyncSession], schedule: BoundStartSchedule,
                                    tls: TLSConfig, tracer: Tracer) -> None:
    while True:
        try:
            async with asyncio.timeout(schedule.rpc_timeout_seconds):
                client = await connect(settings, tracer, tls=tls)
        except (RPCError, RuntimeError, TimeoutError) as exc:
            # The SDK reports an initial transport failure as RuntimeError. Log the type only.
            log.warning("reconciliation observer connection failed", extra={"error_class": type(exc).__name__})
            await asyncio.sleep(schedule.interval_seconds)
        else:
            break
    observer = TemporalExecutionObserver(client, deadline=timedelta(seconds=schedule.rpc_timeout_seconds))
    await BoundStartScheduler(factory, observer, schedule, tracer=tracer).run_forever()
