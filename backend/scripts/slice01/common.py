"""Fixed SLICE tooling inputs and bounded private artifacts, never product DTOs."""
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_res.llm.adapters.bifrost import BifrostTransport
from ai_res.llm.transport import TransportCall
from ai_res.llm.types import Message, Role

from .requirements import PROMPT_SHA256, ExperimentIds, Source, build_messages

ROOT = Path(__file__).resolve().parents[3]
PROFILE_ID = UUID("01a1ef1f-5182-70f8-8dda-603e33876b8b")
ORGANIZATION_ID = UUID("01a1eef2-08a5-737a-8304-65ed7b5b0538")
OWNER_ID = UUID("01a1eef2-08a5-737a-8304-65eec13a0507")
BIFROST_IMAGE = "sha256:c52717deb74c85d4980e0710464a76942ec091daacdb1e11d266ab1e068864a9"
PRIVATE_ROOT = ROOT / "infra/secrets/slice01"
AUTHORIZATION_ROOT = PRIVATE_ROOT / "authorization-2026-11-18"
DIAGNOSTIC_TEMPLATE = "SLICE-01 bounded synthetic identity probe {request_ref}. Reply exactly OK."
MAX_BYTES = 1_048_576


class SliceRefused(ValueError):
    def __init__(self, code: str = "SLICE_REFUSED") -> None:
        super().__init__(code)


def experiment_version(directory: Path) -> int:
    resolved = directory.resolve()
    if resolved == AUTHORIZATION_ROOT:
        return 1
    if (resolved.parent == AUTHORIZATION_ROOT / "versions" and resolved.name.isdecimal()
            and str(int(resolved.name)) == resolved.name and 2 <= int(resolved.name) <= 1000):
        return int(resolved.name)
    raise SliceRefused("AUTHORIZATION_PATH_REQUIRED")


def wallet_directory(directory: Path, mode: str) -> Path:
    if mode == "fixture":
        return directory / "wallet"
    if mode != "live":
        raise SliceRefused("LIVE_MODE_REQUIRED")
    experiment_version(directory)
    return AUTHORIZATION_ROOT / "wallet"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in values:
        if key in result:
            raise SliceRefused("DUPLICATE_FIELD")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise SliceRefused("NONFINITE_JSON")


def decode(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise SliceRefused("ARTIFACT_TOO_LARGE")
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    canonical(value)  # also refuse invalid Unicode and overflow floats
    return value


def read_owned(path: Path, *, private: bool = True, limit: int = MAX_BYTES) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        mask = 0o077 if private else 0o022
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & mask
                or info.st_nlink != 1 or info.st_size > limit):
            raise SliceRefused("UNTRUSTED_FILE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            result = stream.read(limit + 1)
        if len(result) > limit:
            raise SliceRefused("ARTIFACT_TOO_LARGE")
        return result
    finally:
        os.close(fd)


def write_new(path: Path, value: Any) -> None:
    raw = canonical(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def bundle() -> dict[str, str]:
    return {"version": "slice01-prompts/1", "diagnosticTemplateSha256": digest(DIAGNOSTIC_TEMPLATE.encode()),
            "requirementsTemplateSha256": PROMPT_SHA256}


def messages(plan: dict[str, Any], phase: str) -> tuple[Message, ...]:
    request_ref = plan["phases"][phase]
    if phase == "bootstrap":
        return (Message(Role.USER, DIAGNOSTIC_TEMPLATE.format(request_ref=request_ref)),)
    source = source_from_plan(plan)
    ids = ExperimentIds(UUID(plan["experiment"]["workerRunId"]), UUID(plan["experiment"]["taskId"]))
    return build_messages(source, ids, request_ref)


def source_from_plan(plan: dict[str, Any]) -> Source:
    source = plan["source"]
    return Source(UUID(source["sourceId"]), UUID(source["versionId"]), source["checksum"], source["text"])


def native_body(items: tuple[Message, ...]) -> dict[str, Any]:
    return {"model": "deepseek/deepseek-flash", "messages": [{"role": m.role.value.lower(), "content": m.content} for m in items],
            "stream": False, "max_completion_tokens": 2048, "fallbacks": [], "store": False,
            "thinking": {"type": "disabled"}}


def upstream_body(items: tuple[Message, ...]) -> dict[str, Any]:
    return {"model": "deepseek-flash", "messages": [{"role": m.role.value.lower(), "content": m.content} for m in items],
            "stream": False, "max_tokens": 2048, "thinking": {"type": "disabled"}}


class SliceBifrostTransport(BifrostTransport):
    """Explicit non-thinking observed CHAT in tooling; parent's approval guard stays."""

    def _request(self, call: TransportCall, stream: bool) -> tuple[Any, dict[str, str], bytes]:
        binding, headers, encoded = super()._request(call, stream)
        if stream or call.response_schema is not None or call.tool_definitions is not None:
            raise SliceRefused("CHAT_ONLY")
        data = decode(encoded)
        data["thinking"] = {"type": "disabled"}
        return binding, headers, canonical(data)


def load_plan(directory: Path, *, for_execution: bool = True) -> dict[str, Any]:
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SliceRefused("UNTRUSTED_DIRECTORY")
    plan = decode(read_owned(directory / "plan.json"))
    if not isinstance(plan, dict) or plan.get("version") != "slice01/1":
        raise SliceRefused("PLAN_INVALID")
    recorded = plan["manifestSha256"]
    if digest(canonical({k: v for k, v in plan.items() if k != "manifestSha256"})) != recorded:
        raise SliceRefused("PLAN_CHANGED")
    if not for_execution:
        # Financial status and owned-resource cleanup remain available after expiry.
        # This metadata-only read never grants dispatch or decision authority.
        return plan
    if plan["promptBundle"] != bundle():
        raise SliceRefused("PROMPT_CHANGED")
    if digest(read_owned(Path(__file__).parent.parent / "__init__.py", private=False)) != plan["scriptsInitializerSha256"]:
        raise SliceRefused("SOURCE_CHANGED")
    now = datetime.now(UTC)
    checked = datetime.fromisoformat(plan["tariffCheckedAt"])
    expires = datetime.fromisoformat(plan["expiresAt"])
    if (checked.utcoffset() is None or expires.utcoffset() is None or not checked <= now <= expires
            or (expires - checked).total_seconds() > 3600):
        raise SliceRefused("TARIFF_OR_PLAN_EXPIRED")
    for relative, expected in plan["toolHashes"].items():
        # A closed flat package; the plan may not name arbitrary files.
        if Path(relative).name != relative or not relative.endswith(".py"):
            raise SliceRefused("SOURCE_CHANGED")
        if digest(read_owned(Path(__file__).parent / relative, private=False)) != expected:
            raise SliceRefused("SOURCE_CHANGED")
    return plan
