"""Local-first administrator password and session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jose import jwt


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)
    encode = base64.urlsafe_b64encode
    return f"scrypt${n}${r}${p}${encode(salt).decode()}${encode(digest).decode()}"

DEFAULT_LOCAL_ADMIN_PASSWORD_HASH = hash_password("admin")


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
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


def load_password_hash(path: str, fallback: str) -> str:
    """Load a persisted password hash, falling back to configured settings."""

    try:
        persisted = Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return fallback
    return persisted or fallback


def persist_password_hash(password_hash: str) -> None:
    """Persist the local password in the deployment and current process."""

    os.environ["LOCAL_ADMIN_PASSWORD_HASH"] = password_hash
    durable_path = os.environ.get("LOCAL_ADMIN_PASSWORD_HASH_FILE")
    if durable_path is None and Path("/data").is_dir():
        durable_path = "/data/local_admin_password_hash"
    if durable_path:
        durable_file = Path(durable_path)
        durable_file.parent.mkdir(parents=True, exist_ok=True)
        durable_file.write_text(password_hash + "\n", encoding="utf-8")

    path = os.environ.get("ENV_FILE_PATH")
    if not path:
        for candidate in (Path("/app/.env"), Path(__file__).resolve().parents[2] / ".env"):
            if candidate.exists():
                path = str(candidate)
                break
        else:
            path = str(Path(__file__).resolve().parents[2] / ".env")

    env_path = Path(path)
    try:
        content = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    new_line = f"LOCAL_ADMIN_PASSWORD_HASH={password_hash}"
    pattern = r"^LOCAL_ADMIN_PASSWORD_HASH=.*$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(content, encoding="utf-8")
