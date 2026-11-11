"""AUTH-003 / Auth v1.1 §3.2: Argon2id with unique salt, min length 15, local denylist, configurable parameters, constant-shape verification."""
import pytest

from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy, PasswordPolicyError

GOOD = "correct horse battery staple 42"


def _fast() -> PasswordHasherService:  # test-only cost; production parameters come from Settings (WORKING, OWASP-minimum defaults)
    return PasswordHasherService(time_cost=1, memory_kib=8, parallelism=1)


def test_hash_is_argon2id_with_unique_salt_and_never_plaintext() -> None:
    h = _fast()
    a, b = h.hash(GOOD), h.hash(GOOD)
    assert a.startswith("$argon2id$") and b.startswith("$argon2id$")
    assert a != b  # unique random salt per hash
    assert GOOD not in a


def test_verify_accepts_right_and_rejects_wrong_password() -> None:
    h = _fast()
    stored = h.hash(GOOD)
    assert h.verify(stored, GOOD) is True
    assert h.verify(stored, GOOD + "x") is False


def test_verify_never_raises_on_malformed_stored_hash() -> None:
    assert _fast().verify("not-a-hash", GOOD) is False
    assert _fast().verify("", GOOD) is False


def test_verify_against_missing_account_burns_comparable_work_and_is_false() -> None:
    h = _fast()
    assert h.verify_unknown_account(GOOD) is False  # AUTH-005: same code path cost as a real verification


def test_needs_rehash_when_parameters_are_raised() -> None:
    weak, strong = _fast(), PasswordHasherService(time_cost=2, memory_kib=16, parallelism=1)
    assert strong.needs_rehash(weak.hash(GOOD)) is True
    assert strong.needs_rehash(strong.hash(GOOD)) is False


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_cost_parameters_are_refused(bad: int) -> None:
    with pytest.raises(ValueError):
        PasswordHasherService(time_cost=bad, memory_kib=8, parallelism=1)


def test_policy_enforces_minimum_length_15() -> None:
    p = PasswordPolicy(denylist=frozenset())
    p.check("short-pass-14ch")  # exactly 15 characters is allowed
    with pytest.raises(PasswordPolicyError) as e:
        p.check("short-pass-14c")  # 14 is not
    assert e.value.reason == "too_short"


def test_policy_cannot_be_configured_below_normative_minimum() -> None:
    with pytest.raises(ValueError):
        PasswordPolicy(min_length=14, denylist=frozenset())


def test_policy_rejects_denylisted_password_case_and_space_insensitively() -> None:
    p = PasswordPolicy(denylist=frozenset({"passwordpassword1"}))
    with pytest.raises(PasswordPolicyError) as e:
        p.check("  PasswordPassword1 ")
    assert e.value.reason == "common_password"


def test_policy_accepts_long_passphrase_with_spaces_and_unicode() -> None:
    PasswordPolicy(denylist=frozenset()).check("пароль из многих слов и цифр 12345")


def test_policy_rejects_over_maximum_length_to_bound_hashing_cost() -> None:
    with pytest.raises(PasswordPolicyError) as e:
        PasswordPolicy(denylist=frozenset()).check("a" * 1025)
    assert e.value.reason == "too_long"


def test_policy_error_never_echoes_the_password() -> None:
    with pytest.raises(PasswordPolicyError) as e:
        PasswordPolicy(denylist=frozenset()).check("tiny-secret")
    assert "tiny-secret" not in str(e.value) and "tiny-secret" not in repr(e.value)


def test_shipped_denylist_loads_and_blocks_a_known_weak_value() -> None:
    p = PasswordPolicy.with_default_denylist()
    with pytest.raises(PasswordPolicyError):
        p.check("passwordpassword")
