"""Actual private-CA TLS and signed service auth, with a local fake control port.

No provider calls or production credentials. PG semantics have separate tests;
these tests distinguish a real TLS listener from an ASGI `scheme=https` fixture.
"""
import asyncio
import base64
import socket
import ssl
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from starlette.responses import JSONResponse

from ai_res.api import serve_candidate
from ai_res.api.poc_admission_api import create_poc_admission_app
from ai_res.llm.adapters.candidate_control import CandidateControlClient, CandidateControlUnavailable
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, ServiceTokenVerifier
from ai_res.modules.model_registry.poc_control import CandidateClaimedAttempt, CandidateControlDenied, CandidateSettlementResult
from ai_res.platform.ports import ServiceName


def certificates(directory, *, hostname="llm-poc-control"):
    directory.mkdir(mode=0o700)
    now = datetime.now(UTC)
    ca_key, server_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(2))
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic candidate test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                      data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                      encipher_only=None, decipher_only=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    server = (x509.CertificateBuilder().subject_name(server_name).issuer_name(ca_name).public_key(server_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
              .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                          data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                          encipher_only=None, decipher_only=None), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
              .sign(ca_key, hashes.SHA256()))
    ca_file, cert_file, key_file = (directory / name for name in ("ca.pem", "server.pem", "server.key"))
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(server.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
    for path in (ca_file, cert_file, key_file):
        path.chmod(0o600)
    return ca_file, cert_file, key_file


class Control:
    """Local test double, never evidence of PostgreSQL durable accounting."""
    def __init__(self):
        self.claims, self.settlements = [], []
        self.attempt = uuid4()

    async def claim(self, request):
        if self.claims:
            raise CandidateControlDenied()
        self.claims.append(request)
        return CandidateClaimedAttempt(self.attempt, "synthetic-tls-probe", request.body_sha256, request.payload_bytes,
                                       request.stream, request.max_output_tokens)

    async def settle(self, request):
        self.settlements.append(request)
        return CandidateSettlementResult(self.attempt, request.outcome)


@pytest.fixture
def tls_server(tmp_path, monkeypatch):
    real_resolver = socket.getaddrinfo

    def resolver(host, *args, **kwargs):
        if host in ("llm-poc-control", b"llm-poc-control"):
            host = "127.0.0.1"
        return real_resolver(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    servers = []

    def start(*, hostname="llm-poc-control", lose_settlement_ack=False, delay_settlement_ack=0, service=None):
        ca, cert, key = certificates(tmp_path / str(len(servers)), hostname=hostname)
        signing = {name: Ed25519PrivateKey.generate() for name in (ServiceName.LLM_GATEWAY, ServiceName.MANAGER_RUNTIME)}
        public = {name: (value.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),)
                  for name, value in signing.items()}
        verifier = ServiceTokenVerifier(public, max_ttl=timedelta(minutes=2))
        control = service if service is not None else Control()
        settlement_recorded = threading.Event()
        inner = create_poc_admission_app(control, verifier, enabled=True)

        async def app(scope, receive, send):
            # A non-success ACK after the service recorded its fact. The client
            # cannot infer pending from this: DB-backed integration is separate.
            if (lose_settlement_ack or delay_settlement_ack) and scope.get("path") == "/candidate/v1/settlement":
                async def discard(message):
                    pass
                await inner(scope, receive, discard)
                settlement_recorded.set()
                if delay_settlement_ack:
                    await asyncio.sleep(delay_settlement_ack)
                await JSONResponse({"error": {"code": "CANDIDATE_CONTROL_UNAVAILABLE"}}, status_code=503)(scope, receive, send)
            else:
                await inner(scope, receive, send)

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", ssl_certfile=str(cert), ssl_keyfile=str(key),
                                ssl_version=ssl.PROTOCOL_TLS_SERVER, proxy_headers=False, access_log=False,
                                log_config=None, log_level="critical")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        servers.append((server, thread, sock))
        deadline = time.monotonic()+5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Synthetic private TLS listener did not start."

        def issue(service=ServiceName.LLM_GATEWAY, audience=ServiceName.API):
            return ServiceTokenIssuer(service, signing[service], max_ttl=timedelta(minutes=2)).issue(audience, timedelta(minutes=1))

        return SimpleNamespace(url=f"https://llm-poc-control:{port}", ca=ca, cert=cert, key=key, issue=issue, control=control,
                               port=port, settlement_recorded=settlement_recorded, signing_keys=signing)

    yield start
    for server, thread, sock in reversed(servers):
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive(), "Synthetic TLS listener did not stop."


async def test_real_private_tls_signed_identity_claim_and_settlement(tls_server, monkeypatch):
    host = tls_server()
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    body = build_candidate_body("TEXT", uuid4())
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue) as client:
        receipt = await client.claim(body)
        await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="synthetic-tls-provider")
        with pytest.raises(CandidateControlUnavailable):
            await client.claim(body)
    assert len(host.control.claims) == len(host.control.settlements) == 1


@pytest.mark.parametrize("failure", ["wrong-ca", "wrong-hostname", "wrong-service", "wrong-audience"])
async def test_real_tls_or_service_identity_failure_never_reaches_control(tls_server, failure):
    host = tls_server(hostname="different-host" if failure == "wrong-hostname" else "llm-poc-control")
    ca = tls_server().ca if failure == "wrong-ca" else host.ca
    def supplier():
        if failure == "wrong-service":
            return host.issue(ServiceName.MANAGER_RUNTIME)
        if failure == "wrong-audience":
            return host.issue(audience=ServiceName.WORKER_RUNTIME)
        return host.issue()
    async with CandidateControlClient(host.url, ca_file=ca, token_supplier=supplier) as client:
        with pytest.raises(CandidateControlUnavailable):
            await client.claim(build_candidate_body("TEXT", uuid4()))
    assert host.control.claims == []


async def test_non_success_ack_after_recording_does_not_trigger_conflicting_unknown(tls_server):
    host = tls_server(lose_settlement_ack=True)
    async with CandidateControlClient(host.url, ca_file=host.ca, token_supplier=host.issue) as client:
        receipt = await client.claim(build_candidate_body("TEXT", uuid4()))
        with pytest.raises(CandidateControlUnavailable):
            await client.settle_known(receipt, input_tokens=12, output_tokens=2, provider_request_ref="synthetic-provider")
    assert len(host.control.claims) == len(host.control.settlements) == 1
    assert host.control.settlements[0].outcome == "KNOWN"


async def test_forwarded_proto_cannot_turn_plaintext_into_a_tls_connection(tls_server):
    host = tls_server()
    async with httpx.AsyncClient(trust_env=False) as client:
        with pytest.raises(httpx.HTTPError):
            await client.post(f"http://127.0.0.1:{host.port}/candidate/v1/claim", json={}, headers={"x-forwarded-proto": "https"})
    assert host.control.claims == []


def test_serving_requires_valid_mounted_tls_and_disables_proxy_header_trust(tls_server, monkeypatch):
    with pytest.raises(RuntimeError, match="mounted TLS"):
        serve_candidate.serving_tls({})
    host = tls_server()
    assert serve_candidate.serving_tls({"AI_RES_CANDIDATE_TLS_CERT_FILE": str(host.cert),
                                        "AI_RES_CANDIDATE_TLS_KEY_FILE": str(host.key)}) == (host.cert, host.key)
    seen = {}
    monkeypatch.setattr(serve_candidate, "serving_tls", lambda env: (host.cert, host.key))
    monkeypatch.setattr(serve_candidate.uvicorn, "run", lambda *args, **kwargs: seen.update(kwargs))
    serve_candidate.main()
    assert seen["proxy_headers"] is False and seen["ssl_certfile"] and seen["ssl_keyfile"]
    assert seen["access_log"] is False and seen["factory"] is True


@pytest.mark.parametrize("field", ["cert", "key"])
@pytest.mark.parametrize("mutation", ["symlink", "writable", "directory"])
def test_serving_rejects_unsafe_tls_mounts(tls_server, tmp_path, field, mutation):
    host = tls_server()
    source = host.cert if field == "cert" else host.key
    candidate = source
    if mutation == "symlink":
        candidate = tmp_path / "alias.pem"
        candidate.symlink_to(source)
    elif mutation == "writable":
        source.chmod(0o666)
    else:
        candidate = tmp_path / "not-a-file"
        candidate.mkdir()
    cert = candidate if field == "cert" else host.cert
    key = candidate if field == "key" else host.key
    with pytest.raises(RuntimeError, match="mounted TLS"):
        serve_candidate.serving_tls({"AI_RES_CANDIDATE_TLS_CERT_FILE": str(cert), "AI_RES_CANDIDATE_TLS_KEY_FILE": str(key)})


async def test_relay_host_factory_loads_only_its_mounted_gateway_identity(tls_server, tmp_path):
    # Imported test module loads the actual relay script; no provider is started.
    from ..unit.test_llm_egress import relay
    host = tls_server()
    key_file = tmp_path / "gateway.seed"
    key_file.write_bytes(base64.b64encode(host.signing_keys[ServiceName.LLM_GATEWAY].private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())))
    key_file.chmod(0o600)
    env = {"AI_RES_CANDIDATE_SERVICE_KEY_FILE": str(key_file), "AI_RES_CANDIDATE_CA_FILE": str(host.ca),
           "AI_RES_CANDIDATE_CONTROL_URL": host.url, "AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS": "60"}
    async with relay.control_from_env(env) as client:
        await client.claim(build_candidate_body("TEXT", uuid4()))
    assert len(host.control.claims) == 1
    for changes in ({"AI_RES_CANDIDATE_UNKNOWN": "refused"}, {"AI_RES_SERVICE_TOKEN_MAX_TTL_SECONDS": "0"},
                    {"AI_RES_CANDIDATE_CONTROL_URL": "http://llm-poc-control:8443"}):
        with pytest.raises(ValueError, match="configuration unavailable"):
            relay.control_from_env(env | changes)
    key_file.chmod(0o666)
    with pytest.raises(ValueError, match="configuration unavailable"):
        relay.control_from_env(env)
