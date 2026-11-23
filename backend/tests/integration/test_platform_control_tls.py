"""Real private TLS with a synthetic controller. PostgreSQL authority is tested separately."""
import asyncio
import base64
import json
import socket
import ssl
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_res.api.platform_v2 import create_platform_v2_app
from ai_res.api.serve_platform_v2 import create_listener
from ai_res.application.platform_control import PlatformOperationControl
from ai_res.application.platform_manager import AssignedManagerInput
from ai_res.llm import LLMLimits
from ai_res.modules.iam.platform_credentials import PlatformAction, PlatformCredentialIssuer, PlatformCredentialLimits, PlatformCredentialVerifier
from ai_res.orchestration.contracts import OperationRef, OperationState, workflow_id_for
from ai_res.orchestration.manager_workflows import BoundWorkflowCall
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError
from ai_res.platform.config import ConfigError, load_settings
from ai_res.runtime.manager_reasoning import ManagerReasoningInput, QuestionDisposition
from ai_res.runtime.platform_control_client import ManagerHttpPlatform, PlatformControlClient
from tests.integration.test_candidate_control_tls import certificates


def test_protected_platform_requires_a_native_auth_control_identity(tmp_path):
    ca, crt, key = certificates(tmp_path / "protected-platform", hostname="platform-api")
    public = tmp_path / "manager-public-keys"
    manager = Ed25519PrivateKey.generate()
    public.write_bytes(b"MANAGER_RUNTIME " + base64.b64encode(manager.public_key().public_bytes_raw()) + b"\n")
    settings = load_settings({
        "AI_RES_DB_USER": "ai_res_platform_api", "AI_RES_DB_SSLROOTCERT_FILE": str(ca),
        "AI_RES_SERVICE_PUBLIC_KEYS_FILE": str(public), "AI_RES_PLATFORM_TLS_CERTIFICATE_FILE": str(crt),
        "AI_RES_PLATFORM_TLS_KEY_FILE": str(key), "AI_RES_PLATFORM_REQUEST_MAX_BYTES": "4096",
        "AI_RES_PLATFORM_CREDENTIAL_MAX_BYTES": "2048", "AI_RES_PLATFORM_LISTENER_MAX_CONNECTIONS": "16",
    })
    with pytest.raises(ConfigError, match="dedicated Manager and native auth-control registry"):
        create_listener(settings, require_native_auth=True)


async def test_private_platform_tls_verifies_name_and_ca_and_mints_fresh_nonce(tmp_path, monkeypatch):
    hostname = "platform-v2.test"
    ca, crt, key = certificates(tmp_path / "platform", hostname=hostname)
    other_ca, _, _ = certificates(tmp_path / "untrusted", hostname=hostname)
    resolve = socket.getaddrinfo

    fixture_hosts = (hostname, f"other.{hostname}", hostname.encode(), f"other.{hostname}".encode())

    def resolve_fixture(host, *args, **kwargs):
        return resolve("127.0.0.1" if host in fixture_hosts else host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_fixture)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    keylog = tmp_path / "unexpected-keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog))
    operation_id = uuid4()
    operation = OperationRef(str(operation_id), str(uuid4()), str(uuid4()))
    assignment = uuid4()
    reference = BoundWorkflowCall(operation, str(assignment), workflow_id_for(operation_id), str(uuid4()))
    ttl = timedelta(seconds=20)
    keypair = Ed25519PrivateKey.generate()
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 512, 2048)
    issue = PlatformCredentialIssuer(keypair, limits)
    controller = AsyncMock(spec=PlatformOperationControl)
    controller.execute.return_value = OperationState(str(operation_id), "RUNNING")
    app = create_platform_v2_app(controller, PlatformCredentialVerifier([keypair.public_key()], limits),
                                 max_body_bytes=512, body_timeout_seconds=2)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, ssl_certfile=str(crt), ssl_keyfile=str(key), ssl_version=ssl.PROTOCOL_TLS_SERVER,
            proxy_headers=False, access_log=False, log_config=None, log_level="critical",
        )
        server = uvicorn.Server(config)
        serve = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
            for host, ca_file in ((hostname, other_ca), (f"other.{hostname}", ca)):
                wrong = PlatformControlClient(f"https://{host}:{port}", ca_file=ca_file, issuer=issue, ttl=ttl, timeout_seconds=2)
                try:
                    with pytest.raises(PlatformTransientError):
                        await wrong.call(reference, PlatformAction.ACKNOWLEDGE_START)
                finally:
                    await wrong.aclose()
            controller.execute.assert_not_awaited()

            with pytest.raises(ValueError, match="private HTTPS origin"):
                PlatformControlClient(f"http://{hostname}:{port}", ca_file=ca, issuer=issue, ttl=ttl, timeout_seconds=2)

            client = PlatformControlClient(f"https://{hostname}:{port}", ca_file=ca, issuer=issue, ttl=ttl, timeout_seconds=2)
            try:
                for _ in range(2):
                    assert await client.call(reference, PlatformAction.ACKNOWLEDGE_START) == OperationState(str(operation_id), "RUNNING")
                controller.execute.return_value = AssignedManagerInput(str(operation_id), "Private intake")
                adaptive = await client.read_adaptive_manager_input(reference)
                assert adaptive.message == "Private intake" and adaptive.questions == () and adaptive.history_truncated is False
            finally:
                await client.aclose()
            received = [call.args[0] for call in controller.execute.await_args_list]
            assert len(received) == 3
            assert {claim.assignment_id for claim in received} == {assignment}
            assert len({claim.nonce for claim in received}) == 3
            assert not keylog.exists()
        finally:
            server.should_exit = True
            await asyncio.wait_for(serve, timeout=5)


async def test_adaptive_client_checks_bounded_wire_before_building_reasoning_input(tmp_path):
    hostname = "platform-v4.test"
    ca, _, _ = certificates(tmp_path / "adaptive", hostname=hostname)
    operation_id = uuid4()
    operation = OperationRef(str(operation_id), str(uuid4()), str(uuid4()))
    reference = BoundWorkflowCall(operation, str(uuid4()), workflow_id_for(operation_id), str(uuid4()))
    ttl = timedelta(seconds=20)
    signing_key = Ed25519PrivateKey.generate()
    limits = PlatformCredentialLimits(ttl, timedelta(seconds=1), 512, 2048)
    client = PlatformControlClient(
        f"https://{hostname}", ca_file=ca, issuer=PlatformCredentialIssuer(signing_key, limits), ttl=ttl, timeout_seconds=2,
    )
    await client.aclose()
    question = {"questionId": str(uuid4()), "topic": "Scope", "disposition": "OPEN", "answer": None}
    answered = {"questionId": str(uuid4()), "topic": "Owner", "disposition": "ANSWERED", "answer": "Fixture team"}
    valid = {"operationId": str(operation_id), "message": "Continue", "recentQuestions": [question, answered], "historyTruncated": True}
    payload = json.dumps(valid).encode()
    headers = {"Cache-Control": "no-store"}

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/internal/v4/operations/{operation_id}/manager-input"
        return httpx.Response(200, headers=headers, content=payload)

    async def build_input(_reference, message):
        return ManagerReasoningInput("fixture", uuid4(), "fixture", "INTERNAL", LLMLimits(100, 20), message)

    client._client = httpx.AsyncClient(base_url=f"https://{hostname}", transport=httpx.MockTransport(respond), trust_env=False)
    try:
        manager = ManagerHttpPlatform(client, build_input, adaptive_input=True)
        intake = await manager.manager_input(reference)
        assert intake.user_message == "Continue" and intake.history_truncated is True
        assert [(record.disposition, record.answer) for record in intake.recent_questions] == [
            (QuestionDisposition.OPEN, None), (QuestionDisposition.ANSWERED, "Fixture team"),
        ]
        escaped = chr(0x1F600)
        payload = json.dumps({
            **valid,
            "message": escaped * 20_000,
            "recentQuestions": [{**answered, "questionId": str(uuid4()), "topic": escaped * 128, "answer": escaped * 20_000} for _ in range(8)],
        }, ensure_ascii=True).encode()
        assert len((await manager.manager_input(reference)).recent_questions) == 8
        for invalid in (
            {**valid, "operationId": str(uuid4())},
            {**valid, "recentQuestions": [answered, question]},
            {**valid, "recentQuestions": [question, {**answered, "questionId": question["questionId"]}]},
            {**valid, "recentQuestions": [{**answered, "disposition": "UNKNOWN"}]},
        ):
            payload = json.dumps(invalid).encode()
            with pytest.raises(PlatformPermanentError, match="Invalid Platform control response"):
                await manager.manager_input(reference)
        payload = json.dumps(valid).encode() + b" " * 2_200_000
        with pytest.raises(PlatformPermanentError, match="Invalid Platform control response"):
            await manager.manager_input(reference)
        payload = b'{"message":"Duplicate",' + json.dumps(valid).encode()[1:]
        with pytest.raises(PlatformPermanentError, match="Invalid Platform control response"):
            await manager.manager_input(reference)
        payload = json.dumps(valid).encode()
        headers.clear()
        with pytest.raises(PlatformPermanentError, match="Invalid Platform control response"):
            await manager.manager_input(reference)
    finally:
        await client.aclose()
