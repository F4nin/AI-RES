"""Exercise native Temporal, private ar2 and the stock PostgreSQL jobs.

From the repository root, run python -B -m infra.temporal_auth_poc.compose_candidate.
Pass --network to use the private data/workflow/platform topology and redeliver an Outbox row.
Add --lose-start-response to exercise a lost Temporal reply before Run binding.
Use --replay-exhausted-start to exercise controlled replay of a quarantined Start.
Add --manager-timeout to exercise the real Manager Activity timeout after ACK.
Add --paginate-history to force small Workflow Task History pages in the native test server.
Add --native-runtime to use the standalone runtime image for a transport smoke check.
"""

import json
import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from infra.scripts.secrets_dev import generate_tls

HERE = Path(__file__).resolve().parent
PASSWORD_FILES = (
    "postgres_superuser_password", "temporal_db_password", "checkpointer_db_password", "migrator_db_password",
    "api_db_password", "platform_api_db_password", "outbox_db_password", "consumer_db_password", "auditor_db_password", "backup_db_password",
)


def check_isolation(config: dict, fixture: Path, *, networked: bool = False, runtime: bool = False) -> None:
    services = config["services"]
    if set(services) != {"postgres", "postgres-provision", "temporal-schema", "migrate", "candidate-native", "candidate-probe"}:
        raise RuntimeError("unexpected service in the isolated Compose candidate")
    networks = config.get("networks", {})
    if networked and (set(networks) != {"data", "workflow", "platform"} or any(not net.get("internal") or net.get("external") for net in networks.values())):
        raise RuntimeError("the networked candidate requires its three internal networks")
    for name, service in services.items():
        expected_mode = None if networked else "none" if name == "postgres" else "service:postgres"
        expected_networks = set()
        if networked:
            expected_networks = {"data", "workflow", "platform"} if name in {"candidate-native", "candidate-probe"} else {"data"}
        if (service.get("network_mode") != expected_mode or set(service.get("networks", {})) != expected_networks
                or service.get("ports") or service.get("privileged")):
            raise RuntimeError(f"unexpected network or privileged access for {name}")
        writable_fixture = fixture / ("active-certs" if runtime else "native")
        for mount in service.get("volumes", []):
            if mount["type"] != "bind" or (not mount.get("read_only") and (name, mount["source"]) != ("candidate-probe", str(writable_fixture))):
                raise RuntimeError(f"unexpected writable mount for {name}")
        if name == "candidate-native":
            sources = {secret["source"] for secret in service.get("secrets", [])}
            mounts = {(mount["source"], mount["target"]) for mount in service["volumes"]}
            expected_sources = {"postgres_tls_ca_cert"}
            expected_mounts = {(str(fixture / "native-user"), "/etc/passwd")}
            if runtime:
                expected_sources |= {"temporal_db_password", "temporal_platform_ca", "temporal_auth_control_signing_key"}
                expected_sources |= {f"temporal_{scope}_{part}" for scope in ("frontend", "internode") for part in ("cert", "key", "ca")}
                expected_mounts.add((str(fixture / "active-certs"), "/etc/temporal/active-client-certs"))
            else:
                expected_mounts.add((str(fixture / "native"), "/native"))
            if sources != expected_sources or mounts != expected_mounts:
                raise RuntimeError("unexpected native Temporal secret or bind mount")
        if runtime and name == "candidate-probe" and service.get("secrets"):
            raise RuntimeError("the native smoke client does not need any server secrets")
    for name, secret in config["secrets"].items():
        if Path(secret.get("file", "")) != fixture / name or "/" in name:
            raise RuntimeError(f"{name} is not a disposable Compose secret")


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true")
    start_failure = parser.add_mutually_exclusive_group()
    start_failure.add_argument("--lose-start-response", action="store_true")
    start_failure.add_argument("--replay-exhausted-start", action="store_true")
    parser.add_argument("--manager-timeout", action="store_true")
    parser.add_argument("--paginate-history", action="store_true")
    parser.add_argument("--native-runtime", action="store_true")
    args = parser.parse_args()
    if args.native_runtime and (not args.network or args.lose_start_response or args.replay_exhausted_start
                               or args.manager_timeout or args.paginate_history):
        parser.error("--native-runtime requires --network and cannot run the tagged test-binary scenarios")
    if args.lose_start_response and not args.network:
        parser.error("--lose-start-response requires --network")
    if args.replay_exhausted_start and not args.network:
        parser.error("--replay-exhausted-start requires --network")
    if args.manager_timeout and not args.network:
        parser.error("--manager-timeout requires --network")
    if args.paginate_history and not args.network:
        parser.error("--paginate-history requires --network")
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("Docker is required for the Compose candidate")
    with TemporaryDirectory(prefix="aires-temporal-candidate-") as scratch:
        fixture = Path(scratch).resolve()
        native = fixture / "native"
        native.mkdir(mode=0o700)
        uid, gid = (1000, 1000) if sys.platform == "darwin" or os.getuid() == 0 else (os.getuid(), os.getgid())
        if sys.platform == "linux" and os.getuid() == 0:
            os.chown(native, uid, gid)
        runtime_user = fixture / "native-user"
        runtime_user.write_text(f"temporal-probe:x:{uid}:{gid}:Temporal probe:/scratch:/nonexistent\n")
        runtime_user.chmod(0o444)
        secret_files = generate_tls()
        secret_files.update({name: token_hex(24) for name in PASSWORD_FILES})
        for name, content in secret_files.items():
            # The parent is private on the host. Only explicitly scoped services get these file mounts.
            path = fixture / name
            path.write_text(content)
            path.chmod(0o444)
        if args.native_runtime:
            from .check_runtime import prepare

            for name, content in prepare(fixture).items():
                path = fixture / name
                path.write_bytes(content)
                path.chmod(0o444)
                secret_files[name] = content.decode("ascii")
            if sys.platform == "linux" and os.getuid() == 0:
                os.chown(fixture / "active-certs", uid, gid)
        environment = {
            **os.environ, "G02_CANDIDATE_DIR": str(fixture), "G02_CANDIDATE_UID": str(uid), "G02_CANDIDATE_GID": str(gid),
            "G02_PROBE_LOSE_START_RESPONSE": "1" if args.lose_start_response else "0",
            "G02_PROBE_REPLAY_EXHAUSTED_START": "1" if args.replay_exhausted_start else "0",
            "G02_PROBE_MANAGER_TIMEOUT": "1" if args.manager_timeout else "0",
            "G02_PROBE_PAGINATE_HISTORY": "1" if args.paginate_history else "0",
        }
        command = [docker, "compose", "--env-file", "/dev/null", "-p", "aires-temporal-candidate-" + token_hex(6),
                   "--project-directory", str(HERE.parent), "-f", str(HERE / "compose.candidate.yaml")]
        if args.network:
            command.extend(("-f", str(HERE / "compose.network.yaml")))
        if args.native_runtime:
            command.extend(("-f", str(HERE / "compose.runtime.yaml")))
        config = subprocess.check_output([*command, "config", "--format", "json"], env=environment, timeout=15)  # noqa: S603
        check_isolation(json.loads(config), fixture, networked=args.network, runtime=args.native_runtime)
        run = ["run", "--rm", "-T"]
        if args.network:
            run.append("--use-aliases")
        try:
            subprocess.run([*command, *run, "candidate-probe"], env=environment, check=True, timeout=240)  # noqa: S603
            if args.native_runtime:
                subprocess.run([*command, "restart", "candidate-native"], env=environment, check=True, timeout=60)  # noqa: S603
                subprocess.run(  # noqa: S603
                    [*command, *run, "--no-deps", "candidate-probe", "python", "-B",
                     "/repo/infra/temporal_auth_poc/check_runtime.py", "--existing-namespace"],
                    env=environment, check=True, timeout=120,
                )
        except subprocess.CalledProcessError:
            logs = subprocess.run(  # noqa: S603
                [*command, "logs", "--no-color", "--tail", "12", "postgres", "postgres-provision", "migrate", "temporal-schema", "candidate-native"],
                env=environment, capture_output=True, text=True, check=False, timeout=25,
            ).stdout
            for value in secret_files.values():
                for line in value.splitlines():
                    if line:
                        logs = logs.replace(line, "[redacted]")
            print(logs, file=sys.stderr, end="")
            raise
        finally:
            subprocess.run([*command, "down"], env=environment, check=True, timeout=60)  # noqa: S603


if __name__ == "__main__":
    main()
