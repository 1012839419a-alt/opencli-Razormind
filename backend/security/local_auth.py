"""Local-first administrator password and session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import tempfile
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from fastapi import HTTPException, status
from jose import jwt

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1


class LoginAttemptLimiter:
    """Small per-process guard against rapid password guessing."""

    def __init__(
        self, max_attempts: int = 10, window_seconds: int = 60, max_clients: int = 1024
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, client_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.get(client_id)
            if not attempts:
                return
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            if not attempts:
                self._attempts.pop(client_id, None)
                return
            if len(attempts) >= self.max_attempts:
                retry_after = max(1, int(self.window_seconds - (now - attempts[0])))
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many authentication attempts",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, client_id: str) -> None:
        with self._lock:
            if client_id not in self._attempts and len(self._attempts) >= self.max_clients:
                self._attempts.pop(next(iter(self._attempts)))
            self._attempts[client_id].append(time.monotonic())

    def reset(self, client_id: str) -> None:
        with self._lock:
            self._attempts.pop(client_id, None)


login_attempt_limiter = LoginAttemptLimiter()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = _SCRYPT_N, _SCRYPT_R, _SCRYPT_P
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)
    encode = base64.urlsafe_b64encode
    return f"scrypt${n}${r}${p}${encode(salt).decode()}${encode(digest).decode()}"


_STATE_MARKER_INITIAL_CONTENT = "opencli-local-auth-state-v1:initial\n"
_STATE_MARKER_CHANGED_CONTENT = "opencli-local-auth-state-v1:changed\n"
_VALID_STATE_MARKERS = frozenset(
    {_STATE_MARKER_INITIAL_CONTENT, _STATE_MARKER_CHANGED_CONTENT}
)


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt" or (int(n), int(r), int(p)) != (
            _SCRYPT_N,
            _SCRYPT_R,
            _SCRYPT_P,
        ):
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def issue_local_token(username: str, secret_key: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "local-admin",
            "name": "本地管理员",
            "username": username,
            "is_platform_admin": True,
            "auth_method": "local",
            "iat": now,
            "exp": now + timedelta(days=30),
        },
        secret_key,
        algorithm="HS256",
    )


def load_password_hash(configured_hash: str, state_path: str = "") -> str:
    """Load the local password hash, failing closed for incomplete durable state."""

    if not state_path:
        return configured_hash
    path = Path(state_path)
    marker_path = _state_marker_path(path)
    try:
        persisted = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    try:
        marker = marker_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not persisted or marker not in _VALID_STATE_MARKERS:
        return ""
    return persisted


def password_change_required(state_path: str = "") -> bool:
    """Return whether the installer-created initial password is still active."""

    if not state_path:
        return False
    try:
        return (
            _state_marker_path(Path(state_path)).read_text(encoding="utf-8")
            == _STATE_MARKER_INITIAL_CONTENT
        )
    except OSError:
        return False


def _state_marker_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.initialized")


def _write_private_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def initialize_password_hash(password_hash: str, state_path: str = "") -> None:
    """Create local authentication state exactly once.

    Both files must be absent.  A pre-existing or partially-created state is
    never overwritten, so an installer cannot silently replace an operator's
    password.  Readers fail closed while the two files are being created.
    """

    if not state_path:
        raise ValueError("local authentication state path is required")
    path = Path(state_path)
    marker_path = _state_marker_path(path)
    created: list[Path] = []
    try:
        _write_private_exclusive(marker_path, _STATE_MARKER_INITIAL_CONTENT)
        created.append(marker_path)
        _write_private_exclusive(path, f"{password_hash}\n")
        created.append(path)
    except BaseException:
        for created_path in created:
            created_path.unlink(missing_ok=True)
        raise


def _write_private_exclusive(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor != -1:
            os.close(descriptor)
    os.chmod(path, 0o600)


def persist_password_hash(password_hash: str, state_path: str = "") -> None:
    """Persist the local password in a server-owned durable state file."""

    if not state_path:
        raise ValueError("local authentication state path is required")
    path = Path(state_path)
    marker_path = _state_marker_path(path)
    try:
        marker = marker_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("local authentication state is not initialized") from exc
    if marker not in _VALID_STATE_MARKERS or not path.is_file():
        raise RuntimeError("local authentication state is incomplete")
    _write_private_atomic(path, f"{password_hash}\n")
    _write_private_atomic(marker_path, _STATE_MARKER_CHANGED_CONTENT)
