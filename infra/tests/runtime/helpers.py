"""Runtime evidence helpers: tests run against the live Compose stack (`make up`). Without a running stack they are skipped, and a
skip is NOT evidence (the report must show them executed)."""
import json
import subprocess
from pathlib import Path

INFRA = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-p", "ai-res", "-f", str(INFRA / "compose.yaml"), "-f", str(INFRA / "compose.dev.yaml")]
SECRETS = INFRA / "secrets" / "runtime"
LONG_RUNNING = ["api", "platform-api", "outbox-dispatcher", "manager-runtime", "worker-runtime", "reverse-proxy", "postgres", "temporal", "temporal-ui", "minio",
                "otel-collector"]
ONE_SHOT = ["postgres-provision", "migrate", "temporal-schema", "temporal-namespace", "minio-init"]


def sh(cmd: list[str], *, stdin: str | None = None, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=check, timeout=timeout)  # noqa: S603


def compose(*args: str, **kw) -> subprocess.CompletedProcess[str]:
    return sh([*COMPOSE, *args], **kw)


def container_id(service: str) -> str:
    out = compose("ps", "-a", "-q", service).stdout.split()
    assert out, f"no container for {service}"
    return out[0]


def inspect(service: str) -> dict:
    return json.loads(sh(["docker", "inspect", container_id(service)], check=True).stdout)[0]


def exec_in(service: str, *cmd: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    args = ["docker", "exec"] + (["-i"] if stdin is not None else []) + [container_id(service), *cmd]
    return sh(args, stdin=stdin)




def _scan_blob(data: bytes, needles: list[bytes], depth: int = 0) -> set[bytes]:
    """Searches raw bytes, then looks through gzip streams and nested tar archives (layers are gzip with the containerd image store)."""
    import contextlib
    import gzip
    import io
    import tarfile

    hits = {n for n in needles if n in data}
    if depth > 3:
        return hits
    if data[:2] == b"\x1f\x8b":
        with contextlib.suppress(OSError, EOFError):
            hits |= _scan_blob(gzip.decompress(data), needles, depth + 1)
    elif len(data) > 512 and data[257:262] == b"ustar":
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for m in tf:
                    if m.isfile():
                        hits |= _scan_blob(tf.extractfile(m).read(), needles, depth + 1)
        except tarfile.TarError:
            pass
    return hits


def image_secret_hits(image: str, needles: list[bytes], workdir: Path) -> set[bytes]:
    import tarfile

    tar_path = workdir / (image.replace("/", "_").replace(":", "_") + ".tar")
    res = sh(["docker", "save", "-o", str(tar_path), image], timeout=300)
    assert res.returncode == 0, res.stderr
    hits: set[bytes] = set()
    layers = 0
    with tarfile.open(tar_path) as outer:
        for m in outer:
            if m.isfile():
                layers += 1
                hits |= _scan_blob(outer.extractfile(m).read(), needles)
    assert layers > 0, f"docker save of {image} produced no files"
    return hits
