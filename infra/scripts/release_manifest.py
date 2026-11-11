#!/usr/bin/env python3
"""Generates a Release Manifest skeleton (DOC-015 §12.3) from the rendered Compose model: images, registry digests, compose hash, source
commit and SBOM hashes when present. Signing/verification and migration versions are NOT produced yet and are reported as such.
Usage: release_manifest.py [-o infra/releases/release-manifest.json]"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path

import check_compose as cc

INFRA = Path(__file__).resolve().parent.parent
FILES = ["compose.yaml", "compose.dev.yaml"]
DIGEST = re.compile(r"@(sha256:[0-9a-f]{64})$")


def build(model: dict, rendered: str, commit: str | None, dirty: bool, sbom_dir: Path) -> dict:
    services = []
    for name, svc in sorted(model["services"].items()):
        ref = svc["image"]
        m = DIGEST.search(ref)
        sbom = sbom_dir / (re.sub(r"[/:]", "_", DIGEST.sub("", ref)) + ".spdx.json")
        services.append({
            "name": name,
            "image": DIGEST.sub("", ref),
            "digest": m.group(1) if m else None,
            "origin": "third-party" if m else "built",
            "sbom_sha256": hashlib.sha256(sbom.read_bytes()).hexdigest() if sbom.is_file() else None,
            "signature_verified": False,
        })
    return {
        "manifest_version": "0.1",
        "release_id": f"dev-{commit[:12] if commit else 'unknown'}{'-dirty' if dirty else ''}",
        "ai_res_version": None,
        "release_channel": "dev",
        "created_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": commit,
        "source_tree_dirty": dirty,
        "compose": {"files": FILES, "rendered_sha256": hashlib.sha256(rendered.encode()).hexdigest()},
        "services": services,
        "config_schema_versions": {},
        "known_limitations": ["image signatures not verified", "no DB migration versions (S04+)", "third-party image findings are report-only (ADR-043)"],
    }


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=INFRA, capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603, S607


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", default=str(INFRA / "releases" / "release-manifest.json"))
    out = Path(ap.parse_args().o)
    model = cc.load_model(FILES, INFRA)
    rendered = json.dumps(model, sort_keys=True)
    commit = git("rev-parse", "HEAD") or None
    valid_commit = commit if commit and re.fullmatch(r"[0-9a-f]{40}", commit) else None
    manifest = build(model, rendered, valid_commit, bool(git("status", "--porcelain")), INFRA / "releases" / "sbom")
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out} ({len(manifest['services'])} services)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
