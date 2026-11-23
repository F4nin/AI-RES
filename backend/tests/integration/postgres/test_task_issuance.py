"""Native authorization stores and matches only the issuer's task metadata."""
import asyncio
import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.task_issuance import IssuanceLookup, TaskExecutionRef, TaskIssuanceStore, TaskKind
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, WORKER_TASK_QUEUE
from ai_res.platform.ports import ServiceName

from .test_repositories import engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres


async def test_durable_issuance_preserves_exact_scope_under_concurrency(world, engine_for):  # noqa: F811
    factory = create_session_factory(engine_for("ai_res_platform_api"))
    store = TaskIssuanceStore(factory)
    digest = hashlib.sha256(b"synthetic native task bytes").digest()
    key = IssuanceLookup(digest, ServiceName.MANAGER_RUNTIME, "fixture", MANAGER_TASK_QUEUE, TaskKind.WORKFLOW)
    reference = TaskExecutionRef(uuid4(), uuid4())
    assert await store.check(key) is None
    assert await asyncio.gather(*(store.register(key, reference) for _ in range(4))) == [True] * 4
    assert await TaskIssuanceStore(factory).check(key) == reference
    assert await store.check(replace(key, namespace="other")) is None
    assert await store.check(replace(key, task_kind=TaskKind.ACTIVITY)) is None
    with pytest.raises(ValueError):
        replace(key, principal=ServiceName.WORKER_RUNTIME, queue=WORKER_TASK_QUEUE)
    assert not await store.register(key, replace(reference, workflow_run_id=uuid4()))
    assert await store.check(key) == reference
    with world.connect("ai_res_platform_api") as connection:
        assert connection.execute("SELECT operation_id FROM platform.task_issuance_receipts").fetchall() == []
    with world.connect() as connection:
        assert connection.execute("SELECT token_digest,operation_id,workflow_run_id FROM platform.task_issuance_receipts").fetchall() == [
            (digest, reference.operation_id, reference.workflow_run_id),
        ]
