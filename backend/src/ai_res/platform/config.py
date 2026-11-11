"""Typed configuration catalogue (INF-MVP / DOC-015 §11.3). Unknown keys and secrets-in-env fail startup.

Environment variables use the AI_RES_ prefix. Secrets are NEVER read from env values: only `*_file` paths
(Compose secrets) are accepted (security.md, ADR-022).
"""
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_res.platform.pagination import KeyRing

PREFIX = "AI_RES_"
_SECRET_NAME = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)(?!.*_FILE$)", re.I)


class ConfigError(Exception):
    """Startup configuration is invalid. Messages never contain secret values."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["local", "test", "prod"] = "prod"  # safest default (ADR-022)
    llm_gateway: Literal["unconfigured", "deterministic-test-double"] = "unconfigured"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    otlp_endpoint: str | None = None
    cursor_hmac_key_id: str = Field(default="k1", pattern=r"^[A-Za-z0-9._-]{1,32}$")
    cursor_hmac_key_file: Path | None = None
    # PostgreSQL connection (S04). Passwords only via *_file. Numeric defaults are WORKING technical values (ADR-047), not SLOs (OD-02).
    db_host: str | None = None
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="ai_res_db", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    db_user: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,62}$")
    db_password_file: Path | None = None
    db_sslmode: Literal["verify-full", "disable"] = "verify-full"
    db_sslrootcert_file: Path | None = None
    db_application_name: str = Field(default="ai-res", pattern=r"^[A-Za-z0-9._-]{1,48}$")
    db_statement_timeout_ms: int = Field(default=15_000, ge=1)
    db_lock_timeout_ms: int = Field(default=2_000, ge=1)
    db_idle_in_transaction_timeout_ms: int = Field(default=30_000, ge=1)
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_pool_recycle_s: int = Field(default=1_800, ge=30)

    @field_validator("otlp_endpoint")
    @classmethod
    def _no_credentials_in_url(cls, v: str | None) -> str | None:
        if v is not None:
            u = urlsplit(v)
            if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
                raise ValueError("otlp_endpoint must be an http(s) URL without embedded credentials")
        return v

    @model_validator(mode="after")
    def _guards(self) -> "Settings":
        if self.llm_gateway == "deterministic-test-double" and self.environment != "test":
            raise ValueError("deterministic LLM test double is allowed only when environment=test (ADR-022)")
        if self.db_sslmode == "disable" and self.environment not in ("local", "test"):
            raise ValueError("db_sslmode=disable is allowed only when environment is local or test (TLS verify-full is mandatory, DBM-014)")
        if self.db_sslmode == "verify-full" and self.db_host is not None and self.db_sslrootcert_file is None:
            raise ValueError("db_sslrootcert_file is required when db_sslmode=verify-full")
        return self


def load_settings(env: Mapping[str, str]) -> Settings:
    raw: dict[str, str] = {}
    known = set(Settings.model_fields)
    for name, value in env.items():
        if name.upper().startswith(PREFIX) and not name.startswith(PREFIX):
            raise ConfigError(f"{name.upper()}: configuration keys are case-sensitive (use the exact upper-case name)")
        if not name.startswith(PREFIX):
            continue
        field = name[len(PREFIX):].lower()
        if field not in known:
            if _SECRET_NAME.search(name):
                raise ConfigError(f"{name}: secrets must be supplied as a file path via {name}_FILE, never as an env value")
            raise ConfigError(f"{name}: unknown configuration key")
        raw[field] = value
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        # Report field names and reasons only: never echo input values.
        raise ConfigError("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors(include_input=False))) from exc


def read_secret_file(path: Path) -> bytes:
    if not path.is_file():
        raise ConfigError(f"secret file not found: {path}")
    data = path.read_bytes().rstrip(b"\r\n")  # strip only the trailing newline; key bytes are otherwise preserved
    if not data:
        raise ConfigError(f"secret file is empty: {path}")
    return data


def cursor_key_ring(settings: Settings) -> KeyRing:
    if settings.cursor_hmac_key_file is None:
        raise ConfigError("cursor_hmac_key_file is required")
    secret = read_secret_file(settings.cursor_hmac_key_file)
    try:
        return KeyRing(active_id=settings.cursor_hmac_key_id, keys={settings.cursor_hmac_key_id: secret})
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
