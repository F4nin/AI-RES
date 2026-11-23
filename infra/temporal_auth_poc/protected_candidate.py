"""Run the protected production entrypoints in a disposable Compose project."""

import base64
import json
import os
import subprocess
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from infra.scripts import g02_credentials
from infra.scripts.secrets_dev import generate_tls

from .compose_candidate import PASSWORD_FILES

INFRA = Path(__file__).resolve().parent.parent
NETWORKS = {
    "postgres": {"data"}, "postgres-provision": {"data"}, "temporal-schema": {"data"}, "migrate": {"data"},
    "temporal": {"data", "workflow", "platform", "observability"}, "temporal-namespace": {"workflow"},
    "platform-control": {"data", "platform"}, "delivery-control": {"data", "workflow", "delivery"},
    "outbox-dispatcher": {"data", "delivery"}, "candidate-probe": {"data", "workflow", "platform", "observability"},
}
PRIVATE_SECRETS = {
    "temporal": {"temporal_db_password", "postgres_tls_ca_cert", "temporal_auth_control_signing_key", "temporal_platform_ca",
                 *(f"temporal_{scope}_{part}" for scope in ("frontend", "internode") for part in ("ca", "key", "cert"))},
    "temporal-namespace": {"temporal_frontend_ca", "temporal_operator_cert", "temporal_operator_key"},
    "platform-control": {"platform_api_db_password", "postgres_tls_ca_cert", "g02_platform_public_keys", "g02_platform_tls_cert", "g02_platform_tls_key"},
    "delivery-control": {"api_db_password", "postgres_tls_ca_cert", "g02_delivery_tls_cert", "g02_delivery_tls_key",
                         "assigned_delivery_public_keys", "temporal_frontend_ca", "temporal_dispatcher_cert", "temporal_dispatcher_key",
                         "temporal_cancellation_cert", "temporal_cancellation_key"},
    "outbox-dispatcher": {"outbox_db_password", "postgres_tls_ca_cert", "outbox_delivery_signing_key", "g02_delivery_ca"},
}


def prepare_fixture(root: Path) -> dict[str, str]:
    values = generate_tls()
    values.update({name: token_hex(24) for name in PASSWORD_FILES})
    tls = g02_credentials.generate_tls("1")
    native, manager, dispatcher = (Ed25519PrivateKey.generate() for _ in range(3))

    def public_line(service: str, key: Ed25519PrivateKey) -> str:
        return service + " " + base64.b64encode(key.public_key().public_bytes_raw()).decode() + "\n"

    values["g02_platform_public_keys"] = public_line("MANAGER_RUNTIME", manager) + public_line("TEMPORAL_AUTH_CONTROL", native)
    values["assigned_delivery_public_keys"] = public_line("OUTBOX_DISPATCHER", dispatcher)
    values["outbox_delivery_signing_key"] = base64.b64encode(dispatcher.private_bytes_raw()).decode()
    values["temporal_auth_control_signing_key"] = base64.b64encode(native.private_bytes_raw()).decode()
    values["g02_manager_signing_key"] = base64.b64encode(manager.private_bytes_raw()).decode()
    values.update(tls)
    g02_credentials.materialize(root / "g02", values, g02_credentials.validate_tls(tls), publish_pins=True)
    probe_clients = root / "probe-clients"
    probe_clients.mkdir()
    for filename, secret in {
        "ca.pem": "temporal_frontend_ca", "manager.pem": "temporal_manager_cert", "manager.key": "temporal_manager_key",
        "reconciliation-observer.pem": "temporal_reconciliation_cert", "reconciliation-observer.key": "temporal_reconciliation_key",
        "platform-ca.pem": "temporal_platform_ca", "manager-signing-key": "g02_manager_signing_key",
    }.items():
        (probe_clients / filename).write_text(values[secret])
    return values


def assert_isolation(config: dict, root: Path) -> None:
    services = config["services"]
    pending = ["candidate-probe"]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        if name not in NETWORKS:
            raise RuntimeError("protected acceptance has an unexpected service dependency")
        visited.add(name)
        service = services[name]
        pending.extend(service.get("depends_on", ()))
        if (set(service.get("networks", {})) != NETWORKS[name] or service.get("ports") or service.get("privileged")
                or service.get("network_mode") or service.get("devices") or not service.get("read_only")):
            raise RuntimeError(f"insecure protected acceptance topology for {name}")
        secret_names = {secret["source"] for secret in service.get("secrets", ())}
        if name in PRIVATE_SECRETS and secret_names != PRIVATE_SECRETS[name]:
            raise RuntimeError(f"unexpected credentials mounted in {name}")
        for secret in secret_names:
            if Path(config["secrets"][secret].get("file", "")) != root / "g02" / secret:
                raise RuntimeError(f"{name} requested a non-fixture secret")
        for mount in service.get("volumes", ()):
            source = Path(mount["source"])
            if mount["type"] != "bind" or not mount.get("read_only") or not (
                source.is_relative_to(INFRA.parent) or source.is_relative_to(root)
            ):
                raise RuntimeError(f"unexpected mount in {name}")
    if visited != NETWORKS.keys():
        raise RuntimeError("protected acceptance omitted a necessary service")
    for network in {network for names in NETWORKS.values() for network in names}:
        connection = config["networks"][network]
        if not connection.get("internal") or connection.get("external"):
            raise RuntimeError(f"acceptance requires its own internal {network} network")


def main() -> None:
    with TemporaryDirectory(prefix="aires-g02-protected-") as scratch:
        root = Path(scratch).resolve()
        values = prepare_fixture(root)
        env = {
            **os.environ, "G02_PROTECTED_DIR": str(root / "g02"), "G02_TEST_ROOT": str(root),
            "G02_REQUEST_MAX_BYTES": "4096", "G02_CREDENTIAL_MAX_BYTES": "2048",
            "G02_MAX_CONNECTIONS": "32", "G02_CREDENTIAL_TTL_SECONDS": "30", "G02_NAMESPACE_RETENTION_SECONDS": "86400",
        }
        command = ["docker", "compose", "--env-file", "/dev/null", "--project-directory", str(INFRA), "-p", "aires-g02-test-" + token_hex(6),
                   "-f", str(INFRA / "compose.yaml"), "-f", str(INFRA / "compose.g02.yaml"),
                   "-f", str(INFRA / "temporal_auth_poc/compose.protected-test.yaml")]
        rendered = subprocess.check_output([*command, "config", "--format", "json"], env=env, timeout=15)  # noqa: S603
        assert_isolation(json.loads(rendered), root)
        try:
            subprocess.run([*command, "run", "--rm", "-T", "candidate-probe"], check=True, timeout=240, env=env)  # noqa: S603
        except subprocess.CalledProcessError:
            log = subprocess.check_output([*command, "logs", "--no-color", "--tail", "10", *NETWORKS], text=True, env=env, timeout=20)  # noqa: S603
            for value in values.values():
                for line in value.splitlines():
                    if line:
                        log = log.replace(line, "[redacted]")
            print(log)
            raise
        finally:
            subprocess.run([*command, "down"], check=True, timeout=60, env=env)  # noqa: S603


if __name__ == "__main__":
    main()
