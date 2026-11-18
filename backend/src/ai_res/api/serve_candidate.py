"""Separate TLS-only candidate control listener; no product app is mounted here.

This reads explicit host configuration and existing mounted credentials. It never
creates accounts, approves models or establishes tariff freshness. Missing TLS,
activation or a fixed account/manifest refuses startup. Provider calls remain a
separate relay decision after all candidate preparation gates are satisfied.
"""
import os
import re
import ssl
import stat
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import uvicorn
from starlette.applications import Starlette

from ai_res.api.poc_admission_api import create_poc_admission_app
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.service_tokens import verifier_from_settings
from ai_res.modules.model_registry.poc_control import (
    CandidateClaimedAttempt,
    CandidateClaimRequest,
    CandidateControlDenied,
    CandidateControlService,
    CandidateControlUnavailable,
    CandidateSettlementRequest,
    CandidateSettlementResult,
)
from ai_res.platform.config import load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.redaction import configure_logging
from ai_res.platform.telemetry import TelemetryMiddleware

_HOST_KEYS = frozenset({"AI_RES_CANDIDATE_CONTROL_ENABLED", "AI_RES_CANDIDATE_TLS_CERT_FILE", "AI_RES_CANDIDATE_TLS_KEY_FILE",
                        "AI_RES_CANDIDATE_ACCOUNT_ID", "AI_RES_CANDIDATE_PLAN_SHA256", "AI_RES_CANDIDATE_TARIFF_SHA256"})


def _safe_tls_file(path: Path) -> None:
    # O_NONBLOCK also prevents a substituted FIFO from hanging before fstat.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not 0 < info.st_size <= 65_536:
            raise ValueError("unsafe mounted TLS file")


def serving_tls(env: Mapping[str, str]) -> tuple[Path, Path]:
    """Validate mounted certificate/key before a listener is permitted to start."""
    try:
        certificate = Path(env["AI_RES_CANDIDATE_TLS_CERT_FILE"])
        key = Path(env["AI_RES_CANDIDATE_TLS_KEY_FILE"])
        # Files are mounted read-only by composition; reject unsafe properties
        # before handing their paths to the TLS library. Never echo PEM bytes.
        _safe_tls_file(certificate)
        _safe_tls_file(key)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate, key)
        return certificate, key
    except Exception:
        raise RuntimeError("Candidate control requires valid mounted TLS credentials.") from None


def create_candidate_control_from_env(env: Mapping[str, str] | None = None) -> Starlette:
    source = os.environ if env is None else env
    if source.get("AI_RES_CANDIDATE_CONTROL_ENABLED") != "true":
        raise RuntimeError("Candidate control activation is not configured.")
    serving_tls(source)
    try:
        if any(key.startswith("AI_RES_CANDIDATE_") and key not in _HOST_KEYS for key in source):
            raise ValueError("unknown candidate host configuration")
        # Settings deliberately rejects unknown AI_RES_* keys. Candidate host
        # configuration has its own closed namespace; do not feed it into the
        # product settings parser or silently ignore misspelled host fields.
        settings = load_settings({key: value for key, value in source.items() if key not in _HOST_KEYS})
        if settings.db_user != "ai_res_api":
            raise ValueError("unsupported runtime role")
        account = UUID(source["AI_RES_CANDIDATE_ACCOUNT_ID"])
        verifier = verifier_from_settings(settings)
        plan, tariff = source["AI_RES_CANDIDATE_PLAN_SHA256"], source["AI_RES_CANDIDATE_TARIFF_SHA256"]
        # Validate these even though the engine/service is acquired in lifespan.
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (plan, tariff)):
            raise ValueError("invalid candidate binding")
    except Exception:
        raise RuntimeError("Candidate control fixed host configuration is unavailable.") from None
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-candidate-control")
    service: CandidateControlService | None = None

    class AccountingOnly:
        async def claim(self, request: CandidateClaimRequest) -> CandidateClaimedAttempt:
            # An env toggle is insufficient authority for fresh dispatch. The
            # explicit trusted host composition supplies the claim-side gate.
            raise CandidateControlDenied()

        async def settle(self, request: CandidateSettlementRequest) -> CandidateSettlementResult:
            if service is None:
                raise CandidateControlUnavailable()
            return await service.settle(request)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        nonlocal service
        engine = create_runtime_engine(settings, telemetry_name="candidate-control")
        try:
            service = CandidateControlService(create_session_factory(engine), account, plan, tariff)
            yield
        finally:
            service = None
            await engine.dispose()

    app = create_poc_admission_app(AccountingOnly(), verifier, enabled=True)
    app.router.lifespan_context = lifespan
    app.add_middleware(TelemetryMiddleware, tracer=telemetry.tracer_provider.get_tracer("ai-res-candidate-control"))
    return app


def main() -> None:
    try:
        certificate, key = serving_tls(os.environ)
    except RuntimeError:
        raise SystemExit("Candidate control TLS configuration is unavailable.") from None
    uvicorn.run("ai_res.api.serve_candidate:create_candidate_control_from_env", factory=True,
                host="0.0.0.0", port=8443,  # noqa: S104 - isolated container listener; no host-published port
                ssl_certfile=str(certificate), ssl_keyfile=str(key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
                access_log=False, log_config=None, server_header=False, proxy_headers=False)


if __name__ == "__main__":
    main()
