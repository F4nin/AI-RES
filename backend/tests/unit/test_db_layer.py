"""Configuration guards, engine parameters and tenant-context argument safety (no database needed)."""
import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import MetaData

from ai_res.db.base import DOMAIN_SCHEMAS, NAMING_CONVENTION, metadata
from ai_res.db.engine import build_url, connect_args
from ai_res.db.tenant_context import set_tenant_context
from ai_res.platform.config import ConfigError, load_settings


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    pw = tmp_path / "pw"
    pw.write_text("s3cret-value\n")
    ca = tmp_path / "ca"
    ca.write_text("ca")
    return {"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_HOST": "db", "AI_RES_DB_USER": "ai_res_api", "AI_RES_DB_PASSWORD_FILE": str(pw),
            "AI_RES_DB_SSLROOTCERT_FILE": str(ca), **extra}


def test_schema_allowlist_matches_adr_014_and_excludes_foreign_schemas():
    assert len(DOMAIN_SCHEMAS) == len(set(DOMAIN_SCHEMAS)) == 18
    assert not {"public", "temporal", "langgraph", "pg_catalog", "information_schema"} & set(DOMAIN_SCHEMAS)
    assert {"platform", "operations", "execution", "audit", "agents"} <= set(DOMAIN_SCHEMAS)


def test_naming_convention_is_explicit():
    assert metadata.naming_convention == NAMING_CONVENTION and isinstance(metadata, MetaData)
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_password_is_read_from_file_and_never_exposed(tmp_path):
    s = load_settings(_env(tmp_path))
    url = build_url(s)
    assert url.password == "s3cret-value"  # trailing newline stripped
    assert "s3cret-value" not in repr(url) and "s3cret-value" not in str(url) and "s3cret-value" not in repr(s)


def test_connect_args_enforce_tls_search_path_and_timeouts(tmp_path):
    args = connect_args(load_settings(_env(tmp_path)))
    assert args["sslmode"] == "verify-full" and args["sslrootcert"].endswith("ca")
    assert "-c search_path=pg_catalog" in str(args["options"])
    assert "statement_timeout=15000" in str(args["options"]) and "lock_timeout=2000" in str(args["options"])
    assert "idle_in_transaction_session_timeout=30000" in str(args["options"])


def test_tls_cannot_be_disabled_in_prod(tmp_path):
    with pytest.raises(ConfigError, match="db_sslmode=disable"):
        load_settings(_env(tmp_path, AI_RES_ENVIRONMENT="prod", AI_RES_DB_SSLMODE="disable"))


def test_verify_full_requires_ca(tmp_path):
    e = _env(tmp_path)
    del e["AI_RES_DB_SSLROOTCERT_FILE"]
    with pytest.raises(ConfigError, match="db_sslrootcert_file"):
        load_settings(e)


def test_password_in_env_value_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="_FILE"):
        load_settings(_env(tmp_path, AI_RES_DB_PASSWORD="x"))


def test_build_url_requires_credentials_file():
    with pytest.raises(ConfigError):
        build_url(load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_DB_SSLMODE": "disable"}))


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def execute(self, *a: object, **k: object) -> None:
        self.calls.append((a, k))


def test_tenant_context_rejects_non_uuid_without_touching_the_database():
    rec = _Recorder()
    for bad in ("11111111-1111-1111-1111-111111111111", "'; DROP TABLE x;--", None, 5):
        with pytest.raises(TypeError):
            asyncio.run(set_tenant_context(rec, bad, None))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        asyncio.run(set_tenant_context(rec, uuid4(), "p"))  # type: ignore[arg-type]
    assert rec.calls == []


def test_tenant_context_uses_bind_parameters_and_transaction_local_flag():
    rec = _Recorder()
    org, prj = uuid4(), uuid4()
    asyncio.run(set_tenant_context(rec, org, prj))  # type: ignore[arg-type]
    stmts = [str(a[0]) for a, _ in rec.calls]
    assert all("set_config(:name, :value, true)" in s for s in stmts) and len(stmts) == 2
    assert [a[1] for a, _ in rec.calls] == [{"name": "app.organization_id", "value": str(org)}, {"name": "app.project_id", "value": str(prj)}]
