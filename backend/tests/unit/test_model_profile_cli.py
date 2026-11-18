"""CLI boundaries: preview/refusal cannot authenticate, grant or mutate anything."""
import argparse
import json
import warnings
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from ai_res.cli import model_profile

DECISION = str(UUID(int=100))
COMMAND = {"decisionId": DECISION, "correlationId": str(UUID(int=101)),
           "action": "APPROVE_PROFILE_AND_ACCEPT_BIFROST", "profileSha256": "a" * 64,
           "expectationSha256": "b" * 64, "observationSha256": "c" * 64,
           "bifrostAcceptanceSha256": "d" * 64, "policyVersion": "2026-11-18.1"}


@pytest.fixture
def command_file(tmp_path):
    file = tmp_path / "command.json"
    file.write_text(json.dumps(COMMAND))
    file.chmod(0o600)
    return file


def no_prompt(message):
    pytest.fail("preview/refusal must never request a credential")


def test_preview_performs_no_authentication_or_database_access(command_file, monkeypatch, capsys):
    monkeypatch.setattr(model_profile, "create_runtime_engine", lambda *a: pytest.fail("no DB before execute"))
    assert model_profile.main(["--command-file", str(command_file)], prompt=no_prompt, env={}) == 0
    assert "PREVIEW" in capsys.readouterr().out


@pytest.mark.parametrize("changes", ["duplicate", "unknown", "action", "invalid-hash", "secret-error"])
def test_invalid_command_refuses_without_echoing_input(command_file, changes, capsys):
    values = dict(COMMAND)
    if changes == "duplicate":
        command_file.write_text(json.dumps(values)[:-1] + ',"action":"BLOCK"}')
    elif changes == "secret-error":
        command_file.write_text("synthetic-private-input")
    else:
        values[{"unknown": "unknown", "action": "action", "invalid-hash": "profileSha256"}[changes]] = "synthetic-private-input"
        command_file.write_text(json.dumps(values))
    assert model_profile.main(["--command-file", str(command_file)], prompt=no_prompt, env={}) == 2
    captured = capsys.readouterr()
    assert "synthetic-private-input" not in captured.out + captured.err


@pytest.mark.parametrize("change", ["symlink", "shared-write", "oversize"])
def test_untrusted_files_refuse(command_file, tmp_path, change):
    if change == "symlink":
        link = tmp_path / "linked-command"
        link.symlink_to(command_file)
        command_file = link
    elif change == "shared-write":
        command_file.chmod(0o622)
    else:
        command_file.write_bytes(b" " * (model_profile._MAX_FILE_BYTES + 1))
    assert model_profile.main(["--command-file", str(command_file)], prompt=no_prompt, env={}) == 2


@pytest.mark.parametrize("extra", [[], ["--confirm-decision", str(UUID(int=999))],
                                   ["--confirm-decision", DECISION]])
def test_execution_without_complete_binding_cannot_open_database(command_file, extra, monkeypatch):
    monkeypatch.setattr(model_profile, "create_runtime_engine", lambda *a: pytest.fail("no DB on incomplete command"))
    assert model_profile.main(["--command-file", str(command_file), "--execute", *extra], prompt=no_prompt, env={}) == 2


def test_exact_explicit_execution_reaches_only_protected_service_composition(command_file, monkeypatch, tmp_path):
    calls = []

    async def execute(args, command, env, prompt):
        calls.append((args.profile_id, command.decision_id, env))

    monkeypatch.setattr(model_profile, "_execute", execute)
    result = model_profile.main(["--command-file", str(command_file), "--execute", "--confirm-decision", DECISION,
        "--owner-login", "fixture-migrator", "--organization-id", str(UUID(int=1)), "--owner-user-id", str(UUID(int=2)),
        "--profile-id", str(UUID(int=3)), "--auth-db-password-file", str(tmp_path / "api-secret"),
        "--expectation-file", str(tmp_path / "expected"), "--observation-file", str(tmp_path / "observed"),
        "--bifrost-acceptance-file", str(tmp_path / "acceptance")], prompt=no_prompt, env={})
    assert result == 0 and calls == [(UUID(int=3), UUID(DECISION), {})]


def test_execution_errors_do_not_echo_credentials_or_exception_values(command_file, monkeypatch, capsys):
    def fail(path: Path):
        raise RuntimeError("synthetic-private-token")

    monkeypatch.setattr(model_profile, "_command", fail)
    assert model_profile.main(["--command-file", str(command_file)], prompt=no_prompt, env={}) == 2
    captured = capsys.readouterr()
    assert "synthetic-private-token" not in captured.out + captured.err


def test_insecure_getpass_fallback_is_refused_before_reading_stdin(monkeypatch):
    def fallback(message):
        warnings.warn("cannot disable echo", model_profile.getpass.GetPassWarning, stacklevel=1)
        pytest.fail("insecure credential read must never run")

    monkeypatch.setattr(model_profile.getpass, "getpass", fallback)
    with pytest.raises(model_profile.getpass.GetPassWarning):
        model_profile._session_prompt("Session: ")


async def test_real_execute_composition_separates_owner_and_session_authentication(command_file, tmp_path, monkeypatch, capsys):
    from ai_res.platform.config import Settings

    for name in ("expectation", "observation", "acceptance"):
        (tmp_path / name).write_bytes(b"synthetic-metadata")
    engines, built, prompts = [], [], []

    class Engine:
        disposed = False

        async def dispose(self):
            self.disposed = True

    def engine(settings):
        value = Engine()
        engines.append((settings, value))
        return value

    class Service:
        def __init__(self, factory, policy, *, scope, owner_login, sessions):
            built.append((factory, policy, scope, owner_login, sessions))

        async def execute_token(self, token, command, **evidence):
            assert token == "synthetic-private-token"
            assert set(evidence) == {"expectation", "observation", "bifrost_acceptance"}
            return SimpleNamespace(decision_id=command.decision_id, profile_id=UUID(int=3))

    settings = Settings(db_user="fixture_migrator")
    monkeypatch.setattr(model_profile, "load_settings", lambda env: settings)
    monkeypatch.setattr(model_profile, "load_packaged_policy", lambda: SimpleNamespace(version=COMMAND["policyVersion"]))
    monkeypatch.setattr(model_profile, "create_runtime_engine", engine)
    monkeypatch.setattr(model_profile, "create_session_factory", lambda engine: engine)
    monkeypatch.setattr(model_profile, "SessionService", lambda factory, **kw: factory)
    monkeypatch.setattr(model_profile, "PolicyEngine", lambda config, factory: factory)
    monkeypatch.setattr(model_profile, "PolicyEnforcer", lambda policy, factory, config, **kw: policy)
    monkeypatch.setattr(model_profile, "ProfileApprovalService", Service)
    args = argparse.Namespace(owner_login="fixture_migrator", auth_db_password_file=tmp_path / "api-password",
        policy_file=None, policy_sha256=None, expectation_file=tmp_path / "expectation", observation_file=tmp_path / "observation",
        bifrost_acceptance_file=tmp_path / "acceptance", organization_id=UUID(int=1), owner_user_id=UUID(int=2), profile_id=UUID(int=3))

    def prompt(message):
        prompts.append(message)
        return "synthetic-private-token"

    await model_profile._execute(args, model_profile._command(command_file), {}, prompt)
    assert [config.db_user for config, _ in engines] == ["fixture_migrator", "ai_res_api"]
    assert engines[1][0].db_password_file == args.auth_db_password_file
    assert built[0][0] is engines[0][1] and built[0][4] is engines[1][1]
    assert len(prompts) == 1 and all(value.disposed for _, value in engines)
    output = capsys.readouterr()
    assert "APPROVED" in output.out and "synthetic-private-token" not in output.out + output.err
