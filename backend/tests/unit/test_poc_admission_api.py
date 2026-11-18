"""Isolated ASGI control tests; service-token signatures are real, no model calls."""
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_res.api.poc_admission_api import create_poc_admission_app
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, ServiceTokenVerifier
from ai_res.modules.model_registry.poc_control import (
    BODY_CODEC_VERSION,
    CONTROL_VERSION,
    CandidateClaimedAttempt,
    CandidateClaimRequest,
    CandidateControlDenied,
    CandidateControlUnavailable,
    CandidateSettlementResult,
)
from ai_res.platform.ports import ServiceName

BODY = {"version": "flash-candidate-control/0.1", "codecVersion": "flash-candidate-body/0.1", "templateCase": "TEXT",
        "bodySha256": "a" * 64, "payloadBytes": 128, "stream": False, "maxOutputTokens": 256}


class Control:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def claim(self, request):
        self.calls.append(request)
        if self.failure:
            raise self.failure
        return CandidateClaimedAttempt(UUID(int=1), "fixture-request", request.body_sha256, request.payload_bytes, request.stream, request.max_output_tokens)

    async def settle(self, request):
        self.calls.append(request)
        if self.failure:
            raise self.failure
        return CandidateSettlementResult(request.attempt_id, request.outcome)


@pytest.fixture
def credentials():
    keys = {name: Ed25519PrivateKey.generate() for name in (ServiceName.LLM_GATEWAY, ServiceName.MANAGER_RUNTIME)}
    public = {name: (key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),) for name, key in keys.items()}
    verifier = ServiceTokenVerifier(public, max_ttl=timedelta(minutes=2))

    def issue(name=ServiceName.LLM_GATEWAY, audience=ServiceName.API):
        return ServiceTokenIssuer(name, keys[name], max_ttl=timedelta(minutes=2)).issue(audience, timedelta(minutes=1))

    return verifier, issue


async def test_default_disabled_and_plaintext_never_call_verifier_or_service(credentials):
    verifier, issue = credentials
    control = Control()
    for enabled, base, expected in ((False, "https://candidate", 503), (True, "http://candidate", 403)):
        app = create_poc_admission_app(control, verifier, enabled=enabled)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=base) as client:
            response = await client.post("/candidate/v1/claim", json=BODY, headers={"authorization": "Bearer " + issue()})
        assert response.status_code == expected and control.calls == []


async def test_https_signed_gateway_claim_and_settlement_have_only_fixed_wire_fields(credentials):
    verifier, issue = credentials
    control = Control()
    app = create_poc_admission_app(control, verifier, enabled=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://candidate") as client:
        claim = await client.post("/candidate/v1/claim", json=BODY, headers={"authorization": "Bearer " + issue()})
        assert claim.status_code == 200
        assert claim.json() == {"version": CONTROL_VERSION, "attemptId": str(UUID(int=1)), "requestRef": "fixture-request",
                                "bodySha256": "a" * 64, "payloadBytes": 128, "stream": False, "maxOutputTokens": 256}
        settlement = await client.post("/candidate/v1/settlement", json={"version": CONTROL_VERSION, "attemptId": str(UUID(int=1)),
            "bodySha256": "a" * 64, "outcome": "UNKNOWN", "reason": "TIMEOUT"}, headers={"authorization": "Bearer " + issue()})
        assert settlement.status_code == 200 and settlement.json() == {"version": CONTROL_VERSION, "attemptId": str(UUID(int=1)), "outcome": "UNKNOWN"}
    assert control.calls[0].codec_version == BODY_CODEC_VERSION


@pytest.mark.parametrize("mode,status", [("missing", 401), ("garbage", 401), ("wrong-service", 403), ("wrong-audience", 401), ("cookie", 400)])
async def test_wrong_identity_audience_cookie_and_absent_auth_refuse(credentials, mode, status):
    verifier, issue = credentials
    headers = {}
    if mode == "garbage":
        headers["authorization"] = "Bearer invalid-fixture"
    elif mode != "missing":
        if mode == "wrong-service":
            token = issue(ServiceName.MANAGER_RUNTIME)
        elif mode == "wrong-audience":
            token = issue(audience=ServiceName.WORKER_RUNTIME)
        else:
            token = issue()
        headers["authorization"] = "Bearer " + token
    if mode == "cookie":
        headers["cookie"] = "ai_res_session=fixture"
    control = Control()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, verifier, enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", json=BODY, headers=headers)
    assert response.status_code == status and control.calls == []


@pytest.mark.parametrize("change", [{"accountId": str(UUID(int=9))}, {"price": 0}, {"templateCase": "UNKNOWN"}, {"version": "other/99"},
                                   {"codecVersion": "other/99"}, {"payloadBytes": True}, {"stream": 1}, {"maxOutputTokens": 257}])
async def test_claim_rejects_unknown_scope_fields_versions_and_coercions(credentials, change):
    verifier, issue = credentials
    control = Control()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, verifier, enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", json=BODY | change, headers={"authorization": "Bearer " + issue()})
    assert response.status_code == 400 and control.calls == []


@pytest.mark.parametrize("raw,status", [(b'{"version":"x","version":"y"}', 400), (b'{"x":NaN}', 400), (b"\xff", 400), (b"x" * 4097, 413)])
async def test_raw_duplicate_nonfinite_unicode_and_oversize_are_bounded(credentials, raw, status):
    verifier, issue = credentials
    control = Control()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, verifier, enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", content=raw,
                                     headers={"authorization": "Bearer " + issue(), "content-type": "application/json"})
    assert response.status_code == status and control.calls == []


@pytest.mark.parametrize("failure,status", [(CandidateControlDenied(), 409), (CandidateControlUnavailable(), 503),
                                           (RuntimeError("private-fixture-body"), 503)])
async def test_service_failures_never_echo_private_details(credentials, failure, status):
    verifier, issue = credentials
    control = Control()
    control.failure = failure
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, verifier, enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", json=BODY, headers={"authorization": "Bearer " + issue()})
    assert response.status_code == status and "private-fixture-body" not in response.text


@pytest.mark.parametrize("facts", [
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "inputTokens": 2_000_001},
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "outputTokens": None},
    {"outcome": "UNKNOWN", "reason": "TIMEOUT", "providerRequestRef": "provider-fixture"},
    {"outcome": "KNOWN", "inputTokens": 10, "outputTokens": 2, "providerRequestRef": "provider-fixture", "reason": None},
])
async def test_mixed_settlement_fields_become_invalid_usage_even_when_explicit_null(credentials, facts):
    verifier, issue = credentials
    control = Control()
    control.failure = CandidateControlDenied()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, verifier, enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/settlement", json={"version": CONTROL_VERSION, "attemptId": str(UUID(int=1)),
            "bodySha256": "a" * 64, **facts}, headers={"authorization": "Bearer " + issue()})
    assert response.status_code == 409 and len(control.calls) == 1
    assert control.calls[0].outcome == "INVALID_USAGE"


@pytest.mark.parametrize("template,stream,cap", [("TEXT", True, 256), ("SSE", False, 256), ("CANCEL", False, 256), ("TEXT", False, 255)])
def test_claim_dto_refuses_metadata_impossible_for_the_versioned_codec(template, stream, cap):
    with pytest.raises(CandidateControlDenied):
        CandidateClaimRequest(BODY_CODEC_VERSION, template, "a" * 64, 128, stream, cap)


async def test_verifier_outage_is_safe_unavailable_and_never_calls_service(credentials):
    _, issue = credentials

    class UnavailableVerifier:
        async def verify_service_token(self, token, audience):
            raise RuntimeError("private-verifier-fixture")

    control = Control()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, UnavailableVerifier(), enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", json=BODY, headers={"authorization": "Bearer " + issue()})
    assert response.status_code == 503 and control.calls == []
    assert response.json() == {"error": {"code": "CANDIDATE_CONTROL_UNAVAILABLE"}}
    assert "private-verifier-fixture" not in response.text


async def test_duplicate_authorization_never_calls_verifier_or_service(credentials):
    _, issue = credentials

    class MustNotVerify:
        async def verify_service_token(self, token, audience):
            pytest.fail("Duplicate authorization reached token verification")

    control = Control()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_poc_admission_app(control, MustNotVerify(), enabled=True)),
                                 base_url="https://candidate") as client:
        response = await client.post("/candidate/v1/claim", json=BODY,
                                     headers=[("authorization", "Bearer " + issue()), ("authorization", "Bearer " + issue())])
    assert response.status_code == 401 and control.calls == []
    assert response.json() == {"error": {"code": "AUTHENTICATION_REQUIRED"}}
