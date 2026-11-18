"""Concrete development host checks for ADR136; no creation or live activation.

An immutable operator-reviewed configuration binds local files and actual Docker
inspection. Every validation fetches the exact official pricing document again;
no cache age, arbitrary TTL, boolean approval or model admission is inferred.
Only the trusted development host uses Docker inspection, never a Runtime.
"""
import asyncio
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

import httpx

from ai_res.llm.candidate_payload import CandidateBody, canonicalize_candidate_body
from ai_res.modules.model_registry.candidate_integrity import (
    NAMESPACE_COMMAND,
    CandidateIntegrityObservation,
    namespace_observation,
)
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest
from ai_res.modules.model_registry.poc_budget import AUTHORIZATION_KEY
from ai_res.modules.model_registry.poc_control import (
    CandidateClaimedAttempt,
    CandidateClaimRequest,
    CandidateControlDenied,
    CandidateControlPort,
    CandidateSettlementRequest,
    CandidateSettlementResult,
)

HOST_VERSION = "flash-candidate-host/0.2"
OFFICIAL_TARIFF_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
INPUT_PATHS = {"config": "infra/llm_poc/config.template.json", "plan": "docs/implementation/groups/G02_FLASH_ADMISSION.md",
               "tariff": "infra/llm_poc/candidate_tariff.json", "prompt": "backend/src/ai_res/llm/candidate_payload.py"}
BIFROST_BIND_PATHS = {"/poc/start-bifrost.sh": "infra/llm_poc/start-bifrost.sh",
                      "/etc/bifrost/config.template.json": "infra/llm_poc/config.template.json",
                      "/etc/bifrost/pricing.json": "infra/llm_poc/pricing.json",
                      "/etc/bifrost/model-parameters.json": "infra/llm_poc/model-parameters.json",
                      "/etc/bifrost/mcp-library.json": "infra/llm_poc/mcp-library.json"}
_SECRET_DESTINATIONS = frozenset({"/run/secrets/bifrost_admin_password", "/run/secrets/bifrost_virtual_key", "/run/secrets/llm_relay_auth"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LIMIT = 1_048_576
_MANIFEST_KEYS = ("codeRevision", "sourceTreeSha256", "configSha256", "promptSha256", "toolsSha256", "bifrostImageSha256",
                  "planSha256", "tariffSha256")


def _require(condition: bool) -> None:
    if not condition:
        raise CandidateRunDenied("BINDING_MISMATCH")


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _json(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(content, object_pairs_hook=_pairs, parse_constant=lambda _: _require(False))
        _require(isinstance(value, dict))
        return dict(value)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CandidateRunDenied("BINDING_MISMATCH") from None


def _read_file(path: Path) -> bytes:
    """Explicit bounded regular input only; reject symlinks and writable mounts."""
    descriptor, directory = -1, -1
    try:
        _require(path.is_absolute() and ".." not in path.parts)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory = os.open("/", directory_flags)
        for part in path.parts[1:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022 and info.st_nlink == 1
                 and info.st_uid in {0, os.getuid()} and 0 < info.st_size <= _LIMIT)
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            content = source.read(_LIMIT + 1)
        _require(0 < len(content) <= _LIMIT)
        return content
    except OSError:
        raise CandidateRunDenied("BINDING_MISMATCH") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory >= 0:
            os.close(directory)


@dataclass(frozen=True, slots=True, repr=False)
class CandidateHostConfig:
    account_id: UUID
    manifest: CandidateRunManifest
    tariff_snapshot_sha256: str
    bifrost_container_id: str
    expected_runtime_sha256: str
    expected_integrity_sha256: str
    file_path: Path
    file_sha256: str

    def __post_init__(self) -> None:
        _require(isinstance(self.account_id, UUID) and isinstance(self.manifest, CandidateRunManifest)
                 and all(_hash(value) for value in (self.tariff_snapshot_sha256, self.bifrost_container_id,
                                                    self.expected_runtime_sha256, self.expected_integrity_sha256, self.file_sha256))
                 and isinstance(self.file_path, Path) and self.file_path.is_absolute() and self.manifest.tools_sha256 is None)

    @classmethod
    def load(cls, path: Path) -> Self:
        try:
            content = _read_file(path)
            data = _json(content)
            _require(set(data) == {"version", "authorizationKey", "accountId", "manifest", "tariffSnapshotSha256",
                                   "bifrostContainerId", "expectedRuntimeSha256", "expectedIntegritySha256", "inputPaths"})
            _require(data["version"] == HOST_VERSION and data["authorizationKey"] == AUTHORIZATION_KEY
                     and data["inputPaths"] == {**INPUT_PATHS, "tools": None})
            values = data["manifest"]
            _require(isinstance(values, dict) and set(values) == set(_MANIFEST_KEYS))
            manifest = CandidateRunManifest(*(values[name] for name in _MANIFEST_KEYS))
            account = UUID(data["accountId"])
            _require(str(account) == data["accountId"])
            return cls(account, manifest, data["tariffSnapshotSha256"], data["bifrostContainerId"],
                       data["expectedRuntimeSha256"], data["expectedIntegritySha256"], path, _sha(content))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CandidateRunDenied("HOST_UNCONFIGURED") from None


@dataclass(frozen=True, slots=True, repr=False)
class CandidateTariff:
    currency: str
    input_per_million: Decimal
    output_per_million: Decimal
    input_bound: int
    output_bound: int
    snapshot_sha256: str


def read_tariff_descriptor(config: CandidateHostConfig, root: Path) -> CandidateTariff:
    """Immutable reviewed rates and official raw snapshot are one hashed artifact."""
    try:
        content = _read_file(root / INPUT_PATHS["tariff"])
        _require(_sha(content) == config.manifest.tariff_sha256)
        data = _json(content)
        _require(set(data) == {"version", "sourceUrl", "snapshotSha256", "currency", "inputPerMillion", "outputPerMillion",
                               "inputBound", "outputBound"})
        _require(data["version"] == "flash-candidate-tariff/0.1" and data["sourceUrl"] == OFFICIAL_TARIFF_URL
                 and data["snapshotSha256"] == config.tariff_snapshot_sha256 and data["currency"] == "USD"
                 and type(data["inputBound"]) is int and data["inputBound"] == 2_000_000
                 and type(data["outputBound"]) is int and data["outputBound"] == 256)
        _require(all(isinstance(data[name], str) and bool(re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,9})?", data[name]))
                     for name in ("inputPerMillion", "outputPerMillion")))
        inp, out = Decimal(data["inputPerMillion"]), Decimal(data["outputPerMillion"])
        _require(inp.is_finite() and out.is_finite() and inp > 0 and out > 0)
        return CandidateTariff("USD", inp, out, 2_000_000, 256, config.tariff_snapshot_sha256)
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise CandidateRunDenied("BINDING_MISMATCH") from None


class OfficialTariffObserver:
    """Fresh TLS GET on every call; an exact-document change requires re-review."""
    def __init__(self, *, http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=http_transport,
                                         timeout=httpx.Timeout(5), limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def snapshot_sha256(self) -> str:
        try:
            async with asyncio.timeout(5):
                request = self._client.build_request("GET", OFFICIAL_TARIFF_URL,
                                                     headers={"cache-control": "no-cache", "accept-encoding": "identity", "accept": "text/html"})
                request.headers.pop("cookie", None)
                request.headers.pop("authorization", None)
                response = await self._client.send(request, stream=True)
                try:
                    _require(response.status_code == 200 and response.headers.get("content-encoding", "identity").lower() == "identity"
                             and response.headers.get("content-type", "").split(";", 1)[0].strip().lower() == "text/html")
                    content = bytearray()
                    async for part in response.aiter_raw():
                        _require(len(content) + len(part) <= _LIMIT)
                        content.extend(part)
                    _require(bool(content))
                    return _sha(bytes(content))
                finally:
                    await response.aclose()
        except (httpx.HTTPError, OSError, TimeoutError, ValueError):
            raise CandidateRunDenied("HOST_UNCONFIGURED") from None


@dataclass(frozen=True, slots=True, repr=False)
class CandidateRuntimeObservation:
    image_sha256: str
    runtime_sha256: str
    bind_mounts: tuple[tuple[str, str], ...] = ()
    integrity: CandidateIntegrityObservation | None = None
    hardened_launch: bool = False

    def __post_init__(self) -> None:
        _require(_hash(self.image_sha256) and _hash(self.runtime_sha256) and isinstance(self.bind_mounts, tuple)
                 and all(isinstance(pair, tuple) and len(pair) == 2 and all(isinstance(item, str) for item in pair) for pair in self.bind_mounts))
        _require((self.integrity is None or isinstance(self.integrity, CandidateIntegrityObservation)) and type(self.hardened_launch) is bool)


def runtime_observation(data: dict[str, Any], container_id: str) -> CandidateRuntimeObservation:
    """Hash actual stable configuration, including env and mount/network identity.

    Only hashes leave this boundary; raw inspect configuration is never printed.
    A previously reviewed exact hash supplements the structural refusal checks.
    """
    try:
        _require(data["Id"] == container_id and _hash(container_id) and data["State"]["Running"] is True)
        started = data["State"]["StartedAt"]
        _require(isinstance(started, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z", started) is not None
                 and type(data["RestartCount"]) is int and data["RestartCount"] >= 0
                 and type(data["State"]["Pid"]) is int and data["State"]["Pid"] > 0 and data["State"].get("Restarting", False) is False)
        image = data["Image"]
        _require(isinstance(image, str) and image.startswith("sha256:") and _hash(image[7:]))
        host, config, mounts = data["HostConfig"], data["Config"], data["Mounts"]
        _require(isinstance(host, dict) and isinstance(config, dict) and isinstance(mounts, list))
        user = config.get("User")
        _require(isinstance(user, str) and bool(re.fullmatch(r"[1-9][0-9]*(?::[1-9][0-9]*)?", user)))
        _require(host.get("ReadonlyRootfs") is True and host.get("Privileged") is False
                 and host.get("NetworkMode") != "host" and host.get("PidMode") != "host" and host.get("IpcMode") != "host"
                 and not host.get("PortBindings") and not host.get("PublishAllPorts") and not host.get("Devices")
                 and not host.get("DeviceRequests") and not host.get("CapAdd") and "ALL" in host.get("CapDrop", [])
                 and any(value in {"no-new-privileges", "no-new-privileges:true"} for value in host.get("SecurityOpt", [])))
        bound_mounts = []
        destinations: set[str] = set()
        for mount in mounts:
            _require(isinstance(mount, dict) and isinstance(mount.get("Destination"), str) and mount["Destination"] not in destinations)
            destination = mount["Destination"]
            destinations.add(destination)
            if mount.get("Type") == "tmpfs":
                _require(destination in {"/app/data", "/tmp"})  # noqa: S108 - inspected container tmpfs, never a host temp path
            else:
                _require(mount.get("Type") == "bind" and mount.get("RW") is False and isinstance(mount.get("Source"), str)
                         and destination in {*BIFROST_BIND_PATHS, *_SECRET_DESTINATIONS} and "docker.sock" not in mount["Source"])
                bound_mounts.append((destination, mount["Source"]))
        env = config.get("Env", [])
        _require(isinstance(env, list) and all(isinstance(value, str) and "=" in value for value in env))
        for value in env:
            name, _ = value.split("=", 1)
            _require(not any(term in name.upper() for term in ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "VIRTUAL_KEY")) or name.endswith("_FILE"))
        raw_networks = data["NetworkSettings"]["Networks"]
        _require(isinstance(raw_networks, dict) and bool(raw_networks) and "host" not in raw_networks)
        networks = {}
        for name, network in raw_networks.items():
            _require(isinstance(network, dict) and isinstance(network.get("NetworkID"), str) and _hash(network["NetworkID"])
                     and isinstance(network.get("Aliases"), list) and all(isinstance(alias, str) for alias in network["Aliases"]))
            networks[name] = {"NetworkID": network["NetworkID"], "Aliases": sorted(network["Aliases"])}
        # Docker inspect does not preserve Mounts iteration order between reads.
        # Destinations were validated unique above; bind every field while
        # ignoring only the order of this unordered collection.
        stable = {"Config": config, "HostConfig": host, "Mounts": sorted(mounts, key=lambda mount: mount["Destination"]), "Networks": networks,
                  "Process": {"StartedAt": started, "Pid": data["State"]["Pid"], "RestartCount": data["RestartCount"]}}
        encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        hardened = config.get("Entrypoint") == ["/bin/sh", "/app/start-candidate.sh"] and config.get("Cmd") in (None, [])
        return CandidateRuntimeObservation(image[7:], _sha(b"flash-candidate-runtime/0.2\0" + encoded), tuple(sorted(bound_mounts)), hardened_launch=hardened)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise CandidateRunDenied("BINDING_MISMATCH") from None


class DockerCandidateObserver:
    """Trusted dev observation only; no context discovery, mutation or launch."""
    def __init__(self, *, executable: Path = Path("/usr/local/bin/docker"), socket_path: Path = Path("/var/run/docker.sock")) -> None:
        _require(executable.is_absolute() and socket_path.is_absolute() and "\0" not in str(socket_path))
        self._executable, self._endpoint = executable, "unix://" + str(socket_path)

    async def _command(self, args: tuple[str, ...], *, limit: int = _LIMIT) -> bytes:
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(5):
                process = await asyncio.create_subprocess_exec(str(self._executable), "--host", self._endpoint, *args, stdout=asyncio.subprocess.PIPE,
                                                               stderr=asyncio.subprocess.DEVNULL, env={"DOCKER_CONFIG": "/nonexistent"})
                assert process.stdout is not None
                raw = bytearray()
                while part := await process.stdout.read(65_536):
                    _require(len(raw) + len(part) <= limit)
                    raw.extend(part)
                _require(await process.wait() == 0)
                return bytes(raw)
        except (OSError, ValueError, TimeoutError):
            raise CandidateRunDenied("HOST_UNCONFIGURED") from None
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    async def observe(self, container_id: str) -> CandidateRuntimeObservation:
        _require(_hash(container_id))
        inspect_args = ("container", "inspect", container_id, "--format", "{{json .}}")
        before = runtime_observation(_json(await self._command(inspect_args)), container_id)
        _require(before.hardened_launch)
        integrity = namespace_observation(await self._command(("exec", container_id, "/usr/bin/env", "-i", "PATH=/usr/bin:/bin",
                                                               "/bin/sh", "-c", NAMESPACE_COMMAND), limit=16_384))
        after = runtime_observation(_json(await self._command(inspect_args)), container_id)
        _require(before == after)
        return replace(after, integrity=integrity)


class TariffObserverPort(Protocol):
    async def snapshot_sha256(self) -> str: ...


class RuntimeObserverPort(Protocol):
    async def observe(self, container_id: str) -> CandidateRuntimeObservation: ...


class HostValidationPort(Protocol):
    async def validate_host(self) -> None: ...


class CandidateDevelopmentGate:
    def __init__(self, config: CandidateHostConfig, root: Path, *, source_reader: Callable[[], tuple[str, str]],
                 tariff_observer: TariffObserverPort, image_observer: RuntimeObserverPort) -> None:
        _require(isinstance(config, CandidateHostConfig) and isinstance(root, Path) and root.is_absolute())
        self.config, self._root, self._source = config, root, source_reader
        self._tariff, self._image = tariff_observer, image_observer

    def _local(self) -> CandidateTariff:
        config, manifest = self.config, self.config.manifest
        _require(_sha(_read_file(config.file_path)) == config.file_sha256)
        _require(self._source() == (manifest.code_revision, manifest.source_tree_sha256))
        expected = {"config": manifest.config_sha256, "plan": manifest.plan_sha256, "tariff": manifest.tariff_sha256,
                    "prompt": manifest.prompt_sha256}
        for role, relative in INPUT_PATHS.items():
            _require(_sha(_read_file(self._root / relative)) == expected[role])
        return read_tariff_descriptor(config, self._root)

    async def validate_host(self) -> None:
        try:
            config, manifest = self.config, self.config.manifest
            tariff = self._local()
            _require(await self._tariff.snapshot_sha256() == tariff.snapshot_sha256)
            actual = await self._image.observe(config.bifrost_container_id)
            _require(isinstance(actual, CandidateRuntimeObservation) and actual.image_sha256 == manifest.bifrost_image_sha256
                     and actual.runtime_sha256 == config.expected_runtime_sha256 and actual.hardened_launch
                     and isinstance(actual.integrity, CandidateIntegrityObservation)
                     and actual.integrity.namespace_sha256 == config.expected_integrity_sha256)
            mounted = dict(actual.bind_mounts)
            _require(len(mounted) == len(actual.bind_mounts)
                     and set(mounted) == set(BIFROST_BIND_PATHS) | _SECRET_DESTINATIONS)
            for destination, relative in BIFROST_BIND_PATHS.items():
                _require(mounted[destination] == str(self._root / relative))
            assert actual.integrity is not None
            facts = {path: digest for path, _, digest in actual.integrity.files}
            for destination, source in mounted.items():
                _require(facts[destination] == _sha(_read_file(Path(source))))
            # A local edit during either external observation cannot be accepted
            # merely because its earlier digest matched the immutable startup.
            _require(self._local() == tariff)
        except Exception:
            # Injected observer/source failures cannot leak credentials or grant
            # execution. Cancellation is BaseException and remains cancellation.
            raise CandidateRunDenied("HOST_UNCONFIGURED") from None

    async def validate(self, body: CandidateBody, manifest: CandidateRunManifest) -> None:
        _require(isinstance(body, CandidateBody) and canonicalize_candidate_body(body.content) == body and manifest == self.config.manifest)
        await self.validate_host()


class GuardedCandidateControl:
    """Final host revalidation before onceclaim; accounting survives revocation."""
    def __init__(self, service: CandidateControlPort, gate: HostValidationPort) -> None:
        self._service, self._gate = service, gate

    async def claim(self, request: CandidateClaimRequest) -> CandidateClaimedAttempt:
        try:
            await self._gate.validate_host()
        except CandidateRunDenied:
            raise CandidateControlDenied() from None
        return await self._service.claim(request)

    async def settle(self, request: CandidateSettlementRequest) -> CandidateSettlementResult:
        return await self._service.settle(request)
