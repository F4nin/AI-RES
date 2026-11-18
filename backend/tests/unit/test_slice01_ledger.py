"""Real protected files/processes; synthetic accounting facts, no provider calls."""
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.slice01 import ledger as module
from scripts.slice01.ledger import RESERVED_COST, TOKEN_BOUND, SliceLedger, SliceLedgerError

from ai_res.llm.budget import Reservation
from ai_res.llm.errors import BudgetExhausted

MANIFEST = "a" * 64
BACKEND = Path(__file__).resolve().parents[2]


def requests(count=4):
    return {f"slice01-{i}": {"bodySha256": hashlib.sha256(f"fixture-body-{i}".encode()).hexdigest(), "payloadBytes": 128}
            for i in range(count)}


@pytest.fixture
def file(tmp_path):
    tmp_path.chmod(0o700)
    return tmp_path / "budget.jsonl"


@pytest.fixture
def ledger(file):
    return SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=requests())


async def reserve(ledger, ref="slice01-0"):
    return await ledger.reserve(ref, tokens=10, cost=Decimal("0.000001"), currency="USD")


async def claim(ledger, ref="slice01-0"):
    reservation = await reserve(ledger, ref)
    await ledger.arm(ref)
    assert await ledger.claim(ref, requests()[ref]["bodySha256"]) == reservation
    return reservation


def test_initialization_is_explicit_private_immutable_and_never_resets(file):
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256=MANIFEST)
    assert not file.exists()
    ledger = SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=requests())
    assert ledger.path == file
    assert file.stat().st_mode & 0o777 == 0o600
    assert file.with_name(file.name + ".head").stat().st_mode & 0o777 == 0o600
    original = file.read_bytes()
    with pytest.raises(SliceLedgerError, match="ALREADY_INITIALIZED"):
        SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=requests())
    assert file.read_bytes() == original
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256="b" * 64)


async def test_caller_underestimate_cannot_reduce_conservative_reservation(ledger):
    r = await reserve(ledger)
    assert r.tokens == TOKEN_BOUND == 2_002_048 and r.cost == Decimal("0.6024576")
    balance = await ledger.balance()
    assert balance.used_or_reserved == RESERVED_COST and balance.remaining == Decimal("9.3975424")
    assert balance.pending and balance.attempts == 1


@pytest.mark.parametrize("change", [{"currency": "EUR"}, {"cost": None}, {"cost": Decimal("NaN")},
                                    {"cost": Decimal("-1")}, {"tokens": True}, {"tokens": TOKEN_BOUND + 1}])
async def test_unenforceable_cost_or_invalid_arguments_never_reserve(ledger, change):
    values = {"tokens": 1, "cost": Decimal(0), "currency": "USD"} | change
    with pytest.raises(SliceLedgerError):
        await ledger.reserve("slice01-0", **values)
    assert (await ledger.balance()).attempts == 0


async def test_unknown_request_and_request_reuse_refused_across_restart(ledger, file):
    with pytest.raises(SliceLedgerError, match="REQUEST_NOT_ALLOWED"):
        await reserve(ledger, "slice01-not-allowed")
    r = await reserve(ledger)
    await ledger.release(r)
    reopened = SliceLedger(file, manifest_sha256=MANIFEST)
    with pytest.raises(SliceLedgerError, match="REQUEST_REUSED"):
        await reserve(reopened)
    assert (await reopened.balance()).used_or_reserved == 0


async def test_reserved_money_does_not_authorize_dispatch(ledger):
    await reserve(ledger)
    with pytest.raises(SliceLedgerError, match="CLAIM_REFUSED"):
        await ledger.claim("slice01-0", requests()["slice01-0"]["bodySha256"])
    await ledger.arm("slice01-0")
    with pytest.raises(SliceLedgerError, match="CLAIM_REFUSED"):
        await ledger.claim("slice01-0", "b" * 64)
    await ledger.claim("slice01-0", requests()["slice01-0"]["bodySha256"])
    with pytest.raises(SliceLedgerError, match="CLAIM_REFUSED"):
        await ledger.claim("slice01-0", requests()["slice01-0"]["bodySha256"])


@pytest.mark.parametrize("offset", [-1, 30, 31])
async def test_arm_expiry_and_clock_reversal_refuse_claim(ledger, file, offset):
    now = [datetime(2026, 11, 18, tzinfo=UTC)]
    timed = SliceLedger(file, manifest_sha256=MANIFEST, clock=lambda: now[0])
    r = await reserve(timed)
    await timed.arm(r.scope)
    now[0] += timedelta(seconds=offset)
    with pytest.raises(SliceLedgerError, match="CLAIM_REFUSED"):
        await timed.claim(r.scope, requests()[r.scope]["bodySha256"])
    assert (await timed.balance()).pending
    # The durable state proves no claim occurred: releasing cannot refund a
    # dispatched call. The consumed request reference still cannot be reused.
    await timed.release(r)
    assert (await timed.balance()).used_or_reserved == 0


@pytest.mark.parametrize("ttl", [0, -1, 31, float("nan"), float("inf"), True])
async def test_arm_bound_is_not_caller_extensible(ledger, ttl):
    await reserve(ledger)
    with pytest.raises(SliceLedgerError):
        await ledger.arm("slice01-0", ttl_seconds=ttl)


async def test_known_relay_settlement_and_gateway_repeat_are_idempotent(ledger, file):
    r = await claim(ledger)
    await ledger.settle_usage(r, input_tokens=7, output_tokens=3)
    size = file.stat().st_size
    await ledger.settle(r, tokens=10, cost=Decimal("0.0000057"))
    assert file.stat().st_size == size
    balance = await SliceLedger(file, manifest_sha256=MANIFEST).balance()
    assert balance.used_or_reserved == Decimal("0.0000057") and not balance.pending and not balance.blocked
    await reserve(ledger, "slice01-1")


async def test_generic_budget_port_settle_records_exact_known_token_split(ledger):
    r = await claim(ledger)
    await ledger.settle(r, tokens=10, cost=Decimal("0.0000057"))
    await ledger.settle_usage(r, input_tokens=7, output_tokens=3)
    assert (await ledger.balance()).used_or_reserved == Decimal("0.0000057")


async def test_full_maximum_known_usage_remains_known_on_identical_gateway_acknowledgement(ledger, file):
    r = await claim(ledger)
    await ledger.settle_usage(r, input_tokens=2_000_000, output_tokens=2048)
    size = file.stat().st_size
    await ledger.settle(r, tokens=r.tokens, cost=r.cost)
    assert file.stat().st_size == size
    balance = await ledger.balance()
    assert balance.used_or_reserved == RESERVED_COST and not balance.blocked


async def test_unknown_consumes_full_reserve_and_blocks_future_attempts_after_restart(ledger, file):
    r = await claim(ledger)
    await ledger.settle_unknown(r)
    reopened = SliceLedger(file, manifest_sha256=MANIFEST)
    await reopened.settle(r, tokens=r.tokens, cost=r.cost)
    balance = await reopened.balance()
    assert balance.used_or_reserved == RESERVED_COST and balance.blocked and not balance.pending
    with pytest.raises(SliceLedgerError, match="ACCOUNT_BLOCKED"):
        await reserve(reopened, "slice01-1")
    with pytest.raises(SliceLedgerError, match="RELEASE_REFUSED"):
        await reopened.release(r)
    with pytest.raises(SliceLedgerError):
        await reopened.arm("slice01-1")


async def test_settlement_cannot_precede_durable_claim_or_refund_one(ledger):
    r = await reserve(ledger)
    with pytest.raises(SliceLedgerError, match="SETTLEMENT_REFUSED"):
        await ledger.settle_unknown(r)
    await ledger.arm(r.scope)
    await ledger.claim(r.scope, requests()[r.scope]["bodySha256"])
    with pytest.raises(SliceLedgerError, match="RELEASE_REFUSED"):
        await ledger.release(r)
    assert (await ledger.balance()).used_or_reserved == RESERVED_COST


async def test_conflicting_settlement_is_sticky_block_and_never_refunds(ledger, file):
    r = await claim(ledger)
    await ledger.settle_usage(r, input_tokens=8, output_tokens=2)
    with pytest.raises(SliceLedgerError, match="SETTLEMENT_CONFLICT"):
        await ledger.settle_usage(r, input_tokens=0, output_tokens=0)
    reopened = SliceLedger(file, manifest_sha256=MANIFEST)
    balance = await reopened.balance()
    assert balance.blocked and balance.used_or_reserved == Decimal("0.0000048")
    with pytest.raises(SliceLedgerError, match="ACCOUNT_BLOCKED"):
        await reserve(reopened, "slice01-1")


@pytest.mark.parametrize("inp,out", [(2_000_001, 0), (0, 2049), (-1, 0), (False, 0)])
async def test_invalid_or_overrun_usage_blocks_without_releasing_reserve(ledger, inp, out):
    r = await claim(ledger)
    with pytest.raises(SliceLedgerError, match="INVALID_USAGE"):
        await ledger.settle_usage(r, input_tokens=inp, output_tokens=out)
    balance = await ledger.balance()
    assert balance.used_or_reserved == RESERVED_COST and balance.blocked


async def test_one_immutable_global_cost_ceiling_covers_different_request_scopes(file):
    allowed = requests(20)
    ledger = SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=allowed)
    for i in range(16):
        ref = f"slice01-{i}"
        r = await reserve(ledger, ref)
        await ledger.arm(ref)
        await ledger.claim(ref, allowed[ref]["bodySha256"])
        await ledger.settle_usage(r, input_tokens=2_000_000, output_tokens=2047)
    with pytest.raises(BudgetExhausted):
        await reserve(SliceLedger(file, manifest_sha256=MANIFEST), "slice01-16")
    assert (await ledger.balance()).used_or_reserved == Decimal("9.6393024")


@pytest.mark.parametrize("damage", ["partial", "full-line-tail", "bytes", "head-missing", "head-shared", "head-symlink"])
async def test_corruption_and_truncation_fail_closed(ledger, file, damage):
    await reserve(ledger)
    head = file.with_name(file.name + ".head")
    if damage == "partial":
        file.write_bytes(file.read_bytes()[:-3])
    elif damage == "full-line-tail":
        file.write_bytes(file.read_bytes().splitlines(keepends=True)[0])
    elif damage == "bytes":
        file.write_bytes(file.read_bytes().replace(b'"maxCost":"10"', b'"maxCost":"20"'))
    elif damage == "head-missing":
        head.unlink()
    elif damage == "head-shared":
        head.chmod(0o640)
    else:
        target = file.parent / "other-head"
        head.rename(target)
        head.symlink_to(target)
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256=MANIFEST)


@pytest.mark.parametrize("unsafe", ["file-shared", "file-symlink", "file-hardlink", "directory-shared", "directory-symlink"])
def test_unsafe_file_and_directory_are_refused(ledger, file, tmp_path, unsafe):
    if unsafe == "file-shared":
        file.chmod(0o640)
    elif unsafe == "file-symlink":
        target = tmp_path / "target"
        file.rename(target)
        file.symlink_to(target)
    elif unsafe == "file-hardlink":
        os.link(file, tmp_path / "linked")
    elif unsafe == "directory-shared":
        tmp_path.chmod(0o750)
    else:
        link = tmp_path / "parent-link"
        link.symlink_to(tmp_path, target_is_directory=True)
        file = link / file.name
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256=MANIFEST)


@pytest.mark.parametrize("fault", ["partial-write", "fsync", "head-replace"])
async def test_persistence_or_audit_io_failure_never_authorizes_next_dispatch(ledger, file, monkeypatch, fault):
    original_write = module.os.write

    def broken_write(fd, data):
        original_write(fd, data[:7])
        raise OSError("synthetic I/O failure")

    def broken(*args, **kwargs):
        raise OSError("synthetic I/O failure")

    with monkeypatch.context() as patch:
        if fault == "partial-write":
            patch.setattr(module.os, "write", broken_write)
        elif fault == "fsync":
            patch.setattr(module.os, "fsync", broken)
        else:
            patch.setattr(module.os, "replace", broken)
        with pytest.raises(SliceLedgerError):
            await reserve(ledger)
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256=MANIFEST)


WORKER = r'''
import asyncio,json,os,sys
from decimal import Decimal
from pathlib import Path
from scripts.slice01.ledger import SliceLedger,SliceLedgerError
async def main():
 ledger=SliceLedger(Path(sys.argv[1]),manifest_sha256=sys.argv[2])
 ref=sys.argv[3]
 try:
  r=await ledger.reserve(ref,tokens=1,cost=Decimal('0.000001'),currency='USD')
  if sys.argv[4]=='reserve': os._exit(0)
  await ledger.arm(ref)
  await ledger.claim(ref,sys.argv[5])
  if sys.argv[4]=='claim': os._exit(0)
  await ledger.settle_unknown(r)
  os._exit(0)
 except SliceLedgerError as e:
  print(json.dumps({'code':e.code}),flush=True)
  raise SystemExit(2)
asyncio.run(main())
'''


def start_worker(file, ref, mode):
    return subprocess.Popen([sys.executable, "-B", "-c", WORKER, str(file), MANIFEST,
                             ref, mode, requests()[ref]["bodySha256"]], cwd=BACKEND,
                            env={"PATH": os.environ["PATH"], "PYTHONPATH": str(BACKEND), "PYTHONDONTWRITEBYTECODE": "1"},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.mark.parametrize("phase", ["reserve", "claim", "unknown"])
async def test_reservation_claim_and_unknown_survive_abrupt_process_exit(ledger, file, phase):
    process = start_worker(file, "slice01-0", phase)
    out, err = process.communicate(timeout=10)
    assert process.returncode == 0, (out, err)
    reopened = SliceLedger(file, manifest_sha256=MANIFEST)
    balance = await reopened.balance()
    assert balance.used_or_reserved == RESERVED_COST and balance.blocked == (phase == "unknown")
    with pytest.raises(SliceLedgerError):
        await reserve(reopened, "slice01-1")


async def test_concurrent_processes_cannot_reserve_or_claim_same_request_twice(ledger, file):
    workers = [start_worker(file, "slice01-0", "claim") for _ in range(4)]
    outputs = [p.communicate(timeout=10) for p in workers]
    assert sum(p.returncode == 0 for p in workers) == 1, outputs
    assert all(p.returncode in (0, 2) for p in workers)
    balance = await ledger.balance()
    assert balance.attempts == 1 and balance.used_or_reserved == RESERVED_COST and balance.pending


async def test_forged_reservation_receipt_cannot_release_or_settle(ledger):
    r = await claim(ledger)
    forged = Reservation(r.scope, r.token + 1, r.tokens, r.cost)
    with pytest.raises(SliceLedgerError, match="RESERVATION_MISMATCH"):
        await ledger.release(forged)
    with pytest.raises(SliceLedgerError, match="RESERVATION_MISMATCH"):
        await ledger.settle_unknown(forged)
    assert (await ledger.balance()).used_or_reserved == RESERVED_COST


@pytest.mark.parametrize("bad", [{}, {"bad ref": {"bodySha256": "a" * 64, "payloadBytes": 1}},
                                {"valid": {"bodySha256": "not-hash", "payloadBytes": 1}},
                                {"valid": {"bodySha256": "a" * 64, "payloadBytes": 32769}},
                                {"valid": {"bodySha256": "a" * 64, "payloadBytes": True}},
                                {"valid": {"bodySha256": "a" * 64, "payloadBytes": 1, "extra": True}}])
def test_manifest_is_explicit_bounded_and_not_arbitrary_payload_storage(file, bad):
    with pytest.raises(SliceLedgerError):
        SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=bad)
    assert not file.exists()


async def test_ledger_contains_only_metadata_and_no_prompt_or_response(ledger, file):
    await claim(ledger)
    for record in map(json.loads, file.read_text().splitlines()):
        assert set(record) == {"version", "sequence", "previous", "kind", "data", "sha256"}
    raw = file.read_text()
    assert "fixture-body-" not in raw and "prompt" not in raw and "response" not in raw


CHILD = "b" * 64


def version_requests(version, count=2):
    return {f"slice01-v{version}-{i}": {"bodySha256": hashlib.sha256(f"version-{version}-body-{i}".encode()).hexdigest(),
                                      "payloadBytes": 128} for i in range(count)}


async def authorize_version(file, *, parent=MANIFEST, manifest=CHILD, allowed=None):
    return await SliceLedger.authorize_version(file, parent_manifest_sha256=parent, manifest_sha256=manifest,
                                               requests=version_requests(2) if allowed is None else allowed)


async def settle_version_call(ledger, ref, allowed, *, inp=7, out=3):
    r = await reserve(ledger, ref)
    await ledger.arm(ref)
    await ledger.claim(ref, allowed[ref]["bodySha256"])
    await ledger.settle_usage(r, input_tokens=inp, output_tokens=out)
    return r


async def test_authorized_version_preserves_header_every_prior_byte_and_all_spending(ledger, file):
    # Same two-attempt total as the accepted fixture scenario; these are temporary
    # synthetic accounting values, never a copy or mutation of the live wallet.
    await settle_version_call(ledger, "slice01-0", requests(), inp=1000, out=100)
    await settle_version_call(ledger, "slice01-1", requests(), inp=2005, out=335)
    before = file.read_bytes()
    balance = await ledger.balance()
    assert balance.attempts == 2 and balance.used_or_reserved == Decimal("0.0014235")
    child = await authorize_version(file)
    assert file.read_bytes().startswith(before)
    assert await child.balance() == balance
    assert json.loads(file.read_bytes().splitlines()[0])["data"]["manifestSha256"] == MANIFEST
    event = json.loads(file.read_bytes().splitlines()[-1])
    assert event["kind"] == "AUTHORIZE_VERSION"
    assert set(event["data"]) == {"parentManifestSha256", "manifestSha256", "requests", "authorizedAt"}
    reopened = SliceLedger(file, manifest_sha256=CHILD)
    await reserve(reopened, "slice01-v2-0")
    assert (await reopened.balance()).used_or_reserved == Decimal("0.6038811")
    with pytest.raises(SliceLedgerError, match="MANIFEST_MISMATCH"):
        SliceLedger(file, manifest_sha256=MANIFEST)


async def test_old_runtime_objects_cannot_use_any_port_after_version_transition(ledger, file):
    r = await settle_version_call(ledger, "slice01-0", requests())
    child = await authorize_version(file)
    operations = [ledger.balance(), reserve(ledger, "slice01-1"), ledger.arm("slice01-1"),
                  ledger.claim("slice01-1", requests()["slice01-1"]["bodySha256"]), ledger.release(r),
                  ledger.settle_usage(r, input_tokens=7, output_tokens=3), ledger.settle_unknown(r),
                  ledger.settle(r, tokens=10, cost=Decimal("0.0000057"))]
    for operation in operations:
        with pytest.raises(SliceLedgerError, match="MANIFEST_MISMATCH"):
            await operation
    assert not (await child.balance()).blocked
    with pytest.raises(SliceLedgerError, match="REQUEST_NOT_ALLOWED"):
        await reserve(child, "slice01-1")  # Even an unused old allowlist entry is retired.


@pytest.mark.parametrize("phase", ["reserved", "armed", "claimed", "unknown", "blocked"])
async def test_version_authorization_cannot_clear_unresolved_or_blocked_account(ledger, file, phase):
    r = await reserve(ledger)
    if phase != "reserved":
        await ledger.arm(r.scope)
    if phase in {"claimed", "unknown", "blocked"}:
        await ledger.claim(r.scope, requests()[r.scope]["bodySha256"])
    if phase == "unknown":
        await ledger.settle_unknown(r)
    if phase == "blocked":
        with pytest.raises(SliceLedgerError):
            await ledger.settle_usage(r, input_tokens=-1, output_tokens=0)
    before = file.read_bytes()
    with pytest.raises(SliceLedgerError, match="VERSION_REFUSED"):
        await authorize_version(file)
    assert file.read_bytes() == before
    assert (await ledger.balance()).used_or_reserved == RESERVED_COST


@pytest.mark.parametrize("case", ["same-manifest", "bad-manifest", "bad-parent", "reused-ref", "reused-body",
                                 "ambiguous-body", "empty-map", "extra-field"])
async def test_version_authorization_rejects_reuse_ambiguity_and_unbounded_inputs(ledger, file, case):
    allowed, manifest, parent = version_requests(2), CHILD, MANIFEST
    if case == "same-manifest":
        manifest = MANIFEST
    elif case == "bad-manifest":
        manifest = "not-a-hash"
    elif case == "bad-parent":
        parent = "c" * 64
    elif case == "reused-ref":
        allowed = {"slice01-3": version_requests(2)["slice01-v2-0"]}  # Never reserved, still retired forever.
    elif case == "reused-body":
        allowed["slice01-v2-0"]["bodySha256"] = requests()["slice01-3"]["bodySha256"]
    elif case == "ambiguous-body":
        allowed["slice01-v2-1"]["bodySha256"] = allowed["slice01-v2-0"]["bodySha256"]
    elif case == "empty-map":
        allowed = {}
    else:
        allowed["slice01-v2-0"]["maxCost"] = "20"
    before = file.read_bytes()
    with pytest.raises(SliceLedgerError):
        await authorize_version(file, parent=parent, manifest=manifest, allowed=allowed)
    assert file.read_bytes() == before


async def test_version_never_reuses_released_requests_or_previous_manifest(ledger, file):
    await ledger.release(await reserve(ledger))
    with pytest.raises(SliceLedgerError, match="REQUEST_REUSED"):
        await authorize_version(file, allowed={"slice01-0": version_requests(2)["slice01-v2-0"]})
    child = await authorize_version(file)
    before = file.read_bytes()
    with pytest.raises(SliceLedgerError, match="VERSION_REFUSED"):
        await authorize_version(file, parent=CHILD, manifest=MANIFEST, allowed=version_requests(3))
    with pytest.raises(SliceLedgerError, match="MANIFEST_MISMATCH"):
        await authorize_version(file)  # Lost-ACK retry cannot append the version twice.
    assert file.read_bytes() == before and (await child.balance()).attempts == 1


async def test_version_authorization_never_initializes_missing_wallet(file):
    with pytest.raises(SliceLedgerError, match="NOT_INITIALIZED"):
        await authorize_version(file)
    assert not file.exists() and not file.with_name(file.name + ".head").exists()


async def test_global_cap_and_attempt_history_accumulate_across_all_versions(file):
    allowed = version_requests(0, 1)
    current = SliceLedger.initialize(file, manifest_sha256=MANIFEST, requests=allowed)
    manifest = MANIFEST
    for i in range(17):
        if i:
            fresh_manifest = hashlib.sha256(f"manifest-{i}".encode()).hexdigest()
            allowed = version_requests(i, 1)
            current = await authorize_version(file, parent=manifest, manifest=fresh_manifest, allowed=allowed)
            manifest = fresh_manifest
        ref = next(iter(allowed))
        if i == 16:
            with pytest.raises(BudgetExhausted):
                await reserve(current, ref)
        else:
            await settle_version_call(current, ref, allowed, inp=2_000_000, out=2047)
    balance = await current.balance()
    assert balance.cap == Decimal(10) and balance.attempts == 16
    assert balance.used_or_reserved == Decimal("9.6393024") and not balance.pending and not balance.blocked


VERSION_WORKER = r'''
import asyncio,json,os,sys
from pathlib import Path
from scripts.slice01.ledger import SliceLedger,SliceLedgerError
async def main():
 try:
  await SliceLedger.authorize_version(Path(sys.argv[1]),parent_manifest_sha256=sys.argv[2],
   manifest_sha256=sys.argv[3],requests=json.loads(sys.argv[4]))
  print(json.dumps({'manifest':sys.argv[3]}),flush=True)
  os._exit(0)
 except SliceLedgerError as e:
  print(json.dumps({'code':e.code}),flush=True)
  raise SystemExit(2)
asyncio.run(main())
'''


async def test_concurrent_parent_transitions_have_exactly_one_durable_winner(ledger, file):
    workers = []
    for i in range(4):
        manifest = hashlib.sha256(f"race-{i}".encode()).hexdigest()
        workers.append(subprocess.Popen([sys.executable, "-B", "-c", VERSION_WORKER, str(file), MANIFEST, manifest,
                                         json.dumps(version_requests(i + 2))], cwd=BACKEND,
                                        env={"PATH": os.environ["PATH"], "PYTHONPATH": str(BACKEND), "PYTHONDONTWRITEBYTECODE": "1"},
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    outputs = [p.communicate(timeout=10) for p in workers]
    assert sum(p.returncode == 0 for p in workers) == 1, outputs
    assert all(p.returncode in (0, 2) for p in workers), outputs
    winner = next(json.loads(out)["manifest"] for process, (out, _) in zip(workers, outputs, strict=True) if process.returncode == 0)
    records = list(map(json.loads, file.read_text().splitlines()))
    assert len(records) == 2 and records[1]["kind"] == "AUTHORIZE_VERSION"
    reopened = SliceLedger(file, manifest_sha256=winner)
    balance = await reopened.balance()
    assert balance.used_or_reserved == 0 and balance.attempts == 0
    ref = next(iter(records[1]["data"]["requests"]))
    await reserve(reopened, ref)  # Winner survives abrupt process exit with no reinitialization.


@pytest.mark.parametrize("fault", ["partial-write", "fsync", "head-replace"])
async def test_version_audit_io_failure_refuses_both_versions_without_rewriting_history(ledger, file, monkeypatch, fault):
    before = file.read_bytes()
    original_write = module.os.write

    def broken_write(fd, data):
        original_write(fd, data[:7])
        raise OSError("synthetic I/O failure")

    def broken(*args, **kwargs):
        raise OSError("synthetic I/O failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "write" if fault == "partial-write" else "fsync" if fault == "fsync" else "replace",
                      broken_write if fault == "partial-write" else broken)
        with pytest.raises(SliceLedgerError):
            await authorize_version(file)
    assert file.read_bytes().startswith(before)
    for manifest in (MANIFEST, CHILD):
        with pytest.raises(SliceLedgerError):
            SliceLedger(file, manifest_sha256=manifest)


@pytest.mark.parametrize("damage", ["partial-version", "whole-version-tail", "head-missing", "forged-parent", "retired-reserve"])
async def test_version_truncation_and_hash_valid_invalid_transitions_fail_closed(ledger, file, damage):
    await authorize_version(file)
    lines = file.read_bytes().splitlines(keepends=True)
    if damage == "partial-version":
        file.write_bytes(file.read_bytes()[:-3])
    elif damage == "whole-version-tail":
        file.write_bytes(lines[0])
    elif damage == "head-missing":
        file.with_name(file.name + ".head").unlink()
    else:
        records = list(map(json.loads, lines))
        if damage == "forged-parent":
            data = {**records[1]["data"], "parentManifestSha256": "c" * 64}
            records[1] = module._record("AUTHORIZE_VERSION", data, 1, records[0]["sha256"])
        else:
            records.append(module._record("RESERVE", {"requestRef": "slice01-0", "token": 1,
                                                       "tokens": TOKEN_BOUND, "cost": str(RESERVED_COST)},
                                          2, records[-1]["sha256"]))
        raw = b"".join(module._encode(record) + b"\n" for record in records)
        file.write_bytes(raw)
        file.with_name(file.name + ".head").write_bytes(module._encode(module._head(records[-1], len(raw))) + b"\n")
    with pytest.raises(SliceLedgerError):
        SliceLedger(file, manifest_sha256=CHILD)
