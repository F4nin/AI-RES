"""Architecture tests (ADR-008/009, Spec §9): import-linter contracts must hold and must be able to fail."""
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LINT = str(Path(sys.executable).parent / "lint-imports")


def lint(cwd: Path, config: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [LINT] + (["--config", str(config)] if config else [])
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def test_project_contracts_are_kept():
    r = lint(BACKEND)
    assert r.returncode == 0, r.stdout[-800:]
    assert "4 kept, 0 broken" in r.stdout


def test_contracts_fail_on_deliberate_violations(tmp_path):
    pkg = tmp_path / "bad"
    for d in ("api", "modules", "platform"):
        (pkg / d).mkdir(parents=True)
        (pkg / d / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "api" / "handler.py").write_text("import sqlite3  # stands in for an ORM/driver import in the API layer\n")
    (pkg / "platform" / "x.py").write_text("from bad.modules import y\n")
    (pkg / "modules" / "y.py").write_text("")
    cfg = tmp_path / ".importlinter"
    cfg.write_text(textwrap.dedent("""
        [importlinter]
        root_package = bad
        include_external_packages = True
        [importlinter:contract:1]
        name = no driver in api
        type = forbidden
        source_modules = bad.api
        forbidden_modules = sqlite3
        [importlinter:contract:2]
        name = platform independent
        type = forbidden
        source_modules = bad.platform
        forbidden_modules = bad.modules
    """))
    env_path = f"{tmp_path}"
    r = subprocess.run([LINT, "--config", str(cfg)], cwd=tmp_path, capture_output=True,
                       text=True, check=False, env={"PYTHONPATH": env_path, "PATH": ""})
    assert r.returncode != 0 and "2 broken" in r.stdout, r.stdout[-600:] + r.stderr[-300:]


def test_no_endpoints_without_contract_in_s02():
    from ai_res.api.app import create_app
    from ai_res.platform.config import Settings

    app = create_app(Settings(environment="test"))
    assert [r.path for r in app.routes if hasattr(r, "methods")] == []  # contract-first: no routes in S02
