"""Password hashing and policy (Auth v1.1 §3.2, AUTH-003).

Argon2id with a unique random salt per hash. Cost parameters are configuration (Auth v1.1 §3.2: "configurable, OWASP/hardware driven");
the defaults in Settings are the OWASP Password Storage Cheat Sheet minimum profile and are WORKING until benchmarked on the target (ADR-061).
No pepper is used: a pepper would need a secret outside the DB (Secrets v1.1) and is not an MVP requirement.
"""
import secrets
import unicodedata
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 15  # normative floor (Auth v1.1 §3.2); configuration may raise it, never lower it
MAX_LENGTH = 1024  # bounds hashing work for an attacker-chosen input


class PasswordPolicyError(ValueError):
    """`reason` is a stable machine code. The message never contains the password."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"password rejected: {reason}")
        self.reason = reason


def _normalise(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def load_denylist(path: Path | None = None) -> frozenset[str]:
    text = path.read_text(encoding="utf-8") if path is not None else resources.files("ai_res.modules.iam").joinpath("denylist.txt").read_text(encoding="utf-8")
    return frozenset(_normalise(line) for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    denylist: frozenset[str]
    min_length: int = MIN_LENGTH

    def __post_init__(self) -> None:
        if self.min_length < MIN_LENGTH:
            raise ValueError(f"min_length cannot be below the normative {MIN_LENGTH}")

    @classmethod
    def with_default_denylist(cls, path: Path | None = None, min_length: int = MIN_LENGTH) -> "PasswordPolicy":
        return cls(denylist=load_denylist(path), min_length=min_length)

    def check(self, password: str) -> None:
        length = len(unicodedata.normalize("NFKC", password))
        if length < self.min_length:
            raise PasswordPolicyError("too_short")
        if length > MAX_LENGTH:
            raise PasswordPolicyError("too_long")
        if _normalise(password) in self.denylist:
            raise PasswordPolicyError("common_password")


class PasswordHasherService:
    def __init__(self, *, time_cost: int, memory_kib: int, parallelism: int) -> None:
        if min(time_cost, memory_kib, parallelism) < 1:
            raise ValueError("argon2 cost parameters must be positive")
        self._hasher = PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism, type=Type.ID)
        # Hash of a random throw-away value, computed with the CURRENT parameters: verifying against it costs the same as a real account (AUTH-005).
        self._decoy = self._hasher.hash(unicodedata.normalize("NFKC", "decoy-" + secrets.token_urlsafe(24)))

    def hash(self, password: str) -> str:
        return self._hasher.hash(unicodedata.normalize("NFKC", password))

    def verify(self, stored_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(stored_hash, unicodedata.normalize("NFKC", password))
        except (VerificationError, InvalidHashError):
            return False

    def verify_unknown_account(self, password: str) -> bool:
        """Spend a real verification on a decoy hash so unknown-account and wrong-password logins are indistinguishable by timing."""
        self.verify(self._decoy, password)
        return False

    def needs_rehash(self, stored_hash: str) -> bool:
        return self._hasher.check_needs_rehash(stored_hash)
