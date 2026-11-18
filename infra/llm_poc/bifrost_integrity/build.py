"""Separate ADR137 hardened candidate; preserves the original SDK build/audit.

Uses verified public source and the unchanged ADR135 fingerprint patch, then the
explicit transport integrity patch. Never publishes/retags a product image.
"""
import argparse
import importlib.util
import io
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("bifrost_integrity_base_build", BASE.parent / "bifrost_patch/build.py")
assert SPEC and SPEC.loader
base = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = base
SPEC.loader.exec_module(base)
LABEL = "ai-res.bifrost-integrity.build-sha256"
PATCH_PATHS = {"transports/bifrost-http/server/server.go", "transports/bifrost-http/server/candidate_integrity.go",
               "transports/bifrost-http/server/candidate_integrity_test.go"}


def load_manifest():
    manifest = json.loads(base.read_input(BASE / "manifest.json", 65_536))
    base.require(manifest["version"] == "bifrost-candidate-integrity-build/0.1"
                 and manifest["baseManifestSha256"] == base.sha(base.read_input(base.BASE / "manifest.json", 65_536))
                 and manifest["baseBuildToolSha256"] == base.sha(base.read_input(base.BASE / "build.py", 131_072)))
    original = base.load_manifest()
    base.checked_inputs(original)
    for path, field, limit in (("build.py", "buildToolSha256", 131_072), ("Dockerfile", "dockerfileSha256", 65_536),
                               ("start-candidate.sh", "launcherSha256", 65_536), ("integrity.patch", "patchSha256", 2_097_152)):
        base.require(base.sha(base.read_input(BASE / path, limit)) == manifest[field])
    base.require(base.sha(base.read_input(BASE.parent / "config.template.json", 65_536)) == manifest["templateSha256"])
    patch = base.read_input(BASE / "integrity.patch", 2_097_152)
    paths = re.findall(rb"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE)
    old, new = re.findall(rb"^--- (\S+)$", patch, re.MULTILINE), re.findall(rb"^\+\+\+ (\S+)$", patch, re.MULTILINE)
    base.require(len(paths) == len(PATCH_PATHS) and {left.decode() for left, _ in paths} == PATCH_PATHS
                 and all(left == right for left, right in paths) and len(old) == len(new) == len(paths))
    base.require(all(a in {b"a/" + left, b"/dev/null"} and b == b"b/" + right for (left, right), a, b in zip(paths, old, new, strict=True)))
    return manifest, original


def prepared_files(raw, manifest, original):
    """Base tool already validates source/SDK patch/locks and bounded tar bytes."""
    context = base.build_context(raw, original)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(context)) as archive:
        for member in archive:
            base.require(member.isfile() and 0 <= member.size <= base.MAX_FILE)
            source = archive.extractfile(member)
            base.require(source is not None)
            with source:
                files[member.name] = (source.read(base.MAX_FILE + 1), member.mode)
            base.require(len(files[member.name][0]) == member.size)
    with tempfile.TemporaryDirectory(prefix="bifrost-integrity-patch-") as directory:
        root = Path(directory)
        for name, (content, mode) in files.items():
            if not name.startswith("source/"):
                continue
            path = root / name.removeprefix("source/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(mode)
        patch = root / "integrity.patch"
        patch.write_bytes(base.read_input(BASE / "integrity.patch", 2_097_152))
        base.run(["git", "apply", "--no-index", "--check", "--whitespace=error-all", str(patch)], cwd=root)
        base.run(["git", "apply", "--no-index", "--whitespace=error-all", str(patch)], cwd=root)
        for name in PATCH_PATHS:
            files["source/" + name] = (base.read_input(root / name, base.MAX_FILE), 0o644)
        for name, digest in original["moduleLocks"].items():
            base.require(base.sha(base.read_input(root / name, base.MAX_FILE)) == digest)
        base.require(base.read_input(BASE.parent / "config.template.json", 65_536)
                     in files["source/transports/bifrost-http/server/candidate_integrity.go"][0])
    files["Dockerfile"] = (base.read_input(BASE / "Dockerfile", 65_536), 0o644)
    files["start-candidate.sh"] = (base.read_input(BASE / "start-candidate.sh", 65_536), 0o644)
    files["integrity-manifest.json"] = (base.read_input(BASE / "manifest.json", 65_536), 0o644)
    return files


def build_context(raw, manifest, original):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, (content, mode) in sorted(prepared_files(raw, manifest, original).items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), mode
            archive.addfile(info, io.BytesIO(content))
            base.require(stream.tell() <= base.MAX_SOURCE)
    base.require(stream.tell() <= base.MAX_SOURCE)
    return stream.getvalue()


def provenance(client, image_id, manifest, original):
    proof = base.image_provenance(client, image_id, original)
    container = None
    try:
        container = client.containers.create(image_id, entrypoint=["/bin/true"], command=[], network_mode="none")
        for path, expected in (("/app/start-candidate.sh", base.read_input(BASE / "start-candidate.sh", 65_536)),
                                ("/app/candidate-integrity-build.json", base.read_input(BASE / "manifest.json", 65_536))):
            chunks, _ = container.get_archive(path)
            content = bytearray()
            for chunk in chunks:
                base.require(len(content) + len(chunk) <= 131_072)
                content.extend(chunk)
            with tarfile.open(fileobj=io.BytesIO(content)) as archive:
                items = archive.getmembers()
                base.require(len(items) == 1 and items[0].isfile() and items[0].size == len(expected))
                source = archive.extractfile(items[0])
                base.require(source is not None)
                with source:
                    base.require(source.read(65_537) == expected)
        image = client.images.get(image_id)
        base.require(image.attrs["Config"]["Entrypoint"] == ["/bin/sh", "/app/start-candidate.sh"]
                     and image.attrs["Config"].get("Cmd") in (None, []))
        return {"version": manifest["version"], "imageId": image_id, "baseSource": original["source"],
                "fingerprintPatchSha256": original["patch"]["sha256"], "integrityPatchSha256": manifest["patchSha256"],
                "buildManifestSha256": base.sha(base.read_input(BASE / "manifest.json", 65_536)), **proof}
    finally:
        if container is not None:
            container.remove(v=True)


def build_image(snapshot=None):
    import docker
    manifest, original = load_manifest()
    key = base.sha(base.read_input(BASE / "manifest.json", 65_536))
    tag = "ai-res-bifrost-integrity:" + key
    client = docker.from_env(timeout=1800)
    try:
        try:
            image = client.images.get(tag)
        except docker.errors.ImageNotFound:
            if snapshot is None:
                with tempfile.TemporaryDirectory(prefix="bifrost-integrity-source-") as directory:
                    raw, _ = base.fetch_snapshot(Path(directory) / "source")
            else:
                raw = base.read_input(snapshot, base.MAX_SOURCE)
            try:
                image, _ = client.images.build(fileobj=io.BytesIO(build_context(raw, manifest, original)), custom_context=True,
                    dockerfile="Dockerfile", tag=tag, labels={LABEL: key}, pull=False, rm=True, forcerm=True)
            except docker.errors.BuildError:
                raise base.CandidateBuildError() from None
        base.require(image.labels.get(LABEL) == key and re.fullmatch(r"sha256:[0-9a-f]{64}", image.id))
        return image.id, provenance(client, image.id, manifest, original)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    identifier, proof = build_image(args.snapshot)
    print(json.dumps(proof, indent=2, sort_keys=True))
