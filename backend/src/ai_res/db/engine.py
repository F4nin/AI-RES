"""Runtime/migration engine construction (Blueprint §8). Credentials come from files only and never appear in URLs that get logged."""
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ai_res.platform.config import ConfigError, Settings, read_secret_file


def connect_args(settings: Settings) -> dict[str, str | int]:
    """libpq parameters: TLS verification, identifiable application_name and per-session timeouts (no tenant state here)."""
    args: dict[str, str | int] = {
        "sslmode": settings.db_sslmode,
        "application_name": settings.db_application_name,
        "options": (
            "-c search_path=pg_catalog "
            f"-c statement_timeout={settings.db_statement_timeout_ms} "
            f"-c lock_timeout={settings.db_lock_timeout_ms} "
            f"-c idle_in_transaction_session_timeout={settings.db_idle_in_transaction_timeout_ms}"
        ),
    }
    if settings.db_sslmode == "verify-full" and settings.db_sslrootcert_file is not None:
        args["sslrootcert"] = str(settings.db_sslrootcert_file)
    return args


def build_url(settings: Settings, *, driver: str = "postgresql+psycopg") -> URL:
    if settings.db_host is None or settings.db_user is None or settings.db_password_file is None:
        raise ConfigError("db_host, db_user and db_password_file are required to connect to PostgreSQL")
    password = read_secret_file(settings.db_password_file).decode()
    return URL.create(driver, username=settings.db_user, password=password, host=settings.db_host, port=settings.db_port, database=settings.db_name)


def create_runtime_engine(settings: Settings) -> AsyncEngine:
    """Async engine for API-side Application Services. Pool resets connections with ROLLBACK on return; pre-ping detects dead ones."""
    return create_async_engine(
        build_url(settings),
        connect_args=connect_args(settings),
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_s,
        pool_reset_on_return="rollback",
    )
