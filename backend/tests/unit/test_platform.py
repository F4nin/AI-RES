import base64
import io
import json
import logging
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ai_res.platform import clock, ids
from ai_res.platform.concurrency import format_etag, parse_if_match
from ai_res.platform.config import ConfigError, Settings, cursor_key_ring, load_settings
from ai_res.platform.pagination import InvalidCursor, KeyRing, decode_cursor, encode_cursor, validate_limit
from ai_res.platform.ports import AuditOutcome, AuditRecord, Effect, PolicyDecision, PolicyRequest, audit_or_abort, decide_fail_closed
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.redaction import REDACTED, configure_logging
from tests.unit.conftest import RING

# ---------- ids / clock ----------

def test_uuid7_version_and_time_ordering():
    a, b = ids.new_id(), ids.new_id()
    assert ids.is_uuid7(a) and ids.is_uuid7(b) and a != b
    assert sorted([b, a])[0].int <= sorted([b, a])[1].int


def test_rfc3339_utc_and_naive_rejected():
    assert clock.to_rfc3339(datetime(2026, 11, 11, 10, 0, tzinfo=UTC)) == "2026-11-11T10:00:00.000Z"
    local = datetime(2026, 11, 11, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    assert clock.to_rfc3339(local).endswith("T10:00:00.000Z")
    with pytest.raises(ValueError):
        clock.to_rfc3339(datetime(2026, 11, 11))
    assert re.match(r"^\d{4}-\d\d-\d\dT[\d:.]+Z$", clock.to_rfc3339(clock.utc_now()))


# ---------- Problem Details ----------

async def test_unhandled_exception_is_generic_500(client):
    r = await client.get("/t/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "super-secret" not in r.text and "postgres" not in r.text and "Traceback" not in r.text


async def test_validation_error_has_code_and_does_not_echo_input(client):
    r = await client.post("/t/body", json={"name": "SECRET-VALUE-123", "count": "not-a-number"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert "SECRET-VALUE-123" not in r.text and "not-a-number" not in r.text
    assert r.json()["errors"][0]["field"].endswith("count")


async def test_problem_error_and_http_error_mapping(client):
    r = await client.get("/t/problem")
    assert r.status_code == 409 and r.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    r = await client.get("/t/missing")
    assert r.status_code == 404 and r.json()["code"] == "RESOURCE_NOT_FOUND"
    assert r.headers["content-type"].startswith("application/problem+json")


def test_error_code_taxonomy_matches_doc006():
    required = {"VALIDATION_ERROR", "AUTHENTICATION_REQUIRED", "ACCESS_DENIED", "RESOURCE_NOT_FOUND", "STATE_TRANSITION_NOT_ALLOWED",
                "VERSION_CONFLICT", "PRECONDITION_REQUIRED", "IDEMPOTENCY_KEY_REUSED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE",
                "OPERATION_NOT_READY", "POLICY_ENGINE_UNAVAILABLE", "INTERNAL_ERROR"}
    assert required <= {c.value for c in ErrorCode}


# ---------- cursor ----------

def test_cursor_roundtrip():
    t = encode_cursor(RING, subject="u1", audience="list-a", filters={"status": "OPEN"}, keyset=["2026-01-01", "id1"], ttl_seconds=60)
    assert decode_cursor(RING, t, subject="u1", audience="list-a", filters={"status": "OPEN"}) == ["2026-01-01", "id1"]


@pytest.mark.parametrize("mutate", ["flip_payload", "flip_mac", "truncate"])
def test_cursor_tampering_rejected(mutate):
    t = encode_cursor(RING, subject="u1", audience="a", filters={}, keyset=[1], ttl_seconds=60)
    body, mac = t.split(".")
    bad = {"flip_payload": f"{body[:-2]}AA.{mac}", "flip_mac": f"{body}.{mac[:-2]}AA", "truncate": body}[mutate]
    with pytest.raises(InvalidCursor) as e:
        decode_cursor(RING, bad, subject="u1", audience="a", filters={})
    assert e.value.status == 400 and e.value.code is ErrorCode.VALIDATION_ERROR


def test_cursor_bound_to_subject_and_filter_and_key():
    t = encode_cursor(RING, subject="u1", audience="a", filters={"a": 1}, keyset=[1], ttl_seconds=60)
    with pytest.raises(InvalidCursor):
        decode_cursor(RING, t, subject="u2", audience="a", filters={"a": 1})  # other user
    with pytest.raises(InvalidCursor):
        decode_cursor(RING, t, subject="u1", audience="a", filters={"a": 2})  # changed filter
    other = KeyRing(active_id="k1", keys={"k1": b"b" * 32})
    with pytest.raises(InvalidCursor):
        decode_cursor(other, t, subject="u1", audience="a", filters={"a": 1})  # different secret


def test_cursor_key_rotation_old_key_still_verifies_new_cursors_use_active():
    old = KeyRing(active_id="k1", keys={"k1": b"a" * 32})
    t_old = encode_cursor(old, subject="u", audience="a", filters={}, keyset=[1], ttl_seconds=60)
    rotated = KeyRing(active_id="k2", keys={"k1": b"a" * 32, "k2": b"c" * 32})
    assert decode_cursor(rotated, t_old, subject="u", audience="a", filters={}) == [1]
    t_new = encode_cursor(rotated, subject="u", audience="a", filters={}, keyset=[2], ttl_seconds=60)
    assert json.loads(base64.urlsafe_b64decode(t_new.split(".")[0] + "=="))["kid"] == "k2"
    retired = KeyRing(active_id="k2", keys={"k2": b"c" * 32})
    with pytest.raises(InvalidCursor):
        decode_cursor(retired, t_old, subject="u", audience="a", filters={})  # key removed -> old cursors rejected


@given(st.text(max_size=200))
def test_cursor_garbage_only_raises_invalid_cursor(garbage):
    with pytest.raises(InvalidCursor):
        decode_cursor(RING, garbage, subject="u", audience="a", filters={})


def test_keyring_rejects_short_keys_and_limit_bounds():
    with pytest.raises(ValueError):
        KeyRing(active_id="k", keys={"k": b"short"})
    assert validate_limit(None, 50) == 50 and validate_limit(10, 50) == 10
    for bad in (0, -1, 10_000):
        with pytest.raises(ProblemError):
            validate_limit(bad, 50)


# ---------- ETag / If-Match ----------

async def test_if_match_missing_stale_malformed_and_match(client):
    assert (await client.patch("/t/versioned")).status_code == 428
    assert (await client.patch("/t/versioned", headers={"If-Match": '"v2"'})).status_code == 412
    assert (await client.patch("/t/versioned", headers={"If-Match": "*"})).status_code == 412  # no last-write-wins
    assert (await client.patch("/t/versioned", headers={"If-Match": "garbage"})).status_code == 412
    assert (await client.patch("/t/versioned", headers={"If-Match": '"v3"'})).status_code == 200
    assert (await client.patch("/t/versioned", headers={"If-Match": '"v2"'})).json()["code"] == "VERSION_CONFLICT"


def test_etag_format_roundtrip():
    assert format_etag(7) == '"v7"' and parse_if_match('"v7"') == 7
    with pytest.raises(ValueError):
        format_etag(0)


# ---------- redaction ----------

def test_log_redaction_golden():
    buf = io.StringIO()
    log = configure_logging("DEBUG", buf)
    log.info("login with password=hunter2 and Authorization: Bearer abcdefghijklmnop", extra={
        "password": "hunter2", "headers": {"Cookie": "ai_res_session=SESSION123", "X-Ok": "visible"},
        "csrf_token": "csrf-abc", "dsn": "postgresql://u:pw@h/db", "note": "ai_res_session=SESSION999"})
    try:
        raise RuntimeError("secret detail")
    except RuntimeError:
        log.exception("failure")
    out = buf.getvalue()
    for leaked in ("hunter2", "abcdefghijklmnop", "SESSION123", "SESSION999", "csrf-abc", "u:pw@h", "secret detail"):
        assert leaked not in out, leaked
    assert REDACTED in out and "visible" in out
    assert all(json.loads(line) for line in out.splitlines())


async def test_spans_do_not_carry_sensitive_request_data(client, exporter):
    await client.get("/t/ok?token=QUERYSECRET",
                     headers={"Authorization": "Bearer HEADERSECRET1234", "Cookie": "ai_res_session=COOKIESECRET"})
    spans = exporter.get_finished_spans()
    assert spans
    dumped = json.dumps([dict(s.attributes or {}) for s in spans])
    for leaked in ("QUERYSECRET", "HEADERSECRET1234", "COOKIESECRET"):
        assert leaked not in dumped
    assert dict(spans[0].attributes or {})["http.route"] == "/t/ok"


# ---------- correlation ----------

TP = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


async def test_incoming_traceparent_links_span_and_request_id_preserved(client, exporter):
    r = await client.get("/t/ok", headers={"traceparent": TP, "X-Request-ID": "req-12345678"})
    span = exporter.get_finished_spans()[-1]
    assert format(span.context.trace_id, "032x") == TP.split("-")[1]  # same trace as the caller
    assert span.parent is not None and format(span.parent.span_id, "016x") == TP.split("-")[2]
    tp = r.headers["traceparent"]
    assert tp.split("-")[1] == TP.split("-")[1] and tp.split("-")[2] == format(span.context.span_id, "016x")  # our own span id
    assert r.headers["x-request-id"] == "req-12345678"


async def test_missing_or_invalid_correlation_is_generated(client, exporter):
    r = await client.get("/t/ok")
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", r.headers["traceparent"]) and len(r.headers["x-request-id"]) >= 8
    r = await client.get("/t/ok", headers={"traceparent": "garbage", "X-Request-ID": "bad id with spaces"})
    assert r.headers["traceparent"] != "garbage" and " " not in r.headers["x-request-id"]
    assert exporter.get_finished_spans()[-1].parent is None


async def test_request_id_with_trailing_newline_is_replaced():
    from ai_res.api.app import create_app
    app = create_app(Settings(environment="test"))
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/nope", "raw_path": b"/nope", "query_string": b"", "root_path": "",
             "scheme": "http", "http_version": "1.1", "server": ("t", 80), "client": ("c", 1),
             "headers": [(b"x-request-id", b"abcdefgh\n")]}
    await app(scope, receive, send)
    rid = dict(sent[0]["headers"])[b"x-request-id"].decode()
    assert "\n" not in rid and rid != "abcdefgh\n" and len(rid) == 32  # replaced by a generated id


def test_sensitive_key_matching_is_token_based():
    from ai_res.platform.redaction import is_sensitive_key
    for k in ("password", "api_key", "apiKey", "Set-Cookie", "csrf_token", "source_text", "connection_string", "X-Session-Id"):
        assert is_sensitive_key(k), k
    for k in ("resource_id", "resource_type", "content_type", "footprint", "organization_id", "request_id"):
        assert not is_sensitive_key(k), k


async def test_response_correlation_headers_not_duplicated(client):
    r = await client.get("/t/ok", headers={"X-Request-ID": "req-12345678"})
    assert len(r.headers.get_list("x-request-id")) == 1 and len(r.headers.get_list("traceparent")) == 1


async def test_500_carries_correlation_and_no_exception_in_spans(client, exporter):
    r = await client.get("/t/boom", headers={"X-Request-ID": "req-abcdefgh", "traceparent": TP})
    assert r.status_code == 500 and r.headers["x-request-id"] == "req-abcdefgh" and r.headers["traceparent"].startswith("00-" + TP.split("-")[1])
    assert r.json()["requestId"] == "req-abcdefgh" and r.headers["cache-control"] == "no-store"
    span = exporter.get_finished_spans()[-1]
    assert span.status.status_code.name == "ERROR" and not span.events
    assert "super-secret" not in json.dumps([dict(s.attributes or {}) for s in exporter.get_finished_spans()])


async def test_request_id_context_does_not_leak_between_requests(client):
    await client.get("/t/boom", headers={"X-Request-ID": "req-leak0001"})
    r = await client.get("/t/problem")
    assert r.json()["requestId"] != "req-leak0001"


async def test_problem_body_includes_request_id(client):
    r = await client.get("/t/problem", headers={"X-Request-ID": "req-abcdefgh"})
    assert r.json()["requestId"] == "req-abcdefgh"


# ---------- config ----------

def test_config_defaults_to_prod_and_rejects_unknown_key():
    assert load_settings({}).environment == "prod"
    with pytest.raises(ConfigError, match="unknown configuration key"):
        load_settings({"AI_RES_NOT_A_SETTING": "1"})
    assert load_settings({"AI_RES_CURSOR_HMAC_KEY_ID": "k2"}).cursor_hmac_key_id == "k2"  # key *id* is not a secret
    with pytest.raises(ConfigError, match="secrets must be supplied"):
        load_settings({"AI_RES_DB_PASSWORD": "x"})


def test_config_secret_in_env_is_rejected_without_echoing_value():
    with pytest.raises(ConfigError) as e:
        load_settings({"AI_RES_CURSOR_HMAC_KEY": "topsecretvalue"})
    assert "topsecretvalue" not in str(e.value) and "_FILE" in str(e.value)


def test_config_test_double_only_in_test_profile():
    for env in ("local", "prod"):
        with pytest.raises(ConfigError):
            load_settings({"AI_RES_ENVIRONMENT": env, "AI_RES_LLM_GATEWAY": "deterministic-test-double"})
    assert load_settings({"AI_RES_ENVIRONMENT": "test", "AI_RES_LLM_GATEWAY": "deterministic-test-double"}).environment == "test"
    with pytest.raises(ConfigError):
        load_settings({"AI_RES_LLM_GATEWAY": "deterministic-test-double"})  # default profile is prod


def test_config_invalid_value_does_not_echo_it():
    with pytest.raises(ConfigError) as e:
        load_settings({"AI_RES_LOG_LEVEL": "VERYSECRETLEVEL"})
    assert "VERYSECRETLEVEL" not in str(e.value)


def test_cursor_key_from_secret_file(tmp_path):
    f = tmp_path / "cursor.key"
    f.write_bytes(b"k" * 40 + b"\n")
    ring = cursor_key_ring(load_settings({"AI_RES_CURSOR_HMAC_KEY_FILE": str(f)}))
    assert ring.keys["k1"] == b"k" * 40
    short = tmp_path / "short.key"
    short.write_bytes(b"x")
    with pytest.raises(ConfigError):
        cursor_key_ring(load_settings({"AI_RES_CURSOR_HMAC_KEY_FILE": str(short)}))
    with pytest.raises(ConfigError):
        cursor_key_ring(load_settings({"AI_RES_CURSOR_HMAC_KEY_FILE": str(tmp_path / "missing")}))
    with pytest.raises(ConfigError):
        cursor_key_ring(load_settings({}))


# ---------- ports: fail-closed ----------

REQ = PolicyRequest(actor_id="u", action="x.y", resource_type="Project")


class _Policy:
    def __init__(self, effect=None, exc=None):
        self.effect, self.exc = effect, exc

    async def decide(self, request):
        if self.exc:
            raise self.exc
        return PolicyDecision(effect=self.effect, reason_code="R", policy_version="v1")


async def test_policy_outage_denies_with_503():
    with pytest.raises(ProblemError) as e:
        await decide_fail_closed(_Policy(exc=ConnectionError()), REQ, timeout_seconds=1)
    assert e.value.code is ErrorCode.POLICY_ENGINE_UNAVAILABLE and e.value.status == 503


async def test_policy_deny_and_approval_required_never_allow():
    for eff in (Effect.DENY, Effect.APPROVAL_REQUIRED):
        with pytest.raises(ProblemError) as e:
            await decide_fail_closed(_Policy(eff), REQ, timeout_seconds=1)
        assert e.value.code is ErrorCode.ACCESS_DENIED
    assert (await decide_fail_closed(_Policy(Effect.ALLOW), REQ, timeout_seconds=1)).effect is Effect.ALLOW


async def test_audit_failure_aborts_action():
    class Broken:
        async def write(self, record):
            raise OSError("db down")

    with pytest.raises(ProblemError) as e:
        await audit_or_abort(Broken(), AuditRecord(actor_id="u", action="a", outcome=AuditOutcome.ALLOWED, resource_type="Project"),
                             timeout_seconds=1)
    assert e.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE


# ---------- review follow-ups ----------

def test_cursor_audience_expiry_and_size_bounds():
    t = encode_cursor(RING, subject="u", audience="list-a", filters={}, keyset=[1], ttl_seconds=10, now=1000)
    assert decode_cursor(RING, t, subject="u", audience="list-a", filters={}, now=1005) == [1]
    with pytest.raises(InvalidCursor):
        decode_cursor(RING, t, subject="u", audience="list-b", filters={}, now=1005)  # other endpoint
    with pytest.raises(InvalidCursor):
        decode_cursor(RING, t, subject="u", audience="list-a", filters={}, now=1011)  # expired
    with pytest.raises(InvalidCursor):
        padded = encode_cursor(RING, subject="u", audience="list-a", filters={}, keyset=["x" * 3000], ttl_seconds=60, now=1000)
        assert len(padded) > 2048  # a validly signed token is still refused when it exceeds the size cap
        decode_cursor(RING, padded, subject="u", audience="list-a", filters={}, now=1001)
    with pytest.raises(ValueError):
        encode_cursor(RING, subject="u", audience="a", filters={}, keyset=[], ttl_seconds=0)


def test_keyring_repr_hides_secrets_and_is_immutable():
    ring = KeyRing(active_id="k1", keys={"k1": b"S" * 40})
    assert "SSSS" not in repr(ring) and "k1" in repr(ring)
    with pytest.raises(TypeError):
        ring.keys["k1"] = b"x" * 40  # type: ignore[index]


def test_redaction_extended_patterns_and_reserved_fields():
    buf = io.StringIO()
    log = configure_logging("DEBUG", buf)
    log.info('json {"password": "p1 p2"} basic Authorization: Basic dXNlcjpwYXNz url https://user:pw@host/x amqp://a:b@h/v '
             'key sk-abcdefghijklmnopqrstuv', extra={"level": "FORGED", "ts": "FORGED", "payload": {"doc": "source fragment"}, "blob": b"rawbytes"})
    out = buf.getvalue()
    for leaked in ("p1 p2", "dXNlcjpwYXNz", "user:pw", "a:b@h", "sk-abcdefghijklmnopqrstuv", "source fragment", "rawbytes"):
        assert leaked not in out, leaked
    rec = json.loads(out)
    assert rec["level"] == "INFO" and rec["ts"] != "FORGED" and rec["ctx"]["level"] == "FORGED"  # extras cannot overwrite fields


def test_uvicorn_loggers_are_redacted_and_access_log_drops_query():
    buf = io.StringIO()
    configure_logging("INFO", buf)
    logging.getLogger("uvicorn.error").error("db failure postgresql://u:pw@h/db password=abc")
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4", "GET", "/x?cursor=SECRETCURSOR", "1.1", 200)
    out = buf.getvalue()
    assert "u:pw@h" not in out and "password=abc" not in out and "SECRETCURSOR" not in out


async def test_http_exception_headers_pass_through_and_503_maps(client):
    r = await client.post("/t/ok")  # route exists for GET only
    assert r.status_code == 405 and "allow" in r.headers and r.headers["cache-control"] == "no-store"


def test_problem_error_rejects_non_error_status():
    for bad in (0, 200, 302, 700):
        with pytest.raises(ValueError):
            ProblemError(ErrorCode.ACCESS_DENIED, status=bad)


def test_if_match_rejects_zero_and_leading_zeros_and_weak():
    for bad in ('"v0"', '"v007"', 'W/"v1"', '"v١"'):
        with pytest.raises(ProblemError):
            parse_if_match(bad)


def test_config_hardening():
    with pytest.raises(ConfigError):
        load_settings({"ai_res_environment": "local"})  # case-sensitive prefix typo is not silently ignored
    with pytest.raises(ConfigError):
        load_settings({"AI_RES_OTLP_ENDPOINT": "https://user:pass@collector:4318"})
    with pytest.raises(ConfigError):
        load_settings({"AI_RES_CURSOR_HMAC_KEY_ID": "bad id!"})


def test_startup_from_env_requires_cursor_key(tmp_path):
    from ai_res.api.app import create_app_from_env
    with pytest.raises(ConfigError):
        create_app_from_env({})
    f = tmp_path / "k"
    f.write_bytes(b"z" * 40)
    app = create_app_from_env({"AI_RES_CURSOR_HMAC_KEY_FILE": str(f)})
    assert app.state.cursor_key_ring.active_id == "k1"


async def test_policy_timeout_fails_closed_and_malformed_decision():
    import asyncio

    class Hung:
        async def decide(self, request):
            await asyncio.sleep(5)

    with pytest.raises(ProblemError) as e:
        await decide_fail_closed(Hung(), REQ, timeout_seconds=0.05)
    assert e.value.code is ErrorCode.POLICY_ENGINE_UNAVAILABLE

    class Malformed:
        async def decide(self, request):
            return None

    with pytest.raises(ProblemError) as e:
        await decide_fail_closed(Malformed(), REQ, timeout_seconds=1)
    assert e.value.code is ErrorCode.POLICY_ENGINE_UNAVAILABLE
    with pytest.raises(ValueError):
        PolicyDecision(effect="allow", reason_code="R", policy_version="v1")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PolicyRequest(actor_id="u", action="a", resource_type="T", project_id="p")  # project without organization


async def test_policy_problem_error_from_port_is_not_relabelled():
    class Denying:
        async def decide(self, request):
            raise ProblemError(ErrorCode.ACCESS_DENIED)

    with pytest.raises(ProblemError) as e:
        await decide_fail_closed(Denying(), REQ, timeout_seconds=1)
    assert e.value.code is ErrorCode.ACCESS_DENIED


def test_principal_and_service_identity_require_aware_expiry():
    from datetime import datetime

    from ai_res.platform.ports import Principal, ServiceIdentity, ServiceName
    with pytest.raises(ValueError):
        Principal(user_id="u", session_id="s", mfa_verified=False, expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        ServiceIdentity(name=ServiceName.API, audience=ServiceName.WORKER_RUNTIME, expires_at=datetime(2030, 1, 1))


def test_startup_installs_redacting_logging(tmp_path):
    from ai_res.api.app import create_app_from_env
    f = tmp_path / "k"
    f.write_bytes(b"z" * 40)
    create_app_from_env({"AI_RES_CURSOR_HMAC_KEY_FILE": str(f)})
    assert any(isinstance(h.formatter, __import__("ai_res.platform.redaction", fromlist=["x"]).RedactingJsonFormatter)
               for h in logging.getLogger("uvicorn.error").handlers)


def test_redaction_is_linear_time_on_hostile_input():
    import time

    from ai_res.platform.redaction import redact_text
    for hostile in ("a." * 20_000, "A" * 40_000, "-----BEGIN PRIVATE KEY-----" * 2000, "token" * 8000, "a=" * 20_000):
        t0 = time.perf_counter()
        redact_text(hostile)
        assert time.perf_counter() - t0 < 0.5, hostile[:12]


def test_redaction_prefixed_and_suffixed_secret_names():
    from ai_res.platform.redaction import redact_text
    for text in ("access_token=abc123def456", "client_secret: hunter2hunter2", "refresh_token=xyz", "DB_PASSWORD=foo",
                 "SESSION_TOKEN=abcd", "my_password=abc", '"x-api-key": "k-12345"'):
        out = redact_text(f"call failed {text} end")
        assert REDACTED in out and not any(w in out for w in ("abc123def456", "hunter2hunter2", "xyz", "=foo", "abcd", "k-12345")), text


def test_unrepresentable_object_does_not_break_logging():
    class Bad:
        def __repr__(self):
            raise RuntimeError("no repr")

    buf = io.StringIO()
    log = configure_logging("INFO", buf)
    log.info("x", extra={"obj": Bad()})
    assert "unrepresentable" in buf.getvalue()


async def test_timeouts_must_be_positive_numbers():
    for bad in (None, 0, -1, True):
        with pytest.raises(ValueError):
            await decide_fail_closed(_Policy(Effect.ALLOW), REQ, timeout_seconds=bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await audit_or_abort(object(), AuditRecord(actor_id="u", action="a", outcome=AuditOutcome.ALLOWED, resource_type="P"),  # type: ignore[arg-type]
                                 timeout_seconds=bad)  # type: ignore[arg-type]


async def test_audit_hang_fails_closed():
    import asyncio

    class Hung:
        async def write(self, record):
            await asyncio.sleep(5)

    with pytest.raises(ProblemError) as e:
        await audit_or_abort(Hung(), AuditRecord(actor_id="u", action="a", outcome=AuditOutcome.ALLOWED, resource_type="P"),
                             timeout_seconds=0.05)
    assert e.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE


async def test_failure_after_response_start_is_reraised_and_span_marked_error(exporter):
    from ai_res.api.app import create_app
    from ai_res.platform.telemetry import build_tracer_provider
    app = create_app(Settings(environment="test"), build_tracer_provider(exporter))

    async def broken(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("mid-stream secret")

    app.router.routes.clear()
    app.mount("/s", broken)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "method": "GET", "path": "/s/x", "raw_path": b"/s/x", "query_string": b"", "root_path": "", "scheme": "http",
             "http_version": "1.1", "server": ("t", 80), "client": ("c", 1), "headers": []}
    with pytest.raises(RuntimeError):
        await app(scope, receive, send)
    assert sent[0]["status"] == 200 and not any(m["type"] == "http.response.body" and b"secret" in m.get("body", b"") for m in sent)
    span = exporter.get_finished_spans()[-1]
    assert span.status.status_code.name == "ERROR" and not span.events
