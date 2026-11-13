"""Typed configuration catalogue (INF-MVP / DOC-015 §11.3). Unknown keys and secrets-in-env fail startup.

Environment variables use the AI_RES_ prefix. Secrets are NEVER read from env values: only `*_file` paths
(Compose secrets) are accepted (security.md, ADR-022).
"""
import ipaddress
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_res.platform.pagination import KeyRing

PREFIX = "AI_RES_"
_SECRET_NAME = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)(?!.*_FILE$)", re.I)


def _split_csv(value: object) -> object:
    """Environment values are strings: `a,b` -> ('a', 'b'); an empty string is the empty tuple."""
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return value


class ConfigError(Exception):
    """Startup configuration is invalid. Messages never contain secret values."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["local", "test", "prod"] = "prod"  # safest default (ADR-022)
    llm_gateway: Literal["unconfigured", "deterministic-test-double"] = "unconfigured"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    otlp_endpoint: str | None = None  # OTLP/HTTP base URL of the Collector (S13); unset = no export
    release_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._+-]{1,64}$")  # supplied by the release process (infra release manifest); never invented
    otlp_grpc_endpoint: str | None = None  # OTLP/gRPC URL for the Temporal SDK core metrics (S13)
    # WORKING defaults of the fail-open export path (ADR-095), not SLOs (OD-02): bounded queue, short timeouts.
    otlp_export_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    otlp_metric_interval_seconds: float = Field(default=15.0, ge=1, le=300)
    otlp_queue_size: int = Field(default=2048, ge=16, le=65536)
    cursor_hmac_key_id: str = Field(default="k1", pattern=r"^[A-Za-z0-9._-]{1,32}$")
    cursor_hmac_key_file: Path | None = None
    read_lookup_max_projects: int = Field(default=100, ge=1, le=1000)  # WORKING: bound on by-id project probing (ADR-075, G-87)
    sse_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)  # WORKING: poll + re-auth period (ADR-092)
    sse_settle_seconds: float = Field(default=3.0, ge=0, le=60)  # WORKING hypothesis: hold back younger events (late commits)
    sse_max_seconds: int = Field(default=300, ge=1, le=3600)  # WORKING: stream lifetime; client reconnects with Last-Event-ID
    sse_retention_seconds: int = Field(default=604800, ge=60)  # WORKING (no approved retention): older cursor gets a gap signal
    cursor_ttl_seconds: int = Field(default=900, ge=60, le=86400)  # WORKING (page-token lifetime is not fixed by a contract); ADR-074
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
    # Authentication (S07, ADR-061/062). Names are configurable because the wire names await security-owner approval (OD-03).
    # Numeric defaults: idle 30 min / absolute 12 h are normative defaults (Auth v1.1 §6, §11); every other number is a WORKING technical value.
    session_cookie_name: str = Field(default="ai_res_session", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    csrf_header_name: str = Field(default="X-CSRF-Token", pattern=r"^[A-Za-z0-9-]{1,64}$")
    session_idle_seconds: int = Field(default=1_800, ge=60)
    session_absolute_seconds: int = Field(default=43_200, ge=60)
    session_touch_interval_seconds: int = Field(default=60, ge=1)  # WORKING: idle expiry is extended at most this often (write amplification)
    cookie_secure: bool = True
    allowed_origins: Annotated[tuple[str, ...], BeforeValidator(_split_csv)] = ()  # exact origins allowed to make cookie-authenticated state changes / CORS
    default_organization_id: UUID | None = None  # MVP is one organization per installation; login without an explicit organization uses it
    # Argon2id (OWASP Password Storage Cheat Sheet minimum profile m=19 MiB, t=2, p=1): WORKING until benchmarked on the target (ADR-061).
    argon2_time_cost: int = Field(default=2, ge=1)
    argon2_memory_kib: int = Field(default=19_456, ge=8)
    argon2_parallelism: int = Field(default=1, ge=1)
    password_min_length: int = Field(default=15, ge=15)  # the normative floor can be raised, never lowered
    password_denylist_file: Path | None = None
    # Login throttling (Auth v1.1 §4): WORKING numbers, configuration only. Process-local state (KNOWN_GAPS).
    login_account_ip_threshold: int = Field(default=5, ge=1)
    login_ip_threshold: int = Field(default=20, ge=1)
    login_account_threshold: int = Field(default=10, ge=1)
    login_global_threshold: int = Field(default=500, ge=1)
    login_enforce_ip_global: bool = False  # WORKING (ADR-071): False = ip/global only signal; True = they also refuse
    login_delay_base_seconds: int = Field(default=2, ge=1)
    login_delay_max_seconds: int = Field(default=300, ge=1)
    login_window_seconds: int = Field(default=900, ge=1)
    # TOTP seeds are encrypted at rest (AES-256-GCM). The key is a base64 32-byte secret supplied ONLY as a file (Secrets v1.1).
    mfa_encryption_key_id: str = Field(default="k1", pattern=r"^[A-Za-z0-9._-]{1,32}$")
    mfa_encryption_key_file: Path | None = None
    mfa_issuer: str = Field(default="AI RES", pattern=r"^[A-Za-z0-9 ._-]{1,48}$")
    mfa_window_steps: int = Field(default=1, ge=0, le=2)  # WORKING: accepted clock drift in 30 s steps either side
    bootstrap_secret_file: Path | None = None  # Compose secret authorising the one-time creation of the first administrator (Auth v1.1 §3.1)
    # Idempotency (ADR-024): a key-ring FILE (Compose secret), first line = active key, one `<key_id> <base64 32 bytes>` per line. Retention is WORKING (G-58).
    idempotency_keyring_file: Path | None = None
    idempotency_ttl_hours: int = Field(default=24, ge=1)
    # Service identities (Auth v1.1 §8): per-service Ed25519 signing key (own Compose secret) and the public-key registry used to verify callers.
    service_signing_key_file: Path | None = None
    service_public_keys_file: Path | None = None
    service_token_max_ttl_seconds: int = Field(default=300, ge=1)  # WORKING cap on any service credential's lifetime
    # Upload intents (S09, ADR-081). The object-store credentials are Compose secrets (files). Without all of endpoint, bucket, credentials and a size limit
    # the command fails closed (503). There is NO default size limit: no normative document fixes it (WORKING, Source & Context v1.3 §5.1).
    upload_public_endpoint: str | None = None  # scheme://host[:port] the BROWSER uploads to (the object store's S3 API is not exposed yet: S27, G-37)
    upload_bucket: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
    object_store_region: str = Field(default="us-east-1", pattern=r"^[a-z0-9-]{1,32}$")  # MinIO default region; WORKING
    object_store_access_key_file: Path | None = None
    object_store_secret_key_file: Path | None = None
    upload_url_ttl_seconds: int = Field(default=300, ge=30, le=3600)  # WORKING: "short-lived" is not quantified by the documents
    upload_max_size_bytes: int | None = Field(default=None, ge=1)
    upload_content_types: Annotated[tuple[str, ...], BeforeValidator(_split_csv)] = (
        "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/markdown", "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv")  # MVP file kinds PDF/DOCX/MD/TXT/XLSX/CSV; WORKING allowlist
    # Temporal (S11). Frontend address on the internal network only; namespace `ai-res` is created by the `temporal-namespace` one-shot. Plain gRPC inside the
    # `data` network: transport security for Temporal is not decided (WORKING, G-104).
    temporal_address: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$")
    temporal_namespace: str = Field(default="ai-res", pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    asyncapi_contract_file: Path | None = None  # packaged domain-event contract the dispatcher validates against (closes G-99 for the dispatcher process)
    worker_contract_schema_file: Path | None = None  # packaged DOC-007 schema (WORKING); needed by any process validating Worker contracts (S14; wired in S23)
    platform_api_url: str | None = None  # internal Platform API base URL used by the runtimes (never the public listener)
    platform_api_timeout_seconds: float = Field(default=10.0, gt=0, le=60)  # WORKING
    policy_timeout_seconds: float = Field(default=2.0, gt=0, le=30)  # WORKING: Policy Engine decision budget; exceeded => fail-closed 503
    trusted_proxy_cidrs: Annotated[tuple[str, ...], BeforeValidator(_split_csv)] = ()  # peers allowed to set X-Forwarded-For (Caddy); empty = ignore XFF

    @field_validator("otlp_endpoint", "otlp_grpc_endpoint")
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
        if self.cookie_secure is False and self.environment not in ("local", "test"):
            raise ValueError("cookie_secure=false is allowed only when environment is local or test (Auth v1.1 §6)")
        if self.session_idle_seconds > self.session_absolute_seconds:
            raise ValueError("session_idle_seconds cannot exceed session_absolute_seconds")
        if self.login_delay_max_seconds < self.login_delay_base_seconds:
            raise ValueError("login_delay_max_seconds cannot be below login_delay_base_seconds")
        if self.upload_public_endpoint is not None:
            u = urlsplit(self.upload_public_endpoint)
            if u.scheme not in ("http", "https") or not u.hostname or u.path not in ("", "/") or u.query or u.fragment or u.username or u.password:
                raise ValueError("upload_public_endpoint must be scheme://host[:port] without path or credentials")
            if u.scheme == "http" and self.environment not in ("local", "test"):
                raise ValueError("an http upload endpoint is allowed only when environment is local or test")
        for cidr in self.trusted_proxy_cidrs:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError("trusted_proxy_cidrs must be CIDR networks") from exc
        for origin in self.allowed_origins:
            u = urlsplit(origin)
            if (u.scheme not in ("http", "https") or not u.hostname or u.path not in ("", "/") or u.query or u.fragment
                    or u.username or u.password or origin.endswith("/")):
                raise ValueError("allowed_origins must be exact origins like https://app.example.com (no path, wildcard or credentials)")
            if u.scheme == "http" and self.environment not in ("local", "test"):
                raise ValueError("http origins are allowed only when environment is local or test")
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
