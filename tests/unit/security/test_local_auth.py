from backend.security.local_auth import (
    DEFAULT_LOCAL_ADMIN_PASSWORD_HASH,
    hash_password,
    load_password_hash,
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

def test_load_password_hash_prefers_persisted_value(tmp_path):
    persisted = hash_password("persisted-password")
    path = tmp_path / "local_admin_password_hash"
    path.write_text(persisted, encoding="utf-8")

    assert load_password_hash(str(path), DEFAULT_LOCAL_ADMIN_PASSWORD_HASH) == persisted
