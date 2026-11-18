"""Host settings remain explicit, closed and separate from product settings."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider

from ai_res.api import serve_candidate
from ai_res.modules.model_registry.poc_control import CandidateSettlementResult
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceIdentity, ServiceName


def host_env():
    return {"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_USER": "ai_res_api", "AI_RES_CANDIDATE_CONTROL_ENABLED": "true",
            "AI_RES_CANDIDATE_TLS_CERT_FILE": "/mounted/cert", "AI_RES_CANDIDATE_TLS_KEY_FILE": "/mounted/key",
            "AI_RES_CANDIDATE_ACCOUNT_ID": str(uuid4()), "AI_RES_CANDIDATE_PLAN_SHA256": "b" * 64,
            "AI_RES_CANDIDATE_TARIFF_SHA256": "c" * 64}


def test_explicit_host_namespace_does_not_break_the_closed_product_settings_parser(monkeypatch):
    seen = []
    real_parser = serve_candidate.load_settings

    def parse(env):
        seen.append(env)
        return real_parser(env)

    monkeypatch.setattr(serve_candidate, "serving_tls", lambda env: None)
    monkeypatch.setattr(serve_candidate, "load_settings", parse)
    monkeypatch.setattr(serve_candidate, "verifier_from_settings", lambda settings: object())
    monkeypatch.setattr(serve_candidate, "create_runtime_engine", lambda *args, **kwargs: object())
    monkeypatch.setattr(serve_candidate, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(serve_candidate, "CandidateControlService", lambda *args: object())
    monkeypatch.setattr(serve_candidate, "configure_logging", lambda level: None)
    monkeypatch.setattr(serve_candidate, "install_telemetry", lambda *args: SimpleNamespace(tracer_provider=TracerProvider()))
    app = serve_candidate.create_candidate_control_from_env(host_env())
    assert app is not None and seen == [{"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_USER": "ai_res_api"}]


@pytest.mark.parametrize("mutation", [{"AI_RES_CANDIDATE_CONTROL_ENABLED": "false"}, {"AI_RES_CANDIDATE_PLAN_SHA265": "wrong"},
                                     {"AI_RES_CANDIDATE_ACCOUNT_ID": "invalid"}, {"AI_RES_DB_USER": "ai_res_migrator"}])
def test_absent_activation_and_invalid_host_configuration_refuse_before_serving(monkeypatch, mutation):
    monkeypatch.setattr(serve_candidate, "serving_tls", lambda env: None)
    with pytest.raises(RuntimeError):
        serve_candidate.create_candidate_control_from_env(host_env() | mutation)


@pytest.mark.parametrize("construction_failure", [False, True])
async def test_environment_listener_never_grants_claims_and_closes_accounting_engine(monkeypatch, construction_failure):
    events = []

    class Verifier:
        async def verify_service_token(self, token, audience):
            return ServiceIdentity(name=ServiceName.LLM_GATEWAY, audience=ServiceName.API, expires_at=utc_now() + timedelta(minutes=1))

    class Engine:
        async def dispose(self):
            events.append("closed")

    class Control:
        def __init__(self, *args):
            if construction_failure:
                raise ValueError("fixture construction failure")

        async def claim(self, request):
            pytest.fail("env-only listener bypassed trusted host gate")

        async def settle(self, request):
            events.append("accounted")
            return CandidateSettlementResult(request.attempt_id, request.outcome)

    monkeypatch.setattr(serve_candidate, "serving_tls", lambda env: None)
    monkeypatch.setattr(serve_candidate, "verifier_from_settings", lambda settings: Verifier())
    monkeypatch.setattr(serve_candidate, "create_runtime_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(serve_candidate, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(serve_candidate, "CandidateControlService", Control)
    monkeypatch.setattr(serve_candidate, "configure_logging", lambda level: None)
    monkeypatch.setattr(serve_candidate, "install_telemetry", lambda *args: SimpleNamespace(tracer_provider=TracerProvider()))
    app = serve_candidate.create_candidate_control_from_env(host_env())

    async def run():
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://candidate") as client:
            headers = {"authorization": "Bearer fixture-service-token"}
            claim = await client.post("/candidate/v1/claim", json={"version": "flash-candidate-control/0.1",
                "codecVersion": "flash-candidate-body/0.1", "templateCase": "TEXT", "bodySha256": "a" * 64,
                "payloadBytes": 128, "stream": False, "maxOutputTokens": 256}, headers=headers)
            assert claim.status_code == 409
            settled = await client.post("/candidate/v1/settlement", json={"version": "flash-candidate-control/0.1",
                "attemptId": str(uuid4()), "bodySha256": "a" * 64, "outcome": "UNKNOWN", "reason": "TIMEOUT"}, headers=headers)
            assert settled.status_code == 200

    if construction_failure:
        with pytest.raises(ValueError):
            await run()
        assert events == ["closed"]
    else:
        await run()
        assert events == ["accounted", "closed"]
