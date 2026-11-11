# ruff: noqa: E501, S105, S106, S608  -- fixed literal SQL / fake credentials in test fixtures
"""S07 slice 8: the identity HTTP surface end to end on real PostgreSQL (AUTH-003/005/007/008, SEC-001/002/019): cookie attributes, CSRF, Origin,
deny-by-default CORS, stale/revoked/expired sessions, forged X-Forwarded-For, MFA flow, schema conformance and log hygiene."""
import base64
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import jsonschema
import pyotp
import pytest
import yaml

from ai_res.api.app import create_app
from ai_res.api.identity import build_identity_services
from ai_res.db.session import create_session_factory
from ai_res.modules.iam.passwords import PasswordHasherService
from ai_res.platform.config import load_settings

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple 42"
ORIGIN = "http://localhost:5173"
CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
H = {"Origin": ORIGIN}


class Rig:
    def __init__(self, world: Any, tmp_path: Path, **overrides: str) -> None:
        self.w = world
        key = tmp_path / "mfa.key"
        key.write_text(base64.b64encode(bytes(range(32))).decode())
        env = {"AI_RES_ENVIRONMENT": "test", "AI_RES_COOKIE_SECURE": "false", "AI_RES_ALLOWED_ORIGINS": ORIGIN, "AI_RES_MFA_ENCRYPTION_KEY_FILE": str(key),
               "AI_RES_ARGON2_TIME_COST": "1", "AI_RES_ARGON2_MEMORY_KIB": "8", "AI_RES_DEFAULT_ORGANIZATION_ID": str(world.org_a), **overrides}
        self.settings = load_settings(env)
        self.services = build_identity_services(self.settings, create_session_factory(world.engine()))
        self.app = create_app(self.settings, identity=self.services)
        h = PasswordHasherService(time_cost=1, memory_kib=8, parallelism=1)
        with world.pg.connect() as c:
            c.execute("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (%s,%s,%s,'PASSWORD',%s)", [uuid4(), world.org_a, world.user_a, h.hash(PASSWORD)])

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("198.51.100.7", 4444)), base_url="http://testserver")

    async def login(self, c: httpx.AsyncClient, password: str = PASSWORD, email: str = "a@example.com", **extra: Any) -> httpx.Response:
        return await c.post("/api/v1/auth/login", json={"email": email, "password": password, **extra}, headers=H)


@pytest.fixture
def rig(iam_world: Any, tmp_path: Path) -> Rig:
    return Rig(iam_world, tmp_path)


def session_rows(rig: Rig) -> int:
    with rig.w.pg.connect() as c:
        return int(c.execute("SELECT count(*) FROM iam.sessions").fetchone()[0])


async def test_login_sets_a_hardened_cookie_and_never_puts_the_session_in_the_body(rig: Rig) -> None:
    async with rig.client() as c:
        r = await rig.login(c)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    cookie = r.headers["set-cookie"]
    low = cookie.lower()
    assert cookie.startswith("ai_res_session=") and "httponly" in low and "samesite=lax" in low and "path=/api/v1" in low and "domain" not in low
    token = cookie.split(";")[0].split("=", 1)[1]
    assert token not in r.text and set(r.json()) == {"userId", "organizationId", "mfaRequired", "csrfToken", "idleExpiresAt", "absoluteExpiresAt"}
    assert r.json()["mfaRequired"] is False


async def test_login_response_conforms_to_the_overlay_schema_and_me_to_the_canonical_one(rig: Rig) -> None:
    overlay = yaml.safe_load((CONTRACTS / "openapi/extensions/identity_auth.yaml").read_text())
    oas = yaml.safe_load((CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml").read_text())
    async with rig.client() as c:
        login = await rig.login(c)
        me = await c.get("/api/v1/me")
    fmt = jsonschema.FormatChecker()
    jsonschema.validate(login.json(), overlay["components"]["schemas"]["SessionInfo"], format_checker=fmt)
    jsonschema.validate(me.json(), oas["components"]["schemas"]["CurrentUser"], format_checker=fmt)
    assert me.json()["displayName"] == "u" and me.json()["organizations"] == [{"organizationId": str(rig.w.org_a), "name": "o"}]


async def test_every_login_failure_is_one_identical_401(rig: Rig) -> None:
    async with rig.client() as c:
        bodies = [await rig.login(c, "wrong password value 123"), await rig.login(c, email="nobody@example.com"), await rig.login(c, organizationId=str(uuid4()))]
    assert [b.status_code for b in bodies] == [401, 401, 401]
    cleaned = [{k: v for k, v in b.json().items() if k not in ("requestId", "instance")} for b in bodies]
    assert cleaned[0] == cleaned[1] == cleaned[2] and all("set-cookie" not in b.headers for b in bodies)


async def test_login_from_a_foreign_or_missing_origin_is_refused_before_any_work(rig: Rig) -> None:
    async with rig.client() as c:
        for headers in ({"Origin": "https://evil.example"}, {}, {"Origin": "null"}, {"Referer": "https://evil.example/x"}):
            r = await c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD}, headers=headers)
            assert r.status_code == 403 and "set-cookie" not in r.headers
        ok = await c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD}, headers={"Referer": f"{ORIGIN}/login"})  # Referer is accepted only without Origin
        assert ok.status_code == 200
    assert session_rows(rig) == 1


async def test_login_validates_the_body_without_echoing_it(rig: Rig) -> None:
    secret = "Zq9-unique-marker-pw"
    async with rig.client() as c:
        extra = await c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": secret, "isAdmin": True}, headers=H)
        short = await c.post("/api/v1/auth/login", json={"email": "a", "password": secret}, headers=H)
        missing = await c.post("/api/v1/auth/login", content=b"{not json", headers={**H, "Content-Type": "application/json"})
    assert [r.status_code for r in (extra, short, missing)] == [422, 422, 422]
    assert all(secret not in r.text for r in (extra, short, missing)) and session_rows(rig) == 0


async def test_login_without_organization_and_without_a_configured_default_is_refused(iam_world: Any, tmp_path: Path) -> None:
    rig = Rig(iam_world, tmp_path, AI_RES_DEFAULT_ORGANIZATION_ID=str(uuid4()))  # a default that exists nowhere behaves like any unknown organization
    async with rig.client() as c:
        assert (await rig.login(c)).status_code == 401
        explicit = await rig.login(c, organizationId=str(iam_world.org_a))
    assert explicit.status_code == 200 and explicit.json()["organizationId"] == str(iam_world.org_a)


async def test_me_requires_a_live_session(rig: Rig) -> None:
    async with rig.client() as c:
        assert (await c.get("/api/v1/me")).status_code == 401
        assert (await c.get("/api/v1/me", headers={"Cookie": "ai_res_session=garbage"})).status_code == 401
        assert (await c.get("/api/v1/me", headers={"Cookie": f"ai_res_session={rig.w.org_a.hex}.{'A' * 43}"})).status_code == 401
        await rig.login(c)
        assert (await c.get("/api/v1/me")).status_code == 200


async def test_state_changes_need_the_csrf_token_and_an_allowed_origin(rig: Rig) -> None:
    async with rig.client() as c:
        csrf = (await rig.login(c)).json()["csrfToken"]
        assert (await c.get("/api/v1/auth/csrf")).json() == {"csrfToken": csrf}  # re-readable after a reload
        for headers in (H, {**H, "X-CSRF-Token": "wrong"}, {**H, "X-CSRF-Token": csrf[:-1]}, {"X-CSRF-Token": csrf}, {"Origin": "https://evil.example", "X-CSRF-Token": csrf}):
            r = await c.post("/api/v1/auth/logout", headers=headers)
            assert r.status_code == 403, headers
        assert (await c.get("/api/v1/me")).status_code == 200  # nothing above ended the session
        out = await c.post("/api/v1/auth/logout", headers={**H, "X-CSRF-Token": csrf})
        assert out.status_code == 204 and "ai_res_session=" in out.headers["set-cookie"] and "max-age=0" in out.headers["set-cookie"].lower()
        assert (await c.get("/api/v1/me")).status_code == 401  # the server-side session is dead even if the browser kept the cookie


@pytest.mark.parametrize("mutation", [
    "UPDATE iam.sessions SET idle_expires_at = now() - interval '1 second', row_version = row_version + 1",
    "UPDATE iam.sessions SET revoked_at = now(), revoked_reason = 'ADMIN_REVOKED', row_version = row_version + 1",
    "UPDATE iam.users SET status = 'DISABLED', row_version = row_version + 1",
])
async def test_expired_revoked_and_disabled_sessions_are_401(rig: Rig, mutation: str) -> None:
    async with rig.client() as c:
        assert (await rig.login(c)).status_code == 200 and (await c.get("/api/v1/me")).status_code == 200  # control: the session was valid
        with rig.w.pg.connect() as pg:
            pg.execute(mutation)
        stale = await c.get("/api/v1/me")
        assert stale.status_code == 401 and stale.json()["code"] == "AUTHENTICATION_REQUIRED"  # same answer whatever the reason


async def test_cors_is_deny_by_default(rig: Rig) -> None:
    async with rig.client() as c:
        pre = await c.options("/api/v1/auth/login", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-csrf-token"})
        r = await rig.login(c)
        evil = await c.get("/api/v1/me", headers={"Origin": "https://evil.example"})
    for resp in (pre, r, evil):
        assert not any(h.lower().startswith("access-control-") for h in resp.headers), dict(resp.headers)
    assert pre.status_code in (404, 405)


async def test_forged_x_forwarded_for_from_an_untrusted_peer_does_not_evade_the_throttle(iam_world: Any, tmp_path: Path) -> None:
    rig = Rig(iam_world, tmp_path, AI_RES_LOGIN_ACCOUNT_THRESHOLD="4", AI_RES_LOGIN_ACCOUNT_IP_THRESHOLD="50", AI_RES_LOGIN_IP_THRESHOLD="50")
    async with rig.client() as c:
        codes = []
        for i in range(6):
            r = await c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": f"wrong password {i} xxxxx"}, headers={**H, "X-Forwarded-For": f"203.0.113.{i + 1}"})
            codes.append(r.status_code)
        blocked = await c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD}, headers={**H, "X-Forwarded-For": "192.0.2.77"})
    assert codes[:4] == [401] * 4 and 429 in codes[4:] and blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1  # even the right password waits


async def test_password_change_flow_over_http(rig: Rig) -> None:
    new = "another long passphrase 987"
    async with rig.client() as c, rig.client() as other:
        csrf = (await rig.login(c)).json()["csrfToken"]
        await rig.login(other)
        hdr = {**H, "X-CSRF-Token": csrf}
        assert (await c.post("/api/v1/auth/password", json={"currentPassword": "nope nope nope nope", "newPassword": new}, headers=hdr)).status_code == 422  # not 401: the session is fine
        weak = await c.post("/api/v1/auth/password", json={"currentPassword": PASSWORD, "newPassword": "zq9x!m"}, headers=hdr)
        assert weak.status_code == 422 and "zq9x!m" not in weak.text and weak.json()["errors"][0]["field"] == "newPassword"
        assert (await c.post("/api/v1/auth/password", json={"currentPassword": PASSWORD, "newPassword": new}, headers=hdr)).status_code == 204
        assert (await other.get("/api/v1/me")).status_code == 401 and (await c.get("/api/v1/me")).status_code == 200
        assert (await rig.login(c, PASSWORD)).status_code == 401 and (await rig.login(c, new)).status_code == 200


async def test_mfa_flow_rotates_the_session_and_recovery_codes_are_single_use(rig: Rig) -> None:
    async with rig.client() as c:
        first = await rig.login(c)
        hdr = {**H, "X-CSRF-Token": first.json()["csrfToken"]}
        old_cookie = c.cookies.get("ai_res_session")
        enrol = await c.post("/api/v1/auth/mfa/enrollment", json={"currentPassword": PASSWORD}, headers=hdr)
        assert enrol.status_code == 201 and enrol.json()["otpauthUri"].startswith("otpauth://totp/")
        secret = enrol.json()["secret"]
        done = await c.post("/api/v1/auth/mfa/enrollment/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=hdr)
        assert done.status_code == 200 and len(done.json()["recoveryCodes"]) >= 8 and done.json()["csrfToken"] != first.json()["csrfToken"]
        assert c.cookies.get("ai_res_session") != old_cookie  # rotated on privilege change
        assert (await c.get("/api/v1/me", headers={"Cookie": f"ai_res_session={old_cookie}"})).status_code == 401
        code = done.json()["recoveryCodes"][0]
    async with rig.client() as c2:  # a fresh login now requires the second factor
        again = await rig.login(c2)
        assert again.json()["mfaRequired"] is True
        hdr2 = {**H, "X-CSRF-Token": again.json()["csrfToken"]}
        bad = await c2.post("/api/v1/auth/mfa/verify", json={"code": "000000"}, headers=hdr2)
        assert bad.status_code == 401
        ok = await c2.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=hdr2)
        assert ok.status_code == 200
    async with rig.client() as c3:
        third = await rig.login(c3)
        replay = await c3.post("/api/v1/auth/mfa/verify", json={"code": code}, headers={**H, "X-CSRF-Token": third.json()["csrfToken"]})
        assert replay.status_code == 401  # recovery code already spent


async def test_no_credential_ever_reaches_the_logs(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    secrets_seen: list[str] = [PASSWORD]
    async with rig.client() as c:
        first = await rig.login(c)
        secrets_seen += [c.cookies.get("ai_res_session") or "", first.json()["csrfToken"]]
        hdr = {**H, "X-CSRF-Token": first.json()["csrfToken"]}
        enrol = await c.post("/api/v1/auth/mfa/enrollment", json={"currentPassword": PASSWORD}, headers=hdr)
        secrets_seen.append(enrol.json()["secret"])
        done = await c.post("/api/v1/auth/mfa/enrollment/confirm", json={"code": pyotp.TOTP(enrol.json()["secret"]).now()}, headers=hdr)
        secrets_seen += done.json()["recoveryCodes"]
        await rig.login(c, "bad password value 1234")
    text = "\n".join(r.getMessage() + " " + str(r.__dict__.get("args", "")) for r in caplog.records)
    with rig.w.pg.connect() as pg:
        audit = repr(pg.execute("SELECT to_jsonb(a)::text FROM audit.audit_events a").fetchall())
    for secret in secrets_seen:
        assert secret and secret not in text and secret not in audit


async def test_a_session_that_skipped_the_second_factor_is_not_authenticated_for_anything_but_the_second_factor(rig: Rig) -> None:
    async with rig.client() as c:
        first = await rig.login(c)
        hdr = {**H, "X-CSRF-Token": first.json()["csrfToken"]}
        enrol = await c.post("/api/v1/auth/mfa/enrollment", json={"currentPassword": PASSWORD}, headers=hdr)
        done = await c.post("/api/v1/auth/mfa/enrollment/confirm", json={"code": pyotp.TOTP(enrol.json()["secret"]).now()}, headers=hdr)
        recovery = done.json()["recoveryCodes"][0]
    async with rig.client() as c2:
        pending = await rig.login(c2)
        assert pending.json()["mfaRequired"] is True
        hdr2 = {**H, "X-CSRF-Token": pending.json()["csrfToken"]}
        for method, path, body in (("GET", "/api/v1/me", None), ("POST", "/api/v1/auth/password", {"currentPassword": PASSWORD, "newPassword": "another long passphrase 987"}),
                                   ("POST", "/api/v1/auth/mfa/enrollment", {"currentPassword": PASSWORD}), ("POST", "/api/v1/auth/mfa/enrollment/confirm", {"code": "123456"})):
            r = await c2.request(method, path, json=body, headers=hdr2)
            assert r.status_code == 403 and r.json()["errors"] == [{"field": "session", "reason": "mfa_required"}], (path, r.status_code)
        assert (await c2.get("/api/v1/auth/csrf")).status_code == 200  # the client may still learn its CSRF token
        assert (await c2.post("/api/v1/auth/mfa/verify", json={"code": recovery}, headers=hdr2)).status_code == 200
        assert (await c2.get("/api/v1/me")).status_code == 200  # the rotated, verified session works
    async with rig.client() as c3:  # logout is always allowed, even while pending
        again = await rig.login(c3)
        assert (await c3.post("/api/v1/auth/logout", headers={**H, "X-CSRF-Token": again.json()["csrfToken"]})).status_code == 204


async def test_starting_mfa_enrolment_needs_a_fresh_password_proof(rig: Rig) -> None:
    """ADR-072: a stolen cookie alone must not bind an attacker's authenticator (NIST 800-63B §6.1.2)."""
    async with rig.client() as c:
        first = await rig.login(c)
        hdr = {**H, "X-CSRF-Token": first.json()["csrfToken"]}
        assert (await c.post("/api/v1/auth/mfa/enrollment", headers=hdr)).status_code == 422  # no proof at all
        wrong = await c.post("/api/v1/auth/mfa/enrollment", json={"currentPassword": "not the password 123"}, headers=hdr)
        assert wrong.status_code == 422 and wrong.json()["errors"] == [{"field": "currentPassword", "reason": "invalid_current_password"}]
        assert "secret" not in wrong.text
        with rig.w.pg.connect() as conn:
            assert conn.execute("SELECT count(*) FROM iam.mfa_factors").fetchone()[0] == 0  # nothing was created
            reasons = [r[0] for r in conn.execute("SELECT coalesce(reason_code, 'ok') FROM audit.audit_events WHERE action = 'AUTH_REAUTHENTICATED' ORDER BY occurred_at").fetchall()]
        assert reasons == ["invalid_current_password"]
        ok = await c.post("/api/v1/auth/mfa/enrollment", json={"currentPassword": PASSWORD}, headers=hdr)
        assert ok.status_code == 201
