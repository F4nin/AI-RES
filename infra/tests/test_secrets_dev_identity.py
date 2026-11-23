"""S07: format of the generated identity secrets (loaded by the backend's strict loaders)."""
import base64
from subprocess import CompletedProcess

import pytest
import secrets_dev as sd


def test_mfa_key_is_base64_of_exactly_32_bytes_and_unique():
    a, b = sd._generate("mfa_encryption_key"), sd._generate("mfa_encryption_key")
    assert len(base64.b64decode(a, validate=True)) == 32 and a != b


def test_bootstrap_secret_is_long_random_and_both_are_managed_secrets():
    assert len(sd._generate("bootstrap_secret")) >= 48
    assert {"mfa_encryption_key", "bootstrap_secret"} <= set(sd.NAMES) and len(sd.NAMES) == len(set(sd.NAMES))


def test_idempotency_keyring_is_one_key_id_and_32_bytes_and_is_a_managed_secret():
    line = sd._generate("idempotency_keyring")
    key_id, key = line.split()
    assert key_id == "k1" and len(base64.b64decode(key, validate=True)) == 32 and line != sd._generate("idempotency_keyring")
    assert "idempotency_keyring" in sd.NAMES


def test_manager_signing_key_is_a_32_byte_seed_and_the_public_registry_is_derived_from_it():
    seed = sd._generate("manager_signing_key")
    assert len(base64.b64decode(seed, validate=True)) == 32 and seed != sd._generate("manager_signing_key")
    line = sd.derive_service_public_keys({"manager_signing_key": seed})
    service, pub = line.split()
    assert service == "MANAGER_RUNTIME" and len(base64.b64decode(pub, validate=True)) == 32
    assert line == sd.derive_service_public_keys({"manager_signing_key": seed})  # deterministic: the registry is a pure function of the key
    assert {"manager_signing_key", "service_public_keys"} <= set(sd.NAMES)


def test_outbox_delivery_signing_key_has_a_dedicated_public_registry():
    seed = sd._generate("outbox_delivery_signing_key")
    assert len(base64.b64decode(seed, validate=True)) == 32
    line = sd.derive_assigned_delivery_public_keys({"outbox_delivery_signing_key": seed})
    service, public_key = line.split()
    assert service == "OUTBOX_DISPATCHER"
    assert len(base64.b64decode(public_key, validate=True)) == 32
    assert line == sd.derive_assigned_delivery_public_keys({"outbox_delivery_signing_key": seed})
    assert "OUTBOX_DISPATCHER" not in sd.derive_service_public_keys({"manager_signing_key": sd._generate("manager_signing_key")})
    assert {"outbox_delivery_signing_key", "assigned_delivery_public_keys"} <= set(sd.NAMES)


def test_legacy_secret_set_adds_a_matching_delivery_keypair_without_rotation():
    new_names = {"outbox_delivery_signing_key", "assigned_delivery_public_keys"}
    existing = {name: f"existing-{name}" for name in sd.NAMES if name not in new_names and name not in sd.TLS}
    merged, added = sd.merge_missing_secrets(existing)
    assert merged["service_public_keys"] == existing["service_public_keys"]
    assert merged["api_db_password"] == existing["api_db_password"]
    assert merged["assigned_delivery_public_keys"] == sd.derive_assigned_delivery_public_keys(merged)
    assert set(added) == new_names


def test_public_registry_without_signing_seed_fails_closed():
    existing = {"assigned_delivery_public_keys": "OUTBOX_DISPATCHER fixture-public-key"}
    with pytest.raises(SystemExit, match="without their signing seed"):
        sd.merge_missing_secrets(existing)


def test_delivery_keypair_mismatch_is_not_silently_persisted():
    registered_seed = sd._generate("outbox_delivery_signing_key")
    active_seed = sd._generate("outbox_delivery_signing_key")
    existing = {
        "outbox_delivery_signing_key": active_seed,
        "assigned_delivery_public_keys": sd.derive_assigned_delivery_public_keys({"outbox_delivery_signing_key": registered_seed}),
    }
    with pytest.raises(SystemExit, match="do not contain the public key"):
        sd.merge_missing_secrets(existing)


def test_delivery_keypair_upgrade_accepts_whitespace_used_by_shared_key_loader():
    seed = sd._generate("outbox_delivery_signing_key")
    public_record = sd.derive_assigned_delivery_public_keys({"outbox_delivery_signing_key": seed}).strip()
    existing = {"outbox_delivery_signing_key": seed, "assigned_delivery_public_keys": "\t" + public_record.replace(" ", "  \t") + "  \n"}
    merged, added = sd.merge_missing_secrets(existing)
    assert merged["assigned_delivery_public_keys"] == existing["assigned_delivery_public_keys"]
    assert "outbox_delivery_signing_key" not in added and "assigned_delivery_public_keys" not in added


@pytest.mark.parametrize(("status", "expected"), [(1, "support is required"), (0, "invalid Ed25519 public key")])
def test_invalid_openssl_result_does_not_disclose_subprocess_data(monkeypatch, status, expected):
    monkeypatch.setattr(sd.subprocess, "run", lambda *args, **kwargs: CompletedProcess([], status, b"fixture stdout", b"fixture stderr"))
    with pytest.raises(RuntimeError, match=expected) as caught:
        sd.ed25519_public_b64(base64.b64encode(bytes(32)).decode())
    assert "fixture" not in str(caught.value)
    assert caught.value.__context__ is None


def test_postgres_certificates_use_sha256_with_the_local_openssl():
    generated = sd.generate_tls()
    for name in ("postgres_tls_ca_cert", "postgres_tls_server_cert"):
        certificate = sd._run(["openssl", "x509", "-noout", "-text"], input=generated[name]).stdout
        algorithms = {line.strip() for line in certificate.splitlines() if "Signature Algorithm:" in line}
        assert algorithms == {"Signature Algorithm: ecdsa-with-SHA256"}
