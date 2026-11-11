"""Blueprint §4.1/§4.2.9: API/Runtime startup must never run migrations (separate one-shot job).
Checked on what matters: the migration machinery is never imported by the app, and no source outside the migration environment imports
Alembic or calls create_all(). (Using SQLAlchemy/psycopg from the API is legitimate from S05 on, so drivers are NOT asserted here.)"""
import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "ai_res"


def test_api_import_does_not_load_the_migration_machinery():
    code = (
        "import sys, ai_res.api.app, ai_res.api.serve; "
        "bad=[m for m in sys.modules if m == 'alembic' or m.startswith(('alembic.', 'ai_res.db.migrations'))]; "
        "print(','.join(bad)); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
    assert r.returncode == 0, f"API import pulled in: {r.stdout.strip()}"


def _offences(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [f"import {a.name}" for a in node.names if a.name == "alembic" or a.name.startswith("alembic.")]
        elif isinstance(node, ast.ImportFrom) and node.module and (node.module == "alembic" or node.module.startswith("alembic.")):
            out.append(f"from {node.module} import ...")  # also catches `from alembic.command import upgrade as up`
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"create_all", "drop_all"}:
            out.append(f".{node.func.attr}()")
    return out


def test_no_alembic_import_or_create_all_outside_the_migration_environment():
    offenders = {
        str(p.relative_to(SRC)): found
        for p in SRC.rglob("*.py")
        if "db/migrations" not in p.as_posix() and (found := _offences(ast.parse(p.read_text())))
    }
    assert not offenders, offenders


def test_the_scanner_catches_aliased_and_attribute_forms():
    for src in ("from alembic.command import upgrade as up", "import alembic.command as c", "Base.metadata.create_all(engine)"):
        assert _offences(ast.parse(src)), src
