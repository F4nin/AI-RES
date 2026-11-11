"""Container entrypoint: `python -m ai_res.api.serve`. Starts uvicorn with its own logging configuration disabled
(log_config=None) so that the redacting handlers installed by create_app_from_env remain the only log path (ADR-037)."""
import uvicorn


def main() -> None:
    uvicorn.run(
        "ai_res.api.app:create_app_from_env",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container-internal bind; the app network is `internal` and nothing publishes this port
        port=8000,
        log_config=None,
        access_log=False,
        server_header=False,
        proxy_headers=False,  # X-Forwarded-* trust is decided by the application (ADR-020), not by uvicorn defaults
    )


if __name__ == "__main__":
    main()
