"""Local, interactive owner MFA setup using existing HTTPS API endpoints.

Run in your own terminal, not the agent's terminal. Secret material goes only to
new owner-only files under ignored local-admin; no OTP is computed by this helper.
It performs no model/profile approval, policy mutation or inference.
"""
import argparse
import getpass
import json
import os
import ssl
import stat
import sys
import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path

import httpx

ORIGIN = "https://localhost:8443"
ORGANIZATION_ID = "01a1eef2-08a5-737a-8304-65ed7b5b0538"
OWNER_ID = "01a1eef2-08a5-737a-8304-65eec13a0507"
ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "infra/secrets/local-admin"


class CodeRejected(ValueError):
    """The one code submission was refused; the response does not identify why."""


def latest_enrollment(base: Path) -> Path | None:
    candidates = []
    for path in base.glob("owner-mfa-*/enrollment.json"):
        parent, info = path.parent.lstat(), path.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
                or info.st_size > 131072):
            raise ValueError("untrusted pending enrollment file")
        candidates.append((info.st_mtime_ns, path))
    return max(candidates)[1] if candidates else None


def private_read(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 131072:
            raise ValueError("private owned file required")
        with os.fdopen(fd, "r", closefd=False) as source:
            return source.read(131073).strip()
    finally:
        os.close(fd)


def private_write(path: Path, value: object) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(value, output)
        output.write("\n")


def prompt_secret(message: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(message)


def post(client: httpx.Client, route: str, payload: dict, expected: int, csrf: str | None = None) -> dict:
    response = client.post("/api/v1" + route, json=payload,
                           headers={"X-CSRF-Token": csrf} if csrf else {})
    if len(response.content) > 1048576:
        raise ValueError("HTTPS operation refused")
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("unexpected response shape")
    if (route in {"/auth/mfa/verify", "/auth/mfa/enrollment/confirm"}
            and response.status_code == 401 and result.get("code") == "AUTHENTICATION_REQUIRED"):
        raise CodeRejected("code submission not accepted")
    if response.status_code != expected:
        raise ValueError("HTTPS operation refused")
    return result


def submit_code(client: httpx.Client, route: str, csrf: str, *,
                code: Callable[[str], str]) -> dict:
    return post(client, route, {"code": code("Код из вашего authenticator: ").strip()}, 200, csrf)


def run(client: httpx.Client, password: str, directory: Path, *,
        resume_enrollment: Path | None = None,
        code: Callable[[str], str] = prompt_secret, show: Callable[[str], None] = print) -> None:
    login = post(client, "/auth/login", {"organizationId": ORGANIZATION_ID,
                 "email": "admin@ai-res.local", "password": password}, 200)
    if login.get("userId") != OWNER_ID or login.get("organizationId") != ORGANIZATION_ID:
        raise ValueError("unexpected owner identity")
    csrf = login["csrfToken"]
    if not isinstance(csrf, str) or not csrf or type(login.get("mfaRequired")) is not bool:
        raise ValueError("invalid login response")
    before = client.cookies.get("ai_res_session")
    if not isinstance(before, str) or not before:
        raise ValueError("login session unavailable")
    if login["mfaRequired"]:
        completed = submit_code(client, "/auth/mfa/verify", csrf, code=code)
    else:
        enrollment_file = resume_enrollment or directory / "enrollment.json"
        if resume_enrollment is not None:
            enrollment = json.loads(private_read(resume_enrollment))
        else:
            enrollment = post(client, "/auth/mfa/enrollment", {"currentPassword": password}, 201, csrf)
        if not isinstance(enrollment, dict):
            raise ValueError("invalid enrollment response")
        if not all(isinstance(enrollment.get(k), str) and enrollment[k] for k in ("secret", "otpauthUri")):
            raise ValueError("invalid enrollment response")
        if resume_enrollment is None:
            private_write(enrollment_file, enrollment)
        show(f"Откройте {enrollment_file} в своём локальном редакторе.")
        show("Добавьте secret вручную в ваше приложение Authenticator. Не отправляйте файл или код в чат.")
        completed = submit_code(client, "/auth/mfa/enrollment/confirm", csrf, code=code)
        recovery = completed.get("recoveryCodes")
        if not isinstance(recovery, list) or not recovery or not all(isinstance(c, str) and c for c in recovery):
            raise ValueError("recovery codes unavailable")
        private_write(directory / "recovery-codes.json", recovery)
    session = client.cookies.get("ai_res_session")
    rotated_csrf = completed.get("csrfToken")
    if (not isinstance(session, str) or not session or session == before
            or not isinstance(rotated_csrf, str) or not rotated_csrf or rotated_csrf == csrf):
        raise ValueError("rotated MFA session unavailable")
    if not login["mfaRequired"]:
        # Remove only the validated private seed used by this operation.
        enrollment_file.unlink()
    private_write(directory / "session.json", {"sessionToken": session,
                  "organizationId": ORGANIZATION_ID, "userId": OWNER_ID})
    show(f"MFA готова. Закрытые файлы сессии и recovery codes: {directory}")
    show("Профиль модели не утверждался; платных запросов не было.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty():
            raise ValueError("interactive owner terminal required")
        info = PRIVATE.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("private owner directory required")
        tls = ssl.create_default_context(cafile=str(PRIVATE / "caddy-root-ca.crt"))
        password = private_read(args.password_file) if args.password_file else prompt_secret("Текущий пароль администратора: ")
        resume = latest_enrollment(PRIVATE)
        directory = Path(tempfile.mkdtemp(prefix="owner-mfa-", dir=PRIVATE))
        with httpx.Client(base_url=ORIGIN, verify=tls, trust_env=False, follow_redirects=False,
                          timeout=15, headers={"Origin": ORIGIN}) as client:
            run(client, password, directory, resume_enrollment=resume)
        return 0
    except CodeRejected:
        print("Код не принят; повторите запуск.", file=sys.stderr)
        return 2
    except Exception:
        print("MFA setup refused or incomplete; credentials and response details withheld.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
