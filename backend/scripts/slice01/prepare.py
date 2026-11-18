"""Freeze one bounded tooling authorization before containers or paid requests."""
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import docker

from ai_res.modules.model_registry.candidate_host import BIFROST_BIND_PATHS

from .common import (
    AUTHORIZATION_ROOT,
    BIFROST_IMAGE,
    PRIVATE_ROOT,
    PROFILE_ID,
    ROOT,
    SliceRefused,
    bundle,
    canonical,
    digest,
    experiment_version,
    load_plan,
    messages,
    read_owned,
    upstream_body,
    wallet_directory,
    write_new,
)
from .ledger import SliceLedger
from .relay import canonical_body


def _secret(path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_hex(32) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _database_profile(client: Any) -> tuple[str, str, int]:
    # Actual existing API identity/TLS, read-only transaction; never a new login/grant.
    script = '''import asyncio,json,os
from sqlalchemy import text
from ai_res.platform.config import load_settings
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork,create_session_factory
async def go():
 e=create_runtime_engine(load_settings(os.environ))
 try:
  async with UnitOfWork(create_session_factory(e)) as u:
   await u.session.execute(text("SET TRANSACTION READ ONLY"))
   await u.session.execute(text("SELECT set_config('app.model_profile_id','01a1ef1f-5182-70f8-8dda-603e33876b8b',true)"))
   q="SELECT to_jsonb(p)::text,((to_jsonb(p)-'status'-'approved_at'-'approved_by'-'deprecated_at')::text) "
   q+="FROM platform.model_profiles p WHERE id=:p"
   r=(await u.session.execute(text(q),{"p":"01a1ef1f-5182-70f8-8dda-603e33876b8b"})).one()
   cq="SELECT current_generation,blocked FROM platform.model_admission_controls WHERE profile_id=:p"
   c=(await u.session.execute(text(cq),{"p":"01a1ef1f-5182-70f8-8dda-603e33876b8b"})).first()
   pq="SELECT count(*) FROM platform.model_admission_calls WHERE profile_id=:p AND status='IN_FLIGHT'"
   pending=(await u.session.execute(text(pq),{"p":"01a1ef1f-5182-70f8-8dda-603e33876b8b"})).scalar_one()
   if pending or (c is not None and c.blocked): raise ValueError('ADMISSION_BUSY_OR_BLOCKED')
   print(json.dumps([*r,0 if c is None else c.current_generation]))
 finally: await e.dispose()
asyncio.run(go())'''
    result = client.containers.get("ai-res-api-1").exec_run(["python", "-B", "-c", script], demux=True)
    if result.exit_code or result.output[0] is None:
        raise SliceRefused("PROFILE_READ_FAILED")
    profile, immutable, generation = json.loads(result.output[0])
    if type(generation) is not int or generation < 0:
        raise SliceRefused("ADMISSION_INVALID")
    return profile, immutable, generation


def _parent_directory(directory: Path) -> Path:
    version = experiment_version(directory)
    if version == 1:
        raise SliceRefused("PARENT_VERSION_REQUIRED")
    return AUTHORIZATION_ROOT if version == 2 else AUTHORIZATION_ROOT / "versions" / str(version - 1)


def _require_stopped(client: Any, directory: Path) -> None:
    state = decode_runtime(directory)
    for snapshot in state["containers"].values():
        try:
            client.containers.get(snapshot["id"])
        except docker.errors.NotFound:
            continue
        raise SliceRefused("PARENT_RUNTIME_MUST_BE_STOPPED")


def decode_runtime(directory: Path) -> dict[str, Any]:
    from .common import decode
    state: dict[str, Any] = decode(read_owned(directory / "runtime.json"))
    if state.get("version") != "slice01-runtime/1":
        raise SliceRefused("PARENT_RUNTIME_REQUIRED")
    return state


async def activate_version(directory: Path) -> dict[str, Any]:
    """Advance the existing account; never initialize or reset it on this path."""
    plan = load_plan(directory / "config")
    if plan["mode"] != "live":
        raise SliceRefused("LIVE_VERSION_REQUIRED")
    parent = _parent_directory(directory)
    prior = load_plan(parent / "config", for_execution=False)
    if plan["parentManifestSha256"] != prior["manifestSha256"]:
        raise SliceRefused("PARENT_PLAN_CHANGED")
    client = cast(Any, docker).from_env(timeout=30)
    try:
        _require_stopped(client, parent)
        profile, immutable, generation = _database_profile(client)
        if (json.loads(profile)["status"] != "APPROVED" or generation + 1 != plan["admissionGeneration"]
                or digest(immutable.encode()) != plan["immutableProfileSha256"]):
            raise SliceRefused("PROFILE_OR_GENERATION_CHANGED")
    finally:
        client.close()
    wallet = await SliceLedger.authorize_version(wallet_directory(directory, "live") / "ledger.jsonl",
        parent_manifest_sha256=prior["manifestSha256"], manifest_sha256=plan["manifestSha256"], requests=plan["requests"])
    balance = await wallet.balance()
    return {"status": "NEXT_VERSION_AUTHORIZED_SAME_ACCOUNT", "manifestSha256": plan["manifestSha256"],
            "usedOrReservedUSD": str(balance.used_or_reserved), "remainingUSD": str(balance.remaining)}


def prepare(directory: Path, *, mode: str, tariff_checked_at: datetime,
            bifrost_image: str = BIFROST_IMAGE, python_image: str | None = None) -> dict[str, Any]:
    if mode not in {"fixture", "live"}:
        raise SliceRefused("AUTHORIZATION_PATH_REQUIRED")
    version = experiment_version(directory) if mode == "live" else 1
    parent = _parent_directory(directory) if mode == "live" and version > 1 else None
    parent_plan = load_plan(parent / "config", for_execution=False) if parent is not None else None
    now = datetime.now(UTC)
    if (tariff_checked_at.utcoffset() != timedelta(0) or not tariff_checked_at <= now
            or now - tariff_checked_at > timedelta(minutes=10)):
        raise SliceRefused("FRESH_TARIFF_REVIEW_REQUIRED")
    if directory.exists():
        raise SliceRefused("AUTHORIZATION_ALREADY_EXISTS")
    client = cast(Any, docker).from_env(timeout=30)
    try:
        bf_image = client.images.get(bifrost_image).id
        py_image = client.images.get(python_image or "ai-res/api:dev").id
        if not bf_image.startswith("sha256:") or not py_image.startswith("sha256:"):
            raise SliceRefused("IMMUTABLE_IMAGE_REQUIRED")
        if mode == "live" and bf_image != BIFROST_IMAGE:
            raise SliceRefused("REVIEWED_BIFROST_IMAGE_REQUIRED")
        if mode == "live":
            profile, immutable, generation = _database_profile(client)
            expected_status = "CANDIDATE" if version == 1 else "APPROVED"
            if json.loads(profile)["status"] != expected_status or (version == 1 and generation != 0):
                raise SliceRefused("PROFILE_STATUS_OR_GENERATION_INVALID")
            if parent is not None:
                _require_stopped(client, parent)
        else:
            fixture_profile = json.loads((ROOT / "docs/implementation/reviews/SLICE-01_CANDIDATE_CONFIGURATION.json").read_text())
            profile = fixture_profile["profileSnapshot"]
            immutable = "fixture-only-not-a-database-claim"
            generation = 0
    finally:
        client.close()
    if mode == "live":
        PRIVATE_ROOT.mkdir(mode=0o700, exist_ok=True)
        if PRIVATE_ROOT.is_symlink() or PRIVATE_ROOT.stat().st_uid != os.getuid() or PRIVATE_ROOT.stat().st_mode & 0o077:
            raise SliceRefused("UNTRUSTED_DIRECTORY")
    directory.mkdir(mode=0o700, parents=True)
    for name in ("config", "credentials", "results"):
        (directory / name).mkdir(mode=0o700)
    if mode == "fixture" or version == 1:
        (directory / "wallet").mkdir(mode=0o700)
    (directory / "config/native").mkdir(mode=0o700)
    for target, source in BIFROST_BIND_PATHS.items():
        frozen = directory / "config/native" / Path(target).name
        frozen.write_bytes(read_owned(ROOT / source, private=False))
        frozen.chmod(0o700 if target.endswith(".sh") else 0o600)
    contract = ROOT / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json"
    frozen_contract = directory / "config/worker-contract.json"
    frozen_contract.write_bytes(read_owned(contract, private=False))
    frozen_contract.chmod(0o600)
    for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth", "fixture_provider_key"):
        _secret(directory / "credentials" / name)
    template = (ROOT / "infra/llm_poc/config.template.json").read_text()
    for name, placeholder in (("bifrost_admin_password", "$BIFROST_ADMIN_PASSWORD"),
                              ("bifrost_virtual_key", "$BIFROST_VIRTUAL_KEY"), ("llm_relay_auth", "$LLM_RELAY_AUTH")):
        template = template.replace(placeholder, read_owned(directory / "credentials" / name).decode().strip())
    source_root = ROOT / "backend/tests/fixtures/slice01"
    source_text = (source_root / "realworld-routing.md").read_text()
    source_meta = json.loads((source_root / "source.json").read_text())
    if (digest(source_text.encode()) != source_meta["sourceSha256"] or source_meta["license"] != "MIT"
            or digest((source_root / "REALWORLD_LICENSE").read_bytes()) != source_meta["licenseSha256"]):
        raise SliceRefused("SOURCE_LICENSE_OR_CHECKSUM_CHANGED")
    policy = json.loads((ROOT / "docs/implementation/reviews/SLICE-01_OWNER_POLICY.json").read_text())
    policy["version"] = "2026-11-18.143"
    policy["actions"]["slice01.invoke"] = {"resourceType": "SLICE01_REQUEST", "allow": {"orgRoles": ["ORGANIZATION_OWNER"]},
                                           "requiresMfa": True, "humanOnly": True, "auditAllow": True}
    policy_raw = canonical(policy) + b"\n"
    policy_path = directory / "config/policy.json"
    policy_path.write_bytes(policy_raw)
    policy_path.chmod(0o600)
    code = Path(__file__).parent
    library = ROOT / "backend/src/ai_res"
    tool_hashes = {p.name: digest(p.read_bytes()) for p in sorted(code.glob("*.py"))}
    library_sha = digest(canonical([(p.relative_to(library).as_posix(), digest(p.read_bytes())) for p in sorted(library.rglob("*.py"))]))
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, env=git_env,  # noqa:S607
                              check=True, capture_output=True, text=True).stdout.strip()  # noqa:S603,S607
    plan: dict[str, Any] = {"version": "slice01/1", "mode": mode, "authorization": "SLICE01_TEST_2026_11_18",
        "experimentVersion": str(version), "profileStatus": json.loads(profile)["status"], "admissionGeneration": generation + 1,
        "parentManifestSha256": None if parent_plan is None else parent_plan["manifestSha256"],
        "ceilingUSD": "10", "profileId": str(PROFILE_ID), "profileVersion": 1, "profileSnapshot": profile,
        "immutableProfileSha256": digest(immutable.encode()), "toolHashes": tool_hashes, "librarySha256": library_sha,
        "scriptsInitializerSha256": digest(read_owned(code.parent / "__init__.py", private=False)),
        "bifrostImage": bf_image, "pythonImage": py_image, "nativeConfigSha256": digest(template.encode()),
        "nativeInputs": {target: digest((ROOT / source).read_bytes()) for target, source in BIFROST_BIND_PATHS.items()},
        "workerContractSha256": digest((ROOT / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json").read_bytes()),
        "policySha256": digest(policy_raw), "promptBundle": bundle(),
        "tariffSource": "https://api-docs.deepseek.com/quick_start/pricing/", "inputPerMillionUSD": "0.30", "outputPerMillionUSD": "1.20",
        "tariffCheckedAt": tariff_checked_at.isoformat(), "expiresAt": (tariff_checked_at + timedelta(hours=1)).isoformat(),
        "source": {"sourceId": str(uuid4()), "versionId": str(uuid4()), "checksum": source_meta["sourceSha256"],
                   "text": source_text, "license": "MIT", "provenance": source_meta},
        "experiment": {"workerRunId": str(uuid4()), "taskId": str(uuid4()), "domainObjectsCreated": False},
        "phases": {"bootstrap": "slice01-probe-" + uuid4().hex, "run": "slice01-run-" + uuid4().hex}}
    plan["requests"] = {}
    for phase, request_ref in plan["phases"].items():
        body = canonical_body(canonical(upstream_body(messages(plan, phase))))
        plan["requests"][request_ref] = {"bodySha256": digest(body), "payloadBytes": len(body)}
    config_sha = digest(canonical(plan))
    plan["managedVersions"] = {"codeRevision": revision, "profileId": str(PROFILE_ID), "profileVersion": 1,
                               "configSha256": config_sha, "promptSha256": digest(canonical(bundle())), "toolsSha256": None}
    plan["manifestSha256"] = digest(canonical(plan))
    write_new(directory / "config/plan.json", plan)
    if mode == "fixture" or version == 1:
        SliceLedger.initialize(wallet_directory(directory, mode) / "ledger.jsonl",
            manifest_sha256=plan["manifestSha256"], requests=plan["requests"])
    return {"directory": str(directory), "manifestSha256": plan["manifestSha256"], "mode": mode,
            "requests": len(plan["requests"]), "providerCalls": 0, "requiresAccountActivation": parent is not None}
