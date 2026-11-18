"""Unpaid native fixture: real Bifrost + SLICE relay, synthetic upstream injection.

This file is mounted only by tests in an internal network with a fake key.
It is never mounted by live runtime and has no external network path.
"""
import json
from pathlib import Path

import httpx
import uvicorn
from scripts.slice01.common import decode, read_owned, write_new
from scripts.slice01.ledger import SliceLedger
from scripts.slice01.relay import create_app

plan = decode(read_owned(Path("/plan.json")))
assert plan["mode"] == "fixture"
ledger = SliceLedger(Path("/wallet/ledger.jsonl"), manifest_sha256=plan["manifestSha256"])


async def handle(request):
    data = json.loads(request.content)
    # All captured text is synthetic/public fixture data, never a live credential.
    name = "bootstrap" if data["messages"][0]["content"].startswith("SLICE-01 bounded") else "run"
    write_new(Path("/wallet") / (name + "-wire.json"), data)
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "api.deepseek.com"
    assert request.extensions["sni_hostname"] == "api.deepseek.com"
    if name == "bootstrap":
        output = "OK"
    else:
        user = json.loads(data["messages"][-1]["content"])
        source = user["source"]
        lines = source["text"].splitlines()
        index = next(i for i, line in enumerate(lines, 1) if "Home page" in line)
        output = json.dumps({"workerResult": {
            "contractVersion": "1.1", **user["experimentIds"], "workerRole": "REQUIREMENTS", "resultStatus": "COMPLETED",
            "summary": "Synthetic fixture extraction", "findings": [{"findingId": "F1", "classification": "SOURCE_ASSERTION",
                "statement": "Provide the home page.", "evidenceRefs": [{"objectType": "SourceVersion",
                    "objectId": source["versionId"], "versionId": source["versionId"], "checksum": source["checksum"],
                    "locator": f"lines:{index}-{index}", "quote": lines[index - 1]}]}],
            "proposedChanges": [], "artifactRefs": [], "questions": [], "blockers": [], "limitations": ["Synthetic provider fixture"],
            "validation": {"selfAssessment": "NOT_RUN"}, "completedAt": "2026-11-18T15:00:00Z"},
            "findingTypes": [{"findingId": "F1", "declaredType": "FR"}]})
    return httpx.Response(200, json={"id": "fixture-native-" + name, "model": "deepseek-flash",
        "system_fingerprint": "fixture-native-fingerprint", "choices": [{"index": 0, "message": {"role": "assistant", "content": output},
        "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}})


def client_factory(**kwargs):
    return httpx.AsyncClient(**kwargs, transport=httpx.MockTransport(handle))


async def resolver(host, port):
    assert (host, port) == ("api.deepseek.com", 443)
    return ("93.184.216.34",)


app = create_app(ledger=ledger, requests=plan["requests"],
    relay_auth=read_owned(Path("/run/secrets/llm_relay_auth")).decode().strip(),
    provider_key=read_owned(Path("/run/secrets/deepseek_api_key")).decode().strip(),
    resolver=resolver, client_factory=client_factory)
uvicorn.run(app, host="0.0.0.0", port=8081, access_log=False, log_config=None, log_level="critical",  # noqa:S104 - private test-only network
            server_header=False, proxy_headers=False)
