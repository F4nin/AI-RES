"""Durable ADR-182 delivery from the committed Manager Operation journal."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from opentelemetry import metrics
from opentelemetry.trace import StatusCode, Tracer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.application.proactive_messages import NotificationEvent, NotificationScope, plan_proactive_messages
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.platform.clock import utc_now
from ai_res.platform.config import ConfigError
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError

_log = logging.getLogger(__name__)
_DIGEST_BATCH_SIZE = 100  # technical transaction bound, independent of source cadence and recipient pagination
Seconds = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class ProjectNotifications(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    organization_id: UUID
    project_id: UUID
    digest_intervals_seconds: tuple[Seconds, ...]

    @model_validator(mode="after")
    def _unique_intervals(self) -> "ProjectNotifications":
        if len(set(self.digest_intervals_seconds)) != len(self.digest_intervals_seconds):
            raise ValueError("Digest intervals must be unique")
        return self


class NotificationSchedule(BaseModel):
    """Trust only Backend configuration to supply project scopes and frequency options."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    projects: tuple[ProjectNotifications, ...] = Field(min_length=1)
    poll_interval_seconds: float = Field(gt=0)
    page_timeout_seconds: float = Field(gt=0)
    page_size: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def _unique_projects(self) -> "NotificationSchedule":
        if len({(p.organization_id, p.project_id) for p in self.projects}) != len(self.projects):
            raise ValueError("Notification project scopes must be unique")
        return self


def load_notification_schedule(path: Path) -> NotificationSchedule:
    try:
        return NotificationSchedule.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        raise ConfigError("Invalid notification schedule configuration file") from None


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    selected: int | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class NotificationItem:
    event_id: UUID
    operation_id: UUID
    proposal_version_id: UUID | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationPosition:
    published_at: datetime
    delivery_id: UUID
    occurred_at: datetime
    event_id: UUID


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    id: UUID
    published_at: datetime
    items: tuple[NotificationItem, ...]


_RECIPIENT_CONTEXT = text("SELECT set_config('app.notification_recipient_id', :recipient, true)")
_EXACT_SOURCE = """
    FROM operations.operation_events e
    JOIN operations.operations o ON o.id=e.operation_id
    JOIN work.manager_interactions i
      ON (i.organization_id,i.project_id,i.operation_id,i.author_id)=(o.organization_id,o.project_id,o.id,o.initiator_id)
    LEFT JOIN work.manager_proposal_versions p
      ON (p.organization_id,p.project_id,p.interaction_id)=(i.organization_id,i.project_id,i.id)
      AND o.status='SUCCEEDED' AND p.id::text=o.result_ref->>'id'
"""
_QUALIFIED = """
    o.organization_id=:org AND o.project_id=:project AND o.initiator_id=:recipient
    AND o.operation_type='MANAGER_MESSAGE' AND o.initiator_type='USER' AND o.status IN ('FAILED','SUCCEEDED')
    AND e.schema_version=1 AND e.to_status=o.status
    AND ((e.event_type='operation.failed' AND o.status='FAILED')
         OR (e.event_type='operation.succeeded' AND o.status='SUCCEEDED' AND p.id IS NOT NULL))
"""
_CANDIDATES = text(f"""
    SELECT e.event_id,o.id AS operation_id,p.id AS proposal_version_id,e.occurred_at
    {_EXACT_SOURCE}
    WHERE {_QUALIFIED}
      AND (p.id IS NULL)=:mandatory AND (:mandatory OR e.occurred_at<=:cutoff)
      AND NOT EXISTS (SELECT 1 FROM project.notification_events n WHERE n.event_id=e.event_id)
    ORDER BY e.occurred_at,e.event_id LIMIT :limit
""")  # noqa: S608 - fixed query fragments
_INSERT_DELIVERY = text("""
    INSERT INTO project.notification_deliveries (organization_id,project_id,recipient_id,id,mandatory,cutoff_at,published_at)
    VALUES (:org,:project,:recipient,:delivery,:mandatory,:cutoff,:published)
""")
_INSERT_NOTIFICATION = text("""
    INSERT INTO project.notification_events (
        organization_id,project_id,recipient_id,event_id,operation_id,proposal_version_id,occurred_at,delivery_id
    )
    VALUES (:org,:project,:recipient,:event_id,:operation_id,:proposal_version_id,:occurred_at,:delivery)
""")
_DELIVERY_SCOPE = "organization_id=:org AND project_id=:project AND recipient_id=:recipient"
_FEED_MEMBERS = """
    SELECT event_id,operation_id,proposal_version_id,occurred_at
    FROM project.notification_events
    WHERE organization_id=:org AND project_id=:project AND recipient_id=:recipient AND delivery_id=d.id
"""
_FEED_MEMBERS_ORDER = "ORDER BY occurred_at DESC,event_id DESC LIMIT :limit"
_FEED_COLUMNS = "d.id AS delivery_id,d.published_at,n.event_id,n.operation_id,n.proposal_version_id,n.occurred_at"
_FEED_ORDER = "ORDER BY published_at DESC,delivery_id DESC,occurred_at DESC,event_id DESC"
_FEED_SQL = f"""
    WITH delivery_heads AS MATERIALIZED (
        SELECT id,published_at FROM project.notification_deliveries
        WHERE {_DELIVERY_SCOPE} AND published_at IS NOT NULL /* mandatory filter */ /* prior deliveries */
        ORDER BY published_at DESC,id DESC LIMIT :head_limit
    ),
    candidates AS MATERIALIZED (
        SELECT * FROM (
            SELECT {_FEED_COLUMNS}
            FROM delivery_heads d
            CROSS JOIN LATERAL ({_FEED_MEMBERS} {_FEED_MEMBERS_ORDER}) n
            /* remaining members */
        ) refs
        {_FEED_ORDER} LIMIT :limit
    )
    SELECT c.*,EXISTS (
        SELECT 1 {_EXACT_SOURCE}
        WHERE {_QUALIFIED}
          AND e.event_id=c.event_id AND o.id=c.operation_id AND p.id IS NOT DISTINCT FROM c.proposal_version_id AND e.occurred_at=c.occurred_at
    ) AS exact_source
    FROM candidates c {_FEED_ORDER}
"""  # noqa: S608 - fixed query fragments
# Separate the current delivery from older heads so both tuple comparisons can use index bounds,
# even when PostgreSQL chooses a generic plan. The current delivery contributes at most one head.
_REMAINING_MEMBERS = f"""
    UNION ALL
    SELECT {_FEED_COLUMNS}
    FROM project.notification_deliveries d
    CROSS JOIN LATERAL (
        {_FEED_MEMBERS} AND (occurred_at,event_id)<(:before_occurred,:before_event) {_FEED_MEMBERS_ORDER}
    ) n
    WHERE {_DELIVERY_SCOPE} AND d.id=:before_id AND d.published_at=:before_time /* mandatory filter */
"""  # noqa: S608 - fixed query fragments
_RESUMED_FEED_SQL = _FEED_SQL.replace(
    "/* prior deliveries */", "AND (published_at,id)<(:before_time,:before_id)",
).replace("/* remaining members */", _REMAINING_MEMBERS)
_FEED_QUERIES = {
    (resumed, include_digests): text(query.replace("/* mandatory filter */", "" if include_digests else "AND mandatory"))
    for resumed, query in ((False, _FEED_SQL), (True, _RESUMED_FEED_SQL))
    for include_digests in (False, True)
}


def _scope_fields(scope: NotificationScope) -> dict[str, UUID]:
    return {"org": scope.organization_id, "project": scope.project_id, "recipient": scope.recipient_id}


async def set_notification_recipient(uow: UnitOfWork, scope: NotificationScope, *, lock: bool = False) -> None:
    """Use only a verified session subject or a recipient derived from trusted domain facts."""
    await uow.with_tenant(scope.organization_id, scope.project_id)
    await uow.session.execute(_RECIPIENT_CONTEXT, {"recipient": str(scope.recipient_id)})
    if lock:
        key = f"ai-res-notifications/{scope.organization_id}/{scope.project_id}/{scope.recipient_id}"
        await uow.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


async def read_preference(session: AsyncSession) -> NotificationPreference:
    row = (await session.execute(text("SELECT interval_seconds,row_version FROM project.notification_preferences"))).one_or_none()
    return NotificationPreference() if row is None else NotificationPreference(row.interval_seconds, row.row_version)


async def write_preference(
    session: AsyncSession, scope: NotificationScope, *, selected: int, expected: int, request_id: str | None,
) -> NotificationPreference:
    current = await read_preference(session)
    if current.version != expected:
        raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
    if current.selected == selected:
        return current
    next_version = current.version + 1
    await session.execute(text("""
        INSERT INTO project.notification_preferences (organization_id,project_id,recipient_id,interval_seconds,row_version)
        VALUES (:org,:project,:recipient,:interval,:version)
        ON CONFLICT (organization_id,project_id,recipient_id) DO UPDATE
        SET interval_seconds=EXCLUDED.interval_seconds,row_version=EXCLUDED.row_version
    """), {**_scope_fields(scope), "interval": selected, "version": next_version})
    await SqlAuditWriter(session).write(AuditRecord(
        action="NOTIFICATION_PREFERENCE_UPDATED", outcome=AuditOutcome.SUCCEEDED, resource_type="PROJECT",
        resource_id=str(scope.project_id), actor_id=str(scope.recipient_id), organization_id=str(scope.organization_id),
        project_id=str(scope.project_id), request_id=request_id,
        details={"intervalSeconds": selected, "rowVersion": next_version},
    ))
    return NotificationPreference(selected, next_version)


async def read_delivery_candidates(
    session: AsyncSession, scope: NotificationScope, *, before: NotificationPosition | None, include_digests: bool, limit: int,
) -> tuple[tuple[NotificationPosition, NotificationItem | None], ...]:
    """Read a bounded slice of exact source refs, with incomplete digests hidden until they close."""
    params: dict[str, UUID | datetime | int] = {**_scope_fields(scope), "limit": limit, "head_limit": limit + 1}
    if before is not None:
        params.update(before_time=before.published_at, before_id=before.delivery_id, before_occurred=before.occurred_at, before_event=before.event_id)
    rows = (await session.execute(_FEED_QUERIES[before is not None, include_digests], params)).all()
    return tuple(
        (NotificationPosition(row.published_at, row.delivery_id, row.occurred_at, row.event_id),
         NotificationItem(row.event_id, row.operation_id, row.proposal_version_id, row.occurred_at) if row.exact_source else None)
        for row in rows
    )


async def _candidates(
    session: AsyncSession, scope: NotificationScope, *, mandatory: bool, cutoff: datetime, limit: int,
) -> tuple[NotificationItem, ...]:
    rows = (await session.execute(_CANDIDATES, {
        **_scope_fields(scope), "mandatory": mandatory, "cutoff": cutoff, "limit": limit,
    })).all()
    return tuple(NotificationItem(row.event_id, row.operation_id, row.proposal_version_id, row.occurred_at) for row in rows)


async def _store_candidates(
    session: AsyncSession, scope: NotificationScope, candidates: tuple[NotificationItem, ...], *,
    delivery_id: UUID | None = None,
) -> None:
    if not candidates:
        return
    await session.execute(_INSERT_NOTIFICATION, [{
        **_scope_fields(scope), "delivery": delivery_id or item.event_id, "event_id": item.event_id,
        "operation_id": item.operation_id, "proposal_version_id": item.proposal_version_id, "occurred_at": item.occurred_at,
    } for item in candidates])


async def _continue_digest(
    session: AsyncSession, scope: NotificationScope, options: ProjectNotifications, now: datetime,
) -> int:
    active = (await session.execute(text("""
        SELECT id,cutoff_at FROM project.notification_deliveries WHERE published_at IS NULL
    """))).one_or_none()
    cutoff = now if active is None else active.cutoff_at
    interval = None
    last_digest = None
    if active is None:
        selection = (await read_preference(session)).selected
        if selection is None or selection not in options.digest_intervals_seconds:
            return 0
        interval = timedelta(seconds=selection)
        last_digest = (await session.execute(text("""
            SELECT published_at FROM project.notification_deliveries
            WHERE NOT mandatory AND published_at IS NOT NULL ORDER BY published_at DESC LIMIT 1
        """))).scalar_one_or_none()
        if last_digest is not None and now < last_digest + interval:
            return 0
    candidates = await _candidates(session, scope, mandatory=False, cutoff=cutoff, limit=_DIGEST_BATCH_SIZE + 1)
    if active is None:
        if not candidates or interval is None:
            return 0
        first = candidates[0]
        plan = plan_proactive_messages(
            scope, (NotificationEvent(scope, first.event_id, first.occurred_at, False),), now=now,
            digest_interval=interval, last_digest_at=last_digest,
        )
        if not plan.digest:
            return 0
        digest_id = new_id()
        await session.execute(_INSERT_DELIVERY, {
            **_scope_fields(scope), "delivery": digest_id, "mandatory": False, "cutoff": cutoff, "published": None,
        })
    else:
        digest_id = active.id

    batch = candidates[:_DIGEST_BATCH_SIZE]
    await _store_candidates(session, scope, batch, delivery_id=digest_id)
    if len(candidates) > _DIGEST_BATCH_SIZE:
        return 0
    await session.execute(text("""
        UPDATE project.notification_deliveries SET published_at=:now WHERE id=:id AND published_at IS NULL
    """), {"now": now, "id": digest_id})
    first_event = (await session.execute(text("""
        SELECT event_id FROM project.notification_events WHERE delivery_id=:id ORDER BY occurred_at,event_id LIMIT 1
    """), {"id": digest_id})).scalar_one()
    await _audit_publication(session, scope, first_event, digest_id, "DIGEST")
    return 1


async def publish_mandatory(
    factory: async_sessionmaker[AsyncSession], scope: NotificationScope, *, batch_size: int,
) -> int:
    """Commit failures independently of the recipient's optional digest work."""
    async with UnitOfWork(factory) as uow:
        await set_notification_recipient(uow, scope, lock=True)
        now = utc_now()
        mandatory = await _candidates(uow.session, scope, mandatory=True, cutoff=now, limit=batch_size)
        if mandatory:
            await uow.session.execute(_INSERT_DELIVERY, [{
                **_scope_fields(scope), "delivery": item.event_id, "mandatory": True, "cutoff": item.occurred_at, "published": now,
            } for item in mandatory])
            await _store_candidates(uow.session, scope, mandatory)
        for item in mandatory:
            await _audit_publication(uow.session, scope, item.event_id, item.event_id, "MANDATORY")
        return len(mandatory)


async def publish_digest(
    factory: async_sessionmaker[AsyncSession], scope: NotificationScope, options: ProjectNotifications,
) -> int:
    if (scope.organization_id, scope.project_id) != (options.organization_id, options.project_id):
        raise ValueError("Notification options belong to a different project")
    async with UnitOfWork(factory) as uow:
        await set_notification_recipient(uow, scope, lock=True)
        return await _continue_digest(uow.session, scope, options, utc_now())


async def _audit_publication(
    session: AsyncSession, scope: NotificationScope, source_event_id: UUID, delivery_id: UUID, kind: str,
) -> None:
    correlation_id = (await session.execute(text(
        "SELECT correlation_id FROM operations.operation_events WHERE event_id=:id",
    ), {"id": source_event_id})).scalar_one()
    await SqlAuditWriter(session).write(AuditRecord(
        action="NOTIFICATION_PUBLISHED", outcome=AuditOutcome.SUCCEEDED, resource_type="NOTIFICATION",
        resource_id=str(delivery_id), actor_type="SERVICE", organization_id=str(scope.organization_id),
        project_id=str(scope.project_id), request_id=str(correlation_id), details={"kind": kind},
    ))


async def _recipients(
    factory: async_sessionmaker[AsyncSession], project: ProjectNotifications, after: UUID | None, limit: int,
) -> tuple[UUID, ...]:
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(project.organization_id, project.project_id)
        result = await uow.session.execute(text("""
            SELECT DISTINCT author_id FROM work.manager_interactions
            WHERE organization_id=:org AND project_id=:project AND (CAST(:after AS uuid) IS NULL OR author_id>:after)
            ORDER BY author_id LIMIT :limit
        """), {"org": project.organization_id, "project": project.project_id, "after": after, "limit": limit})
        return tuple(result.scalars())


class NotificationScheduler:
    def __init__(self, factory: async_sessionmaker[AsyncSession], schedule: NotificationSchedule, tracer: Tracer) -> None:
        self._factory, self._schedule, self._tracer = factory, schedule, tracer
        self._after: dict[tuple[UUID, UUID], UUID | None] = {}
        meter = metrics.get_meter(__name__)
        self._processed = meter.create_counter("ai_res.notification.scheduler.pages")
        self._delivered = meter.create_counter("ai_res.notification.published.entries")

    async def run_once(self) -> None:
        for project in self._schedule.projects:
            key = project.organization_id, project.project_id
            with self._tracer.start_as_current_span("notification.delivery.page", record_exception=False, set_status_on_exception=False) as span:
                try:
                    async with asyncio.timeout(self._schedule.page_timeout_seconds):
                        recipients = await _recipients(self._factory, project, self._after.get(key), self._schedule.page_size)
                        for recipient in recipients:
                            # Each scan wraps back to the first recipient. A repeatedly failing recipient cannot hold up the rest of the project.
                            self._after[key] = recipient
                            scope = NotificationScope(*key, recipient)
                            mandatory = await publish_mandatory(self._factory, scope, batch_size=self._schedule.page_size)
                            self._delivered.add(mandatory, {"kind": "mandatory"})
                            digest = await publish_digest(self._factory, scope, project)
                            self._delivered.add(digest, {"kind": "digest"})
                        if len(recipients) < self._schedule.page_size:
                            self._after.pop(key, None)
                except (SQLAlchemyError, TimeoutError) as exc:
                    span.set_status(StatusCode.ERROR)
                    self._processed.add(1, {"outcome": "failed"})
                    _log.warning("Notification delivery page failed", extra={"error_class": type(exc).__name__})
                else:
                    self._processed.add(1, {"outcome": "scanned"})

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._schedule.poll_interval_seconds)


@asynccontextmanager
async def start_notification_delivery(
    factory: async_sessionmaker[AsyncSession], schedule: NotificationSchedule, tracer: Tracer,
) -> AsyncIterator[None]:
    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(NotificationScheduler(factory, schedule, tracer).run_forever(), name="notification-delivery")
        try:
            yield
        finally:
            task.cancel()
