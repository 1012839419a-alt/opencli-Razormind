"""Single-owner appliance authentication and opaque browser sessions."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.config import Settings
from backend.database import AsyncSessionLocal
from backend.models.identity import (
    LocalAuthSession,
    LocalCredential,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.schemas.local_auth import normalize_username

SESSION_COOKIE_NAME = "opencli_session"
LOCAL_AUTH_STATE_KEY = "opencli_local_identity"
CSRF_HEADER_NAME = "X-OpenCLI-CSRF"
CSRF_HEADER_VALUE = "1"
LOCAL_OWNER_SUBJECT = "local:owner"

# These are the only API routes which may cross the Fleet middleware without
# an already-authenticated browser session. Logout is intentionally excluded:
# it crosses with a valid session and the normal write-CSRF requirement.
PUBLIC_LOCAL_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/status",
        "/api/v1/auth/setup",
        "/api/v1/auth/login",
    }
)

_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CROCKFORD_CODE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{10}$")
_PASSWORD_HASH_PREFIX = "$bcrypt-sha256$v=1$"
_PASSWORD_BCRYPT_ROUNDS = 12
_DUMMY_PASSWORD_HASH: str | None = None

# Middleware cannot use FastAPI's request-scoped dependency session, so it
# opens a short read-only session through this replaceable factory. Keeping the
# seam explicit also lets isolated integration tests bind it to their engine.
local_auth_session_factory = AsyncSessionLocal


class LocalOwnerAlreadyInitialized(Exception):
    pass


class DeviceClaimUnavailable(Exception):
    pass


class InvalidDeviceClaim(Exception):
    pass


class InvalidLocalCredentials(Exception):
    pass


@dataclass(frozen=True)
class LocalSessionIdentity:
    user_id: str
    subject: str
    email: str | None
    name: str | None
    username: str


@dataclass(frozen=True)
class LocalSessionGrant:
    token: str
    expires_at: datetime
    identity: LocalSessionIdentity


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_public_local_auth_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in PUBLIC_LOCAL_AUTH_PATHS


def local_session_write_has_csrf(method: str, header_value: str) -> bool:
    return method.upper() in _SAFE_HTTP_METHODS or secrets.compare_digest(
        header_value.encode("utf-8"), CSRF_HEADER_VALUE.encode("utf-8")
    )


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def hash_password(password: str) -> str:
    """Hash an arbitrary-length UTF-8 password without bcrypt's 72-byte truncation.

    The SHA-256 digest is fixed-width and bcrypt still supplies the per-password
    salt and work factor.  This deliberately avoids passlib's legacy bcrypt
    backend probe, which is incompatible with bcrypt 5.x.
    """

    digest = hashlib.sha256(password.encode("utf-8")).digest()
    encoded = await run_in_threadpool(
        bcrypt.hashpw,
        digest,
        bcrypt.gensalt(rounds=_PASSWORD_BCRYPT_ROUNDS),
    )
    return f"{_PASSWORD_HASH_PREFIX}{encoded.decode('ascii').removeprefix('$')}"


async def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash.startswith(_PASSWORD_HASH_PREFIX):
        return False
    encoded = f"${password_hash.removeprefix(_PASSWORD_HASH_PREFIX)}".encode("ascii")
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    try:
        return await run_in_threadpool(bcrypt.checkpw, digest, encoded)
    except (UnicodeEncodeError, TypeError, ValueError):
        return False


async def local_auth_initialized(db: AsyncSession) -> bool:
    credential_id = await db.scalar(select(LocalCredential.id).limit(1))
    return credential_id is not None


def device_claim_available(settings: Settings) -> bool:
    """Return whether this deployment can complete one-time owner setup."""
    return bool(_CROCKFORD_CODE.fullmatch(settings.device_claim_code.strip().upper()))


async def claim_local_owner(
    db: AsyncSession,
    *,
    claim_code: str,
    username: str,
    display_name: str | None,
    password: str,
    settings: Settings,
) -> LocalSessionIdentity:
    """Consume the deployment claim by creating the sole local owner."""
    if await local_auth_initialized(db):
        raise LocalOwnerAlreadyInitialized

    configured_claim = settings.device_claim_code.strip().upper()
    if not device_claim_available(settings):
        raise DeviceClaimUnavailable
    candidate = claim_code.strip().upper()
    if not _CROCKFORD_CODE.fullmatch(candidate) or not secrets.compare_digest(
        candidate.encode("ascii"), configured_claim.encode("ascii")
    ):
        raise InvalidDeviceClaim

    normalized_username = normalize_username(username)
    password_hash = await hash_password(password)

    user = await db.scalar(select(User).where(User.subject == LOCAL_OWNER_SUBJECT))
    if user is None:
        user = User(
            subject=LOCAL_OWNER_SUBJECT,
            display_name=display_name or normalized_username,
            disabled=False,
        )
        db.add(user)
        await db.flush()
    else:
        user.disabled = False
        if display_name is not None or not user.display_name:
            user.display_name = display_name or normalized_username

    db.add(
        LocalCredential(
            user_id=user.id,
            singleton_key="owner",
            username=normalized_username,
            password_hash=password_hash,
        )
    )

    workspaces = list((await db.scalars(select(Workspace))).all())
    if not workspaces:
        workspace = Workspace(name="我的空间", slug="my-space", active=True)
        db.add(workspace)
        await db.flush()
        workspaces = [workspace]

    existing_memberships = {
        membership.workspace_id: membership
        for membership in (
            await db.scalars(
                select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
            )
        ).all()
    }
    for workspace in workspaces:
        membership = existing_memberships.get(workspace.id)
        if membership is None:
            db.add(
                WorkspaceMembership(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role=WorkspaceRole.ADMIN,
                )
            )
        else:
            membership.role = WorkspaceRole.ADMIN

    await db.flush()
    return _identity_from_user(user, normalized_username)


async def authenticate_local_owner(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    settings: Settings,
) -> LocalSessionIdentity:
    """Verify the owner password with bounded lockout and uniform failure."""
    global _DUMMY_PASSWORD_HASH

    normalized_username = normalize_username(username)
    result = (
        await db.execute(
            select(LocalCredential, User)
            .join(User, User.id == LocalCredential.user_id)
            .where(LocalCredential.username == normalized_username)
        )
    ).one_or_none()

    if result is None:
        if _DUMMY_PASSWORD_HASH is None:
            _DUMMY_PASSWORD_HASH = await hash_password("opencli-dummy-owner-password")
        await verify_password(password, _DUMMY_PASSWORD_HASH)
        raise InvalidLocalCredentials

    credential, user = result
    now = utcnow()
    locked_until = _as_utc(credential.locked_until)
    password_valid = await verify_password(password, credential.password_hash)

    if locked_until is not None and locked_until > now:
        raise InvalidLocalCredentials

    if locked_until is not None:
        credential.locked_until = None
        credential.failed_attempts = 0

    if not password_valid or user.disabled:
        max_failures = max(1, settings.local_login_max_failures)
        credential.failed_attempts += 1
        if credential.failed_attempts >= max_failures:
            credential.locked_until = now + timedelta(
                seconds=max(1, settings.local_login_lock_seconds)
            )
        await db.flush()
        raise InvalidLocalCredentials

    credential.failed_attempts = 0
    credential.locked_until = None
    credential.last_login_at = now
    await db.flush()
    return _identity_from_user(user, credential.username)


async def create_local_session(
    db: AsyncSession,
    *,
    identity: LocalSessionIdentity,
    remember_device: bool,
    settings: Settings,
) -> LocalSessionGrant:
    now = utcnow()
    ttl_seconds = (
        settings.local_remember_session_ttl_seconds
        if remember_device
        else settings.local_session_ttl_seconds
    )
    expires_at = now + timedelta(seconds=max(60, ttl_seconds))
    token = secrets.token_urlsafe(32)
    db.add(
        LocalAuthSession(
            user_id=identity.user_id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
            last_seen_at=now,
        )
    )
    await db.flush()
    return LocalSessionGrant(token=token, expires_at=expires_at, identity=identity)


async def get_local_session_identity(
    db: AsyncSession, token: str
) -> LocalSessionIdentity | None:
    if not token:
        return None
    result = (
        await db.execute(
            select(LocalAuthSession, User, LocalCredential)
            .join(User, User.id == LocalAuthSession.user_id)
            .join(LocalCredential, LocalCredential.user_id == User.id)
            .where(LocalAuthSession.token_hash == hash_session_token(token))
            .where(LocalAuthSession.revoked_at.is_(None))
        )
    ).one_or_none()
    if result is None:
        return None
    session, user, credential = result
    if user.disabled or _as_utc(session.expires_at) <= utcnow():
        return None
    return _identity_from_user(user, credential.username)


async def authenticate_local_session(token: str) -> LocalSessionIdentity | None:
    """Resolve a browser session from middleware's independent DB session."""
    async with local_auth_session_factory() as db:
        return await get_local_session_identity(db, token)


async def revoke_local_session(db: AsyncSession, token: str) -> bool:
    if not token:
        return False
    session = await db.scalar(
        select(LocalAuthSession).where(
            LocalAuthSession.token_hash == hash_session_token(token),
            LocalAuthSession.revoked_at.is_(None),
        )
    )
    if session is None:
        return False
    session.revoked_at = utcnow()
    await db.flush()
    return True


def _identity_from_user(user: User, username: str) -> LocalSessionIdentity:
    return LocalSessionIdentity(
        user_id=user.id,
        subject=user.subject,
        email=user.email,
        name=user.display_name or username,
        username=username,
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
