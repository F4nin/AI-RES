"""Offline human profile approval; default previews metadata without DB access.

No bootstrap, grants, provider calls or packaged policy changes. Execution needs
an existing MFA session (prompted without echo), a provisioned owner DB login and
normal API credentials solely for authenticating that session. Never run in an
API, Manager or Worker process.
"""
import argparse
import asyncio
import getpass
import json
import os
import stat
import sys
import warnings
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.sessions import SessionService
from ai_res.modules.model_registry.owner_review import OwnerReviewScope
from ai_res.modules.model_registry.profile_approval import (
    ProfileApprovalAction,
    ProfileApprovalDecision,
    ProfileApprovalService,
)
from ai_res.platform.config import ConfigError, Settings, load_settings
from ai_res.policy.config import load_packaged_policy, parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

_MAX_FILE_BYTES = 524288  # local input bound, not a product capacity decision


def _session_prompt(message: str) -> str:
    # getpass otherwise falls back to potentially echoed stdin without a TTY.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(message)


def _read(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022
                or info.st_size > _MAX_FILE_BYTES or info.st_uid != os.getuid()):
            raise ConfigError("approval input must be an owned regular file without shared write access")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(_MAX_FILE_BYTES + 1)
        if len(raw) > _MAX_FILE_BYTES:
            raise ConfigError("approval input is too large")
        return raw
    finally:
        os.close(descriptor)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ConfigError("duplicate approval command field")
        values[key] = value
    return values


def _command(path: Path) -> ProfileApprovalDecision:
    values = json.loads(_read(path), object_pairs_hook=_unique)
    expected = {"decisionId", "correlationId", "action", "profileSha256", "expectationSha256",
                "observationSha256", "bifrostAcceptanceSha256", "policyVersion"}
    if not isinstance(values, dict) or set(values) != expected:
        raise ConfigError("approval command has missing or unknown fields")
    return ProfileApprovalDecision(
        UUID(values["decisionId"]), UUID(values["correlationId"]), ProfileApprovalAction(values["action"]),
        values["profileSha256"], values["expectationSha256"], values["observationSha256"],
        values["bifrostAcceptanceSha256"], values["policyVersion"])


async def _execute(args: argparse.Namespace, command: ProfileApprovalDecision,
                   env: Mapping[str, str], prompt: Callable[[str], str]) -> None:
    settings = load_settings(env)
    if settings.db_user != args.owner_login or not args.auth_db_password_file:
        raise ConfigError("execution needs the provisioned owner login and separate API authentication credentials")
    config = (parse_policy_config(_read(args.policy_file), args.policy_sha256)
              if args.policy_file is not None else load_packaged_policy())
    if config.version != command.policy_version:
        raise ConfigError("approval command policy version is stale")
    expectation = _read(args.expectation_file)
    observation = _read(args.observation_file)
    acceptance = _read(args.bifrost_acceptance_file)
    owner_engine = create_runtime_engine(settings)
    auth_engine = None
    try:
        auth_values = settings.model_dump()
        auth_values["db_user"] = "ai_res_api"
        auth_values["db_password_file"] = args.auth_db_password_file
        auth_settings = Settings.model_validate(auth_values)
        auth_engine = create_runtime_engine(auth_settings)
        auth_factory = create_session_factory(auth_engine)
        sessions = SessionService(auth_factory, idle=timedelta(seconds=settings.session_idle_seconds),
                                  absolute=timedelta(seconds=settings.session_absolute_seconds),
                                  touch_interval=timedelta(seconds=settings.session_touch_interval_seconds))
        policy = PolicyEnforcer(PolicyEngine(config, auth_factory), auth_factory, config, timeout_seconds=settings.policy_timeout_seconds)
        scope = OwnerReviewScope(args.organization_id, args.owner_user_id, args.profile_id)
        service = ProfileApprovalService(create_session_factory(owner_engine), policy, scope=scope,
                                         owner_login=args.owner_login, sessions=sessions)
        receipt = await service.execute_token(prompt("Existing MFA session token: "), command,
                                             expectation=expectation, observation=observation, bifrost_acceptance=acceptance)
        print(f"APPROVED decision_id={receipt.decision_id} profile_id={receipt.profile_id}")
    finally:
        if auth_engine is not None:
            await auth_engine.dispose()
        await owner_engine.dispose()


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None,
         prompt: Callable[[str], str] = _session_prompt) -> int:
    parser = argparse.ArgumentParser(description="Preview or explicitly execute an existing owner's exact model-profile decision.")
    parser.add_argument("--command-file", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-decision", type=UUID)
    parser.add_argument("--owner-login")
    parser.add_argument("--organization-id", type=UUID)
    parser.add_argument("--owner-user-id", type=UUID)
    parser.add_argument("--profile-id", type=UUID)
    parser.add_argument("--auth-db-password-file", type=Path)
    parser.add_argument("--expectation-file", type=Path)
    parser.add_argument("--observation-file", type=Path)
    parser.add_argument("--bifrost-acceptance-file", type=Path)
    parser.add_argument("--policy-file", type=Path)
    parser.add_argument("--policy-sha256")
    args = parser.parse_args(argv)
    try:
        command = _command(args.command_file)
        if not args.execute:
            print(f"PREVIEW decision_id={command.decision_id}; no approval or database access performed")
            return 0
        if (args.confirm_decision != command.decision_id or not args.owner_login
                or any(value is None for value in (args.organization_id, args.owner_user_id, args.profile_id,
                    args.auth_db_password_file, args.expectation_file, args.observation_file, args.bifrost_acceptance_file))
                or (args.policy_file is None) != (args.policy_sha256 is None)):
            raise ConfigError("execution requires exact decision confirmation, owner scope, credentials and acceptance evidence")
        asyncio.run(_execute(args, command, os.environ if env is None else env, prompt))
        return 0
    except Exception:
        # Never print exceptions: DB/parse errors can carry secrets or content.
        print("Model profile approval refused; configuration, identity, policy or exact evidence unavailable.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
