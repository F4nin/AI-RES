"""AUTH-007: opaque tokens, CSRF derivation, Origin validation and cookie attributes (pure functions, no DB)."""
from uuid import uuid4

import pytest

from ai_res.api.request_security import build_session_cookie, check_state_change_origin, constant_time_equal
from ai_res.modules.iam.tokens import csrf_digest, csrf_token_for, new_session_token, parse_session_token, session_digest
from ai_res.platform.config import load_settings
from ai_res.platform.problems import ErrorCode, ProblemError

ORIGIN = "https://app.example.com"


def test_token_is_opaque_random_and_carries_only_a_lookup_hint() -> None:
    org = uuid4()
    a, b = new_session_token(org), new_session_token(org)
    assert a != b
    parsed = parse_session_token(a)
    assert parsed is not None and parsed.organization_id == org
    assert len(a.split(".")[1]) >= 43  # 256 bits of randomness


_HEX, _RAND = "a" * 32, "A" * 43


@pytest.mark.parametrize("bad", ["", "x", "not-a-uuid.abc", _HEX + ".short", "g" * 32 + "." + _RAND, _HEX + "." + _RAND + "\n", _HEX + "." + _RAND + "A"])
def test_malformed_tokens_are_rejected_before_any_lookup(bad: str) -> None:
    assert parse_session_token(bad) is None


def test_digests_are_32_bytes_and_differ_between_session_and_csrf() -> None:
    t = new_session_token(uuid4())
    c = csrf_token_for(t)
    assert len(session_digest(t)) == 32 and len(csrf_digest(c)) == 32
    assert session_digest(t) != csrf_digest(c) and c != t


def test_csrf_token_is_deterministic_per_session_and_unique_across_sessions() -> None:
    org = uuid4()
    t1, t2 = new_session_token(org), new_session_token(org)
    assert csrf_token_for(t1) == csrf_token_for(t1) and csrf_token_for(t1) != csrf_token_for(t2)


def test_constant_time_equal() -> None:
    assert constant_time_equal("abc", "abc") and not constant_time_equal("abc", "abd") and not constant_time_equal("", "abc")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_state_change_with_allowed_origin_passes(method: str) -> None:
    check_state_change_origin(method, origin=ORIGIN, referer=None, allowed=(ORIGIN,))


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_need_no_origin(method: str) -> None:
    check_state_change_origin(method, origin=None, referer=None, allowed=(ORIGIN,))


@pytest.mark.parametrize(("origin", "referer"), [
    ("https://evil.example.net", None),
    ("null", None),
    (None, None),  # neither header: refuse
    (None, "https://evil.example.net/page"),
    ("https://app.example.com.evil.net", None),
    ("http://app.example.com", None),  # scheme mismatch
])
def test_state_change_with_foreign_or_missing_origin_is_403(origin: str | None, referer: str | None) -> None:
    with pytest.raises(ProblemError) as e:
        check_state_change_origin("POST", origin=origin, referer=referer, allowed=(ORIGIN,))
    assert e.value.code is ErrorCode.ACCESS_DENIED


def test_referer_is_accepted_only_when_origin_header_is_absent_and_matches() -> None:
    check_state_change_origin("POST", origin=None, referer=ORIGIN + "/projects/1", allowed=(ORIGIN,))


def test_empty_allowlist_refuses_every_state_change_fail_closed() -> None:
    with pytest.raises(ProblemError):
        check_state_change_origin("POST", origin=ORIGIN, referer=None, allowed=())


def test_session_cookie_has_security_attributes() -> None:
    s = load_settings({})
    c = build_session_cookie(s, "tok")
    assert c["key"] == "ai_res_session" and c["value"] == "tok"
    assert c["httponly"] is True and c["secure"] is True and c["samesite"] == "lax"
    assert c["path"] == "/api/v1" and c.get("domain") is None


def test_insecure_cookie_is_refused_outside_local_and_test() -> None:
    with pytest.raises(Exception, match="cookie_secure"):
        load_settings({"AI_RES_COOKIE_SECURE": "false", "AI_RES_ENVIRONMENT": "prod"})
    assert load_settings({"AI_RES_COOKIE_SECURE": "false", "AI_RES_ENVIRONMENT": "local"}).cookie_secure is False


@pytest.mark.parametrize("origin", ["*", "https://app.example.com/", "https://app.example.com/path", "ftp://x.example.com", "https://u:p@x.example.com"])
def test_allowed_origins_must_be_exact_origins(origin: str) -> None:
    with pytest.raises(Exception, match="allowed_origins"):
        load_settings({"AI_RES_ALLOWED_ORIGINS": origin})


def test_password_min_length_cannot_be_configured_below_normative_floor() -> None:
    with pytest.raises(Exception, match="password_min_length"):
        load_settings({"AI_RES_PASSWORD_MIN_LENGTH": "14"})
