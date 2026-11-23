"""ar2 binds the exact private request and stays separate from ar1."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_res.modules.iam.platform_credentials import (
    PlatformAction,
    PlatformCredentialIssuer,
    PlatformCredentialLimits,
    PlatformCredentialVerifier,
    PlatformRequest,
)
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer
from ai_res.platform.ports import ServiceName

TTL = timedelta(seconds=30)
NOW = datetime(2026, 11, 18, tzinfo=UTC)


@pytest.fixture
def credentials():
    key = Ed25519PrivateKey.generate()
    limits = PlatformCredentialLimits(TTL, timedelta(seconds=2), 256, 2048)
    clock = lambda: NOW  # noqa: E731 - fixed boundary for issuer and verifier
    request = PlatformRequest(PlatformAction.ACKNOWLEDGE_START, uuid4(), b'{"workflowId":"fixture"}')
    issuer = PlatformCredentialIssuer(key, limits, clock=clock)
    verifier = PlatformCredentialVerifier([key.public_key()], limits, clock=clock)
    return key, limits, issuer, verifier, request


def verify(verifier, token, request, *, method="POST", path=None, query=b""):
    return verifier.verify(token, request, received_method=method, received_path=path or request.path.encode(), received_query=query)


def test_exact_bound_request_and_distinct_nonces_on_semantic_retry(credentials):
    _, _, issuer, verifier, request = credentials
    assignment = uuid4()
    first = verify(verifier, issuer.issue(request, assignment_id=assignment, ttl=TTL), request)
    second = verify(verifier, issuer.issue(request, assignment_id=assignment, ttl=TTL), request)
    assert first is not None and second is not None
    assert first.assignment_id == second.assignment_id == assignment
    assert first.nonce != second.nonce
    assert first.expires_at == NOW + TTL


def test_changed_request_or_transport_shape_denies(credentials):
    _, _, issuer, verifier, request = credentials
    token = issuer.issue(request, assignment_id=uuid4(), ttl=TTL)
    for change in (
        replace(request, body=request.body + b" "),
        replace(request, action=PlatformAction.RECORD_FAILURE),
        replace(request, operation_id=uuid4()),
    ):
        assert verify(verifier, token, change) is None
    assert verify(verifier, token, request, method="GET") is None
    assert verify(verifier, token, request, path=request.path.encode() + b"?unexpected=1") is None
    assert verify(verifier, token, request, query=b"unexpected=1") is None


def test_expiry_bad_signature_wrong_key_and_ar1_fail_closed(credentials):
    key, limits, issuer, verifier, request = credentials
    token = issuer.issue(request, assignment_id=uuid4(), ttl=TTL)
    expired = PlatformCredentialVerifier([key.public_key()], limits, clock=lambda: NOW + TTL)
    wrong_key = PlatformCredentialVerifier([Ed25519PrivateKey.generate().public_key()], limits, clock=lambda: NOW)
    for target in (expired, wrong_key):
        assert verify(target, token, request) is None
    assert verify(verifier, token + "=", request) is None
    ar1 = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, key, max_ttl=TTL, clock=lambda: NOW)
    assert verify(verifier, ar1.issue(ServiceName.API, TTL), request) is None
