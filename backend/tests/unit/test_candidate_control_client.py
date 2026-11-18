"""Private control protocol failures never become a dispatch permission."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from ai_res.llm.adapters.candidate_control import CandidateControlClient, CandidateControlUnavailable
from ai_res.llm.candidate_payload import build_candidate_body


@pytest.fixture
def ca_file(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic control test CA")])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    path = tmp_path / "ca.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def response_for(body, **changes):
    return {"version": "flash-candidate-control/0.1", "attemptId": str(uuid4()), "requestRef": "synthetic-probe",
            "bodySha256": body.body_sha256, "payloadBytes": body.payload_bytes, "stream": body.stream,
            "maxOutputTokens": body.max_output_tokens,
            } | changes


@pytest.mark.parametrize("url", ["http://llm-poc-control:8443", "https://example.com", "https://llm-poc-control/other",
                                  "https://user:pass@llm-poc-control", "https://llm-poc-control?next=1"])
def test_control_endpoint_cannot_be_plaintext_or_an_arbitrary_destination(ca_file, url):
    with pytest.raises(CandidateControlUnavailable):
        CandidateControlClient(url, ca_file=ca_file, token_supplier=lambda: "ar1.fixture.signature")


async def test_claim_exact_binding_then_settlement_uses_fresh_auth_and_no_cookies(ca_file):
    body = build_candidate_body("TEXT", uuid4())
    calls = []
    claim = response_for(body)

    def handle(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer ar1.fixture.signature"
        assert "cookie" not in request.headers
        data = json.loads(request.content)
        assert "accountId" not in data and "cost" not in data
        if request.url.path.endswith("/claim"):
            assert data["bodySha256"] == body.body_sha256 and data["codecVersion"] == "flash-candidate-body/0.1"
            return httpx.Response(200, json=claim, headers={"set-cookie": "untrusted=scope"})
        assert data["attemptId"] == claim["attemptId"] and data["outcome"] == "KNOWN"
        return httpx.Response(200, json={"version": claim["version"], "attemptId": claim["attemptId"], "outcome": "KNOWN"})

    async with CandidateControlClient("https://llm-poc-control:8443", ca_file=ca_file,
                                      token_supplier=lambda: "ar1.fixture.signature", http_transport=httpx.MockTransport(handle)) as client:
        receipt = await client.claim(body)
        await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="provider-fixture")
    assert len(calls) == 2


@pytest.mark.parametrize("change", [{"version": "unexpected"}, {"bodySha256": "f" * 64}, {"attemptId": "invalid"},
                                    {"stream": 1}, {"payloadBytes": 1}, {"maxOutputTokens": 257}, {"extra": "not-allowed"}])
async def test_malformed_or_mismatched_claim_response_is_refused(ca_file, change):
    body = build_candidate_body("TEXT", uuid4())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_for(body, **change)))
    async with CandidateControlClient("https://llm-poc-control:8443", ca_file=ca_file,
                                      token_supplier=lambda: "ar1.fixture.signature", http_transport=transport) as client:
        with pytest.raises(CandidateControlUnavailable):
            await client.claim(body)


@pytest.mark.parametrize("status", [301, 401, 403, 409, 500, 503])
async def test_no_retry_redirect_or_upstream_error_detail_on_failed_claim(ca_file, status):
    body = build_candidate_body("TEXT", uuid4())
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, content=b"sensitive-upstream-detail", headers={"location": "https://example.com"})

    async with CandidateControlClient("https://llm-poc-control:8443", ca_file=ca_file,
                                      token_supplier=lambda: "ar1.fixture.signature", http_transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(CandidateControlUnavailable) as failure:
            await client.claim(body)
    assert len(calls) == 1 and "sensitive-upstream-detail" not in str(failure.value)


async def test_untrusted_usage_is_not_forwarded_as_known_or_with_raw_values(ca_file):
    body = build_candidate_body("TEXT", uuid4())
    claim = response_for(body)
    seen = []

    def handle(request):
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json=claim)
        seen.append(json.loads(request.content))
        return httpx.Response(409)

    async with CandidateControlClient("https://llm-poc-control:8443", ca_file=ca_file,
                                      token_supplier=lambda: "ar1.fixture.signature", http_transport=httpx.MockTransport(handle)) as client:
        receipt = await client.claim(body)
        with pytest.raises(CandidateControlUnavailable):
            await client.settle_known(receipt, input_tokens=True, output_tokens=-1, provider_request_ref="unsafe\nvalue")
    assert seen[0]["outcome"] == "INVALID_USAGE"
    assert "unsafe" not in json.dumps(seen) and "inputTokens" not in seen[0]
