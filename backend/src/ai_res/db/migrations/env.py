"""Alembic environment for `ai_res_db` (Blueprint §4.2; DBM-001..003).

* DSN only from AI_RES_DB_* settings (password via *_file); alembic.ini holds no secret.
* Runs as the migration identity (`ai_res_migrator`), then `SET ROLE ai_res_owner`: all objects are owned by the NOLOGIN owner.
* One version table, `platform.alembic_version`; explicit schema allowlist (no `public`, `temporal`, `langgraph`).
* Serialised by a session advisory lock; lock_timeout/statement_timeout come from the migration profile settings.
* Never imported or invoked by API startup (checked by tests/unit/test_no_startup_migration.py).
"""
import os
from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool, text

from ai_res.db.base import DOMAIN_SCHEMAS, OWNER_ROLE, VERSION_TABLE_SCHEMA, metadata
from ai_res.db.engine import build_url, connect_args
from ai_res.platform.config import load_settings

_ALLOWED = frozenset(DOMAIN_SCHEMAS)
_LOCK = "SELECT {fn}(hashtextextended('ai_res.alembic.migrations', 0))"


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    if type_ == "schema":
        return name in _ALLOWED  # None (default schema) and everything else are invisible to autogenerate
    return parent_names.get("schema_name") in _ALLOWED


def _close_migration_mode(ctx: Any, *_: Any, **__: Any) -> None:
    """All revisions of one `upgrade` share a transaction, so a transaction-local `app.migration_mode` set by one revision would stay on for every later one."""
    if not ctx.as_sql:  # offline (--sql) renders SQL only and has no connection
        ctx.connection.exec_driver_sql("SELECT set_config('app.migration_mode', 'off', true)")


def _configure(**kw: Any) -> None:
    context.configure(
        target_metadata=metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=VERSION_TABLE_SCHEMA,
        compare_type=True,
        compare_server_default=False,  # enabled deliberately later, after the first drift review (Blueprint §4.2.6)
        transaction_per_migration=False,
        on_version_apply=_close_migration_mode,
        **kw,
    )


def run_migrations_offline() -> None:
    """`alembic upgrade --sql`: SQL for review (PERSIST-004). Not a substitute for a real upgrade test."""
    _configure(url="postgresql+psycopg://", literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.execute(f"SET ROLE {OWNER_ROLE}")
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}")
        context.run_migrations()


def run_migrations_online() -> None:
    settings = load_settings(os.environ)
    engine = create_engine(build_url(settings), connect_args=connect_args(settings), poolclass=pool.NullPool)
    with engine.connect() as conn:
        guard = conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = session_user")).scalar_one()
        if guard:
            raise RuntimeError("refusing to migrate as a SUPERUSER/BYPASSRLS identity: use ai_res_migrator")
        conn.execute(text(_LOCK.format(fn="pg_advisory_lock")))  # blocks at most lock_timeout: a concurrent migrator fails fast
        try:
            conn.execute(text(f"SET ROLE {OWNER_ROLE}"))
            # Bootstrap exception: Alembic creates its version table before the first revision, so the schema must already exist.
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}"))
            conn.commit()
            _configure(connection=conn)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            # Each cleanup step must run even if the previous one fails (e.g. a dropped connection); the original error is never masked.
            try:
                conn.rollback()
            finally:
                try:
                    conn.execute(text("RESET ROLE"))
                finally:
                    released = conn.execute(text(_LOCK.format(fn="pg_advisory_unlock"))).scalar_one()
                    conn.commit()
                    if not released:
                        raise RuntimeError("migration advisory lock was not held at release time")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
