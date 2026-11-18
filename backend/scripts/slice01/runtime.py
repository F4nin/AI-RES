"""Host-only ephemeral Docker harness; never imported by Manager/Worker Runtime."""
import os
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import docker

from ai_res.modules.model_registry.candidate_host import BIFROST_BIND_PATHS

from .common import ROOT, SliceRefused, canonical, decode, digest, load_plan, read_owned, wallet_directory, write_new


def latest_session() -> Path:
    paths = sorted((ROOT / "infra/secrets/local-admin").glob("owner-mfa-*/session.json"),
                   key=lambda p: p.stat().st_mtime_ns, reverse=True)
    if not paths:
        raise SliceRefused("OWNER_MFA_SESSION_REQUIRED")
    # Metadata only on the host; the token is read solely by the owner/API caller.
    import stat
    info = paths[0].lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SliceRefused("UNTRUSTED_SESSION_FILE")
    return paths[0]


class SliceRuntime:
    def __init__(self, directory: Path, *, cleanup_only: bool = False) -> None:
        self.directory = directory.resolve()
        self.cleanup_only = cleanup_only
        self.plan = load_plan(self.directory / "config", for_execution=not cleanup_only)
        self.client = cast(Any, docker).from_env(timeout=45)

    def close(self) -> None:
        self.client.close()

    def _verify_inputs(self) -> None:
        expected = self.plan["nativeInputs"]
        if set(expected) != set(BIFROST_BIND_PATHS):
            raise SliceRefused("NATIVE_INPUT_CHANGED")
        for target, source in BIFROST_BIND_PATHS.items():
            frozen = self.directory / "config/native" / Path(target).name
            if (digest(read_owned(ROOT / source, private=False)) != expected[target]
                    or digest(read_owned(frozen)) != expected[target]):
                raise SliceRefused("NATIVE_INPUT_CHANGED")
        schema = ROOT / "contracts/json-schema/worker/AI_RES_Worker_Contracts_v1.1.schema.json"
        if (digest(read_owned(schema, private=False)) != self.plan["workerContractSha256"]
                or digest(read_owned(self.directory / "config/worker-contract.json")) != self.plan["workerContractSha256"]):
            raise SliceRefused("CONTRACT_CHANGED")

    def _snapshot(self, container: Any) -> dict[str, Any]:
        container.reload()
        a = container.attrs
        if a["State"]["Status"] != "running" or a["HostConfig"].get("PortBindings"):
            raise SliceRefused("RUNTIME_UNAVAILABLE")
        return {"id": a["Id"], "image": a["Image"], "startedAt": a["State"]["StartedAt"],
                "restartCount": a["RestartCount"], "hostConfigSha256": digest(canonical(a["HostConfig"])),
                "configSha256": digest(canonical(a["Config"])),
                "networks": sorted(a["NetworkSettings"]["Networks"]),
                # Docker returns mounts in unspecified order on successive inspect calls.
                # Compare every mount field after ordering by its unique destination.
                "mountsSha256": digest(canonical(sorted(a["Mounts"], key=lambda m: m["Destination"])))}

    def _wait(self, container: Any, command: list[str]) -> None:
        end = time.monotonic() + 40
        while time.monotonic() < end:
            container.reload()
            if container.status != "running":
                raise SliceRefused("RUNTIME_START_FAILED")
            result = container.exec_run(command)
            if result.exit_code == 0:
                return
            time.sleep(0.3)
        raise SliceRefused("RUNTIME_HEALTH_TIMEOUT")

    def start(self, *, fixture_entry: Path | None = None) -> dict[str, Any]:
        if self.cleanup_only:
            raise SliceRefused("CLEANUP_ONLY")
        self._verify_inputs()
        fixture = self.plan["mode"] == "fixture"
        if fixture != (fixture_entry is not None) or (self.directory / "runtime.json").exists():
            raise SliceRefused("RUNTIME_MODE_OR_REPLAY")
        token = uuid4().hex[:12]
        private = self.client.networks.create("slice01-private-" + token, internal=True,
                    labels={"ai_res.tool": "slice01", "ai_res.instance": token})
        created: list[Any] = []
        networks = [private]
        uid = f"{os.getuid()}:{os.getgid()}"
        hardened = {"user": uid, "detach": True, "read_only": True, "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"], "pids_limit": 128,
                    "labels": {"ai_res.tool": "slice01", "ai_res.instance": token}}
        code = {str(ROOT / "backend/scripts"): {"bind": "/workspace/backend/scripts", "mode": "ro"}}
        credentials = self.directory / "credentials"
        env = {"PYTHONPATH": "/workspace/backend", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            relay_volumes = {**code,
                str(self.directory / "config/plan.json"): {"bind": "/plan.json", "mode": "ro"},
                str(wallet_directory(self.directory, self.plan["mode"])): {"bind": "/wallet", "mode": "rw"},
                str(credentials / "llm_relay_auth"): {"bind": "/run/secrets/llm_relay_auth", "mode": "ro"}}
            provider = credentials / "fixture_provider_key" if fixture else ROOT / "infra/secrets/candidate/runtime/deepseek_api_key"
            # Actual provider material is mounted only in live relay, never read here.
            relay_volumes[str(provider)] = {"bind": "/run/secrets/deepseek_api_key", "mode": "ro"}
            command = ["python", "-B", "-m", "scripts.slice01.relay", "--plan-file", "/plan.json",
                       "--ledger-file", "/wallet/ledger.jsonl", "--relay-auth-file", "/run/secrets/llm_relay_auth",
                       "--provider-key-file", "/run/secrets/deepseek_api_key"]
            if fixture:
                if fixture_entry is None:
                    raise SliceRefused("FIXTURE_REQUIRED")
                relay_volumes[str(fixture_entry.resolve())] = {"bind": "/fixture.py", "mode": "ro"}
                command = ["python", "-B", "/fixture.py"]
            relay = self.client.containers.run(self.plan["pythonImage"], command, name="slice01-relay-" + token,
                      network=private.name, volumes=relay_volumes, environment=env, mem_limit="256m", **hardened)
            created.append(relay)
            # Docker's create API network alias list is applied through reconnect.
            private.disconnect(relay)
            private.connect(relay, aliases=["llm-gateway"])
            if not fixture:
                egress = self.client.networks.create("slice01-egress-" + token, internal=False,
                            labels={"ai_res.tool": "slice01", "ai_res.instance": token})
                networks.append(egress)
                egress.connect(relay)
            self._wait(relay, ["python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)"])
            bf_volumes = {str(self.directory / "config/native" / Path(target).name): {"bind": target, "mode": "ro"}
                          for target in BIFROST_BIND_PATHS}
            bf_volumes.update({str(credentials / name): {"bind": "/run/secrets/" + name, "mode": "ro"}
                              for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth")})
            bifrost = self.client.containers.run(self.plan["bifrostImage"], [], name="slice01-bifrost-" + token,
                        network=private.name, volumes=bf_volumes, tmpfs={"/app/data": f"uid={os.getuid()},gid={os.getgid()},mode=0700",
                        "/tmp": f"uid={os.getuid()},gid={os.getgid()},mode=0700"}, mem_limit="512m", **hardened)  # noqa:S108 - private container tmpfs
            created.append(bifrost)
            private.disconnect(bifrost)
            private.connect(bifrost, aliases=["bifrost-poc"])
            self._wait(bifrost, ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "wget", "-q", "-O", "/dev/null", "-T", "2",
                                 "http://127.0.0.1:8080/health"])
            producer_volumes = {**code,
                str(self.directory / "config"): {"bind": "/config", "mode": "ro"},
                str(self.directory / "results"): {"bind": "/results", "mode": "rw"},
                str(wallet_directory(self.directory, self.plan["mode"])): {"bind": "/wallet", "mode": "rw"},
                str(self.directory / "config/worker-contract.json"):
                    {"bind": "/worker-contract.json", "mode": "ro"},
                str(credentials / "bifrost_virtual_key"): {"bind": "/run/secrets/bifrost_virtual_key", "mode": "ro"}}
            producer_env = dict(env)
            if not fixture:
                for source, target in ((latest_session(), "owner_session.json"),
                                      (ROOT / "infra/secrets/runtime/api_db_password", "api_db_password"),
                                      (ROOT / "infra/secrets/runtime/postgres_tls_ca_cert", "postgres_tls_ca_cert")):
                    producer_volumes[str(source)] = {"bind": "/run/secrets/" + target, "mode": "ro"}
                producer_env.update({"AI_RES_ENVIRONMENT": "prod", "AI_RES_DB_HOST": "postgres", "AI_RES_DB_USER": "ai_res_api",
                    "AI_RES_DB_PASSWORD_FILE": "/run/secrets/api_db_password", "AI_RES_DB_SSLMODE": "verify-full",
                    "AI_RES_DB_SSLROOTCERT_FILE": "/run/secrets/postgres_tls_ca_cert", "AI_RES_DB_APPLICATION_NAME": "slice01-operator"})
            producer = self.client.containers.run(self.plan["pythonImage"], ["python", "-c", "import time;time.sleep(86400)"],
                        name="slice01-caller-" + token, network=private.name, volumes=producer_volumes,
                        environment=producer_env, mem_limit="256m", **hardened)
            created.append(producer)
            if not fixture:
                self.client.networks.get("ai-res_data").connect(producer)
            marker_result = bifrost.exec_run(["cat", "/app/data/candidate-integrity.json"])
            marker = decode(marker_result.output)
            if marker_result.exit_code or marker["configSha256"] != self.plan["nativeConfigSha256"]:
                raise SliceRefused("NATIVE_CONFIGURATION_CHANGED")
            result = {"version": "slice01-runtime/1", "mode": self.plan["mode"], "instance": token,
                      "containers": {name: self._snapshot(c) for name, c in (("relay", relay), ("bifrost", bifrost), ("caller", producer))},
                      "networks": [n.id for n in networks], "marker": marker}
            write_new(self.directory / "runtime.json", result)
            return result
        except BaseException:
            for c in reversed(created):
                c.remove(force=True)
            for n in reversed(networks):
                n.remove()
            raise

    def verify(self) -> dict[str, Any]:
        if self.cleanup_only:
            raise SliceRefused("CLEANUP_ONLY")
        self.plan = load_plan(self.directory / "config")
        self._verify_inputs()
        state: dict[str, Any] = decode(read_owned(self.directory / "runtime.json"))
        if state["mode"] != self.plan["mode"]:
            raise SliceRefused("RUNTIME_CHANGED")
        for snapshot in state["containers"].values():
            current_snapshot = self._snapshot(self.client.containers.get(snapshot["id"]))
            if current_snapshot != snapshot:
                changed = ",".join(k for k in snapshot if current_snapshot[k] != snapshot[k])
                raise SliceRefused("RUNTIME_CHANGED:" + changed)
        bf = self.client.containers.get(state["containers"]["bifrost"]["id"])
        current = bf.exec_run(["cat", "/app/data/candidate-integrity.json"])
        if current.exit_code or decode(current.output) != state["marker"]:
            raise SliceRefused("NATIVE_CONFIGURATION_CHANGED")
        return state

    def execute(self, phase: str) -> dict[str, Any]:
        if phase not in {"preflight", "bootstrap", "run"} or self.plan["mode"] != "live":
            raise SliceRefused("LIVE_PHASE_REQUIRED")
        state = self.verify()
        result = self.client.containers.get(state["containers"]["caller"]["id"]).exec_run(
            ["python", "-B", "-m", "scripts.slice01.producer", phase], demux=True)
        stdout, stderr = result.output
        if result.exit_code or stdout is None:
            # Only a closed machine-code receipt is allowed out of the producer.
            # Arbitrary stderr/exception text may contain source or credentials.
            if stderr is not None and len(stderr) <= 2048:
                try:
                    failure = decode(stderr)
                    if (isinstance(failure, dict) and set(failure) <= {"status", "errorType", "reason", "stage"}
                            and all(isinstance(v, str) and 1 <= len(v) <= 100
                                    and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" for c in v)
                                    for v in failure.values())):
                        write_new(self.directory / "results" / (phase + "-failure.json"), failure)
                except (ValueError, OSError):
                    pass
            raise SliceRefused("PRODUCER_REFUSED")
        self.verify()
        answer: dict[str, Any] = decode(stdout)
        if not isinstance(answer, dict):
            raise SliceRefused("PRODUCER_INVALID_RESULT")
        return answer

    def stop(self) -> None:
        state = decode(read_owned(self.directory / "runtime.json"))
        # Only explicitly recorded owned ephemeral resources; never volumes or main stack.
        for snapshot in reversed(list(state["containers"].values())):
            try:
                c = self.client.containers.get(snapshot["id"])
            except docker.errors.NotFound:
                continue
            if c.labels.get("ai_res.instance") != state["instance"]:
                raise SliceRefused("OWNERSHIP_CHANGED")
            c.remove(force=True)
        for network_id in reversed(state["networks"]):
            try:
                n = self.client.networks.get(network_id)
            except docker.errors.NotFound:
                continue
            if n.attrs["Labels"].get("ai_res.instance") != state["instance"]:
                raise SliceRefused("OWNERSHIP_CHANGED")
            n.remove()
