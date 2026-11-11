"""PERSIST-003 (single head, no accidental branches), revision policy (Blueprint §4.3) and PERSIST-004 (offline SQL review). No database."""
import io
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "src" / "ai_res" / "db" / "migrations" / "versions"


def _cfg() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def test_single_head_and_linear_graph():
    script = ScriptDirectory.from_config(_cfg())
    assert len(script.get_heads()) == 1, "multiple Alembic heads: branches are forbidden (single head required)"
    revisions = list(script.walk_revisions())
    assert all(len(r.nextrev) <= 1 for r in revisions), "a revision has several children (branch)"
    assert [r.down_revision for r in revisions].count(None) == 1, "exactly one base revision expected"
    assert all(r.branch_labels is None or not r.branch_labels for r in revisions)


def test_revision_files_follow_naming_policy():
    files = sorted(p.name for p in VERSIONS.glob("*.py") if p.name != "__init__.py")
    assert files, "no revisions found"
    for i, name in enumerate(files, start=1):
        assert re.fullmatch(r"\d{4}_[a-z0-9_]+\.py", name), f"{name}: expected <sequence>_<intent>.py"
        assert int(name[:4]) == i, f"{name}: sequence must be contiguous"


def test_offline_sql_is_reviewable_and_secret_free():
    cfg = _cfg()
    buf = io.StringIO()
    cfg.output_buffer = buf
    command.upgrade(cfg, "base:head", sql=True)
    sql = buf.getvalue()
    assert "SET ROLE ai_res_owner" in sql
    assert "CREATE TABLE platform.alembic_version" in sql
    assert "CREATE SCHEMA iam AUTHORIZATION ai_res_owner" in sql and "CREATE SCHEMA execution AUTHORIZATION ai_res_owner" in sql
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC" in sql
    assert not re.search(r"(?i)password\s+'", sql)
    for forbidden in ("temporal", "langgraph", "CREATE ROLE", "ALTER ROLE", "DROP "):
        assert forbidden not in sql, f"offline SQL unexpectedly contains {forbidden!r}"


def test_no_hidden_secret_or_dsn_in_alembic_ini():
    text = (BACKEND / "alembic.ini").read_text()
    assert "sqlalchemy.url" not in text and not re.search(r"postgres(ql)?(\+\w+)?://", text)
