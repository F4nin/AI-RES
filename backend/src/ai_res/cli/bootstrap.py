"""`python -m ai_res.cli.bootstrap --organization-name … --admin-email … --admin-name …`

Prompts (no echo, nothing in argv or shell history) for the bootstrap secret and the administrator's password. Prints only identifiers.
Exit codes: 0 created · 2 refused (wrong secret, weak password, already bootstrapped) · 1 configuration/connection error.
"""
import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Callable, Mapping, Sequence

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.bootstrap import BootstrapError, bootstrap_first_admin
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy
from ai_res.platform.config import ConfigError, load_settings, read_secret_file


async def _run(args: argparse.Namespace, env: Mapping[str, str], prompt: Callable[[str], str]) -> int:
    settings = load_settings(env)
    if settings.bootstrap_secret_file is None:
        raise ConfigError("bootstrap_secret_file is required")
    expected = read_secret_file(settings.bootstrap_secret_file)
    presented = prompt("Bootstrap secret: ").encode()
    password = prompt("Administrator password: ")
    if prompt("Repeat password: ") != password:
        print("bootstrap refused: password_mismatch", file=sys.stderr)
        return 2
    hasher = PasswordHasherService(time_cost=settings.argon2_time_cost, memory_kib=settings.argon2_memory_kib, parallelism=settings.argon2_parallelism)
    policy = PasswordPolicy.with_default_denylist(settings.password_denylist_file, settings.password_min_length)
    engine = create_runtime_engine(settings)
    try:
        result = await bootstrap_first_admin(
            create_session_factory(engine), hasher, policy, expected_secret=expected, presented_secret=presented,
            organization_name=args.organization_name, admin_email=args.admin_email, admin_name=args.admin_name, password=password)
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(f"organization_id={result.organization_id}\nuser_id={result.user_id}")
    return 0


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None, prompt: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog="ai_res.cli.bootstrap", description="Create the first administrator (one time per installation).")
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-name", required=True)
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args, os.environ if env is None else env, prompt))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - a traceback would carry SQL parameters (e-mail, hashes); print the class only
        print(f"bootstrap failed: {type(exc).__name__} (details withheld; see the service logs)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
