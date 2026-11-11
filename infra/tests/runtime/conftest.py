"""Runtime evidence fixtures: tests run against the live Compose stack (`make up`). Without a running stack they are skipped, and a
skip is NOT evidence (the report must show them executed)."""
import json
import os

import pytest

from tests.runtime.helpers import LONG_RUNNING, SECRETS, compose


@pytest.fixture(scope="session", autouse=True)
def stack_up():
    """Locally a missing stack skips the suite (a skip is not evidence). With AI_RES_REQUIRE_STACK=1 (CI) it is a hard failure, so a dead
    stack can never produce a green run made of skipped tests."""
    required = os.environ.get("AI_RES_REQUIRE_STACK") == "1"

    def stop(msg: str):
        if required:
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)

    res = compose("ps", "--format", "json")
    if res.returncode != 0:
        stop(f"`docker compose ps` failed: {res.stderr.strip()[:200]}")
    rows = [json.loads(line) for line in res.stdout.splitlines() if line.strip()]
    running = {r["Service"] for r in rows if r.get("State") == "running"}
    if not set(LONG_RUNNING) <= running:
        stop(f"Compose stack is not up (missing: {sorted(set(LONG_RUNNING) - running)}); run `make up`")


@pytest.fixture(scope="session")
def secret_values() -> dict[str, str]:
    return {p.name: p.read_text() for p in SECRETS.iterdir() if p.is_file()}
