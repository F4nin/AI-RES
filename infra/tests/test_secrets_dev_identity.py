"""S07: format of the generated identity secrets (loaded by the backend's strict loaders)."""
import base64

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
