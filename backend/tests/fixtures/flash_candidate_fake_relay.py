"""Container-only synthetic upstream for the actual pinned Bifrost integration.

Imports the real relay/codec. The injected accounting port is a TEST DOUBLE:
this fixture proves wire conversion, never durable paid authorization or billing.
No outgoing socket exists: provider HTTP is an httpx.MockTransport and the Docker
network is internal. Diagnostics contain only keys/types/hashes/counts/outcomes.
"""
import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from starlette.responses import JSONResponse

from ai_res.llm.adapters.candidate_control import CandidateClaimReceipt, CandidateControlUnavailable
from ai_res.llm.adapters.flash_candidate import FlashCandidateProbe
from ai_res.llm.candidate_payload import build_candidate_body
from ai_res.llm.candidate_probe import CandidateProbeError

AUTH = "synthetic-relay-credential-" + "a" * 40
if Path("/fixture/credentials.json").is_file():
    # ADR137's renderer accepts exactly mounted64hex. Existing fixtures without
    # this synthetic-only file retain their original wire credential unchanged.
    AUTH = json.loads(Path("/fixture/credentials.json").read_bytes())["llm_relay_auth"]
PROVIDER = "synthetic-provider-credential-" + "b" * 40
DIAGNOSTICS = {"received": [], "claims": [], "outgoing": [], "settlements": [], "requests": []}
RESPONSE_MODE = "SAME"
SSE_MODES = frozenset({"SSE_ABSENT", "SSE_NULL", "SSE_EMPTY", "SSE_FP_FINISH", "SSE_FP_USAGE", "SSE_ID_FINISH", "SSE_ID_USAGE",
                       "SSE_MODEL_FINISH", "SSE_MODEL_USAGE", "SSE_MISSING_FP", "SSE_NULL_FP", "SSE_FP_TYPE", "SSE_FP_DUPLICATE",
                       "SSE_MISSING_ID", "SSE_NULL_MODEL", "SSE_MALFORMED", "SSE_TRUNCATED", "SSE_ERROR", "SSE_CREDENTIAL"})

spec = importlib.util.spec_from_file_location("candidate_fixture_real_relay", "/fixture/relay.py")
assert spec and spec.loader
relay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = relay
spec.loader.exec_module(relay)
real_canonicalize = relay.canonicalize_candidate_body


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value[:3]]
    return type(value).__name__


def capture(raw):
    item = {"received_sha256": hashlib.sha256(raw).hexdigest()}
    try:
        item["shape"] = shape(json.loads(raw))
        candidate = real_canonicalize(raw)
        item["canonical_sha256"] = candidate.body_sha256
        item["case"] = candidate.case_ref
        return candidate
    finally:
        DIAGNOSTICS["received"].append(item)


relay.canonicalize_candidate_body = capture


class FakeControl:
    """No DB, account, reserve, claim authentication or real settlement is proven."""
    async def claim(self, candidate):
        if candidate.body_sha256 in DIAGNOSTICS["claims"]:
            raise CandidateControlUnavailable()
        DIAGNOSTICS["claims"].append(candidate.body_sha256)
        return CandidateClaimReceipt(uuid4(), "synthetic-wire-fixture", candidate.body_sha256, candidate.payload_bytes,
                                     candidate.stream, candidate.max_output_tokens)

    async def settle_known(self, receipt, *, input_tokens, output_tokens, provider_request_ref):
        DIAGNOSTICS["settlements"].append({"outcome": "KNOWN", "body_sha256": receipt.body_sha256,
                                           "input_tokens": input_tokens, "output_tokens": output_tokens})

    async def settle_unknown(self, receipt, *, reason):
        DIAGNOSTICS["settlements"].append({"outcome": "UNKNOWN", "body_sha256": receipt.body_sha256, "reason": reason})

    async def aclose(self):
        pass


def response(case, *, delta=None, finish="stop", usage=True, mode=None):
    mode = RESPONSE_MODE if mode is None else mode
    message = {"role": "assistant", "content": '{"ok":true}' if case == "JSON" else "OK"}
    if case == "TOOL":
        finish = "tool_calls"
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "synthetic-probe-call", "type": "function",
                   "function": {"name": "probe_check", "arguments": '{"ok":true}'}}]}
    choice = {"index": 0, "finish_reason": finish, "message": message}
    if delta is not None:
        choice = {"index": 0, "finish_reason": finish, "delta": delta}
    data = {"id": "synthetic-provider-" + case.lower(), "object": "chat.completion.chunk" if delta is not None else "chat.completion",
            "created": 1_790_000_000,
            "model": {"ALT_FLASH": "deepseek-v4-flash", "ALT_PRO": "deepseek-v4-pro"}.get(mode, "deepseek-flash"),
            "system_fingerprint": "synthetic-wire-fingerprint",
            "choices": [choice], "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14} if usage else None}
    if mode == "SSE_ABSENT":
        data.pop("system_fingerprint")
    elif mode == "SSE_NULL":
        data["system_fingerprint"] = None
    elif mode == "SSE_EMPTY":
        data["system_fingerprint"] = ""
    elif mode == "SSE_CREDENTIAL":
        # Synthetic fixture key only; no real mounted credentials are read.
        data["system_fingerprint"] = json.loads(Path("/fixture/config.json").read_text())["governance"]["virtual_keys"][0]["value"]
    return data


class SyntheticStream(httpx.AsyncByteStream):
    def __init__(self, case, mode):
        self.case, self.mode = case, mode

    async def __aiter__(self):
        mode = self.mode
        first = response(self.case, delta={"role": "assistant", "content": "OK"}, finish=None, usage=False, mode=mode)
        finish = response(self.case, delta={}, finish="stop", usage=False, mode=mode)
        usage = response(self.case, delta={}, mode=mode)
        usage["choices"] = []
        frames = [finish, usage]
        for field, prefix in (("system_fingerprint", "FP"), ("id", "ID"), ("model", "MODEL")):
            if mode == "SSE_" + prefix + "_FINISH":
                finish[field] = "synthetic-changed"
            elif mode == "SSE_" + prefix + "_USAGE":
                changed = {**usage, field: "synthetic-changed"}
                frames = [finish, changed, usage]  # A -> B -> A in hidden usage frames.
        if mode == "SSE_MISSING_FP":
            finish.pop("system_fingerprint")
        elif mode == "SSE_NULL_FP":
            finish["system_fingerprint"] = None
        elif mode == "SSE_FP_TYPE":
            finish["system_fingerprint"] = False
        elif mode == "SSE_MISSING_ID":
            usage.pop("id")
        elif mode == "SSE_NULL_MODEL":
            finish["model"] = None
        yield ("data: " + json.dumps(first) + "\n\n").encode()
        if self.case == "CANCEL":
            await asyncio.sleep(1)
        if mode == "SSE_ERROR":
            yield b'data: {"error":{"message":"synthetic private failure"}}\n\n'
            return
        if mode == "SSE_MALFORMED":
            yield b'data: {"id":\n\n'
            return
        for index, frame in enumerate(frames):
            encoded = json.dumps(frame)
            if index == 0 and mode == "SSE_FP_DUPLICATE":
                encoded = encoded[:-1] + ',"system_fingerprint":"synthetic-duplicate"}'
            yield ("data: " + encoded + "\n\n").encode()
        if mode != "SSE_TRUNCATED":
            yield b"data: [DONE]\n\n"


async def provider(request):
    assert str(request.url) == "https://93.184.216.34/chat/completions"
    assert request.headers["host"] == "api.deepseek.com"
    assert request.extensions["sni_hostname"] == "api.deepseek.com"
    candidate = real_canonicalize(request.content)
    mode = RESPONSE_MODE
    DIAGNOSTICS["outgoing"].append({"sha256": hashlib.sha256(request.content).hexdigest(), "case": candidate.case_ref})
    if candidate.case_ref == "TIMEOUT":
        await asyncio.sleep(2)
    if candidate.stream:
        return httpx.Response(200, stream=SyntheticStream(candidate.case_ref, mode), headers={"content-type": "text/event-stream"})
    return httpx.Response(200, json=response(candidate.case_ref, mode=mode))


async def resolver(host, port):
    assert (host, port) == ("api.deepseek.com", 443)
    return ("93.184.216.34",)


def client_factory(**options):
    assert options["verify"] is True and options["trust_env"] is False and options["follow_redirects"] is False
    return httpx.AsyncClient(transport=httpx.MockTransport(provider), **options)


inner = relay.create_app(relay.RelayConfig(auth_token=AUTH, provider_key=PROVIDER, allow_provider_calls=True),
                         resolver=resolver, client_factory=client_factory, control_client=FakeControl())


async def app(scope, receive, send):
    global RESPONSE_MODE
    if scope.get("type") == "http" and scope.get("path") == "/fixture/evidence":
        await JSONResponse(DIAGNOSTICS)(scope, receive, send)
    elif scope.get("type") == "http" and scope.get("path", "").removeprefix("/fixture/mode/") in {"SAME", "ALT_FLASH", "ALT_PRO", *SSE_MODES}:
        RESPONSE_MODE = scope["path"].rsplit("/", 1)[-1]
        await JSONResponse({"status": "configured"})(scope, receive, send)
    else:
        if scope.get("type") == "http" and scope.get("path") == "/chat/completions":
            DIAGNOSTICS["requests"].append({"header_names": [name.decode("ascii") for name, _ in scope["headers"]],
                "cache_control_is_no_cache": [value for name, value in scope["headers"] if name == b"cache-control"] == [b"no-cache"]})
        await inner(scope, receive, send)


class CaptureTransport(httpx.AsyncBaseTransport):
    """Preserve streaming while recording bounded key/type/boolean diagnostics."""
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.received = []

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        record = {"status": response.status_code}
        self.received.append(record)

        class CaptureStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                raw = bytearray()
                try:
                    async for chunk in response.stream:
                        if len(raw) + len(chunk) <= 65_536:
                            raw.extend(chunk)
                        yield chunk
                finally:
                    try:
                        data = json.loads(raw)
                        route = data.get("extra_fields", {}).get("routing_info", {})
                        record.update({"shape": shape(data),
                            "routing_checks": {"provider": route.get("provider") == "deepseek",
                                "model": route.get("model") == "deepseek-flash",
                                "requested_model": route.get("requested_model") == "deepseek-flash",
                                "requested_provider": route.get("requested_provider") == "deepseek",
                                "server_side_fallback_empty": route.get("server_side_fallback_model") == "",
                                "server_side_fallback_is_response_model": route.get("server_side_fallback_model") == data.get("model"),
                                "resolved_alias_absent": route.get("resolved_key_alias") is None}})
                    except (ValueError, UnicodeError):
                        events = []
                        for frame in bytes(raw).replace(b"\r\n", b"\n").split(b"\n\n"):
                            if not frame:
                                continue
                            payload = b"\n".join(line[5:].lstrip() for line in frame.split(b"\n") if line.startswith(b"data:"))
                            if payload == b"[DONE]":
                                events.append({"done": True})
                                continue
                            try:
                                value = json.loads(payload)
                                events.append({"shape": shape(value), "usage_present": value.get("usage") is not None,
                                    "finish_stop": any(choice.get("finish_reason") == "stop" for choice in value.get("choices", [])),
                                    "controlled_metadata_refusal": (isinstance(value.get("error"), dict)
                                        and value["error"].get("message") == "chat stream metadata validation failed"),
                                    "fingerprint_matches": value.get("system_fingerprint") == "synthetic-wire-fingerprint",
                                    "fingerprint_empty": value.get("system_fingerprint") == "",
                                    "response_model_matches": value.get("model") == "deepseek-flash",
                                    "provider_ref_matches": value.get("id") == "synthetic-provider-sse"})
                            except (ValueError, UnicodeError):
                                events.append({"unparsed_sha256": hashlib.sha256(payload).hexdigest()})
                        record.update({"stream_sha256": hashlib.sha256(raw).hexdigest(), "events": events})

            async def aclose(self):
                if response.status_code != 200 and "shape" not in record:
                    raw = bytearray()
                    async for chunk in response.stream:
                        if len(raw) + len(chunk) > 65_536:
                            break
                        raw.extend(chunk)
                    try:
                        data = json.loads(raw)
                        record["shape"] = shape(data)
                        error = data.get("error", {})
                        message = error.get("message", "") if isinstance(error, dict) else ""
                        record["error_checks"] = {word: word in message.lower() for word in (
                            "stream", "header", "format", "retry", "auth", "invalid", "model", "unsupported", "options")}
                        record["controlled_metadata_refusal"] = message == "chat stream metadata validation failed"
                    except (ValueError, UnicodeError):
                        record["body_sha256"] = hashlib.sha256(raw).hexdigest()
                await response.stream.aclose()

        return httpx.Response(response.status_code, headers=response.headers, stream=CaptureStream(), extensions=response.extensions)

    async def aclose(self):
        await self.inner.aclose()


async def probe_fixture(case):
    config = json.loads(Path("/fixture/config.json").read_text())
    key = config["governance"]["virtual_keys"][0]["value"]
    async with httpx.AsyncClient(trust_env=False) as client:
        await client.get("http://127.0.0.1:8081/fixture/mode/" + (case if case.startswith("ALT_") or case in SSE_MODES else "SAME"))
    body = build_candidate_body("TEXT" if case.startswith(("ALT_", "AUTH_")) else "SSE" if case in SSE_MODES else case, uuid4())
    capture_transport = CaptureTransport()
    if case == "AUTH_MISSING":
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10) as client:
            response_without_key = await client.post("http://bifrost-poc:8080/v1/chat/completions",
                                                     content=FlashCandidateProbe.native_request(body), headers={"content-type": "application/json"})
            evidence = {"httpStatus": response_without_key.status_code, "outcome": "AUTH_REFUSED"}
    else:
        async with FlashCandidateProbe(virtual_key="synthetic-wrong-virtual-key" if case == "AUTH_WRONG" else key,
                                       http_transport=capture_transport) as probe:
            try:
                evidence = (await probe.probe(body, timeout_seconds=0.15 if case == "TIMEOUT" else 10)).to_dict()
            except CandidateProbeError as error:
                evidence = {"error": error.code.value}
    async with httpx.AsyncClient(trust_env=False) as client:
        diagnostics = (await client.get("http://127.0.0.1:8081/fixture/evidence")).json()
        # A local cancel/timeout cannot establish the relay's accounting state.
        # Let this synthetic fixture drain before the next independent case.
        if case in {"CANCEL", "TIMEOUT"}:
            for _ in range(25):
                if any(item["body_sha256"] == body.body_sha256 for item in diagnostics["settlements"]):
                    break
                await asyncio.sleep(0.1)
                diagnostics = (await client.get("http://127.0.0.1:8081/fixture/evidence")).json()
        await client.get("http://127.0.0.1:8081/fixture/mode/SAME")
    print(json.dumps({"evidence": evidence, "expected_sha256": body.body_sha256, "diagnostics": diagnostics,
                      "bifrost_response": capture_transport.received}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--probe":
        asyncio.run(probe_fixture(sys.argv[2]))
    else:
        uvicorn.run(app, host="0.0.0.0", port=8081, access_log=False, log_level="critical", server_header=False, proxy_headers=False)  # noqa: S104
