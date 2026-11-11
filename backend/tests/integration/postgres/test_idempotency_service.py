# ruff: noqa: E501, S608  -- fixed literal SQL in test fixtures
"""S07 slice 6: idempotency service (ADR-024): HMAC digests with key id, scope, fingerprint, replay, 409, rotation and the rotation-boundary race."""
import asyncio
import base64
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.idempotency.repository import IdempotencyOutcome
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService, load_keyring
from ai_res.platform.config import ConfigError, load_settings
from ai_res.platform.problems import ErrorCode, ProblemError

pytestmark = pytest.mark.postgres
K1, K2 = bytes(range(32)), bytes(range(100, 132))
KEY = "client-key-0123456789abcdef"
PAYLOAD = {"title": "Plan", "items": [1, 2]}


def svc(*keys: tuple[str, bytes]) -> IdempotencyService:
    return IdempotencyService(IdempotencyKeyRing(keys[0][0], dict(keys)), timedelta(hours=24))


async def begin(world: Any, service: IdempotencyService, *, org: Any = None, actor: Any = None, command: str = "createOperation", key: str = KEY, payload: Any = PAYLOAD, complete: bool = False) -> Any:
    org = org or world.org_a
    async with UnitOfWork(create_session_factory(world.engine())) as uow:
        await uow.with_tenant(org)
        rec = await service.begin(uow.session, organization_id=org, project_id=None, actor_type="USER", actor_id=actor or world.user_a, command=command, key=key, payload=payload)
        if complete and rec.outcome is IdempotencyOutcome.NEW:
            await service.complete(uow.session, rec, status="COMPLETED", resource_type="OPERATION", resource_id=uuid4(), response_status=202, response_body_ref={"operationId": "x"})
        return rec


def rows(world: Any) -> int:
    with world.pg.connect() as c:
        return int(c.execute("SELECT count(*) FROM platform.idempotency_records").fetchone()[0])


async def test_first_call_is_new_then_replay_with_the_stored_response(iam_world: Any) -> None:
    s = svc(("k1", K1))
    first = await begin(iam_world, s, complete=True)
    again = await begin(iam_world, s)
    assert first.outcome is IdempotencyOutcome.NEW and again.outcome is IdempotencyOutcome.REPLAY
    assert again.response_status == 202 and again.response_body_ref == {"operationId": "x"} and again.resource_id is not None and rows(iam_world) == 1


async def test_same_key_with_a_different_request_is_409(iam_world: Any) -> None:
    s = svc(("k1", K1))
    await begin(iam_world, s, complete=True)
    for kw in ({"payload": {"title": "Other"}}, {"payload": PAYLOAD | {"items": [2, 1]}}):
        with pytest.raises(ProblemError) as e:
            await begin(iam_world, s, **kw)
        assert e.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED and e.value.status == 409
    assert rows(iam_world) == 1


async def test_payload_key_order_does_not_change_the_fingerprint(iam_world: Any) -> None:
    s = svc(("k1", K1))
    await begin(iam_world, s, payload={"a": 1, "b": 2}, complete=True)
    assert (await begin(iam_world, s, payload={"b": 2, "a": 1})).outcome is IdempotencyOutcome.REPLAY


async def test_scope_is_organization_actor_and_command(iam_world: Any) -> None:
    s = svc(("k1", K1))
    await begin(iam_world, s, complete=True)
    assert (await begin(iam_world, s, command="otherCommand")).outcome is IdempotencyOutcome.NEW  # same key, another command
    assert (await begin(iam_world, s, actor=uuid4())).outcome is IdempotencyOutcome.NEW  # another actor
    assert (await begin(iam_world, s, org=iam_world.org_b, actor=iam_world.user_b)).outcome is IdempotencyOutcome.NEW  # another organization
    assert rows(iam_world) == 4


async def test_unfinished_first_request_is_reported_as_in_progress_not_executed_again(iam_world: Any) -> None:
    s = svc(("k1", K1))
    assert (await begin(iam_world, s)).outcome is IdempotencyOutcome.NEW  # committed without complete()
    assert (await begin(iam_world, s)).outcome is IdempotencyOutcome.IN_PROGRESS


async def test_parallel_identical_requests_create_one_record_and_one_new(iam_world: Any) -> None:
    s = svc(("k1", K1))
    results = await asyncio.gather(*(begin(iam_world, s) for _ in range(8)))
    assert sorted(r.outcome.value for r in results).count("NEW") == 1 and rows(iam_world) == 1


async def test_only_digests_are_stored_never_the_key_or_the_payload(iam_world: Any) -> None:
    await begin(iam_world, svc(("k1", K1)), payload={"secretTitle": "very confidential plan"}, complete=True)
    with iam_world.pg.connect() as c:
        dump = repr(c.execute("SELECT to_jsonb(r)::text FROM platform.idempotency_records r").fetchall())
        kid = c.execute("SELECT key_id, octet_length(key_digest), octet_length(request_fingerprint) FROM platform.idempotency_records").fetchone()
    assert KEY not in dump and "confidential" not in dump and kid == ("k1", 32, 32)


@pytest.mark.parametrize("bad", ["", "short", "x" * 15, "x" * 129, "has space inside key", "tab\tkey-0123456789abc", "новый-ключ-0123456789"])
async def test_key_format_is_validated_before_any_database_work(iam_world: Any, bad: str) -> None:
    with pytest.raises(ProblemError) as e:
        await begin(iam_world, svc(("k1", K1)), key=bad)
    assert e.value.code is ErrorCode.VALIDATION_ERROR and rows(iam_world) == 0


async def test_rotation_old_key_keeps_deduplicating_and_new_records_use_the_active_key(iam_world: Any) -> None:
    await begin(iam_world, svc(("k1", K1)), complete=True)
    rotated = svc(("k2", K2), ("k1", K1))  # k2 active, k1 still accepted
    replay = await begin(iam_world, rotated)
    assert replay.outcome is IdempotencyOutcome.REPLAY and rows(iam_world) == 1
    with pytest.raises(ProblemError):
        await begin(iam_world, rotated, payload={"title": "changed"})  # still 409 under the OLD key's fingerprint
    assert (await begin(iam_world, rotated, key="another-client-key-0123456789")).outcome is IdempotencyOutcome.NEW
    with iam_world.pg.connect() as c:
        assert sorted(r[0] for r in c.execute("SELECT key_id FROM platform.idempotency_records").fetchall()) == ["k1", "k2"]


async def test_race_on_the_rotation_boundary_does_not_create_two_records(iam_world: Any) -> None:
    old, new = svc(("k1", K1)), svc(("k2", K2), ("k1", K1))
    factory = create_session_factory(iam_world.engine())
    first = UnitOfWork(factory)
    await first.__aenter__()
    try:
        await first.with_tenant(iam_world.org_a)
        rec1 = await old.begin(first.session, organization_id=iam_world.org_a, project_id=None, actor_type="USER", actor_id=iam_world.user_a, command="createOperation", key=KEY, payload=PAYLOAD)
        second = asyncio.create_task(begin(iam_world, new))  # an instance that already runs with the rotated ring, while the first is still uncommitted
        await asyncio.sleep(0.5)
        assert not second.done()  # serialised by the advisory lock, not racing
    finally:
        await first.__aexit__(None, None, None)
    rec2 = await second
    assert rec1.outcome is IdempotencyOutcome.NEW and rec2.outcome is IdempotencyOutcome.IN_PROGRESS and rows(iam_world) == 1


async def test_a_failed_first_attempt_leaves_no_record_so_the_retry_executes(iam_world: Any) -> None:
    s = svc(("k1", K1))
    with pytest.raises(RuntimeError):
        async with UnitOfWork(create_session_factory(iam_world.engine())) as uow:
            await uow.with_tenant(iam_world.org_a)
            await s.begin(uow.session, organization_id=iam_world.org_a, project_id=None, actor_type="USER", actor_id=iam_world.user_a, command="createOperation", key=KEY, payload=PAYLOAD)
            raise RuntimeError("command failed")
    assert rows(iam_world) == 0
    assert (await begin(iam_world, s)).outcome is IdempotencyOutcome.NEW


def test_keyring_file_loading(tmp_path: Path) -> None:
    f = tmp_path / "ring"
    k = lambda b: base64.b64encode(b).decode()  # noqa: E731
    f.write_text(f"# active first\nk2 {k(K2)}\nk1 {k(K1)}\n")
    ring = load_keyring(load_settings({"AI_RES_IDEMPOTENCY_KEYRING_FILE": str(f)}))
    assert ring.active_id == "k2" and set(ring.keys) == {"k1", "k2"}
    for body in ("", "k1 not-base64!!", f"k1 {k(b'short')}", f"k1 {k(K1)}\nk1 {k(K2)}", f"bad id {k(K1)} extra", "k/1 " + k(K1)):
        f.write_text(body)
        with pytest.raises(ConfigError):
            load_keyring(load_settings({"AI_RES_IDEMPOTENCY_KEYRING_FILE": str(f)}))
    with pytest.raises(ConfigError):
        load_keyring(load_settings({}))
