from backend.security.local_auth import (
    DEFAULT_LOCAL_ADMIN_PASSWORD_HASH,
    hash_password,
    verify_password,
)


def test_default_password_hash_accepts_admin_only():
    assert verify_password("admin", DEFAULT_LOCAL_ADMIN_PASSWORD_HASH)
    assert not verify_password("wrong", DEFAULT_LOCAL_ADMIN_PASSWORD_HASH)


def test_password_hash_round_trip():
    encoded = hash_password("new-local-password")
    assert encoded.startswith("scrypt$")
    assert verify_password("new-local-password", encoded)
    assert not verify_password("admin", encoded)
