#!/usr/bin/env python3
"""Verifies that every `image: name:tag@sha256:...` / `FROM name:tag@sha256:...` pin still resolves to that digest in the registry
(catches typos and tag moves; DOC-015 §12.2, THR-017). Needs network + docker buildx. Prints references only."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [*ROOT.glob("infra/compose*.yaml"), *ROOT.glob("infra/images/**/Dockerfile"), *ROOT.glob("backend/Dockerfile")]
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9./_-]*:[A-Za-z0-9._-]+)@(sha256:[0-9a-f]{64})")


def resolve(ref: str) -> str | None:
    res = subprocess.run(["docker", "buildx", "imagetools", "inspect", ref], capture_output=True, text=True, check=False)  # noqa: S603, S607
    m = re.search(r"^Digest:\s+(sha256:[0-9a-f]{64})", res.stdout, re.M)
    return m.group(1) if m else None


def main() -> int:
    pins = {m.groups() for f in SOURCES for m in PIN.finditer(f.read_text())}
    if len(pins) < 10:
        print(f"FAIL: only {len(pins)} pinned images found (expected >= 10): refusing to pass vacuously")
        return 1
    bad = 0
    for ref, want in sorted(pins):
        got = resolve(ref)
        ok = got == want
        bad += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {ref}" + ("" if ok else f" pinned={want} registry={got}"))
    print(f"{len(pins)} pinned images, {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
