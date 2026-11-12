"""`python -m ai_res.runtime.manager` - Manager Runtime: hosts OperationWorkflow and the Manager Activities on task queue `ai-res-manager`.
Holds NO database credentials; changes the domain only via the internal Platform API with its own short-lived service token (issuer MANAGER_RUNTIME)."""
from datetime import timedelta

from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, load_private_key
from ai_res.orchestration.client import connect
from ai_res.orchestration.http_platform import TOKEN_TTL, HttpOperationPlatform
from ai_res.orchestration.workers import manager_worker
from ai_res.platform.config import ConfigError, Settings
from ai_res.platform.ports import ServiceName
from ai_res.runtime.lifecycle import main_of, run_worker_until_stopped


async def run(settings: Settings) -> None:
    if not settings.platform_api_url or settings.service_signing_key_file is None:
        raise ConfigError("platform_api_url and service_signing_key_file are required for the Manager Runtime")
    issuer = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, load_private_key(settings.service_signing_key_file),
                                max_ttl=timedelta(seconds=settings.service_token_max_ttl_seconds))
    platform = HttpOperationPlatform(settings.platform_api_url, lambda: issuer.issue(ServiceName.API, TOKEN_TTL),
                                     timeout_seconds=settings.platform_api_timeout_seconds)
    try:
        await run_worker_until_stopped(manager_worker(await connect(settings), platform))
    finally:
        await platform.aclose()


def main() -> int:
    return main_of(run, service="ai-res-manager-runtime")


if __name__ == "__main__":
    raise SystemExit(main())
