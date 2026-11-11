"""Container entrypoint must not let uvicorn replace the redacting logging configuration (ADR-037)."""
from unittest.mock import patch

from ai_res.api import serve


def test_uvicorn_started_with_logging_disabled_and_app_factory():
    with patch("ai_res.api.serve.uvicorn.run") as run:
        serve.main()
    (target,), kw = run.call_args
    assert target == "ai_res.api.app:create_app_from_env"
    assert kw["factory"] is True
    assert kw["log_config"] is None
    assert kw["access_log"] is False
    assert kw["proxy_headers"] is False
    assert kw["server_header"] is False


def test_app_factory_target_resolves_to_a_callable():
    """The uvicorn import string must point at a real factory (a typo would only surface when the container starts)."""
    import importlib

    module, _, attr = "ai_res.api.app:create_app_from_env".partition(":")
    assert callable(getattr(importlib.import_module(module), attr))
