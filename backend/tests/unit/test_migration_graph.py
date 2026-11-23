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
    # Approved forward0022 removes a session-dependent audit CHECK, preserving data/defaults/grants (ADR132).
    # 0023 expands only Flash's explicit observed mode; its IS TRUE CHECK retains immutable non-NULL pins.
    # Keep DROP denied everywhere else: exact exceptions never permit table/schema/column removal.
    restore_actor_fix = "ALTER TABLE platform.model_admission_audit DROP CONSTRAINT ck_maa_writer;"
    observed_pin_expand = "ALTER TABLE platform.model_profiles ALTER COLUMN pinned_model_version DROP NOT NULL;"
    guarded_sql = sql
    # G02 replaces two immutable triggers in their migration transaction to allow event counters.
    # The replacements preserve immutability of the business columns and do not remove data.
    trigger_replacements = (
        ("trg_manager_interactions_immutable", "trg_manager_interaction_body_immutable", "work.manager_interactions"),
        ("trg_plan_versions_immutable", "trg_plan_versions_content_immutable", "work.plan_versions"),
    )
    trigger_drops = tuple(f"DROP TRIGGER {old} ON {table};" for old, _, table in trigger_replacements)
    for dropped, (old, new, table) in zip(trigger_drops, trigger_replacements, strict=True):
        assert sql.index(f"CREATE TRIGGER {old} ") < sql.index(dropped) < sql.index(f"CREATE TRIGGER {new} BEFORE UPDATE ON {table}")
    assignment_actions = "DROP CONSTRAINT ck_operation_assignment_actions,"
    assert sql.count("CONSTRAINT ck_operation_assignment_actions CHECK") == 2
    assert sql.index(assignment_actions) < sql.index("ADD CONSTRAINT ck_operation_assignment_actions CHECK")
    nonce_issuers = "DROP CONSTRAINT ck_platform_nonce_issuer,"
    nonce_replacements = sql.split(nonce_issuers)
    assert len(nonce_replacements) == 3
    assert all(fragment.count("ADD CONSTRAINT ck_platform_nonce_issuer CHECK") == 1 for fragment in nonce_replacements[1:])
    native_audit = "DROP CONSTRAINT ck_platform_auth_reason,"
    native_audit_add = "ADD CONSTRAINT ck_platform_auth_reason CHECK"
    assert sql.count("CONSTRAINT ck_platform_auth_reason CHECK") == 6
    replacements = sql.split(native_audit)
    assert len(replacements) == 6
    assert all(fragment.count(native_audit_add) == 1 for fragment in replacements[1:])
    guarded_sql = guarded_sql.replace(native_audit, "").replace(nonce_issuers, "")
    for reviewed_statement in (restore_actor_fix, observed_pin_expand, *trigger_drops, assignment_actions):
        assert sql.count(reviewed_statement) == 1
        guarded_sql = guarded_sql.replace(reviewed_statement, "")
    for forbidden in ("temporal", "langgraph", "CREATE ROLE", "ALTER ROLE", "DROP "):
        assert forbidden not in guarded_sql, f"offline SQL unexpectedly contains {forbidden!r}"


def test_no_hidden_secret_or_dsn_in_alembic_ini():
    text = (BACKEND / "alembic.ini").read_text()
    assert "sqlalchemy.url" not in text and not re.search(r"postgres(ql)?(\+\w+)?://", text)
