"""Secrets & Key Management v1.1 §3/§4/§7: TOTP seeds are encrypted at rest with a rotatable key and bound to their owner; recovery codes are one-way hashed."""
import base64
from datetime import UTC, datetime
from pathlib import Path

import pyotp
import pytest

from ai_res.modules.iam.secretbox import SecretBox, SecretBoxError, load_secret_box
from ai_res.modules.iam.totp import generate_recovery_codes, match_totp_step, normalise_recovery_code, recovery_digest
from ai_res.platform.config import ConfigError, load_settings

KEY1, KEY2 = bytes(range(32)), bytes(range(32, 64))
AAD = b"mfa-totp:org:user:factor"


def test_round_trip_and_ciphertext_hides_plaintext() -> None:
    box = SecretBox("k1", {"k1": KEY1})
    blob = box.seal(b"JBSWY3DPEHPK3PXP", AAD)
    assert b"JBSWY3DPEHPK3PXP" not in blob and box.open(blob, AAD) == b"JBSWY3DPEHPK3PXP"
    assert box.seal(b"x", AAD) != box.seal(b"x", AAD)  # fresh random nonce each time


def test_ciphertext_is_bound_to_its_owner_context() -> None:
    box = SecretBox("k1", {"k1": KEY1})
    with pytest.raises(SecretBoxError):
        box.open(box.seal(b"seed", AAD), b"mfa-totp:org:OTHER-USER:factor")  # a row copied to another user's factor does not decrypt


def test_tampered_or_truncated_blob_is_refused() -> None:
    box = SecretBox("k1", {"k1": KEY1})
    blob = bytearray(box.seal(b"seed", AAD))
    blob[-1] ^= 1
    for bad in (bytes(blob), b"", b"\x01", box.seal(b"seed", AAD)[:-3], b"\x09" + bytes(blob)[1:]):
        with pytest.raises(SecretBoxError):
            box.open(bad, AAD)


def test_rotation_new_key_encrypts_old_key_still_decrypts_and_unknown_key_fails() -> None:
    old = SecretBox("k1", {"k1": KEY1}).seal(b"seed", AAD)
    rotated = SecretBox("k2", {"k1": KEY1, "k2": KEY2})
    assert rotated.open(old, AAD) == b"seed"
    assert rotated.open(rotated.seal(b"seed", AAD), AAD) == b"seed"
    with pytest.raises(SecretBoxError):
        SecretBox("k2", {"k2": KEY2}).open(old, AAD)  # retired key: re-encrypt before removing it


def test_keys_must_be_32_bytes_and_active_key_must_exist() -> None:
    with pytest.raises(ValueError):
        SecretBox("k1", {"k1": b"short"})
    with pytest.raises(ValueError):
        SecretBox("missing", {"k1": KEY1})


def test_load_from_file_requires_base64_32_byte_key(tmp_path: Path) -> None:
    good = tmp_path / "key"
    good.write_text(base64.b64encode(KEY1).decode() + "\n")
    s = load_settings({"AI_RES_MFA_ENCRYPTION_KEY_FILE": str(good)})
    assert load_secret_box(s).open(load_secret_box(s).seal(b"s", AAD), AAD) == b"s"
    bad = tmp_path / "bad"
    bad.write_text("not base64 of 32 bytes")
    with pytest.raises(ConfigError):
        load_secret_box(load_settings({"AI_RES_MFA_ENCRYPTION_KEY_FILE": str(bad)}))
    with pytest.raises(ConfigError):
        load_secret_box(load_settings({}))


NOW = datetime(2026, 11, 11, 12, 0, 10, tzinfo=UTC)
SECRET = pyotp.random_base32()


def code_at(offset_steps: int) -> str:
    return pyotp.TOTP(SECRET).at(int(NOW.timestamp()) + offset_steps * 30)


def test_current_and_adjacent_steps_match_within_window_and_report_the_step() -> None:
    step = int(NOW.timestamp()) // 30
    assert match_totp_step(SECRET, code_at(0), NOW, window=1) == step
    assert match_totp_step(SECRET, code_at(-1), NOW, window=1) == step - 1
    assert match_totp_step(SECRET, code_at(1), NOW, window=1) == step + 1


def test_codes_outside_the_window_or_malformed_do_not_match() -> None:
    assert match_totp_step(SECRET, code_at(-3), NOW, window=1) is None
    assert match_totp_step(SECRET, code_at(3), NOW, window=1) is None
    for bad in ("", "12345", "1234567", "abcdef", "000000 "):
        assert match_totp_step(SECRET, bad, NOW, window=1) is None


def test_recovery_codes_are_unique_high_entropy_and_normalised_before_hashing() -> None:
    codes = generate_recovery_codes(10)
    assert len(set(codes)) == 10 and all(len(normalise_recovery_code(c)) == 24 for c in codes)
    c = codes[0]
    assert recovery_digest(c) == recovery_digest(c.lower().replace("-", " ")) and len(recovery_digest(c)) == 32
    assert recovery_digest(codes[0]) != recovery_digest(codes[1])
