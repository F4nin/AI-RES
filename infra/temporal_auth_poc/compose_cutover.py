"""Accept stock history preservation and rollback on a fresh, internal Compose project."""

import json
import os
import subprocess
import sys
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from .protected_candidate import INFRA, NETWORKS, PRIVATE_SECRETS, prepare_fixture

STOCK_NETWORKS = {
    "postgres": {"data"}, "postgres-provision": {"data"}, "temporal-schema": {"data"},
    "temporal": {"data", "admin", "workflow", "observability"}, "temporal-namespace": {"admin"},
    "cutover-probe": {"data", "workflow"},
}
NATIVE_NETWORKS = {
    **{name: NETWORKS[name] for name in (*STOCK_NETWORKS, "migrate", "platform-control") if name in NETWORKS},
    "cutover-probe": {"data", "workflow"},
}
PROBE_SECRETS = {"postgres_tls_ca_cert", "temporal_db_password", "temporal_frontend_ca",
                 *(f"temporal_{role}_{field}" for role in ("operator", "dispatcher", "manager", "reconciliation") for field in ("cert", "key"))}


def verify_isolation(config: dict, root: Path, project: str, *, native: bool) -> str:
    if config["name"] != project:
        raise RuntimeError("Compose cutover must use its own disposable project")
    expected = NATIVE_NETWORKS if native else STOCK_NETWORKS
    services = config["services"]
    pending, visited = ["cutover-probe"], set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        if name not in expected:
            raise RuntimeError("cutover has an unexpected service dependency")
        visited.add(name)
        service = services[name]
        pending.extend(service.get("depends_on", ()))
        if (set(service.get("networks", {})) != expected[name] or service.get("ports") or service.get("privileged") or service.get("build")
                or service.get("network_mode") or service.get("devices") or not service.get("read_only") or service.get("pull_policy") != "never"):
            raise RuntimeError(f"unexpected cutover topology for {name}")
        secret_names = {secret["source"] for secret in service.get("secrets", ())}
        if ((native and name in PRIVATE_SECRETS and secret_names != PRIVATE_SECRETS[name])
                or (name == "cutover-probe" and secret_names != PROBE_SECRETS)):
            raise RuntimeError(f"unexpected cutover credentials for {name}")
        for secret in secret_names:
            if Path(config["secrets"][secret].get("file", "")) != root / "g02" / secret:
                raise RuntimeError(f"cutover service {name} requested non-fixture credentials")
        for mount in service.get("volumes", ()):
            source = Path(mount["source"])
            if mount["type"] != "bind" or not mount.get("read_only") or not (source.is_relative_to(INFRA.parent) or source.is_relative_to(root)):
                raise RuntimeError(f"unexpected cutover mount in {name}")
    if visited != expected.keys() or not any(path.startswith("/var/lib/postgresql/data:") for path in services["postgres"]["tmpfs"]):
        raise RuntimeError("cutover requires all declared services and a fresh disposable database")
    for network in {network for names in expected.values() for network in names}:
        connection = config["networks"][network]
        if not connection.get("internal") or connection.get("external") or connection.get("name") != f"{project}_{network}":
            raise RuntimeError(f"cutover requires its own internal {network} network")
    temporal = services["temporal"]
    entrypoint = ["/temporal-native"] if native else ["/bin/sh", "/temporal/start.sh"]
    if temporal.get("entrypoint") != entrypoint:
        raise RuntimeError("unexpected Temporal entrypoint in the cutover fixture")
    return temporal["image"]


def main() -> None:
    with TemporaryDirectory(prefix="aires-g02-cutover-") as scratch:
        root = Path(scratch).resolve()
        values = prepare_fixture(root)
        project = "aires-g02-cutover-" + token_hex(6)
        env = {
            **os.environ, "G02_PROTECTED_DIR": str(root / "g02"), "G02_TEST_ROOT": str(root),
            "G02_REQUEST_MAX_BYTES": "4096", "G02_CREDENTIAL_MAX_BYTES": "2048", "G02_MAX_CONNECTIONS": "32",
            "G02_CREDENTIAL_TTL_SECONDS": "30", "G02_NAMESPACE_RETENTION_SECONDS": "86400",
        }
        base = ["docker", "compose", "--env-file", "/dev/null", "--project-directory", str(INFRA), "-p", project, "-f", str(INFRA / "compose.yaml")]
        cutover = ["-f", str(INFRA / "temporal_auth_poc/compose.cutover-test.yaml")]
        stock = base + cutover
        native = base + ["-f", str(INFRA / "compose.g02.yaml"), "-f", str(INFRA / "temporal_auth_poc/compose.protected-test.yaml")] + cutover

        def run(command, *args, input_data: bytes | None = None, timeout: int = 150) -> bytes:
            result = subprocess.run([*command, *args], env=env, input=input_data, capture_output=True, timeout=timeout)  # noqa: S603
            if result.returncode != 0:
                log = result.stderr.decode(errors="replace") + result.stdout.decode(errors="replace")
                for value in values.values():
                    for line in value.splitlines():
                        if line:
                            log = log.replace(line, "[redacted]")
                print(log, file=sys.stderr, end="")
                raise RuntimeError(f"cutover command failed with exit {result.returncode}: {args[0]}")
            return result.stdout

        def container_state(command, name: str) -> tuple[str, str, str]:
            container = run(command, "ps", "-q", name).decode().strip()
            if not container:
                raise RuntimeError(f"cutover service {name} has no running container")
            row = run(["docker"], "inspect", "--format", "{{.Id}} {{.State.StartedAt}} {{.Config.Image}}", container, timeout=10).decode().split()
            ident, started, image = row
            return ident, started, image

        stock_image = verify_isolation(json.loads(run(stock, "config", "--format", "json")), root, project, native=False)
        native_image = verify_isolation(json.loads(run(native, "config", "--format", "json")), root, project, native=True)
        if stock_image == native_image:
            raise RuntimeError("cutover requires distinct stock and native images")

        try:
            manifest = run(stock, "run", "--rm", "-T", "cutover-probe", "seed")
            assert len(json.loads(manifest)["closed"]) == 2
            postgres = container_state(stock, "postgres")
            initial = container_state(stock, "temporal")
            assert initial[2] == stock_image
            print("PASS stock Temporal drained an active legacy Activity, replayed two closed histories and seeded a separate queued Run", flush=True)

            run(stock, "rm", "--stop", "--force", "temporal-namespace", "temporal")
            run(native, "run", "--rm", "-T", "cutover-probe", "native", input_data=manifest)
            protected = container_state(native, "temporal")
            assert protected[0] != initial[0] and protected[2] == native_image and container_state(native, "postgres") == postgres
            print("PASS native preserved namespace and terminal histories, rejected legacy task issuance and committed its timeout before rollback", flush=True)

            run(native, "rm", "--stop", "--force", "temporal-namespace", "temporal")
            run(stock, "run", "--rm", "-T", "cutover-probe", "rollback", input_data=manifest)
            restored = container_state(stock, "temporal")
            assert restored[0] not in (initial[0], protected[0]) and restored[2] == stock_image and container_state(stock, "postgres") == postgres
            print("PASS stock rollback kept the same stores and namespace and completed the original pending Run without starting another", flush=True)
        finally:
            run(native, "down", timeout=60)


if __name__ == "__main__":
    main()
