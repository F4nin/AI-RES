"""ADR135 local candidate build. No image publication, model calls or approval.

Run with the repository's locked backend Python environment. Source acquisition
is a verified Git sparse snapshot, NOT an official-full-archive checksum. No
project source is sent to GitHub: only the fixed public repository/commit is
fetched. Docker receives only the public SDK snapshot and this reviewed patch.
"""
import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

BASE = Path(__file__).resolve().parent
COMMIT = "7cb75fb2f8276ca48d0792c857fecb67b8879e2f"
TREE = "fe862c3b2236a41ae4f3bc969f992500e2cb22d0"
ORIGIN = "https://github.com/maximhq/bifrost.git"
MAX_SOURCE = 134_217_728
MAX_FILE = 8_388_608
MAX_BINARY = 1_073_741_824
CACHE_LABEL = "ai-res.bifrost-candidate.build-inputs-sha256"


class CandidateBuildError(RuntimeError):
    def __init__(self):
        super().__init__("Candidate build refused: source, patch, locks or provenance failed validation.")


def require(condition):
    if not condition:
        raise CandidateBuildError()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_input(path, limit):
    """Bound even manifest/ignore/patch reads before trusting their contents."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit)
            raw = source.read(limit + 1)
            require(len(raw) == info.st_size and len(raw) <= limit)
            return raw
    except (OSError, ValueError):
        raise CandidateBuildError() from None


def load_manifest():
    value = json.loads(read_input(BASE / "manifest.json", 65_536).decode("utf-8"))
    require(value["version"] == "bifrost-candidate-build/0.1")
    source = value["source"]
    require(source["sourceKind"] == "verified-git-sparse" and source["origin"] == ORIGIN
            and source["commit"] == COMMIT and source["tree"] == TREE
            and source["selection"] == ["LICENSE", "core/**", "transports/**"])
    return value


def selected_path(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and "\\" not in name and ".." not in path.parts and name == path.as_posix()
            and (name == "LICENSE" or name.startswith(("core/", "transports/"))))


def verify_snapshot(raw, manifest):
    """Checksum, selection, modes and locks all bind the same exact tar bytes."""
    source = manifest["source"]
    require(type(raw) is bytes and len(raw) <= MAX_SOURCE and len(raw) == source["archiveBytes"] and sha(raw) == source["archiveSha256"])
    files, size = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                require(member.isfile() and selected_path(member.name) and member.name not in files
                        and member.mode in {0o644, 0o755} and 0 <= member.size <= MAX_FILE and len(files) < 4096)
                stream = archive.extractfile(member)
                require(stream is not None)
                with stream:
                    content = stream.read(MAX_FILE + 1)
                require(len(content) == member.size)
                size += len(content)
                require(size <= MAX_SOURCE)
                files[member.name] = (content, member.mode)
    except (tarfile.TarError, OSError):
        raise CandidateBuildError() from None
    require(len(files) == source["fileCount"] and "LICENSE" in files and sha(files["LICENSE"][0]) == manifest["license"]["sha256"])
    for name, digest in manifest["moduleLocks"].items():
        require(name in files and sha(files[name][0]) == digest)
    return files


def run(command, cwd=None):
    # A public fixed-origin Git fetch must not invoke user hooks, URL rewrites or
    # an interactive credential helper. No global config or toolchain is changed.
    askpass = {"SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "GCM_INTERACTIVE"}
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_") and key not in askpass}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1", GIT_ASKPASS="/bin/false")
    # Environment-level safe config also reaches nested promisor/lazy fetches.
    configs = (("core.hooksPath", os.devnull), ("core.askPass", "/bin/false"), ("credential.helper", ""),
               ("credential.interactive", "false"), ("http.sslVerify", "true"), ("protocol.allow", "never"),
               ("protocol.https.allow", "always"))
    env["GIT_CONFIG_COUNT"] = str(len(configs))
    for index, (key, value) in enumerate(configs):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=300, check=True)  # noqa: S603
        require(len(result.stdout) <= 4_194_304)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise CandidateBuildError() from None


def make_snapshot(source_dir, manifest):
    def git(*args):
        return run(["git", "-C", str(source_dir), *args])

    require(git("rev-parse", "HEAD").decode().strip() == COMMIT and git("rev-parse", "HEAD^{tree}").decode().strip() == TREE)
    rows = git("ls-tree", "-r", "-z", "HEAD", "--", "core", "transports", "LICENSE").split(b"\0")
    output, inventory, size = io.BytesIO(), [], 0
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for row in rows:
            if not row:
                continue
            header, name_raw = row.split(b"\t", 1)
            mode, kind, blob = header.decode("ascii").split()
            name = name_raw.decode("utf-8")
            require(kind == "blob" and mode in {"100644", "100755"} and selected_path(name))
            path = source_dir / name
            require(path.resolve().is_relative_to(source_dir.resolve()))
            content = read_input(path, MAX_FILE)
            # SHA1 here is Git's pinned object identity, not a new security hash.
            actual_blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()  # noqa: S324
            require(actual_blob == blob)
            size += len(content)
            require(size <= MAX_SOURCE and len(inventory) < 4096)
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), int(mode, 8) & 0o777
            archive.addfile(info, io.BytesIO(content))
            inventory.append({"path": name, "gitMode": mode, "gitBlobSha1": blob, "sha256": sha(content), "bytes": len(content)})
    raw = output.getvalue()
    verify_snapshot(raw, manifest)
    return raw, inventory


def fetch_snapshot(destination):
    manifest = load_manifest()
    require(not destination.exists())
    destination.mkdir(parents=True, mode=0o700)
    git = ["git", "-C", str(destination), "-c", "core.hooksPath=/dev/null", "-c", "http.sslVerify=true", "-c", "http.version=HTTP/1.1"]
    run(["git", "init", str(destination)])
    run([*git, "remote", "add", "origin", ORIGIN])
    run([*git, "config", "remote.origin.promisor", "true"])
    run([*git, "config", "remote.origin.partialclonefilter", "blob:none"])
    run([*git, "fetch", "--depth=1", "--filter=blob:none", "origin", COMMIT])
    run([*git, "sparse-checkout", "init", "--no-cone"])
    run([*git, "sparse-checkout", "set", "--no-cone", "/core/", "/transports/", "/LICENSE"])
    run([*git, "-c", "core.autocrlf=false", "checkout", "--detach", "FETCH_HEAD"])
    return make_snapshot(destination, manifest)


def checked_inputs(manifest):
    require(manifest["patch"]["path"] == "fingerprint.patch" and manifest["ui"]["path"] == "headless-index.html")
    dockerfile = read_input(BASE / "Dockerfile", 65_536)
    patch = read_input(BASE / manifest["patch"]["path"], 2_097_152)
    ui = read_input(BASE / manifest["ui"]["path"], 65_536)
    require(sha(dockerfile) == manifest["dockerfileSha256"] and sha(patch) == manifest["patch"]["sha256"]
            and sha(ui) == manifest["ui"]["sha256"] and sha(read_input(Path(__file__), 131_072)) == manifest["buildToolSha256"])
    require(("FROM " + manifest["builder"] + " AS builder").encode() in dockerfile
            and ("FROM " + manifest["runtime"] + " AS runtime").encode() in dockerfile)
    paths = re.findall(rb"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE)
    require(paths and all(left == right for left, right in paths))
    require({left.decode("utf-8") for left, _ in paths} == set(manifest["patch"]["allowedPaths"]))
    require(all(selected_path(left.decode("utf-8")) for left, _ in paths))
    old = re.findall(rb"^--- (\S+)$", patch, re.MULTILINE)
    new = re.findall(rb"^\+\+\+ (\S+)$", patch, re.MULTILINE)
    require(len(old) == len(new) == len(paths))
    require(all(before in {b"a/" + left, b"/dev/null"} and after == b"b/" + right
                for (left, right), before, after in zip(paths, old, new, strict=True)))
    return dockerfile, patch, ui


def build_context(raw, manifest):
    dockerfile, patch, ui = checked_inputs(manifest)
    files = verify_snapshot(raw, manifest)
    with tempfile.TemporaryDirectory(prefix="bifrost-candidate-patch-") as task:
        source = Path(task)
        for name, (content, mode) in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(mode)
        patch_file = source / "candidate.patch"
        patch_file.write_bytes(patch)
        run(["git", "apply", "--no-index", "--check", "--whitespace=error-all", str(patch_file)], cwd=source)
        run(["git", "apply", "--no-index", "--whitespace=error-all", str(patch_file)], cwd=source)
        allowed = set(files) | set(manifest["patch"]["allowedPaths"])
        for name in sorted(allowed):
            files[name] = (read_input(source / name, MAX_FILE), files.get(name, (b"", 0o644))[1])
        for name, digest in manifest["moduleLocks"].items():
            require(sha(files[name][0]) == digest)
    entries = {"source/" + name: value for name, value in files.items()}
    locks = "".join(digest + "  " + name + "\n" for name, digest in sorted(manifest["moduleLocks"].items()))
    entries.update({"Dockerfile": (dockerfile, 0o644), "headless-index.html": (ui, 0o644),
                    "go.work": (manifest["workspace"].encode(), 0o644), "expected-locks.sha256": (locks.encode(), 0o644),
                    "manifest.json": (read_input(BASE / "manifest.json", 65_536), 0o644)})
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, (content, mode) in sorted(entries.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), mode
            archive.addfile(info, io.BytesIO(content))
            require(output.tell() <= MAX_SOURCE)
    require(output.tell() <= MAX_SOURCE)
    return output.getvalue()


class BoundedArchiveReader:
    """Streaming Docker tar reader; neither the archive nor binary is buffered whole."""
    def __init__(self, chunks, limit):
        self.chunks, self.limit, self.total = iter(chunks), limit, 0
        self.pending = bytearray()
        self.ended = False

    def read(self, size):
        require(type(size) is int and 0 <= size <= 4_194_304)
        while len(self.pending) < size and not self.ended:
            try:
                chunk = next(self.chunks)
            except StopIteration:
                self.ended = True
                break
            self.total += len(chunk)
            require(self.total <= self.limit)
            self.pending.extend(chunk)
        value = bytes(self.pending[:size])
        del self.pending[:size]
        return value

    def close(self):
        close = getattr(self.chunks, "close", None)
        if close is not None:
            close()


def actual_binary_sha256(container):
    chunks, _ = container.get_archive("/app/main")
    reader = BoundedArchiveReader(chunks, MAX_BINARY + 1_048_576)
    digest, count, seen = hashlib.sha256(), 0, False
    try:
        with tarfile.open(fileobj=reader, mode="r|") as archive:
            for member in archive:
                require(not seen and member.name == "main" and member.isfile() and 0 < member.size <= MAX_BINARY)
                seen = True
                source = archive.extractfile(member)
                require(source is not None)
                with source:
                    while chunk := source.read(1_048_576):
                        count += len(chunk)
                        require(count <= MAX_BINARY)
                        digest.update(chunk)
                require(count == member.size)
        require(seen)
        return digest.hexdigest()
    finally:
        reader.close()


def image_provenance(client, image_id, manifest):
    """Read a bounded artifact archive from an owned container WITHOUT starting it."""
    container = None
    try:
        container = client.containers.create(image_id, entrypoint=["/bin/true"], command=[], network_mode="none",
                                             labels={"ai-res.bifrost-candidate.provenance": "true"})
        chunks, _ = container.get_archive("/app/candidate-provenance")
        raw = bytearray()
        for chunk in chunks:
            require(len(raw) + len(chunk) <= 2_097_152)
            raw.extend(chunk)
        files = {}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                if member.isdir() and member.name.rstrip("/") == "candidate-provenance":
                    continue
                require(member.isfile() and 0 <= member.size <= 524_288 and member.name.startswith("candidate-provenance/"))
                name = member.name.removeprefix("candidate-provenance/")
                require("/" not in name and "\\" not in name and name not in files)
                stream = archive.extractfile(member)
                require(stream is not None)
                with stream:
                    files[name] = stream.read(524_289)
                require(len(files[name]) == member.size)
        require(set(files) == {"local-core.json", "go-build-info.txt", "elf-program-headers.txt", "binary.sha256", "LICENSE", "source-manifest.json"})
        require(files["source-manifest.json"] == read_input(BASE / "manifest.json", 65_536))
        core = json.loads(files["local-core.json"])
        require(core["Path"] == "github.com/maximhq/bifrost/core" and core["Main"] is True and core["Dir"] == "/src/core")
        info = files["go-build-info.txt"].decode("utf-8")
        require(manifest["goVersion"] in info and re.search(r"(?m)^\s*dep\s+github\.com/maximhq/bifrost/core\s+\(devel\)(?:\s|$)", info))
        headers = files["elf-program-headers.txt"]
        require(headers and b"INTERP" not in headers and sha(files["LICENSE"]) == manifest["license"]["sha256"])
        binary = files["binary.sha256"].decode("ascii").split()
        require(len(binary) == 2 and binary[1] == "main" and re.fullmatch(r"[0-9a-f]{64}", binary[0]))
        actual = actual_binary_sha256(container)
        require(actual == binary[0])
        return {"binarySha256": actual, "localCore": core, "goBuildInfoSha256": sha(files["go-build-info.txt"]),
                "elfWithoutInterpreter": True, "licenseSha256": sha(files["LICENSE"])}
    finally:
        if container is not None:
            container.remove(v=True)


def build_image(snapshot=None):
    """Explicitly called only after SDK review/tests and runtime handoff."""
    import docker

    manifest = load_manifest()
    inputs = checked_inputs(manifest)
    key = sha(json.dumps({"manifest": manifest, "inputs": [sha(value) for value in inputs]}, sort_keys=True).encode())
    tag = "ai-res-bifrost-candidate-fp:" + key
    client = docker.from_env(timeout=1800)
    try:
        try:
            image = client.images.get(tag)
        except docker.errors.ImageNotFound:
            if snapshot is None:
                with tempfile.TemporaryDirectory(prefix="bifrost-candidate-source-") as task:
                    raw, _ = fetch_snapshot(Path(task) / "source")
            else:
                raw = read_input(snapshot, MAX_SOURCE)
            context = build_context(raw, manifest)
            try:
                image, _ = client.images.build(fileobj=io.BytesIO(context), custom_context=True, dockerfile="Dockerfile", tag=tag,
                                               labels={CACHE_LABEL: key, "org.opencontainers.image.revision": COMMIT},
                                               pull=False, rm=True, forcerm=True)
            except docker.errors.BuildError:
                raise CandidateBuildError() from None
        require(image.labels.get(CACHE_LABEL) == key and re.fullmatch(r"sha256:[0-9a-f]{64}", image.id))
        proof = image_provenance(client, image.id, manifest)
        return image.id, {"version": manifest["version"], "source": manifest["source"], "patchSha256": manifest["patch"]["sha256"],
                          "buildInputsSha256": key, "imageId": image.id, "builder": manifest["builder"], "runtime": manifest["runtime"],
                          "goVersion": manifest["goVersion"], "uiMode": manifest["ui"]["mode"], **proof}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "build"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            raw, inventory = fetch_snapshot(args.output / "source")
            (args.output / "source.tar").write_bytes(raw)
            (args.output / "source-inventory.json").write_text(json.dumps(inventory, sort_keys=True, indent=2) + "\n")
            result = {"sourceKind": "verified-git-sparse", "sha256": sha(raw), "files": len(inventory)}
        else:
            _, result = build_image(args.source)
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "build-provenance.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps(result, sort_keys=True))
    except Exception:
        raise SystemExit("Candidate build refused; no image publication or model calls were performed.") from None


if __name__ == "__main__":
    main()
