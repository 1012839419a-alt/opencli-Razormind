import os
import stat

import pytest

from backend.config import Settings
from backend.security.local_auth import (
    hash_password,
    initialize_password_hash,
    load_password_hash,
    password_change_required,
    persist_password_hash,
    verify_password,
)


def test_default_password_hash_accepts_admin_only():
    encoded = hash_password("admin")
    assert verify_password("admin", encoded)
    assert not verify_password("wrong", encoded)


def test_password_hash_round_trip():
    encoded = hash_password("new-local-password")
    assert encoded.startswith("scrypt$")
    assert verify_password("new-local-password", encoded)
    assert not verify_password("admin", encoded)


def test_password_hash_persists_to_durable_state(tmp_path):
    state_path = tmp_path / "state" / "local-admin-password.hash"
    initial = hash_password("initial-local-password")
    encoded = hash_password("durable-local-password")

    initialize_password_hash(initial, str(state_path))
    assert password_change_required(str(state_path)) is True
    persist_password_hash(encoded, str(state_path))

    assert load_password_hash("configured-fallback-must-be-ignored", str(state_path)) == encoded
    assert password_change_required(str(state_path)) is False
    assert state_path.with_name(f"{state_path.name}.initialized").is_file()
    assert verify_password("durable-local-password", state_path.read_text().strip())
    if os.name != "nt":
        assert stat.S_IMODE(state_path.stat().st_mode) == 0o600


def test_password_update_cannot_initialize_missing_state(tmp_path):
    state_path = tmp_path / "local-admin-password.hash"

    with pytest.raises(RuntimeError, match="not initialized"):
        persist_password_hash(hash_password("replacement-password"), str(state_path))

    assert not state_path.exists()
    assert not state_path.with_name(f"{state_path.name}.initialized").exists()


def test_empty_durable_state_fails_closed(tmp_path):
    state_path = tmp_path / "local-admin-password.hash"
    state_path.write_text("", encoding="utf-8")

    state_path.with_name(f"{state_path.name}.initialized").write_text(
        "opencli-local-auth-state-v1:initial\n", encoding="utf-8"
    )
    assert load_password_hash("configured-fallback-must-be-ignored", str(state_path)) == ""


def test_empty_durable_directory_fails_closed(tmp_path):
    state_path = tmp_path / "local-admin-password.hash"

    assert load_password_hash(hash_password("admin"), str(state_path)) == ""
    assert not state_path.exists()
    assert not state_path.with_name(f"{state_path.name}.initialized").exists()


@pytest.mark.parametrize("missing", ["hash", "marker"])
def test_partial_durable_state_fails_closed(tmp_path, missing):
    state_path = tmp_path / "local-admin-password.hash"
    marker_path = state_path.with_name(f"{state_path.name}.initialized")
    if missing == "hash":
        marker_path.write_text("opencli-local-auth-state-v1:initial\n", encoding="utf-8")
    else:
        state_path.write_text(hash_password("admin"), encoding="utf-8")

    assert load_password_hash(hash_password("admin"), str(state_path)) == ""


def test_password_state_initialization_rejects_overwrite(tmp_path):
    state_path = tmp_path / "nested" / "local-admin-password.hash"
    first = hash_password("first-password")
    second = hash_password("second-password")

    initialize_password_hash(first, str(state_path))
    with pytest.raises(FileExistsError):
        initialize_password_hash(second, str(state_path))

    assert load_password_hash("ignored", str(state_path)) == first
    assert not verify_password("second-password", state_path.read_text().strip())


@pytest.mark.parametrize(
    "value",
    ["", "too-short", "change-me-in-production", "change-me-in-production-use-long-random-string"],
)
def test_settings_rejects_weak_or_public_secret_keys(value):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, secret_key=value)


def test_settings_default_secret_is_process_stable_and_unpredictable(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    first = Settings(_env_file=None).secret_key
    second = Settings(_env_file=None).secret_key

    assert first == second
    assert len(first) >= 32
    assert not first.startswith("change-me")
