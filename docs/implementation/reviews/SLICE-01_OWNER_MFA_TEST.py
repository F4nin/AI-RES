"""Behavioral checks for the local owner helper; synthetic HTTP only."""
import importlib.util
import json
import os
from contextlib import nullcontext
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location("slice_owner_mfa", Path(__file__).with_name("SLICE-01_OWNER_MFA.py"))
mfa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mfa)


@pytest.mark.parametrize("existing", [False, True])
def test_personal_code_rotated_cookie_and_private_files_without_secret_output(tmp_path, existing):
    calls, shown, prompts = [], [], []
    secret = "synthetic" + "-enrollment"
    password = "synthetic" + "-password"
    otp = "123" + "456"
    recovery = ["synthetic" + "-recovery"]

    def handle(request):
        path = request.url.path
        calls.append(path)
        body = json.loads(request.content)
        if path.endswith("/login"):
            assert body["password"] == password
            return httpx.Response(200, json={"organizationId": mfa.ORGANIZATION_ID,
                "userId": mfa.OWNER_ID, "csrfToken": "synthetic-csrf", "mfaRequired": existing},
                headers={"set-cookie": "ai_res_session=synthetic-before; Secure; Path=/"})
        assert request.headers["X-CSRF-Token"] == "synthetic-csrf"
        if path.endswith("/enrollment"):
            assert body == {"currentPassword": password}
            return httpx.Response(201, json={"secret": secret, "otpauthUri": "synthetic-uri"})
        assert body == {"code": otp}
        assert existing or (tmp_path / "enrollment.json").exists()
        return httpx.Response(200, json={"csrfToken": "synthetic-new-csrf", "recoveryCodes": recovery},
                              headers={"set-cookie": "ai_res_session=synthetic-after; Secure; Path=/"})

    def code(message):
        prompts.append(message)
        return otp

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client:
        mfa.run(client, password, tmp_path, code=code, show=shown.append)
    assert len(prompts) == 1
    assert calls == (["/api/v1/auth/login", "/api/v1/auth/mfa/verify"] if existing else
                     ["/api/v1/auth/login", "/api/v1/auth/mfa/enrollment", "/api/v1/auth/mfa/enrollment/confirm"])
    assert not (tmp_path / "enrollment.json").exists()
    session = json.loads((tmp_path / "session.json").read_text())
    assert session["sessionToken"] == "synthetic-after"
    for path in tmp_path.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    assert all(s not in "\n".join(shown) for s in (secret, password, otp, "synthetic-after", recovery[0]))
    assert existing or json.loads((tmp_path / "recovery-codes.json").read_text()) == recovery


def test_wrong_owner_cannot_start_enrollment(tmp_path):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"organizationId": mfa.ORGANIZATION_ID, "userId": "synthetic-other"})

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(ValueError):
        mfa.run(client, "synthetic", tmp_path)
    assert calls == ["/api/v1/auth/login"] and not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", ["missing-login-cookie", "missing-rotation", "empty-cookie", "missing-csrf", "unchanged-csrf", "invalid-csrf"])
def test_incomplete_rotation_never_saves_session_or_claims_ready(tmp_path, bad):
    shown = []

    def handle(request):
        if request.url.path.endswith("/login"):
            headers = {} if bad == "missing-login-cookie" else {"set-cookie": "ai_res_session=synthetic-before; Secure; Path=/"}
            return httpx.Response(200, json={"organizationId": mfa.ORGANIZATION_ID,
                "userId": mfa.OWNER_ID, "csrfToken": "synthetic-csrf", "mfaRequired": True}, headers=headers)
        body = {} if bad == "missing-csrf" else {"csrfToken": (
            "synthetic-csrf" if bad == "unchanged-csrf" else 42 if bad == "invalid-csrf" else "synthetic-new")}
        headers = {} if bad == "missing-rotation" else {"set-cookie": (
            "ai_res_session=; Secure; Path=/" if bad == "empty-cookie" else "ai_res_session=synthetic-after; Secure; Path=/")}
        return httpx.Response(200, json=body, headers=headers)

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(ValueError):
        mfa.run(client, "synthetic", tmp_path, code=lambda msg: "123" + "456", show=shown.append)
    assert not (tmp_path / "session.json").exists() and not shown


@pytest.mark.parametrize("unsafe", ["symlink", "shared", "large"])
def test_private_password_rejects_unsafe_file(tmp_path, unsafe):
    path = tmp_path / "input"
    path.write_text("synthetic")
    path.chmod(0o600)
    if unsafe == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    elif unsafe == "shared":
        path.chmod(0o640)
    else:
        path.write_bytes(b"x" * 131073)
    with pytest.raises((OSError, ValueError)):
        mfa.private_read(path)


def test_private_output_never_replaces_existing_file_or_symlink(tmp_path):
    path = tmp_path / "output"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        mfa.private_write(path, {"value": "replacement"})
    link = tmp_path / "linked"
    link.symlink_to(path)
    with pytest.raises(OSError):
        mfa.private_write(link, {})
    assert path.read_text() == "original"


def test_noninteractive_execution_refuses_before_network(monkeypatch, capsys):
    monkeypatch.setattr(mfa.sys, "argv", ["owner-mfa"])
    monkeypatch.setattr(mfa.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(mfa.httpx, "Client", lambda **kw: pytest.fail("no HTTP without personal terminal"))
    assert mfa.main() == 2
    assert "details withheld" in capsys.readouterr().err


def test_private_reads_require_current_file_owner(tmp_path, monkeypatch):
    path = tmp_path / "input"
    path.write_text("synthetic")
    path.chmod(0o600)
    monkeypatch.setattr(mfa.os, "getuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(ValueError):
        mfa.private_read(path)


def test_failed_single_code_submission_preserves_seed_for_next_invocation(tmp_path):
    old = tmp_path / "existing"
    old.mkdir(mode=0o700)
    enrollment = old / "enrollment.json"
    mfa.private_write(enrollment, {"secret": "synthetic-seed", "otpauthUri": "synthetic-uri"})
    output = tmp_path / "new-output"
    output.mkdir(mode=0o700)
    original = enrollment.read_bytes()
    calls, shown, prompts = [], [], []
    confirmations = 0

    def handle(request):
        nonlocal confirmations
        path = request.url.path
        calls.append(path)
        if path.endswith("/login"):
            return httpx.Response(200, json={"organizationId": mfa.ORGANIZATION_ID,
                "userId": mfa.OWNER_ID, "csrfToken": "synthetic-csrf", "mfaRequired": False},
                headers={"set-cookie": "ai_res_session=synthetic-before; Secure; Path=/"})
        assert path.endswith("/enrollment/confirm")
        confirmations += 1
        if confirmations == 1:
            return httpx.Response(401, json={"code": "AUTHENTICATION_REQUIRED", "detail": "Локализованное сообщение."})
        return httpx.Response(200, json={"csrfToken": "synthetic-new", "recoveryCodes": ["synthetic-recovery"]},
                headers={"set-cookie": "ai_res_session=synthetic-after; Secure; Path=/"})

    def code(message):
        prompts.append(message)
        return "123" + "456"

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(mfa.CodeRejected):
        mfa.run(client, "synthetic-password", output, resume_enrollment=enrollment, code=code, show=shown.append)
    assert confirmations == len(prompts) == 1
    assert enrollment.read_bytes() == original and not (output / "session.json").exists()
    assert not any("MFA готова" in message for message in shown)
    resumed = tmp_path / "next-output"
    resumed.mkdir(mode=0o700)
    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client:
        mfa.run(client, "synthetic-password", resumed, resume_enrollment=enrollment, code=code, show=shown.append)
    assert (resumed / "session.json").is_file() and not enrollment.exists()
    assert confirmations == len(prompts) == 2
    assert not any(p.endswith("/enrollment") for p in calls)
    assert not any("synthetic-seed" in s for s in shown)


def test_latest_pending_uses_owned_private_file_without_reading_secret(tmp_path):
    older = tmp_path / "owner-mfa-old"
    newer = tmp_path / "owner-mfa-new"
    for directory in (older, newer):
        directory.mkdir(mode=0o700)
        mfa.private_write(directory / "enrollment.json", {"secret": "synthetic"})
    os.utime(older / "enrollment.json", (1, 1))
    os.utime(newer / "enrollment.json", (2, 2))
    assert mfa.latest_enrollment(tmp_path) == newer / "enrollment.json"
    (newer / "enrollment.json").unlink()
    (newer / "enrollment.json").symlink_to(older / "enrollment.json")
    with pytest.raises(ValueError):
        mfa.latest_enrollment(tmp_path)


@pytest.mark.parametrize("detail", ["Invalid verification code.", "Authentication required.", "Код недействителен.", None, {"untrusted": True}])
def test_localized_detail_never_changes_single_401_submission(detail):
    calls, prompts = [], []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(401, json={"code": "AUTHENTICATION_REQUIRED", "detail": detail})

    def code(message):
        prompts.append(message)
        return "123" + "456"

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(mfa.CodeRejected):
        mfa.submit_code(client, "/auth/mfa/verify", "synthetic-csrf", code=code)
    assert len(calls) == len(prompts) == 1


@pytest.mark.parametrize("status,code", [(500, "AUTHENTICATION_REQUIRED"), (401, "OTHER_CODE"), (429, "RATE_LIMITED")])
def test_other_failures_are_generic_and_not_retried(status, code):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(status, json={"code": code, "detail": "Invalid verification code."})

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(ValueError) as caught:
        mfa.submit_code(client, "/auth/mfa/verify", "synthetic-csrf", code=lambda message: "123" + "456")
    assert type(caught.value) is ValueError and len(calls) == 1


def test_login_401_is_not_misreported_as_a_submitted_code_failure():
    def handle(request):
        return httpx.Response(401, json={"code": "AUTHENTICATION_REQUIRED", "detail": "Invalid verification code."})

    with httpx.Client(base_url=mfa.ORIGIN, transport=httpx.MockTransport(handle)) as client, pytest.raises(ValueError) as caught:
        mfa.post(client, "/auth/login", {}, 200)
    assert type(caught.value) is ValueError


def test_post_never_accesses_title_or_detail():
    class StableCodeOnly(dict):
        def get(self, key, default=None):
            assert key not in {"title", "detail"}
            return super().get(key, default)

        def __getitem__(self, key):
            assert key not in {"title", "detail"}
            return super().__getitem__(key)

    class Response:
        content = b"{}"
        status_code = 401

        def json(self):
            return StableCodeOnly(code="AUTHENTICATION_REQUIRED", detail="Private untrusted response")

    class Client:
        def post(self, *args, **kwargs):
            return Response()

    with pytest.raises(mfa.CodeRejected):
        mfa.post(Client(), "/auth/mfa/verify", {}, 200)


def test_rejected_main_reports_only_bounded_restart_message(tmp_path, monkeypatch, capsys):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(mfa, "PRIVATE", tmp_path)
    monkeypatch.setattr(mfa.sys, "argv", ["owner-mfa"])
    monkeypatch.setattr(mfa.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(mfa.ssl, "create_default_context", lambda **kwargs: object())
    monkeypatch.setattr(mfa, "prompt_secret", lambda message: "synthetic-password")
    monkeypatch.setattr(mfa.httpx, "Client", lambda **kwargs: nullcontext(None))

    def refused(*args, **kwargs):
        raise mfa.CodeRejected("PRIVATE_RESPONSE_REASON")

    monkeypatch.setattr(mfa, "run", refused)
    assert mfa.main() == 2
    output = capsys.readouterr()
    assert not output.out and output.err == "Код не принят; повторите запуск.\n"
