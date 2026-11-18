"""Host operator for the isolated SLICE experiment, with explicit human approval."""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from .common import PRIVATE_ROOT, ROOT, SliceRefused, canonical, decode, digest, load_plan, read_owned, wallet_directory, write_new
from .ledger import SliceLedger
from .prepare import activate_version, prepare
from .runtime import SliceRuntime, latest_session

LIVE = PRIVATE_ROOT / "authorization-2026-11-18"


def acceptance(directory: Path, evidence_path: Path) -> dict[str, Any]:
    """Prepare review material; never represent this operation as human acceptance."""
    from ai_res.modules.model_registry.owner_review import review_evidence
    from ai_res.modules.model_registry.profile_approval import profile_snapshot_hash

    plan = load_plan(directory / "config")
    results = directory / "results"
    expected, observed = review_evidence(read_owned(results / "expectation.json"), read_owned(results / "observation.json"))
    from ai_res.modules.model_registry.admission import evidence_hash

    evidence = decode(read_owned(evidence_path, private=False))
    refs = ("toolHashes", "scriptsInitializerSha256", "bifrostImage", "nativeInputs", "librarySha256", "workerContractSha256")
    if (not isinstance(evidence, dict) or evidence.get("status") != "LOCAL_CHECKS_PASSED"
            or any(evidence.get(key) != plan[key] for key in refs)):
        raise SliceRefused("CURRENT_NATIVE_REVIEW_EVIDENCE_REQUIRED")
    artifact = {"version": "slice01-acceptance/1", "manifestSha256": plan["manifestSha256"],
                "profileId": plan["profileId"], "profileSha256": profile_snapshot_hash(plan["profileSnapshot"]),
                "expectationSha256": evidence_hash(expected).hex(), "observationSha256": evidence_hash(observed).hex(),
                "nativeEvidenceSha256": digest(canonical(evidence)), "evidence": evidence}
    write_new(results / "acceptance.json", artifact)
    return {"status": "REVIEW_MATERIAL_ONLY", "acceptanceSha256": digest(canonical(artifact) + b"\n")}


def approve(runtime: SliceRuntime, confirmation: str, *, action: str = "approve") -> dict[str, Any]:
    """Separate offline owner process; no provider network or runtime owner grants."""
    state = runtime.verify()
    directory, plan = runtime.directory, runtime.plan
    decision_id = UUID(confirmation)
    if str(decision_id) != confirmation:
        raise SliceRefused("EXACT_HUMAN_CONFIRMATION_REQUIRED")
    decision = decode(read_owned(directory / "results" / f"decision-{decision_id}.json"))
    if confirmation != decision["decisionId"] or plan["mode"] != "live":
        raise SliceRefused("EXACT_HUMAN_CONFIRMATION_REQUIRED")
    expected_action = "accept-identity" if plan.get("profileStatus") == "APPROVED" else "approve"
    expected_actions = ["ACCEPT_IDENTITY"] if expected_action == "accept-identity" else ["ACCEPT_IDENTITY", "APPROVE_PROFILE_AND_ACCEPT_BIFROST"]
    if action != expected_action or decision.get("actions") != expected_actions:
        raise SliceRefused("EXACT_HUMAN_ACTION_REQUIRED")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SliceRefused("HUMAN_TERMINAL_REQUIRED")
    if action == "accept-identity":
        print("Подтверждается новая identity для точной версии кода и промпта SLICE-01. Профиль уже утверждён.")
    else:
        print("Подтверждаются identity DeepSeek Flash и допуск этого профиля/Bifrost для SLICE-01.")
    print("Артефакт проверки:", directory / "results/acceptance.json")
    print("SHA-256:", decision["acceptanceSha256"])
    if input("Для подтверждения введите ПРИНИМАЮ: ").strip() != "ПРИНИМАЮ":
        raise SliceRefused("HUMAN_DECLINED")
    if runtime.verify() != state:
        raise SliceRefused("RUNTIME_CHANGED_DURING_HUMAN_REVIEW")
    volumes = {
        str(ROOT / "backend/scripts"): {"bind": "/workspace/backend/scripts", "mode": "ro"},
        str(directory / "config"): {"bind": "/config", "mode": "ro"},
        str(directory / "results"): {"bind": "/results", "mode": "rw"},
        str(directory / "config/worker-contract.json"): {"bind": "/worker-contract.json", "mode": "ro"},
    }
    for source, name in ((latest_session(), "owner_session.json"),
                         (ROOT / "infra/secrets/runtime/api_db_password", "api_db_password"),
                         (ROOT / "infra/secrets/runtime/migrator_db_password", "migrator_db_password"),
                         (ROOT / "infra/secrets/runtime/postgres_tls_ca_cert", "postgres_tls_ca_cert")):
        volumes[str(source)] = {"bind": "/run/secrets/" + name, "mode": "ro"}
    env = {"PYTHONPATH": "/workspace/backend", "PYTHONDONTWRITEBYTECODE": "1", "AI_RES_ENVIRONMENT": "prod",
           "AI_RES_DB_HOST": "postgres", "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": "/run/secrets/api_db_password",
           "AI_RES_DB_SSLMODE": "verify-full", "AI_RES_DB_SSLROOTCERT_FILE": "/run/secrets/postgres_tls_ca_cert",
           "AI_RES_DB_APPLICATION_NAME": "slice01-offline-owner"}
    container = runtime.client.containers.run(plan["pythonImage"],
        ["python", "-B", "-m", "scripts.slice01.owner", action, "--confirm-decision", confirmation],
        detach=True, network="ai-res_data", volumes=volumes, environment=env,
        user=f"{os.getuid()}:{os.getgid()}", read_only=True, cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"], pids_limit=128, mem_limit="256m",
        labels={"ai_res.tool": "slice01-offline-owner", "ai_res.instance": state["instance"]})
    try:
        result = container.wait(timeout=45)
        if result["StatusCode"]:
            raise SliceRefused("OWNER_APPROVAL_REFUSED_CHECK_SAFE_RECEIPTS")
        answer: dict[str, Any] = decode(container.logs(stdout=True, stderr=False))
        if not isinstance(answer, dict):
            raise SliceRefused("OWNER_INVALID_RESULT")
        try:
            if runtime.verify() != state:
                raise SliceRefused("RUNTIME_CHANGED")
        except Exception:
            raise SliceRefused("APPROVAL_MAY_HAVE_COMMITTED_CHECK_AUDIT_AND_RECEIPTS") from None
        return answer
    finally:
        container.remove(force=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "activate-version", "start", "preflight", "bootstrap", "prepare-decision", "approve",
                                         "accept-identity", "run", "status", "stop", "acceptance"))
    parser.add_argument("--directory", type=Path, default=LIVE)
    parser.add_argument("--tariff-checked-at", type=datetime.fromisoformat)
    parser.add_argument("--evidence-file", type=Path)
    parser.add_argument("--confirm-decision")
    args = parser.parse_args()
    runtime = None
    try:
        if args.action == "prepare":
            if args.tariff_checked_at is None:
                raise SliceRefused("FRESH_TARIFF_REVIEW_REQUIRED")
            result = prepare(args.directory, mode="live", tariff_checked_at=args.tariff_checked_at)
        elif args.action == "activate-version":
            result = asyncio.run(activate_version(args.directory))
        elif args.action == "acceptance":
            if args.evidence_file is None:
                raise SliceRefused("EVIDENCE_REQUIRED")
            result = acceptance(args.directory, args.evidence_file)
        elif args.action == "status":
            plan = load_plan(args.directory / "config", for_execution=False)
            ledger = SliceLedger(wallet_directory(args.directory, plan["mode"]) / "ledger.jsonl", manifest_sha256=plan["manifestSha256"])
            balance = asyncio.run(ledger.balance())
            result = {"attempts": balance.attempts, "pending": balance.pending, "blocked": balance.blocked,
                      "usedOrReservedUSD": str(balance.used_or_reserved), "remainingUSD": str(balance.remaining)}
        else:
            runtime = SliceRuntime(args.directory, cleanup_only=args.action == "stop")
            if args.action == "start":
                state = runtime.start()
                result = {"status": "ISOLATED_RUNTIME_STARTED", "instance": state["instance"]}
            elif args.action == "stop":
                runtime.stop()
                result = {"status": "OWNED_RUNTIME_STOPPED"}
            elif args.action == "prepare-decision":
                state = runtime.verify()
                caller = runtime.client.containers.get(state["containers"]["caller"]["id"])
                output = caller.exec_run(["python", "-B", "-m", "scripts.slice01.owner", "prepare-decision"], demux=True)
                if output.exit_code:
                    raise SliceRefused("OWNER_REVIEW_PREPARATION_REFUSED")
                result = decode(output.output[0])
                runtime.verify()
            elif args.action in {"approve", "accept-identity"}:
                result = approve(runtime, args.confirm_decision, action=args.action)
            else:
                result = runtime.execute(args.action)
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({"status": "SLICE_REFUSED", "errorType": type(error).__name__,
                          "reason": str(error) if isinstance(error, SliceRefused) else "OPERATION_UNCONFIRMED"}), file=sys.stderr)
        return 2
    finally:
        if runtime is not None:
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
