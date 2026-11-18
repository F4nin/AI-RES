"""Explicit trusted development composition, with no default activation.

The caller supplies host-controlled paths/settings. This module never launches
containers, creates an account, migrates, enrolls secrets or approves a model.
Only the relay holds the provider credential. Docker observation belongs to this
development host, which must never run as Manager/Worker or inside the relay.
"""
import os
import re
import stat
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from ai_res.cli.flash_candidate import source_binding
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.llm.adapters.flash_candidate import FlashCandidateProbe
from ai_res.modules.model_registry.candidate_host import (
    CandidateDevelopmentGate,
    CandidateHostConfig,
    DockerCandidateObserver,
    GuardedCandidateControl,
    OfficialTariffObserver,
    read_tariff_descriptor,
)
from ai_res.modules.model_registry.candidate_host_account import verify_candidate_account
from ai_res.modules.model_registry.candidate_runner import (
    CandidateAccountingReader,
    CandidateRunDenied,
    CandidateRunManifest,
    CandidateRunner,
    JsonlCandidateEvidence,
)
from ai_res.modules.model_registry.poc_budget import TechnicalPaidLedger
from ai_res.modules.model_registry.poc_control import CandidateControlService
from ai_res.platform.config import Settings


def mounted_virtual_key(path: Path) -> str:
    """Read only the runner's virtual key from its protected mount, never echo it."""
    try:
        if not path.is_absolute() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                    or info.st_mode & 0o777 not in {0o400, 0o600} or not 1 <= info.st_size <= 1024):
                raise ValueError()
            data = source.read(1025)
        key = data.decode("ascii")
        # Only the complete virtual-key form produced by the current renderer
        # belongs here. A generic printable credential could be a provider key.
        if key.endswith("\n"):
            key = key[:-1]
        if re.fullmatch(r"sk-bf-[0-9a-f]{64}", key) is None:
            raise ValueError()
        return key
    except (OSError, ValueError, UnicodeError):
        raise CandidateRunDenied("HOST_UNCONFIGURED") from None


def _gate(config: CandidateHostConfig, root: Path, tariff: OfficialTariffObserver,
          docker_observer: DockerCandidateObserver | None = None) -> CandidateDevelopmentGate:
    # The explicit source-checkout host must describe the package actually
    # executing this composition. A different checkout is not an execution ref.
    if root.resolve() != Path(__file__).resolve().parents[4]:
        raise CandidateRunDenied("BINDING_MISMATCH")
    def observe_source() -> tuple[str, str]:
        actual = source_binding(root)
        return actual.code_revision, actual.source_tree_sha256

    return CandidateDevelopmentGate(config, root, source_reader=observe_source, tariff_observer=tariff,
                                    image_observer=docker_observer if docker_observer is not None else DockerCandidateObserver())


@asynccontextmanager
async def candidate_runner_host(config_path: Path, root: Path, evidence_path: Path, settings: Settings,
                                virtual_key_file: Path, *, docker_observer: DockerCandidateObserver | None = None,
                                ) -> AsyncIterator[tuple[CandidateRunner, CandidateRunManifest]]:
    """Actual factory for HostFactory injection; acquiring resources grants no approval."""
    if settings.environment not in {"local", "test"} or settings.db_user != "ai_res_api":
        raise CandidateRunDenied("HOST_UNCONFIGURED")
    config = CandidateHostConfig.load(config_path)
    async with AsyncExitStack() as stack:
        tariff_observer = await stack.enter_async_context(OfficialTariffObserver())
        gate = _gate(config, root, tariff_observer, docker_observer)
        await gate.validate_host()
        tariff = read_tariff_descriptor(config, root)
        engine = create_runtime_engine(settings)
        stack.push_async_callback(engine.dispose)
        factory = create_session_factory(engine)
        await verify_candidate_account(factory, config.account_id, config.manifest, tariff)
        probe = await stack.enter_async_context(FlashCandidateProbe(virtual_key=mounted_virtual_key(virtual_key_file)))
        yield (CandidateRunner(TechnicalPaidLedger(factory, config.account_id), CandidateAccountingReader(factory, config.account_id),
                               probe, gate, JsonlCandidateEvidence(evidence_path)), config.manifest)


@asynccontextmanager
async def candidate_control_host(config_path: Path, root: Path, settings: Settings, *, docker_observer: DockerCandidateObserver | None = None,
                                 ) -> AsyncIterator[GuardedCandidateControl]:
    """For the separate TLS app: validate claims, preserve accounting after revoke.

    Startup parses the fixed trusted config but deliberately does not require
    tariff/network/image availability to record a settlement for an old claim.
    The caller must retain the existing private TLS/service authentication app.
    """
    if settings.environment not in {"local", "test"} or settings.db_user != "ai_res_api":
        raise CandidateRunDenied("HOST_UNCONFIGURED")
    config = CandidateHostConfig.load(config_path)
    async with AsyncExitStack() as stack:
        tariff_observer = await stack.enter_async_context(OfficialTariffObserver())
        engine = create_runtime_engine(settings)
        stack.push_async_callback(engine.dispose)
        factory = create_session_factory(engine)
        service = CandidateControlService(factory, config.account_id, config.manifest.plan_sha256, config.manifest.tariff_sha256)
        gate = _gate(config, root, tariff_observer, docker_observer)
        # Account/rates revalidation is inside every claim, not just startup.
        async def preflight() -> None:
            await gate.validate_host()
            await verify_candidate_account(factory, config.account_id, config.manifest, read_tariff_descriptor(config, root))

        class ClaimGate:
            async def validate_host(self) -> None:
                await preflight()

        yield GuardedCandidateControl(service, ClaimGate())
