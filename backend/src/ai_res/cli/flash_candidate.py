"""One synthetic candidate case; dry-run default, trusted host hook only.

No credential/account/tariff/approval arguments exist. The separate development
host composition supplies execution dependencies and concrete activation checks;
without it --execute refuses before DB/network/file creation. No product factory
or ordinary ModelProfile is used by this command.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest, CandidateRunner, CandidateRunResult

_FILES = ("backend/pyproject.toml", "backend/uv.lock", "infra/compose.llm-poc.yaml",
          "infra/llm_poc/relay.py", "infra/llm_poc/start-bifrost.sh", "infra/llm_poc/config.template.json",
          "infra/llm_poc/pricing.json", "infra/llm_poc/model-parameters.json", "infra/llm_poc/mcp-library.json",
          "contracts/internal/llm-observed-identity.v0.1.schema.json", "contracts/internal/llm-observed-identity.v0.2.schema.json",
          "contracts/internal/flash-candidate-control.v0.1.schema.json",
          "infra/llm_poc/bifrost_patch/fingerprint.patch", "infra/llm_poc/bifrost_patch/build.py",
          "infra/llm_poc/bifrost_patch/manifest.json", "infra/llm_poc/bifrost_patch/Dockerfile",
          "infra/llm_poc/bifrost_patch/headless-index.html",
          "infra/llm_poc/bifrost_integrity/integrity.patch", "infra/llm_poc/bifrost_integrity/build.py",
          "infra/llm_poc/bifrost_integrity/manifest.json", "infra/llm_poc/bifrost_integrity/Dockerfile",
          "infra/llm_poc/bifrost_integrity/start-candidate.sh")
_NON_SOURCE_DIRS = frozenset({"__pycache__", "secrets", "credentials", "artifacts", "evidence", "uploads", "reports", "build", "dist", "node_modules"})
# Local WORKING input bounds, not product capacity, retention or SLO decisions.
SOURCE_MAX_FILES = 2048
SOURCE_MAX_ENTRIES = 4096
SOURCE_MAX_TOTAL_BYTES = 67_108_864
SOURCE_MAX_FILE_BYTES = 8_388_608


@dataclass(frozen=True, slots=True)
class CandidateSourceBinding:
    code_revision: str
    source_tree_sha256: str


def _git_head(root: Path) -> str:
    try:
        # Host environment overrides must not point the provenance read at a
        # different checkout/configuration. No index refresh/locks are needed.
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        result = subprocess.run(["git", "--no-optional-locks", "rev-parse", "--show-toplevel", "--verify", "HEAD"],  # noqa: S603,S607
                                cwd=root, env=env, capture_output=True, check=True, timeout=5)
        actual_root, head = result.stdout.decode("utf-8").strip().splitlines()
        if Path(actual_root).resolve() != root.resolve():
            raise CandidateRunDenied("BINDING_MISMATCH")
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise CandidateRunDenied("BINDING_MISMATCH") from None
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise CandidateRunDenied("BINDING_MISMATCH")
    return head


def _source_bytes(path: Path, remaining_bytes: int = SOURCE_MAX_FILE_BYTES) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        limit = min(SOURCE_MAX_FILE_BYTES, remaining_bytes)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise CandidateRunDenied("BINDING_MISMATCH")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            content = source.read(limit + 1)
        if len(content) > limit:
            raise CandidateRunDenied("BINDING_MISMATCH")
        return content
    except OSError:
        raise CandidateRunDenied("BINDING_MISMATCH") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def source_binding(root: Path) -> CandidateSourceBinding:
    """Hash the actual bounded candidate source set, including dirty/new files.

    This is explicitly a relevant-source tree, not a whole-workspace snapshot.
    Documents, .git, environment/mounted secrets, caches and artifacts are excluded.
    No git index writes or external processes beyond read-only rev-parse occur.
    """
    paths: set[Path] = set()
    try:
        source_root = root / "backend/src/ai_res"
        directories = [source_root]
        entries = 0
        while directories:
            directory = directories.pop()
            if directory.is_symlink():
                raise CandidateRunDenied("BINDING_MISMATCH")
            # scandir errors propagate. os.walk's default onerror behavior would
            # otherwise silently turn an unreadable subtree into a partial hash.
            with os.scandir(directory) as listing:
                for entry in listing:
                    entries += 1
                    if entries > SOURCE_MAX_ENTRIES:
                        raise CandidateRunDenied("BINDING_MISMATCH")
                    path = Path(entry.path)
                    if entry.name.startswith(".") or (entry.name.casefold() in _NON_SOURCE_DIRS
                                                       and path.relative_to(source_root).as_posix() != "platform/artifacts"):
                        continue
                    if entry.is_symlink():
                        raise CandidateRunDenied("BINDING_MISMATCH")
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(path)
                    elif path.suffix == ".py":
                        paths.add(path)
                        if len(paths) > SOURCE_MAX_FILES:
                            raise CandidateRunDenied("BINDING_MISMATCH")
        # Non-code inputs are exact reviewed paths, never directory discovery.
        paths.update(root / relative for relative in _FILES)
        if not paths or len(paths) > SOURCE_MAX_FILES:
            raise CandidateRunDenied("BINDING_MISMATCH")
        digest = hashlib.sha256(b"flash-candidate-source-tree/0.1\0")
        total_bytes = 0
        for path in sorted(paths):
            # Do not follow a substituted ancestor symlink to external material.
            if any((root / ancestor).is_symlink() for ancestor in path.relative_to(root).parents if ancestor != Path(".")):
                raise CandidateRunDenied("BINDING_MISMATCH")
            encoded_path = path.relative_to(root).as_posix().encode("utf-8")
            data = _source_bytes(path, SOURCE_MAX_TOTAL_BYTES - total_bytes)
            total_bytes += len(data)
            digest.update(len(encoded_path).to_bytes(4, "big") + encoded_path + len(data).to_bytes(8, "big") + hashlib.sha256(data).digest())
        return CandidateSourceBinding(_git_head(root), digest.hexdigest())
    except (OSError, UnicodeError, ValueError):
        raise CandidateRunDenied("BINDING_MISMATCH") from None


HostFactory = Callable[[CandidateSourceBinding, Path], AbstractAsyncContextManager[tuple[CandidateRunner, CandidateRunManifest]]]


def main(argv: Sequence[str] | None = None, *, host_factory: HostFactory | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai_res.cli.flash_candidate", description="One synthetic candidate case; dry run unless explicitly executed.")
    parser.add_argument("--case", required=True, choices=("TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--evidence-file", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout_seconds) or not 0 < args.timeout_seconds <= 30:
            raise CandidateRunDenied()
        body = build_candidate_body(args.case, uuid4())
        if not args.execute:
            print(json.dumps({"version": "flash-candidate-cli/0.1", "mode": "DRY_RUN", "caseRef": body.case_ref,
                              "codecVersion": body.codec_version, "bodySha256": body.body_sha256, "payloadBytes": body.payload_bytes,
                              "stream": body.stream, "maxOutputTokens": body.max_output_tokens,
                              }, sort_keys=True))
            return 0
        if host_factory is None:
            raise CandidateRunDenied("HOST_UNCONFIGURED")
        if args.evidence_file is None:
            raise CandidateRunDenied("EVIDENCE_UNAVAILABLE")
        source = source_binding(Path(__file__).resolve().parents[4])
        factory = host_factory

        async def execute() -> CandidateRunResult:
            # The host owns probe/engine lifetimes, including construction and
            # execution failures. The runner does not close injected ports.
            async with factory(source, args.evidence_file) as (runner, manifest):
                if manifest.code_revision != source.code_revision or manifest.source_tree_sha256 != source.source_tree_sha256:
                    raise CandidateRunDenied("BINDING_MISMATCH")
                return await runner.run(body, manifest, timeout_seconds=args.timeout_seconds)

        result = asyncio.run(execute())
        print(json.dumps({"version": "flash-candidate-cli/0.1", "mode": "EVIDENCE_RECORDED", "attemptId": str(result.attempt_id),
                          "outcome": result.evidence.outcome.value}, sort_keys=True))
        return 0
    except CandidateRunDenied as error:
        print(f"candidate refused: {error.code}", file=sys.stderr)
        return 2
    except Exception:  # No traceback/SQL/provider/credential repr at this operator boundary.
        print("candidate failed: details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
