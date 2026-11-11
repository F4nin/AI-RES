"""AUTH-012 / Auth v1.1 §8: service identities are separate from human sessions and from each other; credentials are short-lived and audience-scoped."""
import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given
from hypothesis import strategies as st

from ai_res.modules.iam.service_tokens import ServiceTokenIssuer, ServiceTokenVerifier
from ai_res.modules.iam.tokens import new_session_token, parse_session_token
from ai_res.platform.ports import ServiceName

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
MAX_TTL = timedelta(minutes=5)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def pub(k: Ed25519PrivateKey) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


@pytest.fixture
def keys() -> dict[ServiceName, Ed25519PrivateKey]:
    return {ServiceName.MANAGER_RUNTIME: key(), ServiceName.WORKER_RUNTIME: key(), ServiceName.API: key()}


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def verifier(keys: dict[ServiceName, Ed25519PrivateKey], clock: Clock) -> ServiceTokenVerifier:
    return ServiceTokenVerifier({n: (pub(k),) for n, k in keys.items()}, max_ttl=MAX_TTL, clock=clock)


def issue(keys: dict[ServiceName, Ed25519PrivateKey], clock: Clock, issuer: ServiceName, audience: ServiceName, ttl: timedelta = timedelta(minutes=2)) -> str:
    return ServiceTokenIssuer(issuer, keys[issuer], max_ttl=MAX_TTL, clock=clock).issue(audience, ttl)


async def test_valid_token_yields_the_issuer_identity_for_the_intended_audience_only(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    t = issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API)
    ident = await verifier.verify_service_token(t, ServiceName.API)
    assert ident is not None and ident.name is ServiceName.MANAGER_RUNTIME and ident.audience is ServiceName.API
    assert ident.expires_at == T0 + timedelta(minutes=2)
    assert await verifier.verify_service_token(t, ServiceName.WORKER_RUNTIME) is None  # a token for the API is useless against another service


async def test_token_expires_and_is_not_valid_before_issue_time(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    t = issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API, ttl=timedelta(minutes=1))
    clock.now = T0 + timedelta(seconds=59)
    assert await verifier.verify_service_token(t, ServiceName.API) is not None
    clock.now = T0 + timedelta(seconds=61)
    assert await verifier.verify_service_token(t, ServiceName.API) is None
    clock.now = T0 - timedelta(minutes=10)  # presented long before it was issued
    assert await verifier.verify_service_token(t, ServiceName.API) is None


def test_lifetime_above_the_cap_cannot_be_issued(keys, clock) -> None:  # type: ignore[no-untyped-def]
    for ttl in (MAX_TTL + timedelta(seconds=1), timedelta(0), timedelta(seconds=-5)):
        with pytest.raises(ValueError):
            issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API, ttl=ttl)


async def test_a_worker_cannot_pass_as_the_manager_even_with_valid_looking_claims(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    # claims iss=MANAGER_RUNTIME but is signed with the worker's key
    worker_key = keys[ServiceName.WORKER_RUNTIME]
    forged = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, worker_key, max_ttl=MAX_TTL, clock=clock).issue(ServiceName.API, timedelta(minutes=1))
    assert await verifier.verify_service_token(forged, ServiceName.API) is None


async def test_unknown_issuer_and_self_audience_are_refused(keys, clock) -> None:  # type: ignore[no-untyped-def]
    only_manager = ServiceTokenVerifier({ServiceName.MANAGER_RUNTIME: (pub(keys[ServiceName.MANAGER_RUNTIME]),)}, max_ttl=MAX_TTL, clock=clock)
    assert await only_manager.verify_service_token(issue(keys, clock, ServiceName.WORKER_RUNTIME, ServiceName.API), ServiceName.API) is None
    with pytest.raises(ValueError):
        issue(keys, clock, ServiceName.API, ServiceName.API)


def tamper(token: str, part: int, mutate) -> str:  # type: ignore[no-untyped-def]
    pieces = token.split(".")
    pieces[part] = mutate(pieces[part])
    return ".".join(pieces)


async def test_tampering_with_payload_or_signature_is_detected(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    t = issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API)
    payload = json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "=="))
    payload["aud"] = "WORKER_RUNTIME"
    swapped = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    assert await verifier.verify_service_token(tamper(t, 1, lambda _: swapped), ServiceName.WORKER_RUNTIME) is None
    assert await verifier.verify_service_token(tamper(t, 2, lambda s: ("A" if s[0] != "A" else "B") + s[1:]), ServiceName.API) is None
    assert await verifier.verify_service_token(tamper(t, 0, lambda _: "ar2"), ServiceName.API) is None  # unknown version: fail closed


async def test_human_session_tokens_and_service_tokens_are_not_interchangeable(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    session = new_session_token(uuid4())
    assert await verifier.verify_service_token(session, ServiceName.API) is None  # a browser session is not accepted by a service endpoint
    assert parse_session_token(issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API)) is None  # a service token is not a session


@pytest.mark.parametrize("garbage", ["", "x", "ar1.", "ar1..", "ar1.a.b", "ar1." + "A" * 5000 + ".AAAA", "Bearer ar1.x.y", "ar1.%%%.%%%", "\x00",
                                     "ar1.e30.e30"])
async def test_garbage_never_raises_and_never_authenticates(verifier: ServiceTokenVerifier, garbage: str) -> None:
    assert await verifier.verify_service_token(garbage, ServiceName.API) is None


@given(st.text(max_size=300))
async def test_fuzzed_input_is_always_refused(text: str) -> None:
    v = ServiceTokenVerifier({ServiceName.API: (pub(key()),)}, max_ttl=MAX_TTL)
    assert await v.verify_service_token(text, ServiceName.API) is None


async def test_duplicate_or_unexpected_claims_are_refused(keys, clock, verifier) -> None:  # type: ignore[no-untyped-def]
    k = keys[ServiceName.MANAGER_RUNTIME]

    def sign(raw: bytes) -> str:
        body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(k.sign(b"ai-res-service-token-v1\x00ar1." + body.encode())).rstrip(b"=").decode()
        return f"ar1.{body}.{sig}"
    base = {"iss": "MANAGER_RUNTIME", "aud": "API", "iat": int(T0.timestamp()), "exp": int(T0.timestamp()) + 60, "jti": "j1"}
    assert await verifier.verify_service_token(sign(json.dumps(base).encode()), ServiceName.API) is not None  # control: the hand-built token is valid
    extra = json.dumps({**base, "role": "ADMIN"}).encode()
    dup = b'{"iss":"MANAGER_RUNTIME","iss":"API","aud":"API","iat":%d,"exp":%d,"jti":"j"}' % (int(T0.timestamp()), int(T0.timestamp()) + 60)
    far = json.dumps({**base, "exp": int(T0.timestamp()) + 3600}).encode()
    for bad in (extra, dup, far, json.dumps({**base, "iss": "NOT_A_SERVICE"}).encode(), json.dumps({**base, "iat": "now"}).encode()):
        assert await verifier.verify_service_token(sign(bad), ServiceName.API) is None


async def test_rotation_accepts_old_and_new_public_keys(keys, clock) -> None:  # type: ignore[no-untyped-def]
    new = key()
    v = ServiceTokenVerifier({ServiceName.MANAGER_RUNTIME: (pub(keys[ServiceName.MANAGER_RUNTIME]), pub(new))}, max_ttl=MAX_TTL, clock=clock)
    old_token = issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API)
    new_token = ServiceTokenIssuer(ServiceName.MANAGER_RUNTIME, new, max_ttl=MAX_TTL, clock=clock).issue(ServiceName.API, timedelta(minutes=1))
    assert await v.verify_service_token(old_token, ServiceName.API) is not None and await v.verify_service_token(new_token, ServiceName.API) is not None


def test_each_token_is_unique_and_carries_no_secret_material(keys, clock) -> None:  # type: ignore[no-untyped-def]
    a, b = issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API), issue(keys, clock, ServiceName.MANAGER_RUNTIME, ServiceName.API)
    assert a != b
    claims = json.loads(base64.urlsafe_b64decode(a.split(".")[1] + "=="))
    assert set(claims) == {"iss", "aud", "iat", "exp", "jti"}


def test_key_files_are_loaded_and_validated(tmp_path, clock) -> None:  # type: ignore[no-untyped-def]
    from cryptography.hazmat.primitives import serialization

    from ai_res.modules.iam.service_tokens import load_private_key, load_public_keys, verifier_from_settings
    from ai_res.platform.config import ConfigError, load_settings
    k = key()
    seed = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    priv, reg = tmp_path / "priv", tmp_path / "reg"
    priv.write_text(base64.b64encode(seed).decode() + "\n")
    reg.write_text(f"# registry\nMANAGER_RUNTIME {base64.b64encode(pub(k)).decode()}\nMANAGER_RUNTIME {base64.b64encode(pub(key())).decode()}\n")
    loaded = load_private_key(priv)
    assert pub(loaded) == pub(k) and len(load_public_keys(reg)[ServiceName.MANAGER_RUNTIME]) == 2
    assert verifier_from_settings(load_settings({"AI_RES_SERVICE_PUBLIC_KEYS_FILE": str(reg)}))
    for bad in ("", "not base64!", base64.b64encode(b"short").decode()):
        priv.write_text(bad)
        with pytest.raises(ConfigError):
            load_private_key(priv)
    for bad in ("NOT_A_SERVICE " + base64.b64encode(pub(k)).decode(), "API", f"API {base64.b64encode(b'short').decode()}"):
        reg.write_text(bad)
        with pytest.raises(ConfigError):
            load_public_keys(reg)
    with pytest.raises(ConfigError):
        verifier_from_settings(load_settings({}))
