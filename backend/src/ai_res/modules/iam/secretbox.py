"""Authenticated encryption for secrets stored in PostgreSQL (TOTP seeds). AES-256-GCM, random 96-bit nonce, key id in the blob so keys can rotate,
and the owner context as AAD so a ciphertext copied to another user/factor does not decrypt. Library primitive only (cryptography); no home-made crypto.

blob = 0x01 | len(key_id) | key_id | nonce(12) | ciphertext+tag
Rotation: add the new key, make it active, re-encrypt, only then remove the old key (an unknown key id fails closed).
"""
import base64
import binascii
import os
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ai_res.platform.config import ConfigError, Settings, read_secret_file

_VERSION = 1
_NONCE = 12


class SecretBoxError(Exception):
    """Decryption refused (wrong key/context, tampering, unknown key id). Never carries plaintext or key material."""


class SecretBox:
    def __init__(self, active_id: str, keys: Mapping[str, bytes]) -> None:
        if active_id not in keys:
            raise ValueError("active key id is not in the key ring")
        if any(len(k) != 32 for k in keys.values()):
            raise ValueError("every key must be exactly 32 bytes")
        if any(not 1 <= len(i.encode()) <= 255 for i in keys):
            raise ValueError("key ids must be 1..255 bytes")
        self._active, self._keys = active_id, dict(keys)

    def seal(self, plaintext: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE)
        kid = self._active.encode()
        return bytes([_VERSION, len(kid)]) + kid + nonce + AESGCM(self._keys[self._active]).encrypt(nonce, plaintext, aad)

    def open(self, blob: bytes, aad: bytes) -> bytes:
        try:
            if len(blob) < 2 or blob[0] != _VERSION:
                raise SecretBoxError("unsupported ciphertext")
            klen = blob[1]
            kid = blob[2:2 + klen].decode()
            nonce, body = blob[2 + klen:2 + klen + _NONCE], blob[2 + klen + _NONCE:]
            key = self._keys.get(kid)
            if key is None or len(nonce) != _NONCE or len(body) < 16:
                raise SecretBoxError("unknown key or malformed ciphertext")
            return AESGCM(key).decrypt(nonce, body, aad)
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise SecretBoxError("ciphertext rejected") from exc


def load_secret_box(settings: Settings) -> SecretBox:
    if settings.mfa_encryption_key_file is None:
        raise ConfigError("mfa_encryption_key_file is required")
    try:
        key = base64.b64decode(read_secret_file(settings.mfa_encryption_key_file), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError("mfa encryption key must be base64") from exc
    if len(key) != 32:
        raise ConfigError("mfa encryption key must decode to exactly 32 bytes")
    return SecretBox(settings.mfa_encryption_key_id, {settings.mfa_encryption_key_id: key})
