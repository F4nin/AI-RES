"""`python -m ai_res.api.serve_internal` - the internal Platform API listener (port 8001, `runtime` network only; never behind the reverse proxy)."""
import os
from collections.abc import Mapping

import uvicorn
from fastapi import FastAPI

from ai_res.api.internal_api import create_internal_app
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.service_tokens import verifier_from_settings
from ai_res.modules.operations.orchestration_service import OperationOrchestrationService
from ai_res.platform.config import load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.redaction import configure_logging


def create_internal_app_from_env(env: Mapping[str, str] | None = None) -> FastAPI:
    settings = load_settings(os.environ if env is None else env)
    configure_logging(settings.log_level)
    telemetry = install_telemetry(settings, "ai-res-platform-api")  # fail-open
    verifier = verifier_from_settings(settings)  # missing public-key registry => refuses to start (fail closed)
    return create_internal_app(OperationOrchestrationService(create_session_factory(create_runtime_engine(settings, telemetry_name="platform-api"))), verifier,
                               tracer_provider=telemetry.tracer_provider)


def main() -> None:
    uvicorn.run("ai_res.api.serve_internal:create_internal_app_from_env", factory=True, host="0.0.0.0", port=8001,  # noqa: S104 - container-internal bind
                log_config=None, access_log=False, server_header=False, proxy_headers=False)


if __name__ == "__main__":
    main()
