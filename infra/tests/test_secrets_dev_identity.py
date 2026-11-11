"""S07: format of the generated identity secrets (loaded by the backend's strict loaders)."""
import base64

import secrets_dev as sd


def test_mfa_key_is_base64_of_exactly_32_bytes_and_unique():
    a, b = sd._generate("mfa_encryption_key"), sd._generate("mfa_encryption_key")
    assert len(base64.b64decode(a, validate=True)) == 32 and a != b


def test_bootstrap_secret_is_long_random_and_both_are_managed_secrets():
    assert len(sd._generate("bootstrap_secret")) >= 48
    assert {"mfa_encryption_key", "bootstrap_secret"} <= set(sd.NAMES) and len(sd.NAMES) == len(set(sd.NAMES))
