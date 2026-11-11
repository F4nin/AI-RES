#!/usr/bin/env python3
"""Waits until every EXPECTED long-running service is healthy and every expected one-shot job exited 0. A missing service is a failure
(not "nothing pending"), and a timeout is a failure. Prints a per-service status. Exit 0 only when the whole expected stack is up."""
import json
import subprocess
import sys
import time

PROJECT_FILES = ["-p", "ai-res", "-f", "compose.yaml", "-f", "compose.dev.yaml"]
ONE_SHOT = {"postgres-provision", "temporal-schema", "temporal-namespace", "minio-init"}
LONG_RUNNING = {"api", "reverse-proxy", "postgres", "temporal", "temporal-ui", "minio", "otel-collector"}
NO_HEALTHCHECK = {"otel-collector"}  # distroless: only "running" can be asserted


def state() -> dict[str, tuple[str, str, int]]:
    res = subprocess.run(["docker", "compose", *PROJECT_FILES, "ps", "-a", "--format", "json"], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if res.returncode != 0:
        raise SystemExit(f"docker compose ps failed: {res.stderr.strip()}")
    rows = [json.loads(line) for line in res.stdout.splitlines() if line.strip()]
    return {r["Service"]: (r["State"], r.get("Health", ""), r.get("ExitCode", 0)) for r in rows}


def problems(st: dict[str, tuple[str, str, int]]) -> tuple[list[str], list[str]]:
    """Returns (failed, pending): failed are definitive, pending may still resolve."""
    failed: list[str] = []
    pending: list[str] = []
    for s in sorted(ONE_SHOT | LONG_RUNNING):
        if s not in st:
            pending.append(f"{s}: missing")
            continue
        run, health, code = st[s]
        if s in ONE_SHOT:
            if run == "exited" and code != 0:
                failed.append(f"{s}: exited {code}")
            elif run != "exited":
                pending.append(f"{s}: {run}")
        elif run in ("exited", "dead"):
            failed.append(f"{s}: {run}")
        elif run != "running" or (s not in NO_HEALTHCHECK and health != "healthy"):
            pending.append(f"{s}: {run}/{health or '-'}")
    return failed, pending


def main(timeout: int = 300) -> int:
    deadline = time.time() + timeout
    while True:
        st = state()
        failed, pending = problems(st)
        if failed or not pending or time.time() > deadline:
            break
        time.sleep(2)
    for s, (run, health, code) in sorted(st.items()):
        print(f"{s:20} {run:8} {health or '-':10} exit={code}")
    for line in failed + pending:
        print(f"NOT READY: {line}", file=sys.stderr)
    return 1 if failed or pending else 0


if __name__ == "__main__":
    sys.exit(main())
